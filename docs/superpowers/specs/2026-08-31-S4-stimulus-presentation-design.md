# S4 — Stimulus presentation

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §8; ADR-0002
- **Depends on:** S0 §5 (panel, modes), the stereoscope optics drawing

---

## 1. What already exists

| Thing | Where | Consequence |
|---|---|---|
| `TARGET_POSITION` payload | `wl-preproc/contracts/events.py` | `(role, x_dva, y_dva)` — **one 2D position, no eye and no disparity** |
| DVA encoding | same | Offset-binary, hundredths of a degree, refused rather than clamped out of range |
| `stimulus_calibration_id` | `wl-preproc/contracts/manifest.py` | **A slot already reserved for our display calibration identity.** §9 defines what goes in it |
| `StartedAtSource.BEHAVIORAL_CONTROL` | same | *"The behavioural control system where present"* — **we stamp the session start label** |

The pipeline deliberately holds no screen geometry. We hold all of it.

---

## 2. Coordinates: cyclopean degrees, and nothing else crosses a boundary

**A task never names a pixel.** Positions are cyclopean degrees; the display module maps them
to per-eye viewport pixels using measured optics. That is what makes the same task run at a
different viewing distance, on a different panel, in either display mode, and on the S13 kiosk.

```
cyclopean (x°, y°, disparity°)
        │
        ├── left  viewport → pixels, via left  optical path, left  centre
        └── right viewport → pixels, via right optical path, right centre
```

The mapping inputs are per-rig and per-animal, and all of them are **measured, not derived**:
each eye's folded optical path length, each viewport's centre, the vergence offset (a software
constant, 3.2° nominal — optics drawing §6), and the display mode's deg/pixel. They live in the
session snapshot beside the gaze mapping version, and a change to any of them is a discontinuity
of the same class as a parameter change (P16).

**Disparity is a stimulus property**, applied as equal and opposite horizontal offsets about the
cyclopean position. A monocular task is the zero-disparity case of the same path, which is what
makes stereo cost nothing to keep available (D6).

---

## 3. Calibration targets are presented at zero disparity

This resolves S5's open item 4, and avoids an amendment.

`TARGET_POSITION` carries one 2D position with no eye field. On a stereoscope that looks like a
gap: a target appears at a different *pixel* position in each viewport. It is not a gap, because
**calibration targets are presented at zero disparity**, so both eyes fixate the same cyclopean
point and one position describes the target for both.

Per-eye maps are still fitted **independently** — each eye has its own raw Purkinje vector
(`CR1 − CR4`, S5 §1) and its own map — but they are fitted against a **shared cyclopean target
set**. That matches `wl-preproc`'s own shape, where `purkinje_vector(path, eye)` and `EyeQuality`
are both keyed by eye while the target is not.

**Consequence for the calibration block:** its 3×3 grid (S5 §2) is a cyclopean grid at zero
disparity. Disparity is never calibrated by the gaze map; it is a rendering property verified
separately (§10).

---

## 4. `DisplayAdapter`

The seam ADR-0002 exists to preserve. PsychoPy is used strictly as a library behind it; the
adapter is ours and is what the simulators substitute for.

Obligations, all of which are the reason the seam is narrow:

1. **Flip-locked.** Everything scheduled for a frame is drawn before the flip; nothing is drawn
   between flips.
2. **The frame period is never assumed.** S0's dual mode makes it 4.2, 8.3 or 2.08 ms, and S13's
   kiosk something else again. Code that hardcodes a period is a bug the checker should catch.
3. **No allocation, no disk I/O, no logging inside a frame.** Assets are resident before an
   epoch begins.
4. **Draws the photodiode patches every frame** (§7), unconditionally, on every code path.
5. **Reports the frame index** so motion (§5) and any logged position are reconstructable.

---

## 5. Motion is a function, not a trajectory

**Position is a pure function of (parameters, seed, frame index).** Never a logged per-frame
trajectory.

- Offline reconstruction is exact, from the parameters and seed already in the trial record.
- The hot path stays allocation-free — no per-frame append, no growing buffer.
- Random-dot kinematograms reproduce by the same mechanism: the seed is the stimulus.

This is the same identity-versus-content rule S2 applied to event codes, applied to stimuli:
the record carries what generates the stimulus, not a transcript of it.

**Gaze-contingency is a stimulus property, not a code path.** A stimulus declares
`anchored_to="gaze"` and the display module resolves its position each frame from the current
gaze sample — which carries the staleness that S5 §4.1 requires every gaze decision to record.

---

## 6. Assets

Natural-image sets are **resident before an epoch begins**. Loading, decoding and uploading to
texture memory happen at block or session boundaries, never inside a trial and never inside a
free-viewing epoch.

