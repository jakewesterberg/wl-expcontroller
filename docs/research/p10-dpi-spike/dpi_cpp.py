"""Thin ctypes binding to the C++ core (libdpi). Same call shape as dpi_numba.Tracker.

ctypes rather than pybind11 so the spike adds no build dependency; `build.sh` compiles.
"""

from __future__ import annotations

import ctypes
import pathlib
import sys

import numpy as np

import dpi_numba

HERE = pathlib.Path(__file__).resolve().parent
_LIB_NAME = "libdpi.dylib" if sys.platform == "darwin" else "libdpi.so"


def load(path: pathlib.Path | None = None) -> ctypes.CDLL:
    lib = ctypes.CDLL(str(path or HERE / "build" / _LIB_NAME))
    lib.dpi_create.restype = ctypes.c_void_p
    lib.dpi_create.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.dpi_destroy.argtypes = [ctypes.c_void_p]
    lib.dpi_process.restype = None
    lib.dpi_process.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    return lib


class Tracker:
    """One camera stream. The ctypes call releases the GIL for its duration."""

    def __init__(self, h: int, w: int, prm: np.ndarray | None = None, lib: ctypes.CDLL | None = None):
        self.lib = lib or load()
        self.h, self.w = h, w
        self.ws = self.lib.dpi_create(h, w)
        self.prm = np.ascontiguousarray(dpi_numba.default_params() if prm is None else prm, dtype=np.int64)
        self.out = np.zeros(dpi_numba.N_OUT, np.float64)
        self._prm_p = self.prm.ctypes.data
        self._out_p = self.out.ctypes.data
        self._fn = self.lib.dpi_process

    def __call__(self, img: np.ndarray) -> np.ndarray:
        # Caller guarantees a C-contiguous uint8 (h, w) frame; not checked on the hot path.
        self._fn(self.ws, img.ctypes.data, img.strides[0], self._prm_p, self._out_p)
        return self.out

    def close(self) -> None:
        if self.ws:
            self.lib.dpi_destroy(self.ws)
            self.ws = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
