"""Fluid and duration accounting, and the only path to the pump.

S8 §5 and §7. **Welfare-critical, and requires human review before merge**
(CLAUDE.md).

**Fluid has a floor, not a ceiling** (PI, 2026-09-06). A session never refuses a
delivery on volume; it reports at close how much of the day's minimum is still owed,
so a person can supplement it.

**One duration limit, and it is out-of-cage to back-in-cage** (PI, 2026-09-19).
There is no session-length maximum and no trial cap; chair time is recorded and
bounds nothing. Several tests below are about *which clock is measured* rather than
about arithmetic, because the two clocks differ by transport and chairing and the
wrong one under-counts.

The reason this module exists at all is that `bounds`' fluid check was called by
nothing outside its own tests for a week. A bound nothing calls reads as present and
is not, so these tests are as much about *who calls whom* as about arithmetic.
"""

from __future__ import annotations

import pytest

from wl_expcontroller import welfare as welfare_module
from wl_expcontroller.bounds import Bounds, Ceiling, Exceeded, Floor
from wl_expcontroller.dio import Simulated as Card
from wl_expcontroller.welfare import Absent, Deployment, Rig, Simulated, Welfare


def _bounds(daily_fluid: float = 250.0, **over: float) -> Bounds:
    """A rig's bounded config: a fluid floor and the out-of-cage ceiling.

    Twelve hours, because that is the institutional limit S8 §5.2 states. A
    fixture, not a protocol figure -- `tasks/reference_bounds.py` keeps its own
    number implausible on purpose, and this one never leaves the test suite.
    """
    ceilings = {
        "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
        "out_of_cage": Ceiling(value=43_200.0, maximum=43_200.0, unit="s"),
    }
    for name, value in over.items():
        ceiling = ceilings[name]
        ceilings[name] = Ceiling(value, ceiling.maximum, ceiling.unit)
    return Bounds(
        subject="A",
        ceilings=ceilings,
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


def _home_bounds(daily_fluid: float = 250.0) -> Bounds:
    """A cage-side config (S13): the same fluid floor and **no duration ceiling**.

    The animal never left home, so there is no out-of-cage interval for a ceiling to
    be about. That absence is declared by `Deployment.ANIMAL_AT_HOME` and never
    inferred from this dict being short an entry, which is the whole point of the
    declaration.
    """
    return Bounds(
        subject="A",
        ceilings={"reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL")},
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


def _welfare(already: float | None = 0.0, **over: float) -> Welfare:
    return Welfare(
        bounds=_bounds(**over),
        pump=Simulated(),
        already_today=already,
        deployment=Deployment.OUT_OF_CAGE,
    )


def _home_welfare(already: float | None = 0.0) -> Welfare:
    return Welfare(
        bounds=_home_bounds(),
        pump=Simulated(),
        already_today=already,
        deployment=Deployment.ANIMAL_AT_HOME,
    )


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

    welfare = Welfare(
        bounds=_bounds(),
        pump=Failing(),
        already_today=0.0,
        deployment=Deployment.OUT_OF_CAGE,
    )

    with pytest.raises(RuntimeError):
        welfare.deliver("reward_correct")

    assert welfare.commanded == 0.15


def test_an_absent_pump_refuses_rather_than_delivering_nothing():
    """The `dio.Absent` argument, one layer up: a session that runs a full protocol
    and dispenses nothing has worked an animal for no reward."""
    welfare = Welfare(
        bounds=_bounds(),
        pump=Absent(),
        already_today=0.0,
        deployment=Deployment.OUT_OF_CAGE,
    )

    with pytest.raises(RuntimeError, match="no pump"):
        welfare.deliver("reward_correct")


def test_a_bounded_config_without_a_daily_fluid_floor_refuses_to_start():
    """A missing floor is not a floor of zero. A session with no daily minimum can
    report no shortfall, so nobody would ever be told to supplement."""
    bounds = _bounds()
    del bounds.minima["daily_fluid"]

    with pytest.raises(Exceeded, match="daily_fluid"):
        Welfare(
            bounds=bounds,
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.OUT_OF_CAGE,
        )


def test_a_cage_side_config_without_a_daily_fluid_floor_refuses_too():
    """The floor is not the rig's alone. Kiosk fluid counts toward the same daily
    figure (S8 §5.2b), so a cage-side session that could report no shortfall is the
    same failure with nobody in the room to notice it."""
    bounds = _home_bounds()
    del bounds.minima["daily_fluid"]

    with pytest.raises(Exceeded, match="daily_fluid"):
        Welfare(
            bounds=bounds,
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.ANIMAL_AT_HOME,
        )


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


# --- the clock the limit is actually about ----------------------------------


def test_the_mark_precedes_session_zero_so_transport_and_chairing_count():
    """PI, 2026-09-19: *"a session from out of cage to back into cage cannot be
    longer than 12 hours"*. The clock ran from head-fixation until then, which
    under-counts by exactly the transport and chairing that precede it.

    **This is the test that makes the ruling real rather than renamed.** The
    session clock reads zero when the session starts, so the animal leaving its
    cage is at a *negative* instant in that base -- and nothing pinned that, which
    is how `wlx run` came to mark it at zero and report chair time under a new
    name. Five minutes of transport here, one minute of work: out-of-cage is six
    times chair time, and both start before the first trial."""
    welfare = _welfare()

    welfare.left_cage(seconds_ago=300.0, now=0.0)
    welfare.head_fixed(at=0.0)

    assert welfare.left_cage_at == pytest.approx(-300.0), "the mark is before zero"
    assert welfare.out_of_cage_seconds(now=60.0) == pytest.approx(360.0)
    assert welfare.chair_seconds(now=60.0) == pytest.approx(60.0)


def test_the_clock_reads_zero_at_the_moment_the_animal_leaves():
    """Its zero-point is the mark, not the session start. There is deliberately no
    "zero before the mark" case -- see
    `test_a_rig_session_with_no_out_of_cage_mark_refuses_rather_than_running_free`,
    which is what happens instead."""
    welfare = _welfare()

    welfare.left_cage(seconds_ago=0.0, now=100.0)

    assert welfare.out_of_cage_seconds(now=100.0) == 0.0


def test_an_animal_that_leaves_its_cage_in_the_future_is_refused():
    """The parameter is how long *ago*. A negative one is a mark nothing could have
    taken, and it would make the interval shorter than the session."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="future"):
        welfare.left_cage(seconds_ago=-60.0, now=0.0)


def test_a_wall_clock_handed_to_the_mark_is_refused():
    """**The time base is checked, not assumed.** A caller with a `time.time()` in
    hand and a parameter named for seconds is one substitution away from a mark
    fifty-seven years old, whose interval is enormous and whose `must_stop` would
    therefore fire on the first pass -- or, given the old signature, one whose
    *instant* was so far in the future that `must_stop` answered `None` forever.
    The subject's own ceiling is the bound, so the refusal is the same one a
    session already past twelve hours gets, and needs no sanity constant."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="wrong base"):
        welfare.left_cage(seconds_ago=1.79e9, now=0.0)


def test_a_session_that_starts_already_past_its_ceiling_is_refused():
    """The same refusal, reached honestly: an animal out of its cage for longer
    than the limit allows cannot begin a session inside it."""
    welfare = _welfare(out_of_cage=60.0)

    with pytest.raises(Exceeded, match="at or outside"):
        welfare.left_cage(seconds_ago=61.0, now=0.0)


def test_a_session_that_starts_exactly_at_its_ceiling_is_refused():
    """**The boundary belongs to the refusal, not to the session.** An animal out
    for exactly the limit has no room for a trial: the first one is already past
    it, and `left_cage` accepting this let a session run one trial and then stop.
    `must_stop` keeps `>` -- at exactly twelve hours nothing has been *longer* than
    twelve hours yet -- and the two now meet rather than overlapping by a trial."""
    welfare = _welfare(out_of_cage=60.0)

    with pytest.raises(Exceeded, match="at or outside"):
        welfare.left_cage(seconds_ago=60.0, now=0.0)


def test_a_mark_that_is_not_a_number_is_refused():
    """**NaN is `False` against every comparison, so it is not "in the future", not
    "past the ceiling" and not "backwards".** Each guard on this path is an ordered
    comparison, and one NaN walked through all of them: `left_cage_at` became NaN,
    `out_of_cage_seconds` returned NaN, and `must_stop`'s `nan > ceiling` is False,
    so it answered `None` for the whole session.

    Reproduced end to end through `wlx run --out-of-cage-ago nan`, whose `type=float`
    accepts it: four hundred rewarded trials, 13.55 mL, a clean summary, and no
    duration limit at all. `inf` breaks the same guards the other way -- ordered but
    unreachable -- and was *not* already refused; see
    `test_every_numeric_entry_point_refuses_an_infinity`."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.left_cage(seconds_ago=float("nan"), now=0.0)


def test_a_session_clock_that_is_not_a_number_is_refused_at_the_mark():
    """The other half of the same arithmetic: `left_cage_at = now - seconds_ago`,
    so a NaN on either side produces a NaN mark."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.left_cage(seconds_ago=0.0, now=float("nan"))


def test_a_duration_that_is_not_a_number_is_refused_when_it_is_read():
    """Guarded on the **computed duration**, not only on the marks, because that is
    the number every ceiling is read against and the last place a NaN can be caught
    before one is compared. Reached here by a clock handed in later; a `Welfare`
    built field-by-field rather than marked reaches it the same way."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.out_of_cage_seconds(now=float("nan"))


def test_an_infinite_mark_is_refused_like_any_other_non_number():
    """`inf` at the one door that always refused it -- `seconds_ago >= ceiling.value`
    is `True` for `inf` against a finite ceiling. That single case was mistaken for
    "`inf` is safe everywhere" through two review rounds; every other door is covered
    by `test_every_numeric_entry_point_refuses_an_infinity`."""
    welfare = _welfare()

    with pytest.raises(Exceeded):
        welfare.left_cage(seconds_ago=float("inf"), now=0.0)


def test_a_cage_side_session_cannot_be_marked_as_leaving_its_cage():
    """The declaration and the mark must not disagree, in either direction."""
    welfare = _home_welfare()

    with pytest.raises(Exceeded, match="at home"):
        welfare.left_cage(seconds_ago=0.0, now=0.0)


def test_putting_the_animal_back_closes_the_interval_and_ends_the_session():
    """**The closed clock is a stop, not a frozen number.**

    This asserted only the first line until a review reproduced the rest: closing
    the interval fixes it, and a fixed number is one no trial can move, so
    `must_stop` answered `None` for the whole rest of a session that reported
    itself fully marked. That is the missing-mark failure reached with both marks
    present. The interval still reports what it was -- the record needs it -- and
    the session is told to end."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=100.0)
    welfare.head_released(at=400.0)

    welfare.returned_to_cage(at=460.0)

    assert welfare.out_of_cage_seconds(now=9_999.0) == pytest.approx(360.0)
    assert "back in its cage" in welfare.must_stop(now=9_999.0)


def test_marking_a_return_while_the_animal_is_head_fixed_is_refused():
    """**Where the freeze is actually stopped.** An animal cannot be in the chair
    and in its cage at once, and this is the one call order that would otherwise
    close the clock mid-session -- `run()` head-fixes before its first frame and
    releases after its last, so the whole loop is inside this refusal. A session is
    ended with a `Stop`, not by recording the animal somewhere it is not."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)
    welfare.head_fixed(at=0.0)

    with pytest.raises(Exceeded, match="head-fixed"):
        welfare.returned_to_cage(at=100.0)


def test_a_return_before_the_animal_left_is_refused():
    """The reproduced Critical: `returned_to_cage(10)` then `left_cage` later gave
    a **negative** interval, which is under every ceiling there is -- so the limit
    switched off while the session reported both marks present."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=1_000.0)

    with pytest.raises(Exceeded, match="negative duration"):
        welfare.returned_to_cage(at=10.0)


def test_a_return_with_no_matching_departure_is_refused():
    """A session marked only at the end has no interval at all, and answering one
    would be inventing the departure."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="not recorded as having left"):
        welfare.returned_to_cage(at=10.0)


def test_a_second_return_is_refused():
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)
    welfare.returned_to_cage(at=400.0)

    with pytest.raises(Exceeded, match="already recorded as back"):
        welfare.returned_to_cage(at=100.0)


def test_a_closed_interval_is_never_re_armed():
    """**Out and back is one session** (PI, asked and answered 2026-09-20).

    The guard was `left_cage_at is not None and returned_at is None`, so a return
    re-armed the opening mark: out at 0, home at 43,000, out again at 43,100
    reported a fresh clock for an animal that had been out twenty-two hours.

    Whether that should instead *resume* a session was put to the PI rather than
    inferred from his wording, and he ruled it starts a new one -- accepting that an
    animal returned mid-day produces two session directories and two records rather
    than one with an unexplained gap. So this refusal is a ruling, not an
    arithmetic convenience, and changing it is a question for him."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)
    welfare.returned_to_cage(at=43_000.0)

    with pytest.raises(Exceeded, match="not re-armed"):
        welfare.left_cage(seconds_ago=0.0, now=43_100.0)


def test_a_clock_that_runs_backwards_is_refused():
    """With both marks guarded the only route left is a `now` before the opening
    mark -- a `Session(clock=...)` whose base is not the base the mark was taken
    in. A negative duration is under every ceiling, so answering it would be a
    limit switched off by arithmetic rather than by a missing mark."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=1_000.0)

    with pytest.raises(Exceeded, match="runs backwards"):
        welfare.out_of_cage_seconds(now=0.0)


def test_a_session_may_not_start_with_the_animal_already_home():
    """The closed-clock hole reached before the loop rather than during it: the
    marks are both present, the interval is fixed, and no trial could be inside
    it."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)
    welfare.returned_to_cage(at=100.0)
    welfare.head_fixed(at=200.0)

    with pytest.raises(Exceeded, match="already recorded as back"):
        welfare.preflight(now=0.0)


def test_taking_out_an_animal_that_is_already_out_is_refused():
    """`head_fixed`'s argument, on the clock that now bounds the session: two starts
    means one of the two is wrong, and the shorter one would silently win."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=100.0)

    with pytest.raises(Exceeded, match="already"):
        welfare.left_cage(seconds_ago=0.0, now=200.0)


def test_a_session_must_stop_at_the_out_of_cage_ceiling():
    welfare = _welfare(out_of_cage=60.0)
    welfare.left_cage(seconds_ago=0.0, now=0.0)

    assert welfare.must_stop(now=59.0) is None
    assert "out_of_cage" in welfare.must_stop(now=61.0)


def test_chair_time_is_recorded_and_bounds_nothing():
    """**Chair time stopped being a ceiling on 2026-09-19**, and `head_fixed` /
    `head_released` remain because their codes (4128/4129) are still the durable
    record of restraint (S8 §5.2). Ten hours in the chair, inside a twelve-hour
    out-of-cage window, is a session that runs on."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)
    welfare.head_fixed(at=0.0)

    assert welfare.chair_seconds(now=36_000.0) == pytest.approx(36_000.0)
    assert welfare.must_stop(now=36_000.0) is None


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


# --- there is no session-length maximum -------------------------------------


def test_nothing_ends_a_session_on_a_trial_count():
    """PI, 2026-09-19: *"the max trials idea makes no sense to me"*. Per-condition
    targets are `scheduler`'s `Counts`/`owed()`/`upcoming()` and always were; the
    session-level cap was the part with no meaning. A bounded config written before
    the ruling still carries `max_trials`, and nothing reads it."""
    bounds = _bounds()
    bounds.ceilings["max_trials"] = Ceiling(value=1.0, maximum=1.0, unit="trials")
    welfare = Welfare(
        bounds=bounds,
        pump=Simulated(),
        already_today=0.0,
        deployment=Deployment.OUT_OF_CAGE,
    )
    welfare.left_cage(seconds_ago=0.0, now=0.0)

    assert welfare.must_stop(now=1.0) is None
    assert not hasattr(welfare_module, "MAX_TRIALS"), "the concept came back"


# --- a missing mark must never disable a limit ------------------------------


def test_a_rig_session_with_no_out_of_cage_mark_refuses_rather_than_running_free():
    """**The absence of a mark must never silently disable a welfare limit.** A
    session whose out-of-cage time nobody recorded is one a person forgot to mark,
    not one the animal is home for -- and answering zero would run it unbounded for
    as long as it liked. `dio.Absent`, `welfare.Absent` and `run.Unwired` all refuse
    rather than quietly doing nothing; this is that shape on the duration path, and
    it refuses on *every* call rather than only at preflight, because a limit that
    can be switched off by forgetting is not a limit."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="out of its cage"):
        welfare.preflight(now=0.0)

    with pytest.raises(Exceeded, match="out of its cage"):
        welfare.must_stop(now=100_000.0)


def test_a_rig_session_still_refuses_to_run_before_the_animal_is_head_fixed():
    """S8 §5.2's preflight requirement, kept. Chair time stopped bounding the
    session on 2026-09-19; it did not stop being what the event codes record, and a
    rig session with no `HEAD_FIXED` in the stream has no record of restraint at
    all."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)

    with pytest.raises(Exceeded, match="head-fixed"):
        welfare.preflight(now=0.0)


def test_a_marked_rig_session_passes_preflight():
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)
    welfare.head_fixed(at=100.0)

    assert welfare.preflight(now=0.0) is None


