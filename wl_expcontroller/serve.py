"""`wlx serve` -- the browser console's process (P4d-2b slices b1 and b2a).

Spec: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §1-§5.

**Its own process, beside `taskd` and never inside it** (S9a §7: the hot loop never
serves a request). It holds one `link.ZmqConsole`, keeps the latest frame, and serves
three things over the stdlib `ThreadingHTTPServer` -- the stack wl-preproc's responder
already runs, so no new dependency:

- `GET /` -- the page, every pane rendered in Python (`web.py`).
- `GET /events` -- server-sent events: one full render on connect, then the fragments
  that changed, once per frame this browser keeps up with and once per keepalive
  interval between frames, each re-rendered from a fresh snapshot. Every event
  carries `live` and `age` -- how long this process has held the latest frame, `null`
  before any -- which the page's stale timer runs on (Ruling 12, 2026-09-27).
- `GET /health` -- `health.py`'s body for wl-works, behind a bearer token.

- `POST /commands` (P4d-2b b2a, spec §5.3) -- one JSON command from the box's own
  page, accepted only under spec §2's four checks and validated before anything is
  queued (`parse_command`); answered *sent*, *not delivered* or *busy*, the truth
  about delivery.

Everything else is 404 or 405, as JSON, never the stdlib's HTML page. **Every request
is answered only when its `Host` names this console** (spec §2, §5.3): loopback, the
box's own names and addresses, and `--allow-host` names (`box_names`); anything else
gets a JSON 421 and no page, which closes DNS rebinding on the LAN-open reads too.

**Restarting it changes nothing in `taskd`** (spec §2): it reads the PUB socket, and
what it sends is acknowledged or said not to be; a pause, a schedule and every
setting are held by `taskd`, not here.

**Threads, and what each owns** (spec §2: each ZMQ socket has one owning thread).
The telemetry thread (`Server._listen`) owns a read-only `ZmqConsole`, its SUB
socket. The command thread (an `Outbox`) owns a `ZmqCommands`, the REQ socket, and
takes commands from a bounded queue. The mark thread (another `Outbox`) owns a
`ZmqMarks`, the PUSH socket to the session's mark endpoint, so a mark's signal goes
ahead of any command waiting on the rig's acknowledgment (spec §5.3). Each browser's
`/events` and each `POST` runs on the HTTP server's thread for that connection.

**No timing claim is made here.** `DEFAULT_STALE_AFTER_S` is a display choice (spec
§3); `QUEUE_DEPTH`, `RATE_SAMPLE_S`, `KEEPALIVE_S`, `REQUEST_TIMEOUT_S`, `RETRY_MS`,
`COMMAND_QUEUE_DEPTH`, `MARK_QUEUE_DEPTH` and the link's `REPLY_TIMEOUT_S` and
`CONNECT_TIMEOUT_S` are housekeeping, not a measurement of this system.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import queue
import secrets
import socket
import sys
import threading
import time
import traceback
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from wl_expcontroller import health as _health
from wl_expcontroller import link as _link
from wl_expcontroller import web as _web
from wl_expcontroller import welfare as _welfare

#: Seconds without a frame, while more are due, before the page greys and `/health`
#: says `degraded`. A display choice (spec §3), not a measurement.
DEFAULT_STALE_AFTER_S = 30.0
#: How many frames one browser's queue holds before its oldest is dropped (spec §2).
#: Small on purpose: telemetry is latest-wins, and a stream renders only the newest
#: frame it finds waiting (`Hub.take`).
QUEUE_DEPTH = 8
#: Trials per minute is read over the frames of the last five minutes (spec §4.1)...
RATE_WINDOW_S = 300.0
#: ...sampled at most once a second, so the window holds a few hundred points however
#: fast a simulator publishes.
RATE_SAMPLE_S = 1.0

#: What `Hub.take` returns once the hub is closed: the stream ends.
CLOSED = object()


def _put_dropping_oldest(subscriber: queue.Queue, item: object) -> None:
    """Queue `item`, dropping the oldest item waiting if the queue is full (spec §2): a
    browser that falls behind loses its oldest frames, never the newest, and never
    holds up the thread that offers them."""
    while True:
        try:
            subscriber.put_nowait(item)
            return
        except queue.Full:
            try:
                subscriber.get_nowait()
            except queue.Empty:
                pass


class Hub:
    """The latest frame, the rate window, and every open stream's queue (spec §2).

    `offer` and `reject` are called by the telemetry thread; everything else by HTTP
    handler threads. One lock guards the frame, the window and the table of
    subscribers; each queue is thread-safe on its own.

    **`offer` and `reject` assume one producer thread**, `Server._listen`, and are
    not safe to call from two at once: each copies the table of subscribers under the
    lock and pushes to the copy after releasing it. A `close()` that lands between
    the copy and the push can therefore leave one stale frame queued behind a
    stream's `CLOSED`. That is bounded -- one item per stream, from the one offer in
    flight -- and it cannot evict `CLOSED`: a queue holds `QUEUE_DEPTH` (8) items, so
    one more push drops only the oldest, and `take` returns `CLOSED` whenever it
    meets it.

    **One clock, and it is steady** (ledger Ruling 1, 2026-09-27). `steady` is what a
    frame is aged on -- `View.frame_age_s`, which the page's time since the last reward
    adds to the frame's own `wall_at` and `/health` reports as the last frame's age --
    and what the rate is read on. `welfare.steady_seconds` by default, which keeps
    counting while the host is asleep (P4d-2a I1), and injectable so that no test reads
    a real clock. **There is no wall clock here**: this process's host clock parts from
    a session's anchored one by any step it has taken since the session began, so
    nothing here subtracts it from a session instant.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        steady: Callable[[], float] = _welfare.steady_seconds,
        marks: bool = False,
    ) -> None:
        #: The PUB endpoint the telemetry thread reads, handed to every `View` so a
        #: page with no frame names where it is listening (m4). No default: a hub
        #: that did not know it would have the page guess.
        self._endpoint = endpoint
        #: Whether this console has the session's mark endpoint (P4d-2b b2a), for
        #: every `View`: without it the page greys its mark control.
        self._marks = marks
        self._steady = steady
        self._lock = threading.Lock()
        self._frame: _link.Telemetry | None = None
        #: When `_frame` arrived, on `steady`.
        self._received: float | None = None
        #: `(steady, trial_index)` sampled at most every `RATE_SAMPLE_S`, within
        #: `RATE_WINDOW_S` of the newest frame.
        self._points: deque = deque()
        #: The newest frame's `(steady, trial_index)`, sampled or not.
        self._newest: tuple[float, int] | None = None
        self._rejected: str | None = None
        #: Each open stream's queue, and whether it is on the box.
        self._subscribers: dict[queue.Queue, bool] = {}
        self._closed = False

    def offer(self, frame: _link.Telemetry) -> None:
        """Keep `frame` as the latest and hand it to every open stream.

        The rate window restarts when the session changes or its trial count goes
        back: a new `wlx run` on the same link is a new session, and a rate across two
        would describe neither. A good frame clears a refusal (`reject`).
        """
        now = self._steady()
        with self._lock:
            previous = self._frame
            if (
                previous is None
                or previous.session_id != frame.session_id
                or frame.trial_index < previous.trial_index
            ):
                self._points.clear()
            if not self._points or now - self._points[-1][0] >= RATE_SAMPLE_S:
                self._points.append((now, frame.trial_index))
            while now - self._points[0][0] > RATE_WINDOW_S:
                self._points.popleft()
            self._newest = (now, frame.trial_index)
            self._frame, self._received, self._rejected = frame, now, None
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, frame)

    def reject(self, why: str) -> None:
        """Say that a frame arrived and could not be used, and wake every stream to
        show it (`Server._listen`). The last good frame stays: a console that cannot
        read one frame shows what it last could, beside the reason -- never a guess."""
        with self._lock:
            self._rejected = why
            latest = self._frame
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, latest)

    def _rate(self) -> float | None:
        """Trials per minute over the window. The caller holds the lock."""
        if not self._points or self._newest is None:
            return None
        (t0, n0), (t1, n1) = self._points[0], self._newest
        if t1 <= t0:
            return None
        return 60.0 * (n1 - n0) / (t1 - t0)

    def trials_per_min(self) -> float | None:
        """Derived here, from `trial_index` and when frames arrived (spec §4.1); `None`
        until two frames a moment apart exist. **Bounds nothing**, and the page says
        it is derived."""
        with self._lock:
            return self._rate()

    def snapshot(
        self, *, on_box: bool, stale_after_s: float, can_write: bool = False
    ) -> tuple[_link.Telemetry | None, _web.View]:
        """The latest frame and the `View` a render of it needs, read together. The
        frame's age is on `steady` alone (ledger Ruling 1). `can_write` is the
        handler's to say (P4d-2b b2a, `may_write`); a caller that does not say gets a
        view that may not write."""
        now = self._steady()
        with self._lock:
            latest = self._frame
            age = None if self._received is None else now - self._received
            rate = self._rate()
            lan = sum(1 for box in self._subscribers.values() if not box)
            rejected = self._rejected
        return latest, _web.View(
            frame_age_s=age,
            stale_after_s=stale_after_s,
            trials_per_min=rate,
            on_box=on_box,
            lan_viewers=lan,
            rejected=rejected,
            endpoint=self._endpoint,
            can_write=can_write,
            can_mark=self._marks,
        )

    def subscribe(self, *, on_box: bool) -> queue.Queue:
        """A new stream's bounded queue. After `close`, one that is already closed."""
        subscriber: queue.Queue = queue.Queue(maxsize=QUEUE_DEPTH)
        with self._lock:
            if self._closed:
                subscriber.put_nowait(CLOSED)
                return subscriber
            self._subscribers[subscriber] = on_box
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self._subscribers.pop(subscriber, None)

    def viewers(self) -> tuple[int, int]:
        """How many streams are open: `(on the box, from the LAN)`."""
        with self._lock:
            box = sum(1 for on in self._subscribers.values() if on)
            return box, len(self._subscribers) - box

    def take(self, subscriber: queue.Queue, timeout: float) -> object:
        """The newest item waiting on `subscriber` -- a frame, `None` when a refusal
        woke it before any frame arrived, or `CLOSED` -- waiting up to `timeout`
        seconds and raising `queue.Empty` after that.

        **Older frames are skipped, not rendered**: telemetry is latest-wins, so a
        browser that fell behind catches up in one render rather than replaying what
        it missed.
        """
        item = subscriber.get(timeout=timeout)
        while item is not CLOSED:
            try:
                item = subscriber.get_nowait()
            except queue.Empty:
                break
        return item

    def close(self) -> None:
        """End every open stream, and any opened after this. The table is emptied so
        no later frame can push a stream's `CLOSED` out of its queue."""
        with self._lock:
            self._closed = True
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, CLOSED)


