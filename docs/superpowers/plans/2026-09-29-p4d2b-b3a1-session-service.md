# P4d-2b Slice b3a-1 — The Session Service: Sessions That Outlive Runs, One Departure and Return for Terminal and Page, the Stranded Rule, Pre-flight, Telemetry Schema 10 and `wlx taskd`: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Execution: subagent-driven**, the method this project uses (b1, b2a, direct view): a fresh implementer per task and a fresh reviewer before the next one starts, then a whole-branch review on the most capable model.
>
> **Branch from `main` as `p4d2b-b3a1-session-service`.** b3a-2 (the page: forms, dialogs, the page's endpoints in `serve.py`) is a later plan and builds on this branch's commands and frames.
>
> **Welfare-critical code changes, listed in Plan decision 20 and Task 10 Step 4.** The branch merges only after the PI approves Task 10's numbered summary (P4d-2b spec §6.4; CLAUDE.md). The Question below was answered on 2026-09-29 (keep the size where it was left), so Task 8 Step 3b adds nothing.
>
> **Every commit** ends with the session's attribution lines, as the repository's history does.

**Goal:** One always-on rig service, `wlx taskd`, holds one animal's session across any number of runs — opened, run and ended by a console's commands, with the departure and the return taken under exactly the terminal's rules through one shared piece of code, a pre-flight under S9a §10's rule before every run, telemetry that says honestly when no session or no run exists, and a refusal to open any session while an animal's return is missing from the record.

**Architecture:** A new welfare-critical `marks.py` holds the departure-and-return decision that lived inside `wlx run`'s prompts; the terminal keeps only its prompting and the service calls the same functions. `taskd.Session` gains `RunSpec` and `run(run)`, per-run state that resets while welfare, clocks and the record go on, a `service` mode that sits `between_runs`, and the record's `runs.jsonl`. `link.py` goes to schema 10 with a separate `Idle` frame and four new commands. A new `service.py` owns the loop (idle publishing, commands, runs), the stranded rule (`stranded.py`) and pre-flight (`preflight.py`), and `cli.py` gains `wlx taskd`. The consoles (`wlx console`, `wlx serve`'s page and `/health`) render the new frames; the page's forms are b3a-2's.

**Tech Stack:** Python 3.11–3.13; dataclasses; argparse; ZeroMQ and msgpack (unchanged, ADR-0003); pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §6 (slice b3a, approved in conversation 2026-09-29), with §2 and §5.1–§5.3 for how b2a's controls reach the rig; `docs/superpowers/specs/2026-08-31-S9a-console-design.md` §7 (processes) and §10 (the pre-flight rule); `docs/superpowers/specs/2026-09-26-P4d2a-return-to-cage-design.md` §10 and its 2026-09-29 amendment (the page takes both times).

## Questions for the PI

**Answered 2026-09-29, in the question UI: "Where it was left"** — the recommendation. The next run keeps the reward size a person set, for the rest of that animal's session; Task 8 Step 3b adds no reset. The PI approved this plan the same day ("Approve, build it").

Asked in these words:

1. **When a person changes the reward size during a run, where does the next run in the same session start?** The reward size lives in the animal's bounds file and can be changed from the page during a run (b2a), always under its approved ceiling. When that run ends and another starts for the same animal, the size could either stay where the person left it, or go back to the number in the bounds file. **Recommendation: keep it where the person left it for the rest of the session.** The bounds belong to the session, which is one animal's (spec §6.1); someone who lowered it would not have it quietly raised again; and each run's row in `runs.jsonl` records the size it started with. The plan builds the recommendation (it is what the code does if nothing resets it); if the answer is "back to the file", Task 8 Step 3b adds the reset, with its test.

## Plan decisions

The spec left these to the plan. Each is taken here with its reason, and the code is in the task named.

1. **`Session.service` says what kind of session it is; `run(run)` says which run** (Tasks 2, 3). `service=True` sessions sit `between_runs` after a run, keep the head fixed, and drop a staged change the run never applied; `service=False` (`wlx run`'s, and every existing test's) ends as today — head released at the loop's end, then `await_return`. What happens after a run is a property of the session, not of how its run was described, and keeping the two apart leaves `wlx run`'s behavior unchanged.
2. **Per run and per session, each decided** (Tasks 2, 3). **Reset when each run starts:** the task and its loaded `Trial`, the run's values, scheduler, tally, trial index, `blocks_run`, stop reason and kind, pause, scheduled stop (spec §6.1: "a scheduled stop ends the run it was set on"), recent outcomes, the pending pre-flight and question, and `run_index` (+1). **Kept for the session:** `welfare` (fluid, the marks, restraint), the anchored wall clock, the frame clock `now()` (it never runs backwards, so a wall that follows frames in the tests stays monotonic), the in-session clock, the record (one folder, `config.json`, the refusal cap), the refusal and control feeds, mark numbering and note joins, the parameter-change sequence, the allocation and its looked-up codes, and the bounded config — reward size included (Question 1). **Staged changes are not reset when a run starts**: a change staged before `run()` applies at its first boundary, which `test_a_live_write_is_staged_and_applied_at_a_trial_boundary` pins; for a service session they are dropped when a run ends, with a feed row saying so, because nothing between runs applies them and a row kept there would read "applies at the next trial".
3. **`spec.values` holds the live values of the run in progress** (Task 2): replaced from each `RunSpec` when it starts, and for the run a `SessionSpec` describes it already is that run's. So `Session.set` — welfare-critical, whole — and `_apply_staged` are untouched.
4. **The record** (Task 2). `config.json` is written when the session opens and holds what is fixed: session, subject, deployment, whether it is a service session, the bounded config's values and file, the rig and settings files, and the setup. `runs.jsonl` has **two rows per run**, `start` and `end`, joined by `run` — the spec's "one row per run" (§6.3) as two, because §6.1 says nothing is lost to a crash: the start row, with the pre-flight and who acknowledged each unknown, is on disk before the first trial, and the end row is written from `run()`'s `finally`, so a fault writes it too. Rows in `trials.jsonl`, `controls.jsonl` and `parameter_changes.jsonl` name their run. `SessionRecord` lives for the session; its trial file opens with a run's first trial and closes with the run; the refusal cap is per session, and a truncation notice is written at the close of the run it happened in.
5. **`RUN_START` 4135 and `RUN_END` 4136** (Task 2) go into `tasks/allocation.py` beside 4131–4134, looked up once per session as `OPERATOR_MARK` is. Strobed when allocated; `RUN_END` only for a run that ended by design (completed, operator, limit) — not a fault, whose card may be what failed, nor Ctrl-C. The end row says how the run ended and whether `RUN_END` was strobed. wl-xtasks owns the final numbering.
6. **End session releases the head, then takes the return** (Tasks 3, 7; spec §6.2 left open when a page session's release is recorded). An `EndSession` stops a run in progress at its next boundary, then records the head's release at that moment, then the session awaits its return in `awaiting_return` — `wlx run`'s own phase after its loop. The return may come in the same command or a later one. `welfare` refuses a return while the head is fixed and one before the release, and recording a release earlier than it happened would be inventing an instant; so End session is pressed as the animal leaves the chair. Pressed after the animal is home, the return can still be recorded as `now`, which overcounts time out of the cage, the safe direction (Review Focus 2).
7. **A confirm-or-amend answer and a pre-flight reach a console as fields in the frame, beside a refusal row** (Tasks 4, 7, 8). b2a's consoles learn a command's fate from the next frame's `Refused` rows — the REP reply only says *received*, and is sent before the command is decoded (M8's rule). A question that must stay on screen until it is answered, and a pre-flight a person reads before starting, are state, so they are fields (`question`, `preflight`); the command that was not applied is a row in the feed, as every refusal is. Both are read from published frames in the tests.
8. **The idle frame is its own shape, `link.Idle`, on the same socket and schema** (Task 4). Every `Telemetry` field describes a session; an idle frame with them all optional would put `None` beside every fluid and clock figure the consoles promise never to guess at. `decode` checks the schema first, for both shapes (the schema-mismatch-by-name rule is unchanged), then reads `phase`. `cli.render`, `web.fragments`, `health` and `serve.Hub` each take `Telemetry | Idle` (Task 5).
9. **`service` is on the wire** (Tasks 4, 5): a frame from `wlx taskd` says so, because its stream does not end when a run stops. `health.expects_frames` and `wlx console`'s watch read it: a run's stop frame is not the last frame.
10. **Stranded, and closed** (Task 7). A session folder under `--root` is stranded when its `welfare_notes.jsonl` has a `departure` row with no `returned` row after it — **including `wlx run`'s `return not recorded` sessions**, which are exactly that, and **a record with a line that is not a row** (a crash mid-write), which fails closed: it stays stranded until repaired by hand, since its departure cannot be known. Closing one is an `EndSession` naming it; its return is checked by `welfare.returned_to_cage` against the recorded departure, restored by a new `Welfare.restore_departure` — not `left_cage`, which refuses a departure past the ceiling, and a stranded animal is the likeliest to be past it. Restraint is not reconstructed: its marks are event codes, not rows.
11. **Nothing is written until a page's departure is accepted** (Task 7). The session is built in memory, its departure decided and marked, and only then `session opened` and `config.json`: a refused or unanswered departure leaves no folder, so its id stays free (spec §6.2: an id already used under `--root` is refused). The rows read `departure`, `session opened`; the terminal's order, the reverse, stays.
12. **`wlx taskd` needs an allocation carrying `HEAD_FIXED`, `HEAD_RELEASED`, `PARAM_CHANGED`, `RUN_START` and `RUN_END`** (Task 7). Spec §6.1 lists `--allocation` as optional "as for `wlx run`". Reading the code found that `wlx run --deployment rig-fixed` without one raises `KeyError` after the departure is on record; the service refuses at start instead, naming the codes. The flag stays optional in argparse and its help says the provisional allocation is refused. The `wlx run` defect is filed (Task 10 Step 7).
13. **Pre-flight is the service's** (Tasks 6, 8). `wlx run` keeps its two refusals and takes no acknowledgement; its start row says `preflight: null`. Pre-flight is taken again at every `StartRun`, never trusted from an earlier `CheckRun`. The items are spec §6.2's plus **starting values**, since a run's values arrive from a console and nothing checked `wlx run`'s `--set` either.
14. **The service contains a run's fault** (Task 8). A fault is published and written into the run's end row by `run()`, and printed to the service's stderr here; the session stays open between runs, the animal still out, so its return can be taken. Anything else that raises ends the process, and the stranded rule finds the animal on restart.
15. **A run's seed is drawn by the service** (`secrets.randbelow`) and recorded in its start row (Task 8), so the run can be replayed; the page does not choose seeds.
16. **Marks outside a run are stamped** (Tasks 3, 7): between runs and while the return is awaited, a mark signal is stamped and strobed at once (`OPERATOR_MARK` looked up when the session is built, so one before the first run is strobed too), and its note is joined. While idle a mark has nothing to belong to, and is refused on the feed.
17. **Garbage collection** (Task 7). `welfare.Rig`'s docstring names this service: a session is a reference cycle (`Session` → `Rig` → `Session.wall_now`) that only the cyclic collector frees. The service collects once when a session closes — between sessions, never during a run — and the docstring says so. Managing the collector during runs (CLAUDE.md's hot-path rule) remains open for every session kind, and is filed (Task 10 Step 7).
18. **Commands** (Tasks 7, 8): read once per housekeeping pass (`HOUSEKEEPING_S`, 1 s, a display cadence) while no run is in progress, returning early when one arrives, and at each trial boundary during a run through `_Routed`: an `EndSession` during a run stops it — a `Stop` in its place — and is finished once the run has returned; any other service command during a run is refused. `_Routed` hands the run the real link's `mark_signal`, so the per-frame check is the same call V12 measured.
19. **Names are single folder names** (Task 7): a session id, an animal and a task are each letters, digits, `_`, `.` and `-`, starting with a letter or digit, because each becomes a path under `--root`, `--subjects` or `--tasks` and they arrive over the wire (Review Focus 1).
20. **The welfare-critical surface after this plan** (`docs/design/architecture.md`, updated in the task that adds each): `marks.py` whole and `stranded.py` whole (new); `Welfare.restore_departure`, and the docstrings of `Rig` and `_refuse_unconfirmed`, in `welfare.py`; in `cli.py`, `_settle_departure`, `_settle_return` and `main`'s `_marks.depart(session, departure)` line (the four functions and one line listed before this plan: two moved to `marks.py` unchanged, two rewritten around it, the line replaced); `preflight.out_of_cage` and `preflight.gate`; `Service._open`, `Service._end`, `Service._close_stranded` and `Service._start`. Untouched and checked in Task 10 Step 4: `bounds.py`, the listed `taskd` functions (`_ends`, `_hold`, `_manual_reward`, `set`, `_schedule`) and `_command`'s two parts, and `link._setting`.

## Global Constraints

- US English in code, docs and comments.
- **"fail blocks, unknown proceeds on a named acknowledgement written into the record, pass proceeds"** (spec §6.2, S9a §10).
- **"A departure more than `welfare.CONFIRM_MARK_WITHIN` ago is answered *confirm or amend*"**, and for the return **"there is no amendment for a return"**; the page's route uses **"the terminal's own parser"** (spec §6.2).
- **"an id already used under `--root` is refused"**; **"while one exists it refuses to open a new session, for that animal or any other"** (spec §6.1, §6.2).
- **`RUN_START` and `RUN_END`, "provisionally 4135 and 4136"; "wl-xtasks owns the final numbering"** (spec §6.3).
- **"Telemetry, schema 10: `phase` gains `idle` and `between_runs`; each frame carries the run index (`None` when no run has started) ... Unknown stays `None`, never `0`"** (spec §6.3). A frame of another schema is refused by name (`SchemaMismatch`).
- **"Every run is unplanned until b3b"**: every start row says `unplanned: true`.
- **`--link PUB,REP[,MARK]`, "loopback unless `--link-allow-remote`"** (spec §6.1).
- Hot path: nothing new per frame. Commands are drained at a trial boundary during a run and once per housekeeping pass otherwise; the per-frame mark check is the real link's own call.
- No timing claim without a measurement (CLAUDE.md). This plan makes none: `HOUSEKEEPING_S` is a display cadence, and the trial pacing in the end-to-end tests is housekeeping for the simulator.
- Sim first: every behavior has a simulator-backed test; the end-to-end tests drive the service over a real `ZmqLink` with the simulated animal, card and pump.
- Welfare-critical code changes only as Plan decision 20 lists, and go to the PI (Task 10).
- `python3 tools/mutate.py` over every new and changed function before the branch merges, each line read as a real `N failed` (CLAUDE.md, "Prove a test can fail"; Task 10 Step 3).

## Review Focus

The five inputs most likely to bite an operator that no task's tests would otherwise exercise, each pinned by a test in its owning task:

1. **A session id or animal that is not one folder name** — `../2027-01-14_01`, `a/b`, `../REFERENCE` — arriving from a page. Expected: refused with a sentence, nothing written anywhere. Test: Task 7, `test_a_session_id_or_animal_that_is_not_one_folder_name_is_refused_and_nothing_is_written`.
2. **End session pressed after the animal is home, with its real, earlier return time.** Expected: the head's release is recorded at the End (Plan decision 6), so `welfare` refuses the earlier return with its sentence, the session keeps waiting for the return, and `now` closes it. Test: Task 7, `test_a_return_typed_before_the_session_was_ended_is_refused_and_now_closes_it`.
3. **Two opens in one pass** — two pages, or a double click. Expected: one session opens; the second is refused naming the first; one folder. Test: Task 7, `test_two_opens_in_one_pass_open_one_session_and_refuse_the_other`.
4. **A second start** — a double click, or a start sent while a run is in progress. Expected: one run; the second refused, never queued behind the first. Tests: Task 8, `test_two_starts_in_one_pass_start_one_run` and `test_during_a_run_the_services_own_commands_are_refused_not_queued`.
5. **A crash that tore the last line of a session's `welfare_notes.jsonl`.** Expected: the session is stranded, never silently skipped; its return is refused with a sentence saying the file must be repaired; no session opens meanwhile. Test: Task 7, `test_a_crashed_sessions_torn_last_line_leaves_it_stranded_never_skipped`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `wl_xcon/marks.py` | create | **welfare-critical**: the parser (moved from `cli`), the departure and return decisions, the page's route |
| `wl_xcon/cli.py` | modify | `_settle_departure`/`_settle_return` on `marks`; `main`'s departure lines; `wlx taskd`'s parser and branch; `render` for schema 10 and `Idle`; `wlx console`'s watch |
| `wl_xcon/record.py` | modify | the session-long record: `configure`, `run_row`, `runs.jsonl`, a trial's `run`, a close per run |
| `wl_xcon/taskd.py` | modify | `RunSpec`, `run(run)`, per-run state, the record's runs, `RUN_START`/`RUN_END`; `service` mode, `end_runs`, `close`, `stamp`, `refuse`, `receive`, `publish` |
| `tasks/allocation.py` | modify | `RUN_START` 4135, `RUN_END` 4136 |
| `wl_xcon/link.py` | modify | schema 10: `Telemetry`'s new fields, `Idle`, `Preflight`, `PreflightItem`, `Question`, `Stranded`; `OpenSession`, `CheckRun`, `StartRun`, `EndSession` on the wire |
| `wl_xcon/web.py`, `wl_xcon/health.py`, `wl_xcon/serve.py` | modify | idle and between-runs frames rendered honestly; `Hub` takes an `Idle` |
| `wl_xcon/preflight.py` | create | the items and S9a §10's gate; **welfare-critical**: `out_of_cage`, `gate` |
| `wl_xcon/stranded.py` | create | **welfare-critical**: finding a stranded session and taking its return |
| `wl_xcon/welfare.py` | modify | **welfare-critical**: `Welfare.restore_departure`; `Rig`'s docstring |
| `wl_xcon/service.py` | create | `wlx taskd`: the loop, sessions, runs, `_Routed`; **welfare-critical**: `_open`, `_end`, `_close_stranded`, `_start` |
| `tools/mutation_gate.py` | modify | `RETURNS` gains `marks`, `preflight`, `stranded`, `service` |
| `tests/_sessions.py` | create | a real `Session` on the simulators, for `marks`, `preflight` and `stranded` |
| `tests/test_marks.py`, `tests/test_preflight.py`, `tests/test_stranded.py`, `tests/test_service.py` | create | their modules; `test_service.py` holds the end-to-end tests |
| `tests/test_cli.py`, `test_record.py`, `test_taskd.py`, `test_link.py`, `test_web.py`, `test_health.py`, `test_serve.py`, `test_welfare.py`, `tests/_frames.py` | modify | as each task says |
| `docs/design/architecture.md` | modify | the welfare-critical list (Tasks 1, 6, 7, 8); the `taskd` row (Task 7) |
| `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` | modify | §6.6: what this plan decided that §6 left open (Task 10) |

---

### Task 1: One departure and one return, for the terminal and the page (`marks.py`)

**Welfare-critical.** Moves the terminal's decision into one module both callers use; the terminal keeps only its prompting. `wlx run`'s behavior and every existing test in `tests/test_cli.py` stay as they are.

**Files:**
- Create: `wl_xcon/marks.py`, `tests/_sessions.py`, `tests/test_marks.py`
- Modify: `wl_xcon/cli.py` (`_TIME_FORMATS`, `_wall_clock_time`, `_clock_or_now` moved; `_settle_departure`, `_settle_return`, `main`'s departure lines; imports), `tools/mutation_gate.py` (`RETURNS`), `docs/design/architecture.md` (the welfare-critical list)

**Interfaces:**
- Produces, in `wl_xcon.marks`: `TIME_FORMATS: str`; `clock_time(text: str) -> float` and `clock_or_now(text: str, now: Callable[[], float]) -> float` (raising `argparse.ArgumentTypeError`); `Confirm(by: str, how: str)`; `Amend(at: float, reason: str, by: str, how: str)`; `Departure(at: float, by: str, how: str, note: dict | None)` with property `confirmed: bool`; `Owed(mark: str, at: float, warning: str)` (an `Exception`) with `.mark`, `.at`, `.warning`, `.answers: tuple[str, ...]`; `decide_departure(session, at, answer: Confirm | Amend | None, *, by: str, how: str) -> Departure`; `depart(session, decision) -> None`; `record_departure(session, decision) -> None`; `take_return(target, at: float, *, confirmed: bool, by: str, how: str) -> None`; `page_departure(session, *, departure: str, answer: str | None, amend_to: str | None, amend_reason: str, by: str) -> Departure`; `page_return(target, *, returned: str, confirm: bool, by: str, how: str = "the page") -> None`.
- Produces, in `tests/_sessions.py`: `WALL: float`; `bounds(subject: str = "A", out_of_cage: float = 43_200.0) -> Bounds`; `session(tmp_path, *, deployment=Deployment.RIG_CHAIRED, out_of_cage=43_200.0) -> Session` (wall fixed at `WALL`); `typed(seconds_before: float) -> str`.
- `cli._wall_clock_time`, `cli._clock_or_now` and `cli._TIME_FORMATS` stay importable, as the same objects.

- [ ] **Step 1: Write the helper and the failing tests**

`tests/_sessions.py`:

```python
"""A real `taskd.Session` on the simulators, for the tests of the code that works around
one -- `marks`, `preflight`, `stranded` -- without running a trial. Never collected: its
name does not start with `test_`."""

from __future__ import annotations

import time
from datetime import datetime

from _rig import DIRECT
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.dio import Simulated as Card
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall these sessions read: this host's clock when the module loaded, so a time
#: typed from it (`typed`) names the same instant on this host's calendar.
WALL = time.time()


def bounds(subject: str = "A", out_of_cage: float = 43_200.0) -> Bounds:
    """A bounded config: a reward entry, the out-of-cage ceiling, the daily floor."""
    return Bounds(
        subject=subject,
        ceilings={
            "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
            "out_of_cage": Ceiling(value=out_of_cage, maximum=100_000.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )


def session(
    tmp_path, *, deployment: Deployment = Deployment.RIG_CHAIRED, out_of_cage: float = 43_200.0
) -> Session:
    """Built and not opened: nothing is on disk until a mark or `open()` writes it.
    Rig-chaired by default, so no head-fixation stands between a test and a return."""
    made = Session(
        SessionSpec(
            task="tasks/fixation_detection.py",
            allocation="tasks/allocation.py",
            root=tmp_path,
            session_id="2027-01-14_01",
            subject="A",
            trials=3,
            frame_period=1 / 240,
            seed=1,
            values={},
            bounds=bounds(out_of_cage=out_of_cage),
            already_delivered_today=0.0,
            deployment=deployment,
            geometry=DIRECT,
        ),
        card=Card(),
        pump=Pump(),
    )
    made.wall_clock = lambda: WALL
    return made


def typed(seconds_before: float) -> str:
    """A time as a person types it, with its date and zone: `seconds_before` `WALL`
    (negative is after it)."""
    return datetime.fromtimestamp(WALL - seconds_before).astimezone().isoformat(
        timespec="seconds"
    )
```

`tests/test_marks.py`:

```python
"""`marks` -- the departure and the return, decided once for `wlx run`'s terminal and
`wlx taskd`'s page (P4d-2b spec §6.2: "One shared piece of code decides"). Every rule
is `welfare`'s; these pin the decision made around it, which both callers now share."""

from __future__ import annotations

import argparse
import json

import pytest

from _sessions import WALL, session, typed
from wl_xcon import cli, marks
from wl_xcon.bounds import Exceeded
from wl_xcon.welfare import CONFIRM_MARK_WITHIN

FAR = CONFIRM_MARK_WITHIN + 600


def _rows(made) -> list[dict]:
    path = made.directory / "welfare_notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _kinds(made) -> list[str]:
    return [row["kind"] for row in _rows(made)]


def _departed(tmp_path):
    """A session whose departure, three hours ago, a person confirmed."""
    made = session(tmp_path)
    marks.depart(
        made,
        marks.decide_departure(
            made, WALL - 3 * 3600, marks.Confirm(by="jake", how="t"), by="jake", how="t"
        ),
    )
    return made


def test_the_terminal_and_the_page_read_a_time_with_one_parser():
    """Spec §6.2: "the service parses it with the terminal's own parser"."""
    assert cli._wall_clock_time is marks.clock_time
    assert cli._clock_or_now is marks.clock_or_now
    assert cli._TIME_FORMATS == marks.TIME_FORMATS


def test_a_near_departure_is_taken_as_given_and_writes_no_confirmation(tmp_path):
    made = session(tmp_path)

    decision = marks.decide_departure(made, WALL - 60, None, by="jake", how="--out-of-cage-at")
    marks.depart(made, decision)
    marks.record_departure(made, decision)

    assert (decision.at, decision.confirmed, decision.note) == (WALL - 60, False, None)
    assert (decision.by, decision.how) == ("jake", "--out-of-cage-at")
    assert made.welfare.left_cage_wall_at == WALL - 60
    assert _kinds(made) == ["departure"]


def test_a_far_departure_with_no_answer_is_owed_and_nothing_is_marked(tmp_path):
    made = session(tmp_path)

    with pytest.raises(marks.Owed) as owed:
        marks.decide_departure(made, WALL - FAR, None, by="jake", how="typed on the page")

    assert (owed.value.mark, owed.value.at) == ("departure", WALL - FAR)
    assert owed.value.answers == ("confirm", "amend")
    assert "Confirm it, or amend it" in owed.value.warning
    assert made.welfare.left_cage_wall_at is None
    assert not made.directory.exists(), "nothing is written for an unanswered mark"


def test_a_far_departure_a_person_confirmed_is_marked_confirmed_with_its_row(tmp_path):
    made = session(tmp_path)

    decision = marks.decide_departure(
        made,
        WALL - FAR,
        marks.Confirm(by="jake", how="confirmed on the page"),
        by="jake",
        how="typed on the page",
    )
    marks.depart(made, decision)
    marks.record_departure(made, decision)

    assert decision.confirmed
    rows = _rows(made)
    assert [row["kind"] for row in rows] == ["departure", "departure confirmed"]
    assert rows[0]["how"] == rows[1]["how"] == "confirmed on the page"


def test_an_amendment_is_its_own_confirmation_and_marks_the_corrected_time(tmp_path):
    made = session(tmp_path)
    typed_at, corrected = WALL - 9 * 3600, WALL - 600

    decision = marks.decide_departure(
        made,
        typed_at,
        marks.Amend(at=corrected, reason="typed 08:45 for 18:45", by="sam", how="amended on the page"),
        by="jake",
        how="typed on the page",
    )
    marks.depart(made, decision)
    marks.record_departure(made, decision)

    assert decision.confirmed and made.welfare.left_cage_wall_at == corrected
    note = _rows(made)[1]
    assert (note["kind"], note["was"], note["now"]) == ("departure amended", typed_at, corrected)
    assert (note["reason"], note["by"]) == ("typed 08:45 for 18:45", "sam")


@pytest.mark.parametrize(("reason", "by", "said"), [("", "sam", "no reason"), ("typo", "", "by nobody")])
def test_an_amendment_without_a_reason_or_a_name_is_refused(tmp_path, reason, by, said):
    made = session(tmp_path)

    with pytest.raises(Exceeded, match=said):
        marks.decide_departure(
            made,
            WALL - 9 * 3600,
            marks.Amend(at=WALL - 600, reason=reason, by=by, how="amended on the page"),
            by="jake",
            how="typed on the page",
        )

    assert made.welfare.left_cage_wall_at is None


def test_an_amendment_meets_every_refusal_the_original_would(tmp_path):
    """An amendment is not an override: into the future is refused at the mark, and
    nothing about the departure is written."""
    made = session(tmp_path)
    decision = marks.decide_departure(
        made,
        WALL - 9 * 3600,
        marks.Amend(at=WALL + 3600, reason="typo", by="sam", how="amended on the page"),
        by="jake",
        how="typed on the page",
    )

    with pytest.raises(Exceeded, match="in the future"):
        marks.depart(made, decision)

    assert not made.directory.exists()


def test_a_departure_past_the_ceiling_is_refused_and_never_asked_about(tmp_path):
    """The band has two edges and only one of them asks (`welfare`'s rule)."""
    made = session(tmp_path, out_of_cage=3600.0)

    decision = marks.decide_departure(made, WALL - 7200, None, by="jake", how="t")

    assert decision.note is None
    with pytest.raises(Exceeded, match="at or outside the limit"):
        marks.depart(made, decision)


def test_a_near_return_is_taken_and_written(tmp_path):
    made = _departed(tmp_path)

    marks.take_return(made, WALL - 60, confirmed=False, by="jake", how="the page")

    assert made.welfare.returned_wall_at == WALL - 60
    assert _kinds(made)[-1] == "returned"


def test_a_far_return_nobody_confirmed_is_owed_confirm_or_retype(tmp_path):
    """No amendment for a return (spec §6.2): the page offers *confirm* or *re-type*."""
    made = _departed(tmp_path)

    with pytest.raises(marks.Owed) as owed:
        marks.take_return(made, WALL - 2 * 3600, confirmed=False, by="jake", how="the page")

    assert (owed.value.mark, owed.value.answers) == ("return", ("confirm", "re-type"))
    assert made.welfare.returned_wall_at is None


def test_a_far_return_a_person_confirmed_is_taken_with_its_row(tmp_path):
    made = _departed(tmp_path)

    marks.take_return(made, WALL - 2 * 3600, confirmed=True, by="jake", how="the page")

    assert _kinds(made)[-2:] == ["returned", "return confirmed"]


@pytest.mark.parametrize(
    ("before_wall", "said"), [(-600, "in the future"), (4 * 3600, "having left it at")]
)
def test_a_return_meets_every_welfare_refusal(tmp_path, before_wall, said):
    made = _departed(tmp_path)

    with pytest.raises(Exceeded, match=said):
        marks.take_return(made, WALL - before_wall, confirmed=True, by="jake", how="the page")


def test_the_pages_departure_is_read_by_the_terminals_parser(tmp_path):
    decision = marks.page_departure(
        session(tmp_path),
        departure=typed(60),
        answer=None,
        amend_to=None,
        amend_reason="",
        by="jake (box, unverified)",
    )

    assert decision.at == pytest.approx(WALL - 60, abs=1.0)
    assert (decision.by, decision.how) == ("jake (box, unverified)", "typed on the page")


def test_the_pages_answers_are_the_terminals(tmp_path):
    confirmed = marks.page_departure(
        session(tmp_path / "a"), departure=typed(3 * 3600), answer="confirm",
        amend_to=None, amend_reason="", by="jake",
    )
    amended = marks.page_departure(
        session(tmp_path / "b"), departure=typed(9 * 3600), answer="amend",
        amend_to=typed(600), amend_reason="typo", by="jake",
    )

    assert (confirmed.confirmed, confirmed.how) == (True, "confirmed on the page")
    assert amended.how == "amended on the page"
    assert amended.at == pytest.approx(WALL - 600, abs=1.0)


@pytest.mark.parametrize("text", ["half past nine", "25:00", ""])
def test_a_page_time_that_is_not_one_is_refused_in_the_terminals_words(tmp_path, text):
    with pytest.raises(argparse.ArgumentTypeError, match="is not a clock time"):
        marks.page_departure(
            session(tmp_path), departure=text, answer=None, amend_to=None,
            amend_reason="", by="jake",
        )


def test_an_amendment_from_the_page_needs_its_corrected_time(tmp_path):
    with pytest.raises(argparse.ArgumentTypeError, match="corrected departure time"):
        marks.page_departure(
            session(tmp_path), departure=typed(9 * 3600), answer="amend",
            amend_to=None, amend_reason="typo", by="jake",
        )


def test_the_pages_return_takes_now_on_the_sessions_clock(tmp_path):
    made = _departed(tmp_path)

    marks.page_return(made, returned="now", confirm=False, by="jake")

    assert made.welfare.returned_wall_at == WALL
    assert _rows(made)[-1]["how"] == "the page"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_marks.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'marks' from 'wl_xcon'`.

- [ ] **Step 3: Create `wl_xcon/marks.py`**

The module docstring, the moved parser, then the new code:

```python
"""The two marks that bound the out-of-cage interval, decided once for every caller.

**Welfare-critical, the whole module** (CLAUDE.md; `docs/design/architecture.md`). Human
review before merge.

The PI ruled on 2026-09-29 that the page takes the departure and the return "under the
terminal's exact rules", through "one shared piece of code" (P4d-2b spec §6.0, §6.2).
This is that code. `welfare` holds the rules -- what is refused, and when a person must
confirm -- and this module holds the decision a caller makes around them, which until
slice b3a lived inside `wlx run`'s prompts (`cli._settle_departure`,
`cli._settle_return`): whether a far mark was confirmed or amended, by whom and how, and
the row that says so. The terminal keeps its prompting and `wlx taskd` its sentences;
neither decides.

- **Parsing**: `clock_time` and `clock_or_now` turn what a person typed into an instant.
  Moved here from `cli` unchanged (they were `_wall_clock_time` and `_clock_or_now`,
  and `cli` still reaches them by those names), so the page's text is read by the
  terminal's own parser.
- **The departure**: `decide_departure` turns an instant and a person's answer -- none,
  `Confirm` or `Amend` -- into a `Departure`, or raises `Owed` for a far one nobody has
  answered; `depart` marks it; `record_departure` writes the confirmation's or the
  amendment's row, after the mark and never before.
- **The return**: `take_return` marks it, or raises `Owed` for a far one nobody
  confirmed. **There is no amendment for a return** (the terminal's rule, P4d-2a spec
  §3): nothing has been marked that one could replace, so a corrected time is simply
  typed again.
- **The page**: `page_departure` and `page_return` take the text and the answer a
  console sent, and go through the same functions.

`session` is a `taskd.Session`. For a return, `target` is anything with `wall_now`,
`return_needs_confirmation` and `returned_to_cage` as `Session` has them -- a
`stranded.Restored` is the other. Untyped for the reason `link.Telemetry.of` gives:
`taskd` imports `cli`, which imports this module.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from wl_xcon.record import welfare_note
```

Then **move, unchanged**, from `wl_xcon/cli.py`: `_TIME_FORMATS` with its `#:` comment (as `TIME_FORMATS`), the whole of `_wall_clock_time` (as `clock_time`), and the whole of `_clock_or_now` (as `clock_or_now`). The only edits: the three names; `_TIME_FORMATS` → `TIME_FORMATS` inside `clock_time`; `_wall_clock_time(text)` → `clock_time(text)` inside `clock_or_now`; and, in the two docstrings, the references to `_wall_clock_time`/`_clock_or_now` renamed to match. Every sentence of both docstrings stays: `tests/test_cli.py`'s `test_the_dst_gap_is_closed_as_a_ruling_and_the_description_is_kept` reads the first one.

Then the new code:

```python
@dataclass(frozen=True)
class Confirm:
    """A person's *confirm* on a far departure: who, when a name was given, and how --
    `--confirm-out-of-cage`, at the terminal, or on the page."""

    by: str
    how: str


@dataclass(frozen=True)
class Amend:
    """A person's *amend*: the corrected instant, why, who (both refused blank by
    `welfare.amend_mark`), and how."""

    at: float
    reason: str
    by: str
    how: str


@dataclass(frozen=True)
class Departure:
    """What the departure is marked with, decided: the instant, who gave it and how (the
    `departure` row's), and the confirmation's or amendment's row, or `None`."""

    at: float
    by: str
    how: str
    note: dict | None

    @property
    def confirmed(self) -> bool:
        """Whether a person acted on it -- confirmed it, or amended it, since an
        amendment is its own confirmation. **What `welfare._refuse_unconfirmed` is told**
        (it was `main`'s `confirmed=note is not None` until b3a), and read from the note
        rather than kept beside it, so the two cannot disagree."""
        return self.note is not None


class Owed(Exception):
    """A far mark nobody has answered for: the sentence a person must be shown, and the
    answers they may give. **Raised, never returned**, so no caller can mark past it."""

    def __init__(self, mark: str, at: float, warning: str) -> None:
        super().__init__(warning)
        self.mark = mark
        self.at = at
        self.warning = warning
        self.answers = ("confirm", "amend") if mark == "departure" else ("confirm", "re-type")


def decide_departure(
    session, at: float, answer: Confirm | Amend | None, *, by: str, how: str
) -> Departure:
    """What a departure typed as `at` is marked with, given a person's answer.

    **PI, 2026-09-20:** *"if a number is input that is more than 30 min from the current
    time, a warning should appear that the experimenter must click through to confirm.
    There should also be an option to update the time if necessary, but a reason should
    be given and the experimenter name logged."*

    - *Amended*: recorded by `welfare.amend_mark` (which refuses a blank reason or name)
      and marked at the corrected instant, which meets every refusal the original
      would. Its own confirmation.
    - *Inside the band* (`departure_needs_confirmation` answers `None`): taken as given,
      `by` and `how` naming where it came from; a *confirm* here changes nothing.
    - *Far, confirmed*: marked as given, with a `departure confirmed` row.
    - *Far, no answer*: `Owed`. The terminal asks, or refuses with no one to ask; the
      page says *confirm or amend*. Nothing is marked or written.

    **Asked before the mark, never after**: `welfare.left_cage` refuses a second mark,
    so an amendment made afterwards would have nowhere to go.
    """
    warning = session.departure_needs_confirmation(at)

    def note(kind: str, now: float, reason: str, who: str, said: str) -> dict:
        return {
            "kind": kind,
            "subject": session.spec.subject,
            "was": at,
            "now": now,
            "reason": reason,
            "by": who,
            "how": said,
            # The session's clock, as `Session._note` stamps every other row, so one
            # file's `recorded_at` column has one base (Ruling 8).
            "recorded_at": session.wall_now(),
        }

    if isinstance(answer, Amend):
        session.amend_mark(
            "departure", original=at, amended=answer.at, reason=answer.reason, by=answer.by
        )
        return Departure(
            answer.at,
            answer.by,
            answer.how,
            note("departure amended", answer.at, answer.reason, answer.by, answer.how),
        )
    if warning is None:
        return Departure(at, by, how, None)
    if isinstance(answer, Confirm):
        return Departure(
            at, answer.by, answer.how, note("departure confirmed", at, "", answer.by, answer.how)
        )
    raise Owed("departure", at, warning)


def depart(session, decision: Departure) -> None:
    """Mark the departure as decided: `session.left_cage`, which writes the `departure`
    row once `welfare` has taken it. **`confirmed=decision.confirmed` is the value
    `welfare._refuse_unconfirmed` trusts**: true exactly when a person acted."""
    session.left_cage(
        at=decision.at, confirmed=decision.confirmed, by=decision.by, how=decision.how
    )


def record_departure(session, decision: Departure) -> None:
    """The confirmation's or amendment's row, **after `depart` has taken the mark and
    never before**: a correction the ceiling or the clock refused leaves no record of a
    change that did not happen. Nothing, for a departure nobody was asked about."""
    if decision.note is not None:
        welfare_note(session.directory, **decision.note)


def take_return(target, at: float, *, confirmed: bool, by: str, how: str) -> None:
    """Mark the return at `at`, or raise `Owed` for a far one nobody confirmed.

    **The confirmation is asked first**, before `welfare`'s other refusals -- the
    terminal's order since P4d-2a, kept so the terminal and the page meet one rule. A
    return typed in the wrong half of the day moves the interval in the direction that
    makes a session look shorter than it was, which is why a far one is a person's to
    confirm (PI, 2026-09-20, ruling 4)."""
    warning = target.return_needs_confirmation(at)
    if warning is not None and not confirmed:
        raise Owed("return", at, warning)
    target.returned_to_cage(at, confirmed=confirmed, by=by, how=how)


def page_departure(
    session,
    *,
    departure: str,
    answer: str | None,
    amend_to: str | None,
    amend_reason: str,
    by: str,
) -> Departure:
    """A departure as a console sent it (P4d-2b spec §6.2): the text as typed, read by
    the terminal's own parser, and the page's answer -- `None`, `"confirm"` or
    `"amend"` with the corrected time and a reason -- given as the terminal's
    `Confirm`/`Amend`, named for the person who sent it. Raises
    `argparse.ArgumentTypeError` for text that is not a time, `Owed` and `Exceeded` as
    `decide_departure` does."""
    at = clock_time(departure)
    choice: Confirm | Amend | None = None
    if answer == "amend":
        if amend_to is None:
            raise argparse.ArgumentTypeError(
                "an amendment gives the corrected departure time, and none was given"
            )
        choice = Amend(
            at=clock_time(amend_to), reason=amend_reason, by=by, how="amended on the page"
        )
    elif answer == "confirm":
        choice = Confirm(by=by, how="confirmed on the page")
    return decide_departure(session, at, choice, by=by, how="typed on the page")


def page_return(
    target, *, returned: str, confirm: bool, by: str, how: str = "the page"
) -> None:
    """A return as a console sent it: the text as typed, or `now` on the session's own
    clock, read by the terminal's parser, then `take_return`."""
    take_return(
        target, clock_or_now(returned, target.wall_now), confirmed=confirm, by=by, how=how
    )
```

- [ ] **Step 4: Prove the move is only a move**

```bash
python3 - <<'EOF'
import ast, subprocess
old = ast.parse(subprocess.run(["git", "show", "main:wl_xcon/cli.py"], capture_output=True, text=True, check=True).stdout)
new = ast.parse(open("wl_xcon/marks.py").read())
def shape(tree, name):
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body
    text = ast.dump(ast.Module(body=body, type_ignores=[])) + ast.dump(fn.args) + ast.dump(fn.returns)
    return text.replace("_TIME_FORMATS", "TIME_FORMATS").replace("_wall_clock_time", "clock_time")
for was, now in (("_wall_clock_time", "clock_time"), ("_clock_or_now", "clock_or_now")):
    assert shape(old, was) == shape(new, now), was
    print(f"{was} -> {now}: the same code")
EOF
```
Expected: two lines, `... the same code`.

- [ ] **Step 5: Put the terminal on `marks`**

In `wl_xcon/cli.py`:

1. Delete `_TIME_FORMATS`, `_wall_clock_time` and `_clock_or_now` (now in `marks`), and import them under their old names, beside the other `wl_xcon` imports:

```python
from wl_xcon import marks as _marks
from wl_xcon.marks import TIME_FORMATS as _TIME_FORMATS
from wl_xcon.marks import clock_or_now as _clock_or_now
from wl_xcon.marks import clock_time as _wall_clock_time
```

Delete `from datetime import datetime` (its one use moved) and `from wl_xcon import record as _record` (its one use goes in item 4).

2. Replace `_settle_departure` with:

```python
def _settle_departure(session, args) -> _marks.Departure:
    """Get a person's act on a far-off departure time, before it is marked.

    **Welfare-critical, outside the welfare modules** (`docs/design/architecture.md`):
    the terminal's route into `marks.decide_departure`, which decides -- the same
    function `wlx taskd`'s page goes through (P4d-2b spec §6.2). What stays here is the
    terminal's part: which answer the person gave, and the name and reason an
    amendment carries.

    **PI, 2026-09-20:** *"if a number is input that is more than 30 min from the current
    time, a warning should appear that the experimenter must click through to confirm.
    There should also be an option to update the time if necessary, but a reason should
    be given and the experimenter name logged."*

    - *Amended*: `--amend-out-of-cage-to TIME` with `--amend-reason` and `--as`, asked
      of `marks` before anything else, as it always was.
    - *Inside the band*: `marks` asks nothing; the ordinary session.
    - *Far*: `--confirm-out-of-cage` confirms it, saying whether a terminal was there;
      with no terminal and no flag **it refuses** -- a confirmation nobody made is
      worse than none; at a terminal it asks, and **anything that is not a
      confirmation stops the session**, end-of-input included.

    **A confirmation's `by` is `--as` if it was given and empty otherwise**: the PI asked
    for a name on the amendment, and an interactive `c` has none to record honestly.
    """
    at = args.out_of_cage_at
    given = {"by": args.actor, "how": "--out-of-cage-at"}
    if args.amend_out_of_cage_to is not None:
        return _marks.decide_departure(
            session,
            at,
            _marks.Amend(
                at=args.amend_out_of_cage_to,
                reason=args.amend_reason,
                by=args.actor,
                how="--amend-out-of-cage-to",
            ),
            **given,
        )
    try:
        return _marks.decide_departure(session, at, None, **given)
    except _marks.Owed as owed:
        warning = owed.warning

    if args.confirm_out_of_cage:
        print(f"  WARNING: {warning}", file=sys.stderr)
        how = (
            "--confirm-out-of-cage"
            if _at_a_terminal()
            else "--confirm-out-of-cage, with no terminal attached"
        )
        return _marks.decide_departure(
            session, at, _marks.Confirm(by=args.actor, how=how), **given
        )

    if not _at_a_terminal():
        raise SystemExit(
            f"refused: {warning}\n"
            f"  There is no terminal attached, so there is nobody to confirm it and "
            f"a confirmation nobody made is worse than none. Pass "
            f"--confirm-out-of-cage to confirm it explicitly, or "
            f"--amend-out-of-cage-to TIME --amend-reason WHY --as WHO to correct it."
        )

    print(f"  WARNING: {warning}", file=sys.stderr)
    # **Exact words, not a prefix.** This matched `a`-anything as *amend*, so `abort`
    # typed at a prompt that ends "anything else to stop" walked into the amendment
    # flow and was then parsed as a clock time.
    answer = _ask(
        "  type `confirm` to accept this departure time, `amend` to correct it, "
        "or anything else to stop: "
    ).strip().lower()

    if answer in ("a", "amend"):
        amended = _ask(f"  the corrected departure time ({_TIME_FORMATS}): ").strip()
        try:
            amended_at = _wall_clock_time(amended)
        except argparse.ArgumentTypeError as bad:
            raise SystemExit(f"refused: {bad}") from bad
        reason = _ask("  why is it being changed? ")
        by = _ask("  your name, for the record: ")
        return _marks.decide_departure(
            session,
            at,
            _marks.Amend(at=amended_at, reason=reason, by=by, how="amended at the terminal"),
            **given,
        )

    if answer in ("c", "confirm"):
        return _marks.decide_departure(
            session,
            at,
            _marks.Confirm(by=args.actor, how="confirmed at the terminal"),
            **given,
        )

    raise SystemExit(
        "refused: the departure time was not confirmed, so the session did not "
        "start. Nothing about the departure has been recorded, and nothing was "
        "delivered."
    )
```

3. In `_settle_return`, replace everything from `warning = session.return_needs_confirmation(at)` to the `except Exceeded` block's `continue` (the lines that ask for confirmation and call `session.returned_to_cage`) with:

```python
        # The decision is `marks.take_return`'s, the page's too (P4d-2b spec §6.2);
        # this prompt is the terminal's one part of it: showing a far return and
        # taking a person's `confirm`.
        try:
            _marks.take_return(session, at, confirmed=False, by=actor, how="terminal")
        except _marks.Owed as owed:
            print(f"  WARNING: {owed.warning}", file=sys.stderr)
            answer = _ask(
                "  type `confirm` to accept this return time, or anything else to "
                "give it again: "
            ).strip().lower()
            if answer not in ("c", "confirm"):
                continue
            try:
                _marks.take_return(session, at, confirmed=True, by=actor, how="terminal")
            except Exceeded as refused:
                print(f"  refused: {refused}", file=sys.stderr)
                continue
        except Exceeded as refused:
            print(f"  refused: {refused}", file=sys.stderr)
            continue
```

and in its docstring replace the paragraph beginning "**The terminal is the only caller of `Session.returned_to_cage` left**" with: "**The rules are `marks.take_return`'s**, which `wlx taskd`'s page goes through too (P4d-2b spec §6.2): this function holds only the prompting -- the clock above each attempt, the time typed, and a person's `confirm` on a far one."

4. In `main`'s `run` branch: in the first `try`, replace

```python
                    departure, note = _settle_departure(session, args)
```
through the `session.left_cage(...)` call (the `by, how = ...` lines and their comments included) with:

```python
                    departure = _settle_departure(session, args)
                    # **Welfare-critical, this one line** (`docs/design/architecture.md`):
                    # the departure marked as `marks` decided it, `confirmed=` included,
                    # which `welfare._refuse_unconfirmed` trusts. It was
                    # `session.left_cage(at=departure, confirmed=note is not None, ...)`
                    # until b3a, and the decision it carried is `marks`' now.
                    _marks.depart(session, departure)
```

In the second `try`, replace

```python
                            if note is not None:
                                _record.welfare_note(session.directory, **note)
```
with `_marks.record_departure(session, departure)`, keeping the comment above it. In the `out of cage:` print, `departure` becomes `departure.at` in both `time.localtime(departure)` calls.

- [ ] **Step 6: The mutation gate and the architecture**

In `tools/mutation_gate.py`'s `RETURNS`, add `"marks": "None",` after `"cli": "None",`.

In `docs/design/architecture.md`, replace the paragraph from "**In code, that is `wl_xcon/bounds.py` and `wl_xcon/welfare.py`, and four functions in `wl_xcon/cli.py`, plus one line inside a fifth" through "...a change elsewhere is not." with:

> **In code, that is `wl_xcon/bounds.py`, `wl_xcon/welfare.py` and `wl_xcon/marks.py`, two functions in `wl_xcon/cli.py` plus one line inside a third — and, since P4d-2b b2a, five functions in `wl_xcon/taskd.py` plus two parts of a sixth (`Session._command`'s `held` pass-through and one `except` line), and one function in `wl_xcon/link.py`.** The modules are kept small deliberately: everything in them can hurt an animal if it is wrong, and a small file is one a person can actually read before signing it off. **`marks.py` is the out-of-cage interval's two marks, decided once for the terminal and the page** (P4d-2b b3a, 2026-09-29; the PI: "The page takes both times", under the terminal's exact rules through one shared piece of code): the parser that turns a typed clock time into an instant (`clock_time`, `clock_or_now`, which were `cli._wall_clock_time` and `cli._clock_or_now` and moved unchanged), whether a far mark was confirmed or amended, by whom and how, and the row that says so. `welfare` refuses what is impossible, but a wrong instant that is merely plausible passes every refusal, so the parsing and the confirmation are part of the limit. **The two `cli` functions are `_settle_departure` and `_settle_return`**, the terminal's prompting around `marks` — which answer a person gave, and the name and reason an amendment carries — and **the line is `main`'s `_marks.depart(session, departure)`**, which marks the departure as `marks` decided it, `confirmed=` included, which `welfare._refuse_unconfirmed` trusts its caller on. A change to any of these, or to the `taskd` and `link` functions and the two parts of `Session._command` below, is a change requiring review; a change elsewhere is not.

In the same file's P4d-2a-era sentence "They stay in `cli.py`, which is where the terminal is, until the wl-works ELN records both ends of the interval", if it remains anywhere, replace it with "`marks.py` is where both the terminal and the page reach them, until the wl-works ELN records both ends of the interval (P4d-2a spec §10)."

- [ ] **Step 7: Run the new tests and every terminal test**

Run: `python3 -m pytest tests/test_marks.py tests/test_cli.py tests/test_mutation_gate.py -q -p no:cacheprovider`
Expected: PASS — `test_cli.py` unchanged and green is the proof that `wlx run`'s behavior did not move.

- [ ] **Step 8: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add wl_xcon/marks.py wl_xcon/cli.py tests/_sessions.py tests/test_marks.py tools/mutation_gate.py docs/design/architecture.md
git commit -m "Decide the departure and the return in one module the terminal and the page share"
```

Body: the PI's ruling (P4d-2b spec §6.0), the move proved by AST (Step 4), and that `test_cli.py` is unchanged.

---

### Task 2: Runs in the record and in `taskd` (`RunSpec`, `runs.jsonl`, `RUN_START`/`RUN_END`)

**Files:**
- Modify: `wl_xcon/record.py` (`SessionRecord`, new `RUNS`), `wl_xcon/taskd.py` (`RunSpec`; `SessionSpec.values`' docstring; `Session`'s new fields, `task`, `open`, `end`, `_fixed_config`, `_params`, `_plan`, `_agent`, `_control`, `_apply_staged`, `run`; `_load` removed), `tasks/allocation.py`
- Test: `tests/test_record.py`, `tests/test_taskd.py`

**Interfaces:**
- Produces, in `wl_xcon.record`: `RUNS = "runs.jsonl"`; `SessionRecord.open(root, session_id, subject)` (creates the folder, opens no file); `SessionRecord.trial(index, outcome, params, block="", condition="", *, run: int)`; `SessionRecord.configure(fixed: dict)`; `SessionRecord.run_row(event: str, run: int, at: float, **fields)`; `SessionRecord.parameter_change(sequence, name, was, now, by, run: int | None = None)`; `SessionRecord.close()` (per run, idempotent). `SessionRecord.snapshot` is removed.
- Produces, in `wl_xcon.taskd`: `RunSpec(task: str, trials: int, seed: int, values: dict, blocks: list[Block] | None = None)` with `RunSpec.of(spec: SessionSpec) -> RunSpec`; `Session.run(run: RunSpec | None = None, *, preflight_rows: list | None = None, by: str = "") -> Census`; `Session.run_index: int | None`; `Session.task -> str | None` (property).
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

In `tests/test_record.py`: add `run=0` to every `record.trial(...)` call; replace `test_the_config_snapshot_records_the_whole_precedence_chain` with the `configure` test below; and add:

```python
from wl_xcon.record import RUNS, REFUSAL_LOG_LIMIT, SessionRecord


def test_the_config_is_written_as_given(tmp_path):
    """P4d-2b spec §6.3: `config.json` holds what is fixed for the whole session; what
    varies by run is in `runs.jsonl`. The record writes what it is given."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.configure({"subject": "A", "setup": {"view": "direct"}})

    written = json.loads((tmp_path / "2027-01-14_01" / "xcon" / "config.json").read_text())

    assert written == {"subject": "A", "setup": {"view": "direct"}}


def test_a_session_record_opens_no_file_until_something_is_written(tmp_path):
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")

    assert record.directory.is_dir()
    assert list(record.directory.iterdir()) == []


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


def test_a_run_row_carries_its_event_its_run_and_its_local_time(tmp_path):
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.run_row("start", 0, 1_700_000_000.0, task="t.py", unplanned=True)
    record.run_row("end", 0, 1_700_000_060.0, stop_kind="completed")

    rows = [json.loads(line) for line in (record.directory / RUNS).read_text().splitlines()]

    assert [(row["event"], row["run"], row["at"]) for row in rows] == [
        ("start", 0, 1_700_000_000.0),
        ("end", 0, 1_700_000_060.0),
    ]
    assert rows[0]["task"] == "t.py" and rows[0]["unplanned"] is True
    assert "local" in rows[0]["at_local"]


def test_the_refusal_cap_is_the_sessions_and_each_run_says_what_it_dropped(tmp_path):
    """`REFUSAL_LOG_LIMIT` is how many rows a session writes, across its runs; a run
    that dropped rows says so at its close, and a run that dropped none adds nothing."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    for i in range(REFUSAL_LOG_LIMIT):
        record.refusal("reward_correct", 1.0 + i, "jake", "over", i, float(i))
    record.close()
    for i in range(3):
        record.refusal("reward_correct", 2.0, "jake", "over", i, float(i))
    record.close()
    record.close()

    rows = [
        json.loads(line)
        for line in (record.directory / "refusals.jsonl").read_text().splitlines()
    ]
    notices = [row for row in rows if row.get("truncated")]
    assert len(rows) == REFUSAL_LOG_LIMIT + 1
    assert [(n["kept"], n["dropped"]) for n in notices] == [(REFUSAL_LOG_LIMIT, 3)]
```

In `tests/test_taskd.py`: import `textwrap`, `RunSpec`; add beside `_parameter_changes`:

```python
RUN_START, RUN_END = 4135, 4136


def _runs(session: Session) -> list[dict]:
    return [
        json.loads(line)
        for line in (session.directory / "runs.jsonl").read_text().splitlines()
    ]


def _trial_rows(session: Session) -> list[dict]:
    return [
        json.loads(line)
        for line in (session.directory / "trials.jsonl").read_text().splitlines()
    ]


def _run_spec(trials: int = 3, seed: int = 2, **values) -> RunSpec:
    return RunSpec(
        task="tasks/fixation_detection.py",
        trials=trials,
        seed=seed,
        values={**VALUES, **values},
    )
```

In `test_a_session_writes_its_record_and_its_config`, the task and the resolved values move from `config.json` to the run's start row (spec §6.3: "What varies by run moves to `runs.jsonl`"). Replace its four assertions with:

```python
    runs = [json.loads(line) for line in (directory / "runs.jsonl").read_text().splitlines()]

    assert len(trials) == 20
    assert json.loads(trials[0])["subject"] == "A"
    assert runs[0]["resolved"]["fix_hold"] == 0.3
    assert runs[0]["versions"]["task"].endswith("fixation_detection.py")
    assert "resolved" not in config, "what varies by run is in runs.jsonl (spec §6.3)"
```

and add these tests:

```python
def test_the_run_a_session_spec_describes_is_run_0_in_every_file_it_writes(tmp_path):
    """Spec §6.3: a row per run -- as a start and an end (Plan decision 4) -- and every
    trial row names its run. `wlx run`'s one run is run 0, with no pre-flight taken."""
    session = _session(_spec(tmp_path, trials=5))
    session.set("fix_hold", 0.5, by="console")

    session.run()

    start, end = _runs(session)
    assert (start["event"], start["run"], end["event"], end["run"]) == ("start", 0, "end", 0)
    assert start["task"] == "tasks/fixation_detection.py"
    assert start["versions"] == {
        "task": "tasks/fixation_detection.py",
        "allocation": "tasks/allocation.py",
    }
    assert start["resolved"]["fix_hold"] == 0.3, "what it started with, before the staged 0.5"
    assert start["layers"] == {"run": start["resolved"]}
    assert start["bounded"] == {"reward_correct": 0.15}
    assert (start["unplanned"], start["preflight"], start["trials"], start["seed"]) == (
        True, None, 5, 1,
    )
    assert (end["stop_kind"], end["trials"], end["strobed"]) == ("completed", 5, True)
    assert {row["run"] for row in _trial_rows(session)} == {0}
    assert _parameter_changes(session)[0]["run"] == 0
    assert session.run_index == 0


def test_a_run_is_strobed_where_it_starts_and_where_it_ends(tmp_path):
    session = _session(_spec(tmp_path, trials=3))

    session.run()

    codes = session.card.codes
    assert codes[:2] == [4128, RUN_START], "after HEAD_FIXED, before the first trial"
    assert codes[-2:] == [RUN_END, 4129], "after the last trial, before HEAD_RELEASED"
    assert codes.count(RUN_START) == codes.count(RUN_END) == 1


def test_a_run_that_faults_writes_its_end_row_and_strobes_no_run_end(tmp_path, monkeypatch):
    """Plan decision 5: `RUN_END` marks a run that ended by design. A fault's end row is
    still written, from `run()`'s `finally`, and says what happened."""
    from wl_xcon import taskd

    def faults(*args, **kwargs):
        raise RuntimeError("the display went away")

    monkeypatch.setattr(taskd, "run_trial", faults)
    session = _session(_spec(tmp_path, trials=3))

    with pytest.raises(RuntimeError):
        session.run()

    end = _runs(session)[-1]
    assert (end["event"], end["stop_kind"], end["strobed"]) == ("end", "fault", False)
    assert "the display went away" in end["stopped_because"]
    assert RUN_END not in session.card.codes


def test_a_run_whose_allocation_has_no_run_codes_runs_and_says_it_was_not_strobed(tmp_path):
    allocation = tmp_path / "no_run_codes.py"
    allocation.write_text(
        textwrap.dedent(
            f"""
            import dataclasses, importlib.util
            _spec = importlib.util.spec_from_file_location(
                "_reference_allocation", {str(Path("tasks/allocation.py").resolve())!r}
            )
            _module = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_module)
            ALLOCATION = dataclasses.replace(
                _module.ALLOCATION,
                task_events={{
                    code: name
                    for code, name in _module.ALLOCATION.task_events.items()
                    if name not in ("RUN_START", "RUN_END")
                }},
            )
            """
        )
    )
    session = _session(_spec(tmp_path, trials=2, allocation=str(allocation)))

    session.run()

    start, end = _runs(session)
    assert (start["strobed"], end["strobed"], end["stop_kind"]) == (False, False, "completed")


def test_a_second_run_starts_afresh_and_the_session_goes_on(tmp_path):
    """Plan decision 2, the run's half and the session's half. Rig-chaired, so no head
    is released between the two runs of a session that is not a service's."""
    session = _session(_spec(tmp_path, deployment=Deployment.RIG_CHAIRED))
    session.run(_run_spec(trials=4, fix_hold=0.4))
    fluid = session.welfare.commanded
    session.scheduled_stop = ("trials", 99.0, "jake", "after trial 99")

    census = session.run(_run_spec(trials=2))

    assert session.run_index == 1
    assert sum(census.outcomes.values()) + census.hangs == 2, "the second run's own count"
    assert session.stop_kind == "completed" and session.scheduled_stop is None
    assert session.spec.values["fix_hold"] == 0.3, "the second run's own starting values"
    assert session.welfare.commanded >= fluid, "the session's fluid goes on"
    assert len(session.recent_outcomes) == 2
    rows = _trial_rows(session)
    assert [(row["run"], row["index"]) for row in rows] == [
        (0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1),
    ]
    assert [(row["event"], row["run"]) for row in _runs(session)] == [
        ("start", 0), ("end", 0), ("start", 1), ("end", 1),
    ]


def test_an_explicit_run_starts_from_a_copy_of_its_values(tmp_path):
    session = _session(_spec(tmp_path, deployment=Deployment.RIG_CHAIRED))
    run = _run_spec(trials=1)

    session.run(run)

    assert session.spec.values == run.values
    assert session.spec.values is not run.values, "the RunSpec is the caller's, unchanged"


def test_the_config_holds_what_is_fixed_and_is_written_as_the_session_opens(tmp_path):
    """Spec §6.3: the animal, the deployment, the bounded config, the rig, the subject
    settings and the setup -- written by `open()`, before any run."""
    session = _session(
        _spec(tmp_path, bounds_config="subjects/A/bounds.py", rig_config="tests/_rig.py")
    )

    session.open()

    config = json.loads((session.directory / "config.json").read_text())
    assert (config["session_id"], config["subject"], config["deployment"]) == (
        "2027-01-14_01", "A", "rig_fixed",
    )
    assert config["bounds"]["ceilings"]["reward_correct"] == {
        "value": 0.15, "maximum": 0.4, "unit": "mL",
    }
    assert config["bounds"]["minima"]["daily_fluid"] == {"value": 250.0, "unit": "mL"}
    assert config["versions"] == {
        "bounds": "subjects/A/bounds.py",
        "rig": "tests/_rig.py",
        "subject_settings": "",
    }
    assert config["setup"]["view"] == "direct"
    assert not {"layers", "resolved"} & set(config)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_record.py tests/test_taskd.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'RUNS'` and `cannot import name 'RunSpec'`.

- [ ] **Step 3: The record**

In `wl_xcon/record.py`, after `CONTROLS`:

```python
#: One row when each run starts and one when it ends (P4d-2b spec §6.3), joined by
#: `run`: the task, the allocation and their versions, the values and the bounded values
#: it started with, `unplanned`, the pre-flight with who acknowledged each unknown item,
#: and who started it; then when it ended, why, and how many trials it ran.
#:
#: **Two rows, not the spec's one** (the b3a-1 plan, decision 4), so a run's start, and
#: the acknowledgements it started on, are on disk before its first trial: a process
#: that dies mid-run leaves the start row, and the missing end row is the signal, as a
#: missing `returned` row is for the out-of-cage interval.
RUNS = "runs.jsonl"
```

Change `SessionRecord`:

```python
@dataclass
class SessionRecord:
    directory: Path
    subject: str
    #: The trial file, opened by a run's first trial and closed with the run (`close`),
    #: `None` between runs. **The record itself lives for the session** (P4d-2b spec
    #: §6.3): one folder, one `config.json`, and one refusal cap across its runs.
    _trials: TextIO | None = None
    #: Refusal rows written this session, and refusals seen past the cap since the last
    #: notice. `close` turns a non-zero drop count into one notice row -- see `refusal`.
    _refusals_written: int = 0
    _refusals_dropped: int = 0

    @classmethod
    def open(cls, root: Path, session_id: str, subject: str) -> SessionRecord:
        """The session's folder, made now; no file is opened until something is
        written."""
        directory = Path(root) / session_id / XCON_DIRNAME
        directory.mkdir(parents=True, exist_ok=True)
        return cls(directory=directory, subject=subject)
```

In `trial`, change the signature to `def trial(self, index: int, outcome: str, params: dict, block: str = "", condition: str = "", *, run: int) -> None:`, add to its docstring "**And the run it is part of** (P4d-2b spec §6.3: "every trial row names its run"), since a session holds several and each counts its trials from 0.", open the file lazily as its first statement:

```python
        if self._trials is None:
            self._trials = (self.directory / "trials.jsonl").open("a", encoding="utf-8")
```

and add `"run": run,` to the row after `"index": index,`.

Replace `snapshot` with:

```python
    def configure(self, fixed: dict) -> None:
        """What is fixed for the whole session (P4d-2b spec §6.3): the animal, the
        deployment, the bounded config, the rig, the subject settings and the setup,
        written as `taskd.Session.open` gives them. What varies by run -- the task, its
        values, its layers -- is in `runs.jsonl`."""
        (self.directory / "config.json").write_text(
            json.dumps(fixed, indent=2, sort_keys=True), encoding="utf-8"
        )

    def run_row(self, event: str, run: int, at: float, **fields: object) -> None:
        """One row of `RUNS`: `event` `"start"` or `"end"`, the run's index, the instant
        on the session's anchored clock with its local time and zone, and the run's own
        fields, written as given."""
        with (self.directory / RUNS).open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"event": event, "run": run, "at": at, "at_local": _local(at), **fields},
                    sort_keys=True,
                )
                + "\n"
            )
```

In `parameter_change`, add a keyword `run: int | None = None` and `"run": run,` to its row, and say in its docstring that `taskd` always passes the run it happened in.

Replace `close` with:

```python
    def close(self) -> None:
        """The end of a run: the notice for refusals dropped since the last one, then
        the trial file. **Called once per run, and again when the session ends**; a
        close with nothing to write or close does nothing.

        **The notice row carries `truncated`**, which no refusal row does, so the two
        are told apart by shape. `kept` is the session's count so far and `dropped` the
        run's, and the drop count starts again after it, so each notice says what its
        own run lost. A session nobody flooded gets none: evidence of a cap that
        appeared on every session would stop being read.

        A crash hard enough to skip this leaves the kept rows and no notice -- the
        tail-loss this module's docstring accepts everywhere else."""
        if self._refusals_dropped:
            with (self.directory / "refusals.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "truncated": True,
                            "kept": self._refusals_written,
                            "dropped": self._refusals_dropped,
                            "limit": REFUSAL_LOG_LIMIT,
                            "why": (
                                "this session refused more welfare-bounded writes "
                                "than the record keeps; the earliest are kept "
                                "because a flood is a fault and a genuine mistake "
                                "comes first"
                            ),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            self._refusals_dropped = 0
        if self._trials is not None:
            self._trials.close()
            self._trials = None
```

In `REFUSAL_LOG_LIMIT`'s comment, "How many refusal rows one session writes" stays true; add "across all of its runs (b3a)".

- [ ] **Step 4: The allocation**

In `tasks/allocation.py`, after `4134: "MANUAL_REWARD",`:

```python
        # A run's start and end (P4d-2b spec §6.3, 2026-09-29): a session holds several
        # runs, and the recording shows where each task began and ended. `RUN_END` is
        # strobed for a run that ended by design, not after a fault (the b3a-1 plan,
        # decision 5). Provisional, in this range for the reason the four above are;
        # wl-xtasks owns the final numbering.
        4135: "RUN_START",
        4136: "RUN_END",
```

- [ ] **Step 5: `RunSpec`, and the session's runs**

In `wl_xcon/taskd.py`, after `SessionSpec`:

```python
@dataclass
class RunSpec:
    """One run of a session: a task and what it starts with (P4d-2b spec §6.1). A
    session holds several; each is its own task, trial count, seed, starting values and
    plan, while the session's welfare, clocks and record go on across them."""

    task: str
    trials: int
    seed: int
    values: dict
    blocks: list[Block] | None = None

    @classmethod
    def of(cls, spec: SessionSpec) -> RunSpec:
        """The run a `SessionSpec` describes: `wlx run`'s one run. **Its values are the
        spec's own dict**, not a copy, so a change applied during the run is in
        `spec.values` afterwards, as it always was. A spec that names no task -- a
        `wlx taskd` session's -- describes no run, and is refused."""
        if not spec.task:
            raise ValueError(
                "this session's spec names no task, so it describes no run; pass a "
                "RunSpec, as wlx taskd does for each of its runs"
            )
        return cls(
            task=spec.task,
            trials=spec.trials,
            seed=spec.seed,
            values=spec.values,
            blocks=spec.blocks,
        )
```

Add to `SessionSpec`'s `values` a `#:` comment above it: "The values trials run with: for `wlx run`'s one run, its values; for a session of several runs, the run in progress or the last one, **replaced from its `RunSpec` when each starts** (the b3a-1 plan, decision 3) -- the one dict `Session.set` and `_apply_staged` read and write, so neither needs a second place to look."

In `Session`, after `blocks_run`:

```python
    #: Which of the session's runs is in progress, or was last: 0 for the first. `None`
    #: before any has started (P4d-2b spec §6.3), never 0.
    run_index: int | None = field(init=False, default=None)
```

and after `_trial`'s declaration:

```python
    #: The run in progress or the last one, or `None` before any.
    _run: RunSpec | None = field(init=False, default=None, repr=False)
    #: `RUN_START` and `RUN_END`, looked up once as the session is built (P4d-2b spec
    #: §6.3), `None` each where the allocation has none.
    _run_codes: tuple = field(init=False, default=(None, None), repr=False)
```

In `__post_init__`, after `self.allocation = ...`:

```python
        self._run_codes = (self._code("RUN_START"), self._code("RUN_END"))
```

Add the property beside `staged`:

```python
    @property
    def task(self) -> str | None:
        """The task of the run in progress or the last run, or `None` before any (P4d-2b
        spec §6.3). The run a `SessionSpec` describes counts before it starts."""
        if self._run is not None:
            return self._run.task
        return self.spec.task or None
```

At the end of `open()`, after the `session opened` note:

```python
        # The record lives for the session (P4d-2b spec §6.3): its folder and what is
        # fixed for the session, written as it opens.
        self._record = SessionRecord.open(
            self.spec.root, self.spec.session_id, self.spec.subject
        )
        self._record.configure(self._fixed_config())
```

At the end of `end()`, after its note:

```python
        if self._record is not None:
            self._record.close()
            self._record = None
```

Add:

```python
    def _fixed_config(self) -> dict:
        """What `config.json` holds (P4d-2b spec §6.3): what is fixed for the whole
        session. The setup as numbers, as direct-view spec §3 asked -- the distance
        degrees were computed on is what a question months later needs."""
        geometry = self.spec.geometry
        return {
            "session_id": self.spec.session_id,
            "subject": self.spec.subject,
            "deployment": self.spec.deployment.value,
            "bounds": {
                "ceilings": {
                    name: dataclasses.asdict(ceiling)
                    for name, ceiling in self.spec.bounds.ceilings.items()
                },
                "minima": {
                    name: dataclasses.asdict(floor)
                    for name, floor in self.spec.bounds.minima.items()
                },
            },
            "versions": {
                "bounds": self.spec.bounds_config,
                "rig": self.spec.rig_config,
                "subject_settings": self.spec.subject_settings,
            },
            "setup": {
                "view": geometry.view,
                "half_ipd_cm": geometry.half_ipd_cm,
                "viewing_distance_cm": geometry.viewing_distance_cm,
                "half_field_deg": [geometry.half_field_h_deg, geometry.half_field_v_deg],
                "mask_deg": geometry.mask_deg,
                "housings": [dataclasses.asdict(h) for h in geometry.housings],
            },
        }
```

Replace `_params` and delete `_load`:

```python
    def _params(self) -> dict[str, Param]:
        """The declarations of the run's task: the run in progress or the last one, or
        the task a `SessionSpec` names before its run starts. **None before any run of a
        session whose spec names no task** (`wlx taskd`'s), so a setting then is refused
        as undeclared."""
        trial = self._trial
        if trial is None and self.spec.task:
            trial = self._trial = _load_trial(Path(self.spec.task))
        return {} if trial is None else {p.name: p for p in trial.params}
```

`_plan` becomes `_plan(self, run: RunSpec)` reading `run.blocks` and `run.trials`; `_agent` becomes `_agent(self, run: RunSpec)` with `seed=run.seed`. In `_control`, pass the run: `self._record.control(kind, by, at, index, run=self.run_index, **detail)`. In `_apply_staged`, pass it: `self._record.parameter_change(self._sequence, name, was, now, by, run=self.run_index)`.

Replace `run()` from its signature down to the line `signal, stamp = self.link.mark_signal, self._stamp` with:

```python
    def run(
        self,
        run: RunSpec | None = None,
        *,
        preflight_rows: list | None = None,
        by: str = "",
    ) -> Census:
        """One run: open the in-session clock if nothing has, check, require the marks,
        then run, then record.

        **`run` is `None` for the run the `SessionSpec` describes** -- `wlx run`'s one
        run, and every call written before sessions held several -- and a `RunSpec` for
        each of a `wlx taskd` session's (P4d-2b spec §6.1). `preflight_rows` are the
        pre-flight's items as `runs.jsonl` records them, with who acknowledged each
        unknown one (`preflight.rows`), and `by` who started the run; `wlx run` takes no
        pre-flight (the b3a-1 plan, decision 13), and its start row says `null`.

        **In that order, and it is load-bearing.** A malformed task is refused before
        anything else happens, and a session whose welfare marks are missing is refused
        before its first frame, by `welfare.preflight` rather than by a second copy of
        the rule here. **What belongs to a run starts afresh only once both pass**, so a
        refused run leaves the last run's state, and its frames, as they were.
        """
        if self.opened_wall_at is None:
            self.open()
        implied = run is None
        if implied:
            run = RunSpec.of(self.spec)
        trial = _load_trial(Path(run.task))
        findings = check(trial, self.allocation, geometry=self.spec.geometry)
        blocking = [f for f in findings if f.blocking]
        if blocking:
            raise SystemExit(
                "task refused, session not started:\n"
                + "\n".join(f"  {f.code}: {f.detail}" for f in blocking)
            )
        self.welfare.preflight(self.wall_now())

        # **A run of its own** (the b3a-1 plan, decision 2): what belongs to a run
        # starts afresh; the session's welfare, clocks, record, feeds and bounded
        # config go on. A change staged before `run()` is not dropped here: it applies
        # at this run's first boundary, as a live write always has.
        self._trial = trial
        self._run = run
        if not implied:
            self.spec.values = dict(run.values)
        self.run_index = 0 if self.run_index is None else self.run_index + 1
        self.stopped_because, self.stop_kind = "", None
        self.paused_at = None
        self.scheduled_stop = None
        self._recent.clear()

        scheduler = Scheduler(blocks=self._plan(run), seed=run.seed)
        make_world = self.world if self.world is not None else self._agent(run)
        tally = Tally()
        self.blocks_run = [scheduler.block.name]
        record = self._record
        start_code, end_code = self._run_codes
        record.run_row(
            "start",
            self.run_index,
            self.wall_now(),
            task=run.task,
            allocation=self.spec.allocation,
            versions={"task": run.task, "allocation": self.spec.allocation},
            trials=run.trials,
            seed=run.seed,
            blocks=None if not run.blocks else [block.name for block in run.blocks],
            layers={"run": dict(self.spec.values)},
            resolved=dict(self.spec.values),
            # The welfare-bounded values it starts with -- a reward size set in an
            # earlier run of this session carries into this one (Question 1, PI).
            bounded={
                name: ceiling.value
                for name, ceiling in self.spec.bounds.ceilings.items()
                if name != OUT_OF_CAGE
            },
            # Every run is unplanned until the day's plan arrives from wl-works: XC-150.
            unplanned=True,
            preflight=preflight_rows,
            by=by,
            strobed=start_code is not None,
        )
        self._tally = tally
        self._scheduler = scheduler
        self._index = 0
        self.phase = "running"
        self._mark_code = self._code("OPERATOR_MARK")
        #: Whether this run's `RUN_END` went out: only on an ending by design.
        ended_strobed = False
```

Keep the lines from `signal, stamp = ...` through `def each_frame` as they are. Inside the `try:`, make its first statements:

```python
            if start_code is not None:
                self.card.emit(start_code)
```

In the loop, `record.trial(...)` gains `run=self.run_index`, and `self.spec.values` stays the dict the trial's values are built from (Plan decision 3). After the loop, replace the head-release block (keep its comment) with:

```python
            if end_code is not None:
                self.card.emit(end_code)
                ended_strobed = True
            if self.spec.deployment is Deployment.RIG_FIXED:
                self.head_released(self.wall_now())
            return tally.census()
```

Replace the `finally:` block with:

```python
        finally:
            # A trial that faulted or was interrupted has no boundary after it, so the
            # marks its frames stamped -- already strobed -- are written here. **Then
            # the run's end row, from here on every way out**, so a fault is in
            # `runs.jsonl` too; **then the close**, which depends on neither write.
            try:
                if self._stamps:
                    self._settle_stamps(self._index)
            finally:
                try:
                    record.run_row(
                        "end",
                        self.run_index,
                        self.wall_now(),
                        stopped_because=self.stopped_because,
                        stop_kind=self.stop_kind,
                        trials=self._index,
                        blocks_run=list(self.blocks_run),
                        strobed=ended_strobed,
                    )
                finally:
                    record.close()
```

(`OUT_OF_CAGE` is already imported in `taskd.py`.)

- [ ] **Step 6: Run them to verify they pass**

Run: `python3 -m pytest tests/test_record.py tests/test_taskd.py tests/test_cli.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add wl_xcon/record.py wl_xcon/taskd.py tasks/allocation.py tests/test_record.py tests/test_taskd.py
git commit -m "Give a session runs: RunSpec, runs.jsonl, and RUN_START and RUN_END"
```

---

### Task 3: A session between runs (`Session.service`)

**Files:**
- Modify: `wl_xcon/taskd.py` (`Session.service`, `preflight`, `question`, `offered_tasks`; `__post_init__`, `open`, `run`, `duration_warning`, `_settle_stamps`, `_command`'s phase guard, `return_not_recorded`; new `end_runs`, `close`, `stamp`, `refuse`, `receive`, `publish`, `_after_service_run`)
- Test: `tests/test_taskd.py`

**Interfaces:**
- Consumes: Task 2's `RunSpec`, `run(run, *, preflight_rows, by)`, `run_index`.
- Produces: `Session(..., service: bool = False)`; `Session.preflight: object` (a `link.Preflight` or `None`, set by the service), `Session.question: object` (a `link.Question` or `None`), `Session.offered_tasks: tuple[str, ...]`; `Session.end_runs(by: str) -> None`; `Session.close(how: str) -> None`; `Session.stamp(mark: int) -> None`; `Session.refuse(name: str, by: str, why: str) -> None`; `Session.receive(command) -> None`; `Session.publish() -> None`; `Session.return_not_recorded(why: str, how: str = "wlx run")`; phase `"between_runs"`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_taskd.py`:

```python
MARK_CODE_B3A = 4133  # OPERATOR_MARK


def _service_session(tmp_path, link=None, **spec) -> Session:
    """A `wlx taskd` session, opened: its spec names no run, and it waits between runs.
    Its wall follows its frames, as `_session`'s does."""
    made = Session(
        _spec(tmp_path, task="", trials=0, values={}, **spec),
        card=Card(),
        pump=Pump(),
        link=link if link is not None else Simulated(),
        service=True,
    )
    made.wall_clock = lambda: WALL_NOW + made.now()
    made.left_cage(at=WALL_NOW)
    if made.spec.deployment is Deployment.RIG_FIXED:
        made.head_fixed(at=made.wall_now())
    made.open(how="wlx taskd")
    return made


def test_a_service_session_waits_between_runs_and_keeps_the_head_fixed(tmp_path):
    """Plan decisions 1 and 6: a service session sits between runs before its first and
    after each, and its head is released only when the session is ended."""
    session = _service_session(tmp_path)
    assert session.phase == "between_runs" and session.run_index is None

    session.run(_run_spec(trials=2))

    assert (session.phase, session.run_index, session.stop_kind) == ("between_runs", 0, "completed")
    assert session.welfare.fixed_wall_at is not None and session.welfare.released_wall_at is None
    assert 4129 not in session.card.codes
    config = json.loads((session.directory / "config.json").read_text())
    assert config["service"] is True


def test_a_service_session_runs_only_between_runs_and_only_a_run_it_is_given(tmp_path):
    session = _service_session(tmp_path)

    with pytest.raises(ValueError, match="names no task"):
        session.run()
    session.end_runs("jake")
    with pytest.raises(RuntimeError, match="between runs"):
        session.run(_run_spec(trials=1))


def test_a_change_staged_as_a_service_run_ends_is_dropped_and_said(tmp_path):
    """Plan decision 2: nothing between runs applies a staged change, so it is dropped,
    and the feed says so rather than showing it staged for a run that may never come."""
    link = Simulated()
    session = _service_session(tmp_path, link=link)
    link.queue(SetParameter(name="fix_hold", value=0.5, by="jake"))
    link.queue(Stop(by="jake"))

    session.run(_run_spec(trials=5))

    assert session.staged == ()
    assert "fix_hold 0.30 → 0.50 was not applied: run 0 ended first" in [
        control[3] for control in session.controls
    ]


def test_between_runs_a_command_for_a_run_is_refused_and_a_mark_is_stamped_and_noted(tmp_path):
    session = _service_session(tmp_path)

    session.receive(Pause(by="jake"))
    session.stamp(9)
    session.receive(
        Mark(mark=9, note="restless", by="jake", pressed_at=None, received_at=None)
    )

    assert "no run is in progress" in session.refusals[-1][2]
    said = [control[3] for control in session.controls]
    assert said[-2:] == ["mark 1 stamped with no run in progress", 'mark 1: "restless"']
    assert session.card.codes[-1] == MARK_CODE_B3A, "strobed, before any run too"


def test_between_runs_past_the_limit_the_warning_says_the_animal_must_come_back(tmp_path):
    """P4d-2a's rule for a session with no loop left to stop, between runs too: past the
    limit, the warning is `must_stop`'s sentence."""
    wall = [WALL_NOW]
    session = _service_session(tmp_path)
    session.wall_clock = lambda: wall[0]
    wall[0] = WALL_NOW + 900.0  # past `_bounds`' 800 s ceiling

    warning = session.duration_warning(session.wall_now())

    assert warning == session.welfare.must_stop(session.wall_now())
    assert "ceiling" in warning


def test_ending_the_runs_releases_the_head_once_and_waits_for_the_return(tmp_path):
    session = _service_session(tmp_path)

    session.end_runs("jake")

    assert session.phase == "awaiting_return"
    assert session.welfare.released_wall_at is not None
    assert session.card.codes.count(4129) == 1
    assert session.stop_kind == "operator"
    assert session.stopped_because == "session ended by jake, before any run"
    with pytest.raises(RuntimeError):
        session.end_runs("jake")


def test_ending_the_runs_after_a_run_keeps_how_the_run_ended(tmp_path):
    session = _service_session(tmp_path)
    session.run(_run_spec(trials=2))

    session.end_runs("jake")

    assert (session.stop_kind, session.stopped_because) == ("completed", "every block is finished")


def test_closing_needs_the_return_then_ends_the_session_with_one_closed_frame(tmp_path):
    link = Simulated()
    session = _service_session(tmp_path, link=link, deployment=Deployment.RIG_CHAIRED)
    # One run first: until Task 4, a frame needs a run's scheduler to be built from.
    session.run(_run_spec(trials=1))
    session.end_runs("jake")

    with pytest.raises(RuntimeError, match="not home"):
        session.close(how="wlx taskd")
    session.returned_to_cage(session.wall_now(), by="jake", how="the page")
    session.close(how="wlx taskd")

    assert session.phase == "closed" and session.ended_wall_at is not None
    assert link.published[-1].phase == "closed"
    kinds = [
        json.loads(line)["kind"]
        for line in (session.directory / "welfare_notes.jsonl").read_text().splitlines()
    ]
    assert kinds[-2:] == ["returned", "session ended"]
```

(`SetParameter`, `Stop`, `Pause`, `Mark` and `Simulated` are already imported in this file.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_taskd.py -q -p no:cacheprovider -k "service or between_runs or ending_the_runs or closing_needs"`
Expected: FAIL — `TypeError: Session.__init__() got an unexpected keyword argument 'service'`.

- [ ] **Step 3: Implement**

In `Session`, after the `link` field:

```python
    #: Whether this is a `wlx taskd` session, which holds several runs (P4d-2b spec
    #: §6.1; the b3a-1 plan, decision 1): it waits `between_runs` before its first and
    #: after each, keeps its head fixed until `end_runs`, and drops a staged change a
    #: run never applied. `False` -- `wlx run`'s, and every direct caller's -- ends as it
    #: always has: head released at its run's end, then `await_return`.
    service: bool = False
```

After `run_index`:

```python
    #: The pre-flight of the run about to start, as a `link.Preflight`, or `None` (P4d-2b
    #: spec §6.3). Set by `wlx taskd`, which takes it; cleared when a run starts.
    preflight: object = field(init=False, default=None)
    #: A far mark a console owes an answer on, as a `link.Question`, or `None` -- for a
    #: service session, the return's *confirm or re-type* (P4d-2b spec §6.2). Set by
    #: `wlx taskd`; cleared when a run starts.
    question: object = field(init=False, default=None)
    #: The task files `wlx taskd` offers this session's runs, for a console's form.
    offered_tasks: tuple = field(init=False, default=())
```

In `__post_init__`, after `self._run_codes = ...`, move the mark code's lookup here and say why:

```python
        # Looked up once, here, since the allocation never changes: a mark stamped
        # before the first run -- a service session between runs -- is strobed too.
        self._mark_code = self._code("OPERATOR_MARK")
```

and delete `self._mark_code = self._code("OPERATOR_MARK")` from `run()`.

At the end of `open()`:

```python
        if self.service:
            self.phase = "between_runs"
```

In `run()`, directly after `if self.opened_wall_at is None: self.open()`:

```python
        if self.service and self.phase != "between_runs":
            raise RuntimeError(
                f"a service session runs only between runs, and this one is "
                f"{self.phase or 'not open'}: no run starts once the session has ended"
            )
```

after `self._recent.clear()`:

```python
        self.preflight = None
        self.question = None
```

and change the head release after the loop to `if self.spec.deployment is Deployment.RIG_FIXED and not self.service:`, adding to its comment: "A service session's head stays fixed between runs and is released by `end_runs` (the b3a-1 plan, decision 6)." In the `finally`, replace the innermost `record.close()` with:

```python
                    try:
                        record.close()
                    finally:
                        if self.service:
                            self._after_service_run()
```

In `duration_warning`, change `self.phase == "awaiting_return"` to `self.phase in ("awaiting_return", "between_runs")`, and add to its docstring: "**Between runs too** (P4d-2b spec §6.1): no loop is running to stop, so past the limit the warning is `must_stop`'s, and a new run is refused (`preflight.out_of_cage`)."

In `_settle_stamps`, change the wording chain to:

```python
            if frame is not None:
                said = f"mark {number} stamped in trial {index}, frame {frame}"
            elif self.phase != "running":
                said = f"mark {number} stamped with no run in progress"
            elif paused:
                said = f"mark {number} stamped while paused, before trial {index}"
            else:
                said = f"mark {number} stamped between trials, before trial {index}"
```

In `_command`, before `if self.phase != "running":`, add:

```python
        if isinstance(command, _link.Mark) and self.service and self.phase != "running":
            # A mark's note, between runs or awaiting the return: joined to its stamp
            # (`stamp`), since a mark is never refused once pressed.
            self._mark_note(command, index)
            return
```

and make the guard's sentence depend on the phase:

```python
        if self.phase != "running":
            self._refuse(
                command.name if isinstance(command, _link.SetParameter) else command.KIND,
                command.by,
                "no run is in progress, so a command for a run is not applied; start a "
                "run first"
                if self.phase == "between_runs"
                else "the session has ended and is waiting for the animal's return to its "
                "cage, which is recorded from the page (End session); a command sent now "
                "is not applied"
                if self.service
                else "the session has ended and is waiting for the animal's return to its "
                "cage, which is marked at wlx run's terminal; a command sent now is not "
                "applied",
            )
            return
```

`return_not_recorded` gains `how: str = "wlx run"` and passes it to `_note`.

Add:

```python
    def end_runs(self, by: str) -> None:
        """No further run in this session (P4d-2b spec §6.2, *End session*; the b3a-1
        plan, decision 6): it stops taking runs, its head is released, and it waits for
        its animal's return, as `wlx run`'s does after its one run.

        **The release is recorded now, before the return**, because `welfare` refuses a
        return while the head is fixed and one before the release: End session is
        pressed as the animal leaves the chair, and the return follows when it is home.
        A session that ran no run is given a stop reason saying so; one that did keeps
        its last run's, which is how its runs ended. Only a service session between runs
        may do this; `wlx taskd` stops a run in progress first."""
        if not self.service or self.phase != "between_runs":
            raise RuntimeError(
                f"end_runs() is for a service session between runs, and this one is "
                f"{self.phase or 'not open'}"
            )
        if not self.stopped_because:
            self.stopped_because = f"session ended by {by}, before any run"
            self.stop_kind = "operator"
        if self.welfare.fixed_wall_at is not None and self.welfare.released_wall_at is None:
            self.head_released(self.wall_now())
        self.phase = "awaiting_return"
        self._control(
            "end", by, f"session ended by {by}: waiting for the animal's return", self._index
        )

    def close(self, how: str) -> None:
        """The animal is home: the session's own clock ended, and its one `closed` frame
        (`await_return` does the same for `wlx run`'s). Refused until the return is
        recorded."""
        if self.welfare.returned_wall_at is None:
            raise RuntimeError(
                "close() before the return is recorded: the animal is not home"
            )
        self.phase = "closed"
        self.end(how=how)
        self.publish()

    def stamp(self, mark: int) -> None:
        """A mark signal that arrived with no trial loop checking for one -- a service
        session between runs, or awaiting its return -- stamped and written at once, as
        the paused loop stamps one (P4d-2b spec §5.1)."""
        self._stamp(mark, None)
        self._settle_stamps(self._index)

    def refuse(self, name: str, by: str, why: str) -> None:
        """One refusal onto this session's feed from outside its trial loop: a console
        command `wlx taskd` could not act on. See `refusals`."""
        self._refuse(name, by, why)

    def receive(self, command) -> None:
        """A console command that reached this session outside a run (`wlx taskd`, between
        runs or awaiting the return): `_command` refuses it for its phase, or joins a
        mark's note."""
        self._command(command, self._index)

    def publish(self) -> None:
        """One frame of this session as it stands, for a caller between its runs."""
        self._publish()

    def _after_service_run(self) -> None:
        """A service session's run is over (the b3a-1 plan, decisions 1 and 2): back
        between runs, where nothing applies a staged change, so any left is dropped and
        said on the feed -- a row kept would read "applies at the next trial" of a run
        that may never come."""
        for name, was, now, by, _bounded in self._staged:
            self._feed(
                "set",
                by,
                self.wall_now(),
                f"{name} {_shown(was)} → {_shown(now)} was not applied: run "
                f"{self.run_index} ended first",
            )
        self._staged.clear()
        self.phase = "between_runs"
```

Add to `_fixed_config`'s dict: `"service": self.service,`.

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_taskd.py -q -p no:cacheprovider`
Expected: PASS — including `test_taskd.py`'s existing post-loop refusal test, which reads "waiting for the animal's return".

- [ ] **Step 5: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/taskd.py tests/test_taskd.py
git commit -m "Let a session wait between runs, and end its runs before its return"
```

---

### Task 4: Telemetry schema 10, the idle frame, and the service's commands on the wire (`link.py`)

**Files:**
- Modify: `wl_xcon/link.py`
- Test: `tests/test_link.py` (and its `_session_with` stand-in), `tests/_frames.py`, `tests/test_cli.py` (its `_telemetry` helper only)

**Interfaces:**
- Consumes: Task 3's `Session.task`, `run_index`, `service`, `preflight`, `question`, `offered_tasks`.
- Produces: `SCHEMA = 10`; `PreflightItem(name: str, result: str, said: str)`; `Preflight(task: str, items: tuple[PreflightItem, ...])`; `Question(mark: str, session_id: str, at: float, said: str, answers: tuple[str, ...])`; `Stranded(session_id: str, subject: str, left_at: float | None)`; `Idle(schema, phase, wall_at, stranded, question, refusals, refusals_dropped, animals, offered_tasks)` with `Idle.of(*, wall_at, stranded, question, refusals, refusals_dropped, link, animals, offered_tasks) -> Idle`; `Telemetry` gains `run_index: int | None`, `service: bool`, `preflight: Preflight | None`, `question: Question | None`, `offered_tasks: tuple`, and `block: str | None`, `task: str | None`; `decode` returns `Telemetry | Idle`; commands `OpenSession` (KIND `"open"`: `by, session_id, animal, deployment, view, departure, delivered_today, answer, amend_to, amend_reason`), `CheckRun` (`"check"`: `by, task, values`), `StartRun` (`"start"`: `by, task, values, trials, acknowledged`), `EndSession` (`"end"`: `by, session_id, returned, confirm`); `VALUES_LIMIT = 64`; `ACKNOWLEDGED_LIMIT = 16`.

- [ ] **Step 1: Write the failing tests**

Update the fixtures first. In `tests/_frames.py`'s `frame()`, add after `half_ipd_cm=None,`:

```python
        run_index=0,
        service=False,
        preflight=None,
        question=None,
        offered_tasks=(),
```

and say in its docstring that schema 10's `preflight` and `question` are `None` for the ordinary frame, like `paused_at`. Do the same in `tests/test_cli.py`'s `_telemetry`. In `tests/test_link.py`'s `_session_with` stand-in, add `task="tasks/fixation_detection.py",` (beside `spec`, at the top level), `run_index=0,`, `service=False,`, `preflight=None,`, `question=None,`, `offered_tasks=(),` with a comment "Read by `Telemetry.of` since schema 10 (P4d-2b b3a)". Change `SCHEMA == 9` to `SCHEMA == 10` in `test_schema_8_reads_the_pause_the_schedule_and_the_feed_from_the_session` and `test_a_frame_carries_the_setup_the_session_runs_in`, and `reads schema 9` to `reads schema 10` in `test_a_schema_7_frame_is_refused_by_a_schema_9_reader` (renaming it `..._by_a_schema_10_reader`).

Then add to `tests/test_link.py` (importing `CheckRun`, `EndSession`, `Idle`, `OpenSession`, `Preflight`, `PreflightItem`, `Question`, `StartRun`, `Stranded` from `wl_xcon.link`):

```python
PREFLIGHT = Preflight(
    task="fixation_detection.py",
    items=(
        PreflightItem("task checks", "pass", "passes"),
        PreflightItem("pump calibration", "unknown", "not measured (V10)"),
    ),
)
QUESTION = Question(
    mark="return",
    session_id="2027-01-14_01",
    at=1_700_000_000.0,
    said="the return given for subject 'A' is 9000 s before the clock",
    answers=("confirm", "re-type"),
)


def test_schema_10_survives_the_wire_with_its_absences_intact():
    """Spec §6.3: the run index, `None` before any run; the pending run's pre-flight;
    the question a console owes an answer on; and whether a service sent it."""
    populated = _telemetry(
        run_index=2, service=True, preflight=PREFLIGHT, question=QUESTION,
        offered_tasks=("fixation_detection.py",), phase="between_runs",
    )
    before_any_run = _telemetry(run_index=None, block=None, task=None, service=True)

    for original in (populated, before_any_run, _telemetry()):
        assert decode(encode(original)) == original
    assert type(decode(encode(populated)).preflight.items[0]) is PreflightItem
    assert type(decode(encode(populated)).question) is Question
    assert SCHEMA == 10


def test_a_session_before_its_first_run_has_no_block_task_or_counts():
    """Unknown is `None`, never a guess (S9a §9): with no run, there is no block and no
    task; zero trials and no outcome are true."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.task = None
    session.run_index = None

    telemetry = Telemetry.of(session, None, None, index=0)

    assert (telemetry.block, telemetry.task, telemetry.run_index) == (None, None, None)
    assert (telemetry.outcomes, telemetry.hangs, telemetry.owed) == ({}, 0, {})


def test_an_idle_frame_is_its_own_shape_and_survives_the_wire():
    """The b3a-1 plan, decision 8: no session, so none of a session's numbers."""
    idle = Idle(
        schema=SCHEMA,
        phase="idle",
        wall_at=1_700_000_000.0,
        stranded=(Stranded("2027-01-13_01", "B", 1_699_990_000.0), Stranded("2027-01-13_02", "", None)),
        question=replace(QUESTION, mark="departure", answers=("confirm", "amend")),
        refusals=(Refused(name="open", by="jake", why="a session is open"),),
        refusals_dropped=0,
        animals=("A", "B"),
        offered_tasks=("fixation_detection.py",),
    )

    restored = decode(encode(idle))

    assert restored == idle
    assert all(type(s) is Stranded for s in restored.stranded)


def test_an_idle_frame_of_another_schema_is_refused_by_name():
    old = encode(
        Idle(
            schema=9, phase="idle", wall_at=1.0, stranded=(), question=None,
            refusals=(), refusals_dropped=0, animals=(), offered_tasks=(),
        )
    )

    with pytest.raises(SchemaMismatch, match="carried schema 9 and this console reads schema 10"):
        decode(old)


def test_an_idle_frame_carries_the_links_refusals_too_capped_and_counted():
    link = Simulated()
    link.refused.extend(Refused("<transport>", "<unknown>", f"bad {i}") for i in range(3))
    mine = [Refused("open", "jake", f"refused {i}") for i in range(REFUSAL_HISTORY)]

    idle = Idle.of(
        wall_at=1.0, stranded=(), question=None, refusals=mine, refusals_dropped=4,
        link=link, animals=(), offered_tasks=(),
    )

    assert len(idle.refusals) == REFUSAL_HISTORY
    assert idle.refusals[-1].why == "bad 2"
    assert idle.refusals_dropped == 4 + 3


SERVICE_COMMANDS = (
    OpenSession(
        by="jake (box, unverified)", session_id="2027-01-14_01", animal="A",
        deployment="rig_fixed", view="direct", departure="09:30", delivered_today=12.5,
        answer="amend", amend_to="08:45", amend_reason="typed 09:30 for 08:45",
    ),
    CheckRun(by="jake", task="fixation_detection.py", values={"fix_hold": 0.3, "looks": "circle"}),
    StartRun(
        by="jake", task="fixation_detection.py", values={"fix_hold": 0.3}, trials=100,
        acknowledged=("pump calibration", "eye tracker"),
    ),
    EndSession(by="jake", session_id=None, returned="now", confirm=True),
)


@pytest.mark.parametrize("command", SERVICE_COMMANDS, ids=lambda c: c.KIND)
def test_the_services_commands_cross_a_real_socket_intact(zmq_cleanup, command):
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    console.send(command)

    assert _decode_command(_encode_command(command)) == command
    assert _drain_until(link) == [command]


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({"kind": "open", "session_id": 7}, "session_id"),
        ({"kind": "open", "deployment": "cage_side"}, "rig_fixed or rig_chaired"),
        ({"kind": "open", "view": "sideways"}, "direct or stereoscope"),
        ({"kind": "open", "answer": "maybe"}, "confirm, amend or none"),
        ({"kind": "open", "delivered_today": float("nan")}, "delivered_today"),
        ({"kind": "open", "delivered_today": True}, "delivered_today"),
        ({"kind": "open", "amend_reason": "x" * 501}, "amend_reason"),
        ({"kind": "start", "values": {"fix_hold": "x" * 201}}, "at most 200"),
        ({"kind": "start", "values": {"fix_hold": float("inf")}}, "not a real number"),
        ({"kind": "start", "values": {f"p{i}": 1.0 for i in range(65)}}, "at most 64"),
        ({"kind": "start", "trials": 0}, "trials"),
        ({"kind": "start", "trials": True}, "trials"),
        ({"kind": "start", "acknowledged": "pump calibration"}, "acknowledged"),
        ({"kind": "start", "acknowledged": ["x"] * 17}, "acknowledged"),
        ({"kind": "check", "task": ""}, "task"),
        ({"kind": "end", "confirm": "yes"}, "confirm"),
        ({"kind": "end", "returned": 1_700_000_000}, "returned"),
    ],
)
def test_a_service_command_with_a_malformed_field_is_refused_before_it_exists(fields, said):
    """M8's rule for the new commands: every field checked where the bytes become a
    command, the refusal naming what it could of the command and its sender."""
    base = {
        "open": {
            "by": "jake", "session_id": "2027-01-14_01", "animal": "A",
            "deployment": "rig_fixed", "view": "direct", "departure": "09:30",
            "delivered_today": None, "answer": None, "amend_to": None, "amend_reason": "",
        },
        "check": {"by": "jake", "task": "t.py", "values": {}},
        "start": {"by": "jake", "task": "t.py", "values": {}, "trials": 3, "acknowledged": []},
        "end": {"by": "jake", "session_id": None, "returned": None, "confirm": False},
    }[fields["kind"]]

    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(**{**base, **fields}))

    assert refused.value.name == fields["kind"] or refused.value.name in fields.get("values", {})
    assert said in refused.value.why
```

(`_packed`, `_drain_until`, `REFUSAL_HISTORY`, `Refused`, `SchemaMismatch`, `replace` and `Simulated` are already in this file's imports or helpers.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_link.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'CheckRun'`.

- [ ] **Step 3: Implement**

In `wl_xcon/link.py`, append to the schema history and bump it:

```python
#: 10 (2026-09-29, P4d-2b b3a): sessions of several runs, and a service between them.
#: `phase` gains `between_runs`; `run_index` names the run (`None` before any);
#: `block` and `task` are `None` before a session's first run; `preflight` is the run
#: about to start's; `question` a far mark a console owes an answer on; `service` says a
#: frame came from `wlx taskd`, whose stream a run's stop does not end; `offered_tasks`
#: what it offers. **And a second shape, `Idle`**, published while no session is open
#: (phase `idle`). Nothing else changed meaning. A reader of 9 refuses 10 and 10 refuses
#: 9, by name, before any other field -- for both shapes (`SchemaMismatch`).
SCHEMA = 10
```

After `Control`:

```python
@dataclass(frozen=True, slots=True)
class PreflightItem:
    """One pre-flight item (P4d-2b spec §6.2): its name as a person acknowledges it,
    `pass`, `unknown` or `fail`, and the sentence saying why."""

    name: str
    result: str
    said: str


@dataclass(frozen=True, slots=True)
class Preflight:
    """The pre-flight of a run about to start (spec §6.3: "the run about to start
    carries its pre-flight results"): its task file, and its items in order."""

    task: str
    items: tuple


@dataclass(frozen=True, slots=True)
class Question:
    """A far mark a console owes an answer on (P4d-2b spec §6.2): which mark, for which
    session, the instant it was typed as, `welfare`'s sentence, and the answers --
    `confirm` or `amend` for a departure, `confirm` or `re-type` for a return."""

    mark: str
    session_id: str
    at: float
    said: str
    answers: tuple


@dataclass(frozen=True, slots=True)
class Stranded:
    """A session found under `--root` with a departure and no return (P4d-2b spec §6.1):
    its id, its animal, and the departure's instant -- `None`, with an empty subject,
    when its record has a line that is not a row and cannot be read."""

    session_id: str
    subject: str
    left_at: float | None


@dataclass(frozen=True, slots=True)
class Idle:
    """What `wlx taskd` publishes while no session is open (P4d-2b spec §6.1): **not a
    `Telemetry` with its fields empty**, since every one of those describes a session,
    and a console that promises never to guess at a fluid figure or a clock has none to
    show here (the b3a-1 plan, decision 8). The stranded sessions that keep a new one
    from opening, a question owed on a departure, the service's refusals with the
    link's, and what a console may open a session with."""

    schema: int
    #: Always `"idle"`: the field `decode` tells the two shapes apart by.
    phase: str
    #: The service's own anchored clock, as `Telemetry.wall_at` is a session's.
    wall_at: float
    stranded: tuple
    question: Question | None
    refusals: tuple
    refusals_dropped: int
    #: The animals under `--subjects` with a bounded config, by folder name.
    animals: tuple
    #: The task files under `--tasks`.
    offered_tasks: tuple

    @classmethod
    def of(
        cls,
        *,
        wall_at: float,
        stranded,
        question: Question | None,
        refusals,
        refusals_dropped: int,
        link,
        animals,
        offered_tasks,
    ) -> "Idle":
        """One idle frame: the service's refusals and the link's, capped at
        `REFUSAL_HISTORY` and counted, as `Telemetry.of` caps a session's."""
        combined = tuple(refusals) + tuple(link.refused)
        kept = combined[-REFUSAL_HISTORY:]
        return cls(
            schema=SCHEMA,
            phase="idle",
            wall_at=wall_at,
            stranded=tuple(stranded),
            question=question,
            refusals=kept,
            refusals_dropped=link.refused_dropped + refusals_dropped + len(combined) - len(kept),
            animals=tuple(animals),
            offered_tasks=tuple(offered_tasks),
        )
```

In `Telemetry`, change `block: str` to `block: str | None` with the comment "`None` before a session's first run (schema 10)", and `task: str` to `task: str | None` with "`session.task`: the run in progress or the last one; `None` before a session's first run (schema 10)". Append after `half_ipd_cm`:

```python
    #: `session.run_index`: the run in progress or the last one; `None` before any
    #: (P4d-2b spec §6.3), never 0.
    run_index: int | None
    #: `session.service`: a frame from `wlx taskd`, whose stream a run's stop does not
    #: end (the b3a-1 plan, decision 9).
    service: bool
    #: `session.preflight`: the run about to start's, or `None`.
    preflight: Preflight | None
    #: `session.question`: the answer a console owes on a far mark, or `None`.
    question: Question | None
    #: `session.offered_tasks`: the task files `wlx taskd` offers; empty for `wlx run`.
    offered_tasks: tuple
```

In `Telemetry.of`: `block=None if scheduler is None else scheduler.block.name`, `outcomes={} if tally is None else {k.value: v for k, v in tally.outcomes.items()}`, `hangs=0 if tally is None else tally.hangs`, `owed={} if scheduler is None else {c: scheduler.owed(c) for c in scheduler.upcoming()}`, `task=session.task`, and after `half_ipd_cm=...`:

```python
            run_index=session.run_index,
            service=session.service,
            preflight=session.preflight,
            question=session.question,
            offered_tasks=tuple(session.offered_tasks),
```

Add the wire helpers above `encode`:

```python
def _refusals_out(refusals) -> list:
    return [{"name": r.name, "by": r.by, "why": r.why} for r in refusals]


def _preflight_out(preflight: Preflight | None) -> dict | None:
    if preflight is None:
        return None
    return {
        "task": preflight.task,
        "items": [{"name": i.name, "result": i.result, "said": i.said} for i in preflight.items],
    }


def _question_out(question: Question | None) -> dict | None:
    if question is None:
        return None
    return {
        "mark": question.mark,
        "session_id": question.session_id,
        "at": question.at,
        "said": question.said,
        "answers": list(question.answers),
    }


def _question_in(data: dict | None) -> Question | None:
    if data is None:
        return None
    return Question(
        mark=data["mark"],
        session_id=data["session_id"],
        at=data["at"],
        said=data["said"],
        answers=tuple(data["answers"]),
    )
```

In `encode`, annotate its parameter `telemetry: Telemetry | Idle` and make its first statements, after `import msgpack`:

```python
    if isinstance(telemetry, Idle):
        return msgpack.packb(
            {
                "schema": telemetry.schema,
                "phase": telemetry.phase,
                "wall_at": telemetry.wall_at,
                "stranded": [
                    {"session_id": s.session_id, "subject": s.subject, "left_at": s.left_at}
                    for s in telemetry.stranded
                ],
                "question": _question_out(telemetry.question),
                "refusals": _refusals_out(telemetry.refusals),
                "refusals_dropped": telemetry.refusals_dropped,
                "animals": list(telemetry.animals),
                "offered_tasks": list(telemetry.offered_tasks),
            },
            use_bin_type=True,
        )
```

and add to the session payload after `"half_ipd_cm"`:

```python
        "run_index": telemetry.run_index,
        "service": telemetry.service,
        "preflight": _preflight_out(telemetry.preflight),
        "question": _question_out(telemetry.question),
        "offered_tasks": list(telemetry.offered_tasks),
```

In `decode`, change the return type to `Telemetry | Idle` and the `try` body to:

```python
    try:
        if data.get("phase") == "idle":
            return _idle_from(data)
        return _telemetry_from(data)
```

adding to its docstring: "**Two shapes, one schema** (b3a): a frame whose `phase` is `idle` is an `Idle`, checked for its schema first like every other." Add:

```python
def _idle_from(data: dict) -> Idle:
    """`_telemetry_from`'s twin for the idle shape."""
    return Idle(
        schema=data["schema"],
        phase=data["phase"],
        wall_at=data["wall_at"],
        stranded=tuple(Stranded(**s) for s in data["stranded"]),
        question=_question_in(data["question"]),
        refusals=tuple(Refused(**r) for r in data["refusals"]),
        refusals_dropped=data["refusals_dropped"],
        animals=tuple(data["animals"]),
        offered_tasks=tuple(data["offered_tasks"]),
    )
```

and to `_telemetry_from`, after `half_ipd_cm=...`:

```python
        run_index=data["run_index"],
        service=data["service"],
        preflight=(
            None
            if data["preflight"] is None
            else Preflight(
                task=data["preflight"]["task"],
                items=tuple(PreflightItem(**i) for i in data["preflight"]["items"]),
            )
        ),
        question=_question_in(data["question"]),
        offered_tasks=tuple(data["offered_tasks"]),
```

The commands, after `ManualReward`:

```python
@dataclass(frozen=True, slots=True)
class OpenSession:
    """Open a session in `wlx taskd` (P4d-2b spec §6.2): who sends it, the session id,
    the animal (a folder under `--subjects`), the deployment (`rig_fixed` or
    `rig_chaired`), the setup (`direct` or `stereoscope`), the departure **as typed**,
    the fluid already given today or `None`, and the answer to a far departure --
    `None`, `"confirm"`, or `"amend"` with the corrected time as typed and a reason."""

    KIND: ClassVar[str] = "open"

    by: str
    session_id: str
    animal: str
    deployment: str
    view: str
    departure: str
    delivered_today: float | None
    answer: str | None
    amend_to: str | None
    amend_reason: str


@dataclass(frozen=True, slots=True)
class CheckRun:
    """Take a run's pre-flight without starting it (spec §6.2: "Pre-flight is shown
    before the run starts"): a task file under `--tasks` and its starting values."""

    KIND: ClassVar[str] = "check"

    by: str
    task: str
    values: dict


@dataclass(frozen=True, slots=True)
class StartRun:
    """Start a run: its task, starting values and trial count, and **the unknown
    pre-flight items this person acknowledges, by name** (S9a §10). The service takes
    the pre-flight again when this arrives, and starts nothing unless it passes."""

    KIND: ClassVar[str] = "start"

    by: str
    task: str
    values: dict
    trials: int
    acknowledged: tuple


@dataclass(frozen=True, slots=True)
class EndSession:
    """End a session (spec §6.2): stop a run in progress, release the head, and record
    the return -- `returned` as typed, or `None` to end the runs and give it later;
    `confirm` for a far one. While no session is open, `session_id` names a stranded
    session to record the return of; otherwise it may name the open one or be `None`."""

    KIND: ClassVar[str] = "end"

    by: str
    session_id: str | None
    returned: str | None
    confirm: bool
```

`Command` gains `| OpenSession | CheckRun | StartRun | EndSession`. Add the limits after `TEXT_LIMIT`:

```python
#: The most starting values one `CheckRun` or `StartRun` may carry, and the most items
#: one may acknowledge: bounds on one packet's reach into a refusal row, the record and
#: every frame, not rules about tasks -- no task here declares a dozen parameters.
VALUES_LIMIT = 64
ACKNOWLEDGED_LIMIT = 16
```

In `_encode_command`, before the `else:`:

```python
    elif isinstance(command, OpenSession):
        payload = {
            "kind": "open", "by": command.by, "session_id": command.session_id,
            "animal": command.animal, "deployment": command.deployment,
            "view": command.view, "departure": command.departure,
            "delivered_today": command.delivered_today, "answer": command.answer,
            "amend_to": command.amend_to, "amend_reason": command.amend_reason,
        }
    elif isinstance(command, (CheckRun, StartRun)):
        payload = {
            "kind": command.KIND, "by": command.by, "task": command.task,
            "values": dict(command.values),
        }
        if isinstance(command, StartRun):
            payload["trials"] = command.trials
            payload["acknowledged"] = list(command.acknowledged)
    elif isinstance(command, EndSession):
        payload = {
            "kind": "end", "by": command.by, "session_id": command.session_id,
            "returned": command.returned, "confirm": command.confirm,
        }
```

Add the decode helpers after `_setting`:

```python
def _word(data: dict, key: str, kind: str, by: str, *, optional: bool = False) -> str | None:
    """A field that is one non-empty string of at most `TEXT_LIMIT` characters, or
    `None` where `optional` allows it; refused otherwise, naming the field."""
    value = data.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > TEXT_LIMIT:
        raise CommandRefused(
            kind,
            by,
            f"a {kind!r} command's {key} is text of 1 to {TEXT_LIMIT} characters, and "
            f"{_quoted(value)} is not, so it is refused",
        )
    return value


def _values(data: dict, kind: str, by: str) -> dict:
    """A run's starting values: at most `VALUES_LIMIT` names, each a parameter name, each
    value what a setting may be (`_setting`, M8's rule, called unchanged)."""
    values = data.get("values")
    if not isinstance(values, dict) or len(values) > VALUES_LIMIT:
        raise CommandRefused(
            kind,
            by,
            f"a {kind!r} command's values are at most {VALUES_LIMIT} named settings, "
            f"and these are not, so it is refused",
        )
    checked = {}
    for name, value in values.items():
        if not isinstance(name, str) or not name or len(name) > TEXT_LIMIT:
            raise CommandRefused(
                kind, by, f"a starting value's name {_quoted(name)} is not one, so it is refused"
            )
        checked[name] = _setting(value, name, by)
    return checked
```

In `_decode_command`, before the final `raise ValueError(...)`:

```python
    if kind == "open":
        by = _actor(data.get("by"), "open")
        if data.get("deployment") not in ("rig_fixed", "rig_chaired"):
            raise CommandRefused(
                "open", by,
                f"a session's deployment is rig_fixed or rig_chaired, and "
                f"{_quoted(data.get('deployment'))} is neither, so it is refused",
            )
        if data.get("view") not in ("direct", "stereoscope"):
            raise CommandRefused(
                "open", by,
                f"a session's setup is direct or stereoscope, and "
                f"{_quoted(data.get('view'))} is neither, so it is refused",
            )
        if data.get("answer") not in (None, "confirm", "amend"):
            raise CommandRefused(
                "open", by,
                f"a departure is answered confirm, amend or none, and "
                f"{_quoted(data.get('answer'))} is none of them, so it is refused",
            )
        delivered = data.get("delivered_today")
        if delivered is not None:
            try:
                finite = (
                    not isinstance(delivered, bool)
                    and isinstance(delivered, (int, float))
                    and math.isfinite(delivered)
                )
            except OverflowError:
                finite = False
            if not finite:
                raise CommandRefused(
                    "open", by,
                    f"delivered_today is mL or nothing, and {_quoted(delivered)} is "
                    f"neither, so it is refused",
                )
            delivered = float(delivered)
        reason = data.get("amend_reason", "")
        if not isinstance(reason, str) or len(reason) > NOTE_LIMIT:
            raise CommandRefused(
                "open", by,
                f"an amend_reason is text of at most {NOTE_LIMIT} characters, so this "
                f"one is refused",
            )
        return OpenSession(
            by=by,
            session_id=_word(data, "session_id", "open", by),
            animal=_word(data, "animal", "open", by),
            deployment=data["deployment"],
            view=data["view"],
            departure=_word(data, "departure", "open", by),
            delivered_today=delivered,
            answer=data.get("answer"),
            amend_to=_word(data, "amend_to", "open", by, optional=True),
            amend_reason=reason,
        )
    if kind in ("check", "start"):
        by = _actor(data.get("by"), kind)
        task = _word(data, "task", kind, by)
        values = _values(data, kind, by)
        if kind == "check":
            return CheckRun(by=by, task=task, values=values)
        trials = data.get("trials")
        if isinstance(trials, bool) or not isinstance(trials, int) or not 1 <= trials <= TRIALS_LIMIT:
            raise CommandRefused(
                "start", by,
                f"a run's trials are a whole number from 1 to {TRIALS_LIMIT}, and "
                f"{_quoted(trials)} is not one, so it is refused",
            )
        acknowledged = data.get("acknowledged")
        if (
            not isinstance(acknowledged, (list, tuple))
            or len(acknowledged) > ACKNOWLEDGED_LIMIT
            or not all(isinstance(a, str) and 0 < len(a) <= TEXT_LIMIT for a in acknowledged)
        ):
            raise CommandRefused(
                "start", by,
                f"a run's acknowledged items are at most {ACKNOWLEDGED_LIMIT} names, and "
                f"{_quoted(acknowledged)} is not that, so it is refused",
            )
        return StartRun(by=by, task=task, values=values, trials=trials, acknowledged=tuple(acknowledged))
    if kind == "end":
        by = _actor(data.get("by"), "end")
        confirm = data.get("confirm", False)
        if not isinstance(confirm, bool):
            raise CommandRefused(
                "end", by, f"confirm is true or false, and {_quoted(confirm)} is neither, so it is refused"
            )
        return EndSession(
            by=by,
            session_id=_word(data, "session_id", "end", by, optional=True),
            returned=_word(data, "returned", "end", by, optional=True),
            confirm=confirm,
        )
```

Update `Link.publish`'s and `Simulated.publish`'s annotations to `Telemetry | Idle`, and the module docstring's list of what this file holds.

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_link.py tests/test_cli.py tests/test_web.py tests/test_health.py tests/test_serve.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass. (No console has an `Idle` to read yet: only Task 7's service publishes one.)

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/link.py tests/test_link.py tests/_frames.py tests/test_cli.py
git commit -m "Put runs, the idle frame and the service's commands on the wire, schema 10"
```

---

### Task 5: The consoles read schema 10 (`wlx console`, the page, `/health`)

**Files:**
- Modify: `wl_xcon/cli.py` (`render`, new `_render_idle`, `_question_line`, `_moment`, `_refusal_lines`; `wlx console`'s watch), `wl_xcon/web.py` (`fragments`, new `_idle`, `_idle_banners`, `_question_banner`, `_idle_refusals`; `_state`, `_head`, `_banners`, `_controls`, `_setup`, `_end`), `wl_xcon/health.py` (`expects_frames`, `verdict`, `_state_text`, `_featured`, `readings`), `wl_xcon/serve.py` (`Hub.offer`)
- Test: `tests/_frames.py` (an `idle()` builder), `tests/test_cli.py`, `tests/test_web.py`, `tests/test_health.py`, `tests/test_serve.py`

**Interfaces:**
- Consumes: Task 4's `Idle`, `Stranded`, `Question`, `Preflight` and `Telemetry`'s new fields.
- Produces: `tests/_frames.idle(**overrides) -> Idle`; `render(frame: Telemetry | Idle) -> str`; `fragments(frame: Telemetry | Idle | None, view) -> dict`; `health.expects_frames/verdict/readings/response` taking `Telemetry | Idle | None`; `Hub.offer(frame: Telemetry | Idle)`.

- [ ] **Step 1: Write the failing tests**

`tests/_frames.py`, importing `Idle` and `Stranded`:

```python
def idle(**overrides) -> Idle:
    """`wlx taskd` with no session open: nothing stranded, nothing owed, two animals and
    one task to offer."""
    base = Idle(
        schema=SCHEMA,
        phase="idle",
        wall_at=1_700_000_041.5,
        stranded=(),
        question=None,
        refusals=(),
        refusals_dropped=0,
        animals=("A", "B"),
        offered_tasks=("fixation_detection.py",),
    )
    return replace(base, **overrides) if overrides else base
```

`tests/test_cli.py` (importing `idle` from `_frames`, and `Idle`, `Preflight`, `PreflightItem`, `Question`, `Refused`, `Stranded` from `wl_xcon.link`):

```python
def test_the_terminal_console_says_no_session_is_open_and_what_is_stranded():
    shown = render(
        idle(
            stranded=(Stranded("2027-01-13_01", "B\x1b[2J", 1_700_000_000.0), Stranded("2027-01-13_02", "", None)),
            refusals=(Refused("open", "jake", "no session opens while <b>"),),
        )
    )

    assert shown.splitlines()[0] == "no session open  (wlx taskd, idle)"
    assert "STRANDED: B�[2J, session 2027-01-13_01, left its cage at" in shown
    assert "session 2027-01-13_02: its welfare record cannot be read" in shown
    assert "animals: A, B" in shown and "tasks offered: fixation_detection.py" in shown
    assert "refused: open by jake: no session opens while <b>" in shown


def test_the_terminal_console_shows_a_session_between_runs_honestly():
    shown = render(
        _telemetry(
            phase="between_runs", service=True, run_index=None, block=None, task=None,
            preflight=Preflight("fixation_detection.py", (PreflightItem("pump calibration", "unknown", "not measured (V10)"),)),
            question=Question("return", "2027-01-14_01", 1.0, "the return is far", ("confirm", "re-type")),
        )
    )

    assert "block none yet" in shown and "task: no run yet" in shown
    assert "phase: between runs" in shown and "run: none yet" in shown
    assert "runs: opened, run and ended from a console (wlx taskd)" in shown
    assert "pre-flight (fixation_detection.py): pump calibration unknown: not measured (V10)" in shown
    assert "QUESTION (return, session 2027-01-14_01): the return is far -- answer confirm or re-type" in shown


def test_wlx_console_keeps_watching_a_service_past_a_runs_end(monkeypatch, capsys):
    """The b3a-1 plan, decision 9: a service's run stop is not the last frame, so the
    watch goes on -- through between runs and idle -- until the operator interrupts."""
    frames = iter(
        [
            _telemetry(service=True, stop_kind="completed", stopped_because="every block is finished"),
            _telemetry(service=True, phase="between_runs", stop_kind="completed", stopped_because="every block is finished"),
            idle(),
        ]
    )

    class _Console:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def send(self, command):
            return None

        def receive(self):
            try:
                return next(frames)
            except StopIteration:
                raise KeyboardInterrupt from None

    monkeypatch.setattr(_link, "ZmqConsole", _Console)

    assert main(["console", "--sub", "tcp://127.0.0.1:1", "--req", "tcp://127.0.0.1:2"]) == 130
    out = capsys.readouterr().out
    assert "phase: between runs" in out and "no session open" in out
```

(`_link` is `wl_xcon.link`; import it in this test file if it is not already.)

`tests/test_web.py`, importing `idle` and the link types:

```python
def test_the_page_with_no_session_open_says_so_and_puts_a_stranded_animal_first():
    panes = fragments(
        idle(
            stranded=(Stranded("2027-01-13_01", "<b>B</b>", 1_700_000_000.0),),
            question=Question("departure", "2027-01-14_01", 1.0, "far <i>", ("confirm", "amend")),
            refusals=(Refused("open", "jake", "refused <script>"),),
        ),
        view(),
    )

    assert set(panes) == set(FRAGMENT_IDS)
    assert 'data-state="idle"' in panes["state"]
    assert panes["banners"].index("Stranded") < panes["banners"].index("Confirm")
    assert "&lt;b&gt;B&lt;/b&gt;" in panes["banners"] and "<b>B" not in panes["banners"]
    assert "far &lt;i&gt; · answer confirm or amend" in panes["banners"]
    assert "Waiting" not in panes["banners"]
    assert "refused &lt;script&gt;" in panes["rt-changes"]
    assert "controls · no session open" in panes["controls"]
    assert "none open · wlx taskd is idle" in panes["rt-health"]
    assert '<span class="pill warn">degraded</span>' in panes["rt-health"], "an animal is stranded"


def test_the_page_between_runs_says_which_run_ended_and_offers_no_run_controls():
    panes = fragments(
        frame(phase="between_runs", service=True, run_index=1, stop_kind="operator", stopped_because="stopped by jake"),
        view(),
    )

    assert 'data-state="between-runs"' in panes["state"] and "run 1 ended" in panes["state"]
    assert "Run 1 ended" in panes["banners"]
    assert "controls · no run in progress" in panes["controls"]
    assert '<span class="k">Run</span><span class="v">1</span>' in panes["head-id"]


def test_the_page_before_a_sessions_first_run_shows_no_block_and_no_task():
    panes = fragments(
        frame(phase="between_runs", service=True, run_index=None, block=None, task=None, trial_index=0, outcomes={}),
        view(),
    )

    assert "between runs" in panes["state"] and "None" not in panes["head-id"]
    assert "no run yet" in panes["setup"] and "no run yet" in panes["end"]


def test_the_page_shows_the_question_a_return_owes():
    panes = fragments(
        frame(phase="awaiting_return", service=True, stop_kind="operator", stopped_because="session ended by jake",
              question=Question("return", "2027-01-14_01", 1.0, "the return is far", ("confirm", "re-type"))),
        view(),
    )

    assert "the return is far · answer confirm or re-type" in panes["banners"]
```

`tests/test_health.py`: import `idle`, `Stranded`, `Idle`; add to `CASES`:

```python
    "idle": (idle(), 1.0),
    "stranded": (idle(stranded=(Stranded("2027-01-13_01", "B", 1_699_990_000.0),)), 1.0),
    "between runs": (
        frame(phase="between_runs", service=True, run_index=0, stop_kind="completed",
              stopped_because="every block is finished"),
        1.0,
    ),
    "before the first run": (
        frame(phase="between_runs", service=True, run_index=None, block=None, task=None,
              trial_index=0, outcomes={}),
        1.0,
    ),
```

to `EXPECTED`: `"idle": "ok", "stranded": "degraded", "between runs": "ok", "before the first run": "ok",`; to `test_the_featured_reading_is_the_one_that_drove_the_verdict`'s list: `("idle", "state"), ("stranded", "stranded"), ("between runs", "out_of_cage"),`; and:

```python
def test_a_service_between_runs_that_goes_quiet_is_degraded():
    """The b3a-1 plan, decision 9: a service publishes between runs and while idle, so
    silence there is a stale stream, as a running session's is."""
    for quiet in (
        frame(phase="between_runs", service=True, stop_kind="completed", stopped_because="done"),
        idle(),
    ):
        assert expects_frames(quiet)
        assert verdict(quiet, frame_age_s=45.0, stale_after_s=30.0, rejected=None) == "degraded"


def test_the_readings_say_no_session_is_open_and_which_animal_is_stranded():
    rows = {
        r["key"]: r["value"]
        for r in readings(
            idle(stranded=(Stranded("2027-01-13_01", "B<", 1.0),)),
            frame_age_s=1.0, stale_after_s=30.0, rejected=None, endpoint=ENDPOINT,
        )
    }

    assert rows["session"] == "none open · wlx taskd is idle"
    assert rows["state"] == "idle · no session open · an animal's return is not recorded"
    assert rows["stranded"] == "2027-01-13_01 · B(lt) · return not recorded"


def test_between_runs_the_state_names_the_run_and_how_it_ended():
    rows = {
        r["key"]: r["value"]
        for r in readings(
            frame(phase="between_runs", service=True, run_index=2, stop_kind="operator",
                  stopped_because="stopped by jake"),
            frame_age_s=1.0, stale_after_s=30.0, rejected=None, endpoint=ENDPOINT,
        )
    }

    assert rows["state"] == "between runs · run 2 ended (operator): stopped by jake"
```

`tests/test_serve.py`, importing `idle`:

```python
def test_an_idle_frame_is_held_and_derives_no_rate():
    """No session, no trials: the rate window empties, and a session's next frame
    starts it afresh."""
    steady = _Clock()
    hub = _hub(steady)
    hub.offer(frame(trial_index=10))
    steady.t += 2.0
    hub.offer(frame(trial_index=12))
    steady.t += 2.0

    hub.offer(idle())

    latest, view_ = hub.snapshot(on_box=True, stale_after_s=30.0)
    assert isinstance(latest, Idle) and view_.trials_per_min is None
    steady.t += 2.0
    hub.offer(frame(trial_index=0))
    assert hub.trials_per_min() is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_cli.py tests/test_web.py tests/test_health.py tests/test_serve.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: 'Idle' object has no attribute 'session_id'` and the like.

- [ ] **Step 3: `wlx console`**

In `wl_xcon/cli.py`, add after `_printable`:

```python
def _moment(at: object) -> str:
    """A wire instant as this host's local date, minute and zone, or `an unknown time`
    for one it cannot show -- never a crash of the screen."""
    try:
        return _local(at)
    except (OverflowError, OSError, ValueError, TypeError):
        return "an unknown time"


def _question_line(question: _link.Question) -> str:
    """The answer a console owes on a far mark, as the page offers it (spec §6.2)."""
    return (
        f"  QUESTION ({_printable(question.mark)}, session "
        f"{_printable(question.session_id)}): {_printable(question.said)} -- answer "
        f"{' or '.join(_printable(answer) for answer in question.answers)}"
    )


def _refusal_lines(refusals: tuple, dropped: int) -> list[str]:
    """The refusal feed's lines, the dropped count above them -- `render`'s own, for a
    session's frame and an idle one alike."""
    if not refusals:
        return ["  refused: none"]
    lines = []
    if dropped:
        lines.append(
            f"  refused: {dropped} earlier refusal(s) NOT SHOWN -- only the most recent "
            f"{len(refusals)} are kept (link.REFUSAL_HISTORY)"
        )
    for refusal in refusals:
        lines.append(
            f"  refused: {_printable(refusal.name)} by {_printable(refusal.by)}: "
            f"{_printable(refusal.why)}"
        )
    return lines


def _render_idle(frame: _link.Idle) -> str:
    """`wlx taskd` with no session open (P4d-2b spec §6.1): any stranded animal first,
    then a question owed, what a session may be opened with, and the refusals."""
    lines = ["no session open  (wlx taskd, idle)"]
    for found in frame.stranded:
        if found.left_at is None:
            lines.append(
                f"  STRANDED: session {_printable(found.session_id)}: its welfare record "
                f"cannot be read; no session opens until it is repaired and its "
                f"animal's return recorded"
            )
        else:
            lines.append(
                f"  STRANDED: {_printable(found.subject)}, session "
                f"{_printable(found.session_id)}, left its cage at {_moment(found.left_at)}, "
                f"this host's local time; its return is not recorded, and no session "
                f"opens until it is"
            )
    if frame.question is not None:
        lines.append(_question_line(frame.question))
    lines.append(f"  animals: {', '.join(_printable(a) for a in frame.animals) or 'none'}")
    lines.append(
        f"  tasks offered: {', '.join(_printable(t) for t in frame.offered_tasks) or 'none'}"
    )
    lines.extend(_refusal_lines(frame.refusals, frame.refusals_dropped))
    return "\n".join(lines)
```

In `render`: its first statement becomes `if isinstance(frame, _link.Idle): return _render_idle(frame)`; the first line's `block {_printable(frame.block)}` becomes `block {'none yet' if frame.block is None else _printable(frame.block)}`; the `task:` part becomes `task: {'no run yet' if frame.task is None else _printable(frame.task)}`; after the `phase:` line add:

```python
    # Schema 10 (P4d-2b b3a): which run, and whether a service holds the session.
    lines.append("  run: none yet" if frame.run_index is None else f"  run: {frame.run_index}")
    if frame.service:
        lines.append("  runs: opened, run and ended from a console (wlx taskd)")
    if frame.offered_tasks:
        lines.append(
            f"  tasks offered: {', '.join(_printable(t) for t in frame.offered_tasks)}"
        )
```

after the `WARNING:` line: `if frame.question is not None: lines.append(_question_line(frame.question))`; before the staged rows:

```python
    if frame.preflight is not None:
        for item in frame.preflight.items:
            lines.append(
                f"  pre-flight ({_printable(frame.preflight.task)}): "
                f"{_printable(item.name)} {_printable(item.result)}: {_printable(item.said)}"
            )
```

and replace the refusal block at its end with `lines.extend(_refusal_lines(frame.refusals, frame.refusals_dropped))`. Add to its docstring: "**Schema 10 adds runs and the service** (P4d-2b b3a): the run, whether `wlx taskd` holds the session, the pre-flight of the run about to start, and a question owed; an `Idle` frame is `_render_idle`'s."

In `main`'s `console` branch, replace `if frame.stopped_because: break` with:

```python
                    # A session's stop ends the watch -- unless `wlx taskd` sent it,
                    # whose stream goes on between runs and while idle (the b3a-1
                    # plan, decision 9): watched until Ctrl-C.
                    if (
                        isinstance(frame, _link.Telemetry)
                        and not frame.service
                        and frame.stopped_because
                    ):
                        break
```

- [ ] **Step 4: The page**

In `wl_xcon/web.py`, import `Idle`. `fragments` becomes:

```python
def fragments(frame: Telemetry | Idle | None, view: View) -> dict[str, str]:
    """Every pane of the page for one frame, keyed by the id of the element each one
    fills (`FRAGMENT_IDS`, in that order). `frame` is `None` before any has arrived,
    and every pane then says so; an `Idle` is `wlx taskd` with no session open."""
    if isinstance(frame, Idle):
        return _idle(frame, view)
    return {
        ...  # unchanged
    }
```

Add:

```python
def _question_banner(question) -> str:
    """The answer a console owes on a far mark (P4d-2b spec §6.2). The buttons that give
    it are b3a-2's; this says what is owed."""
    return _banner(
        "warn",
        "Confirm",
        f"{_e(question.said)} · answer "
        f"{' or '.join(_e(answer) for answer in question.answers)} "
        f"(session {_e(question.session_id)})",
    )


def _idle_banners(frame: Idle, view: View) -> str:
    """A refused frame, then every stranded animal, then a question owed -- where a
    person looks first. The form that opens a session is b3a-2's."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    for found in frame.stranded:
        text = (
            f"session {_e(found.session_id)}: its welfare record cannot be read, so its "
            f"animal's return cannot be checked; no session opens until the file is "
            f"repaired and the return recorded"
            if found.left_at is None
            else f"{_e(found.subject)} left its cage at {_clock_time(found.left_at)} in "
            f"session {_e(found.session_id)}, and its return is not recorded; no session "
            f"opens until it is"
        )
        out.append(_banner("crit", "Stranded", text))
    if frame.question is not None:
        out.append(_question_banner(frame.question))
    if not out:
        out.append(_banner("info", "Idle", "no session open"))
    return "".join(out)


def _idle_refusals(frame: Idle) -> str:
    rows = []
    if frame.refusals_dropped:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(frame.refusals_dropped)} earlier refusal(s) not shown: only the most "
            f"recent {len(frame.refusals)} are kept</span></div>"
        )
    for refusal in frame.refusals:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(refusal.name)} by {_e(refusal.by)}: {_e(refusal.why)}</span></div>"
        )
    return "".join(rows) or '<span class="nm">nothing refused</span>'


def _idle(frame: Idle, view: View) -> dict[str, str]:
    """The page while `wlx taskd` has no session open (P4d-2b spec §6.1: "the page
    shows *no session open*"): every pane as before any frame, except the pill, the
    header, the banners, the controls, *wl-works sees* (`/health` as it would be sent
    for this frame, stranded animals included) and the refusals."""
    panes = fragments(None, view)
    panes["state"] = '<span class="pill neutral" data-state="idle">no session open</span>'
    panes["head-id"] = '<span class="nm">no session open</span>'
    panes["banners"] = _idle_banners(frame, view)
    panes["controls"] = '<span class="nm">controls · no session open</span>'
    panes["rt-health"] = _health_pane(frame, view)
    panes["rt-changes"] = _idle_refusals(frame)
    return panes
```

In `_state`, as its first check after `frame is None`:

```python
    if frame.phase == "between_runs":
        label = (
            "between runs"
            if frame.run_index is None
            else f"between runs · run {frame.run_index} ended · {frame.stop_kind}"
        )
        tone = "crit" if frame.stop_kind in ("fault", "limit") else "neutral"
        return f'<span class="pill {tone}" data-state="between-runs">{_e(label)}</span>'
```

In `_head`, `("Block", _e(frame.block), "")` becomes `("Block", "—" if frame.block is None else _e(frame.block), "")`, and add `("Run", "—" if frame.run_index is None else _e(frame.run_index), ""),` before it. In `_banners`, after the duration warning: `if frame.question is not None: out.append(_question_banner(frame.question))`, and the stop reason's tag becomes `f"Run {frame.run_index} ended" if frame.phase == "between_runs" and frame.run_index is not None else "Ended"`. In `_controls`, before the `stop_kind` check: `if frame.phase == "between_runs": return '<span class="nm">controls · no run in progress</span>'`. In `_setup`, `("task", _e(frame.task))` becomes `("task", '<span class="nm">no run yet</span>' if frame.task is None else _e(frame.task))`. In `_end`, the reason becomes:

```python
    reason = (
        _e(frame.stopped_because)
        if frame.stopped_because
        else '<span class="nm">no run yet</span>'
        if frame.phase == "between_runs"
        else '<span class="nm">still running</span>'
    )
```

- [ ] **Step 5: `/health`**

In `wl_xcon/health.py`, import `Idle`. Then:

```python
def expects_frames(frame: Telemetry | Idle | None) -> bool:
    """Whether more frames are due: the loop is running, a rig session is still
    publishing its out-of-cage clock until the return (P4d-2a), or `wlx taskd` sent it,
    which publishes between runs and while idle (the b3a-1 plan, decision 9). Only then
    is silence a stale stream. The page's stale timer runs on the same answer."""
    if frame is None:
        return False
    if isinstance(frame, Idle):
        return True
    return frame.service or frame.stop_kind is None or frame.phase == "awaiting_return"
```

In `verdict`, add as its first statement:

```python
    if isinstance(frame, Idle):
        # No session: `ok`, unless a frame was refused, the stream went quiet, or an
        # animal's return is missing -- `degraded` until it is recorded, as a session
        # ended on its limit is (spec §3's table; the b3a-1 plan, decision 10).
        stale = _stale(frame, frame_age_s, stale_after_s)
        return "degraded" if rejected or stale or frame.stranded else "ok"
```

and add to its docstring's table: "- `wlx taskd` idle: `ok`; `degraded` while a stranded session exists, a frame was refused, or the stream went quiet".

`_state_text` becomes:

```python
def _state_text(frame: Telemetry | Idle) -> str:
    if isinstance(frame, Idle):
        text = "idle · no session open"
        return f"{text} · an animal's return is not recorded" if frame.stranded else text
    if frame.phase == "between_runs":
        if frame.run_index is None:
            return "between runs · no run yet"
        return (
            f"between runs · run {frame.run_index} ended ({frame.stop_kind}): "
            f"{frame.stopped_because}"
        )
    ...  # the rest unchanged
```

In `_featured`, after `if frame is None: ...`:

```python
    if isinstance(frame, Idle):
        if frame.stranded:
            return "stranded"
        return "refused" if rejected else "last_frame" if stale else "state"
```

In `readings`, replace `if frame is None: ... else:` with a three-way branch, the new middle one:

```python
    elif isinstance(frame, Idle):
        rows = [
            ("session", "Session", "none open · wlx taskd is idle"),
            ("state", "State", _state_text(frame)),
            *refused,
        ]
        if frame.stranded:
            rows.append(
                (
                    "stranded",
                    "Stranded",
                    " · ".join(
                        f"{found.session_id} · {found.subject or 'record unreadable'} · "
                        f"return not recorded"
                        for found in frame.stranded
                    ),
                )
            )
        rows.append(("last_frame", "Last frame", _age_text(frame_age_s)))
```

and in the session branch's first row, `{frame.task}` becomes `{frame.task if frame.task is not None else 'no run yet'}`.

- [ ] **Step 6: `wlx serve`'s hub**

In `wl_xcon/serve.py`'s `Hub.offer`, replace the rate block inside the lock with:

```python
            previous = self._frame
            if isinstance(frame, _link.Idle):
                # No session, so no trials and no rate (P4d-2b spec §6.1).
                self._points.clear()
                self._newest = None
            else:
                if (
                    previous is None
                    or isinstance(previous, _link.Idle)
                    or previous.session_id != frame.session_id
                    or frame.trial_index < previous.trial_index
                ):
                    self._points.clear()
                if not self._points or now - self._points[-1][0] >= RATE_SAMPLE_S:
                    self._points.append((now, frame.trial_index))
                while now - self._points[0][0] > RATE_WINDOW_S:
                    self._points.popleft()
                self._newest = (now, frame.trial_index)
            self._frame, self._received, self._rejected = frame, now, None
            subscribers = list(self._subscribers)
```

and add to its docstring: "An `Idle` frame is held like any other and empties the rate window; a new run, whose trial count starts again, restarts it too." Annotate `offer` and `_frame` as `Telemetry | Idle`.

- [ ] **Step 7: Run them to verify they pass**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_cli.py tests/test_web.py tests/test_health.py tests/test_serve.py -q -p no:cacheprovider`
Expected: PASS, the health contract tests included (each new case is `HealthResponse`).

- [ ] **Step 8: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add wl_xcon/cli.py wl_xcon/web.py wl_xcon/health.py wl_xcon/serve.py tests/_frames.py tests/test_cli.py tests/test_web.py tests/test_health.py tests/test_serve.py
git commit -m "Show no session, and between runs, honestly on every console"
```

---

### Task 6: Pre-flight under S9a §10's rule (`preflight.py`)

**Files:**
- Create: `wl_xcon/preflight.py`, `tests/test_preflight.py`
- Modify: `tools/mutation_gate.py` (`RETURNS`), `docs/design/architecture.md` (the welfare-critical list)

**Interfaces:**
- Consumes: Task 4's `Preflight`, `PreflightItem`.
- Produces: `PASS, UNKNOWN, FAIL`; item names `TASK_CHECKS = "task checks"`, `STARTING_VALUES = "starting values"`, `BOUNDED_CONFIG = "bounded config"`, `SUBJECT_SETTINGS = "subject settings"`, `OUT_OF_CAGE_MARK = "out of cage"`, `PUMP_CALIBRATION = "pump calibration"`, `EYE_TRACKER = "eye tracker"`; `task(path: Path, allocation, geometry) -> tuple[PreflightItem, Trial | None]`; `values(trial: Trial | None, given: dict) -> PreflightItem`; `files(bounds_path: Path, subject: str, settings_path: Path | None, rig: Rig) -> list[PreflightItem]`; `out_of_cage(session) -> PreflightItem`; `unmeasured() -> list[PreflightItem]`; `gate(preflight: Preflight, acknowledged) -> str | None`; `rows(preflight: Preflight, by: str) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_preflight.py`:

```python
"""Pre-flight (P4d-2b spec §6.2) under S9a §10's one rule (PI, 2026-09-19): fail blocks,
unknown proceeds only on a named acknowledgement written into the record, pass proceeds."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from _rig import DIRECT, RIG, STEREOSCOPE
from _sessions import WALL, session
from wl_xcon import preflight
from wl_xcon.cli import _load_allocation, _load_trial
from wl_xcon.link import Preflight, PreflightItem
from wl_xcon.welfare import Deployment

ALLOCATION = _load_allocation(Path("tasks/allocation.py"))
TASK = Path("tasks/fixation_detection.py")


def test_a_task_that_passes_its_checks_in_the_sessions_setup_passes():
    item, trial = preflight.task(TASK, ALLOCATION, DIRECT)

    assert (item.name, item.result) == ("task checks", "pass")
    assert "direct view" in item.said and trial is not None


def test_a_task_written_for_the_other_setup_fails_naming_the_finding():
    item, _ = preflight.task(TASK, ALLOCATION, STEREOSCOPE)

    assert item.result == "fail" and "wrong-setup" in item.said


@pytest.mark.parametrize(
    ("text", "said"),
    [("x = 1\n", "defines 0 trials"), ("raise ValueError('broken on purpose')\n", "did not load")],
)
def test_a_task_file_that_does_not_load_fails_rather_than_raising(tmp_path, text, said):
    bad = tmp_path / "bad.py"
    bad.write_text(text)

    item, trial = preflight.task(bad, ALLOCATION, DIRECT)

    assert item.result == "fail" and said in item.said and trial is None


@pytest.mark.parametrize(
    ("given", "result", "said"),
    [
        ({"fix_hold": 0.3}, "pass", "each declared and in range"),
        ({"fix_hold": 99.0}, "fail", "outside"),
        ({"no_such": 1.0}, "fail", "not a parameter this task declares"),
        ({"fix_hold": "long"}, "fail", "takes a number"),
    ],
)
def test_starting_values_are_checked_against_the_tasks_declarations(given, result, said):
    item = preflight.values(_load_trial(TASK), given)

    assert (item.name, item.result) == ("starting values", result) and said in item.said


def test_the_animals_files_pass_when_they_load_and_name_it(tmp_path):
    folder = tmp_path / "REFERENCE"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    shutil.copy("tasks/reference_subject.py", folder / "settings.py")

    items = preflight.files(folder / "bounds.py", "REFERENCE", folder / "settings.py", RIG)

    assert [(i.name, i.result) for i in items] == [
        ("bounded config", "pass"), ("subject settings", "pass"),
    ]


def test_the_animals_files_fail_when_they_name_another_or_do_not_load(tmp_path):
    folder = tmp_path / "B"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    (folder / "settings.py").write_text("SETTINGS = None\n")

    items = preflight.files(folder / "bounds.py", "B", folder / "settings.py", RIG)

    assert [i.result for i in items] == ["fail", "fail"]
    assert "'REFERENCE'" in items[0].said and "must define SETTINGS" in items[1].said


def test_the_out_of_cage_item_passes_while_the_mark_is_in_and_the_limit_is_not_reached(tmp_path):
    made = session(tmp_path)
    made.left_cage(at=WALL - 60)

    item = preflight.out_of_cage(made)

    assert (item.name, item.result) == ("out of cage", "pass")


def test_the_out_of_cage_item_fails_with_no_departure_or_past_the_limit(tmp_path):
    """Spec §6.1: "reached between runs, it refuses a new run"."""
    unmarked = session(tmp_path / "a")
    past = session(tmp_path / "b", out_of_cage=600.0)
    past.left_cage(at=WALL - 300)
    past.wall_clock = lambda: WALL + 400

    assert preflight.out_of_cage(unmarked).result == "fail"
    item = preflight.out_of_cage(past)
    assert item.result == "fail" and "ceiling" in item.said and "End session" in item.said


def test_what_nothing_measures_is_unknown_and_says_what_it_waits_for():
    """S9a §10: an absent pump calibration is acknowledgeable only while no real pump
    driver exists -- a dated claim, named so it can be found (V10)."""
    items = preflight.unmeasured()

    assert [(i.name, i.result) for i in items] == [
        ("pump calibration", "unknown"), ("eye tracker", "unknown"),
    ]
    assert "V10" in items[0].said and "driver" in items[0].said
    assert "V3" in items[1].said


def _checked(*results: str) -> Preflight:
    return Preflight(
        "t.py", tuple(PreflightItem(f"item {i}", r, f"said {i}") for i, r in enumerate(results))
    )


def test_the_gate_lets_every_pass_through():
    assert preflight.gate(_checked("pass", "pass"), ()) is None


def test_the_gate_blocks_any_fail_even_when_every_unknown_is_acknowledged():
    why = preflight.gate(_checked("pass", "fail", "unknown"), ("item 2",))

    assert why.startswith("pre-flight failed") and "item 1: said 1" in why


def test_the_gate_lets_an_unknown_through_only_when_it_is_acknowledged_by_name():
    assert "item 1" in preflight.gate(_checked("unknown", "unknown"), ("item 0",))
    assert preflight.gate(_checked("unknown", "unknown"), ("item 0", "item 1")) is None


def test_the_gate_fails_closed_on_a_result_it_does_not_know():
    assert preflight.gate(_checked("pass", "maybe"), ()).startswith("pre-flight failed")


def test_the_record_says_who_acknowledged_each_unknown_and_no_one_else():
    rows = preflight.rows(_checked("pass", "unknown"), "jake (box, unverified)")

    assert [(r["name"], r["result"], r["acknowledged_by"]) for r in rows] == [
        ("item 0", "pass", None),
        ("item 1", "unknown", "jake (box, unverified)"),
    ]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_preflight.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'preflight' from 'wl_xcon'`.

- [ ] **Step 3: Implement `wl_xcon/preflight.py`**

```python
"""Pre-flight: what is checked before a run starts (P4d-2b spec §6.2), under S9a §10's
one rule.

**The rule** (PI, 2026-09-19): **fail** blocks; **unknown** proceeds only on an
acknowledgement, by name, written into the record (`runs.jsonl`); **pass** proceeds. The
failure it is shaped against is a gate that cries wolf and gets clicked through, so it
refuses only on evidence of a problem and records acceptance where evidence is merely
absent. `gate` is the rule; the items are what it is asked about: the task's load-time
checks in the session's setup, its starting values, the animal's bounded config and, in
the stereoscope, its settings, the out-of-cage mark and limit, and the two things
nothing measures yet.

**Welfare-critical: `out_of_cage` and `gate`** (`docs/design/architecture.md`). The first
is what refuses a new run once the out-of-cage limit is reached between runs (spec §6.1);
the second is what lets an unknown through. The other items are ordinary: each is an
item a person reads, and a wrong one fails or passes a run that `taskd` still checks
itself -- `Session.run` refuses a blocking finding and a missing mark on its own.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from wl_xcon.bounds import Exceeded
from wl_xcon.check import check
from wl_xcon.cli import _load_bounds, _load_subject_settings, _load_trial, _setup_words
from wl_xcon.geometry import Rig
from wl_xcon.link import Preflight, PreflightItem
from wl_xcon.task import Trial

PASS, UNKNOWN, FAIL = "pass", "unknown", "fail"

#: The items' names, as a person acknowledges them.
TASK_CHECKS = "task checks"
STARTING_VALUES = "starting values"
BOUNDED_CONFIG = "bounded config"
SUBJECT_SETTINGS = "subject settings"
OUT_OF_CAGE_MARK = "out of cage"
PUMP_CALIBRATION = "pump calibration"
EYE_TRACKER = "eye tracker"


def task(path: Path, allocation, geometry) -> tuple[PreflightItem, Trial | None]:
    """The task's load-time checks in the session's setup: **fail** if it will not load
    or any finding blocks. Returns the loaded `Trial` too, for `values`."""
    try:
        trial = _load_trial(path)
    except SystemExit as refused:
        return PreflightItem(TASK_CHECKS, FAIL, str(refused)), None
    except Exception as broken:  # noqa: BLE001 -- a task file is code; its fault is this item's
        return (
            PreflightItem(
                TASK_CHECKS, FAIL, f"{path.name} did not load: {type(broken).__name__}: {broken}"
            ),
            None,
        )
    blocking = [f for f in check(trial, allocation, geometry=geometry) if f.blocking]
    if blocking:
        return (
            PreflightItem(
                TASK_CHECKS, FAIL, "; ".join(f"{f.code}: {f.detail}" for f in blocking)
            ),
            trial,
        )
    return (
        PreflightItem(
            TASK_CHECKS,
            PASS,
            f"{path.name} passes its load-time checks in "
            f"{_setup_words(geometry.view, geometry.half_ipd_cm)}",
        ),
        trial,
    )


def values(trial: Trial | None, given: dict) -> PreflightItem:
    """A run's starting values against the task's own declarations: **fail** for a name
    it does not declare, a word where it takes a number, a number outside its range, or
    a choice it does not offer. Starting values are the task's own (spec §6.2); they
    arrive from a console, so they are checked where `Session.set` checks a live one."""
    if trial is None:
        return PreflightItem(
            STARTING_VALUES, FAIL, "the task did not load, so its values cannot be checked"
        )
    declared = {param.name: param for param in trial.params}
    wrong = []
    for name, value in given.items():
        param = declared.get(name)
        if param is None:
            wrong.append(f"{name!r} is not a parameter this task declares")
        elif param.choices:
            if value not in param.choices:
                wrong.append(f"{name!r} may only be one of {param.choices}")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            wrong.append(f"{name!r} takes a number ({param.unit}), and {value!r} is not one")
        elif (param.low is not None and value < param.low) or (
            param.high is not None and value > param.high
        ):
            wrong.append(
                f"{name!r} is declared over [{param.low}, {param.high}] {param.unit} and "
                f"{value} is outside it"
            )
    if wrong:
        return PreflightItem(STARTING_VALUES, FAIL, "; ".join(wrong))
    return PreflightItem(
        STARTING_VALUES, PASS, f"{len(given)} starting value(s), each declared and in range"
    )


def files(
    bounds_path: Path, subject: str, settings_path: Path | None, rig: Rig
) -> list[PreflightItem]:
    """The animal's files, read again (spec §6.2: "fail if refused"): the bounded config
    loads and names this animal, and in the stereoscope its settings load, name it, and
    give a half-IPD this rig is built for. **The session runs under what it loaded when
    it opened**; a file that no longer loads or names another animal is a sign
    something about this animal's files has gone wrong since, and blocks a new run."""
    items = []
    try:
        found = _load_bounds(bounds_path)
        if found.subject != subject:
            raise SystemExit(
                f"{bounds_path} now holds {found.subject!r}'s bounded config, and this "
                f"session is {subject!r}'s"
            )
        items.append(
            PreflightItem(
                BOUNDED_CONFIG,
                PASS,
                f"{bounds_path} loads and names {subject!r}; the session runs under the "
                f"config it loaded when it opened",
            )
        )
    except SystemExit as refused:
        items.append(PreflightItem(BOUNDED_CONFIG, FAIL, str(refused)))
    except Exception as broken:  # noqa: BLE001 -- a bounds file is code
        items.append(
            PreflightItem(BOUNDED_CONFIG, FAIL, f"{bounds_path} did not load: {type(broken).__name__}: {broken}")
        )
    if settings_path is not None:
        try:
            half = _load_subject_settings(settings_path, subject).half_ipd_cm
            rig.stereoscope(half)
            items.append(
                PreflightItem(
                    SUBJECT_SETTINGS,
                    PASS,
                    f"{settings_path} loads, names {subject!r}, and gives a half-IPD of "
                    f"{half:g} cm this stereoscope is built for",
                )
            )
        except (SystemExit, ValueError) as refused:
            items.append(PreflightItem(SUBJECT_SETTINGS, FAIL, str(refused)))
        except Exception as broken:  # noqa: BLE001 -- a settings file is code
            items.append(
                PreflightItem(SUBJECT_SETTINGS, FAIL, f"{settings_path} did not load: {type(broken).__name__}: {broken}")
            )
    return items


def out_of_cage(session) -> PreflightItem:
    """**Welfare-critical.** The out-of-cage mark and limit, on the session's own clock:
    **fail** when `welfare.preflight` refuses (no departure, the animal recorded home, a
    head-fixed session not fixed) or `welfare.must_stop` says the limit is reached --
    spec §6.1: "reached between runs, it refuses a new run, and the page asks for the
    return". `welfare` decides both; this reads them."""
    wall = session.wall_now()
    try:
        session.welfare.preflight(wall)
    except Exceeded as refused:
        return PreflightItem(OUT_OF_CAGE_MARK, FAIL, str(refused))
    stop = session.welfare.must_stop(wall)
    if stop is not None:
        return PreflightItem(
            OUT_OF_CAGE_MARK,
            FAIL,
            f"{stop}; no run starts past the limit -- end the session (End session) and "
            f"record the animal's return",
        )
    warning = session.welfare.approaching_limit(wall)
    return PreflightItem(
        OUT_OF_CAGE_MARK,
        PASS,
        warning or "the departure is marked and the out-of-cage limit is not reached",
    )


def unmeasured() -> list[PreflightItem]:
    """The two items spec §6.2 names as **unknown until measured**. Each says what it
    waits for, so the next reader can find it rather than believe it (CLAUDE.md)."""
    return [
        PreflightItem(
            PUMP_CALIBRATION,
            UNKNOWN,
            "no pump calibration has been measured (V10), so no millilitre is known to "
            "be what the valve gives; this rig's pump is the simulator. Acknowledgeable "
            "only because no real pump driver exists yet -- when one is written, S9a §10 "
            "says this rule must be revisited before it ships",
        ),
        PreflightItem(
            EYE_TRACKER,
            UNKNOWN,
            "nothing reports the eye tracker's health yet (V3, the eye loop's stall "
            "census, is the measurement it waits on); this rig's gaze is the simulated "
            "animal's",
        ),
    ]


def gate(preflight: Preflight, acknowledged: Collection[str]) -> str | None:
    """**Welfare-critical: S9a §10's one rule.** Why the run may not start, or `None`.

    **Any fail blocks**, acknowledged or not. **Each unknown needs its name in
    `acknowledged`**, which is what a person sent; one not named blocks, and the
    sentence names it. **A result that is neither pass nor unknown counts as a fail**,
    so an item this rule does not know closes the gate rather than opening it."""
    failed = [item for item in preflight.items if item.result not in (PASS, UNKNOWN)]
    if failed:
        return "pre-flight failed, so the run does not start: " + "; ".join(
            f"{item.name}: {item.said}" for item in failed
        )
    owed = [
        item.name
        for item in preflight.items
        if item.result == UNKNOWN and item.name not in acknowledged
    ]
    if owed:
        return (
            f"pre-flight has {len(owed)} unknown item(s) nobody has acknowledged: "
            f"{', '.join(owed)}. Each proceeds only on a named acknowledgement written "
            f"into the record (S9a §10); acknowledge them by name to start"
        )
    return None


def rows(preflight: Preflight, by: str) -> list[dict]:
    """The pre-flight as `runs.jsonl` records it: every item, and **who acknowledged
    each unknown one** -- the person who started the run, since the gate let nothing
    through that they did not name."""
    return [
        {
            "name": item.name,
            "result": item.result,
            "said": item.said,
            "acknowledged_by": by if item.result == UNKNOWN else None,
        }
        for item in preflight.items
    ]
```

- [ ] **Step 4: The gate and the architecture**

`tools/mutation_gate.py`'s `RETURNS` gains `"preflight": "None",`. In `docs/design/architecture.md`, after the `marks.py` sentences Task 1 wrote, add: "**`preflight.out_of_cage` and `preflight.gate`** (P4d-2b b3a): the first is what refuses a new run once the out-of-cage limit is reached between runs, and the second is S9a §10's rule — fail blocks, an unknown proceeds only on a named acknowledgement written into `runs.jsonl` — and a mistake in it lets a run start that should not."

- [ ] **Step 5: Run them to verify they pass**

Run: `python3 -m pytest tests/test_preflight.py tests/test_mutation_gate.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add wl_xcon/preflight.py tests/test_preflight.py tools/mutation_gate.py docs/design/architecture.md
git commit -m "Check a run before it starts: fail blocks, unknown needs a named acknowledgement"
```

---

### Task 7: The service — sessions, the stranded rule, and `wlx taskd`

**Welfare-critical: `stranded.py`, `Welfare.restore_departure`, `Service._open`, `Service._end`, `Service._close_stranded`.**

**Files:**
- Create: `wl_xcon/stranded.py`, `wl_xcon/service.py`, `tests/test_stranded.py`, `tests/test_service.py`
- Modify: `wl_xcon/welfare.py` (`Welfare.restore_departure`; the docstrings of `Rig` and `_refuse_unconfirmed`), `wl_xcon/taskd.py` (docstrings only, Step 7), `wl_xcon/cli.py` (the `taskd` parser and branch), `tests/test_welfare.py` (`ENTRY_POINTS`, and tests), `docs/superpowers/specs/2026-08-31-S8-session-management-design.md` (§5.2d's two new rows and counts), `tools/mutation_gate.py`, `docs/design/architecture.md`

**Interfaces:**
- Consumes: Task 1's `marks.page_departure`, `depart`, `record_departure`, `page_return`, `Owed`; Task 3's `Session(service=True)`, `end_runs`, `close`, `stamp`, `refuse`, `receive`, `publish`, `offered_tasks`, `question`, `return_not_recorded(why, how)`; Task 4's `Idle.of`, `Stranded`, `Question`, `OpenSession`, `EndSession`, `SetParameter`.
- Produces: `Welfare.restore_departure(at: float) -> None`; `stranded.find(root: Path) -> list[link.Stranded]`, `stranded.Restored(directory, subject, welfare, wall_now)`, `stranded.restore(found, bounds, directory, wall_now) -> Restored`, `stranded.RESTORED`; `service.HOUSEKEEPING_S`, `FRAMEWORK_CODES`, `FRAME_PERIOD`; `service.Service(*, rig, rig_path, subjects, tasks, allocation, allocation_path, root, link, card=SimulatedCard, pump=SimulatedPump, seed=_fresh_seed, wall_clock=None)` with `.session`, `.stranded`, `.question`, `.refusals`, `.link`, `.root`, `wall_now()`, `serve(stop)`, `step()`, `publish()`, `shutdown()`; `service.run(args) -> int`; `wlx taskd`.

- [ ] **Step 1: Write the failing tests**

`tests/test_welfare.py`: add to `ENTRY_POINTS` in the clocks section:

```python
    # A stranded session's departure, read back from its record to take its return
    # (P4d-2b b3a): an instant like the marks it restores.
    "Welfare.restore_departure.at": (INSTANT, lambda v: _welfare().restore_departure(v)),
```

and:

```python
def test_a_restored_departure_is_one_a_return_can_close_even_past_the_ceiling():
    """P4d-2b spec §6.1: an animal out of its cage is never forgotten because a process
    died. `left_cage` would refuse a departure past the ceiling; the restored one is read
    back, not decided, so its return can still be taken under every return rule."""
    welfare = _chaired_welfare()
    welfare.restore_departure(WALL_NOW - 50_000.0)  # past the 43,200 s ceiling

    welfare.returned_to_cage(WALL_NOW - 60.0, wall_now=WALL_NOW)

    assert welfare.out_of_cage_seconds(WALL_NOW) == 50_000.0 - 60.0


def test_a_restored_departure_is_refused_where_a_departure_cannot_be():
    with pytest.raises(Exceeded, match="is at home, so no departure can be restored"):
        _home_welfare().restore_departure(WALL_NOW)
    held = _chaired_welfare()
    held.restore_departure(WALL_NOW)
    with pytest.raises(Exceeded, match="already holds a departure"):
        held.restore_departure(WALL_NOW)
```

**S8 §5.2d indexes every `raise` in the two welfare-critical files, and a test counts them** (`test_every_refusal_has_a_row_in_the_table_and_every_row_still_greps`). `restore_departure` adds two, so in `docs/superpowers/specs/2026-08-31-S8-session-management-design.md` §5.2d add after the `is already recorded as out of its cage at` row:

```markdown
| `is at home, so no departure can be restored for it` | A stranded session's departure read back into a cage-side session: the declaration and the mark disagreeing, reached from a restart (P4d-2b b3a) | S13 §4.0; P4d-2b spec §6.1 |
| `already holds a departure, at …, so a recorded one cannot be restored beside it` | Two departures on one interval, the shorter winning -- `left_cage`'s re-arm refusal, for the departure a restart reads back | §5.2 item 4; P4d-2b spec §6.1 |
```

and change the prose counts by hand, since the test cannot see them: "`welfare.py` has **twenty-nine** `raise` sites" becomes **thirty-one**, and "**Thirty-four refusals.** ... **and thirty-two are structural.**" becomes **Thirty-six** and **thirty-four**.

`tests/test_stranded.py`:

```python
"""Stranded sessions (P4d-2b spec §6.1): found from their records after a restart, and
their returns taken under `welfare`'s rules."""

from __future__ import annotations

import json

import pytest

from _sessions import WALL, bounds
from wl_xcon import marks, stranded
from wl_xcon.bounds import Exceeded
from wl_xcon.link import Stranded
from wl_xcon.record import welfare_note


def _notes(root, session_id, *rows):
    directory = root / session_id / "xcon"
    directory.mkdir(parents=True)
    for kind, at in rows:
        welfare_note(directory, kind=kind, subject="A", was=at, now=at, reason="",
                     by="jake", how="t", recorded_at=at)
    return directory


def test_a_session_with_a_departure_and_no_return_is_stranded(tmp_path):
    _notes(tmp_path, "2027-01-13_01", ("session opened", WALL - 900), ("departure", WALL - 900))
    _notes(tmp_path, "2027-01-13_02", ("departure", WALL - 800), ("returned", WALL - 100))
    _notes(tmp_path, "2027-01-13_03", ("departure", WALL - 700), ("return not recorded", WALL - 600))
    (tmp_path / "2027-01-13_04").mkdir()

    assert stranded.find(tmp_path) == [
        Stranded("2027-01-13_01", "A", WALL - 900),
        Stranded("2027-01-13_03", "A", WALL - 700),
    ]


def test_a_record_with_a_torn_line_is_stranded_and_unreadable(tmp_path):
    directory = _notes(tmp_path, "2027-01-13_01", ("departure", WALL - 900), ("returned", WALL - 60))
    with (directory / "welfare_notes.jsonl").open("a") as handle:
        handle.write('{"kind": "depart')

    assert stranded.find(tmp_path) == [Stranded("2027-01-13_01", "", None)]


def test_no_root_finds_nothing(tmp_path):
    assert stranded.find(tmp_path / "missing") == []


def test_a_restored_session_takes_its_return_under_the_rules_and_writes_its_rows(tmp_path):
    directory = _notes(tmp_path, "2027-01-13_01", ("departure", WALL - 3 * 3600))
    found = stranded.find(tmp_path)[0]
    restored = stranded.restore(found, bounds(), directory, lambda: WALL)

    with pytest.raises(marks.Owed):
        marks.take_return(restored, WALL - 2 * 3600, confirmed=False, by="jake", how="the page")
    with pytest.raises(Exceeded, match="having left it at"):
        marks.take_return(restored, WALL - 4 * 3600, confirmed=True, by="jake", how="the page")
    marks.take_return(restored, WALL - 2 * 3600, confirmed=True, by="jake", how="the page")

    rows = [json.loads(l) for l in (directory / "welfare_notes.jsonl").read_text().splitlines()]
    assert [row["kind"] for row in rows] == ["departure", "returned", "return confirmed"]
    assert rows[1]["reason"] == stranded.RESTORED
    assert stranded.find(tmp_path) == []


def test_an_unreadable_or_another_animals_stranded_session_is_refused(tmp_path):
    with pytest.raises(Exceeded, match="cannot be read"):
        stranded.restore(Stranded("x", "", None), bounds(), tmp_path, lambda: WALL)
    with pytest.raises(Exceeded, match="'B'"):
        stranded.restore(Stranded("x", "A", WALL), bounds(subject="B"), tmp_path, lambda: WALL)
```

`tests/test_service.py` — the unit part (the end-to-end part is Task 9's):

```python
"""`wlx taskd` -- the rig service (P4d-2b spec §6): one animal's session at a time, any
number a day, opened, run and ended by a console's commands, and nothing opened while an
animal is stranded. The unit tests drive `Service.step` over an in-process link with an
injected wall; the end-to-end tests at the bottom drive a real service over ZeroMQ."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from _rig import PATH as RIG_FILE
from _rig import RIG
from _sessions import WALL, typed
from _zmq_release import _every_zmq_context_released  # noqa: F401
from wl_xcon.cli import _load_allocation, main
from wl_xcon.link import (
    EndSession,
    Idle,
    OpenSession,
    Pause,
    Simulated,
    Stranded,
    Telemetry,
)
from wl_xcon.record import welfare_note
from wl_xcon.service import Service

ALLOCATION = "tasks/allocation.py"
TWELVE_HOURS = Path("tasks/twelve_hour_bounds.py")
TEN_MINUTES = Path("tasks/reference_bounds.py")
TASK = "fixation_detection.py"
BY = "jake (box, unverified)"


class _Wall:
    """The service's wall, moved by a test: `WALL` until then."""

    def __init__(self) -> None:
        self.at = WALL

    def __call__(self) -> float:
        return self.at


def _folders(tmp_path, bounds: Path = TWELVE_HOURS, animals=("REFERENCE",)):
    """`--subjects`, `--tasks` and `--root` for a service: each animal a folder with its
    bounds (the reference file, renamed for it), `REFERENCE` with its settings too, and
    one task. **Copies, never imports**: a file `--subjects` or `--tasks` points at must
    load by path under the installed `wlx`, as `tests/_rig.py`'s docstring says."""
    subjects, tasks, root = tmp_path / "subjects", tmp_path / "tasks", tmp_path / "sessions"
    for animal in animals:
        (subjects / animal).mkdir(parents=True)
        (subjects / animal / "bounds.py").write_text(
            bounds.read_text().replace('subject="REFERENCE"', f'subject="{animal}"')
        )
    if "REFERENCE" in animals:
        shutil.copy("tasks/reference_subject.py", subjects / "REFERENCE" / "settings.py")
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    root.mkdir()
    return subjects, tasks, root


def _made(folders, *, link=None, wall=None, seed=lambda: 7) -> Service:
    subjects, tasks, root = folders
    return Service(
        rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=link if link is not None else Simulated(), seed=seed,
        wall_clock=wall if wall is not None else _Wall(),
    )


def _service(tmp_path, *, bounds=TWELVE_HOURS, animals=("REFERENCE",), link=None, wall=None):
    return _made(_folders(tmp_path, bounds, animals), link=link, wall=wall)


def _open(**over) -> OpenSession:
    fields = dict(
        by=BY, session_id="2027-01-14_01", animal="REFERENCE", deployment="rig_fixed",
        view="direct", departure=typed(60), delivered_today=0.0, answer=None,
        amend_to=None, amend_reason="",
    )
    fields.update(over)
    return OpenSession(**fields)


def _end(returned: str | None = "now", **over) -> EndSession:
    fields = dict(by=BY, session_id=None, returned=returned, confirm=False)
    fields.update(over)
    return EndSession(**fields)


def _step(service, *commands):
    """One housekeeping pass with `commands` waiting; the last frame it published."""
    for command in commands:
        service.link.queue(command)
    service.step()
    return service.link.published[-1]


def _rows(root, session_id="2027-01-14_01") -> list[dict]:
    path = root / session_id / "xcon" / "welfare_notes.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _kinds(root, session_id="2027-01-14_01") -> list[str]:
    return [row["kind"] for row in _rows(root, session_id)]


def _refused(frame) -> list[str]:
    return [refusal.why for refusal in frame.refusals]


def _strand(root, session_id="2027-01-13_01", left_at=WALL - 3600, *also):
    directory = root / session_id / "xcon"
    directory.mkdir(parents=True)
    for kind in ("departure", *also):
        welfare_note(directory, kind=kind, subject="REFERENCE", was=left_at, now=left_at,
                     reason="", by="jake", how="t", recorded_at=left_at)
    return directory


# --- idle ----------------------------------------------------------------------


def test_with_no_session_open_the_service_publishes_idle_frames_offering_animals_and_tasks(tmp_path):
    service = _service(tmp_path, animals=("B", "REFERENCE"))

    frame = _step(service)

    assert isinstance(frame, Idle)
    assert (frame.phase, frame.animals, frame.offered_tasks) == ("idle", ("B", "REFERENCE"), (TASK,))
    assert (frame.stranded, frame.question, frame.refusals) == ((), None, ())


def test_with_no_session_a_run_command_or_a_mark_is_refused_and_said(tmp_path):
    link = Simulated()
    link.marks.append(4)
    service = _service(tmp_path, link=link)

    frame = _step(service, Pause(by=BY))

    assert [(r.name, r.why) for r in frame.refusals] == [
        ("mark", "no session is open, so the mark was not recorded"),
        ("pause", "no session is open, so a command for a run is not applied; open a session first"),
    ]


# --- open -----------------------------------------------------------------------


def test_open_marks_the_departure_opens_the_session_and_waits_between_runs(tmp_path):
    service = _service(tmp_path)

    frame = _step(service, _open())

    assert isinstance(frame, Telemetry)
    assert (frame.phase, frame.service, frame.run_index) == ("between_runs", True, None)
    assert (frame.session_id, frame.offered_tasks) == ("2027-01-14_01", (TASK,))
    assert _kinds(service.root) == ["departure", "session opened"]
    assert service.session.card.codes == [4128], "head fixed once, as the session opens"
    config = json.loads((service.root / "2027-01-14_01" / "xcon" / "config.json").read_text())
    assert config["service"] is True and config["subject"] == "REFERENCE"


def test_a_session_id_or_animal_that_is_not_one_folder_name_is_refused_and_nothing_is_written(tmp_path):
    """Review Focus 1: each becomes a path, and arrives over the wire."""
    service = _service(tmp_path)

    for over in ({"session_id": "../2027-01-14_01"}, {"session_id": "a/b"},
                 {"session_id": "."}, {"animal": "../REFERENCE"}):
        frame = _step(service, _open(**over))
        assert isinstance(frame, Idle)
        assert "one folder name" in _refused(frame)[-1], over

    assert list(service.root.iterdir()) == []
    assert not (tmp_path / "2027-01-14_01").exists()


@pytest.mark.parametrize(
    ("over", "said"),
    [
        ({"animal": "C"}, "there is no animal 'C'"),
        ({"view": "stereoscope", "animal": "B"}, "settings"),
        ({"departure": "half past nine"}, "is not a clock time"),
        ({"departure": typed(-3600)}, "in the future"),
        ({"departure": typed(9 * 3600), "answer": "amend", "amend_to": typed(600), "amend_reason": ""}, "no reason"),
        ({"delivered_today": -1.0}, "cannot be negative"),
    ],
)
def test_an_open_that_is_refused_says_why_and_writes_nothing(tmp_path, over, said):
    service = _service(tmp_path, animals=("B", "REFERENCE"))

    frame = _step(service, _open(**over))

    assert isinstance(frame, Idle)
    assert any(said in why for why in _refused(frame)), _refused(frame)
    assert list(service.root.iterdir()) == []
```

```python
def test_an_animal_whose_bounds_name_another_is_refused_naming_both(tmp_path):
    folders = _folders(tmp_path, animals=("REFERENCE",))
    (folders[0] / "C").mkdir()
    shutil.copy(folders[0] / "REFERENCE" / "bounds.py", folders[0] / "C" / "bounds.py")

    frame = _step(_made(folders), _open(animal="C"))

    assert any("'REFERENCE''s bounded config" in why and "'C'" in why for why in _refused(frame))


def test_a_departure_past_the_animals_ceiling_is_refused_without_a_question(tmp_path):
    service = _service(tmp_path, bounds=TEN_MINUTES)

    frame = _step(service, _open(departure=typed(900)))

    assert frame.question is None
    assert any("at or outside the limit" in why for why in _refused(frame))


def test_a_session_id_already_used_under_the_root_is_refused(tmp_path):
    service = _service(tmp_path)
    (service.root / "2027-01-14_01").mkdir()

    frame = _step(service, _open())

    assert any("already used" in why for why in _refused(frame))


def test_a_far_departure_is_asked_confirm_or_amend_and_opens_once_confirmed(tmp_path):
    service = _service(tmp_path)
    far = typed(3 * 3600)

    asked = _step(service, _open(departure=far))

    assert isinstance(asked, Idle)
    assert (asked.question.mark, asked.question.session_id) == ("departure", "2027-01-14_01")
    assert asked.question.answers == ("confirm", "amend")
    assert list(service.root.iterdir()) == [], "the id is still free"

    opened = _step(service, _open(departure=far, answer="confirm"))

    assert opened.phase == "between_runs" and opened.question is None
    rows = _rows(service.root)
    assert [r["kind"] for r in rows] == ["departure", "departure confirmed", "session opened"]
    assert (rows[1]["how"], rows[1]["by"]) == ("confirmed on the page", BY)


def test_a_far_departure_amended_on_the_page_is_marked_at_the_corrected_time(tmp_path):
    service = _service(tmp_path)

    _step(service, _open(departure=typed(9 * 3600), answer="amend",
                         amend_to=typed(600), amend_reason="typed 09:30 for 17:30"))

    rows = _rows(service.root)
    assert [r["kind"] for r in rows] == ["departure", "departure amended", "session opened"]
    assert rows[1]["reason"] == "typed 09:30 for 17:30"
    assert service.session.welfare.left_cage_wall_at == pytest.approx(WALL - 600, abs=1.0)


def test_two_opens_in_one_pass_open_one_session_and_refuse_the_other(tmp_path):
    """Review Focus 3."""
    service = _service(tmp_path, animals=("B", "REFERENCE"))

    frame = _step(service, _open(), _open(session_id="2027-01-14_02", animal="B"))

    assert frame.session_id == "2027-01-14_01"
    assert any("a session is open for 'REFERENCE'" in why for why in _refused(frame))
    assert [p.name for p in service.root.iterdir()] == ["2027-01-14_01"]


# --- end ------------------------------------------------------------------------


def test_end_releases_the_head_takes_the_return_and_goes_back_to_idle(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())
    card = service.session.card

    idle = _step(service, _end())

    assert isinstance(idle, Idle) and service.session is None
    assert service.link.published[-2].phase == "closed", "one closed frame first"
    assert card.codes == [4128, 4129]
    assert _kinds(service.root) == ["departure", "session opened", "returned", "session ended"]


def test_end_without_a_return_waits_for_it_and_refuses_a_run(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    waiting = _step(service, _end(returned=None))

    assert (waiting.phase, waiting.stop_kind) == ("awaiting_return", "operator")
    assert waiting.stopped_because == f"session ended by {BY}, before any run"
    refused = _step(service, Pause(by=BY))
    assert "recorded from the page (End session)" in _refused(refused)[-1]
    assert isinstance(_step(service, _end()), Idle)


def test_a_return_typed_before_the_session_was_ended_is_refused_and_now_closes_it(tmp_path):
    """Review Focus 2: End session pressed after the animal is home, with its real,
    earlier time. The head's release was recorded at the End (plan decision 6), so the
    earlier return is refused with `welfare`'s sentence, and the session waits."""
    wall = _Wall()
    service = _service(tmp_path, wall=wall)
    _step(service, _open(departure=typed(1200)))
    wall.at = WALL + 600

    refused = _step(service, _end(returned=typed(-300)))

    assert refused.phase == "awaiting_return"
    assert any("released from head-fixation" in why for why in _refused(refused))
    assert isinstance(_step(service, _end()), Idle)


def test_a_far_return_is_asked_confirm_or_retype_and_taken_once_confirmed(tmp_path):
    wall = _Wall()
    service = _service(tmp_path, wall=wall)
    _step(service, _open(deployment="rig_chaired", departure=typed(1200)))
    wall.at = WALL + 3 * 3600
    far = typed(-1800)

    asked = _step(service, _end(returned=far))

    assert asked.question.answers == ("confirm", "re-type")
    assert asked.phase == "awaiting_return"
    assert isinstance(_step(service, _end(returned=far, confirm=True)), Idle)
    assert _kinds(service.root)[-3:] == ["returned", "return confirmed", "session ended"]


def test_an_end_with_nothing_open_to_end_is_refused(tmp_path):
    """A double click on End session: the second finds no session, and never touches
    another."""
    service = _service(tmp_path)
    _step(service, _open())
    _step(service, _end())

    frame = _step(service, _end())

    assert "no session is open" in _refused(frame)[-1]


def test_any_number_of_sessions_a_day_each_its_own_animal_and_welfare(tmp_path):
    """Spec §6.1: monkey A in the morning, monkey B in the afternoon, and nothing carries
    from one to the next."""
    service = _service(tmp_path, animals=("B", "REFERENCE"))
    _step(service, _open(delivered_today=5.0))
    first = service.session
    _step(service, _end())

    frame = _step(service, _open(session_id="2027-01-14_02", animal="B", delivered_today=None))

    second = service.session
    assert second is not first and second.welfare is not first.welfare
    assert (frame.subject, frame.fluid_session_ml, frame.fluid_today_ml) == ("B", 0.0, None)
    assert _kinds(service.root, "2027-01-14_01")[-1] == "session ended"
    assert _kinds(service.root, "2027-01-14_02") == ["departure", "session opened"]


# --- between runs ---------------------------------------------------------------


def test_between_runs_a_mark_is_stamped_and_strobed(tmp_path):
    link = Simulated()
    service = _service(tmp_path, link=link)
    _step(service, _open())
    link.marks.append(4)

    frame = _step(service)

    assert frame.controls[-1].said == "mark 1 stamped with no run in progress"
    assert service.session.card.codes[-1] == 4133


# --- stranded -------------------------------------------------------------------


def test_a_stranded_session_found_at_start_refuses_every_open_until_its_return_is_recorded(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2])
    service = _made(folders)

    idle = _step(service)
    assert idle.stranded == (Stranded("2027-01-13_01", "REFERENCE", WALL - 3600),)
    refused = _step(service, _open())
    assert "no session opens while an animal's return is not recorded" in _refused(refused)[-1]

    closed = _step(service, _end(session_id="2027-01-13_01"))

    assert closed.stranded == ()
    assert _kinds(folders[2], "2027-01-13_01") == ["departure", "returned"]
    assert _rows(folders[2], "2027-01-13_01")[-1]["how"] == "the page, after a restart"
    assert _step(service, _open()).phase == "between_runs"


def test_a_session_wlx_run_left_with_its_return_not_recorded_is_stranded(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2], "2027-01-13_01", WALL - 600, "return not recorded")

    assert [s.session_id for s in _made(folders).stranded] == ["2027-01-13_01"]


def test_a_crashed_sessions_torn_last_line_leaves_it_stranded_never_skipped(tmp_path):
    """Review Focus 5: a crash mid-write leaves a line that is not a row. Fail closed:
    the session stays stranded, its return is refused with what to do, and nothing opens."""
    folders = _folders(tmp_path)
    directory = _strand(folders[2])
    with (directory / "welfare_notes.jsonl").open("a") as handle:
        handle.write('{"kind": "retur')
    service = _made(folders)

    assert _step(service).stranded == (Stranded("2027-01-13_01", "", None),)
    refused = _step(service, _end(session_id="2027-01-13_01"))
    assert "cannot be read" in _refused(refused)[-1] and "repair" in _refused(refused)[-1]
    assert _step(service, _open()).phase == "idle"


def test_a_stranded_animal_whose_bounds_file_is_gone_is_refused_saying_so(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2])
    (folders[0] / "REFERENCE" / "bounds.py").unlink()
    service = _made(folders)

    refused = _step(service, _end(session_id="2027-01-13_01"))

    assert "restore it" in _refused(refused)[-1]
    assert service.stranded != []


def test_a_service_stopped_with_a_session_open_leaves_it_stranded_for_the_next(tmp_path):
    folders = _folders(tmp_path)
    service = _made(folders)
    _step(service, _open())

    service.shutdown()

    assert _kinds(folders[2])[-2:] == ["return not recorded", "session ended"]
    assert [s.session_id for s in _made(folders).stranded] == ["2027-01-14_01"]


# --- wlx taskd -----------------------------------------------------------------


def _taskd_args(folders, *extra, link="tcp://127.0.0.1:0,tcp://127.0.0.1:0") -> list[str]:
    subjects, tasks, root = folders
    return [
        "taskd", "--rig", RIG_FILE, "--subjects", str(subjects), "--tasks", str(tasks),
        "--root", str(root), "--link", link, *extra,
    ]


def test_wlx_taskd_refuses_an_allocation_without_the_codes_its_sessions_strobe(tmp_path):
    """Plan decision 12: the provisional allocation, used when `--allocation` is omitted,
    has none of them."""
    with pytest.raises(SystemExit, match="HEAD_FIXED, HEAD_RELEASED, PARAM_CHANGED, RUN_START, RUN_END"):
        main(_taskd_args(_folders(tmp_path)))


def test_wlx_taskd_refuses_a_folder_that_is_not_one_and_a_remote_bind(tmp_path):
    folders = _folders(tmp_path)
    missing = (folders[0], tmp_path / "no-tasks", folders[2])

    with pytest.raises(SystemExit, match="--tasks .* is not a folder"):
        main(_taskd_args(missing, "--allocation", ALLOCATION))
    with pytest.raises(SystemExit, match="refusing to bind"):
        main(_taskd_args(folders, "--allocation", ALLOCATION,
                         link="tcp://0.0.0.0:0,tcp://127.0.0.1:0"))


def test_wlx_taskd_serves_until_interrupted_and_says_what_it_left_open(tmp_path, monkeypatch, capsys):
    folders = _folders(tmp_path)

    def serve(self, stop):
        # This service reads this host's clock, not `WALL`: the departure is typed from it.
        self._open(_open(departure=time.strftime("%Y-%m-%dT%H:%M:%S")))
        raise KeyboardInterrupt

    monkeypatch.setattr(Service, "serve", serve)

    assert main(_taskd_args(folders, "--allocation", ALLOCATION)) == 130
    assert _kinds(folders[2])[-2:] == ["return not recorded", "session ended"]
    assert "the return to the cage was not recorded" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_welfare.py tests/test_stranded.py tests/test_service.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: 'Welfare' object has no attribute 'restore_departure'` and `ImportError: cannot import name 'stranded'`.

- [ ] **Step 3: `Welfare.restore_departure` (welfare-critical)**

In `wl_xcon/welfare.py`, after `left_cage`:

```python
    def restore_departure(self, at: float) -> None:
        """The departure of a session whose process stopped before its return was
        recorded, read back from that session's own `departure` row, so that its return
        can be taken under `returned_to_cage`'s rules (P4d-2b spec §6.1: an animal out of
        its cage is never forgotten because a process died).

        **Not `left_cage`, deliberately.** That refuses a departure at or past the
        ceiling, and a far one nobody confirmed: rules about *taking* a mark, which was
        taken -- and refused or confirmed -- when the row was written. A stranded animal
        is the one likeliest to be past its ceiling by now, and refusing its departure
        would leave its return impossible to record. Nothing about the mark is decided
        here; the instant is read back (`stranded.restore`).

        Refused: a cage-side session, which never left; a departure already held, since
        an interval is opened once; and an instant that is not a real number.
        """
        if self.deployment is Deployment.CAGE_SIDE:
            raise Exceeded(
                f"this session declares subject {self.bounds.subject!r} is at home, so "
                f"no departure can be restored for it"
            )
        if self.left_cage_wall_at is not None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} already holds a departure, at "
                f"{self.left_cage_wall_at}, so a recorded one cannot be restored beside it; "
                f"an interval is opened once"
            )
        _finite("the recorded departure of a stranded session", at)
        self.left_cage_wall_at = at
```

In `Rig`'s docstring, replace the paragraph from "**This closes a reference cycle**" to its end with:

> **This closes a reference cycle** (Ruling 4, fix round 1): `taskd.Session` holds this `Rig` (`self.rig`), and this `Rig` holds `wall_clock`, a bound method whose `__self__` is that same `Session`. `Session` -> `rig` -> `wall_clock` -> `Session` is a cycle no refcount alone collects; only Python's cyclic collector frees a finished session's chain. **`wlx taskd` holds many sessions a day** (P4d-2b b3a), so it collects once as each session closes -- between sessions, never during a run (`service.Service._end`). `wlx run` holds one per process, freed at exit. Managing the collector during a run, CLAUDE.md's hot-path rule, is open for both (docs/backlog.md).

- [ ] **Step 4: `wl_xcon/stranded.py` (welfare-critical)**

```python
"""Sessions an animal was left out of its cage in, found after a restart, and their
returns (P4d-2b spec §6.1: "Nothing is quietly lost to a crash").

**Welfare-critical, the whole module** (`docs/design/architecture.md`). Human review
before merge.

**Found from the record alone.** A session under `--root` is stranded when its
`welfare_notes.jsonl` has a `departure` row with no `returned` row after it: a process
that died, a `wlx run` that ended with `return not recorded`, a `wlx taskd` stopped with
its session open -- each leaves exactly that. **A line that is not a row** -- a crash
mid-write -- **fails closed**: the session is stranded with its departure unknown, and
its return cannot be taken until the file is repaired by hand, since a departure nobody
can read is one no return can be checked against.

**Closed under `welfare`'s rules.** `restore` builds a `Welfare` holding only the
recorded departure (`Welfare.restore_departure`) and wraps it in a `Restored`, which
`marks.take_return` takes as it takes a `Session`: not in the future, not before the
departure, confirmed if far. **Restraint is not reconstructed**: its marks are event
codes on the recording, not rows here, and a head is not held fixed by a process that
has died, so the return is checked as a chaired session's is.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from wl_xcon.bounds import Bounds, Exceeded
from wl_xcon.link import Stranded
from wl_xcon.record import WELFARE_NOTES, XCON_DIRNAME, welfare_note
from wl_xcon.welfare import Absent as NoPump
from wl_xcon.welfare import Deployment, Welfare

#: The reason every row written for a stranded session's return carries.
RESTORED = (
    "the service holding this session stopped before its return was recorded; taken "
    "after a restart (P4d-2b spec §6.1)"
)


def find(root: Path) -> list[Stranded]:
    """Every session under `root` whose record holds a departure with no return after
    it, in folder order. A record with a line that is not a row is stranded with its
    subject empty and its departure `None`."""
    root = Path(root)
    if not root.is_dir():
        return []
    found = []
    for notes in sorted(root.glob(f"*/{XCON_DIRNAME}/{WELFARE_NOTES}")):
        session_id = notes.parent.parent.name
        try:
            departure = None
            for line in notes.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["kind"] == "departure":
                    departure = row
                elif row["kind"] == "returned":
                    departure = None
            if departure is not None:
                found.append(
                    Stranded(
                        session_id=session_id,
                        subject=str(departure["subject"]),
                        left_at=float(departure["now"]),
                    )
                )
        except (ValueError, KeyError, TypeError):
            # `json.JSONDecodeError` is a `ValueError`; a row that is not an object, or
            # has no kind, is the others. Fail closed.
            found.append(Stranded(session_id=session_id, subject="", left_at=None))
    return found


@dataclass
class Restored:
    """A stranded session read back from its record: just enough to take its return --
    `wall_now`, `return_needs_confirmation`, `returned_to_cage`, as `taskd.Session` has
    them -- and to write the rows a `Session` would."""

    directory: Path
    subject: str
    welfare: Welfare
    wall_now: Callable[[], float]

    def return_needs_confirmation(self, at: float) -> str | None:
        return self.welfare.return_needs_confirmation(at, wall_now=self.wall_now())

    def returned_to_cage(
        self, at: float, confirmed: bool = False, by: str = "", how: str = ""
    ) -> None:
        """`Session.returned_to_cage`'s shape: the far question asked before the mark,
        so a `return confirmed` row is written when one was owed; the rows only after
        `welfare` has taken it."""
        wall_now = self.wall_now()
        far = self.welfare.return_needs_confirmation(at, wall_now)
        self.welfare.returned_to_cage(at, wall_now=wall_now, confirmed=confirmed)
        for kind in ("returned", "return confirmed") if far is not None else ("returned",):
            welfare_note(
                self.directory,
                kind=kind,
                subject=self.subject,
                was=at,
                now=at,
                reason=RESTORED,
                by=by,
                how=how,
                recorded_at=self.wall_now(),
            )


def restore(
    found: Stranded, bounds: Bounds, directory: Path, wall_now: Callable[[], float]
) -> Restored:
    """A stranded session, ready for its return: its animal's bounded config (which a
    `Welfare` needs to exist, and whose subject must be the session's), and its recorded
    departure. Refused, with the sentence a person needs, for a record that cannot be
    read or bounds that name another animal."""
    if found.left_at is None:
        raise Exceeded(
            f"session {found.session_id}'s welfare record cannot be read: a line of "
            f"{Path(directory) / WELFARE_NOTES} is not a row, as a process that died while "
            f"writing it leaves one. Its departure is unknown, so no return can be "
            f"checked against it: repair the file by hand -- remove the torn line, keep "
            f"every whole row -- then restart wlx taskd"
        )
    if bounds.subject != found.subject:
        raise Exceeded(
            f"session {found.session_id} is {found.subject!r}'s, and the bounded config "
            f"given is {bounds.subject!r}'s"
        )
    welfare = Welfare(
        bounds=bounds, pump=NoPump(), already_today=None, deployment=Deployment.RIG_CHAIRED
    )
    welfare.restore_departure(found.left_at)
    return Restored(Path(directory), found.subject, welfare, wall_now)
```

- [ ] **Step 5: `wl_xcon/service.py`, the sessions**

```python
"""`wlx taskd` -- the rig service (P4d-2b spec §6.1).

One process on the rig PC, all day: idle until a console opens a session, then one
animal's session across as many runs as the operator starts, until its return to the cage
is recorded, and then idle again for the next animal. **All of one animal's welfare state
lives in one `taskd.Session`** (PI, 2026-09-29: "One always-on rig service"), which is
the shape S9a §7 drew; nothing carries from one session to the next.

Its commands are the link's -- `OpenSession`, `CheckRun`, `StartRun` and `EndSession`
beside b2a's -- over the socket `wlx run --link` binds. **They are read once per
housekeeping pass while no run is in progress, and at each trial boundary during one**,
never per frame (the b3a-1 plan, decision 18).

**Crash safety is a refusal, not a recovery** (spec §6.1). On start the service finds
every session under `--root` with a departure and no return (`stranded.find`), and while
one exists it opens no session, for that animal or any other, until an `EndSession`
naming it records the return.

**Welfare-critical: `Service._open`, `Service._end`, `Service._close_stranded` and
`Service._start`** (`docs/design/architecture.md`): the page's route into the two marks,
the stranded rule, and the gate before a run. The rest is ordinary.

**The simulators, today**: the card, the pump and the animal are `wlx run`'s, because no
hardware port exists (docs/CHECKPOINT.md: nothing has touched hardware); a rig's own
replace them when they do.
"""

from __future__ import annotations

import argparse
import gc
import re
import secrets
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from wl_xcon import link as _link
from wl_xcon import marks as _marks
from wl_xcon import stranded as _stranded
from wl_xcon.bounds import Exceeded
from wl_xcon.cli import _load_allocation, _load_bounds, _load_rig, _load_subject_settings
from wl_xcon.codes import Allocation
from wl_xcon.dio import Simulated as SimulatedCard
from wl_xcon.geometry import Rig
from wl_xcon.record import XCON_DIRNAME
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, SessionClock
from wl_xcon.welfare import Simulated as SimulatedPump

#: Seconds between housekeeping passes while no run is in progress: one frame published,
#: the link drained, a mark stamped. The wait ends early when a command or a mark
#: arrives. **A display cadence, not a measurement** -- `await_return`'s own, and well
#: inside `ZmqConsole`'s 5 s receive timeout.
HOUSEKEEPING_S = 1.0

#: The framework events every session here strobes on paths any session can reach:
#: head-fixation at open, its release at the end, an applied setting, and each run's
#: start and end (the b3a-1 plan, decision 12).
FRAMEWORK_CODES = ("HEAD_FIXED", "HEAD_RELEASED", "PARAM_CHANGED", "RUN_START", "RUN_END")

#: The frame period every session here runs at: `wlx run`'s own (`cli.main`).
FRAME_PERIOD = 1 / 240

#: One folder name (the b3a-1 plan, decision 19): a session id, an animal or a task
#: file, each of which becomes a path. Letters, digits, `_`, `.` and `-`, starting with
#: a letter or digit -- so never `.`, `..`, or anything with a separator.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def _fresh_seed() -> int:
    """A run's seed, drawn here and written into its start row (the b3a-1 plan,
    decision 15), so the run can be replayed."""
    return secrets.randbelow(2**31)


def _sentence(refused: BaseException) -> str:
    """What a refusal says: a `SystemExit`'s message, or the exception's own."""
    return str(refused.code if isinstance(refused, SystemExit) else refused)


class Service:
    """`wlx taskd`'s state and loop: the link, the open session if any, the stranded
    sessions, and the question and refusals an idle frame carries."""

    def __init__(
        self,
        *,
        rig: Rig,
        rig_path: str,
        subjects: Path,
        tasks: Path,
        allocation: Allocation,
        allocation_path: str,
        root: Path,
        link,
        card: Callable[[], object] = SimulatedCard,
        pump: Callable[[], object] = SimulatedPump,
        seed: Callable[[], int] = _fresh_seed,
        wall_clock: Callable[[], float] | None = None,
    ) -> None:
        missing = [
            name for name in FRAMEWORK_CODES if name not in allocation.task_events.values()
        ]
        if missing:
            raise SystemExit(
                f"refused: the allocation "
                f"{allocation_path or '(none given, so the provisional one)'} has no "
                f"{', '.join(missing)} event code; every session wlx taskd runs strobes "
                f"each, so give --allocation with them all"
            )
        self.rig, self.rig_path = rig, rig_path
        self.subjects, self.tasks, self.root = Path(subjects), Path(tasks), Path(root)
        self.allocation, self.allocation_path = allocation, allocation_path
        self.link = link
        self._card, self._pump, self._seed = card, pump, seed
        #: Injected by a test; otherwise the service's own anchored wall.
        self.wall_clock = wall_clock
        self._clock = SessionClock()
        self.session: Session | None = None
        self.stranded: list = _stranded.find(self.root)
        #: A departure, or a stranded session's return, a console owes an answer on.
        self.question: _link.Question | None = None
        #: The service's own refusals while no session is open, capped as a session's.
        self.refusals: list = []
        self.refusals_dropped = 0
        #: A run accepted this pass and not started yet: `(RunSpec, rows, by)`.
        self._starting = None
        #: An `EndSession` that arrived during a run, finished once the run returns.
        self._ending = None

    def wall_now(self) -> float:
        """The service's wall: a test's, or its own `SessionClock`, anchored once."""
        return self.wall_clock() if self.wall_clock is not None else self._clock.now()

    # --- the loop -----------------------------------------------------------------

    def serve(self, stop: threading.Event) -> None:
        """Pass after pass until `stop` is set: `wlx taskd`'s loop. `stop` is read
        between passes, so a run in progress finishes -- or is stopped -- first."""
        while not stop.is_set():
            self.step()

    def step(self) -> None:
        """One housekeeping pass: wait for a console (up to `HOUSEKEEPING_S`), stamp a
        mark, take every command waiting, and publish one frame."""
        mark = self.link.idle(HOUSEKEEPING_S)
        if mark:
            self._mark(mark)
        for command in self.link.drain():
            self._route(command)
        self.publish()

    def publish(self) -> None:
        """The open session's frame, or an idle one."""
        if self.session is not None:
            self.session.offered_tasks = self._tasks()
            self.session.publish()
            return
        self.link.publish(
            _link.Idle.of(
                wall_at=self.wall_now(),
                stranded=self.stranded,
                question=self.question,
                refusals=self.refusals,
                refusals_dropped=self.refusals_dropped,
                link=self.link,
                animals=self._animals(),
                offered_tasks=self._tasks(),
            )
        )

    def shutdown(self) -> None:
        """The process is stopping (Ctrl-C at `wlx taskd`'s terminal): a session still
        open is recorded as ended without its return, and its clock closed. The next
        start finds it stranded (`stranded.find`), which is what makes it safe to stop
        rather than wait."""
        session, self.session = self.session, None
        if session is None:
            return
        if (
            session.welfare.left_cage_wall_at is not None
            and session.welfare.returned_wall_at is None
        ):
            session.return_not_recorded("wlx taskd stopped with the session open", how="wlx taskd")
        if session.opened_wall_at is not None and session.ended_wall_at is None:
            session.end(how="wlx taskd")

    # --- commands -----------------------------------------------------------------

    def _route(self, command) -> None:
        if isinstance(command, _link.OpenSession):
            self._open(command)
        elif isinstance(command, _link.EndSession):
            self._end(command)
        elif self.session is not None:
            self.session.receive(command)
        else:
            self._refuse(
                command.name if isinstance(command, _link.SetParameter) else command.KIND,
                command.by,
                "no session is open, so a command for a run is not applied; open a "
                "session first",
            )

    def _refuse(self, name: str, by: str, why: str) -> None:
        """Onto the open session's feed, or, with none open, the idle frame's."""
        if self.session is not None:
            self.session.refuse(name, by, why)
            return
        self.refusals.append(_link.Refused(name=name, by=by, why=why))
        if len(self.refusals) > _link.REFUSAL_HISTORY:
            self.refusals_dropped += len(self.refusals) - _link.REFUSAL_HISTORY
            del self.refusals[: -_link.REFUSAL_HISTORY]

    def _mark(self, mark: int) -> None:
        """A mark signal with no run checking for one: stamped into the open session, or
        refused while idle, since it belongs to no session (the b3a-1 plan, decision 16)."""
        if self.session is not None:
            self.session.stamp(mark)
        else:
            self._refuse("mark", "<unknown>", "no session is open, so the mark was not recorded")

    def _animals(self) -> tuple[str, ...]:
        """The animals a session may be opened for: folders under `--subjects` holding a
        bounded config."""
        if not self.subjects.is_dir():
            return ()
        return tuple(
            sorted(p.name for p in self.subjects.iterdir() if (p / "bounds.py").is_file())
        )

    def _tasks(self) -> tuple[str, ...]:
        """The task files a run may use: `*.py` under `--tasks`, not `_`-prefixed."""
        if not self.tasks.is_dir():
            return ()
        return tuple(
            sorted(p.name for p in self.tasks.glob("*.py") if not p.name.startswith("_"))
        )

    # --- opening --------------------------------------------------------------------

    def _session_for(self, command: _link.OpenSession) -> Session:
        """The session an `OpenSession` asks for, built and **not opened**: nothing is
        written. Raises `SystemExit`, `ValueError` or `Exceeded` with the sentence a
        refusal says."""
        for what, name in (("session id", command.session_id), ("animal", command.animal)):
            if not _NAME.fullmatch(name) or ".." in name:
                raise ValueError(
                    f"a {what} is one folder name -- letters, digits, '_', '.' and '-', "
                    f"starting with a letter or digit -- and {name!r} is not one"
                )
        if (self.root / command.session_id).exists():
            raise ValueError(
                f"session id {command.session_id!r} is already used under {self.root}; "
                f"every session has its own"
            )
        folder = self.subjects / command.animal
        bounds_path = folder / "bounds.py"
        if not bounds_path.is_file():
            raise ValueError(f"there is no animal {command.animal!r}: {bounds_path} does not exist")
        bounds = _load_bounds(bounds_path)
        if bounds.subject != command.animal:
            raise ValueError(
                f"{bounds_path} holds {bounds.subject!r}'s bounded config, and this folder "
                f"is {command.animal!r}'s; ceilings belong to an animal"
            )
        settings_path = None
        if command.view == "direct":
            geometry = self.rig.direct()
        else:
            settings_path = folder / "settings.py"
            if not settings_path.is_file():
                raise ValueError(
                    f"the stereoscope needs {command.animal!r}'s settings, and "
                    f"{settings_path} does not exist"
                )
            geometry = self.rig.stereoscope(
                _load_subject_settings(settings_path, command.animal).half_ipd_cm
            )
        return Session(
            SessionSpec(
                task="",
                allocation=self.allocation_path,
                root=self.root,
                session_id=command.session_id,
                subject=command.animal,
                trials=0,
                frame_period=FRAME_PERIOD,
                seed=0,
                values={},
                bounds=bounds,
                already_delivered_today=command.delivered_today,
                deployment=Deployment(command.deployment),
                geometry=geometry,
                bounds_config=str(bounds_path),
                rig_config=self.rig_path,
                subject_settings="" if settings_path is None else str(settings_path),
            ),
            card=self._card(),
            pump=self._pump(),
            link=self.link,
            service=True,
            wall_clock=self.wall_clock,
        )

    def _open(self, command: _link.OpenSession) -> None:
        """**Welfare-critical.** Open a session (P4d-2b spec §6.2): **none while one is
        open, and none for any animal while one is stranded** (§6.1); then the departure
        through `marks`, the terminal's own rules; and **nothing written until it is
        accepted**, so a refused or unanswered departure leaves no folder and its id
        free (the b3a-1 plan, decision 11). A far departure with no answer puts the
        question on the idle frame, with a refusal row saying what to send."""
        self.question = None
        if self.session is not None:
            self._refuse(
                "open",
                command.by,
                f"a session is open for {self.session.spec.subject!r} "
                f"({self.session.spec.session_id}); end it, with its animal's return, "
                f"before another opens",
            )
            return
        if self.stranded:
            names = "; ".join(
                f"{found.subject or 'an unreadable record'} in session {found.session_id}"
                for found in self.stranded
            )
            self._refuse(
                "open",
                command.by,
                f"no session opens while an animal's return is not recorded: {names}. "
                f"Record it with End session, naming its session",
            )
            return
        try:
            session = self._session_for(command)
        except (SystemExit, ValueError, TypeError, Exceeded) as refused:
            self._refuse("open", command.by, _sentence(refused))
            return
        except Exception as broken:  # noqa: BLE001 -- the animal's files are code
            self._refuse(
                "open", command.by,
                f"the session could not be built: {type(broken).__name__}: {broken}",
            )
            return
        try:
            decision = _marks.page_departure(
                session,
                departure=command.departure,
                answer=command.answer,
                amend_to=command.amend_to,
                amend_reason=command.amend_reason,
                by=command.by,
            )
            _marks.depart(session, decision)
        except _marks.Owed as owed:
            self.question = _link.Question(
                mark="departure",
                session_id=command.session_id,
                at=owed.at,
                said=owed.warning,
                answers=owed.answers,
            )
            self._refuse(
                "open",
                command.by,
                f"{owed.warning}. Nothing was recorded: send it again answering "
                f"confirm, or amend with the corrected time, a reason and your name",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("open", command.by, str(refused))
            return
        _marks.record_departure(session, decision)
        session.open(how="wlx taskd")
        if session.spec.deployment is Deployment.RIG_FIXED:
            session.head_fixed(session.wall_now())
        session.offered_tasks = self._tasks()
        self.session = session

    # --- ending ---------------------------------------------------------------------

    def _end(self, command: _link.EndSession) -> None:
        """**Welfare-critical.** End the open session (P4d-2b spec §6.2): its runs end
        and its head is released (`Session.end_runs`, the b3a-1 plan, decision 6), then
        its return is taken through `marks`, the terminal's rules -- or, given no return,
        it waits for one. With none open, the stranded session it names."""
        if self.session is None:
            self._close_stranded(command)
            return
        session = self.session
        if command.session_id not in (None, session.spec.session_id):
            self._refuse(
                "end",
                command.by,
                f"the session open is {session.spec.session_id}, not "
                f"{command.session_id}; nothing was ended",
            )
            return
        if session.phase == "between_runs":
            session.end_runs(command.by)
        session.question = None
        if command.returned is None:
            return
        try:
            _marks.page_return(
                session, returned=command.returned, confirm=command.confirm, by=command.by
            )
        except _marks.Owed as owed:
            session.question = _link.Question(
                mark="return",
                session_id=session.spec.session_id,
                at=owed.at,
                said=owed.warning,
                answers=owed.answers,
            )
            self._refuse(
                "end",
                command.by,
                f"{owed.warning}. Send it again answering confirm, or with the time "
                f"typed again",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("end", command.by, str(refused))
            return
        session.close(how="wlx taskd")
        self.session = None
        # The session is a reference cycle (`welfare.Rig`'s docstring): collected here,
        # between sessions, never during a run (the b3a-1 plan, decision 17).
        gc.collect()

    def _close_stranded(self, command: _link.EndSession) -> None:
        """**Welfare-critical.** A stranded session's return (spec §6.1), checked against
        its recorded departure under `welfare`'s rules (`stranded.restore`), written into
        its own record. Refused while its record cannot be read or its animal's bounded
        config is gone -- each with what to do."""
        found = next(
            (s for s in self.stranded if s.session_id == command.session_id), None
        )
        if found is None:
            self._refuse(
                "end",
                command.by,
                "no session is open"
                + (
                    f", and no stranded session is {command.session_id!r}"
                    if command.session_id
                    else "; to record a stranded animal's return, name its session"
                )
                + "; nothing was ended",
            )
            return
        if command.returned is None:
            self._refuse(
                "end", command.by,
                f"give the time {found.subject or 'the animal'} went back into its home cage",
            )
            return
        self.question = None
        bounds_path = self.subjects / found.subject / "bounds.py"
        if found.left_at is not None and not bounds_path.is_file():
            self._refuse(
                "end",
                command.by,
                f"{found.subject!r}'s bounded config ({bounds_path}) is needed to check "
                f"its return against its departure, and it does not exist; restore it",
            )
            return
        try:
            restored = _stranded.restore(
                found,
                _load_bounds(bounds_path) if found.left_at is not None else None,
                self.root / found.session_id / XCON_DIRNAME,
                self.wall_now,
            )
            _marks.page_return(
                restored,
                returned=command.returned,
                confirm=command.confirm,
                by=command.by,
                how="the page, after a restart",
            )
        except _marks.Owed as owed:
            self.question = _link.Question(
                mark="return", session_id=found.session_id, at=owed.at,
                said=owed.warning, answers=owed.answers,
            )
            self._refuse(
                "end", command.by,
                f"{owed.warning}. Send it again answering confirm, or with the time typed again",
            )
            return
        except (SystemExit, argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("end", command.by, _sentence(refused))
            return
        self.stranded.remove(found)


def run(args) -> int:
    """`wlx taskd`: load the rig and the allocation, bind the link, and serve until
    interrupted."""
    rig = _load_rig(args.rig)
    allocation = _load_allocation(args.allocation)
    for flag, folder in (("--subjects", args.subjects), ("--tasks", args.tasks)):
        if not folder.is_dir():
            raise SystemExit(f"refused: {flag} {folder} is not a folder")
    parts = args.link.split(",")
    if len(parts) not in (2, 3):
        raise SystemExit(
            f"--link expects PUB,REP or PUB,REP,MARK (two or three comma-separated "
            f"endpoints), got {args.link!r}"
        )
    pub, rep, *mark = parts
    try:
        link = _link.ZmqLink(
            pub, rep, mark[0] if mark else None, allow_remote=args.link_allow_remote
        )
    except _link.RemoteBindRefused as refused:
        raise SystemExit(str(refused)) from refused
    with link:
        service = Service(
            rig=rig,
            rig_path=str(args.rig),
            subjects=args.subjects,
            tasks=args.tasks,
            allocation=allocation,
            allocation_path=str(args.allocation) if args.allocation else "",
            root=args.root,
            link=link,
        )
        print(
            f"wlx taskd: publishing on {link.pub_endpoint}, commands on "
            f"{link.rep_endpoint}"
            + (f", marks on {link.mark_endpoint}" if link.mark_endpoint else "")
        )
        for found in service.stranded:
            print(
                f"  stranded: session {found.session_id} "
                f"({found.subject or 'record unreadable'}); no session opens until its "
                f"return is recorded"
            )
        try:
            service.serve(threading.Event())
        except KeyboardInterrupt:
            open_session = service.session is not None
            service.shutdown()
            print(
                "taskd: interrupted -- the session was open, and the return to the cage "
                "was not recorded; the next start finds it stranded"
                if open_session
                else "taskd: interrupted",
                file=sys.stderr,
            )
            return 130
    return 0
```

Note `stranded.restore` is given `None` bounds only on the unreadable path, where it refuses before reading them: annotate its `bounds` parameter `Bounds | None` and keep the unreadable check first.

- [ ] **Step 6: `wlx taskd`**

In `wl_xcon/cli.py`'s `main`, after the `serve` parser:

```python
    service_parser = sub.add_parser(
        "taskd",
        help="run the rig service: one animal's session at a time, opened, run and "
        "ended from a console (P4d-2b spec §6)",
    )
    service_parser.add_argument(
        "--rig", type=Path, required=True, metavar="PATH",
        help="the rig's display settings: a Python file defining RIG, as tasks/rig.py does",
    )
    service_parser.add_argument(
        "--subjects", type=Path, required=True, metavar="DIR",
        help="one folder per animal, named for it, holding bounds.py (defining BOUNDS, "
        "whose subject must be the folder's name) and, for the stereoscope, "
        "settings.py (defining SETTINGS)",
    )
    service_parser.add_argument(
        "--tasks", type=Path, required=True, metavar="DIR",
        help="the folder of task files a run may use",
    )
    service_parser.add_argument(
        "--allocation", type=Path, default=None,
        help="the event-code allocation. It must carry HEAD_FIXED, HEAD_RELEASED, "
        "PARAM_CHANGED, RUN_START and RUN_END, which every session here strobes, so the "
        "provisional one used when this is omitted is refused",
    )
    service_parser.add_argument(
        "--root", type=Path, required=True,
        help="where session folders go, and where a session left without its animal's "
        "return is looked for at start",
    )
    service_parser.add_argument(
        "--link", required=True, metavar="PUB,REP[,MARK]",
        help="the endpoints this service binds, as `wlx run --link` takes them; `wlx "
        "serve --link` takes the same value. Loopback only unless --link-allow-remote",
    )
    service_parser.add_argument(
        "--link-allow-remote", action="store_true",
        help="permit --link to bind an endpoint other hosts can reach; see `wlx run "
        "--link-allow-remote` for what that exposes, which here includes opening and "
        "ending sessions",
    )
```

and after the `serve` branch:

```python
    if args.command == "taskd":
        # Imported here, as `serve` is: no other subcommand loads the service.
        from wl_xcon import service as _service

        return _service.run(args)
```

- [ ] **Step 7: The gate, the architecture, and who takes the marks now**

Several docstrings say the terminal is the marks' only caller, which this task makes untrue (CLAUDE.md: a claim about the rest of the repo is dated). Rewrite each to name both callers — `wlx run`'s terminal and `wlx taskd`'s page, through `marks.py`, as the wl-works ELN's stand-ins (P4d-2b spec §6.0) — keeping every other sentence: in `wl_xcon/taskd.py`, `Session._note` ("Since P4d-2a spec §10 the one caller in production is `wlx run`"), `left_cage` ("**Not a console's**"), `return_needs_confirmation` ("this method's one caller"), `amend_mark` ("not a console"), `returned_to_cage` ("the terminal, and only the terminal, is this method's one caller in production" — say the service calls it from its own thread, one command at a time, and never beside a terminal, which is another process, so the lock stays gone), and `head_fixed` ("called from `cli.main` itself"); in `wl_xcon/welfare.py`, `_refuse_unconfirmed`'s "both marks are taken at `wlx run`'s terminal today" — its docstring only. Code in none of them changes (Task 10 Step 4 checks).

`tools/mutation_gate.py`'s `RETURNS` gains `"service": "None",` and `"stranded": "None",`. In `docs/design/architecture.md`: the `taskd` row's Job gains "; since P4d-2b b3a also `wlx taskd`, the rig service that holds one animal's session across runs, opened, run and ended from a console (`service.py`)"; and after Task 6's sentence add: "**`stranded.py`, `Welfare.restore_departure`, and `service.Service._open`, `_end` and `_close_stranded`** (P4d-2b b3a): the rule that no session opens while an animal's return is missing from the record, how such a session is found and its return taken, and the page's route into the two marks. `restore_departure` reads back a recorded departure without `left_cage`'s refusals, which were applied when it was taken; a mistake in any of these leaves an animal out of its cage with nothing saying so, or records its return against the wrong instant."

- [ ] **Step 8: Run them to verify they pass**

Run: `python3 -m pytest tests/test_welfare.py tests/test_stranded.py tests/test_service.py tests/test_mutation_gate.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 9: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add wl_xcon/welfare.py wl_xcon/taskd.py wl_xcon/stranded.py wl_xcon/service.py wl_xcon/cli.py tests/test_welfare.py tests/test_stranded.py tests/test_service.py tools/mutation_gate.py docs/design/architecture.md docs/superpowers/specs/2026-08-31-S8-session-management-design.md
git commit -m "Add wlx taskd: sessions from a console, and none while an animal is stranded"
```

---

### Task 8: The service's runs — pre-flight, the gate, and ending a run in progress

**Welfare-critical: `Service._start`.**

**Files:**
- Modify: `wl_xcon/service.py` (`_Routed`; `Service._route`, `step`, `_session_for`, `_end`; new `_between_runs`, `_task`, `_preflight`, `_check`, `_start`, `_run`), `docs/design/architecture.md`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: Task 2's `RunSpec`, `Session.run(run, *, preflight_rows, by)`; Task 3's `Session.preflight`; Task 6's `preflight.task/values/files/out_of_cage/unmeasured/gate/rows`; Task 4's `CheckRun`, `StartRun`, `Stop`, `Preflight`.
- Produces: `CheckRun`/`StartRun` handled; an `EndSession` during a run stops it and ends the session after; `_Routed(link, service)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_service.py`'s unit section (importing `CheckRun`, `SetParameter`, `StartRun`, `Stop` too):

```python
VALUES = {
    "fix_timeout": 4.0, "fix_hold": 0.3, "response_window": 0.6, "target_hold": 0.2,
    "fix_window": 2.0, "target_window": 3.0, "target_position": 10.0,
}
UNKNOWN = ("pump calibration", "eye tracker")


def _start(**over) -> StartRun:
    fields = dict(by=BY, task=TASK, values=dict(VALUES), trials=3, acknowledged=UNKNOWN)
    fields.update(over)
    return StartRun(**fields)


def _runs(root, session_id="2027-01-14_01") -> list[dict]:
    path = root / session_id / "xcon" / "runs.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class _Script(Simulated):
    """A link whose `n`th drain also hands over `script[n]`: the service's own drains
    and a run's, at its boundaries, counted alike."""

    def __init__(self, script: dict) -> None:
        super().__init__()
        self.script, self.drains = script, 0

    def drain(self):
        self.drains += 1
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def test_a_check_shows_the_runs_preflight_and_starts_nothing(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES)))

    assert (frame.phase, frame.run_index) == ("between_runs", None)
    assert frame.preflight.task == TASK
    assert [(i.name, i.result) for i in frame.preflight.items] == [
        ("task checks", "pass"), ("starting values", "pass"), ("bounded config", "pass"),
        ("out of cage", "pass"), ("pump calibration", "unknown"), ("eye tracker", "unknown"),
    ]


def test_a_run_whose_unknowns_nobody_acknowledged_does_not_start(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(acknowledged=("pump calibration",)))

    assert frame.run_index is None and _runs(service.root) == []
    assert "nobody has acknowledged: eye tracker" in _refused(frame)[-1]
    assert frame.preflight is not None, "the pre-flight stays on the frame to acknowledge"


def test_an_acknowledged_run_starts_records_who_acknowledged_what_and_ends_between_runs(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start())

    assert (frame.phase, frame.run_index, frame.stop_kind) == ("between_runs", 0, "completed")
    start, end = _runs(service.root)
    assert {r["name"]: r["acknowledged_by"] for r in start["preflight"]} == {
        "task checks": None, "starting values": None, "bounded config": None,
        "out of cage": None, "pump calibration": BY, "eye tracker": BY,
    }
    assert (start["unplanned"], start["by"], start["seed"], start["trials"]) == (True, BY, 7, 3)
    assert end["stop_kind"] == "completed"
    codes = service.session.card.codes
    assert codes[:2] == [4128, 4135] and 4136 in codes and 4129 not in codes


@pytest.mark.parametrize(
    ("over", "item"),
    [
        ({"values": {**VALUES, "fix_hold": 99.0}}, "starting values"),
        ({"values": {**VALUES, "no_such": 1.0}}, "starting values"),
        ({"task": "empty.py"}, "task checks"),
    ],
)
def test_a_run_with_a_failing_item_does_not_start_even_acknowledged(tmp_path, over, item):
    service = _service(tmp_path)
    (service.tasks / "empty.py").write_text("x = 1\n")
    _step(service, _open())

    frame = _step(service, _start(**over))

    assert frame.run_index is None
    assert f"pre-flight failed, so the run does not start: {item}" in _refused(frame)[-1]


@pytest.mark.parametrize("task", ["missing.py", "../fixation_detection.py", "notes.txt"])
def test_a_task_that_is_not_a_file_under_the_tasks_folder_is_refused_by_name(tmp_path, task):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(task=task))

    assert frame.run_index is None and "is not a task file under" in _refused(frame)[-1]


def test_the_out_of_cage_limit_reached_between_runs_refuses_a_new_run_and_says_so(tmp_path):
    """Spec §6.1: "reached between runs, it refuses a new run, and the page asks for the
    return"."""
    wall = _Wall()
    service = _service(tmp_path, bounds=TEN_MINUTES, wall=wall)
    _step(service, _open(departure=typed(300)))
    _step(service, _start(trials=2))
    wall.at = WALL + 400

    frame = _step(service, _start(trials=2))

    assert frame.run_index == 0, "no second run"
    assert "out of cage: out_of_cage" in _refused(frame)[-1]
    assert "ceiling" in frame.duration_warning
    assert [i.result for i in frame.preflight.items if i.name == "out of cage"] == ["fail"]


def test_the_out_of_cage_limit_ends_a_run_in_progress_and_the_session_waits_for_its_return(tmp_path):
    service = None

    def wall() -> float:
        # Follows the frames while a run is in progress, as a rig's wall does.
        return WALL + (service.session.now() if service is not None and service.session else 0.0)

    service = _service(tmp_path, bounds=TEN_MINUTES, wall=wall)
    _step(service, _open(departure=typed(300)))

    frame = _step(service, _start(trials=100_000))

    assert (frame.phase, frame.stop_kind) == ("between_runs", "limit")
    assert isinstance(_step(service, _end()), Idle)


def test_end_during_a_run_stops_it_at_its_boundary_then_ends_the_session(tmp_path):
    link = _Script({3: [_end()]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=1000))

    assert isinstance(frame, Idle)
    _, end = _runs(service.root)
    assert (end["stop_kind"], end["stopped_because"]) == ("operator", f"stopped by {BY}")
    assert end["trials"] < 1000
    assert _kinds(service.root)[-2:] == ["returned", "session ended"]


def test_during_a_run_the_services_own_commands_are_refused_not_queued(tmp_path):
    """Review Focus 4: a second start sent while a run is in progress -- a double click --
    is refused, never started after the first."""
    link = _Script({4: [_start(), _open(session_id="2027-01-14_02")]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start())

    assert frame.run_index == 0 and len(_runs(service.root)) == 2
    assert [why for why in _refused(frame) if "a run is in progress" in why] != []
    assert len([why for why in _refused(frame) if "a run is in progress" in why]) == 2


def test_two_starts_in_one_pass_start_one_run(tmp_path):
    """Review Focus 4, in one pass."""
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(), _start())

    assert frame.run_index == 0 and len(_runs(service.root)) == 2
    assert "a run is already starting" in _refused(frame)[-1]


def test_an_end_in_the_same_pass_as_a_start_ends_the_session_and_starts_nothing(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(), _end())

    assert isinstance(frame, Idle) and _runs(service.root) == []


def test_a_run_that_faults_leaves_the_session_open_for_its_return(tmp_path, monkeypatch, capsys):
    """The b3a-1 plan, decision 14: published, recorded, said on stderr -- and the animal,
    still out, can have its return taken."""
    from wl_xcon import taskd

    real, calls = taskd.run_trial, [0]

    def faults_once(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError("the display went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", faults_once)
    service = _service(tmp_path)
    _step(service, _open())

    faulted = _step(service, _start())

    assert (faulted.phase, faulted.stop_kind) == ("between_runs", "fault")
    assert "the display went away" in capsys.readouterr().err
    again = _step(service, _start())
    assert (again.run_index, again.stop_kind) == (1, "completed")


def test_a_reward_size_changed_in_one_run_is_where_the_next_run_starts(tmp_path):
    """Question 1 (PI), as recommended: the bounded config is the session's, so a size a
    person set in run 0 is run 1's, and each start row says which."""
    link = _Script({3: [SetParameter(name="reward_correct", value=0.1, by=BY)]})
    service = _service(tmp_path, link=link)
    _step(service, _open())
    _step(service, _start(trials=3))

    _step(service, _start(trials=1))

    first, _, second, _ = _runs(service.root)
    assert (first["bounded"]["reward_correct"], second["bounded"]["reward_correct"]) == (0.05, 0.1)


def test_each_run_draws_its_own_seed_and_records_it(tmp_path):
    seeds = iter([11, 12])
    service = _made(_folders(tmp_path), seed=lambda: next(seeds))
    _step(service, _open())

    _step(service, _start(trials=1))
    _step(service, _start(trials=1))

    assert [row["seed"] for row in _runs(service.root) if row["event"] == "start"] == [11, 12]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_service.py -q -p no:cacheprovider`
Expected: FAIL — until Task 8 the service hands a `CheckRun` or `StartRun` to the session, which refuses it between runs ("no run is in progress ..."), so no pre-flight is on the frame and no `runs.jsonl` is written.

- [ ] **Step 3: Implement**

In `wl_xcon/service.py`, import `traceback`, `from wl_xcon import preflight as _preflight` and `from wl_xcon.taskd import RunSpec`, and add before `Service`:

```python
class _Routed:
    """The link a service session drains through (the b3a-1 plan, decision 18): the
    service's own link, with the service's commands taken out of what a run sees.

    **An `EndSession` during a run stops it** -- a `Stop` in its place, at the boundary
    that drained it -- and is kept for the service to finish once the run has returned.
    Any other service command during a run is refused on the session's feed: a run is in
    progress. **Everything else is the real link's**: `mark_signal`, `publish` and
    `idle` are the link's own bound methods, so the per-frame mark check is the call
    V12 measured, with nothing added."""

    def __init__(self, link, service: "Service") -> None:
        self._link = link
        self._service = service
        self.mark_signal = link.mark_signal
        self.publish = link.publish
        self.idle = link.idle

    @property
    def refused(self):
        return self._link.refused

    @property
    def refused_dropped(self) -> int:
        return self._link.refused_dropped

    def drain(self) -> list:
        kept = []
        for command in self._link.drain():
            if isinstance(command, _link.EndSession) and self._service._ending is None:
                self._service._ending = command
                kept.append(_link.Stop(by=command.by))
            elif isinstance(
                command,
                (_link.OpenSession, _link.CheckRun, _link.StartRun, _link.EndSession),
            ):
                self._service.session.refuse(
                    command.KIND,
                    command.by,
                    "a run is in progress, so this is refused rather than kept for later; "
                    "send it again once the run has ended",
                )
            else:
                kept.append(command)
        return kept
```

In `_session_for`, the session's `link=self.link` becomes `link=_Routed(self.link, self)`.

`_route` gains, before the `self.session is not None` branch:

```python
        elif isinstance(command, _link.CheckRun):
            self._check(command)
        elif isinstance(command, _link.StartRun):
            self._start(command)
```

`step` becomes:

```python
    def step(self) -> None:
        """One housekeeping pass: wait for a console (up to `HOUSEKEEPING_S`), stamp a
        mark, take every command waiting, publish one frame -- and then run a run
        accepted in this pass, finishing an `EndSession` that arrived during it."""
        mark = self.link.idle(HOUSEKEEPING_S)
        if mark:
            self._mark(mark)
        for command in self.link.drain():
            self._route(command)
        self.publish()
        if self._starting is None:
            return
        run, rows, by = self._starting
        self._starting = None
        self._run(run, rows, by)
        if self._ending is not None:
            ending, self._ending = self._ending, None
            self._end(ending)
        self.publish()
```

In `_end`, after the `session_id` check and before `if session.phase == "between_runs":`:

```python
        if self._starting is not None:
            self._starting = None
            self._refuse(
                "start", command.by,
                "the session was ended in the same pass, so the run does not start",
            )
```

Add:

```python
    def _between_runs(self, kind: str, by: str) -> Session | None:
        """The open session, when a run may be checked or started; otherwise refused,
        saying why."""
        if self.session is None:
            self._refuse(kind, by, "no session is open, so no run starts; open a session first")
            return None
        if self.session.phase != "between_runs":
            self._refuse(
                kind, by,
                "the session has ended and waits for its animal's return, so no run starts",
            )
            return None
        if self._starting is not None:
            self._refuse(kind, by, "a run is already starting, so this is refused")
            return None
        return self.session

    def _task(self, name: str, kind: str, by: str) -> Path | None:
        """A task file under `--tasks`, named as one folder entry ending `.py`; refused
        otherwise."""
        path = self.tasks / name
        if not (_NAME.fullmatch(name) and name.endswith(".py") and path.is_file()):
            self._refuse(kind, by, f"{name!r} is not a task file under {self.tasks}")
            return None
        return path

    def _preflight(self, session: Session, task: Path, values: dict) -> _link.Preflight:
        """Spec §6.2's items, taken now, in order."""
        item, trial = _preflight.task(task, self.allocation, session.spec.geometry)
        settings = Path(session.spec.subject_settings) if session.spec.subject_settings else None
        return _link.Preflight(
            task=task.name,
            items=(
                item,
                _preflight.values(trial, values),
                *_preflight.files(
                    Path(session.spec.bounds_config), session.spec.subject, settings, self.rig
                ),
                _preflight.out_of_cage(session),
                *_preflight.unmeasured(),
            ),
        )

    def _check(self, command: _link.CheckRun) -> None:
        """Take a run's pre-flight and put it on the frame, starting nothing."""
        session = self._between_runs("check", command.by)
        if session is None:
            return
        task = self._task(command.task, "check", command.by)
        if task is not None:
            session.preflight = self._preflight(session, task, command.values)

    def _start(self, command: _link.StartRun) -> None:
        """**Welfare-critical.** Accept a run (spec §6.2): the pre-flight **taken now**,
        never trusted from an earlier check, and S9a §10's rule asked of it with the
        items this person acknowledged by name (`preflight.gate`); only then is the run
        kept to start once this pass has published. Every run is unplanned until b3b."""
        session = self._between_runs("start", command.by)
        if session is None:
            return
        task = self._task(command.task, "start", command.by)
        if task is None:
            return
        checked = self._preflight(session, task, command.values)
        session.preflight = checked
        why = _preflight.gate(checked, command.acknowledged)
        if why is not None:
            self._refuse("start", command.by, why)
            return
        self._starting = (
            RunSpec(
                task=str(task),
                trials=command.trials,
                seed=self._seed(),
                values=dict(command.values),
            ),
            _preflight.rows(checked, command.by),
            command.by,
        )

    def _run(self, run: RunSpec, rows: list, by: str) -> None:
        """The run, to its end. **Its two backstop refusals** (`Session.run`'s blocking
        finding and `welfare.preflight`) are refusals here. **A fault is contained**
        (the b3a-1 plan, decision 14): `run()` has published it and written it into
        the run's end row, the session is back between runs with the animal still out,
        and the traceback goes to this process's stderr; the service goes on, so the
        return can be taken. Ctrl-C is not caught: `wlx taskd` ends on it."""
        session = self.session
        try:
            session.run(run, preflight_rows=rows, by=by)
        except (SystemExit, Exceeded) as refused:
            session.refuse("start", by, _sentence(refused))
        except Exception:  # noqa: BLE001 -- see the docstring: published, recorded, said
            traceback.print_exc(file=sys.stderr)
```

**Step 3b — only if the PI answered Question 1 "back to the file".** Then, in `_start`, directly before `self._starting = (...)`, add the reset:

```python
        # Question 1 (PI): each run starts at the values in the animal's bounds file.
        # Staged through `Session.set`, so the change is checked, recorded and strobed
        # like any other, and applied at the run's first boundary, before its first trial.
        fresh = _load_bounds(Path(session.spec.bounds_config))
        for name, ceiling in fresh.ceilings.items():
            if name in session.spec.bounds.ceilings and session.spec.bounds.value(name) != ceiling.value:
                session.set(name, ceiling.value, by="the animal's bounds file, as the run starts")
```

and replace `test_a_reward_size_changed_in_one_run_is_where_the_next_run_starts` with `test_a_reward_size_changed_in_one_run_goes_back_to_the_file_as_the_next_run_starts`, asserting after the second run that `service.session.spec.bounds.value("reward_correct") == 0.05` and that the last row of `parameter_changes.jsonl` has `name` `reward_correct`, `was` `0.1`, `now` `0.05`, `run` `1` and `by` `the animal's bounds file, as the run starts`. (Both start rows still read `bounded` `(0.05, 0.1)`: a start row is written before the first boundary applies the staged reset, and says so by the change row after it.) If the PI answered as recommended, skip this step.

In `docs/design/architecture.md`, extend Task 7's sentence to name `Service._start`: "and `_start`, which asks S9a §10's gate of a pre-flight taken as a run is started, never an earlier one".

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_service.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/service.py tests/test_service.py docs/design/architecture.md
git commit -m "Run a session's runs from the service, each behind its pre-flight"
```

---

### Task 9: End to end over the real link (spec §6.5)

**Files:**
- Test: `tests/test_service.py` (the end-to-end section)

**Interfaces:**
- Consumes: everything above; `link.ZmqLink`, `ZmqConsole`, `ZmqCommands`.

**Read `tests/test_serve.py`'s `CONTROL_TRIAL_BUDGET` comment first, and heed it**: the simulator runs trials unpaced, a console's frame handling can fall behind, and a broken command path must fail these tests in seconds, not at the harness's 300 s. So: every session here has a trial budget of 400 and each trial is paced 5 ms; every wait has a deadline and ends early (within `LAST_FRAME_S`) once the service's thread has gone; the service's `ZmqLink` is built on its own thread, as `wlx taskd` builds it, since `_every_zmq_context_released` assumes an object is used by the thread that built it; and a test that ends with a run still going sends a `Stop` before it sets the service's stop event, as `_Session.__exit__` does.

- [ ] **Step 1: Write the tests**

Append to `tests/test_service.py` (importing `threading`, `time`, `ZmqCommands`, `ZmqConsole`, `ZmqLink`):

```python
# --- end to end: a real `wlx taskd` service over ZeroMQ (spec §6.5) ---------------------

#: Ruling 10, as `tests/test_serve.py`'s `CONTROL_TRIAL_BUDGET` sizes it for a session
#: with a mark socket, and each trial paced as it is there (read its comment for why).
E2E_TRIAL_BUDGET = 400
E2E_PACE_S = 0.005
#: How long a wait still looks once the service's thread has gone.
LAST_FRAME_S = 2.0


def _trial_budget(monkeypatch) -> None:
    """`taskd.run_trial` raises past the budget, so a session a mutant left running
    faults and ends; each trial sleeps `E2E_PACE_S` first. `tests/test_serve.py`'s,
    copied for the reason it copies `test_cli.py`'s."""
    from wl_xcon import taskd

    real, left = taskd.run_trial, [E2E_TRIAL_BUDGET]

    def run_trial(*args, **kwargs):
        left[0] -= 1
        if left[0] < 0:
            raise RuntimeError("this session has run more trials than its budget")
        time.sleep(E2E_PACE_S)
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", run_trial)


def _now(seconds_ago: float = 0.0) -> str:
    """A departure or a return typed as a clock time, from this host's clock now."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - seconds_ago))


class _Rig:
    """A real `wlx taskd` service on a thread, its `ZmqLink` built there; a command sender
    that waits for each acknowledgment, as `wlx serve`'s command thread does; and a
    recorder of every frame, as `tests/test_serve.py`'s `_Session.seen` reads one."""

    def __init__(self, tmp_path, monkeypatch, zmq_cleanup, *, folders=None,
                 bounds=TWELVE_HOURS, wall=None):
        from wl_xcon import dio

        _trial_budget(monkeypatch)
        self.cards: list = []
        cards = self.cards

        class _KeptCard(dio.Simulated):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                cards.append(self)

        self._card = _KeptCard
        probe = zmq_cleanup(
            ZmqLink("tcp://127.0.0.1:0", "tcp://127.0.0.1:0", "tcp://127.0.0.1:0")
        )
        self.pub, self.rep, self.mark = probe.pub_endpoint, probe.rep_endpoint, probe.mark_endpoint
        probe.close()
        self.folders = folders or _folders(tmp_path, bounds)
        self.wall = wall
        self.stop = threading.Event()
        #: Set by a test to leave without `shutdown`, as a crash would.
        self.crash = False
        self.recorder = zmq_cleanup(ZmqConsole(self.pub, None, settle_s=0.0, receive_timeout_s=0.0))
        self.commands = zmq_cleanup(ZmqCommands(self.rep))
        self.frames: list = []
        self._looked = 0
        self.thread = threading.Thread(target=self._serve, daemon=True)

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

    def send(self, command) -> None:
        self.commands.deliver(command)

    def seen(self, predicate, seconds: float = 10.0):
        """The first frame published, from the last one this returned on, for which
        `predicate` is true -- each read as it arrives. Fails within `seconds`, or within
        `LAST_FRAME_S` once the service's thread has gone. **Ten seconds, not b2a's
        twenty**: a frame is due every `HOUSEKEEPING_S` and these runs are a few trials,
        and a mutant that stops the service answering must fail all five tests inside
        the harness's 300 s with the rest of the suite (Step 3)."""
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

    def __enter__(self) -> "_Rig":
        self.thread.start()
        self.seen(lambda frame: True)  # the subscription is live
        return self

    def __exit__(self, *exc_info) -> None:
        if self.thread.is_alive():
            try:
                self.send(Stop(by="e2e-cleanup"))
            except Exception:  # noqa: BLE001 -- best-effort: a run left going is stopped
                pass
        self.stop.set()
        self.thread.join(timeout=30)
        assert not self.thread.is_alive(), "the service did not stop"


def _between(frame) -> bool:
    return isinstance(frame, Telemetry) and frame.phase == "between_runs"


def test_e2e_open_a_session_run_it_twice_and_end_it(tmp_path, monkeypatch, zmq_cleanup):
    """Spec §6.5: open a session, two runs, end it -- over the real link, with the
    simulated animal, card and pump."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup) as rig:
        rig.send(_open(departure=_now()))
        rig.seen(_between)
        for run in (0, 1):
            rig.send(_start(trials=3))
            rig.seen(lambda f, run=run: _between(f) and f.run_index == run and f.stop_kind == "completed")
        rig.send(_end())
        rig.seen(lambda f: isinstance(f, Telemetry) and f.phase == "closed")
        rig.seen(lambda f: isinstance(f, Idle))

    root = rig.folders[2]
    assert [(r["event"], r["run"]) for r in _runs(root)] == [
        ("start", 0), ("end", 0), ("start", 1), ("end", 1),
    ]
    trials = [
        json.loads(line)["run"]
        for line in (root / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text().splitlines()
    ]
    assert trials == [0, 0, 0, 1, 1, 1]
    codes = rig.cards[0].codes
    assert codes[0] == 4128 and codes[-1] == 4129
    assert codes.count(4135) == codes.count(4136) == 2
    assert _kinds(root) == ["departure", "session opened", "returned", "session ended"]


def test_e2e_the_limit_reached_between_runs_refuses_a_new_run_and_asks_for_the_return(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5. The service's wall is this host's, moved forward by the test once the
    first run has ended, so the ten-minute placeholder limit passes between runs."""
    offset = [0.0]
    with _Rig(tmp_path, monkeypatch, zmq_cleanup, bounds=TEN_MINUTES,
              wall=lambda: time.time() + offset[0]) as rig:
        rig.send(_open(departure=_now(120)))
        rig.seen(_between)
        rig.send(_start(trials=2))
        rig.seen(lambda f: _between(f) and f.run_index == 0 and f.stop_kind == "completed")
        offset[0] = 600.0

        warned = rig.seen(lambda f: _between(f) and f.duration_warning and "ceiling" in f.duration_warning)
        rig.send(_start(trials=2))
        refused = rig.seen(lambda f: _between(f) and any("out of cage" in r.why for r in f.refusals))
        rig.send(_end())
        rig.seen(lambda f: isinstance(f, Idle))

    assert warned.run_index == 0 and refused.run_index == 0, "no second run"
    assert len(_runs(rig.folders[2])) == 2


def test_e2e_a_crash_leaves_the_animal_stranded_and_the_restarted_service_waits_for_its_return(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: a crash and restart refuses a new session until the stranded animal's
    return is recorded."""
    folders = _folders(tmp_path, TWELVE_HOURS, ("B", "REFERENCE"))
    with _Rig(tmp_path, monkeypatch, zmq_cleanup, folders=folders) as first:
        first.send(_open(departure=_now()))
        first.seen(_between)
        first.crash = True

    with _Rig(tmp_path, monkeypatch, zmq_cleanup, folders=folders) as second:
        idle = second.seen(lambda f: isinstance(f, Idle))
        assert [s.session_id for s in idle.stranded] == ["2027-01-14_01"]
        second.send(_open(session_id="2027-01-14_02", animal="B", departure=_now()))
        second.seen(lambda f: isinstance(f, Idle) and any("return is not recorded" in r.why for r in f.refusals))
        second.send(_end(session_id="2027-01-14_01"))
        second.seen(lambda f: isinstance(f, Idle) and f.stranded == ())
        second.send(_open(session_id="2027-01-14_02", animal="B", departure=_now()))
        second.seen(lambda f: isinstance(f, Telemetry) and f.subject == "B")

    assert _kinds(folders[2], "2027-01-14_01") == ["departure", "session opened", "returned"]


def test_e2e_an_unknown_preflight_item_is_acknowledged_by_name_and_found_in_runs_jsonl(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup) as rig:
        rig.send(_open(departure=_now()))
        rig.seen(_between)
        rig.send(_start(acknowledged=()))
        shown = rig.seen(lambda f: _between(f) and f.preflight is not None)
        rig.send(_start(acknowledged=UNKNOWN))
        rig.seen(lambda f: _between(f) and f.run_index == 0 and f.stop_kind == "completed")

    assert [i.result for i in shown.preflight.items if i.name in UNKNOWN] == ["unknown", "unknown"]
    start = _runs(rig.folders[2])[0]
    assert {r["name"]: r["acknowledged_by"] for r in start["preflight"] if r["result"] == "unknown"} == {
        "pump calibration": BY, "eye tracker": BY,
    }


def test_e2e_the_departure_and_the_return_meet_the_terminals_rules_over_the_wire(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: every refusal of the departure and the return, through the service as
    through the terminal -- here, one of each over the real link; `test_marks.py` and the
    unit tests above hold every one."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup) as rig:
        rig.send(_open(departure=_now(-3600)))
        rig.seen(lambda f: isinstance(f, Idle) and any("in the future" in r.why for r in f.refusals))
        rig.send(_open(deployment="rig_chaired", departure=_now(2 * 3600)))
        asked = rig.seen(lambda f: isinstance(f, Idle) and f.question is not None)
        rig.send(_open(deployment="rig_chaired", departure=_now(2 * 3600), answer="confirm"))
        rig.seen(_between)
        # Confirmed, so the far question is answered and `welfare`'s own refusal speaks:
        # a return before the departure (`marks.take_return` asks the question first).
        rig.send(_end(returned=_now(3 * 3600), confirm=True))
        rig.seen(lambda f: isinstance(f, Telemetry) and any("having left it at" in r.why for r in f.refusals))
        rig.send(_end(returned=_now(3600)))
        far = rig.seen(lambda f: isinstance(f, Telemetry) and f.question is not None)
        rig.send(_end(returned=_now(3600), confirm=True))
        rig.seen(lambda f: isinstance(f, Idle))

    assert asked.question.answers == ("confirm", "amend")
    assert far.question.answers == ("confirm", "re-type")
    kinds = _kinds(rig.folders[2])
    assert kinds == ["departure", "departure confirmed", "session opened", "returned",
                     "return confirmed", "session ended"]
```

- [ ] **Step 2: Run them, three times**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest tests/test_service.py -q -p no:cacheprovider -k e2e` three times in a row.
Expected: PASS each time. A flake here is a bug in a wait, not bad luck: find the frame the test missed with `seen`'s message before touching a number.

- [ ] **Step 3: Prove a broken command path fails them fast**

```bash
python3 tools/mutate.py --returns None wl_xcon/service.py _route
```
Expected: `caught ... N failed` with the e2e tests among the named failures, in well under the harness's 300 s. If it times out, a wait is unbounded: fix the wait, not the budget.

- [ ] **Step 4: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_service.py
git commit -m "Drive the service end to end over the real link: runs, the limit, a crash"
```

---

### Task 10: Say what changed, prove the tests can fail, and prepare the PI's review

**Files:**
- Modify: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` (a new §6.6), `docs/superpowers/specs/2026-08-31-S9a-console-design.md` (§10, one sentence), `docs/design/architecture.md` (a consistency read)
- Create, **not committed**: `.superpowers/b3a1/welfare-summary.md` (git-ignored), and the mutation logs under `${TMPDIR:-/tmp}`
- **Do not edit `docs/CHECKPOINT.md` or `docs/backlog.md`: the controller writes both** (Step 7 hands it what they need).

- [ ] **Step 1: "Not yet" sentences** (CLAUDE.md: a "not yet" comment is a dated claim)

Run: `git grep -n -e "slice b3" -e "box service" -e "not yet built" -e "nothing yet that holds" -e "terminal-only" -e "the browser will not send" -e "one caller of" -- wl_xcon tasks docs/design`
Rewrite each hit that this branch made untrue to say what is true now, naming what any remaining one waits for (b3a-2, b3b/XC-150, V10). `welfare.Rig`'s docstring is already done (Task 7).

- [ ] **Step 2: The spec, where this plan decided what §6 left open**

In the P4d-2b spec, after §6.5, add:

> ### 6.6 Decided by the b3a-1 plan (2026-09-29), for the PI's review with §6.4
>
> `docs/superpowers/plans/2026-09-29-p4d2b-b3a1-session-service.md` decided what this section left open; the welfare ones are in §6.4's summary.
> - **End session releases the head, then takes the return** (plan decision 6): the release is recorded when End session is pressed, so it is pressed as the animal leaves the chair; the return follows in the same command or a later one. A return typed earlier than the release is refused by `welfare`'s existing cross-check; `now` is always accepted.
> - **`runs.jsonl` has two rows per run**, `start` and `end`, joined by `run` (decision 4), so a run's start and its acknowledgements are on disk before its first trial.
> - **Stranded** means a `departure` row with no `returned` after it, which includes `wlx run`'s `return not recorded` sessions and a record with a torn line (decision 10).
> - **`wlx taskd` needs an allocation carrying `HEAD_FIXED`, `HEAD_RELEASED`, `PARAM_CHANGED`, `RUN_START` and `RUN_END`** (decision 12), where §6.1 listed `--allocation` as optional.
> - **The idle frame is its own shape** on the same socket and schema (decision 8), and **pre-flight adds a starting-values item** (decision 13); `RUN_END` is strobed only for a run that ended by design (decision 5).

In S9a §10, after "**One rule, no exceptions** (PI, 2026-09-19):" list, add: "Built in P4d-2b b3a (`wl_xcon/preflight.py`'s `gate`), for runs started from `wlx taskd`; `wlx run` takes no acknowledgement and records that none was taken."

Read `docs/design/architecture.md`'s welfare-critical paragraphs once through against Plan decision 20, and fix any sentence Tasks 1, 6, 7 and 8 left contradicting another.

```bash
git add docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md docs/superpowers/specs/2026-08-31-S9a-console-design.md docs/design/architecture.md wl_xcon tasks
git commit -m "Record what the b3a-1 plan decided that the spec left open"
```

- [ ] **Step 3: Prove the tests can fail — every new and changed function, read line by line**

**Never run the suite, edit a test or `git add` while a lane is running**: the harness neuters a module's file in place. Each lane is its own `git archive` copy of the branch tip, with `wl-preproc` linked inside it (`tests/conftest.py` looks there) and `PYTHONPATH` set to the copy, so the copy's `wl_xcon` is the one imported, not the editable install:

```bash
PREPROC=/path/to/wl-preproc
tip=$(git rev-parse HEAD)
lane() {  # lane NAME, then "module function" pairs on stdin
  dir="${TMPDIR:-/tmp}/b3a1-lane-$1"
  rm -rf "$dir" && mkdir -p "$dir"
  git archive "$tip" | tar -x -C "$dir"
  ln -s "$PREPROC" "$dir/wl-preproc"
  while read -r module function; do
    (cd "$dir" && PYTHONPATH="$dir" WLX_REQUIRE_PREPROC=1 \
      python3 tools/mutate.py --returns None "wl_xcon/$module.py" $function)
  done > "${TMPDIR:-/tmp}/b3a1-lane-$1.txt" 2>&1
}
lane marks <<'EOF' &
marks --all
stranded --all
welfare restore_departure
EOF
lane preflight <<'EOF' &
preflight --all
record open
record trial
record configure
record run_row
record parameter_change
record close
EOF
lane service <<'EOF' &
service --all
EOF
lane taskd <<'EOF' &
taskd of
taskd task
taskd run
taskd open
taskd end
taskd _fixed_config
taskd _params
taskd _plan
taskd _agent
taskd _control
taskd _apply_staged
taskd end_runs
taskd close
taskd stamp
taskd refuse
taskd receive
taskd publish
taskd _after_service_run
taskd _settle_stamps
taskd _command
taskd duration_warning
taskd return_not_recorded
taskd __post_init__
EOF
lane consoles <<'EOF' &
link of
link encode
link decode
link _telemetry_from
link _idle_from
link _question_in
link _question_out
link _preflight_out
link _refusals_out
link _encode_command
link _decode_command
link _word
link _values
cli _settle_departure
cli _settle_return
cli main
cli render
cli _render_idle
cli _question_line
cli _refusal_lines
cli _moment
web fragments
web _health_pane
web _idle
web _idle_banners
web _idle_refusals
web _question_banner
web _state
web _head
web _banners
web _controls
web _setup
web _end
health expects_frames
health verdict
health _state_text
health _featured
health readings
serve offer
EOF
wait
```

(`taskd of` is `RunSpec.of`; `link of` neuters `Telemetry.of` and `Idle.of` together, as the harness neuters every definition of a name.)

Then read every line of every lane's file, not its exit code:
- every function `caught` with `N failed` and a `<-` naming tests that are about it; `N errors in 0.Ns`, a timeout, or one unrelated test is not a catch (trap 7);
- zero `SURVIVED`, zero `SKIPPED`; `NOT MUTABLE` only for a function whose body already returns at once, named;
- every `baseline:` and `restored:` line the suite's own passed count;
- a lane's `timed out` line is re-run alone, in one lane with nothing else running, before it is believed or blamed; one that still times out is a missing bound, fixed in the owning task.

A survivor is a missing test: write it in the owning task's test file, commit it (with no lane running), and re-run that function alone. A function nothing can test is deleted, not exempted.

- [ ] **Step 4: The welfare-critical surface is what Plan decision 20 says**

```bash
git diff main -- wl_xcon/bounds.py | wc -l
```
Expected: `0`.

```bash
python3 - <<'EOF'
import ast, subprocess
def code(fn):
    """A function's code, its docstring left out: docstrings that named the terminal
    as the marks' only caller were updated on purpose (Task 7 Step 7), and are read in
    the diff below."""
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
UNCHANGED = {
    "wl_xcon/taskd.py": ["Session._ends", "Session._hold", "Session._manual_reward", "Session.set", "Session._schedule"],
    "wl_xcon/link.py": ["_setting"],
    "wl_xcon/welfare.py": ["Welfare.left_cage", "Welfare.returned_to_cage", "Welfare.preflight", "Welfare.must_stop", "Welfare.approaching_limit", "Welfare._refuse_unconfirmed", "Welfare.amend_mark"],
}
for path, names in UNCHANGED.items():
    old = defs(subprocess.run(["git", "show", f"main:{path}"], capture_output=True, text=True, check=True).stdout)
    new = defs(open(path).read())
    for name in names:
        print(("same    " if old[name] == new[name] else "CHANGED ") + f"{path}:{name}")
EOF
```
Expected: every line `same`.

```bash
git diff main -- wl_xcon/taskd.py | grep -n "held\|except (Exceeded, TypeError)"
git diff main -- wl_xcon/welfare.py | grep "^[+-]" | grep -v "^[+-][+-]"
```
Expected: the first prints nothing (`_command`'s two listed parts untouched); the second shows only `restore_departure`, `Rig`'s docstring paragraph, and `_refuse_unconfirmed`'s docstring sentence (Task 7 Step 7).

- [ ] **Step 5: The whole suite, three times**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider -rs` three times in a row.
Expected: all pass each time, and no skip from `test_health.py`, `test_serve.py` or `test_service.py`. Note the passed count for Step 7.

- [ ] **Step 6: The PI's welfare summary**

Write `.superpowers/b3a1/welfare-summary.md` (git-ignored; not committed) for the controller to put to the PI in the question UI as numbered items to approve (memory: he wants items, not files). Plain words, each with the tests that pin it:

1. **The terminal and the page decide the departure and the return with one piece of code** (`marks.py`). The rules are unchanged: a departure not in the future and not past the animal's limit; one more than thirty minutes ago confirmed by a person or amended with a reason and a name; a return not in the future, not before the departure, not while the head is fixed, confirmed if far, never amended. `wlx run` behaves exactly as before — its tests did not change. Pinned by `tests/test_marks.py` and `tests/test_cli.py`.
2. **The page's route into it.** A time arrives as the text a person typed and is read by the terminal's own parser. A far departure is answered *confirm or amend*, a far return *confirm or re-type*, and until then nothing is recorded — for a departure not even the session's folder, so its id stays free. Pinned by Task 7's `test_a_far_departure_is_asked_*`, `test_a_far_return_is_asked_*` and `test_e2e_the_departure_and_the_return_meet_the_terminals_rules_over_the_wire`.
3. **No session opens while an animal's return is missing from the record** — for that animal or any other. At start the service finds every session with a departure and no return, including a `wlx run` session that ended with "return not recorded", and one whose record a crash tore (which stays blocked until the file is repaired by hand). Its return is recorded with End session naming it, checked against its recorded departure under the same return rules; head-fixation is not reconstructed. `welfare.py` gains one method for this, `restore_departure`, which reads the recorded departure back without `left_cage`'s refusals, since those were applied when it was taken — a stranded animal is the one likeliest to be past its limit. Pinned by `tests/test_stranded.py`, Task 7's stranded tests and `test_e2e_a_crash_leaves_the_animal_stranded_*`.
4. **Between runs the out-of-cage clock keeps running and is published**; past the limit the warning reads as "the animal must come back", a new run is refused, and the page asks for the return. The limit still ends a run in progress exactly as it ends a session today (`_ends`, unchanged). Pinned by `test_the_out_of_cage_limit_*` in Task 8 and `test_e2e_the_limit_reached_between_runs_*`.
5. **End session releases the head, then takes the return.** The release is recorded when End session is pressed, so it is pressed as the animal leaves the chair; a return typed earlier than that is refused by the existing check, and `now` always closes the session (which counts a late End session's delay as time out of the cage, the safe direction). Pinned by `test_a_return_typed_before_the_session_was_ended_is_refused_and_now_closes_it`.
6. **Pre-flight before every run, under S9a §10's rule**: any failed item blocks; the pump calibration and the eye tracker's health are unknown until measured, and a run starts only when the person starting it acknowledges each by name, which `runs.jsonl` records. The pump's unknown is acceptable only because no real pump driver exists; when one is written, this must come back to you. `wlx run` takes no such acknowledgement. Pinned by `tests/test_preflight.py`, Task 8's pre-flight tests and `test_e2e_an_unknown_preflight_item_*`.
7. **(If Question 1 was not yet asked, ask it here.)** A reward size changed during a run carries into the session's later runs.
8. **What else is new on the welfare list** (`docs/design/architecture.md`): `marks.py`, `stranded.py`, `preflight.out_of_cage` and `gate`, and the service's `_open`, `_end`, `_close_stranded` and `_start`. Untouched, and checked: `bounds.py`, every listed `taskd` function, `link._setting`, and every `welfare` method but the new one.

- [ ] **Step 7: Hand the controller what CHECKPOINT and the backlog need**

Report, for the controller to write (do not edit either file):
- the passed count (Step 5), the lanes' results (Step 3) with any survivor found and how it was closed, and Step 4's output;
- **backlog items to file** (the `wlx run` allocation defect of Plan decision 12 is already XC-153, filed 2026-09-29 when this plan was reviewed): the collector is not managed during runs, for any session (decision 17); `wlx run` takes no pre-flight acknowledgement (decision 13); b3a-2 — the page's open, start, pre-flight and End-session forms and dialogs, and `serve`'s endpoints for the four commands — with End session shown as two steps (decision 6);
- that XC-016 stays open until b3a-2 lands, and XC-018 still waits on it;
- **the branch merges only after the PI approves Step 6's items**, by fast-forward, once CI's push run is read shard by shard.
