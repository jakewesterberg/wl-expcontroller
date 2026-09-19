"""The core must never acquire a transport dependency (`wl_expcontroller/link.py`'s
own docstring; CLAUDE.md's core/display split; S9a §5's argument, which holds
identically for the console). A rig operator running `wlx run` from a terminal needs
neither `zmq` nor `msgpack`, and this repository keeps a Python 3.13 CI leg that
installs only the core specifically so that a transport dependency leaking into
`taskd.py` or `link.py` fails that leg loudly.

`link.py` is the first module in this repository to `import zmq` (Task 5 of the
console-link slice); this is its permanent regression test, not a one-off
verification that lives only in a session's scratchpad and a report. Task 1 shipped
exactly such a one-off, and Task 1's own fix round found it had been proving nothing
-- see `_transport_import_blocker.py`'s module docstring for the full story. That
script is re-run here, by every future test run, rather than trusted once and
forgotten.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BLOCKER_SCRIPT = Path(__file__).resolve().parent / "_transport_import_blocker.py"
_REPO_ROOT = _BLOCKER_SCRIPT.parent.parent


def test_link_and_taskd_import_with_zmq_and_msgpack_unavailable():
    """Runs the blocker **in a subprocess, on purpose.** By the time this test runs,
    `tests/test_link.py` has almost certainly already imported real `zmq`/`msgpack`
    into this pytest process's `sys.modules` -- and once a module is cached there,
    `import zmq` returns the cached module without ever consulting `sys.meta_path`,
    so a blocker installed here, in-process, would protect nothing. Only a fresh
    interpreter, blocked before either name is first imported, proves anything.

    Asserts on the subprocess's own stdout rather than only its exit code, per
    CLAUDE.md's "read the harness's output, not its exit code" -- the script aborts
    with a non-zero exit for more than one reason (blocker failed to engage; import
    itself failed; import resolved to the wrong checkout), and the message says
    which one actually happened.
    """
    result = subprocess.run(
        [sys.executable, str(_BLOCKER_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(_REPO_ROOT),
    )

    assert result.returncode == 0, (
        f"blocker script failed (exit {result.returncode}):\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    # The blocker proved it can fail -- shown before anything it protects is
    # trusted -- ...
    assert "BLOCKED: import zmq raised" in result.stdout, result.stdout
    assert "BLOCKED: import msgpack raised" in result.stdout, result.stdout
    # ...and only then did the two modules under test import successfully, from this
    # worktree specifically (R9).
    assert "PASS: wl_expcontroller.link imported" in result.stdout, result.stdout
    assert "PASS: wl_expcontroller.taskd imported" in result.stdout, result.stdout
    assert str(_REPO_ROOT) in result.stdout, (
        f"expected both imports to resolve under {_REPO_ROOT}:\n{result.stdout}"
    )
