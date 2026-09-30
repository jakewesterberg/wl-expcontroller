# XC-155 — Trial Markers and the Session's Trial Number

- **Status:** designed in conversation on 2026-09-30 and approved there by the PI ("Looks right, write it up"). He also chose to leave `CONDITION` for later ("Wait until conditions exist").
- **Date:** 2026-09-30
- **Closes:** XC-155. **Unblocks:** XC-173.
- **Parent:** S2 (the event vocabulary: `2026-08-31-S2-event-vocabulary-design.md` §3, §4, §6); P4d-2b spec §6.3 (runs and `RUN_START`/`RUN_END`); wl-preproc's ask in its `docs/pending-wl-xcon-amendments.md`.
- **Facts:** read from wl-preproc's source on 2026-09-30, at `main` `da95dd9` (its working tree `spec/nwb-probes` `3079136` is code-identical). The research notes and a probe that runs wl-preproc's real decoder on streams built by wl-xcon's encoder were kept in the session's scratchpad (git-ignored). The citations below are wl-preproc's paths.

## 1. Why

wl-preproc turns a session's neural recording into trials from the event stream alone. It joins each trial to wl-xcon's `trials.jsonl` by the trial's number, and takes the trial's condition name and settings from that line. Today a real session gives it **no usable trials**, for two reasons:

- **The stream has no trial structure.** wl-preproc opens a trial at `TRIAL_START` (32), names it by the `TRIAL_NUMBER` escape (`0x8001`, a uint32 in four words) that follows, and closes it at `TRIAL_END` (33) (`events/assemble.py:94-124`). wl-xcon emits none of the three. The first word of a trial today is the task's own start-state mark, if the task has one. Probed with wl-preproc's `assemble`:
  - a stream of `TRIAL_NUMBER`s with no `TRIAL_START` collapses into one trial carrying the last number;
  - a `TRIAL_NUMBER` before `TRIAL_START` becomes an empty trial and drops the real one;
  - without `TRIAL_END` each trial's end is inferred, not recorded.
- **The record cannot be joined.** Since b3a-1 every `trials.jsonl` line names its `run`, and a run's `index` restarts at 0. wl-preproc therefore joins no line of a record whose lines name a run (`events/rigtrials.py:75-81`), until it is told the field that carries a number unique within the session. Its ask, quoted from `docs/pending-wl-xcon-amendments.md`: "**This repository needs one thing back: the name of that field**".

XC-155's own wording ("it identifies a trial by the stream's `TRIAL_NUMBER` alone") missed the first reason. `TRIAL_NUMBER` names a trial; `TRIAL_START` makes one.

## 2. What is decided

### 2.1 What each trial sends to the recording

At the trial boundary, before the trial's first frame:

```
TRIAL_START (32)
TRIAL_NUMBER escape: 0x8001, high word, low word, XOR checksum   (4 words, unbroken)
```

Then the trial runs as today: the task's own marks, `OPERATOR_MARK`, and so on. Then, at the trial's end, after the outcome marker (34-38) that is strobed today:

```
TRIAL_END (33)
```

- **At the boundary, never in a frame.** Both sequences are emitted from `Session.run` between trials, where the loop already allocates and writes files (S1 §4's "between-trial surface"; `record.py`'s inter-trial writes). `run_trial`'s frames gain no work. The escape's four words come from `encode.words_for`, which already exists, is framed exactly as wl-preproc's `encode_payload` (a test pins it), and is called by nothing today.
- **Unbroken** (S2 §6 item 3): no other word is strobed between the escape and its checksum on any path, since wl-preproc reads the payload by position and a word in between fails the checksum and loses the trial. The four words go out consecutively on the loop's one thread before the trial's first frame, where no other code is emitted.
- **A trial that faults** strobes no `TRIAL_END`: the card may be what failed. wl-preproc then infers the trial's end (`schema/events.py::_trial_stop_time`), as it does for any trial without one.
- **Both `wlx run` and `wlx taskd`** emit them, since both go through `Session.run`. The census (`simulate`) and any path with no card emit nothing new.
- `codes.py` mirrors `TRIAL_START` 32 and `TRIAL_END` 33 beside the outcome markers 34-38 it already mirrors. They are wl-preproc's frozen framework codes; wl-xcon allocates nothing (ADR-0007).
- **Not in the welfare-critical surface.** `Session.run`'s boundary is not a listed function, and the markers go through `card.emit` as `RUN_START` and `RUN_END` do, not through `welfare.Rig.mark`.

### 2.2 The trial number

