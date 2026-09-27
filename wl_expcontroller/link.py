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

from wl_expcontroller.welfare import DAILY_FLUID, OUT_OF_CAGE

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
#: 6 (2026-09-26, P4d-2a): `phase`, `stop_kind`, and -- added later in the same
#: slice, while schema 6 was still unreleased (Task 9) -- `in_session_seconds`, the
#: PI's second clock, apart from out-of-cage and bounding nothing. A console built
#: against 5 renders an awaiting-return frame's advancing clock as a running
#: session, and has no field at all for the in-session one.
#:
#: 7 (2026-09-26, P4d-2b b1): the configuration a session runs under (`task`,
#: `allocation`, `bounds_config`, `params`), the two limits its numbers are read
#: against (`floor_ml`, `out_of_cage_limit_s`), the frame's own instant (`wall_at`,
#: ledger Ruling 1, 2026-09-27), `last_reward_at` and `recent_outcomes`. Nothing
#: changed meaning. A reader built against 6 decodes a
#: schema-7 frame and ignores the additions; a schema-7 reader cannot decode a
#: schema-6 frame, which lacks them, and `wlx serve` says so on its page rather than
#: showing a guess (`serve.Server._listen`).
SCHEMA = 7

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

#: How many recent outcomes a `Telemetry` frame carries, oldest first: the browser
#: console's Runtime ticks (P4d-2b spec §4.1, "the last 60"). Capped for
#: `REFUSAL_HISTORY`'s reason -- a frame is re-encoded at every trial boundary -- and a
#: display bound, not a measurement.
RECENT_OUTCOMES = 60


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
class ParamRow:
    """One settable value, as the browser console's parameter pane shows it (P4d-2b
    spec §3: "the parameter row is generated from it").

    From `taskd.Session.parameters`: a task `Param` with its current value, or a
    welfare ceiling (`bounded=True`) over `[0, maximum]`. `value` is `None` when the
    task declares a parameter nobody set -- a console prints *unset*, never `0` --
    and may be a string for a categorical one.
    """

    name: str
    unit: str
    low: float | None
    high: float | None
    value: float | str | None
    bounded: bool


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
    #: `welfare.out_of_cage_seconds(wall_now)` -- **the clock the session's one
    #: duration ceiling is read against** (PI, 2026-09-19), read on the wall like the
    #: ceiling (P4d-2a spec §10) so that the console's number and the ceiling's are the
    #: same number. It was frame-derived for the same reason until then.
    #: `None` for a cage-side session, which declared it has no duration bound
    #: (`welfare.Deployment`); never `0.0`, which would read as a clock not started.
    out_of_cage_seconds: float | None
    #: `welfare.chair_seconds(wall_now)` -- restraint, **recorded and bounding nothing**
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
    #: `(session.ended_wall_at or wall_now) - session.opened_wall_at` -- the PI's
    #: second clock (P4d-2a spec §10 item 3), asked for beside out-of-cage and kept
    #: apart from it: "there should also be a in-session clock that is tracked
    #: seperately." **`None` before `open()`**, never `0.0`, for the reason every
    #: other absent clock on this frame is `None` -- a session that has not yet
    #: opened has no in-session interval to report, and `0.0` would say it has one
    #: that just started. **It bounds nothing** -- ruled "only shown and
    #: recorded" -- so `welfare` never sees `opened_wall_at`/`ended_wall_at` and no
    #: `must_stop`/`approaching_limit` reads it.
    in_session_seconds: float | None
    #: `session.spec.deployment.value` -- which of `welfare.Deployment`'s three kinds
    #: this session declared. On the wire rather than inferred from which fields are
    #: `None`, because `cli.render` promises to name a field per line and derive
    #: nothing, and because two kinds share one `None`.
    deployment: str
    #: `welfare.approaching_limit(wall_now)` -- the sentence the session would use as
    #: the out-of-cage ceiling comes into view (PI, 2026-09-20), or `None` while there
    #: is nothing to say. Read rather than recomputed, so the console's warning and
    #: the session's are the same statement and cannot drift.
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
    #: `session.spec.task` -- the task file this session loaded: S9a §3's
    #: configuration information (P4d-2b spec §3). Also in the config snapshot.
    task: str
    #: `session.spec.allocation`. Empty is the provisional allocation (`cli`).
    allocation: str
    #: `session.spec.bounds_config`: the bounded config's file. Empty when nobody
    #: named one, which a console says rather than filling in.
    bounds_config: str
    #: `session.parameters`, as `ParamRow`s: the task's declarations, then the welfare
    #: ceilings a console may stage (P4d-2b spec §3).
    params: tuple
    #: The day's fluid floor, `welfare.bounds.minima[DAILY_FLUID].value` -- what
    #: `fluid_today_ml` is read against. `Welfare` refuses a config without one, so it
    #: is never `None`.
    floor_ml: float
    #: The ceiling the out-of-cage clock runs against, `ceilings[OUT_OF_CAGE].value`
    #: -- the number `welfare.must_stop` compares with, not the maximum. `None`
    #: cage-side, where `Welfare` refuses a config that declares one.
    out_of_cage_limit_s: float | None
    #: **The frame's own instant**: the one `session.wall_now()` reading this frame
    #: was built at, POSIX seconds on the session's anchored clock -- the instant
    #: `out_of_cage_seconds`, `chair_seconds`, `in_session_seconds` and
    #: `duration_warning` describe (ledger Ruling 1, 2026-09-27). On the wire so a
    #: console ages a frame by its own steady clock from the frame's arrival, and
    #: never subtracts its host clock from a session instant, which parts from the
    #: session's anchor by any step of the host clock since the session began.
    wall_at: float
    #: `welfare.last_delivery_wall_at`: the instant the last reward was commanded,
    #: kept once the pump returns -- POSIX seconds on the session's anchored clock,
    #: or `None` before the first, never `0.0` (P4d-2b spec §4.1). A console reads it
    #: against `wall_at`, the same clock, never against its own.
    last_reward_at: float | None
    #: `session.recent_outcomes`: the last `RECENT_OUTCOMES` outcome strings, oldest
    #: first, exactly as `trials.jsonl` records them, `hang` included.
    recent_outcomes: tuple

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
        wall_now = session.wall_now()
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
        # Read, never decided: `Welfare` guarantees a rig session has this ceiling
        # and a cage-side one does not, so its absence is the cage-side case.
        limit = session.welfare.bounds.ceilings.get(OUT_OF_CAGE)
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
            # On the wall, read once above so these two and `duration_warning` below
            # are one instant (P4d-2a spec §10; Task 7 fix round 1). Never
            # `session.now()`: that is the frame clock, which times trials and which
            # `welfare` is given nowhere.
            out_of_cage_seconds=session.welfare.out_of_cage_seconds(wall_now),
            chair_seconds=session.welfare.chair_seconds(wall_now),
            # `session.opened_wall_at`/`session.ended_wall_at`, read as plain
            # attributes like `wall_now` above: the session's own clock, apart from
            # `welfare` entirely (P4d-2a spec §10 item 3) -- there is no method on
            # `welfare` to ask, because it bounds nothing and no `welfare` method
            # takes either instant. `None` before `open()`; `ended_wall_at` beats
            # `wall_now` once `end()` has run, so the frame that closes the clock
            # is also the last one it advances in.
            in_session_seconds=(
                None
                if session.opened_wall_at is None
                else (
                    session.ended_wall_at
                    if session.ended_wall_at is not None
                    else wall_now
                )
                - session.opened_wall_at
            ),
            deployment=session.spec.deployment.value,
            duration_warning=session.duration_warning(wall_now),
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
            # P4d-2b b1 (spec §3, §4.1). The configuration is the spec's -- what the
            # config snapshot records -- and the rest is `welfare`'s and the
            # session's own, read through their public surface.
            task=session.spec.task,
            allocation=session.spec.allocation,
            bounds_config=session.spec.bounds_config,
            params=tuple(ParamRow(*row) for row in session.parameters),
            floor_ml=session.welfare.bounds.minima[DAILY_FLUID].value,
            out_of_cage_limit_s=None if limit is None else limit.value,
            # The reading above, the one this whole frame describes (ledger Ruling 1).
            wall_at=wall_now,
            last_reward_at=session.welfare.last_delivery_wall_at,
            recent_outcomes=session.recent_outcomes,
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
        "in_session_seconds": telemetry.in_session_seconds,
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
        "task": telemetry.task,
        "allocation": telemetry.allocation,
        "bounds_config": telemetry.bounds_config,
        "params": [
            {
                "name": p.name,
                "unit": p.unit,
                "low": p.low,
                "high": p.high,
                "value": p.value,
                "bounded": p.bounded,
            }
            for p in telemetry.params
        ],
        "floor_ml": telemetry.floor_ml,
        "out_of_cage_limit_s": telemetry.out_of_cage_limit_s,
        "wall_at": telemetry.wall_at,
        "last_reward_at": telemetry.last_reward_at,
        "recent_outcomes": list(telemetry.recent_outcomes),
    }
    return msgpack.packb(payload, use_bin_type=True)


