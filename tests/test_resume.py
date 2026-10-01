import json
import os
from pathlib import Path

import pytest

from wl_xcon.resume import PREDATES, Unresumable, read
from wl_xcon.task import Outcome

DEPARTURE = 1_700_000_000.0
TASK = "tasks/fixation_detection.py"
NAMES = ("trial_number", "trial_in_task", "trial_in_run", "trial_in_block",
         "block_in_session", "block_in_task", "block_in_run",
         "run_in_session", "run_in_task", "task_in_session")


def _pos(*numbers, run, task=TASK):
    return {"run": run, "task": task, **dict(zip(NAMES, numbers))}


def _start(run, bounded, task=TASK):
    return {"event": "start", "run": run, "at": DEPARTURE + 60 * run, "task": task,
            "bounded": bounded}


def _end(run):
    return {"event": "end", "run": run, "at": DEPARTURE + 60 * run + 50, "stop_kind": "completed"}


def _line(number, outcome, fluid_ml, last_reward_at, run):
    return {"index": number - 1, "run": run, "trial_number": number, "outcome": outcome,
            "fluid_ml": fluid_ml, "last_reward_at": last_reward_at}


def _reward(ml, at):
    # The real row (`record.control`) also carries `at_local`, `trial_index` and `run`.
    return {"kind": "reward", "by": "jake", "at": at, "ml": ml, "entry": "reward_correct",
            "trial_index": 0, "run": None}


def _change(sequence, name, was, now, run):
    return {"sequence": sequence, "name": name, "was": was, "now": now, "by": "jake", "run": run}


def _config(**over):
    config = {
        "session_id": "2027-01-14_01", "subject": "REFERENCE", "service": True,
        "deployment": "rig_chaired",
        "bounds": {"ceilings": {"reward_correct": {"value": 0.05, "maximum": 10.0, "unit": "mL"}},
                   "minima": {"daily_fluid": {"value": 20.0, "unit": "mL"}}},
        "versions": {"bounds": "b.py", "rig": "r.py", "subject_settings": ""},
        "setup": {"view": "direct"},
        "already_delivered_today": 40.0,
    }
    config.update(over)
    return config


def _jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _folder(tmp_path, *, runs=(), starts=(), lines=(), controls=(), changes=(), config=None):
    directory = tmp_path / "2027-01-14_01" / "xcon"
    directory.mkdir(parents=True)
    (directory / "config.json").write_text(json.dumps(config or _config()))
    for name, rows in (("runs.jsonl", runs), ("trial_starts.jsonl", starts),
                       ("trials.jsonl", lines), ("controls.jsonl", controls),
                       ("parameter_changes.jsonl", changes)):
        if rows:
            _jsonl(directory / name, rows)
    return directory


def _two_runs(tmp_path, changes=()):
    """Two runs of one task. The second was cut by a crash mid-trial: trial 5 started,
    with no line. A hand reward fell between the runs."""
    return _folder(
        tmp_path,
        runs=[_start(0, {"reward_correct": 0.2}), _end(0), _start(1, {"reward_correct": 0.25})],
        starts=[_pos(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, run=0), _pos(2, 2, 2, 2, 1, 1, 1, 1, 1, 1, run=0),
                _pos(3, 3, 1, 1, 2, 2, 1, 2, 2, 1, run=1), _pos(4, 4, 2, 2, 2, 2, 1, 2, 2, 1, run=1),
                _pos(5, 5, 3, 3, 2, 2, 1, 2, 2, 1, run=1)],
        lines=[_line(1, "correct", 0.2, DEPARTURE + 100, run=0),
               _line(2, "no_fixation", 0.0, None, run=0),
               _line(3, "correct", 0.25, DEPARTURE + 300, run=1),
               _line(4, "correct", 0.25, DEPARTURE + 400, run=1)],
        controls=[_reward(0.25, at=DEPARTURE + 200)],
        changes=changes,
    )


