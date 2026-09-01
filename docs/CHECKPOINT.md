# Where this build actually is

**Last updated 2026-09-01**, at the commit this file was committed in. Check
`git log --oneline -1`; if it has moved far, distrust the numbers here before you
distrust the reasoning. Numbers go stale, arguments do not.

**The lab opens January 2027.** Everything is being built before any rig exists.

> **"January validates rather than discovers" was the working assumption and it is
> false.** Review caught it on 2026-08-31: it is load-bearing, because it justifies
> spending effort on the task layer instead of on the four things that must work on
> day one — **DIO out, gaze in, a frame on screen, reward out**. Two of those four now
> exist and are proven without hardware (`dio.py`, `eye.py`); the other two are
> genuinely blocked on a card and a panel. Until a rig runs all four end to end,
> **January discovers.** Sequence accordingly.

Nothing here has touched hardware.

---

## Read this much, and no more

24 design documents exist. **Do not read them all.** In order:

1. **This file** — where things are.
2. **`CLAUDE.md`** — the conventions, including three that were learned the hard way.
3. **`docs/M0-REVIEW.md`** §3 and §4 — what is still open, and the 24 engineering
   calls made without asking.
4. **The one S-spec your package names**, from the table below. Not the others.

`docs/superpowers/specs/2026-08-31-spec-map.md` maps S0–S13 if you need to find one.

---

## Status

**M0 signed off 2026-08-31.** Contracts frozen; code started.

| | |
|---|---|
| Tests | **194, green** |
| CI | pytest on 3.11, 3.12 and 3.13, plus a **mutation gate over every module**. Verified by sweep on 2026-09-01: `check`, `task`, `run`, `scheduler`, `photometry`, `eye`, `dio` — 0 survivors. The only non-caught entries are no-op `display` bodies, where `return None` mutated to `return None` is not a mutation |
| Reference tasks | `fixation_detection`, `adaptive_detection`, `visual_search` (colour pop-out, set size 2–12) |
| Load-time checks | **9 of S1 §9's 10, plus S1a's window check, plus nine added after review 2026-08-31** (`uncoupled-window`, `nothing-to-look-at`, `absent-stimulus`, `duplicate-stimulus`, `empty-update`, `uncalibrated-color`, `unrealizable-color`, `overspecified-color`, `unstated-observer`, `target-outside-array`, `impossible-correlation`, `monocular-stereogram`, `unknown-eye`, `wrong-eye-criterion`).** Check 7 is enforced for reward and *not* for stimulation, because no `Stim` action exists yet. Corrected 2026-08-31 after review caught the count |
| Cross-repo asks outstanding | **4 documents, 3 repos** — see below |
| Hardware verified | **none** |
| Day-one path (DIO out · gaze in · frame on screen · reward out) | **2 of 4 built and proven without hardware**; the display and the real card remain |

### What exists

- `task.py` — the declarative trial: states, guarded transitions, actions, parameters.
- `check.py` — the load-time checks. Check 8 runs *per eye, after disparity*:
  a stimulus inside the cyclopean field can still put one eye's image outside it.
- `geometry.py` — the split-screen field, derived from S0 §5.2's formula with tests
  asserting agreement with the optics drawing.
- `review.py` + `wlx review` — the artifact a task is approved from: Mermaid diagram,
  event-code table **named by transition**, a **display timeline**, window coupling
  and eye, parameter ranges, what needs human review, stimuli.
- `photometry.py` — colour as a physical claim: CIE xyY and DKL cone contrast,
  checked against a measured `Calibration`. **No calibration for our panels exists**,
  so chromatic tasks will not load until one is committed under `docs/measurements/`.
- `eye.py` — OpenIrisDPI's UDP protocol (`WAITFORDATA` on 9003), P1−P4 as the gaze
  signal, hold-last with a 50 ms staleness ceiling. Tested over a loopback socket.
- `dio.py` — the breakout's pin map: 16 event bits on **P0.8–P0.23**, strobe, reward,
  stim trigger, four inputs. `Absent`, `Simulated` and the real card as peers.
- `tasks/` — three reference tasks (`fixation_detection`, `adaptive_detection`,
  `visual_search`) and the reference allocation. `wl-mllib`'s to
  own eventually; here until it exists.
- `encode.py` — the 16-bit strobed word stream. Round-trips through `wl-preproc`'s
  own `decode_stream` and matches their `encode_payload` exactly across the uint32
  range. **We deliberately write no decoder.**
- `run.py` — the trial loop. Hardware, behaviour agents and demo mode are peers the
  loop cannot distinguish.
- `simulate.py` — sessions and the census: outcomes, states visited, hangs, and
  outcomes nothing reached.
