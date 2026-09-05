"""Gaze calibration: our procedure, and our agreement with wl-preproc's model.

Split deliberately. The first half tests what is ours -- which targets to present,
what to refuse and why. The second half is a contract: `basis_row`, `conditioning`,
the model names, the thresholds and the file are all *theirs*, reimplemented here so
a task PC need not import a pipeline that pulls DataJoint behind it, and these tests
are the only thing standing between that reimplementation and a silent drift.
"""

from __future__ import annotations

import math
import os

import pytest

from wl_expcontroller.calibration import (
    MIN_CONDITIONING,
    RAW_DEFINITION,
    EyeMap,
    Fixation,
    GazeCalibration,
    Model,
    _yaml_float,
    basis_row,
    conditioning,
    constellation,
    fit_eye,
    n_terms,
)
from wl_expcontroller.geometry import Geometry

GEOMETRY = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)

#: A forward map the second-order basis can represent exactly, so a fit against it
#: should recover the coefficients rather than approximate them. Deliberately not
#: the simulator's optics: this tests the solver, not the physics.
_TRUE_X = (0.5, 2.0, 0.1, 0.02, -0.01, 0.005)
_TRUE_Y = (-0.25, 0.05, 1.8, -0.005, 0.03, 0.01)


def _fixations(targets, x=_TRUE_X, y=_TRUE_Y):
    """Fixations whose degrees are an exact second-order function of the raw."""
    out = []
    for t in targets:
        row = basis_row(t[0], t[1], Model.SECOND_ORDER)
        dx = sum(c * r for c, r in zip(x, row))
        dy = sum(c * r for c, r in zip(y, row))
        out.append(Fixation(raw=t, target=(dx, dy)))
    return tuple(out)


# ---------------------------------------------------------------------------
# The basis and the metric, against values written down independently
# ---------------------------------------------------------------------------
#
# These two do not compute their expectations with the code under test, and do not
# need the sibling checkout. That matters: the contract tests below are the stronger
# check, but they skip on a machine without `wl-preproc`, and a fit test that builds
# its own input with `basis_row` would agree with a mutated `basis_row` perfectly.


def test_basis_row_is_the_column_order_written_down():
    """Literal, hand-computed, and in the order coefficients are written to the
    file. Their reader does no re-ordering, so a permuted basis produces
    coefficients that are individually right and collectively wrong."""
    assert basis_row(2.0, 3.0, Model.SECOND_ORDER) == (1.0, 2.0, 3.0, 4.0, 9.0, 6.0)
    assert basis_row(2.0, 3.0, Model.AFFINE) == (1.0, 2.0, 3.0)
    assert basis_row(-1.5, 4.0, Model.SECOND_ORDER) == (1.0, -1.5, 4.0, 2.25, 16.0, -6.0)


def test_conditioning_reproduces_their_published_table_value():
    """`wl-preproc` published measured scores for real constellations: a 3x3 grid
    scores 0.2277 on the quadratic basis and 1.0000 on the affine one. Reproducing
    those exactly is what says our reimplementation is theirs, independently of
    whether their source is importable on this machine."""
    grid = tuple((float(x), float(y)) for x in (-1, 0, 1) for y in (-1, 0, 1))
    assert conditioning(grid, Model.SECOND_ORDER) == pytest.approx(0.2277, abs=5e-5)
    assert conditioning(grid, Model.AFFINE) == pytest.approx(1.0000, abs=5e-5)


def test_conditioning_is_invariant_to_where_the_origin_sits_and_to_scale():
    """Both properties are load-bearing on their side and easy to lose in a
    reimplementation. Without centring, `t²` approximates `c² + 2ct` far from the
    origin and an ordinary grid reads as degenerate for no reason but screen
    position; without column normalisation the raw columns run 1, ~100, ~10,000 and
    units dominate the measure entirely."""
    grid = tuple((float(x), float(y)) for x in (-1, 0, 1) for y in (-1, 0, 1))
    moved = tuple((7.0 * x + 40.0, 3.0 * y - 12.0) for x, y in grid)
    assert conditioning(moved, Model.SECOND_ORDER) == pytest.approx(
        conditioning(grid, Model.SECOND_ORDER), abs=1e-12
    )


