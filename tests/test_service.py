"""`wlx taskd` -- the rig service (P4d-2b spec §6): one animal's session at a time, any
number a day, opened, run and ended by a console's commands, and nothing opened while an
animal is stranded. The unit tests drive `Service.step` over an in-process link with an
injected wall; the end-to-end tests at the bottom drive a real service over ZeroMQ."""

from __future__ import annotations

import gc
import inspect
import json
import os
import shutil
import threading
import time
import weakref
from pathlib import Path

import pytest

from _ports import endpoints as free_endpoints
from _rig import PATH as RIG_FILE
from _rig import RIG
from _sessions import WALL, malformed_task, typed, whole_point_task
from _zmq_release import _every_zmq_context_released  # noqa: F401
from wl_xcon import preflight, resume, stranded
from wl_xcon.cli import _load_allocation, main
from wl_xcon.bounds import Exceeded
from wl_xcon.link import (
    REFUSAL_HISTORY,
    CheckRun,
    EndSession,
    Idle,
    ManualReward,
    OpenSession,
    Pause,
    Refused,
    Resume,
    ResumeSession,
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
from wl_xcon.scheduler import Block, Condition
from wl_xcon.service import Service, _fresh_seed
from wl_xcon.task import Outcome
from wl_xcon.taskd import Session
from wl_xcon.welfare import Welfare

#: wl-preproc's decoder and trial assembler, for the path through two crashes (XC-026):
#: `tests/test_taskd.py`'s guard. A missing checkout skips that test locally and fails
#: this module under `WLX_REQUIRE_PREPROC=1`, which CI sets.
_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts import events as their_events
    from wl_preproc.events.assemble import assemble as their_assemble
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). A resumed "
            f"session's stream read by wl-preproc's own code is the only check that one "
            f"recording repeats no number; skipping it would report numbers nobody read"
        ) from exc
    their_events = their_assemble = None

_contract = pytest.mark.skipif(
    their_assemble is None,
    reason="wl-preproc checkout not beside this repo; the path through its assembler cannot run",
)

ALLOCATION = "tasks/allocation.py"
EIGHT_HOURS = Path("tasks/eight_hour_bounds.py")
TEN_MINUTES = Path("tasks/reference_bounds.py")
TASK = "fixation_detection.py"
BY = "jake (box, unverified)"


class _Wall:
    """The service's wall, moved by a test: `WALL` until then."""

    def __init__(self) -> None:
        self.at = WALL

    def __call__(self) -> float:
        return self.at


def _folders(tmp_path, bounds: Path = EIGHT_HOURS, animals=("REFERENCE",)):
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


def _made(folders, *, link=None, wall=None, seed=lambda: 7, card=None) -> Service:
    subjects, tasks, root = folders
    return Service(
        rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=link if link is not None else Simulated(), seed=seed,
        wall_clock=wall if wall is not None else _Wall(),
        **({} if card is None else {"card": card}),
    )


def _service(tmp_path, *, bounds=EIGHT_HOURS, animals=("REFERENCE",), link=None, wall=None):
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


def test_the_idle_frames_refusals_start_fresh_with_each_session(tmp_path):
    """The b3a-1 final review, Minor 7: a refusal from before a session -- "send it again
    answering confirm" among them -- still showed on the idle frame after that session
    closed, reading as something pending. Each session's opening starts the idle feed
    afresh; while it is open, refusals go to its own feed."""
    service = _service(tmp_path)
    before = _step(service, *[Pause(by=BY)] * REFUSAL_HISTORY, _open(answer="confirm"))
    assert before.refusals_dropped == 1 and "none is owed" in _refused(before)[-1]

    _step(service, _open())
    after = _step(service, _end())

    assert isinstance(after, Idle)
    assert (after.refusals, after.refusals_dropped) == ((), 0)


