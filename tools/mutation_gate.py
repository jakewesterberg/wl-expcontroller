#!/usr/bin/env python3
"""Which modules this change needs mutated, and with what flag.

The full sweep re-runs the whole suite once per function -- seventeen modules, about
150 functions, twenty-five minutes -- and it grows with every module and every test.
This selects the subset a change can actually have affected, so a push pays for what
it touched. **The full sweep still runs nightly** (`.github/workflows/ci.yml`), and
that is not decoration: see "What this can miss", below.

**A new module cannot silently escape the gate.** Every file in `wl_expcontroller/`
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
full sweep is what catches it. Anything structural (`conftest.py`, `mutate.py`,
`pyproject.toml`, `tasks/`) escalates to a full sweep here rather than being reasoned
about, because those change what every test sees.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "wl_expcontroller"

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
    "taskd": "None",
    "photometry": "None",
    "eye": "None",
    "dio": "None",
    "bounds": "None",
    "scheduler": "None",
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


def select(changed: list[str]) -> tuple[list[str], str]:
    """(modules to mutate, why). Pure, so the reasoning is testable."""
    if any(path in GLOBAL for path in changed):
        hit = next(path for path in changed if path in GLOBAL)
        return sorted(RETURNS), f"{hit} changed; it alters what every test sees"
    if any(path.startswith("tasks/") for path in changed):
        return sorted(RETURNS), "tasks/ changed; reference tasks are inputs to many tests"

    chosen: set[str] = set()
    for path in changed:
        if path.startswith(f"{PACKAGE}/") and path.endswith(".py"):
            stem = Path(path).stem
            if stem in RETURNS:
                chosen.add(stem)
        elif path.startswith("tests/test_") and path.endswith(".py"):
            # `tests/test_gaze.py` covers `wl_expcontroller/gaze.py`. A test file with
            # no module of that name -- `test_reference_tasks.py` -- selects nothing,
            # and the nightly is what covers the gap that leaves.
            stem = Path(path).stem[len("test_") :]
            if stem in RETURNS:
                chosen.add(stem)
    return sorted(chosen), "changed modules and their own test files"


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


def run(modules: list[str]) -> int:
    failures = []
    for module in modules:
        command = [sys.executable, "tools/mutate.py", "--all"]
        if RETURNS[module] != "[]":
            command += ["--returns", RETURNS[module]]
        command.append(f"{PACKAGE}/{module}.py")
        print(f"\n=== {module} ({' '.join(command[2:])}) ===", flush=True)
        if subprocess.run(command, cwd=ROOT).returncode != 0:
            failures.append(module)
    if failures:
        print(f"\nMUTATION GATE FAILED: {', '.join(failures)}")
        return 1
    print(f"\nmutation gate passed: {len(modules)} module(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="every module (the nightly)")
    parser.add_argument("--base", help="git ref to diff against")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    missing = undeclared()
    if missing:
        # Loud and fatal on purpose. A module absent from both lists is ungated, and
        # nothing else in this repository would ever say so.
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
            modules, why = select(changed)

    print(f"mutation gate: {len(modules)} module(s) -- {why}")
    print(f"  selected: {', '.join(modules) if modules else '(none)'}")
    if not modules:
        print("  nothing this change could have affected; the nightly sweep covers the rest")
        return 0
    if args.dry_run:
        return 0
    return run(modules)


if __name__ == "__main__":
    raise SystemExit(main())
