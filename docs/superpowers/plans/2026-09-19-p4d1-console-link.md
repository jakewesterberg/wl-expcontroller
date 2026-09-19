# P4d-1 — The console link: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

> **Amended 2026-09-19.** The illustrative test snippets below bounded a session with
> `_session(max_trials=N)`. **There is no session-length maximum** (PI, 2026-09-19) and
> `max_trials` no longer exists anywhere; they now read `_session(_spec(tmp_path,
> trials=N))`, which bounds a session on its **block quota** — one of the two things a
> real session ends on, the other being the `out_of_cage` ceiling. Amended rather than
> annotated because this is a document a session *executes*: a plan that teaches a
> removed concept gets it written back.

**Goal:** A running session publishes live telemetry and accepts commands over a socket,
so a second process can watch a session and change a parameter with its actor recorded.

**Architecture:** `Session` gains a `Link` port drained **once per trial boundary, never
per frame**, beside the `World`, `Effects` and `Pump` ports it already has. Telemetry is
built from the objects the record is written from — `Tally`, `Welfare`, `Bounds`,
`Scheduler` — never recomputed. Commands are validated by the existing `Session.set`, so
the console gains no second write path. `Absent`, `Simulated` and a ZMQ implementation are
peers, exactly as in `dio.py`.

**Tech Stack:** Python 3.11–3.12, ZeroMQ (`pyzmq`) with `msgpack`, per ADR-0003. No web
stack in this slice — the consumer is `wlx console`, a terminal client.

**Spec:** `docs/superpowers/specs/2026-08-31-S9a-console-design.md` §6–§10 (§7 processes,
§8 writers, §9 the telemetry contract). Read §9 before Task 2; the whole plan argues from
its one rule.

## Global Constraints

- **US English** everywhere — code, docs, comments.
- **Hot-path discipline.** The link is touched at the trial boundary only. No socket call,
  no allocation and no logging I/O inside `run_trial`. A reviewer should reject any step
  that puts `link.` inside a frame loop.
- **Sim first.** Every task ships with a simulator-backed test. Nothing merges red.
- **`link.py` is not welfare-critical and must not become so.** It carries no limit, no
  clock and no pump. The welfare-critical surface stays exactly two files, `bounds.py` and
  `welfare.py` (CLAUDE.md, S8 §7). If a step would put a limit in `link.py`, stop.
- **The console is a view, never a source** (S9a §9). Every field in `Telemetry` is read
  from an existing object. If a number is not already on one, add it there, not here.
- **A new module must be declared in `tools/mutation_gate.py`**, in `RETURNS` or `EXEMPT`
  with a reason. The gate fails otherwise, on purpose (trap 18).
- **Read the mutation harness's output, not its exit code** (trap 7, seven occurrences).
  `N failed` is a test noticing; `N errors in 0.6s` is not.
- **Never run the suite, edit a test, or `git add` while a mutation sweep is in flight**
  (trap 12).
- **New dependencies need a one-line justification and an ADR-0004 licence entry**, with
  the licence verified against the primary source and cited with an as-of date.

---

### Task 1: Declare the two dependencies ADR-0003 already accepted

ADR-0003 accepted "ZeroMQ (PUB/SUB + REQ/REP) with msgpack" on 2026-08-31 and named its
consequence: *"Two small, boring dependencies (pyzmq, msgpack)."* Neither is in
`pyproject.toml` yet, because nothing needed them until now.

**Files:**
- Modify: `pyproject.toml` (the `[project.optional-dependencies]` block)
- Modify: `docs/design/decisions/ADR-0004-license.md` (its licence inventory)

**Interfaces:**
- Consumes: nothing.
- Produces: a `console` extra installable with `pip install -e ".[console]"`.

- [ ] **Step 1: Verify both licences against the primary source**

Fetch each project's own metadata — not a summary site, and not memory:

```
https://pypi.org/pypi/pyzmq/json      -> .info.license and .info.classifiers
https://pypi.org/pypi/msgpack/json    -> .info.license and .info.classifiers
```

Record what they actually say, with today's date. If a value is ambiguous, write
`UNVERIFIED` and say why rather than picking the likely answer — CLAUDE.md forbids the
guess more than it forbids the gap.

- [ ] **Step 2: Add the extra**

In `pyproject.toml`, beside the existing `dev` and `contract` extras:

