#!/usr/bin/env python3
"""Which calibration constellation should the calibration block present?

Run: `python3 tools/calibration_design.py [--setup NAME]` from the repository root,
with a `wl-preproc` checkout beside this one. Each setup is the source of one record
under `docs/measurements/dev-machine/` (`SETUPS` names it); regenerate a record from
this script rather than editing its numbers by hand. The default, `2026-09-05`, is the
31.5-inch stereoscope that record was measured on, and still regenerates it byte for
byte.

**Two things are measured, and they are not the same question.**

*Conditioning* is `wl-preproc`'s own `_conditioning` -- imported from their source
rather than reimplemented, so what runs here is what will actually gate a session.
It answers "does this constellation constrain the model at all", and it is
deliberately scale-invariant, which means **it cannot see how far the targets
reach.** A grid shrunk to 60% of the field scores identically to one spanning it.

*Accuracy* is out-of-sample gaze error in degrees: fit the map, then evaluate it
across the region tasks actually test. A `Window` is scored wherever a task puts a
stimulus, not where a calibration target was, so error at the targets is not the
quantity of interest -- the gap between the two is.

**The forward model is an assumption, not a measurement of our rig.** It is stated
below and swept across four settings; every conclusion is reported with that sweep
so it is visible whether it survives the assumption changing. V3 replaces it with
bench data. **No number printed here is a claim about our hardware.**
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

#: The same two locations `tests/conftest.py` searches, for the same reason: the
#: metric that gates a session is theirs, and a second copy of it here would be a
#: second definition free to drift. Beside the repo locally; inside it under CI,
#: which cannot place a checkout outside its workspace.
for _candidate in (_ROOT.parent / "wl-preproc", _ROOT / "wl-preproc"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
        break

try:
    from wl_preproc.eye.calibration import (
        MIN_CONDITIONING,
        CalibrationModel,
        _conditioning,
        basis,
        n_terms,
    )
except ImportError as exc:  # pragma: no cover - operator-facing
    raise SystemExit(
        f"wl-preproc is not importable ({exc}). This script measures against THEIR "
        f"conditioning metric and basis; reimplementing either here would measure a "
        f"second definition free to drift from the one that gates a session."
    ) from exc

from tasks.rig import RIG  # noqa: E402
from wl_xcon.calibration import DIRECT_REGION_DEG, REACH  # noqa: E402
from wl_xcon.geometry import Geometry  # noqa: E402

#: The geometry the 2026-09-05 record was measured on: S0's 31.5-inch 16:9 panel (an
#: 80.01 cm diagonal) at 57 cm, as S0 described the rig then. Each eye sees half the
#: panel's width and its full height, so the per-eye field is TALLER than it is wide --
#: a grid square in degrees is the wrong shape for it.
#:
#: **It is not the rig's panel any more.** The PI chose the 26.5-inch ASUS PG27UCDM on
#: 2026-09-27 (S0 §5.1). This stays on the 31.5-inch panel so the script still
#: regenerates the record it is the source of. A run for the PG27UCDM is a new record
#: with its own date, not a regeneration of this one.
_DIAGONAL_CM = 80.01
GEOMETRY = Geometry(
    panel_width_cm=_DIAGONAL_CM * 16 / math.hypot(16, 9),
    panel_height_cm=_DIAGONAL_CM * 9 / math.hypot(16, 9),
    viewing_distance_cm=57.0,
)
HALF_H = GEOMETRY.half_field_h_deg
HALF_V = GEOMETRY.half_field_v_deg

#: Targets sit inside the panel edge. A target at the very edge is one the animal
#: saccades to and half-misses.
MARGIN = 0.85

#: The largest eccentricity the reference tasks declared on 2026-09-05 --
#: `fixation_detection`'s `target_position` ran -16..16 deg, inside the 31.5-inch
#: panel's field. Accuracy is scored over this region because it is where windows can
#: actually land, not over the whole panel.
MAX_TESTED_DEG = 16.0

#: Where a window can land, which the tested disc is clipped to; `None` when the disc
#: lies inside the field whole. On 2026-09-05 the field was the extent itself.
FIELD: tuple[float, float] | None = (HALF_H, HALF_V)

#: What section 7 calls the extent the constellation is scaled to.
EXTENT = "Per-eye field"

#: The reach sections 1, 2 and 4-7 lay their designs out at: section 3's choice.
SHOWN_REACH = 0.75

#: Per-fixation scatter: where the animal's gaze actually sits relative to the
#: target centre, not sample noise within a fixation. An assumption, swept in
#: `fixations_per_target` rather than asserted.
FIXATION_NOISE_DEG = 0.35



@dataclass(frozen=True)
class Setup:
    """What one record measures: the extent the constellation is scaled to (the
    per-eye field on 2026-09-05; a calibration region since the direct-view spec's
    §6), where a window can land, and the reach the record chose."""

    record: str
    extent: str
    half: tuple[float, float]
    field: tuple[float, float] | None
    max_tested_deg: float
    reach: float


#: The stereoscope's record is measured at the drawing's `E` = 1.6 cm. Its ±12° mask
#: is inside the viewport at every IPD the drawing tabulates, so `E` moves nothing here.
_STEREOSCOPE = RIG.stereoscope(half_ipd_cm=1.6)

SETUPS: dict[str, Setup] = {
    "2026-09-05": Setup(
        record="2026-09-05-calibration-constellation.md",
        extent="Per-eye field",
        half=(HALF_H, HALF_V),
        field=(HALF_H, HALF_V),
        max_tested_deg=16.0,
        reach=0.75,
    ),
    # Direct view's region, ±15°, where the stimuli go (direct-view spec §6). Windows
    # land out to ±16°, the detection tasks' range in direct view; that disc lies inside
    # the ±30.5° × ±18.4° field, clear of the housings near (±30°, −18°), so nothing is
    # clipped -- and the field itself is not built here, because direct view refuses to
    # exist without the housings, which are unmeasured (`tasks/rig.py`).
    "direct": Setup(
        record="2026-09-28-calibration-constellation-direct.md",
        extent="Calibration region, direct view",
        half=(DIRECT_REGION_DEG, DIRECT_REGION_DEG),
        field=None,
        max_tested_deg=16.0,
        reach=REACH["direct"],
    ),
    # The mask, which is the stereoscope's field and its calibration region at once.
    # Windows land anywhere inside it, so the tested disc runs to its half-angle.
    "stereoscope": Setup(
        record="2026-09-28-calibration-constellation-stereoscope.md",
        extent="Calibration region, stereoscope (the mask)",
        half=(_STEREOSCOPE.half_field_h_deg, _STEREOSCOPE.half_field_v_deg),
        field=(_STEREOSCOPE.half_field_h_deg, _STEREOSCOPE.half_field_v_deg),
        max_tested_deg=RIG.mask_deg,
        reach=REACH["stereoscope"],
    ),
}


def use(name: str) -> Setup:
    """Point every section at one setup. The sections read module globals, as they
    did when there was one setup, so the 2026-09-05 run is unchanged line for line."""
    global HALF_H, HALF_V, FIELD, MAX_TESTED_DEG, EXTENT, SHOWN_REACH
    setup = SETUPS[name]
    HALF_H, HALF_V = setup.half
    FIELD = setup.field
    MAX_TESTED_DEG = setup.max_tested_deg
    EXTENT = setup.extent
    SHOWN_REACH = setup.reach
    return setup


def _pct(reach: float) -> str:
    return "%d%%" % round(100 * reach)


# ---------------------------------------------------------------------------
# Forward model: gaze angle -> raw P1-P4 vector.
# ---------------------------------------------------------------------------
# Three effects with physical names, so a sweep can say which one a design is
# sensitive to:
#
#   ODD / RADIAL   The Purkinje difference scales with sin(theta). Inverting gives
#                  theta = arcsin(r/k) ~ r/k + r^3/6k^3: an odd, radially symmetric
#                  expansion. **Not representable in [1, dx, dy, dx^2, dy^2, dx*dy]
#                  at all** -- no even polynomial contains an odd radial term. This
#                  is the error floor no constellation removes.
#
#   OBLIQUITY      The camera views the eye off-axis, so the projection of eye
#                  rotation onto the image plane is foreshortened and perspective-
#                  divided. Genuinely quadratic; this is what the second-order
#                  basis exists to absorb.
#
#   ASPHERICITY    Corneal curvature varies across the surface; modelled as a small
#                  radial distortion on the raw vector.

OPTICS = {
    "near-axial": dict(yaw_deg=5.0, pitch_deg=2.0, kappa=0.01),
    "moderate": dict(yaw_deg=25.0, pitch_deg=10.0, kappa=0.04),
    "strong obliquity": dict(yaw_deg=40.0, pitch_deg=20.0, kappa=0.08),
    "radial-dominated": dict(yaw_deg=5.0, pitch_deg=2.0, kappa=0.15),
}


def forward(theta_deg: np.ndarray, yaw_deg: float, pitch_deg: float, kappa: float) -> np.ndarray:
    """Raw Purkinje-difference vector for gaze angles, in arbitrary sensor units."""
    tx, ty = np.radians(theta_deg[:, 0]), np.radians(theta_deg[:, 1])
    gaze = np.column_stack(
        [np.sin(tx) * np.cos(ty), np.sin(ty), np.cos(tx) * np.cos(ty)]
    )

    a, b = np.radians(yaw_deg), np.radians(pitch_deg)
    right = np.array([np.cos(a), 0.0, -np.sin(a)])
    up = np.array([np.sin(a) * np.sin(b), np.cos(b), np.cos(a) * np.sin(b)])
    forward_axis = np.cross(right, up)

    # Weak perspective -- the camera is far compared with the eye, so the divide is
    # gentle, but it is what makes the map genuinely quadratic rather than linear.
    depth = 6.0
    raw = np.column_stack([gaze @ right, gaze @ up]) / (depth + gaze @ forward_axis)[:, None]

    r2 = (raw**2).sum(axis=1, keepdims=True)
    return raw * (1.0 + kappa * r2 * 100.0)


# ---------------------------------------------------------------------------
# Constellations, in degrees.
# ---------------------------------------------------------------------------


def scaled(xs, ys) -> np.ndarray:
    """Fractions of the per-eye half-field, per axis, to degrees."""
    return np.array([(x * HALF_H * MARGIN, y * HALF_V * MARGIN) for x, y in zip(xs, ys)])


def grid(n: int, reach: float = 1.0) -> np.ndarray:
    ticks = np.linspace(-reach, reach, n)
    xs, ys = np.meshgrid(ticks, ticks)
    return scaled(xs.ravel(), ys.ravel())


def ring(n: int, radius: float = 1.0, centre: bool = False) -> np.ndarray:
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    xs, ys = list(radius * np.cos(angles)), list(radius * np.sin(angles))
    if centre:
        xs.append(0.0)
        ys.append(0.0)
    return scaled(xs, ys)


def diagonals(reach: float, fraction: float) -> np.ndarray:
    f = fraction * reach
    return scaled([f, -f, f, -f], [f, f, -f, -f])


def augmented(reach: float | None = None, fraction: float = 0.50) -> np.ndarray:
    """The recommended constellation: a 3x3 plus four intermediates, at the setup's
    reach unless told otherwise."""
    reach = SHOWN_REACH if reach is None else reach
    return np.vstack([grid(3, reach=reach), diagonals(reach, fraction)])


# ---------------------------------------------------------------------------
# Fit and evaluate.
# ---------------------------------------------------------------------------


def fit(raw: np.ndarray, degrees: np.ndarray, model: CalibrationModel) -> np.ndarray:
    coefficients, *_ = np.linalg.lstsq(basis(raw, model), degrees, rcond=None)
    return coefficients


def predict(raw: np.ndarray, coefficients: np.ndarray, model: CalibrationModel) -> np.ndarray:
    return basis(raw, model) @ coefficients


def tested_region(step: int = 24) -> np.ndarray:
    """Where a window can actually land: a disc out to `MAX_TESTED_DEG`, clipped
    to the field. Not the panel's corners, which no task reaches."""
    angles = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    rings = []
    for eccentricity in np.linspace(0.5, MAX_TESTED_DEG, step):
        points = np.column_stack(
            [eccentricity * np.cos(angles), eccentricity * np.sin(angles)]
        )
        if FIELD is not None:
            inside = (np.abs(points[:, 0]) <= FIELD[0]) & (np.abs(points[:, 1]) <= FIELD[1])
            points = points[inside]
        rings.append(points)
    return np.vstack(rings)


