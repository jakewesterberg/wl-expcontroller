"""Display geometry, for both setups: direct view and the split-screen stereoscope.

**One screen at one place, two paths to it** (direct-view spec §2). The screen is fixed
50 cm from the eyes in both setups (PI, 2026-09-28); the stereoscope is a removable device
in front of it.

- **Direct view:** both eyes see the whole panel, at the screen's own distance. The field
  is the panel's, less the light sensors' housings in a bottom corner (spec §4).
- **The stereoscope:** one panel split down the middle, each eye viewing its half through a
  two-mirror periscope. The mirrors translate rather than deviate, so the *optical path* is
  the physical distance plus the lateral shift: about 63 cm, moving with each animal's eye
  spacing (`Geometry.stereoscope`). A removable mask at the panel stops the field, at ±12°
  to start.

**The panel is given by its active area, not its diagonal.** S0 §5.2's diagonal form
assumes an exact 16:9, and the rig's ASUS PG27UCDM is neither: ASUS publishes its
active area as 589.97 × 332.93 mm (1.772:1) and its diagonal as a rounded "26.5-inch
viewable". Feeding the rounded diagonal through the 16:9 fractions puts each edge
0.6-0.9% short (S0 §5.2).

**Degrees map to the panel by `D · tan`, per axis**, so the field is a rectangle in degrees
as it is in centimeters, and a housing's rectangle on the panel is a region in degrees the
same way.

Every number here is derived from `2026-08-31-stereoscope-optics-drawing.md` §3,
S0 §5.2 and the direct-view spec §2, and the tests assert the agreement. **They are
computed, not measured.** V9 measures each eye's real path per animal, because the
mirror carriage is adjustable and the two paths are equal only if the mirrors are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: The two setups a session can run in (direct-view spec §3). The operator picks one at
#: session start; a task's `Trial.view` names one of these, or `"either"`.
VIEWS = ("direct", "stereoscope")


@dataclass(frozen=True, slots=True)
class Housing:
    """One screen-timing light sensor's opaque housing, as a rectangle on the panel.

    **In cm from the active area's bottom-left corner, as the animal faces the screen**:
    `left_cm` and `right_cm` from its left edge, `bottom_cm` and `top_cm` up from its
    bottom edge -- what a person measures at build with a rule against the panel.

    `margin_cm` is recorded beside the rectangle (direct-view spec §4) and widens it on
    every side, because check 8 tests a stimulus's position, not its extent.
    """

    left_cm: float
    right_cm: float
    bottom_cm: float
    top_cm: float
    margin_cm: float

    def __post_init__(self) -> None:
        values = (self.left_cm, self.right_cm, self.bottom_cm, self.top_cm, self.margin_cm)
        if not all(math.isfinite(v) for v in values):
            raise ValueError(
                f"a housing's rectangle must be finite cm; got {values}. A NaN or "
                f"infinite bound compares as neither covering a point nor excluding "
                f"one, so `covers` would go quiet instead of refusing"
            )
        if self.left_cm >= self.right_cm:
            raise ValueError(
                f"a housing's left edge ({self.left_cm:g} cm) must be less than its "
                f"right edge ({self.right_cm:g} cm); left >= right is a rectangle "
                f"that covers no point on the panel, and a stimulus under the real "
                f"housing would pass"
            )
        if self.bottom_cm >= self.top_cm:
            raise ValueError(
                f"a housing's bottom edge ({self.bottom_cm:g} cm) must be less than "
                f"its top edge ({self.top_cm:g} cm); bottom >= top is a rectangle "
                f"that covers no point on the panel, and a stimulus under the real "
                f"housing would pass"
            )
        if self.margin_cm < 0:
            raise ValueError(
                f"a housing's margin must not be negative; got {self.margin_cm:g} "
                f"cm, which would shrink the excluded rectangle instead of widening "
                f"it (direct-view spec §4)"
            )

    def covers(self, x_cm: float, y_cm: float) -> bool:
        """Whether a point on the panel, in the same corner-origin cm, is under this
        housing or its margin."""
        return (
            self.left_cm - self.margin_cm <= x_cm <= self.right_cm + self.margin_cm
            and self.bottom_cm - self.margin_cm <= y_cm <= self.top_cm + self.margin_cm
        )


@dataclass(frozen=True, slots=True)
class Geometry:
    #: The panel's active area. Through the stereoscope each eye's viewport is half its
    #: width and all of its height; in direct view the viewport is the whole panel.
    panel_width_cm: float
    panel_height_cm: float
    #: Along the **folded** optical path through the stereoscope; the screen's own
    #: distance in direct view.
    viewing_distance_cm: float
    #: `"stereoscope"` or `"direct"` (`VIEWS`).
    view: str = "stereoscope"
    #: The stereoscope's mask at the panel, as a half-angle in degrees (direct-view spec
    #: §2), or `None` for the viewport's own field.
    mask_deg: float | None = None
    #: The light sensors' housings, direct view's alone: through the stereoscope the
    #: mask hides them. **Direct view refuses to exist without them.**
    housings: tuple[Housing, ...] = ()
    #: The half-IPD, `E`, a stereoscope field was built for, in cm: one animal's,
    #: from its settings file (PI, 2026-09-29). `None` in direct view, which has none.
    #: Kept on the field so the record and telemetry read it from the object that
    #: decided the field, never from a second copy.
    half_ipd_cm: float | None = None

    def __post_init__(self) -> None:
        if self.view not in VIEWS:
            raise ValueError(
                f"{self.view!r} is not a setup; a geometry is one of {', '.join(VIEWS)}"
            )
        if self.view == "direct" and not self.housings:
            raise ValueError(
                "direct view's field excludes the light sensors' housings, and none were "
                "given. They are measured at build (direct-view spec §9 item 1); a field "
                "without them would pass a stimulus drawn under a housing"
            )
        if self.view == "stereoscope" and self.housings:
            raise ValueError(
                "the stereoscope's mask hides the light sensors, so a stereoscope "
                "geometry takes no housings; a housing there would exclude degrees "
                "the mask already stops, for a reason that does not hold in this "
                "setup"
            )
        if self.view == "direct" and self.mask_deg is not None:
            raise ValueError(
                f"direct view has no mask -- only the stereoscope's removable mask "
                f"stops the field -- so mask_deg={self.mask_deg!r} on a direct "
                f"geometry would silently narrow the field to a value nothing at the "
                f"rig sets"
            )
        if self.view == "direct" and self.half_ipd_cm is not None:
            raise ValueError(
                "direct view has no half-IPD: both eyes see the one screen at its own "
                "distance, so an animal's eye spacing changes nothing in its field"
            )

    @classmethod
    def stereoscope(
        cls,
        panel_width_cm: float,
        panel_height_cm: float,
        *,
        screen_distance_cm: float,
        half_ipd_cm: float,
        mask_deg: float | None = None,
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
            mask_deg=mask_deg,
            half_ipd_cm=half_ipd_cm,
        )

    @classmethod
    def direct(
        cls,
        panel_width_cm: float,
        panel_height_cm: float,
        *,
        screen_distance_cm: float,
        housings: tuple[Housing, ...],
    ) -> Geometry:
        """The whole panel, seen by both eyes at the screen's own distance, less the
        light sensors' housings (direct-view spec §2, §4)."""
        return cls(
            panel_width_cm=panel_width_cm,
            panel_height_cm=panel_height_cm,
            viewing_distance_cm=screen_distance_cm,
            view="direct",
            housings=tuple(housings),
        )

    @property
    def half_width_cm(self) -> float:
        """The viewport's half-width: the whole panel's in direct view, one eye's half
        through the stereoscope."""
        return self.panel_width_cm / (2 if self.view == "direct" else 4)

    @property
    def half_height_cm(self) -> float:
        return self.panel_height_cm / 2

    @property
    def half_field_h_deg(self) -> float:
        """The horizontal half-field a stimulus may use: the viewport's, or the mask's
        where the mask is narrower."""
        return self._stopped(self._viewport_deg(self.half_width_cm))

    @property
    def half_field_v_deg(self) -> float:
        return self._stopped(self._viewport_deg(self.half_height_cm))

    def _viewport_deg(self, half_cm: float) -> float:
        return math.degrees(math.atan(half_cm / self.viewing_distance_cm))

    def _stopped(self, degrees: float) -> float:
        return degrees if self.mask_deg is None else min(degrees, self.mask_deg)

    def pixels_per_degree(self, horizontal_pixels: int) -> float:
        """S0 §5.2's mean across one viewport, so `horizontal_pixels` is the viewport's:
        half the panel through the stereoscope, all of it in direct view. Across the
        viewport's own extent, not the mask's: the mask covers pixels, it does not
        rescale them."""
        return horizontal_pixels / (2 * self._viewport_deg(self.half_width_cm))

    def can_show(self, x_deg: float, y_deg: float) -> bool:
        """Whether a cyclopean position lands inside the field the setup shows.

        A position outside it is not a rendering problem to clamp -- the stimulus would
        be drawn off the panel, behind the mask or under a light sensor's housing, the
        animal would never see it, and the trial would score as a miss
        indistinguishable from behavior. Refused at load instead.
        """
        if abs(x_deg) > self.half_field_h_deg or abs(y_deg) > self.half_field_v_deg:
            return False
        x_cm = self.panel_width_cm / 2 + self.viewing_distance_cm * math.tan(
            math.radians(x_deg)
        )
        y_cm = self.panel_height_cm / 2 + self.viewing_distance_cm * math.tan(
            math.radians(y_deg)
        )
        return not any(housing.covers(x_cm, y_cm) for housing in self.housings)


