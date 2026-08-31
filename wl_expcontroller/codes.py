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
    #: Which `Marker` each terminal outcome strobes. **These are `wl-preproc`'s**,
    #: from `Marker` 1-255, which ADR-0007 leaves in their ownership -- so unlike
    #: `task_events` this half is not waiting on anything and can be populated with
    #: their real, frozen values today.
    outcomes: dict[object, int] = field(default_factory=dict)

    def __contains__(self, code: int) -> bool:
        return code in self.task_events


#: `Marker` values transcribed from `wl-preproc/wl_preproc/contracts/events.py`,
#: which is frozen and carries an explicit warning that renumbering silently
#: relabels every prior recording. Mirrored rather than imported so the rig carries
#: no pipeline dependency; the round-trip tests keep the mirror honest.
#:
#: **`NO_FIXATION` maps to `TRIAL_ABORT`, and that loses information on purpose.**
#: There is no dedicated marker for it, and asking for one would put a task-level
#: distinction into a range whose owner reserves it for trial structure. The reason
#: an abort happened is carried by a `TaskEvent` strobed just before the marker --
#: identity and timing in the stream, the specific meaning in our own range. Any
#: analysis distinguishing abort kinds reads the pair, not the marker alone.
_TRIAL_CORRECT = 34
_TRIAL_ERROR = 35
_TRIAL_ABORT = 36
_TRIAL_FIXATION_BREAK = 37
_TRIAL_NO_RESPONSE = 38


def _standing_outcomes() -> dict[object, int]:
    from wl_expcontroller.task import Outcome

    return {
        Outcome.CORRECT: _TRIAL_CORRECT,
        Outcome.WRONG_TARGET: _TRIAL_ERROR,
        Outcome.NO_FIXATION: _TRIAL_ABORT,
        Outcome.FIXATION_BREAK: _TRIAL_FIXATION_BREAK,
        Outcome.NO_RESPONSE: _TRIAL_NO_RESPONSE,
    }


#: Placeholder until `wl-mllib` publishes one. `task_events` is empty on purpose --
#: a task emitting any code fails until a real allocation is loaded, which is right
#: for a project whose whole guardrail is that codes come from elsewhere. Outcomes
#: are populated, because their half of the allocation is already settled.
PROVISIONAL = Allocation(outcomes=_standing_outcomes())
