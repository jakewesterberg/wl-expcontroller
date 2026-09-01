"""The within-trial task representation.

Declarative data, not code (ADR-0006). A trial is states and guarded transitions;
`taskd` executes it and the task never owns the frame loop. Plain Python
declarations rather than a text DSL, so an ordinary editor gives autocomplete and
type checking -- and so a model authoring one is writing the language it writes best.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from enum import Enum

from wl_expcontroller.photometry import Color


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

    # Correctly withholding, and failing to. **Without both, d' and criterion are
    # not computable** -- and not recoverable offline either, because a correct
    # rejection was previously indistinguishable from an animal that did nothing.
    CORRECT_REJECT = "correct_reject"
    FALSE_ALARM = "false_alarm"

    # Nothing at all
    NO_FIXATION = "no_fixation"
    NO_RESPONSE = "no_response"
    ABORT = "abort"

    # Breaks: a hold that was not maintained
    FIXATION_BREAK = "fixation_break"
    TARGET_BREAK = "target_break"
    CATCH_BREAK = "catch_break"
    MOTION_BREAK = "motion_break"
    #: A blink longer than the task tolerates. Behaviour, and separable from a
    #: fixation break because some tasks must not tolerate blinks at all.
    BLINK_BREAK = "blink_break"

    # The rig, not the animal. Kept apart from `ABORT` -- which means the animal
    # went somewhere that was neither target nor distractor -- because mixing them
    # makes a session's abort rate a number about two unrelated things, with no way
    # to tell whether to fix the animal or the camera.
    TRACKER_LOST = "tracker_lost"
    FAULT = "fault"


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
class Remembered:
    """The marker for a window with deliberately nothing in it.

    A memory-guided saccade scores gaze against a location the animal must hold in
    memory; the defining feature of the paradigm is that the display is blank there.
    That is indistinguishable, from the outside, from an author who forgot to show
    the stimulus -- so the two are made distinguishable by making one of them
    something you have to write down.
    """


REMEMBERED = Remembered()


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
    #: The stimulus this window scores, by name -- or `REMEMBERED` when nothing is
    #: displayed there on purpose. **Unset is refused at load**, because the whole
    #: value of the coupling is that "nothing is there" has to be a claim someone
    #: made rather than a state the task fell into. With it, a hold on a window
    #: whose stimulus is not on the display is a load-time error instead of a
    #: silently different experiment (S1a §11).
    on: "str | Remembered | None" = None
    #: `"both"`, `"left"` or `"right"`. The tracker is binocular (architecture
    #: §1: 500 Hz binocular dDPI), so a per-eye criterion is available and is the
    #: correct primitive on a stereoscope: under dichoptic presentation the
    #: non-viewing eye drifts, and scoring it against a conjugate estimate scores
    #: an average of one eye doing the task and one eye doing nothing.
    eye: str = "both"


@dataclass(frozen=True, slots=True)
class Guard:
    """Base for the guard vocabulary (S1 §2.2). A guard is data: the framework
    evaluates it, the task never does."""


@dataclass(frozen=True, slots=True)
class After(Guard):
    """Elapsed time in seconds, from state entry by default.

    **`since` moves the zero.** Timed from state entry, an interval starts before the
    stimulus it follows exists: the transition happens during a frame and the flip
    that carries the stimulus is 8-33 ms later, depending on refresh rate and where
    in the frame the transition landed. Every SOA written that way is wrong by a
    variable amount -- and variable error is worse than constant error, because it
    cannot be corrected offline. `After(0.05, since=Onscreen("task"))` runs from the
    photodiode saying the stimulus reached the display.

    A plain `After` is the only guard that bounds a wait by construction, which is
    why the checker asks about it by type. **One with a `since` is not**: if the flip
    is dropped or the patch occluded, the guard never arms, so a state relying on it
    alone could wait forever -- and check 4 refuses that.
    """

    seconds: "float | P"
    #: What starts the clock. `None` is state entry.
    since: "Guard | None" = None


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
class FeatureAbove(Guard):
    """A neural feature over threshold. Tier-3 gating (S7); the decision stays in
    `taskd`, never in the feature client.

    Named for the *feature* rather than for a rate, because `FeatureSource` publishes
    whichever of the two feature types an experiment chose (S7 §5) and may one day
    publish something that is not a rate at all -- a phase, a decoder output.
    """

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
class Tolerances:
    """How long the gaze signal may be interrupted before the trial ends.

    **Two graces, because they are two phenomena.** A blink is the animal; tracker
    loss is the rig. They look identical in the data -- gaze leaves the window -- so
    scoring both as fixation breaks inflates a session's break rate with equipment
    failure, invisibly, and an animal looks worse than it is.

    `blink` defaults to zero: a task that tolerates blinks says so, because the other
    way round a task inherits a tolerance nobody chose and reports holds that were
    never observed. `tracker_lost` defaults to 50 ms, which is P6's **measured**
    stall maximum for OpenIrisDPI (~2% of frames >= 10 ms, max ~50 ms) -- that is the
    tracker's behaviour, not the animal's, and blaming the animal for it would cost
    roughly one trial in every few.

    `None` switches enforcement off, explicitly: a joystick-only task has no gaze
    criterion to protect and should not abort because a camera nobody is using
    dropped out.
    """

    blink: "float | P | None" = 0.0
    tracker_lost: "float | P | None" = 0.05


@dataclass(frozen=True, slots=True)
class Trial:
    start: str
    states: list[State]
    params: list[Param] = field(default_factory=list)
    #: Hand-written windows and `ItemWindows` families, in one list: a window is a
    #: window whether an author typed it or an array generated it, and keeping them
    #: apart would mean every check that walks windows had to walk two lists.
    windows: "list[Window | ItemWindows]" = field(default_factory=list)
    tolerances: "Tolerances" = field(default_factory=lambda: Tolerances())


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
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Square(Appearance):
    size: "float | P" = 1.0
    contrast: "float | P" = 1.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Bar(Appearance):
    """For receptive-field mapping."""

    length: "float | P" = 4.0
    width: "float | P" = 0.5
    orientation: "float | P" = 0.0
    contrast: "float | P" = 1.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


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
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


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
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Annulus(Appearance):
    inner: "float | P" = 1.0
    outer: "float | P" = 2.0
    contrast: "float | P" = 1.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Cross(Appearance):
    """A plus sign. The other thing people fixate, besides a disc."""

    size: "float | P" = 0.5
    thickness: "float | P" = 0.1
    contrast: "float | P" = 1.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Polygon(Appearance):
    """`sides=3` a triangle, `sides=4` a diamond, and so on. One appearance rather
    than a class per shape -- the same reasoning that produced `Stimulus`."""

    sides: int = 3
    size: "float | P" = 1.0
    orientation: "float | P" = 0.0
    contrast: "float | P" = 1.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Grating(Appearance):
    """A grating in a hard aperture. Distinct from `Gabor`, whose envelope is
    Gaussian -- the difference matters for edge artifacts and for spatial-frequency
    bandwidth, which is why the field names them separately."""

    sf: "float | P" = 2.0
    orientation: "float | P" = 0.0
    phase: "float | P" = 0.0
    contrast: "float | P" = 1.0
    aperture: "float | P" = 5.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Plaid(Appearance):
    """Two superimposed gratings. `angle` is the separation between components."""

    sf: "float | P" = 2.0
    orientation: "float | P" = 0.0
    angle: "float | P" = 90.0
    contrast: "float | P" = 1.0
    aperture: "float | P" = 5.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Checkerboard(Appearance):
    """RF mapping and evoked potentials."""

    check_size: "float | P" = 1.0
    contrast: "float | P" = 1.0
    aperture: "float | P" = 10.0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Noise(Appearance):
    """`exponent` 0 is white, 1 is pink, 2 is brown. `seed` is the stimulus, so a
    trial reconstructs exactly; `refresh_hz` above zero makes it dynamic."""

    exponent: "float | P" = 1.0
    contrast: "float | P" = 1.0
    aperture: "float | P" = 5.0
    refresh_hz: "float | P" = 0.0
    seed: int = 0
    #: Device-independent colour, or `None` for achromatic at `contrast`. On the
    #: appearance rather than the stimulus because colour is a feature: "red among
    #: green" and "circles among squares" are then the same kind of switch, and both
    #: are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Picture(Appearance):
    asset: str = ""
    size: "float | P" = 10.0


@dataclass(frozen=True, slots=True)
class Movie(Appearance):
    asset: str = ""
    size: "float | P" = 10.0
    loop: bool = False


@dataclass(frozen=True, slots=True)
class Blank(Appearance):
    """Nothing. A catch trial's stimulus is not the absence of a `Show` -- it is a
    `Show` of nothing, which is what makes catch and non-catch trials structurally
    identical and therefore comparable."""


@dataclass(frozen=True, slots=True)
class Form:
    """A disparity field across a patch: depth at every point, not one number.

    `Stimulus.disparity` displaces a whole stimulus, which is position disparity and
    nothing else. Everything the 3D-shape and surface literature is built on -- a
    slant, a curvature, a corrugation -- is a *field*, and a patch carrying one has
    no single disparity to displace by.
    """

    def range(self, values: dict) -> "tuple[float, float]":
        """The least and greatest disparity this form reaches, in degrees."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Corrugation(Form):
    """A sinusoidal depth grating: the standard probe for disparity-defined shape.

    `sf` is in cycles per degree of visual angle, `amplitude` the peak disparity in
    degrees, `orientation` the corrugation's axis in degrees.
    """

    sf: "float | P" = 0.5
    amplitude: "float | P" = 0.1
    orientation: "float | P" = 0.0
    phase: "float | P" = 0.0

    def range(self, values: dict) -> "tuple[float, float]":
        peak = abs(float(_value(self.amplitude, values)))
        return (-peak, peak)


