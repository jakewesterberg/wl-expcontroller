"""Simulated sessions.

The load-time checks prove a task is well *formed*. Simulation proves it is
well *behaved*: that every outcome is reachable by something an animal might
actually do, that no state is starved, and that nothing hangs. Together they are
the D4 acceptance test -- a generated task approved from a diagram and a report,
without reading the source (ADR-0006).
"""

from __future__ import annotations

from wl_expcontroller.simulate import Subject, simulate
from wl_expcontroller.task import (
    After,
    Acquired,
    Broke,
    On,
    Outcome,
    State,
    Trial,
    Window,
)

DETECTION = Trial(
    start="await_fix",
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
    states=[
        State(
            "await_fix",
            go=[
                On(Acquired("fix"), "hold_fix"),
                On(After(2.0), Outcome.NO_FIXATION),
            ],
        ),
        State(
            "hold_fix",
            go=[
                On(Broke("fix"), Outcome.FIXATION_BREAK),
                On(After(0.3), Outcome.CORRECT),
            ],
        ),
    ],
)


def test_simulation_reaches_every_outcome_the_task_declares():
    """A coverage gap is the defect the static checks cannot see: an outcome that
    is syntactically reachable but that no plausible behaviour produces. It is how
    a task quietly never scores an error, and how a condition silently never runs."""
    census = simulate(
        DETECTION,
        Subject(seed=7, hazards={Acquired: 0.25, Broke: 0.02}),
        trials=2_000,
        frame_period=0.01,
    )

    assert census.hangs == 0
    assert set(census.outcomes) == {
        Outcome.NO_FIXATION,
        Outcome.FIXATION_BREAK,
        Outcome.CORRECT,
    }
    assert census.states_visited == {"await_fix", "hold_fix"}


def test_an_outcome_no_behaviour_reaches_is_reported_as_uncovered():
    """An animal that never breaks fixation never produces FIXATION_BREAK. The
    census says so rather than the absence being invisible in a pass."""
    census = simulate(
        DETECTION,
        Subject(seed=7, hazards={Acquired: 0.25, Broke: 0.0}),
        trials=500,
        frame_period=0.01,
    )

    assert Outcome.FIXATION_BREAK not in census.outcomes
    assert census.uncovered(DETECTION) == {Outcome.FIXATION_BREAK}
