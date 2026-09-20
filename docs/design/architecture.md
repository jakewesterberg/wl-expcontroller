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
| `taskd` | Task PC (Linux) | Python | Trial execution, display, gaze logic, DIO, session record | Full headless run against replayed/synthetic inputs |
| `console` | The control box, in a browser on the LAN | Python server + web client | Experimenter UI, live plots, parameter writes, preflight, test screens. **The box authenticates and records the actor** — anybody attached has full access, with visibility rather than a lock (S9a §8); `wl-works` lists devices and links to them, and carries no welfare-affecting action (ADR-0008). **The link exists** (`wl_expcontroller/link.py`, P4d-1, 2026-09-19): `taskd` holds a `Link` port, drained and published once per trial boundary and never per frame, whose live implementation (`ZmqLink`) binds a ZMQ PUB socket for `Telemetry` and a REP socket for `SetParameter`/`Stop` commands (ADR-0003's transport, untouched). `ZmqConsole` is the other end. Reached today by `wlx run --link PUB,REP` and a terminal client, `wlx console --sub PUB --req REP --as WHO`; the browser client and the HTTP/WS server this row otherwise describes — which is also where `labhost` lives (S9a §7) — are P4d-2 | Runs against a fake `taskd` (`link.Simulated`), or a real one over loopback sockets |
| `neurofeatd` | Acquisition PC | C++ | SpikeGLX `fetchLatest` on the filtered AP stream -> MUA features -> ZMQ PUB | Synthetic feature publisher |
| `rhxfeatd` | Intan host | C++/Rust | RHX Spike Output socket -> features -> ZMQ PUB; bounded reader | Synthetic spike-raster publisher |
| `labhost` | Task PC | Python | The pull-only endpoint wl-works polls — **a surface of `console` since 2026-09-19, not its own process** (S9a §7): same server, separate path, separate auth | Contract tests |
| `openiris` | OpenIris PC | (existing C#) | dDPI tracking; UDP 9003; remote API; analog out | UDP replay server |

Welfare-critical modules requiring human review: reward scheduling and per-delivery limits,
fluid and session-duration accounting (a fluid **floor**, an out-of-cage **ceiling**),
token-to-fluid conversion, stimulation bounds and gating, and the bounded-config loader.

**In code, that is `wl_expcontroller/bounds.py` and `wl_expcontroller/welfare.py`, and
nothing else.** Both are kept small deliberately: everything in them can hurt an animal if
it is wrong, and a small file is one a person can actually read before signing it off. A
change to either is a change requiring review; a change elsewhere is not.

The split between the two is what keeps each reviewable. `bounds.py` is **pure** — the
ceilings, the daily *floor*, and the arithmetic of whether a number is past one or short of
it, with no clock, no hardware and no state outliving a question. **Fluid has a floor, not a
ceiling** (PI, 2026-09-06): the daily figure is a minimum the animal must reach, supplemented
by hand after the session, so a delivery is never refused on volume and `Floor` is a different
type from `Ceiling` precisely so the two cannot be confused at a call site. **One ceiling ends
a session, and it is time out of the cage** (PI, 2026-09-19): out of the home cage to back in
it, twelve hours, which is the interval the institutional limit is about. Chair time and trial
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
bounds the session and the restraint one that is recorded beside it — the pump, and `Rig`,
which is what a task's `Reward` action actually reaches. **The whole route from a task's
declaration to fluid is readable in `welfare.py` alone**, which is the property to preserve —
"can anything deliver reward without asking the ceiling" should stay a question one file
answers.

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
animal returned mid-day, rather than one record with an unexplained gap. And the opening mark
is **how long ago**, against the session's frame-derived clock, so that counting transport and
chairing does not depend on a caller knowing to pass a negative instant — S8 §5.2 item 4 has
all three accounts.

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

Event codes are **allocated in `wl-mllib`, never invented in a task**; validation refuses
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
- **Control/telemetry** (console <-> taskd): ZMQ REQ/REP for commands, PUB for telemetry.
  Bearer token, rate limit, and a write-arbitration rule for concurrent writers.
- **Hardware truth:** every trial event gets a strobed word into the recorders and a JSONL
  record carrying the word, frame index and monotonic time.

## Stereo, as viewports

Split-screen mirror stereoscope on **one panel**: each eye views one half through
redirection mirrors. Therefore one window, one flip, one refresh clock, no genlock —
**two viewports on one framebuffer**, in cyclopean coordinates with disparity as a
stimulus property. The monocular v1 task is the zero-disparity case of the same path.

Per-eye viewport geometry (center, folded optical path length, deg/pixel) is measured, not
derived. Mirror angles set vergence, so alignment is a calibrated parameter with a real
alignment procedure. Photodiode patches sit outside both viewports. Panel left/right
nonuniformity is by construction an interocular mismatch and is photometered in V1.

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
no route in, and `wl-preproc` enforces "never initiates a connection" with an AST guardrail.
Integration is pull-based and reuses `wl-preproc`'s existing lab-host protocol, in three
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