class FrameError(Exception):
    """A telemetry frame that arrived but could not be shown: bytes `decode` could
    not parse at all, or a field this schema's `Telemetry` needs that the payload
    did not carry. Raised by `decode`, and caught non-fatally wherever a frame is
    read (`serve.Server._listen`'s `Hub.reject`) -- **never a transport failure**,
    which is what ends the telemetry thread instead (fix round 1, I1's distinction:
    a `zmq.ZMQError` from a broken connection is not a `FrameError` and is left to
    propagate out of `_listen`'s per-frame `try` on purpose)."""


class SchemaMismatch(FrameError):
    """`decode` read a schema this build does not know how to read the rest of the
    frame for. Raised **before any other field is touched** (fix round 1, I3): a
    security review found a real schema-6 `wlx run` beside a schema-7 `wlx serve`
    raised `KeyError: 'task'` instead of naming the mismatch, because the old
    `decode` read fields in encoding order and only checked `schema` against every
    other field's `Telemetry(...)` call already having succeeded. This class is
    raised the moment `data["schema"] != SCHEMA` is known, so a frame from an older
    or newer build is refused by name every time, not only when its particular
    field layout happens to decode cleanly up to the point schema was checked."""

    def __init__(self, schema: object) -> None:
        self.schema = schema
        super().__init__(
            f"a telemetry frame carried schema {schema!r} and this console reads "
            f"schema {SCHEMA}, so it is not shown rather than guessed at"
        )


