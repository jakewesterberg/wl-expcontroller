# Session Levels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Every trial line records its position at every level of the session.
- The recording marks each block.
- The live feed carries performance at the session, task, run and block levels.
- The console's strip becomes the two cells the PI approved in mockup v13.

**Architecture:**
- **A new pure module, `wl_xcon/levels.py`**, holds the session's counters and tallies (`Levels`) and one trial's ten numbers (`Position`).
  - `taskd.Session` keeps one for the whole session and asks it at each trial boundary.
  - It does its own strobing (`BLOCK_START`/`BLOCK_END`, through `encode` and `codes` mirrors of wl-preproc's codec), its own writing (`record.trial`'s new `position`), and its own publishing (`Session.performance`, read by `Telemetry.of` into schema 12).
- **`web.py`'s strip** renders the two cells from the frame alone.

**Tech Stack:** Python 3.11+, pytest, msgpack (wire), wl-preproc's `decode_stream`/`assemble` (tests only, `WLX_REQUIRE_PREPROC=1`).

**Spec:** `docs/superpowers/specs/2026-10-01-session-levels-and-strip-design.md` (approved by the PI, 2026-10-01, with the block line showing `block_in_session`). Mockup: `docs/superpowers/mockups/2026-10-01-console-mockup-v13.html`.

## Global Constraints

- US English in code, docs and comments.
- No timing claim without a measurement (CLAUDE.md).
- Sim first: every behavior ships with a simulator-backed test. Nothing merges with a red suite.
- Hot-path discipline: every new call is at the trial boundary, in `Session.run`'s loop between trials. Nothing new runs per frame.
- The welfare-critical list in `docs/design/architecture.md` is not widened (the PI, 2026-09-30). `welfare.py` and `bounds.py` are not edited. `link.Telemetry.of` reads `welfare.returned_wall_at`, an existing public attribute.
- Every field counts from 1. `index` and `run` (0-based) stay unchanged on every line (spec §3).
- `BLOCK_START` is `0x8002` with two payload words `(block_in_session, task_code)`. `BLOCK_END` is marker 3. `UNALLOCATED_TASK_CODE = 0` (spec §4).
- Tests that need wl-preproc run with `WLX_REQUIRE_PREPROC=1`. Run the full suite as `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`.
- Prove a test can fail: break the code once by hand, see the named test fail, and revert. `tools/mutate.py` runs over every new and changed function in Task 7. Read its output, not its exit code.
- Backlog items, if any, take the next free ID in `docs/backlog.md` at the time. Run `tests/test_backlog.py` alone before committing.
- Branch `session-levels-design` (worktree `.claude/worktrees/levels`). If `main` has moved, rebase onto it before Task 1. `fix-port-race` and `fix-out-of-cage-8h` merge first: the second renames `tasks/twelve_hour_bounds.py` to `tasks/eight_hour_bounds.py` and `TWELVE_HOURS` to `EIGHT_HOURS` in the tests.

## Rulings in this plan

1. **A block opens with its first trial.** `BLOCK_START` goes out just before that trial's `TRIAL_START`. A run stopped before any trial has no block, and uses no block number.
2. **A task's identity is its file's stem** (`levels.task_name`). The same file by a relative and by an absolute path is one task (spec §2).
3. **`record.trial`'s `trial_number` keyword becomes `position`**, which carries `trial_number` with the other nine. Every row writes all ten.
4. **While no run goes, the strip shows one line under session:** "between runs" when `phase` is `between_runs`, and "no run going" otherwise (awaiting the return, or closed).
5. **"By HH:MM" is display arithmetic on published numbers**, like `_pct`: `wall_at - out_of_cage_seconds + out_of_cage_limit_s`.
6. **The reward-per-correct note** reads the frame's `params` row named `reward_correct` (a bounded ceiling). With no such row, the note is empty.

## Review Focus

1. **A run stopped before its first trial** (a Stop at the first boundary): no `BLOCK_START`, no `BLOCK_END`, no block number used. Its next run's first block takes the next number. Test: Task 4.
2. **A run that faults mid-block, then another run:** no `BLOCK_END` for the faulted block. The next block takes the next `block_in_session`. wl-preproc's `assemble` still yields every block. Test: Task 4.
3. **Pause and resume inside a block** keep one block: no second `BLOCK_START`. Test: Task 4.
4. **One task file named by two paths in one session** is one task: `run_in_task` 2, `task_in_session` unchanged. Test: Task 1.
5. **A frame between runs, awaiting the return, closed, or cage-side** renders the strip without a crash, in the words of rulings 4 and 5. Test: Task 6.

---

### Task 1: `levels.py`, the session's counters

**Files:**
- Create: `wl_xcon/levels.py`
- Test: `tests/test_levels.py` (new)
- Modify: `tools/mutation_gate.py`, listing `levels` in `RETURNS` (the gate refuses a module listed in neither `RETURNS` nor `EXEMPT`). Read how `scheduler` or `encode` is listed and do the same.

**Interfaces:**
- Produces:
  - `Position` (frozen dataclass): ten `int` fields in the order `trial_number, trial_in_task, trial_in_run, trial_in_block, block_in_session, block_in_task, block_in_run, run_in_session, run_in_task, task_in_session`.
  - `Position.lone(index: int) -> Position`.
  - `Position.as_record() -> dict[str, int]`.
  - `task_name(task: str) -> str`.
  - `Levels` (dataclass) with attributes `trials, blocks, runs, order, task_trials, task_blocks, task_runs, task, run_trials, run_blocks, block_trials, session_tally, task_tallies, block_tally`, and methods:
    - `start_run(task: str) -> None`;
    - `start_trial() -> tuple[Position, bool]` (the bool: whether this trial opened a block);
    - `end_trial(result) -> None`;
    - `end_block() -> bool` (whether a block was open).

- [ ] **Step 1: Write the failing tests** in `tests/test_levels.py`:

