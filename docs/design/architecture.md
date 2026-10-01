# Architecture

Status: current summary. Reasoning, sources and alternatives live in
`docs/superpowers/specs/2026-08-31-controller-architecture-design.md`; this file is the
orientation document CLAUDE.md sends you to first. Where the two disagree, the spec wins
and this file is stale.

Contracts here are proposals until frozen at milestone M0.

## Principles

1. Two planes per rig, joined by messages and by hardware TTLs — never by shared code or
   shared clocks.
2. **The sync box defines session time.** `wl-sync` owns session identity, the barcode
   codec, the log format and event-code routing. We consume them; we do not mint them.
3. Anything scientifically meaningful becomes an edge or word in a recorded stream.
   Software timestamps are for control flow; hardware timestamps are for analysis.
4. Hardware sits behind small interfaces; every interface has a simulator.
5. The hot loop does bounded work: no allocation, no disk I/O, no unbounded queues, and
   it never renders a plot, serves a request, or holds a UI.
6. **Declare once, derive many.** Parameters, trial outcomes, plots, stimuli and gaze
   mappings are versioned data with provenance, not code. One declaration drives
   validation, the console UI, the saved record and the downstream contracts.

## Per-rig topology

```
   OpenIris PC (Windows)          Task PC (Linux)              Acquisition PC (Windows)
   OpenIris + OpenIrisDPI         taskd + console              SpikeGLX <- Neuropixels
   500 Hz binocular dDPI          NI PCIe-6343                 NI PXIe-6353 (nidq)
        |         \                    |                             ^
        | UDP:9003 \ ACCES DAC         | MDR68 x2                    |
        | (control) \ (recorded copy)  |                             |
        v            v                 v                             |
   +--------------- wl-sync breakout board (2U) ----------------------+
   |  conditioning, level shifting, isolation, mux, comparators        |
   +---+--------------------+---------------------+------------------+
       |                    |                     |
       v                    v                     v
   sync box (Pi/CM5)    Intan RHS            wl-juicer / wl-shook /
   barcode, session     record + stimulate   cameras / speakers / mic
   identity, log
```

**Two rigs in v1** (the breakout spec budgets cabling for two; five boards are fabbed, so
headroom exists). One config file per rig.

## The task PC's interface

Fixed in copper by `wl-sync`'s breakout board. See that repo's `hardware/README.md` and
breakout spec §3 and §9.2.

- **Digital out (19):** 16 event-code bits on **P0.8–P0.23** (not zero-based), event
  strobe, reward commanded, stim trigger.
- **Digital in (4):** task-patch photodiode comparator, flip-patch photodiode comparator
  (a frame clock), chair-motion trigger from `wl-shook`, RHS stim output.
- **Analog in (9):** eye X/Y both eyes (from the ACCES DAC), joystick X/Y, 3 misc BNC.
- **Not in copper:** touchscreen and audio output. Both are host-side, and touch events
  reach the recording clock only as strobed event codes.

The two photodiode comparators returning to us turn two offline checks into online
guarantees: state progression can be gated on physical stimulus onset, and dropped frames
are detected at the display surface.

## Components

