"""`wlx taskd` -- the rig service (P4d-2b spec §6.1).

One process on the rig PC, all day: idle until a console opens a session, then one
animal's session across as many runs as the operator starts, until its return to the cage
is recorded, and then idle again for the next animal. **All of one animal's welfare state
lives in one `taskd.Session`** (PI, 2026-09-29: "One always-on rig service"), which is
the shape S9a §7 drew; nothing carries from one session to the next.

Its commands are the link's -- `OpenSession`, `CheckRun`, `StartRun`, `EndSession` and
`ResumeSession` beside b2a's -- over the socket `wlx run --link` binds. **They are read
once per housekeeping pass while no run is in progress, and at each trial boundary during
one**, never per frame (the b3a-1 plan, decision 18). A run sees the link through `_Routed`:
**an `EndSession` during a run stops it**, and the session ends once the run has
returned; any other of the service's own commands during a run is refused, never kept
for later. **Every run is checked before it starts** (`_start`): its pre-flight taken
again, and S9a §10's rule asked of it -- fail blocks, an unknown proceeds only on a named
acknowledgement written into `runs.jsonl`. **A run's fault is contained** (decision 14):
published, written into its end row, said on stderr, and the session left open between
runs with its animal still out, so the return can be taken.

**After a crash, nothing new opens until the stranded session is ended or resumed** (spec
§6.1; XC-026). On start the service finds every session under `--root` with a departure
and no return (`stranded.find`), and while one exists it opens no session, for that
animal or any other, until an `EndSession` naming it records the return -- **or a
`ResumeSession` naming it resumes that same session from its record** (XC-026,
`_resume`), which is not a new one. A record that cannot carry a resume is refused one,
so its only recovery is its return.

**A confirm or an amend is taken only as the answer to a question this service posed**
(the b3a-1 review's Ruling 1, 2026-09-29; `_unasked`). The PI's rule for a far mark is a
warning the experimenter must click through (2026-09-20), and the wire cannot tell a
click-through from a confirm sent blind in the first request. So a far mark with no
answer puts a `Question` on the frame; an answer is taken while that question is pending,
for its mark, its session and the instant it asked about -- and, for a departure, the
animal, deployment and setup of the open it was asked about; and **the question stays
until it is answered or another replaces it**, so a refused answer -- an amendment with
no reason -- can be corrected and sent again without the warning being lost.

**Every mark is taken on one thread** (the b3a-1 review's Ruling 2): the departure, its
amendment, the head's fixation and release and the return are each taken while a command
is routed, on the thread running `serve`, one command at a time -- which is what lets
`taskd.Session.returned_to_cage` run without the lock it once had.

**Welfare-critical: `Service._open`, `Service._end` (with `Service._unended`, its
refusals before anything is stopped or marked), `Service._close_stranded`,
`Service._start`, `_unasked` and `_folder_name`** (`docs/design/architecture.md`): the
page's route into the two marks, the stranded rule, which answers are taken, the gate a
run passes before it starts, and the rule that keeps a name from any wire or record from
becoming a path out of `--subjects` or `--tasks`. The rest is ordinary.

**The simulators, today**: the card, the pump and the animal are `wlx run`'s, because no
hardware port exists (docs/CHECKPOINT.md: nothing has touched hardware); a rig's own
replace them when they do.
"""

from __future__ import annotations

import argparse
import dataclasses
import gc
import re
import secrets
import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from wl_xcon import link as _link
from wl_xcon import marks as _marks
from wl_xcon import preflight as _preflight
from wl_xcon import resume as _resume_mod
from wl_xcon import stranded as _stranded
from wl_xcon.bounds import Bounds, Exceeded
from wl_xcon.cli import _load_allocation, _load_bounds, _load_rig, _load_subject_settings
from wl_xcon.codes import Allocation
from wl_xcon.dio import Simulated as SimulatedCard
from wl_xcon.geometry import Rig
from wl_xcon.record import XCON_DIRNAME
from wl_xcon.taskd import RunSpec, Session, SessionSpec, bounds_record
from wl_xcon.welfare import OUT_OF_CAGE, Deployment, SessionClock
from wl_xcon.welfare import Simulated as SimulatedPump

#: Seconds between housekeeping passes while no run is in progress: one frame published,
#: the link drained, a mark stamped. The wait ends early when a command or a mark
#: arrives. **A display cadence, not a measurement** -- `await_return`'s own, and well
#: inside `ZmqConsole`'s 5 s receive timeout.
HOUSEKEEPING_S = 1.0

#: The framework events every session here strobes on paths any session can reach:
#: head-fixation at open, its release at the end, an applied setting, and each run's
#: start and end (the b3a-1 plan, decision 12).
FRAMEWORK_CODES = ("HEAD_FIXED", "HEAD_RELEASED", "PARAM_CHANGED", "RUN_START", "RUN_END")

#: The frame period every session here runs at: `wlx run`'s own (`cli.main`).
FRAME_PERIOD = 1 / 240

#: One folder name (the b3a-1 plan, decision 19): a session id, an animal or a task
#: file, each of which becomes a path. Letters, digits, `_`, `.` and `-`, starting with
#: a letter or digit -- so never `.`, `..`, or anything with a separator.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def _folder_name(name: str) -> bool:
    """**Welfare-critical** (fix round 1 of Task 7). Whether `name` is one folder name
    (`_NAME`, and no `..`): the one rule for a session id and an animal arriving over the
    wire, for the animals the idle frame offers, and for a stranded record's animal,
    whose `bounds.py` is code this service runs -- so a name that is not one never
    becomes a path, and nothing outside `--subjects` runs for it."""
    return _NAME.fullmatch(name) is not None and ".." not in name


def _fresh_seed() -> int:
    """A run's seed, drawn here and written into its start row (the b3a-1 plan,
    decision 15), so the run can be replayed."""
    return secrets.randbelow(2**31)


def _sentence(refused: BaseException) -> str:
    """What a refusal says: a `SystemExit`'s message, or the exception's own."""
    return str(refused.code if isinstance(refused, SystemExit) else refused)


