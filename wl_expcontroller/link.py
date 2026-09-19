"""The telemetry message a running session publishes to its consoles, and its schema.

S9a §6-§10 designs the console; **§9, "The telemetry contract," is what this file
implements.** This file holds the message (`Telemetry`, `Staged`, `Refused`), the
commands a console sends back (`SetParameter`, `Stop`, `Command`), the port a session
publishes and drains through (`Link`, `Absent`, `Simulated`), its wire encoding
(`encode`/`decode`, plus the command-side `_encode_command`/`_decode_command`), and
the one live transport that carries all of it over a real socket (`ZmqLink`,
`ZmqConsole`). Nothing here is deferred to a later module -- an earlier version of
this docstring said `encode`/`decode` would land "in a transport module", but Task 5's
own brief puts them in this file instead, so that plan changed and this file is now
current with the code rather than pointing at a module that does not exist.

**Not welfare-critical, and it must not become one.** CLAUDE.md requires human review
before merge for welfare-critical code; `docs/design/architecture.md` names
`wl_expcontroller/bounds.py` and `wl_expcontroller/welfare.py` as the two such
modules, "and nothing else." This file carries no ceiling, no clock and no pump, and
is deliberately not a third. It reads
`welfare`; it never decides anything on its own about what `welfare` reports -- a
limit enforced twice, once in `welfare` and once in a console message, is a limit that
can disagree with itself.

**S9a §9's one rule: every number on the console comes from the object the record is
written from, never computed beside it.** `Telemetry.of` reads `session.welfare`,
`tally` and `scheduler` and assembles the message; it recomputes nothing. A console
showing a sum of reward commands instead of `welfare.session_total()` would silently
disagree with the record the moment `welfare` had a bug in it -- a second,
usually-agreeing implementation is exactly how that bug would hide instead of showing
up on screen.

**Unknown is `None`, never `0`.** `fluid_today_ml` and `shortfall_ml` follow
`welfare.shortfall()`'s own refusal to claim an unmeasured day went well. A console
that rendered `0.0` for a day nobody measured would be a confident answer to a
question nobody could actually answer.
"""

from __future__ import annotations

import time
import weakref
from dataclasses import dataclass, field
from typing import Protocol

#: Bumped whenever a field changes meaning or disappears. ADR-0003: "schema-versioned
#: messages ... version field from day one". A console reading an older schema than it
#: knows must say so rather than render a field it has guessed the meaning of.
SCHEMA = 1


@dataclass(frozen=True, slots=True)
class Staged:
    """A parameter change that has been accepted and has not yet landed.

    **Published to every console, not only to whoever staged it** (S9a §8). With no
    write lock, the only thing between a queued change and an invisible parameter move
    at the next trial boundary is that everybody can see it queued.
    """

    name: str
    was: float | None
    now: float
    by: str
    bounded: bool


@dataclass(frozen=True, slots=True)
class Refused:
    """A console's command that `Session.set` rejected: an undeclared name, or one
    outside its declared range or ceiling.

    **Part of S9a §8's live change feed, the same as `Staged`.** Before this field
    existed, `Session.refusals` was in-memory only -- a person who mistyped a
    parameter name got no feedback at all, and nothing on any console showed that a
    write to a welfare-bounded name had even been attempted. `why` is `str(Exceeded)`,
    already a complete sentence (see `Session.set`'s own messages), not a code a
    console would need the source to interpret.
    """

    name: str
    by: str
    why: str


