# ADR-0002: Display engine

- Status: **Proposed. Deferred to V1** (PI, 2026-08-31) — neither stack is built properly until a rig can measure both
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

## Reopened 2026-08-31, the same day it was accepted

Accepting this was too quick, and installing PsychoPy is what showed it. Four things
that should have been weighed and were not:

1. **`pip install psychopy` pulls 81 dependencies** — `py2app`, `dmgbuild`, `flake8`, a
   Sphinx docs theme, `MeshPy`, `Phidget22`, `gevent`, `pygame`, `opencv-python`,
   `pandas`, `matplotlib`, `moviepy`, `h5py`, `pyarrow`. That is an application being
   installed on a rig, not a library, and every one is an upgrade that can break a
   recording week.
2. **A Python ceiling of 3.12**, which is a symptom of that weight rather than a quirk.
3. **We already cannot use its coordinate system.** `geometry.py` exists because a
   folded optical path with two viewports and a software vergence offset is not
   expressible in PsychoPy's monitor model. One of its principal offerings is unusable
   here.
4. **Its stimuli are stateful objects that advance themselves**, and S4 §5 makes motion a
   pure function of parameters, seed and frame index — so every moving stimulus would be
   working against the grain, and deterministic reconstruction would be fighting it.

What survives is real: Bridges et al.'s photodiode pedigree, and a large tested stimulus
library.

**So: spike the thin stack first** (PI, 2026-08-31). A `DisplayAdapter` over a window,
a vsync-locked flip and fragment shaders — our fifteen appearances are mostly 10–40 lines
of GLSL. Measure it under V1 on the same rig. If it hits the timing, take it; if not,
PsychoPy is still there and we have lost days rather than months.

**The seam exists precisely to make this cheap, and accepting the ADR without exercising
it was the mistake.** The spike is `tools/spike_display.py`, labelled throwaway.

## Ruling 2026-08-31: decide after V1

**Neither stack is built properly yet.** The spike stays a spike, PsychoPy stays
installed, and the choice is made when a rig exists and V1 can measure both under the
same photodiode protocol.

The recommendation was to build the thin stack now, on the grounds that we already
cannot use PsychoPy's units model or its stateful stimuli, so we would be taking 81
dependencies for stimulus generation we would partly rewrite. **That reasoning is
unchanged and stands as the case to re-read in January** — what the ruling rejects is
committing display code before anything can measure it, which is the same discipline
P1 applies to every other number in this project.

**What it costs:** P5 becomes hardware-blocked, so the run of packages needing nothing
from anyone ends at P4. **What it buys:** no chance of building the display layer twice,
and a decision made on a photodiode rather than on a laptop that already produced one
misleading verdict (P4a).
