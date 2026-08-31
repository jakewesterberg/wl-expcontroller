"""`taskd` — running a session end to end.

The pieces joined: a task loaded and checked, a world to run it against, the record
written as it goes. On a rig the world is hardware; here it is a behaviour agent.
**The loop cannot tell them apart** (S6 §6), which is the property that makes a
simulated session evidence about a real one rather than a rehearsal of it.

What this is not, yet: a daemon. There is no console link, no live parameter path,
no preflight. Those are P3's successors; this is the spine they attach to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from wl_expcontroller.check import check
from wl_expcontroller.cli import _load_allocation, _load_trial
from wl_expcontroller.record import SessionRecord
from wl_expcontroller.simulate import Census, Subject, run_session
from wl_expcontroller.task import Entered, Exited, Hold, SaccadeTo


@dataclass
class SessionSpec:
    """Everything a session needs before it starts.

    Deliberately a value: a session's inputs are the thing recorded in the config
    snapshot, so they exist as data before they exist as behaviour.
    """

    task: str
    allocation: str
    root: Path
    session_id: str
    subject: str
    trials: int
    frame_period: float
    seed: int
    values: dict
    hazards: dict = field(
        default_factory=lambda: {
            Entered: 0.20,
            Hold: 0.30,
            SaccadeTo: 0.15,
            Exited: 0.01,
        }
    )
    engagement: float = 0.85
    lapse: float = 0.004


@dataclass
class Session:
    spec: SessionSpec

    def run(self) -> Census:
        """Check, then run, then record. **In that order, and it is load-bearing.**

        A session that begins and *then* discovers the task is malformed has already
        put an animal in a chair. So the checks run before anything else happens, and
        a blocking finding stops the session rather than being reported alongside it.
        """
        trial = _load_trial(Path(self.spec.task))
        allocation = _load_allocation(
            Path(self.spec.allocation) if self.spec.allocation else None
        )

        findings = check(trial, allocation)
        blocking = [f for f in findings if f.blocking]
        if blocking:
            raise SystemExit(
                "task refused, session not started:\n"
                + "\n".join(f"  {f.code}: {f.detail}" for f in blocking)
            )

        record = SessionRecord.open(
            self.spec.root, self.spec.session_id, self.spec.subject
        )
        record.snapshot(
            layers={"session": self.spec.values},
            resolved=self.spec.values,
            versions={"task": self.spec.task, "allocation": self.spec.allocation},
        )
        try:
            return run_session(
                trial,
                Subject(
                    seed=self.spec.seed,
                    hazards=self.spec.hazards,
                    engagement=self.spec.engagement,
                    lapse=self.spec.lapse,
                ),
                trials=self.spec.trials,
                frame_period=self.spec.frame_period,
                values=self.spec.values,
                record=record,
            )
        finally:
            record.close()