@dataclass(frozen=True, slots=True)
class Rig:
    """The rig's display settings: everything both setups' fields are built from
    (direct-view spec §2), written in the rig's settings file, `tasks/rig.py`.

    **The housings may be empty** while they are unmeasured (spec §9 item 1): then
    `direct` refuses, because `Geometry` does, and the stereoscope still works -- its
    mask hides the sensors.

    **A session's field is built from this**: `wlx run --rig` names the file and
    `--view` the setup, and `taskd`'s load-time check runs against that field before
    anything is recorded (direct view part 2, 2026-09-29).
    """

    panel_width_cm: float
    panel_height_cm: float
    #: `Z`: eye to screen, physical, the same in both setups (PI, 2026-09-28).
    screen_distance_cm: float
    #: The stereoscope's mask, as a half-angle (±12° to start, PI 2026-09-28).
    mask_deg: float
    #: The half-IPDs the stereoscope is built for, in cm: the optics drawing's
    #: eye-separation table, IPD 30-38 mm (S0 §7.1.3). An animal outside it is refused
    #: rather than given a field nobody drew.
    half_ipd_range_cm: tuple[float, float]
    housings: tuple[Housing, ...] = ()

    def direct(self) -> Geometry:
        return Geometry.direct(
            self.panel_width_cm,
            self.panel_height_cm,
            screen_distance_cm=self.screen_distance_cm,
            housings=self.housings,
        )

    def stereoscope(self, half_ipd_cm: float) -> Geometry:
        """Through the stereoscope, for one animal's half-IPD, `E`, from its settings
        file (spec §2; PI, 2026-09-29)."""
        low, high = self.half_ipd_range_cm
        if not low <= half_ipd_cm <= high:
            raise ValueError(
                f"a half-IPD of {half_ipd_cm:g} cm is outside the {low:g}-{high:g} cm "
                f"this stereoscope is built for (IPD {20 * low:g}-{20 * high:g} mm, the "
                f"optics drawing's table); its mirrors and its field are unknown there"
            )
        return Geometry.stereoscope(
            self.panel_width_cm,
            self.panel_height_cm,
            screen_distance_cm=self.screen_distance_cm,
            half_ipd_cm=half_ipd_cm,
            mask_deg=self.mask_deg,
        )


@dataclass(frozen=True, slots=True)
class SubjectSettings:
    """One animal's settings, from the file named at session start with
    `--subject-settings` (PI, 2026-09-29), as its bounded config is named with
    `--bounds`.

    Today it holds what the stereoscope's field needs and nothing more: the animal's
    half-IPD, `E`, "measured per animal" (optics drawing §2; backlog XC-082). Direct
    view reads nothing from it. `subject` is checked against the session's own, so one
    animal's eye spacing cannot quietly become another's.
    """

    subject: str
    half_ipd_cm: float

    def __post_init__(self) -> None:
        if not self.subject:
            raise ValueError("subject settings name no subject")
        # `bool` is an `int`; `None` is the placeholder for an unmeasured animal.
        if (
            isinstance(self.half_ipd_cm, bool)
            or not isinstance(self.half_ipd_cm, (int, float))
            or not (math.isfinite(self.half_ipd_cm) and self.half_ipd_cm > 0)
        ):
            raise ValueError(
                f"half_ipd_cm={self.half_ipd_cm!r} is not a half-IPD: half the distance "
                f"between the eyes' centers, in cm, a positive number"
            )
