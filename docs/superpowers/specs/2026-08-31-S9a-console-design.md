# S9a — The experimenter console

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** S9; ADR-0002

---

## 1. Shape, settled

**Superseded 2026-09-19 by ADR-0008: a web application served by each control box.**
Three things changed — the kiosk became real and an iPad cannot run Qt; `labhost` and
`wl-works`' Plan 10 responder put an HTTP server on the box by design anyway, so "a
server on the rig" no longer distinguishes the options; and `wl-works` already specifies
the device directory. The replica pane (§2) is the one part not settled by that ADR: it
is gated on **protocol V11**, a measurement, not on anyone's view of browsers.

What this section said, kept because it is the argument the ADR had to answer:
*"**A desktop application: PySide6 with PyQtGraph** (PI, 2026-08-31). Qt because the live
plots need PyQtGraph and PyQtGraph is Qt; desktop because plots at trial rates are a
stated requirement and a browser would put an HTTP server on a machine whose whole job
is frame-accurate timing."*

**`taskd` owns the session; consoles attach.** A session survives the console closing,
crashing, or sitting on a laptop whose lid shuts over a working animal. Several consoles
may attach at once. That is also what makes the *remote* console real rather than a
viewer — S9 §7's remote operation is this decision, not a feature.

> **Amended 2026-09-19.** This said "one holds the write lock". There is no write lock:
> anybody attached has full access, because `bounds` is the welfare boundary and a lock
> would only buy coordination — at the price of an animal waiting on a sleeping laptop.
> §8 has what replaces it.

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
2. Fedora ships 3.13, but **this is a provisioning detail, not an incompatibility** —
   `dnf install python3.12` and the rig uses that. Corrected 2026-08-31; an earlier
   version of this section overstated it.
3. **It does not add a reason to prefer Ubuntu.** S0's choice rests on NI-DAQmx, which
   is an out-of-tree kernel module against unsupported distributions and is not fixed by
   installing another Python. One reason, not two.

**And it is an argument against PsychoPy rather than for a Python version** — ADR-0002
is reopened on it, among other things.

CI keeps a 3.13 leg **deliberately**, testing the core — schema, checks, encoder, runner,
record — which has no display dependency and must not acquire one. If a 3.13 job ever
fails on an import, something has leaked through `DisplayAdapter`, and that is worth
failing over.

---

## 6. Identity and authority

Settled 2026-09-19, after ADR-0008. **The box is the authority**, because `wl-works`
deliberately will not be: its Plan 10 §4.1 is the first line of its protocol document —
*"Publishing an action makes it available to every member of the lab. There is no
permission model on the app side."* On a preprocessing server the worst case is wasted
compute; on a rig it is fluid, or a session started on an animal nobody is standing next
to.

**The box is an OAuth2 client of `wl-works`.** Not a bespoke scheme: read from their
source 2026-09-19, `src/lib/auth.ts` registers better-auth's `mcp()` plugin, which *is*
the OAuth provider in 1.7.1 and serves the `/oauth2/*` surface Zulip already consumes,
with per-client PKCE. Revocation is proven end to end there — an admin deactivating a
member cut their already-open Zulip session as a direct result. So the ask on `wl-works`
is to register a client, not to build token issuance.

**Two entry points, one console.** The same page, reached two ways, because two UIs would
be the two-operator-surfaces mistake ADR-0008 exists to avoid:

- **Via `wl-works`** — sign in there, land on the box, the box verifies the token. Actions
  are attributed to a real account, and deactivating that account revokes access to every
  box at once.
- **Locally** — straight to the box, authenticated by the box's own credential. Always
  works, never touches the network. **A permanent peer, not an emergency hatch** (PI,
  2026-09-19), so that a `wl-works` outage cannot cost an operator the console with an
  animal in the chair.

**`Actor` is two types, not one type with a nullable name.** `Verified(person, issuer,
token id)` and `Local(box credential)`. Different types for the reason `Floor` and
`Ceiling` are different types: so no call site can treat them alike, and so "we do not
know who" can never render as a name. A forgeable name is worse than no name, because it
is believed.

**The degradation is loud.** The console header states its mode. Every welfare-affecting
action records its actor type, and a session whose welfare actions were unattributed says
so in its summary. The local path is not prevented — preventing it defeats its purpose —
it is made impossible not to notice.

**Token expiry mid-session interrupts nothing.** The session continues, the console drops
to local mode, and the transition is recorded as an event. Never raise out of a trial the
animal is completing, which is the rule `welfare.Rig` already follows for pump faults.

---

## 7. Processes and protocol

