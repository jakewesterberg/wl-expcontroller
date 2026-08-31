# wl-expcontroller — controller architecture design

- **Status:** proposed, for PI review. Supersedes the topology and sequencing in
  `docs/design/architecture.md` and the bridge strategy in ADR-0001.
- **Date:** 2026-08-31
- **Deciders:** Jake (PI)

Every dated external claim below was read from the cited primary source on the date
given. Numbers that have not been measured on our hardware are labeled **budget** or
**UNVERIFIED** and may not be cited as facts about this system (CLAUDE.md; pitfalls P1).

---

## 1. What changed, and why this document exists

The prior research phase (2026-08-30) surveyed the software landscape and sketched an
architecture without reading the rest of the `wl-*` family. Reading it changes the
design substantially: much of what that sketch proposed to build already exists in
`wl-sync`, the rig's electrical interface is already designed in copper, and three
required subsystems were missing entirely.

Eleven decisions were taken in the 2026-08-31 design session. They are recorded in §2;
the rest of this document works out their consequences.

### 1.1 Facts from the rest of the lab stack

| Fact | Source | Consequence here |
|---|---|---|
| `wl-sync` owns session identity, the barcode codec, the log format, and event-code routing | `wl-sync/wl.yaml` `publishes:` | We do not mint sync or session identity. We consume them. |
| The breakout PCB is a designed 2U hub between task PC, sync box, recording NI card, and Intan RHS | `wl-sync/hardware/README.md` | The rig I/O contract is fixed in copper; §3 restates it. |
| Task PC card is **NI PCIe-6343**; recording card is **PXIe-6353**; 12–13 week lead time | `wl-sync` breakout spec §9.3 | Procurement is on the critical path (§13). |
| Reward reaches `wl-juicer` through the board's OR gate, not from us directly | `wl-juicer/README.md`; breakout spec §3.1 | We command; the board delivers; the sync box records. §7.4. |
| `wl-mllib` holds no code; the behavioral stack is explicitly unchosen; no event code is allocated | `wl-mllib/wl.yaml` | The MonkeyLogic "bridge" of ADR-0001 does not exist. The event vocabulary is ours to author jointly. |
| The lab opens **January 2027**; no rig, no data, no lab before then | `wl-preproc/docs/CHECKPOINT.md` | Everything is built before it can be validated on real hardware. |
| `wl-works` hosts the ELN; `wl-elab` is `lifecycle: deprecated` | `wl-orchestrator/registry/packages/*.yaml` | ELN integration targets `wl-works`. §12.3. |
| wl-works binds only to WireGuard; lab machines have no route in, and `wl-preproc` enforces "never initiates a connection" with an AST guardrail | `wl-preproc/docs/pending-wl-works-amendments.md` §11.2 | A rig cannot push to the ELN. Integration is pull-based. §12.3. |
| Lab Linux standard is Fedora | `wl-stack/README.md` | Conflicts with NI-DAQmx's supported distributions. §13.1. |

### 1.2 What the prior sketch got wrong

1. `taskd` minting its own sync barcode — `wl-sync` owns this.
2. `taskd` driving the reward TTL directly — reward transits the board's OR gate.
3. "3–4 rigs" — the board spec budgets cabling for **two** rigs (five boards fabbed,
   so headroom exists, but v1 is two).
4. A single photodiode "patch" — there are **two**, with fixed and distinct roles, and
   both return to us as digital comparator edges (§3.2).
5. Stereoscopy, Intan RHS/RHX, audio, joystick, touchscreen, microphone, accelerometer
   and behavior cameras: absent entirely. All but touchscreen are in copper.

---

## 2. Decisions taken (2026-08-31)

| # | Decision | Displaces |
|---|---|---|
| D1 | **wl-expcontroller is the day-one stack.** MonkeyLogic is never deployed as the working controller. | ADR-0001's bridge strategy; pitfalls P12's mitigation |
| D2 | **v1 = the training ladder plus a first recording task**, 2D and monocular. Stereo and the neural closed loop follow, and must not be architecturally precluded. | roadmap M1–M6 sequencing |
| D3 | **Interchangeability with MonkeyLogic is at the rig-contract and data layer only** — controller-agnostic event lines, reward path, analog inputs, photodiode patches and event vocabulary, owned by `wl-sync` and `wl-mllib`. No shared task language. A dual-boot task PC buys the swap. | ADR-0001 |
| D4 | **Tasks are primarily model-authored** under experimenter direction, so the task API optimizes for verifiability, simulatability and review-by-diagram rather than for authoring ergonomics. | — |
| D5 | **Within-trial logic is declarative data; between-trial logic is ordinary Python.** Representation is Python declarations (dataclass/pydantic), plain-text and IDE-readable. | — |
| D6 | **Split-screen mirror stereoscope on one panel.** Two viewports on one framebuffer, cyclopean coordinates, disparity as a stimulus property; the monocular v1 task is the zero-disparity case of the stereo path. | architecture.md's display section |
| D7 | **SpikeGLX and Intan both record; either may gate the loop; Intan always stimulates.** Two ingest paths behind one feature interface. | architecture.md's single-source neural plane |
| D8 | **Microstimulation in three tiers** — epoch-triggered, gaze-triggered, neural-triggered. Tiers 1 and 2 are v1, so stim welfare interlocks are v1 work. | roadmap M6 |
| D9 | **Live parameter control is a must-have.** Values and structure both, applied atomically at trial boundaries, with a full per-trial parameter snapshot, through one validated write path. | — |
| D10 | **`taskd` and the console are separate processes, always.** The hot loop never renders a plot, serves a request, or holds a UI. The console may run on another machine. | — |
| D11 | **Lab integration is pull-based**, reusing `wl-preproc`'s existing lab-host protocol rather than inventing a second one. | — |

