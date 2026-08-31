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
