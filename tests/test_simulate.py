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
    Entered,
    Exited,
    Entered,
    Exited,
    Hold,
    On,
    Outcome,
    SaccadeTo,
    Score,
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
                On(Entered("fix"), "hold_fix"),
                On(After(2.0), Outcome.NO_FIXATION),
            ],
        ),
        State(
            "hold_fix",
            go=[
                On(Exited("fix"), Outcome.FIXATION_BREAK),
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
        Subject(seed=7, hazards={Entered: 0.25, Exited: 0.02}),
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
        Subject(seed=7, hazards={Entered: 0.25, Exited: 0.0}),
        trials=500,
        frame_period=0.01,
    )

    assert Outcome.FIXATION_BREAK not in census.outcomes
    assert census.uncovered(DETECTION) == {Outcome.FIXATION_BREAK}


def test_the_census_counts_scored_responses_not_only_outcomes():
    """A free-viewing task ends the same mundane way every trial, so an
    outcome-only census says nothing about it. What varies -- and what the
    experiment is about -- is the responses inside the trial."""
    trial = Trial(
        start="look",
        windows=[Window("a", at=(-10.0, 0.0), radius=2.0)],
        states=[
            State(
                "look",
                go=[
                    On(SaccadeTo("a"), "look", do=[Score("a", Outcome.CORRECT)]),
                    On(After(0.5), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )

    census = simulate(
        trial,
        Subject(seed=3, engagement=1.0, hazards={SaccadeTo: 0.05}),
        trials=200,
        frame_period=0.01,
    )

    assert census.outcomes == {Outcome.NO_RESPONSE: 200}, "every trial ends alike"
    assert census.responses[("a", Outcome.CORRECT)] > 0, "and yet things happened"


def test_behaviour_does_not_change_when_the_display_does():
    """Hazards are rates per second, not per frame.

    A per-frame probability means something different at every refresh rate: 0.01
    per frame is a 51% chance of breaking across a 0.3 s hold at 240 Hz and 16% at
    60 Hz. The animal does not know the refresh rate, so a subject tuned on one rig
    would describe a different animal on another -- and S0's dual-mode panel makes
    that a rate change *within* a session.
    """
    trial = Trial(
        start="hold",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "hold",
                go=[
                    On(Hold("fix", 0.3), Outcome.CORRECT),
                    On(Exited("fix"), Outcome.FIXATION_BREAK),
                    On(After(3.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )

    def breaks_at(frame_period: float) -> float:
        census = simulate(
            trial,
            Subject(seed=4, engagement=1.0, hazards={Entered: 0.2, Exited: 0.01}),
            trials=600,
            frame_period=frame_period,
        )
        total = sum(census.outcomes.values())
        return census.outcomes[Outcome.FIXATION_BREAK] / total

    slow, fast = breaks_at(1 / 60), breaks_at(1 / 240)

    assert abs(slow - fast) < 0.08, f"60 Hz gave {slow:.2f}, 240 Hz gave {fast:.2f}"
