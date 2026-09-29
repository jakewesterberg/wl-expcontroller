"""The two marks that bound the out-of-cage interval, decided once for every caller.

**Welfare-critical, the whole module** (CLAUDE.md; `docs/design/architecture.md`). Human
review before merge.

The PI ruled on 2026-09-29 that the page takes the departure and the return "under the
terminal's exact rules", through "one shared piece of code" (P4d-2b spec §6.0, §6.2).
This is that code. `welfare` holds the rules -- what is refused, and when a person must
confirm -- and this module holds the decision a caller makes around them, which until
slice b3a lived inside `wlx run`'s prompts (`cli._settle_departure`,
`cli._settle_return`): whether a far mark was confirmed or amended, by whom and how, and
the row that says so. The terminal keeps its prompting and `wlx taskd` its sentences;
neither decides.

- **Parsing**: `clock_time` and `clock_or_now` turn what a person typed into an instant.
  Moved here from `cli` unchanged (they were `_wall_clock_time` and `_clock_or_now`,
  and `cli` still reaches them by those names), so the page's text is read by the
  terminal's own parser.
- **The departure**: `decide_departure` turns an instant and a person's answer -- none,
  `Confirm` or `Amend` -- into a `Departure`, or raises `Owed` for a far one nobody has
  answered; `depart` marks it; `record_departure` writes the confirmation's or the
  amendment's row, after the mark and never before.
- **The return**: `take_return` marks it, or raises `Owed` for a far one nobody
  confirmed. **There is no amendment for a return** (the terminal's rule, P4d-2a spec
  §3): nothing has been marked that one could replace, so a corrected time is simply
  typed again.
- **The page**: `page_departure` and `page_return` take the text and the answer a
  console sent, and go through the same functions.

`session` is a `taskd.Session`. For a return, `target` is anything with `wall_now`,
`return_needs_confirmation` and `returned_to_cage` as `Session` has them -- a
`stranded.Restored` is the other. Untyped for the reason `link.Telemetry.of` gives:
`taskd` imports `cli`, which imports this module.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from wl_xcon.bounds import Exceeded
from wl_xcon.record import welfare_note


#: What `--out-of-cage-at` accepts, named once so the flag's help, its refusal and
#: this module's tests all quote the same list.
TIME_FORMATS = "HH:MM, HH:MM:SS, or an ISO 8601 date-time such as 2027-01-13T22:40"


def clock_time(text: str) -> float:
    """An operator's clock time to POSIX seconds. `argparse`'s `type=` for the mark.

    **Welfare-critical** (P4d-2a final review I5, when it was `cli._wall_clock_time`;
    whole, with this module, since b3a; `docs/design/architecture.md`): it turns what an
    operator types into the instants
    that bound the out-of-cage interval -- the departure, and a return typed as a
    clock time -- so a mistake here moves the one limit a session has, and a change
    here wants the same human review as `welfare.py`.

    **Two resolutions are stated here rather than left implicit**, because the PI
    asked for both to be decided (2026-09-20):

    - **Timezone: this host's local zone.** A value with no offset is read in the
      zone the lab machine is configured for, which is the clock on the wall the
      operator is reading. A value that carries its own offset is honored as given.
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

    Returning a POSIX float, not a `datetime`: `welfare` compares it with other wall
    instants and does nothing else with it, and handing it a rich object would put
    calendar arithmetic inside a welfare-critical file.

    **The departure has no `now` spelling, and is read a moment from the session's
    wall being anchored** to the host clock (`welfare.SessionClock`, Ruling 8): at the
    terminal by argparse, just before the session is created; from the page by
    `page_departure`, just after the service has built it. `welfare.left_cage` compares
    it with `Session.wall_now()`, so the host calendar this resolves against and the
    session's wall are one base at the departure; they could part only by an
    adjustment of the host clock in that moment. The return's `now` is the session's
    reading, for the reason `clock_or_now` gives.
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
                f"{text!r} is not a clock time; give {TIME_FORMATS}. A bare time is "
                f"today's date in this host's local timezone"
            ) from None
    if parsed.tzinfo is None:
        # Attaches this host's local offset for the instant in question, which is
        # what makes "local" a resolution rather than an assumption.
        parsed = parsed.astimezone()
    return parsed.timestamp()


def clock_or_now(text: str, now: Callable[[], float]) -> float:
    """`now`, or a clock time as `clock_time` reads one. For the return, which
    is usually marked at the moment it happens (P4d-2a).

    **Welfare-critical** (P4d-2a final review I5, when it was `cli._clock_or_now`;
    whole, with this module, since b3a; `docs/design/architecture.md`): the instant it
    returns closes the out-of-cage interval.

    **`now` is read from `now()` -- the session's clock, `Session.wall_now` -- never
    from `time.time()`** (Task 7 fix round 1). The return is compared with marks taken
    on that clock: the loop-end head release, and the wall `returned_to_cage` reads.
    Since Ruling 8 it is the host clock as it read when the session was created,
    carried forward on a steady clock that counts the time the host is asleep
    (`welfare.SessionClock`), so a `time.time()` read here would sit on the wrong side
    of those marks by however far the host clock has been adjusted since, and be
    refused as in the future or as before the release.

    **A typed clock time is read on the host calendar** (`clock_time`: today's
    date, this host's zone), which is `time.time()`'s base. The two bases agree when
    the session is created and part only by an adjustment of the host clock since.
    A time typed to the minute names a moment an operator read off a clock, and is
    not sensitive to that the way "this instant" is; one typed to the current second
    could be, and `now` is the spelling for this instant.
    """
    if text.strip().lower() == "now":
        return now()
    return clock_time(text)


