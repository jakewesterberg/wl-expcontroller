# M0 review packet

**What signing this off means:** the contracts in `docs/design/` and
`docs/superpowers/specs/` are frozen, and code starts. Nothing here asks you to read seventeen
spec files — §3 is the part that needs you, and it is fifteen questions.

**Date:** 2026-08-31. **Specs:** S0–S13 plus the architecture, the spec map and the optics
drawing. **Open items across them:** 76, of which 6 are already answered, 24 are engineering
calls I have made (§4), 18 are blocked on other repositories (§5), 13 are blocked on hardware
that does not exist yet (§6), and **15 need you** (§3) — **four answered 2026-08-31, eleven remain**.

---

## 1. The decisions this rests on

Recorded in ADR-0005, ADR-0006, ADR-0007 and the architecture spec §2. In one line each:

wl-expcontroller is the day-one stack · v1 is the training ladder plus a first 2D monocular
recording task · MonkeyLogic interchangeability at the rig-contract layer only · tasks are
model-authored, so within-trial logic is declarative data · split-screen stereoscope means stereo
is two viewports on one framebuffer · both SpikeGLX and Intan record, either can gate, Intan
always stimulates · stim in three tiers with 1 and 2 in v1 · live parameter control with per-trial
snapshots · taskd and console always separate · lab integration is pull-based.

---

## 2. What has actually been established, that wasn't known on 2026-08-30

Six things that changed the design, all found by reading neighbouring repositories:

1. **The event codec already exists and is frozen** in `wl-preproc`. This project came within one
   spec of building a second one.
2. **`wl-preproc` already reserved `expcontroller/`** for us by name, deliberately outside
   `SYSTEMS`, so we write no `DONE` marker and never block ingest.
3. **The calibration model is not ours** — raw vector `CR1 − CR4`, affine or second-order on
   OpenIrisDPI's own basis. Only the procedure is ours.
4. **A ring of calibration targets is degenerate** on the second-order basis. The intuitive
   pattern would have silently foreclosed second-order calibration for every session.
5. **NI-DAQmx does not support Fedora**, the lab standard. The task PC deviates to Ubuntu 24.04.
6. **A slow RHX client halts acquisition** — our control software can destroy the experiment it
   is controlling (P14).

---

## 3. What needs you — fifteen questions

### 3.1 Science (6)

| # | Question | My position |
|---|---|---|
| ~~1~~ | ~~MUA feature definition v0~~ **Answered: both types, selectable per experiment** — envelope on the SpikeGLX path, RHX's own threshold crossings on the Intan path. Band, threshold and window stay per-experiment | ✔ |
| 2 | Are SpikeGLX and Intan features **deliberately matched**, or allowed to differ? | Matched, unless a study never switches source. They compute differently by default — SpikeGLX does CAR server-side, RHX filters on GPU |
| 3 | **Saccade-detection algorithm** and its parameters for the online detector | Engbert–Kliegl as the default, since `wl-preproc`'s offline suite already includes it and agreement becomes measurable |
| ~~4~~ | ~~Session duration from first trial or first reward~~ **Answered: chair time, from head-fixation.** Needed a console action and two new event codes, since it is the one welfare quantity with no hardware line | ✔ |
| 5 | Default **re-queue policy** by abort reason | Fixation break re-queued at end of block; wrong choice not re-queued. Both overridable per block |
| ~~6~~ | ~~Runaway thresholds~~ **Answered: rate window plus session total, numbers from protocol.** Per-delivery charge bounds already exist, so a count bound gives a session charge ceiling implicitly | ✔ numbers pending protocol |

### 3.2 Rig and animals (5)

| # | Question | Note |
|---|---|---|
| 7 | **Measure IPD per animal** | Sets the whole stereoscope geometry via `a = 3.27·E` |
| 8 | **Chair and head-post geometry** — does a mirror carriage 4.9–6.2 cm from the eyes fit? | If not, the symmetric-field condition cannot be met and the trade changes |
| 9 | **Photodiode patch placement** confirmed against the real optics | Recommendation: bottom strip, 2.18 cm × full width, via a ±17° vertical stop |
| 10 | **Tandem panel: is burn-in protection fully defeatable?** | Disqualifying if not — pixel-shift silently corrupts a calibrated gaze mapping |
| 11 | **Sustained full-field luminance at 100% APL** for that panel | The number that decides how low we sit, and therefore panel lifetime |

