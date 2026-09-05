# S5 — Eye tracking, calibration, and gaze

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §9
- **Carries:** pitfalls **P6**, the project's dominant scientific risk

---

## 1. Most of the calibration is already decided, and not by us

Read from `wl-preproc/wl_preproc/eye/` at `f7fb10a`, 2026-08-31 — including second-order
calibration, merged that same day.

| Thing | Where | Shape |
|---|---|---|
| Raw signal | `eye/gaze.py::purkinje_vector` | **`(CR1X − CR4X, CR1Y − CR4Y)` per eye.** P1 in `CR1`, P4 in `CR4`; CR2/3/5 unused |
| Model | `eye/calibration.py::CalibrationModel` | `AFFINE` = `[1, dx, dy]` (3 terms/axis); `SECOND_ORDER` = `[1, dx, dy, dx², dy², dx·dy]` (6 terms/axis). Taken from **OpenIrisDPI's own tutorial notebook** |
| Source ranking | `CalibrationSource` | `FITTED`, **`ONLINE`**, `CARRIED_FORWARD`, `REFUSED` |
| Recorded file columns | `eye/ohdpi.py` | `LeftFrameNumber`, `LeftSeconds`, `Int0` (sync word, bit 0 on the reference rig), `LeftCR1X`, `LeftCR4X`, ~100 columns total |

**`ONLINE` is defined as our map and it outranks carry-forward.** Their docstring: *"the
calibration that was in use during acquisition, as opposed to our offline fit — the map the
animal was actually held to, which is why it outranks carry-forward … The behavioural control
system will change, and whatever replaces MonkeyLogic will also save a calibration."*

So the *shape* of our online calibration is not ours to design; only the *procedure* is. We fit
the same basis to the same raw vector and publish a map their `read_online_map` can consume —
which today reads a MonkeyLogic `.bhv2` and will need a second reader (§8).

---

## 2. A ring of calibration targets cannot fit a second-order map

`wl-preproc` measured conditioning on real constellations. Their table:

| Constellation | Affine | Second-order |
|---|---|---|
| 3×3 grid | 1.0000 | **0.2277** |
| **ring of 8** | 1.0000 | **0.0000** |
| ring, off-origin | 1.0000 | **0.0000** |
| plus, 5 points | 1.0000 | 0.2361 |
| 4 spread | 0.8646 | 0.2893 |
| collinear | 0.0000 | 0.0000 |

Thresholds: `MIN_CONDITIONING` = 0.05 affine, 0.10 second-order.

**A ring of eight targets — eight points, more than the six a second-order fit needs — is exactly
degenerate on the quadratic basis.** The reason is arithmetic rather than empirical: points on a
circle satisfy `dx² + dy² = r²`, so the constant, `dx²` and `dy²` columns are linearly dependent
and no amount of points on that circle separates them.

**Consequence for the calibration procedure: present a grid, never a ring.** A ring is the
intuitive pattern and it silently forecloses the second-order rung — which S3 §7 already
established is what decides whether a session reaches second-order calibration at all. The
procedure **computes conditioning online and refuses to advance on a degenerate constellation**
rather than discovering it in preprocessing.

**Amended 2026-09-05**, against
`docs/measurements/dev-machine/2026-09-05-calibration-constellation.md`. Three corrections,
each of which this section previously got wrong or left open:

- **The constellation is thirteen targets, not nine** — a 3×3 grid at 75% of the per-eye
  field, plus four intermediates on the diagonals at half that. Coordinates in
  `calibration.constellation`. At equal animal cost nine, thirteen and twenty-five targets are
  indistinguishable for accuracy; what thirteen buys is **survival**. Nine points fitting six
  parameters has three to spare, so losing four makes the second-order fit not
  ill-conditioned but *impossible*, and the session drops to affine at roughly double the
  error. Thirteen survive losing five, 95% of the time.
- **A ring plus a centre is not an acceptable substitute**, and this section implied it was by
  ruling out only the bare ring. Ring-8 plus a centre scores **0.1697** — it passes the 0.10
  gate — while leaving the quadratic radial term resting on a single contrast between two
  radii. It is worse than it looks rather than degenerate, which is the harder failure to see.
