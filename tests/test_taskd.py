"""`taskd` — running a session end to end.

Roadmap M1's gate: a complete task, headless, deterministic over 1,000 trials, with
the full record on disk. Everything below runs against simulators, and the seam it
runs against is the same one hardware will plug into (S6 §6).

**P4b added the session around the trial loop**: blocks with criterion transitions,
the clocks, the one ceiling that ends a session, one validated path for live
parameter writes, and the reward path that reaches `bounds` -- which for a week
reached nothing at all. Several tests below exist to keep a session from being able
to run without those, which is a different claim from their being present.

**That ceiling is time out of the cage** (PI, 2026-09-19), and it is the only one.
This said "a restraint clock, ceilings that end a session", which was two errors in
one clause by the time it was read: chair time is recorded and bounds nothing, and
there is no trial cap at all.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from wl_expcontroller.bounds import Bounds, Ceiling, Exceeded, Floor
from wl_expcontroller.cli import _load_trial
from wl_expcontroller.dio import Simulated as Card
from wl_expcontroller.link import (
    CONTROL_HISTORY,
    RECENT_OUTCOMES,
    REFUSAL_HISTORY,
    CancelScheduledStop,
    Mark,
    Pause,
    Resume,
    ScheduleStop,
    SetParameter,
    Simulated,
    Stop,
    Telemetry,
)
from wl_expcontroller.record import REFUSAL_LOG_LIMIT
from wl_expcontroller.scheduler import Block, Condition, Counting, Scheduler
from wl_expcontroller.simulate import Tally
from wl_expcontroller.task import Outcome
from wl_expcontroller.taskd import PAUSE_HOUSEKEEPING_S, Session, SessionSpec
from wl_expcontroller.welfare import Deployment, Simulated as Pump

VALUES = {
    "fix_timeout": 4.0,
    "fix_hold": 0.3,
    "response_window": 0.6,
    "target_hold": 0.2,
    "fix_window": 2.0,
    "target_window": 3.0,
    "target_position": 10.0,
    "target_looks": None,
}


def _bounds(daily_fluid: float = 250.0, **over: float) -> Bounds:
    ceilings = {
        "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
        # **The session's one duration ceiling** (PI, 2026-09-19), and since
        # `max_trials` went it is also what bounds a *broken* session here -- on
        # the wall since P4d-2a, so only for a session whose wall follows its
        # frames (`_session`, `_Wall.follow`; Ruling 10). Every test here whose
        # loop nothing else would end has one, or, cage-side and without this
        # ceiling, a trial budget (`_trial_budget`). Small enough that a scheduler
        # whose counts stop advancing runs out of session seconds in a fraction of
        # a wall second rather than grinding on forever --
        # which under a mutation run is a 300-second timeout per function, paid once
        # for every function in the module. Eight hundred seconds is a little over
        # four hundred trials of this task, so it replaces `max_trials=400` with a
        # bound of the same size expressed in the unit a real session ends on. Tests
        # that need more say so, and the two stop conditions that remain -- a block
        # quota and this -- are both ones a real session has.
        "out_of_cage": Ceiling(value=800.0, maximum=100_000.0, unit="s"),
    }
    for name, value in over.items():
        ceiling = ceilings[name]
        ceilings[name] = Ceiling(value, ceiling.maximum, ceiling.unit)
    return Bounds(
        subject="A",
        ceilings=ceilings,
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


def _spec(tmp_path, seed: int = 1, trials: int = 50, **kwargs) -> SessionSpec:
    spec = SessionSpec(
        task="tasks/fixation_detection.py",
        allocation="tasks/allocation.py",
        root=tmp_path,
        session_id="2027-01-14_01",
        subject="A",
        trials=trials,
        frame_period=1 / 240,
        seed=seed,
        values=dict(VALUES),
        bounds=_bounds(),
        already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED,
    )
    for name, value in kwargs.items():
        setattr(spec, name, value)
    return spec


#: A fixed wall-clock instant, in POSIX seconds, from which every session's wall
#: clock here is read. The out-of-cage mark became a clock time on 2026-09-20 (PI),
#: and a test that read the real one would make "stops at its ceiling" depend on
#: when the suite ran. Only the differences from it matter.
WALL_NOW = 1_700_000_000.0


def _session(spec, link=None, left_cage_ago: float = 0.0) -> Session:
    """A session wired to simulators, which is the only rig that exists.

    `link` defaults to `None`, i.e. omitted from the call -- `Session.link` then
    falls back to its own default, `link.Absent()`, exactly as a session with no
    console attached does outside a test.

    **Its wall clock advances with its simulated frames**: `WALL_NOW` plus
    `session.now()`. Every welfare duration is read on the wall since P4d-2a (spec
    §10), so a session whose wall stood still would never reach its out-of-cage
    ceiling -- and that ceiling is both what several tests below are about and the
    backstop that ends a broken scheduler's session on simulated seconds rather than
    at a 300-second mutation timeout (`_bounds`). A wall that follows the frames is
    what a rig has anyway, where frames are real time. Tests about the two clocks
    *disagreeing* inject a wall of their own (`_Wall`).

    **The marks this deployment kind needs** (`welfare.preflight`): the out-of-cage
    one starts the clock that bounds the session, and head-fixation is the restraint
    record -- required by `RIG_FIXED`, which `_spec` declares, and *refused* by the
    other two kinds since 2026-09-20. Both are wall instants.
    `test_a_session_refuses_to_run_before_the_animal_is_out_of_its_cage` is the
    fixture's own counter-example, built without this helper.

    `left_cage_ago` stays expressed as an interval because that is what a test about
    the *interval* means; it is turned into a clock time against `WALL_NOW` here,
    which is the one place a test has to know that the parameter changed base. It
    defaults to zero, which is the truth for a simulated session -- nothing was
    transported and nothing was chaired. See
    `test_transport_and_chairing_count_toward_the_sessions_limit`.
    """
    kwargs = {"link": link} if link is not None else {}
    session = Session(spec, card=Card(), pump=Pump(), **kwargs)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW - left_cage_ago)
    if spec.deployment is Deployment.RIG_FIXED:
        session.head_fixed(at=session.wall_now())
    return session


def _parameter_changes(session: Session) -> list[dict]:
    """Every parameter change actually written to `parameter_changes.jsonl`, in the
    order recorded. Reads the file on disk rather than `session._staged` or anything
    in memory -- this backs a test about what a console's command caused to be
    *written*, and a console that only says it changed something proves nothing
    about what a recording could ever be aligned to."""
    path = session.directory / "parameter_changes.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- what was already true --------------------------------------------------


def test_a_session_refuses_to_start_if_the_task_fails_its_checks(tmp_path):
    """The load-time checks are load-time. A session that begins and *then*
    discovers the task is malformed has already put an animal in a chair."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from wl_expcontroller.task import After, On, Outcome, State, Trial\n"
        "t = Trial(start='a', states=[State('a', go=[On(After(1.0), Outcome.CORRECT)]),"
        " State('orphan', go=[On(After(1.0), Outcome.CORRECT)])])\n"
    )
    spec = _spec(tmp_path)
    spec.task = str(bad)

    try:
        _session(spec).run()
    except SystemExit as exit_:
        assert "unreachable-state" in str(exit_)
    else:
        raise AssertionError("a malformed task must not run")


def test_a_session_is_deterministic_for_a_seed(tmp_path):
    """M1's gate says deterministic, and it is the property that makes a simulated
    session evidence: two runs that disagree cannot both be describing the task."""
    first = _session(_spec(tmp_path / "a")).run()
    second = _session(_spec(tmp_path / "b")).run()

    assert first.outcomes == second.outcomes
    assert first.responses == second.responses


def test_a_different_seed_gives_a_different_session(tmp_path):
    """Otherwise the determinism test above passes for the wrong reason."""
    first = _session(_spec(tmp_path / "a", seed=1)).run()
    second = _session(_spec(tmp_path / "b", seed=2)).run()

    assert first.outcomes != second.outcomes


def test_a_session_writes_its_record_and_its_config(tmp_path):
    _session(_spec(tmp_path, trials=20)).run()

    directory = tmp_path / "2027-01-14_01" / "expcontroller"
    trials = (directory / "trials.jsonl").read_text().splitlines()
    config = json.loads((directory / "config.json").read_text())

    assert len(trials) == 20
    assert json.loads(trials[0])["subject"] == "A"
    assert config["resolved"]["fix_hold"] == 0.3
    assert config["versions"]["task"].endswith("fixation_detection.py")


def test_the_m1_gate_one_thousand_deterministic_trials_with_full_outputs(tmp_path):
    """Roadmap M1, asserted rather than described.

    A thousand trials, headless, no hardware, deterministic for a seed, every outcome
    the task declares reached, nothing hanging, and the record on disk.
    """
    spec = _spec(tmp_path, trials=1_000)
    # The gate's own claim is a thousand trials, so the session has to be able to
    # reach them: the block quota is a thousand, and the duration ceiling is the
    # twelve hours a real session runs under (S8 §5.2) rather than the deliberately
    # small backstop `_bounds` uses everywhere else in this file. The gate passing
    # is itself the statement that a thousand trials fit inside a real session.
    spec.bounds = _bounds(out_of_cage=43_200.0)
    census = _session(spec).run()

    trials = (
        tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
    ).read_text().splitlines()

    assert len(trials) == 1_000
    assert sum(census.outcomes.values()) == 1_000
    assert census.hangs == 0
    assert census.states_visited == {"await_fix", "hold_fix", "stim_on", "verify"}
    assert len(census.outcomes) >= 4, "a session reaching one outcome tests nothing"


# --- the reward path, which for a week went nowhere -------------------------


def test_a_session_delivers_reward_and_the_day_counts_every_one(tmp_path):
    """The headline defect P4b exists to fix. `bounds`' fluid check was called by
    nothing outside its own tests; a session commanded reward and no accounting ever
    saw it. This asserts the whole chain: task action, effects port, the day's total,
    pump."""
    session = _session(_spec(tmp_path, trials=200))
    census = session.run()

    correct = census.outcomes[Outcome.CORRECT]
    assert correct > 0, "a session that never rewards cannot test the reward path"
    assert session.welfare.deliveries == correct
    assert len(session.pump.delivered) == correct
    assert session.welfare.total_today() == pytest.approx(correct * 0.15)


def test_a_session_records_when_it_last_paid_on_its_own_wall_clock(tmp_path):
    """The path, not the piece: a task's `Reward`, through `Rig`, into `welfare`, on
    the session's wall. `_session` gives the wall `WALL_NOW` plus the frame clock, so
    a `Rig` that read `time.time()` instead would land years past this range --
    `WALL_NOW` is November 2023."""
    session = _session(_spec(tmp_path, trials=50))

    census = session.run()

    assert census.outcomes[Outcome.CORRECT] > 0
    assert WALL_NOW <= session.welfare.last_delivery_wall_at <= session.wall_now()


def test_a_rewards_instant_is_on_the_sessions_anchored_clock_not_the_host_clock(
    tmp_path, monkeypatch
):
    """**Ruling 8, on the reward path.** With no wall injected, `Rig` reads
    `Session.wall_now`, which is the session's `welfare.SessionClock`: the host clock
    as it read when the session was created, carried forward on a steady clock. So
    the host clock stepped back an hour before a reward moves that reward's instant
    not at all, and it is the instant every other welfare reading of that moment
    gets. A `Rig` given `time.time` would record `WALL_NOW - 3_593.0` here; one given
    the `SessionClock` itself would pass this and fail the test above, whose wall is
    injected. Every steady clock `welfare.steady_seconds` could read is stubbed to one
    value, as `test_the_sessions_wall_does_not_step_when_the_host_clock_does` does."""
    host, steady = [WALL_NOW], [100.0]
    monkeypatch.setattr(time, "time", lambda: host[0])
    monkeypatch.setattr(time, "monotonic", lambda: steady[0])
    monkeypatch.setattr(time, "clock_gettime", lambda clock: steady[0])
    session = Session(_spec(tmp_path), card=Card(), pump=Pump())
    host[0], steady[0] = WALL_NOW - 3_600.0 + 7.0, 107.0

    session.rig.reward("reward_correct")

    assert session.welfare.last_delivery_wall_at == WALL_NOW + 7.0
    assert session.welfare.last_delivery_wall_at == session.wall_now()


def test_a_session_strobes_the_codes_its_task_declares(tmp_path):
    """The other half of the same defect. A session that runs a full protocol and
    emits no event codes writes a record that cannot be aligned to any recording,
    and nothing in it says so."""
    session = _session(_spec(tmp_path, trials=20))
    session.run()

    assert 4096 in session.card.codes, "FIX_ON is an entry action"
    assert 4102 in session.card.codes, "REWARD_COMMANDED accompanies a delivery"


def test_a_session_strobes_the_outcome_marker_the_allocation_gives(tmp_path):
    """`Marker` 34-38 are `wl-preproc`'s and the framework's to emit -- a task
    declares an `Outcome`, never a marker. Without them a recording has no trial
    boundaries at all, whatever else is in the stream."""
    session = _session(_spec(tmp_path, trials=20))
    census = session.run()

    markers = [code for code in session.card.codes if code < 256]
    assert len(markers) == sum(census.outcomes.values())
    assert set(markers) <= {34, 35, 36, 37, 38}


def test_a_session_never_stops_paying_an_animal_that_is_working(tmp_path):
    """**There is no fluid ceiling** (PI, 2026-09-06). A daily figure the session
    passes is a floor it cleared, not a limit it must stop at -- and a session that
    stopped there would be withholding fluid the animal earned."""
    spec = _spec(tmp_path, trials=200)
    spec.bounds = _bounds(daily_fluid=1.0)
    session = _session(spec)

    census = session.run()

    assert sum(census.outcomes.values()) == 200
    assert session.welfare.deliveries == census.outcomes[Outcome.CORRECT]
    assert session.welfare.shortfall() == 0.0


def test_a_session_reports_what_the_day_still_owes(tmp_path):
    """The number the session exists to hand a person at close: what to supplement."""
    spec = _spec(tmp_path, trials=20)
    spec.bounds = _bounds(daily_fluid=200.0)
    session = _session(spec)

    session.run()

    assert session.welfare.shortfall() == pytest.approx(
        200.0 - session.welfare.commanded
    )


def test_a_session_with_an_unknown_daily_total_still_pays_and_says_it_cannot_count(
    tmp_path,
):
    """The ELN was unreachable at `prepare-session`, so nobody knows what the animal
    has already had. Under a floor that must not stop the reward: an unknown day is a
    reporting failure, and the one thing it must not do is stop paying for work."""
    spec = _spec(tmp_path, trials=50)
    spec.already_delivered_today = None
    session = _session(spec)

    census = session.run()

    assert sum(census.outcomes.values()) == 50
    assert session.welfare.deliveries == census.outcomes[Outcome.CORRECT]
    assert session.welfare.shortfall() is None


def test_a_session_refuses_to_run_before_the_animal_is_out_of_its_cage(tmp_path):
    """**The refusal that makes the duration limit real** (PI, 2026-09-19). A rig
    session nobody marked has no start for the twelve-hour clock, and running it
    against an assumed zero is how a limit gets disabled by forgetting rather than
    by deciding. `welfare.preflight` is what `run()` asks, so the rule has one
    home; `test_welfare.py` covers the refusal's own shape."""
    session = Session(_spec(tmp_path, trials=5), card=Card(), pump=Pump())
    session.head_fixed(at=session.wall_now())

    with pytest.raises(Exceeded, match="out of its cage"):
        session.run()