def test_a_far_departure_amended_on_the_page_is_marked_at_the_corrected_time(tmp_path):
    """Asked first: an amendment answers the warning (Ruling 1 of the b3a-1 review)."""
    service = _service(tmp_path)
    _step(service, _open(departure=typed(5 * 3600)))

    _step(service, _open(departure=typed(5 * 3600), answer="amend",
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
    far = typed(5 * 3600)
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
        {"departure": typed(5 * 3600), "answer": "amend", "amend_to": typed(600),
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
    assert (
        "recorded by an EndSession sent over the link (the page's record return…)"
    ) in _refused(refused)[-1]
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


def test_the_idle_frame_carries_the_closed_sessions_summary_until_the_next_open(tmp_path):
    """The b3a-2 final review, I2 (spec §6.2: "The session then closes and the page shows
    its summary"): `_end` closes and drops the session in one pass, so the frames after it
    are idle. They carry that session's last frame -- its supplement owed among it --
    through a refused open, until a session opens; a session that closes without a
    summary (Ctrl-C at the terminal) then leaves none behind it."""
    service = _service(tmp_path, animals=("B", "REFERENCE"))
    _step(service, _open(delivered_today=5.0))
    _step(service, ManualReward(by=BY))

    idle = _step(service, _end())

    assert isinstance(idle, Idle)
    closed = idle.closed
    assert (closed.phase, closed.session_id, closed.subject) == ("closed", "2027-01-14_01", "REFERENCE")
    assert closed.fluid_session_ml == pytest.approx(0.05)
    assert closed.shortfall_ml == pytest.approx(max(0.0, closed.floor_ml - 5.05))
    refused = _step(service, _open(session_id="../outside"))
    assert isinstance(refused, Idle) and refused.closed == closed, "a refused open keeps it"

    _step(service, _open(session_id="2027-01-14_02", animal="B", delivered_today=None))
    service.shutdown()
    after = _step(service)

    assert isinstance(after, Idle) and after.closed is None, "cleared when the next opened"


def test_an_unknown_day_stays_unknown_in_the_closed_summary(tmp_path):
    """Unknown stays `None`, never `0` (S9a §9): a session opened with no fluid given
    today has no day's total and no supplement figure, and its summary says so."""
    service = _service(tmp_path)
    _step(service, _open(delivered_today=None))

    closed = _step(service, _end()).closed

    assert (closed.fluid_today_ml, closed.shortfall_ml) == (None, None)


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
    far = typed(5 * 3600)
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
    assert [(s.session_id, s.subject, s.left_at) for s in idle.stranded] == [
        ("2027-01-13_01", "REFERENCE", WALL - 3600)
    ]
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

    assert _step(service).stranded == (
        Stranded("2027-01-13_01", "", None, False, "its welfare record cannot be read"),
    )
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

    assert _step(service).stranded == (
        Stranded("2027-01-13_01", "", None, False, "its welfare record cannot be read"),
    )
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


def test_a_task_whose_declarations_are_malformed_fails_its_preflight_and_the_service_goes_on(
    tmp_path,
):
    """The b3a-1 final review, Important 1: a bound typed as text passes `check()`, and
    the starting values' comparison with it raised out of `step` -- `wlx taskd` recorded
    "return not recorded" and ended, mid-session, on an ordinary check. It is the
    starting values item's fail now, and the session stays open between runs."""
    service = _service(tmp_path)
    malformed_task(service.tasks)
    _step(service, _open())

    checked = _step(service, CheckRun(by=BY, task="malformed.py", values={"fix_hold": 0.3}))
    started = _step(service, _start(task="malformed.py", values={"fix_hold": 0.3}))
    codes = list(service.session.card.codes)
    ended = _step(service, _end())

    items = {i.name: i for i in checked.preflight.items}
    assert items["task checks"].result == "pass", "check() does not compare a bound"
    assert items["starting values"].result == "fail"
    assert "'fix_hold' could not be checked against its declaration: TypeError" in (
        items["starting values"].said
    )
    assert (started.phase, started.run_index) == ("between_runs", None)
    assert _runs(service.root) == [] and codes == [4128], "nothing ran"
    assert "pre-flight failed, so the run does not start: starting values: " in (
        _refused(started)[-1]
    )
    assert isinstance(ended, Idle) and _kinds(service.root)[-2:] == ["returned", "session ended"]


#: What a check of the reference task shows, item by item, when nothing raises.
CHECKED = {
    "task checks": "pass", "starting values": "pass", "bounded config": "pass",
    "out of cage": "pass", "pump calibration": "unknown", "eye tracker": "unknown",
}


@pytest.mark.parametrize(
    ("builder", "names"),
    [
        ("task", ("task checks",)),
        ("values", ("starting values",)),
        ("files", ("bounded config",)),
        ("out_of_cage", ("out of cage",)),
        ("unmeasured", ("pump calibration", "eye tracker")),
    ],
)
def test_an_item_whose_check_raises_fails_by_its_name_and_the_service_goes_on(
    tmp_path, monkeypatch, builder, names
):
    """The b3a-1 final review's ruling: whatever raises while one item is built -- today's
    items or one a later change adds -- is that item's fail, under its own name, so a
    check or a start never ends `wlx taskd` through its pre-flight. The out-of-cage item
    keeps its name when its own check raises, so the gate sees it and blocks on the
    fail, never on its absence. The other items still show."""
    service = _service(tmp_path)
    _step(service, _open())

    def broken(*_args, **_kwargs):
        raise RuntimeError("broken on purpose")

    monkeypatch.setattr(preflight, builder, broken)

    checked = _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES)))
    started = _step(service, _start())
    ended = _step(service, _end())

    shown = {i.name: i for i in checked.preflight.items}
    assert list(shown) == list(CHECKED), "every item shows, in its place"
    for name in names:
        assert shown[name].result == "fail"
        assert "RuntimeError: broken on purpose" in shown[name].said
    for name, result in CHECKED.items():
        if name not in names and not (builder == "task" and name == "starting values"):
            assert shown[name].result == result, name
    assert (started.phase, started.run_index) == ("between_runs", None)
    assert f"pre-flight failed, so the run does not start: {names[0]}: " in _refused(started)[-1]
    assert _runs(service.root) == []
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
    assert (start["by"], start["seed"], start["trials"]) == (BY, 7, 3)
    assert "unplanned" not in start, "retired by the PI, 2026-10-01 (P4d-2b spec §4.0)"
    assert end["stop_kind"] == "completed"
    codes = service.session.card.codes
    # The run's one block opens after `RUN_START` and wl-preproc's run escape -- 0x8006,
    # run 1, task code 0, checksum (XC-205) -- with `BLOCK_START` (0x8002), block 1, task
    # code 0, checksum; it closes with `BLOCK_END` (3), then wl-preproc's `RUN_END` marker
    # (4), before `RUN_END` (session-levels spec §4).
    assert codes[:11] == [4128, 4135, 0x8006, 1, 0, 0x8007, 0x8002, 1, 0, 0x8003, 32]
    assert codes[-4:] == [33, 3, 4, 4136] and 4129 not in codes


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


