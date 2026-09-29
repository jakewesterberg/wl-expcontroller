"""`wlx taskd` -- the rig service (P4d-2b spec §6): one animal's session at a time, any
number a day, opened, run and ended by a console's commands, and nothing opened while an
animal is stranded. The unit tests drive `Service.step` over an in-process link with an
injected wall; the end-to-end tests at the bottom drive a real service over ZeroMQ."""

from __future__ import annotations

import gc
import inspect
import json
import shutil
import threading
import time
import weakref
from pathlib import Path

import pytest

from _rig import PATH as RIG_FILE
from _rig import RIG
from _sessions import WALL, typed, whole_point_task
from _zmq_release import _every_zmq_context_released  # noqa: F401
from wl_xcon.cli import _load_allocation, main
from wl_xcon.bounds import Exceeded
from wl_xcon.link import (
    CheckRun,
    EndSession,
    Idle,
    OpenSession,
    Pause,
    Refused,
    SetParameter,
    Simulated,
    StartRun,
    Stop,
    Stranded,
    Telemetry,
    ZmqCommands,
    ZmqConsole,
    ZmqLink,
)
from wl_xcon.record import welfare_note
from wl_xcon.service import Service, _fresh_seed
from wl_xcon.taskd import Session

ALLOCATION = "tasks/allocation.py"
TWELVE_HOURS = Path("tasks/twelve_hour_bounds.py")
TEN_MINUTES = Path("tasks/reference_bounds.py")
TASK = "fixation_detection.py"
BY = "jake (box, unverified)"


class _Wall:
    """The service's wall, moved by a test: `WALL` until then."""

    def __init__(self) -> None:
        self.at = WALL

    def __call__(self) -> float:
        return self.at


def _folders(tmp_path, bounds: Path = TWELVE_HOURS, animals=("REFERENCE",)):
    """`--subjects`, `--tasks` and `--root` for a service: each animal a folder with its
    bounds (the reference file, renamed for it), `REFERENCE` with its settings too, and
    one task. **Copies, never imports**: a file `--subjects` or `--tasks` points at must
    load by path under the installed `wlx`, as `tests/_rig.py`'s docstring says."""
    subjects, tasks, root = tmp_path / "subjects", tmp_path / "tasks", tmp_path / "sessions"
    for animal in animals:
        (subjects / animal).mkdir(parents=True)
        (subjects / animal / "bounds.py").write_text(
            bounds.read_text().replace('subject="REFERENCE"', f'subject="{animal}"')
        )
    if "REFERENCE" in animals:
        shutil.copy("tasks/reference_subject.py", subjects / "REFERENCE" / "settings.py")
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    root.mkdir()
    return subjects, tasks, root


def _made(folders, *, link=None, wall=None, seed=lambda: 7) -> Service:
    subjects, tasks, root = folders
    return Service(
        rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=link if link is not None else Simulated(), seed=seed,
        wall_clock=wall if wall is not None else _Wall(),
    )


def _service(tmp_path, *, bounds=TWELVE_HOURS, animals=("REFERENCE",), link=None, wall=None):
    return _made(_folders(tmp_path, bounds, animals), link=link, wall=wall)


def _open(**over) -> OpenSession:
    fields = dict(
        by=BY, session_id="2027-01-14_01", animal="REFERENCE", deployment="rig_fixed",
        view="direct", departure=typed(60), delivered_today=0.0, answer=None,
        amend_to=None, amend_reason="",
    )
    fields.update(over)
    return OpenSession(**fields)


def _end(returned: str | None = "now", **over) -> EndSession:
    fields = dict(by=BY, session_id=None, returned=returned, confirm=False)
    fields.update(over)
    return EndSession(**fields)


def _step(service, *commands):
    """One housekeeping pass with `commands` waiting; the last frame it published."""
    for command in commands:
        service.link.queue(command)
    service.step()
    return service.link.published[-1]


def _rows(root, session_id="2027-01-14_01") -> list[dict]:
    path = root / session_id / "xcon" / "welfare_notes.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _kinds(root, session_id="2027-01-14_01") -> list[str]:
    return [row["kind"] for row in _rows(root, session_id)]


def _refused(frame) -> list[str]:
    return [refusal.why for refusal in frame.refusals]


def _strand(root, session_id="2027-01-13_01", left_at=WALL - 3600, *also):
    directory = root / session_id / "xcon"
    directory.mkdir(parents=True)
    for kind in ("departure", *also):
        welfare_note(directory, kind=kind, subject="REFERENCE", was=left_at, now=left_at,
                     reason="", by="jake", how="t", recorded_at=left_at)
    return directory


# --- idle ----------------------------------------------------------------------


def test_with_no_session_open_the_service_publishes_idle_frames_offering_animals_and_tasks(tmp_path):
    service = _service(tmp_path, animals=("B", "REFERENCE"))

    frame = _step(service)

    assert isinstance(frame, Idle)
    assert (frame.phase, frame.animals, frame.offered_tasks) == ("idle", ("B", "REFERENCE"), (TASK,))
    assert (frame.stranded, frame.question, frame.refusals) == ((), None, ())


def test_only_an_animal_whose_folder_name_an_open_accepts_is_offered(tmp_path):
    """Fix round 1 of Task 7: the idle frame offered any folder holding a bounded
    config, so it could offer an animal every open refuses."""
    folders = _folders(tmp_path, animals=("B", "REFERENCE"))
    for name in ("Monkey A", "a..b"):
        (folders[0] / name).mkdir()
        shutil.copy(folders[0] / "B" / "bounds.py", folders[0] / name / "bounds.py")

    assert _step(_made(folders)).animals == ("B", "REFERENCE")


def test_with_no_session_a_run_command_or_a_mark_is_refused_and_said(tmp_path):
    link = Simulated()
    link.marks.append(4)
    service = _service(tmp_path, link=link)

    frame = _step(service, Pause(by=BY))

    assert [(r.name, r.why) for r in frame.refusals] == [
        ("mark", "no session is open, so the mark was not recorded"),
        ("pause", "no session is open, so a command for a run is not applied; open a session first"),
    ]


# --- open -----------------------------------------------------------------------


def test_open_marks_the_departure_opens_the_session_and_waits_between_runs(tmp_path):
    service = _service(tmp_path)

    frame = _step(service, _open())

    assert isinstance(frame, Telemetry)
    assert (frame.phase, frame.service, frame.run_index) == ("between_runs", True, None)
    assert (frame.session_id, frame.offered_tasks) == ("2027-01-14_01", (TASK,))
    assert _kinds(service.root) == ["departure", "session opened"]
    assert service.session.card.codes == [4128], "head fixed once, as the session opens"
    config = json.loads((service.root / "2027-01-14_01" / "xcon" / "config.json").read_text())
    assert config["service"] is True and config["subject"] == "REFERENCE"


def test_a_session_id_or_animal_that_is_not_one_folder_name_is_refused_and_nothing_is_written(tmp_path):
    """Review Focus 1: each becomes a path, and arrives over the wire."""
    service = _service(tmp_path)

    for over in ({"session_id": "../2027-01-14_01"}, {"session_id": "a/b"},
                 {"session_id": "."}, {"animal": "../REFERENCE"}):
        frame = _step(service, _open(**over))
        assert isinstance(frame, Idle)
        assert "one folder name" in _refused(frame)[-1], over

    assert list(service.root.iterdir()) == []
    assert not (tmp_path / "2027-01-14_01").exists()


@pytest.mark.parametrize(
    ("over", "said"),
    [
        ({"animal": "C"}, "there is no animal 'C'"),
        ({"view": "stereoscope", "animal": "B"}, "settings"),
        ({"departure": "half past nine"}, "is not a clock time"),
        ({"departure": typed(-3600)}, "in the future"),
        ({"delivered_today": -1.0}, "cannot be negative"),
    ],
)
def test_an_open_that_is_refused_says_why_and_writes_nothing(tmp_path, over, said):
    service = _service(tmp_path, animals=("B", "REFERENCE"))

    frame = _step(service, _open(**over))

    assert isinstance(frame, Idle)
    assert any(said in why for why in _refused(frame)), _refused(frame)
    assert list(service.root.iterdir()) == []