@dataclass(frozen=True)
class Confirm:
    """A person's *confirm* on a far departure: who, when a name was given, and how --
    `--confirm-out-of-cage`, at the terminal, or on the page."""

    by: str
    how: str


@dataclass(frozen=True)
class Amend:
    """A person's *amend*: the corrected instant, why, who (both refused blank by
    `welfare.amend_mark`), and how."""

    at: float
    reason: str
    by: str
    how: str


@dataclass(frozen=True)
class Departure:
    """What the departure is marked with, decided: the instant, who gave it and how (the
    `departure` row's), and the confirmation's or amendment's row, or `None`."""

    at: float
    by: str
    how: str
    note: dict | None

    @property
    def confirmed(self) -> bool:
        """Whether a person acted on it -- confirmed it, or amended it, since an
        amendment is its own confirmation. **What `welfare._refuse_unconfirmed` is told**
        (it was `main`'s `confirmed=note is not None` until b3a), and read from the note
        rather than kept beside it, so the two cannot disagree."""
        return self.note is not None


class Owed(Exception):
    """A far mark nobody has answered for: the sentence a person must be shown, and the
    answers they may give. **Raised, never returned**, so no caller can mark past it."""

    def __init__(self, mark: str, at: float, warning: str) -> None:
        super().__init__(warning)
        self.mark = mark
        self.at = at
        self.warning = warning
        self.answers = ("confirm", "amend") if mark == "departure" else ("confirm", "re-type")


def decide_departure(
    session, at: float, answer: Confirm | Amend | None, *, by: str, how: str
) -> Departure:
    """What a departure typed as `at` is marked with, given a person's answer.

    **PI, 2026-09-20:** *"if a number is input that is more than 30 min from the current
    time, a warning should appear that the experimenter must click through to confirm.
    There should also be an option to update the time if necessary, but a reason should
    be given and the experimenter name logged."*

    - *Amended*: recorded by `welfare.amend_mark` (which refuses a blank reason or name)
      and marked at the corrected instant, which meets every refusal the original
      would. Its own confirmation.
    - *Inside the band* (`departure_needs_confirmation` answers `None`): taken as given,
      `by` and `how` naming where it came from; a *confirm* here changes nothing.
    - *Far, confirmed*: marked as given, with a `departure confirmed` row.
    - *Far, no answer*: `Owed`. The terminal asks, or refuses with no one to ask; the
      page says *confirm or amend*. Nothing is marked or written.

    **Asked before the mark, never after**: `welfare.left_cage` refuses a second mark,
    so an amendment made afterwards would have nowhere to go.
    """
    warning = session.departure_needs_confirmation(at)

    def note(kind: str, now: float, reason: str, who: str, said: str) -> dict:
        return {
            "kind": kind,
            "subject": session.spec.subject,
            "was": at,
            "now": now,
            "reason": reason,
            "by": who,
            "how": said,
            # The session's clock, as `Session._note` stamps every other row, so one
            # file's `recorded_at` column has one base (Ruling 8).
            "recorded_at": session.wall_now(),
        }

    if isinstance(answer, Amend):
        session.amend_mark(
            "departure", original=at, amended=answer.at, reason=answer.reason, by=answer.by
        )
        return Departure(
            answer.at,
            answer.by,
            answer.how,
            note("departure amended", answer.at, answer.reason, answer.by, answer.how),
        )
    if warning is None:
        return Departure(at, by, how, None)
    if isinstance(answer, Confirm):
        return Departure(
            at, answer.by, answer.how, note("departure confirmed", at, "", answer.by, answer.how)
        )
    raise Owed("departure", at, warning)


def depart(session, decision: Departure) -> None:
    """Mark the departure as decided: `session.left_cage`, which writes the `departure`
    row once `welfare` has taken it. **`confirmed=decision.confirmed` is the value
    `welfare._refuse_unconfirmed` trusts**: true exactly when a person acted."""
    session.left_cage(
        at=decision.at, confirmed=decision.confirmed, by=decision.by, how=decision.how
    )


def record_departure(session, decision: Departure) -> None:
    """The confirmation's or amendment's row, **after `depart` has taken the mark and
    never before**: a correction the ceiling or the clock refused leaves no record of a
    change that did not happen. Nothing, for a departure nobody was asked about."""
    if decision.note is not None:
        welfare_note(session.directory, **decision.note)