def test_a_cage_side_session_declares_that_it_has_no_duration_bound():
    """S13: the animal never left home, so there is no out-of-cage event and no
    head-fixation, and the PI chose no time-based limit cage-side. The session says
    so with `Deployment.ANIMAL_AT_HOME` -- explicit, greppable, and impossible to
    arrive at by forgetting, which is the difference between a limit nobody set and
    a limit nobody marked."""
    welfare = _home_welfare()

    assert welfare.preflight(now=0.0) is None
    assert welfare.out_of_cage_seconds(now=100_000.0) is None
    assert welfare.must_stop(now=100_000.0) is None


def test_a_rig_config_with_no_out_of_cage_ceiling_refuses_to_start():
    """A missing limit is not an absent one. A bounded config stating no duration
    ceiling for an animal that left its cage is one nobody finished."""
    bounds = _bounds()
    del bounds.ceilings["out_of_cage"]

    with pytest.raises(Exceeded, match="out_of_cage"):
        Welfare(
            bounds=bounds,
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.OUT_OF_CAGE,
        )


def test_a_cage_side_session_carrying_a_duration_ceiling_is_refused():
    """The declaration and the config must not disagree. A bounded config stating a
    twelve-hour limit, under a deployment declaring that the limit does not apply,
    is a limit switched off by a flag -- the failure the declaration exists to
    prevent, arrived at from the other side."""
    bounds = _home_bounds()
    bounds.ceilings["out_of_cage"] = Ceiling(43_200.0, 43_200.0, "s")

    with pytest.raises(Exceeded, match="out_of_cage"):
        Welfare(
            bounds=bounds,
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.ANIMAL_AT_HOME,
        )


