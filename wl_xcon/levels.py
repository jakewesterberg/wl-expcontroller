"""Where each trial sits in its session at every level, and the outcome counts the
console's strip shows at four of them (session-levels spec §3 and §5).

**The vocabulary** (the PI, 2026-10-01; spec §2):
- a session holds runs, each one start-to-stop of one task;
- a run holds blocks, each one stretch of consecutive trials under one block type,
  numbered as it occurs, since types recur;
- a block holds trials.

A task is named by its file, so two runs of one file are runs of one task.

**Pure bookkeeping.** No strobe, no record, no clock. `taskd.Session` holds one
`Levels` for the whole session, beside the counters a run's reset leaves alone (the
b3a-1 plan, decision 2). It asks it at each trial boundary, and does the strobing,
writing and publishing itself (`Session.run`, `Session.performance`).

**A block opens with its first trial** (the session-levels plan, ruling 1). A run
stopped before any trial is no block, takes no number and puts no `BLOCK_START` in the
recording.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

from wl_xcon.simulate import Tally


@dataclass(frozen=True, slots=True)
class Position:
    """One trial's ten position numbers, each counting from 1 (spec §3). Taken as the
    trial starts, so a trial that faults keeps them."""

    trial_number: int
    trial_in_task: int
    trial_in_run: int
    trial_in_block: int
    block_in_session: int
    block_in_task: int
    block_in_run: int
    run_in_session: int
    run_in_task: int
    task_in_session: int

    @classmethod
    def lone(cls, index: int) -> Position:
        """Trial `index`, counting from 0, of a session of one run of one block: what a
        census (`simulate`) writes, since it runs one task once."""
        n = index + 1
        return cls(n, n, n, n, 1, 1, 1, 1, 1, 1)

    def as_record(self) -> dict[str, int]:
        """The ten fields as `trials.jsonl` names them, in this order."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


def task_name(task: str) -> str:
    """A task's name: its file's stem. `tasks/fixation_detection.py` and the same file
    by an absolute path are one task (spec §2; plan ruling 2)."""
    return Path(task).stem


@dataclass
class Levels:
    """The session's counts at every level, and its outcome tallies at the session, each
    task and the open block. The run's own tally stays `Session.run`'s, as it always was.
    """

    #: Trials taken in the session: the last one's `trial_number` (XC-155).
    trials: int = 0
    #: Blocks opened in the session: the last one's `block_in_session`.
    blocks: int = 0
    #: Runs started in the session: the last one's `run_in_session`.
    runs: int = 0
    #: Each task's `task_in_session`, by name, in order of first appearance.
    order: dict = field(default_factory=dict)
    #: By task name: its trials, blocks and runs so far in the session.
    task_trials: dict = field(default_factory=dict)
    task_blocks: dict = field(default_factory=dict)
    task_runs: dict = field(default_factory=dict)
    #: The run in progress's task, or the last run's; `None` before any run.
    task: str | None = None
    #: The run in progress's trials and blocks.
    run_trials: int = 0
    run_blocks: int = 0
    #: The open block's trials, or `None` while no block is open.
    block_trials: int | None = None
    #: Outcome counts: the session's, each task's by name, and the open block's.
    session_tally: Tally = field(default_factory=Tally)
    task_tallies: dict = field(default_factory=dict)
    block_tally: Tally | None = None

    def start_run(self, task: str) -> None:
        """A run of `task` begins. Any block still open is closed: a run ending mid-block
        closes that block (spec §2)."""
        name = task_name(task)
        self.task = name
        self.runs += 1
        self.order.setdefault(name, len(self.order) + 1)
        self.task_runs[name] = self.task_runs.get(name, 0) + 1
        self.task_trials.setdefault(name, 0)
        self.task_blocks.setdefault(name, 0)
        self.task_tallies.setdefault(name, Tally())
        self.run_trials = 0
        self.run_blocks = 0
        self.block_trials = None
        self.block_tally = None

    def start_trial(self) -> tuple[Position, bool]:
        """The next trial's position, taken as it starts, and whether it opened a block
        (so `BLOCK_START` goes out before its `TRIAL_START`)."""
        if self.task is None:
            raise RuntimeError(
                "no run has started, so a trial has no position: start_run comes first"
            )
        opened = self.block_trials is None
        if opened:
            self.blocks += 1
            self.task_blocks[self.task] += 1
            self.run_blocks += 1
            self.block_trials = 0
            self.block_tally = Tally()
        self.trials += 1
        self.task_trials[self.task] += 1
        self.run_trials += 1
        self.block_trials += 1
        position = Position(
            trial_number=self.trials,
            trial_in_task=self.task_trials[self.task],
            trial_in_run=self.run_trials,
            trial_in_block=self.block_trials,
            block_in_session=self.blocks,
            block_in_task=self.task_blocks[self.task],
            block_in_run=self.run_blocks,
            run_in_session=self.runs,
            run_in_task=self.task_runs[self.task],
            task_in_session=self.order[self.task],
        )
        return position, opened

    def end_trial(self, result) -> None:
        """Count a trial's outcome at the session, its task and its block. A trial that
        faulted is never ended, so it counts nowhere: it has no outcome."""
        self.session_tally.add(result)
        self.task_tallies[self.task].add(result)
        self.block_tally.add(result)

    def end_block(self) -> bool:
        """Close the open block, and say whether one was open (so `BLOCK_END` goes out)."""
        if self.block_trials is None:
            return False
        self.block_trials = None
        self.block_tally = None
        return True
