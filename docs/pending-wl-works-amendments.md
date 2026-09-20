# Amendments to wl-works

**Two are open, both opened 2026-08-31** while designing this controller
([`superpowers/specs/2026-08-31-controller-architecture-design.md`](superpowers/specs/2026-08-31-controller-architecture-design.md)
§12.3). Neither is applied here, and neither is wl-works' to discover: that repository is
owned by another worker, including its remote, so these are written where wl-preproc
writes its own — in the requesting repository, for the other side to accept, amend or
refuse.

**Both build on a document that is itself proposed, not agreed.**
`wl-preproc/docs/ops/lab-host-protocol.md` says so in its own opening line: it is written
by wl-preproc, describes the host half, and is *"proposed to wl.works rather than written
into that repository."* If wl-works rejects or reshapes that protocol, both amendments
below move with it, and that is the correct dependency — a second protocol invented here
would be worse than either outcome.

---

# OPEN — wl-works gains a second lab host, and it speaks the protocol it already has

## The ask

Treat the **task PC** as a lab host of the same kind as the preprocessing server: same
transport, same bearer token, same `GET /health` and `POST /jobs`, same status codes, same
three timing numbers. Different *action vocabulary*, identical wire contract.

Nothing about the protocol changes. What changes on the wl-works side is that
`lab-host-protocol.md`'s client is pointed at more than one host, and that the host list
becomes configuration rather than a constant.

## Why this and not a new protocol

Because wl-works' **18b contract tests already run against a fake wl-preproc**, and every
one of those tests is about the wire contract rather than about preprocessing. A second
host that answers the same shapes inherits them. A second protocol would need its own
client, its own tests, and its own maintenance, in exchange for nothing the first one
cannot express.

It also settles a question this controller would otherwise have to answer badly. The rig
**cannot push to the ELN** — `lab-host-protocol.md` §11.2 states the topology, *"the app
binds only to the WireGuard interface and we are on the lab LAN with no route in"*, and
wl-preproc enforces the complement with an AST walk over its whole package asserting it
never opens an outbound connection. So autopopulating the ELN from a rig is a pull, or it
is nothing.

## What the rig would answer

**`GET /health` — live session state as readings, not as a new endpoint.**

This follows `lab-host-protocol.md`'s own stated rule verbatim. Its "What this protocol
does not carry" section declines a job-status endpoint and says that when progress becomes
observable *"it will be as a **reading**, because readings are the surface this host already
publishes and wl.works already polls — not as a new endpoint."* Live session state is
exactly that shape: current, per-host, and cheap.

Proposed readings, in the existing readings format:

| Reading | Example | Why a reading and not a record |
|---|---|---|
| `session` | `wl-2027-01-14-A-001`, or absent | The session identity `wl-sync` minted, if one is running |
| `subject` | `A` | Who is working right now |
| `task` | `detection-v3`, with its version | What is running right now |
| `state` | `running` / `paused` / `idle` / `fault` | Whether a person needs to walk to the rig |
| `trials` | `340 attempted / 318 completed` | Progress, current by nature |
| `fluid` | `142 mL of a 250 mL ceiling` | Welfare-relevant, and stale-by-a-minute is fine |
| `preflight` | `pass`, with its timestamp | Whether the last start-up check was clean |

At the protocol's proposed 60 s poll cadence this gives wl-works a live rig dashboard for
the cost of a field list, and it needs no new endpoint, no callback and no push.

**The finished session summary is *not* asked for over this protocol.**

It goes where session data already goes: a file in the session directory, ingested by
wl-preproc alongside everything else, reaching the ELN through the path that already
exists. `lab-host-protocol.md` declines result upload for the same reason — *"wl.works
pulls; this host never pushes"* — and a session summary is a result. One integration, not
two, and no second copy of the session record free to drift from the ingested one.

The trade wl-works should know it is making: the ELN entry appears **after ingest, not at
session end**. If that latency turns out to matter, the fix is to make ingest prompt, not
to add an endpoint here.

**`POST /jobs` — a small action vocabulary, and one rule about what may go in it.**

