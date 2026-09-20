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
| **Animal** | Fluid against the day's **floor** (PI, 2026-09-06 — not a ceiling), reconciled (P17) not tallied; **time out of the cage** against its ceiling, which is the one limit that ends a session; chair time beside it, recorded and bounding nothing (PI, 2026-09-19) |
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

**"The same machine" is now enforced at the bind, not just asserted here.** Added
2026-09-19. `ZmqLink` binds loopback only; a wildcard, a LAN address, or anything it
cannot classify is refused, and `wlx run --link-allow-remote` (`allow_remote=True`) is how
an operator says a reachable bind was meant. Until P4d-3 builds §6's `Actor`, a command's
`by` is whatever the sender typed, so a reachable REP port means any host on the lab
network can move a reward volume or stop a session under an invented name — the paragraph
above is the *whole* of the authentication, and a bind that leaves the machine voids it.
`ZmqConsole` is not restricted the same way: it connects, and where a console looks is its
own operator's decision.

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

**"Staged" means one thing: validated, and not yet applied** (PI, 2026-09-19). A change of
either kind — an ordinary task parameter or a welfare-bounded value such as
`reward_correct` — is refused or accepted at the moment it is offered, and applied at the
next trial boundary by `taskd.Session._apply_staged`, with the `PARAM_CHANGED` strobe and
the `parameter_changes.jsonl` row written in that same pass. The trial running when a
change is staged uses the old value, whichever kind it is. §8.1 recorded the period when
that was true of only one of the two kinds, and why it stopped being.

### 8.1 A welfare-bounded change used to apply immediately, and no longer does

**Decided 2026-09-19 (PI): a welfare-bounded change defers, like an ordinary parameter.**
This section is kept because the reason is worth grepping, not because anything here is
still live.

`Session.set` called `bounds.set` synchronously as the command was drained, and
`welfare.Rig.deliver` reads `bounds.value(ref)` at the moment it opens the valve — so the
trial that ran later in that same pass was already at the new volume, while `link.Staged`
published it as `staged` and the `PARAM_CHANGED` strobe and `parameter_changes.jsonl` row
landed a pass later still. Measured on `p4d1-console-link` with a six-trial session and one
queued `SetParameter(reward_correct, 0.30)` against a starting 0.15: trial 0 commanded
0.30 mL, and its record row was written between trial 0 and trial 1.

The ceiling held on every path and nothing landed mid-trial, so this was never
over-delivery. It was **fluid attribution off by one trial**: anyone reconciling commanded
fluid against `parameter_changes.jsonl` offline assigned one trial's delivery to the wrong
value.

**What replaced it.** `bounds.Bounds.validate` now answers "would this be refused" without
moving anything, `Session.set` validates at offer time and stages, and
`Session._apply_staged` performs the assignment — so the value, the strobe and the record
row all move in the same pass, immediately before the first trial they describe. The cost
the PI weighed and accepted: an operator who has just lowered a reward volume watches one
more trial go out at the old one.

---

## 9. The telemetry contract

**One rule: every number on the console comes from the object the record is written from,
never computed beside it.** This is where a number nobody measured would get in, and the
defence is structural rather than careful.

| Pane | Source |
|---|---|
| Fluid delivered / floor / supplement | `welfare.session_total`, `total_today`, `shortfall()`, `bounds.minima`. **These two are welfare-load-bearing and may not be dropped or folded away** — see below |
| Time out of cage | `welfare.out_of_cage_seconds` — frame-derived, so it matches the ceiling that ends the session. `None`, rendered *cage-side, the animal is home*, for a deployment with no duration bound (S13 §4.0) |
| Chair time | `welfare.chair_seconds` — shown beside it, and **not** what ends the session since 2026-09-19. Showing only this one meant an operator would watch a session stop on a clock the console never displayed. **`None` for `RIG_CHAIRED` and `CAGE_SIDE`** (PI, 2026-09-20), rendered as *n/a* with the reason — never `0:00`, which on a chaired animal would report restraint nothing measured |
| Deployment | `Telemetry.deployment` — which of the three kinds this session declared. On the wire rather than derived, because two kinds share one `None` for chair time and this pane names fields rather than inferring them |
| Time left out of the cage | `welfare.approaching_limit` as a `WARNING:` line beside the stop reason, once the ceiling is within `warn_within` (PI, 2026-09-20). Silent otherwise, and silent again past the limit, where the stop reason speaks |
| Trials, outcomes, aborts by reason | `simulate.Tally`, already shared with `taskd` |
| Still needed, by condition | `scheduler` quotas |
| Parameter row | The task's own `Param` declarations; writes return through `Session.set` |
| Drops, staleness | `eye`'s staleness accounting |

