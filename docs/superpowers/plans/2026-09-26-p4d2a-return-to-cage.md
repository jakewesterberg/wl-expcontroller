# P4d-2a — Close the Out-of-Cage Interval: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every rig session records both ends of its out-of-cage interval, keeps publishing the wall-clock interval after its trial loop ends, and takes the return-to-cage mark from the box — at the terminal or from a console over the existing link.

**Architecture:** `welfare` gains one method mapping a wall instant onto the session clock through the departure. `taskd.Session` gains a phase (`running` → `awaiting_return` → `closed`), a `stop_kind`, a post-loop `await_return()` that publishes and drains the link until the return lands, and writes the mark rows itself. The link gains a `ReturnedToCage` command and telemetry schema 6. `wlx run` runs `await_return` on a background thread while its main thread holds the terminal prompt; `wlx console --returned` sends the command.

**Tech Stack:** Python 3.11–3.13, stdlib `threading`, pyzmq + msgpack (the existing `console` extra, imported lazily), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-P4d2a-return-to-cage-design.md` — read it first; this plan argues from it.

> **Amended 2026-09-26 (spec §10), after the PI's answers on the ELN.** Tasks 1–6 are built.
> Tasks 7–10 below replace the first plan's Tasks 7–8:
> - Task 7 moves every welfare duration onto the wall clock and removes Task 1's
>   `now_from_wall`.
> - Task 8 removes Task 4's `ReturnedToCage`, and Task 6's `--await-return-for` and
>   console race.
> - Task 9 adds the in-session clock, and the phase line the old Task 7 owed.
> - Task 10 proves it and hands it to the PI.
>
> Where an earlier task's text says otherwise, spec §10 wins. Goal and Architecture above
> describe the first plan; the amendment's shape is spec §10.

## Global Constraints

- **Branch, not `main`.** Work in a worktree on branch `p4d2a-return-to-cage` cut from `main`. This slice changes `welfare.py` and touches session-duration tracking, so it is welfare-critical (CLAUDE.md) and **must not merge to `main` until the PI has approved spec §7's numbered list against the finished code**. Push the branch; do not fast-forward `main`.
- **US English** in code, comments and docs.
- **No timing claim without a measurement.** The post-loop `heartbeat` (default 1 s) is a display cadence, and every docstring or doc that mentions it says so. It must stay well inside `ZmqConsole`'s 5 s receive timeout, or a console waiting for the next post-loop frame times out between them. No latency or throughput number enters the repo.
- **Hot path untouched.** Nothing new runs inside `run_trial` or per frame. `await_return` runs only after `run()` has returned or raised.
- **No new dependency.** `link.py` keeps importing `msgpack`/`zmq` lazily inside functions — `tests/test_no_transport_leak.py` enforces it.
- **Every welfare number comes from `welfare`.** Nothing outside `welfare.py` computes an out-of-cage interval, a warning, or a mapping between clocks (S9a §9).
- **Prove each new test can fail** (CLAUDE.md): Task 8 runs the mutation gate and its output is read line by line — `N failed` is a test noticing; `N errors in 0.8s` is not.
- **Never run the suite, edit a test, or `git add` while a mutation sweep is in flight.**
- Commit messages: imperative subject; body says why; end with the two attribution lines the session supplies.
- Run tests with `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider` from the worktree root (the `wl-preproc` symlink or directory must be present, as in CI).

## Review Focus

The five conditions the spec implies that a person will meet and no task's main tests pin — each has its test added to the owning task:

1. **Ctrl-C at the return prompt** → the run ends, the row says `return not recorded (interrupted at the terminal)`, the exit code is 130, nothing hangs. *Task 6.*
2. ~~A console records the return while the terminal prompt is waiting~~ — superseded by spec §10: there is no console return. *Task 8 removes it.*
3. **A return typed before the departure (the wrong day, the wrong half of the day)** → refused with `welfare`'s sentence and asked again, not taken and not fatal. *Task 6.*
4. **A pump fault ends the loop of a `RIG_FIXED` session** → the exception still propagates, and the return can still be recorded because `await_return` releases the head a fault skipped. *Task 5.*
5. **A `SetParameter` or `Stop` arriving after the loop** → refused with a sentence, never applied, the session keeps waiting for the return. *Task 5.*

---

### Task 1: `welfare.now_from_wall` — one mapping between the clocks, shared

> **Superseded (spec §10): Task 7 removed `now_from_wall`.** Kept as the record of what
> Task 1 built.

**Files:**
- Modify: `wl_expcontroller/welfare.py` (add a method after `return_needs_confirmation`; change one line in `returned_to_cage`)
- Test: `tests/test_welfare.py` (three new tests; one line added to `ENTRY_POINTS`)

**Interfaces:**
- Produces: `Welfare.now_from_wall(self, wall_now: float) -> float` — the session-base instant a wall instant corresponds to, through the departure. Raises `Exceeded` for a cage-side session or one with no departure. Tasks 2 and 5 call it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_welfare.py`:

```python
def test_after_the_loop_the_wall_maps_through_the_departure():
    """P4d-2a. The frame clock stops when the loop does and the wall does not, so the
    interval after the last trial can only be read through the departure's anchor --
    the mapping `returned_to_cage` has used since ruling 4 (PI, 2026-09-20)."""
    welfare = _welfare()
    welfare.left_cage(at=WALL_NOW - 100.0, wall_now=WALL_NOW, now=0.0)

    later = welfare.now_from_wall(WALL_NOW + 600.0)

    assert later == pytest.approx(600.0)
    assert welfare.out_of_cage_seconds(later) == pytest.approx(700.0)


def test_a_cage_side_session_has_no_wall_mapping():
    welfare = Welfare(
        bounds=_bounds(),
        pump=Simulated(),
        already_today=0.0,
        deployment=Deployment.CAGE_SIDE,
    )

    with pytest.raises(Exceeded, match="at home"):
        welfare.now_from_wall(WALL_NOW)


def test_a_rig_session_with_no_departure_has_nothing_to_map_through():
    with pytest.raises(Exceeded, match="not recorded as having left its cage"):
        _welfare().now_from_wall(WALL_NOW)
```

And add one line to the `ENTRY_POINTS` dict, in the `# --- welfare: the clocks` group, directly after the `"Welfare.approaching_limit.now"` entry:

```python
    "Welfare.now_from_wall.wall_now": (
        INSTANT,
        lambda v: _marked().now_from_wall(v),
    ),
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q -p no:cacheprovider tests/test_welfare.py -k "wall_maps or wall_mapping or nothing_to_map or entry"`
Expected: FAIL — `AttributeError: 'Welfare' object has no attribute 'now_from_wall'`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/welfare.py`, add this method immediately after `return_needs_confirmation`:

```python
    def now_from_wall(self, wall_now: float) -> float:
        """The session-base instant `wall_now` corresponds to, through the departure.

        **The mapping `returned_to_cage` has made since ruling 4 (PI, 2026-09-20),
        lifted so the clock can be read after the loop as well** (P4d-2a). While the
        loop runs, `now()` and the wall are the same instant and either will do. Once
        it ends the frame clock stops and the wall does not, and only this mapping
        keeps counting the minutes between the last trial and the return -- the ones
        that ruling exists to count.

        **Through `left_cage`'s anchor, never a fresh `now`/`wall_now` pair**, for the
        reason `returned_to_cage` gives: after the loop those two are no longer the
        same instant.

        Refused where there is no anchor, as `out_of_cage_seconds` refuses an unmarked
        rig session: a cage-side session has no interval, and a rig session with no
        departure has one nobody started.
        """
        _finite("the wall clock this session is reading", wall_now)
        if self.deployment is Deployment.CAGE_SIDE:
            raise Exceeded(
                f"this session declares subject {self.bounds.subject!r} is at home, "
                f"so there is no out-of-cage clock to read against the wall"
            )
        if self.left_cage_at is None or self.left_cage_wall_at is None:
            raise Exceeded(
                f"subject {self.bounds.subject!r} is not recorded as having left its "
                f"cage, so the wall clock has no departure to be read through"
            )
        mapped = self.left_cage_at + (wall_now - self.left_cage_wall_at)
        _finite("the session instant the wall clock maps to", mapped)
        return mapped
