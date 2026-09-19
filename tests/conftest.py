"""Make `wl-preproc`'s frozen codec and calibration model importable for the
round-trip tests.

The dependency is **test-time only, deliberately**. `wl-preproc` is a pipeline
package that pulls DataJoint, Kilosort and SpikeInterface behind it; none of that
belongs on a task PC. So the rig runs our encoder and our own copy of their basis,
and the tests prove both agree with theirs (S2 §6.2). What we never do is write a
second *decoder* -- a second implementation of the framing is a second definition
free to drift.

**Two locations, because CI cannot use the first.** Beside this repo is the natural
layout on a laptop with both checkouts. It is unavailable to `actions/checkout`,
which resolves its `path` against `$GITHUB_WORKSPACE` and **throws** on anything
that escapes it -- so `path: ../wl-preproc` fails the step outright rather than
placing a sibling. That was found on 2026-09-05, in a CI run that had been red since
2026-08-31 with three encoder mutations SURVIVING: `words_for`, `words_for_code` and
`_checksum` are caught by the round-trip alone, and the round-trip was skipping.
CI therefore checks out into `<repo>/wl-preproc`, and both locations are searched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

#: Beside the repo (local), then inside it (CI). First one that exists wins; a
#: checkout in neither place leaves the contract tests to skip, which is a failure
#: rather than a skip whenever `WLX_REQUIRE_PREPROC=1`.
_CANDIDATES = (_ROOT.parent / "wl-preproc", _ROOT / "wl-preproc")

for _candidate in _CANDIDATES:
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
        break


@pytest.fixture
def zmq_cleanup():
    """Registers `ZmqLink`/`ZmqConsole` instances for guaranteed teardown, on a code
    path that does not go through `close()`/`__exit__` at all.

    **Moved here from `test_link.py` in Task 6's fix round 1** -- a pytest fixture is
    module-local unless it lives in `conftest.py`, and `test_cli.py` grew its own
    `ZmqLink`/`ZmqConsole` instances (`wlx run --link`'s end-to-end test) without this
    protection, which reintroduced the exact 300 s mutation hang the next paragraph
    describes, one commit after it was fixed: `tools/mutate.py --returns None
    wl_expcontroller/link.py close` timed out again, this time from contexts
    `test_cli.py` left abandoned rather than `test_link.py`'s. Same fixture, same
    reasoning, just visible to every file in this directory instead of one.

    **Fix round 2 (Task 5) -- why this exists rather than every test's own
    `try`/`finally` or `with`.** `tools/mutate.py --all` neuters `close()`'s entire
    body to prove it is covered (and, because `__exit__` only calls `close()`,
    neuters that too). Every test that used to clean up by calling `link.close()` or
    `with ZmqLink(...) as link:` left an abandoned `Context` behind under that
    mutation, because the call site still ran but the method did nothing. Several
    abandoned contexts, reachable only once pytest's own object graph triggers a
    cyclic GC pass, is what made `tools/mutate.py wl_expcontroller/link.py close`
    hang past its 300 s timeout -- confirmed by `sample`-ing the stuck process
    (`test_link.py`'s fix round 1 report has the full trace), and *not* fixed by
    routing cleanup through `Context.destroy(linger=0)` or a `weakref.finalize`
    safety net, because both still depend on *something* eventually reaching the
    abandoned object -- GC-driven either way, just with a different trigger.

    A fixture's teardown is not GC-driven: it always runs when the requesting test
    returns, pass or fail, and calls `Context.destroy(linger=0)` directly on the raw
    `._ctx` -- bypassing `close()`/`__exit__` entirely, so neutering either one
    cannot stop it. Verified this actually removes the hang before relying on it:
    a throwaway three-test file using this exact pattern, with `close()` neutered by
    hand, ran in 0.18s (one clean, fast, expected failure from the test that calls
    `close()` on purpose; no hang anywhere) where the equivalent `try`/`finally`
    version hung past 300s.

    Calling `destroy()` on an already-destroyed `Context` is a safe no-op (checked
    directly, not assumed), so a test that calls `close()`/uses `with` on purpose --
    because that is the behaviour it is testing -- registers here too, as a backup
    rather than a replacement for what it actually tests.
    """
    contexts = []

    def _register(obj):
        contexts.append(obj._ctx)
        return obj

    yield _register
    for ctx in contexts:
        ctx.destroy(linger=0)
