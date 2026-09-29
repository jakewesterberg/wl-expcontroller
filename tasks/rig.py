"""This rig's display settings: what both setups' fields are built from.

The direct-view spec §2: "The rig's settings hold everything the geometry needs: `Z`; the
mask's half-angle; the sensor housings' rectangles." One screen at one place serves both
setups, so one file does too: `Rig.direct()` is the field in direct view, and
`Rig.stereoscope(E)` the field through the stereoscope for a subject whose half-IPD, `E`,
comes from its record.

Python rather than YAML, for the reason the tasks and `reference_bounds.py` are (ADR-0006):
plain text, diffable, and read in an ordinary editor.

**The light sensors' housings are not measured yet** (direct-view spec §9 item 1: "measured
at build from the real sensors"). Until they are, `housings` is empty and `RIG.direct()`
refuses, so no task passes a direct-view check on this rig's settings. That is deliberate: a
field without them would pass a stimulus drawn under a housing, and a guessed rectangle is a
number nobody measured. The tests stand for this rig with stand-in housings they label as
such.

**Sessions are checked against this file** since direct view part 2: `wlx run --rig` and
`wlx check --rig` load it and build the chosen setup's field from it.
"""

from wl_xcon.geometry import Rig

RIG = Rig(
    # The ASUS PG27UCDM's published active area, 589.97 × 332.93 mm (spec page, read
    # 2026-09-28; S0 §5.1).
    panel_width_cm=58.997,
    panel_height_cm=33.293,
    # `Z`, eye to screen, physical, in both setups (PI, 2026-09-28; direct-view spec §1).
    # Measured once at setup and re-checked in the regular rig checks (V9).
    screen_distance_cm=50.0,
    # The stereoscope's removable mask at the panel, starting at ±12° (PI, 2026-09-28;
    # optics drawing §5).
    mask_deg=12.0,
    # The half-IPDs the stereoscope is built for: IPD 30-38 mm, the optics drawing's
    # eye-separation table (S0 §7.1.3). An animal outside it is refused.
    half_ipd_range_cm=(1.5, 1.9),
    # NOT YET MEASURED: the light sensors' housings, each a rectangle with its margin,
    # measured at build from the real sensors (direct-view spec §4, §9 item 1). Until
    # then direct view refuses to exist on these settings.
    housings=(),
)
