# Where this build actually is

**Last updated 2026-09-26**, at the commit this file was committed in. Check
`git log --oneline -1`; if it has moved far, distrust the numbers here before you
distrust the reasoning. Numbers go stale, arguments do not.

> **This file now describes `main`.** `p4d1-console-link` was reviewed, approved by the
> PI on 2026-09-20 and **fast-forwarded onto `main`**, which moved `300d7d1` → `08adfa2`
> and now carries P4b and P4d-1 together. The long-standing warning that used to sit here
> — that this file described a branch `main` did not have — is **retired**, because there
> is no divergence left to trip over. The branch still exists at the same commit; nothing
> needs it. **Deliberately still not a commit count**: a count of a branch, stated in a
> file tracked on that branch, is wrong the instant it is committed — writing it is itself
> one more commit than it counted, and this file got that wrong three separate times
> before the number was removed rather than corrected again. Run `git log --oneline` and
> look.
>
> **The merge was a fast-forward**, so `main`'s history stays linear and every commit
> described below is reachable from it. `git branch --show-current` still costs nothing
> before believing the rest.
>
> **P4b's CI history is worth keeping.** Its first run failed (`34769913502`,
> 2026-09-13): pytest green on all three Pythons, mutation gate red on `calibration` and
> `saccade`. Not survivors — the harness could not find two functions. Fixed 2026-09-19;
> see "What moved" and trap 7's seventh entry.

**The lab opens January 2027.** Everything is being built before any rig exists.

> **"January validates rather than discovers" was the working assumption and it is
> false.** Review caught it on 2026-08-31: it is load-bearing, because it justifies
> spending effort on the task layer instead of on the four things that must work on
> day one — **DIO out, gaze in, a frame on screen, reward out**. Two exist and are
> proven without hardware (`dio.py`, `eye.py`); **reward out is now built up to the
> pump** (`welfare.py`: a task's `Reward` reaches a delivery, the day is accounted, the
> shortfall against its floor is reported) and stops there, because turning millilitres
> into solenoid open time is a calibration nobody has measured. The display is blocked
> on a panel, the real card on a card, and the last inch of the reward line on a
> measurement. Until a rig runs all four end to end, **January discovers.** Sequence
> accordingly.

Nothing here has touched hardware.

---

## Read this much, and no more

**19 specs, 8 ADRs and 14 other documents exist. Do not read them all.** Counted from
disk on 2026-09-19 (`ls docs/superpowers/specs/*.md`, and `ADR-*.md` less the template);
before that, three figures here and in `next-session.md` had disagreed with each other and
with the directory. The ADR figure moved because ADR-0008 was accepted, and the "other"
figure was one low. In order:

1. **This file** — where things are.
2. **`CLAUDE.md`** — the conventions. Sixteen, and the ones that cost the most to
   learn are near the bottom: prove a test can fail, ship a safety component with its
   consumer, and treat a "not yet" comment as a dated claim nothing can check.
3. **`docs/M0-REVIEW.md`** §3 and §4 — what is still open, and the 24 engineering
   calls made without asking.
4. **The one S-spec your package names**, from the table below. Not the others.

`docs/superpowers/specs/2026-08-31-spec-map.md` maps S0–S13 if you need to find one.

---

## Status

**M0 signed off 2026-08-31.** Contracts frozen; code started.

| | |
|---|---|
| Tests | **740, green on branch `p4d2a-return-to-cage` — with `.[dev,contract,console]` installed.** That is what `main` carries once the PI approves P4d-2a and it fast-forwards; **`main` itself is at 682 until then.** P4d-2a's gate, 2026-09-26, over `cli`, `gaze`, `link`, `record`, `taskd` and `welfare`: **110 caught, 0 survivors, 0 skips, 1 NOT MUTABLE** (`welfare.emit`), every baseline and restore at 739, and every line a real `N failed` once one timeout (`taskd._publish`) had been turned into a failing test and `taskd` re-swept. The 740th test pins a gap the harness could not see (`Session.duration_warning` during the loop); see "What moved on 2026-09-26, afternoon". Before that, 682 on `main` (674 before `tools/mutate.py` learned to name what failed, 2026-09-26; 610 before the PI's round-3 rulings of 2026-09-20 and the review of them; 560 before round 2) (`p4d1-console-link`; `p4b-session-management` alone is 383). **The extras qualifier is not decoration.** P4d-1 added the `console` extra (pyzmq, msgpack) and, until 2026-09-19, neither CI job installed it: measured with both imports blocked, **9 tests fail** — `tests/test_link.py` ×7 and `tests/test_cli.py::test_wlx_run_with_link_{lets_a_real_console_attach,closes_it_when_the_session_ends}` — so the count was a statement about a developer machine and not about CI. `.github/workflows/ci.yml` now installs `console` on both jobs. `bounds` and `welfare` are mutation-clean under the *fixed* harness; see trap 7's sixth and seventh entries for why that qualifier keeps needing to be re-earned. `link.py`/`taskd.py`/`cli.py` (P4d-1) re-swept after the whole-branch review's fixes, 2026-09-19 — **38 target names, 0 survivors, 0 skips, 0 NOT MUTABLE**, every baseline and restore at 438 passed, read from the harness's output and not its exit code. **Re-swept again after the PI's decisions and the review round that followed, 2026-09-19**, over `bounds`, `taskd`, `link`, `cli` and `record` — **52 target names, 0 survivors, 0 skips, 0 NOT MUTABLE**, every baseline and restore at the then-current count, and every line a real `N failed` rather than an `N errors in 0.Ns` (trap 7). **Swept a third time after the welfare-clock rulings**, over `welfare`, `bounds`, `taskd` and `scheduler` at a 467 baseline — **54 target names, 0 survivors, 0 skips, 0 NOT MUTABLE, 0 timeouts**. That run *found* two things rather than confirming them (an uncalled `Session.returned_to_cage`, and two `timed out` lines that were real gaps); both are fixed and both are written up below. **Swept a fourth time after the PI's round-2 rulings, 2026-09-20**, over `welfare`, `bounds`, `taskd`, `cli` and `link` at a 602 baseline — **72 target names, 0 survivors, 0 skips, 0 timeouts, 1 NOT MUTABLE** (`welfare.emit`, a `Protocol` stub whose body is `...`), every baseline and restore at 602, and every line a real `N failed` rather than an `N errors in 0.Ns` (trap 7). **And a fifth time after the review of those rulings**, over the three modules that changed (`welfare`, `bounds`, `cli`) at a 609 baseline — **38 target names, 0 survivors, 0 skips, 0 timeouts, 1 NOT MUTABLE**, plus `taskd.head_released` at 610 once the console-path test landed (**3 failed**, up from 2). That run is also where `_hours_minutes` went from **1 failure to 4**: the review found its only test asserted `0 hours 0 minutes`, which is the one value a function that had stopped working would also produce. **Swept a sixth time after the PI's round-3 rulings, 2026-09-20**, over `welfare`, `bounds`, `cli`, `record` and `taskd` at a 664 baseline — **77 target names, 0 survivors on the final pass, 0 timeouts, 1 SKIPPED** (`welfare.emit`, the documented `Protocol` stub), every line a real `N failed`. **That run found something**: `taskd.Session.return_needs_confirmation` **survived**, a passthrough nothing called, written for symmetry with the departure's. Deleted rather than tested — the rule is enforced by the mark itself — and `welfare._refuse_unconfirmed`'s 2 failures were checked by name to be two *behavioural* tests rather than the §5.2d bookkeeping one. **Re-swept after the review of those rulings at a 674 baseline**, all five modules — **78 target names, 0 survivors, 0 timeouts, 1 SKIPPED**. Three of the five were first read through a `tail` that truncated them, which hides a survivor by construction, and were re-run with complete output rather than trusted |
| CI | **The nightly of 2026-09-25 failed with nothing changed** (run `36115579357`) — on a flaky test, not a survivor, and the harness could not say which; see "What moved on 2026-09-26". The four nightlies before it (09-21 to 09-24) are green. **`main` took the fast-forward of `p4d1-console-link` on 2026-09-20 (`08adfa2`).** Its three pytest legs are green. Its `mutation` job escalated to the **full** sweep, and the reason is worth knowing before reading a push's gate output: a push's gate base is the *previous* `main`, so the whole 55-commit range was in its changed set, `tasks/` included, and it re-ran the sweep that had already passed on `31a3283`. **It finished green (run `35515487242`, 1h55m), read rather than trusted on 2026-09-26**: 22 modules, 264 caught, **0 survivors, 0 skips**, all 44 baselines and restores at `674 passed` — and the five catches that are not a real `N failed` are the four `geometry` imports and `simulate.signal`'s timeout written up under 2026-09-20. **And do not read `main`'s tip run as that check**: `f3ccfe5` is docs-only, so its gate selected **0 modules** (`mutation gate: 0 module(s)`, `selected: (none)`) and passed in three minutes. It is green and it swept nothing, which is the whole reason this row says to read the output. Before that: **green on `main` through `300d7d1`**, verified 2026-09-06 by reading the runs rather than the workflow: six consecutive successes, the `wl-preproc` checkout syncing, `307 passed` with no skips and `WLX_REQUIRE_PREPROC=1` in force. **P4b failed in CI on 2026-09-13 and is green as of 2026-09-19.** The 09-13 run (`34769913502`) escalated to a full sweep as predicted, took 1h46m, and reported `MUTATION GATE FAILED: calibration, saccade` — two functions the harness could not find rather than two survivors (trap 7, seventh entry). Run `35433303094` on `afc7d04` is the fix, **verified by reading its log rather than its exit code**: 21 modules, 215 caught, **0 survivors and 0 skips**, `383 passed` at every baseline, and the four functions the commit was about each reporting a real failure — `recenter 5 failed`, `detect 7 failed`, `_XYZ 4 failed`, `FixPoint 4 failed`. The nightly schedule runs on `main`, which **now contains both P4b and P4d-1**, so from 2026-09-21 its greens describe them — until the merge they did not, and this sentence sat here saying so for six days. pytest on 3.11, 3.12 and 3.13, plus a **mutation gate**. Selective since 2026-09-05: `tools/mutation_gate.py` runs the modules a change can have affected and escalates to all of them on anything structural, with the **full sweep nightly** — the per-push gate cannot see a test deleted from one file that was the only cover for a function in another. It refuses to run at all if a module is in neither its gated nor its exempt list. Functions that already return immediately are reported `NOT MUTABLE` rather than counted as survivors (trap 7) |
| Welfare-critical modules | **two: `bounds.py` and `welfare.py`**, and they are the only two. `bounds` is pure limits — ceilings, and a daily **floor**; `welfare` holds the day's total, the two clocks (out-of-cage, which bounds the session; restraint, which is recorded), the pump, and `Rig` — the object a task's `Reward` action actually reaches. **Both require human review before merge** (CLAUDE.md, S8 §7), and **both have moved on this branch** |
| Fluid | **A floor, not a ceiling** (PI, 2026-09-06). The daily figure is a minimum the animal must reach, topped up by hand after the session; **no delivery is ever refused on volume**. Only the per-delivery magnitude is a ceiling. S8 §4–§5 were written the other way round and now carry the correction |
| Session duration | **One limit: out of the cage to back in the cage, twelve hours** (PI, 2026-09-19). Chair time and a trial cap were the two ceilings until then; neither is a limit now — chair time is recorded by `HEAD_FIXED`/`HEAD_RELEASED` and there is no session-length maximum at all. A rig session is **refused** without its out-of-cage mark; a cage-side one declares `welfare.Deployment.CAGE_SIDE` and has no duration bound. Twelve hours is documented (S8 §5.2 item 4, `welfare.py`) and carried by no constant. **Since 2026-09-20 (PI)** **both marks** are **clock times** (`--out-of-cage-at`, and the return). **With P4d-2a (spec §10, on branch `p4d2a-return-to-cage` until the PI approves it), both ends of the interval are wall instants and every welfare duration is read on the wall**: `Session.wall_now()`, the wall read once when the session is created and carried forward on a monotonic clock. The frame clock times trials only, so the unchairing and the walk back are inside the limit with nothing mapped. **The return is taken at `wlx run`'s terminal, the stand-in until the wl-works ELN records both ends** (PI, 2026-09-26). With no terminal, linked or not, `wlx run` records `return not recorded (no terminal)` and exits. Both ends are rows in `welfare_notes.jsonl`, and the out-of-cage clock is published after the loop until the return. A separate **in-session clock** (session opened to session ended) is published and recorded, and bounds nothing. A mark **more than thirty minutes from now is confirmed by a person or amended with a reason and a name** (`welfare.CONFIRM_MARK_WITHIN`; `wlx run` refuses rather than proceeding when no terminal is attached), there are **three deployment kinds** — `RIG_FIXED`, `RIG_CHAIRED`, `CAGE_SIDE` — with restraint reported **absent rather than zero** where nothing marks it, and the session **warns** at `welfare.WARN_WITHIN_DEFAULT` (1,800 s, **accepted by the PI on 2026-09-20 as a starting value** and still derived from no measurement of this system) before the limit |
| Reference tasks | `fixation_detection`, `adaptive_detection`, `visual_search` (colour pop-out, set size 2–12), `calibration` |
| Load-time checks | **9 of S1 §9's 10, plus S1a's window check, plus nine added after review 2026-08-31** (`uncoupled-window`, `nothing-to-look-at`, `absent-stimulus`, `duplicate-stimulus`, `empty-update`, `uncalibrated-color`, `unrealizable-color`, `overspecified-color`, `unstated-observer`, `target-outside-array`, `impossible-correlation`, `monocular-stereogram`, `unknown-eye`, `wrong-eye-criterion`).** Check 7 is enforced for reward and *not* for stimulation, because no `Stim` action exists yet. Corrected 2026-08-31 after review caught the count |
| Cross-repo asks outstanding | **4 documents, 3 repos**; one blocking ask closed 2026-09-05 — see below |
| Hardware verified | **none** |
| License | **Apache-2.0**, ADR-0004 accepted 2026-09-05. Repository public |
| Day-one path (DIO out · gaze in · frame on screen · reward out) | **2 of 4 built and proven without hardware, and the third built up to the pump**; the display and the real card remain. Reward out runs end to end against a simulated pump, with the day's total accounted and the shortfall against its floor reported at close. What is missing on that leg is a **pump calibration** — millilitres per second of open time — which nobody has measured |

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
  loop cannot distinguish. **`Effects` is the outbound half**, added 2026-09-06: a
  world answers questions, and marks and rewards answer none, so they leave through a
  separate port. The default `Unwired` **refuses**, because for five days `_apply`
  executed the display actions and silently discarded the other two.
