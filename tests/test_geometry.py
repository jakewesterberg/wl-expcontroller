"""Display geometry, and the check that a stimulus can actually be shown.

The numbers come from S0 §5.2's formula and the optics drawing: the ASUS PG27UCDM's
published active area, 589.97 × 332.93 mm (ASUS spec page, read 2026-09-28), split into
two viewports. The screen is fixed 50 cm from the eyes in both setups (PI, 2026-09-28), so
the stereoscope's folded path is `D = Z + HW − E`: 63.15 cm at the drawing's `E` = 1.6 cm.

**Each property is asserted directly.** Before 2026-09-28 the four extents were covered
only by `tests/test_gaze.py` computing a constellation at import, so a mutation reached
the suite as a collection error rather than as a failed assertion.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.geometry import Geometry

#: The PG27UCDM through the stereoscope, the screen at 50 cm, `E` = 1.6 cm
#: (S0 §5.1, §5.2; PI 2026-09-27, 2026-09-28).
STEREOSCOPE = Geometry.stereoscope(
    panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
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
    wider = Geometry(panel_width_cm=60.0, panel_height_cm=33.293, viewing_distance_cm=63.0)

    assert wider.half_width_cm == pytest.approx(15.0)
    assert wider.half_height_cm == pytest.approx(STEREOSCOPE.half_height_cm)


def test_the_stereoscope_path_is_the_screen_distance_plus_the_lateral_run():
    """The periscope carries each eye's axis from x = ∓E out to its viewport's center at
    ∓W/4, and that run is optical path the screen's physical distance does not show:
    `D = Z + W/4 − E`."""
    assert STEREOSCOPE.viewing_distance_cm == pytest.approx(63.149, abs=0.001)

    other = Geometry.stereoscope(
        panel_width_cm=60.0, panel_height_cm=30.0, screen_distance_cm=40.0, half_ipd_cm=2.0
    )
    assert other.viewing_distance_cm == pytest.approx(53.0)
    assert other.panel_width_cm == 60.0
    assert other.panel_height_cm == 30.0


def test_the_path_is_per_animal_because_the_screen_is_fixed():
    """With the screen fixed, wider-set eyes need less lateral run, so the path is
    shorter and the field wider: IPD 30-38 mm spans 63.25-62.85 cm."""
    narrow = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.5
    )
    wide = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.9
    )

    assert narrow.viewing_distance_cm == pytest.approx(63.249, abs=0.001)
    assert wide.viewing_distance_cm == pytest.approx(62.849, abs=0.001)
    assert narrow.half_field_h_deg == pytest.approx(13.126, abs=0.001)
    assert wide.half_field_h_deg == pytest.approx(13.207, abs=0.001)


def test_field_matches_the_optics_drawing():
    """If this drifts from `2026-08-31-stereoscope-optics-drawing.md` §3, one of
    the two is wrong and the rig will be built to whichever nobody checked."""
    assert STEREOSCOPE.half_field_h_deg == pytest.approx(13.146, abs=0.001)
    assert STEREOSCOPE.half_field_v_deg == pytest.approx(14.768, abs=0.001)


def test_pixels_per_degree_matches_the_optics_drawing():
    """S0 §5.2's mean over the viewport: 1920 px across 2 × 13.15°."""
    assert STEREOSCOPE.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(
        73.02, abs=0.005
    )


def test_the_field_meets_the_stereoscope_requirement():
    """PI, 2026-09-27: "for the stereoscope setup +/- 10 deg is enough". Every corner
    of a ±10° square must be showable."""
    for x in (-10.0, 10.0):
        for y in (-10.0, 10.0):
            assert STEREOSCOPE.can_show(x, y)


def test_the_mask_fits_inside_the_field_for_every_ipd():
    """The PI's removable mask at the panel starts at ±12° (2026-09-28). The field it
    stops must be at least that wide for every IPD the drawing tabulates, or the mask
    stops nothing on one side."""
    for half_ipd_cm in (1.5, 1.6, 1.9):
        field = Geometry.stereoscope(
            panel_width_cm=58.997,
            panel_height_cm=33.293,
            screen_distance_cm=50.0,
            half_ipd_cm=half_ipd_cm,
        )
        for x in (-12.0, 12.0):
            for y in (-12.0, 12.0):
                assert field.can_show(x, y)


def test_a_position_outside_the_field_is_not_showable():
    """A model asked for a peripheral target will happily write 30 degrees. The
    stimulus would be drawn off the panel, the animal would never see it, and the
    trial would score as a miss that looks like behaviour."""
    assert STEREOSCOPE.can_show(10.0, 5.0)
    assert not STEREOSCOPE.can_show(30.0, 0.0)
    assert not STEREOSCOPE.can_show(0.0, 25.0)


def test_the_field_edge_is_where_the_drawing_puts_it():
    """±13.5°, the reference tasks' bound for the screen at 43.85 cm, is outside the
    field with the screen at 50 cm."""
    assert STEREOSCOPE.can_show(13.14, 0.0)
    assert STEREOSCOPE.can_show(-13.14, 0.0)
    assert not STEREOSCOPE.can_show(13.16, 0.0)
    assert not STEREOSCOPE.can_show(-13.16, 0.0)
    assert not STEREOSCOPE.can_show(13.5, 0.0)
    assert STEREOSCOPE.can_show(0.0, 14.76)
    assert STEREOSCOPE.can_show(0.0, -14.76)
    assert not STEREOSCOPE.can_show(0.0, 14.78)
    assert not STEREOSCOPE.can_show(0.0, -14.78)
