"""The within-trial task representation.

Declarative data, not code (ADR-0006). A trial is states and guarded transitions;
`taskd` executes it and the task never owns the frame loop. Plain Python
declarations rather than a text DSL, so an ordinary editor gives autocomplete and
type checking -- and so a model authoring one is writing the language it writes best.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(Enum):
    """Terminal states. Real codes come from wl-mllib's allocation (S2); these
    names stand in until that allocation exists."""

    CORRECT = "correct"
    NO_FIXATION = "no_fixation"
    FIXATION_BREAK = "fixation_break"
    NO_RESPONSE = "no_response"
    WRONG_TARGET = "wrong_target"


@dataclass(frozen=True, slots=True)
class Param:
    """One live-editable parameter: name, unit, and the range it may hold.

    The single declaration S8 §3.1 turns into validation, the console's widget,
    the per-trial snapshot and the ELN summary -- which is what makes live control
    work for a task nobody hand-wrote, with no per-task UI code.
    """

    name: str
    unit: str
    low: float
    high: float
    live: bool = True


@dataclass(frozen=True, slots=True)
class P:
    """A reference to a declared parameter, usable anywhere a value is."""

    name: str


@dataclass(frozen=True, slots=True)
class Window:
    """A named region gaze, a joystick or a touch is tested against.

    Declared rather than referred to in passing: position and radius are exactly
    what an experimenter tunes, so both may be parameters, and a task naming a
    window nothing declares has no criterion at all.
    """

    name: str
    at: "tuple[float, float] | P"
    radius: "float | P"


@dataclass(frozen=True, slots=True)
class Guard:
    """Base for the guard vocabulary (S1 §2.2). A guard is data: the framework
    evaluates it, the task never does."""


@dataclass(frozen=True, slots=True)
class After(Guard):
    """Elapsed time from state entry, in seconds. The only guard that bounds a
    wait by construction -- which is why the checker asks about it by type."""

    seconds: "float | P"


@dataclass(frozen=True, slots=True)
class Acquired(Guard):
    """Gaze entered a window and settled. MonkeyLogic's `acquirefix`."""

    window: str


@dataclass(frozen=True, slots=True)
class Broke(Guard):
    """Gaze left a window after acquiring it. "The animal broke fixation." """

    window: str


@dataclass(frozen=True, slots=True)
class Held(Guard):
    """Gaze continuously inside a window for a duration. ML's `holdfix`.

    Distinct from `Acquired` followed by `After`, because the hold restarts if gaze
    leaves -- and because the staleness policy differs: a hold spanning a tracker
    stall is not a hold that was observed (S5 §4.1).
    """

    window: str
    seconds: "float | P"


@dataclass(frozen=True, slots=True)
class SaccadeTo(Guard):
    """A detected saccade landing in a window. Detection is the versioned
    Engbert-Kliegl component (S5 §5), never re-derived per task."""

    window: str


@dataclass(frozen=True, slots=True)
class SaccadeOnset(Guard):
    """A saccade began, wherever it lands. What a gaze-contingent update rides."""


@dataclass(frozen=True, slots=True)
class Onscreen(Guard):
    """The photodiode says the stimulus reached the display (S6 §3).

    Named for the world rather than for our intention, which is the whole
    distinction: a state waiting on `Onscreen` advances on evidence, not on the
    belief that a flip happened.
    """

    patch: str = "task"


@dataclass(frozen=True, slots=True)
class Pressed(Guard):
    device: str


@dataclass(frozen=True, slots=True)
class Released(Guard):
    device: str


@dataclass(frozen=True, slots=True)
class Touched(Guard):
    window: str


@dataclass(frozen=True, slots=True)
class ChairStill(Guard):
    """`wl-shook`'s motion gate: the chair is quiet enough to proceed."""


@dataclass(frozen=True, slots=True)
class RateAbove(Guard):
    """A neural feature over threshold. Tier-3 gating (S7); the decision stays in
    taskd, never in the feature client."""

    source: str
    threshold: float


@dataclass(frozen=True, slots=True)
class Response(Guard):
    device: str


