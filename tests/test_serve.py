"""`wlx serve` (P4d-2b slice b1): the hub, the HTTP surface, and the whole process.

Sim first: the end-to-end test runs a real `wlx run --link` in the simulator and a
real `wlx serve` on loopback, and reads the page's event stream the way a browser
would. Every socket here has a client timeout, so a broken server fails a test in
seconds rather than hanging the suite (and the mutation sweep) for 300.
"""

from __future__ import annotations

import http.client
import json
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from _frames import ENDPOINT, frame
from _rig import DIRECT, PATH as RIG_FILE
# Autouse: every `ZmqLink`/`ZmqConsole` built here, `wlx serve`'s telemetry thread's and
# `wlx run --link`'s included, has its context destroyed at teardown without `close()`.
from _zmq_release import _every_zmq_context_released  # noqa: F401
from wl_xcon import serve
from wl_xcon.cli import main
from wl_xcon.link import (
    SCHEMA,
    CancelScheduledStop,
    ManualReward,
    Mark,
    NotDelivered,
    Pause,
    Resume,
    ScheduleStop,
    SetParameter,
    Stop,
    Unacknowledged,
    ZmqConsole,
    ZmqLink,
)
from wl_xcon.serve import (
    BUSY,
    CLOSED,
    COMMAND_QUEUE_DEPTH,
    LOOPBACK_NAMES,
    MARK_ID_LIMIT,
    MARKS_REMEMBERED,
    QUEUE_DEPTH,
    REWARD_SENT,
    REWARD_UNKNOWN,
    BadCommand,
    Hub,
    MarkNote,
    MarkSignal,
    Outbox,
    Server,
    box_names,
    host_name,
    make_handler,
    names_loopback,
    on_box,
    parse_command,
)
from wl_xcon.web import CONTROLS_AT_THE_BOX, NO_MARK_ENDPOINT
from wl_xcon.web import FONTS, FRAGMENT_IDS, font_bytes

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts.protocol import HealthResponse
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}); the "
            f"/health served over HTTP is checked against their HealthResponse"
        ) from exc
    HealthResponse = None

_contract = pytest.mark.skipif(
    HealthResponse is None, reason="wl-preproc checkout not beside this repo"
)

TOKEN = "t0ken-for-tests"


