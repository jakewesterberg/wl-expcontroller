"""`wlx`, the guardrail's only invocable form.

The checks existed only inside tests until this existed. A guardrail nobody can run
against a file is a test, not a guardrail -- so its exit codes are the contract, and
these assert them.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.cli import main

TASKS = "tasks"
GOOD = f"{TASKS}/fixation_detection.py"
ALLOCATION = f"{TASKS}/allocation.py"


def test_a_clean_task_exits_zero(capsys):
    assert main(["check", GOOD, "--allocation", ALLOCATION]) == 0
    assert "no findings" in capsys.readouterr().out


def test_a_task_with_a_blocking_finding_exits_one(tmp_path, capsys):
    """Exit status is the contract: whatever loads a task on a rig, or in CI, has
    to be able to refuse it without parsing prose."""
    bad = tmp_path / "bad_task.py"
    bad.write_text(
        "from wl_expcontroller.task import After, On, Outcome, State, Trial\n"
        "t = Trial(start='a', states=[\n"
        "    State('a', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('orphan', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "])\n"
    )

    assert main(["check", str(bad)]) == 1
    assert "unreachable-state" in capsys.readouterr().out


def test_an_unallocated_code_is_refused_without_an_allocation(capsys):
    """The default allocation has no task events on purpose. A task emitting any
    code fails until a real allocation is loaded, which is correct for a project
    whose whole guardrail is that codes come from elsewhere."""
    assert main(["check", GOOD]) == 1
    assert "unallocated-code" in capsys.readouterr().out


def test_review_renders_the_artifact(capsys):
    assert main(["review", GOOD, "--allocation", ALLOCATION]) == 0
    out = capsys.readouterr().out
    assert "stateDiagram-v2" in out
    assert "Needs human review" in out


def test_a_file_with_no_trial_says_so(tmp_path):
    empty = tmp_path / "empty.py"
    empty.write_text("x = 1\n")

    with pytest.raises(SystemExit, match="0 trials"):
        main(["check", str(empty)])


def test_an_allocation_file_must_define_ALLOCATION(tmp_path):
    """Looked up by name because an allocation module naturally imports another --
    `PROVISIONAL` -- so two are visible and picking "the only one" would be picking
    arbitrarily."""
    bad = tmp_path / "alloc.py"
    bad.write_text("from wl_expcontroller.codes import PROVISIONAL\n")

    with pytest.raises(SystemExit, match="must define ALLOCATION"):
        main(["check", GOOD, "--allocation", str(bad)])
