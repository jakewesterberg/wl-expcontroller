"""`wlx`, the guardrail's only invocable form.

The checks existed only inside tests until this existed. A guardrail nobody can run
against a file is a test, not a guardrail -- so its exit codes are the contract, and
these assert them.

**`wlx console` is the reason Task 6 of the p4d1 slice exists.** CLAUDE.md: "a safety
component ships with its consumer, or its absence fails." `ZmqLink`/`ZmqConsole`
(`tests/test_link.py`) proved the transport talks to itself; nothing until this file
proved a person could actually run `wlx run --link` and attach `wlx console` to it.
"""

from __future__ import annotations

import argparse
import gc
import json
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from wl_expcontroller.bounds import Exceeded
from wl_expcontroller.cli import _hours_minutes, _wall_clock_time, main, render
from wl_expcontroller.link import (
    Refused,
    ReturnedToCage,
    SetParameter,
    Staged,
    Stop,
    Telemetry,
    ZmqConsole,
    ZmqLink,
    decode,
    encode,
)

TASKS = "tasks"
GOOD = f"{TASKS}/fixation_detection.py"
ALLOCATION = f"{TASKS}/allocation.py"
BOUNDS = f"{TASKS}/reference_bounds.py"

#: Every `--set` this fixation task needs to run headless, factored out once
#: rather than repeated in every `run`/console-link test that has to launch one.
_TASK_SETS = [
    "--set", "fix_timeout=4.0",
    "--set", "fix_hold=0.3",
    "--set", "response_window=0.6",
    "--set", "target_hold=0.2",
    "--set", "fix_window=2.0",
    "--set", "target_window=3.0",
    "--set", "target_position=10.0",
]


def test_a_clean_task_exits_zero(capsys):
    assert main(["check", GOOD, "--allocation", ALLOCATION]) == 0
    assert "no findings" in capsys.readouterr().out


def test_a_task_with_a_blocking_finding_exits_one(tmp_path, capsys):
    """Exit status is the contract: whatever loads a task on a rig, or in CI, has
    to be able to refuse it without parsing prose."""
    bad = tmp_path / "bad_task.py"
    bad.write_text(
        "from wl_expcontroller.task import After, On, Outcome, State, Trial\n"
        "t = Trial(start='a', states=[\n"
        "    State('a', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('orphan', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "])\n"
    )

    assert main(["check", str(bad)]) == 1
    assert "unreachable-state" in capsys.readouterr().out


def test_an_unallocated_code_is_refused_without_an_allocation(capsys):
    """The default allocation has no task events on purpose. A task emitting any
    code fails until a real allocation is loaded, which is correct for a project
    whose whole guardrail is that codes come from elsewhere."""
    assert main(["check", GOOD]) == 1
    assert "unallocated-code" in capsys.readouterr().out


def test_review_renders_the_artifact(capsys):
    assert main(["review", GOOD, "--allocation", ALLOCATION]) == 0
    out = capsys.readouterr().out
    assert "stateDiagram-v2" in out
    assert "Needs human review" in out


def test_a_file_with_no_trial_says_so(tmp_path):
    empty = tmp_path / "empty.py"
    empty.write_text("x = 1\n")

    with pytest.raises(SystemExit, match="0 trials"):
        main(["check", str(empty)])


def test_an_allocation_file_must_define_ALLOCATION(tmp_path):
    """Looked up by name because an allocation module naturally imports another --
    `PROVISIONAL` -- so two are visible and picking "the only one" would be picking
    arbitrarily."""
    bad = tmp_path / "alloc.py"
    bad.write_text("from wl_expcontroller.codes import PROVISIONAL\n")

    with pytest.raises(SystemExit, match="must define ALLOCATION"):
        main(["check", GOOD, "--allocation", str(bad)])


def test_wlx_run_runs_a_session_and_reports_its_outcomes(tmp_path, capsys):
    """`wlx run` had no test at all until 2026-09-06, which is how a subcommand ends
    up unable to construct the object it exists to construct."""
    exit_code = main(
        [
            "run",
            "tasks/fixation_detection.py",
            "--allocation", "tasks/allocation.py",
            "--bounds", "tasks/reference_bounds.py",
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_01",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--delivered-today", "0",
            "--trials", "20",
            "--set", "fix_timeout=4.0",
            "--set", "fix_hold=0.3",
            "--set", "response_window=0.6",
            "--set", "target_hold=0.2",
            "--set", "fix_window=2.0",
            "--set", "target_window=3.0",
            "--set", "target_position=10.0",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "correct" in out
    assert (tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl").exists()


def test_wlx_run_refuses_a_session_that_does_not_say_how_long_the_animal_was_out(
    tmp_path, capsys
):
    """**The under-count cannot be reached by omission.** `--out-of-cage-at` has no
    default, for the reason `--as WHO` has none: the session clock reads zero at the
    start, so a mark defaulted to the session's own zero makes out-of-cage time equal
    chair time -- which is precisely what the out-of-cage clock replaced chair time
    to remove. `cli.py` passed a literal `0.0` until a review caught it. A headless
    run states a clock time and means it; nothing arrives there by not typing.

    The flag was `--out-of-cage-ago SECONDS` until 2026-09-20, when the PI replaced
    it with a clock time. That it is still required, and still has no default, is the
    half of the old argument that survived unchanged.

    Asserts on the message rather than on the exit code alone: argparse exits 2 for
    every missing required option, so a bare `SystemExit` would pass with this flag
    deleted."""
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--bounds", "tasks/reference_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--trials", "3",
            ]
        )

    assert "--out-of-cage-at" in capsys.readouterr().err


def test_wlx_run_refuses_a_days_prior_total_that_is_not_a_number(tmp_path):
    """**The same command, the same kind of bad value, the same treatment.**

    `--out-of-cage-ago nan` gave a clean `refused:` and `--delivered-today nan`
    (the mark flag was that, and took seconds, until 2026-09-20)
    gave a raw traceback out of `SessionSpec` construction -- two flags of one
    subcommand, one sentence and one stack trace. S9's written-for-a-stranger rule
    is about exactly that. The whole construction is guarded now, so a refusal
    from the day's total, from a config's limit, or from the subject mismatch all
    read the same way."""
    with pytest.raises(SystemExit, match="refused: .*not a real number"):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--allocation", "tasks/allocation.py",
                "--bounds", "tasks/reference_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
                "--delivered-today", "nan",
                "--trials", "3",
            ]
        )


def test_wlx_run_refuses_a_negative_days_prior_total(tmp_path):
    """`--delivered-today=-1000` asked the operator for 1019.75 mL of supplement."""
    with pytest.raises(SystemExit, match="refused: .*cannot be negative"):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--allocation", "tasks/allocation.py",
                "--bounds", "tasks/reference_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
                "--delivered-today", "-1000",
                "--trials", "3",
            ]
        )


def test_wlx_run_without_a_bounded_config_refuses(tmp_path, capsys):
    """A session with no ceilings is a session with no limits, and the CLI is where
    a person would most plausibly leave one off."""
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
            ]
        )


# ---------------------------------------------------------------------------
# `--link`: `wlx run` opening a console link, and leaving it closed behind it
# ---------------------------------------------------------------------------


def test_wlx_run_without_link_still_runs(tmp_path):
    """`--link` is optional, and its absence must not become a transport
    dependency for the terminal path. Omitted, `Session` keeps its default
    `link.Absent()` and this behaves exactly as it did before `--link` existed --
    a regression this task must not introduce while adding the option."""
    exit_code = main(
        [
            "run", GOOD,
            "--allocation", ALLOCATION,
            "--bounds", BOUNDS,
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_03",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--delivered-today", "0",
            "--trials", "5",
            *_TASK_SETS,
        ]
    )

    assert exit_code == 0


def test_wlx_run_refuses_a_malformed_link_value(tmp_path):
    """Fix round 1, minor: `--link`'s parsing used to be `.partition(",")`, which
    on a value with a second comma (`"a,b,c"`) silently took `"b,c"` -- the whole
    remainder -- as the REP endpoint rather than refusing it. Exactly two
    comma-separated endpoints or refusal; nothing in between. Raised before any
    socket is touched, so this needs no real endpoint and no cleanup."""
    with pytest.raises(SystemExit, match="PUB,REP"):
        main(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", BOUNDS,
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_05",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
                "--delivered-today", "0",
                "--trials", "5",
                *_TASK_SETS,
                "--link", "tcp://127.0.0.1:1,tcp://127.0.0.1:2,tcp://127.0.0.1:3",
            ]
        )


def test_wlx_run_refuses_a_link_bound_where_the_lab_network_can_reach_it(tmp_path):
    """S9a §7 lets `taskd` trust a command's actor outright "because they are the
    same machine and the console *is* the authenticator", and nothing enforced the
    premise: `--link tcp://0.0.0.0:5571,...` bound in silence, after which any host
    on the lab network could move `reward_correct` or issue `Stop` under an invented
    `--as`. Refused unless `--link-allow-remote` says it was meant.

    Asserts on the message, not just the exit: an operator who gets this needs to
    know what to pass instead and that the missing piece is authentication, not a
    firewall. Raised before any socket is bound, so this needs no cleanup."""
    argv = [
        "run", GOOD,
        "--allocation", ALLOCATION,
        "--bounds", BOUNDS,
        "--root", str(tmp_path),
        "--session-id", "2027-01-14_06",
        "--subject", "REFERENCE",
        "--out-of-cage-at", _hhmm(),
        "--delivered-today", "0",
        "--trials", "5",
        *_TASK_SETS,
        "--link", "tcp://0.0.0.0:5571,tcp://0.0.0.0:5572",
    ]

    with pytest.raises(SystemExit, match="--link-allow-remote") as refused:
        main(argv)

    assert "P4d-3" in str(refused.value), "the refusal must name what is waited on"
    assert "reward volume" in str(refused.value), "it must say what is at stake"