- `cli.py` — `wlx check`, `wlx review`, `wlx run`; exit 1 on a blocking finding.
- **`bounds.py` — the welfare-critical file, and currently the only one.** Ceilings a
  task cannot express and a console cannot exceed; fluid reconciled against the
  delivered line rather than what we commanded; an unknown daily total refuses
  delivery. **Requires human review before merge** (CLAUDE.md).
- `tools/mutate.py` — proves a test can fail. Read its docstring before trusting a
  mutation result by hand.

### What does not exist, and matters

- **`taskd` is a spine, not a daemon.** It runs a session end to end and meets M1,
  but there is no console link, no live parameter path and no preflight. Those are
  P4 and later.
- **Parquet is not written.** JSONL is the durable streamed record; the columnar
  table is a derivation at session close that does not exist yet. Deliberate: a
  Parquet file is only valid once closed, so it cannot be the crash-safe record.
- **The round-trip tests skip in CI**, because they need a `wl-preproc` checkout
  beside this repo and CI has none. So **CI cannot currently catch an encoder
  drift** — the strongest test in the suite is the one CI does not run. Fixing it
  needs `wl-preproc` pinned as a git dependency, which needs a token for a private
  repo. Recorded rather than hidden.

---

## What moved on 2026-09-01

Two external reviews (`nhp-neuroscience-reviewer`, `senior-scientist`) found one
thing between them, and it is the entry worth reading if you read nothing else here:
**every load-time check inspected the same object.** Unreachable-state,
unbounded-wait, no-outcome-path and shadowing are four views of the transition graph,
so adding checks raised the count without narrowing the residual class — and the
residual class was tasks whose graph is right and whose *experiment* is wrong. See
trap 9 and pitfall P18.

Seventeen commits. In dependency order:

1. **A hold clocked from the wrong zero** (`67acf4a`). A memory-guided structure with
   a declared 0.3 s delay ran it for **one frame, 4.2 ms**, and scored `CORRECT`.
   Task written correctly, all ten checks passing. Every working-memory delay in the
   v1 inventory was written that way.
2. **The display now exists as state** (`284f7f2`). `Show` persists until `Hide`
   rather than being scoped to its state — the old wording removed a fixation point
   at the exact frame the animal was asked to hold it. Stimuli have names; `Update`
   changes a live one without the offset transient `Hide`+`Show` inserts; a `Window`
   names the stimulus it scores or `REMEMBERED`. Closed **statically and
   dynamically**: the simulated animal now sees the screen and will not look at a
   stimulus that is not there.
3. **Colour** (`045d626`), in CIE xyY and DKL, on the *appearance* so it is a value a
   parameter can swap. Refused without a measured `Calibration`.
4. **Set size as a value** (`470bcec`). `Array` as an appearance, `ItemWindows` as one
   declaration that becomes n windows plus `.target`/`.distractor`.
   `tasks/visual_search.py` — colour pop-out — was unwritable before this.
5. **Anticorrelated RDS and disparity-defined form** (`b86e89f`), plus `Window.eye`,
   which was parsed and dropped.
6. **Intervals from photodiode onset** (`955a6d8`). `After(0.05,
   since=Onscreen("task"))`. An `After` with a `since` is deliberately **not** a time
   bound, and check 4 refuses it as one.
7. **Five outcomes** (`591ba2c`): `CORRECT_REJECT`, `FALSE_ALARM`, `FAULT`,
   `BLINK_BREAK`, `TRACKER_LOST`, with independent blink and tracker graces.
8. **Range-based checks** (`3871a39`): overlapping windows, unreachable timeouts,
   crowded arrays.
9. **The review artifact** (`4e3e023`) grew a display timeline and now names the
   transition that emits each code.
10. **Gaze ingest** (`532fb54`) and **DIO** (`ae07656`) — the pivot.

### Things that were wrong and are now right

- `tasks/visual_search.py` allowed **twelve items on a 3° ring with 4° windows** —
  adjacent centres 1.55° apart, 8° of summed window. A saccade to one distractor
  would have been scored against another. It passed every check that existed the day
  it was committed. Found only when the crowding check was written a day later.
- The **review artifact crashed** on any task using `ItemWindows`, because the
  vocabulary gained a window kind and nothing rendered it.
- **The event-codec round-trip had never run in CI.** `actions/checkout` fetches this
  repo alone, so `importorskip` skipped all nine tests into a green build. They pass
  against `wl-preproc`'s real decoder; nothing was proving it. CI now checks out the
  sibling and sets `WLX_REQUIRE_PREPROC=1`.
- The new outcomes were **not in the requeue set**, so a trial lost to a dropped
  camera left its condition silently one datum short.
