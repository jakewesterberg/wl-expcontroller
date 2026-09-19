"""`taskd` — running a session end to end.

Roadmap M1's gate: a complete task, headless, deterministic over 1,000 trials, with
the full record on disk. Everything below runs against simulators, and the seam it
runs against is the same one hardware will plug into (S6 §6).

**P4b added the session around the trial loop**: blocks with criterion transitions, a
restraint clock, ceilings that end a session, one validated path for live parameter
writes, and the reward path that reaches `bounds` -- which for a week reached nothing
at all. Several tests below exist to keep a session from being able to run without
those, which is a different claim from their being present.
"""

from __future__ import annotations

import json

import pytest

from wl_expcontroller.bounds import Bounds, Ceiling, Exceeded, Floor
from wl_expcontroller.dio import Simulated as Card
from wl_expcontroller.link import SetParameter, Simulated, Stop
from wl_expcontroller.scheduler import Block, Condition, Counting
from wl_expcontroller.task import Outcome
from wl_expcontroller.taskd import Session, SessionSpec
from wl_expcontroller.welfare import Simulated as Pump

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
        "chair_time": Ceiling(value=14_400.0, maximum=14_400.0, unit="s"),
        # Small enough that a broken scheduler bounds out in seconds rather than
        # grinding to 100,000 trials -- which under a mutation run is a 300-second
        # timeout per function, paid once for every function in the module.
        "max_trials": Ceiling(value=400.0, maximum=100_000.0, unit="trials"),
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
    )
    for name, value in kwargs.items():
        setattr(spec, name, value)
    return spec


def _session(spec, link=None) -> Session:
    """A session wired to simulators, which is the only rig that exists.

    `link` defaults to `None`, i.e. omitted from the call -- `Session.link` then
    falls back to its own default, `link.Absent()`, exactly as a session with no
    console attached does outside a test.
    """
    kwargs = {"link": link} if link is not None else {}
    session = Session(spec, card=Card(), pump=Pump(), **kwargs)
    session.head_fixed(at=0.0)
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
    # The gate's own claim is a thousand trials, so the trial ceiling has to admit
    # them. Everywhere else in this file the ceiling is deliberately small.
    spec.bounds = _bounds(max_trials=1_000.0)
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


def test_a_session_refuses_to_run_before_the_animal_is_in_the_chair(tmp_path):
    """S8 §5.2: head-fixation is required by preflight, because it is what starts the
    restraint clock. A session that started its own clock would be measuring work
    rather than restraint, and setup and calibration would be free."""
    session = Session(_spec(tmp_path, trials=5), card=Card(), pump=Pump())

    with pytest.raises(Exceeded, match="head-fixed"):
        session.run()


def test_a_session_stops_at_its_chair_time_ceiling(tmp_path):
    """Restraint time, not work time. The clock started before the first trial."""
    spec = _spec(tmp_path, trials=1_000)
    spec.bounds = _bounds(chair_time=2.0)
    session = _session(spec)

    census = session.run()

    assert sum(census.outcomes.values()) < 1_000
    assert "chair_time" in session.stopped_because


def test_a_session_stops_at_its_trial_ceiling(tmp_path):
    spec = _spec(tmp_path, trials=1_000)
    spec.bounds = _bounds(max_trials=30.0)
    session = _session(spec)

    census = session.run()

    assert sum(census.outcomes.values()) == 30
    assert "max_trials" in session.stopped_because


def test_head_fixation_is_event_coded_at_both_ends(tmp_path):
    """S8 §5.2: chair time is the one welfare quantity with no hardware line, so the
    codes *are* its durable record and a restart reconstructs the clock from the sync
    box's capture of them."""
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
    ceiling, and the two paths are the same path."""
    session = _session(_spec(tmp_path, trials=4))

    session.set("reward_correct", 0.30, by="console")
    assert session.spec.bounds.value("reward_correct") == 0.30

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


def test_a_session_publishes_once_per_trial(tmp_path):
    """One entry before each trial runs, plus two more at the close: `run()`
    publishes at the top of every pass through `while True:`, and the pass where the
    session discovers its ceiling and stops -- without drawing a sixth trial -- is
    such a pass too, published once before the stop is known (`must_stop`/
    `scheduler.finished` sit *below* that publish) and once more right after, so the
    very last frame names the reason (`publish()` in `run()`). Both final frames
    share `trial_index=5`, one index past the last trial that actually ran; see
    `test_the_last_telemetry_names_a_welfare_ceilings_reason` for the reason itself."""
    link = Simulated()
    spec = _spec(tmp_path)
    spec.bounds = _bounds(max_trials=5)
    session = _session(spec, link=link)

    session.run()

    assert [t.trial_index for t in link.published] == [0, 1, 2, 3, 4, 5, 5]


def test_a_command_from_a_console_lands_at_the_next_boundary_with_its_actor(tmp_path):
    """The console gains no second write path: the command goes through `Session.set`,
    so a welfare-bounded name still meets its ceiling and an undeclared name is still
    refused."""
    link = Simulated()
    spec = _spec(tmp_path)
    spec.bounds = _bounds(max_trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))

    session.run()

    changes = _parameter_changes(session)
    assert changes[0]["name"] == "fix_hold"
    assert changes[0]["by"] == "jake"


def test_a_stop_command_ends_the_session_at_a_boundary_not_mid_trial(tmp_path):
    link = Simulated()
    spec = _spec(tmp_path)
    spec.bounds = _bounds(max_trials=100)
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
    spec = _spec(tmp_path)
    spec.bounds = _bounds(max_trials=3)
    session = _session(spec, link=link)
    link.queue(SetParameter(name="not_a_parameter", value=1.0, by="jake"))

    census = session.run()

    assert sum(census.outcomes.values()) == 3, "the session ran to its trial ceiling"
    assert len(session.refusals) == 1
    assert session.refusals[0][0] == "not_a_parameter"
    assert session.refusals[0][1] == "jake"


# --- the last telemetry frame always names why (S9 "written for a stranger") ------


def test_the_last_telemetry_names_a_welfare_ceilings_reason(tmp_path):
    """A console watching a session hit its trial ceiling must not see the stream go
    quiet with no explanation -- that is precisely the failure the publish-before-
    break ordering exists to prevent, and it must hold for every stop path, not only
    a console-issued `Stop`. Asserts on the reason itself, not a frame count: a count
    assertion would pass even with an empty `stopped_because`."""
    link = Simulated()
    spec = _spec(tmp_path)
    spec.bounds = _bounds(max_trials=5)
    session = _session(spec, link=link)

    session.run()

    assert "max_trials" in link.published[-1].stopped_because
    assert link.published[-1].stopped_because == session.stopped_because


def test_the_last_telemetry_names_a_consoles_stop_reason(tmp_path):
    """The path this was already true for, made explicit against the telemetry a
    console actually reads rather than the session's own attribute."""
    link = Simulated()
    spec = _spec(tmp_path)
    spec.bounds = _bounds(max_trials=100)
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
