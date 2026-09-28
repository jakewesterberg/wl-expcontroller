"""The telemetry message a session publishes to its consoles.

S9a §9, "The telemetry contract": every number on the console comes from the object
the record is written from, never computed beside it. These tests exist to catch the
one way that rule breaks silently -- a field that quietly started summing reward
commands instead of reading `welfare.session_total()` would still look like a
telemetry message and would still pass every other test in this suite.
"""

from __future__ import annotations

import gc
import threading
import time
import weakref
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from wl_expcontroller.bounds import Bounds, Ceiling, Floor
from wl_expcontroller.link import (
    REFUSAL_HISTORY,
    Absent,
    CommandRefused,
    FrameError,
    ParamRow,
    Refused,
    RemoteBindRefused,
    SCHEMA,
    Simulated,
    SetParameter,
    Staged,
    Stop,
    TEXT_LIMIT,
    Telemetry,
    ZmqConsole,
    ZmqLink,
    _decode_command,
    _encode_command,
    decode,
    encode,
)
from wl_expcontroller.scheduler import Block, Condition, Scheduler
from wl_expcontroller.simulate import Tally
from wl_expcontroller.welfare import Deployment, Simulated as Pump, Welfare


def _bounds(daily_fluid: float = 250.0) -> Bounds:
    return Bounds(
        subject="A",
        ceilings={"out_of_cage": Ceiling(value=43_200.0, maximum=43_200.0, unit="s")},
        minima={"daily_fluid": Floor(value=daily_fluid, unit="mL")},
    )


def _session_with(
    delivered_ml: float,
    already_today: float | None,
    deployment: Deployment = Deployment.RIG_FIXED,
):
    """A stand-in for `Session`, carrying exactly what `Telemetry.of` reads from it.

    Not a real `Session`: constructing one loads a task file and an allocation from
    disk, which these tests have no reason to do. `Telemetry.of`'s parameters are
    untyped precisely so any object with the right shape counts as a session (see
    `link.py`). `.staged` and `.refusals` are supplied directly as plain tuples --
    stand-ins for the real `Session.staged` property and `Session.refusals` field,
    so this fixture does not need to construct either the live-parameter or the
    console-command machinery to satisfy `Telemetry.of`'s shape.

    **`.link` is a real `Absent()`, not omitted.** It used to be absent here and
    `Telemetry.of` reached it through `getattr(session, "link", None)` -- a default
    that existed only to keep this stand-in working, and that would also have
    swallowed a `Session` genuinely built without a link, and (through the second
    `getattr` beside it) a rename of `ZmqLink.refused`. Both defaults are gone; a
    session with no link is an `AttributeError` now, which is why this line is here
    rather than in `Telemetry.of`. `Absent` is what `taskd.Session` itself defaults
    to, so this is the real object and not a further stand-in.

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
        deployment=deployment,
        commanded=0.1,
        delivered=delivered_ml,
    )
    # The mark, because `Telemetry.of` asks for `out_of_cage_seconds` and an
    # unmarked rig session refuses rather than answering zero (PI, 2026-09-19). A
    # stand-in that skipped it would make every telemetry test here a test of that
    # refusal instead.
    welfare.left_cage(at=0.0, wall_now=0.0)
    return SimpleNamespace(
        spec=SimpleNamespace(
            session_id="2027-01-14_01",
            subject="A",
            # Read by `Telemetry.of` since 2026-09-20: two of the three kinds
            # answer `None` for chair time and a console has to say which.
            deployment=deployment,
            task="tasks/fixation_detection.py",
            allocation="tasks/allocation.py",
            bounds_config="subjects/A/bounds.py",
        ),
        welfare=welfare,
        stopped_because="",
        staged=(),
        refusals=(),
        # Stand-ins for `Session.parameters` and `Session.recent_outcomes` (P4d-2b
        # b1): the shapes `Telemetry.of` reads, as `staged` and `refusals` are.
        parameters=(
            ("fix_hold", "s", 0.1, 1.0, 0.3, False),
            ("reward_correct", "mL", 0.0, 0.4, 0.15, True),
        ),
        recent_outcomes=("correct", "hang"),
        # Read as a plain attribute by `Telemetry.of`, exactly like `link.refused`
        # and for the same reason -- `Session.refusals` is capped at
        # `REFUSAL_HISTORY` since 2026-09-19, and its discards have to reach the
        # frame or a cap reads as a quiet session.
        refusals_dropped=0,
        link=Absent(),
        phase="running",
        stop_kind=None,
        # The one clock `Telemetry.of` reads (P4d-2a spec §10). There is no `now`
        # here on purpose: the frame clock is for timing trials, and a
        # `Telemetry.of` that handed it to `welfare` would fail on this stand-in.
        wall_now=lambda: 0.0,
        duration_warning=lambda wall_now: welfare.approaching_limit(wall_now),
        # The in-session clock (P4d-2a spec §10 item 3), read as plain attributes
        # -- like `wall_now` above, never through `welfare`, since it bounds
        # nothing and no `welfare` method takes either instant. Opened at the same
        # instant `left_cage` was given above, so `in_session_seconds` is a real
        # number rather than the `None`-before-`open()` case on this stand-in.
        opened_wall_at=0.0,
        ended_wall_at=None,
    )


def _scheduler() -> Scheduler:
    block = Block(name="session", conditions=[Condition("only", {}, target=1)])
    return Scheduler(blocks=[block], seed=0)


def test_a_frame_reads_the_wall_once_and_is_one_instant():
    """**Task 7 fix round 1, Minor 2.** `Telemetry.of` used to read the wall for the
    two durations and let `Session.duration_warning` read it again, so a frame's
    warning and the clocks beside it could describe two moments. The wall here moves
    a second on every read: one read, and the warning is given that same instant."""
    session = _session_with(delivered_ml=1.25, already_today=3.0)
    reads: list = []

    def wall_now() -> float:
        reads.append(None)
        return float(len(reads))

    warned_at: list = []
    session.wall_now = wall_now
    session.duration_warning = lambda at: warned_at.append(at)

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert len(reads) == 1, "one frame, one reading of the wall"
    assert warned_at == [1.0]
    assert telemetry.out_of_cage_seconds == 1.0


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


def test_a_cage_side_sessions_absent_duration_clock_survives_the_wire_as_none():
    """`out_of_cage_seconds` is `None` for a session that declared the animal is at
    home (`welfare.Deployment`, PI 2026-09-19), and a `0.0` arriving in its place
    would render as a clock that had not started rather than one that does not
    exist. msgpack has a native nil, so this is a claim about `encode`/`decode`
    keeping it and not about the format being able to."""
    original = _telemetry(out_of_cage_seconds=None)

    restored = decode(encode(original))

    assert restored.out_of_cage_seconds is None


def test_a_chaired_sessions_absent_chair_clock_survives_the_wire_as_none():
    """**The same rule on the restraint clock** (PI, 2026-09-20). `chair_seconds` is
    `None` for the two deployment kinds that take no head-fixation marks, and a
    `0.00` arriving in its place would tell an operator a restrained animal had been
    restrained for no time at all.

    Assembled from a real chaired session rather than by overriding the field, so
    this is a claim about `Telemetry.of` reading `welfare` as well as about the wire.
    """
    session = _session_with(
        delivered_ml=1.0, already_today=None, deployment=Deployment.RIG_CHAIRED
    )
    original = Telemetry.of(session, Tally(), _scheduler(), index=0)

    restored = decode(encode(original))

    assert original.chair_seconds is None, "welfare reports absent, not 0.00"
    assert restored.chair_seconds is None
    assert restored.deployment == "rig_chaired"


def test_telemetry_carries_the_deployment_so_a_console_can_say_which_absence():
    """Two of the three kinds answer `None` for chair time, for different reasons: a
    cage-side animal is never restrained and a chaired one is restrained and
    unmarked. A console that derived the kind from which fields were `None` would be
    computing, which `cli.render` promises not to do -- so the declaration is on the
    wire."""
    original = _telemetry(deployment="rig_chaired")

    restored = decode(encode(original))

    assert restored.deployment == "rig_chaired"


def test_telemetry_carries_the_warning_as_the_limit_approaches():
    """`welfare.approaching_limit` read, not recomputed -- the console's whole
    reason for showing it is that it is the same sentence the session would use."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.welfare.warn_within = 43_200.0

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.duration_warning == session.welfare.approaching_limit(0.0)
    assert telemetry.duration_warning is not None, "the threshold spans the ceiling"


