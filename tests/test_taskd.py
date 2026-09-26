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
import threading
import time

import pytest

from wl_expcontroller.bounds import Bounds, Ceiling, Exceeded, Floor
from wl_expcontroller.dio import Simulated as Card
from wl_expcontroller.link import (
    REFUSAL_HISTORY,
    SetParameter,
    Simulated,
    Stop,
    Telemetry,
)
from wl_expcontroller.record import REFUSAL_LOG_LIMIT
from wl_expcontroller.scheduler import Block, Condition, Counting, Scheduler
from wl_expcontroller.simulate import Tally
from wl_expcontroller.task import Outcome
from wl_expcontroller.taskd import Session, SessionSpec
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
        # `max_trials` went it is also what bounds a *broken* session here. Small
        # enough that a scheduler whose counts stop advancing runs out of session
        # seconds in a fraction of a wall second rather than grinding on forever --
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


def test_the_sessions_wall_does_not_step_when_the_host_clock_does(
    tmp_path, monkeypatch
):
    """**Ruling 8** (Task 7 fix round 1). With no `wall_clock` injected, the
    session's wall is `time.time()` as it read when the session was created,
    carried forward on `time.monotonic()`. A host clock stepped back an hour -- by
    NTP or by a person -- would otherwise shrink the out-of-cage interval by an hour
    mid-session, which the frame clock the wall replaced never could; a step forward
    would lengthen it. Both clocks are stubbed, so the arithmetic is exact."""
    host, steady = [WALL_NOW], [100.0]
    monkeypatch.setattr(time, "time", lambda: host[0])
    monkeypatch.setattr(time, "monotonic", lambda: steady[0])
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
    """A wall clock a test can move."""

    def __init__(self, at: float) -> None:
        self.at = at

    def __call__(self) -> float:
        return self.at


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
    """
    spec = _spec(tmp_path, trials=3)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=wall)
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=wall())
    session.run()
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


def test_a_head_fixed_session_whose_frames_outran_the_wall_publishes_after_the_loop(
    tmp_path,
):
    """**The simulator finding, at the session** (P4d-2a spec §10). The frame clock is
    counted, not waited for, so a simulated session's frames run far ahead of the
    wall. Two hundred trials here carry at least a hundred frame-clock seconds of
    inter-trial interval alone while the injected wall moves two seconds in all.

    While the welfare clocks read the frame base, this `RIG_FIXED` session's release
    landed at its frame-clock end, hundreds of seconds after its fixation, and the
    first post-loop frame read out-of-cage through the wall: the minute before the
    session plus the wall's two seconds, beside hundreds of seconds of restraint,
    which `out_of_cage_seconds` refuses as impossible. On the wall alone, both
    intervals are the wall's, and the frame is the wall's too.
    """
    link, wall = Simulated(), _Wall(WALL_NOW)
    spec = _spec(tmp_path, trials=200)
    # Twelve hours: the ceiling is not what this is about, and must not end the loop.
    spec.bounds = _bounds(out_of_cage=43_200.0)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=wall)
    session.left_cage(at=WALL_NOW - 60.0)
    session.head_fixed(at=WALL_NOW)
    # The wall creeps a hundredth of a second per trial and stops at two seconds.
    session.observe = lambda condition, values, result: setattr(
        wall, "at", min(wall.at + 0.01, WALL_NOW + 2.0)
    )

    session.run()
    assert session.now() >= 100.0, "the frames must outrun the wall, or this is idle"
    assert wall.at == pytest.approx(WALL_NOW + 2.0)

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        frame = link.published[-1]
        assert frame.out_of_cage_seconds == pytest.approx(wall.at - (WALL_NOW - 60.0))
        assert frame.chair_seconds == pytest.approx(2.0), "restraint is the wall's too"
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

    with pytest.raises(OSError, match="disk full"):
        session.await_return(threading.Event(), heartbeat=0.01)

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