@dataclass(frozen=True, slots=True)
class Slant(Form):
    """A planar disparity gradient, in degrees of disparity per degree of position.

    The extreme disparity depends on how wide the patch is, so `range` is answered
    against the aperture rather than reported on its own -- an amplitude quoted
    without the aperture it spans is not a quantity.
    """

    gradient: "float | P" = 0.05
    orientation: "float | P" = 0.0

    def range(self, values: dict, aperture: float = 0.0) -> "tuple[float, float]":
        reach = abs(float(_value(self.gradient, values))) * aperture / 2.0
        return (-reach, reach)


@dataclass(frozen=True, slots=True)
class RDS(Appearance):
    """A random-dot stereogram: form carried by binocular disparity alone.

    **`correlation` is why this is its own appearance.** +1 is an ordinary
    stereogram, 0 is uncorrelated noise, and **-1 is anticorrelated** -- dots of
    opposite contrast in the two eyes. That is the control condition every disparity
    paper is asked for, because V1 responds to it while perceived depth inverts or
    vanishes, so it separates a correlation-based response from a depth-based one.
    There is no way to express it by displacing a stimulus, which is all
    `Stimulus.disparity` can do.

    A parameter, so correlated and anticorrelated conditions interleave within a
    session. Comparing them across sessions compares two states of the animal.

    `seed` is the stimulus: the dot field is a pure function of parameters, seed and
    frame index, so a trial reconstructs exactly (S4 §5).
    """

    correlation: "float | P" = 1.0
    #: Internal depth structure, or `None` for a frontoparallel patch at whatever
    #: disparity the stimulus carries.
    form: "Form | None" = None
    density: "float | P" = 1.0
    dot_size: "float | P" = 0.1
    aperture: "float | P" = 5.0
    contrast: "float | P" = 1.0
    seed: int = 0
    color: "Color | P | None" = None

    def disparity_range(self, values: dict) -> "tuple[float, float]":
        """The least and greatest disparity anywhere in this patch.

        What check 8 needs: a patch centred safely can still push one eye's image
        off the panel at the extreme of its corrugation, and only that eye's.
        """
        if self.form is None:
            return (0.0, 0.0)
        if isinstance(self.form, Slant):
            return self.form.range(values, float(_value(self.aperture, values)))
        return self.form.range(values)