Proposed initial actions: `prepare-session` (§ the second amendment below) and
`export-session` (re-emit a session's outputs if a transfer was lost). Both are idempotent
under the existing key, both return the existing activation-key shape, and both use `422`
for "this host cannot do that" exactly as documented.

> **No welfare-affecting action is ever published here.** `lab-host-protocol.md`'s most
> prominent line is that publishing an action makes it available to every member of the
> lab and that there is no permission model on the app side. On a preprocessing server the
> worst case is wasted compute. On a rig it is fluid, stimulation, or a session started on
> an animal nobody is standing next to. **Reward delivery, stimulation, session start and
> parameter changes are not actions and will not be exposed through this protocol** — they
> require a person at the console. This is a constraint this repository accepts, stated
> here so wl-works never has to wonder whether a rig action might be one of those.

---

# OPEN — the metadata bundle wl-works already assembles should reach the rig too

## The finding

wl-works already builds a metadata bundle for wl-preproc's job requests: subject, probe
serials, `insertion_number`, and — since wl-preproc's 2026-08-22 amendment, built and
frozen on their side at `contracts/protocol.py` — `trajectory_id` per insertion:

```json
{ "serial": "NP-1234", "insertion_number": 1, "trajectory_id": "T-0042" }
```

**The rig wants the same bundle, at the other end of the session.** Today, everything in it
would be typed into the rig console by hand at session start and then typed into the ELN
again afterward, with two chances to disagree and nothing to catch it. The bundle already
exists, is already authored in the ELN, and is already serialized for a lab host.

## The ask

A `prepare-session` action carrying the existing `MetadataBundle`, plus the session intent:

| Field | Source | Rig use |
|---|---|---|
| `subject` | ELN | Selects the subject's bounded config — per-delivery reward volume, the daily fluid **floor**, session duration, stim limits |
| `probes[]` with `serial`, `insertion_number`, `trajectory_id` | ELN, existing shape | Recorded in the session config snapshot so electrode -> trajectory -> coregistration closes from the behavioural record too |
| `planned_task` | ELN | Preselects the task; the operator confirms rather than chooses |
| `session_intent` | ELN | Free text into the session record and the ELN entry |

**No new fields are requested.** Three of the four already exist in the bundle wl-works
sends wl-preproc; `planned_task` and `session_intent` are the only additions, and both are
optional — a rig that receives neither behaves exactly as it does today.

## Why it reaches wl-works

Because the bundle is authored there and the rig has no route to fetch it (§11.2, above).
Everything the rig needs from the ELN must arrive with a request, which is the same
sentence that shaped wl-preproc's half of this problem.

## What is deliberately not asked for

Declined rather than skipped, so a later revision overturns a decision instead of
discovering an option:

- **No session-start action.** `prepare-session` stages metadata and returns; it does not
  begin a session. See the welfare note above.
- **No TLS, no rate limiting, no permission model, no `Retry-After`.** Identical to
  wl-preproc's declines and for identical reasons; a rig should not be the host that
  invents a second answer.
- **No schema published from this repository yet.** The rig's `session-summary` is declared
  `planned` in `wl.yaml` and no JSON Schema is exported, because the shape should not be
  frozen before wl-works has said whether it wants this at all. When it is frozen it will
  be exported and CI-diffed, the way wl-preproc's two contracts are.

## One addition to the session planner

**Every session needs a planned calibration block.** `wl-preproc` authors block rows from
wl.works' session planner and quarantines on absence, so a calibration block run at the rig
without a matching plan degrades the session's timing tier. And a *dedicated* calibration block
is not optional in the way it might look: `wl-preproc`'s own docstring says it "reliably
supplies six well-spread targets," which is what decides whether a session reaches the
second-order calibration rung at all — an in-task epoch cannot guarantee the spread.

So the planner should emit a calibration block at the head of every session, with
`TaskTypeCode.CALIBRATION`. The in-task `CALIBRATION_START`/`CALIBRATION_END` epochs that follow
through the day need no planning and create no blocks.

## An OAuth2 client per control box (new, 2026-09-19)

ADR-0008 makes the experimenter console a web application served by each control box, and
S9a §6 makes the box an **OAuth2 client of wl.works** so that an action can be attributed
to a real account and revoked by deactivating it.

**This asks for configuration, not development.** Read from source 2026-09-19:
`src/lib/auth.ts` registers better-auth's `mcp()` plugin, which in 1.7.1 *is* the OAuth
provider — its own comment: *"Because it is the OAuth provider, it cannot be combined with
a separate oauthProvider. So the `/oauth2/*` surface Zulip reads and the MCP agent surface
are served by the same plugin."* Zulip is already a live consumer, PKCE is a per-client
column defaulting true, and revocation is proven end to end: an admin deactivating a
member cut their already-open Zulip session as a direct result.

So the ask is a client registration per control box — or one for the fleet, if that is
preferred there; we have no opinion, and the choice is yours because it is your
credential lifecycle.

> **This does not make wl.works load-bearing for a session.** The box's own credential is
> the floor and never depends on the network: if wl.works is unreachable, the console is
> still reachable directly on the LAN and actions are recorded as `unattributed` rather
> than refused. A session with an animal in the chair must not stop because an intranet is
> down. Identity is an attribution mechanism here, never an authorisation one.

> **And the welfare exclusion above is unchanged and unaffected.** Reward, stimulation,
> session start and parameter changes are still not published as lab-host-protocol
> actions, for exactly the reason Plan 10 §4.1 states in its own first line. Attribution
> arriving *from* wl.works does not make wl.works an actor; the box authorises, and the
> box records who asked.

## wl-works runs an NTP server, and lab hosts synchronize to it (new, 2026-09-20)

**The ask: run an NTP server on wl-works, reachable from the lab network on UDP 123, and
let a lab host initiate that one connection.** `ADR-0009` (this repository, 2026-09-20)
is the PI's decision behind it — welfare marks are now clock times (the out-of-cage
departure mark, among them) rather than intervals, and the daily fluid figure spans two
deployments, the rig and the cage-side kiosk, that cannot otherwise agree what "today" or
"09:15" means. Nothing currently guarantees they do; each host just keeps whatever clock
it booted with.

