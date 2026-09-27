"""A complete schema-7 `Telemetry` frame for the browser console's tests (P4d-2b b1).

Imported by `test_health.py`, `test_web.py` and `test_serve.py` as
`from _frames import frame`; never collected, because its name does not start with
`test_`. Every field holds a value a test can find in rendered output, and every
field that may be `None` holds a number here, so a test that wants an absence asks
for it by name.
"""

from __future__ import annotations

from dataclasses import replace

from wl_expcontroller.link import SCHEMA, ParamRow, Telemetry
from wl_expcontroller.web import View


#: The PUB endpoint `view()` says this console reads, and the one `test_serve.py`'s hubs
#: are built with.
ENDPOINT = "tcp://127.0.0.1:5571"


def frame(**overrides) -> Telemetry:
    """A running rig session, forty trials in. Distinctive numbers: 5025 s out of the
    cage is `1:23:45`, 4321 s in session is `1:12:01`, the last reward was charged at
    `1_700_000_000.0`, and the frame was read 41.5 s later -- so with `view()`'s half
    a second in `wlx serve`'s hands, the strip reads the last reward `42 s` ago."""
    base = Telemetry(
        schema=SCHEMA,
        session_id="2027-01-14_01",
        subject="A",
        trial_index=40,
        block="session",
        stopped_because="",
        stop_kind=None,
        phase="running",
        fluid_session_ml=1.25,
        fluid_today_ml=61.25,
        shortfall_ml=188.75,
        out_of_cage_seconds=5025.0,
        chair_seconds=4000.0,
        deployment="rig_fixed",
        duration_warning=None,
        outcomes={"correct": 30, "no_fixation": 8, "fixation_break": 2},
        hangs=0,
        owed={"ecc 10": 18},
        staged=(),
        refusals=(),
        refusals_dropped=0,
        in_session_seconds=4321.0,
        task="tasks/fixation_detection.py",
        allocation="tasks/allocation.py",
        bounds_config="subjects/A/bounds.py",
        params=(
            ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
            ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
        ),
        floor_ml=250.0,
        out_of_cage_limit_s=43_200.0,
        wall_at=1_700_000_041.5,
        last_reward_at=1_700_000_000.0,
        recent_outcomes=("correct", "no_fixation", "correct"),
    )
    return replace(base, **overrides) if overrides else base


def view(**overrides) -> View:
    """A box viewer, alone, half a second after the frame arrived -- forty-two seconds
    after `frame()`'s last reward -- with a derived rate of twelve trials a minute, on
    a console reading `ENDPOINT`."""
    base = View(
        frame_age_s=0.5,
        stale_after_s=30.0,
        trials_per_min=12.0,
        on_box=True,
        lan_viewers=0,
        rejected=None,
        endpoint=ENDPOINT,
    )
    return replace(base, **overrides) if overrides else base
