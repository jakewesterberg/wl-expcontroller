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
