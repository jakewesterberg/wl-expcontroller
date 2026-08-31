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

from wl_expcontroller.run import Result, run_trial
from wl_expcontroller.task import Guard, Outcome, Trial


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
    """

    seed: int
    hazards: dict[type, float] = field(default_factory=dict)
    engagement: float = 0.9
    _rng: random.Random = field(init=False, repr=False)
    _engaged: bool = field(init=False, default=True, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def new_trial(self) -> None:
        self._engaged = self._rng.random() < self.engagement

    def satisfied(self, guard: Guard, state: str, frame: int) -> bool:
        if not self._engaged:
            return False
        hazard = self.hazards.get(type(guard), 0.0)
        return hazard > 0.0 and self._rng.random() < hazard


@dataclass(frozen=True, slots=True)
class Census:
    outcomes: Counter
    states_visited: set[str]
    hangs: int

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


def simulate(
    trial: Trial, subject: Subject, trials: int, frame_period: float
) -> Census:
    """Run `trials` trials and report what happened.

    A trial that reaches `max_frames` without an outcome counts as a **hang**
    rather than raising: one pathological path should not stop a run that exists
    to find pathological paths.
    """
    outcomes: Counter = Counter()
    visited: set[str] = set()
    hangs = 0
    for _ in range(trials):
        subject.new_trial()
        result: Result = run_trial(trial, subject, frame_period)
        visited.update(result.visited)
        if result.outcome is None:
            hangs += 1
        else:
            outcomes[result.outcome] += 1
    return Census(outcomes=outcomes, states_visited=visited, hangs=hangs)