def test_a_head_fixed_session_refuses_to_run_before_the_animal_is_in_the_chair(
    tmp_path,
):
    """S8 §5.2's other preflight mark, kept -- **for the kind that declares it**
    (PI, 2026-09-20). Chair time stopped bounding the session on 2026-09-19 and did
    not stop being what `HEAD_FIXED`/`HEAD_RELEASED` record: a `RIG_FIXED` session
    with neither code in the stream has no record of a restraint that happened."""
    session = Session(
        _spec(tmp_path, trials=5),
        card=Card(),
        pump=Pump(),
        wall_clock=lambda: WALL_NOW,
    )
    session.left_cage(at=WALL_NOW)

    with pytest.raises(Exceeded, match="head-fixed"):
        session.run()


def test_a_chaired_session_runs_and_strobes_no_restraint_codes(tmp_path):
    """**Head-fixation is a property of the deployment, not of being on a rig** (PI,
    2026-09-20). A `RIG_CHAIRED` session runs with no head-fixation mark, is bounded
    by the same out-of-cage clock, and puts **neither 4128 nor 4129** in the stream --
    because it has no restraint to record, and a `HEAD_RELEASED` with no `HEAD_FIXED`
    before it would be a restraint record for restraint nothing marked.

    `run()` released the head unconditionally until this test existed, which would
    have strobed 4129 into exactly such a stream."""
    spec = _spec(tmp_path, trials=5)
    spec.deployment = Deployment.RIG_CHAIRED
    session = _session(spec)

    session.run()

    assert 4128 not in session.card.codes
    assert 4129 not in session.card.codes
    assert session.welfare.chair_seconds(session.wall_now()) is None, (
        "restrained and unmarked is ABSENT, never 0.00"
    )


def test_a_session_stops_at_its_out_of_cage_ceiling(tmp_path):
    """The session's one duration limit, and the only welfare ceiling that ends a
    session at all since `max_trials` went. Out of the cage, not in the chair: the
    clock started at `left_cage`, before head-fixation and before the first trial.

    A hundred trials rather than a thousand because the ceiling is the thing under
    test -- if it stops working, the block quota bounds what runs instead of a
    mutation sweep waiting for a timeout."""
    spec = _spec(tmp_path, trials=100)
    spec.bounds = _bounds(out_of_cage=2.0)
    session = _session(spec)

    census = session.run()

    assert sum(census.outcomes.values()) < 100
    assert "out_of_cage" in session.stopped_because


def test_putting_the_animal_back_in_its_cage_closes_the_sessions_clock(tmp_path):
    """**`run()` deliberately does not do this**, and that is the property under test.

    The limit is on an interval, not on a process (S8 §5.2 item 4): when the loop ends
    the animal is still in the chair, and the release, the unchairing and the walk back
    are all inside the twelve hours. A `run()` that closed the clock itself would report
    a session as shorter than the animal's day actually was, every time. So the mark is
    the console's, and this drives it the way a console would.

    Found by a mutation sweep: `Session.returned_to_cage` was wired to `welfare` and
    called by nothing, which is `bounds.check_delivery`'s failure exactly -- a path that
    reads as present because it exists.

    It works **after** `run()` and not during it: `run()` releases the head as its last
    act, and `welfare.returned_to_cage` refuses while the animal is still recorded as
    head-fixed, so the whole loop is inside that refusal (see
    `test_the_console_cannot_freeze_the_clock_by_marking_the_animal_home_mid_session`)."""
    session = _session(_spec(tmp_path, trials=3))
    session.run()
    when_the_loop_ended = session.welfare.out_of_cage_seconds(session.wall_now())
    assert when_the_loop_ended > 0.0, "a session that took no time cannot test a clock"

    # **The walk back, which ruling 4 is about** (PI, 2026-09-20). The frames have
    # stopped, and so has this helper's wall, which follows them; the animal is
    # released, unchaired and walked back over the next ten minutes of *wall* time,
    # and the return is marked when it is actually home. Both ends of the interval
    # are wall instants, so the frames stopping no longer truncates it.
    wall = WALL_NOW + 600.0
    session.wall_clock = lambda: wall
    session.returned_to_cage(at=wall)

    closed = session.welfare.out_of_cage_seconds(WALL_NOW + 99_999.0)
    assert closed == pytest.approx(600.0), (
        "the clock did not close, so it would have run to the end of time"
    )
    assert closed > when_the_loop_ended, (
        "the release, the unchairing and the walk back are inside the twelve hours, "
        "and marking the return on the frozen frame clock left every one of them out"
    )


def test_the_console_cannot_freeze_the_clock_by_marking_the_animal_home_mid_session(
    tmp_path,
):
    """**A session whose animal is recorded home is one whose limit cannot move.**

    Reproduced before it was fixed: marking the return mid-session froze
    `out_of_cage_seconds` at whatever it read, so `must_stop` answered `None` for the
    rest of a session that reported itself fully marked -- the missing-mark failure
    reached with both marks present. `run()` head-fixes before its first frame and
    releases after its last, so every pass of the loop is inside the refusal below."""
    session = _session(_spec(tmp_path, trials=3))

    with pytest.raises(Exceeded, match="head-fixed"):
        session.returned_to_cage(at=WALL_NOW)

    census = session.run()
    assert sum(census.outcomes.values()) == 3, "the refusal did not end the session"


def test_transport_and_chairing_count_toward_the_sessions_limit(tmp_path):
    """**The whole of Ruling 2, end to end through the session's own clock.**

    A departure marked at the moment the session starts makes out-of-cage time
    identical to chair time -- which is exactly the under-count the clock replaced
    chair time to remove, and which `wlx run` did, at the frame clock's zero, until a
    review caught it. Twenty minutes of transport and chairing here, and the limit
    counts every one of them while the restraint record counts none. Both are read
    on the wall since P4d-2a (spec §10).

    The twelve-hour ceiling rather than `_bounds`' deliberately small backstop,
    because twenty minutes of transport is past an 800-second one -- which is
    `left_cage` refusing a session that starts outside its own limit, and is a
    different test (`test_welfare.py`)."""
    spec = _spec(tmp_path, trials=3)
    spec.bounds = _bounds(out_of_cage=43_200.0)
    session = _session(spec, left_cage_ago=1_200.0)

    session.run()

    out_of_cage = session.welfare.out_of_cage_seconds(session.wall_now())
    chair = session.welfare.chair_seconds(session.wall_now())
    assert out_of_cage == pytest.approx(chair + 1_200.0)
    assert session.welfare.left_cage_wall_at == WALL_NOW - 1_200.0, (
        "the mark must sit before the session started, or transport is free"
    )


def test_a_session_ends_on_its_block_quota_and_not_on_a_trial_ceiling(tmp_path):
    """PI, 2026-09-19: *"the max trials idea makes no sense to me"*. What ends a
    session of ordinary length is the plan running out -- the quota every condition
    carries -- and this is that, asserted where a trial ceiling used to be. A stale
    `max_trials` entry in the bounded config changes nothing, because nothing reads
    one."""
    spec = _spec(tmp_path, trials=30)
    spec.bounds.ceilings["max_trials"] = Ceiling(5.0, 5.0, "trials")
    session = _session(spec)

    census = session.run()

    assert sum(census.outcomes.values()) == 30
    assert session.stopped_because == "every block is finished"


def test_a_release_with_no_fixation_never_reaches_the_card(tmp_path):
    """**The console path, not the piece.** `welfare.head_released` refuses a release
    with nothing to release; this asserts the consequence that matters -- no `4129`
    in the stream -- through the object a console action would actually call.

    `Session.head_released` strobes the code straight after telling `welfare`, so a
    guard that let the call through would have put a `HEAD_RELEASED` into a stream
    with no `HEAD_FIXED` in it. `run()` never does this; a console action added to
    the panel would, which is the whole reason the guard exists.
    """
    session = Session(
        _spec(tmp_path, trials=5),
        card=Card(),
        pump=Pump(),
        wall_clock=lambda: WALL_NOW,
    )
    session.left_cage(at=WALL_NOW)

    with pytest.raises(Exceeded, match="nothing to release"):
        session.head_released(at=WALL_NOW + 10.0)

    assert 4129 not in session.card.codes, "the code must not reach the card"


def test_head_fixation_is_event_coded_at_both_ends(tmp_path):
    """S8 §5.2: restraint is the one welfare quantity with no hardware line, so the
    codes *are* its durable record and an offline reader recovers chair time from the
    sync box's capture of them. Chair time stopped bounding the session on 2026-09-19;
    that is why these two are still strobed."""
    session = _session(_spec(tmp_path, trials=5))
    session.run()

    codes = session.card.codes
    assert codes[0] == 4128, "HEAD_FIXED before anything else in the session"
    assert codes[-1] == 4129, "HEAD_RELEASED after the last trial"


# --- blocks -----------------------------------------------------------------


def _two_blocks() -> list[Block]:
    near = Condition("near", {"target_position": 5.0}, target=6)
    far = Condition("far", {"target_position": 12.0}, target=6)
    return [
        Block(name="near-far", conditions=[near, far]),
        Block(name="far-only", conditions=[Condition("far", {"target_position": 12.0}, target=4)]),
    ]


def test_a_session_runs_its_blocks_in_order_and_stops_when_they_are_done(tmp_path):
    """`taskd` never imported `scheduler`, so a session was a flat run of trials and
    blocks, quotas and criteria existed as a component nothing drove."""
    spec = _spec(tmp_path, trials=400, blocks=_two_blocks())
    session = _session(spec)

    census = session.run()

    assert session.stopped_because == "every block is finished"
    assert session.blocks_run == ["near-far", "far-only"]
    # Six each in the first block plus four in the second, all counted on completed
    # trials, so aborts add to the total without paying the debt.
    assert sum(census.outcomes.values()) >= 16


def test_each_trial_records_the_condition_it_actually_ran(tmp_path):
    """S8 §3.3: the complete resolved parameter set per trial, not a pointer to "the
    config". A condition's overrides are exactly what a pointer would lose."""
    spec = _spec(tmp_path, trials=400, blocks=_two_blocks())
    _session(spec).run()

    rows = [
        json.loads(line)
        for line in (
            tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
        ).read_text().splitlines()
    ]

    positions = {row["params"]["target_position"] for row in rows}
    assert positions == {5.0, 12.0}
    assert {row["condition"] for row in rows} == {"near", "far"}
    assert {row["block"] for row in rows} == {"near-far", "far-only"}


def test_a_criterion_block_ends_on_performance_rather_than_on_a_count(tmp_path):
    """The transition S8 §1 calls a length rule. A block whose criterion is met stops
    early; the session moves on rather than ending."""
    blocks = [
        Block(
            name="shaping",
            conditions=[Condition("only", {}, target=10_000)],
            criterion=(0.2, 10),
            counts_toward=Counting.EVERY_TRIAL,
        ),
        Block(name="test", conditions=[Condition("only", {}, target=5)]),
    ]
    spec = _spec(tmp_path, trials=400, blocks=blocks)
    session = _session(spec)

    session.run()

    assert session.blocks_run == ["shaping", "test"]
    assert session.stopped_because == "every block is finished"


def test_a_session_without_blocks_runs_one_of_its_declared_length(tmp_path):
    """The flat session is the block session with one block, not a second code path.
    Two loops would be two places for the ceilings to be checked differently."""
    session = _session(_spec(tmp_path, trials=12))

    census = session.run()

    assert sum(census.outcomes.values()) == 12
    assert session.blocks_run == ["session"]


# --- the live parameter path ------------------------------------------------


def test_a_live_write_is_staged_and_applied_at_a_trial_boundary(tmp_path):
    """S8 §3.2: staged, then applied atomically in the ITI. Never mid-trial -- a
    parameter that changed under a running trial makes that trial's record a
    description of neither value."""
    session = _session(_spec(tmp_path, trials=4))
    session.set("fix_hold", 0.5, by="console")

    assert session.spec.values["fix_hold"] == 0.3, "not until the boundary"

    session.run()

    rows = [
        json.loads(line)
        for line in (
            tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
        ).read_text().splitlines()
    ]
    assert rows[0]["params"]["fix_hold"] == 0.5


def test_a_live_write_is_recorded_with_its_origin(tmp_path):
    """One validated write path whatever the origin, and the actor recorded -- half
    a guarantee otherwise (S8 §3.3)."""
    session = _session(_spec(tmp_path, trials=4))
    session.set("fix_hold", 0.5, by="console")

    session.run()

    changes = [
        json.loads(line)
        for line in (
            tmp_path / "2027-01-14_01" / "expcontroller" / "parameter_changes.jsonl"
        ).read_text().splitlines()
    ]
    assert changes == [
        {"sequence": 1, "name": "fix_hold", "was": 0.3, "now": 0.5, "by": "console"}
    ]


def test_a_live_write_outside_a_parameters_declared_range_is_refused(tmp_path):
    """The declaration S8 §3.1 turns into validation. It is the same declaration the
    console builds its widget from, so a value it cannot show is a value it cannot
    send."""
    session = _session(_spec(tmp_path, trials=4))

    with pytest.raises(Exceeded, match="fix_hold"):
        session.set("fix_hold", 99.0, by="console")


def test_a_live_write_to_an_undeclared_parameter_is_refused(tmp_path):
    """A typo must not become a parameter. `fix_hld` accepted silently is a session
    running the old value while the console shows the new one."""
    session = _session(_spec(tmp_path, trials=4))

    with pytest.raises(Exceeded, match="fix_hld"):
        session.set("fix_hld", 0.5, by="console")


def test_a_live_write_to_a_welfare_bounded_value_goes_through_its_ceiling(tmp_path):
    """Reward volume is the parameter most often adjusted mid-session and the one
    where a slip is a dose. The console may move it; it may not move it past the
    ceiling, and the two paths are the same path.

    **Refused when it is offered, applied at the next trial boundary** (PI,
    2026-09-19). The ceiling is checked here, in this call, so a person hears about
    a refusal while still looking at the console; the assignment belongs to
    `_apply_staged`, so a trial already under way is never re-priced.
    `test_a_welfare_bounded_change_applies_at_the_next_boundary_like_any_other` is
    the other half of that, through the loop rather than through this method.
    """
    session = _session(_spec(tmp_path, trials=4))

    session.set("reward_correct", 0.30, by="console")
    assert session.spec.bounds.value("reward_correct") == 0.15, (
        "the value moved as the command was offered rather than at the boundary"
    )
    assert session.staged[-1] == ("reward_correct", 0.15, 0.30, "console", True)

    with pytest.raises(Exceeded, match="reward_correct"):
        session.set("reward_correct", 0.90, by="console")


def test_a_parameter_change_is_strobed_so_the_discontinuity_is_on_the_clock(tmp_path):
    """P16. The `PARAM_CHANGE` escape carrying a sequence number is still what is
    wanted and is still unagreed by `wl-preproc`; until it exists a code in our own
    range puts the *timing* of the discontinuity in the stream, with the values in
    the session record beside it."""
    session = _session(_spec(tmp_path, trials=4))
    session.set("fix_hold", 0.5, by="console")

    session.run()

    assert 4130 in session.card.codes


def test_a_session_refuses_a_bounded_config_belonging_to_another_subject(tmp_path):
    """Running subject A against subject B's ceilings is a dose error with a
    plausible-looking session behind it, and nothing downstream would show it: every
    trial row says A while every limit came from B."""
    spec = _spec(tmp_path, trials=5)
    spec.bounds = Bounds(subject="B", ceilings=dict(_bounds().ceilings))

    with pytest.raises(Exceeded, match="'A'.*'B'"):
        Session(spec, card=Card(), pump=Pump())


# --- the console link --------------------------------------------------------