```

In `returned_to_cage`, replace these two lines:

```python
        returned_at = self.left_cage_at + (at - self.left_cage_wall_at)
        _finite("the time the animal went back into its cage", returned_at)
```

with:

```python
        returned_at = self.now_from_wall(at)
```

Keep the comment above them, and change its first sentence to: `# Mapped through the departure by the one method that does it -- see now_from_wall.`

- [ ] **Step 4: Run the welfare tests**

Run: `python -m pytest -q -p no:cacheprovider tests/test_welfare.py`
Expected: all pass, including every existing `returned_to_cage` test and the entry-point census.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/welfare.py tests/test_welfare.py
git commit -m "Read the wall through the departure in one place, so the clock survives the loop"
```

---

### Task 2: Telemetry schema 6 — `phase` and `stop_kind`, and a clock that can outlive the loop

> **Superseded in part (spec §10): Task 7 removed `Session.welfare_now`**; every welfare
> call reads `Session.wall_now()`. The rest of this task stands.

**Files:**
- Modify: `wl_expcontroller/link.py` (`SCHEMA`, `Telemetry` fields, `Telemetry.of`, `encode`, `decode`)
- Modify: `wl_expcontroller/taskd.py` (new fields; `welfare_now`, `duration_warning`, `_publish`; `run()` stores its state; the four stop sites set `stop_kind`)
- Test: `tests/test_link.py`, `tests/test_taskd.py`, `tests/test_cli.py` (builder only)

**Interfaces:**
- Consumes: `Welfare.now_from_wall(wall_now) -> float` (Task 1).
- Produces:
  - `link.SCHEMA == 6`; `Telemetry.phase: str` (`"running"`, `"awaiting_return"`, `"closed"`); `Telemetry.stop_kind: str | None` (`"completed"`, `"operator"`, `"limit"`, `"fault"`, or `None`).
  - `Session.phase: str` — `""` before `run()` opens the record, then `"running"`; Task 5 moves it on.
  - `Session.stop_kind: str | None`.
  - `Session.welfare_now() -> float`; `Session.duration_warning() -> str | None`; `Session._publish() -> None`.
  - `Session._tally`, `Session._scheduler`, `Session._index` — the loop's state, kept for Task 5.

- [ ] **Step 1: Write the failing tests**

In `tests/test_link.py`, extend the `SimpleNamespace` returned by `_session_with` with four entries (after `now=lambda: 0.0,`):

```python
        phase="running",
        stop_kind=None,
        welfare_now=lambda: 0.0,
        duration_warning=lambda: welfare.approaching_limit(0.0),
```

and append:

```python
def test_the_phase_and_the_kind_of_stop_survive_the_wire():
    """Schema 6 (P4d-2a). A console built against 5 would render an awaiting-return
    frame's advancing clock as a running session, which is why the version moved."""
    original = _telemetry(phase="awaiting_return", stop_kind="limit")

    restored = decode(encode(original))

    assert restored == original
    assert restored.schema == 6


def test_a_running_sessions_stop_kind_is_none_on_the_wire_and_never_empty():
    restored = decode(encode(_telemetry()))

    assert restored.stop_kind is None
    assert restored.phase == "running"
```

In `tests/test_cli.py`, add two keyword arguments to the `Telemetry(...)` in `_telemetry`, after `stopped_because="",`:

```python
        stop_kind=None,
        phase="running",
```

In `tests/test_taskd.py`, append:

```python
def test_a_session_that_finishes_its_blocks_says_it_completed(tmp_path):
    link = Simulated()
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert link.published[-1].stop_kind == "completed"
    assert link.published[-1].phase == "running"


def test_a_session_a_console_stopped_says_an_operator_stopped_it(tmp_path):
    link = Simulated()
    link.queue(Stop(by="jake"))
    session = _session(_spec(tmp_path, trials=50), link=link)

    session.run()

    assert session.stop_kind == "operator"
    assert link.published[-1].stop_kind == "operator"


def test_a_session_ended_by_its_out_of_cage_ceiling_says_limit(tmp_path):
    link = Simulated()
    session = _session(_spec(tmp_path, trials=10_000), link=link)

    session.run()

    assert "out_of_cage" in session.stopped_because
    assert session.stop_kind == "limit"
    assert link.published[-1].stop_kind == "limit"


def test_a_session_ended_by_a_fault_says_fault(tmp_path):
    class Broken:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    link = Simulated()
    session = Session(
        _spec(tmp_path, trials=200),
        card=Card(),
        pump=Broken(),
        link=link,
        wall_clock=lambda: WALL_NOW,
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=0.0)

    with pytest.raises(RuntimeError, match="solenoid"):
        session.run()

    assert session.stop_kind == "fault"
    assert link.published[-1].stop_kind == "fault"


def test_before_the_loop_a_session_has_no_phase(tmp_path):
    session = _session(_spec(tmp_path, trials=3))

    assert session.phase == ""
    assert session.stop_kind is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_taskd.py -k "phase or stop_kind or completed or operator_stopped or says_limit or says_fault or no_phase or survive_the_wire"`
Expected: FAIL — `TypeError: Telemetry.__init__() got an unexpected keyword argument 'phase'` (link) and `AttributeError: 'Session' object has no attribute 'stop_kind'` (taskd).

- [ ] **Step 3: Implement — `link.py`**

Change `SCHEMA = 5` to `SCHEMA = 6`, and add this sentence to the comment block directly above `SCHEMA` (create one line if there is none): `#: 6 (2026-09-26, P4d-2a): `phase` and `stop_kind`. A console built against 5 renders an awaiting-return frame's advancing clock as a running session.`

In `class Telemetry`, directly after the `stopped_because: str` field, add:

```python
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
```

In `Telemetry.of`, directly after `stopped_because=session.stopped_because,`, add:

```python
            stop_kind=session.stop_kind,
            phase=session.phase,
```

and replace the three welfare clock lines with:

```python
            # `welfare_now()`, not `now()`: after the loop the frame clock has
            # stopped and the wall has not (P4d-2a). Both are `Session`'s to say.
            out_of_cage_seconds=session.welfare.out_of_cage_seconds(
                session.welfare_now()
            ),
            chair_seconds=session.welfare.chair_seconds(session.welfare_now()),
```

and

```python
            duration_warning=session.duration_warning(),
```

In `encode`, after `"stopped_because": telemetry.stopped_because,` add `"stop_kind": telemetry.stop_kind,` and `"phase": telemetry.phase,`. In `decode`, after `stopped_because=data["stopped_because"],` add `stop_kind=data["stop_kind"],` and `phase=data["phase"],`.

- [ ] **Step 4: Implement — `taskd.py`**

Add `import threading` beside `import time`. Add these fields to `Session`, after `_record`:

```python
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
```

Add these methods in the `# --- the clock ---` section, after `wall_now`:

```python
    def welfare_now(self) -> float:
        """The session-base instant the welfare clocks are read at.

        `now()` while the loop runs. **After it, the wall mapped through the
        departure** (P4d-2a): the frame clock stopped with the last trial and the
        interval did not, and `welfare.now_from_wall` is the one place that mapping
        is made.
        """
        if self.phase == "awaiting_return":
            return self.welfare.now_from_wall(self.wall_now())
        return self.now()

    def duration_warning(self) -> str | None:
        """What an operator must be told about the time left out of the cage.

        `approaching_limit`'s sentence, as during the loop. **After the loop, past the
        limit, `must_stop`'s** (P4d-2a spec §4): there is no loop left to stop, and
        the warning is what tells someone the animal is still out.
        """
        at = self.welfare_now()
        warning = self.welfare.approaching_limit(at)
        if warning is None and self.phase == "awaiting_return":
            warning = self.welfare.must_stop(at)
        return warning
```

