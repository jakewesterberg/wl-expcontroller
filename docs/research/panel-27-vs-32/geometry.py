#!/usr/bin/env python3
"""Stereoscope geometry for the 27-inch against 32-inch panel comparison (research artifact).

Every relation here is taken from the two specs, not invented:

- S0 section 5.2: half_width = W/4, half_height = H/2, theta = atan(half / D) along the
  folded path, px_per_deg = (W_px / 2) / (2 * theta_H_deg).
- The optics drawing (2026-08-31-stereoscope-optics-drawing.md):
  - lateral shift per eye = HW - E; physical eye-to-screen distance Z = D - (HW - E);
  - symmetric-field rule a = E / tan(theta_H) (section 4), nasal clip atan(E / a);
  - mirror size = sqrt(2) * d * (tan(temporal) + tan(nasal)) by 2 * d * tan(vertical),
    with d the optical distance from the eye to the mirror's center (reverse-engineered
    below from the drawing's own 53 x 48 mm and 173 x 157 mm, which it reproduces);
  - photodiode strip = HH - D * tan(stop) (section 5).

A second, exact calculation is added and labeled as such: a point-eye ray trace through
the two 45-degree mirrors. It exposes two simplifications in the drawing's relations
(nasal clip and the 45-degree footprint), which are the same for both panels at equal
angular field and so do not decide the panel question.

Nothing here is measured. Panel dimensions are the makers' published active areas
(read 2026-09-27; see the report). Run:

    python3 docs/research/panel-27-vs-32/geometry.py            # prints the tables
    python3 docs/research/panel-27-vs-32/geometry.py --json     # also writes geometry.json
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-panel-27-vs-32"

D2R = math.pi / 180.0
W_PX = 3840

# Makers' active areas, mm (read 2026-09-27):
#   ASUS PG32UCDM3 spec page: "699.48 x 394.73 mm", pixel pitch 0.182 mm.
#   ASUS PG27UCDM spec page:  "589.97 x 332.93 mm", pixel pitch 0.153 mm (MSI MPG 272URX
#   and Samsung LS27HG802 list the same area).
PANELS = {
    "32 (PG32UCDM3)": (69.948, 39.473),
    "27 (PG27UCDM)": (58.997, 33.293),
    # Nominal diagonals, for checking S0's formula and the PI's arithmetic:
    "31.5 nominal (S0)": (80.0 * 16 / math.hypot(16, 9), 80.0 * 9 / math.hypot(16, 9)),
    "27.0 nominal": (68.58 * 16 / math.hypot(16, 9), 68.58 * 9 / math.hypot(16, 9)),
}

E_NOMINAL = 1.60  # cm, half-IPD placeholder the drawing uses (IPD 32 mm)
E_RANGE = (1.50, 1.90)  # the drawing's IPD table, 30-38 mm
PLANE_S3 = 7.0  # cm, the drawing's section 3 mirror plane (before the symmetric ruling)


def field(panel: str, D: float) -> dict:
    W, H = PANELS[panel]
    HW, HH = W / 4.0, H / 2.0
    tH = math.degrees(math.atan(HW / D))
    tV = math.degrees(math.atan(HH / D))
    pitch = W / W_PX  # cm per pixel
    # Pixel angular size along the horizontal meridian at eccentricity e:
    # d(theta)/dx = cos^2(theta) / D, so arcmin/px = pitch * cos^2(e) / D in arcmin.
    def arcmin_px(e_deg: float) -> float:
        return pitch * math.cos(e_deg * D2R) ** 2 / D * 60.0 / D2R

    return {
        "panel": panel,
        "D_cm": D,
        "HW_cm": HW,
        "HH_cm": HH,
        "theta_H_deg": tH,
        "theta_V_deg": tV,
        "px_per_deg_mean_S0": (W_PX / 2) / (2 * tH),
        "px_per_deg_center": 1.0 / (arcmin_px(0.0) / 60.0),
        "px_per_deg_at_15": 1.0 / (arcmin_px(15.0) / 60.0),
        "arcmin_per_px_center": arcmin_px(0.0),
        "arcmin_per_px_at_15": arcmin_px(15.0),
        "arcmin_per_px_at_edge": arcmin_px(tH),
        "pitch_mm": pitch * 10.0,
        "shows_15deg_H": tH >= 15.0,
        "accommodation_D": 100.0 / D,
    }


def drawing_mirrors(HW: float, D: float, E: float, a: float, tV_deg: float) -> dict:
    """The drawing's own relations, for M1 centered at axial distance a from the eye."""
    tT = HW / D  # temporal half-field, tan
    tN = min(E / a, HW / D)  # nasal: the drawing's clip atan(E/a), capped by the viewport
    tV = math.tan(tV_deg * D2R)
    lat = HW - E
    d2 = a + lat
    return {
        "a_cm": a,
        "nasal_clip_deg_drawing": math.degrees(math.atan(E / a)),
        "lateral_shift_cm": lat,
        "Z_physical_cm": D - lat,
        "mirror_plane_to_screen_cm": D - lat - a,
        "M1_center_x_cm": E,
        "M2_center_x_cm": HW,
        "M1_mm": (10 * math.sqrt(2) * a * (tT + tN), 10 * 2 * a * tV),
        "M2_mm": (10 * math.sqrt(2) * d2 * (tT + tN), 10 * 2 * d2 * tV),
    }


