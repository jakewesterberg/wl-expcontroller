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
    be about. That absence is declared by `Deployment.CAGE_SIDE` and never
    inferred from this dict being short an entry, which is the whole point of the
    declaration.
    """
    return Bounds(
        subject="A",
        ceilings={"reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL")},
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


#: A fixed wall-clock instant for the mark tests, in POSIX seconds. The mark became
#: a clock time on 2026-09-20 (PI), so every test that takes one supplies both ends
#: of the mapping -- the departure and the wall clock the session read it against --
#: rather than letting a real clock into the suite. Only the differences matter.
WALL_NOW = 1_700_000_000.0


def _welfare(already: float | None = 0.0, **over: float) -> Welfare:
    return Welfare(
        bounds=_bounds(**over),
        pump=Simulated(),
        already_today=already,
        deployment=Deployment.RIG_FIXED,
    )


def _chaired_welfare(already: float | None = 0.0, **over: float) -> Welfare:
    """A rig session with no head-fixation: the animal is chaired and unfixed.

    **Restrained, and with no restraint marks**, which is the whole reason this kind
    exists as a declaration rather than as a rig session missing something.
    """
    return Welfare(
        bounds=_bounds(**over),
        pump=Simulated(),
        already_today=already,
        deployment=Deployment.RIG_CHAIRED,
    )


def _home_welfare(already: float | None = 0.0) -> Welfare:
    return Welfare(
        bounds=_home_bounds(),
        pump=Simulated(),
        already_today=already,
        deployment=Deployment.CAGE_SIDE,
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
        deployment=Deployment.RIG_FIXED,
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
        deployment=Deployment.RIG_FIXED,
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
            deployment=Deployment.RIG_FIXED,
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
            deployment=Deployment.CAGE_SIDE,
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

    welfare.left_cage(at=WALL_NOW - 300.0, wall_now=WALL_NOW, now=0.0)
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

    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=100.0)

    assert welfare.out_of_cage_seconds(now=100.0) == 0.0


def test_an_animal_that_leaves_its_cage_in_the_future_is_refused():
    """A departure later than the clock the session is reading is a mark nothing
    could have taken, and it would make the interval shorter than the session.

    **This guard changed job on 2026-09-20 and kept its wording.** It caught a
    negative "how long ago" then; it catches a clock time later than now since. It is
    also the one of the two replacement guards that does the new work: a bare `23:59`
    typed in the morning is in the future, and is refused rather than rolled back to
    yesterday and accepted as a departure twenty-three hours old."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="future"):
        welfare.left_cage(at=WALL_NOW + 60.0, wall_now=WALL_NOW, now=0.0)


def test_a_departure_before_the_epoch_is_refused_by_the_ceiling():
    """**What is left of the wall-clock catch, and what it became.**

    Until 2026-09-20 the parameter was an interval, so `time.time()` handed to it was
    a mark fifty-seven years old and the ceiling refused it as an absurd duration.
    The parameter is a wall-clock instant now, so 1.7e9 is simply *now* and that
    catch is gone -- a cost the PI was shown and accepted. A value that is absurd as
    an *instant* still lands in the same refusal, by the same arithmetic: the
    interval it implies is longer ago than the subject's ceiling."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="against a ceiling of"):
        welfare.left_cage(at=0.0, wall_now=WALL_NOW, now=0.0)


def test_a_session_that_starts_already_past_its_ceiling_is_refused():
    """The same refusal, reached honestly: an animal out of its cage for longer
    than the limit allows cannot begin a session inside it."""
    welfare = _welfare(out_of_cage=60.0)

    with pytest.raises(Exceeded, match="at or outside"):
        welfare.left_cage(at=WALL_NOW - 61.0, wall_now=WALL_NOW, now=0.0)


def test_a_session_that_starts_exactly_at_its_ceiling_is_refused():
    """**The boundary belongs to the refusal, not to the session.** An animal out
    for exactly the limit has no room for a trial: the first one is already past
    it, and `left_cage` accepting this let a session run one trial and then stop.
    `must_stop` keeps `>` -- at exactly twelve hours nothing has been *longer* than
    twelve hours yet -- and the two now meet rather than overlapping by a trial."""
    welfare = _welfare(out_of_cage=60.0)

    with pytest.raises(Exceeded, match="at or outside"):
        welfare.left_cage(at=WALL_NOW - 60.0, wall_now=WALL_NOW, now=0.0)


def test_a_mark_that_is_not_a_number_is_refused():
    """**NaN is `False` against every comparison, so it is not "in the future", not
    "past the ceiling" and not "backwards".** Each guard on this path is an ordered
    comparison, and one NaN walked through all of them: `left_cage_at` became NaN,
    `out_of_cage_seconds` returned NaN, and `must_stop`'s `nan > ceiling` is False,
    so it answered `None` for the whole session.

    Reproduced end to end through `wlx run --out-of-cage-ago nan`, whose `type=float`
    accepted it: four hundred rewarded trials, 13.55 mL, a clean summary, and no
    duration limit at all. That flag became `--out-of-cage-at TIME` on 2026-09-20, so
    the command line can no longer produce a NaN at all -- but every other caller
    still can, which is why this door stays guarded rather than being declared closed
    by a parser. `inf` breaks the same guards the other way -- ordered but
    unreachable -- and was *not* already refused; see
    `test_every_numeric_entry_point_refuses_an_infinity`."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.left_cage(at=WALL_NOW - float("nan"), wall_now=WALL_NOW, now=0.0)


def test_a_session_clock_that_is_not_a_number_is_refused_at_the_mark():
    """The other half of the same arithmetic: `left_cage_at = now - (wall_now - at)`,
    so a NaN on any of the three produces a NaN mark."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=float("nan"))


def test_a_duration_that_is_not_a_number_is_refused_when_it_is_read():
    """Guarded on the **computed duration**, not only on the marks, because that is
    the number every ceiling is read against and the last place a NaN can be caught
    before one is compared. Reached here by a clock handed in later; a `Welfare`
    built field-by-field rather than marked reaches it the same way."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.out_of_cage_seconds(now=float("nan"))


def test_an_infinite_mark_is_refused_like_any_other_non_number():
    """`inf` at the one door that always refused it -- the implied interval is `inf`,
    and `inf >= ceiling.value` is `True` against a finite ceiling. That single case
    was mistaken for "`inf` is safe everywhere" through two review rounds; every
    other door is covered by `test_every_numeric_entry_point_refuses_an_infinity`."""
    welfare = _welfare()

    with pytest.raises(Exceeded):
        welfare.left_cage(at=WALL_NOW - float("inf"), wall_now=WALL_NOW, now=0.0)


def test_a_cage_side_session_cannot_be_marked_as_leaving_its_cage():
    """The declaration and the mark must not disagree, in either direction."""
    welfare = _home_welfare()

    with pytest.raises(Exceeded, match="at home"):
        welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)


def test_putting_the_animal_back_closes_the_interval_and_ends_the_session():
    """**The closed clock is a stop, not a frozen number.**

    This asserted only the first line until a review reproduced the rest: closing
    the interval fixes it, and a fixed number is one no trial can move, so
    `must_stop` answered `None` for the whole rest of a session that reported
    itself fully marked. That is the missing-mark failure reached with both marks
    present. The interval still reports what it was -- the record needs it -- and
    the session is told to end.

    The head is fixed before it is released, which it was not until 2026-09-20 --
    the release was incidental scaffolding here (`returned_to_cage` refuses only a
    head that is fixed *and not* released, and this one was never fixed), and
    `head_released` now refuses a release with nothing to release. Marked properly
    rather than deleted, because the real order is what this test is standing in
    for."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=100.0)
    welfare.head_fixed(at=110.0)
    welfare.head_released(at=400.0)

    welfare.returned_to_cage(at=WALL_NOW + 360.0, wall_now=WALL_NOW + 400.0)

    assert welfare.out_of_cage_seconds(now=9_999.0) == pytest.approx(360.0)
    assert "back in its cage" in welfare.must_stop(now=9_999.0)


def test_marking_a_return_while_the_animal_is_head_fixed_is_refused():
    """**Where the freeze is actually stopped.** An animal cannot be in the chair
    and in its cage at once, and this is the one call order that would otherwise
    close the clock mid-session -- `run()` head-fixes before its first frame and
    releases after its last, so the whole loop is inside this refusal. A session is
    ended with a `Stop`, not by recording the animal somewhere it is not."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    welfare.head_fixed(at=0.0)

    with pytest.raises(Exceeded, match="head-fixed"):
        welfare.returned_to_cage(at=WALL_NOW + 100.0, wall_now=WALL_NOW + 100.0)


