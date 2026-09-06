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
  is a genuine ceiling and it stays one.
- **An unknown daily total leaves the shortfall unknown**, rather than answering zero.
  Not a refusal to deliver -- a refusal to *claim*: nobody can say what to supplement
  without knowing what the animal has already had, and zero would report a day as
  fine when nothing knows whether it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Exceeded(ValueError):
    """A value or a delivery would go past a ceiling. Never caught internally."""


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
    the maximum is a protocol figure that changes only with a protocol.
    """

    value: float
    maximum: float
    unit: str


@dataclass(frozen=True, slots=True)
class Floor:
    """A daily minimum the animal must reach, however it reaches it.

    One number rather than two, because a floor has no "most it may be set to": the
    thing a protocol states is the minimum itself, and a maximum on a minimum is a
    quantity nobody has a name for.
    """

    value: float
    unit: str


@dataclass
class Bounds:
    subject: str
    ceilings: dict[str, Ceiling] = field(default_factory=dict)
    #: Daily minima. Separate from `ceilings` so the two cannot be confused at a call
    #: site, which is how the daily fluid figure came to be enforced as a limit.
    minima: dict[str, Floor] = field(default_factory=dict)

    def value(self, name: str) -> float:
        return self.ceilings[name].value

    def set(self, name: str, value: float, by: str) -> None:
        """Move a bounded value, within its ceiling.

        An unknown name is **refused rather than created**: a typo must not silently
        become an unbounded parameter that is then used. `rewrd_correct` set to 5.0
        would otherwise be accepted, bounded by nothing.
        """
        ceiling = self.ceilings.get(name)
        if ceiling is None:
            raise Exceeded(
                f"{name!r} has no ceiling in the bounded config for subject "
                f"{self.subject!r}; it is refused rather than created"
            )
        if value > ceiling.maximum:
            raise Exceeded(
                f"{name!r} may not exceed {ceiling.maximum} {ceiling.unit} "
                f"(asked for {value} by {by}); the previous value stands"
            )
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
