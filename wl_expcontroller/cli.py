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
from contextlib import nullcontext
from pathlib import Path

from wl_expcontroller import link as _link
from wl_expcontroller.bounds import Bounds
from wl_expcontroller.check import check
from wl_expcontroller.review import render as render_review
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


def render(frame: _link.Telemetry) -> str:
    """One screen's worth of a `Telemetry` frame -- S9a §4's panes this slice has
    data for: fluid, chair, trials by outcome, what is still owed, staged changes
    and refusals. `wlx console`'s only view of a running session.

    **Every line names a field of `Telemetry`; nothing here is computed.** That is
    the same discipline `Telemetry.of` itself follows (S9a §9, `link.py`), one hop
    further out: a renderer that summed or derived a number instead of printing the
    field would be a second implementation that could quietly disagree with the
    record the moment the two drifted apart.

    **Unknown prints `UNKNOWN`, never `0.0`.** `fluid_today_ml`/`shortfall_ml` are
    `None` exactly when `welfare.shortfall()` refused to guess (see `link.py`'s
    module docstring), and `wlx run` already renders that refusal as `UNKNOWN`
    rather than a confident zero. This must agree with it -- a console and a
    headless run disagreeing about whether a day is known would be the same
    failure surfacing twice, differently.

    **Staged changes are shown with who staged them, and so are refusals.** S9a §8
    removed the write lock; staged visibility -- to every console, not only the one
    that staged it -- is what replaces it, so a change already accepted but not
    yet applied must be visible as queued. Refusals are the audit trail for a
    write that did *not* happen: a person who mistyped a parameter name needs to
    see that on screen, not only in a log nobody is watching.
    """
    lines = [
        f"session {frame.session_id}  subject {frame.subject}  "
        f"trial {frame.trial_index}  block {frame.block}",
    ]
    if frame.stopped_because:
        lines.append(f"  STOPPED: {frame.stopped_because}")

    lines.append(f"  fluid session: {frame.fluid_session_ml:.2f} mL")
    lines.append(
        "  fluid today: UNKNOWN -- the day's prior total was not supplied"
        if frame.fluid_today_ml is None
        else f"  fluid today: {frame.fluid_today_ml:.2f} mL"
    )
    # Matches `wlx run`'s own wording (below) exactly -- see this function's
    # docstring for why the two must agree.
    lines.append(
        "  supplement: UNKNOWN -- the day's prior total was not supplied, so "
        "nothing can say what is still owed"
        if frame.shortfall_ml is None
        else f"  supplement: {frame.shortfall_ml:.2f} mL to reach the day's floor"
    )
    lines.append(f"  chair: {frame.chair_seconds:.1f} s")

    attempted = sum(frame.outcomes.values())
    by_outcome = ", ".join(f"{name} {count}" for name, count in frame.outcomes.items())
    lines.append(
        f"  trials: {attempted} attempted ({by_outcome or 'none yet'}), "
        f"{frame.hangs} hangs"
    )

    still_owed = ", ".join(f"{name} {count}" for name, count in frame.owed.items())
    lines.append(f"  still owed: {still_owed or 'none'}")

    if frame.staged:
        for change in frame.staged:
            kind = "bounded" if change.bounded else "task"
            lines.append(
                f"  staged: {change.name} {change.was} -> {change.now} "
                f"by {change.by} ({kind})"
            )
    else:
        lines.append("  staged: none")

    if frame.refusals:
        for refusal in frame.refusals:
            lines.append(f"  refused: {refusal.name} by {refusal.by}: {refusal.why}")
    else:
        lines.append("  refused: none")

    return "\n".join(lines)


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
    runner.add_argument(
        "--link",
        default=None,
        metavar="PUB,REQ",
        help="open a console link, bound on these two endpoints (PUB for "
        "telemetry, REP for commands), e.g. "
        "tcp://127.0.0.1:5571,tcp://127.0.0.1:5572. Omitted, the session runs "
        "with no console attached -- exactly as it did before this option "
        "existed, and with no transport dependency acquired",
    )

    console_parser = sub.add_parser(
        "console", help="attach to a running session's link and watch it"
    )
    console_parser.add_argument(
        "--sub", required=True, help="the session's PUB endpoint (telemetry)"
    )
    console_parser.add_argument(
        "--req", required=True, help="the session's REP endpoint (commands)"
    )
    console_parser.add_argument(
        "--as",
        dest="actor",
        default=None,
        metavar="WHO",
        help="the operator's name. Required by --set/--stop (S9a §6): every "
        "welfare-affecting action records its actor, and a write given with no "
        "--as is refused here rather than defaulting to a name -- a forgeable or "
        "invented actor is worse than none",
    )
    console_parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="stage a parameter change, applied at the session's next trial "
        "boundary; may be given more than once. VALUE must be numeric -- "
        "SetParameter carries a float, and this console will not guess what a "
        "non-numeric value meant",
    )
    console_parser.add_argument(
        "--stop",
        action="store_true",
        help="end the session at its next trial boundary",
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

        # `--link` is the only thing in this command that can reach `zmq`; built
        # here, not at module level, so `wlx run` with no `--link` never acquires
        # the transport dependency (S9a §5's argument for the display layer,
        # holding identically here -- see `link.encode`'s docstring). A plain
        # `nullcontext(None)` when it is omitted keeps `Session`'s own default
        # (`link.Absent()`) untouched, so behaviour with no `--link` is unchanged.
        if args.link is not None:
            pub_endpoint, sep, rep_endpoint = args.link.partition(",")
            if not sep:
                raise SystemExit(
                    f"--link expects PUB,REQ (two comma-separated endpoints), "
                    f"got {args.link!r}"
                )
            link_cm = _link.ZmqLink(pub_endpoint, rep_endpoint)
        else:
            link_cm = nullcontext(None)

        # A context manager, not a bare try/finally: `ZmqLink.close()`'s own
        # docstring names this command as the thing its "nothing calls close() in
        # production yet" was waiting for. `with` is what makes that no longer
        # true, on every exit from this block -- normal return or an exception
        # from `session.run()` alike.
        with link_cm as opened_link:
            session_kwargs: dict[str, object] = {}
            if opened_link is not None:
                session_kwargs["link"] = opened_link
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
                # Simulators, because that is what this subcommand is for. The
                # refusing implementations are the defaults everywhere else, and a
                # headless run that silently used a real card would be the worse
                # surprise.
                card=SimulatedCard(),
                pump=SimulatedPump(),
                **session_kwargs,
            )
            # Headless: nothing puts an animal in a chair, so the restraint clock
            # starts with the session. On a rig this is the console's action, and
            # the difference is the whole reason S8 makes it an explicit one.
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
            # The number a person acts on: how much of the day's minimum is still
            # owed, to be supplemented after the session (PI, 2026-09-06). `None`
            # means the day cannot be counted, which is a louder result than any
            # number.
            owed = session.welfare.shortfall()
            print(
                "  supplement: UNKNOWN -- the day's prior total was not supplied, "
                "so nothing can say what is still owed"
                if owed is None
                else f"  supplement: {owed:.2f} mL to reach the day's floor"
            )
            return 1 if census.hangs else 0

    if args.command == "console":
        wants_write = bool(args.set) or args.stop
        if wants_write and not args.actor:
            print(
                "refused: --set/--stop changes a running session, and every "
                "welfare-affecting action must record its actor (S9a §6) -- pass "
                "--as <who>. A write with no actor is refused here rather than "
                "defaulting to a name, because a forgeable or invented actor is "
                "worse than none.",
                file=sys.stderr,
            )
            return 1

        commands: list[_link.Command] = []
        for assignment in args.set:
            name, _, raw = assignment.partition("=")
            try:
                value = float(raw)
            except ValueError:
                print(
                    f"refused: --set {assignment!r} is not NAME=VALUE with a "
                    f"numeric VALUE",
                    file=sys.stderr,
                )
                return 1
            commands.append(_link.SetParameter(name=name, value=value, by=args.actor))
        if args.stop:
            commands.append(_link.Stop(by=args.actor))

        with _link.ZmqConsole(args.sub, args.req) as console:
            for command in commands:
                console.send(command)
            # Watches until the session says it has stopped, or the operator
            # interrupts -- "the console prints frames as trials run" is a live
            # view, not a one-shot query. `stopped_because` is the session's own
            # last word (`taskd.Session.run`'s `publish()` fires it on every stop
            # path), so waiting for it rather than for `receive()` to time out is
            # what lets this exit on a natural end instead of after 5 idle
            # seconds.
            try:
                while True:
                    frame = console.receive()
                    print(render(frame))
                    print()
                    if frame.stopped_because:
                        break
            except KeyboardInterrupt:
                pass
            except TimeoutError as exc:
                print(f"console: {exc}", file=sys.stderr)
                return 1
        return 0

    if args.command == "review":
        allocation = _load_allocation(args.allocation)
        print(render_review(_load_trial(args.task), allocation.task_events))
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
