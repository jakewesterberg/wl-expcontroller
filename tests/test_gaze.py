"""Replayed OpenIrisDPI samples reaching a `Window` test in degrees.

This is P6's exit condition, and the reason it is one test file rather than three:
`eye` parsing correctly, `calibration` fitting correctly and `run` looping correctly
were each already true separately, and none of that proves an animal's gaze reaches a
criterion. The path has four joints and every one of them is somewhere a sign, a unit
or a clock can be wrong without any single module being wrong.
"""

from __future__ import annotations

import json

import pytest

from wl_expcontroller.calibration import (
    Collector,
    conditions,
    EyeMap,
    Fixation,
    Mapping,
    MappingLog,
    Model,
    constellation,
    fit_eye,
)
from wl_expcontroller.eye import Replay, Tracker, parse
from wl_expcontroller.gaze import Tracked
from wl_expcontroller.geometry import Geometry
from wl_expcontroller.run import run_trial
from wl_expcontroller.scheduler import Block, Scheduler
from wl_expcontroller.task import Outcome, SaccadeTo
from tasks.calibration import calibration

GEOMETRY = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)
TARGETS = constellation(GEOMETRY)

#: A camera whose raw vector is a plain affine function of gaze, so a test can state
#: where the animal is looking in degrees and know what the tracker would report.
#: Deliberately affine and not the design tool's optics: this exercises the join, not
#: the physics, and a second copy of the physics here would drift from that one.
_SCALE_X, _SCALE_Y = 4.0, -3.5
_ORIGIN_X, _ORIGIN_Y = 300.0, 230.0


def _raw_for(x_deg: float, y_deg: float) -> tuple[float, float]:
    return (_ORIGIN_X + _SCALE_X * x_deg, _ORIGIN_Y + _SCALE_Y * y_deg)


def _payload(x_deg: float, y_deg: float, frame: int = 1) -> str:
    """What OpenIrisDPI would emit for an animal looking there.

    P1 carries the signal and P4 sits at a fixed offset, so `dpi()` -- their
    difference -- is `_raw_for` exactly. Building the payload rather than the
    `Sample` keeps the parser in the path: a unit or an index error in `eye.parse`
    is precisely the sort of thing this test exists to catch.
    """
    p1x, p1y = _raw_for(x_deg, y_deg)
    p4x, p4y = 0.0, 0.0
    eye = {
        "FrameNumber": frame,
        "Pupil": {"Center": {"X": p1x, "Y": p1y}, "Size": {"Width": 30.0, "Height": 28.0}},
        "CRs": [
            {"X": p1x, "Y": p1y},
            {"X": 0.0, "Y": 0.0},
            {"X": 0.0, "Y": 0.0},
            {"X": p4x, "Y": p4y},
        ],
    }
    return json.dumps({"Left": eye, "Right": dict(eye)})


def _fitted_mapping(version: int = 1) -> Mapping:
    """A map fit from the reference constellation, through the real fit."""
    fixations = tuple(
        Fixation(raw=_raw_for(x, y), target=(x, y)) for x, y in TARGETS
    )
    eye_map, findings = fit_eye(fixations)
    assert eye_map is not None and not [f for f in findings if f.blocking]
    return Mapping(version=version, targets=TARGETS, left=eye_map, right=eye_map)


def _tracker_at(x_deg: float, y_deg: float, at: float = 0.0) -> Tracker:
    tracker = Tracker()
    tracker.accept(parse(_payload(x_deg, y_deg), at=at))
    return tracker


# ---------------------------------------------------------------------------
# The path, joint by joint
# ---------------------------------------------------------------------------


def test_a_replayed_payload_becomes_degrees():
    """Parser, `dpi()`, fit and map, in one line. An affine camera is recoverable
    exactly, so anything but an exact answer is a defect rather than noise."""
    mapping = _fitted_mapping()
    world = Tracked(_tracker_at(6.0, -4.0), mapping, calibration, frame_period=0.008)

    assert world.gaze("left", frame=0) == pytest.approx((6.0, -4.0), abs=1e-6)
    assert world.gaze("right", frame=0) == pytest.approx((6.0, -4.0), abs=1e-6)


def test_gaze_in_degrees_decides_a_window():
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_timeout": 3.0, "cal_hold": 0.2}
    mapping = _fitted_mapping()

    inside = Tracked(_tracker_at(6.0, -4.0), mapping, calibration, 0.008, values)
    assert inside.in_window("cal", frame=0)

    # Just outside the 2 deg radius, on the diagonal: 2.5 deg away.
    outside = Tracked(_tracker_at(7.77, -5.77), mapping, calibration, 0.008, values)
    assert not outside.in_window("cal", frame=0)


