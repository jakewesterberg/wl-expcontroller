# Pitfalls and mitigations (risk register)

The failure modes we are explicitly designing against. Each has an owner-trigger:
the moment it becomes someone's active job. Review this file at every milestone gate.

| ID | Risk | Severity | Core mitigation |
|---|---|---|---|
| P1 | Unmeasured timing treated as fact | High | Measurement-first culture; validation protocols; committed per-rig numbers |
| P2 | Framework creep / second-system effect | High | Scope fence in ADR-0001; generality needs a second concrete use |
| P3 | Python runtime nondeterminism (GC, GIL) | Medium | Hot-path discipline; managed GC; RT scheduling; escalate to C only on measurement |
| P4 | Linux graphics stack surprises | Medium | Pinned stack per rig; photodiode re-validation after any change |
| P5 | SpikeGLX real-time gap (vendor numbers vs our topology) | High | C++ client on loopback; features-not-raw over the wire; measured fallback path |
| P6 | OpenIrisDPI tail latencies (~2% frames >= 10 ms) | Medium | Staleness-aware gaze logic; grace windows; offline reconstruction as truth |
| P7 | Sync debt discovered at analysis time | High | Hardware-truth rule from day one; reconstruction scripts with round-trip tests |
| P8 | Codebase drift across AI sessions; bus factor | High | CLAUDE.md conventions; tests as contract; ADRs; human review list |
| P9 | License incompatibility discovered late | Medium | ADR-0004 inventory now; DisplayAdapter seam keeps engine swappable |
| P10 | Hardware bought before Linux drivers verified | Medium | Bench-verify drivers on the exact distro before purchase |
| P11 | Works in sim, fails on rig | High | Simulators are first-class; identical interfaces sim/hardware; soak tests |
| P12 | Animal time wasted on immature software | High | Bridge on MonkeyLogic; parity gates before any task migrates; bench soak first |
| P13 | "Eventually public" hygiene debt | Low | Public-ready from day one: no data, no secrets, clean history, cited facts |

## Expanded notes

**P1 — Unmeasured timing.** AI-assisted development makes this worse, not better:
generated code radiates plausibility whether or not the rig meets timing. Rule: a
latency/jitter number may only enter docs, papers, or decisions from a measurement
script whose output is committed under `docs/measurements/<rig>/`. The vendor's
SpikeGLX figures are loopback + C++ + same-machine; our topology differs; we measure
ours (validation V4). Recorded TTLs in the SpikeGLX streams are the only ground truth.

**P2 — Framework creep.** The graveyard in `docs/research/landscape.md` is full of
general frameworks that outlived their maintainer's attention. We build the
Westerberg-lab controller for these rigs. An abstraction earns its place only when a
second concrete consumer exists in this lab. LOC growth without new rig capability is
a review flag.

**P3 — Python nondeterminism.** Bounded per-frame work; preallocated buffers;
`gc.disable()` during trials with explicit collection in inter-trial intervals;
consider `gc.freeze()` after startup; SCHED_FIFO + CPU isolation for taskd; profile
with py-spy under load. Port a hot path to C/C++ only when a measurement demands it.
The frame budget at 240 Hz is ~4.2 ms — treat it as a hard allowance in review.

**P4 — Graphics stack.** X11-vs-Wayland, compositor bypass, and NVIDIA vsync behavior
all move timing. Pin distro/driver/session type per rig in that rig's config, record
it with every measurement, and re-run V1 (photodiode) after any change. OLED
task displays additionally need luminance/persistence QA before visual-science use.

**P5 — SpikeGLX gap.** The unmeasured regime (cross-machine, Python) is exactly where
naive designs land. Design pins the fetch client to the acquisition PC (C++,
loopback), ships features not raw data, and keeps the Open Ephys + Falcon Output path
(published 9.2 ms median, 384 ch) as the fallback and cross-check. Multi-probe CPU
headroom with "low latency" mode enabled is a rig-acceptance measurement, not an
assumption.

**P6 — Tracker stalls.** ~2% of OpenIrisDPI frames >= 10 ms (max ~50 ms) on the
authors' hardware. Fixation logic uses hold-last with a staleness ceiling and grace
periods; trial aborts require corroboration (multiple stale/out-of-window samples).
Measure our own stall distribution (V3) before freezing window parameters.

**P7 — Sync debt.** Retrofit synchronization is how multi-machine rigs quietly ruin
datasets. The sync fabric (shared barcode line, photodiode, event words, camera GPIO)
is milestone M0/M1 work and blocks everything downstream. Reconstruction code ships
with round-trip tests against synthetic recordings.

**P8 — Drift and bus factor.** Conventions in CLAUDE.md; CI green as merge condition;
ADRs so decisions survive personnel and sessions; welfare-critical modules require
human review; onboarding doc once a trainee joins. Boring technology choices are a
deliberate mitigation here.

**P12 — Protecting the science.** The bridge path (MonkeyLogic + OpenIrisDPI analog
out) exists so recording can start on schedule regardless of this project. A task
migrates to wl-expcontroller only after the M5 parity checklist passes on the bench
and in a pilot session. No animal session runs on a build that has not passed an
overnight synthetic soak.