def test_wlx_run_with_link_lets_a_real_console_attach(tmp_path, zmq_cleanup):
    """The wiring this task exists for (CLAUDE.md: "a safety component ships with
    its consumer, or its absence fails"). `test_link.py` already proves
    `ZmqLink`/`ZmqConsole` talk to each other directly; nothing before this test
    proved that `wlx run --link` -- through `main()`'s own argument parsing --
    actually attaches a real `ZmqLink` to a running `Session`, or that a console's
    write travels all the way to `parameter_changes.jsonl`.

    **`zmq_cleanup` (now in `conftest.py`, moved there in fix round 1) registers
    `probe` and `console` below.** Fix round 1 found this test reintroduced the 300 s
    mutation hang `test_link.py`'s own `zmq_cleanup` exists to prevent -- that
    fixture was module-local, so this file's sockets were not protected by it. See
    `conftest.py`'s copy for the full mechanism. `main()`'s *own* `ZmqLink`, built
    and closed entirely inside the background thread below, has no handle this test
    could register the same way; `gc.collect()` after the thread joins forces its
    cyclic collection to happen under this test's own control -- Task 5's own
    measurements found that path safe ("even from an explicit `gc.collect()` in a
    bare script ... none of these reproduce it outside pytest") -- rather than
    leaving it to whenever pytest's internal collector next happens to run.

    Runs `wlx run` on a background thread (a real `Session.run()`, not a mock) and
    drives a real `ZmqConsole` from the test's own thread -- the same two-sided
    shape as the manual two-terminal drive this task's brief calls for, just
    in-process. Endpoints come from a throwaway `ZmqLink` bound to `tcp://
    127.0.0.1:0` and closed immediately -- an OS-assigned free pair reused for the
    real run, rather than a hard-coded port a concurrent run could collide with.

    **Confirms staged-then-applied via telemetry, and only via telemetry.** A
    first draft of this test sent `SetParameter` and read back a single frame just
    to prove the socket was live, trusting a small `--trials` count to end the
    session soon after. That is not safe: `Session.run()` only applies a staged
    change at the *next* pass's top (`_apply_staged()` runs before that pass's own
    `drain()`, `taskd.py`), and if `drain()` happens to pick up the `SetParameter`
    on the session's *literal last* pass -- indistinguishable from any other pass
    to the console, and not improbable when trials are this fast -- the natural
    "every block is finished" stop fires in that same pass, after staging but
    before any later `_apply_staged()` could apply it, and the record never sees
    it. Measured, not theorised: the first draft failed 5/5 runs in isolation
    (`parameter_changes.jsonl` never created) while passing when run after other
    tests in this file had already warmed the same import path -- two timings of
    the same race, not a flake to retry away.

    Fixed two ways, not one: **(a)** wait for a frame that shows `fix_hold` in
    `.staged` and *then* a later frame where it is gone -- proof `_apply_staged()`
    actually ran a pass after staging it, which is what the record depends on --
    rather than trusting that any frame arriving means the write landed; **(b)** the
    session must still be running when the console acts, so the last pass has
    nowhere near enough room to coincide with this command by chance.

    **(b) was a margin, and the margin moved without anyone touching this test**
    (2026-09-26). It was `tasks/reference_bounds.py`'s chair-time ceiling, measured
    at "roughly 1,500" trials. The 2026-09-19 rulings replaced that ceiling with a
    600 s out-of-cage placeholder, and `_hhmm()` starts each run 0-59 s into it, so
    the session ended after about 300 trials and about 0.3 s of wall time -- figures
    from this machine and a scratchpad probe, **not committed under
    `docs/measurements/`, and not a claim about this system**. Started nine minutes
    into that budget, this test failed 5 of 5 on a receive timeout: the session was
    over before the console heard it.

    So the session's length is no longer anybody's ceiling. `_far_bounds` puts the
    out-of-cage limit twelve hours away, and **the console ends the session itself**
    with a `Stop` once it has seen the change applied -- which also drives a
    console's `Stop` through a real `wlx run`, the one path the `--stop` tests stub.
    `--trials` now only bounds how long a *broken* run takes to finish on its own.

    **The return is sent once an `awaiting_return` frame has arrived**, not on the
    stop frame. `run()` releases a `RIG_FIXED` head -- this command's default -- at
    the wall instant the loop ends, which is after the stop frame is published, and
    `welfare` refuses a return before the release. A return timed off the stop frame
    would race that release; the first `awaiting_return` frame is published after it.
    """
    probe = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    pub_endpoint, rep_endpoint = probe.pub_endpoint, probe.rep_endpoint
    probe.close()
    far_bounds = _far_bounds(tmp_path)

    result: dict[str, int] = {}

    def _run() -> None:
        result["exit_code"] = main(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", far_bounds,
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_04",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
                "--delivered-today", "0",
                "--trials", "5000",
                *_TASK_SETS,
                "--link", f"{pub_endpoint},{rep_endpoint}",
            ]
        )

    runner_thread = threading.Thread(target=_run)
    runner_thread.start()
    try:
        with zmq_cleanup(ZmqConsole(pub_endpoint, rep_endpoint)) as console:
            first = console.receive()
            assert first.session_id == "2027-01-14_04"

            console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))

            seen_staged = False
            applied = False
            for _ in range(2000):
                frame = console.receive()
                if "fix_hold" in {s.name for s in frame.staged}:
                    seen_staged = True
                elif seen_staged:
                    applied = True
                    break
                if frame.stopped_because:
                    break  # the session ended -- stop polling either way
            assert seen_staged, "the console's SetParameter was never drained"
            assert applied, "fix_hold was staged but never observed applied"

            console.send(Stop(by="jake"))
            stopped = None
            for _ in range(2000):
                stopped = console.receive().stopped_because
                if stopped:
                    break
            assert stopped == "stopped by jake", stopped

            # P4d-2a: a rig session now waits, publishing its clock, until the
            # return is marked -- here by the console, which is the only one there
            # is, once the loop has ended and the head is released (see above).
            phase = None
            for _ in range(2000):
                phase = console.receive().phase
                if phase == "awaiting_return":
                    break
            assert phase == "awaiting_return", phase
            console.send(ReturnedToCage(at=time.time(), by="jake", confirmed=False))
            for _ in range(2000):
                phase = console.receive().phase
                if phase == "closed":
                    break
            assert phase == "closed", phase
    finally:
        runner_thread.join(timeout=15)
    assert not runner_thread.is_alive(), "wlx run did not finish on its own"
    # Forces the background thread's own ZmqLink -- built and closed entirely
    # inside main(), so this test has no handle to register with zmq_cleanup --
    # through a cyclic collection this test controls, rather than leaving an
    # abandoned Context (if a future mutation ever neuters close()) for whichever
    # later pytest-internal collection happens to reach it first. See this
    # function's docstring.
    gc.collect()
    assert result["exit_code"] == 0

    changes_path = (
        tmp_path / "2027-01-14_04" / "expcontroller" / "parameter_changes.jsonl"
    )
    changes = [json.loads(line) for line in changes_path.read_text().splitlines()]
    fix_hold_changes = [c for c in changes if c["name"] == "fix_hold"]
    assert fix_hold_changes, "the console's SetParameter never reached the record"
    assert fix_hold_changes[0]["by"] == "jake"
    assert fix_hold_changes[0]["now"] == 0.4


def test_wlx_run_with_link_closes_it_when_the_session_ends(tmp_path, monkeypatch):
    """Fix round 1, minor: nothing pinned that `wlx run --link` actually closes
    the link it opens -- the manual two-terminal drive (this task's report)
    checked it by hand with `ps`/`lsof`, which is exactly the "verified only by
    a reviewer's spy" shape this slice has otherwise been careful to avoid
    (`ZmqLink.close()`'s own docstring names this command as what it was
    waiting for).

    Wraps the real `ZmqLink` with a spy that records whether `close()` ran
    while still calling through to it, so this proves the CLI's own `with`
    wiring calls `close()` -- not that `ZmqLink.close()` itself works, which
    `test_link.py` already covers directly.
    """
    closed = []

    class _SpyLink(ZmqLink):
        def close(self) -> None:
            closed.append(True)
            super().close()

    monkeypatch.setattr("wl_expcontroller.link.ZmqLink", _SpyLink)

    exit_code = main(
        [
            "run", GOOD,
            "--allocation", ALLOCATION,
            "--bounds", BOUNDS,
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_06",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--delivered-today", "0",
            "--trials", "5",
            *_TASK_SETS,
            "--link", "tcp://127.0.0.1:0,tcp://127.0.0.1:0",
            "--await-return-for", "0",
        ]
    )

    assert exit_code == 0
    assert closed == [True], "wlx run --link must close the link it opens"


# ---------------------------------------------------------------------------
# `render`: what a console shows for one `Telemetry` frame
# ---------------------------------------------------------------------------


