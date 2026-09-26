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

import ipaddress
import time
import weakref
from dataclasses import dataclass, field
from typing import Protocol

#: Bumped whenever a field changes meaning or disappears. ADR-0003: "schema-versioned
#: messages ... version field from day one". A console reading an older schema than it
#: knows must say so rather than render a field it has guessed the meaning of.
#:
#: 2 (2026-09-19): `refusals` stopped meaning "every refusal since the session
#: started" and became "the most recent `REFUSAL_HISTORY`", and `refusals_dropped`
#: was added to say how many are missing. That is a field changing meaning, which is
#: exactly what this number exists for.
#:
#: 3 (2026-09-19, PI): `Staged.bounded` stopped meaning "this value is already live"
#: and became "this name is checked against a welfare ceiling rather than the task's
#: `Param`". No field was added or removed, which is why this one matters: a console
#: built against schema 2 renders a `bounded=True` row as ALREADY IN EFFECT, and
#: would now tell an operator who has just *lowered* a reward volume that it has
#: taken effect while one more trial is still to go out at the old one. A field that
#: still decodes and no longer means what it did is the case this number exists for.
#:
#: 4 (2026-09-19, PI): `chair_seconds` stopped being the number that ends the
#: session and became a recorded quantity beside it; `out_of_cage_seconds` is the
#: one the ceiling is now read against, and is `None` for a cage-side session that
#: declared it has no duration bound at all. A console built against schema 3 shows
#: chair time as *the* clock and would watch a session stop on a limit it never
#: displayed -- the same "a field still decodes and no longer means what it did"
#: case as 3, with a welfare limit on the other end of it.
#:
#: 5 (2026-09-20, PI): head-fixation stopped being a blanket rig requirement, so
#: there are three deployment kinds rather than two. `chair_seconds` became
#: `float | None` -- **absent, never `0.00`, for the two kinds that take no
#: head-fixation marks** -- `deployment` was added so a console can say *which*
#: absence it is looking at rather than deriving it, and `duration_warning` was added
#: for the warning that now precedes the out-of-cage limit. A console built against 4
#: renders `chair_seconds` with a `None` in it, and one that coerced would tell an
#: operator a restrained animal had been restrained for no time at all.
#:
#: 6 (2026-09-26, P4d-2a): `phase` and `stop_kind`. A console built against 5 renders
#: an awaiting-return frame's advancing clock as a running session.
SCHEMA = 6

#: How many refusals a session keeps, per source, and therefore how many one
#: `Telemetry` frame can carry.
#:
#: **This is a bound on work an untrusted peer can cause, not a display preference.**
#: `Telemetry.refusals` was cumulative and uncapped, and `Telemetry.of` re-encodes the
#: whole of it at every trial boundary. The party that drives its growth is not the
#: operator: `ZmqLink.drain` appends one `Refused` per wire packet it cannot decode,
#: and any peer that can reach the REP socket can send those as fast as it likes. A
#: console built against a bumped `SCHEMA` does it by accident, every packet, forever
#: -- which is the realistic case, not an attack. Both the per-boundary encode and the
#: published PUB frame then grow linearly and without limit.
#:
#: 50, because the number has to clear what a person can plausibly do and stay far
#: under what a loop can. A refusal is a human act at heart -- a mistyped parameter
#: name, a volume above its ceiling -- and fifty of them in one session is already far
#: past the point where somebody would stop and look at the screen; the console shows
#: a handful of lines, so nothing an operator needs is among the ones dropped. At the
#: same time it keeps the frame small: measured on this branch (scratchpad probe, not
#: committed under `docs/measurements/` and not a claim about this system's latency,
#: jitter or throughput -- it is a byte count), one frame carrying the longest refusal
#: this code can produce is 231 bytes empty, 5,433 bytes at 50, 104,233 bytes at 1,000
#: and 1,040,233 bytes at 10,000, re-encoded every boundary.
#:
#: Nothing is lost silently: what falls off is counted in `Telemetry.refusals_dropped`
#: and `ZmqLink.refused_dropped`, and `cli.render` prints the count.
REFUSAL_HISTORY = 50


