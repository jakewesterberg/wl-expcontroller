"""Display geometry, and the check that a stimulus can actually be shown.

The numbers come from S0 §5.2's formula and the optics drawing: a 31.5" 16:9 panel
split into two viewports, viewed at 57 cm along the folded path.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.geometry import Geometry


def test_field_matches_the_optics_drawing():
    """If this drifts from `2026-08-31-stereoscope-optics-drawing.md` §3, one of
    the two is wrong and the rig will be built to whichever nobody checked."""
    geometry = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)

    assert geometry.half_field_h_deg == pytest.approx(17.0, abs=0.05)
    assert geometry.half_field_v_deg == pytest.approx(19.0, abs=0.05)


def test_pixels_per_degree_matches_the_optics_drawing():
    geometry = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)

    assert geometry.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(
        56.5, abs=0.5
    )


def test_a_position_outside_the_field_is_not_showable():
    """A model asked for a peripheral target will happily write 30 degrees. The
    stimulus would be drawn off the panel, the animal would never see it, and the
    trial would score as a miss that looks like behaviour."""
    geometry = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)

    assert geometry.can_show(10.0, 5.0)
    assert not geometry.can_show(30.0, 0.0)
    assert not geometry.can_show(0.0, 25.0)