@dataclass(frozen=True, slots=True)
class Array(Appearance):
    """`n` items evenly spaced on a ring, one of them the target.

    **This exists so that set size is a value.** Written the obvious way -- an
    N-item array as N separate `Show` actions -- set size becomes a change to the
    *shape* of the task: a different task file for four items and eight, unavailable
    to live editing, and untouchable by a parameter. That is the commonest
    manipulation in visual search, and visual search is the lab's programme.

    An appearance rather than an action, so the whole array is **one named stimulus**
    on the display. The rest of the system -- `Hide`, `Update`, the visibility
    analysis, the review artifact -- then needs to know nothing about arrays.
    """

    n: "int | P" = 4
    radius: "float | P" = 8.0
    #: Index of the target within the ring. A parameter, so target position is
    #: manipulable between trials like anything else.
    target: "int | P" = 0
    looks: "Appearance | P" = field(default_factory=Disc)
    #: What the other items look like. Target and distractors differing in exactly
    #: one property is what makes this a feature-search array rather than a
    #: collection of unrelated shapes -- and `looks`/`among` being parameters is what
    #: makes "red among green" and "circle among squares" the same task.
    among: "Appearance | P" = field(default_factory=Disc)
    #: Where item 0 sits, in degrees counter-clockwise from the positive x axis.
    #: Randomising it between trials is what stops an animal learning positions.
    phase: "float | P" = 0.0

    def positions(self, values: dict) -> "list[tuple[float, float]]":
        """Item centres, in cyclopean degrees relative to the stimulus position."""
        n = int(_value(self.n, values))
        radius = float(_value(self.radius, values))
        phase = math.radians(float(_value(self.phase, values)))
        return [
            (
                radius * math.cos(phase + 2 * math.pi * i / n),
                radius * math.sin(phase + 2 * math.pi * i / n),
            )
            for i in range(n)
        ]

    def item_looks(self, index: int, values: dict) -> "Appearance | P":
        target = int(_value(self.target, values))
        return self.looks if index == target else self.among


