"""Load-time checks over what is on the display.

Every earlier check inspects the transition graph, so the residual defect class was
"correct graph, wrong experiment" -- a task holding fixation on a point it had taken
down passed all ten. These close that class statically; `test_simulate` closes it
dynamically. Both, because a static check finds it without a subject and simulation
finds it without the author having coupled anything.
"""

from wl_expcontroller.check import check
from wl_expcontroller.task import (
    REMEMBERED,
    After,
    Disc,
    Entered,
    Hide,
    Hold,
    On,
    Outcome,
    Show,
    State,
    Stimulus,
    Trial,
    Update,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))


def codes(trial: Trial) -> set[str]:
    return {finding.code for finding in check(trial)}


def test_a_hold_on_a_stimulus_that_is_not_displayed_is_refused():
    """The bug the review found, as a load-time refusal."""
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[
            State(
                "await_fix",
                enter=[Show(FIX)],
                go=[
                    On(Entered("fix"), "hold_fix", do=[Hide("fix")]),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.3), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" in codes(trial)


def test_a_stimulus_shown_in_an_earlier_state_satisfies_a_later_hold():
    """A `Show` persists, so the reference structure is legal -- which is the whole
    reason the semantics changed rather than the task."""
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[
            State(
                "await_fix",
                enter=[Show(FIX)],
                go=[
                    On(Entered("fix"), "hold_fix"),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.3), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" not in codes(trial)


def test_a_stimulus_shown_on_only_one_path_in_is_refused():
    """Visible on *some* route into a state is not visible.

    A task where one branch shows the target and another does not is the kind of
    thing that works for a hundred trials and then scores a hold against a blank
    screen on whichever branch nobody tested.
    """
    trial = Trial(
        start="choose",
        windows=[Window("t", at=(8.0, 0.0), radius=2.0, on="target")],
        states=[
            State(
                "choose",
                go=[
                    On(
                        Entered("t"),
                        "verify",
                        do=[Show(Stimulus("target", at=(8.0, 0.0)))],
                    ),
                    On(After(1.0), "verify"),
                ],
            ),
            State(
                "verify",
                go=[
                    On(Hold("t", 0.2), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" in codes(trial)


def test_a_remembered_window_needs_no_stimulus():
    trial = Trial(
        start="wait",
        windows=[Window("mem", at=(8.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "wait",
                go=[
                    On(Hold("mem", 0.2), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" not in codes(trial)


def test_a_window_that_declares_no_coupling_is_refused():
    """Unset is not the same as `REMEMBERED`.

    If unset were allowed to mean "nothing there", the check above would be opt-in
    -- and the tasks most likely to skip it are the ones written fastest.
    """
    trial = Trial(
        start="wait",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State("wait", go=[On(After(1.0), Outcome.NO_FIXATION)]),
        ],
    )
    assert "uncoupled-window" in codes(trial)


def test_hiding_or_updating_a_stimulus_that_is_not_displayed_is_refused():
    trial = Trial(
        start="wait",
        windows=[],
        states=[
            State(
                "wait",
                enter=[Update("ghost", at=(1.0, 0.0))],
                go=[On(After(1.0), Outcome.ABORT, do=[Hide("phantom")])],
            ),
        ],
    )
    found = codes(trial)
    assert "absent-stimulus" in found


def test_an_update_that_changes_nothing_is_refused():
    trial = Trial(
        start="wait",
        windows=[],
        states=[
            State(
                "wait",
                enter=[Show(FIX), Update("fix")],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )
    assert "empty-update" in codes(trial)
