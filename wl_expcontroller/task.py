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
    """How a trial ended.

    Two families. **Responses** are what the animal did about a stimulus, crossed
    with when: to the target or to a distractor, early, on time, or late. **Breaks**
    are the trial ending because a hold was not maintained -- of fixation, of the
    target, of a catch trial, or because the chair moved too much.

    `ABORT` is the residual and is deliberately not a break: the animal went
    somewhere that was neither target nor distractor, which is a different statement
    from failing to hold something.
    """

    # Responses to the target
    CORRECT = "correct"
    EARLY_RESPONSE = "early_response"
    LATE_RESPONSE = "late_response"

    # Responses to a distractor
    WRONG_TARGET = "wrong_target"
    EARLY_ERROR = "early_error"
    LATE_ERROR = "late_error"

    # Nothing at all
    NO_FIXATION = "no_fixation"
    NO_RESPONSE = "no_response"
    ABORT = "abort"

    # Breaks: a hold that was not maintained
    FIXATION_BREAK = "fixation_break"
    TARGET_BREAK = "target_break"
    CATCH_BREAK = "catch_break"
    MOTION_BREAK = "motion_break"


@dataclass(frozen=True, slots=True)
class Param:
    """One live-editable parameter: name, unit, and the range it may hold.

    The single declaration S8 §3.1 turns into validation, the console's widget,
    the per-trial snapshot and the ELN summary -- which is what makes live control
    work for a task nobody hand-wrote, with no per-task UI code.
    """

    name: str
    unit: str
    #: Numeric parameters carry a range; categorical ones carry `choices` instead.
    #: Categorical exists because **appearance is a parameter** -- swapping circles
    #: among squares for penguins among elephants is a value change, and a range
    #: cannot express it (S1a §4).
    low: float | None = None
    high: float | None = None
    choices: tuple = ()
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
class Entered(Guard):
    """Gaze entered a window and settled. Pairs with `Exited`."""

    window: str


@dataclass(frozen=True, slots=True)
class Exited(Guard):
    """Gaze left a window after acquiring it."""

    window: str


@dataclass(frozen=True, slots=True)
class Hold(Guard):
    """Gaze continuously inside a window for a duration. ML's `holdfix`.

    Imperative rather than past tense, because a task file describes what should
    happen rather than what did. Distinct from `Entered` followed by `After`, because the hold restarts if gaze
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
class Appearance:
    """What a stimulus looks like. Never what it is *for* -- that is its window.

    Separating the two is what lets a visual search task switch from circles among
    squares to penguins among elephants **without touching the task**: the structure
    is identical and only an appearance changes. Since appearance can be a parameter
    (§`Param.choices`), that switch is a value applied in an inter-trial interval
    rather than a new task or a new block.
    """


@dataclass(frozen=True, slots=True)
class Disc(Appearance):
    size: "float | P" = 1.0
    contrast: "float | P" = 1.0


@dataclass(frozen=True, slots=True)
class Square(Appearance):
    size: "float | P" = 1.0
    contrast: "float | P" = 1.0


@dataclass(frozen=True, slots=True)
class Bar(Appearance):
    """For receptive-field mapping."""

    length: "float | P" = 4.0
    width: "float | P" = 0.5
    orientation: "float | P" = 0.0
    contrast: "float | P" = 1.0


@dataclass(frozen=True, slots=True)
class Gabor(Appearance):
    """Field names throughout: `sf` is spatial frequency in cycles per degree,
    `sigma` the Gaussian envelope. A model writing
    `spatial_frequency_cycles_per_degree` has not read a methods section."""

    sf: "float | P" = 2.0
    orientation: "float | P" = 0.0
    phase: "float | P" = 0.0
    contrast: "float | P" = 1.0
    sigma: "float | P" = 1.0


@dataclass(frozen=True, slots=True)
class Dots(Appearance):
    """A random-dot kinematogram. `seed` is the stimulus: motion is a pure function
    of parameters, seed and frame index, so a trial reconstructs exactly (S4 §5)."""

    coherence: "float | P" = 0.5
    direction: "float | P" = 0.0
    speed: "float | P" = 5.0
    density: "float | P" = 1.0
    aperture: "float | P" = 5.0
    seed: int = 0


@dataclass(frozen=True, slots=True)
class Picture(Appearance):
    asset: str = ""
    size: "float | P" = 10.0


@dataclass(frozen=True, slots=True)
class Stimulus:
    """Something on the display: a position, an appearance, and how it is shown.

    **One class, because the structure of a task does not change when the things in
    it change.** Position is cyclopean degrees; the display module maps it to
    per-eye viewport pixels using measured optics, so a task never names a pixel and
    the same task runs at a different distance, on a different panel, in either
    display mode, and on the kiosk.
    """

    at: "tuple[float, float] | P"
    looks: "Appearance | P" = field(default_factory=Disc)
    disparity: "float | P" = 0.0
    #: `"both"`, `"left"` or `"right"`. Monocular and dichoptic presentation are
    #: first-class on a stereoscope: rivalry, monocular RF mapping and
    #: interocular-suppression designs all need one viewport to carry what the other
    #: does not. Distinct from disparity, which shifts one stimulus in both eyes.
    eye: str = "both"

    def per_eye(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Left and right image positions: equal and opposite horizontal offsets."""
        x, y = self.at
        half = self.disparity / 2.0
        return ((x - half, y), (x + half, y))


@dataclass(frozen=True, slots=True)
class Show(Action):
    """Put a stimulus on the display for as long as its state is current."""

    stimulus: Stimulus


@dataclass(frozen=True, slots=True)
class Score(Action):
    """Record a scored response *within* a trial (S1a §8).

    A trial emits scored events as it goes and the terminal outcome summarises. That
    is what lets a task express several correct targets -- *which* one was chosen is
    the thing the experiment is about, and it was previously not expressible anywhere
    -- and free viewing, where an animal moves between windows producing a sequence
    of responses rather than one.

    **The classification reuses `Outcome`**, because the same taxonomy applies at
    both grains: a single choice can be early, late, to a distractor or correct
    exactly as a whole trial can. A second vocabulary would have to be kept in step
    with this one for no gain.
    """

    window: str
    scored_as: Outcome


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

    def __init__(self, ref: "str | Bounded") -> None:
        if isinstance(ref, Bounded):
            ref = ref.name
        if not isinstance(ref, str):
            raise TypeError(
                f"Reward takes the name of a bounded-config entry, not "
                f"{type(ref).__name__}: a task may name how reward is configured "
                f"but never how much it is"
            )
        object.__setattr__(self, "ref", Bounded(ref))


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



# --- Shortcuts -------------------------------------------------------------
#
# Named constructors over `Stimulus`, not classes beside it. A fixation point is a
# small disc at the origin often enough that every task would otherwise spell it
# out, and "fix point" is the most-used phrase in the field -- so it earns a name
# without earning a type. Expect more of these; the rule is that a shortcut adds
# **defaults and a name**, never a concept, and anything it produces is an ordinary
# `Stimulus` the rest of the system cannot distinguish.


def FixPoint(
    at: "tuple[float, float] | P" = (0.0, 0.0), size: "float | P" = 0.3, **kwargs
) -> Stimulus:
    """A small disc at the origin: the fixation point."""
    return Stimulus(at=at, looks=Disc(size=size), **kwargs)
