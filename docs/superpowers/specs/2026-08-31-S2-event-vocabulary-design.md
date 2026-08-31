# S2 — Event vocabulary and hardware truth

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §6
- **Amends:** the parent's claim that codes are "allocated in `wl-mllib`"; and
  `wl-mllib/wl.yaml`, which states nothing is allocated

---

## 1. The premise this spec was written under was wrong

The spec map scoped S2 as designing an allocation because `wl-mllib/wl.yaml` says
*"Nothing is allocated yet"* and *"wl-preproc reads event handling from here rather than
defining it."*

**Both statements are false.** `wl-preproc/wl_preproc/contracts/events.py` is a **frozen
interface** (their design spec §3.5 item 4) implementing a complete 16-bit strobed protocol:
range allocation, markers, task events, a task-type namespace, escapes with declared payload
word counts, an XOR checksum, offset-binary degrees-of-visual-angle encoding, and a decoder
that never raises on malformed input. It carries explicit *"values are frozen and never
renumbered"* warnings, because renumbering silently relabels every block in every prior
recording.

So S2 is not a codec design. It is **conformance, allocation in the open ranges, and
settling an ownership contradiction between two repositories.**

---

## 2. Ownership

### 2.1 The rule: decodability versus meaning

`wl-preproc` owns everything required to **turn a strobed word stream into structured
events**. `wl-mllib` owns everything required to **know what those events meant to an
experiment**. Stated as a test: if getting it wrong makes the recording *undecodable*, it is
`wl-preproc`'s; if it makes the recording *uninterpretable*, it is `wl-mllib`'s.

| Range / artifact | Owner | Contains |
|---|---|---|
| Framing, escapes, checksum, payload word counts, DVA encoding | **wl-preproc** | How words become events at all |
| `Marker` 1–255 | **wl-preproc** | Session, block and trial structure — the skeleton a decoder walks |
| `TaskEvent` 256–4095 | **wl-mllib** | Lab-wide task-event semantics |
| `TaskTypeCode` 100+ | **wl-mllib** | Lab-defined task identities |
| Task-specific / condition 4096–32767 | **wl-mllib** | Per-task and per-condition encoding |

### 2.2 The one range this sharpens

Your ruling assigned `wl-preproc` "the markers, the escapes and the framing" and `wl-mllib`
"TaskTypeCode 100+ and the 4096–32767 range," which leaves **`TaskEvent` 256–4095**
unassigned — and `wl-preproc` has already allocated 256–259 into it
(`FIXATION_ACQUIRED`, `FIXATION_END`, `CALIBRATION_START`, `CALIBRATION_END`).

This spec proposes **256–4095 goes to `wl-mllib`**, because those codes are about what an
experiment did, not about whether the stream parses — a decoder that has never heard of
`FIXATION_ACQUIRED` still decodes it as a `SimpleEvent` and loses nothing structural. The
four existing values **transfer as already-allocated and stay frozen at their current
numbers**; ownership moving is not permission to renumber.

**Confirm or overrule this before anything is allocated.** It is the only part of §2 that is
not simply describing what already exists.

### 2.3 What has to change elsewhere

- **`wl-mllib/wl.yaml`** stops claiming the whole vocabulary. Its `publishes` entry narrows
  to the three ranges above, and it gains a `consumes` entry for `wl-preproc`'s codec.
- **`wl-preproc`** is asked to record the split on its side, and two other things (§5).
- **The parent design spec §6** said codes are "allocated in `wl-mllib`." True of the ranges
  a task uses, false of the protocol. Corrected there.

---

## 3. What already exists (do not redesign)

Read from `wl_preproc/contracts/events.py` on 2026-08-31, at commit `f7fb10a`.

```
1–255       session/block markers and trial outcomes   Marker
256–4095    task events                                 TaskEvent
4096–32767  task-specific / condition encoding          (open)
32768+      escapes introducing multi-word payloads     Escape
```

**Allocated:** `SESSION_START` 1, `SESSION_END` 2, `BLOCK_END` 3, `TRIAL_START` 32,
`TRIAL_END` 33, `TRIAL_CORRECT` 34, `TRIAL_ERROR` 35, `TRIAL_ABORT` 36,
`TRIAL_FIXATION_BREAK` 37, `TRIAL_NO_RESPONSE` 38; `FIXATION_ACQUIRED` 256, `FIXATION_END`
257, `CALIBRATION_START` 258, `CALIBRATION_END` 259; escapes `TRIAL_NUMBER` 0x8001 (2
words), `BLOCK_START` 0x8002 (2), `CONDITION` 0x8003 (2), `TARGET_POSITION` 0x8004 (3);
`TaskTypeCode` 1–7 with lab-defined starting at 100; `TargetRole` 0–1.

**Payload framing:** escape word, payload words, then an XOR checksum over the escape and
its words. A truncated or mismatched payload yields a `DecodeError` and decoding continues,
so one bad trial cannot lose a session.

**Positions are degrees, offset-binary, hundredths of a degree** (`DVA_SCALE` 100,
`DVA_OFFSET` 32768), refused rather than clamped out of range. The pipeline holds no screen
geometry deliberately; the task does, because the task renders the stimulus.

---

## 4. The rule for what goes in the stream

`wl-preproc`'s own reasoning for putting the task type inside `BLOCK_START` is that a block
should be *"self-describing in the recording even when the ELN is wrong or late."*
Generalized, that is the allocation rule:

> **Event codes carry identity and timing. The session record carries content.** Encode
> content into the stream only where the recording must remain interpretable without our
> files.

