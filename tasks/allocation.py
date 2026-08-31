"""The reference event-code allocation.

**This is `wl-mllib`'s to own** (ADR-0007). It lives here until that repository has
one, and it is confined to **4096-32767** -- the task-specific range whose ownership
is not in dispute. `TaskEvent` 256-4095 is not used, because moving it to `wl-mllib`
still needs `wl-preproc`'s agreement and allocating there would mean rework if they
decline.

Outcome markers are not here: those are `Marker` values, already allocated and frozen
by `wl-preproc`, and `codes.PROVISIONAL` carries them.
"""

from dataclasses import replace

from wl_expcontroller.codes import PROVISIONAL, Allocation

#: Looked up by name, not by type: this module imports `PROVISIONAL` to build on
#: it, so two `Allocation` instances are visible and picking "the only one" would
#: be picking arbitrarily.
ALLOCATION: Allocation = replace(
    PROVISIONAL,
    task_events={
        4096: "FIX_ON",
        4097: "TARGET_ON",
        4098: "SACCADE_ONSET",
        4099: "TARGET_ACQUIRED",
        4100: "ABORT_NO_FIXATION",
        4101: "ABORT_FIXATION_BREAK",
        4102: "REWARD_COMMANDED",
    },
)
