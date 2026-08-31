# S7 — Neural plane and stimulation

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §10
- **Scope note:** stimulation **tiers 1 and 2** (epoch- and gaze-triggered) are v1 and live in
  S6 and S8. This spec is **tier 3** — neural-contingent — plus the feature interface all three
  eventually share.

---

## 1. Two sources, one interface

Both systems record; either may gate the loop; **Intan always stimulates.**

| | Local-activity gating | Distant-area gating |
|---|---|---|
| Source | Intan RHX **Spike Output** socket | SpikeGLX `fetchLatest`, filtered AP stream (`js = -2`) |
| Client | `rhxfeatd`, on the Intan host | `neurofeatd`, acquisition PC, C++, loopback |
| Effort | Small — RHX already detects the spikes on GPU | Large — we write the feature extractor |
| Artifact | Severe: same amplifier. RHS amp-settle plus our blanking | Absent |
| Published latency | **None. Anywhere.** | Vendor loopback histogram only |

Both publish the same schema-versioned message over ZMQ (msgpack), consumed latest-wins:
schema version, source id, feature vector, channel-map hash, source sample index, publisher
monotonic timestamp, sequence number, and a **validity flag** — a client that fell behind
publishes *invalid*, never stale numbers dressed as fresh ones.

---

## 2. The decision stays in `taskd`

A tempting optimisation is to push the threshold test into `rhxfeatd`, which sits on the same
machine as the amplifier and could assert faster.

**Rejected, for now, on welfare grounds rather than performance ones.** Stimulation gating is on
S8 §7's welfare-critical list, and splitting it across two machines means two implementations of
a bound, two places to review, and two things that can disagree about how much has been
delivered. One decision point, in the process that also holds the bounded config.

This is a **measured** trade, not a permanent one: if V4 shows the round trip through `taskd`
misses the science's timing requirement, that is a reason to revisit with numbers. Designing
around an unmeasured fear would be P1 in the other direction.

**A consequence of S2 makes this easier than it looks.** Intan receives the strobe only and
cannot read event codes, so a client on the Intan host could not condition on trial state read
off its own inputs anyway — it would need `taskd` to tell it. Keeping the decision in `taskd`
removes that message entirely rather than adding one.

---

## 3. P14 — the client that halts the recording

The RHX guide, read 2026-08-31:

> *"It is important that the client application reads the data output quickly, otherwise the
> memory allocated for data output will fill up and **halt data acquisition**."*

A slow client does not drop samples; **it stops the recording.** No other component in this
system can destroy the experiment it is controlling.

Mitigations, all mandatory:

1. **A dedicated bounded reader that does not share the Python GIL.** `rhxfeatd` is compiled,
   for this reason and not for throughput.
2. **Hard drop-oldest.** The buffer is fixed and the oldest data goes. Latest-wins consumers do
   not care; an unbounded queue would trade a visible drop for an invisible cliff.
3. **Channel count and TCP output rate are budgeted deliberately**, at a measured margin from the
   failure point (V8), and a session configuration whose margin has not been measured does not
   run.
4. **Falling behind is a loud alarm**, surfaced on the console and event-coded — never a silent
   degradation.

---

## 4. Stimulation

### 4.1 The path

Task declares parameters → controller pushes them over RHX's TCP command interface **at safe
points only** (session start, block boundaries, ITI; never mid-trial, because a TCP round trip
has no bound) → **read back and confirmed** → our TTL from the NI card hardware-triggers the
RHS. No software in the trigger path (S6 §2).

### 4.2 Bounds, and why they are enforced against observation

Every bound in S8 §4 applies. Two are specific here:

- **Charge balance is verified, not assumed.** A biphasic imbalance is not something to discover
  from tissue.
- **Deliveries are counted against the RHS stim-output line**, which returns to the task PC as a
  digital input — not against our intent. Session limits are therefore enforced against
  stimulation that **actually happened**, which is the difference between a limit and a hope.

