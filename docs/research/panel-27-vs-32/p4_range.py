"""Where the synthetic DPI tracker loses or biases P4 over a +/-17 deg gaze grid (research artifact).

SYNTHETIC. Not a rig number, not an eye number. It reuses the P10 spike's frame model
(`../p10-dpi-spike/synth.py`) and its detector (`../p10-dpi-spike/dpi_numba.py`, Algorithm 1
of the OpenIrisDPI paper), unchanged, and adds only what a wider grid needs:

1. **The camera ROI follows the pupil.** Every frame is rendered with the pupil at the frame
   center, so the P4-in-pupil question is separated from the question of whether a fixed
   720 x 450 ROI still contains the eye. That second question is answered analytically
   (`roi_limit`).
2. **P4 is occluded by the iris.** The spike drew P4 wherever it fell. Here P4's Gaussian is
   multiplied by the pupil's (anti-aliased) interior, because P4 is imaged through the pupil.
   P1, on the corneal surface, is not occluded.

Two eye models:

- **"committed"**: the spike's `synth.geometry` exactly (FIG2 layout at neutral gaze, human
  gains from Wu et al. 2023 with an ASSUMED pupil lever arm, pupil foreshortened by cos of
  the rotation). P4 moves 3.4 px/deg relative to the pupil.
- **"anchored"**: calibrated to the one real-eye range we have. The OpenIrisDPI paper
  (Ressmeyer et al. 2026, section 2.2): "P4 was visible for eye positions up to 10 deg from
  central position in any direction before becoming obscured by the iris", with a
  configuration that "centers P4 in the pupil for neutral gaze" (section 3.1). So P4 starts
  at the pupil center and moves relative to it with a rigid-lever projection onto a camera
  35 deg below the line of sight; its gain G4 is solved so that P4's center first reaches
  the apparent pupil edge 10 deg from neutral, for the FIG2 pupil (105 x 97 px). The
  apparent pupil is foreshortened by cos(angle / k), with k fitted so that FIG2's own
  97 / 105 aspect is the neutral-gaze foreshortening at 35 deg (ASSUMED). P1 is placed per
  Wu et al. 2023 (P1 and P4 overlap only when the eye's axis points at the illuminator, 25
  deg below the line of sight in the paper), so it never masks P4 inside the grid.
  Variants put the camera at 30 and 40 deg (bracketing the direct-view options in
  `direct_view.py`) and on axis (0 deg, a hot-mirror path). Each assumes an LED placement
  exists that centers P4 at neutral gaze for that camera angle (ASSUMED).

Pupil sizes are scaled from FIG2's pupil. At the spike's ASSUMED 16.2 um per pixel, scale 1.0
is a 3.4 mm pupil; see the report for the macaque range, which is ASSUMED.

    python p4_range.py            # ~8 min on the dev machine; writes p4_range.json
    python p4_range.py --quick    # coarse grid, one frame per point
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import platform
import sys
import time
import zlib
from dataclasses import replace

import numpy as np
from scipy.special import ndtr

HERE = pathlib.Path(__file__).resolve().parent
SPIKE = HERE.parent / "p10-dpi-spike"
sys.path.insert(0, str(SPIKE))

import dpi_numba as dn  # noqa: E402
import synth  # noqa: E402

RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-panel-27-vs-32"

CAM_DEG = 35.0  # paper: cameras 35 deg below the line of sight
LED_DEG = 25.0  # paper: LED at 25 deg
PAPER_RANGE_DEG = 10.0  # paper: P4 visible up to 10 deg from center in any direction
FIG2_A, FIG2_B = 105.0, 97.0  # spike: FIG2 right-eye pupil semi-axes, px
# Foreshortening exponent: cos(35 / K) = 97 / 105 (FIG2 aspect, ASSUMED neutral gaze).
K_FORE = CAM_DEG / math.degrees(math.acos(FIG2_B / FIG2_A))
DEG = 180.0 / math.pi
# P1 - P4 gain (px/deg) from the spike's model (Wu 2023's 2.4 um/arcmin at 16.2 um/px).
G14 = synth.DIFF_UM_PER_DEG / synth.UM_PER_PX


def apparent_axes(r_px: float, az: float, el: float, cam_deg: float) -> tuple[float, float]:
    """Axis-aligned approximation of the apparent pupil ellipse (ASSUMED model)."""
    return (r_px * math.cos(math.radians(az / K_FORE)), r_px * math.cos(math.radians((cam_deg + el) / K_FORE)))


def p4_rel(g4: float, az: float, el: float, cam_deg: float) -> tuple[float, float]:
    """P4 relative to the pupil center, image px (y down). Rigid lever projected onto a
    camera cam_deg below the line of sight; linearizes to (g4 az, -g4 cos(cam) el)."""
    L = g4 * DEG  # px per radian
    x = L * math.sin(math.radians(az)) * math.cos(math.radians(el))
    y = -L * (math.sin(math.radians(cam_deg + el)) - math.sin(math.radians(cam_deg)))
    return x, y


def occlusion_angle(g4: float, r_px: float, direction_deg: float, cam_deg: float) -> float:
    """Eccentricity along a gaze direction at which P4's center reaches the apparent pupil
    edge (bisection)."""
    ca, sa = math.cos(math.radians(direction_deg)), math.sin(math.radians(direction_deg))

    def outside(e: float) -> bool:
        az, el = e * ca, e * sa
        a, b = apparent_axes(r_px, az, el, cam_deg)
        x, y = p4_rel(g4, az, el, cam_deg)
        return (x / a) ** 2 + (y / b) ** 2 >= 1.0

    lo, hi = 0.0, 60.0
    if not outside(hi):
        return hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if outside(mid) else (mid, hi)
    return 0.5 * (lo + hi)


def solve_g4() -> float:
    """G4 such that the minimum occlusion angle over directions is the paper's 10 deg."""
    dirs = np.arange(0, 360, 5.0)
    lo, hi = 1.0, 40.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        m = min(occlusion_angle(mid, FIG2_A, d, CAM_DEG) for d in dirs)
        lo, hi = (mid, hi) if m > PAPER_RANGE_DEG else (lo, mid)
    return 0.5 * (lo + hi)


