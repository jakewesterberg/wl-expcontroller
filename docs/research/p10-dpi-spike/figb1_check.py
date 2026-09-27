"""Reproduce the paper's Figure B.1 simulation for the thresholded centroid.

Paper (bioRxiv v2 Appendix B, Fig. B.1 caption): 20 x 20 pixel Gaussian blobs,
I[i, j] = G(i, j) + eta, eta ~ N(0, 1), G(i, j) = SNR * exp(-((i-10)^2 + (j-10)^2) / 6),
error = Euclidean distance between estimated and true center, mean +- SD over 10,000
images, threshold in noise-SD units, SNR = 5, 10, 20, 50.

The paper's curve values are only available as a plot; the minima below were read by eye
from the log-scale panel (approximate, +-15 %), and are what this script is compared with.
Matching them is evidence our ThresholdedCenterOfMass is the paper's.

The caption's formula (exponent / 6, sigma^2 = 3) is run, and also exponent / 12
(sigma^2 = 6): the plotted curves at negative thresholds and at SNR 5 are better matched by
the latter, so the caption and the figure may disagree by a factor of two in the exponent.

Writes figb1_check.json to docs/measurements/dev-machine/2026-09-27-p10-dpi-spike/.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-p10-dpi-spike"

# Read by eye from Fig. B.1a (blue curves): (minimum mean error px, threshold at minimum).
PAPER_BY_EYE = {5: (0.27, 2.0), 10: (0.115, 2.5), 20: (0.057, 3.5), 50: (0.023, 8.0)}


def main() -> None:
    rng = np.random.default_rng(1)
    n = 10_000
    ii, jj = np.mgrid[0:20, 0:20].astype(np.float64)
    thresholds = np.arange(-10.0, 10.01, 0.5)
    out = {"n_images": n, "thresholds": thresholds.tolist(), "caption_exp_6": {}, "alt_exp_12": {}}
    for key, den, snr in [(k, d, s) for k, d in (("caption_exp_6", 6.0), ("alt_exp_12", 12.0)) for s in (5, 10, 20, 50)]:
        g = snr * np.exp(-((ii - 10) ** 2 + (jj - 10) ** 2) / den)
        img = g[None] + rng.standard_normal((n, 20, 20))
        means, sds = [], []
        for t in thresholds:
            w = np.maximum(img - t, 0.0)
            s = w.sum((1, 2))
            ok = s > 0
            cx = (w * jj).sum((1, 2))[ok] / s[ok]
            cy = (w * ii).sum((1, 2))[ok] / s[ok]
            err = np.hypot(cx - 10, cy - 10)
            # Above the blob's peak some images have no positive weight; the paper's
            # curves stop there too. Require >= 99 % of images to have an estimate.
            if ok.mean() < 0.99:
                means.append(float("nan"))
                sds.append(float("nan"))
                continue
            means.append(float(err.mean()))
            sds.append(float(err.std()))
        k = int(np.nanargmin(means))
        paper = PAPER_BY_EYE[snr]
        out[key][str(snr)] = {
            "mean_error_px": [None if m != m else m for m in means],
            "sd_error_px": [None if v != v else v for v in sds],
            "min_mean_error_px": means[k],
            "threshold_at_min": float(thresholds[k]),
            "paper_by_eye_min_mean_error_px": paper[0],
            "paper_by_eye_threshold_at_min": paper[1],
            "ratio_ours_to_paper": means[k] / paper[0],
            "at_minus10sd": means[0],
        }
        print(f"{key} SNR {snr:2d}: ours min {means[k]:.4f} px at {thresholds[k]:+.1f} SD; "
              f"paper (by eye) ~{paper[0]:.3f} at ~{paper[1]:+.1f}; ratio {means[k] / paper[0]:.2f}; "
              f"at -10 SD ours {means[0]:.3f}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "figb1_check.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
