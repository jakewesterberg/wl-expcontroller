"""The task vocabulary's shortcuts.

`FixPoint` survived its first mutation ever on 2026-09-19 -- `379 passed` with its
body neutered -- because **nothing used it**. Not a test, not one of the three
reference tasks, though S1 §5.1's own worked example is `FIX = FixPoint(at=(0, 0),
size=0.3)`. It had never been mutated before because `mutate._function_names`
matched `^ *def ([a-z_][a-z0-9_]*)\\(`, which cannot spell a capital letter, so the
name was not on any target list and no output said so (trap 7, seventh entry).

The rule these tests hold to is S1a §6's: **a shortcut adds defaults and a name,
never a concept**, and what it produces is an ordinary `Stimulus` the rest of the
system cannot distinguish from a hand-written one.
"""

from __future__ import annotations

import pytest

from wl_xcon.task import Disc, Family, FixPoint, Outcome, P, Param, Stimulus


def test_a_fix_point_is_an_ordinary_stimulus():
    """`type(...) is Stimulus`, not `isinstance`: a subclass would be a concept, and
    the whole claim is that nothing downstream can tell this from a stimulus someone
    spelled out."""
    fix = FixPoint()

    assert type(fix) is Stimulus
    assert fix.name == "fix"
    assert fix.at == (0.0, 0.0)
    assert fix.looks == Disc(size=0.3)


def test_its_defaults_are_all_overridable():
    fix = FixPoint(name="target", at=(5.0, -2.0), size=1.5)

    assert fix.name == "target"
    assert fix.at == (5.0, -2.0)
    assert fix.looks == Disc(size=1.5)


def test_it_passes_the_rest_of_the_stimulus_through():
    """`**kwargs` is the half a shortcut could quietly drop: a fix point that ignored
    `eye` or `disparity` would look right and be wrong on a stereoscope."""
    fix = FixPoint(eye="left")

    assert fix.eye == "left"


def test_a_parameter_reaches_both_the_position_and_the_size():
    """A shortcut that resolved its arguments eagerly would turn a `P` into a number
    at import and freeze a parameter the task meant to vary per trial."""
    fix = FixPoint(at=P("where"), size=P("how_big"))

    assert fix.at == P("where")
    assert fix.looks.size == P("how_big")


# ---------------------------------------------------------------------------
# Outcome families (P4d-2b spec §3): the groups the enum's comments draw, as data
# ---------------------------------------------------------------------------


def test_every_outcome_has_a_family():
    """Total, so a console can never meet an outcome it cannot group: a member added
    without one fails here rather than on a rig's screen."""
    for outcome in Outcome:
        assert isinstance(outcome.family, Family), outcome


def test_the_families_are_the_groups_the_enums_comments_draw():
    grouped = {
        family: [o.value for o in Outcome if o.family is family] for family in Family
    }

    assert grouped == {
        Family.TARGET: ["correct", "early_response", "late_response"],
        Family.DISTRACTOR: ["wrong_target", "early_error", "late_error"],
        Family.WITHHOLD: ["correct_reject", "false_alarm"],
        Family.NO_ENGAGEMENT: ["no_fixation", "no_response", "abort"],
        Family.BREAKS: [
            "fixation_break",
            "target_break",
            "catch_break",
            "motion_break",
            "blink_break",
        ],
        Family.RIG: ["tracker_lost", "fault"],
    }


def test_the_family_words_are_the_specs_in_its_order():
    assert [family.value for family in Family] == [
        "target",
        "distractor",
        "withhold",
        "no engagement",
        "breaks",
        "rig",
    ]


def test_a_family_leaves_the_wire_value_alone():
    """`family` is a property, not part of the value, so every record and every frame
    that carries `Outcome.value` reads exactly what it did before."""
    assert Outcome.CORRECT.value == "correct"
    assert Outcome("abort") is Outcome.ABORT


def test_a_parameter_declares_the_value_a_run_starts_with_or_none():
    """P4d-2b spec §6.2: "Starting values are the task's own" -- S8 §3.4's task layer.
    Optional: a parameter the task leaves to whoever starts the run declares none."""
    assert Param("fix_hold", unit="s", low=0.05, high=2.0).start is None
    assert Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3).start == 0.3


@pytest.mark.parametrize("bad", [Disc(size=1.0), True, float("nan"), float("inf"), "0.3"])
def test_a_parameter_refuses_a_start_that_is_not_a_finite_number(bad):
    """A starting value is recorded and published, and only a number is: a starting
    appearance is not carried until something records and publishes one."""
    with pytest.raises(ValueError, match="'fix_hold'.*starting value is a number"):
        Param("fix_hold", unit="s", low=0.05, high=2.0, start=bad)


def test_a_parameter_keeps_an_int_or_float_start():
    assert Param("n", unit="s", start=3).start == 3
    assert Param("n", unit="s", start=0.3).start == 0.3


@pytest.mark.parametrize(
    "start, said",
    [(50.0, "50.0 is above"), (0.01, "0.01 is below")],
)
def test_a_parameter_refuses_a_start_outside_its_own_declared_range(start, said):
    """The b3a-2 final review, m2: a start outside `[low, high]` passed every load-time
    check, so `wlx run`, which takes no pre-flight (XC-159), would run it. Refused as the
    task is built, naming the parameter, its start and its range."""
    with pytest.raises(ValueError, match=rf"'fix_window'.*{said}.*\[0\.5, 5\.0\]"):
        Param("fix_window", unit="deg", low=0.5, high=5.0, start=start)


def test_a_start_on_its_range_edge_or_with_no_range_or_one_edge_is_kept():
    assert Param("fix_window", unit="deg", low=0.5, high=5.0, start=0.5).start == 0.5
    assert Param("fix_window", unit="deg", low=0.5, high=5.0, start=5.0).start == 5.0
    assert Param("n", unit="s", start=1e9).start == 1e9, "no range declared: kept as before"
    assert Param("n", unit="s", low=0.0, start=1e9).start == 1e9
    with pytest.raises(ValueError, match="'n'.*-1.0 is below the range it declares, at least 0.0"):
        Param("n", unit="s", low=0.0, start=-1.0)
    with pytest.raises(ValueError, match="'n'.*2.0 is above the range it declares, at most 1.0"):
        Param("n", unit="s", high=1.0, start=2.0)


def test_a_start_beside_a_bound_that_is_not_a_number_is_left_to_the_preflight():
    """`Param` checks no other field, so a bound typed as text still loads, and the
    pre-flight fails it closed (`tests/_sessions.malformed_task`); this check compares a
    start only with a bound that is a real number, and raises nothing else."""
    assert Param("fix_hold", unit="s", low="0.05", high=2.0, start=0.3).start == 0.3