def truth_committed(scene: synth.Scene, az: float, el: float, jx: float, jy: float) -> synth.Truth:
    t = synth.geometry(scene, az, el)
    dx = scene.width / 2.0 - t.pupil_x + jx
    dy = scene.height / 2.0 - t.pupil_y + jy
    return replace(t, pupil_x=t.pupil_x + dx, pupil_y=t.pupil_y + dy, p1_x=t.p1_x + dx, p1_y=t.p1_y + dy,
                   p4_x=t.p4_x + dx, p4_y=t.p4_y + dy)


def truth_anchored(scene: synth.Scene, g4: float, r_px: float, cam_deg: float, az: float, el: float,
                   jx: float, jy: float) -> synth.Truth:
    cx, cy = scene.width / 2.0 + jx, scene.height / 2.0 + jy
    a, b = apparent_axes(r_px, az, el, cam_deg)
    x4, y4 = p4_rel(g4, az, el, cam_deg)
    # P1 - P4 is zero when the eye points at the illuminator (Wu 2023), LED_DEG below the
    # line of sight in the paper; projected like P4 with the P1 - P4 gain.
    # P1 moves less than P4 toward the gaze, so P1 - P4 moves against it.
    x14 = -G14 * DEG * (math.sin(math.radians(az)) * math.cos(math.radians(el)))
    y14 = G14 * DEG * (math.sin(math.radians(cam_deg + el)) - math.sin(math.radians(cam_deg - LED_DEG)))
    return synth.Truth(pupil_x=cx, pupil_y=cy, pupil_a=a, pupil_b=b, p1_x=cx + x4 + x14, p1_y=cy + y4 + y14,
                       p4_x=cx + x4, p4_y=cy + y4)


