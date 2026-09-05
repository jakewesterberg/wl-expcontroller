# Where this build actually is

**Last updated 2026-09-05**, at the commit this file was committed in. Check
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
| Tests | **307, green** |
| CI | pytest on 3.11, 3.12 and 3.13, plus a **mutation gate**. Selective since 2026-09-05: `tools/mutation_gate.py` runs the modules a change can have affected and escalates to all of them on anything structural, with the **full sweep nightly** — the per-push gate cannot see a test deleted from one file that was the only cover for a function in another. It refuses to run at all if a module is in neither its gated nor its exempt list. Functions that already return immediately are reported `NOT MUTABLE` rather than counted as survivors (trap 7) |
| Reference tasks | `fixation_detection`, `adaptive_detection`, `visual_search` (colour pop-out, set size 2–12), `calibration` |
| Load-time checks | **9 of S1 §9's 10, plus S1a's window check, plus nine added after review 2026-08-31** (`uncoupled-window`, `nothing-to-look-at`, `absent-stimulus`, `duplicate-stimulus`, `empty-update`, `uncalibrated-color`, `unrealizable-color`, `overspecified-color`, `unstated-observer`, `target-outside-array`, `impossible-correlation`, `monocular-stereogram`, `unknown-eye`, `wrong-eye-criterion`).** Check 7 is enforced for reward and *not* for stimulation, because no `Stim` action exists yet. Corrected 2026-08-31 after review caught the count |
| Cross-repo asks outstanding | **4 documents, 3 repos**; one blocking ask closed 2026-09-05 — see below |
| Hardware verified | **none** |
| License | **Apache-2.0**, ADR-0004 accepted 2026-09-05. Repository public |
| Day-one path (DIO out · gaze in · frame on screen · reward out) | **2 of 4 built and proven without hardware**; the display and the real card remain. Gaze now reaches degrees as well as pixels |

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
- `calibration.py` — raw Purkinje vector to degrees, per eye. The model and the file
  are both **wl-preproc's**, read from their source; ours is the procedure. Thirteen
  targets (measured, not chosen), three refusals in a deliberate order — count, then
  conditioning, then extent — and a YAML file round-tripped through their real reader
  in CI. `EyeMap.degrees` is the trial-loop path and allocates nothing.
- `findings.py` — the `Finding` dataclass, lifted out of `check.py` so `calibration`
  can report refusals in the same words without a circular import.
- `saccade.py` — online Engbert-Kliegl, and the batch form it is checked against.
  The algorithm is **`wl-preproc`'s**, chosen by S5 §5 precisely so online-versus-
  offline disagreement measures staleness and latency rather than two methods — and
  a contract test proves ours finds *the same intervals theirs finds*, which is what
  that argument actually rests on. Per-trial adaptive threshold, the S5 §5 stall rule,
  and a detection whose window touched a gap is flagged rather than dropped.
- `gaze.py` — **the join**: `eye.Tracker` + a versioned `Mapping` + a trial's windows,
  behind `run.World`. Replayed OpenIrisDPI payloads reach a `Window` test in degrees,
  which is P6's exit condition. Polls the tracker in `display`, the loop's only
  per-frame call that lands before the frame's guards. `SaccadeOnset` and `SaccadeTo`
  are **different events**: onset fires at confirmation, while the eye is still in
  flight and has landed nowhere; `SaccadeTo` waits for the run to close and then asks
  where. A saccade is consumed by whichever guard takes it, or one saccade becomes a
  stream of them.
- `tasks/calibration.py` — the calibration block, written in the ordinary task
  vocabulary. It passes every load-time check with zero findings, which is the
  finding: the vocabulary can express its own calibration.
- `tools/mutate.py` — proves a test can fail. Read its docstring before trusting a
  mutation result by hand.
- `tools/calibration_design.py` — which constellation the block should present, and
  why. Results in `docs/measurements/dev-machine/2026-09-05-calibration-constellation.md`.

### What does not exist, and matters

