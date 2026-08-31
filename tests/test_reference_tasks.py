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
from wl_expcontroller.simulate import Subject, simulate
from wl_expcontroller.task import (
    GazeEnters,
    GazeHeld,
    GazeLeaves,
    SaccadeInto,
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
            lapse=0.004,
            hazards={
                GazeEnters: 0.20,
                GazeHeld: 0.30,
                SaccadeInto: 0.15,
                GazeLeaves: 0.01,
            },
        ),
        trials=5_000,
        frame_period=1 / 240,
        values=VALUES,
    )

    assert census.hangs == 0
    assert census.uncovered(detection) == set()
    assert census.states_visited == {"await_fix", "hold_fix", "stim_on", "verify"}