def test_a_session_read_back_gives_its_departure_fluid_and_numbers(tmp_path):
    got = read(_two_runs(tmp_path), DEPARTURE)

    assert got.departure == DEPARTURE
    assert got.already_today == 40.0
    assert got.commanded == pytest.approx(0.2 + 0.25 + 0.25 + 0.25)
    assert got.last_reward_at == DEPARTURE + 400
    assert got.run_index == 1
    levels = got.levels
    assert (levels.trials, levels.blocks, levels.runs) == (5, 2, 2)
    assert levels.order == {"fixation_detection": 1}
    assert levels.task_runs == {"fixation_detection": 2}
    assert levels.task_trials == {"fixation_detection": 5}
    assert levels.task_blocks == {"fixation_detection": 2}
    assert levels.session_tally.outcomes == {Outcome.CORRECT: 3, Outcome.NO_FIXATION: 1}
    assert levels.task_tallies["fixation_detection"].outcomes[Outcome.CORRECT] == 3


def test_a_started_trial_with_no_line_keeps_its_number_and_adds_no_fluid(tmp_path):
    """Review Focus 4: trial 5 started, so the next trial is 6, and its fluid is not counted."""
    levels = read(_two_runs(tmp_path), DEPARTURE).levels
    levels.start_run(TASK)
    position, opened = levels.start_trial()
    assert (position.trial_number, position.block_in_session, position.run_in_session) == (6, 3, 3)
    assert opened


def test_a_hand_reward_between_runs_is_counted_and_can_be_the_last_reward(tmp_path):
    """Review Focus 3."""
    directory = _two_runs(tmp_path)
    _jsonl(directory / "controls.jsonl", [_reward(0.25, at=DEPARTURE + 900)])
    got = read(directory, DEPARTURE)
    assert got.commanded == pytest.approx(0.2 + 0.25 + 0.25 + 0.25)
    assert got.last_reward_at == DEPARTURE + 900


def test_the_reward_size_is_the_last_runs_then_its_own_changes(tmp_path):
    """A change made in run 0 is already in run 1's start row; one made in run 1 is not."""
    earlier = read(_two_runs(tmp_path / "a", changes=[_change(1, "reward_correct", 0.2, 0.25, run=0)]),
                   DEPARTURE)
    assert earlier.bounded == {"reward_correct": 0.25} and earlier.sequence == 1
    later = read(_two_runs(tmp_path / "b", changes=[_change(1, "reward_correct", 0.2, 0.25, run=0),
                                                    _change(2, "reward_correct", 0.25, 0.3, run=1),
                                                    _change(3, "fix_window", 2.0, 3.0, run=1)]),
                 DEPARTURE)
    assert later.bounded == {"reward_correct": 0.3} and later.sequence == 3
    # The last start row is authoritative for what came before it: a run-0 change is not
    # replayed over it (it would be the same value in a consistent record, so only a
    # differing one proves the run filter is there).
    stale = read(_two_runs(tmp_path / "c", changes=[_change(1, "reward_correct", 0.2, 0.9, run=0)]),
                 DEPARTURE)
    assert stale.bounded == {"reward_correct": 0.25}


def test_a_session_opened_with_no_run_reads_back_with_run_one_next(tmp_path):
    """Review Focus 2."""
    got = read(_folder(tmp_path), DEPARTURE)
    assert (got.commanded, got.last_reward_at, got.run_index, got.sequence) == (0.0, None, None, 0)
    assert got.bounded == {}
    got.levels.start_run(TASK)
    assert got.levels.start_trial()[0].run_in_session == 1


def test_a_restored_tally_counts_hangs(tmp_path):
    directory = _two_runs(tmp_path)
    _jsonl(directory / "trials.jsonl", [_line(1, "hang", 0.0, None, run=0)])
    assert read(directory, DEPARTURE).levels.session_tally.hangs == 1


@pytest.mark.parametrize("damage", ["config", "line"])
def test_a_record_from_before_xc026_cannot_be_resumed(tmp_path, damage):
    """Review Focus 5: no `already_delivered_today`, or a line with no `fluid_ml`."""
    config = _config()
    if damage == "config":
        del config["already_delivered_today"]
    line = (
        {"trial_number": 1, "run": 0, "outcome": "correct"}
        if damage == "line"
        else _line(1, "correct", 0.2, DEPARTURE + 1, run=0)
    )
    directory = _folder(tmp_path, config=config, runs=[_start(0, {})],
                        starts=[_pos(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, run=0)], lines=[line])
    with pytest.raises(Unresumable, match="written before"):
        read(directory, DEPARTURE)
    assert "fluid so far cannot be known" in PREDATES


