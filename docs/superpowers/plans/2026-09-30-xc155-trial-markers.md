# XC-155 — Trial Markers and the Session's Trial Number: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Execution: subagent-driven**, the method this project uses: a fresh implementer per task and a fresh reviewer before the next one starts, then a whole-branch review on the most capable model. **No task changes welfare-critical code** (Plan decision 10); Task 4 Step 3 proves it.
>
> **Work on the branch `xc155-trial-markers`, in the worktree `.claude/worktrees/xc155`.** It is stacked on b3a-2's tip `c191784`, with the spec's own commit `f3826f6` on top, and b3a-2 reaches `main` first. Before Task 1, check that `git log --oneline -3` shows `f3826f6` over `c191784` and that `docs/superpowers/specs/2026-09-30-xc155-trial-markers-design.md` exists. If either is missing, stop and say so.
>
> **Validated before hand-off** (2026-09-30, on a copy of `f3826f6` made with `git archive`, never a checkout, with `wl-preproc` linked inside it). A script applied Tasks 1-4's code from this plan's own code blocks. Each task's new tests failed first, for the reason its step states. The suite was then green at **1999, 2003 and 2010** after Tasks 1, 2 and 3, under `WLX_REQUIRE_PREPROC=1` with no skip. Task 4's five mutation lanes read as follows: 22 targets (four functions and eighteen line mutants), **22 caught, 0 survived, 0 skipped**, every line a real `N failed`, and every baseline and restore at `2010 passed`. The slowest target, `taskd.run`, took 227 s with all five lanes at once.
>
> **Approved by the PI on 2026-09-30** ("Approve, task by task", asked in the question UI). **Backlog IDs:** Task 4 files its two items at the next free IDs when it runs (the plan's XC-196 and XC-197 may already be taken by then); use what `docs/backlog.md` says.
>
> **Every commit** ends with the session's attribution lines, as the repository's history does.

**Goal:** Every trial a session runs is framed in the neural recording's event stream: `TRIAL_START`, its `TRIAL_NUMBER` escape, and `TRIAL_END`. The trial number counts from 1 across the whole session and is written on the trial's `trials.jsonl` line as `trial_number`, so wl-preproc gets its trials and can join each to its line.

**Architecture:**
- `codes.py` mirrors wl-preproc's `Marker.TRIAL_START` (32) and `TRIAL_END` (33), and `encode.py` names the two uint32 escapes. `taskd.Session` keeps a session-long `_trial_number` beside `_sequence`.
- At each trial boundary in `Session.run`, the loop strobes `TRIAL_START` and `encode.words_for(TRIAL_NUMBER, n)` through `self.card.emit`, as `RUN_START` goes out. That happens just before `run_trial`. `TRIAL_END` goes out after the outcome marker.
- `record.SessionRecord.trial` requires `trial_number`. `run.py`, and so every frame, is unchanged.

**Tech Stack:** Python 3.11-3.13, pytest. wl-preproc is used at test time only (`tests/conftest.py`), for its `decode_stream` and `assemble`.

**Spec:** `docs/superpowers/specs/2026-09-30-xc155-trial-markers-design.md`, approved by the PI on 2026-09-30. It is short; read it whole. Its parents are S2 §3, §4 and §6 (`docs/superpowers/specs/2026-08-31-S2-event-vocabulary-design.md`) and P4d-2b spec §6.3. wl-preproc's ask is in its `docs/pending-wl-xcon-amendments.md`.

## Questions for the PI

**None.** The spec settles everything that touches the animal or the science: the numbering, the markers, `CONDITION` left for later, and what is told to wl-preproc. Everything left open is an engineering call, and those are listed below. The two open questions in spec §3 are asks of wl-preproc, not of the PI. Task 4 drafts them for the controller to send and files them as XC-197.

## Plan decisions

The spec left these to the plan. Each is taken here with its reason, and the code is in the task named.

1. **Where the markers go** (Task 3). `TRIAL_START` and the escape go out right after `make_world(trial, values, index)` and immediately before `run_trial(...)`. `TRIAL_END` goes out right after the outcome marker, before the trial's line is written.
   - **Everything the boundary strobes comes before `TRIAL_START`.** That covers `PARAM_CHANGED` from `_apply_staged`, a boundary mark from `_check_marks`, and `PAUSE`, `RESUME` and `MANUAL_REWARD` from the drain. So none of them can fall inside the escape.
   - **The trial's recorded start is as close to its first frame as the loop allows.** wl-preproc times a trial from its `TRIAL_START`. The condition draw and the world's construction are work between trials and belong before it.
   - **What follows the escape is the trial's own business.** First the start state's `enter` actions (`run.py`, before frame 1), then the frames, each calling `each_frame` first.
2. **The escape's words are computed at the boundary, not precomputed** (Task 3). `encode.words_for` builds a new list each call. At the boundary that is nothing new: the same pass already builds `values`, a world and a JSON line, and writes a file (S1 §4's between-trial surface; `record.py`'s inter-trial writes). Precomputing would need the number before the trial starts, which is exactly when the boundary computes it. CLAUDE.md's hot-path rule is about frames, and `run_trial` gains no work. Task 4 Step 3 checks that `run.py` is byte-identical.
3. **The card is reached as `RUN_START` and `RUN_END` reach it: `self.card.emit`** (Task 3). This avoids `effects.mark`/`welfare.Rig.mark`, the path a task's own `Mark` takes. These are framework structure, like the outcome marker, which the loop already strobes through `self.card.emit`. The spec says so (§2.1, "Not in the welfare-critical surface").
4. **The number is taken as a trial starts** (Task 2). `self._trial_number += 1` runs before `run_trial`, so the escape and the line carry one value.
   - **A trial that faults keeps its number.** The recording has its `TRIAL_START` and escape, though no line is written for it.
   - **The next trial, in the same run or the next, takes the next number.** A number is never reused. wl-preproc keeps the first of two trials that share one and drops the second silently (spec §2.2).
   - The numbering can therefore have a gap where a trial faulted. wl-preproc checks no contiguity (XC-155 research, Q2), and Task 4's reply tells it.
5. **A trial with no outcome is still closed** (Task 3). `TRIAL_END` goes out for every trial `run_trial` returns from, with or without an outcome. A hang (no outcome in `max_frames`) ended; it is not a fault. `check()` rules it out for every task it passes. With `TRIAL_END` it gets a recorded end rather than an inferred one, and its line says `hang`, as it always has. Only a trial that raised strobes no `TRIAL_END`, as spec §2.1 says.
6. **`trial_number` is a required keyword on `record.SessionRecord.trial`** (Task 2). It is keyword-only and has no default, as `run` has been since b3a-1.
   - **Why required:** a line written without it would join nothing in wl-preproc, and nothing would say so. That is the "safety component with no consumer" failure CLAUDE.md names.
   - **Its callers:** `simulate.simulate`, whose census writes a record only when given one, passes `index + 1`. That is the number a rig's session of that one run would strobe, so the simulator and the rig still write one shape ("the simulator and the rig write the same record through the same code"). A census strobes nothing, as spec §2.1 says.
   - `tests/test_record.py`'s direct calls each gain a `trial_number`.
7. **Names** (Task 1).
   - `codes.TRIAL_START` and `codes.TRIAL_END` are public, beside the private `_TRIAL_CORRECT` … `_TRIAL_NO_RESPONSE`, because `taskd` imports them. They sit in the same transcribed block, with its warning.
   - `encode.TRIAL_NUMBER` and `encode.CONDITION` are public, and `_UINT32_ESCAPES` is now built from them. The escape belongs to the framing that `encode.py` mirrors.
   - wl-xcon allocates nothing: all four values are wl-preproc's frozen ones (ADR-0007). `tests/test_event_encoding.py` reads each against theirs, including the five outcome markers. `codes.py` said a test kept that mirror honest, and none did.
8. **How the tests read the stream** (Task 3). No second decoder is written (S2 §6 item 2).
   - **The contract test runs wl-preproc's own `decode_stream` and `assemble`.**
   - **The unit tests write the codes as literals** (`TRIAL_START_CODE, TRIAL_END_CODE, TRIAL_NUMBER_ESCAPE = 32, 33, 0x8001`), so a wrong constant in `codes` or `encode` fails them rather than agreeing with them. They pin whole streams where the task allows it.
   - **The one helper, `_escapes`, finds escape words and strips nothing.** Its docstring says why that is sound for the streams it reads.
   - **A raw `card.codes` now carries payload words:** trial 34's low word is 34, `TRIAL_CORRECT`'s value. So the one test that read every code below 256 as a marker now reads the marker beside each `TRIAL_END` (Task 3 Step 1). The other code-reading tests are safe from this, because each runs fewer trials than the lowest code it looks for. See "The tests that pin strobed codes".
9. **The path test lives in `tests/test_taskd.py`**, guarded as `tests/test_calibration.py` guards its contract tests. A missing wl-preproc skips the test locally and fails the module under `WLX_REQUIRE_PREPROC=1`. It uses that file's own `_service_session`, `_run_spec` and `_trial_rows`. It runs 43 trials over two runs, so trials 32-38 carry payload words equal to `TRIAL_START`, `TRIAL_END` and the outcome markers, and the decoder must read them as numbers (Review Focus 1).
10. **The welfare-critical surface is unchanged.** `docs/design/architecture.md` lists:
    - `bounds.py`, `welfare.py`, `marks.py`, `stranded.py`;
    - `preflight.out_of_cage` and `gate`;
    - seven `service.py` functions;
    - `taskd.Session._ends`, `_hold`, `_manual_reward` (with `OUTSIDE_A_RUN`), `set` and `_schedule`, and two parts of `_command`;
    - `link._setting`;
    - `cli._settle_departure`, `_settle_return` and `main`'s line.

    None is touched. `Session.run` is not on the list. The markers go through `card.emit`, not `welfare.Rig.mark` (decision 3), and nothing about reward, fluid, the out-of-cage clock or stimulation changes. Task 4 Step 3 proves it by diff and by AST.
11. **`Telemetry` is unchanged.** A console's `trial_index` stays the run's index. Nothing in the spec asks a console to show the session's number, and schema 11 stays as it is.
12. **wl-preproc is told by the controller, not by this plan** (spec §3). Task 4 drafts the reply in a git-ignored file, `.superpowers/xc155/wl-preproc-reply.md`. Its two questions (two sessions in one sync-box recording, and the `smallint` ceiling) are filed as **XC-197**, so the wait on wl-preproc's answer is on the backlog. XC-155's `CONDITION` half is filed as **XC-196** (the PI: "Wait until conditions exist").
13. **No timing claim.** Each trial now strobes five more words at the boundary. What a word costs on the real card is unmeasured (XC-064, which waits on the card and the sync box). This plan states no number for it.

## Global Constraints

- US English in code, docs and comments.
- **"At the boundary, never in a frame."** `TRIAL_START` and the escape go out "before the trial's first frame", and `TRIAL_END` "after the outcome marker (34-38)". "`run_trial`'s frames gain no work" (spec §2.1). `wl_xcon/run.py` is not modified.
- **"Unbroken (S2 §6 item 3): no other word is strobed between the escape and its checksum on any path"** (spec §2.1).
- **"A trial that faults strobes no `TRIAL_END`: the card may be what failed"** (spec §2.1).
- **"Both `wlx run` and `wlx taskd` emit them, since both go through `Session.run`. The census (`simulate`) and any path with no card emit nothing new"** (spec §2.1).
- **"`codes.py` mirrors `TRIAL_START` 32 and `TRIAL_END` 33 beside the outcome markers 34-38 it already mirrors. They are wl-preproc's frozen framework codes; wl-xcon allocates nothing (ADR-0007)"** (spec §2.1).
- **"Not in the welfare-critical surface. ... the markers go through `card.emit` as `RUN_START` and `RUN_END` do, not through `welfare.Rig.mark`"** (spec §2.1).
- **"It counts from 1, across the whole session"**, is held "in `Session` beside `_sequence`", and is recorded "on the trial's line in `trials.jsonl` as `trial_number`". "`index` (per run) and `run` stay on every line, unchanged" (spec §2.2).
- **"wl-xcon keeps counting and strobes the true number, since truncating it would make two trials share a number"** (spec §2.2).
- **Not in this change** (spec §2.3): `CONDITION` (0x8003), `BLOCK_START`/`BLOCK_END`, and `trial_number` on rows outside `trials.jsonl`.
- Hot path: nothing new per frame. No timing claim without a measurement (CLAUDE.md).
- Sim first: every behavior has a simulator-backed test. wl-preproc is a test-time dependency only. `WLX_REQUIRE_PREPROC=1` makes its absence a failure.
- `tools/mutate.py`'s method is run over every new and changed function and line before the branch merges, each line read as a real `N failed` (CLAUDE.md, "Prove a test can fail"; Task 4 Step 5).
- **Nothing is sent to wl-preproc** by whoever builds this: Task 4 drafts, the controller sends.

## Review Focus

These are the five inputs most likely to bite a real session that the spec implies without testing. Each is pinned by a test in its owning task.

1. **A trial number equal to a code's value.** Trial 32's escape carries the word 32, `TRIAL_START`'s value, and trials 33-38 carry `TRIAL_END` and the outcome markers. Expected: wl-preproc reads each as a payload, never as a marker, and every trial assembles with its own number. Test: Task 3, `test_a_sessions_stream_assembles_in_wl_preproc_into_its_trials_numbered_across_runs` (43 trials).
2. **A trial that faults, then another run in the same session.** Expected: the faulted trial is opened and numbered and never closed, and no later trial reuses its number. Tests: Task 2, `test_a_trial_that_faults_keeps_its_number_and_the_next_trial_never_reuses_it`; Task 3, `test_a_trial_that_faults_is_opened_and_numbered_and_never_closed`.
3. **Something strobed at the boundary or in the trial's first frame:** a mark, a staged change, a pause. Expected: all of it outside the escape, which stays four unbroken words straight after `TRIAL_START`. Test: Task 3, `test_nothing_is_strobed_inside_a_trial_numbers_escape`.
4. **A trial that ends with no outcome (a hang).** Expected: no outcome marker, a `TRIAL_END` all the same, and a line recording `hang`. Test: Task 3, `test_a_trial_that_reaches_no_outcome_is_still_closed`.
5. **A number past 16 bits.** Expected: the high word carries it, never truncated, and the line carries the same number. Test: Task 3, `test_a_number_past_16_bits_is_strobed_whole_high_word_first`.

## The tests that pin strobed codes

Every test that reads a session's `card.codes` or `cards[0].codes` is listed here, found by the parser rather than by memory, with what this plan does to it. Three things decide whether a test changes:

- **A session that runs no trial strobes exactly what it strobed before.** Its exact list stays exact.
- **A test looking for a code of 4096 or more** can meet it as a payload word only in a session of 4096 trials or more. No such test runs more than 1,000 trials: `_bounds`' 800 s out-of-cage ceiling stops most near 400, and the e2e budgets are 400 or `trials=` of 300 or less.
- **A test reading codes below 256** now meets payload words.

Nothing below is loosened. Every change pins more than the line it replaces.

| Test | What it pins | This plan |
|---|---|---|
| `test_service.py`: `test_open_marks_the_departure_opens_the_session_and_waits_between_runs` (194), `test_a_confirmed_return_nobody_was_asked_about_is_refused_and_nothing_is_marked` (430), `test_end_releases_the_head_takes_the_return_and_goes_back_to_idle` (493), `test_a_check_shows_the_runs_preflight_and_starts_nothing` (899), `test_a_task_whose_declarations_are_malformed_fails_its_preflight_and_the_service_goes_on` (936), `test_a_task_named_by_no_one_file_name_loads_nothing_and_runs_nothing` (1091), `test_a_run_past_the_out_of_cage_limit_is_refused_before_run_start_is_strobed` (1128), `test_a_run_its_session_refuses_as_it_starts_is_a_refusal_and_runs_nothing` (1438), `test_a_run_that_fails_before_it_starts_says_why_on_the_feed_and_on_stderr` (1465) | the whole list: `[4128]` or `[4128, 4129]` | **Unchanged.** No trial runs in any of them, so each list is still the whole stream. |
| `test_service.py`: `test_an_acknowledged_run_starts_records_who_acknowledged_what_and_ends_between_runs` (1029) | `codes[:2] == [4128, 4135]`, `4136 in codes`, `4129 not in codes` | **Tightened, Task 3:** `codes[:3] == [4128, 4135, 32]` and `codes[-2:] == [33, 4136]`: the run's trials sit between its `RUN_START` and `RUN_END`. |
| `test_service.py`: `test_e2e_open_a_session_run_it_twice_and_end_it` (1746) | first and last code, two `RUN_START`s and two `RUN_END`s, each line's run | **Extended:** Task 2, each line's `(run, trial_number)` is `(0, 1)` … `(1, 6)`; Task 3, six `TRIAL_START`s and six `TRIAL_END`s. The `wlx taskd` path over a real link. |
| `test_service.py`: `test_between_runs_a_mark_is_stamped_and_strobed` (697), `test_a_run_is_checked_or_started_only_between_the_runs_of_an_open_session` (884), `test_end_during_a_run_releases_the_head_only_once_the_run_has_ended` (1174), `test_a_run_checks_for_marks_through_the_links_own_method` (1354), `test_the_hand_reward_works_between_runs_and_while_the_return_is_awaited` (1920), `test_during_a_run_a_hand_reward_is_still_given_only_while_paused` (1952), `test_a_reward_drained_after_the_end_that_records_the_return_gives_nothing` (1975) | a code of 4128 or more: last, absent, counted, or ordered | **Unchanged**, and still exact: no run, or a run far short of 4096 trials. |
| `test_taskd.py`: `test_a_run_is_strobed_where_it_starts_and_where_it_ends` (297) | `codes[:2] == [4128, RUN_START]`, `codes[-2:] == [RUN_END, 4129]` | **Tightened, Task 3:** `codes[:3] == [4128, RUN_START, TRIAL_START_CODE]`, `codes[-3:] == [TRIAL_END_CODE, RUN_END, 4129]`. |
| `test_taskd.py`: `test_a_session_strobes_the_outcome_marker_the_allocation_gives` (600) | every code below 256 is a marker, one per trial | **Rewritten, Task 3.** It fails as it stands, reading 100 "markers" in 20 trials, because payload words are below 256. It now reads the code beside each `TRIAL_END`: 20 of them, each in 34-38, each the one the allocation gives that trial's recorded outcome. |
| `test_taskd.py`: 320, 589-590, 697-698, 847, 858, 1039, 2746, 2924, 2973-2974, 2994, 3011, 3156-3157, 3175, 3195, 3275, 3306, 3747, 3788, 3844-3846, 3869, 3898, 3925, 4000, 4026, 4097, 4156, 4219, 4336, 4351, 4388, 4417, 4438 | a code of 4096 or more: first, last, present, absent, counted or ordered; or `_trial_codes`' window, from a trial's `FIX_ON` to its marker, which the escape precedes | **Unchanged**, and still exact: each session runs at most a few hundred trials. |
| `test_serve.py`: 3396, 3483, 3639, 3841, 4101, 4311 | the same, over real processes | **Unchanged**: `CONTROL_TRIAL_BUDGET` is 400, and the page tests run `trials=` of 300 or less. |
| `test_dio.py` 94, `test_welfare.py` 1606 | a card or a `Rig` driven directly | **Unchanged**: no session. |
| `test_cli.py` | reads no strobed code; its fake `emit` raises | `test_wlx_run_runs_a_session_and_reports_its_outcomes` gains its lines' `trial_number` 1-20 (Task 2): the `wlx run` path. |

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `wl_xcon/codes.py` | modify | mirror `TRIAL_START` 32 and `TRIAL_END` 33 |
| `wl_xcon/encode.py` | modify | name `TRIAL_NUMBER` and `CONDITION`; `_UINT32_ESCAPES` from them |
| `wl_xcon/record.py` | modify | `SessionRecord.trial` requires and writes `trial_number` |
| `wl_xcon/simulate.py` | modify | the census's record numbers its trials from 1 |
| `wl_xcon/taskd.py` | modify | `Session._trial_number`; `run()` strobes `TRIAL_START`, the escape, `TRIAL_END`, and records the number |
| `tests/test_event_encoding.py` | modify | the escapes' and markers' values against wl-preproc's; `CONDITION`'s framing |
| `tests/test_record.py` | modify | every `trial()` call gives a number; the number is required and written |
| `tests/test_taskd.py` | modify | the numbering, the stream, and the path through wl-preproc's assembler |
| `tests/test_service.py`, `tests/test_cli.py` | modify | the `wlx taskd` and `wlx run` paths carry the numbers; one list tightened |
| `docs/backlog.md` | modify | XC-155 closed; XC-196 and XC-197 filed; XC-173 waits on nothing |
| `docs/design/architecture.md` | modify | the stream's trial framing, under "Hardware truth" |
| `.superpowers/xc155/wl-preproc-reply.md` | create, **not committed** (git-ignored) | the reply for the controller to send |

---

### Task 1: The codec's names for the trial markers and the trial number

**Files:**
- Modify: `wl_xcon/codes.py` (the transcribed `Marker` block), `wl_xcon/encode.py` (above `_UINT32_ESCAPES`)
- Test: `tests/test_event_encoding.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `codes.TRIAL_START == 32`, `codes.TRIAL_END == 33` (ints); `encode.TRIAL_NUMBER == 0x8001`, `encode.CONDITION == 0x8003` (ints); `encode._UINT32_ESCAPES == (TRIAL_NUMBER, CONDITION)`. `encode.words_for(escape: int, value: int) -> list[int]` is unchanged. Task 3 imports `TRIAL_START`, `TRIAL_END` from `codes` and `TRIAL_NUMBER`, `words_for` from `encode`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_event_encoding.py`, find:

```python
from wl_xcon.encode import words_for, words_for_code  # noqa: E402
```

Replace it with:

```python
from wl_xcon import codes, encode  # noqa: E402
from wl_xcon.encode import words_for, words_for_code  # noqa: E402
```

The module's comment counts its tests, and this task changes the count. Find:

```python
#: CI sets this. A skip is the right behaviour on a laptop without the sibling
#: checkout and the **wrong** behaviour in CI, where these nine tests are the only
```

Replace it with:

```python
#: CI sets this. A skip is the right behaviour on a laptop without the sibling
#: checkout and the **wrong** behaviour in CI, where these tests are the only
```

Find the framing parity test:

```python
@pytest.mark.parametrize("value", [0, 1, 4242, 65535, 65536, 4294967295])
def test_our_payload_framing_matches_theirs_exactly(value):
    """Their `encode_payload` as an oracle, across the uint32 range.

    Stronger than the round trip: it catches a drift that happens to survive
    decoding -- a checksum convention that is self-consistent but not theirs, or a
    word order that reads back the same because both halves were swapped.
    """
    Escape = wl_preproc_events.Escape
    payload = [(value >> 16) & 0xFFFF, value & 0xFFFF]

    assert words_for(Escape.TRIAL_NUMBER, value) == wl_preproc_events.encode_payload(
        Escape.TRIAL_NUMBER, payload
    )
```

Replace it with the same test over both escapes, followed by two new tests:

```python
@pytest.mark.parametrize("escape", ["TRIAL_NUMBER", "CONDITION"])
@pytest.mark.parametrize("value", [0, 1, 4242, 65535, 65536, 4294967295])
def test_our_payload_framing_matches_theirs_exactly(escape, value):
    """Their `encode_payload` as an oracle, across the uint32 range, for both escapes
    `words_for` frames.

    Stronger than the round trip: it catches a drift that happens to survive
    decoding -- a checksum convention that is self-consistent but not theirs, or a
    word order that reads back the same because both halves were swapped.

    **`CONDITION` too, although nothing emits it yet** (it waits on the conditions the
    day's plan brings, XC-150): `words_for` has framed it since it was written, and no
    test read that framing against theirs until XC-155.
    """
    their = wl_preproc_events.Escape[escape]
    payload = [(value >> 16) & 0xFFFF, value & 0xFFFF]

    assert words_for(their, value) == wl_preproc_events.encode_payload(their, payload)


def test_the_escapes_the_rig_names_are_theirs():
    """`encode.TRIAL_NUMBER` is the escape `taskd` strobes each trial's number behind
    (XC-155), so a wrong value there is a stream wl-preproc reads as another escape, or
    as none at all."""
    Escape = wl_preproc_events.Escape

    assert (encode.TRIAL_NUMBER, encode.CONDITION) == (Escape.TRIAL_NUMBER, Escape.CONDITION)


def test_every_marker_codes_mirrors_is_theirs():
    """`codes.py` mirrors `Marker` values and says the round-trip tests keep the mirror
    honest. `TRIAL_START` and `TRIAL_END` frame every trial since XC-155; the five
    outcome markers were mirrored before any test read them against theirs."""
    mirrored = {
        "TRIAL_START": codes.TRIAL_START,
        "TRIAL_END": codes.TRIAL_END,
        "TRIAL_CORRECT": codes._TRIAL_CORRECT,
        "TRIAL_ERROR": codes._TRIAL_ERROR,
        "TRIAL_ABORT": codes._TRIAL_ABORT,
        "TRIAL_FIXATION_BREAK": codes._TRIAL_FIXATION_BREAK,
        "TRIAL_NO_RESPONSE": codes._TRIAL_NO_RESPONSE,
    }

    assert mirrored == {name: int(wl_preproc_events.Marker[name]) for name in mirrored}
```

- [ ] **Step 2: Run the tests to see which fail, and why**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_event_encoding.py -q -p no:cacheprovider`
Expected: `2 failed, 15 passed`. The two failures are `test_the_escapes_the_rig_names_are_theirs` and `test_every_marker_codes_mirrors_is_theirs`, each an `AttributeError` (no `encode.TRIAL_NUMBER` / `codes.TRIAL_START` yet). **The six `CONDITION` cases pass already**: `words_for` has framed `CONDITION` all along, and nothing tested it. Step 3 proves they can fail.

- [ ] **Step 3: Prove the `CONDITION` cases read `CONDITION`'s framing**

Temporarily, in `wl_xcon/encode.py`'s `words_for`, change the return line:

```python
    return [escape, *payload, _checksum(escape, payload)]
```

to a checksum that is right only for `TRIAL_NUMBER`:

```python
    return [escape, *payload, _checksum(0x8001, payload)]
```

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_event_encoding.py -q -p no:cacheprovider`
Expected: `8 failed, 9 passed`. The six `[...-CONDITION]` cases fail, plus Step 2's two; every `[...-TRIAL_NUMBER]` case passes.

Then restore the file exactly: `git checkout -- wl_xcon/encode.py`, and check that `git diff --stat -- wl_xcon/encode.py` prints nothing. (Nothing else has changed `encode.py` yet in this task.)

- [ ] **Step 4: Write the implementation**

In `wl_xcon/codes.py`, find the head of the transcribed block's comment:

```python
#: `Marker` values transcribed from `wl-preproc/wl_preproc/contracts/events.py`,
#: which is frozen and carries an explicit warning that renumbering silently
#: relabels every prior recording. Mirrored rather than imported so the rig carries
#: no pipeline dependency; the round-trip tests keep the mirror honest.
#:
```

Replace it with:

```python
#: `Marker` values transcribed from `wl-preproc/wl_preproc/contracts/events.py`,
#: which is frozen and carries an explicit warning that renumbering silently
#: relabels every prior recording. Mirrored rather than imported so the rig carries
#: no pipeline dependency; the round-trip tests keep the mirror honest
#: (`tests/test_event_encoding.py` reads each value here against theirs).
#:
#: **`TRIAL_START` and `TRIAL_END` frame every trial, and the framework strobes them**
#: (XC-155): `taskd.Session.run` puts `TRIAL_START` and the trial's `TRIAL_NUMBER`
#: escape before the trial's first frame, and `TRIAL_END` after its outcome marker.
#: wl-preproc opens a trial at the one and closes it at the other
#: (`events/assemble.py`), so a stream without them holds no trials at all. Public,
#: unlike the five outcome markers, since `taskd` strobes them by name.
#:
```

(The `**NO_FIXATION maps to TRIAL_ABORT**` paragraph that follows stays as it is.) Then find:

```python
_TRIAL_CORRECT = 34
```

Replace it with:

```python
TRIAL_START = 32
TRIAL_END = 33
_TRIAL_CORRECT = 34
```

In `wl_xcon/encode.py`, find:

```python
#: Payload word counts, mirroring `wl-preproc`'s `PAYLOAD_WORD_COUNTS`. Mirrored
#: rather than imported so the rig carries no pipeline dependency; the round-trip
#: tests are what keep the mirror honest, and a drift fails there rather than in a
#: recording.
_UINT32_ESCAPES = (0x8001, 0x8003)  # TRIAL_NUMBER, CONDITION
```

Replace it with:

```python
#: The two escapes whose payload is one uint32, by `wl-preproc`'s names. `taskd`
#: strobes each trial's number behind `TRIAL_NUMBER` (XC-155). `CONDITION` is framed
#: here and emitted by nothing yet: it waits on the conditions the day's plan brings
#: (XC-150), and on who numbers them, decided then.
TRIAL_NUMBER = 0x8001
CONDITION = 0x8003

#: Payload word counts, mirroring `wl-preproc`'s `PAYLOAD_WORD_COUNTS`. Mirrored
#: rather than imported so the rig carries no pipeline dependency; the round-trip
#: tests are what keep the mirror honest, and a drift fails there rather than in a
#: recording.
_UINT32_ESCAPES = (TRIAL_NUMBER, CONDITION)
```

- [ ] **Step 5: Run the tests to see them pass, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_event_encoding.py -q -p no:cacheprovider`
Expected: `17 passed`.

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider -rs`
Expected: all pass (1999 at validation), and no skip from `test_event_encoding.py`.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/codes.py wl_xcon/encode.py tests/test_event_encoding.py
git commit -m "Name the trial markers and the uint32 escapes, and read them against wl-preproc's"
```

---

### Task 2: Every trial's line carries its session-wide number

**Files:**
- Modify: `wl_xcon/record.py` (`SessionRecord.trial`), `wl_xcon/simulate.py` (`simulate`), `wl_xcon/taskd.py` (`Session`'s fields; `Session.run`'s loop)
- Test: `tests/test_record.py`, `tests/test_taskd.py` (a new section at its end), `tests/test_service.py` (`test_e2e_open_a_session_run_it_twice_and_end_it`), `tests/test_cli.py` (`test_wlx_run_runs_a_session_and_reports_its_outcomes`)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `SessionRecord.trial(index, outcome, params, block="", condition="", *, run: int, trial_number: int) -> None`: `trial_number` is keyword-only and required, and written as the line's `"trial_number"`.
  - `taskd.Session._trial_number: int`: 0 before the session's first trial, and the latest trial's number after. It is incremented once per trial, before `run_trial`, and never reset by `run()`.
  - Task 3 inserts its strobes around that increment. Its code block depends on the exact comment line written here: `# The trial's number, taken as it starts (`_trial_number`).`

- [ ] **Step 1: Write the failing tests**

**`tests/test_record.py`: every direct call gives a number, and two tests pin it.** Make each replacement below exactly; each "find" text occurs once in the file.

In `test_a_trial_is_on_disk_before_the_session_ends`, find:

```python
    record.trial(index=1, outcome="correct", params={"fix_hold": 0.3}, run=0)

    written = (
```

Replace it with:

```python
    record.trial(index=1, outcome="correct", params={"fix_hold": 0.3}, run=0, trial_number=2)

    written = (
```

In `test_every_trial_carries_its_whole_resolved_parameter_set`, find:

```python
    record.trial(index=1, outcome="correct", params={"fix_hold": 0.3}, run=0)
    record.trial(index=2, outcome="correct", params={"fix_hold": 0.9}, run=0)
```

Replace it with:

```python
    record.trial(index=1, outcome="correct", params={"fix_hold": 0.3}, run=0, trial_number=2)
    record.trial(index=2, outcome="correct", params={"fix_hold": 0.9}, run=0, trial_number=3)
```

In `test_the_subject_is_on_every_trial_not_only_in_a_header`, find:

```python
    record.trial(index=1, outcome="correct", params={}, run=0)

    row = json.loads(
```

Replace it with:

```python
    record.trial(index=1, outcome="correct", params={}, run=0, trial_number=2)

    row = json.loads(
```

Find the whole of `test_the_trial_file_is_reopened_for_each_run_and_every_row_names_its_run`:

```python
def test_the_trial_file_is_reopened_for_each_run_and_every_row_names_its_run(tmp_path):
    """Spec §6.3: "Every trial row names its run." The record lives for the session and
    its trial file for a run: closed with one, reopened by the next one's first trial."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=0, outcome="correct", params={}, run=0)
    record.close()
    record.trial(index=0, outcome="no_response", params={}, run=1)
    record.close()
    record.close()  # a second close does nothing

    rows = [
        json.loads(line)
        for line in (record.directory / "trials.jsonl").read_text().splitlines()
    ]
    assert [(row["run"], row["index"], row["outcome"]) for row in rows] == [
        (0, 0, "correct"),
        (1, 0, "no_response"),
    ]
```

Replace it with this version and a new test after it:

```python
def test_the_trial_file_is_reopened_for_each_run_and_every_row_names_its_run(tmp_path):
    """Spec §6.3: "Every trial row names its run." The record lives for the session and
    its trial file for a run: closed with one, reopened by the next one's first trial.
    **And every row carries its trial number beside its run and its index** (XC-155),
    written as given: `taskd` counts it across the session, and wl-preproc joins on it."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=0, outcome="correct", params={}, run=0, trial_number=1)
    record.close()
    record.trial(index=0, outcome="no_response", params={}, run=1, trial_number=2)
    record.close()
    record.close()  # a second close does nothing

    rows = [
        json.loads(line)
        for line in (record.directory / "trials.jsonl").read_text().splitlines()
    ]
    assert [(row["run"], row["index"], row["trial_number"], row["outcome"]) for row in rows] == [
        (0, 0, 1, "correct"),
        (1, 0, 2, "no_response"),
    ]


def test_a_trial_row_is_never_written_without_its_trial_number(tmp_path):
    """XC-155: wl-preproc joins a `trials.jsonl` line to the recording's trial by its
    `trial_number` alone, so a line written without one would join nothing, and nothing
    would say so. Required, as `run` is, and never defaulted."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")

    with pytest.raises(TypeError, match="trial_number"):
        record.trial(index=0, outcome="correct", params={}, run=0)

    assert not (record.directory / "trials.jsonl").exists()
```

In `test_a_crash_leaves_every_trial_written_so_far`, find:

```python
        record.trial(index=index, outcome="correct", params={}, run=0)
```

Replace it with:

```python
        record.trial(index=index, outcome="correct", params={}, run=0, trial_number=index + 1)
```

In `test_a_simulated_session_writes_a_real_session_directory`, find:

```python
    assert json.loads(rows[0])["params"] == {"timeout": 1.0}
```

Replace it with:

```python
    assert json.loads(rows[0])["params"] == {"timeout": 1.0}
    # The numbers a rig's session of this one run would strobe (XC-155).
    assert [json.loads(row)["trial_number"] for row in rows] == list(range(1, 51))
```

In `test_closing_releases_the_file_and_the_context_manager_does_it_for_you`, find:

```python
        r.trial(index=1, outcome="correct", params={}, run=0)
```

Replace it with:

```python
        r.trial(index=1, outcome="correct", params={}, run=0, trial_number=2)
```

**`tests/test_cli.py`: the `wlx run` path.** In `test_wlx_run_runs_a_session_and_reports_its_outcomes`, find:

```python
    assert "correct" in out
    assert (tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl").exists()
```

Replace it with (`json` is already imported there):

```python
    assert "correct" in out
    lines = (tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text().splitlines()
    # `wlx run`'s one run numbers its trials from 1 (XC-155).
    assert [json.loads(line)["trial_number"] for line in lines] == list(range(1, 21))
```

**`tests/test_service.py`: the `wlx taskd` path, over a real link.** In `test_e2e_open_a_session_run_it_twice_and_end_it`, find:

```python
    trials = [
        json.loads(line)["run"]
        for line in (root / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text().splitlines()
    ]
    assert trials == [0, 0, 0, 1, 1, 1]
```

Replace it with:

```python
    trials = [
        json.loads(line)
        for line in (root / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text().splitlines()
    ]
    # Each trial's number counts on across the session's two runs (XC-155).
    assert [(trial["run"], trial["trial_number"]) for trial in trials] == [
        (0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (1, 6),
    ]
```

**`tests/test_taskd.py`: the numbering.** Append this section at the very end of the file (it starts with the blank lines that separate it from the last test):

```python


# --- the session's trial number (XC-155) --------------------------------------------


def test_each_trial_line_carries_its_number_counted_across_the_sessions_runs(tmp_path):
    """XC-155 spec §2.2: the number counts from 1 across the whole session, whichever run
    a trial is in, and is written on its `trials.jsonl` line as `trial_number` -- the
    field wl-preproc joins a line to its recorded trial by. `index` and `run` stay
    beside it, per run."""
    session = _service_session(tmp_path)

    session.run(_run_spec(trials=3))
    session.run(_run_spec(trials=2))

    assert [(row["run"], row["index"], row["trial_number"]) for row in _trial_rows(session)] == [
        (0, 0, 1), (0, 1, 2), (0, 2, 3), (1, 0, 4), (1, 1, 5),
    ]


def test_a_new_session_numbers_its_trials_from_1_again(tmp_path):
    """Spec §2.2: unique within one session. A new session is another session --
    another id, another folder -- and starts again at 1."""
    first = _service_session(tmp_path / "a")
    first.run(_run_spec(trials=2))

    second = _service_session(tmp_path / "b")
    second.run(_run_spec(trials=2))

    assert [row["trial_number"] for row in _trial_rows(first)] == [1, 2]
    assert [row["trial_number"] for row in _trial_rows(second)] == [1, 2]


def test_a_trial_that_faults_keeps_its_number_and_the_next_trial_never_reuses_it(
    tmp_path, monkeypatch
):
    """The number is taken as a trial starts (`Session._trial_number`), so a trial that
    faults has used it -- the recording has it, though no line is written for the trial
    -- and the session's next trial takes the next one. A number used twice would be
    two trials in one recording, and wl-preproc keeps the first and drops the second
    silently (XC-155 spec §2.2)."""
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
        session.run(_run_spec(trials=3))
    session.run(_run_spec(trials=2))

    assert [(row["run"], row["trial_number"]) for row in _trial_rows(session)] == [
        (0, 1), (1, 3), (1, 4),
    ]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_record.py tests/test_taskd.py "tests/test_cli.py::test_wlx_run_runs_a_session_and_reports_its_outcomes" "tests/test_service.py::test_e2e_open_a_session_run_it_twice_and_end_it" -q -p no:cacheprovider`
Expected: **13 failed**:
- the six `test_record.py` tests that call `trial(...)` with a number: `TypeError` for the unexpected keyword `trial_number`;
- `test_a_simulated_session_writes_a_real_session_directory` and the three new `test_taskd.py` tests, with `KeyError: 'trial_number'`;
- `test_a_trial_row_is_never_written_without_its_trial_number`, since no `TypeError` is raised;
- the `test_cli.py` and `test_service.py` tests, with `KeyError: 'trial_number'`.

- [ ] **Step 3: Write the implementation**

**`wl_xcon/record.py`.** Find:

```python
        *,
        run: int,
    ) -> None:
        """One trial's record, flushed before returning.
```

Replace it with:

```python
        *,
        run: int,
        trial_number: int,
    ) -> None:
        """One trial's record, flushed before returning.
```

Find the end of the same docstring:

```python
        **And the run it is part of** (P4d-2b spec §6.3: "every trial row names its
        run"), since a session holds several and each counts its trials from 0.
        """
```

Replace it with:

```python
        **And the run it is part of** (P4d-2b spec §6.3: "every trial row names its
        run"), since a session holds several and each counts its trials from 0.

        **And its trial number** (XC-155): counted from 1 across the whole session, the
        number `taskd` strobed in the trial's `TRIAL_NUMBER` escape, so the line and the
        recording's trial carry one number. wl-preproc joins them by it: `index`
        restarts with each run, and the stream numbers trials across the session.
        Required, as `run` is: a line written without it would join nothing, and
        nothing would say so.
        """
```

In the same method's `json.dumps({...})`, find:

```python
                    "run": run,
                    "subject": self.subject,
```

Replace it with:

```python
                    "run": run,
                    "trial_number": trial_number,
                    "subject": self.subject,
```

**`wl_xcon/simulate.py`**, in `simulate`'s `record.trial(...)` call. Find:

```python
                run=0,  # one simulated run; a session of several is `taskd`'s
            )
```

Replace it with:

```python
                run=0,  # one simulated run; a session of several is `taskd`'s
                # The number a rig's session of this one run strobes for the trial,
                # counting from 1 (`taskd.Session._trial_number`); a census strobes none.
                trial_number=index + 1,
            )
```

**`wl_xcon/taskd.py`.** In `Session`'s fields, find:

```python
    _sequence: int = field(init=False, default=0, repr=False)
```

Replace it with:

```python
    _sequence: int = field(init=False, default=0, repr=False)
    #: **The number of the session's latest trial, counted from 1 across all its runs**
    #: (XC-155), or 0 before its first: strobed in that trial's `TRIAL_NUMBER` escape and
    #: written on its `trials.jsonl` line as `trial_number`, the field wl-preproc joins a
    #: line to its recorded trial by. Kept for the session beside `_sequence`, which
    #: `run()`'s reset leaves alone for the same reason (the b3a-1 plan, decision 2): a
    #: run's `index` restarts at 0, and a number that restarted would name two trials in
    #: one recording, of which wl-preproc keeps the first and drops the second silently.
    #: **Taken as a trial starts**, so a trial that faults keeps its number -- it is in
    #: the recording -- and the next trial never reuses it.
    _trial_number: int = field(init=False, default=0, repr=False)
```

In `Session.run`'s loop, find:

```python
                world = make_world(trial, values, index)
                result = run_trial(
```

Replace it with:

```python
                world = make_world(trial, values, index)
                # The trial's number, taken as it starts (`_trial_number`).
                self._trial_number += 1
                result = run_trial(
```

In the same loop's `record.trial(...)` call, find:

```python
                    run=self.run_index,
                )
                if self.observe is not None:
```

Replace it with:

```python
                    run=self.run_index,
                    trial_number=self._trial_number,
                )
                if self.observe is not None:
```

- [ ] **Step 4: Run the tests to see them pass, then the suite**

Run the Step 2 command again.
Expected: all pass.

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider -rs`
Expected: all pass (2003 at validation).

- [ ] **Step 5: Commit**

```bash
git add wl_xcon/record.py wl_xcon/simulate.py wl_xcon/taskd.py tests/test_record.py tests/test_taskd.py tests/test_service.py tests/test_cli.py
git commit -m "Number each trial from 1 across the session and write it on the trial's line"
```

---

### Task 3: Each trial is opened, numbered and closed in the stream

**Files:**
- Modify: `wl_xcon/taskd.py` (imports; `Session.run`'s loop)
- Test: `tests/test_taskd.py` (imports; a wl-preproc guard; constants; two tests updated; a new section at its end), `tests/test_service.py` (two tests)

**Interfaces:**
- Consumes: from Task 1, `codes.TRIAL_START`, `codes.TRIAL_END`, `encode.TRIAL_NUMBER` and `encode.words_for`. From Task 2, `Session._trial_number` and its increment's comment line, and `trials.jsonl`'s `trial_number`.
- Produces: the stream around every trial `run_trial` returns from:
  - `TRIAL_START`, `0x8001`, the high word, the low word, `0x8001 ^ high ^ low`;
  - the trial's own codes, then its outcome marker, if it has one;
  - `TRIAL_END`.

  A trial that raises gets no `TRIAL_END`. In `tests/test_taskd.py`: `TRIAL_START_CODE`, `TRIAL_END_CODE`, `TRIAL_NUMBER_ESCAPE`, `ONE_STATE_TASK`, `_escapes(codes) -> list[list[int]]`, `_contract`, `their_events`, `their_assemble`.

- [ ] **Step 1: Write the failing tests**

**`tests/test_taskd.py`, its head.** Find:

```python
import json
import sys
import textwrap
```

Replace it with:

```python
import json
import os
import sys
import textwrap
```

Find the last import line and the blank line after it:

```python
from _rig import DIRECT, STEREOSCOPE

```

Replace it with the import line, the wl-preproc guard, and the blank line:

```python
from _rig import DIRECT, STEREOSCOPE

#: wl-preproc's decoder and trial assembler, for the test that runs a session's stream
#: through them (XC-155): the code that turns a recording into trials. A missing
#: checkout skips that test locally and fails this module under `WLX_REQUIRE_PREPROC=1`,
#: which CI sets -- the guard `tests/test_calibration.py` uses.
_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts import events as their_events
    from wl_preproc.events.assemble import assemble as their_assemble
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). A session's "
            f"stream assembled into trials by wl-preproc's own code is the only check that "
            f"a recording from this rig holds its trials; skipping it would report trials "
            f"nobody assembled"
        ) from exc
    their_events = their_assemble = None

