# ADR-0002: Display engine

- Status: Accepted 2026-08-31
- Date: 2026-08-30

## Context
Need frame-locked, photodiode-verifiable stimulus presentation on Linux from Python,
with flip-locked TTL hooks. Verified options in docs/research/landscape.md.

## Decision
PsychoPy used strictly as a library (no Builder), behind a thin `DisplayAdapter`
interface owned by us. Rationale: photodiode-measured 0.34 ms onset variability on
Ubuntu (Bridges et al. 2020), active maintenance (2026.2.3), flip callbacks, huge
community. The adapter keeps the engine swappable and is the seam our simulators use.

## Alternatives considered
- Raw pyglet/OpenGL: fewer deps, but re-derives solved problems (gamma, text, movies,
  calibration); no timing pedigree of its own.
- MWorks: macOS-only. Bonsai/BonVision: Windows-only, C#. Unity (M-USE/NERV-style):
  C#, frame-level only, wrong toolchain for the lab.

## Consequences
GPL-3 gravity on distribution (see ADR-0004). We own gaze-space calibration and all
rig timing validation (validation V1). Per-rig graphics stack gets pinned (X11 vs
Wayland decision recorded per rig; re-validation after driver/OS changes — P4).

## Accepted 2026-08-31

Accepted unchanged. Nothing found since 2026-08-30 argued against it, and two things
argued for it: S4 needs a display module with flip-locked callbacks to draw the
photodiode patches unconditionally, and S11 could not declare a display dependency
while this stayed Proposed — so `wlo stack` was building a task PC missing the
software the rig's whole visual path depends on.

The alternative was spiking raw pyglet/OpenGL first. Declined: it re-derives gamma,
text, movies and timing that PsychoPy has already solved *and measured* (0.34 ms
onset variability on Ubuntu, photodiode-verified), and our own V1 has to measure this
rig regardless of engine. The seam that makes the spike cheap later — `DisplayAdapter`
— is the same seam that makes deferring it cost nothing now.

**Consequence taken deliberately:** GPL-3 gravity on distribution. ADR-0004 already
leaned that way; S13's kiosk is the one thing that might reopen it, and does not yet.