- An image set is declared, versioned, and its identity recorded per trial — the image shown is
  part of the trial's parameters, not an incidental.
- Memory is budgeted at session start; a set that does not fit is refused then, not discovered
  mid-session.
- The S13 kiosk has different memory and a different set; asset residency must therefore be a
  declared requirement, not an assumption.

---

## 7. Photodiode patches are a display-module obligation

`A_PD1` is the **task patch** — stimulus onset. `A_PD2` is the **flip patch** — it alternates
every refresh and is therefore a frame clock. Both are fixed in copper (`wl-sync` breakout spec
§3.1) and both return to us as digital comparator inputs.

- The flip patch **alternates on every refresh, unconditionally**, including during blanks,
  aborts, pauses and error states. A frame clock that stops during an abort is not a frame clock.
- Both patches live in the **bottom strip**, 2.18 cm × full panel width, created by stopping the
  far mirror to ±17° vertical (optics drawing §5). Outside both viewports, so neither is visible
  to either eye.
- **Verified dark to each eye at bring-up**, not assumed from geometry — a stray reflection off a
  mirror edge would put the flip patch back into the field, and that is a V9 item.
- The task patch is driven by the display module from the scene's own onset, so a task cannot
  forget it and cannot desynchronise it from what it drew.

---

## 8. Audio

Three roles: auditory stimuli, performance feedback to the animal, and vocalisation monitoring.
Only the third is already handled (`A_MIC` into NI).

- **Timing is measured, not asserted.** Audio onset jitter on Linux is worse than video and less
  visible. The output is **electrically tapped into one of the three unassigned misc analog BNC
  inputs**, giving sound onset on the NI clock without room-acoustics smearing (parent §8.5).
  Protocol **V7**.
- Sounds are declared assets, resident before an epoch, like images.
- Every sound onset emits `AUDIO_ON` / `AUDIO_OFF` (S2 §5.1), so audio events reach the recording
  clock through the same path as everything else.
- Feedback tones are ordinary stimuli with ordinary event codes; there is no separate feedback
  subsystem.

---

## 9. Stimulus calibration, and the id the manifest already wants

`SessionManifest.stimulus_calibration_id` is a reserved slot with nothing defined in it. S4
defines it as the identity of a **stimulus calibration record** covering:

| Component | Why |
|---|---|
| Per-mode gamma / luminance transfer, per half of the panel | On a split screen, left-right difference is an interocular mismatch (V9) |
| Measured deg/pixel per eye, per mode | From the measured optical paths, not the nominal |
| Vergence offset in force | Software constant, per animal |
| Panel identity, firmware, and the state of every "care" feature | Pixel-shift silently corrupts the geometry (S0 §5.4) |
| ABL fill-factor limit measured as an interocular coupling | S0 §5.4 criterion 2 |
| The V1 and V9 artifacts this was derived from | So the id resolves to measurements, not to a claim |

**A session runs against exactly one stimulus calibration id, and the id changes whenever any
input to it changes** — including a mirror-carriage move for a different animal. That is what
makes the manifest field mean something rather than being a label.

---

## 10. Test screens

Run from the console (S9), and one of them is required at every session start:

1. **Per-eye alignment / vergence target** (Nonius or vernier) — **every session**, residual
   recorded. The optics are adjustable per animal, so this is the cheap test that catches a
   carriage that moved.
2. Geometry and linearity grid, per eye.
3. Gamma and luminance ramp, per half.
4. Photodiode patch test — drive known sequences, confirm both comparator inputs.
5. Frame-timing pattern for V1, per mode.
6. **Disparity verification** — a target at known disparity, confirmed fused and at the intended
   depth. Disparity is not covered by the gaze calibration (§3) and needs its own check.

---

## 11. Measurement

| Protocol | Covers |
|---|---|
| **V1** | Onset lag and variability, dropped frames, **in every mode the rig uses** |
| **V7** | Audio onset timing and jitter, via the misc-BNC tap |
| **V9** | Per-half photometry, per-eye optical paths, ABL interocular coupling, patch darkness |

Dropped frames are detected in hardware, live, from `PD2_COMP` at the display surface — not from
the engine's own frame-interval accounting (parent §11.5).

---

## 12. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Whether `TARGET_POSITION` ever needs a disparity field, or stereo targets stay in our record | nothing today; §3 avoids it |
| 2 | Who writes `SessionManifest` — us, ingest, or wl.works | S10 |
| 3 | Misc-BNC assignment for the audio tap | `wl-sync` |
| 4 | Whether the kiosk shares the stimulus vocabulary or a subset | S13 |
| 5 | Image-set versioning and where sets live on disk | S10 |
