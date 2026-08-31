"""The session record.

Written into `<root>/<YYYY-MM-DD_NN>/expcontroller/`, the directory `wl-preproc`'s
frozen path contract already reserves for us -- deliberately outside `SYSTEMS`, so
we write no DONE marker and never block session-complete detection.
"""

from __future__ import annotations

import json

import pytest

from wl_expcontroller.record import SessionRecord


def test_the_record_lands_where_wl_preproc_expects_it(tmp_path):
    with SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A"):
        pass

    directory = tmp_path / "2027-01-14_01" / "expcontroller"
    assert directory.is_dir()
    assert not (directory / "DONE").exists(), (
        "we are not a SYSTEMS member; a DONE marker here would make ingest wait "
        "for a system that has no timebase extractor"
    )


def test_a_trial_is_on_disk_before_the_session_ends(tmp_path):
    """Streamed, not accumulated (S8 §5.2). A crash loses the tail, not the day --
    the lesson wl-sync learned when its own recorder held a whole session in memory
    and a crash took all of it."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=1, outcome="correct", params={"fix_hold": 0.3})

    written = (
        tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
    ).read_text()

    assert json.loads(written.strip())["outcome"] == "correct"


def test_every_trial_carries_its_whole_resolved_parameter_set(tmp_path):
    """P16. A pointer to "the config" is not enough: a change mid-session is
    invisible at analysis time unless each trial says what it actually ran with."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=1, outcome="correct", params={"fix_hold": 0.3})
    record.trial(index=2, outcome="correct", params={"fix_hold": 0.9})

    rows = [
        json.loads(line)
        for line in (
            tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
        ).read_text().splitlines()
    ]

    assert [row["params"]["fix_hold"] for row in rows] == [0.3, 0.9]


def test_the_subject_is_on_every_trial_not_only_in_a_header(tmp_path):
    """Two animals routinely work in one day (S3 §2), and the session directory is
    keyed on the sync box's day-scoped id. Naming the subject per trial is what
    makes a day partition correctly whatever wl-sync decides about `_02`."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=1, outcome="correct", params={})

    row = json.loads(
        (tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl").read_text()
    )

    assert row["subject"] == "A"


def test_the_config_snapshot_records_the_whole_precedence_chain(tmp_path):
    """S8 §3.4. Recording only the resolved values loses where each came from, and
    "why was fix_hold 0.3 that day" is a question asked months later when the layers
    are the only thing that answers it."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.snapshot(
        layers={
            "rig": {"fix_hold": 0.2},
            "subject": {"fix_hold": 0.3},
            "session": {},
        },
        resolved={"fix_hold": 0.3},
        versions={"task": "detection@3", "code": "abc1234"},
    )

    written = json.loads(
        (tmp_path / "2027-01-14_01" / "expcontroller" / "config.json").read_text()
    )

    assert written["resolved"]["fix_hold"] == 0.3
    assert written["layers"]["rig"]["fix_hold"] == 0.2
    assert written["versions"]["code"] == "abc1234"


def test_a_parameter_change_is_recorded_against_the_sequence_number_it_strobed(tmp_path):
    """The PARAM_CHANGE escape carries a sequence number and nothing else -- the
    values live here (S2 §5.2). If the two disagree the change cannot be placed on
    the recording clock at all, so the join is the whole point."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.parameter_change(sequence=7, name="fix_hold", was=0.3, now=0.5, by="console")

    row = json.loads(
        (tmp_path / "2027-01-14_01" / "expcontroller" / "parameter_changes.jsonl")
        .read_text()
    )

    assert (row["sequence"], row["name"], row["was"], row["now"]) == (7, "fix_hold", 0.3, 0.5)
    assert row["by"] == "console"


def test_a_crash_leaves_every_trial_written_so_far(tmp_path):
    """The property the streaming exists for, tested by not closing anything: the
    file is on disk mid-session, not at the end of one."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    for index in range(5):
        record.trial(index=index, outcome="correct", params={})
    del record  # no close(), no __exit__ -- the process died

    lines = (
        tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
    ).read_text().splitlines()

    assert len(lines) == 5


def test_a_simulated_session_writes_a_real_session_directory(tmp_path):
    """P2's exit condition. The simulator and the rig write the same record through
    the same code, which is what makes a simulated session evidence about a real one
    rather than a rehearsal of it."""
    from wl_expcontroller.simulate import Subject, run_session
    from wl_expcontroller.task import (
        After,
        Entered,
        On,
        Outcome,
        Param,
        State,
        Trial,
        Window,
    )

    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        params=[Param("timeout", unit="s", low=0.1, high=5.0)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("fix"), Outcome.CORRECT),
                    On(After(P_TIMEOUT := __import__(
                        "wl_expcontroller.task", fromlist=["P"]
                    ).P("timeout")), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )

    census = run_session(
        trial,
        Subject(seed=5, hazards={Entered: 0.1}),
        trials=50,
        frame_period=0.01,
        values={"timeout": 1.0},
        record=SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A"),
    )

    rows = (
        tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
    ).read_text().splitlines()

    assert len(rows) == 50
    assert sum(census.outcomes.values()) == 50
    assert json.loads(rows[0])["params"] == {"timeout": 1.0}


def test_closing_releases_the_file_and_the_context_manager_does_it_for_you(tmp_path):
    """`close()` is nearly redundant, because every write is flushed -- that is the
    crash-safety property. Nearly is not the same as actually: the handle still has
    to be released, and a session that leaks one per run leaks one per run forever.

    Found by the mutation harness, which reported `close`, `__enter__` and
    `__exit__` surviving -- three methods nothing exercised.
    """
    with SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A") as r:
        r.trial(index=1, outcome="correct", params={})
        assert not r._trials.closed

    assert r._trials.closed
