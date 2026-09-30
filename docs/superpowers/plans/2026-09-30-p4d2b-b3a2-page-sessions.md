# P4d-2b Slice b3a-2 — Sessions From the Page: `POST /commands` Takes the Service's Commands, the Page's Forms to Open, Check, Start and End, the Question's Answers, a Run From the Task's Own Values, and the Hand Reward Between Runs: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Execution: subagent-driven**, the method this project uses (b1, b2a, direct view, b3a-1): a fresh implementer per task and a fresh reviewer before the next one starts, then a whole-branch review on the most capable model. Tasks 2 and 5 change welfare-critical code (Task 5 only the words of one sentence in `welfare.py`): implement and review both on the most capable model.
>
> **Branch from `main` as `p4d2b-b3a2-page-sessions`, once `main` holds b3a-1** (`wl_xcon/service.py` exists on `main`, and so does `e51e343`, the page's name `xcon`; if either is missing, b3a-1 has not been fast-forwarded yet: stop and say so).
>
> **Validated before hand-off** (2026-09-30, on a `git archive` copy of b3a-1's tip with `e51e343`, never a checkout): Tasks 1-7's code and tests, applied from this plan's own code blocks, pass -- the suite at 1946 with Task 5's two `test_welfare.py` tests, the six `page_e2e` tests three runs in a row, and `serve.parse_command` neutered failing them in about a minute -- and the page was driven in a real browser against a real `wlx taskd` and `wlx serve`: open, pre-flight, acknowledge, start, a hand reward between runs, end, a far return confirmed and refused, re-typed and taken, and a far departure amended, with no console error.
>
> **Approved by the PI on 2026-09-30** ("Approve, build it", asked in the question UI with its three findings stated), to be built task by task with reviews ("Task by task with reviews").
>
> **Welfare-critical code changes, listed in Plan decision 16 and Task 8 Step 4.** The branch merges only after the PI approves Task 8's numbered summary (P4d-2b spec §6.4; CLAUDE.md).
>
> **Every commit** ends with the session's attribution lines, as the repository's history does.

**Goal:** A person at the rig PC opens a session, checks and starts each run, answers a far mark's warning, gives a hand reward between runs and while the return is awaited, and ends the session in two steps -- all from the browser console, through `wlx serve`'s `POST /commands` to `wlx taskd`, under the terminal's exact rules and S9a §10's pre-flight rule, with every run starting from its task's own values.

**Architecture:** `link.py`'s decoder is split so one function (`_command_from`) builds a command from its fields for the wire and for `serve.parse_command` alike; `wlx serve` accepts `open`, `check`, `start` and `end` under §2's four checks and answers them as it answers b2a's commands. `web.py` renders the new panes in Python -- the task chooser's options, the pre-flight pill and panel with one acknowledgement per unknown item, *start run*, the hand reward outside a run, the question's answer buttons, *end session* and *record return…*, a stranded animal's *end session…*, and the idle page's *new session* -- and holds every field a person types in static forms (the *New session* dialog, the end confirmation, the return, the amendment) that no frame replaces; the page's script sends each form as one JSON command and re-sends a typed time with the answer to the warning it raised. `taskd.Session._manual_reward` decides by phase whether a press is given, so a `wlx taskd` session gives one between runs and while its return is awaited. `task.Param` gains `start`, the task's own starting value, which a run starts from under what it was given.

**Tech Stack:** Python 3.11–3.13; the stdlib `ThreadingHTTPServer` and `json`; ZeroMQ and msgpack (unchanged, ADR-0003); the page's one inline script (no framework, no new dependency); pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §6 (slice b3a: §6.0's rulings, the manual-reward ruling among them; §6.1–§6.6), with §2 and §5.0–§5.3 for how b2a's controls reach the rig; the design mockup `docs/superpowers/mockups/2026-09-26-console-mockup-v12.html` (its `dlg-new`, `pf-panel`, `pf-pill`, `a-start`, `a-stop`, `a-end`, `end-confirm`); `docs/superpowers/specs/2026-08-31-S9a-console-design.md` §10 (the pre-flight rule); `docs/superpowers/specs/2026-08-31-S8-session-management-design.md` §3.4 (the task layer); the b3a-1 plan, `docs/superpowers/plans/2026-09-29-p4d2b-b3a1-session-service.md`, whose commands, frames and decisions this builds on.

## Questions for the PI

**None.** Every choice here that touches an animal is settled by a ruling (spec §6.0, including "whenever the console is up, the manual reward should work" and where each part of it is built) or by b3a-1's approved decisions; the engineering calls are below. Three findings the controller should put in front of the PI with Task 8's summary rather than as questions, since the plan builds what the spec says or fixes what the code got wrong:

- **"Starting values are the task's own" (spec §6.2) had nothing to stand on: no task declares a value.** A run started from the page with no values faults at its first trial ("no value bound for parameter 'fix_timeout'", probed on the b3a-1 branch). Plan decision 1 builds what the spec, S8 §3.4's *task* layer and the mockup's "start values: task defaults" all describe: `Param.start`, with `fixation_detection`'s values the mockup shows (Task 1).
- **A pump failure on a hand reward outside a run ends `wlx taskd`**, as any unexpected failure between runs does since b3a-1 (its decision 14); the session is recorded as returned-not-recorded and the stranded rule holds the next start (Plan decision 4). Only the simulated pump exists today. It is Task 8's summary item 4, for the PI to approve or change.
- **A far return's warning offered an amendment the rig refuses.** `welfare.Welfare._far_from_now` ended every far mark's sentence with "Confirm it, or amend it with a reason", and `return_needs_confirmation` calls it for the return too, which has no amendment (spec §6.2; the terminal and the page take a confirmation or the time typed again). Seen on the page while this plan was validated, and ruled by the controller on 2026-09-30: fixed here, words only -- the return's sentence reads "Confirm it, or type it again", the departure's is byte-identical, and the rule is unchanged (Task 5; Plan decision 16). It is Task 8's summary item 6.

## Plan decisions

The spec left these to the plan. Each is taken here with its reason, and the code is in the task named.

1. **A run starts from its task's own values, under the ones it is given** (Task 1). `task.Param` gains `start` (default `None`); `Session.run` starts a run's values from every declared `start`, with the run's own values over them -- for `wlx taskd`'s runs and `wlx run`'s alike -- and its `runs.jsonl` start row records the two layers apart, `{"task": ..., "run": ...}`, as S8 §3.4's precedence asks ("the layers are recorded too, so a value's origin is recoverable"). Spec §6.2 says "Starting values are the task's own"; the mockup the PI reviewed shows "start values: task defaults" with `fixation_detection`'s values (`TASKS.fixation_detection.params`: 4.0, 0.30, 0.60, 0.20, 2.0, 3.0), which are the values every end-to-end test has run it at (`_TASK_SETS`, with `target_position` 10.0, the mockup's target). `fixation_detection` declares those; the other three reference tasks declare none yet, so the page's pre-flight refuses their runs naming each missing value (decision 2) until they do -- filed as **XC-183** in Task 1. `wlx run` now takes a task's `start` where `--set` gave nothing, and checks it no more than it checks `--set` (XC-159). The page sends no values (`values: {}`); remembering an animal's values stays with XC-018.
2. **The pre-flight fails a number a task uses that nothing gives a value** (Task 1). `preflight.values` checks the merged values -- the task's `start`s with what was sent over them -- as it checked what was sent, and fails each parameter the task references (`check.parameters_used`, new) that is a number -- declared with no `choices` -- and has no value, naming it. Without this the start passes, `RUN_START` is strobed and the run faults at its first trial; with it the start is refused first (Review Focus 2). A categorical parameter left unset is not refused: it is an appearance, and nothing in this build resolves one before a trial needs it (S4's display is not built), which is why every test has run `fixation_detection` with `target_looks` unset.
3. **The page's four session commands go through `POST /commands` exactly as b2a's commands do** (Task 3): §2's four checks, `NAME (box, unverified)`, the command thread's REQ socket, *sent* / *not delivered* / *busy*. They are built by the wire's own function -- `link._command_from`, split out of `_decode_command` -- so a page's body is checked by exactly the rules the rig checks the packet by, and a malformed one is a 400 with the wire's sentence, never a traceback (Review Focus 3). *Sent* for one of them says what the page will show next (`serve.SERVICE_SENT`), since "acts on it at its next trial boundary" is b2a's sentence for a run's command and is not true of an open between runs.
4. **The hand reward between runs and while the return is awaited** (Task 2; spec §6.0, PI 2026-09-29). `Session._command` hands every `ManualReward` to `_manual_reward` first, in every phase -- the `held` pass-through, moved ahead of the post-loop refusal it used to follow -- and `_manual_reward` decides by phase: **during a run** only while held paused, unchanged (a press during a trial is XC-157's); **in a `wlx taskd` session between runs or awaiting its return**, given, with no pause to hold, since no trial runs and no task rewards; **anywhere else** refused with a sentence. A "stop after X mL" is not asked outside a run: a scheduled stop belongs to the run it was set on (spec §6.1), and outside a run there is none to end. **`wlx run`'s session after its run is refused**, although the ruling's "awaiting the return" covers it: its return is typed at the terminal on the main thread while `await_return` drains the link on another, so a reward drained there could be given after the return is recorded -- fluid counted to an animal already home. Filed as **XC-184** in Task 2. **A pump fault on a reward outside a run is not caught**, as `welfare.Rig` catches none for a task's reward: it ends `wlx taskd`, which records the session as returned-not-recorded, and the stranded rule holds the next start (b3a-1 decision 14's rule for anything unexpected between runs). Only the simulator's pump exists today; Task 8's summary puts this to the PI.
5. **No session open: a reward is refused with its own sentence** (Task 2), naming XC-158 (the line flush), where `Service._route` said "a command for a run is not applied". The idle page shows no reward button.
6. **The page's forms follow the mockup where it has them; where a later, approved ruling differs, the ruling wins** (Tasks 4, 5):
   - *New session* (`dlg-new`): **no `now` for the departure**, where the mockup's `←cage at` defaults to it -- the terminal's parser has no `now` spelling for the departure (`marks.clock_time`'s docstring), and the page's times follow "the terminal's exact rules" (spec §6.0); the field is empty with a placeholder. **No rig select and no "saved to" line**: `wlx taskd`'s rig and root are fixed by `--rig` and `--root`, and the page knows neither. **The id is typed**, where the mockup computes it: spec §6.2 asks for "the session id, as `wlx run --session-id` takes it". **Deployment, setup and fluid given today are added** (spec §6.2). Order: subject, deployment, setup, `←cage at`, id, given today.
   - *End session* (`a-end`, `end-confirm`): the mockup's sentence ("the in-session clock stops, and the code it used is packaged") predates b3a-1 decision 6 and slice b6: ending releases the head now and takes the return now or later, and packaging is b6's. The confirmation says that, and carries an optional `→cage at` field (spec §6.0: "The page takes both times", where the mockup reads the return from the ELN).
   - *Pre-flight* (`pf-panel`, `pf-pill`): the items are the service's (spec §6.2, `preflight.py`), not the mockup's list; the mockup's *must* tag is left out, since every fail blocks (S9a §10); the row's action cell is an *acknowledge* box for each unknown, where the mockup has test buttons; an unknown is drawn as the mockup's hollow *untested* ring; the pill counts "N to acknowledge", since an unknown is acknowledged, not checked.
   - **Not built here**: the task-library pull and its `task-check` pill (b3b, XC-150), "start from" and "load from a previous session" (XC-018), "load session" (a crash is the stranded rule's *end session…*), the Training tools tab and its typed reward amount and `R` key (b5; the PI's rule is one press = one `reward_correct`, and spec §5.2 gives the reward no key -- b2a's *give reward* button stays).
   - **Added, with no mockup element**: the run's trial count beside the task, since until the day's plan (b3b) a run is `wlx run`'s flat run of N trials; it starts at `wlx run --trials`'s default, 1000 (`web.RUN_TRIALS`).
7. **The pre-flight is taken on request, never on a timer** (Tasks 4, 6). Choosing a task sends a `check`; the pre-flight pill, a button between runs, sends one for the task chosen and opens the Setup tab at the panel (the mockup's pill opens the panel). Nothing re-checks on a frame, and `StartRun` takes the pre-flight again anyway (`Service._start`).
8. ***start run* carries the task of the pre-flight shown** (Tasks 4, 6): the button's `data-task` is the frame's `preflight.task`; the script sends that task, and only while it is the one chosen in the Task select. It is greyed, with the reason, while no pre-flight is shown or any item fails (spec §6.2). Unknown items are not gated in the page: the rig refuses a start that leaves one unacknowledged, naming it.
9. **An acknowledgement is a box per unknown item, carrying its exact name** (Tasks 4, 6): Python never renders one ticked; the script keeps the ticks across a re-render, sends the names ticked with the start, and clears them whenever a pre-flight is asked for or a start is sent, so no tick outlives the run or the task it was given for (Review Focus 4).
10. **An answer re-sends the time as typed, and only for a question this page raised** (Task 6): the script keeps the last open and the last return it sent; *confirm* re-sends the open with `answer: "confirm"`, or the return with `confirm: true`; *amend…* opens the amendment form and re-sends the open with `answer: "amend"`, the corrected time and the reason (the name is the sender's, `by`); *re-type* opens the return form. A warning whose session this page did not send is not answered: the page says to send the time again. `service._unasked` refuses a mismatched answer anyway (b3a-1).
11. **Everything a person types is static; only a select's options are a fragment** (Tasks 4, 5, 6): idle and between-runs frames arrive about once a second (`service.HOUSEKEEPING_S`), and a swapped fragment would erase what is being typed. The dialog, the trial count, the end confirmation, the return and the amendment are outside every fragment; the task and subject selects' options are fragments, and the script keeps the chosen option across a swap (Review Focus 1).
12. **End session is two steps, shown as such** (Task 5; b3a-1 decision 6): the Summary's *end session* asks first -- the head's release now, the return now or left blank for later -- then the pill reads *ended · awaiting the return* beside *record return…*, the second step. A stranded animal's banner carries *end session…*, which opens the same return form naming its session: what `Service._open`'s stranded refusal ("Record it with End session, naming its session") and `preflight.out_of_cage`'s fail ("end the session (End session)") tell a person to do -- XC-176's two sentences, true once this lands.
13. **Outside a run the control bar offers *start run* (between runs), *give reward* and *mark*** (Task 4): the rig gives the first two and stamps a mark outside a run (b3a-1 decision 16); pause and stop have no run to act on and are not shown.
14. **b2a's *stop…* is labeled *stop run***, the mockup's `a-stop` (Task 4); its confirmation step and sentence are b2a's, unchanged (spec §5.2).
15. **The page says each run is unplanned** (spec §6.2): beside *start run* and atop every pre-flight (`web.UNPLANNED`).
16. **The welfare-critical surface after this plan** (`docs/design/architecture.md`, updated in Task 2): **changed** -- `taskd.Session._manual_reward` (its rule: decision 4) and `Session._command`'s `held` pass-through (moved ahead of the post-loop refusal; the line itself unchanged). **Nothing is added to the list.** Also changed, lexically, in `_command`: the awaiting-return refusal's "(the page's End session button waits on b3a-2)" becomes "(the page's End session)" (Task 5), not a listed part. **And one lexical change in `welfare.py`, which is on the list whole** (Task 5; the controller's ruling of 2026-09-30): in `Welfare._far_from_now` alone, the words that end a far mark's sentence are chosen by the mark -- "amend it with a reason" for a departure, unchanged byte for byte, and "type it again" for a return, which has no amendment. The threshold, the refusals, the `None` inside the band, and `departure_needs_confirmation` and `return_needs_confirmation` themselves are untouched. **Untouched, and checked in Task 8 Step 4**: `bounds.py`, every other `welfare.py` function and method, `marks.py`, `stranded.py`; `preflight.out_of_cage` and `gate`; the seven `service` functions; `taskd.Session._ends`, `_hold`, `set`, `_schedule` and `_command`'s `except` line; `link._setting`; `cli._settle_departure`, `_settle_return` and `main`.

## Global Constraints

- US English in code, docs and comments.
- **"Writes only from the rig PC's own browser (§2's four checks), until b2b"** (spec §6.2): loopback peer, `Host` naming loopback, the page's own `Origin`, `Content-Type: application/json`; recorded as **`NAME (box, unverified)`**.
- **"The page sends the text as typed; the service parses it with the terminal's own parser"**, and **"the page offers exactly the terminal's two choices: confirm it, or amend it with a reason and a name"**; for the return **"there is no amendment for a return"** (spec §6.2). Nothing on the page parses or decides a time.
- **"fail blocks, unknown proceeds on a named acknowledgement written into the record, pass proceeds"** (spec §6.2, S9a §10).
- **"Every run is unplanned until b3b brings the day's plan, and the page says so each time, with the warning that an unplanned run lowers the session's timing tier"** (spec §6.2).
- **"Starting values are the task's own. Remembering an animal's values from its last session stays with XC-018."** (spec §6.2).
- **"Wherever a session is open (running, paused, between runs, or awaiting the return), one press is one delivery of the session's `reward_correct` at its current value, through the path a task's reward takes, charged, recorded and strobed as §5.1's paused reward is."** Built here: between runs and while the return is awaited. **During a trial (XC-157) and with no session open (XC-158) stay refused, each with a sentence** (spec §6.0).
- **"A manual reward is never re-sent"**; *sent* only when `taskd` acknowledged it, *not delivered* when the exchange timed out, *busy* when the queue is full (spec §5.3). Nothing here adds a re-send.
- **"Panes are rendered to HTML in Python and pushed as fragments; the page's JavaScript only swaps them in"** (spec §1); the script "still renders nothing itself" -- every `innerHTML` it writes is a fragment (`test_the_script_does_only_what_spec_4_3_and_5_2_ask`). **Every telemetry string reaches the page through `web._e`.** One `fetch`, to `/commands`.
- **"Keys do nothing while a text box has focus"** (spec §5.2); no new key.
- **The console's visible name is `xcon`** (PI, 2026-09-30; `e51e343`: the tab reads "xcon console", the logo "xcon", and the v12 mockup shows the same). No text this plan puts on the page says "expcontroller"; `test_the_page_is_served_with_every_pane_and_its_own_nonce` asserts it for a running session's page, and Task 5 for the idle page with its dialog.
- Hot path: nothing new per frame. No timing claim without a measurement (CLAUDE.md): `RUN_TRIALS` is `wlx run`'s default, and the e2e pacing is housekeeping for the simulator.
- Sim first: every behavior has a simulator-backed test; the end-to-end tests drive a real `wlx taskd` over a real `ZmqLink` through a real `wlx serve`'s HTTP endpoints.
- Welfare-critical code changes only as Plan decision 16 lists, and go to the PI (Task 8).
- `tools/mutate.py`'s method over every new and changed function before the branch merges, each line read as a real `N failed` (CLAUDE.md, "Prove a test can fail"; Task 8 Step 3).
- **Out of scope, and left refused or absent**: the manual reward during a trial (XC-157) and with no session open (XC-158); the task-library pull and the day's plan (b3b, XC-150); remote sign-in, so writes stay the box's (b2b, XC-015); remembered starting values (XC-018); the manual reward after a `wlx run` session's run (XC-184, filed here).

## Review Focus

The five inputs most likely to bite a person at the page that no task's tests would otherwise exercise, each pinned by a test in its owning task:

1. **A frame arriving while a person types into a form** -- idle and between-runs frames come about once a second. Expected: nothing typed is lost, and a chosen task or subject stays chosen. Tests: Task 5, `test_nothing_a_person_types_into_is_inside_a_fragment`; Task 6, `test_a_frame_keeps_the_option_chosen_in_a_select`.
2. **A task under `--tasks` that uses a number with no starting value** -- the three other reference tasks today, or a new one. Expected: its pre-flight fails naming each such parameter, and the start is refused before `RUN_START`, never a fault at its first trial. Test: Task 1, `test_a_number_the_task_uses_that_nothing_gives_a_value_fails_naming_it`.
3. **A malformed session command from a page** -- a number for an id, a list for values, trials as text, one string for the acknowledgements, an answer the terminal does not know, a field the command does not take. Expected: a 400 with the wire's own sentence, nothing queued. Tests: Task 3, `test_a_malformed_session_command_is_refused_with_the_wires_sentence` and `test_a_session_command_from_the_boxs_page_is_dispatched_and_a_malformed_one_is_not`.
4. **An acknowledgement left from an earlier run or another task's pre-flight.** Expected: a start sends only what is ticked on the pre-flight shown for the task chosen, and the ticks clear once a start or a new pre-flight is asked for; the pane never renders a box ticked. Tests: Task 4, `test_each_unknown_item_has_an_unticked_acknowledgement_carrying_its_exact_name`; Task 6, `test_no_acknowledgement_outlives_the_run_or_the_task_it_was_ticked_for`.
5. **A double press on *start run*** -- two POSTs before the first frame shows the run. Expected: one run; the second refused on the feed, never queued behind it. Test: Task 7, inside `test_page_e2e_open_a_session_run_it_twice_and_end_it`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `wl_xcon/task.py` | modify | `Param.start`: the task's own starting value |
| `tasks/fixation_detection.py` | modify | its seven numeric parameters' starts |
| `wl_xcon/check.py` | modify | `parameters_used`: every parameter a task references |
| `wl_xcon/preflight.py` | modify | `values`: the task's starts under what was sent; a used number with no value fails |
| `wl_xcon/taskd.py` | modify | `run`: starts from the task's values, `layers` recorded apart; **welfare-critical**: `_command`'s pass-through moved, `_manual_reward` by phase; `OUTSIDE_A_RUN`; the awaiting sentence |
| `wl_xcon/service.py` | modify | `_route`: a reward with no session open refused with its own sentence |
| `wl_xcon/welfare.py` | modify | **welfare-critical, words only**: `Welfare._far_from_now` ends a far return's sentence "Confirm it, or type it again" |
| `wl_xcon/link.py` | modify | `_command_from` split out of `_decode_command` |
| `wl_xcon/serve.py` | modify | `_SHAPES` and `parse_command` take `open`, `check`, `start`, `end`; `SERVICE_SENT`; `dispatch` |
| `wl_xcon/web.py` | modify | the new panes, the control bar, the Setup and Summary panels, the static forms, the CSS, the script |
| `tests/test_task.py`, `test_reference_tasks.py`, `test_preflight.py`, `test_taskd.py`, `test_service.py`, `test_serve.py`, `test_web.py`, `test_welfare.py`, `test_cli.py`, `tests/_sessions.py` | modify | as each task says; the end-to-end tests through the page are in `test_serve.py` |
| `docs/design/architecture.md` | modify | the welfare-critical paragraphs (Task 2); the `console` row (Tasks 2, 6) |
| `docs/backlog.md` | modify | XC-183 (Task 1), XC-184 (Task 2) filed; XC-016 and XC-176 closed (Task 8) |
| `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` | modify | §6.7: what this plan decided (Task 8) |

---

### Task 1: A run starts from its task's own values (`Param.start`)

**Files:**
- Modify: `wl_xcon/task.py` (`Param`), `tasks/fixation_detection.py` (`params`), `wl_xcon/check.py` (new `parameters_used`), `wl_xcon/preflight.py` (`values`, its import), `wl_xcon/taskd.py` (`Session.run`)
- Modify: `tests/_sessions.py` (`whole_point_task`, `malformed_task`), `tests/test_cli.py` (`_either_task`) -- they rewrite the fixation task's text by exact line
- Modify: `docs/backlog.md` (file XC-183)
- Test: `tests/test_task.py`, `tests/test_reference_tasks.py`, `tests/test_preflight.py`, `tests/test_taskd.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `task.Param.start: object = None`; `check.parameters_used(trial: Trial) -> frozenset[str]`; `preflight.values(trial, given)` (same signature) now checks `{**starts, **given}` and fails a used number with no value; a `runs.jsonl` start row's `layers` is `{"task": {name: start}, "run": {name: given}}`. Later tasks send `values: {}` from the page and rely on `fixation_detection` running from its own values.

- [ ] **Step 1: Write the failing tests**

`tests/test_task.py` -- add `Param` to the `from wl_xcon.task import ...` line, and:

```python
def test_a_parameter_declares_the_value_a_run_starts_with_or_none():
    """P4d-2b spec §6.2: "Starting values are the task's own" -- S8 §3.4's task layer.
    Optional: a parameter the task leaves to whoever starts the run declares none."""
    assert Param("fix_hold", unit="s", low=0.05, high=2.0).start is None
    assert Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3).start == 0.3
```

`tests/test_reference_tasks.py` -- add `from wl_xcon.cli import _load_trial` beside the other imports, and:

```python
def test_the_fixation_task_starts_from_the_values_the_console_mockup_shows():
    """P4d-2b spec §6.2 ("Starting values are the task's own"), with the values the
    mockup the PI reviewed shows for it (`TASKS.fixation_detection`) -- the ones every
    end-to-end test has run it at (`tests/test_cli.py`'s `_TASK_SETS`) -- each inside its
    own range. Its appearance is left unset, as every test has left it."""
    params = _load_trial(TASKS / "fixation_detection.py").params

    assert {param.name: param.start for param in params} == {
        "fix_timeout": 4.0, "fix_hold": 0.3, "response_window": 0.6, "target_hold": 0.2,
        "fix_window": 2.0, "target_window": 3.0, "target_position": 10.0,
        "target_looks": None,
    }
    for param in params:
        if param.start is not None:
            assert param.low <= param.start <= param.high, param.name
```

`tests/test_preflight.py` -- add `from wl_xcon.check import parameters_used`, and:

```python
def test_parameters_used_names_every_parameter_the_task_references():
    """From the task down -- states, windows and the stimuli they name -- as
    `run._resolve` meets them in a trial."""
    assert parameters_used(_load_trial(TASK)) == frozenset({
        "fix_hold", "fix_timeout", "fix_window", "response_window", "target_hold",
        "target_looks", "target_position", "target_window",
    })


def test_a_run_given_nothing_starts_from_the_tasks_own_values():
    """What the page sends (P4d-2b spec §6.2): no values, and the task's own pass."""
    item = preflight.values(_load_trial(TASK), {})

    assert (item.result, item.said) == ("pass", "7 starting value(s), each declared and in range")


def _starting(**starts):
    """The reference task with the named parameters' own `start` replaced."""
    trial = _load_trial(TASK)
    return dataclasses.replace(
        trial,
        params=[
            dataclasses.replace(param, start=starts[param.name]) if param.name in starts else param
            for param in trial.params
        ],
    )


def test_a_number_the_task_uses_that_nothing_gives_a_value_fails_naming_it():
    """Review Focus 2 (the b3a-2 plan, decision 2). A run with a parameter its trials
    resolve and no value for it faulted at its first trial -- `run._resolve`: "no value
    bound for parameter" -- after `RUN_START`. The pre-flight now fails it, naming each,
    so the start is refused first. An appearance, which nothing resolves before S4's
    display exists, is not refused unset."""
    trial = _starting(fix_hold=None, fix_window=None)

    item = preflight.values(trial, {})

    assert (item.name, item.result) == ("starting values", "fail")
    assert "'fix_hold' is used by the task and has no starting value" in item.said
    assert "'fix_window' is used by the task and has no starting value" in item.said
    assert "target_looks" not in item.said
    assert preflight.values(trial, {"fix_hold": 0.3, "fix_window": 2.0}).result == "pass"


def test_a_tasks_own_start_outside_its_range_fails_as_a_sent_value_does():
    item = preflight.values(_starting(fix_hold=99.0), {})

    assert item.result == "fail"
    assert "'fix_hold' is declared over [0.05, 2.0] s and 99.0 is outside it" in item.said
    assert preflight.values(_starting(fix_hold=99.0), {"fix_hold": 0.3}).result == "pass", (
        "what was sent is what the run starts with"
    )
```

`tests/test_taskd.py` -- beside `VALUES`, add:

```python
#: `tasks/fixation_detection.py`'s own starting values (`Param.start`; the b3a-2 plan,
#: decision 1).
FIXATION_STARTS = {
    "fix_timeout": 4.0, "fix_hold": 0.3, "response_window": 0.6, "target_hold": 0.2,
    "fix_window": 2.0, "target_window": 3.0, "target_position": 10.0,
}
```

change, in `test_the_run_a_session_spec_describes_is_run_0_in_every_file_it_writes`,

```python
    assert start["layers"] == {"run": start["resolved"]}
```

to

```python
    assert start["layers"] == {"task": FIXATION_STARTS, "run": start["resolved"]}
```

and add, after `_service_session`'s other tests:

```python
def test_a_run_starts_from_its_tasks_own_values_under_the_ones_it_was_given(tmp_path):
    """P4d-2b spec §6.2 and S8 §3.4's task layer (the b3a-2 plan, decision 1): a run's
    values are its task's `Param.start`s with what the run was given over them, and its
    start row keeps the two layers apart."""
    session = _service_session(tmp_path)

    session.run(
        RunSpec(task="tasks/fixation_detection.py", trials=2, seed=2, values={"fix_hold": 0.5})
    )

    start, _ = _runs(session)
    assert start["layers"] == {"task": FIXATION_STARTS, "run": {"fix_hold": 0.5}}
    assert start["resolved"] == {**FIXATION_STARTS, "fix_hold": 0.5}
    assert session.stop_kind == "completed", "every parameter it uses had a value"


def test_wlx_runs_one_run_takes_the_tasks_own_value_where_set_gave_none(tmp_path):
    session = _session(_spec(tmp_path, trials=2, values={"fix_hold": 0.5}))

    session.run()

    assert session.stop_kind == "completed"
    assert session.spec.values == {**FIXATION_STARTS, "fix_hold": 0.5}
```

`tests/test_service.py`:

```python
def test_a_run_started_with_no_values_starts_from_the_tasks_own(tmp_path):
    """What a page sends (P4d-2b spec §6.2: "Starting values are the task's own"): no
    values, and the run starts, and runs to its end, at the task's own."""
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(values={}))

    assert (frame.phase, frame.run_index, frame.stop_kind) == ("between_runs", 0, "completed")
    assert _runs(service.root)[0]["resolved"]["fix_hold"] == 0.3
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_task.py tests/test_reference_tasks.py tests/test_preflight.py tests/test_taskd.py tests/test_service.py -q -p no:cacheprovider -k "starts_from or start_outside or parameters_used or nothing_gives or declares_the_value or wlx_runs_one_run or run_0_in_every_file"`
Expected: FAIL -- `TypeError: Param.__init__() got an unexpected keyword argument 'start'`, `ImportError: cannot import name 'parameters_used'`, `AttributeError: 'Param' object has no attribute 'start'`, and a `KeyError: "no value bound for parameter 'fix_timeout'..."` from the two runs.

- [ ] **Step 3: `Param.start`**

In `wl_xcon/task.py`, in `class Param`, after `live: bool = True`, add:

```python
    #: **The value a run starts with when nobody gives one** (P4d-2b spec §6.2:
    #: "Starting values are the task's own"; S8 §3.4's *task* layer, under what a console
    #: or `wlx run --set` gives): a number inside `[low, high]`, or one of `choices`.
    #: `None`, the default, leaves it to whoever starts the run -- and a `wlx taskd` run
    #: whose trials use a number nobody gave is refused by its pre-flight
    #: (`preflight.values`), not faulted at its first trial. Checked there, not at load:
    #: `wlx run` checks it no more than it checks `--set` (XC-159).
    start: object = None
```

In `tasks/fixation_detection.py`, replace the seven numeric `Param` lines with:

```python
        Param("fix_timeout", unit="s", low=0.5, high=10.0, start=4.0),
        Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),
        Param("response_window", unit="s", low=0.1, high=3.0, start=0.6),
        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),
        Param("fix_window", unit="deg", low=0.5, high=5.0, start=2.0),
        Param("target_window", unit="deg", low=0.5, high=6.0, start=3.0),
```

and (below its three comment lines, which stay)

```python
        Param("target_position", unit="deg", low=-16.0, high=16.0, start=10.0),
```

and add, above `params=[`, the comment line:

```python
    # Each number starts where the console mockup the PI reviewed shows it (P4d-2b spec
    # §6.2, "Starting values are the task's own"); the appearance is left to the run.
```

- [ ] **Step 4: The three test helpers that rewrite this file's text**

`tests/_sessions.py`, `whole_point_task`: the second `(old, new)` pair becomes

```python
        ('        Param("target_position", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_position", unit="deg", low=-16.0, high=16.0, start=10.0),\n'
         '        Param("target_point", unit="deg", choices=((10.0, 0.0), (-10.0, 0.0))),'),
```

`tests/_sessions.py`, `malformed_task`:

```python
    old = 'Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),'
    assert text.count(old) == 1, old
    path = Path(folder) / "malformed.py"
    path.write_text(text.replace(old, 'Param("fix_hold", unit="s", low="0.05", high=2.0, start=0.3),'))
```

`tests/test_cli.py`, `_either_task`:

```python
    target = 'Param("target_position", unit="deg", low=-16.0, high=16.0, start=10.0)'
    assert text.count(written_for) == 1 and text.count(target) == 1
    text = text.replace(written_for, 'view="either"').replace(
        target, f'Param("target_position", unit="deg", low={-reach}, high={reach}, start=10.0)'
    )
```

(`_either_task` is called with reaches 10.0 and 16.0, so 10.0 stays inside the range.)

- [ ] **Step 5: `check.parameters_used`**

In `wl_xcon/check.py`, after `_iter_param_refs`, add:

```python
def parameters_used(trial: Trial) -> frozenset[str]:
    """Every parameter a task references anywhere -- its states, its windows and the
    stimuli they name -- by name: what its trials resolve (`run._resolve`), and so what a
    run must have a value for (`preflight.values`, P4d-2b b3a-2). `_iter_param_refs`,
    from the task down, so a new vocabulary member is covered the day it is added."""
    return frozenset(ref.name for ref in _iter_param_refs(trial))
```

- [ ] **Step 6: `preflight.values`**

In `wl_xcon/preflight.py`, change `from wl_xcon.check import check` to `from wl_xcon.check import check, parameters_used`, and replace `values` whole with:

```python
def values(trial: Trial | None, given: dict) -> PreflightItem:
    """A run's starting values -- its task's own (`Param.start`), with what a console
    sent over them (P4d-2b spec §6.2; S8 §3.4) -- against the task's own declarations:
    **fail** for a name it does not declare, a word where it takes a number, a number
    outside its range, a choice it does not offer, or a declaration it cannot be
    compared with; and **for a number the task uses that nothing gives a value** (the
    b3a-2 plan, decision 2): a run started without one faults at its first trial
    (`run._resolve`), after `RUN_START`, so it is refused here instead, naming each. A
    categorical parameter is an appearance, which nothing in this build resolves before
    a trial needs it -- S4's display is not built -- so one left unset is not refused.
    Checked as `Session.set` checks a live value, non-finite numbers included. **Nothing
    a task's declarations hold raises out of here.**"""
    if trial is None:
        return PreflightItem(
            STARTING_VALUES, FAIL, "the task did not load, so its values cannot be checked"
        )
    try:
        declared = {param.name: param for param in trial.params}
        starts = {
            name: param.start for name, param in declared.items() if param.start is not None
        }
        used = parameters_used(trial)
    except Exception as broken:  # noqa: BLE001 -- a task's declarations are code's output
        return PreflightItem(
            STARTING_VALUES,
            FAIL,
            f"the task's parameter declarations could not be read: "
            f"{type(broken).__name__}: {broken}",
        )
    merged = {**starts, **given}
    wrong = []
    for name, value in merged.items():
        param = declared.get(name)
        # **Fails closed per value** (the b3a-1 final review, Important 1): `Param` checks
        # none of its fields, so a bound typed as text or `choices` that are not a
        # collection pass `check()` and raise here -- and a raise out of a pre-flight
        # ended `wlx taskd` with the animal out. It fails this value and names it.
        try:
            if param is None:
                wrong.append(f"{name!r} is not a parameter this task declares")
            elif param.choices:
                if value not in param.choices:
                    wrong.append(f"{name!r} may only be one of {param.choices}")
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                wrong.append(f"{name!r} takes a number ({param.unit}), and {value!r} is not one")
            elif not math.isfinite(value):
                wrong.append(f"{name!r} is {value!r}, which is not a real number")
            elif (param.low is not None and value < param.low) or (
                param.high is not None and value > param.high
            ):
                wrong.append(
                    f"{name!r} is declared over [{param.low}, {param.high}] {param.unit} and "
                    f"{value} is outside it"
                )
        except Exception as broken:  # noqa: BLE001 -- see above
            wrong.append(
                f"{name!r} could not be checked against its declaration: "
                f"{type(broken).__name__}: {broken}"
            )
    for name in sorted(used):
        param = declared.get(name)
        if param is not None and not param.choices and name not in merged:
            wrong.append(
                f"{name!r} is used by the task and has no starting value: the task "
                f"declares none, and none was sent"
            )
    if wrong:
        return PreflightItem(STARTING_VALUES, FAIL, "; ".join(wrong))
    return PreflightItem(
        STARTING_VALUES, PASS, f"{len(merged)} starting value(s), each declared and in range"
    )
```

(An undeclared name the task references is not in `declared`, and is `check()`'s blocking `undeclared-parameter` finding, the task item's fail.)

- [ ] **Step 7: `Session.run` starts from the task's values**

In `wl_xcon/taskd.py`, `Session.run`, replace

```python
        self._trial = trial
        self._run = run
        if not implied:
            self.spec.values = dict(run.values)
```

with

```python
        self._trial = trial
        self._run = run
        # **The task's own starting values, under the run's** (P4d-2b spec §6.2:
        # "Starting values are the task's own"; S8 §3.4's task layer; the b3a-2 plan,
        # decision 1): each declared `Param.start` that the run was not given. `wlx run`'s
        # one run fills its spec's own dict, as its values always were (`RunSpec.of`).
        starts = {param.name: param.start for param in trial.params if param.start is not None}
        given = dict(run.values)
        if implied:
            for name, start in starts.items():
                self.spec.values.setdefault(name, start)
        else:
            self.spec.values = {**starts, **given}
```

and, in the `record.run_row("start", ...)` call below it, replace

```python
            layers={"run": dict(self.spec.values)},
```

with

```python
            layers={"task": starts, "run": given},
```

- [ ] **Step 8: Run the new tests, then the files they are in**

Run: `python3 -m pytest tests/test_task.py tests/test_reference_tasks.py tests/test_preflight.py tests/test_taskd.py tests/test_service.py tests/test_cli.py -q -p no:cacheprovider`
Expected: all pass. A failure in `test_cli.py`, `test_preflight.py` or `test_service.py` that names `whole_point`, `malformed` or `either` is Step 4's text not matching the task file: fix the helper, never the assertion.

- [ ] **Step 9: File what this leaves open (CLAUDE.md: an item goes in the moment it is deferred)**

In `docs/backlog.md`, read `**Next free ID: XC-NNN.**`. This plan was written when it said **XC-183**; if it now names another, use that one here, in Task 2's XC-184 (the next after it) and everywhere this plan says either, and say so in the commit. Add under `## Features not yet planned`, after XC-146's line:

```markdown
- **XC-183** Declare starting values (`Param.start`) in `adaptive_detection`, `visual_search` and `calibration`, so `wlx taskd` runs them from the page; until then each one's pre-flight refuses its run, naming every number it uses with no value. — 2026-09-30, [b3a-2 plan, decision 1](superpowers/plans/2026-09-30-p4d2b-b3a2-page-sessions.md#plan-decisions) — waits on: nothing
```

and raise the next free ID by one: `**Next free ID: XC-184.**`

Run: `python3 -m pytest tests/test_backlog.py -q -p no:cacheprovider`
Expected: PASS. (It checks the link names a file that exists: the controller commits this plan to `docs/superpowers/plans/` before execution starts. If it is not there, stop and say so.)

- [ ] **Step 10: The whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add wl_xcon/task.py tasks/fixation_detection.py wl_xcon/check.py wl_xcon/preflight.py wl_xcon/taskd.py tests/_sessions.py tests/test_cli.py tests/test_task.py tests/test_reference_tasks.py tests/test_preflight.py tests/test_taskd.py tests/test_service.py docs/backlog.md
git commit -m "Start each run from its task's own values, and refuse one missing a value it uses"
```

---

### Task 2: The hand reward between runs and while the return is awaited (welfare-critical)

**Implement and review on the most capable model. This is the one change to welfare-critical behavior in the plan (decision 16; Task 5 changes only the words of one `welfare.py` sentence); Task 8 puts it to the PI.**

**Files:**
- Modify: `wl_xcon/taskd.py` (new `OUTSIDE_A_RUN`; `Session._command`: the `ManualReward` pass-through moved, two docstring paragraphs; `Session._manual_reward`: the rule by phase; `Session.receive`'s docstring)
- Modify: `wl_xcon/service.py` (`Service._route`: a reward with no session open)
- Modify: `docs/design/architecture.md` (the welfare-critical paragraph on `_hold`, `_manual_reward` and the pass-through; the `console` row's `ManualReward`), `docs/backlog.md` (file XC-184)
- Test: `tests/test_taskd.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: b3a-1's `Session.receive`, `end_runs`, `close`, `Service._route`; b2a's `_manual_reward` refusals.
- Produces: `taskd.OUTSIDE_A_RUN = ("between_runs", "awaiting_return")`; a `ManualReward` received by a `wlx taskd` session in either phase is one delivery of `reward_correct`, its feed and record row saying `"{ml:g} mL of reward_correct, given between runs"` or `"..., given while the animal's return is awaited"`; with no session open `Service._route` refuses it with `"no session is open, so no reward was given: a reward with no session open, which flushes the line, waits on XC-158"`. Task 4 greys and lights the page's *give reward* by the same phases; Task 7 drives all of it through the page.

- [ ] **Step 1: Write the failing tests**

`tests/test_taskd.py`, after the b3a-1 tests that use `_service_session`:

```python
# --- b3a-2: the hand reward between runs and while the return is awaited ------------


def test_between_runs_a_hand_reward_is_one_correct_trial_reward_through_the_tasks_path(tmp_path):
    """PI, 2026-09-29 (P4d-2b spec §6.0): "whenever the console is up, the manual reward
    should work". Between runs, one press is one delivery of `reward_correct` at the
    value it holds -- 0.15 mL here -- through `Rig.reward` and `Welfare.deliver`, the
    path a task's reward takes, `MANUAL_REWARD` strobed before the valve, one `reward`
    row at the instant it was commanded, and the feed saying where it was given."""
    session = _service_session(tmp_path)
    pump = _Watched(session.card)
    session.welfare.pump = pump
    commanded, deliveries = session.welfare.commanded, session.welfare.deliveries

    session.receive(ManualReward(by="jake"))

    assert session.welfare.commanded == pytest.approx(commanded + 0.15)
    assert session.welfare.deliveries == deliveries + 1
    assert (pump.delivered, pump.strobed_before) == ([0.15], [REWARD_CODE])
    (row,) = _manual_rows(session)
    assert (row["by"], row["ml"], row["entry"]) == ("jake", 0.15, "reward_correct")
    assert row["at"] == session.welfare.last_delivery_wall_at
    assert session.controls[-1][3] == "0.15 mL of reward_correct, given between runs"
    assert [r for r in session.refusals if r[0] == "reward"] == []


def test_after_a_run_and_while_the_return_is_awaited_a_hand_reward_is_given_and_said_so(tmp_path):
    session = _service_session(tmp_path)
    session.run(_run_spec(trials=1))
    session.receive(ManualReward(by="jake"))
    session.end_runs("jake")
    session.receive(ManualReward(by="jake"))

    assert [row["run"] for row in _manual_rows(session)] == [0, 0]
    assert [said for kind, _, _, said in session.controls if kind == "reward"] == [
        "0.15 mL of reward_correct, given between runs",
        "0.15 mL of reward_correct, given while the animal's return is awaited",
    ]
    assert session.card.codes.count(REWARD_CODE) == 2


def test_a_closed_session_refuses_a_hand_reward_and_gives_nothing(tmp_path):
    session = _service_session(tmp_path)
    session.end_runs("jake")
    session.returned_to_cage(session.wall_now(), by="jake", how="the page")
    session.close(how="wlx taskd")
    given = session.welfare.deliveries

    session.receive(ManualReward(by="jake"))

    ((name, by, why),) = [r for r in session.refusals if r[0] == "reward"]
    assert (name, by) == ("reward", "jake")
    assert "the session has ended" in why and "no reward was given" in why
    assert session.welfare.deliveries == given and REWARD_CODE not in session.card.codes


def test_a_pump_that_fails_a_hand_reward_between_runs_is_not_caught(tmp_path):
    """As `welfare.Rig` catches no pump fault for a task's reward: the reward is charged
    before the valve, and the fault goes on to `wlx taskd`, which ends on it and leaves
    the animal stranded for its next start (the b3a-2 plan, decision 4)."""
    session = _service_session(tmp_path)

    class _Broken(Pump):
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    session.welfare.pump = _Broken()

    with pytest.raises(RuntimeError, match="solenoid did not answer"):
        session.receive(ManualReward(by="jake"))
    assert session.welfare.deliveries == 1, "charged before the valve"
```

and in `test_after_the_loop_a_manual_reward_is_refused_and_nothing_is_given`, after `assert "the session has ended" in why`, add:

```python
    assert "XC-184" in why, "wlx run's session after its run: its own item"
```

`tests/test_service.py` -- add `ManualReward` to the `wl_xcon.link` import, and:

```python
def test_the_hand_reward_works_between_runs_and_while_the_return_is_awaited(tmp_path):
    """PI, 2026-09-29 (P4d-2b spec §6.0), through the service: `tasks/twelve_hour_bounds.py`'s
    `reward_correct`, 0.05 mL, once per press, on the frame's fluid total and feed."""
    service = _service(tmp_path)
    _step(service, _open())

    between = _step(service, ManualReward(by=BY))
    _step(service, _end(returned=None))
    awaiting = _step(service, ManualReward(by=BY))

    assert between.fluid_session_ml == pytest.approx(0.05)
    assert between.controls[-1].said == "0.05 mL of reward_correct, given between runs"
    assert awaiting.phase == "awaiting_return"
    assert awaiting.fluid_session_ml == pytest.approx(0.10)
    assert awaiting.controls[-1].said == (
        "0.05 mL of reward_correct, given while the animal's return is awaited"
    )
    assert service.session.card.codes.count(4134) == 2
    assert [r for r in awaiting.refusals if r.name == "reward"] == []


def test_with_no_session_open_a_hand_reward_is_refused_and_says_what_it_waits_for(tmp_path):
    """XC-158 is the button with no session open, a line flush counted to no animal;
    until it is built, a press is refused with its own sentence."""
    service = _service(tmp_path)

    frame = _step(service, ManualReward(by=BY))

    assert frame.refusals == (
        Refused(
            "reward",
            BY,
            "no session is open, so no reward was given: a reward with no session open, "
            "which flushes the line, waits on XC-158",
        ),
    )


def test_during_a_run_a_hand_reward_is_still_given_only_while_paused(tmp_path):
    """XC-157 is the reward during a trial, given the moment it is pressed; until it is
    built, a press while trials run is refused as b2a refused it, and nothing is given.
    This passes before the change too: it pins that the change did not widen it."""
    link = _Script({2: [ManualReward(by=BY)]})
    service = _service(tmp_path, link=link)

    frame = _step(service, _open(), _start())

    (refusal,) = [r for r in frame.refusals if r.name == "reward"]
    assert "the session is not paused" in refusal.why and "no reward was given" in refusal.why
    assert 4134 not in service.session.card.codes
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_taskd.py tests/test_service.py -q -p no:cacheprovider -k "hand_reward or after_the_loop_a_manual_reward"`
Expected: FAIL -- the between-runs and awaiting rewards are refused ("no run is in progress", "the session has ended and is waiting"), so no delivery; the pump test fails `DID NOT RAISE`; the idle sentence is "no session is open, so a command for a run is not applied..."; the `XC-184` assertion fails. `test_during_a_run_a_hand_reward_is_still_given_only_while_paused` passes already.

- [ ] **Step 3: `_command` hands every reward to `_manual_reward` first**

In `wl_xcon/taskd.py`, beside `MANUAL_REWARD_ENTRY`, add:

```python
#: The phases of a `wlx taskd` session in which no run is in progress and a manual
#: reward is given (P4d-2b spec §6.0; `Session._manual_reward`): between runs, and after
#: *End session* while the animal's return is awaited.
OUTSIDE_A_RUN = ("between_runs", "awaiting_return")
```

In `Session._command`, at the very top of the body (before `if isinstance(command, _link.Mark) and self.service and self.phase != "running":`), add:

```python
        if isinstance(command, _link.ManualReward):
            # **Welfare-critical, this pass-through** (`docs/design/architecture.md`):
            # every reward goes to `_manual_reward`, which decides in every phase whether
            # it is given -- held paused in a run, or a `wlx taskd` session between runs
            # or awaiting its return -- with `held`, which only `_hold` sets. Ahead of
            # the post-loop refusal below since P4d-2b b3a-2 (spec §6.0), which it
            # followed until then.
            self._manual_reward(command.by, index, held)
            return
```

and delete the later branch

```python
        if isinstance(command, _link.ManualReward):
            self._manual_reward(command.by, index, held)
            return
```

(between the `CancelScheduledStop` branch and `if not isinstance(command, _link.SetParameter):`). After this edit, `self._manual_reward(command.by, index, held)` appears in `taskd.py` exactly once.

In `_command`'s docstring, replace the paragraph that begins `**Nothing arriving here is accepted once the loop has ended**` with:

```python
        **Nothing arriving here is accepted once the loop has ended but a manual reward
        in a `wlx taskd` session** (P4d-2a spec §10, Task 8; P4d-2b spec §6.0). A parameter
        staged after the last trial could never be applied, and a stop has nothing left
        to stop -- both are refused with the reason rather than silently kept. The page's
        return is `EndSession`, which `wlx taskd` takes itself (`service.Service._end`) and
        never routes here. A manual reward is handed to `_manual_reward` before anything
        else, in every phase, and it gives one while the animal's return is awaited.
```

and the paragraph that begins `**`held` is true only for a command `_hold` drained**` with:

```python
        **`held` is true only for a command `_hold` drained** (P4d-2b b2a, amended
        2026-09-28): the session held paused at this boundary. Only a manual reward
        reads it (`_manual_reward`): during a run the PI's manual reward is given while
        paused, and never while a pause drained in this same pass has yet to hold.
```

- [ ] **Step 4: `_manual_reward` decides by phase**

Replace `Session._manual_reward` whole with:

```python
    def _manual_reward(self, by: str, index: int, held: bool) -> None:
        """**A manual reward** (PI, 2026-09-28: "I want to be able to give manual rewards
        during pause"; 2026-09-29: "whenever the console is up, the manual reward should
        work", P4d-2b spec §6.0). Asked how much one press gives: "Same as a correct
        trial" -- one delivery of the bounded config's `MANUAL_REWARD_ENTRY`, at the value
        it holds now, **through the path a task's reward takes**: `welfare.Rig.reward`,
        then `Welfare.deliver`, which charges it before the valve opens and counts it in
        `commanded`, `deliveries` and `last_delivery_wall_at`. So it is on the fluid
        total and the time since the last reward. `MANUAL_REWARD` is strobed first, as a
        task strobes `REWARD_COMMANDED` before its `Reward`, and one `reward` row goes to
        the record, with the mL given, at the instant the reward was commanded, and a feed
        row saying where it was given.

        **When, by phase** (the b3a-2 plan, decision 4):

        - **During a run, only while held** (`held`: drained by `_hold`), as since b2a.
          Refused, with a sentence and nothing given, when the session is stopping -- a
          `Stop` ahead of it in the drain -- or not paused -- trials running, or a
          `Resume` ahead of it -- or paused in this same drain and not yet held; and when
          a fluid scheduled stop is already due (welfare review round 1, 2026-09-28: two
          presses drained in the same pass, the first reaching it, must not both be
          given, since nothing stops a loopback peer other than the page from sending
          two), checked the same way `_ends` checks it, with nothing strobed or
          delivered on this refusal either. A press during a trial, given the moment it
          is pressed, is XC-157's.
        - **Outside a run, in a `wlx taskd` session between runs or awaiting its animal's
          return** (`OUTSIDE_A_RUN`, b3a-2): given, with no pause to hold, since no trial
          runs and no task rewards. No scheduled stop is asked: one belongs to the run it
          was set on (spec §6.1), and outside a run there is none to end.
        - **Anywhere else, refused**: a `wlx run` session after its run, whose return is
          taken at its terminal on another thread (XC-184), and a session that has
          closed. With no session open, `service.Service._route` refuses it (XC-158).

        Refused everywhere when the bounded config has no `MANUAL_REWARD_ENTRY`, which
        **no other entry replaces**, and when the allocation has no `MANUAL_REWARD` code,
        since the recording could not show it.

        **A pump fault is not caught**, as `welfare.Rig` catches none for a task's reward:
        during a run the session ends on it as a fault, with the reward charged; outside
        one it goes on to `wlx taskd`, which ends on it, records the return as not
        recorded, and leaves the animal stranded for its next start.

        Welfare-critical (`docs/design/architecture.md`): it delivers fluid."""
        if self.phase == "running":
            if self.stopped_because:
                self._refuse(
                    "reward",
                    by,
                    f"the session is stopping ({self.stopped_because}); no reward was given",
                )
                return
            if self.paused_at is None:
                self._refuse(
                    "reward",
                    by,
                    "the session is not paused, and a manual reward is given only while it "
                    "is; no reward was given",
                )
                return
            if not held:
                self._refuse(
                    "reward",
                    by,
                    "the session's pause has not begun holding yet, and a manual reward is "
                    "given only while it is; no reward was given -- press again once the "
                    "page shows the session paused",
                )
                return
            if (
                self.scheduled_stop is not None
                and self.scheduled_stop[0] == "fluid"
                and self.welfare.session_total()
                >= self.scheduled_stop[1] - FLUID_TOLERANCE_ML
            ):
                self._refuse(
                    "reward",
                    by,
                    f"the session has reached its scheduled stop {self.scheduled_stop[3]}, "
                    f"so no reward is given; it ends at this pass",
                )
                return
            where = f"given while paused before trial {index}"
        elif self.service and self.phase in OUTSIDE_A_RUN:
            where = (
                "given between runs"
                if self.phase == "between_runs"
                else "given while the animal's return is awaited"
            )
        else:
            self._refuse(
                "reward",
                by,
                "the session has ended, and outside a run a manual reward is given only in "
                "a wlx taskd session, between runs or while its animal's return is awaited "
                "-- one after a wlx run session's run waits on XC-184; no reward was given",
            )
            return
        if MANUAL_REWARD_ENTRY not in self.spec.bounds.ceilings:
            self._refuse(
                "reward",
                by,
                f"this subject's bounded config has no {MANUAL_REWARD_ENTRY!r} entry, so "
                f"a manual reward has no size, and it is never taken from another "
                f"entry; no reward was given",
            )
            return
        code = self._code("MANUAL_REWARD")
        if code is None:
            self._refuse(
                "reward",
                by,
                "this session's allocation has no MANUAL_REWARD event code, so the "
                "recording could not show the reward; no reward was given",
            )
            return
        ml = self.spec.bounds.value(MANUAL_REWARD_ENTRY)
        self.card.emit(code)
        self.rig.reward(MANUAL_REWARD_ENTRY)
        self._control(
            "reward",
            by,
            f"{ml:g} mL of {MANUAL_REWARD_ENTRY}, {where}",
            index,
            at=self.welfare.last_delivery_wall_at,
            ml=ml,
            entry=MANUAL_REWARD_ENTRY,
        )
```

(The four refusals during a run, the two refusals after them, the delivery and the record row are the b2a code unchanged; what is new is the phase test around them, the `where` words, and the refusal for anywhere else.)

Replace `Session.receive`'s docstring with:

```python
        """A console command that reached this session outside a run (`wlx taskd`, between
        runs or awaiting the return): `_command` gives a manual reward (P4d-2b spec
        §6.0), joins a mark's note, or refuses it for its phase."""
```

- [ ] **Step 5: A reward with no session open**

In `wl_xcon/service.py`, `Service._route`, between

```python
        elif self.session is not None:
            self.session.receive(command)
```

and the final `else:`, add:

```python
        elif isinstance(command, _link.ManualReward):
            # Spec §6.0: with no session open the button flushes the line, counted to no
            # animal -- a slice of its own (XC-158). Until then, refused as a reward.
            self._refuse(
                "reward",
                command.by,
                "no session is open, so no reward was given: a reward with no session "
                "open, which flushes the line, waits on XC-158",
            )
```

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest tests/test_taskd.py tests/test_service.py -q -p no:cacheprovider`
Expected: all pass, `test_a_manual_reward_at_any_other_time_is_refused_and_nothing_is_given` and every b2a manual-reward test among them, unchanged.

- [ ] **Step 7: The welfare-critical paragraph says what the code now does**

In `docs/design/architecture.md`, in the paragraph that begins `**The three `taskd` functions are `Session._ends`, `Session._hold` and `Session._manual_reward`**`, replace from `` `_hold` is the paused loop: `` through `` so a change to that pass-through is also a change to welfare-critical behavior. `` with:

```markdown
`_hold` is the paused loop:
no trial runs, so the task rewards nothing; each pass still drains, publishes and asks
`_ends`; and during a run the commands it drains are the only ones a manual reward is
given for. `_manual_reward` gives one: a person's press of *give reward*, one delivery of
the bounded config's `reward_correct` through `welfare.Rig.reward`, strobed
`MANUAL_REWARD` first -- during a run only while it is held paused, and since P4d-2b b3a-2
(spec §6.0, PI 2026-09-29) in a `wlx taskd` session between runs and while its animal's
return is awaited -- and refused at any other time: during a trial (XC-157), with no
session open (XC-158), after a `wlx run` session's run (XC-184). `Session._command` hands
every reward to `_manual_reward` first, in every phase, with `held`, which only `_hold`
sets -- so a change to that pass-through is also a change to welfare-critical behavior.
```

and change the sentence's last clause that follows, `a reward given while trials run or paid from another entry`, to `a reward given while trials run, given outside a run where no session is open to count it, or paid from another entry`.

In the `console` row, change `` `ManualReward` (a manual reward, given only while paused) `` to `` `ManualReward` (a manual reward: while paused and, in a `wlx taskd` session, between runs and while the return is awaited) ``.

- [ ] **Step 8: File what this defers**

In `docs/backlog.md`, add under `## Features not yet planned`, after XC-183's line (using the next free ID, as Task 1 Step 9 says):

```markdown
- **XC-184** The console's manual reward after a `wlx run` session's run, while its return is awaited at the terminal (spec §6.0's "awaiting the return"); `await_return` drains the link on a thread beside the terminal's, so a reward must not land after the return is recorded (welfare-critical). — 2026-09-30, [b3a-2 plan, decision 4](superpowers/plans/2026-09-30-p4d2b-b3a2-page-sessions.md#plan-decisions) — waits on: nothing
```

and raise the next free ID to `**Next free ID: XC-185.**`

- [ ] **Step 9: The whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add wl_xcon/taskd.py wl_xcon/service.py tests/test_taskd.py tests/test_service.py docs/design/architecture.md docs/backlog.md
git commit -m "Give a hand reward between runs and while the return is awaited"
```

---

### Task 3: `POST /commands` takes the service's four commands

**Files:**
- Modify: `wl_xcon/link.py` (`_decode_command` split: new `_command_from`)
- Modify: `wl_xcon/serve.py` (module docstring; `_SHAPES`; new `_SERVICE_KINDS`, `SERVICE_SENT`; `parse_command`; `_delivered`; `Server.dispatch`)
- Test: `tests/test_serve.py`

**Interfaces:**
- Consumes: b3a-1's `link.OpenSession`, `CheckRun`, `StartRun`, `EndSession` and their decoding rules.
- Produces: `link._command_from(data: dict) -> Command` (raises `CommandRefused` for a malformed command, `ValueError` for an unknown kind); `serve.parse_command` returns an `OpenSession` / `CheckRun` / `StartRun` / `EndSession` for a body of kind `open` / `check` / `start` / `end` whose fields are the wire's own names -- `open`: `session_id`, `animal`, `deployment`, `view`, `departure`, `delivered_today`, `answer`, `amend_to`, `amend_reason`; `check`: `task`, `values`; `start`: `task`, `values`, `trials`, `acknowledged`; `end`: `session_id`, `returned`, `confirm`; `serve.SERVICE_SENT` (the *sent* sentence for these four); `serve._delivered(command, said=SENT)`. Task 6's script sends exactly these bodies; Task 7 posts them.

- [ ] **Step 1: Write the failing tests**

In `tests/test_serve.py`, add `CheckRun`, `EndSession`, `OpenSession` and `StartRun` to the `from wl_xcon.link import (...)` list, and `SENT` and `SERVICE_SENT` to the `from wl_xcon.serve import (...)` list; then, after `test_a_parse_refusal_is_a_bad_command`:

```python
# --- P4d-2b b3a-2: the service's commands from the page ------------------------------

#: The page's `open` body, every field as the *New session* dialog sends it.
OPEN_BODY = {
    "kind": "open", "by": "jake", "session_id": "2027-01-14_01", "animal": "REFERENCE",
    "deployment": "rig_fixed", "view": "direct", "departure": "09:30",
    "delivered_today": 12, "answer": None, "amend_to": None, "amend_reason": "",
}
START_BODY = {
    "kind": "start", "by": "jake", "task": "fixation_detection.py", "values": {},
    "trials": 3, "acknowledged": ["pump calibration", "eye tracker"],
}
END_BODY = {"kind": "end", "by": "jake", "session_id": None, "returned": None, "confirm": False}
PAGE = "jake (box, unverified)"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (OPEN_BODY, OpenSession(
            by=PAGE, session_id="2027-01-14_01", animal="REFERENCE", deployment="rig_fixed",
            view="direct", departure="09:30", delivered_today=12.0, answer=None,
            amend_to=None, amend_reason="",
        )),
        ({**OPEN_BODY, "answer": "amend", "amend_to": "09:10", "amend_reason": "typed 9:30"},
         OpenSession(
            by=PAGE, session_id="2027-01-14_01", animal="REFERENCE", deployment="rig_fixed",
            view="direct", departure="09:30", delivered_today=12.0, answer="amend",
            amend_to="09:10", amend_reason="typed 9:30",
        )),
        ({"kind": "check", "by": "jake", "task": "fixation_detection.py", "values": {}},
         CheckRun(by=PAGE, task="fixation_detection.py", values={})),
        (START_BODY, StartRun(
            by=PAGE, task="fixation_detection.py", values={}, trials=3,
            acknowledged=("pump calibration", "eye tracker"),
        )),
        ({**END_BODY, "session_id": "2027-01-14_01", "returned": "now"},
         EndSession(by=PAGE, session_id="2027-01-14_01", returned="now", confirm=False)),
        (END_BODY, EndSession(by=PAGE, session_id=None, returned=None, confirm=False)),
    ],
    ids=["open", "open-amended", "check", "start", "end-with-return", "end-return-later"],
)
def test_each_session_command_the_page_sends_is_the_one_the_wire_would_decode(body, expected):
    """The b3a-2 plan, decision 3: a page's body is built by the wire's own function, so
    it is checked by exactly the rules the rig checks the packet by."""
    import msgpack

    from wl_xcon.link import _decode_command

    assert parse_command(body) == expected
    assert _decode_command(msgpack.packb({**body, "by": PAGE}, use_bin_type=True)) == expected


@pytest.mark.parametrize(
    ("body", "said"),
    [
        ({**OPEN_BODY, "session_id": 7}, "session_id is text of 1 to 200 characters"),
        ({**OPEN_BODY, "departure": ""}, "departure is text of 1 to 200 characters"),
        ({**OPEN_BODY, "deployment": "cage_side"}, "deployment is rig_fixed or rig_chaired"),
        ({**OPEN_BODY, "view": "both"}, "setup is direct or stereoscope"),
        ({**OPEN_BODY, "delivered_today": "lots"}, "delivered_today is mL or nothing"),
        ({**OPEN_BODY, "delivered_today": float("inf")}, "delivered_today is mL or nothing"),
        ({**OPEN_BODY, "answer": "yes"}, "answered confirm, amend or none"),
        ({"kind": "check", "by": "jake", "task": "", "values": {}}, "task is text of 1 to 200"),
        ({"kind": "check", "by": "jake", "task": "t.py", "values": [1]}, "at most 64 named settings"),
        ({**START_BODY, "trials": "3"}, "trials are a whole number from 1"),
        ({**START_BODY, "trials": True}, "trials are a whole number from 1"),
        ({**START_BODY, "acknowledged": "pump calibration"}, "acknowledged items are at most 16 names"),
        ({**START_BODY, "values": {"fix_hold": True}}, "a setting is a finite number"),
        ({**END_BODY, "confirm": "yes"}, "confirm is true or false"),
        ({**END_BODY, "returned": ""}, "returned is text of 1 to 200"),
        ({**END_BODY, "extra": 1}, "a end command takes no extra"),
        ({**OPEN_BODY, "by": " "}, "every command records who sent it"),
    ],
)
def test_a_malformed_session_command_is_refused_with_the_wires_sentence(body, said):
    """Review Focus 3: never a traceback, and the sentence the rig would have given."""
    with pytest.raises(BadCommand) as refused:
        parse_command(body)

    assert said in str(refused.value)


def test_a_session_command_from_the_boxs_page_is_dispatched_and_a_malformed_one_is_not():
    """Spec §2's four checks, as for b2a's commands: the box's page's `open` reaches the
    command path as the person named; a malformed one is a JSON 400 and reaches
    nothing."""
    dispatch = _Dispatch((200, {"status": "sent", "said": SERVICE_SENT}))
    with _served(_hub(), dispatch=dispatch) as port:
        sent = _post(port, OPEN_BODY)
        refused = _post(port, {**START_BODY, "trials": "3"})

    assert sent == (200, {"status": "sent", "said": SERVICE_SENT})
    assert refused[0] == 400 and refused[1]["said"].startswith("not sent: ")
    assert [type(request) for request in dispatch.seen] == [OpenSession]
    assert dispatch.seen[0].by == PAGE


def test_the_services_commands_are_answered_with_what_the_page_shows_next(zmq_cleanup):
    """*Sent* for one of `wlx taskd`'s commands says the page shows what it did; b2a's
    sentence -- "acts on it at its next trial boundary" -- is a run's, and stays theirs.
    Each is handed to the command thread once."""
    pub, rep = _endpoints(zmq_cleanup)
    server = Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN)
    sender = _Answers(None)
    server._commands.submit = lambda work: work(sender)
    check = CheckRun(by=PAGE, task="fixation_detection.py", values={})

    assert server.dispatch(check) == (200, {"status": "sent", "said": SERVICE_SENT})
    assert server.dispatch(Stop(by=PAGE)) == (200, {"status": "sent", "said": SENT})
    assert sender.sent == [check, Stop(by=PAGE)]
    assert SERVICE_SENT == (
        "sent: the rig has it; the page shows what it did -- a session, a pre-flight, a "
        "run, a question to answer, or a refusal with its reason"
    )
```

(`_Answers` and `_endpoints` are defined further down the file; they exist when the test runs.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_serve.py -q -p no:cacheprovider -k "session_command or services_commands"`
Expected: FAIL -- `ImportError: cannot import name 'SERVICE_SENT'`; once that exists, `BadCommand: 'open' is not a command this console sends`.

- [ ] **Step 3: One function builds a command from its fields**

In `wl_xcon/link.py`, split `_decode_command`: keep its name, signature and docstring -- changing its last paragraph's opening "**Every field is checked here, before a command exists**" to "**Every field is checked before a command exists** (`_command_from`)" -- and make its body

```python
    import msgpack

    return _command_from(msgpack.unpackb(payload, raw=False))
```

then add directly after it:

```python
def _command_from(data: dict) -> Command:
    """A command from its fields, every one checked before a command exists (M8, P4d-2b
    b2a): what `_decode_command` reads off the wire, and since P4d-2b b3a-2 what
    `serve.parse_command` builds `wlx taskd`'s four commands from, so a page's body is
    checked by exactly the rules the rig checks the packet by (the b3a-2 plan, decision
    3). Raises `CommandRefused` for a command that is malformed, naming what it could of
    the parameter and the sender, `ValueError` for a kind this file does not know, and
    whatever a mapping raises for data that is not one."""
```

whose body is everything `_decode_command`'s body held after `data = msgpack.unpackb(payload, raw=False)` -- from `kind = data["kind"]` to the final `raise ValueError(f"unknown command kind on the wire: {_quoted(kind)}")` -- moved unchanged.

- [ ] **Step 4: `wlx serve` takes the four**

In `wl_xcon/serve.py`:

Add to `_SHAPES`:

```python
    # P4d-2b b3a-2: `wlx taskd`'s own, by the wire's field names (`link._command_from`).
    "open": frozenset({
        "session_id", "animal", "deployment", "view", "departure", "delivered_today",
        "answer", "amend_to", "amend_reason",
    }),
    "check": frozenset({"task", "values"}),
    "start": frozenset({"task", "values", "trials", "acknowledged"}),
    "end": frozenset({"session_id", "returned", "confirm"}),
```

After `_SCHEDULES`, add:

```python
#: The kinds `wlx taskd` takes that the page sends by the wire's own field names, built
#: by the wire's own function (`link._command_from`; the b3a-2 plan, decision 3).
_SERVICE_KINDS = frozenset({"open", "check", "start", "end"})
```

After `REWARD_UNKNOWN`, add:

```python
#: What the page is told when the rig has one of `wlx taskd`'s own commands -- an open,
#: a check, a start or an end (P4d-2b b3a-2): what it did is the page's to show from
#: the frames that follow, as a session, a pre-flight, a run, the question a far mark
#: raises, or a refusal with its sentence. `SENT`'s "at its next trial boundary" is a
#: run's command's, and not true of an open between runs.
SERVICE_SENT = (
    "sent: the rig has it; the page shows what it did -- a session, a pre-flight, a run, "
    "a question to answer, or a refusal with its reason"
)
```

In `parse_command`, directly after the `extra` check (`if extra: raise BadCommand(...)`), add:

```python
    if kind in _SERVICE_KINDS:
        try:
            return _link._command_from({**data, "by": by})
        except _link.CommandRefused as refused:
            raise BadCommand(refused.why) from refused
```

Replace `_delivered` with:

```python
def _delivered(command, said: str = SENT) -> Callable[[object], tuple[int, dict]]:
    """The command thread's work for one command: deliver it and say so, in `said`, or
    say why not (spec §5.3)."""

    def work(commands) -> tuple[int, dict]:
        try:
            commands.deliver(command)
        except _link.NotDelivered as exc:
            return not_delivered(str(exc))
        return 200, {"status": "sent", "said": said}

    return work
```

In `Server.dispatch`, before the `MarkNote` branch, add:

```python
        if isinstance(
            request, (_link.OpenSession, _link.CheckRun, _link.StartRun, _link.EndSession)
        ):
            return self._commands.submit(_delivered(request, SERVICE_SENT))
```

In the module docstring's `POST /commands` bullet, after "the truth about delivery.", add: "Since P4d-2b b3a-2 it also takes `wlx taskd`'s own four -- `open`, `check`, `start`, `end` -- built by the wire's own rules (`link._command_from`)."

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_serve.py tests/test_link.py -q -p no:cacheprovider`
Expected: all pass -- every existing decode test in `test_link.py` unchanged.

- [ ] **Step 6: The whole suite, then commit**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

```bash
git add wl_xcon/link.py wl_xcon/serve.py tests/test_serve.py
git commit -m "Take wlx taskd's open, check, start and end at POST /commands, by the wire's rules"
```

---

### Task 4: The page's run controls -- the task, the pre-flight, *start run*, and the hand reward outside a run

**Files:**
- Modify: `wl_xcon/web.py` (imports; new `UNPLANNED`, `RUN_TRIALS`, `_DOTS`; `FRAGMENT_IDS`; new `_options`, `_pf_state`, `_pf_pill`, `_pf_sum`, `_pf_row`, `_preflight_pane`, `_start_button`, `_mark_button`, `_hand_reward_now`, `_outside_a_run`; `_reward_button`, `_reward_answer`, `_controls`; `fragments`, `_idle`; `page`'s control bar and Setup tab; `_CSS`)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `link.Preflight`, `PreflightItem`, `Telemetry.offered_tasks`, `.preflight`, `.service`, `.phase`; `Idle.offered_tasks`; Task 2's phases for the hand reward.
- Produces, for Tasks 5-7: fragments `task-sel` (the Task select's `<option>`s), `pf-pill` (a `<button ... data-cmd="check">` between runs, a `<span>` otherwise), `pf-sum` (the Setup panel's pill), `preflight` (the rows, each unknown with `<input type="checkbox" data-ack="NAME" ...>`, inside `<div class="pf" data-task="TASK">`); in `controls`, between runs, `<button type="button" class="btn go" data-cmd="start" data-task="TASK"...>start run</button>`; *give reward* and *mark* live between runs and while the return is awaited; b2a's stop labeled `stop run`. Static in `page`: `<select id="task-sel">` and `<input ... id="run-trials" value="1000">`. `web.UNPLANNED`, `web.RUN_TRIALS`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, add `Preflight` and `PreflightItem` to the `from wl_xcon.link import ...` line, `RUN_TRIALS` and `UNPLANNED` to the `from wl_xcon.web import (...)` list, `from dataclasses import replace`, and at the end of the file:

```python
# --- P4d-2b b3a-2: sessions from the page ---------------------------------------------


def _between(**over):
    """A `wlx taskd` session between runs, its first run ended, one task offered."""
    fields = dict(
        phase="between_runs", service=True, run_index=0, stop_kind="completed",
        stopped_because="every block is finished", offered_tasks=("fixation_detection.py",),
    )
    fields.update(over)
    return frame(**fields)


#: A pre-flight as `wlx taskd` takes one (`preflight.py`'s item names), two items passing
#: and the two nothing measures yet unknown.
PREFLIGHT = Preflight(
    "fixation_detection.py",
    (
        PreflightItem("task checks", "pass", "fixation_detection.py passes its load-time checks"),
        PreflightItem("out of cage", "pass", "the departure is marked and the limit is not reached"),
        PreflightItem("pump calibration", "unknown", "no pump calibration has been measured (V10)"),
        PreflightItem("eye tracker", "unknown", "nothing reports the eye tracker's health yet"),
    ),
)
FAILING = replace(
    PREFLIGHT,
    items=(PREFLIGHT.items[0], PreflightItem("out of cage", "fail", "past <the> limit"))
    + PREFLIGHT.items[2:],
)


def test_the_task_chooser_offers_what_wlx_taskd_offers_and_says_when_there_is_nothing():
    only = '<option value="fixation_detection.py">fixation_detection.py</option>'

    assert fragments(_between(), view())["task-sel"] == only
    assert fragments(idle(), view())["task-sel"] == only
    assert fragments(frame(), view())["task-sel"] == '<option value="">no task offered</option>'
    assert fragments(None, view())["task-sel"] == '<option value="">no task offered</option>'


@pytest.mark.parametrize(
    ("preflight", "tone", "said"),
    [
        (None, "neutral", "pre-flight · not taken"),
        (PREFLIGHT, "warn", "pre-flight · 2 to acknowledge"),
        (FAILING, "crit", "pre-flight · 1 fail"),
        (replace(PREFLIGHT, items=PREFLIGHT.items[:2]), "ok", "pre-flight ✓"),
    ],
    ids=["not-taken", "unknowns", "a-fail", "all-pass"],
)
def test_between_runs_the_preflight_pill_is_a_button_that_says_what_the_rig_found(
    preflight, tone, said
):
    """The mockup's `pf-pill` and `pf-sum` (the b3a-2 plan, decisions 6 and 7): its words
    from the frame's pre-flight, and, between runs, a button that takes the pre-flight."""
    parts = fragments(_between(preflight=preflight), view())

    assert parts["pf-pill"] == (
        f'<button type="button" class="pill {tone}" data-cmd="check" '
        f'title="take the pre-flight for the task chosen">{said}</button>'
    )
    assert parts["pf-sum"] == f'<span class="pill {tone}">{said}</span>'


@pytest.mark.parametrize(
    ("shown", "said"),
    [
        (None, "no session"),
        (idle(), "no session"),
        (frame(), "pre-flight · wlx run takes none"),
        (frame(service=True), "pre-flight · taken as the run started"),
        (_between(phase="awaiting_return"), "pre-flight · the session has ended"),
    ],
    ids=["no-frame", "idle", "wlx-run", "a-run-going", "ended"],
)
def test_outside_between_runs_the_preflight_pill_only_says_why_there_is_none(shown, said):
    assert fragments(shown, view())["pf-pill"] == f'<span class="pill neutral">{said}</span>'


def test_the_preflight_panel_shows_each_item_its_result_and_the_unplanned_warning():
    shown = fragments(_between(preflight=FAILING), view())["preflight"]

    assert '<span class="st fail" title="fail"></span><span>out of cage</span>' in shown
    assert '<span class="st pass" title="pass"></span><span>task checks</span>' in shown
    assert '<span class="st untested" title="unknown"></span><span>eye tracker</span>' in shown
    assert "past &lt;the&gt; limit" in shown
    assert html.escape(UNPLANNED) in shown
    assert 'data-task="fixation_detection.py"' in shown
    assert "not taken" in fragments(_between(), view())["preflight"]


def test_each_unknown_item_has_an_unticked_acknowledgement_carrying_its_exact_name():
    """Review Focus 4 (the b3a-2 plan, decision 9): one box per unknown item, its exact
    name on it for the start to send, never rendered ticked -- a tick is the person's,
    for the run about to start -- and greyed away from the box."""
    shown = fragments(_between(preflight=PREFLIGHT), view())["preflight"]
    lan = fragments(_between(preflight=PREFLIGHT), view(can_write=False))["preflight"]

    for name in ("pump calibration", "eye tracker"):
        assert (
            f'<label class="chk"><input type="checkbox" data-ack="{name}" '
            f'aria-label="acknowledge {name}"> acknowledge</label>'
        ) in shown
    assert shown.count("data-ack=") == 2, "only an unknown is acknowledged"
    assert "checked" not in shown
    boxes = re.findall(r"<input[^>]*data-ack[^>]*>", lan)
    assert boxes and all(" disabled" in box for box in boxes)


def test_between_runs_start_run_carries_the_shown_preflights_task_and_waits_for_one_with_no_fail():
    """The b3a-2 plan, decision 8, and spec §6.2: "the start refused while any item
    fails" -- greyed with its reason in the page, and refused by the rig anyway."""
    none = fragments(_between(), view())["controls"]
    ready = fragments(_between(preflight=PREFLIGHT), view())["controls"]
    failing = fragments(_between(preflight=FAILING), view())["controls"]

    assert (
        '<button type="button" class="btn go" data-cmd="start" data-task="" disabled '
        'title="take the pre-flight first: choose a task, or press the pre-flight pill">'
        "start run</button>"
    ) in none
    assert (
        '<button type="button" class="btn go" data-cmd="start" '
        'data-task="fixation_detection.py">start run</button>'
    ) in ready
    assert 'disabled title="pre-flight: out of cage failing">start run</button>' in failing
    assert html.escape(UNPLANNED) in ready
    assert 'data-cmd="pause"' not in ready and 'data-cmd="stop"' not in ready


@pytest.mark.parametrize("phase", ["between_runs", "awaiting_return"])
def test_outside_a_run_the_hand_reward_and_mark_are_live_with_what_the_last_press_did(phase):
    """PI, 2026-09-29 (spec §6.0): *give reward* works between runs and while the return
    is awaited in a `wlx taskd` session, and says beside itself what the rig did."""
    controls = fragments(
        _between(
            phase=phase,
            fluid_session_ml=0.4,
            controls=(
                Control("reward", "jake (box, unverified)", 1_700_000_035.0,
                        "0.15 mL of reward_correct, given between runs"),
            ),
        ),
        view(),
    )["controls"]

    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in controls
    assert '<button type="button" class="btn" data-cmd="mark">mark (M)</button>' in controls
    assert "fluid session 0.40 mL" in controls
    assert "0.15 mL of reward_correct, given between runs" in controls


def test_while_the_return_is_awaited_there_is_no_run_to_start():
    controls = fragments(_between(phase="awaiting_return"), view())["controls"]

    assert "session ended · waiting for the animal&#x27;s return" in controls
    assert 'data-cmd="start"' not in controls


def test_a_wlx_run_session_after_its_run_offers_no_hand_reward():
    """XC-184: its return is taken at its terminal, and the rig refuses a press then."""
    assert "give reward" not in fragments(frame(**STATES["awaiting return"]), view())["controls"]


def test_away_from_the_box_the_run_controls_are_greyed_with_the_sentence():
    parts = fragments(_between(preflight=PREFLIGHT), view(on_box=False, can_write=False))
    written = parts["controls"] + parts["pf-pill"] + parts["preflight"]

    buttons = re.findall(r"<button[^>]*data-cmd[^>]*>", written)
    assert buttons and all(" disabled" in tag for tag in buttons)
    assert CONTROLS_AT_THE_BOX in parts["controls"]


def test_the_control_bar_offers_the_task_the_trials_and_the_preflight_as_the_mockup_draws_them():
    """The mockup's toolbar (`task-sel`, `pf-pill`), with the run's trial count beside the
    task (the b3a-2 plan, decision 6): the select's options are a fragment, the count is
    static, and it starts at `wlx run --trials`'s default."""
    document = page(fragments(_between(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert '<label class="tsel" for="task-sel"><span class="k">Task</span><select id="task-sel" aria-label="task">' in document
    assert (
        f'<input class="field mono" id="run-trials" value="{RUN_TRIALS}" inputmode="numeric" '
        f'autocomplete="off" aria-label="trials">'
    ) in document
    assert RUN_TRIALS == 1000
    assert document.index('id="task-sel"') < document.index('id="pf-pill"') < document.index('id="controls"')
    assert "<h2>Pre-flight</h2>" in document and "<h2>Session</h2>" in document
    assert document.index('id="pf-panel"') < document.index('id="setup"')
```

And change two b2a/b3a-1 tests:

In `test_the_controls_offer_pause_mark_and_stop_while_running`, change

```python
    assert '<button type="button" class="btn danger" data-cmd="stop">stop…</button>' in controls
```

to

```python
    assert '<button type="button" class="btn danger" data-cmd="stop">stop run</button>' in controls
```

Replace `test_the_page_between_runs_says_which_run_ended_and_offers_no_run_controls` with:

```python
def test_the_page_between_runs_says_which_run_ended_and_offers_start_run_not_pause_or_stop():
    panes = fragments(
        frame(phase="between_runs", service=True, run_index=1, stop_kind="operator", stopped_because="stopped by jake"),
        view(),
    )

    assert 'data-state="between-runs"' in panes["state"] and "run 1 ended" in panes["state"]
    assert "Run 1 ended" in panes["banners"]
    assert 'data-cmd="start"' in panes["controls"]
    assert 'data-cmd="pause"' not in panes["controls"] and 'data-cmd="stop"' not in panes["controls"]
    assert '<span class="k">Run</span><span class="v">1</span>' in panes["head-id"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_web.py -q -p no:cacheprovider`
Expected: FAIL -- `ImportError: cannot import name 'RUN_TRIALS'`, then `KeyError: 'task-sel'` and the rest.

- [ ] **Step 3: The new panes**

In `wl_xcon/web.py`, change `from wl_xcon.link import RECENT_OUTCOMES, Idle, Telemetry` to `from wl_xcon.link import RECENT_OUTCOMES, Idle, Question, Telemetry`, and replace the `#:` comment above `REWARD_ONLY_PAUSED` (its value stays, `test_the_reward_button_is_live_only_while_paused_and_greyed_otherwise` pins it) with:

```python
#: Why *give reward* is greyed while a run's trials run: during a run the rig gives a
#: manual reward only while it is paused (PI, 2026-09-28); outside a run, in a `wlx
#: taskd` session, it gives one between runs and while the return is awaited (PI,
#: 2026-09-29, spec §6.0; `taskd.Session._manual_reward`).
```

Replace `FRAGMENT_IDS` with:

```python
FRAGMENT_IDS = (
    "state",
    "head-id",
    "presence",
    "strip",
    "banners",
    "task-sel",
    "pf-pill",
    "controls",
    "rt-trials",
    "rt-work",
    "rt-need",
    "rt-wrong",
    "rt-health",
    "rt-changes",
    "params",
    "pf-sum",
    "preflight",
    "setup",
    "end",
)
```

After `DEBOUNCE_MS`, add:

```python
#: What the page says beside *start run* and atop every pre-flight (P4d-2b spec §6.2:
#: "Every run is unplanned until b3b brings the day's plan, and the page says so each
#: time, with the warning that an unplanned run lowers the session's timing tier").
UNPLANNED = (
    "unplanned run: no day's plan reaches this rig yet (b3b), and an unplanned run lowers "
    "the session's timing tier"
)
#: The trials a run is offered with: `wlx run --trials`'s default (`cli`), since until the
#: day's plan (b3b) a run from the page is `wlx run`'s flat run of N trials (the b3a-2
#: plan, decision 6). A starting figure the person changes, not a rule or a measurement.
RUN_TRIALS = 1000
```

Before `# --- the controls (P4d-2b b2a)`, add the pre-flight section:

```python
# --- the run's task and its pre-flight (P4d-2b b3a-2) ------------------------------


def _options(names, none: str) -> str:
    """A select's options, one per name, or one empty option saying why there is none.
    A frame re-renders them; the page's script keeps the option a person chose (the
    b3a-2 plan, decision 11)."""
    if not names:
        return f'<option value="">{_e(none)}</option>'
    return "".join(f'<option value="{_e(name)}">{_e(name)}</option>' for name in names)


def _pf_state(frame: Telemetry | Idle | None) -> tuple[str, str]:
    """The pre-flight pill's tone and words (the mockup's `drawPreflight`), from the
    frame's pre-flight: a fail counts first, then the unknowns a person acknowledges --
    an item that is neither pass nor unknown counts as a fail, as `preflight.gate`
    counts it -- and outside a `wlx taskd` session between runs, why there is none."""
    if frame is None or isinstance(frame, Idle):
        return "neutral", "no session"
    if not frame.service:
        return "neutral", "pre-flight · wlx run takes none"
    if frame.phase == "running":
        return "neutral", "pre-flight · taken as the run started"
    if frame.phase != "between_runs":
        return "neutral", "pre-flight · the session has ended"
    if frame.preflight is None:
        return "neutral", "pre-flight · not taken"
    items = frame.preflight.items
    fails = sum(1 for item in items if item.result not in ("pass", "unknown"))
    unknown = sum(1 for item in items if item.result == "unknown")
    if fails:
        return "crit", f"pre-flight · {fails} fail"
    if unknown:
        return "warn", f"pre-flight · {unknown} to acknowledge"
    return "ok", "pre-flight ✓"


def _pf_sum(frame: Telemetry | Idle | None) -> str:
    """The Setup tab's pre-flight pill (the mockup's `pf-sum`)."""
    tone, said = _pf_state(frame)
    return f'<span class="pill {tone}">{_e(said)}</span>'


def _pf_pill(frame: Telemetry | Idle | None, view: View) -> str:
    """The control bar's pre-flight pill (the mockup's `pf-pill`): between runs, a button
    that takes the pre-flight for the task chosen and opens the Setup tab at its panel
    (the b3a-2 plan, decision 7); otherwise the words alone."""
    if isinstance(frame, Telemetry) and frame.service and frame.phase == "between_runs":
        tone, said = _pf_state(frame)
        off = _off(view) or ' title="take the pre-flight for the task chosen"'
        return (
            f'<button type="button" class="pill {tone}" data-cmd="check"{off}>'
            f"{_e(said)}</button>"
        )
    return _pf_sum(frame)


#: A result's dot (the mockup's `.st`): an unknown is what nothing measured, which the
#: mockup draws as the hollow *untested* ring; anything but pass or unknown is a fail.
_DOTS = {"pass": "pass", "unknown": "untested"}


def _pf_row(item, view: View) -> str:
    """One pre-flight item: its dot, name and sentence, and -- for an unknown -- the box
    that acknowledges it, carrying its exact name and never ticked here (decision 9)."""
    acknowledge = (
        f'<label class="chk"><input type="checkbox" data-ack="{_e(item.name)}" '
        f'aria-label="acknowledge {_e(item.name)}"{_off(view)}> acknowledge</label>'
        if item.result == "unknown"
        else "<span></span>"
    )
    return (
        f'<div class="row"><span class="st {_DOTS.get(item.result, "fail")}" '
        f'title="{_e(item.result)}"></span><span>{_e(item.name)}</span>'
        f'<span class="val">{_e(item.said)}</span>{acknowledge}</div>'
    )


def _preflight_pane(frame: Telemetry | Idle | None, view: View) -> str:
    """The Setup tab's pre-flight (the mockup's `pf-panel`, drawn from `wlx taskd`'s items
    rather than the mockup's list: spec §6.2): one row per item, under a line naming the
    task, S9a §10's rule and the unplanned warning. The mockup's *must* tag is left out,
    since every fail blocks (the b3a-2 plan, decision 6)."""
    if frame is None or isinstance(frame, Idle):
        return _NONE
    if not frame.service:
        return '<span class="nm">wlx run takes no pre-flight (XC-159)</span>'
    if frame.phase == "running":
        return (
            '<span class="nm">a run is in progress: its pre-flight was taken as it '
            "started, and its start row in runs.jsonl holds it</span>"
        )
    if frame.phase != "between_runs":
        return '<span class="nm">the session has ended: no run starts in it</span>'
    if frame.preflight is None:
        return (
            '<span class="nm">not taken: choose a task, or press the pre-flight '
            "pill</span>"
        )
    task = _e(frame.preflight.task)
    rows = "".join(_pf_row(item, view) for item in frame.preflight.items)
    return (
        f'<div class="sub">for {task} · a fail blocks the run; each unknown starts it only '
        f"on your acknowledgement, by name, written into runs.jsonl · {_e(UNPLANNED)}</div>"
        f'<div class="pf" data-task="{task}">{rows}</div>'
    )
```

- [ ] **Step 4: The control bar's buttons**

Replace `_reward_button`, `_reward_answer` and `_controls` whole with:

```python
def _hand_reward_now(frame: Telemetry) -> bool:
    """Whether the rig gives a manual reward now (`taskd.Session._manual_reward`): a run
    held paused (PI, 2026-09-28), or a `wlx taskd` session between runs or awaiting its
    animal's return (PI, 2026-09-29, spec §6.0). During a trial it waits on XC-157, and
    after a `wlx run` session's run on XC-184."""
    return frame.paused_at is not None or (
        frame.service and frame.phase in ("between_runs", "awaiting_return")
    )


def _reward_button(frame: Telemetry, view: View) -> str:
    """The manual reward's button (PI, 2026-09-28 and 2026-09-29): live whenever the rig
    gives one (`_hand_reward_now`), and greyed with `REWARD_ONLY_PAUSED` while a run's
    trials run, and with the §2 sentence away from the box. **One button and no key**:
    a click is one command, and the script holds the button until that command's
    answer."""
    live = _hand_reward_now(frame)
    off = _off(view) or ("" if live else f' disabled title="{_e(REWARD_ONLY_PAUSED)}"')
    return f'<button type="button" class="btn" data-cmd="reward"{off}>give reward</button>'


def _reward_answer(frame: Telemetry) -> str:
    """Beside a live *give reward*, what became of the last press (PI, 2026-09-28), from
    the frames the rig publishes: the session's fluid total, the newest reward given with
    its size and where, and the newest press refused with the rig's sentence -- *last*,
    since a refusal carries no time, as on a parameter card. Nothing while the button is
    greyed."""
    if not _hand_reward_now(frame):
        return ""
    said = [f"fluid session {frame.fluid_session_ml:.2f} mL"]
    given = [control for control in frame.controls if control.kind == "reward"]
    if given:
        said.append(f"last given {_clock_time(given[-1].at)}: {_e(given[-1].said)}")
    refused = [refusal for refusal in frame.refusals if refusal.name == "reward"]
    if refused:
        said.append(f"last refused: {_e(refused[-1].why)}")
    return f'<span class="nm">{" · ".join(said)}</span>'


def _mark_button(view: View) -> str:
    """*mark (M)*: greyed on its own when this console has no mark endpoint."""
    off = _off(view) or ("" if view.can_mark else f' disabled title="{_e(NO_MARK_ENDPOINT)}"')
    return f'<button type="button" class="btn" data-cmd="mark"{off}>mark (M)</button>'


def _start_button(frame: Telemetry, view: View) -> str:
    """*start run* (the mockup's `a-start`), carrying the task of the pre-flight the frame
    shows: the page's script sends that task, and only while it is the one chosen (the
    b3a-2 plan, decision 8). Greyed, with the reason, until a pre-flight is shown with no
    item failing (spec §6.2); `Service._start` takes the pre-flight again and refuses a
    start it would block anyway."""
    preflight = frame.preflight
    if preflight is None:
        why = "take the pre-flight first: choose a task, or press the pre-flight pill"
    else:
        failing = [i.name for i in preflight.items if i.result not in ("pass", "unknown")]
        why = f"pre-flight: {', '.join(failing)} failing" if failing else None
    task = "" if preflight is None else preflight.task
    off = _off(view) or ("" if why is None else f' disabled title="{_e(why)}"')
    return (
        f'<button type="button" class="btn go" data-cmd="start" data-task="{_e(task)}"'
        f"{off}>start run</button>"
    )


def _outside_a_run(frame: Telemetry, view: View) -> str:
    """A `wlx taskd` session between runs or awaiting its animal's return (spec §6.0,
    §6.2): *start run* between runs, with the unplanned warning beside it, and *give
    reward* and *mark* in both, since the rig gives a hand reward and stamps a mark
    outside a run (the b3a-2 plan, decision 13). Pause and stop have no run to act on."""
    # Concatenated, not an f-string: an apostrophe inside a replacement field of a
    # single-quoted f-string is a syntax error before Python 3.12, and 3.11 is supported.
    lead = (
        _start_button(frame, view) + '<span class="nm">' + _e(UNPLANNED) + "</span>"
        if frame.phase == "between_runs"
        else '<span class="nm">'
        + _e("session ended · waiting for the animal's return")
        + "</span>"
    )
    note = "" if view.can_write else f'<span class="nm">{CONTROLS_AT_THE_BOX}</span>'
    return lead + _reward_button(frame, view) + _mark_button(view) + _reward_answer(frame) + note


def _controls(frame: Telemetry | None, view: View) -> str:
    """Pause or resume, mark, give reward, and stop (spec §5.2), while a run runs; and,
    since P4d-2b b3a-2, *start run*, *give reward* and *mark* outside a run in a `wlx
    taskd` session (`_outside_a_run`).

    **Pause or resume by the session's state**, never a toggle: the page sends what
    the button says, and the click handler's `toggleAllowed` stops a double click
    from sending it twice, as `rewardAllowed` does for a reward (R2, 2026-09-28).
    **Stop run** (the mockup's `a-stop`; b2a's *stop…*) opens the page's confirm step.
    **Mark** is greyed on its own when this console has no mark endpoint, and **give
    reward** while trials run (`_reward_button`). **Everywhere but the box**, every
    control is greyed with the §2 sentence, which is also said beside them."""
    if frame is None:
        return '<span class="nm">controls · no session</span>'
    if frame.service and frame.phase in ("between_runs", "awaiting_return"):
        return _outside_a_run(frame, view)
    if frame.stop_kind is not None:
        return '<span class="nm">controls · the session has ended</span>'
    off = _off(view)
    cmd, label = ("resume", "resume (P)") if frame.paused_at is not None else ("pause", "pause (P)")
    note = "" if view.can_write else f'<span class="nm">{CONTROLS_AT_THE_BOX}</span>'
    return (
        f'<button type="button" class="btn" data-cmd="{cmd}"{off}>{label}</button>'
        f"{_mark_button(view)}"
        f"{_reward_button(frame, view)}"
        f'<button type="button" class="btn danger" data-cmd="stop"{off}>stop run</button>'
        f"{_reward_answer(frame)}{note}"
    )
```

- [ ] **Step 5: The panes in `fragments` and `_idle`**

In `fragments`, add the new keys in `FRAGMENT_IDS`' order:

```python
    return {
        "state": _state(frame),
        "head-id": _head(frame),
        "presence": _presence(view),
        "strip": _strip(frame, view),
        "banners": _banners(frame, view),
        "task-sel": _options(() if frame is None else frame.offered_tasks, "no task offered"),
        "pf-pill": _pf_pill(frame, view),
        "controls": _controls(frame, view),
        "rt-trials": _trials(frame),
        "rt-work": _work(frame),
        "rt-need": _need(frame),
        "rt-wrong": _wrong(frame),
        "rt-health": _health_pane(frame, view),
        "rt-changes": _changes(frame),
        "params": _params(frame, view),
        "pf-sum": _pf_sum(frame),
        "preflight": _preflight_pane(frame, view),
        "setup": _setup(frame),
        "end": _end(frame),
    }
```

In `_idle`, after `panes["rt-changes"] = _idle_refusals(frame)`, add:

```python
    panes["task-sel"] = _options(frame.offered_tasks, "no task offered")
```

- [ ] **Step 6: The control bar and the Setup tab in `page`**

In `page`, replace

```python
  <section class="controlbar glass" aria-label="controls">
    <div class="ctlrow" id="controls">{p['controls']}</div>
```

with

```python
  <section class="controlbar glass" aria-label="controls">
    <label class="tsel" for="task-sel"><span class="k">Task</span><select id="task-sel" aria-label="task"{off}>{p['task-sel']}</select></label>
    <label class="tsel" for="run-trials"><span class="k">Trials</span><input class="field mono" id="run-trials" value="{RUN_TRIALS}" inputmode="numeric" autocomplete="off" aria-label="trials"{off}></label>
    <span id="pf-pill">{p['pf-pill']}</span>
    <span class="sep" aria-hidden="true"></span>
    <div class="ctlrow" id="controls">{p['controls']}</div>
```

and replace the Setup tab's line

```python
        <div class="tabpanel" id="tp-setup"><section class="panel glass"><div class="top"><h2>Setup</h2><span class="sub">read-only</span></div><div id="setup">{p['setup']}</div></section></div>
```

with

```python
        <div class="tabpanel" id="tp-setup">
          <section class="panel glass" id="pf-panel"><div class="top"><h2>Pre-flight</h2><span id="pf-sum">{p['pf-sum']}</span></div><div id="preflight">{p['preflight']}</div></section>
          <section class="panel glass"><div class="top"><h2>Session</h2></div><div id="setup">{p['setup']}</div></section>
        </div>
```

In `_CSS`, before the line `body.stale .strip, body.stale .panels { filter: grayscale(1); opacity: 0.55; }`, add the mockup's rules for these elements:

```css
.controlbar .sep { width: 1px; align-self: stretch; background: var(--rule); margin: 0 4px; }
.tsel { display: inline-flex; align-items: center; gap: 6px; }
.tsel .k { font-family: var(--cond); font-weight: 600; font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.tsel select { font-family: var(--mono); font-size: 13.5px; padding: 4px 6px; }
.tsel .field { width: 5em; border-radius: 3px; }
button.pill { border: 0; cursor: pointer; }
.btn.go { background: var(--ok); border-color: var(--ok); color: var(--bg); }
.pf { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 0 20px; }
.pf .row { display: grid; grid-template-columns: 12px minmax(0, 10em) minmax(0, 1fr) auto; gap: 8px; align-items: center; font-size: 13px; padding: 3px 0; border-bottom: 1px solid var(--rule); min-height: 30px; }
.pf .val { font-family: var(--mono); font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
.st { width: 10px; height: 10px; border-radius: 50%; }
.st.pass { background: var(--ok); } .st.warn { background: var(--warn); } .st.fail { background: var(--crit); } .st.untested { box-shadow: inset 0 0 0 1.5px var(--muted); }
.chk { display: flex; gap: 8px; align-items: center; font-size: 13px; }
```

- [ ] **Step 7: Run the tests**

Run: `python3 -m pytest tests/test_web.py tests/test_serve.py tests/test_health.py -q -p no:cacheprovider`
Expected: all pass. `test_the_page_holds_every_pane_in_the_element_its_stream_swaps` now checks the four new ids too; `test_a_stream_on_the_boxs_page_renders_controls_that_work` still counts one greyed control while trials run.

- [ ] **Step 8: The whole suite, then commit**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

```bash
git add wl_xcon/web.py tests/test_web.py
git commit -m "Show the page's task, pre-flight, start run and the hand reward outside a run"
```

---

### Task 5: The page's session forms -- *new session*, the warning's answers, *end session* in two steps, a stranded animal's return

**Files:**
- Modify: `wl_xcon/web.py` (new `END_CONFIRM`; `FRAGMENT_IDS`; new `_new_session_button`, `_idle_setup`, `_end_actions`; `_question_banner`, `_banners`, `_idle_banners`, `_idle`, `fragments`; `page`'s amendment form, Summary panel, end confirmation, return form and *New session* dialog; `_CSS`)
- Modify: `wl_xcon/taskd.py` (`Session._command`'s awaiting-return sentence -- lexical, Plan decision 16)
- Modify: `wl_xcon/welfare.py` (`Welfare._far_from_now` -- **welfare-critical, words only**, Plan decision 16: a far return's sentence offers what the rig takes)
- Test: `tests/test_web.py`, `tests/test_welfare.py`, `tests/test_taskd.py`, `tests/test_service.py`

**Implement and review on the most capable model: Step 6 changes the words of one sentence in `welfare.py`, which is welfare-critical whole.** Only the words that end a far return's sentence change; the departure's sentence stays byte-identical, and the rule -- the thirty minutes, a string and never an exception, nothing marked -- does not change (the controller's ruling, 2026-09-30).

**Interfaces:**
- Consumes: Task 4's `_between`, `PREFLIGHT` test helpers and `_options`; `link.Question`, `Stranded`, `Idle.animals`; `welfare.Welfare.departure_needs_confirmation`, `return_needs_confirmation` (unchanged; both call `_far_from_now`).
- Produces, for Tasks 6-7: fragments `end-actions` (the Summary's pill with `<button ... data-cmd="end" data-session="ID">end session</button>` while a `wlx taskd` session is open, `<button ... data-return="ID">record return…</button>` while its return is awaited) and `dn-subject` (the dialog's subject options, from `Idle.animals`); in `banners`, each answer `<button type="button" class="btn small" data-answer="ANSWER" data-mark="MARK" data-session="ID">`, a stranded animal's `<button ... data-return="ID">end session…</button>`, and idle `<button ... data-cmd="new">new session</button>`; static in `page`: `dlg-new` (`dn-subject`, `dn-deployment`, `dn-view`, `dn-left`, `dn-id`, `dn-given`, `dn-msg`, `dn-ok`, `dn-cancel`), `end-confirm` (`end-return`, `end-yes`, `end-no`), `return-form` (`ret-session`, `ret-at`, `ret-yes`, `ret-no`), `amend-form` (`amend-to`, `amend-why`, `amend-yes`, `amend-no`). `web.END_CONFIRM`. A far return's `Question.said` (the warning the page shows beside *confirm* and *re-type*) now ends "Confirm it, or type it again -- ..."; a far departure's still ends "Confirm it, or amend it with a reason -- ...".

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, add `END_CONFIRM` to the `from wl_xcon.web import (...)` list, and append:

```python
def test_the_summary_ends_a_wlx_taskd_session_in_two_steps():
    """The b3a-2 plan, decision 12 (b3a-1 decision 6): *end session* while the session is
    open -- during a run too, which it stops first -- then *record return…*, the second
    step, while the return is awaited. A `wlx run` session's return is its terminal's."""
    open_ = (
        '<span class="pill neutral">open</span><button type="button" class="btn small '
        'danger" data-cmd="end" data-session="2027-01-14_01">end session</button>'
    )
    for phase in ("between_runs", "running"):
        assert fragments(_between(phase=phase), view())["end-actions"] == open_
    assert fragments(_between(phase="awaiting_return"), view())["end-actions"] == (
        '<span class="pill warn">ended · awaiting the return</span><button type="button" '
        'class="btn small danger" data-return="2027-01-14_01">record return…</button>'
    )
    assert fragments(_between(phase="closed"), view())["end-actions"] == (
        '<span class="pill ok">ended</span>'
    )
    assert "<button" not in fragments(frame(**STATES["awaiting return"]), view())["end-actions"]
    assert fragments(idle(), view())["end-actions"] == '<span class="pill neutral">none</span>'


def test_the_warning_is_answered_with_its_own_answers_naming_its_mark_and_session():
    """Spec §6.2: a far departure is confirmed or amended, a far return confirmed or
    typed again -- buttons for the frame's own answers, which the page's script sends
    only as the answer to this question (the b3a-2 plan, decision 10)."""
    departure = fragments(
        idle(question=Question("departure", "2027-01-14_01", 1.0, "far", ("confirm", "amend"))),
        view(),
    )["banners"]
    returning = fragments(
        _between(
            phase="awaiting_return",
            question=Question("return", "2027-01-14_01", 1.0, "far", ("confirm", "re-type")),
        ),
        view(),
    )["banners"]
    lan = fragments(
        idle(question=Question("departure", "2027-01-14_01", 1.0, "far", ("confirm", "amend"))),
        view(can_write=False),
    )["banners"]

    assert (
        '<button type="button" class="btn small" data-answer="confirm" data-mark="departure" '
        'data-session="2027-01-14_01">confirm</button>'
    ) in departure
    assert (
        '<button type="button" class="btn small" data-answer="amend" data-mark="departure" '
        'data-session="2027-01-14_01">amend…</button>'
    ) in departure
    assert (
        'data-answer="re-type" data-mark="return" data-session="2027-01-14_01">re-type</button>'
    ) in returning
    answers = re.findall(r"<button[^>]*data-answer[^>]*>", lan)
    assert answers and all(" disabled" in tag for tag in answers)


def test_a_stranded_animals_return_is_recorded_from_its_banner_naming_its_session():
    """XC-176: `Service._open`'s refusal says "Record it with End session, naming its
    session", and this is where. A record that cannot be read is repaired by hand first,
    so it has no button."""
    banners = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0), Stranded("2027-01-13_02", "", None))),
        view(),
    )["banners"]

    assert (
        '<button type="button" class="btn small danger" data-return="2027-01-13_01">'
        "end session…</button>"
    ) in banners
    assert 'data-return="2027-01-13_02"' not in banners
    assert "Idle" not in banners, "nothing opens while an animal is stranded"


def test_the_idle_page_offers_a_new_session_and_says_which_animals_and_tasks_there_are():
    """Spec §6.1: "the page shows *no session open* beside the form that opens one"; the
    mockup's Session panel has *new session* too. Greyed while an animal is stranded."""
    parts = fragments(idle(), view())
    stranded = fragments(idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0),)), view())
    button = '<button type="button" class="btn small primary" data-cmd="new">new session</button>'

    assert button in parts["banners"] and "no session open" in parts["banners"]
    assert button in parts["setup"]
    assert "<dt>animals</dt><dd>A, B</dd>" in parts["setup"]
    assert "<dt>tasks offered</dt><dd>fixation_detection.py</dd>" in parts["setup"]
    assert parts["dn-subject"] == '<option value="A">A</option><option value="B">B</option>'
    assert re.search(r'data-cmd="new" disabled title="[^"]+">new session</button>', stranded["setup"])
    assert fragments(frame(), view())["dn-subject"] == '<option value="">no animal offered</option>'


def test_every_string_the_session_panes_show_is_escaped():
    parts = fragments(
        _between(
            session_id=EVIL,
            offered_tasks=(EVIL,),
            preflight=Preflight(EVIL, (PreflightItem(EVIL, "unknown", EVIL),)),
            question=Question(EVIL, EVIL, 1.0, EVIL, (EVIL,)),
        ),
        view(),
    )
    idle_parts = fragments(
        idle(animals=(EVIL,), offered_tasks=(EVIL,), stranded=(Stranded(EVIL, EVIL, 1.0),)),
        view(),
    )

    text = "".join(parts.values()) + "".join(idle_parts.values())
    assert "<script" not in text
    assert EVIL not in text


#: What a person types or chooses on the page's forms. Each is static, outside every
#: fragment, so no frame -- one a second while idle and between runs -- replaces it.
_TYPED = (
    "run-trials", "amend-to", "amend-why", "end-return", "ret-at",
    "dn-deployment", "dn-view", "dn-left", "dn-id", "dn-given",
)


def test_nothing_a_person_types_into_is_inside_a_fragment():
    """Review Focus 1 (the b3a-2 plan, decision 11)."""
    for parts in (fragments(_between(preflight=PREFLIGHT), view()), fragments(idle(), view())):
        document = page(parts, stale_after_s=30.0, nonce="n0nce", can_write=True)
        for name in _TYPED:
            assert document.count(f'id="{name}"') == 1, name
            assert not any(f'id="{name}"' in pane for pane in parts.values()), name


def test_the_new_session_dialog_asks_what_an_open_needs_and_offers_no_now_for_the_departure():
    """Spec §6.2's fields, in the mockup's `dlg-new` (the b3a-2 plan, decision 6): no rig
    and no "saved to" (`wlx taskd`'s are fixed), the id typed, and the departure empty --
    the terminal's parser has no `now` for it."""
    document = page(fragments(idle(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert re.search(r'<div class="scrim" id="dlg-new"[^>]*hidden>', document)
    for field, label in (
        ("dn-subject", "subject"), ("dn-deployment", "deployment"), ("dn-view", "setup"),
        ("dn-left", "←cage at"), ("dn-id", "id"), ("dn-given", "given today, mL"),
    ):
        assert f'<label class="sub" for="{field}">{label}</label>' in document, field
    assert '<option value="rig_fixed">head-fixed</option><option value="rig_chaired">chaired</option>' in document
    assert '<option value="direct">direct view</option><option value="stereoscope">stereoscope</option>' in document
    left = re.search(r'<input[^>]*id="dn-left"[^>]*>', document).group(0)
    assert " value=" not in left and "now" not in left
    assert '<button class="btn primary" id="dn-ok" type="button">open session</button>' in document
    assert "<title>xcon console</title>" in document and "expcontroller" not in document


def test_end_session_asks_first_and_takes_the_return_now_or_later():
    document = page(fragments(_between(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert "<h2>Summary</h2>" in document
    assert re.search(r'<div class="inline crit" id="end-confirm"[^>]*hidden>', document)
    assert html.escape(END_CONFIRM) in document
    assert END_CONFIRM.startswith("end the session?")
    assert "the head's release is recorded then" in END_CONFIRM
    assert "leave it blank" in END_CONFIRM
    assert re.search(r'<div class="inline info" id="return-form"[^>]*hidden>', document)
    assert re.search(r'<div class="inline info" id="amend-form"[^>]*hidden>', document)


def test_away_from_the_box_every_session_form_is_greyed():
    lan = page(fragments(_between(preflight=PREFLIGHT), view(can_write=False)), stale_after_s=30.0, nonce="n0nce")

    for control in (
        "task-sel", "run-trials", "dn-subject", "dn-deployment", "dn-view", "dn-left",
        "dn-id", "dn-given", "dn-ok", "end-return", "end-yes", "ret-at", "ret-yes",
        "amend-to", "amend-why", "amend-yes",
    ):
        assert re.search(r'id="' + control + r'"[^>]* disabled', lan), control
```

In `tests/test_taskd.py`, `test_each_phase_of_a_service_session_refuses_a_command_in_its_own_words`, change

```python
    assert "End session button waits on b3a-2" in awaiting
```

to

```python
    assert "(the page's End session)" in awaiting
```

In `tests/test_service.py`, `test_end_without_a_return_waits_for_it_and_refuses_a_run`, change the expected text to

```python
        "recorded by an EndSession sent over the link (the page's End session)"
```

In `tests/test_welfare.py`, append:

```python
# --- P4d-2b b3a-2: a far mark's words offer what the terminal and the page take ------


def test_a_far_returns_sentence_offers_a_confirmation_or_the_time_typed_again():
    """A return has no amendment (P4d-2a spec §3; P4d-2b spec §6.2): the terminal and the
    page take a confirmation or the time typed again, so the sentence offers those and
    never an amendment the rig would refuse (the b3a-2 plan, decision 16). Words only:
    the same thirty minutes, a string and never an exception, and nothing marked."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW, wall_now=WALL_NOW)

    sentence = welfare.return_needs_confirmation(
        at=WALL_NOW + 100.0, wall_now=WALL_NOW + 7_300.0
    )

    assert sentence == (
        "the return given for subject 'A' is 7200 s before the clock this session is "
        "reading, which is further back than the 1800 s a session takes on trust (PI, "
        "2026-09-20). Confirm it, or type it again -- an hour typed in the wrong half of "
        "the day sits inside every limit there is and nothing else will catch it"
    )
    assert "amend" not in sentence
    assert welfare.returned_wall_at is None, "asking marks nothing"
    assert welfare.return_needs_confirmation(
        at=WALL_NOW + 5_500.0, wall_now=WALL_NOW + 7_300.0
    ) is None, "1,800 s is still the band's edge"


def test_a_far_departures_sentence_is_unchanged_confirm_or_amend_with_a_reason():
    """The departure's words are the PI's two options (2026-09-20), byte for byte as they
    were before the return's changed (the b3a-2 plan, decision 16)."""
    welfare = _welfare()

    sentence = welfare.departure_needs_confirmation(at=WALL_NOW - 7_200.0, wall_now=WALL_NOW)

    assert sentence == (
        "the departure given for subject 'A' is 7200 s before the clock this session is "
        "reading, which is further back than the 1800 s a session takes on trust (PI, "
        "2026-09-20). Confirm it, or amend it with a reason -- an hour typed in the wrong "
        "half of the day sits inside every limit there is and nothing else will catch it"
    )
```

and in `test_a_return_far_from_now_needs_a_persons_confirmation_too` -- **the one existing test that pins the return's old words** (the other three that read "Confirm it, or amend it", `test_a_departure_far_from_now_needs_a_persons_confirmation` in `test_welfare.py`, `test_a_far_departure_with_no_answer_is_owed_and_nothing_is_marked` in `test_marks.py` and `wlx run`'s far-departure refusal in `test_cli.py`, are all about a departure and stay as they are) -- change

```python
    assert "Confirm it, or amend it" in sentence
```

to

```python
    assert "Confirm it, or type it again" in sentence
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_web.py tests/test_welfare.py tests/test_taskd.py tests/test_service.py -q -p no:cacheprovider -k "summary or warning_is_answered or stranded_animals_return or new_session or session_panes or types_into or end_session_asks or session_form or own_words or end_without_a_return or far_returns_sentence or far_departures_sentence or return_far_from_now"`
Expected: FAIL -- `ImportError: cannot import name 'END_CONFIRM'`, then `KeyError: 'end-actions'` and the rest; in `test_welfare.py`, the far return's sentence still says "or amend it with a reason". `test_a_far_departures_sentence_is_unchanged_confirm_or_amend_with_a_reason` passes already: it pins the words that must not move.

- [ ] **Step 3: The session panes**

In `wl_xcon/web.py`, add `"end-actions"` after `"setup"` and `"dn-subject"` after `"end"` in `FRAGMENT_IDS`, so it ends:

```python
    "pf-sum",
    "preflight",
    "setup",
    "end-actions",
    "end",
    "dn-subject",
)
```

After `RUN_TRIALS`, add:

```python
#: What *end session* asks before it is sent (the mockup's `end-confirm`, P4d-2b spec
#: §6.2): what ending does here, the head's release now and the return now or later (the
#: b3a-1 plan, decision 6) -- not the mockup's "the in-session clock stops, and the code
#: it used is packaged", which predates it and slice b6.
END_CONFIRM = (
    "end the session? no further run starts in it; a run in progress stops at its next "
    "trial boundary, and the head's release is recorded then. give the time the animal "
    "went back into its home cage now, or leave it blank and record it once the animal "
    "is home"
)
```

Replace `_question_banner`, `_idle_banners` and `_idle` whole, and change `_banners`' line `out.append(_question_banner(frame.question))` to `out.append(_question_banner(frame.question, view))`:

```python
def _question_banner(question: Question, view: View) -> str:
    """The answer a console owes on a far mark (P4d-2b spec §6.2), with a button for each
    of the frame's own answers, naming its mark and session: the page's script re-sends
    the time as typed with the one pressed, and only for a question this page raised
    (the b3a-2 plan, decision 10). Greyed away from the box."""
    buttons = "".join(
        f'<button type="button" class="btn small" data-answer="{_e(answer)}" '
        f'data-mark="{_e(question.mark)}" data-session="{_e(question.session_id)}"'
        f'{_off(view)}>{_e(answer)}{"…" if answer == "amend" else ""}</button>'
        for answer in question.answers
    )
    return _banner(
        "warn",
        "Confirm",
        f"{_e(question.said)} · answer "
        f"{' or '.join(_e(answer) for answer in question.answers)} "
        f"(session {_e(question.session_id)}) {buttons}",
    )


def _new_session_button(view: View, why: str | None = None) -> str:
    """*new session* (the mockup's `a-new`): opens the page's *New session* dialog."""
    off = _off(view) or ("" if why is None else f' disabled title="{_e(why)}"')
    return f'<button type="button" class="btn small primary" data-cmd="new"{off}>new session</button>'


def _idle_banners(frame: Idle, view: View) -> str:
    """A refused frame, then every stranded animal -- each with *end session…*, which
    takes its return naming its session (XC-176) -- then a question owed, then, with no
    animal stranded, *no session open* beside *new session* (spec §6.1). A stranded
    departure is given as this host's local date, minute and zone, as the terminal gives
    it (`cli._moment`): an animal out since days ago must not read as since this morning
    (the b3a-1 final review, Minor 1). A record that cannot be read has no button: it is
    repaired by hand first."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    for found in frame.stranded:
        if found.left_at is None:
            text = (
                f"session {_e(found.session_id)}: its welfare record cannot be read, so its "
                f"animal's return cannot be checked; no session opens until the file is "
                f"repaired and the return recorded"
            )
        else:
            text = (
                f"{_e(found.subject)} left its cage at {_e(_moment(found.left_at))} in "
                f"session {_e(found.session_id)}, and its return is not recorded; no "
                f"session opens until it is "
                f'<button type="button" class="btn small danger" '
                f'data-return="{_e(found.session_id)}"{_off(view)}>end session…</button>'
            )
        out.append(_banner("crit", "Stranded", text))
    if frame.question is not None:
        out.append(_question_banner(frame.question, view))
    if not frame.stranded:
        out.append(_banner("info", "Idle", f"no session open {_new_session_button(view)}"))
    return "".join(out)


def _idle_setup(frame: Idle, view: View) -> str:
    """The Session panel with no session open (the mockup's Setup tab): *new session*,
    greyed while an animal is stranded, and what `wlx taskd` offers a session."""
    why = (
        "an animal's return is not recorded: end its session from its Stranded banner first"
        if frame.stranded
        else None
    )
    rows = (
        ("animals", ", ".join(frame.animals) or "none: no folder under --subjects holds a bounds.py"),
        ("tasks offered", ", ".join(frame.offered_tasks) or "none: no task file under --tasks"),
    )
    return (
        f'<div class="selrow">{_new_session_button(view, why)}</div><dl class="dl">'
        + "".join(f"<dt>{name}</dt><dd>{_e(value)}</dd>" for name, value in rows)
        + "</dl>"
    )


def _end_actions(frame: Telemetry | Idle | None, view: View) -> str:
    """The Summary's pill and *end session* (the mockup's `end-pill`, `a-end`) while a
    `wlx taskd` session is open -- during a run too, which it stops first -- and, once it
    has ended, *record return…*, the second step (the b3a-2 plan, decision 12). A `wlx
    run` session's return is taken at its terminal, so its pill stands alone."""
    if frame is None or isinstance(frame, Idle):
        return '<span class="pill neutral">none</span>'
    session = _e(frame.session_id)
    if not frame.service:
        return f'<span class="pill neutral">{"open" if frame.stop_kind is None else "ended"}</span>'
    if frame.phase in ("between_runs", "running"):
        return (
            '<span class="pill neutral">open</span><button type="button" class="btn small '
            f'danger" data-cmd="end" data-session="{session}"{_off(view)}>end session</button>'
        )
    if frame.phase == "awaiting_return":
        return (
            '<span class="pill warn">ended · awaiting the return</span><button type="button" '
            f'class="btn small danger" data-return="{session}"{_off(view)}>record return…</button>'
        )
    return '<span class="pill ok">ended</span>'


def _idle(frame: Idle, view: View) -> dict[str, str]:
    """The page while `wlx taskd` has no session open (P4d-2b spec §6.1: "the page shows
    *no session open* beside the form that opens one"): every pane as before any frame,
    except the pill, the header, the banners, the controls, *wl-works sees* (`/health`
    as it would be sent for this frame, stranded animals included), the refusals, the
    tasks offered, the Session panel and the dialog's animals."""
    panes = fragments(None, view)
    panes["state"] = '<span class="pill neutral" data-state="idle">no session open</span>'
    panes["head-id"] = '<span class="nm">no session open</span>'
    panes["banners"] = _idle_banners(frame, view)
    panes["controls"] = '<span class="nm">controls · no session open</span>'
    panes["rt-health"] = _health_pane(frame, view)
    panes["rt-changes"] = _idle_refusals(frame)
    panes["task-sel"] = _options(frame.offered_tasks, "no task offered")
    panes["setup"] = _idle_setup(frame, view)
    panes["dn-subject"] = _options(frame.animals, "no animal offered")
    return panes
```

In `fragments`, add after `"setup": _setup(frame),`:

```python
        "end-actions": _end_actions(frame, view),
```

and after `"end": _end(frame),`:

```python
        "dn-subject": _options((), "no animal offered"),
```

- [ ] **Step 4: The forms in `page`**

In `page`, after `  <div class="banners" id="banners">{p['banners']}</div>`, add:

```python
  <div class="inline info" id="amend-form" role="dialog" aria-label="amend the departure" hidden><span>amend the departure · the corrected time</span><input id="amend-to" autocomplete="off" placeholder="HH:MM, or 2027-01-13T22:40" aria-label="the corrected departure"{off}><span>why</span><input id="amend-why" maxlength="500" autocomplete="off" aria-label="why it is amended"{off}><span class="nm">your name is recorded with it</span><button class="btn small primary" id="amend-yes" type="button"{off}>send amendment</button><button class="btn small" id="amend-no" type="button">cancel</button></div>
```

Replace the End of session tab's line

```python
        <div class="tabpanel" id="tp-end"><section class="panel glass"><div class="top"><h2>End of session</h2><span class="sub">read-only</span></div><div id="end">{p['end']}</div></section></div>
```

with

```python
        <div class="tabpanel" id="tp-end"><section class="panel glass"><div class="top"><h2>Summary</h2><div class="selrow" id="end-actions">{p['end-actions']}</div></div>
          <div class="inline crit" id="end-confirm" role="alertdialog" aria-label="confirm end session" hidden><span>{_e(END_CONFIRM)}</span><span>→cage at</span><input id="end-return" autocomplete="off" placeholder="now, HH:MM, or blank for later" aria-label="the return to the home cage"{off}><button class="btn small danger" id="end-yes" type="button"{off}>end session</button><button class="btn small" id="end-no" type="button">cancel</button></div>
          <div class="inline info" id="return-form" role="dialog" aria-label="the return to the home cage" hidden><span>the return to the home cage · session <b class="mono" id="ret-session"></b> · →cage at</span><input id="ret-at" autocomplete="off" placeholder="now, HH:MM, or 2027-01-13T22:40" aria-label="the return to the home cage"{off}><button class="btn small primary" id="ret-yes" type="button"{off}>record return</button><button class="btn small" id="ret-no" type="button">cancel</button></div>
          <div id="end">{p['end']}</div></section></div>
```

Before `<div class="scrim" id="gone" role="dialog" aria-modal="true" aria-labelledby="gone-h" hidden>`, add:

```python
<div class="scrim" id="dlg-new" hidden>
  <div class="dialog glass" role="dialog" aria-modal="true" aria-labelledby="dn-h">
    <h2 id="dn-h">New session</h2>
    <div class="grid">
      <label class="sub" for="dn-subject">subject</label><select id="dn-subject"{off}>{p['dn-subject']}</select>
      <label class="sub" for="dn-deployment">deployment</label><select id="dn-deployment"{off}><option value="rig_fixed">head-fixed</option><option value="rig_chaired">chaired</option></select>
      <label class="sub" for="dn-view">setup</label><select id="dn-view"{off}><option value="direct">direct view</option><option value="stereoscope">stereoscope</option></select>
      <label class="sub" for="dn-left">←cage at</label><input class="field mono" id="dn-left" autocomplete="off" placeholder="HH:MM, or 2027-01-13T22:40"{off}>
      <label class="sub" for="dn-id">id</label><input class="field mono" id="dn-id" autocomplete="off" placeholder="as wlx run --session-id takes it"{off}>
      <label class="sub" for="dn-given">given today, mL</label><input class="field mono" id="dn-given" inputmode="decimal" autocomplete="off" placeholder="blank when not known"{off}>
    </div>
    <div id="dn-msg" class="sub" role="status"></div>
    <div class="end"><button class="btn" id="dn-cancel" type="button">cancel</button><button class="btn primary" id="dn-ok" type="button"{off}>open session</button></div>
  </div>
</div>
```

In `_CSS`, after the rules Task 4 added, add:

```css
.dialog .grid { display: grid; grid-template-columns: auto 1fr; gap: 8px 12px; align-items: center; }
.dialog .end { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.dialog .field, .dialog select { width: 100%; border-radius: 3px; font: inherit; }
#amend-to, #end-return, #ret-at { width: 13em; }
#amend-why { width: min(28em, 50vw); }
```

Extend `page`'s docstring's last paragraph with: "**The session forms (P4d-2b b3a-2)**: the *New session* dialog, the end confirmation, the return and the amendment are static too, and so is the run's trial count; only the task and subject selects' options are fragments (the b3a-2 plan, decision 11)."

- [ ] **Step 5: The rig's sentence about the page's End session is true now**

In `wl_xcon/taskd.py`, `Session._command`, in the post-loop refusal, change

```python
                "cage, which is recorded by an EndSession sent over the link (the page's "
                "End session button waits on b3a-2); a command sent now is not applied"
```

to

```python
                "cage, which is recorded by an EndSession sent over the link (the page's "
                "End session); a command sent now is not applied"
```

- [ ] **Step 6: A far return's warning offers what the rig takes (welfare-critical, words only)**

The page now shows a far return's warning beside *confirm* and *re-type*, and the sentence `welfare` gives it ends "Confirm it, or amend it with a reason": `_far_from_now` is the one copy of the far-mark rule, and `return_needs_confirmation` calls it for the return, which has no amendment (P4d-2a spec §3; spec §6.2). In `wl_xcon/welfare.py`, `Welfare._far_from_now`, replace

```python
        return (
            f"the {what} given for subject {self.bounds.subject!r} is "
            f"{seconds_ago:.0f} s before the clock this session is reading, which is "
            f"further back than the {CONFIRM_MARK_WITHIN:.0f} s a session takes "
            f"on trust (PI, 2026-09-20). Confirm it, or amend it with a reason -- an "
            f"hour typed in the wrong half of the day sits inside every limit there "
            f"is and nothing else will catch it"
        )
```

with

```python
        # **What a person may answer, in the words the terminal and the page take**
        # (the b3a-2 plan, decision 16): a departure is confirmed or amended with a
        # reason; a return has no amendment (P4d-2a spec §3; P4d-2b spec §6.2), so a
        # corrected time is typed again. Words only: the rule above is the same for both.
        other = "amend it with a reason" if what == "departure" else "type it again"
        return (
            f"the {what} given for subject {self.bounds.subject!r} is "
            f"{seconds_ago:.0f} s before the clock this session is reading, which is "
            f"further back than the {CONFIRM_MARK_WITHIN:.0f} s a session takes "
            f"on trust (PI, 2026-09-20). Confirm it, or {other} -- an "
            f"hour typed in the wrong half of the day sits inside every limit there "
            f"is and nothing else will catch it"
        )
```

Nothing else in `welfare.py` changes: not the docstring, not the threshold, not `departure_needs_confirmation` or `return_needs_confirmation` (Task 8 Step 4 checks every other function and method by AST). With `other` for a departure, the departure's sentence is the same string it was, which `test_a_far_departures_sentence_is_unchanged_confirm_or_amend_with_a_reason` holds to the byte.

- [ ] **Step 7: Run the tests**

Run: `python3 -m pytest tests/test_web.py tests/test_serve.py tests/test_health.py tests/test_welfare.py tests/test_marks.py tests/test_stranded.py tests/test_cli.py tests/test_taskd.py tests/test_service.py -q -p no:cacheprovider`
Expected: all pass -- `test_the_page_holds_every_pane_in_the_element_its_stream_swaps` checks `end-actions` and `dn-subject` too, b3a-1's idle tests keep their stranded-first order, and every departure test that reads "Confirm it, or amend it" still does.

- [ ] **Step 8: The whole suite, then commit**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

```bash
git add wl_xcon/web.py wl_xcon/taskd.py wl_xcon/welfare.py tests/test_web.py tests/test_welfare.py tests/test_taskd.py tests/test_service.py
git commit -m "Show the page's session forms, and word a far return's warning as the rig takes it"
```

---

### Task 6: The page's script sends the forms

**Files:**
- Modify: `wl_xcon/web.py` (`_SCRIPT` and the `#:` comment above it)
- Modify: `docs/design/architecture.md` (the `console` row: the page sends the four)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 3's bodies; Task 4's `task-sel`, `run-trials`, `pf-pill` (`data-cmd="check"`), `data-ack`, start's `data-task`; Task 5's `data-cmd="new"`, `data-cmd="end"` with `data-session`, `data-return`, `data-answer` / `data-mark` / `data-session`, and the static forms' ids.
- Produces: one `post` per form -- `{kind: "check", task, values: {}}`, `{kind: "start", task, values: {}, trials, acknowledged}`, `{kind: "open", session_id, animal, deployment, view, departure, delivered_today, answer, amend_to, amend_reason}`, `{kind: "end", session_id, returned, confirm}` -- each through `post`, the one `fetch`, which adds `by`. Task 7 posts these same bodies.

**Read the script's pinned text first** (`tests/test_web.py`: `test_the_script_does_only_what_spec_4_3_and_5_2_ask`, `test_the_stale_timer_runs_from_the_frames_age_not_from_arrival`, `test_a_double_click_or_one_within_the_hold_cannot_toggle_pause_or_resume`, `test_the_script_pins_the_box_only_write_guard`, `test_a_double_click_on_give_reward_gives_only_one_reward`): every edit below leaves each pinned line as it is. In particular **`function command(cmd) {` keeps its one parameter**, **`check` is already the stale timer's name** (the new function is `takePreflight`), there is still **one `fetch(`**, **one `Date.now()`**, and the only `innerHTML` writes are `html` and `heldParams`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web.py`:

```python
def _function(name: str) -> str:
    """The body of the page script's function `name`, from its opening line to its own
    closing brace at two spaces' indent."""
    return re.search(rf"function {name}\((.*?)\) \{{(.*?)\n  \}}", _SCRIPT, re.S).group(2)


def _listener(element: str) -> str:
    """The body of the page script's click listener on `element`."""
    return re.search(
        rf'el\("{element}"\)\.addEventListener\("click", function \(\) \{{(.*?)\n  \}}\);',
        _SCRIPT,
        re.S,
    ).group(1)


def test_a_frame_keeps_the_option_chosen_in_a_select():
    """Review Focus 1: a frame re-renders the task and subject selects' options; the
    option a person chose stays chosen while it is still offered."""
    swap = _function("swap")

    assert 'var chosen = node && node.tagName === "SELECT" ? node.value : null;' in swap
    assert swap.index("var chosen") < swap.index("node.innerHTML = html;") < swap.index(
        "choose(node, chosen);"
    )
    assert 'if (id === "preflight") { restoreAcks(); }' in swap
    assert "if (option.value === value) { select.value = value; }" in _function("choose")


def test_no_acknowledgement_outlives_the_run_or_the_task_it_was_ticked_for():
    """Review Focus 4 (the b3a-2 plan, decision 9): the ticks are the person's, kept
    across a re-render, sent with the start, and cleared by a start or a new pre-flight."""
    take, start = _function("takePreflight"), _function("startRun")

    assert "acked = {};" in take and "acked = {};" in start
    assert start.index("acked = {};") < start.index("post(")
    assert 'if (box.checked) { acknowledged.push(box.getAttribute("data-ack")); }' in start
    assert (
        'else if (e.target.matches("input[data-ack]")) '
        '{ acked[e.target.getAttribute("data-ack")] = e.target.checked; }'
    ) in _SCRIPT
    assert "box.checked = acked[box.getAttribute(\"data-ack\")] === true;" in _function("restoreAcks")


def test_start_sends_the_task_whose_preflight_is_shown_and_only_while_it_is_chosen():
    """The b3a-2 plan, decision 8; the page's values are none, the task's own (decision 1)."""
    start = _function("startRun")

    assert "var button = el(\"controls\").querySelector('[data-cmd=\"start\"]');" in start
    assert 'var task = button ? button.getAttribute("data-task") : "";' in start
    assert "if (!task || task !== chosenTask()) {" in start
    assert "if (!Number.isInteger(trials) || trials < 1) {" in start
    assert (
        'post({ kind: "start", task: task, values: {}, trials: trials, acknowledged: acknowledged });'
    ) in start
    assert 'post({ kind: "check", task: task, values: {} });' in _function("takePreflight")
    assert 'else if (e.target.id === "task-sel") { takePreflight(false); }' in _SCRIPT


def test_a_new_session_is_sent_with_every_field_the_dialog_asks_as_typed():
    body = _function("openSession")

    for field in (
        'session_id: el("dn-id").value.trim(),',
        'animal: el("dn-subject").value,',
        'deployment: el("dn-deployment").value,',
        'view: el("dn-view").value,',
        'departure: el("dn-left").value.trim(),',
        "delivered_today: today,",
        "answer: null,",
        "amend_to: null,",
        'amend_reason: ""',
    ):
        assert field in body, field
    assert 'var today = given === "" ? null : Number(given);' in body
    assert "lastOpen = Object.assign({}, request);" in body
    assert body.index("lastOpen = Object.assign({}, request);") < body.index("post(")


def test_an_answer_re_sends_the_time_as_typed_and_only_for_a_warning_this_page_raised():
    """The b3a-2 plan, decision 10: *confirm* re-sends the open or the return this page
    sent, with its answer; *amend…* the open with the corrected time and the reason; a
    warning whose session this page did not send is not answered."""
    body = _function("answerWarning")

    assert 'if (given === "re-type") { openReturn(session); return; }' in body
    assert 'var sent = which === "departure" ? lastOpen : lastEnd;' in body
    assert "if (!sent || sent.session_id !== session) {" in body
    assert body.index("if (!sent || sent.session_id !== session) {") < body.index("post(")
    assert 'Object.assign({}, sent, { answer: "confirm" })' in body
    assert "Object.assign({}, sent, { confirm: true })" in body
    assert (
        'post(Object.assign({}, lastOpen, { answer: "amend", amend_to: '
        'el("amend-to").value.trim(), amend_reason: el("amend-why").value.trim() }));'
    ) in _listener("amend-yes")


def test_end_session_sends_the_return_as_typed_or_later_and_a_return_needs_a_time():
    """The b3a-2 plan, decision 12: step one's return may be left blank for later; the
    return form's may not."""
    end, ret = _listener("end-yes"), _listener("ret-yes")

    assert 'returned: returned === "" ? null : returned, confirm: false' in end
    assert 'if (returned !== "") { lastEnd = Object.assign({}, request); }' in end
    assert (
        'if (!returned) { tell("not sent: give the time the animal went back into its home '
        'cage, or now", "crit"); return; }'
    ) in ret
    assert "lastEnd = Object.assign({}, request);" in ret


def test_the_session_forms_are_opened_from_the_buttons_the_panes_render():
    command = re.search(r"function command\(cmd\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)

    for line in (
        'else if (cmd === "new") { openNew(); }',
        'else if (cmd === "check") { takePreflight(true); }',
        'else if (cmd === "start") { startRun(); }',
        'else if (cmd === "end") { askEnd(); }',
    ):
        assert line in command, line
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)
    assert 'var answering = e.target.closest("[data-answer]");' in handler
    assert 'openReturn(returning.getAttribute("data-return"))' in handler
    assert handler.index("[data-answer]") < handler.index("[data-cmd]")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_web.py -q -p no:cacheprovider -k "keeps_the_option or outlives or whose_preflight_is_shown or dialog_asks_as_typed or re_sends or return_needs_a_time or opened_from_the_buttons"`
Expected: FAIL -- `AttributeError: 'NoneType' object has no attribute 'group'` (no such function yet) and the missing lines.

- [ ] **Step 3: The script's state**

In `_SCRIPT`, after

```js
  var REWARD_HOLD_MS = 1000;
  var lastRewardAt = -Infinity;
```

add:

```js
  // P4d-2b b3a-2 (spec §6.2). The last open and the last return this page sent, kept so
  // an answer to the warning they raise re-sends the same typed time with it -- the rig
  // takes an answer only for the time it asked about (`service._unasked`); the unknown
  // pre-flight items ticked, by name, for the run about to start, cleared whenever a
  // pre-flight is asked for or a run started, so no tick outlives the run it was for;
  // and the session the return form is for.
  var lastOpen = null;
  var lastEnd = null;
  var acked = {};
  var returnFor = null;
```

- [ ] **Step 4: A swap keeps a chosen option and the ticks**

Replace

```js
  function swap(id, html) {
    if (id === "params" && busy()) { heldParams = html; return; }
    var node = el(id);
    if (node) { node.innerHTML = html; }
    if (id === "controls") { holdReward(); }
  }
```

with

```js
  function swap(id, html) {
    if (id === "params" && busy()) { heldParams = html; return; }
    var node = el(id);
    var chosen = node && node.tagName === "SELECT" ? node.value : null;
    if (node) { node.innerHTML = html; }
    if (chosen !== null) { choose(node, chosen); }
    if (id === "controls") { holdReward(); }
    if (id === "preflight") { restoreAcks(); }
  }
```

and after the whole `function release() { ... }` add:

```js
  function choose(select, value) {
    // A frame re-renders a select's options; the option a person chose stays chosen
    // while it is still offered (the b3a-2 plan, decision 11).
    Array.prototype.forEach.call(select.options, function (option) {
      if (option.value === value) { select.value = value; }
    });
  }
  function restoreAcks() {
    Array.prototype.forEach.call(document.querySelectorAll("input[data-ack]"), function (box) {
      box.checked = acked[box.getAttribute("data-ack")] === true;
    });
  }
```

- [ ] **Step 5: The forms' functions, and `command` routing to them**

Replace

```js
  function command(cmd) {
    if (cmd === "stop") { el("stop-confirm").hidden = false; }
    else if (cmd === "mark") { mark(); }
    else if (cmd === "reward") { reward(); }
    else { post({ kind: cmd }); }
  }
```

with

```js
  // P4d-2b b3a-2 (spec §6.2): a run, a session and the two marks, from the page. Every
  // field is a static element no frame replaces; each form sends one command through
  // `post`, the one `fetch`, which adds who sent it.
  function chosenTask() { return el("task-sel").value; }
  function takePreflight(showPanel) {
    var task = chosenTask();
    acked = {};
    if (!task) { tell("not sent: no task is offered to check", "crit"); return; }
    post({ kind: "check", task: task, values: {} });
    if (showPanel) { el("t-setup").checked = true; }
  }
  function startRun() {
    var button = el("controls").querySelector('[data-cmd="start"]');
    var task = button ? button.getAttribute("data-task") : "";
    var trials = Number(el("run-trials").value.trim());
    if (!task || task !== chosenTask()) {
      tell("not sent: the pre-flight shown is not for the task chosen; take its pre-flight first (the pre-flight pill)", "crit");
      return;
    }
    if (!Number.isInteger(trials) || trials < 1) {
      tell("not sent: a run's trials are a whole number from 1", "crit");
      return;
    }
    var acknowledged = [];
    Array.prototype.forEach.call(document.querySelectorAll("input[data-ack]"), function (box) {
      if (box.checked) { acknowledged.push(box.getAttribute("data-ack")); }
    });
    acked = {};
    restoreAcks();
    post({ kind: "start", task: task, values: {}, trials: trials, acknowledged: acknowledged });
  }
  function openNew() {
    el("dn-msg").textContent = "";
    el("dlg-new").hidden = false;
    el("dn-subject").focus();
  }
  function openSession() {
    var given = el("dn-given").value.trim();
    var today = given === "" ? null : Number(given);
    if (today !== null && !isFinite(today)) {
      el("dn-msg").textContent = "not sent: the fluid given today is mL, or blank when it is not known";
      return;
    }
    var request = {
      kind: "open",
      session_id: el("dn-id").value.trim(),
      animal: el("dn-subject").value,
      deployment: el("dn-deployment").value,
      view: el("dn-view").value,
      departure: el("dn-left").value.trim(),
      delivered_today: today,
      answer: null,
      amend_to: null,
      amend_reason: ""
    };
    lastOpen = Object.assign({}, request);
    post(request, function (answer) {
      el("dn-msg").textContent = answer.said;
      if (answer.status === "sent") { el("dlg-new").hidden = true; }
    });
  }
  function askEnd() {
    el("end-return").value = "";
    el("end-confirm").hidden = false;
    el("end-return").focus();
  }
  function openReturn(session) {
    returnFor = session;
    el("ret-session").textContent = session;
    el("ret-at").value = "";
    el("return-form").hidden = false;
    el("t-end").checked = true;
    el("ret-at").focus();
  }
  function answerWarning(button) {
    var given = button.getAttribute("data-answer");
    var which = button.getAttribute("data-mark");
    var session = button.getAttribute("data-session");
    if (given === "re-type") { openReturn(session); return; }
    var sent = which === "departure" ? lastOpen : lastEnd;
    if (!sent || sent.session_id !== session) {
      tell("not sent: this page did not send the " + which + " this warning is about, so it cannot answer it; send the time again, then answer the warning it raises", "crit");
      return;
    }
    if (given === "amend") {
      el("amend-to").value = "";
      el("amend-why").value = "";
      el("amend-form").hidden = false;
      el("amend-to").focus();
    } else if (given === "confirm") {
      post(which === "departure" ? Object.assign({}, sent, { answer: "confirm" }) : Object.assign({}, sent, { confirm: true }));
    }
  }
  function command(cmd) {
    if (cmd === "stop") { el("stop-confirm").hidden = false; }
    else if (cmd === "mark") { mark(); }
    else if (cmd === "reward") { reward(); }
    else if (cmd === "new") { openNew(); }
    else if (cmd === "check") { takePreflight(true); }
    else if (cmd === "start") { startRun(); }
    else if (cmd === "end") { askEnd(); }
    else { post({ kind: cmd }); }
  }
```

- [ ] **Step 6: The clicks, the changes and the forms' buttons**

In the click listener, replace its first lines

```js
  document.addEventListener("click", function (e) {
    if (!e.target.closest) { return; }
    var button = e.target.closest("[data-cmd]");
```

with

```js
  document.addEventListener("click", function (e) {
    if (!e.target.closest) { return; }
    var answering = e.target.closest("[data-answer]");
    if (answering && !answering.disabled) { answerWarning(answering); return; }
    var returning = e.target.closest("[data-return]");
    if (returning && !returning.disabled) { openReturn(returning.getAttribute("data-return")); return; }
    var button = e.target.closest("[data-cmd]");
```

Replace

```js
  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches("input[data-param]")) { schedule(e.target); }
  });
```

with

```js
  document.addEventListener("change", function (e) {
    if (!e.target.matches) { return; }
    if (e.target.matches("input[data-param]")) { schedule(e.target); }
    else if (e.target.matches("input[data-ack]")) { acked[e.target.getAttribute("data-ack")] = e.target.checked; }
    else if (e.target.id === "task-sel") { takePreflight(false); }
  });
```

Before the line `  setInterval(check, 1000);`, add:

```js
  el("dn-ok").addEventListener("click", openSession);
  el("dn-cancel").addEventListener("click", function () { el("dlg-new").hidden = true; });
  el("dlg-new").addEventListener("keydown", function (e) {
    if (e.key === "Escape") { el("dlg-new").hidden = true; }
  });
  el("end-yes").addEventListener("click", function () {
    var button = el("end-actions").querySelector('[data-cmd="end"]');
    var returned = el("end-return").value.trim();
    el("end-confirm").hidden = true;
    if (!button) { tell("not sent: no session is open to end", "crit"); return; }
    var request = { kind: "end", session_id: button.getAttribute("data-session"), returned: returned === "" ? null : returned, confirm: false };
    if (returned !== "") { lastEnd = Object.assign({}, request); }
    post(request);
  });
  el("end-no").addEventListener("click", function () { el("end-confirm").hidden = true; });
  el("ret-yes").addEventListener("click", function () {
    var returned = el("ret-at").value.trim();
    if (!returned) { tell("not sent: give the time the animal went back into its home cage, or now", "crit"); return; }
    var request = { kind: "end", session_id: returnFor, returned: returned, confirm: false };
    el("return-form").hidden = true;
    lastEnd = Object.assign({}, request);
    post(request);
  });
  el("ret-no").addEventListener("click", function () { el("return-form").hidden = true; });
  el("amend-yes").addEventListener("click", function () {
    el("amend-form").hidden = true;
    if (!lastOpen) { tell("not sent: this page sent no departure to amend", "crit"); return; }
    post(Object.assign({}, lastOpen, { answer: "amend", amend_to: el("amend-to").value.trim(), amend_reason: el("amend-why").value.trim() }));
  });
  el("amend-no").addEventListener("click", function () { el("amend-form").hidden = true; });
```

In the `#:` comment above `_SCRIPT`, add a last paragraph:

```python
#:
#: **Sessions from the page (P4d-2b b3a-2).** Choosing a task, or pressing the pre-flight
#: pill, takes the pre-flight (`check`); *start run* sends the task of the pre-flight
#: shown, the trial count and the unknown items ticked, then clears the ticks; *new
#: session* sends the dialog's fields as typed; *end session* sends the return typed, or
#: none for later; a warning's *confirm* or *amend* re-sends the open or the return this
#: page sent, with its answer, and a warning this page did not raise is not answered.
#: A swap keeps a select's chosen option and the ticks. It still renders nothing itself.
```

- [ ] **Step 7: Run the tests, and parse the script**

Run: `python3 -m pytest tests/test_web.py tests/test_serve.py -q -p no:cacheprovider`
Expected: all pass, every b1 and b2a script pin among them.

If `node` is on this machine, check the script parses (a smoke check, not a test; CI has no `node`):

```bash
python3 -c "from wl_xcon.web import _SCRIPT; open('${TMPDIR:-/tmp}/wlx-page.js', 'w').write(_SCRIPT)" && node --check "${TMPDIR:-/tmp}/wlx-page.js" && echo parses
```
Expected: `parses`.

- [ ] **Step 8: The architecture's `console` row**

In `docs/design/architecture.md`'s `console` row, replace `— no console sends these four yet: the page's forms for them wait on b3a-2 —` with `— which the page's forms send since b3a-2, through `POST /commands`, built by the wire's own rules (`link._command_from`) —`.

- [ ] **Step 9: The whole suite, then commit**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

```bash
git add wl_xcon/web.py tests/test_web.py docs/design/architecture.md
git commit -m "Send the page's session forms, and re-send a typed time with its warning's answer"
```

---

### Task 7: Spec §6.5 end to end, through the page's endpoints

**Files:**
- Test: `tests/test_serve.py` (a new end-to-end section at the end)

**Interfaces:**
- Consumes: everything above; `service.Service`; `cli._load_allocation`; `tests/_rig.RIG`; this file's `_three_endpoints`, `_trial_budget`, `CONTROL_TRIAL_BUDGET`, `CONTROL_TRIAL_PACE_S`, `_post`, `_stream`, `_events`, `TOKEN`, `MANUAL_REWARD_CODE`, `REWARD_ML`, and its autouse `_torn_down_servers`, which tears down every `Server` a test builds.

**Read `CONTROL_TRIAL_BUDGET`'s comment and `tests/test_service.py`'s `_Rig` first, and heed both**: every trial is paced and budgeted, every wait has a deadline and ends early (within `LAST_FRAME_S`) once the service's thread has gone, the service's `ZmqLink` is built on its own thread, and a test that ends with a run going stops it before it stops the service. b3a-1 drove §6.5's cases through the service's commands (`tests/test_service.py`, `test_e2e_*`); these drive them **through the page's endpoints** -- each a `POST /commands` as Task 6's script sends it, over a real `wlx serve` to a real `wlx taskd`, and each page check read from the fragments a browser's first event carries.

- [ ] **Step 1: Write the tests**

In `tests/test_serve.py`, add `import argparse`, `import html` and `import shutil` to the imports; `RIG` to `from _rig import DIRECT, PATH as RIG_FILE`; `Telemetry` to the `wl_xcon.link` import list; `_load_allocation` to `from wl_xcon.cli import main`; and `from wl_xcon import marks` and `from wl_xcon.service import Service`. Then append:

```python
# --- P4d-2b b3a-2: sessions from the page, end to end (spec §6.5) ---------------------

#: The reference config whose out-of-cage limit is a ten-minute placeholder
#: (`tasks/reference_bounds.py`), passed between runs by moving the service's wall.
TEN_MINUTES = "tasks/reference_bounds.py"
#: The one task these services offer, copied into `--tasks`.
TASK = "fixation_detection.py"
#: What nothing measures yet, acknowledged by name to start a run.
UNKNOWN = ["pump calibration", "eye tracker"]
#: Who the page's commands are recorded as (`serve._person`).
BY = "jake (box, unverified)"
#: `wlx taskd`'s head-fixation, release, run-start and run-end codes (`tasks/allocation.py`).
HEAD_FIXED, HEAD_RELEASED, RUN_START, RUN_END = 4128, 4129, 4135, 4136


def _service_folders(tmp_path, bounds: str = TWELVE_HOURS, animals=("REFERENCE",)):
    """`--subjects`, `--tasks` and `--root` for a service, as `tests/test_service.py`'s
    `_folders` builds them -- copied, for `_main_uninterrupted`'s reason."""
    subjects, tasks, root = tmp_path / "subjects", tmp_path / "tasks", tmp_path / "sessions"
    for animal in animals:
        (subjects / animal).mkdir(parents=True)
        (subjects / animal / "bounds.py").write_text(
            Path(bounds).read_text().replace('subject="REFERENCE"', f'subject="{animal}"')
        )
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    root.mkdir()
    return subjects, tasks, root


def _typed(seconds_ago: float = 0.0) -> str:
    """A time as a person types it, with its date: `seconds_ago` before this host's now
    (negative is after it)."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - seconds_ago))


def _open_body(**over) -> dict:
    """What the page's *New session* dialog sends (Task 6's `openSession`)."""
    body = {
        "kind": "open", "session_id": "2027-01-14_01", "animal": "REFERENCE",
        "deployment": "rig_fixed", "view": "direct", "departure": _typed(),
        "delivered_today": 0, "answer": None, "amend_to": None, "amend_reason": "",
    }
    body.update(over)
    return body


def _start_body(**over) -> dict:
    """What *start run* sends: the task's own values, both unknowns acknowledged."""
    body = {"kind": "start", "task": TASK, "values": {}, "trials": 3, "acknowledged": list(UNKNOWN)}
    body.update(over)
    return body


def _end_body(returned="now", **over) -> dict:
    """What *end session* or the return form sends."""
    body = {"kind": "end", "session_id": "2027-01-14_01", "returned": returned, "confirm": False}
    body.update(over)
    return body


def _between(frame) -> bool:
    return isinstance(frame, Telemetry) and frame.phase == "between_runs"


def _record(root, name: str, session_id: str = "2027-01-14_01") -> list[dict]:
    path = Path(root) / session_id / "xcon" / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class _Taskd:
    """A real `wlx taskd` on a thread, over a `ZmqLink` built there, and a real `wlx serve`
    beside it -- the page's two processes -- and what a test reads them through: every
    frame published, on this test's own SUB socket (`_Session.seen`'s reason); the page's
    fragments as a browser's first event carries them; and the cards its sessions strobed
    onto. `tests/test_service.py`'s `_Rig` with a `Server`, copied rather than imported
    for `_main_uninterrupted`'s reason; every trial paced and budgeted as
    `CONTROL_TRIAL_BUDGET` says."""

    def __init__(self, tmp_path, monkeypatch, zmq_cleanup, *, folders=None,
                 bounds=TWELVE_HOURS, wall=None):
        from wl_xcon import dio

        _trial_budget(monkeypatch, CONTROL_TRIAL_BUDGET, pace_s=CONTROL_TRIAL_PACE_S)
        self.cards: list = []
        cards = self.cards

        class _KeptCard(dio.Simulated):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                cards.append(self)

        self._card = _KeptCard
        self.pub, self.rep, self.mark = _three_endpoints(zmq_cleanup)
        self.folders = folders or _service_folders(tmp_path, bounds)
        self.wall = wall
        self.stop = threading.Event()
        #: Set by a test to leave without `shutdown`, as a crash would.
        self.crash = False
        self.recorder = zmq_cleanup(
            ZmqConsole(self.pub, None, settle_s=0.0, receive_timeout_s=0.0)
        )
        self.frames: list = []
        self._looked = 0
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.server = Server(
            sub=self.pub, req=self.rep, mark=self.mark, http=("127.0.0.1", 0), token=TOKEN
        )
        self.server.start()

    def _serve(self) -> None:
        subjects, tasks, root = self.folders
        with ZmqLink(self.pub, self.rep, self.mark) as link:
            service = Service(
                rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
                allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
                root=root, link=link, card=self._card, wall_clock=self.wall,
            )
            try:
                service.serve(self.stop)
            finally:
                if not self.crash:
                    service.shutdown()

    def post(self, body: dict):
        """`POST /commands` as the box's page sends it, from a person named jake."""
        return _post(self.server.address[1], {**body, "by": "jake"})

    def seen(self, predicate, seconds: float = 10.0):
        """The first frame published, from the last one this returned on, for which
        `predicate` is true -- each read as it arrives. Fails within `seconds`, or within
        `LAST_FRAME_S` once the service's thread has gone (`tests/test_service.py`'s
        `_Rig.seen`, for its reason)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            while self._looked < len(self.frames):
                frame = self.frames[self._looked]
                self._looked += 1
                if predicate(frame):
                    return frame
            try:
                self.frames.append(self.recorder.receive())
                continue
            except TimeoutError:
                pass
            if not self.thread.is_alive():
                deadline = min(deadline, time.monotonic() + LAST_FRAME_S)
            time.sleep(0.005)
        ended = "" if self.thread.is_alive() else "; the service had ended"
        raise AssertionError(f"no frame within {seconds} s satisfied {predicate}{ended}")

    def page(self, predicate, seconds: float = 10.0) -> dict:
        """The page's fragments once this console holds a frame for which `predicate` is
        true: a browser's first event, the full render (spec §4.3)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            latest = self.server.hub.snapshot(on_box=True, stale_after_s=30.0)[0]
            if latest is not None and predicate(latest):
                with _stream(self.server.address[1]) as response:
                    return next(_events(response, deadline_s=seconds))["frags"]
            time.sleep(0.01)
        raise AssertionError(f"the console held no frame within {seconds} s satisfying {predicate}")

    def __enter__(self) -> "_Taskd":
        self.thread.start()
        try:
            self.seen(lambda frame: True)  # the subscription is live
        except BaseException:
            # `with` does not call `__exit__` when `__enter__` raises.
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc_info) -> None:
        if self.thread.is_alive():
            try:
                self.post({"kind": "stop"})  # a run left going is stopped at its boundary
            except Exception:  # noqa: BLE001 -- best-effort cleanup
                pass
        self.stop.set()
        self.thread.join(timeout=30)
        assert not self.thread.is_alive(), "the service did not stop"


def test_page_e2e_open_a_session_run_it_twice_and_end_it(tmp_path, monkeypatch, zmq_cleanup):
    """Spec §6.5, through the page's endpoints: open a session, two runs, end it. The
    first run's *start run* is pressed twice before the run shows (Review Focus 5): one
    run, the second press refused on the feed, never queued behind it."""
    with _Taskd(tmp_path, monkeypatch, zmq_cleanup) as taskd:
        assert taskd.post(_open_body()) == (200, {"status": "sent", "said": SERVICE_SENT})
        taskd.seen(_between)
        before = taskd.page(_between)
        assert taskd.post({"kind": "check", "task": TASK, "values": {}})[0] == 200
        taskd.seen(lambda f: _between(f) and f.preflight is not None)
        checked = taskd.page(lambda f: _between(f) and f.preflight is not None)
        # Fifty trials, so the second press -- sent the moment the first is acknowledged
        # -- reaches the rig while the run it started is still going.
        assert taskd.post(_start_body(trials=50))[0] == 200
        assert taskd.post(_start_body(trials=50))[0] == 200
        taskd.seen(lambda f: _between(f) and f.run_index == 0 and f.stop_kind == "completed")
        twice = taskd.seen(lambda f: _between(f) and any(r.name == "start" for r in f.refusals))
        assert taskd.post(_start_body())[0] == 200
        taskd.seen(lambda f: _between(f) and f.run_index == 1 and f.stop_kind == "completed")
        assert taskd.post(_end_body())[0] == 200
        taskd.seen(lambda f: isinstance(f, Idle))

    root = taskd.folders[2]
    runs = _record(root, "runs.jsonl")
    assert [(r["event"], r["run"]) for r in runs] == [("start", 0), ("end", 0), ("start", 1), ("end", 1)]
    for start in (runs[0], runs[2]):
        assert start["by"] == BY and start["layers"]["run"] == {}
        assert start["layers"]["task"]["fix_hold"] == 0.3
        assert {r["name"]: r["acknowledged_by"] for r in start["preflight"] if r["result"] == "unknown"} == {
            name: BY for name in UNKNOWN
        }
    (refusal,) = [r for r in twice.refusals if r.name == "start"]
    assert refusal.by == BY
    assert "already starting" in refusal.why or "a run is in progress" in refusal.why
    codes = taskd.cards[0].codes
    assert codes[0] == HEAD_FIXED and codes[-1] == HEAD_RELEASED
    assert codes.count(RUN_START) == codes.count(RUN_END) == 2
    assert [row["kind"] for row in _record(root, "welfare_notes.jsonl")] == [
        "departure", "session opened", "returned", "session ended",
    ]
    assert "take the pre-flight first" in before["controls"]
    assert '<option value="fixation_detection.py">' in before["task-sel"]
    assert 'data-task="fixation_detection.py">start run</button>' in checked["controls"]
    assert "pre-flight · 2 to acknowledge" in checked["pf-pill"]


def test_page_e2e_the_limit_reached_between_runs_refuses_a_run_and_the_page_asks_for_the_return(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: the service's wall is this host's, moved forward by the test once the
    first run has ended, so the ten-minute placeholder limit passes between runs. The
    page then shows the pre-flight's fail, greys *start run* with it, and offers *end
    session*; the rig refuses the start anyway."""
    offset = [0.0]
    with _Taskd(tmp_path, monkeypatch, zmq_cleanup, bounds=TEN_MINUTES,
                wall=lambda: time.time() + offset[0]) as taskd:
        taskd.post(_open_body(departure=_typed(120)))
        taskd.seen(_between)
        taskd.post(_start_body(trials=2))
        taskd.seen(lambda f: _between(f) and f.run_index == 0 and f.stop_kind == "completed")
        offset[0] = 600.0
        taskd.post({"kind": "check", "task": TASK, "values": {}})

        def failed(f) -> bool:
            return _between(f) and f.preflight is not None and any(
                i.name == "out of cage" and i.result == "fail" for i in f.preflight.items
            )

        shown_frame = taskd.seen(failed)
        shown = taskd.page(failed)
        taskd.post(_start_body(trials=2))
        refused = taskd.seen(lambda f: _between(f) and any(r.name == "start" and "out of cage" in r.why for r in f.refusals))
        taskd.post(_end_body())
        taskd.seen(lambda f: isinstance(f, Idle))

    (item,) = [i for i in shown_frame.preflight.items if i.name == "out of cage"]
    assert "end the session (End session) and record the animal's return" in item.said
    assert html.escape(item.said) in shown["preflight"]
    assert 'disabled title="pre-flight: out of cage failing">start run</button>' in shown["controls"]
    assert 'data-cmd="end" data-session="2027-01-14_01">end session</button>' in shown["end-actions"]
    assert "pre-flight · 1 fail" in shown["pf-pill"]
    assert refused.run_index == 0, "no second run"
    assert len(_record(taskd.folders[2], "runs.jsonl")) == 2


def test_page_e2e_a_crash_strands_the_animal_and_its_return_is_recorded_from_its_banner(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: a crash and restart refuses a new session until the stranded animal's
    return is recorded -- here from the page: its banner's *end session…* names its
    session, and the refusal tells a person to use it (XC-176)."""
    folders = _service_folders(tmp_path, TWELVE_HOURS, ("B", "REFERENCE"))
    with _Taskd(tmp_path, monkeypatch, zmq_cleanup, folders=folders) as first:
        first.post(_open_body())
        first.seen(_between)
        first.crash = True

    with _Taskd(tmp_path, monkeypatch, zmq_cleanup, folders=folders) as second:
        found = second.seen(lambda f: isinstance(f, Idle) and f.stranded)
        stranded = second.page(lambda f: isinstance(f, Idle) and f.stranded)
        second.post(_open_body(session_id="2027-01-14_02", animal="B"))
        refused = second.seen(lambda f: isinstance(f, Idle) and any(r.name == "open" for r in f.refusals))
        feed = second.page(lambda f: isinstance(f, Idle) and any(r.name == "open" for r in f.refusals))
        second.post(_end_body(session_id="2027-01-14_01"))
        second.seen(lambda f: isinstance(f, Idle) and f.stranded == ())
        second.post(_open_body(session_id="2027-01-14_02", animal="B"))
        second.seen(lambda f: isinstance(f, Telemetry) and f.subject == "B")

    assert [s.session_id for s in found.stranded] == ["2027-01-14_01"]
    assert 'data-return="2027-01-14_01">end session…</button>' in stranded["banners"]
    assert re.search(r'data-cmd="new" disabled title="[^"]+">new session', stranded["setup"])
    (why,) = [r.why for r in refused.refusals if r.name == "open"]
    assert "Record it with End session, naming its session" in why
    assert html.escape(why) in feed["rt-changes"]
    assert [row["kind"] for row in _record(folders[2], "welfare_notes.jsonl")] == [
        "departure", "session opened", "returned",
    ]


def test_page_e2e_an_unknown_item_is_acknowledged_by_its_name_and_found_in_runs_jsonl(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: the page shows each unknown with a box carrying its exact name; a start
    that ticks none is refused naming them, and one that ticks both runs, the record
    saying who acknowledged each."""
    with _Taskd(tmp_path, monkeypatch, zmq_cleanup) as taskd:
        taskd.post(_open_body())
        taskd.seen(_between)
        taskd.post({"kind": "check", "task": TASK, "values": {}})
        shown = taskd.page(lambda f: _between(f) and f.preflight is not None)["preflight"]
        taskd.post(_start_body(acknowledged=[]))
        refused = taskd.seen(lambda f: _between(f) and any(r.name == "start" for r in f.refusals))
        taskd.post(_start_body())
        taskd.seen(lambda f: _between(f) and f.run_index == 0 and f.stop_kind == "completed")

    for name in UNKNOWN:
        assert f'<input type="checkbox" data-ack="{name}" aria-label="acknowledge {name}"> acknowledge' in shown
    assert "checked" not in shown
    (why,) = [r.why for r in refused.refusals if r.name == "start"]
    assert "pump calibration, eye tracker" in why
    (start,) = [r for r in _record(taskd.folders[2], "runs.jsonl") if r["event"] == "start"]
    assert {r["name"]: r["acknowledged_by"] for r in start["preflight"] if r["result"] == "unknown"} == {
        name: BY for name in UNKNOWN
    }


def test_page_e2e_every_departure_and_return_refusal_is_the_terminals_own_sentence(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: every refusal of the departure and the return, through the page exactly
    as through the terminal -- the sentence the terminal's parser and `welfare` give,
    carried to the page's feed unchanged. One of each kind over the page's endpoints;
    `tests/test_marks.py` and `tests/test_service.py` hold every one."""
    try:
        marks.clock_time("25:99")
    except argparse.ArgumentTypeError as bad:
        unreadable = str(bad)
    with _Taskd(tmp_path, monkeypatch, zmq_cleanup) as taskd:
        taskd.post(_open_body(departure="25:99"))
        taskd.seen(lambda f: isinstance(f, Idle) and any(r.why == unreadable for r in f.refusals))
        taskd.post(_open_body(departure=_typed(-3600)))
        taskd.seen(lambda f: isinstance(f, Idle) and any("in the future" in r.why for r in f.refusals))
        taskd.post(_open_body(departure=_typed(13 * 3600)))
        past = taskd.seen(lambda f: isinstance(f, Idle) and any("at or outside the limit" in r.why for r in f.refusals))
        far = _typed(2 * 3600)
        taskd.post(_open_body(departure=far))
        asked = taskd.seen(lambda f: isinstance(f, Idle) and f.question is not None)
        banner = taskd.page(lambda f: isinstance(f, Idle) and f.question is not None)["banners"]
        amend = dict(departure=far, answer="amend", amend_to=_typed(600))
        taskd.post(_open_body(**amend))
        taskd.seen(lambda f: isinstance(f, Idle) and any("no reason given" in r.why for r in f.refusals))
        taskd.post(_open_body(amend_reason="typed the hour before for the one after", **amend))
        taskd.seen(_between)
        before = _typed(3600)
        taskd.post(_end_body(returned=before))
        taskd.seen(lambda f: isinstance(f, Telemetry) and f.question is not None and f.question.mark == "return")
        taskd.post(_end_body(returned=before, confirm=True))
        early = taskd.seen(lambda f: isinstance(f, Telemetry) and any("having left it at" in r.why for r in f.refusals))
        feed = taskd.page(lambda f: isinstance(f, Telemetry) and any("having left it at" in r.why for r in f.refusals))["rt-changes"]
        taskd.post(_end_body())
        taskd.seen(lambda f: isinstance(f, Idle))

    assert past.question is None, "a departure past the ceiling is refused, never asked about"
    assert asked.question.answers == ("confirm", "amend")
    for answer in ("confirm", "amend"):
        assert f'data-answer="{answer}" data-mark="departure" data-session="2027-01-14_01"' in banner
    (why,) = [r.why for r in early.refusals if "having left it at" in r.why]
    assert html.escape(why) in feed
    assert [row["kind"] for row in _record(taskd.folders[2], "welfare_notes.jsonl")] == [
        "departure", "departure amended", "session opened", "returned", "session ended",
    ]
    assert [p.name for p in taskd.folders[2].iterdir()] == ["2027-01-14_01"], (
        "nothing was written for a refused open"
    )


def test_page_e2e_the_hand_reward_is_given_between_runs_and_while_the_return_is_awaited(
    tmp_path, monkeypatch, zmq_cleanup
):
    """PI, 2026-09-29 (spec §6.0), through the page: between runs and while the return is
    awaited, one press is one `reward_correct` on the fluid total, the record and the
    recorded event stream; while a run's trials run it is still refused (XC-157), and
    with no session open too (XC-158)."""
    with _Taskd(tmp_path, monkeypatch, zmq_cleanup) as taskd:
        taskd.post(_open_body())
        opened = taskd.seen(_between)
        live = taskd.page(_between)["controls"]
        assert taskd.post({"kind": "reward"}) == (200, {"status": "sent", "said": REWARD_SENT})
        between = taskd.seen(lambda f: _between(f) and any(c.kind == "reward" for c in f.controls))
        taskd.post(_start_body(trials=300))
        taskd.seen(lambda f: isinstance(f, Telemetry) and f.phase == "running" and f.trial_index >= 2)
        taskd.post({"kind": "reward"})
        running = taskd.seen(lambda f: isinstance(f, Telemetry) and any(r.name == "reward" for r in f.refusals))
        taskd.post({"kind": "stop"})
        taskd.seen(lambda f: _between(f) and f.run_index == 0)
        taskd.post(_end_body(returned=None))
        taskd.seen(lambda f: isinstance(f, Telemetry) and f.phase == "awaiting_return")
        waiting = taskd.page(lambda f: isinstance(f, Telemetry) and f.phase == "awaiting_return")["controls"]
        taskd.post({"kind": "reward"})
        awaiting = taskd.seen(
            lambda f: isinstance(f, Telemetry) and f.phase == "awaiting_return"
            and [c.kind for c in f.controls].count("reward") == 2
        )
        taskd.post(_end_body())
        taskd.seen(lambda f: isinstance(f, Idle))
        taskd.post({"kind": "reward"})
        idle_frame = taskd.seen(lambda f: isinstance(f, Idle) and any(r.name == "reward" for r in f.refusals))

    button = '<button type="button" class="btn" data-cmd="reward">give reward</button>'
    assert button in live and button in waiting
    assert between.fluid_session_ml == pytest.approx(opened.fluid_session_ml + REWARD_ML)
    assert between.controls[-1].said == "0.05 mL of reward_correct, given between runs"
    (during,) = [r for r in running.refusals if r.name == "reward"]
    assert "the session is not paused" in during.why and "no reward was given" in during.why
    assert awaiting.controls[-1].said == (
        "0.05 mL of reward_correct, given while the animal's return is awaited"
    )
    (none,) = [r for r in idle_frame.refusals if r.name == "reward"]
    assert "no session is open, so no reward was given" in none.why and "XC-158" in none.why
    assert taskd.cards[0].codes.count(MANUAL_REWARD_CODE) == 2, "one press, one reward, none refused"
    rows = [row for row in _record(taskd.folders[2], "controls.jsonl") if row["kind"] == "reward"]
    assert [(r["by"], r["ml"], r["entry"]) for r in rows] == [(BY, REWARD_ML, "reward_correct")] * 2
```

- [ ] **Step 2: Run them, three times**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_serve.py -q -p no:cacheprovider -k page_e2e` three times in a row.
Expected: PASS each time. A flake is a wait that looked at the wrong thing, not bad luck: find the frame the test missed from `seen`'s or `page`'s message before touching a number.

- [ ] **Step 3: Prove a broken route to the rig fails them fast**

Run, with nothing else running on the tree:

```bash
python3 tools/mutate.py --returns None wl_xcon/serve.py parse_command
```
Expected: `caught ... N failed`, the `page_e2e` tests among the failures named, well inside the harness's 300 s. A `timed out` is an unbounded wait: fix the wait, not the budget.

- [ ] **Step 4: The whole suite, then commit**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

```bash
git add tests/test_serve.py
git commit -m "Drive spec 6.5's session cases end to end through the page's endpoints"
```

---

### Task 8: Say what changed, prove the tests can fail, and prepare the PI's review

**Files:**
- Modify: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` (a new §6.7), `docs/design/architecture.md` (a consistency read), `docs/backlog.md` (close XC-016 and XC-176)
- Create, **not committed**: `.superpowers/b3a2/welfare-summary.md` (git-ignored), the mutation driver and its logs under `${TMPDIR:-/tmp}`
- **Do not edit `docs/CHECKPOINT.md`: the controller writes it** (Step 8 hands it what it needs).

- [ ] **Step 1: "Not yet" sentences** (CLAUDE.md: a "not yet" comment is a dated claim)

Run: `git grep -n -e "b3a-2" -e "waits on b3a" -e "no console sends these four" -e "are b3a-2's" -e "is b3a-2's" -e "stop…" -- wl_xcon tasks docs/design tests`
Expected: no hit that describes this branch's work as still to come. Rewrite any such hit to say what is true now, naming what a remaining one waits for (b3b/XC-150, XC-157, XC-158, XC-184). A hit in `docs/superpowers/` is a dated record and stays.

- [ ] **Step 2: The spec, where this plan decided what §6 left open**

In the P4d-2b spec, after §6.6, add:

```markdown
### 6.7 Decided by the b3a-2 plan (2026-09-30), for the PI's review with §6.4

`docs/superpowers/plans/2026-09-30-p4d2b-b3a2-page-sessions.md` decided what this section
left open; the welfare ones are in its summary for the PI.
- **Starting values are the task's own, declared on each parameter** (plan decision 1):
  `Param.start`, under what a run is given, both layers in its `runs.jsonl` start row (S8
  §3.4). `fixation_detection` declares the values the mockup shows; a task that uses a
  number with no value is refused by its pre-flight, naming it (decision 2).
- **The hand reward between runs and while the return is awaited** (decision 4) is given
  in a `wlx taskd` session; during a trial (XC-157), with no session open (XC-158) and after
  a `wlx run` session's run (XC-184) it stays refused. §5.2's *give reward* is live
  between runs and while the return is awaited, as well as while paused.
- **The page's four commands are built by the wire's own function** (decision 3), and
  answered *sent* with what the page will show.
- **A far return's warning offers what the rig takes** (decision 16, the controller's
  ruling of 2026-09-30): "Confirm it, or type it again", since a return has no
  amendment; a far departure's warning is unchanged. Words only, in `welfare.py`.
- **The page's forms** (decisions 6-12): the mockup's `dlg-new`, `pf-panel`, `pf-pill`,
  `a-start`, `a-stop` and `end-confirm`, with the departure given no `now`, the id typed,
  deployment, setup and fluid given today added, no rig or save folder, an acknowledgement
  box per unknown item, the run's trial count (1000, `wlx run`'s default), *end session*
  then *record return…*, and a stranded animal's *end session…* on its banner.
```

Read `docs/design/architecture.md`'s welfare-critical paragraphs and `console` row once through against Plan decision 16, and fix any sentence Tasks 2 and 6 left contradicting another.

```bash
git add docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md docs/design/architecture.md wl_xcon tests
git commit -m "Record what the b3a-2 plan decided that the spec left open"
```

- [ ] **Step 3: Prove the tests can fail -- every new and changed function, read line by line**

**Never run the suite, edit a test or `git add` while a lane is running**: the harness neuters a module's file in place. Each lane is its own `git archive` copy of the branch tip, with `wl-preproc` linked inside it (`tests/conftest.py` looks there) and `PYTHONPATH` set to the copy. Each lane takes one baseline, neuters its targets in turn with the copy's own `tools/mutate.py`, and takes one restore -- the harness's method without a baseline and a restore per function (CHECKPOINT, 2026-09-30, "Learned, worth keeping"):

```bash
PREPROC="$(cd .. && pwd)/wl-preproc"   # the checkout beside this one; CI's is inside it
tip=$(git rev-parse HEAD)
cat > "${TMPDIR:-/tmp}/b3a2-drive.py" <<'DRIVE'
"""One baseline, each target neutered in turn by the copy's own `mutate()`, one restore."""
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "tools"))
import mutate  # noqa: E402 -- the copy's own, so its ROOT is the copy

mutate._restore_any_interrupted_run()
ok, baseline, failures = mutate._run_suite()
print(f"baseline: {baseline}", flush=True)
if not ok:
    print("\n".join(failures))
    raise SystemExit(1)
for line in sys.stdin:
    if not line.strip():
        continue
    module, name, returns = line.split()
    caught, summary = mutate.mutate(root / "wl_xcon" / f"{module}.py", name, returns)
    label = (
        "SKIPPED" if caught is None
        else "inert" if caught == mutate.INERT
        else "caught" if caught
        else "SURVIVED"
    )
    print(f"  {label:9} {module}.{name:28} {summary}", flush=True)
ok, restored, failures = mutate._run_suite()
print(f"restored: {restored}", flush=True)
print("\n".join(failures))
DRIVE
lane() {  # lane NAME, then "module function returns" lines on stdin
  dir="${TMPDIR:-/tmp}/b3a2-lane-$1"
  rm -rf "$dir" && mkdir -p "$dir"
  git archive "$tip" | tar -x -C "$dir"
  ln -s "$PREPROC" "$dir/wl-preproc"
  (cd "$dir" && PYTHONPATH="$dir" WLX_REQUIRE_PREPROC=1 python3 "${TMPDIR:-/tmp}/b3a2-drive.py" "$dir") \
    > "${TMPDIR:-/tmp}/b3a2-lane-$1.txt" 2>&1
}
lane values <<'EOF' &
check parameters_used []
preflight values None
taskd run None
EOF
lane reward <<'EOF' &
taskd _command None
taskd _manual_reward None
taskd receive None
service _route None
welfare _far_from_now None
EOF
lane wire <<'EOF' &
link _decode_command None
link _command_from None
serve parse_command None
serve dispatch None
serve _delivered None
EOF
lane page1 <<'EOF' &
web fragments None
web _idle None
web _controls None
web _outside_a_run None
web _start_button None
web _mark_button None
web _reward_button None
web _reward_answer None
web _hand_reward_now None
web _banners None
web _question_banner None
web _idle_banners None
EOF
lane page2 <<'EOF' &
web _options None
web _pf_state None
web _pf_pill None
web _pf_sum None
web _pf_row None
web _preflight_pane None
web _end_actions None
web _idle_setup None
web _new_session_button None
web page None
EOF
wait
```

(`check` is `[]` as `tools/mutation_gate.py`'s `RETURNS` has it; every other module here is `None`.)

Then read every line of every lane's file, not its exit code:
- every function `caught` with `N failed` and a `<-` naming tests that are about it; `N errors in 0.Ns`, a timeout, or one unrelated test is not a catch (trap 7);
- zero `SURVIVED`, zero `SKIPPED`; `inert` only for a function whose body already returns at once, named;
- the `baseline:` and `restored:` lines the suite's own passed count.

A survivor is a missing test: write it in the owning task's test file, commit it (with no lane running), and re-run that function alone in a fresh lane. A function nothing can test is deleted, not exempted. A lane's `timed out` line is re-run alone before it is believed or blamed; one that still times out is an unbounded wait, fixed in the owning test.

- [ ] **Step 4: The welfare-critical surface is what Plan decision 16 says**

```bash
git diff main -- wl_xcon/bounds.py wl_xcon/marks.py wl_xcon/stranded.py | wc -l
git diff main -- wl_xcon/welfare.py | grep "^[+-]" | grep -v "^[+-][+-]"
```
Expected: `0` for the first. The second shows `welfare.py`'s whole change, all of it inside `Welfare._far_from_now` (Task 5 Step 6): the four added comment lines, the added `other = "amend it with a reason" if what == "departure" else "type it again"`, and the one line `f"on trust (PI, 2026-09-20). Confirm it, or amend it with a reason -- an "` replaced by `f"on trust (PI, 2026-09-20). Confirm it, or {other} -- an "`. Anything else is a change nobody ruled on: revert it.

```bash
python3 - <<'EOF'
import ast, subprocess
def code(fn):
    """A function's code, its docstring left out."""
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body
    return ast.dump(ast.Module(body=body, type_ignores=[])) + ast.dump(fn.args)
def defs(text):
    found = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef):
            found[node.name] = code(node)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    found[f"{node.name}.{item.name}"] = code(item)
    return found
EXPECTED = {
    "wl_xcon/taskd.py": {
        "Session._ends": "same", "Session._hold": "same", "Session.set": "same",
        "Session._schedule": "same",
        "Session._command": "CHANGED", "Session._manual_reward": "CHANGED",
    },
    "wl_xcon/link.py": {"_setting": "same"},
    "wl_xcon/preflight.py": {"out_of_cage": "same", "gate": "same"},
    "wl_xcon/service.py": {
        "Service._open": "same", "Service._end": "same", "Service._unended": "same",
        "Service._close_stranded": "same", "Service._start": "same",
        "_unasked": "same", "_folder_name": "same",
    },
    "wl_xcon/cli.py": {"_settle_departure": "same", "_settle_return": "same", "main": "same"},
}
# `welfare.py` is welfare-critical whole: every function and method in it the same,
# but `_far_from_now`, whose words Task 5 Step 6 changed.
old_welfare = defs(subprocess.run(["git", "show", "main:wl_xcon/welfare.py"], capture_output=True, text=True, check=True).stdout)
EXPECTED["wl_xcon/welfare.py"] = {
    name: "CHANGED" if name == "Welfare._far_from_now" else "same" for name in old_welfare
}
for path, names in EXPECTED.items():
    old = defs(subprocess.run(["git", "show", f"main:{path}"], capture_output=True, text=True, check=True).stdout)
    new = defs(open(path).read())
    assert path != "wl_xcon/welfare.py" or set(new) == set(old), "a welfare.py function came or went"
    for name, expected in names.items():
        found = "same" if old[name] == new[name] else "CHANGED"
        print(f"{'ok ' if found == expected else 'BAD'} {found:8} {path}:{name}")
EOF
```
Expected: every line `ok`, `Welfare.departure_needs_confirmation` and `Welfare.return_needs_confirmation` among the `same`.

```bash
git diff main -- wl_xcon/taskd.py | grep -n "except (Exceeded, TypeError)"
grep -c "self._manual_reward(command.by, index, held)" wl_xcon/taskd.py
```
Expected: the first prints nothing (`_command`'s `except` line untouched); the second prints `1` (the pass-through, moved, not duplicated).

- [ ] **Step 5: The whole suite, three times**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider -rs` three times in a row.
Expected: all pass each time, and no skip from `test_health.py`, `test_serve.py` or `test_service.py`. Note the passed count for Step 8.

- [ ] **Step 6: The PI's welfare summary**

Write `.superpowers/b3a2/welfare-summary.md` (git-ignored; not committed) for the controller to put to the PI in the question UI as numbered items to approve (he wants items, not files), in plain words, each with the tests that pin it. **A reviewer checks it against the code before the PI sees it** (CHECKPOINT, 2026-09-30: b3a-1's summary twice claimed more than the code did):

1. **The hand reward now works between runs and while the animal's return is awaited** (your rule of 2026-09-29), in sessions run from the page (`wlx taskd`). One press is one delivery of the animal's `reward_correct` at its current size, through the same path a task's reward takes: counted in the session's fluid and today's total, marked in the neural recording as a manual reward (4134), written to the session record with who pressed it and where ("given between runs", "given while the animal's return is awaited"). The page's button is live in both. Pinned by `test_between_runs_a_hand_reward_is_one_correct_trial_reward_through_the_tasks_path`, `test_the_hand_reward_works_between_runs_and_while_the_return_is_awaited` and `test_page_e2e_the_hand_reward_is_given_between_runs_and_while_the_return_is_awaited`.
2. **Where it is still refused, with a sentence and nothing given**: during a run's trials -- there it works only while the run is paused, as before; the reward at the moment it is pressed is its own slice (XC-157) -- with no session open (the line flush, XC-158), and after the run of a session started at the terminal (`wlx run`), whose return is typed at the terminal (XC-184). A "stop after X mL" belongs to the run it was set on, so none applies between runs. Pinned by `test_during_a_run_a_hand_reward_is_still_given_only_while_paused`, `test_with_no_session_open_a_hand_reward_is_refused_and_says_what_it_waits_for`, `test_after_the_loop_a_manual_reward_is_refused_and_nothing_is_given`, and b2a's paused-reward tests, unchanged.
3. **What changed in the code you review**: the one line that hands a reward command on (`Session._command`) now comes before the check that refuses commands outside a run, and `Session._manual_reward` decides by phase. Its rules during a run are b2a's, word for word. `bounds.py` is unchanged, and so is every rule in `welfare.py` (item 6 is its one change, to words). Pinned by Step 4's check.
4. **A pump failure on a hand reward outside a run ends `wlx taskd`**: the reward is charged, the session is recorded as ended with its return not recorded, and on restart no session opens until that animal's return is recorded -- b3a-1's rule for any unexpected failure between runs. Only the simulated pump exists today; the alternative is to keep the session open and show the failure on the page. Pinned by `test_a_pump_that_fails_a_hand_reward_between_runs_is_not_caught`.
5. **The page's route into the two marks**: the page sends each time exactly as typed; a confirm or an amendment is sent only as the answer to the warning shown, re-sending the same typed time, and the rules that decide are b3a-1's, unchanged (`marks.py` and the service's route, identical by Step 4). *End session* is two steps: the head's release when it is pressed, the return then or later; a stranded animal's return is recorded from its banner, naming its session. Pinned by `test_page_e2e_every_departure_and_return_refusal_is_the_terminals_own_sentence` and `test_page_e2e_a_crash_strands_the_animal_and_its_return_is_recorded_from_its_banner`.
6. **A far return's warning now offers what the rig takes.** When a return is typed more than thirty minutes from now, the warning used to end "Confirm it, or amend it with a reason" -- but a return cannot be amended, only confirmed or typed again, which is all the terminal and the page offer. It now ends "Confirm it, or type it again". The departure's warning is word for word what it was, and nothing about when a warning appears, or what is refused, changed: only the words, in `welfare.py`'s one sentence-building function (`_far_from_now`). Pinned by `test_a_far_returns_sentence_offers_a_confirmation_or_the_time_typed_again` and `test_a_far_departures_sentence_is_unchanged_confirm_or_amend_with_a_reason`.
7. **Nothing was added to the list of code that needs your review.** Checked unchanged: `bounds.py`, every `welfare.py` function but that sentence's, `marks.py`, `stranded.py`, the pre-flight's out-of-cage item and gate, the service's seven functions, `taskd`'s `_ends`, `_hold`, `set`, `_schedule` and `_command`'s `except` line, `link._setting`, and `cli`'s three.

And, for his information and not as a welfare item: **each run now starts from its task's own values** (`fixation_detection`'s are the mockup's: fixation timeout 4.0 s, hold 0.3 s, response window 0.6 s, target hold 0.2 s, fixation window 2.0°, target window 3.0°, target at 10°), and a task that uses a number with no value is refused at its pre-flight rather than faulting at its first trial (Plan decisions 1 and 2).

- [ ] **Step 7: Close what this made true**

In `docs/backlog.md`, delete the lines of **XC-016** (this slice) and **XC-176** (its two sentences name the page's End session, which now exists: `preflight.out_of_cage`'s "end the session (End session)" is the Summary's *end session*, and `Service._open`'s "Record it with End session, naming its session" is the stranded banner's *end session…*). Leave XC-018 and XC-150, which waited on XC-016, as they are: their other waits stand.

Run: `python3 -m pytest tests/test_backlog.py -q -p no:cacheprovider`
Expected: PASS.

```bash
git add docs/backlog.md
git commit -m "Close the page's half of the session service (closes XC-016, XC-176)"
```

- [ ] **Step 8: Hand the controller what CHECKPOINT needs**

Report, for the controller to write (do not edit `docs/CHECKPOINT.md`):
- the passed count (Step 5), each lane's result (Step 3) with any survivor found and how it was closed, and Step 4's output;
- what was filed (XC-183, XC-184, or the IDs they became) and closed (XC-016, XC-176);
- that `wlx run` now takes a task's own starting values where `--set` gives none, and that its `runs.jsonl` start row's `layers` holds `task` and `run` apart;
- **the branch merges only after the PI approves Step 6's items**, by fast-forward, once CI's push run is read shard by shard (the push escalates to a full sweep: `tasks/` changed).

---
