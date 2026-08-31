"""The bounded config: ceilings a task cannot express and a console cannot exceed.

**Welfare-critical. Human review required before merge** (CLAUDE.md, S8 §7). Kept
small on purpose: everything here is a thing that can hurt an animal if it is wrong,
and a small file is one a person can actually read before signing it off.

Three properties, and each exists because of a specific way this goes wrong:

- **A task cannot name a magnitude at all.** `Reward` takes the name of an entry here
  and the type refuses a number, so the guardrail is what a task can *express* rather
  than what review notices -- which matters because the task was probably written by a
  model (P15).
- **A console may move a value within its ceiling and not past it.** The console is a
  human, and a human is exactly who this stops: reward volume is the parameter most
  often adjusted mid-session and the one where a slip is a dose.
- **An unknown total refuses delivery.** A ceiling that cannot be computed cannot be
  enforced (S8 §5.2). This is the one place the design deliberately fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Exceeded(ValueError):
    """A value or a delivery would go past a ceiling. Never caught internally."""


class Unknown(RuntimeError):
    """A ceiling cannot be computed, so it cannot be enforced."""


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


@dataclass
class Bounds:
    subject: str
    ceilings: dict[str, Ceiling] = field(default_factory=dict)
    #: Which entry accumulates against the daily fluid budget. Named rather than
    #: inferred, so adding a second reward size cannot silently escape the budget.
    fluid_budget: str = "daily_fluid"

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

    def check_delivery(self, name: str, delivered_today: float | None) -> None:
        """Refuse a delivery that would put the day past its fluid ceiling.

        **Checked against what this delivery would make the total, not against the
        total so far.** A delivery that starts inside the ceiling and ends outside it
        is the whole case; checking before rather than after is how a limit gets
        exceeded by exactly one reward, every session.

        `delivered_today` is `None` when the total could not be reconstructed -- after
        a crash, or cage-side with no ELN figure. That refuses delivery until a human
        confirms one (S8 §5.2, S13 §4).
        """
        if delivered_today is None:
            raise Unknown(
                f"the daily total for subject {self.subject!r} could not be "
                f"reconstructed, so its ceiling cannot be enforced; reward is "
                f"refused until a human confirms a figure"
            )
        budget = self.ceilings[self.fluid_budget]
        would_be = delivered_today + self.ceilings[name].value
        if would_be > budget.value:
            raise Exceeded(
                f"delivering {self.ceilings[name].value} {budget.unit} would put "
                f"subject {self.subject!r} at {would_be:.2f} against a "
                f"{self.fluid_budget} of {budget.value} {budget.unit}"
            )


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
    enforcing its ceiling against what it commanded would let every hand-delivered
    reward past.

    **The divergence is reported, never absorbed.** Silently taking the larger number
    would throw away the one signal saying a hand reward happened at all -- and
    training days, when hand rewards are commonest, are exactly when an unlogged one
    becomes a silent confound.

    **Delivered below commanded is a fault, not a reconciliation.** The pump should
    never deliver less than asked; if the record says it did, something is wrong with
    the pump, the line, or the recording, and quietly using the smaller number would
    hide a failing rig behind a plausible total. The larger figure is used, which is
    the conservative direction for a ceiling.
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
    """The figure a ceiling is enforced against."""
    return reconcile_report(commanded, delivered).total