- The **mutation harness aborted `--all`** at the first unmatchable signature and
  reported a completed sweep. Fourth blind spot of that shape.

## Work packages

One session each. Each names what to read; **reading more than that is how a session
runs out of context before it produces anything.**

| | Package | Exit condition | Read | Blocked on |
|---|---|---|---|---|
| ~~P0~~ | ~~Make the repo resumable~~ | **done 2026-08-31** | — | — |
| ~~P1~~ | ~~Finish the task layer~~ | **done 2026-08-31** — checks, both reference tasks, `wlx check` and `wlx review`. Reopened the same day: review found the display was modelled nowhere | — | — |
| ~~P2~~ | ~~Session record~~ | **done 2026-08-31** — streamed JSONL, config snapshot, parameter-change log, and `run_session` writing a real directory | — | — |
| ~~P3~~ | ~~`taskd` skeleton~~ | **done 2026-08-31 — roadmap M1 met**: 1,000 deterministic trials, headless, full record, `wlx run` | — | — |
| **P4** | Demo mode: JSONL events, parquet behaviour, config snapshot, directory layout | A simulated session writes a real session directory | S10, S3, S8 | nothing |
| | → **roadmap M1** | 1,000 deterministic trials with full outputs | S8, S9 | — |
| | + operator documentation | The D4 acceptance test; a stranger runs a session | S9 | — |
| **P4b** | Session management: blocks, scheduler, bounded config, welfare accounting, the live parameter path | A session runs blocks with criterion transitions and enforces its ceilings | S8 | nothing |
| P4c | Parquet derivation at close; the `labhost` endpoint | Contract-tested against `wl-preproc`'s published schema | S10 | nothing |
| P4d | The console shell against a fake `taskd` | An operator surface that runs with no rig | S9, S9a | nothing |
| P5 | Display adapter, stereo viewports, photodiode patches | Photodiode-ready display | S4, optics | **hardware — ADR-0002 deferred to V1** |
| **P6** | Eye ingest, calibration, saccade detection | Replay-driven gaze, and a calibration map `wl-preproc` can read | S5 | their reader |
| | → ingest | **done 2026-09-01** — protocol verified from source, loopback-tested; calibration and saccade detection remain | — | — |
| **P7** | I/O behind interfaces: NI DIO, reward, comparator inputs | Absent, simulated and hardware as peers | S6 | hardware to verify |
| | → the interface | **done 2026-09-01** — pin map, refusing `Absent`, recording `Simulated`; the `nidaqmx` implementation needs a card | — | — |
| P8 | Neural plane, both feature sources | post-v1 | S7 | hardware |

**P1–P4 needed no hardware and are done. P4b–P4d need none either**, so the runway
without a rig is longer than it looked — and it now covers the welfare-critical code,
which wants human review time more than anything else does.

**ADR-0002 is deferred to V1** (2026-08-31): neither display stack is built properly
until a rig can measure both. So P5 is hardware-blocked, and the display spike stays a
spike.

---

## Outstanding asks on other repositories

One consolidated handover sits in each repo as `HANDOVER-wl-expcontroller.md`.
**Committed in `wl-sync`; written but uncommitted in `wl-preproc` and `wl-works`**,
because the first was on a feature branch with work in flight and the second is owned
by another worker including its remote.

| Repo | Blocking? | Ask |
|---|---|---|
| `wl-sync` | **yes** | The session id is unreadable by a rig host, so `taskd` cannot name its own output directory. And two animals a day means a subject change must mint `_02` |
| `wl-preproc` | **yes** | `read_online_map` reads a `.bhv2` that will not exist, so `CalibrationSource.ONLINE` is unavailable for every session |
| `wl-preproc` | no | `PARAM_CHANGE` escape; ownership split recorded; codec declared as an artifact; per-trial gaze staleness |
| `wl-works` | no | `prepare-session`, a planned calibration block per session, alerting on bad readings |

Neither blocking item stops P1–P4. Both are built around: codes are allocated in
**4096–32767** (undisputed) and the session id sits behind a provider interface.

---

## Open measurements this creates

**A photometer measurement now gates every chromatic task.** `check` refuses colour
without a `Calibration`, and a real one needs a spectroradiometer or colorimeter on
the actual panel: primaries and background in CIE xyY, gamma, the reachable cone
contrast, and **whose luminous efficiency the luminances were measured against** --
a macaque V(lambda), not a human one, or `lum=0` is isoluminant for nobody in the
room. Result goes under `docs/measurements/`. Until then chromatic tasks will not
load, which is the intended failure: the alternative is a task that runs, looks
convincing, and reports a colour nobody measured.

## Traps

Things that cost something to learn here. Each is a convention in `CLAUDE.md` now.

