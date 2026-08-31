"""Load-time checks (S1 §9). A task failing any of these is refused at load."""

from __future__ import annotations

from dataclasses import dataclass

from wl_expcontroller.task import After, Trial


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    detail: str


def check(trial: Trial) -> list[Finding]:
    return _unreachable_states(trial) + _unbounded_waits(trial)


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
