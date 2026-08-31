"""`taskd` — running a session end to end.

Roadmap M1's gate: a complete task, headless, deterministic over 1,000 trials, with
the full record on disk. Everything below runs against simulators, and the seam it
runs against is the same one hardware will plug into (S6 §6).
"""

from __future__ import annotations

import json

from wl_expcontroller.taskd import Session, SessionSpec


def _spec(tmp_path, seed: int = 1, trials: int = 50) -> SessionSpec:
    return SessionSpec(
        task="tasks/fixation_detection.py",
        allocation="tasks/allocation.py",
        root=tmp_path,
        session_id="2027-01-14_01",
        subject="A",
        trials=trials,
        frame_period=1 / 240,
        seed=seed,
        values={
            "fix_timeout": 4.0,
            "fix_hold": 0.3,
            "response_window": 0.6,
            "target_hold": 0.2,
            "fix_window": 2.0,
            "target_window": 3.0,
            "target_position": 10.0,
            "target_looks": None,
        },
    )


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
        Session(spec).run()
    except SystemExit as exit_:
        assert "unreachable-state" in str(exit_)
    else:
        raise AssertionError("a malformed task must not run")


def test_a_session_is_deterministic_for_a_seed(tmp_path):
    """M1's gate says deterministic, and it is the property that makes a simulated
    session evidence: two runs that disagree cannot both be describing the task."""
    first = Session(_spec(tmp_path / "a")).run()
    second = Session(_spec(tmp_path / "b")).run()

    assert first.outcomes == second.outcomes
    assert first.responses == second.responses


def test_a_different_seed_gives_a_different_session(tmp_path):
    """Otherwise the determinism test above passes for the wrong reason."""
    first = Session(_spec(tmp_path / "a", seed=1)).run()
    second = Session(_spec(tmp_path / "b", seed=2)).run()

    assert first.outcomes != second.outcomes


def test_a_session_writes_its_record_and_its_config(tmp_path):
    Session(_spec(tmp_path, trials=20)).run()

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
    census = Session(_spec(tmp_path, trials=1_000)).run()

    trials = (
        tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
    ).read_text().splitlines()

    assert len(trials) == 1_000
    assert sum(census.outcomes.values()) == 1_000
    assert census.hangs == 0
    assert census.states_visited == {"await_fix", "hold_fix", "stim_on", "verify"}
    assert len(census.outcomes) >= 4, "a session reaching one outcome tests nothing"