@dataclass(frozen=True, slots=True)
class Staged:
    """A parameter change that has been accepted and is not yet applied.

    **Published to every console, not only to whoever staged it** (S9a §8). With no
    write lock, the only thing between a queued change and an invisible parameter move
    at the next trial boundary is that everybody can see it queued.

    **Every row is genuinely pending, whatever `bounded` says** (PI, 2026-09-19).
    `Session._apply_staged` applies all of them at the top of the next pass, and the
    trial running now still uses the old value -- a welfare ceiling and an ordinary
    task parameter alike.

    `bounded` says which **vocabulary** the name belongs to, and nothing about when
    it lands:

    - `bounded=False` -- an ordinary task parameter, checked against the task's own
      `Param` declaration and written to `spec.values`.
    - `bounded=True` -- a welfare-bounded value such as `reward_correct`, checked
      against `bounds.Ceiling.maximum` and written onto the ceiling.

    It briefly meant something else, and a console must not go back to it:
    `Session.set` used to move a bounded value on the ceiling as the command was
    drained, so a `bounded=True` row was already live while this class called it
    staged. `cli.render` names the vocabulary on screen and says of both rows that
    they apply at the next trial. The behaviour, and the attribution bug that ended
    it, live at `taskd.Session.set` and `bounds.Bounds.validate`.
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
    #: Why the session stopped, as a kind rather than a sentence: `completed`,
    #: `operator`, `limit` or `fault`, and `None` while it runs. `stopped_because`
    #: keeps the sentence; this exists because telling a pump fault from a clean
    #: finish by parsing that sentence would be fragile, and P4d-2b's `/health`
    #: verdict needs the difference (P4d-2a spec §6).
    stop_kind: str | None
    #: `running` while the loop runs -- including the frame that announces its stop
    #: -- then `awaiting_return` while a rig session's out-of-cage clock is still
    #: open, then `closed` once the return is recorded. A cage-side session never
    #: leaves `running` on the wire: its last word is its stop frame.
    phase: str
    #: `welfare.session_total()` -- this session's reconciled contribution to today.
    #:
    #: **Welfare-load-bearing, and not only informational** (PI, 2026-09-20). A
    #: reward volume of zero is *allowed* -- pausing reward without ending a session
    #: -- and the PI allowed it **because it is visible**: this field going `0.00`
    #: is how an operator sees that a correctly-working animal is being paid
    #: nothing. Reporting it is the condition of that ruling, so a change that
    #: stopped publishing it, or a pane that stopped showing it, would turn a
    #: permitted operation into a silent one. S8 §5.2c.
    #:
    #: **And zero may be the design working** (PI, 2026-09-20): a trial may have a
    #: reward period that pays an on-screen *token* rather than fluid, converting to
    #: fluid later. So this reading `0.00` is not a fault signal and must not be
    #: treated as one; `shortfall_ml` is the field that still says what is owed.
    fluid_session_ml: float
    #: `welfare.total_today()`. `None` when the day's prior total is unknown, never a
    #: confident `0.0`.
    fluid_today_ml: float | None
    #: `welfare.shortfall()`. `None` for the same reason as `fluid_today_ml` -- a
    #: shortfall against an unmeasured day is not a number, it is a guess.
    #:
    #: The other half of the zero-reward ruling above: with the volume at zero this
    #: keeps reporting the whole floor as owed, so the supplement figure stays
    #: correct and the animal is topped up afterwards.
    shortfall_ml: float | None
    #: `welfare.out_of_cage_seconds(now)` -- **the clock the session's one duration
    #: ceiling is read against** (PI, 2026-09-19), frame-derived rather than a wall
    #: clock so that the console's number and the ceiling's are the same number.
    #: `None` for a cage-side session, which declared it has no duration bound
    #: (`welfare.Deployment`); never `0.0`, which would read as a clock not started.
    out_of_cage_seconds: float | None
    #: `welfare.chair_seconds(now)` -- restraint, **recorded and bounding nothing**
    #: since 2026-09-19. Still shown because an operator wants to know how long an
    #: animal has been in the chair; it is simply not what ends the session.
    #:
    #: **`None`, never `0.0`, for `RIG_CHAIRED` and `CAGE_SIDE`** (PI, 2026-09-20).
    #: A chaired-but-unfixed animal *is* restrained and simply has no head-fixation
    #: marks, so a zero here would report a measurement nothing took -- the
    #: `shortfall()`-answering-zero-for-an-unmeasured-day failure, on the restraint
    #: clock. `deployment` below is how a console says which of the two reasons it
    #: is.
    chair_seconds: float | None
    #: `session.spec.deployment.value` -- which of `welfare.Deployment`'s three kinds
    #: this session declared. On the wire rather than inferred from which fields are
    #: `None`, because `cli.render` promises to name a field per line and derive
    #: nothing, and because two kinds share one `None`.
    deployment: str
    #: `welfare.approaching_limit(now)` -- the sentence the session would use as the
    #: out-of-cage ceiling comes into view (PI, 2026-09-20), or `None` while there is
    #: nothing to say. Read rather than recomputed, so the console's warning and the
    #: session's are the same statement and cannot drift.
    duration_warning: str | None
    #: Keyed by the outcome's wire string (`Outcome.value`), not the enum member --
    #: this dict is what a msgpack-encoded message will carry.
    outcomes: dict
    hangs: int
    #: `{condition: scheduler.owed(condition)}` for every condition currently queued.
    owed: dict
    #: Every change accepted but not yet applied, from `session.staged` -- see
    #: `Staged`, whose `bounded` flag says which vocabulary the name belongs to, not
    #: when it lands. Every row lands at the next trial boundary.
    staged: tuple
    #: The most recent `REFUSAL_HISTORY` refusals, oldest first, from
    #: `session.refusals` (itself capped) and `session.link.refused` -- see
    #: `Refused`. Cumulative
    #: like `outcomes` rather than cleared each boundary, because a refusal is a
    #: resolved event and not a pending one, so there is no "applied" for it to
    #: disappear at -- but **capped**, because the peer that drives its growth is
    #: not necessarily the operator. See `REFUSAL_HISTORY`.
    refusals: tuple
    #: How many refusals happened that are **not** in `refusals`, because they fell
    #: off the far end of `REFUSAL_HISTORY`. Zero for any session nobody flooded.
    #: Present so that a cap cannot be mistaken for a quiet session: a console that
    #: showed fifty refusals and said nothing about the four hundred before them
    #: would be the silent-drop failure this field exists to prevent.
    refusals_dropped: int

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

        **`session.link.refused` is read as a plain attribute, on purpose.** Both
        steps used to be `getattr(..., default)`: the outer one so that
        `test_link.py`'s `SimpleNamespace` stand-in needed no `link`, the inner one
        because `Absent`/`Simulated` had no `refused`. Two silent defaults on the path
        that carries transport refusals to the console means a rename of
        `ZmqLink.refused`, or a `Session` built without a link, makes those refusals
        vanish from telemetry with nothing raising and every test still green -- the
        failure shape `dio.Absent`, `welfare.Absent` and `run.Unwired` all exist to
        refuse. `refused` and `refused_dropped` are part of the `Link` protocol now,
        `Absent` and `Simulated` answer them with empties of their own, and the
        stand-in carries a real `Absent()`. An absent link is an `AttributeError`
        here, which is the point.

        **The refusal feed is capped at `REFUSAL_HISTORY`, newest kept.** What falls
        off is counted rather than dropped -- see that constant, and
        `refusals_dropped`.
        """
        link = session.link
        refusals = (
            tuple(Refused(name=n, by=b, why=w) for n, b, w in session.refusals)
            + tuple(link.refused)
        )
        kept = refusals[-REFUSAL_HISTORY:]
        # Three sources of loss, and none of them overlap: entries `ZmqLink` already
        # trimmed off its own list and entries `Session` already trimmed off its own
        # (neither is in `refusals` above), plus entries this slice drops here.
        # `session.refusals_dropped` joined the sum on 2026-09-19, when
        # `Session.refusals` stopped being the one uncapped list of the three; read
        # as a plain attribute for the reason `link.refused` is.
        dropped = (
            link.refused_dropped
            + session.refusals_dropped
            + len(refusals)
            - len(kept)
        )
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
            stop_kind=session.stop_kind,
            phase=session.phase,
            fluid_session_ml=session.welfare.session_total(),
            fluid_today_ml=session.welfare.total_today(),
            shortfall_ml=session.welfare.shortfall(),
            # `welfare_now()`, not `now()`: after the loop the frame clock has
            # stopped and the wall has not (P4d-2a). Both are `Session`'s to say.
            out_of_cage_seconds=session.welfare.out_of_cage_seconds(
                session.welfare_now()
            ),
            chair_seconds=session.welfare.chair_seconds(session.welfare_now()),
            deployment=session.spec.deployment.value,
            duration_warning=session.duration_warning(),
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
            # `Session.set` rejected, not lose it with no record anywhere. Both are
            # assembled and capped above; see this method's docstring for why neither
            # read goes through a `getattr` default any more.
            refusals=kept,
            refusals_dropped=dropped,
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
        "stop_kind": telemetry.stop_kind,
        "phase": telemetry.phase,
        "fluid_session_ml": telemetry.fluid_session_ml,
        "fluid_today_ml": telemetry.fluid_today_ml,
        "shortfall_ml": telemetry.shortfall_ml,
        "out_of_cage_seconds": telemetry.out_of_cage_seconds,
        "chair_seconds": telemetry.chair_seconds,
        "deployment": telemetry.deployment,
        "duration_warning": telemetry.duration_warning,
        "outcomes": telemetry.outcomes,
        "hangs": telemetry.hangs,
        "owed": telemetry.owed,
        "staged": [
            {"name": s.name, "was": s.was, "now": s.now, "by": s.by, "bounded": s.bounded}
            for s in telemetry.staged
        ],
        "refusals": [{"name": r.name, "by": r.by, "why": r.why} for r in telemetry.refusals],
        "refusals_dropped": telemetry.refusals_dropped,
    }
    return msgpack.packb(payload, use_bin_type=True)


