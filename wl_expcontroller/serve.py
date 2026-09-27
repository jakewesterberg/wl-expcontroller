"""`wlx serve` -- the browser console's process (P4d-2b slice b1).

Spec: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §1-§4.

**Its own process, beside `taskd` and never inside it** (S9a §7: the hot loop never
serves a request). It holds one `link.ZmqConsole`, keeps the latest frame, and serves
three things over the stdlib `ThreadingHTTPServer` -- the stack wl-preproc's responder
already runs, so no new dependency:

- `GET /` -- the page, every pane rendered in Python (`web.py`).
- `GET /events` -- server-sent events: one full render on connect, then the fragments
  that changed, once per frame this browser keeps up with.
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
§3); the queue depth, the rate window's sampling, the keepalive and the receive
timeout are housekeeping. None is a measurement of this system.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import queue
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler

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
        steady: Callable[[], float] = _welfare.steady_seconds,
    ) -> None:
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


#: Seconds between comment lines on a stream with no frame to send. Housekeeping: a
#: browser that went away is found at the next write rather than never.
KEEPALIVE_S = 15.0
#: The reconnection delay the page's `EventSource` is told, in milliseconds.
RETRY_MS = 3000
#: Socket timeout for every request -- wl-preproc's `_REQUEST_TIMEOUT_S`, for its
#: reason: a request that never finishes must not park a thread for good.
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
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
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
            latest, view = self._hub.snapshot(
                on_box=False, stale_after_s=self._stale_after_s
            )
            self._send_json(
                200,
                _health.response(
                    latest,
                    frame_age_s=view.frame_age_s,
                    stale_after_s=self._stale_after_s,
                ),
            )

        def _events(self) -> None:
            """One browser's stream (spec §4.3): a full render on connect, then an
            event per frame it keeps up with, until the hub closes or the browser
            goes away."""
            box = on_box(self.client_address[0])
            subscriber = self._hub.subscribe(on_box=box)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(f"retry: {RETRY_MS}\n\n".encode("ascii"))
                sent: dict[str, str] = {}
                latest, _ = self._hub.snapshot(
                    on_box=box, stale_after_s=self._stale_after_s
                )
                self._send_frame(latest, box, sent)
                while True:
                    try:
                        item = self._hub.take(subscriber, timeout=self._keepalive_s)
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        continue
                    if item is CLOSED:
                        return
                    self._send_frame(item, box, sent)
            except OSError:
                # A broken pipe, a reset, or a write that timed out: the browser went
                # away. There is nobody to tell; `finally` forgets it.
                return
            finally:
                self._hub.unsubscribe(subscriber)

        def _send_frame(self, latest, box: bool, sent: dict) -> None:
            """One event: the fragments that differ from what this browser holds --
            all of them on connect -- and whether more frames are due, which is when
            the page's stale timer runs."""
            _, view = self._hub.snapshot(on_box=box, stale_after_s=self._stale_after_s)
            parts = _web.fragments(latest, view)
            changed = {key: html for key, html in parts.items() if sent.get(key) != html}
            sent.update(changed)
            self.wfile.write(
                event({"frags": changed, "live": _health.expects_frames(latest)})
            )

    return ConsoleHandler