- **`taskd` is a spine, not a daemon.** It runs a session end to end and meets M1,
  but there is no console link, no live parameter path and no preflight. Those are
  P4 and later. **It also never imports `scheduler.py`**, so blocks, quotas and
  criterion transitions exist as a mutation-clean component that nothing drives.
- **`bounds.check_delivery` is called by nothing outside its own tests.** The
  welfare-critical module enforces no ceiling today, because no code path consults it:
  `run.py` resolves a `Reward` action into nothing, its comment noting that `Mark` and
  `Reward` "belong to the I/O layer, which has no simulator yet". **A bound nothing
  calls reads as present and is not**, which is the same shape as trap 7's checker and
  trap 18's gate. It is the first thing P4b should fix.
- **Parquet is not written.** JSONL is the durable streamed record; the columnar
  table is a derivation at session close that does not exist yet. Deliberate: a
  Parquet file is only valid once closed, so it cannot be the crash-safe record.
- **CI is green, 2026-09-05 — for the first time ever.** Of 28 runs in this
  repository's history, exactly one has passed, and it is the one after the fixes
  below. Everything in this entry was found in five runs on one afternoon, after
  four days in which nothing was pushed and every claim about CI was therefore
  about a thing that had never executed.

- ~~**CI is red, has been since 2026-08-31, and nothing since has been pushed.**~~
  Established 2026-09-05 by reading the runs rather than the workflow file. Three
  facts, each of which was believed otherwise:
  - The last pushed run (`33439705522`) fails with **three survivors in the mutation
    gate** — `words_for`, `words_for_code` and `_checksum`. They are caught by the
    codec round-trip alone, and the round-trip was skipping (`1 skipped`) because
    that job had no `wl-preproc`. A mutation gate running without its contract tests
    reports that tests can fail while the ones that would have failed did not run.
  - **`main` is 18 commits ahead of `origin/main`.** Everything from 2026-09-01 and
    2026-09-05 — including the 09-01 fix that added the checkout to the test job —
    has never run in CI at all. The fix was believed to be in force for four days.
  - **That fix would not have worked.** It used `path: ../wl-preproc`, and
    `actions/checkout` resolves `path` against `$GITHUB_WORKSPACE` and **throws** on
    anything that escapes it (verified 2026-09-05 against `src/input-helper.ts`
    lines 40–53 in `actions/checkout`, not against its README). Corrected to a path
    inside the workspace, with `tests/conftest.py` searching both locations.

  **Green, 2026-09-05**, verified by watching the runs rather than by reading the
  workflow. The three encoder mutations that had been surviving since 2026-08-31 --
  `words_for`, `words_for_code`, `_checksum` -- are caught now that the round-trip
  actually executes, which is the first evidence that gate ever worked. One further
  survivor surfaced with it: **`review._scores_label` was covered by no test**, so
  the artifact's window-coupling column -- which stimulus each window scores, and
  whether it is `REMEMBERED` or nothing at all -- rendered unchecked. Trap 11 again,
  and found only because the gate finally ran. A second run then surfaced
  `Unchanged.__repr__`, uncovered -- **newly visible rather than newly broken**: trap
  7 records that the harness's old pattern could not match
  `def __repr__(self) -> str:  # pragma: no cover`, so it had been skipped in
  silence. Fixing the pattern made it reachable and CI made it audible. Resolved by
  testing the sentinel rather than by teaching the harness to honour the pragma,
  because a category of exemption anyone can open with a comment is this tool's
  sixth failure waiting to happen.

- **CI green with the selective gate, 2026-09-05.** `bounds` and `scheduler` have
  now been mutation-tested in CI for the first time, and the run that did it
  escalated to all nineteen modules because the workflow itself had changed --
  which is the escalation rule working rather than a coincidence.

  **A full sweep costs 47-61 minutes** (read off GitHub's own run durations for runs
  `33963919596`, `33966768083`, `33971576019`, `33972113194` on 2026-09-05 -- not a
  claim about the rig, and not from `tools/`). That is per push, and it grows with
  every module and every test, which is why the gate became selective rather than
  merely faster.