```python
"""`levels.Levels`: where each trial sits in its session (session-levels spec §3)."""

from types import SimpleNamespace

import pytest

from wl_xcon.levels import Levels, Position, task_name
from wl_xcon.task import Outcome

FIX = "tasks/fixation_detection.py"


def _result(outcome=Outcome.CORRECT):
    """What `Tally.add` reads of a trial's result."""
    return SimpleNamespace(visited=(), scored=(), outcome=outcome)


def _run(levels, task, blocks, close_last=True):
    """One run of `task`: `blocks` is each block's trial count. Returns the positions."""
    levels.start_run(task)
    out = []
    for at, count in enumerate(blocks):
        for _ in range(count):
            position, _opened = levels.start_trial()
            out.append(position)
            levels.end_trial(_result())
        if close_last or at < len(blocks) - 1:
            levels.end_block()
    return out


def test_the_spec_worked_example_numbers_every_level():
    """Calibration; fixation with blocks of 2, 2, 2; detection; fixation again, 2 then 1."""
    levels = Levels()
    _run(levels, "tasks/calibration.py", [2])
    _run(levels, FIX, [2, 2, 2])
    _run(levels, "tasks/detection.py", [3])
    last = _run(levels, FIX, [2, 1])[-1]

    assert last == Position(
        trial_number=14,
        trial_in_task=9,
        trial_in_run=3,
        trial_in_block=1,
        block_in_session=7,
        block_in_task=5,
        block_in_run=2,
        run_in_session=4,
        run_in_task=2,
        task_in_session=2,
    )


def test_a_block_opens_with_its_first_trial():
    levels = Levels()
    levels.start_run(FIX)

    assert levels.end_block() is False, "no trial ran, so no block is open"
    first, opened = levels.start_trial()
    second, again = levels.start_trial()

    assert (opened, again) == (True, False)
    assert (first.block_in_session, second.block_in_session) == (1, 1)
    assert (first.trial_in_block, second.trial_in_block) == (1, 2)


def test_a_run_stopped_before_any_trial_uses_no_block_number():
    levels = Levels()
    levels.start_run(FIX)
    levels.start_run(FIX)

    position, opened = levels.start_trial()

    assert opened and position.block_in_session == 1 and position.run_in_session == 2


def test_a_run_ending_mid_block_closes_that_block():
    levels = Levels()
    _run(levels, FIX, [2], close_last=False)
    levels.start_run(FIX)

    position, opened = levels.start_trial()

    assert opened
    assert (position.block_in_session, position.block_in_task, position.block_in_run) == (2, 2, 1)


def test_a_trial_that_faulted_keeps_its_numbers():
    """Taken as it starts: the faulted trial is in the recording, and none reuses them."""
    levels = Levels()
    levels.start_run(FIX)
    levels.start_trial()  # faults: no end_trial
    levels.start_run(FIX)

    position, _ = levels.start_trial()

    assert (position.trial_number, position.trial_in_task, position.trial_in_run) == (2, 2, 1)


def test_one_task_file_by_two_paths_is_one_task():
    levels = Levels()
    _run(levels, FIX, [1])
    position = _run(levels, "/home/rig/wl-xcon/tasks/fixation_detection.py", [1])[0]

    assert (position.run_in_task, position.task_in_session, position.trial_in_task) == (2, 1, 2)


def test_tasks_are_numbered_by_first_appearance():
    levels = Levels()
    _run(levels, "tasks/calibration.py", [1])
    _run(levels, FIX, [1])
    again = _run(levels, "tasks/calibration.py", [1])[0]

    assert levels.order == {"calibration": 1, "fixation_detection": 2}
    assert again.task_in_session == 1


def test_outcomes_are_counted_at_the_session_its_task_and_its_block():
    levels = Levels()
    levels.start_run(FIX)
    levels.start_trial()
    levels.end_trial(_result(Outcome.CORRECT))
    levels.start_trial()
    levels.end_trial(_result(None))  # a hang
    levels.end_block()
    levels.start_run("tasks/calibration.py")
    levels.start_trial()
    levels.end_trial(_result(Outcome.NO_FIXATION))

    assert levels.session_tally.outcomes == {Outcome.CORRECT: 1, Outcome.NO_FIXATION: 1}
    assert levels.session_tally.hangs == 1
    assert levels.task_tallies["fixation_detection"].outcomes == {Outcome.CORRECT: 1}
    assert levels.task_tallies["calibration"].outcomes == {Outcome.NO_FIXATION: 1}
    assert levels.block_tally.outcomes == {Outcome.NO_FIXATION: 1}


def test_closing_a_block_drops_its_tally():
    levels = Levels()
    levels.start_run(FIX)
    levels.start_trial()
    levels.end_trial(_result())

    assert levels.end_block() is True
    assert levels.block_tally is None and levels.block_trials is None


def test_a_trial_before_any_run_is_refused():
    with pytest.raises(RuntimeError, match="no run has started"):
        Levels().start_trial()


def test_a_census_trial_sits_alone_in_one_run_of_one_block():
    assert Position.lone(4) == Position(5, 5, 5, 5, 1, 1, 1, 1, 1, 1)


def test_the_record_names_all_ten_fields_in_order():
    assert list(Position.lone(0).as_record()) == [
        "trial_number", "trial_in_task", "trial_in_run", "trial_in_block",
        "block_in_session", "block_in_task", "block_in_run",
        "run_in_session", "run_in_task", "task_in_session",
    ]


def test_a_task_is_named_by_its_files_stem():
    assert task_name("/abs/tasks/fixation_detection.py") == "fixation_detection"
```

- [ ] **Step 2: Run the tests to see them fail.**
  - Run: `python3 -m pytest -q -p no:cacheprovider tests/test_levels.py`
  - Expected: errors on `ModuleNotFoundError: No module named 'wl_xcon.levels'`.

- [ ] **Step 3: Write `wl_xcon/levels.py`:**

```python
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
```

Then add `levels` to `tools/mutation_gate.py`'s `RETURNS`, as its neighbors are listed.

- [ ] **Step 4: Run the tests, and the gate's own tests.**
  - Run: `python3 -m pytest -q -p no:cacheprovider tests/test_levels.py tests/test_mutation_gate.py`
  - Expected: all pass.
- [ ] **Step 5: Prove two of them can fail.** Change `opened = self.block_trials is None` to `opened = True`, run `tests/test_levels.py`, and see `test_a_block_opens_with_its_first_trial` fail. Revert. Do the same with `self.order.setdefault(name, len(self.order) + 1)` changed to `self.order[name] = len(self.order) + 1`, and see `test_tasks_are_numbered_by_first_appearance` fail. Revert.
- [ ] **Step 6: Commit.** `git add wl_xcon/levels.py tests/test_levels.py tools/mutation_gate.py`, then `git commit -m "Count where each trial sits in its session, at every level"`.

---

### Task 2: The block markers in the codec mirrors

**Files:**
- Modify: `wl_xcon/encode.py`, beside `TRIAL_NUMBER` and `words_for`.
- Modify: `wl_xcon/codes.py`, beside `TRIAL_START`/`TRIAL_END`.
- Test: `tests/test_event_encoding.py`.

**Interfaces:**
- Produces:
  - `encode.BLOCK_START = 0x8002`;
  - `encode.UNALLOCATED_TASK_CODE = 0`;
  - `encode.words_for_block(block_number: int, task_code: int) -> list[int]`, four words;
  - `codes.BLOCK_END = 3`.

- [ ] **Step 1: Write the failing tests** in `tests/test_event_encoding.py`. Use the file's existing import of wl-preproc's module, `wl_preproc_events`; read the file's head for its exact name.

```python
from wl_xcon import codes, encode


def test_the_block_markers_are_wl_preprocs():
    assert codes.BLOCK_END == wl_preproc_events.Marker.BLOCK_END
    assert encode.BLOCK_START == wl_preproc_events.Escape.BLOCK_START
    assert wl_preproc_events.PAYLOAD_WORD_COUNTS[wl_preproc_events.Escape.BLOCK_START] == 2


@pytest.mark.parametrize(("block", "task"), [(1, 0), (27, 0), (65_535, 255)])
def test_a_block_start_is_framed_exactly_as_wl_preproc_frames_it(block, task):
    theirs = wl_preproc_events.encode_payload(wl_preproc_events.Escape.BLOCK_START, [block, task])
    assert encode.words_for_block(block, task) == list(theirs)


def test_a_block_start_round_trips_through_wl_preprocs_decoder():
    words = encode.words_for_block(7, encode.UNALLOCATED_TASK_CODE)
    events = wl_preproc_events.decode_stream([(i * 0.001, w) for i, w in enumerate(words)])
    assert [(e.escape, e.words) for e in events] == [(wl_preproc_events.Escape.BLOCK_START, (7, 0))]


@pytest.mark.parametrize(("block", "task", "said"), [
    (0, 0, "counts from 1"),
    (65_536, 0, "block number out of 16-bit range"),
    (1, -1, "task code out of 16-bit range"),
    (1, 65_536, "task code out of 16-bit range"),
])
def test_a_block_start_that_cannot_be_framed_is_refused(block, task, said):
    with pytest.raises(ValueError, match=said):
        encode.words_for_block(block, task)
```

If `decode_stream` yields an object whose attributes differ from `escape` and `words`, read `wl_preproc/contracts/events.py`'s `PayloadEvent` and use its names. `PAYLOAD_WORD_COUNTS` is the name `encode.py`'s comment gives for wl-preproc's count table; confirm it in that file.

- [ ] **Step 2: Run them to see them fail.**
  - Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider tests/test_event_encoding.py`
  - Expected: failures on `AttributeError` for `BLOCK_END`, `BLOCK_START` and `words_for_block`.

- [ ] **Step 3: Implement.** In `encode.py`, after `CONDITION`:

```python
#: wl-preproc's `Escape.BLOCK_START`: two payload words, `(block_number,
#: task_type_code)`, each a 16-bit word of its own, not one uint32. `taskd` strobes it
#: as each block opens, with the block's `block_in_session` (session-levels spec §4).
BLOCK_START = 0x8002

