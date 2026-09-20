# S9 — Operations and console

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §11

Not an appendix. Three items here are the verification loop that makes model-authored tasks
safe (ADR-0006), and they carry v1 status alongside the display module.

**Written for a stranger** (PI, 2026-08-31). People arrive with or before the animals in January,
and a tech or student runs the rigs day to day rather than the PI. So the reader of every
operator-facing string in this system is someone who has never read a spec. Three consequences,
and they are requirements rather than aspirations:

1. **An error that requires knowing the design to interpret is a bug.** Preflight failures name
   the fix, not just the failure; abort reasons are self-explanatory; nothing surfaces an
   internal identifier as though it were an explanation.
2. **Operator documentation is an M1 deliverable** — a "how to run a session" document, not a
   design doc (pitfalls P8).
3. **The naive-operator test is attempted early and repeatedly**, not once at M5.

---

## 1. The process split is a hard rule

`taskd` and `console` are separate processes under all conditions. **The hot loop never renders
a plot, serves a request, or holds a UI.** Four requirements now depend on it: plots off the
frame budget, the external control API, remote access, and the kiosk running a console at all.

The link is ZMQ — REQ/REP for commands, PUB for telemetry — with a bearer token and a rate
limit.

**Amended 2026-09-19.** This sentence also carried "S8 §3.3's arbitration rule between
concurrent writers"; there is no write lock to arbitrate (S9a §8). And under ADR-0008 the
box serves HTTP — but from the `console` process, never from `taskd`, so the rule above is
unchanged rather than bent (S9a §7).

---

## 2. Preflight

**One action, one red/green list, before any session.** The highest-value operational item in
the project: it prevents the two-hours-recorded-with-no-eye-data class of loss.

