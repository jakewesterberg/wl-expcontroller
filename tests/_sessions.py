"""A real `taskd.Session` on the simulators, for the tests of the code that works around
one -- `marks`, `preflight`, `stranded` -- without running a trial. Never collected: its
name does not start with `test_`."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from _rig import DIRECT
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.dio import Simulated as Card
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall these sessions read: this host's clock when the module loaded, so a time
#: typed from it (`typed`) names the same instant on this host's calendar.
WALL = time.time()


def bounds(subject: str = "A", out_of_cage: float = 43_200.0) -> Bounds:
    """A bounded config: a reward entry, the out-of-cage ceiling, the daily floor."""
    return Bounds(
        subject=subject,
        ceilings={
            "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
            "out_of_cage": Ceiling(value=out_of_cage, maximum=100_000.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )


def session(
    tmp_path, *, deployment: Deployment = Deployment.RIG_CHAIRED, out_of_cage: float = 43_200.0
) -> Session:
    """Built and not opened: nothing is on disk until a mark or `open()` writes it.
    Rig-chaired by default, so no head-fixation stands between a test and a return."""
    made = Session(
        SessionSpec(
            task="tasks/fixation_detection.py",
            allocation="tasks/allocation.py",
            root=tmp_path,
            session_id="2027-01-14_01",
            subject="A",
            trials=3,
            frame_period=1 / 240,
            seed=1,
            values={},
            bounds=bounds(out_of_cage=out_of_cage),
            already_delivered_today=0.0,
            deployment=deployment,
            geometry=DIRECT,
        ),
        card=Card(),
        pump=Pump(),
    )
    made.wall_clock = lambda: WALL
    return made


def typed(seconds_before: float) -> str:
    """A time as a person types it, with its date and zone: `seconds_before` `WALL`
    (negative is after it)."""
    return datetime.fromtimestamp(WALL - seconds_before).astimezone().isoformat(
        timespec="seconds"
    )


def whole_point_task(folder: Path) -> Path:
    """A task `check()` itself raises on, written into `folder` as `whole_point.py`: the
    reference task with its target window placed at a whole-point parameter (a legal
    form) and a fixation break its target could overlap. `check`'s overlap test
    unpacks the window's place as a pair and raises `TypeError` (XC-156, filed on main,
    not fixed here): what a pre-flight must turn into a fail rather than pass on."""
    text = Path("tasks/fixation_detection.py").read_text()
    for old, new in (
        ('            "target",\n            at=(P("target_position"), 0.0),',
         '            "target",\n            at=P("target_point"),'),
        ('        Param("target_position", unit="deg", low=-16.0, high=16.0),',
         '        Param("target_position", unit="deg", low=-16.0, high=16.0),\n'
         '        Param("target_point", unit="deg", choices=((10.0, 0.0), (-10.0, 0.0))),'),
        ('                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),',
         '                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),\n'
         '                On(Exited("fix"), Outcome.FIXATION_BREAK),'),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path = Path(folder) / "whole_point.py"
    path.write_text(text)
    return path
