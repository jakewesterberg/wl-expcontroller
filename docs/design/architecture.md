# Architecture

Status: current summary. Reasoning, sources and alternatives live in
`docs/superpowers/specs/2026-08-31-controller-architecture-design.md`; this file is the
orientation document CLAUDE.md sends you to first. Where the two disagree, the spec wins
and this file is stale.

Contracts here are proposals until frozen at milestone M0.

## Principles

1. Two planes per rig, joined by messages and by hardware TTLs — never by shared code or
   shared clocks.
2. **The sync box defines session time.** `wl-sync` owns session identity, the barcode
   codec, the log format and event-code routing. We consume them; we do not mint them.
3. Anything scientifically meaningful becomes an edge or word in a recorded stream.
   Software timestamps are for control flow; hardware timestamps are for analysis.
4. Hardware sits behind small interfaces; every interface has a simulator.
5. The hot loop does bounded work: no allocation, no disk I/O, no unbounded queues, and
   it never renders a plot, serves a request, or holds a UI.
6. **Declare once, derive many.** Parameters, trial outcomes, plots, stimuli and gaze
   mappings are versioned data with provenance, not code. One declaration drives
   validation, the console UI, the saved record and the downstream contracts.

## Per-rig topology

```
   OpenIris PC (Windows)          Task PC (Linux)              Acquisition PC (Windows)
   OpenIris + OpenIrisDPI         taskd + console              SpikeGLX <- Neuropixels
   500 Hz binocular dDPI          NI PCIe-6343                 NI PXIe-6353 (nidq)
        |         \                    |                             ^
        | UDP:9003 \ ACCES DAC         | MDR68 x2                    |
        | (control) \ (recorded copy)  |                             |
        v            v                 v                             |
   +--------------- wl-sync breakout board (2U) ----------------------+
   |  conditioning, level shifting, isolation, mux, comparators        |
   +---+--------------------+---------------------+------------------+
       |                    |                     |
       v                    v                     v
   sync box (Pi/CM5)    Intan RHS            wl-juicer / wl-shook /
   barcode, session     record + stimulate   cameras / speakers / mic
   identity, log
```

**Two rigs in v1** (the breakout spec budgets cabling for two; five boards are fabbed, so
headroom exists). One config file per rig.

## The task PC's interface

Fixed in copper by `wl-sync`'s breakout board. See that repo's `hardware/README.md` and
breakout spec §3 and §9.2.

- **Digital out (19):** 16 event-code bits on **P0.8–P0.23** (not zero-based), event
  strobe, reward commanded, stim trigger.
- **Digital in (4):** task-patch photodiode comparator, flip-patch photodiode comparator
  (a frame clock), chair-motion trigger from `wl-shook`, RHS stim output.
- **Analog in (9):** eye X/Y both eyes (from the ACCES DAC), joystick X/Y, 3 misc BNC.
- **Not in copper:** touchscreen and audio output. Both are host-side, and touch events
  reach the recording clock only as strobed event codes.

The two photodiode comparators returning to us turn two offline checks into online
guarantees: state progression can be gated on physical stimulus onset, and dropped frames
are detected at the display surface.

## Components

