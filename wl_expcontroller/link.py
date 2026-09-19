"""The telemetry message a running session publishes to its consoles, and its schema.

S9a §6-§10 designs the console; **§9, "The telemetry contract," is what this file
implements.** This file currently holds `SCHEMA`, `Staged`, `Telemetry` and
`Telemetry.of` -- the message and the one function that fills it in. Later tasks in
this same slice add `Link`, the port a session publishes `Telemetry` through, and its
wire encoding (`encode`/`decode` in a transport module); grep this file for `Link` to
see whether they have landed yet.

**Not welfare-critical, and it must not become one.** `docs/design/architecture.md`
names `wl_expcontroller/bounds.py` and `wl_expcontroller/welfare.py` as the two
modules requiring human review before merge, "and nothing else" (CLAUDE.md). This file
carries no ceiling, no clock and no pump, and is deliberately not a third. It reads
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

from dataclasses import dataclass

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
        )
