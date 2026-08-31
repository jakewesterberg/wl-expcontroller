# S9a — The experimenter console

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** S9; ADR-0002

---

## 1. Shape, settled

**A desktop application: PySide6 with PyQtGraph** (PI, 2026-08-31). Qt because the live
plots need PyQtGraph and PyQtGraph is Qt; desktop because plots at trial rates are a
stated requirement and a browser would put an HTTP server on a machine whose whole job
is frame-accurate timing.

**`taskd` owns the session; consoles attach.** A session survives the console closing,
crashing, or sitting on a laptop whose lid shuts over a working animal. Several consoles
may watch; one holds the write lock. That is also what makes the *remote* console real
rather than a viewer — S9 §7's remote operation is this decision, not a feature.

---

## 2. The experimenter screen is a replica, not a dashboard widget

MonkeyLogic's Graphics Library draws **two parallel screens**: the subject's, and an
exact replica scaled to the experimenter's, carrying *"additional information for the
experimenter, such as online states of input signals, fixation windows and custom user
strings"* ([Hwang et al. 2019](https://pubmed.ncbi.nlm.nih.gov/31071345/)).

**Take this wholesale.** The experimenter sees what the animal sees, with the invisible
things drawn on top: gaze, the windows, joystick position, which stimulus is up. A
separate "eye tracking depiction" widget beside a stimulus preview would be two things a
person has to correlate by eye, several times a minute, forever.

### 2.1 What a stereoscope does to that idea

The subject sees two viewports through mirrors; the replica cannot simply mirror one
screen. Proposed: **draw the cyclopean view** — the task's own coordinate frame — with
disparity shown as an annotation rather than as two panels, and gaze drawn per eye so
vergence is visible. A two-panel replica would be literal and would make the experimenter
do the fusing, which is the animal's job and not theirs.

**Open:** whether a dichoptic trial (different content per eye, S1a §4.1) needs a
two-panel mode after all. It is the one case a cyclopean replica genuinely cannot show.

### 2.2 Calibration by clicking

ML puts targets on the subject screen by clicking the corresponding place on the control
screen. Adopt it: the replica is already in task coordinates, so clicking it *is* naming
a position in degrees. The calibration grid (S5 §7, a 3×3 — never a ring) is then a
sequence of clicks or one button, and drift correction is a click where the animal is
actually looking.

---

## 3. Information density is the requirement, not a risk

The PI's words: *"it is information dense."* A rig console is read at a glance, many
times an hour, by someone doing three other things. Sparse is not calm here; it is a
person opening panels to find out whether an animal is working.

Everything below is visible without clicking. Four groups, ranked by what a glance is
for:

| Group | Carries |
|---|---|
| **Animal** | Fluid against ceiling, chair time against ceiling, both reconciled (P17) not tallied |
| **Working?** | Running / paused / fault, trials attempted / completed / correct, recent performance |
| **Wrong?** | Abort reasons, dropped frames from the flip patch, tracker staleness, RHX backpressure margin |
| **Still needed** | Per-condition achieved against target — the question actually asked at a rig |

Plus, from the PI and not in S9: **configuration information** (which task, which
allocation, which bounded config, which stimulus calibration, display mode), **task
selection**, and the replica of §2.

---

## 4. Layout

```
┌─ Task: detection@3   Subject: A   Session: 2027-01-14_01   ● RUNNING ─────────┐
├──────────────────────────────┬────────────────────────────────────────────────┤
│                              │  ANIMAL                                        │
│   EXPERIMENTER REPLICA       │   fluid   142 / 250 mL  ▓▓▓▓▓▓░░░░             │
│   (what the animal sees,     │   chair    1:47 / 4:00  ▓▓▓▓░░░░░░             │
│    plus windows, gaze,       ├────────────────────────────────────────────────┤
│    joystick, disparity)      │  TRIALS   340 att / 318 done / 241 correct     │
│                              │   last 20  ▁▃▅▆▇▇▆▅  76%                       │
│                              ├────────────────────────────────────────────────┤
│                              │  WRONG?   drops 0   stale 1.2%   RHX 61% margin│
│                              │   aborts  fix_break 18  no_fix 44  no_resp 12  │
├──────────────────────────────┼────────────────────────────────────────────────┤
│  PLOTS  accuracy over time   │  STILL NEEDED  by condition                    │
│         RT distribution      │   ecc  0°  ▓▓▓▓▓▓▓▓░░  82/100                  │
│         accuracy by position │   ecc 10°  ▓▓▓▓▓░░░░░  51/100                  │
├──────────────────────────────┴────────────────────────────────────────────────┤
│  PARAMETERS (generated)   fix_hold [0.30] s   ecc [10.0]°   contrast [0.45]   │
├───────────────────────────────────────────────────────────────────────────────┤
│  [Pause] [Stop] [Reward] [Animal fixed] [Calibrate] [Recentre] [Test screens]  │
└───────────────────────────────────────────────────────────────────────────────┘
```

The parameter row is **generated from the task's declaration** (S8 §3.1) — typed widgets,
range limits, validation, staged application. No per-task UI code, which is what makes it
work for a task nobody hand-wrote.

---

## 5. The Python ceiling, found by installing it

**PsychoPy 2026.2.3 declares `>=3.10,<3.13`. Python 3.13 cannot run the display layer.**

Nothing in this repository or `wl-preproc`'s said so. Three consequences:

1. `wl.yaml`'s Python constraint is now `>=3.11,<3.13`.
2. **A Fedora workstation cannot run the display code**, since `wl-preproc` records that
   3.13 is what Fedora ships. Development of the display layer happens on 3.12.
3. **S0's Ubuntu 24.04 choice is right for a second, independent reason** — it ships
   Python 3.12. It was chosen for NI-DAQmx; it also happens to be the only mainstream
   option that satisfies both constraints at once.

CI keeps a 3.13 leg **deliberately**, testing the core — schema, checks, encoder, runner,
record — which has no display dependency and must not acquire one. If a 3.13 job ever
fails on an import, something has leaked through `DisplayAdapter`, and that is worth
failing over.

---

## 6. Open

| # | Item |
|---|---|
| 1 | Whether dichoptic trials need a two-panel replica (§2.1) |
| 2 | Whether the replica renders through the same `DisplayAdapter` as the subject screen, or a second lighter path — the same code is truer, a second one cannot cost the subject a frame |
| 3 | Task selection: from a directory, from `wl-mllib`, or pushed by wl.works with the session |
| 4 | Whether plots dock inside the console or float, given a second monitor is likely |