def _telemetry(**overrides) -> Telemetry:
    """A minimal telemetry frame for renderer tests.

    `fluid_today_ml`/`shortfall_ml` default to `None` -- the unknown-day case --
    so a test that does not override them still exercises the `UNKNOWN` path
    rather than a coincidentally-zero one. Everything else defaults to empty so a
    test that cares about one pane can override just that field without the
    rendered text growing content nobody asked it to check.

    `out_of_cage_seconds` defaults to a *number* rather than to `None`, unlike the
    two above, because its `None` is the rarer case: it means a cage-side session
    with no duration bound at all, and a default of `None` would make every
    renderer test here quietly exercise a kiosk. `chair_seconds` defaults to a
    number for the same reason, and `deployment` to the kind that has one.

    `duration_warning` defaults to `None` -- the quiet case -- so a test that does
    not ask for the warning does not get a line it never checked.
    """
    base = Telemetry(
        schema=1,
        session_id="2027-01-14_01",
        subject="REFERENCE",
        trial_index=3,
        block="session",
        stopped_because="",
        stop_kind=None,
        phase="running",
        fluid_session_ml=1.25,
        fluid_today_ml=None,
        shortfall_ml=None,
        out_of_cage_seconds=96.0,
        chair_seconds=42.0,
        deployment="rig_fixed",
        duration_warning=None,
        outcomes={},
        hangs=0,
        owed={},
        staged=(),
        refusals=(),
        refusals_dropped=0,
    )
    return replace(base, **overrides) if overrides else base


def test_console_renders_a_telemetry_frame_without_inventing_a_number():
    """Every line the console prints names a field of `Telemetry`. An unknown day
    prints UNKNOWN, never 0.0 -- `wlx run` already does this and the two must agree."""
    frame = _telemetry(fluid_today_ml=None, shortfall_ml=None)

    rendered = render(frame)

    assert "supplement: UNKNOWN" in rendered
    assert "0.0" not in rendered.split("supplement:")[1].splitlines()[0]


def test_console_renders_chair_time_as_a_clock_not_a_raw_float():
    """Fix round 1, minor: `chair: 28702.8 s` is not a thing to show a person --
    S9a §4 renders chair time as a clock (`1:47 / 4:00`). `_clock` only formats
    `frame.chair_seconds`; the number itself is still read, not recomputed."""
    frame = _telemetry(chair_seconds=107.0)

    rendered = render(frame)

    assert "chair: 1:47" in rendered
    assert "107.0" not in rendered, "the old raw-seconds float is back"


def test_console_shows_the_clock_that_actually_ends_the_session():
    """PI, 2026-09-19: the session's one duration limit runs out of cage to back in
    cage, and chair time bounds nothing. This screen showed only chair time until
    then, so an operator would have watched a session stop on a clock the console
    had never displayed -- S9's "written for a stranger" failure, with a welfare
    limit on the other end of it. Both are shown, and the one that ends the session
    is first."""
    frame = _telemetry(out_of_cage_seconds=4_007.0, chair_seconds=107.0)

    rendered = render(frame)

    assert "out of cage: 1:06:47" in rendered
    assert "chair: 1:47" in rendered
    assert rendered.index("out of cage:") < rendered.index("chair:")


def test_console_says_a_cage_side_session_has_no_duration_bound():
    """`None` is not zero here either. A cage-side session (S13) has no out-of-cage
    interval at all, and rendering `0:00` would show an operator a clock that has
    not started rather than one that does not exist -- the same confusion
    `fluid today: UNKNOWN` exists to prevent, on the duration path."""
    frame = _telemetry(out_of_cage_seconds=None)

    rendered = render(frame)

    line = [
        text for text in rendered.splitlines() if text.strip().startswith("out of cage")
    ]
    assert line == ["  out of cage: n/a -- cage-side, the animal is home"]
    assert "0:00" not in rendered


def test_console_shows_staged_changes_with_who_staged_them():
    """S9a §8 removed the write lock; staged visibility -- with the actor -- is
    what replaces it. A console that showed only applied values would hide a
    change already accepted and waiting for the next trial boundary from everybody
    who did not stage it themselves."""
    frame = _telemetry(
        staged=(Staged(name="fix_hold", was=0.3, now=0.4, by="jake", bounded=False),)
    )

    rendered = render(frame)

    assert "fix_hold" in rendered
    assert "jake" in rendered
    assert "0.3" in rendered
    assert "0.4" in rendered
    # Fix round 1, minor: a bare "(task)" tag named the internal field
    # (`Staged.bounded`), not what it means to a reader.
    assert "task parameter" in rendered


def test_console_labels_a_staged_welfare_ceiling_change_distinctly():
    """The other half of `Staged.bounded` -- a console must not describe a
    welfare-bounded ceiling change (e.g. `reward_correct`) with the same bare
    label as an ordinary task parameter; the two have very different stakes."""
    frame = _telemetry(
        staged=(
            Staged(name="reward_correct", was=0.05, now=0.08, by="jake", bounded=True),
        )
    )

    rendered = render(frame)

    assert "welfare-bounded ceiling" in rendered
    assert "task parameter" not in rendered


def test_console_says_a_staged_change_of_either_kind_is_still_pending():
    """`staged` means one thing again (PI, 2026-09-19, S9a §8): accepted, validated,
    and **not yet applied**, whichever vocabulary the name belongs to.

    It briefly meant two things. A welfare-bounded value was applied by
    `Session.set` as the command was drained, so the trial running in that same pass
    was already at the new volume, and this screen said `ALREADY IN EFFECT` to keep
    an operator from reading a live change as a queued one. Both now defer to the
    next trial boundary, so a screen still claiming a bounded row is live would be
    the same lie in the other direction -- and the direction that matters, because
    an operator who has just *lowered* a reward volume must not be told it has
    already taken effect when one more trial is still to go out at the old one."""
    bounded = render(
        _telemetry(
            staged=(
                Staged(name="reward_correct", was=0.15, now=0.3, by="jake", bounded=True),
            )
        )
    )
    ordinary = render(
        _telemetry(
            staged=(Staged(name="fix_hold", was=0.3, now=0.4, by="jake", bounded=False),)
        )
    )

    assert "ALREADY IN EFFECT" not in bounded, "the old immediate-apply wording is back"
    assert "applies at the next trial" in bounded
    assert "applies at the next trial" in ordinary
    assert "welfare-bounded ceiling" in bounded, "the two are still told apart"
    assert "welfare-bounded ceiling" not in ordinary


def test_console_prints_a_staged_volume_to_the_same_decimals_as_every_other_fluid():
    """Final-review minor: the staged line printed raw `repr`, so a reward volume
    read `0.15 -> 0.3` two lines under `fluid session: 1.25 mL` -- the same quantity,
    the same screen, two conventions, and the one that looked like a typo was the
    welfare-bounded one. `None` is `was` for a parameter with no prior value and
    prints `unset`, not `0.00`, for the reason `fluid_today_ml` prints `UNKNOWN`."""
    rendered = render(
        _telemetry(
            staged=(
                Staged(name="reward_correct", was=0.15, now=0.3, by="jake", bounded=True),
                Staged(name="fix_hold", was=None, now=0.4, by="jake", bounded=False),
            )
        )
    )

    assert "0.15 -> 0.30" in rendered, "a volume is still at raw repr"
    assert "-> 0.3 " not in rendered, "the bare 0.3 repr is back"
    assert "unset -> 0.40" in rendered, "an absent prior value must not read as a number"


def test_console_does_not_compute_a_trial_total_that_excludes_hangs():
    """Fix round 1, IMPORTANT 2: `render`'s trials line used to open with
    `sum(frame.outcomes.values())` labelled "attempted" -- a computed total that
    silently excluded hangs, so 5 outcomes plus 2 hangs printed "5 attempted" for
    7 actual trials, directly contradicting this function's own "nothing here is
    computed" promise (S9a §9: the console reads numbers, it does not derive
    them). `outcomes`/`hangs` are read as they are now, with no total claimed."""
    frame = _telemetry(outcomes={"correct": 3, "no_fixation": 2}, hangs=2)

    rendered = render(frame)

    assert "5 attempted" not in rendered, "a computed, hang-excluding total is back"
    assert "correct 3" in rendered
    assert "no_fixation 2" in rendered
    assert "hangs 2" in rendered


def test_console_shows_refusals_so_a_mistyped_write_is_not_silent():
    """A refused command that only exists in a log nobody reads is the failure a
    prior fix round removed from `Session.refusals`/`Telemetry.refusals` (fix round
    1, Ruling R17c); the console has to be the thing that actually surfaces it."""
    frame = _telemetry(
        refusals=(Refused(name="fx_hold", by="jake", why="not declared"),)
    )

    rendered = render(frame)

    assert "fx_hold" in rendered
    assert "jake" in rendered
    assert "not declared" in rendered


def test_console_renders_a_refusal_that_actually_crossed_the_wire():
    """CLAUDE.md: **test the path, not the piece.** The test above renders a
    `Refused` built in this process, and `tests/test_link.py`'s round-trip proves
    `decode` rebuilds one -- but until this existed, every link in the chain was
    tested while the chain itself was not, which is the exact shape that let `Mark`
    and `Reward` be dropped by the trial loop with every piece green.

    A real console never sees a `Refused` it constructed. It sees bytes, and the
    first thing it does with them is `refusal.name` (`render`, below the refusals
    line). If `decode` ever hands back the plain dicts msgpack gives it -- which
    nothing caught before final review, because the only round-trip in the suite ran
    on an empty `refusals` tuple -- that attribute access is an `AttributeError` on
    the first refusal an operator causes, and the console dies rather than showing
    them their typo."""
    frame = _telemetry(
        refusals=(
            Refused(
                name="reward_correct",
                by="jake",
                why="'reward_correct' may not exceed 0.4 mL",
            ),
        )
    )

    rendered = render(decode(encode(frame)))

    assert "refused: reward_correct by jake" in rendered
    assert "may not exceed 0.4 mL" in rendered


