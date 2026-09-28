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

from dataclasses import replace

import pytest

from tasks.rig import RIG
from wl_expcontroller.geometry import Geometry, Housing

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


# ---------------------------------------------------------------------------
# Direct view, and the stereoscope's mask (direct-view spec §2, §4)
# ---------------------------------------------------------------------------

#: **Stand-ins for the light sensors' housings, not a measurement**: the real ones are
#: measured at build (direct-view spec §9 item 1). One per bottom corner, 4 × 3 cm with
#: a 0.5 cm margin, in cm from the active area's bottom-left corner.
HOUSINGS = (
    Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
)

#: The PG27UCDM seen directly with the screen at 50 cm (direct-view spec §2), with the
#: stand-in housings.
DIRECT = Geometry.direct(58.997, 33.293, screen_distance_cm=50.0, housings=HOUSINGS)

#: The same screen through the stereoscope at `E` = 1.6 cm, stopped by the PI's ±12° mask.
MASKED = Geometry.stereoscope(
    58.997, 33.293, screen_distance_cm=50.0, half_ipd_cm=1.6, mask_deg=12.0
)


def test_direct_view_is_the_whole_panel_at_the_screens_own_distance():
    """No periscope, so no lateral run: the path is `Z`, and the viewport is the whole
    panel, seen by both eyes."""
    assert DIRECT.view == "direct"
    assert DIRECT.viewing_distance_cm == 50.0
    assert DIRECT.half_width_cm == pytest.approx(29.4985)
    assert DIRECT.half_height_cm == pytest.approx(16.6465)


def test_direct_views_field_is_the_spec_tables():
    """The direct-view spec §2's table: ±30.5° × ±18.4° at `Z` = 50 cm."""
    assert DIRECT.half_field_h_deg == pytest.approx(30.539, abs=0.001)
    assert DIRECT.half_field_v_deg == pytest.approx(18.414, abs=0.001)


def test_pixels_per_degree_in_direct_view_are_across_the_whole_panel():
    """S0 §5.2's mean, with the viewport the whole panel: 3840 px across 2 × 30.54°.
    (The spec's 56.8 is the center's, a different statistic.)"""
    assert DIRECT.pixels_per_degree(horizontal_pixels=3840) == pytest.approx(
        62.87, abs=0.005
    )


def test_direct_view_refuses_to_exist_without_the_housings():
    """A missing measurement is not an absent housing. A direct-view field with no
    exclusions would pass a stimulus drawn under a sensor, so it is refused, by either
    road to it, naming what is missing."""
    with pytest.raises(ValueError, match="§9 item 1"):
        Geometry.direct(58.997, 33.293, screen_distance_cm=50.0, housings=())
    with pytest.raises(ValueError, match="housings"):
        Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=50.0,
                 view="direct")


def test_a_setup_that_is_neither_is_refused():
    """`view="stereo"` is not a setup. Read as one or the other it would compute a
    field for a screen nobody has."""
    with pytest.raises(ValueError, match="'stereo' is not a setup"):
        Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=50.0,
                 view="stereo")


def test_a_stimulus_under_a_housing_cannot_be_shown():
    """Direct-view spec §4: check 8 refuses a stimulus that could overlap a housing,
    exactly as it refuses one off the panel. Both bottom corners here, since which
    corner the sensors take is a build finding."""
    assert not DIRECT.can_show(-29.0, -17.0)
    assert not DIRECT.can_show(29.0, -17.0)
    assert DIRECT.can_show(-29.0, 0.0), "the side of the panel, above the housing"
    assert DIRECT.can_show(0.0, -18.0), "the bottom of the panel, between them"
    assert DIRECT.can_show(16.0, 0.0)
    assert not DIRECT.can_show(31.0, 0.0), "off the panel"
    assert not DIRECT.can_show(0.0, 18.5), "off the panel"


