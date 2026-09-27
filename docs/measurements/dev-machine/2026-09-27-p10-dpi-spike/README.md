# P10 DPI spike: results (dev machine, 2026-09-27)

**These are not rig measurements.** The speed numbers come from an Apple M3 Max laptop
running macOS under background load. The precision numbers come from synthetic frames.

- Report: `docs/research/2026-09-27-p10-dpi-spike.md`
- Scripts, and how to rerun them: `docs/research/p10-dpi-spike/README.md`

| File | Produced by |
|---|---|
| `agreement.json`, `agreement_controls.json` | `check_agreement.py` (`--controls` for the second) |
| `linux_container_agreement.txt` | `check_agreement.py` inside a Debian aarch64 container, GCC 14.2; correctness only |
| `figb1_check.json` | `figb1_check.py` |
| `precision.json` | `bench_precision.py` (deterministic) |
| `speed.json`, `speed_run2.json` | `bench_speed.py`, two runs 10 min apart; the machine's load average is inside each |
| `speed_recheck_after_variant.json` | 720x450 medians rechecked after a variant branch was added to the numba core (see the scripts README) |
| `tables.md` | `make_tables.py`, from the JSON above |

**`real_data/` is the one exception to "synthetic".** It holds measurements of OpenIrisDPI's own
output in its tutorial recording (report §7b). They come from real eyes, not from this spike's
code or our rig. The recording itself is not committed.

| File | Produced by |
|---|---|
| `real_data/recording.json` | `real_data/measure_recording.py`: setup, validity, blinks, timing, gain, jitter, spectra |
| `real_data/comparison.json`, `real_data/tables.md` | `real_data/compare_synthetic.py`: the above against `precision.json` |
