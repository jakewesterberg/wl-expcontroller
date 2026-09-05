"""Which modules a change needs mutated -- and the guard against one escaping.

The gate got cheaper by running less, so what matters is what it still runs. These
test the selection, and above all `undeclared()`: the workflow's hand-maintained
module list had silently omitted three modules, one of them the **welfare-critical**
one, while `docs/CHECKPOINT.md` described "a mutation gate over every module".
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "wlx_mutation_gate", Path(__file__).resolve().parents[1] / "tools" / "mutation_gate.py"
)
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


# ---------------------------------------------------------------------------
# The guard that made this safe to build at all
# ---------------------------------------------------------------------------


def test_every_module_on_disk_is_declared_or_exempt():
    """The whole reason a selective gate is defensible. A module in neither list is
    ungated, and before this existed three were: `bounds` -- the welfare-critical
    file -- plus `scheduler` and `findings`, none of which the workflow's
    hand-maintained list mentioned. A list you must remember to update is a list
    that is wrong."""
    assert gate.undeclared() == set(), (
        "add these to RETURNS, or to EXEMPT with a reason, in tools/mutation_gate.py"
    )


def test_the_welfare_critical_module_is_gated_not_exempt():
    """Named explicitly so no future tidying can move `bounds` into EXEMPT without a
    test failing. It is the one module CLAUDE.md requires a human to review."""
    assert "bounds" in gate.RETURNS
    assert "bounds" not in gate.EXEMPT


def test_exemptions_carry_a_reason():
    for module, reason in gate.EXEMPT.items():
        assert reason.strip(), f"{module} is exempt without saying why"


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_a_changed_module_selects_itself():
    modules, _ = gate.select(["wl_expcontroller/calibration.py"])
    assert modules == ["calibration"]


def test_a_changed_test_file_selects_the_module_it_covers():
    """Coverage is a property of module and tests together, so editing
    `test_gaze.py` can change whether `gaze.py`'s mutations are caught even though
    `gaze.py` did not move."""
    modules, _ = gate.select(["tests/test_gaze.py"])
    assert modules == ["gaze"]


def test_a_test_file_with_no_module_of_that_name_selects_nothing():
    modules, _ = gate.select(["tests/test_reference_tasks.py"])
    assert modules == []


def test_changes_are_unioned():
    modules, _ = gate.select(
        ["wl_expcontroller/eye.py", "tests/test_dio.py", "README.md"]
    )
    assert modules == ["dio", "eye"]


def test_documentation_alone_selects_nothing():
    modules, why = gate.select(["docs/CHECKPOINT.md", "README.md"])
    assert modules == []
    assert "changed modules" in why


@pytest.mark.parametrize(
    "path",
    ["tests/conftest.py", "tools/mutate.py", "pyproject.toml", ".github/workflows/ci.yml"],
)
def test_a_structural_change_escalates_to_everything(path):
    """These change what every test sees, so reasoning about a subset is not sound.
    Escalating beats being clever about it."""
    modules, why = gate.select([path])
    assert modules == sorted(gate.RETURNS)
    assert path in why


def test_a_task_change_escalates_because_tasks_are_test_inputs():
    modules, why = gate.select(["tasks/visual_search.py"])
    assert modules == sorted(gate.RETURNS)
    assert "tasks/" in why


def test_an_undiffable_base_runs_everything_rather_than_guessing():
    """A first push to a branch reports an all-zero `before`. Selecting nothing there
    would be a gate that silently did not run -- this repository's recurring bug."""
    assert gate.changed_files("0000000000000000000000000000000000000000") is None
    assert gate.changed_files("") is None
    assert gate.changed_files(None) is None


# ---------------------------------------------------------------------------
# The flags the sweeps actually get
# ---------------------------------------------------------------------------


def test_the_returns_flag_matches_what_the_module_needs():
    """`[]` for functions returning lists a caller concatenates, so a failure
    localises to the covering test; `None` elsewhere. Carried over from the workflow
    unchanged, and asserted because a wrong flag makes a sweep weaker without making
    it fail."""
    assert gate.RETURNS["check"] == "[]"
    assert gate.RETURNS["calibration"] == "[]"
    assert gate.RETURNS["run"] == "None"
    assert gate.RETURNS["bounds"] == "None"
