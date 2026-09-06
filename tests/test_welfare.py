"""Fluid and chair-time accounting, and the only path to the pump.

S8 §5 and §7. **Welfare-critical, and requires human review before merge**
(CLAUDE.md).

**Fluid has a floor, not a ceiling** (PI, 2026-09-06). A session never refuses a
delivery on volume; it reports at close how much of the day's minimum is still owed,
so a person can supplement it. Chair time and trial count *are* ceilings and do stop a
session.

The reason this module exists at all is that `bounds`' fluid check was called by
nothing outside its own tests for a week. A bound nothing calls reads as present and
is not, so these tests are as much about *who calls whom* as about arithmetic.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.bounds import Bounds, Ceiling, Exceeded, Floor
from wl_expcontroller.dio import Simulated as Card
from wl_expcontroller.welfare import Absent, Rig, Simulated, Welfare


def _bounds(daily_fluid: float = 250.0, **over: float) -> Bounds:
    ceilings = {
        "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
        "chair_time": Ceiling(value=14_400.0, maximum=14_400.0, unit="s"),
        "max_trials": Ceiling(value=2000.0, maximum=4000.0, unit="trials"),
    }
    for name, value in over.items():
        ceiling = ceilings[name]
        ceilings[name] = Ceiling(value, ceiling.maximum, ceiling.unit)
    return Bounds(
        subject="A",
        ceilings=ceilings,
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


def _welfare(already: float | None = 0.0, **over: float) -> Welfare:
    return Welfare(bounds=_bounds(**over), pump=Simulated(), already_today=already)


# --- the delivery path ------------------------------------------------------


def test_a_delivery_reaches_the_pump_and_is_accounted():
    welfare = _welfare()

    delivered = welfare.deliver("reward_correct")

    assert delivered == 0.15
    assert welfare.pump.delivered == [0.15]
    assert welfare.commanded == 0.15
    assert welfare.deliveries == 1


def test_the_days_total_carries_what_another_deployment_already_delivered():
    """S8 §5.2b: one daily figure across rig and kiosk, and wl-works holds the
    ledger. An animal cannot be in the chair and at the cage kiosk at once, so a
    start-time number from the deployment that ran first is a current one."""
    welfare = _welfare(already=100.0)

    welfare.deliver("reward_correct")

    assert welfare.total_today() == pytest.approx(100.15)


def test_a_delivery_is_never_refused_on_volume():
    """**There is no fluid ceiling** (PI, 2026-09-06). An animal that keeps working
    keeps earning, and a session that stopped paying to satisfy an upper limit this
    protocol does not have would be withholding fluid it had already asked for."""
    welfare = _welfare(already=249.95)

    for _ in range(20):
        welfare.deliver("reward_correct")

    assert len(welfare.pump.delivered) == 20
    assert welfare.total_today() == pytest.approx(249.95 + 20 * 0.15)


def test_a_day_short_of_its_floor_reports_what_must_be_supplemented():
    """The whole of what the daily figure is for: the top-up after the session."""
    welfare = _welfare(already=100.0)

    welfare.deliver("reward_correct")

    assert welfare.shortfall() == pytest.approx(149.85)


def test_a_day_that_reached_its_floor_owes_nothing():
    welfare = _welfare(already=260.0)

    assert welfare.shortfall() == 0.0


def test_an_unknown_prior_total_leaves_the_shortfall_unknown_and_still_pays():
    """The old design refused delivery on an unknown total, on the argument that a
    ceiling which cannot be computed cannot be enforced. Under a floor that argument
    runs the other way: the one thing an unknown day must not do is stop paying an
    animal that is working."""
    welfare = _welfare(already=None)

    welfare.deliver("reward_correct")

    assert welfare.pump.delivered == [0.15]
    assert welfare.total_today() is None
    assert welfare.shortfall() is None


def test_a_human_confirming_a_figure_makes_the_day_countable_again():
    welfare = _welfare(already=None)
    welfare.deliver("reward_correct")

    welfare.confirm_already_today(12.0, by="jake")

    assert welfare.total_today() == pytest.approx(12.15)
    assert welfare.shortfall() == pytest.approx(237.85)


def test_the_commanded_total_is_charged_before_the_valve_opens():
    """A pump that raises after opening would otherwise leave fluid unaccounted, and
    an under-counted total is the direction that over-delivers. Charging first
    over-counts on a failure, which refuses reward early and is the safe error."""

    class Failing:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    welfare = Welfare(bounds=_bounds(), pump=Failing(), already_today=0.0)

    with pytest.raises(RuntimeError):
        welfare.deliver("reward_correct")

    assert welfare.commanded == 0.15


def test_an_absent_pump_refuses_rather_than_delivering_nothing():
    """The `dio.Absent` argument, one layer up: a session that runs a full protocol
    and dispenses nothing has worked an animal for no reward."""
    welfare = Welfare(bounds=_bounds(), pump=Absent(), already_today=0.0)

    with pytest.raises(RuntimeError, match="no pump"):
        welfare.deliver("reward_correct")


def test_a_bounded_config_without_a_daily_fluid_floor_refuses_to_start():
    """A missing floor is not a floor of zero. A session with no daily minimum can
    report no shortfall, so nobody would ever be told to supplement."""
    bounds = Bounds(
        subject="A",
        ceilings={
            "reward_correct": Ceiling(0.15, 0.4, "mL"),
            "chair_time": Ceiling(14_400.0, 14_400.0, "s"),
        },
    )

    with pytest.raises(Exceeded, match="daily_fluid"):
        Welfare(bounds=bounds, pump=Simulated(), already_today=0.0)


def test_a_bounded_config_without_a_chair_time_ceiling_refuses_to_start():
    bounds = _bounds()
    del bounds.ceilings["chair_time"]

    with pytest.raises(Exceeded, match="chair_time"):
        Welfare(bounds=bounds, pump=Simulated(), already_today=0.0)


# --- reconciliation ---------------------------------------------------------


def test_the_delivered_line_replaces_our_commanded_total_when_it_is_larger():
    """P17: the panel button reaches the pump through the board's OR gate and never
    through us, so our commanded figure is a lower bound."""
    welfare = _welfare()
    welfare.deliver("reward_correct")

    welfare.reconcile(delivered=5.0)

    assert welfare.total_today() == pytest.approx(5.0)
    assert welfare.report().manual_rewards_likely


def test_a_delivered_line_below_commanded_is_a_fault_and_the_larger_figure_stands():
    welfare = _welfare()
    for _ in range(10):
        welfare.deliver("reward_correct")

    welfare.reconcile(delivered=0.5)

    assert welfare.total_today() == pytest.approx(1.5)
    assert "faulty" in welfare.report().fault


def test_reconciliation_is_what_the_shortfall_is_computed_from():
    """Hand rewards count toward the day. A shortfall computed from what we commanded
    would ask for a top-up the animal has already had."""
    welfare = _welfare(already=0.0)
    welfare.deliver("reward_correct")
    welfare.reconcile(delivered=200.0)

    assert welfare.shortfall() == pytest.approx(50.0)


# --- chair time -------------------------------------------------------------


def test_chair_time_runs_from_head_fixation_not_from_the_first_trial():
    """PI, 2026-08-31: the limit is on restraint, not on work, so setup,
    calibration and unrewarded shaping all count."""
    welfare = _welfare()

    welfare.head_fixed(at=100.0)

    assert welfare.chair_seconds(now=160.0) == pytest.approx(60.0)


def test_chair_time_is_zero_before_the_animal_is_in_the_chair():
    assert _welfare().chair_seconds(now=1_000.0) == 0.0


def test_releasing_the_head_stops_the_restraint_clock():
    welfare = _welfare()
    welfare.head_fixed(at=100.0)

    welfare.head_released(at=160.0)

    assert welfare.chair_seconds(now=9_999.0) == pytest.approx(60.0)


def test_fixing_a_head_that_is_already_fixed_is_refused():
    """Two starts means one of the two clocks is wrong, and the shorter one is the
    one that would silently win."""
    welfare = _welfare()
    welfare.head_fixed(at=100.0)

    with pytest.raises(Exceeded, match="already"):
        welfare.head_fixed(at=200.0)


def test_a_session_must_stop_when_the_chair_time_ceiling_is_reached():
    welfare = _welfare(chair_time=60.0)
    welfare.head_fixed(at=0.0)

    assert welfare.must_stop(now=59.0, trials=0) is None
    assert "chair_time" in welfare.must_stop(now=61.0, trials=0)


def test_a_session_must_stop_at_its_trial_ceiling():
    welfare = _welfare(max_trials=10.0)
    welfare.head_fixed(at=0.0)

    assert welfare.must_stop(now=1.0, trials=9) is None
    assert "max_trials" in welfare.must_stop(now=1.0, trials=10)


def test_a_session_with_no_trial_ceiling_runs_on_its_other_limits():
    """`max_trials` is optional in a way `daily_fluid` and `chair_time` are not: a
    session that reports its shortfall and is bounded by restraint is complete, and a
    lab that states no trial cap has stated a policy rather than forgotten one."""
    bounds = _bounds()
    del bounds.ceilings["max_trials"]
    welfare = Welfare(bounds=bounds, pump=Simulated(), already_today=0.0)
    welfare.head_fixed(at=0.0)

    assert welfare.must_stop(now=1.0, trials=100_000) is None


# --- the port a trial's actions actually reach ------------------------------


def test_a_rewards_only_path_to_the_pump_runs_through_the_days_accounting():
    """The property this whole module exists for. `Rig` is what a trial's `Reward`
    action reaches, and it has no way to reach a pump that the day's total does not
    see -- which is what makes the shortfall at close a real number."""
    welfare = _welfare()
    rig = Rig(card=Card(), welfare=welfare)

    rig.reward("reward_correct")

    assert welfare.pump.delivered == [0.15]
    assert welfare.total_today() == pytest.approx(0.15)


def test_a_mark_reaches_the_card_and_never_the_pump():
    rig = Rig(card=Card(), welfare=_welfare())

    rig.mark(4102)

    assert rig.card.codes == [4102]
    assert rig.welfare.pump.delivered == []


def test_a_reward_past_the_days_floor_is_delivered_like_any_other():
    """No refusal path exists for volume, so there is nothing for `Rig` to swallow."""
    rig = Rig(card=Card(), welfare=_welfare(already=249.95))

    rig.reward("reward_correct")

    assert rig.welfare.pump.delivered == [0.15]


def test_a_pump_fault_reaches_the_session_rather_than_being_absorbed():
    """A solenoid that will not answer is a broken rig, and absorbing it would
    produce a session's worth of correct trials nobody was paid for -- the failure
    `Absent` exists to prevent, arrived at by a different route."""

    class Failing:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    rig = Rig(
        card=Card(),
        welfare=Welfare(bounds=_bounds(), pump=Failing(), already_today=0.0),
    )

    with pytest.raises(RuntimeError, match="solenoid"):
        rig.reward("reward_correct")