def test_a_window_is_missed_when_the_map_is_the_wrong_one():
    """The failure this whole path exists to make visible. Uncalibrated gaze lands
    somewhere plausible and the trial scores as behaviour, not as a rig fault."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_timeout": 3.0, "cal_hold": 0.2}
    wrong = Mapping(
        version=1,
        targets=TARGETS,
        left=EyeMap(Model.AFFINE, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1.0, 0.0, 13),
        right=EyeMap(Model.AFFINE, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1.0, 0.0, 13),
    )
    world = Tracked(_tracker_at(6.0, -4.0), wrong, calibration, 0.008, values)
    assert not world.in_window("cal", frame=0)


def test_before_the_first_sample_gaze_is_unavailable_not_centred():
    """`Tracker.state` refuses to report (0, 0) at startup; this asserts the refusal
    survives the join. A world reporting the origin would put gaze exactly on a
    centre target and score a hold against an empty chair."""
    world = Tracked(Tracker(), _fitted_mapping(), calibration, 0.008,
                    {"target_x": 0.0, "target_y": 0.0, "cal_window": 3.0,
                     "fix_timeout": 3.0, "cal_hold": 0.2})
    assert world.gaze("left", frame=0) is None
    assert world.signal(frame=0) == "lost"
    assert not world.in_window("cal", frame=0)


def test_a_stale_sample_is_not_a_position():
    """The staleness ceiling belongs to `Tracker` and is not re-derived here. At
    8 ms a frame, the 50 ms default expires part-way through frame 7."""
    world = Tracked(_tracker_at(0.0, 0.0, at=0.0), _fitted_mapping(), calibration, 0.008,
                    {"target_x": 0.0, "target_y": 0.0, "cal_window": 3.0,
                     "fix_timeout": 3.0, "cal_hold": 0.2})
    assert world.in_window("cal", frame=6)
    assert world.signal(frame=6) == "ok"
    assert not world.in_window("cal", frame=7)
    assert world.signal(frame=7) == "lost"


def test_an_eye_without_a_map_reports_no_gaze():
    mapping = Mapping(version=1, targets=TARGETS, left=_fitted_mapping().left, right=None)
    world = Tracked(_tracker_at(3.0, 3.0), mapping, calibration, 0.008)
    assert world.gaze("left", frame=0) is not None
    assert world.gaze("right", frame=0) is None


def test_version_zero_maps_nothing():
    """A session before its calibration block. Asked for degrees it answers `None`,
    which is what stops an uncalibrated session silently scoring windows."""
    log = MappingLog(TARGETS)
    world = Tracked(_tracker_at(0.0, 0.0), log.current, calibration, 0.008,
                    {"target_x": 0.0, "target_y": 0.0, "cal_window": 3.0,
                     "fix_timeout": 3.0, "cal_hold": 0.2})
    assert world.mapping_version == 0
    assert world.gaze("left", frame=0) is None
    assert not world.in_window("cal", frame=0)


def test_a_saccade_guard_refuses_rather_than_scoring_a_miss():
    """There is no saccade detector yet. `False` would be indistinguishable from an
    animal that did not saccade, and every saccade-contingent trial would score as a
    miss that reads as behaviour."""
    world = Tracked(_tracker_at(0.0, 0.0), _fitted_mapping(), calibration, 0.008)
    with pytest.raises(NotImplementedError, match="S5"):
        world.happened(SaccadeTo("cal"), state="hold", frame=3)


# ---------------------------------------------------------------------------
# End to end: a calibration trial, scored from replayed gaze
# ---------------------------------------------------------------------------


def test_a_calibration_trial_is_scored_from_replayed_gaze():
    """P6's exit condition. Payloads in, `CORRECT` out, through the parser, the
    tracker, a fitted map, the window geometry and the trial loop."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_timeout": 2.0, "cal_hold": 0.1}
    frame_period = 0.008
    world = Tracked(
        Tracker(),
        _fitted_mapping(),
        calibration,
        frame_period,
        values,
        source=Replay(payloads=[(0.0, _payload(6.0, -4.0, frame=n)) for n in range(400)]),
    )

    result = run_trial(calibration, world, frame_period, values=values)
    assert result.outcome is Outcome.CORRECT


