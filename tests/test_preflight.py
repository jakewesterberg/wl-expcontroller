"""Pre-flight (P4d-2b spec §6.2) under S9a §10's one rule (PI, 2026-09-19): fail blocks,
unknown proceeds only on a named acknowledgement written into the record, pass proceeds."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest

from _rig import DIRECT, RIG, STEREOSCOPE
import _sessions
from _sessions import WALL, session
from wl_xcon import preflight
from wl_xcon.cli import _load_allocation, _load_trial
from wl_xcon.link import Preflight, PreflightItem
from wl_xcon.welfare import Absent, Deployment, Simulated

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


def test_a_task_whose_checks_raise_on_it_fails_rather_than_raising(tmp_path):
    """Fix round 1 of Task 8: a task file is code, and `check()` is run on it -- and can
    raise on a shape it does not expect (XC-156). Its fault is this item's, as a failed
    load is, and never the caller's: the service reached this on every check and start,
    and nothing above it contained the exception."""
    item, trial = preflight.task(_sessions.whole_point_task(tmp_path), ALLOCATION, DIRECT)

    assert (item.name, item.result) == ("task checks", "fail")
    assert item.said.startswith("whole_point.py's load-time checks did not finish: TypeError: ")
    assert trial is not None, "it loaded; its checks did not finish"


@pytest.mark.parametrize(
    ("given", "result", "said"),
    [
        ({"fix_hold": 0.3}, "pass", "each declared and in range"),
        ({"fix_hold": 99.0}, "fail", "outside"),
        ({"no_such": 1.0}, "fail", "not a parameter this task declares"),
        ({"fix_hold": "long"}, "fail", "takes a number"),
        ({"fix_hold": float("nan")}, "fail", "not a real number"),
        ({"fix_hold": float("inf")}, "fail", "not a real number"),
        ({"fix_hold": float("-inf")}, "fail", "not a real number"),
    ],
)
def test_starting_values_are_checked_against_the_tasks_declarations(given, result, said):
    item = preflight.values(_load_trial(TASK), given)

    assert (item.name, item.result) == ("starting values", result) and said in item.said


def test_a_bare_exit_from_a_task_or_bounds_file_still_says_something(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nsys.exit()\n")

    item, _ = preflight.task(bad, ALLOCATION, DIRECT)
    kept = preflight.files(bad, "A", None, RIG)[0]

    assert item.result == kept.result == "fail"
    assert item.said.strip() and kept.said.strip() and "bad.py" in item.said


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

    item = preflight.out_of_cage(unmarked)
    assert item.result == "fail" and "not recorded as out of its cage" in item.said
    item = preflight.out_of_cage(past)
    assert item.result == "fail" and "ceiling" in item.said and "End session" in item.said


def test_the_out_of_cage_item_fails_for_a_head_fixed_session_never_fixed(tmp_path):
    made = session(tmp_path, deployment=Deployment.RIG_FIXED)
    made.left_cage(at=WALL - 60)

    item = preflight.out_of_cage(made)

    assert item.result == "fail" and "not recorded as head-fixed" in item.said


def test_the_out_of_cage_item_fails_once_the_animal_is_recorded_home(tmp_path):
    made = session(tmp_path)
    made.left_cage(at=WALL - 300)
    made.returned_to_cage(at=WALL - 100)

    item = preflight.out_of_cage(made)

    assert item.result == "fail" and "already recorded as back" in item.said


def test_a_cage_side_session_passes_and_does_not_claim_a_departure(tmp_path, monkeypatch):
    real = _sessions.bounds

    def no_ceiling(**kwargs):
        made = real(**kwargs)
        kept = {k: v for k, v in made.ceilings.items() if k != "out_of_cage"}
        return dataclasses.replace(made, ceilings=kept)

    monkeypatch.setattr(_sessions, "bounds", no_ceiling)
    made = session(tmp_path, deployment=Deployment.CAGE_SIDE)

    item = preflight.out_of_cage(made)

    assert item.result == "pass" and "no out-of-cage interval" in item.said
    assert "marked" not in item.said


def test_inside_the_warning_band_the_item_passes_with_the_warning_as_its_sentence(tmp_path):
    made = session(tmp_path, out_of_cage=600.0)
    made.left_cage(at=WALL - 300)

    item = preflight.out_of_cage(made)

    assert item.result == "pass" and item.said == made.welfare.approaching_limit(WALL)
    assert "300 s left" in item.said


def test_exactly_at_the_limit_the_item_says_so_and_passes_as_must_stop_does_not_fire(tmp_path):
    made = session(tmp_path, out_of_cage=600.0)
    made.left_cage(at=WALL - 300)
    made.wall_clock = lambda: WALL + 300
    assert made.welfare.must_stop(WALL + 300) is None

    item = preflight.out_of_cage(made)

    assert item.result == "pass" and "at its 600 s out-of-cage limit" in item.said
    assert "not reached" not in item.said


def test_what_nothing_measures_is_unknown_and_says_what_it_waits_for():
    """S9a §10: an absent pump calibration is acknowledgeable only while no real pump
    driver exists -- a dated claim, named so it can be found (V10)."""
    for pump in (Simulated(), Absent()):
        items = preflight.unmeasured(pump)

        assert [(i.name, i.result) for i in items] == [
            ("pump calibration", "unknown"), ("eye tracker", "unknown"),
        ]
        assert "V10" in items[0].said and "driver" in items[0].said
        assert "V3" in items[1].said


def test_a_real_pump_makes_the_calibration_a_fail_not_an_acknowledgeable_unknown():
    class ValvePump:
        def deliver(self, ml):
            pass

    items = preflight.unmeasured(ValvePump())

    assert (items[0].name, items[0].result) == ("pump calibration", "fail")
    assert "V10" in items[0].said and "driver" in items[0].said
    assert items[1].result == "unknown"


def _checked(*results: str, mark: bool = True) -> Preflight:
    items = [PreflightItem(f"item {i}", r, f"said {i}") for i, r in enumerate(results)]
    if mark:
        items.append(PreflightItem("out of cage", "pass", "marked"))
    return Preflight("t.py", tuple(items))


def test_the_gate_lets_every_pass_through():
    assert preflight.gate(_checked("pass", "pass"), ()) is None


def test_the_gate_blocks_any_fail_even_when_every_unknown_is_acknowledged():
    why = preflight.gate(_checked("pass", "fail", "unknown"), ("item 2",))

    assert why.startswith("pre-flight failed") and "item 1: said 1" in why


def test_naming_a_failed_item_never_unblocks_it():
    why = preflight.gate(_checked("fail", "unknown"), ("item 0", "item 1"))

    assert why.startswith("pre-flight failed") and "item 0: said 0" in why


def test_the_gate_lets_an_unknown_through_only_when_it_is_acknowledged_by_name():
    assert "item 1" in preflight.gate(_checked("unknown", "unknown"), ("item 0",))
    assert preflight.gate(_checked("unknown", "unknown"), ("item 0", "item 1")) is None


def test_a_bare_string_is_not_an_acknowledgement_it_is_a_substring_trap():
    said = "I did not check item 0 or item 1"

    why = preflight.gate(_checked("unknown", "unknown"), said)

    assert why is not None and "names" in why


def test_the_gate_fails_closed_on_a_result_it_does_not_know():
    assert preflight.gate(_checked("pass", "maybe"), ()).startswith("pre-flight failed")


def test_a_preflight_without_the_out_of_cage_item_does_not_open_the_gate():
    for empty in (Preflight("t.py", ()), _checked("pass", mark=False)):
        why = preflight.gate(empty, ())

        assert why.startswith("pre-flight failed") and "out of cage" in why


def test_the_record_says_who_acknowledged_each_unknown_and_no_one_else():
    rows = preflight.rows(
        _checked("pass", "unknown", "unknown"), "jake (box, unverified)", ("item 2",)
    )

    assert [(r["name"], r["result"], r["acknowledged_by"]) for r in rows] == [
        ("item 0", "pass", None),
        ("item 1", "unknown", None),
        ("item 2", "unknown", "jake (box, unverified)"),
        ("out of cage", "pass", None),
    ]


@pytest.mark.parametrize("by", ["", "   ", None])
def test_the_record_refuses_an_acknowledgement_nobody_signed(by):
    with pytest.raises(ValueError, match="who acknowledged"):
        preflight.rows(_checked("unknown"), by, ("item 0",))


def test_a_blank_name_is_fine_when_nothing_was_acknowledged():
    rows = preflight.rows(_checked("pass", "unknown"), "", ())

    assert all(r["acknowledged_by"] is None for r in rows)