def test_console_says_when_older_refusals_were_dropped():
    """The refusal feed is capped at `link.REFUSAL_HISTORY`, because the peer that
    decides how fast refusals arrive is not the operator. A cap nobody is told about
    is a silent drop with extra steps -- a screen showing fifty refusals and nothing
    about the four hundred before them reads as "fifty things went wrong", which is
    a different session from the one that happened.

    Printed above the rows, not below: a reader scans down, and learning at the
    bottom that everything above was a tail is learning it too late."""
    rendered = render(
        _telemetry(
            refusals=(Refused(name="fx_hold", by="jake", why="not declared"),),
            refusals_dropped=400,
        )
    )

    first_refusal_line = next(
        line for line in rendered.splitlines() if line.startswith("  refused:")
    )

    assert "400 earlier refusal(s) NOT SHOWN" in first_refusal_line
    assert "fx_hold" in rendered


def test_console_says_nothing_about_dropped_refusals_when_none_were_dropped():
    """The other half: a line that appeared on every ordinary session would be noise,
    and noise is what makes the line above easy to miss on the session that needs
    it."""
    rendered = render(
        _telemetry(
            refusals=(Refused(name="fx_hold", by="jake", why="not declared"),),
            refusals_dropped=0,
        )
    )

    assert "NOT SHOWN" not in rendered


def test_console_renders_the_stop_reason_when_the_session_has_ended():
    frame = _telemetry(stopped_because="stopped by jake")

    rendered = render(frame)

    assert "stopped by jake" in rendered


# ---------------------------------------------------------------------------
# `wlx console`: the actor requirement on a write (S9a §6)
# ---------------------------------------------------------------------------


def test_console_requires_an_actor_for_a_write(capsys):
    """S9a §6: every welfare-affecting action records its actor. A write with no
    `--as` is refused at the CLI rather than defaulting to a name.

    **Asserts the message, not only the exit code -- and that distinction is
    load-bearing, measured by hand-mutating the gate to `if False:`.** With the
    gate bypassed, `main()` still returned 1 here on both tests in this group --
    every one of them, `assert code == 1` alone included -- but only because
    `ZmqConsole.receive()` then ran into its own 5 s timeout against these
    unreachable endpoints (`console: no telemetry received...`) and *that* path
    also returns 1. `code == 1` cannot tell the two apart; the stderr text can,
    and this is the fix from that finding, not a hypothetical.
    """
    code = main(["console", "--sub", "tcp://127.0.0.1:1", "--req",
                 "tcp://127.0.0.1:2", "--set", "fix_hold=0.4"])

    assert code == 1
    err = capsys.readouterr().err
    assert "--as" in err and "actor" in err, (
        f"refused for the wrong reason -- expected the actor gate's own "
        f"message, not a socket timeout against an unreachable endpoint: {err!r}"
    )


def test_console_requires_an_actor_to_stop_too(capsys):
    """The same S9a §6 requirement as `--set`, for the other write this
    subcommand can make -- `Stop` is as welfare-affecting as a parameter change,
    ending a session that may still owe an animal reward. See
    `test_console_requires_an_actor_for_a_write` for why this checks the
    message rather than only the exit code."""
    code = main(["console", "--sub", "tcp://127.0.0.1:1", "--req",
                 "tcp://127.0.0.1:2", "--stop"])

    assert code == 1
    err = capsys.readouterr().err
    assert "--as" in err and "actor" in err, (
        f"refused for the wrong reason -- expected the actor gate's own "
        f"message, not a socket timeout against an unreachable endpoint: {err!r}"
    )


def test_console_with_no_write_needs_no_actor(monkeypatch):
    """Watching a session is not a welfare-affecting action, so a plain `wlx
    console --sub ... --req ...` with no `--set`/`--stop` must not be refused for
    lacking `--as` -- only a write carries that requirement (S9a §6).

    Stubs `link.ZmqConsole` rather than opening a real socket: the property under
    test is that `main()` reaches the point of constructing a console at all --
    proven by `calls`, below -- not any real transport behavior, which
    `test_link.py` already covers.
    """
    calls = []

    class _StubConsole:
        def __init__(self, sub: str, req: str) -> None:
            calls.append((sub, req))

        def __enter__(self) -> "_StubConsole":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def send(self, command: object) -> None:
            raise AssertionError("nothing was staged, so nothing should be sent")

        def receive(self) -> None:
            raise TimeoutError("stub console: nothing to receive")

    monkeypatch.setattr("wl_expcontroller.link.ZmqConsole", _StubConsole)

    code = main(["console", "--sub", "tcp://127.0.0.1:1", "--req", "tcp://127.0.0.1:2"])

    assert calls == [("tcp://127.0.0.1:1", "tcp://127.0.0.1:2")], (
        "the actor gate must not have fired -- it would have returned before "
        "ever constructing a console"
    )
    # Refused here by the stub's TimeoutError (no real session to watch), not by
    # the actor gate -- which is exactly the distinction `calls` above proves.
    assert code == 1


def test_console_refuses_a_non_numeric_set_value(capsys):
    """`SetParameter.value` is a `float` (`link.py`); a console that let a
    non-numeric value through would hand `Session.set` something it never
    promised to carry.

    Checks the message, not only the exit code, for the same reason as
    `test_console_requires_an_actor_for_a_write`: these endpoints are
    unreachable, so a bypassed check here would *also* return 1, later, from
    `ZmqConsole.receive()`'s own timeout -- `code == 1` alone cannot tell a
    refused value from a silently-accepted one that simply never got a reply.
    """
    code = main(["console", "--sub", "tcp://127.0.0.1:1", "--req",
                 "tcp://127.0.0.1:2", "--as", "jake", "--set", "fix_hold=not-a-number"])

    assert code == 1
    err = capsys.readouterr().err
    assert "not-a-number" in err and "NAME=VALUE" in err, (
        f"refused for the wrong reason -- expected the --set parsing message, "
        f"not a socket timeout against an unreachable endpoint: {err!r}"
    )


def test_console_refuses_a_set_with_no_parameter_name(capsys):
    """Final-review minor: `--set` split on `partition("=")` and checked only the
    value, so `--set =0.5` built a `SetParameter(name="", value=0.5)` and **sent**
    it, to be refused by the session over a socket. `--link` had already been
    hardened against exactly this shape of unchecked split and this had not; the
    rule was applied in one place and not the other.

    A console that can see it has nonsense should say so where the person who typed
    it is looking, not spend a round trip to be told by a machine with an animal in
    the chair on it. Checks the message rather than only the exit code, for the same
    reason as the tests above: these endpoints are unreachable, so a bypassed check
    would also return 1, later, from a socket timeout."""
    code = main(["console", "--sub", "tcp://127.0.0.1:1", "--req",
                 "tcp://127.0.0.1:2", "--as", "jake", "--set", "=0.5"])

    assert code == 1
    err = capsys.readouterr().err
    assert "name is required" in err, (
        f"refused for the wrong reason -- expected the empty-name message, not a "
        f"socket timeout against an unreachable endpoint: {err!r}"
    )


def test_console_reports_an_interrupted_watch_as_interrupted(monkeypatch, capsys):
    """Final-review minor: `KeyboardInterrupt` fell through to `return 0`, so a
    watch somebody walked away from and an operator who saw a session stop cleanly
    left an identical trace. 130 is the shell's own SIGINT convention (128 + 2), so
    a wrapper reading only the exit code can tell them apart, and the stderr line
    says the session is still running -- because it is: nothing in this subcommand
    stops a session except `--stop`."""

    class _StubConsole:
        def __init__(self, sub: str, req: str) -> None:
            pass

        def __enter__(self) -> "_StubConsole":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def receive(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("wl_expcontroller.link.ZmqConsole", _StubConsole)

    code = main(["console", "--sub", "tcp://127.0.0.1:1", "--req", "tcp://127.0.0.1:2"])

    assert code == 130, "an abandoned watch is indistinguishable from a clean stop"
    assert "interrupted" in capsys.readouterr().err


def test_wlx_run_refuses_a_set_with_no_parameter_name(tmp_path):
    """The same unchecked split as `wlx console --set`, one subcommand over. Quieter
    and no better: an empty name lands in `spec.values`, is written into the
    session's parameter snapshot, and matches no `Param` any task declares -- a row
    in the record that means nothing. Refused in both places rather than only where
    a reviewer happened to look."""
    with pytest.raises(SystemExit, match="name before the"):
        main(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", BOUNDS,
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_07",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
                "--delivered-today", "0",
                "--trials", "5",
                "--set", "=0.5",
            ]
        )


