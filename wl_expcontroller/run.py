"""The trial loop: the framework executing a task's declarative data.

This is the loop S1 §5.1 keeps out of task files. A task declares states and
guarded transitions; this runs them, frame by frame, and asks a `World` whether
each non-temporal guard is satisfied. On a rig the world is hardware; in a
simulated session it is a behaviour agent; in demo mode it is a mouse and keyboard.
**They are peers** (S6 §6) -- the loop cannot tell them apart, which is what makes
a simulated session evidence about the real one.

`After` is the one guard the loop evaluates itself, from elapsed frames, because
time is the loop's own property rather than something the world reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from wl_expcontroller.task import After, Guard, Outcome, P, Trial


class World(Protocol):
    """Whatever supplies the signals a guard asks about."""

    def satisfied(self, guard: Guard, state: str, frame: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class Quiet:
    """A world where nothing ever happens.

    Useful on its own: it proves a trial terminates on its time bounds alone,
    which is the property S1 §9 check 4 exists to make true.
    """

    def satisfied(self, guard: Guard, state: str, frame: int) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Scripted:
    """A world where named guards fire on given frames.

    Deterministic, so a test can assert a frame count rather than a distribution.
    Frames are counted from the start of the trial, not of the state, because a
    script describes what the animal did and the animal does not know about states.
    """

    at_frame: dict[Guard, int]

    def satisfied(self, guard: Guard, state: str, frame: int) -> bool:
        return self.at_frame.get(guard) == frame


@dataclass(frozen=True, slots=True)
class Result:
    outcome: Outcome | None
    frames: int
    #: Every state this trial entered, in order. A census over many trials turns
    #: this into starvation detection: a state no trial ever entered is either
    #: unreachable in practice or gated on behaviour the animal never produces,
    #: and the static checks cannot tell the difference.
    visited: tuple[str, ...] = ()


def _resolve(value: float | P, values: dict[str, float]) -> float:
    """A parameter reference against this trial's bound values.

    **Missing is an error, never a default.** A timeout that silently became 0.0
    would abort every trial immediately -- and that reads as an animal who will not
    work, not as a bug, which is the most expensive way for this to fail.
    """
    if isinstance(value, P):
        if value.name not in values:
            raise KeyError(
                f"no value bound for parameter {value.name!r}; a trial runs against "
                f"a resolved parameter set, not a partially resolved one"
            )
        return values[value.name]
    return value


def run_trial(
    trial: Trial,
    world: World,
    frame_period: float,
    max_frames: int = 100_000,
    values: dict[str, float] | None = None,
) -> Result:
    """Run one trial to its outcome.

    `max_frames` is a backstop, not a policy: a well-formed task cannot hang,
    because check 3 proves every state reaches an outcome and check 4 proves every
    wait is bounded. It exists so a task that skipped the checker fails a test
    rather than a session.
    """
    by_name = {state.name: state for state in trial.states}
    current = by_name[trial.start]
    entered_at = 0
    visited = [current.name]
    for frame in range(1, max_frames + 1):
        elapsed = (frame - entered_at) * frame_period
        for edge in current.go:
            fired = (
                elapsed >= _resolve(edge.guard.seconds, values or {})
                if isinstance(edge.guard, After)
                else world.satisfied(edge.guard, current.name, frame)
            )
            if not fired:
                continue
            if isinstance(edge.to, Outcome):
                return Result(edge.to, frame, tuple(visited))
            current, entered_at = by_name[edge.to], frame
            visited.append(current.name)
            break
    return Result(None, max_frames, tuple(visited))