def test_a_session_publishes_one_frame_per_trial_then_two_when_it_stops(tmp_path):
    """One entry before each trial runs, plus two more at the close: `run()`
    publishes at the top of every pass through `while True:`, and the pass where the
    session finds its plan finished and stops -- without drawing a sixth trial -- is
    such a pass too, published once before the stop is known (`must_stop`/
    `scheduler.finished` sit *below* that publish) and once more right after, so the
    very last frame names the reason (`publish()` in `run()`). Both final frames
    share `trial_index=5`, one index past the last trial that actually ran; see
    `test_the_last_telemetry_names_a_welfare_ceilings_reason` for the reason itself."""
    link = Simulated()
    spec = _spec(tmp_path, trials=5)
    session = _session(spec, link=link)

    session.run()

    assert [t.trial_index for t in link.published] == [0, 1, 2, 3, 4, 5, 5]


def test_a_queued_commands_staged_value_is_visible_before_it_applies(tmp_path):
    """The load-bearing ordering, made to fail if it moves. The drain happens after
    `_apply_staged()`, so a command offered at one boundary is staged and visible in
    that same boundary's telemetry (S9a §8's live change feed) but does not land
    until the *next* one. Move the drain above `_apply_staged()` and this fails two
    ways at once: the first published frame's `staged` reads empty, since nothing
    else ever populates `Telemetry.staged`, and trial 0 runs under the *new* value
    instead of the old one, because staging and applying would happen in the same
    pass rather than a boundary apart."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))

    session.run()

    staged = link.published[0].staged
    assert len(staged) == 1
    assert staged[0].name == "fix_hold"
    assert staged[0].now == 0.4

    rows = [
        json.loads(line)
        for line in (session.directory / "trials.jsonl").read_text().splitlines()
    ]
    assert rows[0]["params"]["fix_hold"] == 0.3, "trial 0 ran under the old value"


def test_a_command_from_a_console_lands_at_the_next_boundary_with_its_actor(tmp_path):
    """The console gains no second write path: the command goes through `Session.set`,
    so a welfare-bounded name still meets its ceiling and an undeclared name is still
    refused."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))

    session.run()

    changes = _parameter_changes(session)
    assert changes[0]["name"] == "fix_hold"
    assert changes[0]["by"] == "jake"


def test_a_console_command_moving_reward_volume_goes_through_its_ceiling(tmp_path):
    """The highest-consequence capability in this diff -- a console moving reward
    volume -- proved end to end rather than assembled from two halves tested apart.
    `test_a_live_write_to_a_welfare_bounded_value_goes_through_its_ceiling` drove
    `Session.set` directly, and no test had driven a *bounded* name through a
    console command. `reward_correct`'s ceiling here is `Ceiling(value=0.15,
    maximum=0.40, unit="mL")` (see `_bounds`): a command asking for 0.90 is refused,
    visible as a refusal, and one asking for 0.30 is accepted, staged with
    `bounded=True`, and applied by `_apply_staged()` at the next trial boundary --
    the same deferral an ordinary parameter gets (PI, 2026-09-19). The assertion on
    the ceiling below is read after `run()`, i.e. after that boundary has passed;
    `test_a_welfare_bounded_change_applies_at_the_next_boundary_like_any_other`
    is what pins *which* trial first sees it."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="reward_correct", value=0.90, by="jake"))
    link.queue(SetParameter(name="reward_correct", value=0.30, by="jake"))

    session.run()

    assert len(session.refusals) == 1
    assert session.refusals[0][0] == "reward_correct"
    assert session.refusals[0][1] == "jake"
    assert session.spec.bounds.value("reward_correct") == 0.30

    staged = link.published[0].staged
    assert len(staged) == 1
    assert staged[0].name == "reward_correct"
    assert staged[0].now == 0.30
    assert staged[0].bounded is True

    refused = link.published[0].refusals
    assert len(refused) == 1
    assert refused[0].name == "reward_correct"


def test_a_stop_command_ends_the_session_at_a_boundary_not_mid_trial(tmp_path):
    link = Simulated()
    spec = _spec(tmp_path, trials=100)
    session = _session(spec, link=link)
    link.queue(Stop(by="jake"))

    census = session.run()

    assert session.stopped_because == "stopped by jake"
    assert sum(census.outcomes.values()) < 100


def test_a_refused_command_does_not_stop_the_session(tmp_path):
    """A console offering a parameter the task does not declare is a mistake by a
    person, not a fault of the rig. The session records the refusal and runs on --
    stopping would let a typo end a session with an animal in the chair."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="not_a_parameter", value=1.0, by="jake"))

    census = session.run()

    assert sum(census.outcomes.values()) == 3, "the session ran its block quota"
    assert len(session.refusals) == 1
    assert session.refusals[0][0] == "not_a_parameter"
    assert session.refusals[0][1] == "jake"


def test_a_refusal_appears_in_the_telemetry_a_console_reads(tmp_path):
    """`Session.refusals` was in-memory only until now: the person who mistyped a
    name got no feedback, and nothing on any console showed that a write had even
    been attempted. `Telemetry.refusals` mirrors `session.refusals` (S9a §8's live
    change feed), cumulative like `outcomes` rather than cleared per boundary, since
    a refusal is a resolved event and not a pending one."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="not_a_parameter", value=1.0, by="jake"))

    session.run()

    refused = link.published[0].refusals
    assert len(refused) == 1
    assert refused[0].name == "not_a_parameter"
    assert refused[0].by == "jake"
    # Still on the very last frame -- refusals accumulate for the session's life,
    # unlike `staged`, which clears at the boundary the change actually applies.
    assert len(link.published[-1].refusals) == 1


# --- the last telemetry frame always names why (S9 "written for a stranger") ------


def test_the_last_telemetry_names_a_welfare_ceilings_reason(tmp_path):
    """A console watching a session hit the out-of-cage ceiling must not see the
    stream go quiet with no explanation -- that is precisely the failure the
    publish-before-break ordering exists to prevent, and it must hold for every stop
    path, not only a console-issued `Stop`. Asserts on the reason itself, not a
    frame count: a count assertion would pass even with an empty `stopped_because`.

    This was written against `max_trials` and now runs against the one welfare
    ceiling there is (PI, 2026-09-19). The property is unchanged; what changed is
    which limit can end a session."""
    link = Simulated()
    spec = _spec(tmp_path, trials=100)
    spec.bounds = _bounds(out_of_cage=2.0)
    session = _session(spec, link=link)

    session.run()

    assert "out_of_cage" in link.published[-1].stopped_because
    assert link.published[-1].stopped_because == session.stopped_because


def test_the_last_telemetry_names_a_consoles_stop_reason(tmp_path):
    """The path this was already true for, made explicit against the telemetry a
    console actually reads rather than the session's own attribute."""
    link = Simulated()
    spec = _spec(tmp_path, trials=100)
    session = _session(spec, link=link)
    link.queue(Stop(by="jake"))

    session.run()

    assert link.published[-1].stopped_because == "stopped by jake"