def test_an_animal_whose_bounds_name_another_is_refused_naming_both(tmp_path):
    folders = _folders(tmp_path, animals=("REFERENCE",))
    (folders[0] / "C").mkdir()
    shutil.copy(folders[0] / "REFERENCE" / "bounds.py", folders[0] / "C" / "bounds.py")

    frame = _step(_made(folders), _open(animal="C"))

    assert any("'REFERENCE''s bounded config" in why and "'C'" in why for why in _refused(frame))


def test_a_departure_past_the_animals_ceiling_is_refused_without_a_question(tmp_path):
    service = _service(tmp_path, bounds=TEN_MINUTES)

    frame = _step(service, _open(departure=typed(900)))

    assert frame.question is None
    assert any("at or outside the limit" in why for why in _refused(frame))


def test_a_session_id_already_used_under_the_root_is_refused(tmp_path):
    service = _service(tmp_path)
    (service.root / "2027-01-14_01").mkdir()

    frame = _step(service, _open())

    assert any("already used" in why for why in _refused(frame))


def test_a_far_departure_is_asked_confirm_or_amend_and_opens_once_confirmed(tmp_path):
    service = _service(tmp_path)
    far = typed(3 * 3600)

    asked = _step(service, _open(departure=far))

    assert isinstance(asked, Idle)
    assert (asked.question.mark, asked.question.session_id) == ("departure", "2027-01-14_01")
    assert asked.question.answers == ("confirm", "amend")
    assert list(service.root.iterdir()) == [], "the id is still free"

    opened = _step(service, _open(departure=far, answer="confirm"))

    assert opened.phase == "between_runs" and opened.question is None
    rows = _rows(service.root)
    assert [r["kind"] for r in rows] == ["departure", "departure confirmed", "session opened"]
    assert (rows[1]["how"], rows[1]["by"]) == ("confirmed on the page", BY)


def test_an_answered_question_is_gone_from_the_idle_frame_after_its_session(tmp_path):
    """A question is kept until it is answered: once its departure is marked it is gone,
    so the idle frame after that session ends asks nothing of the next animal's."""
    service = _service(tmp_path)
    far = typed(3 * 3600)
    _step(service, _open(departure=far))
    _step(service, _open(departure=far, answer="confirm"))

    idle = _step(service, _end())

    assert isinstance(idle, Idle) and idle.question is None


def test_a_far_departure_amended_on_the_page_is_marked_at_the_corrected_time(tmp_path):
    """Asked first: an amendment answers the warning (Ruling 1 of the b3a-1 review)."""
    service = _service(tmp_path)
    _step(service, _open(departure=typed(9 * 3600)))

    _step(service, _open(departure=typed(9 * 3600), answer="amend",
                         amend_to=typed(600), amend_reason="typed 09:30 for 17:30"))

    rows = _rows(service.root)
    assert [r["kind"] for r in rows] == ["departure", "departure amended", "session opened"]
    assert rows[1]["reason"] == "typed 09:30 for 17:30"
    assert service.session.welfare.left_cage_wall_at == pytest.approx(WALL - 600, abs=1.0)


def test_an_amendment_with_no_reason_is_refused_and_its_question_stays_to_answer(tmp_path):
    """`welfare.amend_mark`'s blank-reason refusal, through the page. The question stays
    on the frame until it is answered: a refused answer is not an answer, and a corrected
    one sent next is taken."""
    service = _service(tmp_path)
    far = typed(9 * 3600)
    _step(service, _open(departure=far))

    refused = _step(service, _open(departure=far, answer="amend", amend_to=typed(600),
                                   amend_reason=""))

    assert isinstance(refused, Idle)
    assert "no reason" in _refused(refused)[-1]
    assert refused.question is not None and refused.question.mark == "departure"
    assert list(service.root.iterdir()) == []

    opened = _step(service, _open(departure=far, answer="amend", amend_to=typed(600),
                                  amend_reason="typed 09:30 for 17:30"))

    assert opened.phase == "between_runs"
    assert _kinds(service.root) == ["departure", "departure amended", "session opened"]


# --- a confirm or an amend answers a question the service posed (Ruling 1) ---------


@pytest.mark.parametrize(
    "over",
    [
        {"departure": typed(3 * 3600), "answer": "confirm"},
        {"departure": typed(9 * 3600), "answer": "amend", "amend_to": typed(600),
         "amend_reason": "typed 09:30 for 17:30"},
        {"departure": typed(60), "answer": "confirm"},
    ],
    ids=["a far confirm", "a far amend", "an in-band confirm"],
)
def test_a_confirm_or_an_amend_nobody_was_asked_for_is_refused_and_nothing_is_written(tmp_path, over):
    """PI, 2026-09-20: a far departure is "a warning ... that the experimenter must click
    through". The wire cannot tell a click-through from a confirm sent blind in the first
    request, so an answer is taken only as the answer to the question this service posed,
    and one sent with none owed is refused before anything is built or marked."""
    service = _service(tmp_path)

    frame = _step(service, _open(**over))

    assert isinstance(frame, Idle) and frame.question is None
    assert "answers the warning" in _refused(frame)[-1]
    assert "nothing was recorded" in _refused(frame)[-1]
    assert list(service.root.iterdir()) == []


@pytest.mark.parametrize(
    "over",
    [{"animal": "B"}, {"deployment": "rig_chaired"}, {"view": "stereoscope"}],
    ids=["another animal", "another deployment", "another setup"],
)
def test_a_confirm_for_another_animal_deployment_or_setup_than_the_one_asked_is_refused(
    tmp_path, over
):
    """Fix round 1 of Task 7: the warning names an animal, and is asked about one open.
    A confirm sent with the same id and time for another animal, deployment or setup is
    a confirm of an open no warning was shown for, and is refused with nothing marked."""
    service = _service(tmp_path, animals=("B", "REFERENCE"))
    far = typed(3 * 3600)
    _step(service, _open(departure=far))

    frame = _step(service, _open(departure=far, answer="confirm", **over))

    assert isinstance(frame, Idle)
    assert "the warning shown was for" in _refused(frame)[-1]
    assert list(service.root.iterdir()) == []
    assert frame.question is not None, "still owed"
    assert _step(service, _open(departure=far, answer="confirm")).phase == "between_runs"
    assert service.session.spec.subject == "REFERENCE"


def test_a_confirm_for_another_time_or_session_than_the_one_asked_about_is_refused(tmp_path):
    """The warning is for one session's departure at one instant; a confirm of another
    time, or of another session's, was never shown one."""
    service = _service(tmp_path)
    far = typed(3 * 3600)
    _step(service, _open(departure=far))

    other_time = _step(service, _open(departure=typed(4 * 3600), answer="confirm"))
    other_session = _step(service, _open(session_id="2027-01-14_02", departure=far,
                                         answer="confirm"))

    assert "the warning shown was for" in _refused(other_time)[-1]
    assert "answers the warning" in _refused(other_session)[-1]
    assert list(service.root.iterdir()) == []
    assert other_session.question.session_id == "2027-01-14_01", "still owed"

    assert _step(service, _open(departure=far, answer="confirm")).phase == "between_runs"


def test_a_confirmed_return_nobody_was_asked_about_is_refused_and_nothing_is_marked(tmp_path):
    """The same rule on the closing mark: a blind confirm on End session is refused before
    the runs end, so not even the head's release is recorded."""
    wall = _Wall()
    service = _service(tmp_path, wall=wall)
    _step(service, _open(departure=typed(1200)))
    wall.at = WALL + 3 * 3600

    frame = _step(service, _end(returned=typed(-1800), confirm=True))

    assert frame.phase == "between_runs"
    assert "answers the warning" in _refused(frame)[-1]
    assert service.session.card.codes == [4128], "the head was not released"
    assert _kinds(service.root) == ["departure", "session opened"]


def test_a_confirmed_return_of_another_time_than_the_one_asked_is_refused(tmp_path):
    wall = _Wall()
    service = _service(tmp_path, wall=wall)
    _step(service, _open(deployment="rig_chaired", departure=typed(1200)))
    wall.at = WALL + 3 * 3600
    far = typed(-1800)
    _step(service, _end(returned=far))

    other = _step(service, _end(returned=typed(-1500), confirm=True))

    assert other.phase == "awaiting_return"
    assert "the warning shown was for" in _refused(other)[-1]
    assert "returned" not in _kinds(service.root)
    assert other.question is not None, "the question is still owed"
    assert isinstance(_step(service, _end(returned=far, confirm=True)), Idle)


