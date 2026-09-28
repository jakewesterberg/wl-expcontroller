"""Display geometry, and the check that a stimulus can actually be shown.

The numbers come from S0 §5.2's formula and the optics drawing: the ASUS PG27UCDM's
published active area, 589.97 × 332.93 mm (ASUS spec page, read 2026-09-28), split into
two viewports and viewed at 57 cm along the folded path.

**Each property is asserted directly.** Before 2026-09-28 the four extents were covered
only by `tests/test_gaze.py` computing a constellation at import, so a mutation reached
the suite as a collection error rather than as a failed assertion.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.geometry import Geometry

#: The PG27UCDM at the stereoscope's 57 cm (S0 §5.1, §5.2; PI 2026-09-27, 2026-09-28).
STEREOSCOPE = Geometry(
    panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=57.0
)


def test_each_viewport_is_a_quarter_of_the_width_and_half_the_height():
    """The panel is split down the middle: each eye's viewport is half the active
    width and all of its height, so its half-extents are W/4 and H/2."""
    assert STEREOSCOPE.half_width_cm == pytest.approx(14.749, abs=0.001)
    assert STEREOSCOPE.half_height_cm == pytest.approx(16.647, abs=0.001)


def test_the_extents_come_from_the_active_area_not_a_diagonal():
    """ASUS's active area is not exactly 16:9 (1.772:1), and its "26.5-inch viewable"
    is rounded. Width and height are each their own input, so changing one must not
    move the other."""
    wider = Geometry(panel_width_cm=60.0, panel_height_cm=33.293, viewing_distance_cm=57.0)

    assert wider.half_width_cm == pytest.approx(15.0)
    assert wider.half_height_cm == pytest.approx(STEREOSCOPE.half_height_cm)


def test_field_matches_the_optics_drawing():
    """If this drifts from `2026-08-31-stereoscope-optics-drawing.md` §3, one of
    the two is wrong and the rig will be built to whichever nobody checked."""
    assert STEREOSCOPE.half_field_h_deg == pytest.approx(14.508, abs=0.001)
    assert STEREOSCOPE.half_field_v_deg == pytest.approx(16.280, abs=0.001)


def test_the_field_is_along_the_folded_path():
    """The same panel along a shorter path subtends more. 50 cm is the distance the
    PI compared and declined on 2026-09-28."""
    closer = Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=50.0)

    assert closer.half_field_h_deg == pytest.approx(16.435, abs=0.001)
    assert closer.half_field_v_deg == pytest.approx(18.414, abs=0.001)


def test_pixels_per_degree_matches_the_optics_drawing():
    """S0 §5.2's mean over the viewport: 1920 px across 2 × 14.51°."""
    assert STEREOSCOPE.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(
        66.17, abs=0.005
    )


def test_the_field_meets_the_stereoscope_requirement():
    """PI, 2026-09-27: "for the stereoscope setup +/- 10 deg is enough". Every corner
    of a ±10° square must be showable."""
    for x in (-10.0, 10.0):
        for y in (-10.0, 10.0):
            assert STEREOSCOPE.can_show(x, y)


def test_a_position_outside_the_field_is_not_showable():
    """A model asked for a peripheral target will happily write 30 degrees. The
    stimulus would be drawn off the panel, the animal would never see it, and the
    trial would score as a miss that looks like behaviour."""
    assert STEREOSCOPE.can_show(10.0, 5.0)
    assert not STEREOSCOPE.can_show(30.0, 0.0)
    assert not STEREOSCOPE.can_show(0.0, 25.0)


def test_the_field_edge_is_where_the_drawing_puts_it():
    """16° was inside the 31.5-inch panel's ±17.0° and is outside this one's ±14.51°."""
    assert STEREOSCOPE.can_show(14.5, 0.0)
    assert STEREOSCOPE.can_show(-14.5, 0.0)
    assert not STEREOSCOPE.can_show(14.52, 0.0)
    assert not STEREOSCOPE.can_show(-14.52, 0.0)
    assert not STEREOSCOPE.can_show(16.0, 0.0)
    assert STEREOSCOPE.can_show(0.0, 16.27)
    assert STEREOSCOPE.can_show(0.0, -16.27)
    assert not STEREOSCOPE.can_show(0.0, 16.29)
    assert not STEREOSCOPE.can_show(0.0, -16.29)