- **Conditioning is necessary and not sufficient.** It is scale-invariant *by construction*
  (their `_conditioning` docstring is explicit about why), so **it cannot see how far the
  targets reach**: a 3×3 shrunk to 60% of the field scores 0.2277, identical to one spanning
  it, and then understates its own error by 3.0× against 1.5×. The acceptance criterion
  therefore gains a second clause — the constellation is compared against the eccentricity the
  session will actually test, and extrapolation beyond it is reported
  (`constellation-inside-tested-region`). Reported, not refused: the measurement supports
  "reach matters", and inventing a refusal threshold it does not support would be fabrication.

**How far out is not obvious, and the intuitive answer is wrong.** 75% of the field beat 60%,
70%, 85% and 100% under every optics assumption swept. Pushing targets to the panel edge is
*worse than* pulling them in: the corners sit near 21° eccentricity, outside the disc any task
uses, and their leverage drags the quadratic away from where stimuli actually go.

---

## 3. Ingest

**UDP port 9003, poll protocol**: send `WAITFORDATA`, receive JSON carrying pupil centre, pupil
diameter, CR centre and P4 centre. We do not modify the tracker's protocol; a worked Python
client ships in the OpenIrisDPI repo.

- Poll at **at least the display frame rate**, in a dedicated thread that never blocks the
  frame loop.
- **Stamp arrival with `CLOCK_MONOTONIC` and compute staleness** — how old the sample is at the
  moment a decision uses it.
- Treat every sample as *latest available*, never as a clocked stream.
- The **ACCES analog copy is a recorded channel, not a control input** (parent §9.1). Its value
  is making the eye PC's software and USB lag measurable by cross-correlation per session.
- Drive OpenIris's remote API (`StartRecording`, `RecordEvent`) so the eye PC's own authoritative
  file is session-aligned by construction, not only by barcode.

The eye PC's file is the record; our UDP stream is a copy for control. **`Int0` carries the sync
word on bit 0 on the reference rig** — rig wiring, not format, and one constant to set per rig.

---

## 4. P6 — the stall problem, handled honestly

The OpenIrisDPI paper reports frame **processing** of 1.1 ± 0.1 ms median with **~2% of frames
≥10 ms (max ~50 ms)** from OS preemption, on the authors' hardware.

**Processing time is not the quantity that hurts us.** What matters is *staleness at the moment
we poll* — a different distribution, related to the first through camera rate, queueing and
drop behaviour, and **not measured by anyone for our configuration**. V3 measures it. Nothing
downstream may quote the paper's 2% as though it described our rig (P1).

### 4.1 The design that tolerates it

1. **Every gaze decision records the staleness of the sample it used.** Not a summary
   statistic — per decision, in the trial record. That makes stratifying by staleness possible
   post hoc, and it is what turns an unknown into a measured covariate.
2. **Hold-last with a staleness ceiling.** Beyond the ceiling the gaze state is *unknown*, not
   *last known*.
3. **A trial abort requires corroboration** — multiple stale or out-of-window samples, never one.
4. **A stall in a critical epoch emits `TRACKER_STALE`** (allocated in S2) so the affected trial
   is identifiable in analysis rather than silently included. This is mandatory whatever else is
   decided: a corrupted gaze-contingent trial that looks clean is worse than a lost one.
5. **A stall does not abort the trial** (PI, 2026-08-31). The update lands on the last known
   gaze position, the trial completes, and it carries `TRACKER_STALE` plus the staleness of the
   sample actually used. Keeping the trial and deciding in analysis beats discarding data at a
   rate nobody has measured yet.

   **The risk this accepts, and the mitigation.** A marked-but-included trial can be analysed by
   someone who did not read the flag. So the mark must not depend on being noticed: staleness
   is carried as a **per-trial quantity in the behavioural table**, not only as an event, so it
   arrives as a column an analysis has to actively drop rather than a footnote it can miss.
   `wl-preproc`'s `EyeQuality` already holds per-eye `tracking_loss_fraction` and
   `blink_rate_hz` as *"a lower bound on how much of a session is unusable"* — a per-trial
   staleness summary belongs in the same place and for the same reason, and §8's amendment
   should offer it.