def test_a_stranded_return_confirmed_blind_is_refused_and_taken_once_asked(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2])
    service = _made(folders)
    far = typed(2400)

    blind = _step(service, _end(session_id="2027-01-13_01", returned=far, confirm=True))

    assert "answers the warning" in _refused(blind)[-1]
    assert blind.stranded != () and _kinds(folders[2], "2027-01-13_01") == ["departure"]

    asked = _step(service, _end(session_id="2027-01-13_01", returned=far))
    assert (asked.question.mark, asked.question.session_id) == ("return", "2027-01-13_01")
    closed = _step(service, _end(session_id="2027-01-13_01", returned=far, confirm=True))

    assert closed.stranded == () and closed.question is None
    assert _kinds(folders[2], "2027-01-13_01") == ["departure", "returned", "return confirmed"]


def test_two_opens_in_one_pass_open_one_session_and_refuse_the_other(tmp_path):
    """Review Focus 3."""
    service = _service(tmp_path, animals=("B", "REFERENCE"))

    frame = _step(service, _open(), _open(session_id="2027-01-14_02", animal="B"))

    assert frame.session_id == "2027-01-14_01"
    assert any("a session is open for 'REFERENCE'" in why for why in _refused(frame))
    assert [p.name for p in service.root.iterdir()] == ["2027-01-14_01"]


# --- end ------------------------------------------------------------------------


def test_end_releases_the_head_takes_the_return_and_goes_back_to_idle(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())
    card = service.session.card

    idle = _step(service, _end())

    assert isinstance(idle, Idle) and service.session is None
    assert service.link.published[-2].phase == "closed", "one closed frame first"
    assert card.codes == [4128, 4129]
    assert _kinds(service.root) == ["departure", "session opened", "returned", "session ended"]


def test_end_without_a_return_waits_for_it_and_refuses_a_run(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    waiting = _step(service, _end(returned=None))

    assert (waiting.phase, waiting.stop_kind) == ("awaiting_return", "operator")
    assert waiting.stopped_because == f"session ended by {BY}, before any run"
    refused = _step(service, Pause(by=BY))
    assert "recorded from the page (End session)" in _refused(refused)[-1]
    assert isinstance(_step(service, _end()), Idle)


def test_a_return_typed_before_the_session_was_ended_is_refused_and_now_closes_it(tmp_path):
    """Review Focus 2: End session pressed after the animal is home, with its real,
    earlier time. The head's release was recorded at the End (plan decision 6), so the
    earlier return is refused with `welfare`'s sentence, and the session waits."""
    wall = _Wall()
    service = _service(tmp_path, wall=wall)
    _step(service, _open(departure=typed(1200)))
    wall.at = WALL + 600

    refused = _step(service, _end(returned=typed(-300)))

    assert refused.phase == "awaiting_return"
    assert any("released from head-fixation" in why for why in _refused(refused))
    assert isinstance(_step(service, _end()), Idle)


def test_a_far_return_is_asked_confirm_or_retype_and_taken_once_confirmed(tmp_path):
    wall = _Wall()
    service = _service(tmp_path, wall=wall)
    _step(service, _open(deployment="rig_chaired", departure=typed(1200)))
    wall.at = WALL + 3 * 3600
    far = typed(-1800)

    asked = _step(service, _end(returned=far))

    assert asked.question.answers == ("confirm", "re-type")
    assert asked.phase == "awaiting_return"
    assert isinstance(_step(service, _end(returned=far, confirm=True)), Idle)
    assert _kinds(service.root)[-3:] == ["returned", "return confirmed", "session ended"]


def test_a_closed_session_is_collected_as_it_closes(tmp_path):
    """Plan decision 17: a session is a reference cycle (`welfare.Rig`'s docstring), so
    the service collects it as it closes, between sessions -- not later, by an automatic
    collection that could land in the next session's run. With automatic collection off,
    only the service's own can free it."""
    service = _service(tmp_path)
    _step(service, _open())
    closing = weakref.ref(service.session)
    enabled = gc.isenabled()
    gc.disable()
    try:
        _step(service, _end())
        assert closing() is None, "freed by the collection at close, not left for a later one"
    finally:
        if enabled:
            gc.enable()


def test_an_end_with_nothing_open_to_end_is_refused(tmp_path):
    """A double click on End session: the second finds no session, and never touches
    another."""
    service = _service(tmp_path)
    _step(service, _open())
    _step(service, _end())

    frame = _step(service, _end())

    assert "no session is open" in _refused(frame)[-1]


def test_any_number_of_sessions_a_day_each_its_own_animal_and_welfare(tmp_path):
    """Spec §6.1: monkey A in the morning, monkey B in the afternoon, and nothing carries
    from one to the next."""
    service = _service(tmp_path, animals=("B", "REFERENCE"))
    _step(service, _open(delivered_today=5.0))
    first = service.session
    _step(service, _end())

    frame = _step(service, _open(session_id="2027-01-14_02", animal="B", delivered_today=None))

    second = service.session
    assert second is not first and second.welfare is not first.welfare
    assert (frame.subject, frame.fluid_session_ml, frame.fluid_today_ml) == ("B", 0.0, None)
    assert _kinds(service.root, "2027-01-14_01")[-1] == "session ended"
    assert _kinds(service.root, "2027-01-14_02") == ["departure", "session opened"]


def test_every_mark_is_taken_on_the_thread_that_serves(tmp_path, monkeypatch):
    """Ruling 2 of the b3a-1 review: `returned_to_cage`'s single-caller invariant -- the
    reason `_mark_lock` was removed -- holds per process because the service takes every
    mark on its one loop thread: the departure, its amendment, the head's fixation and
    release, and the return, each from `serve`'s own pass."""
    taken = []
    for name in ("amend_mark", "left_cage", "head_fixed", "head_released", "returned_to_cage"):
        real = getattr(Session, name)

        def spy(self, *args, _real=real, _name=name, **kwargs):
            taken.append((_name, threading.get_ident()))
            return _real(self, *args, **kwargs)

        monkeypatch.setattr(Session, name, spy)
    stop = threading.Event()

    class _UntilQuiet(Simulated):
        def drain(self):
            drained = super().drain()
            if not drained:
                stop.set()
            return drained

    service = _service(tmp_path, link=_UntilQuiet())
    far = typed(9 * 3600)
    for command in (
        _open(departure=far),
        _open(departure=far, answer="amend", amend_to=typed(600), amend_reason="a typo"),
        _end(),
    ):
        service.link.queue(command)
    # A watchdog, so a pass that never drains fails this test rather than hanging the
    # suite: the harness noticing a hang is not a test noticing (CLAUDE.md).
    watchdog = threading.Timer(10.0, stop.set)
    watchdog.start()
    try:
        service.serve(stop)
    finally:
        watchdog.cancel()

    assert [name for name, _ in taken] == [
        "amend_mark", "left_cage", "head_fixed", "head_released", "returned_to_cage",
    ]
    assert {thread for _, thread in taken} == {threading.get_ident()}


def test_a_service_given_no_seed_draws_each_one_fresh_as_the_record_can_hold_it():
    """Plan decision 15: a run's seed is the service's to draw, and is written into its
    start row so the run can be replayed -- a whole number from 0 below 2**31. Each run
    the service starts draws one (`Service._start`; the test below reads it back)."""
    drawn = [_fresh_seed() for _ in range(64)]

    assert all(type(seed) is int and 0 <= seed < 2**31 for seed in drawn)
    assert len(set(drawn)) > 1, "fresh, not one number"
    assert inspect.signature(Service).parameters["seed"].default is _fresh_seed


# --- between runs ---------------------------------------------------------------


def test_between_runs_a_mark_is_stamped_and_strobed(tmp_path):
    link = Simulated()
    service = _service(tmp_path, link=link)
    _step(service, _open())
    link.marks.append(4)

    frame = _step(service)

    assert frame.controls[-1].said == "mark 1 stamped with no run in progress"
    assert service.session.card.codes[-1] == 4133


# --- stranded -------------------------------------------------------------------


def test_a_stranded_session_found_at_start_refuses_every_open_until_its_return_is_recorded(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2])
    service = _made(folders)

    idle = _step(service)
    assert idle.stranded == (Stranded("2027-01-13_01", "REFERENCE", WALL - 3600),)
    refused = _step(service, _open())
    assert "no session opens while an animal's return is not recorded" in _refused(refused)[-1]

    closed = _step(service, _end(session_id="2027-01-13_01"))

    assert closed.stranded == ()
    assert _kinds(folders[2], "2027-01-13_01") == ["departure", "returned"]
    assert _rows(folders[2], "2027-01-13_01")[-1]["how"] == "the page, after a restart"
    assert _step(service, _open()).phase == "between_runs"