# ---------------------------------------------------------------------------
# The constellation
# ---------------------------------------------------------------------------


def test_the_block_presents_thirteen_targets():
    assert len(constellation(GEOMETRY)) == 13


def test_the_grid_is_scaled_per_axis_because_the_field_is_not_square():
    """Each eye sees half the panel's width and its full height, so the viewport is
    taller than it is wide. A constellation square in degrees would waste the
    vertical extent, and asserting it here is what stops someone 'simplifying' the
    two scale factors into one."""
    targets = constellation(GEOMETRY)
    widest = max(abs(x) for x, _ in targets)
    tallest = max(abs(y) for _, y in targets)
    assert tallest > widest
    assert GEOMETRY.half_field_v_deg > GEOMETRY.half_field_h_deg


def test_every_target_is_inside_the_field_both_eyes_see():
    for x, y in constellation(GEOMETRY):
        assert GEOMETRY.can_show(x, y), f"({x:.2f}, {y:.2f}) is off the panel"


def test_the_constellation_conditions_the_second_order_basis():
    """The whole point of a grid over a ring. If this drops below the threshold the
    calibration block cannot reach second-order and every session falls to affine."""
    score = conditioning(constellation(GEOMETRY), Model.SECOND_ORDER)
    assert score >= MIN_CONDITIONING[Model.SECOND_ORDER]


def test_a_ring_cannot_carry_a_second_order_map():
    """Points on a circle satisfy dx²+dy²=r², so the constant and both square
    columns collapse. Eight points -- more than the six the model needs -- and the
    constellation still constrains it not at all."""
    ring = tuple(
        (10.0 * math.cos(a), 10.0 * math.sin(a))
        for a in [i * math.pi / 4 for i in range(8)]
    )
    assert conditioning(ring, Model.SECOND_ORDER) == pytest.approx(0.0, abs=1e-9)
    assert conditioning(ring, Model.AFFINE) > MIN_CONDITIONING[Model.AFFINE]


def test_the_constellation_survives_losing_four_targets():
    """Nine points fitting six parameters has three to spare; thirteen has seven.
    This is the entire reason the intermediates exist, so it is asserted rather
    than left to the measurement document."""
    targets = constellation(GEOMETRY)
    # Drop the four intermediates -- the worst realistic loss, since they are
    # presented last and an animal that quits, quits at the end.
    kept = targets[:9]
    assert len(kept) >= n_terms(Model.SECOND_ORDER)
    assert conditioning(kept, Model.SECOND_ORDER) >= MIN_CONDITIONING[Model.SECOND_ORDER]


# ---------------------------------------------------------------------------
# Fitting, and refusing
# ---------------------------------------------------------------------------


def test_a_clean_fit_recovers_the_coefficients():
    fixations = _fixations(constellation(GEOMETRY))
    eye, findings = fit_eye(fixations)
    assert eye is not None
    assert eye.model is Model.SECOND_ORDER
    assert [f.code for f in findings] == []
    assert eye.x == pytest.approx(_TRUE_X, abs=1e-9)
    assert eye.y == pytest.approx(_TRUE_Y, abs=1e-9)
    assert eye.rms_residual_deg == pytest.approx(0.0, abs=1e-9)
    assert eye.n_points == 13


def test_a_ring_forecloses_second_order_without_failing_outright():
    """The precise damage a ring does, and the reason it is dangerous rather than
    merely broken. Eight points on a circle condition the affine basis at 0.93 --
    perfectly usable -- while conditioning the quadratic at zero. So the fit does not
    fail; it silently drops a rung, which is why the fallback is reported."""
    ring = tuple(
        (10.0 * math.cos(a), 10.0 * math.sin(a))
        for a in [i * math.pi / 4 for i in range(8)]
    )
    eye, findings = fit_eye(_fixations(ring))
    assert eye is not None
    assert eye.model is Model.AFFINE
    assert [f.code for f in findings] == ["affine-fallback"]
    assert not findings[0].blocking