class OccludingRenderer(synth.Renderer):
    """The spike's renderer, with P4 seen only through the pupil."""

    def reflections(self, img: np.ndarray, t: synth.Truth) -> None:
        s = self.scene
        a1 = s.p4_amp * s.p1_over_p4
        synth._pixel_gaussian(img, t.p1_x, t.p1_y, s.p1_sigma, a1)
        p4 = np.zeros_like(img)
        synth._pixel_gaussian(p4, t.p4_x, t.p4_y, s.p4_sigma, s.p4_amp)
        dx = self._xx - t.pupil_x
        dy = self._yy - t.pupil_y
        rho = np.sqrt((dx / t.pupil_a) ** 2 + (dy / t.pupil_b) ** 2)
        inside = ndtr(-((rho - 1.0) * min(t.pupil_a, t.pupil_b)) / s.pupil_edge_sd)
        img += p4 * inside


def classify(errs: list[np.ndarray], n: int) -> dict:
    found = len(errs)
    rec: dict = {"frames": n, "found": found}
    if found:
        e = np.array(errs)
        rec["p4_err_mean"] = [float(e[:, 0].mean()), float(e[:, 1].mean())]
        rec["p4_err_max_abs"] = float(np.abs(e[:, :2]).max())
        rec["dpi_err_mean"] = [float(np.nanmean(e[:, 2])) if np.isfinite(e[:, 2]).any() else None,
                               float(np.nanmean(e[:, 3])) if np.isfinite(e[:, 3]).any() else None]
    if found < math.ceil(2 * n / 3):
        cls = "lost"
    else:
        m = max(abs(rec["p4_err_mean"][0]), abs(rec["p4_err_mean"][1]))
        cls = "wrong" if rec["p4_err_max_abs"] > 2.0 else ("biased" if m > 0.1 else "ok")
    rec["class"] = cls
    return rec


def run_grid(label: str, scene: synth.Scene, make_truth, grid: np.ndarray, per: int, params: dict) -> dict:
    seed = zlib.crc32(label.encode())
    rend = OccludingRenderer(scene, seed=seed)
    rng = np.random.default_rng(seed + 1)
    trackers = {k: dn.Tracker(scene.height, scene.width, p) for k, p in params.items()}
    cells: dict = {k: {} for k in params}
    for az in grid:
        for el in grid:
            t = make_truth(float(az), float(el), rng.uniform(0, 1), rng.uniform(0, 1))
            bg = rend.background(t)
            rend.reflections(bg, t)
            errs = {k: [] for k in params}
            n_cr = {k: 0 for k in params}
            for _ in range(per):
                img = rend.finish(bg, rng)
                for k, tr in trackers.items():
                    out = tr(img)
                    f = int(out[dn.O_FLAGS])
                    if f & dn.F_CR:
                        n_cr[k] += 1
                    # P4 is judged on its own: the P4 search runs whether or not a CR was
                    # found (it only masks around a CR when there is one).
                    if f & dn.F_P4:
                        e4 = (out[dn.O_P4_X] - t.p4_x, out[dn.O_P4_Y] - t.p4_y)
                        if f & dn.F_CR:
                            ed = (out[dn.O_CR_X] - out[dn.O_P4_X] - (t.p1_x - t.p4_x),
                                  out[dn.O_CR_Y] - out[dn.O_P4_Y] - (t.p1_y - t.p4_y))
                        else:
                            ed = (math.nan, math.nan)
                        errs[k].append(np.array([e4[0], e4[1], ed[0], ed[1]]))
            for k in params:
                rec = classify(errs[k], per)
                rec["cr_found"] = n_cr[k]
                # distance of true P4 inside the apparent pupil edge, px (negative = outside)
                rho = math.hypot((t.p4_x - t.pupil_x) / t.pupil_a, (t.p4_y - t.pupil_y) / t.pupil_b)
                rec["p4_rho"] = rho
                rec["p4_edge_px"] = (1.0 - rho) * min(t.pupil_a, t.pupil_b)
                cells[k][f"{az:+.0f},{el:+.0f}"] = rec
    return cells


