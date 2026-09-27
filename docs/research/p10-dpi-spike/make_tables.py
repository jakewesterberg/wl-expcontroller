"""Render the committed JSON results as the markdown tables quoted in the report.

    python make_tables.py > ../../measurements/dev-machine/2026-09-27-p10-dpi-spike/tables.md
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-p10-dpi-spike"


def speed_tables(path: pathlib.Path, title: str) -> None:
    d = json.loads(path.read_text())
    env = d["environment"]
    print(f"## {title}\n")
    print(f"DEV MACHINE: {env['cpu']}, {env['platform']}, {env['power']}; Python {env['python']}, "
          f"numba {env['numba']}, numpy {env['numpy']}; {env['cxx']} {env['cxx_flags']}. "
          f"{d['frames_per_camera']} frames per camera per row. Load average at start {env['load_avg']}.\n")
    for size in ("roi_720x450", "full_1440x1080"):
        print(f"### {size}\n")
        print("| core | cams | paced 500 Hz | cam | median ms | IQR ms | p99 ms | p99.9 ms | max ms | >1 ms | >2 ms |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in d["runs"]:
            if r["size"] != size:
                continue
            print(f"| {r['core']} | {r['cameras']} | {'yes' if r['paced_500hz'] else 'no'} | {r['camera']} | "
                  f"{r['median_ms']:.3f} | {r['iqr_ms']:.3f} | {r['p99_ms']:.3f} | {r['p99_9_ms']:.3f} | "
                  f"{r['max_ms']:.2f} | {100 * r['frac_over_1ms']:.2f} % | {100 * r['frac_over_2ms']:.2f} % |")
        st = d.get("stages_cpp_native", {}).get(size)
        if st:
            print("\nC++ native, one camera, unpaced, per stage (median / p99 ms): " + "; ".join(
                f"{k} {v['median_ms']:.3f} / {v['p99_ms']:.3f}" for k, v in st.items()))
        print()


def precision_tables(path: pathlib.Path) -> None:
    d = json.loads(path.read_text())
    ex = d["experiments"]
    o = d["optics"]["arcmin_per_px"]
    print("## Precision (synthetic frames, DEV MACHINE)\n")
    print("Errors in sensor pixels; x = azimuth, y = elevation. 'noise SD' = pooled within-position SD "
          "(the analogue of white-noise RMS); 'bias spread' = SD across positions of per-position mean error. "
          f"Arcmin per px of P1-P4: x {o['x_human']:.2f} / y {o['y_human']:.2f} (human-eye gain), "
          f"x {o['x_macaque']:.2f} / y {o['y_macaque']:.2f} (ASSUMED macaque).\n")

    def row(label, r):
        if "dpi_x" not in r:
            return f"| {label} | {r['p4_snr']:.0f} | {100 * r['detection_rate']:.1f} % | - | - | - | - | - | - | - |"
        dx, dy = r["dpi_x"], r["dpi_y"]
        return (f"| {label} | {r['p4_snr']:.0f} | {100 * r['detection_rate']:.1f} % | "
                f"{r['p1_x']['noise_sd']:.4f} / {r['p1_y']['noise_sd']:.4f} | "
                f"{r['p4_x']['noise_sd']:.4f} / {r['p4_y']['noise_sd']:.4f} | "
                f"{dx['noise_sd']:.4f} / {dy['noise_sd']:.4f} | "
                f"{dx['bias_spread']:.4f} / {dy['bias_spread']:.4f} | "
                f"{dx['p99_abs']:.3f} / {dy['p99_abs']:.3f} | "
                f"{dx['noise_arcmin_human']:.3f} / {dy['noise_arcmin_human']:.3f} | "
                f"{dx['noise_arcmin_macaque']:.3f} / {dy['noise_arcmin_macaque']:.3f} |")

    head = ("| condition | P4 SNR | detected | P1 noise SD x/y px | P4 noise SD x/y px | P1-P4 noise SD x/y px | "
            "P1-P4 bias spread x/y px | P1-P4 p99 abs x/y px | P1-P4 noise arcmin x/y (human gain) | "
            "(ASSUMED macaque) |\n|---|---|---|---|---|---|---|---|---|---|")
    for name, title in (
        ("snr_noise", "Noise sweep (base P4 amplitude 90 DN)"),
        ("p4_amplitude", "P4 amplitude sweep (P1 = 80 x P4)"),
        ("p4_sigma", "P4 size sweep"),
        ("head_translation", "Head translation (gaze 2, -2 deg)"),
        ("p4_near_pupil_edge", "Hard case: P4 near the pupil edge (distance, px)"),
        ("p4_near_p1", "Hard case: P4 near P1 (separation, px; Rcr = 29)"),
        ("p2_present", "P2 beside P1 (1 % of P1)"),
        ("variants", "Choices the paper leaves open"),
        ("edge_mitigation", "P4 near the pupil edge: published RP4 15, RP4 6, and a hull-masked ROI (not published)"),
    ):
        print(f"### {title}\n")
        print(head)
        for k, r in ex[name].items():
            print(row(k, r))
        if name in ("p2_present", "p4_near_pupil_edge", "edge_mitigation"):
            print("\nMean P1-P4 error (bias) x/y px: " + "; ".join(
                f"{k} {r['dpi_x']['mean']:+.3f}/{r['dpi_y']['mean']:+.3f}" for k, r in ex[name].items() if "dpi_x" in r))
        print()
    # Rotation grid summarized.
    rot = ex["rotation"]
    print("### Eye rotation grid, +-8 deg (5 x 5)\n")
    print("| az \\ el | " + " | ".join(str(e) for e in (-8, -4, 0, 4, 8)) + " |")
    print("|---|---|---|---|---|---|")
    for az in (-8, -4, 0, 4, 8):
        cells = []
        for el in (-8, -4, 0, 4, 8):
            r = rot[f"az{az}_el{el}"]
            if "dpi_x" not in r:
                cells.append(f"P4 lost ({100 * r['detection_rate']:.0f} %)")
            else:
                cells.append(f"{r['dpi_x']['noise_sd']:.3f}/{r['dpi_y']['noise_sd']:.3f}")
        print(f"| {az} | " + " | ".join(cells) + " |")
    print("\nCells: P1-P4 noise SD x/y in px.\n")
    print("| az \\ el (mean P1-P4 error x/y px) | " + " | ".join(str(e) for e in (-8, -4, 0, 4, 8)) + " |")
    print("|---|---|---|---|---|---|")
    for az in (-8, -4, 0, 4, 8):
        cells = []
        for el in (-8, -4, 0, 4, 8):
            r = rot[f"az{az}_el{el}"]
            cells.append("P4 lost" if "dpi_x" not in r else f"{r['dpi_x']['mean']:+.3f}/{r['dpi_y']['mean']:+.3f}")
        print(f"| {az} | " + " | ".join(cells) + " |")
    print("\nCells: mean P1-P4 error (bias) x/y in px, averaged over the positions near each gaze.\n")
    print("### Blinks\n")
    print("| lid closure | frames | pupil reported | CR reported | P4 reported | P4 > 2 px from true P4 | median P4 error px |")
    print("|---|---|---|---|---|---|---|")
    for k, r in ex["blink"].items():
        med = r["p4_error_px_median_when_reported"]
        print(f"| {k.split('_')[1]} | {r['frames']} | {100 * r['pupil_reported']:.0f} % | {100 * r['cr_reported']:.0f} % | "
              f"{100 * r['p4_reported']:.0f} % | {100 * r['p4_reported_more_than_2px_from_true_p4']:.0f} % | "
              f"{'-' if med is None else f'{med:.0f}'} |")
    print()


def figb1_table(path: pathlib.Path) -> None:
    d = json.loads(path.read_text())
    print("## Fig. B.1 reproduction (thresholded centroid, mean Euclidean error)\n")
    print("| SNR | paper, read by eye (px @ SD) | ours, caption exp(-r^2/6) | ours, exp(-r^2/12) |")
    print("|---|---|---|---|")
    for snr in ("5", "10", "20", "50"):
        a, b = d["caption_exp_6"][snr], d["alt_exp_12"][snr]
        print(f"| {snr} | ~{a['paper_by_eye_min_mean_error_px']:.3f} @ ~{a['paper_by_eye_threshold_at_min']:+.1f} | "
              f"{a['min_mean_error_px']:.4f} @ {a['threshold_at_min']:+.1f} | {b['min_mean_error_px']:.4f} @ {b['threshold_at_min']:+.1f} |")
    print()


def main() -> None:
    print("# P10 DPI spike: result tables (generated by make_tables.py from the JSON beside this file)\n")
    for f, t in (("speed.json", "Speed, run 1"), ("speed_run2.json", "Speed, run 2 (repeat)")):
        if (RESULTS / f).exists():
            speed_tables(RESULTS / f, t)
    if (RESULTS / "precision.json").exists():
        precision_tables(RESULTS / "precision.json")
    if (RESULTS / "figb1_check.json").exists():
        figb1_table(RESULTS / "figb1_check.json")
    a = json.loads((RESULTS / "agreement.json").read_text())
    print("## Core agreement\n")
    print(f"{a['frames']} frames; worst |numba - C++| = {a['worst_abs_difference']['numba_vs_cpp']}; "
          f"hull mismatches vs literal reference = {a['hull_mismatches']}; detection-flag mismatches = "
          f"{a['detection_flag_mismatches']}; worst |numba - reference| CR {a['worst_abs_difference']['numba_vs_ref_cr']}, "
          f"P4 {a['worst_abs_difference']['numba_vs_ref_p4']}, pupil center {a['worst_abs_difference']['numba_vs_ref_pupil']:.1e} px.")


if __name__ == "__main__":
    main()
