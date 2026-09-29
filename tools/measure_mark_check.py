#!/usr/bin/env python3
"""What the per-frame mark check costs in the trial loop (P4d-2b spec §5.4).

CLAUDE.md: no timing claim without a measurement. Slice b2a puts one call inside every
frame -- `link.ZmqLink.mark_signal`, handed to `run.run_trial` as `each_frame` by
`taskd.Session.run` -- so that an operator's mark is stamped in the frame it reaches
the rig (spec §5.0). The spec says: "If the check measurably disturbs frames, it goes
back to the PI before b2a ships." This script is how that is decided on a given
machine, and the number it writes is the only number anyone may quote.

It measures, on the machine it runs on:

1. **The check alone**: `mark_signal()` on a live link whose mark socket is bound and
   idle -- the state it is in on nearly every frame -- in nanoseconds per call.
2. **The trial loop with and without it**: `run_trial` over a trial that ends on its
   own after a fixed number of frames, against a world that does nothing, first with
   no `each_frame` and then with the session's own check shape (the link's bound
   `mark_signal`, then a test on what it answered). Interleaved, trial by trial, so
   drift in the machine lands on both. Reported per frame.
3. **What the check leaves allocated**: `tracemalloc`, the net change and the peak
   over the calls in (1), with the link's own module's share named.

**What this is not.** Frames here are not paced: the loop runs as fast as the CPU
lets it, so this is the check's *CPU cost per frame* -- the only way it could disturb
a paced frame -- and not a frame-timing measurement. It is not V1. On a rig, the
effect on real frame timing is V12 in `docs/validation.md`, measured with the
photodiode. The garbage collector is off inside each timed trial and collected
between them, the discipline CLAUDE.md sets for trial loops, so a collection is not
billed to whichever variant it happened to land in.

    python tools/measure_mark_check.py
    python tools/measure_mark_check.py --frames 2000 --trials 400 \\
        --out docs/measurements/dev-machine/2026-09-27-mark-check.md
"""

from __future__ import annotations

import argparse
import gc
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import zmq  # noqa: E402 -- after the path, so the checkout's package is the one measured

from wl_xcon import link as _link  # noqa: E402
from wl_xcon.run import Quiet, run_trial  # noqa: E402
from wl_xcon.task import After, On, Outcome, State, Trial  # noqa: E402

#: The trial loop's frame period here: a number `After` compares against, nothing
#: more, since frames are not paced.
PERIOD = 0.001


def _trial(frames: int) -> Trial:
    """A trial that ends on its own on frame `frames`: `After` fires on the first
    frame whose elapsed time reaches it, and half a period short of `frames * PERIOD`
    is reached on frame `frames` and not before, whatever the float rounding."""
    return Trial(
        start="wait",
        states=[State("wait", go=[On(After((frames - 0.5) * PERIOD), Outcome.CORRECT)])],
    )


def _session_check(link: _link.ZmqLink):
    """The check exactly as `taskd.Session.run` builds it: the link's `mark_signal`,
    bound once, then a test on the answer. A mark never arrives here, so `stamp` is
    never reached; it is present so the closure is the session's shape."""
    signal = link.mark_signal
    stamped: list = []

    def each_frame(frame: int) -> None:
        mark = signal()
        if mark:
            stamped.append((mark, frame))

    return each_frame


def _timed_trial(trial: Trial, frames: int, each_frame) -> float:
    """Nanoseconds per frame for one trial, with the collector off inside it."""
    gc.collect()
    gc.disable()
    try:
        started = time.perf_counter_ns()
        result = run_trial(trial, Quiet(), PERIOD, values={}, each_frame=each_frame)
        took = time.perf_counter_ns() - started
    finally:
        gc.enable()
    if result.frames != frames:
        raise RuntimeError(f"the trial ran {result.frames} frames, not {frames}")
    return took / frames


def _spread(values: list[float]) -> dict:
    ordered = sorted(values)

    def at(q: float) -> float:
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    return {
        "median": statistics.median(ordered),
        "p90": at(0.90),
        "p99": at(0.99),
        "max": ordered[-1],
    }


