# Validation protocols

Rules: every protocol is a script (lands in tools/ once code exists) plus a written
procedure here; results are committed under docs/measurements/<rig>/<date>/ together
with the rig config snapshot (OS, driver, session type, monitor, SpikeGLX version).
A number without a committed artifact does not exist (pitfalls P1).

## V1 — Display timing (photodiode)
Photodiode on a corner patch driven by known flip sequences; recorded in NIDQ analog.
Report: onset lag (constant), onset variability (SD), duration error, dropped frames
over >= 2 h under task-like load. Run at rig acceptance and after ANY graphics
change (P4).

## V2 — Host output latency (TTL loopback)
taskd asserts a TTL on software events; line looped into NIDQ. Report: distribution
of software-decision-to-edge latency under idle and loaded conditions; compare
against pyControl-sidecar option if tail is unacceptable.

## V2b — Digital-input read latency
New (2026-08-31). Both photodiode comparators and the chair-motion trigger arrive as
NI digital inputs, and state progression may be gated on them. Drive a known edge into
the task PC's DI; report the distribution from physical edge to the state transition
that consumes it, using change detection on P0 rather than polling, under idle and
task-like load. Sets whether photodiode-gated progression is usable inside a frame.

## V3 — Eye loop
(a) Stall census: poll OpenIrisDPI at target rate for >= 1 h; report inter-sample and
staleness distributions (expect ~2% >= 10 ms per the paper; verify on our hardware).
(b) End-to-end: artificial eye step (or replayed saccade) -> gaze-window decision ->
display change measured by photodiode. Report full distribution, not just medians.

## V4 — Neural closed loop (bench), both paths
Signal generator into a probe in saline (or OneBox AI passthrough where appropriate);
the feature client computes features; taskd threshold decision -> stim TTL; TTL recorded
in the same run (method mirrors the Open Ephys Falcon Output test). Report: end-to-end
distribution vs channel count, probes, and low-latency-mode setting; CPU headroom on the
acquisition host.

Run for **both** sources, since they are architecturally different and only one has any
published number at all:
- **SpikeGLX path** — `neurofeatd`, C++, loopback on the acquisition PC. Compare against
  the Open Ephys + Falcon fallback on the same bench.
- **Intan RHX path** — `rhxfeatd` on the Spike Output socket. **No vendor latency figure
  exists**; the RHX guide names the sources (USB to host, TCP to client) and stops. This
  measurement is the first number anyone will have for it, so report the full distribution
  and the conditions in detail.

Additionally report the local-stimulation case specifically: with RHS amp-settle engaged
and our blanking window applied, how long after a stimulus the feature source is usable
again.

## V5 — Soak
Overnight (>= 12 h) synthetic session on the full rig stack: memory ceiling, GC
pauses (instrumented), drops, reconnect events (SpikeGLX handle keepalive), log
integrity. Precondition for any animal session on a new build (P12).

## V6 — Sync reconstruction round-trip
Synthetic multi-stream session with known ground truth -> reconstruction scripts ->
exact recovery of every event on the SpikeGLX clock. Runs in CI once code exists.

## V7 — Audio onset timing
New (2026-08-31). Auditory stimuli and auditory performance feedback are first-class in
this program, and audio onset on Linux has worse jitter and less visibility than video.
Tap the audio output electrically into a misc analog BNC recorded by NI; drive known
onset sequences. Report: constant lag, onset variability, and the distribution of
command-to-sound latency under task-like load. Re-run after any audio stack change, the
same rule V1 applies to graphics (P4).

## V8 — RHX backpressure headroom
New (2026-08-31). The RHX guide states that a client failing to read data output quickly
enough will fill the output buffer and **halt data acquisition** (P14). Run the closed-loop
client under progressively increasing channel count and TCP output rate until it falls
behind. Report: the margin between the operating point and the failure point, the behaviour
at the boundary, and confirmation that falling behind raises a loud alarm rather than
degrading silently. A session configuration whose margin has not been measured does not run.