_contract = pytest.mark.skipif(
    their_assemble is None,
    reason="wl-preproc checkout not beside this repo; the path through its assembler cannot run",
)

```

Find:

```python
RUN_START, RUN_END = 4135, 4136
```

Replace it with:

```python
RUN_START, RUN_END = 4135, 4136
#: wl-preproc's `Marker.TRIAL_START` and `TRIAL_END`, and its `Escape.TRIAL_NUMBER`
#: (XC-155), written here as numbers rather than read from `codes` or `encode`, so a
#: wrong value there fails these tests rather than agreeing with them.
TRIAL_START_CODE, TRIAL_END_CODE, TRIAL_NUMBER_ESCAPE = 32, 33, 0x8001
```

In `test_a_run_is_strobed_where_it_starts_and_where_it_ends`, find:

```python
    codes = session.card.codes
    assert codes[:2] == [4128, RUN_START], "after HEAD_FIXED, before the first trial"
    assert codes[-2:] == [RUN_END, 4129], "after the last trial, before HEAD_RELEASED"
```

Replace it with:

```python
    codes = session.card.codes
    assert codes[:3] == [4128, RUN_START, TRIAL_START_CODE], "before the first trial opens"
    assert codes[-3:] == [TRIAL_END_CODE, RUN_END, 4129], "after the last trial closes"
