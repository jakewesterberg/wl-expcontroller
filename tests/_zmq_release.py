"""Every `ZmqLink`, `ZmqConsole` and `ZmqMarks` a test builds is held until its
teardown, and its `Context` is destroyed there directly. That includes the ones built where the test has
no handle: inside `main()` for `wlx run --link` and `wlx console`, and on `wlx serve`'s
telemetry thread. The teardown never goes through `close()` or `__exit__`, and it never
leaves a context for the cyclic garbage collector.

`test_serve.py` and `test_cli.py` import the fixture below. Those are the two files that
run those commands in this process. Pytest never collects this file, because its name
does not start with `test_`.

**Why it exists (P4d-2b b1's mutation gate, 2026-09-27).** `tools/mutate.py --returns
None wl_expcontroller/link.py close`, and the same for `__exit__`, reported `timed out
after 300s`. P4d-2a's gate read both as real failures. Faulthandler put the hang in a
test's own `gc.collect()`, in `weakref.py` -> `Context.destroy` -> `Context.term`. It
first showed in `test_serve.py`'s end-to-end test. With `test_serve.py` left out of
the run, it showed in the `gc.collect()` of `test_cli.py`'s
`test_wlx_run_with_link_lets_a_real_console_attach` and of its
`test_console_shows_a_schema_mismatch_as_a_sentence_not_a_traceback`. The mechanism,
measured in scratchpad probes:

1. With `close` or `__exit__` neutered, the `ZmqLink` that `wlx run --link` builds inside
   `main()` keeps its `Context` open after the run ends.
2. That link is reachable only through a reference cycle. `taskd.Session` holds its
   `Rig`, and since this branch the `Rig` holds `wall_clock=self.wall_now`, a method
   bound to the session. `gc.get_referrers` showed `ZmqLink <- Session <- method <- Rig
   <- Session`. Before `wall_clock`, reference counting freed the session and its link.
   `link.py`'s `weakref.finalize(self, self._ctx.destroy, 0)` then ran while both sockets
   were still alive, and it closed them.
3. Freed by the cyclic collector instead, the same finalizer found **0** live sockets in
   `Context._sockets`, a `WeakSet`. Freed by reference counting, it found 2. The sockets
   are gone from that set before the callback runs. `destroy` therefore closes nothing,
   and `term()` waits for two sockets that are still open. Each `Socket.__del__` would
   close its socket, but only after the callback returns, on the same thread. So
   `term()` never returns (pyzmq 27.2.0: `zmq/sugar/context.py` `destroy`, and
   `zmq/sugar/socket.py` `__del__`, both read 2026-09-27). A bare script reproduces it
   with no pytest at all: a class holding a context and one socket, put in a cycle,
   deleted, and then `gc.collect()`. **So an explicit `gc.collect()` is not the safe
   path that earlier comments here described. It is where the deadlock happens.**

**The deadlock itself was fixed in `link.py` in the commit after this file's (Ruling
18, 2026-09-27), and the list above is now history.** The finalizer runs
`link._release` with the sockets held strongly, so a cyclic collection of an unclosed
link or console closes them, terminates the context, and returns.
`tests/test_link.py`'s `*_released_by_the_collector*` tests pin that. This fixture
stays, for the reason in the next paragraph: it does not depend on a collection ever
coming.

A fixture's teardown does not wait for the collector, and it does not call the
functions a mutation neuters. Holding each object keeps it reachable, and so out of the
collector's hands, until teardown. Teardown destroys each context while its sockets are
still live. After that the finalizer is a no-op (`destroy` returns at once on a closed
context), whenever the cycle is later collected. Under unmutated code `close()` has
already destroyed every context, so all of this is a no-op too.
"""

from __future__ import annotations

import threading

import pytest

from wl_expcontroller.link import ZmqConsole, ZmqLink, ZmqMarks

#: Objects whose building thread was still running at teardown. That happens only once
#: a test has already failed, for example when a `wlx run` thread outlives its join.
#: They are never destroyed from this thread, because pyzmq's `Context.destroy`
#: docstring says it must not be called while sockets are active in other threads. They
#: are kept referenced, so the collector cannot reach them either.
#:
#: **That only postpones the release.** At interpreter exit, `weakref.finalize`'s exit
#: hook runs each parked object's still-live finalizer, `link._release`, on the main
#: thread. Its builder, a daemon thread, may still be alive then, which is the very case
#: this list exists to avoid. It is accepted because it happens only after a test has
#: already failed, and at exit.
#:
#: **The fixture also assumes an object is used only by the thread that built it.**
#: `builder.is_alive()` is the only question it asks. An object built on the test's
#: thread and handed to another thread that is still running would be destroyed here
#: while that thread uses it. No test in the two importing files did that when this
#: was written (checked 2026-09-27).
_STILL_IN_USE: list = []


@pytest.fixture(autouse=True)
def _every_zmq_context_released(monkeypatch):
    """Wrap `ZmqLink.__init__`, `ZmqConsole.__init__` and `ZmqMarks.__init__` (P4d-2b
    b2a: `wlx serve`'s mark thread builds one) to record each object and the thread
    that built it. At teardown, destroy each context directly with `linger=0`."""
    built: list[tuple[object, threading.Thread]] = []

    for cls in (ZmqLink, ZmqConsole, ZmqMarks):

        def _record_init(self, *args, _real_init=cls.__init__, **kwargs) -> None:
            try:
                _real_init(self, *args, **kwargs)
            finally:
                # Recorded even when construction raised after the context existed:
                # a `ZmqConsole` whose `connect` fails has one socket open.
                if getattr(self, "_ctx", None) is not None:
                    built.append((self, threading.current_thread()))

        monkeypatch.setattr(cls, "__init__", _record_init)

    yield

    here = threading.current_thread()
    for obj, builder in built:
        if builder is not here and builder.is_alive():
            _STILL_IN_USE.append(obj)
            continue
        obj._ctx.destroy(linger=0)
    built.clear()