def test_a_session_wlx_run_left_with_its_return_not_recorded_is_stranded(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2], "2027-01-13_01", WALL - 600, "return not recorded")

    assert [s.session_id for s in _made(folders).stranded] == ["2027-01-13_01"]


def test_a_crashed_sessions_torn_last_line_leaves_it_stranded_never_skipped(tmp_path):
    """Review Focus 5: a crash mid-write leaves a line that is not a row. Fail closed:
    the session stays stranded, its return is refused with what to do, and nothing opens."""
    folders = _folders(tmp_path)
    directory = _strand(folders[2])
    with (directory / "welfare_notes.jsonl").open("a") as handle:
        handle.write('{"kind": "retur')
    service = _made(folders)

    assert _step(service).stranded == (Stranded("2027-01-13_01", "", None),)
    refused = _step(service, _end(session_id="2027-01-13_01"))
    assert "cannot be read" in _refused(refused)[-1] and "repair" in _refused(refused)[-1]
    assert _step(service, _open()).phase == "idle"


def test_a_stranded_animal_whose_bounds_file_is_gone_is_refused_saying_so(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2])
    (folders[0] / "REFERENCE" / "bounds.py").unlink()
    service = _made(folders)

    refused = _step(service, _end(session_id="2027-01-13_01"))

    assert "restore it" in _refused(refused)[-1]
    assert service.stranded != []


@pytest.mark.parametrize("where", ["relative", "absolute"])
def test_a_stranded_record_whose_animal_is_no_folder_name_runs_nothing_outside_subjects(
    tmp_path, where
):
    """Fix round 1 of Task 7 (Critical): a stranded record's subject becomes a path, and
    the bounded config at that path is code. `wlx run --subject` takes any text, so a
    record may name `../outside` or an absolute path; nothing outside `--subjects` may
    run for it. Refused before any path is built, and the animal stays stranded."""
    folders = _folders(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = tmp_path / "ran.txt"
    (outside / "bounds.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
    )
    subject = "../outside" if where == "relative" else str(outside)
    directory = folders[2] / "2027-01-13_01" / "xcon"
    directory.mkdir(parents=True)
    welfare_note(directory, kind="departure", subject=subject, was=WALL - 3600,
                 now=WALL - 3600, reason="", by="jake", how="t", recorded_at=WALL - 3600)
    service = _made(folders)

    refused = _step(service, _end(session_id="2027-01-13_01"))

    assert not marker.exists(), "a file outside --subjects ran"
    assert "names no animal folder" in _refused(refused)[-1]
    assert [s.session_id for s in service.stranded] == ["2027-01-13_01"]
    assert _kinds(folders[2], "2027-01-13_01") == ["departure"]


def test_a_welfare_record_this_host_cannot_read_is_stranded_not_a_crash(tmp_path):
    """Fix round 1 of Task 7: `welfare_notes.jsonl` that is not a readable file -- here a
    folder -- crashed the service at start. It is stranded and unreadable, failing closed
    as a torn line does."""
    folders = _folders(tmp_path)
    (folders[2] / "2027-01-13_01" / "xcon" / "welfare_notes.jsonl").mkdir(parents=True)
    service = _made(folders)

    assert _step(service).stranded == (Stranded("2027-01-13_01", "", None),)
    refused = _step(service, _end(session_id="2027-01-13_01"))
    assert "cannot be read" in _refused(refused)[-1]
    assert _step(service, _open()).phase == "idle"


@pytest.mark.parametrize(
    ("text", "said"),
    [("BOUNDS = not_defined_anywhere\n", "NameError"), ("x = 1\n", "must define BOUNDS")],
)
def test_a_stranded_animal_whose_bounds_file_will_not_load_is_refused_not_a_crash(
    tmp_path, text, said
):
    """The animal's files are code, as `_open` says of them: a broken bounded config is a
    refusal with what to do, never the service's end, and the animal stays stranded."""
    folders = _folders(tmp_path)
    _strand(folders[2])
    (folders[0] / "REFERENCE" / "bounds.py").write_text(text)
    service = _made(folders)

    refused = _step(service, _end(session_id="2027-01-13_01"))

    assert said in _refused(refused)[-1] and "repair it" in _refused(refused)[-1]
    assert [s.session_id for s in service.stranded] == ["2027-01-13_01"]
    assert _kinds(folders[2], "2027-01-13_01") == ["departure"]


def test_a_service_stopped_with_a_session_open_leaves_it_stranded_for_the_next(tmp_path):
    folders = _folders(tmp_path)
    service = _made(folders)
    _step(service, _open())

    service.shutdown()

    assert _kinds(folders[2])[-2:] == ["return not recorded", "session ended"]
    assert [s.session_id for s in _made(folders).stranded] == ["2027-01-14_01"]


# --- runs -----------------------------------------------------------------------

VALUES = {
    "fix_timeout": 4.0, "fix_hold": 0.3, "response_window": 0.6, "target_hold": 0.2,
    "fix_window": 2.0, "target_window": 3.0, "target_position": 10.0,
}
UNKNOWN = ("pump calibration", "eye tracker")


def _start(**over) -> StartRun:
    fields = dict(by=BY, task=TASK, values=dict(VALUES), trials=3, acknowledged=UNKNOWN)
    fields.update(over)
    return StartRun(**fields)


def _runs(root, session_id="2027-01-14_01") -> list[dict]:
    path = root / session_id / "xcon" / "runs.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class _Script(Simulated):
    """A link whose `n`th drain also hands over `script[n]`: the service's own drains
    and a run's, at its boundaries, counted alike."""

    def __init__(self, script: dict) -> None:
        super().__init__()
        self.script, self.drains = script, 0

    def drain(self):
        self.drains += 1
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def test_a_run_is_checked_or_started_only_between_the_runs_of_an_open_session(tmp_path):
    """With no session open there is no animal to run; once End session has been sent,
    the session waits for its animal's return, and no run starts in it."""
    service = _service(tmp_path)
    never = "no session is open, so no run starts; open a session first"
    ended = "the session has ended and waits for its animal's return, so no run starts"

    idle = _step(service, CheckRun(by=BY, task=TASK, values={}), _start())

    assert isinstance(idle, Idle)
    assert [(r.name, r.why) for r in idle.refusals] == [("check", never), ("start", never)]
    _step(service, _open())
    _step(service, _end(returned=None))

    waiting = _step(service, CheckRun(by=BY, task=TASK, values={}), _start())

    assert (waiting.phase, waiting.preflight, waiting.run_index) == ("awaiting_return", None, None)
    assert [(r.name, r.why) for r in waiting.refusals[-2:]] == [("check", ended), ("start", ended)]
    assert _runs(service.root) == [] and 4135 not in service.session.card.codes


def test_a_check_shows_the_runs_preflight_and_starts_nothing(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES)))

    assert (frame.phase, frame.run_index) == ("between_runs", None)
    assert frame.preflight.task == TASK
    assert [(i.name, i.result) for i in frame.preflight.items] == [
        ("task checks", "pass"), ("starting values", "pass"), ("bounded config", "pass"),
        ("out of cage", "pass"), ("pump calibration", "unknown"), ("eye tracker", "unknown"),
    ]
    assert _runs(service.root) == [] and service.session.card.codes == [4128], "nothing ran"


def test_a_task_the_checks_raise_on_fails_its_preflight_and_the_service_goes_on(tmp_path):
    """Fix round 1 of Task 8: `check()` raising on an offered task (XC-156) went out of
    `step` uncaught, and `wlx taskd` ended with the animal out of its cage. It is the
    task checks item's fail now: shown by a check, refused on a start, and the next
    command served."""
    service = _service(tmp_path)
    whole_point_task(service.tasks)
    _step(service, _open())

    checked = _step(service, CheckRun(by=BY, task="whole_point.py", values={}))
    started = _step(service, _start(task="whole_point.py"))
    ended = _step(service, _end())

    assert "whole_point.py" in checked.offered_tasks
    items = {i.name: i for i in checked.preflight.items}
    assert items["task checks"].result == "fail" and "TypeError" in items["task checks"].said
    assert started.run_index is None and _runs(service.root) == []
    assert "pre-flight failed, so the run does not start: task checks: " in _refused(started)[-1]
    assert isinstance(ended, Idle) and _kinds(service.root)[-2:] == ["returned", "session ended"]