def test_a_return_before_the_animal_left_is_refused():
    """The reproduced Critical: `returned_to_cage(10)` then `left_cage` later gave
    a **negative** interval, which is under every ceiling there is -- so the limit
    switched off while the session reported both marks present."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=1_000.0)

    with pytest.raises(Exceeded, match="negative duration"):
        welfare.returned_to_cage(at=WALL_NOW - 10.0, wall_now=WALL_NOW)


def test_a_return_with_no_matching_departure_is_refused():
    """A session marked only at the end has no interval at all, and answering one
    would be inventing the departure."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="not recorded as having left"):
        welfare.returned_to_cage(at=WALL_NOW, wall_now=WALL_NOW)


def test_a_second_return_is_refused():
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    welfare.returned_to_cage(at=WALL_NOW + 400.0, wall_now=WALL_NOW + 400.0)

    with pytest.raises(Exceeded, match="already recorded as back"):
        welfare.returned_to_cage(at=WALL_NOW + 100.0, wall_now=WALL_NOW + 400.0)


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
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    welfare.returned_to_cage(
        at=WALL_NOW + 43_000.0, wall_now=WALL_NOW + 43_000.0, confirmed=True
    )

    with pytest.raises(Exceeded, match="not re-armed"):
        welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=43_100.0)


def test_a_clock_that_runs_backwards_is_refused():
    """With both marks guarded the only route left is a `now` before the opening
    mark -- a `Session(clock=...)` whose base is not the base the mark was taken
    in. A negative duration is under every ceiling, so answering it would be a
    limit switched off by arithmetic rather than by a missing mark."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=1_000.0)

    with pytest.raises(Exceeded, match="runs backwards"):
        welfare.out_of_cage_seconds(now=0.0)


def test_a_session_may_not_start_with_the_animal_already_home():
    """The closed-clock hole reached before the loop rather than during it: the
    marks are both present, the interval is fixed, and no trial could be inside
    it."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    welfare.returned_to_cage(at=WALL_NOW + 100.0, wall_now=WALL_NOW + 100.0)
    welfare.head_fixed(at=200.0)

    with pytest.raises(Exceeded, match="already recorded as back"):
        welfare.preflight(now=0.0)


def test_taking_out_an_animal_that_is_already_out_is_refused():
    """`head_fixed`'s argument, on the clock that now bounds the session: two starts
    means one of the two is wrong, and the shorter one would silently win."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=100.0)

    with pytest.raises(Exceeded, match="already"):
        welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=200.0)


def test_a_session_must_stop_at_the_out_of_cage_ceiling():
    welfare = _welfare(out_of_cage=60.0)
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    assert welfare.must_stop(now=59.0) is None
    assert "out_of_cage" in welfare.must_stop(now=61.0)


def test_chair_time_is_recorded_and_bounds_nothing():
    """**Chair time stopped being a ceiling on 2026-09-19**, and `head_fixed` /
    `head_released` remain because their codes (4128/4129) are still the durable
    record of restraint (S8 §5.2). Ten hours in the chair, inside a twelve-hour
    out-of-cage window, is a session that runs on."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
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
        deployment=Deployment.RIG_FIXED,
    )
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

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
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    with pytest.raises(Exceeded, match="head-fixed"):
        welfare.preflight(now=0.0)


def test_a_marked_rig_session_passes_preflight():
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    welfare.head_fixed(at=100.0)

    assert welfare.preflight(now=0.0) is None


def test_a_cage_side_session_declares_that_it_has_no_duration_bound():
    """S13: the animal never left home, so there is no out-of-cage event and no
    head-fixation, and the PI chose no time-based limit cage-side. The session says
    so with `Deployment.CAGE_SIDE` -- explicit, greppable, and impossible to
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
            deployment=Deployment.RIG_FIXED,
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
            deployment=Deployment.CAGE_SIDE,
        )


def test_a_reward_volume_of_exactly_zero_is_allowed_because_it_is_visible():
    """**Allowed — PI, asked and answered 2026-09-20.** Not merely current behaviour.

    Zero is a quantity, so neither `_finite` nor `_magnitude` refuses it: they
    refuse values that are not quantities. The question put to the PI was whether a
    *policy* refusal belonged on top, because a console setting the volume to zero
    mid-session leaves every subsequent correct trial unpaid -- `welfare.Absent`'s
    failure reached by another route.

    **His ruling: allow it, because it is not silent**, and it is a legitimate
    operational move -- pausing reward without ending a session. The consequence he
    weighed and accepted is that an animal working correctly is paid nothing while
    it holds.

    **The visibility is therefore the condition of the ruling, not a nicety.** Both
    halves are asserted below: the day's accounting reports the whole floor as still
    owed, so the supplement figure stays correct, and `cli.render` shows `fluid
    session: 0.00 mL` throughout. Anything that stopped reporting either would turn
    a permitted operation into a silent one. `cli.render`, `link.Telemetry` and
    S9a §9 all carry that sentence, because a session simplifying a console pane is
    where it would be lost.

    **This is the one place a magnitude of zero is deliberately allowed on the
    welfare path.** The rule -- *a magnitude is finite and not negative* -- is
    unchanged and has no exception; what sits on top of it is a policy choice about
    zero for this one quantity. S8 §5.2c carries the ruling.
    """
    bounds = _bounds()
    bounds.ceilings["reward_correct"] = Ceiling(0.0, 0.40, "mL")
    welfare = Welfare(
        bounds=bounds,
        pump=Simulated(),
        already_today=0.0,
        deployment=Deployment.RIG_FIXED,
    )

    for _ in range(20):
        welfare.deliver("reward_correct")

    assert welfare.pump.delivered == [0.0] * 20, "twenty trials, no fluid"
    # The two numbers the ruling rests on. `session_total()` is what
    # `link.Telemetry.fluid_session_ml` reads and `cli.render` prints as "fluid
    # session"; `shortfall()` is what both it and `wlx run` print as "supplement".
    assert welfare.session_total() == 0.0, (
        "the console must show the operator that nothing is being paid"
    )
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


# --- the mark is a clock time, and the three deployment kinds ---------------


def test_the_departure_is_a_clock_time_mapped_onto_the_session_clock():
    """**A clock time is what an operator reads** (PI, 2026-09-20).

    The parameter was `seconds_ago` until then, which is a number nobody holds: an
    operator knows the animal came out at 08:45, not that it came out 9,143 seconds
    ago. The arithmetic that turns one into the other lives here rather than in a
    caller, so there is one place where the two time bases meet -- `at` and
    `wall_now` are on the wall clock, `now` is the frame-derived session clock, and
    the mark still lands at a negative instant in the latter.
    """
    welfare = _welfare()

    welfare.left_cage(at=WALL_NOW - 300.0, wall_now=WALL_NOW, now=0.0)

    assert welfare.left_cage_at == pytest.approx(-300.0), "the mark is before zero"
    assert welfare.out_of_cage_seconds(now=60.0) == pytest.approx(360.0)


def test_a_departure_later_than_the_wall_clock_is_refused():
    """**The replacement for the guard the clock time cost us** (PI, 2026-09-20).

    A 1.7e9-second *interval* was self-evidently absurd and the ceiling caught it; a
    1.7e9 *instant* is simply now, so that catch is gone. What replaces it is a
    comparison against the wall clock this session is reading: a departure later than
    the present is a mark nothing could have taken.
    """
    welfare = _welfare()

    with pytest.raises(Exceeded, match="in the future"):
        welfare.left_cage(at=WALL_NOW + 60.0, wall_now=WALL_NOW, now=0.0)


def test_a_departure_longer_ago_than_the_ceiling_is_still_refused():
    """The second replacement, and it is the refusal that already existed: a session
    cannot start at or outside the limit it is bounded by. It still catches the gross
    error -- a date typed a day early, a clock an operator's phone was in -- which is
    why the PI accepted losing the wall-clock catch above."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="against a ceiling of"):
        welfare.left_cage(at=WALL_NOW - 43_300.0, wall_now=WALL_NOW, now=0.0)


