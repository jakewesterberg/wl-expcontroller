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
import ast
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

#: `-rfE` makes pytest end with one line per failed or errored test. **Keeping only
#: the last line is how the 2026-09-25 nightly went red on a flaky test without once
#: naming it** (run 36115579357: `1 failed, 673 passed` on 7 of 41 unmutated runs).
#: The message on each line is trimmed to the terminal width *unless* `CI` or
#: `BUILD_NUMBER` is set, which GitHub Actions does -- pytest 9.1.1,
#: `_pytest/terminal.py:_get_line_with_reprcrash_message` and
#: `_pytest/compat.py:running_on_ci`, read 2026-09-26 -- so CI gets it whole.
SUITE_ARGV = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE"]

#: How many failing tests a mutant's line names before it only counts the rest.
NAMED = 3


def _run_suite(cwd: Path = ROOT) -> tuple[bool, str, list[str]]:
    """Whether the suite passed, pytest's final line, and one line per failure.

    `cwd` is only ever the repository in use; it is a parameter so a test can run
    this, end to end, against a three-test suite rather than this one.
    """
    _clear_pycache()
    try:
        result = subprocess.run(
            [sys.executable, *SUITE_ARGV],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {SUITE_TIMEOUT_SECONDS}s (mutation hangs)", []
    output = result.stdout.strip().splitlines()
    return (
        result.returncode == 0,
        output[-1] if output else "no output",
        _failures(result.stdout),
    )


def _failures(stdout: str) -> list[str]:
    """The `FAILED ...`/`ERROR ...` lines of pytest's short test summary.

    **Only the summary is read.** A failing test's captured output is echoed above
    it, verbatim, so a line there that happens to start `FAILED ` is not a failure.
    """
    lines = stdout.splitlines()
    start = next(
        (n for n, line in enumerate(lines) if "short test summary info" in line), None
    )
    if start is None:
        return []
    return [line for line in lines[start + 1 :] if line.startswith(("FAILED ", "ERROR "))]


def _caught_by(failures: list[str]) -> str:
    """What to append to a mutant's line: the tests that failed, by node id.

    On 2026-09-25 a flaky test added exactly one failure to 24 mutant runs. A mutant
    nothing really covers reads `1 failed` in that run and is reported `caught`; the
    name of the test that did the catching is the only thing that shows it.
    """
    if not failures:
        return ""
    names = [line.split(" ", 1)[1].split(" - ", 1)[0] for line in failures]
    shown = ", ".join(names[:NAMED])
    rest = len(names) - NAMED
    return f"  <- {shown}" + (f", +{rest} more" if rest > 0 else "")


def _function_names(source: str) -> list[str]:
    """Every function, module-level and method alike, and each name once.

    Four blind spots found by using it, all the same shape -- the tool quietly
    examining nothing and reporting success. First it matched only `_`-prefixed
    names, so a run over `simulate.py` covered none of it. Then it matched only
    module-level `def`, so `record.py` -- which is entirely methods -- reported
    nothing to mutate, which reads like nothing to check. Then, found by replacing
    the pattern with the parser: `^ *def ([a-z_][a-z0-9_]*)\\(` cannot spell a
    capital, so **`photometry._XYZ` and `task.FixPoint` had never been mutated
    once** and no output said so -- they were simply not on the list.

    A coverage tool that can silently cover nothing has the exact failure mode it
    exists to catch, so `--all` refuses an empty target list and this asks the
    parser rather than a pattern.

    **And each name once.** Every definition of a name is neutered together, so a
    name six worlds implement ran six identical sweeps against identical inputs for
    identical results -- and a sweep is a full run of the suite. `run.py` was
    twenty-four targets and is twelve; `dio.py` was fourteen and is six.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = sorted(
        (node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return list(dict.fromkeys(name for _, name in found))


#: Returned by `mutate` when the neutered body is the body it already had.
INERT = "inert"


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _neuter_source(source: str, function: str, returns: str) -> tuple[str | None, str]:
    r"""`source` with every definition of `function` returning `returns` first, or
    `(None, why)` when there is nothing this can safely do.

    **This asks the parser where a body starts.** It used to ask a regex, and that
    regex was wrong three times in three different ways. A trailing comment defeated
    the match, so `def __repr__(self) -> str:  # pragma: no cover` aborted a whole
    sweep. A body on the signature's own line matched, and the line inserted after it
    made a `SyntaxError`. And a default argument containing a `)` ended the signature
    early: `\([^)]*\)` stops inside `Params()`, so `saccade.detect` could not be
    found at all, and in `calibration.recenter` the scan for the colon ran on into
    `why: str` and inserted a statement **into the parameter list**.

    That last one is the seventh time this harness has been wrong and the third that
    broke toward a false *clean*: the suite reported collection errors, `mutate` read
    the non-zero exit as the mutation being caught, and a function that had never in
    its life been mutated was reported covered. The nightly on `main` still prints
    `caught recenter  2 errors in 0.82s`, which is what that looks like from outside.

    A parser cannot make any of those three mistakes, because `body[0]` **is** the
    body. Two decisions are left, and both are about where the line goes rather than
    about where the body is:

    - a docstring is stepped over rather than displaced, so the mutation lands below
      it and the function keeps its documentation;
    - a body written on the signature's own line is refused *for that definition*,
      because no line can follow `def deliver(self, ml: float) -> None: ...` and still
      parse. Its siblings are still neutered -- a Protocol stub beside a real
      implementation must not exempt the implementation.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, f"{function}: source does not parse ({exc})"

    lines = source.splitlines(keepends=True)
    insertions: list[tuple[int, str]] = []
    on_signature_line = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function:
            continue
        anchor = node.body[0]
        if lines[anchor.lineno - 1][: anchor.col_offset].strip():
            on_signature_line += 1
            continue
        at = anchor.end_lineno if _is_docstring(anchor) else anchor.lineno - 1
        insertions.append((at, " " * anchor.col_offset + f"return {returns}\n"))

    if not insertions:
        if on_signature_line:
            return None, f"{function} is written on its signature's own line"
        return None, f"could not find {function}"

    # Descending, so an earlier insertion cannot move a later one's line number.
    for at, text in sorted(insertions, reverse=True):
        if at and not lines[at - 1].endswith("\n"):
            lines[at - 1] += "\n"
        lines.insert(at, text)
    return "".join(lines), ""


def _already_inert(source: str, function: str, returns: str) -> bool:
    """True when inserting `return {returns}` at the top of `function` changes nothing.

    **A function that already returns immediately cannot be neutered, because it is
    already neutral.** `Quiet.display` and `Scripted.display` are `return None`;
    `World.display` is a docstring. Neutering inserts `return None` above a body that
    was `return None`, the suite passes because nothing changed, and the harness
    called that a SURVIVOR -- so the mutation gate could never go green, and the
    build failed on three functions that are not defects. `docs/CHECKPOINT.md` had
    been carrying the discrepancy as a footnote ("the only non-caught entries are
    no-op display bodies") rather than as the tool bug it is.

    **This must stay narrow.** It is the fifth time this harness has been changed,
    and the previous four were all it quietly examining nothing and reporting
    success -- so a category that does not fail the build is exactly the shape of the
    recurring bug. The condition is therefore proved from the AST, not guessed: every
    definition of the name must already begin (after any docstring) with the very
    statement the mutation would insert, or be empty where the insertion is
    `return None`. If any one definition would really be changed, this is False and a
    survivor is a real survivor.
    """
    try:
        tree = ast.parse(source)
        wanted = ast.dump(ast.parse(f"return {returns}").body[0])
    except SyntaxError:
        return False

    found = False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function:
            continue
        found = True
        body = list(node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]  # the docstring is not a statement the mutation displaces
        neutral_already = returns.strip() == "None" and (
            not body
            or isinstance(body[0], ast.Pass)
            or (
                isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and body[0].value.value is Ellipsis
            )
        )
        if neutral_already:
            continue
        if body and ast.dump(body[0]) == wanted:
            continue
        return False
    return found


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
    if _already_inert(original, function, args_returns):
        return INERT, f"body is already `return {args_returns}`; nothing to neuter"
    mutated, why = _neuter_source(original, function, args_returns)
    if mutated is None:
        # A miss is reported, never fatal. Under `--all` an abort here stopped the
        # sweep at the first unmatchable signature, and every function *after* it
        # went silently unmutated -- which reads as a completed run. That is the
        # same false-clean failure this whole script exists to prevent, and it is
        # the fourth blind spot of exactly that shape.
        return None, why

    try:
        path.write_text(mutated)
        # Written *after* the mutation, holding both texts: the restore checks the
        # file still looks like what it wrote before putting the original back.
        SENTINEL.write_text(
            json.dumps({"path": str(path), "original": original, "mutated": mutated})
        )
        passed, summary, failures = _run_suite()
        return not passed, summary + _caught_by(failures)
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
    baseline_ok, baseline, failures = _run_suite()
    if not baseline_ok:
        raise SystemExit(
            "\n".join([f"suite is not green to begin with: {baseline}", *failures])
        )
    print(f"baseline: {baseline}\n")

    survivors = []
    skipped = []
    inert = []
    for name in targets:
        caught, summary = mutate(path, name, args.returns)
        if caught is None:
            skipped.append(name)
            print(f"  SKIPPED   {name:32} {summary}")
            continue
        if caught is INERT:
            inert.append(name)
            print(f"  inert     {name:32} {summary}")
            continue
        print(f"  {'caught  ' if caught else 'SURVIVED'}  {name:32} {summary}")
        if not caught:
            survivors.append(name)

    ok, summary, failures = _run_suite()
    print("\n".join([f"\nrestored: {summary}", *failures]))
    if inert:
        # Printed, never fatal, and never silent: these are functions no mutation
        # can reach, and a reader has to be able to tell that from coverage.
        print(f"\nNOT MUTABLE (already returns immediately): {', '.join(inert)}")
    if skipped:
        print(f"\nNOT MUTATED (signature not matched): {', '.join(skipped)}")
    if survivors:
        print(f"\nNOT COVERED: {', '.join(survivors)}")
    if survivors or skipped:
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