def exact_mirrors(HW: float, D: float, E: float, a: float, tV_deg: float) -> dict:
    """Point-eye ray trace through both 45-degree mirrors (left eye; x < 0 is temporal).

    Unfolded frame: M1 is the plane x + z = a, M2 the plane x + z = a + lat. A ray with
    direction (u, v, 1) meets a plane x + z = c at distance c / (1 + u). The field is the
    viewport: |u| <= HW / D and |v| <= tan(tV). The nasal edge of M1 is the roof ridge,
    which sits at x = E, z = a - E, so the ridge clips at u = E / (a - E).
    """
    tT = HW / D
    u_ridge = E / (a - E) if a > E else float("inf")
    tN = min(tT, u_ridge)
    tV = math.tan(tV_deg * D2R)
    lat = HW - E

    def mirror(c: float) -> dict:
        h_t = math.sqrt(2) * c * (-tT) / (1 - tT)  # along-mirror coordinate, temporal edge
        h_n = math.sqrt(2) * c * tN / (1 + tN)
        return {
            "length_mm": 10 * (h_n - h_t),
            "height_temporal_mm": 10 * 2 * c * tV / (1 - tT),
            "height_center_mm": 10 * 2 * c * tV,
            "height_nasal_mm": 10 * 2 * c * tV / (1 + tN),
        }

    # Real-space positions (relative to the eye; z toward the screen) of each mirror's
    # edges on the horizontal meridian.
    def m1_pt(u: float) -> tuple[float, float]:
        return (a * u / (1 + u), a / (1 + u))

    def m2_pt(u: float) -> tuple[float, float]:
        return ((a * u - lat) / (1 + u), (a - u * lat) / (1 + u))

    return {
        "nasal_clip_deg_exact": math.degrees(math.atan(u_ridge)),
        "nasal_limited_by": "viewport" if u_ridge >= tT else "roof ridge",
        "ridge_z_cm": a - E,
        "a_exact_symmetric_cm": E * (1 + 1 / tT),
        "M1": mirror(a),
        "M2": mirror(a + lat),
        "M1_temporal_edge_xz_cm": m1_pt(-tT),
        "M1_nasal_edge_xz_cm": m1_pt(tN),
        "M2_temporal_edge_xz_cm": m2_pt(-tT),
        "M2_nasal_edge_xz_cm": m2_pt(tN),
        "M1_bottom_at_eye_x_deg": math.degrees(math.atan(tV)),
    }


def camera_line(D: float, HW: float, HH: float, E: float, housing_h_cm: float, cam_deg: float = 35.0,
                work_cm: float = 57.0) -> dict:
    """Where a camera 35 deg below the line of sight, 57 cm from the eye (the paper's
    geometry), sits against the panel. Assumes the eye is level with the viewport center
    and the active area is vertically centered in the housing (ASSUMED)."""
    Z = D - (HW - E)
    t = math.tan(cam_deg * D2R)
    y_at_panel = -Z * t
    housing_bottom = -housing_h_cm / 2.0
    return {
        "Z_cm": Z,
        "line_height_at_panel_plane_cm": y_at_panel,
        "active_area_bottom_cm": -HH,
        "housing_bottom_cm_ASSUMED_centered": housing_bottom,
        "clearance_below_housing_cm": housing_bottom - y_at_panel,
        "camera_z_cm": work_cm * math.cos(cam_deg * D2R),
        "camera_y_cm": -work_cm * math.sin(cam_deg * D2R),
        "camera_behind_panel_plane_cm": work_cm * math.cos(cam_deg * D2R) - Z,
    }