def test_a_run_stopped_while_paused_leaves_no_pause_on_the_frames_between_runs(tmp_path):
    """The b3a-1 final review, Minor 3: the run's own last frame keeps its pause, as the
    truth of how it ended, but between runs nothing is paused, and a frame that said
    "paused" there would be read as a run held and waiting."""
    link = _Script({3: [Pause(by=BY)], 4: [Stop(by=BY)]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start(trials=1000))

    assert any(
        isinstance(f, Telemetry) and f.phase == "running" and f.paused_at is not None
        for f in link.published
    ), "the run was paused when it stopped"
    assert (frame.phase, frame.stop_kind, frame.paused_at) == ("between_runs", "operator", None)
    assert _step(service).paused_at is None


def test_during_a_run_the_services_own_commands_are_refused_not_queued(tmp_path):
    """Review Focus 4: a second start sent while a run is in progress -- a double click --
    is refused, never started after the first."""
    link = _Script({4: [_start(), _open(session_id="2027-01-14_02"),
                        CheckRun(by=BY, task=TASK, values={}),
                        ResumeSession(by=BY, session_id="2027-01-14_01")]})
    service = _service(tmp_path, link=link)
    _step(service, _open())

    frame = _step(service, _start())

    assert frame.run_index == 0 and len(_runs(service.root)) == 2
    in_progress = [r.name for r in frame.refusals if "a run is in progress" in r.why]
    assert in_progress == ["start", "open", "check", "resume_session"]
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


# --- resume (XC-026) -------------------------------------------------------------


def _run_to_its_end(service) -> Telemetry:
    """The run the last pass accepted, at its end. `Service.step` runs a run it accepted
    in the same pass, through to its end (`_run`), so no pass is left to drive: this
    checks that it completed and the session is back between runs, rather than assuming
    it."""
    frame = service.link.published[-1]
    assert (frame.phase, frame.stop_kind, service._starting) == ("between_runs", "completed", None)
    return frame


def _crashed(folders, *session_ids, delivered_today=0.0, run=False) -> None:
    """Sessions left as a process that died leaves them: each opened by a service of its
    own -- all built before any opened, so none finds another stranded -- given a run if
    `run`, and then dropped, with no end and no return."""
    services = [_made(folders) for _ in session_ids]
    for service, session_id in zip(services, session_ids):
        _step(service, _open(session_id=session_id, delivered_today=delivered_today))
        if run:
            _step(service, _start())
            _run_to_its_end(service)


def _written(root, session_id) -> dict:
    """Every file under a session's folder, by its path there, with its bytes."""
    folder = root / session_id
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def _resume_refused(service, session_id) -> str:
    """A resume sent and refused: its sentence, once it is known that **nothing was
    written to the stranded folder** and the session is still stranded."""
    before = _written(service.root, session_id)

    frame = _step(service, ResumeSession(by=BY, session_id=session_id))

    assert _written(service.root, session_id) == before, "a refused resume wrote nothing"
    assert session_id in [s.session_id for s in service.stranded]
    assert frame.refusals[-1].name == "resume_session"
    return _refused(frame)[-1]


def test_a_stopped_session_is_resumed_and_its_numbers_go_on(tmp_path):
    folders = _folders(tmp_path)
    first = _made(folders)
    _step(first, _open())
    _step(first, _start())
    _run_to_its_end(first)
    # the process stops: a second service over the same root, with no end and no return
    second = _made(folders)
    idle = _step(second)
    assert [(s.session_id, s.resumable, s.why) for s in idle.stranded] == [("2027-01-14_01", True, "")]

    frame = _step(second, ResumeSession(by=BY, session_id="2027-01-14_01"))

    assert frame.session_id == "2027-01-14_01" and frame.phase == "between_runs"
    assert frame.resumed_at == WALL
    assert second.stranded == []
    _step(second, _start())
    _run_to_its_end(second)
    runs = _runs(folders[2])
    assert [row["run"] for row in runs if row["event"] == "start"] == [0, 1]


def _kept_cards() -> tuple[list, type]:
    """A card class whose every instance is kept, in the order the services build them,
    so their codes read as one recording; and the list they are kept in."""
    from wl_xcon import dio

    cards: list = []

    class _Kept(dio.Simulated):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            cards.append(self)

    return cards, _Kept


@_contract
def test_a_run_that_raised_before_its_start_row_leaves_no_number_a_resume_repeats(
    tmp_path, monkeypatch, capsys
):
    """The final review's I3, as it was driven: run 2 raises after `Levels.start_run` and
    before its start row is written -- its `Scheduler`, here -- which the service contains;
    run 3 runs; the process stops. The resumed session's next run is run 4: its numbers
    are rebuilt from those the start rows recorded, never by counting the rows, which
    strobed run 3 twice in one recording."""
    from wl_xcon import taskd

    real, calls = taskd.Scheduler, [0]

    def fails_once(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError("a scheduler that fails once")
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "Scheduler", fails_once)
    cards, kept = _kept_cards()
    folders = _folders(tmp_path)
    first = _made(folders, card=kept)
    _step(first, _open())
    for _ in range(3):
        _step(first, _start())
    assert "a scheduler that fails once" in capsys.readouterr().err
    second = _made(folders, card=kept)
    _step(second, ResumeSession(by=BY, session_id="2027-01-14_01"))

    _step(second, _start())

    _run_to_its_end(second)
    stream = [(i * 0.001, word) for i, word in enumerate(w for card in cards for w in card.codes)]
    events = their_events.decode_stream(stream)
    assert [e.words for e in events if isinstance(e, their_events.PayloadEvent)
            and e.escape is their_events.Escape.RUN_START] == [(1, 0), (3, 0), (4, 0)]
    assert [run.run_number for run in their_assemble(events).runs] == [1, 3, 4]
    assert [(row["run"], row["run_in_session"]) for row in _runs(folders[2])
            if row["event"] == "start"] == [(0, 1), (2, 3), (3, 4)]


@pytest.mark.parametrize("today", [40.0, None])
def test_a_resumed_sessions_day_takes_the_earlier_fluid_from_its_record(tmp_path, today):
    """The day's earlier fluid is `config.json`'s `already_delivered_today`, as given at
    open: never read afresh, and never `0.0` for a day nobody measured -- `None` stays
    `None`, and the day's total with it (spec §4)."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01", delivered_today=today, run=True)
    service = _made(folders)

    frame = _step(service, ResumeSession(by=BY, session_id="2027-01-14_01"))

    assert service.session.welfare.already_today == today
    assert frame.fluid_session_ml > 0, "the run before the crash gave fluid"
    if today is None:
        assert (frame.fluid_today_ml, frame.shortfall_ml) == (None, None)
    else:
        assert frame.fluid_today_ml == pytest.approx(today + frame.fluid_session_ml)


def test_one_stranded_session_is_resumed_while_another_stays_stranded(tmp_path):
    """Plan ruling 7 (spec §5): each stranded session is resumed or ended on its own, so
    another still stranded is no bar to a resume -- and is still a bar to a new open.
    A resumed session starts the idle feed and the last summary afresh, as an open does."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01", "2027-01-14_02")
    service = _made(folders)
    assert [s.session_id for s in _step(service).stranded] == ["2027-01-14_01", "2027-01-14_02"]
    _step(service, _open(session_id="2027-01-14_03"))
    assert service.refusals != []

    frame = _step(service, ResumeSession(by=BY, session_id="2027-01-14_02"))

    assert (frame.session_id, frame.resumed_at) == ("2027-01-14_02", WALL)
    assert [s.session_id for s in service.stranded] == ["2027-01-14_01"]
    assert service.refusals == [], "the idle feed starts afresh with the resumed session"
    idle = _step(service, _end())
    assert isinstance(idle, Idle) and [s.session_id for s in idle.stranded] == ["2027-01-14_01"]
    assert idle.closed is not None and idle.closed.session_id == "2027-01-14_02"
    refused = _step(service, _open(session_id="2027-01-14_03"))
    assert isinstance(refused, Idle)
    assert "no session opens while an animal's return is not recorded" in _refused(refused)[-1]
    assert not (folders[2] / "2027-01-14_03").exists()

    frame = _step(service, ResumeSession(by=BY, session_id="2027-01-14_01"))

    assert frame.session_id == "2027-01-14_01" and service.stranded == []
    assert (service.refusals, service.closed) == ([], None)


def test_an_open_refused_for_a_stranded_animal_says_it_can_be_resumed_or_ended(tmp_path):
    folders = _folders(tmp_path)
    _strand(folders[2])

    refused = _step(_made(folders), _open())

    assert _refused(refused)[-1].endswith(
        ". Resume it, or record its return with End session, naming its session"
    )


def test_a_resume_while_a_session_is_open_is_refused_and_writes_nothing(tmp_path):
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01", "2027-01-14_02")
    service = _made(folders)
    _step(service, ResumeSession(by=BY, session_id="2027-01-14_01"))

    why = _resume_refused(service, "2027-01-14_02")

    assert why == (
        "a session is open (2027-01-14_01); a stranded session is resumed only while none is"
    )
    assert service.session.spec.session_id == "2027-01-14_01"


