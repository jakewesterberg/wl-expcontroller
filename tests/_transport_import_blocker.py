"""Run in a fresh subprocess by `test_no_transport_leak.py` -- never imported in
this process, and never collected by pytest itself (its name does not match
`test_*.py`).

**Why a subprocess at all.** Once `zmq` or `msgpack` has been imported anywhere in a
process, `sys.modules` caches it, and every later `import zmq` returns the cached
module without ever consulting `sys.meta_path` again. By the time this repository's
test suite reaches any single test, `tests/test_link.py` has almost certainly already
imported real `zmq`/`msgpack` (its `ZmqLink`/`ZmqConsole` tests need them), so a
blocker installed in that same process would protect nothing. Only a fresh
interpreter, with the blocker installed before either name is first imported, proves
the property this file exists to prove: that `wl_expcontroller.link` and
`wl_expcontroller.taskd` do not require a transport dependency to import.

**Why `find_spec`, never `find_module`.** Task 1 of this slice originally shipped a
verification using a `sys.meta_path` finder that defined only `find_module`. Task 1's
own fix round found that hook silently inert on this interpreter (Python 3.13.9):
`importlib`'s finder protocol no longer falls back to the legacy hook, so a
`find_module`-only finder is skipped outright and a real `import zmq` sails straight
through it while the check goes on to report success -- a check that cannot fail,
which is exactly what `CLAUDE.md`'s `tools/mutate.py` rule exists to catch, just
written by hand instead of as a pytest test. This script uses `find_spec`, and proves
the block can fail (`import zmq` and `import msgpack` must each raise) before it
trusts anything the block appears to protect.
"""

from __future__ import annotations

import sys
from pathlib import Path

# This worktree's own source, ahead of anything else on sys.path. R9 (see
# .superpowers/sdd/2026-09-19-p4d1-console-link/progress.md): the shared conda base
# env used to run this suite holds an editable install of wl_expcontroller pointing at
# the MAIN checkout, not this worktree, so a subprocess given no explicit path would
# silently prove this property of the wrong tree. Computed relative to this file
# rather than hard-coded, so the check is correct regardless of where this worktree
# (or its eventual merge into `main`) happens to live on disk.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

for _mod in ("zmq", "msgpack"):
    assert _mod not in sys.modules, f"{_mod} already imported before the blocker was installed"


class _Blocker:
    """A meta-path finder that raises for `zmq`/`msgpack` and defers to the next
    finder for everything else. `find_spec`, never `find_module` -- see the module
    docstring above."""

    blocked = {"zmq", "msgpack"}

    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in self.blocked:
            raise ImportError(f"simulated absence: {name} is not installed")
        return None


sys.meta_path.insert(0, _Blocker())

# Prove the blocker can fail before trusting anything it appears to protect.
_failed_to_block = []
for _mod in ("zmq", "msgpack"):
    try:
        __import__(_mod)
    except ImportError as exc:
        print(f"BLOCKED: import {_mod} raised ({exc})")
    else:
        print(f"NOT BLOCKED: import {_mod} succeeded -- the blocker did not engage")
        _failed_to_block.append(_mod)

if _failed_to_block:
    print(
        f"ABORT: blocker did not prove it can fail for {_failed_to_block}; "
        f"not trusting the import checks that would follow"
    )
    sys.exit(1)

import wl_expcontroller.link as _link  # noqa: E402
import wl_expcontroller.taskd as _taskd  # noqa: E402

# Not just "it imported" -- imported from THIS worktree, not a stale editable-install
# target (R9 again). A path from outside _REPO_ROOT would mean this whole script
# proved the property of a different tree.
for _name, _mod in (("link", _link), ("taskd", _taskd)):
    _resolved = str(Path(_mod.__file__).resolve())
    if not _resolved.startswith(str(_REPO_ROOT)):
        print(f"ABORT: wl_expcontroller.{_name} imported from outside this worktree: {_resolved}")
        sys.exit(1)

print(f"PASS: wl_expcontroller.link imported ({_link.__file__})")
print(f"PASS: wl_expcontroller.taskd imported ({_taskd.__file__})")
