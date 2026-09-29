"""`wlx taskd` -- the rig service (P4d-2b spec §6.1).

One process on the rig PC, all day: idle until a console opens a session, then one
animal's session across as many runs as the operator starts, until its return to the cage
is recorded, and then idle again for the next animal. **All of one animal's welfare state
lives in one `taskd.Session`** (PI, 2026-09-29: "One always-on rig service"), which is
the shape S9a §7 drew; nothing carries from one session to the next.

Its commands are the link's -- `OpenSession`, `CheckRun`, `StartRun` and `EndSession`
beside b2a's -- over the socket `wlx run --link` binds. **They are read once per
housekeeping pass while no run is in progress**, never per frame (the b3a-1 plan,
decision 18). **Runs are not taken yet**: until the service starts them (decision 18's
other half, with its reading at each trial boundary), a `CheckRun` or `StartRun` reaches
the open session and is refused there, as any command for a run is between runs.

**Crash safety is a refusal, not a recovery** (spec §6.1). On start the service finds
every session under `--root` with a departure and no return (`stranded.find`), and while
one exists it opens no session, for that animal or any other, until an `EndSession`
naming it records the return.

**A confirm or an amend is taken only as the answer to a question this service posed**
(the b3a-1 review's Ruling 1, 2026-09-29; `_unasked`). The PI's rule for a far mark is a
warning the experimenter must click through (2026-09-20), and the wire cannot tell a
click-through from a confirm sent blind in the first request. So a far mark with no
answer puts a `Question` on the frame; an answer is taken while that question is pending,
for its mark, its session and the instant it asked about; and **the question stays
until it is answered or another replaces it**, so a refused answer -- an amendment with
no reason -- can be corrected and sent again without the warning being lost.

**Every mark is taken on one thread** (the b3a-1 review's Ruling 2): the departure, its
amendment, the head's fixation and release and the return are each taken while a command
is routed, on the thread running `serve`, one command at a time -- which is what lets
`taskd.Session.returned_to_cage` run without the lock it once had.

**Welfare-critical: `Service._open`, `Service._end`, `Service._close_stranded` and
`_unasked`** (`docs/design/architecture.md`): the page's route into the two marks, the
stranded rule, and which answers are taken. The rest is ordinary.

**The simulators, today**: the card, the pump and the animal are `wlx run`'s, because no
hardware port exists (docs/CHECKPOINT.md: nothing has touched hardware); a rig's own
replace them when they do.
"""

from __future__ import annotations