def observe(
    targets: np.ndarray, optics: dict, per_target: int, rng: np.random.Generator
) -> np.ndarray:
    """The raw vector a block would actually record: `per_target` fixations at each
    target, each offset by the animal's own scatter, averaged."""
    noisy = np.repeat(targets, per_target, axis=0)
    noisy = noisy + rng.normal(0.0, FIXATION_NOISE_DEG, noisy.shape)
    raw = forward(noisy, **optics)
    return raw.reshape(len(targets), per_target, 2).mean(axis=1)


def field_error(
    targets: np.ndarray,
    optics: dict,
    per_target: int,
    rng: np.random.Generator,
    model: CalibrationModel = CalibrationModel.SECOND_ORDER,
    repeats: int = 60,
) -> tuple[float, float]:
    """(P95, RMS) error over the tested region and RMS residual at the targets.

    Both a P95 and an RMS, because they answer different questions and mixing
    them is the available mistake here: a residual is an RMS, so comparing it
    against a P95 manufactures a discrepancy out of the statistic alone."""
    region = tested_region()
    truth_raw = forward(region, **optics)
    p95s, rmss, residuals = [], [], []
    for _ in range(repeats):
        raw = observe(targets, optics, per_target, rng)
        coefficients = fit(raw, targets, model)
        residual = predict(raw, coefficients, model) - targets
        residuals.append(float(np.sqrt((residual**2).sum(axis=1).mean())))
        error = predict(truth_raw, coefficients, model) - region
        distance = np.sqrt((error**2).sum(axis=1))
        p95s.append(float(np.percentile(distance, 95)))
        rmss.append(float(np.sqrt((distance**2).mean())))
    return float(np.mean(p95s)), float(np.mean(rmss)), float(np.mean(residuals))


