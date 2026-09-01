"""Per-eye gaze criteria, which the binocular tracker makes available.

The rigs track both eyes independently (architecture: 500 Hz binocular dDPI, and
analog-in carries eye X/Y for both eyes), so a per-eye criterion is a real primitive
rather than an aspiration. It is also the *correct* primitive on a stereoscope: under
dichoptic presentation the non-viewing eye drifts, so scoring a conjugate estimate
scores the average of one eye doing the task and one eye doing nothing.

`Window.eye` existed and the loop ignored it, which is worse than not having it -- a
task could declare a left-eye criterion, run, record, and be scored on both.
"""

from wl_expcontroller.check import check
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
    Trial,
    Window,
)


class PerEye:
    """A world that knows which eye is where, as a binocular tracker does."""

    def __init__(self, inside_for: str) -> None:
        self.inside_for = inside_for
        self.asked: list[tuple[str, str]] = []

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        self.asked.append((window, eye))
        return eye == self.inside_for

    def happened(self, guard, state: str, frame: int) -> bool:
        return False

    def signal(self, frame: int) -> str:
        """Always available: these tests are not about signal loss."""
        return "ok"

    def display(self, visible, frame: int) -> None:
        pass


def a_task(eye: str) -> Trial:
    return Trial(
        start="hold",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix", eye=eye)],
        states=[
            State(
                "hold",
                enter=[Show(Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3)))],
                go=[
                    On(Hold("fix", 0.02), Outcome.CORRECT),
                    On(After(0.5), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )


def test_the_loop_asks_the_world_about_the_eye_the_window_declares():
    world = PerEye(inside_for="left")

    assert run_trial(a_task("left"), world, 0.01).outcome is Outcome.CORRECT
    assert ("fix", "left") in world.asked
    assert ("fix", "both") not in world.asked


def test_a_left_eye_criterion_is_not_satisfied_by_the_right_eye():
    """The whole point. Otherwise the declaration is decorative."""
    assert run_trial(a_task("left"), PerEye("right"), 0.01).outcome is Outcome.NO_FIXATION
    assert run_trial(a_task("right"), PerEye("right"), 0.01).outcome is Outcome.CORRECT


def test_a_conjugate_window_is_asked_about_both():
    world = PerEye(inside_for="both")

    assert run_trial(a_task("both"), world, 0.01).outcome is Outcome.CORRECT
    assert ("fix", "both") in world.asked


def test_scoring_one_eye_against_a_stimulus_the_other_eye_sees_is_refused():
    """A dichoptic task that scores the blind eye.

    It runs, it records, and every trial is an abort for a reason no one can see in
    the data -- the animal was doing the task perfectly with the eye nobody scored.
    """
    trial = Trial(
        start="hold",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix", eye="left")],
        states=[
            State(
                "hold",
                enter=[
                    Show(Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3), eye="right"))
                ],
                go=[
                    On(Hold("fix", 0.02), Outcome.CORRECT),
                    On(After(0.5), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )
    assert "wrong-eye-criterion" in {f.code for f in check(trial)}


def test_an_unknown_eye_is_refused():
    """`eye='lft'` is not a criterion, and it would fail as a silent never-true."""
    trial = a_task("lft")
    assert "unknown-eye" in {f.code for f in check(trial)}