def test_a_run_whose_unknowns_nobody_acknowledged_does_not_start(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(acknowledged=("pump calibration",)))

    assert frame.run_index is None and _runs(service.root) == []
    assert "nobody has acknowledged: eye tracker" in _refused(frame)[-1]
    assert frame.preflight is not None, "the pre-flight stays on the frame to acknowledge"


def test_an_acknowledged_run_starts_records_who_acknowledged_what_and_ends_between_runs(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start())

    assert (frame.phase, frame.run_index, frame.stop_kind) == ("between_runs", 0, "completed")
    start, end = _runs(service.root)
    assert {r["name"]: r["acknowledged_by"] for r in start["preflight"]} == {
        "task checks": None, "starting values": None, "bounded config": None,
        "out of cage": None, "pump calibration": BY, "eye tracker": BY,
    }
    assert (start["unplanned"], start["by"], start["seed"], start["trials"]) == (True, BY, 7, 3)
    assert end["stop_kind"] == "completed"
    codes = service.session.card.codes
    assert codes[:2] == [4128, 4135] and 4136 in codes and 4129 not in codes


@pytest.mark.parametrize(
    ("over", "item"),
    [
        ({"values": {**VALUES, "fix_hold": 99.0}}, "starting values"),
        ({"values": {**VALUES, "no_such": 1.0}}, "starting values"),
        ({"task": "empty.py"}, "task checks"),
    ],
)
def test_a_run_with_a_failing_item_does_not_start_even_acknowledged(tmp_path, over, item):
    service = _service(tmp_path)
    (service.tasks / "empty.py").write_text("x = 1\n")
    _step(service, _open())

    frame = _step(service, _start(**over))

    assert frame.run_index is None
    assert f"pre-flight failed, so the run does not start: {item}" in _refused(frame)[-1]


@pytest.mark.parametrize("task", ["missing.py", "../fixation_detection.py", "notes.txt"])
def test_a_task_that_is_not_a_file_under_the_tasks_folder_is_refused_by_name(tmp_path, task):
    service = _service(tmp_path)
    (service.tasks / "notes.txt").write_text("x = 1\n")  # a file, and not a task file
    _step(service, _open())

    frame = _step(service, _start(task=task))

    assert frame.run_index is None and "is not a task file under" in _refused(frame)[-1]


@pytest.mark.parametrize("name", ["../outside.py", "ABSOLUTE", "a..b.py", "_hidden.py", "two words.py"])
def test_a_task_named_by_no_one_file_name_loads_nothing_and_runs_nothing(tmp_path, name):
    """Carried from Task 7: a run's task arrives over the wire and becomes a path, and the
    file there is code the service loads. So it is one folder name (`_folder_name`), the
    rule a session id and an animal are held to, refused before any path is built -- a
    parent reference, an absolute path, and names `_NAME` or the `..` rule refuse -- and
    said on the feed. Each file is planted where its name would reach, so a refusal that
    did not happen would run it. None is offered, either."""
    service = _service(tmp_path)
    marker = tmp_path / "ran.txt"
    planted = f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
    (tmp_path / "outside.py").write_text(planted)
    for inside in ("a..b.py", "_hidden.py", "two words.py"):
        (service.tasks / inside).write_text(planted)
    if name == "ABSOLUTE":
        name = str(tmp_path / "outside.py")
    _step(service, _open())

    checked = _step(service, CheckRun(by=BY, task=name, values={}))
    started = _step(service, _start(task=name))

    assert not marker.exists(), "a task file was loaded"
    for frame, kind in ((checked, "check"), (started, "start")):
        refusal = frame.refusals[-1]
        assert (refusal.name, refusal.by) == (kind, BY)
        assert refusal.why.startswith(f"{name!r} is not a task file under {service.tasks}")
        assert refusal.why.endswith("so nothing was loaded")
    assert (started.preflight, started.run_index) == (None, None)
    assert _runs(service.root) == [] and service.session.card.codes == [4128]
    assert started.offered_tasks == (TASK,)


def test_the_out_of_cage_limit_reached_between_runs_refuses_a_new_run_and_says_so(tmp_path):
    """Spec §6.1: "reached between runs, it refuses a new run, and the page asks for the
    return"."""
    wall = _Wall()
    service = _service(tmp_path, bounds=TEN_MINUTES, wall=wall)
    _step(service, _open(departure=typed(300)))
    _step(service, _start(trials=2))
    wall.at = WALL + 400

    frame = _step(service, _start(trials=2))

    assert frame.run_index == 0, "no second run"
    assert "out of cage: out_of_cage" in _refused(frame)[-1]
    assert "ceiling" in frame.duration_warning
    assert [i.result for i in frame.preflight.items if i.name == "out of cage"] == ["fail"]


def test_a_run_past_the_out_of_cage_limit_is_refused_before_run_start_is_strobed(tmp_path):
    """Carried from Task 3: `Session.run` does not refuse a run past the limit --
    `welfare.preflight` checks no ceiling -- so it would strobe `RUN_START` and write its
    start row before `_ends` stopped it at the first boundary. The service's pre-flight
    refuses it first: the out-of-cage item fails once `must_stop` fires, and the gate
    blocks on it, acknowledged or not."""
    wall = _Wall()
    service = _service(tmp_path, bounds=TEN_MINUTES, wall=wall)
    _step(service, _open(departure=typed(300)))
    wall.at = WALL + 400

    frame = _step(service, _start(acknowledged=(*UNKNOWN, "out of cage")))

    why = _refused(frame)[-1]
    assert why.startswith("pre-flight failed, so the run does not start: out of cage: out_of_cage")
    assert "no run starts past the limit" in why
    assert service.session.card.codes == [4128], "no RUN_START"
    assert _runs(service.root) == [] and frame.run_index is None


def test_the_out_of_cage_limit_ends_a_run_in_progress_and_the_session_waits_for_its_return(tmp_path):
    service = None

    def wall() -> float:
        # Follows the frames while a run is in progress, as a rig's wall does.
        return WALL + (service.session.now() if service is not None and service.session else 0.0)

    service = _service(tmp_path, bounds=TEN_MINUTES, wall=wall)
    _step(service, _open(departure=typed(300)))

    frame = _step(service, _start(trials=100_000))

    assert (frame.phase, frame.stop_kind) == ("between_runs", "limit")
    assert isinstance(_step(service, _end()), Idle)


def test_end_during_a_run_stops_it_at_its_boundary_then_ends_the_session(tmp_path):
    link = _Script({3: [_end()]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=1000))

    assert isinstance(frame, Idle)
    _, end = _runs(service.root)
    assert (end["stop_kind"], end["stopped_because"]) == ("operator", f"stopped by {BY}")
    assert end["trials"] < 1000
    assert _kinds(service.root)[-2:] == ["returned", "session ended"]


def test_end_during_a_run_releases_the_head_only_once_the_run_has_ended(tmp_path):
    """Carried from Task 7: `_end` is for a session between runs or awaiting its return,
    so an End during a run stops it -- a `Stop` in its place -- and is finished once the
    run has returned: the head's release after `RUN_END`, never mid-run. Given no return
    time, the session then waits for one."""
    link = _Script({3: [_end(returned=None)]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=1000))

    assert (frame.phase, frame.stop_kind) == ("awaiting_return", "operator")
    codes = service.session.card.codes
    assert codes.index(4136) < codes.index(4129), "RUN_END, then the head's release"
    assert _runs(service.root)[-1]["stopped_because"] == f"stopped by {BY}"
    assert isinstance(_step(service, _end()), Idle)


def test_end_while_a_run_is_paused_stops_it_there_then_ends_the_session(tmp_path):
    """The paused loop drains through the same link (`Session._hold`), so an End sent
    while paused stops the run as one sent between trials does."""
    link = _Script({3: [Pause(by=BY)], 4: [_end()]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=1000))

    assert isinstance(frame, Idle)
    _, end = _runs(service.root)
    assert (end["stop_kind"], end["stopped_because"], end["trials"]) == (
        "operator", f"stopped by {BY}", 0,
    )
    assert _kinds(service.root)[-2:] == ["returned", "session ended"]