def test_a_stranded_session_whose_config_is_torn_cannot_be_resumed_and_says_so(tmp_path):
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01")
    config = folders[2] / "2027-01-14_01" / "xcon" / "config.json"
    config.write_text(config.read_text()[:40])
    service = _made(folders)

    (found,) = _step(service).stranded
    assert found.resumable is False and "config.json" in found.why

    why = _resume_refused(service, "2027-01-14_01")

    assert "config.json" in why and why.endswith("end it instead")


def test_a_stranded_session_with_no_config_cannot_be_resumed_and_says_so(tmp_path):
    """A record from before the service kept one: `_strand` writes only the departure."""
    folders = _folders(tmp_path)
    _strand(folders[2])
    service = _made(folders)

    (found,) = _step(service).stranded
    assert (found.left_at, found.resumable) == (WALL - 3600, False) and "config.json" in found.why

    assert "config.json" in _resume_refused(service, "2027-01-13_01")


def test_a_stranded_session_recorded_before_xc026_cannot_be_resumed_and_says_why(tmp_path):
    """Spec §4: its fluid so far cannot be known, and is never taken as zero."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01", run=True)
    path = folders[2] / "2027-01-14_01" / "xcon" / "config.json"
    config = json.loads(path.read_text())
    del config["already_delivered_today"]
    path.write_text(json.dumps(config))
    service = _made(folders)

    (found,) = _step(service).stranded
    assert (found.resumable, found.why) == (False, resume.PREDATES)

    assert _resume_refused(service, "2027-01-14_01") == resume.PREDATES


def test_a_stranded_session_past_its_out_of_cage_limit_is_refused_with_welfares_sentence(tmp_path):
    """Plan ruling 6: asked of `must_stop` on the recorded departure, before anything is
    written; the page then asks for the return."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01")
    wall = _Wall()
    service = _made(folders, wall=wall)
    (found,) = service.stranded
    wall.at = found.left_at + 28_800 + 1

    why = _resume_refused(service, "2027-01-14_01")

    assert why == (
        "out_of_cage: subject 'REFERENCE' has been out of its cage 28801 s against a "
        "ceiling of 28800; record its return with End session instead"
    )


def test_a_session_refused_past_its_limit_is_then_offered_only_end(tmp_path):
    """Spec §5 (fix round 1 of Task 7): past its out-of-cage limit a resume is refused,
    and "the page then asks for the return, and only *end* is offered". The entry is
    marked not resumable, with the refusal's sentence; a second resume, sent later, is
    refused with that same sentence, not asked again, and writes nothing; *end session…*
    still takes the return."""
    from _frames import view
    from wl_xcon.web import fragments

    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01")
    wall = _Wall()
    service = _made(folders, wall=wall)
    (found,) = service.stranded
    wall.at = found.left_at + 28_800 + 1
    why = _resume_refused(service, "2027-01-14_01")

    idle = _step(service)

    assert [(s.session_id, s.resumable, s.why) for s in idle.stranded] == [
        ("2027-01-14_01", False, why),
    ]
    banners = fragments(idle, view())["banners"]
    assert 'data-resume=' not in banners and 'data-return="2027-01-14_01"' in banners
    wall.at += 600
    assert _resume_refused(service, "2027-01-14_01") == why, "marked once, never re-asked"
    _step(service, _end(session_id="2027-01-14_01"))
    assert service.stranded == [], "end session… still takes the return"
    assert _kinds(folders[2])[-1] == "returned"


