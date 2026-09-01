"""Blinks and tracker loss, told apart and tolerated separately.

They look identical in the data -- gaze leaves the window -- and they are not the
same event. A blink is the animal; tracker loss is the rig. Scoring both as fixation
breaks inflates a session's break rate with equipment failure, and the inflation is
invisible, so an animal looks worse than it is and nobody can tell whether to fix the
animal or the camera.

The graces are independent because the phenomena are. Some tasks must not tolerate
blinks at all; every task should tolerate a brief tracker stall, because P6 measured
~2% of OpenIrisDPI frames at >= 10 ms with a maximum near 50 ms and that is the
tracker's own behaviour rather than the animal's.
"""

import pytest

from wl_expcontroller.run import run_trial
from wl_expcontroller.task import (
    After,
    Disc,
    Hold,
    On,
    Outcome,
    Show,
    State,
    Stimulus,
    Tolerances,
    Trial,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))


class Interrupted:
    """A world holding fixation, with the gaze signal interrupted on given frames."""

    def __init__(self, kind: str, frames: range) -> None:
        self.kind = kind
        self.frames = frames

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        return True

    def happened(self, guard, state: str, frame: int) -> bool:
        return False

    def display(self, visible, frame: int) -> None:
        pass

    def signal(self, frame: int) -> str:
        return self.kind if frame in self.frames else "ok"


def holding(tolerances: Tolerances) -> Trial:
    return Trial(
        start="hold",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        tolerances=tolerances,
        states=[
            State(
                "hold",
                enter=[Show(FIX)],
                go=[
                    On(Hold("fix", 0.1), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )


def test_a_blink_is_not_tolerated_by_default():
    """Strict by default, because a task that allows blinks should say so.

    The other way round, a task inherits a tolerance nobody chose and reports holds
    that were never observed.
    """
    trial = holding(Tolerances())
    result = run_trial(trial, Interrupted("blink", range(3, 5)), frame_period=0.01)

    assert result.outcome is Outcome.BLINK_BREAK


def test_a_blink_inside_a_declared_grace_does_not_break_the_hold():
    trial = holding(Tolerances(blink=0.3))
    result = run_trial(trial, Interrupted("blink", range(3, 20)), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT


def test_a_blink_beyond_the_declared_grace_breaks_it():
    trial = holding(Tolerances(blink=0.05))
    result = run_trial(trial, Interrupted("blink", range(3, 40)), frame_period=0.01)

    assert result.outcome is Outcome.BLINK_BREAK


def test_a_brief_tracker_stall_is_always_forgiven():
    """P6's measured stall distribution, tolerated by default.

    ~2% of frames >= 10 ms, max ~50 ms. That is the tracker's behaviour, and a
    default that scored it as a fixation break would blame the animal for the
    camera on roughly one trial in every few.
    """
    trial = holding(Tolerances())
    result = run_trial(trial, Interrupted("lost", range(3, 6)), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT


def test_sustained_tracker_loss_is_its_own_outcome_not_a_fixation_break():
    """The distinction the whole change exists for."""
    trial = holding(Tolerances())
    result = run_trial(trial, Interrupted("lost", range(3, 40)), frame_period=0.01)

    assert result.outcome is Outcome.TRACKER_LOST
    assert result.outcome is not Outcome.FIXATION_BREAK


def test_the_two_graces_are_independent():
    """A task may forbid blinks and still forgive a stall, and the reverse."""
    strict_blink = holding(Tolerances(blink=0.0, tracker_lost=0.2))
    assert (
        run_trial(strict_blink, Interrupted("blink", range(3, 5)), 0.01).outcome
        is Outcome.BLINK_BREAK
    )
    assert (
        run_trial(strict_blink, Interrupted("lost", range(3, 15)), 0.01).outcome
        is Outcome.CORRECT
    )

    loose_blink = holding(Tolerances(blink=0.3, tracker_lost=0.0))
    assert (
        run_trial(loose_blink, Interrupted("blink", range(3, 15)), 0.01).outcome
        is Outcome.CORRECT
    )
    assert (
        run_trial(loose_blink, Interrupted("lost", range(3, 5)), 0.01).outcome
        is Outcome.TRACKER_LOST
    )


def test_an_interruption_freezes_a_hold_rather_than_lapsing_it():
    """A hold spanning a forgiven stall is not a hold that was *observed*.

    S5 4.1's staleness policy: the frames are not counted toward the hold, so a
    0.1 s hold interrupted for 0.03 s completes 0.03 s later than an uninterrupted
    one -- rather than restarting, which would be wrong, or counting the blind
    frames, which would report a hold nobody saw.
    """
    clean = run_trial(holding(Tolerances()), Interrupted("lost", range(0, 0)), 0.01)
    stalled = run_trial(holding(Tolerances()), Interrupted("lost", range(3, 6)), 0.01)

    assert clean.outcome is stalled.outcome is Outcome.CORRECT
    assert stalled.frames == clean.frames + 3


def test_a_task_may_switch_enforcement_off_explicitly():
    """A joystick-only task has no gaze criterion to protect, and should not abort
    because a camera nobody is using dropped out."""
    trial = holding(Tolerances(blink=None, tracker_lost=None))
    result = run_trial(trial, Interrupted("lost", range(3, 60)), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT


def test_the_signal_detection_outcomes_exist():
    """Without all four cells d' and criterion are not computable -- and not
    recoverable offline either, because the distinction was never recorded."""
    assert Outcome.CORRECT_REJECT.value == "correct_reject"
    assert Outcome.FALSE_ALARM.value == "false_alarm"


def test_a_rig_fault_is_not_an_animal_abort():
    """`ABORT` means the animal went somewhere that was neither target nor
    distractor. A dropped frame is not that, and mixing them makes a session's
    abort rate a number about two unrelated things."""
    assert Outcome.FAULT is not Outcome.ABORT
    assert Outcome.FAULT.value == "fault"


def test_a_simulated_session_can_reach_the_signal_outcomes():
    """Otherwise they are untested in every simulated session.

    Traps 8 and 9 were both this: a subject that cannot produce a condition makes
    the task's handling of it unreachable, and the report says clean. A subject that
    never blinks would have made `BLINK_BREAK` and `TRACKER_LOST` exactly that.
    """
    from wl_expcontroller.simulate import Subject, simulate
    from wl_expcontroller.task import Entered

    trial = holding(Tolerances(blink=0.05, tracker_lost=0.05))

    blinker = simulate(
        trial,
        Subject(seed=2, engagement=1.0, hazards={Entered: 8.0}, blinks=3.0),
        trials=300,
        frame_period=1 / 240,
    )
    staller = simulate(
        trial,
        Subject(seed=2, engagement=1.0, hazards={Entered: 8.0}, stalls=3.0),
        trials=300,
        frame_period=1 / 240,
    )

    assert blinker.outcomes[Outcome.BLINK_BREAK] > 0
    assert blinker.outcomes[Outcome.TRACKER_LOST] == 0
    assert staller.outcomes[Outcome.TRACKER_LOST] > 0
    assert staller.outcomes[Outcome.BLINK_BREAK] == 0