Add `_publish` just before `run`:

```python
    def _publish(self) -> None:
        """One frame from the state the loop last left -- the body of `run()`'s
        `publish`, kept callable after the loop so `await_return` publishes the same
        shape rather than a second one."""
        self.link.publish(
            _link.Telemetry.of(self, self._tally, self._scheduler, self._index)
        )
```

In `run()`, directly after `record.snapshot(...)` and before `try:`, add:

```python
        self._tally = tally
        self._scheduler = scheduler
        self._index = 0
        self.phase = "running"
```

Replace the body of the `publish()` closure (keep its docstring) with:

```python
                self._index = index
                self._publish()
```

Set `stop_kind` at the four stop sites:
- in `_command`, the `Stop` branch: `self.stopped_because = f"stopped by {command.by}"` then `self.stop_kind = "operator"`
- after `stop = self.welfare.must_stop(self.now())`: `self.stopped_because = stop` then `self.stop_kind = "limit"`
- `self.stopped_because = "every block is finished"` then `self.stop_kind = "completed"`
- in `except Exception as fault:`, after the `stopped_because` assignment: `self.stop_kind = "fault"`

- [ ] **Step 5: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass. If a test elsewhere builds `Telemetry(...)` or a `Telemetry.of` stand-in and now fails on the new fields, give it `stop_kind=None, phase="running"` (a `Telemetry`) or the four stand-in entries above.

- [ ] **Step 6: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/taskd.py tests/test_link.py tests/test_taskd.py tests/test_cli.py
git commit -m "Say what kind of stop ended a session, and which phase it is in"
```

---

### Task 3: The marks write their own rows

**Files:**
- Modify: `wl_expcontroller/taskd.py` (`left_cage`, `returned_to_cage`, new `return_needs_confirmation`, `return_not_recorded`, `_note`; import `welfare_note`)
- Test: `tests/test_taskd.py`

**Interfaces:**
- Consumes: `record.welfare_note(directory, *, kind, subject, was, now, reason, by, how, recorded_at)` (exists).
- Produces:
  - `Session.left_cage(self, at: float, confirmed: bool = False, by: str = "", how: str = "terminal") -> None` — writes a `departure` row once the mark is accepted.
  - `Session.returned_to_cage(self, at: float, confirmed: bool = False, by: str = "", how: str = "terminal") -> None` — under `_mark_lock`; writes `returned`, and `return confirmed` when a far return was confirmed.
  - `Session.return_needs_confirmation(self, at: float) -> str | None`.
  - `Session.return_not_recorded(self, why: str) -> None` — writes `return not recorded` with `reason=why`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_taskd.py`:

```python
def _welfare_notes(session: Session) -> list[dict]:
    path = session.directory / "welfare_notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _chaired(tmp_path, **kwargs) -> Session:
    """A rig session with no head-fixation, so a return is refused for nothing but
    what the test is about."""
    spec = _spec(tmp_path, trials=3, deployment=Deployment.RIG_CHAIRED, **kwargs)
    return Session(spec, card=Card(), pump=Pump(), wall_clock=lambda: WALL_NOW)


def test_a_departure_is_recorded_whether_or_not_anyone_confirmed_it(tmp_path):
    """P4d-2a spec §1 item 2: the one number that bounds a session was in the record
    only when a far mark was confirmed or amended."""
    session = _session(_spec(tmp_path, trials=3), left_cage_ago=60.0)

    rows = _welfare_notes(session)

    assert [row["kind"] for row in rows] == ["departure"]
    assert rows[0]["was"] == WALL_NOW - 60.0
    assert rows[0]["how"] == "terminal"


def test_a_return_is_recorded_with_who_and_how(tmp_path):
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW - 60.0)

    session.returned_to_cage(at=WALL_NOW, by="jake", how="console")

    rows = _welfare_notes(session)
    assert [row["kind"] for row in rows] == ["departure", "returned"]
    assert rows[1]["now"] == WALL_NOW
    assert rows[1]["by"] == "jake"
    assert rows[1]["how"] == "console"


def test_a_far_return_that_was_confirmed_says_so(tmp_path):
    session = _chaired(tmp_path, bounds=_bounds(out_of_cage=43_200.0))
    session.left_cage(at=WALL_NOW - 7_200.0, confirmed=True)

    session.returned_to_cage(at=WALL_NOW - 3_600.0, confirmed=True, by="jake")

    kinds = [row["kind"] for row in _welfare_notes(session)]
    assert kinds == ["departure", "returned", "return confirmed"]


def test_a_refused_return_writes_no_row(tmp_path):
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW - 60.0)

    with pytest.raises(Exceeded, match="before|negative"):
        session.returned_to_cage(at=WALL_NOW - 120.0)

    assert [row["kind"] for row in _welfare_notes(session)] == ["departure"]


def test_a_return_nobody_recorded_says_why(tmp_path):
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW - 60.0)

    session.return_not_recorded("no terminal and no console attached")

    rows = _welfare_notes(session)
    assert rows[-1]["kind"] == "return not recorded"
    assert rows[-1]["reason"] == "no terminal and no console attached"


def test_the_session_says_when_a_return_needs_a_person(tmp_path):
    session = _chaired(tmp_path, bounds=_bounds(out_of_cage=43_200.0))
    session.left_cage(at=WALL_NOW - 7_200.0, confirmed=True)

    assert session.return_needs_confirmation(WALL_NOW - 60.0) is None
    assert "Confirm it" in session.return_needs_confirmation(WALL_NOW - 3_600.0)
```

Add `from wl_expcontroller.bounds import ... Exceeded` if the import line lacks it (it already imports `Exceeded`).

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q -p no:cacheprovider tests/test_taskd.py -k "recorded or confirmed_says or refused_return or needs_a_person"`
Expected: FAIL — no `welfare_notes.jsonl` rows; `TypeError: returned_to_cage() got an unexpected keyword argument 'by'`; `AttributeError: ... 'return_not_recorded'`.

- [ ] **Step 3: Implement**

Change the record import in `taskd.py` to:

```python
from wl_expcontroller.record import EXPCONTROLLER_DIRNAME, SessionRecord, welfare_note
```

Add a private helper in the `# --- out of cage, and restraint ---` section:

```python
    def _note(self, kind: str, at: float, by: str, how: str, reason: str = "") -> None:
        """One mark row in `welfare_notes.jsonl` (P4d-2a spec §3).

        Written by the mark methods themselves, so every caller -- the terminal, a
        console over the link, P4d-2b's browser -- leaves the same row and none can
        reach the mark around it. `was` and `now` are both the mark's instant: nothing
        was amended, so there is one value to record.
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
```

Replace `left_cage`'s signature and body (keep the docstring, and add a final paragraph: `**It writes the \`departure\` row itself** (P4d-2a spec §3), once \`welfare\` has accepted the mark, so a refused departure leaves no row.`):

```python
    def left_cage(
        self, at: float, confirmed: bool = False, by: str = "", how: str = "terminal"
    ) -> None:
        self.welfare.left_cage(
            at, wall_now=self.wall_now(), now=self.now(), confirmed=confirmed
        )
        self._note("departure", at, by, how)
```

Add the passthrough after `departure_needs_confirmation`:

```python
    def return_needs_confirmation(self, at: float) -> str | None:
        """What a person must be shown before `returned_to_cage(at)`, or `None`.

        The passthrough `returned_to_cage`'s docstring said would arrive "when
        P4d-2's console prompts too": `wlx run`'s return prompt is its caller
        (P4d-2a). `wall_now()` is this object's seam onto the wall, for the reason
        `departure_needs_confirmation` gives.
        """
        return self.welfare.return_needs_confirmation(at, wall_now=self.wall_now())
```