@pytest.mark.parametrize(
    ("was", "now", "named"),
    [
        ("maximum=10.0", "maximum=9.0", "reward_correct"),
        ('Floor(value=20.0, unit="mL")', 'Floor(value=25.0, unit="mL")', "daily_fluid"),
        (
            '"out_of_cage": Ceiling(',
            '"reward_error": Ceiling(value=0.0, maximum=1.0, unit="mL"),\n        "out_of_cage": Ceiling(',
            "reward_error",
        ),
    ],
)
def test_a_stranded_session_whose_animals_bounds_changed_is_refused_naming_what(
    tmp_path, was, now, named
):
    """Plan ruling 3: what `config.json` recorded at open and the bounds loaded now must
    be equal -- a changed ceiling, a changed floor, or an entry added -- since a session's
    limits do not change across a restart."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01")
    path = folders[0] / "REFERENCE" / "bounds.py"
    assert path.read_text().count(was) == 1
    path.write_text(path.read_text().replace(was, now))
    # `cli._load_bounds` loads through Python's bytecode cache, which a same-size edit in
    # the same second as the open's load does not invalidate (`20.0` to `25.0`).
    shutil.rmtree(path.parent / "__pycache__", ignore_errors=True)
    service = _made(folders)

    why = _resume_refused(service, "2027-01-14_01")

    assert why == (
        f"'REFERENCE''s bounds changed since session 2027-01-14_01 opened ({named}); a "
        f"session's limits do not change across a restart, so end it instead"
    )
    # A plain refusal (fix round 1 of Task 7): restoring the animal's file makes the
    # session resumable again, so it is never marked otherwise.
    assert [(s.resumable, s.why) for s in _step(service).stranded] == [(True, "")]


def test_a_resume_naming_no_stranded_session_is_refused_naming_it(tmp_path):
    service = _service(tmp_path)

    frame = _step(service, ResumeSession(by=BY, session_id="2027-01-14_09"))

    assert _refused(frame) == ["no stranded session '2027-01-14_09' can be resumed"]
    assert list(service.root.iterdir()) == []


def test_a_stranded_session_whose_welfare_record_cannot_be_read_is_refused_saying_so(tmp_path):
    folders = _folders(tmp_path)
    directory = _strand(folders[2])
    with (directory / "welfare_notes.jsonl").open("a") as handle:
        handle.write('{"kind": "retur')
    service = _made(folders)

    why = _resume_refused(service, "2027-01-13_01")

    assert why == (
        "no stranded session '2027-01-13_01' can be resumed: its welfare record cannot be read"
    )


@pytest.mark.parametrize("where", ["relative", "absolute"])
def test_a_resumable_record_whose_animal_is_no_folder_name_runs_nothing_outside_subjects(
    tmp_path, where
):
    """`_close_stranded`'s rule (fix round 1 of Task 7, Critical), for a resume: the
    record's animal becomes a path, and the bounded config there is code. `wlx run
    --subject` takes any text, so a record may name `../outside` or an absolute path;
    nothing outside `--subjects` runs for it, and nothing is written."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01")
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = tmp_path / "ran.txt"
    (outside / "bounds.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
    )
    subject = "../outside" if where == "relative" else str(outside)
    directory = folders[2] / "2027-01-14_01" / "xcon"
    config = json.loads((directory / "config.json").read_text())
    (directory / "config.json").write_text(json.dumps({**config, "subject": subject}))
    rows = [{**row, "subject": subject} for row in _rows(folders[2])]
    (directory / "welfare_notes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    service = _made(folders)
    assert [(s.subject, s.resumable) for s in service.stranded] == [(subject, True)]

    why = _resume_refused(service, "2027-01-14_01")

    assert not marker.exists(), "a file outside --subjects ran"
    assert "one folder name" in why and repr(subject) in why


# The controller's ruling on Task 4 (2026-10-01): a record the service cannot read fails
# closed, as `stranded.find` always has -- it never stops `wlx taskd` starting, and never
# crashes `step()`.


def _infinite_trial_number(directory) -> None:
    rows = [json.loads(line) for line in (directory / "trial_starts.jsonl").read_text().splitlines()]
    rows[0]["trial_number"] = float("inf")
    (directory / "trial_starts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _bounds_as(bounds):
    def damage(directory) -> None:
        config = json.loads((directory / "config.json").read_text())
        config["bounds"] = bounds(config["bounds"])
        (directory / "config.json").write_text(json.dumps(config))
    return damage


@pytest.mark.parametrize(
    ("damage", "said"),
    [
        (_infinite_trial_number, "OverflowError"),
        (_bounds_as(lambda b: {"ceilings": b["ceilings"]}), "config.json"),
        (_bounds_as(lambda b: [b]), "config.json"),
    ],
    ids=["Infinity in trial_starts", "bounds without minima", "bounds not a mapping"],
)
def test_a_record_the_service_cannot_read_is_stranded_unresumable_and_never_stops_it(
    tmp_path, damage, said
):
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01", run=True)
    damage(folders[2] / "2027-01-14_01" / "xcon")

    service = _made(folders)

    (found,) = _step(service).stranded
    assert (found.session_id, found.left_at is not None, found.resumable) == (
        "2027-01-14_01", True, False,
    )
    assert said in found.why
    assert said in _resume_refused(service, "2027-01-14_01")
    assert isinstance(_step(service), Idle), "the service goes on"


def test_a_record_naming_two_animals_is_refused_before_anything_is_built(tmp_path, monkeypatch):
    """`config.json`'s animal is the one `_build` loads bounds for; the departure row's is
    the one the out-of-cage check holds them to. A record that disagrees with itself is
    refused, naming both, before either becomes a path."""
    folders = _folders(tmp_path, animals=("B", "REFERENCE"))
    _crashed(folders, "2027-01-14_01")
    path = folders[2] / "2027-01-14_01" / "xcon" / "config.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "subject": "B"}))
    service = _made(folders)
    monkeypatch.setattr(Service, "_build", lambda *_a, **_k: pytest.fail("a session was built"))

    why = _resume_refused(service, "2027-01-14_01")

    assert why == (
        "session 2027-01-14_01's config.json names 'B' and its departure names "
        "'REFERENCE'; a record that disagrees with itself is not resumed, so end it instead"
    )
    assert isinstance(_step(service), Idle), "the service goes on"


@pytest.mark.parametrize("where", ["restore", "must_stop"])
def test_what_the_out_of_cage_check_raises_is_a_refusal_never_the_services_end(
    tmp_path, monkeypatch, where
):
    """`stranded.restore` refuses a record it cannot hold a return to, by raising
    `Exceeded`; whatever it or `must_stop` raises that way is said, and nothing written."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01")
    service = _made(folders)

    def refuses(*_args, **_kwargs):
        raise Exceeded("the out-of-cage check refused it, in this test")

    monkeypatch.setattr(*((stranded, "restore") if where == "restore" else (Welfare, "must_stop")), refuses)

    assert _resume_refused(service, "2027-01-14_01") == "the out-of-cage check refused it, in this test"
    assert isinstance(_step(service), Idle), "the service goes on"


def _start_row_bounded_as(value):
    def damage(directory) -> None:
        rows = [json.loads(line) for line in (directory / "runs.jsonl").read_text().splitlines()]
        rows[0]["bounded"]["reward_correct"] = value
        (directory / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return damage


def _negative_fluid(directory) -> None:
    lines = [json.loads(line) for line in (directory / "trials.jsonl").read_text().splitlines()]
    lines[0]["fluid_ml"] = -1000.0
    (directory / "trials.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))


@pytest.mark.parametrize(
    ("damage", "said"),
    [
        (_start_row_bounded_as(100.0), "'reward_correct' may not exceed 10.0 mL (asked for 100.0)"),
        (_negative_fluid, "a resumed session's commanded fluid is -"),
        (_start_row_bounded_as("0.05"), "must be real number, not str"),
    ],
    ids=["bounded over its maximum", "negative fluid", "bounded not a number"],
)
def test_a_record_the_session_will_not_take_back_is_a_refusal_never_the_services_end(
    tmp_path, damage, said
):
    """Review fix round 1, Important 1: `Session.resume` refuses a value its welfare
    rules refuse -- before its first write -- and a record `find` offers to resume can
    still hold one. Refused, saying it; nothing written; the service goes on."""
    folders = _folders(tmp_path)
    _crashed(folders, "2027-01-14_01", run=True)
    damage(folders[2] / "2027-01-14_01" / "xcon")
    service = _made(folders)
    (found,) = _step(service).stranded
    assert found.resumable, "a record find offers to resume"

    assert said in _resume_refused(service, "2027-01-14_01")
    assert isinstance(_step(service), Idle), "the service goes on"


@pytest.mark.parametrize("sent", ["open", "resume_session"])
@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("BOUNDS = not_defined_anywhere\n", "the session could not be built: NameError: "),
        ("x = 1\n", "must define BOUNDS"),
    ],
    ids=["raises", "defines no BOUNDS"],
)
def test_an_animal_whose_bounds_will_not_load_is_refused_alike_by_an_open_and_a_resume(
    tmp_path, sent, text, said
):
    """Review fix round 1, Important 2: `_open` and `_resume` refuse a session they
    cannot build through one handler (`_built`), so they say the same thing, under
    their own kind, and neither ends the service."""
    folders = _folders(tmp_path)
    if sent == "resume_session":
        _crashed(folders, "2027-01-14_01")
    (folders[0] / "REFERENCE" / "bounds.py").write_text(text)
    service = _made(folders)

    if sent == "open":
        frame = _step(service, _open())
        assert list(service.root.iterdir()) == []
        why = frame.refusals[-1].why
        assert frame.refusals[-1].name == "open"
    else:
        why = _resume_refused(service, "2027-01-14_01")

    assert said in why
    assert isinstance(_step(service), Idle), "the service goes on"


# --- the path through two crashes (XC-026 spec §7; plan Task 7) ------------------


def _xy_plan() -> list[Block]:
    """Blocks X then Y, two trials each, every trial paying: four trials a run, and the
    run's third trial opens its second block."""
    return [
        Block(name=name, conditions=[Condition(name.lower(), {}, target=2)],
              counts_toward=frozenset(Outcome))
        for name in ("X", "Y")
    ]


def _dying(monkeypatch, *, ran: int, began: int) -> list[float]:
    """`taskd.run_trial`, counted across every service in the test. The trial of call
    `ran` runs its frames, and then its process dies: before its outcome, its
    `TRIAL_END` or its line. The trial of call `began` dies as it begins, before its first
    frame. **Each dies by `KeyboardInterrupt`**, which `Service._run` does not contain
    (it is no `Exception`), so it leaves `Service.step` in the middle of the trial; the
    test then drops the service with no `shutdown` -- no end, no return -- as `_Rig`'s
    `crash` leaves one. Unlike a kill, `Session.run`'s `finally` still writes the run's end
    row; `resume.read` reads only start rows, so what a resume restores is the same.
    Returns what each death took with it, in order: the fluid its trial's frames
    commanded, which no line holds."""
    from wl_xcon import taskd

    real, calls, lost = taskd.run_trial, [0], []

    def run_trial(*args, **kwargs):
        calls[0] += 1
        if calls[0] == began:
            lost.append(0.0)
            raise KeyboardInterrupt
        if calls[0] != ran:
            return real(*args, **kwargs)
        welfare = kwargs["effects"].welfare
        before = welfare.commanded
        real(*args, **kwargs)
        lost.append(welfare.commanded - before)
        raise KeyboardInterrupt

    monkeypatch.setattr(taskd, "run_trial", run_trial)
    return lost


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _recorded_fluid(xcon: Path) -> float:
    """The fluid so far as the record holds it (spec §4): every trial line's `fluid_ml`,
    then every hand reward's `ml`, summed in `resume.read`'s order."""
    lines = _jsonl(xcon / "trials.jsonl")
    hand = [row for row in _jsonl(xcon / "controls.jsonl") if row["kind"] == "reward"]
    return sum(float(line["fluid_ml"]) for line in lines) + sum(float(row["ml"]) for row in hand)


def _killed(xcon: Path, run: int) -> None:
    """The record exactly as a kill leaves it (spec §3: "a start row and no end row";
    fix round 1 of Task 7): `Session.run`'s `finally` wrote the interrupted run's end row,
    which a SIGKILL would not have, so it is taken out again."""
    rows = _jsonl(xcon / "runs.jsonl")
    assert (rows[-1]["event"], rows[-1]["run"], rows[-1]["stop_kind"]) == ("end", run, "operator")
    (xcon / "runs.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows[:-1]))


@_contract
def test_two_crashes_and_their_resumes_repeat_no_number_in_one_recording(tmp_path, monkeypatch):
    """XC-026, the path and not the piece (spec §7; the plan's Review Focus 1, 3 and 4).
    One rig-fixed session, three processes, one sync-box recording:

    1. the first opens it and runs run 1 on a block plan, its reward size changed during
       it and a hand reward given while it is paused; a hand reward between runs; then
       run 2, whose third trial, the first of block 4, runs its frames and dies;
    2. the second finds it stranded, resumes it, gives a hand reward, and runs run 3,
       whose second trial dies as it begins;
    3. the third resumes it again, runs run 4, a setting changed in it, and ends it.

    Every card's codes, in order, are one stream, read by wl-preproc's own
    `decode_stream` and `assemble`."""
    from wl_xcon import dio, taskd
    from wl_xcon import service as service_module

    cards: list = []

    class _KeptCard(dio.Simulated):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            cards.append(self)

    # The block plan a run is given until XC-207 gives the service one.
    monkeypatch.setattr(
        service_module, "RunSpec", lambda **fields: taskd.RunSpec(**fields, blocks=_xy_plan())
    )
    lost = _dying(monkeypatch, ran=7, began=9)
    folders = _folders(tmp_path)
    xcon = folders[2] / "2027-01-14_01" / "xcon"
    resumed = ResumeSession(by=BY, session_id="2027-01-14_01")

    def wall(seconds_later: float) -> _Wall:
        moved = _Wall()
        moved.at = WALL + seconds_later
        return moved

    # --- the first process ---
    # Run 1's seed gives rewarded and unrewarded trials; run 2's rewards its third, so the
    # first death takes a commanded reward with it.
    seeds = iter([7, 6])
    first = _made(folders, card=_KeptCard, seed=lambda: next(seeds), link=_Script({
        3: [SetParameter(name="reward_correct", value=0.1, by=BY)],
        5: [Pause(by=BY)], 6: [ManualReward(by=BY)], 7: [Resume(by=BY)],
    }))
    _step(first, _open())
    _step(first, _start())
    _run_to_its_end(first)
    _step(first, ManualReward(by=BY))
    with pytest.raises(KeyboardInterrupt):
        _step(first, _start())
    _killed(xcon, run=1)
    departure = first.session.welfare.left_cage_wall_at
    died_with = first.session.welfare.session_total()
    assert lost[0] > 0, "the first death took a reward its trial commanded, and no line holds it"

    # --- the second process: resumed, a hand reward, run 3 dies ---
    second = _made(folders, card=_KeptCard, wall=wall(600))
    assert [(s.session_id, s.resumable, s.left_at) for s in _step(second).stranded] == [
        ("2027-01-14_01", True, departure),
    ]
    frame = _step(second, resumed)
    assert (frame.phase, frame.run_index, frame.resumed_at) == ("between_runs", 1, WALL + 600)
    welfare = second.session.welfare
    assert welfare.left_cage_wall_at == departure, "the clock runs from the first departure"
    assert welfare.session_total() == _recorded_fluid(xcon)
    assert welfare.session_total() == pytest.approx(died_with - lost[0])
    assert second.session.spec.bounds.value("reward_correct") == 0.1
    _step(second, ManualReward(by=BY))
    with pytest.raises(KeyboardInterrupt):
        _step(second, _start())
    _killed(xcon, run=2)
    died_with = welfare.session_total()

    # --- the third process: resumed again, run 4 to its end, and the session ended ---
    third = _made(folders, card=_KeptCard, wall=wall(1200), link=_Script({
        4: [SetParameter(name="reward_correct", value=0.08, by=BY)],
    }))
    frame = _step(third, resumed)
    assert (frame.phase, frame.run_index, frame.resumed_at) == ("between_runs", 2, WALL + 1200)
    welfare = third.session.welfare
    assert welfare.left_cage_wall_at == departure, "the clock runs from the first departure"
    assert welfare.session_total() == _recorded_fluid(xcon)
    assert welfare.session_total() == pytest.approx(died_with - lost[1])
    assert third.session.spec.bounds.value("reward_correct") == 0.1, "run 1's size, twice carried"
    assert welfare.last_delivery_wall_at == WALL + 600, "the second process's hand reward"
    _step(third, _start())
    _run_to_its_end(third)
    assert welfare.session_total() == pytest.approx(_recorded_fluid(xcon)), "each reward once"
    assert isinstance(_step(third, _end()), Idle)

    # --- the recording, as wl-preproc reads it ---
    assert len(cards) == 3, "one card a process"
    stream = [(i * 0.001, word) for i, word in enumerate(w for card in cards for w in card.codes)]
    events = their_events.decode_stream(stream)
    assembly = their_assemble(events)
    escape = their_events.Escape

    def payloads(which) -> list[tuple]:
        return [e.words for e in events
                if isinstance(e, their_events.PayloadEvent) and e.escape is which]

    codes = [e.code for e in events if isinstance(e, their_events.SimpleEvent)]
    assert assembly.errors == []
    # No trial, block or run number repeats: as strobed, and as assembled.
    assert [(high << 16) | low for high, low in payloads(escape.TRIAL_NUMBER)] == list(range(1, 14))
    assert [trial.trial_id for trial in assembly.trials] == list(range(1, 14))
    assert [block for block, _task in payloads(escape.BLOCK_START)] == list(range(1, 8))
    assert [block.block_id for block in assembly.blocks] == list(range(1, 8))
    assert payloads(escape.RUN_START) == [(1, 0), (2, 0), (3, 0), (4, 0)]
    assert [run.run_number for run in assembly.runs] == [1, 2, 3, 4]
    # The two that died never closed: their trial, their block and their run.
    assert [trial.trial_id for trial in assembly.trials if trial.end_s is None] == [7, 9]
    assert [block.block_id for block in assembly.blocks if block.end_s is None] == [4, 5]
    assert [run.run_number for run in assembly.runs if run.end_s is None] == [2, 3]
    assert codes.count(4137) == 2, "SESSION_RESUMED, once at each resume"
    # Spec §8a item 2: a rig-fixed resume fixes the head again, with no release between:
    # the one release comes after the last fixation.
    last_fixed = len(codes) - 1 - codes[::-1].index(4128)
    assert codes.index(4129) > last_fixed, "no HEAD_RELEASED before the last HEAD_FIXED"
    assert (codes.count(4128), codes.count(4129)) == (3, 1)

    # --- the record ---
    lines = _jsonl(xcon / "trials.jsonl")
    numbers = [line["trial_number"] for line in lines]
    assert numbers == sorted(set(numbers)), "strictly increasing"
    started = [row["trial_number"] for row in _jsonl(xcon / "trial_starts.jsonl")]
    assert started == list(range(1, 14))
    assert sorted(set(range(1, numbers[-1] + 1)) - set(numbers)) == [7, 9], "the gaps are the deaths"
    # Each line joins the trial its number names, inside the block and the run it names.
    for line in lines:
        (trial,) = [t for t in assembly.trials if t.trial_id == line["trial_number"]]
        (block,) = [b for b in assembly.blocks if b.start_s <= trial.start_s <= b.last_s]
        (run,) = [r for r in assembly.runs if r.start_s <= trial.start_s <= r.last_s]
        assert (block.block_id, run.run_number) == (line["block_in_session"], line["run_in_session"])
    assert [(row["event"], row["run"]) for row in _jsonl(xcon / "runs.jsonl")] == [
        ("start", 0), ("end", 0), ("start", 1), ("start", 2), ("start", 3), ("end", 3),
    ], "each run that died has its start row and no end row, as a kill leaves it"
    runs = [row for row in _jsonl(xcon / "runs.jsonl") if row["event"] == "start"]
    assert [row["bounded"]["reward_correct"] for row in runs] == [0.05, 0.1, 0.1, 0.1]
    changes = _jsonl(xcon / "parameter_changes.jsonl")
    assert [(row["sequence"], row["run"]) for row in changes] == [(1, 0), (2, 3)], "none repeats"
    hand =[row["where"] for row in _jsonl(xcon / "controls.jsonl") if row["kind"] == "reward"]
    assert [where.split(" before")[0] for where in hand] == [
        "given while paused", "given between runs", "given between runs",
    ]
    assert _kinds(folders[2]) == [
        "departure", "session opened", "session resumed", "session resumed", "returned",
        "session ended",
    ]
    assert {(row["by"], row["how"]) for row in _rows(folders[2]) if row["kind"] == "session resumed"} == {
        (BY, "wlx taskd"),
    }


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


def test_wlx_taskd_refuses_a_folder_that_is_not_one_and_a_remote_bind(tmp_path, monkeypatch):
    folders = _folders(tmp_path)
    missing = (folders[0], tmp_path / "no-tasks", folders[2])

    def served(self, stop):
        # Both refusals come before the service serves. Without this, a refusal that
        # stopped refusing would serve until interrupted, and the test would hang
        # rather than fail: the b3a-1 full sweep's `_binds_beyond_this_machine`
        # timeout (2026-09-30).
        raise AssertionError("wlx taskd served when it should have refused")

    monkeypatch.setattr(Service, "serve", served)

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
                 bounds=EIGHT_HOURS, wall=None):
        from wl_xcon import dio

        _trial_budget(monkeypatch)
        self.cards: list = []
        cards = self.cards

        class _KeptCard(dio.Simulated):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                cards.append(self)

        self._card = _KeptCard
        self.pub, self.rep, self.mark = free_endpoints(3)
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
        try:
            self.seen(lambda frame: True)  # the subscription is live
        except BaseException:
            # `with` does not call `__exit__` when `__enter__` raises: stop the service here,
            # or its thread keeps its ports until the process ends.
            self.__exit__(None, None, None)
            raise
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
        json.loads(line)
        for line in (root / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text().splitlines()
    ]
    # Each trial's number counts on across the session's two runs (XC-155).
    assert [(trial["run"], trial["trial_number"]) for trial in trials] == [
        (0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (1, 6),
    ]
    codes = rig.cards[0].codes
    assert codes[0] == 4128 and codes[-1] == 4129
    assert codes.count(4135) == codes.count(4136) == 2
    # Each of the six trials opened and closed in the stream (XC-155); numbered 1..6, so
    # no payload word is 32 or 33.
    assert codes.count(32) == codes.count(33) == 6
    # Each run is one block, numbered on across the session, and a run in wl-preproc's
    # terms too (XC-205): after its `RUN_START`, the run escape (0x8006, its number, task
    # code 0, checksum), then its `BLOCK_START`; before its `RUN_END`, its `BLOCK_END` and
    # then the `RUN_END` marker (4) (session-levels spec §4). Read beside the
    # allocation's run codes, which no payload word or checksum here equals, and never
    # found by their own values: trial 3's escape carries a 3 and a 0x8002, and trial
    # 4's a 4.
    assert [codes[i + 1 : i + 9] for i, code in enumerate(codes) if code == 4135] == [
        [0x8006, 1, 0, 0x8007, 0x8002, 1, 0, 0x8003],
        [0x8006, 2, 0, 0x8004, 0x8002, 2, 0, 0x8000],
    ]
    assert [codes[i - 2 : i] for i, code in enumerate(codes) if code == 4136] == [[3, 4], [3, 4]]
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
    folders = _folders(tmp_path, EIGHT_HOURS, ("B", "REFERENCE"))
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


def test_e2e_a_departure_past_the_ceiling_is_refused_by_welfares_sentence_and_marks_nothing(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5, through the service over the wire: no question, no session folder."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup, bounds=TEN_MINUTES) as rig:
        rig.send(_open(departure=_now(900)))
        refused = rig.seen(lambda f: isinstance(f, Idle) and any("at or outside the limit" in r.why for r in f.refusals))

    assert refused.question is None
    assert list(rig.folders[2].iterdir()) == []


def test_e2e_an_amendment_with_no_reason_or_no_sender_is_refused_and_marks_nothing(
    tmp_path, monkeypatch, zmq_cleanup
):
    """Spec §6.5. The amendment's actor is the command's `by`, which the wire's `_actor`
    refuses when blank before the service sees it, so a blank name is refused there (the
    link's sentence) and a blank reason by `welfare.amend_mark` (the service's)."""
    with _Rig(tmp_path, monkeypatch, zmq_cleanup) as rig:
        far = _now(5 * 3600)
        amend = dict(departure=far, answer="amend", amend_to=_now(600))
        rig.send(_open(departure=far))
        rig.seen(lambda f: isinstance(f, Idle) and f.question is not None)
        rig.send(_open(amend_reason="", **amend))
        no_reason = rig.seen(lambda f: isinstance(f, Idle) and any("no reason" in r.why for r in f.refusals))
        rig.send(_open(by="  ", amend_reason="typed 09:30 for 17:30", **amend))
        no_sender = rig.seen(lambda f: isinstance(f, Idle) and any("must say who sent it" in r.why for r in f.refusals))
        assert no_reason.question is not None and no_sender.question is not None
        assert list(rig.folders[2].iterdir()) == []
        rig.send(_open(amend_reason="typed 09:30 for 17:30", **amend))
        rig.seen(_between)
        rig.send(_end())
        rig.seen(lambda f: isinstance(f, Idle))

    assert _kinds(rig.folders[2]) == ["departure", "departure amended", "session opened",
                                      "returned", "session ended"]


def test_a_run_started_with_no_values_starts_from_the_tasks_own(tmp_path):
    """What a page sends (P4d-2b spec §6.2: "Starting values are the task's own"): no
    values, and the run starts, and runs to its end, at the task's own."""
    service = _service(tmp_path)
    _step(service, _open())

    frame = _step(service, _start(values={}))

    assert (frame.phase, frame.run_index, frame.stop_kind) == ("between_runs", 0, "completed")
    assert _runs(service.root)[0]["resolved"]["fix_hold"] == 0.3


def test_the_hand_reward_works_between_runs_and_while_the_return_is_awaited(tmp_path):
    """PI, 2026-09-29 (P4d-2b spec §6.0), through the service: `tasks/eight_hour_bounds.py`'s
    `reward_correct`, 0.05 mL, once per press, on the frame's fluid total and feed."""
    service = _service(tmp_path)
    _step(service, _open())

    between = _step(service, ManualReward(by=BY))
    _step(service, _end(returned=None))
    awaiting = _step(service, ManualReward(by=BY))

    assert between.fluid_session_ml == pytest.approx(0.05)
    assert between.controls[-1].said == "0.05 mL of reward_correct, given between runs"
    assert awaiting.phase == "awaiting_return"
    assert awaiting.fluid_session_ml == pytest.approx(0.10)
    assert awaiting.controls[-1].said == (
        "0.05 mL of reward_correct, given while the animal's return is awaited"
    )
    assert service.session.card.codes.count(4134) == 2
    assert [r for r in awaiting.refusals if r.name == "reward"] == []


def test_with_no_session_open_a_hand_reward_is_refused_and_says_what_it_waits_for(tmp_path):
    """XC-158 is the button with no session open, a line flush counted to no animal;
    until it is built, a press is refused with its own sentence."""
    service = _service(tmp_path)

    frame = _step(service, ManualReward(by=BY))

    assert frame.refusals == (
        Refused(
            "reward",
            BY,
            "no session is open, so no reward was given: a reward with no session open, "
            "which flushes the line, waits on XC-158",
        ),
    )


def test_during_a_run_a_hand_reward_is_still_given_only_while_paused(tmp_path):
    """XC-157 is the reward during a trial, given the moment it is pressed; until it is
    built, a press while trials run is refused as b2a refused it, and nothing is given.
    This passes before the change too: it pins that the change did not widen it."""
    link = _Script({2: [ManualReward(by=BY)]})
    service = _service(tmp_path, link=link)

    frame = _step(service, _open(), _start())

    (refusal,) = [r for r in frame.refusals if r.name == "reward"]
    assert "the session is not paused" in refusal.why and "no reward was given" in refusal.why
    assert 4134 not in service.session.card.codes


def test_a_reward_drained_after_the_end_that_records_the_return_gives_nothing(tmp_path):
    """The animal is home once `EndSession` records its return, and the session is closed
    in that pass: a reward drained after it in the same pass finds no session open, and
    is refused with XC-158's sentence -- no fluid, no `MANUAL_REWARD`."""
    service = _service(tmp_path)
    _step(service, _open())
    session = service.session

    frame = _step(service, _end(), ManualReward(by=BY))

    assert isinstance(frame, Idle) and service.session is None
    assert [r for r in frame.refusals if r.name == "reward"] == [
        Refused(
            "reward",
            BY,
            "no session is open, so no reward was given: a reward with no session open, "
            "which flushes the line, waits on XC-158",
        )
    ]
    assert (session.welfare.commanded, session.welfare.deliveries) == (0.0, 0)
    assert 4134 not in session.card.codes
