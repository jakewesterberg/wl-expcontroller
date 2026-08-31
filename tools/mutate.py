#!/usr/bin/env python3
"""Prove a test can fail, by breaking the code it claims to cover.

A test that passes whether or not the behaviour exists is worse than no test: it
reports safety it cannot provide. This script neuters one function -- replacing its
body with `return []` -- runs the suite, and restores.

**It clears `__pycache__` around every step, and that is the whole reason it is a
script rather than three shell lines.** Doing this by hand left stale bytecode from
a previous mutation in place: the source was restored, the interpreter kept running
the broken version, and the suite reported failures against code that was already
correct. A false failure is merely alarming. The same staleness in the other
direction reports a **false pass** -- the mutation never actually ran, and a vacuous
test is pronounced sound. That is the failure this exists to prevent, so it cannot
depend on anyone remembering to clear a cache.

    python3 tools/mutate.py wl_expcontroller/check.py _unbounded_waits
    python3 tools/mutate.py --all wl_expcontroller/check.py
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _clear_pycache() -> None:
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _run_suite() -> tuple[bool, str]:
    _clear_pycache()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stdout.strip().splitlines()[-1]


def _function_names(source: str) -> list[str]:
    """Every function, module-level and method alike.

    Two blind spots found by using it, both the same shape -- the tool quietly
    examining nothing and reporting success. First it matched only `_`-prefixed
    names, so a run over `simulate.py` covered none of it. Then it matched only
    module-level `def`, so `record.py` -- which is entirely methods -- reported
    nothing to mutate, which reads like nothing to check.

    A coverage tool that can silently cover nothing has the exact failure mode it
    exists to catch, so `--all` refuses an empty target list and this matches both
    indentation levels.
    """
    return re.findall(r"^ *def ([a-z_][a-z0-9_]*)\(", source, flags=re.M)


def mutate(path: Path, function: str, args_returns: str) -> bool:
    """True if neutering `function` makes the suite fail, i.e. it is covered.

    A name defined more than once -- `satisfied`, implemented by every `World` --
    has **all** its definitions neutered together. Bailing on the ambiguity was the
    earlier behaviour and it was worse than useless: it stopped the whole run, so
    `run.py` reported nothing at all rather than reporting what it could.

    **What the neutered body returns changes how sharp the answer is.** For the
    checkers, whose results are concatenated, `return []` fails exactly the tests
    that cover that check -- so "1 failed" localises the coverage. `return None`
    breaks the concatenation instead, failing every check test at once: still proof
    the function is load-bearing, but no longer proof that any single test isolates
    it. Prefer the value the caller actually composes; the default suits list
    returns because that is what this codebase's checkers do.
    """
    original = path.read_text()
    pattern = (
        rf'( *def {re.escape(function)}\([^)]*\)[^:]*:\n(?: *""".*?"""\n)?)'
    )
    def _neuter(match: re.Match) -> str:
        head = match.group(0)
        indent = " " * (len(head) - len(head.lstrip(" ")))
        return f"{head}{indent}    return {args_returns}\n"

    mutated, count = re.subn(pattern, _neuter, original, flags=re.S)
    if count == 0:
        raise SystemExit(f"could not find {function} in {path}")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as backup:
        backup.write(original)
    try:
        path.write_text(mutated)
        passed, summary = _run_suite()
        return not passed, summary
    finally:
        path.write_text(original)
        _clear_pycache()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("function", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--returns",
        default="[]",
        help="what the neutered body returns; see mutate() on why it matters",
    )
    args = parser.parse_args()

    path = ROOT / args.path
    if args.all:
        targets = _function_names(path.read_text())
        if not targets:
            raise SystemExit(f"--all found no module-level functions in {path}")
    else:
        if not args.function:
            raise SystemExit("give a function name or --all")
        targets = [args.function]

    baseline_ok, baseline = _run_suite()
    if not baseline_ok:
        raise SystemExit(f"suite is not green to begin with: {baseline}")
    print(f"baseline: {baseline}\n")

    survivors = []
    for name in targets:
        caught, summary = mutate(path, name, args.returns)
        print(f"  {'caught  ' if caught else 'SURVIVED'}  {name:32} {summary}")
        if not caught:
            survivors.append(name)

    ok, summary = _run_suite()
    print(f"\nrestored: {summary}")
    if survivors:
        print(f"\nNOT COVERED: {', '.join(survivors)}")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
