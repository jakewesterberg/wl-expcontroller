# S6 — I/O subsystem

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §3.2
- **Depends on:** S0 (card verified), S2 (word format), S3 (sync obligations)

The electrical contract is fixed in copper by `wl-sync`. This spec is the software side of it,
plus the things the copper implies that nobody wrote down.

---

## 1. The lines

**NI PCIe-6343. 19 digital out, 4 digital in, 9 analog in.**

| Direction | Line | Notes |
|---|---|---|
| out | Event code ×16, on **P0.8–P0.23** | Not zero-based. A config string for us; it would have been a real constraint for MonkeyLogic |
| out | Event strobe | Latches the word into the sync box's PIO and the recording NI |
| out | Reward commanded | OR'd on the board with the panel button; we never drive the pump |
| out | Stim trigger | Hardware-triggers the RHS; no software in the trigger path |
| **in** | `PD1_COMP` — task patch | Physical stimulus onset. A state primitive (S1 §5.4) |
| **in** | `PD2_COMP` — flip patch | Frame clock. Live dropped-frame detection |
| **in** | Chair motion trigger | From `wl-shook`. Gates task progression |
| **in** | RHS stim output | Intan actually stimulated. Counts deliveries against intent |
| analog in | Eye X/Y ×2 eyes, joystick X/Y, 3 × misc BNC | 9 channels |

**We do not trigger the cameras.** They free-run and the sync box records their
`ExposureActive` strobes (S3 §8). Any camera-trigger role a controller might assume is not ours.

---

## 2. Digital output

**The event word is the only thing with tight timing.** Bit order on P0.8–P0.23, strobe width,
and setup and hold against the sync box's PIO capture and the recording NI are verified on the
event-path mule before the full board exists, and become part of the V2 record.

Three rules:

1. **An escape sequence is atomic.** Escape word, payload words and checksum are strobed as one
   uninterruptible sequence, on every code path including an abort (S2 §6.3). A partial payload
   yields a `DecodeError` downstream and loses the rest of the trial's codes.
2. **Reward commanded and stim trigger are asserted from the DAQ, never through a vendor API.**
   `sglx_ni_DO_set` and RHX's TCP command interface are both API round trips with no bound;
   `spikeglx-realtime.md` already made this point for SpikeGLX and it applies identically to
   Intan.
3. **Output is software-timed, and its jitter is measured** (V2), not assumed. If the tail is
   unacceptable, S0 §3.2's fallbacks apply — the copper does not change.

---

## 3. Digital input: change detection, not polling

The photodiode comparators and the chair trigger are **state primitives** a task can wait on
(S1 §5.4). That makes their read latency part of the trial's critical path, which is new — the
prior design had digital input as an analysis convenience.

- **Change detection on P0**, with the edge timestamped as close to the hardware as the driver
  allows. Polling in the frame loop adds a frame of latency and quantises the edge to the frame.
- **`PD2_COMP` is counted continuously**, not sampled. A missing flip edge is a dropped frame,
  detected at the display surface, reported live and logged per trial (parent §11.5).
- **A missing `PD1_COMP` after a scene that should have produced one is a fault**, not a
  silence — it emits `PHOTODIODE_MISSING` and the trial is marked (S2 §5.1). A trial that ran
  with no stimulus must never look like a trial the animal failed.
- **V2b measures edge-to-userspace latency** under idle and loaded conditions. It has no prior
  estimate; if it is worse than a frame, photodiode-gated progression needs rethinking rather
  than tuning.

---

## 4. Reward, and why our total is a floor

The board's reward path: our `RWD_CMD` and the debounced panel button feed an OR gate, whose
output drives `wl-juicer` and is separately recorded as *delivered*.

- A console "give reward" **commands through the normal path**, so it appears as commanded *and*
  delivered. A panel press appears as delivered-without-commanded, which is how a hand-delivered
  reward stays countable.
- **Our commanded total is a lower bound on fluid delivered** (P17). Welfare accounting
  reconciles against the sync box's record of the delivered line, never against our intent.
- **Volume is time**, so the pump calibration (ml per ms) is what makes the accounting mean
  anything. It is measured per rig, re-measured on a schedule, and its identity is recorded in
  the session snapshot. An uncalibrated pump makes every fluid number fiction.
- Reward actions name a bounded-config entry and never carry a magnitude (S1 §2.3).

---

## 5. Analog input

**Scan rate is set by the microphone and nothing else** — an X-series card multiplexes one ADC
across the scan list, so the fastest channel sets the rate for all of them. On the recording
card that is 40 kHz for vocalisations (`wl-sync` breakout spec §9.3). The task PC's own 9
channels have no such requirement; its scan rate is set by the fastest thing *it* needs, which
is the joystick.

- **Eye analog is a recorded copy, not a control input** (S5 §3). We sample it so the eye PC's
  lag is measurable by cross-correlation; the UDP stream is what a decision uses.
- **Joystick** needs calibration (range, centre, dead zone) per rig and per animal, a hold and
  release discriminator, and its calibration identity in the session snapshot. It is a response
  device, so its latency belongs in V2.
- **Misc BNC ×3**, currently unassigned. S4 §8 proposes one for the **audio verification tap**;
  the assignment is `wl-sync`'s to confirm.

---

## 6. The hardware interface must degrade to absent

S13's kiosk has no NI card, no sync box, no neural plane — so this is not a rig-only subsystem
with a stub for tests. Every interface has three implementations and they are peers:

| Implementation | Used by |
|---|---|
| Hardware | The rigs |
| **Absent** | The kiosk, and any rig running without a device |
| Simulated | CI, demo mode, simulated sessions |

**"Absent" is not "broken."** A task that requires a device the deployment lacks is refused **at
load time** with a clear reason, not discovered when a trial tries to reward. The check is the
same shape as S1 §9's other load-time checks.

---

## 7. Hot-path discipline

The frame loop's I/O budget is bounded work only: preallocated buffers, no allocation, no
logging, no unbounded queues, and no call whose latency is not measured. `nidaqmx-python` is a
ctypes wrapper (S0 §3), so every call crosses into C — the cost is measured (V2, V2b), and if a
path is too slow it moves rather than being tuned in place.

---

## 8. Measurement

| Protocol | Covers |
|---|---|
| **V2** | Software-decision-to-edge latency, idle and loaded |
| **V2b** | Digital-input edge to state transition, using change detection |
| **V6** | Every line we assert appearing correctly in the reconstruction |

---

## 9. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | `PCIe-6343` + DAQmx on Ubuntu 24.04 — **UNVERIFIED** (S0 §3) | everything here |
| 2 | Misc-BNC assignment for the audio tap | `wl-sync` |
| 3 | Whether change detection on this card gives sub-frame latency (V2b) | photodiode-gated progression |
| 4 | Pump calibration procedure and schedule | fluid accounting meaning anything |
| 5 | Whether a lever/button needs a line, and which spare it uses | task vocabulary |
