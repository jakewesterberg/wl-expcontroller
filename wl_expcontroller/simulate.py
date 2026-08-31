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

import random
from collections import Counter
from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from wl_expcontroller.run import Result, run_trial
from wl_expcontroller.task import Guard, Outcome, Trial

if TYPE_CHECKING:
    from wl_expcontroller.record import SessionRecord


@dataclass
class Subject:
    """A behaving animal, to the fidelity simulation needs.

    `hazards` maps a guard *type* to its per-frame probability of firing, so a
    latency is geometric with that rate. Seeded, because a simulated session that
    cannot be reproduced is an anecdote.

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
    _rng: random.Random = field(init=False, repr=False)
    _engaged: bool = field(init=False, default=True, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def new_trial(self) -> None:
        self._engaged = self._rng.random() < self.engagement

    def satisfied(self, guard: Guard, state: str, frame: int) -> bool:
        if not self._engaged:
            return False
        if self.lapse > 0.0 and self._rng.random() < self.lapse:
            self._engaged = False
            return False
        hazard = self.hazards.get(type(guard), 0.0)
        return hazard > 0.0 and self._rng.random() < hazard


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