- `simulate.py` — the census: outcomes, states visited, hangs, and outcomes nothing
  reached. `Tally` is shared with `taskd`, so a census counts the same things whether
  it came from an exhaustive walk of a task or from a session under its ceilings.
- `cli.py` — `wlx check`, `wlx review`, `wlx run`, `wlx console`; exit 1 on a blocking
  finding. `wlx run` needs `--bounds`, reports what it commanded and why it stopped,
  and takes an optional `--link PUB,REP` that opens a console link (nothing acquires
  the transport dependency when it is omitted). `wlx console --sub PUB --req REP --as
  WHO` attaches to a running session, renders each `Telemetry` frame (S9a §4's panes:
  fluid, chair, trials, still owed, staged, refused) and can `--set NAME=VALUE` or
  `--stop` it. `wlx run` had **no test at all** until 2026-09-06, which is how a
  subcommand ends up unable to construct the object it exists to construct.
- `link.py` — the console link: the telemetry message and its schema (`Telemetry`,
  `Staged`, `Refused`, `SCHEMA`), the commands a console sends back (`SetParameter`,
  `Stop`), the port a session drains and publishes through (`Link`, `Absent`,
  `Simulated` as peers, exactly as in `dio.py`), and the one live transport
  (`ZmqLink`/`ZmqConsole`, ZMQ PUB/SUB + REQ/REP, msgpack, per ADR-0003). Drained and
  published **once per trial boundary, never per frame** — S9 §1's hot-loop rule,
  proved by a test rather than only argued. **S9a §9's one rule, enforced structurally
  rather than by care**: every `Telemetry` field is read from `welfare`, `tally` or
  `scheduler`, never recomputed, and unknown is `None`, never a confident `0`. **Not
  welfare-critical, and built to stay that way** — it carries no ceiling, no clock and
  no pump; the welfare-critical surface stays exactly `bounds.py` and `welfare.py`.
  Added 2026-09-19 (P4d-1). Three things this slice found and deliberately left open
  are recorded in "What moved on 2026-09-19" below.
- `taskd.py` — **the session**: blocks from `scheduler`, criterion transitions,
  ceilings that end a run, one validated path for live parameter writes, and the
  world as an injectable seam. A flat run of N trials is the block session with one
  block, not a second loop.
- `tasks/reference_bounds.py` — a bounded config for `wlx run` and for reading.
  **Every number in it is a placeholder**; its subject is `REFERENCE`, and a session
  refuses a bounded config belonging to another subject, so it cannot quietly become
  a real one. The one number that is *not* implausibly small is `reward_correct`'s
  maximum, 10 mL: a runaway-fluid fault bound rather than a dose cap (PI, 2026-09-19).
- **`bounds.py` — welfare-critical, and pure.** Ceilings a task cannot express and a
  console cannot exceed, **and a daily fluid floor** — a minimum, not a budget. Fluid
  reconciled against the delivered line rather than what we commanded. No clock, no
  hardware, no state that outlives a question. `Floor` and `Ceiling` are different
  types so the two cannot be confused at a call site, which is exactly how the daily
  figure came to be compared with `>`. **`validate` and `set` are separate calls**
  (2026-09-19) because a change is checked when it is offered and applied a boundary
  later; `set` goes through `validate`, so the rule has one home. **Requires human
  review before merge**.
- **`welfare.py` — welfare-critical, and the caller.** The day's fluid total including
  what another deployment already delivered, the restraint clock started by
  head-fixation, the `Pump` port, and **`Rig` — the object a task's `Reward` action
  actually reaches.** `shortfall()` is what a session hands a person at close: how much
  of the day's minimum is still owed. The whole route from a task's declaration to fluid
  is readable in this one file, which is the property to keep. Added 2026-09-06 because
  limits alone were not enough. **Requires human review before merge.**
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
  mutation result by hand, and **read its output rather than its exit code**: it has
  been wrong six times, and the sixth reported `caught` on the strength of a syntax
  error (trap 7).
- `tools/calibration_design.py` — which constellation the block should present, and
  why. Results in `docs/measurements/dev-machine/2026-09-05-calibration-constellation.md`.

### What does not exist, and matters

- ~~**`taskd` is a spine, not a daemon**, and never imports `scheduler.py`~~ and
  ~~**`bounds.check_delivery` is called by nothing outside its own tests**~~ —
  **both closed 2026-09-06**, and what they were is now pitfall P21. See "What moved"
  below.
- ~~**`taskd` is still not a daemon.** There is no console link over a socket~~ —
  **closed 2026-09-19 (P4d-1).** `Session.link` drains commands into `Session.set` and
  publishes telemetry, once per trial boundary, over a real ZMQ socket (`link.py`'s
  `ZmqLink`/`ZmqConsole`); `wlx console` is a terminal client for it. Still missing:
  the browser client and HTTP/WS server ADR-0008 chose, and the `labhost` surface that
  rides on it (P4d-2); the OAuth `Verified`/`Local` actor split (P4d-3, this slice
  carries `by` as a plain string); `rt_approx_ms` (P4d-4); and **preflight beyond the
  two refusals in `Session.run`** — S9a §10's one rule (fail blocks, unknown proceeds
  on a recorded acknowledgement) is designed but not built (P4d-5).
- **Nothing converts millilitres to solenoid open time.** `welfare.Pump` takes
  millilitres because that is what the ceilings are denominated in; the conversion is
  a **per-rig pump calibration that has never been measured**, so the driver that
  opens copper does not exist and would be inventing a dose if it did. `wl-sync`'s
  board one-shots the *manual* button at ~199 ms and passes our commanded line through
  its OR gate untouched (their `hardware/README.md`, 2026-08-15 entry), so the pulse
  width is ours to choose — which is exactly why the number matters. New open
  measurement; see below.
- **A live parameter change is not on the recording clock**, only in the session
  record. `PARAM_CHANGE` is an *escape* carrying a uint32 sequence number and
  `wl-preproc` has not agreed the amendment, so `PARAM_CHANGED` (4130) marks the
  timing in our own range and the values sit beside it in
  `parameter_changes.jsonl`. Strictly better than the silence P16 warns about and
  strictly worse than the escape: two changes in one interval are told apart by order
  alone, and a dropped code desynchronises that ordering in a way a sequence number
  would survive.
- **Calibration is a whole session, not an interlude.** S8 §1 wants sub-tasks a
  session enters and leaves without ending; `gaze.Calibrating` drives a session whose
  *task* is the calibration block. Switching task mid-session is the interlude, and it
  does not exist.
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

  **That figure is stale, and the direction is the point.** Two full sweeps since, read
  the same way: `34769913502` took **1h46m** on 2026-09-13, and `35433303094` took
  **1h39m** on 2026-09-19. The second is the faster one *despite* eight more tests and
  two more functions on the target lists, because those lists lost their duplicates. The
  figure to carry forward is **about 1h40m**, and it will keep growing with the suite.

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

  ~~**CI is red now and stays red until someone creates a secret.**~~ **Resolved, and
  this file said otherwise for a day.** It needed a fine-grained PAT with
  `Contents: read` on `jakewesterberg/wl-preproc` as the repository secret
  `WL_PREPROC_TOKEN`; that secret exists and works.

  **Verified 2026-09-06 by reading the runs, not the workflow** (`gh run list`): the
  last six runs on `main` all succeeded, and run `33984657820`'s log shows the
  `wl-preproc` checkout syncing from the remote and `307 passed` with no skips. Both
  jobs set `WLX_REQUIRE_PREPROC=1`, so a missing checkout would have *failed* rather
  than skipped — which is what makes that green mean the contract tests actually ran.
  Left as a struck-through entry rather than deleted, because "CI is red and needs a
  person" was a live ask in this file and someone should be able to see that it closed.

  The reasoning behind it stands and is why the guard is worth keeping: the round-trip
  and the calibration contract are the only checks that we emit their protocol and fit
  their model rather than our idea of either, and **a contract test that is allowed
  not to run is not a contract test.**

  Three ways of getting one checkout wrong, each of which looked fixed: no checkout,
  a path outside the workspace, and no credentials for it.

---

## What moved on 2026-09-26, afternoon

**Resume here:**
- **P4d-2a:** built, gated and pushed; it waits on the PI's review of spec §7
  (`docs/next-session.md` §1). The ledger is
  `.superpowers/sdd/2026-09-26-p4d2a-return-to-cage/progress.md` in the worktree
  `.claude/worktrees/p4d2a-return-to-cage`. It is git-ignored, so it exists only on the
  machine that ran it; `git log` on the branch is the fallback.
- **b1:** once P4d-2a has merged, start P4d-2b's b1 from its plan.

### The console was designed by mockup, and the PI ruled as it went

- **The design:** twelve rounds of a clickable mockup settled what the browser console is.
  - v12 is `docs/superpowers/mockups/2026-09-26-console-mockup-v12.html`.
  - The review it was checked against is `docs/superpowers/mockups/2026-09-26-console-review.md`, a Fable-model GUI review with sources for every claim about other systems. The PI accepted its top ten and set aside its welfare questions.
