# Display spike — swap-interval timing on a development machine

> **This is not a V1 measurement and must never be cited as one.** V1 is a photodiode
> on a rig, measuring when light reached the panel. This is `time.perf_counter()`
> around a buffer swap on a macOS laptop, measuring when the GPU let go of a frame.
> The two answer different questions, and only the first is about the animal's
> experience. Recorded here because P1 requires numbers to live under
> `docs/measurements/` with their conditions, including the ones that decide nothing.

**Machine:** macOS (darwin 25.6.0), 120 Hz internal panel, windowed unless noted.
**Date:** 2026-08-31. **Script:** `tools/spike_display.py`, and `/tmp` control for PsychoPy.

## What was compared

| Stack | median | sd | min | long frames |
|---|---|---|---|---|
| PsychoPy 2026.2.3 (pyglet), windowed | **8.336 ms** (120.0 Hz) | **1.30 ms** | 1.772 ms | **1.79%** |
| glfw + moderngl, first attempt | 8.418 ms (118.8 Hz) | 4.78 ms | **0.432 ms** | 36.0% |
| glfw + moderngl, pipeline drained | 8.337 ms (119.9 Hz) | 3.21 ms | 0.950 ms | 15.5% |
| glfw + moderngl, fullscreen, first attempt | 4.521 ms (221 Hz) | 5.85 ms | 0.604 ms | 47.7% |

## What it settled

**Feasibility, yes.** A Gabor is ~25 lines of GLSL over one quad; the two photodiode
patches are eight more and are drawn unconditionally every frame. Three dependencies
(`glfw`, `moderngl`, `numpy`) against PsychoPy's 81, and it runs on **Python 3.13**,
which PsychoPy cannot.

**`swap_interval(1)` is not enough, and that is the finding.** The first attempt showed
36% long frames and a 0.432 ms minimum -- swaps returning before the GPU had finished, so
the loop free-ran. Fullscreen made it *worse* (221 Hz on a 120 Hz panel), which is the
signature of vsync not being enforced at all rather than of a fast display. It looked
like evidence against the thin stack and was evidence against the loop.

Forcing the pipeline to drain after the swap moved the median onto the panel rate
exactly. **PsychoPy does this deliberately**, and knowing to is a large part of what its
timing pedigree actually buys -- which is transferable knowledge rather than a
dependency.

## What it did not settle, and cannot

**Whether the residual jitter is the stack or the loop.** Drained, the thin stack still
shows 3.21 ms sd against PsychoPy's 1.30 on the same machine. That gap could be several
things and **macOS is not the target platform**: the rig is Linux, fullscreen, with the
compositor bypassed, where the mechanisms differ entirely. Chasing it here would be
optimising against a machine nobody will run an experiment on.

## Recommendation

**Keep ADR-0002 reopened and make this a V1 comparison on the rig.** Run both stacks
under the same photodiode protocol, at each display mode, and take the one that hits the
timing. It costs nothing to defer: `DisplayAdapter` exists, P5 has not started, and the
thin stack now has a working reference implementation to measure.

**And do not compare display stacks on a development machine again.** The first two rows
above would have been read as a verdict by anyone who did not run the control.
