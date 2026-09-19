"""The telemetry message a session publishes to its consoles.

S9a §9, "The telemetry contract": every number on the console comes from the object
the record is written from, never computed beside it. These tests exist to catch the
one way that rule breaks silently -- a field that quietly started summing reward
commands instead of reading `welfare.session_total()` would still look like a
telemetry message and would still pass every other test in this suite.
"""

from __future__ import annotations

from types import SimpleNamespace

from wl_expcontroller.bounds import Bounds, Ceiling, Floor
from wl_expcontroller.link import Absent, Simulated, SetParameter, Stop, Telemetry
from wl_expcontroller.scheduler import Block, Condition, Scheduler
from wl_expcontroller.simulate import Tally
from wl_expcontroller.welfare import Simulated as Pump, Welfare


def _bounds(daily_fluid: float = 250.0) -> Bounds:
    return Bounds(
        subject="A",
        ceilings={"chair_time": Ceiling(value=14_400.0, maximum=14_400.0, unit="s")},
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


def _session_with(delivered_ml: float, already_today: float | None):
    """A stand-in for `Session`, carrying exactly what `Telemetry.of` reads from it.

    Not a real `Session`: constructing one loads a task file and an allocation from
    disk, which these tests have no reason to do. `Telemetry.of`'s parameters are
    untyped precisely so any object with the right shape counts as a session (see
    `link.py`). `.staged` is supplied directly as a plain tuple -- the public
    property of the same name on the real `Session` belongs to a later piece of this
    slice, and this fixture does not need to wait for it to exist.

    `delivered_ml` becomes `welfare.delivered` -- the sync box's delivered-line
    figure -- rather than `welfare.commanded`, with `commanded` pinned to a small
    fixed value distinct from it. **This distinction is load-bearing.** Once
    `.delivered` is set, `session_total()` reconciles to `max(commanded, delivered)`
    (`bounds.reconcile`), so with `commanded` small and `delivered` the larger figure
    -- never the reverse, which `reconcile_report` treats as a pump fault rather than
    a smaller total -- `session_total()` lands on `delivered_ml`, distinct from
    `commanded`. Set `commanded=delivered_ml` instead (an earlier version of this
    fixture did, and left `.delivered` at its default `None`) and `session_total()`
    returns exactly `commanded` -- indistinguishable from a `Telemetry.of` that read
    `welfare.commanded` directly instead of calling `.session_total()`, which is the
    one bug S9a §9 exists to catch.
    """
    welfare = Welfare(
        bounds=_bounds(),
        pump=Pump(),
        already_today=already_today,
        commanded=0.1,
        delivered=delivered_ml,
    )
    return SimpleNamespace(
        spec=SimpleNamespace(session_id="2027-01-14_01", subject="A"),
        welfare=welfare,
        stopped_because="",
        staged=(),
        now=lambda: 0.0,
    )


def _scheduler() -> Scheduler:
    block = Block(name="session", conditions=[Condition("only", {}, target=1)])
    return Scheduler(blocks=[block], seed=0)


def test_telemetry_reads_welfare_rather_than_recomputing_it():
    """S9a §9's one rule. The console shows what `welfare` says was delivered, never a
    sum of reward commands -- so a bug in `welfare` shows up on screen rather than being
    masked by a second, agreeing implementation."""
    session = _session_with(delivered_ml=1.25, already_today=3.0)
    tally = Tally()

    telemetry = Telemetry.of(session, tally, _scheduler(), index=7)

    assert telemetry.fluid_session_ml == session.welfare.session_total()
    assert telemetry.fluid_today_ml == session.welfare.total_today()
    assert telemetry.shortfall_ml == session.welfare.shortfall()
    assert telemetry.trial_index == 7


def test_an_unknown_day_is_none_and_never_zero():
    """`shortfall()` answers `None` for a day nobody measured, and the console must
    carry that through rather than rendering a confident 0.0 (S9a §9)."""
    session = _session_with(delivered_ml=1.0, already_today=None)

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.fluid_today_ml is None
    assert telemetry.shortfall_ml is None


def _telemetry() -> Telemetry:
    """A test telemetry object for console link tests."""
    return Telemetry.of(_session_with(delivered_ml=1.0, already_today=None), Tally(), _scheduler(), index=0)


def test_absent_publishes_nowhere_and_yields_no_commands():
    """**Unlike `dio.Absent` and `run.Unwired`, this one does not refuse**, and the
    difference is what is lost. A dropped event code is missing from a recording
    forever and a dropped reward is fluid an animal worked for. Telemetry nobody
    subscribed to loses nothing -- the record is the record, and a session with no
    console attached is a normal configuration, which is exactly how the cage-side
    kiosk runs."""
    link = Absent()

    link.publish(_telemetry())

    assert link.drain() == []


def test_simulated_keeps_what_was_published_and_returns_queued_commands():
    link = Simulated()
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))

    link.publish(_telemetry())

    assert len(link.published) == 1
    assert link.drain() == [SetParameter(name="fix_hold", value=0.4, by="jake")]
    assert link.drain() == [], "a command is delivered once, not every boundary"
