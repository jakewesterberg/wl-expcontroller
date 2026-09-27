"""Load OpenIrisDPI's tutorial recording for the P10 real-data follow-up.

The recording is OpenIrisDPI's own per-frame output (positions, not images). Column
names are those of wl-preproc's reader (`wl_preproc/eye/ohdpi.py`, our lab's code), and
every one is checked against the file's own header here. Nothing in this directory was
written from OpenIris or OpenIrisDPI source, wiki, README or tutorial notebook.

Paths come from arguments or the environment, never from this file:

    OPENIRIS_TXT          the session's .txt (its -settings.xml, -log.log and .cal are
                          found next to it by the session stem)
    OPENIRIS_TARGETS_NPZ  calibration.npz from the same bundle (fixation targets + sync)
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import pandas as pd

ENV_TXT = "OPENIRIS_TXT"
ENV_TARGETS = "OPENIRIS_TARGETS_NPZ"

EYES = ("Left", "Right")
PER_EYE = (
    "FrameNumber", "FrameNumberRaw", "Seconds",
    "PupilX", "PupilY", "PupilWidth", "PupilHeight", "PupilAngle",
    "DataQuality", "CR1X", "CR1Y", "CR4X", "CR4Y",
)
SHARED = ("Int0", "DebugTimeGrabbedLeft", "DebugTimeGrabbedRight", "DebugTimeProcessed")
# wl-preproc's reader: Int0 carries the sync line on bit 0 in this recording.
SYNC_BIT = 0


def resolve(txt: str | None, targets: str | None) -> tuple[pathlib.Path, pathlib.Path | None]:
    """The .txt (required) and calibration.npz (optional), from arguments or environment."""
    t = txt or os.environ.get(ENV_TXT)
    if not t:
        raise SystemExit(f"give --txt or set {ENV_TXT} to the OpenIris session's .txt")
    p = pathlib.Path(t).expanduser()
    if not p.is_file():
        raise SystemExit(f"{p}: not a file")
    g = targets or os.environ.get(ENV_TARGETS)
    q = pathlib.Path(g).expanduser() if g else None
    if q is not None and not q.is_file():
        raise SystemExit(f"{q}: not a file")
    return p, q


def sidecars(txt: pathlib.Path) -> dict[str, pathlib.Path]:
    """The session's other files, by OpenIris's shared-stem naming."""
    stem = txt.with_suffix("")
    return {
        "settings": stem.parent / f"{stem.name}-settings.xml",
        "log": stem.parent / f"{stem.name}-log.log",
        "cal": stem.with_suffix(".cal"),
    }


def load(txt: pathlib.Path) -> tuple[dict[str, np.ndarray], dict]:
    """Every column once: the ones this follow-up uses, and a census of all of them.

    The census (NaN count, exact-zero count, range, distinct values when few) is how the
    file's missing-value convention is established, so it covers every column rather
    than only the ones used.
    """
    frame = pd.read_csv(txt, sep=" ", engine="c")
    wanted = [f"{e}{c}" for e in EYES for c in PER_EYE] + list(SHARED)
    missing = sorted(set(wanted) - set(frame.columns))
    if missing:
        raise SystemExit(f"{txt}: header lacks {missing}; not the expected OpenIris format")
    census = {}
    for name in frame.columns:
        a = frame[name].to_numpy()
        u = np.unique(a[: min(a.size, 200_000)])
        entry = {
            "dtype": str(a.dtype),
            "nan": int(np.isnan(a).sum()) if a.dtype.kind == "f" else 0,
            "exact_zero": int((a == 0).sum()),
            "min": float(np.nanmin(a)),
            "max": float(np.nanmax(a)),
        }
        if u.size <= 8:
            vals, counts = np.unique(a, return_counts=True)
            if vals.size <= 16:
                entry["values"] = {repr(float(v)): int(c) for v, c in zip(vals, counts)}
        census[name] = entry
    cols = {name: frame[name].to_numpy() for name in wanted}
    return cols, {"rows": int(len(frame)), "columns": int(frame.shape[1]), "census": census}
