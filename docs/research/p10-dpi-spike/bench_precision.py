"""Precision of the clean-room detector on synthetic frames with known ground truth.

Every error is estimate minus truth, in sensor pixels, x = azimuth axis, y = elevation.
The DPI vector is P1 - P4 (S5's CR1 - CR4). "noise SD" is the pooled within-position
standard deviation over noise realizations at a fixed true position (the synthetic
analogue of the paper's white-noise RMS); "bias spread" is the SD across positions of the
per-position mean error (sub-pixel systematic error, e.g. pixel locking). Positions vary
the sub-pixel phase of P1 and P4 independently.

Uses the numba core; check_agreement.py shows the C++ core returns identical numbers.
Writes precision.json to docs/measurements/dev-machine/2026-09-27-p10-dpi-spike/.

    python bench_precision.py            # full run (~35k frames)
    python bench_precision.py --quick    # a tenth of the frames
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import pathlib
import platform
import time
import zlib

import numpy as np

import dpi_numba as dn
import synth

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-p10-dpi-spike"


def _errors(out: np.ndarray, t: synth.Truth) -> np.ndarray | None:
    f = int(out[dn.O_FLAGS])
    if not (f & dn.F_CR and f & dn.F_P4):
        return None
    p1 = (out[dn.O_CR_X] - t.p1_x, out[dn.O_CR_Y] - t.p1_y)
    p4 = (out[dn.O_P4_X] - t.p4_x, out[dn.O_P4_Y] - t.p4_y)
    return np.array([p1[0], p1[1], p4[0], p4[1], p1[0] - p4[0], p1[1] - p4[1]])


def run_condition(
    scene: synth.Scene,
    prm: np.ndarray,
    positions: list[synth.Truth],
    per_position: int,
    seed: int,
) -> dict:
    """Render `per_position` noisy frames at each true position and summarize errors."""
    rend = synth.Renderer(scene, seed=seed)
    rng = np.random.default_rng(seed + 1)
    tr = dn.Tracker(scene.height, scene.width, prm)
    per_pos_errs = []
    n_total = 0
    n_found = 0
    for t in positions:
        bg = rend.background(t)
        rend.reflections(bg, t)
        errs = []
        for _ in range(per_position):
            img = rend.finish(bg, rng)
            e = _errors(tr(img), t)
            n_total += 1
            if e is not None:
                n_found += 1
                errs.append(e)
        if errs:
            per_pos_errs.append(np.array(errs))
    return summarize(per_pos_errs, n_total, n_found)


def summarize(per_pos_errs: list[np.ndarray], n_total: int, n_found: int) -> dict:
    names = ["p1_x", "p1_y", "p4_x", "p4_y", "dpi_x", "dpi_y"]
    res: dict = {"frames": n_total, "detected": n_found, "detection_rate": n_found / max(n_total, 1)}
    if not per_pos_errs:
        return res
    allerr = np.concatenate(per_pos_errs)
    usable = [e for e in per_pos_errs if len(e) >= 2]
    if usable:
        # pooled within-position variance
        ss = sum(((e - e.mean(0)) ** 2).sum(0) for e in usable)
        dof = sum(len(e) - 1 for e in usable)
        noise_sd = np.sqrt(ss / dof)
        means = np.array([e.mean(0) for e in usable])
        bias_spread = means.std(0) if len(usable) > 1 else np.zeros(6)
    else:
        noise_sd = np.full(6, np.nan)
        bias_spread = np.full(6, np.nan)
    for i, nm in enumerate(names):
        a = allerr[:, i]
        res[nm] = {
            "noise_sd": float(noise_sd[i]),
            "bias_spread": float(bias_spread[i]),
            "mean": float(a.mean()),
            "rms": float(np.sqrt((a**2).mean())),
            "p99_abs": float(np.percentile(np.abs(a), 99)),
            "max_abs": float(np.abs(a).max()),
            "gross_gt_1px": int((np.abs(a) > 1.0).sum()),
        }
    for axis in ("x", "y"):
        sd = res[f"dpi_{axis}"]["noise_sd"]
        rms = res[f"dpi_{axis}"]["rms"]
        res[f"dpi_{axis}"]["noise_arcmin_human"] = sd * synth.arcmin_per_px(axis, "human")
        res[f"dpi_{axis}"]["noise_arcmin_macaque"] = sd * synth.arcmin_per_px(axis, "macaque")
        res[f"dpi_{axis}"]["rms_arcmin_human"] = rms * synth.arcmin_per_px(axis, "human")
    return res


def jitter_positions(scene: synth.Scene, n: int, rng: np.random.Generator, az=0.0, el=0.0, **kw) -> list[synth.Truth]:
    """n positions near (az, el): +-0.1 deg of rotation and a [0, 1) px head shift, so the
    sub-pixel phases of P1 and P4 vary independently."""
    out = []
    for _ in range(n):
        out.append(
            synth.geometry(
                scene,
                az + rng.uniform(-0.1, 0.1),
                el + rng.uniform(-0.1, 0.1),
                head_dx_px=rng.uniform(0, 1) + kw.get("head_dx_px", 0.0),
                head_dy_px=rng.uniform(0, 1) + kw.get("head_dy_px", 0.0),
                **{k: v for k, v in kw.items() if k not in ("head_dx_px", "head_dy_px")},
            )
        )
    return out


def snr_of(scene: synth.Scene) -> float:
    r = synth.Renderer.__new__(synth.Renderer)
    r.scene = scene
    return scene.p4_amp / float(r.noise_sd(scene.pupil_level))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    k = 0.1 if args.quick else 1.0
    npos, nper = 20, max(int(50 * k), 5)
    base = synth.Scene()
    prm = dn.default_params()
    rng = np.random.default_rng(2026)
    out: dict = {
        "date": time.strftime("%Y-%m-%d"),
        "machine": platform.platform(),
        "note": "DEV MACHINE, SYNTHETIC FRAMES. Not a rig measurement, not real eyes.",
        "scene_base": dataclasses.asdict(base),
        "params_base": prm.tolist(),
        "optics": {
            "um_per_px": synth.UM_PER_PX,
            "dpi_um_per_arcmin_human": synth.DPI_UM_PER_ARCMIN_HUMAN,
            "macaque_d_ratio_ASSUMED": synth.MACAQUE_D_RATIO,
            "vertical_foreshortening": synth.VERTICAL_FORESHORTENING,
            "arcmin_per_px": {
                ax + "_" + sp: synth.arcmin_per_px(ax, sp) for ax in ("x", "y") for sp in ("human", "macaque")
            },
        },
        "experiments": {},
    }
    ex = out["experiments"]
    t0 = time.time()

    def cond(name: str, scene: synth.Scene, prm_: np.ndarray, positions, per, extra: dict | None = None):
        r = run_condition(scene, prm_, positions, per, seed=zlib.crc32(name.encode()))  # stable across runs
        r["p4_snr"] = snr_of(scene)
        if extra:
            r.update(extra)
        ex.setdefault(name.split(":")[0], {})[name.split(":")[1]] = r
        d = r.get("dpi_x", {})
        print(f"{name:32s} det={r['detection_rate']:.3f} snr={r['p4_snr']:6.1f} "
              f"dpi_sd=({d.get('noise_sd', float('nan')):.4f},{r.get('dpi_y', {}).get('noise_sd', float('nan')):.4f}) px "
              f"bias_spread=({d.get('bias_spread', float('nan')):.4f}) [{time.time() - t0:.0f}s]", flush=True)

    # E1: noise (SNR) sweep at the base P4 amplitude.
    for s in (0.5, 1.0, 2.0, 4.0, 8.0):
        sc = dataclasses.replace(base, noise_scale=s)
        cond(f"snr_noise:scale_{s}", sc, prm, jitter_positions(sc, npos, rng), nper, {"noise_scale": s})
    # E2: P4 amplitude sweep (P1 scales with it, ratio 80).
    for a in (35.0, 45.0, 60.0, 90.0, 130.0):
        sc = dataclasses.replace(base, p4_amp=a)
        cond(f"p4_amplitude:amp_{a:g}", sc, prm, jitter_positions(sc, npos, rng), nper, {"p4_amp": a})
    # E3: P4 size sweep.
    for sg in (1.5, 2.0, 2.5, 3.5):
        sc = dataclasses.replace(base, p4_sigma=sg)
        cond(f"p4_sigma:sigma_{sg}", sc, prm, jitter_positions(sc, npos, rng), nper, {"p4_sigma": sg})
    # E4: eye rotations, 5 x 5 grid over +-8 deg.
    for az in (-8, -4, 0, 4, 8):
        for el in (-8, -4, 0, 4, 8):
            cond(f"rotation:az{az}_el{el}", base, prm, jitter_positions(base, max(npos // 4, 3), rng, az, el),
                 nper, {"az": az, "el": el})
    # E5: head translations (move P1, P4, pupil together), +-30 px = +-0.49 mm.
    for dx in (-30, 0, 30):
        for dy in (-30, 0, 30):
            cond(f"head_translation:dx{dx}_dy{dy}", base, prm,
                 jitter_positions(base, max(npos // 4, 3), rng, 2.0, -2.0, head_dx_px=dx, head_dy_px=dy),
                 nper, {"dx_px": dx, "dy_px": dy})
    # E6: P4 near the pupil edge. P4 placed d px inside the edge, up and to the right.
    ang = math.radians(-40.0)
    for d in (3, 6, 9, 12, 15, 20, 30):
        # a point on the pupil ellipse along `ang`, then d px inward along the radius
        a_, b_ = base.pupil_a_px, base.pupil_b_px
        rr = 1.0 / math.sqrt((math.cos(ang) / a_) ** 2 + (math.sin(ang) / b_) ** 2)
        rel = ((rr - d) * math.cos(ang), (rr - d) * math.sin(ang))
        cond(f"p4_near_pupil_edge:d{d}", base, prm, jitter_positions(base, max(npos // 2, 3), rng, p4_rel_pupil=rel),
             nper, {"distance_to_edge_px": d})
    # E7: P4 near P1 (the CR mask has radius Rcr = 29 px).
    for sep in (20, 28, 32, 36, 45, 60):
        cond(f"p4_near_p1:sep{sep}", base, prm,
             jitter_positions(base, max(npos // 2, 3), rng, p4_rel_pupil=(-10.0, 51.0 - sep)),
             nper, {"p1_p4_separation_px": sep})
    # E9: P2 beside P1 (paper: shifts the CR centroid, "a deterministic function of viewing
    # angle"). Bias per gaze position is what matters, so report means.
    sc = dataclasses.replace(base, p2_rel=0.01)
    for az, el in ((-6, 0), (0, 0), (6, 0), (0, -6), (0, 6)):
        cond(f"p2_present:az{az}_el{el}", sc, prm, jitter_positions(sc, max(npos // 4, 3), rng, az, el), nper,
             {"az": az, "el": el, "p2_rel": 0.01})
    # E10: choices the paper leaves open, and alternatives to published ones.
    for label, p in (
        ("published_p4_threshold_Tpup", prm),
        ("no_blur", dn.default_params(blur=0)),
        ("p4_threshold_20", dn.default_params(p4_thr=20)),
        ("p4_threshold_14_bg_plus_5sd", dn.default_params(p4_thr=14)),
    ):
        for s in (1.0, 4.0):
            sc = dataclasses.replace(base, noise_scale=s)
            cond(f"variants:{label}_noise{s}", sc, p, jitter_positions(sc, npos, rng), nper,
                 {"variant": label, "noise_scale": s})

    # E11: mitigations for P4 near the pupil edge. The published centroid (line 25) takes
    # every ROI pixel above Tpup, and iris pixels are above Tpup. Compare the published
    # setting (RP4 = 15, Fig. 2), a smaller operator setting (RP4 = 6, still published
    # algorithm), and an ROI masked to the filled hull (NOT the published algorithm).
    for label, p in (
        ("published_RP4_15", prm),
        ("published_RP4_6", dn.default_params(r_p4=6)),
        ("masked_roi_RP4_15", dn.default_params(p4_roi_masked=1)),
    ):
        for d in (6, 9, 12, 15, 20, 30):
            a_, b_ = base.pupil_a_px, base.pupil_b_px
            rr = 1.0 / math.sqrt((math.cos(ang) / a_) ** 2 + (math.sin(ang) / b_) ** 2)
            rel = ((rr - d) * math.cos(ang), (rr - d) * math.sin(ang))
            cond(f"edge_mitigation:{label}_d{d}", base, p,
                 jitter_positions(base, max(npos // 2, 3), np.random.default_rng(d), p4_rel_pupil=rel),
                 nper, {"variant": label, "distance_to_edge_px": d})

    # E8: blinks. Detection counts only; there is no true P4 when the lid covers it.
    rend = synth.Renderer(base, seed=77)
    brng = np.random.default_rng(78)
    tr = dn.Tracker(base.height, base.width, prm)
    nb = max(int(300 * k), 20)
    blinks = {}
    for closure in (1.0, 0.5, 0.3):
        flags = []
        p4err = []
        for _ in range(nb):
            t = synth.geometry(base, brng.uniform(-3, 3), brng.uniform(-3, 3))
            o = tr(rend.blink(brng, t=t, closure=closure))
            f = int(o[dn.O_FLAGS])
            flags.append(f)
            if f & dn.F_P4:
                p4err.append(math.hypot(o[dn.O_P4_X] - t.p4_x, o[dn.O_P4_Y] - t.p4_y))
        flags = np.array(flags)
        # Is the true P4 under the lid? margin at P4's x: y_lid - 0.0006 (x - px)^2
        blinks[f"closure_{closure}"] = {
            "frames": nb,
            "pupil_reported": float(np.mean(flags & dn.F_PUPIL > 0)),
            "cr_reported": float(np.mean(flags & dn.F_CR > 0)),
            "p4_reported": float(np.mean(flags & dn.F_P4 > 0)),
            "p4_error_px_median_when_reported": float(np.median(p4err)) if p4err else None,
            "p4_reported_more_than_2px_from_true_p4": float(np.mean(np.array(p4err) > 2.0)) if p4err else 0.0,
        }
        print("blink", closure, blinks[f"closure_{closure}"], flush=True)
    ex["blink"] = blinks
    out["elapsed_s"] = time.time() - t0
    RESULTS.mkdir(parents=True, exist_ok=True)
    name = "precision_quick.json" if args.quick else "precision.json"
    (RESULTS / name).write_text(json.dumps(out, indent=1))
    print("wrote", RESULTS / name)


if __name__ == "__main__":
    main()