#: Seconds between refreshes on a stream with no frame to send: an event re-rendered
#: from a fresh snapshot, so what ages between frames -- the time since the last
#: reward, *wl-works sees*, `age` -- moves on the page (Ruling 12, 2026-09-27). Also
#: housekeeping: a browser that went away is found at the next write rather than never.
KEEPALIVE_S = 15.0
#: The reconnection delay the page's `EventSource` is told, in milliseconds --
#: housekeeping, not a measurement of this system.
RETRY_MS = 3000
#: Socket timeout for every request -- wl-preproc's `_REQUEST_TIMEOUT_S`, for its
#: reason: a request that never finishes must not park a thread for good.
#: Housekeeping, not a measurement of this system.
REQUEST_TIMEOUT_S = 30.0

#: Each bundled font by the exact path the page asks for it at (`web.FONTS`). A request
#: is looked up here, never joined onto a directory, so there is no path to traverse.
_FONTS = {f"/fonts/{font.file}": font for font in _web.FONTS}
_ROUTES = frozenset({"/", "/events", "/health", "/commands", *_FONTS})
_UNAUTHORIZED = {"error": "unauthorized"}
#: What a request whose `Host` does not name this console is answered (P4d-2b spec
#: §5.3): a JSON 421 and no page. It names no host, echoing nothing it was sent.
_MISDIRECTED = {
    "error": "misdirected request",
    "said": (
        "this console answers only to its own names: loopback, this box's host names "
        "and addresses, and names given with --allow-host"
    ),
}
#: Fixed bodies, keyed on the status alone and echoing nothing a caller sent
#: (wl-preproc's `_SEND_ERROR_BODIES`).
_ERRORS = {
    400: {"error": "bad request"},
    404: {"error": "not found"},
    405: {"error": "method not allowed"},
    414: {"error": "request line too long"},
    431: {"error": "request header fields too large"},
    505: {"error": "http version not supported"},
}
_FALLBACK = {"error": "request rejected"}


def on_box(host: str) -> bool:
    """Whether a peer is this machine: loopback in either family, or an IPv4 loopback
    mapped into IPv6. Anything that does not parse is the LAN."""
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


#: The names loopback goes by in a `Host` header (P4d-2b spec §2, §5.3).
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def host_name(header: str | None) -> str | None:
    """The name a `Host` header gives, lowercased and without its port, or `None`
    when there is none or it does not parse: `127.0.0.1:8080` is `127.0.0.1`,
    `[::1]:8080` is `::1`, `Box.local` is `box.local`. An unbracketed IPv6
    address is not a `Host` (RFC 9110 §7.2 brackets it) and names nothing here."""
    if not header or not header.isascii():
        return None
    value = header.strip().lower()
    if value.startswith("["):
        name, bracket, rest = value[1:].partition("]")
        if not bracket or not name:
            return None
        if rest and not (rest.startswith(":") and rest[1:].isdecimal()):
            return None
        return name
    name, colon, port = value.rpartition(":")
    if not colon:
        return value or None
    if not port.isdecimal() or not name or ":" in name:
        return None
    return name


def names_loopback(name: str | None) -> bool:
    """Whether a `Host` name is this machine by loopback (spec §2's second check):
    `localhost`, or an address in 127.0.0.0/8 or `::1`."""
    if name is None:
        return False
    return name == "localhost" or on_box(name)


def box_names(allowed: tuple[str, ...] = ()) -> frozenset[str]:
    """Every name a request's `Host` may give for this console (P4d-2b spec §5.3):
    loopback, this box's host name and fully qualified name, the addresses those
    resolve to, and `allowed` -- `--allow-host`, for a name the box is reached by
    that it does not know itself by. Lowercased.

    Read once, when `wlx serve` starts. A lookup that fails adds nothing and is not
    an error: loopback and `--allow-host` still work, and the refusal a LAN viewer
    then gets names the flag that fixes it."""
    names = set(LOOPBACK_NAMES)
    for name in (socket.gethostname(), socket.getfqdn()):
        if name:
            names.add(name.lower())
    for name in sorted(names - LOOPBACK_NAMES):
        try:
            found = socket.getaddrinfo(name, None)
        except OSError:
            continue
        names.update(info[4][0].split("%", 1)[0].lower() for info in found)
    names.update(name.strip().lower() for name in allowed if name.strip())
    return frozenset(names)