### 4.3 Tier 3 needs two things tiers 1 and 2 do not

- **A refractory period**, enforced in the gating logic and independently bounded in config.
- **A runaway detector.** Closed-loop stimulation admits positive feedback — stimulation drives
  activity that re-triggers stimulation. The detector trips on rate over a window and on total
  per session, and **latches**: it requires a human to clear, because a self-clearing detector on
  a positive-feedback loop is not a detector.

### 4.4 Blanking

The RHS blinds its own amplifier around a pulse (amp-settle, ~1 ms post as the guide's starting
point). Our feature extractor needs its own window on top, because a threshold detector sees the
artifact before the amplifier has settled.

**Blank on the observed stim-output line, not on our command.** We know when we asked; the line
knows when it fired. On the local path those differ by the whole trigger latency, and blanking
on intent would leave the artifact's leading edge inside the feature window.

The blanking window's duration is a measured quantity (V4), not a guess, and it is recorded per
session because it directly determines what the closed loop can see.

---

## 5. Features

**Two feature types, selectable per experiment** (PI, 2026-08-31), behind one `FeatureSource`
interface:

| Type | Computed as | Natural home |
|---|---|---|
| **Envelope** | band-pass, full-wave rectify, boxcar integrate over a sliding window | SpikeGLX path — the filtered AP stream is already there |
| **Threshold-crossing rate** | events past a per-channel threshold, counted in a window | Intan path — **RHX's Spike Output socket already produces these on GPU**, so the local loop is nearly free |

This plays each system's strength rather than forcing a common denominator, and it is why the
local path costs so much less to build than the distant one (§1).

**The cost is comparability, and it is paid explicitly.** The two types are different quantities,
so an experiment that switches source mid-study is comparing different things unless it
deliberately matches them — which means reimplementing detection on the SpikeGLX side, or an
envelope on the Intan side, at that experiment's own cost. **The feature type and its full
parameter set are recorded per session**, so the question can at least be asked afterwards.

Band, threshold, integration window and channel combination remain PI-owned per experiment. Two
engineering constraints on whatever is chosen:

- **CAR is server-side on the SpikeGLX path** — SpikeGLX maintains a bandpassed, globally
  demuxed-CAR stream (`js = -2`) and the cost is paid inside its C++, not our client. RHX does its
  own filtering and threshold detection on GPU. **So the two paths compute different things
  unless deliberately matched**, and any experiment that switches sources mid-study must account
  for it.
- **The channel map hash travels with every message.** A feature vector whose channel map has
  changed is a different quantity with the same shape, and that is exactly the kind of silent
  substitution that survives review.

---

## 6. Measurement

| Protocol | Covers |
|---|---|
| **V4** | Neural-event-to-stim-TTL, **both paths**, against channel count, probes and low-latency mode. Plus the post-stim recovery time with amp-settle and our blanking engaged |
| **V8** | RHX backpressure headroom — the margin between the operating point and the failure point, and confirmation that falling behind alarms rather than degrades |

The RHX path has **no published latency figure anywhere**; V4 will be the first number for it.
The SpikeGLX path has vendor loopback numbers that describe a configuration that is not ours.

Gates (proposed): median ≤ 6 ms on the SpikeGLX path; the RHX path measured and reported without
a target, because inventing a threshold for an unmeasured path would be P1.

---

## 7. Open items

| # | Item | Owner |
|---|---|---|
| 1 | **MUA feature definition v0** — band, rectification, window, channel combination | PI, scientific |
| 2 | Whether `rhxfeatd` and `neurofeatd` share an implementation or only a contract | S7 |
| 3 | Whether the two paths' features are deliberately matched or allowed to differ | PI, scientific |
| 4 | Runaway thresholds: rate window and per-session total | PI + welfare review |
| 5 | Whether `rig/intan` and `rig/sglx` are one machine (S0 open item 2) | V8 decides |