```
   wl-works ──── polls /health, links to the console ─────┐
       │  OAuth2 (identity)                               │
       ▼                                                  ▼
browser ──HTTP/WS──►  console  ──ZMQ REQ/REP (commands)──►  taskd ──► world, devices
                      ├ OAuth client + local credential  ◄──ZMQ PUB (telemetry)──┘
                      ├ static assets, WS fan-out
                      └ /health  (the labhost surface)
```

**Two processes, and the split was already mandatory.** §1 of S9: *"`taskd` and `console`
are separate processes under all conditions. The hot loop never renders a plot, serves a
request, or holds a UI."* An HTTP server inside `taskd` is out on that rule alone.

**ADR-0003's link is untouched** — REQ/REP for commands, PUB for telemetry, msgpack,
schema-versioned. The console is a new client of an existing contract, not a new
transport.

**The console can die without the experiment noticing.** It holds HTTP sessions, OAuth
state and a cache of the last telemetry so a newly-opened browser renders immediately. It
holds no authoritative session state. Restart it mid-session and nothing in the trial loop
changes, which is the property §1 asks for when it says a session survives the console
closing.

**Identity crosses one trust boundary and it is explicit.** `wl-works` asserts identity to
the box, signed. Inside the box the console asserts the actor to `taskd` over ZMQ and
`taskd` trusts it, because they are the same machine and the console *is* the
authenticator. Command messages therefore carry an `actor`, and the audit is written by
`taskd`, where the validated write path already lives.

**`labhost` stops being its own component.** P4c's pull-only `/health` endpoint becomes a
surface of the console process rather than a second server on the box: same process,
separate path, separate auth, since `wl-preproc`'s lab-host protocol carries its own
bearer token and deliberately no permission model.

**The subject's display is not affected by any of this.** S13 §3 routes the kiosk through
the display module's zero-disparity path, so `DisplayAdapter` is unchanged and ADR-0002
stays deferred. The console is an operator surface only.

---

## 8. Writers: visibility instead of a lock

Settled 2026-09-19 (PI): *"anybody connecting to the session should be able to access
features full access."* **There is no write lock.** S9 §10's open item 1 — arbitration
between console and control-API writers — resolves by dissolving: both are ordinary
writers.

**This is safe because `bounds` is the welfare boundary, not the lock.** Two writers
cannot do harm concurrently: a per-delivery magnitude is ceiling-checked whoever asks,
fluid is a floor with no ceiling to race against, mappings are versioned, and stop is
idempotent. Concurrent writers cause *confusion*, not damage — and confusion is cheaper to
solve with visibility than with a lock that makes an animal wait while somebody's laptop
is asleep.

Three things replace it:

- **Presence.** Every console shows who else is attached.
- **A live change feed.** Every parameter change, reward and state transition appears on
  every attached console with its actor.
- **Staged changes are visible to everyone, not only to whoever staged them.** This is the
  one that carries the weight. With no lock, the only thing standing between a change and
  an invisible parameter move is that everybody can see it.

Last-write-wins within an ITI, both writes recorded with their actors, and the resolution
shown.

### 8.1 "Staged" means two different things, and the code has always known which

Corrected 2026-09-19, against the code rather than against this paragraph's earlier
wording — which said `Session.set` "stages and applies at the next trial boundary" of
every change alike, and was true of only one of the two kinds.

| | Ordinary task parameter | Welfare-bounded value (e.g. `reward_correct`) |
|---|---|---|
| When the value moves | Next pass, in `Session._apply_staged` | **Immediately**, in `Session.set`, as the command is drained |
| The trial running in that pass | Uses the **old** value | Uses the **new** value |
| `PARAM_CHANGED` strobe + `parameter_changes.jsonl` row | Next pass | Next pass |
| Shown on the console as | `staged` — pending | `staged` — **already in effect** |

`welfare.Rig.deliver` reads `bounds.value(ref)` at the moment it opens the valve, and
`Session.set` has already moved that ceiling, so there is nothing left to defer. Measured
on `p4d1-console-link` with a six-trial session and one queued
`SetParameter(reward_correct, 0.30)` against a starting value of 0.15: trial 0 commanded
0.30 mL, and the `parameter_changes.jsonl` row for it was written between trial 0 and
trial 1.

**This is not over-delivery.** The ceiling (`Ceiling.maximum`) is enforced on the way in
whichever path is taken, and nothing lands mid-trial on either. It is an *attribution*
problem: **for a welfare-bounded name the record is off by one trial**, so anyone
reconciling commanded fluid against `parameter_changes.jsonl` offline will assign one
trial's delivery to the wrong value.