- **Three modules were never in the CI mutation gate at all**, found when the
  hand-maintained list in the workflow was replaced by one derived from disk:
  `bounds` — **the welfare-critical module** — plus `scheduler` and `findings`. This
  file has said "a mutation gate over every module" since M0. Both `bounds` and
  `scheduler` pass a sweep, so nothing was actually wrong with them; what was wrong
  was the claim. See trap 18.

  **Pushed and watched, 2026-09-05.** Run `33956427875`: the path fix was correct and
  a **third**, independent fault was underneath it. `GITHUB_TOKEN` is scoped to this
  repository, so checking out a second private one returns `Not Found` — which is the
  token problem this file recorded in the abstract ("needs a token for a private
  repo") without connecting it to the checkout that was believed to work.

  **CI is red now and stays red until someone creates a secret.** It needs a
  fine-grained PAT with `Contents: read` on `jakewesterberg/wl-preproc`, added as the
  repository secret `WL_PREPROC_TOKEN`. A step before each checkout says exactly that
  rather than letting the failure surface as `Not Found` from an action that cannot
  explain itself. **Red is the correct state**, not a thing to route around: the
  round-trip and the calibration contract are the only checks that we emit their
  protocol and fit their model rather than our idea of either, and a contract test
  that is allowed to not run is not a contract test.

  Three ways of getting one checkout wrong, each of which looked fixed: no checkout,
  a path outside the workspace, and no credentials for it.

---

## What moved on 2026-09-05

**Eye calibration, and a cross-repo blocker that was already unblocked.**

`wl-preproc` had written `eye/expcontroller.py::read_expcontroller_map` — a reader
built for us, in answer to our own handover — and this file still listed the ask as
blocking. **Reading their source rather than our note about it is what found it**,
which is trap 1 for the fourth time. Their reader fixes the schema, so most of what
looked like design work was already decided.

- **The constellation is measured, not chosen** (`tools/calibration_design.py`,
  results under `docs/measurements/dev-machine/`). Thirteen targets: a 3×3 grid at 75%
  of the per-eye field plus four intermediates on the diagonals at half that.
- **75% reach beat 60%, 70%, 85% and 100%** under every optics assumption swept, and
  the intuitive answer — span the whole field — was the *worst* of the five. The panel
  corners sit near 21° eccentricity, outside the disc any task uses, and their leverage
  drags the quadratic away from where stimuli go.
- **Thirteen points buy survival, not accuracy.** At equal animal cost 9, 13 and 25 are
  indistinguishable. Nine points fitting six parameters has three to spare, so losing
  four makes the second-order fit impossible rather than merely poor; thirteen survive
  losing five 95% of the time.
- **`calibration.py`**: per-eye fit, second-order reaching down to affine with a
  reported fallback, three refusals ordered count → conditioning → extent, and the YAML
  file round-tripped through their real reader.
- **`findings.py`**: `Finding` lifted out of `check.py`, because the extent check will
  eventually run the other way round and a circular import was waiting.
- **The CI mutation job now checks out `wl-preproc`.** It did not, so contract tests
  skipped inside the gate that exists to prove tests can fail.

**The rest of P6, later the same day.** The fit had no producer and no consumer;
both now exist.

- **`tasks/calibration.py`** — the block as an ordinary task. It passes all load-time
  checks with **zero findings**, which is the result worth recording: the previous
  four times a real artifact was written against this vocabulary it exposed a gap
  (trap 5), and this time it did not.
- **The map is one versioned object** (S5 §6). `MappingLog` is session-scoped and
  append-only; `Mapping` carries the recentering offset **beside** the coefficients
  rather than folded into them, because a folded constant is indistinguishable from a
  fit that landed there and S5 requires the correction be reversible offline. The file
  folds it, since their schema has nowhere else to put it, and the change log is what
  survives.
- **Version 0 maps nothing.** A session before its calibration block answers `None`
  for degrees rather than zeros — the same refusal `eye.Tracker.state` makes at the
  other end, for the same reason: a tracker reporting the origin scores a hold against
  an empty chair.
- **`gaze.Tracked` joins four modules** and P6's exit condition is met — replayed
  payloads reach a `Window` test in degrees, and a whole thirteen-target block runs
  from scheduled conditions to an installed map.
- **A recentering replaces rather than accumulates**, and a refit drops it. The second
  recentering was measured against gaze the first had already corrected, and an offset
  describes a chair position under the map it was measured against.

### One bug the join found immediately

**Polling gaze in `in_window` kills the trial at frame 7.** `World.display` is the
loop's only per-frame call that lands *before* the frame's guards; `signal` runs next
and `in_window` last. With the poll in `in_window`, `signal` saw a sample nothing had
refreshed, the staleness ceiling expired mid-hold, and the trial scored
`TRACKER_LOST`. It looked exactly like a dropped camera. **Anything a world needs to
do once per frame belongs in `display`**, whose docstring already said so.

### Two ideas measured down, recorded so they are not proposed again

**Holding four targets out as a validation set.** Attractive, and wrong at this budget:
four points at ten fixations each carry a noise floor the size of the error being
estimated, so the held-out number overstates true error by 34–51% *whether the model
fits or not*, with a ±0.05° spread between identical sessions. It cannot estimate
accuracy and it cannot detect misfit, which were the two reasons to want it.

**A ring plus a centre as an acceptable constellation.** `docs/next-session.md` offered
it as equivalent to a grid. It scores 0.1697 — it *passes* the 0.10 gate — while
leaving the quadratic radial term resting on a single contrast between two radii.

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
| **P6** | Eye ingest, calibration, saccade detection | Replay-driven gaze, and a calibration map `wl-preproc` can read | S5 | ~~their reader~~ nothing |
| | → ingest | **done 2026-09-01** — protocol verified from source, loopback-tested | — | — |
| | → the calibration fit and its file | **done 2026-09-05** — constellation, per-eye fit, three refusals, round-tripped through their reader | — | — |
| | → the block, the versioned map, the join | **done 2026-09-05** — `tasks/calibration.py`, `Mapping`/`MappingLog`/`Collector`, and `gaze.Tracked`. A whole block runs from scheduled targets to an installed map | — | — |
| | → saccade detection | **done 2026-09-05** — online Engbert–Kliegl, contract-tested to find the same intervals `wl-preproc`'s offline detector finds, wired to both saccade guards | — | — |
| | → wiring the calibration block into `taskd` | **not started.** The block composes in a test and that test is the driver's shape; no *session* runs one, and nothing writes the map at session close. Overlaps P4b | S5, S8 | nothing |
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
| ~~`wl-preproc`~~ | ~~**yes**~~ | ~~`read_online_map` reads a `.bhv2` that will not exist~~ **Closed 2026-09-05: they built the second reader** (`eye/expcontroller.py::read_expcontroller_map`, at `c3f6c5e`). Its source fixes the schema, and `tests/test_calibration.py` round-trips against it |
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
7. **The mutation harness has now been wrong five times, and the fifth broke the
    other way.** The first four were false *clean* -- quietly examining nothing and
    reporting success. The fifth was a false *alarm*: neutering inserts
    `return None` at the top of a function whose body was already `return None`,
    which changes nothing, so the suite passed and the harness called it a SURVIVOR.
    Three no-op `display` bodies meant **the mutation gate could never go green**,
    and this file carried the discrepancy as a footnote instead of a bug. Now proved
    from the AST and reported as `NOT MUTABLE`, with `tests/test_mutate.py` testing
    the narrowness rather than the feature -- a category that does not fail the build
    is precisely the shape of the first four, so what is tested is that it refuses
    every case but the one. Original entry follows.

    **The mutation harness has been wrong four times, always the same way** — quietly
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

13. **A gate can be blind to the thing that matters most, by design, and still read
    as passing.** `wl-preproc`'s conditioning metric is scale-invariant on purpose --
    without it, an ordinary grid reads as degenerate for no reason but where the
    screen origin sits. The cost is that **it cannot see how far the targets reach**:
    a 3×3 shrunk to 60% of the field scores 0.2277, *identical* to one spanning it,
    then understates its own error by 3.0× against 1.5×. The calibration procedure had
    conditioning as its only acceptance criterion, so this was the whole gate. Same
    lesson as trap 9 from the other direction: ask what a gate is looking at, and then
    ask what it was deliberately built not to look at.

14. **PyYAML reads `1e-17` as a string.** YAML 1.1's float pattern requires a decimal
    point before the exponent, so `yaml.safe_load("a: 1e-17")` returns `'1e-17'`, and
    a quadratic calibration coefficient small enough to render that way is entirely
    ordinary. The file would have been declined, or silently rescued by pydantic's
    coercion, depending on the reader's mood. `calibration._yaml_float` inserts the
    point; a test proves it end to end through their reader rather than only against
    the helper. **Any hand-written YAML in this repo needs the same care.**

15. **The four calibration decisions that looked like design were already made.**
    The model, the basis column order, the conditioning thresholds, and the entire
    file schema all live in `wl-preproc`'s source -- including a reader written
    specifically for us that this checkpoint still listed as an outstanding blocking
    ask. Trap 1, fourth occurrence. The pattern is now specific enough to state as a
    rule: **before designing anything that crosses a repo boundary, grep their source
    for our own name.**

16. **A backslash inside an f-string expression is a syntax error before 3.12, and
    only CI can see it.** `review.py` had `f"...{' \u2192 '.join(x)}..."`, which PEP
    701 legalised in 3.12 -- so every local interpreter here parses it happily, and
    `ast.parse(..., feature_version=(3, 11))` does **not** reproduce the error. This
    package declares `requires-python = ">=3.11"`, so `wlx review` was unimportable on
    its own declared floor for four days. **The 3.11 CI job is the only detector**,
    which is worth knowing the next time it is tempting to trim the matrix.

17. **Nothing was pushed for four days, and every claim about CI was therefore
    unverified.** The 09-01 checkout fix, the 3.11 syntax error, the pytest
    invocation difference and the mutation gate's false alarm were all sitting in
    unpushed commits. The first push found four bugs in two runs. **A green local
    suite says nothing about CI, and `git log origin/main..main` is the check** --
    a checkpoint that says "CI does X" when X has never executed is the same class of
    error as a stale checkpoint, and harder to see.

18. **A hand-maintained list of things to check is a list that is wrong.** The CI
    mutation gate enumerated its modules in YAML, so a module joined the gate only if
    someone remembered to add it. Three never were -- `bounds`, `scheduler`,
    `findings` -- and `bounds` is the welfare-critical file, the one CLAUDE.md
    requires a human to review before merge. Nothing detected it for a week, because
    nothing compared the list against the directory. `tools/mutation_gate.py` now
    derives the set from disk and **fails if a module is in neither its gated nor its
    exempt list**, so a new module is a build failure rather than a silent omission.
    The same shape as trap 7: the question is not whether the gate passes, it is
    whether the gate is looking at everything it claims to.

19. **A contract test's counterparty moves while you work, and the two halves fail
    differently.** On 2026-09-05 the local `wl-preproc` checkout advanced onto a
    feature branch where `detect_engbert_kliegl` had gained an `fs_hz` argument, while
    `origin/main` -- **which is what CI checks out** -- still had the older signature.
    The saccade contract test therefore failed locally and passed in CI, for a change
    to neither detector's behaviour. Two lessons, and the second is the useful one.
    A signature is not the contract; the intervals are, so the test adapts its *call*
    and keeps asserting the behaviour on both. And **a local sibling checkout is not
    the version CI tests against** -- it can be ahead, behind, or on a branch -- so a
    green local contract test and a green CI contract test are different claims.
