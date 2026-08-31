"""Load-time checks (S1 §9). A task failing any of these is refused at load."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from wl_expcontroller.codes import PROVISIONAL, Allocation
from wl_expcontroller.components import Registry
from wl_expcontroller.geometry import Geometry
from wl_expcontroller.photometry import DKL, Calibration, Color, unrealizable, xyY
from wl_expcontroller.task import (
    RDS,
    After,
    Array,
    ItemWindows,
    Custom,
    Entered,
    Exited,
    Hide,
    Hold,
    Mark,
    Outcome,
    P,
    Remembered,
    SaccadeTo,
    Show,
    Touched,
    Trial,
    Update,
    Window,
    actions_of,
    arrays_of,
)


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    detail: str
    #: Whether this refuses the load. A non-blocking finding still surfaces -- a
    #: `Custom` component is legitimate and still belongs on the review list.
    blocking: bool = True


def check(
    trial: Trial,
    allocation: Allocation = PROVISIONAL,
    components: Registry | None = None,
    geometry: Geometry | None = None,
    calibration: Calibration | None = None,
) -> list[Finding]:
    return (
        _unreachable_states(trial)
        + _unbounded_waits(trial)
        + _states_with_no_outcome_path(trial)
        + _shadowed_transitions(trial)
        + _unallocated_codes(trial, allocation)
        + _undeclared_parameters(trial)
        + _custom_components(trial, components or Registry())
        + _offscreen_stimuli(trial, geometry)
        + _unallocated_outcomes(trial, allocation)
        + _undeclared_windows(trial)
        + _uncoupled_windows(trial)
        + _display_faults(trial)
        + _color_faults(trial, calibration)
        + _array_faults(trial)
        + _stereogram_faults(trial)
        + _eye_faults(trial)
    )


def _unreachable_states(trial: Trial) -> list[Finding]:
    """S1 §9 check 2: every state is reachable from the start state."""
    by_name = {state.name: state for state in trial.states}
    seen: set[str] = set()
    frontier = [trial.start]
    while frontier:
        name = frontier.pop()
        if name in seen or name not in by_name:
            continue
        seen.add(name)
        frontier.extend(
            edge.to for edge in by_name[name].go if isinstance(edge.to, str)
        )
    return [
        Finding("unreachable-state", f"no transition reaches {name!r}")
        for name in (s.name for s in trial.states)
        if name not in seen
    ]


def _unbounded_waits(trial: Trial) -> list[Finding]:
    """S1 §9 check 4: every wait has a time bound, or says it has none.

    The S1 bake-off produced exactly this defect while writing the permissive
    form of a fixation task -- a hold loop with no timeout, invisible on reading.
    A state whose transitions are all event-guarded can wait forever if the event
    never arrives, which for a fixation hold means an animal that has looked away.
    """
    return [
        Finding(
            "unbounded-wait",
            f"state {state.name!r} has no `After` transition and does not "
            f"declare `unbounded=True`",
        )
        for state in trial.states
        if not state.unbounded
        and not any(isinstance(edge.guard, After) for edge in state.go)
    ]


def _states_with_no_outcome_path(trial: Trial) -> list[Finding]:
    """S1 §9 check 3: from every state, some path reaches a terminal outcome.

    Reachability run backwards. A state that cannot reach an outcome is a trap:
    the trial never scores, never ends, and never says why -- it simply stops
    producing trials while the console still shows a session running.
    """
    by_name = {state.name: state for state in trial.states}
    escapes: set[str] = set()
    changed = True
    while changed:
        changed = False
        for state in trial.states:
            if state.name in escapes:
                continue
            if any(
                isinstance(edge.to, Outcome) or edge.to in escapes
                for edge in state.go
            ):
                escapes.add(state.name)
                changed = True
    return [
        Finding(
            "no-outcome-path",
            f"state {name!r} cannot reach any terminal outcome",
        )
        for name in by_name
        if name not in escapes
    ]


def _shadowed_transitions(trial: Trial) -> list[Finding]:
    """S1 §9 check 10, in the form it takes once order is defined.

    The check was written as "no two transitions can fire on the same frame
    without a declared priority." Transitions now fire in **declared order**
    (M0 §4), which resolves the ambiguity that phrasing was worried about --
    so what is left to detect is the decidable half: a guard repeated on one
    state means every later copy is unreachable.

    That is dead code rather than a race, and it is a shape a generated task
    produces readily, since repeating a guard with a different destination looks
    entirely reasonable in isolation.
    """
    findings: list[Finding] = []
    for state in trial.states:
        seen: set[object] = set()
        for edge in state.go:
            if edge.guard in seen:
                findings.append(
                    Finding(
                        "shadowed-transition",
                        f"state {state.name!r} repeats guard {edge.guard!r}; "
                        f"the later transition can never fire",
                    )
                )
            seen.add(edge.guard)
    return findings


def _unallocated_codes(trial: Trial, allocation: Allocation) -> list[Finding]:
    """S1 §9 check 1: every event code a task names exists in the allocation.

    The cheapest guardrail in the design against a model-authored task (P15), and
    the one that fails loudest. A model asked for a stimulus-onset code will emit a
    plausible number; nothing about 4097 looks wrong on the page, and the recording
    it produces carries timing with no meaning. The allocation is the only thing
    that knows.

    Refused at **load** rather than at run: the point is to catch it before an
    animal is in the chair, not when the first trial strobes.
    """
    return [
        Finding(
            "unallocated-code",
            f"state {name!r} emits code {action.code}, which is not in the "
            f"allocation; codes are allocated in wl-mllib, never invented in a task",
        )
        for name, action in actions_of(trial)
        if isinstance(action, Mark) and action.code not in allocation
    ]


def _iter_param_refs(value: object) -> list[P]:
    """Every parameter reference anywhere inside a value.

    Walks dataclass fields generically rather than knowing the guard and action
    vocabularies, so a new vocabulary member is covered by this check the day it
    is added rather than the day someone remembers to update a list here.
    """
    if isinstance(value, P):
        return [value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        found: list[P] = []
        for f in dataclasses.fields(value):
            found.extend(_iter_param_refs(getattr(value, f.name)))
        return found
    if isinstance(value, (list, tuple)):
        return [ref for item in value for ref in _iter_param_refs(item)]
    return []


def _undeclared_parameters(trial: Trial) -> list[Finding]:
    """S1 §9 check 6: every parameter a task references is declared.

    An undeclared reference has no range, no widget and no place in the per-trial
    snapshot -- so it is either live-editable to any value or not editable at all,
    and nothing distinguishes the two from the task file.
    """
    declared = {param.name for param in trial.params}
    findings: list[Finding] = []
    for state in trial.states:
        for ref in _iter_param_refs(state):
            if ref.name not in declared:
                findings.append(
                    Finding(
                        "undeclared-parameter",
                        f"state {state.name!r} references parameter "
                        f"{ref.name!r}, which the task does not declare",
                    )
                )
    return findings


def _custom_components(trial: Trial, components: Registry) -> list[Finding]:
    """S1 §9 check 9: every `Custom` component resolves to reviewed framework code.

    Two findings rather than one, because they are different statements. A name
    that resolves to nothing **refuses the load** -- the seam is being used as a
    hole, and the behaviour would simply not exist at run time. A name that does
    resolve is **accepted and flagged**: using the seam is legitimate and still
    puts the task on the human-review list beside the welfare-critical modules.
    """
    findings: list[Finding] = []
    for name, action in actions_of(trial):
        if not isinstance(action, Custom):
            continue
        if action.name in components:
            findings.append(
                Finding(
                    "custom-component-needs-review",
                    f"state {name!r} uses custom component "
                    f"{action.name!r}; this task needs human review",
                    blocking=False,
                )
            )
        else:
            findings.append(
                Finding(
                    "unresolved-custom-component",
                    f"state {name!r} names custom component "
                    f"{action.name!r}, which resolves to no reviewed component",
                )
            )
    return findings


def _extremes(value: object, ranges: dict[str, tuple[float, float]]) -> list[float]:
    """The values a position component can actually take.

    A literal is itself; a parameter is **both ends of its declared range**, because
    every value between them is one an experimenter can dial in live. Checking the
    range rather than a value proves the task cannot place a stimulus off-screen for
    any legal setting, instead of proving it happens not to today.
    """
    if isinstance(value, P):
        low, high = ranges.get(value.name, (0.0, 0.0))
        return [low, high]
    return [float(value)]


def _offscreen_stimuli(trial: Trial, geometry: Geometry | None) -> list[Finding]:
    """S1 §9 check 8: every stimulus can actually be shown.

    Checked **per eye, after disparity**, not at the cyclopean position. Disparity is
    applied as equal and opposite horizontal offsets, so a stimulus comfortably inside
    the field can still put one eye's image outside it -- and only that eye's. On a
    split-screen stereoscope that is a stimulus the animal fuses on one side and loses
    on the other, a far stranger failure than simply not seeing it.

    Skipped when no geometry is supplied: a task is not wrong for being checked
    without a rig, it is unchecked, and the caller knows which it wanted.
    """
    if geometry is None:
        return []
    ranges = {
        p.name: (p.low, p.high)
        for p in trial.params
        if p.low is not None and p.high is not None
    }
    findings: list[Finding] = []
    for name, action in actions_of(trial):
        if not isinstance(action, Show):
            continue
        stimulus = action.stimulus
        x_values = _extremes(stimulus.at[0], ranges)
        y_values = _extremes(stimulus.at[1], ranges)
        if isinstance(stimulus.looks, Array):
            # An array's items sit on a ring around the stimulus position, so the
            # thing that can leave the field is an *item*, never the centre. The
            # extreme is the widest legal radius: with n a parameter too, every
            # smaller set is a subset of those positions.
            widest = max(_extremes(stimulus.looks.radius, ranges))
            x_values = [x + dx for x in x_values for dx in (widest, -widest, 0.0)]
            y_values = [y + dy for y in y_values for dy in (widest, -widest, 0.0)]
        half = _extremes(stimulus.disparity, ranges)
        if isinstance(stimulus.looks, RDS):
            # A disparity *field* has no single value to displace by, so the
            # extremes of the form are added to the stimulus's own disparity: a
            # patch centred safely can still push one eye's image off the panel at
            # the extreme of its corrugation, and only that eye's.
            try:
                low, high = stimulus.looks.disparity_range(
                    {name: bounds[1] for name, bounds in ranges.items()}
                )
            except (KeyError, TypeError):
                low, high = (0.0, 0.0)
            half = [value + reach for value in half for reach in (low, high)]
        bad = [
            (x + offset, y)
            for x in x_values
            for y in y_values
            for offset in (min(half) / 2, -min(half) / 2, max(half) / 2, -max(half) / 2)
            if not geometry.can_show(x + offset, y)
        ]
        if not bad:
            continue
        described = ", ".join(
            f"{v.name}" if isinstance(v, P) else f"{v:g}"
            for v in (stimulus.at[0], stimulus.at[1])
        )
        findings.append(
            Finding(
                "stimulus-off-screen",
                f"state {name!r} shows a stimulus at ({described}) which can reach "
                f"{bad[0][0]:.1f}, {bad[0][1]:.1f} -- outside the "
                f"\u00b1{geometry.half_field_h_deg:.1f}\u00b0 \u00d7 "
                f"\u00b1{geometry.half_field_v_deg:.1f}\u00b0 field"
                + (
                    f", with disparity {stimulus.disparity}"
                    if stimulus.disparity
                    else ""
                ),
            )
        )
    return findings

def _unallocated_outcomes(trial: Trial, allocation: Allocation) -> list[Finding]:
    """S1 §9 check 5: every terminal outcome maps to an allocated marker.

    An outcome with no marker is a trial that ends without saying how: the
    recording carries the timing of a decision whose result exists only in our
    files, and the pairing between the two is exactly what the hardware-truth rule
    exists to avoid depending on.
    """
    seen: list[object] = []
    for state in trial.states:
        for edge in state.go:
            if isinstance(edge.to, Outcome) and edge.to not in seen:
                seen.append(edge.to)
    return [
        Finding(
            "unallocated-outcome",
            f"outcome {outcome.name} maps to no allocated marker",
        )
        for outcome in seen
        if outcome not in allocation.outcomes
    ]


def _window_refs(value: object) -> list[str]:
    """Window names referenced anywhere. Walks generically, like `_iter_param_refs`,
    so a new guard naming a window is covered the day it is added."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        found: list[str] = []
        for f in dataclasses.fields(value):
            attribute = getattr(value, f.name)
            if f.name == "window" and isinstance(attribute, str):
                found.append(attribute)
            else:
                found.extend(_window_refs(attribute))
        return found
    if isinstance(value, (list, tuple)):
        return [name for item in value for name in _window_refs(item)]
    return []


