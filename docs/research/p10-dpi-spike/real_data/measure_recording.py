"""Measure OpenIrisDPI's real output in the tutorial recording (P10 follow-up, report §7b).

Every number this writes is FROM THE TUTORIAL RECORDING: OpenIrisDPI's own per-frame P1
(`CR1`) and P4 (`CR4`) positions, on the lab setup that recorded it. It is not our
tracker, not our rig, and not a measurement of P4 brightness (the file holds positions).

    python measure_recording.py --txt <session>.txt --targets calibration.npz
    python measure_recording.py --selftest      # the estimators on signals of known noise

Writes recording.json to docs/measurements/dev-machine/2026-09-27-p10-dpi-spike/real_data/.

Method, in brief (the report's §7b has it in full):
- usable frame: pupil found, P1 and P4 both non-zero, and neither a whole-pixel centroid;
- fixation: an 11-frame (about 22 ms) least-squares slope of P1 - P4 gives its velocity;
  a frame is in fixation when that speed is under V px/s, all 11 frames are usable, and
  no pupil-lost frame is within 100 ms;
- windows: each fixation run is cut into consecutive non-overlapping W-frame windows;
- per window and axis: SD, RMS of successive differences, and a white-noise floor from
  the periodogram above 200 Hz (the band the paper's WN-RMS uses, per the spike report).
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import platform
import re
import xml.etree.ElementTree as ET

import numpy as np

import recording as rec

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[2] / "measurements" / "dev-machine" / "2026-09-27-p10-dpi-spike" / "real_data"

V_BASE = 30.0          # px/s, P1 - P4 speed below which a frame is fixation
V_SWEEP = (15.0, 30.0, 60.0)
W_BASE = 100           # frames per window (about 200 ms)
W_SWEEP = (50, 100, 250)
SLOPE_N = 11           # frames in the velocity estimate (about 22 ms)
BLINK_GUARD = 50       # frames (about 100 ms) kept clear of any pupil-lost frame
FLOOR_HZ = 200.0       # white-noise floor band: [200 Hz, Nyquist)
HUMP_HZ = (30.0, 180.0)
PCT = (5, 25, 50, 75, 95)
SIGNALS = ("p1x", "p1y", "p4x", "p4y", "dx", "dy")


# ---------------------------------------------------------------- small helpers

def _round(x):
    if isinstance(x, float):
        return float(f"{x:.6g}")
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    if isinstance(x, np.generic):
        return _round(x.item())
    return x


def runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Start (inclusive) and end (exclusive) of each run of True."""
    m = np.concatenate([[0], mask.astype(np.int8), [0]])
    dm = np.diff(m)
    return np.flatnonzero(dm == 1), np.flatnonzero(dm == -1)


def dilate(mask: np.ndarray, r: int) -> np.ndarray:
    return np.convolve(mask.astype(np.int32), np.ones(2 * r + 1, np.int32), "same") > 0


def pct(a, q=PCT) -> dict:
    a = np.asarray(a, float)
    if a.size == 0:
        return {"n": 0}
    out = {"n": int(a.size), "mean": float(a.mean())}
    out.update({f"p{p}": float(np.percentile(a, p)) for p in q})
    return out


def slope(x: np.ndarray, n: int, fs: float) -> np.ndarray:
    """Centered n-point least-squares slope, per second."""
    k = np.arange(n) - (n - 1) / 2
    k = k / np.sum(k * k)
    return np.convolve(x, k[::-1], "same") * fs


