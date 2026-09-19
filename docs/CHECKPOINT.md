# Where this build actually is

**Last updated 2026-09-19**, at the commit this file was committed in. Check
`git log --oneline -1`; if it has moved far, distrust the numbers here before you
distrust the reasoning. Numbers go stale, arguments do not.

> **This file describes `p4b-session-management`, not `main` — and, for the P4d-1
> material below, `p4d1-console-link`, built on top of it.** `p4b-session-management`
> is **11 commits** ahead of `main`; ten are pushed (`origin/p4b-session-management`),
> the eleventh (`8693299`) is local only. `p4d1-console-link` branches from that same
> `8693299` — run `git log --oneline p4b-session-management..p4d1-console-link` for
> the current list. **Deliberately not a count written here**: a commit count of a
> branch, stated in a file tracked on that branch, is wrong the instant it is
> committed — writing it is itself one more commit than it counted, and this file
> got that wrong three separate times before the number was removed rather than
> corrected again. `p4d1-console-link` **is committed locally only — not pushed, and
> not merged** (`git ls-remote origin p4d1-console-link` finds nothing; the push and
> the merge decision are the PI's, not a session's). `main` is still at `300d7d1`
> and knows about neither branch. Both exist rather than merging straight in
> because `bounds.py` and `welfare.py` are welfare-critical and want a
> human before they merge (CLAUDE.md); `p4d1-console-link` adds a second, narrower ask
> to the same review rather than opening a new one (see the P4d-1 entry under "What
> moved on 2026-09-19", and `docs/next-session.md` §1). **`git branch --show-current`
> before believing anything below** — on `main` this file does not describe the tree
> you are looking at, and on `p4b-session-management` alone it describes everything
> except P4d-1.
>
> **P4b has now run in CI, and the first run failed** (`34769913502`, 2026-09-13):
> pytest green on all three Pythons, mutation gate red on `calibration` and `saccade`.
> Not survivors — the harness could not find two functions. Fixed 2026-09-19; see
> "What moved" and trap 7's seventh entry.

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
| Tests | **421, green — with `.[dev,contract,console]` installed** (`p4d1-console-link`; `p4b-session-management` alone is 383). **The extras qualifier is not decoration.** P4d-1 added the `console` extra (pyzmq, msgpack) and, until 2026-09-19, neither CI job installed it: measured with both imports blocked, **9 tests fail** — `tests/test_link.py` ×7 and `tests/test_cli.py::test_wlx_run_with_link_{lets_a_real_console_attach,closes_it_when_the_session_ends}` — so "421, green" was a statement about a developer machine and not about CI. `.github/workflows/ci.yml` now installs `console` on both jobs. `bounds` and `welfare` are mutation-clean under the *fixed* harness; see trap 7's sixth and seventh entries for why that qualifier keeps needing to be re-earned. `link.py`/`taskd.py`/`cli.py` (P4d-1) swept clean 2026-09-19 too — 36 target names, 0 survivors, 0 skips |
| CI | **Green on `main` through `300d7d1`**, verified 2026-09-06 by reading the runs rather than the workflow: six consecutive successes, the `wl-preproc` checkout syncing, `307 passed` with no skips and `WLX_REQUIRE_PREPROC=1` in force. **P4b failed in CI on 2026-09-13 and is green as of 2026-09-19.** The 09-13 run (`34769913502`) escalated to a full sweep as predicted, took 1h46m, and reported `MUTATION GATE FAILED: calibration, saccade` — two functions the harness could not find rather than two survivors (trap 7, seventh entry). Run `35433303094` on `afc7d04` is the fix, **verified by reading its log rather than its exit code**: 21 modules, 215 caught, **0 survivors and 0 skips**, `383 passed` at every baseline, and the four functions the commit was about each reporting a real failure — `recenter 5 failed`, `detect 7 failed`, `_XYZ 4 failed`, `FixPoint 4 failed`. The nightly schedule runs on `main`, which does not contain P4b, so those greens say nothing about it. pytest on 3.11, 3.12 and 3.13, plus a **mutation gate**. Selective since 2026-09-05: `tools/mutation_gate.py` runs the modules a change can have affected and escalates to all of them on anything structural, with the **full sweep nightly** — the per-push gate cannot see a test deleted from one file that was the only cover for a function in another. It refuses to run at all if a module is in neither its gated nor its exempt list. Functions that already return immediately are reported `NOT MUTABLE` rather than counted as survivors (trap 7) |
| Welfare-critical modules | **two: `bounds.py` and `welfare.py`**, and they are the only two. `bounds` is pure limits — ceilings, and a daily **floor**; `welfare` holds the day's total, the restraint clock, the pump, and `Rig` — the object a task's `Reward` action actually reaches. **Both require human review before merge** (CLAUDE.md, S8 §7) |
| Fluid | **A floor, not a ceiling** (PI, 2026-09-06). The daily figure is a minimum the animal must reach, topped up by hand after the session; **no delivery is ever refused on volume**. Only the per-delivery magnitude is a ceiling. Chair time and trial count are ceilings and do end a session. S8 §4–§5 were written the other way round and now carry the correction |
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
  a real one.
- **`bounds.py` — welfare-critical, and pure.** Ceilings a task cannot express and a
  console cannot exceed, **and a daily fluid floor** — a minimum, not a budget. Fluid
  reconciled against the delivered line rather than what we commanded. No clock, no
  hardware, no state that outlives a question. `Floor` and `Ceiling` are different
  types so the two cannot be confused at a call site, which is exactly how the daily
  figure came to be compared with `>`. **Requires human review before merge**.
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

## What moved on 2026-09-19

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

```
python3 tools/mutate.py --all --returns None wl_expcontroller/link.py
  baseline: 421 passed in 12.34s -- 14 functions, all caught (of, encode, decode,
  _encode_command, _decode_command, publish, drain, queue, __init__, close,
  __enter__, __exit__, send, receive) -- restored: 421 passed in 9.54s

python3 tools/mutate.py --all --returns None wl_expcontroller/taskd.py
  baseline: 421 passed in 13.09s -- 16 functions, all caught (__post_init__,
  directory, now, head_fixed, head_released, set, staged, _command, _params,
  _apply_staged, _load, _plan, _agent, make, run, publish) -- restored: 421 passed
  in 10.24s

python3 tools/mutate.py --all --returns None wl_expcontroller/cli.py
  baseline: 421 passed in 12.37s -- 6 functions, all caught (_load_trial,
  _load_allocation, _load_bounds, _clock, render, main) -- restored: 421 passed
  in 9.57s
```

**Zero `SURVIVED`, zero `SKIPPED`, no hang, across all three modules — 36 functions,
each `caught` by a real assertion failure** (`__post_init__` and `run` each fail 40+
of the 421 tests; the narrowest, `_clock` and `head_released`, fail exactly one — the
range a coverage tool should show, not a flat number). Full transcripts in
`.superpowers/sdd/2026-09-19-p4d1-console-link/task-7-report.md`.

**Three things found and deliberately left open, recorded rather than fixed —
`docs/next-session.md` §6 has the full account, and item 3 is also in §1 beside the
`bounds.py`/`welfare.py` review already waiting:**

1. **A pump fault publishes nothing.** `welfare.deliver` raises, `Rig` deliberately
   does not swallow it, and the exception propagates past `Session.run`'s `finally`
   with no final `Telemetry` frame and no `stopped_because` — a console watching a
   rig break, unattended, cage-side, sees only silence. What a console should show
   when the rig itself is faulty is a design question for a later slice.
2. **A change staged on a session's literal last pass is never applied** —
   `_apply_staged()` gets no further pass once the loop decides to stop. The final
   frame still shows it `staged` beside `STOPPED:`, an implicit signal rather than
   silence, but `--set X --stop` over real sockets does not land both commands in
   the same `drain()` batch — Task 6's reviewer reproduced this 20/20 times (not
   committed under `docs/measurements/`, and not a claim about this system's timing;
   the number says the ordering held every time it was tried, nothing about speed) —
   so the obvious way to hit this on purpose does not. Residual risk: a
   `SetParameter` landing on whichever pass a welfare ceiling or "every block
   finished" resolves on.