@dataclass(frozen=True, slots=True)
class On:
    """One guarded transition: when `guard` fires, do `do`, then go to `to`.

    Actions belong on the transition rather than on the destination because the
    scoring action -- reward -- happens on the *edge* that scores. A terminal
    outcome has no state to enter, so an entry action could never express it.
    """

    guard: Guard
    to: "str | Outcome"
    do: list["Action"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class State:
    name: str
    enter: list[Action] = field(default_factory=list)
    go: list[On] = field(default_factory=list)
    #: Declared when a state deliberately has no time bound -- free viewing of
    #: natural images is the motivating case (S1 §5.4). The checker refuses an
    #: undeclared one, so an unbounded wait is always a choice on the record
    #: rather than an omission nobody noticed.
    unbounded: bool = False


@dataclass(frozen=True, slots=True)
class Trial:
    start: str
    states: list[State]
    params: list[Param] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Bounded:
    """A reference to an entry in the rig/subject bounded config (S8 §4).

    The task names it; it never holds the value. Resolution happens against the
    subject's ceiling at run time, in the process that also owns the accounting.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Action:
    """Base for the action vocabulary (S1 §2.3)."""


@dataclass(frozen=True, slots=True)
class Stimulus:
    """Declared in **cyclopean degrees**, with disparity as a property (S4 §2).

    A task never names a pixel: the display module maps cyclopean position to
    per-eye viewport pixels using measured optics. That is what lets one task run
    at a different viewing distance, on a different panel, in either display mode,
    and on the kiosk -- and it is why a monocular task is the zero-disparity case
    of the stereo path rather than a separate one.
    """

    at: "tuple[float, float] | P"
    disparity: float = 0.0
    #: `"both"`, `"left"` or `"right"`. Monocular and dichoptic presentation are
    #: first-class on a stereoscope: rivalry, monocular RF mapping and
    #: interocular-suppression designs all need one viewport to carry what the
    #: other does not. Distinct from disparity, which shifts one stimulus in both.
    eye: str = "both"

    def per_eye(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Left and right image positions: equal and opposite horizontal offsets."""
        x, y = self.at
        half = self.disparity / 2.0
        return ((x - half, y), (x + half, y))


@dataclass(frozen=True, slots=True)
class FixPoint(Stimulus):
    size: float = 0.3


@dataclass(frozen=True, slots=True)
class Spot(Stimulus):
    """A plain disc."""

    size: float = 1.0
    contrast: float = 1.0


@dataclass(frozen=True, slots=True)
class Gabor(Stimulus):
    """Field names throughout: `sf` is spatial frequency in cycles per degree,
    `sigma` the Gaussian envelope. A model writing
    `spatial_frequency_cycles_per_degree` has not read a methods section."""

    sf: "float | P" = 2.0
    orientation: "float | P" = 0.0
    phase: "float | P" = 0.0
    contrast: "float | P" = 1.0
    sigma: "float | P" = 1.0


@dataclass(frozen=True, slots=True)
class Dots(Stimulus):
    """A random-dot kinematogram. `seed` is the stimulus: motion is a pure function
    of parameters, seed and frame index, so a trial reconstructs exactly (S4 §5)."""

    coherence: "float | P" = 0.5
    direction: "float | P" = 0.0
    speed: "float | P" = 5.0
    density: "float | P" = 1.0
    aperture: "float | P" = 5.0
    seed: int = 0


@dataclass(frozen=True, slots=True)
class Bar(Stimulus):
    """For receptive-field mapping."""

    length: "float | P" = 4.0
    width: "float | P" = 0.5
    orientation: "float | P" = 0.0
    contrast: "float | P" = 1.0


@dataclass(frozen=True, slots=True)
class Image(Stimulus):
    asset: str = ""
    size: "float | P" = 10.0


@dataclass(frozen=True, slots=True)
class Show(Action):
    """Put a stimulus on the display for as long as its state is current."""

    stimulus: Stimulus


@dataclass(frozen=True, slots=True)
class Custom(Action):
    """Behaviour the vocabulary lacks, named rather than contained (S1 §8).

    Resolves to a reviewed component in the framework's own source. A task using
    one is flagged onto the human-review list beside the welfare-critical modules
    -- accepted is not the same as unremarkable.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Mark(Action):
    """Strobe an event code -- what ML and the field both call an *event marker*.

    The code is allocated elsewhere (S2, ADR-0007) and validated at load; a task
    naming an unallocated one is refused.
    """

    code: int


class Reward(Action):
    """Deliver reward, by bounded-config reference.

    **Refuses a magnitude, deliberately and at runtime.** A type checker catches
    `Reward(0.15)` too, but nothing guarantees one is running on the machine that
    loads a generated task -- and welfare bounds that depend on someone having run
    a linter are not bounds. See S8 §7's welfare-critical module list.
    """

    __slots__ = ("ref",)

    def __init__(self, ref: Bounded) -> None:
        if not isinstance(ref, Bounded):
            raise TypeError(
                f"Reward takes a bounded-config reference, not {type(ref).__name__}: "
                f"a task may name how reward is configured but never how much it is"
            )
        object.__setattr__(self, "ref", ref)


def actions_of(trial: Trial) -> list[tuple[str, Action]]:
    """Every action in a trial, with the state it belongs to.

    **Both places.** Actions sit on state entry and on transitions, and anything
    walking them must walk both -- reward can only ever be a transition action,
    because a terminal outcome has no state to enter. The first real task passed a
    checker with this gap while emitting an unallocated code, which is how it was
    found.

    One definition rather than two, because `check.py` and `review.py` both need
    it: a review artifact showing a different set of actions from the one the
    checker inspected would be the worst possible artifact -- a picture the
    reviewer trusts, of a task nobody validated.
    """
    found: list[tuple[str, Action]] = []
    for state in trial.states:
        found.extend((state.name, action) for action in state.enter)
        for edge in state.go:
            found.extend((state.name, action) for action in edge.do)
    return found
