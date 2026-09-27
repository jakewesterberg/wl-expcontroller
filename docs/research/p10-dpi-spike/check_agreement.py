"""Check the two cores against each other and against a literal, slow reference.

The reference follows Algorithm 1 line by line with numpy/scipy: a full Laplacian of the
masked binary image, scipy's ConvexHull (qhull) over every edge pixel, numpy's eig for the
ellipse. It shares no code with the cores. It confirms that the fast paths in the cores
(per-row hull extremes, the geometric erosion) are exact, and that numba and C++ agree.

Writes docs/measurements/dev-machine/2026-09-27-p10-dpi-spike/agreement.json.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.ndimage import convolve
from scipy.spatial import ConvexHull

import dpi_cpp
import dpi_numba as dn
import synth

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-p10-dpi-spike"


def ref_blur(img: np.ndarray) -> np.ndarray:
    k = np.array([18, 63, 94, 63, 18], np.int64)
    p = np.pad(img.astype(np.int64), 2, mode="edge")
    h, w = img.shape
    t = sum(k[i] * p[2 : 2 + h, i : i + w] for i in range(5))
    tp = np.pad(t, ((2, 2), (0, 0)), mode="edge")
    v = sum(k[i] * tp[i : i + h, :] for i in range(5))
    return ((v + 32768) >> 16).astype(np.uint8)


def ref_tcom(blur, cx, cy, r, t):
    h, w = blur.shape
    ys = slice(max(cy - r, 0), min(cy + r, h - 1) + 1)
    xs = slice(max(cx - r, 0), min(cx + r, w - 1) + 1)
    sub = blur[ys, xs].astype(np.int64) - t
    sub[sub < 0] = 0
    if sub.sum() <= 0:
        return None
    yy, xx = np.mgrid[ys, xs]
    return (sub * xx).sum() / sub.sum(), (sub * yy).sum() / sub.sum()


def ref_ellipse(pts: np.ndarray):
    x, y = pts[:, 0].astype(float), pts[:, 1].astype(float)
    mx, my = x.mean(), y.mean()
    s = math.sqrt(((x - mx) ** 2 + (y - my) ** 2).sum() / (2 * len(x))) + 1e-12
    x, y = (x - mx) / s, (y - my) / s
    D1 = np.stack([x * x, x * y, y * y], 1)
    D2 = np.stack([x, y, np.ones_like(x)], 1)
    S1, S2, S3 = D1.T @ D1, D1.T @ D2, D2.T @ D2
    T = -np.linalg.solve(S3, S2.T)
    M = S1 + S2 @ T
    M = np.array([M[2] / 2, -M[1], M[0] / 2])
    _, vec = np.linalg.eig(M)
    vec = vec.real
    ok = 4 * vec[0] * vec[2] - vec[1] ** 2 > 0
    a1 = vec[:, np.argmax(ok)]
    a2 = T @ a1
    A, B, C = a1
    D, E, F = a2
    den = B * B - 4 * A * C
    x0 = (2 * C * D - B * E) / den
    y0 = (2 * A * E - B * D) / den
    return x0 * s + mx, y0 * s + my


def reference(img: np.ndarray, prm: np.ndarray, laplacian=None) -> dict:
    t_pup, t_cr, r_pup, r_cr, r_erode, r_p4, min_pup = (int(v) for v in prm[:7])
    h, w = img.shape
    blur = ref_blur(img)
    thr = blur < t_pup  # line 8
    if thr.sum() < min_pup:
        return {"flags": 0}
    yy, xx = np.nonzero(thr)
    cx, cy = xx.mean(), yy.mean()  # line 9
    Y, Xg = np.mgrid[0:h, 0:w]
    mask = (Xg - cx) ** 2 + (Y - cy) ** 2 <= r_pup**2  # line 10
    B = (thr & mask).astype(np.int64)
    k4 = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]]) if laplacian is None else laplacian
    lap = convolve(B, k4, mode="constant", cval=0)  # line 11
    ey, ex = np.nonzero(lap > 0)  # line 12
    pts = np.stack([ex, ey], 1)
    hull = pts[ConvexHull(pts).vertices]  # line 13
    res = {"flags": 1, "hull": sorted(map(tuple, hull.tolist())), "pupil": ref_ellipse(hull)}
    icr = (blur > t_cr) & mask  # line 15
    cr = None
    if icr.any():
        cyy, cxx = np.nonzero(icr)
        cr = ref_tcom(blur, int(round(cxx.mean())), int(round(cyy.mean())), r_cr, t_cr)  # 16-18
    res["cr"] = cr
    # Lines 19-23: pixel centers at least r_erode inside every hull edge, outside CR disc.
    hv = hull.astype(float)
    area2 = sum(hv[i, 0] * hv[(i + 1) % len(hv), 1] - hv[(i + 1) % len(hv), 0] * hv[i, 1] for i in range(len(hv)))
    sgn = 1.0 if area2 > 0 else -1.0
    inside = np.ones((h, w), bool)
    for i in range(len(hv)):
        e = hv[(i + 1) % len(hv)] - hv[i]
        n = np.array([-e[1], e[0]]) / np.hypot(*e) * sgn
        inside &= n[0] * (Xg - hv[i, 0]) + n[1] * (Y - hv[i, 1]) >= r_erode
    if cr is not None:
        inside &= (Xg - cr[0]) ** 2 + (Y - cr[1]) ** 2 > r_cr**2
    cand = np.where(inside, blur.astype(np.int64), -1)
    k = int(np.argmax(cand))  # first maximum in raster order
    by, bx = divmod(k, w)
    p4 = None
    if cand[by, bx] > t_pup:
        p4 = ref_tcom(blur, bx, by, r_p4, t_pup)  # 24-25
    res["p4"] = p4
    return res


def hull_of(out_hull: np.ndarray, n: int):
    return sorted(map(tuple, out_hull[:n].tolist()))


def main(write: bool = True, cpp_prm: np.ndarray | None = None, laplacian=None, frame_filter=None) -> int:
    sc = synth.Scene()
    rend = synth.Renderer(sc, seed=11)
    rng = np.random.default_rng(12)
    prm = dn.default_params()
    nb = dn.Tracker(sc.height, sc.width, prm)
    cp = dpi_cpp.Tracker(sc.height, sc.width, prm if cpp_prm is None else cpp_prm)
    frames = []
    for az in (-8, -3, 0, 4, 8):
        for el in (-8, 0, 7):
            frames.append(("rotation", rend.frame(synth.geometry(sc, az, el), rng)))
    for _ in range(4):
        frames.append(("blink", rend.blink(rng, closure=1.0)))
        frames.append(("half-blink", rend.blink(rng, closure=0.5)))
    # Pupil against the left image border (exercises the border rule in pass B).
    frames.append(("border", rend.frame(synth.geometry(sc, 0, 0, head_dx_px=-300), rng)))
    for s in (2.0, 4.0, 8.0):
        rend.scene.noise_scale = s
        frames.append((f"noise{s}", rend.frame(synth.geometry(sc, 2, -2), rng)))
    rend.scene.noise_scale = 1.0

    worst = {"numba_vs_cpp": 0.0, "numba_vs_ref_cr": 0.0, "numba_vs_ref_p4": 0.0, "numba_vs_ref_pupil": 0.0}
    hull_mismatch = 0
    flag_mismatch = 0
    rows = []
    if frame_filter is not None:
        frames = [f for f in frames if frame_filter(f[0])]
    for name, img in frames:
        a = nb(img).copy()
        hull_n = hull_of(nb.ws.hull, int(a[dn.O_NHULL])) if not math.isnan(a[dn.O_NHULL]) else []
        b = cp(img).copy()
        both = ~(np.isnan(a) & np.isnan(b))
        diff = float(np.nanmax(np.abs(a[both] - b[both]))) if both.any() else 0.0
        if np.any(np.isnan(a) != np.isnan(b)):
            diff = float("inf")
        worst["numba_vs_cpp"] = max(worst["numba_vs_cpp"], diff)
        r = reference(img, prm, laplacian)
        row = {"frame": name, "flags_numba": int(a[0]), "flags_cpp": int(b[0]), "numba_vs_cpp_max_abs": diff}
        if r["flags"]:
            same_hull = r["hull"] == hull_n
            hull_mismatch += not same_hull
            row["hull_identical"] = same_hull
            if int(a[0]) & dn.F_ELLIPSE:
                d = max(abs(a[dn.O_PUP_X] - r["pupil"][0]), abs(a[dn.O_PUP_Y] - r["pupil"][1]))
                worst["numba_vs_ref_pupil"] = max(worst["numba_vs_ref_pupil"], d)
            for key, ox, fl in (("cr", dn.O_CR_X, dn.F_CR), ("p4", dn.O_P4_X, dn.F_P4)):
                has = bool(int(a[0]) & fl)
                if has != (r[key] is not None):
                    flag_mismatch += 1
                    row[f"{key}_flag_mismatch"] = True
                elif has:
                    d = max(abs(a[ox] - r[key][0]), abs(a[ox + 1] - r[key][1]))
                    worst[f"numba_vs_ref_{key}"] = max(worst[f"numba_vs_ref_{key}"], d)
        rows.append(row)
    summary = {
        "frames": len(frames),
        "worst_abs_difference": worst,
        "hull_mismatches": hull_mismatch,
        "detection_flag_mismatches": flag_mismatch,
        "rows": rows,
    }
    if write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "agreement.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))
    main.last = summary
    ok = worst["numba_vs_cpp"] == 0.0 and hull_mismatch == 0 and flag_mismatch == 0
    ok = ok and max(worst["numba_vs_ref_cr"], worst["numba_vs_ref_p4"]) < 1e-9
    print("AGREE" if ok else "DISAGREE")
    return 0 if ok else 1


def controls() -> int:
    """Negative controls: perturbations the check must catch. Writes agreement_controls.json."""
    cases = [
        ("C++ Tpup 31 (not 30)", dict(cpp_prm=dn.default_params(t_pup=31)), None),
        ("C++ Rerode 7 (not 8)", dict(cpp_prm=dn.default_params(r_erode=7)), None),
        ("C++ Rerode 7, on non-blink frames only (expected NOT caught)", dict(cpp_prm=dn.default_params(r_erode=7)), lambda n: "blink" not in n),
        ("C++ RP4 14 (not 15)", dict(cpp_prm=dn.default_params(r_p4=14)), None),
        ("C++ RP4 14, on non-blink frames only (expected NOT caught)", dict(cpp_prm=dn.default_params(r_p4=14)), lambda n: "blink" not in n),
        ("reference with an 8-neighbor Laplacian", dict(laplacian=np.array([[1, 1, 1], [1, -8, 1], [1, 1, 1]])), None),
        ("reference with an 8-neighbor Laplacian, non-blink frames", dict(laplacian=np.array([[1, 1, 1], [1, -8, 1], [1, 1, 1]])),
         lambda n: "blink" not in n),
    ]
    out = []
    for label, kw, flt in cases:
        rc = main(write=False, frame_filter=flt, **kw)
        s = main.last
        out.append({"control": label, "caught": rc != 0, "frames": s["frames"],
                    "worst_abs_difference": s["worst_abs_difference"],
                    "hull_mismatches": s["hull_mismatches"],
                    "detection_flag_mismatches": s["detection_flag_mismatches"]})
        print(out[-1])
    (RESULTS / "agreement_controls.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    if "--controls" in sys.argv:
        sys.exit(controls())
    sys.exit(main())