| Check | Why it earned a line |
|---|---|
| Tracker streaming, and staleness within ceiling | S5 — a tracker that is "up" but stale is the failure that looks fine |
| **Session id readable from the sync box** | S3 §6 — we cannot name our own output directory without it |
| Sync box up, current segment healthy | It defines session time |
| DAQ present; all 19 out and 4 in respond | S6 — a loopback test, not an enumeration |
| **Both photodiode patches responding** | Task patch *and* flip patch, driven and read back |
| **Optics alignment residual within tolerance** | Optics drawing §4.4 — the mirrors are adjustable per animal, so this is per-session, not per-build |
| SpikeGLX / RHX running and armed | Including RHX's TCP output configured within its measured margin (V8) |
| Display at expected mode and refresh | S0 §5.3 — mode is rig configuration and V1 is per mode |
| `stimulus_calibration_id` current | S4 §9 — invalid if anything feeding it changed |
| **Daily fluid total reconstructable** | S8 §5.2 — if it is not, the day's supplement is unreportable and preflight must say so *before* the animal is in the chair. (This said "reward is refused"; **reversed 2026-09-06**, S8 §5.2 item 3 — there is no fluid ceiling, and an uncountable day must not stop paying an animal that is working) |
| **Animal recorded as out of its cage** | S8 §5.2 item 4 — the session's one duration limit runs out-of-cage to back-in-cage, and `welfare` refuses a rig session whose mark is missing rather than running it unbounded. A cage-side deployment declares `CAGE_SIDE` instead (S13 §4.0) |
| **Day's prior fluid known** | S8 §5.2b — one daily figure spans rig and kiosk. **Corrected 2026-09-06: it is a floor**, so this preflight item is what makes the end-of-session supplement computable, and an unknown prior total makes that unreportable rather than stopping reward |
| **Head-fixation recorded** — *`RIG_FIXED` only* | S8 §5.2 — restraint has no hardware line, so `HEAD_FIXED`/`HEAD_RELEASED` are its only durable record. (Chair time stopped being the session's duration limit on 2026-09-19; the preflight requirement stays for the kind that has the marks, because such a session with neither code has no record of a restraint that happened. **Since 2026-09-20 this is per deployment**: `RIG_CHAIRED` takes no head-fixation marks, and `welfare` refuses one rather than recording restraint it did not measure) |
| Pump primed, calibration in date | S6 §4 — an uncalibrated pump makes fluid numbers fiction |
| Disk space for a full session | |
| **Config diff against last session** | "This rig differs in 3 ways" catches the change nobody remembers making |

A failed check names the fix, not just the failure.

**Three states, not two** (settled 2026-09-19; S9a §10 carries the reasoning). A check
that has **failed** blocks. A check whose answer is **unknown** proceeds, on an explicit
acknowledgement written into the session record naming who accepted it and what was
unknown. There are no exceptions to that, including the pump calibration — which is safe
only while the real pump driver may not be written before V10 exists, and must be
revisited the day it is. The shape is chosen against the failure mode where a gate refuses
so often that people route around it, at which point it protects nothing.

---

## 3. Running a session

- **Pause** at a trial boundary, console fully live, resume. The thing MonkeyLogic makes
  awkward, so it is designed as a first-class state rather than an interruption.
- **Emergency stop** is distinct: immediate, mid-trial, safe — stimulus blanked, stimulation
  inhibited, reward stopped, trial marked aborted. Pause is for thinking; stop is for trouble.
- **Animal fixed / released** — an explicit console action, required before a `RIG_FIXED` session
  starts and **refused** for the other two deployment kinds (PI, 2026-09-20), event-coded as
  `HEAD_FIXED` / `HEAD_RELEASED`. It starts and stops the restraint clock, which is **recorded and
  bounds nothing** since 2026-09-19; nothing else in the system knows when the animal went in. A
  `RIG_CHAIRED` session reports restraint as **absent rather than zero** — it is restrained and
  unmarked, and a clock at zero would claim a measurement nobody took.
- **Out of cage / back in cage** — the console action added 2026-09-19 beside it, and the one
  preflight now depends on: it starts the twelve-hour clock that *is* the welfare limit (S8
  §5.2 item 4). A rig session without it is refused; a cage-side deployment declares it has no
  such interval (S13 §4.0). **It is given as a clock time** — `wlx run --out-of-cage-at`, and the
  console action the same — because that is what an operator reads (PI, 2026-09-20), and the
  session prints the interval it computed so a mistyped hour is legible. **It gets no event
  code**: the marks are operator-entered rather than measured (PI, 2026-09-20, closing S8 open
  item 8).
- **Warning as the out-of-cage limit approaches** — `welfare.approaching_limit`, shown beside the
  stop reason, so a block can be finished deliberately rather than cut mid-sequence (PI,
  2026-09-20). The threshold is configurable and its default is a proposal, not a settled figure.
- **Manual reward** commands through the normal path so it logs as commanded *and* delivered,
  distinguishable from a panel press (S6 §4).
- **Generated parameter panel**, derived from the task's declaration — typed widgets, range
  limits, validation, staged application (S8 §3). No per-task UI code, which is what makes it
  work for tasks nobody hand-wrote.
- **Per-condition counters** showing achieved against target.
- **Abort-reason readout** — the most-asked question at any rig, trivial because terminal states
  carry outcome codes.
- **Fluid and session accounting** against the ceiling, continuously.

---

## 4. Live plots

Declared, not drawn. The task declares its **trial outcome schema** and selects from a closed
vocabulary: running series, distribution, grouped comparison, **spatial map in visual-field
coordinates**, psychometric/staircase, outcome raster by abort reason, gaze overlay.

Four rules:

1. Plots compute in the console process. No plot can cost a frame.
2. Bounded incremental accumulators — nothing re-fits the history each trial.
3. Plots derive from **the same trial records written to disk**. Divergent paths eventually
   disagree and you believe the wrong one at the worst moment.
4. The plot declaration is saved with the session, so the live view reproduces exactly offline
   and the same renderer serves finished sessions and cross-day comparisons.

**Boundary:** behavioural dynamics here, neural visualisation in `wl-expviz`.

---

## 5. Demo mode and simulated sessions

**These are the D4 acceptance test, not conveniences.**

- **Keyboard/mouse demo mode** — any task drivable with the mouse standing in for gaze and keys
  for responses, in thirty seconds, with no hardware. Mouse also stands in for touch (S13).
- **Simulated sessions** — replayed eye recordings plus synthetic behaviour agents, running
  thousands of trials and asserting termination, reachability, outcome coverage, parameter
  ranges honoured, and no dead states.

**The gate:** a task Claude wrote is approved from its rendered state diagram, its condition and
event-code table, and its simulation report — **without reading the source.** If that is not
possible, the design failed, not the reviewer (ADR-0006).

---

## 6. Test screens

Per S4 §10, with one required at every session start: the **per-eye alignment / vergence
target**, residual recorded. Plus geometry grid, gamma ramp, photodiode patch test, frame-timing
pattern per mode, and disparity verification.

---

## 7. Remote and one-action launch

**A remote console is the design, not remote desktop.** The console runs on another machine over
ZMQ — telemetry rather than pixels: low bandwidth, responsive, several consoles at once.

**Screen sharing on the task PC is a timing hazard** (P4): capture stacks hook the graphics
pipeline on the machine whose whole job is frame-accurate presentation. Remote desktop stays
available for rig-local work, off during recording, and the flip patch will show it if someone
forgets.

**One-action launch**: a desktop entry that brings up `taskd`, the console and preflight together.
A physical start button through the sync box's GPIO is feasible later if wanted.

---

## 8. Toolkit

**Superseded 2026-09-19 by ADR-0008.** The console is a web application served by each
control box, because an iPad cannot run Qt and two operator surfaces is two sets of bugs for
the stranger this document is written for. The "no gain" clause below did not survive contact
with two later decisions: `labhost` (P4c) and `wl-works`' Plan 10 responder contract both put
an HTTP server on every lab machine regardless, so the server was never the distinguishing
cost. What survives is §1's rule — the hot loop serves no requests — which a console process
beside `taskd` honours either way.

What this section said: *"**PyQtGraph** for the live plots — the boring, correct choice for
rig-side scientific plotting at trial rates, and it stays local so the console never depends on
a network or a browser. Matplotlib is too slow for live use; a web UI would put a server on the
rig for no gain, since wl.works already covers anything a browser should show."*

---

## 9. Session notes

Notes typed at the console land in the session record and reach the **wl-works ELN** through the
pull path (parent §12.3) — not into a text file nobody reads, and not by the rig pushing, which
the network topology forbids.

---

## 10. Open items

| # | Item | Blocks |
|---|---|---|
| ~~1~~ | ~~Arbitration between console and control-API writers (S8 §3.3)~~ **Closed 2026-09-19: there is no write lock, so there is nothing to arbitrate.** Both are ordinary writers; `bounds` is the welfare boundary, and visibility replaces coordination. S9a §8 | — |
| ~~2~~ | ~~What preflight does when a check is *unknown* rather than failed~~ **Closed 2026-09-19: unknown proceeds on a recorded acknowledgement; only an actual failure blocks.** S9a §10 | — |
| 3 | Whether the console can run against a live session it did not start | remote use |
| 4 | Behaviour-agent fidelity — how realistic a synthetic animal needs to be | the simulation gate's value |
