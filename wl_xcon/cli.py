"""`wlx` — the command line.

`wlx check` is the reason this exists. The load-time checks were reachable only
from tests, which meant the guardrail that refuses a malformed task could not
actually be run against one by a person, in CI, or by whatever tool eventually
loads tasks on a rig. A check nobody can invoke is a test, not a guardrail.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import threading
import time
import unicodedata
from contextlib import nullcontext
from pathlib import Path

from wl_xcon import link as _link
from wl_xcon import marks as _marks
from wl_xcon.marks import TIME_FORMATS as _TIME_FORMATS
from wl_xcon.marks import clock_or_now as _clock_or_now
from wl_xcon.marks import clock_time as _wall_clock_time
from wl_xcon.bounds import Bounds, Exceeded
from wl_xcon.check import check
from wl_xcon.review import render as render_review
from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.geometry import VIEWS, Geometry, Rig, SubjectSettings
from wl_xcon.task import Trial
from wl_xcon.welfare import Deployment


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


def _load_named(path: Path, name: str) -> object:
    """Import a settings file and return what it defines as `name`, or `None`. A
    settings object refuses bad values when it is built, which happens inside the
    file, so a `ValueError` from running it is said as a refusal sentence rather than
    left as a traceback. So is a `TypeError`: a file written before a field existed
    fails as a missing argument."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ValueError, TypeError) as refused:
        raise SystemExit(f"refused: {path}: {refused}") from refused
    return vars(module).get(name)


def _load_rig(path: Path) -> Rig:
    """Load a rig's display settings (direct-view spec §2): a Python file defining
    `RIG`, as `tasks/rig.py` does. Refused when it defines none, as a bounded config
    without `BOUNDS` is: a check against no field is a check that did not run."""
    found = _load_named(path, "RIG")
    if not isinstance(found, Rig):
        raise SystemExit(f"{path} must define RIG, a geometry.Rig")
    return found


def _load_subject_settings(path: Path, subject: str | None) -> SubjectSettings:
    """Load one animal's settings (PI, 2026-09-29): a Python file defining `SETTINGS`.
    **Refused for another animal**, as a bounded config is, when `subject` is given:
    one animal's eye spacing is not another's."""
    found = _load_named(path, "SETTINGS")
    if not isinstance(found, SubjectSettings):
        raise SystemExit(f"{path} must define SETTINGS, a geometry.SubjectSettings")
    if subject is not None and found.subject != subject:
        raise SystemExit(
            f"refused: {path} holds {found.subject!r}'s settings and this session is "
            f"for {subject!r}; one animal's eye spacing is not another's"
        )
    return found


#: Said by `wlx run` and `wlx check` alike, so the two cannot drift apart.
_DIRECT_READS_NO_SETTINGS = (
    "refused: --subject-settings holds the stereoscope's half-IPD, and direct view "
    "reads nothing from it; leave it off, or pass --view stereoscope"
)


def _setup_words(view: object, half_ipd_cm: object) -> str:
    """A setup in words, for `wlx check`, the terminal console and the page. Takes
    wire values, so anything that is not a finite number is said, not formatted
    (Review Focus 4)."""
    if view == "direct":
        return "direct view"
    if view != "stereoscope":
        return f"an unknown setup ({_printable(str(view))})"
    if half_ipd_cm is None:
        return "the stereoscope, half-IPD not given"
    # `bool` is an `int`, so a wire `true` would otherwise print as "1.00 cm".
    if (
        isinstance(half_ipd_cm, bool)
        or not isinstance(half_ipd_cm, (int, float))
        or not math.isfinite(half_ipd_cm)
    ):
        return "the stereoscope, half-IPD unreadable"
    return f"the stereoscope, half-IPD {half_ipd_cm:.2f} cm"


def _setups(
    trial: Trial, rig: Rig, view: str | None, settings: SubjectSettings | None
) -> list[Geometry]:
    """The fields `wlx check` holds a task to (direct-view spec §8): the setup named, or
    every setup the task allows. Through the stereoscope, one animal's field when its
    settings are given, and otherwise the fields at **both ends** of the half-IPDs the
    rig is built for, so a task that passes, passes for every animal it could run on.
    A task whose `view` is unrecognized gets none, and `check` refuses it by name."""
    views = (
        [view]
        if view is not None
        else {
            "direct": ["direct"],
            "stereoscope": ["stereoscope"],
            "either": ["direct", "stereoscope"],
        }.get(trial.view, [])
    )
    halves = [settings.half_ipd_cm] if settings else list(rig.half_ipd_range_cm)
    geometries: list[Geometry] = []
    for name in views:
        try:
            geometries.extend(
                [rig.direct()]
                if name == "direct"
                else [rig.stereoscope(half) for half in halves]
            )
        except ValueError as refused:
            sentence = f"refused: {refused}"
            if name == "direct" and view is None and len(views) > 1:
                # Failing closed is right; but the other setup can still be checked.
                sentence += (
                    "; the task is also written for the stereoscope, and --view "
                    "stereoscope checks that setup"
                )
            raise SystemExit(sentence) from refused
    return geometries


def _session_geometry(args) -> Geometry:
    """The field a `wlx run` session is held to, from `--rig`, `--view` and
    `--subject-settings` (direct-view spec §3; PI, 2026-09-29). Every refusal is a
    sentence: an unmeasured rig, an animal the stereoscope is not built for, another
    animal's file, or a file where none belongs."""
    rig = _load_rig(args.rig)
    if args.view == "direct":
        if args.subject_settings is not None:
            raise SystemExit(_DIRECT_READS_NO_SETTINGS)
        build = rig.direct
    else:
        if args.subject_settings is None:
            raise SystemExit(
                "refused: --view stereoscope needs --subject-settings, the file "
                "holding this animal's half-IPD (PI, 2026-09-29)"
            )
        half = _load_subject_settings(args.subject_settings, args.subject).half_ipd_cm

        def build() -> Geometry:
            return rig.stereoscope(half)

    try:
        return build()
    except ValueError as refused:
        raise SystemExit(f"refused: {refused}") from refused


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


def _time_of_day(at: float) -> str | None:
    """A frame's instant as this host's local clock time, `HH:MM:SS`, or `None` when
    there is none to show: not a number, or finite and too far out for
    `time.localtime`, which raises `OverflowError`, `OSError` or `ValueError` for it,
    by platform and by how far (the b2a final review). A frame's field that cannot be
    shown is said to be unknown by `render`, never a crash of the screen."""
    if not math.isfinite(at):
        return None
    try:
        return time.strftime("%H:%M:%S", time.localtime(at))
    except (OverflowError, OSError, ValueError):
        return None


