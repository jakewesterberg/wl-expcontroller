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
    arrays_of,
    After,
    Custom,
    Mark,
    Guard,
    Outcome,
    P,
    Hide,
    ItemWindows,
    Reward,
    Show,
    Trial,
    Update,
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
    """A guard as a reviewer would say it out loud.

    Unset optional fields are omitted rather than rendered as `None`: a diagram that
    says `After(0.3s, None)` is noisier than the source it replaces, and noise is how
    a reviewer stops reading the artifact. What is *set* is always shown -- an SOA
    timed from photodiode onset rather than state entry is a different experiment,
    so `since` appears whenever it is there.
    """
    fields = [
        (name, getattr(guard, name))
        for name in guard.__slots__
        if getattr(guard, name) is not None
    ]
    rendered = [
        _value_label(value) if name != "since" else f"since={_guard_label(value)}"
        for name, value in fields
    ]
    label = f"{type(guard).__name__}({', '.join(rendered)})"
    if isinstance(guard, After) and isinstance(guard.seconds, float):
        head, _, tail = label.partition(f"{guard.seconds:g}")
        label = f"{head}{guard.seconds:g}s{tail}"
    return label


def _scores_label(on: object) -> str:
    """What a window scores. `REMEMBERED` is spelled out, because a window with
    deliberately nothing in it is a claim the reviewer should see made."""
    if on is None:
        return "**nothing declared**"
    if isinstance(on, str):
        return f"`{on}`"
    return "*remembered location*"


def _target_label(target: object) -> str:
    return target.name if isinstance(target, Outcome) else str(target)


def _timeline(trial: Trial) -> list[str]:
    """When each stimulus is on the display, and what happens to it.

    **Position and disparity are not enough.** Every defect the 2026-08-31 reviews
    found was about *when* something was on screen -- a fixation point removed at the
    moment fixation was asked for, an SOA timed from the wrong zero -- so an artifact
    showing only position is a picture a reviewer trusts of the half of the task that
    was never the problem.

    States are listed in declaration order, which is the order a reader follows; it
    is not an execution order, and a branching task has none.
    """
    events: dict[str, list[str]] = {}
    for state in trial.states:
        for action in list(state.enter) + [a for e in state.go for a in e.do]:
            if isinstance(action, Show):
                events.setdefault(action.stimulus.name, []).append(
                    f"shown in `{state.name}`"
                )
            elif isinstance(action, Hide):
                events.setdefault(action.stimulus, []).append(
                    f"hidden in `{state.name}`"
                )
            elif isinstance(action, Update):
                changed = ", ".join(sorted(action.changes()))
                events.setdefault(action.stimulus, []).append(
                    f"changed in `{state.name}` ({changed})"
                )
    if not events:
        return []
    lines = ["## Display timeline", "", "| Stimulus | On screen |", "|---|---|"]
    for name, happenings in events.items():
        if not any(step.startswith("hidden") for step in happenings):
            # Said explicitly rather than left blank: an empty cell reads as missing
            # information, and "never taken down" is a decision worth seeing.
            happenings = happenings + ["**until the trial ends**"]
        lines.append(f"| `{name}` | {' \u2192 '.join(happenings)} |")
    lines.append("")
    return lines


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

    # **Named by transition, not only by state.** A state can strobe one code on
    # entry and another on each outgoing edge, and an artifact attributing them all
    # to the state cannot be checked against a recording -- which is the one thing
    # this table is for.
    lines += ["## Event codes", "", "| Code | Meaning | Emitted by | When |",
              "|---|---|---|---|"]
    for state in trial.states:
        for action in state.enter:
            if isinstance(action, Mark):
                lines.append(
                    f"| {action.code} | {names.get(action.code, '**UNALLOCATED**')} "
                    f"| `{state.name}` | on entry |"
                )
        for edge in state.go:
            for action in edge.do:
                if isinstance(action, Mark):
                    lines.append(
                        f"| {action.code} "
                        f"| {names.get(action.code, '**UNALLOCATED**')} "
                        f"| `{state.name}` | on \u2192 {_target_label(edge.to)} |"
                    )
    lines.append("")

    lines += _timeline(trial)

    if trial.windows:
        lines += ["## Windows", "", "| Name | Centre | Radius | Scores | Eye |",
                  "|---|---|---|---|---|"]
        arrays = arrays_of(trial)
        for window in trial.windows:
            if isinstance(window, ItemWindows):
                # A family, described as one: how many members it has is a
                # parameter, so listing them would be listing one configuration.
                array = arrays.get(window.of)
                count = _value_label(array.n) if array is not None else "?"
                lines.append(
                    f"| `{window.of}.*` | {count} items on a ring "
                    f"| {_value_label(window.radius)} | `{window.of}` "
                    f"| {window.eye} |"
                )
                continue
            centre = (
                f"({_value_label(window.at[0])}, {_value_label(window.at[1])})"
                if isinstance(window.at, tuple)
                else _value_label(window.at)
            )
            lines.append(
                f"| `{window.name}` | {centre} | {_value_label(window.radius)} "
                f"| {_scores_label(window.on)} | {window.eye} |"
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