def test_console_reports_a_second_commands_timeout_cleanly(monkeypatch, capsys):
    """Fix round 1, IMPORTANT 1: `console.send()` sat outside the `try` that
    catches `TimeoutError` (`cli.py`). `ZmqConsole.send()`'s own docstring says a
    second `send()` reads the *previous* command's reply first, and raises
    `TimeoutError` -- exactly like `receive()` -- if a gone or too-slow session
    never answers it. `--set X --stop`, this subcommand's own advertised usage,
    sends two commands, so this was not a hypothetical: every test before this one
    sent at most one command and so never exercised a second `send()` at all.

    Stubs `ZmqConsole` so the *second* `send()` raises `TimeoutError` directly,
    rather than waiting out a real 5 s `RCVTIMEO` against an unreachable endpoint --
    the property under test is `main()`'s own exception handling around `send()`,
    which `test_link.py` has no reason to cover.
    """
    calls = []

    class _StubConsole:
        def __init__(self, sub: str, req: str) -> None:
            pass

        def __enter__(self) -> "_StubConsole":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def send(self, command: object) -> None:
            calls.append(command)
            if len(calls) >= 2:
                raise TimeoutError(
                    "no reply to the previous command within the console's "
                    "receive timeout; refusing to send another command until "
                    "this socket is healthy again"
                )

        def receive(self) -> None:
            raise AssertionError("the receive loop must never be reached here")

    monkeypatch.setattr("wl_expcontroller.link.ZmqConsole", _StubConsole)

    code = main(
        [
            "console", "--sub", "tcp://127.0.0.1:1", "--req", "tcp://127.0.0.1:2",
            "--as", "jake", "--set", "fix_hold=0.4", "--stop",
        ]
    )

    assert len(calls) == 2, "both commands should have been attempted"
    assert code == 1
    err = capsys.readouterr().err
    assert "console:" in err, f"expected the one-line console: ... message, got: {err!r}"
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# The out-of-cage mark as a clock time, and the third deployment kind
# ---------------------------------------------------------------------------


def _hhmm() -> str:
    """This host's local clock, to the minute -- what an operator would type.

    Truncating to the minute puts it between 0 and 60 seconds in the past, which is
    inside every ceiling these tests use and never in the future.
    """
    return time.strftime("%H:%M")


def test_wlx_run_takes_the_departure_as_a_clock_time(tmp_path, capsys):
    """**PI, 2026-09-20: a clock time is what an operator reads.** `--out-of-cage-ago
    SECONDS` is gone rather than aliased -- an operator who types the old flag gets an
    argparse error, not a number interpreted in a base nobody meant."""
    exit_code = main(
        [
            "run",
            "tasks/fixation_detection.py",
            "--allocation", "tasks/allocation.py",
            "--bounds", "tasks/reference_bounds.py",
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_01",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--delivered-today", "0",
            "--trials", "5",
            "--set", "fix_timeout=4.0",
            "--set", "fix_hold=0.3",
            "--set", "response_window=0.6",
            "--set", "target_hold=0.2",
            "--set", "fix_window=2.0",
            "--set", "target_window=3.0",
            "--set", "target_position=10.0",
        ]
    )

    assert exit_code == 0
    assert "--out-of-cage-ago" not in capsys.readouterr().out


def test_wlx_run_prints_how_long_the_animal_has_been_out(tmp_path, capsys):
    """**The visibility the PI asked for in exchange for the guard he gave up.**

    A clock time cannot be refused for being implausible the way a 1.7e9-second
    interval could, and `08:45` typed for `18:45` is nine hours of slack that lands
    inside a twelve-hour ceiling. So the computed interval is printed where an
    operator sees it as the session starts -- a nine-hour error is then legible
    rather than silent."""
    main(
        [
            "run",
            "tasks/fixation_detection.py",
            "--allocation", "tasks/allocation.py",
            "--bounds", "tasks/reference_bounds.py",
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_01",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--delivered-today", "0",
            "--trials", "2",
            "--set", "fix_timeout=4.0",
            "--set", "fix_hold=0.3",
            "--set", "response_window=0.6",
            "--set", "target_hold=0.2",
            "--set", "fix_window=2.0",
            "--set", "target_window=3.0",
            "--set", "target_position=10.0",
        ]
    )

    out = capsys.readouterr().out
    assert "the animal has been out 0 hours 0 minutes" in out
    assert "local time" in out, "the zone the clock time was read in is stated"


def test_the_visible_interval_reads_a_nine_hour_typo_as_nine_hours():
    """**The mitigation Ruling 1 traded a guard for, tested at the size it exists
    for.** `08:45` typed for `18:45` is nine hours, it sits comfortably inside a
    twelve-hour ceiling, and no refusal will ever catch it -- this line is the whole
    of what does. Its only test asserted `0 hours 0 minutes`, which is the one value
    that would also be produced by a function that had stopped working.

    `_hours_minutes` is pure, so testing nine hours needs no session and no invented
    bounded config -- the reason given for not doing this the first time was wrong.
    """
    assert _hours_minutes(9 * 3_600.0) == "9 hours 0 minutes"
    assert _hours_minutes(9 * 3_600.0 + 15 * 60.0) == "9 hours 15 minutes"


def test_the_visible_interval_says_one_hour_rather_than_one_hours():
    """A person reads this sentence once, at the moment it matters most."""
    assert _hours_minutes(3_660.0) == "1 hour 1 minute"


def test_the_visible_interval_never_reads_a_negative_duration():
    """`welfare` refuses a backwards interval before this is ever called, so the
    clamp is a second line rather than the only one -- but a formatter that printed
    `-1 hours -53 minutes` would make a refused state look like a report."""
    assert _hours_minutes(-400.0) == "0 hours 0 minutes"


def test_wlx_run_refuses_a_departure_in_the_future(tmp_path):
    """The first of the two guards that replace the wall-clock catch. A bare time is
    today's date on this host and is never rolled back to yesterday, so `23:59` typed
    in the morning is refused rather than silently becoming a departure twenty-three
    hours ago."""
    tomorrow = datetime.now().astimezone() + timedelta(hours=2)

    with pytest.raises(SystemExit, match="refused: .*in the future"):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--allocation", "tasks/allocation.py",
                "--bounds", "tasks/reference_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", tomorrow.isoformat(timespec="minutes"),
                "--delivered-today", "0",
                "--trials", "2",
            ]
        )


def test_wlx_run_refuses_a_departure_longer_ago_than_the_ceiling(tmp_path):
    """The second. `tasks/reference_bounds.py`'s placeholder ceiling is ten minutes,
    so an hour ago is outside it -- which is the same refusal a real twelve-hour
    config gives a departure typed a day early."""
    an_hour_ago = datetime.now().astimezone() - timedelta(hours=1)

    with pytest.raises(SystemExit, match="refused: .*against a ceiling of"):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--allocation", "tasks/allocation.py",
                "--bounds", "tasks/reference_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", an_hour_ago.isoformat(timespec="minutes"),
                "--delivered-today", "0",
                "--trials", "2",
            ]
        )


def test_wlx_run_refuses_a_departure_that_is_not_a_time(tmp_path, capsys):
    """**The surface an operator actually touches**, which is where the worst defect
    of this whole branch got furthest.

    `--out-of-cage-ago` was `type=float` and argparse happily parsed `nan`. Every
    guard on the mark was an ordered comparison and NaN is `False` against all of
    them, so this exact command line ran a full session with its duration limit
    switched off:

        --out-of-cage-ago 0    -> ended: out_of_cage: 601 s against a ceiling of 600
        --out-of-cage-ago nan  -> ended: every block is finished
                                  400 trials, ~760 session-seconds, 13.55 mL

    A reward-delivering session to completion, unbounded, with a summary that read
    entirely normally. **A clock time closes that at the parser rather than at the
    guard** -- `datetime` accepts no spelling of `nan`, and nothing this flag can
    produce is non-finite -- and the message names what to type instead.
    `welfare._finite` still stands behind it for every other caller, which
    `test_welfare.py` covers. Asserted here rather than only there because the unit
    test would have passed while the old command line still worked: the parser is
    part of the path."""
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--bounds", "tasks/reference_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", "nan",
                "--trials", "2",
            ]
        )

    assert "HH:MM" in capsys.readouterr().err


