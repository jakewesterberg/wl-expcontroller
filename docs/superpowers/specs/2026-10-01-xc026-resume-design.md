# XC-026 — Resume a Session After a Crash

- **Status:** designed in conversation on 2026-10-01. The PI answered each question in the UI
  (quoted below) and approved the design's sections ("Yes, continue", "Yes, write the spec"). The
  spec itself awaits his review.
- **Date:** 2026-10-01
- **Closes:** XC-026 and XC-201.
- **Parents:**
  - S8 §6 (restart and resume: "The session **continues**; block and trial indices carry forward
    from the record"), §5.2 and §5.2c;
  - the P4d-2b spec §6.1 ("Nothing is quietly lost to a crash") and its b3a-1 stranded-session
    rules;
  - the session-levels spec (`2026-10-01-session-levels-and-strip-design.md`): the ten position
    numbers, the block and run markers.
- **Asked for by** wl-preproc (2026-10-01). Without this, a crash and restart starts trial numbers
  again at 1 inside one sync-box recording. The PI placed it before January.

## 1. Why

A crashed `wlx taskd` leaves its session **stranded**: a departure in `welfare_notes.jsonl`
with no return after it (`stranded.find`). Today (b3a-1) the restarted service refuses every new
session until someone records that animal's return. The page offers only *end session…*.

So an animal still on the rig after a crash can only be worked on by:
1. recording a return that has not happened;
2. then opening a new session, whose numbers restart at 1 in the same sync-box recording, where
   wl-preproc keeps the first of each repeated number.

S8 §6 decided the other way in August: the session continues. It was never built.

## 2. Decided

- **Both, resume and end** (the PI, 2026-10-01: "Resume or end"). The stranded banner offers
  *resume session* beside *end session…*. End records the return, as today.
- **The departure is taken from the record, without asking** (the PI: "Take it silently").
  `welfare_notes.jsonl` holds it already. That replaces S8 §6's 2026-09-20 note that a person
  re-supplies it, which predates the notes file.
- **The fluid so far is written per trial** (the PI: "Written per trial"). The resume adds it
  up. §4 has the details.

## 3. What a resume does

A resume reopens **the same session**: its id, its folder, its record files, appended to. It
comes back **between runs** (`phase` `between_runs`), ready for the next run. *(2026-10-01, the
PI, answering the final review's I1: "Bring it back waiting". A session whose runs were ended
with End session before its process stopped (its `end` row in `controls.jsonl`, its head
released, its return not yet given) comes back **waiting for its return** (`awaiting_return`)
instead. No run starts, a hand reward can still be given, its head is not marked fixed again,
and the return closes it through the usual path, with the usual summary: its fluid and its
supplement shown.)* It restores:

| What | From |
|---|---|
| Subject, deployment, view and setup | `config.json`, with the animal's bounds and settings files loaded as at open. If the loaded bounds' ceilings or floor differ from what `config.json` recorded, it is refused: a session's limits do not change silently across a crash. |
| The welfare-bounded values it last ran with (a reward size set during the session) | The last run's `runs.jsonl` start row (`bounded`), then later `parameter_changes.jsonl` rows. A value set in one run carries into the next (the PI's Question 1, b3a-1). The out-of-cage limit is in no start row, so its latest change, in any run, is carried (2026-10-01, the final review's I2). |
| The departure (the out-of-cage clock) | `welfare_notes.jsonl` (`Welfare.restore_departure`, as `stranded.restore` uses it) |
| The fluid so far, and the day's earlier fluid | The new rows in §4 |
| Every position number: trial, block, run and task, and the session's and each task's tallies | `trials.jsonl` and `runs.jsonl` (`levels.Levels`, rebuilt) |

- **The interrupted run stays as it ended**: faulted, with no `RUN_END`. It has a start row and
  no end row, or an end row with `stop_kind` `fault`. The next run's number is the last run's
  plus one. Block and trial numbers carry on, so **one recording never repeats a number**.
  *(2026-10-01, the final review's M3: across a process crash, not a power loss. The rows a
  resume numbers from, `trial_starts.jsonl` and `runs.jsonl`'s start rows, are flushed to the
  operating system before their strobes and never `fsync`ed, so a host that loses power can
  lose rows whose numbers the recording already holds, and a resume would issue them again.
  Whether to `fsync` them waits on a measurement, XC-210. And the next run's number is the
  largest recorded plus one, as the start rows recorded it: the final review's I3 found a run
  that failed before its start row, which a count of the rows would have repeated.)*
- **Not restored: restraint.** Its marks are event codes on the recording, not rows. The PI ruled
  that head-fixation bounds nothing (2026-09-19, and "only cage to cage time matters",
  2026-09-26). After a resume, `chair_seconds` is `None` ("not measured"), never a guess.
- **The in-session clock** restarts at the resume and says so. It bounds nothing, so no ruling
  depends on it.
- **The restart is marked:**
  - in the record, a `resumed` row in `welfare_notes.jsonl` with who, when, and the crash's last
    recorded instant;
  - in the recording, the new provisional allocation code **4137 `SESSION_RESUMED`**, beside
    4135/4136 in `tasks/allocation.py` (wl-xtasks owns the final numbering, as for those two),
    strobed once at the resume;
  - on the console, a banner while the resumed session runs, and in the end-of-session summary
    ("resumed after a crash at HH:MM").
- **Several crashes:** a resumed session that crashes is stranded again and can be resumed again.

## 4. The fluid record (welfare-critical)

Today `Welfare.commanded`, the delivered line and the day's earlier fluid live only in memory.
From this change on:

1. **Each trial's line in `trials.jsonl` carries `fluid_ml`**: the fluid commanded during that
   trial, `welfare.commanded` after the trial less before it. It is written with the line, at
   the trial's end, never mid-trial (hot-path rule).
2. **Each hand reward's row in `controls.jsonl` carries `ml`**, the amount commanded.
3. **`config.json` records `already_delivered_today`**: the day's earlier fluid given at open,
   or `null` when unknown.

On resume:
- the session's fluid so far is the sum of (1) and (2);
- the day's total adds (3), or stays unknown when (3) is `null`, exactly as at open.

- **A crash mid-trial** can miss only that trial's reward from the sum. That makes the shortfall,
  and so the supplement, come out larger, never smaller. *(Not the whole of it: §8a's
  correction of 2026-10-01 adds every trial that faulted.)*
- **The pump's delivered line** is reconciled from the resume on. The restored part counts as
  commanded (`reconcile_report` says so).
- **A record written before this change** has no `fluid_ml`, no hand-reward `ml` and no
  `already_delivered_today`. It **cannot be resumed**: the page offers only *end*, saying why.
  Its fluid so far cannot be known, and it is never taken as zero.

## 5. The page, the command and its refusals

- **The command.** A new link command, `ResumeSession(by, session_id)`, decoded and refused like
  every command (`link._decode_command`). Through `wlx serve` it arrives from the page's
  *resume session* button on the stranded banner, under the person's name.
- **`Service._resume`** (new, welfare-critical) builds the session as §3 says and publishes it.
  It **refuses**, with a refusal row saying why, when:
  - a session is already open;
  - the stranded record cannot be read (it fails closed, as `stranded.find` does today), or its
    `config.json` names another session than its folder (2026-10-01, the final review's M5);
  - the record predates §4 (above);
  - the animal is already past its out-of-cage limit, on the restored departure and the limit
    the session last had (2026-10-01, the final review's I2: never its file's, when the session
    lowered it). The page then asks for the return, and only *end* is offered; *(2026-10-01, Task 7's review: "then" is
    after the refused resume. The service marks that stranded session not resumable, with the
    refusal's sentence as its reason, so its banner no longer offers resume; past the limit only
    ever stays true. The changed-bounds refusal below leaves it resumable.)*
  - the bounds loaded differ from `config.json`'s (§3).
- **A session ended before its crash is resumed waiting for its return** (2026-10-01, the PI:
  "Bring it back waiting"; §3). It is not refused: *start run* is refused for it, as for any
  session awaiting its return, and *end session…* takes the return.
- **"No new session while an animal is stranded" still holds** (P4d-2b §6.1). A resume is not a
  new session. With two stranded sessions, each is resumed or ended on its own.
- **`wlx run`** refuses a `--session-id` whose folder already exists (closes XC-201). The refusal
  names the folder and says a stranded session is resumed or ended from the page (`wlx taskd`).
  The terminal does not resume.

## 6. Told to wl-preproc once built

- Numbers no longer restart after a crash: the resumed session's next `RUN_START` (escape
  `0x8006`) carries the next run number, and every block and trial number continues.
- **4137 `SESSION_RESUMED`** marks the resume. wl-preproc's rule already bounds the crashed run
  at the next run's start.
- **A resumed rig-fixed (`RIG_FIXED`) session strobes another `HEAD_FIXED` (4128) at the
  resume, with no `HEAD_RELEASED` (4129) between, unless its runs were ended before the crash**
  (added 2026-10-01; §8a item 2, pinned by the plan's path test; corrected 2026-10-01 for the
  PI's ruling in §3). A resume marks the head fixed again because a run needs it, and nothing
  recorded whether it was released across the crash. A session ended before the crash had its
  4129 strobed by End session, and it comes back waiting for its return with no run to start,
  so its resume strobes no 4128. So one recording holds one or more 4128 and at most one 4129,
  after the last 4128: at the session's end, or before the 4137 of a resume that brings it back
  waiting. The session's own restraint time counts from the latest 4128. Restraint bounds
  nothing.

## 7. Testing (sim first)

- **The path.** A simulated `wlx taskd` session (`Service` over a temporary root):
  1. runs a run with a block plan and some rewards, a hand reward, and a parameter change;
  2. is killed mid-trial: the service object is dropped without `end` or a return;
  3. a new `Service` on the same root finds it stranded, resumes it, and runs another run.

  The test checks that:
  - every line's ten numbers continue (spec §3 of session-levels);
  - the run numbers in the stream (`0x8006`) are 1, then 2;
  - `SESSION_RESUMED` is in the stream;
  - wl-preproc's `decode_stream` and `assemble` find no repeated trial, block or run number;
  - the out-of-cage clock reads from the original departure;
  - `session_total` equals the fluid given before the crash, less at most the crashed trial's;
  - the reward size set in the first run is the one the resumed run starts with;
  - `welfare_notes.jsonl` has the `resumed` row.
- **The refusals**, each by test:
  - an open session;
  - an unreadable record;
  - a pre-change record;
  - a session past its limit;
  - changed bounds;
  - `wlx run` given an existing folder.
- **The fluid rows**: `fluid_ml` on a rewarded and an unrewarded trial, the hand reward's `ml`,
  and `already_delivered_today`, known and unknown.
- `tools/mutate.py` over every new and changed function.

## 8. Human review before merge

The PI reviews, as a numbered summary:
- `Service._resume` and its refusals;
- the welfare restore (departure, fluid so far, day's total);
- the `fluid_ml` and hand-reward `ml` writes;
- `already_delivered_today` in `config.json`;
- any change inside a function already on `docs/design/architecture.md`'s welfare list (`_manual_reward` among them).

This spec does not widen the list (the PI, 2026-09-30). `Service._resume` restores the
out-of-cage clock and the fluid, so whether it joins the list is a question in his review
summary, his to answer.

## 8a. Corrections found while planning (2026-10-01)

A read of the code for the plan found five things this spec had not settled. Each is decided here;
none changes what the PI chose.

1. **A trial that dies mid-trial has strobed its number and has no `trials.jsonl` line**, since
   the line is written as the trial ends. Rebuilding from lines alone would issue that trial's
   number, and its block's if it opened one, a second time in the same recording. So **each
   trial's position is also written as it starts**, at the boundary before `TRIAL_START` and never
   in a frame, as a row of a new `trial_starts.jsonl`. The rebuild takes every number from those
   rows.
2. **A head-fixed (`RIG_FIXED`) session cannot start a run without a head-fixed mark**
   (`Welfare.preflight`). A resume of one therefore **marks the head fixed again at the resume**
   and strobes `HEAD_FIXED`, unless its runs were ended before the crash and it comes back
   waiting for its return, with no run to start (§3's 2026-10-01 note); its restraint time
   counts from the resume, an undercount. Restraint
   bounds nothing (the PI, 2026-09-19 and 2026-09-26). §3's "`chair_seconds` is `None`" stands for
   a chaired session only.
3. **More session state is restored:**
   - the parameter-change sequence number, `_sequence`, from `parameter_changes.jsonl`'s largest
     `sequence`, so its join numbers never repeat;
   - the last reward's instant (`welfare.last_delivery_wall_at`): each trial's line also carries
     `last_reward_at` (the instant of its last reward, or `null`), and the hand-reward rows carry
     `at` already. Otherwise the strip would read "no reward yet" after a resume.
4. **The page must know which stranded sessions can be resumed.** `link.Stranded` gains
   `resumable: bool` and `why: str` (empty when resumable), set by `stranded.find`.
   Telemetry gains `resumed_at` (the resume's instant, or `None`) for the console's banner and the
   end-of-session line. Schema 12 → 13.
5. **The command's wire kind is `resume_session`**, since `resume` is already the pause's resume.

Also, the pump's delivered line is not reconciled anywhere in production today
(`Welfare.reconcile` is called only by tests), so §4's sentence on it describes nothing to carry.
The hand-reward row already carries `ml` (§4 item 2). Only its reading on resume is new.

**Corrected 2026-10-01, while writing the plan's path test: §4's "a crash mid-trial can miss
only that trial's reward" is not the whole of it.** A `wlx taskd` session survives a trial that
faults: `Service._run` contains the fault, and the session goes on between runs. That trial's
commanded fluid is in the process's total but has no line, since a line is written only as a
trial ends. So a later resume undercounts **every faulted trial in the session**, not only the
trial the crash cut short. It is still an undercount, so the shortfall, and the supplement,
come out larger, never smaller.

## 9. Out of scope

- Resuming from the terminal (`wlx run`).
- Reconstructing restraint time.
- A session id from wl-sync (XC-088).
- The final numbering of 4137 (wl-xtasks).
