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
import socket
import threading
import time
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

from _frames import frame
from wl_expcontroller.serve import CLOSED, QUEUE_DEPTH, Hub, make_handler, on_box
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
