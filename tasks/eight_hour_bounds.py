"""A second reference bounded config, with the real eight-hour duration ceiling.

**Read `reference_bounds.py` first.** Both of its guards apply here unchanged: the
subject is `REFERENCE`, so a session refuses this config for a real animal, and every
*fluid* number is a deliberately implausible placeholder. This file differs from that
one in exactly one entry and exists for exactly one reason.

**Why it exists.** `reference_bounds.py`'s `out_of_cage` ceiling is ten minutes -- a
placeholder, and **shorter than `welfare.CONFIRM_MARK_WITHIN`**, which is thirty. So
the confirmation band a departure more than thirty minutes old has to sit in (PI,
2026-09-20) is *empty* there: the ceiling refuses such a departure before any
confirmation is offered. That is correct on both sides -- the threshold is his number
and is deliberately not derived from the ceiling -- but it meant **no config that
shipped with this repository could exercise the prompt at all**, so nobody could dry-run
the one welfare interaction an operator is asked to perform. Review found that; this
closes it.

    wlx run tasks/fixation_detection.py --bounds tasks/eight_hour_bounds.py \\
        --rig tests/_rig.py --view direct --allocation tasks/allocation.py \\
        --root /tmp/dry-run --session-id 2027-01-14_01 --subject REFERENCE \\
        --out-of-cage-at YYYY-MM-DDTHH:MM --delivered-today 0 --trials 2

Give the clock time about five hours before now, with its date. It has to be more than
`welfare.CONFIRM_MARK_WITHIN` ago, or nothing is asked, and less than the eight-hour
ceiling, or it is refused before anything is asked. Five hours sits well inside both
edges: the ceiling is three hours off, so the thirty-minute warning before it
(`welfare.WARN_WITHIN_DEFAULT`) does not appear either.

The dry run uses the tests' stand-in rig because `tasks/rig.py`'s direct view refuses
until the housings are measured.

**Eight hours is not a placeholder and is not this file inventing one.** It is the
institutional figure, as the PI corrected it on 2026-10-01: this file carried twelve,
the figure recorded from his ruling of 2026-09-19, until then. It is documented in S8
§5.2 item 4 and in `welfare.py`'s docstring, and `welfare.py` deliberately carries no
constant for it so that nothing can default to it.
Writing it into a *bounded config* is exactly where it belongs -- a subject's config is
what states a limit -- and the subject here is still `REFERENCE`, so this states it for
nobody.

**Every other number is still a placeholder**, and the fluid ones are the same
implausible values as next door. This is not a protocol, and no approved protocol figure
for reward volume or daily fluid exists in this repository.
"""

from wl_xcon.bounds import Bounds, Ceiling, Floor

BOUNDS = Bounds(
    subject="REFERENCE",
    ceilings={
        # Identical to `reference_bounds.py`: a placeholder value, and a **fault
        # bound** rather than a dose cap on the maximum (PI, 2026-09-19).
        "reward_correct": Ceiling(value=0.05, maximum=10.0, unit="mL"),
        # **The one entry that differs, and the whole reason this file exists.**
        # Eight hours, the institutional figure (PI, 2026-09-19, corrected from
        # twelve on 2026-10-01) -- a **protocol figure**, so it changes when the
        # protocol does. It is longer than `welfare.CONFIRM_MARK_WITHIN`, which is
        # what gives this config a confirmation band to dry-run in.
        "out_of_cage": Ceiling(value=28_800.0, maximum=28_800.0, unit="s"),
    },
    minima={
        # Still a placeholder, still implausible, still a floor rather than a
        # ceiling (PI, 2026-09-06).
        "daily_fluid": Floor(value=20.0, unit="mL"),
    },
)