**If the console needs a number that is not in those objects, the fix is to add it to the
object.** A console-only number cannot be in the record, cannot be checked, and will
eventually be read off a screen into a paper.

**And two of those numbers may not be removed, because a welfare ruling rests on them.**
A reward volume of **zero** is allowed — pausing reward without ending a session — and the
PI allowed it on 2026-09-20 **because it is visible** (S8 §5.2c). `fluid session` going
`0.00 mL` is how an operator sees that a correctly-working animal is being paid nothing, and
`supplement` keeps reporting the whole floor as owed so it is topped up afterwards. The
consequence he weighed and accepted is that, while it holds, the animal earns nothing. **So
a console change that stopped showing either — a simplified pane, a folded summary, a
reconciliation that no longer published `fluid_session_ml` — would turn a permitted operation
into a silent one.** That is a welfare regression arrived at by editing a display, which is
the reason this sits in the console spec rather than only in S8.

**Approximation is in the name.** `rt_approx_ms`, never `rt_ms` — online RT is
approximate by decision (PI, 2026-09-19: *"an approximate rt online is fine enough"*),
with the real value recovered offline from sync ticks. Unknown is `None`, never `0`,
following `shortfall()`'s refusal to claim a day went well.

**The console never computes a welfare number.** Fluid shown is what `welfare` says was
*delivered*, never a sum of reward commands issued.

**Telemetry is lossy by design.** ZMQ PUB drops rather than blocks, because latest-wins
telemetry must never stall a frame. The consequence, stated loudly: **the console is a
view, never a source.**

**And a refusal of a welfare-bounded name therefore goes into the session record as well**
(PI, 2026-09-19). A refusal used to reach `Refused` and nothing else, so an attempt to set
a dose above its limit left no durable trace at all unless a console happened to be
attached and happened to still hold the row — which this same section caps. "Somebody
tried to give this animal four times its volume" is asked months later and is answered
from the record or not at all, so `taskd.Session._command` writes a row into
`refusals.jsonl` for any name carrying a `bounds.Ceiling`. An ordinary parameter typo
stays telemetry-only: a slip at a keyboard is not a welfare event, and recording every one
of them would bury the rows that are.

**A pump fault publishes one frame before it propagates** (PI, 2026-09-19). `welfare.Rig`
deliberately does not swallow a pump that will not answer, and that exception used to
leave `taskd.Session.run` with no telemetry at all — a console watching a rig break,
unattended and cage-side, saw the stream simply stop. The loop boundary now sets
`stopped_because` to name the fault, publishes once, and re-raises unchanged. The refusal
is the behaviour that matters; the frame only means a stranger can read what happened off
the screen, which is this spec's own rule for an abort reason.

Schema-versioned with golden-file tests, which ADR-0003 already requires. **`SCHEMA` is 4
as of 2026-09-19**, and both bumps that day are the same case — a field that still decodes
and no longer means what it did. At 3, `Staged.bounded` stopped meaning "already live" and
became "checked against a welfare ceiling", so a console built against 2 would render a
lowered reward volume as already in effect. At 5, `chair_seconds` became `float | None` and
`deployment`/`duration_warning` arrived — a console built against 4 renders a `None` chair
clock, and one that coerced would tell an operator a restrained animal had been restrained for
no time at all. At 4, `chair_seconds` stopped being the number
that ends the session: `out_of_cage_seconds` is what the ceiling is read against, and a
console built against 3 would show chair time as *the* clock and then watch a session stop
on a limit it never displayed. Trial-rate telemetry on one topic; the replica's
display-rate stream, if V11 permits one, on a separate droppable topic.

**A frame is bounded, and the one list that was not is the refusal feed.** Added
2026-09-19, schema 2. Every other field in `Telemetry` is fixed-width or bounded by the
task (`outcomes` by the outcome enum, `owed` by the block's conditions, `staged` by what
an operator queued in one ITI). `refusals` was cumulative and uncapped, and the party
driving its growth is not the operator: `ZmqLink.drain` records one refusal per wire
packet it cannot decode, so a console built against a bumped `SCHEMA` — the case this
very section's versioning makes likely — adds one per packet, forever, with `Telemetry.of`
re-encoding the whole accumulation at every boundary. It is capped at
`link.REFUSAL_HISTORY` (50), newest kept, with `refusals_dropped` carrying the count of
what fell off so that a cap can never be read as a quiet session. `wlx console` prints
that count above the rows.

**`taskd.Session.refusals` is capped the same way** (2026-09-19). It is the third list fed
by the same peer — one entry per `SetParameter` the session refuses, as fast as a peer can
send them — and was left unbounded when the other two were capped. Two bounded lists
beside one unbounded one is not a policy. Its discards join `ZmqLink.refused_dropped` in
`Telemetry.refusals_dropped`, so the printed count is of everything missing rather than of
one source's share.

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
