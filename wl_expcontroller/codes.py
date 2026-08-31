"""The event-code allocation this controller validates against.

**This module does not own the allocation and must never become its definition.**
Ownership is settled by ADR-0007: `wl-preproc` owns the framing, the escapes and
`Marker` 1-255; `wl-mllib` owns `TaskEvent` 256-4095, `TaskTypeCode` 100+, and the
task-specific range 4096-32767. A second definition here would be exactly the
failure S2 found between `wl-mllib`'s manifest and `wl-preproc`'s frozen codec --
two repositories disagreeing about who allocates, with nothing able to detect it.

So `Allocation` is a *loaded* thing. `PROVISIONAL` below exists only until
`wl-mllib` has one to load, and it is deliberately confined to **4096-32767**, the
one range whose ownership is not in dispute: ADR-0007 moves `TaskEvent` 256-4095 to
`wl-mllib`, and `wl-preproc` has not yet agreed. Allocating there instead would mean
rework if they decline; allocating here does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The range ADR-0007 assigns to task-specific and condition encoding, and the only
#: range this project allocates into while the `TaskEvent` question is open.
TASK_SPECIFIC = range(4096, 32768)


@dataclass(frozen=True, slots=True)
class Allocation:
    """Which numeric codes mean what. Loaded, never invented."""

    task_events: dict[int, str] = field(default_factory=dict)

    def __contains__(self, code: int) -> bool:
        return code in self.task_events


#: Placeholder until `wl-mllib` publishes one. Empty on purpose: a task that emits
#: any code fails the check until a real allocation is loaded, which is the correct
#: behaviour for a project whose whole guardrail is that codes come from elsewhere.
PROVISIONAL = Allocation()
