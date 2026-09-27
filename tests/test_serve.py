"""`wlx serve` (P4d-2b slice b1): the hub, the HTTP surface, and the whole process.

Sim first: the end-to-end test runs a real `wlx run --link` in the simulator and a
real `wlx serve` on loopback, and reads the page's event stream the way a browser
would. Every socket here has a client timeout, so a broken server fails a test in
seconds rather than hanging the suite (and the mutation sweep) for 300.
"""

from __future__ import annotations

import queue

import pytest

from _frames import frame
from wl_expcontroller.serve import CLOSED, QUEUE_DEPTH, Hub


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