3. **`wlx console --set reward_correct=...` is the first person-invocable path that
   moves a reward limit** (`Session.set` → `bounds.set`). `cli.py` does not become
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
- **Two ceilings end a session** — chair time and trials — and chair time runs
  **from head-fixation**, which a session now refuses to start without. **Fluid is not
  one of them.** The session
  clock is derived from frames rather than the wall, which is what keeps "stops at its
  restraint ceiling" deterministic; on a rig frames *are* the clock, so it is the
  honest choice there too.
- **`HEAD_FIXED`/`HEAD_RELEASED` are strobed** (4128/4129). Chair time is the one
  welfare quantity with no hardware line, so the codes *are* its durable record.
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
| ~~P4b~~ | ~~Session management: blocks, scheduler, bounded config, welfare accounting, the live parameter path~~ | **done 2026-09-06** — a session runs blocks with criterion transitions, enforces its chair-time and trial ceilings, and reports the day's fluid shortfall at close; `welfare.py` is the second welfare-critical module and **wants human review** | — | — |
| **P4c** | Parquet derivation at close ~~; the `labhost` endpoint~~ (`labhost` moved under `console`, ADR-0008 — see P4d-2) | Contract-tested against `wl-preproc`'s published schema | S10 | nothing. Independently ready to pick up; `trials.jsonl` now carries block and condition per row, so the derivation has what it needs |
| ~~P4d-1~~ | ~~The console link: telemetry out, commands in, over a real socket~~ | **done 2026-09-19** — `Session` gains a `Link` port drained once per trial boundary, never per frame; `link.py`'s `Telemetry`/`Staged`/`Refused` message and `SetParameter`/`Stop` commands; `ZmqLink`/`ZmqConsole` over ZMQ PUB/SUB + REQ/REP; `wlx console` as a terminal client. Not welfare-critical and built to stay that way. Three items found and deliberately left open — see "What moved" below | — | — |
| **P4d-2** | The console's HTTP/WS surface (S9a §7) and the `labhost` endpoint it carries (S9a §7, superseding P4c's framing — `labhost` is a surface of `console`, not its own process) | A browser reaches a running session on the LAN, and `wl-works` can pull session state from `GET /health` | S9a §7 | nothing |
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
| `wl-works` | no | `prepare-session`, a planned calibration block per session, alerting on bad readings |

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
7. **The mutation harness has now been wrong seven times, and the seventh had been
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

