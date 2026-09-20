"""The bounded config: what a task cannot express and a console cannot exceed.

**Welfare-critical. Human review required before merge** (CLAUDE.md, S8 §7). Pure:
the limits, and the arithmetic of whether a number is past one or short of it. No
clock, no hardware, no state outliving a question -- `welfare.py` has all three.

**S8 §5.2b, §5.2c and §5.2d carry the arguments.** §5.2d indexes every refusal in
this file and in `welfare.py` to the failure it was written against, so "is this one
earned?" is a lookup.

- **Fluid has a floor, not a ceiling** (PI, 2026-09-06). The daily figure is a
  minimum topped up by hand after the session, so nothing here caps earned reward and
  no delivery is refused on volume. This file was built the other way round until
  then, and refused deliveries an animal had earned.
- **`Ceiling` and `Floor` are different types**, because they were the same one when
  the daily figure came to be compared with `>`. A `Floor` cannot be passed to `set`;
  a `Ceiling` cannot be asked for a shortfall.
- **A task cannot name a magnitude at all**: `Reward` takes the name of an entry here
  and the type refuses a number (S1 §2.3), so the guardrail is what a task can
  *express* rather than what review notices -- which matters because the task was
  probably written by a model (P15).
- **A console may move a value within its ceiling and not past it**, and **checking
  and moving are two calls** (`validate`, then `set`) because they happen at two
  moments -- see `validate`.
- **An unknown daily total leaves the shortfall unknown** rather than answering zero.
  Not a refusal to deliver, a refusal to *claim*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class Exceeded(ValueError):
    """A value or a delivery would go past a ceiling. Never caught internally."""


def _finite(what: str, value: float) -> None:
    """An **instant** entering the welfare path: refused unless it is a real number.

    **`nan` and `inf` defeat ordered comparisons in opposite ways** -- one is `False`
    against every one of them, the other unreachable, so `seconds > inf` is `False`
    for every real duration and an `inf` ceiling is never exceeded. Both were
    measured running a full reward-delivering session with no limit at all (S8
    §5.2c). An earlier version of this docstring called `inf` safe; that was false,
    and only the *mark* route ever refused it.

    `math.isfinite`, which `calibration._yaml_float` already uses: a second spelling
    of "is this a number" is a second thing to keep in step. See `_magnitude` for the
    stronger rule volumes, durations and limits get.
    """
    if not math.isfinite(value):
        raise Exceeded(
            f"{what} is {value!r}, which is not a real number: it defeats the "
            f"comparisons every limit is enforced with, so the bound it belongs to "
            f"would be switched off rather than exceeded"
        )


def _magnitude(what: str, value: float) -> None:
    """A **magnitude** entering the welfare path: finite, and not negative.

    Volumes, durations and the limits on them are quantities of something, and every
    guard here compares them with `>` -- so a negative value passes them all in the
    way `nan` does. Measured: `--set reward_correct=-0.5` commanded twenty rewards of
    -0.5 mL to the pump (S8 §5.2c).

    **The assumption, stated so a future entry can push back rather than find a hole:
    every bounded quantity in this system is a magnitude.** A stimulation amplitude
    needing a sign would want its own type.

    **Zero is allowed, and that is not an exception.** Zero is a quantity; this
    refuses things that are not. A reward volume of zero is permitted by the PI
    (2026-09-20) because it is visible -- a policy choice on top of this rule, with
    its own condition, not a gap in it. S8 §5.2c.
    """
    _finite(what, value)
    if value < 0.0:
        raise Exceeded(
            f"{what} is {value!r}, and a quantity of fluid or of time cannot be "
            f"negative; a negative dose is not a smaller dose, and it passes every "
            f"limit here because they all compare with `>`"
        )


class Unknown(RuntimeError):
    """A figure cannot be computed, so it cannot be claimed.

    Retained rather than deleted: a distinct type is what lets a caller tell "we do
    not know" from "the answer is zero".
    """


@dataclass(frozen=True, slots=True)
class Ceiling:
    """A current value and the most it may ever be set to.

    Two numbers rather than one because the *setting* is routine and the *limit* is
    not: reward volume moves between sessions without ceremony, and the maximum is
    not an experimenter's to move while a session runs.

    **A maximum is one of two kinds of limit and this type does not distinguish
    them** (PI, 2026-09-19): a **protocol figure**, which changes when the protocol
    does, or a **fault bound** set far above anything a protocol would ask for, so
    that what it refuses is software commanding an impossible quantity rather than an
    animal earning a ration. Both are enforced identically, so a bounded config says
    at each entry which kind its maximum is.
    """

    value: float
    maximum: float
    unit: str

    def __post_init__(self) -> None:
        """**A limit that is not a magnitude is not a limit** (`_magnitude`).

        Here rather than only at the call sites because a bounded config builds these
        directly -- it is Python (ADR-0006) -- which is the route a review used to
        reach `welfare.must_stop` with a NaN ceiling.
        """
        _magnitude("a ceiling's value", self.value)
        _magnitude("a ceiling's maximum", self.maximum)


@dataclass(frozen=True, slots=True)
class Floor:
    """A daily minimum the animal must reach, however it reaches it.

    One number rather than two, because a floor has no "most it may be set to": the
    thing a protocol states is the minimum itself, and a maximum on a minimum is a
    quantity nobody has a name for.
    """

    value: float
    unit: str

    def __post_init__(self) -> None:
        """A floor that is not a magnitude is not a floor either (`_magnitude`).

        Less dangerous than a bad ceiling -- nothing stops, since no delivery is
        refused on volume -- but `shortfall()` would answer `nan` where a person
        reads the figure they supplement against.
        """
        _magnitude("a floor's value", self.value)


@dataclass
class Bounds:
    subject: str
    ceilings: dict[str, Ceiling] = field(default_factory=dict)
    #: Daily minima. Separate from `ceilings` so the two cannot be confused at a call
    #: site, which is how the daily fluid figure came to be enforced as a limit.
    minima: dict[str, Floor] = field(default_factory=dict)

    def value(self, name: str) -> float:
        return self.ceilings[name].value

    def validate(self, name: str, value: float) -> None:
        """Would this value be refused? Raises `Exceeded` if so, and **moves
        nothing**.

        **Separate from `set` because a change is checked when a console offers it
        and applied a trial boundary later** (PI, 2026-09-19); S9a §8.1 has that
        account, and it is about `taskd` rather than this file.

        An unknown name is **refused rather than created**: `rewrd_correct` set to
        5.0 would otherwise be accepted, bounded by nothing.

        **A bad value is refused here, not at assignment.** `Ceiling` would refuse
        to hold one anyway, but it would raise inside `taskd._apply_staged`, which
        states that its re-validation cannot fail and leaves earlier rows applied if
        one does. Refusing at offer time means the person is still looking.

        No actor: a refusal does not depend on who asked, and every caller records
        the actor beside it.
        """
        _magnitude(f"{name!r}", value)
        ceiling = self.ceilings.get(name)
        if ceiling is None:
            raise Exceeded(
                f"{name!r} has no ceiling in the bounded config for subject "
                f"{self.subject!r}; it is refused rather than created"
            )
        if value > ceiling.maximum:
            raise Exceeded(
                f"{name!r} may not exceed {ceiling.maximum} {ceiling.unit} "
                f"(asked for {value}); the previous value stands"
            )

    def set(self, name: str, value: float, by: str) -> None:
        """Move a bounded value, within its ceiling.

        **Validated through `validate`, never by a second copy of the rule here.**
        Two copies of a ceiling check are two places for it to drift. `by` is the
        actor the caller records; the refusal itself does not depend on who asked.
        """
        self.validate(name, value)
        ceiling = self.ceilings[name]
        self.ceilings[name] = Ceiling(value, ceiling.maximum, ceiling.unit)

    def shortfall(self, name: str, delivered_today: float | None) -> float | None:
        """How much of a daily minimum is still owed, or `None` if nobody knows.

        **The whole of what the daily fluid figure is for** (PI, 2026-09-06), and
        never a refusal: withholding reward an animal worked for, to satisfy an upper
        limit this protocol does not have, is the failure this replaced.

        `delivered_today` is `None` when the total could not be reconstructed -- a
        crash, or cage-side with no ELN figure. **The answer is then `None`, not
        zero**: a day nobody can measure is not a day that went well.
        """
        floor = self.minima.get(name)
        if floor is None:
            raise Exceeded(
                f"the bounded config for subject {self.subject!r} declares no "
                f"{name!r} minimum, so nothing can say what the day still owes; a "
                f"missing floor is not a floor of zero"
            )
        if delivered_today is None:
            return None
        # **The measurement, not just the floor.** `max(0.0, floor - nan)` is `0.0`,
        # because `nan > 0.0` is False -- so an unmeasured day arrived here as
        # "nothing is owed" on a fluid-restricted animal, in the one figure a person
        # acts on. `None` is how this function says "unknown"; a number that is not
        # a number must never be able to impersonate zero.
        _magnitude("the day's delivered total", delivered_today)
        return max(0.0, floor.value - delivered_today)


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """What the two fluid records say, and what the difference means."""

    total: float
    commanded: float
    delivered: float
    unexplained: float
    manual_rewards_likely: bool
    fault: str | None


def reconcile_report(commanded: float, delivered: float) -> Reconciliation:
    """Compare what we asked for with what the delivered line recorded.

    **Our commanded total is a lower bound, not a total** (P17). The panel's manual
    reward button bypasses this software entirely and is recorded as *delivered*, so
    a shortfall computed from what we commanded would ask for a top-up the animal has
    already had by hand.

    **The divergence is reported, never absorbed**: silently taking the larger number
    throws away the one signal that a hand reward happened, and training days are when
    an unlogged one becomes a silent confound.

    **Delivered below commanded is a fault, not a reconciliation.** The larger figure
    is used and the fault is reported, rather than a failing rig hiding behind a
    plausible total.
    """
    # Both figures are volumes, and both arrive from outside: `commanded` from this
    # session's own accounting, `delivered` from the sync box's record (S8 §5.1).
    # `max(commanded, delivered)` with a `nan` on either side returns whichever the
    # comparison happens to pick, and every fluid figure downstream is then `nan`.
    _magnitude("the commanded fluid total", commanded)
    _magnitude("the delivered-line fluid total", delivered)
    fault = None
    if delivered < commanded:
        fault = (
            f"the delivered line recorded {delivered} against {commanded} commanded, "
            f"which is less than commanded -- the pump, the line or the recording is "
            f"faulty, and the larger figure is used until it is explained"
        )
    unexplained = max(0.0, delivered - commanded)
    return Reconciliation(
        total=max(commanded, delivered),
        commanded=commanded,
        delivered=delivered,
        unexplained=unexplained,
        manual_rewards_likely=unexplained > 0.0,
        fault=fault,
    )


def reconcile(commanded: float, delivered: float) -> float:
    """The day's fluid total: the figure a shortfall is computed from."""
    return reconcile_report(commanded, delivered).total