```toml
# What the CONSOLE needs: the link between `taskd` and a console process.
# ADR-0003 chose ZeroMQ with msgpack for control/telemetry on 2026-08-31 and named
# these two as its consequence. Deliberately an extra rather than a core dependency:
# a rig running `wlx run` from a terminal needs neither, and the 3.13 CI leg must keep
# importing the core with no transport installed.
console = ["pyzmq>=26", "msgpack>=1"]
```

- [ ] **Step 3: Record both in ADR-0004's inventory**

Add a row per package in the inventory table, with the licence exactly as the primary
source states it and the as-of date from Step 1.

- [ ] **Step 4: Prove the core still imports without them**

```bash
pip uninstall -y pyzmq msgpack 2>/dev/null; python3 -c "import wl_expcontroller.taskd"
```
Expected: no error. The core must not acquire a transport dependency — the same argument
S9a §5 makes for keeping a 3.13 CI leg.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docs/design/decisions/ADR-0004-license.md
git commit -m "Declare the transport dependencies ADR-0003 accepted"
```

---

### Task 2: The telemetry message, and its schema

**Files:**
- Create: `wl_expcontroller/link.py`
- Create: `tests/test_link.py`
- Modify: `tools/mutation_gate.py` (the `RETURNS` dict)

**Interfaces:**
- Consumes: `simulate.Tally`, `welfare.Welfare`, `bounds.Bounds`, `scheduler.Scheduler`.
- Produces: `Telemetry`, `Staged`, `SCHEMA`, and
  `Telemetry.of(session, tally, scheduler, index) -> Telemetry`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m pytest tests/test_link.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wl_expcontroller.link'`.

- [ ] **Step 3: Write the message**

```python
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
    stopped_because: str
    fluid_session_ml: float
    fluid_today_ml: float | None
    shortfall_ml: float | None
    chair_seconds: float
    outcomes: dict
    hangs: int
    owed: dict
    staged: tuple

    @classmethod
    def of(cls, session, tally, scheduler, index: int) -> "Telemetry":
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
            staged=tuple(
                Staged(name=n, was=w, now=v, by=b, bounded=bd)
                for n, w, v, b, bd in session._staged
            ),
        )
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python3 -m pytest tests/test_link.py -v`
Expected: PASS, both.

- [ ] **Step 5: Declare the module in the mutation gate**

In `tools/mutation_gate.py`, add to `RETURNS`:

```python
    "link": "None",
```

`None` rather than `[]` because nothing in this module returns a list callers concatenate.
Then confirm the gate no longer reports it undeclared:

```bash
python3 tools/mutation_gate.py --base HEAD
```
Expected: it runs; it does **not** exit with a module-undeclared error.

- [ ] **Step 6: Commit**

```bash
git add wl_expcontroller/link.py tests/test_link.py tools/mutation_gate.py
git commit -m "Say what a session tells its consoles"
```

---

### Task 3: The port, and why `Absent` is allowed to be silent

**Files:**
- Modify: `wl_expcontroller/link.py`
- Modify: `tests/test_link.py`

**Interfaces:**
- Consumes: `Telemetry` from Task 2.
- Produces: `Link` (Protocol), `Absent`, `Simulated`, `SetParameter`, `Stop`,
  `Command = SetParameter | Stop`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m pytest tests/test_link.py -k "absent or simulated" -v`
Expected: FAIL — `ImportError: cannot import name 'Absent'`.

- [ ] **Step 3: Write the port**

```python
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


class Link(Protocol):
    def publish(self, telemetry: Telemetry) -> None:
        """Offer telemetry to whoever is listening. **Must never block**: latest-wins
        telemetry that could stall a trial boundary would make a view able to delay an
        experiment."""

    def drain(self) -> list:
        """Every command that has arrived since the last call. Non-blocking, and each
        command is returned once."""


@dataclass(frozen=True, slots=True)
class Absent:
    """No console, and that is a legitimate configuration -- see the test."""

    def publish(self, telemetry: Telemetry) -> None:
        return None

    def drain(self) -> list:
        return []


@dataclass
class Simulated:
    """The in-process link a test drives."""

    published: list = field(default_factory=list)
    _queued: list = field(default_factory=list)

    def queue(self, command) -> None:
        self._queued.append(command)

    def publish(self, telemetry: Telemetry) -> None:
        self.published.append(telemetry)

    def drain(self) -> list:
        taken, self._queued = self._queued, []
        return taken
```

- [ ] **Step 4: Run and watch them pass**

Run: `python3 -m pytest tests/test_link.py -v`
Expected: PASS, all four.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py tests/test_link.py
git commit -m "Give a session a port its consoles attach to"
```

