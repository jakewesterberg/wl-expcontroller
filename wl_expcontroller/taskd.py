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
2026-09-19) and the head-fixation that records restraint, while a cage-side one
declares `Deployment.ANIMAL_AT_HOME` and needs neither. The declaration is on
`SessionSpec` rather than inferred, because a rig session nobody marked and a kiosk
session with nothing to mark are indistinguishable to anything that guesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from wl_expcontroller import link as _link
from wl_expcontroller.bounds import Bounds, Exceeded, _finite
from wl_expcontroller.check import check
from wl_expcontroller.cli import _load_allocation, _load_trial
from wl_expcontroller.codes import Allocation
from wl_expcontroller.dio import Absent as NoCard
from wl_expcontroller.record import EXPCONTROLLER_DIRNAME, SessionRecord
from wl_expcontroller.scheduler import Block, Condition, Scheduler
from wl_expcontroller.simulate import Census, Subject, Tally, prepare
from wl_expcontroller.run import run_trial
from wl_expcontroller.task import Entered, Exited, Outcome, Param, SaccadeTo, Trial
from wl_expcontroller.welfare import Absent as NoPump, Deployment, Rig, Welfare


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
    #: Rig or cage-side. **Required, with no default**, because the two differ in
    #: which welfare limits exist at all (`welfare.Deployment`) and a default would
    #: be a limit acquired -- or lost -- by omission.
    deployment: Deployment
    #: The session's plan. `None` means one block of `trials` trials, which is the
    #: same code path with one block in it.
    blocks: list[Block] | None = None
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
    #: The gap between trials, in seconds. Both clocks count it, because the animal
    #: is out of its cage and in the chair for it.
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
    #: Session time in seconds. Defaults to a clock derived from frames, which is
    #: what makes a simulated session's two clocks deterministic: a wall clock would
    #: make "stops at its out-of-cage ceiling" depend on how fast the machine ran. On
    #: a rig, frames *are* the clock, so the same choice is the honest one there.
    clock: object = None
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

    # --- out of cage, and restraint ---------------------------------------

    def left_cage(self, seconds_ago: float) -> None:
        """The console action that starts the clock bounding this session.

        **`seconds_ago`, against `now()`, and this is the whole time-base
        contract.** `now()` is frame-derived and reads zero when the session starts,
        so the animal leaving its cage is at a negative instant in that base and a
        timestamp parameter would invite a caller to pass zero -- which makes
        out-of-cage time equal chair time and reintroduces the under-count the clock
        exists to remove. `welfare.left_cage` refuses a future value and refuses one
        longer ago than the ceiling, so a wall clock handed to this cannot be
        mistaken for a duration.

        **Not event-coded yet**, and `welfare.py`'s docstring says what that is
        waiting for: two codes are S2's and `wl-preproc`'s to allocate (ADR-0007),
        and it is asked of the PI rather than taken here. Until then this clock has
        no hardware record, so a restart cannot reconstruct it -- the same gap S8
        §5.2 closed for chair time by coding `HEAD_FIXED`.
        """
        self.welfare.left_cage(seconds_ago, now=self.now())

    def returned_to_cage(self, at: float) -> None:
        """The animal is home. `at` is an instant on `now()`'s clock.

        **Not called by `run()`**, because it is not true when the loop ends: the
        session finishes, then the animal is released, unchaired and walked back,
        and every one of those seconds is inside the limit. `welfare` refuses this
        while the animal is still recorded as head-fixed, so it cannot be used to
        freeze the clock mid-session -- release the head, or send a `Stop`."""
        self.welfare.returned_to_cage(at)

    def head_fixed(self, at: float) -> None:
        """The console action S8 §5.2 requires before a rig session may start.

        Event-coded at both ends, because restraint has no hardware line: the codes
        *are* its durable record, and an offline reader recovers chair time from the
        sync box's capture of them rather than from anything of ours that a crash
        took with it. Chair time stopped bounding the session on 2026-09-19; that is
        why it is still recorded.
        """
        self.welfare.head_fixed(at)
        self.card.emit(self.allocation.code_for("HEAD_FIXED"))

    def head_released(self, at: float) -> None:
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
        """
        if isinstance(command, _link.Stop):
            self.stopped_because = f"stopped by {command.by}"
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
            self.refusals.append((command.name, command.by, str(refused)))
            if len(self.refusals) > _link.REFUSAL_HISTORY:
                self.refusals_dropped += len(self.refusals) - _link.REFUSAL_HISTORY
                del self.refusals[: -_link.REFUSAL_HISTORY]

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
        self.welfare.preflight(self.now())

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
                self.link.publish(_link.Telemetry.of(self, tally, scheduler, index))

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
                stop = self.welfare.must_stop(self.now())
                if stop:
                    self.stopped_because = stop
                    publish()
                    break
                if scheduler.finished:
                    if scheduler.done:
                        self.stopped_because = "every block is finished"
                        publish()
                        break
                    # **A plan can be advanced through only as many times as it has
                    # blocks.** This `continue` runs no trial, draws no condition
                    # and moves no clock, so a scheduler that reported `finished`
                    # and then did not leave the block would spin here forever: no
                    # telemetry would change, `must_stop` would never fire because
                    # `self._elapsed` never moves, and a rig would look like it was
                    # running with an animal in the chair and nothing happening.
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
            self.head_released(self.now())
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
            publish()
            raise
        finally:
            record.close()
            self._record = None
