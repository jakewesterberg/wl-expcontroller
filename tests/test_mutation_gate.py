"""Which modules a change needs mutated -- and the guard against one escaping.

The gate got cheaper by running less, so what matters is what it still runs. These
test the selection, and above all `undeclared()`: the workflow's hand-maintained
module list had silently omitted three modules, one of them the **welfare-critical**
one, while `docs/CHECKPOINT.md` described "a mutation gate over every module".
"""

from __future__ import annotations

import argparse
import ast
import functools
import importlib.util
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

_GATE = Path(__file__).resolve().parents[1] / "tools" / "mutation_gate.py"
_SPEC = importlib.util.spec_from_file_location("wlx_mutation_gate", _GATE)
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
# --shard: splitting the full sweep across parallel jobs (2026-09-27, PI "both"),
# by function rather than by module since 2026-09-30 (PI): `serve` alone held a
# shard for 2h42m in run 36737681413, and a module kept whole is a floor no
# number of machines can go under.
# ---------------------------------------------------------------------------

#: The real selection, sharded, is what the nightly matrix actually runs -- these
#: tests use it rather than a synthetic list so "every function lands in one shard"
#: means the functions a sweep would really mutate.
_MODULES = sorted(gate.RETURNS)

#: Every count CI or a person could plausibly ask for, then one past the work
#: itself (the package held 566 functions on 2026-09-30).
_COUNTS = [*range(1, 13), 100, 1000]


@functools.cache
def _functions() -> dict[str, list[str]]:
    """The gate's own listing of the real package, read once rather than once per
    shard, which parsed every module thousands of times over.
    `test_the_targets_are_...` pins that this listing is the one `shard_targets`
    reads when it is given none."""
    return {module: gate.module_functions(module) for module in _MODULES}


def _targets() -> list[tuple[str, str]]:
    return gate.shard_targets(_MODULES, _functions())


def _functions_of(plan: list[tuple[str, list[str]]]) -> list[tuple[str, str]]:
    return [(module, name) for module, names in plan for name in names]


def _all_shards(
    modules: list[str], n: int, functions: dict[str, list[str]] | None = None
) -> list[list[tuple[str, str]]]:
    """All `n` shards of `modules`; of the real package's, unless `functions` is given."""
    if functions is None and set(modules) <= set(_MODULES):
        functions = _functions()
    return [
        _functions_of(gate.shard_plan(modules, k, n, functions)) for k in range(1, n + 1)
    ]


def test_the_targets_are_the_modules_by_name_then_mutates_own_listing():
    """The flat list the shards cut: modules by name, and within each exactly what
    `tools/mutate.py --all` would run, in its order -- `_function_names` itself, so
    the gate cannot hand `--only` a name `mutate.py` does not list."""
    listing = gate._load_mutate()._function_names
    expected = [
        (module, name)
        for module in _MODULES
        for name in listing((gate.ROOT / gate.PACKAGE / f"{module}.py").read_text())
    ]
    assert _targets() == expected
    assert gate.shard_targets(list(reversed(_MODULES))) == expected


@pytest.mark.parametrize("n", _COUNTS)
def test_every_function_lands_in_exactly_one_shard(n):
    """Nothing lost, nothing twice, for every shard count -- and in order, since
    the shards are contiguous cuts of one list: laid end to end they are it."""
    shards = _all_shards(_MODULES, n)
    assert len(shards) == n
    assert [target for shard in shards for target in shard] == _targets()


@pytest.mark.parametrize("n", _COUNTS)
def test_shard_sizes_differ_by_at_most_one_and_the_earlier_ones_are_larger(n):
    sizes = [len(shard) for shard in _all_shards(_MODULES, n)]
    assert max(sizes) - min(sizes) <= 1
    # Pairwise rather than `sizes == sorted(...)`: pytest's diff of two thousand-long
    # lists takes two minutes to print when this fails.
    assert all(a >= b for a, b in zip(sizes, sizes[1:])), "a later shard is larger"


def test_shard_sizes_on_a_small_list_are_exactly_as_specified():
    """Ten functions over four shards: 3, 3, 2, 2 -- the extra two to the first
    two shards, never 3, 3, 3, 1."""
    functions = {"a": ["p", "q", "r", "s"], "b": ["t", "u", "v", "w", "x", "y"]}
    sizes = [len(shard) for shard in _all_shards(["a", "b"], 4, functions=functions)]
    assert sizes == [3, 3, 2, 2]