def test_during_a_run_an_end_that_would_be_refused_is_refused_and_stops_nothing(tmp_path):
    """An End `_end` refuses before anything is marked -- one naming another session, or
    a confirm nobody was asked for (`_unasked`) -- is refused during a run before anything
    is stopped, so a stale page cannot stop this animal's run by sending another's."""
    link = _Script({3: [_end(session_id="2027-01-13_01"), _end(confirm=True)]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=3))

    assert (frame.phase, frame.stop_kind) == ("between_runs", "completed")
    assert [r.name for r in frame.refusals] == ["end", "end"]
    assert "the session open is 2027-01-14_01, not 2027-01-13_01" in _refused(frame)[0]
    assert "answers the warning" in _refused(frame)[1]
    assert _kinds(service.root) == ["departure", "session opened"]
    assert isinstance(_step(service, _end()), Idle), "an End it would take is still taken"


def test_a_second_end_during_a_run_is_refused_and_the_first_is_the_one_taken(tmp_path):
    """A double click on End session during a run: the first stops the run and is
    finished once it returns; the second is refused, never taken in the first's place."""
    link = _Script({3: [_end(returned=None), _end()]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=1000))

    assert frame.phase == "awaiting_return", "the first End's: no return time given"
    assert [r.name for r in frame.refusals if "a run is in progress" in r.why] == ["end"]


def test_an_end_finished_after_a_run_ends_that_session_and_never_a_later_one(tmp_path):
    """The End a run was stopped for is spent once it is finished: the next animal's
    session runs its runs and waits between them, rather than being ended by it."""
    link = _Script({3: [_end()]})
    service = _service(tmp_path, link=link)
    _step(service, _open())
    _step(service, _start(trials=1000))
    _step(service, _open(session_id="2027-01-14_02"))

    frame = _step(service, _start(trials=1))

    assert (frame.phase, frame.session_id, frame.stop_kind) == (
        "between_runs", "2027-01-14_02", "completed",
    )
    assert _kinds(service.root, "2027-01-14_02") == ["departure", "session opened"]


def test_a_service_sessions_frames_carry_the_links_own_refusals(tmp_path):
    """`Link.refused` is part of the protocol so that a packet the link could not decode
    is a refusal on every frame (`Telemetry.of`). A service session reads its link
    through `_Routed`, which hands over the real link's, and its count of those dropped."""
    link = Simulated()
    service = _service(tmp_path, link=link)
    _step(service, _open())
    link.refused.append(Refused(name="set", by="<unknown>", why="not a command"))
    link.refused_dropped = 2

    frame = _step(service)

    assert [r.why for r in frame.refusals] == ["not a command"]
    assert frame.refusals_dropped == 2


def test_a_stop_during_a_run_is_the_runs_and_ends_only_the_run(tmp_path):
    """Spec §6.1: "Stop ends the run, not the session." `_Routed` hands a run every
    command that is not the service's own."""
    link = _Script({3: [Stop(by=BY)]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=1000))

    assert (frame.phase, frame.stop_kind, frame.stopped_because) == (
        "between_runs", "operator", f"stopped by {BY}",
    )
    assert _kinds(service.root) == ["departure", "session opened"]


def test_during_a_run_the_services_own_commands_are_refused_not_queued(tmp_path):
    """Review Focus 4: a second start sent while a run is in progress -- a double click --
    is refused, never started after the first."""
    link = _Script({4: [_start(), _open(session_id="2027-01-14_02"),
                        CheckRun(by=BY, task=TASK, values={})]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start())

    assert frame.run_index == 0 and len(_runs(service.root)) == 2
    in_progress = [r.name for r in frame.refusals if "a run is in progress" in r.why]
    assert in_progress == ["start", "open", "check"]
    assert frame.preflight is None, "the check took no pre-flight"
    assert [p.name for p in service.root.iterdir()] == ["2027-01-14_01"]


def test_two_starts_in_one_pass_start_one_run(tmp_path):
    """Review Focus 4, in one pass."""
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(), _start())

    assert frame.run_index == 0 and len(_runs(service.root)) == 2
    assert "a run is already starting" in _refused(frame)[-1]


def test_an_end_in_the_same_pass_as_a_start_ends_the_session_and_starts_nothing(tmp_path):
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(), _end())

    assert isinstance(frame, Idle) and _runs(service.root) == []
    closed = service.link.published[-2]
    assert closed.phase == "closed"
    assert (closed.refusals[-1].name, closed.refusals[-1].why) == (
        "start", "the session was ended in the same pass, so the run does not start",
    )


def test_a_run_checks_for_marks_through_the_links_own_method(tmp_path):
    """Plan decision 18: `_Routed` hands a run the real link's `mark_signal`, so the
    per-frame check is the call V12 measured with nothing wrapped around it -- and a mark
    sent during a run is stamped and strobed inside it."""

    class _MarkInRun(_Script):
        def drain(self):
            if self.drains == 2:  # the run's first boundary
                self.marks.append(1)
            return super().drain()

    service = _service(tmp_path, link=_MarkInRun({}))
    _step(service, _open())
    routed = service.session.link

    assert routed.mark_signal == service.link.mark_signal
    assert routed.mark_signal.__self__ is service.link
    _step(service, _start())
    codes = service.session.card.codes
    assert codes.index(4135) < codes.index(4133) < codes.index(4136)


def test_a_run_that_faults_leaves_the_session_open_for_its_return(tmp_path, monkeypatch, capsys):
    """The b3a-1 plan, decision 14: published, recorded, said on stderr -- and the animal,
    still out, can have its return taken."""
    from wl_xcon import taskd

    real, calls = taskd.run_trial, [0]

    def faults_once(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError("the display went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", faults_once)
    service = _service(tmp_path)
    _step(service, _open())

    faulted = _step(service, _start())

    assert (faulted.phase, faulted.stop_kind) == ("between_runs", "fault")
    assert "the display went away" in capsys.readouterr().err
    _, end = _runs(service.root)
    assert end["stop_kind"] == "fault" and "the display went away" in end["stopped_because"]
    assert not [r for r in faulted.refusals if r.name == "start"], "a fault, not a refusal"
    again = _step(service, _start())
    assert (again.run_index, again.stop_kind) == (1, "completed")
    assert isinstance(_step(service, _end()), Idle)
    assert _kinds(service.root)[-2:] == ["returned", "session ended"]


def test_a_welfare_refusal_during_a_run_is_that_runs_fault_not_a_refused_start(
    tmp_path, monkeypatch, capsys
):
    """`Exceeded` is what `welfare` raises in a run (a delivery it will not make) as well
    as what `Session.run` refuses a start with. Raised once the run has started, it is
    the run's fault -- published, in its end row, and on stderr -- never a start
    refusal on the feed."""
    from wl_xcon import taskd

    real, calls = taskd.run_trial, [0]

    def refuses_once(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise Exceeded("the pump would not give it")
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", refuses_once)
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start())

    assert (frame.phase, frame.stop_kind) == ("between_runs", "fault")
    assert "the pump would not give it" in capsys.readouterr().err
    assert not [r for r in frame.refusals if r.name == "start"]
    assert _runs(service.root)[-1]["stop_kind"] == "fault"


def test_a_run_its_session_refuses_as_it_starts_is_a_refusal_and_runs_nothing(
    tmp_path, monkeypatch, capsys
):
    """`Session.run`'s own refusals -- a blocking finding, `welfare.preflight` -- stand
    behind the pre-flight. Reached, each is a refusal on the feed, not a fault: nothing
    is strobed or written, and the session waits between runs."""
    from wl_xcon import taskd

    def blocked(path):
        raise SystemExit("task refused, session not started:\n  E1: a finding")

    monkeypatch.setattr(taskd, "_load_trial", blocked)
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start())

    assert (frame.phase, frame.run_index) == ("between_runs", None)
    assert (frame.refusals[-1].name, frame.refusals[-1].why) == (
        "start", "task refused, session not started:\n  E1: a finding",
    )
    assert service.session.card.codes == [4128] and _runs(service.root) == []
    assert capsys.readouterr().err == ""