def _value(value, values: dict):
    """A parameter reference against bound values, for expansion.

    Missing is an error rather than a default, for the reason `run._resolve` gives:
    a set size that silently became zero would draw an empty screen, and an empty
    screen reads as an animal who will not work.
    """
    if isinstance(value, P):
        if value.name not in values:
            raise KeyError(f"no value bound for parameter {value.name!r}")
        return values[value.name]
    return value


@dataclass(frozen=True, slots=True)
class ItemWindows:
    """The per-item windows an `Array` needs, declared once.

    One declaration rather than n, because n is not known until a trial runs. It
    generates `<of>.<i>` per item plus two aliases: **`<of>.target`**, and
    **`<of>.distractor`**, which is satisfied by any non-target item.

    The distractor alias is the point. Without it, every error saccade would have to
    be enumerated as one transition per item -- which is the same structure-versus-
    value problem one level down, and it would make the measurement search tasks
    exist to produce, target-versus-distractor, unavailable.
    """

    of: str
    radius: "float | P"
    eye: str = "both"

    def expand(self, array: Array, values: dict) -> "list[Window]":
        at = array.positions(values)
        target = int(_value(array.target, values))
        windows = [
            Window(f"{self.of}.{i}", at=xy, radius=self.radius, on=self.of, eye=self.eye)
            for i, xy in enumerate(at)
        ]
        windows.append(
            Window(
                f"{self.of}.target",
                at=at[target],
                radius=self.radius,
                on=self.of,
                eye=self.eye,
            )
        )
        windows.append(
            Window(
                f"{self.of}.distractor",
                at=at[target],  # nominal; membership is the union of the others
                radius=self.radius,
                on=self.of,
                eye=self.eye,
            )
        )
        return windows

    def members(self, array: Array, values: dict) -> "dict[str, tuple[str, ...]]":
        """Alias name to the concrete item windows that satisfy it."""
        n = len(array.positions(values))
        target = int(_value(array.target, values))
        return {
            f"{self.of}.target": (f"{self.of}.{target}",),
            f"{self.of}.distractor": tuple(
                f"{self.of}.{i}" for i in range(n) if i != target
            ),
        }