def _local(at: float) -> str:
    """An instant as this host's local date and time, to the second, with its zone."""
    return time.strftime("%Y-%m-%d %H:%M:%S (%Z)", time.localtime(at))


def _unasked(
    question: _link.Question | None,
    mark: str,
    session_id: str,
    text: str | None,
    now: Callable[[], float] | None = None,
    posed_for: tuple = (),
    sent_for: tuple = (),
) -> str | None:
    """**Welfare-critical** (the b3a-1 review's Ruling 1). Why an answer sent with the
    time `text` -- a page's *confirm*, or a departure's *amend* -- is not the answer to
    the question this service posed, or `None` when it is: the question pending, for
    this `mark`, this session, and the instant `text` is read as by the parser
    `marks.page_departure` and `marks.page_return` read it with (`now` for a return,
    which may be typed `now`) -- **and for what the question was posed for**
    (`posed_for`, against the answer's `sent_for`; fix round 1 of Task 7): a departure's
    warning names one animal and was asked about one open, so its animal, deployment and
    setup must be the answer's too. A return's question is bound by its session alone,
    which fixes all three.

    **PI, 2026-09-20:** a far mark is *"a warning ... that the experimenter must click
    through to confirm"*. A console learns of the warning only from the `Question` on a
    frame, and nothing on the wire tells a confirm clicked on it from one sent blind in
    the first request, so an answer is taken only while its question is pending -- and
    only for the instant it asked about, since a confirm of another time, or of another
    session's mark, is a confirm of something no warning was shown for. Refused before
    anything is built or marked."""
    at = None
    if text is not None:
        try:
            at = _marks._page_time(text, now)
        except argparse.ArgumentTypeError as bad:
            return str(bad)
    if question is not None and (question.mark, question.session_id) == (mark, session_id):
        if question.at == at and posed_for == sent_for:
            return None
        if question.at == at:
            return (
                f"the warning shown was for session {session_id}'s {mark} of "
                f"{', '.join(map(repr, posed_for))}, and this {mark} is of "
                f"{', '.join(map(repr, sent_for))}; an answer is taken only for what it "
                f"was asked about, so it is refused and nothing was recorded. Send it "
                f"without an answer, and answer the warning shown for it"
            )
        return (
            f"the warning shown was for session {session_id}'s {mark} at "
            f"{_local(question.at)}, and this {mark} is "
            f"{'given no time' if at is None else 'at ' + _local(at)}; an answer is taken "
            f"only for the time it was asked about, so it is refused and nothing was "
            f"recorded. Send the time without an answer, and answer the warning shown "
            f"for it"
        )
    answer = "a confirmation or an amendment" if mark == "departure" else "a confirmation"
    return (
        f"{answer} answers the warning a far {mark} is shown with, and none is owed for "
        f"session {session_id}'s {mark}, so it is refused and nothing was recorded: the "
        f"warning is one the experimenter clicks through (PI, 2026-09-20). Send the time "
        f"without an answer, and answer the warning if one is shown"
    )


def _unfinished(names: tuple[str, ...], broken: BaseException) -> tuple:
    """A fail for each of `names`, the pre-flight items whose check raised `broken`."""
    return tuple(
        _link.PreflightItem(
            name,
            _preflight.FAIL,
            f"this item's check did not finish: {type(broken).__name__}: {broken}",
        )
        for name in names
    )


def _contained(names: tuple[str, ...], build: Callable[[], object]) -> tuple:
    """The items `build` returns -- one, or a list -- or, if it raises, a fail for each
    of `names` (`Service._preflight`)."""
    try:
        built = build()
    except Exception as broken:  # noqa: BLE001 -- `Service._preflight`'s docstring
        return _unfinished(names, broken)
    return tuple(built) if isinstance(built, list) else (built,)


#: What `Service._built` returns: whatever the build it is given returns.
_Built = TypeVar("_Built")

#: The service's own commands: taken between runs, never handed to a run.
_SERVICE_COMMANDS = (
    _link.OpenSession, _link.CheckRun, _link.StartRun, _link.EndSession, _link.ResumeSession,
)


class _Routed:
    """The link a service session drains through (the b3a-1 plan, decision 18): the
    service's own link, with the service's commands taken out of what a run sees.

    **An `EndSession` during a run stops it** -- a `Stop` in its place, at the boundary
    that drained it -- and is kept for the service to finish once the run has returned
    (`Service.step`), since `Service._end` is for a session between runs or awaiting
    its return. One `_end` would refuse before anything is marked (`Service._unended`)
    is refused here instead, before anything is stopped. Any other service command
    during a run is refused on the session's feed: a run is in progress. **Everything
    else is the real link's**: `mark_signal` and `idle` are the link's own bound
    methods, so the per-frame mark check is the call V12 measured, with nothing added.
    `publish`, once per trial boundary and never per frame, is the link's too, and also
    keeps the frame a session closes with for the idle frames that follow
    (`Service.closed`)."""

    def __init__(self, link, service: "Service") -> None:
        self._link = link
        self._service = service
        self.mark_signal = link.mark_signal
        self.idle = link.idle

    def publish(self, frame) -> None:
        """The real link's `publish`; and a `closed` frame -- the one `Session.close`
        publishes as the return is recorded -- kept as the service's `closed`, since the
        same pass drops the session and every frame after it is idle (the b3a-2 final
        review, I2). Kept here rather than in `Service._end`, which is welfare-critical and
        unchanged, and without a reference to the session, which `_end` collects."""
        self._link.publish(frame)
        if frame.phase == "closed":
            self._service.closed = frame

    @property
    def refused(self):
        return self._link.refused

    @property
    def refused_dropped(self) -> int:
        return self._link.refused_dropped

    def drain(self) -> list:
        """At a trial boundary, or a paused run's housekeeping pass: the commands a run
        takes, with the service's own taken out."""
        service, kept = self._service, []
        for command in self._link.drain():
            if isinstance(command, _link.EndSession) and service._ending is None:
                why = service._unended(command)
                if why is not None:
                    service.session.refuse(command.KIND, command.by, why)
                    continue
                service._ending = command
                kept.append(_link.Stop(by=command.by))
            elif isinstance(command, _SERVICE_COMMANDS):
                service.session.refuse(
                    command.KIND,
                    command.by,
                    "a run is in progress, so this is refused rather than kept for later; "
                    "send it again once the run has ended",
                )
            else:
                kept.append(command)
        return kept


