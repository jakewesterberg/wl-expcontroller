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
| **P18** | **Correct graph, wrong experiment** | **High** | Gates must inspect different *objects*, not the same one three ways — see expanded note |
| **P19** | **A colour nobody measured reaches a methods section** | **High** | Device-independent colour only; refuse it without a photometer calibration naming its observer |
| **P20** | **Generated structure nobody reads** | Medium | Anything a parameter generates — array items, their windows — needs a check, because no author will ever look at it |

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

**P4a — Display timing measured off-rig is not evidence.** A display spike on a macOS
laptop showed a thin glfw stack at 36% long frames against PsychoPy's 1.8%, which reads
as a verdict. It was not: the same machine, the same measurement, and the difference was
a missing pipeline drain in the spike's own loop. Fullscreen made it look worse still --
221 Hz on a 120 Hz panel, the signature of vsync not being enforced rather than of speed.
**No display stack is judged anywhere but a rig, under V1, with a photodiode.** Numbers
from a development machine go under `docs/measurements/dev-machine/` and are labelled as
deciding nothing.

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
Boring technology choices are a deliberate mitigation here.

**Sharpened 2026-08-31, and the previous mitigation was inadequate.** People arrive with or
before the animals in January, and **a tech or student runs the rigs day to day rather than the
PI**. Every mitigation above protects *developers*; none of them help an operator. So:

- **Operator documentation is an M1 deliverable**, not a later one. Not a design doc — a "how to
  run a session" doc, written for someone who has never read a spec.
- **Every operator-facing string is written as though a stranger reads it.** Preflight failures
  name the fix, abort reasons are self-explanatory, and an error that requires knowing the design
  to interpret is a bug. This costs nothing now and cannot be retrofitted cheaply.
- **The acceptance test moves earlier.** Roadmap M5's gate — a naive operator running a full
  training session without a terminal — is the right test, and with people arriving in January it
  cannot wait until M5 to be attempted for the first time. **Registry over README:** a
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


**P18 — Correct graph, wrong experiment.** For a long stretch every load-time check
inspected the same object: unreachable-state, unbounded-wait, no-outcome-path and
shadowing are four views of the transition graph. Adding more of them raised the
count without narrowing the residual class, and the residual class was tasks whose
graph is right and whose *experiment* is wrong — nothing modelled what was on the
screen, when, or for how long. The first reference task carried one: `Show` was
scoped to its state, so the fixation point was removed at the exact frame the animal
was asked to hold it. It read correctly, passed all ten checks, and simulated 2,000
trials clean.

The mitigation is not more checks, it is checks over **more objects**: the display
timeline, the photometry, the parameter space, the eye. And it applies to the
simulator equally — a subject that responds to the transition graph alone reproduces
every defect of this kind perfectly, which is why the simulated animal now sees the
screen and will not look at a stimulus that is not there.

**The general form: ask what a gate is looking at, not how many gates there are.**

**P19 — A colour nobody measured.** RGB is a set of instructions to one panel, so a
colour written in a task file is a different stimulus on every monitor and describes
nothing reproducible in a methods section. The specific damage is quiet: a monitor
asked for a colour outside its gamut clips, and a clipped colour has neither the
requested chromaticity nor the requested luminance — so an isoluminant pair stops
being isoluminant and a chromatic experiment's control condition becomes a luminance
manipulation, in a task that runs and looks convincing. Mitigation: colour is
specified in CIE xyY or DKL cone contrast, checked against a measured `Calibration`,
and refused without one. The calibration must name **whose luminous efficiency** it
was measured against, because a human V(lambda) makes a stimulus that is isoluminant
for nobody in the room.

*As of 2026-09-01 no calibration for our panels exists.* Chromatic tasks will not
load until a photometer measurement is committed under `docs/measurements/`.

**P20 — Generated structure nobody reads.** The point of `Array` and `ItemWindows` is
that set size is a value, so the individual items and their windows are never written
down and never read. That removes the author's eye from exactly the structure most
likely to be wrong: `tasks/visual_search.py` shipped allowing twelve items on a 3°
ring with 4° windows — adjacent centres 1.55° apart with 8° of summed window, so a
saccade to one distractor would have been scored against another. It passed every
check that existed when it was committed, and the defect was found only when the
crowding check was written a day later.

Mitigation: anything a parameter generates gets a check reasoning over the declared
ranges, not the current values. The rule generalises — **when a feature exists to
stop a human writing something out, it also stops a human reviewing it.**