def test_staged_and_refused_rows_come_back_as_objects_not_raw_dicts():
    """The round-trip above ran on a frame whose `staged` and `refusals` were both
    **empty**, so for as long as it was the only one, `decode` was free to hand back
    whatever msgpack gave it for those two fields and stay green.

    Measured, final review: hand-mutating `decode`'s `refusals=` line to
    `tuple(data["refusals"])` -- dropping the `Refused(**r)` rebuild entirely --
    left the suite at `421 passed, 0 failed`. The same mutation on the `staged=`
    line one row up *did* fail a test, because `tests/test_cli.py`'s `--link`
    end-to-end reads `{s.name for s in frame.staged}` off a frame that really
    crossed a socket. Nothing anywhere did the equivalent for `refusals`, so the
    first refusal an operator caused over a real socket would have reached
    `cli.render`'s `refusal.name` as a plain dict.

    Both fields are non-empty here, and both are checked by attribute rather than
    by equality alone -- `restored == original` on its own is a weaker claim than it
    looks, since it would still hold for anything that compared equal to the
    original tuple."""
    original = _telemetry(
        staged=(Staged(name="fix_hold", was=0.3, now=0.4, by="jake", bounded=False),),
        refusals=(
            Refused(name="reward_correct", by="jake", why="may not exceed 0.4 mL"),
            Refused(name="fx_hold", by="sam", why="not a parameter this task declares"),
        ),
    )

    restored = decode(encode(original))

    assert restored == original
    assert [type(r) for r in restored.refusals] == [Refused, Refused]
    assert [r.name for r in restored.refusals] == ["reward_correct", "fx_hold"]
    assert [r.by for r in restored.refusals] == ["jake", "sam"]
    assert restored.refusals[0].why == "may not exceed 0.4 mL"
    assert [type(s) for s in restored.staged] == [Staged]
    assert restored.staged[0].name == "fix_hold"
    assert restored.staged[0].bounded is False


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


