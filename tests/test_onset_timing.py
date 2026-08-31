"""Intervals timed from when the stimulus actually appeared.

`After(0.1)` times from a **state transition**, but the stimulus it follows does not
exist until the next flip -- and the flip is 8-33 ms later depending on the refresh
rate and where in the frame the transition landed. So every SOA written this way is
wrong by a variable amount, in the direction nobody notices, and variable error is
worse than constant error because it cannot be corrected offline.

This matters most where the interval *is* the independent variable: priming, masking,
cue-target SOA. `Onscreen` -- the photodiode saying the stimulus reached the display
-- has been in the vocabulary since S1 and was used by nothing.
"""

import pytest

from wl_expcontroller.check import check
from wl_expcontroller.run import Scripted, run_trial
from wl_expcontroller.task import (
    After,
    Disc,
    On,
    Onscreen,
    Outcome,
    Show,
    State,
    Stimulus,
    Trial,
    Window,
)

CUE = Stimulus("cue", at=(0.0, 0.0), looks=Disc(size=1.0))


def soa_task(since) -> Trial:
    return Trial(
        start="cue_on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="cue")],
        states=[
            State(
                "cue_on",
                enter=[Show(CUE)],
                go=[
                    On(After(0.05, since=since), Outcome.CORRECT),
                    # A plain bound, so the state cannot wait forever if the
                    # photodiode never reports.
                    On(After(1.0), Outcome.ABORT),
                ],
            ),
        ],
    )


def test_an_soa_from_state_entry_starts_before_the_stimulus_exists():
    """The behaviour being corrected, stated so the difference is visible."""
    world = Scripted(at_frame={Onscreen("task"): 4})
    result = run_trial(soa_task(since=None), world, frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # 50 ms after the transition, which was 30 ms before the stimulus appeared.
    assert result.frames == 5


def test_an_soa_from_photodiode_onset_starts_when_the_stimulus_appeared():
    world = Scripted(at_frame={Onscreen("task"): 4})
    result = run_trial(soa_task(since=Onscreen("task")), world, frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # The photodiode reported on frame 4; 50 ms of SOA runs from there.
    assert result.frames == 9


def test_a_photodiode_that_never_reports_falls_through_to_the_plain_bound():
    """An `After` with a `since` is not a time bound on its own.

    If the flip is dropped or the patch is occluded the guard never arms, so a state
    relying on it alone could wait forever -- which is the failure mode check 4
    exists to make impossible.
    """
    result = run_trial(soa_task(since=Onscreen("task")), Scripted(at_frame={}), 0.01)

    assert result.outcome is Outcome.ABORT


def test_an_after_with_a_since_does_not_satisfy_the_unbounded_wait_check():
    trial = Trial(
        start="cue_on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="cue")],
        states=[
            State(
                "cue_on",
                enter=[Show(CUE)],
                go=[On(After(0.05, since=Onscreen("task")), Outcome.CORRECT)],
            ),
        ],
    )
    assert "unbounded-wait" in {f.code for f in check(trial)}


def test_the_result_records_when_the_stimulus_actually_appeared():
    """Declared versus realized. Without it the record says what was asked for and
    nothing about what happened, and the two differ by exactly the amount this
    change exists to expose."""
    world = Scripted(at_frame={Onscreen("task"): 4})
    result = run_trial(soa_task(since=Onscreen("task")), world, frame_period=0.01)

    assert result.confirmed == ((("task"), 4),)