import argparse
import gc
import re
import secrets
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from wl_xcon import link as _link
from wl_xcon import marks as _marks
from wl_xcon import stranded as _stranded
from wl_xcon.bounds import Exceeded
from wl_xcon.cli import _load_allocation, _load_bounds, _load_rig, _load_subject_settings
from wl_xcon.codes import Allocation
from wl_xcon.dio import Simulated as SimulatedCard
from wl_xcon.geometry import Rig
from wl_xcon.record import XCON_DIRNAME
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, SessionClock
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
) -> str | None:
    """**Welfare-critical** (the b3a-1 review's Ruling 1). Why an answer sent with the
    time `text` -- a page's *confirm*, or a departure's *amend* -- is not the answer to
    the question this service posed, or `None` when it is: the question pending, for
    this `mark`, this session, and the instant `text` is read as by the parser
    `marks.page_departure` and `marks.page_return` read it with (`now` for a return,
    which may be typed `now`).

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
        if question.at == at:
            return None
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
        #: The service's own refusals while no session is open, capped as a session's.
        self.refusals: list = []
        self.refusals_dropped = 0
        #: The service's runs (the b3a-1 plan, decision 18), which nothing sets yet:
        #: a run accepted this pass and not started, `(RunSpec, rows, by)`; and an
        #: `EndSession` that arrived during a run, finished once the run returns.
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
        mark, take every command waiting, and publish one frame."""
        mark = self.link.idle(HOUSEKEEPING_S)
        if mark:
            self._mark(mark)
        for command in self.link.drain():
            self._route(command)
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
            )
        )

    def shutdown(self) -> None:
        """The process is stopping (Ctrl-C at `wlx taskd`'s terminal): a session still
        open is recorded as ended without its return, and its clock closed. The next
        start finds it stranded (`stranded.find`), which is what makes it safe to stop
        rather than wait."""
        session, self.session = self.session, None
        if session is None:
            return
        if (
            session.welfare.left_cage_wall_at is not None
            and session.welfare.returned_wall_at is None
        ):
            session.return_not_recorded("wlx taskd stopped with the session open", how="wlx taskd")
        if session.opened_wall_at is not None and session.ended_wall_at is None:
            session.end(how="wlx taskd")

    # --- commands -----------------------------------------------------------------

    def _route(self, command) -> None:
        if isinstance(command, _link.OpenSession):
            self._open(command)
        elif isinstance(command, _link.EndSession):
            self._end(command)
        elif self.session is not None:
            self.session.receive(command)
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
        bounded config."""
        if not self.subjects.is_dir():
            return ()
        return tuple(
            sorted(p.name for p in self.subjects.iterdir() if (p / "bounds.py").is_file())
        )

    def _tasks(self) -> tuple[str, ...]:
        """The task files a run may use: `*.py` under `--tasks`, not `_`-prefixed."""
        if not self.tasks.is_dir():
            return ()
        return tuple(
            sorted(p.name for p in self.tasks.glob("*.py") if not p.name.startswith("_"))
        )

    # --- opening --------------------------------------------------------------------

    def _session_for(self, command: _link.OpenSession) -> Session:
        """The session an `OpenSession` asks for, built and **not opened**: nothing is
        written. Raises `SystemExit`, `ValueError` or `Exceeded` with the sentence a
        refusal says."""
        for what, name in (("session id", command.session_id), ("animal", command.animal)):
            if not _NAME.fullmatch(name) or ".." in name:
                raise ValueError(
                    f"a {what} is one folder name -- letters, digits, '_', '.' and '-', "
                    f"starting with a letter or digit -- and {name!r} is not one"
                )
        if (self.root / command.session_id).exists():
            raise ValueError(
                f"session id {command.session_id!r} is already used under {self.root}; "
                f"every session has its own"
            )
        folder = self.subjects / command.animal
        bounds_path = folder / "bounds.py"
        if not bounds_path.is_file():
            raise ValueError(f"there is no animal {command.animal!r}: {bounds_path} does not exist")
        bounds = _load_bounds(bounds_path)
        if bounds.subject != command.animal:
            raise ValueError(
                f"{bounds_path} holds {bounds.subject!r}'s bounded config, and this folder "
                f"is {command.animal!r}'s; ceilings belong to an animal"
            )
        settings_path = None
        if command.view == "direct":
            geometry = self.rig.direct()
        else:
            settings_path = folder / "settings.py"
            if not settings_path.is_file():
                raise ValueError(
                    f"the stereoscope needs {command.animal!r}'s settings, and "
                    f"{settings_path} does not exist"
                )
            geometry = self.rig.stereoscope(
                _load_subject_settings(settings_path, command.animal).half_ipd_cm
            )
        return Session(
            SessionSpec(
                task="",
                allocation=self.allocation_path,
                root=self.root,
                session_id=command.session_id,
                subject=command.animal,
                trials=0,
                frame_period=FRAME_PERIOD,
                seed=0,
                values={},
                bounds=bounds,
                already_delivered_today=command.delivered_today,
                deployment=Deployment(command.deployment),
                geometry=geometry,
                bounds_config=str(bounds_path),
                rig_config=self.rig_path,
                subject_settings="" if settings_path is None else str(settings_path),
            ),
            card=self._card(),
            pump=self._pump(),
            link=self.link,
            service=True,
            wall_clock=self.wall_clock,
        )

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
                f"Record it with End session, naming its session",
            )
            return
        if command.answer is not None:
            unasked = _unasked(self.question, "departure", command.session_id, command.departure)
            if unasked is not None:
                self._refuse("open", command.by, unasked)
                return
        try:
            session = self._session_for(command)
        except (SystemExit, ValueError, TypeError, Exceeded) as refused:
            self._refuse("open", command.by, _sentence(refused))
            return
        except Exception as broken:  # noqa: BLE001 -- the animal's files are code
            self._refuse(
                "open", command.by,
                f"the session could not be built: {type(broken).__name__}: {broken}",
            )
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

    # --- ending ---------------------------------------------------------------------

    def _end(self, command: _link.EndSession) -> None:
        """**Welfare-critical.** End the open session (P4d-2b spec §6.2): a confirm
        taken only for the question posed (`_unasked`), before anything is marked; then
        its runs end and its head is released (`Session.end_runs`, the b3a-1 plan,
        decision 6), then its return is taken through `marks`, the terminal's rules --
        or, given no return, it waits for one. With none open, the stranded session it
        names."""
        if self.session is None:
            self._close_stranded(command)
            return
        session = self.session
        if command.session_id not in (None, session.spec.session_id):
            self._refuse(
                "end",
                command.by,
                f"the session open is {session.spec.session_id}, not "
                f"{command.session_id}; nothing was ended",
            )
            return
        if command.confirm is not False:
            unasked = _unasked(
                session.question, "return", session.spec.session_id, command.returned,
                session.wall_now,
            )
            if unasked is not None:
                self._refuse("end", command.by, unasked)
                return
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
    return 0
