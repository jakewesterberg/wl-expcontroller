# wl-expcontroller

Research and design repository for a lab-built experiment controller for closed-loop
nonhuman primate neurophysiology: a Python, Linux-first alternative to NIMH MonkeyLogic
for the Westerberg lab rigs (KU Leuven). Part of the `wl-*` repo family.

**Status: research phase. No code yet — deliberately.** This repo holds the software
landscape survey, the architecture sketch, the risk register, and the validation plan.
Code lands only after the contracts in `docs/design/` are settled (roadmap milestone M0).

## Why this exists

As of 2026-08-30 there is no actively maintained, Linux-native, Python-first NHP
task-control suite. The two healthy suites are NIMH MonkeyLogic (Windows + MATLAB) and
MWorks (macOS-only); every Linux-capable option (REC-GUI, Pype, PLDAPS) is dormant.
Our rigs need three closed-loop regimes — gaze/behavior-contingent display control,
neural-signal-contingent control from real-time Neuropixels MUA, and event-triggered
stimulation/feedback — against an OpenIrisDPI (digital dual-Purkinje) eye tracker and
SpikeGLX acquisition. The full survey with sources: `docs/research/landscape.md`.

## Scope (v1)

- 3-4 head-fixed macaque recording rigs; Neuropixels via SpikeGLX on Windows
  acquisition PCs (that layer is unchanged by this project)
- Task controller: Python on Linux
- Closed-loop regimes: (a) gaze/behavior-contingent display control at frame level;
  (b) neural-signal-contingent control from real-time MUA features;
  (c) event-triggered stimulation/feedback via hardware TTL
- Eye tracking: OpenIrisDPI over UDP (analog-out as bridge/fallback)

Non-goals for v1: a general community framework, freely-moving or home-cage paradigms,
and hard-real-time (sub-millisecond software loop) guarantees.

## Approach — five commitments

1. **Spec first.** Module boundaries, message contracts, and sync conventions are
   written and reviewed before code (`docs/design/`). Irreversible choices get ADRs.
2. **Sim first.** Every component runs headless against simulators (replayed OpenIris
   JSON, synthetic neural features, fake I/O) in CI. Hardware sits behind interfaces.
3. **Measure everything.** No timing number is ever asserted from code reading. Every
   timing-relevant path gets a measurement protocol (`docs/validation.md`) and its
   results are committed under `docs/measurements/<rig>/`. Recorded TTLs are ground
   truth.
4. **Thin core.** Build on maintained engines (PsychoPy for display, ZMQ for
   messaging); write the minimum that is ours (state machine, calibration, I/O glue,
   session management). Generality is added only when a second concrete use exists.
5. **Bridge, don't bet the science.** Rigs can come up on MonkeyLogic with OpenIrisDPI
   analog-out while v1 matures; tasks migrate individually on demonstrated parity.
   Experiments are never hostage to this project's schedule.

## Layout

```
docs/research/     verified findings (landscape, OpenIrisDPI, SpikeGLX real-time)
docs/design/       architecture + decisions/ (ADRs)
docs/pitfalls.md   risk register with mitigations
docs/roadmap.md    milestones with measurable acceptance gates
docs/validation.md measurement protocols
docs/measurements/ per-rig measured results (committed artifacts)
CLAUDE.md          working conventions for AI-assisted development
```

## License

Not yet chosen — see ADR-0004 (`docs/design/decisions/`). Repo stays private until
that decision is made.
