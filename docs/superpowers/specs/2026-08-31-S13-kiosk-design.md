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

No stereoscope. No NI card. No sync box. No neural plane. No SpikeGLX, no Intan.

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
- **Reward**, on whatever local mechanism the cage uses.
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

**S8 §5.2's fail-closed rule applies here with more force, not less.** If the daily fluid total
cannot be reconstructed after a restart, reward is refused until a human confirms — and
cage-side, nobody is watching to notice that it should have been.

---

## 5. Recording

**Open, and it is the main design question this spec does not answer.** A kiosk session has no
barcode, no sync box, and no acquisition systems, so `wl-preproc`'s session directory does not
obviously fit: `SessionLayout` is keyed on a sync box session id that will not exist.

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
| 2 | Kiosk hardware: panel, touch sensor, reward mechanism, host | S0-equivalent |
| 3 | Whether the kiosk shares the stimulus vocabulary or a subset | S4 |
| 4 | Supervision model — is a person notified when it stops? | PI, welfare |
| 5 | Whether kiosk fluid counts against the same daily budget as rig work | PI, protocol |
