# S13 — Cage-side touchscreen kiosk

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **New scope**, PI-requested 2026-08-31. Not v1.

A single-screen touchscreen deployment of wl-expcontroller running cage-side as a kiosk.

---

## 1. Why this changes the project rather than extending it

**It takes home-cage work off the deferred list**, where the README had it as a non-goal. That
list is working as intended: a deferred item leaves it when a real consumer appears, and only
then.

More usefully, it is the **second concrete consumer** P2 demands before an abstraction earns its
place. The hardware interfaces, the task model and the bounded config are now legitimately
general in a way the rig alone would never have justified — and generality that answers to two
real deployments is the opposite of framework creep.

---

## 2. What is absent

No stereoscope. No NI card. No neural plane. No SpikeGLX, no Intan.

> **"No sync box" was here and is withdrawn (PI, 2026-09-19).** It does not survive the
> requirement that timing be measurable: RT is recovered offline by joining a hardware
> timebase, so a deployment with no tick has nothing to recover from. The cage-side
> deployment gets a **reduced sync module** — smaller than the rig's 2U breakout, which
> exists to interface an NI card, an Intan and an eye tracker that the kiosk has none of.
> It also gives `wl-juicer`'s dose input and witness line the home its own spec designed
> them for (§3), instead of the host faking both in software on the welfare-critical path.
> `wl-touchtrain` owns the hardware; this section will be rewritten when that repository
> holds a design.

**So "absent" is a first-class device state** (S6 §6), beside hardware and simulated rather than
a stub for tests. A task requiring a device the deployment lacks is **refused at load time with a
reason**, not discovered when a trial tries to reward.

That constraint improves the rig code too: it forces every hardware dependency to be declared
rather than assumed, which is exactly what makes a rig running temporarily without its Intan a
recoverable situation rather than a crash.

---

## 3. What is present

- **One screen, no mirrors.** Monocular by construction; the display module's zero-disparity path
  (S4 §2), with the kiosk's own geometry and no vergence offset.
- **Touch as the primary response.** No hardware line exists for it even on the rig, so touch
  events reach any record only as event codes (S2 §5.1) — here, they are the only response
  modality.
- **Reward, through `wl-juicer`** (PI, 2026-09-13). Its spec wires both of its lines to the sync
  box — the dose input from `wl-sync` `J6`, the witness line back to `J5B`. **Since the kiosk
  now gets a reduced sync module (§2, 2026-09-19), those two lines land where their own spec
  put them** rather than being faked by the host in software on the welfare-critical path.
  What the reduced module must carry is `wl-touchtrain`'s to specify (§6 item 2).
- **An attached panel with a wired touch sensor** (PI, 2026-09-19), not a tablet. A touch
  arriving over a wireless link cannot be strobed promptly, and the offline join against a
  hardware tick is how RT is recovered — so the response path must not cross a network. A
  tablet is the *experimenter's* window instead, which ADR-0008 provides for free.
- **The same task model.** A task written for the rig runs here if its declared device
  requirements are met; one that needs gaze or stimulation does not, and says so at load.

---

## 4. Welfare: one mechanism, different numbers

Ruled 2026-08-31. The kiosk uses **the same bounded config** as the rig — ceilings the task
cannot exceed and the console cannot override — with kiosk-appropriate values.

Two consequences that matter more than the numbers:

- **The welfare-critical module stays single**, written once and reviewed once. The
  less-supervised deployment gets **no weaker path of its own**, which is the failure mode this
  choice forecloses.
- The precedence chain gains a layer: **deployment → rig → subject → task → session → live
  edits**, still under one ceiling.

### 4.0 A kiosk session has no duration bound, and says so

**Ruled 2026-09-19 (PI).** The one welfare duration limit is twelve hours out of the home cage
to back in it (S8 §5.2 item 4). A cage-side session has no out-of-cage event, because the
animal never left home — so the limit has nothing to measure, and the PI chose no time-based
limit here rather than a different number.

**That absence is declared, never inferred.** A rig session where somebody forgot to mark the
animal coming out of its cage looks exactly like a cage-side one to any code that answers
zero, and treating the two alike would run an unmarked rig session unbounded. So
`welfare.Deployment` is a required field with no default. `RIG_FIXED` and `RIG_CHAIRED` both
carry the clock and the ceiling and **refuse** a session missing either, and `CAGE_SIDE` is the
explicit, greppable statement that this deployment is cage-side and the animal is home.
(The three kinds date from 2026-09-20, when the PI made head-fixation a property of the
deployment rather than of being on a rig; the members were `OUT_OF_CAGE` and `ANIMAL_AT_HOME`
until then. S8 §5.2 item 4 has the table.) A cage-side
bounded config that also states an `out_of_cage` ceiling is refused, because the declaration
and the config disagreeing is the same limit-by-omission failure reached from the other side.

`welfare.out_of_cage_seconds` answers `None` for such a session — never `0.0` — and the
console renders that as *cage-side, the animal is home* rather than as a clock at zero.
`welfare.chair_seconds` answers `None` too, and `welfare.head_fixed` **refuses** a cage-side
session outright: an animal that never left home was never restrained, and a `0.00` restraint
figure would be a measurement nothing took.