def _undeclared_windows(trial: Trial) -> list[Finding]:
    """S1a §1: every window a task names is declared.

    A task referring to a gaze window nothing declares has no fixation criterion --
    no position, no radius, nothing an experimenter can tune. It is the same defect
    as an undeclared parameter and would read just as reasonably in a generated file.
    """
    declared = _declared_window_names(trial)
    findings: list[Finding] = []
    for state in trial.states:
        for name in _window_refs(state):
            if name not in declared:
                findings.append(
                    Finding(
                        "undeclared-window",
                        f"state {state.name!r} references window {name!r}, "
                        f"which the task does not declare",
                    )
                )
    return findings


# --- What is on the display ------------------------------------------------
#
# Every check above this line inspects the transition graph. None of them models
# the screen, so the class of defect they cannot see is "correct graph, wrong
# experiment" -- and the first reference task carried one: it showed a fixation
# point in one state and asked for a hold on it in the next, which under the
# original state-scoped `Show` removed the point at the exact frame the animal was
# asked to hold it. Ten checks passed. Found by review 2026-08-31.


def _uncoupled_windows(trial: Trial) -> list[Finding]:
    """Every window says what it scores, or says `REMEMBERED`.

    Unset cannot be allowed to mean "nothing there": that would make the
    nothing-to-look-at check opt-in, and the tasks most likely to skip it are the
    ones written fastest. A memory-guided saccade is a real paradigm and its blank
    location is the point -- so it is spelled out rather than defaulted into.
    """
    return [
        Finding(
            "uncoupled-window",
            f"window {window.name!r} does not say which stimulus it scores; give it "
            f"on='<stimulus>', or on=REMEMBERED if nothing is displayed there",
        )
        for window in trial.windows
        # An `ItemWindows` family always couples to its array, by construction.
        if not isinstance(window, ItemWindows) and window.on is None
    ]


