"""The telemetry message a session publishes to its consoles.

S9a §9, "The telemetry contract": every number on the console comes from the object
the record is written from, never computed beside it. These tests exist to catch the
one way that rule breaks silently -- a field that quietly started summing reward
commands instead of reading `welfare.session_total()` would still look like a
telemetry message and would still pass every other test in this suite.
"""

from __future__ import annotations

import time
from dataclasses import replace
from types import SimpleNamespace

from wl_expcontroller.bounds import Bounds, Ceiling, Floor
from wl_expcontroller.link import (
    Absent,
    Simulated,
    SetParameter,
    Stop,
    Telemetry,
    ZmqConsole,
    ZmqLink,
    decode,
    encode,
)
from wl_expcontroller.scheduler import Block, Condition, Scheduler
from wl_expcontroller.simulate import Tally
from wl_expcontroller.welfare import Simulated as Pump, Welfare


def _bounds(daily_fluid: float = 250.0) -> Bounds:
    return Bounds(
        subject="A",
        ceilings={"chair_time": Ceiling(value=14_400.0, maximum=14_400.0, unit="s")},
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


def _session_with(delivered_ml: float, already_today: float | None):
    """A stand-in for `Session`, carrying exactly what `Telemetry.of` reads from it.

    Not a real `Session`: constructing one loads a task file and an allocation from
    disk, which these tests have no reason to do. `Telemetry.of`'s parameters are
    untyped precisely so any object with the right shape counts as a session (see
    `link.py`). `.staged` and `.refusals` are supplied directly as plain tuples --
    stand-ins for the real `Session.staged` property and `Session.refusals` field,
    so this fixture does not need to construct either the live-parameter or the
    console-command machinery to satisfy `Telemetry.of`'s shape.

    `delivered_ml` becomes `welfare.delivered` -- the sync box's delivered-line
    figure -- rather than `welfare.commanded`, with `commanded` pinned to a small
    fixed value distinct from it. **This distinction is load-bearing.** Once
    `.delivered` is set, `session_total()` reconciles to `max(commanded, delivered)`
    (`bounds.reconcile`), so with `commanded` small and `delivered` the larger figure
    -- never the reverse, which `reconcile_report` treats as a pump fault rather than
    a smaller total -- `session_total()` lands on `delivered_ml`, distinct from
    `commanded`. Set `commanded=delivered_ml` instead (an earlier version of this
    fixture did, and left `.delivered` at its default `None`) and `session_total()`
    returns exactly `commanded` -- indistinguishable from a `Telemetry.of` that read
    `welfare.commanded` directly instead of calling `.session_total()`, which is the
    one bug S9a §9 exists to catch.
    """
    welfare = Welfare(
        bounds=_bounds(),
        pump=Pump(),
        already_today=already_today,
        commanded=0.1,
        delivered=delivered_ml,
    )
    return SimpleNamespace(
        spec=SimpleNamespace(session_id="2027-01-14_01", subject="A"),
        welfare=welfare,
        stopped_because="",
        staged=(),
        refusals=(),
        now=lambda: 0.0,
    )


def _scheduler() -> Scheduler:
    block = Block(name="session", conditions=[Condition("only", {}, target=1)])
    return Scheduler(blocks=[block], seed=0)


def test_telemetry_reads_welfare_rather_than_recomputing_it():
    """S9a §9's one rule. The console shows what `welfare` says was delivered, never a
    sum of reward commands -- so a bug in `welfare` shows up on screen rather than being
    masked by a second, agreeing implementation."""
    session = _session_with(delivered_ml=1.25, already_today=3.0)
    tally = Tally()

    telemetry = Telemetry.of(session, tally, _scheduler(), index=7)

    assert telemetry.fluid_session_ml == session.welfare.session_total()
    assert telemetry.fluid_today_ml == session.welfare.total_today()
    assert telemetry.shortfall_ml == session.welfare.shortfall()
    assert telemetry.trial_index == 7


def test_an_unknown_day_is_none_and_never_zero():
    """`shortfall()` answers `None` for a day nobody measured, and the console must
    carry that through rather than rendering a confident 0.0 (S9a §9)."""
    session = _session_with(delivered_ml=1.0, already_today=None)

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.fluid_today_ml is None
    assert telemetry.shortfall_ml is None


def _telemetry(**overrides) -> Telemetry:
    """A test telemetry object for console link tests.

    `_session_with(..., already_today=None)` already makes `fluid_today_ml` and
    `shortfall_ml` come out `None` (see `test_an_unknown_day_is_none_and_never_zero`
    above). `**overrides` lets a call site say so explicitly anyway -- via
    `dataclasses.replace` on the assembled `Telemetry` -- without this fixture
    growing a second construction path just to accept keyword tweaks.
    """
    base = Telemetry.of(_session_with(delivered_ml=1.0, already_today=None), Tally(), _scheduler(), index=0)
    return replace(base, **overrides) if overrides else base


def test_absent_publishes_nowhere_and_yields_no_commands():
    """**Unlike `dio.Absent` and `run.Unwired`, this one does not refuse**, and the
    difference is what is lost. A dropped event code is missing from a recording
    forever and a dropped reward is fluid an animal worked for. Telemetry nobody
    subscribed to loses nothing -- the record is the record, and a session with no
    console attached is a normal configuration, which is exactly how the cage-side
    kiosk runs."""
    link = Absent()

    link.publish(_telemetry())

    assert link.drain() == []


def test_simulated_keeps_what_was_published_and_returns_queued_commands():
    link = Simulated()
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))

    link.publish(_telemetry())

    assert len(link.published) == 1
    assert link.drain() == [SetParameter(name="fix_hold", value=0.4, by="jake")]
    assert link.drain() == [], "a command is delivered once, not every boundary"