def decode(payload: bytes) -> Telemetry:
    """The inverse of `encode`, rebuilding `Staged`/`Refused` rather than leaving
    them as the plain dicts msgpack hands back.

    **`None` survives.** msgpack has a native nil, distinct from `0`/`0.0`, and
    `unpackb`'s default `raw=False` returns Python `str` rather than `bytes` for text
    -- so `fluid_today_ml`/`shortfall_ml`/`out_of_cage_seconds`/`chair_seconds`
    round-trip as `None` when that is what they were, never silently becoming a
    number. For the first two that is an unknown day; for the third it is a cage-side
    session that has no such interval, and a `0.0` on the wire would read as a clock
    that had not started; for the fourth it is a deployment that takes no
    head-fixation marks, where a `0.00` would report an animal as unrestrained that
    is sitting in a chair.
    See this module's docstring: an unknown
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
        stop_kind=data["stop_kind"],
        phase=data["phase"],
        fluid_session_ml=data["fluid_session_ml"],
        fluid_today_ml=data["fluid_today_ml"],
        shortfall_ml=data["shortfall_ml"],
        out_of_cage_seconds=data["out_of_cage_seconds"],
        chair_seconds=data["chair_seconds"],
        deployment=data["deployment"],
        duration_warning=data["duration_warning"],
        outcomes=data["outcomes"],
        hangs=data["hangs"],
        owed=data["owed"],
        staged=tuple(Staged(**s) for s in data["staged"]),
        refusals=tuple(Refused(**r) for r in data["refusals"]),
        refusals_dropped=data["refusals_dropped"],
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


@dataclass(frozen=True, slots=True)
class ReturnedToCage:
    """The animal is home (P4d-2a). `at` is a POSIX wall instant -- a clock time is
    what an operator reads (PI, 2026-09-20, ruling 4). `confirmed` says a person
    acted on a time more than thirty minutes off; `welfare.returned_to_cage` refuses
    a far one without it, and that refusal comes back as a `Refused` with the
    sentence a person needs. Carries the request, never a second validator.

    **`__post_init__` checks types, not finiteness -- fix round 1, measured.**
    `ReturnedToCage(at="banana", by="jake", confirmed=False)` reached
    `bounds._finite` (via `welfare._far_from_now`, via `return_needs_confirmation`),
    and `math.isfinite("banana")` raises `TypeError`, not `Exceeded`.
    `taskd.Session._command` catches only `Exceeded` -- "Refusals do not end the
    session" is its own rule -- so the `TypeError` escaped into `run()`'s fault
    handler and ended the session outright, which is the one outcome a malformed
    command must never cause. **`confirmed` has the same shape of problem on a
    different guard**: `welfare._refuse_unconfirmed` tests `if sentence is None or
    confirmed:`, so any truthy non-bool -- the string `"no"` included -- satisfies it
    as though a person had confirmed a far mark, silently defeating the one guard
    `confirmed` exists for. Both are checked here, at the one place every
    `ReturnedToCage` is built, whether directly or through `_decode_command` -- a
    packet that fails this check then fails inside `ZmqLink.drain`'s existing broad
    `except` around decode and becomes a `Refused`, never reaching `_command` at
    all. **Finiteness is deliberately not checked here**: `nan`/`inf` are real
    numbers by this check and stay welfare's to refuse, via `_finite`, exactly as
    they already are -- this class carries the request, never a second validator,
    and `_finite`'s job is not being duplicated, only guarded against a type it was
    never written to accept.
    """

    at: float
    by: str
    confirmed: bool

    def __post_init__(self) -> None:
        # `bool` is an `int` subclass, so `isinstance(True, (int, float))` alone
        # would silently accept a wall instant of `1` where a person meant "yes".
        if isinstance(self.at, bool) or not isinstance(self.at, (int, float)):
            raise TypeError(
                f"a return's `at` must be a real number (a POSIX wall instant), "
                f"not {self.at!r}"
            )
        if not isinstance(self.by, str):
            raise TypeError(
                f"a return's `by` must be a string naming who sent it, not "
                f"{self.by!r}"
            )
        if not isinstance(self.confirmed, bool):
            raise TypeError(
                f"a return's `confirmed` must be exactly a bool, not "
                f"{self.confirmed!r} -- a truthy non-bool would silently satisfy "
                f"the confirmation check it exists to gate"
            )


Command = SetParameter | Stop | ReturnedToCage


def _encode_command(command: Command) -> bytes:
    """`SetParameter`/`Stop`/`ReturnedToCage` to msgpack, tagged by kind so
    `_decode_command` knows which dataclass to rebuild.

    Private, unlike `encode`/`decode`: `ZmqConsole.send` is the only caller, in this
    same file, so this is an implementation detail of the REQ/REP leg rather than a
    wire contract another module is meant to import.
    """
    import msgpack

    if isinstance(command, SetParameter):
        payload = {"kind": "set", "name": command.name, "value": command.value, "by": command.by}
    elif isinstance(command, Stop):
        payload = {"kind": "stop", "by": command.by}
    elif isinstance(command, ReturnedToCage):
        payload = {
            "kind": "returned",
            "at": command.at,
            "by": command.by,
            "confirmed": command.confirmed,
        }
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
    if kind == "returned":
        return ReturnedToCage(
            at=data["at"], by=data["by"], confirmed=data["confirmed"]
        )
    raise ValueError(f"unknown command kind on the wire: {kind!r}")


class Link(Protocol):
    #: Refusals this link produced itself, rather than `Session.set` -- a wire packet
    #: that could not be turned into a `Command`. **Part of the protocol, not an
    #: extension `ZmqLink` happens to carry**, and that is the whole point: it used to
    #: be reached through `getattr(link, "refused", ())`, so renaming it on `ZmqLink`
    #: would have made transport refusals disappear from telemetry with nothing
    #: raising. An implementation that cannot produce one answers with an empty
    #: sequence and says so, the way `dio.Absent` is explicit about having no card.
    refused: "list[Refused] | tuple[Refused, ...]"
    #: How many `refused` entries this link has already discarded to stay inside
    #: `REFUSAL_HISTORY`. Rolled into `Telemetry.refusals_dropped`.
    refused_dropped: int

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

    #: Always empty, and it is a statement rather than an oversight: `Absent` never
    #: sees wire bytes, so it can never fail to decode one. Declared here so that
    #: `Telemetry.of` can read `session.link.refused` outright -- see its docstring.
    refused: tuple = ()
    #: Always zero, for the same reason: nothing to keep, so nothing to discard.
    refused_dropped: int = 0

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
    #: See `Absent.refused` -- same reasoning. A queued command is handed over as an
    #: object, never as bytes, so nothing here can fail to decode. A test that needs
    #: transport refusals in telemetry can still put `Refused` rows in this list
    #: directly, which is what makes it a field rather than a constant.
    refused: list = field(default_factory=list)
    refused_dropped: int = 0

    def queue(self, command) -> None:
        self._queued.append(command)

    def publish(self, telemetry: Telemetry) -> None:
        self.published.append(telemetry)

    def drain(self) -> list[Command]:
        taken, self._queued = self._queued, []
        return taken


class RemoteBindRefused(Exception):
    """A `ZmqLink` was asked to bind somewhere other hosts can reach, without being
    told to. See `ZmqLink.__init__`'s `allow_remote`."""