#: The task type code a task carries until wl-xtasks allocates codes (spec §4).
#: wl-preproc's `TaskTypeCode` namespace is 1-255 (`contracts/events.py`), so 0 names no
#: task: it says "not allocated" rather than naming another.
UNALLOCATED_TASK_CODE = 0
```

After `words_for`:

```python
def words_for_block(block_number: int, task_code: int) -> list[int]:
    """`BLOCK_START`'s full word sequence: the escape, the block's number in the
    session, the task's type code, and the checksum every escape carries.

    Called before anything of the block is strobed, as `words_for` is for a trial's
    number (XC-155): a value that cannot be framed raises ahead of the stream."""
    if not 0 <= block_number <= WORD_MASK:
        raise ValueError(f"block number out of 16-bit range: {block_number}")
    if block_number < 1:
        raise ValueError(f"a block number counts from 1: {block_number}")
    if not 0 <= task_code <= WORD_MASK:
        raise ValueError(f"task code out of 16-bit range: {task_code}")
    payload = [block_number, task_code]
    return [BLOCK_START, *payload, _checksum(BLOCK_START, payload)]
```

In `codes.py`, after `TRIAL_END = 33`, and extend the comment block above `TRIAL_START` with one sentence:

```python
#: **`BLOCK_END` closes a block** (session-levels spec §4): `taskd.Session.run` strobes
#: it after a block's last `TRIAL_END`, when its block type is done or its run ends by
#: design. A run that faults sends none, as it sends no `RUN_END`.
BLOCK_END = 3
```

- [ ] **Step 4: Run the tests.**
  - Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider tests/test_event_encoding.py`
  - Expected: all pass.
- [ ] **Step 5: Prove the framing test can fail.** Swap the payload to `[task_code, block_number]` and see `test_a_block_start_is_framed_exactly_as_wl_preproc_frames_it` fail for `(27, 0)`. Revert.
- [ ] **Step 6: Commit.** `git commit -am "Mirror wl-preproc's block markers, framed and pinned against theirs"`.

---

### Task 3: Ten numbers on every trial line

