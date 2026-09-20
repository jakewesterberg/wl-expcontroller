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
  **Both ends of that interval are wall-clock times** (PI, 2026-09-20): the frame clock
  stops when the frames do, so a return read from it left the unchairing and the walk
  back outside the limit. **The session warns as the limit approaches** (PI,
  2026-09-20) so a block can be finished deliberately rather than cut mid-sequence --
  `approaching_limit`, at `WARN_WITHIN_DEFAULT`, which he accepted the same day as a
  starting value.
- **Either mark more than thirty minutes from now is confirmed by a person** (PI,
  2026-09-20), or amended with a reason and a name. They are clock times, so a
  nine-hour typo passes every refusal there is; `departure_needs_confirmation`,
  `return_needs_confirmation` and `amend_mark` are the mitigation, the marks
  themselves refuse an unconfirmed one, and `CONFIRM_MARK_WITHIN` is his figure.
- **Three deployment kinds, not two** (PI, 2026-09-20): head-fixation is a property
  of the deployment rather than of being on a rig. **S8 §5.2 item 4 has the table**
  of which marks each kind requires, refuses and event-codes; the one thing to carry
  away here is that `chair_seconds` is **absent, never zero**, for a kind that takes
  no head-fixation marks.
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
marks get no event code** -- PI, 2026-09-20, closing S8 open item 8: they are
operator-entered rather than measured, so a hardware timestamp would add precision to
a number that never had it, and our own log and the session directory already carry
them. A restart therefore re-asks a person for the departure time, by design.
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

#: How long before the `out_of_cage` ceiling a session starts saying so, in seconds.
#: **Thirty minutes. Accepted by the PI on 2026-09-20 as a starting value** -- his
#: ruling, not an implementer's choice, which is the difference between a number an
#: operator sees and a number somebody guessed.
#:
#: **It is still derived from no measurement of this system, and that is why it is a
#: *starting* value rather than a settled one.** No block duration has been measured
#: and nothing under `docs/measurements/` states one, so nothing here claims it clears
#: a block. S8 §5.2 item 4 carries the reasoning, what it is not claiming, and why this
#: may have a named default where the twelve-hour ceiling may not.
#: `Welfare.warn_within` is where a lab sets its own.
WARN_WITHIN_DEFAULT = 1_800.0

#: How far from the current time either welfare mark may be before a **person** has to
#: say so, in seconds.
#:
#: **Thirty minutes, and it is the PI's number rather than a derived one** (PI,
#: 2026-09-20): *"if a number is input that is more than 30 min from the current time,
#: a warning should appear that the experimenter must click through to confirm."* It
#: is not a twenty-fourth of anything and nothing here computes it, so it may not be
#: re-derived from the ceiling -- a session under a shorter ceiling keeps this
#: threshold and simply has no band (see `departure_needs_confirmation`).
#:
#: **It is 1,800 and so is `WARN_WITHIN_DEFAULT`, and the two are unrelated.** Both
#: are the PI's since 2026-09-20 and they still are not the same number twice: that one
#: is a *starting* value for a line that bounds nothing and may be tuned by any lab;
#: this one is a threshold on a mark that bounds a session. Deriving either from the
#: other would make tuning a console warning quietly move a welfare guard, so they are
#: separate constants that happen to agree. S8 §5.2 item 4 carries both rulings.
#:
#: **It applies to both marks** (PI, 2026-09-20, ruling 4): the return is a clock time
#: too, and one typed hours ago moves the same interval, in the direction that makes a
#: session look shorter than it was. It was `CONFIRM_DEPARTURE_WITHIN` for the few hours
#: the departure was the only clock-time mark.
CONFIRM_MARK_WITHIN = 1_800.0