def test_the_last_telemetry_names_every_block_finished(tmp_path):
    """The third stop path: a flat session running to its declared length, with no
    welfare ceiling in the way. Same requirement, same assertion shape."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)

    session.run()

    assert link.published[-1].stopped_because == "every block is finished"


# --- the PI's four decisions of 2026-09-19 ----------------------------------


def _changes_so_far(session: Session) -> list[dict]:
    """`parameter_changes.jsonl` as it stands *right now*, mid-session.

    Separate from `_parameter_changes` because that one reads a file a completed
    session is known to have written, and this one is called from inside the loop,
    where the file does not exist until the first change is recorded. A missing
    file here means "no change recorded yet", which is the thing being measured.
    """
    path = session.directory / "parameter_changes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _watch(session: Session) -> list:
    """Record, after every trial, what that trial actually ran under.

    `observe` runs once per trial, after its outcome is recorded and before the
    next pass, so the ceiling it reads is the one that trial's rewards were priced
    at -- `welfare.deliver` reads `bounds.value(ref)` per delivery.
    """
    seen: list = []
    session.observe = lambda condition, values, result: seen.append(
        (session.spec.bounds.value("reward_correct"), len(_changes_so_far(session)))
    )
    return seen


def test_a_welfare_bounded_change_applies_at_the_next_boundary_like_any_other(
    tmp_path,
):
    """PI, 2026-09-19: a welfare-bounded change defers exactly as an ordinary
    parameter does -- validated when offered, applied atomically at the next trial
    boundary.

    It used to move the ceiling inside `Session.set`, as the command was drained,
    so the trial that ran later in that *same* pass was already at the new volume
    while every console displayed it as `staged`. An operator who had just lowered
    a reward volume was told it had not taken effect yet. It had.
    """
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    seen = _watch(session)
    link.queue(SetParameter(name="reward_correct", value=0.30, by="jake"))

    session.run()

    assert seen[0][0] == 0.15, "trial 0 ran at the new volume; the change did not defer"
    assert seen[1][0] == 0.30, "the change never landed"


def test_a_bounded_changes_record_row_lands_in_the_pass_that_applies_it(tmp_path):
    """The off-by-one in fluid attribution, which is the reason the decision was
    made rather than a side effect of it.

    `_apply_staged` wrote the `PARAM_CHANGED` strobe and the
    `parameter_changes.jsonl` row one pass *after* `set` had already moved the
    ceiling, so the first trial rewarded at the new volume ran before its own row
    existed. Anyone reconciling commanded fluid against that file offline assigned
    one trial's delivery to the wrong value. Applying and recording in the same
    pass is what puts the row immediately before the first trial it describes.
    """
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    seen = _watch(session)
    link.queue(SetParameter(name="reward_correct", value=0.30, by="jake"))

    session.run()

    assert seen[0] == (0.15, 0), "a row was recorded for a change no trial had yet run"
    assert seen[1] == (0.30, 1), "the row and the volume it describes are a pass apart"


def test_a_pump_fault_publishes_a_final_frame_before_it_propagates(tmp_path):
    """PI, 2026-09-19. `welfare.deliver` raises, `welfare.Rig` deliberately does not
    swallow it, and it used to propagate past `run()`'s `finally` with no telemetry
    at all -- so a console watching a rig break, unattended and cage-side, saw the
    stream simply stop with no reason anywhere on screen.

    One frame naming the fault is published at the loop boundary and the exception
    then propagates exactly as before. **The refusal is the behaviour that
    matters**: swallowing it would produce a session's worth of correct trials
    nobody was paid for, which is what `welfare.Absent` exists to prevent arrived
    at by a different route.
    """

    class Broken:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    link = Simulated()
    spec = _spec(tmp_path, trials=200)
    session = Session(
        spec, card=Card(), pump=Broken(), link=link, wall_clock=lambda: WALL_NOW
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=WALL_NOW)

    with pytest.raises(RuntimeError, match="solenoid"):
        session.run()

    assert "solenoid" in link.published[-1].stopped_because, (
        "the last frame a broken rig ever publishes does not name the fault"
    )
    assert "solenoid" in session.stopped_because


def test_a_refused_welfare_bounded_set_reaches_the_session_record(tmp_path):
    """PI, 2026-09-19. A refusal used to reach telemetry and nothing else, and
    telemetry is lossy by design (S9a §9) -- so an attempt to set a dose above its
    limit left no durable trace at all unless a console happened to be attached and
    happened to still have the row. The durable record is what a welfare question
    is answered from months later."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="reward_correct", value=0.90, by="jake"))

    session.run()

    rows = [
        json.loads(line)
        for line in (session.directory / "refusals.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["name"] == "reward_correct"
    assert rows[0]["by"] == "jake"
    assert rows[0]["asked"] == 0.90
    assert "0.4" in rows[0]["why"], "the row does not say what the ceiling was"


def test_a_recorded_refusal_says_where_in_the_session_it_happened(tmp_path):
    """A row whose whole reason for existing is "this is asked months later" has to
    say *when* within the session, or a reader has only an ordering. `trial_index`
    is the trial about to run and `session_seconds` is `Session.now()` -- the
    frame-derived clock the trials are timed on, never a wall clock, because a wall
    clock here would invite someone to align a refusal to the neural recording. (The
    out-of-cage ceiling read the same clock until P4d-2a moved it to the wall.)

    The second refusal is queued from `observe`, after trial 0, so it drains on a
    later pass: a row that hardcoded zeros, or read the wrong index, passes on the
    first refusal alone and fails here."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="reward_correct", value=0.90, by="jake"))
    session.observe = lambda condition, values, result: (
        link.queue(SetParameter(name="reward_correct", value=0.80, by="sam"))
        if not link._queued
        else None
    )

    session.run()

    rows = [
        json.loads(line)
        for line in (session.directory / "refusals.jsonl").read_text().splitlines()
    ]
    # Four, not three: `observe` queues after each of the three trials, and the
    # pass that finds the block quota filled drains the last one before it stops.
    # A *refused* command is recorded on that pass; an accepted one would be staged
    # and dropped, which is the open item this commit widened -- see
    # `docs/next-session.md` §6.
    assert [row["trial_index"] for row in rows] == [0, 1, 2, 3]
    assert rows[0]["session_seconds"] == 0.0
    assert rows[1]["session_seconds"] > 0.0, "every row reads as the session's start"
    seconds = [row["session_seconds"] for row in rows]
    assert seconds == sorted(seconds) and len(set(seconds)) == 4
    assert [row["by"] for row in rows] == ["jake", "sam", "sam", "sam"]


def test_an_ordinary_parameter_typo_stays_out_of_the_session_record(tmp_path):
    """The other half, and the reason this is not simply "record every refusal". A
    mistyped task-parameter name is a person's slip at a keyboard, not a welfare
    event; writing every one of them into the session record would bury the
    ceiling refusals that matter among the ones that do not. It is still on the
    live feed every console sees."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="not_a_parameter", value=1.0, by="jake"))

    session.run()

    assert not (session.directory / "refusals.jsonl").exists()
    assert len(session.refusals) == 1, "and it is still on the console's feed"


def _refusal_rows(session: Session) -> list[dict]:
    return [
        json.loads(line)
        for line in (session.directory / "refusals.jsonl").read_text().splitlines()
    ]


def _flood(link, n: int) -> None:
    """`n` ceiling refusals with distinguishable asked-values, so a test can tell
    which end of the flood survived."""
    for i in range(n):
        link.queue(SetParameter(name="reward_correct", value=1.0 + i / 100, by="jake"))


def test_the_recorded_refusal_log_keeps_the_first_rows_not_the_last(tmp_path):
    """PI, 2026-09-19: `refusals.jsonl` is bounded, and it keeps the **oldest**.

    The opposite of `Telemetry.refusals`, deliberately, and the asymmetry is the
    decision rather than an oversight. A console feed answers "what is happening
    now", so it keeps the newest. A session record answers "what happened", and a
    flood of refusals is a fault or a misbehaving console while a *genuine* mistake
    appears early -- when a person is typing. Keeping the last fifty of a thousand
    would discard the only rows a human wrote.
    """
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    _flood(link, REFUSAL_LOG_LIMIT + 12)

    session.run()

    rows = _refusal_rows(session)
    kept = [row for row in rows if not row.get("truncated")]
    assert len(kept) == REFUSAL_LOG_LIMIT
    assert kept[0]["asked"] == 1.0, "the first refusal fell off"
    assert kept[-1]["asked"] == pytest.approx(1.0 + (REFUSAL_LOG_LIMIT - 1) / 100)


def test_a_truncated_refusal_log_says_so_and_says_how_many_are_missing(tmp_path):
    """A cap that reads as a quiet session is the silent drop the count exists to
    prevent -- the same argument as `Telemetry.refusals_dropped`, one layer down and
    on the durable side, where there is no live console to have noticed."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    _flood(link, REFUSAL_LOG_LIMIT + 12)

    session.run()

    rows = _refusal_rows(session)
    assert rows[-1]["truncated"] is True, "the log was capped and does not say so"
    assert rows[-1]["dropped"] == 12
    assert rows[-1]["kept"] == REFUSAL_LOG_LIMIT
    assert len(rows) == REFUSAL_LOG_LIMIT + 1, "one notice, not one per drop"


def test_an_untruncated_refusal_log_carries_no_notice_row(tmp_path):
    """The notice is evidence of a cap, so a session nobody flooded must not carry
    one -- a reader who saw it on every session would stop reading it."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    _flood(link, 3)

    session.run()

    rows = _refusal_rows(session)
    assert len(rows) == 3
    assert not any(row.get("truncated") for row in rows)


def test_the_sessions_own_refusal_list_is_capped_like_the_other_two(tmp_path):
    """`ZmqLink.refused` and `Telemetry.refusals` are both bounded at
    `REFUSAL_HISTORY` with the discards counted, because the party driving their
    growth is an untrusted network peer rather than the operator. `Session.refusals`
    is driven by exactly the same peer -- one entry per `SetParameter` it refuses,
    as fast as it can send them -- and was the third list, unbounded. Two bounded
    and one not is not a policy."""
    link = Simulated()
    spec = _spec(tmp_path, trials=3)
    session = _session(spec, link=link)
    for n in range(REFUSAL_HISTORY + 10):
        link.queue(SetParameter(name=f"not_a_parameter_{n}", value=1.0, by="jake"))

    session.run()

    assert len(session.refusals) == REFUSAL_HISTORY
    assert session.refusals_dropped == 10
    assert session.refusals[-1][0] == f"not_a_parameter_{REFUSAL_HISTORY + 9}", (
        "the newest must survive the cap"
    )
    assert link.published[0].refusals_dropped == 10, (
        "a capped list read as a quiet session, which is the silent drop the count "
        "exists to prevent"
    )


def test_a_session_that_finishes_its_blocks_says_it_completed(tmp_path):
    link = Simulated()
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert link.published[-1].stop_kind == "completed"
    assert link.published[-1].phase == "running"


def test_a_session_a_console_stopped_says_an_operator_stopped_it(tmp_path):
    link = Simulated()
    link.queue(Stop(by="jake"))
    session = _session(_spec(tmp_path, trials=50), link=link)

    session.run()

    assert session.stop_kind == "operator"
    assert link.published[-1].stop_kind == "operator"


def test_a_session_ended_by_its_out_of_cage_ceiling_says_limit(tmp_path):
    link = Simulated()
    session = _session(_spec(tmp_path, trials=10_000), link=link)

    session.run()

    assert "out_of_cage" in session.stopped_because
    assert session.stop_kind == "limit"
    assert link.published[-1].stop_kind == "limit"


def test_a_session_ended_by_a_fault_says_fault(tmp_path):
    class Broken:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    link = Simulated()
    session = Session(
        _spec(tmp_path, trials=200),
        card=Card(),
        pump=Broken(),
        link=link,
        wall_clock=lambda: WALL_NOW,
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=WALL_NOW)

    with pytest.raises(RuntimeError, match="solenoid"):
        session.run()

    assert session.stop_kind == "fault"
    assert link.published[-1].stop_kind == "fault"


def _interrupted_on(monkeypatch, call: int) -> None:
    """Make the `call`-th trial of a session raise `KeyboardInterrupt`, as Ctrl-C at
    the terminal does to whatever the main thread is running."""
    from wl_expcontroller import taskd

    real, calls = taskd.run_trial, [0]

    def run_trial(*args, **kwargs):
        calls[0] += 1
        if calls[0] == call:
            raise KeyboardInterrupt
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", run_trial)


def test_ctrl_c_in_the_loop_stops_the_session_as_an_operator_would(
    tmp_path, monkeypatch
):
    """**P4d-2a final review I4.** `run()` caught `Exception`, and `KeyboardInterrupt`
    is not one, so Ctrl-C at the terminal left the session with no stop reason at
    all: the post-loop frames read `('awaiting_return', None, '')`, breaking the rule
    that `stop_kind` is `None` only while the loop runs. It is an operator's stop,
    made at the terminal rather than from a console, and one frame now says so before
    the interrupt goes on to whoever called `run()`."""
    link = Simulated()
    session = _session(_spec(tmp_path, trials=10), link=link)
    _interrupted_on(monkeypatch, call=3)

    with pytest.raises(KeyboardInterrupt):
        session.run()

    assert session.stopped_because == "interrupted at the terminal"
    assert session.stop_kind == "operator"
    assert link.published[-1].stopped_because == "interrupted at the terminal"
    assert link.published[-1].stop_kind == "operator"


def test_the_sessions_wall_does_not_step_when_the_host_clock_does(
    tmp_path, monkeypatch
):
    """**Ruling 8** (Task 7 fix round 1). With no `wall_clock` injected, the
    session's wall is `time.time()` as it read when the session was created,
    carried forward on a steady clock (`welfare.SessionClock`, since the final
    review's I5). A host clock stepped back an hour -- by NTP or by a person -- would
    otherwise shrink the out-of-cage interval by an hour mid-session, which the frame
    clock the wall replaced never could; a step forward would lengthen it. Every
    steady clock the platform choice could read is stubbed to the same value
    (`welfare.steady_seconds`), so this holds whichever one this host reads, and the
    arithmetic is exact."""
    host, steady = [WALL_NOW], [100.0]
    monkeypatch.setattr(time, "time", lambda: host[0])
    monkeypatch.setattr(time, "monotonic", lambda: steady[0])
    monkeypatch.setattr(time, "clock_gettime", lambda clock: steady[0])
    session = Session(_spec(tmp_path), card=Card(), pump=Pump())

    first = session.wall_now()
    host[0], steady[0] = WALL_NOW - 3_600.0, 105.0
    second = session.wall_now()
    host[0], steady[0] = WALL_NOW + 7_200.0, 110.0
    third = session.wall_now()

    assert first == WALL_NOW
    assert second >= first, "the host clock stepped back and took the session with it"
    assert second == WALL_NOW + 5.0, "five steady seconds passed, and only those"
    assert third == WALL_NOW + 10.0, "a forward step is not taken either"


@pytest.mark.skipif(
    not (hasattr(time, "CLOCK_BOOTTIME") or sys.platform == "darwin"),
    reason="this platform has no steady clock known to count suspend "
    "(welfare.steady_seconds' fallback, which says so)",
)
def test_a_host_that_sleeps_mid_session_does_not_take_the_time_off_the_clock(
    tmp_path, monkeypatch
):
    """**Final review I1.** The anchor used to be carried forward on
    `time.monotonic()`, which stops while the host sleeps -- `mach_absolute_time()` on
    macOS, `CLOCK_MONOTONIC` on Linux. A laptop lid closed for an hour mid-session put
    the session's wall an hour behind: the return typed `now` an hour early, the
    interval an hour short, and `must_stop` an hour late. The session now reads the
    clock `welfare.steady_seconds` chooses, which counts the suspend on both
    platforms; `time.monotonic()` is stubbed to stop, as it does."""
    host, awake, counting = [WALL_NOW], [100.0], [100.0]
    monkeypatch.setattr(time, "time", lambda: host[0])
    monkeypatch.setattr(time, "monotonic", lambda: awake[0])
    monkeypatch.setattr(time, "clock_gettime", lambda clock: counting[0])
    session = Session(_spec(tmp_path), card=Card(), pump=Pump())

    # Five seconds awake, then an hour asleep.
    awake[0] += 5.0
    counting[0] += 3_605.0
    host[0] += 3_605.0

    assert session.wall_now() == WALL_NOW + 3_605.0


def test_before_the_loop_a_session_has_no_phase(tmp_path):
    session = _session(_spec(tmp_path, trials=3))

    assert session.phase == ""
    assert session.stop_kind is None


def _welfare_notes(session: Session) -> list[dict]:
    path = session.directory / "welfare_notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _chaired(tmp_path, **kwargs) -> Session:
    """A rig session with no head-fixation, so a return is refused for nothing but
    what the test is about."""
    spec = _spec(tmp_path, trials=3, deployment=Deployment.RIG_CHAIRED, **kwargs)
    return Session(spec, card=Card(), pump=Pump(), wall_clock=lambda: WALL_NOW)


def test_a_departure_is_recorded_whether_or_not_anyone_confirmed_it(tmp_path):
    """P4d-2a spec §1 item 2: the one number that bounds a session was in the record
    only when a far mark was confirmed or amended."""
    session = _session(_spec(tmp_path, trials=3), left_cage_ago=60.0)

    rows = _welfare_notes(session)

    assert [row["kind"] for row in rows] == ["departure"]
    assert rows[0]["was"] == WALL_NOW - 60.0
    assert rows[0]["how"] == "terminal"


def test_a_return_is_recorded_with_who_and_how(tmp_path):
    """`how` is an arbitrary label `returned_to_cage` records rather than validates
    -- this pins that it and `by` pass through untouched. Task 8: `"terminal"`
    rather than `"console"`, since a console can no longer be the one calling this."""
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW - 60.0)

    session.returned_to_cage(at=WALL_NOW, by="jake", how="terminal")

    rows = _welfare_notes(session)
    assert [row["kind"] for row in rows] == ["departure", "returned"]
    assert rows[1]["now"] == WALL_NOW
    assert rows[1]["by"] == "jake"
    assert rows[1]["how"] == "terminal"


def test_a_far_return_that_was_confirmed_says_so(tmp_path):
    session = _chaired(tmp_path, bounds=_bounds(out_of_cage=43_200.0))
    session.left_cage(at=WALL_NOW - 7_200.0, confirmed=True)

    session.returned_to_cage(at=WALL_NOW - 3_600.0, confirmed=True, by="jake")

    kinds = [row["kind"] for row in _welfare_notes(session)]
    assert kinds == ["departure", "returned", "return confirmed"]


def test_a_refused_return_writes_no_row(tmp_path):
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW - 60.0)

    with pytest.raises(Exceeded, match="before|negative"):
        session.returned_to_cage(at=WALL_NOW - 120.0)

    assert [row["kind"] for row in _welfare_notes(session)] == ["departure"]


def test_a_return_nobody_recorded_says_why(tmp_path):
    """`return_not_recorded` records whatever reason it is given verbatim -- this
    pins the pass-through, not any one reason's exact wording (`cli._close_interval`
    owns that; see `test_a_headless_run_records_that_nobody_could_mark_the_return`
    in `tests/test_cli.py`)."""
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW - 60.0)

    session.return_not_recorded("no terminal")

    rows = _welfare_notes(session)
    assert rows[-1]["kind"] == "return not recorded"
    assert rows[-1]["reason"] == "no terminal"


def test_the_session_says_when_a_return_needs_a_person(tmp_path):
    session = _chaired(tmp_path, bounds=_bounds(out_of_cage=43_200.0))
    session.left_cage(at=WALL_NOW - 7_200.0, confirmed=True)

    assert session.return_needs_confirmation(WALL_NOW - 60.0) is None
    assert "Confirm it" in session.return_needs_confirmation(WALL_NOW - 3_600.0)


def test_a_refused_departure_writes_no_row(tmp_path):
    """The symmetric case to `test_a_refused_return_writes_no_row`: a mark `welfare`
    refuses is not in the record either, because `_note` is only ever called after
    `welfare` has accepted."""
    session = _chaired(tmp_path)

    with pytest.raises(Exceeded, match="future"):
        session.left_cage(at=WALL_NOW + 60.0)

    assert _welfare_notes(session) == []


def test_a_failed_row_write_is_never_swallowed(tmp_path, monkeypatch):
    """P4d-2a spec §3: `_note` writes only after `welfare` has already taken the
    mark, so a failed write cannot be retried -- a second attempt would call
    `welfare.returned_to_cage` again and be refused by its own sentence, with the
    file still holding no row. This pins that the failure surfaces rather than
    being caught and turned into an `Exceeded` (or anything else) in this module."""
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW - 60.0)

    def _disk_full(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("wl_expcontroller.taskd.welfare_note", _disk_full)

    with pytest.raises(OSError, match="disk full"):
        session.returned_to_cage(at=WALL_NOW)


class _Wall:
    """A wall clock a test can move by hand -- and, while `follow` is set, one that
    advances with a session's frames, at `pace` wall seconds per frame second.

    **Ruling 10** (P4d-2a final review). With every welfare duration on the wall, a
    session whose wall stood still could never reach its out-of-cage ceiling, so a
    mutant that stops sessions finishing -- `scheduler.record` neutered -- ran eight
    tests here forever instead of failing them, and the harness read `timed out`.
    Following the frames while the loop runs puts the ceiling back in reach at
    simulated speed, as `_session`'s wall does. A test about the post-loop clock then
    calls `still()` and moves the wall by hand from wherever the loop left it.
    """

    def __init__(self, at: float) -> None:
        self.at = at
        self.follow = None
        self.pace = 1.0

    def __call__(self) -> float:
        if self.follow is None:
            return self.at
        return self.at + self.pace * self.follow()

    def still(self) -> None:
        """Stop following the frames, keeping the reading it had."""
        self.at = self()
        self.follow = None


def _trial_budget(spec: SessionSpec):
    """An `observe` hook that fails a session whose scheduler never finishes.

    **For the one session no wall can bound**: a cage-side session has no
    out-of-cage ceiling at all, so following the frames ends nothing (Ruling 10).
    Ten times the declared trials, and a hundred more, is far past anything a
    working scheduler runs here -- a hang is the only way a trial goes uncounted.
    """
    allowed, seen = 10 * spec.trials + 100, [0]

    def observe(condition, values, result) -> None:
        seen[0] += 1
        if seen[0] > allowed:
            raise RuntimeError(
                f"{seen[0]} trials in a session of {spec.trials}: its scheduler is "
                f"not finishing, and nothing else ends a cage-side session"
            )

    return observe


def _until(predicate, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def _awaiting(session: Session, **kwargs) -> tuple[threading.Thread, threading.Event]:
    give_up = threading.Event()
    thread = threading.Thread(
        target=session.await_return, args=(give_up,), kwargs={"heartbeat": 0.01, **kwargs}
    )
    thread.start()
    return thread, give_up


def _fixed_and_run(tmp_path, link, wall) -> Session:
    """A head-fixed session, run to the end of its loop against `wall`.

    `RIG_FIXED`, this file's default kind and `wlx run`'s, and the one with a
    restraint cross-check to fail. This was `_chaired_and_run`, `RIG_CHAIRED`, until
    P4d-2a moved every welfare duration to the wall (spec §10): none of its callers
    is about chairing, and chaired sessions mark no head-fixation, so the
    frame-against-wall mismatch that refused a head-fixed session's post-loop frames
    never ran here.

    **The wall follows the frames while the loop runs, and stands still after it**
    (Ruling 10), so the loop ends -- at `_bounds()`' 800 s ceiling if nothing else
    ends it -- and each caller moves the wall by hand for the post-loop clock it is
    about. Three trials put the loop's end a few seconds after `WALL_NOW`.
    """
    spec = _spec(tmp_path, trials=3)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=wall)
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=wall())
    wall.follow = session.now
    session.run()
    wall.still()
    return session