def event(payload: dict) -> bytes:
    """One server-sent event named `frame`. `json.dumps` escapes every newline and
    control character, so the payload is one `data:` line whatever telemetry held."""
    return b"event: frame\ndata: " + json.dumps(payload).encode("utf-8") + b"\n\n"


def _csp(nonce: str) -> str:
    """The page's Content-Security-Policy: its one script by nonce, inline styles (the
    bar widths), its bundled fonts and the event stream from this origin, and nothing
    else -- no request leaves the box from this page. Defense beneath `web._e`, not
    instead of it."""
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
        f"font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
        f"frame-ancestors 'none'"
    )


# --- writes from the box (P4d-2b b2a, spec §5.3) ---------------------------------------

#: The largest body `POST /commands` reads, in bytes. One command is a few hundred;
#: a longer body is refused before it is read. Housekeeping, not a measurement.
BODY_LIMIT = 4096
#: The longest name a person may give at the box's prompt (spec §5.2).
NAME_LIMIT = 64
#: The largest mark number `wlx serve` hands a browser: 2**53 - 1, JavaScript's
#: `Number.MAX_SAFE_INTEGER`, the largest whole number a browser's JSON carries
#: exactly -- the page sends the number back with the note, and a number it had
#: rounded would join nothing. Within the signal's eight bytes (`link.MARK_LIMIT`).
MARK_ID_LIMIT = 2**53 - 1
#: How many marks' instants `wlx serve` keeps for the notes that follow them. A mark
#: whose note comes after 256 later marks, or after a restart, is recorded with its
#: pressed and received instants unknown, never guessed.
MARKS_REMEMBERED = 256
#: How many commands may wait for the command thread, and marks for the mark thread,
#: before `POST /commands` answers *busy* (spec §5.3). Housekeeping, not a
#: measurement: a person's clicks, debounced, do not fill them; a flood does.
COMMAND_QUEUE_DEPTH = 4
MARK_QUEUE_DEPTH = 8
#: How long an outbox thread waits for work before it looks again at whether to
#: stop, so `Server.close` returns promptly. A responsiveness choice.
OUTBOX_POLL_S = 0.25

#: What the page is told when the rig has a command (spec §5.3): *sent* means `taskd`
#: acknowledged receipt. Whether it was applied or refused is the feed's to show.
SENT = (
    "sent: the rig has it and acts on it at its next trial boundary; the changes feed "
    "shows what it did"
)
#: What the page is told when the queue is full (spec §5.3).
BUSY = (
    503,
    {
        "status": "busy",
        "said": (
            "busy: wlx serve is still sending earlier commands, so this one was not "
            "sent; try again"
        ),
    },
)


class BadCommand(ValueError):
    """A `POST /commands` body that is not a command this console sends. The message
    is the sentence the page shows; nothing was queued."""


@dataclass(frozen=True, slots=True)
class MarkSignal:
    """M pressed at the box: send the mark's signal now, ahead of every command (spec
    §5.3). `pressed_at` is the browser's clock, `None` if it did not say."""

    by: str
    pressed_at: float | None


@dataclass(frozen=True, slots=True)
class MarkNote:
    """The note typed after M -- empty after Esc -- for mark `mark`: sent to the rig as
    a `link.Mark` command, with the instants `wlx serve` kept for that mark."""

    mark: int
    note: str
    by: str


#: The fields each kind of command takes besides `kind` and `by`. A schedule takes
#: exactly one of `at`, `trials` or `ml`, checked in `parse_command`.
_SHAPES = {
    "set": frozenset({"name", "value"}),
    "stop": frozenset(),
    "pause": frozenset(),
    "resume": frozenset(),
    "cancel": frozenset(),
    "schedule": frozenset({"at", "trials", "ml"}),
    "mark": frozenset({"pressed_at"}),
    "note": frozenset({"mark", "note"}),
}
_SCHEDULES = {"at": "clock", "trials": "trials", "ml": "fluid"}


def _person(by: object) -> str:
    """The actor a box command is recorded under: the name the page asked for, as
    `NAME (box, unverified)` (spec §2, S9a §6: a forgeable name is worse than none,
    because it is believed, so it says it is unverified)."""
    if (
        not isinstance(by, str)
        or not by.strip()
        or len(by.strip()) > NAME_LIMIT
        or not by.strip().isprintable()
    ):
        raise BadCommand(
            f"every command records who sent it (S9a §6): give a name of 1 to "
            f"{NAME_LIMIT} printable characters"
        )
    return f"{by.strip()} (box, unverified)"


def parse_command(data: object):
    """One `POST /commands` body -- a JSON object with a `kind` and the person's
    name, `by` -- as what `Server.dispatch` sends: a `link` command, a `MarkSignal`
    or a `MarkNote`. **Validated before anything is queued** (spec §5.3), with the
    wire's own rules where the wire has one (`link._setting` for a value, M8;
    `link.check_schedule` for a schedule), so the page hears the sentence at once
    and the rig never sees what it would refuse on type. Raises `BadCommand`.

    A field a kind does not take is refused, not ignored: a page that sent one has a
    bug a person should see."""
    if not isinstance(data, dict):
        raise BadCommand("a command is one JSON object")
    kind = data.get("kind")
    if kind not in _SHAPES:
        raise BadCommand(f"{kind!r} is not a command this console sends")
    by = _person(data.get("by"))
    extra = set(data) - {"kind", "by"} - _SHAPES[kind]
    if extra:
        raise BadCommand(f"a {kind} command takes no {', '.join(sorted(extra))}")
    if kind == "set":
        name = data.get("name")
        if not isinstance(name, str) or not name or len(name) > _link.TEXT_LIMIT:
            raise BadCommand("a setting names its parameter")
        try:
            value = _link._setting(data.get("value"), name, by)
        except _link.CommandRefused as refused:
            raise BadCommand(refused.why) from refused
        return _link.SetParameter(name=name, value=value, by=by)
    if kind == "schedule":
        given = [key for key in _SCHEDULES if key in data]
        if len(given) != 1:
            raise BadCommand("a scheduled stop takes exactly one of at, trials or ml")
        stop, value = _SCHEDULES[given[0]], data[given[0]]
        why = _link.check_schedule(stop, value)
        if why is not None:
            raise BadCommand(why)
        return _link.ScheduleStop(kind=stop, value=value, by=by)
    if kind == "mark":
        pressed = data.get("pressed_at")
        if pressed is not None and (
            isinstance(pressed, bool)
            or not isinstance(pressed, (int, float))
            or not math.isfinite(pressed)
        ):
            raise BadCommand("a mark's pressed_at is the browser's clock, in seconds")
        return MarkSignal(by=by, pressed_at=None if pressed is None else float(pressed))
    if kind == "note":
        number, note = data.get("mark"), data.get("note")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= MARK_ID_LIMIT
        ):
            raise BadCommand("a note names the mark it is for")
        if not isinstance(note, str) or len(note) > _link.NOTE_LIMIT:
            raise BadCommand(f"a note is text of at most {_link.NOTE_LIMIT} characters")
        return MarkNote(mark=number, note=note, by=by)
    return {
        "stop": _link.Stop,
        "pause": _link.Pause,
        "resume": _link.Resume,
        "cancel": _link.CancelScheduledStop,
    }[kind](by=by)


