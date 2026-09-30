#!/usr/bin/env python3
"""Which modules this change needs mutated, and with what flag.

The full sweep re-runs the whole suite once per function -- twenty-nine modules and
566 functions on 2026-09-30 -- and it grows with every module and every test. This
selects the subset a change can actually have affected, so a push pays for what it
touched. **The full sweep still runs nightly** (`.github/workflows/ci.yml`), and
that is not decoration: see "What this can miss", below.

**`--shard K/N` cuts by function, not by module (PI, 2026-09-30).** The selected
modules' functions are one list -- modules by name, each module's functions in
`mutate.py --all`'s own order -- cut into `N` contiguous chunks whose sizes differ by
at most one. Shard `K` runs chunk `K` as one `mutate.py --all --only <its part>` per
module it touches, so a module can be split between two machines. Until then a
module was kept whole and the modules balanced by function count, which left
`serve` (60 functions) alone on one machine for 2h42m of a push's gate (run
36737681413, read 2026-09-30) however many machines there were. See `shard_plan`.

**A new module cannot silently escape the gate.** Every file in `wl_xcon/`
must appear in `RETURNS` or in `EXEMPT` with a reason, and this script fails if one
does not. That is the actual hazard here -- `findings.py` was added earlier today and
was never added to the workflow's hand-maintained module list, so it would have gone
ungated indefinitely without anyone noticing. A list you have to remember to update is
a list that is wrong.

**What this can miss, stated rather than implied.** Mutation coverage is a property of
a module *and* the tests that cover it. Selecting on changed files catches the two
common cases -- the module changed, or its own test file changed -- and misses one:
deleting or weakening a test in `test_a.py` that happened to be the only thing
covering a function in `b.py`. Nothing in a diff makes that visible, so the nightly
full sweep is what catches it. Anything structural (`conftest.py` and the shared
test helpers beside it, `mutate.py`, `pyproject.toml`, `tasks/`) escalates to a full
sweep here rather than being reasoned about, because those change what every test
sees.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "wl_xcon"

#: Module -> what a neutered body returns, which decides how sharp the answer is.
#: `[]` for modules whose functions return lists that callers concatenate: it fails
#: exactly the tests covering that function, so "1 failed" localises the coverage.
#: `None` breaks the concatenation and fails everything at once -- still proof the
#: function is load-bearing, but no longer proof any single test isolates it.
#: See `mutate.mutate`'s docstring; these values are the ones the workflow used
#: when the list lived in YAML.
RETURNS: dict[str, str] = {
    "check": "[]",
    "encode": "[]",
    "calibration": "[]",
    "gaze": "[]",
    "saccade": "None",
    "run": "None",
    "simulate": "None",
    "review": "None",
    "record": "None",
    "geometry": "None",
    "task": "None",
    "codes": "None",
    "components": "None",
    "cli": "None",
    "marks": "None",
    "preflight": "None",
    "service": "None",
    "stranded": "None",
    "taskd": "None",
    "photometry": "None",
    "eye": "None",
    "dio": "None",
    "bounds": "None",
    "welfare": "None",
    "scheduler": "None",
    "link": "None",
    "health": "None",
    "web": "None",
    "serve": "None",
}

#: Modules with nothing to neuter, and why. An entry here is a claim someone made,
#: which is the point: the alternative is a module quietly absent from both lists.
EXEMPT: dict[str, str] = {
    "__init__": "package marker",
    "findings": "one frozen dataclass; no functions and no behaviour to neuter",
}

#: Changes that alter what every test sees, so reasoning about a subset is not
#: sound. Escalate rather than be clever.
GLOBAL = (
    "tests/conftest.py",
    # An autouse fixture: it changes object lifetimes in test_serve.py and test_cli.py.
    "tests/_zmq_release.py",
    # The one frame test_health.py, test_web.py and test_serve.py build their cases on.
    "tests/_frames.py",
    "tools/mutate.py",
    "tools/mutation_gate.py",
    "pyproject.toml",
    ".github/workflows/ci.yml",
)


def declared_modules() -> set[str]:
    return {p.stem for p in (ROOT / PACKAGE).glob("*.py")}


def undeclared() -> set[str]:
    """Modules on disk that neither list mentions. Always an error."""
    return declared_modules() - set(RETURNS) - set(EXEMPT)


def select(changed: list[str], *, changed_only: bool = False) -> tuple[list[str], str]:
    """(modules to mutate, why). Pure, so the reasoning is testable.

    `changed_only=True` is what `--changed-only` passes -- a push or pull request.
    A full sweep is now roughly six hours (2026-09-27; see docs/CHECKPOINT.md's CI
    row), so a push runs only what its own diff can have affected and **never
    escalates at all** (the controller's ruling, 2026-09-27, on the PI's intent:
    "the full check nightly only"); the sharded nightly `--all` sweep covers every
    escalation case instead.

    There are exactly two ways below that this function would otherwise escalate
    to every module -- a GLOBAL path, and a `tasks/` path, since reference tasks
    are inputs to many tests just as a GLOBAL file changes what every test sees --
    and `changed_only` is checked in both, not in one and forgotten in the other.
    Each says, when it would have escalated, that it did not and that the nightly
    sweep covers it, so the log does not read like a full check that happened to
    select nothing. **Not escalating adds nothing; it never removes anything**: the
    modules the change touched directly, and their own test files, are still swept
    beside a shared path (2026-09-28 -- until then a shared path returned an empty
    selection early, so a push touching `conftest.py` and `serve.py` swept neither).
    **If a third escalation path is ever added here, it must get
    the same `if changed_only` treatment**, or `--changed-only` silently stops
    meaning "never escalates" for that one path -- `tests/test_mutation_gate.py`'s
    `test_every_escalation_path_in_select_is_covered_by_changed_only` is what would
    need a new case added alongside the new path.
    """
    # Under --changed-only a shared path adds nothing -- but it never *removes*
    # anything either: the modules the change touched directly are still swept below
    # (fix of 2026-09-28; until then a shared path returned an empty selection early,
    # so a push touching `conftest.py` and `serve.py` swept neither).
    not_escalated = ""
    if any(path in GLOBAL for path in changed):
        hit = next(path for path in changed if path in GLOBAL)
        if not changed_only:
            return sorted(RETURNS), f"{hit} changed; it alters what every test sees"
        not_escalated = (
            f"{hit} changed; --changed-only does not escalate on it -- "
            f"the nightly full sweep covers it"
        )
    elif any(path.startswith("tasks/") for path in changed):
        if not changed_only:
            return sorted(RETURNS), "tasks/ changed; reference tasks are inputs to many tests"
        not_escalated = (
            "tasks/ changed; --changed-only does not escalate on it -- "
            "the nightly full sweep covers it"
        )

    chosen: set[str] = set()
    for path in changed:
        if path.startswith(f"{PACKAGE}/") and path.endswith(".py"):
            stem = Path(path).stem
            if stem in RETURNS:
                chosen.add(stem)
        elif path.startswith("tests/test_") and path.endswith(".py"):
            # `tests/test_gaze.py` covers `wl_xcon/gaze.py`. A test file with
            # no module of that name -- `test_reference_tasks.py` -- selects nothing,
            # and the nightly is what covers the gap that leaves.
            stem = Path(path).stem[len("test_") :]
            if stem in RETURNS:
                chosen.add(stem)
    if not_escalated:
        return sorted(chosen), f"{not_escalated}; swept: changed modules and their own test files"
    return sorted(chosen), "changed modules and their own test files"


@functools.cache
def _load_mutate():
    """`tools/mutate.py`, loaded by path: this directory is not a package.

    The gate reads `_function_names` from it rather than keeping a copy. The names
    a shard hands `mutate.py --only` must be names `mutate.py --all` lists, or
    `--only` refuses them; one listing cannot disagree with itself, and a copy is a
    test that can agree with itself while disagreeing with the tool.
    """
    spec = importlib.util.spec_from_file_location(
        "wlx_mutate_listing", Path(__file__).resolve().parent / "mutate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_functions(module: str) -> list[str]:
    """What `tools/mutate.py --all wl_xcon/<module>.py` would mutate, in its order.

    `mutate._function_names` itself: every `def`, module-level or a method, read
    with `ast` and never a pattern (CLAUDE.md: "a tool that reasons about code asks
    the parser"), and **each name once** -- `mutate()` neuters every definition of
    a name together, so `publish` in three classes is one target. That is what
    keeps a shard boundary from splitting one name between two machines.
    """
    source = (ROOT / PACKAGE / f"{module}.py").read_text()
    return _load_mutate()._function_names(source)


def shard_targets(
    modules: list[str], functions: dict[str, list[str]] | None = None
) -> list[tuple[str, str]]:
    """Every `(module, function)` a sweep of `modules` mutates, in one fixed order:
    modules by name, and each module's functions as `module_functions` lists them.

    Sorted here rather than trusted from the caller, so the order -- and with it
    every shard -- depends only on which modules were selected. `functions`, when
    given, is used instead of reading `wl_xcon/*.py`, which is what lets a test
    prove the chunking without depending on the package's current shape.
    """
    if functions is None:
        functions = {module: module_functions(module) for module in modules}
    return [(module, name) for module in sorted(modules) for name in functions[module]]


def _chunk(total: int, k: int, n: int) -> tuple[int, int]:
    """`[start, end)` of the `k`-th (1-based) of `n` contiguous chunks of `total`.

    Sizes differ by at most one, and the first `total % n` chunks take the extra
    one each; with `n > total` the last `n - total` chunks are empty.
    """
    size, extra = divmod(total, n)
    start = (k - 1) * size + min(k - 1, extra)
    return start, start + size + (1 if k <= extra else 0)


def shard_plan(
    modules: list[str], k: int, n: int, functions: dict[str, list[str]] | None = None
) -> list[tuple[str, list[str]]]:
    """Shard `k` of `n`: `[(module, [function, ...]), ...]`, in `shard_targets` order.

    **Split by function, not by module (PI, 2026-09-30; the module docstring says
    why).** A module is cut wherever its chunk ends, and each machine runs
    `mutate.py --all --only` on its part of each module it touches.

    The flat target list is cut into `n` contiguous chunks whose sizes differ by at
    most one (`_chunk`). Contiguous rather than dealt round-robin so a shard spans
    few modules, and each module it touches costs one baseline and one restored
    suite. A name is one target however many times it is defined
    (`module_functions`), so no boundary can fall inside it. Nothing here depends
    on the order modules were given or on anything but the inputs, so every CI job
    computes the same shards while seeing only its own `k`.
    """
    targets = shard_targets(modules, functions)
    start, end = _chunk(len(targets), k, n)
    plan: list[tuple[str, list[str]]] = []
    for module, name in targets[start:end]:
        if plan and plan[-1][0] == module:
            plan[-1][1].append(name)
        else:
            plan.append((module, [name]))
    return plan


def parse_shard(value: str) -> tuple[int, int]:
    """Parse `"K/N"` for `--shard`, refusing with a reason rather than a guess.

    `argparse`'s default message for a bad `type=` value is "invalid parse_shard
    value", which does not say what is wrong. `"0/6"` (K below 1), `"7/6"` (K above
    N), `"a/b"` (not integers) and `"3"` (no `/` at all) each get their own
    sentence, naming the value it was given.
    """
    parts = value.split("/")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise argparse.ArgumentTypeError(
            f"--shard wants K/N as two positive integers (e.g. 1/12), got {value!r}"
        )
    k, n = int(parts[0]), int(parts[1])
    if n < 1:
        raise argparse.ArgumentTypeError(f"--shard's N must be at least 1, got {value!r}")
    if k < 1 or k > n:
        raise argparse.ArgumentTypeError(
            f"--shard's K must be between 1 and N ({n}), got {value!r}"
        )
    return k, n


def changed_files(base: str | None) -> list[str] | None:
    """Paths changed since `base`, or `None` when that cannot be determined."""
    if not base or set(base) == {"0"}:
        return None
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def run(plan: list[tuple[str, list[str] | None]]) -> int:
    """One `mutate.py --all` per module, in order: the whole module when its entry
    is `None`, and `--only` its part of the module when a shard cut it."""
    failures = []
    for module, only in plan:
        command = [sys.executable, "tools/mutate.py", "--all"]
        if only is not None:
            command += ["--only", ",".join(only)]
        if RETURNS[module] != "[]":
            command += ["--returns", RETURNS[module]]
        command.append(f"{PACKAGE}/{module}.py")
        print(f"\n=== {module} ({' '.join(command[2:])}) ===", flush=True)
        if subprocess.run(command, cwd=ROOT).returncode != 0:
            failures.append(module)
    if failures:
        print(f"\nMUTATION GATE FAILED: {', '.join(failures)}")
        return 1
    print(f"\nmutation gate passed: {len(plan)} module(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all", action="store_true", help="every module (the nightly, and workflow_dispatch)"
    )
    parser.add_argument("--base", help="git ref to diff against")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help=(
            "only modules whose own source or test file changed; never escalates on "
            "GLOBAL (pushes and pull requests -- the nightly --all sweep covers the "
            "rest)"
        ),
    )
    parser.add_argument(
        "--shard",
        type=parse_shard,
        metavar="K/N",
        help=(
            "run only the K-th of N contiguous, near-equal chunks of the selected "
            "modules' functions, a module cut wherever its chunk ends (see "
            "shard_plan)"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    missing = undeclared()
    if missing:
        # Loud and fatal on purpose. A module absent from both lists is ungated, and
        # nothing else in this repository would ever say so. This guard fires before
        # --all, --changed-only or --shard are even looked at, so no mode can skip it.
        print(
            f"UNDECLARED MODULE(S): {', '.join(sorted(missing))}\n"
            f"Add each to RETURNS in tools/mutation_gate.py, or to EXEMPT with a "
            f"reason. A module in neither list is silently ungated."
        )
        return 1

    if args.all:
        modules, why = sorted(RETURNS), "--all"
    else:
        changed = changed_files(args.base)
        if changed is None:
            modules, why = sorted(RETURNS), f"cannot diff against {args.base!r}; not guessing"
        else:
            modules, why = select(changed, changed_only=args.changed_only)

    print(f"mutation gate: {len(modules)} module(s) -- {why}")
    print(f"  selected: {', '.join(modules) if modules else '(none)'}")

    # --shard is literal: it cuts the functions of whatever `modules` already is,
    # never re-expanding it. `ci.yml` pairs it with `--all` (the nightly) and with
    # `--changed-only` (a push); a small selection cut twelve ways is mostly empty
    # shards, and an empty shard passes at once.
    plan: list[tuple[str, list[str] | None]] = [(module, None) for module in modules]
    if args.shard and modules:
        k, n = args.shard
        functions = {module: module_functions(module) for module in modules}
        hollow = [module for module in modules if not functions[module]]
        if hollow:
            # Unsharded, `mutate.py --all` refuses a module it finds nothing in. A
            # module with no targets lands in no chunk, so sharded it would vanish
            # from every shard and the gate would pass having never examined it.
            # Every shard computes the whole list, so every shard refuses.
            print(
                f"NO FUNCTIONS TO MUTATE: {', '.join(hollow)}\n"
                f"`mutate.py --all` would refuse each one (no `def`, or source that "
                f"does not parse). Fix it, or move it to EXEMPT with a reason."
            )
            return 1
        total = len(shard_targets(modules, functions))
        chosen = shard_plan(modules, k, n, functions)
        count = sum(len(names) for _, names in chosen)
        print(
            f"  shard {k}/{n}: {count} of {total} function(s), in {len(chosen)} "
            f"module(s) -- contiguous by module name, then by function"
        )
        for module, names in chosen:
            print(f"    {module} ({len(names)}): {', '.join(names)}")
        if not chosen:
            print(
                f"  shard {k}/{n} is empty: {n} shard(s) requested for {total} "
                f"function(s); nothing to run"
            )
            return 0
        plan = chosen

    if not modules:
        print("  nothing this change could have affected; the nightly sweep covers the rest")
        return 0
    if args.dry_run:
        return 0
    return run(plan)


if __name__ == "__main__":
    raise SystemExit(main())