def test_a_run_that_fails_before_it_starts_says_why_on_the_feed_and_on_stderr(
    tmp_path, monkeypatch, capsys
):
    """Fix round 1 of Task 8: anything else raised before a run starts -- here its task,
    edited to fail at import between the pre-flight and the run -- is said on the feed as
    a start refusal, so a page shows why no run started, and on stderr, since it is not
    one of the refusals `Session.run` means to make. Nothing is strobed or written."""
    from wl_xcon import taskd

    def broken(path):
        raise RuntimeError("the task file changed under the run")

    monkeypatch.setattr(taskd, "_load_trial", broken)
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start())

    assert (frame.phase, frame.run_index) == ("between_runs", None)
    assert (frame.refusals[-1].name, frame.refusals[-1].why) == (
        "start", "the run did not start: RuntimeError: the task file changed under the run",
    )
    assert "RuntimeError: the task file changed under the run" in capsys.readouterr().err
    assert service.session.card.codes == [4128] and _runs(service.root) == []


def test_a_reward_size_changed_in_one_run_is_where_the_next_run_starts(tmp_path):
    """Question 1 (PI), as recommended: the bounded config is the session's, so a size a
    person set in run 0 is run 1's, and each start row says which."""
    link = _Script({3: [SetParameter(name="reward_correct", value=0.1, by=BY)]})
    service = _service(tmp_path, link=link)
    _step(service, _open())
    _step(service, _start(trials=3))

    _step(service, _start(trials=1))

    first, _, second, _ = _runs(service.root)
    assert (first["bounded"]["reward_correct"], second["bounded"]["reward_correct"]) == (0.05, 0.1)


def test_each_run_draws_its_own_seed_and_records_it(tmp_path):
    seeds = iter([11, 12])
    service = _made(_folders(tmp_path), seed=lambda: next(seeds))
    _step(service, _open())

    _step(service, _start(trials=1))
    _step(service, _start(trials=1))

    assert [row["seed"] for row in _runs(service.root) if row["event"] == "start"] == [11, 12]


def test_a_service_given_no_seed_records_a_fresh_one_in_each_runs_start_row(tmp_path):
    """Carried from Task 7: `_fresh_seed` has its caller -- the service's own runs."""
    subjects, tasks, root = _folders(tmp_path)
    service = Service(
        rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=Simulated(), wall_clock=_Wall(),
    )
    _step(service, _open())

    _step(service, _start(trials=1))

    (seed,) = [row["seed"] for row in _runs(root) if row["event"] == "start"]
    assert type(seed) is int and 0 <= seed < 2**31


# --- wlx taskd -----------------------------------------------------------------


def _taskd_args(folders, *extra, link="tcp://127.0.0.1:0,tcp://127.0.0.1:0") -> list[str]:
    subjects, tasks, root = folders
    return [
        "taskd", "--rig", RIG_FILE, "--subjects", str(subjects), "--tasks", str(tasks),
        "--root", str(root), "--link", link, *extra,
    ]


def test_wlx_taskd_refuses_an_allocation_without_the_codes_its_sessions_strobe(tmp_path):
    """Plan decision 12: the provisional allocation, used when `--allocation` is omitted,
    has none of them."""
    with pytest.raises(SystemExit, match="HEAD_FIXED, HEAD_RELEASED, PARAM_CHANGED, RUN_START, RUN_END"):
        main(_taskd_args(_folders(tmp_path)))


def test_wlx_taskd_refuses_a_folder_that_is_not_one_and_a_remote_bind(tmp_path):
    folders = _folders(tmp_path)
    missing = (folders[0], tmp_path / "no-tasks", folders[2])

    with pytest.raises(SystemExit, match="--tasks .* is not a folder"):
        main(_taskd_args(missing, "--allocation", ALLOCATION))
    with pytest.raises(SystemExit, match="refusing to bind"):
        main(_taskd_args(folders, "--allocation", ALLOCATION,
                         link="tcp://0.0.0.0:0,tcp://127.0.0.1:0"))


def test_wlx_taskd_serves_until_interrupted_and_says_what_it_left_open(tmp_path, monkeypatch, capsys):
    folders = _folders(tmp_path)

    def serve(self, stop):
        # This service reads this host's clock, not `WALL`: the departure is typed from it.
        self._open(_open(departure=time.strftime("%Y-%m-%dT%H:%M:%S")))
        raise KeyboardInterrupt

    monkeypatch.setattr(Service, "serve", serve)

    assert main(_taskd_args(folders, "--allocation", ALLOCATION)) == 130
    assert _kinds(folders[2])[-2:] == ["return not recorded", "session ended"]
    assert "the return to the cage was not recorded" in capsys.readouterr().err


def test_wlx_taskd_stopped_by_a_fault_records_why_the_return_was_not_and_raises_it(
    tmp_path, monkeypatch, capsys
):
    """Fix round 1 of Task 7: only Ctrl-C recorded the open session's return as not
    recorded. A fault out of the loop now records why too, then goes on to the caller."""
    folders = _folders(tmp_path)
    passes = []

    def step(self):
        if not passes:
            passes.append(1)
            # This service reads this host's clock, not `WALL`.
            self._open(_open(departure=time.strftime("%Y-%m-%dT%H:%M:%S")))
            return
        raise RuntimeError("the card stopped answering")

    monkeypatch.setattr(Service, "step", step)

    with pytest.raises(RuntimeError, match="the card stopped answering"):
        main(_taskd_args(folders, "--allocation", ALLOCATION))
    rows = _rows(folders[2])
    assert [row["kind"] for row in rows][-2:] == ["return not recorded", "session ended"]
    assert "RuntimeError: the card stopped answering" in rows[-2]["reason"]
    assert "the return to the cage was not recorded" in capsys.readouterr().err


# --- end to end: a real `wlx taskd` service over ZeroMQ (spec §6.5) ---------------------

#: Ruling 10, as `tests/test_serve.py`'s `CONTROL_TRIAL_BUDGET` sizes it for a session
#: with a mark socket, and each trial paced as it is there (read its comment for why).
E2E_TRIAL_BUDGET = 400
E2E_PACE_S = 0.005
#: How long a wait still looks once the service's thread has gone.
LAST_FRAME_S = 2.0


def _trial_budget(monkeypatch) -> None:
    """`taskd.run_trial` raises past the budget, so a session a mutant left running
    faults and ends; each trial sleeps `E2E_PACE_S` first. `tests/test_serve.py`'s,
    copied for the reason it copies `test_cli.py`'s."""
    from wl_xcon import taskd

    real, left = taskd.run_trial, [E2E_TRIAL_BUDGET]

    def run_trial(*args, **kwargs):
        left[0] -= 1
        if left[0] < 0:
            raise RuntimeError("this session has run more trials than its budget")
        time.sleep(E2E_PACE_S)
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", run_trial)


