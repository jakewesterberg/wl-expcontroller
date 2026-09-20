# ADR-0009: wl-works runs an NTP server, and lab hosts synchronize to it

- Status: Accepted 2026-09-20
- Date: 2026-09-20
- Deciders: PI

## Context

Welfare marks are now wall-clock times rather than intervals — the out-of-cage departure
mark is a clock time an operator reads and types (PI, 2026-09-20; `welfare.left_cage`
does the mapping onto the session clock itself). And the daily fluid figure spans two
deployments, the rig and the cage-side kiosk, that cannot see each other's records. Both
need to agree on what "today" is and what "09:15" means, and nothing today guarantees
that they do: each host keeps whatever clock it booted with.

**What was verified, and when:**

- `docs/design/architecture.md` states, unqualified until this commit: wl-works binds
  only to WireGuard and lab machines have no route in, and `wl-preproc` enforces "never
  initiates a connection" with an AST guardrail. Re-checked against `wl-preproc` source
  2026-09-20 (`tests/test_cli_guardrails.py`): the guardrail is a static AST walk over
  **`wl_preproc`'s own package source**, asserting nothing in it opens an outbound
  socket — a property of that application's code, not a network-layer rule. NTP is
  client-initiated by the protocol itself, so a lab host that wants time from wl-works
  needs a route to it (UDP 123) that does not exist today.
- `ntp.kuleuven.be`, KU Leuven ICTS's central NTP service, **exists** — verified
  2026-09-20 directly against ICTS's own service page,
  `https://admin.kuleuven.be/icts/services/ntp`: it names `ntp.kuleuven.be`
  (134.58.255.1) as the synchronization source for users within KU Leuven, confirmed
  independently by DNS resolution the same day. Its reachability from the rig's
  specific network segment is **UNVERIFIED** and is a question for the PI or ICTS, not
  settled here.
- A second claim considered alongside it — that KU Leuven's Computer Science
  department separately runs `ntp.cs.kuleuven.be` — does **not** hold up under an
  attempt to verify it: queried against public DNS 2026-09-20, that hostname returns
  `NXDOMAIN`. General DNS resolution was confirmed working at the same time (`kuleuven.be`
  and `www.cs.kuleuven.be` both resolve), so this is not a broken resolver. A
  department-internal service could still be resolvable only from inside KU Leuven's
  network (split-horizon DNS would produce exactly this result from outside it), so this
  does not prove the server doesn't exist — but its existence is **UNVERIFIED**, unlike
  `ntp.kuleuven.be`'s, and it is recorded here so a later session does not repeat it as
  settled fact.
- The sync box already carries an NTP-stamped start in one case: `wl-preproc`'s frozen
  `SessionManifest` contract (verified 2026-09-20 against
  `wl_preproc/contracts/manifest.py`) defines `StartedAtSource.SYNCBOX_NTP` — used as the
  session *label* source specifically when there is no task PC (anesthetized mapping,
  spontaneous-activity sessions); that module's own docstring is explicit that "the
  timebase is always the sync box" regardless of which label source is used. Checked the
  same day: `wl-touchtrain`, the cage-side kiosk repository, specifies no sync box and no
  clock source at all yet (no `clock`, `NTP` or `sync` reference anywhere in its docs).

## Decision

**wl-works runs an NTP server. Lab hosts synchronize their wall clocks to it.** Today
that is the task PC; the cage-side kiosk joins once `wl-touchtrain` specifies a
platform for it. This is ordinary client-initiated NTP: the lab host asks, wl-works
answers.

**This serves bookkeeping time only, never experimental time.** Which day it is, which
operator acted, when an animal was marked out of or back into its cage. The timing
record is unaffected and remains the sync box's hardware ticks and the strobed event
words — S3's finding that "our log is not the timing record" still holds, in full, for
the same reason it held before: two other systems already carry the timing of anything
scientifically meaningful. Nobody should read an NTP-disciplined wall clock on a task PC
or a kiosk as good enough for aligning neural data, now or later.

**Verify rather than assume.** Preflight should compare the host clock against the
reference and refuse or warn beyond a threshold, in the same spirit as every other check
in this system. That is recorded here as a preflight item **to build**; it is not built
by this ADR.

## Alternatives considered

**`ntp.kuleuven.be` (KU Leuven ICTS's central service).** Loses not on its merits — it
exists, is free, and is already the institution's own answer to this exact problem — but
on what is not yet known: whether it is reachable from the rig's network segment is
unverified, and that is a question for the PI or for ICTS to settle, not something this
session can determine. Depending on it now would mean waiting on that answer before the
welfare-mark and fluid-accounting need is served. wl-works does not have that problem: it
is already the lab's own controlled infrastructure, and the rig already depends on it for
other pull-based integration (`docs/pending-wl-works-amendments.md`). If reachability is
later confirmed, revisiting which host serves this role is cheap — the lab hosts only
need one NTP source configured, not this one specifically.

**The sync box.** It already expects to carry an NTP-stamped start, but only as a
session-label source for sessions with no task PC — it does not, by itself, give either
deployment this decision is actually about (the rig's own wall clock, or the kiosk's) a
synchronized time. The cage-side kiosk has no sync box at all today, and `wl-touchtrain`
has not specified one. A mechanism only one of the two deployments has cannot be what
makes them agree with each other.

## Consequences

**A route that does not exist today has to exist, and it is narrower than it sounds.**
`docs/design/architecture.md`'s topology paragraph is amended in this commit: lab
machines still have no route in for the application layer, and `wl-preproc`'s AST
guardrail — a check over application source — is completely untouched by this decision.
What changes is one routing exception, one port, one direction: a lab host may reach
wl-works on UDP 123 to ask the time. Do not read this as the guardrail being relaxed; it
refuses exactly what it always refused, and nothing in `wl_preproc` gains a socket it
did not have.

**A wl-works outage stops clocks being corrected, and that is mild.** An NTP client that
cannot reach its server keeps its own clock and drifts at whatever rate its local
oscillator drifts (ordinary ppm-scale rates, not a number this repository has measured
or needs to). It does not stop, error, or invalidate anything already recorded. A
multi-day wl-works outage does not stop a rig session and does not invalidate a day's
fluid accounting. Nobody should treat wl-works as a session-blocking dependency because
of this decision — it was not one before, and running an NTP service does not make it
one now.

**Scope stays bounded on purpose.** This does not reopen wl-works' welfare-action
exclusion (ADR-0008): NTP is a clock source, not an action, and is never published
through the lab-host protocol. It does not change what the timing record is (S3).

**Follow-ups, not done here:**

- `docs/pending-wl-works-amendments.md` gains a new ask — wl-works runs the service and
  opens the routing exception it needs — drafted for that repository's owner to accept,
  amend or refuse, the same as every other ask recorded there.
- A preflight clock-skew check (compare the host clock to the NTP reference; refuse or
  warn beyond a threshold) is work to build, not built here.
- The session-management design (S8) is where the wall-clock welfare-mark material
  lives, and it is being revised in a concurrent session as of this ADR. Cross-reference
  for whoever next edits it: any discussion of what clock a wall-clock mark (such as the
  out-of-cage departure time) is read against should cite this ADR for where that clock
  comes from and what it does not do.