## V9 — Display geometry and per-half photometry (split-screen stereoscope)
New (2026-08-31). Each eye's folded optical path length, viewport center and deg/pixel are
**measured, not derived** from the monitor's physical distance. Separately photometer the
left and right halves of the panel: on a split screen, left-right luminance or chromatic
nonuniformity is by construction an interocular mismatch that biases binocular combination
and would hide inside a panel that looks uniform. Report both halves' luminance and
chromaticity across the used area, and the vergence alignment residual after the
Nonius/vernier procedure.

**The full panel acceptance test is S0 §5.4** and is written to run before a panel is
committed to, not after. Its six criteria, two of which are disqualifying: burn-in
protection fully defeatable (pixel-shift silently translates the image and can walk the
photodiode patch off its sensor); ABL characterised **as an interocular coupling** by
sweeping fill factor in one viewport while photometering the other; per-half uniformity;
per-unit gamma, additivity and channel independence; photodiode-measured pixel response
and onset **in every display mode the rig will use**; and sustained full-field luminance
at 100% APL. Re-run in full on any panel change, including between units of one model --
the JOV study this derives from states performance "cannot be assumed or guaranteed"
across identical models.

## V10 — Pump calibration (millilitres per second of open time)
New (2026-09-06). **Nothing in this repository converts a reward volume into a solenoid
open time**, and until this is measured the real pump driver is deliberately not written
(`welfare.Pump` takes millilitres; the drive that opens copper is P7's).

The pulse width is genuinely ours to choose: `wl-sync`'s board one-shots the **manual**
button at ~199 ms and passes our commanded line (`RWD_CMD`, active-HIGH) straight through
the reward-OR gate untouched (their `hardware/README.md`, 2026-08-15 panel-instrumentation
entry). So there is no fixed quantum to discover, only a rate to measure.

Procedure: with the line and spout as the rig will run them, command a fixed open time and
collect the delivery into a tared vessel over **N ≥ 50 repeats**, by gravimetry (1 mL of
water ≈ 1 g) rather than by eye. Repeat across the open times a session actually uses, and
across reservoir levels from full to near-empty, because head pressure changes the rate and
a session drains the reservoir as it runs.

Report: millilitres per second and its variability; linearity against open time (a fixed
per-delivery dead time shows up as a non-zero intercept); the drift across reservoir level;
and the smallest open time that still delivers a repeatable drop. Re-run after any change to
the pump, the tubing, the spout or the reservoir geometry.

**Welfare-relevant, so the number is a committed artifact and not a note.** Every reward
volume in a bounded config is expressed in millilitres, and this measurement is the only
thing that makes those numbers mean anything at the animal's mouth.

## V11 — Replica pane over the LAN, in a browser (console)
New (2026-09-19). **ADR-0008 makes no claim that a browser can carry S9a §2's experimenter
replica**, and this is the measurement that decides it. Trial-rate plots are not in
question; the replica is, because it redraws the animal's screen with gaze, windows and
disparity on top at display rate, and PyQtGraph was chosen for exactly that.

**Measurable now, with no rig.** Nothing here needs a panel, a card or a tracker: the point
is the transport and the browser, not the stimulus.

Procedure: publish synthetic gaze samples and stimulus state from a host on the lab network
at the display rates a rig will run (**120 Hz, and 60 Hz**), consume them in a browser on a
second machine over the LAN, and render the S9a §4 replica pane. Run for **≥ 10 minutes**
per rate, which is a block rather than a demo, and repeat on the hardware an operator will
actually use — including the lowest-powered one, since "it was smooth on the dev laptop" is
not a finding about the lab.

Report: end-to-end latency from publish to paint (median and the upper tail, not the mean —
a replica that is usually current and occasionally seconds stale is worse than one that is
evenly late, because nobody can learn to trust it); dropped and coalesced samples; whether
the browser keeps up while the same page draws the trial-rate plots beside it; and CPU on
the control box, since that box is also running `taskd`.

**What the answer decides.** If the replica holds, the console is one surface and the Qt
stack is never added. If it does not, the fallback is a native path for *that pane only*,
not a second whole console — and the kiosk is unaffected regardless, because it has one
screen and no mirrors, so the animal's display is the thing itself rather than a replica
of it.