def test_a_wall_clock_that_is_not_a_number_is_refused_at_the_mark():
    """Both wall-clock readings are instants, and the interval computed from them is
    a third value neither guard covers (S8 §5.2c's own rule: arithmetic on two
    checked values can still produce an unchecked one)."""
    welfare = _welfare()

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.left_cage(at=float("nan"), wall_now=WALL_NOW, now=0.0)


def test_a_chaired_session_reports_chair_time_absent_rather_than_zero():
    """**The trap this repository has a scar from** (PI, 2026-09-20).

    A chaired-but-unfixed animal *is* restrained; it simply has no head-fixation
    marks. `0.00` here would be `shortfall()` answering `0` for a day nobody measured
    in a different costume -- a welfare quantity reported as a measured zero when
    nothing measured it. `None` is the only honest answer, and the console renders it
    as *unmeasured*, not as a clock at zero.
    """
    welfare = _chaired_welfare()
    welfare.left_cage(
        at=WALL_NOW - 3_600.0, wall_now=WALL_NOW, now=0.0, confirmed=True
    )

    assert welfare.chair_seconds(now=3_600.0) is None


def test_a_cage_side_session_reports_chair_time_absent_too():
    """For the other reason: the animal never left home, so there is no restraint at
    all. Both answer `None`; the console says which, because *the animal is home* and
    *chaired and unfixed* are different facts about an animal."""
    assert _home_welfare().chair_seconds(now=3_600.0) is None


