"""The within-trial task representation.

Declarative data, not code (ADR-0006). A trial is states and guarded transitions;
`taskd` executes it and the task never owns the frame loop. Plain Python
declarations rather than a text DSL, so an ordinary editor gives autocomplete and
type checking -- and so a model authoring one is writing the language it writes best.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(Enum):
    """Terminal states. Real codes come from wl-mllib's allocation (S2); these
    names stand in until that allocation exists."""

    CORRECT = "correct"
    NO_FIXATION = "no_fixation"
    FIXATION_BREAK = "fixation_break"
    NO_RESPONSE = "no_response"
    WRONG_TARGET = "wrong_target"


@dataclass(frozen=True, slots=True)
class Param:
    """One live-editable parameter: name, unit, and the range it may hold.

    The single declaration S8 §3.1 turns into validation, the console's widget,
    the per-trial snapshot and the ELN summary -- which is what makes live control
    work for a task nobody hand-wrote, with no per-task UI code.
    """

    name: str
    unit: str
    low: float
    high: float
    live: bool = True


@dataclass(frozen=True, slots=True)
class P:
    """A reference to a declared parameter, usable anywhere a value is."""

    name: str


@dataclass(frozen=True, slots=True)
class Guard:
    """Base for the guard vocabulary (S1 §2.2). A guard is data: the framework
    evaluates it, the task never does."""


@dataclass(frozen=True, slots=True)
class After(Guard):
    """Elapsed time from state entry, in seconds. The only guard that bounds a
    wait by construction -- which is why the checker asks about it by type."""

    seconds: "float | P"


@dataclass(frozen=True, slots=True)
class GazeEnters(Guard):
    window: str


@dataclass(frozen=True, slots=True)
class GazeLeaves(Guard):
    window: str


@dataclass(frozen=True, slots=True)
class Response(Guard):
    device: str


@dataclass(frozen=True, slots=True)
class On:
    """One guarded transition: when `guard` fires, go to `to`."""

    guard: Guard
    to: "str | Outcome"


@dataclass(frozen=True, slots=True)
class State:
    name: str
    enter: list[Action] = field(default_factory=list)
    go: list[On] = field(default_factory=list)
    #: Declared when a state deliberately has no time bound -- free viewing of
    #: natural images is the motivating case (S1 §5.4). The checker refuses an
    #: undeclared one, so an unbounded wait is always a choice on the record
    #: rather than an omission nobody noticed.
    unbounded: bool = False


@dataclass(frozen=True, slots=True)
class Trial:
    start: str
    states: list[State]
    params: list[Param] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Bounded:
    """A reference to an entry in the rig/subject bounded config (S8 §4).

    The task names it; it never holds the value. Resolution happens against the
    subject's ceiling at run time, in the process that also owns the accounting.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Action:
    """Base for the action vocabulary (S1 §2.3)."""


@dataclass(frozen=True, slots=True)
class Custom(Action):
    """Behaviour the vocabulary lacks, named rather than contained (S1 §8).

    Resolves to a reviewed component in the framework's own source. A task using
    one is flagged onto the human-review list beside the welfare-critical modules
    -- accepted is not the same as unremarkable.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Emit(Action):
    """Strobe an event code. The code is allocated elsewhere (S2, ADR-0007) and
    validated at load; a task naming an unallocated one is refused."""

    code: int


class Reward(Action):
    """Deliver reward, by bounded-config reference.

    **Refuses a magnitude, deliberately and at runtime.** A type checker catches
    `Reward(0.15)` too, but nothing guarantees one is running on the machine that
    loads a generated task -- and welfare bounds that depend on someone having run
    a linter are not bounds. See S8 §7's welfare-critical module list.
    """

    __slots__ = ("ref",)

    def __init__(self, ref: Bounded) -> None:
        if not isinstance(ref, Bounded):
            raise TypeError(
                f"Reward takes a bounded-config reference, not {type(ref).__name__}: "
                f"a task may name how reward is configured but never how much it is"
            )
        object.__setattr__(self, "ref", ref)