def whole_pixel(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (x == np.round(x)) & (y == np.round(y))


# ---------------------------------------------------------------- 1. subject and setup

def setup_facts(side: dict[str, pathlib.Path], cols: dict, targets: pathlib.Path | None,
                header: list[str]) -> dict:
    root = ET.parse(side["settings"]).getroot()
    top = {t: root.findtext(t) for t in (
        "EyeTrackerSystem", "EyeTrackingPipeline", "CalibrationMethod", "RecordVideo",
        "MaxNumberOfProcessingThreads", "BufferSize")}

    def item(section: str, key: str) -> ET.Element | None:
        for it in root.find(section).findall("item"):
            if it.findtext("key/string") == key:
                return it.find("value")[0]
        return None

    cam = item("AllEyeTrackerSystemSettings", top["EyeTrackerSystem"])
    camera = {c.tag: (c.text if len(c) == 0 else {g.tag: g.text for g in c}) for c in cam}
    pipe = item("AllTrackingPipelinesSettings", top["EyeTrackingPipeline"])
    pipeline = {}
    for c in pipe:
        if c.tag.startswith("Cropping"):
            pipeline[c.tag] = {"Width": c.findtext("Width"), "Height": c.findtext("Height")}
        else:
            pipeline[c.tag] = c.text

    log_lines = side["log"].read_text(errors="replace").splitlines()
    kinds: dict[str, int] = {}
    other = []
    for ln in log_lines:
        m = re.match(r"^(\d\d:\d\d:\d\d) - (.*)$", ln)
        msg = m.group(2) if m else ln
        if msg.startswith("Calibration Message = "):
            k = msg.split("= ", 1)[1].split(":", 1)[0]
            kinds[k] = kinds.get(k, 0) + 1
        else:
            other.append(ln)
    targets_in_log = sorted({ln.rsplit(":", 1)[1] for ln in log_lines if "FixStart:" in ln})

    cal = ET.parse(side["cal"]).getroot()
    cal_numbers = [float(e.text) for e in cal.iter() if e.text and re.fullmatch(r"-?[\d.]+", e.text.strip())]
    cal_results = sorted({e.text for e in cal.iter("ProcessFrameResult")})

    words = re.compile(r"monkey|macaque|human|subject|animal|participant|patient", re.I)
    hits = [f"data header: {c}" for c in header if words.search(c)]
    for name, p in side.items():
        hits += [f"{name}: {w}" for w in words.findall(p.read_text(errors="replace"))]
    npz = {}
    if targets is not None:
        with np.load(targets, allow_pickle=False) as z:
            npz = {k: list(z[k].shape) for k in z.files}
            hits += [f"calibration.npz key: {k}" for k in z.files if words.search(k)]

    coord_max = {e: {c: float(cols[f"{e}{c}"].max()) for c in ("CR1X", "CR1Y", "CR4X", "CR4Y", "PupilX", "PupilY")}
                 for e in rec.EYES}
    return {
        "subject": {
            "stated": bool(hits),
            "search": "monkey|macaque|human|subject|animal|participant|patient, case-insensitive, "
                      "in settings, log, .cal and calibration.npz key names",
            "hits": hits,
        },
        "settings": {"top": top, "camera_system": camera, "dpi_pipeline": pipeline},
        "log": {
            "first_line": log_lines[0], "last_line": log_lines[-1],
            "calibration_messages": kinds, "other_lines": other,
            "fixation_targets_in_log": targets_in_log,
        },
        "cal_file": {"every_number_zero": all(v == 0 for v in cal_numbers), "numbers": len(cal_numbers),
                     "ProcessFrameResult": cal_results},
        "calibration_npz_arrays": npz,
        "coordinate_max_px": coord_max,
    }


# ---------------------------------------------------------------- 2. validity

def validity(cols: dict, fs: float, in_target: np.ndarray | None) -> tuple[dict, dict]:
    out, masks = {}, {}
    for e in rec.EYES:
        g = lambda c: cols[f"{e}{c}"]  # noqa: E731
        pup_fields = np.stack([g(c) == 0 for c in ("PupilX", "PupilY", "PupilWidth", "PupilHeight", "PupilAngle")])
        pupil_lost = (g("PupilX") == 0) & (g("PupilY") == 0)
        p1_missing = (g("CR1X") == 0) | (g("CR1Y") == 0)
        p4_missing = (g("CR4X") == 0) | (g("CR4Y") == 0)
        p1_whole = whole_pixel(g("CR1X"), g("CR1Y")) & ~p1_missing
        p4_whole = whole_pixel(g("CR4X"), g("CR4Y")) & ~p4_missing
        usable = ~pupil_lost & ~p1_missing & ~p4_missing & ~p1_whole & ~p4_whole
        m = {
            "pupil_lost": pupil_lost,
            "p1_missing": p1_missing,
            "p4_missing": p4_missing,
            "p4_reported_while_pupil_lost": pupil_lost & ~p4_missing,
            "p1_whole_pixel": p1_whole,
            "p4_whole_pixel": p4_whole,
            "p4_unusable": pupil_lost | p4_missing | p4_whole,
            "p1_unusable": pupil_lost | p1_missing | p1_whole,
            "not_usable": ~usable,
        }
        masks[e] = {"usable": usable, **m}
        d = {}
        for k, a in m.items():
            st, en = runs(a)
            r = {"frames": int(a.sum()), "percent": 100.0 * float(a.mean()), "episodes": int(st.size),
                 "episode_ms": pct((en - st) / fs * 1e3, (50, 90, 100))}
            if in_target is not None:
                r["percent_in_completed_targets"] = 100.0 * float(a[in_target].mean())
                r["percent_outside"] = 100.0 * float(a[~in_target].mean())
            d[k] = r
        d["pupil_fields_exact_zero"] = {
            c: int(z.sum()) for c, z in zip(("PupilX", "PupilY", "PupilWidth", "PupilHeight", "PupilAngle"), pup_fields)}
        d["pupil_lost_rows_with_any_nonzero_pupil_field"] = int((pupil_lost & ~pup_fields.all(0)).sum())
        d["p1_missing_breakdown"] = {
            "both_zero": int(((g("CR1X") == 0) & (g("CR1Y") == 0)).sum()),
            "y_zero_only": int(((g("CR1X") != 0) & (g("CR1Y") == 0)).sum()),
            "x_zero_only": int(((g("CR1X") == 0) & (g("CR1Y") != 0)).sum()),
            "on_pupil_lost_frames": int((p1_missing & pupil_lost).sum()),
        }
        d["p4_missing_on_pupil_lost_frames"] = int((p4_missing & pupil_lost).sum())
        py = g("PupilY")
        ok = ~pupil_lost
        d["pupil_y_median_px"] = {"p1_missing": float(np.median(py[ok & p1_missing])),
                                  "p1_present": float(np.median(py[ok & ~p1_missing]))}
        if in_target is not None:
            lo, hi = np.percentile(py[ok & in_target], [1, 99])
            sel = ok & p1_missing
            d["p1_missing_with_pupil_y_outside_target_p1_p99"] = {
                "target_pupil_y_p1_p99": [float(lo), float(hi)],
                "percent_of_p1_missing": 100.0 * float(((py[sel] < lo) | (py[sel] > hi)).mean())}
        dq = g("DataQuality")
        vals, counts = np.unique(dq, return_counts=True)
        d["DataQuality"] = {repr(float(v)): int(c) for v, c in zip(vals, counts)}
        out[e] = d
    return out, masks


def blinks(cols: dict, masks: dict, fs: float, fix_masks: dict) -> dict:
    n = next(iter(cols.values())).size
    out = {}
    lost = {e: masks[e]["pupil_lost"] for e in rec.EYES}
    for e, other in (("Left", "Right"), ("Right", "Left")):
        st, en = runs(lost[e])
        near = dilate(lost[other], 25)
        x4, y4 = cols[f"{e}CR4X"], cols[f"{e}CR4Y"]
        good4 = ~masks[e]["p4_missing"] & ~lost[e]
        dist = []
        for s, t in zip(st, en):
            j = s - 1
            while j >= 0 and not masks[e]["usable"][j]:
                j -= 1
            if j >= 0:
                dist.append(float(np.median(np.hypot(x4[s:t] - x4[j], y4[s:t] - y4[j]))))
        x1, y1 = cols[f"{e}CR1X"], cols[f"{e}CR1Y"]
        good1 = ~masks[e]["p1_missing"] & ~lost[e]
        # Step from frame i to i + 1, kept only where both frames report the reflection.
        jump = np.r_[np.hypot(np.diff(x4), np.diff(y4)), 0.0]
        pair = good4 & np.r_[good4[1:], False]
        jump1 = np.r_[np.hypot(np.diff(x1), np.diff(y1)), 0.0]
        pair1 = good1 & np.r_[good1[1:], False]
        before = np.zeros(n, bool)
        after = np.zeros(n, bool)
        for s, t in zip(st, en):
            before[max(s - 25, 0):s - 1] = True
            after[t:min(t + 24, n - 1)] = True
        fx = fix_masks[e] & np.r_[fix_masks[e][1:], False]
        out[e] = {
            "pupil_lost_episodes": int(st.size),
            "episode_ms": pct((en - st) / fs * 1e3),
            "overlapping_other_eye_within_50ms": float(np.mean([near[s:t].any() for s, t in zip(st, en)])),
            "p4_reported_while_pupil_lost": {
                "episodes_with_p4_on_every_frame": float(np.mean([(~masks[e]["p4_missing"][s:t]).all() for s, t in zip(st, en)])),
                "median_distance_from_last_usable_p4_px": pct(dist),
            },
            "p4_step_over_2px_percent": {
                "50ms_before_pupil_loss": 100.0 * float((jump[before & pair] > 2).mean()),
                "50ms_after_pupil_recovery": 100.0 * float((jump[after & pair] > 2).mean()),
                "in_fixation": 100.0 * float((jump[fx] > 2).mean()),
            },
            "p1_step_over_2px_percent_same_frames": {
                "50ms_before_pupil_loss": 100.0 * float((jump1[before & pair1] > 2).mean()),
                "50ms_after_pupil_recovery": 100.0 * float((jump1[after & pair1] > 2).mean()),
            },
        }
    either = lost["Left"] | lost["Right"]
    st, en = runs(either)
    merged = [[st[0], en[0]]]
    for s, t in zip(st[1:], en[1:]):
        if s - merged[-1][1] <= 25:
            merged[-1][1] = t
        else:
            merged.append([s, t])
    merged = np.array(merged)
    out["either_eye_merged"] = {
        "rule": "pupil-lost runs in either eye, merged across gaps of 25 frames (50 ms) or less",
        "episodes": int(len(merged)),
        "per_minute": float(len(merged) / (n / fs / 60.0)),
        "episode_ms": pct((merged[:, 1] - merged[:, 0]) / fs * 1e3, (5, 25, 50, 75, 95, 100)),
    }
    return out


# ---------------------------------------------------------------- 3. frame timing

def timing(cols: dict, side: dict) -> dict:
    out = {}
    for e in rec.EYES:
        fn, raw, sec = cols[f"{e}FrameNumber"], cols[f"{e}FrameNumberRaw"], cols[f"{e}Seconds"]
        steps = np.diff(fn)
        dt = np.round(np.diff(sec) * 1e4).astype(np.int64)  # in 0.1 ms, the column's resolution
        vals, counts = np.unique(dt, return_counts=True)
        k = (fn - fn[0]).astype(float)
        line = np.polyfit(k, sec, 1)
        resid = (sec - np.polyval(line, k)) * 1e3
        out[e] = {
            "rows": int(fn.size),
            "frame_number_first_last": [int(fn[0]), int(fn[-1])],
            "frame_number_steps": {str(int(v)): int(c) for v, c in zip(*np.unique(steps, return_counts=True))},
            "gaps": int((steps != 1).sum()),
            "dropped_frames": int((steps[steps > 1] - 1).sum()),
            "frame_number_minus_raw": sorted({int(v) for v in np.unique(fn - raw)}),
            "seconds_resolution_s": 1e-4 if np.allclose(sec * 1e4, np.round(sec * 1e4)) else None,
            "interval_ms_counts": {f"{v / 10:.1f}": int(c) for v, c in zip(vals, counts)},
            "span_s": float(sec[-1] - sec[0]),
            "rate_hz": float((fn[-1] - fn[0]) / (sec[-1] - sec[0])),
            "period_ms_line_fit": float(line[0] * 1e3),
            "seconds_residual_from_line_ms_min_max": [float(resid.min()), float(resid.max())],
        }
    off = (cols["LeftSeconds"] - cols["RightSeconds"]) * 1e3
    out["left_right"] = {
        "frame_numbers_identical": bool(np.array_equal(cols["LeftFrameNumber"], cols["RightFrameNumber"])),
        "seconds_offset_ms_first_last_min_max": [float(off[0]), float(off[-1]), float(off.min()), float(off.max())],
    }
    dbg = {}
    for c in ("DebugTimeGrabbedLeft", "DebugTimeGrabbedRight", "DebugTimeProcessed"):
        d = np.diff(cols[c]) * 1e3
        dbg[c] = {"interval_ms": pct(d, (0.1, 1, 50, 99, 99.9, 100)), "percent_over_10ms": 100.0 * float((d > 10).mean())}
    lat = (cols["DebugTimeProcessed"] - np.maximum(cols["DebugTimeGrabbedLeft"], cols["DebugTimeGrabbedRight"])) * 1e3
    dbg["processed_minus_later_grab_ms"] = pct(lat, (1, 50, 99, 99.9, 100))
    dbg["processed_minus_later_grab_percent_over_10ms"] = 100.0 * float((lat > 10).mean())
    dbg["note"] = "DebugTime* meanings are inferred from the column names only; the file does not define them"
    out["debug_columns"] = dbg
    out["log_recorder_lines"] = [ln for ln in side["log"].read_text(errors="replace").splitlines()
                                 if "Recorder" in ln or "StopRecording" in ln]
    return out


# ---------------------------------------------------------------- targets and gain

def align_targets(cols: dict, targets: pathlib.Path) -> dict:
    """Map calibration.npz's clock onto frame numbers through the shared sync line."""
    with np.load(targets, allow_pickle=False) as z:
        t_sync, y_sync = z["t_sync"], z["y_sync"]
        fp = {k: z[k] for k in ("fp_on", "fp_off", "fp_x", "fp_y")}
    bit = ((cols["Int0"] >> rec.SYNC_BIT) & 1).astype(np.int8)
    e_eye = np.flatnonzero(np.diff(bit) != 0) + 1
    thr = 0.5 * (np.percentile(y_sync, 1) + np.percentile(y_sync, 99))
    yb = (y_sync > thr).astype(np.int8)
    e_npz = np.flatnonzero(np.diff(yb) != 0) + 1
    t_npz = t_sync[e_npz]
    fs0 = (cols["LeftFrameNumber"][-1] - cols["LeftFrameNumber"][0]) / (cols["LeftSeconds"][-1] - cols["LeftSeconds"][0])
    iv_eye, iv_npz = np.diff(e_eye) / fs0, np.diff(t_npz)
    best = None
    for k in range(-50, 51):
        a = iv_eye[max(-k, 0):][:2000]
        b = iv_npz[max(k, 0):][:2000]
        m = min(a.size, b.size)
        err = float(np.median(np.abs(a[:m] - b[:m])))
        if best is None or err < best[1]:
            best = (k, err)
    k = best[0]
    fe = e_eye[max(-k, 0):]
    tn = t_npz[max(k, 0):]
    m = min(fe.size, tn.size)
    fe, tn = fe[:m], tn[:m]
    polarity = float(np.mean(bit[fe] == yb[e_npz[max(k, 0):][:m]]))
    a, b = np.polyfit(tn, fe, 1)
    resid = fe - (a * tn + b)
    if polarity < 1.0 or np.abs(resid).max() > 2.0:
        raise SystemExit(f"sync alignment failed: polarity {polarity}, max residual {np.abs(resid).max():.2f} frames")
    on = np.round(a * fp["fp_on"] + b).astype(np.int64)
    off = np.round(a * fp["fp_off"] + b).astype(np.int64)
    return {
        "frame_per_s": float(a), "frame_at_t0": float(b), "edge_offset": int(k), "edges_matched": int(m),
        "residual_frames_max_abs": float(np.abs(resid).max()), "polarity_agreement": polarity,
        "on": on, "off": off, "x": fp["fp_x"], "y": fp["fp_y"],
    }


def target_mask(n: int, al: dict) -> np.ndarray:
    m = np.zeros(n, bool)
    for s, t in zip(al["on"], al["off"]):
        m[max(s, 0):min(t, n)] = True
    return m


def gain(cols: dict, masks: dict, al: dict) -> dict:
    """Affine fit of P1 - P4 (px) to target position (target units), per eye."""
    out = {}
    for e in rec.EYES:
        dx = cols[f"{e}CR1X"] - cols[f"{e}CR4X"]
        dy = cols[f"{e}CR1Y"] - cols[f"{e}CR4Y"]
        u = masks[e]["usable"]
        rows = []
        for off, tx, ty in zip(al["off"], al["x"], al["y"]):
            s, t = off - 150, off  # the last ~300 ms of each completed target period
            if s < 0 or t > u.size or u[s:t].mean() < 0.9:
                continue
            k = u[s:t]
            rows.append((tx, ty, np.median(dx[s:t][k]), np.median(dy[s:t][k])))
        r = np.array(rows)
        used = r.shape[0]
        for _ in range(3):
            A = np.column_stack([r[:, 0], r[:, 1], np.ones(len(r))])
            cx = np.linalg.lstsq(A, r[:, 2], rcond=None)[0]
            cy = np.linalg.lstsq(A, r[:, 3], rcond=None)[0]
            res = np.hypot(r[:, 2] - A @ cx, r[:, 3] - A @ cy)
            keep = res < 3 * np.median(res)
            r, res = r[keep], res[keep]
        G = np.array([[cx[0], cx[1]], [cy[0], cy[1]]])
        Gi = np.linalg.inv(G)
        out[e] = {
            "targets_with_90pct_usable": int(used), "kept_after_outlier_passes": int(len(r)),
            "px_per_unit": [[float(v) for v in row] for row in G],
            "offset_px": [float(cx[2]), float(cy[2])],
            "residual_px": pct(res, (50, 90)),
            "unit_per_px_row_norm": [float(np.linalg.norm(Gi[0])), float(np.linalg.norm(Gi[1]))],
            "arcmin_per_px_if_unit_is_degree": [60 * float(np.linalg.norm(Gi[0])), 60 * float(np.linalg.norm(Gi[1]))],
        }
    return out


# ---------------------------------------------------------------- 4. jitter

def signals(cols: dict, e: str) -> dict[str, np.ndarray]:
    p1x, p1y, p4x, p4y = (cols[f"{e}{c}"] for c in ("CR1X", "CR1Y", "CR4X", "CR4Y"))
    return {"p1x": p1x, "p1y": p1y, "p4x": p4x, "p4y": p4y, "dx": p1x - p4x, "dy": p1y - p4y}


def fixation(sig: dict, usable: np.ndarray, pupil_lost: np.ndarray, fs: float, v: float) -> np.ndarray:
    ok = usable & ~dilate(pupil_lost, BLINK_GUARD)
    whole = np.convolve(ok.astype(np.int32), np.ones(SLOPE_N, np.int32), "same") == SLOPE_N
    speed = np.hypot(slope(sig["dx"], SLOPE_N, fs), slope(sig["dy"], SLOPE_N, fs))
    return whole & (speed < v)


def windows(fix: np.ndarray, w: int, within: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Window starts, and each window's offset from the start of its fixation run."""
    st, en = runs(fix)
    starts, offs = [], []
    for s, t in zip(st, en):
        for s0 in range(s, t - w + 1, w):
            if within is None or within[s0:s0 + w].all():
                starts.append(s0)
                offs.append(s0 - s)
    return np.array(starts, np.int64), np.array(offs, np.int64)


def _detrend(X: np.ndarray) -> np.ndarray:
    t = np.arange(X.shape[1], dtype=float)
    t -= t.mean()
    Xd = X - X.mean(1, keepdims=True)
    return Xd - ((Xd * t).sum(1) / (t * t).sum())[:, None] * t


def periodogram(X: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """One-sided PSD (px^2/Hz) per row: mean and linear trend removed, Hann window."""
    w = np.hanning(X.shape[1])
    F = np.fft.rfft(_detrend(X) * w, axis=1)
    psd = np.abs(F) ** 2 / (fs * (w ** 2).sum())
    psd[:, 1:] *= 2
    if X.shape[1] % 2 == 0:
        psd[:, -1] /= 2
    return np.fft.rfftfreq(X.shape[1], 1 / fs), psd


def window_stats(x: np.ndarray, starts: np.ndarray, w: int, fs: float) -> dict[str, np.ndarray]:
    X = np.stack([x[s:s + w] for s in starts]).astype(float)
    d = np.diff(X, axis=1)
    dc = d - d.mean(1, keepdims=True)
    f, psd = periodogram(X, fs)
    band = (f >= FLOOR_HZ) & (f < fs / 2 - 1e-9)
    t = np.arange(w, dtype=float)
    t -= t.mean()
    return {
        "sd": X.std(1, ddof=1),
        "sd_detrended": _detrend(X).std(1, ddof=1),
        "rms_step": np.sqrt((d ** 2).mean(1)),
        "white_floor_sd": np.sqrt(psd[:, band].mean(1) * fs / 2),
        "step_lag1_autocorr": (dc[:, 1:] * dc[:, :-1]).sum(1) / (dc ** 2).sum(1),
        "drift_px_s": ((X - X.mean(1, keepdims=True)) * t).sum(1) / (t * t).sum() * fs,
    }


def jitter(cols: dict, masks: dict, fs: float, in_target: np.ndarray | None) -> tuple[dict, dict]:
    out, fixm = {}, {}
    for e in rec.EYES:
        sig = signals(cols, e)
        m = masks[e]
        fix = fixation(sig, m["usable"], m["pupil_lost"], fs, V_BASE)
        fixm[e] = fix
        starts, offs = windows(fix, W_BASE)
        res = {
            "fixation_frames_percent": 100.0 * float(fix.mean()),
            "windows": int(starts.size),
            "window_ms": W_BASE / fs * 1e3,
            "per_window": {},
        }
        per = {name: window_stats(sig[name], starts, W_BASE, fs) for name in SIGNALS}
        for name in SIGNALS:
            res["per_window"][name] = {k: pct(v) for k, v in per[name].items() if k != "drift_px_s"}
        res["p1_minus_p4_drift_speed_px_s"] = pct(np.hypot(per["dx"]["drift_px_s"], per["dy"]["drift_px_s"]))
        # Sensitivity to the two free choices.
        sens = []
        for v in V_SWEEP:
            fv = fixation(sig, m["usable"], m["pupil_lost"], fs, v)
            for w in W_SWEEP:
                s2, _ = windows(fv, w)
                row = {"v_px_s": v, "w_frames": w, "windows": int(s2.size)}
                for name in ("dx", "dy"):
                    st = window_stats(sig[name], s2, w, fs)
                    row[name] = {k: float(np.median(st[k])) for k in ("sd", "rms_step", "white_floor_sd")}
                sens.append(row)
        res["sensitivity_medians"] = sens
        if in_target is not None:
            s3, _ = windows(fix, W_BASE, within=in_target)
            row = {"windows": int(s3.size)}
            for name in SIGNALS:
                st = window_stats(sig[name], s3, W_BASE, fs)
                row[name] = {k: float(np.median(st[k])) for k in ("sd", "rms_step", "white_floor_sd")}
            res["inside_completed_targets_medians"] = row
        # Does the sample-to-sample jitter decay after a fixation starts (post-saccadic)?
        s4, o4 = windows(fix, 50)
        st = window_stats(sig["dx"], s4, 50, fs)["rms_step"]
        sty = window_stats(sig["dy"], s4, 50, fs)["rms_step"]
        bins = [(0, 50), (50, 100), (100, 200), (200, 400), (400, 10 ** 9)]
        res["rms_step_by_time_since_fixation_start"] = [
            {"frames": [lo, hi if hi < 10 ** 9 else None], "windows": int(((o4 >= lo) & (o4 < hi)).sum()),
             "dx_median": float(np.median(st[(o4 >= lo) & (o4 < hi)])),
             "dy_median": float(np.median(sty[(o4 >= lo) & (o4 < hi)]))} for lo, hi in bins]
        out[e] = res
    return out, fixm


def spectra(cols: dict, fixm: dict, fs: float, w: int = 250) -> dict:
    """Mean spectra in fixation, their white floor and band-limited excess, and L-R coherence."""
    edges = np.arange(0.0, fs / 2 + 10, 10.0)
    out = {"window_frames": w, "band_edges_hz": [float(v) for v in edges], "per_eye": {}}
    for e in rec.EYES:
        sig = signals(cols, e)
        starts, _ = windows(fixm[e], w)
        eye = {"windows": int(starts.size)}
        for name in SIGNALS:
            X = np.stack([sig[name][s:s + w] for s in starts]).astype(float)
            f, psd = periodogram(X, fs)
            mean = psd.mean(0)
            floor_band = (f >= FLOOR_HZ) & (f < fs / 2 - 1e-9)
            floor = float(mean[floor_band].mean())
            hb = (f >= HUMP_HZ[0]) & (f < HUMP_HZ[1])
            df = f[1] - f[0]
            eye[name] = {
                "band_mean_psd_px2_hz": [float(mean[(f >= lo) & (f < hi)].mean()) if ((f >= lo) & (f < hi)).any() else None
                                         for lo, hi in zip(edges[:-1], edges[1:])],
                "white_floor_psd_px2_hz": floor,
                "white_floor_sd_px": float(np.sqrt(floor * fs / 2)),
                "excess_rms_px_30_180hz": float(np.sqrt(np.clip(mean[hb] - floor, 0, None).sum() * df)),
            }
        out["per_eye"][e] = eye
    joint = fixm["Left"] & fixm["Right"]
    starts, _ = windows(joint, w)
    wv = np.hanning(w)
    bands = [(2, 10), (10, 30), (30, 50), (50, 80), (80, 110), (110, 150), (150, 200), (200, 250)]
    coh = {"windows": int(starts.size), "bands_hz": bands}
    for name in SIGNALS:
        A, B = (np.fft.rfft(_detrend(np.stack([signals(cols, e)[name][s:s + w] for s in starts]).astype(float)) * wv, axis=1)
                for e in rec.EYES)
        f = np.fft.rfftfreq(w, 1 / fs)
        c = np.abs((A * np.conj(B)).mean(0)) ** 2 / ((np.abs(A) ** 2).mean(0) * (np.abs(B) ** 2).mean(0))
        coh[name] = [float(c[(f >= lo) & (f < hi)].mean()) for lo, hi in bands]
    out["left_right_coherence"] = coh
    return out


# ---------------------------------------------------------------- self-test

def selftest(fs: float = 498.55) -> dict:
    """The estimators on signals of known noise: white, and white plus a 60-140 Hz band.

    It must return the white SD from both estimators on white noise, and must show the
    step RMS rising while the >200 Hz floor stays put when band-limited power is added.
    """
    rng = np.random.default_rng(20260927)
    n = 200_000
    sd = 0.03
    t = np.arange(n) / fs
    white = sd * rng.standard_normal(n) + 0.5 * np.sin(2 * np.pi * 0.3 * t)  # plus a slow drift
    f = np.fft.rfftfreq(n, 1 / fs)
    spec = np.where((f > 60) & (f < 140), 1.0, 0.0) * np.exp(2j * np.pi * rng.random(f.size))
    band = np.fft.irfft(spec, n)
    band *= 0.08 / band.std()
    ramp = 12.0 * t
    sl = slope(ramp, SLOPE_N, fs)[SLOPE_N:-SLOPE_N]
    out = {"true_white_sd": sd, "band_rms_added": 0.08, "slope_of_12px_s_ramp": pct(sl, (0, 100))}
    starts = np.arange(1000, n - 2000, 400)
    for name, x in (("white", white), ("white_plus_band", white + band)):
        st = window_stats(x, starts, W_BASE, fs)
        out[name] = {"rms_step_over_sqrt2": float(np.median(st["rms_step"]) / np.sqrt(2)),
                     "white_floor_sd": float(np.median(st["white_floor_sd"])),
                     "step_lag1_autocorr": float(np.median(st["step_lag1_autocorr"]))}
    ok = (abs(out["white"]["rms_step_over_sqrt2"] / sd - 1) < 0.05
          and abs(out["white"]["white_floor_sd"] / sd - 1) < 0.1
          and abs(out["white_plus_band"]["white_floor_sd"] / sd - 1) < 0.1
          and out["white_plus_band"]["rms_step_over_sqrt2"] > 2 * sd
          and abs(out["white"]["step_lag1_autocorr"] + 0.5) < 0.05
          and np.allclose(sl, 12.0))
    out["pass"] = bool(ok)
    return out


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--txt", help=f"the session .txt (or set {rec.ENV_TXT})")
    ap.add_argument("--targets", help=f"calibration.npz (or set {rec.ENV_TARGETS}); optional")
    ap.add_argument("--out", default=str(RESULTS), help="output directory")
    ap.add_argument("--selftest", action="store_true", help="run only the estimator self-test")
    args = ap.parse_args()

    check = selftest()
    print("selftest", "PASS" if check["pass"] else "FAIL", json.dumps(_round(check)))
    if args.selftest:
        raise SystemExit(0 if check["pass"] else 1)
    if not check["pass"]:
        raise SystemExit("estimator self-test failed; refusing to measure")

    txt, targets = rec.resolve(args.txt, args.targets)
    side = rec.sidecars(txt)
    cols, census = rec.load(txt)
    n = cols["LeftFrameNumber"].size
    fs = float((cols["LeftFrameNumber"][-1] - cols["LeftFrameNumber"][0])
               / (cols["LeftSeconds"][-1] - cols["LeftSeconds"][0]))

    al = align_targets(cols, targets) if targets else None
    in_target = target_mask(n, al) if al else None
    valid, masks = validity(cols, fs, in_target)
    jit, fixm = jitter(cols, masks, fs, in_target)
    result = {
        "note": "FROM THE TUTORIAL RECORDING: OpenIrisDPI's own per-frame output. Not our tracker, "
                "not our rig, not a measurement of P4 brightness.",
        "date": datetime.date.today().isoformat(),
        "input": {"txt": txt.name, "bytes": txt.stat().st_size, "rows": census["rows"],
                  "columns": census["columns"], "targets": targets.name if targets else None},
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "pandas": __import__("pandas").__version__, "platform": platform.platform()},
        "method": {"v_px_s": V_BASE, "v_sweep": V_SWEEP, "window_frames": W_BASE, "w_sweep": W_SWEEP,
                   "slope_frames": SLOPE_N, "blink_guard_frames": BLINK_GUARD, "floor_hz": FLOOR_HZ,
                   "excess_band_hz": HUMP_HZ, "rate_hz": fs},
        "estimator_selftest": check,
        "setup": setup_facts(side, cols, targets, list(census["census"])),
        "column_census": census["census"],
        "validity": valid,
        "blinks": blinks(cols, masks, fs, fixm),
        "timing": timing(cols, side),
        "jitter": jit,
        "spectra": spectra(cols, fixm, fs),
    }
    if al:
        result["targets"] = {
            "alignment": {k: v for k, v in al.items() if k not in ("on", "off", "x", "y")},
            "completed_target_periods": int(al["on"].size),
            "period_ms": pct((al["off"] - al["on"]) / fs * 1e3, (5, 50, 95)),
            "frames_in_periods_percent": 100.0 * float(in_target.mean()),
            "unit_note": "calibration.npz and the log give target x/y without a unit; arcmin figures assume degrees",
            "gain": gain(cols, masks, al),
        }
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "recording.json").write_text(json.dumps(_round(result), indent=1) + "\n")
    print(f"wrote {out / 'recording.json'}")


if __name__ == "__main__":
    main()
