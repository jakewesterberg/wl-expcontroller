# S12 — Parity check and swap verification

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Deliberately last, and deliberately small.**

---

## 1. What this is not

Under ADR-0005 the MonkeyLogic swap is maintained at the **rig-contract and data layer only**.
There are no maintained MonkeyLogic task twins and no shared task language. So this is a
**verification exercise**, not a parallel development effort — and running it earlier would
invert P2 by building generality for a consumer that does not exist.

---

## 2. Parity as a completeness check, not a specification

The feature inventory in the parent spec §15 was **derived from the stated experimental
programme**, not copied from MonkeyLogic's manual. That ordering is the point: copying the manual
would have produced a hundred features and missed the three the science actually needs.

MonkeyLogic's documented feature list is then read **once, afterwards**, purely to ask *"is there
anything here we need and do not have?"* Anything it turns up is evaluated on its own merits
against the programme, not adopted because MonkeyLogic has it.

---

## 3. The swap verification, run once

Verify that a MonkeyLogic rig can be stood up on the same hardware and produce the same recorded
streams:

1. Boot the task PC's Windows partition; the same PCIe-6343 and the same MDR68 cabling.
2. Configure MonkeyLogic's event lines for **P0.8–P0.23** — non-zero-based, which `wl-sync`'s
   board spec flags as a thing to confirm rather than assume, and which is a config string for us
   and a real constraint for them.
3. Set `RewardPolarity = HIGH` to match the board's active-high `RWD_CMD`.
4. Run a simple fixation task; confirm the sync box, NI and Intan records are indistinguishable
   in form from ours.
5. Confirm `wl-preproc` ingests the result — noting that `CalibrationSource.ONLINE` would then
   come from a `.bhv2`, which is the reader that exists today.

**Then stop.** The result is a recorded verification, not a maintained capability.

---

## 4. What would make this matter

If v1 misses January badly enough that recording must start on something, this is the document
that says whether the swap is real. That is its only job, and it is worth one bench day to be
able to answer it with evidence rather than hope.

---

## 5. Open items

| # | Item |
|---|---|
| 1 | Whether anyone in the lab can still drive MonkeyLogic well enough to run the check |
| 2 | Whether the check needs a task at all, or a signal generator suffices |
