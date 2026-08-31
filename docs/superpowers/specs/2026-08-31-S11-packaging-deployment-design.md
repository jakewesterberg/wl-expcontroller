# S11 — Packaging, deployment, and CI

- **Status:** proposed, for PI review
- **Date:** 2026-08-31

---

## 1. Already done

- **`wl.yaml`** authored and `wl-check`-clean; **registered in `wl-orchestrator`**. Deliberately
  declares no display or messaging dependency, because ADR-0002 and ADR-0003 are still Proposed
  and declaring them would assert a toolchain nothing has accepted.
- **`ni-daqmx` catalogued** even though `wl-sync`'s board chose the card, because the driver is
  an out-of-tree DKMS module and so constrains the machine's *distribution* — the fact
  `wlo stack` needs and cannot recover elsewhere.

**The remote does not exist yet.** Both the manifest and the registry entry say so in place
rather than implying a repository that would 404. Pushing it is a prerequisite for anything
resolving that field.

---

## 2. Deployment targets

| Selector | What | Stack |
|---|---|---|
| `rig/task` | Task PC | **Ubuntu 24.04 LTS**, dual-boot Windows (S0 §2) |
| kiosk | Cage-side | S13; class not yet named in `wl-stack`'s vocabulary |

Both need a **`wl-stack` playbook**, and the `rig/*` role vocabulary (S0 §1) needs `wl-stack` to
adopt it before the manifest's `runs_on` means anything. The task PC's deviation from Fedora is
recorded as a rig-class decision, not a drift.

---

## 3. CI and the simulator harness

The sim harness is not a test fixture; it is the **product's verification loop** (ADR-0006,
S9 §5). It runs in CI on every change:

1. Every interface has hardware, **absent**, and simulated implementations as peers (S6 §6).
2. Replayed OpenIrisDPI recordings, not only synthetic traces — S5's saccade detector is tested
   against real stall behaviour or it is not tested.
3. Synthetic behaviour agents driving thousands of trials per task.
4. **Golden-file round trip through `wl-preproc`'s own `decode_stream`** (S2 §6.2). We write no
   second decoder; a second implementation is a second definition free to drift.
5. The ten load-time checks (S1 §9) run as tests over every task in the library.

`wl-preproc`'s synthetic generator already emits SpikeGLX and RHS sessions with planted ground
truth and three deliberately different tick origins. **Our generator should feed that harness
rather than build a second one** (S3 §8).

---

## 4. Versions and pinning

- Python floor **3.11**, matching `wl-sync` and `wl-preproc`.
- Cross-repo dependencies are **commit-pinned with a stated reason**, following `wl-preproc`'s
  pin of `wl-sync` — a pin without a `why` is a fault the schema names.
- Task definitions carry a version; a change is a discontinuity, not an update (P16).
- Every measurement artifact records the full stack it was measured on: distro, kernel, driver,
  session type, panel, firmware, SpikeGLX and RHX versions (P4).

---

## 5. License

**ADR-0004 is Open.** The dependency inventory is maintained meanwhile, and no `LICENSE` file
exists. The lean is GPL-3, honest given a PsychoPy import, and common in this niche — but S13's
kiosk is a second deployment and a possible reuse story, which is exactly the "concrete reuse
scenario" ADR-0004 said would reopen the question. **Revisit at M10, with S13 as input.**

---

## 6. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Push the repository; the declared remote does not exist | anything resolving it |
| 2 | `wl-stack` adopting the `rig/*` role vocabulary | `runs_on` meaning anything |
| 3 | A machine class for the kiosk | S13 |
| 4 | ADR-0002 and ADR-0003 accepted, so dependencies can be declared | `wlo stack` building a real task PC |