# ---------------------------------------------------------------------------
# The wire: encode/decode, and both ends over a real socket
# ---------------------------------------------------------------------------


def test_telemetry_survives_the_wire_unchanged():
    """A golden round-trip, which ADR-0003 requires of every message schema
    ("schema-versioned messages ... version field from day one"). A field that
    silently changes type on the wire is a console rendering something other than
    what the session meant."""
    original = _telemetry(fluid_today_ml=None, shortfall_ml=None)

    restored = decode(encode(original))

    assert restored == original
    assert restored.fluid_today_ml is None, "None must not become 0.0 on the wire"


def _drain_until(link, *, tries=50, pause=0.01):
    """Call `link.drain()` repeatedly until it returns a command or `link.refused`
    has *grown* since this call started, or give up after `tries * pause` seconds
    (0.5 s by default) and return the empty list `drain()` last gave.

    **Fix round 1, judgment call 2.** The original name for this gap -- "the REQ/REP
    race" -- was a misnomer the reviewer corrected by measuring it directly, in this
    session's own scratchpad, on this machine -- **not committed under
    `docs/measurements/`, and not a claim about this system's own latency, jitter or
    throughput** (CLAUDE.md; the same disclaimer `link.py`'s `ZmqConsole` docstring
    carries for its settle delay, which this note previously lacked -- the two were
    inconsistent within this one file, and an unmarked number beside a marked one
    reads as the true one). With a zero-delay `console.send()` immediately followed
    by `link.drain()`, the first `drain()` missed the command on every one of 40
    trials, but *zero* were actually lost -- a later `drain()` always got it. There
    is no race and nothing is lost: ZeroMQ's I/O runs on a background thread that a
    zero-timeout `poll()` called in the very next Python statement gives no chance to
    run first, so the command simply is not visible *yet*. The original fix was a
    fixed `time.sleep(0.02)`, the same probe measured clean at 0/2000 -- but a fixed
    sleep tuned on one machine is exactly the kind of assumption that flakes on a
    slower or more loaded one. Retrying is bounded (never longer than `tries *
    pause`) but adaptive: it returns the instant something is visible rather than
    gambling on one wait.

    **`refused` is checked by growth, not by truthiness -- found by this helper's
    own first version being flaky.** `link.refused` is cumulative, like
    `Session.refusals` (never cleared at a boundary), so once one malformed packet
    has been refused, `if link.refused:` is true forever -- a version that checked
    it that way exited on the very first, empty `drain()` of every *later* call in
    the same test, before a real command had any time to arrive.
    """
    refused_before = len(link.refused)
    for _ in range(tries):
        commands = link.drain()
        if commands or len(link.refused) > refused_before:
            return commands
        time.sleep(pause)
    return []


