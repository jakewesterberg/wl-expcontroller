"""`wlx serve` (P4d-2b slice b1): the hub, the HTTP surface, and the whole process.

Sim first: the end-to-end test runs a real `wlx run --link` in the simulator and a
real `wlx serve` on loopback, and reads the page's event stream the way a browser
would. Every socket here has a client timeout, so a broken server fails a test in
seconds rather than hanging the suite (and the mutation sweep) for 300.
"""

from __future__ import annotations

import gc
import http.client
import json
import os
import queue
import re
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from _frames import frame
from wl_expcontroller import serve
from wl_expcontroller.cli import main
from wl_expcontroller.link import Stop, ZmqConsole, ZmqLink
from wl_expcontroller.serve import CLOSED, QUEUE_DEPTH, Hub, Server, make_handler, on_box
from wl_expcontroller.web import FONTS, FRAGMENT_IDS, font_bytes

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
    return Hub(steady=steady or _Clock(0.0))


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


@pytest.fixture(autouse=True)
def _torn_down_servers(monkeypatch):
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
    """
    real_init = Server.__init__
    built: list[Server] = []

    def _record_init(self, *args, **kwargs) -> None:
        real_init(self, *args, **kwargs)
        built.append(self)

    monkeypatch.setattr(Server, "__init__", _record_init)
    yield
    for server in built:
        _teardown_without_close(server)


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

    from wl_expcontroller.cli import _load_bounds
    from wl_expcontroller.dio import Simulated as Card
    from wl_expcontroller.link import Telemetry
    from wl_expcontroller.scheduler import Block, Condition, Scheduler
    from wl_expcontroller.simulate import Tally
    from wl_expcontroller.taskd import Session, SessionSpec
    from wl_expcontroller.web import fragments
    from wl_expcontroller.welfare import Deployment, Simulated as Pump

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
def _served(hub: Hub, *, keepalive_s: float = 15.0, stale_after_s: float = 30.0):
    """The handler on a real loopback socket, with no ZMQ anywhere."""
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(
            hub, token=TOKEN, stale_after_s=stale_after_s, keepalive_s=keepalive_s
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
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


def _events(response):
    """Each `frame` event's payload, as a browser's `EventSource` would dispatch it:
    comments and the `retry:` line are skipped."""
    name, data = None, None
    while True:
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


def test_a_known_path_with_the_wrong_method_is_405_and_b1_takes_no_post():
    hub = _hub()
    with _served(hub) as port:
        assert _request(port, "POST", "/")[0] == 405
        assert _request(port, "POST", "/events")[0] == 405
        assert _request(port, "PUT", "/health")[0] == 405
        assert _request(port, "DELETE", "/")[0] == 405
        assert _request(port, "POST", "/commands")[0] == 404


def test_a_method_the_stdlib_does_not_know_gets_json_not_its_html_page():
    hub = _hub()
    with _served(hub) as port:
        known = _raw(port, b"BREW / HTTP/1.0\r\n\r\n")
        unknown = _raw(port, b"BREW /nope HTTP/1.0\r\n\r\n")

    assert known.startswith(b"HTTP/1.0 405")
    assert known.endswith(b'{"error": "method not allowed"}')
    assert unknown.startswith(b"HTTP/1.0 404")
    assert b"<" not in known + unknown


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


def test_a_quiet_stream_sends_keepalives():
    hub = _hub()
    with _served(hub, keepalive_s=0.05) as port, _stream(port) as response:
        lines = [response.readline() for _ in range(40)]

    assert b": keepalive\n" in lines


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
    "a telemetry frame carried schema 6, and this console reads schema 7, so it is "
    "not shown"
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
        super().__init__(steady=_Clock(0.0))
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
            port, b"GET /health HTTP/1.0\r\nAuthorization: Bearer t\xe9ken\r\n\r\n"
        )

    assert answer.startswith(b"HTTP/1.0 401")
    assert answer.endswith(b'{"error": "unauthorized"}')


# --- the process (Task 11) --------------------------------------------------------

GOOD = "tasks/fixation_detection.py"
ALLOCATION = "tasks/allocation.py"
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


def _trial_budget(monkeypatch, allowed: int) -> None:
    """Fail the session a test starts once it has run `allowed` trials: `taskd`'s
    `run_trial` raises past that, so the session faults, publishes that it did, and
    `wlx run` ends -- `tests/test_cli.py`'s budget, for the one test here that runs a
    session. The session's own clocks stay under test."""
    from wl_expcontroller import taskd

    real, left = taskd.run_trial, [allowed]

    def run_trial(*args, **kwargs):
        left[0] -= 1
        if left[0] < 0:
            raise RuntimeError(
                "this session has run more trials than its budget "
                "(tests/test_serve.py, Ruling 10): nothing ended it"
            )
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
    # threads this test cannot register with `zmq_cleanup`; collected here, under the
    # test's control (`ZmqLink.close`'s docstring).
    gc.collect()
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
        assert "this console reads schema 7" in why
        assert server.hub.snapshot(on_box=True, stale_after_s=30.0)[0] is None

        why = _until_refused(
            server,
            lambda: link._pub.send(msgpack.packb({"schema": 7}, use_bin_type=True)),
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
        gc.collect()


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
        assert "this console reads schema 7" in why
        assert "KeyError" not in why
        assert "could not be decoded" not in why
    finally:
        server.close()
        gc.collect()


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
    gc.collect()


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
        for _ in _events(response):
            pass  # drain to EOF; `_events` returns once `readline()` sees one
        elapsed_drain = time.monotonic() - drain_started

    assert elapsed_close < 2.0, f"close() took {elapsed_close:.2f}s (want well under 5s)"
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
    gc.collect()


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
    assert "the session is unaffected" in captured.err


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


def test_serving_waits_for_the_operator(_bounded_real_wait):
    """A `_wait` that returned would end the console the moment it started.

    Fix round 1, I1: `_wait` now blocks on a real `Server`'s `_fatal` `Event`
    rather than looping on its own, so this stub carries one that is never set --
    `server=None` (the old stand-in) no longer works, since `_wait` reads
    `server._fatal` unconditionally.

    Fix round 2, N1: this file's autouse `_bounded_real_wait` fixture replaces
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
    """Spec §2: a token file, never the repository. `pyproject.toml` stands in for a
    token someone saved into the checkout."""
    inside = Path(serve.__file__).resolve().parents[1] / "pyproject.toml"

    with pytest.raises(SystemExit, match="inside this repository"):
        main(_serve_args(tmp_path, token=inside))


def test_read_token_refuses_a_file_inside_any_git_checkout_not_just_this_one(
    tmp_path,
):
    """Fix round 1, M1: `_REPO_ROOT` was `Path(__file__).resolve().parents[1]` --
    somewhere in `site-packages` for a non-editable install of `wl_expcontroller`,
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
    ["tcp://127.0.0.1:5571", "a,b,c", ",tcp://127.0.0.1:5572"],
)
def test_wlx_serve_refuses_a_link_that_is_not_two_endpoints(tmp_path, link):
    with pytest.raises(SystemExit, match="exactly two"):
        main(_serve_args(tmp_path, link=link))


def test_parse_link_strips_whitespace_around_each_endpoint():
    """Fix round 1, I1(a): the security review's own reproduction was a `--link`
    with a space after the comma -- `"tcp://127.0.0.1:5571, tcp://127.0.0.1:5572"`
    -- which the old `parse_link` returned with the leading space still on the
    second endpoint, still `"://"`-shaped, so it passed straight through and only
    ZeroMQ noticed, inside the telemetry thread, with no `try` around it (I1(b))."""
    assert serve.parse_link("tcp://127.0.0.1:5571, tcp://127.0.0.1:5572") == (
        "tcp://127.0.0.1:5571",
        "tcp://127.0.0.1:5572",
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
