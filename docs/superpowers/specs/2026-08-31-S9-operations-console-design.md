# S9 — Operations and console

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §11

Not an appendix. Three items here are the verification loop that makes model-authored tasks
safe (ADR-0006), and they carry v1 status alongside the display module.

---

## 1. The process split is a hard rule

`taskd` and `console` are separate processes under all conditions. **The hot loop never renders
a plot, serves a request, or holds a UI.** Four requirements now depend on it: plots off the
frame budget, the external control API, remote access, and the kiosk running a console at all.

The link is ZMQ — REQ/REP for commands, PUB for telemetry — with a bearer token, a rate limit,
and S8 §3.3's arbitration rule between concurrent writers.

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
| **Daily fluid total reconstructable** | S8 §5.2 — if it is not, reward is refused and preflight must say so *before* the animal is in the chair |
| **Day's prior fluid known** | S8 §5.2b — one budget spans rig and kiosk, so the ceiling is `ceiling − already_delivered_today` and an unknown prior total fails closed |
| **Head-fixation recorded** | S8 §5.2 — session duration is chair time, and the clock cannot start without it |
| Pump primed, calibration in date | S6 §4 — an uncalibrated pump makes fluid numbers fiction |
| Disk space for a full session | |
| **Config diff against last session** | "This rig differs in 3 ways" catches the change nobody remembers making |

A failed check names the fix, not just the failure.

---

## 3. Running a session

- **Pause** at a trial boundary, console fully live, resume. The thing MonkeyLogic makes
  awkward, so it is designed as a first-class state rather than an interruption.
- **Emergency stop** is distinct: immediate, mid-trial, safe — stimulus blanked, stimulation
  inhibited, reward stopped, trial marked aborted. Pause is for thinking; stop is for trouble.
- **Animal fixed / released** — an explicit console action, required before a session starts,
  event-coded as `HEAD_FIXED` / `HEAD_RELEASED`. It starts and stops the restraint clock, which is
  the welfare limit; nothing else in the system knows when the animal went in.
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

**PyQtGraph** for the live plots — the boring, correct choice for rig-side scientific plotting at
trial rates, and it stays local so the console never depends on a network or a browser. Matplotlib
is too slow for live use; a web UI would put a server on the rig for no gain, since wl.works
already covers anything a browser should show.

---

## 9. Session notes

Notes typed at the console land in the session record and reach the **wl-works ELN** through the
pull path (parent §12.3) — not into a text file nobody reads, and not by the rig pushing, which
the network topology forbids.

---

## 10. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Arbitration between console and control-API writers (S8 §3.3) | the control API |
| 2 | What preflight does when a check is *unknown* rather than failed | preflight semantics |
| 3 | Whether the console can run against a live session it did not start | remote use |
| 4 | Behaviour-agent fidelity — how realistic a synthetic animal needs to be | the simulation gate's value |
