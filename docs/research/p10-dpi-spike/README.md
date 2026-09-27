# P10 DPI spike: scripts

Research artifacts behind `../2026-09-27-p10-dpi-spike.md`. **Not package code and not
tests:** nothing here is imported by `wl_expcontroller/` or collected by pytest
(`testpaths = ["tests"]`). Every number in the report comes from one of these scripts;
their outputs are committed under
`docs/measurements/dev-machine/2026-09-27-p10-dpi-spike/`.

**Clean room.** Written from the OpenIrisDPI paper (bioRxiv 2025.04.18.649589 v2, Appendix
B) and general DPI literature only. No OpenIris or OpenIrisDPI source, wiki or README was
opened. The report lists the sources.

| File | What |
|---|---|
| `synth.py` | Synthetic eye frames with sub-pixel ground truth; optical model; every value cited or ASSUMED |
| `dpi_numba.py` | Core (a): Algorithm 1 in Python + numba, no allocation per frame |
| `dpi_core.cpp` | Core (b): the same, statement for statement, in C++ with a C ABI |
| `dpi_cpp.py` | ctypes binding for core (b) |
| `bench_cpp.cpp` | C++-only benchmark loop (no Python), one thread per camera |
| `build.sh` | Builds `build/libdpi.{dylib,so}` and `build/bench_cpp` |
| `check_agreement.py` | Both cores against each other and a literal numpy/scipy reference; `--controls` runs the perturbations it must catch |
| `figb1_check.py` | Reproduces the paper's Fig. B.1 thresholded-centroid simulation |
| `bench_precision.py` | Localization error against ground truth: SNR, size, rotation, head translation, hard cases, blinks |
| `bench_speed.py` | Per-frame time: both cores, 720x450 and 1440x1080, 1 and 2 cameras, paced at 500 Hz and not |
| `make_tables.py` | Renders the committed JSON as `tables.md` (the report's tables) |
| `real_data/` | The follow-up on OpenIrisDPI's tutorial recording (report §7b); its own README says how to run it |

## Rerun

Needs Python 3.13 and a C++17 compiler. Use a throwaway venv, not the project's `.venv`:

```sh
cd docs/research/p10-dpi-spike
uv venv /tmp/p10venv && VIRTUAL_ENV=/tmp/p10venv uv pip install numpy numba scipy
./build.sh
/tmp/p10venv/bin/python check_agreement.py    # must print AGREE
/tmp/p10venv/bin/python check_agreement.py --controls
/tmp/p10venv/bin/python figb1_check.py        # ~10 s
/tmp/p10venv/bin/python bench_speed.py        # ~6 min; keep the machine otherwise idle
/tmp/p10venv/bin/python bench_precision.py    # ~5 min; run after, not during, the speed run
/tmp/p10venv/bin/python make_tables.py > ../../measurements/dev-machine/2026-09-27-p10-dpi-spike/tables.md
```

Versions used for the committed results are recorded inside each JSON (`environment`).
Pools of frames for the speed run (up to ~0.5 GB) are written to `build/` and deleted.
`--quick` on either bench runs a tenth of the frames for a smoke test.

`precision.json` is deterministic: rerunning reproduces it exactly (seeds are CRC32s of
the condition names). `speed*.json` are not; they depend on the machine's load.

**Two edits after the speed runs, recorded so nobody is surprised.**

- `dpi_numba.py` gained the `p4_roi_masked` variant: one branch in the P4 stage, off by
  default.
- `bench_cpp.cpp`'s parameter array gained the matching tenth element, which the C++ core
  ignores.

The algorithm is unchanged, and `check_agreement.py` still agrees. A 5,000-frame recheck of
the 720x450 medians after the edit, at a load average of about 21
(`speed_recheck_after_variant.json`), gave 0.337 ms (numba) and 0.237 ms (ctypes), against
0.341 ms and 0.238 ms in run 1.

Speed numbers are **dev-machine numbers** (Apple M3 Max laptop, macOS). They are not the
rig's and must not be quoted as such.