- **The rulings:** every ruling made along the way is in the P4d-2b spec,
  `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §4.0. Among them:
  - **The ELN owns out-of-cage:** the wl-works ELN records both ends of the interval, and the console takes no return.
  - **Its own clock:** expcontroller keeps a separate in-session clock, shown and recorded, bounding nothing.
  - **Runs:** they follow the day's plan, and an unplanned run is explicit and warned.
  - **The task library:** it is pulled from GitHub (wl-mllib, to be renamed) before a session's first run.
  - **At the end:** ending a session packages the code it used for wl-nas.
- **The build order:** P4d-2b is built in six slices, b1 → b6.
  - **b1 is specified:** its spec is §4 (`d0375b3`), and its plan is `docs/superpowers/plans/2026-09-26-p4d2b-b1-read-only-console.md` (`9cfb94f`). The plan was verified in a scratch copy: 937 tests passed, and every changed function's mutant was caught.
  - **b1 waits on P4d-2a:** it builds only after P4d-2a merges.
  - **b1 is welfare-critical:** its Task 2 (`welfare.deliver` records the last reward's instant) needs the PI's review before merge.
- **ADR-0004 is amended** (PI): unmodified OFL-1.1 fonts may ship as served assets, each
  family's `OFL.txt` beside its files. The code stays Apache-2.0. The licenses of IBM Plex
  and Newsreader were verified at their primary sources.

### P4d-2a was re-cut by the ELN ruling, and awaits the PI's review

- **The amendment:** spec `2026-09-26-P4d2a-return-to-cage-design.md` §10 moves every welfare duration onto the wall clock.
  - The session reads a monotonic clock anchored once to the wall, so a host clock step cannot shrink out-of-cage time.
  - The return is taken at `wlx run`'s terminal only, as the ELN's stand-in; the link command and `--await-return-for` are gone.
  - The in-session clock is added.
  - §7 is the seven-item list the PI approves.
- **What forced it:** the frame clock outruns the wall in the simulator, so the default `rig-fixed` path could not record its return.
- **Where it stands:** Tasks 1–10 are done on branch `p4d2a-return-to-cage`, rebased onto `main` at `f195d6a` and pushed. That is 740 tests; not on main until it merges.
- **What Task 10 found:**
  - **The rebase:** one conflict, the P4d-2b spec's header, resolved to main's version (ledger Ruling 9). The tree after it differs from the old tip only by main's six documentation files.
  - **The gate** (`tools/mutation_gate.py --base origin/main`, selected `cli`, `gaze`, `link`, `record`, `taskd`, `welfare`): 110 caught, 0 survivors, 0 skips, and `welfare.emit` inert (the documented `Protocol` stub). Every baseline and restore read 739 passed.
    - **One line was not a test noticing.** `taskd._publish` was reported caught by a 300 s timeout. In a scratch copy, `test_a_fault_after_the_loop_is_published_then_raised` called `await_return` on the test's own thread and relied on its first publish raising. With `_publish` neutered it never raised and never returned. The test now bounds `give_up` with a 5 s timer; under the mutation it fails with `DID NOT RAISE`. With that test set aside, the same mutation already failed 19 others in 20 s, so the function was covered and the harness could not say so.
    - **The taskd re-sweep** after that fix (and one docstring change): all 30 names read `N failed`, `_publish` among them at 20 failed, with the baseline and restore at 739.
    - **One gap the harness cannot see, closed.** `Session.duration_warning` has two halves: `approaching_limit`'s sentence while the loop runs, and `must_stop`'s after it. Only the post-loop half was pinned (`1 failed`). `test_link.py` checks `Telemetry.of` against a stand-in whose `duration_warning` is a lambda, so a real session silent until its loop ended failed no test. That is the warning the PI asked for on 2026-09-20. `test_while_the_loop_runs_each_frame_carries_the_sessions_own_warning` pins it: with only the during-loop half silenced, the other 739 pass and it fails. The function now reads `2 failed`.
    - **Each function the plan added or changed** was checked for a test from this plan in its failing set, in a scratch copy wherever the `<-` list was truncated. All have one except `welfare.preflight` and `welfare.approaching_limit`. Those are caught only by older tests, which Task 7 rewrote onto wall instants, so the catch is still on the new base.
  - **Four stale texts** named the code before Task 9's fix or the removed console return: `Session.end`'s and `Session._note`'s docstrings, and two comments in `tests/test_cli.py`. All corrected. The frame-clock paragraph under "What moved on 2026-09-06" is now marked as history.
- **Next:** the PI reviews spec §7; `docs/next-session.md` §1 has the seven items, each with the test that pins it. **It does not merge before his review**, and then only by fast-forward.

### CI

The 09-26 nightly (`36230556322`) was clean on tests and the full mutation sweep. The 09-25
flake did not recur, and the harness now names any failure it sees.

## What moved on 2026-09-26

### The 09-25 nightly failed on a test the harness would not name

Run `36115579357`, full sweep, on `2ac9bea` — the same commit, the same resolved
packages and the same `wl-preproc` (`87e7318`) as the green nightly the day before:

```
MUTATION GATE FAILED: bounds, check, cli, encode, gaze, run, taskd
```

**Not survivors.** The *unmutated* suite went `1 failed, 673 passed` on 7 of its 41
baselines and restores, spread across 80 minutes, and seven modules failed wherever
it happened to land. `_run_suite` kept pytest's last line and discarded the rest, so
the log says a test failed and never which.

It also landed on mutant runs, and that is the part that matters. Diffing every
mutant's failure count against 09-24's: **24 read exactly one higher, and none read
lower.** A mutant nothing really covers reads `1 failed` in such a run and is
reported `caught`. So a flake does not only turn a build red; it can turn a survivor
green, which is trap 7's shape arriving from a direction the harness had no defense
against.

What is established, each from a run rather than an argument:

- **It predates 09-25.** 09-22 has one `+1` (`simulate.new_trial`, 10 failed against
  9). 09-21, 09-23 and 09-24 have none.
- **It depends on the machine.** 09-25 ran in centralus and was the fastest nightly
  by far (baseline 16.05 s against 19.4–25.2 s on the other four). The runner image
  is not it: 09-23 ran on the same new image (`20260920.314.1`) and was clean.
- **It fails fast.** The failing baselines took 16.18–16.34 s, inside the passing
  range, so it is not a 5 s `RCVTIMEO` or a 15 s thread join.
- **It does not reproduce under control: 0 failures in 313 runs.** 73 on macOS (64
  of them under 8× concurrency), 40 in a Linux / Python 3.13 container with CI's exact
  package versions, and 200 on GitHub's own runners — ten shards across four CPU
  models and six regions, including centralus on an AMD EPYC 9V45 at 14–15 s a run,
  all through the harness's own argv and cache clearing (throwaway branch
  `probe/flake-2026-09-26`, run `36223269006`; branch deleted).

**So the test is still unnamed.** What changed is that the next occurrence will name
it.

### The harness names what failed

`tools/mutate.py` now runs pytest with `-rfE` and keeps its short-summary lines:

- a red baseline or restore prints **every** `FAILED`/`ERROR` line, message included —
  pytest trims that message to the terminal width *except* under `CI`, which GitHub
  sets (pytest 9.1.1, `_pytest/terminal.py:_get_line_with_reprcrash_message` and
  `_pytest/compat.py:running_on_ci`, read 2026-09-26);
- every `caught`/`SURVIVED` line ends `<- node ids`, three named and the rest counted.
  **A `caught` whose only `<-` is a test unrelated to that function is a survivor.**

Proved against itself, and it found something doing so: all five changed functions are
caught by a real `N failed`, but **`_run_suite` survived the first pass** — the argv and
the parser each had a test and the function joining them had none (CLAUDE.md: test the
path, not the piece). It now takes a `cwd` so a test drives it end to end on a
three-test suite.

### A race found on the way, fixed, and not shown to be the flake

`tests/test_cli.py::test_wlx_run_with_link_lets_a_real_console_attach` says its session
has "roughly 1,500" trials of margin. That was measured under the chair-time ceiling the
2026-09-19 rulings removed; the session now ends at `tasks/reference_bounds.py`'s 600 s
out-of-cage placeholder, and `_hhmm()` starts each run 0–59 s into it. Measured **on this
machine, in this session's scratchpad, not committed under `docs/measurements/`, and not
a claim about this system**: about 300 trials in about 0.3 s of wall time, inside which
the console must attach, send, and see two frames. A probe replicating the test with only
the departure varied:

| Out-of-cage budget left | pass | fails fast | fails on a 5 s timeout |
|---|---|---|---|
| ~600 s (the test as written) | 20 | 0 | 0 |
| ~300 s | 10 | 3 | 7 |
| ~120 s | 3 | 0 | 17 |
| ~60 s | 0 | 3 | 17 |

A real race with a margin five times smaller than its docstring says — and **probably not
09-25's culprit**, since here it mostly fails slow and CI's failures were all fast. The
docstring's 1,500 is exactly what CLAUDE.md means by a dated claim nothing can check.

**Fixed as a defect in its own right, not as the flake.** The test now uses `_far_bounds`
(the out-of-cage limit twelve hours away) and the console ends the session itself with a
`Stop` once it has seen the change applied, so no ceiling decides how long the session
lasts. Red first: with `_hhmm()` shifted nine minutes early by a scratch plugin, the old
test failed 5 of 5 on a receive timeout; the new one passes 5 of 5, in 0.2 s rather than
5. It also now drives a console's `Stop` through a real `wlx run`, and that assertion was
shown to fail (`'' == 'stopped by jake'`) with `taskd` made to ignore `Stop`. **If the
flake the harness eventually names is this test, it was this race; if it is another,
this one was still wrong.**

## What moved on 2026-09-20

### P4d-1 is on `main`

**The PI reviewed the welfare surface on 2026-09-20 and approved it**, which was the one
thing holding both branches back (CLAUDE.md: welfare-critical code requires human review
before merge). `p4d1-console-link` was then **fast-forwarded onto `main`**: `300d7d1` →
`08adfa2`, 55 commits, history still linear. P4b rode in with it — it had been sitting
unmerged since 2026-09-13 behind the same review.

What the PI approved, in the four questions that were actually put to them: a mark more
than thirty minutes from now is a person's to confirm or amend with a reason and a name;
the DST switches happen at night when no experiment runs, so they are not designed
around; `returned_to_cage` is a wall-clock mark like the departure; and **zero reward is a
designed outcome** — a trial may have a reward period and deliver no juice, because an
on-screen token may stand in for one. That last one is a task-vocabulary gap, recorded in
§7 and deliberately not designed here.

**What this does not mean.** The merge is verified by the suite — 674 passing on three
Pythons — and *not yet* by the sweep: the `mutation` job of run `35515487242` was still
running when this was written. It is re-running a sweep that already passed on `31a3283`,
so the expectation is green, but an expectation is not a reading. Check it.

### The sweep is green, and four of its entries are green for a reason that is not a test

The full sweep on `31a3283` passed: 22 modules, ~2h, a 674-test baseline, **0 SURVIVED and
0 SKIPPED**. It escalated from the selective gate to all 22 because `tasks/` changed, which
is `mutation_gate.GLOBAL` working as intended. Reading its output rather than its verdict —
the rule that has now paid for itself twice on this branch — turned up four entries in
`geometry` that say `caught` and mean something weaker:

```
caught    half_width_cm                    1 error in 1.20s
caught    half_height_cm                   1 error in 1.21s
caught    half_field_h_deg                 1 error in 1.21s
caught    half_field_v_deg                 1 error in 1.22s
```

**These four are caught by an import, not by an assertion.** Neutering `half_width_cm`
makes `tests/test_gaze.py:42` — `TARGETS = constellation(GEOMETRY)`, which runs at *module
scope* — raise `TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'` from
inside `calibration.constellation`. pytest prints `Interrupted: 1 error during collection`,
runs **zero tests**, and exits 2. `_run_suite` returns `result.returncode == 0`, so every
non-zero exit is recorded as `caught`.

**This is not the old false clean, and saying so matters.** In the recorded incident the
collection error came from the *harness*: a regex inserted a statement into a parameter list,
the file stopped parsing, and a function that had never been mutated was reported covered.
Here the mutation is applied correctly by the AST path and the `TypeError` is its own
consequence, so CI really would be red. The catch is real. It is *incidental*: nothing in the
suite asserts anything about those four properties, and the whole verdict rests on one line
in an unrelated test module that happens to compute at import. **Move that line into a
fixture — an ordinary, desirable cleanup — and all four flip to SURVIVED with no change to
production code.** That is the sense in which the gate is reporting safety it does not have.

The one `timed out after 300s (mutation hangs)` entry, `simulate.signal`, is a different
thing and stands: the harness documents that call and its reasoning, and a suite that stops
terminating has detected the change.

**What this costs the next session.** The harness cannot currently tell an incidental catch
from an earned one, because exit 1 (tests ran, a test failed) and exit 2 (collection aborted,
nothing ran) both reach it as "non-zero". Splitting those in `_run_suite` is small, and the
honest third state is not `caught` — it is *inconclusive*, and it should fail the gate rather
than pass it, because a run in which no test executed is not evidence. Then `geometry`'s four
properties need tests that assert on them, and `tests/test_gaze.py:42` can move into a
fixture where it belongs.

**And the selective gate would not be the thing that told you.** `mutation_gate.select`
maps `tests/test_gaze.py` to the `gaze` module by name, so the PR that moved that line into
a fixture would sweep `gaze` and never look at `geometry`. The four would turn into
survivors on the *nightly*, detached from the change that caused them.

None of this touches P4d-1. `geometry.py` is not on this branch's diff, and the finding is
pre-existing — the first full sweep in a while is simply the first thing to look at it.

### The PI's round-3 rulings: a person on a far mark, a wall-clock return, and three records made

Six rulings in one pass, on the branch the round-2 work is already on. **Two change
behaviour on the welfare path and four are records** — and the two that change behaviour
both came out of the same trade: the marks became clock times, so a plausible typo now
survives every refusal there is.

1. **A mark more than thirty minutes from now is a person's to confirm, or to amend with a
   reason and a name.** *"if a number is input that is more than 30 min from the current
   time, a warning should appear that the experimenter must click through to confirm. There
   should also be an option to update the time if necessary, but a reason should be given and
   the experimenter name logged."*

   **Thirty minutes is his figure**, in `welfare.CONFIRM_MARK_WITHIN`, not derived from the
   ceiling. It is 1,800 and so is `WARN_WITHIN_DEFAULT`: **two constants that happen to agree**,
   kept apart so that tuning a console warning cannot quietly move a welfare guard.

   **The band sits between the refusals and both edges still refuse.** A future mark and a
   departure at or past the ceiling are refused outright and never offered for confirmation —
   a prompt that sometimes means "check this" and sometimes stands between an operator and a
   run is a prompt clicked past. **Worth knowing before reading the tests:**
   `tasks/reference_bounds.py`'s ceiling is a deliberately implausible ten minutes, *shorter
   than the threshold*, so that config has an empty band and never prompts.

   **The non-interactive decision, which is the one to check.** `wlx run` asks when `stdin` is
   a terminal and **refuses when it is not**, naming `--confirm-out-of-cage`. A headless run
   that proceeded would write a confirmation nobody made, which is worse than none. The flag is
   the honest way to say it out loud, and the recorded row says the confirmation came from a
   flag rather than a person — **a wrapper with it baked in is how this ruling would otherwise
   be defeated in silence**, and that is the one thing a record can still show months later.

   **The guard is on the marks, not only in `wlx run`.** `welfare.left_cage` and
   `returned_to_cage` take `confirmed` and refuse a far mark without it. CLAUDE.md's rule, not
   belt and braces: both are console actions, and P4d-2's console calling `Session.left_cage`
   directly would reach around the prompt entirely. A caller can lie to `confirmed`; it cannot
   forget it.

   **The amendment is recorded in `welfare_notes.jsonl`, and the choice of file is the
   argument.** Not `parameter_changes.jsonl` — its `sequence` joins a row to a `PARAM_CHANGE`
   strobe on the recording clock, and these marks deliberately have no code (open item 8), so
   a row there would look alignable and be nothing of the kind. Not `refusals.jsonl` — that is
   for writes that did **not** happen, and it is capped against a flooding console peer.
   `record.welfare_note` writes it **at the moment it happens, before `Session.run` opens the
   record**, because the mark must be settled before `preflight` and because a row written
   then survives every refusal that can follow. Each instant is written twice, as a POSIX
   float and as local clock time with its zone, because a person is who reads it.

2. **The DST gap is closed, not fixed.** *"the dst switches happen in the night, when no
   experiments occur."* The unsafe half is spring-forward: `02:30` resolves to `03:30` and
   reports the animal as out up to an hour **less** than it has been. **The description of
   what would happen is kept** in `cli._wall_clock_time` and S8 §5.2 item 4, because the
   dismissal rests on a fact about when experiments run and not on the arithmetic. If night
   sessions ever start — an overnight protocol, an unattended kiosk — it is live again, and
   whoever reads it then needs to find what it does rather than a note saying it was closed.

3. **Zero reward is confirmed, and the reason is new information.** *"zero reward is fine.
   some trials will have a reward period, but they may not receive a juice reward. they may
   get an on-screen token reward that eventually becomes a real reward."* So a zero-volume
   reward is **a designed trial outcome**, not an edge case being tolerated. **`fluid session:
   0.00 mL` no longer implies something is wrong** — a session at zero may be running exactly
   as intended — and nothing may treat it as a fault signal. `supplement` is still the number
   that matters, because a token is not fluid. Carried into S8 §5.2c, S9a §9, `bounds.py`,
   `link.py`, `cli.render` and `next-session.md`.

4. **The return mark is a wall-clock time too, and it closes a real gap.**
   `Session.now()` is frame-derived and stops when the frames do, so an operator who ended a
   session, unchaired the animal, walked it back and *then* marked the return was recording
   the animal as home **at the instant the loop ended** — the release, the unchairing and the
   walk back fell outside the twelve hours, every time. That caveat was written in
   `returned_to_cage`'s own docstring and in `next-session.md` as a note about the caller; it
   was the defect. Struck through in both.

   **`returned_to_cage(at, wall_now, confirmed=False)` maps against `left_cage`'s wall
   anchor**, `Welfare.left_cage_wall_at` — **not** against a fresh `now`/`wall_now` pair. Those
   two are the same instant only while the loop is running, and a mapping built on them would
   drop exactly the interval this ruling exists to count. Every refusal the return had is
   preserved; two are new and both are the departure's — a return in the future, and an
   unconfirmed far one. The confirmation applies identically because a return typed hours ago
   moves the same interval, in the direction that makes a session look shorter than it was.

5. **The thirty-minute warning threshold stands, as a starting value.**
   `WARN_WITHIN_DEFAULT` = 1,800 s is his figure now rather than this repository's proposal.
   **Every word of the "not derived from any measurement" note is kept**, because it is still
   true and is exactly why it is a *starting* value: no block duration has been measured and
   nothing under `docs/measurements/` states one. Closed in `next-session.md` §5.

6. **The NTP server is `ntp.wl.works`** (ADR-0009). Two consequences recorded and they are not
   the same shape: the **ICTS alternative closes** — `ntp.kuleuven.be` exists, was verified
   against ICTS's own service page, and is now *checked and not chosen* rather than pending, so
   its rig-segment reachability stops being a question because nothing will depend on it (the
   verification is kept, struck through, because it is why the alternative was real) — and **the
   route stays open**: lab hosts still need a path on UDP 123, flagged in the ADR, in
   `architecture.md` and in the `wl-works` ask. **Naming a host did not open that route.** And
   the line most likely to be misread once `ntp.wl.works` is in a config file is intact: this
   serves bookkeeping time, never experimental time.