def test_wlx_run_can_run_a_chaired_session_with_no_head_fixation(tmp_path, capsys):
    """**Head-fixation is a property of the deployment** (PI, 2026-09-20). A chaired
    session runs, is bounded by the same out-of-cage clock, and emits no
    `HEAD_FIXED`/`HEAD_RELEASED` -- because it has none to record."""
    exit_code = main(
        [
            "run",
            "tasks/fixation_detection.py",
            "--allocation", "tasks/allocation.py",
            "--bounds", "tasks/reference_bounds.py",
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_01",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--deployment", "rig-chaired",
            "--delivered-today", "0",
            "--trials", "5",
            "--set", "fix_timeout=4.0",
            "--set", "fix_hold=0.3",
            "--set", "response_window=0.6",
            "--set", "target_hold=0.2",
            "--set", "fix_window=2.0",
            "--set", "target_window=3.0",
            "--set", "target_position=10.0",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    # `wlx run` is headless -- `render` is the console's, and `test_taskd.py` is
    # where the absent 4128/4129 are asserted, because that is where the card is.
    # What this proves is that the session ran at all: before 2026-09-20 preflight
    # refused every rig session with no head-fixation mark.
    assert "ended:" in out
    assert "chair" not in out


def test_the_console_reports_a_chaired_sessions_chair_time_as_unmeasured(tmp_path):
    """**Not applicable must be distinguishable from zero on the console too.**
    A chaired animal is restrained, so `chair: 0:00` would be a claim that nothing
    measured -- the trap this repository has a scar from."""
    frame = _telemetry(chair_seconds=None, deployment="rig_chaired")

    rendered = render(frame)

    line = [t for t in rendered.splitlines() if t.strip().startswith("chair:")]
    assert len(line) == 1
    assert "n/a" in line[0]
    assert "UNMEASURED" in line[0], "the word that separates absent from zero"
    assert "0:00" not in line[0]


def test_the_console_says_a_cage_side_session_has_no_restraint_at_all(tmp_path):
    """The other `None`, and a different fact about an animal: cage-side it was never
    restrained, rather than restrained and unmarked."""
    frame = _telemetry(
        chair_seconds=None, out_of_cage_seconds=None, deployment="cage_side"
    )

    line = [
        t for t in render(frame).splitlines() if t.strip().startswith("chair:")
    ]
    assert len(line) == 1
    assert "the animal is home" in line[0]


def test_the_console_still_shows_a_head_fixed_sessions_chair_clock():
    """The kind that has the marks keeps the number, formatted as a clock."""
    frame = _telemetry(chair_seconds=107.0, deployment="rig_fixed")

    assert "chair: 1:47" in render(frame)


def test_the_console_names_the_deployment_it_is_watching():
    """Read, not derived. Two kinds share one `None` for chair time, and `render`
    promises to name a field per line rather than infer one."""
    assert "deployment: rig_chaired" in render(_telemetry(deployment="rig_chaired"))


def test_the_console_warns_as_the_out_of_cage_limit_approaches():
    """**PI, 2026-09-20.** The console showed the clock and nothing drew attention as
    it ran out, so a session ended as an interruption rather than as a deadline an
    operator had been working towards. The warning is high on the screen, beside the
    stop reason, because that is where a person looks when something is wrong."""
    frame = _telemetry(duration_warning="out_of_cage: subject 'A' has 900 s left")

    rendered = render(frame)

    assert "WARNING: out_of_cage: subject 'A' has 900 s left" in rendered
    assert rendered.index("WARNING:") < rendered.index("fluid session:")


def test_the_console_is_quiet_when_there_is_nothing_to_warn_about():
    """A warning line that is always present is a line nobody reads."""
    assert "WARNING" not in render(_telemetry(duration_warning=None))




# ---------------------------------------------------------------------------
# A departure far from now: the confirmation, and the amendment
# ---------------------------------------------------------------------------
#
# **PI, 2026-09-20:** *"if a number is input that is more than 30 min from the
# current time, a warning should appear that the experimenter must click through to
# confirm. There should also be an option to update the time if necessary, but a
# reason should be given and the experimenter name logged."*
#
# **`tasks/reference_bounds.py` cannot reach this band**, and that is worth knowing
# before reading these tests rather than after: its `out_of_cage` ceiling is a
# deliberately implausible ten minutes, so anything more than thirty minutes ago is
# refused outright by the ceiling long before a confirmation is offered. Every test
# here therefore writes its own bounded config with a twelve-hour ceiling -- the
# institutional figure S8 5.2 item 4 states -- which is also the only shape in
# which the confirmation band exists at all.

_FAR_BOUNDS = '''\
"""A bounded config for the confirmation band: a real twelve-hour ceiling.

`tasks/reference_bounds.py`'s ten minutes is a placeholder by design, and it is
shorter than the thirty-minute confirmation threshold, so the band between them is
empty there. This is a test fixture and never leaves the suite.
"""

from wl_expcontroller.bounds import Bounds, Ceiling, Floor

BOUNDS = Bounds(
    subject="REFERENCE",
    ceilings={
        "reward_correct": Ceiling(value=0.05, maximum=10.0, unit="mL"),
        "out_of_cage": Ceiling(value=43_200.0, maximum=43_200.0, unit="s"),
    },
    minima={"daily_fluid": Floor(value=20.0, unit="mL")},
)
'''


def _far_bounds(tmp_path) -> str:
    path = tmp_path / "far_bounds.py"
    path.write_text(_FAR_BOUNDS, encoding="utf-8")
    return str(path)


def _load_bounds_for_test(tmp_path):
    from pathlib import Path

    from wl_expcontroller.cli import _load_bounds

    # `_load_bounds` reads a `Path` (`.stem`, in `cli.py`); `_far_bounds` returns
    # `str` for the CLI's own `--bounds` flag (also `type=Path`, argparse's to
    # convert). This helper is the one caller that skips argparse, so it converts.
    return _load_bounds(Path(_far_bounds(tmp_path)))


def _hours_ago(hours: float) -> str:
    """A clock time `hours` in the past, with its date, as an operator would type it
    for an overnight or early-morning departure."""
    when = datetime.now().astimezone() - timedelta(hours=hours)
    return when.isoformat(timespec="minutes")


def _run_args(tmp_path, *extra: str) -> list:
    return [
        "run",
        "tasks/fixation_detection.py",
        "--allocation", "tasks/allocation.py",
        "--bounds", _far_bounds(tmp_path),
        "--root", str(tmp_path),
        "--session-id", "2027-01-14_01",
        "--subject", "REFERENCE",
        "--delivered-today", "0",
        "--trials", "2",
        *_TASK_SETS,
        *extra,
    ]


def _notes(tmp_path) -> list:
    path = tmp_path / "2027-01-14_01" / "expcontroller" / "welfare_notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_a_far_departure_is_refused_when_nobody_can_be_asked(tmp_path):
    """**The non-interactive path must not proceed in silence.**

    `wlx run` is a command line that may have no terminal behind it -- a wrapper, a
    scheduler, a `labhost` process. A confirmation nobody made is worse than no
    confirmation, because the record then says a person saw a nine-hour departure
    and nobody did. So it refuses, and the message names the flag that is the honest
    way to say it out loud."""
    with pytest.raises(SystemExit) as refused:
        main(_run_args(tmp_path, "--out-of-cage-at", _hours_ago(9)))

    assert "--confirm-out-of-cage" in str(refused.value)
    assert "no terminal" in str(refused.value)


def test_the_flag_is_the_non_interactive_confirmation_and_says_so(tmp_path):
    """An explicit flag is a deliberate statement, so it is accepted -- and it is
    recorded as having come from a flag rather than from a person at a terminal,
    because a wrapper with it baked in is exactly how the ruling would be defeated
    quietly."""
    exit_code = main(
        _run_args(
            tmp_path, "--out-of-cage-at", _hours_ago(9), "--confirm-out-of-cage"
        )
    )

    assert exit_code == 0
    rows = _notes(tmp_path)
    assert [row["kind"] for row in rows] == [
        "departure", "departure confirmed", "return not recorded",
    ]
    assert rows[1]["how"] == "--confirm-out-of-cage, with no terminal attached"


def test_a_near_departure_asks_nothing_and_writes_no_confirmation(tmp_path):
    """The ordinary session is untouched: no prompt, no flag needed, no confirmation
    or amendment row. A confirmation that appeared every session would be clicked
    past every session. (P4d-2a: `left_cage` now writes its own `departure` row
    unconditionally, and nobody is here to take the return either, so the run still
    ends with a `return not recorded` row -- neither is what this test is about.)"""
    assert main(_run_args(tmp_path, "--out-of-cage-at", _hhmm())) == 0
    assert _kinds(tmp_path) == ["departure", "return not recorded"]


def test_an_interactive_run_asks_and_a_person_can_confirm(tmp_path, monkeypatch):
    """With a terminal, it asks. The answer is a person's act, which is the whole
    content of the ruling."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "confirm")

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hours_ago(9)))

    assert exit_code == 0
    rows = _notes(tmp_path)
    # P4d-2a: the return prompt asks too, at the terminal this test also fakes --
    # and its fixed `"confirm"` answer is not a clock time three times running.
    assert [row["kind"] for row in rows] == [
        "departure", "departure confirmed", "return not recorded",
    ]
    assert rows[1]["how"] == "confirmed at the terminal"


def test_an_interactive_run_stops_when_the_person_does_not_confirm(
    tmp_path, monkeypatch
):
    """Anything that is not a confirmation is a refusal, including end-of-input. A
    prompt whose default is "proceed" is the silent path wearing a question mark."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")

    with pytest.raises(SystemExit) as refused:
        main(_run_args(tmp_path, "--out-of-cage-at", _hours_ago(9)))

    assert "not confirmed" in str(refused.value)
    assert _notes(tmp_path) == []


def test_an_interactive_run_can_amend_the_time_with_a_reason_and_a_name(
    tmp_path, monkeypatch
):
    """**The option the PI asked for beside the confirmation.** The amended time is
    what the session is bounded by, and the row says who changed it and why."""
    answers = iter(
        ["amend", _hours_ago(0.2), "typed 08:45 for 18:45", "jake", "now"]
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hours_ago(9)))

    assert exit_code == 0
    rows = _notes(tmp_path)
    # P4d-2a: the return prompt asks too, at the same terminal, and this run's last
    # answer -- "now" -- takes it.
    assert [row["kind"] for row in rows] == [
        "departure", "departure amended", "returned",
    ]
    assert rows[1]["reason"] == "typed 08:45 for 18:45"
    assert rows[1]["by"] == "jake"
    assert rows[1]["was"] != rows[1]["now"]