def decode(payload: bytes) -> Telemetry:
    """The inverse of `encode`, rebuilding `Staged`/`Refused` rather than leaving
    them as the plain dicts msgpack hands back.

    **`None` survives.** msgpack has a native nil, distinct from `0`/`0.0`, and
    `unpackb`'s default `raw=False` returns Python `str` rather than `bytes` for text
    -- so `fluid_today_ml`/`shortfall_ml`/`out_of_cage_seconds`/`chair_seconds`/
    `in_session_seconds` round-trip as `None` when that is what they were, never
    silently becoming a number. For the first two that is an unknown day; for the
    third it is a cage-side session that has no such interval, and a `0.0` on the
    wire would read as a clock that had not started; for the fourth it is a
    deployment that takes no head-fixation marks, where a `0.00` would report an
    animal as unrestrained that is sitting in a chair; for the fifth it is a
    session that has not called `open()` yet, where a `0.0` would read as a clock
    already running.
    See this module's docstring: an unknown
    day rendered as a confident `0.0` is exactly the failure `welfare.shortfall()`
    exists to prevent, and a console showing it would be the same failure one hop
    further downstream.

    **The schema is read and checked first, before any other field** (fix round 1,
    I3): see `SchemaMismatch`. Every other way this can fail -- bytes that are not
    msgpack at all, or a schema-matching payload still missing a field this schema's
    `Telemetry` needs -- raises `FrameError` too, so a caller can catch one type for
    "this frame is bad" without knowing `msgpack`'s or a dict's own exception
    classes. Raised, never returned: `wlx console` (`cli.py`) and `wlx serve`
    (`serve.Server._listen`) both call this directly and are the ones that decide
    whether "bad frame" is fatal for them.
    """
    import msgpack

    try:
        data = msgpack.unpackb(payload, raw=False)
    except Exception as exc:  # noqa: BLE001 -- any of msgpack's own exception types
        raise FrameError(
            f"a telemetry frame could not be decoded, so it is not shown: "
            f"{_describe(exc)}"
        ) from exc
    schema = data.get("schema") if isinstance(data, dict) else None
    if schema != SCHEMA:
        raise SchemaMismatch(schema)
    try:
        return _telemetry_from(data)
    except (KeyError, TypeError) as exc:
        raise FrameError(
            f"a telemetry frame could not be decoded, so it is not shown: "
            f"{_describe(exc)}"
        ) from exc


