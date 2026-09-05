"""Make `wl-preproc`'s frozen codec and calibration model importable for the
round-trip tests.

The dependency is **test-time only, deliberately**. `wl-preproc` is a pipeline
package that pulls DataJoint, Kilosort and SpikeInterface behind it; none of that
belongs on a task PC. So the rig runs our encoder and our own copy of their basis,
and the tests prove both agree with theirs (S2 §6.2). What we never do is write a
second *decoder* -- a second implementation of the framing is a second definition
free to drift.

**Two locations, because CI cannot use the first.** Beside this repo is the natural
layout on a laptop with both checkouts. It is unavailable to `actions/checkout`,
which resolves its `path` against `$GITHUB_WORKSPACE` and **throws** on anything
that escapes it -- so `path: ../wl-preproc` fails the step outright rather than
placing a sibling. That was found on 2026-09-05, in a CI run that had been red since
2026-08-31 with three encoder mutations SURVIVING: `words_for`, `words_for_code` and
`_checksum` are caught by the round-trip alone, and the round-trip was skipping.
CI therefore checks out into `<repo>/wl-preproc`, and both locations are searched.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

#: Beside the repo (local), then inside it (CI). First one that exists wins; a
#: checkout in neither place leaves the contract tests to skip, which is a failure
#: rather than a skip whenever `WLX_REQUIRE_PREPROC=1`.
_CANDIDATES = (_ROOT.parent / "wl-preproc", _ROOT / "wl-preproc")

for _candidate in _CANDIDATES:
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
        break
