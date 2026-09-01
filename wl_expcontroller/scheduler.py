"""The trial scheduler: which condition next, when a block ends, what is still owed.

Between-trial code (ADR-0006), so it may hold state and do arbitrary arithmetic --
it runs in the inter-trial interval where an error is observable and recoverable
rather than a dropped frame.

**Blocks are planned in wl.works before a session** (S3 §7). `wl-preproc` authors
block rows from that planner and quarantines on absence, so this schedules *within* a
planned block and never invents one. Changing condition weights or geometry is free;
changing task type is a planning operation.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from wl_expcontroller.task import Outcome

class Counting:
    """Which outcomes pay a condition's debt. **Declared per block** (PI, 2026-08-31),
    because the rule is task-specific and no single answer is right.

    "Run until ten correct" and "show the array a hundred times regardless of
    accuracy" are both ordinary requirements, and they disagree about every trial
    that is not correct. A scheduler that picked one would silently impose an
    experimental design on every task in the lab.
    """

    #: The animal chose. Wrong is still a datum about the condition.
    RESPONDED = frozenset(
        {
            Outcome.CORRECT,
            Outcome.WRONG_TARGET,
            Outcome.EARLY_RESPONSE,
            Outcome.LATE_RESPONSE,
            Outcome.EARLY_ERROR,
            Outcome.LATE_ERROR,
        }
    )

    #: Only a correct trial pays. An error leaves the debt standing.
    CORRECT_ONLY = frozenset({Outcome.CORRECT})

    #: The stimulus was shown, however the trial ended. Excludes the failures that
    #: happen *before* onset -- an animal that never fixated was never presented
    #: with anything, which is the distinction this exists to draw.
    PRESENTED = RESPONDED | {
        Outcome.NO_RESPONSE,
        Outcome.TARGET_BREAK,
        Outcome.CATCH_BREAK,
    }

    #: Everything, including trials the animal never engaged with.
    EVERY_TRIAL = frozenset(Outcome)


#: Retained for readers of older commits; `Counting.RESPONDED` is the name now.
COMPLETED = Counting.RESPONDED

#: The default requeue policy: outcomes where the condition still owes a datum, so
#: the trial comes back. Two families.
#:
#: **The animal failed to engage** rather than choosing wrongly -- it did not answer,
#: so nothing was measured.
#:
#: **The rig failed**, which is not the animal's doing at all. These were added on
#: 2026-09-01 with the outcomes themselves; without them a condition that lost a
#: trial to a dropped camera would be silently one datum short, and the shortfall
#: appears nowhere because a block ends when every condition is owed nothing.
REQUEUED = frozenset(
    {
        Outcome.FIXATION_BREAK,
        Outcome.NO_FIXATION,
        Outcome.TARGET_BREAK,
        Outcome.BLINK_BREAK,
        Outcome.TRACKER_LOST,
        Outcome.FAULT,
    }
)


@dataclass(frozen=True, slots=True)
class Order:
    """How the next condition is chosen. **Declared per block** (PI, 2026-08-31)."""


@dataclass(frozen=True, slots=True)
class Shuffled(Order):
    """Every still-owed condition once per pass, in random order.

    Balance as the block progresses, and a bound on how long an animal waits for any
    condition. Partly predictable near the end of a pass, when few remain.
    """


@dataclass(frozen=True, slots=True)
class WithReplacement(Order):
    """Each trial drawn independently, optionally weighted.

    No sequential predictability, and it supports conditions wanted rarely -- catch
    trials, probes. Balance only in expectation, so the counters matter more.
    """

    weights: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Constrained(Order):
    """Drawn with replacement, refusing runs longer than `max_run`.

    What most search and attention designs actually use, because an animal exploits
    runs: three of the same target position in a row and it stops searching and
    starts predicting.
    """

    max_run: int = 2
    weights: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Condition:
    name: str
    values: dict
    target: int


@dataclass(frozen=True, slots=True)
class Block:
    name: str
    conditions: list[Condition]
    #: `(proportion, window)` -- "80% correct over the last 20 judged trials".
    #: When absent, the block ends once every condition is owed nothing.
    criterion: tuple[float, int] | None = None
    #: Which outcomes pay a condition's debt.
    counts_toward: frozenset = Counting.RESPONDED
    #: Which outcomes are judged for the criterion. **Separate from the counter on
    #: purpose**: a block may count every presentation toward its quota while judging
    #: performance only on completed choices, and conflating the two makes a
    #: criterion track engagement rather than what the animal can do.
    criterion_over: frozenset | None = None
    #: Which outcomes send the condition back into the queue. **Declared per block**,
    #: because which aborts owe a datum is a task's judgement rather than the
    #: framework's: a block training an animal to hold fixation may treat a fixation
    #: break as a real error that pays its debt, while a block measuring a
    #: psychometric function must not.
    requeue_on: frozenset = REQUEUED
    order: Order = field(default_factory=Shuffled)


@dataclass
class Counts:
    attempted: int = 0
    completed: int = 0
    correct: int = 0


@dataclass
class Scheduler:
    blocks: list[Block]
    seed: int = 0
    _rng: random.Random = field(init=False, repr=False)
    _counts: dict = field(init=False, default_factory=dict, repr=False)
    _queue: deque = field(init=False, default_factory=deque, repr=False)
    requeued: list = field(init=False, default_factory=list)
    _window: deque = field(init=False, default_factory=deque, repr=False)
    _index: int = field(init=False, default=0, repr=False)
    _drawn: list = field(init=False, default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._counts = {c.name: Counts() for c in self.block.conditions}
        self._refill()

    @property
    def block(self) -> Block:
        return self.blocks[self._index]

    def _refill(self) -> None:
        """Queue the next draw, however this block declares its order.

        Always from the seeded generator, so a session's condition order is
        reconstructable -- a randomisation nobody can reproduce is one nobody can
        rule out as an explanation.
        """
        pending = [c.name for c in self.block.conditions if self.owed(c.name) > 0]
        if not pending:
            return
        order = self.block.order
        if isinstance(order, Shuffled):
            self._rng.shuffle(pending)
            self._queue.extend(pending)
            return

        weights = [order.weights.get(name, 1.0) for name in pending]
        if isinstance(order, Constrained):
            allowed = [
                name
                for name in pending
                if not (
                    len(self._drawn) >= order.max_run
                    and all(previous == name for previous in self._drawn[-order.max_run:])
                )
            ]
            if allowed:
                pending = allowed
                weights = [order.weights.get(name, 1.0) for name in pending]
        self._queue.append(self._rng.choices(pending, weights=weights, k=1)[0])

    def counts(self, condition: str) -> Counts:
        return self._counts[condition]

    def owed(self, condition: str) -> int:
        """Target minus **completed**, never minus attempted.

        An aborted trial produced no datum, so it left the condition owing exactly
        what it owed before.
        """
        target = next(c.target for c in self.block.conditions if c.name == condition)
        return max(0, target - self._counts[condition].completed)

    @property
    def _judged(self) -> frozenset:
        block = self.block
        return block.criterion_over if block.criterion_over is not None else block.counts_toward

    def upcoming(self) -> list[str]:
        return list(self._queue)

    @property
    def finished(self) -> bool:
        if self.block.criterion is not None:
            proportion, window = self.block.criterion
            if len(self._window) < window:
                return False
            return sum(self._window) / len(self._window) >= proportion
        return all(self.owed(c.name) == 0 for c in self.block.conditions)

    def next_trial(self) -> Condition:
        if not self._queue:
            self._refill()
        name = self._queue.popleft()
        self._drawn.append(name)
        self._counts[name].attempted += 1
        return next(c for c in self.block.conditions if c.name == name)

    def record(self, condition: str, outcome: Outcome) -> None:
        counts = self._counts[condition]
        if outcome in self.block.counts_toward:
            counts.completed += 1
            counts.correct += outcome is Outcome.CORRECT
        if outcome in self._judged:
            self._window.append(1 if outcome is Outcome.CORRECT else 0)
            if self.block.criterion is not None:
                while len(self._window) > self.block.criterion[1]:
                    self._window.popleft()
        if outcome not in self.block.counts_toward and outcome in self.block.requeue_on:
            # End of the block, not immediately: an animal must not be able to make
            # an easy condition repeat by breaking on the hard one.
            self.requeued.append(condition)
            self._queue.append(condition)