def test_an_amendment_can_be_made_without_a_terminal_too(tmp_path):
    """Same three things, stated as flags. The interactive prompt is a way of
    supplying them, not a second rule about what an amendment is."""
    exit_code = main(
        _run_args(
            tmp_path,
            "--out-of-cage-at", _hours_ago(9),
            "--amend-out-of-cage-to", _hhmm(),
            "--amend-reason", "wl-works pushed the wrong departure",
            "--as", "jake",
        )
    )

    assert exit_code == 0
    rows = _notes(tmp_path)
    # P4d-2a: no terminal and no console attached, so nobody can take the return
    # either -- that is a `return not recorded` row, not a second rule about what an
    # amendment is.
    assert [row["kind"] for row in rows] == [
        "departure", "departure amended", "return not recorded",
    ]
    assert rows[1]["how"] == "--amend-out-of-cage-to"
    assert "local" in rows[1]["now_local"]


def test_an_amendment_with_no_reason_is_refused(tmp_path):
    """No default and no blank: the reason is the row's whole reason for existing."""
    with pytest.raises(SystemExit, match="refused: .*no reason"):
        main(
            _run_args(
                tmp_path,
                "--out-of-cage-at", _hours_ago(9),
                "--amend-out-of-cage-to", _hhmm(),
                "--as", "jake",
            )
        )


def test_an_amendment_with_no_actor_is_refused(tmp_path):
    """`--as WHO` is required here for the reason it is required for a console
    write: an anonymous change to a welfare clock is worse than none."""
    with pytest.raises(SystemExit, match="refused: .*nobody"):
        main(
            _run_args(
                tmp_path,
                "--out-of-cage-at", _hours_ago(9),
                "--amend-out-of-cage-to", _hhmm(),
                "--amend-reason", "typed 08:45 for 18:45",
            )
        )


def test_an_amended_time_still_meets_every_refusal_the_original_would(tmp_path):
    """An amendment is not an override. The amended value goes through `left_cage`
    exactly as the original does, so a "correction" into the future is refused."""
    tomorrow = (datetime.now().astimezone() + timedelta(hours=2)).isoformat(
        timespec="minutes"
    )

    with pytest.raises(SystemExit, match="refused: .*in the future"):
        main(
            _run_args(
                tmp_path,
                "--out-of-cage-at", _hours_ago(9),
                "--amend-out-of-cage-to", tomorrow,
                "--amend-reason", "typed 08:45 for 18:45",
                "--as", "jake",
            )
        )


def test_a_departure_past_the_ceiling_is_still_refused_without_a_prompt(
    tmp_path, monkeypatch
):
    """**The band has two edges and only one of them asks.** Past the ceiling the
    session is refused outright, with no confirmation offered -- offering one would
    teach an operator that the prompt is what stands between them and a run."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": pytest.fail("a session past its ceiling asks nobody"),
    )

    with pytest.raises(SystemExit, match="refused: .*against a ceiling of"):
        main(_run_args(tmp_path, "--out-of-cage-at", _hours_ago(13)))


def test_the_dst_gap_is_closed_as_a_ruling_and_the_description_is_kept():
    """**Ruling 2, PI 2026-09-20: closed, not fixed.** *"the dst switches happen in
    the night, when no experiments occur."* So the spring-forward hour that resolves
    `02:30` to `03:30` cannot arise, and the arithmetic is left as it is.

    **The description has to survive the dismissal.** It was dismissed because of a
    fact about when experiments happen, not because of anything about the
    arithmetic -- so if night sessions ever start, whoever reads this must find what
    would happen rather than a note saying it was considered and closed.
    """
    doc = _wall_clock_time.__doc__

    assert "no experiments occur" in doc, "the PI's reason, in his own words"
    assert "night session" in doc, "the condition the dismissal rests on"
    assert "03:30" in doc, "what the skipped hour still resolves to, kept"
    assert "out up to an hour" in doc, "and which direction that is wrong in"


def test_a_closed_stdin_is_not_a_terminal_and_the_flag_still_works(
    tmp_path, monkeypatch
):
    """**fd 0 closed makes `sys.stdin` `None`, not a non-tty.**

    Found by review probing the non-interactive path with a pipe, a here-doc,
    `/dev/null`, `yes c |`, a closed fd 0 and a real pty. Only the closed one got
    through, and it got through as an `AttributeError` rather than a sentence -- so
    it failed safe (no session, no row) while defeating `--confirm-out-of-cage`,
    which is the documented way to run this headless. A traceback here also breaks
    the rule the same diff states forty lines down: every welfare refusal on this
    path is a message, not a stack trace.
    """
    monkeypatch.setattr("sys.stdin", None)

    exit_code = main(
        _run_args(
            tmp_path, "--out-of-cage-at", _hours_ago(9), "--confirm-out-of-cage"
        )
    )

    assert exit_code == 0
    rows = _notes(tmp_path)
    # P4d-2a: with `sys.stdin` `None` there is no terminal for the return either, so
    # this closed-stdin run still ends with a `return not recorded` row.
    assert [row["kind"] for row in rows] == [
        "departure", "departure confirmed", "return not recorded",
    ]
    assert rows[1]["how"] == "--confirm-out-of-cage, with no terminal attached"


def test_a_closed_stdin_refuses_with_a_sentence_rather_than_a_traceback(
    tmp_path, monkeypatch
):
    """The other half: with no flag and no stdin at all, the refusal is the ordinary
    non-interactive one, naming what to pass."""
    monkeypatch.setattr("sys.stdin", None)

    with pytest.raises(SystemExit) as refused:
        main(_run_args(tmp_path, "--out-of-cage-at", _hours_ago(9)))

    assert "--confirm-out-of-cage" in str(refused.value)
    assert "no terminal" in str(refused.value)


def test_abort_at_the_prompt_stops_rather_than_starting_an_amendment(
    tmp_path, monkeypatch
):
    """The prompt said "anything else to stop" and matched `a`-anything as *amend*,
    so `abort` walked into the amendment flow. It still ended in a refusal -- the
    reason and the name would have been blank -- but a prompt that lies about what a
    word does is the kind of thing an operator learns once and remembers wrong."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "abort")

    with pytest.raises(SystemExit) as refused:
        main(_run_args(tmp_path, "--out-of-cage-at", _hours_ago(9)))

    assert "not confirmed" in str(refused.value)
    assert _notes(tmp_path) == []


def test_the_shipped_reference_config_cannot_reach_the_confirmation_band(tmp_path):
    """**Stated in `--confirm-out-of-cage`'s help, and checked here rather than
    believed.**

    `tasks/reference_bounds.py`'s `out_of_cage` ceiling is a deliberately implausible
    ten minutes -- **shorter than `welfare.CONFIRM_MARK_WITHIN`, which is thirty** --
    so a departure far enough to need confirming is refused by the ceiling before any
    confirmation is offered. Correct on both sides: the threshold is the PI's number
    and is deliberately not derived from the ceiling. The consequence, which review
    found, is that nothing that ships could dry-run the one welfare interaction an
    operator is asked to perform.
    """
    with pytest.raises(SystemExit, match="refused: .*against a ceiling of"):
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--allocation", "tasks/allocation.py",
                "--bounds", "tasks/reference_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hours_ago(9),
                "--delivered-today", "0",
                "--trials", "2",
            ]
        )


def test_the_twelve_hour_reference_config_can(tmp_path):
    """The other half, and the reason `tasks/twelve_hour_bounds.py` exists: the same
    command against a config carrying the real institutional ceiling reaches the
    confirmation instead of the ceiling refusal. Both guards of
    `tasks/reference_bounds.py` still apply to it -- subject `REFERENCE`, and every
    fluid number still an implausible placeholder."""
    with pytest.raises(SystemExit) as refused:
        main(
            [
                "run",
                "tasks/fixation_detection.py",
                "--allocation", "tasks/allocation.py",
                "--bounds", "tasks/twelve_hour_bounds.py",
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hours_ago(9),
                "--delivered-today", "0",
                "--trials", "2",
            ]
        )

    assert "Confirm it, or amend it" in str(refused.value)
    assert "--confirm-out-of-cage" in str(refused.value)


def test_the_twelve_hour_reference_config_runs_a_session_when_confirmed(
    tmp_path, capsys
):
    """And it is a config a session actually runs under, not only one that refuses --
    the dry run the help text points an operator at has to end somewhere."""
    exit_code = main(
        [
            "run",
            "tasks/fixation_detection.py",
            "--allocation", "tasks/allocation.py",
            "--bounds", "tasks/twelve_hour_bounds.py",
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_01",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hours_ago(9),
            "--confirm-out-of-cage",
            "--delivered-today", "0",
            "--trials", "3",
            *_TASK_SETS,
        ]
    )

    assert exit_code == 0
    assert "the animal has been out 9 hours" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# P4d-2a: the return to the cage
# ---------------------------------------------------------------------------


def _kinds(tmp_path) -> list[str]:
    return [row["kind"] for row in _notes(tmp_path)]


def test_a_headless_run_records_that_nobody_could_mark_the_return(tmp_path):
    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "return not recorded"]
    assert _notes(tmp_path)[-1]["reason"] == "no terminal and no console attached"


def test_a_run_at_a_terminal_takes_the_return(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "now")

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "returned"]
    assert _notes(tmp_path)[-1]["how"] == "terminal"


