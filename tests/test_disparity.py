"""Binocular structure that displacing a whole stimulus cannot express.

`Stimulus.disparity` shifts an entire patch, which covers position disparity and
nothing else. Two things the disparity programme cannot do without:

**Anticorrelated RDS.** Dots of opposite contrast in the two eyes. It is the control
every disparity paper is asked for, because V1 responds to it while perceived depth
inverts or vanishes -- so it separates a correlation-based response from a
depth-based one. There is no way to write it as a displacement.

**Disparity-defined form.** A corrugation or a slant is a depth *field* across one
patch, not one number for the patch. It is what 3D-shape work is built on, and it is
also the only way to make a stimulus whose form is invisible monocularly -- Julesz's
whole point, and the reason cyclopean form is a category of its own.
"""

import pytest

from wl_expcontroller.check import check
from wl_expcontroller.task import (
    RDS,
    After,
    Corrugation,
    On,
    Outcome,
    P,
    Param,
    Show,
    Slant,
    State,
    Stimulus,
    Trial,
    Window,
)


def a_task(looks, **stimulus_kwargs) -> Trial:
    stimulus_kwargs.setdefault("at", (0.0, 0.0))
    return Trial(
        start="on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[
            State(
                "on",
                enter=[Show(Stimulus("s", looks=looks, **stimulus_kwargs))],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )


def codes(trial, **kwargs) -> set[str]:
    return {f.code for f in check(trial, **kwargs)}


def test_an_anticorrelated_stereogram_is_expressible():
    """The control condition, statable in one value."""
    correlated = RDS(correlation=1.0)
    anticorrelated = RDS(correlation=-1.0)

    assert anticorrelated.correlation == -1.0
    assert correlated != anticorrelated
    assert codes(a_task(anticorrelated)) == set()


def test_correlation_is_a_parameter_so_the_control_is_a_value_not_a_task():
    """Correlated and anticorrelated conditions must interleave within a session,
    because comparing them across sessions compares two states of the animal."""
    param = Param("correlation", unit="r", low=-1.0, high=1.0)
    trial = a_task(RDS(correlation=P("correlation")))
    trial = Trial(
        start=trial.start,
        states=trial.states,
        params=[param],
        windows=trial.windows,
    )
    assert codes(trial) == set()


def test_a_correlation_outside_minus_one_to_one_is_refused():
    """Correlation is a correlation. 1.5 is not a stronger stimulus, it is not a
    stimulus -- but it reads as one in a generated task file."""
    assert "impossible-correlation" in codes(a_task(RDS(correlation=1.5)))
    assert "impossible-correlation" in codes(
        Trial(
            start="on",
            windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
            params=[Param("corr", unit="r", low=-2.0, high=1.0)],
            states=a_task(RDS(correlation=P("corr"))).states,
        )
    )


def test_a_stereogram_shown_to_one_eye_only_is_refused():
    """A stereogram is a relationship between two images.

    Monocular presentation of one is not a degraded version of the stimulus, it is
    a field of random dots with no disparity at all -- and it would still run,
    still record, and still appear in a figure as a disparity condition.
    """
    assert "monocular-stereogram" in codes(a_task(RDS(), eye="left"))
    assert "monocular-stereogram" not in codes(a_task(RDS(), eye="both"))


def test_disparity_defined_form_is_a_field_not_a_number():
    """A corrugation has a disparity at every point; the patch has no single one."""
    form = Corrugation(sf=0.5, amplitude=0.2, orientation=0.0)
    patch = RDS(form=form)

    assert patch.form is form
    assert patch.disparity_range({}) == pytest.approx((-0.2, 0.2))


def test_a_slant_reports_the_extremes_it_reaches_across_its_aperture():
    """A gradient's disparity depends on how wide the patch is, which is why the
    aperture is part of the answer and not a separate thing to remember."""
    patch = RDS(aperture=4.0, form=Slant(gradient=0.1, orientation=0.0))

    # +/- 0.1 deg of disparity per degree of position, over +/- 2 deg.
    assert patch.disparity_range({}) == pytest.approx((-0.2, 0.2))


def test_form_disparity_counts_toward_the_off_screen_check():
    """Check 8 applies to the depths a patch actually reaches.

    A patch centred safely can still push one eye's image off the panel at the
    extreme of its corrugation -- and only that eye's, which on a split-screen
    stereoscope is a stimulus the animal fuses on one side and loses on the other.
    """
    from wl_expcontroller.geometry import Geometry

    geometry = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)
    safe = a_task(RDS(form=Corrugation(sf=0.5, amplitude=0.2)), at=(15.0, 0.0))
    extreme = a_task(RDS(form=Corrugation(sf=0.5, amplitude=8.0)), at=(15.0, 0.0))

    assert "stimulus-off-screen" not in codes(safe, geometry=geometry)
    assert "stimulus-off-screen" in codes(extreme, geometry=geometry)


def test_a_plain_patch_has_no_disparity_range_of_its_own():
    assert RDS().disparity_range({}) == (0.0, 0.0)
