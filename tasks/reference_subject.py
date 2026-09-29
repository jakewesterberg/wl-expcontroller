"""The reference animal's settings: a file for `wlx run --subject-settings`, and for
reading.

One per animal, named at session start like its bounded config (PI, 2026-09-29). It
holds the animal's half-IPD, `E`, which the stereoscope's field is built from; direct
view reads nothing from it.

**The number is not a measurement.** 1.6 cm is the optics drawing's nominal `E`, and
the subject is `REFERENCE`, the one `reference_bounds.py` is written for, so a session
refuses this file for any real animal.
"""

from wl_xcon.geometry import SubjectSettings

SETTINGS = SubjectSettings(subject="REFERENCE", half_ipd_cm=1.6)