def test_a_reward_volume_of_exactly_zero_is_accepted_and_the_day_still_reports_it():
    """**Pinned as current behaviour, not endorsed — a question for the PI.**

    Zero is a quantity, so neither `_finite` nor `_magnitude` refuses it: they
    refuse values that are not quantities. But a console setting a reward volume to
    zero mid-session makes every subsequent correct trial unpaid, which is
    `welfare.Absent`'s failure reached by another route.

    What saves it from being silent is the day's accounting, asserted here: the
    animal earns nothing, and `shortfall()` reports the whole floor as still owed,
    so a person is told to supplement it. The console also shows `fluid session:
    0.00 mL` throughout.

    Whether a zero volume is ever legitimate is animal-facing, so it is asked
    rather than assumed (CLAUDE.md, "ask, do not file"). If the answer is no, the
    refusal belongs in `Bounds.validate` beside the negative one, and this test
    inverts. S8 §5.2c carries the question.
    """
    bounds = _bounds()
    bounds.ceilings["reward_correct"] = Ceiling(0.0, 0.40, "mL")
    welfare = Welfare(
        bounds=bounds,
        pump=Simulated(),
        already_today=0.0,
        deployment=Deployment.OUT_OF_CAGE,
    )

    for _ in range(20):
        welfare.deliver("reward_correct")

    assert welfare.pump.delivered == [0.0] * 20, "twenty trials, no fluid"
    assert welfare.shortfall() == pytest.approx(250.0), (
        "the day's accounting must still report the whole floor as owed"
    )