def class_map(cells: dict, grid: np.ndarray) -> list[str]:
    """The grid's classes as text rows, elevation high to low, azimuth left to right."""
    sym = {"ok": ".", "biased": "b", "wrong": "W", "lost": "x"}
    return ["".join(sym[cells[f"{az:+.0f},{el:+.0f}"]["class"]] for az in grid) for el in grid[::-1]]


def summarize(cells: dict, grid: np.ndarray) -> dict:
    """Per radius: fraction of grid points at that eccentricity (rounded) in each class, and
    the largest eccentricity inside which every point is 'ok' / not 'lost'."""
    out = {}
    pts = []
    for key, rec in cells.items():
        az, el = (float(v) for v in key.split(","))
        pts.append((math.hypot(az, el), az, el, rec["class"]))
    pts.sort()

    def radius_all(pred) -> float:
        bad = [e for e, _, _, c in pts if not pred(c)]
        return min(bad) if bad else float("inf")

    out["first_not_ok_deg"] = radius_all(lambda c: c == "ok")
    out["first_lost_or_wrong_deg"] = radius_all(lambda c: c in ("ok", "biased"))
    for axis_name, sel in (("right", lambda a, e: e == 0 and a > 0), ("left", lambda a, e: e == 0 and a < 0),
                           ("up", lambda a, e: a == 0 and e > 0), ("down", lambda a, e: a == 0 and e < 0)):
        on = sorted((abs(a) + abs(e), c) for _, a, e, c in pts if sel(a, e))
        firsts = [r for r, c in on if c != "ok"]
        out[f"{axis_name}_first_not_ok"] = firsts[0] if firsts else None
        lost = [r for r, c in on if c in ("lost", "wrong")]
        out[f"{axis_name}_first_lost"] = lost[0] if lost else None
    ring = {}
    for R in (10, 12, 15, 17):
        sel = [c for e, _, _, c in pts if abs(e - R) <= 0.5]
        if sel:
            ring[R] = {c: sel.count(c) / len(sel) for c in ("ok", "biased", "wrong", "lost")}
    out["ring"] = ring
    # The PI's requirement is an eccentricity (a disc), not a box.
    for R in (10, 15, 17):
        disc = [c for e, _, _, c in pts if e <= R + 1e-9]
        out[f"disc{R}_fraction"] = {c: disc.count(c) / len(disc) for c in ("ok", "biased", "wrong", "lost")}
    # Largest |mean P4 error| among found-but-not-ok points inside 15 deg, px.
    worst = [max(abs(rec["p4_err_mean"][0]), abs(rec["p4_err_mean"][1]))
             for key, rec in cells.items() if "p4_err_mean" in rec and rec["class"] in ("biased", "wrong")
             and math.hypot(*(float(v) for v in key.split(","))) <= 15 + 1e-9]
    out["disc15_worst_mean_p4_err_px"] = max(worst) if worst else 0.0
    return out


def coverage(g4: float, r_px: float, centers: list[tuple[float, float]], radius: float, margin_px: float,
             cam_deg: float = CAM_DEG) -> float:
    """Fraction of a gaze disc in which P4 sits at least margin_px inside the apparent pupil
    for at least one illuminator. Illuminator i is modeled as moving the gaze at which P4
    is centered to centers[i] (the paper: illuminator placement 'centers P4 in the pupil for
    neutral gaze'); how far each LED must move to do that is not modeled."""
    n_in = n_all = 0
    for az in np.arange(-radius, radius + 1e-9, 0.5):
        for el in np.arange(-radius, radius + 1e-9, 0.5):
            if math.hypot(az, el) > radius + 1e-9:
                continue
            n_all += 1
            a, b = apparent_axes(r_px, az, el, cam_deg)
            for caz, cel in centers:
                x, y = p4_rel(g4, az, el, cam_deg)
                x0, y0 = p4_rel(g4, caz, cel, cam_deg)
                x, y = x - x0, y - y0
                rho = math.hypot(x / a, y / b)
                if (1.0 - rho) * min(a, b) >= margin_px:
                    n_in += 1
                    break
    return n_in / n_all