| Component | Runs on | Language | Job | Simulator |
|---|---|---|---|---|
| `taskd` | Task PC (Linux) | Python | Trial execution, display, gaze logic, DIO, session record; since P4d-2b b3a also `wlx taskd`, the rig service that holds one animal's session across runs, opened, run and ended from a console (`service.py`) | Full headless run against replayed/synthetic inputs |
| `console` | The control box, in a browser on the LAN | Python server + web client | Experimenter UI, live plots, parameter writes, preflight, test screens. **The box authenticates and records the actor** — anybody attached has full access, with visibility rather than a lock (S9a §8); `wl-works` lists devices and links to them, and carries no welfare-affecting action (ADR-0008). **The link exists** (`wl_xcon/link.py`, P4d-1, 2026-09-19): `taskd` holds a `Link` port, drained and published once per trial boundary and never per frame, whose live implementation (`ZmqLink`) binds a ZMQ PUB socket for `Telemetry`, a REP socket for its commands — `SetParameter` and `Stop`, and since P4d-2b b2a `Pause`, `Resume`, `Mark` (a mark's note), `ScheduleStop`, `CancelScheduledStop` and `ManualReward` (a manual reward: while paused and, in a `wlx taskd` session, between runs and while the return is awaited), and since P4d-2b b3a `OpenSession`, `CheckRun`, `StartRun` and `EndSession`, which `wlx taskd` acts on and a `wlx run` session refuses — which the page's forms send since b3a-2, through `POST /commands`, built by the wire's own rules (`link._command_from`), and whose closed session's summary `wlx taskd`'s idle frame carries until the next session opens (telemetry schema 11) — each checked where it is decoded — and, given a third endpoint, a PULL socket for an operator's mark signal, which the trial loop checks once per frame (ADR-0003's transport, untouched: a third socket on the same link). `ZmqConsole` is the other end. Reached today by `wlx run --link PUB,REP` or `wlx taskd --link PUB,REP` and a terminal client, `wlx console --sub PUB --req REP --as WHO`. **The browser console exists** (P4d-2b slice b1, 2026-09-26, read-only then; the box's writes since b2a and its session forms since b3a-2, below): `wlx serve --link PUB,REP --http HOST:PORT --health-token-file PATH` is its own process — a stdlib `ThreadingHTTPServer`, one `ZmqConsole` on a telemetry thread, server-sent events to each browser from a bounded queue, and every pane rendered in Python (`web.py`) so the page's script only swaps fragments. The wl-works fonts are bundled and served by the box, so the page never reaches the internet (PI, 2026-09-26). Reads are open to the LAN. **Writes come from the box** (P4d-2b slice b2a, 2026-09-28): `POST /commands` is accepted only from a loopback peer, with a `Host` naming loopback, the page's own `Origin` and `Content-Type: application/json` (spec §2), and recorded as `NAME (box, unverified)`; every request is answered only when its `Host` names this console (`--allow-host` adds names). `wlx serve` owns each socket on one thread — a read-only telemetry thread, a command thread whose REQ socket waits for `taskd`'s acknowledgment (*sent*, *not delivered*, *busy*), and a mark thread that sends the signal ahead of every command. Writes from people signed in to wl-works are slice b2b | Runs against a fake `taskd` (`link.Simulated`), or a real one over loopback sockets |
| `neurofeatd` | Acquisition PC | C++ | SpikeGLX `fetchLatest` on the filtered AP stream -> MUA features -> ZMQ PUB | Synthetic feature publisher |
| `rhxfeatd` | Intan host | C++/Rust | RHX Spike Output socket -> features -> ZMQ PUB; bounded reader | Synthetic spike-raster publisher |
| `labhost` | Task PC | Python | The pull-only endpoint wl-works polls — **a surface of `console` since 2026-09-19, not its own process** (S9a §7): same server, separate path, separate auth. Served as `GET /health` by `wlx serve` (`health.py`, P4d-2b b1): `HealthResponse` schema 1, contract-tested against wl-preproc's own model; a bearer token read from a file outside the repository, compared with `hmac.compare_digest`, one `401` for every credential failure — the rules of wl-preproc's `responder/handler.py`. Exactly one reading is featured, the most urgent (PI, 2026-09-26), because wl-works shows only the first | Contract tests |
| `openiris` | OpenIris PC | (existing C#) | dDPI tracking; UDP 9003; remote API; analog out | UDP replay server |

Welfare-critical modules requiring human review: reward scheduling and per-delivery limits,
fluid and session-duration accounting (a fluid **floor**, an out-of-cage **ceiling**),
token-to-fluid conversion, stimulation bounds and gating, and the bounded-config loader.

**In code, that is `wl_xcon/bounds.py`, `wl_xcon/welfare.py`, `wl_xcon/marks.py` and
`wl_xcon/stranded.py`, two functions in `wl_xcon/preflight.py` (`out_of_cage`, `gate`),
seven in `wl_xcon/service.py` (`Service._open`, `Service._end` with `Service._unended`,
`Service._close_stranded`, `Service._start`, `_unasked`, `_folder_name`), two functions in
`wl_xcon/cli.py` plus one line inside a third — and, since
P4d-2b b2a, five functions in `wl_xcon/taskd.py` plus two parts of a sixth
(`Session._command`'s `held` pass-through and one `except` line), and one function in
`wl_xcon/link.py`.** The
modules are kept small deliberately: everything in them can hurt an animal if it is
wrong, and a small file is one a person can actually read before signing it off.
**`marks.py` is the out-of-cage interval's two marks, decided once for the terminal and
the page** (P4d-2b b3a, 2026-09-29; the PI: "The page takes both times", under the
terminal's exact rules through one shared piece of code): the parser that turns a typed
clock time into an instant (`clock_time`, `clock_or_now`, which were
`cli._wall_clock_time` and `cli._clock_or_now` and moved unchanged), whether a far mark
was confirmed or amended, by whom and how, and the row that says so. `welfare` refuses
what is impossible, but a wrong instant that is merely plausible passes every refusal,
so the parsing and the confirmation are part of the limit. **The two `cli` functions are
`_settle_departure` and `_settle_return`**, the terminal's prompting around `marks` —
which answer a person gave, and the name and reason an amendment carries — and **the
line is `main`'s `_marks.depart(session, departure)`**, which marks the departure as
`marks` decided it, `confirmed=` included, which `welfare._refuse_unconfirmed` trusts
its caller on. A change to any of these, or to the two `preflight` functions, the seven
`service` functions, the `taskd` and `link` functions and the two parts of
`Session._command` below, is a change requiring review; a change elsewhere is not.

**`preflight.out_of_cage` and `preflight.gate`** (P4d-2b b3a): the first is what refuses
a new run once the out-of-cage limit is reached between runs, and the second is S9a
§10's rule — fail blocks, an unknown proceeds only on a named acknowledgement written
into `runs.jsonl` — and a mistake in it lets a run start that should not.

**`stranded.py`, `Welfare.restore_departure`, and `service.Service._open`, `_end` (with
`_unended`, its refusals before anything is marked, which a run in progress asks too, so an
End refused before anything is marked never stops a run) and `_close_stranded`** (P4d-2b
b3a): the rule that no session opens while an animal's return is missing from the record,
how such a session is found and its return taken, and the page's route into the two marks.
`restore_departure` reads back a recorded departure without `left_cage`'s refusals, which
were applied when it was taken; a mistake in any of
these leaves an animal out of its cage with nothing saying so, or records its return
against the wrong instant. **And `service._unasked`** (the b3a-1 review's Ruling 1): a
page's *confirm*, or a departure's *amend*, is taken only as the answer to the question
the service posed — for that mark, that session and the instant it asked about, and for a
departure the animal, deployment and setup of the open it was asked about — since the
PI's rule for a far mark is a warning the experimenter clicks through, and nothing on the
wire tells a click-through from a confirm sent blind; a mistake in it lets a far mark be
taken that no person was shown. **And `service._folder_name`** (fix round 1): one folder
name, the rule for a session id, an animal and a run's task from the wire and for a
stranded record's animal, whose `bounds.py` is code the service runs — a mistake in it runs
a file from outside `--subjects` on the return path, or from outside `--tasks` as a run
is checked. **And `service.Service._start`** (P4d-2b b3a), which asks S9a §10's
gate of a pre-flight taken as a run is started, never an earlier one, with the out-of-cage
item always among its items — so a run past the limit is refused before `RUN_START`, since
`Session.run` refuses none — and writes who acknowledged each unknown into the run's start
row; a mistake in it starts a run that should not start.

**The three `taskd` functions are `Session._ends`, `Session._hold` and
`Session._manual_reward`** (P4d-2b b2a, 2026-09-28; the third since the PI's 2026-09-28
amendment). `_ends` is the one place the trial loop asks `welfare.must_stop`, between
trials and on every pass of a paused session alike, and where a scheduled stop — "after X
mL this session" among them, read from `welfare.session_total()` — ends a session; it asks
the limit first, so a session at its limit ends as `limit`. `_hold` is the paused loop:
no trial runs, so the task rewards nothing; each pass still drains, publishes and asks
`_ends`; and during a run the commands it drains are the only ones a manual reward is
given for. `_manual_reward` gives one: a person's press of *give reward*, one delivery of
the bounded config's `reward_correct` through `welfare.Rig.reward`, strobed
`MANUAL_REWARD` first — during a run only while it is held paused, and since P4d-2b b3a-2
(spec §6.0, PI 2026-09-29) in a `wlx taskd` session between runs and while its animal's
return is awaited — and refused at any other time: during a trial (XC-157), with no
session open (XC-158), after a `wlx run` session's run (XC-184). **Which phases outside a
run give one is `taskd.OUTSIDE_A_RUN`**, a constant `_manual_reward` reads, so it is part
of that function's rule: a change to it is a change requiring review (the b3a-2 final
review, m3; the page's `web._hand_reward_now` repeats it, pinned equal by a test).
`Session._command` hands every reward to `_manual_reward` first, in every phase, with
`held`, which only `_hold` sets — so a change to that pass-through is also a change to
welfare-critical behavior. All
three call `welfare` unchanged, and none holds a clock or a limit of its own; they are on
this list because a plausible mistake in any — the limit asked on one path and not the
other, a paused session that forgot to ask, a reward given while trials run, given outside
a run where no session is open to count it, or paid from another entry — ends a session
late or rewards an animal when nobody meant it to, and passes every refusal `welfare` has.

**The other two `taskd` functions are `Session.set`, whole, and `Session._schedule`; the
line is `Session._command`'s `except (Exceeded, TypeError) as refused:`; and the `link`
function is `link._setting`** (the P4d-2b b2a final review, 2026-09-28: `set`, the line
and `link._setting` are what the PI's items 3 and 4 rest on, and `_schedule` is what item
2 rests on). `set` is the one write path for a setting from a console: its two type
guards refuse a value that is not a number, for a welfare ceiling and for a numeric
parameter alike (M8, item 4), and it sends a ceiling's name to `bounds.validate`, which
is what keeps a reward size set from the page under its approved ceiling (item 3).
`link._setting` is M8 where bytes become a command — in `_command_from` for the wire's
`_decode_command`, and in `serve.parse_command` for a `POST /commands` body: a `set`'s
value directly and, through `_command_from` since P4d-2b b3a-2, each starting value a
page's `check` or `start` carries — refusing a value that is neither a finite number nor a
bounded word before any session sees it. The `except` line turns what `set` raises into a
refusal on the feed, and a ceiling's refusal into a row in the record, rather than the end
of a session (item 4); like `main`'s `confirmed=` line, it is one line, and with the
`held` pass-through above it is all of `_command` that is welfare-critical; the rest of
that function is ordinary. `_schedule` fixes the target `_ends` compares against — a
trial count from the trial about to run, an instant on the session's clock, or mL this
session, refused when already reached — so a wrong target ends a session early or late
while every check in `_ends` passes.

The split between the two is what keeps each reviewable. `bounds.py` is **pure** — the
ceilings, the daily *floor*, and the arithmetic of whether a number is past one or short of
it, with no clock, no hardware and no state outliving a question. **Fluid has a floor, not a
ceiling** (PI, 2026-09-06): the daily figure is a minimum the animal must reach, supplemented
by hand after the session, so a delivery is never refused on volume and `Floor` is a different
type from `Ceiling` precisely so the two cannot be confused at a call site. **One ceiling ends
a session, and it is time out of the cage** (PI, 2026-09-19): out of the home cage to back in
it, eight hours (the PI corrected the twelve recorded here on 2026-10-01), which is the
interval the institutional limit is about. Chair time and trial
count were the two until then; there is no session-length maximum, per-condition targets are
`scheduler`'s, and chair time is recorded by `HEAD_FIXED`/`HEAD_RELEASED` and bounds nothing.
**Checking a value and moving it are
two calls** — `Bounds.validate` then `Bounds.set` (PI, 2026-09-19) — because a change is
refused when a console offers it and applied a trial boundary later; `set` goes through
`validate`, so the ceiling rule has exactly one home. **A `Ceiling.maximum` is not always a
protocol figure**: it is either that, or a *fault bound* set far above anything a protocol
would ask for, so that what it refuses is software commanding an impossible quantity rather
than an animal earning a ration. `reward_correct`'s maximum is the second kind and
`out_of_cage`'s the first; a bounded config is expected to say which at each entry.

`welfare.py` has all three: the day's running total, two clocks — the out-of-cage one that
bounds the session and the restraint one that is recorded beside it — the wall they are both
read on (`SessionClock`, the host clock read once per session and carried forward on a
steady clock that counts the time the host is asleep; moved here from `taskd` by the P4d-2a
final review, because it decides the interval), the pump, and `Rig`,
which is what a task's `Reward` action actually reaches. **The whole route from a task's
declaration to fluid is readable in `welfare.py` alone**, which is the property to preserve —
"can anything deliver reward without asking the ceiling" should stay a question one file
answers.

**`deliver` also keeps the instant the reward was commanded, once the pump returns**
(`Welfare.last_delivery_wall_at`, P4d-2b b1, 2026-09-26). `Rig.reward` reads that instant
through `Session.wall_now` — the session's `SessionClock`, the one clock every welfare
instant is on — before `deliver` runs, so it is when the reward was commanded, before the
charge and the valve. The charge — `commanded` and `deliveries` — still lands before the
valve opens, as it always did, and the instant is stored only once the pump returns, so a
delivery the pump refused is charged but not timed. It is read for the console's time
since the last reward. Nothing compares it with a limit, and it is not refused when it is
not a number, so a display field can never end a trial.

**Whether a duration limit applies at all is declared, not inferred** (`welfare.Deployment`,
PI 2026-09-19). A rig session declares `RIG_FIXED` or `RIG_CHAIRED` and is refused without both
its mark and its ceiling; a cage-side kiosk session declares `CAGE_SIDE` and has no duration bound,
which S13 §4.0 carries. The field is required on `SessionSpec` with no default, because a rig
session nobody marked and a kiosk session with nothing to mark are indistinguishable to
anything that answers zero — and the absence of a mark must never be what disables a limit.

**Nor may the presence of both.** The interval is opened once, closed once and never runs
backwards: a return is refused unless it closes an open interval, refused while the animal is
recorded head-fixed, and refused before the departure; a closed interval refuses a preflight
and stops a running session rather than freezing its clock. **Out and back is one session**
(PI, asked and answered 2026-09-20): an animal returned briefly and brought out again starts a
new one, at the cost — which he weighed and accepted — of two session directories for an
animal returned mid-day, rather than one record with an unexplained gap. And **both marks are
wall-clock instants, and every welfare duration is read on the wall** (PI, 2026-09-20; P4d-2a
spec §10, 2026-09-26): the departure, the return and the head-fixation marks are kept as the
wall instants they are, so transport and chairing count by subtraction and no caller has a
second base to get wrong. The frame-derived session clock times trials and is passed to
`welfare` nowhere — a simulator counts frames without waiting for them, and mapping one base
onto the other is what failed. S8 §5.2 item 4 has all three accounts.

**Nor may a value that is not a number.** Every guard above is an *ordered* comparison and
**NaN is `False` against all of them**, so one NaN switched the duration limit off entirely —
through a bounded config's ceiling, and through `wlx run --out-of-cage-ago nan` (that flag is
`--out-of-cage-at TIME` since 2026-09-20 and can no longer carry a NaN; the guard stands for
every other caller). `bounds`
refuses a non-finite value at `Ceiling`, at `Floor` and at `validate`, so a limit that is not
a number cannot be constructed at all; `welfare` refuses one at the mark and on the computed
duration. **`inf` breaks them the other way and was not already refused**: it is ordered
but unreachable, so `seconds > inf` is `False` for every real duration and an `inf` ceiling is
never exceeded. An earlier version of this paragraph said `inf` was safe; that was measured
false, which is why the check is finiteness rather than a larger comparison.

Added 2026-09-06, because ceilings alone were not enough: `bounds.check_delivery` was called
by nothing outside its own tests for a week, so a task could command reward, a session could
run to completion, and no ceiling was ever asked. A bound nothing calls reads as present and
is not.

**Not yet welfare-critical, because they do not exist:** token-to-fluid conversion (no token
vocabulary) and stimulation bounds and gating (no `Stim` action). Both belong on this list
the day they are written.

## The task model

**Within a trial: declarative data.** States, guarded transitions, entry/exit actions,
outcome codes. `taskd` executes it; the task never owns the frame loop. Statically
checkable, exhaustively simulatable, renderable as a diagram.

**Between trials: ordinary Python.** Condition selection, blocks, staircases, adaptive
updates.

Representation is **Python declarations** (dataclass/pydantic) — plain text, diffable, and
readable in an ordinary IDE with autocomplete and type checking. Tasks are primarily
model-authored under experimenter direction, so the API optimizes for verifiability and
review rather than authoring ergonomics.

Event codes are **allocated in `wl-exptasks`, never invented in a task**; validation refuses
an unregistered code at load time.

A session is a sequence of **blocks** (condition set, parameter overrides, length rule,
transition) and **interludes** (sub-tasks such as calibration that the session enters and
leaves without ending). Token economies require session-scoped state and a persistent
display layer that per-trial scenes do not reset.

## Message contracts (draft v0)

- **Eye samples** (openiris -> taskd): OpenIris-native UDP poll on 9003
  (`WAITFORDATA` -> JSON). We stamp arrival with `CLOCK_MONOTONIC` and compute staleness.
  The protocol is not modified. The ACCES analog copy is a recorded channel, not the
  control path.
- **Neural features** (`neurofeatd`/`rhxfeatd` -> taskd): ZMQ PUB/SUB, msgpack,
  schema-versioned; feature vector, channel-map hash, source sample index, publisher
  monotonic time, sequence number. Latest-wins.
- **Control/telemetry** (console <-> taskd): ZMQ REQ/REP for commands, PUB for telemetry,
  and PUSH/PULL for an operator's mark signal — eight bytes, read by the trial loop once
  per frame and stamped in the frame it arrives (P4d-2b b2a). Bearer token, rate limit,
  and a write-arbitration rule for concurrent writers.
- **Browser** (browser <-> console): HTTP, with server-sent events carrying rendered HTML
  fragments to the page (P4d-2b spec §1). WebSockets are deferred to the replica pane, if
  V11 shows a browser can carry it at display rate.
- **Hardware truth:** every trial event gets a strobed word into the recorders and a JSONL
  record carrying the word, frame index and monotonic time. **Each trial is framed in the
  stream** (XC-155): `TRIAL_START` (32) and its `TRIAL_NUMBER` escape (`0x8001`, four
  words) at the boundary before its first frame, and `TRIAL_END` (33) after its outcome
  marker. A trial with no outcome (a hang) still gets `TRIAL_END`; a trial that faults or
  is interrupted gets none. The escape is unbroken on every path the loop takes, but not
  on every exit: a card fault, a Ctrl-C, a SIGTERM or a crash between its words cuts it
  short, and wl-preproc's decoder then takes the next words as its payload whatever they
  are, losing that trial and what comes next with it. When a `wlx taskd` session goes on
  to another run with nothing strobed between, that is the next run's `RUN_START` and, if
  the escape was cut after its first or second word, the opening of that run's first
  block, and what the decoder makes of the rest can lose its first trial too (XC-199). A
  block's `BLOCK_START` escape (below) is cut short the same way. Read the stream
  through wl-preproc's `decode_stream`, never by value: from trial 1 the escape's payload
  words take marker values (1-3 are `SESSION_START`, `SESSION_END` and `BLOCK_END`,
  32-38 the trial markers), and trial 3's checksum is `BLOCK_START`'s `0x8002`. The
  number counts from 1 across
  a session's runs and is the trial's `trial_number` in `trials.jsonl`, the field
  wl-preproc will join a line to its recorded trial by, once it reads it (its runs-and-trials plan, which it confirmed on 2026-10-01).
  Every line carries ten position numbers (`levels.Position`; session-levels spec §3).
  `CONDITION` is not emitted yet (XC-197).
  **Each block is marked too** (the session-levels spec, 2026-10-01): `BLOCK_START`
  (`0x8002`, its `block_in_session` and its task's code, 0 until wl-xtasks allocates
  codes) just before the block's first `TRIAL_START`, and `BLOCK_END` (3) after its last
  `TRIAL_END` when its block type is done or its run ends by design; a run that faults
  sends no `BLOCK_END` for its open block, as it sends no `RUN_END`. A block is a
  stretch of trials under one block type inside a run, not a run (the PI, 2026-10-01);
  runs stay `RUN_START`/`RUN_END`.

## The display: direct view, and stereo as viewports

**Two setups share one screen, fixed 50 cm from the eyes** (`2026-09-28-direct-view-design.md`).
**Direct view** — both eyes see the whole panel — is where most experiments run, the first
animal task included. The split-screen mirror stereoscope is a removable device in front of the
same screen. The operator picks the setup at session start. Each setup has its own field in
`geometry.py`, built from the rig's settings (`tasks/rig.py`): the whole panel less the light
sensors' housings, or the stereoscope's viewport stopped by its mask.

**A task says which setup it is written for**: `Trial.view`, `"direct"`, `"stereoscope"` or
`"either"` (the default). Disparity, a random-dot stereogram or a stimulus shown to one eye needs
`"stereoscope"`, a load-time finding at every load. Check 8 against the session's field, and the
refusal of a task written for the other setup, need the session's geometry, and **the checks now
run against the session's own field, from `--rig` and `--view`** (`wlx run` and `wlx check`,
direct view part 2, 2026-09-29): a task that does not pass in the chosen setup is refused before
the session opens. The setup is in the session record and in telemetry schema 9.

Through the stereoscope each eye views one half of the panel through redirection mirrors.
Therefore one window, one flip, one refresh clock, no genlock — **two viewports on one
framebuffer**, in cyclopean coordinates with disparity as a stimulus property. A task without
disparity or per-eye content is the zero-disparity case of the same path, and runs in either
setup.

Per-eye viewport geometry (center, folded optical path length, deg/pixel) is measured, not
derived. Mirror angles set vergence, so alignment is a calibrated parameter with a real
alignment procedure. Photodiode patches sit outside both viewports, at a bottom corner, and
under the sensors' housings in direct view. Panel left/right nonuniformity is by construction
an interocular mismatch and is photometered in V1.

## Neural plane and stimulation

Both systems record; either may gate the loop; **Intan always stimulates.**

| | Local-activity gating | Distant-area gating |
|---|---|---|
| Source | Intan RHX Spike Output socket | SpikeGLX `fetchLatest`, filtered AP stream |
| Client | `rhxfeatd`, Intan host | `neurofeatd`, acquisition PC, C++, loopback |
| Artifact | Severe (same amplifier); RHS amp-settle plus our blanking | Absent |

RHS stimulation is **hardware-triggered from a digital input** — no software in the trigger
path. Stim parameters are pushed over RHX's TCP command interface at safe points only
(session start, block boundaries, ITI), **read back and confirmed**, and bounded by the
rig/subject config. Delivery is counted against the RHS stim-output line, not against
intent.

Three stimulation tiers: epoch-triggered and gaze-triggered are **v1** (so welfare
interlocks are v1 work); neural-triggered is post-v1.

## Sync conventions (day-one requirements)

Owned by `wl-sync`; our obligations are to feed it correctly. One shared barcode line into
the recorders and the camera GPIOs; two photodiode patches with fixed roles; 16-bit strobed
event words; every TTL we emit also recorded; offline reconstruction scripts with
round-trip tests.

## Data outputs and lab integration

Per session: JSONL trial/event log, parquet behavioral tables, a complete config and
provenance snapshot (resolved parameters, bounded config, gaze-mapping versions, task and
code versions, plot declaration, parameter-change log), and a DONE marker conforming to
`wl-preproc`'s published schema. Raw neural data never touches the task PC.

**The rig cannot push to the ELN.** wl-works binds only to WireGuard and lab machines have
no route in **for the application layer**, and `wl-preproc` enforces "never initiates a
connection" with an AST guardrail. **One narrow exception exists since ADR-0009
(2026-09-20): a lab host has a route to wl-works on UDP 123 only, to synchronize its
wall clock over NTP against `ntp.wl.works`** — the hostname is the PI's, named
2026-09-20 — because welfare marks are now clock times and the daily fluid figure
spans deployments that must agree what time it is, and nothing did. **That route does
not exist yet**: naming the server settled which system serves the time and not how a
lab host reaches it, and the ask is open in `docs/pending-wl-works-amendments.md`. Be precise about
what changed: a system time daemon is a different layer from the AST-guarded
application source, so the guardrail above is untouched; what is no longer unqualified
is the routing claim itself, narrowed rather than reversed. NTP serves bookkeeping time
only — which day it is, when a mark was made — never the timing record, which remains
the sync box's hardware ticks and the strobed event words (S3). Application integration
is otherwise still pull-based and reuses `wl-preproc`'s existing lab-host protocol, in three
directions: wl-works pushes a `prepare-session` action carrying the ELN metadata bundle;
live session state is exposed as **readings on `GET /health`**; and the finished session
summary is **a file in the session directory** that `wl-preproc` ingests, because the
protocol declines result upload. No welfare-affecting action — reward, stimulation, session
start, parameter change — is ever published through it, since wl-works' permission model is
flat by design. Drafted at `docs/pending-wl-works-amendments.md`.

Behavioral visualization lives here; **neural visualization stays in `wl-expviz`**.

## Platform

**NI-DAQmx 2026 Q2 supports RHEL 9.6/10.0, openSUSE 15.6/16.0 and Ubuntu 22.04/24.04 LTS —
not Fedora** (read 2026-08-31). `wl-stack` standardizes the lab on Fedora, so the task PC
deviates deliberately: **Ubuntu 24.04 LTS**, recorded as a rig-class decision, dual-booting
Windows to satisfy the MonkeyLogic swap. `PCIe-6343`-on-Linux is **UNVERIFIED** until a card
runs on a bench (P10).

## Open questions

Tracked in the design spec §16. The ones that block others: escape-hatch strictness (S1),
touchscreen configuration, display panel and refresh, photodiode patch placement against
the real optics, and the event-code allocation.