def test_a_link_refuses_to_bind_where_other_hosts_can_reach_it():
    """S9a §7 justifies `taskd` trusting a command's `by` field outright -- "because
    they are the same machine and the console *is* the authenticator" -- and nothing
    enforced the premise. `ZmqLink` bound whatever string it was handed, so
    `--link tcp://0.0.0.0:5571,...` was accepted in silence and any host on the lab
    network could then move `reward_correct` or issue `Stop` under any `--as` name it
    invented.

    Every form below is a bind other hosts can reach, and a refusal is cheap: the
    operator passes one more flag. The reverse mistake is an open port nobody chose,
    so anything this cannot parse is refused too rather than guessed at. No cleanup
    fixture, because the refusal happens before a `Context` exists."""
    for endpoint in (
        "tcp://0.0.0.0:5571",
        "tcp://192.168.1.50:5571",
        "tcp://*:5571",
        "tcp://eth0:5571",
        "tcp://[::]:5571",
        "udp://127.0.0.1:5571",
    ):
        try:
            ZmqLink(pub_endpoint=endpoint, rep_endpoint="tcp://127.0.0.1:0")
        except RemoteBindRefused as refused:
            assert "P4d-3" in str(refused), "the refusal must name what is waited on"
        else:
            raise AssertionError(f"{endpoint} was bound without being asked for")

    # The REP endpoint is checked too, not only the first argument -- REP is the one
    # that carries commands, so a check that only covered PUB would miss the half
    # that matters most.
    try:
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://0.0.0.0:5571")
    except RemoteBindRefused:
        pass
    else:
        raise AssertionError("a remote REP endpoint was bound without being asked for")


def test_which_endpoints_count_as_leaving_this_machine():
    """The classification on its own, with no socket involved, because some of the
    cases cannot be bound on every machine and binding is not what is being checked.

    `127.0.0.2` is the reason this is a separate test: it is inside 127.0.0.0/8 and
    must classify as local, and a prefix match on the literal `127.0.0.1` would have
    called it remote. It is *also* not assignable on a stock macOS loopback, while
    Linux binds it, so binding it here would test something different on each host.
    Checking the predicate keeps the case on every host. What a bind that fails
    partway through `ZmqLink.__init__` owes is
    `test_a_link_that_cannot_bind_does_not_abandon_its_context`'s subject."""
    from wl_expcontroller.link import _binds_beyond_this_machine as beyond

    for local in (
        "tcp://127.0.0.1:5571",
        "tcp://127.0.0.2:5571",
        "tcp://127.53.19.4:0",
        "tcp://localhost:5571",
        "tcp://[::1]:5571",
        "inproc://console",
        "ipc:///tmp/wlx-console",
    ):
        assert not beyond(local), f"{local} is local and was called remote"

    for remote in (
        "tcp://0.0.0.0:5571",
        "tcp://192.168.1.50:5571",
        "tcp://10.0.0.1:5571",
        "tcp://*:5571",
        "tcp://eth0:5571",
        "tcp://[::]:5571",
        "udp://127.0.0.1:5571",
        "nonsense",
    ):
        assert beyond(remote), f"{remote} would be reachable and was called local"


def test_a_loopback_link_binds_and_an_explicit_remote_one_is_allowed(zmq_cleanup):
    """The other side of the refusal, on real sockets. Loopback still binds with
    nothing extra passed -- a guard that also blocked the ordinary case would be
    worse than the hole it closes -- and `allow_remote=True` is how somebody says a
    non-loopback bind was meant. Port 0 throughout, so neither can collide with
    anything already listening."""
    for endpoint in ("tcp://127.0.0.1:0", "tcp://localhost:0"):
        zmq_cleanup(ZmqLink(pub_endpoint=endpoint, rep_endpoint="tcp://127.0.0.1:0"))

    # Bound on purpose, and it works: the flag is about deliberateness, not about
    # disabling the transport.
    remote = zmq_cleanup(
        ZmqLink(
            pub_endpoint="tcp://0.0.0.0:0",
            rep_endpoint="tcp://0.0.0.0:0",
            allow_remote=True,
        )
    )

    assert remote.pub_endpoint.startswith("tcp://0.0.0.0:")


def _half_built(raised, cls):
    """The `cls` whose constructor raised, read from that constructor's own frame in
    the traceback `raised` holds. That frame keeps it alive for as long as the
    exception is held, which is the situation the test below is about."""
    tb = raised.tb
    while tb is not None:
        candidate = tb.tb_frame.f_locals.get("self")
        if isinstance(candidate, cls):
            return candidate
        tb = tb.tb_next
    raise AssertionError(f"no {cls.__name__} constructor frame in the traceback")