def test_after_the_loop_the_out_of_cage_clock_keeps_running_on_the_wall(tmp_path):
    """P4d-2a spec §1 item 4: the clock went dark when the loop ended."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 600.0

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        frame = link.published[-1]
        assert frame.out_of_cage_seconds == pytest.approx(600.0)
        assert frame.stop_kind == "completed"
    finally:
        give_up.set()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert link.published[-1].phase == "awaiting_return", "no return, so never closed"


def test_past_the_limit_after_the_loop_the_warning_says_so(tmp_path):
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 900.0  # `_bounds()`' ceiling is 800 s

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        assert "against a ceiling of" in link.published[-1].duration_warning
    finally:
        give_up.set()
        thread.join(timeout=2)


def test_the_closed_frame_tells_nobody_to_bring_back_an_animal_already_home(
    tmp_path,
):
    """**P4d-2a final review I2**, reproduced by the reviewer: a ceiling of 800 s and a
    return at 60 s left the closed frame reading "has 740 s left ... finish the block
    and start bringing the animal back". That frame is the last one a console keeps,
    and in production any return between 11h30 and 12h would have left it. A return
    inside the warning band now closes the interval with no warning at all."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 120.0

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        assert link.published[-1].duration_warning is not None, "open, it warns"
        session.returned_to_cage(at=WALL_NOW + 60.0, by="jake")
        assert _until(lambda: session.phase == "closed")
    finally:
        give_up.set()
        thread.join(timeout=2)

    closed = link.published[-1]
    assert closed.phase == "closed"
    assert closed.out_of_cage_seconds == pytest.approx(60.0)
    assert closed.duration_warning is None


def test_a_return_past_the_ceiling_closes_with_no_warning_on_any_frame(tmp_path):
    """The other band of I2: the animal came home after the limit. `must_stop` is
    what speaks past the ceiling while the interval is open, and once it is closed
    nothing warns -- the out-of-cage clock on the frame, and the stop reason, carry
    the fact. **Including the one stale frame** a return recorded between
    `await_return`'s check and its publish can produce (Task 5's deferred minor):
    `phase` still reads `awaiting_return` there, and `must_stop`'s "recorded as back
    in its cage" sentence used to go out as the warning."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 900.0  # `_bounds()`' ceiling is 800 s
    session.phase = "awaiting_return"  # where `await_return` has put it
    assert "against a ceiling of" in session.duration_warning(wall()), "open, past it"

    session.returned_to_cage(at=WALL_NOW + 850.0, by="jake")

    assert session.phase == "awaiting_return", "the window before the closed frame"
    assert session.duration_warning(wall()) is None
    session.phase = "closed"
    assert session.duration_warning(wall()) is None


def test_while_the_loop_runs_each_frame_carries_the_sessions_own_warning(tmp_path):
    """The other half of `Session.duration_warning`: while the loop runs, it is
    `welfare.approaching_limit`'s sentence (PI, 2026-09-20: a warning, so a block can
    be finished deliberately). **Task 10 found this half pinned by nothing.**
    `Telemetry.of` reads the warning through `Session.duration_warning` since P4d-2a,
    and `test_link.py` checks `Telemetry.of` against a stand-in whose
    `duration_warning` is a lambda, so a real session that said nothing until the loop
    ended failed no test. The harness could not see it: neutering the whole method is
    caught by the post-loop test above.

    `warn_within` is 1,800 s against `_bounds()`' 800 s ceiling, so the threshold
    spans the whole session and every running frame must warn. The wall follows the
    frames (Ruling 10), so each frame's sentence names the time left at that frame's
    own reading: the first is `approaching_limit`'s at the departure, asked before
    the loop, and every one says what its own out-of-cage clock leaves."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    spec = _spec(tmp_path, trials=3, warn_within=1_800.0)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=wall)
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=WALL_NOW)
    first = session.welfare.approaching_limit(WALL_NOW)
    wall.follow = session.now
    session.run()

    running = [frame for frame in link.published if frame.phase == "running"]
    assert running, "the loop published its frames"
    assert first is not None, "the threshold spans the ceiling"
    assert running[0].duration_warning == first
    for frame in running:
        left = f"has {800.0 - frame.out_of_cage_seconds:.0f} s left of its 800 s"
        assert left in (frame.duration_warning or ""), frame


def test_a_head_fixed_session_whose_frames_outran_the_wall_publishes_after_the_loop(
    tmp_path,
):
    """**The simulator finding, at the session** (P4d-2a spec §10). The frame clock is
    counted, not waited for, so a simulated session's frames run far ahead of the
    wall. Two hundred trials here carry at least a hundred frame-clock seconds of
    inter-trial interval alone while the injected wall, following the frames at a
    hundredth of their pace (Ruling 10), moves a few seconds in all.

    While the welfare clocks read the frame base, this `RIG_FIXED` session's release
    landed at its frame-clock end, hundreds of seconds after its fixation, and the
    first post-loop frame read out-of-cage through the wall: the minute before the
    session plus the wall's few seconds, beside hundreds of seconds of restraint,
    which `out_of_cage_seconds` refuses as impossible. On the wall alone, both
    intervals are the wall's, and the frame is the wall's too.
    """
    link, wall = Simulated(), _Wall(WALL_NOW)
    spec = _spec(tmp_path, trials=200)
    # The ceiling is not what this is about and must not end the loop -- two hundred
    # trials move this wall a few seconds -- but it must be *reachable*: a scheduler
    # that never finishes then ends here at simulated speed, not never (Ruling 10).
    spec.bounds = _bounds(out_of_cage=120.0)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=wall)
    session.left_cage(at=WALL_NOW - 60.0)
    session.head_fixed(at=WALL_NOW)
    # The wall follows the frames at a hundredth of their pace.
    wall.follow, wall.pace = session.now, 0.01

    session.run()
    wall.still()
    assert session.stop_kind == "completed", "the ceiling must not end the loop"
    assert session.now() >= 100.0, "the frames must outrun the wall, or this is idle"
    assert wall.at == pytest.approx(WALL_NOW + session.now() / 100.0)

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        frame = link.published[-1]
        assert frame.out_of_cage_seconds == pytest.approx(wall.at - (WALL_NOW - 60.0))
        assert frame.chair_seconds == pytest.approx(session.now() / 100.0), (
            "restraint is the wall's too"
        )
    finally:
        give_up.set()
        thread.join(timeout=2)
    assert not thread.is_alive(), "the post-loop phase did not end when given up"


def test_the_terminal_can_record_the_return_while_await_return_is_polling(tmp_path):
    """The shape `cli._close_interval` actually drives: `await_return` runs on a
    background thread, publishing the clock, while the terminal calls
    `returned_to_cage` from a different thread once a person answers.

    **Task 8:** this used to queue a console's `ReturnedToCage` on the link and let
    `await_return`'s own drain notice it -- that route is gone, the PI having ruled
    the wl-works ELN owns the return rather than a console, so `link.py` carries no
    such command any more. The terminal is the one caller of `returned_to_cage` left
    in production, and it calls it directly, from a thread of its own, exactly as
    reproduced here."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 120.0

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        session.returned_to_cage(at=WALL_NOW + 60.0, by="jake")
        assert _until(lambda: session.phase == "closed")
    finally:
        give_up.set()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert link.published[-1].phase == "closed"
    assert link.published[-1].out_of_cage_seconds == pytest.approx(60.0)
    assert [r["kind"] for r in _welfare_notes(session)][-1] == "returned"


def test_after_the_loop_a_parameter_or_a_stop_is_refused_not_applied(tmp_path):
    """Review Focus 5."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))
    link.queue(Stop(by="sam"))

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: len(session.refusals) == 2)
    finally:
        give_up.set()
        thread.join(timeout=2)

    assert [(n, b) for n, b, _ in session.refusals] == [("fix_hold", "jake"), ("stop", "sam")]
    assert all("waiting for the animal's return" in why for _, _, why in session.refusals)
    assert session.staged == ()
    assert session.stop_kind == "completed", "a late stop changes nothing"


def test_a_fault_skipped_the_release_and_the_return_can_still_land(tmp_path):
    """Review Focus 4, and P4d-2a spec §1 item 3: a fault re-raises past the release
    at the end of `run()`, and `welfare` refuses a return for a head still fixed.
    `await_return` releases it before its own loop runs.

    **Task 8:** the return itself is the terminal's alone now, called from another
    thread once the release has happened -- the same shape `cli._close_interval`
    drives -- not the link's: the console route this test used to land it by is
    gone."""

    class Broken:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    link = Simulated()
    session = Session(
        _spec(tmp_path, trials=200), card=Card(), pump=Broken(), link=link,
        wall_clock=lambda: WALL_NOW,
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=WALL_NOW)
    with pytest.raises(RuntimeError, match="solenoid"):
        session.run()
    assert session.welfare.released_wall_at is None, "the gap this test closes"

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: session.welfare.released_wall_at is not None)
        session.returned_to_cage(at=WALL_NOW, by="jake")
        assert _until(lambda: session.phase == "closed")
    finally:
        give_up.set()
        thread.join(timeout=2)

    assert session.welfare.released_wall_at is not None
    assert session.welfare.returned_wall_at is not None
    assert link.published[-1].phase == "closed"
    assert link.published[-1].stop_kind == "fault"


def test_a_card_fault_releasing_the_head_after_the_loop_is_published_then_raised(
    tmp_path,
):
    """**Final review M7.** The head release `await_return` makes on entry sat outside
    its fault handler, so a card that failed strobing `HEAD_RELEASED` escaped with no
    fault frame -- the session's last word stayed whatever the loop said, and a
    console could not tell the post-loop phase had failed. It is inside now, and gets
    the one frame naming the fault that everything else there gets.

    `give_up` is set by a timer, as in the test above, so a release that no longer
    raises ends this with `DID NOT RAISE` rather than polling forever."""

    class Broken:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    link, card = Simulated(), Card()
    session = Session(
        _spec(tmp_path, trials=200), card=card, pump=Broken(), link=link,
        wall_clock=lambda: WALL_NOW,
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=WALL_NOW)
    with pytest.raises(RuntimeError, match="solenoid"):
        session.run()
    published = len(link.published)

    def emit(code: int) -> None:
        raise OSError("the card did not answer")

    card.emit = emit
    give_up = threading.Event()
    deadline = threading.Timer(5.0, give_up.set)
    deadline.start()
    try:
        with pytest.raises(OSError, match="did not answer"):
            session.await_return(give_up, heartbeat=0.01)
    finally:
        deadline.cancel()

    assert len(link.published) == published + 1, "one frame naming the fault"
    assert link.published[-1].stop_kind == "fault"
    assert "after the loop" in link.published[-1].stopped_because
    assert "the card did not answer" in link.published[-1].stopped_because


def _cage_side_bounds() -> Bounds:
    """A cage-side config (S13, see `test_welfare._home_bounds`): the same fluid
    floor as `_bounds()` but **no `out_of_cage` ceiling** -- `welfare.Welfare`
    refuses a `Deployment.CAGE_SIDE` session declared *with* one, since the animal
    never left home and there is no interval for that ceiling to bound."""
    return Bounds(
        subject="A",
        ceilings={"reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL")},
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )


def test_a_cage_side_session_has_no_return_to_await(tmp_path):
    link = Simulated()
    spec = _spec(
        tmp_path, trials=3, deployment=Deployment.CAGE_SIDE, bounds=_cage_side_bounds()
    )
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=lambda: WALL_NOW)
    session.observe = _trial_budget(spec)
    session.run()
    published = len(link.published)

    session.await_return(threading.Event(), heartbeat=0.01)

    assert len(link.published) == published


def test_await_return_before_the_loop_is_refused(tmp_path):
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW)

    with pytest.raises(RuntimeError, match="before run"):
        session.await_return(threading.Event())


def test_a_fault_after_the_loop_is_published_then_raised(tmp_path, monkeypatch):
    """Fix round 1: a fault raised while `await_return`'s own loop is running must
    mirror `run()`'s one-frame-then-propagate rule rather than leaving `phase` stuck
    at `awaiting_return` forever with no fault frame, which is what a background
    thread dying with an unjoined traceback would otherwise look like from a
    console.

    **Task 8:** this used to reproduce the fault through a queued console
    `ReturnedToCage` reaching a failed `_note` write, drained from inside this
    loop -- that route is gone, and `returned_to_cage` runs only on the terminal's
    own thread now (`test_a_failed_row_write_is_never_swallowed` above already pins
    that a failed write there is not swallowed). What is still `await_return`'s own
    work to fail at is publishing a frame, so this drives the same
    publish-then-raise contract through that instead: the loop's first `publish()`
    raises, and the `except` block's own recovery `publish()` -- the one frame
    naming the fault -- must still get out before the original exception does."""

    calls: list = []

    def _boom(telemetry) -> None:
        calls.append(telemetry)
        if len(calls) == 1:
            raise OSError("disk full")

    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    monkeypatch.setattr(link, "publish", _boom)

    # **Bounded, so a loop that never publishes fails here rather than hanging**
    # (Task 10's mutation gate). `await_return` ends only on a return, a fault or
    # `give_up`, and this test supplies no return, so its only way out is the
    # publish it expects to fail. With `Session._publish` neutered that publish
    # never happens, and an unset `give_up` kept this call -- on the test's own
    # thread -- looping until the harness's 300 s timeout, which it reported as
    # "timed out" rather than as a test noticing. The timer sets `give_up` long
    # after a working `_publish` has raised; if it fires, `pytest.raises` reports
    # the missing exception.
    give_up = threading.Event()
    deadline = threading.Timer(5.0, give_up.set)
    deadline.start()
    try:
        with pytest.raises(OSError, match="disk full"):
            session.await_return(give_up, heartbeat=0.01)
    finally:
        deadline.cancel()

    assert len(calls) == 2, "the fault frame must still be published after the first fails"
    assert session.stop_kind == "fault"
    assert "disk full" in session.stopped_because


# ---------------------------------------------------------------------------
# Task 9: the in-session clock, apart from out-of-cage (P4d-2a spec §10 item 3)
# ---------------------------------------------------------------------------


def test_open_writes_a_session_opened_row_and_a_second_call_raises(tmp_path):
    wall = _Wall(WALL_NOW)
    spec = _spec(
        tmp_path, trials=3, deployment=Deployment.CAGE_SIDE, bounds=_cage_side_bounds()
    )
    session = Session(spec, card=Card(), pump=Pump(), wall_clock=wall)

    session.open()

    assert session.opened_wall_at == WALL_NOW
    rows = _welfare_notes(session)
    assert [row["kind"] for row in rows] == ["session opened"]
    assert rows[0]["was"] == WALL_NOW

    with pytest.raises(RuntimeError, match="open"):
        session.open()


def test_end_refuses_before_open_and_a_second_call_after(tmp_path):
    wall = _Wall(WALL_NOW)
    spec = _spec(
        tmp_path, trials=3, deployment=Deployment.CAGE_SIDE, bounds=_cage_side_bounds()
    )
    session = Session(spec, card=Card(), pump=Pump(), wall_clock=wall)

    with pytest.raises(RuntimeError, match="open"):
        session.end()

    session.open()
    wall.at = WALL_NOW + 42.0
    session.end()

    assert session.ended_wall_at == WALL_NOW + 42.0
    rows = _welfare_notes(session)
    assert [row["kind"] for row in rows] == ["session opened", "session ended"]
    assert rows[-1]["was"] == WALL_NOW + 42.0

    with pytest.raises(RuntimeError, match="end"):
        session.end()


def test_run_opens_the_in_session_clock_itself_if_nothing_has(tmp_path):
    """The backstop for a direct API user who never calls `open()` -- `wlx run`
    calls it explicitly and earlier still (`tests/test_cli.py`), so this is the
    only path that ever reaches `run()`'s own call."""
    session = _session(_spec(tmp_path, trials=3))
    assert session.opened_wall_at is None

    session.run()

    assert session.opened_wall_at is not None
    kinds = [row["kind"] for row in _welfare_notes(session)]
    # `_session()` already marked the departure before `run()` was ever called
    # (see its own docstring), so `session opened` lands second here -- this test
    # is about `run()` opening the clock at all, not about row order, which
    # `tests/test_cli.py` pins for `wlx run`'s own call sequence.
    assert kinds == ["departure", "session opened"]