def test_a_calibration_trial_aborts_when_the_animal_looks_elsewhere():
    """The same path, with the animal looking well away from the target.
    `NO_FIXATION` rather than `CORRECT` is what says the window test is actually
    being applied rather than passing everything."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_timeout": 0.5, "cal_hold": 0.1}
    frame_period = 0.008
    world = Tracked(
        Tracker(),
        _fitted_mapping(),
        calibration,
        frame_period,
        values,
        source=Replay(payloads=[(0.0, _payload(-6.0, 6.0, frame=n)) for n in range(400)]),
    )

    result = run_trial(calibration, world, frame_period, values=values)
    assert result.outcome is Outcome.NO_FIXATION


def test_a_tracker_that_stops_delivering_is_equipment_not_behaviour():
    """The source runs dry part-way through the hold. That has to reach the loop as
    `TRACKER_LOST`, not as a fixation break: scoring a dropped camera as the animal
    looking away inflates a session's break rate with equipment failure, invisibly."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_timeout": 3.0, "cal_hold": 2.0}
    frame_period = 0.008
    world = Tracked(
        Tracker(),
        _fitted_mapping(),
        calibration,
        frame_period,
        values,
        source=Replay(payloads=[(0.0, _payload(6.0, -4.0, frame=n)) for n in range(20)]),
    )

    result = run_trial(calibration, world, frame_period, values=values)
    assert result.outcome is Outcome.TRACKER_LOST


# ---------------------------------------------------------------------------
# The collector, and the versioned map
# ---------------------------------------------------------------------------


def test_the_collector_fits_both_eyes_from_held_fixations():
    collector = Collector()
    for x, y in TARGETS:
        assert collector.accept((x, y), [parse(_payload(x, y), at=0.0)])

    left, right, findings = collector.fit()
    assert left is not None and right is not None
    assert left.model is Model.SECOND_ORDER
    assert [f for f in findings if f.blocking] == []
    assert left.n_points == 13


def test_a_target_worked_twice_still_counts_once():
    """`fit_eye` weights by target, so a target the scheduler happened to present
    twice would otherwise pull the fit toward wherever the animal was asked twice."""
    collector = Collector()
    for x, y in TARGETS:
        collector.accept((x, y), [parse(_payload(x, y), at=0.0)])
    collector.accept(TARGETS[0], [parse(_payload(*TARGETS[0]), at=0.0)])

    assert len(collector.fixations("left")) == 13


def test_a_target_with_too_few_samples_is_declined():
    collector = Collector(minimum_samples=3)
    assert not collector.accept((0.0, 0.0), [parse(_payload(0.0, 0.0), at=0.0)])
    assert collector.fixations("left") == ()


def test_the_collector_averages_the_samples_it_is_given():
    collector = Collector()
    collector.accept(
        (2.0, 2.0),
        [parse(_payload(1.0, 1.0), at=0.0), parse(_payload(3.0, 3.0), at=0.0)],
    )
    (fixation,) = collector.fixations("left")
    assert fixation.raw == pytest.approx(_raw_for(2.0, 2.0))


def test_the_map_is_versioned_and_every_change_is_logged():
    log = MappingLog(TARGETS)
    assert log.version == 0

    fitted = _fitted_mapping().left
    log.install(at=100.0, targets=TARGETS, left=fitted, right=fitted, why="block 1")
    assert log.version == 1

    log.recenter(at=250.0, left=(0.5, -0.25), right=(0.5, -0.25), why="chair shifted")
    assert log.version == 2
    assert [c.why for c in log.changes] == ["block 1", "chair shifted"]
    assert [c.at for c in log.changes] == [100.0, 250.0]

    # Reconstructible after the fact, which is the point of keeping versions.
    assert log.at_version(1).offsets == ((0.0, 0.0), (0.0, 0.0))
    assert log.at_version(2).offsets == ((0.5, -0.25), (0.5, -0.25))


def test_recentering_shifts_gaze_without_refitting():
    fitted = _fitted_mapping().left
    log = MappingLog(TARGETS)
    log.install(at=0.0, targets=TARGETS, left=fitted, right=fitted)
    before = Tracked(_tracker_at(3.0, 3.0), log.current, calibration, 0.008)
    assert before.gaze("left", 0) == pytest.approx((3.0, 3.0), abs=1e-6)

    log.recenter(at=1.0, left=(0.5, -0.25), right=(0.5, -0.25))
    after = Tracked(_tracker_at(3.0, 3.0), log.current, calibration, 0.008)
    assert after.gaze("left", 0) == pytest.approx((3.5, 2.75), abs=1e-6)
    # The coefficients themselves are untouched, so the correction is reversible.
    assert log.current.left.x == fitted.x


def test_recentering_replaces_rather_than_accumulates():
    """Two recenterings are two statements about where the animal is now. The
    second was measured against gaze the first had already corrected, so adding
    them applies the first twice."""
    fitted = _fitted_mapping().left
    log = MappingLog(TARGETS)
    log.install(at=0.0, targets=TARGETS, left=fitted, right=fitted)
    log.recenter(at=1.0, left=(0.5, 0.0), right=(0.5, 0.0))
    log.recenter(at=2.0, left=(0.2, 0.0), right=(0.2, 0.0))

    world = Tracked(_tracker_at(3.0, 3.0), log.current, calibration, 0.008)
    assert world.gaze("left", 0) == pytest.approx((3.2, 3.0), abs=1e-6)