def _visible_on_entry(trial: Trial) -> dict[str, frozenset[str]]:
    """For each state, the stimuli on the display on *every* path into it.

    A **must** analysis, not a may: visible on some route in is not visible. A task
    whose one branch shows the target and whose other does not works for a hundred
    trials and then scores a hold against a blank screen on the branch nobody ran.

    Iterated to a fixpoint over the graph rather than walked once, because states
    reachable by several routes -- and cycles, which the vocabulary permits -- have
    no single predecessor to inherit from.
    """
    every = frozenset(
        action.stimulus.name for _, action in actions_of(trial) if isinstance(action, Show)
    )
    by_name = {state.name: state for state in trial.states}
    entry: dict[str, frozenset[str]] = {
        name: (frozenset() if name == trial.start else every) for name in by_name
    }

    def after(visible: frozenset[str], actions: list) -> frozenset[str]:
        for action in actions:
            if isinstance(action, Show):
                visible = visible | {action.stimulus.name}
            elif isinstance(action, Hide):
                visible = visible - {action.stimulus}
        return visible

    for _ in range(len(by_name) + 1):
        arriving: dict[str, list[frozenset[str]]] = {name: [] for name in by_name}
        for state in trial.states:
            leaving = after(entry[state.name], state.enter)
            for edge in state.go:
                if isinstance(edge.to, Outcome):
                    continue
                arriving[edge.to].append(after(leaving, edge.do))
        settled = {
            name: (
                frozenset()
                if name == trial.start
                else frozenset.intersection(*inbound) if inbound else frozenset()
            )
            for name, inbound in arriving.items()
        }
        if settled == entry:
            break
        entry = settled
    return entry


