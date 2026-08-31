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
    Entered,
    Exited,
    Hold,
    On,
    Outcome,
    P,
    Param,
    SaccadeTo,
    Score,
    State,
    Trial,
    Window,
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
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("fix"), "hold_fix"),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State("hold_fix", go=[On(After(0.05), Outcome.CORRECT)]),
        ],
    )

    result = run_trial(
        trial,
        world=Scripted({}, inside={frame: "fix" for frame in range(3, 40)}),
        frame_period=0.01,
    )

    assert result.outcome is Outcome.CORRECT
    assert result.frames == 8  # enters on 3, holds 50 ms across frames 4-8


def test_a_world_where_nothing_happens_falls_through_to_the_time_bound():
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("fix"), "hold_fix"),
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


def test_a_trial_records_every_scored_response_and_still_ends_once():
    """S1a §8. A trial emits scored events as it goes; the terminal outcome
    summarises. Free viewing is then a trial with many scored responses and a
    mundane ending, rather than a shape the model cannot express."""
    trial = Trial(
        start="first",
        windows=[
            Window("a", at=(-10.0, 0.0), radius=2.0),
            Window("b", at=(10.0, 0.0), radius=2.0),
        ],
        states=[
            State(
                "first",
                go=[
                    On(
                        SaccadeTo("a"),
                        "second",
                        do=[Score("a", Outcome.CORRECT)],
                    ),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
            State(
                "second",
                go=[
                    On(
                        SaccadeTo("b"),
                        Outcome.CORRECT,
                        do=[Score("b", Outcome.WRONG_TARGET)],
                    ),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )

    result = run_trial(
        trial,
        Scripted({SaccadeTo("a"): 3, SaccadeTo("b"): 7}),
        frame_period=0.01,
    )

    assert result.outcome is Outcome.CORRECT
    assert [(s.window, s.scored_as, s.frame) for s in result.scored] == [
        ("a", Outcome.CORRECT, 3),
        ("b", Outcome.WRONG_TARGET, 7),
    ]


class _Membership:
    """A world that reports only where gaze is, frame by frame."""

    def __init__(self, inside: dict[int, str]) -> None:
        self.inside = inside

    def in_window(self, window: str, frame: int) -> bool:
        return self.inside.get(frame) == window

    def happened(self, guard, state: str, frame: int) -> bool:
        return False


def test_entered_exited_and_hold_are_derived_from_membership_not_asked_of_the_world():
    """The property that makes worlds interchangeable.

    A world reports *where gaze is*. The loop derives entering, leaving and holding
    from that, so those semantics -- including the staleness policy S5 §4.1
    requires -- exist once. If each world implemented them, the simulator and a
    mouse would disagree about what a hold is, and a person validating a task in
    demo mode would be validating different behaviour from the one an animal gets.
    """
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("fix"), "hold_fix"),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.03), Outcome.CORRECT),
                    On(Exited("fix"), Outcome.FIXATION_BREAK),
                ],
            ),
        ],
    )
    # inside from frame 2; a hold of 30 ms at 10 ms frames completes on frame 5
    world = _Membership({frame: "fix" for frame in range(2, 40)})

    result = run_trial(trial, world, frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # Frame 2 is consumed entering `hold_fix`; the hold there runs 3, 4, 5. A hold
    # cannot count the frame that triggered entry into its own state.
    assert result.frames == 5


def test_leaving_a_window_restarts_a_hold_rather_than_pausing_it():
    """A hold is continuous. Accumulating across a gap would score an animal that
    looked away and back as having held throughout, which is the opposite of what
    the criterion is for."""
    trial = Trial(
        start="hold_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.03), Outcome.CORRECT),
                    On(After(0.2), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    # in for two frames, out for one, then in continuously
    inside = {1: "fix", 2: "fix", 4: "fix", 5: "fix", 6: "fix", 7: "fix"}

    result = run_trial(trial, _Membership(inside), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    assert result.frames == 6, "the hold restarted at frame 4, completing on 6"


def test_a_hold_is_measured_from_state_entry_not_from_when_gaze_arrived():
    """Found by review, 2026-08-31, and it made correctly-authored tasks wrong.

    `holding_since` was trial-scoped, so a `Hold` in a later state was already
    satisfied by presence that began before that state was entered. A memory-guided
    structure -- hold 0.3 s, then a declared 0.3 s delay with fixation enforced --
    ran the delay for **one frame** and scored CORRECT. Every working-memory delay
    in the v1 inventory is written this way.

    A hold in a state means held continuously *since that state began*.
    """
    trial = Trial(
        start="hold_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.3), "delay"),
                    On(After(5.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "delay",
                go=[
                    On(Hold("fix", 0.3), Outcome.CORRECT),
                    On(Exited("fix"), Outcome.FIXATION_BREAK),
                    On(After(5.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    always_inside = Scripted({}, inside={f: "fix" for f in range(1, 5000)})

    result = run_trial(trial, always_inside, frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # 0.3 s to satisfy the first hold, then a further 0.3 s inside `delay`.
    assert result.frames == 60, f"the delay ran {(result.frames - 30) / 100:.2f} s"
