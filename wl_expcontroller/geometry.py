"""Display geometry for the split-screen stereoscope.

One panel split down the middle, each eye viewing its half through a two-mirror
periscope. The mirrors translate rather than deviate, so the *optical path* is the
physical eye-to-panel distance plus the lateral shift. The screen is fixed 50 cm from
the eyes in both setups (PI, 2026-09-28), so through the stereoscope the path is about
63 cm, and it moves with each animal's eye spacing (`Geometry.stereoscope`).

**The panel is given by its active area, not its diagonal.** S0 §5.2's diagonal form
assumes an exact 16:9, and the rig's ASUS PG27UCDM is neither: ASUS publishes its
active area as 589.97 × 332.93 mm (1.772:1) and its diagonal as a rounded "26.5-inch
viewable". Feeding the rounded diagonal through the 16:9 fractions puts each edge
0.6-0.9% short of the published area (S0 §5.2).

Every number here is derived from `2026-08-31-stereoscope-optics-drawing.md` §3 and
S0 §5.2, and the tests assert the agreement. **They are computed, not measured.**
V9 measures each eye's real path per animal, because the mirror carriage is
adjustable and the two paths are equal only if the mirrors are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Geometry:
    #: The panel's active area. Each eye's viewport is half its width and all of
    #: its height.
    panel_width_cm: float
    panel_height_cm: float
    #: Along the **folded** optical path, not the physical distance to the panel.
    viewing_distance_cm: float

    @classmethod
    def stereoscope(
        cls,
        panel_width_cm: float,
        panel_height_cm: float,
        *,
        screen_distance_cm: float,
        half_ipd_cm: float,
    ) -> Geometry:
        """The field through the periscope, with the screen `screen_distance_cm` from
        the eyes and the eyes `half_ipd_cm` either side of the midline.

        **The screen is fixed and the path follows from it** (PI, 2026-09-28: the same
        physical distance in the stereoscope and in direct view, 50 cm). Each eye's axis
        is carried from x = ∓E out to its viewport's center at ∓W/4, and that lateral
        run is optical path the physical distance does not show: `D = Z + W/4 − E`.
        So the path, and with it the field, is per animal (optics drawing §3, §4.4).
        """
        return cls(
            panel_width_cm=panel_width_cm,
            panel_height_cm=panel_height_cm,
            viewing_distance_cm=screen_distance_cm + panel_width_cm / 4 - half_ipd_cm,
        )

    @property
    def half_width_cm(self) -> float:
        return self.panel_width_cm / 4

    @property
    def half_height_cm(self) -> float:
        return self.panel_height_cm / 2

    @property
    def half_field_h_deg(self) -> float:
        return math.degrees(math.atan(self.half_width_cm / self.viewing_distance_cm))

    @property
    def half_field_v_deg(self) -> float:
        return math.degrees(math.atan(self.half_height_cm / self.viewing_distance_cm))

    def pixels_per_degree(self, horizontal_pixels: int) -> float:
        """Across one eye's viewport, so `horizontal_pixels` is half the panel."""
        return horizontal_pixels / (2 * self.half_field_h_deg)

    def can_show(self, x_deg: float, y_deg: float) -> bool:
        """Whether a cyclopean position lands inside the field both eyes see.

        A position outside it is not a rendering problem to clamp -- the stimulus would
        be drawn off the panel, the animal would never see it, and the trial would
        score as a miss indistinguishable from behaviour. Refused at load instead.
        """
        return (
            abs(x_deg) <= self.half_field_h_deg
            and abs(y_deg) <= self.half_field_v_deg
        )