def test_a_record_with_lines_and_no_starts_cannot_be_resumed(tmp_path):
    """Lines with no `trial_starts.jsonl` were written before XC-026."""
    directory = _folder(tmp_path, runs=[_start(0, {})],
                        lines=[_line(1, "correct", 0.2, DEPARTURE + 1, run=0)])
    with pytest.raises(Unresumable, match="written before"):
        read(directory, DEPARTURE)


@pytest.mark.parametrize("name", ["config.json", "trials.jsonl", "trial_starts.jsonl",
                                  "runs.jsonl", "controls.jsonl", "parameter_changes.jsonl"])
def test_an_unreadable_record_cannot_be_resumed(tmp_path, name):
    directory = _two_runs(tmp_path, changes=[_change(1, "reward_correct", 0.2, 0.25, run=0)])
    with (directory / name).open("a") as handle:
        handle.write('{"torn": ')
    with pytest.raises(Unresumable, match=name.replace(".", r"\.")):
        read(directory, DEPARTURE)


def test_a_line_with_no_start_cannot_be_resumed(tmp_path):
    directory = _two_runs(tmp_path)
    with (directory / "trials.jsonl").open("a") as handle:
        handle.write(json.dumps(_line(9, "correct", 0.25, DEPARTURE + 500, run=1)) + "\n")
    with pytest.raises(Unresumable, match="trial 9"):
        read(directory, DEPARTURE)


def test_a_start_row_missing_its_number_cannot_be_resumed(tmp_path):
    directory = _two_runs(tmp_path)
    with (directory / "trial_starts.jsonl").open("a") as handle:
        handle.write(json.dumps({"run": 1, "task": TASK}) + "\n")
    with pytest.raises(Unresumable, match="trial_number"):
        read(directory, DEPARTURE)


def test_the_last_write_is_the_newest_record_file(tmp_path):
    directory = _two_runs(tmp_path)
    for path in directory.iterdir():
        os.utime(path, (DEPARTURE + 5, DEPARTURE + 5))
    os.utime(directory / "trials.jsonl", (DEPARTURE + 777, DEPARTURE + 777))
    assert read(directory, DEPARTURE).last_written_at == DEPARTURE + 777


# --- fail closed (the controller's ruling on Task 4, 2026-10-01) -------------------
#
# A record the service cannot read must never stop `wlx taskd` starting, since
# `stranded.find` reads every stranded folder through `read` as it starts: whatever a
# record makes raise is `Unresumable`, naming it.


def test_an_infinite_number_in_a_record_cannot_be_resumed(tmp_path):
    """`int(Infinity)` raises `OverflowError`, which no narrower handler named."""
    directory = _two_runs(tmp_path)
    with (directory / "trial_starts.jsonl").open("a") as handle:
        handle.write(json.dumps(_pos(float("inf"), 6, 4, 4, 2, 2, 1, 2, 2, 1, run=1)) + "\n")
    assert "Infinity" in (directory / "trial_starts.jsonl").read_text()

    with pytest.raises(Unresumable, match="OverflowError"):
        read(directory, DEPARTURE)


def test_a_record_nested_past_the_parsers_depth_cannot_be_resumed(tmp_path):
    directory = _two_runs(tmp_path)
    (directory / "controls.jsonl").write_text("[" * 100_000 + "]" * 100_000 + "\n")

    with pytest.raises(Unresumable, match="RecursionError"):
        read(directory, DEPARTURE)


@pytest.mark.parametrize(
    "bounds",
    [
        {"ceilings": {"reward_correct": {"value": 0.05, "maximum": 10.0, "unit": "mL"}}},
        [],
        {"ceilings": [], "minima": {}},
        {"ceilings": {}, "minima": "daily_fluid"},
        None,
    ],
    ids=["no minima", "a list", "ceilings a list", "minima a string", "none"],
)
def test_a_config_whose_bounds_are_not_ceilings_and_minima_cannot_be_resumed(tmp_path, bounds):
    """What a resume compares the animal's bounds with (plan ruling 3) must be there to
    compare, so a `config.json` without it is refused, naming the file."""
    directory = _folder(tmp_path, config=_config(bounds=bounds))

    with pytest.raises(Unresumable, match=r"config\.json"):
        read(directory, DEPARTURE)