What must survive without our files is small, and `wl-preproc` has already allocated most of
it: trial structure, trial number, condition, task type, target position, outcome. Parameter
values, stimulation settings, plot declarations and token internals do not qualify — they
always travel with the session directory, and encoding floats into 16-bit words to duplicate
them would buy nothing and cost precision.

The consequence is that **our additions are almost all simple codes, not escapes** — which
matters, because an escape is an amendment against a frozen interface and a simple code is
not.

---

## 5. What wl-expcontroller needs

### 5.1 In wl-mllib's ranges (ours to allocate, no amendment required)

Proposed `TaskEvent` additions, grouped. Numbers are deliberately left unassigned here — they
are allocated once, in `wl-mllib`, in one commit, so no two sessions can pick differently.

| Group | Events | Driven by |
|---|---|---|
| Stimulus | `STIMULUS_ON`, `STIMULUS_OFF`, `PHOTODIODE_CONFIRMED`, `PHOTODIODE_MISSING` | Photodiode-gated progression (parent §5.4); a missing edge must be a recorded fault, not a silence |
| Gaze | `SACCADE_ONSET`, `SACCADE_END`, `TARGET_ACQUIRED`, `TRACKER_STALE` | Saccadic choice; P6 makes stall episodes worth recording as events rather than inferring later |
| Response | `RESPONSE_JOYSTICK`, `RESPONSE_TOUCH`, `RESPONSE_LEVER` | Touch has **no hardware line**, so a code is its only route to the recording clock |
| Reward and tokens | `REWARD_COMMANDED`, `TOKEN_AWARDED`, `TOKEN_LOST`, `TOKEN_CASHED` | Token economies; the reward lines are hardware truth, these carry the reason |
| Stimulation | `STIM_TRIGGERED_EPOCH`, `STIM_TRIGGERED_GAZE`, `STIM_TRIGGERED_NEURAL` | Three tiers (parent §10.4); the trigger itself is already on three hardware lines, so these carry *which rule fired* |
| Session control | `PAUSE_START`, `PAUSE_END`, `FREE_VIEW_START`, `FREE_VIEW_END` | Unbounded free-viewing epochs are first-class (parent §5.4) |
| Calibration | `RECENTER_APPLIED`, `DRIFT_CORRECTION_APPLIED`, `GAZE_MAPPING_CHANGED` | The mapping is versioned and every trial cites its version (parent §9.3) |
| Display | `DISPLAY_MODE_CHANGED`, `FRAME_DROP` | Dual-mode is a rig configuration (S0 §5.3); drops are detected in hardware via `PD2_COMP` |
| Audio | `AUDIO_ON`, `AUDIO_OFF` | Auditory stimuli and feedback (parent §8.5) |

`TaskTypeCode` 100+ is allocated per task as tasks are written; the standing 1–7 already
cover the mapping tasks.

**Nothing above is allocated until a task needs it.** A vocabulary grows the same way an
abstraction does (P2): on a second concrete consumer, not on anticipation.

### 5.2 In wl-preproc's ranges (amendment required)

Exactly **one** new escape is requested:

| Escape | Payload | Why it must be an escape |
|---|---|---|
| `PARAM_CHANGE` | 2 words — a uint32 change sequence number | P16: a live parameter change is an undocumented discontinuity unless it lands on the recording clock. The *values* stay in the session record; this carries only the pointer that joins them |

Drafted at `docs/pending-wl-preproc-amendments.md`.

---

## 6. Conformance requirements on wl-expcontroller

1. **Codes are allocated, never invented.** A task naming a code absent from the `wl-mllib`
   allocation is **refused at load time**, not at run time. This is the cheapest guardrail in
   the design against model-authored task files (P15).
2. **Golden-file tests against `wl-preproc`'s own decoder.** Our emitted streams are decoded
   by `decode_stream` in tests, and the round trip is asserted. We do not write a second
   decoder; a second implementation is a second definition free to drift.
3. **The escape sequence is atomic.** Escape, payload words and checksum are strobed as one
   uninterruptible sequence — no other code may be emitted between them, on any code path,
   including an abort.
4. **Word semantics and strobe timing** — bit order on P0.8–P0.23, strobe width, and setup
   and hold times against the sync box's PIO capture and the NI card — are verified on the
   event-path mule before the full board exists (`wl-sync` breakout spec §10.3), and become
   part of the V2 record.

---

## 7. Intan reads the strobe, not the codes

`wl-preproc`'s docstring: *"Full width goes to the sync box and NI; Intan RHS receives the
strobe only, because its 16 digital inputs cannot fit 16 data lines plus strobe plus
barcode."*

So **Intan can time-align events but cannot read what any of them were.** Recovering meaning
on the Intan timebase requires the sync box or NI record plus the barcode. Consequences:

- Any analysis performed purely in Intan's timebase is blind to event identity until
  alignment has run. It is not a data loss — the barcode closes it — but it is an ordering
  constraint on analysis, and it was not in the parent design.
- **It constrains the local-activity closed loop (S7).** A `rhxfeatd` decision cannot be
  conditioned on event identity read from Intan's own digital inputs; if the neural plane
  needs to know the trial state, `taskd` must tell it over the message bus rather than the
  wire. Recorded here because S7 would otherwise have assumed the codes were available.

---

## 8. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Confirm `TaskEvent` 256–4095 moves to `wl-mllib` (§2.2) | any allocation |
| 2 | `wl-preproc` accepting the `PARAM_CHANGE` escape | P16's guarantee |
| 3 | `wl-preproc` recording the ownership split on its side | the contradiction persisting |
| 4 | Whether their DVA comment's MonkeyLogic premise needs restating under ADR-0005 | nothing; it is a reasoning correction |
| 5 | Strobe width and setup/hold against PIO capture and the 6343 | the mule test, then V2 |
