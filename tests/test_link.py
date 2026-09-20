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
    REFUSAL_HISTORY,
    Absent,
    Refused,
    RemoteBindRefused,
    Simulated,
    SetParameter,
    Staged,
    Stop,
    Telemetry,
    ZmqConsole,
    ZmqLink,
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
    welfare.left_cage(at=0.0, wall_now=0.0, now=0.0)
    return SimpleNamespace(
        spec=SimpleNamespace(
            session_id="2027-01-14_01",
            subject="A",
            # Read by `Telemetry.of` since 2026-09-20: two of the three kinds
            # answer `None` for chair time and a console has to say which.
            deployment=deployment,
        ),
        welfare=welfare,
        stopped_because="",
        staged=(),
        refusals=(),
        # Read as a plain attribute by `Telemetry.of`, exactly like `link.refused`
        # and for the same reason -- `Session.refusals` is capped at
        # `REFUSAL_HISTORY` since 2026-09-19, and its discards have to reach the
        # frame or a cap reads as a quiet session.
        refusals_dropped=0,
        link=Absent(),
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
    called it remote. It is *also* not assignable on a stock macOS loopback -- trying
    to bind it here raised out of `ZmqLink.__init__` and left an abandoned `Context`
    for pytest's cyclic collector, which is the 300 s hang `ZmqLink.close()`'s
    docstring is about. Checking the predicate keeps the case and loses the hang."""
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


def test_a_link_that_cannot_bind_does_not_abandon_its_context(zmq_cleanup):
    """Found by triggering it: `tcp://127.0.0.2:0` is inside the loopback block, so
    the guard above lets it through, and on a stock macOS loopback it is not an
    assignable address. The `ZMQError` then raised out of `__init__` **after** the
    `Context` and the PUB socket existed and **before** any caller had a handle to
    register with `zmq_cleanup` -- so the context was abandoned mid-construction, and
    the suite stopped terminating. That is the failure `ZmqLink.close()`'s docstring
    describes at length; a constructor that can raise between creating a context and
    returning it is one of the ways in.

    An unbindable endpoint is an ordinary operator mistake -- a port already in use
    is the common one -- and it must cost an error message, not a hung session."""
    try:
        ZmqLink(pub_endpoint="tcp://127.0.0.2:0", rep_endpoint="tcp://127.0.0.1:0")
    except Exception:  # noqa: BLE001 -- whatever zmq raises for this address
        pass
    else:  # pragma: no cover -- this address does bind on some hosts
        return

    # If the context above had been abandoned rather than destroyed, this test would
    # not be the thing that fails: the suite would stop terminating, later, in
    # somebody else's collection. Proving the cleanup happened is therefore the
    # assertion -- a link built and closed normally afterwards still works, which
    # cannot be true of a process wedged in `ctx_t::terminate()`.
    healthy = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    assert healthy.drain() == []


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
