"""A complete `Telemetry` frame, at this build's `SCHEMA`, for the browser console's
tests (P4d-2b b1; schema 8's fields since b2a, schema 9's since direct view part 2, schema 10's since b3a,
schema 12's since session levels).

Imported by `test_health.py`, `test_web.py` and `test_serve.py` as
`from _frames import frame`; never collected, because its name does not start with
`test_`. Every field holds a value a test can find in rendered output, and every
field that may be `None` holds a number here, so a test that wants an absence asks
for it by name -- **except schema 8's `paused_at` and `scheduled_stop`**, whose
`None` is the ordinary running session (not paused, nothing scheduled), and whose
number would make every frame here a paused one. Schema 9's `half_ipd_cm` is `None` for
the same kind of reason: the frame is a direct-view session, which has none. Schema 10's `preflight` and
`question` are `None` for the ordinary frame, like `paused_at`. Schema 12's `performance` is
a running session's four levels, each level's counts distinct from every other's, and
`returned_at` is `None`, like `paused_at`: a running session's animal has not gone back.
"""

from __future__ import annotations

from dataclasses import replace

from wl_xcon.link import SCHEMA, Counts, Idle, ParamRow, Performance, Stranded, Telemetry
from wl_xcon.web import View


#: The PUB endpoint `view()` says this console reads, and the one `test_serve.py`'s hubs
#: are built with.
ENDPOINT = "tcp://127.0.0.1:5571"


def frame(**overrides) -> Telemetry:
    """A running rig session, forty trials in. Distinctive numbers: 5025 s out of the
    cage is `1:23:45`, 4321 s in session is `1:12:01`, the last reward was commanded
    at `1_700_000_000.0`, and the frame was read 41.5 s later -- so with `view()`'s half
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
        out_of_cage_limit_s=28_800.0,
        wall_at=1_700_000_041.5,
        last_reward_at=1_700_000_000.0,
        recent_outcomes=("correct", "no_fixation", "correct"),
        paused_at=None,
        scheduled_stop=None,
        controls=(),
        controls_dropped=0,
        view="direct",
        half_ipd_cm=None,
        run_index=0,
        service=False,
        preflight=None,
        question=None,
        offered_tasks=(),
        performance=Performance(
            session=Counts({"correct": 30, "no_fixation": 10}, 0),
            task=Counts({"correct": 20, "no_fixation": 5}, 0),
            run=Counts({"correct": 12, "no_fixation": 3}, 0),
            block=Counts({"correct": 4, "no_fixation": 1}, 0),
            task_name="fixation_detection",
            runs_of_task=2,
            run_in_session=3,
            block_in_session=27,
            block_type="near",
        ),
        returned_at=None,
    )
    return replace(base, **overrides) if overrides else base


def view(**overrides) -> View:
    """A box viewer, alone, half a second after the frame arrived -- forty-two seconds
    after `frame()`'s last reward -- with a derived rate of twelve trials a minute, on
    a console reading `ENDPOINT`. Since P4d-2b b2a it may write, as the box's own page
    may, and its console has the session's mark endpoint."""
    base = View(
        frame_age_s=0.5,
        stale_after_s=30.0,
        trials_per_min=12.0,
        on_box=True,
        lan_viewers=0,
        rejected=None,
        endpoint=ENDPOINT,
        can_write=True,
        can_mark=True,
    )
    return replace(base, **overrides) if overrides else base


def idle(**overrides) -> Idle:
    """`wlx taskd` with no session open: nothing stranded, nothing owed, two animals and
    one task to offer."""
    base = Idle(
        schema=SCHEMA,
        phase="idle",
        wall_at=1_700_000_041.5,
        stranded=(),
        question=None,
        refusals=(),
        refusals_dropped=0,
        animals=("A", "B"),
        offered_tasks=("fixation_detection.py",),
    )
    return replace(base, **overrides) if overrides else base
