"""Fluid and chair-time accounting, and the only path from a task to the pump.

**Welfare-critical. Human review required before merge** (CLAUDE.md, S8 §7, items 2
and 3). The second such module, and it exists because the first one was not enough:
`bounds.py` had ceilings and `bounds.check_delivery` was called by nothing outside
its own tests, so a task could command reward, a session could run to completion, and
no ceiling was ever asked. **A bound nothing calls reads as present and is not** --
the same shape as a mutation gate that could never go green and a checker that
examined nothing. This module is the caller.

The split between the two files is deliberate and is what keeps each reviewable.
`bounds.py` is pure: the limits themselves -- ceilings, a daily floor -- and the
arithmetic of whether a number is past one or short of it. It has no clock, no hardware
and no state that outlives a question. This file has all three -- a running total, a
restraint clock, and a pump -- and joining them to the limits is the whole of its job.

**Fluid has a floor, not a ceiling** (PI, 2026-09-06). This file was written the
other way round first, and the difference matters: a fluid *ceiling* refuses a
delivery an animal earned and stops a session partway through, which under this
protocol withholds fluid to satisfy a limit nobody set. The daily figure is a
**minimum**, and what this module does with it is report at session close how much is
still owed, so a person can supplement it. **No delivery is ever refused on volume.**

Chair time and trial count *are* ceilings, and they do stop a session.

Two things fail closed here, and neither is fluid:

- **A missing floor or a missing chair-time ceiling refuses to start.** A bounded
  config lacking either is one nobody finished, and a missing floor reads exactly like
  a floor of zero to anything that does not check -- so nobody would ever be told to
  supplement.
- **An unconfigured pump refuses** rather than delivering nothing, for `dio.Absent`'s
  reason one layer up: a session that runs a full protocol and dispenses nothing has
  worked an animal for no reward and said so nowhere.

And one thing deliberately does *not*: an unknown prior total leaves the day's
shortfall unknown and **keeps paying the animal**. Reporting `None` is a refusal to
claim the day went well; refusing delivery would be a refusal to pay for work.

**What is not here, and why.** Nothing converts millilitres into an open time for the
solenoid. `wl-sync`'s board one-shots the *manual* button at ~199 ms and passes our
commanded line through its OR gate untouched (their `hardware/README.md`, the
2026-08-15 panel-instrumentation entry), so the pulse width is ours to choose and the
volume it yields is a per-rig pump calibration that has never been measured. Writing
one now would be inventing a dose. So `Pump` takes millilitres, the implementations
here account and simulate, and the driver that opens copper is P7's -- blocked on the
same measurement as everything else on that side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from wl_expcontroller.bounds import (
    Bounds,
    Exceeded,
    Reconciliation,
    reconcile,
    reconcile_report,
)

#: The daily fluid minimum a session reports its shortfall against (S8 §5.2b, as
#: corrected by the PI on 2026-09-06). Named rather than inferred, so adding a second
#: reward size cannot silently escape the day's accounting.
DAILY_FLUID = "daily_fluid"

#: The restraint ceiling, in seconds. **Chair time, from head-fixation** (S8 §5.2,
#: PI 2026-08-31) -- not from the first trial and not from the first reward. The name
#: is where that survives: `session_duration` invites someone to start it when the
#: session starts, and setup, calibration and unrewarded shaping all count.
CHAIR_TIME = "chair_time"

#: Optional, unlike the two above. A session bounded by fluid and by restraint is
#: bounded; a lab that states no trial cap has stated a policy rather than forgotten
#: one.
MAX_TRIALS = "max_trials"


class Pump(Protocol):
    """Whatever turns a volume into fluid in front of the animal.

    Millilitres, because millilitres are what the ceilings are denominated in and a
    unit conversion between the limit and the delivery is a place for a factor of
    sixty to hide.
    """

    def deliver(self, ml: float) -> None: ...


@dataclass
class Simulated:
    """Records volumes; touches nothing. What a simulated session delivers into.

    Complete rather than a stub: a simulated session has no fluid, so a list of the
    volumes it commanded *is* the whole truth about it, and the accounting under test
    is the same accounting a rig runs.
    """

    delivered: list = field(default_factory=list)

    def deliver(self, ml: float) -> None:
        self.delivered.append(ml)


@dataclass
class Absent:
    """No pump. **Refuses, rather than quietly doing nothing.**

    `dio.Absent`'s argument, one layer up and with the animal on the other end of it:
    a no-op pump lets a session run its full protocol, score every trial correct, and
    dispense nothing at all. The animal has worked for nothing, the session looks
    clean, and the first sign is a weight check days later.
    """

    def deliver(self, ml: float) -> None:
        raise RuntimeError(
            "no pump is configured, so a reward cannot be delivered; a session that "
            "scores trials correct and dispenses nothing is worse than one that "
            "refuses to start. Use welfare.Simulated for a dry run"
        )


@dataclass
class Welfare:
    """One subject's day, as far as this session can see it.

    Constructed per session and never shared: `already_today` is a figure from
    `wl-works` at session start (S8 §5.2b), and a stale one is a ceiling computed
    against yesterday.
    """

    bounds: Bounds
    pump: Pump
    #: What another deployment already delivered today, from `prepare-session`.
    #: **`None` is a refusal, not a zero** -- an unreachable ELN cage-side is the
    #: commonest way this is unknown, and continuing on an assumed zero is how a
    #: daily budget silently doubles.
    already_today: float | None
    #: What this session has commanded. A **lower bound** on what the animal got
    #: (P17), which is why it is never used alone.
    commanded: float = 0.0
    #: The sync box's delivered-line figure for this session, when it is readable.
    #: `None` until one arrives; S8 open item 2 is whether that is continuous or only
    #: at session end, and this shape does not care which.
    delivered: float | None = None
    deliveries: int = 0
    fixed_at: float | None = None
    released_at: float | None = None
    #: Anything a person should see in the session summary, in order.
    notes: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if DAILY_FLUID not in self.bounds.minima:
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} declares no "
                f"{DAILY_FLUID!r} minimum, so a session could never say what the day "
                f"still owes; a missing floor is not a floor of zero"
            )
        if CHAIR_TIME not in self.bounds.ceilings:
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} has no "
                f"{CHAIR_TIME!r} ceiling, so restraint is unbounded; a missing limit "
                f"is not an absent one"
            )

    # --- fluid ------------------------------------------------------------

    def session_total(self) -> float:
        """This session's contribution to the day, reconciled where possible.

        **Through `bounds.reconcile`, never by taking a maximum here.** Which of the
        two figures a ceiling is enforced against is a welfare rule with a written
        argument behind it -- including that a delivered line *below* commanded is a
        fault rather than a smaller total -- and a second copy of that rule is a
        second place for it to drift.
        """
        if self.delivered is None:
            return self.commanded
        return reconcile(self.commanded, self.delivered)

    def total_today(self) -> float | None:
        """What the animal has had today, or `None` if nobody knows."""
        if self.already_today is None:
            return None
        return self.already_today + self.session_total()

    def shortfall(self) -> float | None:
        """How much of the day's minimum is still owed, or `None` if unknown.

        **The number a session exists to hand a person at close.** An animal that
        earned less than its floor in the chair is supplemented afterwards; one that
        earned more has earned more. `None` means the day cannot be counted -- an
        unreachable ELN at `prepare-session` is the usual reason -- and it is reported
        rather than resolved to zero, because a day nobody measured is not a day that
        went well.
        """
        return self.bounds.shortfall(DAILY_FLUID, self.total_today())

    def report(self) -> Reconciliation:
        """What the two fluid records say, for the session summary and the console."""
        return reconcile_report(self.commanded, self.delivered or 0.0)

    def reconcile(self, delivered: float) -> None:
        """Take the sync box's delivered-line figure for this session."""
        self.delivered = delivered

    def confirm_already_today(self, total: float, by: str) -> None:
        """A human supplying the day's prior total, making the day countable again.

        Recorded with its actor, because a figure someone typed and a figure the ELN
        pushed are different kinds of evidence about the same animal.
        """
        self.already_today = total
        self.notes.append(("already_today confirmed", total, by))

    def deliver(self, ref: str) -> float:
        """The only path from a `Reward` action to fluid.

        **No volume check, deliberately** (PI, 2026-09-06): there is no fluid ceiling,
        so there is nothing here that can refuse. What bounds a delivery is
        `Ceiling.maximum` on `ref` itself, enforced when a console *sets* the volume
        rather than when a task commands one -- which is the right place, because the
        magnitude is a configuration decision and the task can only name it.

        **Charged before the valve opens.** A pump that raises after opening would
        otherwise leave fluid unaccounted, and the day's total is what a person
        supplements against.
        """
        ml = self.bounds.value(ref)
        self.commanded += ml
        self.deliveries += 1
        self.pump.deliver(ml)
        return ml

    # --- restraint --------------------------------------------------------

    def head_fixed(self, at: float) -> None:
        """Start the restraint clock. Required before a session may run (S8 §5.2)."""
        if self.fixed_at is not None and self.released_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is already recorded as head-fixed "
                f"at {self.fixed_at}; a second start would run two restraint clocks "
                f"and the shorter one would silently win"
            )
        self.fixed_at = at
        self.released_at = None

    def head_released(self, at: float) -> None:
        self.released_at = at

    def chair_seconds(self, now: float) -> float:
        """Restraint time so far. Zero before the animal is in the chair."""
        if self.fixed_at is None:
            return 0.0
        end = self.released_at if self.released_at is not None else now
        return end - self.fixed_at

    # --- the session's own limits ----------------------------------------

    def must_stop(self, now: float, trials: int) -> str | None:
        """Why this session must end, or `None`. **Never about fluid.**

        Returned rather than raised: a session ending on its ceiling is the design
        working, and it has a record to close, a map to write and a summary to
        report. An exception would make the correct ending look like a fault.
        """
        chair = self.bounds.ceilings[CHAIR_TIME]
        if self.chair_seconds(now) > chair.value:
            return (
                f"chair_time: subject {self.bounds.subject!r} has been restrained "
                f"{self.chair_seconds(now):.0f} {chair.unit} against a ceiling of "
                f"{chair.value:.0f}"
            )
        cap = self.bounds.ceilings.get(MAX_TRIALS)
        if cap is not None and trials >= cap.value:
            return f"max_trials: {trials} trials against a ceiling of {cap.value:.0f}"
        return None