def _display_faults(trial: Trial) -> list[Finding]:
    """Guards and actions checked against what is actually on the screen."""
    scores = _coupling(trial)
    entry = _visible_on_entry(trial)
    findings: list[Finding] = []

    for state in trial.states:
        visible = set(entry.get(state.name, frozenset()))
        for action in state.enter:
            findings += _one_action(state.name, action, visible)

        # Guards are evaluated against the display as the state *begins*, after its
        # entry actions: a state that shows a target and holds it is legal.
        for edge in state.go:
            window = getattr(edge.guard, "window", None)
            if window is not None and isinstance(
                edge.guard, (Entered, Exited, Hold, SaccadeTo, Touched)
            ):
                on = scores.get(window)
                if isinstance(on, str) and on not in visible:
                    findings.append(
                        Finding(
                            "nothing-to-look-at",
                            f"state {state.name!r} scores {window!r} against stimulus "
                            f"{on!r}, which is not on the display there; a hold on a "
                            f"stimulus that has been taken down cannot be satisfied "
                            f"by the animal doing the task correctly",
                        )
                    )
            for action in edge.do:
                findings += _one_action(state.name, action, set(visible))
    return findings


def _one_action(state: str, action, visible: set[str]) -> list[Finding]:
    """Check one display action against the current screen, and apply it."""
    if isinstance(action, Show):
        if action.stimulus.name in visible:
            return [
                Finding(
                    "duplicate-stimulus",
                    f"state {state!r} shows {action.stimulus.name!r}, which is "
                    f"already on the display; two live stimuli under one name make "
                    f"Hide and Update ambiguous",
                )
            ]
        visible.add(action.stimulus.name)
        return []
    if isinstance(action, Hide):
        if action.stimulus not in visible:
            return [
                Finding(
                    "absent-stimulus",
                    f"state {state!r} hides {action.stimulus!r}, which is not on "
                    f"the display",
                )
            ]
        visible.discard(action.stimulus)
        return []
    if isinstance(action, Update):
        found = []
        if action.stimulus not in visible:
            found.append(
                Finding(
                    "absent-stimulus",
                    f"state {state!r} updates {action.stimulus!r}, which is not on "
                    f"the display",
                )
            )
        if not action.changes():
            found.append(
                Finding(
                    "empty-update",
                    f"state {state!r} updates {action.stimulus!r} without changing "
                    f"anything",
                )
            )
        return found
    return []


