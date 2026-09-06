# wl-expcontroller

Research and design repository for a lab-built experiment controller for closed-loop
nonhuman primate neurophysiology: a Python, Linux-first replacement for NIMH MonkeyLogic
on the Westerberg lab rigs (KU Leuven). Part of the `wl-*` repo family.

**Status: M0 signed off 2026-08-31; code since.** The contracts in `docs/design/` are
settled and the package exists — a declarative task model with load-time checks, a trial
loop, gaze ingest and calibration, event encoding, a session record, and sessions that run
blocks under welfare bounds. **Nothing has touched hardware**, and the display and the real
DAQ card are the two legs of the day-one path that are still blocked on it.

`docs/CHECKPOINT.md` is where this repository says what is actually true; this file is a
summary and goes stale faster.

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

Non-goals for v1: a general community framework, freely-moving paradigms, a GUI task
builder, and hard-real-time (sub-millisecond software loop) guarantees.

**A cage-side touchscreen kiosk is in scope, but not in v1** (spec map S13) — a single-screen
deployment with no stereoscope, no DAQ and no neural plane. It is the second concrete consumer
that earns the hardware interfaces their generality.

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
docs/CHECKPOINT.md       where the build actually is -- read this first
wl_expcontroller/        the package
tasks/                   reference tasks, the event allocation, a reference bounded config
tools/                   the mutation harness and the gate that selects for it
CLAUDE.md                working conventions for AI-assisted development
```

Two files are **welfare-critical and require human review before merge**:
`wl_expcontroller/bounds.py` and `wl_expcontroller/welfare.py`. They are kept small so
that a person can actually read them before signing one off.

Start with `docs/superpowers/specs/2026-08-31-controller-architecture-design.md` for the
reasoning, and `docs/design/architecture.md` for the summary.

## License

**Apache-2.0** — see `LICENSE`, and ADR-0004 (`docs/design/decisions/`) for why. In
short: nothing here imposes copyleft (there is no PsychoPy import, and OpenIris talks
over UDP as a separate process), and `tasks/` is destined for `wl-mllib` under
ADR-0007, which a GPL-3 core would have made impossible.

This is research software for a lab that does not exist yet — **no part of it has run
on hardware.** Read `docs/CHECKPOINT.md` before assuming any of it works.
