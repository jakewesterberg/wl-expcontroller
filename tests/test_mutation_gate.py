"""Which modules a change needs mutated -- and the guard against one escaping.

The gate got cheaper by running less, so what matters is what it still runs. These
test the selection, and above all `undeclared()`: the workflow's hand-maintained
module list had silently omitted three modules, one of them the **welfare-critical**
one, while `docs/CHECKPOINT.md` described "a mutation gate over every module".
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
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
    modules, _ = gate.select(["wl_xcon/calibration.py"])
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
        ["wl_xcon/eye.py", "tests/test_dio.py", "README.md"]
    )
    assert modules == ["dio", "eye"]


def test_documentation_alone_selects_nothing():
    modules, why = gate.select(["docs/CHECKPOINT.md", "README.md"])
    assert modules == []
    assert "changed modules" in why


@pytest.mark.parametrize(
    "path",
    [
        "tests/conftest.py",
        "tests/_zmq_release.py",
        "tests/_frames.py",
        "tools/mutate.py",
        "pyproject.toml",
        ".github/workflows/ci.yml",
    ],
)
def test_a_structural_change_escalates_to_everything(path):
    """These change what every test sees, so reasoning about a subset is not sound.
    Escalating beats being clever about it."""
    modules, why = gate.select([path])
    assert modules == sorted(gate.RETURNS)
    assert path in why


def test_the_zmq_release_fixture_alone_escalates_though_it_names_no_module():
    """P4d-2b b1, Ruling 19. `tests/_zmq_release.py` is an autouse fixture that holds
    every `ZmqLink` and `ZmqConsole` in `test_serve.py` and `test_cli.py` until
    teardown. Editing it changes object lifetimes in both files, and with them what
    the `link`, `serve` and `cli` sweeps can catch. Its name is not `test_` plus a
    module, so the per-file rule selected nothing for it, and a push that changed
    only that file ran no sweep at all."""
    modules, why = gate.select(["tests/_zmq_release.py"])
    assert modules == sorted(gate.RETURNS)
    assert "tests/_zmq_release.py" in why


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


# ---------------------------------------------------------------------------
# --shard: splitting the full sweep across parallel jobs (2026-09-27, PI "both")
# ---------------------------------------------------------------------------

#: The real target list, sharded, is what the nightly matrix actually runs -- these
#: tests use it rather than a synthetic module list so "the shards partition the
#: selected modules" means the modules a sweep would really select.
_TARGETS = sorted(gate.RETURNS)


@pytest.mark.parametrize("n", range(1, 9))
def test_shards_partition_the_selected_modules_exactly(n):
    """No module lost, none duplicated, for every shard count from 1 to 8 -- the
    range `.github/workflows/ci.yml` and a person's `--shard` could plausibly ask
    for."""
    groups = gate.shard_groups(_TARGETS, n)
    assert len(groups) == n
    flattened = [module for group in groups for module in group]
    assert sorted(flattened) == _TARGETS
    assert len(flattened) == len(_TARGETS), "a module appears in more than one shard"


@pytest.mark.parametrize("n", range(1, 9))
def test_shards_are_balanced_by_function_count(n):
    """The largest shard's function count is at most the smallest's plus the
    largest single module's count -- the guarantee greedy least-loaded placement
    gives, and the reason `serve.py` (38 functions) and `components.py` (1) can
    still land in shards of comparable size."""
    groups = gate.shard_groups(_TARGETS, n)
    totals = [sum(gate._function_count(m) for m in group) for group in groups]
    largest_module = max(gate._function_count(m) for m in _TARGETS)
    assert max(totals) <= min(totals) + largest_module


def test_sharding_is_deterministic_across_calls():
    """The same modules and `n` must produce the same groups every time -- a CI
    matrix job only sees its own `K`, so shard 3 of 6 run on one runner has to agree
    with shard 3 of 6 as computed on every other runner, with no shared state
    between them."""
    first = gate.shard_groups(_TARGETS, 6)
    second = gate.shard_groups(_TARGETS, 6)
    assert first == second


def test_a_shard_beyond_the_module_count_is_empty_in_list_order():
    """`n` may exceed the number of modules to place -- a person could ask for more
    shards than there is work. The extra shards are simply empty, and they are the
    highest-numbered ones: every index below the module count receives exactly one
    module before any receives a second."""
    groups = gate.shard_groups(["a", "b", "c"], 5, counts={"a": 3, "b": 2, "c": 1})
    non_empty = [g for g in groups if g]
    empty = [g for g in groups if not g]
    assert len(non_empty) == 3
    assert len(empty) == 2
    assert groups[3] == [] and groups[4] == []


def test_shard_groups_respects_given_counts_not_module_name_length():
    """Balance is by function count, not by how many modules land in a group --
    passing counts directly (rather than reading `wl_xcon/*.py`) is what
    makes this provable without depending on the current state of the package."""
    counts = {"big": 10, "small1": 3, "small2": 3, "small3": 4}
    groups = gate.shard_groups(list(counts), 2, counts=counts)
    totals = sorted(sum(counts[m] for m in group) for group in groups)
    # "big" alone (10) should sit by itself against the other three combined (10).
    assert totals == [10, 10]


# ---------------------------------------------------------------------------
# --shard: bad values are refused, not guessed at
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["0/6", "7/6", "a/b", "3"])
def test_a_bad_shard_value_is_refused_with_a_message(value):
    with pytest.raises(argparse.ArgumentTypeError) as excinfo:
        gate.parse_shard(value)
    assert value in str(excinfo.value)


def test_a_good_shard_value_parses_to_k_and_n():
    assert gate.parse_shard("3/6") == (3, 6)
    assert gate.parse_shard("1/1") == (1, 1)


# ---------------------------------------------------------------------------
# --changed-only: pushes and PRs never escalate on GLOBAL; the nightly covers it
# ---------------------------------------------------------------------------


def test_changed_only_does_not_escalate_on_a_global_change_and_says_so():
    modules, why = gate.select(["pyproject.toml"], changed_only=True)
    assert modules == [], "a GLOBAL path must not blow up a push's sweep"
    assert "does not escalate" in why
    assert "nightly" in why


def test_changed_only_still_selects_the_changed_module_when_nothing_global_moved():
    modules, why = gate.select(["wl_xcon/gaze.py"], changed_only=True)
    assert modules == ["gaze"]


def test_without_changed_only_a_global_change_still_escalates():
    """The contrast that makes --changed-only's own behaviour legible: the ordinary
    selector's GLOBAL handling is unchanged, only a new flag beside it."""
    modules, why = gate.select(["pyproject.toml"])
    assert modules == sorted(gate.RETURNS)
    assert "pyproject.toml" in why


