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
            "out_of_cage": Ceiling(value=43_200.0, maximum=43_200.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )


def test_a_ceiling_that_is_not_a_number_cannot_be_built():
    """**A limit that is not a number is not a limit.** NaN compares `False`
    against every ordered test, so a NaN ceiling is not exceeded by anything: a
    review reproduced one in a bounded config reaching `welfare.must_stop`, which
    answered `None` for a whole reward-delivering session with an honest mark and
    a clean summary.

    Refused at the type, because a bounded config builds these directly -- it is
    Python (ADR-0006) -- so there is no call site to put the check at."""
    with pytest.raises(Exceeded, match="not a number"):
        Ceiling(value=float("nan"), maximum=10.0, unit="s")

    with pytest.raises(Exceeded, match="not a number"):
        Ceiling(value=1.0, maximum=float("nan"), unit="s")


def test_a_floor_that_is_not_a_number_cannot_be_built():
    """Less dangerous than a NaN ceiling -- no delivery is refused on volume, so
    nothing stops -- but `shortfall()` would answer `nan` and both the console and
    `wlx run` print it as the figure a person supplements against."""
    with pytest.raises(Exceeded, match="not a number"):
        Floor(value=float("nan"), unit="mL")


def test_a_console_offering_a_value_that_is_not_a_number_is_refused_when_it_asks():
    """Refused by `validate`, not merely by the `Ceiling` that `set` would build.
    `taskd._apply_staged` states that its re-validation cannot fail and leaves
    earlier rows applied if one does, so a NaN accepted at offer time would blow up
    mid-apply. It is refused while the person is still looking, like every other
    value this method refuses."""
    bounds = _bounds()

    with pytest.raises(Exceeded, match="not a number"):
        bounds.validate("reward_correct", float("nan"))

    assert bounds.value("reward_correct") == 0.15, "the previous value must stand"


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


# --- validation separated from application (PI, 2026-09-19) ------------------


def test_validating_a_value_refuses_exactly_what_set_refuses():
    """A welfare-bounded change is now validated when it is offered and applied at
    the next trial boundary (PI, 2026-09-19), so the two halves have to be
    separable. `validate` answers "would this be refused" and refuses on the same
    two grounds `set` does: past the ceiling, and a name that has no ceiling at
    all."""
    bounds = _bounds()

    with pytest.raises(Exceeded, match="reward_correct"):
        bounds.validate("reward_correct", 0.9)

    with pytest.raises(Exceeded, match="no ceiling"):
        bounds.validate("rewrd_correct", 0.2)


def test_validating_a_value_does_not_move_it():
    """The whole reason the split exists. A check that moved the value would make
    the *offer* the change, which is the behaviour being removed -- a console's
    `reward_correct` used to be live for the trial that ran later in the same pass,
    while being displayed as `staged` and recorded a trial late."""
    bounds = _bounds()

    bounds.validate("reward_correct", 0.25)

    assert bounds.value("reward_correct") == 0.15, "validating moved the value"


def test_set_refuses_through_validate_so_the_rule_cannot_drift():
    """Structural, and deliberately so. `set` and `validate` must not each carry
    their own copy of the ceiling rule: a second copy is a second place for it to
    drift, and the one that drifts silently is the one a console offers a value
    against. Stubbing `validate` here proves `set` asks it rather than re-deriving
    the answer."""
    bounds = _bounds()
    asked = []
    bounds.validate = lambda name, value: asked.append((name, value))

    bounds.set("reward_correct", 0.25, by="console")

    assert asked == [("reward_correct", 0.25)], "set did not go through validate"
    assert bounds.value("reward_correct") == 0.25