1. **Read the neighbouring repository's source, not its manifest.** `wl-mllib`'s
   manifest said the event vocabulary was unallocated; `wl-preproc` had a frozen
   codec. This project came within one spec of building a second one. Twice more
   since: `expcontroller/` was already reserved for us by name, and the eye
   calibration model was already fixed.
2. **`wlo validate` cannot catch a false description.** It checks that a published
   name resolves to one publisher, never that what it says is true.
3. **A ring of calibration targets is degenerate** on the second-order basis, because
   points on a circle make the constant, dx² and dy² columns linearly dependent. The
   intuitive pattern silently forecloses second-order calibration.
4. **Clear `__pycache__` when mutating.** Doing it by hand left stale bytecode and
   reported failures against already-correct code. The same staleness the other way
   reports a false *pass*. Use `tools/mutate.py`.
5. **Writing a real task found four gaps specification had not.** Missing vocabulary
   (`GazeHeld`, `SaccadeInto`, transition actions), a checker blind to transitions
   that passed a task emitting an unallocated code, a runner that never resolved
   parameters, and a subject that could not lapse mid-trial. **Write the artifact
   before trusting the machinery that makes it.**
6. **A killed mutation run once left a neutered method on disk, and it was committed
   and pushed** — the timeout bypassed the `finally` that restores, and the commit did
   not re-run the suite. Fixed both ways: the harness writes a sentinel and heals on
   its next run, and the rule stands that **nothing is committed without a green
   suite in the same breath**. `git add -A` after a long-running command is the shape
   of the mistake.
7. **The mutation harness has been wrong four times, always the same way** — quietly
   examining nothing and reporting success. It matched only `_`-prefixed names, then
   only module-level `def`, then gave up entirely on a name defined twice, then
   **aborted the whole `--all` sweep at the first signature it could not match** --
   `def __repr__(self) -> str:  # pragma: no cover`, whose trailing comment defeated
   the pattern -- so every function after it went unmutated and the run read as
   complete. Each time it found real gaps once fixed, including a dead `per_eye`
   method and an untested CLI. **If a module reports few functions, distrust the tool
   before the code**, and a miss is now reported rather than fatal.
8. **A pure hazard model cannot produce non-engagement**, and hazards are rates
   per second — a per-frame number describes a different animal at every refresh rate. It fires eventually given
   enough frames, so `NO_FIXATION` — the commonest real abort — was unreachable in
   every simulated session until engagement became per-trial.

9. **Every check inspected the same object, so a whole defect class was invisible.**
   Unreachable-state, unbounded-wait, no-outcome-path, shadowing — all three views of
   the transition graph. Nothing modelled what was *on the screen*, when, or for how
   long, so the residual class was **"correct graph, wrong experiment"**, and the
   first reference task carried one: `Show` was scoped to its state, so the fixation
   point was removed at the exact frame the animal was asked to hold it. The task read
   correctly, all ten checks passed, and 2,000 simulated trials reported clean.
   Fixed by making `Show` persist until `Hide`, giving stimuli names, coupling each
   `Window` to the stimulus it scores, and adding both a static check
   (`nothing-to-look-at`) and a dynamic one (a simulated animal will not look at a
   stimulus that is not there). Found by review 2026-08-31.
   **The general lesson: ask what a gate is looking at, not how many gates there are.**


10. **A feature that stops a human writing something out also stops a human reviewing
    it.** `Array` and `ItemWindows` exist so set size is a value rather than a
    structure — which means the items and their windows are never typed and never
    read. `tasks/visual_search.py` shipped allowing twelve items on a 3° ring with 4°
    windows: adjacent centres 1.55° apart, 8° of summed window, so a saccade to one
    distractor would have been scored against another. It passed every check that
    existed the day it was committed. Found only when the crowding check was written.
    See P20.

11. **The review artifact is the review, so what it omits is unreviewed.** It rendered
    stimulus position and disparity and nothing about time — while every defect the
    reviews found was about *when* something was on screen. It also raised
    `AttributeError` on any task using `ItemWindows`, because the vocabulary gained a
    window kind and nothing rendered it, and no test rendered a task with an array.
    **When you extend the vocabulary, extend the artifact in the same commit.**


12. **The mutation harness can hang, and a hang is how the sentinel gets used.**
    Neutering `Scheduler.record` stops the counts advancing, so a test running a
    block to completion never finishes; the suite hung, an outer timeout killed the
    harness past its `finally`, and a neutered `scheduler.py` was left on disk. The
    sentinel restored it correctly on the next check — it works — but the fix is a
    per-run timeout in the tool, and a mutation that hangs now counts as caught,
    because a suite that no longer terminates has certainly noticed it.
    **Never `git add` immediately after a mutation run that did not print `restored:`.**
