# Pitfalls and mitigations (risk register)

The failure modes we are explicitly designing against. Each has an owner-trigger:
the moment it becomes someone's active job. Review this file at every milestone gate.

| ID | Risk | Severity | Core mitigation |
|---|---|---|---|
| P1 | Unmeasured timing treated as fact | High | Measurement-first culture; validation protocols; committed per-rig numbers |
| P2 | Framework creep / second-system effect | High | Scope fence in ADR-0001; generality needs a second concrete use |
| P3 | Python runtime nondeterminism (GC, GIL) | Medium | Hot-path discipline; managed GC; RT scheduling; escalate to C only on measurement |
| P4 | Linux graphics stack surprises | Medium | Pinned stack per rig; photodiode re-validation after any change; no screen sharing during recording |
| P5 | SpikeGLX real-time gap (vendor numbers vs our topology) | High | C++ client on loopback; features-not-raw over the wire; measured fallback path |
| P6 | OpenIrisDPI tail latencies (~2% frames >= 10 ms) | **High** | Staleness-aware gaze logic; grace windows; offline reconstruction as truth |
| P7 | Sync debt discovered at analysis time | High | Hardware-truth rule from day one; `wl-sync` owns the fabric; round-trip tests |
| P8 | Codebase drift across AI sessions; bus factor | High | CLAUDE.md conventions; tests as contract; ADRs; human review list |
| P9 | License incompatibility discovered late | Medium | ADR-0004 inventory now; DisplayAdapter seam keeps engine swappable |
| P10 | Hardware bought before Linux drivers verified | **High** | Bench-verify `PCIe-6343` + DAQmx on the exact distro before commissioning |
| P11 | Works in sim, fails on rig | High | Simulators are first-class; identical interfaces sim/hardware; soak tests |
| P12 | Animal time wasted on immature software | **High** | **Bridge removed (D1) — see expanded note for the replacement mitigation** |
| P13 | "Eventually public" hygiene debt | Low | Public-ready from day one: no data, no secrets, clean history, cited facts |
| **P14** | **RHX TCP backpressure halts acquisition** | **High** | Bounded dedicated reader; drop-oldest; budgeted channel/rate; falling-behind is a loud alarm |
| **P15** | **Model-authored tasks are plausibly wrong** | **High** | Declarative within-trial layer; allocated-not-invented codes; simulated sessions; demo mode; review by rendered diagram |
| **P16** | **Live parameter change becomes an undocumented discontinuity** | **High** | Full per-trial parameter snapshot; event-coded changes; atomic ITI application; provenance on every write |
| **P17** | **Our fluid total is a lower bound, not a total** | Medium | Reconcile against the sync box's record of the delivered line, never against commanded |

## Expanded notes

**P1 — Unmeasured timing.** AI-assisted development makes this worse, not better:
generated code radiates plausibility whether or not the rig meets timing. Rule: a
latency/jitter number may only enter docs, papers, or decisions from a measurement
script whose output is committed under `docs/measurements/<rig>/`. Vendor SpikeGLX figures
are loopback + C++ + same-machine; Intan publishes no figure at all; our topology differs
from both. Recorded TTLs are the only ground truth.

**P2 — Framework creep.** The graveyard in `docs/research/landscape.md` is full of general
frameworks that outlived their maintainer's attention. We build the Westerberg-lab
controller for these rigs. An abstraction earns its place only when a second concrete
consumer exists in this lab. Note that gaze-contingent rendering and neural-threshold
gating **already meet that test** and belong in the core vocabulary; a general task DSL
that also targets MATLAB does not, which is why D3 puts interchangeability at the
rig-contract layer instead.

**P3 — Python nondeterminism.** Bounded per-frame work; preallocated buffers;
`gc.disable()` during trials with explicit collection in inter-trial intervals; consider
`gc.freeze()` after startup; SCHED_FIFO + CPU isolation for `taskd`; profile with py-spy
under load. The console is a separate process precisely so no UI or plotting work can
share the hot loop's runtime.

**P4 — Graphics stack.** X11-vs-Wayland, compositor bypass, and NVIDIA vsync behavior all
move timing. Pin distro/driver/session type per rig, record it with every measurement, and
re-run V1 after any change. OLED task displays additionally need luminance/persistence QA.
**Screen sharing is part of this risk:** VNC/RDP/capture stacks hook the graphics pipeline
on the machine whose whole job is frame-accurate presentation. Remote work uses a remote
*console* (ZMQ telemetry), not remote pixels; remote desktop stays off during recording,
and the flip patch will show it if someone forgets.

**P5 — SpikeGLX gap.** The unmeasured regime (cross-machine, Python) is exactly where naive
designs land. Design pins the fetch client to the acquisition PC (C++, loopback), ships
features not raw data, and keeps the Open Ephys + Falcon path (published 9.241 ms median,
384 ch) as the fallback and cross-check.

