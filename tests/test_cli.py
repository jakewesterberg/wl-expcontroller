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

import json
import threading
from dataclasses import replace

import pytest

from wl_expcontroller.cli import main, render
from wl_expcontroller.link import (
    Refused,
    SetParameter,
    Staged,
    Telemetry,
    ZmqConsole,
    ZmqLink,
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
            "--delivered-today", "0",
            "--trials", "5",
            *_TASK_SETS,
        ]
    )

    assert exit_code == 0


def test_wlx_run_with_link_lets_a_real_console_attach(tmp_path):
    """The wiring this task exists for (CLAUDE.md: "a safety component ships with
    its consumer, or its absence fails"). `test_link.py` already proves
    `ZmqLink`/`ZmqConsole` talk to each other directly; nothing before this test
    proved that `wlx run --link` -- through `main()`'s own argument parsing --
    actually attaches a real `ZmqLink` to a running `Session`, or that a console's
    write travels all the way to `parameter_changes.jsonl`.

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
    rather than trusting that any frame arriving means the write landed; **(b)** a
    `--trials` count comfortably past `tasks/reference_bounds.py`'s chair-time
    ceiling at these task parameters (empirically ~1,500 trials), so the session
    has hundreds of passes still to run after this early command is sent, and the
    exact-last-pass coincidence (a) guards against has nowhere near enough room
    to land by chance.
    """
    probe = ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    pub_endpoint, rep_endpoint = probe.pub_endpoint, probe.rep_endpoint
    probe.close()

    result: dict[str, int] = {}

    def _run() -> None:
        result["exit_code"] = main(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", BOUNDS,
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_04",
                "--subject", "REFERENCE",
                "--delivered-today", "0",
                "--trials", "5000",
                *_TASK_SETS,
                "--link", f"{pub_endpoint},{rep_endpoint}",
            ]
        )

    runner_thread = threading.Thread(target=_run)
    runner_thread.start()
    try:
        with ZmqConsole(pub_endpoint, rep_endpoint) as console:
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
    finally:
        runner_thread.join(timeout=15)
    assert not runner_thread.is_alive(), "wlx run did not finish on its own"
    assert result["exit_code"] == 0

    changes_path = (
        tmp_path / "2027-01-14_04" / "expcontroller" / "parameter_changes.jsonl"
    )
    changes = [json.loads(line) for line in changes_path.read_text().splitlines()]
    fix_hold_changes = [c for c in changes if c["name"] == "fix_hold"]
    assert fix_hold_changes, "the console's SetParameter never reached the record"
    assert fix_hold_changes[0]["by"] == "jake"
    assert fix_hold_changes[0]["now"] == 0.4


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
    """
    base = Telemetry(
        schema=1,
        session_id="2027-01-14_01",
        subject="REFERENCE",
        trial_index=3,
        block="session",
        stopped_because="",
        fluid_session_ml=1.25,
        fluid_today_ml=None,
        shortfall_ml=None,
        chair_seconds=42.0,
        outcomes={},
        hangs=0,
        owed={},
        staged=(),
        refusals=(),
    )
    return replace(base, **overrides) if overrides else base


def test_console_renders_a_telemetry_frame_without_inventing_a_number():
    """Every line the console prints names a field of `Telemetry`. An unknown day
    prints UNKNOWN, never 0.0 -- `wlx run` already does this and the two must agree."""
    frame = _telemetry(fluid_today_ml=None, shortfall_ml=None)

    rendered = render(frame)

    assert "supplement: UNKNOWN" in rendered
    assert "0.0" not in rendered.split("supplement:")[1].splitlines()[0]


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
    proven by `calls`, below -- not any real transport behaviour, which
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