### 3.3 Kiosk, protocol, and process (4)

| # | Question | Note |
|---|---|---|
| ~~12~~ | ~~Kiosk fluid against the daily budget~~ **Answered: yes, one budget.** wl-works holds the ledger and pushes the day's total in `prepare-session`; an unknown prior total fails closed | ✔ |
| 13 | **Kiosk supervision** — is a person notified when it stops? | Fail-closed already applies; this is about who finds out |
| 14 | **Kiosk recording model** | Recommendation: a lighter record of its own, not the session directory — minting a synthetic session id would create the second identity authority S3 spent its length deleting |
| 15 | **Push the repository.** The declared remote does not exist | Blocks anything resolving `wl.yaml`'s `remote` field |

---

## 4. Engineering calls I have made — overrule any of these

Listed so they are visible rather than buried. None need an answer; all are reversible.

**Task model:** transitions fire in declared order, with an explicit priority field available for
the ambiguous case · `Outcome` is `wl-mllib`'s enum directly, not a task-local alias · the review
artifact has one renderer, callable from the console and from a CLI.

**Platform:** Ubuntu 24.04 LTS on the task PC · PyQtGraph for live plots · `rhxfeatd` and
`neurofeatd` share a **contract, not an implementation** — the two paths differ enough that a
shared base would be a false economy · our synthetic generator feeds `wl-preproc`'s existing
harness rather than a second one.

**Operations:** an *unknown* preflight check blocks like a failed one, and says which it was —
"we could not tell" is not "fine" · a console may attach to a session it did not start,
read-only, until it takes the write lock · behaviour agents model outcome distributions and
reaction times, not realistic gaze traces; replayed recordings cover what a synthetic animal
cannot.

**Data:** the session record is streamed, not accumulated · fluid reconciles against the sync
box's delivered line, and reward is refused if the daily total cannot be reconstructed after a
restart. That last one is the only place in the design that deliberately fails closed, and it is
welfare-critical rather than an engineering call — flagged here so it is not missed.

---

## 5. Blocked on other repositories

One consolidated handover per repo (spec map §Handovers). **Two of these block real work:**

- **`wl-preproc` — the online-calibration reader.** Without it `CalibrationSource.ONLINE` is
  unavailable for every session, and it is the source they rank *above* carry-forward.
- **`wl-sync` — the session id.** Without it taskd cannot name its own output directory.

The rest are cheap: the `PARAM_CHANGE` escape, the ownership split, the codec as a declared
artifact, a `prepare-session` action, and a planned calibration block per session.

---

## 6. Blocked on hardware that does not exist

Not answerable before January, and **none of them block M0** — they block the measurements that
gate M2 onward: `PCIe-6343` + DAQmx on Ubuntu (V2, V2b) · tracker staleness distribution and the
OpenIris PC tuning (V3) · RHX latency, which has **no published figure anywhere** (V4) · RHX
backpressure margin (V8) · display timing per mode (V1) · panel photometry and ABL interocular
coupling (V9) · audio onset (V7).

**The purchase that unblocks the most, soonest, is the NI cards** — 12–13 weeks, and the
Windows side needs them regardless, so the buy carries no software risk.

---

## 7. What happens on sign-off

In order, and each is testable before the next starts:

1. **Load-time checker and the task schema** — S1 §9's ten checks. Nothing else can be verified
   until a task can be validated.
2. **Simulator harness** — replayed eye data, synthetic behaviour agents, and the golden-file
   round trip through `wl-preproc`'s own `decode_stream`. This is the product's verification
   loop, not a test fixture.
3. **`taskd` skeleton against simulators** — a complete fixation task, headless, deterministic
   over 1,000 trials. Roadmap M1.
4. **Keyboard/mouse demo mode** — the moment a generated task becomes reviewable in thirty
   seconds, which is what makes ADR-0006 safe.

Steps 1, 2 and 4 need no hardware at all.
