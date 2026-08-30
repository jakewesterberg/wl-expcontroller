# ADR-0002: Display engine

- Status: Proposed
- Date: 2026-08-30

## Context
Need frame-locked, photodiode-verifiable stimulus presentation on Linux from Python,
with flip-locked TTL hooks. Verified options in docs/research/landscape.md.

## Decision (proposed)
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