Replace `returned_to_cage`'s signature and body. Keep its docstring, but delete the paragraph beginning `**There is deliberately no \`return_needs_confirmation\` passthrough` (the passthrough now exists and has a caller) and add: `**Under \`_mark_lock\`** (P4d-2a): the terminal and a console can both offer the return, and \`welfare\`'s check-then-set must not interleave. The first accepted mark wins; the second is refused by \`welfare\`'s own sentence.`

```python
    def returned_to_cage(
        self, at: float, confirmed: bool = False, by: str = "", how: str = "terminal"
    ) -> None:
        with self._mark_lock:
            wall_now = self.wall_now()
            far = self.welfare.return_needs_confirmation(at, wall_now)
            self.welfare.returned_to_cage(at, wall_now=wall_now, confirmed=confirmed)
            self._note("returned", at, by, how)
            if far is not None:
                self._note("return confirmed", at, by, how)
```

Add after it:

```python
    def return_not_recorded(self, why: str) -> None:
        """Say in the record why the interval was left open (P4d-2a spec §3).

        A process killed outright cannot write this, and then the missing `returned`
        row is the signal; every other way of ending without a return says why.
        """
        self._note("return not recorded", self.wall_now(), "", "wlx run", reason=why)
```

- [ ] **Step 4: Run the taskd and CLI tests**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py tests/test_cli.py`
Expected: the new tests pass. **Three existing `test_cli.py` tests now fail, correctly**, because a `departure` row is written first: the ones asserting `[row["kind"] for row in rows] == ["departure confirmed"]` (twice) and `== ["departure amended"]`. Do **not** fix them in this task — Task 6 changes the same runs again (the return rows) and sets their final expected lists once. Record their names in the commit body.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/taskd.py tests/test_taskd.py
git commit -m "Record both marks every time, from the one method each mark goes through"
```

---

### Task 4: `ReturnedToCage` on the link, and one route for every command

**Files:**
- Modify: `wl_expcontroller/link.py` (`ReturnedToCage`, `Command`, `_encode_command`, `_decode_command`)
- Modify: `wl_expcontroller/taskd.py` (`_command`, new `_refuse`)
- Test: `tests/test_link.py`, `tests/test_taskd.py`

**Interfaces:**
- Consumes: `Session.returned_to_cage(at, confirmed, by, how)` (Task 3); `Session.phase`, `Session.stop_kind` (Task 2).
- Produces:
  - `link.ReturnedToCage(at: float, by: str, confirmed: bool)` — frozen, slotted dataclass; `at` a POSIX wall instant. Wire kind `"returned"`.
  - `link.Command = SetParameter | Stop | ReturnedToCage`.
  - `Session._refuse(name: str, by: str, why: str) -> None` — appends to `refusals` and caps at `REFUSAL_HISTORY`.
  - `_command` routes `ReturnedToCage` to `returned_to_cage(..., how="console")` in any phase; refuses `SetParameter`/`Stop` once `phase != "running"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_link.py` (add `ReturnedToCage` to its `wl_expcontroller.link` import):

```python
def test_a_return_to_the_cage_crosses_a_real_socket(zmq_cleanup):
    """P4d-2a. The mark a console sends is a POSIX wall instant, a name, and whether
    a person confirmed a far time -- all three must arrive as sent."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    console.send(ReturnedToCage(at=1_700_000_123.5, by="jake", confirmed=True))

    assert _drain_until(link) == [
        ReturnedToCage(at=1_700_000_123.5, by="jake", confirmed=True)
    ]
```

Append to `tests/test_taskd.py` (add `ReturnedToCage` to its `wl_expcontroller.link` import):

```python
def test_a_console_return_during_the_loop_ends_a_chaired_session(tmp_path):
    """A chaired animal can be walked home mid-session, and the loop must not run a
    trial outside the interval: `must_stop` answers for a closed one."""
    link = Simulated()
    link.queue(ReturnedToCage(at=WALL_NOW, by="jake", confirmed=False))
    spec = _spec(tmp_path, trials=50, deployment=Deployment.RIG_CHAIRED)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=lambda: WALL_NOW)
    session.left_cage(at=WALL_NOW)

    session.run()

    assert "back in its cage" in session.stopped_because
    assert session.stop_kind == "limit"
    assert [r["how"] for r in _welfare_notes(session) if r["kind"] == "returned"] == ["console"]


def test_a_console_return_while_the_head_is_fixed_is_refused_and_the_session_runs_on(tmp_path):
    link = Simulated()
    link.queue(ReturnedToCage(at=WALL_NOW, by="jake", confirmed=False))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.stop_kind == "completed"
    names = [name for name, _by, _why in session.refusals]
    assert names == ["returned_to_cage"]
    assert "head-fixed" in session.refusals[0][2]
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_taskd.py -k "return_to_the_cage or console_return"`
Expected: FAIL — `ImportError: cannot import name 'ReturnedToCage'`.

- [ ] **Step 3: Implement — `link.py`**

After `class Stop`, add:

```python
@dataclass(frozen=True, slots=True)
class ReturnedToCage:
    """The animal is home (P4d-2a). `at` is a POSIX wall instant -- a clock time is
    what an operator reads (PI, 2026-09-20, ruling 4). `confirmed` says a person
    acted on a time more than thirty minutes off; `welfare.returned_to_cage` refuses
    a far one without it, and that refusal comes back as a `Refused` with the
    sentence a person needs. Carries the request, never a second validator."""

    at: float
    by: str
    confirmed: bool
```

Change `Command = SetParameter | Stop` to `Command = SetParameter | Stop | ReturnedToCage`.

In `_encode_command`, before the `else:`, add:

```python
    elif isinstance(command, ReturnedToCage):
        payload = {
            "kind": "returned",
            "at": command.at,
            "by": command.by,
            "confirmed": command.confirmed,
        }
```

In `_decode_command`, before the final `raise`, add:

```python
    if kind == "returned":
        return ReturnedToCage(
            at=data["at"], by=data["by"], confirmed=data["confirmed"]
        )
```

Update `_encode_command`'s docstring first line to `` `SetParameter`/`Stop`/`ReturnedToCage` to msgpack, ... ``.

- [ ] **Step 4: Implement — `taskd.py`**

Add `_refuse` directly before `_command`:

```python
    def _refuse(self, name: str, by: str, why: str) -> None:
        """One refusal onto the capped list -- see `refusals`."""
        self.refusals.append((name, by, why))
        if len(self.refusals) > _link.REFUSAL_HISTORY:
            self.refusals_dropped += len(self.refusals) - _link.REFUSAL_HISTORY
            del self.refusals[: -_link.REFUSAL_HISTORY]
```

Replace `_command`'s body (keep its docstring; append a paragraph: `**The return is accepted in any phase; nothing else is, once the loop has ended** (P4d-2a). A parameter staged after the last trial could never be applied, and a stop has nothing left to stop -- both are refused with the reason rather than silently kept.`):

```python
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
```

- [ ] **Step 5: Run the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_taskd.py tests/test_no_transport_leak.py`
Expected: all pass (`test_cli.py`'s three known failures from Task 3 remain until Task 6).

- [ ] **Step 6: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/taskd.py tests/test_link.py tests/test_taskd.py
git commit -m "Let a console send the return to the cage, and route every command one way"
```

---

### Task 5: `Session.await_return` — the clock stays visible until the animal is home

**Files:**
- Modify: `wl_expcontroller/taskd.py` (new method, after `run`)
- Test: `tests/test_taskd.py`

**Interfaces:**
- Consumes: `_publish`, `welfare_now`, `duration_warning`, `phase` (Task 2); `returned_to_cage`, `head_released` (existing/Task 3); `_command` (Task 4).
- Produces: `Session.await_return(self, give_up: threading.Event, heartbeat: float = 1.0) -> None`. Returns when the return is recorded (after publishing one `closed` frame) or when `give_up` is set (publishing nothing further). Returns at once for a cage-side session. Raises `RuntimeError` if `run()` never opened the record.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_taskd.py` (add `import threading` and `import time` to the imports):

```python
class _Wall:
    """A wall clock a test can move."""

    def __init__(self, at: float) -> None:
        self.at = at

    def __call__(self) -> float:
        return self.at