def test_a_cage_side_session_pays_and_counts_the_day_like_any_other():
    """One mechanism across rig and kiosk (S13 §4). What a kiosk session lacks is
    the duration bound, not the fluid accounting -- the daily figure is shared."""
    welfare = _home_welfare(already=100.0)

    welfare.deliver("reward_correct")

    assert welfare.pump.delivered == [0.15]
    assert welfare.shortfall() == pytest.approx(149.85)


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
        welfare=Welfare(
            bounds=_bounds(),
            pump=Failing(),
            already_today=0.0,
            deployment=Deployment.OUT_OF_CAGE,
        ),
    )

    with pytest.raises(RuntimeError, match="solenoid"):
        rig.reward("reward_correct")


# ---------------------------------------------------------------------------
# Every number that enters the welfare path, and the proof that this is all of
# them
# ---------------------------------------------------------------------------
#
# **Three Criticals in three review rounds were one class of defect, found one
# surface at a time**: a guard on a *limit* while the *measurement* compared
# against it went unchecked. `nan` defeats every ordered comparison by being
# `False` against all of them, `inf` by being unreachable, and a negative
# magnitude by passing a `>` that expects a quantity. Fixing each surface where it
# was found is why there were three rounds.
#
# So the surface is enumerated rather than sampled, and the enumeration is
# **checked by code rather than asserted**. `ENTRY_POINTS` names every way a
# number reaches `welfare` or `bounds` from outside the process;
# `test_the_enumeration_of_numeric_entry_points_is_complete` recomputes that set
# from the live modules and fails if anything is in neither list. Adding a
# float-taking method to either welfare-critical file therefore fails this suite
# until it is guarded and listed, or listed as exempt with a reason -- the same
# shape as `tools/mutation_gate.py`, which refuses to run when a module is in
# neither of its lists.
#
# **What would have to be true for one to be missing**, stated so the claim is
# falsifiable rather than confident: a number would have to reach a comparison in
# `bounds` or `welfare` without passing through any float-annotated parameter or
# field of those two modules. There are exactly two such routes. One is an
# unannotated parameter -- the introspection below reads annotations, so an
# unannotated float is invisible to it, which is why `test_every_numeric_parameter_
# is_annotated` exists. The other is arithmetic: two checked values can produce an
# unchecked third, which is why `out_of_cage_seconds` checks the *computed*
# duration and `reconcile_report` checks both inputs rather than trusting that
# guarded inputs give a guarded result.

