"""The session record.

Written into `<root>/<YYYY-MM-DD_NN>/xcon/`, the directory `wl-preproc`'s
frozen path contract already reserves for us -- deliberately outside `SYSTEMS`, so
we write no DONE marker and never block session-complete detection.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path

import pytest

from wl_xcon.levels import Position
from wl_xcon.record import RUNS, REFUSAL_LOG_LIMIT, TRIAL_STARTS, SessionRecord, welfare_note


def test_the_record_lands_where_wl_preproc_expects_it(tmp_path):
    with SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A"):
        pass

    directory = tmp_path / "2027-01-14_01" / "xcon"
    assert directory.is_dir()
    assert not (directory / "DONE").exists(), (
        "we are not a SYSTEMS member; a DONE marker here would make ingest wait "
        "for a system that has no timebase extractor"
    )


#: A missing checkout skips locally and fails under `WLX_REQUIRE_PREPROC=1`, which CI
#: sets -- the same guard as `test_gaze.py` and `test_calibration.py`.
_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"


def _their_folder_name() -> str | None:
    """`wl_preproc.contracts.paths.XCON_DIRNAME`, read by the parser.

    **Not imported**: that module imports `wl_sync` for `SessionId`, and CI checks out
    wl-preproc but not wl-sync. The constant is a string literal, so the assignment in
    their source is the same fact without running their module. Anything other than a
    plain literal assignment raises: the constant moving is exactly what this test is
    here to notice, and it must not pass because it could not find it.
    """
    spec = importlib.util.find_spec("wl_preproc")
    if spec is None or not spec.submodule_search_locations:
        return None
    source = Path(next(iter(spec.submodule_search_locations))) / "contracts" / "paths.py"
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id == "XCON_DIRNAME":
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            raise AssertionError(f"{source}: XCON_DIRNAME is no longer a string literal")
    raise AssertionError(f"{source} no longer defines XCON_DIRNAME")


def test_the_record_lands_in_the_folder_wl_preproc_reads(tmp_path):
    """Their reader finds our files by this folder name alone (`schema/eye.py::
    _find_xcon_log` globs `<session>/xcon/*.yaml`), so a drift here is not an error
    anywhere: the pipeline would simply find no calibration file. It was
    renamed once already, on 2026-09-28."""
    theirs = _their_folder_name()
    if theirs is None:
        if _REQUIRED:
            raise AssertionError(
                "WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable; the folder "
                "our record lands in is only right if it is the one they read"
            )
        pytest.skip("wl-preproc checkout not beside this repo; the contract cannot run")

    with SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A") as record:
        assert record.directory == tmp_path / "2027-01-14_01" / theirs


def test_a_trial_is_on_disk_before_the_session_ends(tmp_path):
    """Streamed, not accumulated (S8 §5.2). A crash loses the tail, not the day --
    the lesson wl-sync learned when its own recorder held a whole session in memory
    and a crash took all of it."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(
        index=1, outcome="correct", params={"fix_hold": 0.3}, run=0, position=Position.lone(1),
        fluid_ml=0.0,
        last_reward_at=None,
    )

    written = (
        tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl"
    ).read_text()

    assert json.loads(written.strip())["outcome"] == "correct"


