"""Per-frame processing time of the two cores, one and two cameras, paced and not.

DEV MACHINE NUMBERS. They say how much CPU the algorithm needs on this laptop; they say
nothing about the rig's OS scheduling, USB, or camera driver (see the report).

Cores:
  numba       - dpi_numba, driven from a Python loop (the function releases the GIL)
  cpp_ctypes  - the C++ core called through ctypes from a Python loop
  cpp_native  - the C++ core in a C++ loop (build/bench_cpp), no Python at all
Each camera is a thread with its own workspace and its own stretch of a frame pool large
enough (hundreds of MB) that frames arrive cache-cold, as DMA'd camera frames would.
"paced" releases one frame per camera every 2 ms (500 Hz) on a shared clock, as two
hardware-synchronized cameras would; "unpaced" runs back to back. Only the call is timed.

    ./build.sh && python bench_speed.py [--frames 10000] [--quick]

Writes speed.json to docs/measurements/dev-machine/2026-09-27-p10-dpi-spike/.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import platform
import struct
import subprocess
import sys
import threading
import time

import numpy as np

import dpi_cpp
import dpi_numba as dn
import synth

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "measurements" / "dev-machine" / "2026-09-27-p10-dpi-spike"
BUILD = HERE / "build"
PERIOD_NS = 2_000_000  # 500 Hz


def make_pool(scene: synth.Scene, n: int, seed: int) -> np.ndarray:
    """Varied frames: gaze within +-8 deg, head within +-20 px, ~2 % blinks."""
    rend = synth.Renderer(scene, seed=seed)
    rng = np.random.default_rng(seed + 1)
    pool = np.empty((n, scene.height, scene.width), np.uint8)
    for i in range(n):
        t = synth.geometry(scene, rng.uniform(-8, 8), rng.uniform(-8, 8),
                           head_dx_px=rng.uniform(-20, 20), head_dy_px=rng.uniform(-20, 20))
        if rng.random() < 0.02:
            pool[i] = rend.blink(rng, t=t, closure=rng.uniform(0.3, 1.0))
        else:
            pool[i] = rend.frame(t, rng)
    return pool


def write_pool(pool: np.ndarray, path: pathlib.Path) -> None:
    n, h, w = pool.shape
    with open(path, "wb") as f:
        f.write(b"DPIP" + struct.pack("<3i", h, w, n))
        f.write(pool.tobytes())


def stats(ns: np.ndarray) -> dict:
    ms = ns.astype(np.float64) / 1e6
    q = np.percentile(ms, [50, 90, 99, 99.9])
    iqr = np.percentile(ms, 75) - np.percentile(ms, 25)
    edges = [0, 0.1, 0.2, 0.3, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10, 20, 50, 1e9]
    hist, _ = np.histogram(ms, bins=edges)
    return {
        "n": int(ms.size),
        "median_ms": float(q[0]),
        "iqr_ms": float(iqr),
        "mean_ms": float(ms.mean()),
        "p90_ms": float(q[1]),
        "p99_ms": float(q[2]),
        "p99_9_ms": float(q[3]),
        "max_ms": float(ms.max()),
        "frac_over_1ms": float((ms > 1).mean()),
        "frac_over_2ms": float((ms > 2).mean()),
        "slowest_10_ms": sorted(ms.tolist())[-10:],
        "hist_edges_ms": edges[:-1],
        "hist_counts": hist.tolist(),
    }


def python_run(kind: str, pool: np.ndarray, frames: int, cams: int, paced: bool) -> list[np.ndarray]:
    n, h, w = pool.shape
    trackers = [(dn.Tracker(h, w) if kind == "numba" else dpi_cpp.Tracker(h, w)) for _ in range(cams)]
    times = [np.zeros(frames, np.int64) for _ in range(cams)]
    for k, tr in enumerate(trackers):  # warm-up (numba compiles on first call)
        for i in range(200):
            tr(pool[(k * n // cams + i) % n])
    barrier = threading.Barrier(cams)
    start = [0]

    def cam(k: int) -> None:
        tr = trackers[k]
        out = times[k]
        off = k * n // cams
        pc = time.perf_counter_ns
        barrier.wait()
        if k == 0:
            start[0] = pc() + 5_000_000
        barrier.wait()
        t0 = start[0]
        for i in range(frames):
            if paced:
                dl = t0 + i * PERIOD_NS
                d = dl - pc()
                if d > 0:
                    time.sleep(d / 1e9)  # sleep, never spin: a spinning thread holds the GIL
            img = pool[(off + i) % n]
            a = pc()
            tr(img)
            out[i] = pc() - a

    th = [threading.Thread(target=cam, args=(k,)) for k in range(cams)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    return times


def native_run(pool_path: pathlib.Path, frames: int, cams: int, paced: bool, stages: bool = False) -> tuple[list[np.ndarray], list[np.ndarray]]:
    prefix = BUILD / f"run_{cams}_{int(paced)}_{int(stages)}"
    cmd = [str(BUILD / "bench_cpp"), str(pool_path), str(prefix), str(frames), str(cams),
           str(PERIOD_NS // 1000 if paced else 0), "1" if stages else "0"]
    subprocess.run(cmd, check=True, capture_output=True)
    times = [np.fromfile(f"{prefix}.t{k}.i64", np.int64) for k in range(cams)]
    st = [np.fromfile(f"{prefix}.t{k}.stages.i64", np.uint64).reshape(-1, 6) for k in range(cams)] if stages else []
    return times, st


def environment() -> dict:
    def sh(*c):
        try:
            return subprocess.run(c, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception as e:  # pragma: no cover
            return f"unavailable: {e}"
    import numba
    return {
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "platform": platform.platform(),
        "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string") if sys.platform == "darwin" else platform.processor(),
        "perf_cores": sh("sysctl", "-n", "hw.perflevel0.physicalcpu") if sys.platform == "darwin" else "",
        "efficiency_cores": sh("sysctl", "-n", "hw.perflevel1.physicalcpu") if sys.platform == "darwin" else "",
        "power": sh("pmset", "-g", "batt").splitlines()[0] if sys.platform == "darwin" else "",
        "load_avg": os.getloadavg(),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "numba": numba.__version__,
        "cxx": sh("clang++", "--version").splitlines()[0],
        "cxx_flags": "-O3 -std=c++17 -ffp-contract=off (build.sh)",
        "switchinterval_s": sys.getswitchinterval(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=10_000)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--name", default="speed.json", help="output file name (a repeat: speed_run2.json)")
    args = ap.parse_args()
    frames = 1000 if args.quick else args.frames
    BUILD.mkdir(exist_ok=True)
    res: dict = {
        "note": "DEV MACHINE (Apple M3 Max laptop, macOS). Not the rig, not Linux, no camera, "
                "no USB. Processing time per frame per camera only.",
        "environment": environment(),
        "frames_per_camera": frames,
        "params": dn.default_params().tolist(),
        "runs": [],
    }
    sizes = {"roi_720x450": (synth.Scene(), 600), "full_1440x1080": (synth.full_frame_scene(), 300)}
    for size_name, (scene, npool) in sizes.items():
        t0 = time.time()
        pool = make_pool(scene, npool if not args.quick else npool // 3, seed=4242)
        pool_path = BUILD / f"pool_{size_name}.bin"
        write_pool(pool, pool_path)
        print(f"{size_name}: pool {pool.shape} {pool.nbytes / 1e6:.0f} MB built in {time.time() - t0:.0f}s", flush=True)
        for kind in ("numba", "cpp_ctypes", "cpp_native"):
            for cams in (1, 2):
                for paced in (False, True):
                    if kind == "cpp_native":
                        times, _ = native_run(pool_path, frames, cams, paced)
                    else:
                        times = python_run(kind, pool, frames, cams, paced)
                    for k, t in enumerate(times):
                        s = stats(t)
                        s.update({"size": size_name, "core": kind, "cameras": cams, "camera": k,
                                  "paced_500hz": paced, "scene": dataclasses.asdict(scene)})
                        res["runs"].append(s)
                        print(f"  {kind:10s} cams={cams} cam{k} paced={paced!s:5s} median={s['median_ms']:.3f} "
                              f"iqr={s['iqr_ms']:.3f} p99={s['p99_ms']:.3f} p99.9={s['p99_9_ms']:.3f} "
                              f"max={s['max_ms']:.3f} >1ms={s['frac_over_1ms']:.4f}", flush=True)
        # Stage breakdown, C++ native, one camera, unpaced.
        _, st = native_run(pool_path, frames, 1, False, stages=True)
        d = np.diff(st[0].astype(np.int64), axis=1) / 1e6
        labels = ["blur_threshold_l7_9", "edges_cr_scan_l10_12_15", "hull_ellipse_l13_14", "cr_tcom_l16_18", "p4_l19_25"]
        res.setdefault("stages_cpp_native", {})[size_name] = {
            lab: {"median_ms": float(np.median(d[:, i])), "p99_ms": float(np.percentile(d[:, i], 99))}
            for i, lab in enumerate(labels)
        }
        print("  stages:", {k: round(v["median_ms"], 4) for k, v in res["stages_cpp_native"][size_name].items()}, flush=True)
        del pool
        pool_path.unlink()
    RESULTS.mkdir(parents=True, exist_ok=True)
    name = "speed_quick.json" if args.quick else args.name
    (RESULTS / name).write_text(json.dumps(res, indent=1))
    print("wrote", RESULTS / name)


if __name__ == "__main__":
    main()