import dataclasses
import inspect

from wl_expcontroller import bounds as bounds_module

#: A magnitude is finite and non-negative; an instant is merely finite. Every entry
#: point below is one or the other, and that distinction is the rule the earlier
#: rounds were missing: -0.5 mL passed every `>` in the file.
MAGNITUDE = "magnitude"
INSTANT = "instant"

#: Where a magnitude's negative refusal is worded for its own parameter rather than
#: by `_magnitude`. `seconds_ago` is the one: "left its cage in the future" tells an
#: operator what is wrong, where "cannot be negative" would only say that it is.
NEGATIVE_MESSAGE = {"Welfare.left_cage.seconds_ago": "in the future"}

#: How to drive each numeric entry point with a bad value, and which rule it is
#: under. Each callable arranges a subject so the value is the only thing wrong.
ENTRY_POINTS = {
    # --- bounds: the limits themselves --------------------------------------
    "Ceiling.value": (MAGNITUDE, lambda v: Ceiling(value=v, maximum=10.0, unit="s")),
    "Ceiling.maximum": (MAGNITUDE, lambda v: Ceiling(value=1.0, maximum=v, unit="s")),
    "Floor.value": (MAGNITUDE, lambda v: Floor(value=v, unit="mL")),
    # --- bounds: what a console offers, and what a day measured -------------
    "Bounds.validate.value": (
        MAGNITUDE,
        lambda v: _bounds().validate("reward_correct", v),
    ),
    "Bounds.set.value": (
        MAGNITUDE,
        lambda v: _bounds().set("reward_correct", v, by="jake"),
    ),
    "Bounds.shortfall.delivered_today": (
        MAGNITUDE,
        lambda v: _bounds().shortfall("daily_fluid", v),
    ),
    "reconcile_report.commanded": (
        MAGNITUDE,
        lambda v: bounds_module.reconcile_report(v, 1.0),
    ),
    "reconcile_report.delivered": (
        MAGNITUDE,
        lambda v: bounds_module.reconcile_report(1.0, v),
    ),
    "reconcile.commanded": (MAGNITUDE, lambda v: bounds_module.reconcile(v, 1.0)),
    "reconcile.delivered": (MAGNITUDE, lambda v: bounds_module.reconcile(1.0, v)),
    # --- welfare: the day's fluid -------------------------------------------
    "Welfare.already_today": (MAGNITUDE, lambda v: _welfare(already=v)),
    "Welfare.commanded": (
        MAGNITUDE,
        lambda v: Welfare(
            bounds=_bounds(),
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.OUT_OF_CAGE,
            commanded=v,
        ),
    ),
    "Welfare.delivered": (
        MAGNITUDE,
        lambda v: Welfare(
            bounds=_bounds(),
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.OUT_OF_CAGE,
            delivered=v,
        ),
    ),
    "Welfare.confirm_already_today.total": (
        MAGNITUDE,
        lambda v: _welfare().confirm_already_today(v, by="jake"),
    ),
    "Welfare.reconcile.delivered": (MAGNITUDE, lambda v: _welfare().reconcile(v)),
    # --- welfare: the clocks -------------------------------------------------
    "Welfare.left_cage.seconds_ago": (
        MAGNITUDE,
        lambda v: _welfare().left_cage(seconds_ago=v, now=0.0),
    ),
    "Welfare.left_cage.now": (
        INSTANT,
        lambda v: _welfare().left_cage(seconds_ago=0.0, now=v),
    ),
    "Welfare.returned_to_cage.at": (
        INSTANT,
        lambda v: _welfare().returned_to_cage(v),
    ),
    "Welfare.head_fixed.at": (INSTANT, lambda v: _welfare().head_fixed(v)),
    "Welfare.head_released.at": (INSTANT, lambda v: _welfare().head_released(v)),
    "Welfare.chair_seconds.now": (INSTANT, lambda v: _welfare().chair_seconds(v)),
    "Welfare.out_of_cage_seconds.now": (
        INSTANT,
        lambda v: _marked().out_of_cage_seconds(v),
    ),
    "Welfare.preflight.now": (INSTANT, lambda v: _marked().preflight(v)),
    "Welfare.must_stop.now": (INSTANT, lambda v: _marked().must_stop(v)),
}

