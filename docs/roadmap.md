# Roadmap

Milestones gate on measured artifacts, not on code existing. Thresholds marked
(proposed) are finalized when their protocol first runs (`docs/validation.md`).

**Governing constraint:** the lab opens **January 2027** and wl-expcontroller is the
day-one stack (D1). v1 is the training ladder plus a first recording task, 2D and
monocular (D2). Anything not on that path is deferred by default.

## M0 — Contracts frozen (research phase exit)
Architecture reviewed; the S0–S12 spec map agreed; message schemas v0 written as
code-ready structures; the division of labor with `wl-sync` signed off; **event-code
vocabulary allocated with `wl-mllib`**; display panel and refresh chosen; **task PC OS
chosen and `PCIe-6343` + DAQmx bench-verified on it (P10)**; NI cards ordered.
Gate: PI sign-off on `docs/design/` and the spec map.

## M1 — Simulated skeleton
`taskd` runs a complete fixation task headless against simulators (replayed OpenIris JSON,
synthetic features, fake I/O); CI green; a 1,000-trial simulated session is deterministic
and produces the full log/data outputs. **Keyboard/mouse demo mode runs the same task.**
**Operator documentation begins here** — people arrive with or before the animals, and a tech or
student runs the rigs day to day (P8), so a "how to run a session" document is an M1 deliverable
rather than a later one. Gate: recorded sim session artifact committed; a generated task reviewed
from its rendered diagram and its simulation report alone (the D4 acceptance test).

## M2 — Display validated on rig hardware
Protocol V1 on at least one rig: photodiode-measured onset lag and variability, dropped-frame
rate over a 2 h stress run; protocol **V9** for split-panel per-half photometry and stereo
viewport geometry measured rather than derived. Gates (proposed): onset variability < 1 ms; drops < 0.1%.

## M3 — Eye loop live
OpenIrisDPI streaming into `taskd` on-rig; calibration, recentering and drift correction
working with a versioned gaze mapping; protocol V3: stall distribution plus end-to-end
gaze-step-to-display-change latency. Gate: measured latency distribution committed;
**saccade-triggered updates demonstrated inside saccadic suppression**, or the design
revised. Gaze-window grace parameters set from data, never from the paper's numbers.

## M4 — I/O and sync fabric
Reward command path to `wl-juicer`, event words, both photodiode comparators, chair-motion
gate and the `wl-sync` barcode all recorded and reconstructable; protocols V2 (TTL loopback)
and **V2b (digital-input read latency)** measured; **photodiode-gated state progression
demonstrated**; **V6** (sync reconstruction round-trip) green. Gate: a full bench "session"
reconstructs with zero unexplained events.

## M5 — Operations complete
Preflight, one-action launch, pause and emergency stop, manual reward, generated parameter
panel with per-trial snapshots, per-condition counters, abort-reason readout, live plots,
test screens including the per-eye alignment target, remote console. Protocol **V7** (audio
onset). Gate: a naive operator runs a full training session start to finish without a
terminal — **attempted early and repeatedly from M1 onward**, not first tried here.

## M6 — First real task, first animal
One production task (fixation -> detection) end-to-end on the bench and then in a pilot
session, including **stimulation tiers 1 and 2 with welfare interlocks live** and fluid
accounting reconciled against the delivered line. Gate: PI approves; overnight synthetic
soak (V5) passed on that exact build (P12).

## M7 — Data and lab integration
Session outputs ingested by `wl-preproc`; `labhost` endpoint serving the session summary;
the wl-works amendment agreed and ELN autopopulation working end to end. Gate: a session
appears in the ELN with no manual transcription.

## M8 — Stereo
Disparity stimuli on the split-screen stereoscope; per-eye calibration and vergence
alignment procedure; a stereo task run in a pilot session. Cheap by construction if M2
built viewports properly — expensive if it did not, which is why M2 is gated on geometry.

## M9 — Neural-contingent loop (stimulation tier 3)
`neurofeatd` and `rhxfeatd`; protocol V4 (signal-generator/saline closed loop) on both
paths; **V8** (RHX backpressure headroom) under multi-probe load with low-latency mode CPU
headroom recorded. Gates (proposed): median <= 6 ms on the SpikeGLX path; the RHX path
measured for the first time anywhere; runaway detector and refractory enforcement verified.

## M10 — Second rig, release prep
Config-driven rollout; per-rig acceptance records; `wl.yaml` and the `wl-orchestrator`
registry entry; ADR-0004 decided; S12 swap verification run once; public-release hygiene
check (P13); consider methods-paper write-up.
