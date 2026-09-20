"""Fluid and session-duration accounting, and the only path from a task to the pump.

**Welfare-critical. Human review required before merge** (CLAUDE.md, S8 §7).
**S8 §5.2 and §5.2c carry the arguments** -- which PI ruling set each limit and
when, and the failures each guard was written against. They are there so that this
file is what a reviewer can hold in their head: one sentence per rule, and the
refusal messages an operator actually reads.

- `bounds.py` holds the limits and the arithmetic; this holds the state -- the day's
  running total, two clocks, a pump -- and joining them is the whole of its job.
- **Fluid has a floor, not a ceiling** (PI, 2026-09-06): no delivery is refused on
  volume, and the day's shortfall is reported at close so a person can supplement.
- **One duration limit: out of the cage to back in it**, twelve hours (PI,
  2026-09-19). Chair time is recorded and bounds nothing; there is no trial cap.
- **`Rig` is the only route from a task's `Reward` to fluid**, so "can anything
  deliver reward without the day's accounting seeing it" is a one-file question.
- A missing floor, a missing mark, an unconfigured pump, a value that is not a real
  number, or a negative magnitude all **refuse**: in each case the bad thing is
  indistinguishable from a benign one to anything that answers zero. *An instant is
  finite; a magnitude is finite and not negative* (`bounds._finite`/`_magnitude`,
  S8 §5.2c; `tests/test_welfare.py` enumerates every door).
- An **unknown** prior total does not refuse -- it leaves the shortfall `None` and
  keeps paying. A refusal to claim the day went well, not a refusal to pay.

**No millilitres-to-open-time conversion lives here**: the pump calibration has never
been measured, so `Pump` takes millilitres and P7 owns the driver. **The out-of-cage
marks have no event code yet** -- two codes are S2's and `wl-preproc`'s to allocate
(ADR-0007), asked of the PI, S8 open item 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from wl_expcontroller.bounds import (
    Bounds,
    Exceeded,
    Reconciliation,
    reconcile,
    reconcile_report,
    _finite,
    _magnitude,
)

#: The daily fluid minimum a session reports its shortfall against (S8 §5.2b, as
#: corrected by the PI on 2026-09-06). Named rather than inferred, so adding a second
#: reward size cannot silently escape the day's accounting.
DAILY_FLUID = "daily_fluid"

#: The duration ceiling, in seconds. **From leaving the home cage to returning to
#: it** (PI, 2026-09-19) -- not from head-fixation, which under-counts by transport
#: and chairing, and not from the first trial. Twelve hours is the institutional
#: figure; the number itself lives in a subject's bounded config and nowhere in this
#: module, so that nothing can default to it.
OUT_OF_CAGE = "out_of_cage"


class Deployment(Enum):
    """Where the animal is for this session, and therefore whether a duration bound
    exists at all. **Required, with no default and no third answer.**

    A declaration rather than an inference: a rig session nobody marked and a
    cage-side one with nothing to mark are indistinguishable to anything that
    answers zero. Defaulting either way is wrong, so the session says which it is
    and `welfare` refuses what does not match (S13 §4.0).
    """

    #: A rig session: the animal left its home cage, was transported, chaired and
    #: head-fixed. The twelve-hour clock binds it, and it must carry both marks.
    OUT_OF_CAGE = "out_of_cage"

    #: A cage-side kiosk session (S13): the animal never left home, so there is no
    #: out-of-cage event, no head-fixation, and **no duration bound** -- which the PI
    #: chose, and which this member is how a session states rather than acquires.
    ANIMAL_AT_HOME = "animal_at_home"


class Pump(Protocol):
    """Whatever turns a volume into fluid in front of the animal.

    Millilitres, because that is what the bounded config is denominated in: a unit
    conversion between the limit and the delivery hides a factor of sixty.
    """

    def deliver(self, ml: float) -> None: ...


@dataclass
class Simulated:
    """Records volumes; touches nothing. What a simulated session delivers into.

    Complete rather than a stub: a simulated session has no fluid, so the list of
    volumes it commanded *is* the whole truth about it.
    """

    delivered: list = field(default_factory=list)

    def deliver(self, ml: float) -> None:
        self.delivered.append(ml)


@dataclass
class Absent:
    """No pump. **Refuses, rather than quietly doing nothing.**

    `dio.Absent`'s argument with an animal on the other end: a no-op pump lets a
    session score every trial correct and dispense nothing, and the first sign is a
    weight check days later.
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

    Constructed per session and never shared: a stale `already_today` is a figure
    computed against yesterday (S8 §5.2b).
    """

    bounds: Bounds
    pump: Pump
    #: What another deployment already delivered today, from `prepare-session`.
    #: **`None` is a refusal, not a zero** -- an assumed zero is how a daily figure
    #: silently doubles.
    already_today: float | None
    #: Rig or cage-side. **Required, with no default**, so that every construction
    #: site states which welfare limits apply to it -- see `Deployment`.
    deployment: Deployment
    #: What this session has commanded. A **lower bound** on what the animal got
    #: (P17), which is why it is never used alone.
    commanded: float = 0.0
    #: The sync box's delivered-line figure, when readable. `None` until one
    #: arrives; S8 open item 2 is whether that is continuous or only at close.
    delivered: float | None = None
    deliveries: int = 0
    #: The clock that bounds the session. **Set through `left_cage` and
    #: `returned_to_cage`, never by constructing a `Welfare` around them** -- the
    #: guards live on those methods. `out_of_cage_seconds` still catches a
    #: non-finite or backwards result, so a direct construction can hide only a
    #: wrong-but-ordered instant.
    left_cage_at: float | None = None
    returned_at: float | None = None
    #: The restraint clock. Recorded, and it bounds nothing (PI, 2026-09-19).
    fixed_at: float | None = None
    released_at: float | None = None
    #: Anything a person should see in the session summary, in order.
    notes: list = field(default_factory=list)

    def __post_init__(self) -> None:
        # The three volumes this object is built around; `already_today` arrives
        # from `wl-works`. A `nan` in it turned an unmeasured day into "nothing is
        # owed" (S8 §5.2c).
        for what, value in (
            ("the day's prior fluid total", self.already_today),
            ("this session's commanded fluid", self.commanded),
            ("the delivered-line fluid figure", self.delivered),
        ):
            if value is not None:
                _magnitude(what, value)
        if DAILY_FLUID not in self.bounds.minima:
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} declares no "
                f"{DAILY_FLUID!r} minimum, so a session could never say what the day "
                f"still owes; a missing floor is not a floor of zero"
            )
        declared = OUT_OF_CAGE in self.bounds.ceilings
        if self.deployment is Deployment.OUT_OF_CAGE and not declared:
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} has no "
                f"{OUT_OF_CAGE!r} ceiling, so a session out of the cage would be "
                f"unbounded; a missing limit is not an absent one"
            )
        if self.deployment is Deployment.ANIMAL_AT_HOME and declared:
            # A limit switched off by a flag -- what the declaration exists to
            # prevent, reached from the other side.
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} states an "
                f"{OUT_OF_CAGE!r} ceiling while this session declares the animal is "
                f"at home; a session cannot both have that interval and not have it"
            )

    # --- fluid ------------------------------------------------------------

    def session_total(self) -> float:
        """This session's contribution to the day, reconciled where possible.

        **Through `bounds.reconcile`, never by taking a maximum here**: which of
        the two figures a total comes from is a welfare rule, and a second copy of
        it is a second place for it to drift.
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

        **The number a session exists to hand a person at close.** `None` means the
        day cannot be counted -- an unreachable ELN at `prepare-session` is the usual
        reason -- and is reported rather than resolved to zero, because a day nobody
        measured is not a day that went well.
        """
        return self.bounds.shortfall(DAILY_FLUID, self.total_today())

    def report(self) -> Reconciliation:
        """What the two fluid records say, for the session summary and the console."""
        return reconcile_report(self.commanded, self.delivered or 0.0)

    def reconcile(self, delivered: float) -> None:
        """Take the sync box's delivered-line figure for this session.

        A volume arriving from outside the process (S8 §5.1), so it is checked like
        one: every fluid figure a person reads is computed from it.
        """
        _magnitude("the delivered-line fluid figure", delivered)
        self.delivered = delivered

    def confirm_already_today(self, total: float, by: str) -> None:
        """A human supplying the day's prior total, making the day countable again.

        Recorded with its actor: a figure someone typed and one the ELN pushed are
        different kinds of evidence about the same animal.
        """
        _magnitude("the day's prior fluid total", total)
        self.already_today = total
        self.notes.append(("already_today confirmed", total, by))

    def deliver(self, ref: str) -> float:
        """The only path from a `Reward` action to fluid.

        **No volume check, deliberately** (PI, 2026-09-06): there is no fluid
        ceiling. What bounds a delivery is `Ceiling.maximum` on `ref`, enforced when
        a console *sets* the volume -- the magnitude is a configuration decision and
        a task can only name it. **Charged before the valve opens**, so a pump that
        raises after opening leaves no fluid unaccounted.
        """
        ml = self.bounds.value(ref)
        self.commanded += ml
        self.deliveries += 1
        self.pump.deliver(ml)
        return ml

    # --- out of cage, and back in -----------------------------------------

    def left_cage(self, seconds_ago: float, now: float) -> None:
        """Start the clock the session is bounded by (PI, 2026-09-19).

        **How long ago, not at what time.** The session clock reads zero at the
        start, so the animal leaving its cage is at a *negative* instant in that
        base; a timestamp parameter invited a caller to pass zero, which made
        out-of-cage time equal chair time. S8 §5.2 item 4 has that account.

        Refused: a cage-side deployment (it never left); a value that is not a real
        number or is negative (S8 §5.2c); and one **at or past** the ceiling, which
        also catches a wall clock, and is *at* because an animal out for exactly the
        limit has no room for a trial.
        """
        if self.deployment is Deployment.ANIMAL_AT_HOME:
            raise Exceeded(
                f"this session declares subject {self.bounds.subject!r} is at home, "
                f"so it cannot also be recorded as leaving its cage; the declaration "
                f"and the mark disagree and neither is safe to prefer"
            )
        if self.left_cage_at is not None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is already recorded as out of its "
                f"cage at {self.left_cage_at}; a second mark would run two clocks and "
                f"the shorter one would silently win. A closed interval is not "
                f"re-armed either (PI, 2026-09-20): out and back is one session, so "
                f"an animal brought out again starts a new one"
            )
        _finite("the time since this subject left its cage", seconds_ago)
        _finite("the session clock", now)
        if seconds_ago < 0.0:
            raise Exceeded(
                f"subject {self.bounds.subject!r} cannot have left its cage "
                f"{-seconds_ago} seconds in the future; this is how long ago the "
                f"animal came out, on the session's own clock"
            )
        ceiling = self.bounds.ceilings[OUT_OF_CAGE]
        if seconds_ago >= ceiling.value:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is recorded as out of its cage "
                f"{seconds_ago} {ceiling.unit} ago, against a ceiling of "
                f"{ceiling.value:.0f}; a session cannot start at or outside the "
                f"limit it is bounded by, because its first trial is already past "
                f"it. If this was a timestamp, it is in the wrong base -- this "
                f"parameter is how long ago, in seconds"
            )
        self.left_cage_at = now - seconds_ago

    def returned_to_cage(self, at: float) -> None:
        """Close the interval: the animal is home, and this session is over.

        `at` is an instant, not a "how long ago": unlike the opening mark this one
        is at or after the present. **The session clock stops when the frames do**,
        so a return marked long after the loop ended carries the loop's last
        reading unless the caller supplies a later one.

        **This closes an open interval and does nothing else** -- every refusal
        below was reachable when it did not. **It also closes the session** (PI,
        2026-09-20): out and back is one session, so `left_cage` refuses to re-arm.
        S8 §5.2 item 4 has the ruling and the consequence he accepted.
        """
        _finite("the time the animal went back into its cage", at)
        if self.deployment is Deployment.ANIMAL_AT_HOME:
            raise Exceeded(
                f"this session declares subject {self.bounds.subject!r} is at home, "
                f"so there is no interval for a return to close"
            )
        if self.left_cage_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is not recorded as having left its "
                f"cage, so a return closes nothing; a session marked only at the end "
                f"has no interval at all"
            )
        if self.returned_at is not None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is already recorded as back in its "
                f"cage at {self.returned_at}; a second return would move a closed "
                f"interval, and the shorter one would silently win"
            )
        if self.fixed_at is not None and self.released_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is recorded as head-fixed at "
                f"{self.fixed_at} and not released, so it cannot also be in its cage; "
                f"release the head first. A session is stopped with a stop, not by "
                f"recording the animal somewhere it is not"
            )
        if at < self.left_cage_at:
            raise Exceeded(
                f"subject {self.bounds.subject!r} cannot be back in its cage at {at} "
                f"having left it at {self.left_cage_at}; a negative duration is not a "
                f"duration, and an interval that runs backwards bounds nothing"
            )
        self.returned_at = at

    def out_of_cage_seconds(self, now: float) -> float | None:
        """How long the animal has been out of its home cage.

        `None` -- never zero -- for a cage-side session: there is no such interval,
        and a zero reads on a console as a clock that has not started.

        **A missing mark raises rather than answering zero**, and raises on every
        call rather than only at `preflight`, because an unmarked rig session is
        indistinguishable from a cage-side one to anything that answers a number.
        `dio.Absent`'s rule, on the clock that bounds a session.
        """
        if self.deployment is Deployment.ANIMAL_AT_HOME:
            return None
        if self.left_cage_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is not recorded as out of its "
                f"cage, so the session's one duration limit has no start; call "
                f"left_cage(), or declare Deployment.ANIMAL_AT_HOME if the animal "
                f"never left it. A missing mark is not an absent limit"
            )
        end = self.returned_at if self.returned_at is not None else now
        seconds = end - self.left_cage_at
        # **On the computed duration, not only on the marks**: this is the number
        # every ceiling is read against, and arithmetic on two checked values can
        # still produce an unchecked third (S8 §5.2c).
        _finite("the time out of the cage", seconds)
        if seconds < 0.0:
            # The marks are guarded, so the only way here is a `now` before the
            # opening mark -- a `Session(clock=...)` that runs backwards, or one
            # whose base is not the base the mark was taken in. **A negative
            # duration is not a duration**, and it is under every ceiling there is,
            # so answering it would be a limit switched off by arithmetic.
            raise Exceeded(
                f"the clock for subject {self.bounds.subject!r} reads {seconds:.0f} "
                f"{self.bounds.ceilings[OUT_OF_CAGE].unit}: {end} is before the "
                f"animal left its cage at {self.left_cage_at}. A duration that runs "
                f"backwards is under every ceiling and bounds nothing"
            )
        return seconds

    def preflight(self, now: float) -> None:
        """What must be true before a session runs (S8 §5.2). Raises `Exceeded`.

        Called by `taskd.Session.run` before its first frame, so a missing mark is
        a refusal a person sees at the console rather than a fault mid-session.

        Three things must hold for a rig: the **out-of-cage mark** (asked of
        `out_of_cage_seconds`, so that refusal has one home), **head-fixation**
        (S8 §5.2 -- without it there is no record of restraint), and an interval
        still **open** (a session whose animal is recorded home is bounded by a
        number no trial can move).

        **It does not check the ceiling**, and claimed to until a review read it:
        `left_cage` refuses a mark at or past the limit and `must_stop` refuses
        during the loop. `now` is passed rather than assumed zero, which hardcoded
        the base into a second place.
        """
        self.out_of_cage_seconds(now)  # for the refusal; the number is not wanted
        if self.returned_at is not None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is already recorded as back in its "
                f"cage at {self.returned_at}, so this session's interval is closed "
                f"and no trial can be inside it; a session cannot start with the "
                f"animal at home"
            )
        if self.deployment is Deployment.OUT_OF_CAGE and self.fixed_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is not recorded as head-fixed, so "
                f"the session would carry no record of restraint; call head_fixed() "
                f"first (S8 §5.2)"
            )

    # --- restraint, which is recorded and bounds nothing ------------------

    def head_fixed(self, at: float) -> None:
        """Start the restraint clock.

        Recorded rather than bounding since 2026-09-19; `HEAD_FIXED`/`HEAD_RELEASED`
        (4128/4129) remain the durable record of restraint (S8 §5.2).
        """
        _finite("the time the animal was head-fixed", at)
        if self.fixed_at is not None and self.released_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is already recorded as head-fixed "
                f"at {self.fixed_at}; a second start would run two restraint clocks "
                f"and the shorter one would silently win"
            )
        self.fixed_at = at
        self.released_at = None

    def head_released(self, at: float) -> None:
        _finite("the time the animal was released", at)
        self.released_at = at

    def chair_seconds(self, now: float) -> float:
        """Restraint time so far. Zero before the animal is in the chair."""
        _finite("the session clock", now)
        if self.fixed_at is None:
            return 0.0
        end = self.released_at if self.released_at is not None else now
        return end - self.fixed_at

    # --- the session's own limit ------------------------------------------

    def must_stop(self, now: float) -> str | None:
        """Why this session must end, or `None`. **Never about fluid.**

        Returned rather than raised: a session ending on its ceiling is the design
        working, and it has a record to close, a map to write and a summary to
        report. An exception would make the correct ending look like a fault.

        **One limit, and no trial count** (PI, 2026-09-19) -- the parameter that
        carried one is gone rather than ignored, so nothing can pass a number here
        and believe it was weighed. `None` from `out_of_cage_seconds` is a
        cage-side session; a rig session with no mark raises there instead.

        **A closed interval is a stop, not a frozen clock** -- and a stop rather
        than a refusal, because a session that must end has a record to close.
        """
        if self.returned_at is not None:
            return (
                f"{OUT_OF_CAGE}: subject {self.bounds.subject!r} is recorded as back "
                f"in its cage at {self.returned_at}, so no further trial can be "
                f"inside the interval this session is bounded by"
            )
        seconds = self.out_of_cage_seconds(now)
        if seconds is None:
            return None
        ceiling = self.bounds.ceilings[OUT_OF_CAGE]
        if seconds > ceiling.value:
            return (
                f"{OUT_OF_CAGE}: subject {self.bounds.subject!r} has been out of "
                f"its cage {seconds:.0f} {ceiling.unit} against a ceiling of "
                f"{ceiling.value:.0f}"
            )
        return None


@dataclass
class Rig:
    """A trial's outbound I/O: the card, and the only path to the pump.

    What a task's `Mark` and `Reward` actions actually reach (`run.Effects`). It
    lives here rather than beside the loop so the whole route from a task's
    declaration to fluid is readable in one file.

    **Nothing is swallowed.** There is no fluid ceiling (PI, 2026-09-06), so the
    only way `deliver` fails is a pump that will not answer -- a broken rig, not the
    design working, and absorbing it would produce a session of correct trials
    nobody was paid for. An earlier version caught a ceiling here and stopped at the
    next trial boundary; the shape was right and the premise was not, and a
    *stopping* condition arriving mid-trial still belongs here rather than raising
    out of the frame loop.
    """

    card: object
    welfare: Welfare

    def mark(self, code: int) -> None:
        self.card.emit(code)

    def reward(self, ref: str) -> None:
        self.welfare.deliver(ref)