def _until(predicate, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def _awaiting(session: Session, **kwargs) -> tuple[threading.Thread, threading.Event]:
    give_up = threading.Event()
    thread = threading.Thread(
        target=session.await_return, args=(give_up,), kwargs={"heartbeat": 0.01, **kwargs}
    )
    thread.start()
    return thread, give_up


def _chaired_and_run(tmp_path, link, wall) -> Session:
    spec = _spec(tmp_path, trials=3, deployment=Deployment.RIG_CHAIRED)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=wall)
    session.left_cage(at=WALL_NOW)
    session.run()
    return session


def test_after_the_loop_the_out_of_cage_clock_keeps_running_on_the_wall(tmp_path):
    """P4d-2a spec §1 item 4: the clock went dark when the loop ended."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _chaired_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 600.0

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        frame = link.published[-1]
        assert frame.out_of_cage_seconds == pytest.approx(600.0)
        assert frame.stop_kind == "completed"
    finally:
        give_up.set()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert link.published[-1].phase == "awaiting_return", "no return, so never closed"


def test_past_the_limit_after_the_loop_the_warning_says_so(tmp_path):
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _chaired_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 900.0  # `_bounds()`' ceiling is 800 s

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: link.published[-1].phase == "awaiting_return")
        assert "against a ceiling of" in link.published[-1].duration_warning
    finally:
        give_up.set()
        thread.join(timeout=2)


def test_a_console_return_after_the_loop_closes_the_interval(tmp_path):
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _chaired_and_run(tmp_path, link, wall)
    wall.at = WALL_NOW + 120.0
    link.queue(ReturnedToCage(at=WALL_NOW + 60.0, by="jake", confirmed=False))

    session.await_return(threading.Event(), heartbeat=0.01)

    assert session.phase == "closed"
    assert link.published[-1].phase == "closed"
    assert link.published[-1].out_of_cage_seconds == pytest.approx(60.0)
    assert [r["kind"] for r in _welfare_notes(session)][-1] == "returned"


def test_after_the_loop_a_parameter_or_a_stop_is_refused_not_applied(tmp_path):
    """Review Focus 5."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _chaired_and_run(tmp_path, link, wall)
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))
    link.queue(Stop(by="sam"))

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: len(session.refusals) == 2)
    finally:
        give_up.set()
        thread.join(timeout=2)

    assert [(n, b) for n, b, _ in session.refusals] == [("fix_hold", "jake"), ("stop", "sam")]
    assert all("waiting for the animal's return" in why for _, _, why in session.refusals)
    assert session.staged == ()
    assert session.stop_kind == "completed", "a late stop changes nothing"


def test_a_fault_skipped_the_release_and_the_return_can_still_land(tmp_path):
    """Review Focus 4, and P4d-2a spec §1 item 3: a fault re-raises past the release
    at the end of `run()`, and `welfare` refuses a return for a head still fixed."""

    class Broken:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    link = Simulated()
    session = Session(
        _spec(tmp_path, trials=200), card=Card(), pump=Broken(), link=link,
        wall_clock=lambda: WALL_NOW,
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=0.0)
    with pytest.raises(RuntimeError, match="solenoid"):
        session.run()
    assert session.welfare.released_at is None, "the gap this test closes"
    link.queue(ReturnedToCage(at=WALL_NOW, by="jake", confirmed=False))

    session.await_return(threading.Event(), heartbeat=0.01)

    assert session.welfare.released_at is not None
    assert session.welfare.returned_at is not None
    assert link.published[-1].phase == "closed"
    assert link.published[-1].stop_kind == "fault"


def test_a_cage_side_session_has_no_return_to_await(tmp_path):
    link = Simulated()
    spec = _spec(tmp_path, trials=3, deployment=Deployment.CAGE_SIDE)
    session = Session(spec, card=Card(), pump=Pump(), link=link, wall_clock=lambda: WALL_NOW)
    session.run()
    published = len(link.published)

    session.await_return(threading.Event(), heartbeat=0.01)

    assert len(link.published) == published


def test_await_return_before_the_loop_is_refused(tmp_path):
    session = _chaired(tmp_path)
    session.left_cage(at=WALL_NOW)

    with pytest.raises(RuntimeError, match="before run"):
        session.await_return(threading.Event())
```

If `_spec`'s cage-side session is refused by `welfare.preflight` for some other reason, read the refusal and give the spec what a cage-side session needs; do not weaken the assertion.

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q -p no:cacheprovider tests/test_taskd.py -k "after_the_loop or past_the_limit or fault_skipped or cage_side_session_has_no or before_the_loop_is_refused"`
Expected: FAIL — `AttributeError: 'Session' object has no attribute 'await_return'`.

- [ ] **Step 3: Implement**

Add after `run()` in `taskd.py`:

```python
    def await_return(self, give_up: threading.Event, heartbeat: float = 1.0) -> None:
        """Keep a rig session's out-of-cage clock visible until the animal is home.

        **P4d-2a.** Since ruling 4 (PI, 2026-09-20) the interval runs on the wall
        until the return, but nothing published it after the last trial, so a console
        showed a frozen clock and a limit crossed after the loop was seen by nobody.
        This publishes a frame every `heartbeat` seconds -- **a display cadence for a
        console, not a measurement of this system**, and well inside `ZmqConsole`'s
        5 s receive timeout so a waiting console never times out between frames -- with
        the clock read through
        `welfare_now()`, and drains the link, where the return may arrive.

        **It ends when the return is recorded**, by a console through `_command` or by
        the terminal through `returned_to_cage` from another thread, and then
        publishes one `closed` frame. **It never ends on its own otherwise**: `give_up`
        is its owner's to set, and then it publishes nothing further and the owner
        writes `return_not_recorded`.

        **A head a fault left fixed is released first.** `run()` releases it at a
        normal end, but a fault re-raises past that, and `welfare` refuses a return
        while the head is recorded as fixed. Head-post release bounds nothing (PI,
        2026-09-19, restated 2026-09-26), so it is marked here rather than asked for.

        A cage-side session has no interval, and this returns at once.
        """
        if self.spec.deployment is Deployment.CAGE_SIDE:
            return
        if self._scheduler is None:
            raise RuntimeError(
                "await_return before run() opened the record: there is no session "
                "whose clock could be published"
            )
        if self.welfare.fixed_at is not None and self.welfare.released_at is None:
            self.head_released(self.now())
        self.phase = "awaiting_return"
        while self.welfare.returned_at is None and not give_up.is_set():
            for command in self.link.drain():
                self._command(command, self._index)
            if self.welfare.returned_at is not None:
                break
            self._publish()
            give_up.wait(heartbeat)
        if self.welfare.returned_at is not None:
            self.phase = "closed"
            self._publish()
```

- [ ] **Step 4: Run the taskd tests**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py`
Expected: all pass. Run it three times; a test that passes twice and fails once is a race in the test's waiting, and is fixed by waiting on a condition, never by a longer sleep.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/taskd.py tests/test_taskd.py
git commit -m "Keep the out-of-cage clock published until the animal is home"
```

---

### Task 6: `wlx run` takes the return, and says why when it cannot

**Files:**
- Modify: `wl_expcontroller/cli.py` (`_clock_or_now`, `_settle_return`, `_close_interval`, `--await-return-for`, the `run` branch)
- Test: `tests/test_cli.py` (new tests; three existing assertions updated; two `--link` tests adapted)

**Interfaces:**
- Consumes: `Session.await_return`, `return_needs_confirmation`, `returned_to_cage`, `return_not_recorded`, `phase`, `welfare.returned_at` (Tasks 2–5); `link.ReturnedToCage` (Task 4).
- Produces:
  - `cli._clock_or_now(text: str) -> float` — `time.time()` for `now` (any case), else `_wall_clock_time(text)`. Task 7 uses it.
  - `cli._settle_return(session, actor: str, attempts: int = 3) -> str | None` — `None` once the return is recorded (here or by a console); otherwise the reason it was not.
  - `cli._close_interval(session, args, linked: bool) -> bool` — `True` if the operator interrupted.
  - `wlx run --await-return-for SECONDS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` (add `ReturnedToCage` to its `wl_expcontroller.link` import):