def test_a_link_that_cannot_bind_does_not_abandon_its_context(zmq_cleanup):
    """Found by triggering it: `tcp://127.0.0.2:0` is inside the loopback block, so
    the guard above lets it through, and on a stock macOS loopback it is not an
    assignable address. The `ZMQError` then raised out of `__init__` **after** the
    `Context` and the PUB socket existed and **before** any caller had a handle to
    call `close()` on. Before `__init__` had its `except`, the context was abandoned
    mid-construction, left to whatever freed the object, and the old finalizer could
    deadlock there (`link._release`'s docstring; fixed by Ruling 18).

    **What the `except` still owes is promptness**, and that is what this checks.
    Without it, the half-built link lives as long as its exception does, because the
    constructor's frame in the traceback holds it. Its context stays open and its PUB
    port stays bound for as long as a caller that logs the error, a debugger, or
    `pytest.raises` here holds on to it. The operator's retry, with the REP endpoint
    corrected and the same PUB endpoint, then fails on a port that only the failed
    attempt's exception is keeping bound.

    A REP port already in use is the failure, not `127.0.0.2`: Linux binds that
    address, so it failed only on some hosts, and the test returned early on the
    others. A port in use fails everywhere, and it is the common operator mistake."""
    import zmq

    taken = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))

    with pytest.raises(zmq.ZMQError) as raised:
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint=taken.rep_endpoint)
    # Held from here to the end of the test, as a caller holding the error would.
    half_built = zmq_cleanup(_half_built(raised, ZmqLink))
    # The premise: PUB bound a port, and it was REP's bind that failed.
    assert half_built.pub_endpoint.startswith("tcp://127.0.0.1:")
    assert not hasattr(half_built, "rep_endpoint")

    try:
        retry = zmq_cleanup(
            ZmqLink(pub_endpoint=half_built.pub_endpoint, rep_endpoint="tcp://127.0.0.1:0")
        )
    except zmq.ZMQError as exc:
        raise AssertionError(
            f"the failed constructor still holds its PUB port {half_built.pub_endpoint}: {exc}"
        ) from exc
    assert retry.pub_endpoint == half_built.pub_endpoint
    assert half_built._ctx.closed, "the failed constructor left its context open"


def test_a_flood_of_undecodable_packets_cannot_grow_the_link_without_bound(zmq_cleanup):
    """The test above proves one bad packet is recorded rather than raised. This one
    proves the *thousandth* is not, because `link.refused` was cumulative and
    uncapped and the party deciding its length is the peer, not this end.

    The realistic source is the one `drain()`'s own docstring names: a console built
    against a bumped `SCHEMA` fails to decode nothing -- it fails to *encode*
    something this end understands -- and keeps trying, every packet, forever. Each
    one appended a `Refused`, and `Telemetry.of` re-encoded the whole accumulation
    into every PUB frame at every trial boundary, so both the per-boundary work and
    the frame grew linearly with how long the broken console stayed connected.

    `REFUSAL_HISTORY + 5` packets here rather than a thousand: the property is the
    trim, and the trim either holds at the boundary or does not. What fell off is in
    `refused_dropped`, which is what keeps this a cap rather than a quieter version
    of the silent drop the docstring argues against."""
    import msgpack

    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    sent = REFUSAL_HISTORY + 5
    for n in range(sent):
        console._req.send(msgpack.packb({"kind": f"from_a_newer_console_{n}"}, use_bin_type=True))
        console._awaiting_reply = True
        _drain_until(link)
        console._req.recv()
        console._awaiting_reply = False

    assert len(link.refused) == REFUSAL_HISTORY, "the refusal list is unbounded again"
    assert link.refused_dropped == sent - REFUSAL_HISTORY
    # The newest are the ones kept: an operator looking at a console wants what just
    # happened, not what happened first.
    assert f"from_a_newer_console_{sent - 1}" in link.refused[-1].why
    assert f"from_a_newer_console_{sent - REFUSAL_HISTORY}" in link.refused[0].why


def test_telemetry_caps_the_refusal_feed_and_counts_what_it_dropped():
    """The same bound one hop out. `Telemetry.of` concatenates `session.refusals`
    with `session.link.refused` and publishes the result, so capping only the link
    would still let an operator's own refusals -- or the sum of the two -- grow a
    frame without limit.

    `refusals_dropped` adds both losses: what `ZmqLink` already trimmed off its own
    list, and what this cap drops from the concatenation. They cannot double-count,
    because an entry the link discarded never reaches the concatenation at all."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.refusals = tuple(
        (f"param_{n}", "jake", "not a parameter this task declares")
        for n in range(REFUSAL_HISTORY + 3)
    )
    session.link = Simulated(
        refused=[Refused(name="<transport>", by="<unknown>", why="newest")],
        refused_dropped=7,
    )

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert len(telemetry.refusals) == REFUSAL_HISTORY
    # The session's 53 plus the link's 1 is 54, so 4 fall off this end -- plus the 7
    # the link had already discarded before any of this reached `Telemetry.of`.
    assert telemetry.refusals_dropped == 4 + 7
    assert telemetry.refusals[-1].why == "newest", "the newest must survive the cap"
    assert telemetry.refusals[0].name == "param_4", "the oldest are the ones dropped"


def test_telemetry_refuses_a_session_with_no_link_rather_than_publishing_none():
    """Final-review m5. `Telemetry.of` used to read the link as
    `getattr(getattr(session, "link", None), "refused", ())` -- two defaults, one of
    which existed only to let this file's `SimpleNamespace` stand-in omit `.link`.

    Both hid the same failure. A `Session` genuinely built without a link, or a
    rename of `ZmqLink.refused`, would have made every transport refusal disappear
    from telemetry with nothing raising and the suite still green -- which is the
    shape `dio.Absent`, `welfare.Absent` and `run.Unwired` all exist to refuse
    rather than paper over. `Absent` and `Simulated` now answer `refused` with
    empties of their own, so the read has no reason to be defensive."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    del session.link

    try:
        Telemetry.of(session, Tally(), _scheduler(), index=0)
    except AttributeError:
        pass
    else:
        raise AssertionError("a session with no link published telemetry anyway")


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