### 4.2 Attack the source, not only the symptom

The 2% is OS preemption on a Windows PC, and the paper measured *their* machine. Before treating
it as a constant, the OpenIris PC gets tuned as a rig-configuration task with a **measured
before-and-after**: real-time process priority, CPU affinity and isolation, power management
disabled, no other software, no background scanning. If that moves the distribution materially,
the whole class of saccade-contingent experiment gets easier — and if it does not, we have
measured that rather than assumed it.

---

## 5. Online saccade detection

**Engbert–Kliegl** (PI, 2026-08-31): velocity-threshold in 2D velocity space with a per-trial
adaptive threshold. Chosen for a reason beyond its own merits — it is **already in `wl-preproc`'s
offline suite**, so online-versus-offline agreement measures staleness and latency rather than
comparing two different algorithms. Picking anything else would have made the disagreement
uninterpretable.

A **versioned, tested component with logged parameters** — not per-task code, because its
parameters affect results and a task that re-derives it makes two sessions incomparable.

**The adaptive threshold needs a stall rule.** Engbert–Kliegl's threshold is derived from the
trial's own velocity distribution, which a tracker stall corrupts: samples spanning a gap produce
an apparent velocity that is an artifact of the gap, not of the eye. So velocity is computed only
across consecutive samples within the staleness ceiling, and a saccade whose detection window
contains a gap is **flagged, not silently reported** (§4.1 item 4).

- Tested against **replayed OpenIrisDPI recordings**, not synthetic traces alone.
- Its parameters and version are in the trial record; a change is a discontinuity of the same
  class as a parameter change (P16).
- It must degrade explicitly under staleness: a saccade detected across a gap is flagged, not
  silently reported.
- Provides the `SaccadeOnset()` and `SaccadeInto(window)` guards from S1 §2.2, and nothing else
  in a task may implement its own.

The binding requirement is the parent's: a saccade-triggered display change should land inside
saccadic suppression. That budget is measured end to end in V3(b), photodiode to photodiode, not
computed from component latencies.

---

## 6. The gaze mapping is one versioned object

Recentering, drift correction, the calibration button and mid-session recalibration are four
faces of one thing: **the map changes during a session.**

- Session-scoped, versioned, with a change log.
- **Every trial cites the mapping version in force.**
- **Automatic drift correction never overwrites the raw signal.** Raw and corrected are both
  recorded, every adjustment is logged, and the correction is reversible offline — a silent
  correction is indistinguishable from an artifact.
- Toggling drift correction is a logged parameter change.
- **The optics are part of the mapping's validity.** S0's stereoscope is adjustable per animal
  (`a = 3.27·E`), so a mirror-carriage change invalidates the map exactly as a recalibration
  does. Mirror geometry and both measured optical paths sit beside the mapping version in the
  session snapshot.

**Gaze windows are specified in cyclopean degrees**, with per-eye mapping to viewport pixels
(parent §9). A task never names a pixel.

---

## 7. The calibration procedure

Two mechanisms, both, per S3 §7 — `wl-preproc` calls them *"complementary, not alternatives."*

**Planned calibration block, at session start.** Emits `TaskTypeCode.CALIBRATION` in its
`BLOCK_START` payload, planned by wl.works' session planner so ingest does not quarantine it.
Presents the **thirteen-target constellation** (§2), gathers fixations at each target, computes conditioning online, and
refuses to complete on a degenerate constellation. This is the block that reliably supplies the
six well-spread targets the second-order rung requires.

**In-task epochs, throughout the day.** Bounded by `TaskEvent.CALIBRATION_START` /
`CALIBRATION_END`, gathering points from fixations a normal task already produces. Creates no
block, needs no planning, and is what makes ordinary trials contribute to the map and tracks
drift.

**Recentering** is a single-point offset applied to the existing map — the cheap operation an
experimenter runs when the animal has settled differently in the chair. It is a new mapping
version like any other.

---

## 8. What we publish

**An online calibration map, in a form `wl-preproc` can read.** Today
`eye/calibration.py::read_online_map` takes a `.bhv2` path and parses a MonkeyLogic binary.
Under ADR-0005 there will be no `.bhv2`, so a second reader is needed — and the format should be
ours to write and theirs to read, not a binary they must reverse-engineer.