def roi_limit(scale: float, cam_deg: float = CAM_DEG) -> dict:
    """Fixed 720 x 450 ROI centered at neutral gaze: the gaze at which the pupil's edge meets
    the ROI border, using the spike's pupil motion (10.3 mm lever, ASSUMED) at 16.2 um/px."""
    g = synth.PUPIL_UM_PER_DEG / synth.UM_PER_PX
    r = FIG2_A * scale
    res = {}
    for name, (dx, dy) in {"right": (1, 0), "up": (0, 1), "down": (0, -1)}.items():
        e = 0.0
        while e < 40:
            az, el = e * dx, e * dy
            a, b = apparent_axes(r, az, el, cam_deg)
            cx = 360 + g * az
            cy = 225 - g * math.cos(math.radians(cam_deg)) * el
            if cx + a > 720 or cy - b < 0 or cy + b > 450:
                break
            e += 0.1
        res[name] = round(e, 1)
    return res


def main() -> None:
    global K_FORE
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    step = 2.0 if args.quick else 1.0
    per = 1 if args.quick else 3
    grid = np.arange(-17.0, 17.0 + 1e-9, step)

    g4 = solve_g4()
    occl = {
        "g4_px_per_deg": g4,
        "g4_um_per_deg_at_16.2um": g4 * synth.UM_PER_PX,
        "committed_p4_rel_px_per_deg": (synth.P4_UM_PER_DEG - synth.PUPIL_UM_PER_DEG) / synth.UM_PER_PX,
        "k_foreshortening": K_FORE,
    }
    # Range against camera angle, analytic: FIG2-derived foreshortening, and plain cosine
    # (k = 1, re-anchored to 10 deg at 35 deg) as the pessimistic bound.
    vs_cam = {}
    for kname, kval in (("fig2_k", K_FORE), ("cosine_k1", 1.0)):
        k_save = K_FORE
        K_FORE = kval
        g = solve_g4()
        for s in (1.0, 1.5):
            vs_cam[f"{kname}_scale{s}"] = {
                f"{cam:.0f}": round(min(occlusion_angle(g, FIG2_A * s, a_, cam) for a_ in range(0, 360, 5)), 2)
                for cam in (0.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0)}
        K_FORE = k_save
    # Analytic occlusion angles for the anchored model, per pupil scale and camera angle.
    scales = [0.75, 1.0, 1.25, 1.5, 1.75]
    analytic = {}
    for cam in (CAM_DEG, 0.0):
        for s in scales:
            r = FIG2_A * s
            analytic[f"cam{cam:.0f}_scale{s}"] = {
                d: round(occlusion_angle(g4, r, ang, cam), 2)
                for d, ang in (("right", 0), ("up", 90), ("left", 180), ("down", 270), ("up-right", 45),
                               ("down-right", 315))
            } | {"min_over_directions": round(min(occlusion_angle(g4, r, a_, cam) for a_ in range(0, 360, 5)), 2)}

    layouts = {
        "one (paper)": [(0.0, 0.0)],
        "two, +/-7 az": [(-7.0, 0.0), (7.0, 0.0)],
        "four, +/-6.5 diag": [(-6.5, -6.5), (-6.5, 6.5), (6.5, -6.5), (6.5, 6.5)],
        "seven, hex r=9": [(0.0, 0.0)] + [(9 * math.cos(math.radians(k * 60)), 9 * math.sin(math.radians(k * 60)))
                                           for k in range(6)],
    }
    cover = {}
    for s in (1.0, 1.25, 1.5):
        for lname, cs in layouts.items():
            # margin 9 px: R_erode 8 plus a pixel; below ~9 px R_P4 = 6 is unbiased (spike 7.4)
            cover[f"scale{s} {lname}"] = {f"disc{R}": round(coverage(g4, FIG2_A * s, cs, R, 9.0), 3) for R in (15, 17)}

    base = synth.Scene()
    params = {"RP4_15": dn.default_params(r_pup=260), "RP4_6": dn.default_params(r_pup=260, r_p4=6)}
    runs = {}
    t0 = time.time()
    # committed model, FIG2 pupil
    runs["committed_scale1.0"] = run_grid("committed_scale1.0", base,
                                          lambda az, el, jx, jy: truth_committed(base, az, el, jx, jy), grid, per,
                                          params)
    for s in scales:
        sc = replace(base, pupil_a_px=FIG2_A * s, pupil_b_px=FIG2_B * s, iris_radius_px=max(330.0, 330.0 * s))
        r = FIG2_A * s
        runs[f"anchored_cam35_scale{s}"] = run_grid(
            f"anchored_cam35_scale{s}", sc,
            lambda az, el, jx, jy, sc=sc, r=r: truth_anchored(sc, g4, r, CAM_DEG, az, el, jx, jy), grid, per, params)
    # Other camera angles: 0 deg is a hot-mirror path; 30 and 40 bracket the direct-view
    # options (direct_view.py puts the lowest P4-centering camera at 27-37 deg).
    for cam in (0.0, 30.0, 40.0):
        for s in (1.0, 1.5):
            b0 = FIG2_A * s * math.cos(math.radians(cam / K_FORE))
            sc = replace(base, pupil_a_px=FIG2_A * s, pupil_b_px=b0, iris_radius_px=max(330.0, 330.0 * s))
            r = FIG2_A * s
            runs[f"anchored_cam{cam:.0f}_scale{s}"] = run_grid(
                f"anchored_cam{cam:.0f}_scale{s}", sc,
                lambda az, el, jx, jy, sc=sc, r=r, cam=cam: truth_anchored(sc, g4, r, cam, az, el, jx, jy), grid,
                per, params)
    elapsed = time.time() - t0

    summary = {name: {k: summarize(v, grid) for k, v in cells.items()} for name, cells in runs.items()}
    roi = {f"scale{s}": roi_limit(s) for s in scales}
    out = {
        "date": time.strftime("%Y-%m-%d"),
        "note": "SYNTHETIC frames; not rig or eye numbers. See p4_range.py docstring.",
        "machine": platform.platform(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "numba": __import__("numba").__version__, "scipy": __import__("scipy").__version__},
        "grid_deg": [float(grid[0]), float(grid[-1]), step],
        "frames_per_point": per,
        "anchoring": occl,
        "analytic_occlusion_deg": analytic,
        "fixed_roi_720x450_limit_deg": roi,
        "illuminator_coverage": cover,
        "range_vs_camera_angle_deg": vs_cam,
        "summary": summary,
        "class_maps": {name: {k: class_map(v, grid) for k, v in cells.items()} for name, cells in runs.items()},
        "class_map_legend": "rows: elevation +17 (top) to -17 deg; columns: azimuth -17 to +17 deg; "
                            "'.' ok, 'b' biased > 0.1 px, 'W' wrong (error > 2 px), 'x' lost",
        "elapsed_s": elapsed,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    name = "p4_range_quick.json" if args.quick else "p4_range.json"
    (RESULTS / name).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"anchoring": occl, "analytic": analytic, "roi": roi, "coverage": cover, "vs_cam": vs_cam, "summary": summary,
                      "elapsed_s": elapsed}, indent=1))


if __name__ == "__main__":
    main()