**And a finding, recorded as a finding rather than as work.** `task.py`'s `Reward` means
**fluid** — it names a bounded-config entry and reaches `welfare.Rig.reward` → `Welfare.deliver`
→ the pump — and **nothing in the task vocabulary models a token** that accumulates across
trials and later converts. S1 §2.3 lists `Token(+1 / -1)` and `SetPersistent(...)`; `task.py`
implements neither, and `grep -rn "Token\|SetPersistent\|persistent" wl_expcontroller/` returns
nothing. S8 §5.3 already specifies a conversion bound for a mechanism with no representation to
bound. Three things are missing — **a persistent count, a conversion rule through
`welfare.deliver`, and what the recording sees when a token rather than fluid is paid** (an
event-code question before it is a schema one). It is a **gap in S1/S8's vocabulary, not a
welfare-path defect**; written into S8 §5.3, S8 open item 9, S1 §10 item 3 and
`docs/next-session.md` §7, and **deliberately not designed.**

### The review of those rulings, and the invariant it found lying around

**Verdict: safe to merge, no Critical.** The confirmation could not be defeated — probed
with a pipe, a here-doc, `/dev/null`, `yes c |`, a closed fd 0 and a real pty. Two things
worth carrying forward.

**`sys.stdin` can be `None`, and that is not the same as a non-tty.** With file descriptor
0 closed — a daemon, a service manager, a detached `subprocess` — Python leaves
`sys.stdin` as `None`, so `sys.stdin.isatty()` **raises** rather than answering `False`. It
failed safe (no session, no row) and it was still wrong twice over: a traceback where this
same diff promises a sentence, and `--confirm-out-of-cage` — the documented headless path —
defeated. `cli._at_a_terminal()` is the one place that asks now. **If you write
`isatty()`, ask what a closed fd 0 does to it.**

**The restraint record is a cross-check, not only a record.** A return typed one second
after a departure 25 minutes old, on a session head-fixed at 60 s and released at 1,400 s,
gave `out_of_cage_seconds` of **1.0** beside `chair_seconds` of **1,340** — both marks
present, both orderings individually legal, the whole thing inside the thirty-minute band
so nothing prompted, and an impossible pair accepted in silence, under-reporting the exact
interval ruling 4 exists to count. The invariant is free and physical: **an animal must be
out of its cage to be in the chair**, so the interval contains the restraint and can never
be shorter than it. Guarded at the mark (`returned_to_cage` refuses a return before the
release) *and* at the read (`out_of_cage_seconds` refuses the shorter interval), because
`head_fixed` deliberately has no ordering check against the departure and that route
reaches the same impossible pair without any mark being individually wrong. **If you add a
second clock, ask what pairs of readings it makes impossible.**

**And no config that ships could reach the confirmation band at all.**
`tasks/reference_bounds.py`'s ceiling is ten minutes, shorter than the thirty-minute
threshold, so a far departure is refused by the ceiling before a confirmation is offered —
correct on both sides, and it meant nobody could dry-run the one welfare interaction an
operator is asked to perform. `tasks/twelve_hour_bounds.py` is a second reference config
with the real institutional ceiling, same subject `REFERENCE` and the same implausible
fluid placeholders, and `--confirm-out-of-cage`'s help points at it.

**What the sweep found that nobody asked about.** `taskd.Session.return_needs_confirmation`
**survived**, because it was a passthrough nothing called — written for symmetry with the
departure's, which `wlx run` actually prompts with. That is `bounds.check_delivery`'s failure
exactly: a path that reads as present because it exists. **Deleted rather than given a test**,
since the rule it would have exposed is already enforced *by the mark*; a console that wants the
sentence calls `welfare.return_needs_confirmation` directly. The reason is in
`Session.returned_to_cage`'s docstring so the next reader does not re-add it.

### The PI's round-2 rulings: a clock time, a third deployment kind, a warning, and a closed ask

He reviewed the completed welfare change and made four rulings. **Two of them revise
interfaces this same branch introduced**, which is the shape to expect here — the thing
to carry forward is that he changed an interface a session had already justified in
writing, and was right to.

1. **The out-of-cage mark is a clock time, not an interval.** *"A clock time is what an
   operator reads."* `welfare.left_cage(at, wall_now, now)` takes the departure and the
   wall clock as wall-clock instants and the session clock beside them, and **does the
   mapping itself** — he asked for it there rather than in the caller, and the caller is
   exactly where the last version of this went wrong (`cli.py` passed a literal `0.0`).
   `wlx run --out-of-cage-ago SECONDS` is now `--out-of-cage-at TIME`.

   **What it cost, shown to him and accepted.** The ceiling refusal doubled as a
   wall-clock catch — an *interval* of 1.79e9 seconds is fifty-seven years and absurd on
   its face. An *instant* of 1.79e9 is now, so that is gone; and `08:45` typed for
   `18:45` is nine hours of slack inside a twelve-hour ceiling. What replaces it: a
   refusal for a departure **in the future** (against the wall clock the session reads),
   the **ceiling refusal unchanged**, and — the condition he set — **the computed interval
   printed at session start**: `out of cage: the animal has been out 9 hours 15 minutes,
   having left its cage at 2027-01-14 08:45 (CET, this host's local time)`.

   **Date and timezone are resolved, not implicit** (`cli._wall_clock_time`): a naive
   value is read in **this host's local zone**, one with an offset is honoured, an
   ambiguous local hour takes the first occurrence, and a bare `HH:MM` is **today and
   never rolled back to yesterday** — rolling back would turn `23:59` mistyped in the
   morning into an animal recorded as out for most of a day, which is the exact class of
   error the guards are for. Overnight departures are typed with a date.

2. **Head-fixation is a property of the deployment, not of being on a rig** —
   `RIG_FIXED` / `RIG_CHAIRED` / `CAGE_SIDE`, replacing `OUT_OF_CAGE` / `ANIMAL_AT_HOME`.
   He was shown exactly this shape and chose it.

   **The trap, and it is the one this repository has a scar from: a chaired-but-unfixed
   animal *is* restrained.** So `chair_seconds` answers **`None`, never `0.00`**, for the
   two kinds that take no head-fixation marks. A restrained session reporting zero
   restraint is `shortfall()` answering `0` for a day nobody measured, in a different
   costume. Worked through on every surface: `welfare.head_fixed` **refuses** the two
   kinds that declare no marks (otherwise `None` would be *discarding* a measurement
   somebody took); `taskd.Session.run` releases the head only for `RIG_FIXED`, so no
   stream carries a `HEAD_RELEASED` with no `HEAD_FIXED` before it; `Telemetry.deployment`
   goes on the wire so the console can name *which* absence — `n/a -- cage-side, the
   animal is home and unrestrained` against `n/a -- this deployment takes no
   head-fixation marks, so restraint is UNMEASURED here, not zero` — rather than deriving
   it from the pattern of nulls.

3. **The session warns as the twelve-hour limit approaches.** `welfare.approaching_limit`
   returns the sentence, `Telemetry.duration_warning` carries it, `cli.render` prints it
   beside the stop reason. Silent past the limit, where `must_stop` speaks.

   **`WARN_WITHIN_DEFAULT` is 1,800 s and is a proposal, not a settled figure — it is in
   the outstanding-asks table for him.** It is **not derived from any measurement of this
   system**: no block duration has been measured and nothing under `docs/measurements/`
   states one, so nothing anywhere claims it clears a block. It is a twenty-fourth of the
   limit, long enough to finish what is running and walk an animal back, short enough not
   to sit on screen for most of a session. `--warn-within` configures it; zero switches it
   off. **It may carry a named default where twelve hours may not, because it bounds
   nothing** — the session ends at the same instant whatever it is. A threshold wider than
   the ceiling is **not** refused: such a session genuinely is inside it throughout, and a
   refusal would make `tasks/reference_bounds.py`'s ten-minute placeholder fail to
   construct a `Welfare` at all. (That refusal was written, measured against the
   placeholder config, and removed — the note is in `welfare.__post_init__`.)

4. **The out-of-cage marks get no event code. S8 open item 8 is closed** (2026-09-20).
   His reasoning: they are **operator-entered rather than measured**, so a hardware
   timestamp would add precision to a number that never had it, and our own log plus the
   session directory already carry them. The head-fixation argument does not carry over,
   because that clock is about an event with a defined instant and this one is about a
   recollection. The consequence follows rather than being conceded: a restart re-asks a
   person for the departure time — the same clock time they typed the first time. It is
   struck through rather than deleted in S8 §8, S2 §5, S9 §3 and `docs/next-session.md`,
   and **removed from the outstanding-ask lists**: it is no longer a question for
   `wl-preproc`.

**`link.SCHEMA` is 5.** `chair_seconds` became `float | None`, `deployment` and
`duration_warning` were added. A console built against 4 renders a `None` chair clock, and
one that coerced it would tell an operator a restrained animal had been restrained for no
time at all — the same "a field still decodes and no longer means what it did" case as 3
and 4, with a welfare quantity on the other end.

**One thing the rulings found that nobody asked about.** Ruling 2 says the 4128/4129
codes belong to `RIG_FIXED` and nowhere else, and `run()` was made to honour it — but
`welfare.head_released` had no deployment guard, so a console action wired straight to
`taskd.Session.head_released` could still strobe a `HEAD_RELEASED` into a stream that
never carried a `HEAD_FIXED`: a restraint record for restraint nothing marked. Found by
asking what the sentence *"no stream carries a HEAD_RELEASED with no HEAD_FIXED before
it"* actually depended on — `run()`, and nothing else. Guarded at both ends now. **If a
ruling gives a mark a condition, check the mark that closes it.**

### The review of those rulings, and the one thing it says about how to write this file

Seven findings, and **three of the four documentation ones were the same defect: verbatim
duplicates of the same argument in `welfare.py` and in S8, which had drifted apart.** The
§5.2d preamble still said "nine `_finite`/`_magnitude` refusals ... eighteen `raise` sites"
while its own closing sentence had been corrected in the same session; §5.2 item 4 said
head-fixation "stays a preflight requirement for a rig session" eighty lines below its own
table saying `RIG_CHAIRED` is a rig session that refuses it; and the same item credited
"no stream carries a HEAD_RELEASED with no HEAD_FIXED before it" to `run()`, which was
never what made it true.

**The fix is not shorter prose, it is one copy.** `welfare.py` is ~140 lines of logic over
twenty methods and 113 lines of refusal messages an operator reads — length is not the
problem. Three blocks that existed **twice** moved to S8, where `CLAUDE.md`'s read order
already sends a reviewer, each leaving a pointer: the seven-column `Deployment` table, the
sixteen-line `WARN_WITHIN_DEFAULT` justification, and `left_cage`'s historical `seconds_ago`
account. **Every refusal message stays verbatim in the code.** If you find yourself writing
the same argument in both places again, put it in S8 and point at it — a copy is a thing
that can disagree, and this round proves it does.

**And the CRITICAL, which is the same lesson one level down.** The `head_released` guard
added at the end of the previous round checked the *deployment* and not whether there was
anything to release — so a `RIG_FIXED` session never fixed still accepted the release,
strobed a 4129 into a stream with no 4128, and then reported `chair: 0:00` for it, with
`returned_to_cage`'s "fixed and not released" check blind to it because `fixed_at` was
`None`. A guard written to make a sentence true, that did not make it true. Two more
refusals on `head_released` (nothing to release; released before fixed) and a computed-
duration guard on `chair_seconds` — which had been checking `now`, a value that is not the
quantity, while `tests/test_welfare.py` exempted `fixed_at`/`released_at` from the
entry-point enumeration *on the grounds that* `chair_seconds` guarded them. **An exemption
is a claim; check what it rests on.**

**What the refusal index did, and it is why §5.2d exists.** The one new refusal in a
welfare-critical file (`which takes no head-fixation marks`) and the two reworded ones
failed `test_every_refusal_has_a_row_in_the_table_and_every_row_still_greps` before
anything else noticed. It also caught a sentence nobody had checked: §5.2d claimed
"nine of them are the two guards of §5.2c and fourteen are structural", and nine
reproduces neither the row count nor the `raise`-site count. Replaced with two figures the
test checks.

### wl-works will run NTP, and lab hosts will synchronize to it

**ADR-0009** (PI, 2026-09-20): welfare marks are now clock times and the daily fluid
figure spans two deployments that cannot otherwise agree what time it is, so wl-works
runs an NTP server and lab hosts synchronize to it. Two costs, shown to him and
accepted. **It needs a routing exception that does not exist today** —
`docs/design/architecture.md`'s topology paragraph is amended, narrowly: the AST
guardrail (over application source) is untouched, and only the routing claim is
qualified, from unconditional to "for the application layer." **A wl-works outage
stops clocks being corrected, and that is mild** — an NTP client keeps its own clock
and drifts; a multi-day outage neither stops a session nor invalidates a day's fluid
accounting. **This is bookkeeping time, never the timing record** — S3's "our log is
not the timing record" is unaffected, and nobody should read an NTP-disciplined wall
clock as good enough for aligning neural data. A preflight clock-skew check is recorded
as work to build, not built here. Ask drafted at `docs/pending-wl-works-amendments.md`;
alternatives considered (KU Leuven ICTS's `ntp.kuleuven.be`, and the sync box, each with
the concrete reason it lost) are in the ADR.

---

## What moved on 2026-09-19

### The PI's four decisions, and the one open ask they closed

**Taken after the whole-branch review below, and implemented on `p4d1-console-link`.**
Three of the four touch the reward path, and one of them edits a welfare-critical file, so
the human review this branch already waits on now covers `bounds.py` itself rather than
only the capability beside it (`docs/next-session.md` §1).

1. **A welfare-bounded change defers, like an ordinary parameter.** This **reverses
   documentation written one commit earlier**, which correctly described the old
   immediate-apply behaviour in `taskd.py`, `link.Staged`, `cli.render` and a new S9a
   §8.1 — all of them now describe deferral, and §8.1 is rewritten as the history of why.
   `bounds.Bounds.validate` answers "would this be refused" and moves nothing;
   `Session.set` validates at offer time and stages; `_apply_staged` assigns. The value,
   the `PARAM_CHANGED` strobe and the `parameter_changes.jsonl` row now move in the same
   pass, which is what removes the off-by-one in fluid attribution. The cost the PI
   weighed: an operator who has just lowered a volume watches one more trial go out at the
   old one.