```python
# ---------------------------------------------------------------------------
# P4d-2a: the return to the cage
# ---------------------------------------------------------------------------


def _kinds(tmp_path) -> list[str]:
    return [row["kind"] for row in _notes(tmp_path)]


def test_a_headless_run_records_that_nobody_could_mark_the_return(tmp_path):
    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "return not recorded"]
    assert _notes(tmp_path)[-1]["reason"] == "no terminal and no console attached"


def test_a_run_at_a_terminal_takes_the_return(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "now")

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "returned"]
    assert _notes(tmp_path)[-1]["how"] == "terminal"


def test_a_far_return_is_confirmed_at_the_terminal(tmp_path, monkeypatch):
    answers = iter([_hours_ago(1), "confirm"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    exit_code = main(
        _run_args(tmp_path, "--out-of-cage-at", _hours_ago(2), "--confirm-out-of-cage")
    )

    assert exit_code == 0
    assert _kinds(tmp_path) == [
        "departure", "departure confirmed", "returned", "return confirmed",
    ]


def test_a_return_before_the_departure_is_refused_and_asked_again(tmp_path, monkeypatch):
    """Review Focus 3: the wrong half of the day, typed at the prompt."""
    answers = iter([_hours_ago(3), "confirm", "now"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    exit_code = main(
        _run_args(tmp_path, "--out-of-cage-at", _hours_ago(2), "--confirm-out-of-cage")
    )

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "departure confirmed", "returned"]


def test_three_answers_that_are_not_a_time_end_the_prompt_and_say_so(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "confirm")

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 0
    assert _kinds(tmp_path) == ["departure", "return not recorded"]
    assert _notes(tmp_path)[-1]["reason"] == "no clock time given at the terminal"


def test_an_interrupted_return_prompt_is_recorded_and_exits_130(tmp_path, monkeypatch):
    """Review Focus 1."""

    def interrupt(_prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", interrupt)

    exit_code = main(_run_args(tmp_path, "--out-of-cage-at", _hhmm()))

    assert exit_code == 130
    assert _kinds(tmp_path) == ["departure", "return not recorded"]
    assert _notes(tmp_path)[-1]["reason"] == "interrupted at the terminal"


def test_a_console_can_record_the_return_while_the_terminal_waits(tmp_path, monkeypatch):
    """Review Focus 2. The prompt is blocked in `input()` when the console's mark
    lands; the next answer is told so, and there is one `returned` row, not two."""
    from wl_expcontroller.cli import _settle_return
    from wl_expcontroller.dio import Simulated as Card
    from wl_expcontroller.taskd import Session, SessionSpec
    from wl_expcontroller.welfare import Deployment, Simulated as Pump

    spec = SessionSpec(
        task=GOOD, allocation=ALLOCATION, root=tmp_path, session_id="2027-01-14_01",
        subject="REFERENCE", trials=3, frame_period=1 / 240, seed=1, values={},
        bounds=_load_bounds_for_test(tmp_path), already_delivered_today=0.0,
        deployment=Deployment.RIG_CHAIRED,
    )
    session = Session(spec, card=Card(), pump=Pump())
    session.left_cage(at=time.time() - 60.0)

    def answer(_prompt=""):
        session.returned_to_cage(time.time(), by="sam", how="console")
        return "now"

    monkeypatch.setattr("builtins.input", answer)

    assert _settle_return(session, "jake") is None
    kinds = _kinds(tmp_path)
    assert kinds.count("returned") == 1
    assert _notes(tmp_path)[-1]["how"] == "console"
```

Add this helper beside `_far_bounds` (it loads the same file `_far_bounds` writes):

```python
def _load_bounds_for_test(tmp_path):
    from wl_expcontroller.cli import _load_bounds

    return _load_bounds(_far_bounds(tmp_path))
```

Update the three existing assertions Task 3 left failing, to the lists these runs now produce:
- the test asserting `["departure confirmed"]` for a **flag** confirmation with no terminal → `["departure", "departure confirmed", "return not recorded"]`
- the test asserting `["departure confirmed"]` with `builtins.input` returning `"confirm"` → `["departure", "departure confirmed", "return not recorded"]` (its fixed answer is not a clock time three times)
- `test_an_interactive_run_can_amend_the_time_with_a_reason_and_a_name` → extend its `answers` with a final `"now"`, and assert `["departure", "departure amended", "returned"]`

Adapt the two `wlx run --link` tests, which would otherwise wait for a return nobody sends:
- `test_wlx_run_with_link_closes_it_when_the_session_ends`: add `"--await-return-for", "0",` to its argv.
- `test_wlx_run_with_link_lets_a_real_console_attach`: after `assert stopped == "stopped by jake", stopped`, add:

```python
            # P4d-2a: a rig session now waits, publishing its clock, until the
            # return is marked -- here by the console, which is the only one there is.
            console.send(ReturnedToCage(at=time.time(), by="jake", confirmed=False))
            phase = None
            for _ in range(2000):
                phase = console.receive().phase
                if phase == "closed":
                    break
            assert phase == "closed", phase
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q -p no:cacheprovider tests/test_cli.py -k "return or departure or amend or link"`
Expected: FAIL — `unrecognized arguments: --await-return-for`, `ImportError: cannot import name '_settle_return'`, and wrong row lists.

- [ ] **Step 3: Implement**

In `cli.py`, add `import threading` beside the other imports. Add after `_wall_clock_time`:

```python
def _clock_or_now(text: str) -> float:
    """`now`, or a clock time as `_wall_clock_time` reads one. For the return, which
    is usually marked at the moment it happens (P4d-2a)."""
    if text.strip().lower() == "now":
        return time.time()
    return _wall_clock_time(text)
```

Add after `_settle_departure`:

```python
def _settle_return(session, actor: str, attempts: int = 3) -> str | None:
    """Ask the person at the terminal when the animal went back into its cage.

    **P4d-2a spec §5.** `None` once the return is recorded -- here, or by a console
    while this was waiting -- and otherwise the reason it was not, for the row.

    **The prompt ends.** An empty answer ends it at once, and so do `attempts`
    answers that are not an accepted mark: a prompt that re-asked forever would hang
    any script, and any test, that answers with a fixed string. A far time gets the
    departure's confirmation (PI, 2026-09-20); anything but `confirm` there asks for
    the time again. **There is no amendment**, because nothing has been marked yet
    that one could replace -- a corrected time is simply the time entered.
    """
    for _ in range(attempts):
        if session.welfare.returned_at is not None:
            print("  the return was recorded from a console", file=sys.stderr)
            return None
        raw = _ask("  returned to cage at (HH:MM, or now): ").strip()
        if session.welfare.returned_at is not None:
            print("  the return was recorded from a console", file=sys.stderr)
            return None
        if not raw:
            return "no answer at the terminal"
        try:
            at = _clock_or_now(raw)
        except argparse.ArgumentTypeError as bad:
            print(f"  {bad}", file=sys.stderr)
            continue
        warning = session.return_needs_confirmation(at)
        confirmed = False
        if warning is not None:
            print(f"  WARNING: {warning}", file=sys.stderr)
            answer = _ask(
                "  type `confirm` to accept this return time, or anything else to "
                "give it again: "
            ).strip().lower()
            if answer not in ("c", "confirm"):
                continue
            confirmed = True
        try:
            session.returned_to_cage(at, confirmed=confirmed, by=actor, how="terminal")
        except Exceeded as refused:
            if session.welfare.returned_at is not None:
                print("  the return was recorded from a console", file=sys.stderr)
                return None
            print(f"  refused: {refused}", file=sys.stderr)
            continue
        return None
    return "no clock time given at the terminal"


def _close_interval(session, args, linked: bool) -> bool:
    """Take the return, or record why nobody could (P4d-2a spec §3, §5).

    `await_return` runs on a background thread, publishing the clock and draining
    the link; this thread holds the terminal prompt. **The two meet only at
    `Session._mark_lock`.** Returns `True` if the operator interrupted, so the caller
    can exit 130 as `wlx console` does.
    """
    if session.spec.deployment is Deployment.CAGE_SIDE:
        return False
    if not session.phase:
        session.return_not_recorded("the session did not start")
        return False
    terminal = _at_a_terminal()
    if not terminal and not linked:
        session.return_not_recorded("no terminal and no console attached")
        return False
    give_up = threading.Event()
    waiter = threading.Thread(
        target=session.await_return, args=(give_up,), daemon=True
    )
    waiter.start()
    why = None
    interrupted = False
    try:
        if terminal:
            why = _settle_return(session, args.actor or "")
        elif args.await_return_for is not None:
            waiter.join(timeout=args.await_return_for)
            if session.welfare.returned_at is None:
                why = f"nobody marked it within {args.await_return_for:g} s"
        else:
            waiter.join()
    except KeyboardInterrupt:
        why = "interrupted at the terminal"
        interrupted = True
    finally:
        give_up.set()
        waiter.join()
        if session.welfare.returned_at is None:
            session.return_not_recorded(why or "interrupted at the terminal")
    return interrupted
```