def test_a_head_fixed_session_still_reports_chair_time_as_a_number():
    """The kind that has the marks keeps the number. `RIG_FIXED` is the only one of
    the three where `chair_seconds` is a measurement rather than an absence."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    welfare.head_fixed(at=0.0)

    assert welfare.chair_seconds(now=600.0) == pytest.approx(600.0)


def test_a_chaired_session_refuses_a_head_fixation_mark():
    """The declaration binds in both directions, as it already does for the cage-side
    kind: a deployment that states it takes no head-fixation marks cannot then record
    one. Without this, `chair_seconds` answering `None` would be discarding a
    measurement somebody took rather than reporting one nobody could."""
    welfare = _chaired_welfare()

    with pytest.raises(Exceeded, match="takes no head-fixation marks"):
        welfare.head_fixed(at=0.0)


def test_a_chaired_session_refuses_a_release_mark_too():
    """**The other end of the same record, and the claim it makes true.**

    `taskd.Session.head_released` strobes `HEAD_RELEASED` (4129). `run()` calls it only
    for `RIG_FIXED`, but a console action wired straight to it would put a 4129 in the
    stream of a session that never had a 4128 -- a restraint record for restraint
    nothing marked. Guarding only the opening mark left that reachable while the
    documentation said it was not.
    """
    welfare = _chaired_welfare()

    with pytest.raises(Exceeded, match="cannot be recorded as released"):
        welfare.head_released(at=0.0)


def test_releasing_a_head_that_was_never_fixed_is_refused():
    """**The guard added on 2026-09-20 stopped one check short.**

    It asked which deployment this was and not whether there was anything to
    release, so a `RIG_FIXED` session that had never been fixed accepted the
    release: `released_at` was set, `taskd.Session.head_released` strobed 4129 into
    a stream with no 4128, `chair_seconds` then answered `0.00` for it, and
    `returned_to_cage`'s "fixed and not released" check could not see it because
    `fixed_at` was still `None`. The sentence *"no stream carries a HEAD_RELEASED
    with no HEAD_FIXED before it"* was still false, for a second reason.

    Reachable only by calling `Session.head_released` outside `run()` -- which is
    exactly the console action the deployment guard was added for.
    """
    welfare = _welfare()

    with pytest.raises(Exceeded, match="is not recorded as head-fixed, so there is "
                                       "nothing to release"):
        welfare.head_released(at=100.0)


def test_releasing_a_head_before_it_was_fixed_is_refused():
    """`returned_to_cage` refuses a return before the departure; this is the same
    refusal on the restraint clock, which did not have one. Without it,
    `head_fixed(500)` then `head_released(100)` are both finite, both accepted, and
    `chair_seconds` answers **-400.0**."""
    welfare = _welfare()
    welfare.head_fixed(at=500.0)

    with pytest.raises(Exceeded, match="cannot have been released at"):
        welfare.head_released(at=100.0)


def test_a_restraint_clock_that_runs_backwards_is_refused_when_it_is_read():
    """**The computed duration, not only the marks** -- `out_of_cage_seconds`'
    rule, which `chair_seconds` did not have. It guarded `now` and nothing else, so
    a backwards restraint interval reached the wire and rendered as
    `chair: -1:53:20` on a console.

    The marks are guarded now, so the only way here is a field assigned directly or
    a `now` in a base the mark was not taken in -- which is exactly why
    `out_of_cage_seconds` checks its own result as well, and why the entry-point
    enumeration's exemption for `fixed_at`/`released_at` can only rest on *this*.
    """
    welfare = _welfare()
    welfare.fixed_at = 500.0

    with pytest.raises(Exceeded, match="restraint clock for subject"):
        welfare.chair_seconds(now=100.0)


def test_a_restraint_clock_that_is_not_a_number_is_refused_when_it_is_read():
    """The other half, and the reason the exemption's old wording was wrong: a
    direct assignment bypasses `head_fixed`, so the *read* is where a non-finite
    restraint interval has to be caught."""
    welfare = _welfare()
    welfare.fixed_at = float("nan")

    with pytest.raises(Exceeded, match="not a real number"):
        welfare.chair_seconds(now=100.0)


def test_a_cage_side_session_refuses_a_head_fixation_mark():
    """Same refusal, same reason. This was accepted silently until 2026-09-20: a
    session that declared the animal was at home could still be recorded as
    head-fixed, and nothing anywhere disagreed."""
    with pytest.raises(Exceeded, match="takes no head-fixation marks"):
        _home_welfare().head_fixed(at=0.0)


def test_a_chaired_session_runs_without_head_fixation():
    """**Head-fixation stops being a blanket rig requirement** (PI, 2026-09-20).
    It is a property of the deployment, not of being on a rig, so preflight asks for
    it only where the deployment says it exists."""
    welfare = _chaired_welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    welfare.preflight(now=0.0)


def test_a_chaired_session_is_bounded_by_the_same_out_of_cage_clock():
    """Restraint is what differs between the two rig kinds; the twelve-hour limit is
    not. A chaired session is out of its cage and the clock binds it identically."""
    welfare = _chaired_welfare(out_of_cage=60.0)
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    assert welfare.must_stop(now=61.0) is not None


def test_a_chaired_session_still_refuses_a_config_with_no_duration_ceiling():
    """The rig kinds share the requirement as well as the clock: `RIG_CHAIRED` is not
    a way to reach a session out of the cage with no limit on it."""
    with pytest.raises(Exceeded, match="has no 'out_of_cage' ceiling"):
        Welfare(
            bounds=_home_bounds(),
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.RIG_CHAIRED,
        )


def test_a_chaired_session_still_refuses_to_run_with_no_out_of_cage_mark():
    """The mark is the other thing both rig kinds require. Dropping head-fixation
    from `RIG_CHAIRED` must not drop the mark with it."""
    welfare = _chaired_welfare()

    with pytest.raises(Exceeded, match="is not recorded as out of its cage"):
        welfare.preflight(now=0.0)


# --- the warning before the limit -------------------------------------------


def test_the_session_warns_before_the_limit_rather_than_only_at_it():
    """**PI, 2026-09-20: warn as the twelve-hour limit approaches**, so an operator
    can finish a block deliberately instead of having a session cut mid-sequence.
    The console showed the clock and nothing drew attention as it ran out."""
    welfare = _welfare(out_of_cage=3_600.0)
    welfare.warn_within = 600.0
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    warning = welfare.approaching_limit(now=3_100.0)

    assert warning is not None
    assert "500" in warning, "the warning says how much is left"


def test_nothing_warns_while_there_is_more_than_the_threshold_left():
    """A warning that is always on is one nobody reads."""
    welfare = _welfare(out_of_cage=3_600.0)
    welfare.warn_within = 600.0
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    assert welfare.approaching_limit(now=2_900.0) is None


def test_the_warning_stops_once_the_limit_is_past_because_must_stop_speaks():
    """Two different statements about the same clock. Past the ceiling the session is
    ending, and a warning beside a stop would read as though there were still a
    choice to make."""
    welfare = _welfare(out_of_cage=3_600.0)
    welfare.warn_within = 600.0
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    assert welfare.approaching_limit(now=3_700.0) is None
    assert welfare.must_stop(now=3_700.0) is not None


def test_a_cage_side_session_never_warns():
    """It has no duration bound to approach (S13 §4.0), and `None` here is the same
    `None` `out_of_cage_seconds` answers -- not a warning suppressed."""
    assert _home_welfare().approaching_limit(now=99_999.0) is None


def test_the_warning_threshold_is_configurable_and_defaults_to_a_named_figure():
    """**Welfare-facing, so it is a named default rather than a literal** -- and it
    is the PI's to accept or change. Thirty minutes is this session's proposal, not a
    measurement: no block duration has been measured on this system, so nothing here
    may claim the threshold clears one."""
    assert welfare_module.WARN_WITHIN_DEFAULT == 1_800.0
    assert _welfare().warn_within == welfare_module.WARN_WITHIN_DEFAULT


def test_a_threshold_wider_than_the_ceiling_warns_for_the_whole_session():
    """**And is not refused**, which was written and then removed on 2026-09-20.

    Refusing it would have made every short-ceiling config fail to construct a
    `Welfare` -- including `tasks/reference_bounds.py`'s deliberately implausible ten
    minutes, which would have turned `wlx run` into a hard failure over a
    placeholder. It is also a true statement rather than a nonsensical one: a session
    whose whole allowance is under the threshold is inside it throughout.
    """
    welfare = Welfare(
        bounds=_bounds(out_of_cage=600.0),
        pump=Simulated(),
        already_today=0.0,
        deployment=Deployment.RIG_FIXED,
        warn_within=1_800.0,
    )
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    assert welfare.approaching_limit(now=0.0) is not None


def test_a_zero_threshold_switches_the_warning_off():
    """Configurable includes off. A lab that does not want the line says so with a
    number rather than by a flag that means something else."""
    welfare = _welfare(out_of_cage=3_600.0)
    welfare.warn_within = 0.0
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    assert welfare.approaching_limit(now=3_599.0) is None


# --- a departure far from now, and the person who has to say so -------------
#
# **PI, 2026-09-20:** *"if a number is input that is more than 30 min from the
# current time, a warning should appear that the experimenter must click through to
# confirm. There should also be an option to update the time if necessary, but a
# reason should be given and the experimenter name logged."*
#
# This is the mitigation for the guard he accepted losing when the mark became a
# clock time: `08:45` typed for `18:45` is nine hours and sits comfortably inside a
# twelve-hour ceiling, so no refusal will ever catch it. These tests are about the
# *band* -- between "obviously wrong", which is still refused outright, and
# "obviously fine", which still runs with nothing asked.


def test_a_departure_far_from_now_needs_a_persons_confirmation():
    """Two hours ago, inside a twelve-hour ceiling: nothing refuses it and nothing
    should, but a person has to have seen it."""
    welfare = _welfare()

    sentence = welfare.departure_needs_confirmation(
        at=WALL_NOW - 7_200.0, wall_now=WALL_NOW
    )

    assert sentence is not None
    assert "Confirm it, or amend it" in sentence, "both options the PI asked for"


def test_a_departure_close_to_now_needs_nothing_of_anybody():
    """The ordinary case -- an operator typing the time they just walked the animal
    out -- asks nothing, or the confirmation becomes something to click past."""
    welfare = _welfare()

    assert (
        welfare.departure_needs_confirmation(at=WALL_NOW - 600.0, wall_now=WALL_NOW)
        is None
    )


def test_the_confirmation_threshold_is_thirty_minutes_and_is_the_PIs_number():
    """**Thirty minutes is his figure, not a derived one** (PI, 2026-09-20), which
    is why it is a named constant rather than a literal in `cli.py`.

    The boundary is checked on both sides because `WARN_WITHIN_DEFAULT` is also
    1,800 and the two are unrelated. Both are his since 2026-09-20 and they are still
    not the same number twice: that one is a *starting* value for a console line that
    bounds nothing and any lab may tune, and this one is a threshold on a mark that
    bounds a session. Deriving either from the other would make tuning a warning
    quietly move a welfare guard.
    """
    assert welfare_module.CONFIRM_MARK_WITHIN == 1_800.0
    welfare = _welfare()

    assert (
        welfare.departure_needs_confirmation(at=WALL_NOW - 1_800.0, wall_now=WALL_NOW)
        is None
    )
    assert (
        welfare.departure_needs_confirmation(at=WALL_NOW - 1_801.0, wall_now=WALL_NOW)
        is not None
    )


def test_a_departure_past_the_ceiling_is_refused_rather_than_confirmed():
    """**The existing refusals stand.** A confirmation offered for something
    `left_cage` is about to refuse outright would train an operator to click through
    a prompt that means two different things."""
    welfare = _welfare(out_of_cage=3_600.0)

    assert (
        welfare.departure_needs_confirmation(at=WALL_NOW - 3_600.0, wall_now=WALL_NOW)
        is None
    )
    with pytest.raises(Exceeded, match="against a ceiling of"):
        welfare.left_cage(at=WALL_NOW - 3_600.0, wall_now=WALL_NOW, now=0.0)


def test_a_departure_in_the_future_is_refused_rather_than_confirmed():
    """The other end of the same rule. "More than 30 minutes from the current time"
    reads as a distance, but the future half of it is already refused outright, so
    nothing here offers to confirm one."""
    welfare = _welfare()

    assert (
        welfare.departure_needs_confirmation(at=WALL_NOW + 7_200.0, wall_now=WALL_NOW)
        is None
    )
    with pytest.raises(Exceeded, match="in the future"):
        welfare.left_cage(at=WALL_NOW + 7_200.0, wall_now=WALL_NOW, now=0.0)


def test_a_cage_side_session_has_no_departure_to_confirm():
    """It never left, so `left_cage` refuses any mark at all and there is no band."""
    assert (
        _home_welfare().departure_needs_confirmation(
            at=WALL_NOW - 7_200.0, wall_now=WALL_NOW
        )
        is None
    )


def test_an_amendment_carries_a_reason_and_an_actor_into_the_record():
    """**Both, and the pair is what makes the row answer a question months later**
    (PI, 2026-09-20: *"a reason should be given and the experimenter name
    logged"*)."""
    welfare = _welfare()

    welfare.amend_mark(
        "departure",
        original=WALL_NOW - 33_300.0,
        amended=WALL_NOW - 900.0,
        reason="typed 08:45 for 18:45",
        by="jake",
    )

    assert welfare.notes == [
        (
            "mark amended",
            "departure",
            WALL_NOW - 33_300.0,
            WALL_NOW - 900.0,
            "typed 08:45 for 18:45",
            "jake",
        )
    ]


def test_an_amendment_with_no_reason_is_refused_rather_than_recorded_blank():
    """A blank reason is worse than no row: it looks like an answer. The PI asked
    for a reason, and a row saying an experimenter changed a welfare clock for no
    stated cause answers nothing anyone will ask."""
    with pytest.raises(Exceeded, match="no reason"):
        _welfare().amend_mark(
            "departure",
            original=WALL_NOW - 33_300.0,
            amended=WALL_NOW - 900.0,
            reason="   ",
            by="jake",
        )


def test_an_amendment_with_no_actor_is_refused_like_a_console_write_with_no_as():
    """`--as WHO` is required for a console write because a forgeable or invented
    actor is worse than none. This moves the clock that bounds the session, so it
    gets the same rule."""
    with pytest.raises(Exceeded, match="nobody"):
        _welfare().amend_mark(
            "departure",
            original=WALL_NOW - 33_300.0,
            amended=WALL_NOW - 900.0,
            reason="typed 08:45 for 18:45",
            by="",
        )


def test_an_amendment_is_refused_before_it_touches_the_mark():
    """The refusals above must land before `left_cage` does, or a session ends up
    marked with an amendment nothing recorded -- the mark cannot be re-armed, so
    there would be no way back."""
    welfare = _welfare()

    with pytest.raises(Exceeded):
        welfare.amend_mark(
            "departure",
            original=WALL_NOW - 33_300.0,
            amended=WALL_NOW - 900.0,
            reason="x",
            by="",
        )

    assert welfare.left_cage_at is None
    assert welfare.notes == []


# --- the return, which is a clock time too ----------------------------------
#
# **PI, 2026-09-20 (ruling 4): the return mark is a wall-clock time, like the
# departure.** The symmetry is the point, and it closes a real gap rather than
# tidying one: `Session.now()` is frame-derived and stops when the frames do, so an
# operator who ends a session, unchairs the animal, walks it back and *then* marks
# the return recorded the animal as home at the instant the loop ended. The
# unchairing and the walk back -- minutes of an animal out of its cage -- did not
# count toward the twelve hours.


def test_the_walk_back_counts_because_the_return_is_a_clock_time():
    """**The gap ruling 4 closes, at the size it exists for.**

    A session whose frames stop at 1,000 s, an animal unchaired and walked back over
    the next ten wall minutes, and a return marked when it is actually home. The
    interval is what the two wall clocks say -- departure to return -- and not what
    the frozen frame clock said when the loop ended.
    """
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW - 300.0, wall_now=WALL_NOW, now=0.0)

    # Frames stopped at session-clock 1,000; the operator marks the return 1,600
    # wall seconds after the session began, from a terminal reading 1,700.
    welfare.returned_to_cage(at=WALL_NOW + 1_600.0, wall_now=WALL_NOW + 1_700.0)

    # 300 s of transport before session zero, plus 1,600 s to the return.
    assert welfare.out_of_cage_seconds(now=1_000.0) == pytest.approx(1_900.0)


