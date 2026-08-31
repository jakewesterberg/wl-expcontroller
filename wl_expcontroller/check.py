"""Load-time checks (S1 §9). A task failing any of these is refused at load."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from wl_expcontroller.codes import PROVISIONAL, Allocation
from wl_expcontroller.components import Registry
from wl_expcontroller.geometry import Geometry
from wl_expcontroller.task import After, Custom, Emit, Outcome, P, Show, Trial


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
            f"state {state.name!r} emits code {action.code}, which is not in the "
            f"allocation; codes are allocated in wl-mllib, never invented in a task",
        )
        for state in trial.states
        for action in state.enter
        if isinstance(action, Emit) and action.code not in allocation
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
    for state in trial.states:
        for action in state.enter:
            if not isinstance(action, Custom):
                continue
            if action.name in components:
                findings.append(
                    Finding(
                        "custom-component-needs-review",
                        f"state {state.name!r} uses custom component "
                        f"{action.name!r}; this task needs human review",
                        blocking=False,
                    )
                )
            else:
                findings.append(
                    Finding(
                        "unresolved-custom-component",
                        f"state {state.name!r} names custom component "
                        f"{action.name!r}, which resolves to no reviewed component",
                    )
                )
    return findings


def _offscreen_stimuli(trial: Trial, geometry: Geometry | None) -> list[Finding]:
    """S1 §9 check 8: every stimulus can actually be shown.

    Checked **per eye, after disparity**, not at the cyclopean position. Disparity
    is applied as equal and opposite horizontal offsets, so a stimulus comfortably
    inside the field can still put one eye's image outside it -- and only that
    eye's. On a split-screen stereoscope that is a stimulus the animal fuses on one
    side and loses on the other, which is a far stranger failure than simply not
    seeing it.

    Skipped when no geometry is supplied, because a task is not wrong for being
    checked without a rig; it is unchecked, and the caller knows which it wanted.
    """
    if geometry is None:
        return []
    findings: list[Finding] = []
    for state in trial.states:
        for action in state.enter:
            if not isinstance(action, Show):
                continue
            for eye, (x, y) in zip(("left", "right"), action.stimulus.per_eye()):
                if geometry.can_show(x, y):
                    continue
                where = (
                    f"at {action.stimulus.at}"
                    if action.stimulus.disparity == 0.0
                    else f"at {action.stimulus.at} with disparity "
                    f"{action.stimulus.disparity}, putting the {eye} eye's image "
                    f"at ({x:.1f}, {y:.1f})"
                )
                findings.append(
                    Finding(
                        "stimulus-off-screen",
                        f"state {state.name!r} shows a stimulus {where}, outside "
                        f"the ±{geometry.half_field_h_deg:.1f}° × "
                        f"±{geometry.half_field_v_deg:.1f}° field",
                    )
                )
                break
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