def test_in_session_seconds_advances_with_the_wall_and_stops_after_end(tmp_path):
    """P4d-2a spec §10 item 3: `Telemetry.in_session_seconds` reads
    `(ended_wall_at or wall_now) - opened_wall_at` -- `None` before `open()`, moving
    with the wall while the session is open, and frozen the instant `end()` has run.

    Cage-side, so no departure or head-fixation mark is needed just to ask
    `Telemetry.of` for a frame -- `welfare.out_of_cage_seconds` answers `None`
    outright rather than requiring one, and this test is about the clock `welfare`
    never sees at all.
    """
    wall = _Wall(WALL_NOW)
    spec = _spec(
        tmp_path, trials=3, deployment=Deployment.CAGE_SIDE, bounds=_cage_side_bounds()
    )
    session = Session(spec, card=Card(), pump=Pump(), wall_clock=wall)
    scheduler = Scheduler(
        blocks=[Block(name="only", conditions=[Condition("only", {}, target=1)])],
        seed=0,
    )
    tally = Tally()

    def frame() -> Telemetry:
        return Telemetry.of(session, tally, scheduler, index=0)

    assert session.opened_wall_at is None
    assert frame().in_session_seconds is None, "no clock before open()"

    session.open()
    assert frame().in_session_seconds == pytest.approx(0.0)

    wall.at = WALL_NOW + 90.0
    assert frame().in_session_seconds == pytest.approx(90.0), "moves with the wall"

    wall.at = WALL_NOW + 150.0
    session.end()
    assert frame().in_session_seconds == pytest.approx(150.0)

    wall.at = WALL_NOW + 999.0
    assert frame().in_session_seconds == pytest.approx(150.0), (
        "must not advance after end()"
    )


def test_the_in_session_clock_bounds_nothing(tmp_path):
    """P4d-2a spec §10 item 3, in the brief's own words: **it bounds nothing.** A
    session open thirteen hours by the wall, whose departure was only an hour ago,
    must have `must_stop` and `approaching_limit` say nothing about it -- both read
    `welfare` alone, and `welfare` never receives `opened_wall_at`/`ended_wall_at`
    (nothing in this file passes either to it, and `Welfare.__init__` takes no such
    argument)."""
    wall = _Wall(WALL_NOW)
    # Twelve hours: comfortably past the thirteen the in-session clock will read,
    # so a `must_stop`/`approaching_limit` answer here can only be about the
    # departure, one hour old, never about the in-session clock this test is
    # actually asking about.
    spec = _spec(tmp_path, trials=3, bounds=_bounds(out_of_cage=43_200.0))
    session = Session(spec, card=Card(), pump=Pump(), wall_clock=wall)
    session.open()

    # Thirteen hours after the session opened -- the reading everything below is
    # taken at -- with the departure marked an hour before *that* instant, not
    # before the session's own opening.
    wall.at = WALL_NOW + 13 * 3_600.0
    session.left_cage(at=wall.at - 3_600.0, confirmed=True)

    scheduler = Scheduler(
        blocks=[Block(name="only", conditions=[Condition("only", {}, target=1)])],
        seed=0,
    )
    frame = Telemetry.of(session, Tally(), scheduler, index=0)
    assert frame.in_session_seconds == pytest.approx(13 * 3_600.0), (
        "the session really has been open thirteen hours"
    )

    assert session.welfare.must_stop(session.wall_now()) is None
    assert session.welfare.approaching_limit(session.wall_now()) is None
    assert frame.duration_warning is None


# --- what the browser console reads (P4d-2b b1) ------------------------------


def test_a_session_keeps_the_last_sixty_outcomes_as_the_record_wrote_them(tmp_path):
    """Spec §4.1: the Runtime pane's ticks. **The record's own strings**, `hang`
    included: one string is computed and handed to both, so a tick can never say what
    `trials.jsonl` does not."""
    session = _session(_spec(tmp_path, trials=100))
    assert session.recent_outcomes == ()

    session.run()

    recorded = [
        json.loads(line)["outcome"]
        for line in (session.directory / "trials.jsonl").read_text().splitlines()
    ]
    assert len(recorded) == 100
    assert session.recent_outcomes == tuple(recorded[-RECENT_OUTCOMES:])
    assert len(session.recent_outcomes) == RECENT_OUTCOMES == 60


def test_the_parameters_a_console_shows_are_the_declarations_then_the_ceilings(
    tmp_path,
):
    """Spec §3: the parameter pane is generated from `params`. The task's own
    declarations with their current values, then each ceiling a console could stage
    -- and not the out-of-cage ceiling, which is the limit a clock runs against and
    not a task setting."""
    session = _session(_spec(tmp_path))
    declared = _load_trial(Path("tasks/fixation_detection.py")).params

    rows = session.parameters
    by_name = {row[0]: row for row in rows}

    assert [row[0] for row in rows[: len(declared)]] == [p.name for p in declared]
    fix_hold = next(p for p in declared if p.name == "fix_hold")
    assert by_name["fix_hold"] == (
        "fix_hold",
        fix_hold.unit,
        fix_hold.low,
        fix_hold.high,
        0.3,
        False,
    )
    assert by_name["reward_correct"] == ("reward_correct", "mL", 0.0, 0.40, 0.15, True)
    assert "out_of_cage" not in by_name


def test_a_parameter_nobody_set_is_unset_not_zero(tmp_path):
    spec = _spec(tmp_path)
    del spec.values["fix_hold"]
    session = _session(spec)

    values = {row[0]: row[4] for row in session.parameters}

    assert values["fix_hold"] is None


def test_the_config_snapshot_names_the_bounded_config_it_ran_under(tmp_path):
    """S9a §3's "which bounded config" had no source: `SessionSpec` holds `Bounds`,
    never the file it came from. It is recorded where the task and allocation are."""
    session = _session(_spec(tmp_path, trials=2, bounds_config="subjects/A/bounds.py"))

    session.run()

    config = json.loads((session.directory / "config.json").read_text())
    assert config["versions"]["bounds"] == "subjects/A/bounds.py"