@dataclass(frozen=True, slots=True)
class Stimulus:
    """Something on the display: a position, an appearance, and how it is shown.

    **One class, because the structure of a task does not change when the things in
    it change.** Position is cyclopean degrees; the display module maps it to
    per-eye viewport pixels using measured optics, so a task never names a pixel and
    the same task runs at a different distance, on a different panel, in either
    display mode, and on the kiosk.
    """

    #: The handle. `Hide` and `Update` address a stimulus by it, a `Window` names
    #: the one it scores, and the review artifact labels the timeline with it.
    #: Positional and required: an anonymous stimulus can be put up and never
    #: referred to again, which is the whole of what went wrong.
    name: str
    at: "tuple[float, float] | P"
    looks: "Appearance | P" = field(default_factory=Disc)
    disparity: "float | P" = 0.0
    #: `"both"`, `"left"` or `"right"`. Monocular and dichoptic presentation are
    #: first-class on a stereoscope: rivalry, monocular RF mapping and
    #: interocular-suppression designs all need one viewport to carry what the other
    #: does not. Distinct from disparity, which shifts one stimulus in both eyes.
    eye: str = "both"

    # No `per_eye()` here. Mapping a cyclopean position to two viewport positions
    # needs the vergence offset and each eye's *measured* optical path (S4 §2,
    # optics drawing §6), which live in the display module and not in a task. An
    # earlier version of this class carried one; it was deleted when the mutation
    # harness reported it as covered by nothing, having been left behind when
    # check 8 moved to reasoning over parameter *ranges* rather than values.


class Unchanged:
    """`Update`'s "leave this alone", which `None` cannot mean.

    `None` is a legal value for several stimulus properties, so a default of `None`
    would make "set it to nothing" and "do not touch it" the same instruction.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNCHANGED"


UNCHANGED = Unchanged()


@dataclass(frozen=True, slots=True)
class Show(Action):
    """Put a stimulus on the display. **It stays until `Hide` or the end of the
    trial** -- not until its state ends.

    State-scoped presentation was the original wording and it was wrong in a way no
    check could see: the reference task shows a fixation point in one state and asks
    for a hold on it in the next, so the point was removed at the exact frame the
    animal was asked to hold it. The task was written correctly and passed all ten
    checks. Persistence also makes `Hide` and `Update` mean something, which
    state-scoping did not.
    """

    stimulus: Stimulus


@dataclass(frozen=True, slots=True)
class Hide(Action):
    """Take a stimulus off the display, by name."""

    stimulus: str


@dataclass(frozen=True, slots=True)
class Update(Action):
    """Change properties of a stimulus already on the display, without an offset.

    Change detection, apparent motion and gaze-contingent updating all need one
    uninterrupted presentation with one property different. `Hide` followed by
    `Show` inserts an offset transient and at least one blank frame -- which is the
    exact confound those paradigms are built to avoid, so expressing them that way
    would be expressing a different experiment.
    """

    stimulus: str
    at: "tuple[float, float] | P | Unchanged" = UNCHANGED
    looks: "Appearance | P | Unchanged" = UNCHANGED
    disparity: "float | P | Unchanged" = UNCHANGED
    eye: "str | Unchanged" = UNCHANGED

    def changes(self) -> dict:
        """The properties this actually sets. Empty means the action does nothing,
        which the checker refuses."""
        return {
            field_name: value
            for field_name, value in (
                ("at", self.at),
                ("looks", self.looks),
                ("disparity", self.disparity),
                ("eye", self.eye),
            )
            if not isinstance(value, Unchanged)
        }


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
    name: str = "fix",
    at: "tuple[float, float] | P" = (0.0, 0.0),
    size: "float | P" = 0.3,
    **kwargs,
) -> Stimulus:
    """A small disc at the origin: the fixation point."""
    return Stimulus(name=name, at=at, looks=Disc(size=size), **kwargs)


def arrays_of(trial: Trial) -> "dict[str, Array]":
    """Every array stimulus a trial can show, by stimulus name."""
    return {
        action.stimulus.name: action.stimulus.looks
        for _, action in actions_of(trial)
        if isinstance(action, Show) and isinstance(action.stimulus.looks, Array)
    }


def expand_windows(
    trial: Trial, values: dict
) -> "tuple[list[Window], dict[str, tuple[str, ...]]]":
    """A trial's windows with every array family expanded, plus alias membership.

    One definition, used by the runner and the checker both, for the reason
    `actions_of` gives: a checker that inspected a different set of windows from the
    one the loop scores would be validating a task nobody runs.
    """
    arrays = arrays_of(trial)
    windows: list[Window] = []
    aliases: dict[str, tuple[str, ...]] = {}
    for declared in trial.windows:
        if isinstance(declared, ItemWindows):
            array = arrays.get(declared.of)
            if array is None:
                continue
            windows.extend(declared.expand(array, values))
            aliases.update(declared.members(array, values))
        else:
            windows.append(declared)
    return windows, aliases