#: Numeric surface that is deliberately *not* an entry point, each with its reason.
#: An entry here is a claim someone made, which is the point: the alternative is a
#: parameter quietly absent from both lists.
NOT_ENTRY_POINTS = {
    "_finite.value": "the guard itself",
    "_magnitude.value": "the guard itself",
    "Welfare.deliveries": "a counter this module increments; never supplied",
    "Reconciliation.total": "an output, computed from checked inputs",
    "Reconciliation.commanded": "an output; see above",
    "Reconciliation.delivered": "an output; see above",
    "Reconciliation.unexplained": "an output; see above",
    "Welfare.left_cage_at": (
        "set only by left_cage, which checks it. A Welfare constructed around this "
        "field bypasses that, which out_of_cage_seconds still catches for non-finite "
        "and backwards values -- see the field's own comment"
    ),
    "Welfare.returned_at": "set only by returned_to_cage, which checks it",
    "Welfare.fixed_at": "set only by head_fixed, which checks it",
    "Welfare.released_at": "set only by head_released, which checks it",
    "Pump.deliver.ml": "a volume leaving this module, already checked by its ceiling",
    "Simulated.deliver.ml": "as Pump.deliver",
    "Absent.deliver.ml": "as Pump.deliver; refuses unconditionally anyway",
    "Rig.mark.code": "an event code, not a welfare quantity; dio owns its range",
}


