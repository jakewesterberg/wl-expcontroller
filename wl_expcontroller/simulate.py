"""Simulated sessions, and the census that makes them evidence.

S9 §5: this is the D4 acceptance test, not a convenience. The load-time checks
prove a task is well *formed*; simulation proves it is well *behaved* -- every
outcome reachable by something an animal might plausibly do, no state starved,
nothing hanging.

The subject models **outcome distributions and reaction times, not realistic gaze
traces** (M0 §4). A per-guard hazard rate gives geometric latencies, which is a
reaction-time model and is enough to answer the questions simulation is asked.
Anything more faithful is what replayed recordings are for, and a synthetic animal
that looked convincing would invite exactly the confusion between the two.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from wl_expcontroller.run import Result, run_trial
from wl_expcontroller.task import (
    Entered,
    expand_windows,
    Exited,
    Guard,
    Outcome,
    Remembered,
    Trial,
)

if TYPE_CHECKING:
    from wl_expcontroller.record import SessionRecord


@dataclass
class Subject:
    """A behaving animal, to the fidelity simulation needs.

    `hazards` maps a guard *type* to a **rate in events per second**, converted to a
    per-frame probability by the frame period. Rates rather than probabilities
    because a per-frame number means something different at every refresh rate --
    0.01 per frame is a 51% chance of breaking across a 0.3 s hold at 240 Hz and 16%
    at 60 Hz -- and the animal does not know the refresh rate. S0's dual-mode panel
    makes that a rate change *within* a session, so a subject expressed per frame
    would describe a different animal in each mode.

    Seeded, because a simulated session that cannot be reproduced is an anecdote.

    **`engagement` is not a refinement, it is what makes the model able to produce
    a no-response at all.** A pure hazard fires eventually given enough frames --
    at 0.25 per frame over a 2 s window the chance of never acquiring fixation is
    about 10^-25 -- so a hazard-only animal never fails to engage, and NO_FIXATION,
    the commonest real abort, would be unreachable in every simulated session. The
    first run of this module demonstrated exactly that, which is the kind of thing
    simulation exists to find. So engagement is decided **once per trial**: a
    disengaged animal ignores the world for the whole trial and the task falls
    through to its time bounds.

    **`lapse` is the same argument one level down, and it was found the same way.**
    Engagement decided once per trial cannot produce an animal that acquires
    fixation, holds it, and then stops -- so `NO_RESPONSE` was unreachable on the
    first reference task, and every task's no-response path would have gone untested
    by simulation while the report claimed a clean run. A per-frame lapse gives up
    mid-trial, which is behaviour animals actually produce and is the only route to
    that outcome.
    """

    seed: int
    hazards: dict[type, float] = field(default_factory=dict)
    engagement: float = 0.9
    #: Per-frame probability of giving up part-way through a trial.
    lapse: float = 0.0
    #: Blinks and tracker stalls, as rates per second with a mean duration in
    #: seconds. **Zero by default and that is a real limitation**: a subject that
    #: never blinks makes `BLINK_BREAK` and `TRACKER_LOST` unreachable in every
    #: simulated session, so a task's handling of them would go untested while the
    #: report claimed a clean run -- the failure that produced traps 8 and 9. A
    #: session meant to exercise them sets these.
    blinks: float = 0.0
    blink_seconds: float = 0.25
    stalls: float = 0.0
    stall_seconds: float = 0.03
    _rng: random.Random = field(init=False, repr=False)
    _engaged: bool = field(init=False, default=True, repr=False)
    _inside: set = field(init=False, default_factory=set, repr=False)
    _windows: set = field(init=False, default_factory=set, repr=False)
    _frame: int = field(init=False, default=0, repr=False)
    #: What is on the display right now, and which stimulus each window scores.
    #: The second is set by `simulate` from the trial, so a subject need not be
    #: constructed knowing the task.
    _visible: set = field(init=False, default_factory=set, repr=False)
    _interrupted: str = field(init=False, default="ok", repr=False)
    _interrupted_until: int = field(init=False, default=0, repr=False)
    _scores: dict = field(init=False, default_factory=dict, repr=False)
    #: Set by `simulate`, so a subject need not be constructed knowing the rig.
    _frame_period: float = field(init=False, default=1 / 240, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def new_trial(self) -> None:
        self._engaged = self._rng.random() < self.engagement
        self._inside = set()
        self._visible = set()
        self._interrupted = "ok"
        self._interrupted_until = 0
        self._frame = 0

    def signal(self, frame: int) -> str:
        """Whether the gaze signal is available this frame.

        Two independent interruptions, because they are two phenomena: the animal
        blinks, and the tracker stalls. Durations are geometric about their declared
        mean, which is the same rate-based reasoning `hazards` uses and for the same
        reason -- a per-frame number describes a different animal at every refresh
        rate.
        """
        self._tick(frame)
        if frame < self._interrupted_until:
            return self._interrupted
        for kind, rate, mean in (
            ("blink", self.blinks, self.blink_seconds),
            ("lost", self.stalls, self.stall_seconds),
        ):
            if rate > 0.0 and self._rng.random() < self._per_frame(rate):
                frames = max(1, int(self._rng.expovariate(1.0 / mean) / self._frame_period))
                self._interrupted = kind
                self._interrupted_until = frame + frames
                return kind
        self._interrupted = "ok"
        return "ok"

    def display(self, visible, frame: int) -> None:
        """See the screen.

        **An animal cannot look at something that is not there**, and until this
        existed the subject responded to the transition graph alone -- so every
        "correct graph, wrong experiment" defect simulated perfectly. A task that
        took its fixation point down at the moment it asked for fixation ran 2,000
        trials and reported clean.
        """
        self._visible = set(visible)

    def _lookable(self, window: str) -> bool:
        """Whether there is anything at `window` to look at.

        An uncoupled window is not gated: the coupling is what the checker exists
        to require, and a subject that silently treated "not declared" as "not
        there" would report an authoring omission as an animal who will not work.
        `REMEMBERED` is not gated either, by definition -- a memory-guided saccade
        is scored against a blank location on purpose.
        """
        on = self._scores.get(window)
        if on is None or isinstance(on, Remembered):
            return True
        return on in self._visible

    def _per_frame(self, rate: float) -> float:
        """A rate in events per second as a per-frame probability."""
        return 1.0 - math.exp(-rate * self._frame_period)

    def _tick(self, frame: int) -> None:
        """Advance membership once per frame, however many windows are asked about.

        Guards are evaluated several times per frame, so drawing on every question
        would make an animal's behaviour depend on how many transitions a state
        happens to declare -- which is a property of the task file, not of the animal.
        """
        if frame == self._frame:
            return
        self._frame = frame
        if not self._engaged:
            return
        if self.lapse > 0.0 and self._rng.random() < self._per_frame(self.lapse):
            self._engaged = False
            self._inside = set()
            return
        enter = self._per_frame(self.hazards.get(Entered, 0.0))
        leave = self._per_frame(self.hazards.get(Exited, 0.0))
        for window in list(self._windows):
            if window in self._inside:
                # A stimulus that disappears takes the animal's gaze with it.
                # Conservative on purpose: an animal *can* hold gaze on a blank
                # location, but no paradigm asks it to without saying so, and this
                # is the assumption that turns a vanished stimulus into a visible
                # break rather than a silently different experiment.
                if not self._lookable(window):
                    self._inside.discard(window)
                elif leave > 0.0 and self._rng.random() < leave:
                    self._inside.discard(window)
            elif (
                enter > 0.0
                and self._lookable(window)
                and self._rng.random() < enter
            ):
                self._inside.add(window)

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        """Per-window and independent, which is not how an animal looks.

        Adequate rather than faithful, and deliberately so (M0 §4): agents model
        outcome distributions and reaction times, not gaze traces. A task whose
        conclusions depend on an animal being unable to occupy two windows at once
        is a task that needs replayed recordings, not a better synthetic animal.
        """
        self._windows.add(window)
        self._tick(frame)
        return window in self._inside

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        self._tick(frame)
        if not self._engaged:
            return False
        hazard = self._per_frame(self.hazards.get(type(guard), 0.0))
        if hazard <= 0.0 or self._rng.random() >= hazard:
            return False
        # A saccade that lands in a window leaves the animal *in* it, so a hold
        # that follows can complete. Without this a task could detect a saccade to
        # a target and then never register the animal as looking at it.
        window = getattr(guard, "window", None)
        if window is not None:
            if not self._lookable(window):
                return False
            self._inside.add(window)
        return True


@dataclass(frozen=True, slots=True)
class Census:
    outcomes: Counter
    states_visited: set[str]
    hangs: int
    #: Scored responses by `(window, classification)`. A free-viewing task ends the
    #: same mundane way every trial, so an outcome-only census says nothing about
    #: it -- what varies, and what the experiment is about, happens inside.
    responses: Counter = field(default_factory=Counter)

    def uncovered(self, trial: Trial) -> set[Outcome]:
        """Outcomes the task declares that no simulated trial reached.

        Not a failure by itself -- a rare error condition may legitimately need
        more trials than were run, and a subject configured not to make a mistake
        will never produce one. It is a question the report asks out loud, which
        is the difference between an outcome nobody reached and an outcome nobody
        noticed was unreachable.
        """
        declared = {
            edge.to
            for state in trial.states
            for edge in state.go
            if isinstance(edge.to, Outcome)
        }
        return declared - set(self.outcomes)


def run_session(
    trial: Trial,
    subject: Subject,
    trials: int,
    frame_period: float,
    values: dict[str, float] | None = None,
    record: "SessionRecord | None" = None,
) -> Census:
    """Run a session, optionally writing the record a rig would write.

    **The simulator and the rig write through the same code.** That is what makes a
    simulated session evidence about a real one rather than a rehearsal of it -- a
    separate "simulation output" path would be free to differ from the real one in
    exactly the ways that matter, and nobody would find out until January.
    """
    census = simulate(trial, subject, trials, frame_period, values, record)
    return census


def simulate(
    trial: Trial,
    subject: Subject,
    trials: int,
    frame_period: float,
    values: dict[str, float] | None = None,
    record: "SessionRecord | None" = None,
) -> Census:
    """Run `trials` trials and report what happened.

    A trial that reaches `max_frames` without an outcome counts as a **hang**
    rather than raising: one pathological path should not stop a run that exists
    to find pathological paths.
    """
    outcomes: Counter = Counter()
    responses: Counter = Counter()
    visited: set[str] = set()
    hangs = 0
    subject._frame_period = frame_period
    # Expanded, because an array's per-item windows are not in `trial.windows` --
    # how many there are is not known until `n` is bound.
    declared, _ = expand_windows(trial, values or {})
    subject._scores = {window.name: window.on for window in declared}
    for index in range(trials):
        subject.new_trial()
        result: Result = run_trial(
            trial, subject, frame_period, values=values or {}
        )
        visited.update(result.visited)
        for scored in result.scored:
            responses[(scored.window, scored.scored_as)] += 1
        if result.outcome is None:
            hangs += 1
        else:
            outcomes[result.outcome] += 1
        if record is not None:
            record.trial(
                index=index,
                outcome=result.outcome.value if result.outcome else "hang",
                params=dict(values or {}),
            )
    return Census(
        outcomes=outcomes,
        states_visited=visited,
        hangs=hangs,
        responses=responses,
    )