class Service:
    """`wlx taskd`'s state and loop: the link, the open session if any, the stranded
    sessions, and the question and refusals an idle frame carries."""

    def __init__(
        self,
        *,
        rig: Rig,
        rig_path: str,
        subjects: Path,
        tasks: Path,
        allocation: Allocation,
        allocation_path: str,
        root: Path,
        link,
        card: Callable[[], object] = SimulatedCard,
        pump: Callable[[], object] = SimulatedPump,
        seed: Callable[[], int] = _fresh_seed,
        wall_clock: Callable[[], float] | None = None,
    ) -> None:
        missing = [
            name for name in FRAMEWORK_CODES if name not in allocation.task_events.values()
        ]
        if missing:
            raise SystemExit(
                f"refused: the allocation "
                f"{allocation_path or '(none given, so the provisional one)'} has no "
                f"{', '.join(missing)} event code; every session wlx taskd runs strobes "
                f"each, so give --allocation with them all"
            )
        self.rig, self.rig_path = rig, rig_path
        self.subjects, self.tasks, self.root = Path(subjects), Path(tasks), Path(root)
        self.allocation, self.allocation_path = allocation, allocation_path
        self.link = link
        self._card, self._pump, self._seed = card, pump, seed
        #: Injected by a test; otherwise the service's own anchored wall.
        self.wall_clock = wall_clock
        self._clock = SessionClock()
        self.session: Session | None = None
        self.stranded: list = _stranded.find(self.root)
        #: A departure, or a stranded session's return, a console owes an answer on:
        #: kept until it is answered or another replaces it (`_unasked`).
        self.question: _link.Question | None = None
        #: What a departure's `question` was posed for -- the animal, deployment and
        #: setup of its open (fix round 1 of Task 7). **Set whenever a departure question
        #: is posed, and read only beside one** (`_open`), so it is never cleared; a
        #: stranded return's question is bound by its session alone.
        self._posed_for: tuple = ()
        #: The service's own refusals while no session is open, capped as a session's.
        self.refusals: list = []
        self.refusals_dropped = 0
        #: **The last closed session's final frame** (the b3a-2 final review, I2; spec
        #: §6.2: "The session then closes and the page shows its summary"), for the idle
        #: frames until the next session opens (`Idle.closed`). Set as the session
        #: publishes its `closed` frame (`_Routed.publish`), cleared as the next opens
        #: (`_route`).
        self.closed: _link.Telemetry | None = None
        #: The service's runs (the b3a-1 plan, decision 18): a run `_start` accepted
        #: this pass and not started, `(RunSpec, rows, by)`; and an `EndSession` that
        #: arrived during a run (`_Routed`), finished once the run returns (`step`).
        self._starting = None
        self._ending = None

    def wall_now(self) -> float:
        """The service's wall: a test's, or its own `SessionClock`, anchored once."""
        return self.wall_clock() if self.wall_clock is not None else self._clock.now()

    # --- the loop -----------------------------------------------------------------

    def serve(self, stop: threading.Event) -> None:
        """Pass after pass until `stop` is set: `wlx taskd`'s loop, and the one thread
        every mark is taken on. `stop` is read between passes."""
        while not stop.is_set():
            self.step()

    def step(self) -> None:
        """One housekeeping pass: wait for a console (up to `HOUSEKEEPING_S`), stamp a
        mark, take every command waiting, publish one frame -- and then run a run
        accepted in this pass, finishing an `EndSession` that arrived during it."""
        mark = self.link.idle(HOUSEKEEPING_S)
        if mark:
            self._mark(mark)
        for command in self.link.drain():
            self._route(command)
        self.publish()
        if self._starting is None:
            return
        run, rows, by = self._starting
        self._starting = None
        self._run(run, rows, by)
        if self._ending is not None:
            ending, self._ending = self._ending, None
            self._end(ending)
        self.publish()

    def publish(self) -> None:
        """The open session's frame, or an idle one."""
        if self.session is not None:
            self.session.offered_tasks = self._tasks()
            self.session.publish()
            return
        self.link.publish(
            _link.Idle.of(
                wall_at=self.wall_now(),
                stranded=self.stranded,
                question=self.question,
                refusals=self.refusals,
                refusals_dropped=self.refusals_dropped,
                link=self.link,
                animals=self._animals(),
                offered_tasks=self._tasks(),
                closed=self.closed,
            )
        )

    def shutdown(self, why: str = "wlx taskd stopped with the session open") -> None:
        """The process is stopping -- Ctrl-C at `wlx taskd`'s terminal, or a fault out of
        its loop (`run`) -- so a session still open is recorded as ended without its
        return, saying `why`, and its clock closed. The next start finds it stranded
        (`stranded.find`), which is what makes it safe to stop rather than wait."""
        session, self.session = self.session, None
        if session is None:
            return
        if (
            session.welfare.left_cage_wall_at is not None
            and session.welfare.returned_wall_at is None
        ):
            session.return_not_recorded(why, how="wlx taskd")
        if session.opened_wall_at is not None and session.ended_wall_at is None:
            session.end(how="wlx taskd")

    # --- commands -----------------------------------------------------------------

    def _route(self, command) -> None:
        if isinstance(command, _link.OpenSession):
            idle = self.session is None
            self._open(command)
            if idle and self.session is not None:
                # **The idle feed starts afresh with each session** (the b3a-1 final
                # review, Minor 7): its refusals were about the time before this one --
                # "send it again answering confirm" among them -- and shown again once
                # the session closed, they would read as pending. While it is open,
                # refusals go to its own feed (`_refuse`). **And the End tab's summary is
                # replaced by this session's** (the b3a-2 final review, I2).
                self.refusals.clear()
                self.refusals_dropped = 0
                self.closed = None
        elif isinstance(command, _link.EndSession):
            self._end(command)
        elif isinstance(command, _link.CheckRun):
            self._check(command)
        elif isinstance(command, _link.StartRun):
            self._start(command)
        elif isinstance(command, _link.ResumeSession):
            idle = self.session is None
            self._resume(command)
            if idle and self.session is not None:
                # As for an open: the idle feed and the last summary were about before.
                self.refusals.clear()
                self.refusals_dropped = 0
                self.closed = None
        elif self.session is not None:
            self.session.receive(command)
        elif isinstance(command, _link.ManualReward):
            # Spec §6.0: with no session open the button flushes the line, counted to no
            # animal -- a slice of its own (XC-158). Until then, refused as a reward.
            self._refuse(
                "reward",
                command.by,
                "no session is open, so no reward was given: a reward with no session "
                "open, which flushes the line, waits on XC-158",
            )
        else:
            self._refuse(
                command.name if isinstance(command, _link.SetParameter) else command.KIND,
                command.by,
                "no session is open, so a command for a run is not applied; open a "
                "session first",
            )

    def _refuse(self, name: str, by: str, why: str) -> None:
        """Onto the open session's feed, or, with none open, the idle frame's."""
        if self.session is not None:
            self.session.refuse(name, by, why)
            return
        self.refusals.append(_link.Refused(name=name, by=by, why=why))
        if len(self.refusals) > _link.REFUSAL_HISTORY:
            self.refusals_dropped += len(self.refusals) - _link.REFUSAL_HISTORY
            del self.refusals[: -_link.REFUSAL_HISTORY]

    def _mark(self, mark: int) -> None:
        """A mark signal with no run checking for one: stamped into the open session, or
        refused while idle, since it belongs to no session (the b3a-1 plan, decision 16)."""
        if self.session is not None:
            self.session.stamp(mark)
        else:
            self._refuse("mark", "<unknown>", "no session is open, so the mark was not recorded")

    def _animals(self) -> tuple[str, ...]:
        """The animals a session may be opened for: folders under `--subjects` holding a
        bounded config, **named as an open accepts** (`_folder_name`; fix round 1 of Task
        7), so the idle frame never offers an animal every open would refuse."""
        if not self.subjects.is_dir():
            return ()
        return tuple(
            sorted(
                p.name
                for p in self.subjects.iterdir()
                if _folder_name(p.name) and (p / "bounds.py").is_file()
            )
        )

    def _tasks(self) -> tuple[str, ...]:
        """The task files a run may use: `*.py` under `--tasks`, **named as a run
        accepts** (`_folder_name`, which also leaves out a `_`-prefixed module), so a
        frame never offers a task every run would refuse (`_task`)."""
        if not self.tasks.is_dir():
            return ()
        return tuple(sorted(p.name for p in self.tasks.glob("*.py") if _folder_name(p.name)))

    # --- opening --------------------------------------------------------------------

    def _session_for(self, command: _link.OpenSession) -> Session:
        """The session an `OpenSession` asks for, built and **not opened**: nothing is
        written. Raises `SystemExit`, `ValueError` or `Exceeded` with the sentence a
        refusal says."""
        for what, name in (("session id", command.session_id), ("animal", command.animal)):
            if not _folder_name(name):
                raise ValueError(
                    f"a {what} is one folder name -- letters, digits, '_', '.' and '-', "
                    f"starting with a letter or digit -- and {name!r} is not one"
                )
        if (self.root / command.session_id).exists():
            raise ValueError(
                f"session id {command.session_id!r} is already used under {self.root}; "
                f"every session has its own"
            )
        session, _bounds = self._build(
            session_id=command.session_id, animal=command.animal,
            deployment=command.deployment, view=command.view,
            delivered_today=command.delivered_today,
        )
        return session

    def _build(
        self,
        *,
        session_id: str,
        animal: str,
        deployment: str,
        view: str,
        delivered_today: float | None,
    ) -> tuple[Session, Bounds]:
        """A session for `animal`, built from its files under `--subjects` and **not
        opened**: nothing is written. Returned with the bounds it loaded, which a resume
        compares with its record's (`_resume`). Raises `SystemExit`, `ValueError` or
        `Exceeded` with the sentence a refusal says.

        **The animal is held to `_folder_name` before any path is built** (XC-026): an
        open has already checked it (`_session_for`), and a resume's comes from a record
        -- `config.json`'s subject, which `wlx run --subject` takes as any text -- so a
        `../outside` or an absolute path never makes a `bounds.py` outside `--subjects`
        the code that runs, as `_close_stranded` refuses one."""
        if not _folder_name(animal):
            raise ValueError(
                f"an animal is one folder name -- letters, digits, '_', '.' and '-', "
                f"starting with a letter or digit -- and {animal!r} is not one"
            )
        folder = self.subjects / animal
        bounds_path = folder / "bounds.py"
        if not bounds_path.is_file():
            raise ValueError(f"there is no animal {animal!r}: {bounds_path} does not exist")
        bounds = _load_bounds(bounds_path)
        if bounds.subject != animal:
            raise ValueError(
                f"{bounds_path} holds {bounds.subject!r}'s bounded config, and this folder "
                f"is {animal!r}'s; ceilings belong to an animal"
            )
        settings_path = None
        if view == "direct":
            geometry = self.rig.direct()
        else:
            settings_path = folder / "settings.py"
            if not settings_path.is_file():
                raise ValueError(
                    f"the stereoscope needs {animal!r}'s settings, and "
                    f"{settings_path} does not exist"
                )
            geometry = self.rig.stereoscope(
                _load_subject_settings(settings_path, animal).half_ipd_cm
            )
        session = Session(
            SessionSpec(
                task="",
                allocation=self.allocation_path,
                root=self.root,
                session_id=session_id,
                subject=animal,
                trials=0,
                frame_period=FRAME_PERIOD,
                seed=0,
                values={},
                bounds=bounds,
                already_delivered_today=delivered_today,
                deployment=Deployment(deployment),
                geometry=geometry,
                bounds_config=str(bounds_path),
                rig_config=self.rig_path,
                subject_settings="" if settings_path is None else str(settings_path),
            ),
            card=self._card(),
            pump=self._pump(),
            link=_Routed(self.link, self),
            service=True,
            wall_clock=self.wall_clock,
        )
        return session, bounds

    def _built(self, kind: str, by: str, build: Callable[[], _Built]) -> _Built | None:
        """What `build` returns -- a session built and not opened, for an open or a
        resume -- or `None`, refused under `kind`, saying why: a `SystemExit`,
        `ValueError`, `TypeError` or `Exceeded` with its own sentence, and anything else
        named, since the animal's files are code and a broken one is never the
        service's end. **The one handler `_open` and `_resume` share** (review fix
        round 1 of XC-026 Task 4), so the two cannot drift."""
        try:
            return build()
        except (SystemExit, ValueError, TypeError, Exceeded) as refused:
            self._refuse(kind, by, _sentence(refused))
        except Exception as broken:  # noqa: BLE001 -- the animal's files are code
            self._refuse(
                kind, by,
                f"the session could not be built: {type(broken).__name__}: {broken}",
            )
        return None

    def _open(self, command: _link.OpenSession) -> None:
        """**Welfare-critical.** Open a session (P4d-2b spec §6.2): **none while one is
        open, and none for any animal while one is stranded** (§6.1); an answer taken
        only for the question posed (`_unasked`); then the departure through `marks`,
        the terminal's own rules; and **nothing written until it is accepted**, so a
        refused or unanswered departure leaves no folder and its id free (the b3a-1
        plan, decision 11). A far departure with no answer puts the question on the idle
        frame, with a refusal row saying what to send."""
        if self.session is not None:
            self._refuse(
                "open",
                command.by,
                f"a session is open for {self.session.spec.subject!r} "
                f"({self.session.spec.session_id}); end it, with its animal's return, "
                f"before another opens",
            )
            return
        if self.stranded:
            names = "; ".join(
                f"{found.subject or 'an unreadable record'} in session {found.session_id}"
                for found in self.stranded
            )
            self._refuse(
                "open",
                command.by,
                f"no session opens while an animal's return is not recorded: {names}. "
                f"Resume it, or record its return with End session, naming its session",
            )
            return
        # What a departure's question is posed for, beside its session and instant (fix
        # round 1 of Task 7): the animal its warning names, the deployment and the setup.
        asked_about = (command.animal, command.deployment, command.view)
        if command.answer is not None:
            unasked = _unasked(
                self.question, "departure", command.session_id, command.departure,
                posed_for=self._posed_for, sent_for=asked_about,
            )
            if unasked is not None:
                self._refuse("open", command.by, unasked)
                return
        session = self._built("open", command.by, lambda: self._session_for(command))
        if session is None:
            return
        try:
            decision = _marks.page_departure(
                session,
                departure=command.departure,
                answer=command.answer,
                amend_to=command.amend_to,
                amend_reason=command.amend_reason,
                by=command.by,
            )
            _marks.depart(session, decision)
        except _marks.Owed as owed:
            self.question = _link.Question(
                mark="departure",
                session_id=command.session_id,
                at=owed.at,
                said=owed.warning,
                answers=owed.answers,
            )
            self._posed_for = asked_about
            self._refuse(
                "open",
                command.by,
                f"{owed.warning}. Nothing was recorded: send it again answering "
                f"confirm, or amend with the corrected time, a reason and your name",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("open", command.by, str(refused))
            return
        # Marked: whatever was asked is answered, or moot now a session is open.
        self.question = None
        _marks.record_departure(session, decision)
        session.open(how="wlx taskd")
        if session.spec.deployment is Deployment.RIG_FIXED:
            session.head_fixed(session.wall_now())
        session.offered_tasks = self._tasks()
        self.session = session

    def _resume(self, command: _link.ResumeSession) -> None:
        """**Welfare-critical** (pending the PI's ruling on the list). A stranded session
        resumed (XC-026 spec §5): refused, saying why, while a session is open, for an id
        not stranded, when its record cannot give what a resume needs or names two
        animals, when its animal's bounds changed since it opened, or when the animal is
        past its out-of-cage limit on the recorded departure -- each **before anything is
        written** (plan ruling 6). Otherwise built as `_open` builds one (`_build`), from
        its record (`resume.read`), and resumed (`Session.resume`). Another session still
        stranded is no bar: each is resumed or ended on its own (spec §5; plan ruling 7).
        **A record it cannot carry is a refusal, never the service's end** (the
        controller's ruling on Task 4): what `stranded.restore` raises is said too, and
        what `Session.resume` refuses before it writes. **One refused for being past its
        limit is then marked not resumable**, with the refusal's sentence, so the page
        offers only *end* (spec §5; fix round 1 of Task 7); a stranded session marked
        not resumable, by this or by `stranded.find`, is refused with what it is marked."""
        if self.session is not None:
            self._refuse(command.KIND, command.by,
                         f"a session is open ({self.session.spec.session_id}); a stranded "
                         f"session is resumed only while none is")
            return
        found = next((s for s in self.stranded if s.session_id == command.session_id), None)
        if found is None or found.left_at is None:
            self._refuse(command.KIND, command.by,
                         f"no stranded session {command.session_id!r} can be resumed"
                         + ("" if found is None else f": {found.why}"))
            return
        if not found.resumable:
            # What the banner says of it, so the page and the refusal agree: its record
            # cannot carry a resume (`stranded.find`), or its animal is past its limit
            # (below). Neither is taken back while this service runs.
            self._refuse(command.KIND, command.by, found.why)
            return
        directory = self.root / found.session_id / XCON_DIRNAME
        try:
            restoration = _resume_mod.read(directory, found.left_at)
        except _resume_mod.Unresumable as refused:
            self._refuse(command.KIND, command.by, _sentence(refused))
            return
        if restoration.subject != found.subject:
            # `_build` loads bounds for `config.json`'s animal, and `stranded.restore`
            # holds them to the departure row's: one record, so one animal.
            self._refuse(command.KIND, command.by,
                         f"session {found.session_id}'s config.json names "
                         f"{restoration.subject!r} and its departure names {found.subject!r}; "
                         f"a record that disagrees with itself is not resumed, so end it instead")
            return
        built = self._built(command.KIND, command.by, lambda: self._build(
            session_id=found.session_id, animal=restoration.subject,
            deployment=restoration.deployment, view=restoration.view,
            delivered_today=restoration.already_today,
        ))
        if built is None:
            return
        session, bounds = built
        now_bounds = bounds_record(bounds)
        changed = sorted(
            name
            for kind in ("ceilings", "minima")
            for name in set(restoration.bounds_at_open[kind]) | set(now_bounds[kind])
            if restoration.bounds_at_open[kind].get(name) != now_bounds[kind].get(name)
        )
        if changed:
            self._refuse(command.KIND, command.by,
                         f"{restoration.subject!r}'s bounds changed since session "
                         f"{found.session_id} opened ({', '.join(changed)}); a session's "
                         f"limits do not change across a restart, so end it instead")
            return
        try:
            # **Against the limit the session had** (the final review's I2): one it lowered
            # is the one `Session.resume` restores, so it is the one this check reads, set
            # through `Bounds.set` on a copy, which holds it under the file's maximum.
            limits = dataclasses.replace(bounds, ceilings=dict(bounds.ceilings))
            if OUT_OF_CAGE in restoration.bounded:
                limits.set(OUT_OF_CAGE, restoration.bounded[OUT_OF_CAGE], by=command.by)
            stop = _stranded.restore(found, limits, directory, self.wall_now).welfare.must_stop(
                self.wall_now()
            )
        except Exceeded as refused:
            self._refuse(command.KIND, command.by, _sentence(refused))
            return
        if stop is not None:
            # **The page then asks for the return, and only end is offered** (spec §5;
            # fix round 1 of Task 7): the entry is marked so, with this sentence, and its
            # banner loses *resume session*. Past the limit only ever stays true, so the
            # mark is never wrong. Changed bounds stay a plain refusal: restoring the
            # animal's file makes the session resumable again.
            why = f"{stop}; record its return with End session instead"
            self.stranded[self.stranded.index(found)] = dataclasses.replace(
                found, resumable=False, why=why
            )
            self._refuse(command.KIND, command.by, why)
            return
        try:
            session.resume(restoration, by=command.by, how="wlx taskd")
        except (Exceeded, TypeError, ValueError) as refused:
            # Its welfare rules refuse a value from the record -- a reward size over its
            # maximum, a negative fluid, a size that is no number -- before its first
            # write (review fix round 1, Important 1).
            self._refuse(command.KIND, command.by, _sentence(refused))
            return
        session.offered_tasks = self._tasks()
        self.session = session
        # A return asked about it while it was stranded is moot now, as `_close_stranded`
        # leaves it (the final review's I4); another stranded session's question stays.
        if self.question is not None and self.question.session_id == found.session_id:
            self.question = None
        self.stranded.remove(found)

    # --- runs -----------------------------------------------------------------------

    def _between_runs(self, kind: str, by: str) -> Session | None:
        """The open session, when a run may be checked or started; otherwise refused,
        saying why."""
        if self.session is None:
            self._refuse(kind, by, "no session is open, so no run starts; open a session first")
            return None
        if self.session.phase != "between_runs":
            self._refuse(
                kind, by,
                "the session has ended and waits for its animal's return, so no run starts",
            )
            return None
        if self._starting is not None:
            self._refuse(kind, by, "a run is already starting, so this is refused")
            return None
        return self.session

    def _task(self, name: str, kind: str, by: str) -> Path | None:
        """A task file under `--tasks`, named by one file name ending `.py`; refused
        otherwise. **The name is held to `_folder_name` before any path is built**
        (carried from Task 7): it arrives over the wire, and the file it names is code
        the pre-flight and the run load, so a parent reference or an absolute path would
        run a file from outside `--tasks`."""
        if not (_folder_name(name) and name.endswith(".py")):
            self._refuse(
                kind, by,
                f"{name!r} is not a task file under {self.tasks}: a task is named by one "
                f"file name ending .py -- letters, digits, '_', '.' and '-', starting with "
                f"a letter or digit -- so nothing was loaded",
            )
            return None
        path = self.tasks / name
        if not path.is_file():
            self._refuse(
                kind, by, f"{name!r} is not a task file under {self.tasks}, so nothing was loaded"
            )
            return None
        return path

    def _preflight(self, session: Session, task: Path, values: dict) -> _link.Preflight:
        """Spec §6.2's items, taken now, in order -- the out-of-cage item always among
        them, since `preflight.gate` refuses a pre-flight without it.

        **Whatever raises while one item is checked is that item's fail** (the b3a-1
        final review's ruling), under the item's own name, and the other items are
        still taken: a check or a start never ends the service through its pre-flight,
        whatever item a later change adds. The out-of-cage item keeps its name when its
        own check raises, so the gate blocks on its fail, never on its absence."""
        settings = Path(session.spec.subject_settings) if session.spec.subject_settings else None
        try:
            item, trial = _preflight.task(task, self.allocation, session.spec.geometry)
            checked = (item,)
        except Exception as broken:  # noqa: BLE001 -- see the docstring
            checked, trial = _unfinished((_preflight.TASK_CHECKS,), broken), None
        return _link.Preflight(
            task=task.name,
            items=(
                *checked,
                *_contained(
                    (_preflight.STARTING_VALUES,), lambda: _preflight.values(trial, values)
                ),
                *_contained(
                    (_preflight.BOUNDED_CONFIG,)
                    + (() if settings is None else (_preflight.SUBJECT_SETTINGS,)),
                    lambda: _preflight.files(
                        Path(session.spec.bounds_config), session.spec.subject, settings,
                        self.rig,
                    ),
                ),
                *_contained(
                    (_preflight.OUT_OF_CAGE_MARK,), lambda: _preflight.out_of_cage(session)
                ),
                *_contained(
                    (_preflight.PUMP_CALIBRATION, _preflight.EYE_TRACKER),
                    lambda: _preflight.unmeasured(session.pump),
                ),
            ),
        )

    def _check(self, command: _link.CheckRun) -> None:
        """Take a run's pre-flight and put it on the frame, starting nothing."""
        session = self._between_runs("check", command.by)
        if session is None:
            return
        task = self._task(command.task, "check", command.by)
        if task is not None:
            session.preflight = self._preflight(session, task, command.values)

    def _start(self, command: _link.StartRun) -> None:
        """**Welfare-critical.** Accept a run (spec §6.2): the pre-flight **taken now**,
        never trusted from an earlier check, and S9a §10's rule asked of it with the
        items this person acknowledged by name (`preflight.gate`); only then is the run
        kept to start once this pass has published, with a seed drawn for it and the
        pre-flight as its start row records it -- who acknowledged each unknown
        (`preflight.rows`). Its block plan and conditions come from the task program or
        are chosen at the rig, and until either exists (XC-207) a run is one block.

        **A run past the out-of-cage limit is refused here, before `RUN_START`**
        (carried from Task 3): `Session.run` refuses none -- `welfare.preflight` checks no
        ceiling -- so it would strobe the start and write its row before `_ends` stopped
        it. The pre-flight's out-of-cage item fails once `welfare.must_stop` fires, and
        a fail blocks whatever is acknowledged."""
        session = self._between_runs("start", command.by)
        if session is None:
            return
        task = self._task(command.task, "start", command.by)
        if task is None:
            return
        checked = self._preflight(session, task, command.values)
        session.preflight = checked
        why = _preflight.gate(checked, command.acknowledged)
        if why is not None:
            self._refuse("start", command.by, why)
            return
        self._starting = (
            RunSpec(
                task=str(task),
                trials=command.trials,
                seed=self._seed(),
                values=dict(command.values),
            ),
            _preflight.rows(checked, command.by, command.acknowledged),
            command.by,
        )

    def _run(self, run: RunSpec, rows: list, by: str) -> None:
        """The run, to its end. **Its two backstop refusals** (`Session.run`'s blocking
        finding and `welfare.preflight`), raised before it starts, are refusals here.
        **Anything else is a fault, and contained** (the b3a-1 plan, decision 14): one
        raised once the run started -- `Exceeded` from a delivery `welfare` would not
        make among them -- `run()` has published and written into the run's end row;
        the session is back between runs with the animal still out, and the traceback
        goes to this process's stderr; the service goes on, so the return can be taken.
        **One raised before the run started** (fix round 1 of Task 8) -- a task edited to
        fail between its pre-flight and its run -- goes to stderr too, and is a start
        refusal on the feed, so a page shows why no run started. Ctrl-C is not caught:
        `wlx taskd` ends on it."""
        session = self.session
        before = session.run_index
        try:
            session.run(run, preflight_rows=rows, by=by)
        except (SystemExit, Exception) as ended:  # noqa: BLE001 -- see the docstring
            if session.run_index != before:
                traceback.print_exc(file=sys.stderr)
            elif isinstance(ended, (SystemExit, Exceeded)):
                session.refuse("start", by, _sentence(ended))
            else:
                traceback.print_exc(file=sys.stderr)
                session.refuse(
                    "start", by, f"the run did not start: {type(ended).__name__}: {ended}"
                )

    # --- ending ---------------------------------------------------------------------

    def _end(self, command: _link.EndSession) -> None:
        """**Welfare-critical.** End the open session (P4d-2b spec §6.2): refused before
        anything is marked when it names another session or answers a question nobody
        was asked (`_unended`); a run accepted in this pass does not start; then its
        runs end and its head is released (`Session.end_runs`, the b3a-1 plan, decision
        6), then its return is taken through `marks`, the terminal's rules -- or, given
        no return, it waits for one. With none open, the stranded session it names.

        **Never during a run**: one sent then stops the run (`_Routed`) and is finished
        here once the run has returned (`step`), so the session is between runs or
        awaiting its return whenever this runs."""
        if self.session is None:
            self._close_stranded(command)
            return
        session = self.session
        unended = self._unended(command)
        if unended is not None:
            self._refuse("end", command.by, unended)
            return
        if self._starting is not None:
            self._starting = None
            self._refuse(
                "start", command.by,
                "the session was ended in the same pass, so the run does not start",
            )
        if session.phase == "between_runs":
            session.end_runs(command.by)
        if command.returned is None:
            return
        try:
            _marks.page_return(
                session, returned=command.returned, confirm=command.confirm, by=command.by
            )
        except _marks.Owed as owed:
            session.question = _link.Question(
                mark="return",
                session_id=session.spec.session_id,
                at=owed.at,
                said=owed.warning,
                answers=owed.answers,
            )
            self._refuse(
                "end",
                command.by,
                f"{owed.warning}. Send it again answering confirm, or with the time "
                f"typed again",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("end", command.by, str(refused))
            return
        session.close(how="wlx taskd")
        self.session = None
        # The session is a reference cycle (`welfare.Rig`'s docstring): collected here,
        # between sessions, never during a run (the b3a-1 plan, decision 17). **The
        # local goes first**: a collection with it still held frees nothing, and the
        # cycle would wait for an automatic one that could land in the next run.
        del session
        gc.collect()

    def _unended(self, command: _link.EndSession) -> str | None:
        """**Welfare-critical, as `_end`'s first step.** Why an `EndSession` ends nothing
        of the open session, or `None`: it names another session, or it confirms a
        return nobody was asked about (`_unasked`). Asked by `_end`, before anything is
        marked, and by `_Routed` during a run, before anything is stopped -- one rule
        for both, so an End refused before anything is marked never stops this animal's
        run. An End whose return time `_end` refuses later -- one it cannot read, or a
        far one sent unconfirmed, which poses a question -- has stopped the run by then,
        as between runs it has ended them."""
        session = self.session
        if command.session_id not in (None, session.spec.session_id):
            return (
                f"the session open is {session.spec.session_id}, not "
                f"{command.session_id}; nothing was ended"
            )
        if command.confirm is not False:
            return _unasked(
                session.question, "return", session.spec.session_id, command.returned,
                session.wall_now,
            )
        return None

    def _close_stranded(self, command: _link.EndSession) -> None:
        """**Welfare-critical.** A stranded session's return (spec §6.1), checked against
        its recorded departure under `welfare`'s rules (`stranded.restore`), written into
        its own record; a confirm taken only for the question posed (`_unasked`).
        Refused while its record cannot be read or its animal's bounded config is gone
        or will not load -- each with what to do."""
        found = next(
            (s for s in self.stranded if s.session_id == command.session_id), None
        )
        if found is None:
            self._refuse(
                "end",
                command.by,
                "no session is open"
                + (
                    f", and no stranded session is {command.session_id!r}"
                    if command.session_id
                    else "; to record a stranded animal's return, name its session"
                )
                + "; nothing was ended",
            )
            return
        if command.returned is None:
            self._refuse(
                "end", command.by,
                f"give the time {found.subject or 'the animal'} went back into its home cage",
            )
            return
        if command.confirm is not False:
            unasked = _unasked(
                self.question, "return", found.session_id, command.returned, self.wall_now
            )
            if unasked is not None:
                self._refuse("end", command.by, unasked)
                return
        bounds = None
        if found.left_at is not None:
            # **Before any path is built** (fix round 1 of Task 7): the subject is the
            # record's, and `wlx run --subject` takes any text, so `../outside` or an
            # absolute path would make a `bounds.py` outside `--subjects` the code that
            # runs next. An open's own rule, `_folder_name`, applies to it.
            if not _folder_name(found.subject):
                self._refuse(
                    "end",
                    command.by,
                    f"session {found.session_id}'s record names no animal folder: its "
                    f"animal is {found.subject!r}, which is not one folder name under "
                    f"--subjects, so no bounded config is loaded for it and no return can "
                    f"be checked. Repair the record by hand -- the departure row's "
                    f"subject is the animal's folder name -- then restart wlx taskd",
                )
                return
            bounds_path = self.subjects / found.subject / "bounds.py"
            if not bounds_path.is_file():
                self._refuse(
                    "end",
                    command.by,
                    f"{found.subject!r}'s bounded config ({bounds_path}) is needed to "
                    f"check its return against its departure, and it does not exist; "
                    f"restore it",
                )
                return
            try:
                bounds = _load_bounds(bounds_path)
            except (SystemExit, Exception) as broken:  # noqa: BLE001 -- the animal's files are code
                self._refuse(
                    "end",
                    command.by,
                    f"{found.subject!r}'s bounded config ({bounds_path}) is needed to "
                    f"check its return against its departure, and it would not load "
                    f"({type(broken).__name__}: {_sentence(broken)}); repair it",
                )
                return
        try:
            restored = _stranded.restore(
                found, bounds, self.root / found.session_id / XCON_DIRNAME, self.wall_now
            )
            _marks.page_return(
                restored,
                returned=command.returned,
                confirm=command.confirm,
                by=command.by,
                how="the page, after a restart",
            )
        except _marks.Owed as owed:
            self.question = _link.Question(
                mark="return", session_id=found.session_id, at=owed.at,
                said=owed.warning, answers=owed.answers,
            )
            self._refuse(
                "end", command.by,
                f"{owed.warning}. Send it again answering confirm, or with the time typed again",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("end", command.by, _sentence(refused))
            return
        if self.question is not None and self.question.session_id == found.session_id:
            self.question = None
        self.stranded.remove(found)


def run(args) -> int:
    """`wlx taskd`: load the rig and the allocation, bind the link, and serve until
    interrupted."""
    rig = _load_rig(args.rig)
    allocation = _load_allocation(args.allocation)
    for flag, folder in (("--subjects", args.subjects), ("--tasks", args.tasks)):
        if not folder.is_dir():
            raise SystemExit(f"refused: {flag} {folder} is not a folder")
    parts = args.link.split(",")
    if len(parts) not in (2, 3):
        raise SystemExit(
            f"--link expects PUB,REP or PUB,REP,MARK (two or three comma-separated "
            f"endpoints), got {args.link!r}"
        )
    pub, rep, *mark = parts
    try:
        link = _link.ZmqLink(
            pub, rep, mark[0] if mark else None, allow_remote=args.link_allow_remote
        )
    except _link.RemoteBindRefused as refused:
        raise SystemExit(str(refused)) from refused
    with link:
        service = Service(
            rig=rig,
            rig_path=str(args.rig),
            subjects=args.subjects,
            tasks=args.tasks,
            allocation=allocation,
            allocation_path=str(args.allocation) if args.allocation else "",
            root=args.root,
            link=link,
        )
        print(
            f"wlx taskd: publishing on {link.pub_endpoint}, commands on "
            f"{link.rep_endpoint}"
            + (f", marks on {link.mark_endpoint}" if link.mark_endpoint else "")
        )
        for found in service.stranded:
            print(
                f"  stranded: session {found.session_id} "
                f"({found.subject or 'record unreadable'}); no session opens until its "
                f"return is recorded"
            )
        try:
            service.serve(threading.Event())
        except KeyboardInterrupt:
            open_session = service.session is not None
            service.shutdown()
            print(
                "taskd: interrupted -- the session was open, and the return to the cage "
                "was not recorded; the next start finds it stranded"
                if open_session
                else "taskd: interrupted",
                file=sys.stderr,
            )
            return 130
        except BaseException as fault:
            # **Any other way out says why too** (fix round 1 of Task 7): a fault with a
            # session open is recorded as the reason its return was not, then goes on to
            # the caller unchanged. A kill (SIGTERM, SIGKILL) writes nothing, and the
            # missing row is the signal, as for `wlx run`.
            if service.session is not None:
                service.shutdown(
                    f"wlx taskd stopped on a fault with the session open: "
                    f"{type(fault).__name__}: {fault}"
                )
                print(
                    f"taskd: stopped by {type(fault).__name__} -- the session was open, "
                    f"and the return to the cage was not recorded; the next start finds "
                    f"it stranded",
                    file=sys.stderr,
                )
            raise
    return 0