def test_a_console_and_a_session_talk_over_a_real_socket(zmq_cleanup):
    """Over loopback rather than a mock, for the reason `tests/test_eye.py` uses a
    real socket: a protocol proven against a mock is a proof about the mock.

    Uses `_drain_until` rather than a fixed sleep between `console.send()` and
    `link.drain()` -- see that helper's docstring for the full story (fix round 1),
    including why its numbers are marked rather than stated as fact. An earlier
    version of this test's docstring also claimed its fixed sleep was *why*
    `link.publish`/`console.receive` below needed no settle delay of their own; the
    reviewer measured that claim false (with `ZmqConsole`'s PUB/SUB settle forced to
    `0`, the old 20 ms gap already gave 0/40 telemetry misses on its own -- same
    scratchpad probe as `_drain_until`'s, same disclaimer: not committed under
    `docs/measurements/`, not a claim about this system).
    `test_the_system_still_works_with_no_settle_delay` below proves the zero-settle
    case directly instead of leaving an unmeasured claim in a docstring comment.
    """
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
    commands = _drain_until(link)
    link.publish(_telemetry())

    assert commands == [SetParameter(name="fix_hold", value=0.4, by="jake")]
    assert console.receive().session_id == _telemetry().session_id


def test_a_console_can_send_a_sequence_of_commands(zmq_cleanup):
    """Fix round 1, **CRITICAL 1**, measured: a REQ socket refuses a second `send()`
    before the first send's reply is read (`zmq.error.ZMQError: Operation cannot be
    accomplished in current state`), and `SetParameter` then `Stop` -- an operator
    adjusting a parameter and then ending the session -- is the ordinary sequence
    S9a §8 is built on. The original real-socket test above sends exactly one
    command and so never exercised this; this is the test that sends two.

    `send()` now reads the *previous* send's reply lazily, on the next `send()`,
    rather than never (see its docstring) -- proven here by the fact that the second
    `send()` does not raise.
    """
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
    first = _drain_until(link)

    console.send(Stop(by="jake"))
    second = _drain_until(link)

    assert first == [SetParameter(name="fix_hold", value=0.4, by="jake")]
    assert second == [Stop(by="jake")]


def test_an_undecodable_command_is_refused_not_raised(zmq_cleanup):
    """Fix round 1, **CRITICAL 2**, measured with `{"kind": "pause"}`: `drain()` used
    to decode a packet before replying to it, so an undecodable packet's exception
    propagated out of `drain` and out of `taskd.py`'s trial loop -- one garbage
    packet, or one console built against a newer schema version (S9a §9 versions the
    wire for exactly this reason, not hypothetically), ended a session with an
    animal in the chair. Worse: because the REP socket was left owing a reply, the
    *next* call's poll/recv against a perfectly valid command failed too -- one bad
    packet took the whole channel down, not just itself.

    Writes the malformed payload directly on `console._req`, bypassing
    `console.send()` (which only ever offers a real `Command`) -- this simulates a
    corrupted packet or a mismatched console build, neither of which goes through
    this codebase's own encoder. Sets `console._awaiting_reply = True` to match: the
    raw send leaves a reply outstanding on this socket exactly as a real
    `console.send()` would, and the console wrapper's own bookkeeping (fix round 1,
    CRITICAL 1) needs to agree with reality or the *next* `console.send()` below
    would try to send without first reading it.
    """
    import msgpack

    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    console._req.send(msgpack.packb({"kind": "pause"}, use_bin_type=True))
    console._awaiting_reply = True

    commands = _drain_until(link)

    assert commands == [], "nothing decodable arrived, so nothing is returned"
    assert len(link.refused) == 1
    assert "pause" in link.refused[0].why

    # The other half of CRITICAL 2: the channel must still work afterwards.
    console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
    commands = _drain_until(link)
    assert commands == [SetParameter(name="fix_hold", value=0.4, by="jake")]