# --- Colour ----------------------------------------------------------------


def _appearances(trial: Trial):
    """Every appearance a trial can put on screen, including the ones only a
    parameter selects.

    **Parameter choices count.** Pop-out is expressed as an appearance parameter --
    a red target among green distractors is the same task as a circle among squares
    with a different value -- so an appearance reachable only through `Param.choices`
    is as real as one written into a `Show`, and checking only the latter would skip
    exactly the stimuli this vocabulary was extended to express.
    """
    from wl_expcontroller.task import Appearance, Show, Update

    seen = []
    for _, action in actions_of(trial):
        looks = None
        if isinstance(action, Show):
            looks = action.stimulus.looks
        elif isinstance(action, Update) and not isinstance(action.looks, P):
            looks = action.looks
        if isinstance(looks, Appearance):
            seen.append(looks)
    for param in trial.params:
        seen.extend(c for c in param.choices if isinstance(c, Appearance))
    return seen


def _color_faults(trial: Trial, panel: Calibration | None) -> list[Finding]:
    """Colour checked against a display somebody measured.

    RGB is a set of instructions to one panel, so a colour that is not checked
    against a measurement is a colour nobody knows. The specific failure this
    prevents: a monitor asked for a colour outside its gamut clips silently, and a
    clipped colour has neither the requested chromaticity nor the requested
    luminance -- so an isoluminant pair stops being isoluminant and a chromatic
    experiment's control condition quietly becomes a luminance manipulation.
    """
    findings: list[Finding] = []
    for looks in _appearances(trial):
        color = getattr(looks, "color", None)
        if color is None or isinstance(color, P):
            continue
        what = type(looks).__name__
        if panel is None:
            findings.append(
                Finding(
                    "uncalibrated-color",
                    f"{what} asks for {color}, but no display calibration was "
                    f"supplied; colour is a physical claim and this one is "
                    f"unmeasured",
                )
            )
            continue
        if isinstance(color, xyY) and getattr(looks, "contrast", 1.0) != 1.0:
            findings.append(
                Finding(
                    "overspecified-color",
                    f"{what} sets an absolute colour and a contrast of "
                    f"{looks.contrast}; both claim to set the same physical "
                    f"quantity. Use DKL for a modulation, or drop the contrast",
                )
            )
        if isinstance(color, DKL) and color.lum == 0.0 and color.magnitude() > 0.0:
            if not panel.observer:
                findings.append(
                    Finding(
                        "unstated-observer",
                        f"{what} claims isoluminance, but the calibration measured "
                        f"{panel.measured_on} does not say whose luminous efficiency "
                        f"it used; a human V(lambda) makes a stimulus that is "
                        f"isoluminant for nobody in the room",
                    )
                )
        why = unrealizable(color, panel)
        if why is not None:
            findings.append(
                Finding("unrealizable-color", f"{what} asks for {color}: {why}")
            )
    return findings