class Deployment(Enum):
    """Where the animal is for this session, and what that means it can be marked
    with. **Required, with no default.**

    A declaration rather than an inference: a rig session nobody marked and a
    cage-side one with nothing to mark are indistinguishable to anything that
    answers zero. Defaulting either way is wrong, so the session says which it is
    and `welfare` refuses what does not match (S13 §4.0).

    **Three kinds since 2026-09-20 (PI)**, because head-fixation is a property of
    the deployment and not of being on a rig. **S8 §5.2 item 4 has the table** --
    which marks each kind requires, refuses, and event-codes -- and it is there
    rather than here because a copy of it in both places is a copy that can disagree,
    which is how three of this round's four documentation defects happened.

    The one sentence that must not be re-derived from the table: **a
    chaired-but-unfixed animal *is* restrained**; what it has no marks for is
    head-fixation. So `chair_seconds` answers `None` rather than `0.00` wherever
    nothing marks restraint -- a restrained session reporting zero restraint is
    `shortfall()` answering `0` for a day nobody measured, in another costume.
    """

    #: A rig session: the animal left its home cage, was transported, chaired and
    #: head-fixed. The twelve-hour clock binds it, and it must carry both marks.
    RIG_FIXED = "rig_fixed"

    #: A rig session with no head-fixation -- a chaired animal working at a screen.
    #: The twelve-hour clock binds it exactly as above, and it carries the
    #: out-of-cage mark; it has no restraint marks, so it reports no restraint time.
    RIG_CHAIRED = "rig_chaired"

    #: A cage-side kiosk session (S13): the animal never left home, so there is no
    #: out-of-cage event, no head-fixation, and **no duration bound** -- which the PI
    #: chose, and which this member is how a session states rather than acquires.
    CAGE_SIDE = "cage_side"


#: The kinds where the animal left its home cage, and which the twelve-hour ceiling
#: therefore binds. A tuple rather than a method on `Deployment`, so that the whole
#: three-way behaviour of this file is readable as `is` and `in` against S8 §5.2
#: item 4's table and nothing dispatches.
_OUT_OF_THE_CAGE = (Deployment.RIG_FIXED, Deployment.RIG_CHAIRED)


class Pump(Protocol):
    """Whatever turns a volume into fluid in front of the animal.

    Millilitres, because that is what the bounded config is denominated in: a unit
    conversion between the limit and the delivery hides a factor of sixty.
    """

    def deliver(self, ml: float) -> None: ...