def test_a_head_fixed_run_whose_frames_outran_the_wall_takes_the_return(
    tmp_path, monkeypatch
):
    """**The slice's main path with default flags** (P4d-2a spec §10, found by Task
    6's implementer). `wlx run` defaults to `rig-fixed`, and the simulator does not
    wait for the frames it counts: two hundred trials put at least a hundred seconds
    of inter-trial interval alone (`iti` = 0.5 s) on the frame clock, however little
    wall time they took. While welfare counted in the frame base, that lead refused
    the first post-loop frame -- chair time longer than out-of-cage -- and refused the
    return typed `now` as before the head release, so this run faulted after its loop.
    Every welfare duration is on the wall clock since, and the frames' lead is
    nothing welfare can see."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "now")
    # **Pinned, not assumed** (Task 7 fix round 1, Minor 3): this test is about the
    # default kind, so it records what the parser actually gave `--deployment` and
    # fails if the default ever stops being `rig-fixed`.
    parsed: list = []
    real_parse_args = argparse.ArgumentParser.parse_args

    def recording_parse_args(parser, *args, **kwargs):
        namespace = real_parse_args(parser, *args, **kwargs)
        parsed.append(namespace)
        return namespace

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", recording_parse_args)

    exit_code = main(
        _run_args(tmp_path, "--out-of-cage-at", _hhmm(), "--trials", "200")
    )

    assert [namespace.deployment for namespace in parsed] == ["rig-fixed"]
    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "returned"]
    trials = tmp_path / "2027-01-14_01" / "expcontroller" / "trials.jsonl"
    assert len(trials.read_text().splitlines()) == 200, "the loop ran every trial"


@pytest.mark.parametrize("step", [120.0, -120.0], ids=["host-ahead", "host-behind"])
def test_the_return_prompt_reads_now_on_the_sessions_clock(tmp_path, monkeypatch, step):
    """**Task 7 fix round 1, Important.** `now` at the return prompt is compared with
    marks taken on the session's anchored wall (`Session.wall_now`, Ruling 8): the
    loop-end release, and the wall `returned_to_cage` reads. Read from `time.time()`
    instead, it lands wherever the host clock has been moved to since the session
    began -- ahead, and it is refused as in the future; behind, and as before the
    release. The host clock is stepped two minutes either way at the prompt, after
    the session was created and its anchor taken; `now` is taken either way."""
    real_time = time.time
    offset = [0.0]
    monkeypatch.setattr(time, "time", lambda: real_time() + offset[0])

    def answer(_prompt=""):
        offset[0] = step
        return "now"

    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", answer)

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "returned"]


def test_a_far_return_is_confirmed_at_the_terminal(tmp_path, monkeypatch):
    """**`rig-chaired`, because a far return is only possible without a release
    after it.** `wlx run` releases a `rig-fixed` head at the loop's end, a moment
    ago, and a return an hour ago would put the animal home while still in the
    chair -- `welfare` refuses that before any confirmation is asked, and rightly.
    A chaired session has no head-fixation marks, so the confirmation is what this
    reaches."""
    answers = iter([_hours_ago(1), "confirm"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    exit_code = main(
        _run_args(
            tmp_path,
            "--out-of-cage-at", _hours_ago(2),
            "--confirm-out-of-cage",
            "--deployment", "rig-chaired",
        )
    )

    assert exit_code == 0
    assert _kinds(tmp_path) == [
        "departure", "departure confirmed", "returned", "return confirmed",
    ]


def test_a_return_before_the_departure_is_refused_and_asked_again(tmp_path, monkeypatch):
    """Review Focus 3: the wrong half of the day, typed at the prompt."""
    answers = iter([_hours_ago(3), "confirm", "now"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    exit_code = main(
        _run_args(
            tmp_path,
            "--out-of-cage-at", _hours_ago(2),
            "--confirm-out-of-cage",
        )
    )

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "departure confirmed", "returned"]


def test_three_answers_that_are_not_a_time_end_the_prompt_and_say_so(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "confirm")

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "return not recorded"]
    assert _notes(tmp_path)[-1]["reason"] == "no clock time given at the terminal"


def test_an_interrupted_return_prompt_is_recorded_and_exits_130(tmp_path, monkeypatch):
    """Review Focus 1."""

    def interrupt(_prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", interrupt)

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 130
    assert _kinds(tmp_path) == ["departure", "return not recorded"]
    assert _notes(tmp_path)[-1]["reason"] == "interrupted at the terminal"


def test_a_console_can_record_the_return_while_the_terminal_waits(tmp_path, monkeypatch):
    """Review Focus 2. The prompt is blocked in `input()` when the console's mark
    lands; the next answer is told so, and there is one `returned` row, not two."""
    from wl_expcontroller.cli import _settle_return
    from wl_expcontroller.dio import Simulated as Card
    from wl_expcontroller.taskd import Session, SessionSpec
    from wl_expcontroller.welfare import Deployment, Simulated as Pump

    spec = SessionSpec(
        task=GOOD, allocation=ALLOCATION, root=tmp_path, session_id="2027-01-14_01",
        subject="REFERENCE", trials=3, frame_period=1 / 240, seed=1, values={},
        bounds=_load_bounds_for_test(tmp_path), already_delivered_today=0.0,
        deployment=Deployment.RIG_CHAIRED,
    )
    session = Session(spec, card=Card(), pump=Pump())
    session.left_cage(at=session.wall_now() - 60.0)

    def answer(_prompt=""):
        session.returned_to_cage(session.wall_now(), by="sam", how="console")
        return "now"

    monkeypatch.setattr("builtins.input", answer)

    assert _settle_return(session, "jake") is None
    kinds = _kinds(tmp_path)
    assert kinds.count("returned") == 1
    assert _notes(tmp_path)[-1]["how"] == "console"


def test_a_failure_in_the_post_loop_phase_is_raised_not_swallowed(tmp_path, monkeypatch):
    """Ruling B (Task 6 review). `_close_interval`'s background thread runs
    `await_return` wrapped in a helper that catches whatever it raises instead of
    letting the thread die with it unseen. This proves the exception still reaches
    the caller -- on the main thread, once the terminal side is done -- rather than
    being swallowed: the terminal's own `returned` mark must not be lost along with
    the fault that came after it.
    """

    def _boom(self, give_up, heartbeat=1.0):
        raise RuntimeError("publish failed")

    monkeypatch.setattr("wl_expcontroller.taskd.Session.await_return", _boom)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "now")

    with pytest.raises(RuntimeError, match="publish failed"):
        main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert _kinds(tmp_path)[-1] == "returned"


# ---------------------------------------------------------------------------
# Task 6 review, fix round 1
# ---------------------------------------------------------------------------


def test_a_background_fault_during_a_timed_wait_names_the_fault_not_a_timeout(
    tmp_path, monkeypatch
):
    """Important 1. `waiter.join(timeout=...)` (`cli._close_interval`) returns the
    instant the background thread dies, which can be long before the timeout it was
    given -- and the row must not then say "nobody marked it within N s" when N
    seconds never passed. `--await-return-for 5` here, but the fault fires at once,
    so a wrong fix would still show `5` in the reason though barely any time passed.
    The exception itself must still reach `main()` unchanged (Ruling 5, P4d-2a
    spec §5) -- swallowing it would be the same mistake `_wait`'s own docstring
    refuses."""

    def _boom(self, give_up, heartbeat=1.0):
        raise RuntimeError("publish failed")

    monkeypatch.setattr("wl_expcontroller.taskd.Session.await_return", _boom)

    with pytest.raises(RuntimeError, match="publish failed"):
        main(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", BOUNDS,
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_01",
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
                "--delivered-today", "0",
                "--trials", "5",
                *_TASK_SETS,
                "--link", "tcp://127.0.0.1:0,tcp://127.0.0.1:0",
                "--await-return-for", "5",
            ]
        )

    rows = _notes(tmp_path)
    assert rows[-1]["kind"] == "return not recorded"
    assert rows[-1]["reason"] == "the post-loop phase failed: RuntimeError"


def test_await_return_for_names_the_seconds_when_nobody_marks_the_return(tmp_path):
    """Important 2. `--await-return-for`'s own lapse -- no terminal, no console,
    nobody there -- had no test. `0.05` keeps this fast: nothing here waits on a
    heartbeat (`Session.await_return`'s default is 1 s) longer than the timed wait
    itself needs."""
    exit_code = main(
        [
            "run", GOOD,
            "--allocation", ALLOCATION,
            "--bounds", BOUNDS,
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_01",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--delivered-today", "0",
            "--trials", "5",
            *_TASK_SETS,
            "--link", "tcp://127.0.0.1:0,tcp://127.0.0.1:0",
            "--await-return-for", "0.05",
        ]
    )

    assert exit_code == 0
    rows = _notes(tmp_path)
    assert rows[-1]["kind"] == "return not recorded"
    assert rows[-1]["reason"] == "nobody marked it within 0.05 s"


def test_an_empty_answer_at_the_terminal_ends_the_prompt_and_asks_nothing_more(
    tmp_path, monkeypatch
):
    """Minor 2. An empty answer -- and end of input, `_ask`'s own path for it --
    is a quiet non-answer, not a re-ask: a script whose input closes mid-prompt
    must not be asked a second question it has nothing left to answer."""
    asked = []

    def answer(prompt=""):
        asked.append(prompt)
        return ""

    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", answer)

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert len(asked) == 1, "no answer at all ends the prompt at once"
    assert _kinds(tmp_path) == ["departure", "return not recorded"]
    assert _notes(tmp_path)[-1]["reason"] == "no answer at the terminal"
