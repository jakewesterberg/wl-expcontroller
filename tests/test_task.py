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

from wl_expcontroller.task import Disc, FixPoint, P, Stimulus


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
