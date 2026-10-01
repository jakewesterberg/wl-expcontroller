"""`levels.Levels`: where each trial sits in its session (session-levels spec §3)."""

from types import SimpleNamespace

import pytest

from wl_xcon.levels import Levels, Position, task_name
from wl_xcon.task import Outcome

FIX = "tasks/fixation_detection.py"


def _result(outcome=Outcome.CORRECT):
    """What `Tally.add` reads of a trial's result."""
    return SimpleNamespace(visited=(), scored=(), outcome=outcome)


def _run(levels, task, blocks, close_last=True):
    """One run of `task`: `blocks` is each block's trial count. Returns the positions."""
    levels.start_run(task)
    out = []
    for at, count in enumerate(blocks):
        for _ in range(count):
            position, _opened = levels.start_trial()
            out.append(position)
            levels.end_trial(_result())
        if close_last or at < len(blocks) - 1:
            levels.end_block()
    return out


def test_the_spec_worked_example_numbers_every_level():
    """Calibration; fixation with blocks of 2, 2, 2; detection; fixation again, 2 then 1."""
    levels = Levels()
    _run(levels, "tasks/calibration.py", [2])
    _run(levels, FIX, [2, 2, 2])
    _run(levels, "tasks/detection.py", [3])
    last = _run(levels, FIX, [2, 1])[-1]

    assert last == Position(
        trial_number=14,
        trial_in_task=9,
        trial_in_run=3,
        trial_in_block=1,
        block_in_session=7,
        block_in_task=5,
        block_in_run=2,
        run_in_session=4,
        run_in_task=2,
        task_in_session=2,
    )


def test_a_block_opens_with_its_first_trial():
    levels = Levels()
    levels.start_run(FIX)

    assert levels.end_block() is False, "no trial ran, so no block is open"
    first, opened = levels.start_trial()
    second, again = levels.start_trial()

    assert (opened, again) == (True, False)
    assert (first.block_in_session, second.block_in_session) == (1, 1)
    assert (first.trial_in_block, second.trial_in_block) == (1, 2)


def test_a_run_stopped_before_any_trial_uses_no_block_number():
    levels = Levels()
    levels.start_run(FIX)
    levels.start_run(FIX)

    position, opened = levels.start_trial()

    assert opened and position.block_in_session == 1 and position.run_in_session == 2


def test_a_run_ending_mid_block_closes_that_block():
    levels = Levels()
    _run(levels, FIX, [2], close_last=False)
    levels.start_run(FIX)

    position, opened = levels.start_trial()

    assert opened
    assert (position.block_in_session, position.block_in_task, position.block_in_run) == (2, 2, 1)


def test_a_trial_that_faulted_keeps_its_numbers():
    """Taken as it starts: the faulted trial is in the recording, and none reuses them."""
    levels = Levels()
    levels.start_run(FIX)
    levels.start_trial()  # faults: no end_trial
    levels.start_run(FIX)

    position, _ = levels.start_trial()

    assert (position.trial_number, position.trial_in_task, position.trial_in_run) == (2, 2, 1)


def test_one_task_file_by_two_paths_is_one_task():
    levels = Levels()
    _run(levels, FIX, [1])
    position = _run(levels, "/home/rig/wl-xcon/tasks/fixation_detection.py", [1])[0]

    assert (position.run_in_task, position.task_in_session, position.trial_in_task) == (2, 1, 2)


def test_tasks_are_numbered_by_first_appearance():
    levels = Levels()
    _run(levels, "tasks/calibration.py", [1])
    _run(levels, FIX, [1])
    again = _run(levels, "tasks/calibration.py", [1])[0]

    assert levels.order == {"calibration": 1, "fixation_detection": 2}
    assert again.task_in_session == 1


def test_a_new_task_is_numbered_past_the_largest_task_not_by_the_count():
    """XC-026's final review, I3: counts rebuilt from a record can have a gap -- task 2's
    run raised after `start_run` and before its start row, so nothing recorded it -- and
    a new task numbered by the count would repeat task 3. Live there is no gap, and the
    largest plus one is the count plus one (above)."""
    levels = Levels(order={"calibration": 1, "detection": 3})

    levels.start_run(FIX)

    assert levels.order["fixation_detection"] == 4


def test_outcomes_are_counted_at_the_session_its_task_and_its_block():
    levels = Levels()
    levels.start_run(FIX)
    levels.start_trial()
    levels.end_trial(_result(Outcome.CORRECT))
    levels.start_trial()
    levels.end_trial(_result(None))  # a hang
    levels.end_block()
    levels.start_run("tasks/calibration.py")
    levels.start_trial()
    levels.end_trial(_result(Outcome.NO_FIXATION))

    assert levels.session_tally.outcomes == {Outcome.CORRECT: 1, Outcome.NO_FIXATION: 1}
    assert levels.session_tally.hangs == 1
    assert levels.task_tallies["fixation_detection"].outcomes == {Outcome.CORRECT: 1}
    assert levels.task_tallies["calibration"].outcomes == {Outcome.NO_FIXATION: 1}
    assert levels.block_tally.outcomes == {Outcome.NO_FIXATION: 1}


def test_closing_a_block_drops_its_tally():
    levels = Levels()
    levels.start_run(FIX)
    levels.start_trial()
    levels.end_trial(_result())

    assert levels.end_block() is True
    assert levels.block_tally is None and levels.block_trials is None


def test_a_trial_before_any_run_is_refused():
    with pytest.raises(RuntimeError, match="no run has started"):
        Levels().start_trial()


def test_a_census_trial_sits_alone_in_one_run_of_one_block():
    assert Position.lone(4) == Position(5, 5, 5, 5, 1, 1, 1, 1, 1, 1)


def test_the_record_names_all_ten_fields_in_order():
    assert list(Position.lone(0).as_record()) == [
        "trial_number", "trial_in_task", "trial_in_run", "trial_in_block",
        "block_in_session", "block_in_task", "block_in_run",
        "run_in_session", "run_in_task", "task_in_session",
    ]


def test_a_task_is_named_by_its_files_stem():
    assert task_name("/abs/tasks/fixation_detection.py") == "fixation_detection"
