"""`taskd` — running a session end to end.

The pieces joined: a task loaded and checked, a world to run it against, blocks drawn
from a scheduler, ceilings that can end the session, and the record written as it
goes. On a rig the world is hardware; here it is a behaviour agent. **The loop cannot
tell them apart** (S6 §6), which is the property that makes a simulated session
evidence about a real one rather than a rehearsal of it.

**A session is the block session with one block.** A run of N trials is expressed as
a single unnamed block rather than as a second loop, because a second loop is a
second place for the ceilings to be checked -- and a limit enforced in one of two
paths is a limit that depends on which path a session took.

**Wired, not yet reachable.** `Session.link` drains commands into `Session.set` and
publishes telemetry, once per trial boundary and never per frame (below) -- but
nothing yet puts a second process on the other end of it. The ZMQ transport and `wlx
console` are later tasks in this same work package. There is also no preflight yet
beyond the two refusals below.

**Two refusals stand between a session and its first trial**, and both are the shape
this file exists to hold. A task with a blocking finding does not run, because a
session that begins and *then* discovers the task is malformed has already put an
animal in a chair. And a session that has not satisfied `welfare.preflight` does not
run: a rig session needs the mark that starts the twelve-hour out-of-cage clock (PI,
2026-09-19), and `Deployment.RIG_FIXED` additionally needs the head-fixation that
records restraint, while a cage-side one declares `Deployment.CAGE_SIDE` and needs
neither. The declaration is on `SessionSpec` rather than inferred, because a rig
session nobody marked and a kiosk session with nothing to mark are indistinguishable
to anything that guesses.

**Three deployment kinds since 2026-09-20 (PI)**, and this file is where two of the
consequences land: `head_released` is emitted at the end of a run only for the kind
that was fixed, and `link.Telemetry` carries the declaration so a console can say
which absence it is looking at. `welfare.Deployment` has the table.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from wl_expcontroller import link as _link
from wl_expcontroller.bounds import Bounds, Exceeded, _finite
from wl_expcontroller.check import check
from wl_expcontroller.cli import _clock, _load_allocation, _load_trial
from wl_expcontroller.codes import Allocation
from wl_expcontroller.dio import Absent as NoCard
from wl_expcontroller.record import EXPCONTROLLER_DIRNAME, SessionRecord, welfare_note
from wl_expcontroller.scheduler import Block, Condition, Scheduler
from wl_expcontroller.simulate import Census, Subject, Tally, prepare
from wl_expcontroller.run import run_trial
from wl_expcontroller.task import Entered, Exited, Outcome, Param, SaccadeTo, Trial
from wl_expcontroller.welfare import (
    OUT_OF_CAGE,
    WARN_WITHIN_DEFAULT,
    Absent as NoPump,
    Deployment,
    Rig,
    SessionClock,
    Welfare,
)

#: How long the paused loop waits for a console between its housekeeping passes --
#: draining commands, publishing a frame, and asking `welfare.must_stop` -- in
#: seconds (P4d-2b spec §5.1). The wait ends early when a mark or a command arrives
#: (`link.Link.idle`), so a resume or a stop is read as soon as it lands; this bounds
#: only how long a paused session goes between frames, and between limit checks,
#: when nothing arrives. A responsiveness choice, not a measurement of this system.
PAUSE_HOUSEKEEPING_S = 0.5


def _gap(later: float | None, earlier: float | None) -> float | None:
    """`later - earlier`, or `None` when either instant is unknown: a mark's gaps are
    recorded as the clocks read, and one nobody read is not a gap of zero."""
    if later is None or earlier is None:
        return None
    return later - earlier


def _next_occurrence(hhmm: str, wall: float) -> float:
    """The first instant after `wall` at which this host's local clock reads `hhmm`
    (P4d-2b spec §5.1: "the next occurrence of that time, within 24 hours").

    **`wall` is the session's anchored clock** (`Session.wall_now`), so a scheduled
    stop is read on the clock every welfare instant is on, and a host clock stepped
    mid-session moves it no more than it moves the out-of-cage limit. Local time is
    the host's zone, as the departure mark's clock time is (`cli._wall_clock_time`),
    and `time.mktime` with `tm_isdst=-1` lets the platform say whether daylight
    saving applies on the day, and rolls day 32 into the next month.

    **Exactly now counts as past**: `hhmm` read at 14:30:00 names tomorrow's 14:30,
    because the spec's occurrence is the next one. The schedule's own words then
    carry the date (`Session._schedule`), so the slip is read, not waited for."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    today = time.localtime(wall)
    for days in (0, 1):
        target = time.mktime(
            (today.tm_year, today.tm_mon, today.tm_mday + days, hour, minute, 0, 0, 0, -1)
        )
        if target > wall:
            return target
    # Unreachable: tomorrow's `hhmm` is after `wall` on every calendar day. Said
    # rather than looped past, so a platform where it is not fails here, by name.
    raise ValueError(f"no occurrence of {hhmm} after {wall} within a day")


@dataclass
class SessionSpec:
    """Everything a session needs before it starts.

    Deliberately a value: a session's inputs are the thing recorded in the config
    snapshot, so they exist as data before they exist as behaviour. The card and the
    pump are not here for that reason -- they are apparatus, not inputs, and a rig is
    not something a config snapshot can describe.
    """

    task: str
    allocation: str
    root: Path
    session_id: str
    subject: str
    trials: int
    frame_period: float
    seed: int
    values: dict
    #: The ceilings this session runs under. **Required**: a session with no bounded
    #: config is a session with no limits, and `Welfare` refuses one missing either
    #: of the two entries a session cannot be bounded without.
    bounds: Bounds
    #: What another deployment already delivered today (S8 §5.2b), from wl-works's
    #: `prepare-session`. **`None` leaves the day's shortfall unknown** rather than
    #: assuming zero -- and it does *not* stop the session paying the animal, because
    #: the daily figure is a floor rather than a ceiling (PI, 2026-09-06).
    already_delivered_today: float | None
    #: Which of the three deployment kinds this is. **Required, with no default**,
    #: because they differ in which welfare limits exist at all and in which marks
    #: the session may carry (`welfare.Deployment`), and a default would be a limit
    #: acquired -- or lost -- by omission.
    deployment: Deployment
    #: The session's plan. `None` means one block of `trials` trials, which is the
    #: same code path with one block in it.
    blocks: list[Block] | None = None
    #: How close to the out-of-cage ceiling the session starts warning, in seconds
    #: (PI, 2026-09-20). Defaulted rather than required, unlike the fields above,
    #: because it bounds nothing: the session ends at the same instant whatever it
    #: is. See `welfare.WARN_WITHIN_DEFAULT` for the figure and why it is a proposal.
    warn_within: float = WARN_WITHIN_DEFAULT
    #: Where `bounds` was loaded from, as the operator named it: S9a §3's "which
    #: bounded config" (P4d-2b spec §3). Written into the config snapshot beside the
    #: task and the allocation, and published from there. Empty when a caller built
    #: `Bounds` in code, as the tests do; a console then says *not given* rather than
    #: inventing a name.
    bounds_config: str = ""
    #: Rates per second, not per frame (S9/simulate). Roughly: acquires fixation
    #: within a few hundred ms, saccades to a target at a plausible latency, and
    #: breaks fixation about once every twenty seconds of holding.
    hazards: dict = field(
        default_factory=lambda: {
            Entered: 6.0,
            SaccadeTo: 5.0,
            Exited: 0.05,
        }
    )
    engagement: float = 0.85
    #: Per second, so a trial of a few seconds lapses occasionally.
    lapse: float = 0.15
    #: The gap between trials, in seconds, added to the frame clock (`Session.now()`)
    #: after each trial. The animal is out of its cage and in the chair for it, and
    #: the welfare clocks count it as they count everything: on the wall (P4d-2a
    #: spec §10), for however long it actually takes.
    iti: float = 0.5


