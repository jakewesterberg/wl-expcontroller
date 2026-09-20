"""The bounded config: what a task cannot express and a console cannot exceed.

**Welfare-critical. Human review required before merge** (CLAUDE.md, S8 §7). Kept
small on purpose: everything here is a thing that can hurt an animal if it is wrong,
and a small file is one a person can actually read before signing it off.

**Fluid has a floor, not a ceiling** (PI, 2026-09-06), and this file was built the
other way round until then. The daily fluid figure is a **minimum the animal must
reach**, topped up by hand after the session if the work did not earn it -- so there
is no upper limit on earned reward, and a delivery is never refused on volume. What
was here before refused a delivery that would put the day past its "budget", which
under this protocol withholds fluid an animal earned in order to satisfy a limit
nobody set. S8 §4's phrase "daily fluid budget" is what made that reading available;
the spec now carries the correction.

**Ceilings and floors are different types here, deliberately.** They were the same
type when both were `Ceiling`, which is exactly how the daily figure came to be
compared with `>` -- a floor stored as a ceiling reads as one at every call site. A
`Floor` cannot be passed to `set`, and a `Ceiling` cannot be asked for a shortfall.

Three properties, and each exists because of a specific way this goes wrong:

- **A task cannot name a magnitude at all.** `Reward` takes the name of an entry here
  and the type refuses a number, so the guardrail is what a task can *express* rather
  than what review notices -- which matters because the task was probably written by a
  model (P15).
- **A console may move a value within its ceiling and not past it.** The console is a
  human, and a human is exactly who this stops: reward volume per delivery is the
  parameter most often adjusted mid-session and the one where a slip is a dose. This
  is a genuine ceiling and it stays one. **Checking and moving are two calls**
  (`validate`, then `set`) because they happen at two moments -- see `validate`.
- **An unknown daily total leaves the shortfall unknown**, rather than answering zero.
  Not a refusal to deliver -- a refusal to *claim*: nobody can say what to supplement
  without knowing what the animal has already had, and zero would report a day as
  fine when nothing knows whether it was.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class Exceeded(ValueError):
    """A value or a delivery would go past a ceiling. Never caught internally."""


def _finite(what: str, value: float) -> None:
    """An **instant** entering the welfare path: refused unless it is a real number.

    **`nan` and `inf` both defeat ordered comparisons, in opposite ways.** `nan` is
    `False` against every one of them, so nothing refuses it. `inf` is ordered but
    unreachable: `seconds > inf` is `False` for every real duration, so an `inf`
    *ceiling* is never exceeded either. Both were measured, each running a full
    reward-delivering session with a clean summary and no limit at all.

    An earlier version of this docstring said `inf` "was already refused correctly,
    and only NaN slipped through". **That was false and is recorded here rather than
    quietly deleted**: only the *mark* route refused `inf`, because `seconds_ago >=
    ceiling.value` is `True` for `inf` against a finite ceiling. The *ceiling* route
    refused neither. A wrong sentence in a welfare-critical file is worse than a long
    one, and this one had already been repeated twice.

    `math.isfinite` covers both and is what `calibration._yaml_float` already uses;
    a second spelling of "is this a number" is a second thing to keep in step.

    See `_magnitude` for the stronger rule that volumes, durations and limits get.
    """
    if not math.isfinite(value):
        raise Exceeded(
            f"{what} is {value!r}, which is not a real number: it defeats the "
            f"comparisons every limit is enforced with, so the bound it belongs to "
            f"would be switched off rather than exceeded"
        )


def _magnitude(what: str, value: float) -> None:
    """A **magnitude** entering the welfare path: finite, and not negative.

    Volumes, durations and the limits on them are quantities of something. A
    negative one is not a smaller quantity, it is a different kind of thing, and
    every guard in this file compares magnitudes with `>` -- so a negative value
    passes them all in the same way `nan` does.

    Measured, through the real console path: `--set reward_correct=-0.5` was
    accepted and applied, commanding twenty rewards of **-0.5 mL** to the pump and
    then telling the operator to supplement 30 mL against a 20 mL floor.
    `--delivered-today=-1000` asked for 1019.75 mL.

    **The assumption, stated so a future entry can push back on it: every bounded
    quantity in this system is a magnitude.** Reward volume, daily fluid, time out
    of the cage and the token figures all are. S8 §4 also lists stimulation bounds,
    which do not exist yet; if one of those ever needs a sign -- a cathodic-first
    amplitude, say -- it wants its own type rather than a hole in this one.
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

    Retained rather than deleted: `welfare` reports an unknown day loudly at session
    close, and a distinct type is what lets a caller tell "we do not know" from "the
    answer is zero".
    """


@dataclass(frozen=True, slots=True)
class Ceiling:
    """A current value and the most it may ever be set to.

    Two numbers rather than one because the *setting* is routine and the *limit* is
    not: an experimenter moves reward volume between sessions without ceremony, and
    the maximum is not theirs to move while a session runs.

    **A maximum is one of two kinds of limit and this type does not distinguish
    them** (PI, 2026-09-19). It may be a **protocol figure** -- a number a protocol
    states, changing only when the protocol does, which is what the out-of-cage
    ceiling is. Or it may be a **fault bound** -- set far above anything a protocol would
    ask for, so that what it refuses is software commanding an impossible quantity
    rather than an animal earning a ration. Both are enforced identically here; what
    differs is what a refusal *means*, so a bounded config is expected to say at each
    entry which kind its maximum is.
    """

    value: float
    maximum: float
    unit: str

    def __post_init__(self) -> None:
        """**A limit that is not a number is not a limit** -- see `_finite`.

        Here rather than only at the call sites because a bounded config builds
        these directly (`tasks/reference_bounds.py` is Python, ADR-0006), which is
        the route a review reproduced: a NaN ceiling reached `welfare.must_stop`
        and answered `None` for a whole session.
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
        """A floor that is not a number is not a floor either (`_finite`).

        Less dangerous than a NaN ceiling -- no delivery is ever refused on volume,
        so nothing stops -- but it makes `shortfall()` answer `nan`, which the
        console and `wlx run` print as a supplement figure. A number nobody can act
        on, shown where a person acts on it.
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
        and applied a trial boundary later** (PI, 2026-09-19). While they were one
        call a welfare-bounded value could not be checked without being moved, so it
        went live a trial before the record said it had; **S9a §8.1** has that
        account, and it is about `taskd`, not about this file.

        An unknown name is **refused rather than created**: a typo must not silently
        become an unbounded parameter that is then used. `rewrd_correct` set to 5.0
        would otherwise be accepted, bounded by nothing.

        **A value that is not a number is refused here, not at assignment.**
        `Ceiling` refuses to hold one, so `set` would raise either way -- but it
        would raise inside `taskd._apply_staged`, which states that its
        re-validation cannot fail and leaves earlier rows applied if one does. A
        NaN offered by a console is refused while the person is still looking, like
        every other value this method refuses.

        No actor: a refusal does not depend on who asked, and every caller records
        the actor beside the refusal it raises.
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

        **The whole of what the daily fluid figure is for** (PI, 2026-09-06). An
        animal that earned less than its floor in the chair is supplemented after the
        session; one that earned more has earned more, and there is nothing to do.
        Never a refusal: withholding reward an animal worked for, in order to satisfy
        an upper limit this protocol does not have, is the failure this replaced.

        `delivered_today` is `None` when the total could not be reconstructed -- after
        a crash, or cage-side with no ELN figure. **The answer is then `None`, not
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
    reward button bypasses this software entirely -- debounced, monostabled, OR'd with
    our commanded line on `wl-sync`'s board, and recorded as *delivered*. A session
    computing the day's shortfall from what it commanded would ask for a top-up the
    animal has already had by hand -- which under a floor is the direction that
    over-delivers, exactly as under a ceiling it was the direction that under-counted.

    **The divergence is reported, never absorbed.** Silently taking the larger number
    would throw away the one signal saying a hand reward happened at all -- and
    training days, when hand rewards are commonest, are exactly when an unlogged one
    becomes a silent confound.

    **Delivered below commanded is a fault, not a reconciliation.** The pump should
    never deliver less than asked; if the record says it did, something is wrong with
    the pump, the line, or the recording, and quietly using the smaller number would
    hide a failing rig behind a plausible total. The larger figure is used, and the
    fault is reported rather than the number quietly corrected.
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
