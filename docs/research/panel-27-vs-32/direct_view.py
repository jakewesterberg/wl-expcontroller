#!/usr/bin/env python3
"""Direct-view geometry and eye-camera angles for the 27-inch against 32-inch comparison.

Research artifact, stdlib only. **Direct viewing is not designed anywhere in the specs yet**
(S0, S4 and architecture.md D6 assume the stereoscope); this script only does the arithmetic
the report needs. Nothing here is measured.

Assumptions, each stated in the report:

- The eye is on the perpendicular through the center of the active area, at distance D.
- The housing border (housing height minus active height, makers' figures) is split evenly
  top and bottom (ASSUMED; `--border-bottom-all` puts all of it at the bottom instead).
- The eye camera and its IR LED view the eye from below the screen (the lab's current
  setups, PI 2026-09-27). Anything that must see the eye clears the housing's bottom edge by
  a 2 deg margin (ASSUMED: about the 1.8 deg half-angle of a 100 mm f/2.8 lens's entrance
  pupil seen from 57 cm).
- The paper's P4-centering rule is taken as a 10 deg offset: its LED sits at 25 deg and its
  camera at 35 deg ("the infrared illuminator is placed at a shallower angle than the imaging
  cameras", Ressmeyer et al. 2026, section 3.1). So the lowest camera angle that still
  centers P4 is the LED's floor + 10 deg (ASSUMED transferable).

    python3 docs/research/panel-27-vs-32/direct_view.py            # tables
    python3 docs/research/panel-27-vs-32/direct_view.py --json     # also writes direct_view.json
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-panel-27-vs-32"

# Makers' pages, read 2026-09-27: active area (W, H) and housing height without stand, cm.
PANELS = {
    "32": {"name": "ASUS PG32UCDM3", "W": 69.948, "H": 39.473, "housing_H": 41.3, "housing_W": 71.8},
    "27": {"name": "ASUS PG27UCDM", "W": 58.997, "H": 33.293, "housing_H": 36.92, "housing_W": 61.03},
}
DISTANCES = [45.0, 50.0, 57.0, 65.0, 75.0]
MARGIN_DEG = 2.0
P4_OFFSET_DEG = 10.0  # paper: LED 25 deg, camera 35 deg
PAPER_CAM, PAPER_LED = 35.0, 25.0
IPD_CM = 3.2  # the drawing's placeholder
N_BOROFLOAT = 1.47  # ASSUMED refractive index for a lateral-shift estimate only


def deg(x: float) -> float:
    return math.degrees(x)


def direct(panel: str, D: float, border_bottom_all: bool = False) -> dict:
    p = PANELS[panel]
    hw, hh = p["W"] / 2, p["H"] / 2
    pitch = p["W"] / 3840
    border = p["housing_H"] - p["H"]
    b_bottom = border if border_bottom_all else border / 2
    edge_active = deg(math.atan(hh / D))
    edge_housing = deg(math.atan((hh + b_bottom) / D))
    led_floor = edge_housing + MARGIN_DEG
    cam_floor = edge_housing + MARGIN_DEG  # a camera alone, ignoring P4 centering
    cam_p4 = led_floor + P4_OFFSET_DEG

    def ppd(e: float) -> float:
        return 1.0 / (pitch * math.cos(math.radians(e)) ** 2 / D * 180 / math.pi)

    return {
        "panel": panel,
        "D_cm": D,
        "field_H_deg": deg(math.atan(hw / D)),
        "field_V_deg": edge_active,
        "housing_side_deg": deg(math.atan(p["housing_W"] / 2 / D)),
        "px_per_deg_mean": 3840 / (2 * deg(math.atan(hw / D))),
        "px_per_deg_center": ppd(0.0),
        "px_per_deg_at_15": ppd(15.0),
        "arcmin_per_px_center": 60.0 / ppd(0.0),
        "bottom_edge_active_deg": edge_active,
        "bottom_edge_housing_deg": edge_housing,
        "margin_for_15deg_V": edge_active - 15.0,
        "shows_15deg": edge_active >= 15.0,
        "camera_floor_deg": cam_floor,
        "led_floor_deg": led_floor,
        "camera_p4_centered_min_deg": cam_p4,
        "paper_35_25_fits": led_floor <= PAPER_LED,
        "accommodation_D": 100 / D,
    }


def hot_mirror(tH: float, tV: float, d: float) -> dict:
    """A plane dichroic tilted 45 deg about a horizontal axis, centered d cm in front of the
    eyes, covering both eyes' lines of sight to a field of half-tangents (tH, tV). Rays at
    vertical tangent v meet it at z = d / (1 + v) (near edge) to d / (1 - v) (far edge)."""
    z_far, z_near = d / (1 - tV), d / (1 + tV)
    return {
        "d_cm": d,
        "length_along_tilt_cm": math.sqrt(2) * d * (tV / (1 - tV) + tV / (1 + tV)),
        "width_far_edge_cm": IPD_CM + 2 * z_far * tH,
        "width_near_edge_cm": IPD_CM + 2 * z_near * tH,
        "aoi_range_deg": (45 - deg(math.atan(tV)), 45 + deg(math.atan(tV))),
        "aoi_at_side_deg": deg(math.acos(math.cos(math.radians(45)) * math.cos(math.atan(tH)))),
    }


def plate_shift_mm(aoi_deg: float, t_mm: float = 3.3, n: float = N_BOROFLOAT) -> float:
    a = math.radians(aoi_deg)
    r = math.asin(math.sin(a) / n)
    return t_mm * math.sin(a - r) / math.cos(r)


def main() -> None:
    bottom_all = "--border-bottom-all" in sys.argv
    rows = [direct(p, D, bottom_all) for p in ("32", "27") for D in DISTANCES]
    print(f"border split: {'all at bottom' if bottom_all else 'even (ASSUMED)'}; margin {MARGIN_DEG} deg")
    print("pan  D    field H x V     ppd mean/c/15      bottom act/hous  15deg margin  cam floor  LED floor  cam(P4)  35/25 fits  acc")
    for r in rows:
        print(f"{r['panel']:3} {r['D_cm']:4.0f}  +/-{r['field_H_deg']:4.1f} x {r['field_V_deg']:4.1f}  "
              f"{r['px_per_deg_mean']:5.1f}/{r['px_per_deg_center']:5.1f}/{r['px_per_deg_at_15']:5.1f}  "
              f"{r['bottom_edge_active_deg']:5.1f}/{r['bottom_edge_housing_deg']:5.1f}   {r['margin_for_15deg_V']:+5.1f}      "
              f"{r['camera_floor_deg']:5.1f}     {r['led_floor_deg']:5.1f}     {r['camera_p4_centered_min_deg']:5.1f}   "
              f"{str(r['paper_35_25_fits']):5}   {r['accommodation_D']:.2f}")
    hm = {}
    for p in ("32", "27"):
        P = PANELS[p]
        for D in (57.0,):
            full = (P["W"] / 2 / D, P["H"] / 2 / D)
            box17 = (math.tan(math.radians(17)), math.tan(math.radians(17)))
            for label, (tH, tV) in (("full screen", full), ("+/-17 deg", box17)):
                for d in (6.0, 8.0, 10.0):
                    hm[f"{p} @ {D:.0f}, {label}, d={d:.0f}"] = hot_mirror(tH, tV, d)
    print("\nhot mirror (45 deg about a horizontal axis):")
    for k, v in hm.items():
        print(f"  {k:32}: {v['width_far_edge_cm']:5.1f} (far) / {v['width_near_edge_cm']:4.1f} (near) wide x "
              f"{v['length_along_tilt_cm']:4.1f} cm along the tilt; AOI {v['aoi_range_deg'][0]:.0f}-{v['aoi_range_deg'][1]:.0f} deg, "
              f"{v['aoi_at_side_deg']:.0f} at the side")
    shifts = {a: plate_shift_mm(a) for a in (26, 30, 45, 60, 64)}
    print("\nlateral image shift through 3.3 mm BOROFLOAT (n ASSUMED 1.47):",
          {a: round(s, 2) for a, s in shifts.items()})
    if "--json" in sys.argv:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "direct_view.json").write_text(json.dumps(
            {"assumptions": {"border_bottom_all": bottom_all, "margin_deg": MARGIN_DEG,
                             "p4_offset_deg": P4_OFFSET_DEG, "ipd_cm": IPD_CM},
             "rows": rows, "hot_mirror": hm, "plate_shift_mm": shifts}, indent=1) + "\n")
        print(f"wrote {RESULTS / 'direct_view.json'}")


if __name__ == "__main__":
    main()
