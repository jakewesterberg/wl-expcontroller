"""The telemetry message a running session publishes to its consoles, and its schema.

S9a §6-§10 designs the console; **§9, "The telemetry contract," is what this file
implements.** This file currently holds `SCHEMA`, `Staged`, `Telemetry` and
`Telemetry.of` -- the message and the one function that fills it in. Later tasks in
this same slice add `Link`, the port a session publishes `Telemetry` through, and its
wire encoding (`encode`/`decode` in a transport module); grep this file for `Link` to
see whether they have landed yet.

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
            # to reach around.
            refusals=tuple(
                Refused(name=n, by=b, why=w) for n, b, w in session.refusals
            ),
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
