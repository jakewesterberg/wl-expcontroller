"""The bounded config: what a task cannot express and a console cannot exceed.

S8 §4 and §7. This is welfare-critical code and requires human review before merge
(CLAUDE.md). It is deliberately small.

**Fluid has a floor, not a ceiling** (PI, 2026-09-06). Everything else here is a
ceiling; the daily fluid figure is a *minimum the animal must reach*, topped up by
hand after the session if the work did not earn it. The tests below that used to
assert a refusal past a daily total are gone, and their absence is the point: a
delivery refused on volume withholds fluid an animal earned, which is the opposite of
what the daily figure protects.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.bounds import (
    Bounds,
    Ceiling,
    Exceeded,
    Floor,
    reconcile,
    reconcile_report,
)


def _bounds() -> Bounds:
    return Bounds(
        subject="A",
        ceilings={
            "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
            "chair_time": Ceiling(value=14_400.0, maximum=14_400.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
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


def test_a_days_shortfall_is_what_still_has_to_be_supplemented():
    """The daily fluid figure is a **floor** (PI, 2026-09-06): an animal that did not
    earn it in the chair is topped up afterwards. So the question this answers is not
    "may I deliver" but "how much is still owed"."""
    bounds = _bounds()

    assert bounds.shortfall("daily_fluid", delivered_today=100.0) == 150.0


def test_a_day_that_reached_its_floor_owes_nothing():
    bounds = _bounds()

    assert bounds.shortfall("daily_fluid", delivered_today=250.0) == 0.0


def test_earning_past_the_floor_is_not_an_error_and_owes_nothing():
    """There is no ceiling. An animal that worked well and earned 300 mL has earned
    300 mL, and a session that refused the last of it would have withheld fluid to
    satisfy a limit nobody set."""
    bounds = _bounds()

    assert bounds.shortfall("daily_fluid", delivered_today=300.0) == 0.0


def test_an_unknown_daily_total_leaves_the_shortfall_unknown():
    """Not a refusal to deliver -- a refusal to *claim*. Nobody can say what to
    supplement without knowing what the animal has already had, and answering zero
    would say the day was fine when nothing knows whether it was."""
    bounds = _bounds()

    assert bounds.shortfall("daily_fluid", delivered_today=None) is None


def test_a_floor_that_is_not_declared_is_refused_rather_than_assumed():
    """A subject with no daily minimum is a bounded config nobody finished, and a
    missing floor reads identically to a floor of zero to anything that does not
    check."""
    bounds = Bounds(subject="A", ceilings=dict(_bounds().ceilings))

    with pytest.raises(Exceeded, match="daily_fluid"):
        bounds.shortfall("daily_fluid", delivered_today=100.0)


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
