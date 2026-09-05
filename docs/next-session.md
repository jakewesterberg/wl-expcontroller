# Next session — wl-expcontroller

**State at handoff:** `main`, **307 tests passing**, working tree clean, **0 unpushed
commits**, and **CI green** — for the first time in the repository's history, verified
by watching the run rather than by reading the workflow. No hardware exists.

> **Read `docs/CHECKPOINT.md` first, then this.** The checkpoint says where the build
> is; this says what to do. There are 25 design documents and **you should read three**:
> the checkpoint, `docs/M0-REVIEW.md` §3–§4, and
> `docs/superpowers/specs/2026-08-31-S8-session-management-design.md`. Reading more is
> how a session exhausts its context before producing anything, and that is the
> specific failure this file exists to prevent.

---

## 0. Check this before believing anything below

```
git log --oneline -1 && git status --short && git log --oneline origin/main..main
```

**Trap 17, learned expensively on 2026-09-05.** Nothing was pushed for four days while
this file and the checkpoint both described CI behaviour that had never executed. The
first push found seven bugs in five runs, including a Python 3.11 syntax error that
made `wlx review` unimportable on this package's own declared floor. **A green local
suite says nothing about CI**, and unpushed commits are how every one of those hid.

---

## 1. P4b — session management, and the welfare-critical code inside it

**Exit condition:** a session runs blocks with criterion transitions and enforces its
ceilings. Read **S8**.

**Start here, because it is the thing that is actually wrong.**
`bounds.check_delivery` is **called by nothing outside its own tests.** Grep it. The
welfare-critical module — the one CLAUDE.md singles out as requiring human review
before merge — enforces nothing today, because no code path consults it. `run.py`
resolves a `Reward` action into nothing at all: its own comment says `Mark` and
`Reward` "belong to the I/O layer, which has no simulator yet". So a task can command
reward, a session can run to completion, and no ceiling is ever asked.

That is not a missing feature. **A bound that nothing calls is a bound that reads as
present and is not**, which is worse than an absent one — the same shape as the
mutation gate that could never go green and the checker that examined nothing (traps 7
and 18). Fixing it is the first thing worth doing here.

**Second: `taskd` does not use the scheduler.** `scheduler.py` exists, is
mutation-clean, and handles blocks, conditions, quotas, requeue-on-abort and criterion
transitions. `taskd.py` never imports it. A "session" today is a flat run of trials, so
blocks, criteria and per-condition quotas exist as a component nothing drives.

**Third, and it is the same session boundary:** the calibration block still does not
run in a session.
`tests/test_gaze.py::test_a_whole_calibration_block_produces_an_installed_map`
composes every piece — scheduler, task, collector, fit, `MappingLog.install` — and
**that test is the shape the driver takes**. Nothing writes the map to
`<session>/expcontroller/*.yaml` at close, though `calibration.GazeCalibration.to_yaml`
already produces exactly the bytes `wl-preproc`'s reader accepts.

**Requires human review before merge** (CLAUDE.md). Keep the welfare-critical surface
small, and say plainly in the PR what a reviewer has to check.

---

## 2. Traps specific to this work

- **Fluid is reconciled against the delivered line, not what was commanded.**
  `bounds.reconcile` exists for this and the distinction is the point: a solenoid that
  did not open delivered nothing, whatever the command said.
- **An unknown daily total refuses delivery.** `bounds.Unknown` is not an error path to
  smooth over; it is the designed answer to "we do not know how much this animal has
  had today".
- **`counts_toward` and `criterion_over` are deliberately separate** (`scheduler.py`).
  A block may count every presentation toward its quota while judging performance only
  on completed choices, and conflating them makes a criterion track engagement rather
  than what the animal can do.
- **The detector and the mapping are both versioned, and every trial cites both.**
  `saccade.VERSION` and `MappingLog.version`. S5 §5 and §6 make a change to either a
  discontinuity of the same class as a parameter change (P16).
- **Never `git add` after a mutation run that did not print `restored:`** (trap 12).
- **A new module must be declared in `tools/mutation_gate.py`**, in `RETURNS` or in
  `EXEMPT` with a reason. The gate fails otherwise, on purpose — that guard is how
  three modules were found ungated, one of them `bounds` (trap 18).

---

## 3. Do not do these, and why

- **Do not start the display (P5).** ADR-0002 is deferred to V1; neither stack is built
  properly until a photodiode on a rig can compare them.
- **Do not write a `nidaqmx` implementation you cannot run.** `dio.py`'s interface is
  the deliverable; guessing at DAQmx semantics now means rewriting it later.
- **Do not add Parquet yet.** JSONL is the durable streamed record deliberately; the
  columnar table is a derivation at session close, and it is P4c with S10.
- **Do not allocate event codes outside 4096–32767.** `TaskEvent` 256–4095 still needs
  `wl-preproc`'s agreement on ADR-0007.
- **Do not add a load-time check before reading P18 and trap 9.** More gates over the
  same object is what produced the defect class the reviews found.

---

## 4. Waiting on people, not on code

| Who | What | Blocks |
|---|---|---|
| `wl-sync` | Session id readable by a rig host; a subject change mints `_02` | naming our own output directory |
| `wl-preproc` | `PARAM_CHANGE` escape; ownership split; codec as an artifact | P16's guarantee |
| `wl-works` | `prepare-session`, a calibration block per session, alerting | ELN autopopulation |
| PI | **A photometer measurement of the panel** | every chromatic task (P19); `tasks/visual_search.py` is what waits |
| PI | IPD per animal; the tandem panel's two questions | optics, panel |

**Closed 2026-09-05:** `wl-preproc`'s online-calibration reader — they built it, and
its source fixes the schema — and the licence question. Every `wl-*` repository is now
Apache-2.0, `Copyright 2026 Jacob A. Westerberg`, with `wl-expcontroller` and
`wl-preproc` public.

---

## 5. After P4b

P4c: the derived Parquet table at session close, then the `labhost` endpoint (S10 §4),
which can be contract-tested against `wl-preproc`'s published schema without them
answering anything. Then P4d, the console shell against a fake `taskd`.

**Do not skip ahead to hardware work to feel productive.** Everything on that side is
blocked on a card, a panel, or a photometer, and none of the three is ours to hurry.