@dataclass(frozen=True, slots=True)
class Telemetry:
    """What a session tells its consoles, once per trial boundary.

    **Every field is read from the object the record is written from.** None is
    recomputed here, because a console-only number cannot be in the record, cannot be
    checked, and will eventually be read off a screen into a paper (S9a §9).
    """

    schema: int
    session_id: str
    subject: str
    trial_index: int
    block: str
    #: Empty until the session has stopped (mirrors `taskd.Session.stopped_because`).
    stopped_because: str
    #: `welfare.session_total()` -- this session's reconciled contribution to today.
    fluid_session_ml: float
    #: `welfare.total_today()`. `None` when the day's prior total is unknown, never a
    #: confident `0.0`.
    fluid_today_ml: float | None
    #: `welfare.shortfall()`. `None` for the same reason as `fluid_today_ml` -- a
    #: shortfall against an unmeasured day is not a number, it is a guess.
    shortfall_ml: float | None
    #: `welfare.chair_seconds(now)` -- frame-derived, so it matches the ceiling that
    #: ends the session rather than a wall clock that would not.
    chair_seconds: float
    #: Keyed by the outcome's wire string (`Outcome.value`), not the enum member --
    #: this dict is what a msgpack-encoded message will carry.
    outcomes: dict
    hangs: int
    #: `{condition: scheduler.owed(condition)}` for every condition currently queued.
    owed: dict
    #: Every change accepted but not yet applied, from `session.staged` -- see
    #: `Staged`.
    staged: tuple
    #: Every command refused since the session started, from `session.refusals` --
    #: see `Refused`. Cumulative like `outcomes`, not cleared each boundary: a
    #: refusal is a resolved event, not a pending one, so there is no "applied" for
    #: it to disappear at.
    refusals: tuple

    @classmethod
    def of(cls, session, tally, scheduler, index: int) -> "Telemetry":
        """Assemble one trial boundary's telemetry, read and never recomputed.

        `session`, `tally` and `scheduler` are deliberately untyped. Later in this
        slice, `taskd.Session` holds a `Link` and `taskd.py` imports this module -- so
        a `Session` type hint on the first parameter would import `taskd`, which would
        import `link`, immediately. `tally` (`simulate.Tally`) and `scheduler`
        (`scheduler.Scheduler`) are left the same way for symmetry rather than
        annotating two parameters and not the third. Do not add these hints to
        satisfy a linter; the cycle is real.
        """
        return cls(
            schema=SCHEMA,
            session_id=session.spec.session_id,
            subject=session.spec.subject,
            trial_index=index,
            block=scheduler.block.name,
            # No `condition`: telemetry is published at the boundary, *before* the
            # next condition is drawn, so the field could only ever be empty. A field
            # that is always empty is worse than an absent one -- a console renders it
            # and a reader believes it means "no condition" rather than "not yet".
            stopped_because=session.stopped_because,
            fluid_session_ml=session.welfare.session_total(),
            fluid_today_ml=session.welfare.total_today(),
            shortfall_ml=session.welfare.shortfall(),
            chair_seconds=session.welfare.chair_seconds(session.now()),
            outcomes={k.value: v for k, v in tally.outcomes.items()},
            hangs=tally.hangs,
            owed={c: scheduler.owed(c) for c in scheduler.upcoming()},
            # `session.staged`, the public property -- never `session._staged`. This
            # module reaches into `Session` only through its declared surface; a
            # private attribute read across the module boundary is exactly the kind
            # of coupling that breaks silently the day the private shape changes.
            staged=tuple(
                Staged(name=n, was=w, now=v, by=b, bounded=bd)
                for n, w, v, b, bd in session.staged
            ),
            # `session.refusals`, already public -- unlike `_staged`, nothing private
            # to reach around -- plus `session.link.refused`, fix round 1's CRITICAL
            # 2: a wire packet `ZmqLink.drain()` could not decode is a refusal too,
            # and the console should see it the same way it sees a `SetParameter`
            # `Session.set` rejected, not lose it with no record anywhere. Read via
            # `getattr` with a default at both steps -- `session.link` is `Absent()`
            # by default (`taskd.Session`'s own default factory) and `Simulated` has
            # no `.refused` either, because neither ever decodes wire bytes and so
            # can never produce this kind of refusal; only `ZmqLink` can.
            refusals=tuple(
                Refused(name=n, by=b, why=w) for n, b, w in session.refusals
            )
            + tuple(getattr(getattr(session, "link", None), "refused", ())),
        )