def test_a_housings_margin_is_part_of_it():
    """The margin is recorded beside each rectangle and widens it on every side.
    4.5 cm in from the left edge is 26.565° left of center at 50 cm; 3.5 cm up from
    the bottom is 14.731° below it."""
    housing = HOUSINGS[0]
    assert housing.covers(4.5, 1.0) and not housing.covers(4.51, 1.0)
    assert housing.covers(-0.5, 1.0) and not housing.covers(-0.51, 1.0)
    assert housing.covers(2.0, 3.5) and not housing.covers(2.0, 3.51)
    assert housing.covers(2.0, -0.5) and not housing.covers(2.0, -0.51)

    assert not DIRECT.can_show(-26.6, -16.0)
    assert DIRECT.can_show(-26.5, -16.0)
    assert not DIRECT.can_show(-29.0, -14.8)
    assert DIRECT.can_show(-29.0, -14.6)


def test_the_mask_is_the_stereoscopes_field():
    """The PI's removable mask at the panel, ±12° to start (2026-09-28): inside the
    viewport's ±13.15° × ±14.77°, so it sets both edges."""
    assert MASKED.half_field_h_deg == 12.0
    assert MASKED.half_field_v_deg == 12.0
    assert MASKED.can_show(11.99, -11.99)
    assert not MASKED.can_show(12.01, 0.0)
    assert not MASKED.can_show(0.0, -12.01)


def test_a_mask_wider_than_the_viewport_stops_nothing():
    """The mask can only narrow the field. One cut wider than the viewport leaves the
    viewport's own edge, which is where the mirrors end."""
    wide = Geometry.stereoscope(
        58.997, 33.293, screen_distance_cm=50.0, half_ipd_cm=1.6, mask_deg=20.0
    )
    assert wide.half_field_h_deg == pytest.approx(13.146, abs=0.001)
    assert wide.half_field_v_deg == pytest.approx(14.768, abs=0.001)


def test_the_mask_covers_pixels_and_does_not_rescale_them():
    """Pixels per degree are the viewport's: the mask hides the edge, it does not
    change what one pixel subtends."""
    assert MASKED.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(
        STEREOSCOPE.pixels_per_degree(horizontal_pixels=1920)
    )
    assert MASKED.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(73.02, abs=0.005)


# ---------------------------------------------------------------------------
# The rig's settings (direct-view spec §2), `tasks/rig.py`
# ---------------------------------------------------------------------------


def test_the_rigs_settings_are_its_screen_its_distance_and_its_mask():
    """"The rig's settings hold everything the geometry needs": the PG27UCDM's
    published active area, `Z` = 50 cm in both setups, and the mask at ±12° (PI,
    2026-09-28)."""
    assert (RIG.panel_width_cm, RIG.panel_height_cm) == (58.997, 33.293)
    assert RIG.screen_distance_cm == 50.0
    assert RIG.mask_deg == 12.0


def test_the_rigs_housings_are_unmeasured_so_direct_view_refuses_on_its_settings():
    """NOT YET MEASURED (direct-view spec §9 item 1), and this pins it: when the
    housings are written into `tasks/rig.py`, this fails, and is replaced by a test of
    the measured rectangles. Until then no task passes direct view on this rig."""
    assert RIG.housings == ()
    with pytest.raises(ValueError, match="§9 item 1"):
        RIG.direct()


def test_the_rig_gives_direct_view_the_panel_at_z_and_its_housings():
    assert replace(RIG, housings=HOUSINGS).direct() == DIRECT


def test_the_rig_gives_the_stereoscope_its_mask_and_the_subjects_path():
    """`E` comes from the subject's record (spec §2), so the stereoscope's field is
    built per subject; the mask is the rig's and stops it at every IPD the drawing
    tabulates."""
    assert RIG.stereoscope(half_ipd_cm=1.6) == MASKED
    assert RIG.stereoscope(half_ipd_cm=1.9).viewing_distance_cm == pytest.approx(
        62.849, abs=0.001
    )
    for half_ipd_cm in (1.5, 1.6, 1.9):
        field = RIG.stereoscope(half_ipd_cm=half_ipd_cm)
        assert (field.half_field_h_deg, field.half_field_v_deg) == (12.0, 12.0)