def _marked() -> Welfare:
    """A rig `Welfare` with its interval open, so a clock call is the only fault."""
    welfare = _welfare()
    welfare.left_cage(seconds_ago=0.0, now=0.0)
    return welfare


def _is_numeric(annotation) -> bool:
    text = annotation if isinstance(annotation, str) else str(annotation)
    return "float" in text or text.strip() in ("int", "<class 'int'>")


def _numeric_params(label: str, fn) -> set:
    hints = getattr(fn, "__annotations__", {})
    return {
        f"{label}.{p}"
        for p in inspect.signature(fn).parameters
        if p not in ("self", "cls") and _is_numeric(hints.get(p))
    }


def _numeric_surface() -> set:
    """Every float-annotated parameter and field of the welfare-critical modules.

    Read from the live modules rather than from a list, so that `ENTRY_POINTS` is
    checked and not merely believed.
    """
    found = set()
    for module in (bounds_module, welfare_module):
        for name, obj in vars(module).items():
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            if inspect.isfunction(obj):
                found |= _numeric_params(name, obj)
            elif inspect.isclass(obj):
                if dataclasses.is_dataclass(obj):
                    found |= {
                        f"{name}.{f.name}"
                        for f in dataclasses.fields(obj)
                        if _is_numeric(f.type)
                    }
                for attr, value in vars(obj).items():
                    if inspect.isfunction(value) and not attr.startswith("__"):
                        found |= _numeric_params(f"{name}.{attr}", value)
    return found


