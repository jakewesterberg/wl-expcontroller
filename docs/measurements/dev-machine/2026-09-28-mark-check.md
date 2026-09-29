# The per-frame mark check -- its cost in the trial loop, on a development machine

> **Naming note (2026-09-29):** this document predates the rename and keeps the names it was
> written with. The repository `wl-expcontroller` is `wl-xcon` since 2026-09-28, and the Python
> package `wl_expcontroller` is `wl_xcon` since 2026-09-29 (XC-053), so a path such as
> `wl_expcontroller/taskd.py` is now `wl_xcon/taskd.py`.

> **This is not V1, and not a frame-timing measurement.** Frames here are not paced; the
> loop runs as fast as the CPU lets it. It measures what the check costs the CPU per
> frame, which is the only way it could disturb a paced frame. The effect on real frame
> timing is V12 (`docs/validation.md`), on a rig, with the photodiode.

**Date:** 2026-09-28. **Script:** `tools/measure_mark_check.py`
(P4d-2b b2a, spec §5.4), run as
`python tools/measure_mark_check.py --frames 1000 --trials 300`.
**Machine:** macOS-27.0-arm64-arm-64bit, arm64, arm.
**Python:** 3.12.13. **pyzmq:** 27.2.0 (libzmq 4.3.5).

## What was measured

`run.run_trial` over a trial that ends on frame 1000, against `run.Quiet`
(a world where nothing happens), 300 times with no `each_frame` and
300 times with the session's check -- `link.ZmqLink.mark_signal` on a live
loopback link whose mark socket is bound and idle -- interleaved trial by trial. The
collector is off inside each timed trial. The check alone is 200000 calls in
twenty batches.

| | median | p90 | p99 | max |
|---|---|---|---|---|
| trial loop, no check (ns per frame) | 339.5 | 379.7 | 397.1 | 407.7 |
| trial loop, with the check (ns per frame) | 8141.2 | 10022.0 | 12029.2 | 14444.3 |
| the check alone (ns per call) | 7866.4 | 9251.1 | 9758.1 | 9758.1 |

**Median added per frame by the check: 7801.7 ns.**

## What the check allocates

Over 200000 calls with nothing waiting (`tracemalloc`): net
64 bytes, peak 184 bytes above the
starting point, and 0 bytes still held that were
allocated in `wl_expcontroller/link.py`. The peak includes `tracemalloc`'s own
bookkeeping between readings; the held figure is the one about the check.

## What it decides, and what it does not

It says what the check costs a frame's CPU on this machine. Whether that disturbs a
frame on a rig -- at the rig's refresh rate, with the rig's display and card -- is V12's
to say, and the spec's rule stands: if it does, it goes back to the PI before b2a ships.
