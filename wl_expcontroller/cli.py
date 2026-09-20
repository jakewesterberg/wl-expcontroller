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
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from wl_expcontroller import link as _link
from wl_expcontroller import record as _record
from wl_expcontroller.bounds import Bounds, Exceeded
from wl_expcontroller.check import check
from wl_expcontroller.review import render as render_review
from wl_expcontroller.codes import PROVISIONAL, Allocation
from wl_expcontroller.task import Trial
from wl_expcontroller.welfare import Deployment


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


#: What `--out-of-cage-at` accepts, named once so the flag's help, its refusal and
#: this module's tests all quote the same list.
_TIME_FORMATS = "HH:MM, HH:MM:SS, or an ISO 8601 date-time such as 2027-01-13T22:40"


def _wall_clock_time(text: str) -> float:
    """An operator's clock time to POSIX seconds. `argparse`'s `type=` for the mark.

    **Two resolutions are stated here rather than left implicit**, because the PI
    asked for both to be decided (2026-09-20):

    - **Timezone: this host's local zone.** A value with no offset is read in the
      zone the lab machine is configured for, which is the clock on the wall the
      operator is reading. A value that carries its own offset is honoured as given.
    - **Date: today, on this host, and never rolled back.** A bare `HH:MM` later than
      now is refused as being in the future rather than quietly becoming a departure
      twenty-three hours ago. An overnight departure is typed with its date.
    - **The two daylight-saving hours, both resolved and neither silent.** Measured
      on a CET/CEST host, 2026-09-20: an **ambiguous** local time -- the repeated
      hour when clocks go back -- takes the *first* occurrence, which `astimezone()`
      gives by leaving `fold` at 0 (`2026-10-25T02:30` resolves to `+02:00`). A
      **nonexistent** one -- the skipped hour when clocks go forward -- is moved
      *forward*: `2026-03-29T02:30` resolves to `03:30+02:00`. The directions differ
      and so does what they cost. The ambiguous case takes the earlier instant, so
      the interval comes out up to an hour **longer** than meant, which is the safe
      direction for a ceiling. **The nonexistent case is the unsafe one**: the
      departure is read up to an hour later than meant, so the animal is reported as
      having been out up to an hour *less* than it has. Once a year, on one hour, in
      one direction -- and the interval printed at session start is what surfaces it,
      since an operator who typed a real time then reads a figure an hour short of
      the wall clock.

      **Closed by the PI on 2026-09-20 -- closed, not fixed.** *"the dst switches
      happen in the night, when no experiments occur."* So the skipped hour cannot be
      typed as a departure, and the arithmetic above is left exactly as it is rather
      than special-cased for a value nothing can produce.

      **The description above stays because the dismissal is conditional on that
      fact and not on the arithmetic.** If night sessions ever start -- an overnight
      protocol, a cage-side kiosk running unattended (S13) -- the hour comes back
      with them, and whoever reads this then needs to find what would happen rather
      than a note saying it was considered and closed. `2026-03-29T02:30` still
      resolves to `03:30+02:00`, and that still reports an animal as out up to an
      hour less than it has been.

    Rolling back would have been the convenient choice and is the wrong one: it turns
    `23:59` mistyped in the morning into an animal recorded as out for most of a day,
    which is precisely the plausible-typo class this flag's refusals exist for.

    Returning a POSIX float, not a `datetime`: `welfare.left_cage` is the one place
    the wall clock and the session clock meet, and handing it a rich object would put
    calendar arithmetic inside a welfare-critical file.
    """
    raw = text.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            clock = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        today = datetime.now()
        parsed = today.replace(
            hour=clock.hour, minute=clock.minute, second=clock.second, microsecond=0
        )
        break
    else:
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"{text!r} is not a clock time; give {_TIME_FORMATS}. A bare time is "
                f"today's date in this host's local timezone"
            ) from None
    if parsed.tzinfo is None:
        # Attaches this host's local offset for the instant in question, which is
        # what makes "local" a resolution rather than an assumption.
        parsed = parsed.astimezone()
    return parsed.timestamp()


def _hours_minutes(seconds: float) -> str:
    """`seconds` as `N hours M minutes` -- the phrasing the PI asked for.

    Separate from `_clock` and deliberately wordier than it: `_clock`'s `9:15:00`
    is for a figure an operator glances at repeatedly on a running console, and this
    is for the one sentence that has to be *read* once, at session start, so that a
    nine-hour typo registers as nine hours.
    """
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    return (
        f"{hours} hour{'' if hours == 1 else 's'} "
        f"{minutes} minute{'' if minutes == 1 else 's'}"
    )