```

Find the whole of `test_a_session_strobes_the_outcome_marker_the_allocation_gives`:

```python
def test_a_session_strobes_the_outcome_marker_the_allocation_gives(tmp_path):
    """`Marker` 34-38 are `wl-preproc`'s and the framework's to emit -- a task
    declares an `Outcome`, never a marker. Without them a recording has no trial
    boundaries at all, whatever else is in the stream."""
    session = _session(_spec(tmp_path, trials=20))
    census = session.run()

    markers = [code for code in session.card.codes if code < 256]
    assert len(markers) == sum(census.outcomes.values())
    assert set(markers) <= {34, 35, 36, 37, 38}
```

Replace it with:

```python
def test_a_session_strobes_the_outcome_marker_the_allocation_gives(tmp_path):
    """`Marker` 34-38 are `wl-preproc`'s and the framework's to emit -- a task
    declares an `Outcome`, never a marker. Without them a recording's trials have no
    outcomes, whatever else is in the stream. Each trial's is strobed just before its
    `TRIAL_END` (XC-155), and is the one the allocation gives its recorded outcome.

    **Read beside each `TRIAL_END`, not as every code below 256**, as it was until
    XC-155: the stream now carries each trial's number as payload words, and trial
    34's low word is 34, `TRIAL_CORRECT`'s value. Twenty trials put no payload word at
    33, so each `TRIAL_END` found here is one."""
    session = _session(_spec(tmp_path, trials=20))
    census = session.run()

    codes = session.card.codes
    markers = [codes[i - 1] for i, code in enumerate(codes) if code == TRIAL_END_CODE]
    assert len(markers) == sum(census.outcomes.values()) == 20
    assert set(markers) <= {34, 35, 36, 37, 38}
    assert markers == [
        session.allocation.outcomes[Outcome(row["outcome"])] for row in _trial_rows(session)
    ]