**P6 — Tracker stalls.** ~2% of OpenIrisDPI frames >= 10 ms (max ~50 ms) on the authors'
hardware. **Raised to High** because the experimental program depends on saccade-triggered
display changes landing inside saccadic suppression — a budget tighter than anything else
in this project, and one a 50 ms stall destroys outright. Fixation logic uses hold-last with
a staleness ceiling and grace periods; aborts require corroboration. V3 runs on our hardware
before window parameters are frozen, and its result may force a design change rather than a
parameter change.

**P7 — Sync debt.** Retrofit synchronization is how multi-machine rigs quietly ruin datasets.
`wl-sync` owns the fabric; our obligation is to feed it correctly and to delete our own
duplicate concepts rather than maintain a second definition (S3).

**P8 — Drift and bus factor.** Conventions in CLAUDE.md; CI green as merge condition; ADRs
so decisions survive personnel and sessions; welfare-critical modules require human review.
Boring technology choices are a deliberate mitigation here. **Registry over README:** a
package's lifecycle is what `wl-orchestrator` says it is, not what that repo's own README
says — `wl-elab` reads as the live ELN in its README and is `deprecated` in the registry.

**P10 — Hardware before drivers.** **Raised to High.** NI-DAQmx's supported distributions do
not include Fedora, the lab's standard; the task PC therefore deviates to Ubuntu 24.04 LTS,
and `PCIe-6343`-on-Linux remains **UNVERIFIED** until a card runs on a bench. Cards are
ordered on lead time regardless (the Windows side is unambiguously supported and D3 needs
it), but commissioning does not proceed on an assumption.

**P12 — Protecting the science, without a bridge.** D1 removed the MonkeyLogic bridge that
was this risk's mitigation, and `wl-mllib` is empty, so the bridge was never real: switching
to it would have meant writing a task library from scratch under pressure. The replacement
mitigation is staged exposure rather than a fallback system:

1. No animal session on a build that has not passed an overnight synthetic soak (V5).
2. The training ladder runs first and is the lowest-stakes possible proving ground — a
   failure costs a training day, not a recording.
3. Each capability is gated on its own measurement before any experiment depends on it.
4. D3 keeps the swap *possible* — the rig contract is controller-agnostic and the task PC
   dual-boots — so a catastrophic outcome is recoverable in weeks rather than being
   foreclosed. It is insurance, not a plan.

**P14 — RHX backpressure.** The RHX user guide (read 2026-08-31): "It is important that the
client application reads the data output quickly, otherwise the memory allocated for data
output will fill up and halt data acquisition." A slow closed-loop client does not drop
samples; it stops the recording. This is a failure mode with no equivalent elsewhere in the
system — **our control software can destroy the experiment it is controlling.** Mitigation:
a dedicated bounded reader that does not share the Python GIL, a hard drop-oldest policy,
deliberately budgeted channel counts and TCP output rates, and "the client fell behind" as
a loud alarm rather than a silent degradation. Headroom is measured under closed-loop load
(V8) before any session depends on it.

**P15 — Model-authored task correctness.** Tasks are primarily written by a model under
experimenter direction (D4), which makes P1 and P8 apply to task code: generated tasks are
syntactically clean, plausibly structured, and confidently wrong in ways that read well.
The human's role is reviewer, so the mitigation is to make review possible rather than to
ask for more care: within-trial logic is inspectable data, event codes are allocated in
`wl-mllib` and refused if unregistered, welfare parameters are unreachable from the task
file, every task is drivable in keyboard/mouse demo mode in seconds, and thousands of
simulated trials assert termination, reachability and outcome coverage before an animal
sees it. **A task nobody could review from a diagram and a simulation run has failed the
design, not the reviewer.**

**P16 — Parameter change as silent discontinuity.** Live parameter editing is a stated
must-have and is also the most likely way this system quietly damages a dataset: a change
made at trial 300 is invisible at analysis time unless it was recorded. Mitigation: every
trial carries a **complete** resolved parameter snapshot rather than a pointer to "the
config"; every change emits an event code so the discontinuity is on the recording clock;
changes are staged and applied atomically in the ITI so no trial runs on a half-applied
set; and every write records its origin and actor through one validated path.

**P17 — Fluid accounting floor.** The panel's manual reward button bypasses our software
entirely — debounced, monostabled, OR'd with our commanded line, recorded as *delivered*.
Our commanded total is therefore a lower bound on fluid delivered. Welfare accounting
reconciles against the sync box's record of the delivered line. Recording commanded and
delivered separately is what makes a hand-delivered reward countable at all, and training
days are exactly when an unlogged one would become a silent confound.
