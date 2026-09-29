"""What a refusal looks like, wherever one is raised.

Lifted out of `check.py` when gaze calibration needed the same vocabulary. Both
answer the same question in the same words -- *this is why I will not proceed, and
here is the name of the reason* -- and the CLI renders either without caring which
produced it.

It lives in its own module rather than in `check.py` because the dependency has to
run the other way: a load-time check that compares a task's declared eccentricity
range against the calibrated extent will import `calibration`, and `calibration`
already needs to report findings. One of the two had to move, and a four-line
dataclass is the cheaper thing to relocate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    detail: str
    #: Whether this refuses the load. A non-blocking finding still surfaces -- a
    #: `Custom` component is legitimate and still belongs on the review list.
    blocking: bool = True