```

Append this section at the very end of `tests/test_taskd.py`, after Task 2's:

```python


# --- the trial markers (XC-155) -----------------------------------------------------

#: A task with one state: `FIX_ON` on entering it, `CORRECT` 0.01 s later. No window, no
#: reward and no parameter, so every code its session strobes is one these tests name.
ONE_STATE_TASK = """
from wl_xcon.task import After, Mark, On, Outcome, State, Trial

trial = Trial(
    start="only",
    states=[State("only", enter=[Mark(4096)], go=[On(After(0.01), Outcome.CORRECT)])],
)
"""


def _escapes(codes: list) -> list:
    """Each `TRIAL_NUMBER` escape in a stream, as the four words from its escape word on.
    Found by the escape word alone, which holds for these tests' streams: a payload word
    is that value only for a trial numbered 0x8001 or more, and a checksum is only for
    trial 0, which no session strobes."""
    return [codes[i : i + 4] for i, code in enumerate(codes) if code == TRIAL_NUMBER_ESCAPE]


def test_each_trial_is_opened_numbered_and_closed_in_the_stream(tmp_path):
    """XC-155 spec §2.1, the whole stream of a `wlx run` session of two trials: after
    `HEAD_FIXED` and `RUN_START`, each trial is `TRIAL_START`, its number's escape --
    0x8001, the high word, the low word, and 0x8001 XOR both as the checksum -- then the
    task's own `FIX_ON`, the outcome marker (34, correct) and `TRIAL_END`; then
    `RUN_END` and `HEAD_RELEASED`."""
    task = tmp_path / "one_state.py"
    task.write_text(ONE_STATE_TASK)
    session = _session(_spec(tmp_path, trials=2, task=str(task), values={}))

    session.run()

    assert session.card.codes == [
        4128, RUN_START,
        TRIAL_START_CODE, TRIAL_NUMBER_ESCAPE, 0x0000, 0x0001, 0x8000, 4096, 34, TRIAL_END_CODE,
        TRIAL_START_CODE, TRIAL_NUMBER_ESCAPE, 0x0000, 0x0002, 0x8003, 4096, 34, TRIAL_END_CODE,
        RUN_END, 4129,
    ]
    assert [row["trial_number"] for row in _trial_rows(session)] == [1, 2]