def test_publish_sends_with_dontwait_and_swallows_again(zmq_cleanup):
    """S9a §9's one hard requirement on `publish`: it must never block. **Fix round
    1, IMPORTANT**: nothing previously tested that `flags=zmq.DONTWAIT` is actually
    passed -- deleting it would not have failed a single test. Structural, per
    CLAUDE.md ("no timing claim without a measurement"), rather than a wall-clock
    attempt to fill a PUB queue: the reviewer measured that a real PUB socket does
    not raise `zmq.Again` under load in the first place, it drops the message
    instead, so `publish`'s `except zmq.Again` is correct, deliberate defensive code
    for a documented possibility this build's sockets do not appear to reach --
    **not dead code**, which is exactly what a wall-clock test finding no reachable
    case would wrongly suggest to a future reader.
    """
    import zmq

    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))

    calls = []

    def fake_send(data, flags=0):
        calls.append(flags)
        raise zmq.Again("simulated full queue")

    link._pub.send = fake_send

    link.publish(_telemetry())  # must not raise

    assert calls == [zmq.DONTWAIT]


def test_the_system_still_works_with_no_settle_delay(zmq_cleanup):
    """Fix round 1, judgment call 1: `ZmqConsole.__init__`'s default 50 ms settle
    delay reduces one real but non-critical gap (see the class docstring) -- it is
    never a correctness requirement, because retrying (`_drain_until`, and the same
    idea applied to `receive` below) is what actually makes delivery reliable, not a
    sleep. Proven by setting `settle_s=0` directly rather than trusting the class
    docstring's measurements at the nonzero default to also describe the zero case.

    Uses `with` for both ends -- exercising `__enter__`/`__exit__` (fix round 1,
    judgment call 3) rather than only the explicit `close()` every other test here
    uses -- and checks `.closed` after both blocks exit, not only the functional
    behaviour inside them. The mutation harness found this necessary: `__enter__`
    returning something other than `self` breaks attribute access inside the block
    and so is already caught, but a neutered `__exit__` that skips `self.close()`
    entirely leaves both blocks looking identical from the inside -- only checking
    afterwards catches it. Also registers both ends with `zmq_cleanup` (fix round 2)
    as a backup: this test's whole point is exercising `__exit__`, so its own
    cleanup must not be the only thing standing between a broken `__exit__` and an
    abandoned `Context`.
    """
    with zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")) as link:
        with zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0)) as console:
            console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
            commands = _drain_until(link)
            link.publish(_telemetry())

            assert commands == [SetParameter(name="fix_hold", value=0.4, by="jake")]
            assert console.receive().session_id == _telemetry().session_id
        assert console._sub.closed and console._req.closed, "__exit__ must close the console"
    assert link._pub.closed and link._rep.closed, "__exit__ must close the link"


def test_close_releases_both_sockets(zmq_cleanup):
    """Found by the mutation harness (`tools/mutate.py --all wl_expcontroller/link.py`
    reported `close` surviving), the same way `test_record.py` found `close`
    surviving there. The real-socket test above calls `close()` in a `finally`
    purely for hygiene -- so a full suite run does not accumulate open sockets and
    ports across hundreds of tests -- without ever checking that anything closed;
    gutting `close()`'s body would not have failed a single test before this one.
    Also registers both ends with `zmq_cleanup` (fix round 2): this test's whole
    point is exercising `close()`, so its own explicit calls below must not be the
    only thing standing between a broken `close()` and an abandoned `Context` --
    `zmq_cleanup`'s teardown does not depend on `close()` working."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))
    assert not link._pub.closed and not link._rep.closed
    assert not console._sub.closed and not console._req.closed

    link.close()
    console.close()

    assert link._pub.closed and link._rep.closed
    assert console._sub.closed and console._req.closed
