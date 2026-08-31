"""The load-time checks from S1 §9.

A task that fails any of these is refused at load, not at run. The point is that a
generated task is caught before an animal sees it -- pitfalls P15.
"""

import pytest

from wl_expcontroller.task import (
    After,
    Bounded,
    GazeLeaves,
    On,
    Outcome,
    Response,
    Reward,
    State,
    Trial,
)
from wl_expcontroller.check import check


def test_a_state_no_transition_can_reach_is_reported():
    """S1 §9 check 2. A state nothing reaches is dead code in a task, and in a
    generated task it is the shape a hallucinated state name takes."""
    trial = Trial(
        start="await_fix",
        states=[
            State("await_fix", go=[On(After(4.0), Outcome.NO_FIXATION)]),
            State("orphan", go=[On(After(1.0), Outcome.CORRECT)]),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["unreachable-state"]
    assert "orphan" in findings[0].detail


def test_a_state_with_no_time_bound_is_reported_as_an_unbounded_wait():
    """S1 §9 check 4, and the defect the S1 bake-off actually produced: a
    fixation hold that can wait forever. Every wait needs a bound or an
    explicit declaration that it has none."""
    trial = Trial(
        start="hold_fix",
        states=[
            State(
                "hold_fix",
                go=[On(GazeLeaves("fix"), Outcome.FIXATION_BREAK)],
            ),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["unbounded-wait"]
    assert "hold_fix" in findings[0].detail


def test_a_state_declaring_itself_unbounded_is_accepted():
    """Free viewing of natural images is a first-class unbounded epoch (S1 §5.4).
    The check exists to make it deliberate and visible, not to forbid it."""
    trial = Trial(
        start="free_view",
        states=[
            State(
                "free_view",
                go=[On(Response("lever"), Outcome.CORRECT)],
                unbounded=True,
            ),
        ],
    )

    assert check(trial) == []


def test_a_reward_action_refuses_a_magnitude():
    """S1 §2.3 and S8 §4. A task may name a bounded-config entry; it may not say
    how much. The ceiling is enforced by what the task can express, not by review
    noticing -- which matters because the task was probably written by a model.

    A type checker catches this too. The runtime refusal is the one that catches
    a generated task at load, on a machine with no type checker running.
    """
    with pytest.raises(TypeError, match="bounded-config"):
        Reward(0.15)


def test_a_reward_action_names_a_bounded_config_entry():
    assert Reward(Bounded("reward_small")).ref.name == "reward_small"