def test_the_escapes_number_the_trials_across_runs_as_their_lines_do(tmp_path):
    """Spec §2.2, in the stream: the escapes of a `wlx taskd` session's two runs carry
    1 to 5, the numbers its lines carry, and a new session's first escape carries 1."""
    session = _service_session(tmp_path / "a")
    session.run(_run_spec(trials=3))
    session.run(_run_spec(trials=2))
    other = _service_session(tmp_path / "b")
    other.run(_run_spec(trials=1))

    assert _escapes(session.card.codes) == [
        [TRIAL_NUMBER_ESCAPE, 0x0000, number, TRIAL_NUMBER_ESCAPE ^ number]
        for number in range(1, 6)
    ]
    assert [row["trial_number"] for row in _trial_rows(session)] == [1, 2, 3, 4, 5]
    assert _escapes(other.card.codes) == [[TRIAL_NUMBER_ESCAPE, 0x0000, 0x0001, 0x8000]]


def test_nothing_is_strobed_inside_a_trial_numbers_escape(tmp_path):
    """S2 §6 item 3: an escape is atomic -- "no other code may be emitted between them,
    on any code path". wl-preproc reads the payload by position, so a word strobed
    inside it fails the checksum and loses the trial. Here a mark arrives at every
    check, each boundary's and every frame's, and a change is staged, so the loop
    strobes something everywhere it can; each trial's escape still goes out whole,
    straight after its `TRIAL_START`, with its boundary's mark before the trial opens
    and its first frame's after `FIX_ON`."""
    link = Simulated()
    link.marks.extend([5] * 100_000)
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    codes = session.card.codes
    opened = [i for i, code in enumerate(codes) if code == TRIAL_START_CODE]
    assert len(opened) == 3
    for number, at in enumerate(opened, start=1):
        assert codes[at - 1] == MARK_CODE, "the boundary's mark, before the trial opens"
        assert codes[at : at + 5] == [
            TRIAL_START_CODE, TRIAL_NUMBER_ESCAPE, 0x0000, number, TRIAL_NUMBER_ESCAPE ^ number,
        ]
        assert codes[at + 5 : at + 7] == [FIX_ON, MARK_CODE], "the first frame's, after"
    assert 4130 in codes, "the staged change was strobed at a boundary"


def test_a_trial_that_faults_is_opened_and_numbered_and_never_closed(tmp_path, monkeypatch):
    """Spec §2.1: a trial that faults strobes no `TRIAL_END` -- the card may be what
    failed -- and wl-preproc infers its end, as for any trial without one. Its opening
    and its number went out whole before its first frame, and nothing after them."""
    from wl_xcon import taskd

    real, calls = taskd.run_trial, []

    def faults_second(*args, **kwargs):
        calls.append(None)
        if len(calls) == 2:
            raise RuntimeError("the display went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", faults_second)
    session = _session(_spec(tmp_path, trials=3))

    with pytest.raises(RuntimeError, match="the display went away"):
        session.run()

    codes = session.card.codes
    assert codes[-5:] == [TRIAL_START_CODE, TRIAL_NUMBER_ESCAPE, 0x0000, 0x0002, 0x8003]
    assert (codes.count(TRIAL_START_CODE), codes.count(TRIAL_END_CODE)) == (2, 1)