#: Transports that cannot leave this machine whatever follows them, so binding on one
#: is never a remote bind. `inproc` is in-process; `ipc` is a Unix socket on the local
#: filesystem.
_LOCAL_TRANSPORTS = ("inproc://", "ipc://")


def _binds_beyond_this_machine(endpoint: str) -> bool:
    """Whether binding `endpoint` would accept connections from other hosts.

    **Refuses by defaulting to `True` on anything it does not understand**, which is
    the direction that fails loudly. A wildcard (`tcp://*:5571`), an interface name
    (`tcp://eth0:5571`) and a transport not in `_LOCAL_TRANSPORTS` all come back
    `True` rather than being parsed harder and guessed at: the cost of a wrong `True`
    is an operator passing one more flag, and the cost of a wrong `False` is an open
    port on the lab network that nobody chose.

    `ipaddress` rather than a string prefix, so the whole of 127.0.0.0/8 and `::1`
    count and `tcp://127.0.0.1.evil.example:5571` does not.
    """
    if endpoint.startswith(_LOCAL_TRANSPORTS):
        return False
    scheme, _, rest = endpoint.partition("://")
    if scheme != "tcp":
        return True
    if rest.startswith("["):  # tcp://[::1]:5571
        host, _, _ = rest[1:].partition("]")
    else:
        host, _, _ = rest.partition(":")
    if host == "localhost":
        return False
    try:
        return not ipaddress.ip_address(host).is_loopback
    except ValueError:
        return True


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

    Binds to `pub_endpoint`/`rep_endpoint`, **loopback only unless told otherwise**
    (see `__init__`) -- `tcp://127.0.0.1:0` asks the OS for an ephemeral port -- and
    `self.pub_endpoint`/`self.rep_endpoint` read back what ZeroMQ actually bound
    (`zmq.LAST_ENDPOINT`), which is what a `ZmqConsole` needs in order to connect.
    """

    def __init__(
        self, pub_endpoint: str, rep_endpoint: str, *, allow_remote: bool = False
    ):
        """Bind both sockets. **Loopback unless `allow_remote` says otherwise.**

        S9a §7 states the assumption this link runs on, in as many words: `taskd`
        trusts the actor named in a command *"because they are the same machine and
        the console **is** the authenticator."* Nothing enforced it. These two lines
        used to bind whatever string they were handed, so
        `wlx run --link tcp://0.0.0.0:5571,...` was accepted in silence, and after it
        any host on the lab network could move `reward_correct` or issue `Stop` under
        any `--as` name it cared to invent. The spec's premise was a sentence in a
        document and the code was a wildcard bind.

        A non-loopback endpoint is therefore refused here rather than bound, and
        `allow_remote=True` -- `wlx run --link-allow-remote` on the command line -- is
        how somebody says they meant it. It does not make a remote bind safe; it makes
        it deliberate, and it is the whole of what stands between this port and the
        network until real authentication exists.

        **That authentication is P4d-3's, and this is what it is waiting for**
        (CLAUDE.md: a "not yet" must name what it is waiting for). S9a §6 designs it:
        the box as an OAuth2 client of `wl-works`, `Actor` as `Verified(person,
        issuer, token id)` or `Local(box credential)` rather than the bare `by: str`
        this link carries today. Until that lands, `by` is whatever the sender typed,
        and a loopback-only bind is the only thing making that acceptable. Grep
        `P4d-3` when it does.

        `ZmqConsole` is deliberately not restricted the same way: it *connects*, and
        a console reaching a session on another host is a decision the console's own
        operator makes about where to look, not a port this process opens.
        """
        import zmq

        if not allow_remote:
            # Before the context, so a refusal leaves nothing to clean up.
            for role, endpoint in (("PUB", pub_endpoint), ("REP", rep_endpoint)):
                if _binds_beyond_this_machine(endpoint):
                    raise RemoteBindRefused(
                        f"refusing to bind the {role} endpoint on {endpoint!r}: it is "
                        f"reachable from other hosts, and a console link has no "
                        f"authentication yet -- `by` is whatever the sender typed, so "
                        f"any host that can reach this port can move a reward volume "
                        f"or stop the session under an invented name (S9a §6 designs "
                        f"the real thing; it is P4d-3's). Bind on loopback "
                        f"(tcp://127.0.0.1:PORT), or pass --link-allow-remote / "
                        f"allow_remote=True to say you meant it."
                    )

        self._ctx = zmq.Context()
        # A cleanup path that does not go through close() at all -- see close()'s
        # own docstring for why that matters and what it replaced.
        weakref.finalize(self, self._ctx.destroy, 0)

        # **Everything from here to the end of the binds is inside the `try`, and
        # that is not tidiness.** `bind` fails for ordinary reasons -- a port already
        # in use, an address this host has not configured -- and until this was here,
        # such a failure raised out of the constructor *after* the context and the
        # PUB socket existed and *before* any caller had a handle to close. The
        # context was then abandoned mid-construction, which is exactly the state
        # `close()`'s docstring says makes pytest's cyclic collector stop
        # terminating. Found by doing it: `tcp://127.0.0.2:0` is inside the loopback
        # block, so the `allow_remote` guard above lets it through, and a stock macOS
        # loopback has no such address -- the suite hung past 600 s.
        try:
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
        except BaseException:
            # `destroy(linger=0)`, the same call `close()` makes and for the same
            # reason -- it force-closes whichever sockets exist rather than needing
            # to know which ones got that far.
            self._ctx.destroy(linger=0)
            raise

        #: Wire packets `drain()` could not turn into a `Command`, as `Refused`
        #: entries -- see `drain()`'s docstring (fix round 1, CRITICAL 2). The
        #: transport-layer twin of `Session.refusals`, and **part of the `Link`
        #: protocol** rather than an extension only this class carries: `Absent` and
        #: `Simulated` answer with empties of their own, so `Telemetry.of` can read
        #: `link.refused` outright instead of through a `getattr` default that would
        #: hide a rename here.
        #:
        #: **Bounded at `REFUSAL_HISTORY`, newest kept.** This list is the one thing
        #: in this file whose length an untrusted peer decides; it used to grow
        #: forever, one entry per undecodable packet, with `Telemetry.of` re-encoding
        #: all of it at every trial boundary.
        self.refused: list[Refused] = []
        #: How many entries the trim in `drain()` has discarded. Published as part of
        #: `Telemetry.refusals_dropped` so a cap never reads as a quiet session.
        self.refused_dropped: int = 0

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

        **Bounded, and the bound is the point.** The paragraph above is the argument
        for recording every one of these, and it is also the reason the list cannot
        be allowed to grow: the peer producing them is the one this end does not
        control, and the newer-console-against-a-bumped-`SCHEMA` case named there
        produces one per packet for as long as it keeps trying. `self.refused` is
        trimmed to the most recent `REFUSAL_HISTORY` and the discards are counted in
        `self.refused_dropped`, so the cap is visible on the console rather than
        being a quieter version of the silent drop this whole passage argues against.
        The trim is O(`REFUSAL_HISTORY`) and this runs once per trial boundary, never
        inside a frame.
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
                if len(self.refused) > REFUSAL_HISTORY:
                    self.refused_dropped += len(self.refused) - REFUSAL_HISTORY
                    del self.refused[:-REFUSAL_HISTORY]
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
        `session.run()` alike.

        **The open item above is not "unrelated", the way this paragraph first
        said -- Task 6's own fix round 1 reproduced it, by hand, one file over,**
        which is why that claim is corrected here rather than left standing.
        `tests/test_cli.py`'s first end-to-end `--link` test built its own
        `ZmqLink`/`ZmqConsole` instances without `test_link.py`'s `zmq_cleanup`
        fixture, module-local at the time, and `tools/mutate.py --returns None
        wl_expcontroller/link.py close` hung past 300 s again -- measured, same
        command, only that test file differing from the commit one before it.
        That is independent confirmation the open item is a property of *any*
        unregistered `ZmqLink`/`ZmqConsole` left for pytest's cyclic collector
        while `close()` is neutered, not something specific to `test_link.py`'s
        own tests. Fixed by moving `zmq_cleanup` to `conftest.py` (shared across
        files rather than module-local) and, for the one `ZmqLink` this task's
        test has no handle to register -- the one `main()` itself builds and
        closes, entirely inside a background thread -- an explicit `gc.collect()`
        after that thread joins, forcing its cyclic collection under the test's
        own control rather than leaving it for pytest's. **The mechanism itself
        (why a collector pass specifically invoked as pytest's own, `gc_collect_
        main`, hangs where an explicit `gc.collect()` from a test does not) is
        still exactly as open as the paragraph above says.** Only "nothing calls
        `close()` in production" is resolved by this one.
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
