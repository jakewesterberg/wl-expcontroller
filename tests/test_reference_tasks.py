"""The reference tasks, held to the standard ADR-0006 rests on.

A task is approved from its checks and its simulation report, not by reading its
source. These assert both for the tasks that demonstrate it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from wl_expcontroller.check import check
from wl_expcontroller.geometry import Geometry
from wl_expcontroller.photometry import Calibration, xyY
from wl_expcontroller.simulate import Subject, simulate
from wl_expcontroller.task import (
    Entered,
    Hold,
    Exited,
    Outcome,
    SaccadeTo,
    Trial,
)

TASKS = Path(__file__).resolve().parents[1] / "tasks"
GEOMETRY = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)
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
    )

    assert census.hangs == 0
    assert census.uncovered(search) == set()