2. **A pump fault publishes one frame before it propagates.** `welfare.py` did not change
   for this one (the welfare-clock rulings later the same day are what moved it)
   and `welfare.Rig` still refuses to swallow a pump that will not answer — but the
   exception used to leave `Session.run` with no telemetry at all, so a console watching a
   rig break, unattended and cage-side, saw the stream simply stop. The loop boundary now
   names the fault in `stopped_because`, publishes once, and re-raises unchanged.
3. **A refused welfare-bounded set reaches the session record**, in a new `refusals.jsonl`
   beside `parameter_changes.jsonl`. Telemetry is lossy by design (S9a §9), so a refusal
   that reached only telemetry left no durable trace of an attempt to set a dose above its
   limit. Ordinary parameter typos stay telemetry-only.
4. **`reward_correct`'s maximum is 10 mL, and stops being a dose cap.** At 10 mL a single
   delivery is not a protocol dose, it is the size of thing that happens only when
   software is broken — so it is a **runaway-fluid fault bound**. That **answers the ask
   this file has carried since 2026-09-06** (S8 open item 6, `next-session.md` §5): *"Is a
   runaway-fluid fault limit wanted? Not a ration — a sanity bound catching a software
   fault delivering litres, reported as a fault."* **Answered 2026-09-19: yes, and it is
   this entry.** The *value* beside it (0.05 mL) stays a placeholder until there are
   animals. `bounds.Ceiling`'s docstring no longer claims every maximum is a protocol
   figure — it names the two kinds and leaves the value out of the library — and
   `tasks/reference_bounds.py` labels each entry: `reward_correct` a fault bound,
   `chair_time` a protocol figure. **`max_trials` turned out to be neither** — the
   concept itself is going; see the next entry.

### And a ruling that removes a concept: there is no session-length maximum

Asked because the fault-bound-versus-protocol-figure taxonomy had no answer for
`max_trials`. The answer was more fundamental than a label. **PI, 2026-09-19:** *"There
is no session length max. … Each task, depending on its config, will have a target
number of trials (likely per condition within the task). But the max trials idea makes
no sense to me. The only limit we have welfare wise is that a session from out of cage
to back into cage cannot be longer than 12 hours."*

Most of the replacement was already built — per-condition targets are `scheduler.owed()`,
`Counts` and `upcoming()`, which the console renders as *still needed by condition*. It
was the session-level cap that made no sense.

**Done, same day, once the PI settled the clock** (four rulings; see the next section).
`max_trials` is gone from `welfare`, from `must_stop`, from `tasks/reference_bounds.py`
and from every document that said two ceilings end a session.

### The welfare clock, and the four rulings that reshaped it

**Welfare-critical, and `welfare.py` moved for the first time on this branch** — it had
been at zero diff until now, so the human review this branch waits on (CLAUDE.md,
`docs/next-session.md` §1) now covers all three of `bounds.py`, `welfare.py` and the
console path.

1. **`max_trials` is gone** (above). `welfare.must_stop` takes `now` alone; the parameter
   that carried a trial count was removed rather than ignored, so nothing can pass a
   number and believe it was weighed. `tests/test_welfare.py` pins that a bounded config
   left over from before the ruling, still carrying a `max_trials` ceiling, changes
   nothing.
2. **The clock measures out-of-cage to back-in-cage, bounded at twelve hours.** Chair
   time started at head-fixation and so missed the transport and chairing that precede
   it — it under-counted exactly the interval the institution bounds. `welfare` gained
   `left_cage` / `returned_to_cage` / `out_of_cage_seconds`, and `out_of_cage` is the one
   ceiling `must_stop` reads. **`head_fixed` / `head_released` and their codes 4128/4129
   remain**: chair time is still recorded and bounds nothing. (It was required by *every*
   rig preflight until 2026-09-20, when it became a property of the deployment — see the
   round-2 rulings below.) S8 §5.2 item 4 carries the whole account.
3. **A kiosk session has no duration bound and must declare it.** `welfare.Deployment` is
   a required field with no default: the rig kinds refuse a session missing its mark or
   its ceiling, `CAGE_SIDE` states that the animal never left home (S13 §4.0). (The
   members were `OUT_OF_CAGE`/`ANIMAL_AT_HOME`, and there were two, until 2026-09-20.) **The
   absence of a mark must never be what disables a limit** — an unmarked rig session and
   a cage-side one are indistinguishable to anything that answers zero, so
   `out_of_cage_seconds` **raises** on an unmarked rig session at every call rather than
   only at preflight, and a cage-side config that also states an `out_of_cage` ceiling is
   refused because the declaration and the config must not disagree.
4. **Twelve hours is documented, not configured.** It is in S8 §5.2 item 4 and in
   `welfare.py`'s docstring, and **no constant carries it** — a number with a name is a
   number something defaults to. `tasks/reference_bounds.py`'s `out_of_cage` value is ten
   minutes and stays implausible, per that file's own two guards and the PI's standing
   rule that its placeholders stay placeholders until there are animals.

**Two consequences outside `welfare.py`.** `SCHEMA` was **4** here and is **5** since the
round-2 rulings: `chair_seconds` stopped
being the number that ends the session and `Telemetry.out_of_cage_seconds` is what the
ceiling is read against, so a console built against 3 would show chair time as *the*
clock and then watch a session stop on a limit it never displayed. And the loop bound in
`tests/test_taskd.py` is now the `out_of_cage` ceiling (800 s, a little over four hundred
trials of that task) where it used to be `max_trials=400` — the same size of backstop,
expressed in the unit a real session ends on, so a scheduler mutation still bounds out in
a fraction of a wall second rather than timing out at 300.

~~**Open, and asked of the PI rather than filed:** the out-of-cage marks have **no event
code**.~~ **Answered 2026-09-20: they get none** — see "The PI's round-2 rulings" below.

### And the fix round that followed, which found the mirror of the rule above

Two defects, both of which switched the limit off **while the session reported itself
correctly marked** — so neither is visible in any artifact the session produces, which is
the family this whole module exists to close.

1. **The *presence* of both marks, mis-ordered, was as bad as a missing one.** The rule
   written above is "the absence of a mark must never disable a welfare limit"; it is only
   half. `returned_to_cage` was two unguarded lines beside a `left_cage` that had a careful
   guard. A return *before* the departure gave a **negative** duration, which is under
   every ceiling there is — a session with a 2-second limit ran 300 trials with the clock
   reading −429 s. A return marked **mid-session froze** the clock, so `must_stop` answered
   `None` for the rest of it. And `left_cage`'s guard was `left_cage_at is not None and
   returned_at is None`, so a return **re-armed** it: out at 0, home at 43,000, out again
   at 43,100 reported a fresh clock for an animal out twenty-two hours.

   The interval is now **opened once, closed once, and never runs backwards**. A return is
   refused unless it closes an open interval, refused while the animal is recorded
   head-fixed — it cannot be in the chair and in its cage at once, and `run()` fixes before
   its first frame and releases after its last, so the whole loop sits inside that refusal —
   and refused before the departure. A closed interval refuses a `preflight` and **stops** a
   running session rather than freezing it.

   **Out and back is one session — PI, asked and answered 2026-09-20.** The code was
   written that way first, on the reading that a session *is* "out of cage to back into
   cage"; the question of whether an animal returned briefly and brought out again resumes
   its session or starts a new one went to the PI rather than being left as an inference,
   and he confirmed it starts a new one. Recorded as his ruling and not as our reading,
   because three of the first four decisions this repo revisited as inferences changed the
   moment somebody asked (CLAUDE.md, "ask, do not file"). **The consequence he weighed and
   accepted:** an animal returned mid-day produces **two session directories and two
   records**, not one record with an unexplained gap — which is the more honest account,
   since nothing downstream could tell such a gap from a session that simply ran long.

2. **Nothing said what time base the mark was in, and as wired the change did not achieve
   the ruling.** `Session.now()` is frame-derived and reads zero at session start, so
   counting transport and chairing needs a mark *before* zero — and `cli.py` passed `0.0`,
   which made out-of-cage time identical to chair time. The under-count the clock replaced
   chair time to remove, reintroduced by the interface, with no test pinning it.
   `welfare.left_cage(seconds_ago, now)` took the number an operator holds; it refused
   the future, and refused longer ago than the subject's own ceiling — which is what caught
   a wall clock handed to a session-relative parameter, and is the same refusal a session
   already past twelve hours gets. **`wlx run --out-of-cage-ago` is required with no
   default**, for the reason `--as WHO` is: a headless run types `0` and means it.
   (**The parameter is `left_cage(at, wall_now, now)` and the flag is `--out-of-cage-at`
   since 2026-09-20** — the PI ruled that a clock time is what an operator reads. The
   time-base argument above is unchanged and the mapping moved *into* `welfare`; what the
   change cost, and what replaces it, is under "The PI's round-2 rulings".)

3. **And then a value that is unordered against every bound.** Found by review after the
   two above were closed, and the sharpest of the three: every guard on this path is an
   *ordered* comparison, and **NaN is `False` against all of them** — not in the future, not
   past the ceiling, not backwards. `left_cage(nan)` made the mark NaN, the duration NaN, and
   `must_stop` answer `None` forever. Reachable from the surface an operator touches:
   `--out-of-cage-ago` was `type=float` and argparse parses `nan`, so `wlx run` ran **400
   rewarded trials, 13.55 mL, a clean summary and no duration limit at all**. A NaN
   `out_of_cage` **ceiling** in a bounded config did the same with an honest mark.

   `bounds._finite` refuses a non-finite value at `Ceiling`, at `Floor` and at
   `Bounds.validate`, so a limit that is not a number cannot be constructed; `welfare`
   refuses one at both ends of the mark and on the computed duration. `math.isfinite`,
   because `calibration._yaml_float` already spells it that way and a second spelling of
   "is this a number" is a second thing to keep in step. This entry said **`inf` was
   always refused correctly**; the next round measured that false — `seconds > inf` is
   `False` for every real duration, so an `inf` ceiling is never exceeded either, and
   only the *mark* route ever refused it. Corrected rather than deleted, because the
   sentence had been repeated twice before anyone checked it.

   Two smaller things went with it. `preflight` took the session clock instead of
   hardcoding `0.0`, which had baked the zero-base assumption into a second place. And
   `left_cage` now refuses `seconds_ago >= ceiling` rather than `>`: an animal out for
   exactly the limit has no room for a trial, and the boundary now meets `must_stop`'s `>`
   instead of overlapping it by one.

4. **And then the same class again, on the surfaces the first two rounds did not touch.**
   Rounds 1–3 were one defect found three times: **a guard on a *limit*, with the
   *measurement* compared against it left unchecked.** `--delivered-today nan` printed
   `supplement: 0.00 mL` for an animal on 10.90 mL against a 20 mL floor — an unmeasured
   day turned into "nothing is owed", in the figure the PI's own floor ruling exists to
   produce. `--set reward_correct=-0.5`, through the real console path, commanded twenty
   rewards of −0.5 mL to the pump. Neither is exotic; both are `type=float`.

   **The fix is the rule, not the two patches:** *an instant is finite; a magnitude is
   finite and not negative* (`bounds._finite`, `bounds._magnitude`). It now applies at
   every door — the limits, the console's offered value, the day's prior total, the
   sync box's delivered figure, the marks, and every clock reading.

   **And the enumeration is checked rather than asserted.** `tests/test_welfare.py`
   lists every numeric entry point with a driver, recomputes that set from the live
   modules, and fails if one is in neither the guarded list nor an exempt list with a
   reason — `tools/mutation_gate.py`'s shape, for parameters. A second test closes its
   one blind spot, an unannotated parameter. **Adding a float-taking method to either
   welfare-critical file now fails the suite until it is guarded or explained.**

   `welfare.py` was cut from 630 to **515 lines / 247 executable** in the same pass,
   with the dated narratives moved into S8 §5.2c and every refusal message kept
   verbatim. Two sentences in it were measured **false** and corrected: that `inf` was
   already refused everywhere (only the mark route refused it), and that `preflight`
   checks the ceiling (it does not; `left_cage` and `must_stop` do).

   **And one PI ruling came out of that round** (2026-09-20). A reward volume of
   **exactly zero** is a quantity, so neither guard refuses it; the question was whether
   a *policy* refusal belonged on top, since a console zeroing the volume leaves every
   subsequent correct trial unpaid. **Answered: allow it, because it is not silent** —
   and because it is a legitimate operational move, pausing reward without ending a
   session. The consequence he weighed and accepted: while it holds, an animal working
   correctly is paid nothing.

   **That makes two console numbers welfare-load-bearing.** `fluid session: 0.00 mL`
   (from `welfare.session_total`) is how an operator sees it, and `supplement` keeps
   reporting the whole floor as owed so the animal is topped up. **A change that stopped
   showing either would turn a permitted operation into a silent one** — a welfare
   regression reached by simplifying a display. The sentence is in `cli.render`,
   `link.Telemetry` and S9a §9 as well as S8 §5.2c, because a P4d-2 or P4d-4 session
   editing a console pane is where it would otherwise be lost. It is also **the one
   place a magnitude of zero is deliberately allowed**, so the rule itself keeps no
   exception.

5. **A verification pass then attacked the tripwire itself, and got past it six
   times.** The enumeration of numeric entry points was real, but the introspection
   that checks it had blind spots: it filtered on `inspect.isfunction`, so a
   `@property` setter, a `@staticmethod` and a `@classmethod` taking a float were
   invisible; its classifier matched only `"float"` or exactly `"int"`, so `int |
   None`, `Optional[int]` and `Decimal` slipped; and it required *an* annotation
   rather than a classifiable one, so `ml: object` passed. **None existed in either
   module** — this was the tripwire, not a live hole — but a tripwire with six blind
   spots is the failure it exists to prevent, one level up. All six are caught now,
   and the fixed test immediately found a real one: `Rig.card: object`, which now has
   a `Card` Protocol beside `Pump`.

   Three claims were also wrong and are corrected. **"Exactly two routes"** by which a
   number could reach a comparison unguarded: there are **at least six**, and the
   other four are named. **`Welfare.deliveries` "never supplied"**: it is a
   constructor field, and `Welfare(deliveries=-7)` is accepted — harmless, since
   nothing compares it, but the true reason is that it is a *count*, not a magnitude;
   the three clock fields carried the same overstatement. And **§5.2c earned nine
   refusals while the two files have twenty-three** — the other fourteen are
   structural and lived in prose a reviewer would not find from the code. **S8 §5.2d
   is now a table of all twenty-three**, first clause verbatim and greppable, each
   with the failure it was written against; a test keeps it in step with the code in
   both directions.

   `bounds.py` got `welfare.py`'s treatment, which it had not had: **327 → 285 lines,
   99 executable**, narrative moved to S8, every refusal message verbatim. And `wlx
   run` now refuses *every* bad welfare value with a message rather than a traceback —
   `--out-of-cage-ago nan` was wrapped and `--delivered-today nan` was not (that flag
   is `--out-of-cage-at TIME` since 2026-09-20 and refuses a non-time at the parser).

`welfare` and `bounds` re-swept at a 560 baseline — 28 names, **0 survivors, 0 skips, 0
timeouts, 1 `NOT MUTABLE`** (`Card.emit`, a Protocol stub whose implementations live in
`dio`; the documented category, not a survivor). Full account in
`welfare-clock-report.md`.


**Also, same class as the work just completed:** `taskd.Session.refusals` was the third
list growing without bound under the same untrusted peer as `ZmqLink.refused` and
`Telemetry.refusals`. Capped at `link.REFUSAL_HISTORY` with the discards counted into
`Telemetry.refusals_dropped`, consistently with the other two.

**`SCHEMA` is 3.** `Staged.bounded` stopped meaning "already live" and became "checked
against a welfare ceiling rather than the task's `Param`" — a field that still decodes and
no longer means what it did, which is exactly the case that number exists for: a console
built against schema 2 renders a just-lowered reward volume as `ALREADY IN EFFECT`.

### The whole-branch review of P4d-1, and its fixes

**The last pass before the PI sees it.** Seven tasks had each been reviewed on their own;
this reviewed the branch as a whole and found six things no single task's review could
have, because each of them is about two places disagreeing. In commit order:

- **CI would have been red on every job at the first push.** P4d-1 added the `console`
  extra and neither CI job installed it. Measured with `zmq`/`msgpack` blocked:
  `9 failed, 412 passed`. Worse on the mutation job, which escalates to a full sweep on a
  `pyproject.toml` change and would have aborted at `tools/mutate.py`'s "suite is not green
  to begin with" with no coverage evidence at all. **A test count is a claim about an
  environment**, and "421, green" was a claim about a developer machine. The Tests row
  above now says what it is green *with*.
- **A welfare-bounded change applies immediately and was displayed as `staged`.** Four
  documents said it deferred to the next trial boundary; only one test said otherwise.
  Measured: a queued `SetParameter(reward_correct, 0.30)` against a starting 0.15 has
  trial 0 — the trial in that same pass — commanding 0.30 mL, while its
  `parameter_changes.jsonl` row lands between trial 0 and trial 1. The ceiling holds and
  nothing lands mid-trial, so this is attribution, not over-delivery — but **the record is
  off by one trial for fluid attribution**. Fixed by documentation only, in all four
  places plus three more carrying the same claim. It was then put to the PI as a question,
  and **answered the same day: it defers** — see "The PI's four decisions" above, which
  reverses the documentation this bullet describes.
- **`Refused` could not survive the wire and nothing could tell.** `decode` was correct,
  but the suite's only round-trip ran on an empty `refusals` tuple — deleting the rebuild
  left `421 passed, 0 failed`. Two tests now, one of them `render(decode(encode(...)))`,
  because the chain is what a console walks.
- **The refusal feed grew without bound, driven by an untrusted peer.** Capped at 50 per
  source with the drops counted and printed; `SCHEMA` → 2.
- **Nothing constrained the bind address.** `wlx run --link tcp://0.0.0.0:...` was accepted
  in silence, which voids S9a §7's entire justification for trusting a command's actor.
  Loopback unless `--link-allow-remote`, with **P4d-3** named at the bind as what real
  authentication waits on.
