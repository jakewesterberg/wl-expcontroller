"""`wlx` — the command line.

`wlx check` is the reason this exists. The load-time checks were reachable only
from tests, which meant the guardrail that refuses a malformed task could not
actually be run against one by a person, in CI, or by whatever tool eventually
loads tasks on a rig. A check nobody can invoke is a test, not a guardrail.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from wl_expcontroller.check import check
from wl_expcontroller.task import Trial


def _load_trial(path: Path) -> Trial:
    """Import a task file and return the `Trial` it defines.

    Tasks are plain Python declarations (ADR-0006), so loading one is an import.
    That is also why the checks run *at load*: by the time this returns, the task
    is a data structure that can be inspected rather than a program to be trusted.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    trials = [v for v in vars(module).values() if isinstance(v, Trial)]
    if len(trials) != 1:
        raise SystemExit(f"{path} defines {len(trials)} trials; expected exactly 1")
    return trials[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wlx")
    sub = parser.add_subparsers(dest="command", required=True)
    checker = sub.add_parser("check", help="run the load-time checks on a task file")
    checker.add_argument("task", type=Path)
    args = parser.parse_args(argv)

    findings = check(_load_trial(args.task))
    for finding in findings:
        marker = "refused " if finding.blocking else "review  "
        print(f"{marker} {finding.code:28} {finding.detail}")

    blocking = [f for f in findings if f.blocking]
    if blocking:
        print(f"\n{len(blocking)} blocking finding(s): task refused")
        return 1
    if findings:
        print(f"\n{len(findings)} non-blocking finding(s): task needs human review")
    else:
        print("no findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
