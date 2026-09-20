"""A second reference bounded config, with the real twelve-hour duration ceiling.

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

    wlx run tasks/fixation_detection.py --bounds tasks/twelve_hour_bounds.py \\
        --root /tmp/dry-run --session-id 2027-01-14_01 --subject REFERENCE \\
        --out-of-cage-at 2027-01-14T06:00 --delivered-today 0 --trials 2

**Twelve hours is not a placeholder and is not this file inventing one.** It is the
institutional figure, documented in S8 §5.2 item 4 and in `welfare.py`'s docstring, and
`welfare.py` deliberately carries no constant for it so that nothing can default to it.
Writing it into a *bounded config* is exactly where it belongs -- a subject's config is
what states a limit -- and the subject here is still `REFERENCE`, so this states it for
nobody.

**Every other number is still a placeholder**, and the fluid ones are the same
implausible values as next door. This is not a protocol, and no approved protocol figure
for reward volume or daily fluid exists in this repository.
"""

from wl_expcontroller.bounds import Bounds, Ceiling, Floor

BOUNDS = Bounds(
    subject="REFERENCE",
    ceilings={
        # Identical to `reference_bounds.py`: a placeholder value, and a **fault
        # bound** rather than a dose cap on the maximum (PI, 2026-09-19).
        "reward_correct": Ceiling(value=0.05, maximum=10.0, unit="mL"),
        # **The one entry that differs, and the whole reason this file exists.**
        # Twelve hours, the institutional figure (PI, 2026-09-19) -- a **protocol
        # figure**, so it changes when the protocol does. It is longer than
        # `welfare.CONFIRM_MARK_WITHIN`, which is what gives this config a
        # confirmation band to dry-run in.
        "out_of_cage": Ceiling(value=43_200.0, maximum=43_200.0, unit="s"),
    },
    minima={
        # Still a placeholder, still implausible, still a floor rather than a
        # ceiling (PI, 2026-09-06).
        "daily_fluid": Floor(value=20.0, unit="mL"),
    },
)
