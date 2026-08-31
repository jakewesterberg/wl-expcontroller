# wl-expcontroller

Research and design repository for a lab-built experiment controller for closed-loop
nonhuman primate neurophysiology: a Python, Linux-first replacement for NIMH MonkeyLogic
on the Westerberg lab rigs (KU Leuven). Part of the `wl-*` repo family.

**Status: design phase. No code yet — deliberately.** This repo holds the software
landscape survey, the architecture, the risk register, and the validation plan. Code lands
only after the contracts in `docs/design/` are settled (roadmap milestone M0).

## Why this exists

As of 2026-08-30 there is no actively maintained, Linux-native, Python-first NHP
task-control suite. The two healthy suites are NIMH MonkeyLogic (Windows + MATLAB) and
MWorks (macOS-only); every Linux-capable option (REC-GUI, Pype, PLDAPS) is dormant. The
full survey, with sources: `docs/research/landscape.md`.

Our rigs need gaze-contingent display control at frame level, neural-signal-contingent
control from real-time SpikeGLX **and** Intan RHX data, event-triggered stimulation through
an Intan RHS, stereoscopic presentation, and deep integration with the rest of the `wl-*`
stack. Nothing existing does that on Linux from Python.

## Scope (v1)

- **Two** head-fixed macaque recording rigs (five breakout boards fabbed, so headroom
  exists). Neuropixels via SpikeGLX on Windows acquisition PCs; Intan RHS for recording and
  stimulation. Those layers are unchanged by this project.
- Task controller: Python on Linux, driving an NI PCIe-6343.
- **v1 target:** the training ladder plus a first recording task, 2D and monocular.
  Stereoscopy and the neural-contingent loop follow, and are not architecturally precluded.
- Eye tracking: OpenIrisDPI over UDP as the control path; its analog copy recorded so the
  eye PC's lag stays measurable.

Non-goals for v1: a general community framework, freely-moving or home-cage paradigms, a
GUI task builder, and hard-real-time (sub-millisecond software loop) guarantees.

## Approach — five commitments

1. **Spec first.** Module boundaries, message contracts and sync conventions are written and
   reviewed before code (`docs/design/`, `docs/superpowers/specs/`). Irreversible choices get
   ADRs.
2. **Sim first.** Every component runs headless against simulators (replayed OpenIris JSON,
   synthetic neural features, fake I/O) in CI. Hardware sits behind interfaces. Tasks are
   primarily model-authored, so simulated sessions and keyboard/mouse demo mode are how a
   task is reviewed — not a nicety (ADR-0006, pitfalls P15).
3. **Measure everything.** No timing number is asserted from code reading. Every
   timing-relevant path gets a protocol (`docs/validation.md`) whose results are committed
   under `docs/measurements/<rig>/`. Recorded TTLs are ground truth.
4. **Thin core, and don't rebuild the neighbours.** Build on maintained engines (PsychoPy for
   display, ZMQ for messaging). `wl-sync` already owns session identity, the barcode codec,
   the log format and event routing; we consume them rather than reinvent them. Generality is
   added only when a second concrete use exists.
5. **Staged exposure, not a fallback.** wl-expcontroller is the day-one stack (ADR-0005) — the
   MonkeyLogic bridge was retired because the task library it assumed does not exist. The rig
   contract stays controller-agnostic and the task PC dual-boots, so the swap remains possible;
   what protects the science is measurement gates and the training ladder, not a second system.

## Layout

```
docs/research/           verified findings (landscape, OpenIrisDPI, SpikeGLX real-time)
docs/design/             architecture + decisions/ (ADRs)
docs/superpowers/specs/  design specs and the S0-S12 spec map
docs/pitfalls.md         risk register with mitigations
docs/roadmap.md          milestones with measurable acceptance gates
docs/validation.md       measurement protocols
docs/measurements/       per-rig measured results (committed artifacts)
CLAUDE.md                working conventions for AI-assisted development
```

Start with `docs/superpowers/specs/2026-08-31-controller-architecture-design.md` for the
reasoning, and `docs/design/architecture.md` for the summary.

## License

Not yet chosen — see ADR-0004 (`docs/design/decisions/`). Repo stays private until that
decision is made.