@dataclass
class Session:
    """One subject's run: blocks, ceilings, a record, and the trial loop.

    `card` and `pump` default to the refusing implementations. That is not caution
    for its own sake -- a session whose card silently accepted every strobe would
    write a record that cannot be aligned to any recording, and a session whose pump
    silently accepted every delivery would work an animal for nothing. Both failures
    are invisible in every artifact the session produces.
    """

    spec: SessionSpec
    card: object = field(default_factory=NoCard)
    pump: object = field(default_factory=NoPump)
    #: Session time in seconds, **for timing trials and nothing else**. Defaults to a
    #: clock derived from frames, which is what makes a simulated session's trials
    #: deterministic; on a rig, frames *are* the clock. It is also where a recorded
    #: refusal is placed within the session (`record.SessionRecord.refusal`).
    #:
    #: **It is passed to `welfare` nowhere** (P4d-2a spec §10, 2026-09-26). It was
    #: every welfare duration's base until then, and a simulator counts frames
    #: without waiting for them, so it outran the wall the marks were taken on and
    #: the two disagreed -- the restraint cross-check refused a simulated rig
    #: session's first post-loop frame, and its return typed "now".
    clock: object = None
    #: The **wall** clock, in POSIX seconds, and a different base from `clock`. By
    #: default, the session's own `welfare.SessionClock`: `time.time()` as it read when
    #: the session was created, carried forward on a steady clock that counts the time
    #: the host is asleep -- see `wall_now`. **Every welfare duration is read from it**
    #: (P4d-2a spec
    #: §10): the marks an operator gives as clock times (PI, 2026-09-20), the
    #: head-fixation marks beside them, and the readings `out_of_cage_seconds`,
    #: `chair_seconds`, `must_stop` and `approaching_limit` are asked at. Injectable so
    #: that no test reads a real clock -- and so a simulated session that must stop at
    #: its out-of-cage ceiling deterministically is given a wall that advances with
    #: its frames, as `tests/test_taskd.py` does, rather than one that waits on this
    #: host.
    wall_clock: object = None
    #: Optional. `(trial, values, index) -> World`, called once per trial. Default:
    #: the behaviour agent. **This is the seam hardware plugs into** (S6 §6) -- until
    #: it existed, a session could only ever run against a simulated animal, and the
    #: claim that the loop cannot tell a world from a rig had no way to be exercised
    #: at the session level.
    world: object = None
    #: Optional. `(condition, values, result) -> None`, after each trial's outcome is
    #: recorded. What a calibration block collects its fixations through.
    observe: object = None
    #: Where consoles attach. Drained and published **once per trial boundary, never
    #: per frame** -- a socket call inside `run_trial` would put the network in the
    #: frame budget, which S9 §1 forbids in the sentence that makes the process split
    #: a hard rule. `Absent()` is a real configuration, not a stub: the cage-side kiosk
    #: runs unattended.
    link: object = field(default_factory=_link.Absent)
    welfare: Welfare = field(init=False)
    rig: Rig = field(init=False)
    allocation: Allocation = field(init=False)
    #: Why the session ended. Empty until it has.
    stopped_because: str = field(init=False, default="")
    #: Console commands refused rather than applied: `(name, by, why)`. See
    #: `_command` -- a person mistyping a parameter name is not a fault of the rig,
    #: and the session records the refusal and runs on rather than ending over it.
    #: **Capped at `link.REFUSAL_HISTORY`, newest kept**, for the same reason
    #: `ZmqLink.refused` is: the peer driving its growth is not the operator.
    refusals: list = field(init=False, default_factory=list)
    #: How many refusals fell off the far end of `refusals`. Rolled into
    #: `link.Telemetry.refusals_dropped`, so a cap can never read as a quiet session.
    refusals_dropped: int = field(init=False, default=0)
    blocks_run: list = field(init=False, default_factory=list)
    _elapsed: float = field(init=False, default=0.0, repr=False)
    _staged: list = field(init=False, default_factory=list, repr=False)
    _sequence: int = field(init=False, default=0, repr=False)
    _record: SessionRecord | None = field(init=False, default=None, repr=False)
    #: `""` until `run()` opens the record, then `running`; `await_return` moves it
    #: to `awaiting_return` and `closed` (P4d-2a). Published as `Telemetry.phase`.
    phase: str = field(init=False, default="")
    #: The kind of `stopped_because`: `completed`, `operator`, `limit` or `fault`.
    #: `operator` is a console's `Stop` or Ctrl-C at `wlx run`'s terminal.
    stop_kind: str | None = field(init=False, default=None)
    #: The last `link.RECENT_OUTCOMES` outcomes as the strings `trials.jsonl` records
    #: (`hang` for a trial with no outcome), oldest first (P4d-2b spec §4.1). Appended
    #: beside `record.trial`, from the one string both are given.
    _recent: deque = field(
        init=False,
        default_factory=lambda: deque(maxlen=_link.RECENT_OUTCOMES),
        repr=False,
    )
    #: The loop's own state, kept so a frame can still be built after it returns.
    _tally: Tally | None = field(init=False, default=None, repr=False)
    _scheduler: Scheduler | None = field(init=False, default=None, repr=False)
    _index: int = field(init=False, default=0, repr=False)
    #: The session's anchored wall clock, created with it: what `wall_now` reads when
    #: no `wall_clock` is injected. A `welfare.SessionClock`, and in the reviewed file
    #: rather than here since the P4d-2a final review (I5): it decides the interval.
    _anchored: SessionClock = field(init=False, repr=False)
    #: The session's own clock, apart from out-of-cage (P4d-2a spec §10 item 3).
    #: `None` until `open()`, a wall instant afterwards. **Bounds nothing** -- no
    #: `welfare` method reads either this or `ended_wall_at` -- and exists only to
    #: be shown and recorded, per the PI's own words on the ruling. See `open()`.
    opened_wall_at: float | None = field(init=False, default=None)
    #: `None` until `end()`, a wall instant afterwards. See `end()`.
    ended_wall_at: float | None = field(init=False, default=None)
    #: When a console paused the session, on the session's anchored clock, or `None`
    #: while trials run (P4d-2b spec §5.1). Set at the boundary the `Pause` was
    #: drained at, cleared by `Resume`; a session stopped while paused keeps it, as
    #: the truth of how it ended. Published as `Telemetry.paused_at`.
    paused_at: float | None = field(init=False, default=None)
    #: The consoles' changes feed: the last `link.CONTROL_HISTORY` control events as
    #: `(kind, by, at, said)`, oldest first -- see `controls`.
    _controls: deque = field(
        init=False,
        default_factory=lambda: deque(maxlen=_link.CONTROL_HISTORY),
        repr=False,
    )
    #: How many control events fell off the far end of `_controls`. Rolled into
    #: `Telemetry.controls_dropped`, so a cap can never read as a quiet session.
    controls_dropped: int = field(init=False, default=0)
    #: The scheduled stop, held here so a closed page cannot lose it (P4d-2b spec
    #: §5.1): `(kind, target, by, said)`, or `None`. `target` is an instant on the
    #: session's anchored clock (`clock`), a trial count (`trials`) or mL this
    #: session (`fluid`); `said` is its words, used by the feed, the strip and the
    #: stop reason alike. One at a time: a new schedule replaces it.
    scheduled_stop: tuple | None = field(init=False, default=None)
    #: `OPERATOR_MARK`'s code, looked up once when `run()` starts so the frame never
    #: searches the allocation; `None` when the allocation has none (P4d-2b b2a).
    _mark_code: int | None = field(init=False, default=None, repr=False)
    #: Marks stamped in a frame and not yet written: `(mark, frame, at, paused)`. The
    #: frame only appends; `_settle_stamps` writes them at the boundary after.
    _stamps: list = field(init=False, default_factory=list, repr=False)
    #: Every mark this session stamped, by its signal's number: `(number, trial,
    #: frame, at)`, what a note arriving later is joined to.
    _stamped: dict = field(init=False, default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._anchored = SessionClock()
        if self.spec.subject != self.spec.bounds.subject:
            # A dose error with a plausible-looking session behind it: every trial
            # row would say one subject while every limit came from another, and
            # nothing downstream compares the two.
            raise Exceeded(
                f"this session is for subject {self.spec.subject!r} and its bounded "
                f"config is for {self.spec.bounds.subject!r}; ceilings belong to an "
                f"animal, not to a rig"
            )
        self.allocation = _load_allocation(
            Path(self.spec.allocation) if self.spec.allocation else None
        )
        self.welfare = Welfare(
            bounds=self.spec.bounds,
            pump=self.pump,
            already_today=self.spec.already_delivered_today,
            deployment=self.spec.deployment,
            warn_within=self.spec.warn_within,
        )
        # `wall_now`, the one clock every welfare instant is read on (P4d-2a spec §10,
        # Ruling 8): `self._anchored`, the session's `SessionClock`, unless a test
        # injected `wall_clock`. Not `self._anchored.now` itself, which would skip an
        # injected wall, and a bound method, so a wall injected after construction is
        # the one read.
        self.rig = Rig(card=self.card, welfare=self.welfare, wall_clock=self.wall_now)

    # --- the clock --------------------------------------------------------

    @property
    def directory(self) -> Path:
        """Where this session's files go. The record's directory, so anything a
        session derives at close lands beside the record it derives from."""
        return Path(self.spec.root) / self.spec.session_id / EXPCONTROLLER_DIRNAME

    def now(self) -> float:
        if self.clock is not None:
            return self.clock()
        return self._elapsed

    def wall_now(self) -> float:
        """The wall clock, in POSIX seconds -- a different base from `now()`.

        **The one clock every welfare call is given** (P4d-2a spec §10), during the
        loop and after it alike: there is no mapping between bases to switch on
        `phase`, because nothing welfare reads is on the frame clock. An injected
        `wall_clock` is used as it is. See `wall_clock`.

        **Otherwise it is the session's `welfare.SessionClock`**, created with the
        session: `time.time()` as it read then, carried forward on a steady clock
        (Ruling 8, Task 7 fix round 1). A host clock stepped mid-session, by NTP or by
        a person, cannot move the interval, and since the P4d-2a final review (I1)
        **neither can the host going to sleep**: the steady clock counts a suspend
        on Linux and macOS, where `time.monotonic()`, which this read until then,
        does not. So out-of-cage is departure to return in steady seconds, the time
        asleep included, however the host clock moves in between.
        `welfare.steady_seconds` has the sources for each platform and the fallback
        elsewhere; `welfare.SessionClock` has the cost of anchoring, and why `wlx run`
        reads the return's `now` from here. Both live in the reviewed file because
        this reading decides the interval (I5).
        """
        if self.wall_clock is not None:
            return self.wall_clock()
        return self._anchored.now()

    def duration_warning(self, wall_now: float) -> str | None:
        """What an operator must be told about the time left out of the cage.

        `approaching_limit`'s sentence, as during the loop. **After the loop, past the
        limit, `must_stop`'s** (P4d-2a spec §4): there is no loop left to stop, and
        the warning is what tells someone the animal is still out.

        **At `wall_now`, the caller's reading, not one of its own** (Task 7 fix round
        1): `link.Telemetry.of` reads the wall once per frame and hands the same
        instant to this and to both durations, so a frame's warning and the clocks
        printed beside it describe one moment rather than two.

        **`None` once the return is recorded, whatever `phase` says** (P4d-2a final
        review I2): the animal is home, and no sentence about bringing it back, or
        about it still being out, is true of it. Asked of `welfare` rather than of
        `phase`, because a return recorded on the terminal's thread lands before
        `await_return` moves `phase` to `closed`, and the frame published in between
        used to carry `must_stop`'s "recorded as back in its cage" as a warning.
        """
        if self.welfare.returned_wall_at is not None:
            return None
        warning = self.welfare.approaching_limit(wall_now)
        if warning is None and self.phase == "awaiting_return":
            warning = self.welfare.must_stop(wall_now)
        return warning

    # --- out of cage, and restraint ---------------------------------------

    def _note(self, kind: str, at: float, by: str, how: str, reason: str = "") -> None:
        """One mark row in `welfare_notes.jsonl` (P4d-2a spec §3).

        Written by the mark methods themselves, so every caller leaves the same row
        and none can reach the mark around it. Since P4d-2a spec §10 the one caller
        in production is `wlx run` (its terminal prompts, and the process itself for
        `session opened`/`session ended`/`return not recorded`); no console or
        browser marks either end of the interval, and the wl-works ELN's marks will
        reach this box through the lab-host protocol, not `link.py`. `was` and `now`
        are both the mark's instant: nothing was amended, so there is one value to
        record.

        **Called only after `welfare` has accepted the mark, never before**, so a mark
        that never happened cannot be logged as having happened. That ordering has a
        cost: if this write itself fails -- disk full, permission -- the exception is
        `record.welfare_note`'s own, not `Exceeded`, and it propagates unchanged. It is
        never caught and retried here or by any caller in this module, because a retry
        would call `welfare.left_cage`/`welfare.returned_to_cage` a second time and be
        refused by that mark's own sentence ("already recorded as back in its cage"),
        leaving memory certain and the file still empty with no path back to matching
        them. A failed write is therefore spec §3's "killed outright" case in
        disguise -- the missing row downstream is the signal, exactly as it is when
        nothing runs at all.
        """
        welfare_note(
            self.directory,
            kind=kind,
            subject=self.spec.subject,
            was=at,
            now=at,
            reason=reason,
            by=by,
            how=how,
            recorded_at=self.wall_now(),
        )

    # --- the in-session clock -----------------------------------------------

    def open(self, how: str = "terminal") -> None:
        """Start the session's own clock: the session opened to the session ended,
        on the wall, apart from out-of-cage (P4d-2a spec §10 item 3).

        **It is the PI's own second clock, asked for beside out-of-cage**: "there
        should also be a in-session clock that is tracked seperately." Ruled "only
        shown and recorded" -- **it bounds nothing**, so no `welfare` method takes
        `opened_wall_at` or reads it anywhere. Written to `welfare_notes.jsonl`
        beside `departure` and `returned` because that file already holds the
        session's clock marks, not because this row bounds anything the way they do.

        **Needs no open record**, exactly as `_note` documents: `welfare_note`
        creates `self.directory` itself, so this can run, and does for `wlx run`,
        before `SessionRecord.open()` and before the departure is even asked about.

        **A second call raises.** A session's own clock has one start; calling this
        twice would leave two `session opened` rows on record for one session and
        `in_session_seconds` would have no way to say which `opened_wall_at` it
        meant.

        `run()` calls this itself when nothing already has, so a direct API user
        gets the clock too, without needing to know to ask for it. `wlx run` calls
        it explicitly, right after building the `Session` and before the departure
        is marked, so `session opened` is the first row a run ever writes.
        """
        if self.opened_wall_at is not None:
            raise RuntimeError(
                "session.open() called twice: a session's own clock starts once, "
                "and a second start would leave two 'session opened' rows for one "
                "session with no way to say which opened_wall_at is meant"
            )
        self.opened_wall_at = self.wall_now()
        self._note("session opened", self.opened_wall_at, "", how)

    def end(self, how: str = "terminal") -> None:
        """Stop the session's own clock. See `open()` for what it is and why.

        **Refuses before `open()`**: there is no clock running to stop, and ending
        one that was never started would put an `ended_wall_at` before an
        `opened_wall_at` nobody has, in `in_session_seconds`'s subtraction (this
        method's own inverse mistake). **Refuses a second call** for the same
        reason `open()` does: one ending, one instant, one row.

        For `wlx run`, called once from `cli.main`'s outer `finally` (Task 9 fix
        round 1), which wraps everything from `open()` on: after the return is
        settled or recorded as not recorded when the run got that far, and after
        a refused or interrupted departure when it did not. Whichever way the
        run left, the session's own clock closes with it.
        """
        if self.opened_wall_at is None:
            raise RuntimeError(
                "session.end() called before session.open(): there is no "
                "in-session clock running to stop"
            )
        if self.ended_wall_at is not None:
            raise RuntimeError(
                "session.end() called twice: a session's own clock ends once, "
                "and a second end would leave two 'session ended' rows for one "
                "session with no way to say which ended_wall_at is meant"
            )
        self.ended_wall_at = self.wall_now()
        self._note("session ended", self.ended_wall_at, "", how)

    # --- out of cage, and restraint ---------------------------------------

    def left_cage(
        self, at: float, confirmed: bool = False, by: str = "", how: str = "terminal"
    ) -> None:
        """The terminal's action that starts the clock bounding this session.

        **Not a console's** (residual fix round, correcting a stale docstring): the
        PI ruled the wl-works ELN owns the interval, not a console, so this is called
        only from `wlx run`'s own terminal (`cli.main`), which is the stand-in until
        the ELN exists (P4d-2a spec §10).

        **`at` is a wall-clock instant, in POSIX seconds** (PI, 2026-09-20): a clock
        time is what an operator reads. This hands `welfare.left_cage` the wall
        reading beside it, and `welfare` keeps the departure as the wall instant it
        is (P4d-2a spec §10). It also handed over `now()`, the frame clock, until
        then, for a mapping between the two bases that `welfare` no longer makes; a
        caller doing its own arithmetic between them was how a plain zero once made
        out-of-cage time equal chair time.

        **Deliberately not event-coded** (PI, 2026-09-20, closing S8 open item 8):
        the marks are operator-entered rather than measured, so a hardware timestamp
        would add precision to a number that never had it, and our own log and the
        session directory already carry them. The consequence he accepted is that a
        restart re-asks a person for the departure time.

        **It writes the `departure` row itself** (P4d-2a spec §3), once `welfare` has
        accepted the mark, so a refused departure leaves no row.
        """
        self.welfare.left_cage(at, wall_now=self.wall_now(), confirmed=confirmed)
        self._note("departure", at, by, how)

    def departure_needs_confirmation(self, at: float) -> str | None:
        """What a person must be shown before `left_cage(at)` is called, or `None`.

        **Asked before the mark, never after** (PI, 2026-09-20): `welfare.left_cage`
        refuses a second mark, so an amendment has nowhere to go once the first one
        has landed. It moves nothing, which is what makes asking first safe.

        Here for the reason `left_cage` is: `wall_now()` is this object's seam onto
        the wall clock, and a caller reading `time.time()` for itself would read the
        host clock rather than the session's anchored wall (Ruling 8) -- the two part
        by any adjustment of the host clock since the session was created.
        """
        return self.welfare.departure_needs_confirmation(at, wall_now=self.wall_now())

    def return_needs_confirmation(self, at: float) -> str | None:
        """What a person must be shown before `returned_to_cage(at)`, or `None`.

        `wlx run`'s terminal return prompt is this method's one caller (P4d-2a spec
        §10, Task 8) -- not a console: the PI ruled the wl-works ELN owns the
        interval. `wall_now()` is this object's seam onto the wall, for the reason
        `departure_needs_confirmation` gives.
        """
        return self.welfare.return_needs_confirmation(at, wall_now=self.wall_now())

    def amend_mark(
        self, what: str, original: float, amended: float, reason: str, by: str
    ) -> None:
        """The terminal's action that goes with the confirmations above, called from
        `wlx run` or `cli._settle_departure` -- not a console (see `left_cage`).

        Records the amendment and refuses a blank reason or actor; the caller then
        takes the amended value with `left_cage` or `returned_to_cage`, which apply
        every refusal the original would have met. The durable row is the caller's to
        write (`record.welfare_note`) -- see `welfare.amend_mark` for why it is not
        written from inside the welfare-critical file.
        """
        self.welfare.amend_mark(
            what, original=original, amended=amended, reason=reason, by=by
        )

    def returned_to_cage(
        self, at: float, confirmed: bool = False, by: str = "", how: str = "terminal"
    ) -> None:
        """The animal is home. **`at` is a wall-clock instant** (PI, 2026-09-20).

        **Not called by `run()`**, because it is not true when the loop ends: the
        session finishes, then the animal is released, unchaired and walked back,
        and every one of those seconds is inside the limit -- **and since ruling 4
        they are counted**, because the mark is read from the wall rather than from
        the frame clock that stopped with the loop. `welfare` refuses this while the
        animal is still recorded as head-fixed, so it cannot be used to freeze the
        clock mid-session -- release the head, or send a `Stop`.

        **No lock around this any more** (P4d-2a spec §10, Task 8). It ran under
        `_mark_lock` while a console could offer the return from the trial loop's own
        thread and race the terminal for it; the PI ruled the wl-works ELN owns the
        return, not a console, so `link.py` carries no such command any more and
        `cli._settle_return` -- the terminal, and only the terminal -- is this
        method's one caller in production, one attempt at a time. `_mark_lock` is
        removed along with it rather than kept for a race that can no longer happen.
        """
        wall_now = self.wall_now()
        # Asked before the mark, deliberately, so there is an answer to decide
        # afterwards whether a `return confirmed` row is owed; `welfare` asks the
        # same question again inside `returned_to_cage`, to refuse an unconfirmed
        # far return.
        far = self.welfare.return_needs_confirmation(at, wall_now)
        self.welfare.returned_to_cage(at, wall_now=wall_now, confirmed=confirmed)
        self._note("returned", at, by, how)
        if far is not None:
            self._note("return confirmed", at, by, how)

    def return_not_recorded(self, why: str) -> None:
        """Say in the record why the interval was left open (P4d-2a spec §3).

        A process killed outright cannot write this, and then the missing `returned`
        row is the signal; every other way of ending without a return says why.
        """
        self._note("return not recorded", self.wall_now(), "", "wlx run", reason=why)

    def head_fixed(self, at: float) -> None:
        """The action `wlx run` takes, S8 §5.2 requires, before a `RIG_FIXED` session
        starts -- not a console's: called from `cli.main` itself, never asked for.

        Event-coded at both ends, because restraint has no hardware line: the codes
        *are* its durable record, and an offline reader recovers chair time from the
        sync box's capture of them rather than from anything of ours that a crash
        took with it. Chair time stopped bounding the session on 2026-09-19; that is
        why it is still recorded.

        **`welfare.head_fixed` refuses the other two deployment kinds** (PI,
        2026-09-20), which is what keeps `4128`/`4129` out of a stream that has no
        head-fixation to record -- the refusal is there rather than here so the one
        rule has one home.

        **`at` is a wall instant, in POSIX seconds** (P4d-2a spec §10), the base the
        out-of-cage marks are in, so chair time and out-of-cage time are two
        intervals on one clock. `wall_now()` is the reading for a mark taken as it
        happens.
        """
        self.welfare.head_fixed(at)
        self.card.emit(self.allocation.code_for("HEAD_FIXED"))

    def head_released(self, at: float) -> None:
        """The closing restraint mark; `at` is a wall instant, as `head_fixed`'s is."""
        self.welfare.head_released(at)
        self.card.emit(self.allocation.code_for("HEAD_RELEASED"))

    # --- the live parameter path ------------------------------------------

    def set(self, name: str, value: float, by: str) -> None:
        """The one validated write path, whatever the origin (S8 §3.3).

        **Validated now, applied at the next trial boundary -- every name alike**
        (PI, 2026-09-19). A value is refused at the moment it is offered, so the
        console hears about it while a person is still looking; nothing is assigned
        here, so no trial is ever re-priced under way.

        Two vocabularies, deliberately: a **welfare-bounded** name is checked by
        `bounds.validate` against its ceiling, and an ordinary one against the task's
        own `Param` declaration. Reward volume is in the first, which is why the
        console can adjust it and cannot exceed it. Both then go on `_staged` and
        both are applied by `_apply_staged()` at the top of the pass *after* the one
        that drained them (S8 §3.2: a parameter that changed under a running trial
        makes that trial's record a description of neither value).
        `test_a_queued_commands_staged_value_is_visible_before_it_applies` and
        `test_a_welfare_bounded_change_applies_at_the_next_boundary_like_any_other`
        pin the two halves: trial 0 runs under the old value either way.

        **A welfare-bounded name used to be different, and that is what this fixed.**
        `bounds.set` was called here, as the command was drained, so the new volume
        was live for the trial that ran later in that same pass -- `run()` drains,
        publishes, and only then calls `run_trial` -- while `link.Staged` reported it
        `staged` and the `PARAM_CHANGED` strobe and `parameter_changes.jsonl` row
        landed a pass later still. The ceiling held throughout, so it was never
        over-delivery; it was **fluid attribution off by one trial**, and anyone
        reconciling commanded fluid against that file offline assigned one trial's
        delivery to the wrong value. Deferring costs an operator who has just lowered
        a volume one more trial at the old one, which the PI weighed and chose.
        `bounds.validate` carries the welfare-side account of the same change.

        **`was` is the value before this ITI, not before this row.** Two sets of one
        name in a single drain both record the same `was`, because neither has been
        applied when the second is staged -- so the rows read `0.15 -> 0.30` and
        `0.15 -> 0.20` and the second wins (S9a §8's last-write-wins, both actors
        recorded). A reader must take the last row's `now` for the interval and must
        not chain or sum them; a bounded name is the one where doing so would
        mis-attribute fluid, which is the thing this method was changed to stop.
        """
        if name in self.spec.bounds.ceilings:
            # M8 (P4d-2b b2a): a ceiling takes a number. A word reached
            # `bounds._finite` and raised `TypeError` out of this method, which
            # `run()`'s fault handler turned into the end of the session; `True`
            # was accepted as 1.0. Refused here, before `bounds` is asked, with the
            # sentence a console shows.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Exceeded(
                    f"{name!r} is a welfare ceiling and takes a number; {value!r} is "
                    f"not one, so it is refused and the previous value stands"
                )
            # Checked here, assigned by `_apply_staged()` -- `bounds.validate` moves
            # nothing. An ordinary parameter's checks below are the same shape.
            self.spec.bounds.validate(name, value)
            self._staged.append(
                (name, self.spec.bounds.value(name), value, by, True)
            )
            return

        declared = self._params().get(name)
        if declared is None:
            raise Exceeded(
                f"{name!r} is not a parameter this task declares, so it is refused "
                f"rather than created; a typo accepted here runs the old value while "
                f"the console shows the new one"
            )
        if not declared.live:
            raise Exceeded(f"{name!r} is declared not live-editable by this task")
        if declared.choices:
            if value not in declared.choices:
                raise Exceeded(f"{name!r} may only be one of {declared.choices}")
        else:
            # M8 (P4d-2b b2a): a numeric parameter takes a number, and a word used
            # to reach `_finite` below and raise `TypeError` instead of this
            # sentence. `bool` is refused although Python counts it as an `int`.
            # A categorical parameter skips the numeric checks: its value is one of
            # its choices, which may be words, and `_finite` raised on those too.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Exceeded(
                    f"{name!r} takes a number ({declared.unit}); {value!r} is not "
                    f"one, so it is refused and the previous value stands"
                )
            # **The same hole as the welfare path, on the task's own declaration.**
            # The range check below is two ordered comparisons, and `nan` is
            # `False` against both -- so a declared range accepts a value no range
            # contains. This is not a welfare-critical file and a `nan` fixation
            # window is a broken trial rather than a hurt animal, but it is the
            # identical defect and it enters from the identical place: a console
            # over the wire, or `--set` on a command line. `bounds._finite` is the
            # same guard the ceilings use.
            _finite(f"{name!r}", value)
            low, high = declared.low, declared.high
            if (low is not None and value < low) or (high is not None and value > high):
                raise Exceeded(
                    f"{name!r} is declared over [{low}, {high}] {declared.unit} and "
                    f"{value} is outside it"
                )
        self._staged.append((name, self.spec.values.get(name), value, by, False))

    @property
    def staged(self) -> tuple:
        """Every accepted change not yet applied: `(name, was, now, by, bounded)`,
        the exact shape `link.Telemetry.of` reads to build its `Staged` rows.

        **"Not yet applied" is true of every row, bounded or not** (PI, 2026-09-19).
        It was true of only the ordinary ones until then: a bounded row's value had
        already been moved on the ceiling by `set()` and was live for the trial that
        ran later in the same pass, while this property's name said otherwise on
        every attached console. `bounded` now says which *vocabulary* the name
        belongs to -- a welfare ceiling or the task's own `Param` -- and no longer
        says anything about when it lands.

        The public face of `_staged`. `link.py` reaches `Session` only through its
        declared surface, never a private attribute -- this is what makes that true
        rather than merely stated.
        """
        return tuple(self._staged)

    @property
    def recent_outcomes(self) -> tuple:
        """The last `link.RECENT_OUTCOMES` outcome strings, oldest first -- the public
        face of `_recent`, for the reason `staged` is public."""
        return tuple(self._recent)

    @property
    def controls(self) -> tuple:
        """The recent control events a console's changes feed lists, as `(kind, by,
        at, said)`, oldest first (P4d-2b spec §5.1): `stop`, `pause`, `resume`, and
        -- from the tasks that add them -- `mark`, `note`, `schedule`, `cancel`,
        `scheduled_stop` and `set` (a staged setting applied). `at` is the session's anchored clock; `said` is the
        sentence a console shows after the kind. The public face of `_controls`,
        for the reason `staged` is public; the session record keeps every one."""
        return tuple(self._controls)

    @property
    def parameters(self) -> tuple:
        """Every settable value a console shows, as `(name, unit, low, high, value,
        bounded)` -- the shape `link.Telemetry.of` builds its `ParamRow`s from (P4d-2b
        spec §3: "the parameter row is generated from it").

        The task's own `Param` declarations first, in declaration order, each with
        its value in `spec.values` (`None` when nobody set it); then every welfare
        ceiling a console could stage through `set`, bounded, over `[0, maximum]` --
        a ceiling's value is a magnitude (`bounds._magnitude`), so zero is its floor.

        **Not the out-of-cage ceiling.** It is the limit the session's clock runs
        against, published as that (`Telemetry.out_of_cage_limit_s`); a parameter
        card for it would set the duration limit beside a fixation hold as though it
        were a task setting.
        """
        declared = tuple(
            (p.name, p.unit, p.low, p.high, self.spec.values.get(p.name), False)
            for p in self._params().values()
        )
        ceilings = tuple(
            (name, ceiling.unit, 0.0, ceiling.maximum, ceiling.value, True)
            for name, ceiling in self.spec.bounds.ceilings.items()
            if name != OUT_OF_CAGE
        )
        return declared + ceilings

    def _control(
        self,
        kind: str,
        by: str,
        feed: str,
        index: int,
        at: float | None = None,
        **detail: object,
    ) -> float:
        """One control event: onto the changes feed, saying `feed`, and into the
        session record, at `at` on the session's anchored clock -- now, unless the
        event was stamped earlier (a mark, in its frame) -- which it returns (P4d-2b
        spec §5.1). `index` is the trial it happened in or, between trials, the trial
        about to run; `detail` is the record row's own fields."""
        if at is None:
            at = self.wall_now()
        if len(self._controls) == self._controls.maxlen:
            self.controls_dropped += 1
        self._controls.append((kind, by, at, feed))
        if self._record is not None:
            self._record.control(kind, by, at, index, **detail)
        return at

    def _code(self, name: str) -> int | None:
        """The code this session's allocation gives a framework event, or `None` when
        it gives none. `Allocation.code_for` refuses rather than inventing a number;
        a control that needs a code it does not have refuses in its turn (`_pause`),
        rather than raising out of the loop."""
        try:
            return self.allocation.code_for(name)
        except KeyError:
            return None

    def _pause(self, by: str, index: int) -> None:
        """Hold the session at this boundary (P4d-2b spec §5.1): `run()` enters
        `_hold` before the next trial. Strobed now, so the recording shows where the
        gap begins.

        **Refused, with the sentence, when it would not hold a session that can
        resume and be seen to**: a session already stopping -- a `Stop` drained
        ahead of this in the same pass (Review Focus 3) -- one already paused (a
        double click), or an allocation without both `PAUSE` and `RESUME`, which
        would leave a gap in the recording with an end nobody could find."""
        if self.stopped_because:
            self._refuse(
                "pause",
                by,
                f"the session is stopping ({self.stopped_because}); a pause is not "
                f"applied",
            )
            return
        if self.paused_at is not None:
            self._refuse(
                "pause",
                by,
                "the session is already paused; this pause changes nothing",
            )
            return
        codes = {name: self._code(name) for name in ("PAUSE", "RESUME")}
        missing = [name for name, code in codes.items() if code is None]
        if missing:
            self._refuse(
                "pause",
                by,
                f"this session's allocation has no {' or '.join(missing)} event code, "
                f"so the recording could not show the pause; it is refused",
            )
            return
        self.card.emit(codes["PAUSE"])
        self.paused_at = self._control("pause", by, f"paused at trial {index}", index)

    def _resume(self, by: str, index: int) -> None:
        """End the pause: `_hold` returns and `run()` goes back to the top of its
        loop, which applies whatever was staged while paused before the next trial
        runs (spec §5.1). Strobed, so the recording shows where the gap ends.

        **Refused when a stop is already on its way**: mirroring `_pause`'s guard,
        a `Stop` drained ahead of this in the same pass ends the session at that
        boundary regardless, and a resume here would strobe `RESUME`, write a
        "resumed" row for a pause that never ended, and clear `paused_at` on a
        session `_hold`'s field contract says should keep it, as the truth of how
        it ended (Important review item 1)."""
        if self.stopped_because:
            self._refuse(
                "resume",
                by,
                "the session is already stopping, so a resume changes nothing",
            )
            return
        if self.paused_at is None:
            self._refuse("resume", by, "the session is not paused; this resume changes nothing")
            return
        self.card.emit(self.allocation.code_for("RESUME"))
        held = self.wall_now() - self.paused_at
        self.paused_at = None
        self._control(
            "resume", by, f"resumed after {_clock(held)} paused", index, paused_s=held
        )

    def _stamp(self, mark: int, frame: int | None) -> None:
        """**An operator's mark, in the frame it reached the rig** (P4d-2b spec
        §5.0, §5.1): `OPERATOR_MARK` strobed now, and the stamp -- the mark's
        number, the frame (`None` between trials and while paused), the session's
        anchored clock -- kept for `_settle_stamps` to write at the boundary after.

        **Called from inside a frame**, but only when a signal arrived: the per-frame
        check that finds none is `link.mark_signal` alone. What this does on a mark
        is bounded -- one strobe, one clock read, one append -- and is the whole of
        the mark's work in the frame; nothing here writes a file. A mark is never
        refused, since it has already been pressed: without an `OPERATOR_MARK` code
        it is stamped unstrobed, and `_settle_stamps` says so."""
        if self._mark_code is not None:
            self.card.emit(self._mark_code)
        self._stamps.append((mark, frame, self.wall_now(), self.paused_at is not None))

    def _settle_stamps(self, index: int) -> None:
        """Write the stamps a frame or a boundary kept (`_stamp`): one `mark` row
        each, numbered in the order this session stamped them, onto the changes feed
        and into the record, and remembered for the note that follows (`_mark_note`).
        `index` is the trial they were stamped in, or the one about to run."""
        for mark, frame, at, paused in self._stamps:
            number = len(self._stamped) + 1
            if frame is not None:
                said = f"mark {number} stamped in trial {index}, frame {frame}"
            elif paused:
                said = f"mark {number} stamped while paused, before trial {index}"
            else:
                said = f"mark {number} stamped between trials, before trial {index}"
            strobed = self._mark_code is not None
            if not strobed:
                said += (
                    "; not strobed: this session's allocation has no OPERATOR_MARK "
                    "event code"
                )
            self._control(
                "mark", "", said, index, at=at,
                mark=mark, number=number, frame=frame, strobed=strobed,
            )
            self._stamped[mark] = (number, index, frame, at)
        self._stamps.clear()

    def _check_marks(self, index: int) -> None:
        """The mark check at a trial boundary (spec §5.1: it "runs between trials and
        while paused too"): a mark waiting here is stamped with no frame and written
        at once, since nothing here is inside a frame."""
        mark = self.link.mark_signal()
        if mark:
            self._stamp(mark, None)
            self._settle_stamps(index)

    def _mark_note(self, command, index: int) -> None:
        """A `Mark` command: the note half of a mark, joined to its stamp by the
        signal's number (spec §5.1). One `note` row carrying the three instants --
        pressed (the browser's clock), received (`wlx serve`'s), stamped (the
        session's anchored clock, with its frame) -- **and the gaps between them**,
        each across two clocks and recorded as they read, never hidden and never
        corrected. A note for a mark this session never stamped -- a signal that
        did not arrive, or one from before this session -- is recorded as such."""
        joined = self._stamped.get(command.mark)
        number, trial, frame, stamped_at = joined if joined else (None, None, None, None)
        quoted = f'"{command.note}"' if command.note else "no note"
        said = (
            f"a note for mark {command.mark}, which this session never stamped: {quoted}"
            if number is None
            else f"mark {number}: {quoted}"
        )
        self._control(
            "note",
            command.by,
            said,
            index,
            mark=command.mark,
            number=number,
            note=command.note,
            pressed_at=command.pressed_at,
            received_at=command.received_at,
            stamped_at=stamped_at,
            stamped_in_trial=trial,
            frame=frame,
            received_after_pressed_s=_gap(command.received_at, command.pressed_at),
            stamped_after_received_s=_gap(stamped_at, command.received_at),
        )

    def _schedule(self, command, index: int) -> None:
        """Hold a scheduled stop (P4d-2b spec §5.1), replacing any before it.

        `link.check_schedule` is asked again here -- the wire asked it of a command
        that crossed it -- so a schedule that reached the session another way meets
        the same rule. The target is fixed now: a clock time's next occurrence on
        the session's anchored clock, a trial count from the trials run so far, or
        mL this session."""
        why = _link.check_schedule(command.kind, command.value)
        if why is not None:
            self._refuse("schedule", command.by, f"{why}, so it is refused")
            return
        if self.stopped_because:
            self._refuse(
                "schedule",
                command.by,
                f"the session is stopping ({self.stopped_because}); a schedule is not "
                f"applied",
            )
            return
        if command.kind == "clock":
            wall = self.wall_now()
            target = _next_occurrence(command.value, wall)
            said = f"at {command.value}"
            if time.localtime(target)[:3] != time.localtime(wall)[:3]:
                said += f" on {time.strftime('%Y-%m-%d', time.localtime(target))}"
        elif command.kind == "trials":
            target = float(index + command.value)
            said = f"after trial {index + command.value}"
        else:
            target = float(command.value)
            said = f"after {command.value:g} mL this session"
        replaced = self.scheduled_stop
        self.scheduled_stop = (command.kind, target, command.by, said)
        self._control(
            "schedule",
            command.by,
            f"scheduled stop {said}" + (f", replacing {replaced[3]}" if replaced else ""),
            index,
            stop=command.kind,
            target=target,
            said=said,
            replaced=replaced[3] if replaced else None,
        )

    def _cancel(self, by: str, index: int) -> None:
        """Remove the scheduled stop (spec §5.1), or say there is none."""
        if self.scheduled_stop is None:
            self._refuse("cancel", by, "there is no scheduled stop to cancel; nothing changed")
            return
        said = self.scheduled_stop[3]
        self.scheduled_stop = None
        self._control(
            "cancel", by, f"cancelled the scheduled stop {said}", index, cancelled=said
        )

    def _ends(self, index: int) -> bool:
        """Whether the session must end at this boundary, with its reason and kind
        set. **One place for it**, asked between trials and on every pass of the
        paused loop alike (P4d-2b spec §5.1: "ending the session on it exactly as
        between trials"), so neither can be enforced on one path and not the other.

        **The out-of-cage limit first**, `welfare.must_stop`, read on the wall as
        ever (P4d-2a spec §10): a session at its limit ends as `limit` even when a
        schedule fell due at the same check. **Then the scheduled stop**, which ends
        the session like the stop button -- `stop_kind` `operator`, the reason
        *scheduled stop (...) set by NAME* -- when its clock time has come on the
        session's anchored clock, `index` trials have run, or `welfare`'s session
        fluid has reached it. `welfare` is read, never asked to decide."""
        wall = self.wall_now()
        stop = self.welfare.must_stop(wall)
        if stop:
            self.stopped_because = stop
            self.stop_kind = "limit"
            return True
        if self.scheduled_stop is None:
            return False
        kind, target, by, said = self.scheduled_stop
        due = (
            wall >= target
            if kind == "clock"
            else index >= target
            if kind == "trials"
            else self.welfare.session_total() >= target
        )
        if not due:
            return False
        self.stopped_because = f"scheduled stop ({said}) set by {by}"
        self.stop_kind = "operator"
        # Spent: the stop reason says it now, and a console no longer offers to
        # cancel a stop that has happened.
        self.scheduled_stop = None
        self._control(
            "scheduled_stop", by, self.stopped_because, index, stop=kind, target=target
        )
        return True

    def _hold(self, index: int, publish) -> None:
        """**Paused** (P4d-2b spec §5.1): no trial runs and nothing is rewarded, while
        once per housekeeping pass the loop drains commands -- resume, stop, marks,
        schedules, settings -- publishes a frame, and asks `_ends` whether the
        out-of-cage limit has arrived, ending the session on it as between trials.
        The out-of-cage clock runs on the wall throughout, since nothing here stops
        it.

        **Nothing is rewarded because nothing can be**: a reward is a trial's action
        (`run.Effects.reward`), and no trial runs here. **Nothing is drawn** for the
        same reason: a stimulus is shown only by a trial, so the display the task's
        trials draw on shows its background with nothing on it (spec §5.0). There is
        no display process yet to be told so -- S4's is not built (docs/CHECKPOINT.md:
        "a frame on screen" is blocked on a panel) -- and when there is, this is the
        pause it must show: V12 item 3 in `docs/validation.md`, not yet written.

        Returns when the session resumes, or with `stopped_because` set when it must
        end; `run()` reads which."""
        while self.paused_at is not None:
            # The wait is also the paused loop's mark check: `idle` returns the
            # moment a mark arrives, and it is stamped then.
            mark = self.link.idle(PAUSE_HOUSEKEEPING_S)
            if mark:
                self._stamp(mark, None)
                self._settle_stamps(index)
            for command in self.link.drain():
                self._command(command, index)
            publish()
            if self.stopped_because:
                return
            if self._ends(index):
                publish()
                return

    def _refuse(self, name: str, by: str, why: str) -> None:
        """One refusal onto the capped list -- see `refusals`."""
        self.refusals.append((name, by, why))
        if len(self.refusals) > _link.REFUSAL_HISTORY:
            self.refusals_dropped += len(self.refusals) - _link.REFUSAL_HISTORY
            del self.refusals[: -_link.REFUSAL_HISTORY]

    def _command(self, command, index: int) -> None:
        """A console's request, routed to the one write path.

        `index` is the trial about to run, carried only so a recorded refusal can
        say where in the session it happened -- see `record.SessionRecord.refusal`.

        **Refusals do not end the session.** A person mistyping a parameter name is
        not a fault of the rig, and ending a session with an animal in the chair over
        a typo is a worse outcome than ignoring it. The refusal is recorded.

        **A refusal of a ceiling-bounded name also goes into the session record**
        (PI, 2026-09-19). Everything else here is telemetry, and telemetry is lossy
        by design (S9a §9) -- an attempt to set a dose above its limit left no
        durable trace unless a console happened to be attached. An ordinary
        parameter typo stays telemetry-only; `record.SessionRecord.refusal` carries
        why the two are not treated alike.

        **The list is capped, like the two beside it.** `ZmqLink.refused` and
        `Telemetry.refusals` are both bounded at `link.REFUSAL_HISTORY` with the
        discards counted, because the party driving their growth is an untrusted
        network peer rather than the operator -- one entry per `SetParameter` it
        sends, as fast as it can send them. This list is driven by exactly the same
        peer and was the third one, unbounded.

        **Nothing arriving here is accepted once the loop has ended** (P4d-2a spec
        §10, Task 8). A parameter staged after the last trial could never be
        applied, and a stop has nothing left to stop -- both are refused with the
        reason rather than silently kept. **The return used to be the one
        exception** -- a console's `ReturnedToCage` was accepted in any phase -- but
        the PI ruled the wl-works ELN owns the return, not a console, so `link.py`
        has no such command any more and this method has nothing left to route in
        the post-loop phase but a refusal.
        """
        if self.phase != "running":
            self._refuse(
                command.name if isinstance(command, _link.SetParameter) else command.KIND,
                command.by,
                "the session has ended and is waiting for the animal's return to its "
                "cage, which is marked at wlx run's terminal; a command sent now is "
                "not applied",
            )
            return
        if isinstance(command, _link.Stop):
            self.stopped_because = f"stopped by {command.by}"
            self.stop_kind = "operator"
            # P4d-2b b2a: the record says who stopped the session and when, as it
            # says who paused it; the reason alone was in telemetry and at the
            # terminal, and neither is the record.
            self._control("stop", command.by, self.stopped_because, index)
            return
        if isinstance(command, _link.Pause):
            self._pause(command.by, index)
            return
        if isinstance(command, _link.Resume):
            self._resume(command.by, index)
            return
        if isinstance(command, _link.Mark):
            self._mark_note(command, index)
            return
        if isinstance(command, _link.ScheduleStop):
            self._schedule(command, index)
            return
        if isinstance(command, _link.CancelScheduledStop):
            self._cancel(command.by, index)
            return
        if not isinstance(command, _link.SetParameter):
            # A command this session has no branch for -- a newer console's -- is
            # refused under its kind, as `drain` refuses an unknown kind on the
            # wire, and the session runs on.
            self._refuse(
                command.KIND,
                command.by,
                f"a {command.KIND!r} command is not one this session acts on, so it "
                f"is refused",
            )
            return
        try:
            self.set(command.name, command.value, by=command.by)
        except (Exceeded, TypeError) as refused:
            # **M8's backstop** (P4d-2b b2a): `TypeError` too. The wire refuses a
            # malformed value before it becomes a command (`link._setting`) and
            # `set` refuses what it knows is not a number, so this catches only a
            # check neither of them makes yet -- and a session never ends with an
            # animal in the chair because a setting was malformed.
            why = (
                str(refused)
                if isinstance(refused, Exceeded)
                else f"{command.name!r} could not be checked ({type(refused).__name__}: "
                f"{refused}), so it is refused and the session runs on"
            )
            if command.name in self.spec.bounds.ceilings and self._record is not None:
                self._record.refusal(
                    name=command.name,
                    # As asked, when it can be written as asked; `repr` otherwise,
                    # so the row is written whatever the value was.
                    asked=(
                        command.value
                        if isinstance(command.value, (int, float, str))
                        else repr(command.value)
                    ),
                    by=command.by,
                    why=why,
                    trial_index=index,
                    session_seconds=self.now(),
                )
            self._refuse(command.name, command.by, why)

    def _params(self) -> dict[str, Param]:
        trial = self._trial if self._trial is not None else self._load()
        return {p.name: p for p in trial.params}

    def _apply_staged(self) -> None:
        """Applied atomically in the inter-trial interval, and all of them at once.

        Atomic because a task whose two parameters must agree -- an eccentricity and
        the window that scores it -- would otherwise run one trial with one changed
        and the other not, and that trial is a datum from an experiment nobody
        designed.

        **A bounded row is applied here too, and that is the point** (PI,
        2026-09-19). It used to be recorded here and applied a pass earlier, inside
        `set()`, so the strobe and the `parameter_changes.jsonl` row for a reward
        volume were written *after* the first trial rewarded at it. Applying and
        recording in the same pass is what puts the row immediately before the first
        trial it describes, which is what an offline reconciliation of commanded
        fluid reads it as. The two branches below differ only in where the value
        lives -- a welfare ceiling or the task's own values -- never in when.

        **Bounded values go back through `bounds.set`, which re-validates.** The
        ceiling check is cheap and belongs to `bounds`; asking it again at the moment
        of assignment costs nothing and means no path reaches a ceiling without one.

        **"Atomically" is true because that re-validation cannot fail here, not
        because this loop is transactional.** Every staged value was validated at
        offer time, `Ceiling` is frozen, and nothing reassigns `spec.bounds` while a
        session runs -- so `bounds.set` below raises on no reachable path today. **If
        anything ever lets a `Ceiling.maximum` move mid-session**, this loop would
        leave the earlier rows applied and `_staged` uncleared, and the validation
        would have to move to a pass of its own above the assignments before that
        change ships. Named so the next reader can grep it rather than believe it.
        """
        if not self._staged:
            return
        for name, was, now, by, bounded in self._staged:
            self._sequence += 1
            if bounded:
                self.spec.bounds.set(name, now, by=by)
            else:
                self.spec.values[name] = now
            if self._record is not None:
                self._record.parameter_change(self._sequence, name, was, now, by)
            self.card.emit(self.allocation.code_for("PARAM_CHANGED"))
        self._staged.clear()

    # --- running ----------------------------------------------------------

    _trial: Trial | None = field(init=False, default=None, repr=False)

    def _load(self) -> Trial:
        self._trial = _load_trial(Path(self.spec.task))
        return self._trial

    def _plan(self) -> list[Block]:
        """The session's blocks, or the one block a flat session is."""
        if self.spec.blocks:
            return self.spec.blocks
        return [
            Block(
                name="session",
                conditions=[Condition("session", {}, target=self.spec.trials)],
                # Every trial pays, including aborts. A flat "run N trials" means N
                # trials, not N completed ones -- the completed-trial reading is what
                # a condition target expresses, and a session that quietly ran on
                # past its declared length would be a different session.
                counts_toward=frozenset(Outcome),
            )
        ]

    def _agent(self):
        """The default world: one behaviour agent, told about each trial.

        One `Subject` for the session rather than one per trial, because its
        generator carries the session's randomness -- a fresh subject per trial would
        reseed to the same animal every time, and every trial would be identical.
        """
        subject = Subject(
            seed=self.spec.seed,
            hazards=self.spec.hazards,
            engagement=self.spec.engagement,
            lapse=self.spec.lapse,
        )

        def make(trial: Trial, values: dict, index: int) -> Subject:
            subject.new_trial()
            prepare(subject, trial, self.spec.frame_period, values)
            return subject

        return make

    def _publish(self) -> None:
        """One frame from the state the loop last left -- the body of `run()`'s
        `publish`, kept callable after the loop so `await_return` publishes the same
        shape rather than a second one."""
        self.link.publish(
            _link.Telemetry.of(self, self._tally, self._scheduler, self._index)
        )

    def run(self) -> Census:
        """Open the in-session clock if nothing has, check, then require the marks,
        then run, then record.

        **In that order, and it is load-bearing.** A malformed task is refused before
        anything else happens -- ideally before the animal is in the chair at all --
        and a session whose welfare marks are missing is refused before its first
        frame, by `welfare.preflight` rather than by a second copy of the rule here.

        **`open()` runs first, ahead of the check it would otherwise be refused
        alongside** (P4d-2a spec §10 item 3): a direct API user who never called
        `open()` still gets a `session opened` row and a working
        `Telemetry.in_session_seconds`, even on a task that goes on to refuse.
        `wlx run` calls `open()` itself, earlier still -- before the departure is
        even marked -- so this is a no-op there and only a backstop for everyone
        else.
        """
        if self.opened_wall_at is None:
            self.open()
        trial = self._load()
        findings = check(trial, self.allocation)
        blocking = [f for f in findings if f.blocking]
        if blocking:
            raise SystemExit(
                "task refused, session not started:\n"
                + "\n".join(f"  {f.code}: {f.detail}" for f in blocking)
            )
        self.welfare.preflight(self.wall_now())

        scheduler = Scheduler(blocks=self._plan(), seed=self.spec.seed)
        make_world = self.world if self.world is not None else self._agent()
        tally = Tally()
        self.blocks_run = [scheduler.block.name]

        record = SessionRecord.open(
            self.spec.root, self.spec.session_id, self.spec.subject
        )
        self._record = record
        record.snapshot(
            layers={"session": dict(self.spec.values)},
            resolved=dict(self.spec.values),
            versions={
                "task": self.spec.task,
                "allocation": self.spec.allocation,
                "bounds": self.spec.bounds_config,
            },
        )
        self._tally = tally
        self._scheduler = scheduler
        self._index = 0
        self.phase = "running"
        self._mark_code = self._code("OPERATOR_MARK")
        # **The per-frame mark check** (P4d-2b spec §5.1), handed to `run_trial` as
        # its one per-frame hook. Bound once, here, so each frame is two calls and a
        # test on a small integer; `_stamp` runs only when a signal arrived.
        signal, stamp = self.link.mark_signal, self._stamp

        def each_frame(frame: int) -> None:
            mark = signal()
            if mark:
                stamp(mark, frame)

        try:
            index = 0
            #: Block transitions taken. Bounded by the plan -- see the check below.
            advanced = 0

            def publish() -> None:
                """Telemetry for the current boundary, to whoever is attached.

                Called at the top of every pass, and **again** immediately after a
                natural stop (a welfare ceiling, or every block finished) sets
                `stopped_because` -- so the last frame a session ever publishes
                always names the real reason, on every stop path alike. A
                console-issued `Stop` needs no second call: `_command` sets
                `stopped_because` before this runs, so the top-of-pass call already
                carries it. S9's "Written for a stranger" requirement says an error
                that requires knowing the design to interpret is a bug and abort
                reasons must be self-explanatory; a console that watched the stream
                simply go quiet on the out-of-cage ceiling would have neither.
                The extra frame this costs on a natural stop is free: telemetry is
                lossy and latest-wins by design (S9a §9), so nothing downstream cares
                that two frames share a `trial_index`.
                """
                self._index = index
                self._publish()

            while True:
                self._apply_staged()
                # Between trials the frame's mark check runs once here, before the
                # drain, so a mark's stamp is written ahead of a note that arrived
                # with it (P4d-2b spec §5.1).
                self._check_marks(index)
                # Drain *after* `_apply_staged()`, not before: staging and applying
                # in the same pass would collapse S9a §8's one-boundary visibility
                # window to nothing. A change drained here is staged but not yet
                # applied -- `_apply_staged()` above already ran this pass, so it
                # will not land until the *next* one -- and `publish()` below reports
                # it queued. Reorder this and `Telemetry.staged` reads empty forever:
                # nothing else populates it, so the only sign of a queued change
                # before it silently lands would be gone.
                for command in self.link.drain():
                    self._command(command, index)
                # Publish *before* the stop check: a console watching a session that
                # stops learns that it stopped and why, rather than seeing the stream
                # simply cease.
                publish()
                if self.stopped_because:
                    break
                # The wall, not `now()` (P4d-2a spec §10): one clock read replacing
                # another at the same trial boundary, never per frame. `_ends` is
                # the same question the paused loop asks.
                if self._ends(index):
                    publish()
                    break
                if self.paused_at is not None:
                    # Held here, at the boundary, until a resume or an ending
                    # (P4d-2b spec §5.1). A resume goes back to the top, where
                    # anything staged while paused is applied before the next trial.
                    self._hold(index, publish)
                    if self.stopped_because:
                        break
                    continue
                if scheduler.finished:
                    if scheduler.done:
                        self.stopped_because = "every block is finished"
                        self.stop_kind = "completed"
                        publish()
                        break
                    # **A plan can be advanced through only as many times as it has
                    # blocks.** This `continue` runs no trial, draws no condition
                    # and moves no clock, so a scheduler that reported `finished`
                    # and then did not leave the block would spin here: no telemetry
                    # would change, `must_stop` would not fire until the wall itself
                    # reached the ceiling -- hours on a rig, and never under a test
                    # whose wall follows the frames, since `self._elapsed` does not
                    # move -- and a rig would look like it was running with an
                    # animal in the chair and nothing happening.
                    #
                    # `Scheduler.advance` raises on the last block, so no path
                    # reaches this today. It is counted here anyway, and **counted
                    # rather than compared**: a plan may legitimately list the same
                    # `Block` object twice -- "multiple blocks of the same tasks"
                    # is how the PI described a session (2026-09-19) -- so a guard
                    # asking whether the block *changed* would abort one of those
                    # with an animal in the chair. A count cannot: a session
                    # advances exactly `len(blocks) - 1` times, and the next one is
                    # impossible whatever the blocks are.
                    #
                    # It is also what makes a mutation of `advance` fail a test
                    # instead of hanging the suite until a 300-second timeout, which
                    # is the harness noticing rather than a test noticing.
                    advanced += 1
                    if advanced >= len(scheduler.blocks):
                        raise RuntimeError(
                            f"this session has advanced {advanced} times through a "
                            f"plan of {len(scheduler.blocks)} blocks, so the "
                            f"scheduler is not leaving {scheduler.block.name!r}; it "
                            f"can draw no further trial and must not spin"
                        )
                    scheduler.advance()
                    self.blocks_run.append(scheduler.block.name)
                    continue

                condition = scheduler.next_trial()
                values = {**self.spec.values, **condition.values}
                world = make_world(trial, values, index)
                result = run_trial(
                    trial,
                    world,
                    self.spec.frame_period,
                    values=values,
                    effects=self.rig,
                    each_frame=each_frame,
                )
                # The marks this trial's frames stamped, written now that it is over.
                self._settle_stamps(index)
                self._elapsed += result.frames * self.spec.frame_period + self.spec.iti
                if result.outcome is not None:
                    # The terminal `Marker`, which is `wl-preproc`'s and the
                    # framework's to emit -- a task declares an `Outcome` and never a
                    # marker. The *reason* was strobed by the task's own transition
                    # immediately before this, which is how eighteen outcomes share
                    # five markers without losing which one happened.
                    self.card.emit(self.allocation.outcomes[result.outcome])
                tally.add(result)
                scheduler.record(condition.name, result.outcome)
                # One string for the record and for a console's recent outcomes, so
                # the two cannot disagree (P4d-2b spec §4.1).
                recorded = result.outcome.value if result.outcome else "hang"
                self._recent.append(recorded)
                record.trial(
                    index=index,
                    outcome=recorded,
                    params=values,
                    block=scheduler.block.name,
                    condition=condition.name,
                )
                if self.observe is not None:
                    self.observe(condition, values, result)
                index += 1
            # **Only the kind that was fixed is released** (PI, 2026-09-20).
            # `welfare.head_released` would accept the call for any deployment, and
            # `self.card.emit` would then put a `HEAD_RELEASED` in the stream of a
            # session that had no `HEAD_FIXED` -- a restraint record for restraint
            # nothing marked, which is the zero-where-an-absence-belongs failure
            # `chair_seconds` refuses on the other surface. On the wall, like the
            # fixation (P4d-2a spec §10).
            if self.spec.deployment is Deployment.RIG_FIXED:
                self.head_released(self.wall_now())
            return tally.census()
        except KeyboardInterrupt:
            # **Ctrl-C at the terminal is an operator's stop** (P4d-2a final review
            # I4), made at `wlx run`'s own terminal rather than from a console. It is
            # not an `Exception`, so it went past the handler below with no reason
            # set, and every frame after it -- the post-loop ones included -- read
            # `stop_kind` `None`, which means "still running". One frame names it,
            # as for a console's `Stop`, and the interrupt goes on to the caller,
            # which still owes the animal its return (`cli.main`). The head is left
            # as it was, as a fault leaves it: `await_return` releases it on entry.
            self.stopped_because = "interrupted at the terminal"
            self.stop_kind = "operator"
            publish()
            raise
        except Exception as fault:
            # **One frame naming the fault, then it propagates unchanged** (PI,
            # 2026-09-19). `welfare.deliver` raises when the pump will not answer,
            # `welfare.Rig` deliberately does not swallow it, and it used to come
            # straight past the `finally` below with no telemetry at all -- so a
            # console watching a rig break, unattended and cage-side, saw the
            # stream simply stop. That is the failure S9's "written for a stranger"
            # rule names: an ending nobody can interpret from what is on screen.
            #
            # **The refusal is the behaviour that matters and is not touched.**
            # Swallowing a pump fault would produce a session's worth of correct
            # trials nobody was paid for, which is what `welfare.Absent` exists to
            # prevent arrived at by another route. This sets a reason, publishes,
            # and re-raises the same exception.
            #
            # `publish()` is not guarded: if telemetry itself fails here that is a
            # second fault, and Python chains the first onto it (`__context__`), so
            # the session still aborts and neither is hidden. A `try` around it
            # that did nothing would be the swallow this whole path refuses.
            self.stopped_because = (
                f"fault, session aborted: {type(fault).__name__}: {fault}"
            )
            self.stop_kind = "fault"
            publish()
            raise
        finally:
            # A trial that faulted or was interrupted has no boundary after it, so
            # the marks its frames stamped -- already strobed -- are written here,
            # while the record is still open (P4d-2b b2a).
            if self._stamps:
                self._settle_stamps(self._index)
            record.close()
            self._record = None

    def await_return(self, give_up: threading.Event, heartbeat: float = 1.0) -> None:
        """Keep a rig session's out-of-cage clock visible until the animal is home.

        **P4d-2a.** Since ruling 4 (PI, 2026-09-20) the interval runs on the wall
        until the return, but nothing published it after the last trial, so a console
        showed a frozen clock and a limit crossed after the loop was seen by nobody.
        This publishes a frame every `heartbeat` seconds -- **a display cadence for a
        console, not a measurement of this system**, and well inside `ZmqConsole`'s
        5 s receive timeout so a waiting console never times out between frames -- with
        the clock read from the wall, as every welfare duration is (P4d-2a spec §10).

        **Draining the link is for post-loop refusals now, never for the return
        itself** (P4d-2a spec §10, Task 8). It used to be where the return could
        arrive too, drained here and routed by `_command` to `returned_to_cage`; the
        PI ruled the wl-works ELN owns the return, not a console, so `link.py` carries
        no such command any more. What still arrives here is a late `SetParameter` or
        `Stop`, and `_command` still refuses both with the session's one sentence for
        the post-loop phase (see its own docstring) and puts the refusal on the wire
        for whoever is watching.

        **It ends when the return is recorded, by the terminal alone, from another
        thread** (`cli._close_interval` runs this method on a background thread while
        `_settle_return` holds the terminal prompt on its own) -- this loop notices
        through `welfare.returned_wall_at`, never by being told, and then publishes
        one `closed` frame. **It never ends on its own otherwise**: `give_up` is its
        owner's to set, and then it publishes nothing further and the owner writes
        `return_not_recorded`.

        **A head a fault left fixed is released first.** `run()` releases it at a
        normal end, but a fault re-raises past that, and `welfare` refuses a return
        while the head is recorded as fixed. Head-post release bounds nothing (PI,
        2026-09-19, restated 2026-09-26), so it is marked here rather than asked for.

        **One frame naming the fault, then it propagates unchanged** -- the same rule
        `run()`'s own `except Exception as fault:` follows (fix round 1), covering
        whatever this method's own work can still raise -- the head release on entry
        (final review M7), `link.drain()`, `_command`, `_publish()` -- now that
        `returned_to_cage` is never one of them. Left
        unguarded, such an exception would escape with `phase` stuck at
        `awaiting_return` forever, no `closed` frame, and -- on the background thread
        `cli._close_interval` runs this on -- a traceback nobody joins. This publishes
        one `fault` frame, unguarded as `run()`'s is (a second failure here chains
        onto the first rather than hiding it), and then re-raises. **Surfacing that
        exception is the thread's owner's job, never this method's**:
        `cli._close_interval` re-raises it on the main thread rather than swallowing
        or retrying it. A write failure recording the return itself is no longer this
        method's to guard at all -- `returned_to_cage` runs only on the terminal's own
        thread now, and `test_a_failed_row_write_is_never_swallowed`
        (`tests/test_taskd.py`) pins that it is not swallowed there.

        A cage-side session has no interval, and this returns at once.
        """
        if self.spec.deployment is Deployment.CAGE_SIDE:
            return
        if self._scheduler is None:
            raise RuntimeError(
                "await_return before run() opened the record: there is no session "
                "whose clock could be published"
            )
        try:
            # Inside the handler (final review M7): a card that fails strobing
            # `HEAD_RELEASED` is a post-loop fault like any other here, and gets the
            # frame that names it. It escaped with none until then.
            if (
                self.welfare.fixed_wall_at is not None
                and self.welfare.released_wall_at is None
            ):
                self.head_released(self.wall_now())
            self.phase = "awaiting_return"
            while self.welfare.returned_wall_at is None and not give_up.is_set():
                for command in self.link.drain():
                    self._command(command, self._index)
                if self.welfare.returned_wall_at is not None:
                    break
                self._publish()
                give_up.wait(heartbeat)
            if self.welfare.returned_wall_at is not None:
                self.phase = "closed"
                self._publish()
        except Exception as fault:
            self.stopped_because = (
                f"fault after the loop, the return may not be recorded: "
                f"{type(fault).__name__}: {fault}"
            )
            self.stop_kind = "fault"
            self._publish()
            raise