def test_a_shard_is_the_same_whatever_the_input_order_and_whatever_the_process():
    """Each CI job computes only its own `K`, with no shared state, so shard 5 of 12
    on one runner has to be shard 5 of 12 on every other. A fresh interpreter per
    hash seed is what a runner is: an in-process second call cannot see an order
    that comes from iterating a set, and a runner can."""
    shuffled = list(_MODULES)
    random.Random(20260930).shuffle(shuffled)
    assert gate.shard_plan(shuffled, 5, 12) == gate.shard_plan(_MODULES, 5, 12)

    outputs = set()
    for seed in ("0", "1", "2", "3"):
        result = subprocess.run(
            [sys.executable, str(_GATE), "--all", "--shard", "5/12", "--dry-run"],
            cwd=gate.ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1, "shard 5/12 differed between interpreters"
    (output,) = outputs
    for module, names in gate.shard_plan(_MODULES, 5, 12):
        assert f"    {module} ({len(names)}): {', '.join(names)}" in output


def _defined_more_than_once(module: str) -> set[str]:
    """Read here with `ast`, independently of the tool, so the test does not agree
    with the tool by construction."""
    tree = ast.parse((gate.ROOT / gate.PACKAGE / f"{module}.py").read_text())
    names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return {name for name in names if names.count(name) > 1}


def test_a_name_defined_more_than_once_is_one_target_and_never_split(
    tmp_path, monkeypatch
):
    """`mutate()` neuters every definition of a name together, so `publish` in two
    classes is one mutant. Listed twice, it could land in two shards and run twice
    -- or, split, be half of an `--only` in each. Through the gate's real listing,
    on a module written here so the case exists whatever the package looks like."""
    (tmp_path / gate.PACKAGE).mkdir()
    (tmp_path / gate.PACKAGE / "worlds.py").write_text(
        "class Quiet:\n"
        "    def publish(self): ...\n"
        "def first(): ...\n"
        "class Loud:\n"
        "    def publish(self):\n"
        "        return 1\n"
        "def last(): ...\n"
    )
    monkeypatch.setattr(gate, "ROOT", tmp_path)

    assert gate.shard_targets(["worlds"]) == [
        ("worlds", "publish"),
        ("worlds", "first"),
        ("worlds", "last"),
    ]
    for n in range(1, 6):
        seen = [t for shard in _all_shards(["worlds"], n) for t in shard]
        assert seen.count(("worlds", "publish")) == 1, n


def test_no_name_the_package_defines_twice_is_split_or_repeated():
    """The same property on the real package, which has plenty: `link.publish`,
    `run.satisfied`, `serve.__init__`. The first assertion keeps this from passing
    vacuously the day nothing is defined twice."""
    repeated = {(m, name) for m in _MODULES for name in _defined_more_than_once(m)}
    assert len(repeated) > 10, repeated
    for n in range(1, 13):
        seen = [t for shard in _all_shards(_MODULES, n) for t in shard]
        for target in repeated:
            assert seen.count(target) == 1, (n, target)


def test_shards_past_the_function_count_are_the_trailing_ones_and_empty():
    """More shards than work: one function each to the first shards, and the
    extras are the highest-numbered ones, empty."""
    functions = {"a": ["x", "y"], "b": ["z"]}
    plans = [gate.shard_plan(["a", "b"], k, 5, functions=functions) for k in range(1, 6)]
    assert plans == [[("a", ["x"])], [("a", ["y"])], [("b", ["z"])], [], []]


def test_a_module_is_cut_between_shards_and_each_part_listed_under_it():
    """Six functions over three shards: `a` is cut after `q`, and shard 2 holds the
    rest of `a` and the start of `b` -- one `--only` call per module."""
    functions = {"a": ["p", "q", "r"], "b": ["s", "t"], "c": ["u"]}
    assert [gate.shard_plan(["c", "b", "a"], k, 3, functions=functions) for k in (1, 2, 3)] == [
        [("a", ["p", "q"])],
        [("a", ["r"]), ("b", ["s"])],
        [("b", ["t"]), ("c", ["u"])],
    ]


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
    partitions the functions of whatever modules were already selected, never
    re-expanding them back to the full `RETURNS` set. The push job pairs
    `--changed-only` with `--shard` (XC-141), so a merge push's selection is cut
    across twelve machines by function exactly as the nightly's is."""
    modules, _ = gate.select(
        ["wl_xcon/dio.py", "wl_xcon/eye.py"], changed_only=True
    )
    assert modules == ["dio", "eye"]
    shards = _all_shards(modules, 12)
    flattened = [target for shard in shards for target in shard]
    assert flattened == gate.shard_targets(["dio", "eye"])
    assert {module for module, _ in flattened} == {"dio", "eye"}


# ---------------------------------------------------------------------------
# --shard wired into main()
# ---------------------------------------------------------------------------


def _no_subprocess(*args, **kwargs):
    raise AssertionError(f"a sweep was launched: {args}")


def _spanning_shard(n: int) -> tuple[int, list[tuple[str, list[str]]]]:
    """The first shard of `n` whose chunk covers more than one module."""
    for k in range(1, n + 1):
        plan = gate.shard_plan(_MODULES, k, n, _functions())
        if len(plan) > 1:
            return k, plan
    raise AssertionError(f"no shard of {n} spans two modules")


def test_dry_run_prints_each_module_of_the_shard_and_the_functions_it_would_run(
    monkeypatch, capsys
):
    k, plan = _spanning_shard(12)
    monkeypatch.setattr(gate.subprocess, "run", _no_subprocess)
    monkeypatch.setattr(
        sys, "argv", ["mutation_gate.py", "--all", "--shard", f"{k}/12", "--dry-run"]
    )

    assert gate.main() == 0

    out = capsys.readouterr().out
    assert f"shard {k}/12" in out
    for module, names in plan:
        assert f"    {module} ({len(names)}): {', '.join(names)}" in out


def test_a_shard_runs_each_of_its_modules_with_only_its_functions(monkeypatch, capsys):
    """The commands themselves: one `mutate.py --all --only` per module in the
    chunk, in order, with that module's `--returns` exactly as `RETURNS` has it."""
    k, plan = _spanning_shard(12)
    commands = []

    def record(command, cwd):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(gate.subprocess, "run", record)
    monkeypatch.setattr(sys, "argv", ["mutation_gate.py", "--all", "--shard", f"{k}/12"])

    assert gate.main() == 0

    assert commands == [
        [
            sys.executable,
            "tools/mutate.py",
            "--all",
            "--only",
            ",".join(names),
            *([] if gate.RETURNS[module] == "[]" else ["--returns", gate.RETURNS[module]]),
            f"{gate.PACKAGE}/{module}.py",
        ]
        for module, names in plan
    ]
    assert "mutation gate passed" in capsys.readouterr().out


def test_a_failing_part_fails_the_shard_and_names_its_module(monkeypatch, capsys):
    k, plan = _spanning_shard(12)
    failing = plan[-1][0]
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda command, cwd: subprocess.CompletedProcess(
            command, 1 if command[-1] == f"{gate.PACKAGE}/{failing}.py" else 0
        ),
    )
    monkeypatch.setattr(sys, "argv", ["mutation_gate.py", "--all", "--shard", f"{k}/12"])

    assert gate.main() == 1

    assert f"MUTATION GATE FAILED: {failing}" in capsys.readouterr().out


