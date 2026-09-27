"""Set the tutorial recording's real jitter against the spike's synthetic precision.

Reads real_data/recording.json (from measure_recording.py) and the spike's precision.json,
writes real_data/comparison.json and real_data/tables.md (the report's §7b tables).

    python compare_synthetic.py

The matching P4 SNR is an INFERENCE: the synthetic P4 SNR at which the spike's code, on
synthetic frames, shows the noise OpenIrisDPI shows on this recording. The recording
holds positions, not intensities, so it measures no P4 brightness.
"""

from __future__ import annotations

import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SPIKE = HERE.parents[2] / "measurements" / "dev-machine" / "2026-09-27-p10-dpi-spike"
REAL = SPIKE / "real_data"

# The paper's in-vivo white-noise RMS, as the spike report (§1, §5.2) quotes it.
PAPER_WN_ARCMIN = {"x": 0.39, "y": 0.44}
AXES = ("x", "y")
EYES = ("Left", "Right")


def curve(prec: dict, sig: str) -> list[tuple[float, float]]:
    """(SNR, noise SD px) along the spike's noise sweep, ascending SNR."""
    pts = [(v["p4_snr"], v[sig]["noise_sd"]) for v in prec["experiments"]["snr_noise"].values()]
    return sorted(pts)


def invert(pts: list[tuple[float, float]], y: float) -> tuple[float, bool]:
    """SNR at which the curve reaches noise y: log-log interpolation, end slope beyond."""
    ls = [(math.log(s), math.log(n)) for s, n in pts]
    ly = math.log(y)
    for (s0, n0), (s1, n1) in zip(ls, ls[1:]):
        if min(n0, n1) <= ly <= max(n0, n1):
            return math.exp(s0 + (ly - n0) * (s1 - s0) / (n1 - n0)), False
    (s0, n0), (s1, n1) = (ls[0], ls[1]) if ly > ls[0][1] else (ls[-2], ls[-1])
    return math.exp(s0 + (ly - n0) * (s1 - s0) / (n1 - n0)), True


def r(x: float, d: int = 3) -> float:
    return float(f"{x:.{d}g}")


def main() -> None:
    real = json.loads((REAL / "recording.json").read_text())
    prec = json.loads((SPIKE / "precision.json").read_text())
    scale_curve = sorted((v["noise_scale"], v) for v in prec["experiments"]["snr_noise"].values())
    base_snr = prec["experiments"]["snr_noise"]["scale_1.0"]["p4_snr"]

    out = {"note": "Real values FROM THE TUTORIAL RECORDING; synthetic values from precision.json. "
                   "Matching SNRs are inferences, not measurements of P4 brightness.",
           "paper_wn_rms_arcmin": PAPER_WN_ARCMIN, "per_eye": {}}
    for e in EYES:
        jit = real["jitter"][e]["per_window"]
        spec = real["spectra"]["per_eye"][e]
        am = real["targets"]["gain"][e]["arcmin_per_px_if_unit_is_degree"]
        eye = {}
        for i, a in enumerate(AXES):
            row = {}
            d = f"d{a}"
            floor = spec[d]["white_floor_sd_px"]
            pw = jit[d]["white_floor_sd"]
            step = jit[d]["rms_step"]["p50"] / math.sqrt(2)
            c = curve(prec, f"dpi_{a}")
            row["p1_minus_p4_px"] = {
                "white_floor_mean_spectrum": floor,
                "white_floor_per_window_p25_p50_p75": [pw["p25"], pw["p50"], pw["p75"]],
                "rms_step_over_sqrt2_median": step,
                "sd_median": jit[d]["sd"]["p50"],
                # White noise at the floor would give a ratio of 1; the excess is the band-limited part.
                "rms_step_over_sqrt2_floor_ratio": step / pw["p50"],
            }
            snr_floor, x1 = invert(c, floor)
            snr_iqr = [invert(c, v)[0] for v in (pw["p75"], pw["p50"], pw["p25"])]
            snr_step, x2 = invert(c, step)
            row["matching_p4_snr_INFERENCE"] = {
                "from_white_floor": snr_floor, "extrapolated": x1,
                "from_per_window_floor_p75_p50_p25": snr_iqr,
                "if_all_step_jitter_were_white": snr_step, "extrapolated_step": x2,
            }
            paper_px = PAPER_WN_ARCMIN[a] / am[i]
            row["arcmin_if_target_unit_is_degree"] = {
                "arcmin_per_px": am[i],
                "white_floor": floor * am[i],
                "rms_step_over_sqrt2": step * am[i],
                "paper_wn_rms": PAPER_WN_ARCMIN[a],
                "paper_wn_rms_in_this_recordings_px": paper_px,
                "synthetic_snr_reaching_paper_figure_at_this_scale": invert(c, paper_px)[0],
            }
            p4 = spec[f"p4{a}"]["white_floor_sd_px"]
            row["p4_alone"] = {"white_floor": p4, "matching_p4_snr": invert(curve(prec, f"p4_{a}"), p4)[0]}
            p1 = spec[f"p1{a}"]["white_floor_sd_px"]
            sc = [(s, v[f"p1_{a}"]["noise_sd"]) for s, v in scale_curve]
            # Invert along 1/scale so the curve, like SNR, falls as its abscissa rises.
            inv_scale, _ = invert([(1 / s, n) for s, n in sc][::-1], p1)
            row["p1_alone"] = {"white_floor": p1, "matching_noise_scale": 1 / inv_scale,
                               "model_p4_snr_at_that_scale": base_snr * inv_scale}
            # How much of the P1 and P4 floors is shared, frame by frame, and cancels in P1 - P4.
            row["p1_p4_floor_correlation"] = (p1 ** 2 + p4 ** 2 - floor ** 2) / (2 * p1 * p4)
            eye[a] = row
        out["per_eye"][e] = eye
    (REAL / "comparison.json").write_text(json.dumps(out, indent=1) + "\n")
    (REAL / "tables.md").write_text(tables(real, out, prec))
    print(f"wrote {REAL / 'comparison.json'} and {REAL / 'tables.md'}")


