# S0 — Rig topology, hosts, and hardware

- **Status:** proposed, for PI review
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md`; first row of
  `2026-08-31-spec-map.md`

This spec is deliberately short and exists to unblock purchasing. It decides where
software runs, what the task PC is, and how the display geometry is computed — and it
names the one claim the whole design rests on that nobody has verified.

**Lead time is the governing fact.** NI cards are 12–13 weeks out and `wl-sync`'s breakout
spec §10.3 already says to order now, independent of that board's own pace. The lab opens
January 2027.

---

## 1. Host classes and roles

`wl-manifest` validates the class and leaves the role free
(`wl_manifest/hosts.py`: classes are `dws`, `rws`, `mws`, `serv`, `rig`). A rig is not one
machine, so this spec proposes the role vocabulary and asks `wl-stack` to adopt it.

| Selector | Machine | OS | Runs |
|---|---|---|---|
| `rig/task` | Task PC | **Ubuntu 24.04 LTS**, dual-boot Windows | `taskd`, `console`, `labhost` |
| `rig/eye` | OpenIris PC | Windows | OpenIris + OpenIrisDPI, ACCES DAC |
| `rig/sglx` | Acquisition PC | Windows | SpikeGLX, `neurofeatd` |
| `rig/intan` | Intan host | Windows or Linux | RHX, `rhxfeatd` |
| `rig/sync` | Sync box | Pi OS | `wl-sync` (already declared) |

`rig/sync` is already in use by `wl-sync`. The other four are new and land in
`wl-orchestrator`'s registry only once `wl-stack` agrees them, since host identity is
that repository's to define.

**Open:** whether `rig/intan` and `rig/sglx` are the same physical machine. RHX and
SpikeGLX both want CPU headroom, and P14 makes an RHX client that falls behind an
acquisition-halting fault — so co-tenancy is a measurement (V8), not a preference.

---

## 2. The task PC's operating system

### 2.1 Decision

**Ubuntu 24.04 LTS**, with a Windows partition on the same machine.

### 2.2 Why not Fedora

`wl-stack` standardizes the lab on Fedora. This machine deviates deliberately.

**NI-DAQmx 2026 Q2 supports RHEL 9.6/10.0, openSUSE 15.6/16.0, and Ubuntu 22.04/24.04 LTS.
Fedora is not on the list**
([NI Linux Device Drivers 2026 Q2 compatibility](https://www.ni.com/en/support/documentation/compatibility/26/ni-linux-device-drivers-2026-q2-compatibility.html),
read 2026-08-31). The kernel modules are DKMS-built against pinned kernels, so this is not
a packaging inconvenience that a shim policy can absorb — it is an out-of-tree kernel module
on a machine that must not break the week before a recording, and Fedora's kernel cadence is
the wrong environment for one. `wl-stack`'s own README already anticipates that `rig` will
differ from a workstation.

Ubuntu over RHEL 10 because it is the mainstream target for the NVIDIA and graphics stack
this machine also depends on, and because LTS gives a pinned kernel for the DKMS module's
whole life. RHEL 10 remains the fallback if a graphics problem makes Ubuntu untenable.

### 2.3 Why the Windows partition

ADR-0005 keeps MonkeyLogic a possible swap at the rig-contract layer. The same NI PCIe-6343
and the same MDR68 cabling serve both, so the swap costs a partition rather than a machine.
It also makes the Windows-side DAQmx path available as a control when diagnosing anything
odd on Linux.

### 2.4 What gets pinned, and re-validated

Distribution, kernel, NVIDIA driver, and session type (X11 vs Wayland) are recorded in the
rig config and in every measurement artifact. **Any change to any of them re-runs V1**
(pitfalls P4). Screen sharing stays off during recording, for the same reason.

---

## 3. The one unverified claim

> **NI PCIe-6343 with NI-DAQmx on Ubuntu 24.04 LTS is UNVERIFIED.**

NI's Linux readme formally supports **LabVIEW and C/C++ (gcc)** only and points to a
per-device compatibility tool rather than listing hardware
([NI-DAQmx Linux readme](https://www.ni.com/pdf/manuals/ni-daqmx-linux-2023-q1.html), read
2026-08-31). `nidaqmx-python` is a ctypes wrapper over that C API, so it should follow
wherever the C API goes — and "should" is the word P10 exists to forbid.

### 3.1 The bench test, in order

Run on a workstation with the card installed, **before rig commissioning and before the
breakout board arrives**. Nothing downstream proceeds on an assumption.

1. Driver installs; `dkms status` clean; card enumerates in NI MAX equivalent / `nilsdev`.
2. Survives a kernel update, or the kernel is pinned and the pin is recorded.
3. **Digital out:** write a 16-bit word plus strobe on P0.8–P0.23; loop back and confirm bit
   order and strobe width. This is the event-code path (S2) and the first thing that must
   be right.
4. **Digital in with change detection**, not polling — this is the photodiode-gated
   progression primitive (§5.4 of the parent). Measure edge-to-userspace latency under idle
   and loaded conditions. **This is protocol V2b and it has no prior estimate at all.**
5. **Analog in:** 9 channels, confirm ranges and terminal configuration.
6. Software-timed output jitter under load, with `taskd`-like CPU pressure (V2).
7. Repeat 3–6 on the Windows partition as a control.

### 3.2 If it fails

In descending order of preference: pin an older kernel; move to RHEL 10; move the event-code
path to the sync box's PIO (which already does contiguous-range capture) and keep NI for
analog only; or a microcontroller sidecar in the style of pyControl (measured 556 ± 17 µs
event-to-output). The board does not change in any of these — the copper is
controller-agnostic, which is the point of ADR-0005.

---

## 4. Task PC hardware

| Part | Requirement | Why |
|---|---|---|
| DAQ | **NI PCIe-6343** | Fixed by `wl-sync`'s board: 19 digital out, 4 in, 9 analog in, event codes on P0.8–P0.23 |
| Cables | 2 × `SHC68-68-EPM` per rig | Analog and digital ride physically separate shielded cables |
| GPU | NVIDIA, **DisplayPort 2.1 UHBR20 preferred** | See §5.3: it is the difference between compression in the visual path and none |
| CPU | High single-thread clock; enough cores to isolate `taskd` | Hot-path discipline uses CPU isolation and SCHED_FIFO (P3) |
| RAM | Sized for preloaded natural-image sets | No disk I/O once an epoch starts |
| Storage | NVMe, sized for a session's logs and behavioral tables | Raw neural data never lands here |

Two rigs. `wl-sync` fabs five breakout boards, so there is headroom, but nothing here is
specified for more than two.

---

## 5. Display

### 5.1 Panel class

**32-inch-class 16:9 flat OLED**, dual-mode preferred. Specific model deferred: the
intended purchase is a **tandem OLED expected to release in late 2026**.

Tandem is the right architecture for this application, and for a reason narrower than its
marketing. Stacked emissive layers reach a given luminance at lower per-layer current, which
buys **ABL headroom** and **burn-in resistance** — precisely the two risks §5.4 lists. The
figure that matters is therefore **sustained full-field luminance at 100% APL**, not peak
small-window brightness, which is the number that will be advertised and is irrelevant here.

**Schedule mitigation.** A launch date is not a plan. Buy a known-good 4K OLED now for bench
work — the ASUS ROG Swift OLED PG32UCDP (31.5" flat WOLED, 4K@240 / FHD@480,
[ASUS product page](https://rog.asus.com/monitors/27-to-31-5-inches/rog-swift-oled-pg32ucdp/),
read 2026-08-31) is the reference candidate — so that M1 and M2 are not blocked on a product
launch. V1 and V9 must be re-run on any new panel regardless: the JOV authors state that
performance "cannot be assumed or guaranteed" even across units of one model.

### 5.2 Geometry, as a formula

Written parametrically so a panel change is a recompute, not a redesign. For a 16:9 panel of
diagonal `L`, split vertically, viewed at distance `D` **along the folded optical path**:

```
half_width  = 0.2179 * L      (each eye's viewport half-width)
half_height = 0.2451 * L
theta_H = atan(half_width  / D)      field per eye = +/- theta_H
theta_V = atan(half_height / D)                     +/- theta_V
px_per_deg = (W_px / 2) / (2 * theta_H_degrees)
```

For a 31.5" panel (`L` = 80.0 cm; half-width 17.44 cm, half-height 19.61 cm):

| D | Field per eye (H × V) | 4K mode | FHD/480 mode |
|---|---|---|---|
| 45 cm | ±21.2° × ±23.5° | 45 px/deg | 23 px/deg |
| 50 cm | ±19.2° × ±21.4° | 50 px/deg | 25 px/deg |
| **57 cm** | **±17.0° × ±19.0°** | **56 px/deg** | **28 px/deg** |
| 65 cm | ±15.0° × ±16.8° | 64 px/deg | 32 px/deg |

**Build for 57 cm** (ruled 2026-08-31). At 57.3 cm one centimetre on the screen subtends one
degree — `1/tan(1°) = 57.29` — which is why it is the field's standing convention. The
arithmetic benefit is largely vestigial now that software does the trigonometry, and the
identity is a small-angle one that breaks down off-centre (at 20° eccentricity, 20° is 20.9 cm,
not 20 cm — a 4.5% error, so it must never be treated as linear across the field). What
survives is comparability with the literature and the ability to catch a gross geometry error
by eye. Against 50 cm it trades 2.2° of horizontal field for 6 px/deg, and ±17° still holds a
six-item array at 10° eccentricity with 7° of margin. A six-item array at the stated 10° maximum eccentricity sits inside
±19° with room to roughly double it, at 1.2 arcmin/pixel. The viewport is 8:9, so horizontal
eccentricity is the binding dimension — the cost of 16:9, and not binding on anything in the
stated program. Path lengths are **measured per eye**, not derived (V9): the two folded paths
are equal only if the mirrors are, and mirror angles set vergence, so alignment is a
calibrated parameter with a Nonius/vernier procedure rather than an assumed symmetry.

### 5.3 Mode is a rig configuration

4K and FHD/480 carry **identical pixel rates** (~30 Gbps at 10-bit for 4K/120 and FHD/480),
which is why dual-mode panels offer both. That gives a real experimental trade:

| Mode | Per eye @57 cm | Frame quantum | Suits |
|---|---|---|---|
| 4K | 1920×2160, 56 px/deg | 4.2 ms @240, 8.3 ms @120 | Disparity, fine gratings, natural images |
| FHD | 960×1080, 28 px/deg | **2.08 ms** | Saccade-contingent updates, fast timing |

Consequences: **V1 runs in every mode the rig will use**; each mode carries its own
calibration and deg/pixel; the mode is recorded in the session snapshot; and gaze-contingent
code never assumes a frame period.

**Compression is a purchase-time question.** 4K/240 at 10-bit is ~60 Gbps and exceeds
DisplayPort 1.4's ~25.9 Gbps of data, so it requires DSC. 4K/120 and FHD/480 sit at ~30 Gbps —
still over DP 1.4 at 10-bit, under it at 8-bit. DP 2.1 UHBR20 (~77 Gbps) carries all of them
uncompressed. DSC is "visually lossless" by VESA's design intent, which is a claim about human
subjective judgement on natural images, not about fine gratings, random-dot stereograms, or an
animal's V1. **Prefer a GPU and panel that can avoid it; if DSC is unavoidable, its effect is
measured, not assumed.**

### 5.4 Panel acceptance test — written now, before the panel exists

Fold into **V9**. A panel that fails 1 or 2 is disqualified regardless of everything else.

1. **Burn-in protection is fully defeatable.** Pixel-shift, screen-move, logo dimming and
   anti-flicker all off, and *verified* off. Pixel-shift translates the whole image
   periodically: on a rig with a calibrated gaze-to-pixel mapping and a photodiode patch at a
   fixed screen location, that is a silent, periodic corruption of the geometry, and it can
   walk the patch off its sensor. Ask the vendor before purchase; no review covers it.
2. **ABL as interocular coupling.** Fill-factor sweep in one viewport, photometered in the
   other. On two displays ABL is a per-eye nonlinearity; **on one shared panel it is a
   coupling** — a bright stimulus in the left eye's viewport dimming the right eye's. The JOV
   paper found luminance "drops drastically" above ~40% fill factor on the panel it tested.
   Report the fill-factor range within which no coupling is detectable; that range is a
   stimulus-design constraint.
3. **Per-half uniformity.** Photometer left and right halves separately. On a split screen,
   left-right nonuniformity *is* an interocular mismatch. The IPS LCD in the JOV study showed
   10.7% with the left side underperforming; the 27" OLED showed ~4%.
4. **Gamma, additivity and channel independence**, per unit, after calibration.
5. **Pixel response and onset**, photodiode-measured, in every mode.
6. **Sustained full-field luminance at 100% APL**, which is the tandem claim that actually
   matters.

**Burn-in mitigation may not touch the stimulus** (ruled 2026-08-31). Jittering the fixation
point between trials was proposed here and **rejected**: microsaccade analyses, fixation-
stability measures and receptive-field mapping all assume a fixed fixation point, and
introducing a stimulus manipulation to solve a hardware problem trades a real experimental
property for a panel's convenience.

So mitigation is entirely hardware-side, which **raises the stakes on the tandem panel**: its
inherent burn-in resistance is now load-bearing rather than a bonus, and running well below
peak luminance is a longevity strategy as well as an ABL one. Panel replacement is budgeted
rather than avoided. This makes acceptance criterion 6 — sustained full-field luminance at
100% APL — the number that decides how low we can sit, and therefore how long a panel lasts.

---

## 6. Procurement

| Item | Qty | Lead | Order |
|---|---|---|---|
| NI PCIe-6343 | 2 (+1 bench) | **12–13 wk** | **Now.** Independent of everything else, and needed for the Windows side regardless, so the purchase carries no software risk |
| `SHC68-68-EPM` | 4 (+2 bench) | with the cards | Now — same lead time, easily forgotten |
| Bench 4K OLED | 1 | stock | Now — unblocks M1/M2 from the tandem launch |
| Task PC | 2 (+1 bench) | stock | Now, so the §3.1 bench test can run |
| Tandem OLED | 2 | late 2026 | On release, against §5.4 |
| Stereoscope optics | 2 sets | build | After §5.2's distance is fixed against the real chair geometry |

`wl-sync` fabs the breakout boards on its own schedule: prototype late October to late
November, production run mid-November to mid-December, with almost no slack for a respin.

---

## 7. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | `wl-stack` adopting the `rig/*` role vocabulary | the registry entry's `runs_on` |
| 2 | Whether `rig/intan` and `rig/sglx` are one machine | V8, and the task PC's network layout |
| 3 | Tandem panel model, and whether burn-in protection is defeatable | the panel purchase |
| 4 | Whether the chosen GPU + panel can avoid DSC | GPU purchase |
| 5 | Photodiode patch placement against the real optics | rig build, and `wl-sync` agreement |
| 6 | Viewing distance against the real chair and head-post geometry | optics build |
