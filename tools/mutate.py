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
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Written before a file is mutated and removed after it is restored. A `finally`
#: cannot survive SIGKILL, and a timeout kills -- which once left a neutered
#: `__exit__` on disk that was then committed and pushed, because the commit did not
#: re-run the suite. The sentinel makes the damage self-healing rather than silent:
#: the next run restores from it before doing anything else.
SENTINEL = ROOT / ".mutate-in-progress.json"


def _restore_any_interrupted_run() -> None:
    """Undo a mutation left behind by a killed process -- **only if it is still there**.

    Called before anything else, including the baseline, so a suite that looks red
    because of a stale mutation is repaired rather than reported.

    **It restores only when the file still matches the text this tool wrote.** A
    blind restore is worse than the problem it solves: run this in the background,
    edit the source while it holds a mutation, and healing would revert that work
    silently. Never edit source while this is running; this check is the backstop,
    not permission.
    """
    if not SENTINEL.exists():
        return
    saved = json.loads(SENTINEL.read_text())
    path = Path(saved["path"])
    current = path.read_text()
    if current == saved["mutated"]:
        path.write_text(saved["original"])
        print(f"restored {path} from an interrupted run\n")
    elif current == saved["original"]:
        pass  # someone already put it back
    else:
        # **Do not restore.** The file has changed since the mutation, so the
        # sentinel's copy is stale and writing it back would silently revert
        # whatever was done in between. This nearly happened: a harness run was
        # backgrounded, source was edited while it held a mutation, and a
        # self-healing restore would have thrown that work away without a word.
        print(
            f"WARNING: {path} changed since an interrupted mutation run.\n"
            f"  Not restoring -- the sentinel's copy is stale and would revert "
            f"live edits.\n"
            f"  Check for a stray `return` at the top of a function, then delete "
            f"{SENTINEL.name}.\n"
        )
        return
    SENTINEL.unlink()


def _clear_pycache() -> None:
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


#: A mutated suite may not terminate. Neutering `Scheduler.record` stops the counts
#: advancing, so a test running a block to completion never sees it finish -- and the
#: suite hung until an outer timeout killed the whole harness, past its `finally`,
#: stranding a neutered module on disk. The sentinel healed that, but the hang is the
#: cause and this is the fix: a mutation that hangs counts as *caught*, since a suite
#: that no longer terminates has certainly noticed the mutation.
SUITE_TIMEOUT_SECONDS = 300


def _run_suite() -> tuple[bool, str]:
    _clear_pycache()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {SUITE_TIMEOUT_SECONDS}s (mutation hangs)"
    output = result.stdout.strip().splitlines()
    return result.returncode == 0, output[-1] if output else "no output"


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
        # `[^\n]*` after the colon so a trailing comment does not defeat the match.
        # `def __repr__(self) -> str:  # pragma: no cover` did, and under `--all`
        # that aborted the sweep at that line.
        rf'( *def {re.escape(function)}\([^)]*\)[^:]*:[^\n]*\n(?: *""".*?"""\n)?)'
    )
    def _neuter(match: re.Match) -> str:
        head = match.group(0)
        indent = " " * (len(head) - len(head.lstrip(" ")))
        return f"{head}{indent}    return {args_returns}\n"

    mutated, count = re.subn(pattern, _neuter, original, flags=re.S)
    if count == 0:
        # A miss is reported, never fatal. Under `--all` an abort here stopped the
        # sweep at the first unmatchable signature, and every function *after* it
        # went silently unmutated -- which reads as a completed run. That is the
        # same false-clean failure this whole script exists to prevent, and it is
        # the fourth blind spot of exactly that shape.
        return None, f"could not find {function}"

    try:
        path.write_text(mutated)
        # Written *after* the mutation, holding both texts: the restore checks the
        # file still looks like what it wrote before putting the original back.
        SENTINEL.write_text(
            json.dumps({"path": str(path), "original": original, "mutated": mutated})
        )
        passed, summary = _run_suite()
        return not passed, summary
    finally:
        path.write_text(original)
        SENTINEL.unlink(missing_ok=True)
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

    _restore_any_interrupted_run()
    baseline_ok, baseline = _run_suite()
    if not baseline_ok:
        raise SystemExit(f"suite is not green to begin with: {baseline}")
    print(f"baseline: {baseline}\n")

    survivors = []
    skipped = []
    for name in targets:
        caught, summary = mutate(path, name, args.returns)
        if caught is None:
            skipped.append(name)
            print(f"  SKIPPED   {name:32} {summary}")
            continue
        print(f"  {'caught  ' if caught else 'SURVIVED'}  {name:32} {summary}")
        if not caught:
            survivors.append(name)

    ok, summary = _run_suite()
    print(f"\nrestored: {summary}")
    if skipped:
        print(f"\nNOT MUTATED (signature not matched): {', '.join(skipped)}")
    if survivors:
        print(f"\nNOT COVERED: {', '.join(survivors)}")
    if survivors or skipped:
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
