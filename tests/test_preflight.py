"""Pre-flight (P4d-2b spec §6.2) under S9a §10's one rule (PI, 2026-09-19): fail blocks,
unknown proceeds only on a named acknowledgement written into the record, pass proceeds."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from _rig import DIRECT, RIG, STEREOSCOPE
from _sessions import WALL, session
from wl_xcon import preflight
from wl_xcon.cli import _load_allocation, _load_trial
from wl_xcon.link import Preflight, PreflightItem
from wl_xcon.welfare import Deployment

ALLOCATION = _load_allocation(Path("tasks/allocation.py"))
TASK = Path("tasks/fixation_detection.py")


def test_a_task_that_passes_its_checks_in_the_sessions_setup_passes():
    item, trial = preflight.task(TASK, ALLOCATION, DIRECT)

    assert (item.name, item.result) == ("task checks", "pass")
    assert "direct view" in item.said and trial is not None


def test_a_task_written_for_the_other_setup_fails_naming_the_finding():
    item, _ = preflight.task(TASK, ALLOCATION, STEREOSCOPE)

    assert item.result == "fail" and "wrong-setup" in item.said


@pytest.mark.parametrize(
    ("text", "said"),
    [("x = 1\n", "defines 0 trials"), ("raise ValueError('broken on purpose')\n", "did not load")],
)
def test_a_task_file_that_does_not_load_fails_rather_than_raising(tmp_path, text, said):
    bad = tmp_path / "bad.py"
    bad.write_text(text)

    item, trial = preflight.task(bad, ALLOCATION, DIRECT)

    assert item.result == "fail" and said in item.said and trial is None


@pytest.mark.parametrize(
    ("given", "result", "said"),
    [
        ({"fix_hold": 0.3}, "pass", "each declared and in range"),
        ({"fix_hold": 99.0}, "fail", "outside"),
        ({"no_such": 1.0}, "fail", "not a parameter this task declares"),
        ({"fix_hold": "long"}, "fail", "takes a number"),
    ],
)
def test_starting_values_are_checked_against_the_tasks_declarations(given, result, said):
    item = preflight.values(_load_trial(TASK), given)

    assert (item.name, item.result) == ("starting values", result) and said in item.said


def test_the_animals_files_pass_when_they_load_and_name_it(tmp_path):
    folder = tmp_path / "REFERENCE"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    shutil.copy("tasks/reference_subject.py", folder / "settings.py")

    items = preflight.files(folder / "bounds.py", "REFERENCE", folder / "settings.py", RIG)

    assert [(i.name, i.result) for i in items] == [
        ("bounded config", "pass"), ("subject settings", "pass"),
    ]


def test_the_animals_files_fail_when_they_name_another_or_do_not_load(tmp_path):
    folder = tmp_path / "B"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    (folder / "settings.py").write_text("SETTINGS = None\n")

    items = preflight.files(folder / "bounds.py", "B", folder / "settings.py", RIG)

    assert [i.result for i in items] == ["fail", "fail"]
    assert "'REFERENCE'" in items[0].said and "must define SETTINGS" in items[1].said


def test_the_out_of_cage_item_passes_while_the_mark_is_in_and_the_limit_is_not_reached(tmp_path):
    made = session(tmp_path)
    made.left_cage(at=WALL - 60)

    item = preflight.out_of_cage(made)

    assert (item.name, item.result) == ("out of cage", "pass")


def test_the_out_of_cage_item_fails_with_no_departure_or_past_the_limit(tmp_path):
    """Spec §6.1: "reached between runs, it refuses a new run"."""
    unmarked = session(tmp_path / "a")
    past = session(tmp_path / "b", out_of_cage=600.0)
    past.left_cage(at=WALL - 300)
    past.wall_clock = lambda: WALL + 400

    assert preflight.out_of_cage(unmarked).result == "fail"
    item = preflight.out_of_cage(past)
    assert item.result == "fail" and "ceiling" in item.said and "End session" in item.said


def test_what_nothing_measures_is_unknown_and_says_what_it_waits_for():
    """S9a §10: an absent pump calibration is acknowledgeable only while no real pump
    driver exists -- a dated claim, named so it can be found (V10)."""
    items = preflight.unmeasured()

    assert [(i.name, i.result) for i in items] == [
        ("pump calibration", "unknown"), ("eye tracker", "unknown"),
    ]
    assert "V10" in items[0].said and "driver" in items[0].said
    assert "V3" in items[1].said


def _checked(*results: str) -> Preflight:
    return Preflight(
        "t.py", tuple(PreflightItem(f"item {i}", r, f"said {i}") for i, r in enumerate(results))
    )


def test_the_gate_lets_every_pass_through():
    assert preflight.gate(_checked("pass", "pass"), ()) is None


def test_the_gate_blocks_any_fail_even_when_every_unknown_is_acknowledged():
    why = preflight.gate(_checked("pass", "fail", "unknown"), ("item 2",))

    assert why.startswith("pre-flight failed") and "item 1: said 1" in why


def test_the_gate_lets_an_unknown_through_only_when_it_is_acknowledged_by_name():
    assert "item 1" in preflight.gate(_checked("unknown", "unknown"), ("item 0",))
    assert preflight.gate(_checked("unknown", "unknown"), ("item 0", "item 1")) is None


def test_the_gate_fails_closed_on_a_result_it_does_not_know():
    assert preflight.gate(_checked("pass", "maybe"), ()).startswith("pre-flight failed")


def test_the_record_says_who_acknowledged_each_unknown_and_no_one_else():
    rows = preflight.rows(_checked("pass", "unknown"), "jake (box, unverified)")

    assert [(r["name"], r["result"], r["acknowledged_by"]) for r in rows] == [
        ("item 0", "pass", None),
        ("item 1", "unknown", "jake (box, unverified)"),
    ]