---

### Task 4: Wire it to the trial boundary, and prove nothing touches a frame

This is the task the whole slice exists for, and the one a reviewer should read hardest:
a port wired to nothing is pitfall P21, and a port wired into a frame loop is a timing
bug that no test will notice.

**Files:**
- Modify: `wl_expcontroller/taskd.py` (the `Session` dataclass fields, and `run()`'s loop)
- Modify: `tests/test_taskd.py`

**Interfaces:**
- Consumes: `link.Link`, `link.Absent`, `link.Simulated`, `link.SetParameter`,
  `link.Stop`, `Telemetry.of` from Tasks 2–3.
- Produces: `Session(link=...)`, defaulting to `Absent()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_session_publishes_once_per_trial():
    link = Simulated()
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    assert [t.trial_index for t in link.published] == [0, 1, 2, 3, 4]


def test_a_command_from_a_console_lands_at_the_next_boundary_with_its_actor():
    """The console gains no second write path: the command goes through `Session.set`,
    so a welfare-bounded name still meets its ceiling and an undeclared name is still
    refused."""
    link = Simulated()
    session = _session(_spec(tmp_path, trials=3), link=link)
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake"))

    session.run()

    changes = _parameter_changes(session)
    assert changes[0]["name"] == "fix_hold"
    assert changes[0]["by"] == "jake"


def test_a_stop_command_ends_the_session_at_a_boundary_not_mid_trial():
    link = Simulated()
    session = _session(_spec(tmp_path, trials=100), link=link)
    link.queue(Stop(by="jake"))

    census = session.run()

    assert session.stopped_because == "stopped by jake"
    assert sum(census.outcomes.values()) < 100


def test_a_refused_command_does_not_stop_the_session():
    """A console offering a parameter the task does not declare is a mistake by a
    person, not a fault of the rig. The session records the refusal and runs on --
    stopping would let a typo end a session with an animal in the chair."""
    link = Simulated()
    session = _session(_spec(tmp_path, trials=3), link=link)
    link.queue(SetParameter(name="not_a_parameter", value=1.0, by="jake"))

    census = session.run()

    assert sum(census.outcomes.values()) == 3, "the session ran its block quota"
    assert len(session.refusals) == 1
    assert session.refusals[0][0] == "not_a_parameter"
    assert session.refusals[0][1] == "jake"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m pytest tests/test_taskd.py -k "link or console or command or stop" -v`
Expected: FAIL — `TypeError: Session.__init__() got an unexpected keyword argument 'link'`.

- [ ] **Step 3: Add the field**

In the `Session` dataclass, beside `world` and `observe`:

```python
    #: Where consoles attach. Drained and published **once per trial boundary, never
    #: per frame** -- a socket call inside `run_trial` would put the network in the
    #: frame budget, which S9 §1 forbids in the sentence that makes the process split
    #: a hard rule. `Absent()` is a real configuration, not a stub: the cage-side kiosk
    #: runs unattended.
    link: object = field(default_factory=_link.Absent)
```

- [ ] **Step 4: Drain and publish in the loop**

In `run()`, inside `while True:` and immediately **after** `self._apply_staged()` — so a
command offered on the previous boundary has already landed, and the telemetry a console
sees matches the values the next trial will run:

```python
                for command in self.link.drain():
                    self._command(command)
                self.link.publish(
                    _link.Telemetry.of(self, tally, scheduler, index)
                )
```

and add the handler beside `set()`:

```python
    def _command(self, command) -> None:
        """A console's request, routed to the one write path.

        **Refusals do not end the session.** A person mistyping a parameter name is
        not a fault of the rig, and ending a session with an animal in the chair over
        a typo is a worse outcome than ignoring it. The refusal is recorded.
        """
        if isinstance(command, _link.Stop):
            self.stopped_because = f"stopped by {command.by}"
            return
        try:
            self.set(command.name, command.value, by=command.by)
        except Exceeded as refused:
            self.refusals.append((command.name, command.by, str(refused)))
```

with `refusals: list = field(init=False, default_factory=list)` on the dataclass, and
`stopped_because` checked in the existing `must_stop` branch so a `Stop` breaks the loop.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `python3 -m pytest tests/test_taskd.py -v`
Expected: PASS. Then the whole suite: `python3 -m pytest -q`.

- [ ] **Step 6: Prove the link is nowhere near a frame**

```bash
grep -n 'link\.' wl_expcontroller/run.py
```
Expected: **no output.** `run.py` is the frame loop; the link must not appear in it. If it
does, the wiring went in the wrong place and Step 4 must be redone.

- [ ] **Step 7: Prove the new tests can fail**

```bash
python3 tools/mutate.py --returns None wl_expcontroller/taskd.py _command
```
**Read the output, not the exit code.** Expected: `caught _command   N failed, M passed`.
`N errors in 0.Ns` is a collection error and means the mutation did not run (trap 7).

- [ ] **Step 8: Commit**

```bash
git add wl_expcontroller/taskd.py tests/test_taskd.py
git commit -m "Let a console watch a session, and change a parameter through it"
```

---

### Task 5: The ZMQ implementation, both ends

**Files:**
- Modify: `wl_expcontroller/link.py`
- Modify: `tests/test_link.py`

**Interfaces:**
- Consumes: `Link`, `Telemetry`, `SetParameter`, `Stop`.
- Produces: `ZmqLink(pub_endpoint, rep_endpoint)` for the `taskd` side and
  `ZmqConsole(sub_endpoint, req_endpoint)` for the console side, plus
  `encode(telemetry) -> bytes` and `decode(payload) -> Telemetry`.

- [ ] **Step 1: Write the failing round-trip test**

```python
def test_telemetry_survives_the_wire_unchanged():
    """A golden round-trip, which ADR-0003 requires of every message schema. A field
    that silently changes type on the wire is a console rendering something other than
    what the session meant."""
    original = _telemetry(fluid_today_ml=None, shortfall_ml=None)

    restored = decode(encode(original))

    assert restored == original
    assert restored.fluid_today_ml is None, "None must not become 0.0 on the wire"


def test_a_console_and_a_session_talk_over_a_real_socket():
    """Over loopback rather than a mock, for the reason `tests/test_eye.py` uses a real
    socket: a protocol proven against a mock is a proof about the mock."""
    link = ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    console = ZmqConsole(link.pub_endpoint, link.rep_endpoint)

    console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
    commands = link.drain()
    link.publish(_telemetry())

    assert commands == [SetParameter(name="fix_hold", value=0.4, by="jake")]
    assert console.receive().session_id == _telemetry().session_id
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m pytest tests/test_link.py -k zmq -v`
Expected: FAIL — `ImportError: cannot import name 'ZmqLink'`.

- [ ] **Step 3: Implement both ends**

Import `zmq` and `msgpack` **inside** the class bodies or behind a module-level guard, so
`import wl_expcontroller.link` still works with neither installed — Task 1 Step 4's
property must survive this task.

`publish` uses a PUB socket with `zmq.DONTWAIT` and swallows `zmq.Again`: telemetry is
lossy by design (S9a §9), and a full queue must never stall a trial boundary. `drain`
polls the REP socket with a zero timeout and replies to each request, so a console learns
its command was accepted.

- [ ] **Step 4: Run and watch them pass**

Run: `python3 -m pytest tests/test_link.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py tests/test_link.py
git commit -m "Carry the link over a socket, losing telemetry rather than time"
```

---

### Task 6: `wlx console`, the consumer that makes the port real

A port with no consumer is the failure CLAUDE.md names: *"a safety component ships with
its consumer, or its absence fails."* This task is why the slice is one plan and not two.

**Files:**
- Modify: `wl_expcontroller/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `ZmqConsole`, `Telemetry`, `SetParameter`, `Stop`.
- Produces: `wlx console --sub <endpoint> --req <endpoint> [--set name=value] [--stop]`,
  and `--as <who>` for the actor.

- [ ] **Step 1: Write the failing test**

```python
def test_console_renders_a_telemetry_frame_without_inventing_a_number():
    """Every line the console prints names a field of `Telemetry`. An unknown day
    prints UNKNOWN, never 0.0 -- `wlx run` already does this and the two must agree."""
    frame = _telemetry(fluid_today_ml=None, shortfall_ml=None)

    rendered = render(frame)

    assert "supplement: UNKNOWN" in rendered
    assert "0.0" not in rendered.split("supplement:")[1].splitlines()[0]


def test_console_requires_an_actor_for_a_write():
    """S9a §6: every welfare-affecting action records its actor. A write with no
    `--as` is refused at the CLI rather than defaulting to a name."""
    code = main(["console", "--sub", "tcp://127.0.0.1:1", "--req",
                 "tcp://127.0.0.1:2", "--set", "fix_hold=0.4"])

    assert code == 1
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m pytest tests/test_cli.py -k console -v`
Expected: FAIL — `argparse` exits 2 on the unknown subcommand `console`.

- [ ] **Step 3: Add `--link` to `wlx run`**

Task 6 Step 5 drives two terminals, and `wlx run` has no way to open a link. Add a
`--link PUB,REQ` option that constructs a `ZmqLink` and passes it as `Session(link=...)`;
omitted, the session keeps `Absent()` and behaves exactly as it does today. Test that
omitting it still runs, so the terminal path does not acquire a transport dependency.

- [ ] **Step 4: Add the subcommand and the renderer**

Follow the shape of the existing `run` subcommand in `cli.py:94`. `render(frame)` prints
one line per pane of S9a §4 that this slice has data for: fluid, chair, trials by outcome,
what is still owed, and **staged changes with who staged them** — the last is §8's
visibility requirement and the reason a console that showed only applied values would be
wrong.

- [ ] **Step 5: Run and watch them pass**

Run: `python3 -m pytest tests/test_cli.py -v`, then `python3 -m pytest -q`.
Expected: PASS.

- [ ] **Step 6: Drive it end to end by hand, two terminals**

```bash
# terminal 1
python3 -m wl_expcontroller.cli run --task tasks/fixation_detection.py \
  --bounds tasks/reference_bounds.py --link tcp://127.0.0.1:5571,tcp://127.0.0.1:5572
# terminal 2
python3 -m wl_expcontroller.cli console --sub tcp://127.0.0.1:5571 \
  --req tcp://127.0.0.1:5572 --as jake --set fix_hold=0.4
```
Expected: the console prints frames as trials run, and `parameter_changes.jsonl` in the
session directory records `fix_hold` with `by: jake`. **Check that file** — a console that
says it changed something proves nothing; the record is the record.

- [ ] **Step 7: Commit**

```bash
git add wl_expcontroller/cli.py tests/test_cli.py
git commit -m "Attach a console to a running session"
```

---

### Task 7: Sweep, and update the documents this changed

- [ ] **Step 1: Run the mutation sweeps, and read them**

```bash
python3 tools/mutate.py --all --returns None wl_expcontroller/link.py
python3 tools/mutate.py --all --returns None wl_expcontroller/taskd.py
```
**Read the output.** Every line should be `caught  <name>  N failed, M passed`. A
`SURVIVED` is a real gap and needs a test, not an argument. A `SKIPPED` means the harness
could not reach the function — trap 7's seventh entry — and is also a failure.

Do not run the suite or `git add` while either sweep is in flight (trap 12).

- [ ] **Step 2: Update the documents**

- `docs/design/architecture.md` — the `console` row gains the link's endpoints.
- `docs/CHECKPOINT.md` — "What exists" gains `link.py`; the work-package table marks
  P4d-1 done and names P4d-2 next.
- `docs/next-session.md` — what moved, and what P4d-2 needs.

- [ ] **Step 3: Push and watch CI**

```bash
git push origin <branch>
gh run list --branch <branch> --limit 1
```
`tools/mutation_gate.py` escalates to a full sweep because `pyproject.toml` changed — about
1h40m. **Read the run's log rather than its conclusion** when it finishes.

---

## Self-review

**Spec coverage.** S9a §7's process split: Tasks 3–6 (the console is a separate process;
Task 4 Step 6 proves the link is not in the frame loop). §8's visibility: `Staged` in Task
2 and the renderer in Task 6 Step 3. §9's one rule: Task 2, enforced by its first test.
§9's `None`-never-`0`: Task 2 and Task 6. §6's actor: Tasks 3, 4 and 6.

**Not covered here, deliberately, and each belongs to a later slice:** §6's OAuth identity
and the `Verified`/`Local` types (P4d-3 — this slice carries `by` as a plain string, which
is what `Session.set` already takes); §7's HTTP surface and `labhost` (P4d-2); §9's
`rt_approx_ms` (needs a response timestamp that `Result` does not yet carry — **raise it
at the start of P4d-4 rather than discovering it there**); §10's preflight (P4d-5).

**Three issues found and fixed inline rather than recorded:** `Telemetry.condition` could
only ever be empty at publish time and was removed; Task 4's fourth test asserted
something meaningless and now checks `session.refusals` directly; and Task 6 Step 5 drove
`wlx run --link`, a flag no task added, which is now Task 6 Step 3.