def _describe(exc: Exception) -> str:
    """`Type: message`, or `Type` alone when the exception carries no message (fix
    round 2, M-e): some of `msgpack`'s own exception classes (`FormatError` among
    them) raise with an empty `str(exc)`, and `f"{type(exc).__name__}: {exc}"`
    for one of those left a dangling `"FormatError: "` -- a trailing colon and
    space naming nothing, which reads as truncated rather than as "no message"."""
    message = str(exc)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _telemetry_from(data: dict) -> Telemetry:
    """The field-by-field rebuild `decode` used to do inline. Split out so `decode`
    can wrap only this part's `KeyError`/`TypeError` in `FrameError` -- the schema
    check above it must not be, since `SchemaMismatch` already is one."""
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
        in_session_seconds=data["in_session_seconds"],
        deployment=data["deployment"],
        duration_warning=data["duration_warning"],
        outcomes=data["outcomes"],
        hangs=data["hangs"],
        owed=data["owed"],
        staged=tuple(Staged(**s) for s in data["staged"]),
        refusals=tuple(Refused(**r) for r in data["refusals"]),
        refusals_dropped=data["refusals_dropped"],
        task=data["task"],
        allocation=data["allocation"],
        bounds_config=data["bounds_config"],
        params=tuple(ParamRow(**p) for p in data["params"]),
        floor_ml=data["floor_ml"],
        out_of_cage_limit_s=data["out_of_cage_limit_s"],
        wall_at=data["wall_at"],
        last_reward_at=data["last_reward_at"],
        recent_outcomes=tuple(data["recent_outcomes"]),
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

    **No `"returned"` kind (P4d-2a spec §10, Task 8).** `ReturnedToCage` lived here
    briefly (Task 4) and is gone: the PI ruled the wl-works ELN owns the return, not
    a console, so the browser will never send one and this file has nothing left to
    encode for it. A packet still tagged `"returned"` -- an old console build, or one
    that never got the memo -- reaches `_decode_command` below and is refused
    through the same unknown-kind path as any other kind this file does not
    recognize, never built into a command.
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
    """The inverse of `_encode_command`. `ZmqLink.drain` is the only caller.

    **`"returned"` is deliberately not a recognized kind** (P4d-2a spec §10, Task
    8): it falls through to the `unknown command kind` refusal below like any other
    kind this file does not implement, exactly as it would have before `Task 4`
    ever added it -- there is no special case for it here to keep it from being a
    special case.
    """
    import msgpack

    data = msgpack.unpackb(payload, raw=False)
    kind = data["kind"]
    if kind == "set":
        return SetParameter(name=data["name"], value=data["value"], by=data["by"])
    if kind == "stop":
        return Stop(by=data["by"])
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