def test_a_constellation_that_carries_nothing_is_a_named_finding():
    """Collinear targets constrain neither basis. numpy's lstsq would return a
    minimum-norm solution for the rank-deficient design without complaining -- a map
    that looks like a map and maps nothing -- so the refusal has to come before the
    solve, and has to be named."""
    collinear = tuple((float(x), 2.0 * x) for x in range(-4, 4))
    eye, findings = fit_eye(_fixations(collinear))
    assert eye is None
    assert [f.code for f in findings] == ["degenerate-constellation"]
    assert findings[0].blocking
    assert "on a line" in findings[0].detail


def test_too_few_targets_is_caught_by_count_not_by_conditioning():
    """Their `fit_map` records why the order matters: four spread targets on a
    six-term basis score a healthy 0.2787 while the design is 4x6 and two dimensions
    are missing entirely. Count has to be checked first."""
    eye, findings = fit_eye(_fixations(((-5.0, -5.0), (5.0, 5.0))))
    assert eye is None
    assert [f.code for f in findings] == ["too-few-targets"]


def test_a_constellation_that_only_carries_affine_falls_back_and_says_so():
    """Five targets cannot reach the six-term basis. The fallback is legitimate and
    must not be silent: it roughly doubles the error, and an operator who does not
    know it happened cannot decide to recalibrate."""
    plus = ((0.0, 0.0), (-8.0, 0.0), (8.0, 0.0), (0.0, -8.0), (0.0, 8.0))
    eye, findings = fit_eye(_fixations(plus))
    assert eye is not None
    assert eye.model is Model.AFFINE
    assert [f.code for f in findings] == ["affine-fallback"]
    assert not findings[0].blocking


def test_extrapolation_beyond_the_targets_is_reported():
    """The one thing conditioning cannot see. A grid shrunk to 60% of the field
    scores identically to one spanning it, then understates its own error."""
    small = tuple((x * 0.4, y * 0.4) for x, y in constellation(GEOMETRY))
    eye, findings = fit_eye(_fixations(small), tested_eccentricity_deg=16.0)
    assert eye is not None
    assert "constellation-inside-tested-region" in [f.code for f in findings]
    assert not [f for f in findings if f.blocking]


def test_a_constellation_that_spans_the_tested_region_reports_nothing():
    fixations = _fixations(constellation(GEOMETRY))
    _, findings = fit_eye(fixations, tested_eccentricity_deg=16.0)
    assert [f.code for f in findings] == []


# ---------------------------------------------------------------------------
# Applying the map -- the trial-loop path
# ---------------------------------------------------------------------------


def test_the_map_applied_matches_the_map_fitted():
    fixations = _fixations(constellation(GEOMETRY))
    eye, _ = fit_eye(fixations)
    for fixation in fixations:
        assert eye.degrees(fixation.raw) == pytest.approx(fixation.target, abs=1e-9)


def test_an_affine_map_applies_with_three_coefficients():
    eye = EyeMap(Model.AFFINE, (1.0, 2.0, 3.0), (4.0, 5.0, 6.0), 1.0, 0.0, 3)
    assert eye.degrees((10.0, 100.0)) == (1.0 + 20.0 + 300.0, 4.0 + 50.0 + 600.0)


def test_a_map_whose_coefficients_do_not_match_its_model_is_refused():
    with pytest.raises(ValueError, match="takes 6 coefficients"):
        EyeMap(Model.SECOND_ORDER, (1.0, 2.0, 3.0), (1.0, 2.0, 3.0), 1.0, 0.0, 9)


# ---------------------------------------------------------------------------
# Serialising
# ---------------------------------------------------------------------------


def test_small_floats_are_written_so_yaml_reads_them_back_as_numbers():
    """PyYAML, which their reader uses, resolves `1e-17` to the *string* '1e-17' --
    YAML 1.1's float pattern requires a decimal point before the exponent. A
    quadratic coefficient that small is entirely ordinary."""
    assert _yaml_float(1e-17) == "1.0e-17"
    assert _yaml_float(-3e-05) == "-3.0e-05"
    assert _yaml_float(0.1) == "0.1"
    assert _yaml_float(2.0) == "2.0"