def test_a_return_later_than_the_wall_clock_is_refused():
    """The departure's future refusal, on the closing mark. An animal cannot be
    recorded home at a time that has not happened yet."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    with pytest.raises(Exceeded, match="in the future"):
        welfare.returned_to_cage(at=WALL_NOW + 60.0, wall_now=WALL_NOW)


def test_a_return_before_the_departure_is_refused_on_the_wall_clock_too():
    """Every refusal the return already had is preserved, now read against wall
    instants rather than session ones."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    with pytest.raises(Exceeded, match="cannot be back in its cage"):
        welfare.returned_to_cage(at=WALL_NOW - 60.0, wall_now=WALL_NOW)


def test_a_return_far_from_now_needs_a_persons_confirmation_too():
    """**The same thirty minutes, and for the same reason.** A return typed hours
    ago is as suspicious as a departure typed hours ago, and it moves the same
    interval -- in the direction that makes a session look shorter than it was."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    sentence = welfare.return_needs_confirmation(
        at=WALL_NOW + 100.0, wall_now=WALL_NOW + 7_300.0
    )

    assert sentence is not None
    assert "Confirm it, or amend it" in sentence


def test_a_far_return_nobody_confirmed_is_refused():
    """**The absence of the confirmation fails, rather than being checked
    elsewhere.** The departure's confirmation has a consumer in `wlx run`; the return
    has none until the console gains the action, so the guard lives on the mark where
    nothing can be built that forgets it (CLAUDE.md)."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    with pytest.raises(Exceeded, match="not confirmed by anyone"):
        welfare.returned_to_cage(at=WALL_NOW + 100.0, wall_now=WALL_NOW + 7_300.0)


def test_a_far_return_a_person_confirmed_is_taken():
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)

    welfare.returned_to_cage(
        at=WALL_NOW + 100.0, wall_now=WALL_NOW + 7_300.0, confirmed=True
    )

    assert welfare.out_of_cage_seconds(now=100.0) == pytest.approx(100.0)


def test_a_far_departure_nobody_confirmed_is_refused_at_the_mark():
    """The same guard on the opening mark, so a console calling `left_cage` directly
    -- which is exactly what P4d-2 adds -- cannot reach around `wlx run`'s prompt."""
    with pytest.raises(Exceeded, match="not confirmed by anyone"):
        _welfare().left_cage(at=WALL_NOW - 7_200.0, wall_now=WALL_NOW, now=0.0)


def test_a_far_departure_a_person_confirmed_is_taken():
    welfare = _welfare()

    welfare.left_cage(
        at=WALL_NOW - 7_200.0, wall_now=WALL_NOW, now=0.0, confirmed=True
    )

    assert welfare.out_of_cage_seconds(now=0.0) == pytest.approx(7_200.0)


def test_an_amendment_names_which_mark_it_changed():
    """One amendment path for both marks (PI, 2026-09-20), so the reason and the
    actor are required identically and the row says which clock moved."""
    welfare = _welfare()

    welfare.amend_mark(
        "return",
        original=WALL_NOW,
        amended=WALL_NOW - 60.0,
        reason="marked before the animal was actually in",
        by="jake",
    )

    assert welfare.notes[0][:2] == ("mark amended", "return")


# --- an animal must be out of its cage to be in the chair -------------------
#
# **The restraint record is a cross-check on the duration, not only a record.**
# Found by review probing ruling 4: a return marked one second after the departure,
# on a session whose head was fixed at 60 s and released at 1,400 s, gave
# `out_of_cage_seconds` of **1.0** beside `chair_seconds` of **1,340**. Both marks
# present, both orderings individually legal, the whole thing inside the
# thirty-minute band so nothing prompted -- and an impossible pair accepted in
# silence, under-reporting the exact interval ruling 4 exists to count.
#
# The invariant is free and physical: the out-of-cage interval **contains** the
# restraint interval, so it can never be shorter than it, and a return cannot
# precede a release. Guarded at the mark *and* at the read, which is this file's
# standing rule -- the mark refusal tells the operator while they are typing, and
# the read refusal catches the routes that do not go through that mark.


def test_a_return_before_the_head_was_released_is_refused():
    """**The probe, at the size it was found.** Twenty-five minutes out, fixed at
    60 s, released at 1,400 s, and a return typed one second after the departure."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW - 1_500.0, wall_now=WALL_NOW, now=0.0)
    welfare.head_fixed(at=60.0)
    welfare.head_released(at=1_400.0)

    with pytest.raises(Exceeded, match="before it was released"):
        welfare.returned_to_cage(at=WALL_NOW - 1_499.0, wall_now=WALL_NOW)

    assert welfare.returned_at is None, "the impossible mark must not be taken"


def test_a_return_after_the_release_is_taken_like_any_other():
    """The boundary the refusal above is about: released, and then walked back.

    The release at session-clock 1,400 is wall-clock `WALL_NOW + 1_400` here, since
    session zero was read against `WALL_NOW` -- which is the arithmetic the refusal
    above turns on, and getting it wrong is how this test was first written."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW - 1_500.0, wall_now=WALL_NOW, now=0.0)
    welfare.head_fixed(at=60.0)
    welfare.head_released(at=1_400.0)

    welfare.returned_to_cage(at=WALL_NOW + 1_500.0, wall_now=WALL_NOW + 1_500.0)

    # 1,500 s of transport and chairing before session zero, plus 1,500 s after it.
    assert welfare.out_of_cage_seconds(now=9_999.0) == pytest.approx(3_000.0)