def not_delivered(why: str) -> tuple[int, dict]:
    """The answer for a command or a mark that did not reach the rig (spec §5.3)."""
    said = why if why.startswith("not delivered") else f"not delivered: {why}"
    return 504, {"status": "not_delivered", "said": said}


@dataclass
class _Job:
    """One piece of work for an `Outbox`'s thread, and the answer it leaves."""

    work: Callable[[object], tuple[int, dict]]
    answer: tuple[int, dict] | None = None
    done: threading.Event = field(default_factory=threading.Event)


class Outbox:
    """A bounded queue and the one thread that owns a sender (spec §2: each ZMQ socket
    has one owning thread). `wlx serve` has two: the command thread, whose sender is a
    `link.ZmqCommands`, and the mark thread, whose sender is a `link.ZmqMarks`.

    **The sender is built on the thread**, by `build`, and closed there, so no other
    thread ever touches its socket. `submit` puts one job on the queue -- or answers
    *busy* at once when the queue is full (spec §5.3) -- and waits for its answer.
    **Every job is answered**: by its work; by `not_delivered` when the work raised,
    or the sender could not be built; or, when the thread stops, by *not delivered:
    wlx serve is closing* -- so no HTTP handler waits forever. `stop` is the
    `Server`'s own stop event, so whatever stops the server stops this thread.
    """

    def __init__(
        self,
        name: str,
        build: Callable[[], object],
        depth: int,
        stop: threading.Event,
    ) -> None:
        self._build = build
        self._queue: queue.Queue = queue.Queue(maxsize=depth)
        self._stop = stop
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def submit(self, work: Callable[[object], tuple[int, dict]]) -> tuple[int, dict]:
        if self._stop.is_set():
            return not_delivered("wlx serve is closing")
        job = _Job(work)
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            return BUSY
        while not job.done.wait(OUTBOX_POLL_S):
            if not self.thread.is_alive():
                # Queued after the thread answered its last job and left: nobody
                # will answer this one, so it is answered here.
                return not_delivered("wlx serve is closing")
        return job.answer

    def _run(self) -> None:
        sender, broken = None, None
        try:
            sender = self._build()
        except Exception as exc:  # noqa: BLE001 -- said to every job, never hidden
            broken = _link._describe(exc)
        try:
            while not self._stop.is_set():
                try:
                    job = self._queue.get(timeout=OUTBOX_POLL_S)
                except queue.Empty:
                    continue
                self._answer(job, sender, broken)
        finally:
            if sender is not None:
                sender.close()
            while True:
                try:
                    job = self._queue.get_nowait()
                except queue.Empty:
                    break
                job.answer = not_delivered("wlx serve is closing")
                job.done.set()

    def _answer(self, job: _Job, sender: object, broken: str | None) -> None:
        try:
            job.answer = (
                not_delivered(f"wlx serve could not reach the rig ({broken})")
                if broken is not None
                else job.work(sender)
            )
        except Exception as exc:  # noqa: BLE001 -- answered, never hidden
            job.answer = not_delivered(_link._describe(exc))
        finally:
            job.done.set()


def _delivered(command) -> Callable[[object], tuple[int, dict]]:
    """The command thread's work for one command: deliver it and say so, or say why
    not (spec §5.3)."""

    def work(commands) -> tuple[int, dict]:
        try:
            commands.deliver(command)
        except _link.NotDelivered as exc:
            return not_delivered(str(exc))
        return 200, {"status": "sent", "said": SENT}

    return work