def test_a_non_finite_coefficient_is_refused_rather_than_written():
    with pytest.raises(ValueError, match="non-finite"):
        _yaml_float(float("nan"))


def test_the_file_names_the_raw_feature_their_reader_demands():
    text = GazeCalibration(1, constellation(GEOMETRY)).to_yaml()
    assert f'raw_definition: "{RAW_DEFINITION}"' in text


# ---------------------------------------------------------------------------
# Contract: wl-preproc's model, thresholds and reader
# ---------------------------------------------------------------------------

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"

try:
    import numpy as np

    from wl_preproc.eye import calibration as their_calibration
    from wl_preproc.eye.expcontroller import read_expcontroller_map
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). "
            f"These tests are the only thing proving our reimplementation of their "
            f"basis, their conditioning metric and their file format still agrees "
            f"with the originals; skipping them would report a compatibility nobody "
            f"verified"
        ) from exc
    their_calibration = None
    read_expcontroller_map = None

_contract = pytest.mark.skipif(
    their_calibration is None,
    reason="wl-preproc checkout not beside this repo; the contract cannot run",
)


@_contract
def test_our_model_names_are_their_model_names():
    """The values are written into the file and validated against their enum, so a
    spelling difference is a declined calibration, not a type error here."""
    assert {m.value for m in Model} == {m.value for m in their_calibration.CalibrationModel}


@_contract
def test_our_thresholds_are_their_thresholds():
    theirs = {m.value: v for m, v in their_calibration.MIN_CONDITIONING.items()}
    assert {m.value: v for m, v in MIN_CONDITIONING.items()} == theirs


@_contract
def test_our_term_counts_are_theirs():
    for model in Model:
        assert n_terms(model) == their_calibration.n_terms(
            their_calibration.CalibrationModel(model.value)
        )


@_contract
def test_our_basis_row_is_their_basis_column_for_column():
    """Column ORDER is the contract, not just column content: their reader does no
    re-ordering, so a permuted basis writes coefficients that are individually
    correct and collectively wrong."""
    rng = np.random.default_rng(20260905)
    points = rng.normal(0.0, 8.0, (40, 2))
    for model in Model:
        theirs = their_calibration.basis(
            points, their_calibration.CalibrationModel(model.value)
        )
        ours = np.array([basis_row(x, y, model) for x, y in points])
        assert ours == pytest.approx(theirs)


@_contract
def test_our_conditioning_is_their_conditioning():
    """Over ordinary constellations and the pathological ones, because the metric's
    value is in what it refuses."""
    rng = np.random.default_rng(7)
    cases = [
        constellation(GEOMETRY),
        constellation(GEOMETRY)[:9],
        tuple((10.0 * math.cos(a), 10.0 * math.sin(a))
              for a in [i * math.pi / 4 for i in range(8)]),
        tuple((x, 2.0 * x) for x in range(-4, 4)),  # collinear
        ((3.0, 3.0),) * 7,  # identical
        tuple((x + 40.0, y + 40.0) for x, y in constellation(GEOMETRY)),  # off-origin
    ]
    cases += [tuple(map(tuple, rng.normal(0.0, 9.0, (n, 2)))) for n in (6, 9, 13, 25)]
    for targets in cases:
        for model in Model:
            theirs = their_calibration._conditioning(
                np.asarray(targets, dtype=float),
                their_calibration.CalibrationModel(model.value),
            )
            assert conditioning(targets, model) == pytest.approx(theirs, abs=1e-12)


@_contract
def test_the_file_we_write_is_the_file_they_read(tmp_path):
    """The round trip that matters: our YAML, their parser, their `CalibrationMap`.
    Their model forbids extra fields at both levels, so an invented key is a
    declined file rather than an ignored one."""
    left, _ = fit_eye(_fixations(constellation(GEOMETRY)))
    right, _ = fit_eye(_fixations(constellation(GEOMETRY), x=_TRUE_Y, y=_TRUE_X))
    path = tmp_path / "calibration.yaml"
    path.write_text(GazeCalibration(3, constellation(GEOMETRY), left, right).to_yaml())

    online = read_expcontroller_map(path)
    assert online is not None, "their reader declined the file we wrote"
    assert online.left is not None and online.right is not None
    assert online.left.model.value == Model.SECOND_ORDER.value
    assert online.left.x == pytest.approx(_TRUE_X, abs=1e-9)
    assert online.left.y == pytest.approx(_TRUE_Y, abs=1e-9)
    assert online.right.x == pytest.approx(_TRUE_Y, abs=1e-9)