Add the argument to the `run` subparser, beside `--confirm-out-of-cage`:

```python
    run_parser.add_argument(
        "--await-return-for",
        type=float,
        default=None,
        metavar="SECONDS",
        help="with --link and no terminal, how long to wait for a console to mark "
        "the return to the cage before recording that nobody did (P4d-2a). Without "
        "it, such a run waits until the return is marked or it is interrupted",
    )
```

(Use the subparser's actual variable name; read the file.)

In the `run` branch, replace `census = session.run()` with:

```python
            interrupted = False
            try:
                census = session.run()
            finally:
                interrupted = _close_interval(
                    session, args, linked=opened_link is not None
                )
```

and change the final `return 1 if census.hangs else 0` to:

```python
            if interrupted:
                print(
                    "run: interrupted -- the return to the cage was not recorded",
                    file=sys.stderr,
                )
                return 130
            return 1 if census.hangs else 0
```

- [ ] **Step 4: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass. Run `tests/test_cli.py` three times; the `--link` tests must not flake.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/cli.py tests/test_cli.py
git commit -m "Take the return at the terminal, and record why when nobody can"
```

---

### Task 7: Every welfare duration on the wall clock (welfare-critical)

**Why:** spec §10, item 1. Task 6's implementer found the fault. `Session.now()` is
accumulated frame time, which outruns the wall in the simulator. The frame-based interval
and a wall-mapped return therefore disagree. With the default `rig-fixed` deployment, a
simulated session's first post-loop frame is refused by the restraint cross-check, and its
return is refused as "before the head release".

**Files:**
- Modify: `wl_expcontroller/welfare.py`, `wl_expcontroller/taskd.py`, `wl_expcontroller/link.py` (`Telemetry.of`), `wl_expcontroller/cli.py` (the `head_fixed` call, and the interval printed at session start)
- Modify tests: `tests/test_welfare.py`, `tests/test_taskd.py`, `tests/test_cli.py`, `tests/test_link.py`, and every other test that builds a departure or restraint mark in the session base. Grep for `left_cage(`, `now_from_wall`, `welfare_now`, `out_of_cage_seconds(`, `chair_seconds(`, `head_fixed(`, `head_released(`, `must_stop(`, `approaching_limit(`, `preflight(`.
- Modify docs: every mention of `now_from_wall` in the repo (grep). This includes the S8 §5.2d refusal-table rows and the entry-point census line that Task 1 added. Each mention is removed or rewritten; none is left describing a function that no longer exists.

**Interfaces (after this task):**
- `Welfare.left_cage(at: float, wall_now: float, confirmed: bool = False) -> None`: no `now` parameter; the departure is kept as a wall instant.
- `Welfare.returned_to_cage(at: float, wall_now: float, confirmed: bool = False) -> None`: the return is kept as a wall instant.
- `Welfare.out_of_cage_seconds(wall_now)`, `preflight(wall_now)`, `must_stop(wall_now)`, `approaching_limit(wall_now)`, `chair_seconds(wall_now)`: every argument is a POSIX wall instant.
- `Welfare.head_fixed(at)`, `Welfare.head_released(at)`: wall instants.
- `Welfare.now_from_wall`: removed. `Session.welfare_now()`: removed; every caller uses `Session.wall_now()`. `Session.now()` (frame time) stays for trial timing and is passed to `welfare` nowhere.
- **A field whose base changes is renamed**, so no reader silently gets the other base. For example, `left_cage_at` + `left_cage_wall_at` become one `left_cage_wall_at`, `returned_at` becomes `returned_wall_at`, and `fixed_at`/`released_at` become `fixed_wall_at`/`released_wall_at`. The implementer picks the exact names and applies them everywhere. Telemetry field names do not change: they carry durations.

**Consumes:** Task 3's rows (their `at` is already a wall instant), Task 5's `await_return` and `duration_warning`, Task 6's `_settle_return` and `_close_interval`.

- [ ] **Step 1: Failing tests first.** Write these, run them, and see each fail for the stated reason before touching `welfare.py`:
  1. `tests/test_cli.py`: `wlx run` in the simulator with the **default** deployment (`rig-fixed`), running trials, with stdin a terminal that answers the return prompt `now`. Expected: exit 0, and `welfare_notes.jsonl` holds a `departure` and a `returned` row (plus any confirmation rows the departure needs). It fails today: the return is refused as before the head release, or the post-loop phase faults.
  2. `tests/test_taskd.py`: a `RIG_FIXED` session with an injected wall clock that advances far less than its frame clock over its trials (for example, many trials while the wall moves 2 s). Expected: `await_return`'s first frame publishes without raising, and its `out_of_cage_seconds` equals wall minus departure.
  3. `tests/test_welfare.py` covers:
     - before the return, `out_of_cage_seconds(w)` is `w - departure`; after it, the value is fixed at `return - departure`;
     - the restraint cross-check compares wall chair time with wall out-of-cage;
     - these are still refused, each with its existing sentence: a return before the release, a departure in the future, a non-finite reading, and a mark at or past the ceiling.
- [ ] **Step 2: Implement.** Keep every refusal and its sentence; change only the base.
  - The trial loop's `must_stop` check reads `self.wall_now()` where it read `self.now()`: one clock read replacing another, at the same place, not a new per-frame read.
  - `wlx run` marks head fixation with the wall instant it reads at the moment it used to pass `0.0`.
  - Docstrings that argue about the two bases, and about ruling 4's mapping, are rewritten to say what is now true: the departure and return are wall instants, and the ELN's will be too.
- [ ] **Step 3: Remove the Ruling 6 mitigations.**
  - Every `--deployment rig-chaired` that Task 6 added to `tests/test_cli.py` to sidestep the mismatch returns to the default, and its explanatory comment is removed, unless the test is about the chaired kind.
  - Any `RIG_CHAIRED` choice in `tests/test_taskd.py` that exists only to sidestep the mismatch goes too. Keep Task 5's `_chaired_and_run` only where chairing is the point.
- [ ] **Step 4: Run the suite.** `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`: all pass, three runs in a row (the post-loop tests use threads).
- [ ] **Step 5: Commit.** Subject: `Count every welfare duration on the wall clock`. The body names the simulator finding and spec §10.

### Task 8: The return is taken at the terminal only

**Why:** spec §10, item 2. The ELN owns the return, the browser will not send one, and `wlx run`'s prompt is the stand-in until the ELN exists.

**Files:**
- Modify: `wl_expcontroller/link.py`, `wl_expcontroller/taskd.py`, `wl_expcontroller/cli.py`
- Modify tests: `tests/test_link.py`, `tests/test_taskd.py`, `tests/test_cli.py`
- Modify: `docs/design/architecture.md` (the `console` row lists the link's commands as `SetParameter` and `Stop`)

**Interfaces (after this task):**
- `link.Command = SetParameter | Stop`, and the codec has no `"returned"` kind.
- `wlx run` has no `--await-return-for`.
- `_close_interval` has two paths:
  - **With a terminal:** the background thread runs `await_return`, publishing while `_settle_return` asks.
  - **With no terminal, linked or not:** it writes one `return not recorded (no terminal)` row and returns without waiting; `wlx run` exits 0.

- [ ] **Step 1: Failing tests first:**
  1. A linked `wlx run` with no terminal never calls `Session.await_return`: monkeypatch it to record calls, and assert zero. Its row reads `return not recorded (no terminal)`, and the exit code is 0.
  2. `link`'s decoder, given a msgpack command tagged `"returned"`, refuses it through the existing unknown-kind path; it does not build a command.
  3. `wlx run ... --await-return-for 5` is rejected by argparse (exit 2).
- [ ] **Step 2: Implement.**
  - Remove `ReturnedToCage`: the class, the union member, the codec entries, and `taskd._command`'s route.
  - Remove `--await-return-for`, `_console_recorded_it`, and every console-race branch in `_settle_return` and `_close_interval`.
  - Delete `Session._mark_lock` if the terminal is now the only writer of the return, and say so in the commit body. Keep it if another writer remains.
  - After the loop, `SetParameter` and `Stop` are still refused, with the same sentence.
- [ ] **Step 3: Rewrite the tests that assumed a console return.**
  - Remove Task 4's `ReturnedToCage` tests, the console-wins-the-race test, and the two `--await-return-for` tests from Task 6's fix round.
  - The `--link` tests that closed the session with `ReturnedToCage` now end on `return not recorded (no terminal)`.
  - `test_wlx_run_with_link_lets_a_real_console_attach` keeps its point: a real console attaches and receives frames. It now ends as a no-terminal run.
- [ ] **Step 4: Run the suite.** `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`: all pass, three runs in a row.
- [ ] **Step 5: Commit.** Subject: `Take the return at the terminal only, until the ELN takes it`.

### Task 9: The in-session clock, and a console that shows the phase

**Why:** spec §10, item 3. The PI ruled the in-session clock "only shown and recorded". The first plan's Task 7 also owed `wlx console` a line for `phase`.

**Files:**
- Modify: `wl_expcontroller/taskd.py`, `wl_expcontroller/link.py`, `wl_expcontroller/cli.py`
- Modify tests: `tests/test_taskd.py`, `tests/test_link.py`, `tests/test_cli.py`, and the telemetry golden files

**Interfaces (after this task):**
- `Session.open(how: str = "terminal") -> None` sets `opened_wall_at` and writes a `session opened` row through `Session._note`, which needs no open record: it writes to the spec's directory. A second call raises `RuntimeError`. `run()` calls it when nothing has, so a direct API user gets the clock too. `wlx run` calls it right after building the `Session`, before the departure is marked.
- `Session.end(how: str = "terminal") -> None` sets `ended_wall_at` and writes a `session ended` row. Before `open()` it raises `RuntimeError`, and a second call raises `RuntimeError` too.
- `Telemetry.in_session_seconds: float | None` reads `(ended_wall_at or wall_now) - opened_wall_at`, and is `None` before `open()`. It is added to schema 6, which has not left this branch; update the golden files and the stand-in fixtures.
- `wlx run` calls `session.end()` once, in `_close_interval`'s `finally`, after the return is settled or recorded as not recorded. A cage-side session ends right after `run()`.
- `cli.render` prints two lines: `  in session: H:MM:SS`, and `  phase: running`, `awaiting return` or `closed` (from `Telemetry.phase`).

- [ ] **Step 1: Failing tests first:**
  1. For `wlx run`, the rows arrive in the order `session opened`, `departure`, (any confirmation rows), `returned` or `return not recorded`, `session ended`. Every test that asserts an exact list of kinds (the six from Ruling 3, among others) gains the two new rows.
  2. `in_session_seconds` advances with an injected wall clock and stops advancing after `end()`.
  3. **It bounds nothing.** Take a session open 13 hours by the wall, whose departure was 1 hour ago: `must_stop` and `approaching_limit` return nothing about it.
  4. `render` prints both lines (golden).
- [ ] **Step 2: Implement.** Nothing in `welfare` reads the in-session clock.
- [ ] **Step 3: Run the suite.** `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`: all pass, three runs in a row.
- [ ] **Step 4: Commit.** Subject: `Keep an in-session clock, apart from the out-of-cage one`.

### Task 10: Prove it, write it down, and hand it to the PI

**Files:**
- Modify: `docs/CHECKPOINT.md`, `docs/next-session.md`, `docs/superpowers/specs/2026-08-31-S9a-console-design.md` (§9), `docs/superpowers/specs/2026-08-31-S8-session-management-design.md` (§5.2 item 4)

- [ ] **Step 1: Mutation gate, read line by line.**

Run: `python tools/mutation_gate.py --base main 2>&1 | tee /tmp/p4d2a-gate.txt` from the worktree (it takes a while). It should select at least `welfare`, `taskd`, `link`, `cli` and `record`. **Read every line.**
- The result must show zero `SURVIVED` and zero `SKIPPED`.
- Every `caught` must show `N failed` and a `<-` naming tests about that function; `N errors` or a single unrelated test does not count.
- Confirm each new or changed function this way: find its line and check that the `<-` names a test written in this plan. The functions are `duration_warning`, `_publish`, `_note`, `return_needs_confirmation`, `return_not_recorded`, `_refuse`, `await_return`, `_clock_or_now`, `_settle_return`, `_close_interval`, `end`, and every `welfare` method whose base changed in Task 7.
- A survivor gets a test that fails without it. A function nothing can test gets deleted, not exempted.

- [ ] **Step 2: Documents.**
  - `docs/CHECKPOINT.md`: add a "What moved" entry for P4d-2a. It covers:
    - the findings, including the simulator clock fault and the PI's ELN answers;
    - what was built, and the gate result as read;
    - **that the branch awaits the PI's review of spec §7**.
  - `docs/CHECKPOINT.md`, the Work packages table: split P4d-2 into P4d-2a (built on branch `p4d2a-return-to-cage`, awaiting welfare review) and P4d-2b (brainstorm in progress; spec `2026-09-26-P4d2b-browser-console-design.md`, resume at its §4, with the mockup rulings held there).
  - `docs/CHECKPOINT.md`, the Status table: update the test count and the Session duration row.
  - `docs/next-session.md`, §1: the welfare review is pending again, with spec §7's seven items as a numbered list.
  - `docs/next-session.md`, §6: P4d-2b is next after approval.
  - S9a §9: add rows for `phase`, `stop_kind` and `in_session_seconds` to the telemetry table, and replace the stale "`SCHEMA` is 4" sentence with the history through 6.
  - S8 §5.2 item 4: add one paragraph:
    - both ends of the interval are wall instants;
    - the return is taken by `wlx run`'s prompt, as the stand-in until the wl-works ELN records it;
    - both ends are rows in `welfare_notes.jsonl`;
    - the interval is published after the loop;
    - the in-session clock is kept apart and bounds nothing.

- [ ] **Step 3: Full suite, then commit and push the branch.**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`. Expected: all pass.

```bash
git add docs/
git commit -m "Record closing the out-of-cage interval, and what the PI is asked to approve"
git push -u origin p4d2a-return-to-cage
```

Then read the branch's CI run (`gh run list --branch p4d2a-return-to-cage`): its log, not its verdict.

- [ ] **Step 4: Hand the PI the review.** Give the PI spec §7's seven items as a numbered list. Each item gets one sentence on what the code now does, and the test that pins it. **Do not merge to `main`.** It merges by fast-forward only after the PI approves.