def test_close_terminates_the_context_and_a_second_close_is_harmless(zmq_cleanup):
    """`close()` now runs the same release the collector would (`link._release`,
    Ruling 18), so this pins what it owes on the ordinary path: the context is
    terminated, not only the sockets closed, and calling it again does nothing and
    raises nothing -- `with` plus an explicit `close()` inside it is an ordinary way
    to call it twice."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0))

    link.close()
    console.close()

    assert link._ctx.closed, "close() left the link's context unterminated"
    assert console._ctx.closed, "close() left the console's context unterminated"

    link.close()
    console.close()

    assert link._pub.closed and link._rep.closed and link._ctx.closed
    assert console._sub.closed and console._req.closed and console._ctx.closed


@contextmanager
def _interrupted_once(sock):
    """Inside this block, `sock.close` raises `KeyboardInterrupt` once, before it
    closes anything, and is the real `close` from then on. That is a Ctrl-C landing
    between `_release`'s two `sock.close` calls.

    **The block, not the test, owns the stand-in.** If nothing called it -- a
    neutered `close()` or `_release` -- it is removed on the way out. Left in place,
    `zmq_cleanup`'s teardown would call it through `Context.destroy`, and a
    `KeyboardInterrupt` there ends the whole pytest session, not one test: the
    mutation harness saw `close` "caught" by a suite that stopped at 425 of 1092."""

    def close(*args, **kwargs):
        del sock.close  # the next call reaches the real method
        raise KeyboardInterrupt("a Ctrl-C between the two sock.close calls")

    sock.close = close
    try:
        yield
    finally:
        if "close" in vars(sock):
            del sock.close


def test_a_close_interrupted_partway_leaves_the_net_armed_and_a_second_close_finishes(
    zmq_cleanup,
):
    """Ruling 19 (2026-09-27), from the review of Ruling 18. `close()` used to be
    `self._finalizer()`, and `weakref.finalize` removes its registry entry *before*
    it calls `_release`. So a release interrupted partway -- a Ctrl-C between the two
    `sock.close` calls, during `wlx run`'s `with` exit -- left no net at all: the
    finalizer was dead, a second `close()` did nothing, and the context was never
    terminated. `close()` now runs `_release` itself and detaches the finalizer only
    once it has returned, so the net stays armed and a second `close()` finishes the
    release. Both ends, because each has its own `close()`."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0))

    for end, second in ((link, link._rep), (console, console._req)):
        name = type(end).__name__

        with _interrupted_once(second), pytest.raises(KeyboardInterrupt):
            end.close()

        assert not end._ctx.closed, f"the {name}'s release was not interrupted"
        assert end._finalizer.alive, f"an interrupted close() disarmed the {name}'s net"

        end.close()

        assert second.closed, f"a second close() left the {name}'s socket open"
        assert end._ctx.closed, f"a second close() left the {name}'s context unterminated"
        assert not end._finalizer.alive, f"a completed close() left the {name}'s net armed"


@contextmanager
def _collector_paused():
    """No automatic collection runs inside this block, so the only one that can free
    what a test drops is the one the test starts itself, on its own thread. Without
    this, an allocation after the drop could trigger a collection on the test's own
    thread -- and under the deadlock these tests exist for, that would hang the suite
    instead of failing a test."""
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


def _collected_within(seconds: float) -> bool:
    """Run one full cyclic collection on a daemon thread, and say whether it returned
    within `seconds`.

    **A daemon thread and a bounded join, so the deadlock is a failure and not a
    hang.** Before Ruling 18 this collection never returned: `pyzmq`'s `Context._term`
    waits in `zmq_ctx_destroy` with the GIL released, so this thread could sit there
    while the join below timed out and the test failed. A stuck thread keeps the
    collector marked busy for the rest of the process, so a later `gc.collect()`
    returns at once having collected nothing; the tests after a failure here fail
    too, loudly, rather than hanging."""
    collector = threading.Thread(target=gc.collect, name="wlx-test-collector", daemon=True)
    collector.start()
    collector.join(timeout=seconds)
    return not collector.is_alive()


# **None of the three tests below registers its cyclic object with `zmq_cleanup`, on
# purpose.** That fixture's teardown calls `destroy` on the context. If the collector
# thread is stuck in `term()` on that context, which is the failure these tests
# exist to catch, a second `term()` from the teardown blocks too, and a bounded failure
# becomes a hung suite. When the tests pass, the collector has already terminated the
# context. `tests/_zmq_release.py`'s autouse fixture, which holds every object a test
# builds, is imported only by `test_serve.py` and `test_cli.py`, so it holds nothing
# here. If it ever did, the object would never become garbage, and these tests would
# fail on `ctx.closed` instead of exercising the collector. They could not pass by it.
#
# **What each test holds, and why it cannot change the outcome.** It holds the
# context strongly, and the sockets only through `weakref`s. A context refers to its
# sockets only through its own `WeakSet`, so holding it keeps no socket reachable.
# A strong reference to a socket would keep it in that `WeakSet`, and the old
# `destroy` would then have closed it, so that kind of reference would hide the bug.
# `ctx.closed` stands for the sockets: libzmq's `zmq_ctx_term` returns only once every
# socket in the context is closed, and pyzmq sets `closed` only after it returns. The
# `weakref`s then show that the net let go of the sockets once it ran, and did not
# keep them alive.