# ---------------------------------------------------------------------------
# The measurements.
# ---------------------------------------------------------------------------


def section_conditioning() -> None:
    print("## 1. Conditioning, and what it cannot see\n")
    print("Gate: %.2f affine, %.2f second-order.\n"
          % (MIN_CONDITIONING[CalibrationModel.AFFINE],
             MIN_CONDITIONING[CalibrationModel.SECOND_ORDER]))
    candidates = {
        "ring of 8": ring(8),
        "ring of 8 + centre": ring(8, centre=True),
        "3x3, spanning the field": grid(3),
        "3x3, 60% of the field": grid(3, reach=0.6),
        "3x3 @%s + 4 intermediates" % _pct(SHOWN_REACH): augmented(),
    }
    print("| constellation | affine | second-order | verdict |")
    print("|---|---|---|---|")
    for name, targets in candidates.items():
        affine = _conditioning(targets, CalibrationModel.AFFINE)
        second = _conditioning(targets, CalibrationModel.SECOND_ORDER)
        passes = second >= MIN_CONDITIONING[CalibrationModel.SECOND_ORDER]
        print("| %s | %.4f | %.4f | %s |"
              % (name, affine, second, "pass" if passes else "**REFUSED**"))


def section_honesty(rng: np.random.Generator) -> None:
    print("\n## 2. What the reported residual hides\n")
    print("`rms_residual_deg` is the number an operator judges a calibration by, and")
    print("the number that goes in the file `wl-preproc` reads. It is trustworthy")
    print("only when the targets span the region the task will test.\n")
    print("| constellation | residual at targets | true P95 over tested region | understated by |")
    print("|---|---|---|---|")
    for name, targets in {
        "ring of 8 + centre": ring(8, centre=True),
        "3x3, 60% of the field": grid(3, reach=0.6),
        "3x3, spanning the field": grid(3),
        "3x3 @%s + 4 intermediates" % _pct(SHOWN_REACH): augmented(),
    }.items():
        p95, _, residual = field_error(targets, OPTICS["moderate"], 10, rng)
        print("| %s | %.3f | %.3f | %.1fx |" % (name, residual, p95, p95 / residual))


