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

from wl_expcontroller.bounds import Bounds
from wl_expcontroller.check import check
from wl_expcontroller.review import render
from wl_expcontroller.codes import PROVISIONAL, Allocation
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


def _load_allocation(path: Path | None) -> Allocation:  # noqa: C901
    """Load the allocation a task is checked against.

    Separate from the task on purpose: codes are allocated elsewhere and never
    invented in a task (S2 §6.1), so the two arrive by different routes and a task
    cannot smuggle in its own vocabulary.
    """
    if path is None:
        return PROVISIONAL
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found = vars(module).get("ALLOCATION")
    if not isinstance(found, Allocation):
        raise SystemExit(f"{path} must define ALLOCATION")
    return found


def _load_bounds(path: Path):
    """Load a subject's bounded config. **Welfare-critical input** (S8 §4).

    A separate file from the task and from the allocation, arriving by its own route,
    because a task may name how reward is configured and must never be able to say
    how much it is. A file that does not define `BOUNDS` is refused rather than
    treated as an empty config -- an empty one has no ceilings, and `Welfare` would
    refuse it a moment later anyway with a message about the wrong thing.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found = vars(module).get("BOUNDS")
    if not isinstance(found, Bounds):
        raise SystemExit(f"{path} must define BOUNDS")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wlx")
    sub = parser.add_subparsers(dest="command", required=True)
    checker = sub.add_parser("check", help="run the load-time checks on a task file")
    checker.add_argument("task", type=Path)
    checker.add_argument("--allocation", type=Path, default=None)

    reviewer = sub.add_parser(
        "review", help="render the artifact a task is approved from"
    )
    reviewer.add_argument("task", type=Path)
    reviewer.add_argument("--allocation", type=Path, default=None)

    runner = sub.add_parser("run", help="run a session headless against simulators")
    runner.add_argument("task", type=Path)
    runner.add_argument("--allocation", type=Path, default=None)
    runner.add_argument("--root", type=Path, required=True)
    runner.add_argument("--session-id", required=True)
    runner.add_argument("--subject", required=True)
    runner.add_argument("--trials", type=int, default=1000)
    runner.add_argument("--seed", type=int, default=1)
    runner.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    runner.add_argument(
        "--bounds",
        type=Path,
        required=True,
        help="the subject's bounded config: a Python file defining BOUNDS",
    )
    runner.add_argument(
        "--delivered-today",
        type=float,
        default=None,
        help="mL already delivered to this subject today, from wl-works. Omitted "
        "means unknown, and the day's shortfall is then unreportable -- reward is "
        "still delivered, because the daily figure is a floor and not a ceiling",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        from wl_expcontroller.dio import Simulated as SimulatedCard
        from wl_expcontroller.taskd import Session, SessionSpec
        from wl_expcontroller.welfare import Simulated as SimulatedPump

        values: dict[str, object] = {}
        for assignment in args.set:
            name, _, raw = assignment.partition("=")
            try:
                values[name] = float(raw)
            except ValueError:
                values[name] = raw
        session = Session(
            SessionSpec(
                task=str(args.task),
                allocation=str(args.allocation) if args.allocation else "",
                root=args.root,
                session_id=args.session_id,
                subject=args.subject,
                trials=args.trials,
                frame_period=1 / 240,
                seed=args.seed,
                values=values,
                bounds=_load_bounds(args.bounds),
                already_delivered_today=args.delivered_today,
            ),
            # Simulators, because that is what this subcommand is for. The refusing
            # implementations are the defaults everywhere else, and a headless run
            # that silently used a real card would be the worse surprise.
            card=SimulatedCard(),
            pump=SimulatedPump(),
        )
        # Headless: nothing puts an animal in a chair, so the restraint clock starts
        # with the session. On a rig this is the console's action, and the difference
        # is the whole reason S8 makes it an explicit one.
        session.head_fixed(at=0.0)
        census = session.run()
        total = sum(census.outcomes.values()) or 1
        for outcome, count in census.outcomes.most_common():
            print(f"  {outcome.value:18} {count:6}  {100 * count / total:5.1f}%")
        print(f"  {'hangs':18} {census.hangs:6}")
        print(f"  ended: {session.stopped_because}")
        print(
            f"  fluid: {session.welfare.commanded:.2f} mL commanded over "
            f"{session.welfare.deliveries} deliveries"
        )
        # The number a person acts on: how much of the day's minimum is still owed,
        # to be supplemented after the session (PI, 2026-09-06). `None` means the
        # day cannot be counted, which is a louder result than any number.
        owed = session.welfare.shortfall()
        print(
            "  supplement: UNKNOWN -- the day's prior total was not supplied, so "
            "nothing can say what is still owed"
            if owed is None
            else f"  supplement: {owed:.2f} mL to reach the day's floor"
        )
        return 1 if census.hangs else 0

    if args.command == "review":
        allocation = _load_allocation(args.allocation)
        print(render(_load_trial(args.task), allocation.task_events))
        return 0

    findings = check(_load_trial(args.task), _load_allocation(args.allocation))
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