def test_an_unclosed_link_in_a_reference_cycle_is_released_by_the_collector():
    """**Ruling 18.** `wlx run --link`'s `ZmqLink` sits in a reference cycle,
    `Session -> Rig -> Session.wall_now -> Session`. If `close()` never ran, only the
    cyclic collector frees it, and the finalizer is the only thing that releases its
    sockets and context. That finalizer used to be `ctx.destroy`. It found no sockets
    in the context's `WeakSet`, because the collector had already cleared them, and
    `term()` then waited forever for sockets that were still open, on the collecting
    thread, which in `wlx run` is the trial process. Reproduced 2026-09-27, in a bare
    script and in this suite. The link here is put in a cycle of its own, which is the
    same situation without building a `Session`."""
    with _collector_paused():
        link = ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
        link._cycle = link
        ctx = link._ctx
        sockets = [weakref.ref(link._pub), weakref.ref(link._rep)]
        del link

        returned = _collected_within(10.0)

    assert returned, "collecting an unclosed ZmqLink in a reference cycle hung for 10 s"
    assert ctx.closed, "the collector freed the link without terminating its context"
    assert all(ref() is None for ref in sockets), "the finalizer kept the link's sockets alive"


def test_an_unclosed_console_in_a_reference_cycle_is_released_by_the_collector(zmq_cleanup):
    """The console side of the test above. The link it connects to is an ordinary
    one, registered with `zmq_cleanup`. Only the console is dropped in a cycle."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    with _collector_paused():
        console = ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0)
        console._cycle = console
        ctx = console._ctx
        sockets = [weakref.ref(console._sub), weakref.ref(console._req)]
        del console

        returned = _collected_within(10.0)

    assert returned, "collecting an unclosed ZmqConsole in a reference cycle hung for 10 s"
    assert ctx.closed, "the collector freed the console without terminating its context"
    assert all(ref() is None for ref in sockets), "the finalizer kept the console's sockets alive"


def test_a_console_that_failed_to_connect_is_released_by_the_collector_too():
    """A `ZmqConsole` whose `connect` raises is half-built: its context and its SUB
    socket exist, and the REQ socket does not. Nothing ever calls `close()` on it,
    because no caller ever had a handle. So the finalizer has to release exactly the
    sockets that got made, and from inside a cycle as well. The subclass plants the
    cycle before the constructor runs, and records the context and a `weakref` to
    the socket even though the constructor raises. That is the only way to reach an
    object whose construction failed."""
    import zmq

    planted: dict = {}

    class _Cyclic(ZmqConsole):
        def __init__(self, *args, **kwargs):
            self._cycle = self
            try:
                super().__init__(*args, **kwargs)
            finally:
                planted["ctx"] = self._ctx
                planted["sub"] = weakref.ref(self._sub)

    with _collector_paused():
        try:
            _Cyclic("tcp://a b:5571", "tcp://127.0.0.1:1", settle_s=0)
        except zmq.ZMQError:
            pass
        else:  # pragma: no cover -- libzmq accepted a host with a space in it
            raise AssertionError("connect accepted 'tcp://a b:5571'")

        returned = _collected_within(10.0)

    assert returned, "collecting a half-built ZmqConsole in a reference cycle hung for 10 s"
    assert planted["ctx"].closed, "the collector freed the console without terminating its context"
    assert planted["sub"]() is None, "the finalizer kept the console's SUB socket alive"


def test_the_phase_and_the_kind_of_stop_survive_the_wire():
    """Schema 6 (P4d-2a). A console built against 5 would render an awaiting-return
    frame's advancing clock as a running session, which is why the version moved."""
    original = _telemetry(phase="awaiting_return", stop_kind="limit")

    restored = decode(encode(original))

    assert restored == original
    assert restored.schema == SCHEMA


def test_a_running_sessions_stop_kind_is_none_on_the_wire_and_never_empty():
    restored = decode(encode(_telemetry()))

    assert restored.stop_kind is None
    assert restored.phase == "running"


def test_a_returned_command_is_refused_through_the_unknown_kind_path(zmq_cleanup):
    """P4d-2a spec §10, Task 8: `ReturnedToCage` and its `"returned"` wire kind are
    gone -- the PI ruled the wl-works ELN owns the return, not a console, so the
    browser will never send one and this file implements no such command any more.
    A packet still tagged `"returned"` -- an old console build, or a corrupted one --
    must be refused exactly like any other kind this file does not recognize, never
    decoded into a command. Same shape as
    `test_an_undecodable_command_is_refused_not_raised`: the raw send bypasses
    `console.send()` (which only ever offers a real `Command`), and the channel must
    still work afterwards."""
    import msgpack

    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    console._req.send(
        msgpack.packb(
            {"kind": "returned", "at": 1_700_000_123.5, "by": "jake", "confirmed": True},
            use_bin_type=True,
        )
    )
    console._awaiting_reply = True

    commands = _drain_until(link)

    assert commands == [], "a 'returned' packet must not build a command"
    assert len(link.refused) == 1
    assert "returned" in link.refused[0].why

    # The other half: the channel must still work afterwards.
    console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
    commands = _drain_until(link)
    assert commands == [SetParameter(name="fix_hold", value=0.4, by="jake")]


# ---------------------------------------------------------------------------
# Schema 7 (P4d-2b b1): what the browser console reads
# ---------------------------------------------------------------------------