def test_the_interval_can_never_be_shorter_than_the_restraint_it_contains():
    """**The same impossibility by the other route, caught where it is read.**

    `head_fixed` has no ordering check against the departure -- a console may mark
    in either order, and constraining that would refuse a legal sequence -- so a
    fixation *before* the animal left its cage produces chair time longer than
    out-of-cage time without any mark being individually wrong. The duration reading
    is where the two can be compared, and this file's own rule is that a computed
    value is checked as well as its inputs."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    welfare.fixed_at = -600.0

    with pytest.raises(Exceeded, match="restraint record reads"):
        welfare.out_of_cage_seconds(now=100.0)


def test_an_ordinary_session_reads_a_longer_interval_than_its_restraint():
    """The case the guard must not fire on, which is every real session: the animal
    leaves its cage, is transported and chaired, and only then head-fixed."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW - 1_200.0, wall_now=WALL_NOW, now=0.0)
    welfare.head_fixed(at=0.0)

    assert welfare.out_of_cage_seconds(now=300.0) == pytest.approx(1_500.0)
    assert welfare.chair_seconds(now=300.0) == pytest.approx(300.0)


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
            deployment=Deployment.RIG_FIXED,
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
# **What would have to be true for a door to be missing**, stated so the claim is
# falsifiable rather than confident. A number would have to reach a comparison in
# `bounds` or `welfare` without passing any parameter or field this enumeration can
# see. **There are at least six such routes** -- an earlier version of this comment
# said "exactly two", which a review disproved by planting six doors it could not
# see, three of them in the first category alone:
#
# 1. **A parameter or field the introspection cannot classify** -- unannotated, or
#    annotated `object`/`Any`, or behind a `@property`/`@staticmethod`/`@classmethod`
#    descriptor rather than a plain function. Closed:
#    `test_every_numeric_parameter_is_annotated` refuses the first two, and
#    `_callables` walks the third.
# 2. **A numeric annotation the classifier does not recognise.** `int | None`,
#    `Optional[int]` and `Decimal` all slipped the first version. Narrowed, not
#    closed: `_NUMERIC` is a word-boundary regex over a list of spellings, and a
#    type it does not name is invisible. Adding one means adding it there.
# 3. **A number inside a container.** `Bounds.ceilings`/`minima` are `dict`, and the
#    numbers in them are guarded by `Ceiling`/`Floor` -- the types inside the
#    container, not the container's annotation. A `dict[str, float]` field would be
#    a real hole, and there is none in either file.
# 4. **`*args`/`**kwargs`**, which name no parameter to enumerate. Only `Pump`'s
#    Protocol has them, and it takes no welfare quantity.
# 5. **Arithmetic**: two checked values producing an unchecked third. Not closable by
#    enumerating doors, which is why `out_of_cage_seconds` checks the *computed*
#    duration and `reconcile_report` checks both of its inputs.
# 6. **Assignment after construction**, which bypasses `__post_init__`. What makes
#    that safe is not the setter but the read: every field feeding a comparison is
#    guarded where it is *used* as well as where it is set.
#
# So the enumeration is complete for *doors it can classify*, and 2–6 are covered by
# checking results as well as inputs. That is the honest boundary.

import dataclasses
import inspect
import re
from pathlib import Path

from wl_expcontroller import bounds as bounds_module

#: A magnitude is finite and non-negative; an instant is merely finite. Every entry
#: point below is one or the other, and that distinction is the rule the earlier
#: rounds were missing: -0.5 mL passed every `>` in the file.
MAGNITUDE = "magnitude"
INSTANT = "instant"

#: Where a magnitude's negative refusal is worded for its own parameter rather than
#: by `_magnitude`. **Empty since 2026-09-20**, and kept rather than deleted: the one
#: entry was `Welfare.left_cage.seconds_ago`, whose "left its cage in the future" is
#: still the wording an operator reads -- but the mark became a clock time (PI), so
#: the parameters either side of it are *instants*, which the negative case never
#: drives. The next magnitude with a refusal of its own needs this.
NEGATIVE_MESSAGE: dict = {}

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
            deployment=Deployment.RIG_FIXED,
            commanded=v,
        ),
    ),
    "Welfare.delivered": (
        MAGNITUDE,
        lambda v: Welfare(
            bounds=_bounds(),
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.RIG_FIXED,
            delivered=v,
        ),
    ),
    "Welfare.confirm_already_today.total": (
        MAGNITUDE,
        lambda v: _welfare().confirm_already_today(v, by="jake"),
    ),
    "Welfare.reconcile.delivered": (MAGNITUDE, lambda v: _welfare().reconcile(v)),
    # --- welfare: the clocks -------------------------------------------------
    # Three readings, two bases, one mapping (PI, 2026-09-20). All three are
    # *instants*: a wall-clock reading is merely finite, and the interval computed
    # from two of them is checked inside `left_cage` rather than being a door this
    # table can name -- S8 §5.2c's fifth blind spot, closed where it lives.
    "Welfare.left_cage.at": (
        INSTANT,
        lambda v: _welfare().left_cage(at=v, wall_now=WALL_NOW, now=0.0),
    ),
    "Welfare.left_cage.wall_now": (
        INSTANT,
        lambda v: _welfare().left_cage(at=WALL_NOW, wall_now=v, now=0.0),
    ),
    "Welfare.left_cage.now": (
        INSTANT,
        lambda v: _welfare().left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=v),
    ),
    # The confirmation band (PI, 2026-09-20) reads the same two wall-clock instants
    # `left_cage` does, and computes the same interval from them, so it gets the
    # same three checks rather than trusting that its caller already made them: on
    # the console path it is asked *before* the mark and on no other authority. The
    # two public forms and the shared private one are each driven, because the
    # enumeration is about doors rather than about implementations.
    "Welfare._far_from_now.at": (
        INSTANT,
        lambda v: _welfare()._far_from_now("departure", at=v, wall_now=WALL_NOW),
    ),
    "Welfare._far_from_now.wall_now": (
        INSTANT,
        lambda v: _welfare()._far_from_now("departure", at=WALL_NOW, wall_now=v),
    ),
    "Welfare.departure_needs_confirmation.at": (
        INSTANT,
        lambda v: _welfare().departure_needs_confirmation(at=v, wall_now=WALL_NOW),
    ),
    "Welfare.departure_needs_confirmation.wall_now": (
        INSTANT,
        lambda v: _welfare().departure_needs_confirmation(at=WALL_NOW, wall_now=v),
    ),
    "Welfare.return_needs_confirmation.at": (
        INSTANT,
        lambda v: _welfare().return_needs_confirmation(at=v, wall_now=WALL_NOW),
    ),
    "Welfare.return_needs_confirmation.wall_now": (
        INSTANT,
        lambda v: _welfare().return_needs_confirmation(at=WALL_NOW, wall_now=v),
    ),
    # Two instants a person typed, one of which becomes a mark. Guarded here as well
    # as at the mark, because this runs first and drives the durable row.
    "Welfare.amend_mark.original": (
        INSTANT,
        lambda v: _welfare().amend_mark(
            "departure", original=v, amended=WALL_NOW, reason="typo", by="jake"
        ),
    ),
    "Welfare.amend_mark.amended": (
        INSTANT,
        lambda v: _welfare().amend_mark(
            "departure", original=WALL_NOW, amended=v, reason="typo", by="jake"
        ),
    ),
    # A wall-clock instant since 2026-09-20 (PI, ruling 4), with the wall clock it is
    # read against beside it -- the departure's three readings, one short, because
    # the session clock no longer enters the closing mark at all.
    "Welfare.returned_to_cage.at": (
        INSTANT,
        lambda v: _marked().returned_to_cage(v, wall_now=WALL_NOW),
    ),
    "Welfare.returned_to_cage.wall_now": (
        INSTANT,
        lambda v: _marked().returned_to_cage(WALL_NOW, wall_now=v),
    ),
    "Welfare.head_fixed.at": (INSTANT, lambda v: _welfare().head_fixed(v)),
    # Fixed first: `head_released` refuses a release with nothing to release since
    # 2026-09-20, and `_finite` still runs before that guard, so this drives the
    # parameter rather than the ordering.
    "Welfare.head_released.at": (INSTANT, lambda v: _fixed().head_released(v)),
    "Welfare.chair_seconds.now": (INSTANT, lambda v: _welfare().chair_seconds(v)),
    "Welfare.out_of_cage_seconds.now": (
        INSTANT,
        lambda v: _marked().out_of_cage_seconds(v),
    ),
    "Welfare.preflight.now": (INSTANT, lambda v: _marked().preflight(v)),
    "Welfare.must_stop.now": (INSTANT, lambda v: _marked().must_stop(v)),
    "Welfare.approaching_limit.now": (
        INSTANT,
        lambda v: _marked().approaching_limit(v),
    ),
    "Welfare.now_from_wall.wall_now": (
        INSTANT,
        lambda v: _marked().now_from_wall(v),
    ),
    # A duration, so a magnitude -- and on the welfare path even though it bounds
    # nothing: a NaN threshold makes `remaining > warn_within` False forever, so the
    # warning would never fire and a welfare-facing line would be silently off.
    "Welfare.warn_within": (
        MAGNITUDE,
        lambda v: Welfare(
            bounds=_bounds(),
            pump=Simulated(),
            already_today=0.0,
            deployment=Deployment.RIG_FIXED,
            warn_within=v,
        ),
    ),
}

