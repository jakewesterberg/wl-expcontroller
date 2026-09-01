"""The artifact must show the display, because the display is what goes wrong."""

from wl_expcontroller.review import render
from wl_expcontroller.task import (
    After, Disc, Entered, Hide, Hold, Mark, On, Outcome, Show, State,
    Stimulus, Trial, Update, Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))
TARGET = Stimulus("target", at=(8.0, 0.0), looks=Disc(size=1.0))

TRIAL = Trial(
    start="await_fix",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=2.0, on="fix"),
        Window("target", at=(8.0, 0.0), radius=2.0, on="target"),
    ],
    states=[
        State("await_fix", enter=[Show(FIX), Mark(4096)],
              go=[On(Entered("fix"), "hold_fix"),
                  On(After(2.0), Outcome.NO_FIXATION, do=[Mark(4100)])]),
        State("hold_fix",
              go=[On(Hold("fix", 0.3), "stim_on"),
                  On(After(2.0), Outcome.NO_FIXATION)]),
        State("stim_on", enter=[Show(TARGET), Hide("fix"), Mark(4097)],
              go=[On(Hold("target", 0.2), Outcome.CORRECT, do=[Mark(4099)]),
                  On(After(1.0), Outcome.NO_RESPONSE)]),
    ],
)


def test_the_artifact_shows_when_each_stimulus_is_on_screen():
    """Position and disparity are not enough.

    Every defect the reviews found was about *when* something was on the display,
    not where -- so an artifact showing only position is a picture a reviewer trusts
    of the half of the task that was never the problem.
    """
    artifact = render(TRIAL)

    assert "## Display timeline" in artifact
    # Shown in one state, taken down in another: the reviewer can see the span.
    assert "`fix`" in artifact
    assert "shown in `await_fix`" in artifact
    assert "hidden in `stim_on`" in artifact
    # A stimulus never taken down says so, rather than leaving a blank cell that
    # reads as missing information.
    assert "until the trial ends" in artifact


def test_the_code_table_names_the_transition_not_only_the_state():
    """A state emitting several codes on different edges is ambiguous otherwise.

    `stim_on` strobes one code on entry and another on the edge to CORRECT, and an
    artifact attributing both to `stim_on` cannot be checked against a recording.
    """
    artifact = render(TRIAL)

    assert "on entry" in artifact
    assert "on → CORRECT" in artifact


def test_an_update_appears_in_the_timeline():
    trial = Trial(
        start="on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.5), "changed")]),
            State("changed", enter=[Update("fix", looks=Disc(size=1.5))],
                  go=[On(After(0.5), Outcome.CORRECT)]),
        ],
    )
    assert "changed in `changed`" in render(trial)


def test_an_array_task_renders():
    """Review-by-artifact fails closed only if the artifact renders.

    `ItemWindows` was added to the vocabulary and nothing rendered one, so the
    review artifact -- the thing ADR-0006 says a task is approved from -- raised
    `AttributeError` on every search task. No test caught it because no test
    rendered a task with an array.
    """
    from wl_expcontroller.task import Array, ItemWindows, P, Param, SaccadeTo

    trial = Trial(
        start="search",
        params=[Param("set_size", unit="items", low=2, high=6)],
        windows=[ItemWindows(of="search", radius=2.0)],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=P("set_size"), radius=8.0, target=0),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    artifact = render(trial)

    # The family is described as a family, since how many there are is a parameter.
    assert "search.*" in artifact
    assert "set_size items" in artifact
