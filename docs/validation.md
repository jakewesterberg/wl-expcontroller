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

## V3 — Eye loop
(a) Stall census: poll OpenIrisDPI at target rate for >= 1 h; report inter-sample and
staleness distributions (expect ~2% >= 10 ms per the paper; verify on our hardware).
(b) End-to-end: artificial eye step (or replayed saccade) -> gaze-window decision ->
display change measured by photodiode. Report full distribution, not just medians.

## V4 — Neural closed loop (bench)
Signal generator into a probe in saline (or OneBox AI passthrough where appropriate);
neurofeatd computes features; taskd threshold decision -> stim TTL; TTL recorded in
the same SpikeGLX run (method mirrors the Open Ephys Falcon Output test). Report:
end-to-end distribution vs channel count, probes, and low-latency-mode setting; CPU
headroom on the acquisition PC. Compare primary path vs Open Ephys + Falcon fallback
on the same bench.

## V5 — Soak
Overnight (>= 12 h) synthetic session on the full rig stack: memory ceiling, GC
pauses (instrumented), drops, reconnect events (SpikeGLX handle keepalive), log
integrity. Precondition for any animal session on a new build (P12).

## V6 — Sync reconstruction round-trip
Synthetic multi-stream session with known ground truth -> reconstruction scripts ->
exact recovery of every event on the SpikeGLX clock. Runs in CI once code exists.