---

## 3. The rig, as it actually is

### 3.1 Topology

```
   OpenIris PC (Windows)          Task PC (Linux)              Acquisition PC (Windows)
   OpenIris + OpenIrisDPI         taskd + console              SpikeGLX <- Neuropixels
   500 Hz binocular dDPI          NI PCIe-6343                 NI PXIe-6353 (nidq)
        |         \                    |                             ^
        | UDP:9003 \ ACCES DAC         | MDR68 x2                    |
        | (control) \ (recorded copy)  |                             |
        v            v                 v                             |
   +--------------- wl-sync breakout board (2U) ----------------------+
   |  conditioning, level shifting, isolation, mux, comparators        |
   +---+--------------------+---------------------+------------------+
       |                    |                     |
       v                    v                     v
   sync box (Pi/CM5)    Intan RHS            wl-juicer / wl-shook /
   barcode, session     record + stimulate   cameras / speakers / mic
   identity, log
```

The sync box defines session time. Every scientifically meaningful event becomes an
edge or word recorded in at least one acquisition stream; network messages are never
the timing record.

### 3.2 The task PC's interface (from the breakout spec §3, §9.2)

**Digital out — 19 lines.** 16 event-code data bits on **P0.8–P0.23** (not zero-based),
event strobe, reward commanded, stim trigger.

**Digital in — 4 lines.**

| Line | Meaning | Why we care |
|---|---|---|
| `PD1_COMP` | Task patch comparator — stimulus onset at the display surface | Photodiode-gated state progression (§5.4); onset verification |
| `PD2_COMP` | Flip patch comparator — alternates every refresh, a frame clock | Live dropped-frame detection at the display surface (§11.4) |
| `ACC` motion trigger | Chair motion energy over threshold, from `wl-shook` | Gates task progression |
| RHS stim output | Intan actually stimulated | Verifying delivery against intent (§10.4) |

**Analog in — 9 channels.** Eye X/Y both eyes (4, from the ACCES DAC), joystick X/Y (2),
misc BNC (3, currently unassigned — §9.3 proposes one for audio verification).

**Not present in copper:** touchscreen, audio output. Both are USB/host-side (§8.4, §9.4).

### 3.3 What the two photodiode patches change

Both reach us as digital edges, not only as analog waveforms recorded downstream. That
turns two offline checks into online guarantees:

- **Onset**: a state can wait for physical confirmation that a stimulus reached the
  display before advancing (§5.4). A *missing* edge is then a detectable fault during
  the session rather than a discovery months later.
- **Frames**: drops are detected at the display surface, catching post-GPU drops that a
  vsync tap structurally cannot (breakout spec §3.1 makes this argument explicitly).

Both patches must sit **outside both eyes' viewports** on the split screen (§8.2), or
the flip patch becomes a flickering distractor in one eye's field.

---

## 4. Components

| Component | Host | Language | Owns | Simulator |
|---|---|---|---|---|
| `taskd` | Task PC | Python | Trial execution, display, gaze logic, DIO, session record | Full headless run against replayed and synthetic inputs |
| `console` | Any machine | Python | Experimenter UI, live plots, parameter writes, preflight, test screens | Talks ZMQ to `taskd`; runs against a fake `taskd` |
| `neurofeatd` | Acquisition PC | C++ | SpikeGLX `fetchLatest` on the filtered AP stream -> MUA features -> ZMQ | Synthetic feature publisher |
| `rhxfeatd` | Intan host | C++ or Rust | RHX Spike Output socket -> features -> ZMQ; bounded reader | Synthetic spike-raster publisher |
| `labhost` | Task PC | Python | The pull-based endpoint wl-works polls (§12.3) | Contract tests against the published schema |

`taskd` and `console` are separate processes under all conditions (D10). Three separate
requirements depend on it: plots off the hot path, the control API, and remote access.

**Welfare-critical modules requiring human review** (CLAUDE.md): reward scheduling and
limits, fluid and session-duration accounting, token-to-fluid conversion, stimulation
parameter bounds and gating, and the bounded-config loader that enforces all of them.

---

## 5. The task model

### 5.1 The split

**Within a trial: declarative data.** A trial is a set of states with guarded
transitions, entry and exit actions, and an outcome code. `taskd` executes it; the task
does not own the frame loop. This is where errors cost animal welfare and timing
integrity, so it is the part that is statically checkable, exhaustively simulatable,
renderable as a diagram, and hot-path-safe by construction.

**Between trials: ordinary Python.** Condition selection, block progression, staircases,
adaptive parameter updates. Outside the frame budget, errors are observable and
recoverable, and the freedom costs nothing.

### 5.2 Why, given D4