def tables(real: dict, cmp: dict, prec: dict) -> str:
    L = ["# P10 real data: tables (generated by `compare_synthetic.py`)", "",
         "**Every real number here is FROM THE TUTORIAL RECORDING** (OpenIrisDPI's own output, "
         f"`{real['input']['txt']}`, {real['input']['rows']:,} rows). Synthetic numbers are from "
         "`../precision.json`. Rates are percentages of all rows unless stated.", ""]

    L += ["## Validity (per eye)", "",
          "| | Left % | Left episodes | Right % | Right episodes |", "|---|---|---|---|---|"]
    names = {"pupil_lost": "pupil lost (all pupil fields 0)", "p1_missing": "P1 missing (a CR1 coordinate is 0)",
             "p4_missing": "P4 missing (a CR4 coordinate is 0)",
             "p4_reported_while_pupil_lost": "P4 reported on a pupil-lost frame",
             "p1_whole_pixel": "P1 a whole-pixel centroid", "p4_whole_pixel": "P4 a whole-pixel centroid",
             "p1_unusable": "P1 unusable (any of the above)", "p4_unusable": "P4 unusable (any of the above)",
             "not_usable": "frame not usable for P1 − P4"}
    for k, label in names.items():
        a, b = real["validity"]["Left"][k], real["validity"]["Right"][k]
        L.append(f"| {label} | {a['percent']:.3f} | {a['episodes']} | {b['percent']:.3f} | {b['episodes']} |")
    L += ["", "`DataQuality` is " + ", ".join(
        f"{e}: " + ", ".join(f"{v} on {c:,} rows" for v, c in real["validity"][e]["DataQuality"].items())
        for e in EYES) + ". Inside the completed target periods every class above is "
        + ", ".join(f"{e} {real['validity'][e]['not_usable']['percent_in_completed_targets']:.4f} %" for e in EYES)
        + " not usable.", ""]

    b = real["blinks"]
    L += ["## Blinks (pupil-lost episodes)", "",
          "| | Left | Right |", "|---|---|---|",
          f"| episodes | {b['Left']['pupil_lost_episodes']} | {b['Right']['pupil_lost_episodes']} |",
          "| duration ms, median (p5–p95) | " + " | ".join(
              f"{b[e]['episode_ms']['p50']:.0f} ({b[e]['episode_ms']['p5']:.0f}–{b[e]['episode_ms']['p95']:.0f})" for e in EYES) + " |",
          "| overlapping a pupil loss in the other eye (±50 ms) | " + " | ".join(
              f"{100 * b[e]['overlapping_other_eye_within_50ms']:.0f} %" for e in EYES) + " |",
          "| P4 reported on every pupil-lost frame of the episode | " + " | ".join(
              f"{100 * b[e]['p4_reported_while_pupil_lost']['episodes_with_p4_on_every_frame']:.0f} % of episodes" for e in EYES) + " |",
          "| that P4's distance from the last usable P4, px, median (p5–p95) | " + " | ".join(
              "{p50:.0f} ({p5:.0f}–{p95:.0f})".format(**b[e]['p4_reported_while_pupil_lost']['median_distance_from_last_usable_p4_px']) for e in EYES) + " |",
          "| frame steps > 2 px, P4 / P1: 50 ms before loss | " + " | ".join(
              f"{b[e]['p4_step_over_2px_percent']['50ms_before_pupil_loss']:.0f} % / {b[e]['p1_step_over_2px_percent_same_frames']['50ms_before_pupil_loss']:.0f} %" for e in EYES) + " |",
          "| frame steps > 2 px, P4 / P1: 50 ms after recovery | " + " | ".join(
              f"{b[e]['p4_step_over_2px_percent']['50ms_after_pupil_recovery']:.0f} % / {b[e]['p1_step_over_2px_percent_same_frames']['50ms_after_pupil_recovery']:.0f} %" for e in EYES) + " |",
          "| P4 frame steps > 2 px in fixation | " + " | ".join(
              f"{b[e]['p4_step_over_2px_percent']['in_fixation']:.3f} %" for e in EYES) + " |",
          "", "Either eye, runs merged across ≤ 50 ms: {episodes} episodes, {pm:.1f} per minute, "
          "median {m:.0f} ms (max {mx:.0f} ms).".format(
              episodes=b["either_eye_merged"]["episodes"], pm=b["either_eye_merged"]["per_minute"],
              m=b["either_eye_merged"]["episode_ms"]["p50"], mx=b["either_eye_merged"]["episode_ms"]["p100"]), ""]

    t = real["timing"]
    L += ["## Frame timing", "", "| | Left | Right |", "|---|---|---|"]
    L.append("| rows | " + " | ".join(f"{t[e]['rows']:,}" for e in EYES) + " |")
    L.append("| frame-number gaps / dropped frames | " + " | ".join(f"{t[e]['gaps']} / {t[e]['dropped_frames']}" for e in EYES) + " |")
    L.append("| `Seconds` intervals (0.1 ms resolution) | " + " | ".join(
        ", ".join(f"{k} ms × {v:,}" for k, v in t[e]["interval_ms_counts"].items()) for e in EYES) + " |")
    L.append("| rate over the span, Hz | " + " | ".join(f"{t[e]['rate_hz']:.4f}" for e in EYES) + " |")
    L.append("| `Seconds` minus a straight line in frame number, ms (min, max) | " + " | ".join(
        "{:.3f}, {:.3f}".format(*t[e]["seconds_residual_from_line_ms_min_max"]) for e in EYES) + " |")
    dbg = t["debug_columns"]
    L += ["", "Left − Right `Seconds`: {0:.1f} ms at the start, {1:.1f} ms at the end (min {2:.1f}, max {3:.1f}).".format(
        *t["left_right"]["seconds_offset_ms_first_last_min_max"]), "",
        "`DebugTime*` columns (meaning inferred from the names only): grab interval p99.9 "
        f"{dbg['DebugTimeGrabbedLeft']['interval_ms']['p99.9']:.1f} ms, max {dbg['DebugTimeGrabbedLeft']['interval_ms']['p100']:.1f} ms, "
        f"{dbg['DebugTimeGrabbedLeft']['percent_over_10ms']:.2f} % over 10 ms; processed − later grab median "
        f"{dbg['processed_minus_later_grab_ms']['p50']:.1f} ms, p99 {dbg['processed_minus_later_grab_ms']['p99']:.1f} ms, "
        f"max {dbg['processed_minus_later_grab_ms']['p100']:.1f} ms, "
        f"{dbg['processed_minus_later_grab_percent_over_10ms']:.1f} % over 10 ms.", ""]

    m = real["method"]
    L += ["## Jitter in fixation windows", "",
          f"Windows of {m['window_frames']} frames (≈ {real['jitter']['Left']['window_ms']:.0f} ms); fixation = "
          f"{m['slope_frames']}-frame slope speed of P1 − P4 < {m['v_px_s']:.0f} px/s. Values are px; "
          "each cell is the median (p25–p75) across windows. `floor` is the white-noise SD from the "
          f"periodogram above {m['floor_hz']:.0f} Hz.", ""]
    for e in EYES:
        jj = real["jitter"][e]
        L += [f"**{e}**: {jj['windows']:,} windows ({jj['fixation_frames_percent']:.0f} % of frames in fixation).", "",
              "| signal | SD | RMS step | floor | step lag-1 autocorr (white: −0.5) |", "|---|---|---|---|---|"]
        for s, lab in (("p1x", "P1 x"), ("p1y", "P1 y"), ("p4x", "P4 x"), ("p4y", "P4 y"), ("dx", "P1 − P4 x"), ("dy", "P1 − P4 y")):
            w = jj["per_window"][s]
            cell = lambda k: f"{w[k]['p50']:.3f} ({w[k]['p25']:.3f}–{w[k]['p75']:.3f})"  # noqa: E731
            L.append(f"| {lab} | {cell('sd')} | {cell('rms_step')} | {cell('white_floor_sd')} | "
                     f"{w['step_lag1_autocorr']['p50']:.2f} |")
        L.append("")
    L += ["Sensitivity of the P1 − P4 medians (x / y, px) to the fixation threshold V and window W:", "",
          "| eye | V px/s | W frames | windows | SD | RMS step | floor |", "|---|---|---|---|---|---|---|"]
    for e in EYES:
        for s in real["jitter"][e]["sensitivity_medians"]:
            L.append(f"| {e} | {s['v_px_s']:.0f} | {s['w_frames']} | {s['windows']:,} | "
                     f"{s['dx']['sd']:.3f} / {s['dy']['sd']:.3f} | {s['dx']['rms_step']:.3f} / {s['dy']['rms_step']:.3f} | "
                     f"{s['dx']['white_floor_sd']:.3f} / {s['dy']['white_floor_sd']:.3f} |")
    L.append("")

    sp = real["spectra"]
    L += [f"## Spectra in fixation ({sp['window_frames']}-frame windows, mean periodogram)", "",
          "| signal | Left floor px | Left 30–180 Hz excess RMS px | Right floor px | Right excess px |", "|---|---|---|---|---|"]
    for s in ("p1x", "p1y", "p4x", "p4y", "dx", "dy"):
        a, c = sp["per_eye"]["Left"][s], sp["per_eye"]["Right"][s]
        L.append(f"| {s} | {a['white_floor_sd_px']:.4f} | {a['excess_rms_px_30_180hz']:.3f} | "
                 f"{c['white_floor_sd_px']:.4f} | {c['excess_rms_px_30_180hz']:.3f} |")
    edges = sp["band_edges_hz"]
    L += ["", "Mean PSD, px²/Hz, by 10 Hz band (Left):", "",
          "| band Hz | " + " | ".join(("P1 x", "P4 x", "P1−P4 x", "P1−P4 y")) + " |", "|---|---|---|---|---|"]
    for i, lo in enumerate(edges[:-1]):
        vals = [sp["per_eye"]["Left"][s]["band_mean_psd_px2_hz"][i] for s in ("p1x", "p4x", "dx", "dy")]
        if vals[0] is None:
            continue
        L.append(f"| {lo:.0f}–{edges[i + 1]:.0f} | " + " | ".join(f"{v:.2e}" for v in vals) + " |")
    co = sp["left_right_coherence"]
    L += ["", f"Left–Right coherence ({co['windows']:,} windows with both eyes in fixation):", "",
          "| band Hz | " + " | ".join(("P1 x", "P1 y", "P4 x", "P4 y", "P1−P4 x", "P1−P4 y")) + " |", "|---|---|---|---|---|---|---|"]
    for i, (lo, hi) in enumerate(co["bands_hz"]):
        L.append(f"| {lo}–{hi} | " + " | ".join(f"{co[s][i]:.2f}" for s in ("p1x", "p1y", "p4x", "p4y", "dx", "dy")) + " |")

    g = real["targets"]["gain"]
    L += ["", "## Gain from the fixation targets", "",
          f"{real['targets']['completed_target_periods']} completed target periods, aligned through the sync line "
          f"({real['targets']['alignment']['edges_matched']:,} edges, max residual "
          f"{real['targets']['alignment']['residual_frames_max_abs']:.2f} frames). Target units are not stated.", "",
          "| eye | px per unit (x←tx, y←ty) | fit residual px, median | arcmin per px if unit = degree (x / y) |", "|---|---|---|---|"]
    for e in EYES:
        G = g[e]["px_per_unit"]
        L.append(f"| {e} | {G[0][0]:.2f}, {G[1][1]:.2f} (cross {G[0][1]:.2f}, {G[1][0]:.2f}) | {g[e]['residual_px']['p50']:.2f} | "
                 f"{g[e]['arcmin_per_px_if_unit_is_degree'][0]:.2f} / {g[e]['arcmin_per_px_if_unit_is_degree'][1]:.2f} |")

    L += ["", "## Against the spike's synthetic precision (INFERENCE)", "",
          "Synthetic P1 − P4 noise SD against P4 SNR (spike noise sweep): " + "; ".join(
              f"SNR {s:.0f}: {n:.4f}" for s, n in curve(prec, "dpi_x")) + " (x).", "",
          "| eye, axis | real floor px | matching SNR (per-window IQR) | real RMS step/√2 px | ÷ per-window floor | SNR if all of it were white | "
          "floor in arcmin (if deg) | paper WN-RMS | SNR reaching the paper's figure at this scale |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in EYES:
        for a in AXES:
            x = cmp["per_eye"][e][a]
            px, sn, am = x["p1_minus_p4_px"], x["matching_p4_snr_INFERENCE"], x["arcmin_if_target_unit_is_degree"]
            L.append(f"| {e} {a} | {px['white_floor_mean_spectrum']:.4f} | {sn['from_white_floor']:.0f} "
                     f"({sn['from_per_window_floor_p75_p50_p25'][0]:.0f}–{sn['from_per_window_floor_p75_p50_p25'][2]:.0f}) | "
                     f"{px['rms_step_over_sqrt2_median']:.4f} | {px['rms_step_over_sqrt2_floor_ratio']:.1f} | "
                     f"{sn['if_all_step_jitter_were_white']:.0f} | "
                     f"{am['white_floor']:.2f}′ | {am['paper_wn_rms']:.2f}′ | {am['synthetic_snr_reaching_paper_figure_at_this_scale']:.0f} |")
    L += ["", "P1 and P4 alone (white floor px → the spike's model). The last column is the correlation of "
          "the P1 and P4 floors implied by the three floors, (P1² + P4² − (P1 − P4)²) / (2·P1·P4):", "",
          "| eye, axis | P4 floor | matching P4 SNR | P1 floor | P1 matches noise scale | model P4 SNR at that scale | P1–P4 floor correlation |",
          "|---|---|---|---|---|---|---|"]
    for e in EYES:
        for a in AXES:
            x = cmp["per_eye"][e][a]
            L.append(f"| {e} {a} | {x['p4_alone']['white_floor']:.4f} | {x['p4_alone']['matching_p4_snr']:.0f} | "
                     f"{x['p1_alone']['white_floor']:.4f} | {x['p1_alone']['matching_noise_scale']:.1f} | "
                     f"{x['p1_alone']['model_p4_snr_at_that_scale']:.0f} | {x['p1_p4_floor_correlation']:.2f} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