# Housing heights without stand (maker pages, 2026-09-27): PG32UCDM3 41.3 cm; PG27UCDM 36.92 cm.
HOUSING_H = {"32 (PG32UCDM3)": 41.3, "27 (PG27UCDM)": 36.92}


def options() -> list[tuple[str, str, float]]:
    W32 = PANELS["32 (PG32UCDM3)"][0]
    W27 = PANELS["27 (PG27UCDM)"][0]
    d_same = 57.0 * (W27 / 4) / (W32 / 4)  # 27 at the distance giving the 32's field
    d_16 = (W27 / 4) / math.tan(16.0 * D2R)  # 27 at +/-16.0 deg horizontal
    return [
        ("A", "32 (PG32UCDM3)", 57.0),
        ("B", "27 (PG27UCDM)", 57.0),
        ("C", "27 (PG27UCDM)", d_same),
        ("D", "27 (PG27UCDM)", d_16),
    ]


def main() -> None:
    out = {"options": [], "checks": {}}
    # --- checks against S0 and the PI's arithmetic -----------------------------------
    s0 = field("31.5 nominal (S0)", 57.0)
    n27 = field("27.0 nominal", 57.0)
    hw27 = PANELS["27.0 nominal"][0] / 4
    out["checks"] = {
        "S0_31.5_at_57": [round(s0["theta_H_deg"], 2), round(s0["theta_V_deg"], 2), round(s0["px_per_deg_mean_S0"], 1)],
        "PI_27.0_half_width_cm": round(hw27, 3),
        "PI_27.0_theta_H_at_57": round(n27["theta_H_deg"], 2),
        "PI_27.0_D_for_17deg_cm": round(hw27 / math.tan(17 * D2R), 2),
        "maker_27_D_for_17deg_cm": round(PANELS["27 (PG27UCDM)"][0] / 4 / math.tan(17 * D2R), 2),
        # The drawing's section 3 mirror sizes, reproduced from its relations:
        "drawing_s3_reproduced": drawing_mirrors(PANELS["31.5 nominal (S0)"][0] / 4, 57.0, 1.6, 7.0, 19.0)["M1_mm"]
        + drawing_mirrors(PANELS["31.5 nominal (S0)"][0] / 4, 57.0, 1.6, 7.0, 19.0)["M2_mm"],
        "drawing_s42_reproduced_E1.9_stop17": drawing_mirrors(PANELS["31.5 nominal (S0)"][0] / 4, 57.0, 1.9, 1.9 / math.tan(17 * D2R), 17.0)["M1_mm"]
        + drawing_mirrors(PANELS["31.5 nominal (S0)"][0] / 4, 57.0, 1.9, 1.9 / math.tan(17 * D2R), 17.0)["M2_mm"],
    }
    for key, panel, D in options():
        f = field(panel, D)
        HW, HH = f["HW_cm"], f["HH_cm"]
        tH, tV = f["theta_H_deg"], f["theta_V_deg"]
        row = {"option": key, **f}
        # Mirrors: the symmetric rule (drawing section 4), nominal E, full vertical field
        # and with the vertical stop at +/- theta_H (drawing section 5).
        a_sym = E_NOMINAL / math.tan(tH * D2R)
        row["mirrors_sym_fullV"] = drawing_mirrors(HW, D, E_NOMINAL, a_sym, tV)
        row["mirrors_sym_stop"] = drawing_mirrors(HW, D, E_NOMINAL, a_sym, tH)
        a_big = E_RANGE[1] / math.tan(tH * D2R)
        row["mirrors_sym_stop_largest_ipd"] = drawing_mirrors(HW, D, E_RANGE[1], a_big, tH)
        row["mirrors_s3_plane7"] = drawing_mirrors(HW, D, E_NOMINAL, PLANE_S3, tV)
        row["exact_sym_stop"] = exact_mirrors(HW, D, E_NOMINAL, a_sym, tH)
        row["exact_sym_stop_largest_ipd"] = exact_mirrors(HW, D, E_RANGE[1], a_big, tH)
        row["photodiode_strip_cm"] = HH - D * math.tan(tH * D2R)  # stop at +/- theta_H
        row["photodiode_strip_px"] = (HH - D * math.tan(tH * D2R)) / (f["pitch_mm"] / 10)
        row["vergence_deg"] = 2 * math.degrees(math.atan(E_NOMINAL / D))
        row["vergence_MA"] = 100.0 / D
        row["camera"] = camera_line(D, HW, HH, E_NOMINAL, HOUSING_H[panel])
        out["options"].append(row)

    print("checks:", json.dumps(out["checks"], indent=1))
    hdr = "opt panel              D     field H x V     px/deg(S0) c/15   arcmin/px c/15/edge  Z     lat   a_sym  M1(dwg,stop)   M2(dwg,stop)   strip  acc D  verg"
    print(hdr)
    for r in out["options"]:
        m = r["mirrors_sym_stop"]
        print(
            f"{r['option']:3} {r['panel']:17} {r['D_cm']:5.2f}  +/-{r['theta_H_deg']:5.2f} x {r['theta_V_deg']:5.2f}  "
            f"{r['px_per_deg_mean_S0']:5.1f} {r['px_per_deg_center']:5.1f}/{r['px_per_deg_at_15']:5.1f}  "
            f"{r['arcmin_per_px_center']:4.2f}/{r['arcmin_per_px_at_15']:4.2f}/{r['arcmin_per_px_at_edge']:4.2f}  "
            f"{m['Z_physical_cm']:5.2f} {m['lateral_shift_cm']:5.2f} {m['a_cm']:5.2f}  "
            f"{m['M1_mm'][0]:4.0f}x{m['M1_mm'][1]:3.0f}  {m['M2_mm'][0]:4.0f}x{m['M2_mm'][1]:4.0f}  "
            f"{r['photodiode_strip_cm']:4.2f}  {r['accommodation_D']:4.2f}  {r['vergence_deg']:4.2f}"
        )
    print("\nexact trace (symmetric, stop at +/-theta_H, E=1.6):")
    for r in out["options"]:
        x = r["exact_sym_stop"]
        print(
            f"{r['option']}: nasal clip {x['nasal_clip_deg_exact']:.1f} ({x['nasal_limited_by']}), ridge z {x['ridge_z_cm']:.2f}, "
            f"M1 {x['M1']['length_mm']:.0f} x {x['M1']['height_temporal_mm']:.0f} (temporal) / {x['M1']['height_nasal_mm']:.0f} (nasal) mm, "
            f"M2 {x['M2']['length_mm']:.0f} x {x['M2']['height_temporal_mm']:.0f}/{x['M2']['height_nasal_mm']:.0f} mm, "
            f"M2 nasal edge x,z = {x['M2_nasal_edge_xz_cm'][0]:.1f},{x['M2_nasal_edge_xz_cm'][1]:.2f}; "
            f"temporal {x['M2_temporal_edge_xz_cm'][0]:.1f},{x['M2_temporal_edge_xz_cm'][1]:.1f}; "
            f"exact symmetric a = {x['a_exact_symmetric_cm']:.2f}"
        )
    print("\ncamera line (35 deg below, 57 cm):")
    for r in out["options"]:
        c = r["camera"]
        print(
            f"{r['option']}: panel plane Z {c['Z_cm']:.1f}, line at y {c['line_height_at_panel_plane_cm']:.1f}, "
            f"housing bottom {c['housing_bottom_cm_ASSUMED_centered']:.1f}, clearance {c['clearance_below_housing_cm']:.1f} cm; "
            f"camera at z {c['camera_z_cm']:.1f}, y {c['camera_y_cm']:.1f} ({c['camera_behind_panel_plane_cm']:.1f} cm behind the panel plane)"
        )
    if "--json" in sys.argv:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "geometry.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
        print(f"\nwrote {RESULTS / 'geometry.json'}")


if __name__ == "__main__":
    main()
