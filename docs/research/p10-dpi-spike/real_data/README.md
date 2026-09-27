# P10 real data: OpenIrisDPI's tutorial recording

Scripts behind §7b of `../../2026-09-27-p10-dpi-spike.md`. They measure OpenIrisDPI's own
per-frame output in the tutorial recording: validity, blinks, frame timing, and the jitter of
P1, P4 and P1 − P4 in fixation. They then set that jitter against the spike's synthetic
precision. **Every real number they produce is from the tutorial recording.** None is from
our tracker or our rig, and none measures P4 brightness, because the file holds positions,
not images.

**Clean room.** The inputs are the recording and its sidecar files, `calibration.npz` from
the same bundle, and wl-preproc's reader (`wl_preproc/eye/ohdpi.py`), which supplied the
column names. The names are checked here against the file's own header. No OpenIris or
OpenIrisDPI source, wiki, README or tutorial notebook was opened.

**Nothing from the recording is committed.** The inputs stay where they are and are named
by argument or environment:

| Variable | Argument | What |
|---|---|---|
| `OPENIRIS_TXT` | `--txt` | the session's `.txt`; its `-settings.xml`, `-log.log` and `.cal` are found beside it by the shared stem |
| `OPENIRIS_TARGETS_NPZ` | `--targets` | `calibration.npz` (fixation targets and the sync line); optional, but the gain, the in-target rates and the arcmin columns need it |

| File | What |
|---|---|
| `recording.py` | Loads every column once, checks the header, and takes a census: NaN, exact-zero, range, and the distinct values when there are few |
| `measure_recording.py` | Setup facts, validity, blinks, timing, sync alignment and gain, and fixation-window jitter and spectra. Writes `recording.json` |
| `compare_synthetic.py` | `recording.json` against the spike's `precision.json`: matching P4 SNR (an inference) and arcmin. Writes `comparison.json` and `tables.md` |

Results go to `docs/measurements/dev-machine/2026-09-27-p10-dpi-spike/real_data/`.

## Run

Use a throwaway venv, not the project's `.venv`.

```sh
uv venv /tmp/p10real && VIRTUAL_ENV=/tmp/p10real uv pip install numpy pandas
cd docs/research/p10-dpi-spike/real_data
export OPENIRIS_TXT=~/Downloads/Tutorial/OpenIris-2024Jul31-114628/OpenIris-2024Jul31-114628.txt
export OPENIRIS_TARGETS_NPZ=~/Downloads/Tutorial/calibration.npz
/tmp/p10real/bin/python measure_recording.py      # about 40 s on the dev machine
/tmp/p10real/bin/python compare_synthetic.py      # instant
```

The committed results were made with Python 3.13.9, numpy 2.5.3 and pandas 3.0.6 (the
versions are recorded in `recording.json`). Both scripts are deterministic.

## Estimator self-test

`measure_recording.py` runs its self-test first (alone with `--selftest`) and refuses to
measure if it fails. The self-test builds 200,000 samples of white noise with SD 0.03 px
plus a slow drift. It checks three things:

- the step RMS / √2 and the >200 Hz floor both return 0.03 (within 5 % and 10 %);
- the lag-1 autocorrelation of the steps is −0.5;
- after 0.08 px RMS of 60–140 Hz power is added, the step RMS rises and the floor does not
  move.

It also checks that the 11-point slope returns a ramp's rate exactly.

It was shown to fail on three deliberate faults, run by hand and not committed:

- the floor taken over the whole band;
- the PSD normalization halved;
- the slope scaled by 0.9.

On white noise the floor's per-window median reads about 4 % low, which is the median of a
χ² variable, so per-window floors are slightly conservative. The mean-spectrum floor does
not carry that bias.