def test_a_refit_drops_the_offset():
    """A recentering describes a chair position under the map it was measured
    against. Carrying it across a refit applies a correction the new fit already
    contains."""
    fitted = _fitted_mapping().left
    log = MappingLog(TARGETS)
    log.install(at=0.0, targets=TARGETS, left=fitted, right=fitted)
    log.recenter(at=1.0, left=(3.0, 3.0), right=(3.0, 3.0))
    log.install(at=2.0, targets=TARGETS, left=fitted, right=fitted, why="block 2")

    assert log.current.offsets == ((0.0, 0.0), (0.0, 0.0))


def test_recentering_without_a_map_is_refused():
    with pytest.raises(ValueError, match="no map to recenter"):
        MappingLog(TARGETS).recenter(at=1.0, left=(1.0, 0.0))


def test_the_offset_is_folded_into_the_file_because_their_schema_has_no_room():
    """Their model forbids fields it does not declare, so a recentered map has to
    reach the file as coefficients. Folding into the constant is exact for an
    additive offset; what is lost is that a recentering happened, and that survives
    in the change log."""
    fitted = _fitted_mapping().left
    log = MappingLog(TARGETS)
    log.install(at=0.0, targets=TARGETS, left=fitted, right=fitted)
    log.recenter(at=1.0, left=(0.5, -0.25), right=(0.0, 0.0))

    written = log.current.as_calibration()
    assert written.left.x[0] == pytest.approx(fitted.x[0] + 0.5)
    assert written.left.y[0] == pytest.approx(fitted.y[0] - 0.25)
    assert written.left.x[1:] == fitted.x[1:]
    assert written.right.x[0] == pytest.approx(fitted.x[0])
    assert written.mapping_version == 2


# ---------------------------------------------------------------------------
# A whole calibration block, from scheduled targets to an installed map
# ---------------------------------------------------------------------------


def test_a_whole_calibration_block_produces_an_installed_map():
    """Every piece of P6 at once: the scheduler walks the constellation, the task
    scores each target from replayed gaze, the collector averages what was held, the
    fit runs, and the result is installed as a new mapping version.

    This is the shape the `taskd` driver has to take, written as a test because
    `taskd` is still a spine and wiring a calibration block into a real session is
    P4b's. Until then this is what says the pieces compose -- each was tested alone,
    and alone none of them proves an animal's gaze becomes a map.
    """
    frame_period = 0.008
    block = Block(
        name="calibration",
        conditions=conditions(
            GEOMETRY, window_deg=3.0, hold_s=0.1, timeout_s=1.0, repeats=2
        ),
    )
    scheduler = Scheduler(blocks=[block], seed=11)
    collector = Collector()
    log = MappingLog(TARGETS)

    # Version 0 maps nothing, so the block cannot be scored through the map it is
    # about to produce. A calibration window is sized for that: wide enough to admit
    # gaze that is wrong by the amount calibration is about to correct.
    bootstrap = _fitted_mapping()

    trials = 0
    while not scheduler.finished and trials < 200:
        condition = scheduler.next_trial()
        trials += 1
        target = (condition.values["target_x"], condition.values["target_y"])
        world = Tracked(
            Tracker(),
            bootstrap,
            calibration,
            frame_period,
            condition.values,
            source=Replay(payloads=[(0.0, _payload(*target, frame=n)) for n in range(400)]),
        )
        result = run_trial(calibration, world, frame_period, values=condition.values)
        scheduler.record(condition.name, result.outcome)

        # Only trials the task paid for contribute. A fixation the task would not
        # reward is not one to calibrate against.
        if result.outcome is Outcome.CORRECT:
            collector.accept(target, [parse(_payload(*target), at=0.0)])

    assert scheduler.finished
    assert trials == 26, "thirteen targets, twice each"

    left, right, findings = collector.fit(tested_eccentricity_deg=16.0)
    assert left is not None and right is not None
    assert [f for f in findings if f.blocking] == []
    assert left.model is Model.SECOND_ORDER
    assert left.n_points == 13, "a target worked twice contributes one pairing"

    installed = log.install(at=42.0, targets=TARGETS, left=left, right=right,
                            why="calibration block")
    assert installed.version == 1
    assert log.changes[0].why == "calibration block"

    # And the installed map is the one a later trial would be scored through.
    scored = Tracked(_tracker_at(6.0, -4.0), log.current, calibration, frame_period)
    assert scored.mapping_version == 1
    assert scored.gaze("left", 0) == pytest.approx((6.0, -4.0), abs=1e-6)
