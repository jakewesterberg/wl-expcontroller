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
        4103: "ARRAY_ON",
        4104: "DISTRACTOR_ACQUIRED",
        # The calibration block (S5 sec 7). START/END bound the block; the per-trial
        # pair marks each target. `TaskEvent.CALIBRATION_START` is what S5 names, but
        # 256-4095 is not ours to allocate into until wl-preproc agrees ADR-0007, so
        # these live in the undisputed range like everything else here.
        4105: "CALIBRATION_TARGET_ON",
        4106: "CALIBRATION_TARGET_HELD",
        4107: "CALIBRATION_START",
        4108: "CALIBRATION_END",
        # Outcome reasons. Eighteen outcomes share five markers, so these are what
        # distinguish them in a recording -- strobed immediately before the marker.
        4110: "OUTCOME_CORRECT",
        4111: "OUTCOME_EARLY_RESPONSE",
        4112: "OUTCOME_LATE_RESPONSE",
        4113: "OUTCOME_WRONG_TARGET",
        4114: "OUTCOME_EARLY_ERROR",
        4115: "OUTCOME_LATE_ERROR",
        4116: "OUTCOME_NO_FIXATION",
        4117: "OUTCOME_NO_RESPONSE",
        4118: "OUTCOME_ABORT",
        4119: "OUTCOME_FIXATION_BREAK",
        4120: "OUTCOME_TARGET_BREAK",
        4121: "OUTCOME_CATCH_BREAK",
        4122: "OUTCOME_MOTION_BREAK",
        4123: "OUTCOME_CORRECT_REJECT",
        4124: "OUTCOME_FALSE_ALARM",
        4125: "OUTCOME_BLINK_BREAK",
        4126: "OUTCOME_TRACKER_LOST",
        4127: "OUTCOME_FAULT",
    },
)
