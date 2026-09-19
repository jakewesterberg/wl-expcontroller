# ADR-0008: The experimenter console is a web application served by each control box

- Status: Accepted 2026-09-19
- Date: 2026-09-19
- Deciders: PI
- Supersedes: S9a §1's toolkit decision (PI, 2026-08-31) and S9 §8

## Context

S9a §1 settled the console as **a desktop application: PySide6 with PyQtGraph** (PI,
2026-08-31), and S9 §8 gave the reason: *"a web UI would put a server on the rig for no
gain, since wl.works already covers anything a browser should show."* Three things have
happened since, and each weakens a different part of that argument.

**1. The kiosk became real, and it cannot run Qt.** S13's cage-side deployment is now
`wl-touchtrain`, registered in `wl-orchestrator` and scaffolded 2026-09-13, with an iPad
as the subject's display (PI, 2026-09-19). S9 §1 already listed *"the kiosk running a
console at all"* as one of four requirements depending on the `taskd`/console process
split — but a Qt console cannot be the answer on an iPad. Keeping S9a §1 means **two
operator surfaces**, and S9's opening requirement is that every operator-facing string is
read by someone who has never read a spec. Two surfaces is two sets of bugs for that
person to learn.

**2. "A server on the rig" has already been decided, twice, elsewhere.** P4c puts
`labhost` on the task PC by design (architecture.md: *"the pull-only endpoint wl-works
polls"*), and `wl-works`' Plan 10 responder contract expects an HTTP responder on every
lab machine. The server arrives whether or not it serves a UI, so S9 §8's objection no
longer distinguishes the options. What remains of it is the real constraint, which is
S9 §1's: **the hot loop never serves a request.** A console process serving HTTP beside
`taskd` satisfies that exactly as a Qt process attaching over ZMQ does.

**3. `wl-works` already specifies the device directory.** Read from source 2026-09-19:
Plan 10's design opens *"It is not a dashboard. It is a control plane for lab machines,
with a status board as its read half"*, and specifies `/infrastructure`, a responder
contract, health readings and triggerable actions. The tab listing every control device
is that page; it does not need inventing.

**What we verified about authority, and it decides the shape.** `wl-works` Plan 10 §4.1
is the first line of its protocol document:

> **Publishing an action makes it available to every member of the lab.** There is no
> permission model on the app side. If an action should not be triggerable by anyone who
> can log in, do not publish it.

§6.2 justifies that deliberately — *"the host is the real boundary anyway — an action the
app refuses to show is still an HTTP endpoint on the LAN — so putting a second, weaker
boundary in the app buys the illusion of control rather than control."* On a
preprocessing server the worst case is wasted compute. On a rig it is fluid, stimulation,
or a session started on an animal nobody is standing next to.

**Network direction, verified:** lab hosts never initiate. wl-works binds only to
WireGuard, lab machines have no route in, and integration is pull-based
(architecture.md, sourcing `wl-preproc`'s pending amendments §11.2). wl-works reaching
into a control box runs with the grain; a box dialling out does not.

## Decision

**The experimenter console is a web application, served by each control box, and the box
is the authority.**

1. **Served by the box, in a process beside `taskd`, never inside it.** S9 §1's process
   split is unchanged and remains a hard rule; the console process attaches to `taskd`
   over the ADR-0003 link exactly as the Qt console would have.
2. **`wl-works` provides discovery and readings, and never authority.** It lists control
   devices and links to them. **No welfare-affecting action — reward, stimulation,
   session start, parameter change — is published as a lab-host-protocol action**, which
   is the standing constraint architecture.md already records and Plan 10 §6.2 is the
   reason for.
3. **Authentication, the single-writer lock and the audit log live on the box.** S9a §1
   already has several consoles watching and one holding the write lock; that lock is
   enforced by `taskd`, not by a UI. This is Plan 10 §6.2's own logic taken seriously: if
   the host is the boundary, it has to be a real one.
4. **LAN-only** (PI, 2026-09-19: *"off-site is not necessary. at least now it isn't"*).
   The browser reaches the box directly; nothing bridges. A `wl-works` outage therefore
   cannot cost an operator the console mid-session — which matters because S13 §4.1
   already carries "wl-works sees silence" as an unsolved residual.
5. **One surface for both deployments.** The rig and the kiosk run the same console.

## Alternatives considered

- **Keep PySide6 (S9a §1).** Loses because the kiosk cannot run it, and the cost is a
  second operator surface rather than a missing feature.
- **Serve the console from `wl-works`.** Loses on two counts: it puts the component whose
  permission model is deliberately flat into the live control path for reward and session
  start, and it makes `wl-works` availability a session dependency.
- **Proxy the box's console through `wl-works` for off-site use.** Not refused on its
  merits — deferred, because off-site control is not wanted now. Nothing here forecloses
  it: a box that owns its origin and its own auth is unchanged by a route placed in front
  of it later.
- **Remote desktop onto the task PC.** Already refused by S9 §7 and pitfall P4: capture
  stacks hook the graphics pipeline on the machine whose whole job is frame-accurate
  presentation.

## Consequences

**Open, and gated on a measurement rather than an opinion.** S9a §2's experimenter
replica — the animal's screen with gaze, windows and disparity drawn on top, at display
rate — is the one thing PyQtGraph was chosen for. Trial-rate plots are not in question.
**Protocol V11**: stream synthetic gaze and stimulus state at 120 Hz across the lab LAN
to a browser and measure end-to-end latency and dropped frames; result under
`docs/measurements/`. Until it exists **this ADR makes no claim that a browser can carry
the replica**, and the fallback if it cannot is a native path for that one pane, not a
second whole console. The kiosk is unaffected either way: one screen, no mirrors, and the
animal's display is the thing itself rather than a replica of it.

**New dependencies**, each needing an ADR-0004 inventory entry with its licence verified
against the primary source before it is added. The Qt stack (PySide6, PyQtGraph) is **not**
added.

**Amended in the same commit:** S9a §1, S9 §8, and architecture.md's `console` row.

**Not decided here:** whether the kiosk's iPad is a thin client for a Linux host or runs
the task itself. It is recorded as the next decision in `docs/next-session.md`, with the
argument that S13 §4's "the welfare-critical module stays single" points hard at the
thin client.