With a model as the primary author, the human's role moves from writing to reviewing,
and the failure mode moves with it: generated code is syntactically clean, plausibly
structured, and confidently wrong in ways that read well. That is pitfalls P1 and P8
aimed at task code. The declarative layer answers it four ways — mechanical checking,
simulation before an animal sees it, review of a rendered diagram rather than source,
and a small closed vocabulary that grounds generation.

The counterargument is real and shaped the representation: **models write mainstream
Python far better than a bespoke DSL with no training data.** Hence D5 — the declarative
layer is Python declarations, not a new text language. That also satisfies the
requirement that tasks be readable and editable in an ordinary IDE with autocomplete,
type checking and jump-to-definition, and it keeps tasks plain-text and diffable.

### 5.3 Escape hatches

**Settled by S1's bake-off (2026-08-31).** The within-trial layer stays pure data; behavior the vocabulary lacks is
declared by name and its implementation lives in the framework's tested, reviewed source
rather than in the task file. Gaze-contingent rendering and neural-threshold gating are
*not* escape hatches — they are core lab science with many consumers and belong in the
vocabulary (P2's "second concrete use" test is already met).

### 5.4 State primitives that are not obvious

- `WaitFor(PhotodiodeEdge)` — progression gated on physical stimulus onset (§3.3).
  Requires a low-latency digital-input path; change detection on P0 rather than polling.
  **DI read latency is unmeasured (V2b).**
- `WaitFor(ChairStill)` — the `wl-shook` motion trigger gating progression.
- `WaitFor(SaccadeOnset)` / `WaitFor(SaccadeTo(target))` — online saccade detection is a
  versioned, tested component with logged parameters, not per-task code (§9.2).
- Unbounded epochs — free viewing of natural images is a first-class case, not an escape
  hatch. States may have no timeout where declared deliberately.

### 5.5 Session structure

A session is a sequence of **blocks** and **interludes**, declared as data.

- A **block** declares its condition set, parameter overrides, a length rule (fixed N, or
  criterion-based such as "80% correct over the last 20 completed trials"), and its
  transition. Mini-blocks of held stimulus parameters are the common case.
- An **interlude** is a sub-task the session enters and leaves without ending — eye
  calibration being the motivating case (§9.3).
- The **trial scheduler** owns condition selection, block progression and the counters.
  Aborted trials are re-queueable under a declared policy. Counters distinguish
  **attempted / completed / correct** per condition, and the console displays
  **achieved against target**, because the question at the rig is never "how many have I
  run" but "how many more do I need."

Criterion-based transitions consume the same running statistics the live plots use,
computed once.

### 5.6 Cross-trial state

Token economies force this: accumulated tokens are persistent state that survives trial
boundaries *and* a persistent display layer the per-trial scene does not reset. So:

- A **session-scoped state store**, recorded in every per-trial snapshot and in the event
  stream.
- A **persistent display layer** distinct from per-trial scenes.
- Token-to-fluid conversion is welfare-critical and lives under the bounded config
  (§7.3), not in the task file. Token loss on error is expressible.

---

## 6. Event vocabulary and hardware truth

**Corrected 2026-08-31 by S2.** This section originally said nothing was allocated
anywhere. In fact `wl-preproc/wl_preproc/contracts/events.py` is a **frozen interface**
carrying the range allocation, the markers, a task-type namespace, four escapes with payload
framing, an XOR checksum and offset-binary degree encoding. `wl-mllib`'s manifest claimed the
whole vocabulary and was wrong; ADR-0007 splits ownership on **decodability versus meaning**
— framing, escapes and `Marker` 1–255 are `wl-preproc`'s; `TaskEvent` 256–4095,
`TaskTypeCode` 100+ and 4096–32767 are `wl-mllib`'s. See
`docs/superpowers/specs/2026-08-31-S2-event-vocabulary-design.md`.

Requirements:

1. Codes are **allocated, never invented in a task** — in `wl-mllib` for the ranges it
   owns, in `wl-preproc` for the frozen protocol layer. Validation refuses an unregistered
   code **at load time**, not at run time. This is the single cheapest guardrail against
   model-authored task files. We write no second decoder: conformance is tested by
   round-tripping our streams through `wl-preproc`'s own `decode_stream`.
2. 16 data bits plus strobe on P0.8–P0.23. Word semantics, strobe width and settling time
   are part of the contract, verified on the event-path mule before the full board exists
   (breakout spec §10.3).
3. Every trial event gets both a strobed word and a JSONL record carrying the word, the
   frame index, and the monotonic timestamp.
4. Touch events have **no hardware line**; they reach the recording clock only as strobed
   event codes (§8.4). This is a real asymmetry and must be stated wherever touch data is
   analyzed.
5. **Intan receives the strobe only** — its 16 digital inputs cannot carry 16 data lines plus
   strobe plus barcode. So analysis in Intan's timebase is blind to event identity until
   barcode alignment has run, and a real-time client on the Intan host cannot condition on
   event identity read off that machine's inputs: `taskd` must tell the neural plane the trial
   state over the message bus. This constrains S7 and was not in the original design.

---

## 7. Parameters, provenance, and live control

### 7.1 The parameter model

Each task **declares** its parameter space: name, type, unit, valid range, and whether it
is live-editable. From that one declaration the system derives validation, the console's
control widgets, the saved record, and the ELN summary — no per-task UI code, which is
what makes it work for model-authored tasks.

### 7.2 Application and provenance

- **Staged, then applied atomically in the ITI.** Never mid-trial. If regenerating derived
  stimuli overruns the ITI, **the ITI extends; frames are never dropped.**
- **Every trial records a complete parameter snapshot**, not a pointer to "the config." A
  mid-session change is otherwise an undocumented discontinuity that surfaces during
  analysis months later. This is the single most likely way this feature does damage
(pitfalls **P16**).
- Changes emit an event code, so the discontinuity is visible on the recording clock.
- **One validated write path**, whatever the origin — console, external control API, or
  (if ever enabled) the task itself. Origin and actor are recorded. In-task writes are
  off by default.

| Tier | Example | Live? |
|---|---|---|
| Values | eccentricity, size, contrast, durations, reward volume, stim amplitude | Yes |
| Structure | six items to eight, active conditions, condition weights, block composition | Yes — regenerated in the ITI |
| Logic | new states, new stimulus types, changed trial flow | No — explicit task reload at a trial boundary, logged as a discontinuity |

### 7.3 The bounded config

Welfare-critical parameters are **live-editable by a human through the console, bounded by
ceilings in the rig/subject config that the console cannot exceed and the task cannot
touch.** Covers reward volume and rate, daily fluid budget, session duration, token
conversion, and every stimulation bound in §10.4.

Precedence: **rig defaults -> subject defaults -> task defaults -> session overrides ->
live edits**, with the bounded config as a ceiling over all of it. The resolved set is
snapshotted per trial.

### 7.4 Fluid accounting has a floor, not a total

The panel's manual reward button bypasses our software entirely: it is debounced,
monostabled to a fixed duration, OR'd with our commanded line, and recorded as
*delivered* (breakout spec §3.1). A console "give reward" button commands through the
normal path so it appears as commanded **and** delivered; a panel press appears as
delivered-without-commanded.

**Therefore our fluid total is a lower bound** (pitfalls **P17**). Real accounting
reconciles against the sync box's record of the delivered line. Stating this now prevents
a silent welfare error later.

### 7.5 Remote and programmatic access

The console may run on another machine, connecting to `taskd` over ZMQ — telemetry over
the wire, not pixels. An external control API reaches the same validated write path,
enabling online adaptive procedures as separate processes.

Both need: bearer-token authentication, a rate limit, and a **write-arbitration rule**
for concurrent console and API writers.

**Screen sharing on the task PC is a timing hazard.** VNC/RDP/capture stacks hook the
graphics pipeline on the machine whose whole job is frame-accurate presentation — P4
territory. Remote desktop stays available for rig-local work but should be off during
recording; the flip patch will show it if someone forgets.

---

## 8. Stimulus presentation

### 8.1 Display engine

PsychoPy as a library behind our own `DisplayAdapter` (ADR-0002, unchanged). Photodiode-
measured on Ubuntu: 0.34 ms onset variability, 4.71 ms constant onset lag
([Bridges et al. 2020](https://peerj.com/articles/9414/)) — **their measurement, not
ours**; V1 measures ours.

### 8.2 Stereo as viewports

Split-screen mirror stereoscope, one panel, each eye viewing one half through redirection
mirrors. Consequences:

- **Two viewports on one framebuffer.** One window, one flip, one refresh clock, no
  genlock. Stereo is not a second pipeline.
- **Cyclopean coordinates with disparity as a stimulus property.** The monocular v1 task
  is the zero-disparity case of the same code path, so stereo costs almost nothing later.
- **Per-eye viewport geometry** — its own center, its own folded optical path length, its
  own deg/pixel. Path lengths are **measured, not derived** from the monitor's physical
  distance.
- **Mirror angles set vergence**, so alignment is a calibrated rig parameter with a real
  alignment procedure (Nonius/vernier), not an assumed symmetry.
- **Per-eye resolution and aspect are halved horizontally**, which constrains eccentricity
  and argues for horizontal resolution when selecting the panel.
- **Photodiode patches sit outside both viewports** (§3.3).
- **Panel uniformity becomes an interocular difference.** Left-right luminance or color
  nonuniformity across a split panel is by construction an interocular mismatch, which
  biases binocular combination. Photometering both halves separately, and measuring each
  eye's folded path length rather than deriving it, is protocol **V9**. On a two-display
  stereoscope this would present as "the displays don't match"; here it hides inside one
  panel that looks fine.

### 8.3 Static and moving stimuli

Motion is a **deterministic function of parameters, seed and frame index** — never a
logged trajectory. Offline reconstruction is then exact and nearly free, the hot path
stays allocation-free, and random-dot kinematograms reproduce by the same mechanism.
Assets are preloaded before an epoch begins; no disk I/O once it starts.

### 8.4 Touchscreen

Not in copper, and geometrically at odds with the stereoscope — an animal cannot reach a
display it views through mirrors. Touch implies a distinct physical configuration, and
touch events reach the recording clock only as strobed event codes (§6). **Open item:
whether touch is a second panel, a rig mode with the stereoscope out of path, or deferred.**

### 8.5 Audio

Three roles, none present in the prior architecture: auditory stimulus presentation,
performance feedback to the animal, and vocalization monitoring. Only the third is handled
(`A_MIC` to NI). Audio onset timing on Linux has worse jitter and less visibility than
video, so:

- The audio output is **electrically tapped into one of the three unassigned misc BNC
  inputs**, giving sound onset on the NI clock without room-acoustics smearing. This is a
  proposed assignment against `wl-sync` breakout spec open item #6/#7 and needs their
  agreement.
- Audio onset gets its own measurement protocol (**V7**, §14).

---

## 9. Eye tracking, calibration, and gaze

### 9.1 Which path controls

**UDP (port 9003) is the control path; the ACCES analog copy is a recorded channel.**
Settled by the science, not by preference: saccade-triggered display changes must land
inside saccadic suppression to be invisible, and the analog path adds ~3–4 ms (OpenIrisDPI
paper, via `docs/research/openiris-dpi.md`) on top of being capped at ~2 kHz delivered
bandwidth by the ACCES DAC's 4 kHz conversion rate (breakout spec §12 item 10). The OpenIrisDPI paper states the analog signal "may limit the use of this signal for
gaze-contingent applications."

The analog copy earns its channels by making the eye PC's software+USB lag measurable by
cross-correlation per session.

We also drive OpenIris's remote API (`StartRecording`, `RecordEvent`) so the eye PC's own
authoritative file is session-aligned by construction, not only by post-hoc barcode.

### 9.2 Online saccade detection

A versioned, tested component with logged parameters — not per-task code, because its
parameters affect results. Tested against replayed OpenIrisDPI data.

**The dominant risk to this whole class of experiment is tracker stalls.** The
OpenIrisDPI paper reports frame processing of 1.1 ± 0.1 ms median but **~2% of frames
>= 10 ms (max ~50 ms)** on the authors' hardware. Gaze logic uses hold-last with a
staleness ceiling and grace periods; a trial abort requires corroboration. Our own stall
distribution is measured (V3) before window parameters are frozen.

### 9.3 The gaze mapping is a versioned object

Recentering, automatic drift correction, the calibration button and mid-pause
recalibration are one concept, not four: **the mapping changes during a session.**

- The mapping is session-scoped and versioned, with a change log.
- **Every trial cites the mapping version in force.**
- Calibration runs as an interlude (§5.5).
- **Automatic drift correction never overwrites the raw signal.** Raw and corrected are
  both recorded, every adjustment is logged, and the correction is reversible offline. A
  silent correction is indistinguishable from an artifact.
- Toggling drift correction is a logged parameter change like any other.

### 9.4 Other behavioral inputs

Joystick X/Y arrive as analog on the task PC (calibration, deadzone, hold/release
detection are ours). Lever/button inputs use spare digital lines where available.

---

## 10. Neural plane and stimulation

### 10.1 Two sources, one interface

Both systems record; either may gate the loop; **Intan always stimulates.**

| | Local-activity gating | Distant-area gating |
|---|---|---|
| Source | Intan RHX **Spike Output** socket | SpikeGLX `fetchLatest`, filtered AP stream (`js = -2`) |
| Client | `rhxfeatd` on the Intan host | `neurofeatd` on the acquisition PC, C++, loopback |
| Effort | Small — RHX already detects the spikes | Large — we write the feature extractor |
| Artifact | Severe (same amplifier); mitigated by RHS amp-settle plus our blanking | Absent |
| Latency pressure | Highest — targeting a window in local activity | Lower — gating on an activity level |

Both publish the same schema-versioned feature message over ZMQ (msgpack), consumed
latest-wins. A `FeatureSource` interface with two implementations; the task selects at
config time.

### 10.2 Verified RHX facts (user guide, read 2026-08-31)

- **Two data output sockets.** Waveform data on the Waveform Output socket; **spike raster
  event data on a separate Spike Output socket.** RHX already performs GPU-accelerated
  band-splitting and threshold spike detection, so the local path can consume events
  rather than traces.
- **Stimulation is hardware-triggerable.** "Any digital input or analog input on the main
  controller or optional I/O Expander may be used to trigger a stimulation sequence,"
  edge- or level-triggered, active high or low. Analog inputs trigger at 1.65 V.
  **No software sits in the trigger path.**
- **Stim parameters are settable over the TCP command interface** — trigger, shape,
  magnitude, duration, per channel.
- **Amp-settle is built into RHS headstages**, engaging around the pulse with configurable
  pre/post duration; the guide suggests ~1 ms post as a starting point. RHD systems
  additionally accept a digital blanking line at 4–5 sample periods of latency.
- **No latency figure is published.** The guide names the sources (USB to host, TCP to
  client) and stops. This is a V4 measurement, not a citation.

### 10.3 The RHX backpressure hazard (new pitfall P14)

> "It is important that the client application reads the data output quickly, otherwise
> the memory allocated for data output will fill up and **halt data acquisition**."

A slow closed-loop client does not drop samples — **it stops the recording.** Our control
software can destroy the experiment it is controlling. Mitigations: a dedicated bounded
reader not sharing the Python GIL; a hard drop-oldest policy; deliberate budgeting of
channel count and TCP output rate; and "the client fell behind" as a loud alarm, never a
silent degradation.

### 10.4 Stimulation: three tiers and their bounds

| Tier | Trigger | Requires | Milestone |
|---|---|---|---|
| 1 | Trial epoch (time-based) | DIO only | v1 |
| 2 | Eye movement or position | DIO + eye path | v1 |
| 3 | Measured neural activity | DIO + eye + real-time neural plane | post-v1 |

Tiers 1 and 2 are reachable in v1, so **stimulation welfare interlocks are v1 work**, not
deferred to the last milestone as the current roadmap has it.

Parameter handling:

- Tasks declare stim parameters; the controller pushes them over TCP at **safe points
  only** — session start, block boundaries, ITI. Never mid-trial: a TCP round trip has no
  bound. Per-trial-varying stim follows §7.2's rule (extend the ITI, never drop a frame).
- **Read back after writing.** Query and confirm before any trial can trigger.
- **Bounded by the rig/subject config**: amplitude, pulse width, frequency, train duration,
  duty cycle, charge per phase, charge density — ceilings the task cannot exceed and the
  console cannot override.
- **Charge balance is verified, not assumed.**
- **Delivery is counted against the RHS stim-output line**, not against our intent. Session
  stim limits are enforced against deliveries actually observed — the difference between a
  limit and a hope.
- Refractory enforcement and a runaway-loop detector are mandatory for tier 3.

`Stimulator` is an interface with an RHS implementation; "stimulator(s)" plural costs
nothing now and does not invite a framework (P2).

---

## 11. Operations and interface

Not an appendix. Three of these are the verification loop that makes D4 safe.

### 11.1 Preflight check

One action, one red/green list, before any session: tracker streaming, DAQ lines present,
sync box up, SpikeGLX/RHX running and armed, display at expected refresh, photodiode
responding, reward pump primed, disk space, config diff against last session. Prevents
the two-hours-recorded-with-no-eye-data class of loss. **Highest operational priority.**

### 11.2 Demo mode and simulated sessions

- **Keyboard/mouse demo mode.** Any task drivable with the mouse standing in for gaze and
  keys for responses. This is how a human validates a generated task in thirty seconds.
- **Simulated sessions.** Replay of recorded eye data, plus synthetic behavior agents, to
  run thousands of trials and assert properties: termination, reachability, no dead
  states, outcome coverage, parameter ranges honored.

These have the same v1 status as the display module (D4).

### 11.3 Console

Launched by one action (a desktop launcher wrapping preflight; a physical start button
through the sync box's GPIO is feasible later). Provides: pause at trial boundary with the
console fully live, emergency stop distinct from pause, manual reward, live parameter
panel derived from the declaration, calibration and recentering controls, drift-correction
toggle, per-condition counters (achieved against target), abort-reason readout, fluid and
session accounting against the ceiling, test screens (including the per-eye alignment
target the split-screen optics require at every session start), and reward pump
calibration.

### 11.4 Live plots

Declared, not drawn. A task declares its **trial outcome schema** — outcome, RT, target
position, condition id, difficulty, with types and roles — and selects plots from a closed
vocabulary: running series, distribution, grouped comparison, **spatial map in visual-field
coordinates**, psychometric/staircase, outcome raster by abort reason, gaze overlay.

Rules:

1. Plots compute in the console process. **No plot, however expensive, can cost a frame.**
2. Bounded incremental accumulators; nothing re-fits the whole history per trial.
3. Plots derive from the **same trial records written to disk**. Divergent paths eventually
   disagree and you believe the wrong one at the worst moment.
4. The plot declaration is saved with the session, so the live view reproduces exactly
   offline and the same renderer serves finished sessions and cross-day comparisons.

**Boundary:** behavioral dynamics here; neural visualization in `wl-expviz`. The console
does not grow a second, worse version of it.

### 11.5 Refresh and dropped-frame monitoring

Hardware-truth via `PD2_COMP` at the display surface (§3.3), displayed live and logged per
trial — not the engine's own frame-interval accounting.

### 11.6 One declaration, four consumers

The trial outcome schema drives the live plots, the saved behavioral tables, the session
summary wl-works polls, and the event decoding `wl-mllib` publishes for `wl-preproc`.
Declaring it once and deriving all four is the difference between this being cheap and
this being four subsystems that drift.

---

## 12. Data outputs and lab integration

### 12.1 Boundaries

| Repo | Direction | Contract |
|---|---|---|
| `wl-sync` | we consume | session identity, barcode codec, log format, event-code routing |
| `wl-mllib` | we co-author | task event vocabulary; the task library itself |
| `wl-juicer` | we command | reward, through the board's OR gate |
| `wl-shook` | we consume | chair motion trigger gating progression |
| `wl-preproc` | we produce for | session directory, DONE markers, behavioral tables |
| `wl-works` | pull-based both ways | ELN metadata in, session summary out (§12.3) |
| `wl-expviz` | disjoint | neural visualization stays there |

### 12.2 Per-session outputs

JSONL trial/event log; behavioral tables (parquet); complete config snapshot including the
resolved parameter set, bounded config, gaze mapping versions, task version and code
version; the plot declaration; the parameter-change log; and — **not** a DONE marker. S3 §5: `wl-preproc`'s frozen path contract places us at
`<root>/<YYYY-MM-DD_NN>/expcontroller/`, deliberately outside `SYSTEMS`, so we write no marker
and never block session-complete detection. Raw neural data never touches the task PC.

### 12.3 wl-works and the ELN

The rig **cannot** push to the ELN (§1.1). Integration is pull-based and reuses
`wl-preproc`'s existing `docs/ops/lab-host-protocol.md` — bearer token, `GET /health`
verdict shape, published JSON Schemas — rather than inventing a second protocol.
**wl-works' own contract tests already run against a fake implementation of it.**

| Direction | Carries | Mechanism |
|---|---|---|
| ELN -> rig | subject, probe serials, `insertion_number`, `trajectory_id`, planned task, session intent | wl-works pushes a `prepare-session` action; three of six fields already exist in the bundle it sends `wl-preproc` |
| rig -> wl-works, live | session, subject, task, state, trial counts, fluid against ceiling, preflight result | **readings on `GET /health`**, polled at the protocol's 60 s cadence |
| rig -> ELN, finished | trials run, performance by condition, fluid delivered, task and config versions, parameter-change log, abort census | **a file in the session directory**, ingested by `wl-preproc`, reaching the ELN by the path that already exists |

The split is not arbitrary. `lab-host-protocol.md` declines a job-status endpoint and states
that when progress becomes observable "it will be as a **reading**, because readings are the
surface this host already publishes and wl.works already polls — not as a new endpoint"; it
separately declines result upload, "wl.works pulls; this host never pushes." Live state is a
reading; a finished summary is a result. Following both rules costs us no new endpoint and
no second copy of the session record free to drift from the ingested one. The trade is that
the ELN entry appears **after ingest rather than at session end**; if that latency matters,
the fix is prompt ingest, not a new endpoint.

**No welfare-affecting action is ever published through this protocol.** wl-works' permission
model is flat by design — publishing an action makes it available to every lab member. On a
preprocessing server the worst case is wasted compute; on a rig it is fluid, stimulation, or
a session started on an animal nobody is standing next to. Reward, stimulation, session start
and parameter changes require a person at the console.

**The cross-repo amendment is drafted at `docs/pending-wl-works-amendments.md`**, in the style
of `wl-preproc`'s open amendments, and is theirs to accept, amend or refuse. Another worker
owns that repository, including its remote. Note that it builds on a protocol document that
is itself proposed rather than agreed.

---

## 13. Hardware and platform

### 13.1 The Linux question, answered honestly

**NI-DAQmx 2026 Q2 supports RHEL 9.6/10.0, openSUSE 15.6/16.0, and Ubuntu 22.04/24.04 LTS.
Fedora is not on the list** ([NI Linux Device Drivers 2026 Q2 compatibility](https://www.ni.com/en/support/documentation/compatibility/26/ni-linux-device-drivers-2026-q2-compatibility.html),
read 2026-08-31). Kernel modules are DKMS-built against pinned kernels. NI's Linux readme
formally supports **LabVIEW and C/C++ (gcc)** only and points to a per-device compatibility
tool rather than listing hardware
([NI-DAQmx Linux readme](https://www.ni.com/pdf/manuals/ni-daqmx-linux-2023-q1.html),
read 2026-08-31). `nidaqmx-python` is a ctypes wrapper over that C API.

`wl-stack` standardizes the lab on Fedora. A Fedora task PC and a vendor-supported
NI-DAQmx install are mutually exclusive as stated, and Fedora's kernel churn is the wrong
environment for DKMS modules on a machine that must not break the week before a recording.
`wl-stack`'s own README already anticipates that `rig` will differ from a workstation.

**Recommendation:** the task PC runs **Ubuntu 24.04 LTS**, deviating from the workstation
standard deliberately and recorded as a rig-class decision. **PCIe-6343-on-Linux is
UNVERIFIED until a card runs on a bench** (P10). Dual-boot Windows satisfies D3.

### 13.2 Procurement

The board spec's own schedule note (§10.3) says to order the NI cards now: 12–13 week lead
time, independent of the board's pace, and the prototype lands late October to late
November with almost no slack for a respin. The purchase carries no software risk, since
the Windows side is unambiguously supported and D3 requires it anyway.

Display panel and refresh target are an S0 decision. With one panel and no genlock, a high
refresh rate is affordable; OLED requires luminance and persistence QA before visual-science
use (P4).

---

## 14. Latency budgets — requirements, not measurements

Every row is a **budget or an external number, never a claim about this system.**

| Path | Budget | Basis |
|---|---|---|
| Eye sample -> gaze decision | <= 1 display frame + staleness ceiling | OpenIrisDPI 1.1 ms median; ~2% >= 10 ms (paper) |
| Saccade onset -> display change | **inside saccadic suppression** | The binding constraint for gaze-contingent work; tighter than anything previously written down |
| Decision -> display change | next flip | engine flip-locked |
| Photodiode edge -> state transition | UNVERIFIED | New; NI DI change-detection latency (V2b) |
| Neural event -> feature at `taskd` (SpikeGLX) | ~2–5 ms | vendor loopback histogram plus one hop (V4) |
| Neural event -> feature at `taskd` (RHX) | UNVERIFIED | No published figure exists (V4) |
| Neural event -> stim TTL | ~3–6 ms | estimate (V4) |
| Audio command -> sound onset | UNVERIFIED | New (V7) |
| Fallback: Open Ephys + Falcon | ~9–13 ms | published plugin measurement |

New protocols added to `docs/validation.md`: **V2b** digital-input read latency, **V7**
audio onset timing and jitter, **V8** RHX backpressure headroom under closed-loop load, and
**V9** display geometry and per-half photometry for the split-screen stereoscope. **V4** is
widened to cover both neural paths, since only one of them has any published number at all.

---

## 15. Feature inventory, derived from the science

Derived from the stated experimental program, not from MonkeyLogic's manual — which is used
afterward only as a completeness check (P2).

**The program:** saccadic choice mostly, sometimes joystick and touchscreen, sometimes
passive fixation; gaze-contingent beyond fixation enforcement, with stimuli changing on eye
movements; both free viewing of natural images and discrete trials; both working-memory
delays and stimulus-locked designs; microstimulation during trial epochs, contingent on eye
position or movement, and contingent on measured neural activity; auditory stimuli and
auditory performance feedback, plus vocalization monitoring.

| Capability | Driven by | v1 |
|---|---|---|
| Fixation windows with stall-tolerant logic | all | Yes |
| Eye calibration, recentering, drift correction, mid-session recalibration | all | Yes |
| Online saccade detection and saccade-target windows | saccadic choice | Yes |
| Gaze-contingent stimulus update within a trial | gaze-contingent designs | Yes |
| Static and moving stimuli, deterministic from seed | moving stimuli | Yes |
| Natural-image sets, preloaded, with unbounded free-viewing epochs | free viewing | Yes |
| Working-memory delays with fixation enforcement | delay designs | Yes |
| Joystick input | joystick trials | Yes |
| Reward delivery, fluid and session accounting reconciled against the delivered line | all | Yes |
| Token economies with persistent cross-trial state and display layer | token designs | Yes |
| Blocks, mini-blocks, criterion-based transitions, per-condition counters | block designs | Yes |
| Live parameter control, values and structure | stated must-have | Yes |
| Photodiode-gated progression | timing integrity | Yes |
| Stimulation tiers 1 and 2 with welfare bounds | epoch and gaze-contingent stim | Yes |
| Auditory stimuli and performance feedback | auditory designs | Yes |
| Preflight, demo mode, simulated sessions, live plots, remote console | operations | Yes |
| Stereoscopic presentation with disparity | stereo designs | Path only |
| Stimulation tier 3 (neural-contingent) | closed-loop designs | No |
| Touchscreen | touch trials | Open (§8.4) |

---

## 16. Open questions

| # | Question | Owner | Blocks |
|---|---|---|---|
| 1 | ~~Escape-hatch strictness in the within-trial layer~~ **Answered in S1**: typed seam, novelty promoted into reviewed framework code, tasks using one are flagged. The bake-off's permissive version contained two defects the author did not notice | S1 | — |
| 2 | Touchscreen: second panel, rig mode, or deferred | PI | S4, S6 |
| 3 | ~~Display panel, refresh target, panel technology~~ **Answered in S0**: 32-inch-class 16:9 flat OLED, tandem model deferred to late 2026, bench panel bought now, 57 cm build distance, mode as rig config. Remaining: whether burn-in protection is defeatable, and whether GPU + panel can avoid DSC | S0 | panel purchase only |
| 4 | Photodiode patch placement against the real optics | PI + `wl-sync` | rig build |
| 5 | Misc BNC assignment for the audio verification tap | `wl-sync` agreement | S0 |
| 6 | ~~Event-code vocabulary allocation~~ **Largely answered in S2**: the protocol exists and is frozen; ADR-0007 splits ownership. Remaining: `wl-preproc` agreeing that `TaskEvent` 256–4095 moves, and accepting one new escape | `wl-preproc` | allocation, then S1 |
| 7 | wl-works amendment for the session-summary contract | drafted here, theirs to accept | S10 |
| 8 | MUA feature definition v0 (band, rectification, window, CAR) | PI, scientific | S7 |
| 9 | Console toolkit (PyQtGraph is the working recommendation) | S9 | S9 |
| 10 | Whether `rhxfeatd` and `neurofeatd` share an implementation | S7 | S7 |
| 11 | Restart-safety: can a session resume after a `taskd` crash | S8 | S8 |

---

## 17. What this changes in existing documents

| Document | Change |
|---|---|
| `docs/design/architecture.md` | Rewritten to match §3–§12 |
| `ADR-0001` | Bridge strategy superseded by D1/D3; consequences updated |
| `docs/pitfalls.md` | P12's mitigation replaced; P6 and P10 raised to High; **P14** (RHX backpressure halts acquisition), **P15** (model-authored task correctness), **P16** (parameter change as undocumented discontinuity), **P17** (fluid total is a lower bound) added |
| `docs/roadmap.md` | Stim tiers 1–2 move into v1; parity gate M5 loses its comparator; demo mode and preflight become gated deliverables |
| `docs/validation.md` | V2b, V7, V8, V9 added; V4 widened to both neural paths |
| `README.md` | Two rigs, not 3–4; bridge language removed |
| `docs/superpowers/specs/` | **S0**–**S13** written — the whole map, plus the stereoscope optics drawing |
| `docs/design/decisions/` | **ADR-0007** (event vocabulary ownership) |
| `docs/design/decisions/` | **ADR-0005** (day-one stack and interchangeability; supersedes ADR-0001 decision 3) and **ADR-0006** (task representation) written. Lab-host protocol adoption (D11) still needs an ADR once S10 is specified. |