# --- Arrays ----------------------------------------------------------------


def _ranges(trial: Trial) -> dict[str, tuple[float, float]]:
    return {
        p.name: (p.low, p.high)
        for p in trial.params
        if p.low is not None and p.high is not None
    }


def _widest(value, ranges) -> tuple[float, float]:
    """The lowest and highest a value can take over its declared range."""
    if isinstance(value, P):
        low, high = ranges.get(value.name, (0.0, 0.0))
        return (low, high)
    return (float(value), float(value))


def _declared_window_names(trial: Trial) -> set[str]:
    """Window names a task has, including every one an array generates.

    An array's items are named `<of>.<i>` and are as declared as anything an author
    typed -- the whole point is that the author cannot type them, because how many
    there are is not known until a trial runs.
    """
    arrays = arrays_of(trial)
    ranges = _ranges(trial)
    names: set[str] = set()
    for window in trial.windows:
        if isinstance(window, ItemWindows):
            names |= {f"{window.of}.target", f"{window.of}.distractor"}
            array = arrays.get(window.of)
            if array is not None:
                highest = int(_widest(array.n, ranges)[1])
                names |= {f"{window.of}.{i}" for i in range(highest)}
        else:
            names.add(window.name)
    return names


def _coupling(trial: Trial) -> dict[str, object]:
    """Which stimulus each window scores, generated families included."""
    scores: dict[str, object] = {}
    for name in _declared_window_names(trial):
        scores[name] = None
    for window in trial.windows:
        if isinstance(window, ItemWindows):
            for name in list(scores):
                if name.startswith(f"{window.of}."):
                    scores[name] = window.of
        else:
            scores[window.name] = window.on
    return scores