def encode(telemetry: Telemetry) -> bytes:
    """`Telemetry` to msgpack, the wire format ADR-0003 named alongside ZeroMQ.

    Imports `msgpack` **lazily, inside this function** -- the same discipline as
    `ZmqLink`/`ZmqConsole` below and required by this task: `link.py` is imported by
    `taskd.py`, which a rig operator running `wlx run` from a terminal loads with
    neither `zmq` nor `msgpack` installed, and the Python 3.13 CI leg exists
    specifically to catch a transport dependency leaking into that path (S9a §5's
    argument for the display layer, holding identically here).

    Every field is written out by name rather than handed to
    `dataclasses.asdict(telemetry)`. `asdict` would flatten `staged`/`refusals` into
    plain dicts happily enough for encoding, but `decode` still has to rebuild
    `Staged`/`Refused` instances to make `restored == original` true, so the two
    directions are written out explicitly here rather than trusting a generic
    recursive helper to invert itself correctly.
    """
    import msgpack

    payload = {
        "schema": telemetry.schema,
        "session_id": telemetry.session_id,
        "subject": telemetry.subject,
        "trial_index": telemetry.trial_index,
        "block": telemetry.block,
        "stopped_because": telemetry.stopped_because,
        "fluid_session_ml": telemetry.fluid_session_ml,
        "fluid_today_ml": telemetry.fluid_today_ml,
        "shortfall_ml": telemetry.shortfall_ml,
        "chair_seconds": telemetry.chair_seconds,
        "outcomes": telemetry.outcomes,
        "hangs": telemetry.hangs,
        "owed": telemetry.owed,
        "staged": [
            {"name": s.name, "was": s.was, "now": s.now, "by": s.by, "bounded": s.bounded}
            for s in telemetry.staged
        ],
        "refusals": [{"name": r.name, "by": r.by, "why": r.why} for r in telemetry.refusals],
    }
    return msgpack.packb(payload, use_bin_type=True)


def decode(payload: bytes) -> Telemetry:
    """The inverse of `encode`, rebuilding `Staged`/`Refused` rather than leaving
    them as the plain dicts msgpack hands back.

    **`None` survives.** msgpack has a native nil, distinct from `0`/`0.0`, and
    `unpackb`'s default `raw=False` returns Python `str` rather than `bytes` for text
    -- so `fluid_today_ml`/`shortfall_ml` round-trip as `None` when that is what they
    were, never silently becoming a number. See this module's docstring: an unknown
    day rendered as a confident `0.0` is exactly the failure `welfare.shortfall()`
    exists to prevent, and a console showing it would be the same failure one hop
    further downstream.
    """
    import msgpack

    data = msgpack.unpackb(payload, raw=False)
    return Telemetry(
        schema=data["schema"],
        session_id=data["session_id"],
        subject=data["subject"],
        trial_index=data["trial_index"],
        block=data["block"],
        stopped_because=data["stopped_because"],
        fluid_session_ml=data["fluid_session_ml"],
        fluid_today_ml=data["fluid_today_ml"],
        shortfall_ml=data["shortfall_ml"],
        chair_seconds=data["chair_seconds"],
        outcomes=data["outcomes"],
        hangs=data["hangs"],
        owed=data["owed"],
        staged=tuple(Staged(**s) for s in data["staged"]),
        refusals=tuple(Refused(**r) for r in data["refusals"]),
    )


@dataclass(frozen=True, slots=True)
class SetParameter:
    """A parameter change offered by a console. Validated by `Session.set`, which is
    the one write path -- this carries the request, never a second validator."""

    name: str
    value: float
    by: str


@dataclass(frozen=True, slots=True)
class Stop:
    """End the session at the next trial boundary. **Never mid-trial**: a trial the
    animal completed must not be aborted, which is the rule `welfare.Rig` follows for
    pump faults."""

    by: str


Command = SetParameter | Stop


def _encode_command(command: Command) -> bytes:
    """`SetParameter`/`Stop` to msgpack, tagged by kind so `_decode_command` knows
    which dataclass to rebuild.

    Private, unlike `encode`/`decode`: `ZmqConsole.send` is the only caller, in this
    same file, so this is an implementation detail of the REQ/REP leg rather than a
    wire contract another module is meant to import.
    """
    import msgpack

    if isinstance(command, SetParameter):
        payload = {"kind": "set", "name": command.name, "value": command.value, "by": command.by}
    elif isinstance(command, Stop):
        payload = {"kind": "stop", "by": command.by}
    else:
        raise TypeError(f"no wire encoding for {command!r}")
    return msgpack.packb(payload, use_bin_type=True)