@dataclass
class Rig:
    """A trial's outbound I/O: the card, and the only path to the pump.

    This is what a task's `Mark` and `Reward` actions actually reach (`run.Effects`).
    It lives in the welfare-critical file rather than beside the loop so that the
    whole route from a task's declaration to fluid is readable in one place: a
    reviewer asking "can anything deliver reward without the day's accounting seeing
    it" answers that by reading this file and no other.

    **Nothing is swallowed here.** There is no fluid ceiling to refuse a delivery
    (PI, 2026-09-06), so the only way `deliver` fails is a pump that will not
    answer -- and that is a broken rig, not the design working. Absorbing it would
    produce a session's worth of correct trials nobody was paid for, which is the
    failure `Absent` exists to prevent arrived at by a different route.

    An earlier version caught a ceiling here and stopped the session at the next
    trial boundary. Recorded because the shape was right and the premise was not: if
    a *stopping* condition ever arrives mid-trial, it belongs here and it must not
    raise out of the frame loop -- that would abort a trial the animal completed,
    losing a real datum and leaving the display in a state nothing wrote down.
    """

    card: object
    welfare: Welfare

    def mark(self, code: int) -> None:
        self.card.emit(code)

    def reward(self, ref: str) -> None:
        self.welfare.deliver(ref)