def test_schema_7_reads_the_configuration_from_the_session():
    """Spec §3: which task, which allocation, which bounded config, and the parameter
    rows -- each from the object the record is written from."""
    session = _session_with(delivered_ml=1.0, already_today=None)

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.schema == SCHEMA == 7
    assert telemetry.task == "tasks/fixation_detection.py"
    assert telemetry.allocation == "tasks/allocation.py"
    assert telemetry.bounds_config == "subjects/A/bounds.py"
    assert telemetry.params == (
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
        ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
    )
    assert telemetry.recent_outcomes == ("correct", "hang")


def test_the_limits_are_the_ones_welfare_reads_them_against():
    """`floor_ml` is the day's floor and `out_of_cage_limit_s` the ceiling's *value*
    -- the number `welfare.must_stop` compares with -- never its maximum."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.welfare.bounds.ceilings["out_of_cage"] = Ceiling(
        value=3_600.0, maximum=43_200.0, unit="s"
    )

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.floor_ml == 250.0
    assert telemetry.out_of_cage_limit_s == 3_600.0


def test_a_cage_side_session_has_no_limit_to_publish():
    """`None`, never `0.0`: a cage-side session has no out-of-cage ceiling at all, and
    a zero would read as a limit already reached."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.welfare = Welfare(
        bounds=Bounds(
            subject="A",
            ceilings={},
            minima={"daily_fluid": Floor(value=250.0, unit="mL")},
        ),
        pump=Pump(),
        already_today=None,
        deployment=Deployment.CAGE_SIDE,
    )
    session.spec.deployment = Deployment.CAGE_SIDE
    session.duration_warning = lambda wall_now: None

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.out_of_cage_limit_s is None
    assert telemetry.out_of_cage_seconds is None


def test_the_last_reward_is_welfares_instant_and_none_before_the_first():
    session = _session_with(delivered_ml=1.0, already_today=None)
    assert Telemetry.of(session, Tally(), _scheduler(), index=0).last_reward_at is None

    session.welfare.last_delivery_wall_at = 1_700_000_123.0

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)
    assert telemetry.last_reward_at == 1_700_000_123.0


def test_a_frame_carries_the_one_instant_it_was_read_at():
    """Ledger Ruling 1 (2026-09-27): `wall_at` is the wall reading `Telemetry.of`
    already takes once per frame -- the instant the frame's durations and warning
    describe, on the session's anchored clock -- so a console ages the frame from it
    and never from a host clock of its own. Still one reading: the wall here moves a
    second on every read, as in `test_a_frame_reads_the_wall_once_and_is_one_instant`."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    reads: list = []

    def wall_now() -> float:
        reads.append(None)
        return 100.0 + len(reads)

    session.wall_now = wall_now

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert len(reads) == 1, "one frame, one reading of the wall"
    assert telemetry.wall_at == 101.0
    assert telemetry.out_of_cage_seconds == 101.0


def test_schema_7_survives_the_wire_with_its_absences_intact():
    """The golden round trip, with every new field populated and every new `None`
    present: a missing reward time, a cage-side limit, an unset parameter, and a
    categorical one whose value is a string."""
    original = _telemetry(
        params=(
            ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
            ParamRow("target_looks", "", None, None, None, False),
            ParamRow("shape", "", None, None, "penguin", False),
        ),
        recent_outcomes=("correct", "hang", "no_fixation"),
        last_reward_at=None,
        out_of_cage_limit_s=None,
    )

    restored = decode(encode(original))

    assert restored == original
    assert [type(p) for p in restored.params] == [ParamRow, ParamRow, ParamRow]
    assert restored.params[1].value is None
    assert restored.params[2].value == "penguin"
    assert restored.recent_outcomes == ("correct", "hang", "no_fixation")
    assert restored.last_reward_at is None
    assert restored.out_of_cage_limit_s is None


def test_a_console_can_be_given_a_shorter_receive_timeout(zmq_cleanup):
    """P4d-2b b1: `wlx serve`'s telemetry thread looks between receives at whether it
    should stop, so its wait is short. `wlx console` keeps the 5 s it always had."""
    import zmq

    link = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    short = zmq_cleanup(
        ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0, receive_timeout_s=0.05)
    )
    default = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0))

    assert short._sub.getsockopt(zmq.RCVTIMEO) == 50
    assert default._sub.getsockopt(zmq.RCVTIMEO) == 5000
    try:
        short.receive()
    except TimeoutError:
        pass
    else:
        raise AssertionError("a console received a frame nobody published")


def test_a_frame_error_with_no_message_names_only_the_exception_type():
    """Fix round 2, M-e: `f"{type(exc).__name__}: {exc}"` for an exception whose
    own `str()` is empty left a dangling `"FormatError: "` -- a trailing colon and
    space naming nothing, reading as truncated rather than as "no message".
    `0xc1` is msgpack's one reserved, never-used byte, and `msgpack.unpackb`
    raises `FormatError` on it with an empty message -- a real trigger, not a
    synthetic one, confirmed by hand before writing this test."""
    try:
        decode(b"\xc1")
    except FrameError as exc:
        assert str(exc) == (
            "a telemetry frame could not be decoded, so it is not shown: FormatError"
        )
    else:
        raise AssertionError("msgpack's one reserved byte did not raise FrameError")


# ---------------------------------------------------------------------------
# M8 (P4d-2a's review, closed in P4d-2b b2a): a setting's value is checked where
# the command is decoded
# ---------------------------------------------------------------------------


def _packed(**fields) -> bytes:
    import msgpack

    return msgpack.packb(fields, use_bin_type=True)


@pytest.mark.parametrize(
    "value",
    [True, False, None, [0.4], {"v": 0.4}, float("nan"), float("inf"), float("-inf")],
)
def test_a_setting_that_is_not_a_real_number_or_a_word_is_refused_where_it_is_decoded(
    value,
):
    """M8: `SetParameter.value` was a type hint nothing enforced, so a string reached
    `bounds._finite`, raised `TypeError`, and `run()`'s fault handler ended the whole
    session. A value is a finite real number that is not a `bool`, or a word for a
    categorical parameter; anything else is refused here, naming the parameter and
    the sender, so the refusal a console shows says whose write it was."""
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name="fix_hold", value=value, by="jake"))

    assert refused.value.name == "fix_hold"
    assert refused.value.by == "jake"
    assert "'fix_hold' was sent" in refused.value.why
    assert "the session runs on" in refused.value.why


def test_a_whole_number_decodes_as_a_float_and_a_word_as_itself():
    """A browser's JSON gives `1` for one and `0.5` for a half; both are numbers. A
    categorical choice travels as its word, and `Session.set` checks it against the
    task's `choices`."""
    whole = _decode_command(_packed(kind="set", name="fix_window", value=2, by="jake"))
    word = _decode_command(_packed(kind="set", name="shape", value="penguin", by="jake"))

    assert whole == SetParameter(name="fix_window", value=2.0, by="jake")
    assert type(whole.value) is float
    assert word == SetParameter(name="shape", value="penguin", by="jake")