def test_changed_only_does_not_escalate_on_a_tasks_change_and_says_so():
    """The controller's ruling (2026-09-27): `--changed-only` must never escalate
    at all, and `tasks/` is the other path in `select()` that normally does --
    reference tasks are inputs to many tests, same as a GLOBAL file changing what
    every test sees. Treated identically to GLOBAL: select nothing extra, and say
    that escalating would have selected everything and that the nightly covers it."""
    modules, why = gate.select(["tasks/visual_search.py"], changed_only=True)
    assert modules == [], "tasks/ must not blow up a push's sweep under --changed-only"
    assert "does not escalate" in why
    assert "nightly" in why


@pytest.mark.parametrize(
    "shared", ["tests/conftest.py", "pyproject.toml", "tasks/visual_search.py"]
)
def test_changed_only_still_sweeps_the_modules_a_push_changed_beside_a_shared_file(
    shared,
):
    """"Never escalate" means "add nothing for the shared file", never "sweep
    nothing". Until 2026-09-28 a push that touched `conftest.py` and `serve.py`
    together selected zero modules -- not even `serve` -- because the shared file
    returned an empty selection before the changed modules were looked at (found
    by the b2a plan's pre-flight). The directly changed module and its test file
    must still be swept, and the reason must still say what was not escalated."""
    modules, why = gate.select(
        [shared, "wl_xcon/serve.py", "tests/test_gaze.py"], changed_only=True
    )
    assert modules == ["gaze", "serve"]
    assert "does not escalate" in why
    assert "nightly" in why


def test_every_escalation_path_in_select_is_covered_by_changed_only():
    """`select()` has exactly two ways to escalate to every module: a GLOBAL path,
    and a `tasks/` path. This pins that count so a third escalation path added later
    cannot silently bypass `--changed-only` the way `tasks/` briefly did -- if
    someone adds a new `if ...: return sorted(RETURNS), ...` branch to `select()`
    without also teaching it about `changed_only`, this test will not catch the
    *new* branch by name, but the two branches it already knows about are the
    complete set as of 2026-09-27 (verified by reading `select()`, not guessed)."""
    for changed in (["pyproject.toml"], ["tasks/calibration.py"]):
        modules, why = gate.select(changed, changed_only=True)
        assert modules == []
        assert "does not escalate" in why
        assert "nightly" in why


# ---------------------------------------------------------------------------
# --shard combined with --changed-only
# ---------------------------------------------------------------------------


def test_shard_combined_with_changed_only_slices_only_the_smaller_selection():
    """The chosen behaviour, and why: `--shard` stays literal -- it always
    partitions whatever module list was already selected, never re-expanding it
    back to the full `RETURNS` set. `ci.yml` never pairs `--shard` with
    `--changed-only` (the push job uses `--changed-only` alone; the sharded job
    uses `--all` alone), so this combination has no real caller today, but the
    simplest correct rule is "shard whatever you were given," not a special case
    that would have to be justified and tested on its own. A --changed-only
    selection of two modules, sharded six ways, is mostly empty shards -- expected,
    and covered by `shard_groups`'s own emptiness tests."""
    modules, _ = gate.select(
        ["wl_xcon/dio.py", "wl_xcon/eye.py"], changed_only=True
    )
    assert modules == ["dio", "eye"]
    groups = gate.shard_groups(modules, 6)
    assert sorted(m for group in groups for m in group) == ["dio", "eye"]
    assert sum(1 for group in groups if group) == 2


# ---------------------------------------------------------------------------
# --shard wired into main(): --dry-run so a test never launches a real sweep
# ---------------------------------------------------------------------------


def test_main_with_shard_selects_only_that_groups_modules(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["mutation_gate.py", "--all", "--shard", "1/6", "--dry-run"])
    assert gate.main() == 0
    out = capsys.readouterr().out
    assert "shard 1/6" in out


def test_main_with_a_shard_past_the_module_count_says_so_and_passes(monkeypatch, capsys):
    n = len(gate.RETURNS) + 3
    monkeypatch.setattr(
        sys, "argv", ["mutation_gate.py", "--all", "--shard", f"{n}/{n}", "--dry-run"]
    )
    assert gate.main() == 0
    out = capsys.readouterr().out
    assert "empty" in out
