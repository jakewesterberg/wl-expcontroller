"""The join: a tracker, a versioned map, and a trial's windows, as a `World`.

Four modules become one working path here. `eye` produces samples in camera pixels,
`calibration` turns a raw Purkinje vector into degrees at a stated mapping version,
`task` declares where the windows are, and `run` asks one question -- *is gaze inside
this window* -- without knowing that any of the above exists.

**What this deliberately does not do.** It does not decide what entering, leaving or
holding mean; the trial loop derives those from membership so the semantics exist
once, and a world that re-derived them would let the simulator and the rig disagree
about what a hold is. It does not implement staleness either: `Tracker.state` owns
that, and this reports it.

**`happened` answers nothing yet, and says so.** `SaccadeTo` and `SaccadeOnset` ride
on the versioned Engbert-Kliegl component that does not exist (S5 §5). Returning
`False` for a saccade guard is not "the saccade did not happen", it is "nothing here
can tell you" -- so the guards that need it raise rather than quietly scoring every
trial as a miss. A task using them against this world fails loudly at the frame it
would have mattered.
"""

from __future__ import annotations

import math
from typing import Mapping as MappingType

from wl_expcontroller.calibration import Mapping
from wl_expcontroller.eye import Tracker
from wl_expcontroller.task import (
    Guard,
    P,
    SaccadeOnset,
    SaccadeTo,
    Stimulus,
    Trial,
    expand_windows,
)


def _resolve(value: float | P, values: dict[str, float]) -> float:
    """A literal or a parameter reference, as a number. Mirrors `run._resolve`;
    kept here rather than imported to avoid a cycle, and small enough that the
    duplication is cheaper than the coupling."""
    return values[value.name] if isinstance(value, P) else value


class Tracked:
    """A `World` whose gaze comes from a real (or replayed) tracker.

    Frames are converted to session time as `frame * frame_period + started_at`,
    which is the only place the loop's frame clock and the tracker's arrival stamps
    meet. The loop counts frames because a display does; the tracker stamps arrivals
    because a poll-based protocol carries no clock we can trust (`eye.py`). Neither
    is wrong and the conversion has to live somewhere.
    """

    def __init__(
        self,
        tracker: Tracker,
        mapping: Mapping,
        trial: Trial,
        frame_period: float,
        values: dict[str, float] | None = None,
        started_at: float = 0.0,
        source=None,
    ) -> None:
        self.tracker = tracker
        self.mapping = mapping
        self.frame_period = frame_period
        self.started_at = started_at
        #: Anything with `poll(at)` -- `eye.Replay` or `eye.UdpSource`. Optional so
        #: a test can drive the tracker directly, but on a rig this is how gaze
        #: arrives, and it is polled in `display` for the reason given there.
        self.source = source
        self._values = values or {}
        declared, _aliases = expand_windows(trial, self._values)
        self._windows = {window.name: window for window in declared}
        #: Which mapping version scored this trial. S5 §6: every trial cites the
        #: version in force, and it is read off the map rather than passed in, so a
        #: trial cannot cite a version it was not actually scored under.
        self.mapping_version = mapping.version

    def when(self, frame: int) -> float:
        return self.started_at + frame * self.frame_period

    def gaze(self, which: str, frame: int) -> tuple[float, float] | None:
        """Where that eye is looking, in degrees, or `None`.

        `None` means one of three different things -- no sample yet, the sample is
        too old, or this eye has no map -- and they are deliberately not told apart
        here. The loop asks `signal` when it needs to know which, because a window
        test only ever needed the answer "not usable".
        """
        if self.tracker.state(self.when(frame)) != "ok":
            return None
        sample = self.tracker.latest
        if sample is None:
            return None
        return self.mapping.degrees(which, getattr(sample, which).dpi())

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        declared = self._windows.get(window)
        if declared is None:
            return False
        centre = declared.at
        if isinstance(centre, P):
            centre = self._values[centre.name]
        cx, cy = (_resolve(c, self._values) for c in centre)
        radius = _resolve(declared.radius, self._values)

        which = ("left", "right") if eye == "both" else (eye,)
        positions = [self.gaze(side, frame) for side in which]
        if any(position is None for position in positions):
            return False
        # A conjugate criterion is the mean of the two eyes, not either one: an
        # `eye="both"` window asks where the animal is looking, and under dichoptic
        # presentation one eye alone answers a different question. A window that
        # wants one eye says so, which is what `Window.eye` exists for.
        x = sum(p[0] for p in positions) / len(positions)
        y = sum(p[1] for p in positions) / len(positions)
        return math.hypot(x - cx, y - cy) <= radius

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        if isinstance(guard, (SaccadeTo, SaccadeOnset)):
            raise NotImplementedError(
                f"{type(guard).__name__} needs the saccade detector of S5 §5, which "
                f"does not exist yet. Returning False here would score every "
                f"saccade-contingent trial as a miss and read as behaviour"
            )
        return False

    def signal(self, frame: int) -> str:
        """`"ok"` or `"lost"`. **Never `"blink"`**, because telling a blink from a
        dropped camera needs the pupil-area collapse `eye.py` records as UNVERIFIED
        -- what OpenIris emits when tracking fails is not documented in the material
        read, and a fabricated rule here decides whether an animal is looking. Until
        the V3 bench measurement, a blink reaches the loop as tracker loss, which
        over-reports equipment failure rather than under-reporting it."""
        return self.tracker.state(self.when(frame))

    def display(self, visible: MappingType[str, Stimulus], frame: int) -> None:
        """Also where gaze is polled, which is not an abuse of the name.

        `World.display` is the loop's only per-frame call that lands **before** the
        frame's guards are evaluated -- `signal` and `in_window` both come after --
        so it is the one place a sample can arrive and be current for the frame that
        reads it. Polling anywhere else means every window test scores the previous
        frame's gaze, and at 8 ms a frame that is a whole frame of lag introduced by
        the harness rather than by the tracker. The first version of this class had
        the poll in `in_window`, and the trial died of staleness at frame 7 because
        `signal` ran first and saw a sample nothing had refreshed.
        """
        if self.source is not None:
            self.tracker.accept(self.source.poll(self.when(frame)))