- **Found on the way:** `ZmqLink.__init__` abandoned its `Context` if `bind` raised —
  a port already in use is the ordinary case — which is the state that makes the suite stop
  terminating. It cost a 600 s hang here before it was closed.

Six minors too, of which two were the same rule applied in one place and not its twin: an
unchecked `partition("=")` in `--set` after `--link` had been hardened, and a measurement
disclaimer in one test file and not the other.

`bounds.py` and `welfare.py` remain untouched by this branch — checked against its own
base, `8693299`, not against `main`. The full report is in
`.superpowers/sdd/2026-09-19-p4d1-console-link/final-fix-report.md` (untracked;
`.superpowers/` is gitignored).

### The console is a web application now, and `wl-works` lists the devices

**ADR-0008, accepted by the PI 2026-09-19.** It supersedes S9a §1's PySide6 decision and
S9 §8, and it came from the PI asking whether the experimenter interface could be reached
through `wl-works`. Three findings decided it, each read from source rather than recalled:

- **`wl-works` already specifies the directory.** Its Plan 10 design opens *"It is not a
  dashboard. It is a control plane for lab machines, with a status board as its read
  half"*, and specifies `/infrastructure`, a responder contract and health readings. The
  tab does not need inventing.
- **But `wl-works` must not hold the authority.** Plan 10 §4.1, deliberately the first
  line of its protocol document: *"Publishing an action makes it available to every member
  of the lab. There is no permission model on the app side."* §6.2 defends that with *"the
  host is the real boundary anyway"*. On a preprocessing server the worst case is wasted
  compute; on a rig it is fluid, or a session started on an animal nobody is standing next
  to. So the box authenticates, the box records who asked, and `wl-works` carries a link
  and readings — which is the exclusion `architecture.md` already recorded, now with the
  reason attached to it.
- **"A server on the rig" stopped distinguishing the options.** S9 §8 rejected a web UI
  because it would put a server on the rig; `labhost` (P4c) and Plan 10's responder both
  put one there by design. What survives is S9 §1 — the hot loop serves no requests —
  which a console process beside `taskd` honours either way.

**LAN-only** (PI: *"off-site is not necessary. at least now it isn't"*), so nothing
bridges and a `wl-works` outage cannot cost an operator the console mid-session. Nothing
forecloses off-site later: a box that owns its origin and its auth is unchanged by a route
placed in front of it.

**One thing is gated on a measurement, not on an opinion: protocol V11.** S9a §2's
replica pane — the animal's screen with gaze and windows drawn on top, at display rate —
is the one thing PyQtGraph was chosen for, and this ADR claims nothing about whether a
browser carries it. V11 measures it over the LAN with no rig. If it fails, the fallback is
a native path for that pane, not a second console.

**The kiosk's iPad is the next decision** and is deliberately not made here — see
`next-session.md` §3d — **answered on 2026-09-19; see the console design above.**

### The console design, brainstormed and settled

S9a now carries the whole control-system design in §6–§10, and **two of S9's open items
closed by being dissolved rather than answered.** Decisions, each the PI's:

- **Identity is OAuth2 against `wl-works`** — which turned out to be configuration rather
  than development. Read from their source: `src/lib/auth.ts` registers better-auth's
  `mcp()` plugin, which *is* the OAuth provider in 1.7.1 and serves the `/oauth2/*`
  surface Zulip already consumes, with revocation proven end to end. The ask drafted in
  `pending-wl-works-amendments.md` is "register a client".
- **Two entry points, one console.** Via `wl-works` for attributed actions; **locally as a
  permanent peer**, never an emergency hatch, so an intranet outage cannot cost an
  operator the console with an animal in the chair. `Actor` is two types — `Verified` and
  `Local` — because a forgeable name is worse than no name.
- **No write lock** (S9 open item 1, closed). Anybody attached has full access. Safe
  because **`bounds` is the welfare boundary, not the lock**: magnitudes are
  ceiling-checked whoever asks, fluid is a floor with nothing to race against, mappings
  are versioned, stop is idempotent. Visibility — presence, a live change feed, and
  **staged changes visible to everyone** — replaces coordination.
- **Preflight: unknown proceeds on a recorded acknowledgement; only a failure blocks**
  (S9 open item 2, closed). One rule, no exceptions, shaped against a gate that cries wolf
  and gets routed around. **It carries a dated dependency**: it is safe only while the
  pump driver may not be written before V10, and S9a §10 says so in the place someone
  would have to grep.
- **RT is approximate online and real offline.** `rt_approx_ms`, never `rt_ms`. An
  earlier proposal to wire hardware response lines was withdrawn — it would have changed a
  board on the strength of reasoning rather than a measurement, which is the thing this
  repo forbids.
- **The kiosk's animal-facing screen is an attached panel with a wired touch sensor**, not
  an iPad: a touch arriving over WiFi cannot be strobed promptly, and the offline join is
  the method. The iPad becomes the *experimenter's* window, which ADR-0008 already gives
  for free. **And the cage-side deployment gets a reduced sync module** — reversing S13
  §2's "no sync box" — which also gives `wl-juicer`'s dose and witness lines the home its
  spec designed them for.

**One thing found and deliberately not fixed here:** the session directory carries
`trials.jsonl`, `config.json`, `parameter_changes.jsonl` and `eye_calibration.yaml` but
**no event-code table**, so nothing downstream can name a code without checking out the
task at the recorded version and re-deriving it. `wlx review` builds that table already.
It is a P4c item, not a console one.

### The console link ships (P4d-1), and three things about it stay open

Built on `p4d1-console-link` — see this file's banner above for how to find the
branch's own commits (deliberately not a count; see why there) — on top of
`p4b-session-management`, itself still unmerged and waiting on the welfare review
below. `Session` gains a `link` field, drained and published **once per trial
boundary and never per frame** — proved by a test, not only argued (the plan's Task
4 Step 6). `link.py` (new, 672 lines) holds the telemetry message and its schema
(`Telemetry`, `Staged`, `Refused`, `SCHEMA`), the commands a console sends back
(`SetParameter`, `Stop`), the port (`Link`, with `Absent`/`Simulated` as peers exactly
as in `dio.py`), and the one live transport — `ZmqLink`/`ZmqConsole` over ZMQ PUB/SUB
+ REQ/REP, msgpack, ADR-0003's transport untouched. `cli.py` gains `wlx run --link
PUB,REP` and a new subcommand, `wlx console --sub PUB --req REP --as WHO [--set
NAME=VALUE] [--stop]`, a terminal client. **`link.py` carries no ceiling, no clock and
no pump and stayed off the welfare-critical list under review** — the surface is
still exactly `bounds.py` and `welfare.py`.

**S9a §9's one rule, enforced structurally rather than by care.** Every `Telemetry`
field is read from `welfare`, `tally` or `scheduler` — `Telemetry.of` recomputes
nothing — and unknown is `None`, never a confident `0`, following
`welfare.shortfall()`'s own refusal to claim an unmeasured day went well.

**Two Criticals were found and fixed before this shipped, both about a *sequence* of
commands rather than one command in isolation** — S9a §8's ordinary case,
`--set X --stop`, is two commands. A REQ socket refuses a second `send()` before the
first reply is read, so the second command raised until `send()` was made to read the
previous reply lazily, one send behind. And `drain()` used to decode a command before
replying to it, so one undecodable packet — a newer console against an older
`SCHEMA`, a realistic case since the wire is versioned by design, not only
corruption — propagated an exception out of the trial loop *and* left the REP socket
owing a reply, wedging every command after it too; fixed by replying unconditionally
before decoding, and turning a bad packet into a `Refused` entry (the transport-layer
twin of `Session.refusals`) rather than dropping it.

**Mutation sweeps, read rather than trusted (CLAUDE.md; trap 7's shape is exactly
what "read the output" guards against):**

Re-run in full after the whole-branch review's fixes, since those added two functions
(`_binds_beyond_this_machine`, `_value`) and seventeen tests:

```
python3 tools/mutate.py --all --returns None wl_expcontroller/link.py
  baseline: 438 passed in 25.01s -- 15 functions, all caught (of, encode, decode,
  _encode_command, _decode_command, publish, drain, queue,
  _binds_beyond_this_machine, __init__, close, __enter__, __exit__, send,
  receive) -- restored: 438 passed in 14.10s

python3 tools/mutate.py --all --returns None wl_expcontroller/taskd.py
  baseline: 438 passed in 14.05s -- 16 functions, all caught (__post_init__,
  directory, now, head_fixed, head_released, set, staged, _command, _params,
  _apply_staged, _load, _plan, _agent, make, run, publish) -- restored: 438 passed
  in 21.40s

python3 tools/mutate.py --all --returns None wl_expcontroller/cli.py
  baseline: 438 passed in 16.24s -- 7 functions, all caught (_load_trial,
  _load_allocation, _load_bounds, _clock, _value, render, main) -- restored: 438
  passed in 13.58s