**Why this needs a routing change, and why it is narrower than it sounds.** §11.2's
topology — wl-works binds only to WireGuard, lab machines have no route in — is stated in
`docs/design/architecture.md` as an unqualified rule until this commit. NTP is
client-initiated: the lab host asks, the server answers. So a lab host reaching wl-works
for time needs a route to it that does not exist today, on UDP 123 only.

**This is not the AST guardrail changing.** `wl-preproc`'s "never initiates a connection"
check (`tests/test_cli_guardrails.py`, read from source 2026-09-20) is a static walk over
*application source*, asserting nothing in that package opens an outbound socket. A
system time daemon is a different layer — it is not application code the guardrail walks,
and this ask does not touch it. What changes is a routing/firewall rule: one UDP port,
one direction, one purpose.

**What this repository accepts, so wl-works does not have to guess.** An NTP client that
cannot reach its server keeps its own clock and drifts at ordinary rates; a multi-day
wl-works outage does not stop a rig session and does not invalidate a day's fluid
accounting. wl-works is not becoming load-bearing for a session by running this service,
on the same principle already established above for the console and its OAuth2 client:
the rig's own clock is the floor, and this only disciplines it. And this is bookkeeping
time, never the timing record — it sets which day it is and what a wall-clock mark reads,
never the alignment of neural data, which stays the sync box's hardware ticks and the
strobed event words. The welfare-action exclusion is unaffected: NTP is a clock source,
not an action, and is never published through the lab-host protocol.

**What we would still like verified, but are not blocked on.** `ntp.kuleuven.be`, KU
Leuven ICTS's own central NTP service, exists — verified 2026-09-20 against
`https://admin.kuleuven.be/icts/services/ntp` — but its reachability from the rig's
network segment is unverified. If wl-works' operator or ICTS can settle that, it may be
worth revisiting later which host the lab hosts point at; the lab hosts only need one
configured source, not this one specifically.

---

## What wl-works must decide

1. Whether the client's host list becomes configuration.
2. Whether `prepare-session` and `export-session` are acceptable as published actions given
   the flat permission model, with the welfare exclusion above as a standing constraint.
3. Whether a control box may register as an OAuth2 client of wl.works for operator
   attribution (above), and whether that is one client per box or one for the fleet.
4. Whether `planned_task` and `session_intent` are worth adding to a bundle that is already
   load-bearing on their side — their Plan 18b tests run against a fake, so the payload
   shape matters there before either machine exists.
5. Whether wl-works can run an NTP server reachable from the lab network on UDP 123, and
   open the one-port routing exception that requires (new, 2026-09-20 — see above).

Nothing here is blocked on an answer: the controller's v1 works with no ELN integration at
all, writing everything to the session directory as it would anyway. This buys the ELN
entry, not the recording.