def _now(seconds_ago: float = 0.0) -> str:
    """A departure or a return typed as a clock time, from this host's clock now."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - seconds_ago))


class _Rig:
    """A real `wlx taskd` service on a thread, its `ZmqLink` built there; a command sender
    that waits for each acknowledgment, as `wlx serve`'s command thread does; and a
    recorder of every frame, as `tests/test_serve.py`'s `_Session.seen` reads one."""

    def __init__(self, tmp_path, monkeypatch, zmq_cleanup, *, folders=None,
                 bounds=TWELVE_HOURS, wall=None):
        from wl_xcon import dio

        _trial_budget(monkeypatch)
        self.cards: list = []
        cards = self.cards

        class _KeptCard(dio.Simulated):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                cards.append(self)

        self._card = _KeptCard
        probe = zmq_cleanup(
            ZmqLink("tcp://127.0.0.1:0", "tcp://127.0.0.1:0", "tcp://127.0.0.1:0")
        )
        self.pub, self.rep, self.mark = probe.pub_endpoint, probe.rep_endpoint, probe.mark_endpoint
        probe.close()
        self.folders = folders or _folders(tmp_path, bounds)
        self.wall = wall
        self.stop = threading.Event()
        #: Set by a test to leave without `shutdown`, as a crash would.
        self.crash = False
        self.recorder = zmq_cleanup(ZmqConsole(self.pub, None, settle_s=0.0, receive_timeout_s=0.0))
        self.commands = zmq_cleanup(ZmqCommands(self.rep))
        self.frames: list = []
        self._looked = 0
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        subjects, tasks, root = self.folders
        with ZmqLink(self.pub, self.rep, self.mark) as link:
            service = Service(
                rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
                allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
                root=root, link=link, card=self._card, wall_clock=self.wall,
            )
            try:
                service.serve(self.stop)
            finally:
                if not self.crash:
                    service.shutdown()

    def send(self, command) -> None:
        self.commands.deliver(command)

    def seen(self, predicate, seconds: float = 10.0):
        """The first frame published, from the last one this returned on, for which
        `predicate` is true -- each read as it arrives. Fails within `seconds`, or within
        `LAST_FRAME_S` once the service's thread has gone. **Ten seconds, not b2a's
        twenty**: a frame is due every `HOUSEKEEPING_S` and these runs are a few trials,
        and a mutant that stops the service answering must fail all five tests inside
        the harness's 300 s with the rest of the suite (Step 3)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            while self._looked < len(self.frames):
                frame = self.frames[self._looked]
                self._looked += 1
                if predicate(frame):
                    return frame
            try:
                self.frames.append(self.recorder.receive())
                continue
            except TimeoutError:
                pass
            if not self.thread.is_alive():
                deadline = min(deadline, time.monotonic() + LAST_FRAME_S)
            time.sleep(0.005)
        ended = "" if self.thread.is_alive() else "; the service had ended"
        raise AssertionError(f"no frame within {seconds} s satisfied {predicate}{ended}")

    def __enter__(self) -> "_Rig":
        self.thread.start()
        self.seen(lambda frame: True)  # the subscription is live
        return self

    def __exit__(self, *exc_info) -> None:
        if self.thread.is_alive():
            try:
                self.send(Stop(by="e2e-cleanup"))
            except Exception:  # noqa: BLE001 -- best-effort: a run left going is stopped
                pass
        self.stop.set()
        self.thread.join(timeout=30)
        assert not self.thread.is_alive(), "the service did not stop"


def _between(frame) -> bool:
    return isinstance(frame, Telemetry) and frame.phase == "between_runs"


def test_e2e_open_a_session_run_it_twice_and_end_it(tmp_path, monkeypatch, zmq_cleanup):
    """Spec §6.5: open a session, two runs, end it -- over the real link, with the
    simulated animal, card and pump."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup) as rig:
        rig.send(_open(departure=_now()))
        rig.seen(_between)
        for run in (0, 1):
            rig.send(_start(trials=3))
            rig.seen(lambda f, run=run: _between(f) and f.run_index == run and f.stop_kind == "completed")
        rig.send(_end())
        rig.seen(lambda f: isinstance(f, Telemetry) and f.phase == "closed")
        rig.seen(lambda f: isinstance(f, Idle))

    root = rig.folders[2]
    assert [(r["event"], r["run"]) for r in _runs(root)] == [
        ("start", 0), ("end", 0), ("start", 1), ("end", 1),
    ]
    trials = [
        json.loads(line)["run"]
        for line in (root / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text().splitlines()
    ]
    assert trials == [0, 0, 0, 1, 1, 1]
    codes = rig.cards[0].codes
    assert codes[0] == 4128 and codes[-1] == 4129
    assert codes.count(4135) == codes.count(4136) == 2
    assert _kinds(root) == ["departure", "session opened", "returned", "session ended"]


def test_e2e_the_limit_reached_between_runs_refuses_a_new_run_and_asks_for_the_return(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5. The service's wall is this host's, moved forward by the test once the
    first run has ended, so the ten-minute placeholder limit passes between runs."""
    offset = [0.0]
    with _Rig(tmp_path, monkeypatch, zmq_cleanup, bounds=TEN_MINUTES,
              wall=lambda: time.time() + offset[0]) as rig:
        rig.send(_open(departure=_now(120)))
        rig.seen(_between)
        rig.send(_start(trials=2))
        rig.seen(lambda f: _between(f) and f.run_index == 0 and f.stop_kind == "completed")
        offset[0] = 600.0

        warned = rig.seen(lambda f: _between(f) and f.duration_warning and "ceiling" in f.duration_warning)
        rig.send(_start(trials=2))
        refused = rig.seen(lambda f: _between(f) and any("out of cage" in r.why for r in f.refusals))
        rig.send(_end())
        rig.seen(lambda f: isinstance(f, Idle))

    assert warned.run_index == 0 and refused.run_index == 0, "no second run"
    assert len(_runs(rig.folders[2])) == 2


def test_e2e_a_crash_leaves_the_animal_stranded_and_the_restarted_service_waits_for_its_return(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: a crash and restart refuses a new session until the stranded animal's
    return is recorded."""
    folders = _folders(tmp_path, TWELVE_HOURS, ("B", "REFERENCE"))
    with _Rig(tmp_path, monkeypatch, zmq_cleanup, folders=folders) as first:
        first.send(_open(departure=_now()))
        first.seen(_between)
        first.crash = True

    with _Rig(tmp_path, monkeypatch, zmq_cleanup, folders=folders) as second:
        idle = second.seen(lambda f: isinstance(f, Idle))
        assert [s.session_id for s in idle.stranded] == ["2027-01-14_01"]
        second.send(_open(session_id="2027-01-14_02", animal="B", departure=_now()))
        second.seen(lambda f: isinstance(f, Idle) and any("return is not recorded" in r.why for r in f.refusals))
        second.send(_end(session_id="2027-01-14_01"))
        second.seen(lambda f: isinstance(f, Idle) and f.stranded == ())
        second.send(_open(session_id="2027-01-14_02", animal="B", departure=_now()))
        second.seen(lambda f: isinstance(f, Telemetry) and f.subject == "B")

    assert _kinds(folders[2], "2027-01-14_01") == ["departure", "session opened", "returned"]


def test_e2e_an_unknown_preflight_item_is_acknowledged_by_name_and_found_in_runs_jsonl(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup) as rig:
        rig.send(_open(departure=_now()))
        rig.seen(_between)
        rig.send(_start(acknowledged=()))
        shown = rig.seen(lambda f: _between(f) and f.preflight is not None)
        rig.send(_start(acknowledged=UNKNOWN))
        rig.seen(lambda f: _between(f) and f.run_index == 0 and f.stop_kind == "completed")

    assert [i.result for i in shown.preflight.items if i.name in UNKNOWN] == ["unknown", "unknown"]
    start = _runs(rig.folders[2])[0]
    assert {r["name"]: r["acknowledged_by"] for r in start["preflight"] if r["result"] == "unknown"} == {
        "pump calibration": BY, "eye tracker": BY,
    }


def test_e2e_the_departure_and_the_return_meet_the_terminals_rules_over_the_wire(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5: every refusal of the departure and the return, through the service as
    through the terminal -- here, one of each over the real link; `test_marks.py` and the
    unit tests above hold every one."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup) as rig:
        rig.send(_open(departure=_now(-3600)))
        rig.seen(lambda f: isinstance(f, Idle) and any("in the future" in r.why for r in f.refusals))
        far_departure = _now(2 * 3600)
        rig.send(_open(deployment="rig_chaired", departure=far_departure))
        asked = rig.seen(lambda f: isinstance(f, Idle) and f.question is not None)
        rig.send(_open(deployment="rig_chaired", departure=far_departure, answer="confirm"))
        rig.seen(_between)
        # A return before the departure: the far question is asked first (as
        # `marks.take_return` asks it), and once it is confirmed `welfare`'s own refusal speaks.
        before = _now(3 * 3600)
        rig.send(_end(returned=before))
        rig.seen(lambda f: isinstance(f, Telemetry) and f.question is not None)
        rig.send(_end(returned=before, confirm=True))
        rig.seen(lambda f: isinstance(f, Telemetry) and any("having left it at" in r.why for r in f.refusals))
        far_return = _now(3600)
        rig.send(_end(returned=far_return))
        far = rig.seen(lambda f: isinstance(f, Telemetry) and f.question is not None and f.question.answers == ("confirm", "re-type"))
        rig.send(_end(returned=far_return, confirm=True))
        rig.seen(lambda f: isinstance(f, Idle))

    assert asked.question.answers == ("confirm", "amend")
    assert far.question.answers == ("confirm", "re-type")
    kinds = _kinds(rig.folders[2])
    assert kinds == ["departure", "departure confirmed", "session opened", "returned",
                     "return confirmed", "session ended"]
