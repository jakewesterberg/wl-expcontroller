# Roadmap

Milestones gate on measured artifacts, not on code existing. Thresholds marked
(proposed) are finalized when their protocol first runs (docs/validation.md).

## M0 — Contracts frozen (research phase exit)
Architecture.md reviewed; message schemas v0 written as code-ready structures; sync
conventions signed off; open questions in architecture.md resolved or explicitly
deferred; display refresh target chosen per rig; DAQ hardware chosen with Linux
drivers bench-verified (P10). Gate: PI sign-off on docs/design/.

## M1 — Simulated skeleton
taskd runs a complete fixation task headless against simulators (replayed OpenIris
JSON, synthetic features, fake I/O); CI green; 1,000-trial simulated session is
deterministic and produces the full log/data outputs. Gate: recorded sim session
artifact committed.

## M2 — Display validated on rig hardware
Protocol V1 on at least one rig: photodiode-measured onset lag and variability,
dropped-frame rate over a 2 h stress run. Gates (proposed): onset variability
< 1 ms; drops < 0.1%.

## M3 — Eye loop live
OpenIrisDPI streaming into taskd on-rig; calibration routine working; protocol V3:
stall distribution + end-to-end gaze-step-to-display-change latency (artificial eye
or replay + photodiode). Gate: measured latency distribution committed; gaze-window
grace parameters set from data.

## M4 — I/O and sync fabric
Reward pump, event words, sync barcode, photodiode all recorded in SpikeGLX streams;
protocol V2 (TTL loopback) measured; offline reconstruction round-trips synthetic
sessions exactly. Gate: a full bench "session" reconstructs with zero unexplained
events.

## M5 — Behavior parity (first real task)
One production task (e.g., fixation -> detection) runs end-to-end on the bench and in
a pilot animal session. Parity checklist vs the MonkeyLogic bridge version: trial
timing, reward accounting, event completeness, experimenter workflow. Gate: PI
approves migration of that task; bridge remains available.

## M6 — Neural-contingent loop
neurofeatd on the acquisition PC; protocol V4 (signal-generator/saline closed loop):
neural-event-to-TTL distribution measured with multi-probe load and low-latency-mode
CPU headroom recorded. Gates (proposed): median <= 6 ms on the primary path; fallback
(Open Ephys + Falcon) documented on the same bench if primary misses.

## M7 — Multi-rig + release prep
Config-driven rollout to remaining rigs; per-rig acceptance records; ADR-0004
decided; public-release hygiene check (P13); consider methods-paper write-up.
