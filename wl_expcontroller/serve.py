"""`wlx serve` -- the browser console's process (P4d-2b slice b1).

Spec: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §1-§4.

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

Everything else is 404 or 405, as JSON, never the stdlib's HTML page. **b1 has no
`POST`**: nothing on the page writes; writes from the box are slice b2's.

**Restarting it changes nothing in `taskd`** (spec §2): it only ever reads the PUB
socket, and telemetry is lossy by design (S9a §9).

**Threads, and what each owns.** The telemetry thread (`Server._listen`) owns the
`ZmqConsole` -- both of its sockets, created, read and closed there -- so each ZMQ
socket has one owning thread. b1 sends no command, so the REQ socket is connected and
never used; slice b2 moves it to a command thread of its own. Each browser's
`/events` runs on the HTTP server's thread for that connection, reading its own
bounded queue from the `Hub`.

**No timing claim is made here.** `DEFAULT_STALE_AFTER_S` is a display choice (spec
§3); `QUEUE_DEPTH`, `RATE_SAMPLE_S`, `KEEPALIVE_S`, `REQUEST_TIMEOUT_S` and
`RETRY_MS` are housekeeping, not a measurement of this system.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import queue
import secrets
import sys
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable
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
    ) -> None:
        #: The PUB endpoint the telemetry thread reads, handed to every `View` so a
        #: page with no frame names where it is listening (m4). No default: a hub
        #: that did not know it would have the page guess.
        self._endpoint = endpoint
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
        self, *, on_box: bool, stale_after_s: float
    ) -> tuple[_link.Telemetry | None, _web.View]:
        """The latest frame and the `View` a render of it needs, read together. The
        frame's age is on `steady` alone (ledger Ruling 1)."""
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
_ROUTES = frozenset({"/", "/events", "/health", *_FONTS})
_UNAUTHORIZED = {"error": "unauthorized"}
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


def make_handler(
    hub: Hub,
    *,
    token: str,
    stale_after_s: float,
    keepalive_s: float = KEEPALIVE_S,
) -> type[BaseHTTPRequestHandler]:
    """A handler class closing over `hub` and the token, built the way wl-preproc's
    `make_handler` is and for its reason: `BaseHTTPRequestHandler` handles the whole
    request inside `__init__`, so all it needs must already be class attributes.

    Refuses an empty or non-ASCII token before building anything: `hmac.compare_digest`
    cannot compare a non-ASCII `str`, and a handler built from one would refuse every
    request, the correct one included (wl-preproc, review round 2's Minor 7).
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
            code = 405 if self.path in _ROUTES else 404
            self._send_json(code, _ERRORS[code])

        # Every verb a client commonly sends besides GET. b1 takes no POST at all:
        # nothing on the page writes (spec §4.2).
        do_POST = _refuse_method
        do_PUT = _refuse_method
        do_DELETE = _refuse_method
        do_PATCH = _refuse_method
        do_OPTIONS = _refuse_method
        do_HEAD = _refuse_method
        do_TRACE = _refuse_method

        def do_GET(self) -> None:
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
                self._send_json(404, _ERRORS[404])

        def _font(self, font) -> None:
            """A bundled font (PI, 2026-09-26: "bundle the fonts"). Cached a day: the
            files change only with the package."""
            self._write(
                200, _web.font_bytes(font), "font/woff2", cache="max-age=86400"
            )

        def _page(self) -> None:
            latest, view = self._hub.snapshot(
                on_box=on_box(self.client_address[0]),
                stale_after_s=self._stale_after_s,
            )
            nonce = secrets.token_urlsafe(16)
            body = _web.page(
                _web.fragments(latest, view),
                stale_after_s=self._stale_after_s,
                nonce=nonce,
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
            subscriber = self._hub.subscribe(on_box=box)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self._security_headers(cache="no-store")
                self.end_headers()
                self.wfile.write(f"retry: {RETRY_MS}\n\n".encode("ascii"))
                sent: dict[str, str] = {}
                self._send_frame(box, sent)
                while True:
                    try:
                        item = self._hub.take(subscriber, timeout=self._keepalive_s)
                    except queue.Empty:
                        self._send_frame(box, sent)
                        continue
                    if item is CLOSED:
                        return
                    self._send_frame(box, sent)
            except OSError:
                # A broken pipe, a reset, or a write that timed out: the browser went
                # away. There is nobody to tell; `finally` forgets it.
                return
            finally:
                self._hub.unsubscribe(subscriber)

        def _send_frame(self, box: bool, sent: dict) -> None:
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
                on_box=box, stale_after_s=self._stale_after_s
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
    is refused before anything else happens -- and starts two threads in `start`: the
    telemetry thread (`_listen`) and the HTTP server's loop.
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
    ) -> None:
        self.hub = Hub(endpoint=sub)
        self._sub = sub
        self._req = req
        self._receive_timeout_s = receive_timeout_s
        self._stop = threading.Event()
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
        self._web.start()

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
            with _link.ZmqConsole(
                self._sub, self._req, receive_timeout_s=self._receive_timeout_s
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


def parse_link(text: str) -> tuple[str, str]:
    """`PUB,REP`, exactly as `wlx run --link` takes it. This process reads the first
    and, in b1, never sends to the second.

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
    if len(parts) != 2 or not all(parts):
        raise SystemExit(
            f"refused: --link expects PUB,REP -- exactly two comma-separated endpoints "
            f"such as tcp://127.0.0.1:5571, as given to `wlx run --link` -- got {text!r}"
        )
    for endpoint in parts:
        _refuse_unless_tcp_endpoint(endpoint, text)
    return parts[0], parts[1]


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
    POSIX, `Event.wait()` is interrupted by Ctrl-C the same way `time.sleep` is --
    this codebase's own tests exercise exactly that path on this platform.
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
    sub, req = parse_link(args.link)
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
            sub=sub, req=req, http=(host, port), token=token, stale_after_s=stale_after
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
            f"{sub}; GET /health needs the bearer token",
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
