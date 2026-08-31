"""The bounded config: ceilings a task cannot express and a console cannot exceed.

S8 §4 and §7. This is welfare-critical code and requires human review before merge
(CLAUDE.md). It is deliberately small, and everything in it fails closed.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.bounds import (
    Bounds,
    Ceiling,
    Exceeded,
    Unknown,
    reconcile,
    reconcile_report,
)


def _bounds() -> Bounds:
    return Bounds(
        subject="A",
        ceilings={
            "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
            "daily_fluid": Ceiling(value=250.0, maximum=250.0, unit="mL"),
            "chair_time": Ceiling(value=14_400.0, maximum=14_400.0, unit="s"),
        },
    )


def test_a_console_may_move_a_value_within_its_ceiling():
    bounds = _bounds()

    bounds.set("reward_correct", 0.25, by="console")

    assert bounds.value("reward_correct") == 0.25


def test_a_console_cannot_exceed_a_ceiling():
    """The console is a human, and a human is exactly who this stops. Reward volume
    is the parameter most often adjusted mid-session and the one where a slip is a
    dose."""
    bounds = _bounds()

    with pytest.raises(Exceeded, match="reward_correct"):
        bounds.set("reward_correct", 0.9, by="console")

    assert bounds.value("reward_correct") == 0.15, "and the old value stands"


def test_a_name_with_no_ceiling_is_refused_rather_than_created():
    """A typo must not silently become an unbounded parameter. `rewrd_correct` set
    to 5.0 would otherwise be accepted, bounded by nothing, and used."""
    bounds = _bounds()

    with pytest.raises(Exceeded, match="no ceiling"):
        bounds.set("rewrd_correct", 0.2, by="console")


def test_delivering_against_an_unknown_daily_total_is_refused():
    """S8 §5.2, the one place the design deliberately fails closed. A ceiling that
    cannot be computed cannot be enforced, and continuing on an unknown total is
    the one failure whose cost is not ours to absorb."""
    bounds = _bounds()

    with pytest.raises(Unknown, match="daily total"):
        bounds.check_delivery("reward_correct", delivered_today=None)


def test_delivery_is_refused_once_the_daily_total_reaches_its_ceiling():
    bounds = _bounds()

    bounds.check_delivery("reward_correct", delivered_today=100.0)

    with pytest.raises(Exceeded, match="daily_fluid"):
        bounds.check_delivery("reward_correct", delivered_today=249.95)


def test_the_ceiling_is_checked_against_what_this_delivery_would_make_the_total():
    """Not against the total so far. A delivery that starts inside the ceiling and
    ends outside it is the whole case -- checking before rather than after is how a
    limit gets exceeded by exactly one reward, every session."""
    bounds = _bounds()

    with pytest.raises(Exceeded):
        bounds.check_delivery("reward_correct", delivered_today=249.90)


def test_fluid_reconciles_against_delivered_not_against_commanded():
    """P17. The panel's manual reward button bypasses our software entirely --
    debounced, monostabled, OR'd with our commanded line, and recorded as
    *delivered*. So our commanded total is a lower bound, and a session that
    enforced against it would let every hand-delivered reward past the ceiling."""
    bounds = _bounds()

    # We commanded 100 mL. The delivered line says 180: someone used the panel.
    with pytest.raises(Exceeded):
        bounds.check_delivery(
            "reward_correct", delivered_today=reconcile(commanded=100.0, delivered=249.9)
        )


def test_reconciliation_reports_the_divergence_rather_than_absorbing_it():
    """A gap between commanded and delivered is information -- usually manual
    rewards, occasionally a fault -- and silently taking the larger number would
    throw away the one signal that says a hand reward happened at all."""
    report = reconcile_report(commanded=100.0, delivered=118.0)

    assert report.total == 118.0
    assert report.unexplained == 18.0
    assert report.manual_rewards_likely is True


def test_delivered_below_commanded_is_a_fault_not_a_reconciliation():
    """The pump should never deliver less than commanded. If it does, something is
    wrong with the pump, the line or the recording -- and quietly using the smaller
    number would hide a failing rig behind a plausible total."""
    report = reconcile_report(commanded=100.0, delivered=82.0)

    assert report.total == 100.0, "the larger figure is used, conservatively"
    assert report.fault is not None
    assert "less than commanded" in report.fault