def section_reach(rng: np.random.Generator) -> None:
    print("\n## 3. How far out the targets should reach\n")
    print("P95 error (deg) over the tested region, 3x3 grid, 11 fixations/target.\n")
    reaches = [0.6, 0.7, 0.75, 0.85, 1.0]
    print("| optics | " + " | ".join("%d%%" % (100 * r) for r in reaches) + " | best |")
    print("|---" * (len(reaches) + 2) + "|")
    for label, optics in OPTICS.items():
        values = [field_error(grid(3, reach=r), optics, 11, rng)[0] for r in reaches]
        best = reaches[int(np.argmin(values))]
        print("| %s | " % label + " | ".join("%.3f" % v for v in values)
              + " | **%d%%** |" % (100 * best))


def section_count(rng: np.random.Generator) -> None:
    print("\n## 4. Target count, at equal animal cost\n")
    budget = 130
    print("P95 error (deg) over the tested region; total fixations held at %d.\n" % budget)
    designs = {
        "3x3 @%s (9)" % _pct(SHOWN_REACH): grid(3, reach=SHOWN_REACH),
        "3x3 + intermediates @0.35 (13)": augmented(fraction=0.35),
        "3x3 + intermediates @0.50 (13)": augmented(fraction=0.50),
        "3x3 + intermediates @0.70 (13)": augmented(fraction=0.70),
        "3x3 + intermediates at corners (13)": augmented(fraction=1.00),
        "5x5 @%s (25)" % _pct(SHOWN_REACH): grid(5, reach=SHOWN_REACH),
    }
    print("| design | n | fix/target | " + " | ".join(OPTICS) + " |")
    print("|---" * (len(OPTICS) + 3) + "|")
    for name, targets in designs.items():
        per = max(1, budget // len(targets))
        values = [field_error(targets, o, per, rng)[0] for o in OPTICS.values()]
        print("| %s | %d | %d | " % (name, len(targets), per)
              + " | ".join("%.3f" % v for v in values) + " |")


def section_dropout(rng: np.random.Generator) -> None:
    print("\n## 5. Surviving targets the animal will not work\n")
    print("Percentage of random dropouts that still fit (>= %d points) and still pass"
          % n_terms(CalibrationModel.SECOND_ORDER))
    print("the %.2f gate. **This is the whole case for thirteen points.**\n"
          % MIN_CONDITIONING[CalibrationModel.SECOND_ORDER])
    designs = {
        "3x3 @%s (9)" % _pct(SHOWN_REACH): grid(3, reach=SHOWN_REACH),
        "3x3 + intermediates @0.50 (13)": augmented(fraction=0.50),
        "3x3 + intermediates @0.70 (13)": augmented(fraction=0.70),
    }
    losses = range(0, 6)
    print("| design | " + " | ".join("lose %d" % k for k in losses) + " |")
    print("|---" * (len(list(losses)) + 1) + "|")
    gate = MIN_CONDITIONING[CalibrationModel.SECOND_ORDER]
    for name, targets in designs.items():
        row = []
        for k in losses:
            trials, survived = 2000, 0
            for _ in range(trials):
                kept = targets
                if k:
                    keep = rng.choice(len(targets), len(targets) - k, replace=False)
                    kept = targets[keep]
                if len(kept) < n_terms(CalibrationModel.SECOND_ORDER):
                    continue
                if _conditioning(kept, CalibrationModel.SECOND_ORDER) >= gate:
                    survived += 1
            row.append("%.0f%%" % (100 * survived / trials))
        print("| %s | " % name + " | ".join(row) + " |")


def section_held_out(rng: np.random.Generator) -> None:
    print("\n## 6. Why the intermediates are fit points, not held-out points\n")
    print("Holding four of the thirteen out to estimate error was proposed and then")
    print("measured down. Four points at ten fixations each carry a noise floor of")
    print("about %.2f deg, which is the same size as the error being estimated, so the"
          % (FIXATION_NOISE_DEG / np.sqrt(10)))
    print("estimate cannot resolve it. `spread` is the standard deviation of the")
    print("held-out estimate across repeats of the SAME calibration: a gate whose")
    print("reading moves that much between identical sessions cannot be acted on.\n")
    fit_targets = grid(3, reach=SHOWN_REACH)
    test_targets = diagonals(SHOWN_REACH, 0.50)
    region = tested_region()
    print("| optics | held-out estimate | spread | true RMS | error |")
    print("|---|---|---|---|---|")
    for label, optics in OPTICS.items():
        held, true = [], []
        truth_raw = forward(region, **optics)
        for _ in range(60):
            raw = observe(fit_targets, optics, 10, rng)
            coefficients = fit(raw, fit_targets, CalibrationModel.SECOND_ORDER)
            test_raw = observe(test_targets, optics, 10, rng)
            error = predict(test_raw, coefficients, CalibrationModel.SECOND_ORDER) - test_targets
            held.append(np.sqrt((error**2).sum(axis=1).mean()))
            field = predict(truth_raw, coefficients, CalibrationModel.SECOND_ORDER) - region
            true.append(np.sqrt((field**2).sum(axis=1).mean()))
        h, sd, t = np.mean(held), np.std(held), np.mean(true)
        print("| %s | %.3f | +/-%.3f | %.3f | %+.0f%% |" % (label, h, sd, t, 100 * (h - t) / t))

    print("\nThe estimate is wrong by a similar margin whether the model fits the")
    print("optics or not, so the gap between residual and held-out does not")
    print("discriminate misfit either -- which was the reason to hold them out.")
    print("They do more good inside the fit, where section 5 shows what they buy.\n")


def section_recommended() -> None:
    print("\n## 7. The constellation this recommends\n")
    targets = augmented()
    print("%s: +/-%.2f deg horizontal, +/-%.2f deg vertical.\n" % (EXTENT, HALF_H, HALF_V))
    print("| role | x (deg) | y (deg) | eccentricity |")
    print("|---|---|---|---|")
    rows = [
        ("centre", 0.0, 0.0),
        ("edge, horizontal (x2)", abs(targets[:, 0]).max(), 0.0),
        ("edge, vertical (x2)", 0.0, abs(targets[:, 1]).max()),
        ("corner (x4)", abs(targets[:, 0]).max(), abs(targets[:, 1]).max()),
        ("intermediate (x4)", abs(targets[9:, 0]).max(), abs(targets[9:, 1]).max()),
    ]
    for label, x, y in rows:
        print("| %s | %.2f | %.2f | %.2f |" % (label, x, y, np.hypot(x, y)))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--setup", choices=sorted(SETUPS), default="2026-09-05")
    use(parser.parse_args(argv).setup)
    rng = np.random.default_rng(20260905)
    print("# Calibration constellation: measurements\n")
    print("Generated by `tools/calibration_design.py`. Do not edit the numbers by hand.\n")
    section_conditioning()
    section_honesty(rng)
    section_reach(rng)
    section_count(rng)
    section_dropout(rng)
    section_held_out(rng)
    section_recommended()


if __name__ == "__main__":
    main()