def _decode_command(payload: bytes) -> Command:
    """The inverse of `_encode_command`. `ZmqLink.drain` is the only caller."""
    import msgpack

    data = msgpack.unpackb(payload, raw=False)
    kind = data["kind"]
    if kind == "set":
        return SetParameter(name=data["name"], value=data["value"], by=data["by"])
    if kind == "stop":
        return Stop(by=data["by"])
    raise ValueError(f"unknown command kind on the wire: {kind!r}")


class Link(Protocol):
    def publish(self, telemetry: Telemetry) -> None:
        """Offer telemetry to whoever is listening. **Must never block**: latest-wins
        telemetry that could stall a trial boundary would make a view able to delay an
        experiment."""

    def drain(self) -> list[Command]:
        """Every command that has arrived since the last call. Non-blocking, and each
        command is returned once."""


@dataclass(frozen=True, slots=True)
class Absent:
    """No console, and that is a legitimate configuration. **Unlike `dio.Absent` and
    `run.Unwired`, this one is silent, not refusing**, because what is lost differs.
    A dropped event code is missing from a recording forever, and a dropped reward is
    fluid an animal worked for -- either is catastrophic. But telemetry nobody
    subscribed to loses nothing; the record is the record. A session with no console
    attached is exactly how the cage-side kiosk runs."""

    def publish(self, telemetry: Telemetry) -> None:
        return None

    def drain(self) -> list[Command]:
        return []


@dataclass
class Simulated:
    """The in-process link a test drives. A complete `Link` implementation that does
    not abstract away the state -- every telemetry message is kept in `published`, and
    every command queued by the test is delivered exactly once to the next `drain()`
    call, never appearing again. This allows test code to verify both directions: that
    the session published telemetry when expected, and that commands work their way in
    only when the test staged them."""

    published: list = field(default_factory=list)
    _queued: list = field(default_factory=list)

    def queue(self, command) -> None:
        self._queued.append(command)

    def publish(self, telemetry: Telemetry) -> None:
        self.published.append(telemetry)

    def drain(self) -> list[Command]:
        taken, self._queued = self._queued, []
        return taken


