"""The reference tasks, held to the standard ADR-0006 rests on.

A task is approved from its checks and its simulation report, not by reading its
source. These assert both for the tasks that demonstrate it.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tasks.rig import RIG
from wl_xcon.calibration import constellation
from wl_xcon.check import check
from wl_xcon.geometry import Housing
from wl_xcon.photometry import Calibration, xyY
from wl_xcon.run import Recorded
from wl_xcon.simulate import Subject, simulate
from wl_xcon.task import (
    Entered,
    Hold,
    Exited,
    Outcome,
    SaccadeTo,
    Trial,
)

TASKS = Path(__file__).resolve().parents[1] / "tasks"

#: The rig in direct view (`tasks/rig.py`), where every reference task runs, with
#: **stand-in housings**: the real ones are unmeasured (direct-view spec §9 item 1). One
#: per bottom corner, 4 × 3 cm with a 0.5 cm margin.
GEOMETRY = replace(
    RIG,
    housings=(
        Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
        Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    ),
).direct()
VALUES = {
    "fix_timeout": 4.0,
    "fix_hold": 0.3,
    "response_window": 0.6,
    "target_hold": 0.2,
}


def _load(name: str, attribute: str):
    sys.path.insert(0, str(TASKS))
    spec = importlib.util.spec_from_file_location(name, TASKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, attribute)


@pytest.fixture(scope="module")
def detection() -> Trial:
    return _load("fixation_detection", "detection")


def test_the_reference_task_passes_every_load_time_check(detection):
    allocation = _load("allocation", "ALLOCATION")

    assert check(detection, allocation, geometry=GEOMETRY) == []


def test_simulation_reaches_every_outcome_the_reference_task_declares(detection):
    """The acceptance test, and the one that is hard to satisfy honestly.

    `NO_RESPONSE` needs an animal that acquires fixation, holds it, and then does
    not respond -- a mid-trial lapse. A subject whose engagement is decided once per
    trial cannot produce one, so every task's no-response path would go untested by
    simulation while the report claimed a clean run.
    """
    census = simulate(
        detection,
        Subject(
            seed=11,
            engagement=0.85,
            # Rates per second, not per frame.
            lapse=0.15,
            hazards={Entered: 6.0, SaccadeTo: 5.0, Exited: 0.05},
        ),
        trials=5_000,
        frame_period=1 / 240,
        values=VALUES,
        effects=Recorded(),
    )

    assert census.hangs == 0
    assert census.uncovered(detection) == set()
    assert census.states_visited == {"await_fix", "hold_fix", "stim_on", "verify"}


@pytest.fixture(scope="module")
def adaptive() -> Trial:
    return _load("adaptive_detection", "adaptive_detection")


def test_the_adaptive_task_passes_every_load_time_check(adaptive):
    allocation = _load("allocation", "ALLOCATION")

    assert check(adaptive, allocation, geometry=GEOMETRY) == []


def test_the_adaptive_trial_is_the_detection_trial_with_more_parameters(adaptive, detection):
    """S1's bake-off finding, asserted rather than claimed: the adaptive task's
    *trial* is structurally the same. Everything adaptive lives between trials."""
    assert [s.name for s in adaptive.states] == [s.name for s in detection.states]
    assert {p.name for p in detection.params} < {p.name for p in adaptive.params}


def test_the_staircase_converges_downward_on_success_and_backs_off_on_error():
    staircase = _load("adaptive_detection", "Staircase")(value=0.5)

    staircase.update(True)
    assert staircase.value == 0.5, "one correct is not enough; it is two-down"
    staircase.update(True)
    assert staircase.value < 0.5

    harder = staircase.value
    staircase.update(False)
    assert staircase.value > harder, "one error backs off immediately"


def test_an_aborted_trial_does_not_move_the_staircase():
    """An abort says nothing about difficulty. Letting one move the estimate makes
    contrast track engagement rather than perception -- so a disengaged animal
    would be handed easier stimuli for a reason unrelated to what it can see."""
    module_staircase = _load("adaptive_detection", "Staircase")
    next_params = _load("adaptive_detection", "next_params")
    staircase = module_staircase(value=0.5)

    for outcome in (Outcome.NO_FIXATION, Outcome.FIXATION_BREAK, Outcome.NO_RESPONSE):
        next_params(staircase, eccentricity=10.0, last=outcome)

    assert staircase.value == 0.5


# --- Colour pop-out search -------------------------------------------------
#
# The paradigm the vocabulary could not express before 2026-08-31: no colour, so a
# red target among green distractors could not be stated; and an array was N `Show`
# actions, so set size was a change to the shape of the task rather than a value.

SEARCH_VALUES = {
    "fix_timeout": 4.0,
    "fix_hold": 0.3,
    "response_window": 0.6,
    "target_hold": 0.2,
    "fix_window": 2.0,
    "item_window": 2.0,
    "eccentricity": 8.0,
    "set_size": 6,
    "target_index": 1,
    "array_phase": 0.0,
}

#: Illustrative, not measured. A real calibration comes from a photometer on the
#: actual panel and is committed under `docs/measurements/`; none exists yet.
PANEL = Calibration(
    red=xyY(0.640, 0.330, 45.0),
    green=xyY(0.300, 0.600, 145.0),
    blue=xyY(0.150, 0.060, 15.0),
    background=xyY(0.3127, 0.3290, 50.0),
    gamma=2.2,
    observer="macaque V(lambda) -- placeholder, unmeasured",
    measured_on="unmeasured",
)


@pytest.fixture(scope="module")
def search() -> Trial:
    return _load("visual_search", "search")


def test_the_search_task_passes_every_load_time_check(search):
    allocation = _load("allocation", "ALLOCATION")

    assert check(search, allocation, geometry=GEOMETRY, calibration=PANEL) == []


def test_the_search_task_will_not_load_without_a_measured_display(search):
    """Isoluminance is a claim about photometry, so it needs a photometer.

    The failure mode this prevents is not a crash: it is a task that runs, looks
    convincing, and reports a colour nobody measured -- which reaches a methods
    section.
    """
    allocation = _load("allocation", "ALLOCATION")
    codes = {f.code for f in check(search, allocation, geometry=GEOMETRY)}

    assert "uncalibrated-color" in codes


def test_set_size_is_a_value_this_task_can_be_run_at_several_of(search):
    """The gap, closed: one task file, many set sizes, no structural change."""
    for n in (2, 4, 8, 12):
        census = simulate(
            search,
            Subject(seed=7, engagement=0.9, lapse=0.1, hazards={Entered: 4.0, Exited: 0.3, SaccadeTo: 5.0}),
            trials=120,
            frame_period=1 / 240,
            values={**SEARCH_VALUES, "set_size": n, "target_index": 0},
            effects=Recorded(),
        )
        assert census.hangs == 0
        assert census.outcomes.total() == 120


def test_simulation_reaches_every_outcome_the_search_task_declares(search):
    census = simulate(
        search,
        Subject(
            seed=5,
            engagement=0.85,
            lapse=0.15,
            hazards={Entered: 4.0, Exited: 0.5, SaccadeTo: 5.0},
        ),
        trials=1500,
        frame_period=1 / 240,
        values=SEARCH_VALUES,
        effects=Recorded(),
    )

    assert census.hangs == 0
    assert census.uncovered(search) == set()


# --- In direct view (direct-view spec §8) -----------------------------------------

REFERENCE = {
    "fixation_detection": "detection",
    "adaptive_detection": "adaptive_detection",
    "visual_search": "search",
    "calibration": "calibration",
}


def _range(trial: Trial, name: str) -> tuple[float, float]:
    (param,) = [p for p in trial.params if p.name == name]
    return (param.low, param.high)


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_every_reference_task_is_written_for_direct_view(name):
    """The first animal task runs in direct view (PI, 2026-09-28), and these are the
    tasks that stand for it."""
    assert _load(name, REFERENCE[name]).view == "direct"


def test_the_interim_narrowing_is_undone(detection, adaptive, search):
    """The ranges the stereoscope's ±12° mask forced on 2026-09-28, back to what they
    were, now that direct view's field is what they are checked against."""
    assert _range(detection, "target_position") == (-16.0, 16.0)
    assert _range(adaptive, "target_position") == (-16.0, 16.0)
    assert _range(adaptive, "eccentricity") == (2.0, 16.0)
    assert _range(search, "eccentricity") == (5.0, 14.0)


def test_the_calibration_task_passes_every_load_time_check_in_direct_view():
    allocation = _load("allocation", "ALLOCATION")

    assert check(_load("calibration", "calibration"), allocation, geometry=GEOMETRY) == []


def test_the_calibration_task_can_present_direct_views_whole_constellation():
    """Its ranges are the ±15° region the constellation is placed over, so every
    target the block schedules is one the task declares."""
    task = _load("calibration", "calibration")
    (x_low, x_high), (y_low, y_high) = _range(task, "target_x"), _range(task, "target_y")

    assert (x_low, x_high, y_low, y_high) == (-15.0, 15.0, -15.0, 15.0)
    for x, y in constellation(GEOMETRY):
        assert x_low <= x <= x_high and y_low <= y <= y_high


def test_a_direct_view_task_is_refused_in_the_stereoscope_naming_both(detection):
    """What direct view part 2's session start will say if the operator picks the
    stereoscope for this task: the mismatch, and the ±16° its mask cannot show."""
    allocation = _load("allocation", "ALLOCATION")
    codes = {f.code for f in check(detection, allocation, geometry=RIG.stereoscope(1.6))}

    assert codes == {"wrong-setup", "stimulus-off-screen"}
