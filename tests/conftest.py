"""Make `wl-preproc`'s frozen codec importable for the round-trip tests.

The dependency is **test-time only, deliberately**. `wl-preproc` is a pipeline
package that pulls DataJoint, Kilosort and SpikeInterface behind it; none of that
belongs on a task PC. So the rig runs our encoder, and the tests prove it agrees
with their decoder (S2 §6.2). What we never do is write a second *decoder* -- a
second implementation of the framing is a second definition free to drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SIBLING = Path(__file__).resolve().parents[2] / "wl-preproc"
if _SIBLING.is_dir() and str(_SIBLING) not in sys.path:
    sys.path.insert(0, str(_SIBLING))
