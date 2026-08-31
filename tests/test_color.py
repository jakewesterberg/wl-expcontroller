"""Colour, in a space the display cannot silently reinterpret.

RGB is a set of instructions to a particular monitor, not a description of a light,
so "red" in a task file means a different stimulus on every panel and nothing at all
in a methods section. The flagship pop-out paradigm -- a red target among green
distractors, isoluminant -- was unwritable in this vocabulary until now, and
*isoluminant* is the word that makes a measurement mandatory: it is a claim about
photometry, and a claim nobody measured is a claim that is usually false.
"""

import pytest

from wl_expcontroller.check import check
from wl_expcontroller.photometry import DKL, Calibration, xyY
from wl_expcontroller.task import (
    REMEMBERED,
    After,
    Disc,
    On,
    Outcome,
    Param,
    Show,
    State,
    Stimulus,
    Trial,
    Window,
)

# A plausible sRGB-like panel, as if measured. Numbers here are illustrative and
# are not a claim about any panel we own -- a real one comes from a photometer and
# is committed under docs/measurements/.
PANEL = Calibration(
    red=xyY(0.640, 0.330, 45.0),
    green=xyY(0.300, 0.600, 145.0),
    blue=xyY(0.150, 0.060, 15.0),
    background=xyY(0.3127, 0.3290, 50.0),
    gamma=2.2,
    observer="macaque V(lambda), Sidley & Sperling 1967",
    measured_on="2026-08-31",
)


def a_task(looks) -> Trial:
    return Trial(
        start="on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[
            State(
                "on",
                enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=looks))],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )


def codes(trial, calibration=PANEL) -> set[str]:
    return {f.code for f in check(trial, calibration=calibration)}


def test_a_colour_the_panel_cannot_produce_is_refused():
    """Outside the gamut is not a rendering artifact, it is a different stimulus.

    A monitor asked for a colour it cannot make clips, silently, and the clipped
    colour is neither the requested chromaticity nor the requested luminance -- so
    an isoluminant pair stops being isoluminant and the experiment's control
    condition quietly becomes a luminance manipulation.
    """
    # A monochromatic-locus red, well outside any three-primary display.
    assert "unrealizable-color" in codes(a_task(Disc(color=xyY(0.72, 0.28, 40.0))))


def test_a_colour_inside_the_gamut_is_accepted():
    assert "unrealizable-color" not in codes(a_task(Disc(color=xyY(0.500, 0.400, 30.0))))


def test_a_luminance_the_panel_cannot_reach_is_refused():
    """Inside the gamut in chromaticity and still impossible in brightness."""
    assert "unrealizable-color" in codes(a_task(Disc(color=xyY(0.3127, 0.3290, 900.0))))


def test_colour_without_a_calibration_is_refused():
    """No photometer, no colour.

    The alternative is a task that runs, looks convincing, and reports a colour
    nobody measured -- which is worse than one that will not load, because it
    reaches a methods section.
    """
    assert "uncalibrated-color" in codes(
        a_task(Disc(color=xyY(0.500, 0.400, 30.0))), calibration=None
    )


def test_an_achromatic_task_needs_no_calibration():
    assert codes(a_task(Disc(size=1.0)), calibration=None) == set()


def test_isoluminance_is_a_declared_measurement_not_a_default():
    """`DKL(lum=0)` is isoluminant *by construction*, against a stated observer.

    Construction alone is not enough: the cone contrasts depend on whose luminous
    efficiency the display was measured against, and a macaque's is not a human's.
    A calibration that does not say refuses the colour rather than letting the task
    inherit a silent assumption about the species in the chair.
    """
    unstated = Calibration(
        red=PANEL.red,
        green=PANEL.green,
        blue=PANEL.blue,
        background=PANEL.background,
        gamma=2.2,
        observer="",
        measured_on="2026-08-31",
    )
    isoluminant = Disc(color=DKL(lum=0.0, l_m=0.08))
    assert "unstated-observer" in codes(a_task(isoluminant), calibration=unstated)
    assert "unstated-observer" not in codes(a_task(isoluminant), calibration=PANEL)


def test_a_cone_contrast_beyond_the_measured_maximum_is_refused():
    """The panel's reachable cone contrast is a measured number, not an aspiration."""
    assert "unrealizable-color" in codes(a_task(Disc(color=DKL(l_m=0.95))))


def test_pop_out_is_expressible_as_one_parameter():
    """The paradigm this gap blocked.

    Target and distractors differ in one feature, and which feature is a value --
    so a colour pop-out and a shape pop-out are the same task with a different
    parameter, which is exactly what the declarative model is for.
    """
    red = Disc(size=1.0, color=DKL(lum=0.0, l_m=0.08))
    green = Disc(size=1.0, color=DKL(lum=0.0, l_m=-0.08))
    param = Param("target_looks", unit="appearance", choices=(red, green))
    assert param.choices[0].color.lum == 0.0
    assert param.choices[0].color != param.choices[1].color


def test_an_absolute_colour_cannot_also_carry_a_contrast():
    """`xyY` names a light; `contrast` scales a modulation. Both at once means two
    different things claim to set the same physical quantity, and which one wins is
    the sort of thing nobody discovers until the figures disagree."""
    assert "overspecified-color" in codes(
        a_task(Disc(color=xyY(0.500, 0.400, 30.0), contrast=0.5))
    )