def measure(frames: int = 1000, trials: int = 300, calls: int = 200_000) -> dict:
    """Run the three measurements and return what they found, as numbers."""
    link = _link.ZmqLink(
        "tcp://127.0.0.1:0", "tcp://127.0.0.1:0", mark_endpoint="tcp://127.0.0.1:0"
    )
    try:
        check = link.mark_signal
        for _ in range(1000):
            check()

        per_call = []
        for _ in range(20):
            started = time.perf_counter_ns()
            for _ in range(calls // 20):
                check()
            per_call.append((time.perf_counter_ns() - started) / (calls // 20))

        tracemalloc.start()
        try:
            before = tracemalloc.take_snapshot()
            tracemalloc.reset_peak()
            base, _ = tracemalloc.get_traced_memory()
            for _ in range(calls):
                check()
            now, peak = tracemalloc.get_traced_memory()
            after = tracemalloc.take_snapshot()
        finally:
            tracemalloc.stop()
        held_by_link = sum(
            stat.size_diff
            for stat in after.compare_to(before, "filename")
            if stat.traceback[0].filename == _link.__file__
        )

        trial = _trial(frames)
        each_frame = _session_check(link)
        for _ in range(10):
            _timed_trial(trial, frames, None)
            _timed_trial(trial, frames, each_frame)
        without, with_check = [], []
        for _ in range(trials):
            without.append(_timed_trial(trial, frames, None))
            with_check.append(_timed_trial(trial, frames, each_frame))
    finally:
        link.close()

    return {
        "frames": frames,
        "trials": trials,
        "calls": calls,
        "check_ns": _spread(per_call),
        "without_ns": _spread(without),
        "with_ns": _spread(with_check),
        "alloc_net_bytes": now - base,
        "alloc_peak_bytes": peak - base,
        "alloc_held_by_link_bytes": held_by_link,
    }


def report(found: dict) -> str:
    """The measurement as a Markdown file for `docs/measurements/`, with its
    conditions, in the shape the display spike's is."""
    rows = "\n".join(
        f"| {label} | {found[key]['median']:.1f} | {found[key]['p90']:.1f} | "
        f"{found[key]['p99']:.1f} | {found[key]['max']:.1f} |"
        for label, key in (
            ("trial loop, no check (ns per frame)", "without_ns"),
            ("trial loop, with the check (ns per frame)", "with_ns"),
            ("the check alone (ns per call)", "check_ns"),
        )
    )
    added = found["with_ns"]["median"] - found["without_ns"]["median"]
    return f"""# The per-frame mark check -- its cost in the trial loop, on a development machine

> **This is not V1, and not a frame-timing measurement.** Frames here are not paced; the
> loop runs as fast as the CPU lets it. It measures what the check costs the CPU per
> frame, which is the only way it could disturb a paced frame. The effect on real frame
> timing is V12 (`docs/validation.md`), on a rig, with the photodiode.

**Date:** {time.strftime('%Y-%m-%d')}. **Script:** `tools/measure_mark_check.py`
(P4d-2b b2a, spec §5.4), run as
`python tools/measure_mark_check.py --frames {found['frames']} --trials {found['trials']}`.
**Machine:** {platform.platform()}, {platform.machine()}, {platform.processor() or 'processor not reported'}.
**Python:** {platform.python_version()}. **pyzmq:** {zmq.__version__} (libzmq {zmq.zmq_version()}).

## What was measured

`run.run_trial` over a trial that ends on frame {found['frames']}, against `run.Quiet`
(a world where nothing happens), {found['trials']} times with no `each_frame` and
{found['trials']} times with the session's check -- `link.ZmqLink.mark_signal` on a live
loopback link whose mark socket is bound and idle -- interleaved trial by trial. The
collector is off inside each timed trial. The check alone is {found['calls']} calls in
twenty batches.

| | median | p90 | p99 | max |
|---|---|---|---|---|
{rows}

**Median added per frame by the check: {added:.1f} ns.**

## What the check allocates

Over {found['calls']} calls with nothing waiting (`tracemalloc`): net
{found['alloc_net_bytes']} bytes, peak {found['alloc_peak_bytes']} bytes above the
starting point, and {found['alloc_held_by_link_bytes']} bytes still held that were
allocated in `wl_xcon/link.py`. The peak includes `tracemalloc`'s own
bookkeeping between readings; the held figure is the one about the check.

## What it decides, and what it does not

It says what the check costs a frame's CPU on this machine. Whether that disturbs a
frame on a rig -- at the rig's refresh rate, with the rig's display and card -- is V12's
to say, and the spec's rule stands: if it does, it goes back to the PI before b2a ships.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--calls", type=int, default=200_000)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    text = report(measure(args.frames, args.trials, args.calls))
    if args.out is None:
        print(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
