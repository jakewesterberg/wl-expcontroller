"""`wlx taskd` -- the rig service (P4d-2b spec §6): one animal's session at a time, any
number a day, opened, run and ended by a console's commands, and nothing opened while an
animal is stranded. The unit tests drive `Service.step` over an in-process link with an
injected wall; the end-to-end tests at the bottom drive a real service over ZeroMQ."""

from __future__ import annotations

import gc
import json
import shutil
import threading
import time
import weakref
from pathlib import Path

import pytest

from _rig import PATH as RIG_FILE
from _rig import RIG
from _sessions import WALL, typed
from _zmq_release import _every_zmq_context_released  # noqa: F401
from wl_xcon.cli import _load_allocation, main
from wl_xcon.link import (
    EndSession,
    Idle,
    OpenSession,
    Pause,
    Simulated,
    Stranded,
    Telemetry,
)
from wl_xcon.record import welfare_note
from wl_xcon.service import Service
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

    service.serve(stop)

    assert [name for name, _ in taken] == [
        "amend_mark", "left_cage", "head_fixed", "head_released", "returned_to_cage",
    ]
    assert {thread for _, thread in taken} == {threading.get_ident()}


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
