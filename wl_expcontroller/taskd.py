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
from dataclasses import dataclass, field
from pathlib import Path

from wl_expcontroller import link as _link
from wl_expcontroller.bounds import Bounds, Exceeded, _finite
from wl_expcontroller.check import check
from wl_expcontroller.cli import _load_allocation, _load_trial
from wl_expcontroller.codes import Allocation
from wl_expcontroller.dio import Absent as NoCard
from wl_expcontroller.record import EXPCONTROLLER_DIRNAME, SessionRecord, welfare_note
from wl_expcontroller.scheduler import Block, Condition, Scheduler
from wl_expcontroller.simulate import Census, Subject, Tally, prepare
from wl_expcontroller.run import run_trial
from wl_expcontroller.task import Entered, Exited, Outcome, Param, SaccadeTo, Trial
from wl_expcontroller.welfare import (
    WARN_WITHIN_DEFAULT,
    Absent as NoPump,
    Deployment,
    Rig,
    Welfare,
)


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
    #: The **wall** clock, in POSIX seconds, and a different base from `clock`.
    #: `time.time` by default. **Every welfare duration is read from it** (P4d-2a spec
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
    stop_kind: str | None = field(init=False, default=None)
    #: The loop's own state, kept so a frame can still be built after it returns.
    _tally: Tally | None = field(init=False, default=None, repr=False)
    _scheduler: Scheduler | None = field(init=False, default=None, repr=False)
    _index: int = field(init=False, default=0, repr=False)
    #: One mark at a time: the terminal and a console can both offer the return.
    _mark_lock: threading.Lock = field(
        init=False, default_factory=threading.Lock, repr=False
    )

    def __post_init__(self) -> None:
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
        self.rig = Rig(card=self.card, welfare=self.welfare)

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
        `phase`, because nothing welfare reads is on the frame clock. See
        `wall_clock`.
        """
        if self.wall_clock is not None:
            return self.wall_clock()
        return time.time()

    def duration_warning(self) -> str | None:
        """What an operator must be told about the time left out of the cage.

        `approaching_limit`'s sentence, as during the loop. **After the loop, past the
        limit, `must_stop`'s** (P4d-2a spec §4): there is no loop left to stop, and
        the warning is what tells someone the animal is still out. Read on the wall,
        as every welfare duration is.
        """
        at = self.wall_now()
        warning = self.welfare.approaching_limit(at)
        if warning is None and self.phase == "awaiting_return":
            warning = self.welfare.must_stop(at)
        return warning

    # --- out of cage, and restraint ---------------------------------------

    def _note(self, kind: str, at: float, by: str, how: str, reason: str = "") -> None:
        """One mark row in `welfare_notes.jsonl` (P4d-2a spec §3).

        Written by the mark methods themselves, so every caller -- the terminal, a
        console over the link, P4d-2b's browser -- leaves the same row and none can
        reach the mark around it. `was` and `now` are both the mark's instant: nothing
        was amended, so there is one value to record.

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

    def left_cage(
        self, at: float, confirmed: bool = False, by: str = "", how: str = "terminal"
    ) -> None:
        """The console action that starts the clock bounding this session.

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
        the wall clock, and a caller reading `time.time()` for itself would be a
        second place the two clock bases meet.
        """
        return self.welfare.departure_needs_confirmation(at, wall_now=self.wall_now())

    def return_needs_confirmation(self, at: float) -> str | None:
        """What a person must be shown before `returned_to_cage(at)`, or `None`.

        The passthrough `returned_to_cage`'s docstring said would arrive "when
        P4d-2's console prompts too": `wlx run`'s return prompt is its caller
        (P4d-2a). `wall_now()` is this object's seam onto the wall, for the reason
        `departure_needs_confirmation` gives.
        """
        return self.welfare.return_needs_confirmation(at, wall_now=self.wall_now())

    def amend_mark(
        self, what: str, original: float, amended: float, reason: str, by: str
    ) -> None:
        """The console action that goes with the confirmations above.

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

        **Under `_mark_lock`** (P4d-2a): the terminal and a console can both offer the
        return, and `welfare`'s check-then-set must not interleave. The first accepted
        mark wins; the second is refused by `welfare`'s own sentence.
        """
        with self._mark_lock:
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
        """The console action S8 §5.2 requires before a `RIG_FIXED` session starts.

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
        if declared.choices and value not in declared.choices:
            raise Exceeded(f"{name!r} may only be one of {declared.choices}")
        # **The same hole as the welfare path, on the task's own declaration.** The
        # range check below is two ordered comparisons, and `nan` is `False` against
        # both -- so a declared range accepts a value no range contains. This is not
        # a welfare-critical file and a `nan` fixation window is a broken trial
        # rather than a hurt animal, but it is the identical defect and it enters
        # from the identical place: a console over the wire, or `--set` on a
        # command line. `bounds._finite` is the same guard the ceilings use.
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

        **The return is accepted in any phase; nothing else is, once the loop has
        ended** (P4d-2a). A parameter staged after the last trial could never be
        applied, and a stop has nothing left to stop -- both are refused with the
        reason rather than silently kept.
        """
        if isinstance(command, _link.ReturnedToCage):
            try:
                self.returned_to_cage(
                    command.at, confirmed=command.confirmed, by=command.by, how="console"
                )
            except Exceeded as refused:
                self._refuse("returned_to_cage", command.by, str(refused))
            return
        if self.phase != "running":
            self._refuse(
                "stop" if isinstance(command, _link.Stop) else command.name,
                command.by,
                "the session has ended and is waiting for the animal's return to its "
                "cage; the return is the only mark it still takes",
            )
            return
        if isinstance(command, _link.Stop):
            self.stopped_because = f"stopped by {command.by}"
            self.stop_kind = "operator"
            return
        try:
            self.set(command.name, command.value, by=command.by)
        except Exceeded as refused:
            if command.name in self.spec.bounds.ceilings and self._record is not None:
                self._record.refusal(
                    name=command.name,
                    asked=command.value,
                    by=command.by,
                    why=str(refused),
                    trial_index=index,
                    session_seconds=self.now(),
                )
            self._refuse(command.name, command.by, str(refused))

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
        """Check, then require the marks, then run, then record.

        **In that order, and it is load-bearing.** A malformed task is refused before
        anything else happens -- ideally before the animal is in the chair at all --
        and a session whose welfare marks are missing is refused before its first
        frame, by `welfare.preflight` rather than by a second copy of the rule here.
        """
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
            versions={"task": self.spec.task, "allocation": self.spec.allocation},
        )
        self._tally = tally
        self._scheduler = scheduler
        self._index = 0
        self.phase = "running"
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
                # another at the same trial boundary, never per frame.
                stop = self.welfare.must_stop(self.wall_now())
                if stop:
                    self.stopped_because = stop
                    self.stop_kind = "limit"
                    publish()
                    break
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
                )
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
                record.trial(
                    index=index,
                    outcome=result.outcome.value if result.outcome else "hang",
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
        the clock read from the wall, as every welfare duration is (P4d-2a spec §10),
        and drains the link, where the return may arrive.

        **It ends when the return is recorded**, by a console through `_command` or by
        the terminal through `returned_to_cage` from another thread, and then
        publishes one `closed` frame. **It never ends on its own otherwise**: `give_up`
        is its owner's to set, and then it publishes nothing further and the owner
        writes `return_not_recorded`.

        **A head a fault left fixed is released first.** `run()` releases it at a
        normal end, but a fault re-raises past that, and `welfare` refuses a return
        while the head is recorded as fixed. Head-post release bounds nothing (PI,
        2026-09-19, restated 2026-09-26), so it is marked here rather than asked for.

        **One frame naming the fault, then it propagates unchanged** -- the same rule
        `run()`'s own `except Exception as fault:` follows (fix round 1). `welfare`
        accepts a return -- setting `returned_wall_at` -- *before* `_note` writes its
        row, so the row write (`record.welfare_note`, disk full or otherwise) can still
        fail with the mark already recorded in memory. Left unguarded, that exception
        would escape with `phase` stuck at `awaiting_return` forever, no `closed`
        frame, and -- on Task 6's background thread -- a traceback nobody joins. This
        publishes one `fault` frame, unguarded as `run()`'s is (a second failure here
        chains onto the first rather than hiding it), and then re-raises. **Surfacing
        that exception is the thread's owner's job, never this method's**: Task 6
        re-raises it in the main thread rather than swallowing or retrying it, for the
        same reason `_note`'s own docstring gives -- a retry would call
        `welfare.returned_to_cage` a second time and be refused by that mark's own
        sentence, leaving memory certain and the file still empty with no path back to
        matching them.

        A cage-side session has no interval, and this returns at once.
        """
        if self.spec.deployment is Deployment.CAGE_SIDE:
            return
        if self._scheduler is None:
            raise RuntimeError(
                "await_return before run() opened the record: there is no session "
                "whose clock could be published"
            )
        if (
            self.welfare.fixed_wall_at is not None
            and self.welfare.released_wall_at is None
        ):
            self.head_released(self.wall_now())
        self.phase = "awaiting_return"
        try:
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