def make_handler(
    hub: Hub,
    *,
    token: str,
    stale_after_s: float,
    keepalive_s: float = KEEPALIVE_S,
    hosts: frozenset[str] = LOOPBACK_NAMES,
    dispatch: Callable[[object], tuple[int, dict]] | None = None,
) -> type[BaseHTTPRequestHandler]:
    """A handler class closing over `hub` and the token, built the way wl-preproc's
    `make_handler` is and for its reason: `BaseHTTPRequestHandler` handles the whole
    request inside `__init__`, so all it needs must already be class attributes.

    Refuses an empty or non-ASCII token before building anything: `hmac.compare_digest`
    cannot compare a non-ASCII `str`, and a handler built from one would refuse every
    request, the correct one included (wl-preproc, review round 2's Minor 7).

    **P4d-2b b2a.** `hosts` is every name a request's `Host` may give (`box_names`);
    anything else is a JSON 421. `dispatch` sends a parsed command and says what
    became of it (`Server.dispatch`); a handler given none answers every command
    *not delivered*.
    """
    if not token or not token.isascii():
        raise ValueError(
            "the /health bearer token must be non-empty ASCII: hmac.compare_digest "
            "cannot compare anything else, and a handler built from one would refuse "
            "every request, the correct one included"
        )

    class ConsoleHandler(BaseHTTPRequestHandler):
        _hub = hub
        _token = token
        _stale_after_s = stale_after_s
        _keepalive_s = keepalive_s
        _hosts = hosts
        # A function stored on a class becomes a method; `staticmethod` keeps it the
        # plain callable it was given.
        _dispatch = None if dispatch is None else staticmethod(dispatch)
        # No interpreter version in any `Server` header (wl-preproc's Important 5).
        server_version = ""
        sys_version = ""
        timeout = REQUEST_TIMEOUT_S

        def _authorized(self) -> bool:
            """`Authorization: Bearer <token>`, the scheme matched case-insensitively
            (RFC 7235 §2.1), the token by `hmac.compare_digest` on UTF-8 bytes --
            wl-preproc's `_authorized`. Missing, malformed and wrong take one path."""
            value = self.headers.get("Authorization")
            if value is None:
                return False
            scheme, _, candidate = value.partition(" ")
            if scheme.lower() != "bearer" or not candidate:
                return False
            return hmac.compare_digest(
                candidate.encode("utf-8"), self._token.encode("utf-8")
            )

        def _security_headers(self, *, cache: str) -> None:
            """The two headers every response carries, `/events` included -- written
            here once so a header added later cannot land in `_write`'s responses
            and stay missing from the streamed one (F3)."""
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")

        def _write(
            self,
            status: int,
            body: bytes,
            content_type: str,
            headers: tuple = (),
            cache: str = "no-store",
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers(cache=cache)
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            self._write(status, json.dumps(payload).encode("utf-8"), "application/json")

        def _host_ok(self) -> bool:
            """Whether this request's `Host` names this console (spec §2, §5.3)."""
            return host_name(self.headers.get("Host")) in self._hosts

        def may_write(self) -> bool:
            """Spec §2's first two checks -- a loopback peer, and a `Host` naming
            loopback -- which are what a page's controls are greyed by. `POST
            /commands` adds the other two, `Origin` and `Content-Type`."""
            return on_box(self.client_address[0]) and names_loopback(
                host_name(self.headers.get("Host"))
            )

        def _from_the_box(self) -> bool:
            """All four of spec §2's checks on a write: a loopback peer; `Host` naming
            loopback (against DNS rebinding); `Origin` being the page this console
            serves on that host (against a cross-site post from another page open
            in the box's browser); and `Content-Type: application/json`, which makes
            a browser ask a preflight this server never approves."""
            host = self.headers.get("Host") or ""
            origin = self.headers.get("Origin") or ""
            content = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            return (
                self.may_write()
                and origin.lower() == f"http://{host}".lower()
                and content.lower() == "application/json"
            )

        def send_error(self, code, message=None, explain=None) -> None:
            """Every error the stdlib raises on its own, as JSON and never its HTML
            page (wl-preproc's `send_error`, read 2026-09-26). `message` and `explain`
            are discarded: the stdlib formats the caller's own bytes into them.

            **An unknown method is 405 on a known path and 404 elsewhere**, where
            wl-preproc answers 401: every one of its paths needs the token, and here
            only `GET /health` does -- the pages are open to the LAN (spec §2).
            """
            if code == 501:
                code = 405 if getattr(self, "path", None) in _ROUTES else 404
            self._send_json(code, _ERRORS.get(code, _FALLBACK))

        def _refuse_method(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            code = 405 if self.path in _ROUTES else 404
            self._send_json(code, _ERRORS[code])

        # Every verb a client commonly sends besides GET and POST. An `OPTIONS`
        # preflight is one of them: refused, so a cross-site page is never let to
        # post JSON (spec §2's fourth check).
        do_PUT = _refuse_method
        do_DELETE = _refuse_method
        do_PATCH = _refuse_method
        do_OPTIONS = _refuse_method
        do_HEAD = _refuse_method
        do_TRACE = _refuse_method

        def do_POST(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            if self.path != "/commands":
                self._refuse_method()
                return
            self._command()

        def _command(self) -> None:
            """`POST /commands` (spec §5.3): one JSON command, from the box, checked
            and validated before anything is queued, then sent and answered *sent*,
            *not delivered* or *busy*."""
            if not self._from_the_box():
                self._send_json(
                    403, {"status": "refused", "said": _web.CONTROLS_AT_THE_BOX}
                )
                return
            length = self.headers.get("Content-Length") or ""
            if not length.isascii() or not length.isdecimal():
                self._send_json(
                    400, {"status": "refused", "said": "a command needs a Content-Length"}
                )
                return
            if int(length) > BODY_LIMIT:
                self._send_json(
                    413,
                    {"status": "refused", "said": f"a command is at most {BODY_LIMIT} bytes"},
                )
                return
            try:
                data = json.loads(self.rfile.read(int(length)).decode("utf-8"))
                request = parse_command(data)
            except (UnicodeDecodeError, ValueError) as exc:
                # `BadCommand` is a `ValueError`, and so is `json`'s own error.
                said = str(exc) if isinstance(exc, BadCommand) else "a command is one JSON object"
                self._send_json(400, {"status": "refused", "said": f"not sent: {said}"})
                return
            if self._dispatch is None:
                code, answer = not_delivered("this console has no command path")
            else:
                code, answer = self._dispatch(request)
            self._send_json(code, answer)

        def do_GET(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            if self.path == "/":
                self._page()
            elif self.path == "/events":
                self._events()
            elif self.path == "/health":
                if not self._authorized():
                    self._send_json(401, _UNAUTHORIZED)
                    return
                self._health()
            elif self.path in _FONTS:
                self._font(_FONTS[self.path])
            else:
                # 405 for a known path that takes another method -- `/commands`,
                # since b2a -- and 404 for anything else.
                self._refuse_method()

        def _font(self, font) -> None:
            """A bundled font (PI, 2026-09-26: "bundle the fonts"). Cached a day: the
            files change only with the package."""
            self._write(
                200, _web.font_bytes(font), "font/woff2", cache="max-age=86400"
            )

        def _page(self) -> None:
            can_write = self.may_write()
            latest, view = self._hub.snapshot(
                on_box=on_box(self.client_address[0]),
                stale_after_s=self._stale_after_s,
                can_write=can_write,
            )
            nonce = secrets.token_urlsafe(16)
            body = _web.page(
                _web.fragments(latest, view),
                stale_after_s=self._stale_after_s,
                nonce=nonce,
                can_write=can_write,
            )
            self._write(
                200,
                body.encode("utf-8"),
                "text/html; charset=utf-8",
                (("Content-Security-Policy", _csp(nonce)),),
            )

        def _health(self) -> None:
            """`health.response` from one snapshot, the refusal included (Ruling 11,
            2026-09-27): a console refusing every frame is `degraded`, never `ok`."""
            latest, view = self._hub.snapshot(
                on_box=False, stale_after_s=self._stale_after_s
            )
            self._send_json(
                200,
                _health.response(
                    latest,
                    frame_age_s=view.frame_age_s,
                    stale_after_s=view.stale_after_s,
                    rejected=view.rejected,
                    endpoint=view.endpoint,
                ),
            )

        def _events(self) -> None:
            """One browser's stream (spec §4.3): a full render on connect, then an
            event per frame it keeps up with, and a refresh each `keepalive_s`
            without one, until the hub closes or the browser goes away.

            **A quiet interval re-renders, it does not send a comment** (Ruling 12,
            2026-09-27). The page's panes age between frames -- the time since the
            last reward adds the seconds this process has held the frame, and
            *wl-works sees* turns `degraded` when the frame goes stale -- and a
            comment moved neither, so a stalled stream kept `ok · Last frame 0 s
            ago` on the page while `GET /health` said `degraded`. The refresh is
            `_send_frame` like any other event: only what changed, with `live` and
            `age`, and possibly no fragment at all.

            `take` is only ever used as a wake-up and to notice `CLOSED` -- never as
            the frame that gets rendered (F2, below `_send_frame`)."""
            box = on_box(self.client_address[0])
            can_write = self.may_write()
            subscriber = self._hub.subscribe(on_box=box)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self._security_headers(cache="no-store")
                self.end_headers()
                self.wfile.write(f"retry: {RETRY_MS}\n\n".encode("ascii"))
                sent: dict[str, str] = {}
                self._send_frame(box, can_write, sent)
                while True:
                    try:
                        item = self._hub.take(subscriber, timeout=self._keepalive_s)
                    except queue.Empty:
                        self._send_frame(box, can_write, sent)
                        continue
                    if item is CLOSED:
                        return
                    self._send_frame(box, can_write, sent)
            except OSError:
                # A broken pipe, a reset, or a write that timed out: the browser went
                # away. There is nobody to tell; `finally` forgets it.
                return
            finally:
                self._hub.unsubscribe(subscriber)

        def _send_frame(self, box: bool, can_write: bool, sent: dict) -> None:
            """One event: the fragments that differ from what this browser holds --
            all of them on connect -- whether more frames are due (`live`), which is
            when the page's stale timer runs, and `age`, the seconds this process
            has held the latest frame on its steady clock, `None` before any.

            **The page's stale timer runs from `age`** (Ruling 12, 2026-09-27): its
            baseline is the event's arrival less `age`, so a page that connects
            onto an old frame, or is woken by a refusal, never restarts the clock
            the way resetting it on arrival did.

            **Frame and view come from the same `snapshot()` call** (F2, security
            review fix round 1). `_events`'s `take` only wakes this up; rendering the
            frame `take` handed back beside a `view` read a moment later could pair
            an older frame with a newer frame's age, understating the time since the
            last reward by one inter-frame interval -- the direction that hides a
            working, unpaid animal. Telemetry is latest-wins, so reading both from
            one snapshot is always safe: whatever is newest when this runs is what
            is sent, never a stale value carried in from `take`.
            """
            latest, view = self._hub.snapshot(
                on_box=box, stale_after_s=self._stale_after_s, can_write=can_write
            )
            parts = _web.fragments(latest, view)
            changed = {key: html for key, html in parts.items() if sent.get(key) != html}
            sent.update(changed)
            self.wfile.write(
                event(
                    {
                        "frags": changed,
                        "live": _health.expects_frames(latest),
                        "age": view.frame_age_s,
                    }
                )
            )

    return ConsoleHandler


#: How long the telemetry thread's receive waits before it looks again at whether to
#: stop, so `Server.close` returns promptly. A responsiveness choice, not a
#: measurement; `wlx console` keeps `ZmqConsole`'s 5 s.
RECEIVE_TIMEOUT_S = 0.5


class Server:
    """`wlx serve`'s whole process, as an object a test can start and stop.

    Binds the HTTP port on construction -- so `address` is known, and a port in use
    is refused before anything else happens -- and starts its threads in `start`: the
    telemetry thread (`_listen`), the command thread and, given a mark endpoint, the
    mark thread (each an `Outbox`, P4d-2b b2a), and the HTTP server's loop.

    `mark` is the session's mark endpoint, `--link`'s third; `None` without one, and
    then a mark is answered *not delivered* and the page greys its control.
    `allow_hosts` is `--allow-host`. `reply_timeout_s` and `connect_timeout_s` are
    the command sender's (`link.ZmqCommands`), passed so a test need not wait them.
    """

    def __init__(
        self,
        *,
        sub: str,
        req: str,
        http: tuple[str, int],
        token: str,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        keepalive_s: float = KEEPALIVE_S,
        receive_timeout_s: float = RECEIVE_TIMEOUT_S,
        mark: str | None = None,
        allow_hosts: tuple[str, ...] = (),
        reply_timeout_s: float = _link.REPLY_TIMEOUT_S,
        connect_timeout_s: float = _link.CONNECT_TIMEOUT_S,
    ) -> None:
        self.hub = Hub(endpoint=sub, marks=mark is not None)
        self._sub = sub
        self._req = req
        self._receive_timeout_s = receive_timeout_s
        self._stop = threading.Event()
        #: The command thread (spec §5.3): it alone owns the REQ socket.
        self._commands = Outbox(
            "wlx-serve-commands",
            lambda: _link.ZmqCommands(req, reply_timeout_s, connect_timeout_s),
            COMMAND_QUEUE_DEPTH,
            self._stop,
        )
        #: The mark thread: it alone owns the PUSH socket to the mark endpoint, so a
        #: mark's signal never waits behind a command (spec §5.3). `None` without a
        #: mark endpoint.
        self._marks = (
            None
            if mark is None
            else Outbox(
                "wlx-serve-marks",
                lambda: _link.ZmqMarks(mark, connect_timeout_s),
                MARK_QUEUE_DEPTH,
                self._stop,
            )
        )
        #: Each signalled mark's `(pressed_at, received_at)`, by number, for the note
        #: that follows it; the newest `MARKS_REMEMBERED`. HTTP threads share it.
        self._marked: OrderedDict = OrderedDict()
        self._marked_lock = threading.Lock()
        #: Set by `_listen` when the telemetry thread cannot go on -- a transport
        #: failure, never a bad frame (fix round 1, I1). `_wait` blocks on this
        #: alongside the operator's Ctrl-C, and `run` reads `_fatal_reason` once it
        #: wakes to say why, then closes and returns non-zero rather than serving on
        #: with a telemetry thread that is quietly gone.
        self._fatal = threading.Event()
        self._fatal_reason: str | None = None
        #: The full traceback behind `_fatal_reason` (fix round 2, M-c): the one
        #: line is what an operator needs; this is what the next session diagnosing
        #: an unfamiliar hub bug needs, and `_fatal_reason` alone was not going to
        #: be enough for that.
        self._fatal_traceback: str | None = None
        self._http = ThreadingHTTPServer(
            http,
            make_handler(
                self.hub,
                token=token,
                stale_after_s=stale_after_s,
                keepalive_s=keepalive_s,
                hosts=box_names(allow_hosts),
                dispatch=self.dispatch,
            ),
        )
        self._web = threading.Thread(
            target=self._http.serve_forever, name="wlx-serve-http", daemon=True
        )
        self._telemetry = threading.Thread(
            target=self._listen, name="wlx-serve-telemetry", daemon=True
        )
        self._started = False
        self._closed = False

    @property
    def address(self) -> tuple[str, int]:
        """`(host, port)` as bound: the port the OS chose when `http` asked for 0."""
        host, port = self._http.server_address[:2]
        return host, port

    def start(self) -> None:
        self._started = True
        self._telemetry.start()
        self._commands.start()
        if self._marks is not None:
            self._marks.start()
        self._web.start()

    def dispatch(self, request) -> tuple[int, dict]:
        """Send one parsed command (`parse_command`) and say what became of it.

        A `MarkSignal` goes to the mark thread, ahead of every command; the rest go
        to the command thread's queue, a `MarkNote` as the `link.Mark` it is, with
        the instants this process kept for that mark."""
        if isinstance(request, MarkSignal):
            return self._signal(request)
        if isinstance(request, MarkNote):
            pressed_at, received_at = self._recall(request.mark)
            request = _link.Mark(
                mark=request.mark,
                note=request.note,
                by=request.by,
                pressed_at=pressed_at,
                received_at=received_at,
            )
        return self._commands.submit(_delivered(request))

    def _signal(self, request: MarkSignal) -> tuple[int, dict]:
        """A mark's signal (spec §5.1, §5.3): a fresh number, the instant this
        process received it -- its own host clock, one of the record's three -- and
        the signal sent on the mark thread. Answered *signaled* with the number the
        page sends back with the note."""
        if self._marks is None:
            return not_delivered(_web.NO_MARK_ENDPOINT)
        number = secrets.randbelow(MARK_ID_LIMIT) + 1
        received_at = time.time()

        def work(marks) -> tuple[int, dict]:
            try:
                marks.signal(number)
            except _link.NotDelivered as exc:
                return not_delivered(str(exc))
            self._remember(number, request.pressed_at, received_at)
            return 200, {
                "status": "signaled",
                "mark": number,
                "said": "mark sent to the rig: type a note and press Enter, or Esc",
            }

        return self._marks.submit(work)

    def _remember(self, number: int, pressed_at: float | None, received_at: float) -> None:
        with self._marked_lock:
            self._marked[number] = (pressed_at, received_at)
            while len(self._marked) > MARKS_REMEMBERED:
                self._marked.popitem(last=False)

    def _recall(self, number: int) -> tuple[float | None, float | None]:
        with self._marked_lock:
            return self._marked.pop(number, (None, None))

    def _listen(self) -> None:
        """The telemetry thread: the one `ZmqConsole`, created, read and closed here,
        so its sockets have one owning thread (spec §2).

        **A frame this console cannot use is said, never shown and never fatal**
        (Review Focus 1): one that does not decode, and one of another schema --
        `link.decode` raises `link.FrameError` for both (`link.SchemaMismatch` is
        one), checked first thing every schema, before any other field is touched
        (fix round 1, I3). Either goes to `Hub.reject`, the page says why, and the
        last good frame stays.

        **A transport failure ends this thread, not silently** (fix round 1, I1).
        Before this fix, `ZmqConsole`'s own construction and every call in this loop
        sat outside any `try`, so a `--link` endpoint that parsed but that ZeroMQ
        itself refused (a bad port, a wildcard host connected-to rather than bound,
        an unknown scheme) raised out of this daemon thread, which `threading`
        prints to stderr and then quietly drops -- `wlx serve` kept its HTTP server
        up, `/health` kept saying `ok` on the last frame it ever got, forever. Now
        anything that is not a `TimeoutError` (an idle receive; expected, not an
        error) or a `FrameError` (a bad frame; said, not fatal) escapes this `with`
        block, is caught once below, and sets `_fatal` so `run` can end the process
        instead of serving on with a dead telemetry thread. Nothing here retries in
        a loop with no sleep: a fatal exception ends the thread on the first one,
        it does not spin.
        """
        try:
            # Read-only (P4d-2b b2a): no REQ socket here. Commands are the command
            # thread's, so each socket has one owning thread (spec §2).
            with _link.ZmqConsole(
                self._sub, None, receive_timeout_s=self._receive_timeout_s
            ) as console:
                while not self._stop.is_set():
                    try:
                        frame = console.receive()
                    except TimeoutError:
                        continue
                    except _link.FrameError as exc:
                        self.hub.reject(str(exc))
                        continue
                    self.hub.offer(frame)
        except Exception as exc:  # noqa: BLE001 -- ends the process, never hidden (I1)
            if self._stop.is_set():
                return  # asked to stop; a transport error on the way out is not new
            # fix round 3, M1: `_link._describe` (fix round 2, M-e) prints the
            # exception type alone when its own message is empty, instead of the
            # dangling "RuntimeError: " this line used to build inline -- the same
            # bug M-e fixed for `link.FrameError`, reachable here too.
            self._fatal_reason = _link._describe(exc)
            # fix round 2, M-c: the one-line reason is what an operator reads; the
            # full traceback is what diagnoses a hub bug nobody anticipated.
            self._fatal_traceback = traceback.format_exc()
            self._fatal.set()

    def close(self) -> None:
        """Stop serving, end every open stream, and close the `ZmqConsole`. Safe to
        call twice, and before `start`.

        **Fix round 2, N2.** `_http.shutdown()` blocks forever for a `serve_forever`
        loop that never ran at all (the stdlib's own docs on `shutdown()`), and
        `Thread.join()` raises `RuntimeError` on a thread that was never `.start()`-ed
        rather than returning -- both were reachable if a Ctrl-C landed inside
        `Server.start()` itself, between `self._telemetry.start()` and
        `self._web.start()`: `self._started` is set *before* either thread starts, so
        it cannot tell "both threads are up" from "one of them never got the chance."
        `Thread.ident` can: it stays `None` until a thread has actually begun running,
        and `.start()` itself blocks until `.ident` is set, so checking it here
        correctly separates "never started" from "already running" for the
        `shutdown()` deadlock and the `join()` `RuntimeError` above.

        **Fix round 3, M3: this does not cover every interleaving, and saying so
        plainly matters more than sounding finished.** A Ctrl-C landing during
        `Thread.start()`'s own internal startup wait (POSIX: `Thread._started.wait()`,
        called from inside `.start()` itself, a narrow window) can still leave that
        thread alive briefly after this method returns. That is not a hang -- the
        thread is a daemon and its own loop checks `_stop`, which is set above -- but
        it may print an exception traceback (for instance, from a socket this method
        has already closed underneath it) before it notices and exits.
        """
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self.hub.close()
        web_started = self._web.ident is not None
        telemetry_started = self._telemetry.ident is not None
        if web_started:
            self._http.shutdown()
        self._http.server_close()
        if web_started:
            self._web.join(timeout=5)
        if telemetry_started:
            self._telemetry.join(timeout=5)
        # The outboxes stop on `_stop` too, answering anything still queued, and
        # close their sockets on their own threads (P4d-2b b2a).
        for outbox in (self._commands, self._marks):
            if outbox is not None and outbox.thread.ident is not None:
                outbox.thread.join(timeout=5)


def _git_checkout_containing(path: Path) -> Path | None:
    """The nearest ancestor of `path` (`path` itself included) with a `.git` entry --
    file or directory -- or `None` if none of them has one.

    **Fix round 1, M1.** `_REPO_ROOT`, computed from `Path(__file__)`, is somewhere
    under `site-packages` for a non-editable install of `wl_expcontroller` -- and
    `read_token`'s "inside this repository" refusal, checked with
    `resolved.is_relative_to(_REPO_ROOT)`, then guards nothing there: no token file
    written into a real git checkout is ever *inside* a `site-packages` directory. Its
    own test computed `_REPO_ROOT` the identical way, so it agreed with the check
    regardless of whether that path was a real repository, which is why the test kept
    passing while the check itself guarded nothing.

    Walking up from the token path instead finds any git checkout wherever it
    actually is -- **a file counts, not only a directory**, because a worktree's
    `.git` is a file naming the real one elsewhere (this repository's own worktrees,
    this session's own worktree among them, are exactly this case)."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def read_token(path: Path) -> str:
    """The `/health` bearer token: from a file, never from the repository (spec §2).

    Refused, each with a sentence and before anything binds: a file inside this
    checkout -- one `git add` from public -- a file that cannot be read, an empty one
    (there is no default token), one holding a non-ASCII character, which
    `hmac.compare_digest` cannot compare, so every request would fail, the correct
    one included (wl-preproc refuses the same), and one holding a newline or other
    control character no HTTP header can carry (fix round 1, M2). The whitespace
    around it -- the newline an editor leaves -- is not part of the token.
    """
    resolved = path.expanduser().resolve()
    checkout = _git_checkout_containing(resolved)
    if checkout is not None:
        raise SystemExit(
            f"refused: the /health token file {str(path)!r} is inside this repository "
            f"({checkout}), one `git add` from being published; keep it outside any "
            f"checkout (P4d-2b spec §2: a token file, never the repository)"
        )
    try:
        token = resolved.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(
            f"refused: cannot read the /health token file {str(path)!r}: {exc}"
        ) from exc
    if not token:
        raise SystemExit(
            f"refused: the /health token file {str(path)!r} is empty; there is no "
            f"default token, so wl-works could never authenticate -- write one token "
            f"on one line"
        )
    if not token.isascii():
        raise SystemExit(
            "refused: the /health token contains a non-ASCII character; "
            "hmac.compare_digest cannot compare it, which would make every request "
            "fail authentication, the correct one included"
        )
    if not token.isprintable():
        raise SystemExit(
            "refused: the /health token cannot be carried in a header: it contains "
            "a newline or other control character (a token file with a second line, "
            "for example); write it on one line with nothing else in the file"
        )
    return token


def parse_link(text: str) -> tuple[str, str, str | None]:
    """`PUB,REP` or `PUB,REP,MARK`, exactly as `wlx run --link` takes it (P4d-2b b2a
    added the third): telemetry is read from the first, commands are sent to the
    second, and mark signals to the third, which is `None` when not given.

    **Fix round 1, I1(a).** This used to check only that each half contained
    `"://"` somewhere, which is what its docstring already claimed to do and did
    not: `"tcp://127.0.0.1:5571, tcp://127.0.0.1:5572"` (a space after the comma,
    the security review's own reproduction) passed it, and the leading space rode
    along into `ZmqConsole.connect()` inside the telemetry thread, where ZeroMQ
    refused it -- a traceback on a daemon thread instead of a sentence here.
    `tcp://127.0.0.1:abc`, `tcp://127.0.0.1` (no port), `tcp://*:5571` and
    `foo://...` all passed the same way.

    Now each endpoint is stripped and required to be `tcp://HOST:PORT`, PORT a
    decimal number from 1 to 65535, HOST anything but empty or `*` -- a console
    *connects*; it never binds, so a wildcard bind address is never what it means
    (`link.ZmqConsole`'s own docstring makes the same distinction from
    `link.ZmqLink`). Only `tcp://` -- neither `wlx run --link` nor `wlx console
    --sub/--req` (`cli.py`) restrict a `--link`/`--sub`/`--req` value to a
    transport at all before handing it to `ZmqLink`/`ZmqConsole`, and nothing in
    this codebase's tests exercises `ipc://`/`inproc://` through either of those
    end to end (only `link._binds_beyond_this_machine`'s own classification test
    does, and only on the *bind* side); accepting them here without an end-to-end
    check anywhere would be inventing support this parser cannot verify.
    """
    parts = [part.strip() for part in text.split(",")]
    if len(parts) not in (2, 3) or not all(parts):
        raise SystemExit(
            f"refused: --link expects PUB,REP or PUB,REP,MARK -- two or three "
            f"comma-separated endpoints such as tcp://127.0.0.1:5571, as given to "
            f"`wlx run --link` -- got {text!r}"
        )
    for endpoint in parts:
        _refuse_unless_tcp_endpoint(endpoint, text)
    return parts[0], parts[1], parts[2] if len(parts) == 3 else None


def _refuse_unless_tcp_endpoint(endpoint: str, whole: str) -> None:
    """One `--link` endpoint, already stripped: `tcp://HOST:PORT` or a `SystemExit`
    naming exactly what is wrong with it, before anything connects (fix round 1,
    I1(a))."""
    scheme, sep, rest = endpoint.partition("://")
    if not sep or scheme != "tcp":
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r} (in {whole!r}) must be "
            f"tcp://HOST:PORT"
        )
    host, colon, port = rest.rpartition(":")
    if not colon or not host:
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r} is missing a port -- expected "
            f"tcp://HOST:PORT"
        )
    if host == "*":
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r} names a wildcard host; a "
            f"console connects, it never binds, so give the box's own address "
            f"or name instead"
        )
    # M3's `isascii()`-and-`isdecimal()` fix applies here for the same reason:
    # `str.isdigit()` accepts characters `int()` does not.
    if not port.isascii() or not port.isdecimal() or not (1 <= int(port) <= 65535):
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r}'s port must be a decimal "
            f"number from 1 to 65535"
        )


def parse_http(text: str) -> tuple[str, int]:
    """`HOST:PORT`, IPv4 or a name: the stdlib server here binds IPv4 only."""
    host, sep, port = text.rpartition(":")
    if (
        not sep
        or not host
        or ":" in host
        or host.startswith("[")
        # fix round 1, M3: `str.isdigit()` accepts characters `int()` does not --
        # `"²"` (superscript two) is a digit by Unicode's reckoning and raised
        # a bare `ValueError` traceback out of `int(port)` below instead of this
        # sentence. `isascii() and isdecimal()` is the pair `int()` itself agrees
        # with.
        or not port.isascii()
        or not port.isdecimal()
        or int(port) > 65535
    ):
        raise SystemExit(
            f"refused: --http expects HOST:PORT with an IPv4 address or a name -- "
            f"127.0.0.1:8080 for this box only, 0.0.0.0:8080 to let the lab network "
            f"read the page -- got {text!r}"
        )
    return host, int(port)


def _wait(server: Server) -> None:
    """Block until the operator interrupts, or the telemetry thread cannot go on
    (fix round 1, I1). Its own function so a test can stand in for the person
    pressing Ctrl-C, and returns on its own once `server._fatal` is set -- which
    is the only way this can return without `KeyboardInterrupt`, so `run` tells
    the two apart by whether an exception came out of this call.

    **Fix round 2, M-b; fix round 3, M2 (its docstring contradicted itself, and
    this rewrite is the fix for that too -- CLAUDE.md: no fabrication).** On
    POSIX, a real SIGINT ends a serving `wlx serve` with 130:
    `test_wlx_serve_exits_130_on_a_real_sigint` starts one as its own process, with
    this function unpatched, fetches its page and sends the signal. That is the only
    test that does; every other Ctrl-C test raises `KeyboardInterrupt` through a
    monkeypatch, which shows `run`'s handling and not that the signal arrives.
    **Windows is UNVERIFIED here**: a blocking `Event.wait()` with no timeout is
    documented elsewhere as not reliably interruptible by Ctrl-C on that platform
    (a wait with no timeout never returns control to the interpreter for a signal
    to be noticed there), but nothing in this repository has measured it. Waiting
    in a loop with a short timeout -- checked and abandoned once a second, never
    once forever -- is the portable form regardless of which platform's claim
    turns out to hold, at the cost of a wake-up this process is not otherwise
    doing anything with. Not a measurement of this system either way.
    """
    while not server._fatal.wait(1.0):
        pass


def run(args) -> int:
    """`wlx serve`: check everything, bind, serve until interrupted (spec §2).

    Every refusal is a sentence, and all of them happen before anything binds.
    Ctrl-C ends it with 130, as `wlx console` does, and says what it did not stop.
    A telemetry thread that cannot go on ends it too (fix round 1, I1): `_wait`
    returns on its own rather than raising, so it is distinguished from Ctrl-C by
    `server._fatal` being set, and this returns 1 with a sentence naming why --
    the session on the box is unaffected either way; this is the console's own
    process, and closing it commands nothing.
    """
    token = read_token(args.health_token_file)
    sub, req, mark = parse_link(args.link)
    host, port = parse_http(args.http)
    stale_after = (
        DEFAULT_STALE_AFTER_S if args.stale_after is None else args.stale_after
    )
    if not math.isfinite(stale_after) or stale_after <= 0:
        raise SystemExit(
            f"refused: --stale-after must be a positive number of seconds, got "
            f"{args.stale_after!r}"
        )
    try:
        server = Server(
            sub=sub,
            req=req,
            http=(host, port),
            token=token,
            stale_after_s=stale_after,
            mark=mark,
            allow_hosts=tuple(args.allow_host),
        )
    except OSError as exc:
        raise SystemExit(f"refused: cannot serve on {host}:{port}: {exc}") from exc
    # fix round 1, M5: `server.start()` and the startup print used to sit after this
    # `try`, so a Ctrl-C landing between construction and `_wait` escaped as a bare
    # `KeyboardInterrupt` traceback instead of the 130 this function promises
    # everywhere else. Both are inside it now.
    try:
        server.start()
        bound_host, bound_port = server.address
        print(
            f"wlx serve: the console is at http://{bound_host}:{bound_port}/, reading "
            f"{sub}, sending commands to {req} and marks to "
            f"{mark or 'nowhere (no MARK endpoint given)'}; controls work only from "
            f"this box's own browser at http://127.0.0.1:{bound_port}/; GET /health "
            f"needs the bearer token",
            flush=True,
        )
        _wait(server)
    except KeyboardInterrupt:
        print(
            "serve: interrupted -- the session keeps running on the box; nothing here "
            "stops it",
            file=sys.stderr,
        )
        return 130
    finally:
        server.close()
    if server._fatal.is_set():
        print(
            f"wlx serve: the telemetry thread stopped: {server._fatal_reason}; "
            f"the session is unaffected",
            file=sys.stderr,
        )
        # fix round 2, M-c: the traceback behind the one-line reason, for whoever
        # has to diagnose a hub bug the sentence alone cannot explain.
        if server._fatal_traceback:
            print(server._fatal_traceback, file=sys.stderr)
        return 1
    return 0