class Card(Protocol):
    """Whatever puts an event code on a wire -- `dio.Simulated`, or a real card.

    A structural type rather than an import, for the reason `Pump` is one: this
    module has no hardware in it and `dio` is not a dependency of the welfare path.
    `Rig.card` was annotated `object` until 2026-09-20, which the entry-point
    enumeration could not classify -- an annotation naming no type is a door its
    tripwire cannot see, whatever it happens to hold today.
    """

    def emit(self, code: int) -> None: ...


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
    #: The **wall-clock** instant of the same departure, kept as the anchor the
    #: return is mapped against (PI, 2026-09-20, ruling 4). Set by `left_cage` and by
    #: nothing else; `returned_to_cage` refuses when it is absent, because a
    #: clock-time return has no interval to close without it.
    left_cage_wall_at: float | None = None
    returned_at: float | None = None
    #: The restraint clock. Recorded, and it bounds nothing (PI, 2026-09-19). Only
    #: `Deployment.RIG_FIXED` can carry these at all.
    fixed_at: float | None = None
    released_at: float | None = None
    #: How close to the `out_of_cage` ceiling `approaching_limit` starts saying so,
    #: in seconds. See `WARN_WITHIN_DEFAULT` -- including why a warning threshold may
    #: have a default where the limit itself may not. Zero means never warn.
    warn_within: float = WARN_WITHIN_DEFAULT
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
        _magnitude("the out-of-cage warning threshold", self.warn_within)
        declared = OUT_OF_CAGE in self.bounds.ceilings
        if self.deployment in _OUT_OF_THE_CAGE and not declared:
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} has no "
                f"{OUT_OF_CAGE!r} ceiling, so a session out of the cage would be "
                f"unbounded; a missing limit is not an absent one"
            )
        if self.deployment is Deployment.CAGE_SIDE and declared:
            # A limit switched off by a flag -- what the declaration exists to
            # prevent, reached from the other side.
            raise Exceeded(
                f"the bounded config for subject {self.bounds.subject!r} states an "
                f"{OUT_OF_CAGE!r} ceiling while this session declares the animal is "
                f"at home; a session cannot both have that interval and not have it"
            )
        # **And no refusal for a threshold wider than the ceiling**, which was
        # written and removed on 2026-09-20. It would have made every short-ceiling
        # config -- `tasks/reference_bounds.py`'s deliberately implausible ten
        # minutes among them -- refuse to construct a `Welfare` at all, and a
        # placeholder limit turning `wlx run` into a hard failure is a worse outcome
        # than a warning that is on for the whole of a ten-minute session. It is also
        # not nonsense there: a session whose entire allowance is under the threshold
        # genuinely is inside it throughout. This is a warning, not a limit, so the
        # only guard it earns is the one above.

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

    def left_cage(
        self, at: float, wall_now: float, now: float, confirmed: bool = False
    ) -> None:
        """Start the clock the session is bounded by (PI, 2026-09-19).

        **At what time, and the mapping between the two clocks lives here** (PI,
        2026-09-20). `at` and `wall_now` are wall-clock instants in POSIX seconds --
        a clock time is what an operator reads, and 9,143 seconds ago is not. `now`
        is the frame-derived session clock, which reads zero at the start, so the
        departure lands at a *negative* instant in that base and transport and
        chairing are inside the interval. Doing that arithmetic here rather than in a
        caller is the point: a caller that computed `seconds_ago` itself is a second
        place for the two bases to meet, and the first one passed a plain zero.

        **This parameter was `seconds_ago` until 2026-09-20, and the change cost a
        guard the PI was shown and accepted.** S8 §5.2 item 4 has that account: what
        the ceiling refusal used to double as, why a clock time cannot be refused the
        same way, and why the computed interval is therefore printed in front of the
        operator at session start (`cli.main`) rather than only bounded.

        Refused: a cage-side deployment (it never left); any of the three readings
        not being a real number, and the interval computed from two of them likewise
        (S8 §5.2c); a departure in the future; one **at or past** the ceiling, which
        is *at* because an animal out for exactly the limit has no room for a trial;
        and one more than `CONFIRM_MARK_WITHIN` ago that `confirmed` does not
        say a person acted on.

        **`confirmed` is on the mark rather than only on the caller** (PI,
        2026-09-20), and that is the CLAUDE.md rule rather than belt and braces:
        `wlx run` asks a person, but `taskd.Session.left_cage` is a console action
        and the console P4d-2 adds would otherwise reach around the prompt entirely.
        A caller can lie to this flag; it cannot forget it.
        """
        if self.deployment is Deployment.CAGE_SIDE:
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
        _finite("the time this subject left its cage", at)
        _finite("the wall clock this session is reading", wall_now)
        _finite("the session clock", now)
        # The interval is a third value computed from two checked ones, which S8
        # §5.2c names as a door no enumeration of parameters can close.
        seconds_ago = wall_now - at
        _finite("the time since this subject left its cage", seconds_ago)
        if seconds_ago < 0.0:
            raise Exceeded(
                f"subject {self.bounds.subject!r} cannot have left its cage "
                f"{-seconds_ago:.0f} seconds in the future; the departure is a "
                f"clock time, and this one is later than the clock this session is "
                f"reading. A bare time is today's date on this host -- give the "
                f"date too if the animal came out yesterday"
            )
        ceiling = self.bounds.ceilings[OUT_OF_CAGE]
        if seconds_ago >= ceiling.value:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is recorded as out of its cage "
                f"{seconds_ago} {ceiling.unit} ago, against a ceiling of "
                f"{ceiling.value:.0f}; a session cannot start at or outside the "
                f"limit it is bounded by, because its first trial is already past "
                f"it. Check the date and the hour -- a departure typed a day early, "
                f"or in the wrong half of the day, lands here"
            )
        # Last, so every refusal above still speaks first: a confirmation offered
        # for something about to be refused teaches an operator that the prompt is
        # what stands between them and a run.
        self._refuse_unconfirmed(
            self.departure_needs_confirmation(at, wall_now), confirmed
        )
        self.left_cage_at = now - seconds_ago
        # **The wall instant of the departure, kept so the return can be a clock
        # time too** (PI, 2026-09-20, ruling 4). `returned_to_cage` maps its own
        # wall reading against *this* anchor rather than against a fresh
        # `now`/`wall_now` pair, because the session clock stops when the frames do
        # and the two bases stop being the same instant the moment the loop ends --
        # which is precisely the interval that ruling exists to start counting.
        self.left_cage_wall_at = at

    def _far_from_now(self, what: str, at: float, wall_now: float) -> str | None:
        """The one copy of "is this mark far enough from now to need a person".

        **PI, 2026-09-20**: more than thirty minutes from the current time and the
        experimenter confirms it, or amends it. It is the mitigation for the guard he
        accepted losing when the marks became clock times -- `08:45` typed for `18:45`
        is nine hours, and no refusal will ever catch it (S8 §5.2 item 4).

        A string and never an exception, like `must_stop` and `approaching_limit`: a
        far mark is not wrong, it is unverified, and a caller's job is to get a
        person's act on it rather than to fail. **It moves nothing**, so the two
        public forms can be asked *before* the mark -- which is where they must be
        asked, since neither mark can be re-armed and an amendment would then have
        nowhere to go.

        A mark in the future needs no confirmation because both marks refuse one
        outright; the same is true of a departure past the ceiling, which
        `departure_needs_confirmation` takes out of the band for that reason.
        """
        _finite(f"the {what} time given for this subject", at)
        _finite("the wall clock this session is reading", wall_now)
        seconds_ago = wall_now - at
        _finite(f"the time since the {what} this subject is marked with", seconds_ago)
        if seconds_ago <= CONFIRM_MARK_WITHIN:
            return None
        return (
            f"the {what} given for subject {self.bounds.subject!r} is "
            f"{seconds_ago:.0f} s before the clock this session is reading, which is "
            f"further back than the {CONFIRM_MARK_WITHIN:.0f} s a session takes "
            f"on trust (PI, 2026-09-20). Confirm it, or amend it with a reason -- an "
            f"hour typed in the wrong half of the day sits inside every limit there "
            f"is and nothing else will catch it"
        )

    def departure_needs_confirmation(self, at: float, wall_now: float) -> str | None:
        """What a person must be shown before this departure is marked, or `None`.

        **Outside the band on both sides it answers `None`**, so the two existing
        refusals stand untouched: a departure in the future and one at or past the
        ceiling are refused outright by `left_cage`, and offering to confirm either
        would teach an operator that the prompt is the only thing between them and a
        run. A cage-side session has no departure at all.

        The threshold is `CONFIRM_MARK_WITHIN` and is not derived from the
        ceiling, so a config whose ceiling is shorter than thirty minutes -- which
        `tasks/reference_bounds.py`'s ten-minute placeholder is -- simply has an empty
        band, and every departure it would ask about is refused instead.
        """
        if self.deployment is Deployment.CAGE_SIDE:
            return None
        sentence = self._far_from_now("departure", at, wall_now)
        if sentence is None:
            return None
        if wall_now - at >= self.bounds.ceilings[OUT_OF_CAGE].value:
            return None
        return sentence

    def return_needs_confirmation(self, at: float, wall_now: float) -> str | None:
        """The same question on the closing mark (PI, 2026-09-20, ruling 4).

        **The same thirty minutes and the same amendment path**, because a return
        typed hours ago moves the same interval and in the direction that makes a
        session look shorter than it was. There is no ceiling clause here: a return
        is not refused for being long ago -- `must_stop` reports the interval it
        produces -- so the band has one edge rather than two.
        """
        if self.deployment is Deployment.CAGE_SIDE:
            return None
        return self._far_from_now("return", at, wall_now)

    def _refuse_unconfirmed(self, sentence: str | None, confirmed: bool) -> None:
        """Turn "a person should see this" into "a person did", or refuse.

        **The confirmation is enforced on the marks rather than only in `wlx run`**,
        which is CLAUDE.md's rule and not caution: the departure prompt has a consumer
        and the return has none until the console gains the action, and a guardrail
        written now and wired later is how `bounds`' fluid check went a week called by
        nothing. A caller can lie to `confirmed`; it cannot forget it.
        """
        if sentence is None or confirmed:
            return
        raise Exceeded(
            f"{sentence}. It was not confirmed by anyone, so it is refused rather "
            f"than taken: a mark this far from the clock is a person's to confirm or "
            f"amend (PI, 2026-09-20), and a confirmation nobody made is worse than "
            f"no confirmation at all"
        )

    def amend_mark(
        self, what: str, original: float, amended: float, reason: str, by: str
    ) -> None:
        """A person changing one of the two marks before it is taken (PI, 2026-09-20).

        *"There should also be an option to update the time if necessary, but a
        reason should be given and the experimenter name logged."* Both are required
        with no default and no blank: a row saying somebody moved a clock that bounds
        a session, for no stated cause and under no name, answers none of the
        questions it would be read for months later.

        **One method for both marks** rather than one per mark, so the reason and the
        actor are required identically and there is no second copy to drift. `what`
        is the mark's name as an operator would say it -- `"departure"` or
        `"return"` -- and reaches nothing but the message and the note.

        **This records; the mark is taken afterwards.** Called first, so a refusal
        here lands before the mark rather than after it: neither mark can be re-armed,
        so an amendment refused afterwards would leave a session bounded by the value
        it was meant to replace with no way back. `original` and `amended` are
        wall-clock instants and both are checked, because this runs before `left_cage`
        or `returned_to_cage` sees either and on no other authority.

        **The durable half is the caller's**, and deliberately so: at this moment
        `taskd` has not opened the session record, and writing it here would put a
        file path in the welfare-critical file. `record.welfare_note` writes the row;
        `notes` is this object's own account of it, for the session summary.
        """
        _finite(f"the {what} time being amended", original)
        _finite(f"the amended {what} time", amended)
        if not reason.strip():
            raise Exceeded(
                f"the {what} time for subject {self.bounds.subject!r} was amended "
                f"with no reason given, so it is refused rather than recorded blank; "
                f"a row that says a welfare clock was moved and not why answers "
                f"nothing anyone will ask it"
            )
        if not by.strip():
            raise Exceeded(
                f"the {what} time for subject {self.bounds.subject!r} was amended "
                f"by nobody, so it is refused; the clock this session is bounded by "
                f"is not something a person changes anonymously, for the reason a "
                f"console write is refused without --as WHO"
            )
        self.notes.append(("mark amended", what, original, amended, reason, by))

    def returned_to_cage(
        self, at: float, wall_now: float, confirmed: bool = False
    ) -> None:
        """Close the interval: the animal is home, and this session is over.

        **`at` is a wall-clock instant in POSIX seconds, like the departure** (PI,
        2026-09-20, ruling 4), and **the symmetry is the point**. It was an instant on
        the session clock until then, and that clock is frame-derived: it stops when
        the frames do. So an operator who ended a session, unchaired the animal,
        walked it back and *then* marked the return recorded the animal as home at
        the instant the loop ended -- the unchairing and the walk back, minutes of an
        animal out of its cage, fell outside the twelve hours. With both ends of the
        interval read from the wall, the frame clock stopping no longer matters.

        **The mapping is against `left_cage`'s anchor, not against a fresh
        `now`/`wall_now` pair.** Those two are the same instant only while the loop is
        running; once it ends the session clock is frozen and the wall clock is not,
        and a mapping built on them would drop exactly the interval this ruling exists
        to count. `left_cage_wall_at` is that anchor.

        **Every refusal it already had is preserved**, now read against wall instants:
        nothing to close, a second return, an animal still head-fixed, a return before
        the departure. Two are new and both are the departure's: a return **in the
        future**, which is a mark nothing could have taken, and one more than
        `CONFIRM_MARK_WITHIN` ago that no person confirmed.

        **It also closes the session** (PI, 2026-09-20): out and back is one session,
        so `left_cage` refuses to re-arm. S8 §5.2 item 4 has the ruling and the
        consequence he accepted.
        """
        _finite("the time the animal went back into its cage", at)
        _finite("the wall clock this session is reading", wall_now)
        if self.deployment is Deployment.CAGE_SIDE:
            raise Exceeded(
                f"this session declares subject {self.bounds.subject!r} is at home, "
                f"so there is no interval for a return to close"
            )
        # **Both, not just the session-base one.** A `Welfare` constructed around
        # `left_cage_at` directly has no wall anchor, and there is no interval a
        # clock-time return could close without one -- so it is the same refusal
        # rather than a `TypeError` five lines down.
        if self.left_cage_at is None or self.left_cage_wall_at is None:
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
        if at > wall_now:
            raise Exceeded(
                f"subject {self.bounds.subject!r} cannot be back in its cage "
                f"{at - wall_now:.0f} seconds in the future; the return is a clock "
                f"time, and this one is later than the clock this session is reading"
            )
        if at < self.left_cage_wall_at:
            raise Exceeded(
                f"subject {self.bounds.subject!r} cannot be back in its cage at {at} "
                f"having left it at {self.left_cage_wall_at}; a negative duration is "
                f"not a duration, and an interval that runs backwards bounds nothing"
            )
        self._refuse_unconfirmed(
            self.return_needs_confirmation(at, wall_now), confirmed
        )
        # Mapped through the departure, which is the one place the two bases were
        # read at the same instant -- see this method's docstring. The result is a
        # third value computed from checked ones, so it is checked (S8 §5.2c).
        returned_at = self.left_cage_at + (at - self.left_cage_wall_at)
        _finite("the time the animal went back into its cage", returned_at)
        self.returned_at = returned_at

    def out_of_cage_seconds(self, now: float) -> float | None:
        """How long the animal has been out of its home cage.

        `None` -- never zero -- for a cage-side session: there is no such interval,
        and a zero reads on a console as a clock that has not started.

        **A missing mark raises rather than answering zero**, and raises on every
        call rather than only at `preflight`, because an unmarked rig session is
        indistinguishable from a cage-side one to anything that answers a number.
        `dio.Absent`'s rule, on the clock that bounds a session.
        """
        if self.deployment is Deployment.CAGE_SIDE:
            return None
        if self.left_cage_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is not recorded as out of its "
                f"cage, so the session's one duration limit has no start; call "
                f"left_cage(), or declare Deployment.CAGE_SIDE if the animal "
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
        `out_of_cage_seconds`, so that refusal has one home), an interval still
        **open** (a session whose animal is recorded home is bounded by a number no
        trial can move), and **head-fixation for the kind that has it**.

        **Head-fixation is asked of `RIG_FIXED` only** (PI, 2026-09-20). It was a
        blanket rig requirement until then, which made a chaired-but-unfixed session
        impossible to declare and therefore impossible to run honestly. It is still
        required where the deployment says the marks exist, for the reason it always
        was: a session with neither code in the stream would carry no record of a
        restraint that happened.

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
        if self.deployment is Deployment.RIG_FIXED and self.fixed_at is None:
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

        **Refused unless the deployment says these marks exist** (PI, 2026-09-20).
        The declaration binds in both directions, as it already does for the
        out-of-cage mark: without this, `chair_seconds` answering `None` for the
        other two kinds would be *discarding* a measurement somebody took rather than
        reporting one nobody could take. A cage-side session could be recorded as
        head-fixed until this existed, and nothing anywhere disagreed.
        """
        _finite("the time the animal was head-fixed", at)
        if self.deployment is not Deployment.RIG_FIXED:
            raise Exceeded(
                f"this session declares subject {self.bounds.subject!r} is "
                f"{self.deployment.value}, which takes no head-fixation marks, so "
                f"the animal cannot be recorded as fixed; the declaration and the "
                f"mark disagree and neither is safe to prefer"
            )
        if self.fixed_at is not None and self.released_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is already recorded as head-fixed "
                f"at {self.fixed_at}; a second start would run two restraint clocks "
                f"and the shorter one would silently win"
            )
        self.fixed_at = at
        self.released_at = None

    def head_released(self, at: float) -> None:
        """Stop the restraint clock. **Refused where `head_fixed` is** (PI,
        2026-09-20), because the two are one record and guarding only the opening
        mark leaves the closing one reachable: `taskd.Session.head_released` strobes
        `HEAD_RELEASED`, so a console action wired straight to it would put a 4129 in
        a stream that never carried a 4128.

        **Three refusals, and the first version had only the deployment one** -- a
        `RIG_FIXED` session never fixed still accepted a release, which is the same
        4129-with-no-4128 by a second route and additionally made `chair_seconds`
        answer `0.00` for it. *Which* deployment this is, *whether* there is anything
        to release, and *when* relative to the fixation: the closing mark gets what
        `returned_to_cage` already had.
        """
        _finite("the time the animal was released", at)
        if self.deployment is not Deployment.RIG_FIXED:
            raise Exceeded(
                f"this session declares subject {self.bounds.subject!r} is "
                f"{self.deployment.value}, which takes no head-fixation marks, so "
                f"the animal cannot be recorded as released; a HEAD_RELEASED with no "
                f"HEAD_FIXED before it is a restraint record for restraint nothing "
                f"marked"
            )
        if self.fixed_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is not recorded as head-fixed, so "
                f"there is nothing to release; a release on its own strobes a "
                f"HEAD_RELEASED into a stream with no HEAD_FIXED in it, and leaves "
                f"the restraint clock reading zero rather than absent"
            )
        if at < self.fixed_at:
            raise Exceeded(
                f"subject {self.bounds.subject!r} cannot have been released at {at} "
                f"having been head-fixed at {self.fixed_at}; a negative duration is "
                f"not a duration, and a restraint record that runs backwards records "
                f"no restraint"
            )
        self.released_at = at

    def chair_seconds(self, now: float) -> float | None:
        """Head-fixation time so far, or `None` where nothing measures it.

        **`None` for `RIG_CHAIRED` and `CAGE_SIDE`, never `0.00`** (PI, 2026-09-20).
        The two have different reasons and the same answer: a cage-side animal is
        never restrained, and a chaired one *is* restrained and simply has no
        head-fixation marks. A restrained session reporting zero restraint is
        `shortfall()` answering `0` for a day nobody measured, wearing another
        costume -- a welfare quantity reported as a measured zero by something that
        measured nothing. Callers say which reason on screen (`cli.render`); this
        says only that there is no number.

        Zero *is* the answer for a `RIG_FIXED` session before head-fixation: that
        kind takes the marks, and none has been taken, so no restraint has happened
        yet. `preflight` refuses to start such a session anyway.

        **Guarded on the computed interval, not only on `now`** -- `out_of_cage_
        seconds`' rule, which this did not have until 2026-09-20. It checked `now`,
        which is not the quantity: `head_fixed(500)` then `head_released(100)` were
        both finite, both accepted, and this returned `-400.0`, which reached the
        wire and rendered `chair: -1:53:20`. It is also the whole basis on which
        `tests/test_welfare.py` exempts `fixed_at` and `released_at` from its
        entry-point enumeration, and that exemption named `now` while the guard was
        looking at it.
        """
        _finite("the session clock", now)
        if self.deployment is not Deployment.RIG_FIXED:
            return None
        if self.fixed_at is None:
            return 0.0
        end = self.released_at if self.released_at is not None else now
        seconds = end - self.fixed_at
        _finite("the time in the chair", seconds)
        if seconds < 0.0:
            # The marks are guarded, so the only way here is a field assigned
            # directly or a `now` in a base the mark was not taken in -- the same
            # two routes `out_of_cage_seconds` names, and the reason both check
            # their own result as well as their inputs (S8 §5.2c).
            raise Exceeded(
                f"the restraint clock for subject {self.bounds.subject!r} reads "
                f"{seconds:.0f} s: {end} is before the animal was head-fixed at "
                f"{self.fixed_at}. A duration that runs backwards is not a shorter "
                f"restraint, and it is reported as one"
            )
        return seconds

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

    def approaching_limit(self, now: float) -> str | None:
        """How little of the out-of-cage interval is left, once it is worth saying.

        **PI, 2026-09-20: warn as the twelve-hour limit approaches**, so an operator
        can finish a block deliberately rather than have a session cut mid-sequence.
        The console showed the clock and nothing drew attention as it ran out, which
        made the limit arrive as an interruption instead of as a deadline.

        A string like `must_stop`, and never an exception, for the same reason: this
        is the design working. It is `None` for a cage-side session (no bound to
        approach), `None` while more than `warn_within` is left, and `None` again
        once the limit is past -- there `must_stop` speaks, and a warning beside a
        stop would read as though a choice were still open. `warn_within` of zero
        therefore never warns, which is how the warning is switched off.

        **This bounds nothing**, which is why `warn_within` may have a default at all
        (`WARN_WITHIN_DEFAULT`): whatever it is set to, the session ends at the same
        instant.
        """
        seconds = self.out_of_cage_seconds(now)
        if seconds is None:
            return None
        ceiling = self.bounds.ceilings[OUT_OF_CAGE]
        # Two guarded, non-negative, finite values, so the difference is finite too;
        # checked anyway because §5.2c's standing lesson is that a computed third
        # value is a door, and this one is read against a threshold.
        remaining = ceiling.value - seconds
        _finite("the time left out of the cage", remaining)
        if remaining <= 0.0 or remaining > self.warn_within:
            return None
        return (
            f"{OUT_OF_CAGE}: subject {self.bounds.subject!r} has {remaining:.0f} "
            f"{ceiling.unit} left of its {ceiling.value:.0f} {ceiling.unit} out of "
            f"the cage; finish the block and start bringing the animal back"
        )


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

    card: Card
    welfare: Welfare

    def mark(self, code: int) -> None:
        self.card.emit(code)

    def reward(self, ref: str) -> None:
        self.welfare.deliver(ref)
