"""Executing a declarative trial.

The framework runs the task; the task never owns the frame loop (ADR-0006). These
tests are about that loop -- and they are the same loop the rig runs, with a
simulated world substituted for hardware.
"""

from __future__ import annotations

import pytest

from wl_expcontroller.run import Quiet, Scripted, run_trial
from wl_expcontroller.task import (
    After,
    GazeEnters,
    On,
    Outcome,
    P,
    Param,
    State,
    Trial,
)


def test_a_time_guard_fires_on_the_first_frame_at_or_past_its_deadline():
    """The frame quantum is real and the task cannot see it. A 100 ms wait on a
    10 ms frame resolves on frame 10, not at 100 ms -- which is why S1 forbids a
    task assuming a frame period and why V1 measures the real one."""
    trial = Trial(
        start="wait",
        states=[State("wait", go=[On(After(0.1), Outcome.CORRECT)])],
    )

    result = run_trial(trial, world=Quiet(), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    assert result.frames == 10


def test_the_clock_restarts_on_state_entry():
    """A hold is 50 ms *after acquisition*, not 50 ms after the trial began. If
    elapsed time were measured from the trial rather than the state, every hold
    would shorten by however long the animal took to look -- an error that gets
    worse the slower the animal is, which is exactly backwards."""
    trial = Trial(
        start="await_fix",
        states=[
            State(
                "await_fix",
                go=[
                    On(GazeEnters("fix"), "hold_fix"),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State("hold_fix", go=[On(After(0.05), Outcome.CORRECT)]),
        ],
    )

    result = run_trial(
        trial, world=Scripted({GazeEnters("fix"): 3}), frame_period=0.01
    )

    assert result.outcome is Outcome.CORRECT
    assert result.frames == 8  # 3 frames to acquire, then 5 to hold


def test_a_world_where_nothing_happens_falls_through_to_the_time_bound():
    trial = Trial(
        start="await_fix",
        states=[
            State(
                "await_fix",
                go=[
                    On(GazeEnters("fix"), "hold_fix"),
                    On(After(0.04), Outcome.NO_FIXATION),
                ],
            ),
            State("hold_fix", go=[On(After(0.05), Outcome.CORRECT)]),
        ],
    )

    result = run_trial(trial, world=Quiet(), frame_period=0.01)

    assert result.outcome is Outcome.NO_FIXATION


def test_a_parameter_reference_is_resolved_from_the_trials_bound_values():
    """S8 §3.4: a trial runs against a *resolved* parameter set, snapshotted per
    trial. Found by simulating the first real task, whose guards are all parameter
    references -- the loop compared a float to a `P` and raised."""
    trial = Trial(
        start="wait",
        params=[Param("timeout", unit="s", low=0.01, high=1.0)],
        states=[State("wait", go=[On(After(P("timeout")), Outcome.NO_RESPONSE)])],
    )

    result = run_trial(trial, Quiet(), frame_period=0.01, values={"timeout": 0.05})

    assert result.outcome is Outcome.NO_RESPONSE
    assert result.frames == 5


def test_running_without_a_value_for_a_declared_parameter_is_refused():
    """Not defaulted to zero. A missing timeout that silently becomes 0.0 turns
    every trial into an immediate abort, which looks like an animal that will not
    work rather than like a bug."""
    trial = Trial(
        start="wait",
        params=[Param("timeout", unit="s", low=0.01, high=1.0)],
        states=[State("wait", go=[On(After(P("timeout")), Outcome.NO_RESPONSE)])],
    )

    with pytest.raises(KeyError, match="timeout"):
        run_trial(trial, Quiet(), frame_period=0.01, values={})