def test_twelve_shards_through_mutate_run_every_function_exactly_once(monkeypatch):
    """Test the path, not the piece. Each shard's real commands are handed to
    `tools/mutate.py`'s own `main()` -- its `--only` parsing and refusal included --
    with only the suite runs and the neutering stubbed. Across the twelve, every
    function the package has is mutated once, in order, and every call brackets
    its part with one baseline and one restored suite."""
    spec = importlib.util.spec_from_file_location(
        "wlx_mutate_for_gate_test", gate.ROOT / "tools" / "mutate.py"
    )
    mutate_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mutate_tool)
    mutated: list[tuple[str, str]] = []
    suites = []
    monkeypatch.setattr(mutate_tool, "_restore_any_interrupted_run", lambda: None)
    monkeypatch.setattr(
        mutate_tool,
        "_run_suite",
        lambda: suites.append(1) or (True, "1 passed in 0.01s", []),
    )
    monkeypatch.setattr(
        mutate_tool,
        "mutate",
        lambda path, name, returns: mutated.append((path.stem, name))
        or (True, "1 failed in 0.01s"),
    )
    calls = []

    def through_mutate(command, cwd):
        assert command[:2] == [sys.executable, "tools/mutate.py"]
        calls.append(command)
        monkeypatch.setattr(sys, "argv", ["mutate.py", *command[2:]])
        return subprocess.CompletedProcess(command, mutate_tool.main())

    monkeypatch.setattr(gate.subprocess, "run", through_mutate)
    for k in range(1, 13):
        monkeypatch.setattr(sys, "argv", ["mutation_gate.py", "--all", "--shard", f"{k}/12"])
        assert gate.main() == 0, k

    assert mutated == _targets()
    assert len(suites) == 2 * len(calls)


def test_main_with_a_shard_past_the_function_count_says_so_and_passes(monkeypatch, capsys):
    n = len(_targets()) + 3
    monkeypatch.setattr(gate.subprocess, "run", _no_subprocess)
    monkeypatch.setattr(sys, "argv", ["mutation_gate.py", "--all", "--shard", f"{n}/{n}"])

    assert gate.main() == 0

    out = capsys.readouterr().out
    assert f"shard {n}/{n} is empty" in out
    assert "nothing to run" in out


def test_a_selected_module_with_no_functions_fails_every_shard(
    tmp_path, monkeypatch, capsys
):
    """Unsharded, `mutate.py --all` refuses a module with nothing to mutate -- and
    one that does not parse lists nothing too. Sharded, such a module has no
    functions to land anywhere, so it would simply vanish from every shard: a
    module in `RETURNS` that no sweep examines, and a green gate. Each shard
    refuses instead, since each computes the whole list."""
    (tmp_path / gate.PACKAGE).mkdir()
    (tmp_path / gate.PACKAGE / "full.py").write_text("def a(): ...\ndef b(): ...\n")
    (tmp_path / gate.PACKAGE / "hollow.py").write_text("LIMIT = 3\n")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "RETURNS", {"full": "None", "hollow": "None"})
    monkeypatch.setattr(gate, "EXEMPT", {})
    monkeypatch.setattr(gate.subprocess, "run", _no_subprocess)

    for k in (1, 2):
        monkeypatch.setattr(
            sys, "argv", ["mutation_gate.py", "--all", "--shard", f"{k}/2", "--dry-run"]
        )
        assert gate.main() == 1, k
        assert "NO FUNCTIONS TO MUTATE: hollow" in capsys.readouterr().out