#: Numeric surface that is deliberately *not* an entry point, each with its reason.
#: An entry here is a claim someone made, which is the point: the alternative is a
#: parameter quietly absent from both lists.
NOT_ENTRY_POINTS = {
    "_finite.value": "the guard itself",
    "_magnitude.value": "the guard itself",
    # **A count, not a magnitude.** This said "never supplied", which was false --
    # it is a constructor field and `Welfare(deliveries=-7)` is accepted. Harmless,
    # because nothing compares it against a limit: it is reported, not enforced. The
    # reason is what it *is*, not where it comes from.
    "Welfare.deliveries": "a count of deliveries, compared against no limit",
    "Reconciliation.total": "an output, computed from checked inputs",
    "Reconciliation.commanded": "an output; see above",
    "Reconciliation.delivered": "an output; see above",
    "Reconciliation.unexplained": "an output; see above",
    # The four clock fields, all with the same honest reason. Three of them said
    # "set only by X, which checks it", which overstates in the way `left_cage_at`'s
    # entry already avoided: a `Welfare` can be constructed around any of them, and
    # a field can be assigned after construction. What makes that safe is not the
    # setter -- it is that every *read* is guarded.
    "Welfare.left_cage_at": (
        "an instant the marks set; a direct construction or a later assignment "
        "bypasses left_cage, and out_of_cage_seconds catches a non-finite or "
        "backwards result on every read"
    ),
    # The wall anchor `returned_to_cage` maps against (PI, 2026-09-20, ruling 4).
    # Same reason as `left_cage_at`, and with one extra guard behind it: a `Welfare`
    # constructed around `left_cage_at` alone has no anchor, and the return refuses
    # rather than mapping against `None`.
    "Welfare.left_cage_wall_at": (
        "a wall instant left_cage sets; a direct construction or a later assignment "
        "bypasses it, returned_to_cage refuses when it is absent, and "
        "out_of_cage_seconds catches a non-finite or backwards result on every read"
    ),
    "Welfare.returned_at": "as left_cage_at; read through out_of_cage_seconds",
    # These two said "read through chair_seconds, which guards `now`", and that
    # was the wrong value: `now` is not the restraint interval, and
    # `head_fixed(500)` / `head_released(100)` produced -400.0 through a guard
    # that was looking elsewhere. `chair_seconds` checks its own computed result
    # now, which is what makes the exemption true rather than merely stated.
    "Welfare.fixed_at": (
        "an instant the marks set; a direct construction or a later assignment "
        "bypasses head_fixed, and chair_seconds catches a non-finite or backwards "
        "restraint interval on every read"
    ),
    "Welfare.released_at": "as fixed_at; read through chair_seconds",
    "Pump.deliver.ml": "a volume leaving this module, already checked by its ceiling",
    "Simulated.deliver.ml": "as Pump.deliver",
    "Absent.deliver.ml": "as Pump.deliver; refuses unconditionally anyway",
    "Card.emit.code": "an event code leaving this module; dio owns its range",
    "Rig.mark.code": "an event code, not a welfare quantity; dio owns its range",
}