class ZmqLink:
    """The `taskd` side of the console link, live on a real socket (S9a §7:
    `taskd ── ZMQ REQ/REP (commands) / ZMQ PUB (telemetry) ──> console`, ADR-0003's
    transport, untouched by the console design).

    Two sockets, not one, because the two directions have opposite delivery
    semantics. `publish` (PUB) is lossy and must never block, so a console that is
    slow, unattached, or stuck reading its last message cannot stall a trial
    boundary. `drain` (REP) is reliable within one poll -- a command that is seen is
    never silently dropped -- but is still non-blocking on this end, because a
    session's trial loop calls it once per boundary and cannot wait on a console
    that has nothing to say.

    Imports `zmq` **lazily, inside `__init__`**, never at module level -- see
    `encode`'s docstring for why this file cannot afford an unconditional
    `import zmq`.

    Binds to `pub_endpoint`/`rep_endpoint` as given -- `tcp://127.0.0.1:0` asks the
    OS for an ephemeral port -- and `self.pub_endpoint`/`self.rep_endpoint` read back
    what ZeroMQ actually bound (`zmq.LAST_ENDPOINT`), which is what a `ZmqConsole`
    needs in order to connect.
    """

    def __init__(self, pub_endpoint: str, rep_endpoint: str):
        import zmq

        self._ctx = zmq.Context()
        # A cleanup path that does not go through close() at all -- see close()'s
        # own docstring for why that matters and what it replaced.
        weakref.finalize(self, self._ctx.destroy, 0)

        self._pub = self._ctx.socket(zmq.PUB)
        # LINGER=0 from creation, not only passed at close time: whenever this
        # socket is closed -- by close(), or by the finalizer above -- it cannot
        # block flushing a queued message, regardless of which path closed it.
        self._pub.setsockopt(zmq.LINGER, 0)
        self._pub.bind(pub_endpoint)
        self.pub_endpoint = self._pub.getsockopt_string(zmq.LAST_ENDPOINT)

        self._rep = self._ctx.socket(zmq.REP)
        self._rep.setsockopt(zmq.LINGER, 0)
        self._rep.bind(rep_endpoint)
        self.rep_endpoint = self._rep.getsockopt_string(zmq.LAST_ENDPOINT)

        #: Wire packets `drain()` could not turn into a `Command`, as `Refused`
        #: entries -- see `drain()`'s docstring (fix round 1, CRITICAL 2). Cumulative
        #: like `Session.refusals`, which this is the transport-layer twin of: a
        #: `ZmqLink`-specific extension, not part of the `Link` protocol, because
        #: `Absent`/`Simulated` never see wire bytes and so can never produce one.
        self.refused: list[Refused] = []

    def publish(self, telemetry: Telemetry) -> None:
        """Offer telemetry to whoever is subscribed. **Never blocks** (S9a §9: "ZMQ
        PUB drops rather than blocks, because latest-wins telemetry must never stall
        a frame"): sent with `zmq.DONTWAIT`, and a full send queue -- `zmq.Again` --
        is swallowed rather than raised. The next boundary's frame supersedes this
        one regardless, so losing it costs nothing a working console would notice."""
        import zmq

        try:
            self._pub.send(encode(telemetry), flags=zmq.DONTWAIT)
        except zmq.Again:
            pass

    def drain(self) -> list[Command]:
        """Every well-formed command waiting on the REP socket right now, replied to
        as it is read.

        Polls with a zero timeout -- never blocks the trial loop waiting for a
        console that has nothing to say -- looping only while `poll` reports more
        already waiting, so this returns as soon as the queue is empty rather than
        after a fixed number of checks. REP's state machine requires exactly one
        reply per request; skipping it would wedge the socket for whichever console
        sent it, so every `recv` here is paired with a `send` before the next
        `recv`. The reply means "your command reached the session," not "your
        command was applied" -- `drain` only turns bytes into `Command` objects;
        `Session.set` is where acceptance or refusal is decided, and that outcome
        reaches every console as `Staged`/`Refused` in the next `Telemetry` frame,
        not in this reply.

        **Reply before decode, always -- fix round 1, CRITICAL 2, measured.** The
        reply used to be sent only after a successful `_decode_command`, so an
        undecodable packet's exception propagated out of `drain` and out of
        `taskd.py`'s trial loop, ending the session -- measured with `{"kind":
        "pause"}`. Worse, because the reply was never sent, the REP socket was left
        owing one, so the *next* call's poll/recv against a perfectly valid command
        also failed: one garbage packet took the whole channel down, not just
        itself. Replying unconditionally, before the `try`, means a malformed packet
        can never leave the REP socket in that state.

        **Never raised, never dropped silently either.** Every way a wire packet can
        fail to become a `Command` -- bad msgpack, the wrong shape, an unknown kind
        -- is caught broadly and deliberately (`Exception`, not a narrow list) and
        turned into a `Refused` appended to `self.refused`, because refusing quietly
        is how a console (a newer build against a bumped `SCHEMA`, S9a §9, is a
        realistic source of this, not just corruption) loses a command with no
        record anywhere that anything was even attempted -- the same failure
        `Session.refusals` exists to prevent for a rejected `SetParameter`. `name`
        and `by` are placeholders (`"<transport>"`, `"<unknown>"`): a packet that
        failed to decode carries no reliable actor or parameter name to report,
        unlike a `SetParameter` that decoded fine and was rejected by `Session.set`.
        """
        import zmq

        commands: list[Command] = []
        while self._rep.poll(timeout=0, flags=zmq.POLLIN):
            raw = self._rep.recv()
            self._rep.send(b"received")
            try:
                commands.append(_decode_command(raw))
            except Exception as exc:  # noqa: BLE001 -- deliberately broad, see above
                self.refused.append(
                    Refused(name="<transport>", by="<unknown>", why=f"could not decode command: {exc}")
                )
        return commands

    def close(self) -> None:
        """Release both sockets and this link's own `Context`, promptly.

        `Context.destroy(linger=0)`, not `.term()` plus two manual `.close()` calls
        -- fix round 1, measured: `ctx.term()` blocks on ANY socket under that
        context that is not yet closed (a bare probe script, this session's
        scratchpad: an unclosed socket makes `term()` hang indefinitely), while
        `destroy(linger=0)`, called the same way from ordinary application code,
        force-closes every socket the context owns and returns immediately
        (measured: 0.0001 s against the identical unclosed socket) -- so this stays
        correct even if a future edit adds a third socket here and forgets to list
        it explicitly, which the old three-line version could not say.

        **An open item, recorded rather than papered over.** `__init__` also
        registers a `weakref.finalize(self, self._ctx.destroy, 0)` -- confirmed, by
        sampling the stuck process, to actually run (a mutated, do-nothing `close()`
        no longer leaves the callback un-invoked) -- but neutering `close()`
        (`tools/mutate.py --all`, proving it is covered) still hangs the full suite
        past 300 s. The same `destroy(linger=0)` call that returns in 0.0001 s from
        this method, from a bare script, and even from an explicit `gc.collect()` in
        a bare script with several abandoned link/console pairs, blocks in
        `ctx_t::terminate()` specifically when invoked as a `weakref.finalize`
        callback from *pytest's* cyclic collector (`gc_collect_main`) -- narrowed
        that far and no further before running out of budget for this round. Ruled
        out by direct measurement, not assumption: an unread `drain()` reply left on
        the REQ socket; the number of accumulated abandoned pairs; and a live peer
        connection on the socket being destroyed -- none of these reproduce it
        outside pytest. `tools/mutate.py`'s own docstring calls a hung mutation
        caught, since a suite that stops terminating has certainly noticed the
        change, and every other function in this file is caught by a fast,
        conventional assertion failure -- only this one costs the full 300 s. Left
        for a future session with a `sample`/`py-spy` trace of pytest's own object
        graph at the point of collection, which this round did not have time for.

        Not part of the `Link` protocol. **Resolved 2026-09-19 (Task 6):** this
        paragraph used to name `wlx run --link` as the "not yet" nothing called
        `close()` in production was waiting for (CLAUDE.md: a "not yet" must name
        what it is waiting for, so the next reader can grep it rather than believe
        it). `wlx run --link` (`cli.py`'s `run` command) now constructs the
        `ZmqLink` this method belongs to, wrapped in `with` rather than a bare
        `try`/`finally` so `close()` cannot be forgotten -- it runs via `__exit__`
        on every exit from that command, a normal return or an exception out of
        `session.run()` alike. The open item immediately above this paragraph (the
        300 s pytest-collector hang under `weakref.finalize`) is unrelated and
        still open; this note only closes the "nothing calls it yet" half.
        """
        self._ctx.destroy(linger=0)

    def __enter__(self) -> "ZmqLink":
        return self

    def __exit__(self, *exc_info: object) -> None:
        """So a `try`/`finally` around `close()` cannot be forgotten -- every test in
        this file that opens a `ZmqLink` can use `with` instead."""
        self.close()


