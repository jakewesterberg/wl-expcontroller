"""Load-time checks (S1 §9). A task failing any of these is refused at load."""

from __future__ import annotations

from dataclasses import dataclass

from wl_expcontroller.codes import PROVISIONAL, Allocation
from wl_expcontroller.task import After, Emit, Outcome, Trial


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    detail: str


def check(trial: Trial, allocation: Allocation = PROVISIONAL) -> list[Finding]:
    return (
        _unreachable_states(trial)
        + _unbounded_waits(trial)
        + _states_with_no_outcome_path(trial)
        + _shadowed_transitions(trial)
        + _unallocated_codes(trial, allocation)
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
