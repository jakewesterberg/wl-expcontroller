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
| GPU | **NVIDIA GeForce RTX 5070 Ti** (PI, 2026-09-26). NVIDIA lists "DisplayPort 2.1b with UHBR20", 3× DisplayPort and 16 GB GDDR7 ([spec page](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/), read 2026-09-26). Partner boards' port layouts can vary, so confirm UHBR20 on the board bought | UHBR20 (~77 Gb/s) carries 4K/240 at 10-bit (~60 Gb/s) with no DSC (§5.3). 16 GB rather than the RTX 5070's 12 GB, for preloaded natural-image sets: one 4K 8-bit RGBA image is ~33 MB of VRAM. Rendering load is not the constraint; the link and VRAM are |
| CPU | High single-thread clock; enough cores to isolate `taskd` | Hot-path discipline uses CPU isolation and SCHED_FIFO (P3) |
| RAM | Sized for preloaded natural-image sets | No disk I/O once an epoch starts |
| Storage | NVMe, sized for a session's logs and behavioral tables | Raw neural data never lands here |

Two rigs. `wl-sync` fabs five breakout boards, so there is headroom, but nothing here is
specified for more than two.

---

## 5. Display

### 5.1 Panel class

**27-inch-class 16:9 flat tandem QD-OLED at 4K/240** (changed from 32-inch-class on
2026-09-27; see below). **QD-OLED is a requirement** (PI, 2026-09-26).

**Chosen (PI, 2026-09-27): the ASUS ROG Swift OLED PG27UCDM.** It replaces the PG32UCDM
Gen 3 chosen the day before. **Why:** most experiments view the monitor directly, not
through the stereoscope, which needs only ±10° (PI, 2026-09-27). The eye-tracker camera
views the eye from below the screen, and the PI's worry was the camera angle a larger
screen forces. The comparison (`docs/research/2026-09-27-panel-27-vs-32.md`) found:
- the camera-angle difference is only 1–2° at a given distance;
- the 27-inch shows less field;
- neither panel is the limit at 15°: DPI's P4 reach (about 10° in macaques, per the
  OpenIrisDPI paper) is the limit, and it is handled by a pupil and corneal-reflection
  fallback (S5, PI 2026-09-27).

The PI chose the 27-inch with those numbers in hand.

**Direct-view geometry at 57 cm** (the comparison's figures): about ±27° × ±16°, at about
65 px/deg. That leaves roughly a degree of vertical margin beyond a 15° target, so the
direct-view viewing distance was left to the direct-view design. **The PI has since fixed the
screen at 50 cm from the eyes, physically, in both setups** (2026-09-28, §5.2). At 50 cm direct
view shows ±30.5° × ±18.4°, 3.4° beyond a 15° target vertically; its design, approved the same
day, is `2026-09-28-direct-view-design.md`.

**The Alienware AW2725Q was compared, 2026-09-28, and the PI kept the ASUS** — "3, but we check
again for a new dell model later (in jan once I arrive and can purchase)"; Dell is easier to order
at KU Leuven. Per Dell's user guide and product page, read 2026-09-28: the **same active area,
589.97 × 332.93 mm**, and 0.153 mm pitch, 3840 × 2160 at 240 Hz, QD-OLED, $899.99 — so none of
§5.2's geometry would change. The difference: **"1 DisplayPort 1.4 (HDCP 1.4 & 2.3) port
(Supports up to 3840 x 2160, 240 Hz, DSC, HDR)"**, so 4K/240 needs DSC (§5.3's rule is to avoid
it). No QD-OLED generation or "tandem" is named; pixel refresh "is activated automatically when you
have used the monitor for 4 hours" and "takes approximately 6 to 8 minutes", and the guide does not
say whether it waits for standby (UNVERIFIED — a 12-hour session would meet it); no pixel shift or
proximity sensor is mentioned. **Re-check Dell's lineup in January 2027, before purchase**, for a
27-inch 4K QD-OLED with DisplayPort 2.1 UHBR20 (uncompressed 4K/240).

ASUS lists, per the spec page and product page read 2026-09-27:
- a **26.5" Tandem QD-OLED**, "Latest 4th-gen QD-OLED", 3840 × 2160 at 240 Hz, 0.153 mm
  pixel pitch, 10-bit;
- **"DisplayPort 2.1a UHBR20 (80Gbps full bandwidth)"**, carrying "4K at 240Hz ... without
  compression", plus HDMI 2.1 × 2;
- DisplayHDR 400 True Black;
- **a three-year warranty that includes panel burn-in**;
- VESA 100 × 100, 4.97 kg without its stand.