class _Clock:
    """A clock a test sets by hand."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _hub(steady: _Clock | None = None) -> Hub:
    return Hub(steady=steady or _Clock(0.0), endpoint=ENDPOINT)


@pytest.fixture(autouse=True)
def _bounded_real_wait(monkeypatch):
    """Fix round 2, N1. `serve._wait` blocks on `server._fatal.wait()` with no
    timeout (M-b's fix round 2 makes this a 1 s poll loop rather than one
    unbounded call, but the loop itself still never gives up on its own). A test
    whose mutant removes whatever was supposed to end that wait -- `_fatal.set()`
    itself, or a refusal that was supposed to keep `run` from ever reaching a real
    `Server` at all -- reaches this loop for real and then never returns. Under
    the mutation gate that shows up as a 300 s `timed out`, the harness noticing
    rather than a test (CLAUDE.md; the exact thing Ruling 10 (P4d-2a) exists to
    prevent for a session, restated here for a wait).

    Autouse, so every test in this file that reaches the real `_wait` through
    `run`/`main` -- rather than through its own `monkeypatch.setattr(serve,
    "_wait", ...)`, which simply overrides this one again -- gets a bounded
    stand-in instead: 10 s, then `pytest.fail`, never a hang. Tests that need the
    *real* function's own blocking behavior (`test_serving_waits_for_the_operator`)
    take this fixture themselves to get it back, captured here before the patch.
    """
    real_wait = serve._wait

    def _bounded(server) -> None:
        if not server._fatal.wait(10):
            pytest.fail(
                "wlx serve reached its wait and nothing ended it within 10s "
                "(fix round 2, N1: a hanging wait must fail a test, not the suite)"
            )

    monkeypatch.setattr(serve, "_wait", _bounded)
    yield real_wait


def _teardown_without_close(server: Server) -> None:
    """Stop `server` the way `Server.close` should, but never by calling `close`
    itself (fix round 3, I). The mutation harness blanks every function named
    `close` in `serve.py` at once, `Hub.close` and `Server.close` alike -- proven
    by the reviewer with the harness's own `_neuter_source`
    (`tools/mutate.py`): a `Server` a test built through `run()` for
    `test_wlx_serve_returns_130_for_a_ctrl_c_between_construction_and_wait`
    reported `1 passed in 0.16s` and then never let the interpreter exit, because
    nothing had told its telemetry thread to stop and the still-open `zmq.Context`
    blocked destroying itself at shutdown around it.

    Bounded and safe to call more than once (a test that already closed its own
    `Server` gets this again at teardown; every step here is idempotent or a
    no-op on an already-stopped object). `self._http.shutdown()` and each
    thread's own `.join()` are skipped when that thread's `Thread.ident` is
    `None` -- fix round 2, N2's reasoning, restated here rather than duplicated
    with `_started`, which cannot tell "never started" from "already up."
    """
    server._stop.set()
    server.hub.close()
    web_started = server._web.ident is not None
    telemetry_started = server._telemetry.ident is not None
    if web_started:
        server._http.shutdown()
    server._http.server_close()
    if web_started:
        server._web.join(timeout=5)
    if telemetry_started:
        server._telemetry.join(timeout=5)
    # P4d-2b b2a: the command and mark threads stop on `_stop` as well; joined here so
    # their sockets are closed on their own threads before `_every_zmq_context_released`
    # destroys the contexts.
    for outbox in (server._commands, server._marks):
        if outbox is not None and outbox.thread.ident is not None:
            outbox.thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _torn_down_servers(monkeypatch, _every_zmq_context_released):
    """Fix round 3, I. Wraps `Server.__init__` so every `Server` this file builds
    -- whether a test constructs one directly (`server_cleanup`'s old job) or
    `serve.run`/`main` builds one internally (`test_wlx_serve_returns_130_for_a_
    ctrl_c_between_construction_and_wait` and the N2 test, neither of which ever
    called `server_cleanup`) -- is torn down at teardown through
    `_teardown_without_close`, never through `Server.close`.

    Autouse, so a new test cannot forget it the way the two tests above did.
    `server_cleanup` (below) is kept as a pass-through for the tests that already
    call it -- fix round 3 merged its teardown into this one rather than running
    both (each step in `_teardown_without_close` is idempotent, but there is no
    reason to call `shutdown()`/`join()` twice from two independent fixtures when
    one suffices).

    It requests `_every_zmq_context_released` (`tests/_zmq_release.py`) so that
    fixture's teardown runs after this one. The telemetry thread is joined before its
    `ZmqConsole`'s context is destroyed, never while a socket is still in use there.
    """
    real_init = Server.__init__
    built: list[Server] = []

    def _record_init(self, *args, **kwargs) -> None:
        real_init(self, *args, **kwargs)
        built.append(self)

    monkeypatch.setattr(Server, "__init__", _record_init)
    yield
    # Every server is torn down even when one teardown raises: a failure here used
    # to leave each later server running, its telemetry thread in a ZMQ receive
    # into interpreter shutdown. The failures are raised together at the end.
    failures = []
    for server in built:
        try:
            _teardown_without_close(server)
        except Exception as exc:  # noqa: BLE001 -- collected and re-raised below
            failures.append(exc)
    if failures:
        raise ExceptionGroup("tearing down a test's wlx serve servers failed", failures)


# --- the hub (Task 9) ------------------------------------------------------------


def test_a_hub_with_no_frame_has_nothing_to_show():
    found, seen = _hub().snapshot(on_box=True, stale_after_s=30.0)

    assert found is None
    assert seen.frame_age_s is None
    assert seen.trials_per_min is None


def test_the_latest_frame_is_kept_with_its_age():
    mono = _Clock(10.0)
    hub = _hub(mono)

    hub.offer(frame(trial_index=3))
    mono.t = 25.0
    found, seen = hub.snapshot(on_box=True, stale_after_s=30.0)

    assert found.trial_index == 3
    assert seen.frame_age_s == 15.0
    assert seen.stale_after_s == 30.0


def test_trials_per_minute_is_trials_over_the_time_between_frames():
    """Spec §4.1: derived here, from `trial_index` and when frames arrived."""
    mono = _Clock(0.0)
    hub = _hub(mono)

    hub.offer(frame(trial_index=0))
    mono.t = 30.0
    hub.offer(frame(trial_index=30))

    assert hub.trials_per_min() == 60.0


def test_one_frame_derives_no_rate():
    hub = _hub()
    hub.offer(frame(trial_index=5))

    assert hub.trials_per_min() is None


def test_the_rate_forgets_frames_older_than_five_minutes():
    """Across all three frames the rate would be 160 trials in 460 s; over the last
    five minutes it is 60 trials in 60 s."""
    mono = _Clock(0.0)
    hub = _hub(mono)

    hub.offer(frame(trial_index=0))
    mono.t = 400.0
    hub.offer(frame(trial_index=100))
    mono.t = 460.0
    hub.offer(frame(trial_index=160))

    assert hub.trials_per_min() == 60.0


def test_a_new_session_restarts_the_rate():
    """A second `wlx run` on the same link is a new session, and a rate across two
    would describe neither."""
    mono = _Clock(0.0)
    hub = _hub(mono)
    hub.offer(frame(session_id="2027-01-14_01", trial_index=0))
    mono.t = 60.0
    hub.offer(frame(session_id="2027-01-14_01", trial_index=60))

    mono.t = 61.0
    hub.offer(frame(session_id="2027-01-14_02", trial_index=0))
    assert hub.trials_per_min() is None

    mono.t = 91.0
    hub.offer(frame(session_id="2027-01-14_02", trial_index=15))
    assert hub.trials_per_min() == 30.0


def test_a_trial_count_that_goes_back_restarts_the_rate():
    mono = _Clock(0.0)
    hub = _hub(mono)
    hub.offer(frame(trial_index=50))
    mono.t = 10.0
    hub.offer(frame(trial_index=3))

    assert hub.trials_per_min() is None


def test_a_fast_publisher_cannot_grow_the_rate_window():
    """A simulator publishes far faster than a rig; the window keeps at most one point
    a second however many frames arrive."""
    mono = _Clock(0.0)
    hub = _hub(mono)

    for n in range(10_000):
        mono.t = n * 0.001
        hub.offer(frame(trial_index=n))

    assert len(hub._points) <= 11
    assert round(hub.trials_per_min()) == 60_000


def test_a_stream_that_falls_behind_keeps_only_the_newest_frames():
    """Review Focus 4: a tab that stops reading never holds up the telemetry thread
    and never grows -- its oldest frames go."""
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)

    for n in range(20):
        hub.offer(frame(trial_index=n))

    kept = [subscriber.get_nowait().trial_index for _ in range(subscriber.qsize())]
    assert kept == list(range(20 - QUEUE_DEPTH, 20))


def test_take_renders_only_the_newest_frame_waiting():
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)
    for n in range(3):
        hub.offer(frame(trial_index=n))

    assert hub.take(subscriber, timeout=1.0).trial_index == 2
    with pytest.raises(queue.Empty):
        hub.take(subscriber, timeout=0.01)


def test_closing_the_hub_ends_every_stream_including_later_ones():
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)
    hub.offer(frame())

    hub.close()
    hub.offer(frame(trial_index=99))

    assert hub.take(subscriber, timeout=1.0) is CLOSED
    assert hub.take(hub.subscribe(on_box=False), timeout=1.0) is CLOSED
    assert hub.viewers() == (0, 0)


def test_viewers_are_counted_by_where_they_are():
    hub = _hub()
    hub.subscribe(on_box=True)
    lan = hub.subscribe(on_box=False)
    hub.subscribe(on_box=False)

    assert hub.viewers() == (1, 2)
    assert hub.snapshot(on_box=True, stale_after_s=30.0)[1].lan_viewers == 2

    hub.unsubscribe(lan)
    assert hub.viewers() == (1, 1)


def test_a_refused_frame_wakes_every_stream_and_a_good_one_clears_it():
    """Review Focus 1, in the hub: a frame that could not be used is said on every
    open page at once, and the last good frame -- here none -- is what is shown."""
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)

    hub.reject("a telemetry frame carried schema 6")

    assert hub.take(subscriber, timeout=1.0) is None
    found, seen = hub.snapshot(on_box=True, stale_after_s=30.0)
    assert found is None
    assert seen.rejected == "a telemetry frame carried schema 6"

    hub.offer(frame())
    assert hub.snapshot(on_box=True, stale_after_s=30.0)[1].rejected is None


def test_a_host_clock_stepped_back_between_two_frames_leaves_the_reward_age_right(
    tmp_path, monkeypatch
):
    """**Ledger Ruling 1 (2026-09-27), the path and not the piece.** A real session on
    its anchored clock, a real reward through its `Rig`, two real frames from
    `Telemetry.of` with the host clock stepped back an hour between them, and the strip
    `wlx serve` renders from its hub. The age is the second frame's `wall_at` less the
    reward's instant -- both on the session's `SessionClock`, which the step cannot
    move -- plus the seconds the hub has held that frame on its own steady clock: 50 s
    and 12 s. Read against the host clock instead, as first planned, it was `0 s`."""
    import time
    from pathlib import Path

    from wl_xcon.cli import _load_bounds
    from wl_xcon.dio import Simulated as Card
    from wl_xcon.link import Telemetry
    from wl_xcon.scheduler import Block, Condition, Scheduler
    from wl_xcon.simulate import Tally
    from wl_xcon.taskd import Session, SessionSpec
    from wl_xcon.web import fragments
    from wl_xcon.welfare import Deployment, Simulated as Pump

    wall = 1_700_000_000.0
    # Every steady clock `welfare.steady_seconds` could read, stubbed to one value, as
    # `tests/test_taskd.py`'s anchored-clock tests do.
    host, steady = [wall], [100.0]
    monkeypatch.setattr(time, "time", lambda: host[0])
    monkeypatch.setattr(time, "monotonic", lambda: steady[0])
    monkeypatch.setattr(time, "clock_gettime", lambda clock: steady[0])
    session = Session(
        SessionSpec(
            task="tasks/fixation_detection.py",
            allocation="tasks/allocation.py",
            root=tmp_path,
            session_id="2027-01-14_09",
            subject="REFERENCE",
            trials=1,
            frame_period=1 / 240,
            seed=1,
            values={},
            bounds=_load_bounds(Path("tasks/twelve_hour_bounds.py")),
            already_delivered_today=0.0,
            deployment=Deployment.RIG_CHAIRED,
            geometry=DIRECT,
        ),
        card=Card(),
        pump=Pump(),
    )
    session.left_cage(at=wall)
    scheduler = Scheduler(
        blocks=[Block(name="session", conditions=[Condition("only", {}, target=1)])],
        seed=0,
    )
    served = _Clock(0.0)
    hub = _hub(served)

    def publish() -> Telemetry:
        published = Telemetry.of(session, Tally(), scheduler, index=0)
        hub.offer(published)
        return published

    host[0], steady[0] = wall + 10.0, 110.0
    session.rig.reward("reward_correct")
    host[0], steady[0] = wall + 30.0, 130.0
    publish()
    # The host clock stepped back an hour, by NTP or by a person: thirty seconds later
    # on every steady clock, 3,570 seconds earlier on the host's.
    host[0], steady[0], served.t = wall + 60.0 - 3_600.0, 160.0, 30.0
    second = publish()
    served.t = 42.0

    strip = fragments(*hub.snapshot(on_box=True, stale_after_s=30.0))["strip"]

    assert second.wall_at == wall + 60.0, "the session's anchored clock took the step"
    assert second.last_reward_at == wall + 10.0
    assert (
        '<span class="lab">Since last reward</span><span class="val">62 s</span>'
        in strip
    )


# --- the HTTP surface (Task 10) ---------------------------------------------------


@contextmanager
def _served(
    hub: Hub,
    *,
    keepalive_s: float = 15.0,
    stale_after_s: float = 30.0,
    hosts: frozenset = LOOPBACK_NAMES,
    dispatch=None,
):
    """The handler on a real loopback socket, with no ZMQ anywhere."""
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(
            hub,
            token=TOKEN,
            stale_after_s=stale_after_s,
            keepalive_s=keepalive_s,
            hosts=hosts,
            dispatch=dispatch,
        ),
    )
    # A short poll, so `shutdown()` returns in a twentieth of a second rather than
    # the stdlib's default half: dozens of tests here each serve and shut down once,
    # and the mutation sweep runs them once per function. Housekeeping.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        hub.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(port: int, method: str, path: str, headers: dict | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def _raw(port: int, data: bytes) -> bytes:
    """Bytes a browser would never send, and everything the server says back."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(data)
        chunks = []
        while chunk := sock.recv(4096):
            chunks.append(chunk)
    return b"".join(chunks)


def _events(response, *, deadline_s: float | None = None):
    """Each `frame` event's payload, as a browser's `EventSource` would dispatch it:
    comments and the `retry:` line are skipped.

    `deadline_s` bounds the whole read on this generator's own clock. The socket's
    10 s timeout alone does not: a server that writes comment lines and never an
    event keeps the socket busy, and this loop would skip them forever -- as it did
    against the `: keepalive` comments Ruling 12 replaced."""
    ends = None if deadline_s is None else time.monotonic() + deadline_s
    name, data = None, None
    while True:
        if ends is not None and time.monotonic() > ends:
            raise AssertionError(f"no frame event within {deadline_s} s")
        line = response.readline()
        if not line:
            return
        line = line.decode("utf-8").rstrip("\n")
        if line == "":
            if name == "frame" and data is not None:
                yield json.loads(data)
            name, data = None, None
        elif line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            data = line[len("data: ") :]


def _read_to_eof(response, *, within_s: float) -> bool:
    """Read `response` to its end. True if the end came within `within_s` on this
    test's own clock. False if the server was still writing when that time ran out.

    The socket's 10 s timeout cannot bound this read alone. A stream that never ends
    but keeps writing, which is what a `Hub.take` that stopped returning `CLOSED`
    produces, has a line ready for every `readline()`, so that timeout never fires.
    Draining it with an unbounded loop hung the whole suite under that mutant instead
    of failing this test (2026-09-27)."""
    ends = time.monotonic() + within_s
    while time.monotonic() < ends:
        if not response.readline():
            return True
    return False


@contextmanager
def _stream(port: int):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", "/events")
    response = connection.getresponse()
    try:
        yield response
    finally:
        response.close()
        connection.close()


def test_the_page_is_served_with_every_pane_and_its_own_nonce():
    hub = _hub()
    hub.offer(frame())
    with _served(hub) as port:
        status, headers, body = _request(port, "GET", "/")

    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    policy = headers["Content-Security-Policy"]
    nonce = policy.split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'<script nonce="{nonce}">'.encode() in body
    assert "default-src 'none'" in policy and "connect-src 'self'" in policy
    assert "font-src 'self'" in policy
    assert b'id="strip"' in body and b"2027-01-14_01" in body
    assert b"http://" not in body and b"https://" not in body


def test_every_bundled_font_is_served_with_its_type():
    """The page's fonts come from this box (PI, 2026-09-26): each face `web.FONTS`
    declares, as `font/woff2`, byte for byte the file the package carries."""
    hub = _hub()
    with _served(hub) as port:
        for font in FONTS:
            status, headers, body = _request(port, "GET", f"/fonts/{font.file}")
            assert status == 200, font.file
            assert headers["Content-Type"] == "font/woff2", font.file
            assert body == font_bytes(font), font.file


def test_a_font_path_that_is_not_a_bundled_name_is_404():
    """Exact names from a fixed table: nothing is joined onto a directory, so a `..`
    has nowhere to go, and a license file or a module beside the fonts is not served."""
    hub = _hub()
    with _served(hub) as port:
        for path in (
            "/fonts/../web.py",
            "/fonts/../../pyproject.toml",
            "/fonts/%2e%2e/web.py",
            "/fonts/ibm-plex-sans/OFL.txt",
            f"/fonts/ibm-plex-sans/{FONTS[0].file}",
            "/fonts/Unknown.woff2",
            f"/fonts/{FONTS[0].file}?v=1",
            "/fonts/",
            "/fonts",
        ):
            assert _request(port, "GET", path)[::2] == (
                404,
                b'{"error": "not found"}',
            ), path
        assert _request(port, "POST", f"/fonts/{FONTS[0].file}")[0] == 405


def test_health_needs_the_token_and_every_failure_looks_the_same():
    """wl-preproc's rule: missing, malformed and wrong are one path to one `401`, so
    which part was wrong cannot be read off the response."""
    hub = _hub()
    with _served(hub) as port:
        answers = {
            _request(port, "GET", "/health", headers)[::2]
            for headers in (
                {},
                {"Authorization": "Bearer wrong"},
                {"Authorization": f"Basic {TOKEN}"},
                {"Authorization": "Bearer"},
                {"Authorization": "Bearer "},
            )
        }

    assert answers == {(401, b'{"error": "unauthorized"}')}


def test_health_answers_the_token_whatever_the_schemes_case():
    hub = _hub()
    hub.offer(frame())
    with _served(hub) as port:
        for scheme in ("Bearer", "bearer"):
            status, headers, body = _request(
                port, "GET", "/health", {"Authorization": f"{scheme} {TOKEN}"}
            )
            assert status == 200, scheme
            assert headers["Content-Type"] == "application/json"
            assert set(json.loads(body)) == {"verdict", "readings", "actions"}


def test_an_unknown_path_is_404_as_json():
    hub = _hub()
    with _served(hub) as port:
        for path in ("/nope", "/favicon.ico", "/health/", "/events/x"):
            assert _request(port, "GET", path)[::2] == (
                404,
                b'{"error": "not found"}',
            ), path


def test_a_known_path_with_the_wrong_method_is_405():
    """`/commands` is a path since b2a and takes `POST` alone; every other path takes
    no `POST` at all."""
    hub = _hub()
    with _served(hub) as port:
        assert _request(port, "POST", "/")[0] == 405
        assert _request(port, "POST", "/events")[0] == 405
        assert _request(port, "PUT", "/health")[0] == 405
        assert _request(port, "DELETE", "/")[0] == 405
        assert _request(port, "GET", "/commands")[0] == 405
        assert _request(port, "OPTIONS", "/commands")[0] == 405
        assert _request(port, "POST", "/nope")[0] == 404


def test_a_method_the_stdlib_does_not_know_gets_json_not_its_html_page():
    hub = _hub()
    with _served(hub) as port:
        known = _raw(port, b"BREW / HTTP/1.0\r\n\r\n")
        unknown = _raw(port, b"BREW /nope HTTP/1.0\r\n\r\n")

    assert known.startswith(b"HTTP/1.0 405")
    assert known.endswith(b'{"error": "method not allowed"}')
    assert unknown.startswith(b"HTTP/1.0 404")
    assert b"<" not in known + unknown


def test_a_method_the_stdlib_does_not_know_with_a_foreign_host_is_421():
    """Fix round 1, Important 3 (security review): an unknown method reaches
    `send_error` directly, bypassing `do_GET`/`do_POST`'s own `Host` check -- so a
    DNS-rebound request answered 405 instead of 421, the one path the other two
    methods already close. A request with no `Host` at all is unaffected -- this
    file's own pin, above, stays 405."""
    hub = _hub()
    with _served(hub) as port:
        foreign = _raw(port, b"BREW / HTTP/1.0\r\nHost: evil.example\r\n\r\n")

    assert foreign.startswith(b"HTTP/1.0 421")
    assert b'"misdirected request"' in foreign
    assert b"evil" not in foreign


def test_a_malformed_request_gets_no_html_and_no_echo():
    hub = _hub()
    with _served(hub) as port:
        answer = _raw(port, b"GARBAGE\r\n\r\n")

    assert b'"bad request"' in answer
    assert b"<" not in answer
    assert b"GARBAGE" not in answer


def test_no_response_names_the_interpreter():
    hub = _hub()
    with _served(hub) as port:
        for path in ("/", "/nope", "/health"):
            server = _request(port, "GET", path)[1].get("Server", "")
            assert "Python" not in server and "BaseHTTP" not in server, path


def test_a_stream_opens_with_a_full_render_then_sends_what_changed():
    """Spec §4.3: one full render on connect, then a fragment per frame -- here, only
    the fragments that differ from what this browser already holds."""
    hub = _hub()
    with _served(hub) as port, _stream(port) as response:
        assert response.getheader("Content-Type") == "text/event-stream"
        events = _events(response)

        first = next(events)
        assert tuple(first["frags"]) == FRAGMENT_IDS
        assert first["live"] is False
        assert 'data-state="none"' in first["frags"]["state"]

        hub.offer(frame(trial_index=5))
        second = next(events)
        assert second["live"] is True
        assert 'data-trial="5"' in second["frags"]["head-id"]

        hub.offer(frame(trial_index=6))
        third = next(events)
        assert 'data-trial="6"' in third["frags"]["head-id"]
        assert "setup" not in third["frags"], "an unchanged pane was sent again"


def test_a_stream_on_the_box_says_so():
    hub = _hub()
    with _served(hub) as port, _stream(port) as response:
        first = next(_events(response))

    assert first["frags"]["presence"].startswith("<b>this box</b>")


def test_a_quiet_stream_is_refreshed_each_keepalive_not_sent_a_comment():
    """Ruling 12 (2026-09-27) replaced Task 10's `: keepalive` comment with an event:
    each keepalive interval re-renders from a fresh snapshot and sends the fragments
    that changed -- none here, since nothing moved -- with `live` and `age`. An event
    with nothing changed is still a write, so a browser that went away is still
    found at the next one."""
    hub = _hub()
    hub.offer(frame())
    with _served(hub, keepalive_s=0.05) as port, _stream(port) as response:
        lines = [response.readline() for _ in range(40)]

    assert b": keepalive\n" not in lines
    payloads = [
        json.loads(line[len(b"data: ") :]) for line in lines if line.startswith(b"data: ")
    ]
    assert len(payloads) >= 10
    assert tuple(payloads[0]["frags"]) == FRAGMENT_IDS
    assert all(p == {"frags": {}, "live": True, "age": 0.0} for p in payloads[1:])


def _since_last_reward(payload: dict) -> str:
    found = re.search(
        r'<span class="lab">Since last reward</span><span class="val">([^<]*)</span>',
        payload["frags"]["strip"],
    )
    assert found, payload["frags"]["strip"]
    return found.group(1)


def _until_sent(events, fragment: str) -> dict:
    """The next payload that carries `fragment`, from at most 200 events -- each a
    keepalive refresh at most `keepalive_s` apart -- never an unbounded wait."""
    for _, payload in zip(range(200), events):
        if fragment in payload["frags"]:
            return payload
    raise AssertionError(f"no refresh carried {fragment!r}")


def test_every_payload_carries_age_and_it_is_null_before_any_frame():
    """Ruling 12: the page's stale timer is based on `age`, so every event carries
    it -- the full render, a refusal's wake-up, a frame's, and a keepalive
    refresh.

    The last batch reads until an `age == 0.0` payload rather than a fixed count:
    keepalives arrive every `keepalive_s` regardless of the test thread, so a stall
    of one interval or more between `reject` and `offer` -- entirely plausible under
    the mutation gate's parallel load -- would otherwise let a backlogged pre-offer
    refresh be the third read and make `payloads[-1]` describe the wrong state."""
    hub = _hub()
    with _served(hub, keepalive_s=0.05) as port, _stream(port) as response:
        events = _events(response, deadline_s=10.0)
        payloads = [next(events) for _ in range(3)]
        hub.reject(REFUSED)
        payloads += [next(events) for _ in range(3)]
        hub.offer(frame())
        for _, payload in zip(range(200), events):
            payloads.append(payload)
            if payload["age"] == 0.0:
                break
        else:
            raise AssertionError("no refresh carried age == 0.0 after the offer")

    assert all("age" in payload for payload in payloads)
    assert payloads[0]["age"] is None
    assert payloads[-1]["age"] == 0.0


def test_a_quiet_stream_whose_frame_goes_stale_is_refreshed_to_degraded():
    """Ruling 12: `_events` rendered only when the hub woke it, so through a stall the
    *wl-works sees* pane kept `ok · Last frame 0 s ago` while `GET /health` said
    `degraded`. A keepalive refresh now re-renders it."""
    steady = _Clock(0.0)
    hub = _hub(steady)
    hub.offer(frame())
    with _served(hub, keepalive_s=0.05, stale_after_s=30.0) as port, _stream(
        port
    ) as response:
        events = _events(response, deadline_s=10.0)
        assert '<span class="pill ok">ok</span>' in next(events)["frags"]["rt-health"]
        steady.t = 45.0
        refreshed = _until_sent(events, "rt-health")

    assert '<span class="pill warn">degraded</span>' in refreshed["frags"]["rt-health"]
    assert "45 s ago" in refreshed["frags"]["rt-health"]
    assert refreshed["age"] == 45.0


def test_a_stream_opened_onto_an_old_frame_is_told_its_age_at_once():
    """Ruling 12: a page that reconnected onto an already-stale stream got a full
    render with no age, so its timer started from the render's arrival -- no stale
    banner for `--stale-after` seconds, and then one that understated N."""
    steady = _Clock(0.0)
    hub = _hub(steady)
    hub.offer(frame())
    steady.t = 100.0
    with _served(hub) as port, _stream(port) as response:
        first = next(_events(response, deadline_s=10.0))

    assert first["age"] >= 100.0
    assert first["live"] is True


def test_the_time_since_the_last_reward_advances_with_no_new_frame():
    """Ledger Ruling 1's "plus the seconds `wlx serve` has held the frame" only
    reaches a live page if the page is re-rendered between frames (Ruling 12):
    `frame()`'s reward is 41.5 s before its instant, then 20 s more pass here."""
    steady = _Clock(0.0)
    hub = _hub(steady)
    hub.offer(frame())
    with _served(hub, keepalive_s=0.05) as port, _stream(port) as response:
        events = _events(response, deadline_s=10.0)
        first = next(events)
        steady.t = 20.0
        later = _until_sent(events, "strip")

    assert _since_last_reward(first) == "41 s"
    assert _since_last_reward(later) == "61 s"


def test_closing_the_hub_ends_an_open_stream():
    hub = _hub()
    with _served(hub, keepalive_s=60.0) as port, _stream(port) as response:
        next(_events(response))
        hub.close()
        tail = [response.readline() for _ in range(5)]

    assert tail[-1] == b"", "the stream stayed open after the hub closed"


def test_a_browser_that_goes_away_is_forgotten():
    """Review Focus 4: a closed tab is noticed at the next write, and its queue goes."""
    hub = _hub()
    with _served(hub) as port:
        with _stream(port) as response:
            next(_events(response))
            assert hub.viewers() == (1, 0)
        for n in range(250):
            hub.offer(frame(trial_index=n))
            if hub.viewers() == (0, 0):
                break
            time.sleep(0.02)

        assert hub.viewers() == (0, 0)


def test_the_box_is_a_loopback_peer_and_nothing_else():
    for host in ("127.0.0.1", "127.8.9.10", "::1", "::ffff:127.0.0.1"):
        assert on_box(host), host
    for host in ("192.168.1.50", "10.0.0.7", "::ffff:10.0.0.7", "not an address", ""):
        assert not on_box(host), host


def test_a_handler_refuses_a_token_it_could_not_compare():
    """wl-preproc's `make_handler` refuses a non-ASCII token for its reason:
    `hmac.compare_digest` cannot compare one, so every request would fail, the
    correct one included."""
    for token in ("", "tök"):
        with pytest.raises(ValueError):
            make_handler(_hub(), token=token, stale_after_s=30.0)


@_contract
def test_health_over_http_is_wl_preprocs_health_response():
    """The body as it crosses the wire -- JSON encoding included -- against their
    model, with markup in the frame."""
    hub = _hub()
    hub.offer(frame(session_id="<b>&", stop_kind="operator", stopped_because="<script>"))
    with _served(hub) as port:
        status, _, body = _request(
            port, "GET", "/health", {"Authorization": f"Bearer {TOKEN}"}
        )

    assert status == 200
    assert HealthResponse.model_validate_json(body).verdict == "ok"


# --- a refused frame (Ruling 11, 2026-09-27) ---------------------------------------

#: What `Server._listen` hands `Hub.reject` for a schema-6 `wlx run` beside this
#: `wlx serve` -- the case the final review probed, where every frame is refused.
REFUSED = (
    f"a telemetry frame carried schema 6, and this console reads schema {SCHEMA}, so "
    f"it is not shown"
)


def _health_body(port: int) -> dict:
    status, _, body = _request(
        port, "GET", "/health", {"Authorization": f"Bearer {TOKEN}"}
    )
    assert status == 200
    return json.loads(body)


def _featured(body: dict) -> list[tuple[str, str]]:
    return [(r["key"], r["value"]) for r in body["readings"] if r["featured"]]


def test_a_refusal_alone_makes_health_degraded_with_the_refusal_featured():
    """Ruling 11: every frame refused used to leave `/health` answering `ok`, "none
    attached", with no reading that mentioned the refusal -- wl-works saw a healthy
    host that could not see its session. Driven by `Hub.reject` alone."""
    hub = _hub()
    hub.reject(REFUSED)
    with _served(hub) as port:
        body = _health_body(port)

    assert body["verdict"] == "degraded"
    assert _featured(body) == [("refused", REFUSED)]


def test_a_refusal_alone_shows_the_same_on_the_page_and_no_waiting_banner():
    """Ruling 11: the page's *wl-works sees* pane said a green `ok`, and a *Waiting*
    banner under the red *Refused* one asserted that no session was publishing on
    the link -- false, since one was, in a schema this console cannot read."""
    hub = _hub()
    hub.reject(REFUSED)
    with _served(hub) as port, _stream(port) as response:
        frags = next(_events(response))["frags"]

    assert '<span class="pill warn">degraded</span>' in frags["rt-health"]
    assert re.search(
        r'<span class="f">◆</span><span class="l">Refused</span>'
        r'<span class="v">[^<]*schema 6',
        frags["rt-health"],
    )
    assert frags["rt-health"].count("◆") == 1
    assert '<span class="tag">Refused</span>' in frags["banners"]
    assert "Waiting" not in frags["banners"]
    assert "no telemetry yet" not in frags["banners"]


def test_an_accepted_frame_after_a_refusal_returns_health_to_ok():
    """Ruling 11: `degraded` lasts until the next frame this console can read --
    `Hub.offer` clears the refusal -- whether a good frame was held before it or
    not."""
    hub = _hub()
    with _served(hub) as port:
        hub.reject(REFUSED)
        assert _health_body(port)["verdict"] == "degraded"

        hub.offer(frame())
        body = _health_body(port)
        assert body["verdict"] == "ok"
        assert "refused" not in {r["key"] for r in body["readings"]}

        hub.reject(REFUSED)
        body = _health_body(port)
        assert body["verdict"] == "degraded"
        assert _featured(body) == [("refused", REFUSED)]

        hub.offer(frame(trial_index=41))
        assert _health_body(port)["verdict"] == "ok"


def test_health_with_no_frame_names_the_endpoint_its_hub_reads():
    """m4, over the wire: the session reading names the PUB endpoint rather than
    implying that nothing publishes."""
    hub = Hub(steady=_Clock(0.0), endpoint="tcp://10.0.0.7:5571")
    with _served(hub) as port:
        body = _health_body(port)

    session = next(r for r in body["readings"] if r["key"] == "session")
    assert session["value"] == (
        "none attached · no frame has arrived on tcp://10.0.0.7:5571"
    )


def test_a_servers_hub_names_the_sub_endpoint_it_reads():
    """m4: the endpoint the page and `/health` name is the one `--link` gave the
    telemetry thread, not a guess."""
    server = Server(
        sub="tcp://127.0.0.1:5571",
        req="tcp://127.0.0.1:5572",
        http=("127.0.0.1", 0),
        token=TOKEN,
    )

    view = server.hub.snapshot(on_box=True, stale_after_s=30.0)[1]
    assert view.endpoint == "tcp://127.0.0.1:5571"


# --- fix round 1: the security review's four findings ----------------------------


class _StaleTakeHub(Hub):
    """F2: `take` answers every wake-up with a fixed stale frame, no matter which
    frame actually woke it or what the hub holds by the time the caller reads it --
    modeling the race a real telemetry thread and a real HTTP thread can hit: a
    newer frame lands between `take` returning and the next `snapshot` read. Pins
    that a streamed event is rendered from one `snapshot()` call, frame and view
    together, never `take`'s frame paired with a separately read (and by then
    newer) view."""

    def __init__(self, stale_frame) -> None:
        super().__init__(steady=_Clock(0.0), endpoint=ENDPOINT)
        self._stale_frame = stale_frame

    def take(self, subscriber, timeout):
        item = super().take(subscriber, timeout)
        return item if item is CLOSED else self._stale_frame


def test_a_streamed_frame_is_rendered_with_the_view_its_own_snapshot_gives():
    """F2, the direction that hides an unpaid animal: if the fragments came from the
    frame `take` woke the stream with, but the age came from a `snapshot()` read
    after a newer frame had already landed, the newer frame's short age would be
    stamped onto the older frame's content -- or, as pinned here, the wrong frame's
    content would reach the page at all. Rendering both from one `snapshot()` call
    closes it: whatever is newest when `_send_frame` reads the hub is what is sent,
    never a stale `take` value."""
    hub = _StaleTakeHub(frame(trial_index=5))
    with _served(hub) as port, _stream(port) as response:
        events = _events(response)
        next(events)  # the full render on connect, before any frame

        hub.offer(frame(trial_index=6))
        second = next(events)

    assert 'data-trial="6"' in second["frags"]["head-id"], (
        "the event was rendered from take()'s stale frame (5) instead of the frame "
        "snapshot() already shows (6)"
    )


def test_the_page_gets_a_fresh_nonce_each_request():
    """F1: the existing page test only checks that the header and the body agree on
    one nonce; a handler that hard-coded a constant nonce would still pass it."""
    hub = _hub()
    with _served(hub) as port:
        _, first_headers, _ = _request(port, "GET", "/")
        _, second_headers, _ = _request(port, "GET", "/")

    def nonce_of(headers):
        policy = headers["Content-Security-Policy"]
        return policy.split("'nonce-", 1)[1].split("'", 1)[0]

    assert nonce_of(first_headers) != nonce_of(second_headers)


def test_cache_control_matches_what_each_response_promises():
    hub = _hub()
    hub.offer(frame())
    with _served(hub) as port:
        assert _request(port, "GET", "/")[1]["Cache-Control"] == "no-store"
        assert (
            _request(port, "GET", "/health", {"Authorization": f"Bearer {TOKEN}"})[1][
                "Cache-Control"
            ]
            == "no-store"
        )
        assert (
            _request(port, "GET", f"/fonts/{FONTS[0].file}")[1]["Cache-Control"]
            == "max-age=86400"
        )
        with _stream(port) as response:
            assert response.getheader("Cache-Control") == "no-store"


def test_nosniff_is_on_every_kind_of_response():
    hub = _hub()
    hub.offer(frame())
    with _served(hub) as port:
        status, headers, _ = _request(port, "GET", "/")
        assert status == 200 and headers["X-Content-Type-Options"] == "nosniff"

        status, headers, _ = _request(port, "GET", "/health")
        assert status == 401 and headers["X-Content-Type-Options"] == "nosniff"

        status, headers, _ = _request(port, "GET", "/nope")
        assert status == 404 and headers["X-Content-Type-Options"] == "nosniff"

        with _stream(port) as response:
            assert response.getheader("X-Content-Type-Options") == "nosniff"


def test_the_streams_first_line_states_its_retry_delay():
    """The `_events` helper skips the `retry:` line along with every comment, so it
    is asserted here on its own."""
    hub = _hub()
    with _served(hub) as port, _stream(port) as response:
        first_line = response.readline()

    assert first_line == b"retry: 3000\n"


def test_401_headers_are_identical_across_every_kind_of_bad_credential():
    """Not only the same status and body (already pinned): the same headers, once
    `Date` -- which ticks between two requests -- is set aside."""
    hub = _hub()
    with _served(hub) as port:
        header_sets = []
        for headers in (
            {},
            {"Authorization": "Bearer wrong"},
            {"Authorization": f"Basic {TOKEN}"},
        ):
            _, response_headers, _ = _request(port, "GET", "/health", headers)
            response_headers.pop("Date", None)
            header_sets.append(response_headers)

    assert header_sets[0] == header_sets[1] == header_sets[2]


def test_a_non_ascii_authorization_header_gets_the_same_401():
    """A byte no client library would send unasked (Latin-1 `\\xe9`, sent raw on the
    wire) must not crash the handler or reset the connection: it is one more wrong
    credential, answered exactly like any other."""
    hub = _hub()
    with _served(hub) as port:
        answer = _raw(
            port,
            b"GET /health HTTP/1.0\r\nHost: 127.0.0.1\r\n"
            b"Authorization: Bearer t\xe9ken\r\n\r\n",
        )

    assert answer.startswith(b"HTTP/1.0 401")
    assert answer.endswith(b'{"error": "unauthorized"}')


# --- the process (Task 11) --------------------------------------------------------

GOOD = "tasks/fixation_detection.py"
ALLOCATION = "tasks/allocation.py"
#: What every `wlx run` here runs in: the stand-in rig's direct view, which the
#: reference tasks are written for.
_SETUP = ("--rig", RIG_FILE, "--view", "direct")
#: The twelve-hour reference config: a session under it runs until it is stopped.
TWELVE_HOURS = "tasks/twelve_hour_bounds.py"
#: What the fixation task needs set to run headless (as in `test_cli.py`).
_TASK_SETS = [
    "--set", "fix_timeout=4.0",
    "--set", "fix_hold=0.3",
    "--set", "response_window=0.6",
    "--set", "target_hold=0.2",
    "--set", "fix_window=2.0",
    "--set", "target_window=3.0",
    "--set", "target_position=10.0",
]

#: **Ruling 10** (P4d-2a final review), as `tests/test_cli.py`'s autouse fixture has it:
#: a `wlx run` here that cannot finish fails rather than running on until the mutation
#: harness kills the suite. The end-to-end session below declares 100,000 trials and
#: is ended by a console's `Stop` after about 900 (898 to 916 over five runs of this
#: test in the plan's pre-flight, 2026-09-26: a scratch count, not a claim about this
#: system). A mutant that breaks the `Stop` path would otherwise leave that session
#: running on its daemon thread past the test, into the rest of the suite and
#: interpreter shutdown. Flat rather than scaled to the declared trials, which are
#: deliberately unreachable here.
E2E_TRIAL_BUDGET = 20_000


def _trial_budget(monkeypatch, allowed: int, pace_s: float = 0.0) -> None:
    """Fail the session a test starts once it has run `allowed` trials: `taskd`'s
    `run_trial` raises past that, so the session faults, publishes that it did, and
    `wlx run` ends -- `tests/test_cli.py`'s budget, for the tests here that run a
    session. The session's own clocks stay under test. `pace_s` sleeps before each
    trial (`CONTROL_TRIAL_PACE_S` says why)."""
    from wl_xcon import taskd

    real, left = taskd.run_trial, [allowed]

    def run_trial(*args, **kwargs):
        left[0] -= 1
        if left[0] < 0:
            raise RuntimeError(
                "this session has run more trials than its budget "
                "(tests/test_serve.py, Ruling 10): nothing ended it"
            )
        if pace_s:
            time.sleep(pace_s)
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", run_trial)


def _main_uninterrupted(argv: list) -> int:
    """`main(argv)`, with an escaping `KeyboardInterrupt` turned into a failure --
    `tests/test_cli.py`'s helper of the same name, for its reason (P4d-2a final review
    M3): a `KeyboardInterrupt` that escapes a test ends the whole pytest run, not the
    test. Copied rather than imported, since importing `test_cli` would collect its
    tests a second time."""
    try:
        return main(argv)
    except KeyboardInterrupt:
        pytest.fail("KeyboardInterrupt escaped main(): Ctrl-C must end wlx serve cleanly")


@pytest.fixture
def server_cleanup():
    """Registers each `Server` a test builds -- kept for the tests that already
    call it, as a pass-through.

    **Fix round 3.** The actual teardown -- without calling `Server.close`, for
    the reason `_torn_down_servers`'s docstring above gives in full -- moved to
    that autouse fixture, which catches every `Server` this file builds (this
    one's own explicit registration included, since it also goes through
    `Server.__init__`) rather than only the ones a test remembered to hand to
    this one. Two independent teardowns of the same `Server` would have been
    redundant, not wrong (`_teardown_without_close`'s own steps are each
    idempotent), so there was no reason to keep both doing the work.
    """

    def _register(server):
        return server

    yield _register


def _endpoints(zmq_cleanup) -> tuple[str, str]:
    """A free PUB/REP pair on loopback, bound by a throwaway link and released."""
    probe = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    pub, rep = probe.pub_endpoint, probe.rep_endpoint
    probe.close()
    return pub, rep


#: The strip's time since the last reward before any reward (`web._last_reward`).
_NONE_YET = (
    '<span class="lab">Since last reward</span>'
    '<span class="val"><span class="nm">none yet</span></span>'
)


def _advancing(server: Server, count: int = 2) -> list[int]:
    """Trial numbers from `server`'s event stream until `count` increasing ones are
    seen: the trial count advancing, as a person watching would see it. Bounded by
    the stream's 10 s read timeout and by a count of events, never by hope."""
    seen: list[int] = []
    with _stream(server.address[1]) as response:
        for _, payload in zip(range(20_000), _events(response)):
            found = re.search(
                r'data-trial="(\d+)"', payload["frags"].get("head-id", "")
            )
            if found and (not seen or int(found.group(1)) > seen[-1]):
                seen.append(int(found.group(1)))
            if len(seen) >= count:
                return seen
    raise AssertionError(f"the trial count never advanced: {seen}")


def test_the_console_follows_a_simulated_session_through_a_restart_to_its_end(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §4.4's end to end, and spec §2's "restarting `wlx serve` changes nothing
    in `taskd`" (Review Focus 5): a real `wlx run --link` in the simulator, a real
    `wlx serve` on loopback, and the event stream read as a browser reads it.

    The session is ended by a console's `Stop` -- what slice b2's page will send --
    because under the twelve-hour reference config nothing else would end it soon,
    and `E2E_TRIAL_BUDGET` fails it if the `Stop` never lands (Ruling 10). With no
    terminal attached -- pytest's stdin is not one -- `wlx run` records `return not
    recorded (no terminal)` and publishes nothing after the loop (P4d-2a Task 8), so
    the stop frame, `phase` still `running`, is the last one the console sees.
    """
    _trial_budget(monkeypatch, E2E_TRIAL_BUDGET)
    pub, rep = _endpoints(zmq_cleanup)
    first = server_cleanup(Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN))
    first.start()
    second = None
    result: dict = {}

    def _run() -> None:
        result["exit_code"] = main(
            [
                "run", GOOD,
                *_SETUP,
                "--allocation", ALLOCATION,
                "--bounds", TWELVE_HOURS,
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_08",
                "--subject", "REFERENCE",
                "--out-of-cage-at", time.strftime("%H:%M"),
                "--delivered-today", "0",
                "--trials", "100000",
                *_TASK_SETS,
                "--link", f"{pub},{rep}",
            ]
        )

    # A daemon, so a run that a broken `Stop` never ends cannot hold the suite open.
    runner = threading.Thread(target=_run, daemon=True)
    runner.start()
    try:
        before = _advancing(first)
        first.close()

        second = server_cleanup(
            Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN)
        )
        second.start()
        after = _advancing(second)
        assert after[0] > before[-1], "the session did not run on without a console"

        # m5: the strip's time since the last reward, over the real wire -- a real
        # reward's instant on the session's clock, through a real frame, rendered by
        # a real `wlx serve` -- stops reading "none yet" once the session has paid.
        rewarded = None
        with _stream(second.address[1]) as response:
            for _, payload in zip(
                range(20_000), _events(response, deadline_s=20.0)
            ):
                strip = payload["frags"].get("strip", "")
                if "Since last reward" in strip and _NONE_YET not in strip:
                    rewarded = strip
                    break
        assert rewarded is not None, "the strip never left 'none yet' for a reward"
        assert re.search(
            r'<span class="lab">Since last reward</span><span class="val">\d+ s</span>',
            rewarded,
        ), rewarded

        # m5: `/health` on real telemetry, with the token, is wl-preproc's own
        # `HealthResponse` -- checked whenever their model is importable, which
        # `WLX_REQUIRE_PREPROC=1` makes a requirement of this module (as `_contract`
        # does for the tests it marks), so CI always checks it.
        status, _, health_body = _request(
            second.address[1],
            "GET",
            "/health",
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert json.loads(health_body)["verdict"] == "ok"
        if HealthResponse is not None:
            assert HealthResponse.model_validate_json(health_body).verdict == "ok"

        with zmq_cleanup(ZmqConsole(pub, rep)) as console, _stream(
            second.address[1]
        ) as response:
            events = _events(response)
            next(events)
            console.send(Stop(by="e2e"))
            ended = None
            for _, payload in zip(range(20_000), events):
                if 'data-state="ended"' in payload["frags"].get("state", ""):
                    ended = payload
                    break

        assert ended is not None, "the console never showed the session ending"
        assert "stopped by e2e" in ended["frags"]["banners"]
        assert ended["live"] is False
    finally:
        # Fix round 1, M6: an assertion above this `finally` (or the `Stop` never
        # reaching the session for some other reason) used to leave the runner
        # thread with no `Stop` sent at all, riding out its full `E2E_TRIAL_BUDGET`
        # (about 13 s, the plan's pre-flight measurement) before this test's own
        # 30 s join -- close on a slow host, and a wasted 13 s on every host when
        # the thing under test is a bug that already showed itself. Sending one
        # more `Stop` here, if the session is still running, ends it at the next
        # trial boundary instead of at the budget.
        if runner.is_alive():
            try:
                with zmq_cleanup(ZmqConsole(pub, rep)) as rescue:
                    rescue.send(Stop(by="e2e-cleanup"))
            except Exception:  # noqa: BLE001 -- best-effort cleanup, never masks
                pass  # the real failure above with a cleanup-path exception here
        runner.join(timeout=30)
        first.close()
        if second is not None:
            second.close()
    assert not runner.is_alive(), "wlx run did not finish once it was stopped"
    # Both servers' `ZmqConsole`s and `main()`'s own `ZmqLink` were built inside
    # threads this test cannot register with `zmq_cleanup`. `_every_zmq_context_released`
    # destroys their contexts at teardown. The `gc.collect()` that used to stand here was
    # where `link.close`'s mutant deadlocked (`tests/_zmq_release.py`).
    # Fix round 1, M6: a `KeyError` here, if `_run`'s thread crashed before ever
    # setting `result["exit_code"]`, pointed at this line instead of at whatever
    # actually crashed `_run` -- a stack trace whose most useful frame is missing.
    assert "exit_code" in result, (
        "wlx run's thread never recorded an exit code -- it likely raised before "
        "main() returned; check this test's own thread for the real traceback"
    )
    assert result["exit_code"] == 0


def _until_refused(server: Server, publish, expect: str) -> str:
    """Publish until the hub says it refused a frame for `expect`'s reason: a PUB
    socket drops what it sends before a subscription lands, so one send proves
    nothing."""
    for _ in range(250):
        publish()
        rejected = server.hub.snapshot(on_box=True, stale_after_s=30.0)[1].rejected
        if rejected and expect in rejected:
            return rejected
        time.sleep(0.02)
    raise AssertionError(f"the server never said it refused a frame ({expect!r})")


def test_a_frame_this_console_cannot_read_is_shown_as_refused_not_guessed(
    zmq_cleanup, server_cleanup
):
    """Review Focus 1: a frame of another schema -- a schema-6 `wlx run` beside this
    `wlx serve`, which this slice's own upgrade makes likely -- and a packet that is
    no frame at all. Each is said, neither is shown, and serving goes on."""
    import msgpack

    link = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    server = server_cleanup(
        Server(
            sub=link.pub_endpoint,
            req=link.rep_endpoint,
            http=("127.0.0.1", 0),
            token=TOKEN,
        )
    )
    server.start()
    try:
        why = _until_refused(
            server, lambda: link.publish(replace(frame(), schema=6)), "schema 6"
        )
        assert f"this console reads schema {SCHEMA}" in why
        assert server.hub.snapshot(on_box=True, stale_after_s=30.0)[0] is None

        why = _until_refused(
            server,
            lambda: link._pub.send(msgpack.packb({"schema": SCHEMA}, use_bin_type=True)),
            "could not be decoded",
        )
        assert "KeyError" in why

        for _ in range(250):
            link.publish(frame())
            shown, seen = server.hub.snapshot(on_box=True, stale_after_s=30.0)
            if shown is not None:
                break
            time.sleep(0.02)
        assert shown is not None and seen.rejected is None
        assert _request(server.address[1], "GET", "/")[0] == 200
    finally:
        server.close()


#: A schema-6 frame's own field set (`link.py`'s schema docstring, entry 6), built
#: by hand rather than via `replace(frame(), schema=6)`: that helper starts from a
#: *schema-7* frame and only overwrites `schema`, so it still carries `task`,
#: `allocation`, `bounds_config`, `params`, `floor_ml`, `out_of_cage_limit_s`,
#: `wall_at`, `last_reward_at` and `recent_outcomes` -- every field schema 7 added.
#: A real schema-6 `wlx run` never sends those at all (fix round 1, I3).
_SCHEMA_6_PAYLOAD = {
    "schema": 6,
    "session_id": "2027-01-14_08",
    "subject": "REFERENCE",
    "trial_index": 5,
    "block": "block-1",
    "stopped_because": None,
    "stop_kind": None,
    "phase": "running",
    "fluid_session_ml": 12.5,
    "fluid_today_ml": 12.5,
    "shortfall_ml": 0.0,
    "out_of_cage_seconds": 300.0,
    "chair_seconds": None,
    "in_session_seconds": 300.0,
    "deployment": "cage_side",
    "duration_warning": None,
    "outcomes": {"correct": 3},
    "hangs": 0,
    "owed": {},
    "staged": [],
    "refusals": [],
    "refusals_dropped": 0,
}


def test_a_real_schema_6_frame_is_refused_by_name_not_a_keyerror(
    zmq_cleanup, server_cleanup
):
    """Fix round 1, I3: `test_a_frame_this_console_cannot_read_is_shown_as_refused_not_guessed`'s
    schema-6 case above uses `replace(frame(), schema=6)`, which only overwrites the
    `schema` field on an otherwise-complete schema-7 frame -- `task` and the rest of
    schema 7's additions are still on it, so `decode` (before this fix) sailed past
    building the whole `Telemetry` and only its `schema != SCHEMA` check afterward
    ever fired.

    A real schema-6 `wlx run` sends none of those fields. Before this fix, `decode`
    read fields in encoding order and hit `data["task"]` -- missing from a genuine
    schema-6 payload -- before it ever compared `schema`, so `wlx serve` showed
    "a telemetry frame could not be decoded, so it is not shown: KeyError: 'task'"
    instead of naming the schema mismatch it actually was."""
    link = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    server = server_cleanup(
        Server(
            sub=link.pub_endpoint,
            req=link.rep_endpoint,
            http=("127.0.0.1", 0),
            token=TOKEN,
        )
    )
    server.start()
    try:
        import msgpack

        why = _until_refused(
            server,
            lambda: link._pub.send(
                msgpack.packb(_SCHEMA_6_PAYLOAD, use_bin_type=True)
            ),
            "schema 6",
        )
        assert f"this console reads schema {SCHEMA}" in why
        assert "KeyError" not in why
        assert "could not be decoded" not in why
    finally:
        server.close()


def test_closing_the_server_stops_serving(zmq_cleanup, server_cleanup):
    pub, rep = _endpoints(zmq_cleanup)
    server = server_cleanup(Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN))
    server.start()
    port = server.address[1]
    assert _request(port, "GET", "/")[0] == 200

    server.close()
    server.close()

    with pytest.raises(OSError):
        _request(port, "GET", "/")


def test_closing_the_server_stops_its_threads_and_open_streams(
    zmq_cleanup, server_cleanup
):
    """Fix round 1, I2: the security review's mutants -- deleting `self._stop.set()`
    or `self.hub.close()` in `Server.close` -- passed every existing `Server` test,
    each merely 5 s slower (the `.join(timeout=5)` calls timing out rather than
    returning promptly). None of those tests checked what `close()` is actually
    supposed to stop: this one does, three ways.

    Bounded well under the 5 s join cap (2 s), so a mutant that reintroduces either
    deletion fails this test in seconds -- not by hanging the suite, and not merely
    by being slower than an assertion nobody wrote."""
    pub, rep = _endpoints(zmq_cleanup)
    server = server_cleanup(Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN))
    server.start()

    with _stream(server.address[1]) as response:
        started = time.monotonic()
        server.close()
        elapsed_close = time.monotonic() - started

        drain_started = time.monotonic()
        ended = _read_to_eof(response, within_s=5.0)
        elapsed_drain = time.monotonic() - drain_started

    assert elapsed_close < 2.0, f"close() took {elapsed_close:.2f}s (want well under 5s)"
    assert ended, "an /events stream open when close() ran was still sending 5 s later"
    assert elapsed_drain < 2.0, (
        f"an /events stream open when close() ran took {elapsed_drain:.2f}s to see "
        f"EOF (want well under 5s)"
    )
    assert not server._telemetry.is_alive(), "the telemetry thread outlived close()"
    assert not server._web.is_alive(), "the HTTP thread outlived close()"


def _token_file(tmp_path, text: str = f"{TOKEN}\n") -> Path:
    path = tmp_path / "health.token"
    path.write_text(text, encoding="utf-8")
    return path


def _serve_args(
    tmp_path,
    *,
    token: Path | None = None,
    link: str = "tcp://127.0.0.1:5571,tcp://127.0.0.1:5572",
    http: str = "127.0.0.1:0",
    extra: tuple = (),
) -> list:
    return [
        "serve",
        "--link", link,
        "--http", http,
        "--health-token-file", str(token if token is not None else _token_file(tmp_path)),
        *extra,
    ]


def test_wlx_serve_serves_until_interrupted_then_closes(
    tmp_path, monkeypatch, capsys, zmq_cleanup, server_cleanup
):
    pub, rep = _endpoints(zmq_cleanup)
    seen: dict = {}

    def interrupted(server: Server) -> None:
        server_cleanup(server)
        seen["port"] = server.address[1]
        seen["page"] = _request(seen["port"], "GET", "/")[0]
        seen["health"] = _request(
            seen["port"], "GET", "/health", {"Authorization": f"Bearer {TOKEN}"}
        )[0]
        raise KeyboardInterrupt

    monkeypatch.setattr(serve, "_wait", interrupted)

    assert _main_uninterrupted(_serve_args(tmp_path, link=f"{pub},{rep}")) == 130
    assert seen["page"] == 200 and seen["health"] == 200
    captured = capsys.readouterr()
    assert f"http://127.0.0.1:{seen['port']}/" in captured.out
    assert "the session keeps running on the box" in captured.err
    with pytest.raises(OSError):
        _request(seen["port"], "GET", "/")


class _OneFrameThenNothingConsole:
    """A fake `ZmqConsole`: one good frame on its first `receive()`, then a
    `TimeoutError` -- deterministic, no real socket, no timing dependency. Stands
    in for `_link.ZmqConsole` in the fix round 1, I1(b) tests below, so a fatal
    exception past that one frame is exercised the instant `_listen` starts,
    rather than waiting on a real PUB/SUB round trip that could in principle be
    slow on a loaded host."""

    def __init__(self, *args, **kwargs) -> None:
        self._served = False

    def receive(self):
        if self._served:
            raise TimeoutError("no more simulated frames")
        self._served = True
        return frame()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        return None


def test_wlx_serve_ends_with_a_sentence_when_the_telemetry_thread_cannot_start(
    tmp_path, monkeypatch, capsys
):
    """Fix round 1, I1(b): before this fix, `ZmqConsole(...)` construction (the
    `with` statement at the top of `Server._listen`) sat outside every `try`, so a
    `--link` that parsed but that ZeroMQ itself refused at connect time --
    `tcp://127.0.0.1:abc`, a wildcard host, an unknown scheme -- raised out of a
    daemon thread. `threading`'s default excepthook prints that once to stderr and
    the thread is simply gone: `wlx serve` kept its HTTP server up and `/health`
    kept saying `ok` on the last frame it ever received, forever.

    `_link.ZmqConsole` is monkeypatched to raise on construction rather than
    reproduced with a real endpoint zmq happens to reject on this host/zmq
    version: `parse_link` (I1(a), same fix round) already refuses every endpoint
    shape the security review found that reaches this point, so a *real*
    zmq-raises-at-connect reproduction would depend on some other, unlisted zmq
    quirk instead of the one behavior this test exists to pin -- that whatever
    reaches this point and raises ends the process with a sentence.
    """

    def _raises_on_construction(*args, **kwargs):
        raise RuntimeError("simulated: this transport cannot connect")

    monkeypatch.setattr(serve._link, "ZmqConsole", _raises_on_construction)

    exit_code = _main_uninterrupted(_serve_args(tmp_path))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "wlx serve: the telemetry thread stopped" in captured.err
    assert "simulated: this transport cannot connect" in captured.err
    assert "the session is unaffected" in captured.err


def test_a_fatal_exception_with_no_message_is_named_plainly(
    tmp_path, monkeypatch, capsys
):
    """Fix round 3, M1: `_fatal_reason` built `f"{type(exc).__name__}: {exc}"`
    inline, so an exception raised with no message (`RuntimeError()`, no argument,
    `str(exc) == ""`) printed a dangling `"...stopped: RuntimeError: ; the
    session is unaffected"` -- the same trailing colon-and-space fix round 2,
    M-e already fixed for `link.FrameError`'s own message (`link._describe`),
    reachable here too since this was a second, independent place that built the
    same shape of string by hand instead of sharing that helper."""

    def _raises_with_no_message(*args, **kwargs):
        raise RuntimeError()

    monkeypatch.setattr(serve._link, "ZmqConsole", _raises_with_no_message)

    exit_code = _main_uninterrupted(_serve_args(tmp_path))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert (
        "wlx serve: the telemetry thread stopped: RuntimeError; "
        "the session is unaffected"
    ) in captured.err
    assert "RuntimeError: ;" not in captured.err
    assert "RuntimeError:\n" not in captured.err


def test_wlx_serve_ends_with_a_sentence_when_offering_a_frame_raises(
    tmp_path, monkeypatch, capsys
):
    """Fix round 1, I1(b): not only a failure at construction -- anything
    unexpected escaping the receive loop must end the process too, not just a
    decode/schema problem (`link.FrameError`, handled separately and non-fatally).
    `Hub.offer` stands in for any future bug in the hub itself; `_OneFrameThenNothingConsole`
    hands `_listen` one good, schema-7 frame deterministically so `offer` is
    reached on the very first iteration."""
    monkeypatch.setattr(serve._link, "ZmqConsole", _OneFrameThenNothingConsole)

    def _raises(self, telemetry) -> None:
        raise RuntimeError("simulated: the hub could not accept this frame")

    monkeypatch.setattr(Hub, "offer", _raises)

    exit_code = _main_uninterrupted(_serve_args(tmp_path))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "wlx serve: the telemetry thread stopped" in captured.err
    assert "simulated: the hub could not accept this frame" in captured.err
    assert "the session is unaffected" in captured.err


def test_wlx_serve_ends_with_a_sentence_for_a_link_zmq_refuses_for_real(
    tmp_path, capsys
):
    """Fix round 2, M-d. Not a monkeypatch this time (CLAUDE.md: "test the path,
    not the piece") -- both tests above stub `_link.ZmqConsole`/`Hub.offer`, which
    covers the *shape* of a fatal telemetry failure but never proves a real one
    reaches the same ending. `tcp://a b:5571` (a space inside the host) is
    accepted by `parse_link`/`_refuse_unless_tcp_endpoint`: a space is not `*`,
    and it never reaches port validation, since the host is everything before the
    last `:`. ZeroMQ itself refuses to connect to it
    (`zmq.error.ZMQError: Invalid argument`, confirmed by hand against a bare
    `zmq.Context().socket(zmq.SUB).connect(...)` before writing this test) inside
    the telemetry thread, which is exactly the transport failure I1(b) (fix round
    1) exists to end the process on rather than hide.
    """
    exit_code = _main_uninterrupted(
        _serve_args(tmp_path, link="tcp://a b:5571,tcp://127.0.0.1:5572")
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "wlx serve: the telemetry thread stopped" in captured.err
    assert "the session is unaffected" in captured.err


def test_wlx_serve_returns_130_for_a_ctrl_c_between_construction_and_wait(
    tmp_path, monkeypatch, capsys
):
    """Fix round 1, M5: `server.start()` and the startup print used to sit before
    the `try`/`except KeyboardInterrupt` this function wraps `_wait` in, so a
    Ctrl-C landing there -- after `Server()` is built but before the first
    `_wait` call -- escaped as a bare `KeyboardInterrupt` traceback instead of the
    130 every other interruption path here returns."""
    real_start = Server.start

    def _start_then_interrupt(self) -> None:
        real_start(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(Server, "start", _start_then_interrupt)

    exit_code = _main_uninterrupted(_serve_args(tmp_path))
    captured = capsys.readouterr()

    assert exit_code == 130
    assert "the session keeps running on the box" in captured.err


def test_wlx_serve_closes_cleanly_when_ctrl_c_lands_inside_start(
    tmp_path, monkeypatch, capsys
):
    """Fix round 2, N2. A Ctrl-C landing *inside* `Server.start()` itself -- after
    `self._telemetry.start()` but before `self._web.start()` -- used to leave
    `close()` calling `self._http.shutdown()` on a `serve_forever()` that never
    ran, which the stdlib's own docs say blocks forever. The reviewer confirmed it
    by stack: `wait <- wait <- shutdown <- close <- run`.

    `threading.Thread.start` is monkeypatched to raise `KeyboardInterrupt` only for
    the thread named `"wlx-serve-http"` (`Server.__init__`'s own name for `_web`),
    so the telemetry thread starts normally and `Server.start()` itself runs
    unmodified -- this is `_web.start()` failing, not a reimplementation of
    `start()`.

    Run on a background thread with a bounded `join`, per this round's own rule
    (N1) that nothing here waits unboundedly: if `close()` regresses back to
    hanging, this test fails in ~10 s instead of joining the mutation gate's list
    of things that time out at 300 s doing nothing.
    """
    real_thread_start = threading.Thread.start

    def _start(self) -> None:
        if self.name == "wlx-serve-http":
            raise KeyboardInterrupt
        return real_thread_start(self)

    monkeypatch.setattr(threading.Thread, "start", _start)

    result: dict = {}

    def _run() -> None:
        result["exit_code"] = _main_uninterrupted(_serve_args(tmp_path))

    runner = threading.Thread(target=_run, daemon=True)
    runner.start()
    runner.join(timeout=10)

    assert not runner.is_alive(), (
        "wlx serve did not return within 10s of a Ctrl-C landing inside start() "
        "(fix round 2, N2: close() must not hang on shutdown() for a "
        "serve_forever() that never ran)"
    )
    captured = capsys.readouterr()
    assert result.get("exit_code") == 130, (
        f"expected 130 (Ctrl-C), got {result.get('exit_code')!r}: {captured.err}"
    )
    assert "the session keeps running on the box" in captured.err


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="a POSIX signal; Ctrl-C on Windows is UNVERIFIED (`serve._wait`)",
)
def test_wlx_serve_exits_130_on_a_real_sigint(tmp_path):
    """Every other Ctrl-C test here raises `KeyboardInterrupt` through a monkeypatch,
    so none shows that a real SIGINT ends a serving `wlx serve` at all. This one
    starts it as its own process -- the real `_wait`, not this file's bounded
    stand-in -- waits for its address line, fetches the page from it, sends SIGINT,
    and reads 130 and the sentence. Every wait is bounded, and the process is killed
    if it outlives one.

    The child starts with SIGINT at its default, as a terminal gives it, whatever
    this run inherited. A suite started as a background job -- `nohup ... &`, or a
    mutation sweep launched that way -- has SIGINT ignored, an ignored signal
    survives exec, and Python installs its `KeyboardInterrupt` handler only over the
    default. Without this the test failed there, and every mutation baseline with
    it, while passing at a terminal (2026-09-27)."""
    command = [
        sys.executable,
        "-c",
        "import sys; from wl_xcon.cli import main; sys.exit(main(sys.argv[1:]))",
        *_serve_args(tmp_path),
    ]
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL),
    )
    try:
        first_line: queue.Queue = queue.Queue()
        threading.Thread(
            target=lambda: first_line.put(process.stdout.readline()), daemon=True
        ).start()
        try:
            address = first_line.get(timeout=30)
        except queue.Empty:
            pytest.fail("wlx serve never printed its address within 30 s")
        found = re.search(r"the console is at http://127\.0\.0\.1:(\d+)/", address)
        assert found, address
        assert _request(int(found.group(1)), "GET", "/")[0] == 200

        process.send_signal(signal.SIGINT)
        _, err = process.communicate(timeout=15)

        assert process.returncode == 130, err
        assert "the session keeps running on the box" in err
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_serving_waits_for_the_operator(_bounded_real_wait):
    """A `_wait` that returned would end the console the moment it started.

    `_wait` blocks on a real `Server`'s `_fatal` `Event` -- set when the telemetry
    thread dies (Ruling 9) -- rather than looping on its own, so this stub carries
    one that is never set; `server=None` does not work, since `_wait` reads
    `server._fatal` unconditionally.

    This file's autouse `_bounded_real_wait` fixture replaces
    `serve._wait` everywhere else with a bounded stand-in, so a mutant that breaks
    the real one fails a test instead of hanging the suite -- but that means
    `serve._wait` is no longer the real function by the time a test body runs.
    This test is explicitly about the *real* function's own blocking behavior, so
    it takes the fixture itself and calls the reference it returns (captured
    before the patch) rather than `serve._wait`. Still bounded on its own
    (`join(timeout=0.2)`): a test that exists to prove something never returns
    must never wait on it unboundedly to find out."""
    waiter = threading.Thread(
        target=_bounded_real_wait, args=(SimpleNamespace(_fatal=threading.Event()),), daemon=True
    )
    waiter.start()
    waiter.join(timeout=0.2)

    assert waiter.is_alive()


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("", "is empty"),
        ("   \n", "is empty"),
        ("tök\n", "non-ASCII"),
        # Fix round 1, M2: `.strip()` only removes *leading/trailing* whitespace,
        # so a second line survives inside the token -- no HTTP header can carry
        # it, and `hmac.compare_digest` would never see the wl-works's correct
        # token match, since wl-works cannot send a newline in a header value.
        (f"{TOKEN}\nsecond-line\n", "cannot be carried in a header"),
    ],
)
def test_wlx_serve_refuses_a_token_it_cannot_use(tmp_path, text, why):
    with pytest.raises(SystemExit, match=why):
        main(_serve_args(tmp_path, token=_token_file(tmp_path, text)))


def test_wlx_serve_refuses_a_token_file_inside_the_repository(tmp_path):
    """Spec §2: a token file, never the repository, refused through `wlx serve`
    itself. The checkout is built in `tmp_path` -- a `.git` directory beside the
    token -- so this passes or fails on the refusal, wherever the suite runs, and not
    on whether this copy of the code happens to sit in a git checkout."""
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    inside = _token_file(checkout)

    with pytest.raises(SystemExit, match="inside this repository"):
        main(_serve_args(tmp_path, token=inside))


def test_read_token_refuses_a_file_inside_any_git_checkout_not_just_this_one(
    tmp_path,
):
    """Fix round 1, M1: `_REPO_ROOT` was `Path(__file__).resolve().parents[1]` --
    somewhere in `site-packages` for a non-editable install of `wl_xcon`,
    guarding nothing there -- and the test above computed the very same expression
    to check against, so it agreed with the refusal regardless of whether that path
    was a real git checkout. Walking up from the token file itself, looking for a
    `.git` entry, catches a checkout wherever it actually is, and works whether
    `.git` is a directory (an ordinary clone) or a file (a worktree, this session's
    own worktree among them -- `git worktree`'s own on-disk layout)."""
    as_directory = tmp_path / "repo-with-git-dir"
    (as_directory / ".git").mkdir(parents=True)
    token_under_dir_repo = as_directory / "health.token"
    token_under_dir_repo.write_text(f"{TOKEN}\n", encoding="utf-8")

    as_worktree = tmp_path / "repo-with-git-file"
    as_worktree.mkdir()
    (as_worktree / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
    token_under_worktree = as_worktree / "health.token"
    token_under_worktree.write_text(f"{TOKEN}\n", encoding="utf-8")

    outside = tmp_path / "not-a-checkout" / "health.token"
    outside.parent.mkdir()
    outside.write_text(f"{TOKEN}\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="inside this repository"):
        serve.read_token(token_under_dir_repo)
    with pytest.raises(SystemExit, match="inside this repository"):
        serve.read_token(token_under_worktree)
    assert serve.read_token(outside) == TOKEN


def test_wlx_serve_refuses_a_token_file_it_cannot_read(tmp_path):
    with pytest.raises(SystemExit, match="cannot read"):
        main(_serve_args(tmp_path, token=tmp_path / "missing.token"))


@pytest.mark.parametrize(
    "link",
    [
        "tcp://127.0.0.1:5571",
        "tcp://127.0.0.1:1,tcp://127.0.0.1:2,tcp://127.0.0.1:3,tcp://127.0.0.1:4",
        ",tcp://127.0.0.1:5572",
    ],
)
def test_wlx_serve_refuses_a_link_that_is_not_two_or_three_endpoints(tmp_path, link):
    with pytest.raises(SystemExit, match="two or three"):
        main(_serve_args(tmp_path, link=link))


def test_parse_link_strips_whitespace_around_each_endpoint():
    """Fix round 1, I1(a): the security review's own reproduction was a `--link`
    with a space after the comma -- `"tcp://127.0.0.1:5571, tcp://127.0.0.1:5572"`
    -- which the old `parse_link` returned with the leading space still on the
    second endpoint, still `"://"`-shaped, so it passed straight through and only
    ZeroMQ noticed, inside the telemetry thread, with no `try` around it (I1(b)).
    Two endpoints give no mark endpoint (P4d-2b b2a); a third is it."""
    assert serve.parse_link("tcp://127.0.0.1:5571, tcp://127.0.0.1:5572") == (
        "tcp://127.0.0.1:5571",
        "tcp://127.0.0.1:5572",
        None,
    )
    assert serve.parse_link("tcp://127.0.0.1:1, tcp://127.0.0.1:2 ,tcp://127.0.0.1:3") == (
        "tcp://127.0.0.1:1",
        "tcp://127.0.0.1:2",
        "tcp://127.0.0.1:3",
    )


@pytest.mark.parametrize(
    ("link", "why"),
    [
        # The security review's own reproduction, RE-CHECKED here as a positive
        # case above and as the four negatives it named below: each of these
        # passed the old `parse_link` (every half still contained "://") and only
        # made ZeroMQ raise once the telemetry thread tried to connect (I1(b)).
        ("tcp://127.0.0.1:abc,tcp://127.0.0.1:5572", "decimal"),
        ("tcp://127.0.0.1,tcp://127.0.0.1:5572", "port"),
        ("tcp://*:5571,tcp://127.0.0.1:5572", "wildcard"),
        ("foo://127.0.0.1:5571,tcp://127.0.0.1:5572", "tcp://HOST:PORT"),
        # Not one of the review's probes, but the same shape: two endpoints, no
        # scheme on either -- moved here from
        # `test_wlx_serve_refuses_a_link_that_is_not_two_endpoints` (fix round 1),
        # since "5571,5572" really is two endpoints, just not `tcp://` ones, and
        # deserves its own sentence rather than borrowing "exactly two"'s.
        ("5571,5572", "tcp://HOST:PORT"),
        # Three parts, which is a count `--link` takes since P4d-2b b2a, none of
        # them an endpoint (this was "not two endpoints" in b1).
        ("a,b,c", "tcp://HOST:PORT"),
    ],
)
def test_wlx_serve_refuses_a_link_endpoint_zmq_would_choke_on(tmp_path, link, why):
    with pytest.raises(SystemExit, match=why):
        main(_serve_args(tmp_path, link=link))


@pytest.mark.parametrize(
    "http",
    [
        "8080",
        "localhost:",
        "127.0.0.1:99999",
        "[::1]:8080",
        "::1:8080",
        # Fix round 1, M3: "²" (superscript two) is a digit by
        # `str.isdigit()`'s reckoning but not by `int()`'s -- the old check used
        # the former and let `int(port)` raise a bare, uncaught `ValueError`
        # instead of this function's own sentence.
        "127.0.0.1:²",
    ],
)
def test_wlx_serve_refuses_an_address_it_cannot_serve_on(tmp_path, http):
    with pytest.raises(SystemExit, match="HOST:PORT"):
        main(_serve_args(tmp_path, http=http))


@pytest.mark.parametrize("stale", ["0", "-5", "nan", "inf"])
def test_wlx_serve_refuses_a_stale_after_that_is_not_a_positive_time(tmp_path, stale):
    with pytest.raises(SystemExit, match="--stale-after"):
        main(_serve_args(tmp_path, extra=("--stale-after", stale)))


# --- P4d-2b b2a: every request's Host (spec §2, §5.3) --------------------------------


@pytest.mark.parametrize(
    ("header", "name"),
    [
        ("127.0.0.1:8080", "127.0.0.1"),
        ("LocalHost:8080", "localhost"),
        ("localhost", "localhost"),
        ("[::1]:8080", "::1"),
        ("[::1]", "::1"),
        ("Rig3.Lab.example:80", "rig3.lab.example"),
        (None, None),
        ("", None),
        ("::1", None),
        ("127.0.0.1:80x", None),
        ("[::1:8080", None),
        ("[]:80", None),
        ("h\xe9te:80", None),
    ],
)
def test_host_name_is_the_name_a_host_header_gives(header, name):
    assert host_name(header) == name


def test_names_loopback_is_localhost_and_the_loopback_addresses_alone():
    assert all(names_loopback(n) for n in ("localhost", "127.0.0.1", "127.8.9.10", "::1"))
    assert not any(names_loopback(n) for n in (None, "mac.lab", "192.168.1.92", "localhost.evil"))


def test_box_names_are_loopback_this_boxs_own_names_and_addresses_and_the_allowed(
    monkeypatch,
):
    """The defaults (spec §5.3): loopback and the box's own host names and addresses;
    `--allow-host` adds names. Read from the host's resolver, which a test pins."""
    monkeypatch.setattr(serve.socket, "gethostname", lambda: "Rig3")
    monkeypatch.setattr(serve.socket, "getfqdn", lambda: "rig3.lab.example")
    found = {
        "rig3": [(2, 1, 6, "", ("192.168.1.92", 0))],
        "rig3.lab.example": [(30, 1, 6, "", ("fe80::1%en0", 0, 0, 1))],
    }

    def getaddrinfo(name, port):
        if name not in found:
            raise OSError("no such name")
        return found[name]

    monkeypatch.setattr(serve.socket, "getaddrinfo", getaddrinfo)

    assert box_names(("Other.Name ", "")) == frozenset(
        {
            "localhost", "127.0.0.1", "::1",
            "rig3", "rig3.lab.example", "192.168.1.92", "fe80::1",
            "other.name",
        }
    )


def test_a_lookup_that_fails_leaves_loopback_and_the_allowed(monkeypatch):
    monkeypatch.setattr(serve.socket, "gethostname", lambda: "")
    monkeypatch.setattr(serve.socket, "getfqdn", lambda: "")

    assert box_names(("rig3",)) == LOOPBACK_NAMES | {"rig3"}


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/"), ("GET", "/events"), ("GET", "/health"), ("GET", "/nope"),
     ("POST", "/commands"), ("PUT", "/")],
)
def test_a_request_whose_host_names_another_console_gets_a_json_421(method, path):
    """Spec §2 and §5.3: every request is answered only when its `Host` names this
    console. A DNS-rebinding page's request carries its own name, and gets a JSON
    421 and no page -- not even the token check."""
    hub = _hub()
    with _served(hub) as port:
        status, headers, body = _request(
            port, method, path, {"Host": "evil.example", "Authorization": f"Bearer {TOKEN}"}
        )

    assert status == 421
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body)["error"] == "misdirected request"
    assert b"<" not in body and b"evil" not in body


def test_a_request_with_no_host_at_all_is_misdirected():
    hub = _hub()
    with _served(hub) as port:
        answer = _raw(port, b"GET / HTTP/1.0\r\n\r\n")

    assert answer.startswith(b"HTTP/1.0 421")


def test_a_name_given_with_allow_host_is_answered():
    hub = _hub()
    with _served(hub, hosts=LOOPBACK_NAMES | {"rig3.lab"}) as port:
        status = _request(port, "GET", "/", {"Host": f"rig3.lab:{port}"})[0]

    assert status == 200


# --- P4d-2b b2a: POST /commands, from the box (spec §2, §5.3) --------------------------


class _Dispatch:
    """What `Server.dispatch` would be, recording each request it is handed."""

    def __init__(self, answer=(200, {"status": "sent", "said": "sent: test"})):
        self.seen: list = []
        self.answer = answer

    def __call__(self, request):
        self.seen.append(request)
        return self.answer


def _post(port: int, body, headers: dict | None = None):
    """`POST /commands` the way the box's own page sends it, unless `headers` says
    otherwise: loopback `Host`, this page's `Origin`, and JSON."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    sent = {
        "Host": f"127.0.0.1:{port}",
        "Origin": f"http://127.0.0.1:{port}",
        "Content-Type": "application/json",
    }
    sent.update(headers or {})
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.putrequest("POST", "/commands", skip_host=True)
        for name, value in sent.items():
            if value is not None:
                connection.putheader(name, value)
        connection.putheader("Content-Length", str(len(raw)))
        connection.endheaders(raw)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_a_command_from_the_boxs_own_page_is_dispatched_as_the_person_named():
    """Spec §2's four checks all hold, the body is a command, and it is dispatched
    with the actor recorded as `NAME (box, unverified)` -- S9a §6: a forgeable name
    says it is unverified. The dispatch's answer is the page's."""
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(port, {"kind": "pause", "by": " jake "})

    assert (status, answer) == (200, {"status": "sent", "said": "sent: test"})
    assert dispatch.seen == [Pause(by="jake (box, unverified)")]


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": None},
        {"Origin": "http://evil.example"},
        {"Origin": "http://127.0.0.1:1"},
        {"Content-Type": "text/plain"},
        {"Content-Type": None},
        {"Host": "rig3.lab"},
    ],
    ids=["no-origin", "cross-site", "other-port", "text-plain", "no-type", "lan-name"],
)
def test_a_write_that_fails_one_of_the_four_checks_is_refused_with_the_sentence(headers):
    """Spec §2: a write from the box is accepted only when all four hold. A LAN name
    in `Host` -- one this console answers reads on -- is still not loopback, so the
    box's browser under that name cannot write. Each is refused with the §2
    sentence, and nothing is dispatched."""
    dispatch = _Dispatch()
    with _served(_hub(), hosts=LOOPBACK_NAMES | {"rig3.lab"}, dispatch=dispatch) as port:
        status, answer = _post(port, {"kind": "stop", "by": "jake"}, headers)

    assert status == 403
    assert answer == {"status": "refused", "said": CONTROLS_AT_THE_BOX}
    assert dispatch.seen == []


def test_a_write_from_a_peer_that_is_not_the_box_is_refused(monkeypatch):
    """The first check: a loopback peer. Every test socket is loopback, so the peer
    the handler reads is made a LAN one.

    **Fix round 1, Important 1.** `_post`'s default `Host: 127.0.0.1:{port}` made
    this test unable to fail: `names_loopback` also calls `on_box` (serve.py:367),
    so with the monkeypatch in place the `Host` check refused the request on its
    own, whether or not `may_write`'s own peer check (`on_box(self.client_
    address[0])`) was even there. `Host: localhost` and a matching `Origin` avoid
    that: `names_loopback("localhost")` is `True` on the literal alone, short-
    circuiting before it ever calls `on_box`, so only the peer check can produce
    the 403 this test asserts."""
    monkeypatch.setattr(serve, "on_box", lambda host: False)
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(
            port,
            {"kind": "stop", "by": "jake"},
            {"Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"},
        )

    assert (status, answer["said"]) == (403, CONTROLS_AT_THE_BOX)
    assert dispatch.seen == []


@pytest.mark.parametrize(
    ("body", "said"),
    [
        (b"not json", "a command is one JSON object"),
        (b"[1]", "a command is one JSON object"),
        (b"\xff", "a command is one JSON object"),
        ({"kind": "reboot", "by": "jake"}, "'reboot' is not a command"),
        ({"kind": "pause"}, "every command records who sent it"),
        ({"kind": "pause", "by": "   "}, "every command records who sent it"),
        ({"kind": "pause", "by": "j" * 65}, "every command records who sent it"),
        ({"kind": "pause", "by": "ja\nke"}, "every command records who sent it"),
        ({"kind": "pause", "by": "jake", "why": "x"}, "a pause command takes no why"),
        ({"kind": "set", "by": "jake", "name": "fix_hold", "value": True}, "neither"),
        ({"kind": "set", "by": "jake", "value": 0.4}, "names its parameter"),
        ({"kind": "schedule", "by": "jake", "at": "25:00"}, "HH:MM"),
        ({"kind": "schedule", "by": "jake", "at": "14:30", "trials": 3}, "exactly one"),
        ({"kind": "schedule", "by": "jake"}, "exactly one"),
        ({"kind": "mark", "by": "jake", "pressed_at": "now"}, "pressed_at"),
        ({"kind": "note", "by": "jake", "mark": MARK_ID_LIMIT + 1, "note": ""}, "names the mark"),
        ({"kind": "note", "by": "jake", "mark": 3, "note": "x" * 501}, "at most 500"),
        ({"kind": "reward", "by": "jake", "ml": 0.5}, "a reward command takes no ml"),
    ],
)
def test_a_body_that_is_not_a_command_is_refused_before_anything_is_queued(body, said):
    """Spec §5.3: the body is validated before anything is queued, with a sentence
    the page shows; a person with no name is told to give one (Review Focus 6)."""
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(port, body)

    assert status == 400
    assert answer["status"] == "refused"
    assert answer["said"].startswith("not sent: ")
    assert said in answer["said"]
    assert dispatch.seen == []


@pytest.mark.parametrize(
    "body",
    [
        b'{"kind": [], "by": "jake"}',
        b'{"kind": {}, "by": "jake"}',
        ('{"kind": "mark", "by": "jake", "pressed_at": ' + str(10**400) + "}").encode("ascii"),
        ('{"kind": "schedule", "by": "jake", "ml": ' + str(10**400) + "}").encode("ascii"),
        f'{{"kind": "schedule", "by": "jake", "trials": {2**64}}}'.encode("ascii"),
    ],
    ids=[
        "kind-is-a-list",
        "kind-is-a-dict",
        "mark-pressed-at-overflows-a-float",
        "schedule-ml-overflows-a-float",
        "schedule-trials-past-the-wires-signed-range",
    ],
)
def test_a_malformed_body_of_any_shape_gets_a_json_refusal_and_nothing_is_queued(body):
    """Fix round 1, Important 2 (security review). Each of these used to escape
    `_command`'s specific `except (UnicodeDecodeError, ValueError)` and kill the
    handler thread with no answer at all: an unhashable `kind` (`TypeError` from
    `kind not in _SHAPES`, serve.py:524), and a JSON integer too large for `float`
    to carry -- `OverflowError` from `math.isfinite`, in the mark branch
    (serve.py:553) and in `link.check_schedule`'s fluid branch (link.py:933). A
    `trials` count of `2**64` is a fifth shape: no `OverflowError`, but it used to
    pass `check_schedule` (no upper bound, link.py:923), get queued, and only then
    fail inside msgpack on the command thread -- a validation failure reported as a
    *not delivered* one. Every shape now gets an ordinary JSON refusal before
    anything is queued, and the server keeps serving."""
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(port, body)
        still_serving = _request(port, "GET", "/")[0]

    assert 400 <= status < 500, (status, answer)
    assert answer["status"] == "refused"
    assert dispatch.seen == []
    assert still_serving == 200


def test_a_body_longer_than_the_limit_or_without_a_length_is_refused_unread():
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        too_long = _post(port, {"kind": "pause", "by": "j" * 5000})
        answer = _raw(
            port,
            (
                f"POST /commands HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n"
                f"Origin: http://127.0.0.1:{port}\r\n"
                f"Content-Type: application/json\r\n\r\n"
            ).encode("ascii"),
        )

    assert too_long == (413, {"status": "refused", "said": "a command is at most 4096 bytes"})
    assert answer.startswith(b"HTTP/1.0 400")
    assert b"Content-Length" in answer
    assert dispatch.seen == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"kind": "set", "by": "jake", "name": "fix_hold", "value": 1},
         SetParameter(name="fix_hold", value=1.0, by="jake (box, unverified)")),
        ({"kind": "set", "by": "jake", "name": "shape", "value": "penguin"},
         SetParameter(name="shape", value="penguin", by="jake (box, unverified)")),
        ({"kind": "stop", "by": "jake"}, Stop(by="jake (box, unverified)")),
        ({"kind": "resume", "by": "jake"}, Resume(by="jake (box, unverified)")),
        ({"kind": "cancel", "by": "jake"}, CancelScheduledStop(by="jake (box, unverified)")),
        ({"kind": "schedule", "by": "jake", "at": "14:30"},
         ScheduleStop(kind="clock", value="14:30", by="jake (box, unverified)")),
        ({"kind": "schedule", "by": "jake", "trials": 12},
         ScheduleStop(kind="trials", value=12, by="jake (box, unverified)")),
        ({"kind": "schedule", "by": "jake", "ml": 5},
         ScheduleStop(kind="fluid", value=5, by="jake (box, unverified)")),
        ({"kind": "mark", "by": "jake", "pressed_at": 1_700_000_000},
         MarkSignal(by="jake (box, unverified)", pressed_at=1_700_000_000.0)),
        ({"kind": "mark", "by": "jake"}, MarkSignal(by="jake (box, unverified)", pressed_at=None)),
        ({"kind": "note", "by": "jake", "mark": 7, "note": "bubble"},
         MarkNote(mark=7, note="bubble", by="jake (box, unverified)")),
        ({"kind": "reward", "by": "jake"}, ManualReward(by="jake (box, unverified)")),
    ],
)
def test_each_command_the_page_sends_parses_to_what_the_rig_is_sent(body, expected):
    assert parse_command(body) == expected


def test_a_parse_refusal_is_a_bad_command():
    with pytest.raises(BadCommand):
        parse_command({"kind": "pause", "by": ""})


def test_the_boxs_page_may_write_and_the_same_box_under_a_lan_name_may_not(monkeypatch):
    """`View.can_write` is spec §2's first two checks, per request: the page greys
    its controls where a write would be refused anyway.

    **Fix round 1, Important 5.** Pinned on the rendered controls themselves, not
    only `data-can-write`: a grayed control carries `disabled` right beside its
    `data-cmd`, a live one does not -- `data-can-write` alone never proved the
    *controls* actually reflect it. **Important 1's own case, restated on the page
    render**: a peer that is not the box, under a `Host` (`localhost`) that would
    otherwise pass -- it short-circuits `names_loopback` before `on_box` is ever
    called -- still may not write."""
    hub = _hub()
    hub.offer(frame())
    with _served(hub, hosts=LOOPBACK_NAMES | {"rig3.lab"}) as port:
        box = _request(port, "GET", "/")[2].decode("utf-8")
        lan = _request(port, "GET", "/", {"Host": f"rig3.lab:{port}"})[2].decode("utf-8")

    assert 'data-can-write="1"' in box
    assert 'data-can-write="0"' in lan
    assert 'data-cmd="pause">' in box, "the box's own page has a live control"
    assert 'data-cmd="pause" disabled' in lan, "a LAN viewer's controls are grayed"

    monkeypatch.setattr(serve, "on_box", lambda host: False)
    other = _hub()
    other.offer(frame())
    with _served(other) as port:
        peer = _request(port, "GET", "/", {"Host": f"localhost:{port}"})[2].decode("utf-8")

    assert 'data-can-write="0"' in peer
    assert 'data-cmd="pause" disabled' in peer


def test_a_stream_on_the_boxs_page_renders_controls_that_work():
    hub = Hub(steady=_Clock(0.0), endpoint=ENDPOINT, marks=True)
    hub.offer(frame())
    with _served(hub) as port, _stream(port) as response:
        first = next(_events(response))

    controls = first["frags"]["controls"]
    assert 'data-cmd="pause"' in controls
    # Every control but the manual reward, which waits for a pause (Task 13).
    assert controls.count(" disabled") == 1
    assert 'data-cmd="reward" disabled' in controls


# --- P4d-2b b2a: the outboxes, where each ZMQ socket has its one thread ---------------


class _Sender:
    """A sender that answers its work, and a way to hold it mid-work."""

    def __init__(self) -> None:
        self.thread = None
        self.release = threading.Event()
        self.release.set()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _outbox(build, depth: int = 2) -> tuple[Outbox, threading.Event]:
    stop = threading.Event()
    outbox = Outbox("test-outbox", build, depth, stop)
    outbox.start()
    return outbox, stop


def _submitted(outbox: Outbox, work, seconds: float = 10.0) -> tuple[int, dict]:
    """`outbox.submit(work)` on a thread of its own, and its answer within `seconds`;
    fails the test otherwise. `submit` waits for as long as the outbox's thread
    lives, so a job that thread never answers -- the defect these tests exist to
    catch -- would hang the test on its own thread rather than fail it: with
    `Outbox._answer` neutered, the mutation harness ran out its 300 s and printed
    `timed out`, which no test noticed (`docs/next-session.md`: the fix is a bound)."""
    answers: list = []
    thread = threading.Thread(
        target=lambda: answers.append(outbox.submit(work)), daemon=True
    )
    thread.start()
    thread.join(timeout=seconds)
    assert answers, f"the outbox did not answer within {seconds} s"
    return answers[0]


def test_an_outbox_builds_its_sender_on_its_own_thread_and_answers_each_job():
    sender = _Sender()

    def build():
        sender.thread = threading.current_thread().name
        return sender

    outbox, stop = _outbox(build)
    try:
        answer = _submitted(
            outbox, lambda built: (200, {"status": "sent", "said": built.thread})
        )
    finally:
        stop.set()
        outbox.thread.join(timeout=5)

    assert answer == (200, {"status": "sent", "said": "test-outbox"})
    assert sender.closed, "the sender is closed on its thread when the outbox stops"


def test_a_full_outbox_answers_busy_at_once_and_every_queued_job_is_answered():
    """Review Focus 1: a flood -- a double click, a held key, a stuck page -- fills
    the queue, and what does not fit is answered *busy* at once, never queued without
    bound and never left hanging."""
    sender = _Sender()
    sender.release.clear()
    outbox, stop = _outbox(lambda: sender, depth=2)
    in_hand = threading.Event()

    def held(built):
        in_hand.set()
        built.release.wait(10)
        return 200, {"status": "sent", "said": "held"}

    answers: list = []

    def submit() -> None:
        answers.append(outbox.submit(held))

    threads = [threading.Thread(target=submit, daemon=True) for _ in range(3)]
    try:
        # One job in the thread's hands first, then two to fill the queue behind it.
        # Started together, the third could find the queue full before the thread had
        # taken the first, and be the one told *busy* (seen once, on a loaded machine).
        threads[0].start()
        assert in_hand.wait(5.0), "the outbox thread never took the first job"
        threads[1].start()
        threads[2].start()
        assert _until(lambda: outbox._queue.full(), 5.0), "one in hand and two waiting"
        started = time.monotonic()
        busy = outbox.submit(held)
        assert time.monotonic() - started < 1.0, "busy is said at once"
        sender.release.set()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        sender.release.set()
        stop.set()
        outbox.thread.join(timeout=5)

    assert busy == BUSY
    assert answers == [(200, {"status": "sent", "said": "held"})] * 3


def test_an_outbox_whose_sender_cannot_be_built_says_so_to_every_job():
    def build():
        raise RuntimeError("no such endpoint")

    outbox, stop = _outbox(build)
    try:
        answer = _submitted(outbox, lambda built: (200, {}))
    finally:
        stop.set()
        outbox.thread.join(timeout=5)

    assert answer == (
        504,
        {
            "status": "not_delivered",
            "said": "not delivered: wlx serve could not reach the rig (RuntimeError: no such endpoint)",
        },
    )


def test_work_that_raises_is_answered_not_delivered():
    outbox, stop = _outbox(_Sender)
    try:

        def raises(built):
            raise ValueError("socket gone")

        answer = _submitted(outbox, raises)
    finally:
        stop.set()
        outbox.thread.join(timeout=5)

    assert answer == (504, {"status": "not_delivered", "said": "not delivered: ValueError: socket gone"})


def test_a_job_submitted_to_a_stopped_outbox_is_answered_not_delivered():
    outbox, stop = _outbox(_Sender)
    stop.set()
    outbox.thread.join(timeout=5)

    assert _submitted(outbox, lambda built: (200, {}))[1]["said"] == (
        "not delivered: wlx serve is closing"
    )


def test_a_job_answered_just_as_its_thread_exits_is_not_reported_closing(monkeypatch):
    """Fix round 1, Important 4. `submit`'s wait loop timed out and then read
    `self.thread.is_alive()` as `False` -- true whenever the thread answered a job
    and then exited between the two checks -- and reported the job *closing*
    even though it had a real answer.

    Reproduced deterministically, with no real thread or timing dependency: a
    `threading.Event` standing in for `job.done` reports the timeout `wait`'s
    caller actually saw, but -- as a departing thread's very last act would --
    lands the job's answer and its own `set()` before returning that `False`. A
    `thread` double whose `is_alive()` is always `False` stands in for "the
    thread has already exited" without ever starting or stopping a real one."""
    answer = (200, {"status": "sent", "said": "answered just in time"})

    class _RacyDone(threading.Event):
        def wait(self, timeout=None) -> bool:
            job.answer = answer
            self.set()
            return False  # the timeout `submit`'s caller actually observed

    class _DeadThread:
        def is_alive(self) -> bool:
            return False

    outbox = Outbox("test-outbox", lambda: None, 2, threading.Event())
    outbox.thread = _DeadThread()
    job = serve._Job(lambda built: None)
    job.done = _RacyDone()
    monkeypatch.setattr(serve, "_Job", lambda work: job)

    assert outbox.submit(lambda built: None) == answer


def _until(predicate, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


# --- P4d-2b b2a: the Server's command and mark threads, on real sockets ---------------


def _rig(zmq_cleanup) -> ZmqLink:
    return zmq_cleanup(
        ZmqLink(
            pub_endpoint="tcp://127.0.0.1:0",
            rep_endpoint="tcp://127.0.0.1:0",
            mark_endpoint="tcp://127.0.0.1:0",
        )
    )


def _drained(link, until, seconds: float = 10.0) -> tuple[threading.Thread, list]:
    got: list = []

    def run() -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and until not in got:
            got.extend(link.drain())
            time.sleep(0.005)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, got


def test_a_command_is_sent_when_the_rig_acknowledges_it(zmq_cleanup, server_cleanup):
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(sub=rig.pub_endpoint, req=rig.rep_endpoint, http=("127.0.0.1", 0), token=TOKEN)
    )
    server.start()
    try:
        thread, got = _drained(rig, Pause(by="jake (box, unverified)"))
        status, answer = _post(server.address[1], {"kind": "pause", "by": "jake"})
        thread.join(timeout=15)
    finally:
        server.close()

    assert (status, answer["status"]) == (200, "sent")
    assert got == [Pause(by="jake (box, unverified)")]


def test_with_taskd_gone_the_page_is_told_not_delivered(zmq_cleanup, server_cleanup):
    """Spec §5.4: with `taskd` gone, the page is told *not delivered* -- once the
    connect timeout passes, since there is no rig to wait a reply from."""
    probe = _rig(zmq_cleanup)
    pub, rep = probe.pub_endpoint, probe.rep_endpoint
    probe.close()
    server = server_cleanup(
        Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN, connect_timeout_s=0.2)
    )
    server.start()
    try:
        status, answer = _post(server.address[1], {"kind": "stop", "by": "jake"})
    finally:
        server.close()

    assert status == 504
    assert answer == {
        "status": "not_delivered",
        "said": f"not delivered: no rig is connected on {rep}",
    }


def _drained_any(link, kind, seconds: float = 10.0) -> tuple[threading.Thread, list]:
    """Drain `link` on a thread until a command of type `kind` arrives."""
    got: list = []

    def run() -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not any(isinstance(c, kind) for c in got):
            got.extend(link.drain())
            time.sleep(0.005)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, got


def test_a_mark_goes_ahead_of_a_command_waiting_on_the_rig(zmq_cleanup, server_cleanup):
    """Spec §5.3: the mark's signal goes on its own path, as soon as it arrives,
    ahead of the queue -- here, ahead of a pause the rig has not acknowledged,
    because nothing drains it -- and the note that follows it carries the instants
    `wlx serve` kept for that mark: the browser's `pressed_at`, and when this process
    received the signal, on its own clock."""
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(
            sub=rig.pub_endpoint,
            req=rig.rep_endpoint,
            mark=rig.mark_endpoint,
            http=("127.0.0.1", 0),
            token=TOKEN,
            reply_timeout_s=2.0,
        )
    )
    server.start()
    port = server.address[1]
    waiting: list = []
    pause = threading.Thread(
        target=lambda: waiting.append(_post(port, {"kind": "pause", "by": "sam"})),
        daemon=True,
    )
    try:
        pause.start()
        time.sleep(0.2)
        before = time.time()
        started = time.monotonic()
        status, answer = _post(port, {"kind": "mark", "by": "jake", "pressed_at": 1_700_000_000.5})
        took = time.monotonic() - started
        after = time.time()
        signalled = 0
        for _ in range(400):
            signalled = rig.mark_signal()
            if signalled:
                break
            time.sleep(0.005)
        pause.join(timeout=10)

        thread, got = _drained_any(rig, Mark)
        noted = _post(port, {"kind": "note", "by": "jake", "mark": answer["mark"], "note": "bubble"})
        thread.join(timeout=15)
    finally:
        server.close()

    assert (status, answer["status"]) == (200, "signaled")
    assert took < 1.5, "the mark waited behind the pause"
    assert 1 <= answer["mark"] <= MARK_ID_LIMIT
    assert signalled == answer["mark"]
    assert waiting and waiting[0][0] == 504, "the pause was never acknowledged"
    assert noted[0] == 200
    (note,) = [command for command in got if isinstance(command, Mark)]
    assert (note.mark, note.note, note.by) == (answer["mark"], "bubble", "jake (box, unverified)")
    assert note.pressed_at == 1_700_000_000.5
    assert before <= note.received_at <= after


def test_a_console_without_the_mark_endpoint_says_a_mark_is_not_delivered(
    zmq_cleanup, server_cleanup
):
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(sub=rig.pub_endpoint, req=rig.rep_endpoint, http=("127.0.0.1", 0), token=TOKEN)
    )
    server.start()
    try:
        status, answer = _post(server.address[1], {"kind": "mark", "by": "jake"})
    finally:
        server.close()

    assert status == 504
    assert answer["said"] == f"not delivered: {NO_MARK_ENDPOINT}"
    assert server._marks is None


def test_a_note_for_a_mark_this_console_does_not_know_carries_no_instants(
    zmq_cleanup, server_cleanup
):
    """Review Focus 5's neighbor: a `wlx serve` restarted between a mark and its note
    knows neither instant, and says so with `None` rather than inventing one."""
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(sub=rig.pub_endpoint, req=rig.rep_endpoint, http=("127.0.0.1", 0), token=TOKEN)
    )
    server.start()
    try:
        thread, got = _drained_any(rig, Mark)
        status, _ = _post(server.address[1], {"kind": "note", "by": "jake", "mark": 42, "note": ""})
        thread.join(timeout=15)
    finally:
        server.close()

    assert status == 200
    assert got == [Mark(mark=42, note="", by="jake (box, unverified)", pressed_at=None, received_at=None)]


def test_the_marks_kept_for_their_notes_are_the_newest_and_each_is_given_once():
    server = Server(sub=ENDPOINT, req="tcp://127.0.0.1:1", http=("127.0.0.1", 0), token=TOKEN)
    try:
        for number in range(1, MARKS_REMEMBERED + 2):
            server._remember(number, None, float(number))

        assert server._recall(1) == (None, None), "the oldest was let go"
        assert server._recall(MARKS_REMEMBERED + 1) == (None, float(MARKS_REMEMBERED + 1))
        assert server._recall(MARKS_REMEMBERED + 1) == (None, None), "given once"
    finally:
        server.close()


def test_closing_the_server_stops_its_command_and_mark_threads(zmq_cleanup, server_cleanup):
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(
            sub=rig.pub_endpoint,
            req=rig.rep_endpoint,
            mark=rig.mark_endpoint,
            http=("127.0.0.1", 0),
            token=TOKEN,
        )
    )
    server.start()
    assert server._commands.thread.is_alive() and server._marks.thread.is_alive()

    started = time.monotonic()
    server.close()

    assert time.monotonic() - started < 2.0
    assert not server._commands.thread.is_alive()
    assert not server._marks.thread.is_alive()


def test_wlx_serve_takes_the_mark_endpoint_and_the_allowed_hosts(tmp_path, monkeypatch):
    seen: dict = {}

    def stop_at_construction(self, **kwargs) -> None:
        seen.update(kwargs)
        raise OSError("stopped here by the test")

    monkeypatch.setattr(Server, "__init__", stop_at_construction)

    with pytest.raises(SystemExit, match="stopped here by the test"):
        main(
            _serve_args(
                tmp_path,
                link="tcp://127.0.0.1:5571,tcp://127.0.0.1:5572,tcp://127.0.0.1:5573",
                extra=("--allow-host", "rig3.lab", "--allow-host", "rig3"),
            )
        )

    assert seen["mark"] == "tcp://127.0.0.1:5573"
    assert seen["allow_hosts"] == ("rig3.lab", "rig3")


# --- Task 1 review ledger: an integer too large for a float ---------------------------


def test_a_setting_whose_integer_overflows_a_float_is_refused_not_raised():
    """Task 1's review, ledgered for this task: `link._setting`'s
    `math.isfinite(value)` raises `OverflowError` on a Python int too large to
    become a `float` (`10**400`, say). msgpack cannot carry one, but
    `serve.parse_command` decodes a JSON body, whose integers Python reads without
    bound, so a `POST /commands` setting this large can still reach it -- refused
    with a sentence, never a 500 or a dead thread, the session (this console's own
    serving) running on."""
    digits = str(10**400)
    body = (
        '{"kind": "set", "by": "jake", "name": "fix_hold", "value": '
        f"{digits}}}"
    ).encode("ascii")
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(port, body)
        still_serving = _request(port, "GET", "/")[0]

    assert status == 400
    assert answer["status"] == "refused"
    assert "not a real number" in answer["said"]
    assert "the session runs on" in answer["said"]
    assert dispatch.seen == []
    assert still_serving == 200


# --- P4d-2b b2a end to end: a real `wlx run --link`, a real `wlx serve`, and POST
# /commands the way the page sends them (spec §5.4) ----------------------------------

#: The three framework codes b2a allocates (`tasks/allocation.py`), and the first code
#: `fixation_detection` strobes in a trial.
PAUSE_CODE, RESUME_CODE, MARK_CODE, FIX_ON = 4131, 4132, 4133, 4096
#: `fixation_detection`'s trial-ending markers (`codes._standing_outcomes`).
MARKERS = {34, 35, 36, 37, 38}

#: **Ruling 10, sized for these sessions.** Each one below is ended by the page's
#: `stop`, its schedule or its limit within about a hundred trials: 27 to 84 over three
#: runs of these twelve tests in the plan's pre-flight, 2026-09-27. b1's
#: `E2E_TRIAL_BUDGET` is sized for b1's session, which has no mark socket; a session
#: with one runs fewer trials a second in the simulator, every frame paying for the
#: mark check Task 14 measures. There, b1's 20,000 trials took about 20 s without one,
#: and 1,000 took a few seconds with one (scratch readings on one loaded machine, not
#: claims about this system). Under b1's budget, a mutant that breaks the command path
#: -- `taskd.Session._command` neutered -- held each of these tests past 50 s, its 20 s
#: frame wait and then its 30 s join, and the suite past the mutation harness's 300 s:
#: a timeout, which no test noticed.
#:
#: **400, with each trial paced** (after `main`'s run `36497082927`, 2026-09-29). There,
#: the mark end to end failed once in a restore run, on unmutated code, with "wlx run
#: had ended": the budget ran out before the console showed what the test waited for.
#: The simulator runs trials unpaced, a few hundred frames a second, and `wlx serve`'s
#: telemetry thread handles every frame in turn. So a runner slow enough leaves the
#: console's latest frame behind a session producing at nearly the rate the thread can
#: take, and it may not catch up before the budget ends the session. Scratch probes
#: on copies of the tree, 2026-09-29, two runs each of the thirteen end to end tests:
#: - unpaced, with every frame the console takes delayed 20 ms, failed 3 and then 1;
#: - paced at 5 ms, under the same delay, failed none.
#: Each sleep also releases the GIL to the threads a test's commands pass through. The
#: budget comes down with the pacing so that a broken command path still fails these
#: tests in a few seconds. With `taskd.Session._command` mutated, the harness's run
#: took 171 s paced and 155 s unpaced locally, against its 300 s limit.
CONTROL_TRIAL_BUDGET = 400

#: How long each trial of these sessions sleeps before it runs (see
#: `CONTROL_TRIAL_BUDGET`). Housekeeping for the simulator, not a trial duration.
CONTROL_TRIAL_PACE_S = 0.005

#: How long `_Session.frame` still waits once `wlx run` has ended, for the last frame
#: it published to reach the console.
LAST_FRAME_S = 2.0


def _three_endpoints(zmq_cleanup) -> tuple[str, str, str]:
    """A free PUB/REP/mark triple on loopback, bound by a throwaway link and released."""
    probe = _rig(zmq_cleanup)
    endpoints = probe.pub_endpoint, probe.rep_endpoint, probe.mark_endpoint
    probe.close()
    return endpoints


class _Session:
    """A real simulated `wlx run --link PUB,REP,MARK` on a thread, the `Server` beside
    it, and what a test reads them through: the latest frame the console holds, every
    frame the session published, the card the session strobed onto (captured as `wlx
    run` builds it), and the record.

    **Every frame, on this test's own SUB socket** (the b2a final fix wave). The
    console holds only the latest frame, so a state that lasts one frame -- a setting
    staged at one boundary and applied at the next -- can come and go between two
    looks. On CI's two-vCPU runners it did, with the simulated rig competing for the
    GIL (runs `36453778281` and `36435219146`). `recorder` connects before `wlx run`
    binds, **but a SUB receives only what is published after its subscription has
    joined**, which happens some time after the bind, on libzmq's reconnect timer. So
    a test reading `frames` first waits with `seen` for any frame, which proves the
    subscription is live, before it sends anything. From then on libzmq queues what
    arrives on its own I/O thread, with no GIL, up to the socket's high-water mark:
    1,000 messages, pyzmq 27.2.0 and libzmq 4.3.5's default as read in this venv on
    2026-09-28. A session here publishes one frame per boundary. Only `seen` reads
    `recorder`, so a test that uses it does its waiting on the console with `frame`
    and reads the recorder afterwards; what it reads is bounded by how few trials the
    session runs before the test stops it."""

    def __init__(self, tmp_path, monkeypatch, zmq_cleanup, *, bounds=TWELVE_HOURS,
                 session_id="2027-01-14_21", cleanup=None):
        from wl_xcon import dio

        _trial_budget(monkeypatch, CONTROL_TRIAL_BUDGET, pace_s=CONTROL_TRIAL_PACE_S)
        self.cards: list = []
        cards = self.cards

        class _KeptCard(dio.Simulated):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                cards.append(self)

        monkeypatch.setattr(dio, "Simulated", _KeptCard)
        self.pub, self.rep, self.mark = _three_endpoints(zmq_cleanup)
        self.root = tmp_path
        self.session_id = session_id
        self.bounds = bounds
        #: The departure `wlx run` is given, read once, here, with its date (the b2a
        #: final fix wave). `wlx run` used to read `%H:%M` itself, later, on its own
        #: thread, so a test that worked a duration out from its own reading could
        #: straddle a minute -- the flake `403de3c` fixed in `tests/test_cli.py` -- or
        #: midnight, where a bare clock time names a moment later today and is refused
        #: as in the future (`cli._wall_clock_time`).
        self.departure = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.zmq_cleanup = zmq_cleanup
        self.cleanup = cleanup
        self.result: dict = {}
        self.recorder = zmq_cleanup(
            ZmqConsole(self.pub, None, settle_s=0.0, receive_timeout_s=0.0)
        )
        #: Every frame `recorder` has received, in the order it was published.
        self.frames: list = []
        #: Where `seen` looks from: the last frame it returned.
        self._looked = 0
        self.server = self.serve()
        self.runner = threading.Thread(target=self._run, daemon=True)

    def serve(self) -> Server:
        server = Server(
            sub=self.pub, req=self.rep, mark=self.mark, http=("127.0.0.1", 0), token=TOKEN
        )
        if self.cleanup is not None:
            self.cleanup(server)
        server.start()
        return server

    def _run(self) -> None:
        self.result["exit_code"] = _main_uninterrupted(
            [
                "run", GOOD,
                *_SETUP,
                "--allocation", ALLOCATION,
                "--bounds", str(self.bounds),
                "--root", str(self.root),
                "--session-id", self.session_id,
                "--subject", "REFERENCE",
                "--out-of-cage-at", self.departure,
                "--delivered-today", "0",
                "--trials", "100000",
                *_TASK_SETS,
                "--link", f"{self.pub},{self.rep},{self.mark}",
            ]
        )

    def __enter__(self) -> "_Session":
        self.runner.start()
        return self

    def __exit__(self, *exc_info) -> None:
        # Fix round 1, M6's rescue, as in the b1 end to end: a session still running
        # when a test ends is stopped at its next boundary, not left to its budget.
        if self.runner.is_alive():
            try:
                with self.zmq_cleanup(ZmqConsole(self.pub, self.rep)) as rescue:
                    rescue.send(Stop(by="e2e-cleanup"))
            except Exception:  # noqa: BLE001 -- best-effort cleanup
                pass
        self.runner.join(timeout=30)
        self.server.close()

    def post(self, body: dict):
        return _post(self.server.address[1], body)

    def frame(self, predicate, seconds: float = 20.0):
        """The first frame this console holds for which `predicate` is true, within
        `seconds`; fails the test otherwise -- and within `LAST_FRAME_S` once `wlx
        run` has ended, since no frame comes after that: a session a mutant ended
        early fails its test then, rather than after the full wait."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            latest = self.server.hub.snapshot(on_box=True, stale_after_s=30.0)[0]
            if latest is not None and predicate(latest):
                return latest
            if not self.runner.is_alive():
                deadline = min(deadline, time.monotonic() + LAST_FRAME_S)
            time.sleep(0.01)
        ended = "" if self.runner.is_alive() else "; wlx run had ended"
        raise AssertionError(f"no frame within {seconds} s satisfied {predicate}{ended}")

    def seen(self, predicate, seconds: float = 20.0):
        """The first frame `wlx run` published, from the last one this returned on, for
        which `predicate` is true, read from `recorder` -- so a state that lasted one
        frame is found however long this thread was kept from looking. Fails as
        `frame` does otherwise, and as soon, once `wlx run` has ended and every frame
        it published has been read.

        **One frame at a time, each checked as it arrives.** It used to drain every
        waiting frame before checking any, and `frame` drained too. On CI, decoding
        fell behind publishing, so a wait returned only once the recorder caught up.
        That could be hundreds of trials after the frame it wanted, or never before
        `CONTROL_TRIAL_BUDGET` ended the session: runs `36477904368` and
        `36477917775`, which failed the staged/applied test on every attempt."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            while self._looked < len(self.frames):
                if predicate(self.frames[self._looked]):
                    return self.frames[self._looked]
                self._looked += 1
            try:
                self.frames.append(self.recorder.receive())
                continue
            except TimeoutError:
                pass
            if not self.runner.is_alive():
                deadline = min(deadline, time.monotonic() + LAST_FRAME_S)
            time.sleep(0.005)
        ended = "" if self.runner.is_alive() else "; wlx run had ended"
        raise AssertionError(
            f"no frame published within {seconds} s satisfied {predicate}{ended}"
        )

    def ended(self):
        return self.frame(lambda f: f.stop_kind is not None)

    def controls(self) -> list[dict]:
        path = Path(self.root) / self.session_id / "xcon" / "controls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def finished(self) -> None:
        self.runner.join(timeout=30)
        assert not self.runner.is_alive(), "wlx run did not finish"
        assert "exit_code" in self.result, "wlx run's thread raised before main() returned"


def test_e2e_a_setting_is_staged_then_applied_at_the_next_trial(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """S9a §8 end to end: the page's setting is staged at the boundary that drains it,
    with the old value still in force, and applied at the next one -- the next trial's
    frame -- and the feed says who changed it.

    **Read from every frame the session published** (`_Session.seen`; the b2a final
    fix wave). The staged row is on one frame, a single trial of simulated time, and
    polling the console's latest frame missed it on CI's two-vCPU runners. That is
    also what lets this say *the next trial* rather than *some later frame*.

    **But the waiting is done on the console, and the recorder is read afterwards**
    (after runs `36477904368` and `36477917775`). The applied value holds still, so
    the console cannot miss it, and the stop goes as soon as it is there. Read while
    the session ran, the recorder lagged it on CI, and the stop went out after the
    trial budget had ended the session."""

    def applied_value(frame):
        return any(p.name == "fix_hold" and p.value == 0.4 for p in frame.params)

    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        # The recorder's first frame: its subscription is live, so nothing the POST
        # causes is published before it can hear it.
        run.seen(lambda f: True)
        assert run.post({"kind": "set", "by": "jake", "name": "fix_hold", "value": 0.4})[0] == 200
        run.frame(applied_value)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
        staged = run.seen(lambda f: any(s.name == "fix_hold" for s in f.staged))
        applied = run.seen(applied_value)
        (row,) = staged.staged
        assert (row.name, row.was, row.now, row.by) == (
            "fix_hold", 0.3, 0.4, "jake (box, unverified)"
        )
        assert any(p.name == "fix_hold" and p.value == 0.3 for p in staged.params)
        assert not applied.staged
        assert applied.trial_index == staged.trial_index + 1
        assert any(
            c.kind == "set" and c.by == "jake (box, unverified)" and c.said.startswith("fix_hold 0.30 → 0.40")
            for c in applied.controls
        )
    run.finished()


def test_e2e_a_malformed_setting_is_refused_on_the_feed_and_the_session_runs_on(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """M8, end to end: a word sent for a numeric parameter is a categorical choice on
    the wire, so it reaches the rig, where it once raised `TypeError` out of
    `bounds._finite` and ended the session. Now it is a refusal with a sentence on the
    feed, and trials go on."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        before = run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "set", "by": "jake", "name": "fix_hold", "value": "abc"})[0] == 200
        refused = run.frame(lambda f: any(r.name == "fix_hold" for r in f.refusals))
        (refusal,) = [r for r in refused.refusals if r.name == "fix_hold"]
        assert refusal.by == "jake (box, unverified)"
        assert "'fix_hold' takes a number (s)" in refusal.why
        run.frame(lambda f: f.trial_index > refused.trial_index + 2)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        assert run.ended().stop_kind == "operator"
        assert before.stop_kind is None
    run.finished()


def test_e2e_pause_holds_the_trial_count_keeps_the_clock_and_resume_continues(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 2)
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        first = run.frame(lambda f: f.paused_at is not None)
        later = run.frame(
            lambda f: f.paused_at is not None
            and f.out_of_cage_seconds >= first.out_of_cage_seconds + 1.0
        )
        assert later.trial_index == first.trial_index, "a trial ran while paused"
        assert run.post({"kind": "resume", "by": "sam"})[0] == 200
        run.frame(lambda f: f.paused_at is None and f.trial_index > first.trial_index)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()
    codes = run.cards[0].codes
    assert codes.count(PAUSE_CODE) == 1 and codes.count(RESUME_CODE) == 1
    assert codes.index(RESUME_CODE) == codes.index(PAUSE_CODE) + 1
    kinds = [row["kind"] for row in run.controls()]
    assert kinds == ["pause", "resume", "stop"]


def test_e2e_the_limit_ends_a_session_paused_in_front_of_it(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §5.4 and human review item 1: pause, and the out-of-cage limit still
    arrives and ends the session, mid-pause.

    **The limit is an hour away, and the session's wall is moved to it once the pause
    holds** (the b2a final fix wave). It used to be real, six seconds past the
    departure, and `wlx run`'s start, a first trial, the pause's POST and the pause
    itself all had to beat it -- a margin a slow enough runner does not have -- with
    the departure read by this test and by `wlx run` at two different moments. Here
    nothing races. `taskd`'s `SessionClock` -- the wall the session reads every
    welfare duration on, `welfare.SessionClock` unchanged underneath -- is a subclass
    that adds the offset this test sets, and it sets one only after the pause holds.
    The paused session then finds the limit where it would an hour on: `_hold` asks
    `_ends`, which asks `welfare.must_stop` on the session's own wall."""
    from wl_xcon import taskd

    ahead = [0.0]

    class _Steered(taskd.SessionClock):
        def now(self) -> float:
            return super().now() + ahead[0]

    monkeypatch.setattr(taskd, "SessionClock", _Steered)
    limit = 3600.0
    bounds = tmp_path / "short_bounds.py"
    bounds.write_text(
        "from wl_xcon.bounds import Bounds, Ceiling, Floor\n"
        "BOUNDS = Bounds(subject='REFERENCE', ceilings={"
        "'reward_correct': Ceiling(value=0.05, maximum=10.0, unit='mL'), "
        f"'out_of_cage': Ceiling(value={limit!r}, maximum=43200.0, unit='s')}}, "
        "minima={'daily_fluid': Floor(value=20.0, unit='mL')})\n",
        encoding="utf-8",
    )
    with _Session(tmp_path, monkeypatch, zmq_cleanup, bounds=bounds, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        paused = run.frame(lambda f: f.paused_at is not None)
        ahead[0] = limit
        ended = run.ended()
    run.finished()

    assert paused.stop_kind is None and paused.out_of_cage_seconds < limit
    assert ended.stop_kind == "limit"
    assert ended.trial_index == paused.trial_index, "the limit ended it while paused"
    assert ended.paused_at == paused.paused_at, "it ended in the pause it was in"
    assert ended.out_of_cage_seconds > limit


def test_e2e_a_mark_is_strobed_in_its_trial_and_recorded_with_three_instants_and_a_note(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §5.4: a mark puts `OPERATOR_MARK` into the recorded event stream -- the
    card `wlx run` strobed onto -- where its stamp says it arrived, and the record
    holds its three instants, their gaps, and its note."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 2)
        pressed = time.time()
        status, signal = run.post({"kind": "mark", "by": "jake", "pressed_at": pressed})
        assert (status, signal["status"]) == (200, "signaled")
        run.frame(lambda f: any(c.kind == "mark" for c in f.controls))
        # **Paused once the stamp has landed** (the b2a final fix wave's residual). The
        # mark itself must go while trials run, since where it is strobed is the claim;
        # the note and the stop need not. Sent while trials ran, they left the session
        # three HTTP round trips to outlast `CONTROL_TRIAL_BUDGET`, and one CI run
        # (`36435219146`, mutation job) ended it first ("wlx run had ended"). Paused,
        # no trial is spent however slowly they arrive.
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        run.frame(lambda f: f.paused_at is not None)
        assert run.post({"kind": "note", "by": "jake", "mark": signal["mark"], "note": "sneeze"})[0] == 200
        run.frame(lambda f: any(c.kind == "note" for c in f.controls))
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()

    stamp, pause, note, stop = run.controls()
    assert pause["kind"] == "pause"
    assert (stamp["kind"], stamp["mark"], stamp["number"]) == ("mark", signal["mark"], 1)
    assert (stop["kind"], stop["by"]) == ("stop", "jake (box, unverified)")
    codes = run.cards[0].codes
    assert codes.count(MARK_CODE) == 1
    starts = [i for i, code in enumerate(codes) if code == FIX_ON]
    at = codes.index(MARK_CODE)
    trial_start = starts[stamp["trial_index"]]
    if stamp["frame"] is None:
        assert at < trial_start, "stamped between trials, strobed before the trial"
        assert stamp["trial_index"] == 0 or at > starts[stamp["trial_index"] - 1]
    else:
        trial_end = next(i for i in range(trial_start, len(codes)) if codes[i] in MARKERS)
        assert trial_start < at < trial_end, "strobed inside the trial its stamp names"
    assert note["note"] == "sneeze" and note["by"] == "jake (box, unverified)"
    assert note["pressed_at"] == pressed
    assert pressed <= note["received_at"] <= note["stamped_at"] + 60.0
    assert note["received_after_pressed_s"] == pytest.approx(note["received_at"] - pressed)
    assert note["stamped_after_received_s"] == pytest.approx(
        note["stamped_at"] - note["received_at"]
    )


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"trials": 3}, "scheduled stop (after trial {target}) set by jake (box, unverified)"),
        (None, "scheduled stop (after {target:g} mL this session) set by jake (box, unverified)"),
        ({"at": "00:00"}, "scheduled stop (at 00:00{day}) set by jake (box, unverified)"),
    ],
    ids=["trials", "fluid", "clock"],
)
def test_e2e_each_kind_of_scheduled_stop_ends_the_session_with_its_reason(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup, body, reason
):
    """Spec §5.4. The clock kind's next occurrence is made a quarter second away
    (`taskd._next_occurrence`, in this process, where `wlx run` runs): a real minute
    is too long for the suite, and what that function computes is pinned on its own
    in `tests/test_taskd.py`. Everything else is real -- the page's POST, `wlx
    serve`'s command thread, the wire, and the session's anchored clock."""
    from wl_xcon import taskd

    monkeypatch.setattr(taskd, "_next_occurrence", lambda hhmm, wall: wall + 0.25)
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        running = run.frame(lambda f: f.trial_index >= 1)
        if body is None:
            # **The fluid case is scheduled while paused** (the b2a final fix wave).
            # It schedules relative to the session's total, as an operator would,
            # and `taskd` refuses an "after X mL" schedule the session has already
            # reached (Task 7 fix round 1). Scheduled while trials ran, 1.0 mL above
            # the last frame -- about twenty correct trials here -- was already
            # behind on CI's two-vCPU runners by the time the command crossed HTTP,
            # the `Outbox` and the wire. Paused, the task rewards nothing, so the
            # total read from a paused frame is the total the schedule meets, and
            # any margin is ahead of it however slowly the command arrives.
            assert run.post({"kind": "pause", "by": "jake"})[0] == 200
            paused = run.frame(lambda f: f.paused_at is not None)
            body = {"ml": paused.fluid_session_ml + 5 * REWARD_ML}
            assert run.post({"kind": "schedule", "by": "jake", **body})[0] == 200
            # Acknowledged means drained, and a later command drains later.
            assert run.post({"kind": "resume", "by": "jake"})[0] == 200
        else:
            assert run.post({"kind": "schedule", "by": "jake", **body})[0] == 200
        ended = run.ended()
    run.finished()

    # A schedule that fired is spent, so the frames may never have shown it held;
    # the record has what it was.
    rows = run.controls()
    kinds = [row["kind"] for row in rows]
    if "ml" in body:
        assert kinds == ["pause", "schedule", "resume", "scheduled_stop"]
        schedule, fired = rows[1], rows[3]
    else:
        assert kinds == ["schedule", "scheduled_stop"]
        schedule, fired = rows
    day = schedule["said"][len("at 00:00"):] if "at" in body else ""
    if "trials" in body:
        target = int(schedule["target"])
    elif "ml" in body:
        target = schedule["target"]
    else:
        target = None
    assert ended.stop_kind == "operator"
    assert ended.stopped_because == reason.format(target=target, day=day)
    assert fired["by"] == "jake (box, unverified)"
    assert ended.scheduled_stop is None
    assert running.stop_kind is None
    if "ml" in body:
        assert ended.fluid_session_ml >= body["ml"] - taskd.FLUID_TOLERANCE_ML


def test_e2e_cancel_removes_the_scheduled_stop(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §5.4: a scheduled stop the page cancels is gone, and never fires.

    **Scheduled and cancelled while paused** (the b2a final fix wave). Scheduled while
    trials ran, thirty trials out, the stop fired before the cancel arrived on CI's
    two-vCPU runners, and the cancel then waited on a session that had ended until
    `_post` timed out. Paused, the target stands still between the schedule and the
    cancel however slowly either arrives; the resume after them is what shows the
    cancelled stop does not fire."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        running = run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        paused = run.frame(lambda f: f.paused_at is not None)
        assert run.post({"kind": "schedule", "by": "jake", "trials": 3})[0] == 200
        held = run.frame(lambda f: f.scheduled_stop is not None)
        assert run.post({"kind": "cancel", "by": "sam"})[0] == 200
        cancelled = run.frame(lambda f: f.scheduled_stop is None)
        assert run.post({"kind": "resume", "by": "jake"})[0] == 200
        past = run.frame(lambda f: f.trial_index > held.scheduled_stop.target + 5)
        assert past.stop_kind is None, "a cancelled schedule still stopped the session"
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()
    assert running.scheduled_stop is None
    assert held.scheduled_stop.target == paused.trial_index + 3
    assert cancelled.paused_at is not None and cancelled.stop_kind is None
    assert cancelled.trial_index == paused.trial_index
    kinds = [row["kind"] for row in run.controls()]
    assert kinds == ["pause", "schedule", "cancel", "resume", "stop"]


def test_e2e_a_write_from_elsewhere_is_refused_and_the_session_never_sees_it(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §5.4: a write from a non-loopback peer, or to an unknown `Host`, is
    refused -- and never reaches the rig: no control, no refusal, no strobe.

    **Task 11's review.** The "not the box" request is posted with explicit `Host`
    and `Origin` headers naming `localhost`, not `_post`'s default loopback IP
    literal: `names_loopback` also calls `on_box` (serve.py), so with the default
    `Host` the `Host` check would refuse the request on its own, whether or not
    `may_write`'s own peer check (`on_box(self.client_address[0])`) were even there.
    `names_loopback("localhost")` is `True` on the literal alone, short-circuiting
    before it ever calls `on_box`, so only the peer check can produce the 403 this
    test asserts -- the same shape as `test_a_write_from_a_peer_that_is_not_the_box_is_refused`.
    """
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        port = run.server.address[1]
        wrong_host = _post(port, {"kind": "pause", "by": "mallory"}, {"Host": "evil.example"})
        with monkeypatch.context() as patch:
            patch.setattr(serve, "on_box", lambda host: False)
            not_the_box = _post(
                port,
                {"kind": "pause", "by": "mallory"},
                {"Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"},
            )
        after = run.frame(lambda f: f.trial_index >= 3)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()

    assert wrong_host[0] == 421
    assert not_the_box == (403, {"status": "refused", "said": CONTROLS_AT_THE_BOX})
    assert after.paused_at is None and after.refusals == () and after.controls == ()
    assert PAUSE_CODE not in run.cards[0].codes


def test_e2e_with_taskd_gone_the_page_is_told_not_delivered(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
        run.finished()
        status, answer = run.post({"kind": "pause", "by": "jake"})
        mark_status, mark = run.post({"kind": "mark", "by": "jake"})

    assert status == 504
    assert answer["said"] == f"not delivered: no rig is connected on {run.rep}"
    assert mark_status == 504
    assert mark["said"] == f"not delivered: no rig is listening for marks on {run.mark}"


def test_e2e_wlx_serve_restarted_while_paused_shows_it_paused_and_can_resume(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Review Focus 5: the pause is held by `taskd`, so a `wlx serve` restarted while
    the session is paused picks it up paused -- its page offers *resume* -- and the
    resume it sends continues the session."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        paused = run.frame(lambda f: f.paused_at is not None)
        run.server.close()

        run.server = run.serve()
        again = run.frame(lambda f: f.paused_at is not None)
        with _stream(run.server.address[1]) as response:
            first = next(_events(response))
        assert 'data-cmd="resume"' in first["frags"]["controls"]
        assert 'data-state="paused"' in first["frags"]["state"]
        assert again.trial_index == paused.trial_index
        assert run.post({"kind": "resume", "by": "jake"})[0] == 200
        run.frame(lambda f: f.paused_at is None and f.trial_index > paused.trial_index)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()


# --- P4d-2b b2a, amended 2026-09-28 (PI): a manual reward during a pause ---------------

#: `MANUAL_REWARD`'s code (`tasks/allocation.py`), after b2a's other three.
MANUAL_REWARD_CODE = 4134
#: `tasks/twelve_hour_bounds.py`'s `reward_correct`: what one press gives these sessions.
REWARD_ML = 0.05


class _Answers:
    """A command sender whose `deliver` records what it was handed and raises `raised`,
    or returns when that is `None`."""

    def __init__(self, raised: Exception | None) -> None:
        self.raised = raised
        self.sent: list = []

    def deliver(self, command) -> None:
        self.sent.append(command)
        if self.raised is not None:
            raise self.raised


@pytest.mark.parametrize(
    ("raised", "answer"),
    [
        (None, (200, {"status": "sent", "said": REWARD_SENT})),
        (
            Unacknowledged("not delivered: the rig did not acknowledge it within 15 s"),
            REWARD_UNKNOWN,
        ),
        (RuntimeError("socket gone"), REWARD_UNKNOWN),
        (
            NotDelivered("not delivered: no rig is connected on tcp://127.0.0.1:5572"),
            (
                504,
                {
                    "status": "not_delivered",
                    "said": (
                        "not delivered: no rig is connected on tcp://127.0.0.1:5572; "
                        "no reward was given"
                    ),
                },
            ),
        ),
    ],
    ids=["acknowledged", "unacknowledged", "failed-after-handing-over", "never-sent"],
)
def test_a_rewards_answer_is_sent_unknown_or_not_given_and_it_is_delivered_once(
    raised, answer
):
    """No accidental doubles (PI, 2026-09-28). A reward the rig acknowledged is *sent*;
    one it took and did not acknowledge -- or one whose send failed in a way that
    cannot say whether it went -- is *unknown*, never *not delivered*, which would
    invite the press that doubles it; only one that never left `wlx serve` is *not
    delivered*, and says no reward was given. Each is handed to the sender once."""
    sender = _Answers(raised)

    assert serve._rewarded(ManualReward(by="jake"))(sender) == answer
    assert sender.sent == [ManualReward(by="jake")]


def test_a_reward_the_rig_takes_and_never_acknowledges_is_unknown_and_sent_once(
    zmq_cleanup, server_cleanup
):
    """No accidental doubles, on real sockets (PI, 2026-09-28). The rig here is a ROUTER
    socket, which reads every message and answers none, so it sees each one `wlx
    serve` sends: one press is one POST and one reward command on the wire, and after
    the reply timeout the page is told *unknown* and nothing sends it again. If a
    retry is ever added to the command path, this is where it doubles a reward."""
    import zmq

    from wl_xcon.link import _decode_command

    telemetry = _rig(zmq_cleanup)
    ctx = zmq.Context()
    rig = ctx.socket(zmq.ROUTER)
    try:
        rig.setsockopt(zmq.LINGER, 0)
        port = rig.bind_to_random_port("tcp://127.0.0.1")
        server = server_cleanup(
            Server(
                sub=telemetry.pub_endpoint,
                req=f"tcp://127.0.0.1:{port}",
                http=("127.0.0.1", 0),
                token=TOKEN,
                reply_timeout_s=0.3,
            )
        )
        server.start()
        try:
            answer = _post(server.address[1], {"kind": "reward", "by": "jake"})
            seen: list = []
            # Several reply timeouts, and the command thread's reset, after the answer.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if rig.poll(50, zmq.POLLIN):
                    seen.append(rig.recv_multipart())
        finally:
            server.close()
    finally:
        rig.close(linger=0)
        ctx.term()

    assert answer == REWARD_UNKNOWN
    assert [_decode_command(frames[-1]) for frames in seen] == [
        ManualReward(by="jake (box, unverified)")
    ]


def test_e2e_a_reward_pressed_while_paused_is_one_correct_trial_reward_on_the_record(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """PI, 2026-09-28, end to end. While trials run, the page's *give reward* is greyed,
    and a press that reaches the rig anyway is refused on the feed. Paused, the button
    is live; the POST it sends crosses `wlx serve`'s command thread to the held
    session, which gives exactly one `reward_correct` -- and the next frame's fluid
    total, the page, `controls.jsonl` and the recorded event stream all show it, while
    the trial count stands still."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        port = run.server.address[1]
        running = run.frame(lambda f: f.trial_index >= 2)
        with _stream(port) as response:
            greyed = next(_events(response))["frags"]["controls"]
        assert run.post({"kind": "reward", "by": "jake"}) == (
            200, {"status": "sent", "said": REWARD_SENT}
        )
        refused = run.frame(lambda f: any(r.name == "reward" for r in f.refusals))
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        paused = run.frame(lambda f: f.paused_at is not None)
        with _stream(port) as response:
            live = next(_events(response))["frags"]["controls"]
        assert run.post({"kind": "reward", "by": "jake"})[0] == 200
        given = run.frame(lambda f: any(c.kind == "reward" for c in f.controls))
        with _stream(port) as response:
            shown = next(_events(response))["frags"]["controls"]
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        ended = run.ended()
    run.finished()

    assert running.stop_kind is None
    assert 'data-cmd="reward" disabled' in greyed
    (refusal,) = [r for r in refused.refusals if r.name == "reward"]
    assert refusal.by == "jake (box, unverified)"
    assert "the session is not paused" in refusal.why
    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in live
    assert given.paused_at is not None and given.trial_index == paused.trial_index
    assert given.fluid_session_ml == pytest.approx(paused.fluid_session_ml + REWARD_ML)
    assert f"fluid session {given.fluid_session_ml:.2f} mL" in shown
    assert ended.fluid_session_ml == pytest.approx(given.fluid_session_ml)
    assert ended.trial_index == paused.trial_index
    pause, reward, stop = run.controls()
    assert (pause["kind"], reward["kind"], stop["kind"]) == ("pause", "reward", "stop")
    assert reward["by"] == "jake (box, unverified)"
    assert (reward["ml"], reward["entry"]) == (REWARD_ML, "reward_correct")
    assert reward["trial_index"] == paused.trial_index
    assert reward["at"] == given.last_reward_at
    codes = run.cards[0].codes
    assert codes.count(MANUAL_REWARD_CODE) == 1
    at = codes.index(MANUAL_REWARD_CODE)
    assert codes.index(PAUSE_CODE) < at
    assert FIX_ON not in codes[at:], "no trial ran after the pause"