def _at_a_terminal() -> bool:
    """Whether there is a person on the other end of `stdin`.

    **`sys.stdin` can be `None`, and that is not the same as a non-tty.** With file
    descriptor 0 closed -- a daemon, a service manager, a `subprocess` given
    `stdin=None` on a detached parent -- Python leaves `sys.stdin` as `None`, and
    `sys.stdin.isatty()` then raises `AttributeError` rather than answering `False`.
    Found by review probing the non-interactive path with a pipe, a here-doc,
    `/dev/null`, `yes c |`, a closed fd 0 and a real pty: only the closed one got
    through, and it got through as a traceback that also defeated
    `--confirm-out-of-cage`, the documented way to run this headless.

    One function rather than the expression twice, because the two call sites have to
    agree: one decides whether to prompt, and the other labels the recorded row.
    """
    return sys.stdin is not None and sys.stdin.isatty()


def _ask(prompt: str) -> str:
    """One line from the person at the terminal, or `""` if there is none.

    A function rather than a bare `input()` so that end-of-input is a *quiet*
    non-answer rather than a traceback: a pipe that closes mid-prompt must land on
    the same path as a person typing nothing, and that path refuses.
    """
    try:
        return input(prompt)
    except EOFError:
        return ""


def _settle_departure(session, args) -> tuple:
    """Get a person's act on a far-off departure time, before it is marked.

    **PI, 2026-09-20:** *"if a number is input that is more than 30 min from the
    current time, a warning should appear that the experimenter must click through to
    confirm. There should also be an option to update the time if necessary, but a
    reason should be given and the experimenter name logged."*

    Returns `(departure, note)` -- the instant to mark with, and the row to write
    once the mark is accepted, or `None` when nothing was asked. **The row is the
    caller's to write and only after `left_cage` has taken the value**, so an
    amendment refused by the ceiling or for being in the future leaves no record of a
    change that did not happen.

    **What each case does, and the non-interactive one is the decision.**

    - *Inside the band* (`welfare.departure_needs_confirmation` answers `None`): the
      ordinary session, which asks nothing and writes nothing. A prompt on every
      session is a prompt clicked past on every session.
    - *Amended*: `--amend-out-of-cage-to TIME` with `--amend-reason` and `--as`, or
      the same three typed at the prompt. **An amendment is its own confirmation** --
      a named person giving a reason has done strictly more than click through -- but
      it is not an override: the amended value goes to `left_cage` and meets every
      refusal the original would have.
    - *Interactive*: `stdin` is a terminal, so it asks, and **anything that is not a
      confirmation stops the session**, end-of-input included. A prompt whose default
      is "proceed" is the silent path wearing a question mark.
    - *Non-interactive*: **it refuses.** `wlx run` may have no terminal behind it -- a
      wrapper, a scheduler, the `labhost` process P4d-2 adds -- and proceeding there
      would write a confirmation nobody made, which is worse than no confirmation at
      all. `--confirm-out-of-cage` is the honest way to say it out loud, and the row
      records that it came from a flag rather than from a person, because a wrapper
      with it baked in is how this ruling would otherwise be defeated in silence.

    **A confirmation's `by` is `--as` if it was given and empty otherwise, and that is
    not an oversight.** The PI asked for a name on the *amendment*, where
    `welfare.amend_mark` requires one; a confirmation is a person clicking through,
    and an interactive `c` has no name to record honestly. `how` is what carries the
    information a reader actually needs — whether a person or a flag answered.
    """
    at = args.out_of_cage_at
    warning = session.departure_needs_confirmation(at)

    def note(kind: str, now: float, reason: str, by: str, how: str) -> dict:
        return {
            "kind": kind,
            "subject": args.subject,
            "was": at,
            "now": now,
            "reason": reason,
            "by": by,
            "how": how,
            "recorded_at": time.time(),
        }

    if args.amend_out_of_cage_to is not None:
        amended = args.amend_out_of_cage_to
        # Refuses a blank reason or a blank actor, in `welfare`, so the console
        # action P4d-2 adds cannot reach the record around this rule.
        session.amend_mark(
            "departure",
            original=at,
            amended=amended,
            reason=args.amend_reason,
            by=args.actor,
        )
        return amended, note(
            "departure amended",
            amended,
            args.amend_reason,
            args.actor,
            "--amend-out-of-cage-to",
        )

    if warning is None:
        return at, None

    if args.confirm_out_of_cage:
        print(f"  WARNING: {warning}", file=sys.stderr)
        return at, note(
            "departure confirmed",
            at,
            "",
            args.actor,
            "--confirm-out-of-cage"
            if _at_a_terminal()
            else "--confirm-out-of-cage, with no terminal attached",
        )

    if not _at_a_terminal():
        raise SystemExit(
            f"refused: {warning}\n"
            f"  There is no terminal attached, so there is nobody to confirm it and "
            f"a confirmation nobody made is worse than none. Pass "
            f"--confirm-out-of-cage to confirm it explicitly, or "
            f"--amend-out-of-cage-to TIME --amend-reason WHY --as WHO to correct it."
        )

    print(f"  WARNING: {warning}", file=sys.stderr)
    # **Exact words, not a prefix.** This matched `a`-anything as *amend*, so
    # `abort` typed at a prompt that ends "anything else to stop" walked into the
    # amendment flow and was then parsed as a clock time. It still refused, but a
    # prompt that lies about what a word does is learned once and remembered wrong.
    answer = _ask(
        "  type `confirm` to accept this departure time, `amend` to correct it, "
        "or anything else to stop: "
    ).strip().lower()

    if answer in ("a", "amend"):
        amended = _ask(f"  the corrected departure time ({_TIME_FORMATS}): ").strip()
        try:
            amended_at = _wall_clock_time(amended)
        except argparse.ArgumentTypeError as bad:
            raise SystemExit(f"refused: {bad}") from bad
        reason = _ask("  why is it being changed? ")
        by = _ask("  your name, for the record: ")
        session.amend_mark(
            "departure", original=at, amended=amended_at, reason=reason, by=by
        )
        return amended_at, note(
            "departure amended", amended_at, reason, by, "amended at the terminal"
        )

    if answer in ("c", "confirm"):
        return at, note(
            "departure confirmed", at, "", args.actor, "confirmed at the terminal"
        )

    raise SystemExit(
        "refused: the departure time was not confirmed, so the session did not "
        "start. Nothing has been recorded and nothing was delivered."
    )


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

    **An absent number says which absence it is, and never prints as zero.**
    `chair_seconds` is `None` for the two deployment kinds that take no
    head-fixation marks (PI, 2026-09-20), and the two have different reasons: a
    cage-side animal is never restrained, and a chaired one is restrained and
    unmarked. Rendering either as `0:00` would report a measurement nothing took,
    which on the restraint clock is the same failure `fluid today: UNKNOWN` exists
    to prevent on the fluid one. `deployment` is on the frame so this line can name
    the reason rather than infer it from which fields came through empty.

    **The two fluid lines are the condition of a welfare ruling, not a readout.**
    A reward volume of zero is *allowed* -- pausing reward without ending a session
    -- and the PI allowed it on 2026-09-20 **because it is visible**: `fluid
    session: 0.00 mL` is how an operator sees that a correctly-working animal is
    being paid nothing, and `supplement:` keeps reporting the whole floor as owed so
    it is topped up afterwards. **A change that stopped showing either would turn a
    permitted operation into a silent one** -- a welfare regression reached by
    simplifying a console pane, which is exactly why this sentence is here and not
    only in S8 §5.2c.

    **And a session at `0.00 mL` may be working as designed** (PI, 2026-09-20): a
    trial may have a reward period paying an on-screen *token* rather than fluid,
    converting to fluid later. So this line is not a fault indicator, and `supplement`
    is what still says what the animal is owed. Nothing in the task vocabulary models
    that token yet -- S8 §5.3.

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
    # Named rather than derived. Two of the three kinds answer `None` for chair time
    # for different reasons, and a console that worked out which from the pattern of
    # `None`s would be computing -- see this function's second paragraph.
    lines.append(f"  deployment: {frame.deployment}")
    if frame.stopped_because:
        lines.append(f"  STOPPED: {frame.stopped_because}")
    # Beside the stop reason and above everything else, because that is where a
    # person looks when something is wrong. The session's own sentence, read from
    # `welfare.approaching_limit` and not rebuilt here (PI, 2026-09-20).
    if frame.duration_warning:
        lines.append(f"  WARNING: {frame.duration_warning}")

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
    # **Absent is not zero, and the two absences are not each other** (PI,
    # 2026-09-20). `chair: 0:00` on a chaired-but-unfixed session would tell an
    # operator a restrained animal had been restrained for no time at all -- a
    # welfare quantity reported as a measured zero by something that measured
    # nothing, which is `shortfall()` answering `0` for an unmeasured day in another
    # costume. So the word UNMEASURED appears, and the cage-side case gets its own
    # sentence because "never restrained" and "restrained and unmarked" are
    # different facts about an animal.
    if frame.chair_seconds is not None:
        lines.append(f"  chair: {_clock(frame.chair_seconds)}")
    elif frame.deployment == Deployment.CAGE_SIDE.value:
        lines.append("  chair: n/a -- cage-side, the animal is home and unrestrained")
    else:
        lines.append(
            "  chair: n/a -- this deployment takes no head-fixation marks, so "
            "restraint is UNMEASURED here, not zero; the animal is in a chair"
        )

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
        "--out-of-cage-at",
        type=_wall_clock_time,
        required=True,
        metavar="TIME",
        help=f"the clock time this subject came out of its home cage: {_TIME_FORMATS}. "
        "A bare time is TODAY's date in THIS HOST's local timezone, never yesterday's "
        "-- give the date too for an overnight departure. **Required, with no "
        "default**, for the reason `--as WHO` is: the session's one welfare limit "
        "runs out of cage to back in cage (S8 5.2), and a default would make it equal "
        "chair time, which is the under-count that limit replaced chair time to "
        "remove. Refused if it is in the future or longer ago than the subject's "
        "out_of_cage ceiling. The session prints the resulting interval as it starts, "
        "because a plausible typo -- 08:45 for 18:45 -- is inside a twelve-hour "
        "ceiling and nothing else would catch it",
    )
    runner.add_argument(
        "--confirm-out-of-cage",
        action="store_true",
        help="confirm, without being asked, a departure more than "
        "welfare.CONFIRM_MARK_WITHIN (1800 s) before now. **The honest "
        "non-interactive path** (PI, 2026-09-20): with no terminal attached there is "
        "nobody to click through the warning, and a run that proceeded anyway would "
        "record a confirmation nobody made, which is worse than none. It is written "
        "into welfare_notes.jsonl as having come from this flag rather than from a "
        "person, so a wrapper with it baked in is visible months later. Ignored when "
        "the departure is recent enough to need no confirmation. **No config that "
        "ships with this repository can reach the band at all**: "
        "tasks/reference_bounds.py's out_of_cage ceiling is a deliberately "
        "implausible ten minutes, shorter than the threshold, so a far departure is "
        "refused by the ceiling before a confirmation is ever offered -- "
        "tasks/twelve_hour_bounds.py is a second reference config, with the real "
        "institutional figure, that this path can be dry-run against",
    )
    runner.add_argument(
        "--amend-out-of-cage-to",
        type=_wall_clock_time,
        default=None,
        metavar="TIME",
        help="replace --out-of-cage-at with this time, recording the change. "
        "Requires --amend-reason and --as, both with no default (PI, 2026-09-20: a "
        "reason is given and the experimenter name logged). The amended value meets "
        "every refusal the original would -- it is a correction, not an override",
    )
    runner.add_argument(
        "--amend-reason",
        default="",
        metavar="WHY",
        help="why the departure time is being amended. Required by "
        "--amend-out-of-cage-to; a blank one is refused rather than recorded, "
        "because a row saying a welfare clock moved and not why answers nothing",
    )
    runner.add_argument(
        "--as",
        dest="actor",
        default="",
        metavar="WHO",
        help="the experimenter amending the departure time. Required by "
        "--amend-out-of-cage-to, for the reason `wlx console --as` is required by a "
        "write: an anonymous change to the clock a session is bounded by is worse "
        "than none",
    )
    runner.add_argument(
        "--deployment",
        choices=("rig-fixed", "rig-chaired"),
        default="rig-fixed",
        help="which kind of session this is (welfare.Deployment). `rig-fixed` is the "
        "animal chaired and head-fixed; `rig-chaired` is chaired and unfixed, which "
        "takes no head-fixation marks and therefore reports restraint time as ABSENT "
        "rather than as zero. Both are bounded by the same out-of-cage clock. "
        "Defaulted -- unlike --out-of-cage-at -- because omission lands on the "
        "stricter kind, which requires a mark the other does not. `cage-side` is not "
        "offered: there is no kiosk host to run one on (S13 §6 item 2), and a "
        "cage-side bounded config would be refused by this one anyway",
    )
    runner.add_argument(
        "--warn-within",
        type=float,
        default=None,
        metavar="SECONDS",
        help="how close to the out-of-cage ceiling the session starts warning (PI, "
        "2026-09-20), so a block can be finished deliberately rather than cut "
        "mid-sequence. Omitted uses welfare.WARN_WITHIN_DEFAULT, which is 1800 -- the "
        "PI's own starting value, accepted 2026-09-20, and still derived from no "
        "measurement of this system. Zero switches the warning off",
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
        from wl_expcontroller.welfare import (
            WARN_WITHIN_DEFAULT,
            Simulated as SimulatedPump,
        )

        # `--deployment` arrives as a hyphenated word because that is how a flag
        # reads; the enum's own value is the underscored one that goes on the wire.
        deployment = Deployment(args.deployment.replace("-", "_"))

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
            # **Every welfare refusal on this path is a message, not a traceback.**
            # `--out-of-cage-ago` was wrapped and `--delivered-today` was not, so
            # the same bad value on two flags of the same subcommand gave a
            # sentence on one and a stack trace on the other. S9's "written for a
            # stranger" rule is about exactly that. The whole construction is
            # inside the guard because the refusal can come from any of three
            # places -- `Welfare.__post_init__` on the day's total, `Bounds`
            # rejecting a config's limit, or the subject mismatch -- and a person
            # reading the message does not care which.
            try:
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
                        # A simulated rig run, so the rig's limits apply -- which of
                        # the two rig kinds is `--deployment`'s to say since
                        # 2026-09-20 (PI). There is still no flag for the cage-side
                        # deployment because there is no kiosk to run one on: S13 is
                        # a proposed spec, and `wl-touchtrain` owns the hardware
                        # (S13 §6 item 2).
                        deployment=deployment,
                        warn_within=(
                            WARN_WITHIN_DEFAULT
                            if args.warn_within is None
                            else args.warn_within
                        ),
                    ),
                    # Simulators, because that is what this subcommand is for.
                    # The refusing implementations are the defaults everywhere
                    # else, and a headless run that silently used a real card
                    # would be the worse surprise.
                    card=SimulatedCard(),
                    pump=SimulatedPump(),
                    **session_kwargs,
                )
                # On a rig both of these are the console's actions, and the
                # difference is the whole reason S8 makes them explicit. Here the
                # out-of-cage one comes from `--out-of-cage-at`, which has no
                # default: a headless run states the departure as a clock time and
                # means it, rather than arriving at the session's own zero by
                # omission and quietly reporting chair time as time out of the cage.
                # Head-fixation lands at the session's own zero -- and only for the
                # kind that has it, since `welfare.head_fixed` refuses the other.
                # **A departure far from now is a person's to confirm or amend**
                # (PI, 2026-09-20), and that happens before the mark: `left_cage`
                # refuses a second one, so an amendment made afterwards would have
                # nowhere to go. The row is written after the mark is accepted, so a
                # "correction" the ceiling refuses leaves no record of a change that
                # did not happen.
                departure, note = _settle_departure(session, args)
                # `confirmed` is true exactly when a person acted -- an
                # amendment is its own confirmation, since a named person giving
                # a reason has done strictly more than click through.
                # `welfare.left_cage` refuses a far mark without it, so the
                # console P4d-2 adds cannot reach around this prompt.
                session.left_cage(at=departure, confirmed=note is not None)
                if note is not None:
                    _record.welfare_note(session.directory, **note)
                if deployment is Deployment.RIG_FIXED:
                    session.head_fixed(at=0.0)
            except Exceeded as refused:
                raise SystemExit(f"refused: {refused}") from refused
            # **The consequence of a clock time, made visible** (PI, 2026-09-20).
            # He accepted losing the automatic wall-clock refusal on the condition
            # that a mistyped hour is legible rather than silent: `08:45` for
            # `18:45` sits comfortably inside a twelve-hour ceiling, and nothing
            # else on this path would remark on it. Read from `welfare`, never
            # recomputed here -- `render`'s rule, on the headless path.
            #
            # **`departure`, not `args.out_of_cage_at`**: an amended time is what
            # the session is bounded by, so it is what this line must show. Printing
            # the value the operator first typed would have this sentence describe a
            # clock nothing is running.
            print(
                f"  out of cage: the animal has been out "
                f"{_hours_minutes(session.welfare.out_of_cage_seconds(session.now()))}"
                f", having left its cage at "
                f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(departure))}"
                # The zone **at the departure**, not at now. A session started just
                # after a daylight-saving change would otherwise label a departure
                # made before it with the zone that is current now -- and that is
                # precisely the one hour a year when the label carries information.
                f" ({time.strftime('%Z', time.localtime(departure))}"
                f", this host's local time)"
            )
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