@_contract
def test_one_eye_alone_is_a_valid_file(tmp_path):
    """'A file offering a map for only one eye is fine' -- their review round 1.
    Tracking is often better on one side, and a session that loses the right eye
    must still deliver the left."""
    left, _ = fit_eye(_fixations(constellation(GEOMETRY)))
    path = tmp_path / "calibration.yaml"
    path.write_text(GazeCalibration(1, constellation(GEOMETRY), left=left).to_yaml())

    online = read_expcontroller_map(path)
    assert online is not None
    assert online.left is not None
    assert online.right is None


@_contract
def test_a_coefficient_small_enough_to_need_an_exponent_survives_the_round_trip(tmp_path):
    """The PyYAML float trap, proven end to end rather than only against the
    helper: a map whose quadratic terms are tiny is what a well-behaved camera
    produces, and it must not arrive as a list of strings."""
    tiny = (1e-17, 2.0, 3.0, -4.5e-18, 5e-20, 6.0)
    eye = EyeMap(Model.SECOND_ORDER, tiny, tiny, 0.3, 0.05, 13)
    path = tmp_path / "calibration.yaml"
    path.write_text(GazeCalibration(1, constellation(GEOMETRY), left=eye).to_yaml())

    online = read_expcontroller_map(path)
    assert online is not None, "their reader declined a file with exponent floats"
    assert online.left is not None
    assert all(isinstance(v, float) for v in online.left.x)
    assert online.left.x == pytest.approx(tiny)


@_contract
def test_they_decline_a_file_claiming_a_different_raw_feature(tmp_path):
    """Proves the refusal we depend on is real: if we ever fit against something
    other than P1-P4, honestly labelled coefficients must not be silently applied to
    their CR1-CR4 difference."""
    left, _ = fit_eye(_fixations(constellation(GEOMETRY)))
    text = GazeCalibration(1, constellation(GEOMETRY), left=left).to_yaml()
    text = text.replace(f'"{RAW_DEFINITION}"', '"P1 - P3"')
    path = tmp_path / "calibration.yaml"
    path.write_text(text)

    assert read_expcontroller_map(path) is None


def test_the_constellation_becomes_one_scheduler_condition_per_target():
    """Presenting the targets is ordinary block business -- no bespoke sequencer --
    so this asserts the translation rather than the sequencing."""
    from wl_expcontroller.calibration import conditions

    built = conditions(GEOMETRY, window_deg=3.0, hold_s=0.15, timeout_s=2.0, repeats=4)
    targets = constellation(GEOMETRY)

    assert len(built) == len(targets) == 13
    assert len({c.name for c in built}) == 13, "conditions are counted by name"
    assert [c.target for c in built] == [4] * 13
    assert [(c.values["target_x"], c.values["target_y"]) for c in built] == list(targets)
    for condition in built:
        assert condition.values["cal_window"] == 3.0
        assert condition.values["cal_hold"] == 0.15
        assert condition.values["fix_timeout"] == 2.0


def test_every_condition_supplies_every_parameter_the_task_declares():
    """A missing value is a task the runner cannot resolve, and the runner resolves
    lazily -- so the gap would surface as a trial that behaves oddly rather than one
    that refuses. Asserted against the task's own declarations so adding a parameter
    to the task without adding it here fails here."""
    from tasks.calibration import calibration as calibration_task
    from wl_expcontroller.calibration import conditions

    declared = {param.name for param in calibration_task.params}
    for condition in conditions(GEOMETRY, window_deg=3.0, hold_s=0.15, timeout_s=2.0):
        assert declared == set(condition.values), f"{condition.name} does not match"
