"""Gaze calibration: the raw Purkinje vector to degrees, per eye.

**The model is not ours.** `wl-preproc/wl_preproc/eye/calibration.py` fixed it before
this file existed -- `AFFINE` is `[1, dx, dy]`, `SECOND_ORDER` is
`[1, dx, dy, dx², dy², dx·dy]`, taken from OpenIrisDPI's own tutorial notebook -- and
`wl_preproc/eye/expcontroller.py` fixed the file we write it into. We supply the
*procedure*: which targets to present, how to refuse a constellation that cannot
carry the model, and how to serialise the result. Read their source before changing
anything here; their README does not describe it (CLAUDE.md, trap 1).

**We do not import theirs.** `wl-preproc` pulls DataJoint, Kilosort and SpikeInterface
behind it, none of which belongs on a task PC -- the same reasoning `tests/conftest.py`
records for the event codec. So `basis` and `conditioning` are reimplemented here and
`tests/test_calibration.py` proves them equal to theirs, function by function, over
random constellations. What we never write is a *reader*: reading the file back is
their side of the contract and a second reader would be a second definition.

**Fitting allocates; applying does not.** `fit_eye` runs at a block boundary and uses
numpy freely. `EyeMap.degrees` runs on every gaze sample inside the trial loop, so it
is six multiplies and five adds on plain floats, with no array, no allocation and no
branch on model beyond a stored length (CLAUDE.md, hot-path discipline).

**Three refusals, and the order matters.** Point count is checked *before*
conditioning, because conditioning is structurally blind to under-determination:
their `fit_map` docstring records four spread targets against a six-term basis
scoring a healthy 0.2787 while the design is 4x6 and two dimensions are simply
missing. Conditioning is checked before the fit, so a degenerate constellation is a
named finding rather than a singular matrix. And extent is reported after both,
because it is the one thing conditioning *cannot* see -- being scale-invariant by
design -- and it is the difference between a calibration that is honest about its own
error and one that understates it. See
`docs/measurements/dev-machine/2026-09-05-calibration-constellation.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from wl_expcontroller.findings import Finding
from wl_expcontroller.geometry import Geometry

#: What `raw_definition` must say in the file. Their reader refuses any other value
#: rather than silently misapplying coefficients fit against a different feature --
#: `CR1`/`CR4` are ohDPI's names for the Purkinje images `eye.EyeReading.dpi`
#: subtracts as P1 and P4. Same signal, their spelling, because it is their field.
RAW_DEFINITION = "CR1 - CR4"


class Model(StrEnum):
    """Mirrors `wl_preproc.eye.calibration.CalibrationModel`. The *values* are the
    contract -- they are written into the file and validated against their enum --
    so a test asserts these strings equal theirs rather than trusting the spelling.
    """

    AFFINE = "affine"
    SECOND_ORDER = "second_order"


def n_terms(model: Model) -> int:
    """How many coefficients `model` has per axis."""
    return 6 if model is Model.SECOND_ORDER else 3


#: Theirs, mirrored, and asserted equal in the contract tests. Per model because a
#: threshold measured against a three-point affine means something different on a
#: six-term basis.
MIN_CONDITIONING: dict[Model, float] = {
    Model.AFFINE: 0.05,
    Model.SECOND_ORDER: 0.10,
}


def basis_row(dx: float, dy: float, model: Model) -> tuple[float, ...]:
    """One row of the design matrix, in the column order the file is written in.

    Their `basis()` builds this for a whole array; this is the single-row form the
    hot path needs and the fit reuses, so there is one statement of the column order
    rather than two that can disagree.
    """
    if model is Model.SECOND_ORDER:
        return (1.0, dx, dy, dx * dx, dy * dy, dx * dy)
    return (1.0, dx, dy)


def conditioning(targets: tuple[tuple[float, float], ...], model: Model) -> float:
    """How well a constellation constrains `model`: smallest over largest singular
    value of its mean-centred, column-normalised basis expansion.

    A faithful reimplementation of their `_conditioning`, including the three
    properties their docstring calls load-bearing. **Centring is not optional**: far
    from the origin `t²` is approximately `c² + 2ct`, so the square columns become
    near-linear combinations of the constant and linear ones and an ordinary
    constellation reads as degenerate for no reason but where the screen origin sits.
    **Normalisation is not optional either**: the raw columns run 1, ~100, ~10,000
    and units would otherwise dominate the measure entirely.

    Called on the TARGET positions, never the raw signal. A well-spread raw cloud
    from a single target location is noise, not information, and scores well while
    least squares returns coefficients mapping every sample in the session onto one
    point.
    """
    points = np.asarray(targets, dtype=float)
    centred = points - points.mean(axis=0)
    design = np.array([basis_row(dx, dy, model) for dx, dy in centred], dtype=float)
    norms = np.linalg.norm(design, axis=0)
    norms[norms == 0] = 1.0
    singular = np.linalg.svd(design / norms, compute_uv=False)
    return 0.0 if singular[0] <= 0 else float(singular[-1] / singular[0])


@dataclass(frozen=True, slots=True)
class Fixation:
    """One target's worth of gaze: the raw vector the animal held while that target
    was on screen, already averaged over the fixations it gave to it.

    Averaging happens before this type, in the calibration block, because how many
    fixations a target got and which were accepted is the block's business. What
    reaches the fit is one pairing per target.
    """

    #: `eye.EyeReading.dpi()` -- P1 minus P4, in camera pixels.
    raw: tuple[float, float]
    #: Where the target was, in degrees, cyclopean.
    target: tuple[float, float]


@dataclass(frozen=True, slots=True)
class EyeMap:
    """One eye's map, and how it was fit.

    `conditioning` and `rms_residual_deg` describe *this* fit and are written into
    the file. Their reader validates and then discards both, deliberately -- their
    `CalibrationMap` reserves those columns for maps THEY fit and will not
    misreport ours into them. They are still worth writing: they are what an
    operator judges a calibration by.
    """

    model: Model
    #: In `basis_row` column order. Written to the file in this order, because their
    #: reader does no re-ordering -- it defines the wire format and we write to it.
    x: tuple[float, ...]
    y: tuple[float, ...]
    conditioning: float
    rms_residual_deg: float
    n_points: int

    def __post_init__(self) -> None:
        expected = n_terms(self.model)
        if len(self.x) != expected or len(self.y) != expected:
            raise ValueError(
                f"{self.model.value} takes {expected} coefficients per axis, "
                f"got {len(self.x)} for x and {len(self.y)} for y"
            )

    def degrees(self, raw: tuple[float, float]) -> tuple[float, float]:
        """Raw Purkinje vector to degrees. **Trial-loop hot path**: no allocation
        beyond the returned tuple, no numpy, no per-sample branch on the model."""
        dx, dy = raw
        cx, cy = self.x, self.y
        if len(cx) == 6:
            terms = (1.0, dx, dy, dx * dx, dy * dy, dx * dy)
            return (
                cx[0] + cx[1] * dx + cx[2] * dy
                + cx[3] * terms[3] + cx[4] * terms[4] + cx[5] * terms[5],
                cy[0] + cy[1] * dx + cy[2] * dy
                + cy[3] * terms[3] + cy[4] * terms[4] + cy[5] * terms[5],
            )
        return (
            cx[0] + cx[1] * dx + cx[2] * dy,
            cy[0] + cy[1] * dx + cy[2] * dy,
        )


def fit_eye(
    fixations: tuple[Fixation, ...],
    tested_eccentricity_deg: float | None = None,
) -> tuple[EyeMap | None, list[Finding]]:
    """One eye's map, or `None` and the reason.

    Reaches for `SECOND_ORDER` and falls back to `AFFINE`, because which rung a
    session reaches is decided by the constellation the animal actually worked, not
    by what was presented. A fallback is reported (non-blocking) rather than
    silently taken: it roughly doubles the error, and an operator who does not know
    it happened cannot decide to recalibrate.
    """
    findings: list[Finding] = []
    targets = tuple(f.target for f in fixations)

    # Count first. Conditioning cannot see under-determination -- four spread
    # targets on a six-term basis score a healthy 0.2787 against a 4x6 design.
    if len(fixations) < n_terms(Model.AFFINE):
        findings.append(
            Finding(
                "too-few-targets",
                f"{len(fixations)} target(s) worked; even an affine map needs "
                f"{n_terms(Model.AFFINE)}. No map is produced for this eye",
            )
        )
        return None, findings

    model = None
    for candidate in (Model.SECOND_ORDER, Model.AFFINE):
        if len(fixations) < n_terms(candidate):
            continue
        score = conditioning(targets, candidate)
        if score >= MIN_CONDITIONING[candidate]:
            model = candidate
            break

    if model is None:
        second = conditioning(targets, Model.SECOND_ORDER)
        affine = conditioning(targets, Model.AFFINE)
        findings.append(
            Finding(
                "degenerate-constellation",
                f"{len(fixations)} targets condition the second-order basis at "
                f"{second:.4f} and the affine basis at {affine:.4f}, against minima "
                f"of {MIN_CONDITIONING[Model.SECOND_ORDER]:.2f} and "
                f"{MIN_CONDITIONING[Model.AFFINE]:.2f}. Targets on a line carry "
                f"neither basis; targets on a circle carry the affine one and never "
                f"the quadratic, since dx²+dy²=r² collapses the constant and both "
                f"square columns together",
            )
        )
        return None, findings

    if model is Model.AFFINE:
        findings.append(
            Finding(
                "affine-fallback",
                f"{len(fixations)} targets reached only the affine rung; the "
                f"second-order basis conditioned at "
                f"{conditioning(targets, Model.SECOND_ORDER):.4f} against a "
                f"{MIN_CONDITIONING[Model.SECOND_ORDER]:.2f} minimum",
                blocking=False,
            )
        )

    raw = np.array([f.raw for f in fixations], dtype=float)
    degrees = np.array([f.target for f in fixations], dtype=float)
    design = np.array([basis_row(dx, dy, model) for dx, dy in raw], dtype=float)
    coefficients, *_ = np.linalg.lstsq(design, degrees, rcond=None)

    residual = design @ coefficients - degrees
    rms = float(np.sqrt((residual**2).sum(axis=1).mean()))

    outer = max(math.hypot(*t) for t in targets)
    if tested_eccentricity_deg is not None and outer < tested_eccentricity_deg:
        findings.append(
            Finding(
                "constellation-inside-tested-region",
                f"targets reach {outer:.2f} deg but windows can land out to "
                f"{tested_eccentricity_deg:.2f} deg, so gaze beyond {outer:.2f} deg "
                f"is extrapolated and the {rms:.3f} deg residual understates the "
                f"error there. Conditioning cannot see this -- it is scale-invariant "
                f"by construction, and scores a shrunken grid exactly as it scores "
                f"one that spans the field",
                blocking=False,
            )
        )

    return (
        EyeMap(
            model=model,
            x=tuple(float(v) for v in coefficients[:, 0]),
            y=tuple(float(v) for v in coefficients[:, 1]),
            conditioning=conditioning(targets, model),
            rms_residual_deg=rms,
            n_points=len(fixations),
        ),
        findings,
    )


def _yaml_float(value: float) -> str:
    """A float in a form YAML 1.1 reads back as a float.

    **Verified against PyYAML, which is what their reader uses:**
    `yaml.safe_load("a: 1e-17")` returns the *string* `'1e-17'`, because YAML 1.1's
    float pattern requires a decimal point before the exponent. A quadratic
    coefficient small enough to render that way is entirely ordinary, so emitting
    `repr()` directly would put a string where their `list[float]` expects a number
    and lean on pydantic's coercion to rescue it. This inserts the point instead.
    """
    if not math.isfinite(value):
        raise ValueError(
            f"{value!r} cannot be written to a calibration file; their reader takes "
            f"float and a non-finite coefficient is a failed fit, not a map"
        )
    text = repr(float(value))
    if "e" in text and "." not in text:
        mantissa, exponent = text.split("e")
        text = f"{mantissa}.0e{exponent}"
    elif "e" not in text and "." not in text:
        text = f"{text}.0"
    return text


@dataclass(frozen=True, slots=True)
class GazeCalibration:
    """A session's map, in the shape `wl_preproc.eye.expcontroller` reads.

    `targets` is file-wide and `left`/`right` are independent, matching their reader
    exactly: one constellation was presented, and whether it produced a usable fit
    for one eye or both is a separate fact per eye. A session with a good left and a
    tracking failure on the right is an ordinary outcome, not a broken file.
    """

    mapping_version: int
    #: The constellation presented, in degrees -- not the subset either eye worked.
    targets: tuple[tuple[float, float], ...]
    left: EyeMap | None = None
    right: EyeMap | None = None

    def to_yaml(self) -> str:
        """The file. Written by hand rather than through a YAML library, for the
        reason `encode.py` gives about the codec: the schema is theirs, fixed, and
        tiny, and the round-trip test runs against their real reader. What that buys
        is one fewer dependency on a task PC. What it costs is that every field name
        below must match `_ExpcontrollerCalibration`, which forbids extras at both
        levels -- so an invented field is a declined file, and the contract test is
        what stops that reaching a session."""
        lines = [
            f"mapping_version: {self.mapping_version}",
            f'raw_definition: "{RAW_DEFINITION}"',
            "targets:",
        ]
        lines += [
            f"- [{_yaml_float(x)}, {_yaml_float(y)}]" for x, y in self.targets
        ]
        for name, eye in (("left", self.left), ("right", self.right)):
            if eye is None:
                continue
            lines += [
                f"{name}:",
                f"  model: {eye.model.value}",
                "  coefficients:",
                "    x: [" + ", ".join(_yaml_float(v) for v in eye.x) + "]",
                "    y: [" + ", ".join(_yaml_float(v) for v in eye.y) + "]",
                f"  conditioning: {_yaml_float(eye.conditioning)}",
                f"  rms_residual_deg: {_yaml_float(eye.rms_residual_deg)}",
            ]
        return "\n".join(lines) + "\n"


#: Fractions of the per-eye half-field. Measured, not chosen: see
#: `docs/measurements/dev-machine/2026-09-05-calibration-constellation.md`.
#: `REACH` at 0.75 beat 0.6, 0.7, 0.85 and 1.0 under every optics assumption swept --
#: pushing targets to the panel edge is worse than pulling them in, because the
#: corners sit outside the disc any task uses and their leverage drags the quadratic
#: away from where stimuli actually go. `INTERMEDIATE` at 0.5 beat 0.35, 0.7 and 1.0
#: on dropout survival and conditioning, at identical accuracy.
MARGIN = 0.85
REACH = 0.75
INTERMEDIATE = 0.50


def constellation(
    geometry: Geometry,
    reach: float = REACH,
    intermediate: float = INTERMEDIATE,
    margin: float = MARGIN,
) -> tuple[tuple[float, float], ...]:
    """The thirteen targets the calibration block presents, in degrees.

    A 3x3 grid plus four intermediates on the diagonals, scaled to each axis of the
    per-eye field separately -- which is **taller than it is wide**, because
    splitting the panel halves each eye's width and keeps its full height. A grid
    square in degrees would be the wrong shape for it.

    **Thirteen rather than nine buys survival, not accuracy.** At equal animal cost
    the two are indistinguishable. Nine points fitting six parameters has three to
    spare: lose four targets and the second-order fit is not ill-conditioned, it is
    impossible, and the session drops to affine. Thirteen survive losing five 95% of
    the time.

    **Never a ring.** Points on a circle satisfy dx²+dy²=r² exactly, so a ring of
    eight scores 0.0000 on the quadratic basis however many points it has. A ring
    plus a centre is worse than it looks rather than degenerate -- it passes the gate
    at 0.1697 while leaving the radial term resting on a single contrast.
    """
    half_h = geometry.half_field_h_deg * margin
    half_v = geometry.half_field_v_deg * margin
    outer_x, outer_y = reach * half_h, reach * half_v
    inner_x, inner_y = intermediate * outer_x, intermediate * outer_y

    targets = [
        (sx * outer_x, sy * outer_y)
        for sx in (-1.0, 0.0, 1.0)
        for sy in (-1.0, 0.0, 1.0)
    ]
    targets += [
        (sx * inner_x, sy * inner_y) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)
    ]
    return tuple(targets)