def test_a_trial_that_reaches_no_outcome_is_still_closed(tmp_path, monkeypatch):
    """A trial `run_trial` returns from without an outcome -- a hang, which `check()`
    rules out for any task it passes -- strobes no outcome marker, and it still ended:
    `TRIAL_END` closes it, and its line records `hang`. The second trial runs whole, so
    the run's one trial is completed and the run ends."""
    from wl_xcon import taskd

    real, calls = taskd.run_trial, []

    def hangs_first(*args, **kwargs):
        calls.append(None)
        if len(calls) == 1:
            return real(*args, max_frames=1, **kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", hangs_first)
    task = tmp_path / "one_state.py"
    task.write_text(ONE_STATE_TASK)
    session = _session(_spec(tmp_path, trials=1, task=str(task), values={}))

    session.run()

    assert session.card.codes == [
        4128, RUN_START,
        TRIAL_START_CODE, TRIAL_NUMBER_ESCAPE, 0x0000, 0x0001, 0x8000, 4096, TRIAL_END_CODE,
        TRIAL_START_CODE, TRIAL_NUMBER_ESCAPE, 0x0000, 0x0002, 0x8003, 4096, 34, TRIAL_END_CODE,
        RUN_END, 4129,
    ]
    assert [row["outcome"] for row in _trial_rows(session)] == ["hang", "correct"]


def test_a_number_past_16_bits_is_strobed_whole_high_word_first(tmp_path):
    """Spec §2.2, the ceiling: the escape carries a uint32, and the session strobes the
    true number, never a truncated one -- a truncated number would name two trials in
    one recording. Trial 65,536 is the first whose high word is not 0. (Set on the
    counter directly: no test runs 65,535 trials to reach it.)"""
    task = tmp_path / "one_state.py"
    task.write_text(ONE_STATE_TASK)
    session = _session(_spec(tmp_path, trials=1, task=str(task), values={}))
    session._trial_number = 0xFFFF

    session.run()

    assert _escapes(session.card.codes) == [[TRIAL_NUMBER_ESCAPE, 0x0001, 0x0000, 0x8000]]
    assert [row["trial_number"] for row in _trial_rows(session)] == [65_536]


@_contract
def test_a_sessions_stream_assembles_in_wl_preproc_into_its_trials_numbered_across_runs(tmp_path):
    """XC-155 spec §4, the path and not the piece: a `wlx taskd` session's two runs on
    the simulated card, decoded by wl-preproc's `decode_stream` and assembled by its
    `assemble` -- the code that turns a recording into trials. One trial per trial run,
    numbered 1 to 43 across both runs, each with a start and a recorded end, nothing
    it could not decode; and every `trials.jsonl` line joins the assembled trial its
    `trial_number` names, whose outcome is the line's own. **Forty-three trials**, so
    trials 32 to 38 carry payload words equal to `TRIAL_START`, `TRIAL_END` and the
    outcome markers, and must be read as numbers."""
    session = _service_session(tmp_path)
    session.run(_run_spec(trials=3))
    session.run(_run_spec(trials=40, seed=5))
    session.end_runs("jake")

    stream = [(i * 0.001, word) for i, word in enumerate(session.card.codes)]
    assembly = their_assemble(their_events.decode_stream(stream))
    lines = _trial_rows(session)

    assert assembly.errors == []
    assert [trial.trial_id for trial in assembly.trials] == list(range(1, 44))
    assert [(line["run"], line["index"]) for line in lines] == [
        *[(0, index) for index in range(3)],
        *[(1, index) for index in range(40)],
    ]
    by_number = {line["trial_number"]: line for line in lines}
    assert sorted(by_number) == list(range(1, 44)), "one line for each number"
    for trial in assembly.trials:
        line = by_number[trial.trial_id]
        marker = their_events.Marker(session.allocation.outcomes[Outcome(line["outcome"])])
        assert trial.outcome == marker.name.removeprefix("TRIAL_").lower(), line
        assert trial.end_s is not None and trial.start_s < trial.end_s, line
```

**`tests/test_service.py`.** In `test_an_acknowledged_run_starts_records_who_acknowledged_what_and_ends_between_runs`, find:

```python
    codes = service.session.card.codes
    assert codes[:2] == [4128, 4135] and 4136 in codes and 4129 not in codes
```

Replace it with:

```python
    codes = service.session.card.codes
    assert codes[:3] == [4128, 4135, 32] and codes[-2:] == [33, 4136] and 4129 not in codes
```

In `test_e2e_open_a_session_run_it_twice_and_end_it`, find:

```python
    assert codes.count(4135) == codes.count(4136) == 2
    assert _kinds(root) == ["departure", "session opened", "returned", "session ended"]
```

Replace it with:

```python
    assert codes.count(4135) == codes.count(4136) == 2
    # Each of the six trials opened and closed in the stream (XC-155); numbered 1..6, so
    # no payload word is 32 or 33.
    assert codes.count(32) == codes.count(33) == 6
    assert _kinds(root) == ["departure", "session opened", "returned", "session ended"]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_taskd.py tests/test_service.py -q -p no:cacheprovider -rs`
Expected: **11 failed**, each because no trial marker or escape is strobed yet, and no skip:
- `test_a_run_is_strobed_where_it_starts_and_where_it_ends`: `codes[2]` is `FIX_ON`, not 32.
- `test_a_session_strobes_the_outcome_marker_the_allocation_gives`: no `TRIAL_END`, so `0 == 20`.
- The seven new tests.
- The two `test_service.py` tests: no 32 after `RUN_START`; no 32 or 33 counted.

The path test must **fail**, not skip. A skip means wl-preproc is not importable: stop and fix that first (`tests/conftest.py` says where it looks).

- [ ] **Step 3: Write the implementation**

In `wl_xcon/taskd.py`'s imports, find:

```python
from wl_xcon.codes import Allocation
from wl_xcon.dio import Absent as NoCard
```

Replace it with:

```python
from wl_xcon.codes import TRIAL_END, TRIAL_START, Allocation
from wl_xcon.dio import Absent as NoCard
from wl_xcon.encode import TRIAL_NUMBER, words_for
```

In `Session.run`'s loop, find what Task 2 wrote:

```python
                world = make_world(trial, values, index)
                # The trial's number, taken as it starts (`_trial_number`).
                self._trial_number += 1
                result = run_trial(
```

Replace it with:

```python
                world = make_world(trial, values, index)
                # **The trial opens in the stream at the boundary, never in a frame**
                # (XC-155; S1 §4's between-trial surface): `TRIAL_START`, then its number
                # (`_trial_number`, taken as it starts) in the `TRIAL_NUMBER` escape's
                # four words, from `encode.words_for`. **Unbroken** (S2 §6 item 3):
                # wl-preproc reads the payload by position, so a word strobed inside it
                # fails the checksum and loses the trial. The four go out here,
                # consecutively, on the loop's one thread: after everything this
                # boundary strobes, and before the trial's first frame.
                self._trial_number += 1
                self.card.emit(TRIAL_START)
                for word in words_for(TRIAL_NUMBER, self._trial_number):
                    self.card.emit(word)
                result = run_trial(
```

In the same loop, find:

```python
                    self.card.emit(self.allocation.outcomes[result.outcome])
                tally.add(result)
```

Replace it with:

```python
                    self.card.emit(self.allocation.outcomes[result.outcome])
                # **The trial closes after its outcome marker** (XC-155): `TRIAL_END`, for
                # every trial `run_trial` returned from -- one that reached no outcome (a
                # hang) ended too. A trial that raised never gets here and strobes none:
                # the card may be what failed, and wl-preproc infers its end
                # (`schema/events.py::_trial_stop_time`).
                self.card.emit(TRIAL_END)
                tally.add(result)
```

- [ ] **Step 4: Run the tests to see them pass, then the suite**

Run the Step 2 command again.
Expected: all pass, and no skip.

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider -rs`
Expected: all pass (2010 at validation), and no skip from `test_taskd.py`.

Run: `git diff c191784 -- wl_xcon/run.py | wc -l` (`c191784` is the tip this branch is stacked on).
Expected: `0`, since nothing in `run_trial` changed.

- [ ] **Step 5: Commit**

```bash
git add wl_xcon/taskd.py tests/test_taskd.py tests/test_service.py
git commit -m "Frame each trial in the stream with TRIAL_START, its number and TRIAL_END"
```

---

### Task 4: Say what changed, prove the tests can fail, and draft the reply to wl-preproc

**Files:**
- Modify: `docs/backlog.md`, `docs/design/architecture.md`, `wl_xcon/encode.py` (one comment), `tests/test_event_encoding.py` (one docstring)
- Create, **not committed**: `.superpowers/xc155/wl-preproc-reply.md` (git-ignored); the lane driver and its logs under a fresh `mktemp -d` directory
- **Do not edit `docs/CHECKPOINT.md`: the controller writes it** (Step 7 hands it what it needs). **Send nothing to wl-preproc.**

- [ ] **Step 1: The backlog, the architecture, and the "not yet" sentences**

**The next free ID.** The backlog's line `**Next free ID: XC-196.**` names the IDs this step takes: XC-196 and XC-197. If the line names a higher number, another branch has taken IDs first. Then use that number and the one after it, everywhere this plan says XC-196 and XC-197, the step's comment edits below included.

In `docs/backlog.md`, **delete** the XC-155 line (under "Deferred defects"), which is this whole line:

```markdown
- **XC-155** Emit the `TRIAL_NUMBER` (0x8001) escape at the start of every trial and `CONDITION` (0x8003) inside it, and record the condition's number in `trials.jsonl` beside its name: nothing calls `encode.words_for`, so a real session gives wl-preproc no trials at all (it identifies a trial by the stream's `TRIAL_NUMBER` alone and joins the record by it). **The number must be unique within the session**: since b3a-1 a session holds several runs and a run's trial index restarts, so it cannot simply be that index. **Tell wl-preproc the key field's name** when it is settled: since its `a2e2cf1` (branch `spec/nwb-publishing`) it joins no line of a `trials.jsonl` whose lines name a run, until it reads that key. — 2026-09-29, wl-preproc's report (its `docs/pending-wl-xcon-amendments.md`, NWB piece 2a); [`wl_xcon/encode.py`](../wl_xcon/encode.py) — waits on: nothing
```

Find the XC-173 line:

```markdown
- **XC-173** Rows written outside a run (a mark stamped between runs, the `end` control row, a mark after End) carry the last run's index and trial index, the shape of a row at that run's last boundary; decide what a row's `run` means with XC-155's join key. — 2026-09-30, [CHECKPOINT 2026-09-30, b3a-1](CHECKPOINT.md#what-moved-on-2026-09-30-p4d-2b-slice-b3a-1-the-session-service) — waits on: XC-155
```

Replace it with (it waits on nothing now, and names the key):

```markdown
- **XC-173** Rows written outside a run (a mark stamped between runs, the `end` control row, a mark after End) carry the last run's index and trial index, the shape of a row at that run's last boundary; decide what a row's `run` means beside XC-155's join key, each trial's `trial_number`. — 2026-09-30, [CHECKPOINT 2026-09-30, b3a-1](CHECKPOINT.md#what-moved-on-2026-09-30-p4d-2b-slice-b3a-1-the-session-service) — waits on: nothing
```

Under "Features not yet planned", find the XC-150 line:

```markdown
- **XC-150** P4d-2b b3b: the task-library pull from GitHub before a run, and the day's plan sent from wl-works that runs follow in order. — 2026-09-29, [P4d-2b spec §6](superpowers/specs/2026-09-26-P4d2b-browser-console-design.md#6-slice-b3a-sessions-from-the-page-approved-in-conversation-2026-09-29) — waits on: wl-xtasks holding tasks; wl-works sending plans
```

Replace it with itself and XC-196 after it:

```markdown
- **XC-150** P4d-2b b3b: the task-library pull from GitHub before a run, and the day's plan sent from wl-works that runs follow in order. — 2026-09-29, [P4d-2b spec §6](superpowers/specs/2026-09-26-P4d2b-browser-console-design.md#6-slice-b3a-sessions-from-the-page-approved-in-conversation-2026-09-29) — waits on: wl-xtasks holding tasks; wl-works sending plans
- **XC-196** Emit `CONDITION` (0x8003) inside every trial, and record its number in `trials.jsonl` beside the condition's name (wl-preproc's ask 2); decide then who numbers conditions, since every trial runs under one condition named "session" until the day's plan brings real ones. — 2026-09-30, the PI ("Wait until conditions exist"), [XC-155 spec §2.3](superpowers/specs/2026-09-30-xc155-trial-markers-design.md#23-not-in-this-change) — waits on: XC-150
```

At the end of "Waiting on another repository", find the XC-111 line:

```markdown
- **XC-111** wl-trajectortree: carry the three renames into its current code and docs once it is back on `main`. — 2026-09-28, [wl-orchestrator `d8b9ccb`](https://github.com/jakewesterberg/wl-orchestrator/commit/d8b9ccb) — waits on: wl-trajectortree's branch `polish-the-last-five` merging
```

Replace it with itself and XC-197 after it:

```markdown
- **XC-111** wl-trajectortree: carry the three renames into its current code and docs once it is back on `main`. — 2026-09-28, [wl-orchestrator `d8b9ccb`](https://github.com/jakewesterberg/wl-orchestrator/commit/d8b9ccb) — waits on: wl-trajectortree's branch `polish-the-last-five` merging
- **XC-197** wl-preproc: whether one sync-box recording can hold two wl-xcon sessions (two animals on a rig in a day), in which case each session's trial numbers from 1 collide in its stream and must be unique across the rig's day instead; and its `trial_id` is a `smallint` (to 32,767), below the uint32 the stream carries. Asked with XC-155's field name. — 2026-09-30, [XC-155 spec §3](superpowers/specs/2026-09-30-xc155-trial-markers-design.md#3-told-to-wl-preproc-once-built) — waits on: sending it, then wl-preproc
```

Find:

```markdown
**Next free ID: XC-196.**
```

Replace it with:

```markdown
**Next free ID: XC-198.**
```

In `docs/design/architecture.md`, under "Message contracts (draft v0)", find:

```markdown
- **Hardware truth:** every trial event gets a strobed word into the recorders and a JSONL
  record carrying the word, frame index and monotonic time.
```

Replace it with:

```markdown
- **Hardware truth:** every trial event gets a strobed word into the recorders and a JSONL
  record carrying the word, frame index and monotonic time. **Each trial is framed in the
  stream** (XC-155): `TRIAL_START` (32) and its `TRIAL_NUMBER` escape (`0x8001`, four words,
  unbroken) at the boundary before its first frame, and `TRIAL_END` (33) after its outcome
  marker, or none after a trial that faults. The number counts from 1 across a session's
  runs and is the trial's `trial_number` in `trials.jsonl`, the field wl-preproc joins a line
  to its recorded trial by. `CONDITION` is not emitted yet (XC-196).
```

Two "not yet" sentences from Task 1 can now name XC-196 (CLAUDE.md: name what a "not yet" waits for, so it can be grepped). In `wl_xcon/encode.py`, find:

```python
#: strobes each trial's number behind `TRIAL_NUMBER` (XC-155). `CONDITION` is framed
#: here and emitted by nothing yet: it waits on the conditions the day's plan brings
#: (XC-150), and on who numbers them, decided then.
```

Replace it with:

```python
#: strobes each trial's number behind `TRIAL_NUMBER` (XC-155). `CONDITION` is framed
#: here and emitted by nothing yet (XC-196): it waits on the conditions the day's plan
#: brings (XC-150), and on who numbers them, decided then.
```

In `tests/test_event_encoding.py`, find:

```python
    **`CONDITION` too, although nothing emits it yet** (it waits on the conditions the
    day's plan brings, XC-150): `words_for` has framed it since it was written, and no
    test read that framing against theirs until XC-155.
```

Replace it with:

```python
    **`CONDITION` too, although nothing emits it yet** (XC-196, which waits on the
    conditions the day's plan brings, XC-150): `words_for` has framed it since it was
    written, and no test read that framing against theirs until XC-155.
```

**The other "not yet" sentences.** Run: `git grep -n -e "XC-155" -e "called by nothing" -e "nothing calls" -e "no trials at all" -e "not emitted" -e "nothing emits" -e "emitted by nothing" -- wl_xcon tasks tests docs/design docs/backlog.md docs/pitfalls.md docs/roadmap.md docs/superpowers/specs/2026-08-31-S2-event-vocabulary-design.md`

Expected hits, all true after this change:
- comments and docstrings that say what XC-155 did, in `codes.py`, `encode.py`, `record.py`, `taskd.py` and the tests;
- `encode.py`'s and `test_event_encoding.py`'s `CONDITION` sentences, naming XC-196;
- `architecture.md`'s new paragraph;
- XC-173, XC-196 and XC-197 in the backlog;
- unrelated hits about other code: `link.py`'s `drain()`, `cli.py`'s `close()`, and a guardrail nothing called in `welfare.py`, `architecture.md`, `pitfalls.md` (P21), `test_welfare.py` and `test_taskd.py` (`check_delivery`).

Nothing in the S2 spec is hit: S2 says nothing about when the markers are emitted, so no "not yet" there has become true, and it is not edited. Rewrite any other hit that describes this work as still to come. A hit in `docs/superpowers/` other than S2 is a dated record and stays.

Run: `python3 -m pytest tests/test_backlog.py -q -p no:cacheprovider`
Expected: PASS.

```bash
git add docs/backlog.md docs/design/architecture.md wl_xcon/encode.py tests/test_event_encoding.py
git commit -m "Record the trial markers and close XC-155's number half (closes XC-155)"
```

- [ ] **Step 2: The whole suite, three times**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider -rs` three times in a row.
Expected: all pass each time, with no skip. Note the passed count for Step 7 (2010 at validation).

- [ ] **Step 3: The welfare-critical surface and the frames are untouched**

`c191784` is b3a-2's tip, which this branch is stacked on. If the branch has been rebased, use `git merge-base HEAD main` instead, once `main` holds b3a-2.

```bash
BASE=c191784
git diff --stat "$BASE" -- wl_xcon tasks
git diff "$BASE" -- wl_xcon/run.py wl_xcon/welfare.py wl_xcon/bounds.py wl_xcon/marks.py wl_xcon/stranded.py wl_xcon/preflight.py wl_xcon/service.py wl_xcon/link.py wl_xcon/cli.py | wc -l
```

Expected:
- The first command lists exactly `wl_xcon/codes.py`, `wl_xcon/encode.py`, `wl_xcon/record.py`, `wl_xcon/simulate.py` and `wl_xcon/taskd.py`.
- The second prints `0`. `run.py` is in that list: nothing in `run_trial`'s frames changed.

```bash
python3 - <<'EOF'
import ast, subprocess
BASE = "c191784"
def members(text):
    """`Session`'s methods, and `OUTSIDE_A_RUN`, as their ASTs."""
    found = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef) and node.name == "Session":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    found[item.name] = ast.dump(item)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if getattr(target, "id", None) == "OUTSIDE_A_RUN":
                    found["OUTSIDE_A_RUN"] = ast.dump(node)
    return found
old = members(subprocess.run(["git", "show", f"{BASE}:wl_xcon/taskd.py"], capture_output=True, text=True, check=True).stdout)
new = members(open("wl_xcon/taskd.py").read())
print("changed:", sorted(name for name in old if old[name] != new.get(name)))
print("added:", sorted(set(new) - set(old)))
for name in ("_ends", "_hold", "_manual_reward", "set", "_schedule", "_command", "OUTSIDE_A_RUN"):
    print(("ok " if old[name] == new[name] else "BAD"), name)
EOF
```

Expected: `changed: ['run']`, `added: []`, and seven `ok` lines. Anything else is a change nobody ruled on: revert it.

- [ ] **Step 4: Draft the reply to wl-preproc (not sent)**

It answers wl-preproc's ask in its `docs/pending-wl-xcon-amendments.md` ("OPEN — the stream must carry each trial's number and condition"). It asks the two questions of spec §3. **The controller sends it once this branch is on `main`; do not send it, and do not edit anything in wl-preproc.**

```bash
mkdir -p .superpowers/xc155
cat > .superpowers/xc155/wl-preproc-reply.md <<'EOF'
# From wl-xcon: XC-155 is built, and the field is `trial_number`

**To wl-preproc**, answering its `docs/pending-wl-xcon-amendments.md`, "OPEN — the stream must
carry each trial's number and condition", ask 1. From wl-xcon, 2026-09-30. Nothing here asks
you to change code. Items 2 and 3 are questions.

## 1. The field is `trial_number`

- **Every line of `xcon/trials.jsonl` now carries `trial_number`.** It is an integer, counted
  from 1 across the whole wl-xcon session, whichever run the trial is in. It equals the
  `TRIAL_NUMBER` (`0x8001`) payload strobed after that trial's `TRIAL_START`.
- `index` and `run` stay on every line beside it, per run. A run's `index` still restarts at 0.
- **The number is unique within one wl-xcon session**: one session id, one `xcon/` folder.
  - A new session starts again at 1.
  - A service restarted after a crash opens a new session. Carrying the numbering across a
    restart is our XC-026, not built.
- **The stream around every trial now reads:**

        TRIAL_START (32)
        TRIAL_NUMBER: 0x8001, high word, low word, XOR checksum      (4 words, unbroken)
        ... the task's own codes ...
        the outcome marker (34-38)
        TRIAL_END (33)

  - Both ends are strobed at the trial boundary, never inside a frame.
  - Nothing is strobed between the escape and its checksum, on any path.
  - `RUN_START` (4135) and `RUN_END` (4136) still bound each run.
- **Two cases your join will meet:**
  - **A trial that faults.** It strobes its `TRIAL_START` and its number, then nothing: no
    outcome marker, no `TRIAL_END`, and no `trials.jsonl` line. Your `assemble` gives it
    `outcome=None, end_s=None`, and your join finds no line for it. Its number is never
    reused, so the numbering has a gap there.
  - **A trial that ends with no outcome** (a hang, which our load-time checks rule out for
    any task they pass). It strobes `TRIAL_END` and no outcome marker, and its line's
    `outcome` is `"hang"`.
- **No `CONDITION` yet** (your ask 2).
  - Every trial today runs under one condition named `"session"`. The day's plan that brings
    real conditions is not built (our XC-150).
  - We will emit `CONDITION`, and record its number beside the condition's name, once
    conditions exist. Their numbering is decided then (our XC-196).
  - Until then your `nwb/conditions.py` takes names from `trials.jsonl`, as it does today.
- **No `BLOCK_START`/`BLOCK_END`.** wl.works asked you, in its message of 2026-09-30, to take
  our runs as your blocks, from `RUN_START` and `RUN_END`.
- **How we checked it.** We ran a session's stream through your own `decode_stream` and
  `assemble`, read at your `main` `da95dd9`. The stream came from our simulated card, over
  two runs and 43 trials, so trials 32-38 carry payload words equal to your markers' values.
  - The result: one trial per trial run, numbered 1-43, each with its outcome and a recorded
    end, and no decode error.
  - Every line joined its trial by `trial_number`.
  - The test is our `tests/test_taskd.py::test_a_sessions_stream_assembles_in_wl_preproc_into_its_trials_numbered_across_runs`.

## 2. A question: can one sync-box recording hold two wl-xcon sessions?

For example, a morning animal and an afternoon animal on one rig, if the sync box's session
spans the day.

- Your `populate_session` decodes a session directory's whole sync-box log with no split by
  subject (`schema/events.py:339-343`).
- `nwb/gather.py:71-77` says two animals can share one sync-box session id.
- If one stream can hold two of our sessions, both number their trials from 1. Then the
  second trial with each number is dropped silently at `Trial.insert(...,
  skip_duplicates=True)` (`schema/events.py:476`).
- In that case our numbers would have to be unique across a rig's day instead.

Your answer decides which (our XC-197).

## 3. The ceiling

Your trial key is element-event's `trial_id : smallint` (`element_event/trial.py:146-153`).
So a trial number above 32,767 fits the stream's uint32 but not your table. We did not
check what your database does then.

We keep counting and strobe the true number, because truncating it would make two trials
share a number. A session would reach it only if it were long and its task fast.

Written from wl-xcon's branch `xc155-trial-markers`, at the commit below; the controller
checks it is on `main` before sending:
EOF
git rev-parse --short HEAD >> .superpowers/xc155/wl-preproc-reply.md
git status --short .superpowers
```

Expected: `git status` prints nothing, because `.superpowers/` is git-ignored. Read the file through once. The last line, the tip's short SHA, is where the reply was written from; the controller checks that commit is on `main` before sending.

- [ ] **Step 5: Prove the tests can fail: every new and changed function, and every new line**

**Never run the suite, edit a test or `git add` while a lane is running**: the harness changes a module's file in place. Each lane is its own `git archive` copy of the branch tip, in a fresh directory, with `wl-preproc` linked inside it (`tests/conftest.py` looks there) and `PYTHONPATH` set to the copy.

Each lane takes one baseline, then runs its targets in turn, then takes one restore:
- a function, neutered by the copy's own `tools/mutate.py`;
- or a line mutant from the driver's `LINES` table, checked to parse before the suite runs (CLAUDE.md: a `SyntaxError` must never do the reporting).

Nothing here removes a directory: each run makes a new one with `mktemp -d`.

```bash
tip=$(git rev-parse HEAD)
# The checkout beside the main one (a worktree's parent is not it).
PREPROC="$(dirname "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")/wl-preproc"
test -d "$PREPROC/wl_preproc" || echo "STOP: no wl-preproc checkout at $PREPROC"  # if printed, stop here
LANES=$(mktemp -d "${TMPDIR:-/tmp}/xc155-lanes.XXXX")
echo "$LANES"
cat > "$LANES/drive.py" <<'DRIVE'
"""XC-155's mutation proof in one `git archive` lane: one baseline, then each target in
turn -- a function neutered by the copy's own `mutate()`, or one line mutant from
`LINES` -- then one restore. Every line mutant is checked to parse before the suite
runs (CLAUDE.md: a `SyntaxError` must never do the reporting)."""
import ast
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "tools"))
import mutate  # noqa: E402 -- the copy's own, so its ROOT is the copy

