"""What a human reviews instead of source.

ADR-0006's acceptance test: a task Claude wrote is approved from a rendered state
diagram, a table of every event code with the state that emits it, the declared
parameters with their ranges, and a simulation report. **If a task cannot be
reviewed from these, the design failed rather than the reviewer.**

The diagram is Mermaid, so it renders in the repository, in a pull request, and in
anything the lab already reads -- rather than needing a viewer nobody has installed
at 8am.
"""

from __future__ import annotations

from wl_expcontroller.task import (
    After,
    Custom,
    Mark,
    Guard,
    Outcome,
    P,
    Reward,
    Show,
    Trial,
    actions_of,
)


def _value_label(value: object) -> str:
    """A parameter reference by name, a literal duration with its unit.

    The unit belongs to the *literal*, not to the name: `After(fix_timeouts)` reads
    as a parameter nobody declared, and a reviewer who stops trusting the diagram
    goes back to reading source -- which is the thing this artifact replaces.
    """
    if isinstance(value, P):
        return value.name
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _guard_label(guard: Guard) -> str:
    fields = [getattr(guard, name) for name in guard.__slots__]
    label = f"{type(guard).__name__}({', '.join(_value_label(f) for f in fields)})"
    if isinstance(guard, After) and isinstance(guard.seconds, float):
        label = label[:-1] + "s)"
    return label


def _target_label(target: object) -> str:
    return target.name if isinstance(target, Outcome) else str(target)


def render(trial: Trial, allocation_names: dict[int, str] | None = None) -> str:
    names = allocation_names or {}
    lines: list[str] = ["## Trial structure", "", "```mermaid", "stateDiagram-v2"]
    lines.append(f"    [*] --> {trial.start}")
    for state in trial.states:
        for edge in state.go:
            lines.append(
                f"    {state.name} --> {_target_label(edge.to)}: "
                f"{_guard_label(edge.guard)}"
            )
    lines += ["```", ""]

    lines += ["## Event codes", "", "| Code | Meaning | Emitted by |", "|---|---|---|"]
    for name, action in actions_of(trial):
        if isinstance(action, Mark):
            lines.append(
                f"| {action.code} | {names.get(action.code, '**UNALLOCATED**')} "
                f"| `{name}` |"
            )
    lines.append("")

    if trial.windows:
        lines += ["## Windows", "", "| Name | Centre | Radius |", "|---|---|---|"]
        for window in trial.windows:
            centre = (
                f"({_value_label(window.at[0])}, {_value_label(window.at[1])})"
                if isinstance(window.at, tuple)
                else _value_label(window.at)
            )
            lines.append(
                f"| `{window.name}` | {centre} | {_value_label(window.radius)} |"
            )
        lines.append("")

    if trial.params:
        lines += ["## Parameters", "", "| Name | Unit | Range | Live |", "|---|---|---|---|"]
        for param in trial.params:
            lines.append(
                f"| {param.name} | {param.unit} | {param.low}–{param.high} "
                f"| {'yes' if param.live else 'no'} |"
            )
        lines.append("")

    welfare = [
        (name, action)
        for name, action in actions_of(trial)
        if isinstance(action, (Reward, Custom))
    ]
    if welfare:
        lines += ["## Needs human review", ""]
        for name, action in welfare:
            what = (
                f"reward, bounded by `{action.ref.name}`"
                if isinstance(action, Reward)
                else f"custom component `{action.name}`"
            )
            lines.append(f"- `{name}`: {what}")
        lines.append("")

    stimuli = [
        (name, action.stimulus)
        for name, action in actions_of(trial)
        if isinstance(action, Show)
    ]
    if stimuli:
        lines += ["## Stimuli", "", "| State | Position (cyclopean°) | Disparity° |",
                  "|---|---|---|"]
        for name, stimulus in stimuli:
            lines.append(f"| `{name}` | {stimulus.at} | {stimulus.disparity} |")
        lines.append("")

    return "\n".join(lines)

