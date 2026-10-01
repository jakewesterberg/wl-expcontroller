# Session Levels — Runs, Blocks, Ten Position Numbers, and the Console's Strip

- **Status:** designed in conversation on 2026-10-01 with the PI, who answered each section's
  questions in the UI (quoted below). He saw it drawn in the mockup
  `docs/superpowers/mockups/2026-10-01-console-mockup-v13.html` and asked for this spec to be
  written and for wl-preproc and wl-works to be told the same day. He approved it the same day,
  with one change: the strip's block line shows the session's block number (§6).
- **Date:** 2026-10-01
- **Parents:**
  - the P4d-2b browser console spec (`2026-09-26-P4d2b-browser-console-design.md`): §4.0, the
    strip's rulings, which this amends, and §4.2;
  - S2, the event vocabulary;
  - the XC-155 spec (`2026-09-30-xc155-trial-markers-design.md`), the session's trial number;
  - b3a-1, runs.
- **Related:**
  - XC-150, the day's plan, which brings real block plans;
  - XC-026, carrying numbers across a crash (the PI: before January);
  - XC-198, closed by wl-preproc's answers of 2026-10-01.
- **Facts read** on 2026-10-01:
  - wl-preproc `main` `0458b10`: `wl_preproc/contracts/events.py`, the frozen codec;
  - wl-works `7be0c6a5`: `docs/superpowers/specs/2026-08-09-glossary-design.md` §1, and the
    January canonical-NWB spec.

## 1. Why

The PI asked for the strip's *Correct / trials* to show performance over the whole session,
over the current task and over the current block. He also asked to settle what the data's
divisions are: "a session that can be multiple tasks, each task can be run multiple times, and
tasks can have a block structure where a set of trials has a specific set of conditions.
trials are the individual instances."

Three things made that more than a display change:

- **"Block" meant two different things across the lab's repositories.**
  - wl-works' glossary review of 2026-08-09, from the PI's own rulings, defines
    `block` as "one run of one task, with its discrete set of output files"
    (`animal_session_block`). wl-works' January canonical-NWB spec and wl-preproc's
    `spec/runs-and-trials` (`43543ad`) built on that sense: wl-preproc asked wl-xcon that
    morning to send `BLOCK_START` once per run.
  - wl-xcon's code, MonkeyLogic, and the PI today use "block" for a set of trials under one set
    of conditions, inside a run.
  - The NWB format has one block level.
- **The live page and the mockup disagreed.**
  - The P4d-2b spec §4.0 says the strip shows correct / trials "for the session", and the v12
    mockup does.
  - The live page (`web._correct`) counts the frame's `outcomes` and `trial_index`, both reset
    at each run's start. So it has shown only the current run's numbers since b3a-1 made
    sessions hold several runs.
  - That is a defect, and this change fixes it.