#: label -> (module file, [(exact old text, new text), ...]); each old text must occur
#: exactly once in the file.
LINES = {
    "L01-no-trial-start": ("wl_xcon/taskd.py", [
        ("                self.card.emit(TRIAL_START)\n", ""),
    ]),
    "L02-no-escape": ("wl_xcon/taskd.py", [
        ("                for word in words_for(TRIAL_NUMBER, self._trial_number):\n"
         "                    self.card.emit(word)\n", ""),
    ]),
    "L03-escape-before-trial-start": ("wl_xcon/taskd.py", [
        ("                self.card.emit(TRIAL_START)\n"
         "                for word in words_for(TRIAL_NUMBER, self._trial_number):\n"
         "                    self.card.emit(word)\n",
         "                for word in words_for(TRIAL_NUMBER, self._trial_number):\n"
         "                    self.card.emit(word)\n"
         "                self.card.emit(TRIAL_START)\n"),
    ]),
    "L04-a-mark-inside-the-escape": ("wl_xcon/taskd.py", [
        ("                    self.card.emit(word)\n",
         "                    self.card.emit(word)\n"
         "                    self._check_marks(index)\n"),
    ]),
    "L05-no-trial-number-increment": ("wl_xcon/taskd.py", [
        ("                self._trial_number += 1\n", ""),
    ]),
    "L06-no-trial-end": ("wl_xcon/taskd.py", [
        ("                self.card.emit(TRIAL_END)\n", ""),
    ]),
    "L07-trial-end-before-the-outcome": ("wl_xcon/taskd.py", [
        ("                self.card.emit(TRIAL_END)\n", ""),
        ("                if result.outcome is not None:\n",
         "                self.card.emit(TRIAL_END)\n"
         "                if result.outcome is not None:\n"),
    ]),
    "L08-trial-end-only-with-an-outcome": ("wl_xcon/taskd.py", [
        ("                self.card.emit(TRIAL_END)\n",
         "                if result.outcome is not None:\n"
         "                    self.card.emit(TRIAL_END)\n"),
    ]),
    "L09-trial-end-after-a-fault": ("wl_xcon/taskd.py", [
        ('            self.stop_kind = "fault"\n            publish()\n',
         '            self.stop_kind = "fault"\n'
         "            self.card.emit(TRIAL_END)\n"
         "            publish()\n"),
    ]),
    "L10-number-reset-with-each-run": ("wl_xcon/taskd.py", [
        ("        self.scheduled_stop = None\n        self._recent.clear()\n",
         "        self.scheduled_stop = None\n        self._recent.clear()\n"
         "        self._trial_number = 0\n"),
    ]),
    "L11-line-numbered-by-its-index": ("wl_xcon/taskd.py", [
        ("                    trial_number=self._trial_number,\n",
         "                    trial_number=index + 1,\n"),
    ]),
    "L12-trial-number-defaulted": ("wl_xcon/record.py", [
        ("        trial_number: int,\n    ) -> None:", "        trial_number: int = 0,\n    ) -> None:"),
    ]),
    "L13-trial-number-not-written": ("wl_xcon/record.py", [
        ('                    "trial_number": trial_number,\n', ""),
    ]),
    "L14-census-numbered-from-0": ("wl_xcon/simulate.py", [
        ("                trial_number=index + 1,\n", "                trial_number=index,\n"),
    ]),
    "L15-trial-start-value": ("wl_xcon/codes.py", [
        ("TRIAL_START = 32\n", "TRIAL_START = 31\n"),
    ]),
    "L16-trial-end-value": ("wl_xcon/codes.py", [
        ("TRIAL_END = 33\n", "TRIAL_END = 39\n"),
    ]),
    "L17-trial-number-escape-value": ("wl_xcon/encode.py", [
        ("TRIAL_NUMBER = 0x8001\n", "TRIAL_NUMBER = 0x8003\n"),
    ]),
    "L18-condition-escape-value": ("wl_xcon/encode.py", [
        ("CONDITION = 0x8003\n", "CONDITION = 0x8004\n"),
    ]),
}