Proposed: a small text file in `expcontroller/` carrying, per eye, the `CalibrationModel`, the
coefficients in their basis order, the target constellation used, the measured conditioning, the
RMS residual from `validate_map`, and the mapping version. Every field is one they already
compute or consume.

**Drafted as an amendment** at `docs/pending-wl-preproc-amendments.md`.

**Accepted and built, verified 2026-09-05 against `wl-preproc` at `c3f6c5e`.** This is no
longer a proposal: `wl_preproc/eye/expcontroller.py::read_expcontroller_map` exists, and
reading it settles the format rather than leaving it to us. **The ask is closed and the
schema is theirs**, which means the fields below are a contract and not a suggestion —
their models forbid unrecognised keys at both levels, so a field we invent is a declined
file rather than an ignored one.

| | Field | Notes |
|---|---|---|
| file-wide | `mapping_version` | int. Read and required; nothing branches on it yet |
| file-wide | `raw_definition` | Must be the literal `"CR1 - CR4"` — their names for our P1 and P4. **They refuse any other value**, so coefficients honestly labelled for a different feature can never be silently applied to their CR1−CR4 difference |
| file-wide | `targets` | Degrees. The constellation *presented*, not the subset an eye worked |
| per eye | `model` | `affine` or `second_order`, validated against their enum |
| per eye | `coefficients.x` / `.y` | **In `basis()` column order.** They do no re-ordering here, unlike the `.bhv2` path, because this format is theirs to define and ours to write to |
| per eye | `conditioning`, `rms_residual_deg` | Required, validated, then deliberately discarded — their `CalibrationMap` reserves those columns for fits *they* performed and will not misreport ours into them |

**Per eye, independently.** `left:` and `right:` are validated separately, and a file offering
a usable map for one eye is an ordinary outcome rather than a broken file — tracking is
often better on one side. A malformed `right` declines only `right`.

**Wire format is YAML**, matching every other cross-repo file that pipeline reads. We write
it by hand (`calibration.GazeCalibration.to_yaml`) rather than take a YAML dependency onto a
task PC, for the reason `encode.py` gives about the codec, and
`tests/test_calibration.py` round-trips it through their real reader. One trap found doing
so and worth not rediscovering: **PyYAML resolves `1e-17` to the string `'1e-17'`**, because
YAML 1.1's float pattern requires a decimal point before the exponent — and a quadratic
coefficient that small is entirely ordinary.

---

## 9. Measurement

**V3(a) — stall census.** Poll at target rate for ≥1 h; report inter-sample and **staleness**
distributions, before and after the OpenIris PC tuning of §4.2. Not the paper's number: ours.

**V3(b) — end to end.** Artificial eye step, or replayed saccade, through gaze decision to
display change, measured photodiode to photodiode. Report the full distribution and the fraction
landing inside saccadic suppression. **This is the number that decides whether the
saccade-contingent programme is feasible as designed.**

**V3(c) — calibration quality.** RMS residual by constellation and model, on replayed data, so
the online fit is validated against `validate_map` before an animal depends on it.

---

## 10. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | ~~`wl-preproc` accepting an online-calibration reader for our format~~ **Closed 2026-09-05: they built it** (`eye/expcontroller.py::read_expcontroller_map`, at `c3f6c5e`), and its source fixes the schema — see §8 | — |
| 2 | Staleness ceiling and grace-period values | frozen only after V3(a) |
| 3 | ~~Stall policy inside a gaze-contingent epoch~~ **Answered: proceed and mark.** Remaining: whether the per-trial staleness summary reaches `wl-preproc`'s `EyeQuality` | wl-preproc |
| 4 | ~~Independent per-eye maps or a cyclopean fit~~ **Answered in S4 §3: independent per-eye maps against a shared cyclopean target set at zero disparity** | — |
| 5 | ~~Saccade-detection algorithm~~ **Answered: Engbert–Kliegl**, matching `wl-preproc`'s offline suite so agreement is interpretable. Remaining: its parameters, from V3(c) | V3(c) |