def test_every_trial_carries_its_whole_resolved_parameter_set(tmp_path):
    """P16. A pointer to "the config" is not enough: a change mid-session is
    invisible at analysis time unless each trial says what it actually ran with."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(
        index=1, outcome="correct", params={"fix_hold": 0.3}, run=0, position=Position.lone(1),
        fluid_ml=0.0,
        last_reward_at=None,
    )
    record.trial(
        index=2, outcome="correct", params={"fix_hold": 0.9}, run=0, position=Position.lone(2),
        fluid_ml=0.0,
        last_reward_at=None,
    )

    rows = [
        json.loads(line)
        for line in (
            tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl"
        ).read_text().splitlines()
    ]

    assert [row["params"]["fix_hold"] for row in rows] == [0.3, 0.9]


def test_the_subject_is_on_every_trial_not_only_in_a_header(tmp_path):
    """Two animals routinely work in one day (S3 §2), and the session directory is
    keyed on the sync box's day-scoped id. Naming the subject per trial is what
    makes a day partition correctly whatever wl-sync decides about `_02`."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=1, outcome="correct", params={}, run=0, position=Position.lone(1), fluid_ml=0.0, last_reward_at=None)

    row = json.loads(
        (tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text()
    )

    assert row["subject"] == "A"


def test_the_config_is_written_as_given(tmp_path):
    """P4d-2b spec §6.3: `config.json` holds what is fixed for the whole session; what
    varies by run is in `runs.jsonl`. The record writes what it is given."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.configure({"subject": "A", "setup": {"view": "direct"}})

    written = json.loads((tmp_path / "2027-01-14_01" / "xcon" / "config.json").read_text())

    assert written == {"subject": "A", "setup": {"view": "direct"}}


def test_a_session_record_opens_no_file_until_something_is_written(tmp_path):
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")

    assert record.directory.is_dir()
    assert list(record.directory.iterdir()) == []


def test_the_trial_file_is_reopened_for_each_run_and_every_row_names_its_run(tmp_path):
    """Spec §6.3: "Every trial row names its run." The record lives for the session and
    its trial file for a run: closed with one, reopened by the next one's first trial.
    **And every row carries its trial number beside its run and its index** (XC-155),
    written as given: `taskd` counts it across the session, and wl-preproc joins on it."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=0, outcome="correct", params={}, run=0, position=Position.lone(0), fluid_ml=0.0, last_reward_at=None)
    record.close()
    record.trial(
        index=0,
        outcome="no_response",
        params={},
        run=1,
        position=Position(2, 2, 1, 1, 2, 2, 1, 2, 2, 1),
        fluid_ml=0.0,
        last_reward_at=None,
    )
    record.close()
    record.close()  # a second close does nothing

    rows = [
        json.loads(line)
        for line in (record.directory / "trials.jsonl").read_text().splitlines()
    ]
    assert [(row["run"], row["index"], row["trial_number"], row["outcome"]) for row in rows] == [
        (0, 0, 1, "correct"),
        (1, 0, 2, "no_response"),
    ]


def test_a_trial_row_is_never_written_without_its_position(tmp_path):
    """XC-155: wl-preproc joins a `trials.jsonl` line to the recording's trial by its
    `trial_number` alone, so a line written without one would join nothing, and nothing
    would say so. Since the session levels (spec §3) that number comes in the trial's
    `position`, with the nine beside it. Required, as `run` is, and never defaulted."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")

    with pytest.raises(TypeError, match="position"):
        record.trial(index=0, outcome="correct", params={}, run=0, fluid_ml=0.0, last_reward_at=None)

    assert not (record.directory / "trials.jsonl").exists()


def test_a_trial_row_carries_its_ten_position_numbers(tmp_path):
    """Session-levels spec §3: every line carries all ten, each counting from 1, written
    as given -- `taskd` counts them. The spec's worked example: a trial late in the
    second fixation run of a session of calibration, fixation, detection and fixation.
    `index` and `run` stay beside them, 0-based, as they were."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    position = Position(512, 400, 58, 18, 27, 21, 3, 4, 2, 2)
    record.trial(index=57, outcome="correct", params={}, run=3, position=position, fluid_ml=0.0, last_reward_at=None)

    row = json.loads((record.directory / "trials.jsonl").read_text().splitlines()[-1])
    assert {k: row[k] for k in position.as_record()} == position.as_record()
    assert (row["index"], row["run"]) == (57, 3), "the 0-based fields stay as they were"


def test_a_run_row_carries_its_event_its_run_and_its_local_time(tmp_path):
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.run_row("start", 0, 1_700_000_000.0, task="t.py", by="jake")
    record.run_row("end", 0, 1_700_000_060.0, stop_kind="completed")

    rows = [json.loads(line) for line in (record.directory / RUNS).read_text().splitlines()]

    assert [(row["event"], row["run"], row["at"]) for row in rows] == [
        ("start", 0, 1_700_000_000.0),
        ("end", 0, 1_700_000_060.0),
    ]
    assert rows[0]["task"] == "t.py" and rows[0]["by"] == "jake"
    assert "local" in rows[0]["at_local"]


def test_the_refusal_cap_is_the_sessions_and_each_run_says_what_it_dropped(tmp_path):
    """`REFUSAL_LOG_LIMIT` is how many rows a session writes, across its runs; a run
    that dropped rows says so at its close, and a run that dropped none adds nothing."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    for i in range(REFUSAL_LOG_LIMIT):
        record.refusal("reward_correct", 1.0 + i, "jake", "over", i, float(i))
    record.close()
    for i in range(3):
        record.refusal("reward_correct", 2.0, "jake", "over", i, float(i))
    record.close()
    record.close()

    rows = [
        json.loads(line)
        for line in (record.directory / "refusals.jsonl").read_text().splitlines()
    ]
    notices = [row for row in rows if row.get("truncated")]
    assert len(rows) == REFUSAL_LOG_LIMIT + 1
    assert [(n["kept"], n["dropped"]) for n in notices] == [(REFUSAL_LOG_LIMIT, 3)]


def test_a_parameter_change_is_recorded_against_the_sequence_number_it_strobed(tmp_path):
    """The PARAM_CHANGE escape carries a sequence number and nothing else -- the
    values live here (S2 §5.2). If the two disagree the change cannot be placed on
    the recording clock at all, so the join is the whole point."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.parameter_change(sequence=7, name="fix_hold", was=0.3, now=0.5, by="console")

    row = json.loads(
        (tmp_path / "2027-01-14_01" / "xcon" / "parameter_changes.jsonl")
        .read_text()
    )

    assert (row["sequence"], row["name"], row["was"], row["now"]) == (7, "fix_hold", 0.3, 0.5)
    assert row["by"] == "console"


def test_a_crash_leaves_every_trial_written_so_far(tmp_path):
    """The property the streaming exists for, tested by not closing anything: the
    file is on disk mid-session, not at the end of one."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    for index in range(5):
        record.trial(
            index=index, outcome="correct", params={}, run=0, position=Position.lone(index),
            fluid_ml=0.0,
            last_reward_at=None,
        )
    del record  # no close(), no __exit__ -- the process died

    lines = (
        tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl"
    ).read_text().splitlines()

    assert len(lines) == 5


def test_a_simulated_session_writes_a_real_session_directory(tmp_path):
    """P2's exit condition. The simulator and the rig write the same record through
    the same code, which is what makes a simulated session evidence about a real one
    rather than a rehearsal of it."""
    from wl_xcon.simulate import Subject, run_session
    from wl_xcon.task import (
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
                        "wl_xcon.task", fromlist=["P"]
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
        tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl"
    ).read_text().splitlines()

    assert len(rows) == 50
    assert sum(census.outcomes.values()) == 50
    assert json.loads(rows[0])["params"] == {"timeout": 1.0}
    # The numbers a rig's session of this one run would strobe (XC-155).
    assert [json.loads(row)["trial_number"] for row in rows] == list(range(1, 51))


def test_closing_releases_the_file_and_the_context_manager_does_it_for_you(tmp_path):
    """`close()` is nearly redundant, because every write is flushed -- that is the
    crash-safety property. Nearly is not the same as actually: the handle still has
    to be released, and a session that leaks one per run leaks one per run forever.

    Found by the mutation harness, which reported `close`, `__enter__` and
    `__exit__` surviving -- three methods nothing exercised.
    """
    with SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A") as r:
        r.trial(index=1, outcome="correct", params={}, run=0, position=Position.lone(1), fluid_ml=0.0, last_reward_at=None)
        handle = r._trials
        assert not handle.closed

    assert handle.closed and r._trials is None


def test_the_refusal_log_limit_matches_the_in_memory_refusal_caps():
    """Three in-memory lists and one file are bounded by the same policy, for the
    same reason: the party driving their growth is an untrusted peer, not the
    operator. Two constants rather than one import keeps `record.py` free of a
    dependency on the console link -- the durable record must not learn about
    telemetry -- so this test is what stops them drifting apart in silence.

    They are not the same *rule*: the file keeps the oldest rows and the feed keeps
    the newest (`taskd`'s tests say why). It is the size that has to agree.
    """
    from wl_xcon.link import REFUSAL_HISTORY
    from wl_xcon.record import REFUSAL_LOG_LIMIT

    assert REFUSAL_LOG_LIMIT == REFUSAL_HISTORY


def test_a_welfare_note_is_written_before_the_record_is_open(tmp_path):
    """**The amendment happens before `Session.run` opens anything** (PI, 2026-09-20).

    The departure time has to be settled before `welfare.preflight`, which is what
    lets a session refuse rather than start and stop -- so the row that records an
    operator changing it cannot be a `SessionRecord` method. Writing it at the moment
    it happened is also what makes it survive every later refusal, which is exactly
    when somebody will want to know what the operator was told and what they did.
    """
    directory = tmp_path / "2027-01-14_01" / "xcon"
    assert not directory.exists()

    welfare_note(
        directory,
        kind="departure amended",
        subject="A",
        was=1_700_000_000.0,
        now=1_700_032_400.0,
        reason="typed 08:45 for 18:45",
        by="jake",
        how="amended at the terminal",
        recorded_at=1_700_032_500.0,
    )

    row = json.loads((directory / "welfare_notes.jsonl").read_text().splitlines()[0])
    assert row["reason"] == "typed 08:45 for 18:45"
    assert row["by"] == "jake"
    assert row["was"] == 1_700_000_000.0 and row["now"] == 1_700_032_400.0


def test_a_welfare_note_says_the_time_in_words_a_person_can_read(tmp_path):
    """`1700000000.0` does not answer "why was this session's departure changed".

    Each instant is written twice -- the float for anything re-reading it, and local
    clock time with its zone for the person who is actually asking. The zone is the
    one in force **at that instant**, for the reason `wlx run`'s session-start line
    resolves it that way.
    """
    directory = tmp_path / "s" / "xcon"
    welfare_note(
        directory,
        kind="departure confirmed",
        subject="A",
        was=1_700_000_000.0,
        now=1_700_000_000.0,
        reason="",
        by="",
        how="confirmed at the terminal",
        recorded_at=1_700_000_100.0,
    )

    row = json.loads((directory / "welfare_notes.jsonl").read_text().splitlines()[0])
    for field in ("was_local", "now_local", "recorded_at_local"):
        assert row[field].endswith(" local")
        assert row[field][:4].isdigit(), f"{field} starts with a year: {row[field]!r}"


def test_welfare_notes_are_not_capped_like_refusals(tmp_path):
    """**Deliberately unbounded, unlike `refusal`.** The cap next door exists because
    a console peer can generate refusals as fast as it can send packets. These are
    generated by a person typing at a prompt, at most once per session, and a
    departure amendment that fell off the end of a file would be the one row somebody
    goes looking for."""
    directory = tmp_path / "s" / "xcon"
    for index in range(REFUSAL_LOG_LIMIT + 5):
        welfare_note(
            directory,
            kind="departure amended",
            subject="A",
            was=float(index),
            now=float(index) + 1.0,
            reason="a reason",
            by="jake",
            how="--amend-out-of-cage-to",
            recorded_at=0.0,
        )

    lines = (directory / "welfare_notes.jsonl").read_text().splitlines()
    assert len(lines) == REFUSAL_LOG_LIMIT + 5


def test_a_welfare_note_is_not_written_into_either_file_beside_it(tmp_path):
    """**Its own file, and the two reasons are in `record.WELFARE_NOTES`.** A row in
    `parameter_changes.jsonl` carries a `sequence` that joins it to a strobe on the
    recording clock, and the out-of-cage marks are deliberately not event-coded (PI,
    2026-09-20) -- so such a row would look alignable and be nothing of the kind.
    `refusals.jsonl` is for writes that did not happen, and is capped."""
    directory = tmp_path / "s" / "xcon"
    welfare_note(
        directory,
        kind="departure confirmed",
        subject="A",
        was=1.0,
        now=1.0,
        reason="",
        by="",
        how="--confirm-out-of-cage, with no terminal attached",
        recorded_at=0.0,
    )

    assert not (directory / "parameter_changes.jsonl").exists()
    assert not (directory / "refusals.jsonl").exists()


def test_a_trial_start_is_one_line_of_the_position_a_run_and_a_task(tmp_path):
    """XC-026 spec §8a item 1: the ten position fields plus `run` and `task`, nothing else."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    position = Position.lone(4)
    record.trial_start(position, run=2, task="tasks/x.py")

    text = (tmp_path / "2027-01-14_01" / "xcon" / TRIAL_STARTS).read_text()
    assert text.count("\n") == 1, "flushed, one line"
    assert json.loads(text) == {"run": 2, "task": "tasks/x.py", **position.as_record()}
    assert len(position.as_record()) == 10
    record.close()


def test_a_trial_line_carries_its_fluid_and_its_last_reward(tmp_path):
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(
        index=1, outcome="correct", params={}, run=0, position=Position.lone(1),
        fluid_ml=0.3, last_reward_at=1_700_000_001.5,
    )

    row = json.loads((tmp_path / "2027-01-14_01" / "xcon" / "trials.jsonl").read_text())
    assert (row["fluid_ml"], row["last_reward_at"]) == (0.3, 1_700_000_001.5)