```

**Zero `SURVIVED`, zero `SKIPPED`, zero `NOT MUTABLE`, no hang, across all three
modules — 38 functions, each `caught` by a real assertion failure** (`__post_init__`
and `_load_allocation` each fail 45+ of the 438 tests; the narrowest,
`head_released` and `_clock`, fail exactly one — the range a coverage tool should
show, not a flat number). Full transcripts in
`.superpowers/sdd/2026-09-19-p4d1-console-link/task-7-report.md` for the first run and
`final-fix-report.md` beside it for this one.

**Swept again after the welfare-clock rulings**, over `welfare`, `bounds`, `taskd` and
`scheduler` at a 467-test baseline — **54 target names, 0 survivors, 0 skips, 0 NOT
MUTABLE, and 0 timeouts**, every line a real `N failed`. Full transcripts in
`welfare-clock-report.md` beside the other two. Two findings the sweep produced rather
than confirmed, both now fixed and both of the kind the harness exists for:

1. **`taskd.Session.returned_to_cage` SURVIVED.** It was wired to `welfare` and called
   by nothing and tested by nothing — `bounds.check_delivery`'s failure exactly, a path
   that reads as present because it exists. It now has a test that drives it the way a
   console would, and the test also pins why `run()` must *not* call it: when the loop
   ends the animal is still in the chair, and the release, the unchairing and the walk
   back are all inside the twelve hours.
2. **`Scheduler.record` and `Scheduler.advance` each reported `caught … timed out after
   300s`** — the harness noticing a hang, not a test noticing a defect, which is trap 7's
   shape again. `record` hung because `test_scheduler.py` drove a block with `while not
   scheduler.finished:`, a loop that trusts the code under test; it counts to a finite
   bound and asserts now. `advance` hung because `run()`'s block-advance `continue` runs
   no trial and moves no clock, so a scheduler that reported `finished` and then stayed
   put would spin with an animal in the chair and nothing on any console changing.
   `run()` now **counts** block transitions and refuses the one past `len(blocks) - 1`.
   Counted rather than compared on purpose: a plan may legitimately list the same `Block`
   object twice — "multiple blocks of the same tasks" is the PI's own description — so a
   guard asking whether the block *changed* would abort one of those sessions. Both
   functions now report `6 failed` and `25 failed`.

**Three things found and deliberately left open, recorded rather than fixed —
`docs/next-session.md` §6 has the full account, and item 3 is also in §1 beside the
`bounds.py`/`welfare.py` review already waiting:**

1. **A pump fault publishes nothing.** `welfare.deliver` raises, `Rig` deliberately
   does not swallow it, and the exception propagates past `Session.run`'s `finally`
   with no final `Telemetry` frame and no `stopped_because` — a console watching a
   rig break, unattended, cage-side, sees only silence. What a console should show
   when the rig itself is faulty is a design question for a later slice.
   **Closed the same day by the PI's second decision** — see "The PI's four
   decisions" above. This paragraph is what it was closed against.
2. **A change staged on a session's literal last pass is never applied** —
   `_apply_staged()` gets no further pass once the loop decides to stop. The final
   frame still shows it `staged` beside `STOPPED:`, an implicit signal rather than
   silence, but `--set X --stop` over real sockets does not land both commands in
   the same `drain()` batch — Task 6's reviewer reproduced this 20/20 times (not
   committed under `docs/measurements/`, and not a claim about this system's timing;
   the number says the ordering held every time it was tried, nothing about speed) —
   so the obvious way to hit this on purpose does not. Residual risk: a
   `SetParameter` landing on whichever pass a welfare ceiling or "every block
   finished" resolves on. **Widened the same day by the PI's first decision**: a
   welfare-bounded name used to be immune, because `Session.set` moved the ceiling at
   drain time and only the record row was lost; now the value is staged too, so such
   a command on the stopping pass is dropped entirely. Still open, now on the reward
   path — `docs/next-session.md` §6 item 2 carries the full note.
3. **`wlx console --set reward_correct=...` is the first person-invocable path that
   moves a reward limit** (`Session.set` validates, `_apply_staged` → `bounds.set` at
   the next boundary, since 2026-09-19). `cli.py` does not become
   welfare-critical — the ceiling is still enforced in `bounds.py` alone — but the
   capability is new and welfare-facing, and CLAUDE.md wants a human lab member on
   it before merge, same as `bounds.py`/`welfare.py`.

### The branch was pushed, and the gate caught something real

`docs/next-session.md` said the first thing to do was push the branch and watch the
runs. That happened on 2026-09-13, and **the run failed** — which is the entry justifying
why it was the first thing to do. Run `34769913502`: pytest green on 3.11, 3.12 and
3.13, then the mutation gate escalated to a full sweep as predicted, ran for 1h46m, and
printed

```
MUTATION GATE FAILED: calibration, saccade
  SKIPPED   recenter    could not find recenter
  SKIPPED   detect      could not find detect
