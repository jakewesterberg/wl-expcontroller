# S10 — Data outputs and lab integration

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §12; S3 §5

---

## 1. Where our files go

`wl-preproc/contracts/paths.py` is a **frozen interface** and already names us:

```
<root>/<YYYY-MM-DD_NN>/
├── session_manifest.yaml
├── syncbox/  spikeglx/  rhs/  ohdpi/  bcam/     ← SYSTEMS, each with a DONE marker
└── expcontroller/                                ← ours
```

**We are deliberately not a `SYSTEMS` member.** Their reasoning: members need a `DONE` marker, an
`AcquisitionSystem` row, and a timebase extractor, and `timebase/extract.py` asserts
`set(EXTRACTORS) == set(SYSTEMS)` — *"an experiment controller's log carries no barcode and needs
no alignment, so adding it there would demand an extractor that cannot exist."*

Two consequences: **we write no `DONE` marker** and never block session-complete detection; and
**our alignment comes entirely from the codes we strobe**, which is why S3 §4's obligation to
mirror every meaningful decision as a code is not optional.

---

## 2. What we write

| Artifact | Contents |
|---|---|
| Event log (JSONL) | Every event: the code word, frame index, monotonic time, and the *meaning* the recorded streams cannot carry |
| Behavioural tables (parquet) | One row per trial: outcome, RT, condition, target positions, **the full resolved parameter snapshot**, gaze-mapping version, per-trial gaze staleness (S5), token state, stim deliveries observed |
| Config snapshot | Rig, subject, task and code versions; bounded config in force; optics geometry and both measured optical paths; display mode; `stimulus_calibration_id`; the whole precedence chain, not just the resolved values |
| Parameter-change log | Keyed by the sequence number `PARAM_CHANGE` carries |
| Plot declaration | So the live view reproduces exactly offline (S9 §4) |
| Online calibration map | Per eye, in the form S5 §8 defines |

**Streamed, not accumulated** (S8 §5.2). A crash loses the tail, not the session — the lesson
`wl-sync` learned when its own recorder held a day in memory.

Raw neural data never touches the task PC.

---

## 3. The session manifest

`SessionManifest` carries `session_id`, `subject`, `rig`, `started_at`, `started_at_source`,
`expected_systems`, `acquisition_build_id`, `stimulus_calibration_id`, `notes`.

Two fields are ours by their own definition:

- **`started_at_source: BEHAVIORAL_CONTROL`** — *"The behavioural control system where present;
  the sync box's NTP-stamped start otherwise."* We stamp the session start label when we are
  running.
- **`stimulus_calibration_id`** — a reserved slot S4 §9 now defines.

And one field settles an argument elsewhere: **`subject` is a single string.** A directory
describes one subject, so with two animals a day the session id must change when the subject does
(S3 §2). That is a consequence of their frozen contract, not our preference.

**Who writes the manifest is open** — us, ingest, or wl.works. It sits at the directory root
rather than under `expcontroller/`, which suggests not us alone.

---

## 4. The lab-host endpoint

We implement `wl-preproc`'s existing lab-host protocol rather than inventing a second one: same
transport, bearer token, `GET /health`, `POST /jobs`, same status codes and timing constants.
**wl-works' contract tests already run against a fake implementation of it.**

| Direction | Carries | Mechanism |
|---|---|---|
| ELN → rig | subject, probe serials, `insertion_number`, `trajectory_id`, planned task, session intent | `prepare-session` action |
| rig → wl-works, live | session, subject, task, state, trial counts, fluid against ceiling, preflight result | **readings on `GET /health`** |
| rig → ELN, finished | trials run, performance by condition, fluid delivered, versions, parameter-change log, abort census | **a file in the session directory**, ingested by `wl-preproc` |

The split follows their own rules: new observables become *readings* rather than endpoints, and
result upload is declined because *"wl.works pulls; this host never pushes."*

**No welfare-affecting action is ever published through this protocol.** wl-works' permission
model is flat by design; on a rig the worst case is fluid, stimulation, or a session started on
an animal nobody is standing next to.

---

## 5. What we ask of other repos

All four amendment documents in this repo converge here:

| Repo | Ask |
|---|---|
| `wl-sync` | Session id readable by a rig host; a subject change mints `_02` |
| `wl-preproc` | `PARAM_CHANGE` escape; ownership split recorded; codec declared as an artifact; **online-calibration reader**; per-trial gaze staleness in `EyeQuality` |
| `wl-works` | Host list as configuration; `prepare-session`; a **planned calibration block per session** |

Two of these block real things rather than tidying: without the calibration reader
`CalibrationSource.ONLINE` is unavailable for every session under ADR-0005, and without the
session id we cannot name our own output directory.

---

## 6. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Who writes `session_manifest.yaml` | directory assembly |
| 2 | Behavioural table schema, column by column | analysis contracts |
| 3 | Where image sets and their versions live on disk | S4 §6 |
| 4 | Whether kiosk sessions enter this pipeline at all | S13 |