- **It counts from 1, across the whole session**: the first trial of the session's first run is 1, and each trial after it adds 1, whichever run it is in. It is held in `Session` beside `_sequence` (the parameter-change sequence), which a run's reset leaves alone (b3a-1 plan, decision 2).
- **It is recorded on the trial's line in `trials.jsonl` as `trial_number`**, equal to the number strobed for that trial. That is the field wl-preproc joins on, and its name is what it asked for. `index` (per run) and `run` stay on every line, unchanged.
- **Unique within one wl-xcon session.** A new session starts again at 1, because it is another session: another id, another folder, another animal's record. See §3's first question for when that is not enough.
- **Crash and restart.** A service restarted after a crash opens a new session; the stranded one is closed from its record (b3a-1). Carrying the numbering of a session across a restart is S8 §6's continuation, XC-026, not built.
- **The ceiling.** The escape carries a uint32. wl-preproc's trial table stores its key as element-event's `trial_id : smallint` (`element_event/trial.py:146-153`), so a number above 32,767 fits the stream and not its table; what the database does then is UNVERIFIED there. wl-xcon keeps counting and strobes the true number, since truncating it would make two trials share a number, which wl-preproc drops silently (`schema/events.py:476`). The ceiling goes to wl-preproc (§3). A session reaching it would be a long session of a fast task; no timing claim is made about when.

### 2.3 Not in this change

- **`CONDITION` (`0x8003`) is not emitted yet** (the PI, 2026-09-30: "Wait until conditions exist"). Every trial today runs under one condition named "session", since no production path passes blocks (`_plan` makes one block with one condition), and nothing yet says who numbers conditions. wl-preproc treats `CONDITION` as optional and takes condition names from `trials.jsonl`, so nothing is lost. It is emitted once the day's plan brings real conditions (b3b, XC-150), with its numbering decided then. XC-155's condition half is refiled as its own item.
- **No `BLOCK_START`/`BLOCK_END`.** wl.works has asked wl-preproc to take wl-xcon's runs as its blocks, from `RUN_START` 4135 and `RUN_END` 4136 (wl.works' message of 2026-09-30); wl-xcon's run is wl-preproc's and the ELN's block.
- **Rows outside `trials.jsonl`** (marks, controls, parameter changes) do not gain `trial_number` here. XC-173 (what a row's `run` means outside a run) was waiting on this key and can now be decided on its own.

## 3. Told to wl-preproc once built

Once this is on `main`, wl-xcon answers wl-preproc's ask in the channel it asked in:

1. **The field is `trial_number`**: session-unique, from 1, equal to the `TRIAL_NUMBER` strobed after that trial's `TRIAL_START`; `index` and `run` stay beside it, per run. Also: the stream now carries `TRIAL_START` and `TRIAL_END` around every trial, and no `CONDITION` yet (§2.3).
2. **A question: can one sync-box recording hold two wl-xcon sessions?** For example, a morning animal and an afternoon animal on one rig, if the sync box's session spans the day. wl-preproc decodes a session directory's whole sync-box log with no per-subject split (`schema/events.py:339-343`), and "two animals can share one" sync-box session id (`nwb/gather.py:71-77`). If so, per-session numbers from 1 would collide in that stream, and the second trial with each number would be dropped silently. The answer decides whether the number must instead be unique across a rig's day.
3. **The ceiling:** `trial_id` is a `smallint`, and wl-xcon strobes the true number above 32,767.

## 4. Testing (sim first)

- **The path, through wl-preproc's own code.** A session's emitted words, from the simulated card (`dio.Simulated`, over two runs), are decoded by wl-preproc's `decode_stream` and assembled by its `assemble`. The test expects one trial per trial run, numbered 1..N across both runs, each with its outcome, its start and its recorded end. It also checks that every `trials.jsonl` line's `trial_number` equals its assembled trial's. `WLX_REQUIRE_PREPROC=1` makes a missing wl-preproc a failure, as for the codec tests.
- **Unit level:**
  - the boundary emits exactly `TRIAL_START`, the four escape words and, after the outcome, `TRIAL_END`, in that order;
  - the number carries on from run to run and a new session starts at 1;
  - a faulting trial emits no `TRIAL_END`;
  - no word is strobed between the escape and its checksum.
- **The tests that pin exact code lists** (`tests/test_service.py`, `tests/test_taskd.py` and others) are updated to the new stream. Each is re-read, not loosened: a list that now holds `32, …, 33` still pins every code.
- `tools/mutate.py` over every new and changed function.

## 5. Out of scope

- `CONDITION`, as above.
- Carrying numbers across a restart (XC-026).
- Anything wl-preproc changes on its side.
