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
from wl_expcontroller.bounds import Bounds, Exceeded
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


def _clock(seconds: float) -> str:
    """`seconds` as `H:MM:SS` (or `M:SS` under an hour) -- S9a §4's own chair-time
    example (`1:47 / 4:00`). Formatting, not derivation: every digit comes from
    the one number passed in, read from `Telemetry.chair_seconds` and nowhere
    recomputed -- `render`'s own "nothing here is computed" promise is about a
    second *source* for a number, not about which base a human reads it in. Added
    fix round 1, minor: a raw `28702.8 s` is not a thing to show a person glancing
    at a screen.
    """
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _value(value: float | None) -> str:
    """A staged parameter value, to the same 2 decimal places every fluid figure on
    this screen uses.

    Formatting, not derivation -- see `_clock`, same reasoning. The staged line
    printed raw `repr` until 2026-09-19, so a reward volume read `0.15 -> 0.3` two
    lines under `fluid session: 1.25 mL`: the same quantity, the same screen, two
    conventions, and the one that looked like a typo was the welfare-bounded one.

    `None` is `Staged.was` for a parameter the session had no prior value for. It
    prints `unset` rather than `0.00`, for the reason `fluid_today_ml` prints
    `UNKNOWN`: a value nobody has is not a value of zero.
    """
    return "unset" if value is None else f"{value:.2f}"


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

    **The two fluid lines are the condition of a welfare ruling, not a readout.**
    A reward volume of zero is *allowed* -- pausing reward without ending a session
    -- and the PI allowed it on 2026-09-20 **because it is visible**: `fluid
    session: 0.00 mL` is how an operator sees that a correctly-working animal is
    being paid nothing, and `supplement:` keeps reporting the whole floor as owed so
    it is topped up afterwards. **A change that stopped showing either would turn a
    permitted operation into a silent one** -- a welfare regression reached by
    simplifying a console pane, which is exactly why this sentence is here and not
    only in S8 §5.2c.

    **Staged changes are shown with who staged them, and so are refusals.** S9a §8
    removed the write lock; staged visibility -- to every console, not only the one
    that staged it -- is what replaces it, so a change already accepted must be
    visible. Refusals are the audit trail for a write that did *not* happen: a
    person who mistyped a parameter name needs to see that on screen, not only in a
    log nobody is watching.

    **A capped refusal feed says so.** `Telemetry.refusals` keeps only the most
    recent `link.REFUSAL_HISTORY`, because a peer this end does not control decides
    how fast they arrive. `refusals_dropped` is printed above the rows rather than
    below them -- a reader scans down, and learning at the bottom that the fifty
    lines above were the tail of four hundred is learning it too late.

    **A staged row says which vocabulary the name belongs to, and that it applies at
    the next trial** (PI, 2026-09-19). Both kinds defer: `Session._apply_staged`
    writes an ordinary task parameter into `spec.values` and a welfare-bounded one
    onto its ceiling, in the same pass, and the trial running now uses the old value
    either way. The two are still named apart because the stakes are -- a reward
    volume and a fixation hold are not the same row to read past.

    This screen briefly said `ALREADY IN EFFECT` of a bounded row, and that was
    true when it was written: `Session.set` moved the ceiling as the command was
    drained. Saying it now would be the same lie in the more dangerous direction --
    an operator who has just *lowered* a reward volume, told it has taken effect
    while one more trial is still to go out at the old one. `taskd.Session.set` and
    `bounds.Bounds.validate` carry the behaviour and why it changed.

    **A volume is printed to 2 decimal places, like every other fluid figure on this
    screen.** `reward_correct` appears on the staged line, and printing it at raw
    `repr` while the fluid lines above use `:.2f` puts `0.15 -> 0.3` and `0.30 mL` on
    the same screen for the same quantity.
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
    # The out-of-cage line is first because it is the one that ends the session
    # (PI, 2026-09-19). Chair time is below it and bounds nothing; showing only
    # chair time, as this screen did until then, meant an operator watched a
    # session stop on a clock the console had never displayed.
    lines.append(
        "  out of cage: n/a -- cage-side, the animal is home"
        if frame.out_of_cage_seconds is None
        else f"  out of cage: {_clock(frame.out_of_cage_seconds)}"
    )
    lines.append(f"  chair: {_clock(frame.chair_seconds)}")

    # Fix round 1, IMPORTANT 2: this used to open with `sum(frame.outcomes.values())
    # attempted`, a computed total that also silently excluded hangs (5 outcomes
    # plus 2 hangs printed "5 attempted" when 7 trials ran) -- both a wrong number
    # and a direct contradiction of this function's own "nothing here is computed"
    # promise a few lines up. `frame.outcomes` and `frame.hangs` are read as they
    # are, with no total claimed; a reader who wants one can add what is on screen.
    by_outcome = ", ".join(f"{name} {count}" for name, count in frame.outcomes.items())
    lines.append(f"  trials: {by_outcome or 'none yet'}, hangs {frame.hangs}")

    still_owed = ", ".join(f"{name} {count}" for name, count in frame.owed.items())
    lines.append(f"  still owed: {still_owed or 'none'}")

    if frame.staged:
        for change in frame.staged:
            # Fix round 1, minor: a bare "(task)"/"(bounded)" tag names an
            # internal field, not what it means to whoever is reading the
            # screen -- spelled out instead. Both clauses end the same way
            # because both rows now land at the same moment (PI, 2026-09-19);
            # what differs is which limit the value was checked against. See
            # this function's docstring and `taskd.Session.set`.
            kind = (
                "welfare-bounded ceiling, applies at the next trial"
                if change.bounded
                else "task parameter, applies at the next trial"
            )
            lines.append(
                f"  staged: {change.name} {_value(change.was)} -> "
                f"{_value(change.now)} by {change.by} ({kind})"
            )
    else:
        lines.append("  staged: none")

    if frame.refusals:
        # Before the rows, not after: a person reads down and would otherwise see
        # fifty refusals and learn only at the bottom that there were four hundred.
        if frame.refusals_dropped:
            lines.append(
                f"  refused: {frame.refusals_dropped} earlier refusal(s) NOT SHOWN "
                f"-- only the most recent {len(frame.refusals)} are kept "
                f"(link.REFUSAL_HISTORY)"
            )
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
        "--out-of-cage-ago",
        type=float,
        required=True,
        metavar="SECONDS",
        help="how long ago this subject came out of its home cage, in seconds. "
        "**Required, with no default**, for the reason `--as WHO` is: the session's "
        "one welfare limit runs out of cage to back in cage (S8 5.2), and a default "
        "of zero would silently make it equal chair time -- the under-count that "
        "limit replaced chair time to remove. A headless run says `0` and means it. "
        "Refused if it is in the future or longer ago than the subject's out_of_cage "
        "ceiling, which is also what catches a wall-clock timestamp handed to a "
        "how-long-ago",
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
        metavar="PUB,REP",
        help="open a console link on two endpoints THIS SESSION binds: first the "
        "PUB endpoint it publishes telemetry on, then the REP endpoint it "
        "receives commands on, e.g. "
        "tcp://127.0.0.1:5571,tcp://127.0.0.1:5572. A console attaches to the "
        "same pair from the other side, passing the first to `wlx console "
        "--sub` and the second to `--req`. Loopback only unless "
        "--link-allow-remote is also given. Omitted, the session runs with no "
        "console attached -- exactly as it did before this option existed, and "
        "with no transport dependency acquired",
    )
    runner.add_argument(
        "--link-allow-remote",
        action="store_true",
        help="permit --link to bind an endpoint other hosts can reach (0.0.0.0, a "
        "LAN address, a wildcard). Refused by default: the console link has no "
        "authentication yet, so `--as WHO` is whatever the sender typed, and any "
        "host that can reach the REP port can move a reward volume or stop the "
        "session under an invented name. S9a §6 designs the real thing and it is "
        "P4d-3's; this flag does not make a remote bind safe, only deliberate",
    )

    console_parser = sub.add_parser(
        "console", help="attach to a running session's link and watch it"
    )
    # `--link PUB,REP` names the SESSION's sockets and `--sub`/`--req` name this
    # CONSOLE's, so the endpoints cross over: `--sub` takes the session's PUB and
    # `--req` takes its REP. Both spellings are the right ones for the process being
    # configured -- renaming either would make that process's own flag describe
    # somebody else's socket -- so the help says the pairing outright instead.
    console_parser.add_argument(
        "--sub",
        required=True,
        metavar="SESSION_PUB",
        help="where to SUBscribe for telemetry: the session's PUB endpoint, i.e. "
        "the FIRST of the two given to `wlx run --link PUB,REP`",
    )
    console_parser.add_argument(
        "--req",
        required=True,
        metavar="SESSION_REP",
        help="where to send commands: the session's REP endpoint, i.e. the SECOND "
        "of the two given to `wlx run --link PUB,REP`",
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
        from wl_expcontroller.welfare import Deployment, Simulated as SimulatedPump

        values: dict[str, object] = {}
        for assignment in args.set:
            name, sep, raw = assignment.partition("=")
            # The same unchecked split `wlx console --set` had, one subcommand over
            # -- refused here too rather than only where a reviewer happened to look.
            # An empty name here is quieter and no better: it lands in `spec.values`,
            # gets written into the session's own parameter snapshot, and matches no
            # `Param` any task declares, so it is a row in the record that means
            # nothing.
            if not sep or not name:
                raise SystemExit(
                    f"--set expects NAME=VALUE with a parameter name before the "
                    f"'=', got {assignment!r}"
                )
            try:
                values[name] = float(raw)
            except ValueError:
                values[name] = raw

        # `--link` is the only thing in this command that can reach `zmq`; built
        # here, not at module level, so `wlx run` with no `--link` never acquires
        # the transport dependency (S9a §5's argument for the display layer,
        # holding identically here -- see `link.encode`'s docstring). A plain
        # `nullcontext(None)` when it is omitted keeps `Session`'s own default
        # (`link.Absent()`) untouched, so behavior with no `--link` is unchanged.
        if args.link is not None:
            # Fix round 1, minor: `.partition(",")` on a value with a second
            # comma (`"a,b,c"`) silently took everything after the first comma
            # -- `"b,c"` -- as one endpoint, rather than refusing it. `.split`
            # plus an exact length check refuses anything that is not exactly
            # two comma-separated parts.
            link_parts = args.link.split(",")
            if len(link_parts) != 2:
                raise SystemExit(
                    f"--link expects PUB,REP (exactly two comma-separated "
                    f"endpoints), got {args.link!r}"
                )
            pub_endpoint, rep_endpoint = link_parts
            # Refused rather than bound when an endpoint is reachable from another
            # host, unless --link-allow-remote says otherwise -- see
            # `ZmqLink.__init__`. Converted to `SystemExit` here so an operator gets
            # the sentence and not a traceback; the message is the one the link
            # wrote, which names what to pass instead.
            try:
                link_cm = _link.ZmqLink(
                    pub_endpoint, rep_endpoint, allow_remote=args.link_allow_remote
                )
            except _link.RemoteBindRefused as refused:
                raise SystemExit(str(refused)) from refused
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
                    # A simulated rig run, so the rig's limits apply. There is no
                    # flag for the cage-side deployment because there is no kiosk
                    # to run one on: S13 is a proposed spec, and `wl-touchtrain`
                    # owns the hardware (S13 §6 item 2). When one exists this is
                    # where its declaration is chosen.
                    deployment=Deployment.OUT_OF_CAGE,
                ),
                # Simulators, because that is what this subcommand is for. The
                # refusing implementations are the defaults everywhere else, and a
                # headless run that silently used a real card would be the worse
                # surprise.
                card=SimulatedCard(),
                pump=SimulatedPump(),
                **session_kwargs,
            )
            # On a rig both of these are the console's actions, and the difference
            # is the whole reason S8 makes them explicit. Here the out-of-cage one
            # comes from `--out-of-cage-ago`, which has no default: a headless run
            # with no animal says `0` and means it, rather than arriving at zero by
            # omission and quietly reporting chair time as time out of the cage.
            # Head-fixation lands at the session's own zero, which is what a
            # simulated session's restraint record is.
            # **A refused value is a message, not a traceback.** Everything else
            # this subcommand refuses -- a missing `BOUNDS`, an unloadable task, a
            # `--set` with no name -- exits with a sentence a person can act on, and
            # a welfare refusal is the last one that should read as a crash.
            try:
                session.left_cage(seconds_ago=args.out_of_cage_ago)
            except Exceeded as refused:
                raise SystemExit(f"refused: {refused}") from refused
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
            name, sep, raw = assignment.partition("=")
            # Final-review minor: the name was never checked, so `--set =0.5` built a
            # `SetParameter(name="", ...)` and sent it, to be refused by the session
            # over a socket. `--link` was hardened against exactly this shape of
            # unchecked split and this was not. A console that can tell it has
            # nonsense should say so here, where the person who typed it is looking,
            # rather than spending a round trip to be told by a machine with an
            # animal in a chair on it.
            if not sep or not name:
                print(
                    f"refused: --set {assignment!r} is not NAME=VALUE -- a parameter "
                    f"name is required before the '='",
                    file=sys.stderr,
                )
                return 1
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
            # `send()` is inside this same `try` -- fix round 1, IMPORTANT 1: a
            # second `send()` reads the *previous* command's reply first
            # (`ZmqConsole.send`'s own docstring) and raises `TimeoutError`,
            # exactly like `receive()`, if a gone or too-slow session never
            # answers. `--set X --stop` -- this subcommand's own advertised
            # usage two paragraphs up -- sends two commands, so a raw traceback
            # from an uncaught `send()` was not a hypothetical: nothing before
            # this exercised a second command, because every earlier test sent
            # at most one.
            try:
                for command in commands:
                    console.send(command)
                # Watches until the session says it has stopped, or the
                # operator interrupts -- "the console prints frames as trials
                # run" is a live view, not a one-shot query. `stopped_because`
                # is the session's own last word (`taskd.Session.run`'s
                # `publish()` fires it on every stop path), so waiting for it
                # rather than for `receive()` to time out is what lets this
                # exit on a natural end instead of after 5 idle seconds.
                while True:
                    frame = console.receive()
                    print(render(frame))
                    print()
                    if frame.stopped_because:
                        break
            except KeyboardInterrupt:
                # Final-review minor: this used to fall through to `return 0`, so a
                # watch somebody walked away from and an operator who saw the
                # session stop cleanly left the same trace. 130 is the shell's own
                # convention for SIGINT (128 + 2), so a wrapper that only reads the
                # exit code can still tell them apart -- and the line says which,
                # for a person reading a terminal rather than a status.
                print(
                    "console: interrupted -- the session is still running; "
                    "nothing here stops it (use --stop for that)",
                    file=sys.stderr,
                )
                return 130
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