def _hours_minutes(seconds: float) -> str:
    """`seconds` as `N hours M minutes` -- the phrasing the PI asked for.

    Separate from `_clock` and deliberately wordier than it: `_clock`'s `9:15:00`
    is for a figure an operator glances at repeatedly on a running console, and this
    is for the one sentence that has to be *read* once, at session start, so that a
    three-hour typo registers as three hours.
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


def _settle_departure(session, args) -> _marks.Departure:
    """Get a person's act on a far-off departure time, before it is marked.

    **Welfare-critical, outside the welfare modules** (`docs/design/architecture.md`):
    the terminal's route into `marks.decide_departure`, which decides -- the same
    function `wlx taskd`'s page goes through (P4d-2b spec §6.2). What stays here is the
    terminal's part: which answer the person gave, and the name and reason an
    amendment carries.

    **PI, 2026-09-20:** *"if a number is input that is more than 30 min from the current
    time, a warning should appear that the experimenter must click through to confirm.
    There should also be an option to update the time if necessary, but a reason should
    be given and the experimenter name logged."*

    - *Amended*: `--amend-out-of-cage-to TIME` with `--amend-reason` and `--as`, asked
      of `marks` before anything else, as it always was.
    - *Inside the band*: `marks` asks nothing; the ordinary session.
    - *Far*: `--confirm-out-of-cage` confirms it, saying whether a terminal was there;
      with no terminal and no flag **it refuses** -- a confirmation nobody made is
      worse than none; at a terminal it asks, and **anything that is not a
      confirmation stops the session**, end-of-input included.

    **A confirmation's `by` is `--as` if it was given and empty otherwise**: the PI asked
    for a name on the amendment, and an interactive `c` has none to record honestly.
    `how` is what carries what a reader of the welfare record needs -- whether a person
    or a flag answered -- since a wrapper with the flag baked in is how this ruling
    would otherwise be defeated in silence.
    """
    at = args.out_of_cage_at
    given = {"by": args.actor, "how": "--out-of-cage-at"}
    if args.amend_out_of_cage_to is not None:
        return _marks.decide_departure(
            session,
            at,
            _marks.Amend(
                at=args.amend_out_of_cage_to,
                reason=args.amend_reason,
                by=args.actor,
                how="--amend-out-of-cage-to",
            ),
            **given,
        )
    try:
        return _marks.decide_departure(session, at, None, **given)
    except _marks.Owed as owed:
        warning = owed.warning

    if args.confirm_out_of_cage:
        print(f"  WARNING: {warning}", file=sys.stderr)
        how = (
            "--confirm-out-of-cage"
            if _at_a_terminal()
            else "--confirm-out-of-cage, with no terminal attached"
        )
        return _marks.decide_departure(
            session, at, _marks.Confirm(by=args.actor, how=how), **given
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
    # **Exact words, not a prefix.** This matched `a`-anything as *amend*, so `abort`
    # typed at a prompt that ends "anything else to stop" walked into the amendment
    # flow and was then parsed as a clock time.
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
        return _marks.decide_departure(
            session,
            at,
            _marks.Amend(at=amended_at, reason=reason, by=by, how="amended at the terminal"),
            **given,
        )

    if answer in ("c", "confirm"):
        return _marks.decide_departure(
            session,
            at,
            _marks.Confirm(by=args.actor, how="confirmed at the terminal"),
            **given,
        )

    raise SystemExit(
        "refused: the departure time was not confirmed, so the session did not "
        "start. Nothing about the departure has been recorded, and nothing was "
        "delivered."
    )


#: The return prompt's words, in one place (final review I3). **It asks for the
#: *home* cage**, so it is answered once the animal is in it; it read "returned to
#: cage at", which a person could answer with the animal still in the chair beside
#: the rig -- and a `now` typed then undercounts the interval.
_RETURN_PROMPT = "  returned to its home cage at (HH:MM, or now): "


def _local(at: float) -> str:
    """A wall instant as this host's local date, minute and zone -- `YYYY-MM-DD HH:MM
    (ZONE)`. The zone **at that instant**, not now, for the reason the departure's
    line gives: across a daylight-saving change the label is the information."""
    moment = time.localtime(at)
    return f"{time.strftime('%Y-%m-%d %H:%M', moment)} ({time.strftime('%Z', moment)})"


def _settle_return(session, actor: str, attempts: int = 3) -> str | None:
    """Ask the person at the terminal when the animal went back into its cage.

    **Welfare-critical, outside the two welfare modules** (P4d-2a final review I5,
    `docs/design/architecture.md`): it decides which instant closes the out-of-cage
    interval and whether a far one was confirmed by a person.

    **P4d-2a spec §5, amended by §10.** `None` once the return is recorded here,
    and otherwise the reason it was not, for the row. **The rules are
    `marks.take_return`'s**, which `wlx taskd`'s page goes through too (P4d-2b spec
    §6.2): this function holds only the prompting -- the clock above each attempt, the
    time typed, and a person's `confirm` on a far one.

    **The prompt ends, in one of two ways, and the reason names which.**
    End-of-input -- a closed stdin -- ends it at once, since nothing further can
    arrive. Otherwise `attempts` answers that are not an accepted mark end it: a
    prompt that re-asked forever would hang any script, and any test, that answers
    with a fixed string. **An empty line is one of those answers** (PI, 2026-09-26:
    "Count it as an attempt"): it ended the prompt until then, so a stray Enter left
    the interval open for good. A far time gets the departure's confirmation (PI,
    2026-09-20); anything but `confirm` there asks for the time again. **There is no
    amendment**, because nothing has been marked yet that one could replace -- a
    corrected time is simply the time entered.
    """
    for _ in range(attempts):
        # **The clock, and the warning when there is one, above every attempt**
        # (final review I3). Without `--link`, `await_return` publishes into
        # nothing, so this is the only place a terminal-only operator reads the
        # post-loop clock -- or learns it has passed the limit. Both from one wall
        # reading, through the session and `welfare`, never computed here.
        #
        # **`_hours_minutes`, not `_clock`** (residual fix round): this duration sits
        # right above a question asking for an `HH:MM` clock time, and `_clock`'s
        # `9:15` is shaped exactly like one -- a person skimming both lines could
        # take the duration for the answer already given. `_hours_minutes`'s "9
        # hours 15 minutes" cannot be mistaken for a clock reading.
        wall_now = session.wall_now()
        so_far = session.welfare.out_of_cage_seconds(wall_now)
        print(
            f"  out of cage: {_hours_minutes(so_far)} so far, until the return is "
            f"marked"
        )
        warning = session.duration_warning(wall_now)
        if warning is not None:
            print(f"  WARNING: {warning}", file=sys.stderr)
        # Not `_ask`, which reads end-of-input as an empty line: here the two differ.
        try:
            raw = input(_RETURN_PROMPT).strip()
        except EOFError:
            return "end of input at the terminal"
        if not raw:
            print(
                "  nothing was typed; give the time the animal went back into its "
                "home cage, or `now`",
                file=sys.stderr,
            )
            continue
        try:
            at = _clock_or_now(raw, session.wall_now)
        except argparse.ArgumentTypeError as bad:
            print(f"  {bad}", file=sys.stderr)
            continue
        # The decision is `marks.take_return`'s, the page's too (P4d-2b spec §6.2);
        # this prompt is the terminal's one part of it: showing a far return and
        # taking a person's `confirm`.
        try:
            _marks.take_return(session, at, confirmed=False, by=actor, how="terminal")
        except _marks.Owed as owed:
            print(f"  WARNING: {owed.warning}", file=sys.stderr)
            answer = _ask(
                "  type `confirm` to accept this return time, or anything else to "
                "give it again: "
            ).strip().lower()
            if answer not in ("c", "confirm"):
                continue
            try:
                _marks.take_return(session, at, confirmed=True, by=actor, how="terminal")
            except Exceeded as refused:
                print(f"  refused: {refused}", file=sys.stderr)
                continue
        except Exceeded as refused:
            print(f"  refused: {refused}", file=sys.stderr)
            continue
        # **The interval the return closed, made visible** (final review I3), as
        # the departure's is at the start: a return typed in the wrong half of the
        # day is then as legible as a departure typed there. Read from `welfare`.
        print(
            f"  out of cage: the animal was out "
            f"{_hours_minutes(session.welfare.out_of_cage_seconds(session.wall_now()))}"
            f", having left its cage at {_local(session.welfare.left_cage_wall_at)}"
            f" and come back to it at {_local(session.welfare.returned_wall_at)}"
            f", this host's local time"
        )
        return None
    return f"{attempts} answers at the terminal, none of them an accepted return time"


def _close_interval(session, args) -> bool:
    """Take the return at the terminal, or record why nobody could (P4d-2a spec §3,
    §5, amended by §10: the wl-works ELN owns the return, and `wlx run`'s terminal
    prompt is the stand-in until it exists).

    **With no terminal, nothing waits, console attached or not** (Task 8). A linked
    run with no terminal has nobody who could ever answer the prompt -- the ELN's
    return does not reach this box through `link.py`, and the browser console this
    slice once planned to build for the purpose was ruled out with it -- so
    `await_return` is not even started; one `return not recorded (no terminal)` row
    is written at once and `wlx run` exits 0.

    **With a terminal**, `await_return` runs on a background thread, publishing the
    clock, while this thread holds the terminal prompt (`_settle_return`). Returns
    `True` if the operator interrupted, so the caller can exit 130 as `wlx console`
    does.

    **A fault on that background thread is captured and re-raised on this one, never
    retried.** `_wait` below catches whatever `await_return` raises so the thread
    does not simply die with it unseen; this function raises it again, once the
    terminal side has settled, for the same reason `await_return`'s own docstring
    refuses to retry it -- `welfare.returned_to_cage` cannot be called a second time
    without being refused by the mark it already accepted.

    **Does not call `session.end()`** (Task 9 fix round 1). It used to, in its own
    `finally`, but that left `session opened` unclosed on every exit from `main`'s
    run command that happens *before* this function is ever called -- a refused or
    interrupted departure prompt, chiefly. `main` now owns `end()` from an outer
    `finally` that wraps this call along with everything before it, so `session
    ended` is still always the last row a run writes (this function's own writes,
    `returned`/`return not recorded`, all land first, `main`'s `finally` runs only
    once this function has returned or raised past it) -- just from one caller
    higher up than before.
    """
    if session.spec.deployment is Deployment.CAGE_SIDE:
        return False
    if not session.phase:
        session.return_not_recorded("the session did not start")
        return False
    if not _at_a_terminal():
        session.return_not_recorded("no terminal")
        return False
    give_up = threading.Event()
    failure: list[BaseException] = []

    def _wait() -> None:
        try:
            session.await_return(give_up)
        except BaseException as exc:
            failure.append(exc)

    waiter = threading.Thread(target=_wait, daemon=True)
    waiter.start()
    why = None
    interrupted = False
    try:
        # **The prompt waits for the post-loop phase to begin, or for its thread to
        # end** (P4d-2a final review I4), **inside this `try`** (residual fix round:
        # this wait used to sit before the `try`, so a second Ctrl-C landing in it
        # escaped uncaught -- past `give_up.set()` and `return_not_recorded` below --
        # leaving no return row and a traceback). `await_return` releases a head
        # that a fault or Ctrl-C left fixed, and only then moves `phase` on; a
        # return answered before that release lands is refused as an animal home
        # while still in the chair. A person does not type that fast, and a test's
        # answer does. Joined in short steps rather than polled, and bounded by the
        # thread: one that fails first ends the wait.
        while session.phase == "running" and waiter.is_alive():
            waiter.join(0.01)
        why = _settle_return(session, args.actor or "")
    except KeyboardInterrupt:
        why = "interrupted at the terminal"
        interrupted = True
    except BaseException as failed:
        # The prompt reads `welfare` above every attempt now (final review I3), and a
        # refusal there is a fault, not an interrupt: the row says which.
        why = f"the return prompt failed: {type(failed).__name__}"
        raise
    finally:
        give_up.set()
        waiter.join()
        if session.welfare.returned_wall_at is None:
            if why is None and failure:
                why = f"the post-loop phase failed: {type(failure[0]).__name__}"
            session.return_not_recorded(why or "interrupted at the terminal")
    if failure:
        raise failure[0]
    return interrupted


def _summary(session, census) -> None:
    """What `wlx run` prints about a session whose loop has ended: its outcomes when
    the loop returned them, why it stopped, and the day's fluid.

    `census` is `None` when the loop did not return one -- Ctrl-C (final review I4)
    -- and then only the lines that do not need it are printed. Every figure is read
    from the session and its `welfare`, never recomputed here (`render`'s rule).
    """
    if census is not None:
        total = sum(census.outcomes.values()) or 1
        for outcome, count in census.outcomes.most_common():
            print(f"  {outcome.value:18} {count:6}  {100 * count / total:5.1f}%")
        print(f"  {'hangs':18} {census.hangs:6}")
    print(f"  ended: {session.stopped_because}")
    print(
        f"  fluid: {session.welfare.commanded:.2f} mL commanded over "
        f"{session.welfare.deliveries} deliveries"
    )
    # The number a person acts on: how much of the day's minimum is still owed, to
    # be supplemented after the session (PI, 2026-09-06). `None` means the day cannot
    # be counted, which is a louder result than any number.
    owed = session.welfare.shortfall()
    print(
        "  supplement: UNKNOWN -- the day's prior total was not supplied, "
        "so nothing can say what is still owed"
        if owed is None
        else f"  supplement: {owed:.2f} mL to reach the day's floor"
    )


def _interrupted(session) -> None:
    """The last line of a run Ctrl-C ended, saying whether the return is recorded."""
    print(
        "run: interrupted -- the return to the cage was not recorded"
        if session.welfare.returned_wall_at is None
        else "run: interrupted -- the session stopped at the terminal, and the return "
        "to the cage is recorded",
        file=sys.stderr,
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


def _shown(value: object) -> str:
    """A parameter's value on the terminal: `unset` for `None`, two decimals for a
    number, like every other figure on this screen, and the text of a categorical
    choice. Formatting, not derivation -- see `_value`."""
    if value is None:
        return "unset"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value)


def _edge(value: float | None) -> str:
    """One end of a declared range: `open` where the task declared none."""
    return "open" if value is None else f"{value:g}"


def _with_unit(text: str, unit: str) -> str:
    return f"{text} {unit}" if unit else text


def _printable(text: str) -> str:
    """A wire-sourced string, made safe for a terminal: every C0/C1 control
    character (Unicode category `Cc` -- ESC, CR, LF, DEL and the C1 controls
    including CSI, U+009B) and every bidirectional override/isolate character
    (U+202A-U+202E, U+2066-U+2069) is replaced with U+FFFD. `link.py`'s `decode`
    checks a wire string's type and length, never its printability; text off the
    wire must not be able to move the cursor, clear the screen or forge a
    `STOPPED:`/`WARNING:` line on the console that is supposed to show them.

    Compared by code point (`ord`), never by embedding the bidi override/isolate
    characters themselves as literals in this file -- the hazard this function
    keeps off the *terminal* has no place in the *source* either.
    """
    return "".join(
        "\ufffd"
        if unicodedata.category(ch) == "Cc"
        or 0x202A <= ord(ch) <= 0x202E
        or 0x2066 <= ord(ch) <= 0x2069
        else ch
        for ch in text
    )


def _moment(at: object) -> str:
    """A wire instant as this host's local date, minute and zone, or `an unknown time`
    for one it cannot show -- never a crash of the screen."""
    try:
        return _local(at)
    except (OverflowError, OSError, ValueError, TypeError):
        return "an unknown time"


def _question_line(question: _link.Question) -> str:
    """The answer a console owes on a far mark, as the page offers it (spec §6.2)."""
    return (
        f"  QUESTION ({_printable(question.mark)}, session "
        f"{_printable(question.session_id)}): {_printable(question.said)} -- answer "
        f"{' or '.join(_printable(answer) for answer in question.answers)}"
    )


def _refusal_lines(refusals: tuple, dropped: int) -> list[str]:
    """The refusal feed's lines, the dropped count above them -- `render`'s own, for a
    session's frame and an idle one alike."""
    if not refusals:
        return ["  refused: none"]
    lines = []
    if dropped:
        lines.append(
            f"  refused: {dropped} earlier refusal(s) NOT SHOWN -- only the most recent "
            f"{len(refusals)} are kept (link.REFUSAL_HISTORY)"
        )
    for refusal in refusals:
        lines.append(
            f"  refused: {_printable(refusal.name)} by {_printable(refusal.by)}: "
            f"{_printable(refusal.why)}"
        )
    return lines


def _render_idle(frame: _link.Idle) -> str:
    """`wlx taskd` with no session open (P4d-2b spec §6.1): any stranded animal first,
    then a question owed, what a session may be opened with, and the refusals."""
    lines = ["no session open  (wlx taskd, idle)"]
    for found in frame.stranded:
        if found.left_at is None:
            lines.append(
                f"  STRANDED: session {_printable(found.session_id)}: its welfare record "
                f"cannot be read; no session opens until it is repaired and its "
                f"animal's return recorded"
            )
        else:
            lines.append(
                f"  STRANDED: {_printable(found.subject)}, session "
                f"{_printable(found.session_id)}, left its cage at {_moment(found.left_at)}, "
                f"this host's local time; its return is not recorded, and no session "
                f"opens until it is resumed or its return recorded; "
                + (
                    "it can be resumed: resume it from the page, or record its return"
                    if found.resumable
                    else f"it cannot be resumed ({_printable(found.why)}): record its return"
                )
            )
    if frame.question is not None:
        lines.append(_question_line(frame.question))
    lines.append(f"  animals: {', '.join(_printable(a) for a in frame.animals) or 'none'}")
    lines.append(
        f"  tasks offered: {', '.join(_printable(t) for t in frame.offered_tasks) or 'none'}"
    )
    lines.extend(_refusal_lines(frame.refusals, frame.refusals_dropped))
    return "\n".join(lines)


def render(frame: _link.Telemetry | _link.Idle) -> str:
    """One screen's worth of a `Telemetry` frame -- S9a §4's panes this slice has
    data for: fluid, chair, trials by outcome, what is still owed, staged changes
    and refusals. `wlx console`'s only view of a running session.

    **`in session` and `phase` (P4d-2a spec §10 item 3).** The in-session clock is
    the PI's second one, apart from out-of-cage and bounding nothing -- it has no
    limit to warn about, unlike the line above it -- and `phase` names where in the
    session's life this frame was taken: `running`, `awaiting return` (a rig
    session's post-loop clock, still open), or `closed` (the return recorded).

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

    **Schema 7 adds the configuration and the limits** (P4d-2b b1): which task,
    allocation and bounded config; fluid today against the day's floor; the
    out-of-cage clock against the ceiling it is stopped on; the instant the last
    reward was commanded, kept once the pump returned; the parameter rows; and the
    last outcomes. Each absence is a word --
    *PROVISIONAL*, *not given*, *none yet*, *unset*, *open* -- never a zero.

    **Schema 8 adds the controls** (P4d-2b b2a): whether the session is paused and
    since when, the scheduled stop and who set it -- in the rig's own words -- and
    the recent control events, each with who sent it, below the staged rows. A capped
    feed says so above its rows, as the refusal feed does. Absences are words again:
    *no*, *none*.

    **Every wire-sourced string is run through `_printable` before it reaches this
    screen** (fix round 1, IMPORTANT). `link.py`'s `decode` checks a string's type
    and length, never its printability, and a box-local peer's mark note, `by`,
    refusal reason or any other free text is echoed here verbatim otherwise. Left
    unescaped, a control character can move the terminal's cursor or clear its
    screen, and an embedded newline can forge a line of this function's own output
    -- including a `STOPPED:` or `WARNING:` line nothing actually raised. Numbers
    this function formats itself, and the lines and labels it composes itself, need
    no such treatment; only text read off `frame` (or an object reached from it)
    does.

    **Schema 10 adds runs and the service** (P4d-2b b3a): the run, whether `wlx taskd`
    holds the session, the pre-flight of the run about to start, and a question owed; an
    `Idle` frame is `_render_idle`'s.
    """
    if isinstance(frame, _link.Idle):
        return _render_idle(frame)
    lines = [
        f"session {_printable(frame.session_id)}  subject {_printable(frame.subject)}  "
        f"trial {frame.trial_index}  "
        f"block {'none yet' if frame.block is None else _printable(frame.block)}",
    ]
    # Named rather than derived. Two of the three kinds answer `None` for chair time
    # for different reasons, and a console that worked out which from the pattern of
    # `None`s would be computing -- see this function's second paragraph.
    lines.append(f"  deployment: {_printable(frame.deployment)}")
    resumed = None if frame.resumed_at is None else _time_of_day(frame.resumed_at)
    if frame.resumed_at is not None:
        lines.append(
            "  resumed after its process stopped, at "
            f"{'an unknown time' if resumed is None else resumed[:5]}"
        )
    # Direct-view spec §3: the setup, shown for the whole session. Words from the
    # frame's own fields, never inferred.
    lines.append(f"  setup: {_setup_words(frame.view, frame.half_ipd_cm)}")
    # P4d-2b spec §3: S9a §3's configuration information. Named, never guessed: an
    # empty allocation is the provisional one (`_load_allocation`), and an empty
    # bounds path means the caller built `Bounds` in code.
    lines.append(
        f"  task: {'no run yet' if frame.task is None else _printable(frame.task)}"
        f"  allocation: {_printable(frame.allocation) or 'PROVISIONAL (none given)'}"
        f"  bounds: {_printable(frame.bounds_config) or 'not given'}"
    )
    # **The PI's second clock, apart from out-of-cage** (P4d-2a spec §10 item 3):
    # "only shown and recorded", never a bound, so it has no WARNING line of its
    # own the way out-of-cage does. `None` before `open()` -- practically never on
    # a live frame, since a session publishes nothing before it has run `open()`
    # itself -- prints `n/a` for the reason every other absent clock here does:
    # `0:00` would say a clock had started that has not.
    lines.append(
        "  in session: n/a -- not yet opened"
        if frame.in_session_seconds is None
        else f"  in session: {_clock(frame.in_session_seconds)}"
    )
    # `running`/`awaiting_return`/`closed` (`taskd.Session.phase`) spelled with a
    # space rather than the internal underscore -- this line is for a person, not
    # a match against the field's own wire spelling.
    lines.append(f"  phase: {_printable(frame.phase).replace('_', ' ')}")
    # Schema 10 (P4d-2b b3a): which run, and whether a service holds the session. The
    # run counts from 1 for a person, as the browser console's strip and header give it
    # (session-levels spec §3); `run_index` counts from 0, as the record's `run` does.
    lines.append("  run: none yet" if frame.run_index is None else f"  run: {frame.run_index + 1}")
    if frame.service:
        lines.append("  runs: opened, run and ended from a console (wlx taskd)")
    if frame.offered_tasks:
        lines.append(
            f"  tasks offered: {', '.join(_printable(t) for t in frame.offered_tasks)}"
        )
    # Schema 8 (P4d-2b b2a). The pause's instant as a clock time on this host, like
    # the last reward's; one this host cannot show is `unknown`, never a crash.
    paused_at = None if frame.paused_at is None else _time_of_day(frame.paused_at)
    if frame.paused_at is None:
        lines.append("  paused: no")
    elif paused_at is None:
        lines.append("  paused: since an unknown time")
    else:
        lines.append(f"  paused: since {paused_at}")
    # The rig's own words for it, never recomposed here from `kind` and `target`.
    lines.append(
        "  scheduled stop: none"
        if frame.scheduled_stop is None
        else f"  scheduled stop: {_printable(frame.scheduled_stop.said)}, set by "
        f"{_printable(frame.scheduled_stop.by)}"
    )
    if frame.stopped_because:
        lines.append(f"  STOPPED: {_printable(frame.stopped_because)}")
    # Beside the stop reason and above everything else, because that is where a
    # person looks when something is wrong. The session's own sentence, read from
    # `welfare.approaching_limit` and not rebuilt here (PI, 2026-09-20).
    if frame.duration_warning:
        lines.append(f"  WARNING: {_printable(frame.duration_warning)}")
    if frame.question is not None:
        lines.append(_question_line(frame.question))

    lines.append(f"  fluid session: {frame.fluid_session_ml:.2f} mL")
    lines.append(
        f"  fluid today: UNKNOWN -- the day's prior total was not supplied "
        f"(floor {frame.floor_ml:.2f} mL)"
        if frame.fluid_today_ml is None
        else f"  fluid today: {frame.fluid_today_ml:.2f} mL of a "
        f"{frame.floor_ml:.2f} mL floor"
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
    if frame.out_of_cage_seconds is None:
        lines.append("  out of cage: n/a -- cage-side, the animal is home")
    elif frame.out_of_cage_limit_s is None:
        lines.append(f"  out of cage: {_clock(frame.out_of_cage_seconds)}")
    else:
        # Against the ceiling's value, the number the session is stopped on (schema 7).
        lines.append(
            f"  out of cage: {_clock(frame.out_of_cage_seconds)} of "
            f"{_clock(frame.out_of_cage_limit_s)}"
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
    by_outcome = ", ".join(
        f"{_printable(name)} {count}" for name, count in frame.outcomes.items()
    )
    lines.append(f"  trials: {by_outcome or 'none yet'}, hangs {frame.hangs}")

    # When the last reward was commanded, kept once the pump returned, as a clock time
    # on this host (P4d-2b spec §4.1). None yet is said, never printed as a time; an
    # instant that is not a number -- `welfare.deliver` stores one rather than refusing
    # it, since it bounds nothing -- is `unknown`, where `time.localtime` raised (m1),
    # and so is a finite one too far out for it (the b2a final review).
    rewarded_at = (
        None if frame.last_reward_at is None else _time_of_day(frame.last_reward_at)
    )
    if frame.last_reward_at is None:
        lines.append("  last reward: none yet")
    elif rewarded_at is None:
        lines.append("  last reward: unknown")
    else:
        lines.append(f"  last reward: at {rewarded_at}")
    for row in frame.params:
        # `name` and `unit` are always text; `value` is a number for most rows but a
        # categorical choice's own text for others (`ParamRow.value: float | str |
        # None`) -- only the string case is wire text `_shown` would otherwise pass
        # through untouched.
        name = _printable(row.name)
        unit = _printable(row.unit)
        value = _printable(row.value) if isinstance(row.value, str) else row.value
        if row.bounded:
            limit = f"(welfare ceiling {_with_unit(_shown(row.high), unit)})"
        elif row.low is None and row.high is None:
            limit = "(no declared range)"
        else:
            limit = (
                f"(range {_edge(row.low)} to "
                f"{_with_unit(_edge(row.high), unit)})"
            )
        lines.append(
            f"  param: {name} {_with_unit(_shown(value), unit)} {limit}"
        )
    lines.append(
        f"  recent (oldest first): "
        f"{' '.join(_printable(outcome) for outcome in frame.recent_outcomes)}"
        if frame.recent_outcomes
        else "  recent: none yet"
    )

    still_owed = ", ".join(
        f"{_printable(name)} {count}" for name, count in frame.owed.items()
    )
    lines.append(f"  still owed: {still_owed or 'none'}")

    if frame.preflight is not None:
        for item in frame.preflight.items:
            lines.append(
                f"  pre-flight ({_printable(frame.preflight.task)}): "
                f"{_printable(item.name)} {_printable(item.result)}: {_printable(item.said)}"
            )
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
                f"  staged: {_printable(change.name)} {_value(change.was)} -> "
                f"{_value(change.now)} by {_printable(change.by)} ({kind})"
            )
    else:
        lines.append("  staged: none")

    # The changes feed's control events (schema 8), oldest first like the refusals
    # below, the count of what fell off the cap before them for the same reason. A
    # mark's stamp has no sender -- it arrives with the note -- and says so by
    # naming none.
    if frame.controls:
        if frame.controls_dropped:
            lines.append(
                f"  control: {frame.controls_dropped} earlier control event(s) NOT "
                f"SHOWN -- only the most recent {len(frame.controls)} are kept "
                f"(link.CONTROL_HISTORY)"
            )
        for control in frame.controls:
            by = _printable(control.by)
            who = f" by {by}" if by else ""
            lines.append(
                f"  control: {_printable(control.kind)}{who}: "
                f"{_printable(control.said)}"
            )
    else:
        lines.append("  controls: none")

    lines.extend(_refusal_lines(frame.refusals, frame.refusals_dropped))

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wlx")
    sub = parser.add_subparsers(dest="command", required=True)
    checker = sub.add_parser("check", help="run the load-time checks on a task file")
    checker.add_argument("task", type=Path)
    checker.add_argument("--allocation", type=Path, default=None)
    checker.add_argument(
        "--rig",
        type=Path,
        required=True,
        metavar="PATH",
        help="the rig's display settings: a Python file defining RIG, as tasks/rig.py "
        "does. Required: check 8 holds a task to the field the rig shows, and a check "
        "with no field is one that did not run",
    )
    checker.add_argument(
        "--view",
        choices=VIEWS,
        default=None,
        help="check against this setup only; omitted, against every setup the task "
        "allows (direct-view spec §8)",
    )
    checker.add_argument(
        "--subject-settings",
        type=Path,
        default=None,
        metavar="PATH",
        help="one animal's settings, a Python file defining SETTINGS: the stereoscope "
        "is then checked at that animal's half-IPD, rather than at both ends of the "
        "rig's range",
    )

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
        "--rig",
        type=Path,
        required=True,
        metavar="PATH",
        help="the rig's display settings: a Python file defining RIG, as tasks/rig.py "
        "does. Required, as --bounds is: the session's field is built from it",
    )
    runner.add_argument(
        "--view",
        choices=VIEWS,
        required=True,
        help="which setup this session runs in. **Required, with no default** "
        "(direct-view spec §3): nothing senses which is in place, so the operator "
        "says, the choice is shown all session, and a task written for the other "
        "setup is refused before anything is recorded",
    )
    runner.add_argument(
        "--subject-settings",
        type=Path,
        default=None,
        metavar="PATH",
        help="this animal's settings: a Python file defining SETTINGS, for --subject "
        "(PI, 2026-09-29). Required with --view stereoscope, for the animal's "
        "half-IPD; refused with --view direct, which reads nothing from it",
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
        "because a plausible typo -- 15:45 for 18:45 -- is inside an eight-hour "
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
        "tasks/eight_hour_bounds.py is a second reference config, with the real "
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
        metavar="PUB,REP[,MARK]",
        help="open a console link on endpoints THIS SESSION binds: first the "
        "PUB endpoint it publishes telemetry on, then the REP endpoint it "
        "receives commands on, and optionally a third, the MARK endpoint an "
        "operator's mark signal arrives on, e.g. "
        "tcp://127.0.0.1:5571,tcp://127.0.0.1:5572,tcp://127.0.0.1:5573. A "
        "console attaches from the other side: `wlx console --sub` takes the "
        "first and `--req` the second, and `wlx serve --link` takes the same "
        "value as given here. Without MARK the session takes no marks. Loopback "
        "only unless --link-allow-remote is also given. Omitted, the session runs "
        "with no console attached -- exactly as it did before this option "
        "existed, and with no transport dependency acquired",
    )
    runner.add_argument(
        "--link-allow-remote",
        action="store_true",
        help="permit --link to bind an endpoint other hosts can reach (0.0.0.0, a "
        "LAN address, a wildcard). Refused by default: the console link has no "
        "authentication yet, so `--as WHO` is whatever the sender typed, and any "
        "host that can reach the REP port can, under an invented name, change a "
        "setting (a reward volume among them), pause and resume the session, give "
        "manual rewards while it is paused, schedule or cancel a stop, or stop it; "
        "any host that can reach the MARK port can put marks on the record. S9a §6 "
        "designs the real thing and it is P4d-3's; this flag does not make a remote "
        "bind safe, only deliberate",
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

    server_parser = sub.add_parser(
        "serve",
        help="serve a running session's browser console, and /health",
    )
    server_parser.add_argument(
        "--link",
        required=True,
        metavar="PUB,REP[,MARK]",
        help="the session's endpoints, exactly as given to `wlx run --link`. "
        "Telemetry is read from the first, commands are sent to the second, and an "
        "operator's mark signal to the third; without the third the page's mark "
        "control is greyed",
    )
    server_parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="NAME",
        help="a name this box is reached by, to answer to (P4d-2b spec §5.3); may be "
        "given more than once. Every request's Host must name this console -- "
        "loopback, this box's own host names and addresses, or a name given here -- "
        "or it is refused with a 421, against DNS rebinding",
    )
    server_parser.add_argument(
        "--http",
        required=True,
        metavar="HOST:PORT",
        help="where to serve the page and /health: 127.0.0.1:8080 for this box only, "
        "or 0.0.0.0:8080 to let the lab network read it (P4d-2b spec §2: reads are "
        "open to the LAN). An IPv4 address or a name",
    )
    server_parser.add_argument(
        "--health-token-file",
        required=True,
        type=Path,
        metavar="PATH",
        help="a file holding the bearer token wl-works sends to GET /health, on one "
        "line. Refused if it is inside this repository: a token there is one `git "
        "add` from public",
    )
    server_parser.add_argument(
        "--stale-after",
        type=float,
        default=None,
        metavar="SECONDS",
        help="how long without a frame, while one is due, before the page greys and "
        "/health says degraded. Omitted uses 30, a display choice (P4d-2b spec §3), "
        "not a measurement",
    )

    service_parser = sub.add_parser(
        "taskd",
        help="run the rig service: one animal's session at a time, opened, run and "
        "ended from a console (P4d-2b spec §6)",
    )
    service_parser.add_argument(
        "--rig", type=Path, required=True, metavar="PATH",
        help="the rig's display settings: a Python file defining RIG, as tasks/rig.py does",
    )
    service_parser.add_argument(
        "--subjects", type=Path, required=True, metavar="DIR",
        help="one folder per animal, named for it, holding bounds.py (defining BOUNDS, "
        "whose subject must be the folder's name) and, for the stereoscope, "
        "settings.py (defining SETTINGS)",
    )
    service_parser.add_argument(
        "--tasks", type=Path, required=True, metavar="DIR",
        help="the folder of task files a run may use",
    )
    service_parser.add_argument(
        "--allocation", type=Path, default=None,
        help="the event-code allocation. It must carry HEAD_FIXED, HEAD_RELEASED, "
        "PARAM_CHANGED, RUN_START and RUN_END, which every session here strobes, so the "
        "provisional one used when this is omitted is refused",
    )
    service_parser.add_argument(
        "--root", type=Path, required=True,
        help="where session folders go, and where a session left without its animal's "
        "return is looked for at start",
    )
    service_parser.add_argument(
        "--link", required=True, metavar="PUB,REP[,MARK]",
        help="the endpoints this service binds, as `wlx run --link` takes them; `wlx "
        "serve --link` takes the same value. Loopback only unless --link-allow-remote",
    )
    service_parser.add_argument(
        "--link-allow-remote", action="store_true",
        help="permit --link to bind an endpoint other hosts can reach; see `wlx run "
        "--link-allow-remote` for what that exposes, which here includes opening and "
        "ending sessions",
    )

    args = parser.parse_args(argv)

    if args.command == "serve":
        # Imported here, the way `--link` builds its `ZmqLink` inside `run`: no other
        # subcommand loads a web server.
        from wl_xcon import serve as _serve

        return _serve.run(args)

    if args.command == "taskd":
        # Imported here, as `serve` is: no other subcommand loads the service.
        from wl_xcon import service as _service

        return _service.run(args)

    if args.command == "run":
        from wl_xcon.dio import Simulated as SimulatedCard
        from wl_xcon.taskd import Session, SessionSpec
        from wl_xcon.welfare import (
            WARN_WITHIN_DEFAULT,
            Simulated as SimulatedPump,
        )

        # `--deployment` arrives as a hyphenated word because that is how a flag
        # reads; the enum's own value is the underscored one that goes on the wire.
        deployment = Deployment(args.deployment.replace("-", "_"))

        geometry = _session_geometry(args)
        # **Refused before anything is recorded** (direct-view spec §3, plan decision
        # 7): a task written for the other setup, or one the chosen field cannot show,
        # stops here -- before the session opens and before the departure is asked
        # about. `Session.run()` checks again, as the backstop for a caller that is
        # not this command.
        refusals = [
            finding
            for finding in check(
                _load_trial(args.task),
                _load_allocation(args.allocation),
                geometry=geometry,
            )
            if finding.blocking
        ]
        if refusals:
            raise SystemExit(
                "task refused, session not started, nothing recorded:\n"
                + "\n".join(f"  {f.code}: {f.detail}" for f in refusals)
            )

        # Once the check passes, one line, before the `--set` parsing, the link and
        # the `Session`; not beside `out of cage:`, which sits inside the welfare
        # path. Without `--link` this is the only place the setup is said here.
        print(f"  setup: {_setup_words(geometry.view, geometry.half_ipd_cm)}")

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
            #
            # P4d-2b b2a: a third endpoint, the mark socket, is optional, so a
            # `--link PUB,REP` written for b1 runs as it did.
            link_parts = args.link.split(",")
            if len(link_parts) not in (2, 3):
                raise SystemExit(
                    f"--link expects PUB,REP or PUB,REP,MARK (two or three "
                    f"comma-separated endpoints), got {args.link!r}"
                )
            pub_endpoint, rep_endpoint, *mark = link_parts
            # Refused rather than bound when an endpoint is reachable from another
            # host, unless --link-allow-remote says otherwise -- see
            # `ZmqLink.__init__`. Converted to `SystemExit` here so an operator gets
            # the sentence and not a traceback; the message is the one the link
            # wrote, which names what to pass instead.
            try:
                link_cm = _link.ZmqLink(
                    pub_endpoint,
                    rep_endpoint,
                    mark[0] if mark else None,
                    allow_remote=args.link_allow_remote,
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
            # reading the message does not care which. This guard is only about
            # building the `Session`: nothing here has opened its clock yet, so
            # there is nothing for a `finally` to close if it raises.
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
                        geometry=geometry,
                        rig_config=str(args.rig),
                        subject_settings=(
                            "" if args.subject_settings is None else str(args.subject_settings)
                        ),
                        warn_within=(
                            WARN_WITHIN_DEFAULT
                            if args.warn_within is None
                            else args.warn_within
                        ),
                        # Which bounded config, as the operator named it: recorded in
                        # the config snapshot and published to consoles (P4d-2b §3).
                        bounds_config=str(args.bounds),
                    ),
                    # Simulators, because that is what this subcommand is for.
                    # The refusing implementations are the defaults everywhere
                    # else, and a headless run that silently used a real card
                    # would be the worse surprise.
                    card=SimulatedCard(),
                    pump=SimulatedPump(),
                    **session_kwargs,
                )
            except Exceeded as refused:
                raise SystemExit(f"refused: {refused}") from refused

            # **Guarantees `session.end()` on every exit from here on** (Task 9 fix
            # round 1). Before this, `session.end()` ran only inside
            # `_close_interval`'s own `finally`, reached solely from the
            # `try: census = session.run() finally: ...` below -- so a refused
            # departure (`_settle_departure`'s "not confirmed", or an `Exceeded`
            # from `left_cage`/`amend_mark`) or a `KeyboardInterrupt` at either
            # prompt propagated past this whole function with `session opened` on
            # record and nothing to close it. Everything from here to this
            # command's two `return`s now runs inside one `try`, so every exit --
            # a refusal, an interrupt, a fault `_close_interval` re-raises, or a
            # clean finish -- reaches the `finally` below exactly once.
            # `_close_interval` no longer calls `session.end()` itself; this is
            # the one caller left, which is also why `how="wlx run"` is passed
            # here rather than left at `end()`'s own `"terminal"` default -- the
            # process opens and ends the session, not a person at a prompt.
            #
            # **The session's own clock starts before the departure is even asked
            # about** (P4d-2a spec §10 item 3): `session opened` is the first row
            # this run writes, ahead of `departure` and ahead of anything
            # `_settle_departure` below can still refuse over. It is an
            # administrative timestamp, not a welfare mark: an unconfirmed
            # departure still declines to start the session in every way that
            # matters -- no departure mark, no trial, no fluid -- this row aside,
            # which is why `_settle_departure`'s own refusal says "nothing about
            # the departure" rather than claiming nothing at all was recorded.
            # `Session.run()` would open the clock anyway if nothing had by then,
            # which is the backstop for a direct API user, not the reason `open()`
            # is called here.
            session.open(how="wlx run")
            try:
                # On a rig both of these are a person's marks -- out-of-cage the
                # wl-works ELN's once it exists (P4d-2a spec §10) -- and the
                # difference is the whole reason S8 makes them explicit. Here the
                # out-of-cage one comes from `--out-of-cage-at`, which has no
                # default: a headless run states the departure as a clock time and
                # means it, rather than arriving at the session's own zero by
                # omission and quietly reporting chair time as time out of the cage.
                # Head-fixation is marked at the wall instant it is taken -- the
                # base every welfare duration is read in since P4d-2a (spec §10),
                # where it was the frame clock's zero before -- and only for the
                # kind that has it, since `welfare.head_fixed` refuses the other.
                # **A departure far from now is a person's to confirm or amend**
                # (PI, 2026-09-20), and that happens before the mark: `left_cage`
                # refuses a second one, so an amendment made afterwards would have
                # nowhere to go. The row is written after the mark is accepted, so a
                # "correction" the ceiling refuses leaves no record of a change that
                # did not happen.
                marked_then_interrupted = False
                try:
                    departure = _settle_departure(session, args)
                    # **Welfare-critical, this one line** (`docs/design/architecture.md`):
                    # the departure marked as `marks` decided it, `confirmed=` included,
                    # which `welfare._refuse_unconfirmed` trusts. It was
                    # `session.left_cage(at=departure, confirmed=note is not None, ...)`
                    # until b3a, and the decision it carried is `marks`' now.
                    _marks.depart(session, departure)
                except Exceeded as refused:
                    raise SystemExit(f"refused: {refused}") from refused
                except KeyboardInterrupt:
                    # **The departure prompt's own Ctrl-C** (Task 9 fix round 1).
                    # `_settle_departure`'s interactive prompts run through `_ask`,
                    # which turns end-of-input into a quiet `""` but leaves
                    # `KeyboardInterrupt` to propagate. Caught here, so Ctrl-C at
                    # either prompt leaves the terminal the same way. **Said only if
                    # it is true** (final review M1): an interrupt that lands inside
                    # `left_cage` after `welfare` took the mark takes the path below.
                    if session.welfare.left_cage_wall_at is None:
                        print(
                            "run: interrupted -- the departure was not recorded",
                            file=sys.stderr,
                        )
                        return 130
                    marked_then_interrupted = True

                # **From the departure mark on, every way out reaches
                # `_close_interval`** (final review M1). A card that failed at
                # head-fixation, or Ctrl-C there, left `departure` on record and no
                # return row at all; now a fault or a refusal before the first
                # trial takes the not-started branch, which says so, and goes on,
                # and Ctrl-C at any point from here takes the interrupted path.
                # `_close_interval` is reached on every way out of `session.run()`
                # too -- a normal end, Ctrl-C, a fault -- so the interval is never
                # left open with nothing said about why (P4d-2a spec §3, §5, amended
                # by §10: the terminal, and only the terminal, until the wl-works
                # ELN exists).
                census = None
                try:
                    if not marked_then_interrupted:
                        try:
                            # The row is written after the mark is accepted, so a
                            # "correction" the ceiling refuses leaves no record of a
                            # change that did not happen.
                            _marks.record_departure(session, departure)
                            # Head-fixation is marked at the wall instant it is taken,
                            # and only for the kind that has it, since
                            # `welfare.head_fixed` refuses the other.
                            if deployment is Deployment.RIG_FIXED:
                                session.head_fixed(at=session.wall_now())
                        except Exceeded as refused:
                            raise SystemExit(f"refused: {refused}") from refused

                        # **The consequence of a clock time, made visible** (PI,
                        # 2026-09-20). He accepted losing the automatic wall-clock
                        # refusal on the condition that a mistyped hour is legible
                        # rather than silent: `15:45` for `18:45` sits comfortably
                        # inside an eight-hour ceiling, and nothing else on this path
                        # would remark on it. Read from `welfare`, never recomputed
                        # here -- `render`'s rule, on the headless path.
                        #
                        # **`departure`, not `args.out_of_cage_at`**: an amended time
                        # is what the session is bounded by, so it is what this line
                        # must show. Read at the wall, as every welfare duration is
                        # (P4d-2a spec §10).
                        so_far = session.welfare.out_of_cage_seconds(
                            session.wall_now()
                        )
                        print(
                            f"  out of cage: the animal has been out "
                            f"{_hours_minutes(so_far)}, having left its cage at "
                            f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(departure.at))}"
                            # The zone **at the departure**, not at now. A session
                            # started just after a daylight-saving change would
                            # otherwise label a departure made before it with the
                            # zone that is current now -- and that is precisely the
                            # one hour a year when the label carries information.
                            f" ({time.strftime('%Z', time.localtime(departure.at))}"
                            f", this host's local time)"
                        )
                        census = session.run()
                except KeyboardInterrupt:
                    # **Ctrl-C after the departure mark** (final review I4, M1).
                    # During the loop, `run()` has named it an operator's stop and
                    # published it; before it, nothing ran. Either way the animal is
                    # out of its cage, so the return is taken below.
                    census = None
                except BaseException:
                    # A fault, or a refusal before the first trial: the return is
                    # still taken at the terminal, or its absence recorded, before
                    # the exception goes on -- on a rig there is still a head to
                    # release and a clock to publish.
                    #
                    # **The stop reason prints first** (residual fix round, Ruling
                    # 13): an operator typing a return time is entitled to know why
                    # the session stopped before being asked for it. **Not the rest
                    # of `_summary`**: `welfare.deliver` counts a delivery as
                    # `commanded` before `pump.deliver` runs it, so after a pump
                    # fault the fluid and supplement figures would count the very
                    # delivery that failed.
                    print(f"  ended: {session.stopped_because}")
                    _close_interval(session, args)
                    raise
                if census is None:
                    # The return first, then the summary: Ctrl-C was the operator
                    # stopping the session, and the animal going home is what is left
                    # to do. Exit 130, as Ctrl-C at the return prompt exits.
                    _close_interval(session, args)
                    if session.phase:
                        _summary(session, None)
                    _interrupted(session)
                    return 130
                # **The summary first, then the return** (final review I3): the stop
                # reason and the supplement are what an operator needs while the
                # animal is still out, and the return is typed once it is home. In a
                # `try`, so a summary that fails to print still reaches the return.
                try:
                    _summary(session, census)
                finally:
                    interrupted = _close_interval(session, args)
                if interrupted:
                    _interrupted(session)
                    return 130
                return 1 if census.hangs else 0
            finally:
                if session.opened_wall_at is not None and session.ended_wall_at is None:
                    session.end(how="wlx run")

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
                    # A session's stop ends the watch -- unless `wlx taskd` sent it,
                    # whose stream goes on between runs and while idle (the b3a-1
                    # plan, decision 9): watched until Ctrl-C.
                    if (
                        isinstance(frame, _link.Telemetry)
                        and not frame.service
                        and frame.stopped_because
                    ):
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
            except _link.FrameError as exc:
                # Fix round 2, M-a: before this, a frame `decode` could not use --
                # a mismatched schema (`_link.SchemaMismatch`) or one that did not
                # decode at all -- crashed this loop with a traceback instead of
                # the sentence `wlx serve` already shows for the same case
                # (`serve.Server._listen`'s `Hub.reject`).
                print(f"console: {exc}", file=sys.stderr)
                return 1
        return 0

    if args.command == "review":
        allocation = _load_allocation(args.allocation)
        print(render_review(_load_trial(args.task), allocation.task_events))
        return 0

    trial = _load_trial(args.task)
    allocation = _load_allocation(args.allocation)
    rig = _load_rig(args.rig)
    settings = (
        _load_subject_settings(args.subject_settings, None)
        if args.subject_settings is not None
        else None
    )
    geometries = _setups(trial, rig, args.view, settings)
    if settings is not None and geometries and {g.view for g in geometries} == {"direct"}:
        raise SystemExit(_DIRECT_READS_NO_SETTINGS)
    for geometry in geometries:
        print(f"checked against: {_setup_words(geometry.view, geometry.half_ipd_cm)}")
    # One list across the setups, each finding once: most findings are the task's own
    # and read the same in every setup, while check 8's name the field they failed in.
    findings: list = []
    for geometry in geometries or [None]:
        for finding in check(trial, allocation, geometry=geometry):
            if finding not in findings:
                findings.append(finding)
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
