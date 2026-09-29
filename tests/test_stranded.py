"""Stranded sessions (P4d-2b spec §6.1): found from their records after a restart, and
their returns taken under `welfare`'s rules."""

from __future__ import annotations

import json

import pytest

from _sessions import WALL, bounds
from wl_xcon import marks, stranded
from wl_xcon.bounds import Exceeded
from wl_xcon.link import Stranded
from wl_xcon.record import welfare_note


def _notes(root, session_id, *rows):
    directory = root / session_id / "xcon"
    directory.mkdir(parents=True)
    for kind, at in rows:
        welfare_note(directory, kind=kind, subject="A", was=at, now=at, reason="",
                     by="jake", how="t", recorded_at=at)
    return directory


def test_a_session_with_a_departure_and_no_return_is_stranded(tmp_path):
    _notes(tmp_path, "2027-01-13_01", ("session opened", WALL - 900), ("departure", WALL - 900))
    _notes(tmp_path, "2027-01-13_02", ("departure", WALL - 800), ("returned", WALL - 100))
    _notes(tmp_path, "2027-01-13_03", ("departure", WALL - 700), ("return not recorded", WALL - 600))
    (tmp_path / "2027-01-13_04").mkdir()

    assert stranded.find(tmp_path) == [
        Stranded("2027-01-13_01", "A", WALL - 900),
        Stranded("2027-01-13_03", "A", WALL - 700),
    ]


def test_a_record_with_a_torn_line_is_stranded_and_unreadable(tmp_path):
    directory = _notes(tmp_path, "2027-01-13_01", ("departure", WALL - 900), ("returned", WALL - 60))
    with (directory / "welfare_notes.jsonl").open("a") as handle:
        handle.write('{"kind": "depart')

    assert stranded.find(tmp_path) == [Stranded("2027-01-13_01", "", None)]


def test_no_root_finds_nothing(tmp_path):
    assert stranded.find(tmp_path / "missing") == []


def test_a_restored_session_takes_its_return_under_the_rules_and_writes_its_rows(tmp_path):
    directory = _notes(tmp_path, "2027-01-13_01", ("departure", WALL - 3 * 3600))
    found = stranded.find(tmp_path)[0]
    restored = stranded.restore(found, bounds(), directory, lambda: WALL)

    with pytest.raises(marks.Owed):
        marks.take_return(restored, WALL - 2 * 3600, confirmed=False, by="jake", how="the page")
    with pytest.raises(Exceeded, match="having left it at"):
        marks.take_return(restored, WALL - 4 * 3600, confirmed=True, by="jake", how="the page")
    marks.take_return(restored, WALL - 2 * 3600, confirmed=True, by="jake", how="the page")

    rows = [json.loads(l) for l in (directory / "welfare_notes.jsonl").read_text().splitlines()]
    assert [row["kind"] for row in rows] == ["departure", "returned", "return confirmed"]
    assert rows[1]["reason"] == stranded.RESTORED
    assert stranded.find(tmp_path) == []


def test_an_unreadable_or_another_animals_stranded_session_is_refused(tmp_path):
    with pytest.raises(Exceeded, match="cannot be read"):
        stranded.restore(Stranded("x", "", None), bounds(), tmp_path, lambda: WALL)
    with pytest.raises(Exceeded, match="'B'"):
        stranded.restore(Stranded("x", "A", WALL), bounds(subject="B"), tmp_path, lambda: WALL)