def _release(ctx, sockets) -> None:
    """Close each of `sockets` with `linger=0`, then terminate `ctx`.

    This is how a `ZmqLink` or a `ZmqConsole` lets go of ZeroMQ, and it is the only
    way. Each object registers it with `weakref.finalize` before opening its first
    socket, and passes the context and its own list of sockets, which the constructor
    appends to as each one opens. It is reached four ways:

    - `close()` calls it directly, and detaches the finalizer only once it returns,
      so a release interrupted partway leaves the net armed (`ZmqLink.close`).
    - `ZmqLink.__init__` calls `close()` when its binds raise partway. Only
      `ZmqLink`'s constructor does: `ZmqConsole.__init__` has no `except`, and a
      half-built console is released by its finalizer when it is freed.
    - The finalizer runs it, at most once, when an object is freed without `close()`
      having run: by reference counting, the usual case, or by the cyclic collector,
      when the object is in a reference cycle.
    - `weakref.finalize`'s exit hook runs a finalizer still alive at interpreter exit.

    It is idempotent. A closed socket is skipped, and `destroy` returns at once on a
    closed context, so running it again after a completed or interrupted release does
    no harm. Nothing here runs per frame.

    **Why it holds the sockets itself (Ruling 18, 2026-09-27).** The net used to be
    `weakref.finalize(self, self._ctx.destroy, 0)`, and when the cyclic collector freed
    an unclosed object, that net deadlocked the collecting thread:

    - pyzmq's `Context.destroy` closes the sockets it finds in `Context._sockets`, a
      `WeakSet`, then calls `term()`. `term()` blocks until every socket in the context
      is closed.
    - The collector clears every weak reference to the objects it is about to free
      before it invokes any weakref callback. So by the time the finalizer ran, the
      sockets were already gone from that set. `destroy` closed nothing, and `term()`
      waited for two sockets that were still open.
    - Each socket's `Socket.__del__` would have closed it, but the collector runs
      `__del__` only after the callbacks return, on the same thread. So `term()` never
      returned.

    Measured: freed by reference counting, the old finalizer's `destroy` found 2 live
    sockets, and the process went on. Freed through a cycle, it found 0, and the
    process hung in `term` <- `destroy` <- `weakref.__call__`. That happened in a bare
    script with no pytest, and in this suite. The `*_released_by_the_collector*` tests
    in `tests/test_link.py` are that reproduction. The cycle is real: `taskd.Session`
    holds its `Rig`, the `Rig`'s `wall_clock` is a method bound to that session, and a
    `wlx run --link` session holds its `ZmqLink`. Every production construction uses
    `with`, so `close()` runs. But the net exists for the case where it did not, and
    in that case it hung the trial process.

    Sources: pyzmq 27.2.0, as installed in this repo's venv, read 2026-09-27.
    `zmq/sugar/context.py` has `Context.destroy`, which iterates `_sockets`, then
    `term()`, and its docstring's thread warning. `zmq/sugar/socket.py` has
    `Socket.__del__`, which calls `close()` if the socket is not closed.
    `zmq/backend/cython/_zmq.py` has `Context._term`, which calls `zmq_ctx_destroy`
    with the GIL released and does nothing on a closed context, and `Socket.close`,
    which does nothing on a closed socket. The collector's order is CPython 3.12.13's
    `Modules/gcmodule.c`: `handle_weakrefs` clears, then calls back, and
    `gc_collect_main` runs `finalize_garbage` after it. Read 2026-09-27.

    **What changed.** The finalizer's arguments are the context and the list of
    sockets. Never the object, and never a bound method of it: either would keep the
    object alive forever. **The strong reference is the mechanism.** The finalizer
    registry references the list, so the sockets stay reachable, the collector leaves
    them out of what it frees, and they stay in the context's `WeakSet` as well. The
    loop below, which closes them from the list, is belt and braces: with it removed,
    `destroy` alone would find and close them, for as long as the list is held
    (checked 2026-09-27, Ruling 19: all of `tests/test_link.py` passed without it).
    `destroy` then terminates the context, and returns at once on a context that is
    already closed, as one is after a test fixture destroyed it first.

    **So every socket must be appended to the list the moment it exists. That is
    required, not tidiness.** A socket missing from the list is held by nothing but
    its object. When the collector frees that object, the socket is freed with it:
    its `WeakSet` entry is cleared first, `destroy` cannot see it, and `term()` waits
    for it forever -- the original deadlock, back for that one socket. `destroy`'s
    own sweep of the `WeakSet` is a backstop for `close()` only, where the object is
    alive and the set is whole. This test pins it:
    `test_an_unclosed_link_in_a_reference_cycle_is_released_by_the_collector`. With
    the REP socket's `append` removed, it fails at its 10 s bound (checked
    2026-09-27, Ruling 19).

    **Threads.** pyzmq's `destroy` docstring says it must not be called while sockets
    are active in other threads, because `Socket.close` is not threadsafe. Each
    caller runs on a thread where that holds:

    - `close()` runs it on the thread that called `close()`, where `destroy` ran
      before.
    - `ZmqLink`'s failed constructor runs it, through `close()`, on the constructing
      thread, before any caller has a handle.
    - Reference counting runs it on the thread that dropped the last reference, and
      the collector on whichever thread collected. Either way the object is
      unreachable by then, so nothing can be using its sockets. Closing them on that
      thread is what each socket's own `__del__` would have done, on that same thread.
    - `weakref.finalize` also runs a still-live finalizer at interpreter exit, on
      the main thread, as it did for the old net.
    """
    for sock in sockets:
        if not sock.closed:
            sock.close(linger=0)
    ctx.destroy(linger=0)


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
        #: Every socket this link opens, appended the moment it exists. The finalizer
        #: below holds this list, not `self`, so what it releases stays reachable
        #: however this object is freed. **The append is required**: a socket left
        #: out of it brings back the collector deadlock. See `_release`.
        self._sockets: list = []
        # Registered before the first socket, so a constructor that raises partway
        # is covered too. It runs `_release` at most once, if this link is freed
        # without `close()` having run. `close()` runs `_release` itself and then
        # detaches it, and the `except` below goes through `close()`.
        self._finalizer = weakref.finalize(self, _release, self._ctx, self._sockets)

        # **Everything from here to the end of the binds is inside the `try`, and
        # that is not tidiness.** `bind` fails for ordinary reasons -- a port already
        # in use, an address this host has not configured -- and until this was here,
        # such a failure raised out of the constructor *after* the context and the
        # PUB socket existed and *before* any caller had a handle to close. The
        # context was then abandoned mid-construction, left to whatever freed the
        # object, which before `_release` could deadlock (see its docstring). Found
        # by doing it: `tcp://127.0.0.2:0` is inside the loopback block, so the
        # `allow_remote` guard above lets it through, and a stock macOS loopback has
        # no such address -- the suite hung past 600 s.
        try:
            self._pub = self._ctx.socket(zmq.PUB)
            self._sockets.append(self._pub)
            # LINGER=0 from creation, not only passed at close time: whenever this
            # socket is closed -- by close(), or by the finalizer above -- it cannot
            # block flushing a queued message, regardless of which path closed it.
            self._pub.setsockopt(zmq.LINGER, 0)
            self._pub.bind(pub_endpoint)
            self.pub_endpoint = self._pub.getsockopt_string(zmq.LAST_ENDPOINT)

            self._rep = self._ctx.socket(zmq.REP)
            self._sockets.append(self._rep)
            self._rep.setsockopt(zmq.LINGER, 0)
            self._rep.bind(rep_endpoint)
            self.rep_endpoint = self._rep.getsockopt_string(zmq.LAST_ENDPOINT)
        except BaseException:
            # `close()`, now, rather than when this half-built object is freed: it
            # closes whichever sockets got that far, and an interrupted release leaves
            # the finalizer armed here too.
            self.close()
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

        Runs `_release`: each socket is closed with `linger=0`, then
        `Context.destroy(linger=0)` terminates the context. Then it detaches this
        link's finalizer, so the finalizer never runs `_release` again. A second call
        runs `_release` again, and that does nothing: it skips closed sockets, and
        `destroy` returns at once on a closed context.

        **`destroy`, not a bare `.term()`** -- fix round 1, measured: `ctx.term()`
        blocks on ANY socket under that context that is not yet closed (a bare probe
        script, this session's scratchpad: an unclosed socket makes `term()` hang
        indefinitely), while `destroy(linger=0)`, called the same way from ordinary
        application code, force-closes every socket the context still lists and
        returns immediately (measured: 0.0001 s against the identical unclosed
        socket). So on this path, where the link is alive and the context's
        `WeakSet` is whole, `destroy` also closes a socket a future edit opened and
        forgot to append to `self._sockets`. **That is a backstop for `close()` only,
        and the append is still required.** When the collector frees a link whose
        `close()` never ran, a socket missing from the list brings the original
        deadlock back (`_release` has why), and
        `test_an_unclosed_link_in_a_reference_cycle_is_released_by_the_collector`
        fails at its 10 s bound.

        **`_release` first, `detach()` after (Ruling 19, 2026-09-27).**
        This used to be `self._finalizer()`, and `weakref.finalize.__call__` removes
        its registry entry *before* it calls `_release`. A release interrupted
        partway -- a Ctrl-C between the two `sock.close` calls, during `wlx run`'s
        `with` exit -- therefore disarmed the net: a second `close()` did nothing, and
        the context was never terminated. A later cyclic collection of that link then
        hung (reproduced 2026-09-27, in a bare script): pyzmq's own
        `Context.__del__` calls `destroy`, which finds the `WeakSet` already cleared,
        and `term()` waits for the socket the release never reached. Now the
        finalizer stays armed until `_release` has returned, so a second `close()`,
        or the finalizer when the link is freed, finishes the release. This test
        pins it:
        `test_a_close_interrupted_partway_leaves_the_net_armed_and_a_second_close_finishes`.

        **The open item this docstring carried until 2026-09-27 is closed (Ruling
        18).** It recorded that neutering `close()` hung the suite past 300 s inside
        the `weakref.finalize(self, self._ctx.destroy, 0)` callback `__init__` used
        to register, and it concluded that only *pytest's* cyclic collector did
        that, because an explicit `gc.collect()` in a bare script returned. Both
        halves were wrong. Any cyclic collection of an unclosed link hung that way,
        in a bare script too, and the bare scripts that returned had freed their
        objects by reference counting instead. The cause was the old finalizer:
        `destroy` looked for the sockets in a `WeakSet` the collector had already
        emptied, closed nothing, and `term()` waited on them forever. `_release`'s
        docstring has the mechanism, the pyzmq and CPython source it was read from,
        and the fix. The finalizer now holds the sockets itself.

        Not part of the `Link` protocol. **Resolved 2026-09-19 (Task 6):** this
        paragraph used to name `wlx run --link` as the "not yet" nothing called
        `close()` in production was waiting for (CLAUDE.md: a "not yet" must name
        what it is waiting for, so the next reader can grep it rather than believe
        it). `wlx run --link` (`cli.py`'s `run` command) now constructs the
        `ZmqLink` this method belongs to, wrapped in `with` rather than a bare
        `try`/`finally` so `close()` cannot be forgotten -- it runs via `__exit__`
        on every exit from that command, a normal return or an exception out of
        `session.run()` alike.

        **Task 6's own fix round 1 met the same hang one file over.**
        `tests/test_cli.py`'s first end-to-end `--link` test built its own
        `ZmqLink`/`ZmqConsole` instances without `test_link.py`'s `zmq_cleanup`
        fixture, module-local at the time, and `tools/mutate.py --returns None
        wl_expcontroller/link.py close` hung past 300 s again. That was fixed by
        moving `zmq_cleanup` to `conftest.py`, and, for the one `ZmqLink` the test
        has no handle to register -- the one `main()` builds and closes on a
        background thread -- by an explicit `gc.collect()` after that thread
        joined. The explicit collection was safe only while reference counting
        freed that link. Once `Rig.wall_clock` put it in a `Session` cycle (P4d-2b
        b1), the explicit collection became where the deadlock happened.
        `b85d0d7` replaced it with `tests/_zmq_release.py`, and `_release` removed
        the deadlock itself.
        """
        _release(self._ctx, self._sockets)
        self._finalizer.detach()

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

    def __init__(
        self,
        pub_endpoint: str,
        req_endpoint: str,
        settle_s: float = 0.05,
        receive_timeout_s: float = 5.0,
    ):
        import zmq

        self._ctx = zmq.Context()
        # Registered before the first socket, as in `ZmqLink.__init__`, and for a
        # reason that matters more here: nothing below is in a `try`, so a `connect`
        # that raises (`tcp://a b:5571`) leaves a half-built console no caller ever
        # holds. This finalizer is then what releases the socket that got made.
        self._sockets: list = []
        self._finalizer = weakref.finalize(self, _release, self._ctx, self._sockets)

        self._sub = self._ctx.socket(zmq.SUB)
        self._sockets.append(self._sub)
        self._sub.setsockopt(zmq.LINGER, 0)  # see ZmqLink.__init__ -- same reasoning
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")
        # `receive_timeout_s` is 5 s by default, the ceiling `wlx console` has always
        # had. `wlx serve`'s telemetry thread passes a short one so it can look between
        # receives at whether to stop, and `Server.close` returns promptly (P4d-2b b1).
        # A responsiveness choice either way, not a measurement.
        self._sub.setsockopt(zmq.RCVTIMEO, int(receive_timeout_s * 1000))
        self._sub.connect(pub_endpoint)

        self._req = self._ctx.socket(zmq.REQ)
        self._sockets.append(self._req)
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
        _release(self._ctx, self._sockets)
        self._finalizer.detach()

    def __enter__(self) -> "ZmqConsole":
        return self

    def __exit__(self, *exc_info: object) -> None:
        """See `ZmqLink.__exit__` -- same reasoning, same shape."""
        self.close()