- **Block numbers need a rule.** Block types recur ("Bt1 to Bt2 to Bt1 to Bt2 is Block 1 to
  Block 2 to Block 3 to Block 4"), and their numbers continue across runs.

## 2. The vocabulary (decided)

The PI, 2026-10-01: block means a set of conditions ("1, but it is important that blocks are
temporal instances").

| Word | Meaning |
|---|---|
| **Session** | One animal's visit to the rig, cage to cage. One folder, one sync-box recording (wl-preproc's answer to XC-198's question, 2026-10-01: one recording per animal). |
| **Task** | A task program, named by its file, e.g. `fixation_detection`. Two runs of the same file are the same task, whatever its version. |
| **Run** | One start-to-stop of one task within a session. A task may be run more than once. wl-xcon's runs, as in `runs.jsonl` and `RUN_START`/`RUN_END`. |
| **Block type** | A named set of conditions, e.g. Bt1. In code, a `scheduler.Block`. |
| **Block** | One stretch of consecutive trials under one block type, inside one run. Block types recur, and each occurrence is a new block. |
| **Condition** | One set of parameter values a trial runs under. A block type holds one or more. |
| **Trial** | One instance. |

- **A run ending mid-block closes that block.** The next run of the task starts a new block,
  even if it carries on with the same block type. A block lies inside one run.
- **wl-works' glossary row of 2026-08-09 is superseded.** What it called a block is a run.
  wl-works was told on 2026-10-01 (§8).

## 3. Ten position numbers (decided)

The PI, 2026-10-01: "Perhaps we should have a few levels of numbers to cover all bases… that
way we cover both the analysis-level useful numbers and the more metadata-y numbers". He chose
to include the run levels ("Yes, all of them") and to number tasks by first appearance
("Distinct task order").

**Every line of `xcon/trials.jsonl` carries all ten, each counting from 1:**

| Field | Counts | Resets |
|---|---|---|
| `trial_number` | trials in the session (XC-155, already built) | never in a session |
| `trial_in_task` | this task's trials in the session, across its runs | never; per task |
| `trial_in_run` | trials in this run | at each run's start |
| `trial_in_block` | trials in this block | at each block's start |
| `block_in_session` | blocks in the session, any task | never in a session |
| `block_in_task` | this task's blocks in the session, across its runs | never; per task |
| `block_in_run` | blocks in this run | at each run's start |
| `run_in_session` | runs in the session | never in a session |
| `run_in_task` | this task's runs in the session | never; per task |
| `task_in_session` | distinct tasks, in their order of first appearance | never; a task keeps its number |

Worked example: a session runs calibration, fixation, detection, then fixation again. For a
trial late in the second fixation run, the line could read `trial_number` 512, `trial_in_task`
400, `trial_in_run` 58, `trial_in_block` 18, `block_in_session` 27, `block_in_task` 21,
`block_in_run` 3, `run_in_session` 4, `run_in_task` 2, `task_in_session` 2.

- **What stays.** `block` keeps naming the block type, and `condition` the condition. `index`
  (0-based trial in run) and `run` (0-based run in session) stay unchanged, so a record written
  before this change reads as it does now, and wl-preproc's reader of old records is not moved.
- **Counted in `taskd.Session`**, at the trial boundary, beside `_trial_number` and
  `_sequence`, the session's counters that a run's reset leaves alone (b3a-1 plan, decision 2).
  - The per-task counters are keyed by the task's name as the run records it.
  - `task_in_session` comes from the order in which names first appear.
- **A trial that faults keeps its numbers**, as `trial_number` does (XC-155). They are taken as
  the trial starts, and no later trial reuses them. A block that a fault ends is still a block.
- **`runs.jsonl`'s start row** gains `run_in_session`, `run_in_task` and `task_in_session`, so
  a run is placed without reading its trials.
- **Crash and restart** start every counter again with the new session. Carrying them forward
  is XC-026, which the PI placed before January; it is not in this change.

## 4. The recording (decided; sent to wl-preproc 2026-10-01)

- **At each block's start**, before its first `TRIAL_START`, wl-preproc's `BLOCK_START` escape
  (`0x8002`) with its two payload words, as `contracts/events.py` defines them:
  - word 1: **`block_in_session`**. It is unique in the recording even while every task code is
    0, which `block_in_task` would not be.
  - word 2: the task's `TaskTypeCode`, or **0** until wl-xtasks allocates codes.
- **`BLOCK_END` (marker 3)** when a block ends:
  - after its last `TRIAL_END`, when its block type is done;
  - and when its run ends by design (completed, stopped, limit). The order is `BLOCK_END`, then
    `RUN_END`.
  - A run that faults sends neither, as for `RUN_END` today. wl-preproc then closes the block
    at the next run's start (its answer of 2026-10-01).
- **The order within a run:** `RUN_START`, then for each block: `BLOCK_START` + payload, the
  block's trials framed as XC-155 frames them, `BLOCK_END`. Then `RUN_END`.
- **Emitted at the boundary, never in a frame**, by `Session.run` beside the trial markers
  (XC-155 §2.1). The escape's words are computed before anything is strobed, and are sent
  unbroken. `codes.py` mirrors `BLOCK_END`, and `encode.py` mirrors `BLOCK_START`, each pinned
  by a test against wl-preproc's enums.
- **Runs stay bare `RUN_START`/`RUN_END`.** If wl-preproc wants a run's number in the recording,
  its escape is wl-preproc's to allocate (ADR-0007: decodability is theirs), and wl-xcon sends
  it once allocated. That is not in this change.
- **Until block plans exist (XC-150),** `_plan` gives every run one block, so each run has
  exactly one `BLOCK_START`/`BLOCK_END` pair.

## 5. The live feed (`Telemetry`, schema 11 → 12)

A frame carries the four levels the strip shows, each read from the session's own counts and
never recomputed by a console (the `Telemetry` docstring's rule):

- **Session, task, run and block tallies**: the outcome counts for each, so the strip's rollup
  (correct plus correct rejection, P4d-2b §4.0) is applied on the page as today.
- The current block's `block_in_session` and block type, and the current task's name and
  `run_in_task`.
- **Between runs**, the session tally stays. The run, task and block tallies are `None`, and
  the strip says "between runs".
- `outcomes` and `trial_index`, the run's, stay as they are for every other reader: the
  *Working?* pane, `/health`, and the terminal console.
- **`returned_at`**: `welfare.returned_wall_at`, the recorded return on the session's anchored
  clock, or `None` before it. It is read, as every welfare figure on the frame is, so the
  strip can say when the animal went back.

## 6. The console's strip (decided; drawn in mockup v13)

The PI, 2026-10-01: combine the fluid and last-reward boxes, add the required supplement, put
back-to-cage last in that box ("2", dropping the separate out-of-cage box), and order the
performance lines session, task, run, block ("task is the higher level, so it should be just
below session"). **This amends P4d-2b §4.0**:
- the strip goes from four cells to two;
- the supplement returns to the strip, which §4.0 had moved to the end-of-session summary.

**Cell 1, Fluid today / floor**: the value and its bar as today, then three lines:
- **supplement**: `shortfall_ml` mL "to reach the floor", "none · floor met" at zero, or
  "unknown" when the day's prior total was not supplied. These are the frame's own numbers, as
  the terminal console already shows them.
- **last reward**: the time since it, then the reward per correct while a run goes, or "no run
  going".
  - The mockup turns the cell amber when the animal stalls. The live page has never had a stall
    signal; that is one of XC-021's accepted console items, not built here.
- **back to cage**: "by HH:MM", then "N out · M left":
  - the deadline is the departure plus the limit, both the frame's;
  - amber within the duration warning; red at the limit;
  - "at HH:MM · recorded" once the return is recorded;
  - "cage-side · no limit" for a cage-side session, as the out-of-cage cell says today.

**Cell 2, Correct / trials**: four lines, each "correct / trials", a percentage, and a note:
- **session**, with trials per minute (derived by `wlx serve`, as today);
- **the task's name**, across its runs, noting how many runs;
- **this run**, noting its number;
- **block N · type**: the current block's `block_in_session` and its block type.

Between runs, one line reading "between runs" stands in for the task, run and block lines.

**The scheduled-stop cell** appears beside them while a stop is scheduled, as today.

- **The block line shows `block_in_session`** (the PI, 2026-10-01, reviewing this spec).
  That is the number the recording's `BLOCK_START` carries, so the strip and the recording
  name a block alike. This spec's draft had proposed `block_in_task`.
- **The limit is 8 hours.** The PI, 2026-10-01: the institution's out-of-cage limit is 8
  hours, and the 12 recorded since 2026-09-19 was wrong. The mockup shows 8. The repository's
  documents and the reference bounds config are corrected on their own branch,
  `fix-out-of-cage-8h`, whose welfare-code lines go to the PI before it merges.

## 7. Not in the welfare-critical surface

No function on `docs/design/architecture.md`'s welfare-critical list changes:
- the counters and markers are `Session.run`'s boundary bookkeeping;
- the strip only displays welfare numbers the frame already carries.

The list is not widened (the PI, 2026-09-30).

## 8. Told to other repositories (2026-10-01)

- **wl-preproc** (its session, the same day):
  - the vocabulary;
  - §4's markers, its answer to the morning's ask 1;
  - the ten field names, as proposed, to be confirmed when this spec is approved;
  - XC-026 before January;
  - XC-198 closed by its answers.

  Reading `trial_number` and the new fields is wl-preproc's to build.
- **wl-works** (its session, the same day):
  - its glossary's block row is superseded, and `animal_session_block` would be a run table
    (not yet built there);
  - the ten numbers;
  - the 8-hour limit.

## 9. Testing (sim first)

- **The path, through wl-preproc's own code.** A `wlx taskd` session on the simulated card runs
  the sequence below, and its words are decoded and assembled by wl-preproc's `decode_stream`
  and `assemble`:
  - task A with a block plan that recurs (types X, Y, X);
  - task B;
  - task A again, stopped mid-block.

  The test expects:
  - one assembled block per block, numbered by `block_in_session`;
  - each trial inside its block;
  - every line's ten numbers equal to the values worked out by hand for that sequence;
  - the stopped block closed by `BLOCK_END`.
- **A faulting run** sends no `BLOCK_END` or `RUN_END`. The next run's first block still takes
  the next `block_in_session`.
- **The feed:** the four tallies at a trial boundary, between runs, and across runs of the same
  task.
- **The page:** `web.py`'s two cells, with each line in its states. That covers supplement
  unknown, owed and met; a stalled animal; back-to-cage warned, at the limit, recorded and
  cage-side; and between runs.
- **Exact code lists** in existing tests are re-read and extended, not loosened (as in
  XC-155 §4).
- `tools/mutate.py` over every new and changed function.

## 10. Out of scope

- Real block plans: the day's plan, XC-150. Until then a run is one block.
- Carrying numbers across a crash: XC-026, before January, its own change.
- A run-number escape: wl-preproc's to allocate.
- Task type codes: wl-xtasks' to allocate.
- The 8-hour correction, on its own branch (§6).