class ZmqConsole:
    """The console side of the same link (S9a §7). Connects to a running
    `ZmqLink`'s two endpoints: SUB for telemetry, REQ for commands.

    Subscribes to everything (`b""`) -- S9a §9 leaves splitting telemetry across
    topics to a later slice ("a separate droppable topic" for a display-rate stream,
    "if V11 permits one"); today there is exactly one topic, so no filtering is
    needed here.

    **The settle delay after connecting reduces one real but non-critical gap; it is
    never a correctness requirement.** ZeroMQ's PUB socket does not queue a message
    for a subscriber whose subscription has not yet propagated to it -- the
    well-documented "slow joiner" behaviour -- so a console that connects and is
    published to immediately can miss that first frame. Telemetry is lossy by design
    (S9a §9) and the next published frame always arrives regardless, so a console
    that keeps reading is never actually stuck -- this delay only spares a human
    opening a console the sight of a gap before the very first frame. `settle_s`
    (default 0.05, i.e. 50 ms) is a parameter rather than a hard-coded sleep so a
    test can set it to `0` and prove the system is still correct without it --
    `test_the_system_still_works_with_no_settle_delay` in `test_link.py` does exactly
    that, using retries rather than a second sleep to observe the (still real, just
    unmitigated) gap resolve itself. 50 ms was measured on this machine to be well
    clear of the problem at the default (0 misses in 1000 back-to-back trials, this
    session's scratchpad probe, not committed as a repo measurement because it is a
    ZeroMQ implementation detail rather than a claim about this system's own latency,
    jitter or throughput).
    """

    def __init__(self, pub_endpoint: str, req_endpoint: str, settle_s: float = 0.05):
        import zmq

        self._ctx = zmq.Context()
        weakref.finalize(self, self._ctx.destroy, 0)  # see ZmqLink.__init__

        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.setsockopt(zmq.LINGER, 0)  # see ZmqLink.__init__ -- same reasoning
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")
        # Bounded, not infinite: a console that lost its session should raise
        # rather than hang a UI thread forever. Not a latency claim about this
        # system -- a ceiling above which something is already wrong, not a
        # measured number.
        self._sub.setsockopt(zmq.RCVTIMEO, 5000)
        self._sub.connect(pub_endpoint)

        self._req = self._ctx.socket(zmq.REQ)
        self._req.setsockopt(zmq.LINGER, 0)
        # Same ceiling as the SUB socket above, same reasoning -- see send()'s
        # docstring for why a bounded read happens there at all.
        self._req.setsockopt(zmq.RCVTIMEO, 5000)
        self._req.connect(req_endpoint)
        #: Whether the last send() has a reply on this socket still unread. REQ's
        #: state machine forbids a second send() before the first send's reply is
        #: read -- see send()'s docstring.
        self._awaiting_reply = False

        time.sleep(settle_s)  # see the class docstring -- the PUB/SUB settle delay

    def send(self, command: Command) -> None:
        """Offer a command to the session.

        **Fix round 1, CRITICAL 1, measured:** a REQ socket's state machine forbids
        a second `send()` before the first send's reply is read -- `SetParameter`
        then `Stop`, the ordinary sequence S9a §8 is built on, raised
        `zmq.error.ZMQError: Operation cannot be accomplished in current state` on
        the second call, because the reply `drain()` always sends was left
        permanently unread. Fixed by reading it here, **lazily, one send behind**:
        this call first consumes the *previous* send's reply, if one is still
        outstanding, and only then sends the new command. The first-ever `send()`
        (nothing outstanding) is unaffected and still returns as soon as the message
        is queued -- REQ's send half returns before a peer has necessarily processed
        anything, so this cannot block on a session that has not called `drain` yet.
        Reading eagerly, inside the *same* call that sends -- awaiting this command's
        own reply before returning -- was rejected: nothing calls `drain()`
        concurrently with `send()` in this codebase (no threads), so that would
        deadlock any single caller that sends and then itself drives `drain()`,
        which is exactly how every test here and how `wlx console` (Task 6) is
        expected to work.

        Bounded by the REQ socket's `RCVTIMEO` (set in `__init__`, same ceiling as
        `receive`'s SUB socket): if the previous reply never arrives, this raises
        `TimeoutError` rather than wedging silently -- consistent with `receive()`,
        and for the same reason nothing outside this file should see a `zmq.Again`.
        """
        import zmq

        if self._awaiting_reply:
            try:
                self._req.recv()
            except zmq.Again as exc:
                raise TimeoutError(
                    "no reply to the previous command within the console's receive "
                    "timeout; refusing to send another command until this socket "
                    "is healthy again"
                ) from exc
            self._awaiting_reply = False
        self._req.send(_encode_command(command))
        self._awaiting_reply = True

    def receive(self) -> Telemetry:
        """Block for the next telemetry frame, up to the receive timeout set in
        `__init__`. Raises `TimeoutError` rather than leaking `zmq.Again` -- nothing
        outside this file has a reason to know this link happens to be ZeroMQ."""
        import zmq

        try:
            raw = self._sub.recv()
        except zmq.Again as exc:
            raise TimeoutError("no telemetry received within the console's receive timeout") from exc
        return decode(raw)

    def close(self) -> None:
        """See `ZmqLink.close` -- same reasoning, same shape."""
        self._ctx.destroy(linger=0)

    def __enter__(self) -> "ZmqConsole":
        return self

    def __exit__(self, *exc_info: object) -> None:
        """See `ZmqLink.__exit__` -- same reasoning, same shape."""
        self.close()