**Files:**
- Modify: `wl_xcon/record.py` (`SessionRecord.trial`, ~189-240).
- Modify: `wl_xcon/simulate.py` (`run_session`'s `record.trial` call, ~356).
- Modify: `wl_xcon/taskd.py`:
  - the `_trial_number` field, ~339-347, which `_levels` replaces;
  - `run()`, ~1895-1935, for `start_run` and the start row's three fields;
  - `run()`, ~2050-2113, for `start_trial`, `end_trial`, `end_block` at the advance, and `position`.
- Test: `tests/test_record.py`, `tests/test_taskd.py`, `tests/test_simulate.py` where they call `record.trial` or read `_trial_number`.

**Interfaces:**
- Consumes (Task 1): `Levels`, `Position`.
- Produces:
  - `SessionRecord.trial(index, outcome, params, block="", condition="", *, run: int, position: Position)`.
  - `Session._levels: Levels`.
  - `runs.jsonl` start rows gain `run_in_session`, `run_in_task` and `task_in_session`.

- [ ] **Step 1: Write the failing tests.**

In `tests/test_record.py`, a row carries all ten:

```python
from wl_xcon.levels import Position


def test_a_trial_row_carries_its_ten_position_numbers(tmp_path):
    record = _record(tmp_path)  # use this file's existing way of building a SessionRecord
    position = Position(512, 400, 58, 18, 27, 21, 3, 4, 2, 2)
    record.trial(index=57, outcome="correct", params={}, run=3, position=position)

    row = _rows(tmp_path)[-1]  # this file's existing reader of trials.jsonl
    assert {k: row[k] for k in position.as_record()} == position.as_record()
    assert (row["index"], row["run"]) == (57, 3), "the 0-based fields stay as they were"
```

Update every existing `record.trial(..., trial_number=N)` call in `tests/test_record.py`:
- to `position=Position.lone(N - 1)`;
- and for the two-run example (~line 154, `run=1, trial_number=2`) to `position=Position(2, 2, 1, 1, 2, 2, 1, 2, 2, 1)`.

Rename `test_a_trial_row_is_never_written_without_its_trial_number` to `..._without_its_position`. It asserts a `TypeError` when `position` is omitted.

In `tests/test_taskd.py`, the path, with a recurring block plan across runs and a task between:

```python
from wl_xcon.task import Outcome


def _plan(*names, each=2):
    """A plan whose blocks recur by name: every trial pays, so each block runs exactly `each`."""
    return [
        Block(
            name=name,
            conditions=[Condition(name.lower(), {}, target=each)],
            counts_toward=frozenset(Outcome),
        )
        for name in names
    ]


def _levels_run(blocks=None, trials=50, seed=2):
    return RunSpec(
        task="tasks/fixation_detection.py", trials=trials, seed=seed, values=dict(VALUES), blocks=blocks
    )


def _other_run(tmp_path, blocks):
    """A run of a second task: `ONE_STATE_TASK`, written to a file of its own."""
    path = tmp_path / "one_state.py"
    path.write_text(ONE_STATE_TASK)
    return RunSpec(task=str(path), trials=50, seed=2, values={}, blocks=blocks)


def test_every_line_carries_its_position_across_runs_blocks_and_tasks(tmp_path):
    """Spec §3 on a real service session: fixation with blocks X, Y, X; a second task
    (`one_state`); then fixation again with X, Y. Each line's ten numbers are what the
    spec's definitions give: trials 1-6 in blocks 1-3, trial 7 in block 4, trials 8-11
    in blocks 5-6."""
    session = _service_session(tmp_path)
    session.run(_levels_run(blocks=_plan("X", "Y", "X")))
    session.run(_other_run(tmp_path, _plan("C", each=1)))
    session.run(_levels_run(blocks=_plan("X", "Y")))
    session.end_runs("jake")

    lines = _trial_rows(session)
    last = lines[-1]
    assert [line["trial_number"] for line in lines] == list(range(1, 12))
    assert {k: last[k] for k in (
        "trial_in_task", "trial_in_run", "trial_in_block", "block_in_session",
        "block_in_task", "block_in_run", "run_in_session", "run_in_task", "task_in_session",
    )} == {
        "trial_in_task": 10, "trial_in_run": 4, "trial_in_block": 2, "block_in_session": 6,
        "block_in_task": 5, "block_in_run": 2, "run_in_session": 3, "run_in_task": 2,
        "task_in_session": 1,
    }
    assert [line["block"] for line in lines[:6]] == ["X", "X", "Y", "Y", "X", "X"]
```

If a service session refuses a `RunSpec` whose task is not one it offers, give `_service_session` the file to offer, the way its keyword arguments allow. Read `_service_session` first. `ONE_STATE_TASK` (XC-155) has no parameters, so `values={}`.

```python
def test_a_runs_start_row_places_it_in_the_session(tmp_path):
    session = _service_session(tmp_path)
    session.run(_levels_run(blocks=_plan("X")))
    session.run(_levels_run(blocks=_plan("X")))
    session.end_runs("jake")

    starts = [row for row in _run_rows(session) if row["event"] == "start"]  # this file's reader of runs.jsonl
    assert [(r["run_in_session"], r["run_in_task"], r["task_in_session"]) for r in starts] == [
        (1, 1, 1),
        (2, 2, 1),
    ]
```

If no `_run_rows` helper exists, read `runs.jsonl` the way `_trial_rows` reads `trials.jsonl`.

Update XC-155's counter test (~4700, `session._trial_number = 0xFFFF`) to `session._levels.trials = 0xFFFF`, and its docstring's `Session._trial_number` to `Session._levels`.

- [ ] **Step 2: Run them to see them fail.**
  - Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider tests/test_record.py tests/test_taskd.py -k "position or start_row or 0xFFFF or trial_number"`
  - Expected: failures, `TypeError: ... unexpected keyword argument 'position'`.

- [ ] **Step 3: Implement.**

`record.py`, `trial()`: replace the `trial_number: int` parameter with `position: Position` (import from `wl_xcon.levels`). In the row dict, replace `"trial_number": trial_number,` with `**position.as_record(),`. Replace the docstring's "And its trial number" paragraph with:

```text
        **And its position at every level** (session-levels spec §3): ten numbers, each
        counting from 1 -- `trial_number` (XC-155: the number `taskd` strobed in the
        trial's `TRIAL_NUMBER` escape, so the line and the recording's trial carry one
        number, which wl-preproc joins by) and the trial's place in its task, run and
        block, its block's in the session, task and run, its run's in the session and
        task, and its task's in the session. Required, as `run` is: a line written
        without them would join nothing, and nothing would say so.
```

`simulate.py`: replace `trial_number=index + 1,` and its two comment lines with:

```python
                # One run of one block (`levels.Position.lone`): the numbers a rig's
                # session of this one run would strobe and write; a census strobes none.
                position=Position.lone(index),
```

Import `Position` inside `run_session`, with the comment "`levels` imports this module for `Tally`, so a module-level import would cycle".

`taskd.py`:
- Replace the `_trial_number` field and its comment with:

```python
    #: **Where each trial sits in the session at every level** (session-levels spec
    #: §3): its ten position numbers, `trial_number` (XC-155) among them, and the
    #: outcome counts the strip shows at the session, task and block levels. Kept for
    #: the session beside `_sequence`, which a run's reset leaves alone (the b3a-1 plan,
    #: decision 2): a number counted across runs, or per task across runs, would
    #: restart with each run otherwise. **Taken as a trial starts**, so a trial that
    #: faults keeps its numbers -- it is in the recording -- and the next trial never
    #: reuses them.
    _levels: Levels = field(init=False, default_factory=Levels, repr=False)
```

- In `run()`, right after `self.run_index = 0 if self.run_index is None else self.run_index + 1`:

```python
        levels = self._levels
        levels.start_run(run.task)
```

- In the start `record.run_row(...)`, add:

```python
            run_in_session=levels.runs,
            run_in_task=levels.task_runs[levels.task],
            task_in_session=levels.order[levels.task],
```

- At the advance, just before `scheduler.advance()`:

```python
                    # The block its type finished is closed; the next trial opens the next.
                    levels.end_block()
```

- At the trial boundary, replace `self._trial_number += 1` and `escape = words_for(TRIAL_NUMBER, self._trial_number)` with:

```python
                position, _opened = levels.start_trial()
                escape = words_for(TRIAL_NUMBER, position.trial_number)
```

  Then update the comment's "`_trial_number`, taken as it starts" to "`position.trial_number`, taken as it starts (`Levels.start_trial`)".
- After `tally.add(result)`, add `levels.end_trial(result)`.
- In `record.trial(...)`, replace `trial_number=self._trial_number,` with `position=position,`.

Import `from wl_xcon.levels import Levels`.

- [ ] **Step 4: Run the full suite.**
  - Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
  - Expected: green. Every test that called `record.trial(..., trial_number=...)` was updated in Step 1. Grep for `trial_number=` in `tests/` and `wl_xcon/` to be sure.
- [ ] **Step 5: Prove it can fail.** In `record.trial`, drop `**position.as_record(),` and see `test_a_trial_row_carries_its_ten_position_numbers` and the path test fail. Revert.
- [ ] **Step 6: Commit.** `git commit -am "Write every trial's ten position numbers, and place each run in its session"`.

---

### Task 4: `BLOCK_START` and `BLOCK_END` in the recording

**Files:**
- Modify: `wl_xcon/taskd.py`, `run()`: the trial boundary, the advance, and the by-design end before `RUN_END`.
- Modify: `docs/design/architecture.md`, the hardware-truth paragraph on the trial markers (~303-320).
- Test: `tests/test_taskd.py`.

**Interfaces:**
- Consumes (Task 2): `encode.BLOCK_START`, `encode.words_for_block`, `encode.UNALLOCATED_TASK_CODE`, `codes.BLOCK_END`.
- Consumes (Task 3): `Levels.start_trial()`'s `opened`, and `Levels.end_block()`'s return.

- [ ] **Step 1: Write the failing tests** in `tests/test_taskd.py`, beside XC-155's stream tests, with this file's helpers (`_service_session`, `_Scripted`, `_walled`, `_scheduled_at_trial`, the constants `TRIAL_START_CODE`, `TRIAL_END_CODE`, `RUN_END`, `PAUSE_CODE` and `RESUME_CODE`, and `their_events`/`their_assemble`, guarded as XC-155's path test guards them):

```python
from wl_xcon.codes import BLOCK_END
from wl_xcon.encode import BLOCK_START, UNALLOCATED_TASK_CODE, words_for_block


def _block_words(codes):
    """The stream's block markers in order, read by position as wl-preproc reads them:
    an escape (a word at or above 0x8000) is followed by its two payload words and its
    checksum, all skipped. Trial 3's checksum is 0x8002 and trial 3's low word is 3, so
    a scan by value would misread both (XC-155's cut-escape finding)."""
    out, i = [], 0
    while i < len(codes):
        word = codes[i]
        if word >= 0x8000:
            if word == BLOCK_START:
                out.append(("start", codes[i + 1]))
            i += 4
            continue
        if word == BLOCK_END:
            out.append("end")
        i += 1
    return out


def test_each_block_is_opened_and_closed_in_the_stream(tmp_path):
    session = _service_session(tmp_path)
    session.run(_levels_run(blocks=_plan("X", "Y", "X")))
    session.end_runs("jake")

    assert _block_words(session.card.codes) == [
        ("start", 1), "end", ("start", 2), "end", ("start", 3), "end",
    ]


def test_a_block_opens_just_before_its_first_trial_and_closes_after_its_last(tmp_path):
    session = _service_session(tmp_path)
    session.run(_levels_run(blocks=_plan("X")))
    session.end_runs("jake")

    codes = session.card.codes
    first = codes.index(TRIAL_START_CODE)
    assert codes[first - 4 : first] == words_for_block(1, UNALLOCATED_TASK_CODE)
    last = len(codes) - 1 - codes[::-1].index(TRIAL_END_CODE)
    assert codes[last + 1 : last + 3] == [BLOCK_END, RUN_END]


def test_a_run_stopped_before_its_first_trial_marks_no_block(tmp_path):
    """Review Focus 1: a Stop drained at the first boundary ends the run with no trial;
    the next run's first block is number 1."""
    link = Simulated()
    session = _service_session(tmp_path, link=link)
    link.queue(Stop(by="jake"))
    session.run(_levels_run(blocks=_plan("X")))
    session.run(_levels_run(blocks=_plan("X")))
    session.end_runs("jake")

    assert _block_words(session.card.codes) == [("start", 1), "end"]
    assert [row["block_in_session"] for row in _trial_rows(session)] == [1, 1]


def test_a_faulted_run_leaves_its_block_open_and_the_next_takes_the_next_number(
    tmp_path, monkeypatch
):
    """Review Focus 2, through wl-preproc: no BLOCK_END for the faulted block; the next
    run's first block is 2; assemble yields both."""
    from wl_xcon import taskd

    real, calls = taskd.run_trial, []

    def faults_second(*args, **kwargs):
        calls.append(None)
        if len(calls) == 2:
            raise RuntimeError("the display went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", faults_second)
    session = _service_session(tmp_path)
    with pytest.raises(RuntimeError, match="the display went away"):
        session.run(_levels_run(blocks=_plan("X", each=3)))
    session.run(_levels_run(blocks=_plan("X")))
    session.end_runs("jake")

    assert _block_words(session.card.codes) == [("start", 1), ("start", 2), "end"]
    stream = [(i * 0.001, word) for i, word in enumerate(session.card.codes)]
    assembly = their_assemble(their_events.decode_stream(stream))
    assert [block.block_id for block in assembly.blocks] == [1, 2]
    assert assembly.blocks[1].end_s is not None


def test_a_pause_inside_a_block_keeps_one_block(tmp_path):
    """Review Focus 3: paused after the second of three trials, then resumed; one block."""
    link = _Scripted(script={1: [Resume(by="sam")]}, step=10.0)
    session, wall = _walled(tmp_path, link, trials=3)
    link.wall = wall
    _scheduled_at_trial(link, session, 2, Pause(by="jake"))

    session.run()

    assert PAUSE_CODE in session.card.codes and RESUME_CODE in session.card.codes
    assert _block_words(session.card.codes) == [("start", 1), "end"]


def test_a_sessions_blocks_and_trials_assemble_in_wl_preproc(tmp_path):
    """Spec §9, the path: fixation X, Y, X; a second task; fixation again, stopped after
    its first trial, mid-block. Every block assembles with its block_in_session and an
    end, the stopped one closed by BLOCK_END; every trial lies inside one block."""
    link = Simulated()
    session = _service_session(tmp_path, link=link)
    _scheduled_at_trial(link, session, 8, Stop(by="jake"))
    session.run(_levels_run(blocks=_plan("X", "Y", "X")))
    session.run(_other_run(tmp_path, _plan("C", each=1)))
    session.run(_levels_run(blocks=_plan("X", "Y")))
    session.end_runs("jake")

    stream = [(i * 0.001, word) for i, word in enumerate(session.card.codes)]
    assembly = their_assemble(their_events.decode_stream(stream))
    assert assembly.errors == []
    assert [block.block_id for block in assembly.blocks] == [1, 2, 3, 4, 5]
    assert all(block.end_s is not None for block in assembly.blocks)
    assert len(assembly.trials) == 8
    for trial in assembly.trials:
        inside = [b for b in assembly.blocks if b.start_s <= trial.start_s <= b.end_s]
        assert len(inside) == 1, trial
```

Import `Stop`, `Pause`, `Resume` and `Simulated` as this file already does for its other tests.

Then re-read every test in `tests/test_taskd.py`, `tests/test_service.py` and `tests/test_serve.py` that pins an exact list of strobed codes (grep `card.codes ==` and `codes[`). Extend each with the `BLOCK_START` words and `BLOCK_END` where they now fall. Do not loosen any of them (spec §9). `test_nothing_is_strobed_inside_a_trial_numbers_escape` asserts the boundary's mark immediately precedes each `TRIAL_START`. For the first trial, a block's four words now sit between them: assert the mark precedes the block's escape there, and keep every other assertion.

XC-155's path test (`test_a_sessions_stream_assembles_in_wl_preproc_into_its_trials_numbered_across_runs`) must still pass unchanged: blocks do not change trials.

- [ ] **Step 2: Run them to see them fail.**
  - Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider tests/test_taskd.py -k "block"`
  - Expected: the new tests fail with no block words in the stream.

- [ ] **Step 3: Implement** in `taskd.run()`.

At the trial boundary, replace the Task 3 lines from `position, _opened = levels.start_trial()` through the `TRIAL_NUMBER` emits with:

```python
                position, opened = levels.start_trial()
                # **Every word this boundary strobes is computed first** (XC-155): a
                # value that cannot be framed raises here, ahead of the stream, never
                # leaving a block or a trial opened without its number.
                block_words = (
                    words_for_block(position.block_in_session, UNALLOCATED_TASK_CODE)
                    if opened
                    else ()
                )
                escape = words_for(TRIAL_NUMBER, position.trial_number)
                # **A block opens with its first trial** (session-levels spec §4; plan
                # ruling 1): `BLOCK_START` with its number in the session and its task's
                # code, unbroken, just before that trial's `TRIAL_START`.
                for word in block_words:
                    self.card.emit(word)
                self.card.emit(TRIAL_START)
                for word in escape:
                    self.card.emit(word)
```

At the advance, replace Task 3's `levels.end_block()` with:

```python
                    # The block its type finished closes in the stream after its last
                    # `TRIAL_END`; the next trial opens the next (session-levels spec §4).
                    if levels.end_block():
                        self.card.emit(BLOCK_END)
```

At the by-design end, just before `if end_code is not None:` (the `RUN_END` emit), add:

```python
            # **A run that ends by design closes its open block first** (spec §4):
            # `BLOCK_END`, then `RUN_END`. A fault or an interrupt never reaches here,
            # so it sends neither, as it sends no `RUN_END` today.
            if levels.end_block():
                self.card.emit(BLOCK_END)
```

Import `BLOCK_END` from `wl_xcon.codes`, and `BLOCK_START` (only if a comment or assertion needs it), `UNALLOCATED_TASK_CODE` and `words_for_block` from `wl_xcon.encode`.

`architecture.md`: in the paragraph describing `TRIAL_START`/`TRIAL_NUMBER`/`TRIAL_END`, add:

```text
  **Each block is marked too** (the session-levels spec, 2026-10-01): `BLOCK_START`
  (`0x8002`, its `block_in_session` and its task's code, 0 until wl-xtasks allocates
  codes) just before the block's first `TRIAL_START`, and `BLOCK_END` (3) after its last
  `TRIAL_END` when its block type is done or its run ends by design; a run that faults
  sends neither. A block is a stretch of trials under one block type inside a run, not
  a run (the PI, 2026-10-01); runs stay `RUN_START`/`RUN_END`.
```

Also add, where `trials.jsonl`'s fields are described: "every line carries ten position numbers (`levels.Position`; session-levels spec §3)".

- [ ] **Step 4: Run the full suite.** `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`. Expected: green.
- [ ] **Step 5: Prove the end-of-run close can fail.** Delete the `BLOCK_END` before `RUN_END`, and see `test_each_block_is_opened_and_closed_in_the_stream` and the wl-preproc path test fail. Revert.
- [ ] **Step 6: Commit.** `git commit -am "Mark each block in the recording, opened with its first trial and closed by design"`.

---

### Task 5: The feed, schema 12

**Files:**
- Modify: `wl_xcon/link.py`:
  - `SCHEMA` to 12;
  - new `Counts` and `Performance` dataclasses, before `Telemetry`;
  - `Telemetry` gains `performance` and `returned_at`;
  - `Telemetry.of`;
  - `_telemetry_out`, `_telemetry_from`, and their two new helpers.
- Modify: `wl_xcon/taskd.py`: a module function `_counts(tally)` and the `Session.performance` property, beside `task`.
- Modify: `tests/_frames.py`, `tests/test_cli.py` (~900, its own `Telemetry(...)`), and `tests/test_link.py` (`_session_with`'s `SimpleNamespace`, ~132).
- Test: `tests/test_link.py`, `tests/test_taskd.py`.

**Interfaces:**
- Consumes (Tasks 1 and 3): `Session._levels`.
- Produces:
  - `link.Counts(outcomes: dict, hangs: int)`;
  - `link.Performance(session: Counts, task: Counts | None, run: Counts | None, block: Counts | None, task_name: str | None, runs_of_task: int | None, run_in_session: int | None, block_in_session: int | None, block_type: str | None)`;
  - `Telemetry.performance: Performance`;
  - `Telemetry.returned_at: float | None`;
  - `Session.performance -> link.Performance`.

- [ ] **Step 1: Write the failing tests.**

`tests/test_link.py`, the round trip (beside the existing encode/decode round-trip test):

```python
def test_the_strips_levels_and_the_return_survive_the_wire():
    original = replace(
        frame(),  # import from _frames, as this file's other round-trip test does, or build via Telemetry.of
        performance=Performance(
            session=Counts({"correct": 9, "no_fixation": 2}, 1),
            task=Counts({"correct": 7}, 0),
            run=Counts({"correct": 4}, 0),
            block=Counts({"correct": 2}, 0),
            task_name="fixation_detection",
            runs_of_task=2,
            run_in_session=3,
            block_in_session=27,
            block_type="near",
        ),
        returned_at=1_700_000_100.0,
    )
    assert decode(encode(original)) == original


def test_a_frame_between_runs_carries_the_session_alone():
    performance = Performance(Counts({}, 0), None, None, None, None, None, None, None, None)
    original = replace(frame(), performance=performance, phase="between_runs")
    assert decode(encode(original)).performance == performance
```

`tests/test_taskd.py`, the session's own reading:

```python
def test_the_performance_counts_the_session_the_task_the_run_and_the_block(tmp_path):
    """Spec §5: read at a boundary during a run (from `observe`), then between runs."""
    session = _service_session(tmp_path)
    seen = []
    session.observe = lambda condition, values, result: seen.append(session.performance)
    session.run(_levels_run(blocks=_plan("X", "Y")))
    session.run(_levels_run(blocks=_plan("X")))

    during = seen[-1]  # the second run's last trial
    assert during.task_name == "fixation_detection"
    assert (during.runs_of_task, during.run_in_session, during.block_in_session) == (2, 2, 3)
    assert during.block_type == "X"
    assert sum(during.session.outcomes.values()) + during.session.hangs == 6
    assert sum(during.task.outcomes.values()) + during.task.hangs == 6
    assert sum(during.run.outcomes.values()) + during.run.hangs == 2
    assert sum(during.block.outcomes.values()) + during.block.hangs == 2

    between = session.performance
    assert (between.task, between.run, between.block, between.task_name) == (None, None, None, None)
    assert sum(between.session.outcomes.values()) + between.session.hangs == 6
```

`observe` is called after `levels.end_trial` and `record.trial` (Task 3), so the counts include that trial. If `_service_session` rejects setting `observe` after construction, set it through the helper's own keyword. Read `_service_session`.

`test_link.py`: assert `Telemetry.of(...)` reads `returned_at` from `session.welfare.returned_wall_at`:

```python
def test_the_frame_reads_the_return_from_welfare():
    session = _session_with(delivered_ml=1.0)
    session.welfare.returned_wall_at = 1_700_000_200.0
    assert Telemetry.of(session, Tally(), _scheduler(), index=0).returned_at == 1_700_000_200.0
```

Adapt this to how `_session_with` exposes `welfare`. If it is a real `Welfare`, call its `returned_to_cage` with the arguments its signature needs instead of setting the attribute.

- [ ] **Step 2: Run them to see them fail.**
  - Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_taskd.py -k "performance or levels or return"`
  - Expected: `ImportError` for `Counts`/`Performance`, or `AttributeError`.

- [ ] **Step 3: Implement.**

`link.py`, before `class Telemetry`:

```python
@dataclass(frozen=True, slots=True)
class Counts:
    """One level's outcome counts for the strip (session-levels spec §5): by outcome's
    wire string, as `Telemetry.outcomes`, and the trials that reached no outcome."""

    outcomes: dict
    hangs: int


@dataclass(frozen=True, slots=True)
class Performance:
    """The strip's four levels (session-levels spec §5 and §6), from
    `taskd.Session.performance`: read from the session's `levels.Levels` and its run's
    tally, never recomputed here.

    `task`, `run` and `block` and their names are `None` while no run goes: between
    runs, awaiting the return, closed. `block`, `block_in_session` and `block_type`
    are also `None` in a run before its first trial and between its blocks: a block
    opens with its first trial (the session-levels plan, ruling 1)."""

    session: Counts
    task: Counts | None
    run: Counts | None
    block: Counts | None
    #: The run's task by name (`levels.task_name`), and how many runs of it so far.
    task_name: str | None
    runs_of_task: int | None
    #: The run in progress's `run_in_session`.
    run_in_session: int | None
    #: The open block's `block_in_session` and its block type.
    block_in_session: int | None
    block_type: str | None
```

`Telemetry`: append two fields at the end of the class's fields, after `offered_tasks`:

```python
    #: `session.performance`: the strip's session, task, run and block counts
    #: (session-levels spec §5).
    performance: Performance
    #: `welfare.returned_wall_at`: the recorded return, on the session's anchored clock,
    #: or `None` before it (spec §5). Read, as every welfare figure here is.
    returned_at: float | None
```

`Telemetry.of`: add `performance=session.performance,` and `returned_at=session.welfare.returned_wall_at,` at the end of the `cls(...)` call. `SCHEMA = 12`, with one line in the schema comment history above it saying what 12 added.

The wire helpers, beside `_question_out`/`_question_in`:

```python
def _counts_out(counts: Counts | None) -> dict | None:
    return None if counts is None else {"outcomes": dict(counts.outcomes), "hangs": counts.hangs}


def _counts_in(data: dict | None) -> Counts | None:
    return None if data is None else Counts(outcomes=dict(data["outcomes"]), hangs=data["hangs"])


def _performance_out(performance: Performance) -> dict:
    return {
        "session": _counts_out(performance.session),
        "task": _counts_out(performance.task),
        "run": _counts_out(performance.run),
        "block": _counts_out(performance.block),
        "task_name": performance.task_name,
        "runs_of_task": performance.runs_of_task,
        "run_in_session": performance.run_in_session,
        "block_in_session": performance.block_in_session,
        "block_type": performance.block_type,
    }


def _performance_in(data: dict) -> Performance:
    return Performance(
        session=_counts_in(data["session"]),
        task=_counts_in(data["task"]),
        run=_counts_in(data["run"]),
        block=_counts_in(data["block"]),
        task_name=data["task_name"],
        runs_of_task=data["runs_of_task"],
        run_in_session=data["run_in_session"],
        block_in_session=data["block_in_session"],
        block_type=data["block_type"],
    )
```

In `_telemetry_out`, add `"performance": _performance_out(t.performance), "returned_at": t.returned_at,`. Use the function's own parameter name. In `_telemetry_from`, add `performance=_performance_in(data["performance"]), returned_at=data["returned_at"],`.

`taskd.py`, a module-level helper near the other private helpers:

```python
def _counts(tally) -> _link.Counts:
    """A tally as the strip's counts, by outcome's wire string as `Telemetry.outcomes`."""
    return _link.Counts(
        outcomes={k.value: v for k, v in tally.outcomes.items()}, hangs=tally.hangs
    )
```

and, beside `Session.task`:

```python
    @property
    def performance(self) -> _link.Performance:
        """The strip's four levels (session-levels spec §5): the session's, and while a
        run goes its task's, its own and its open block's, read from `_levels` and the
        run's tally."""
        levels = self._levels
        session = _counts(levels.session_tally)
        if self.phase != "running" or levels.task is None:
            return _link.Performance(session, None, None, None, None, None, None, None, None)
        open_block = levels.block_tally is not None
        return _link.Performance(
            session=session,
            task=_counts(levels.task_tallies[levels.task]),
            run=_counts(self._tally),
            block=_counts(levels.block_tally) if open_block else None,
            task_name=levels.task,
            runs_of_task=levels.task_runs[levels.task],
            run_in_session=levels.runs,
            block_in_session=levels.blocks if open_block else None,
            block_type=self._scheduler.block.name if open_block else None,
        )
```

Test fixtures:
- `tests/_frames.py`'s `frame()` gains a running session's `performance`:

```python
        performance=Performance(
            session=Counts({"correct": 30, "no_fixation": 10}, 0),
            task=Counts({"correct": 20, "no_fixation": 5}, 0),
            run=Counts({"correct": 12, "no_fixation": 3}, 0),
            block=Counts({"correct": 4, "no_fixation": 1}, 0),
            task_name="fixation_detection",
            runs_of_task=2,
            run_in_session=3,
            block_in_session=27,
            block_type="near",
        ),
        returned_at=None,
```

  It also gets one sentence in the module docstring on schema 12's fields, as earlier schemas have.
- Add the same two fields, with the same values, to `tests/test_cli.py`'s `Telemetry(...)`.
- Add `performance=Performance(Counts({}, 0), None, None, None, None, None, None, None, None)` to `tests/test_link.py`'s `_session_with` namespace.

- [ ] **Step 4: Run the full suite.** `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`. Expected: green. Any test that pinned `SCHEMA == 11` is updated to 12 with a line saying what 12 added.
- [ ] **Step 5: Prove the round trip can fail.** In `_performance_in`, swap `task` and `run`, and see the round-trip test fail. Revert.
- [ ] **Step 6: Commit.** `git commit -am "Publish the session's, task's, run's and block's counts, and the return, in schema 12"`.

---

### Task 6: The strip's two cells

**Files:**
- Modify: `wl_xcon/web.py`:
  - `_strip`;
  - new `_fluid` and `_performance`, which replace `_fluid_today`, `_out_of_cage`, `_correct` and `_last_reward`;
  - a `_lines` helper;
  - a minute-clock helper;
  - the `.strip .lines` CSS, beside `.strip .val` (~1351-1358).
- Modify: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §4.0 and §4.2: one dated note each, pointing at the session-levels spec §6.
- Test: `tests/test_web.py`.

**Interfaces:**
- Consumes (Task 5): `Telemetry.performance`, `Telemetry.returned_at`, and the existing `fluid_today_ml`, `floor_ml`, `shortfall_ml`, `last_reward_at`, `wall_at`, `out_of_cage_seconds`, `out_of_cage_limit_s`, `duration_warning`, `stop_kind`, `phase` and `params`. From `View`: `frame_age_s` and `trials_per_min`.

- [ ] **Step 1: Write the failing tests** in `tests/test_web.py`. Use `fragments`, `frame` and `view` as the file does. All fragments are `parts["strip"]`.

```python
from dataclasses import replace

from wl_xcon.link import Counts, Performance


def _between(phase):
    return replace(
        frame(),
        phase=phase,
        performance=Performance(
            Counts({"correct": 30, "no_fixation": 10}, 0), None, None, None, None, None, None, None, None
        ),
    )


def test_the_strip_has_two_cells():
    assert fragments(frame(), view())["strip"].count('<div class="row">') == 2


def test_correct_trials_shows_the_session_its_task_this_run_and_this_block():
    strip = fragments(frame(), view(trials_per_min=12.0))["strip"]
    assert '30<span class="u"> / 40</span>' in strip and "75%" in strip
    assert "12.0/min" in strip
    assert "fixation_detection" in strip and "2 runs" in strip
    assert "this run" in strip and "run 3" in strip
    assert "block 27 · near" in strip


def test_correct_counts_correct_and_correct_reject_at_every_level():
    """The one rollup (PI, 2026-09-26), on each line."""
    perf = Performance(
        session=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        task=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        run=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        block=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        task_name="t", runs_of_task=1, run_in_session=1, block_in_session=1, block_type="b",
    )
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert strip.count("50%") == 4


def test_hangs_count_among_the_trials():
    perf = replace(frame().performance, session=Counts({"correct": 1}, 1))
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert '1<span class="u"> / 2</span>' in strip and "50%" in strip


def test_between_runs_one_line_says_so():
    """Review Focus 5 and plan ruling 4."""
    strip = fragments(_between("between_runs"), view())["strip"]
    assert "between runs" in strip and "this run" not in strip and "block" not in strip


def test_after_the_runs_one_line_says_no_run_is_going():
    strip = fragments(_between("awaiting_return"), view())["strip"]
    assert "no run going" in strip


def test_before_the_first_trial_the_session_says_so_not_zero():
    perf = Performance(Counts({}, 0), None, None, None, None, None, None, None, None)
    strip = fragments(replace(frame(), performance=perf, phase="between_runs"), view())["strip"]
    assert "no trials yet" in strip


def test_the_supplement_owed_is_on_the_strip():
    strip = fragments(replace(frame(), shortfall_ml=12.5), view())["strip"]
    assert "supplement" in strip and "12.50" in strip and "to reach the floor" in strip


def test_a_met_floor_says_so():
    strip = fragments(replace(frame(), shortfall_ml=0.0), view())["strip"]
    assert "floor met" in strip


def test_an_unknown_day_says_the_supplement_is_unknown():
    strip = fragments(replace(frame(), shortfall_ml=None, fluid_today_ml=None), view())["strip"]
    assert "unknown" in strip and "the day's prior total was not supplied" in strip


def test_back_to_cage_gives_the_deadline_the_time_out_and_the_time_left():
    """5025 s out of an 8 h limit (ruling 5): the deadline is the frame's wall instant
    less the time out plus the limit, as this host shows it."""
    f = replace(frame(), out_of_cage_seconds=5025.0, out_of_cage_limit_s=28_800.0, duration_warning=None)
    strip = fragments(f, view())["strip"]
    deadline = time.strftime("%H:%M", time.localtime(f.wall_at - 5025.0 + 28_800.0))
    assert f"by {deadline}" in strip
    assert f"{_clock(5025.0)} out · {_clock(28_800.0 - 5025.0)} left" in strip


def test_back_to_cage_warns_with_the_sessions_warning_and_is_critical_at_the_limit():
    warned = fragments(replace(frame(), duration_warning="30 min left"), view())["strip"]
    limited = fragments(replace(frame(), stop_kind="limit"), view())["strip"]
    assert 'class="k warn"' in warned and 'class="k crit"' in limited


def test_a_recorded_return_says_when():
    f = replace(frame(), returned_at=1_700_000_000.0, phase="closed")
    strip = fragments(f, view())["strip"]
    assert "at " + time.strftime("%H:%M", time.localtime(1_700_000_000.0)) in strip and "recorded" in strip


def test_a_cage_side_session_has_no_back_to_cage_clock():
    strip = fragments(replace(frame(), out_of_cage_seconds=None, out_of_cage_limit_s=None), view())["strip"]
    assert "cage-side" in strip and "no limit" in strip
```

`_clock` is `from wl_xcon.cli import _clock`, as `web.py` imports it.

Then update the existing strip tests. Rename each to what it now pins, and keep each one's claim:
- `test_with_nothing_scheduled_the_strip_keeps_its_four_cells` becomes `..._keeps_its_two_cells`;
- `test_the_strips_correct_counts_correct_and_correct_reject` is covered by the new rollup test: delete the old one;
- `test_before_the_first_trial_the_strip_says_so_not_zero` is replaced by the new one of that name;
- `test_out_of_cage_time_with_no_published_limit_shows_the_clock_alone` asserts the time out with "no limit published";
- `test_a_cage_side_session_says_it_has_no_out_of_cage_clock_rather_than_zero`;
- `test_the_time_since_the_last_reward_is_the_frames_instant_aged_by_serve` (still `42 s ago`);
- `test_the_out_of_cage_time_is_never_dropped`;
- `test_the_fluid_bar_is_today_over_the_floor`.

- [ ] **Step 2: Run them to see them fail.**
  - Run: `python3 -m pytest -q -p no:cacheprovider tests/test_web.py`
  - Expected: the new tests fail.

- [ ] **Step 3: Implement** in `web.py`. Replace `_fluid_today`, `_out_of_cage`, `_correct` and `_last_reward` with:

```python
def _wall_minute(at: float) -> str:
    """A session instant as this host's `HH:MM`, as `_clock_time` gives `HH:MM:SS`."""
    return _clock_time(at)[:5]


def _lines(rows: list[tuple[str, str, str, str, str]]) -> str:
    """A strip cell's lines: each `(name, value, percent, note, tone)`. `value` is
    HTML built from escaped parts; `tone` is `""`, `"warn"` or `"crit"`."""
    out = []
    for name, value, percent, note, tone in rows:
        hot = f" {tone}" if tone else ""
        out.append(
            f'<span class="k{hot}">{_e(name)}</span><span class="n{hot}">{value}</span>'
            f'<span class="n">{percent}</span><span class="x">{note}</span>'
        )
    return '<div class="lines">' + "".join(out) + "</div>"


def _fluid(frame: Telemetry, view: View) -> str:
    """The strip's first cell (session-levels spec §6): fluid today against the floor
    with its bar, then the supplement, the last reward, and back to cage."""
    floor = f'<span class="u">/ {frame.floor_ml:.2f} mL</span>'
    if frame.fluid_today_ml is None:
        head = f'<span class="nm">unknown</span>{floor}'
        bar = None
    else:
        head = f"{frame.fluid_today_ml:.2f}{floor}"
        tone = "ok" if frame.fluid_today_ml >= frame.floor_ml else ""
        bar = (_pct(frame.fluid_today_ml, frame.floor_ml), tone)
    rows = [_supplement(frame), _reward_line(frame, view), _back_to_cage(frame)]
    return _cell("Fluid today / floor", head, bar=bar, after=_lines(rows))


def _supplement(frame: Telemetry) -> tuple:
    if frame.shortfall_ml is None:
        return ("supplement", '<span class="nm">unknown</span>', "", "the day's prior total was not supplied", "")
    if frame.shortfall_ml <= 0:
        return ("supplement", '<span class="u">none</span>', "", "floor met", "")
    return ("supplement", f'{frame.shortfall_ml:.2f}<span class="u"> mL</span>', "", "to reach the floor", "")


def _reward_line(frame: Telemetry, view: View) -> tuple:
    if frame.last_reward_at is None:
        return ("last reward", '<span class="nm">none yet</span>', "", "", "")
    held = view.frame_age_s or 0.0
    since = frame.wall_at - frame.last_reward_at + held
    age = '<span class="nm">unknown</span>' if not math.isfinite(since) else _e(_health.ago(since) + " ago")
    return ("last reward", age, "", _e(_per_correct(frame)), "")


def _per_correct(frame: Telemetry) -> str:
    """The reward size the run pays a correct trial (plan ruling 6), or "no run going"."""
    if frame.phase != "running":
        return "no run going"
    for row in frame.params:
        if row.name == "reward_correct" and isinstance(row.value, (int, float)):
            return f"{row.value:.2f} {row.unit} per correct"
    return ""


def _back_to_cage(frame: Telemetry) -> tuple:
    out = frame.out_of_cage_seconds
    if out is None:
        return ("back to cage", '<span class="nm">cage-side</span>', "", "no limit", "")
    if frame.returned_at is not None:
        return ("back to cage", _e(f"at {_wall_minute(frame.returned_at)}"), "", _e(f"{_clock(out)} out · recorded"), "")
    limit = frame.out_of_cage_limit_s
    if limit is None:
        return ("back to cage", _e(_clock(out)), "", "out · no limit published", "")
    left = limit - out
    tone = "crit" if frame.stop_kind == "limit" or left <= 0 else "warn" if frame.duration_warning else ""
    when = f"by {_wall_minute(frame.wall_at - out + limit)}"
    note = f"{_clock(out)} out · " + (f"{_clock(left)} left" if left > 0 else "past the limit")
    return ("back to cage", _e(when), "", _e(note), tone)


def _correct_of(counts) -> tuple[int, int]:
    """The strip's one rollup (PI, 2026-09-26): `correct` plus `correct_reject`, over
    every trial at the level, hangs included."""
    correct = counts.outcomes.get(Outcome.CORRECT.value, 0) + counts.outcomes.get(
        Outcome.CORRECT_REJECT.value, 0
    )
    return correct, sum(counts.outcomes.values()) + counts.hangs


def _level(name: str, counts, note: str) -> tuple:
    correct, trials = _correct_of(counts)
    if trials == 0:
        return (name, '<span class="u">—</span>', "", "no trials yet", "")
    return (
        name,
        f'{_e(correct)}<span class="u"> / {_e(trials)}</span>',
        f"{100.0 * correct / trials:.0f}%",
        _e(note),
        "",
    )


def _performance(frame: Telemetry, view: View) -> str:
    """The strip's second cell (session-levels spec §6): session, task, this run, this
    block -- or, while no run goes, one line saying so (plan ruling 4)."""
    perf = frame.performance
    rate = "" if view.trials_per_min is None else f"{view.trials_per_min:.1f}/min"
    rows = [_level("session", perf.session, rate)]
    if perf.run is None:
        said = "between runs" if frame.phase == "between_runs" else "no run going"
        rows.append((said, "", "", "", ""))
    else:
        runs = f"{perf.runs_of_task} run" + ("" if perf.runs_of_task == 1 else "s")
        rows.append(_level(perf.task_name, perf.task, runs))
        rows.append(_level("this run", perf.run, f"run {perf.run_in_session}"))
        if perf.block is None:
            rows.append(("block", '<span class="u">—</span>', "", "", ""))
        else:
            rows.append(_level(f"block {perf.block_in_session} · {perf.block_type}", perf.block, ""))
    return _cell("Correct / trials", "", after=_lines(rows))
```

`_cell` gains an `after: str = ""` keyword appended after the bar and sub. Write this one change exactly:

```python
def _cell(
    label: str,
    value: str,
    *,
    sub: str = "",
    bar: tuple[float, str] | None = None,
    after: str = "",
) -> str:
    ...  # unchanged, then before the return:
    if after:
        parts.append(after)
```

`_strip` becomes:

```python
def _strip(frame: Telemetry | None, view: View) -> str:
    if frame is None:
        return _cell("Fluid today / floor", _NONE) + _cell("Correct / trials", _NONE)
    return (
        _fluid(frame, view)
        + _performance(frame, view)
        + (
            _scheduled(frame, view)
            if frame.scheduled_stop is not None and frame.stop_kind is None
            else ""
        )
    )
```

Keep the existing comment on the scheduled cell's guard.

CSS, after `.strip .bar { height: 4px; }`:

```css
.strip .lines { display: grid; grid-template-columns: auto auto auto 1fr; gap: 1px 10px; font-size: 12.5px; align-items: baseline; }
.strip .lines .k { color: var(--muted); white-space: nowrap; }
.strip .lines .n { font-family: var(--mono); font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.strip .lines .n .u { color: var(--muted); }
.strip .lines .x { color: var(--muted); font-size: 11.5px; white-space: nowrap; }
.strip .lines .warn { color: var(--warn); font-weight: 600; }
.strip .lines .crit { color: var(--crit); font-weight: 600; }
```

`_e`, `_NONE`, `_health`, `_clock` and `Outcome` are already imported or defined in `web.py`. Delete the four replaced functions only once no caller remains: grep `_out_of_cage(`, `_correct(`, `_last_reward(` and `_fluid_today(`.

P4d-2b spec: under §4.0's strip ruling and §4.2's "Strip: four cells", add:

```text
  *(Amended 2026-10-01 by the session-levels spec §6: two cells, the fluid box with the
  supplement, the last reward and back to cage, and Correct / trials at the session,
  task, run and block; the supplement returns to the strip.)*
```

- [ ] **Step 4: Run the full suite.** `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`. Expected: green.
- [ ] **Step 5: Render it and look.** Start `wlx serve` against a simulated `wlx taskd` session, the way `docs/CHECKPOINT.md`'s b3a-2 entry describes the demo. Open the page in a headless browser with `<meta charset="utf-8">` intact, and screenshot the strip:
  - while running;
  - between runs;
  - after the end.

  Compare with mockup v13's two cells, and save the screenshots in the task's report folder. Fix any line that differs from the mockup in words or order.
- [ ] **Step 6: Prove two of them can fail.** Make `_back_to_cage` ignore `returned_at`, and see `test_a_recorded_return_says_when` fail. Make `_performance` always print "between runs" when `perf.run is None`, and see `test_after_the_runs_one_line_says_no_run_is_going` fail. Revert both.
- [ ] **Step 7: Commit.** `git commit -am "Draw the strip as two cells: fluid and its welfare lines, and correct at four levels"`.

---

### Task 7: Proof, and the record of it

**Files:**
- No product code. A report under the plan's workspace.

- [ ] **Step 1: Run the full suite three times in a row.** `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`, run three times. Record each count and time.
- [ ] **Step 2: Sweep every new and changed function.** Use parallel lanes in separate `git archive` copies of the tree, as `docs/CHECKPOINT.md`'s CI row describes:

```bash
python3 tools/mutate.py --all --returns None wl_xcon/levels.py
python3 tools/mutate.py --all --only words_for_block wl_xcon/encode.py
python3 tools/mutate.py --all --only trial --returns None wl_xcon/record.py
python3 tools/mutate.py --all --only run_session wl_xcon/simulate.py
python3 tools/mutate.py --all --only run,performance,_counts wl_xcon/taskd.py
python3 tools/mutate.py --all --only of,_counts_out,_counts_in,_performance_out,_performance_in,_telemetry_out,_telemetry_from wl_xcon/link.py
python3 tools/mutate.py --all --only _cell,_strip,_wall_minute,_lines,_fluid,_supplement,_reward_line,_per_correct,_back_to_cage,_correct_of,_level,_performance wl_xcon/web.py
```

  Use each module's `--returns` value as `tools/mutation_gate.py` lists it. Read each line:
  - every target must be `caught` with `N failed`;
  - a survivor gets a test that kills it, then a re-sweep of that function;
  - a `timed out` is run again locally with no limit and recorded;
  - `N errors in` with no failures is not a catch: fix the harness input, or report it.
- [ ] **Step 3: Write the report** with:
  - the three suite counts;
  - every sweep line;
  - every survivor and its fix;
  - the screenshots from Task 6;
  - the line count of `git diff main -- wl_xcon/`.