def _array_faults(trial: Trial) -> list[Finding]:
    """An array's target must be one of its items, for every legal setting.

    Set size and target index are both live parameters, so an experimenter can put
    the target at position 6 of a four-item array between one trial and the next.
    Reasoning over declared ranges is the only way to catch that before it is a
    session rather than a load.
    """
    ranges = _ranges(trial)
    findings: list[Finding] = []
    for state, action in actions_of(trial):
        looks = getattr(getattr(action, "stimulus", None), "looks", None)
        if not isinstance(looks, Array):
            continue
        lowest_n = int(_widest(looks.n, ranges)[0])
        lowest_t, highest_t = (int(v) for v in _widest(looks.target, ranges))
        if lowest_t < 0 or highest_t >= lowest_n:
            findings.append(
                Finding(
                    "target-outside-array",
                    f"state {state!r} shows an array of as few as {lowest_n} items "
                    f"with a target index reaching {highest_t}; the target must be "
                    f"one of the items for every setting the console allows, not "
                    f"only the one it has today",
                )
            )
    return findings


# --- Stereograms -----------------------------------------------------------


def _stereogram_faults(trial: Trial) -> list[Finding]:
    """A stereogram is a relationship between two images, so it needs both."""
    ranges = _ranges(trial)
    findings: list[Finding] = []
    for state, action in actions_of(trial):
        stimulus = getattr(action, "stimulus", None)
        looks = getattr(stimulus, "looks", None)
        if not isinstance(looks, RDS):
            continue
        low, high = _widest(looks.correlation, ranges)
        if low < -1.0 or high > 1.0:
            findings.append(
                Finding(
                    "impossible-correlation",
                    f"state {state!r} shows a stereogram whose correlation reaches "
                    f"{low if low < -1.0 else high:g}; correlation runs from -1 "
                    f"(anticorrelated) through 0 (uncorrelated) to +1. A value "
                    f"outside that is not a stronger stimulus, it is not a stimulus",
                )
            )
        if getattr(stimulus, "eye", "both") != "both":
            findings.append(
                Finding(
                    "monocular-stereogram",
                    f"state {state!r} shows a stereogram to the "
                    f"{stimulus.eye} eye only; monocular presentation of one half "
                    f"is not a degraded stereogram, it is a field of random dots "
                    f"with no disparity -- and it would still run, still record, "
                    f"and still appear in a figure as a disparity condition",
                )
            )
    return findings


# --- Which eye ---------------------------------------------------------------

EYES = ("both", "left", "right")


def _eye_faults(trial: Trial) -> list[Finding]:
    """Per-eye criteria must name an eye, and must name one that can see.

    A window scoring the eye a stimulus is *not* shown to runs, records, and aborts
    every trial for a reason invisible in the data: the animal was doing the task
    perfectly with the eye nobody scored.
    """
    findings: list[Finding] = []
    shown_to = {
        action.stimulus.name: getattr(action.stimulus, "eye", "both")
        for _, action in actions_of(trial)
        if isinstance(action, Show)
    }
    for window in trial.windows:
        eye = window.eye
        name = getattr(window, "name", None) or f"{window.of}.*"
        if eye not in EYES:
            findings.append(
                Finding(
                    "unknown-eye",
                    f"window {name!r} scores eye {eye!r}; it must be one of "
                    f"{', '.join(EYES)}. An unrecognised eye is not a criterion, "
                    f"it is a guard that is silently never true",
                )
            )
            continue
        on = getattr(window, "on", None)
        if not isinstance(on, str):
            continue
        stimulus_eye = shown_to.get(on)
        if stimulus_eye is None or stimulus_eye == "both" or eye == "both":
            continue
        if stimulus_eye != eye:
            findings.append(
                Finding(
                    "wrong-eye-criterion",
                    f"window {name!r} scores the {eye} eye against stimulus "
                    f"{on!r}, which is shown only to the {stimulus_eye} eye; the "
                    f"animal can do the task perfectly and abort every trial",
                )
            )
    return findings
