"""Fluid and session-duration accounting, and the only path from a task to the pump.

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
and no state that outlives a question. This file has all three -- a running total, two
clocks, and a pump -- and joining them to the limits is the whole of its job.

**Fluid has a floor, not a ceiling** (PI, 2026-09-06). This file was written the
other way round first, and the difference matters: a fluid *ceiling* refuses a
delivery an animal earned and stops a session partway through, which under this
protocol withholds fluid to satisfy a limit nobody set. The daily figure is a
**minimum**, and what this module does with it is report at session close how much is
still owed, so a person can supplement it. **No delivery is ever refused on volume.**

**There is one duration limit, and it runs out of cage to back in cage** (PI,
2026-09-19): *"The only limit we have welfare wise is that a session from out of cage
to back into cage cannot be longer than 12 hours."* Twelve hours is the institutional
figure. It is **documented here and not configured here** -- no constant in this
module carries it, because a number with a name is a number something will default
to, and the real figure arrives with a real subject's bounded config.

Two things this ruling removed. **Chair time is no longer a ceiling**: it is still
recorded, because `HEAD_FIXED`/`HEAD_RELEASED` are the durable record of restraint
(S8 §5.2), but a clock that starts at head-fixation under-counts the limit by the
transport and chairing that precede it, and it is not what the limit is about. And
**there is no session-length maximum**: per-condition targets live in `scheduler`
(`Counts`, `owed()`, `upcoming()`) and always did, so `max_trials` said nothing a
task's own config did not say better.

Three things fail closed here, and none of them is fluid:

- **A missing floor refuses to start.** A bounded config lacking one is a config
  nobody finished, and a missing floor reads exactly like a floor of zero to anything
  that does not check -- so nobody would ever be told to supplement.
- **A missing mark refuses, rather than running unbounded.** `Deployment` is the
  whole of this: a session either declares that the animal left its cage -- and then
  must carry the mark and the ceiling that bound it -- or declares that the animal is
  home, cage-side, with no such interval to measure (S13). **The absence of a mark
  must never be the thing that disables a limit.** A rig session nobody marked looks
  exactly like a cage-side one to any code that answers zero, which is why
  `out_of_cage_seconds` refuses on every call rather than only at preflight.
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

**The out-of-cage marks have no event code yet, and that is an ask rather than an
oversight.** S8 §5.2's argument for coding head-fixation -- a clock with no hardware
record cannot survive a restart -- now applies with more force to this clock, since
it is the one that bounds the session. Allocating two codes is S2's and `wl-preproc`'s
to agree (ADR-0007), so it is asked of the PI rather than taken here. Until it is
answered, a restart loses this clock's start and a person has to supply it again;
nothing reconstructs chair time from the sync box today either.
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

    It is a declaration rather than an inference because the two cases are
    indistinguishable from the absence of a mark: a rig session where someone forgot
    to record the animal coming out of its cage has no out-of-cage time, and so does
    a cage-side one where the animal never left. Defaulting either way is wrong --
    one direction refuses every kiosk session, the other runs an unmarked rig session
    with no limit at all -- so the session says which it is, and `welfare` refuses
    what does not match.
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

    Millilitres, because millilitres are what the bounded config is denominated in and
    a unit conversion between the limit and the delivery is a place for a factor of
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
    #: Rig or cage-side. **Required, with no default**, so that every construction
    #: site states which welfare limits apply to it -- see `Deployment`.
    deployment: Deployment
    #: What this session has commanded. A **lower bound** on what the animal got
    #: (P17), which is why it is never used alone.
    commanded: float = 0.0
    #: The sync box's delivered-line figure for this session, when it is readable.
    #: `None` until one arrives; S8 open item 2 is whether that is continuous or only
    #: at session end, and this shape does not care which.
    delivered: float | None = None
    deliveries: int = 0
    #: The clock that bounds the session: when the animal came out of its home cage,
    #: and when it went back in. **Set these through `left_cage` and
    #: `returned_to_cage`, never by constructing a `Welfare` around them** -- the
    #: ordering and finiteness guards live on those methods, and a field passed to
    #: the constructor reaches none of them. In-repo callers only, and
    #: `out_of_cage_seconds` still refuses a non-finite or backwards result, so
    #: what a direct construction can hide is a wrong-but-ordered instant.
    left_cage_at: float | None = None
    returned_at: float | None = None
    #: The restraint clock. Recorded, and it bounds nothing (PI, 2026-09-19).
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
        declared = OUT_OF_CAGE in self.bounds.ceilings
        if self.deployment is Deployment.OUT_OF_CAGE and not declared:
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} has no "
                f"{OUT_OF_CAGE!r} ceiling, so a session out of the cage would be "
                f"unbounded; a missing limit is not an absent one"
            )
        if self.deployment is Deployment.ANIMAL_AT_HOME and declared:
            # The declaration and the config disagreeing is a limit switched off by
            # a flag, which is what the declaration exists to prevent -- reached
            # from the other side. One of the two is wrong and neither is safe to
            # prefer silently.
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} states an "
                f"{OUT_OF_CAGE!r} ceiling while this session declares the animal is "
                f"at home; a session cannot both have that interval and not have it"
            )

    # --- fluid ------------------------------------------------------------

    def session_total(self) -> float:
        """This session's contribution to the day, reconciled where possible.

        **Through `bounds.reconcile`, never by taking a maximum here.** Which of the
        two figures a total is computed from is a welfare rule with a written
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

    # --- out of cage, and back in -----------------------------------------

    def left_cage(self, seconds_ago: float, now: float) -> None:
        """Start the clock the session is bounded by (PI, 2026-09-19).

        **"How long ago", not "at what time", and the difference is the ruling.**
        The session clock (`taskd.Session.now`) is derived from frames and reads
        zero when the session object starts, so the animal leaving its cage -- which
        happened before any of this software ran -- sits at a *negative* instant in
        that base. A timestamp parameter invited a caller to pass zero, and `wlx
        run` did: out-of-cage time then equalled chair time, which is precisely the
        under-count this clock replaced chair time to remove. This shape cannot be
        got wrong that way, and it is the number an operator actually holds -- the
        animal came out of its cage twenty minutes ago.

        Four refusals, and each is a value that cannot be in this base:

        - **A cage-side session cannot leave a cage it never left.** The deployment
          already said so, and the two must not disagree.
        - **A value that is not a number is refused first**, before anything
          compares it (`bounds._finite`). NaN is not in the future, not past the
          ceiling and not backwards -- it is `False` against all three, so it walked
          through every guard below and left `left_cage_at` NaN, `must_stop`
          answering `None` for the whole session. Reproduced through `wlx run
          --out-of-cage-ago nan`, which ran four hundred rewarded trials with a
          clean summary and no limit at all.
        - **The future is refused.** Nothing left its cage after the software
          started asking.
        - **At or past the ceiling is refused**, which is also what catches a wall
          clock handed to a session-relative parameter: 1.79e9 seconds is
          fifty-seven years, not a transport. The bound is the session's own limit
          rather than a sanity constant, because a session already at twelve hours
          before its first frame must not start -- one refusal serves both readings.
          **At**, not past: an animal out for exactly the limit has no room for a
          trial, and `must_stop`'s own `>` then fires on the first pass that
          exceeds it rather than a trial later.
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
                f"re-armed either: one session is one time out of the cage, and an "
                f"animal that has gone home has finished this one"
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

        `at` is an instant on the session clock rather than a "how long ago",
        because unlike the opening mark this one is at or after the present -- there
        is a clock reading for it, and `taskd.Session.returned_to_cage` passes one.
        **The session clock stops when the frames do**, so a return marked well
        after the loop ended carries the loop's last reading unless the caller
        supplies a later one; that is a limit of a frame-derived clock and is named
        rather than papered over.

        **This closes an open interval and does nothing else.** Two unguarded lines
        stood here and every one of the refusals below was reachable: a return
        before the animal left gave a *negative* duration that passed every ceiling
        test, and a return marked mid-session froze the clock at the value it had --
        `must_stop` answering `None` for the rest of a session that reported itself
        fully marked. That is the same failure as a missing mark, reached with both
        marks present, which is why it is refused here and not merely checked later.
        """
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

        `None` -- never zero -- when the session declared the animal is at home,
        because a cage-side session has no such interval at all and a zero would
        read on a console as a clock that has not started yet.

        **A missing mark raises rather than answering zero.** An unmarked rig
        session is indistinguishable from a cage-side one to anything that answers
        a number, so answering one would let forgetting a mark disable the only
        duration limit there is. This is `dio.Absent`'s rule on the clock that
        bounds a session, and it refuses here rather than only at `preflight` so
        that no later caller can reach an unbounded answer.
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
        # **Checked on the computed duration, not only on the marks.** The marks
        # are guarded where they are taken, but this is the number every ceiling is
        # read against, and it is the last place a NaN can be caught before one is
        # compared -- from a `now` this method was handed, or from a `Welfare`
        # constructed field-by-field rather than marked (see `left_cage_at`).
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

        **`now` is passed rather than assumed zero.** This called
        `out_of_cage_seconds(0.0)`, which is right only because the default session
        clock starts at zero -- a `Session(clock=...)` with any other base would
        have had a legitimately-marked session refused for running backwards. It
        failed closed, so it was never going to hurt an animal; what it did was
        bake the zero-base assumption into a second place, and "how long ago"
        already depends on that assumption quietly enough in one.

        Called by `taskd.Session.run` before its first frame, so a missing mark is
        a refusal a person sees at the console rather than a fault partway into a
        session with an animal already in the chair.

        Two marks for a rig, and each refuses for its own reason. The out-of-cage
        one **bounds** the session, and `out_of_cage_seconds` is asked for it here
        rather than re-checked, so the rule has one home. Head-fixation **records**
        restraint: it stopped being a ceiling on 2026-09-19 and did not stop being
        what the event codes carry, and a rig session with no `HEAD_FIXED` in the
        stream has no record of restraint at all.

        **And the interval must still be open.** A session whose animal is already
        recorded as home is one whose limit is a fixed number that no trial can
        move -- fully marked, and bounding nothing. `returned_to_cage` refuses a
        return while the animal is head-fixed, so the marks cannot be closed *during*
        a run; this is the same hole reached before one starts.
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

        Recorded rather than bounding: chair time stopped being a ceiling on
        2026-09-19, and `HEAD_FIXED`/`HEAD_RELEASED` (4128/4129) remain the durable
        record of restraint that S8 §5.2 made them.
        """
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

    # --- the session's own limit ------------------------------------------

    def must_stop(self, now: float) -> str | None:
        """Why this session must end, or `None`. **Never about fluid.**

        Returned rather than raised: a session ending on its ceiling is the design
        working, and it has a record to close, a map to write and a summary to
        report. An exception would make the correct ending look like a fault.

        **One limit, and no trial count** (PI, 2026-09-19). The parameter that
        carried one is gone rather than ignored, so that nothing can pass a number
        here and believe it was weighed.

        `None` from `out_of_cage_seconds` is a cage-side session, which the PI gave
        no time-based limit; a rig session with no mark raises there rather than
        reaching this line.

        **A closed interval is a stop, not a frozen clock.** If the animal is
        recorded as home, every further trial would be outside the interval this
        session is bounded by, and the clock would sit at whatever it read when the
        mark landed -- a limit that cannot be reached because it cannot move.
        `returned_to_cage` refuses while the animal is head-fixed, so a rig loop
        cannot reach this; it is here because a limit that can be switched off by a
        sequence of legal calls is not a limit, and because this is the branch that
        is right whatever future call order arrives. It is a **stop reason rather
        than a refusal** for this method's own reason: a session that must end has
        a record to close.
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
