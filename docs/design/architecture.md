# Architecture (working draft)

Status: draft for review. Contracts here are proposals until frozen at milestone M0.

## Principles

1. Two planes per rig, joined by messages and by hardware TTLs — never by shared code
   or shared clocks.
2. The SpikeGLX sample clock is the single ground truth. Anything scientifically
   meaningful becomes an edge or word in a SpikeGLX-recorded digital stream.
3. Software timestamps are for control flow; hardware timestamps are for analysis.
4. Hardware sits behind small interfaces; every interface has a simulator.
5. The hot loop does bounded work: no allocation, no disk I/O, no unbounded queues.

## Per-rig topology

```
             OpenIris PC (Windows)                Acquisition PC (Windows)
             OpenIris + OpenIrisDPI               SpikeGLX  <-- Neuropixels
             500 Hz binocular dDPI                   |  loopback (127.0.0.1)
                 |            \                   neurofeatd (C++)
                 | UDP:9003    \ analog out          |  MUA features
                 | (poll)       \ (bridge to ML)     |  ZMQ PUB, msgpack
                 v               v                   v
        +---------------------- Task PC (Linux) ----------------------+
        |  taskd (Python)                                             |
        |    eye client (poll thread)   neural client (SUB thread)    |
        |    trial state machine        session/parameter manager     |
        |    display adapter (PsychoPy) -----> task display + photodiode
        |    io adapter -> TTLs: reward pump, stim trigger, event word, sync
        +-------------------------------------------------------------+
                 |                                    |
                 v                                    v
          reward / stimulator                 NIDQ / OneBox digital+analog inputs
          (OneBox WavePlayer for waveforms,   (records photodiode, all TTLs,
           hardware-triggered by our TTL)      event words, camera GPIO sync)
```

Experimenter UI runs on the task PC (separate process, ZMQ telemetry; never in the
hot loop). Rig count: 3-4, one config file per rig.

## Components

| Component | Runs on | Language | Job | Simulator |
|---|---|---|---|---|
| taskd | Task PC (Linux) | Python | State machine, display, gaze windows, I/O, session + trial logging | Full headless run against replayed/synthetic inputs |
| neurofeatd | Acquisition PC | C++ | `fetchLatest` on the filtered AP stream -> per-channel MUA features -> ZMQ PUB | Synthetic feature publisher (Python) |
| openiris | OpenIris PC | (existing C#) | dDPI tracking; UDP 9003 poll server; analog out as bridge | UDP replay server feeding recorded JSON |
| ui | Task PC | Python | Experimenter console, online plots, parameter edits | n/a (talks ZMQ to taskd) |

Welfare-critical modules (human review required per CLAUDE.md): reward scheduling and
limits, session duration/fluid accounting, stimulation gating.

## Message contracts (draft v0)

- **Eye samples** (openiris -> taskd): OpenIris-native poll on UDP 9003
  (`WAITFORDATA` -> JSON). taskd stamps arrival with CLOCK_MONOTONIC and computes
  staleness. We do not modify the tracker protocol.
- **Neural features** (neurofeatd -> taskd): ZMQ PUB/SUB, msgpack. Message: schema
  version, feature vector (float32[]), channel map hash, headCt (SpikeGLX sample
  index of window end), publisher monotonic timestamp, sequence number. Target rate
  0.5-1 kHz; consumer treats it as latest-wins.
- **Control/telemetry** (ui <-> taskd): ZMQ REQ/REP for commands, PUB for telemetry.
- **Hardware truth**: every trial event gets (a) a strobed event word on digital
  lines into NIDQ, and (b) a JSONL log entry carrying the word, frame index, and
  monotonic time. Photodiode patch on every visual transition that matters.

## Latency budgets (planning numbers, to be replaced by measurements)

| Path | Budget | Basis |
|---|---|---|
| Eye sample -> gaze decision | <= 1 display frame + staleness ceiling | OpenIrisDPI 1.1 ms median processing; ~2% >= 10 ms stalls (paper) |
| Gaze decision -> display change | next flip (4.2 ms at 240 Hz; 16.7 ms at 60 Hz) | engine flip-locked |
| Neural event -> feature at taskd | ~2-5 ms | vendor loopback histogram + one network hop (measure: V4) |
| Neural event -> stim TTL | ~3-6 ms (estimate) | above + decision + DAQ write (measure: V4) |
| Fallback (Open Ephys + Falcon path) | ~9-13 ms | published plugin measurement |

Display refresh is an open question with real leverage: at 240 Hz the frame quantum
drops to ~4.2 ms and dominates nothing (cf. REC-GUI's 240 Hz demonstration).

## Sync conventions (day-one requirements)

1. One shared sync line (e.g., 1 Hz + session-unique barcode) into: NIDQ, OneBox AI,
   OpenIris camera GPIO. 2. Photodiode into NIDQ analog. 3. Event words: 16-bit
   strobed digital into NIDQ. 4. Every TTL we emit is also recorded. 5. Offline
   reconstruction scripts are part of the repo, with round-trip tests.

## Data outputs

Per session: JSONL trial/event log + parquet behavioral tables + config snapshot +
code version; offline NWB export aligned to the SpikeGLX clock. Raw neural data never
touches this repo or the task PC.

## Open questions (tracked toward M0)

- Display refresh target per rig (60 vs 120 vs 240 Hz) and monitor QA for OLED.
- taskd concurrency model: threads vs single-loop with non-blocking polls (prototype
  both under the frame budget; measure).
- DAQ hardware for TTL/event words on Linux (LabJack vs NI vs microcontroller;
  driver verification before purchase — pitfalls P10).
- Feature definition v0 for MUA (band, rectify/integrate window, CAR handled
  server-side) — scientific choice, PI-owned.