**What does not change: the fluid floor.** A cage-side session is refused without one, exactly
as a rig session is (§4's shared daily figure, S8 §5.2b). Losing the duration bound does not
loosen the accounting.

**Kiosk fluid counts toward the same daily figure as rig work** (PI, 2026-08-31; that figure is
a **floor** rather than a budget — PI, 2026-09-06, see S8's head), so the two
deployments share a total neither can see directly. wl-works holds the
ledger and pushes the day's already-delivered figure in `prepare-session`; each deployment
reports `floor − already_delivered_today − earned_here` as what is still to supplement
(S8 §5.2b, as corrected 2026-09-06 — written here as `ceiling − already_delivered_today`
before that). Sequential use is the only real case, since an animal cannot be in the chair and
at the kiosk at once, so a start-time figure suffices.

> ~~**S8 §5.2's fail-closed rule applies here with more force, not less.** If the daily fluid
> total cannot be reconstructed after a restart, reward is refused until a human confirms — and
> cage-side, nobody is watching to notice that it should have been.~~
>
> **Reversed 2026-09-06 with S8 §5.2 item 3, and corrected here 2026-09-19.** That rule follows
> from a fluid *ceiling*, and there is none. Under a floor the argument runs the other way, and
> hardest cage-side: a deployment that cannot learn the day's prior total still pays the animal
> and reports the day as uncountable (`Welfare.shortfall()` answers `None`). Refusing reward
> where nobody is watching would be an unrewarded session rather than an unreportable one.

### 4.1 Supervision, and why the alert cannot come from the kiosk

Both mechanisms (PI, 2026-08-31): the kiosk's state is visible as readings, **and** a stop raises
an active alert that reaches a person.

**But the kiosk cannot notify anyone.** It is a lab host, and lab hosts cannot initiate
connections to wl.works. So the alert cannot originate where the fault is.

> **Citation corrected 2026-09-19.** This said "(S3 §1)", which is about what `wl-sync`
> owns and does not say it. The claim lives in the controller architecture design §1.1 —
> *"wl-works binds only to WireGuard; lab machines have no route in, and `wl-preproc`
> enforces 'never initiates a connection' with an AST guardrail"* — sourcing
> `wl-preproc`'s `pending-wl-works-amendments.md` §11.2, and is repeated in
> `docs/design/architecture.md`. The claim was right and the pointer was not, which is
> the kind of error that survives because the sentence reads as though it was checked.

**wl.works polls and wl.works alerts.** The kiosk publishes `state` as a reading like any other;
wl.works, which *can* reach outward, raises the notification when it polls a fault, a stop, or
a refusal. (This said "a fluid ceiling"; there is none — PI, 2026-09-06. What a cage-side
session can raise is a pump fault, a console refusal, or a day it could not count.) One
mechanism serves both answers, and the kiosk stays a pure responder.

**One residual, stated rather than solved:** a network-dependent alert cannot report a network
failure. If the kiosk is unreachable, wl.works sees silence — which is indistinguishable from a
kiosk nobody is using. A local indicator at the cage would close that gap and needs no network;
worth considering when the hardware is specified (§6 item 2).

---

## 5. Recording

**Open, and it is the main design question this spec does not answer.** A kiosk session has no
acquisition systems, so `wl-preproc`'s session directory does not obviously fit.

> **Partly overtaken 2026-09-19.** This said the kiosk has "no barcode, no sync box", and
> concluded that `SessionLayout`'s sync-box session id "will not exist". With a reduced sync
> module (§2) it may well exist — a sync module is what mints that id — and a barcode may be
> available too. **Whether the reduced module carries either is `wl-touchtrain`'s to specify
> and is not decided here**, so the three candidates below are still live rather than
> resolved. What has changed is that the first of them is no longer ruled out by hardware.

Three candidates:

1. **A lighter record of its own** — behavioural tables and event log, no session directory, no
   ingest. Simplest; leaves kiosk data outside the pipeline.
2. **A synthetic session id** minted by the kiosk. Fits the layout at the cost of a second
   authority on session identity — the exact thing S3 spent its length deleting.
3. **Ingested as a distinct record type**, with `expected_systems` empty. Needs `wl-preproc` to
   accept a session with no acquisition systems, which their `_known_and_include_syncbox`
   validator currently forbids.

Recommendation: **(1) for a first version**, revisited if kiosk data turns out to want the
pipeline's alignment and quality machinery — which it may not, since there is nothing to align
it to.

---

## 6. Open items

| # | Item | Owner |
|---|---|---|
| 1 | Recording model (§5) | PI + `wl-preproc` |
| 2 | Kiosk hardware: panel, touch sensor, reward mechanism (`wl-juicer`, §3), host | `wl-touchtrain`, registered 2026-09-13 |
| 3 | Whether the kiosk shares the stimulus vocabulary or a subset | S4 |
| 4 | ~~Supervision model~~ **Answered: both — readings on the dashboard, and an active alert.** See §4.1 for how, given the kiosk cannot initiate a connection | wl-works |
| 5 | ~~Whether kiosk fluid counts against the rig's daily budget~~ **Answered: yes, one daily figure — and it is a floor, not a budget** (PI, 2026-09-06). Remaining: wl.works holding the ledger | wl-works |