# ---------------------------------------------------------------------------
# M8 (P4d-2b b2a): a malformed setting is refused and never ends the session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value", "said"),
    [
        ("fix_hold", "abc", "'fix_hold' takes a number (s)"),
        ("fix_hold", True, "'fix_hold' takes a number (s)"),
        ("reward_correct", "lots", "'reward_correct' is a welfare ceiling and takes a number"),
        ("reward_correct", False, "'reward_correct' is a welfare ceiling and takes a number"),
    ],
)
def test_a_malformed_setting_is_refused_and_the_session_runs_on(tmp_path, name, value, said):
    """M8, the backstop behind the decoder: a value that is not a number reaches
    `Session.set` only from inside this process (the wire refuses it first), and it is
    refused with a sentence rather than raising `TypeError` out of `bounds._finite`,
    which `run()`'s fault handler turned into the end of the session."""
    link = Simulated()
    link.queue(SetParameter(name=name, value=value, by="jake"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert [(n, b) for n, b, _ in session.refusals] == [(name, "jake")]
    assert said in session.refusals[0][2]


def test_a_type_error_in_a_setting_is_a_refusal_not_a_fault(tmp_path, monkeypatch):
    """The spec's second half of M8: `Session._command` refuses on a `TypeError` too,
    so no check `set` does not yet make can end a session with an animal in the
    chair."""

    def raises(self, name, value, by):
        raise TypeError("must be real number, not list")

    monkeypatch.setattr(Session, "set", raises)
    link = Simulated()
    link.queue(SetParameter(name="fix_hold", value=[0.4], by="jake"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    assert session.stop_kind == "completed"
    (refusal,) = session.refusals
    assert refusal[:2] == ("fix_hold", "jake")
    assert "could not be checked" in refusal[2]
    assert "must be real number, not list" in refusal[2]


def test_a_malformed_ceiling_write_is_recorded_as_asked(tmp_path):
    """A refused write to a welfare ceiling goes to the session record (PI,
    2026-09-19), a malformed one included, with what was asked written as it came."""
    link = Simulated()
    link.queue(SetParameter(name="reward_correct", value="lots", by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    (row,) = _refusal_rows(session)
    assert row["name"] == "reward_correct"
    assert row["asked"] == "lots"
    assert row["by"] == "jake"


def test_a_command_the_session_does_not_act_on_is_refused_not_a_fault(tmp_path):
    """A command type `_command` has no branch for -- a newer console's, say -- is
    refused under its kind and the session runs on, the rule `drain` already applies
    to an unknown kind on the wire."""

    class Recenter:
        KIND = "recenter"

        def __init__(self, by: str) -> None:
            self.by = by

    link = Simulated()
    link.queue(Recenter(by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.refusals == [
        ("recenter", "jake", "a 'recenter' command is not one this session acts on, so it is refused")
    ]


# ---------------------------------------------------------------------------
# P4d-2b b2a: pause and resume (spec §5.1)
# ---------------------------------------------------------------------------

#: The three framework codes b2a allocates (`tasks/allocation.py`).
PAUSE_CODE, RESUME_CODE, MARK_CODE = 4131, 4132, 4133

#: How many times a `_Scripted` session may drain its commands. The loop drains once
#: at each trial boundary and once in each paused wait, so these sessions -- a few
#: trials, at most a few hundred waits -- stay far below it.
PASS_BUDGET = 2_000


class _Scripted(Simulated):
    """A link whose `idle` -- the paused loop's one wait -- runs a script: on its Nth
    call it queues `script[N]`, moves `wall` on by `step` seconds, and calls `each`.

    **Ruling 10, for a paused loop**: a session still paused after `budget` waits
    fails -- `idle` raises, the session faults -- rather than holding the suite until
    the mutation harness kills it, which is what a neutered `Resume` would otherwise
    do here. **And for a paused loop that never waits**: with `Session._hold`
    neutered, the loop goes round the boundary draining and publishing with no trial
    and no `idle`, so neither budget moves and the suite hung until the harness's
    300 s; a session that drains more than `PASS_BUDGET` times fails the same way."""

    def __init__(self, script=None, wall=None, step=0.0, budget=200, each=None):
        super().__init__()
        self.script = dict(script or {})
        self.wall = wall
        self.step = step
        self.budget = budget
        self.each = each
        self.waits: list = []
        self.drains = 0

    def drain(self) -> list:
        self.drains += 1
        if self.drains > PASS_BUDGET:
            raise RuntimeError(
                f"drained {PASS_BUDGET} times: the loop is going round with no trial "
                f"and no wait (tests/test_taskd.py, Ruling 10)"
            )
        return super().drain()

    def idle(self, timeout: float) -> int:
        self.waits.append(timeout)
        if len(self.waits) > self.budget:
            raise RuntimeError(
                f"still paused after {self.budget} waits: nothing ended the pause "
                f"(tests/test_taskd.py, Ruling 10)"
            )
        if self.wall is not None:
            self.wall.at += self.step
        for command in self.script.get(len(self.waits), ()):
            self.queue(command)
        if self.each is not None:
            self.each()
        return super().idle(timeout)


def _walled(tmp_path, link, *, trials: int = 5, **spec) -> tuple[Session, "_Wall"]:
    """A head-fixed session whose wall follows its frames while trials run and moves
    only when a test moves it while paused (`_Scripted.step`)."""
    wall = _Wall(WALL_NOW)
    session = Session(
        _spec(tmp_path, trials=trials, **spec),
        card=Card(),
        pump=Pump(),
        link=link,
        wall_clock=wall,
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=wall())
    # The frames' seconds, on top of wherever `at` stands: a paused wait moves `at`.
    wall.follow = session.now
    return session, wall


def _controls_rows(session: Session) -> list[dict]:
    path = session.directory / "controls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_pause_holds_the_session_at_a_boundary_and_resume_continues(tmp_path):
    """Spec §5.1: at the next trial boundary the loop holds -- no trial runs -- and
    resume continues. Both are strobed so the recording shows the gap, and nothing
    else is strobed inside it."""
    link = _Scripted(script={3: [Resume(by="sam")]}, step=30.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "completed"
    assert len(link.waits) == 3
    codes = session.card.codes
    assert codes.count(PAUSE_CODE) == 1 and codes.count(RESUME_CODE) == 1
    assert codes.index(RESUME_CODE) == codes.index(PAUSE_CODE) + 1, (
        "something was strobed while paused: a trial ran"
    )
    trials = (session.directory / "trials.jsonl").read_text().splitlines()
    assert len(trials) == 5
    held = [frame.trial_index for frame in link.published if frame.trial_index == 0]
    assert len(held) >= 4, "the paused loop published once per wait at trial 0"


def test_pause_and_resume_are_recorded_with_who_and_when(tmp_path):
    """Spec §5.1: every control is written to the session record with who sent it and
    when -- the instant on the session's anchored clock, as a number and as a clock
    time."""
    link = _Scripted(script={3: [Resume(by="sam")]}, step=30.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    pause, resume = _controls_rows(session)
    assert (pause["kind"], pause["by"], pause["trial_index"]) == ("pause", "jake", 0)
    assert (resume["kind"], resume["by"], resume["trial_index"]) == ("resume", "sam", 0)
    assert resume["paused_s"] == pytest.approx(90.0)
    assert resume["at"] - pause["at"] == pytest.approx(90.0)
    assert pause["at_local"].endswith("local")


def test_a_stop_is_recorded_with_who_and_when(tmp_path):
    """Spec §5.1: every control is written to the session record with who sent it and
    when. A console's stop was in telemetry and at the terminal and nowhere on disk."""
    link = Simulated()
    link.queue(Stop(by="sam"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    (row,) = _controls_rows(session)
    assert (row["kind"], row["by"], row["trial_index"]) == ("stop", "sam", 0)
    assert row["at"] == WALL_NOW
    assert session.controls[0][3] == "stopped by sam"


def test_nothing_is_rewarded_while_paused(tmp_path):
    """Human review item 1 (spec §5.5): while paused, nothing is rewarded. No trial
    runs, so no `Reward` action reaches the pump, and the session's fluid stands
    still. Paused after six trials, so what stands still is not zero.

    `before` is read at the moment the pause is decided -- before `_pause` runs and
    before `_hold`'s `while` is entered -- because `seen`'s first reading is taken
    inside the first `idle`, which is after both. A delivery added in `_pause`, or
    at the top of `_hold` ahead of the loop, would land between `before` and
    `seen[0]` and pass unseen by `seen` alone (review item 2)."""
    seen: list = []
    before: list = []
    link = _Scripted(script={4: [Resume(by="jake")]}, step=10.0)
    session, wall = _walled(tmp_path, link, trials=9)
    link.wall = wall
    link.each = lambda: seen.append(
        (
            session.welfare.session_total(),
            session.welfare.deliveries,
            len(session.pump.delivered),
        )
    )
    ran = [0]

    def pause_after_six(condition, values, result) -> None:
        ran[0] += 1
        if ran[0] == 6:
            before.append(
                (
                    session.welfare.session_total(),
                    session.welfare.deliveries,
                    len(session.pump.delivered),
                )
            )
            link.queue(Pause(by="jake"))

    session.observe = pause_after_six

    session.run()

    assert len(seen) == 4
    assert seen[0][0] > 0.0, "choose a pause point after a reward"
    assert len(set(seen)) == 1, f"fluid moved while paused: {seen}"
    assert seen[0] == before[0], "fluid moved between deciding to pause and the first reading"


def test_the_out_of_cage_limit_still_ends_a_paused_session(tmp_path):
    """Human review item 1 (spec §5.5): the out-of-cage clock keeps running while
    paused, and `welfare.must_stop` still ends the session on it, exactly as between
    trials. The wall moves five minutes per wait; `_bounds()`' limit is 800 s."""
    link = _Scripted(step=300.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "limit"
    assert session.stopped_because.startswith("out_of_cage")
    assert len(link.waits) == 3, "800 s is past after the third five-minute wait"
    assert not (session.directory / "trials.jsonl").read_text().strip(), "no trial ran"
    clocks = [frame.out_of_cage_seconds for frame in link.published]
    assert clocks == sorted(clocks) and clocks[-1] > 800.0, "the clock kept running"
    assert link.published[-1].stop_kind == "limit"


def test_the_limit_still_ends_a_paused_session_with_refused_commands_on_the_way(tmp_path):
    """Regression (review round 1, item 3a): a refused command drained on a paused
    pass must not change when the out-of-cage limit ends the session. `_ends` is
    asked at the end of every pass in `_hold`, busy or not, so a `SetParameter` for
    an undeclared parameter -- refused, changing nothing -- drained on every pass on
    the way to the limit still lets it land on the same wait as with no commands at
    all (`test_the_out_of_cage_limit_still_ends_a_paused_session`)."""
    refuse = [SetParameter(name="not_a_parameter", value=1.0, by="jake")]
    link = _Scripted(script={1: refuse, 2: refuse, 3: refuse}, step=300.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "limit"
    assert session.stopped_because.startswith("out_of_cage")
    assert len(link.waits) == 3, "the limit still lands on the third wait, same as with no commands"
    assert not (session.directory / "trials.jsonl").read_text().strip(), "no trial ran"
    assert len(session.refusals) == 3


def test_the_limit_still_ends_a_paused_session_with_a_mark_stamped_on_every_wait(tmp_path):
    """Task 6 review (welfare evidence for `_hold`): a mark stamped on a paused pass
    must not change when the out-of-cage limit ends the session, mirroring
    `test_the_limit_still_ends_a_paused_session_with_refused_commands_on_the_way` for
    a mark instead of a refused command. `_hold`'s own mark check stamps whatever
    `link.idle` hands back before `_ends` is asked (spec §5.1), so a mark on every
    wait must still let the limit land on the same wait as with no marks at all
    (`test_the_out_of_cage_limit_still_ends_a_paused_session`, wait 3), run no trial,
    and leave one `mark` control row behind for every wait that stamped one."""
    link = _Scripted(step=300.0)
    # The leading 0 is `_check_marks`'s own pre-pause check, at the top of `run()`'s
    # loop before `Pause` is even drained; 1-5 are `_hold`'s waits, a new mark number
    # on each -- more than the three this run needs.
    link.marks = [0, 1, 2, 3, 4, 5]
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "limit"
    assert session.stopped_because.startswith("out_of_cage")
    assert len(link.waits) == 3, "the limit still lands on the third wait, same as with no marks"
    assert not (session.directory / "trials.jsonl").read_text().strip(), "no trial ran"
    marks = [row for row in _controls_rows(session) if row["kind"] == "mark"]
    assert len(marks) == 3, "one mark row per wait before the end"


def test_the_limit_still_ends_a_paused_session_when_a_resume_lands_the_same_pass(tmp_path):
    """Regression (review round 1, item 3b): a resume landing in the same drain as
    the pass that crosses the out-of-cage limit does not race it. `_resume` clears
    `paused_at` and strobes `RESUME`, then `_hold` asks `_ends` before it loops back
    to check `paused_at` again, so the limit still ends the session on that same
    pass and `run()` never reaches a trial."""
    link = _Scripted(script={3: [Resume(by="jake")]}, step=300.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "limit"
    assert session.stopped_because.startswith("out_of_cage")
    assert len(link.waits) == 3, "the limit still lands on the third wait, same as with no resume"
    assert RESUME_CODE in session.card.codes, "the resume still strobed before the limit ended it"
    assert not (session.directory / "trials.jsonl").read_text().strip(), "no trial ran after the pause"


def test_a_setting_staged_while_paused_applies_when_trials_resume(tmp_path):
    """Spec §5.1: settings staged while paused apply when trials resume -- at the top
    of the pass that runs the next trial, recorded and strobed there."""
    link = _Scripted(
        script={1: [SetParameter(name="fix_hold", value=0.4, by="sam")], 3: [Resume(by="jake")]}
    )
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=3)
    link.wall = wall

    session.run()

    assert _parameter_changes(session)[0]["now"] == 0.4
    rows = [json.loads(line) for line in (session.directory / "trials.jsonl").read_text().splitlines()]
    assert [row["params"]["fix_hold"] for row in rows] == [0.4, 0.4, 0.4]


def test_stop_while_paused_ends_the_session(tmp_path):
    link = _Scripted(script={2: [Stop(by="sam")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "operator"
    assert session.stopped_because == "stopped by sam"
    assert len(link.waits) == 2


def test_a_second_pause_and_a_resume_with_nothing_paused_are_refused(tmp_path):
    """A double click sends two pauses; the second is said, not stacked, and a stray
    resume is said too. Neither strobes."""
    link = _Scripted(script={2: [Resume(by="jake"), Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=2)
    link.wall = wall

    session.run()

    assert [(n, why.split(";")[0]) for n, _, why in session.refusals] == [
        ("pause", "the session is already paused"),
        ("resume", "the session is not paused"),
    ]
    assert session.card.codes.count(PAUSE_CODE) == 1
    assert session.card.codes.count(RESUME_CODE) == 1


def test_a_pause_pressed_after_a_stop_is_refused_and_the_session_ends(tmp_path):
    """Review Focus 3: pause pressed while a stop is already on its way. Both land in
    one drain; the stop ends the session at that boundary, and the pause is refused
    with a sentence rather than holding a session that is ending."""
    link = _Scripted()
    link.queue(Stop(by="sam"))
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stopped_because == "stopped by sam"
    assert link.waits == [], "a stopping session never held"
    ((name, by, why),) = session.refusals
    assert (name, by) == ("pause", "jake")
    assert "the session is stopping (stopped by sam)" in why
    assert PAUSE_CODE not in session.card.codes


def test_a_resume_pressed_after_a_stop_is_refused_and_the_session_ends(tmp_path):
    """Important review item 1: a resume that reaches a paused session after a stop
    in the same drain resumes nothing. Both land in one drain, inside `_hold`; the
    stop ends the session at that boundary, and the resume is refused with a
    sentence -- mirroring `_pause`'s guard -- rather than strobing `RESUME`, writing
    a "resumed" row for a pause that never ended, and clearing `paused_at` on a
    session whose own field contract says a stop keeps it set."""
    link = _Scripted(script={2: [Stop(by="sam"), Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert RESUME_CODE not in session.card.codes
    assert [row["kind"] for row in _controls_rows(session)] == ["pause", "stop"]
    ((name, by, why),) = session.refusals
    assert (name, by) == ("resume", "jake")
    assert "the session is already stopping" in why
    assert session.paused_at is not None, "a stop keeps paused_at, as the field says"
    assert session.stopped_because == "stopped by sam"
    assert session.stop_kind == "operator"


def test_a_pause_is_refused_when_the_allocation_cannot_mark_it(tmp_path):
    """A pause the recording cannot show is refused rather than taken silently: the
    allocation must carry both `PAUSE` and `RESUME`, so the gap has two ends."""
    from dataclasses import replace

    link = _Scripted()
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=2)
    link.wall = wall
    session.allocation = replace(
        session.allocation,
        task_events={
            code: name
            for code, name in session.allocation.task_events.items()
            if name != "RESUME"
        },
    )

    session.run()

    assert session.stop_kind == "completed"
    ((name, _, why),) = session.refusals
    assert name == "pause"
    assert "no RESUME event code" in why
    assert link.waits == []


def test_the_paused_loop_waits_one_housekeeping_interval_at_a_time(tmp_path):
    link = _Scripted(script={2: [Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=1)
    link.wall = wall

    session.run()

    assert link.waits == [PAUSE_HOUSEKEEPING_S, PAUSE_HOUSEKEEPING_S]


def test_after_the_loop_a_pause_or_a_resume_is_refused_not_applied(tmp_path):
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    link.queue(Pause(by="jake"))
    link.queue(Resume(by="sam"))

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: len(session.refusals) == 2)
    finally:
        give_up.set()
        thread.join(timeout=2)

    assert [(n, b) for n, b, _ in session.refusals] == [("pause", "jake"), ("resume", "sam")]
    assert session.paused_at is None


def test_the_control_feed_keeps_the_newest_and_counts_what_fell_off(tmp_path):
    """The feed a console shows is bounded like the refusal feed, and a cap never
    reads as a quiet session. The record keeps every row."""
    pairs = CONTROL_HISTORY // 2 + 10
    # Resumed and paused again in one drain, so the loop stays held, and resumed for
    # good on the last wait: `pairs` pauses and `pairs` resumes.
    script = {n: [Resume(by="jake"), Pause(by="jake")] for n in range(1, pairs)}
    script[pairs] = [Resume(by="jake")]
    link = _Scripted(script=script, budget=2 * pairs)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=1)
    link.wall = wall

    session.run()

    assert len(session.controls) == CONTROL_HISTORY
    assert session.controls_dropped == 2 * pairs - CONTROL_HISTORY
    assert len(_controls_rows(session)) == 2 * pairs
    kinds = [row[0] for row in session.controls]
    assert kinds[-1] == "resume"


# ---------------------------------------------------------------------------
# P4d-2b b2a: marks, stamped in the frame they arrive (spec §5.0, §5.1)
# ---------------------------------------------------------------------------

#: `fixation_detection`'s first code on entering a trial, and the markers a trial ends
#: on (`codes._standing_outcomes`).
FIX_ON = 4096
MARKERS = {34, 35, 36, 37, 38}


class _MarkAfter(Simulated):
    """A link whose mark check answers `mark` on the `calls`-th check after it is
    armed, and zero otherwise -- so a test chooses the frame a mark arrives in."""

    def __init__(self, mark: int, calls: int) -> None:
        super().__init__()
        self.mark = mark
        self.calls = calls
        self.armed = False
        self.seen = 0

    def mark_signal(self) -> int:
        if not self.armed:
            return 0
        self.seen += 1
        if self.seen == self.calls:
            return self.mark
        return 0


def _trial_codes(codes: list, trial: int) -> list:
    """The codes strobed during trial `trial` (0-based): from its `FIX_ON` to its
    ending marker."""
    starts = [i for i, code in enumerate(codes) if code == FIX_ON]
    start = starts[trial]
    end = next(i for i in range(start, len(codes)) if codes[i] in MARKERS)
    return codes[start : end + 1]


def test_a_mark_is_strobed_and_stamped_in_the_frame_it_arrives(tmp_path):
    """Spec §5.0, the PI's ruling: marks must be instant -- stamped in the frame they
    reach the rig, not at the next trial boundary. Armed after the second trial, the
    link answers on its eleventh check: the first is the boundary's, so the mark
    arrives in the third trial's tenth frame, and that is where the code is strobed
    and what the record names."""
    link = _MarkAfter(mark=77, calls=11)
    session = _session(_spec(tmp_path, trials=4), link=link)
    ran = [0]

    def arm_after_two(condition, values, result) -> None:
        ran[0] += 1
        if ran[0] == 2:
            link.armed = True

    session.observe = arm_after_two

    session.run()

    assert MARK_CODE in _trial_codes(session.card.codes, 2)
    assert session.card.codes.count(MARK_CODE) == 1
    (stamp,) = _controls_rows(session)
    assert (stamp["kind"], stamp["mark"], stamp["number"]) == ("mark", 77, 1)
    assert (stamp["trial_index"], stamp["frame"]) == (2, 10)
    assert stamp["strobed"] is True
    assert session.controls[0][3] == "mark 1 stamped in trial 2, frame 10"


def test_a_mark_between_trials_is_stamped_at_the_boundary_with_no_frame(tmp_path):
    link = Simulated()
    link.marks.append(5)
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    (stamp,) = _controls_rows(session)
    assert (stamp["trial_index"], stamp["frame"]) == (0, None)
    assert session.controls[0][3] == "mark 1 stamped between trials, before trial 0"
    assert session.card.codes.index(MARK_CODE) < session.card.codes.index(FIX_ON)


def test_a_mark_while_paused_is_stamped_when_it_arrives(tmp_path):
    class _MarkWhilePaused(_Scripted):
        def idle(self, timeout: float) -> int:
            super().idle(timeout)
            return 9 if len(self.waits) == 2 else 0

    link = _MarkWhilePaused(script={3: [Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=1)
    link.wall = wall

    session.run()

    pause, stamp, resume = _controls_rows(session)
    assert (pause["kind"], stamp["kind"], resume["kind"]) == ("pause", "mark", "resume")
    assert (stamp["mark"], stamp["frame"]) == (9, None)
    assert session.controls[1][3] == "mark 1 stamped while paused, before trial 0"
    codes = session.card.codes
    assert codes.index(PAUSE_CODE) < codes.index(MARK_CODE) < codes.index(RESUME_CODE)


def test_a_note_joins_its_stamp_with_the_three_instants_and_their_gaps(tmp_path):
    """Spec §5.1: the record keeps when M was pressed (the browser's clock), when
    `wlx serve` received it (its clock), and when the rig stamped it (the session's
    anchored clock and frame), and the gaps between them are recorded, never hidden.
    The note arrives as a `Mark` command and is joined to its stamp by number."""
    link = Simulated()
    link.marks.append(5)
    link.queue(
        Mark(
            mark=5,
            note="reward line bubble",
            by="jake (box, unverified)",
            pressed_at=WALL_NOW - 2.0,
            received_at=WALL_NOW - 1.5,
        )
    )
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    stamp, note = _controls_rows(session)
    assert note["kind"] == "note" and note["by"] == "jake (box, unverified)"
    assert (note["mark"], note["number"], note["note"]) == (5, 1, "reward line bubble")
    assert note["pressed_at"] == WALL_NOW - 2.0
    assert note["received_at"] == WALL_NOW - 1.5
    assert note["stamped_at"] == stamp["at"] == WALL_NOW
    assert note["received_after_pressed_s"] == pytest.approx(0.5)
    assert note["stamped_after_received_s"] == pytest.approx(1.5)
    assert (note["stamped_in_trial"], note["frame"]) == (0, None)
    assert session.controls[1][1:] == (
        "jake (box, unverified)", session.controls[1][2], 'mark 1: "reward line bubble"'
    )


def test_a_note_left_bare_and_a_note_whose_instants_are_unknown_still_record(tmp_path):
    """Esc leaves the mark bare; a `wlx serve` restarted between the signal and the
    note knows no instants. Both are recorded as they are, never filled in."""
    link = Simulated()
    link.marks.append(5)
    link.queue(Mark(mark=5, note="", by="jake", pressed_at=None, received_at=None))
    session = _session(_spec(tmp_path, trials=1), link=link)

    session.run()

    _, note = _controls_rows(session)
    assert note["note"] == ""
    assert note["received_after_pressed_s"] is None
    assert note["stamped_after_received_s"] is None
    assert session.controls[1][3] == "mark 1: no note"


def test_a_note_for_a_mark_this_session_never_stamped_says_so(tmp_path):
    link = Simulated()
    link.queue(Mark(mark=99, note="lost?", by="jake", pressed_at=None, received_at=None))
    session = _session(_spec(tmp_path, trials=1), link=link)

    session.run()

    (note,) = _controls_rows(session)
    assert note["number"] is None and note["stamped_at"] is None
    assert session.controls[0][3] == 'a note for mark 99, which this session never stamped: "lost?"'


def test_two_marks_pressed_fast_are_two_stamps_in_order(tmp_path):
    """Review Focus 2: M pressed twice fast. Two signals, two numbers, two codes, in
    order, neither lost -- the check reads one per frame, so the second is stamped in
    the next frame and its row names that frame."""
    link = Simulated()
    link.marks.extend([5, 6])
    session = _session(_spec(tmp_path, trials=1), link=link)

    session.run()

    first, second = _controls_rows(session)
    assert (first["mark"], first["number"], first["frame"]) == (5, 1, None)
    assert (second["mark"], second["number"], second["trial_index"], second["frame"]) == (6, 2, 0, 1)
    assert session.card.codes.count(MARK_CODE) == 2


def test_a_mark_the_allocation_cannot_strobe_is_stamped_and_says_so(tmp_path):
    """A mark cannot be refused -- it has already been pressed -- so without an
    `OPERATOR_MARK` code it is recorded unstrobed, and the feed says so rather than
    implying the recording has it."""
    from dataclasses import replace

    link = Simulated()
    link.marks.append(5)
    session = _session(_spec(tmp_path, trials=1), link=link)
    session.allocation = replace(
        session.allocation,
        task_events={
            code: name
            for code, name in session.allocation.task_events.items()
            if name != "OPERATOR_MARK"
        },
    )

    session.run()

    (stamp,) = _controls_rows(session)
    assert stamp["strobed"] is False
    assert session.controls[0][3].endswith(
        "; not strobed: this session's allocation has no OPERATOR_MARK event code"
    )
    assert MARK_CODE not in session.card.codes


def test_a_mark_in_a_trial_that_faults_is_still_recorded(tmp_path, monkeypatch):
    """The strobe is on the recording the instant it happens; the record row is
    written at the boundary after, and a trial that faults has no boundary after, so
    the stamps it holds are written as the session closes."""
    from wl_expcontroller import taskd

    def faults(trial, world, frame_period, values=None, effects=None, each_frame=None):
        each_frame(1)
        raise RuntimeError("the display went away")

    monkeypatch.setattr(taskd, "run_trial", faults)
    link = Simulated()
    link.marks.extend([0, 8])  # nothing at the boundary; mark 8 in frame 1
    session = _session(_spec(tmp_path, trials=3), link=link)

    with pytest.raises(RuntimeError, match="the display went away"):
        session.run()

    (stamp,) = _controls_rows(session)
    assert (stamp["mark"], stamp["trial_index"], stamp["frame"]) == (8, 0, 1)


# ---------------------------------------------------------------------------
# P4d-2b b2a: the scheduled stop (spec §5.1), held by `taskd`
# ---------------------------------------------------------------------------


@pytest.fixture
def utc(monkeypatch):
    """The host's zone as UTC, so a clock time names one instant whatever zone the
    suite runs in. `WALL_NOW` is 2023-11-14 22:13:20 UTC."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _scheduled_at_trial(link, session, after: int, *commands) -> None:
    """Queue `commands` once `after` trials have run, through `observe`."""
    ran = [0]

    def queue(condition, values, result) -> None:
        ran[0] += 1
        if ran[0] == after:
            for command in commands:
                link.queue(command)

    session.observe = queue


def _trials_run(session: Session) -> int:
    return len((session.directory / "trials.jsonl").read_text().splitlines())


def test_a_stop_after_n_trials_ends_the_session_there_with_its_reason(tmp_path):
    """Spec §5.1: after N more trials, counted from when the schedule is accepted,
    shown as the target trial number. It stops the session like the stop button --
    `stop_kind` `operator` -- with the reason *scheduled stop (...) set by NAME*."""
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=3, by="jake"))
    session = _session(_spec(tmp_path, trials=50), link=link)

    session.run()

    assert _trials_run(session) == 3
    assert session.stop_kind == "operator"
    assert session.stopped_because == "scheduled stop (after trial 3) set by jake"
    assert session.scheduled_stop is None, "a stop that has happened is spent"
    assert link.published[-1].scheduled_stop is None
    rows = _controls_rows(session)
    assert [row["kind"] for row in rows] == ["schedule", "scheduled_stop"]
    assert (rows[0]["stop"], rows[0]["target"], rows[0]["said"]) == ("trials", 3.0, "after trial 3")
    assert rows[1]["by"] == "jake"


def test_after_n_trials_counts_from_when_the_schedule_is_accepted(tmp_path):
    link = Simulated()
    session = _session(_spec(tmp_path, trials=50), link=link)
    _scheduled_at_trial(link, session, 2, ScheduleStop(kind="trials", value=3, by="jake"))

    session.run()

    assert _trials_run(session) == 5
    assert session.stopped_because == "scheduled stop (after trial 5) set by jake"


def test_a_stop_at_a_clock_time_is_read_on_the_sessions_clock(tmp_path, utc):
    """At a clock time on the rig's session clock (spec §5.1): the next occurrence of
    that time, on the session's anchored clock -- `wall_now`, which here follows the
    frames from `WALL_NOW` (22:13:20) -- so 22:14 is forty seconds in."""
    link = Simulated()
    link.queue(ScheduleStop(kind="clock", value="22:14", by="jake"))
    session = _session(_spec(tmp_path, trials=500), link=link)

    session.run()

    assert session.stopped_because == "scheduled stop (at 22:14) set by jake"
    (schedule, fired) = _controls_rows(session)
    assert schedule["target"] == WALL_NOW + 40.0
    assert fired["at"] >= WALL_NOW + 40.0
    frames = [frame.wall_at for frame in link.published]
    assert frames[-3] < WALL_NOW + 40.0 <= frames[-1], "it stopped at the first boundary past 22:14"


def test_a_clock_time_already_past_or_exactly_now_is_tomorrows(tmp_path, utc):
    """Review Focus 4: a scheduled time that is past, or exactly now, is the next
    occurrence of it -- tomorrow's -- as the spec rules, and the feed and the strip
    say which day, so a slip of the hour is read rather than waited for."""
    from wl_expcontroller.taskd import _next_occurrence

    assert _next_occurrence("22:14", WALL_NOW) == WALL_NOW + 40.0
    assert _next_occurrence("22:13", WALL_NOW) == WALL_NOW - 20.0 + 86_400.0
    assert _next_occurrence("22:13", WALL_NOW - 20.0) == WALL_NOW - 20.0 + 86_400.0
    assert _next_occurrence("00:00", WALL_NOW) == WALL_NOW + 6_400.0

    link = Simulated()
    link.queue(ScheduleStop(kind="clock", value="22:13", by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.scheduled_stop[3] == "at 22:13 on 2023-11-15"
    assert session.controls[0][3] == "scheduled stop at 22:13 on 2023-11-15"


def test_a_stop_after_fluid_reads_welfares_session_fluid(tmp_path):
    """After X mL this session, read from `welfare`'s session fluid (spec §5.1) --
    `session_total()`, the figure the console shows -- and nothing else."""
    link = Simulated()
    link.queue(ScheduleStop(kind="fluid", value=0.3, by="jake"))
    session = _session(_spec(tmp_path, trials=200), link=link)

    session.run()

    assert session.stopped_because == "scheduled stop (after 0.3 mL this session) set by jake"
    assert session.welfare.session_total() >= 0.3
    before_last = [frame.fluid_session_ml for frame in link.published][-3]
    assert before_last < 0.3, "it stopped at the first boundary at or past 0.3 mL"


def test_a_new_schedule_replaces_the_old_and_says_so(tmp_path):
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=2, by="jake"))
    link.queue(ScheduleStop(kind="trials", value=4, by="sam"))
    session = _session(_spec(tmp_path, trials=50), link=link)

    session.run()

    assert _trials_run(session) == 4
    assert session.stopped_because == "scheduled stop (after trial 4) set by sam"
    assert session.controls[1][3] == "scheduled stop after trial 4, replacing after trial 2"


def test_cancel_removes_the_scheduled_stop(tmp_path):
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=2, by="jake"))
    link.queue(CancelScheduledStop(by="sam"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.scheduled_stop is None
    cancel = _controls_rows(session)[1]
    assert (cancel["kind"], cancel["by"], cancel["cancelled"]) == ("cancel", "sam", "after trial 2")


def test_cancel_with_nothing_scheduled_is_refused(tmp_path):
    link = Simulated()
    link.queue(CancelScheduledStop(by="sam"))
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    assert session.refusals == [
        ("cancel", "sam", "there is no scheduled stop to cancel; nothing changed")
    ]


def test_a_malformed_schedule_that_never_crossed_the_wire_is_refused(tmp_path):
    """`link.check_schedule` is asked again of a schedule that reached the session
    without the wire, so one rule holds on both paths."""
    link = Simulated()
    link.queue(ScheduleStop(kind="clock", value="25:00", by="jake"))
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    ((name, by, why),) = session.refusals
    assert (name, by) == ("schedule", "jake")
    assert "HH:MM" in why and why.endswith("so it is refused")
    assert session.scheduled_stop is None


def test_a_scheduled_stop_ends_a_paused_session(tmp_path, utc):
    """Checked at each trial boundary *and while paused* (spec §5.1)."""
    link = _Scripted(step=30.0)
    link.queue(Pause(by="jake"))
    link.queue(ScheduleStop(kind="clock", value="22:14", by="sam"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stopped_because == "scheduled stop (at 22:14) set by sam"
    assert len(link.waits) == 2, "22:14 passed on the second thirty-second wait"


def test_the_limit_wins_when_it_and_a_schedule_fall_due_together(tmp_path, utc):
    """Both at one check: the out-of-cage limit is asked first, and a session that
    reached it ends as `limit`, never as an operator's stop."""
    link = _Scripted(step=900.0)
    link.queue(Pause(by="jake"))
    link.queue(ScheduleStop(kind="clock", value="22:14", by="sam"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "limit"
    # The premise: a single 900 s wait crosses both the 800 s out-of-cage ceiling
    # and 22:14 (40 s ahead of `WALL_NOW`), so this is genuinely "both due on the
    # same check" and not the limit merely winning a race across several.
    assert len(link.waits) == 1, "both the limit and the schedule are due on the first wait"
    assert session.scheduled_stop is not None, "the schedule was not spent: the limit alone decided this stop"


def _stopped_by_the_operator(tmp_path):
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=1000, by="jake"))
    link.queue(Stop(by="sam"))
    session = _session(_spec(tmp_path, trials=50), link=link)
    session.run()
    return session, link


def _stopped_by_the_limit(tmp_path):
    link = _Scripted(step=900.0)
    link.queue(Pause(by="jake"))
    # A "trials" target far past anything this session reaches: due only on
    # `index`, never on the wall the paused wait moves, so it stays unspent when
    # the limit ends the session -- the case this fix guards, not
    # `test_the_limit_wins_when_it_and_a_schedule_fall_due_together`'s "both due at
    # once", which asks a different question.
    link.queue(ScheduleStop(kind="trials", value=1000, by="sam"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall
    session.run()
    return session, link


def _stopped_by_completion(tmp_path):
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=1000, by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)
    session.run()
    return session, link


@pytest.mark.parametrize(
    ("make", "stop_kind"),
    [
        (_stopped_by_the_operator, "operator"),
        (_stopped_by_the_limit, "limit"),
        (_stopped_by_completion, "completed"),
    ],
    ids=["stop button", "out-of-cage limit", "natural completion"],
)
def test_a_finished_session_publishes_no_scheduled_stop_to_cancel(tmp_path, make, stop_kind):
    """Fix round 1 (review of Task 8, link.py:542-549): `_ends` clears
    `Session.scheduled_stop` only on the one path where the schedule itself fires;
    the stop button, the out-of-cage limit and natural completion all leave an
    unspent schedule on the session -- Task 7's
    `test_the_limit_wins_when_it_and_a_schedule_fall_due_together` depends on exactly
    that for the limit path, so `Session.scheduled_stop` must stay set here too. But
    a console must not be shown an ended session's schedule as one it could still
    cancel: `Telemetry.of` now publishes `scheduled_stop=None` once
    `session.stopped_because` is set, whatever ended it, while the session's own
    field is left alone."""
    session, link = make(tmp_path)

    assert session.stopped_because
    assert session.stop_kind == stop_kind
    assert session.scheduled_stop is not None, "the session's own record must stay unspent"
    assert link.published[-1].scheduled_stop is None, "the last frame must not offer to cancel it"


# ---------------------------------------------------------------------------
# P4d-2b b2a, Task 7 fix round 1: the fluid schedule's rounding, and one guard test
# ---------------------------------------------------------------------------


def test_after_fluid_ends_at_the_amount_not_one_reward_past_it(tmp_path):
    """Important: a sum of same-sized deliveries lands a whisker past a round target
    in a binary float -- ten deliveries of 0.1 mL sum to 0.9999999999999999, not
    1.0 -- so "after 1 mL" must not wait for an eleventh reward before it stops.
    `FLUID_TOLERANCE_ML` is what keeps it at ten rather than eleven."""
    link = Simulated()
    link.queue(ScheduleStop(kind="fluid", value=1.0, by="jake"))
    session = _session(
        _spec(tmp_path, trials=400, bounds=_bounds(reward_correct=0.1)), link=link
    )

    session.run()

    assert session.stopped_because == "scheduled stop (after 1 mL this session) set by jake"
    assert session.welfare.deliveries == 10, "ten deliveries of 0.1 mL, not eleven"


def test_a_fluid_schedule_at_or_below_the_current_total_is_refused(tmp_path):
    """Ruling 2: an "after X mL" schedule the session has already reached would be
    found due at the very next check, so it is refused instead -- named at the
    session's own current total, to two decimals -- and the session runs on. Trials
    and a clock time need no such guard (spec §5.1: trials count forward from now,
    and a past clock time rolls to tomorrow's), so only the fluid kind is refused
    this way."""
    link = Simulated()
    session = _session(
        _spec(tmp_path, trials=400, bounds=_bounds(reward_correct=0.1)), link=link
    )
    queued = [False]

    def queue_once_five_delivered(condition, values, result) -> None:
        if not queued[0] and session.welfare.deliveries >= 5:
            queued[0] = True
            link.queue(ScheduleStop(kind="fluid", value=0.5, by="jake"))

    session.observe = queue_once_five_delivered

    session.run()

    assert session.stop_kind == "completed"
    assert session.scheduled_stop is None, "the schedule was refused, never held"
    schedules = [row for row in session.refusals if row[0] == "schedule"]
    assert len(schedules) == 1
    name, by, why = schedules[0]
    assert by == "jake"
    assert "0.50 mL" in why
    assert why.endswith("use Stop to end it now")


def test_a_schedule_queued_behind_a_stop_in_the_same_drain_is_refused(tmp_path):
    """The pause guard's mirror (`_pause`, `_resume`): a `Stop` drained just ahead of
    a `ScheduleStop` in the same pass leaves the session already stopping, so the
    schedule is refused rather than held for an `_ends` check the session never
    reaches -- the session ends by the `Stop` alone."""
    link = Simulated()
    link.queue(Stop(by="jake"))
    link.queue(ScheduleStop(kind="trials", value=3, by="sam"))
    session = _session(_spec(tmp_path, trials=50), link=link)

    session.run()

    schedules = [row for row in session.refusals if row[0] == "schedule"]
    assert len(schedules) == 1
    name, by, why = schedules[0]
    assert by == "sam"
    assert "a schedule is not applied" in why
    assert session.scheduled_stop is None
    assert session.stopped_because == "stopped by jake"
    assert session.stop_kind == "operator"


def test_an_applied_setting_is_on_the_changes_feed_with_who_and_when(tmp_path):
    """Spec §5.2: the changes feed lists every setting change with who made it. A
    staged row leaves `Telemetry.staged` when it is applied; the feed keeps it, as
    `set`, with the trial it applies from. The record already has it, in
    `parameter_changes.jsonl`, so no control row repeats it there."""
    link = Simulated()
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake (box, unverified)"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    ((kind, by, at, said),) = session.controls
    assert (kind, by) == ("set", "jake (box, unverified)")
    assert said == "fix_hold 0.30 → 0.40, from trial 1"
    assert at >= WALL_NOW
    assert _controls_rows(session) == []