Sources:
- [spec page](https://rog.asus.com/monitors/27-to-31-5-inches/rog-swift-oled-pg27ucdm/spec/)
- [product page](https://rog.asus.com/monitors/27-to-31-5-inches/rog-swift-oled-pg27ucdm/)

With the RTX 5070 Ti, 4K/240 runs without DSC, so open item 4 stays closed. Still open,
as for the panel before it:
- **ASUS's "Pixel cleaning" runs automatically.** Its **Neo Proximity Sensor "transitions to
  a black image"** when it decides you have stepped away. Only its detection distance is
  stated as adjustable, and no page says either feature can be turned off. §5.4 test 1
  disqualifies a panel on this, so ask ASUS before buying.
- **No FHD/480 mode is listed.**
- **Full-field luminance and color accuracy are unpublished**, so V9 measures them.

**§5.2's geometry and the stereoscope optics drawing were recomputed for the PG27UCDM on
2026-09-28.** The drawing's revision also fixes the two errors the comparison found in its
relations: mirror sizes that clipped the field's corners, and a wrong nasal-clip formula.

**The PG32UCDM Gen 3, chosen 2026-09-26 and replaced 2026-09-27.** ASUS lists:
- a 31.5" **Tandem QD-OLED** panel at 4K/240;
- **"DisplayPort 2.1a UHBR20 (80Gbps full bandwidth)"**, carrying "4K at 240Hz ... without
  compression";
- DisplayHDR 500 True Black;
- a three-year warranty that includes panel burn-in.

Sources:
- [product page](https://rog.asus.com/us/monitors/27-to-31-5-inches/rog-swift-oled-pg32ucdm-gen3-pg32ucdm3/)
- [spec page](https://rog.asus.com/us/monitors/27-to-31-5-inches/rog-swift-oled-pg32ucdm-gen3-pg32ucdm3/spec/)

Both were read 2026-09-26. It is QD-OLED **and** tandem, the architecture the paragraph
below argues for, and with the RTX 5070 Ti it runs 4K/240 without DSC, which settles open
item 4. Three things remain:
- **No FHD/480 mode is listed**, so §5.3's 2.08 ms FHD mode is unavailable on this panel.
  The frame quantum is 4.2 ms at 4K/240.
- **OLED Care may not be defeatable.** ASUS lists pixel shift ("users can choose between
  several movement levels") and a **Neo Proximity Sensor that "switches to a black screen"**
  when it decides no one is present. Neither page says either can be turned off. On a rig,
  the one in front of the screen is an animal at a fixed distance, so either could corrupt a
  session. §5.4 test 1 disqualifies a panel on this, so ask ASUS before buying.
- **Unpublished figures:** full-field luminance at 100% APL and color depth are not listed,
  so they are unverified until V9 measures them.

§5.2's geometry was computed from its 31.5" viewable diagonal until 2026-09-28.

**Considered the same day:**
- The **Samsung Odyssey OLED G8 G80SH** (`LS32HG802SNXZA`; QD-OLED, "DP 2.1 (UHBR20)",
  [product page](https://www.samsung.com/us/monitors/gaming/32-inch-odyssey-oled-g8-g80sh-4k-gaming-monitor-sku-ls32hg802snxza/)
  read 2026-09-26), was chosen briefly. It was replaced because the Gen 3's panel is tandem.
- The **ASUS PG32UCDMR** is the like-for-like non-tandem alternative: third-generation
  QD-OLED, DP 2.1a UHBR20, DisplayHDR 400 True Black.
- The **ASUS PG32UCWM** is a tandem *RGB* OLED with an FHD/480 dual mode. It is excluded by
  the QD-OLED requirement, and would be the choice if the fast mode ever outweighs it.

The ASUS PG32UCDP below is kept as history: ASUS lists its input as "DisplayPort 1.4 DSC"
([spec page](https://rog.asus.com/monitors/27-to-31-5-inches/rog-swift-oled-pg32ucdp/spec/),
read 2026-09-26), so it compresses 4K/240 whatever the GPU.

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

Written parametrically so a panel change is a recompute, not a redesign. For a panel whose
active area is `W` × `H`, split vertically, viewed at distance `D` **along the folded optical
path**:

```
half_width  = W / 4           (each eye's viewport half-width)
half_height = H / 2
theta_H = atan(half_width  / D)      field per eye = +/- theta_H
theta_V = atan(half_height / D)                     +/- theta_V
px_per_deg = (W_px / 2) / (2 * theta_H_degrees)
```

**Use the maker's active area, not the diagonal.** For an exact 16:9 panel of diagonal `L` the
half-extents are `0.2179 * L` and `0.2451 * L`, the form this section first used. ASUS publishes
the PG27UCDM's active area as "589.97 x 332.93 mm"
([spec page](https://rog.asus.com/us/monitors/27-to-31-5-inches/rog-swift-oled-pg27ucdm/spec/),
read 2026-09-28), which is 1.772:1 rather than 16:9, and its "26.5-inch viewable" is rounded (the
area's own diagonal is 26.67 in). The diagonal form fed 26.5 in would put each edge 0.6–0.9%
short.

**The screen is 50 cm from the eyes, physically, in both setups** (PI, 2026-09-28): "I want the
screen to be the same physical distance from the animal in stereoscope and the direct viewing.
The stereoscope is a device that is removable and everything else is fixed." The screen is fixed
in place, on a locked arm or stand with a stop, measured once at setup and re-checked in the
regular rig checks.

**So the stereoscope's optical path is about 63 cm:** `D = Z + HW − E`, 63.15 cm at `E` = 1.6 cm
and 62.85–63.25 cm over IPD 30–38 mm, because the periscope adds its lateral run `HW − E`
(optics drawing §3, §4.4). `D` in the formula is that folded path, and it is per animal. The
path was ruled 57 cm on 2026-08-31 and reaffirmed on 2026-09-28 after comparing 50 cm; the same
day the PI fixed the physical distance instead, and the path followed.

For the PG27UCDM (half-width 14.75 cm, half-height 16.65 cm):

| D | Field per eye (H × V) | 4K mode | FHD/480 mode |
|---|---|---|---|
| 45 cm | ±18.2° × ±20.3° | 53 px/deg | 26 px/deg |
| 50 cm | ±16.4° × ±18.4° | 58 px/deg | 29 px/deg |
| 57 cm | ±14.5° × ±16.3° | 66 px/deg | 33 px/deg |
| **63.15 cm** (the stereoscope, `E` = 1.6 cm) | **±13.1° × ±14.8°** | **73 px/deg** | **37 px/deg** |
| 65 cm | ±12.8° × ±14.4° | 75 px/deg | 38 px/deg |

The px/deg columns are the formula's mean across the viewport. Through the stereoscope a pixel
at the center subtends 0.84 arcmin, 71.7 px/deg. The PG27UCDM lists no FHD/480 mode (§5.1), so
that column is the formula's alone. The 31.5" panel this section described until 2026-09-28
gave ±17.0° × ±19.0° and 56 px/deg at 57 cm.

**The stereoscope needs ±10°** (PI, 2026-09-27: "for the stereoscope setup +/- 10 deg is enough,
most of the experiments will not be in the stereoscope"). Through it the panel gives ±13.15° ×
±14.77° at `E` = 1.6 cm. That field is stopped by a removable mask at the panel, starting at
±12° (PI, 2026-09-28; the optics drawing's §5), 1.15° inside its horizontal edge.

**The 1 cm ≈ 1° convention does not hold through the stereoscope.** At 57.3 cm one centimeter on
the screen subtends one degree (`1/tan(1°) = 57.29`); at 63.15 cm it subtends 0.91°. The
convention was always a small-angle identity that breaks down off-center (at 20° eccentricity,
20° is 20.9 cm, not 20 cm — a 4.5% error), and software does the trigonometry, so a gross
geometry error is caught against the measured path. ±13.15° holds a six-item array at 10°
eccentricity with 3.1° of margin, 2° inside the ±12° mask, and the same array sits inside ±14.8°
vertically, at 0.84 arcmin per pixel. (This paragraph said 1.2 arcmin before 2026-09-28, which
was the 31.5" panel's figure at 50 cm; at 57 cm it was 1.1.) The viewport is 8:9, so horizontal
eccentricity is the binding dimension — the cost of 16:9, and not binding on anything in the
stated program. Path lengths are **measured per eye**, not derived (V9): the two folded paths
are equal only if the mirrors are, and mirror angles set vergence, so alignment is a
calibrated parameter with a Nonius/vernier procedure rather than an assumed symmetry.

### 5.3 Mode is a rig configuration

4K and FHD/480 carry **identical pixel rates** (~30 Gbps at 10-bit for 4K/120 and FHD/480),
which is why dual-mode panels offer both. That gives a real experimental trade:

| Mode | Per eye, stereoscope (D ≈ 63 cm) | Frame quantum | Suits |
|---|---|---|---|
| 4K | 1920×2160, 73 px/deg | 4.2 ms @240, 8.3 ms @120 | Disparity, fine gratings, natural images |
| FHD | 960×1080, 37 px/deg | **2.08 ms** | Saccade-contingent updates, fast timing |

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
| Stereoscope optics | 2 sets | build | Geometry drawn (`2026-08-31-stereoscope-optics-drawing.md`); first-surface mirrors, 4 per rig |

`wl-sync` fabs the breakout boards on its own schedule: prototype late October to late
November, production run mid-November to mid-December, with almost no slack for a respin.

The eye tracker's and the behavior cameras' parts lists are in §7.

---

## 7. Parts lists (addendum, 2026-09-27; revised the same day)

A reasoned list for the PI, who owns procurement. It is not an order.

**Edmund Optics first** (PI, 2026-09-27): every optics, lighting and mounting line is checked
at Edmund first, and Edmund is preferred where it meets the requirement. Each row notes when
Edmund had nothing suitable. **Every optics, lighting, filter and mounting row has now had that
check**: rows 5b–5c and §7.10 on 2026-09-27, the rest on 2026-09-28 (§7.11). Edmund's USB3
cards and cables were checked too. The computers, GPU, drives, motherboard, RAM, power supply,
case, cooler and the ACCES box were not checked at Edmund, because they are outside its range.

**Revised after the PI went through the first version row by row** (2026-09-27, 38 rows).
The rows keep the walkthrough's numbers: 7.1-1 to 7.1-16 and C1 to C22. **The PI's
decisions bind.** What is still open says what it waits on.

- **Sources.** Every part fact (model, spec, price, compatibility) comes from the maker's or a
  distributor's own page, read 2026-09-27, or is marked **UNVERIFIED**. Links are in the
  tables. Two retailers, Micro Center and B&H, served a bot check on the power supply's page.
  It was not bypassed, and neither is used. 8020.net did the same in the first version. What
  the Edmund pass changed cites Edmund's pages read 2026-09-28.
- **Prices** are what each page showed that day, in US dollars unless marked €. Sale prices
  are marked. None is a quote.
- **Status** is one of: *decided*; *waits on* a named measurement or design; or *PI's call*.
- **Arithmetic** is labeled as arithmetic, **assumptions** as ASSUMED, and **inferences** as
  INFERENCE.

**What binds the lists** (PI, 2026-09-27):

- **Two IR bands.** The eye tracker uses **940 ± 25 nm** and the behavior cameras use
  **850 ± 25 nm**. Each group's band-pass filter rejects the other group's light. So the
  behavior cameras have their own 850 nm lamps, and C20 is required.
- **The eye tracker.**
  - OpenIrisDPI stays live on **one tracker PC: Windows now, Linux later** (P10). There is
    no second purchase.
  - P10's tracker is validated offline on raw eye video from our rig, so the tracker PC
    records raw video from both cameras.
  - **Direct view is the primary configuration.** The camera views the eye from below the
    screen, mounted on the head-post frame and independent of the monitor. The stereoscope
    (±10°) is secondary, and its mount is decided with the layout.
  - **One collimated 940 nm light per eye.** The cameras and the lights ride on an IPD
    adjustment system on the rig's existing frame, with 3D-printed brackets.
  - The left camera's ExposureActive goes to wl-sync GPIO26 (S3 §8). The right camera is
    aligned by its barcode samples.
  - The ACCES USB-AO16-8A stays as the analog backup.
- **The behavior cameras (P9).**
  - 1–2 on the face and 1–2 on the body: 2–4 typical, 8 at most.
  - 200 fps, recorded the whole session, encoded on a consumer GPU.
  - The primary triggers the rest through a **custom fan-out board**, which also strobes the
    lamps (PI, 2026-09-27, reversing the off-the-shelf call; §7.4). It needs a design check.
  - **Fixed lenses now**, at ASSUMED distances. There are no filter adapters.
  - The mounts are 3D-printed brackets on the existing frame.
  - **The cameras do not go into regular use until wl-nas exists.**
- **The camera box** is AMD and rack-mounted. Its target is about $4,000 for the computer,
  GPU, storage and USB cards, not counting the cameras. The PI accepted about $4,690 with two
  drives, and later **a modest overrun** of that (PI, 2026-09-27; §7.6).

### 7.1 The eye tracker: changes from the OpenIrisDPI reference build

The reference build is the OpenIrisDPI wiki's "ohDPI Assembly Introduction", read 2026-09-27.
This addendum worked from that reading's hardware list and did not reopen the wiki. Nothing in
the list touches P10's method, which stays clean-room
(`docs/research/2026-09-27-p10-dpi-spike.md` §3).

| # | Role | Requirement | Candidate (maker, model) | Qty | Source, read 2026-09-27 | Price (USD) | PI's decision; status |
|---|---|---|---|---|---|---|---|
| 1 | Tracker cameras | OpenIrisDPI's own frames: same sensor, 500 Hz at the paper's 720 × 450 ROI | Teledyne FLIR Blackfly S **BFS-U3-16S2M-CS**, bought from Edmund as **#11-507** | 2 | [Edmund #11-507](https://www.edmundoptics.com/p/bfs-u3-16s2m-cs-usb3-blackflyreg-s-monochrome-camera/40163/) (read 2026-09-28; 14 in stock); [Teledyne product page](https://www.teledynevisionsolutions.com/products/blackfly-s-usb3/?model=BFS-U3-16S2M-CS&vertical=machine%20vision&segment=iis) | 556.50 each (Edmund and Teledyne) | **Kept.** It is also P9's body, so the rig has one camera model. *Decided*. **Source: Edmund**, the same part at the same price |
| 2 | Lenses | A C-mount machine-vision lens, NIR-coated, at about the reference's magnification (0.2×), focusing at the working distance, with a ring if needed (§7.1.1) | For about 45–50 cm: Edmund Optics **#74-054**, 75 mm C VIS-NIR. It has f/2.0–16, a 425–1000 nm BBAR coating, a 2/3" format, a 500 mm–∞ working distance, a **M43 × 0.75** filter thread, and measures Ø48 × 98.8 mm. For about 57–60 cm: Edmund **#27-555**, 100 mm C VIS-NIR. It has f/2.8–22, the same coating, a 4/3" format, 750 mm–∞, a **M46 × 0.75** thread, and measures Ø52 × 92.1 mm | 2 | [#74-054](https://www.edmundoptics.com/p/75mm-c-vis-nir-series-fixed-focal-length-lens/56588/); [#27-555](https://www.edmundoptics.com/p/100mm-c-vis-nir-series-fixed-focal-length-lens/53829/) | 690.00 each (9 in stock); 760.00 each ("contact us") | **Changed** from the Laowa macro to a C-mount lens. Which focal length *waits on* the direct-view working distance (§7.1.1) |
| 3 | Spacer and ring | Put the C-mount lens on the CS body, and focus closer than the lens's minimum | Edmund **#03-618**, a 5 mm spacer (male CS, female C) that Edmund lists under Teledyne FLIR. It is needed: the C-mount flange distance is 17.526 mm and CS is 12.526 mm (Edmund). Alternative: Teledyne **ACC-01-5004** direct. Plus a C-mount extension ring where the eye is inside the lens's minimum working distance (§7.1.1): Edmund **#54-628** (5 mm), or the **#54-261** kit (0.5, 1, 2 × 5, 10, 15 and 40 mm) to fit it on the bench | 2 + 0–2 | [#03-618](https://www.edmundoptics.com/p/5mm-spacer-to-convert-cs-mount-cameras-to-c-mount/90/) (read 2026-09-28; 20+ in stock); [Teledyne spacer](https://www.teledynevisionsolutions.com/products/cs-to-c-mount-5mm-spacer-adapter/); [Edmund, lens mounts](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/lens-mounts/); [#54-628](https://www.edmundoptics.com/p/5mm-length-c-mount-extension-tube/11303/); [#54-261](https://www.edmundoptics.com/p/c-mount-extension-tube-kit/11115/) | 29.00 each (Teledyne direct: 11.80); 33.25; 133.00 (kit, "contact us") | **The spacer is needed**; the EF adapter is gone. **Swapped to Edmund** (PI preference), at $17.20 more each. Edmund names no Teledyne part number, so that #03-618 is the ACC-01-5004 is INFERENCE. The ring *waits on* the working distance |
| 4 | IR filter | 940 ± 25 nm band-pass, threaded straight onto the lens, no adapter | Edmund mounted machine-vision band-pass: **#28-792** (M43 × 0.75) on #74-054; **#28-793** (M46 × 0.75) on #27-555. 940 nm center, FWHM 55 nm, transmission 90% or more, blocking 350–900 and 1000–1100 nm; 7 mm thick with its thread. Alternative: MidOpt **BN940-43 / BN940-46** (useful range 928–955 nm, FWHM 55 nm, peak transmission 85% or more) | 2 | [#28-792](https://www.edmundoptics.com/p/bandpass-filter-940nm-m43-thread/52504/), [#28-793](https://www.edmundoptics.com/p/bandpass-filter-940nm-m46-thread/52505/) (read 2026-09-28); [MidOpt BN940](https://midopt.com/filters/bn940/); [MidOpt threads](https://midopt.com/mounting-solutions/threaded-mount/); Machine Vision Direct [BN940-43](https://machinevisiondirect.com/products/midopt-bn940-43), [BN940-46](https://machinevisiondirect.com/products/midopt-bn940-46) | 231.00 (3 in stock) / 252.00 (1 in stock). MidOpt through Machine Vision Direct: the same prices, built to order in 15 business days | **Changed** from the long-pass sheet. *Decided*; the size follows row 2. **Swapped to Edmund** (PI preference). Edmund's site finds no "MidOpt" or "BN940" and names no maker for these. Their center, width, threads and prices match MidOpt's BN940, so they may be MidOpt's (INFERENCE). The 55 nm FWHM is slightly wider than ±25 nm. Edmund's stated blocking covers the behavior lamps' 850 nm |
| 5 | Light, per eye | One compact collimated 940 nm source per eye, riding on the IPD carriage. It sits 10° shallower than its camera (the paper's rule), with its current capped for eye safety (§7.1.2) | Thorlabs **M940L3** (940 nm; 800 mW minimum at 1000 mA; FWHM 37 nm) with a **SM1U25-B** adjustable collimation adapter, which has a Ø1" asphere, AR-coated 650–1050 nm. It replaces the reference's Ø2" SM2F + ACL50832U. Alternative: Mightex **LCS-0940-02-22**, an integrated collimator: 200 mW typical at 1000 mA, 22 mm aperture, 3.4° half-divergence | 2 | [Thorlabs mounted LEDs](https://www.thorlabs.com/mounted-leds?pn=M940L3); [SM1U25-B](https://www.thorlabs.com/item/SM1U25-B); [Mightex](https://www.mightexsystems.com/product/high-power-led-collimator-sources-22-mm-clear-aperture/) | 274.55 (lead time) + 338.29 = **612.84 per eye**; Mightex's price is not published | **Changed** (PI): one light per eye, on the IPD system. Edmund has no compact collimated 940 nm source (§7.1.2; rechecked 2026-09-28). Thorlabs or Mightex is the *PI's call* |
| 5b | Light driver | Constant current, a modulation input (so the lights can later strobe with the exposures), and a current cap the operator cannot turn past | Thorlabs **LEDD1B** T-Cube: up to 1200 mA; modulation to 5 kHz; trigger mode to 1 kHz; a current limit adjustable from **0.2 to 1.2 A** by a trim pot. With a **KPS201** supply. One per eye | 2 + 2 | [LEDD1B family page](https://www.thorlabs.com/t-cube-tm-led-driver?pn=LEDD1B); [LEDD1B](https://www.thorlabs.com/item/LEDD1B); [KPS201](https://www.thorlabs.com/item/KPS201) | 380.04 + 43.15 each | **Two single-channel drivers, one per eye.** No two-channel driver with a modulation input was sensible (§7.1.2). **The LEDD1B's limit does not go below 200 mA**; the alternatives are compared in §7.10, and it stays the recommendation there with row 5c behind it. *PI's call*. Edmund has no constant-current driver for this LED (§7.10) |
| 5c | Fixed attenuator, per eye | A physical cap on the light at the eye, whatever the driver does: sized at bring-up so the eye stays under the limit at the highest current the driver can deliver (§7.10) | Edmund Optics **TECHSPEC NIR ND**, Ø25 mm, reflective (metallic on fused silica), flat 700–1100 nm, OD tolerance ±10%, 3.00 mm thick; **#47-530** is OD 1.0, and the OD is chosen at bring-up. Held in the collimator's output by a Thorlabs **SM1A38** (external M34 × 0.5, internal SM1) and an Edmund **#35-763** SM1 retainer ring | 2 + 2 + 2 | [Edmund NIR ND family](https://www.edmundoptics.com/f/near-ir-nir-neutral-density-nd-filters/13025/); [#47-530](https://www.edmundoptics.com/p/10-od-25mm-dia-nir-nd-filter-/7611/); [SM1A38](https://www.thorlabs.com/item/SM1A38); [#35-763 (listed as an accessory)](https://www.edmundoptics.com/p/5mm-id1-lens-tube/33305/) | 126.00 (OD 1.0; other ODs not read) + 31.62 + 5.25 | **New; decided** (PI, 2026-09-28, §7.10). The OD is set at bring-up. Whether the SM1A38 is deep enough for a 3 mm filter and a ring is **UNVERIFIED** |
| 6 | Lens clamps | — | Thorlabs VG100/M | — | — | — | **Dropped** (PI). A C-mount lens is held by the camera |
| 7 | IPD adjustment system | Per-animal eye spacing. It carries both cameras and both lights, on the rig's existing frame, with 3D-printed brackets | Requirements are in §7.1.3. An off-the-shelf slide, one per side: Edmund TECHSPEC **#16-716** metric dovetail stage: 65 × 65 mm; 25 mm travel; 0.5 mm lead-screw pitch, hex-driven; an external plate lock included; brass, 15 kg load; 10 µm straight-line accuracy. Its angular deviation is not published (**UNVERIFIED**). Alternative: Thorlabs **DTS25/M** (25 mm travel, 1 mm per turn, a locking screw, ±250 µrad angular deviation, 68 × 99 × 20 mm) | 2 | [#16-716](https://www.edmundoptics.com/p/dovetail-stage-65mm-sq-metric/44117/) (read 2026-09-28; 20+ in stock); [Thorlabs DTS25](https://www.thorlabs.com/1-inch-25-mm-travel-dovetail-translation-stages?pn=DTS25/M); [DTS25/M](https://www.thorlabs.com/item/DTS25_M) | 212.00 each (DTS25/M: 233.88) | **Changed** (PI) from 80/20 framing. **Swapped to Edmund** (PI preference): the same travel, a lock, a smaller footprint, $21.88 less each. Edmund's 40 mm stage (#16-715) has only 14 mm of travel, the bare ±7 mm. Its design *waits on* rig geometry. Symmetric or independent carriages is the *PI's call* (§7.1.3) |
| 8 | Direct-view camera mount (primary) | The cameras and lights sit on the head-post frame, **independent of the monitor**, below the screen at about 30–35° (panel comparison §4.2) | The IPD system (row 7) on a 3D-printed bracket from the frame | 1 | panel comparison | — | **Changed** (PI). At the paper's 57 cm and 35°, the camera is 46.7 cm forward of the eyes and 32.7 cm below them (panel comparison §4.2). *Waits on* the direct-view working distance |
| 8b | Monitor arm or stand | The PG27UCDM (VESA 100 × 100; 4.97 kg without its stand, §5.1) goes on its own arm or stand, off the camera frame | Ergotron **LX Desk Monitor Arm, 45-241-224**: VESA 75 and 100; 3.2–11.3 kg; a clamp or grommet | 1 | [Ergotron](https://www.ergotron.com/en-us/products/product-details/45-241) | 219.00 | **New** (PI). A spring arm can be moved, so the viewing distance is re-measured each session or the arm is locked in place (INFERENCE; V9). Arm or fixed stand is the *PI's call*. Edmund has nothing suitable: its site finds no VESA mount, only lab articulating arms |
| 9 | Stereoscope mount (secondary, ±10°) | The same camera-to-eye geometry, below M1 | — | — | panel comparison §9 | — | **Decided with the layout** (PI): either the one carriage moves, or there is a second fixed position |
| 10 | Camera USB cables | Camera to tracker PC | Teledyne FLIR's USB 3.1 Micro-B locking cable, 5 m, bought from Edmund as **#88-058** (Teledyne's **ACC-01-2301**). Beyond 5 m: Newnex **FIRENEX-ULS-08 / -12 / -16**, active. Edmund's 8–20 m USB3 locking cables (#34-212 is 8 m, $276) do not say they are active, so they are not used | 2 | [#88-058](https://www.edmundoptics.com/p/usb-30-locking-cable-5m/30343/) (read 2026-09-28); [Teledyne cables](https://www.teledynevisionsolutions.com/products/usb-3.1-locking-cable); [Teledyne app note](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/extending-the-working-distance-of-usb-3.1-cameras); [Newnex](https://newnex.com/usb-3-active-cable-a-to-micro-b.php) | 61.00 each (Teledyne direct: 37.50); Newnex's price is not published | **Kept** (PI). **Source: Edmund**, the same Teledyne cable, at $23.50 more each. The length is chosen with the layout, and §7.8 covers a passthrough panel |
| 11 | GPIO cables | Camera GPIO to the sync box | Teledyne FLIR's Hirose HR10 6-pin GPIO cable, bought from Edmund: **#88-064** (1 m) or **#88-065** (4.5 m). Teledyne's numbers are **ACC-01-3009** and **ACC-01-3010** | 2 | [#88-064](https://www.edmundoptics.com/p/blackflyreg-6-pin-gpio-hirose-connector-1m-cable/30349/), [#88-065](https://www.edmundoptics.com/p/blackflyreg-6-pin-gpio-hirose-connector-45m-cable/30350/) (read 2026-09-28); [Teledyne](https://www.teledynevisionsolutions.com/products/hirose-hr10-6-pin-circular-connector/) | 38.00 / 71.00 (Teledyne direct: 37.50 / 43.90) | **Kept** (PI). **Source: Edmund**, the same Teledyne cables. The length is chosen with the layout |
| 12 | Eye-group sync wiring | wl-sync's eye barcode BNC (`CAM_SYNC_EYE`) goes into each camera's opto input, Line 0. The left camera's ExposureActive leaves by its opto output, Line 1, into wl-sync J17B, which is GPIO26. That front end supplies its own 1 kΩ pull-up to 5 V (wl-sync `hardware/breakout/frame-time-inputs.md`) | wiring | — | [FLIR I/O table](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/InputOutputControl.htm); wl-sync at `92714ce` | — | **Decided** (PI, 2026-09-27): only the left camera's ExposureActive goes to GPIO26, so there is no wire-OR and no sync-box change. The right camera is aligned by the barcode it samples every frame |
| 13 | Tracker PC | **One PC: Windows 11 now** (OpenIrisDPI), **Linux later** (P10). Reference class (the reference used an i9-12900K). A free PCIe slot that is **x4 electrical** for row 14, a PCIe 2.0 x4 card. A free M.2 slot for row 15. Neither slot may disable the other. PCIe ASPM on the bring-up list (§7.6) | requirements, not a model | 1 | the reference build; row 14's card page | — | **Changed** (PI): one PC, and no second purchase at P10. The model is the *PI's call* |
| 14 | One USB3 controller per camera | 2 × 162 MB/s (arithmetic, §7.1.4) | Teledyne **ACC-01-1205**: four independent Fresco FL1100 host controllers on PCIe 2.0 x4 | 1 | [card page](https://www.teledynevisionsolutions.com/products/usb-3.1-host-controller-card?model=ACC-01-1205&vertical=machine%20vision&segment=iis) | 148.00 | **Always added** (PI). *Decided*. Edmund has nothing suitable: its USB3 cards are PCIe 2.0 x1, and the four-port [#89-539](https://www.edmundoptics.com/p/4-port-usb-30-pcie-card-20-x-1/32010/) puts all four ports on one Fresco FL1100 ($80; read 2026-09-28) |
| 15 | Raw validation video (P10) | Raw video from both cameras, at 324 MB/s sustained | Samsung **990 PRO 4 TB** (MZ-V9P4T0B/AM; PCIe 4.0; 5 years or 2,400 TBW) | 1 | [Samsung](https://www.samsung.com/us/memory-storage/nvme-ssd/990-pro-pcie-4-0-nvme-ssd-4tb-sku-mz-v9p4t0b-am/) | 1,099.99 | **Kept** (PI). Whether OpenIris writes raw or compressed video is **UNVERIFIED**, and is confirmed first. The drive's sustained write rate after its cache is unpublished, so it is measured |
| 16 | Analog backup | Analog eye into SpikeGLX | ACCES I/O **USB-AO16-8A** (16-bit, 8 analog outputs, 2 analog inputs) | 1 | [ACCES family page](https://accesio.com/product/usb-ao16-16a/) | 604.00 | **Kept** (PI), the 8A and not the 8E. *Decided* |

#### 7.1.1 The tracker lens: magnification and focal length

**The magnification.**

- **The reference image scale.** The pupil is about 200 px across in OpenIrisDPI's
  tutorial frames (the P10 spike reads semi-axes of 105 × 97 px). At 3.45 µm per pixel, that
  is 0.690 mm on the sensor (arithmetic).
- **The pupil: 3.4 mm, ASSUMED.** This is the PI's working figure, not a measurement on our
  animals. It gives m = 0.690 / 3.4 = **0.203** (arithmetic).
- The result is only as good as that assumption. A 3 mm pupil would give m = 0.23, and a 5 mm
  pupil m = 0.138 (arithmetic).

**The focal length.** By the thin lens, m = f / (u − f), so f = u · m / (1 + m), where u is
the object distance. The extension past infinity focus is Δ = f² / (u − f). Principal-plane
offsets are ignored, and Edmund measures working distance from the lens's front, so each
ring length below is an estimate to within a few millimeters. It is fitted on the bench.

| Working distance u (ASSUMED) | f for m = 0.203 | Lens | m with it | 3.4 mm pupil on the sensor | Δ needed | Δ at the lens's own minimum | Ring |
|---|---|---|---|---|---|---|---|
| 45 cm | 75.9 mm | #74-054, 75 mm | 0.200 | 197 px | 15.0 mm | 13.2 mm (at 500 mm) | about 2 mm |
| 50 cm | 84.4 mm | #74-054, 75 mm | 0.176 | 174 px | 13.2 mm | 13.2 mm | none |
| 57 cm (the paper's) | 96.2 mm | #27-555, 100 mm | 0.213 | 210 px | 21.3 mm | 15.4 mm (at 750 mm) | about 6 mm |
| 60 cm | 101.3 mm | #27-555, 100 mm | 0.200 | 197 px | 20.0 mm | 15.4 mm | about 5 mm |

- **The field at m = 0.2** is 24.8 × 18.6 mm at the eye for the full sensor, and 12.4 × 7.8 mm
  for the 720 × 450 ROI (arithmetic).
- **The ROI can move on the sensor** by 360 px horizontally and 315 px vertically in each
  direction. That is ±6.2 mm and ±5.4 mm at the eye, so fine positioning needs no carriage
  movement (arithmetic).
- **CS against C.** The camera is CS-mount. A C-mount lens needs the 5 mm spacer (row 3).
- **NIR focus.** None of these makers publishes a focus shift at 940 nm, so focus is set under
  the 940 nm light with the filter on.
- **Lens width against the eye spacing.** Both lenses (Ø48 mm and Ø52 mm) are wider than the
  largest eye separation in the drawing, 38 mm. The two cameras therefore cannot sit side by
  side on parallel axes at eye spacing. Each is aimed at its own eye with a small toe-in.
  Arithmetic: with the lens centers 52 mm apart, each axis is 7–11 mm off its eye's line, a
  toe-in of 0.9–1.4° at 45 cm. The toe-in is set once and held (§7.1.3).

**Other makers checked** (read 2026-09-27):

- **Computar.** The M7528-MP (75 mm, MOD 0.3 m, M30.5 × 0.5) and the M7528-MPW3 (MOD 0.4 m,
  M34 × 0.5) are both **discontinued** on Computar's own pages
  ([M7528-MP](https://www.computar.com/products/m7528-mp),
  [M7528-MPW3](https://www.computar.com/products/m7528-mpw3)). Graftek still lists them, with
  a 400–1000 nm range, at $217 and $319.
- **Thorlabs.** The MVL75M23 (75 mm f/2.5, 1.2 m minimum working distance, M34 × 0.5,
  $252.95) and the MVL100M23 (100 mm f/2.8, 2.0 m, M40.5 × 0.5, $246.10) are about $440–510
  cheaper per lens
  ([Thorlabs](https://www.thorlabs.com/camera-lenses-for-machine-vision?pn=MVL75M23)).
  Neither states a NIR coating, and at these distances they need about 10–16 mm of extension
  (arithmetic). They are the value alternative if the NIR coating is not required.
- **Kowa.** The LM75FC24M has a 400–1000 nm coating, a 150 mm MOD and a M34 × 0.5 thread, and
  measures Ø45 × 89 mm, at €966
  ([Kowa](https://www.kowa-lenses.com/LM75FC24M-1.1-75mm-24MP-C-Mount-Lens/12459)). It is a
  1.1" 24 MP lens, far more than this sensor needs.

#### 7.1.2 The per-eye light, its driver, and eye safety

**What was checked for a compact collimated 940 nm source** (the PI asked about Edmund, and
about a smaller LED with a collimator):

- **Edmund Optics.** A search of Edmund's site lists 940 nm bar lights, a ring light, linear
  backlights, a coaxial spot light, and a 6" × 6" collimated backlight, which is far too
  large. Only one compact light was opened: the Advanced Illumination MicroBrite spot light,
  SL223-940IC.
  - It is Ø7.9 × 38.1 mm and is not collimated.
  - Edmund notes that its intensity cannot be controlled ($355;
    [Edmund](https://www.edmundoptics.com/p/ir-940nm-microbrite-led-spot-light/45702/)).
  - **Among what was found, Edmund has nothing compact and collimated with current
    control.**
  - **Rechecked 2026-09-28.** The smallest 940 nm collimated source Edmund lists is Advanced
    Illumination's 2" × 2" collimated backlight,
    [#73-833](https://www.edmundoptics.com/p/2-x-2-940nm-collimated-backlight/56357/): its
    housing is 106.7 × 106.7 × 19.1 mm, it runs in constant mode only, and it costs $670.
- **Thorlabs.** The smaller collimator is the Ø1" SM1U25-B on the reference's own M940L3,
  replacing the Ø2" SM2F. Thorlabs' ready-collimated M940L3-C versions fit microscope ports.
  The M940L3's housing diameter was not read: Thorlabs uses Ø30.5 mm and Ø57.0 mm housings
  (**UNVERIFIED** which).
- **Mightex LCS-0940-02-22.** This is an integrated collimator that any constant-current
  source can drive. Its housing size and price are not published (**UNVERIFIED**).
- **Recommendation: Thorlabs M940L3 + SM1U25-B.** It is the reference's emitter, it runs from
  the LEDD1B, and its price is published. Mightex is the alternative if its housing proves
  smaller.

**The driver.** It is two single-channel LEDD1Bs, one per eye. The alternatives, and how each
enforces a cap, are compared in §7.10.

- Thorlabs' only multi-channel driver with modulation is the
  [DC4100](https://www.thorlabs.com/item/DC4100): four channels with **one** modulation
  input, at $3,354.38.
- Mightex's two-channel
  [SLC-MA02-U](https://www.mightexsystems.com/product/compact-universal-1-and-2-channel-led-controllers/)
  has **no** external trigger.
- Mightex's four-channel
  [SLC-AA04-US](https://www.mightexsystems.com/product/slc-sa-aa-series-universal-four-channel-led-controllers-with-external-triggers/)
  has a trigger per channel, at €1,395.20 and up. It sets its current limit in software from
  0 mA.

**Eye safety** (welfare; kept from the first version):

- **The requirement.**
  - At bring-up, measure the IR at each eye position with a power meter, with each light at
    its set current.
  - Cap the driver current so that exposure stays under the limits for the longest session.
  - Re-check whenever a light, its collimation or its current changes.
- **IEC 62471:2006 was not read.** IEC sells it, so its limit values are **UNVERIFIED** here.
- **ICNIRP 2013** (*Health Physics* 105(1):74–96;
  [PDF](https://www.icnirp.org/cms/upload/publications/ICNIRPVisible_Infrared2013.pdf), read
  2026-09-27) gives these limits:
  - **The cornea and lens, 780 nm–3 µm** (its eqns 20–21):
    - 18 · t^−0.75 kW m⁻² for t under 1000 s;
    - **100 W m⁻² (10 mW cm⁻²) for 1000 s or longer.**
    - A thermal detector read without the guideline's spectral weighting gives a
      conservative value.
  - **The retina, for a near-IR source with a weak visual stimulus** (eqns 8–9): a radiance
    limit that depends on the source's angular size, α.
    - It is computed from the rig's geometry at bring-up, using the typeset equations.
    - The PDF's text layer garbles eqn 9's constant, so it is not quoted here.
- **These limits are for human eyes.** Whether they transfer to macaques is **UNVERIFIED**.
- **The power, as arithmetic.** A uniform Ø25 mm beam (ASSUMED uniform) at 100 W m⁻² carries
  49 mW. Thorlabs rates the M940L3 at 800 mW minimum at 1000 mA, so the light runs far below
  its rating. How far depends on the collimator's capture, which is measured.
- **The cap must be one the operator cannot turn past.**
  - The LEDD1B's trim-pot limit goes down to 200 mA and no lower (Thorlabs).
  - If the safe current is below 200 mA, that limit does not protect the eye. The fix is
    then one of:
    - a fixed attenuator in the light (a neutral-density filter or an aperture); or
    - a driver whose hardware limit reaches the value.
  - §7.10 compares the drivers and recommends the attenuator, sized for the driver's highest
    possible current, behind the LEDD1B's trim-pot limit.

#### 7.1.3 The IPD adjustment system: requirements

- **The range.** The drawing's eye-separation table covers IPD 30–38 mm
  (`2026-08-31-stereoscope-optics-drawing.md` §4). That puts each eye 15–19 mm from the
  midline, ±2 mm about 34 mm.
  - Each carriage needs that ±2 mm, plus margin for a head that is not centered on the frame
    (ASSUMED ±5 mm). That is at least ±7 mm per side.
  - The #16-716's 25 mm of travel covers it, as the DTS25/M's would, and the ROI adds ±6.2 mm
    of fine positioning (§7.1.1).
- **Independent carriages are recommended** over a symmetric slide.
  - The head post sets where the eyes are, and nothing guarantees they are centered on the
    frame.
  - A symmetric slide keeps the pair centered but cannot follow an off-center head. One such
    slide is the igus drylin **SLW-BB-0620**
    ([igus](https://www.igus.com/product/22670)): one left-right screw moves two carriages in
    opposite directions, with an optional clamp. Its price is not published.
  - Which kind is the *PI's call*.
- **Locked after adjustment.** A clamp holds the carriage without relying on the lead screw.
  The #16-716 comes with an external plate lock; the DTS25/M has a locking screw.
- **The cameras and lights ride together.** Each carriage carries its camera and its eye's
  light, so re-positioning for an animal does not change the paper's 10° between them.
- **Rotation stability matters.**
  - DPI cancels head translation, but not camera rotation (PI).
  - A camera roll rotates the P1 − P4 vector. A turned collimated light moves the reflections
    as an eye rotation would (INFERENCE).
  - So the brackets hold angle: stiff sections, short lever arms, and two fasteners or a keyed
    face at each joint, with no single-screw pivots.
  - Edmund publishes no angular deviation for the #16-716 (**UNVERIFIED**). The DTS25/M's is
    ±250 µrad over its travel (Thorlabs).
- **Filament: stiff and creep-resistant.** The recommendation is **carbon-fiber-filled
  high-temperature nylon (PAHT-CF)**, or polycarbonate (PC). **Not PLA.**
  - The reason: a comparison of FDM-printed PLA, PC and PAHT-CF ranked PAHT-CF highest in
    steady-state (stage II) creep resistance, then PC, then PLA. PAHT-CF also had the highest
    flexural modulus (*J. Mater. Eng. Perform.*,
    [doi:10.1007/s11665-024-09144-9](https://link.springer.com/article/10.1007/s11665-024-09144-9),
    abstract read 2026-09-27).
  - Whether the lab's printer can print either is the lab's check.
- **Metal threaded inserts.** Every screwed joint that is adjusted, or that carries a camera
  or a light, goes into a heat-set or press-fit brass insert, never into printed thread.
- **The camera interface** is Teledyne FLIR's Blackfly S (30 mm) 1/4"-20 tripod adapter, bought
  from Edmund as #88-210 (Teledyne's ACC-01-0003), as for C21.

#### 7.1.4 Raw validation video: the arithmetic

8-bit mono, two cameras:

- **At the recording's frame, 720 × 450.** This is the spike's §7b.1 inference from the
  recording's coordinates. 720 × 450 × 1 B × 500 fps = 162.0 MB/s per camera and 324.0 MB/s
  for two. That is 1.17 TB an hour, so 4 TB holds 3.4 h.
- **At full frame, the same rate.** 1440 × 1080 × 1 B × 500 fps = 777.6 MB/s per camera,
  1.56 GB/s for two, and 5.6 TB an hour. The camera cannot do this: FLIR lists 226 fps at
  full frame.
- **At full frame and 226 fps.** 351.5 MB/s per camera and 703.0 MB/s for two. That is
  2.53 TB an hour, so 4 TB holds 1.6 h.

### 7.2 The behavior-camera system (P9)

| # | Role | Requirement | Candidate (maker, model) | Qty | Source, read 2026-09-27 | Price (USD) | PI's decision; status |
|---|---|---|---|---|---|---|---|
| C1 | Cameras | 1–2 on the face (blinks, eyelids, licking) and 1–2 on the body (hands, arms, posture); 200 fps; 8 at most | Teledyne FLIR **BFS-U3-16S2M-CS**: Sony IMX273, 1/2.9", 1440 × 1080, 226 fps, 3.45 µm, CS-mount, USB 3.1 Gen 1, 3 W maximum. Bought from Edmund as **#11-507** | 2–4 (8 max) | [Edmund #11-507](https://www.edmundoptics.com/p/bfs-u3-16s2m-cs-usb3-blackflyreg-s-monochrome-camera/40163/) (read 2026-09-28; 14 in stock); [Teledyne](https://www.teledynevisionsolutions.com/products/blackfly-s-usb3/?model=BFS-U3-16S2M-CS&vertical=machine%20vision&segment=iis) | 556.50 each (Edmund and Teledyne) | **Kept.** *Decided*. **Source: Edmund**, the same part at the same price |
| C2 | Face lens | About 15 cm of field at about 40 cm (ASSUMED), so f ≈ 12.8 mm (§7.3). NIR-coated; a filter thread of its own | Edmund Optics **#27-554**, 12 mm C VIS-NIR: 425–1000 nm BBAR; 2/3"; f/1.8–16; 100 mm–∞; filter thread **M25.5 × 0.50**; Ø32 × 27.9 mm | 1–2 | [Edmund](https://www.edmundoptics.com/p/12mm-c-vis-nir-series-fixed-focal-length-lens/53828/) | 635.00 (20+ in stock) | **Fixed lens now** (PI). *Decided.* Edmund was the fallback, and it is the best-value NIR-coated lens found (§7.3) |
| C3 | Body lens | About 60 cm of field at about 80 cm (ASSUMED), so f ≈ 6.6 mm (§7.3). NIR-coated; a filter thread of its own | Edmund Optics **#39-939**, 6 mm C VIS-NIR: the same coating; up to 1/1.8"; f/1.4–16; 75 mm–∞; distortion up to −6.84%; Ø36 × 48.9 mm. It has a **front thread, M34 × 0.5 (female)**. Its listed filter thread is M43 × 0.50, through adapter #85-308 ("Required") | 1–2 | [Edmund](https://www.edmundoptics.com/p/6mm-c-series-vis-nir-fixed-focal-length-lens/40554/) | 725.00 ("contact us") | **Fixed lens now** (PI). *Decided*. The filter goes in the front M34 thread, with no adapter. Whether a filter there touches the front glass or vignettes is **UNVERIFIED**: ask Edmund before buying |
| C4 | Filter adapter | — | Edmund #85-308 | — | — | — | **Dropped** (PI: no adapters) |
| C5 | 850 ± 25 nm band-pass filter | Passes the behavior lamps and rejects the tracker's 940 nm; threads straight onto the lens | MidOpt **BN850**: useful range 840–865 nm, FWHM 52 nm, peak transmission 85% or more, tolerance ±10 nm. **BN850-25.5** on the 12 mm; **BN850-34** in the 6 mm's front thread. MidOpt's BP850 is not used: its FWHM is 160 nm | 1 per camera | [MidOpt BN850](https://midopt.com/filters/bn850/); [MidOpt BP850](https://midopt.com/filters/bp850/); Graftek [BN850-25.5](https://graftek.com/product/bn850-25-5/), [BN850-34](https://graftek.com/product/bn850-34/) | 168.00 / 197.00 each (lead time on request) | **Kept, at 850 nm** (PI's bands). *Decided*. **Edmund has nothing suitable** (read 2026-09-28): its site finds no "MidOpt" or "BN850". Its front-threaded 850 nm filters have a 160 nm FWHM ([#21-748](https://www.edmundoptics.com/p/ir-m255-x-050-mounted-machine-vision-filter/48643/), M25.5, $141; [#21-714](https://www.edmundoptics.com/p/ir-m34-x-050-mounted-machine-vision-filter/48625/), M34, $166), as the BP850 does. Its TECHSPEC high-performance NIR filter is 880 nm with a 135 nm FWHM. Their half-maximum edges sit at 930 and 947.5 nm (arithmetic), too near 940 nm to reject the tracker. A behind-the-lens Edmund filter needs the PI (§7.11) |
| C6 | CS-to-C spacer | A C-mount lens on the CS body | Edmund **#03-618** (§7.1 row 3). Alternative: Teledyne **ACC-01-5004** direct | 1 per camera | [#03-618](https://www.edmundoptics.com/p/5mm-spacer-to-convert-cs-mount-cameras-to-c-mount/90/) (read 2026-09-28); [Teledyne](https://www.teledynevisionsolutions.com/products/cs-to-c-mount-5mm-spacer-adapter/) | 29.00 (Teledyne direct: 11.80) | **Kept.** *Decided*. **Swapped to Edmund** (PI preference), at $17.20 more each |
| C7 | USB host card | One controller per camera (P9 §2). Four cameras are 1.24 GB/s through one PCIe 2.0 x4 card (arithmetic) | Teledyne **ACC-01-1205** (§7.1 row 14) | 1 (2 for 8 cameras) | [card page](https://www.teledynevisionsolutions.com/products/usb-3.1-host-controller-card?model=ACC-01-1205&vertical=machine%20vision&segment=iis) | 148.00 | **Kept.** *Decided.* Whether one card sustains four cameras is P9 bring-up check 2. Edmund has nothing suitable: its cards are PCIe 2.0 x1 (§7.1 row 14) |
| C8 | USB cables | Passive runs of 5 m or less (Teledyne); active beyond that | Teledyne FLIR's locking USB 3.1 cables, bought from Edmund: **#86-770** (3 m) or **#88-058** (5 m). Teledyne's numbers are **ACC-01-2300** and **ACC-01-2301**. Beyond 5 m: Newnex **FIRENEX-ULS-08 / -12 / -16** (Edmund's longer cables do not say they are active, §7.1 row 10) | 1 per camera | [#86-770](https://www.edmundoptics.com/p/usb-30-locking-cable-3m-length/29172/), [#88-058](https://www.edmundoptics.com/p/usb-30-locking-cable-5m/30343/) (read 2026-09-28); [Teledyne](https://www.teledynevisionsolutions.com/products/usb-3.1-locking-cable); [Newnex](https://newnex.com/usb-3-active-cable-a-to-micro-b.php) | 41.00 / 61.00 (Teledyne direct: 24.60 / 37.50); Newnex's price is not published | **Waits** (PI) on the layout and a possible passthrough panel (§7.8). **Source: Edmund**, the same Teledyne cables |
| C9 | GPIO cables | Camera GPIO to the fan-out board and the sync box | Edmund **#88-064** (1 m) or **#88-065** (4.5 m), as §7.1 row 11. Teledyne's numbers are **ACC-01-3009** and **ACC-01-3010** | 1 per camera | [#88-064](https://www.edmundoptics.com/p/blackflyreg-6-pin-gpio-hirose-connector-1m-cable/30349/), [#88-065](https://www.edmundoptics.com/p/blackflyreg-6-pin-gpio-hirose-connector-45m-cable/30350/) (read 2026-09-28); [Teledyne](https://www.teledynevisionsolutions.com/products/hirose-hr10-6-pin-circular-connector/) | 38.00 / 71.00 (Teledyne direct: 37.50 / 43.90) | **Waits** (PI), as C8. **Source: Edmund**, the same Teledyne cables |
| C10 | Trigger fan-out board | The primary's exposure drives up to 7 secondaries' opto inputs (3.5–7 mA at 2.6 V or more), plus the two lamps' strobe inputs | **Custom** (§7.4): wl-sync's comparator front end, then one SN74AHCT541 channel and one 47 Ω series resistor per secondary, plus a lamp-strobe stage per lamp, checked against the LM75-850-W's strobe input | 1 | [FLIR I/O table](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/InputOutputControl.htm); wl-sync at `92714ce`; [TI SN74AHCT541, SCLS269Q](https://www.ti.com/lit/ds/symlink/sn74ahct541.pdf); [SVL LM75 datasheet](https://smartvisionlights.com/wp-content/uploads/LM75_Datasheet.pdf) | parts only, not priced | **Custom board after all** (PI, 2026-09-27), not the PRL-4110 ($1,850 with its supply). **Needs a design check** (§7.4). *Waits on* measuring the primary's Line 2 low level |
| C11 | Behavior-group sync wiring | The primary samples the barcode every frame. The group's ExposureActive goes to GPIO27 (P9 §2; S3 §8) | Barcode from wl-sync's `CAM_SYNC_BEH1` BNC into the primary's Line 0. The primary's Line 1 (opto output) goes to wl-sync J6B, which is GPIO27. The primary's Line 2 goes to the fan-out board's input, pulled up to 5 V on the board (§7.4) | wiring | [FLIR I/O table](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/InputOutputControl.htm) | — | **Kept.** *Decided.* **Line 3 must not take the barcode**: its input high is 3.6 V at most, and the barcode is 5 V logic. Driving ExposureActive on Lines 1 and 2 at once is **UNVERIFIED** in Spinnaker |
| C12 | Camera box: CPU | Acquisition and file writing for 4–8 streams | AMD **Ryzen 7 9700X**: 8 cores and 16 threads; 3.8 GHz base, 5.5 GHz boost; 65 W; AM5; PCIe 5.0, 28 lanes (24 usable); DDR5 to DDR5-5600 (2 × 1R); no cooler in the box, and AMD recommends a premium air cooler | 1 | [AMD](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-7-9700x.html); [Newegg](https://www.newegg.com/amd-ryzen-7-9000-series-ryzen-7-9700x-granite-ridge-socket-am5-desktop-cpu-processor/p/N82E16819113843) | 339.00 (Newegg, new) | **AMD** (PI). *Decided* |
| C13 | Motherboard | The GPU, two x4 USB cards and two NVMe drives, with no slot disabling another. ATX, for a rack case | ASUS **ProArt X870E-Creator WiFi**. From the CPU: 2 × PCIe 5.0 x16 slots (x16, x8/x8, or x8/x4/x4 with M.2_2) and M.2_1 and M.2_2 (PCIe 5.0 x4). From the chipset: a PCIe 4.0 x16 slot running at x4, and M.2_3 and M.2_4 (PCIe 4.0 x4). ATX, 30.5 × 24.4 cm; 10 GbE and 2.5 GbE | 1 | [ASUS spec](https://www.asus.com/motherboards-components/motherboards/proart/proart-x870e-creator-wifi/techspec/); [ASUS US](https://www.asus.com/us/motherboards-components/motherboards/proart/proart-x870e-creator-wifi/) | 549.99 (ASUS Store, showing "Notify me") | *Decided* for the list. The slot map is in §7.6. The 10 GbE is for the copy to wl-nas |
| C14 | RAM | Acquisition buffers; no swapping; runs on AM5 | Corsair **Vengeance 32 GB (2 × 16 GB) DDR5-4800 CL40**, CMK32GX5M2A4800C40 | 1 kit | [Corsair DDR5 page](https://www.corsair.com/us/en/c/memory/ddr5-ram) | 399.99 (sale; list 505.99) | **Kept** (PI). It is a DDR5-4800 kit, under the 9700X's listed DDR5-5600. Whether it is on the board's qualified list is **UNVERIFIED** |
| C15 | GPU | Two or more NVENC, within the 12-session cap (§7.5) | NVIDIA **GeForce RTX 5070 Ti**: 2 × ninth-generation NVENC; 300 W; NVIDIA asks for 750 W of system power | 1 | [NVIDIA 5070 family](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/); [NVIDIA matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new) | from 749 (NVIDIA's "starting at"; partner boards vary) | **Kept, pending the encode measurement** (PI). For the rack case, a board of NVIDIA's SFF-Ready size (§7.6) |
| C16 | Video NVMe | 4 cameras for 12 h at an ASSUMED 10:1 is 5.37 TB (§7.6) | 2 × Samsung **990 PRO 4 TB** (MZ-V9P4T0B/AM), 8 TB in all | 2 | [Samsung](https://www.samsung.com/us/memory-storage/nvme-ssd/990-pro-pcie-4-0-nvme-ssd-4tb-sku-mz-v9p4t0b-am/) | 1,099.99 each | **Two drives, decided** (PI). How many hours they hold *waits on* P9's measured bitrate |
| C17 | Power supply | 750 W or more (NVIDIA) | Seasonic **CORE GX ATX 3.1 (2024), 850 W**: 80 PLUS Gold; fully modular; a native 12V-2x6 cable (up to 600 W); ATX 3.1 and PCIe 5.1; 140 × 150 × 86 mm; 7-year warranty. Retailers name it **CORE GX-850 ATX3** | 1 | [Seasonic](https://seasonic.com/core-gx-atx-3-2024/); [Newegg (the 1000 W sibling)](https://www.newegg.com/seasonic-usa-atx-3-1-1000-w-80-plus-gold-certified-power-supply-core-gx-1000-atx3/p/N82E16817151283) | **UNVERIFIED**. Newegg offered the 750 W at 114.99 and the 1000 W at 159.99, not the 850 W. Micro Center and B&H served bot checks | **Seasonic, decided** (PI). The model name is "CORE GX ATX 3.1" at 850 W. "Core" is the series and "Gold" its rating; no model is called "Core Gold" |
| C18 | Case | Rack-mount | not chosen; constraints in §7.6 | 1 | — | — | **Rack-mount** (PI). The model is the *PI's call* |
| C19 | CPU cooler | AM5; its height fits the case | a Noctua, not chosen; constraints in §7.6 | 1 | — | — | **Noctua** (PI), chosen with the case |
| C20 | Behavior lamps | **Required**, 850 nm, one per view (face, body). A diffuse flood, placed outside the animal's view. A visible-cut filter on each emitter. A driver with a strobe input, so the lamps flash only during behavior exposures (§7.7) | Smart Vision Lights **LM75-850-W**: 850 nm; 80° lens; 8 LEDs; 80 × 34 × 26 mm; a built-in Multi-Drive driver; PNP (above 4 V) or NPN strobe input; 24 VDC; 6.6 W maximum continuous; IEC 62471 Exempt Group at 850 nm (SVL's datasheet). Bought from Edmund as **#90-436**, which lists a 71.00 × 25.5 mm active area. Add a MidOpt **LP830** long-pass (50% cut-on at 830 nm, useful range 845–1100 nm), cut to the emitter window, and Edmund's **#27-110** light-diffusing film, cut to the same window. Both are held in the lamp's bracket (§7.7) | 2 (1 per view) | [Edmund #90-436](https://www.edmundoptics.com/p/smart-vision-lights-75mm-850nm-bar-light/57261/), [#27-110](https://www.edmundoptics.com/p/75-x-75mm-light-diffusing-film/52184/) (read 2026-09-28); [SVL LM75](https://smartvisionlights.com/products/lm75/); [SVL datasheet, rev. 09/25/26](https://smartvisionlights.com/wp-content/uploads/LM75_Datasheet.pdf); [Machine Vision Direct](https://machinevisiondirect.com/products/lm75-850-w); [MidOpt LP830](https://midopt.com/filters/lp830/) | 510.00 each (Edmund, 1 in stock; Machine Vision Direct: 511.00). LP830 is priced by quote (**UNVERIFIED**). One 75 × 75 mm film, 22.75, gives both lamps' pieces (arithmetic). The 24 V supply is not chosen (§7.7) | **Required** (PI). *Decided* for the list. The darkness check is required (§7.7). **Lamp: source Edmund**, the same part. **Diffuser: Edmund** (it was unchosen). **LP830: Edmund has nothing suitable**: its site finds no "LP830", and its SCHOTT RG830 ([#14-536](https://www.edmundoptics.com/p/schott-rg830-50mm-sq-2mm-thick-colored-glass-longpass-filter/42561/), 50 × 50 × 2 mm, $92.50) shares the 830 nm cut-on but lists its passband from 950 nm, so it would dim the 850 nm lamp more than LP830 (INFERENCE), and it is smaller than the window |
| C21 | Camera mounts | Face and body views from several angles (3D) | 3D-printed brackets on the existing frame, with the filament and insert rules of §7.1.3. Per camera, Teledyne FLIR's Blackfly S (30 mm) 1/4"-20 tripod adapter is the interface, bought from Edmund as **#88-210** (Teledyne's **ACC-01-0003**) | 1 per camera | [#88-210](https://www.edmundoptics.com/p/blackflyreg-frac14-20-tripod-adapter/30486/) (read 2026-09-28); [Teledyne](https://www.teledynevisionsolutions.com/products/tripod-adapter-for-bfs-30mm-bfly-cmln-cm3-ffmv-fl2-fl3-fmvu/) | 18.00 each (Teledyne direct: 11.80) | **Changed** (PI) from 80/20 rails and ball heads. The positions *wait on* rig geometry. **Source: Edmund**, at $6.20 more each. Edmund's mounts and posts are not needed: the brackets are printed (PI) |
| C22 | Interim offload | Where the video goes before wl-nas | — | — | — | — | **Wait for wl-nas** (PI). The cameras do not go into regular use until it exists. Until then, video stays on the box for bring-up only, and is never deleted before a checksummed copy exists (P9 §5) |

### 7.3 Lenses: the focal lengths

- **The sensor.** FLIR lists the IMX273 as 1/2.9". Sony gives "Diagonal 6.3 mm (Type 1/2.9)"
  for its 1456 × 1088 recording pixels
  ([Sony flyer](https://www.sony-semicon.com/files/62/flyer_industry/IMX273_287_296_297_Flyer.pdf)).
  The camera's 1440 × 1080 at 3.45 µm is 4.968 × 3.726 mm, a 6.21 mm diagonal (arithmetic).
- **The relation** is the thin lens: magnification m = sensor width / field width, and
  f = u · m / (1 + m) at subject distance u. It ignores the principal-plane offsets Edmund
  lists, so the fields are approximate.

| View | Distance u (ASSUMED) | Field width (ASSUMED) | f needed | Chosen | Field with the chosen lens (W × H) | Object scale |
|---|---|---|---|---|---|---|
| Face (eyes, mouth) | 40 cm | 15 cm | 12.8 mm | **12 mm** | 16.1 × 12.0 cm | 0.11 mm/px |
| Body (hands, arms, posture) | 80 cm | 60 cm | 6.6 mm | **6 mm** | 65.7 × 49.3 cm | 0.46 mm/px |

- **Why these focal lengths.** Each is slightly shorter than the computed one, so its field is
  at least the assumed one. The image circles (11 mm and 9 mm) cover the sensor's 6.21 mm
  diagonal.
- **Best value, NIR-coated: Edmund's C VIS-NIR series is the pick** among lenses whose maker
  states a NIR coating. The others checked (read 2026-09-27):
  - **Kowa.**
    - The LM12JC (12 mm, f/1.4, M27 × 0.5) is $292 and sold out. Kowa's US page gives its
      coating as "Visible (400nm - 800nm)" and its EU page as "Peak Coating (400nm –
      1000nm)". The US page rates it for 5.0 µm pixels, against the camera's 3.45 µm. The
      LM6JC is also "Visible (400nm - 800nm)", at $292, sold out
      ([LM12JC](https://www.kowavision.com/products/lm12jc),
      [EU](https://www.kowa-lenses.com/LM12JC-2-3-12mm-MP-C-Mount-Lens/10223),
      [LM6JC](https://www.kowavision.com/products/lm6jc)).
    - The LM12JC10M has a VIS-to-NIR broadband coating and a M25.5 × 0.5 thread, at $1,394,
      sold out ([Kowa](https://www.kowavision.com/products/lm12jc10m)).
    - The LM12HC is visible only.
  - **Computar.** Its "IR Corrected" MPYIR series and its MP2 series are discontinued
    ([MPYIR](https://www.computar.com/series/mpyir), [MP2](https://www.computar.com/series/mp2)).
  - **Fujinon.** The HF-XA-5M series page makes no NIR statement. The HF12XA-5M has a
    M25.5 × 0.5 thread and the HF6XA-5M a M37.5 × 0.5 thread
    ([Fujifilm](https://www.fujifilm.com/us/en/business/optical-devices/mvlens/hf-xa-5m-series)).
  - **No lens with a built-in band-pass filter was found.**
- **NIR focus.** No focus-shift figure at 850 nm is published, so focus is set under the lamps
  with the filter on.
- **The 6 mm lens and a band-pass.** An interference band-pass shifts toward shorter
  wavelengths off-axis. The corners of the 6 mm lens's wide field may therefore darken
  (INFERENCE). MidOpt says its BN940's narrow-band design is less sensitive to that shift; its
  BN850 page makes no such claim. This is checked at bring-up.
- **Rerun when the geometry is set.** Change u and the field, and recompute f.

### 7.4 The trigger fan-out board (custom; needs a design check)

**A custom board after all** (PI, 2026-09-27), not the PRL-4110 ($1,850 with its supply). Its
design is the first version's (§7.4 at `a898480`), with lamp-strobe outputs added. It **needs
a design check**. The wiring findings of the off-the-shelf pass are kept below.

**FLIR's figures for the BFS-U3-16S2** come from its
[Input/Output Control](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/InputOutputControl.htm)
and
[GPIO Electrical Characteristics](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/ElectricalGPIO.htm)
pages. They were measured with the opto I/O at 5 V / 1 kΩ and the non-isolated output at
5 V / 330 Ω.

| Line | Kind | FLIR's figures |
|---|---|---|
| 0 | Opto-isolated input | Low 0–1.4 V; high 2.6–30 V; 3.5–7 mA; propagation up to 18 µs (low to high) and 9 µs (high to low) |
| 1 | Opto-isolated output | Open collector, so it needs a pull-up; up to 25 mA and 24 V; propagation up to 36 µs and 18 µs. At 5 V / 1.0 kΩ its low is 0.92 V unloaded and 0.86 V loaded, "for reference only" |
| 2 | Non-isolated input/output | Open drain; sinks up to 25 mA; up to 24 V; input high 2.6–24 V; propagation up to 1 µs. **Its output low level is not published** |
| 3 | Non-isolated input | High 2.6–3.6 V |

**FLIR's own reference** is its
[synchronized-capture application note](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/configuring-synchronized-capture-with-multiple-cameras/)
(read 2026-09-27):

- The primary's opto output (pin 4, Line 1) is pulled up by 10 kΩ to the primary's own
  3.3 V (pin 3).
- It drives each secondary's **pin 1, Line 3**, the non-isolated input, with the grounds
  joined.
- FLIR says any hardware trigger giving a 3.3 or 5 V square wave can stand in for the primary.

**The wiring findings** (kept from the off-the-shelf pass):

- **Secondaries on Line 0.** A 5 V board must not drive Line 3, because Line 3's high is
  3.6 V at most. It drives each secondary's **Line 0**, the opto input, which also keeps each
  secondary isolated.
- **The primary feeds the board from Line 2** (open drain), pulled up to 5 V on the board.
  - Line 1 stays wl-sync's (GPIO27). Its front end supplies its own pull-up, and a second
    pull-up on the same output would move FLIR's operating point.
  - **Line 2's low level is unpublished, so it is measured at bring-up** before the board is
    trusted. It must sit well under the comparator's 2.50 V threshold.

**The circuit**, built from stages wl-sync already uses (wl-sync at `92714ce`):

1. **Input.** Line 2 into a copy of wl-sync's frame-time front end
   (`hardware/breakout/frame-time-inputs.md`): 100 Ω, a BAT54S clamp, and an LM339 on +12 V
   with a 2.50 V threshold and about 33 mV of hysteresis. It is a comparator because Line 2's
   low level is unpublished; a TTL input's margin would be a coincidence.
2. **Secondaries.** One SN74AHCT541: one channel and one 47 Ω series resistor per secondary,
   as wl-sync drives its camera BNCs (its finding F4). Seven secondaries and a monitor output
   fill its eight channels. Checked against TI's figures (SCLS269Q, rev. August 2024, read
   2026-09-27) as arithmetic:
   - **Output high.** TI guarantees VOH ≥ 3.8 V at 8 mA with VCC = 4.5 V, over temperature.
     Less 47 Ω × 7 mA = 0.33 V, Line 0 sees at least 3.47 V, above its 2.6 V high. This
     settles the first version's open question.
   - **Current.** Seven loads at 7 mA are 49 mA: each under the recommended 8 mA per output,
     and together inside the 75 mA package limit (wl-sync `datasheet-params.toml`,
     `[sn74ahct541]`).
3. **Lamp strobes, checked against the LM75-850-W** (SVL datasheet, rev. 09/25/26). Its PNP
   input activates above +4 V (24 V at most) and draws 2.8 mA at 4 V, 8.8 mA at 12 V and
   17.6 mA at 24 V. Its NPN input activates below 1 V and sinks 14.4 mA at 0 V. One or the
   other, not both. **Neither is safely driven by a '541 channel** (arithmetic):
   - **PNP.** TI guarantees VOH ≥ 4.4 V only at 50 µA, and ≥ 3.8 V at 8 mA (VCC = 4.5 V).
     Nothing between is guaranteed at about 3 mA, and the 47 Ω takes another 0.13 V. So
     "above 4 V" is not guaranteed. On a 5.0 V rail it is likely, but unpublished (INFERENCE).
   - **NPN.** 14.4 mA is over the 8 mA per output. Through 47 Ω it drops 0.68 V before the
     output's own low (0.44 V at 8 mA), so the input sits above 1 V.
   - So **each lamp gets its own stage**: a high-side switch driving the PNP input from a
     supply well above 4 V, or an open-collector or open-drain transistor sinking the NPN
     input. Which, and its part, is the design check's.
   - The lamp's trigger returns to its own 24 V supply's ground, so either stage joins that
     ground to the board's unless it is optically isolated (INFERENCE). The no-added-noise
     check (P9 §6, check 4) decides whether that matters.
4. **Power and ground.** +12 V in for the LM339, and +5 V regulated on the board for the
   pull-up and the buffer. The board's ground is the primary's camera ground (pin 6) and each
   secondary's opto ground (pin 5).
5. **Polarity.** Which edge starts a secondary's exposure is set in the camera file (P9 §3)
   and verified at bring-up.

**The design check must settle:**

- the lamp stage, its part and its grounding;
- Line 2's measured low level against the 2.50 V threshold;
- whether Lines 1 and 2 can both carry ExposureActive (C11; **UNVERIFIED** in Spinnaker);
- the secondaries' trigger latency, which FLIR does not publish. The primary-to-secondary
  exposure skew is measured with every camera imaging one LED pulse;
- the connectors and the enclosure.

**Not chosen** (the off-the-shelf pass): the Pulse Research Lab
[PRL-4110](https://www.pulseresearchlab.com/products/prl-4110), a 1:10 TTL fan-out with
back-terminated BNC outputs, 9 ns typical delay, $1,850 with its supply; and the
[ESPER TriggerBox](https://www.esperhq.com/product/multiple-camera-trigger-triggerbox/),
6 outputs per unit on 3.5 mm jacks that do not lock, £220 before VAT.

**For wl-sync (an ask, not a change here).** Its `[flir_bfs_gpio]` pins the BFS-U3-200S6
page's 0.87 V low. The 16S2 page gives 0.92 V unloaded and 0.86 V loaded at the same
5 V / 1 kΩ. Its 2.50 V threshold still leaves 1.58 V of low margin, so nothing breaks.

### 7.5 NVIDIA's session limit and the encoder

**The limit.**

- NVIDIA's [support matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new)
  lists "Max # of concurrent sessions" as **12** for the GeForce RTX 50-series boards.
- It lists **2 NVENC** on the RTX 5070 Ti and 5080, 3 on the 5090, and 1 on the 5070 and
  5060 Ti.
- The [NVENC application note, SDK 13.1](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/nvenc-application-note/index.html)
  says that on non-qualified (GeForce) GPUs the limit is **12 concurrent sessions per
  system**, across all such cards. The
  [13.0 note](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvenc-application-note/index.html)
  said 8.
- No page read lists monochrome (4:0:0) input.

**What it means:**

- **4 cameras:** 4 sessions of 12.
- **8 cameras:** 8 of 12, with 4 spare. Under the older cap of 8 there would be none.
- **The preview** (P9 §4) must not open NVENC sessions of its own: 8 recordings and 8
  preview encodes would be 16.
- **The driver** enforces the cap, so bring-up confirms it by opening sessions until one is
  refused.

**The throughput.** NVIDIA publishes indicative frame rates **per NVENC**:

- at 1920 × 1080, 4:2:0, 8-bit;
- measured on an RTX 5070 Ti at its highest video clocks, on Windows 11 with SDK 13.1;
- to be multiplied by the NVENC count for concurrent sessions.

The demand, as arithmetic:

- 4 cameras at 1440 × 1080 and 200 fps are 800 frames a second. By pixel count that is 600
  frames of 1080p (the scaling is ASSUMED linear).
- 8 cameras are 1,200 frames of 1080p.

| Preset (NVIDIA's HQ tuning) | Per NVENC (1080p fps) | × 2 NVENC | 4 cameras (600) | 8 cameras (1,200) |
|---|---|---|---|---|
| HEVC P1 | 1,119 | 2,238 | fits | fits |
| HEVC P3 | 947 | 1,894 | fits | fits |
| HEVC P5 | 521 | 1,042 | fits | **does not** |
| HEVC P7 | 181 | 362 | **does not** | **does not** |
| AV1 P5 | 552 | 1,104 | fits | **does not** |

**Reading the table:**

- By NVIDIA's own figures, one NVENC (the 5070 or 5060 Ti) carries 4 cameras only at HEVC
  P3 or faster. So the RTX 5070 Ti is the cheapest GeForce listed with two NVENC.
- **The throughput for our input is UNVERIFIED**: mono, 1440 × 1080, at whichever preset
  proves visually lossless on our video. P9 requires measuring it on the box: 8 streams
  for 12 hours (bring-up check 2).

### 7.6 The camera box: AMD, rack-mounted, and the budget

**Storage: the arithmetic.**

- **Raw.** 1440 × 1080 × 1 B × 200 fps = 311.04 MB/s per camera. That is 1.244 GB/s for 4
  cameras and 2.488 GB/s for 8.
- **ASSUMED compression 10:1.** This is a round number, not a measurement and not a
  published figure. P9 §5 requires the measured bitrate.

| Cameras | 5:1 | **10:1 (ASSUMED)** | 20:1 |
|---|---|---|---|
| 4, for 12 h (43,200 s) | 10.75 TB | **5.37 TB** (124.4 MB/s) | 2.69 TB |
| 8, for 12 h | 21.50 TB | 10.75 TB | 5.37 TB |

- **Capacity.** 8 TB holds a 12-hour, 4-camera session at any ratio of 6.7:1 or better.
- **Endurance.** Samsung lists 2,400 TBW per drive, so a 5.37 TB session is about 0.1% of
  the pair's 4,800 TBW.
- **Sustained write.** Samsung publishes a sequential write figure, not a sustained rate
  after the cache. 124 MB/s (or 249 MB/s for 8 cameras) is checked in bring-up check 2.

**The slot map** (ProArt X870E-Creator WiFi, from ASUS's spec page):

- **GPU** in PCIEX16(G5)_1. It runs at x8 once slot 2 is used.
- **USB card 1** in PCIEX16(G5)_2, at x8, or at x4 if M.2_2 is used. Either is more than the
  card's PCIe 2.0 x4.
- **USB card 2** (for 8 cameras) in the chipset's x16 slot, at x4. ASUS lists no sharing for
  that slot.
- **NVMe 1** in M.2_1, from the CPU. **NVMe 2** in M.2_3 or M.2_4, from the chipset. M.2_2 is
  left empty.
- **No slot disables another** in this map.
- **Physical spacing is UNVERIFIED.** A GPU 2.5 slots thick must not cover slot 2; this is read
  from the board's manual before buying.
- **Every camera is on an ACC-01-1205**, and none is on the board's own USB. The second card
  shares the chipset's link to the CPU with NVMe 2 and the network. That load is part of
  bring-up check 2.
- **An alternative board: ASUS ProArt B650-Creator**
  ([ASUS spec](https://www.asus.com/motherboards-components/motherboards/proart/proart-b650-creator/techspec/)).
  - It has 2 × PCIe 4.0 x16 from the CPU (x16 or x8/x8), and M.2_1 and M.2_2 from the CPU.
  - Its chipset x16 slot runs at x4 and is **disabled when M.2_3 runs at x4**.
  - So the same map works with M.2_3 empty.
  - It has 2.5 GbE only, and ASUS's US page showed no price.

**Teledyne's guidance on AMD hosts: none found.**

- These were read:
  - the ACC-01-1205 page: PCIe 2.0 x4, four Fresco FL1100 controllers;
  - the
    [USB 3.1 Multiple Camera Setup](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/usb-3.1-multiple-camera-setup/)
    note. Its test systems are all Intel, and it puts effective USB 3.1 bandwidth at about
    450 MB/s.
- The "Recommended USB 3.1 System Components" note returned HTTP 500 from
  teledynevisionsolutions.com and 404 from its FLIR mirror.
- So an AMD host is **UNVERIFIED** for these cameras. Bring-up check 2 (8 cameras for 12 h
  with no drops) is what verifies it.

**PCIe ASPM goes on the bring-up list** (PI), for the camera box and the tracker PC.

- ASPM is disabled in the board's firmware for the USB cards' slots, and read back from Linux
  for each device.
- The Linux kernel's `pcie_aspm=off` does **not** disable ASPM. It leaves whatever the
  firmware configured unchanged
  ([kernel parameters](https://www.kernel.org/doc/Documentation/admin-guide/kernel-parameters.txt),
  read 2026-09-27).
- Where the ASUS firmware exposes the setting is **UNVERIFIED**.

**The rack case and the cooler: the constraints.** Both are the PI's call, chosen together.

- **The board** is ATX, 30.5 × 24.4 cm.
- **The power supply** is ATX, 140 mm deep (Seasonic).
- **The GPU's length and height.**
  - Take an RTX 5070 Ti that meets NVIDIA's
    [SFF-Ready](https://www.nvidia.com/en-us/geforce/news/small-form-factor-sff-ready/) size:
    304 mm long at most, 151 mm tall at most including the power cable's bend radius, and
    2.5 slots at most.
  - Which partner cards meet it is **UNVERIFIED**.
- **Three cards** fit: the GPU and two USB cards, with the spacing above.
- **The cooler's height** is set by the case maker's stated limit, not by a rule per rack
  unit.
  - One example that meets every constraint here is the Sliger **CX4170a**, a 17"-deep 4U
    ([Sliger](https://www.sliger.com/products/cx4170a)). It takes ATX to EATX boards, GPUs up to
    375 mm long and 158 mm tall, air coolers up to 153 mm, and an ATX power supply. It has
    room for 7 × 120 mm fans, none included. Its price was not read.
  - For a shorter case, Noctua markets the 110 mm **NH-D9L** as fully 3U compliant
    ([Noctua](https://www.noctua.at/en/products/nh-d9l)). Its AM5 fit was not read
    (**UNVERIFIED**).
  - The 9700X is 65 W. AMD recommends a premium air cooler.
- **Airflow** runs front to back through the rack, past the GPU and both USB cards. The case's
  fans are bought with it.

**The camera box**, 4 cameras:

| Item | Part | Price (USD) |
|---|---|---|
| CPU | AMD Ryzen 7 9700X | 339.00 |
| Motherboard | ASUS ProArt X870E-Creator WiFi | 549.99 |
| RAM | Corsair CMK32GX5M2A4800C40, 32 GB | 399.99 |
| GPU | NVIDIA GeForce RTX 5070 Ti | 749.00 |
| Video NVMe | 2 × Samsung 990 PRO 4 TB | 2,199.98 |
| USB card | Teledyne ACC-01-1205 | 148.00 |
| **Priced subtotal** | | **4,385.96** |
| Power supply | Seasonic CORE GX ATX 3.1, 850 W | **UNVERIFIED** (its 750 W and 1000 W siblings were 114.99 and 159.99) |
| Case | rack-mount, not chosen | — |
| CPU cooler | Noctua, not chosen | — |

**Against the targets** (arithmetic):

- The priced subtotal is **$385.96 over the ~$4,000 target** before the power supply, case and
  cooler.
- The PI accepted about $4,690. That leaves about **$304** for those three.
- If the power supply costs what its siblings do, $144–189 is left for a rack case and a
  cooler. That is likely too little: no rack-case price was read, so this is an INFERENCE.
  **Expect the total to pass $4,690.**
- **The PI accepts a modest overrun** of the camera-box budget (2026-09-27). The rack case
  and the cooler are still chosen with cost in view; "modest" has no number.
- **Against the first version** ($4,686.93): the CPU is $65.00 cheaper and the board $60.00
  dearer. The power supply, case and cooler are replaced by rack-fit parts.
- **Eight cameras** add a second ACC-01-1205 ($148) in the chipset slot, and at 10:1 another
  8 TB.
- **Outside the budget:** the cameras, lenses, filters, lamps, cables and the fan-out board. So
  is a separate OS drive: the OS shares drive 1 here.
- **Not sized here:** P10's tracker running on this box later (the spike's §9 item 7).
- **The Edmund pass changes nothing here** (§7.11): every part it moved is outside this budget.

### 7.7 The behavior lamps (850 nm)

- **What they are** (PI): one per view (face and body), 850 nm, a diffuse flood, and outside
  the animal's view.
- **The pick: Smart Vision Lights LM75-850-W** (C20), bought from Edmund as #90-436. It has a
  built-in driver, so there is no separate driver to buy. From SVL's datasheet (rev. 09/25/26):
  - **Continuous-mode wiring**:
    - the light follows its trigger for as long as the trigger is held, from 30 µs with no
      upper limit;
    - 10 µs latency;
    - 275 mA at most at 24 VDC ±5%.
  - **OverDrive** is brighter, but its duty cycle is 10% at most and its strobe 50 ms at most.
    At 200 fps that allows exposures of 0.5 ms or less (arithmetic). **Use continuous-mode
    wiring** unless exposures are that short.
  - **The trigger** is PNP (above +4 V, 24 V at most) or NPN (below 1 V), not both.
- **Strobed only during behavior exposures** (PI).
  - A lamp-strobe stage on the fan-out board drives each lamp's trigger input; a '541
    channel cannot, and the stage is part of the board's design check (§7.4). The board's
    input is the primary's exposure output, so the lamps are on while the primary exposes.
  - The secondaries start later by their own trigger latency, which FLIR does not publish.
    The tail of their exposures may go unlit by that much.
  - This is measured in the skew test (§7.4). If it matters, the secondaries' exposure is set
    shorter than the primary's.
- **A visible-cut filter on each emitter.** A MidOpt LP830 is cut to cover the LM75's
  emitting area (71 × 25.5 mm) and held in the lamp's bracket. It cuts the LED's shorter
  wavelengths, which is where a faint red glow comes from (INFERENCE).
  - Whether 850 nm light is visible to rhesus monkeys at these levels is **UNVERIFIED**.
  - Edmund has no equivalent (C20). SVL's 75 mm bar-light mount is Edmund
    [#90-438](https://www.edmundoptics.com/p/smart-vision-lights-75mm-bar-light-mount/57263/)
    ($77), but it holds neither the filter nor the diffuser, so the bracket stays custom.
- **The diffuser** is Edmund's light-diffusing film,
  [#27-110](https://www.edmundoptics.com/p/75-x-75mm-light-diffusing-film/52184/): 75 × 75 mm,
  0.13 mm TAC polymer, 300–1100 nm, made to be cut to size ($22.75). It sits in the bracket with
  the filter. One sheet gives both lamps' 71 × 25.5 mm pieces (arithmetic). Its transmission at
  850 nm is not published (**UNVERIFIED**). SVL lists diffusers among its accessories, but none
  for the LM75.
- **Power.** Each lamp needs 24 VDC, 275 mA at most. SVL's 5PM12-5 5 m cable is Edmund
  [#23-951](https://www.edmundoptics.com/p/svl-5-pin-5-meter-cable-164-feet/49639/) ($60.50).
  Edmund names SVL's T2 supply as the LM75's US supply:
  [#75-577](https://www.edmundoptics.com/p/5-pin-m12-24v-92a-power-supply-us/56772/), 24 V at
  9.2 A, flying leads and a 5-pin M12, $365. That current covers both lamps (arithmetic:
  0.55 A). Whether one supply serves both, with the fan-out board's strobe wired in, is the
  design check's (§7.4), so the supply is still not chosen.
- **Eye safety.** SVL rates the LM75 at 850 nm as Exempt Group under IEC 62471:2006, with no
  photobiological hazard even in continuous use. That is SVL's own test, stated on its
  datasheet.
- **Required at bring-up** (P9 §6, check 3):
  - **Darkness at the eye position, as S4's patches are.** In a dark room, with the lamps
    strobing at session settings, a dark-adapted observer at the eye position sees no glow. A
    visible glow means more filtering, moving the lamp, or a question to the PI.
  - **No interference with the tracker.** P1 and P4 are unchanged with the lamps on and off,
    and no 850 nm shows in the tracker's images through its BN940.
  - **No added neural noise** from the lamps' drivers (check 4).

### 7.8 Cables through a passthrough panel

The PI said: "we may have a passthrough panel from in to out of the rig". If there is one,
the cables cross it, and the layout decides it. This is what it implies:

- **USB3.**
  - Teledyne recommends passive cables of 5 m or less, and notes that longer cables see more
    bad or dropped packets.
  - It says nothing about couplers
    ([app note](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/extending-the-working-distance-of-usb-3.1-cameras)).
  - A bulkhead coupler adds two mated connector pairs to every passive run, and whether that
    still fits Teledyne's 5 m is **UNVERIFIED**.
  - The options, in order:
    1. continuous cables through a gland or split grommet, with no connector in the run;
    2. active cables through the panel. Teledyne's suggested vendors are Icron (Spectra
       3001-15), Newnex (FireNEX-UL-8 and -12) and Alysium (A70-8403);
    3. a USB3 bulkhead coupler, qualified by a 12-hour, 8-camera run with no drops (check 2).
- **GPIO and trigger lines.**
  - BNC bulkhead feedthroughs suit the barcode, ExposureActive and trigger lines, if the
    fan-out board's connectors are BNC as wl-sync's are (the design check picks them).
  - The Hirose HR10 camera cables go through a gland. Panel-mount HR10 receptacles were not
    looked up (**UNVERIFIED**).
- **Grounding.** A metal panel joins the cable shields to whatever the panel is bonded to. It
  is part of the no-added-noise check (INFERENCE; check 4).

### 7.9 What this list cannot settle yet

- **The rig geometry.**
  - The tracker's working distance picks its lens (75 or 100 mm) and its ring.
  - Every behavior camera's distance and field in §7.3 is ASSUMED.
  - Where the camera box sits decides passive against active USB, the GPIO lengths, and
    whether a passthrough panel is used (§7.8).
- **The measurements P9 names:**
  - the real bitrate, which sizes the NVMe;
  - NVENC throughput on our mono 1440 × 1080 video at a visually lossless preset, for 4 and
    for 8 cameras;
  - sensitivity at 850 nm, since no NIR quantum efficiency is published, and whether the
    lamps are bright enough at the chosen exposure;
  - darkness at the eye position, and no change to P1 and P4 with the lamps on;
  - 12 hours at 200 fps with no drops, on an AMD host, with ASPM off;
  - no added neural noise.
- **The tracker's light at the eye.** It is measured with a power meter, and the driver
  current is capped (§7.1.2). The attenuator's OD is chosen from that measurement (§7.10).
- **The primary's Line 2 low level** into the fan-out board, and the board's design check
  (§7.4).
- **The ASUS proximity sensor.** It is still open whether the Neo Proximity Sensor and pixel
  cleaning can be turned off (open item 3). How the sensor senses is not published. So
  whether the tracker's 940 nm light affects it is **UNVERIFIED**.
- **The direct-view design** (`2026-09-28-direct-view-design.md`, approved 2026-09-28) fixed the
  screen at 50 cm in both setups and put one camera position below the screen for both, at the
  paper's 35°/25° (its §5). The camera's working distance, and so the lens row above, is chosen
  with the mount; the stereoscope must leave the camera's and light's lines clear.

### 7.10 Eye-light drivers and the safety cap

**The question** (PI, 2026-09-27: "can you find alternative drivers first then decide?"). The
LEDD1B's current limit stops at 200 mA (§7.1.2). If the safe level at the eye is below what
the M940L3 gives at 200 mA, the driver cannot enforce it. What matters most is a **hard cap**:
one set in hardware, which neither a knob nor a control signal can exceed. Sources are the
makers' own pages and manuals, read 2026-09-27 (UTC). Edmund was checked first.

**Does the LEDD1B's MOD input go below 200 mA? Yes, down to zero, but not as a hard cap.**

- In MOD, 0–5 V maps linearly onto 0 mA to the trim-pot limit: "the current limit equals the
  LED current for maximum input voltage of 5V" (manual, §3.2). At a 200 mA limit, 1 V gives
  40 mA (arithmetic). The zero-set-point offset is 10–40 mV.
- In CW and TRIG, the knob likewise spans 0 mA to the limit.
- **The hard cap is still the trim pot.** Thorlabs says the limit holds "regardless of the
  other settings or the modulation input voltage". Anything lower is only as firm as its
  source: a MOD voltage from a DAQ or the task is a software cap, and the knob can be turned
  up.
- A MOD voltage fixed in hardware (a divider on a fixed reference) would be a hard cap, but
  it is a custom circuit (INFERENCE). The manual forbids a negative voltage or more than 5 V
  at MOD IN.
- **With nothing connected to MOD IN, the LED is off** (manual, §3.5), so a pulled cable fails
  dark.

| Driver | Lowest setting (resolution) | Max current | Hard cap? | Modulation input | Ch. | Fits the M940L3 | Power | Price |
|---|---|---|---|---|---|---|---|---|
| Thorlabs **LEDD1B** ([page](https://www.thorlabs.com/t-cube-tm-led-driver?pn=LEDD1B), [manual](https://media.thorlabs.com/globalassets/items/l/le/led/ledd1b/20947-d02.pdf)) | 0 mA by knob or MOD; limit 200–1200 mA by trim pot (continuous; resolution not published) | 1200 mA | **Yes, at 200 mA or more** (the trim pot) | MOD 0–5 V, 10 kΩ, 0–5 kHz sine, slew 13.6 mA/µs; TRIG TTL (high ≥ 2 V, low ≤ 0.55 V), 0–1 kHz, rise 51 µs, fall 79 µs | 1 | Yes: M8, listed by Thorlabs | 15 V, KPS201 | 380.04 + 43.15 |
| Thorlabs **DC40** ([page](https://www.thorlabs.com/4.0-a-led-driver)) | 0 A by knob; limit 0.1–4.0 A, from the LED's EEPROM or the software GUI, accurate to ±(1.0% + 25 mA) | 4.0 A | **No**: firmware, set over USB. MOD is clamped to it | TTL (high 2.6–5.0 V), DC–5 kHz; MOD 0–5 V at 800 mA/V, DC–5 kHz | 1 | Yes: M8, listed | 15 V supply included | 770.40 |
| Thorlabs **DC2200** ([page](https://www.thorlabs.com/led-driver-for-high-power-and-mounted-leds?pn=DC2200), [manual](https://media.thorlabs.com/globalassets/items/d/dc/dc2/dc2200/mtn005097-d02.pdf)) | 0 A; 0.1 mA resolution; user limit from "1" (the manual gives no unit) to the LED's EEPROM maximum | 2.0 A (M8 terminal) | **No**: firmware, set on the touchscreen or over USB. Past the limit in external modulation a limit indicator trips; clamp or shut-off is **UNVERIFIED** | Analog 0–5 V at 400 mA/V, DC–250 kHz (small signal); TTL, DC to ≥ 18 kHz | 1 | Yes: M8 (LED2), listed | Included | 2,593.01 |
| Thorlabs **DC4100 / DC4104** ([page](https://www.thorlabs.com/advanced-four-channel-led-driver?pn=DC4100), [manual](https://media.thorlabs.com/globalassets/items/d/dc/dc4/dc4104/doc-101098.pdf)) | 0 mA; 1 mA resolution, ±10 mA; per-channel user limit | 1000 mA | **No**: firmware. External control is "Clipped to Limit", and a hidden menu raises the LED's own maximum until power-off (DC4104 manual) | 0–10 V at 100 mA/V, 0–100 kHz sine: one input for all four (DC4100) or one each (DC4104) | 4 | Through the DC4100-HUB ($401.67); 5 V maximum forward voltage, against the M940L3's 2.75 V typical | Not read | 3,354.38 / 3,691.20, + hub |
| Mightex **SLA-1000-2** ([page](https://www.mightexsystems.com/product/sla-series-two-channel-led-drivers-with-manual-and-analog-input-controls/), [datasheet](https://mightex.wpenginepowered.com/wp-content/uploads/2019/04/SLA_leddriver_datasheet_v3p2_Apr2013.pdf)) | 0 mA by knob or analog; resolution not published (finer at a lower cap) | 1000 mA | **Yes, by DIP switch per channel: 350, 500 or 1000 mA** | Analog 0–5 V, linear; 1 kHz maximum. No separate TTL input | 2 | Bare LED+ / LED− pins: needs Thorlabs' CON8ML-4 female M8 lead ($39.10) per LED | 9–24 V; whether a supply is included was not read | €524.80 per 2 channels |
| Mightex **SLA-0100-2** (same page) | As above | **100 mA**: cannot run the M940L3 at its rating | **Yes: 30, 50 or 100 mA** | As above; 50 kHz maximum | 2 | As above | As above | €524.80 per 2 channels |
| Mightex **SLC-AA04 / SA04** ([page](https://www.mightexsystems.com/product/slc-sa-aa-series-universal-four-channel-led-controllers-with-external-triggers/)) | 0 mA; 12-bit | 1000 mA normal; **3500 mA** in strobe or trigger | **No**: a software limit ("built-in security feature") | Trigger per channel, high 4.5–10 V, which a 5 V logic output may not reach (INFERENCE) | 4 | Mightex connectors; an adapter is **UNVERIFIED** | 9–24 V | €1,395.20–2,265.60 |
| Doric **LEDD** ([page](https://neuro.doriclenses.com/products/led-drivers), [manual](https://doriclenses.com/downloads/UserManual/UserManual_LED_Light_Source_V2.1.1.pdf)) | 40 mA; in low-power mode 2.5 mA (manual) or 4 mA (page), with a 200 mA ceiling | 2000 mA | **No**: the maximum is set with the front knob, and the software offers overdrive | TTL (high > 2.8 V); analog 0–5 V at 400 mA/V; rise and fall < 10 µs; 10 kHz | 1, 2 or 4 | M8 female; whether its pin-out matches Thorlabs' is **UNVERIFIED** | Included | Not published |
| **Passive: Edmund NIR ND** ([#47-530](https://www.edmundoptics.com/p/10-od-25mm-dia-nir-nd-filter-/7611/)), row 5c | — | — | **Yes, optically**: transmission is 10^−OD at every current | — | 1 per light | Ø25 mm, in the collimator's output through SM1A38 and a retainer ring | None | 126.00 + 31.62 + 5.25 |

**Checked and set aside:**

- **Edmund Optics.** Its searches for "LED driver" and "LED controller" show no
  constant-current driver for a mounted LED. The nearest are the Visionlux
  [24V LED Controller #73-651](https://www.edmundoptics.com/p/24v-led-controller/55877/)
  (200–2000 mA, a P1J connector, listed with Edmund's telecentric ring-light kit, $270) and
  CCS's [PD2 controllers](https://www.edmundoptics.com/p/power-supply-pd2-3012-a/47268/) for
  CCS lights ($570).
- **Thorlabs has no K-Cube LED driver.** Its
  [LED-driver list](https://www.thorlabs.com/led-drivers) is the LEDD1B, the upLED, the DC40,
  the DC2200, a basic driver for Solis LEDs, and the DC4100/DC4104. The
  [upLED](https://www.thorlabs.com/constant-current-usb-controlled-led-driver) (1.2 A, 1 mA
  steps, $575.56) has no modulation input.
- **Mightex, other lines.** The
  [SLC-MA01-U](https://www.mightexsystems.com/product/compact-universal-1-and-2-channel-led-controllers/)
  has no external trigger (€608). The
  [SLB-1200-1](https://www.mightexsystems.com/product/slb-series-manual-analog-input-controlled-universal-led-driver-with-current-display/)
  (DIP caps of 350, 750 or 1200 mA; €844.80) and the
  [BLS-1000-2](https://www.mightexsystems.com/product/bls-high-speed-led-drivers/) (500, 750 or
  1000 mA; from €1,561.60) have hard caps, but none lower than the LEDD1B's.
- **Prizmatix's** [UHPTLCC-02](https://www.prizmatix.com/LEDUHP/Benchtop-UHP-T-LED-Controllers.aspx)
  controls Prizmatix's own heads, whose driver is inside the head, so it cannot drive the
  M940L3.
- **Opto Engineering's** [LTDV1CH-17V](https://www.opto-e.com/en/products/ltdv-series/LTDV1CH-17V)
  is a machine-vision strobe controller with 0.16 A continuous at most, priced by quote.

**The attenuator.**

- **Edmund's TECHSPEC NIR ND** ([family](https://www.edmundoptics.com/f/near-ir-nir-neutral-density-nd-filters/13025/))
  is specified flat across 700–1100 nm, which covers 940 nm. It comes in OD 0.3–3.0 at
  Ø25 mm. Its OD tolerance is ±10%, so OD 1.0 passes 7.9–12.6% (arithmetic).
  - It is reflective, with the mirrored side toward the LED. So most of the rejected light is
    sent back toward the LED rather than absorbed in the filter (INFERENCE).
- **Thorlabs' absorptive NE-series**, such as
  [NE10A](https://www.thorlabs.com/mounted-absorptive-neutral-density-filters?pn=NE10A) in an
  SM1-threaded mount at $64.18, is cheaper. But Thorlabs selects its glass for flat absorption
  over 400–650 nm only, so its OD at 940 nm would have to be read off its curve or measured.
- **The fit.** The SM1U25-B's output is internal SM2 on a removable adapter. Removing it
  exposes internal M34 × 0.5, and Thorlabs names the SM1A38 (external M34 × 0.5, internal SM1)
  as the SM1 alternative ([Thorlabs](https://www.thorlabs.com/mounted-leds?pn=SM1U25-B)).
  The filter sits in the SM1A38 under an SM1 retainer ring. Whether it is deep enough is
  **UNVERIFIED**; if not, a short SM1 lens tube carries it.

**Decided (PI, 2026-09-28):**
- **The ND attenuator is committed now** (row 5c), as the cap that holds whatever the driver
  does. Its OD is chosen at bring-up from the power-meter reading.
- **The driver is chosen at bring-up**, once the tracker's real current need is measured.
  The Mightex SLA-1000-2's switch-set hardware cap and the LEDD1B are both still in play,
  and so is the SLA-0100-2 if 100 mA proves enough.

The agent's recommendation had been to keep the LEDD1B with the ND behind it. Per eye:

1. **The ND's OD is chosen at bring-up**, so the eye stays under the limit at the highest
   current the LEDD1B can deliver, 1200 mA, not at the setting.
   - The power meter reads the eye position with the filter in place and the LED at its
     1000 mA rating. So the filter's own tolerance is inside the reading.
   - The OD then carries at least a 1.2× margin for the driver's 1200 mA. This is ASSUMED:
     the LED's output rises no faster than its current.
2. **The trim pot is set to 1000 mA or less** (Thorlabs asks for the LED's rating anyway) and
   covered with a tamper-evident seal.
3. That gives **two independent hardware layers**. The ND alone keeps the eye under the
   limit even at the driver's maximum. The trim pot keeps the current at or below the
   1000 mA the ND was measured at, so the 1.2× margin stays spare. The knob and the MOD
   voltage then work below both.
4. **The filter is checked** at every bring-up and whenever the light is serviced. The
   eye-position measurement is repeated whenever the light, collimator, filter or driver
   changes (§7.1.2).

**The cost per eye** (arithmetic):

- LEDD1B $380.04 + KPS201 $43.15 + ND $126.00 + SM1A38 $31.62 + retainer $5.25 = **$586.06**.
  Of that, the cap's parts are $162.87.
- Both eyes: $1,172.12.
- The ND's price is for OD 1.0. Other ODs' prices were not read.

**Why not the others:**

- **The fine, low limits are all firmware.** The DC40, DC2200, DC4100/4104, Doric and the
  Mightex SLC can each be raised from a front panel or a USB link. The Thorlabs ones cost
  $770.40–3,691.20 per driver.
- **Mightex's DIP caps are hardware, but coarse.**
  - The SLA-1000-2's lowest is 350 mA, above the LEDD1B's 200 mA.
  - The SLA-0100-2's 30/50/100 mA cannot reach the LED's rating. It helps only if the measured
    safe current is 100 mA or less. It is then a fallback at €262.40 per eye, plus a
    CON8ML-4 and a 9–24 V supply.
- **The ND works with whichever driver is bought.**

### 7.11 The Edmund pass (2026-09-28)

The PI's standing request (2026-09-27): "the more stuff we can source from edmund optics, the
better". Every optics, lighting, filter and mounting row in §7.1 and §7.2, and every other part
Edmund plausibly sells, was checked on Edmund's own pages, read in a browser on 2026-09-28. No
bot check was served. Each row carries its finding; this is the summary.

**Moved to Edmund.** The old part stays in its row as the alternative.

| Row | Edmund part | Replaces | Kind | Price change each (USD) |
|---|---|---|---|---|
| 7.1-1, C1 | #11-507, the BFS-U3-16S2M-CS | Teledyne direct | the same part | 0 |
| 7.1-4 | #28-792 (M43) / #28-793 (M46), 940 nm, FWHM 55 nm | MidOpt BN940-43 / -46 | swapped (PI preference) | 0; in stock rather than built to order |
| 7.1-7 | #16-716 dovetail stage, 25 mm travel, plate lock | Thorlabs DTS25/M | swapped (PI preference) | −21.88 |
| 7.1-3, C6 | #03-618 CS-to-C spacer, listed under Teledyne FLIR | Teledyne ACC-01-5004 | swapped; the same part is INFERENCE | +17.20 |
| 7.1-10, C8 | #86-770 (3 m) / #88-058 (5 m) USB 3.1 locking cables | Teledyne ACC-01-2300 / -2301 | the same part | +16.40 / +23.50 |
| 7.1-11, C9 | #88-064 (1 m) / #88-065 (4.5 m) GPIO cables | Teledyne ACC-01-3009 / -3010 | the same part | +0.50 / +27.10 |
| §7.1.3, C21 | #88-210 tripod adapter | Teledyne ACC-01-0003 | the same part | +6.20 |
| C20 | #90-436, the LM75-850-W | Machine Vision Direct | the same part | −1.00 |
| C20, §7.7 | #27-110 light-diffusing film | nothing (not chosen) | new | 22.75 for both lamps |
| §7.7 | #23-951, SVL's 5PM12-5 cable | SVL, unpriced | the same part | 60.50, not priced before |

**Edmund had nothing suitable:**

- **7.1-5, the collimated 940 nm light:** the smallest found is a 106.7 mm backlight in
  constant mode (§7.1.2).
- **7.1-14 and C7, the USB card:** its cards are PCIe 2.0 x1, with four ports on one controller.
- **C5, the 850 nm band-pass:** its 850 nm filters are 160 nm wide, and its 880 nm one 135 nm.
- **C20, the visible-cut filter:** its RG830 lists its passband from 950 nm and is 50 mm square.
- **7.1-8b, the monitor arm:** it sells no VESA mount.
- **Cables beyond 5 m:** its 8–20 m USB3 cables do not say they are active; Newnex stays.
- **7.1-5b, the driver:** none (§7.10). **7.1-5c's SM1A38** stays Thorlabs: a search for an
  M34 × 0.5-to-SM1 adapter found none at Edmund.
- **Already Edmund:** the lenses (7.1-2, C2, C3), the extension rings (7.1-3), and the ND and
  its retainer ring (7.1-5c).
- **Mounts and posts:** none needed; the brackets are printed (PI).

**For the PI** (an Edmund option that would change a decision):

1. **A band-pass behind the lens for the behavior cameras.** Edmund's C-mount camera filter
   [#73-321](https://www.edmundoptics.com/p/narrow-nir-850nm-c-mount-bandpass-filter/54809/)
   (845–860 nm, FWHM 33 nm, 88% or more, $292, 9 in stock) threads into the camera, between
   the lens and the sensor. Edmund recommends it for wide-angle lenses.
   - For: one Edmund part fits both lenses, replaces MidOpt's BN850, and sidesteps the 6 mm
     lens's front-thread question (C3).
   - Against: it is not threaded onto the lens, as the PI decided. Its 33 nm band is narrower
     than ±25 nm. Whether it fits in the CS body behind the 5 mm spacer is **UNVERIFIED**.
   - **The PI's answer (2026-09-28): check the fit first, then decide.** Two checks, from
     Edmund's mechanical drawing or a question to Edmund:
     - whether it threads in behind the 5 mm CS-to-C spacer;
     - whether the lenses still focus at the planned distances, since a glass filter behind
       the lens shifts the focal plane by roughly a third of its thickness (thickness × (1 −
       1/n); arithmetic, n about 1.5).

     Until then, the MidOpt BN850 stays in C5.
   - The 940 nm twin, [#73-322](https://www.edmundoptics.com/p/narrow-nir-940nm-c-mount-bandpass-filter/54810/),
     is not needed: row 4 already has an Edmund filter for the lens thread.
   - **Fit check (2026-09-28).** Read on Edmund's own product/spec-sheet pages and drawings,
     and on Teledyne FLIR's own Blackfly S documentation, all on 2026-09-28 (browser reads;
     no bot check was served on any of them):
     - **#73-321's mechanical specs** (Edmund's spec sheet for
       [#73-321](https://www.edmundoptics.com/p/narrow-nir-850nm-c-mount-bandpass-filter/54809/),
       read 2026-09-28): filter thread **C-Mount** (the same 1"-32 UN thread family the
       lenses and the spacer use — Edmund's own page for
       [#03-618](https://www.edmundoptics.com/p/5mm-spacer-to-convert-cs-mount-cameras-to-c-mount/90/)
       gives "Female Thread: C-Mount (1" - 32 TPI)", read 2026-09-28); outer diameter
       25.40 mm; clear aperture 19.50 mm; **substrate thickness 1.00 mm**; **mount thickness
       3.00 mm** (the ring's front-to-back length). Whether it adds to the lens-to-sensor
       stack depends on how it mounts, which is not published (see below); construction "Mounted in Black Anodized Ring".
       Substrate glass type/index is not published — **UNVERIFIED**; n ≈ 1.5 is assumed
       below, as the PI's original note already assumed. No dimensioned drawing beyond this
       spec sheet is published, so the ring's step profile is also **UNVERIFIED**.
     - **Where it threads.** C-mount and CS-mount are the same thread; Edmund's own
       [Lens Mounts](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/lens-mounts/)
       note (read 2026-09-28) gives C-Mount flange distance **17.526 mm** and CS-Mount
       **12.526 mm** (the 5.00 mm the spacer makes up), so #73-321 can physically thread onto
       the camera's CS-mount face, between camera and spacer, or between spacer and lens —
       thread compatibility does not decide the order. Teledyne's own Blackfly S
       Installation Guide and the BFS-U3-16S2 model pages
       (https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/LensMount.htm,
       read 2026-09-28) state the BFS-U3-16S2M (monochrome) has a 1 mm ± 0.07 mm clear glass
       dust-protection window (Schott B270, replacing the color IR-cut filter) plus a further
       "0.5 mm sensor package window" between the mount face and the sensor, but neither that
       guide nor Edmund's pages publish a maximum-intrusion or thread-depth figure for the
       CS-mount cavity beyond the flange-distance number itself. **Whether the camera body
       has 3.00 mm of unobstructed physical depth for the filter ring before the internal
       shutter/PCB is still UNVERIFIED** — unchanged from the PI's original note; no
       manufacturer page answers it.
     - **Rear protrusion.** Edmund's own dimensioned drawings (read 2026-09-28) give
       #27-554's (12 mm) max rear protrusion past its C-mount flange as **0.52 mm**, and
       #39-939's (6 mm) as **4.50 mm at 50 mm working distance / 5.13 mm at infinity**.
       Neither number is the blocker here: a filter threaded behind the flange sits on the
       camera side of the register, not the lens side, so it does not have to clear the
       lens's own rear barrel.
     - **Focus shift (arithmetic; corrected by the controller).** What matters is how the
       ring mounts, and Edmund does not publish it.
       - **Recessed:** if the ring threads *into* the camera's mount and sits inside it, with
         the spacer and lens threaded in front, the stack length is unchanged. Only the glass
         shifts the image plane back, by t·(1 − 1/n) = 1.00 × (1 − 1/1.5) ≈ **0.33 mm**
         (n assumed; substrate UNVERIFIED). That shift uses up focus travel: the lens must
         extend by (v − f) + 0.33 mm. By the thin-lens relation (principal planes ignored):
         - #27-554, 12 mm, at 40 cm: v − f = 144/388 ≈ 0.37 mm, so 0.70 mm of its ≈ 1.64 mm
           travel (∞ → 100 mm). **It focuses.**
         - #39-939, 6 mm, at 80 cm: v − f = 36/794 ≈ 0.05 mm, so 0.38 mm of its ≈ 0.52 mm
           travel (∞ → 75 mm). **It focuses, with about 0.14 mm to spare**, which a
           glass with n above 1.5 would narrow. Neither lens reaches infinity with the filter
           in; the rig does not need infinity.
       - **Stacked:** if the ring instead sits between the spacer and the lens, adding its
         3.00 mm, the lens needs about 2.67 mm more extension than either has. Then neither
         lens focuses at any distance.
     - **Verdict: unknown until Edmund answers two things.**
       - Does #73-321 recess inside a camera's mount, with the lens in front of it, or does
         it stack?
       - Does the Blackfly S's CS mount have at least 3 mm of clear depth for the ring, in
         front of its 1 mm dust window?

       If it recesses and fits, both lenses focus at the planned distances by the
       arithmetic above. The 6 mm lens's margin is thin, so it is checked on the rig. The
       MidOpt BN850 stays in C5 until then.
       *An agent's first draft of this check concluded "doesn't fit and focus", assuming
       the ring stacks. The controller corrected it, because a camera-mount filter
       normally recesses.*

**The price effect** (arithmetic): one rig with 2 tracker and 4 behavior cameras, 2 stages and
2 lamps.

- **Teledyne's accessories through Edmund** cost more:
  - spacers 6 × $17.20 = $103.20, and tripod adapters 6 × $6.20 = $37.20;
  - USB cables $112.60 (5 m to the tracker, 3 m to the behavior cameras) or $141.00 (all 5 m);
  - GPIO cables $3.00 (all 1 m) or $162.60 (all 4.5 m);
  - so **+$256.00 to +$444.00**. **The PI accepts it (2026-09-28): Edmund anyway**, one vendor where possible.
- The stages save $43.76 and the lamps $2.00.
- **Net: +$210.24 to +$398.24 a rig**, plus $22.75 for the diffuser, which was not priced
  before. Buying those accessories from Teledyne direct instead is a per-row choice.
- **The camera-box budget (§7.6) is unchanged**: nothing it counts moved.

---

## 8. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | `wl-stack` adopting the `rig/*` role vocabulary | the registry entry's `runs_on` |
| 2 | Whether `rig/intan` and `rig/sglx` are one machine | V8, and the task PC's network layout |
| 3 | ~~Tandem panel model~~ **The ASUS PG27UCDM, a 26.5" tandem QD-OLED, was chosen** (PI, 2026-09-27, §5.1, replacing the PG32UCDM Gen 3 of 2026-09-26). Still open: **whether its automatic pixel cleaning and Neo Proximity Sensor can be fully turned off** (§5.4 test 1). Ask ASUS before buying | the panel purchase |
| 4 | ~~Whether the chosen GPU + panel can avoid DSC~~ **Closed 2026-09-26: yes.** The RTX 5070 Ti and the PG27UCDM both list DisplayPort 2.1 UHBR20, and ASUS states 4K/240 "without compression" for the PG27UCDM (read 2026-09-27; §4, §5.1) | — |
| 5 | Photodiode patch placement against the real optics | rig build, and `wl-sync` agreement |
| 6 | Viewing distance against the real chair and head-post geometry | optics build |