**Open for the PI, not settled here.** Should a welfare-bounded change apply immediately,
as it does, or defer like an ordinary one? Deferring means an operator who has just
lowered a reward volume watches one more trial go out at the old one; keeping this means
the record needs a second strobe point, or this section becomes the contract and offline
tooling has to know it. Either fix touches something that is expensive to get wrong — the
call path into a welfare-critical module, or this spec — so it is a question rather than a
table entry. It is marked in the source at `taskd.Session.set`, where the behavior lives.

---

## 9. The telemetry contract

**One rule: every number on the console comes from the object the record is written from,
never computed beside it.** This is where a number nobody measured would get in, and the
defence is structural rather than careful.

| Pane | Source |
|---|---|
| Fluid delivered / floor / supplement | `welfare.session_total`, `total_today`, `shortfall()`, `bounds.minima` |
| Chair time | `welfare.chair_seconds` — frame-derived, so it matches the ceiling that ends the session |
| Trials, outcomes, aborts by reason | `simulate.Tally`, already shared with `taskd` |
| Still needed, by condition | `scheduler` quotas |
| Parameter row | The task's own `Param` declarations; writes return through `Session.set` |
| Drops, staleness | `eye`'s staleness accounting |

**If the console needs a number that is not in those objects, the fix is to add it to the
object.** A console-only number cannot be in the record, cannot be checked, and will
eventually be read off a screen into a paper.

**Approximation is in the name.** `rt_approx_ms`, never `rt_ms` — online RT is
approximate by decision (PI, 2026-09-19: *"an approximate rt online is fine enough"*),
with the real value recovered offline from sync ticks. Unknown is `None`, never `0`,
following `shortfall()`'s refusal to claim a day went well.

**The console never computes a welfare number.** Fluid shown is what `welfare` says was
*delivered*, never a sum of reward commands issued.

**Telemetry is lossy by design.** ZMQ PUB drops rather than blocks, because latest-wins
telemetry must never stall a frame. The consequence, stated loudly: **the console is a
view, never a source.** Schema-versioned with golden-file tests, which ADR-0003 already
requires. Trial-rate telemetry on one topic; the replica's display-rate stream, if V11
permits one, on a separate droppable topic.

---

## 10. Preflight semantics

S9 §10's open item 2 — what preflight does when a check is *unknown* rather than failed.

**Presence is a load-time refusal; preflight is about condition.** A task needing gaze
will not load on a deployment without gaze (S13 §2 made "absent" a first-class device
state precisely so it is refused at load time with a reason), and `check` already refuses
a chromatic task with no photometer calibration. So preflight never asks *is there a
tracker*, only *is it healthy* — which is a real three-state question.

**One rule, no exceptions** (PI, 2026-09-19):

- **fail** → blocks. A check that has actively failed stops the session.
- **unknown** → proceeds on an **explicit acknowledgement that is written into the session
  record**: which checks were unknown, and who accepted them.
- **pass** → proceeds.

The failure mode this is shaped against is not proceeding on an unknown. It is **a gate
that cries wolf and gets clicked through**, because a gate people route around protects
nothing. Refusing only on evidence of a problem, and recording acceptance where evidence
is merely absent, keeps a refusal meaningful.

Months later, when data looks odd, the record says *"this session started with the optics
residual unknown, acknowledged by jake"* rather than nothing at all. Same instinct as
`shortfall()` answering `None` and the `unattributed` actor: do not prevent, make it
impossible not to notice, and put it in the data rather than in somebody's memory.

**A dated dependency, stated so the next reader can grep it rather than believe it.**
An absent pump calibration (V10) is acknowledgeable like everything else, and that is
safe *only* because the real pump driver does not exist and may not be written until V10
is measured (`docs/CHECKPOINT.md`, "Open measurements"). An unmeasured millilitre
conversion therefore cannot reach an animal whatever preflight allows. **If anyone writes
that driver, this rule must be revisited before it ships** — at that point an
acknowledgeable unknown would mean a per-delivery ceiling enforced against a number
nobody measured, while appearing to work.

---

## 11. Open

| # | Item |
|---|---|
| 1 | Whether dichoptic trials need a two-panel replica (§2.1) |
| 2 | Whether the replica renders through the same `DisplayAdapter` as the subject screen, or a second lighter path — the same code is truer, a second one cannot cost the subject a frame |
| 3 | Task selection: from a directory, from `wl-mllib`, or pushed by wl.works with the session |
| 4 | Whether plots dock inside the console or float, given a second monitor is likely |