def _marked() -> Welfare:
    """A rig `Welfare` with its interval open, so a clock call is the only fault."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW, now=0.0)
    return welfare


def _fixed() -> Welfare:
    """A `_marked()` one with the head fixed, so a release is the only fault."""
    welfare = _marked()
    welfare.head_fixed(at=0.0)
    return welfare


#: Every spelling of "this holds a number" the classifier recognises. Regex on word
#: boundaries rather than `in`, so `Decimal` is caught and `information` is not.
_NUMERIC = re.compile(r"\b(int|float|Decimal|complex|Real|Number)\b")

#: Annotations that name no type at all. **Refused in these two files**, rather than
#: accepted as non-numeric: `ml: object` carries a float perfectly well, and an
#: annotation the classifier cannot classify is a door it cannot see.
_OPAQUE = re.compile(r"\b(object|Any)\b")


def _classify(annotation) -> str:
    """`"numeric"`, `"other"`, or `"opaque"` -- and `"opaque"` is an error.

    A review planted six doors the first version of this could not see. Three were
    *descriptors* rather than functions; two were numeric annotations it did not
    recognise (`int | None`, `Optional[int]`); one was `object`, which it accepted as
    "not a number" when the honest answer is "unknown". None existed in either module
    -- this is the tripwire, not a live hole -- but a tripwire with six blind spots
    is the thing it exists to prevent, one level up.
    """
    if annotation is None:
        return "other"
    text = annotation if isinstance(annotation, str) else str(annotation)
    if _NUMERIC.search(text):
        return "numeric"
    if _OPAQUE.search(text):
        return "opaque"
    return "other"


def _is_numeric(annotation) -> bool:
    return _classify(annotation) == "numeric"


def _callables(cls) -> list:
    """Every function reachable on `cls`, **including the ones behind descriptors**.

    `vars(cls)[name]` is a `property`, `staticmethod` or `classmethod` object, none
    of which is an `inspect.isfunction`. Filtering on that alone made a `@property`
    setter, a `@staticmethod` and a `@classmethod` taking a float invisible to both
    tests below.
    """
    found = []
    for attr, value in vars(cls).items():
        if attr.startswith("__"):
            continue
        # `Enum` contributes `_generate_next_value_` from `enum.py`, and a base class
        # can contribute anything. Only functions written in the file under test are
        # this test's business.
        fn = value
        if isinstance(fn, (staticmethod, classmethod)):
            fn = fn.__func__
        if not isinstance(fn, property) and getattr(
            fn, "__module__", cls.__module__
        ) != cls.__module__:
            continue
        if isinstance(value, property):
            for part, fn in (("fget", value.fget), ("fset", value.fset)):
                if fn is not None:
                    found.append((f"{attr}" if part == "fget" else f"{attr}", fn))
        elif isinstance(value, (staticmethod, classmethod)):
            found.append((attr, value.__func__))
        elif inspect.isfunction(value):
            found.append((attr, value))
    return found


def _numeric_params(label: str, fn) -> set:
    hints = getattr(fn, "__annotations__", {})
    return {
        f"{label}.{p}"
        for p in inspect.signature(fn).parameters
        if p not in ("self", "cls") and _is_numeric(hints.get(p))
    }


def _numeric_surface() -> set:
    """Every numeric parameter and field of the welfare-critical modules.

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
                for attr, fn in _callables(obj):
                    found |= _numeric_params(f"{name}.{attr}", fn)
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
    """The introspection's own blind spots, closed.

    `_numeric_surface` reads annotations, so a parameter it cannot *classify* is a
    door it cannot see -- and the enumeration would look complete while missing one.
    Two ways that happens, and both are refused here rather than tolerated:

    - **No annotation at all.**
    - **An annotation naming no type**: `object` or `Any`. The first version
      accepted these as "not a number", which is wrong -- `ml: object` carries a
      float perfectly well, and the honest answer is "unknown".

    Descriptors are walked through `_callables`, because `@property`, `@staticmethod`
    and `@classmethod` are not `inspect.isfunction` and were invisible to both tests
    until a review planted three of them.
    """
    unclassifiable = []
    for module in (bounds_module, welfare_module):
        for name, obj in vars(module).items():
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            # Dunders are excluded for the same reason `_numeric_surface` excludes
            # them: `dataclass`, `Enum` and `Protocol` generate `__eq__`,
            # `__setattr__`, `__replace__` and friends without annotations, and
            # none of them can carry a float an author wrote.
            entries = (
                [(name, obj)]
                if inspect.isfunction(obj)
                else [(f"{name}.{a}", fn) for a, fn in _callables(obj)]
                if inspect.isclass(obj)
                else []
            )
            for label, fn in entries:
                hints = getattr(fn, "__annotations__", {})
                for p in inspect.signature(fn).parameters:
                    if p in ("self", "cls"):
                        continue
                    if p not in hints:
                        unclassifiable.append(f"{label}.{p} (unannotated)")
                    elif _classify(hints[p]) == "opaque":
                        unclassifiable.append(f"{label}.{p} ({hints[p]})")
        for name, obj in vars(module).items():
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            if inspect.isclass(obj) and dataclasses.is_dataclass(obj):
                for f in dataclasses.fields(obj):
                    if _classify(f.type) == "opaque":
                        unclassifiable.append(f"{name}.{f.name} ({f.type})")

    assert not unclassifiable, (
        f"parameters or fields in a welfare-critical file whose annotation the "
        f"entry-point enumeration cannot classify: {sorted(unclassifiable)}. An "
        f"unannotated one, or one annotated `object`/`Any`, is a door the tripwire "
        f"cannot see -- `ml: object` carries a float perfectly well. Annotate it "
        f"with the type it actually holds"
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


# ---------------------------------------------------------------------------
# The refusal table, which must not rot
# ---------------------------------------------------------------------------


_S8 = (
    Path(__file__).resolve().parent.parent
    / "docs/superpowers/specs/2026-08-31-S8-session-management-design.md"
)


def _table_phrases() -> list:
    """The greppable first column of S8 §5.2d, one phrase per refusal."""
    rows = []
    inside = False
    for line in _S8.read_text().splitlines():
        if line.startswith("### 5.2d"):
            inside = True
            continue
        if inside and line.startswith("### "):
            break
        if inside and line.startswith("| `"):
            cell = line.split("|")[1].strip()
            # `phrase` *(note)* -> phrase
            phrase = cell.split("`")[1]
            rows.append(phrase)
    return rows


def _raise_messages() -> list:
    """Every `raise` in the two welfare-critical files, message reconstructed.

    The message is rebuilt from the f-string's literal parts with interpolations
    elided, and whitespace collapsed -- because a refusal message wraps over four or
    five source lines, so no phrase from it appears literally in the file.
    """
    import ast
    import re as _re

    found = []
    for module in (bounds_module, welfare_module):
        source = Path(module.__file__).read_text()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Raise):
                continue
            exc = node.exc
            if not isinstance(exc, ast.Call) or not exc.args:
                found.append("")
                continue
            arg = exc.args[0]
            pieces = arg.values if isinstance(arg, ast.JoinedStr) else [arg]
            text = "".join(
                p.value
                if isinstance(p, ast.Constant) and isinstance(p.value, str)
                else "\u2026"
                for p in pieces
            )
            found.append(_re.sub(r"\s+", " ", text).strip())
    return found


def test_every_refusal_has_a_row_in_the_table_and_every_row_still_greps():
    """**S8 §5.2d is an index into the code, so it must stay one.**

    The claim it makes -- that "is this refusal earned?" is a lookup -- holds only
    while the table covers every `raise` and every phrase in it still lands on one.
    Both directions are checked, because each rots differently: a new refusal with
    no row makes the table incomplete, and a reworded message makes a row
    ungreppable while the table still looks full.
    """
    phrases = _table_phrases()
    messages = _raise_messages()

    assert len(phrases) == len(messages), (
        f"S8 §5.2d has {len(phrases)} rows and the two welfare-critical files have "
        f"{len(messages)} raise sites. Every refusal gets a row -- that table is the "
        f"answer to 'is this one earned?'"
    )

    def lands(phrase: str) -> bool:
        """True if some refusal message contains the phrase's parts, in order.

        `\u2026` in a row marks where the message interpolates a value, so the
        parts either side must appear in sequence within one message.
        """
        parts = [p for p in phrase.split("\u2026") if p]
        for message in messages:
            at = 0
            for part in parts:
                at = message.find(part, at)
                if at < 0:
                    break
                at += len(part)
            else:
                return True
        return False

    missing = [p for p in phrases if not lands(p)]
    assert not missing, (
        f"these S8 §5.2d phrases match no refusal message, so the table's first "
        f"column is not greppable: {missing}. A reworded refusal needs its row "
        f"reworded with it"
    )


def test_the_zero_reward_ruling_records_why_zero_is_a_designed_outcome():
    """**Ruling 3, 2026-09-20: the reason is new information and changes the number.**

    The PI confirmed a zero-volume reward and gave a reason nobody here had: *"some
    trials will have a reward period, but they may not receive a juice reward. they
    may get an on-screen token reward that eventually becomes a real reward."*

    So `fluid session: 0.00 mL` is not an edge case being tolerated -- it is a
    **designed trial outcome**, a reward period that pays a token rather than fluid.
    That strengthens the case for the existing behaviour and changes what the figure
    means to a reader: a session at zero may be working exactly as intended.

    Asserted against the record rather than against code because nothing in the code
    changed -- the whole of this ruling is the reason, and a reason that is dropped
    from the record is a ruling that reverts to the weaker argument it replaced.
    """
    section = _S8.read_text().split("### 5.2c")[1].split("### 5.2d")[0]

    assert "token" in section.lower(), (
        "S8 §5.2c is where the zero-reward ruling lives, and the PI's reason for it "
        "is the token economy -- a reward period that pays a token rather than "
        "fluid. Without it the section argues only that zero is visible"
    )
    assert "2026-09-20" in section


def test_after_the_loop_the_wall_maps_through_the_departure():
    """P4d-2a. The frame clock stops when the loop does and the wall does not, so the
    interval after the last trial can only be read through the departure's anchor --
    the mapping `returned_to_cage` has used since ruling 4 (PI, 2026-09-20)."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW - 100.0, wall_now=WALL_NOW, now=0.0)

    later = welfare.now_from_wall(WALL_NOW + 600.0)

    assert later == pytest.approx(600.0)
    assert welfare.out_of_cage_seconds(later) == pytest.approx(700.0)


def test_a_cage_side_session_has_no_wall_mapping():
    welfare = Welfare(
        bounds=_home_bounds(),
        pump=Simulated(),
        already_today=0.0,
        deployment=Deployment.CAGE_SIDE,
    )

    with pytest.raises(Exceeded, match="at home"):
        welfare.now_from_wall(WALL_NOW)


def test_a_rig_session_with_no_departure_has_nothing_to_map_through():
    with pytest.raises(Exceeded, match="not recorded as having left its cage"):
        _welfare().now_from_wall(WALL_NOW)