def line_mutant(label):
    """Apply one line mutant, run the suite, restore. `(caught, summary)`, or `None` and
    why when the mutant cannot be applied as written."""
    relative, edits = LINES[label]
    path = root / relative
    original = path.read_text()
    mutated = original
    for old, new in edits:
        found = mutated.count(old)
        if found != 1:
            return None, f"its text is found {found} times in {relative}, not once"
        mutated = mutated.replace(old, new)
    try:
        ast.parse(mutated)
    except SyntaxError as error:
        return None, f"the mutant does not parse ({error}); fix the mutant, not the code"
    try:
        path.write_text(mutated)
        mutate.SENTINEL.write_text(
            json.dumps({"path": str(path), "original": original, "mutated": mutated})
        )
        passed, summary, failures = mutate._run_suite()
        return not passed, summary + mutate._caught_by(failures)
    finally:
        path.write_text(original)
        mutate.SENTINEL.unlink(missing_ok=True)
        mutate._clear_pycache()


mutate._restore_any_interrupted_run()
ok, baseline, failures = mutate._run_suite()
print(f"baseline: {baseline}", flush=True)
if not ok:
    print("\n".join(failures))
    raise SystemExit(1)
for line in sys.stdin:
    words = line.split()
    if not words:
        continue
    if words[0] == "fn":
        _, module, name, returns = words
        caught, summary = mutate.mutate(root / "wl_xcon" / f"{module}.py", name, returns)
        target = f"{module}.{name}"
    else:
        target = words[1]
        caught, summary = line_mutant(target)
    label = (
        "SKIPPED" if caught is None
        else "inert" if caught == mutate.INERT
        else "caught" if caught
        else "SURVIVED"
    )
    print(f"  {label:9} {target:36} {summary}", flush=True)
ok, restored, failures = mutate._run_suite()
print(f"restored: {restored}", flush=True)
print("\n".join(failures))
DRIVE
lane() {  # lane NAME, then "fn module function returns" or "line LABEL" lines on stdin
  dir="$LANES/$1"
  mkdir "$dir"
  git archive "$tip" | tar -x -C "$dir"
  ln -s "$PREPROC" "$dir/wl-preproc"
  (cd "$dir" && PYTHONPATH="$dir" WLX_REQUIRE_PREPROC=1 python3 "$LANES/drive.py" "$dir") \
    > "$LANES/$1.txt" 2>&1
}
lane functions <<'EOF' &
fn taskd run None
fn record trial None
fn simulate simulate None
fn encode words_for []
EOF
lane open <<'EOF' &
line L01-no-trial-start
line L02-no-escape
line L03-escape-before-trial-start
line L04-a-mark-inside-the-escape
line L05-no-trial-number-increment
EOF
lane close <<'EOF' &
line L06-no-trial-end
line L07-trial-end-before-the-outcome
line L08-trial-end-only-with-an-outcome
line L09-trial-end-after-a-fault
line L10-number-reset-with-each-run
EOF
lane record <<'EOF' &
line L11-line-numbered-by-its-index
line L12-trial-number-defaulted
line L13-trial-number-not-written
line L14-census-numbered-from-0
EOF
lane values <<'EOF' &
line L15-trial-start-value
line L16-trial-end-value
line L17-trial-number-escape-value
line L18-condition-escape-value
EOF
wait
for f in functions open close record values; do echo "== $f"; cat "$LANES/$f.txt"; done
```

`encode` takes `[]`, as `tools/mutation_gate.py`'s `RETURNS` has it; the others take `None`. `codes.py`'s functions are unchanged; its two new values are line mutants L15 and L16.

Then **read every line of every lane's file, not its exit code**:
- Every target reads `caught`, with `N failed` and a `<-` naming tests about it. `N errors in 0.Ns`, a timeout, or one unrelated test is not a catch (CHECKPOINT, trap 7).
- Zero `SURVIVED`, zero `SKIPPED`. A `SKIPPED` line mutant means its text was not found once or did not parse: fix the mutant's text in the driver, never the code.
- The `baseline:` and `restored:` lines both read the suite's own passed count.

At validation, the tests that caught each line mutant were:

The lanes print three names per target. The rest of each list below was read by name from a
separate run of the same mutant.

| Target | At validation | Tests it failed |
|---|---|---|
| `taskd.run` | 247 failed | every session test |
| `record.trial` | 33 failed | `test_record.py`'s trial tests, and every session test that writes a trial's line |
| `simulate.simulate` | 12 failed | `test_a_simulated_session_writes_a_real_session_directory` and the census tests |
| `encode.words_for` | 20 failed | the round trip, both escapes' framing cases, and the stream tests |
| L01 no `TRIAL_START` | 7 failed | the two tightened lists (`test_a_run_is_strobed_where_it_starts_and_where_it_ends`, `test_an_acknowledged_run_starts_records_who_acknowledged_what_and_ends_between_runs`), `test_e2e_open_a_session_run_it_twice_and_end_it`, and the whole-stream, unbroken, fault and hang tests |
| L02 no escape | 7 failed | the whole-stream, escapes-across-runs, unbroken, fault, hang, 16-bit and path tests |
| L03 escape before `TRIAL_START` | 7 failed | the two tightened lists, and the whole-stream, unbroken, fault, hang and path tests |
| L04 a mark inside the escape | 4 failed | **`test_nothing_is_strobed_inside_a_trial_numbers_escape`**, and three mark tests whose mark counts it doubles |
| L05 the number never advanced | 12 failed | every `trial_number` test (`test_record.py`'s aside), the `wlx run` and `wlx taskd` paths, and every stream test |
| L06 no `TRIAL_END` | 8 failed | the two tightened lists, the e2e test, the outcome-marker test, and the whole-stream, fault, hang and path tests |
| L07 `TRIAL_END` before the outcome | 6 failed | `test_a_session_strobes_the_outcome_marker_the_allocation_gives`, the two tightened lists, and the whole-stream, hang and path tests |
| L08 `TRIAL_END` only with an outcome | 1 failed | `test_a_trial_that_reaches_no_outcome_is_still_closed` |
| L09 `TRIAL_END` after a fault | 2 failed | `test_a_trial_that_faults_is_opened_and_numbered_and_never_closed`, `test_a_pump_that_fails_a_manual_reward_faults_the_session_as_a_tasks_would` |
| L10 the number reset with each run | 6 failed | `test_each_trial_line_carries_its_number_counted_across_the_sessions_runs`, `test_a_trial_that_faults_keeps_its_number_and_the_next_trial_never_reuses_it`, and the escapes-across-runs, 16-bit, path and e2e tests |
| L11 a line numbered by its index | 6 failed | the same six |
| L12 `trial_number` defaulted | 1 failed | `test_a_trial_row_is_never_written_without_its_trial_number` |
| L13 `trial_number` not written | 11 failed | every test that reads a line's `trial_number` |
| L14 the census numbered from 0 | 1 failed | `test_a_simulated_session_writes_a_real_session_directory` |
| L15 `TRIAL_START`'s value | 8 failed | `test_every_marker_codes_mirrors_is_theirs`, and each test that writes 32 as a literal. **Not the path test**: wl-preproc's `assemble` opens a trial at its `TRIAL_NUMBER` when no `TRIAL_START` came first, which is why the unit tests write the codes as literals (Plan decision 8). |
| L16 `TRIAL_END`'s value | 9 failed | the mirror test, and each test that writes 33 as a literal, the path test among them |
| L17 `TRIAL_NUMBER`'s value | 15 failed | the round trip, the six `TRIAL_NUMBER` framing cases, `test_the_escapes_the_rig_names_are_theirs`, and every stream test |
| L18 `CONDITION`'s value | 7 failed | the six `CONDITION` framing cases, and `test_the_escapes_the_rig_names_are_theirs` |

A survivor is a missing test. Write it in the owning task's test file and commit it, with no lane running. Then re-run that target alone in a fresh lane (a new `mktemp -d`). A target no test can catch is deleted, not exempted. Re-run a `timed out` line alone before it is believed or blamed.

- [ ] **Step 6: The branch is ready for its whole-branch review**

Run: `git status --short` (expect nothing) and `git log --oneline c191784..HEAD` (expect the spec's commit and this plan's four task commits, plus any survivor fix from Step 5).

- [ ] **Step 7: Hand the controller what CHECKPOINT needs**

Report, for the controller to write (do not edit `docs/CHECKPOINT.md`):
- the passed count (Step 2); each lane's result (Step 5), with any survivor found and how it was closed; and Step 3's output;
- what was filed (XC-196, XC-197, or the IDs they became) and closed (XC-155), and that XC-173 waits on nothing now;
- that `.superpowers/xc155/wl-preproc-reply.md` is drafted and unsent, and what it asks (spec §3's questions 2 and 3);
- that the branch merges after b3a-2 reaches `main`, by fast-forward, once CI's push run is read shard by shard;
- **no welfare-critical change, so no PI welfare review** (Step 3).