def take_return(target, at: float, *, confirmed: bool, by: str, how: str) -> None:
    """Mark the return at `at`, or raise `Owed` for a far one nobody confirmed.

    **The confirmation is asked first**, before `welfare`'s other refusals -- the
    terminal's order since P4d-2a, kept so the terminal and the page meet one rule. A
    return typed in the wrong half of the day moves the interval in the direction that
    makes a session look shorter than it was, which is why a far one is a person's to
    confirm (PI, 2026-09-20, ruling 4)."""
    warning = target.return_needs_confirmation(at)
    if warning is not None and not confirmed:
        raise Owed("return", at, warning)
    target.returned_to_cage(at, confirmed=confirmed, by=by, how=how)


def _page_time(text: str, now: Callable[[], float] | None = None) -> float:
    """What a console typed, read by the terminal's parser -- `clock_time`, or
    `clock_or_now` given the session's `now` -- and refused in the terminal's words
    when it is not a time this host can place.

    **The parser is not changed for this, and must not be**: it is the terminal's,
    moved here unchanged. A date `datetime` parses and this host's calendar cannot
    place -- `0001-01-01T00:00`, `9999-12-31T23:59` -- makes its `astimezone()` raise
    `ValueError`, which is not an `argparse.ArgumentTypeError`. `argparse` turns that
    into a usage error for `--out-of-cage-at`; from a console it would have reached
    the page as a traceback rather than a refusal (fix round 1 of the b3a-1 Task 1
    review). `OverflowError` and `OSError` for the same instant on other platforms,
    as `cli._time_of_day` catches them.

    **`Exceeded` passes through untouched**: it is a `ValueError`, and a welfare
    refusal must never be relabeled as a typo.
    """
    try:
        return clock_time(text) if now is None else clock_or_now(text, now)
    except Exceeded:
        raise
    except (ValueError, OverflowError, OSError) as outside:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a clock time this host can place ({outside}); give "
            f"{TIME_FORMATS}"
        ) from outside


def page_departure(
    session,
    *,
    departure: str,
    answer: str | None,
    amend_to: str | None,
    amend_reason: str,
    by: str,
) -> Departure:
    """A departure as a console sent it (P4d-2b spec §6.2): the text as typed, read by
    the terminal's own parser, and the page's answer -- `None`, `"confirm"` or
    `"amend"` with the corrected time and a reason -- given as the terminal's
    `Confirm`/`Amend`, named for the person who sent it. Raises
    `argparse.ArgumentTypeError` for text that is not a time, `Owed` and `Exceeded` as
    `decide_departure` does.

    **Anything else a console sends is refused, never read as no answer** -- the
    terminal's rule, where anything that is not a confirmation stops (fix round 1 of
    the b3a-1 Task 1 review). An answer it does not know (`"Amend"`, `"amended"`), or
    a corrected time or a reason sent without `amend`, would otherwise leave an
    in-band departure marked at the very time the person was correcting, with their
    amendment dropped without a word. A reason that is only blank space is no reason,
    as `welfare.amend_mark` counts one. Checked before anything is parsed or marked.
    """
    if answer not in (None, "confirm", "amend"):
        raise argparse.ArgumentTypeError(
            f"a departure is answered confirm, amend or not at all, and {answer!r} is "
            f"none of them, so it is refused rather than read as no answer"
        )
    if answer != "amend":
        sent = [
            f"a corrected departure time {amend_to!r}" if amend_to is not None else "",
            f"a reason {amend_reason!r}" if amend_reason.strip() else "",
        ]
        if any(sent):
            raise argparse.ArgumentTypeError(
                f"{' and '.join(part for part in sent if part)} came without the answer "
                f"amend, so it is refused rather than dropped; send it with amend, or "
                f"leave it out"
            )
    at = _page_time(departure)
    choice: Confirm | Amend | None = None
    if answer == "amend":
        if amend_to is None:
            raise argparse.ArgumentTypeError(
                "an amendment gives the corrected departure time, and none was given"
            )
        choice = Amend(
            at=_page_time(amend_to), reason=amend_reason, by=by, how="amended on the page"
        )
    elif answer == "confirm":
        choice = Confirm(by=by, how="confirmed on the page")
    return decide_departure(session, at, choice, by=by, how="typed on the page")


def page_return(
    target, *, returned: str, confirm: bool, by: str, how: str = "the page"
) -> None:
    """A return as a console sent it: the text as typed, or `now` on the session's own
    clock, read by the terminal's parser, then `take_return`.

    **`confirm` is refused unless it is `True` or `False`** (fix round 1 of the b3a-1
    Task 1 review): `take_return` and `welfare._refuse_unconfirmed` read it for its
    truth, so a `"false"` sent as text would confirm a far return nobody confirmed. It
    is the return's only answer: there is no amendment, so a corrected time is simply
    sent again.
    """
    if not isinstance(confirm, bool):
        raise argparse.ArgumentTypeError(
            f"a return is confirmed true or false, and {confirm!r} is neither, so it is "
            f"refused rather than read as one"
        )
    take_return(
        target, _page_time(returned, target.wall_now), confirmed=confirm, by=by, how=how
    )