@pytest.mark.parametrize("by", [None, "", "   ", 7])
def test_a_command_that_does_not_say_who_sent_it_is_refused(by):
    """S9a §6: every write records its actor. A packet with no usable `by` is refused
    by name rather than recorded as written by nobody."""
    fields = {"kind": "set", "name": "fix_hold", "value": 0.4}
    if by is not None:
        fields["by"] = by

    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(**fields))

    assert refused.value.name == "fix_hold"
    assert refused.value.by == "<unknown>"
    assert "who sent it" in refused.value.why


def test_a_setting_with_no_parameter_name_is_refused():
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name="", value=0.4, by="jake"))

    assert refused.value.name == "<transport>"
    assert "no parameter name" in refused.value.why


def test_a_malformed_setting_over_the_wire_is_a_refusal_naming_it_and_the_link_goes_on(
    zmq_cleanup,
):
    """The path, not the piece: a real packet on a real socket, a refusal that names
    the parameter and the sender (so the feed says whose write it was), and a channel
    that still carries the next command."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    # `True`, not a word: a word is a categorical choice on the wire, and whether it
    # is one of this parameter's choices is `Session.set`'s to say.
    console._req.send(_packed(kind="set", name="fix_hold", value=True, by="jake"))
    console._awaiting_reply = True
    commands = _drain_until(link)

    assert commands == []
    assert [(r.name, r.by) for r in link.refused] == [("fix_hold", "jake")]

    console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
    assert _drain_until(link) == [SetParameter(name="fix_hold", value=0.4, by="jake")]


# ---------------------------------------------------------------------------
# M8 fix round 1: TEXT_LIMIT's stated bound is kept for what a refusal sentence
# quotes, not just for a name or a word
# ---------------------------------------------------------------------------


def test_a_refusal_sentence_quotes_at_most_text_limit_characters_of_a_huge_value():
    """The check the reviewer ran: one packet with a 100,000-float list produced a
    refusal `why` of 500,152 characters before this fix. `_quoted` keeps the
    sentence inside `TEXT_LIMIT`'s promise -- a fixed ceiling on the fixed words
    around the quoted value, not on the value itself."""
    huge = [0.4] * 100_000
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name="fix_hold", value=huge, by="jake"))

    why = refused.value.why
    assert len(why) < 2 * TEXT_LIMIT + 200
    assert "…" in why


def test_a_setting_with_an_over_long_name_is_refused_without_quoting_all_of_it():
    """The no-name refusal used to embed `{name!r}` unbounded -- the very case
    `TEXT_LIMIT` exists for. `_quoted` truncates it too."""
    long_name = "x" * (TEXT_LIMIT + 1)
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name=long_name, value=0.4, by="jake"))

    assert long_name not in refused.value.why


@pytest.mark.parametrize(
    ("by", "expected"),
    [
        ("jake", "jake"),
        ("", "<unknown>"),
        ("   ", "<unknown>"),
        (7, "<unknown>"),
        ("x" * (TEXT_LIMIT + 1), "<unknown>"),
    ],
)
def test_the_no_name_refusal_records_by_under_the_same_rule_as_actor(by, expected):
    """The no-name refusal used to take `data["by"]` unbounded and unchecked for
    blank, unlike `_actor`. It now records the sender only when it is a name
    `_actor` would also accept, and `"<unknown>"` otherwise."""
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name="", value=0.4, by=by))

    assert refused.value.by == expected


def test_the_no_name_refusal_records_unknown_when_by_is_missing_entirely():
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name="", value=0.4))

    assert refused.value.by == "<unknown>"