def test_the_enumeration_of_numeric_entry_points_is_complete():
    """**The claim that `ENTRY_POINTS` is all of them, checked rather than asserted.**

    Three review rounds found one class of defect on three surfaces, because each
    was fixed where it was found. This recomputes the numeric surface of both
    welfare-critical modules and fails if anything on it is in neither list -- so a
    new float-taking method cannot be added without either guarding it or writing
    down why it needs none.
    """
    declared = set(ENTRY_POINTS) | set(NOT_ENTRY_POINTS)
    actual = _numeric_surface()

    missing = actual - declared
    assert not missing, (
        f"numeric entry points in neither ENTRY_POINTS nor NOT_ENTRY_POINTS: "
        f"{sorted(missing)}. Guard it and list it, or list it as exempt with the "
        f"reason -- an unlisted one is how the last three Criticals each reached a "
        f"comparison"
    )

    stale = declared - actual
    assert not stale, f"listed but no longer present: {sorted(stale)}"


def test_every_numeric_parameter_is_annotated():
    """The one blind spot of the introspection above, closed.

    `_numeric_surface` reads annotations, so an *unannotated* float parameter would
    be invisible to it -- the enumeration would look complete while missing a door.
    Every parameter of every public callable in both files must therefore carry an
    annotation, whatever its type.
    """
    unannotated = []
    for module in (bounds_module, welfare_module):
        for name, obj in vars(module).items():
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            # Dunders are excluded for the same reason `_numeric_surface` excludes
            # them: `dataclass`, `Enum` and `Protocol` generate `__eq__`,
            # `__setattr__`, `__replace__` and friends without annotations, and
            # none of them can carry a float an author wrote.
            callables = [(name, obj)] if inspect.isfunction(obj) else [
                (f"{name}.{a}", v)
                for a, v in vars(obj).items()
                if inspect.isfunction(v) and not a.startswith("__")
            ]
            for label, fn in callables:
                hints = getattr(fn, "__annotations__", {})
                for p in inspect.signature(fn).parameters:
                    if p not in ("self", "cls") and p not in hints:
                        unannotated.append(f"{label}.{p}")

    assert not unannotated, (
        f"unannotated parameters in a welfare-critical file: {sorted(unannotated)}. "
        f"The entry-point enumeration reads annotations, so an unannotated float is "
        f"a door it cannot see"
    )


@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
def test_every_numeric_entry_point_refuses_a_value_that_is_not_a_number(entry):
    """`nan` at every door, one case per door."""
    _, drive = ENTRY_POINTS[entry]

    with pytest.raises(Exceeded, match="not a real number"):
        drive(float("nan"))


@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
def test_every_numeric_entry_point_refuses_an_infinity(entry):
    """`inf` too, for its own reason: it is ordered but unreachable, so an `inf`
    ceiling is never exceeded by any real duration. A docstring claimed `inf` was
    already refused everywhere; it was refused at exactly one door."""
    _, drive = ENTRY_POINTS[entry]

    with pytest.raises(Exceeded):
        drive(float("inf"))


@pytest.mark.parametrize(
    "entry",
    sorted(name for name, (rule, _) in ENTRY_POINTS.items() if rule == MAGNITUDE),
)
def test_every_magnitude_refuses_a_negative_value(entry):
    """A volume or a duration is a quantity of something, and `-0.5 mL` was accepted
    through the real console path and commanded to the pump twenty times."""
    _, drive = ENTRY_POINTS[entry]
    expected = NEGATIVE_MESSAGE.get(entry, "cannot be negative")

    with pytest.raises(Exceeded, match=expected):
        drive(-1.0)