```

**Not survivors.** A skip fails the gate on purpose (`tools/mutate.py`): a function the
harness cannot mutate is a function whose coverage is unproven, and the whole point of
this tool is that it never reports safety it has not measured.

### What was underneath it was worse than a red build

The pattern's `\([^)]*\)` cannot cross a `)` inside a parameter list, and both
functions have one — `params: Params = Params()` and
`left: tuple[float, float] = (0.0, 0.0)`. `saccade.detect` therefore matched nothing.
**`calibration.recenter` matched part of its own signature**, so the mutation was
inserted into the parameter list, the suite reported collection errors, and `mutate`
read the non-zero exit as `caught`.

So that function had been reported covered *for as long as it existed*, and the nightly
on `main` was still printing `caught recenter  2 errors in 0.82s` on 2026-09-18 —
verified by reading run `35323903984`'s log rather than by reasoning about the tool.
With the fix it reports **`caught recenter  5 failed, 374 passed`**: a real test
failure, the first this function has ever produced.

`saccade.detect` is the opposite case and worth separating: the nightly shows
`caught detect  7 failed, 300 passed`, so it was genuinely covered and the stricter
pattern of 2026-09-06 **regressed** it. One fix, two different lies.

### The pattern is gone

`_neuter_source` asks `ast` where a body starts. Three regex failures in a row were
each the fix for the last — a trailing comment defeated the match, then a same-line body
matched and produced a `SyntaxError`, then a nested paren ended the signature early —
and that sequence is the argument: `body[0]` **is** the body, and no punctuation in a
signature can move it. What is left to decide is only where the inserted line goes: a
docstring is stepped over rather than displaced, and a body on the signature's own line
is refused for that definition while its siblings are still neutered.

### And two functions that were never on the list at all

`_function_names` matched `^ *def ([a-z_][a-z0-9_]*)\(`, which **cannot spell a
capital letter**. `photometry._XYZ` and `task.FixPoint` had therefore never been mutated
once, and nothing in any output said so — they were simply absent. Found by replacing
the pattern with the parser and diffing the target lists. Fourth instance of this
harness's recurring shape: quietly examining nothing and reporting success.

### And the first thing the fixed harness found: `task.FixPoint` is covered by nothing

`SURVIVED  FixPoint  379 passed in 13.61s`. Neuter the task vocabulary's
fixation-point shortcut and **the whole suite still passes**, because nothing in this
repository uses it: no test, and none of the three reference tasks, though S1a §6
settles it as vocabulary and S1 §5.1's worked example is `FIX = FixPoint(at=(0, 0),
size=0.3)`. It had never been mutated in its life, so nothing had ever had the chance
to say so.

It has tests now (`tests/test_task.py`, which also gives `task` a test file the
selective gate can map to it). But the more useful finding is the disagreement it
exposes: **the spec's worked example uses a shortcut none of our worked examples use.**
Either the reference tasks should spell fixation points the way a task author will, or
the vocabulary is carrying a name for a thing nobody reaches for. Worth one decision,
and it is a task-layer decision rather than a repair, so it is not made here.

### The cheap win from §3b, taken

Every definition of a name is neutered together, so a name six worlds implement ran six
identical sweeps — six full runs of the suite, same input, same result. `_function_names`
now returns each name once: `run.py` 24 targets → 12, `dio.py` 14 → 6, `welfare.py`
17 → 14, `calibration.py` 24 → 22. Across those eight modules 120 → 94. It changes no
result; it halves the cost of the modules with protocol implementations.

---

## What moved on 2026-09-06

### The thing worth reading first: fluid has a floor, not a ceiling

**Asked of the PI on 2026-09-06 and answered:** *"there is never a ceiling for fluid
reward. only a floor (which can be supplemented after the training/rec session to
reach)."*

Every fluid limit in this repository was built the wrong way round. `bounds` refused a
delivery that would put the day past its "budget", `welfare` stopped the session on
that refusal, and S8 §4 said *"daily fluid budget"* — which is the phrase that made the
reading available and is now corrected in place. Under this lab's protocol a fluid
ceiling **withholds fluid an animal earned in order to satisfy a limit nobody set**,
and stops the session partway through doing it.

What replaced it:

- **`bounds.Floor` is a different type from `bounds.Ceiling`**, and the daily figure
  lives in `Bounds.minima` rather than `Bounds.ceilings`. Same type for both is exactly
  how a minimum came to be compared with `>`: a floor stored as a ceiling reads as one
  at every call site.
- **`bounds.shortfall(name, delivered_today)`** replaces `check_delivery`. It answers
  *how much is still owed*, never *may I deliver*.
- **Nothing refuses a delivery on volume.** The per-delivery magnitude keeps its
  ceiling, enforced when a console *sets* it — which is the right place, since the
  magnitude is a configuration decision and a task can only name it.
- **An unknown day no longer refuses reward.** S8 §5.2's fail-closed rule followed from
  a ceiling; under a floor the argument runs the other way, and the one thing an
  uncountable day must not do is stop paying an animal that is working. `shortfall()`
  answers `None` rather than zero, because a day nobody measured is not a day that went
  well, and `wlx run` prints that as `supplement: UNKNOWN`.

**This is what "ask, do not file" is for.** The question was put to the PI as a
question at the moment the code forced it, and the answer overturned a model that had
been in the spec since M0, had passed its own tests, and had just been wired into every
session. An open-items table would have recorded it and the wrong model would have
shipped.

---

**P4b: the session, and the two guardrails that were not wired to anything.**

The headline is not a feature. `bounds`' fluid check — the welfare-critical one — was
called by nothing outside its own tests, and `run.py` resolved both
`Mark` and `Reward` into nothing at all, behind a comment saying they "belong to the
I/O layer, which has no simulator yet". **`dio.Simulated` had existed for five days.**
So the M1 gate ran a thousand trials, scored them correct, **strobed no event codes
and delivered no reward**, and 307 tests passed. A session with no codes cannot be
aligned to any recording; an animal that is not paid cannot say so. Both failures are
invisible in every artifact the session produces. Now pitfall **P21**.

- **`welfare.py`, the second welfare-critical module.** The day's fluid total
  (including what another deployment already delivered — S8 §5.2b), the restraint
  clock, the `Pump` port, and **`Rig`, which is what a `Reward` action reaches**. The
  split from `bounds.py` is what keeps each reviewable: `bounds` is pure limits with
  no clock and no hardware, and `welfare` is the one file that has to be read to
  answer *can anything deliver reward without the day's accounting seeing it*.
- **`run.Effects`.** A world answers questions; a mark and a reward answer none, so
  they leave through a separate port. **The default refuses.** Wiring it turned 12
  green tests red, and every one of those was a test running a rewarding task whose
  rewards went nowhere — which is the clearest possible statement of the bug.
- **A pump fault is not absorbed.** A solenoid that will not answer is a broken rig,
  and swallowing it would produce a session's worth of correct trials nobody was paid
  for. `Rig` had a second branch catching a fluid ceiling and stopping the session at
  the next trial boundary; the PI's correction removed the premise, and the shape is
  recorded in its docstring because it is the right shape for any *future* stopping
  condition that arrives mid-trial: never raise out of the frame loop, because that
  aborts a trial the animal completed.
- **`taskd` runs blocks.** `scheduler.py` was mutation-clean, handled quotas, requeue
  and criterion transitions, and nothing imported it — so nothing ever advanced past
  the first block, and `_index` was never incremented in the module's whole life.
  `advance()`/`done` exist now and reset the counters and the criterion window,
  because a criterion carried across a block boundary is met on evidence from a
  different task configuration.
- **A flat run of N trials is the block session with one block.** Not a second loop: a
  second loop is a second place for the ceilings to be checked differently.
- **One ceiling ends a session, and it is time out of the cage** — from the animal
  leaving its home cage to going back in, bounded at twelve hours (PI, 2026-09-19).
  **Fluid is not one.** **Chair time is not one either, since 2026-09-19**, and
  neither is a trial count: `max_trials` is gone and chair time is recorded beside
  the limit rather than being it. A rig session refuses to start without the
  out-of-cage mark; a cage-side one declares `CAGE_SIDE` and has no duration
  bound at all. A `RIG_CHAIRED` one carries the mark, no head-fixation, and reports
  restraint as **absent rather than zero**. See "The welfare clock, and the four rulings that reshaped it".
  **History, not current fact:** when this was written the session clock was derived
  from frames rather than the wall, and this line called that what kept "stops at its
  duration ceiling" deterministic, and the honest choice on a rig, where frames *are*
  the clock. **P4d-2a (2026-09-26, spec §10) took that base off every welfare
  duration**: in the simulator frames outran the wall, so the default `rig-fixed` path
  could not record its return. Out-of-cage, restraint and the limit check now read
  `Session.wall_now()` — the wall as read once at session creation, carried forward on
  a monotonic clock — and the frame clock times trials and nothing else. A simulated
  dry run reaches its ceiling only in real time; tests that need the ceiling inject a
  wall clock.
- **`HEAD_FIXED`/`HEAD_RELEASED` are strobed** (4128/4129). Restraint is the one
  welfare quantity with no hardware line, so the codes *are* its durable record —
  which is why they stayed when chair time stopped bounding anything — **for
  `RIG_FIXED` only** since 2026-09-20. **The out-of-cage marks get no codes**, ruled
  2026-09-20: operator-entered rather than measured, so a hardware timestamp would add
  precision to a number that never had it (S8 item 8, closed).
- **The terminal `Marker` is emitted by the framework**, not the task: a task declares
  an `Outcome` and never a marker. Without it a recording has no trial boundaries at
  all, whatever else is in the stream.
- **One validated write path for live parameters.** Validated when offered, applied
  atomically at the next trial boundary, recorded with its origin. A welfare-bounded
  name goes through `bounds.set` and its ceiling; an ordinary one through the task's
  own `Param` declaration — so the console can move reward volume and cannot move it
  past the ceiling, by the same call.
- **Every trial records its block and condition**, not only its resolved parameters.
  Two conditions can resolve to identical values — a catch trial and a signal trial
  differing only in what the task does with them — and an analysis grouping by
  parameters would silently merge them.
- **A session refuses a bounded config belonging to another subject.** Running A
  against B's ceilings is a dose error with a plausible-looking session behind it, and
  nothing downstream compares the two.
- **`wlx run` had no test**, and could not construct a `SessionSpec` after the above.
  It now takes `--bounds` and `--delivered-today`, and reports what it commanded.

**P6's last piece, closed with it.** `gaze.Calibrating` drives a *session* through the
calibration block: it makes each trial's world, collects the fixation from the trials
the task paid for, fits, installs a new mapping version, and writes
`<session>/expcontroller/eye_calibration.yaml` — round-tripped through `wl-preproc`'s
real reader. The composition test that used to stand in for this said in its own
docstring that it was "the shape the driver has to take"; it was, and it was not one.

**The fit averages the hold, not the trial.** A calibration trial *begins* with the
animal looking somewhere else — that is what `Entered("cal")` waits for — so averaging
every sample the trial saw drags each target toward wherever gaze happened to start,
by an amount that depends on how long acquisition took. The resulting map is wrong in
a way neither the conditioning check nor the extent check can see (trap 13's shape
again).

### One ask closed by looking rather than by doing

This file said **"CI is red now and stays red until someone creates a secret"** and
named a PAT only the PI could create. It is not red: `gh run list` shows six
consecutive successes on `main`, and run `33984657820` logs the `wl-preproc` checkout
syncing and `307 passed` with no skips under `WLX_REQUIRE_PREPROC=1`. The secret exists
and the contract tests run.

Same shape as trap 1, one repo in: **a live ask stayed live because nothing re-read the
thing it was about.** The cost here was small — a person's attention, aimed at a job
already done — but this file is where the next session learns what is blocked, and a
blocker that has cleared is exactly as misleading as one that has not been noticed.

### And the harness was wrong again, in the file it matters most in

`welfare.py`'s first mutation sweep reported every `deliver` **caught**. It was not: the
`Pump` protocol's one-line body (`def deliver(self, ml: float) -> None: ...`) makes the
mutation a `SyntaxError`, every definition of that name is neutered together, so the run
reported collection errors and `mutate` reads any non-zero exit as caught. **The
welfare-critical path from a task's `Reward` to the pump was reported mutation-clean on
the strength of a syntax error.**

Caught by reading the output rather than the exit code: `caught deliver  3 errors in
0.60s` is not the shape of a test failing. With the fix, the same function reports
**16 failed** and `welfare.py` is genuinely mutation-clean. Sixth failure of this tool,
and the second that broke toward a false clean by way of an invalid mutation. Trap 7
carries it.

**And the same class of hole, caught in the new contract test.** The calibration-file
test was written with `pytest.importorskip`, which skips silently — including in CI,
where `WLX_REQUIRE_PREPROC=1` exists precisely to turn a missing `wl-preproc` into a
failure. It now uses `test_calibration.py`'s guard. A contract test that is allowed not
to run is not a contract test, which is the same sentence `tests/conftest.py` has
carried since the codec round-trip skipped into a green build.

### Two things this created

**A pump calibration is now an open measurement**, in the same class as the photometer
one. `welfare.Pump` takes millilitres; nothing converts them to solenoid open time, and
`wl-sync`'s board makes clear that the pulse width is ours to choose — it one-shots the
*manual* button at ~199 ms and passes our commanded line straight through the reward-OR
gate. So the number is a per-rig measurement of the pump, and until it exists the real
driver is not written rather than guessed.

**The session grew a world seam.** `Session(world=...)` is where hardware plugs in. It
had to exist for the calibration driver, and it is the first time the claim that "the
loop cannot tell a rig from a simulator" has been exercisable at the session level
rather than the trial level.

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
| ~~P3~~ | ~~`taskd` skeleton~~ | **done 2026-08-31.** ~~roadmap M1 met~~ — **that claim was wrong and is withdrawn 2026-09-06**: M1 also names fake I/O (nothing was strobed or delivered until P4b), demo mode, and an operator document. The first is fixed; the other two are P4 | — | — |
| **P4** | Demo mode: JSONL events, parquet behaviour, config snapshot, directory layout | A simulated session writes a real session directory | S10, S3, S8 | nothing |
| | → **roadmap M1** | 1,000 deterministic trials with full outputs | S8, S9 | — |
| | + operator documentation | The D4 acceptance test; a stranger runs a session | S9 | — |
| ~~P4b~~ | ~~Session management: blocks, scheduler, bounded config, welfare accounting, the live parameter path~~ | **done 2026-09-06** — a session runs blocks with criterion transitions, enforces its one duration ceiling (**time out of the cage**, since the 2026-09-19 rulings; chair time and a trial cap until then) and reports the day's fluid shortfall at close; `welfare.py` is the second welfare-critical module and **wants human review** | — | — |
| **P4c** | Parquet derivation at close ~~; the `labhost` endpoint~~ (`labhost` moved under `console`, ADR-0008 — see P4d-2) | Contract-tested against `wl-preproc`'s published schema | S10 | nothing. Independently ready to pick up; `trials.jsonl` now carries block and condition per row, so the derivation has what it needs |
| ~~P4d-1~~ | ~~The console link: telemetry out, commands in, over a real socket~~ | **done 2026-09-19** — `Session` gains a `Link` port drained once per trial boundary, never per frame; `link.py`'s `Telemetry`/`Staged`/`Refused` message and `SetParameter`/`Stop` commands; `ZmqLink`/`ZmqConsole` over ZMQ PUB/SUB + REQ/REP; `wlx console` as a terminal client. Not welfare-critical and built to stay that way. Three items found and deliberately left open; **one of them (a pump fault publishing nothing) was closed by the PI on 2026-09-19 and one was widened by the same decisions** — see "What moved" above | — | — |
| **P4d-2a** | Close the out-of-cage interval: both ends recorded as wall instants, the return taken at `wlx run`'s terminal as the ELN's stand-in, the clock published after the loop, and a separate in-session clock | **Built on branch `p4d2a-return-to-cage` (2026-09-26), awaiting the PI's welfare review of spec §7.** It merges by fast-forward only after he approves | `docs/superpowers/specs/2026-09-26-P4d2a-return-to-cage-design.md` §7, §10 | **the PI's review** |
| **P4d-2b** | The browser console and `GET /health` (S9a §7), with the `labhost` endpoint it carries (`labhost` is a surface of `console`, not its own process), in six slices b1–b6 | **b1 specified and planned; b2–b6 still to be brainstormed.** Spec `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md`: §1–§4 approved, with the mockup rulings held in §4.0. §4 is slice b1, the read-only console, and its plan is `docs/superpowers/plans/2026-09-26-p4d2b-b1-read-only-console.md`. b2–b6 each get a section as they are designed | that spec | **P4d-2a merging** (b1 builds on telemetry schema 6) |
| P5 | Display adapter, stereo viewports, photodiode patches | Photodiode-ready display | S4, optics | **hardware — ADR-0002 deferred to V1** |
| **P6** | Eye ingest, calibration, saccade detection | Replay-driven gaze, and a calibration map `wl-preproc` can read | S5 | ~~their reader~~ nothing |
| | → ingest | **done 2026-09-01** — protocol verified from source, loopback-tested | — | — |
| | → the calibration fit and its file | **done 2026-09-05** — constellation, per-eye fit, three refusals, round-tripped through their reader | — | — |
| | → the block, the versioned map, the join | **done 2026-09-05** — `tasks/calibration.py`, `Mapping`/`MappingLog`/`Collector`, and `gaze.Tracked`. A whole block runs from scheduled targets to an installed map | — | — |
| | → saccade detection | **done 2026-09-05** — online Engbert–Kliegl, contract-tested to find the same intervals `wl-preproc`'s offline detector finds, wired to both saccade guards | — | — |
| | → wiring the calibration block into `taskd` | **done 2026-09-06** — `gaze.Calibrating` drives a session through the block, fits from the *hold*, installs a version and writes the file `wl-preproc`'s reader accepts | — | — |
| **P7** | I/O behind interfaces: NI DIO, reward, comparator inputs | Absent, simulated and hardware as peers | S6 | a card **and, for reward, a pump calibration** — protocol V10, never measured |
| | → the interface | **done 2026-09-01** — pin map, refusing `Absent`, recording `Simulated`; the `nidaqmx` implementation needs a card | — | — |
| | → the reward path above the pump | **done 2026-09-06** — a task's `Reward` reaches a ceiling-checked delivery and a `Pump` port; the driver that opens copper needs V10 | — | — |
| P8 | Neural plane, both feature sources | post-v1 | S7 | hardware |

**P1–P4b and P4d-1 needed no hardware and are done. P4c and P4d-2 need none either.**
The welfare-critical surface is still exactly two files, `bounds.py` and `welfare.py`
— `link.py` and the rest of P4d-1 deliberately stayed off that list — and **both want
a human before merge** — that is the thing on this list that cannot be done by another
session. P4d-1 adds a second, narrower ask to the same review: see "What moved on
2026-09-19" and `docs/next-session.md` §1.

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
| `wl-works` | no | `prepare-session`, a planned calibration block per session, alerting on bad readings, and an NTP server for lab hosts to synchronize to (ADR-0009) |

Neither blocking item stops P1–P4. Both are built around: codes are allocated in
**4096–32767** (undisputed) and the session id sits behind a provider interface.

---

## Open measurements this creates

**A pump calibration gates real reward delivery** (new 2026-09-06). `welfare.Pump`
takes millilitres because the ceilings are denominated in millilitres; nothing
converts them to solenoid open time, and that conversion is a per-rig measurement of
the pump and line. `wl-sync`'s board one-shots the **manual** button at ~199 ms and
passes our commanded line straight through the reward-OR gate untouched (their
`hardware/README.md`, 2026-08-15 panel-instrumentation entry), so the pulse width is
ours to choose and the volume it yields is ours to measure. Until it is measured the
real pump driver is **not written**, on the same rule as `nidaqmx`: guessing at it now
means a dose nobody measured. **Protocol V10** in `docs/validation.md`; result goes under
`docs/measurements/`.


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
7. **An eighth, 2026-09-26, and this one threw the answer away rather than getting it
    wrong.** `_run_suite` kept pytest's last line. When a flaky test went red on 7 of 41
    unmutated runs in the 09-25 nightly, the log said `1 failed, 673 passed` seven times
    and never which test; and when the same flake landed on 24 mutant runs it added one
    failure to each, which is exactly enough to report a real survivor as `caught`. Now
    every red suite prints its failure lines and every mutant's line ends `<- node ids`.
    **Read the `<-`**: a function caught only by a test that has nothing to do with it
    was not caught. Original entry follows.

    **The mutation harness has now been wrong seven times, and the seventh had been
    lying for as long as the function existed.** `calibration.recenter` and
    `saccade.detect` both take a default argument containing a `)` --
    `left: tuple[float, float] = (0.0, 0.0)`, `params: Params = Params()` -- and the
    pattern's `\([^)]*\)` ends the signature at that inner paren. For `detect` the
    scan then found no colon and the function was simply never matched. For
    `recenter` it found the one in `why: str` and matched **part of the signature**,
    so the mutation was inserted *into the parameter list*: `SyntaxError`, collection
    errors, non-zero exit, `caught`.

    So the module was reported mutation-clean while one of its functions had never
    once been neutered. The nightly on `main` printed `caught recenter  2 errors in
    0.82s` every night, which is the whole tell: two *errors* is not a test failing.

    **Three regex failures in a row, each one the fix for the last.** `[^\n]*` was
    added so a trailing comment could not defeat the match; it swallowed a same-line
    body. `[^:\n]*` fixed that; it could not cross a nested paren. The pattern is gone:
    `_neuter_source` asks `ast` where the body starts, because `body[0]` **is** the
    body and no amount of punctuation in a signature can move it.

    **And the same file had two more functions it had never named.** `_function_names`
    matched `^ *def ([a-z_][a-z0-9_]*)\(`, which cannot spell a capital letter, so
    `photometry._XYZ` and `task.FixPoint` were not on any target list and no output
    ever said so. Both now come from the parser too. Original entry follows.

    **The mutation harness has now been wrong six times, and the sixth is the one that
    matters most.** A body written on the signature's own line -- `def deliver(self,
    ml: float) -> None: ...` -- cannot have a statement inserted after it, so the
    mutation produced a **`SyntaxError`**. The suite then reported *collection errors*,
    `mutate` reads any non-zero exit as the mutation being caught, and every definition
    sharing that name was reported covered without a single test being consulted.

    The name in question was `deliver`, in `welfare.py`: **the welfare-critical path
    from a task's `Reward` action to the pump**, reported as mutation-clean on the
    strength of a syntax error. Found by reading the output rather than the exit code
    -- `caught deliver  3 errors in 0.60s` is not the shape of a test failing, and four
    identical lines for four different definitions is not the shape of four tests
    failing either.

    The offending clause was itself a fix: `[^\n]*` after the colon was added so a
    trailing comment could not defeat the match (see the fifth failure, below), and it
    swallowed a same-line body with the same appetite. Now `[ \t]*(?:#[^\n]*)?` --
    a comment is not a body -- with `tests/test_mutate.py` asserting that both cases
    still behave and that the mutation **parses**. Original entry follows.

    **The mutation harness has now been wrong five times, and the fifth broke the
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

20. **A "not yet" comment is the one claim nothing can check, and it goes stale in
    silence.** `run.py`'s `_apply` executed the display actions and dropped `Mark` and
    `Reward`, saying they "belong to the I/O layer, which has no simulator yet".
    `dio.Simulated` landed five days later and that sentence became false with nothing
    to notice: it is a claim about the *rest of the repository*, and a test suite can
    only check claims about the code under it. The cost was the M1 gate running a
    thousand trials, scoring them correct, strobing no codes and delivering no reward,
    with every test green — and `bounds`' fluid check, the welfare-critical one,
    called by nothing outside its own tests for a week. `scheduler.py` was the same
    shape without the animal: mutation-clean, and `taskd` never imported it, so
    `_index` was never incremented in the module's whole life.

    Three rules, and the first is the one that would have caught it: **a safety
    component ships with its consumer in the same commit, or its absence fails.**
    `run.Unwired` now refuses a mark or a reward it cannot deliver, the way
    `dio.Absent` and `welfare.Absent` refuse. **Test the path, not the piece** — every
    link of that chain was individually tested while the chain was broken. And write
    what a "not yet" is waiting for **by name**, so the next reader can grep it rather
    than believe it. Same family as traps 7 and 18: the question is never whether a
    guardrail passes, it is whether anything reaches it. Now pitfall P21.

21. **A test fixture can satisfy the thing it is meant to violate.** The test that the
    calibration fit uses the *hold* rather than the whole trial put the animal at a
    fixed wrong position first -- and that position sat inside some target's 3° window,
    so on that trial the hold completed from gaze that never moved and the test passed
    for a reason unrelated to the slice under test. Fixed by making the wrong position
    relative to each target. **Watched it fail before trusting it** (`began = 0.0` in
    `Calibrating.observe`), which is what found the fixture bug rather than shipping a
    test that could not fail.

22. **A limit built the wrong way round passes every test it has.** Fluid was modelled
    as a ceiling from M0 until 2026-09-06: `bounds` refused a delivery past a daily
    "budget", `welfare` stopped the session on it, and both were thoroughly tested,
    mutation-clean and internally consistent. **The PI's protocol has no fluid ceiling
    at all** -- only a daily floor, supplemented by hand afterwards -- so all of that
    correctness was in service of withholding fluid an animal had earned.

    Nothing in the repository could have caught it. The tests asserted the model, the
    mutation gate proved the tests could fail, and S8 §4's phrase *"daily fluid
    budget"* is what made the wrong reading available in the first place. What caught
    it was **asking the PI a direct question at the moment the code forced one**
    (CLAUDE.md, "ask, do not file"), on a decision that was animal-facing and expensive
    to get wrong.

    Two durable changes came out of it. `Floor` and `Ceiling` are **different types**,
    because a minimum stored as a maximum reads as a maximum at every call site --
    which is precisely how a floor came to be compared with `>`. And a limit whose
    *direction* is load-bearing now says which it is in its own name: `minima` beside
    `ceilings`, `shortfall` rather than `check_delivery`.