| Component | Runs on | Language | Job | Simulator |
|---|---|---|---|---|
| `taskd` | Task PC (Linux) | Python | Trial execution, display, gaze logic, DIO, session record | Full headless run against replayed/synthetic inputs |
| `console` | Any machine | Python | Experimenter UI, live plots, parameter writes, preflight, test screens | Runs against a fake `taskd` |
| `neurofeatd` | Acquisition PC | C++ | SpikeGLX `fetchLatest` on the filtered AP stream -> MUA features -> ZMQ PUB | Synthetic feature publisher |
| `rhxfeatd` | Intan host | C++/Rust | RHX Spike Output socket -> features -> ZMQ PUB; bounded reader | Synthetic spike-raster publisher |
| `labhost` | Task PC | Python | The pull-only endpoint wl-works polls | Contract tests |
| `openiris` | OpenIris PC | (existing C#) | dDPI tracking; UDP 9003; remote API; analog out | UDP replay server |

Welfare-critical modules requiring human review: reward scheduling and limits, fluid and
session-duration accounting, token-to-fluid conversion, stimulation bounds and gating, and
the bounded-config loader that enforces them.

## The task model

**Within a trial: declarative data.** States, guarded transitions, entry/exit actions,
outcome codes. `taskd` executes it; the task never owns the frame loop. Statically
checkable, exhaustively simulatable, renderable as a diagram.

**Between trials: ordinary Python.** Condition selection, blocks, staircases, adaptive
updates.

Representation is **Python declarations** (dataclass/pydantic) — plain text, diffable, and
readable in an ordinary IDE with autocomplete and type checking. Tasks are primarily
model-authored under experimenter direction, so the API optimizes for verifiability and
review rather than authoring ergonomics.

Event codes are **allocated in `wl-mllib`, never invented in a task**; validation refuses
an unregistered code at load time.

A session is a sequence of **blocks** (condition set, parameter overrides, length rule,
transition) and **interludes** (sub-tasks such as calibration that the session enters and
leaves without ending). Token economies require session-scoped state and a persistent
display layer that per-trial scenes do not reset.

## Message contracts (draft v0)

- **Eye samples** (openiris -> taskd): OpenIris-native UDP poll on 9003
  (`WAITFORDATA` -> JSON). We stamp arrival with `CLOCK_MONOTONIC` and compute staleness.
  The protocol is not modified. The ACCES analog copy is a recorded channel, not the
  control path.
- **Neural features** (`neurofeatd`/`rhxfeatd` -> taskd): ZMQ PUB/SUB, msgpack,
  schema-versioned; feature vector, channel-map hash, source sample index, publisher
  monotonic time, sequence number. Latest-wins.
- **Control/telemetry** (console <-> taskd): ZMQ REQ/REP for commands, PUB for telemetry.
  Bearer token, rate limit, and a write-arbitration rule for concurrent writers.
- **Hardware truth:** every trial event gets a strobed word into the recorders and a JSONL
  record carrying the word, frame index and monotonic time.

## Stereo, as viewports

Split-screen mirror stereoscope on **one panel**: each eye views one half through
redirection mirrors. Therefore one window, one flip, one refresh clock, no genlock —
**two viewports on one framebuffer**, in cyclopean coordinates with disparity as a
stimulus property. The monocular v1 task is the zero-disparity case of the same path.

Per-eye viewport geometry (center, folded optical path length, deg/pixel) is measured, not
derived. Mirror angles set vergence, so alignment is a calibrated parameter with a real
alignment procedure. Photodiode patches sit outside both viewports. Panel left/right
nonuniformity is by construction an interocular mismatch and is photometered in V1.

## Neural plane and stimulation

Both systems record; either may gate the loop; **Intan always stimulates.**

| | Local-activity gating | Distant-area gating |
|---|---|---|
| Source | Intan RHX Spike Output socket | SpikeGLX `fetchLatest`, filtered AP stream |
| Client | `rhxfeatd`, Intan host | `neurofeatd`, acquisition PC, C++, loopback |
| Artifact | Severe (same amplifier); RHS amp-settle plus our blanking | Absent |

RHS stimulation is **hardware-triggered from a digital input** — no software in the trigger
path. Stim parameters are pushed over RHX's TCP command interface at safe points only
(session start, block boundaries, ITI), **read back and confirmed**, and bounded by the
rig/subject config. Delivery is counted against the RHS stim-output line, not against
intent.

Three stimulation tiers: epoch-triggered and gaze-triggered are **v1** (so welfare
interlocks are v1 work); neural-triggered is post-v1.

## Sync conventions (day-one requirements)

Owned by `wl-sync`; our obligations are to feed it correctly. One shared barcode line into
the recorders and the camera GPIOs; two photodiode patches with fixed roles; 16-bit strobed
event words; every TTL we emit also recorded; offline reconstruction scripts with
round-trip tests.

## Data outputs and lab integration

Per session: JSONL trial/event log, parquet behavioral tables, a complete config and
provenance snapshot (resolved parameters, bounded config, gaze-mapping versions, task and
code versions, plot declaration, parameter-change log), and a DONE marker conforming to
`wl-preproc`'s published schema. Raw neural data never touches the task PC.

**The rig cannot push to the ELN.** wl-works binds only to WireGuard and lab machines have
no route in, and `wl-preproc` enforces "never initiates a connection" with an AST guardrail.
Integration is pull-based and reuses `wl-preproc`'s existing lab-host protocol, in three
directions: wl-works pushes a `prepare-session` action carrying the ELN metadata bundle;
live session state is exposed as **readings on `GET /health`**; and the finished session
summary is **a file in the session directory** that `wl-preproc` ingests, because the
protocol declines result upload. No welfare-affecting action — reward, stimulation, session
start, parameter change — is ever published through it, since wl-works' permission model is
flat by design. Drafted at `docs/pending-wl-works-amendments.md`.

Behavioral visualization lives here; **neural visualization stays in `wl-expviz`**.

## Platform

**NI-DAQmx 2026 Q2 supports RHEL 9.6/10.0, openSUSE 15.6/16.0 and Ubuntu 22.04/24.04 LTS —
not Fedora** (read 2026-08-31). `wl-stack` standardizes the lab on Fedora, so the task PC
deviates deliberately: **Ubuntu 24.04 LTS**, recorded as a rig-class decision, dual-booting
Windows to satisfy the MonkeyLogic swap. `PCIe-6343`-on-Linux is **UNVERIFIED** until a card
runs on a bench (P10).

## Open questions

Tracked in the design spec §16. The ones that block others: escape-hatch strictness (S1),
touchscreen configuration, display panel and refresh, photodiode patch placement against
the real optics, and the event-code allocation.
