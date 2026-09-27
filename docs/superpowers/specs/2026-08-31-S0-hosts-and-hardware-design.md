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
65 px/deg. That leaves roughly a degree of vertical margin beyond a 15° target, so **the
direct-view viewing distance is still open** and is set in the direct-view design.

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

**§5.2's geometry and the stereoscope optics drawing must be recomputed for 26.5".** The
comparison also found that the drawing's relations undersize M1 and M2 enough to clip the
field's corners, and that its nasal-clip formula is wrong. Both are recorded in the
comparison report and still to be fixed. §5.2 below still shows the 31.5" figures.

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

Its §5.2 geometry was computed from the 31.5" viewable diagonal.

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
| Stereoscope optics | 2 sets | build | Geometry drawn (`2026-08-31-stereoscope-optics-drawing.md`); first-surface mirrors, 4 per rig |

`wl-sync` fabs the breakout boards on its own schedule: prototype late October to late
November, production run mid-November to mid-December, with almost no slack for a respin.

The eye tracker's and the behavior cameras' parts lists are in §7.

---

## 7. Parts lists (addendum, 2026-09-27)

A reasoned list for the PI, who owns procurement. It is not an order.

- **Sources.** Every part fact (model, spec, price, compatibility) comes from the maker's or
  distributor's own page, read 2026-09-27, or is marked **UNVERIFIED**. Links are in the
  tables.
- **Prices** are what each page showed that day in US dollars. Four Corsair prices were sale
  prices, and NVIDIA's is its "starting at" figure. Thorlabs's site showed euros until it was
  switched to US dollars. None is a quote.
- **Status** is one of: *decided*; *waits on* a named measurement or design; or *PI's call*.
- **Arithmetic** in this section is labeled as arithmetic. **Assumptions** are labeled
  ASSUMED.

**What binds the lists** (PI, 2026-09-27):

- **The eye tracker.**
  - OpenIrisDPI stays live on its own Windows PC and cameras.
  - P10's C++ tracker is validated offline on raw eye video from our rig, so the tracker PC
    records raw video from both cameras.
  - The ACCES USB-AO16-8A stays as the analog backup.
  - The camera views the eye from below the screen in direct view, which is the primary
    configuration. The stereoscope (±10°) is the secondary one.
  - The IR is 940 nm.
  - ExposureActive goes to wl-sync GPIO26 (S3 §8).
- **The behavior cameras (P9).**
  - 1–2 on the face and 1–2 on the body: 2–4 typical, 8 at most.
  - 200 fps, recorded the whole session, encoded on a consumer GPU.
  - The primary triggers the rest through a fan-out board.
  - The tracker's 940 nm light comes first. A lamp is a contingent line.
- **The camera-box budget** is under about $4,000 for the computer, GPU, storage and USB
  cards, not counting the cameras.

### 7.1 The eye tracker: changes from the OpenIrisDPI reference build

The reference build is the OpenIrisDPI wiki's "ohDPI Assembly Introduction", read 2026-09-27.
This addendum worked from that reading's hardware list and did not reopen the wiki. Nothing in
the list touches P10's method, which stays clean-room
(`docs/research/2026-09-27-p10-dpi-spike.md` §3).

| # | Role | Requirement | Candidate (maker, model) | Qty | Source, read 2026-09-27 | Price (USD) | Kept or changed; status |
|---|---|---|---|---|---|---|---|
| 1 | Tracker cameras | OpenIrisDPI's own frames: same sensor, 500 Hz at the paper's 720 × 450 ROI | Teledyne FLIR Blackfly S **BFS-U3-16S2M-CS** | 2 | [Teledyne product page](https://www.teledynevisionsolutions.com/products/blackfly-s-usb3/?model=BFS-U3-16S2M-CS&vertical=machine%20vision&segment=iis) | 556.50 each | **Kept.** It is also P9's body, so the rig has one camera model. *Decided* |
| 2 | Lenses | The reference's optics, so P10's same-frames comparison compares trackers, not optics | Venus Optics **Laowa 100 mm f/2.8 2× Ultra Macro APO**, Canon EF | 2 | [maker's page](https://www.venuslens.net/product/laowa-100mm-f-2-8-2x-macro-apo/). It refused a scripted fetch; facts are from a search engine's excerpt of it | **UNVERIFIED** | **Kept.** The maker says only the EF version has a chip and motor for aperture control. On a passive adapter the aperture therefore cannot be set from the camera (INFERENCE; check at bring-up). *Decided* |
| 3 | Lens adapters | An EF lens on a CS-mount body | a generic EF-to-C adapter, plus Teledyne **ACC-01-5004** CS-to-C 5 mm spacer | 2 + 2 | [spacer page](https://www.teledynevisionsolutions.com/products/cs-to-c-mount-5mm-spacer-adapter/) | adapter **UNVERIFIED**; spacer 11.80 | **Changed: add the spacer**, unless the adapter bought is EF-to-CS. Without it, the 5 mm the spacer exists to supply comes out of the macro's focus travel. *Decided* |
| 4 | IR filter | Pass 940 nm and block visible room light | Edmund Optics **#43-953**, 2" × 2" optical cast plastic IR long-pass (Thermoset ADC, 1.5 mm, over 90% transmission typical) | 1 | [Edmund page](https://www.edmundoptics.com/p/2quot-x-2quot-optical-cast-plastic-ir-longpass-filter/5422/) | 23.25 | **Kept.** The page text gives no cut-on wavelength: **UNVERIFIED**. That matters to P9's 850 nm option, which needs this filter to reject 850 nm (P9 §2). *Decided*; the 850 nm option *waits on* the cut-on |
| 5 | Illuminator | 940 nm (PI), collimated onto the eye, and 10° shallower than the camera (the paper's rule) | Thorlabs **M940L3** (940 nm, 800 mW minimum, mounted LED, 1000 mA); **LEDD1B** T-Cube driver (1200 mA maximum; no supply); **KPS201** (15 V, 2.66 A); **SM2F** adjustable collimation adapter (Ø2"); **ACL50832U** (Ø2" asphere, f = 32 mm, NA 0.76, uncoated) | 1 each | Thorlabs [M940L3](https://www.thorlabs.com/item/M940L3), [LEDD1B](https://www.thorlabs.com/item/LEDD1B), [KPS201](https://www.thorlabs.com/item/KPS201), [SM2F](https://www.thorlabs.com/item/SM2F), [ACL50832U](https://www.thorlabs.com/item/ACL50832U) | 274.55 + 380.04 + 43.15 + 315.23 + 53.69 = **1,066.66** | **Kept.** *Decided* |
| 6 | Lens clamps | Hold the lens barrels | Thorlabs **VG100/M** adjustable-height optics clamp, metric | 2 | [Thorlabs](https://www.thorlabs.com/item/VG100_M) | 109.63 each | **Kept.** *Decided* |
| 7 | Frame | Carries rows 8 and 9 | 80/20 **1010** profile; the reference's brackets (4115, 4118, 4141, 4148, 4139, 4166); 1/4-20 fasteners | per layout | 8020.net refused scripted access with a bot check, which was not bypassed | **UNVERIFIED** | **Changed:** re-cut for our two configurations. *Waits on* rig geometry |
| 8 | Direct-view mount (primary) | Hold the PG27UCDM by its VESA 100 × 100 mount (4.97 kg without its stand; §5.1). Put both cameras and the LED below its lower edge at the paper's 35° / 25° | a VESA 100 × 100 plate on the 80/20 frame | 1 | §5.1 (ASUS, read 2026-09-27) | **UNVERIFIED** (part not chosen) | **New.** The lowest camera angle that still centers P4 on this panel is 29.9° at 57 cm (panel comparison §4.2), so 35° fits. At the paper's 57 cm working distance, 35° puts the camera 46.7 cm forward of the eyes and 32.7 cm below them (same report). *Waits on* the direct-view design, which sets the viewing distance (57–65 cm) |
| 9 | Stereoscope mount (secondary, ±10°) | The same camera-to-eye geometry, below M1 | 80/20, as row 7 | 1 | panel comparison §9 | — | **New.** At the paper's angles the camera clears M1 plus a 5 mm mount by about 11°, and the LED by about 3° (on the drawing, still at 31.5"). *Waits on* the drawing's recompute for 26.5" (§5.1) |
| 10 | Camera USB cables | Camera to tracker PC | Teledyne **ACC-01-2301** USB3 Micro-B locking, 5 m. The reference used generic 15 ft (4.6 m) cables. Beyond 5 m: Newnex **FIRENEX-ULS-08 / -12 / -16**, active, locking Micro-B, bus-powered, rated up to 16 m | 2 | [Teledyne cables](https://www.teledynevisionsolutions.com/products/usb-3.1-locking-cable); [Teledyne app note](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/extending-the-working-distance-of-usb-3.1-cameras); [Newnex](https://newnex.com/usb-3-active-cable-a-to-micro-b.php) | 37.50 each; Newnex's price is not published | **Kept** while the run is passive: Teledyne recommends passive cables of 5 m or less. *Waits on* where the tracker PC sits |
| 11 | GPIO cables | Camera GPIO to the sync box | Teledyne **ACC-01-3009** (Hirose HR10 6-pin, 1 m) or **ACC-01-3010** (4.5 m) | 2 | [Teledyne](https://www.teledynevisionsolutions.com/products/hirose-hr10-6-pin-circular-connector/) | 37.50 / 43.90 | **Kept**, or the 4.5 m cable if the sync box is farther than 1 m. *Waits on* the layout |
| 12 | Eye-group sync wiring | wl-sync's eye barcode BNC (`CAM_SYNC_EYE`) goes into the camera's opto input, Line 0. ExposureActive leaves by the opto output, Line 1, into wl-sync J17B, which is GPIO26. That front end supplies its own 1 kΩ pull-up to 5 V (wl-sync `hardware/breakout/frame-time-inputs.md`) | wiring | — | [FLIR I/O table](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/InputOutputControl.htm); wl-sync at `92714ce` | — | **New**, per the PI. **GPIO26 is one input**, sized for one strobe per group because a primary triggers the rest. Two free-running cameras on it would wire-OR their strobes. Whether OpenIris runs its two cameras as primary and secondary is **UNVERIFIED**: its source is off-limits under P10's clean-room rule. *PI's call*: one strobe with primary/secondary, or a second input |
| 13 | Tracker PC | Windows; OpenIrisDPI stays live on its own PC (PI) | the reference's class: i9-12900K, 16 GB or more, 2 or more USB 3.1 ports | 1 | the reference build | — | **Kept**, with rows 14 and 15 added. *PI's call* (procurement) |
| 14 | One USB3 controller per camera | 2 × 162 MB/s (arithmetic, below) | Teledyne **ACC-01-1205**: four independent Fresco FL1100 host controllers, PCIe 2.0 x4, 4 locking ports. Powered from the slot or a 4-pin/SATA 12 V connector; Windows or Linux (datasheet) | 1 | [card page](https://www.teledynevisionsolutions.com/products/usb-3.1-host-controller-card?model=ACC-01-1205&vertical=machine%20vision&segment=iis); [datasheet](https://flir.netx.net/file/asset/71254/original/attachment/) | 148.00 | **New, if the PC lacks one controller per camera.** Teledyne's 2-port card (ACC-01-1201) is one Renesas uPD720202 on PCIe 2.0 x1, so both cameras would share it. *Waits on* checking the tracker PC's controllers |
| 15 | Raw validation video (P10) | Raw video from both cameras (PI), at 324 MB/s sustained | Samsung **990 PRO 4 TB** (MZ-V9P4T0B/AM; PCIe 4.0; 5 years or 2,400 TBW) | 1 | [Samsung](https://www.samsung.com/us/memory-storage/nvme-ssd/990-pro-pcie-4-0-nvme-ssd-4tb-sku-mz-v9p4t0b-am/) | 1,099.99 | **New.** Holds 3.4 h at the recording's frame size (below). *Waits on* two things. Does OpenIris write the video raw or compressed? (**UNVERIFIED**) And the drive's sustained write rate after its cache is unpublished, so it is measured |
| 16 | Analog backup | Analog eye into SpikeGLX (PI) | ACCES I/O **USB-AO16-8A** (16-bit, 8 analog outputs, 2 analog inputs; the family page lists outputs updated at up to 4 kHz) | 1 | [ACCES family page](https://accesio.com/product/usb-ao16-16a/) | 604.00 | **Kept.** `docs/research/openiris-dpi.md` names the **-8E** (439.00; 8 outputs, no inputs). The PI named the 8A. *Decided* |

**Raw validation video: the arithmetic**, 8-bit mono, two cameras:

- **At the recording's frame, 720 × 450.** This is the spike's §7b.1 inference from the
  recording's coordinates. 720 × 450 × 1 B × 500 fps = 162.0 MB/s per camera and 324.0 MB/s
  for two. That is 1.17 TB an hour, so 4 TB holds 3.4 h.
- **At full frame, the same rate.** 1440 × 1080 × 1 B × 500 fps = 777.6 MB/s per camera,
  1.56 GB/s for two, and 5.6 TB an hour. The camera cannot do this: FLIR lists 226 fps at
  full frame.
- **At full frame and 226 fps.** 351.5 MB/s per camera and 703.0 MB/s for two. That is
  2.53 TB an hour, so 4 TB holds 1.6 h.

### 7.2 The behavior-camera system (P9)

| # | Role | Requirement | Candidate (maker, model) | Qty | Source, read 2026-09-27 | Price (USD) | Status |
|---|---|---|---|---|---|---|---|
| 1 | Cameras | 1–2 on the face (blinks, eyelids, licking) and 1–2 on the body (hands, arms, posture); 200 fps; 8 at most | Teledyne FLIR **BFS-U3-16S2M-CS**: Sony IMX273, 1/2.9", 1440 × 1080, 226 fps, 3.45 µm, CS-mount, USB 3.1 Gen 1, 3 W maximum | 2–4 (8 max) | [Teledyne](https://www.teledynevisionsolutions.com/products/blackfly-s-usb3/?model=BFS-U3-16S2M-CS&vertical=machine%20vision&segment=iis) | 556.50 each | *Decided* (PI) |
| 2 | Face lens | About 15 cm of field at about 40 cm (ASSUMED), so f ≈ 12.8 mm (§7.3) | Edmund Optics **#27-554**, 12 mm TECHSPEC C VIS-NIR: 425–1000 nm broadband AR coating; C-mount; up to 2/3"; f/1.8–16; working distance 100 mm to ∞; 11 mm image circle; filter thread **M25.5 × 0.50** | 1–2 | [Edmund](https://www.edmundoptics.com/p/12mm-c-vis-nir-series-fixed-focal-length-lens/53828/) | 635.00 | *Waits on* rig geometry |
| 3 | Body lens | About 60 cm of field at about 80 cm (ASSUMED), so f ≈ 6.6 mm (§7.3) | Edmund Optics **#39-939**, 6 mm C VIS-NIR: the same coating; up to 1/1.8"; f/1.4–16; working distance 75 mm to ∞; 9 mm image circle; distortion up to −6.84%; filter thread through adapter #85-308 | 1–2 | [Edmund](https://www.edmundoptics.com/p/6mm-c-series-vis-nir-fixed-focal-length-lens/40554/) | 725.00 (stock: "contact us") | *Waits on* rig geometry |
| 4 | Filter adapter, 6 mm lens | A filter thread for the 6 mm lens | Edmund Optics **#85-308**, M43 × 0.75 female from 36 mm | 1 per body lens | [Edmund](https://www.edmundoptics.com/p/filter-adapter-m43-x-075-from-36mm-diameter/28238/) | 60.50 | **Check before buying.** The lens page gives its filter thread through this adapter as M43 × **0.50**, and the adapter's page says M43 × **0.75**. MidOpt's M43 is × 0.75. *Waits on* Edmund confirming |
| 5 | 940 nm band-pass filter | Pass the tracker's 940 nm and reject the rest; the thread must match the lens | MidOpt **BN940**: useful range 928–955 nm, FWHM 55 nm, peak transmission 85% or more. **BN940-25.5** (M25.5 × 0.5) on the 12 mm lens; **BN940-43** (M43 × 0.75) on #85-308 for the 6 mm lens | 1 per camera | [BN940](https://midopt.com/filters/bn940/); [MidOpt thread table](https://midopt.com/mounting-solutions/threaded-mount/) | not published (by quote) | *Decided* (940 nm, PI); the 6 mm lens's thread per row 4 |
| 6 | CS-to-C spacer | A C-mount lens on the CS body | Teledyne **ACC-01-5004** | 1 per camera | [Teledyne](https://www.teledynevisionsolutions.com/products/cs-to-c-mount-5mm-spacer-adapter/) | 11.80 | *Decided* |
| 7 | USB host card | One controller per camera (P9 §2). Four cameras are 1.24 GB/s through one PCIe 2.0 x4 card (arithmetic) | Teledyne **ACC-01-1205** (§7.1 row 14) | 1 (2 for 8 cameras) | [card page](https://www.teledynevisionsolutions.com/products/usb-3.1-host-controller-card?model=ACC-01-1205&vertical=machine%20vision&segment=iis) | 148.00 | *Decided.* Whether one card sustains four cameras is P9 bring-up check 2 |
| 8 | USB cables | Passive runs of 5 m or less (Teledyne's recommendation); active beyond that | Teledyne **ACC-01-2300** (3 m) or **ACC-01-2301** (5 m), locking. Beyond 5 m: Newnex **FIRENEX-ULS-08 / -12 / -16** | 1 per camera | [Teledyne](https://www.teledynevisionsolutions.com/products/usb-3.1-locking-cable); [Newnex](https://newnex.com/usb-3-active-cable-a-to-micro-b.php) | 24.60 / 37.50; Newnex's price is not published | *Waits on* where the box sits. An active cable puts repeater electronics at the rig. P9 bring-up check 4 (no added neural noise) covers it |
| 9 | GPIO cables | Camera GPIO to the fan-out board and the sync box | Teledyne **ACC-01-3009** (1 m) or **ACC-01-3010** (4.5 m) | 1 per camera | [Teledyne](https://www.teledynevisionsolutions.com/products/hirose-hr10-6-pin-circular-connector/) | 37.50 / 43.90 | *Waits on* the layout |
| 10 | Trigger fan-out board | The primary's exposure drives up to 7 secondaries' opto inputs, each needing 3.5–7 mA at 2.6 V or more | custom: wl-sync's comparator front end, then one SN74AHCT541 channel and one 47 Ω resistor per secondary (§7.4) | 1 | [FLIR I/O table](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/InputOutputControl.htm); wl-sync at `92714ce` | parts only, not priced | **Needs a design check** |
| 11 | Behavior-group sync wiring | The primary samples the barcode every frame; the group's ExposureActive goes to GPIO27 (P9 §2; S3 §8) | Barcode from wl-sync's `CAM_SYNC_BEH1` BNC into the primary's Line 0. The primary's Line 1 (opto output) to wl-sync J6B, which is GPIO27. The primary's Line 2 to the fan-out input | wiring | [FLIR I/O table](https://softwareservices.flir.com/BFS-U3-16S2/latest/40-Installation/InputOutputControl.htm) | — | *Decided* (S3, P9). **Line 3 must not take the barcode**: its input high is 3.6 V at most, and the barcode is 5 V logic. Driving ExposureActive on Lines 1 and 2 at once is **UNVERIFIED** in Spinnaker. Only one of wl-sync's four behavior barcode BNCs is used |
| 12 | Camera box: CPU | Acquisition and file writing for 4–8 streams; the lanes for x8/x8 | Intel **Core Ultra 7 265K**: 20 cores (8 P + 12 E); 24 PCIe lanes, in configurations up to 1x16+2x4 or 2x8+2x4; 125 W base, 250 W maximum turbo; up to 256 GB DDR5 | 1 | [Intel](https://www.intel.com/content/www/us/en/products/sku/241063/intel-core-ultra-7-processor-265k-30m-cache-up-to-5-50-ghz/specifications.html) | RCP 394–404 | *Decided* for the list. The brand is the PI's call. Chosen partly because Intel publishes a US price. AMD's store redirected this session to its EU prices |
| 13 | Motherboard | GPU and the first USB card on CPU lanes (x8/x8). A second USB card, for 8 cameras, on a slot of x4 or wider | ASUS **ProArt Z890-Creator WiFi**: 2 × PCIe 5.0 x16 (x16 or x8/x8); 1 × PCIe 4.0 x16 at x4 from the chipset, disabled when M.2_5 is in use; 5 × M.2; 10 GbE and 2.5 GbE | 1 | [ASUS spec](https://www.asus.com/motherboards-components/motherboards/proart/proart-z890-creator-wifi/techspec/); [ASUS US page](https://www.asus.com/us/motherboards-components/motherboards/proart/proart-z890-creator-wifi/) | 489.99 (ASUS Store) | *Decided* for the list. The 10 GbE port is for the copy to wl-nas |
| 14 | RAM | Acquisition buffers; no swapping | Corsair **Vengeance 32 GB (2 × 16 GB) DDR5-4800 CL40**, CMK32GX5M2A4800C40 | 1 kit | [Corsair DDR5 page](https://www.corsair.com/us/en/c/memory/ddr5-ram) | 399.99 (sale; list 505.99) | *Decided.* 32 GB, not 64: Corsair's 64 GB kits were 780–1,040 that day |
| 15 | GPU | Two or more NVENC, within the 12-session cap (§7.5) | NVIDIA **GeForce RTX 5070 Ti**: 2 × ninth-generation NVENC; 300 W; NVIDIA asks for 750 W of system power | 1 | [NVIDIA 5070 family](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/); [NVIDIA matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new) | from 749 (NVIDIA's "starting at"; partner boards vary) | *Waits on* P9's encoder measurement. It is the task PC's GPU too (§4), so the lab runs one driver line |
| 16 | Video NVMe | 4 cameras for 12 h at an ASSUMED 10:1 is 5.37 TB (§7.6) | 2 × Samsung **990 PRO 4 TB** (MZ-V9P4T0B/AM), 8 TB in all | 2 | [Samsung](https://www.samsung.com/us/memory-storage/nvme-ssd/990-pro-pcie-4-0-nvme-ssd-4tb-sku-mz-v9p4t0b-am/) | 1,099.99 each | *Waits on* P9's measured bitrate. The drive count is the *PI's call* against the budget (§7.6) |
| 17 | Power supply | 750 W or more (NVIDIA), with the CPU's 250 W turbo | Corsair **RM850e**, CP-9020296-NA | 1 | [Corsair PSU page](https://www.corsair.com/us/en/c/psu) | 115.99 (sale; list 144.99) | *Decided* |
| 18 | Case | ATX; a 360 mm radiator | Corsair **FRAME 4000D RS ARGB**, CC-9011296-WW: ATX and E-ATX; 360 mm radiators front and top; GPUs up to 430 mm; 7 slots | 1 | [Corsair](https://www.corsair.com/us/en/p/pc-cases/cc-9011296-ww/frame-4000d-rs-argb-modular-mid-tower-pc-case-cc-9011296-ww) | 89.99 (sale; list 124.99) | *Decided* |
| 19 | CPU cooler | LGA 1851 | Corsair **NAUTILUS 360 RS**, CW-9060089-WW (LGA 1851 listed) | 1 | [Corsair](https://www.corsair.com/us/en/p/cpu-coolers/cw-9060089-ww/nautilus-360-rs-liquid-cpu-cooler-cw-9060089-ww) | 89.99 (sale; list 109.99) | *Decided* |
| 20 | Behavior lamp (contingent) | Only if the passive 940 nm image is too dark (P9 §2; bring-up check 3). The tracker's LED is collimated onto the eye, so the body is the likely dark view | a second Thorlabs M940L3 + LEDD1B + KPS201 chain, diffused rather than collimated (diffuser not chosen) | 0–1 | as §7.1 row 5 | 274.55 + 380.04 + 43.15 | *PI's call* after bring-up check 3. Strobing it in the tracker's off-time needs one clock (P9 §2); the LEDD1B's modulation input was not read (**UNVERIFIED**). **Interference with the tracker must be proven absent at bring-up**: P1 and P4 unchanged, and no stray 940 nm in the tracker's images |
| 21 | Camera mounts | Face and body views from several angles (3D) | 80/20 1010 rails on the rig frame. Per camera: Teledyne **ACC-01-0003** tripod adapter (1/4"-20) and a 1/4"-20 ball head | 1 per camera | [Teledyne](https://www.teledynevisionsolutions.com/products/tripod-adapter-for-bfs-30mm-bfly-cmln-cm3-ffmv-fl2-fl3-fmvu/) | 11.80; ball head **UNVERIFIED** | *Waits on* rig geometry |
| 22 | Interim offload | Until wl-nas exists, video stays on the box (P9 §5) | not chosen | — | — | — | *PI's call.* At 10:1 the 8 TB holds one worst-case session (12 h, 4 cameras), and P9 §4 opens a session paused when the disk is short |

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

- **Why these lenses.** Each chosen lens is slightly shorter than the computed focal length,
  so its field is at least the assumed one. The image circles (11 mm and 9 mm) cover the
  sensor's 6.21 mm diagonal.
- **NIR.** Both lenses are Edmund's C VIS-NIR series, coated for 425–1000 nm and designed for
  NIR use. No focus-shift figure at 940 nm is published, so focus is set under 940 nm light.
- **Rerun when the geometry is set.** Change u and the field, and recompute f.

### 7.4 The trigger fan-out board (needs a design check)

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

**The proposed circuit**, built from two stages wl-sync already uses (wl-sync at `92714ce`):

1. **Input.** The primary's Line 2, pulled up to +5 V on the board, into a copy of wl-sync's
   frame-time front end (`hardware/breakout/frame-time-inputs.md` §1–§4): 100 Ω, a BAT54S
   clamp, and an LM339 on +12 V with a 2.50 V threshold and about 33 mV of hysteresis. It is a
   comparator because Line 2's low level is unpublished. A TTL input's margin would be a
   coincidence, which is wl-sync's own reasoning for the opto output.
2. **Output.** One SN74AHCT541, with one channel and one 47 Ω series resistor per secondary.
   That is how wl-sync drives its five camera BNCs: its finding F4 was one output driving
   several coax runs (`hardware/README.md`). Seven secondaries at 7 mA at most are 49 mA,
   inside the part's 75 mA package limit and its 8 mA recommended per output (wl-sync
   `datasheet-params.toml`, `[sn74ahct541]`). The eighth channel is a monitor output.
3. **Power and ground.** +12 V in for the LM339, and +5 V regulated on the board for the
   pull-ups and the buffer. The board's ground is the primary's camera ground (pin 6) and
   each secondary's opto ground (pin 5), so the secondaries stay isolated.
4. **Line 1 stays wl-sync's.** Its front end supplies its own pull-up. A second pull-up on
   the same output would move FLIR's operating point.
5. **Polarity.** Which edge starts a secondary's exposure is set in the camera file (P9 §3)
   and verified at bring-up.

**The design check must settle:**

- the AHCT541's output high at 7 mA against the opto input's 2.6 V (not pinned by wl-sync,
  so **UNVERIFIED** here);
- whether Lines 1 and 2 can both carry ExposureActive (§7.2 row 11);
- the secondaries' trigger latency, which FLIR does not publish, so the primary-to-secondary
  exposure skew is measured with every camera imaging one LED pulse.

No off-the-shelf fan-out was verified. A lab pulse distribution amplifier would do if each
output sources 7 mA at 2.6 V or more.

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

### 7.6 The camera box and the budget

**Storage: the arithmetic.**

- **Raw.** 1440 × 1080 × 1 B × 200 fps = 311.04 MB/s per camera. That is 1.244 GB/s for 4
  cameras and 2.488 GB/s for 8.
- **ASSUMED compression 10:1.** This is a round number, not a measurement and not a
  published figure. P9 §5 requires the measured bitrate.

| Cameras | 5:1 | **10:1 (ASSUMED)** | 20:1 |
|---|---|---|---|
| 4, for 12 h (43,200 s) | 10.75 TB | **5.37 TB** (124.4 MB/s) | 2.69 TB |
| 8, for 12 h | 21.50 TB | 10.75 TB | 5.37 TB |

- **Capacity.** 8 TB holds a 12-hour, 4-camera session at any ratio of 6.7:1 or better. 4 TB
  needs 13.4:1, and holds 8.9 h at 10:1.
- **Endurance.** Samsung lists 2,400 TBW per drive, so a 5.37 TB session is about 0.1% of
  the pair's 4,800 TBW.
- **Sustained write.** Samsung publishes a sequential write figure, not a sustained rate
  after the cache. 124 MB/s (or 249 MB/s for 8 cameras) is checked in bring-up check 2.

**The camera box**, 4 cameras:

| Item | Part | Price (USD) |
|---|---|---|
| CPU | Intel Core Ultra 7 265K | 404.00 (top of Intel's range) |
| Motherboard | ASUS ProArt Z890-Creator WiFi | 489.99 |
| RAM | Corsair CMK32GX5M2A4800C40, 32 GB | 399.99 |
| GPU | NVIDIA GeForce RTX 5070 Ti | 749.00 |
| Video NVMe | 2 × Samsung 990 PRO 4 TB | 2,199.98 |
| USB card | Teledyne ACC-01-1205 | 148.00 |
| Power supply | Corsair RM850e | 115.99 |
| Case | Corsair FRAME 4000D RS ARGB | 89.99 |
| CPU cooler | Corsair NAUTILUS 360 RS | 89.99 |
| **Total** | | **4,686.93** |

**The list meets the 12-hour requirement and is over the ~$4,000 budget by $686.93** at the
day's prices:

- Four Corsair items are at sale prices; at list they add $190. The GPU is NVIDIA's
  "starting at" price.
- The NVMe is 47% of the total. Samsung's store listed its 4 TB 990 PRO at $1,099.99.

**The variant within budget** drops the second drive, for **$3,586.94**. It holds 8.9 h of 4
cameras at 10:1, and meets 12 h only if the measured ratio is 13.4:1 or better.

- **Eight cameras** add a second ACC-01-1205 ($148) in the chipset slot, and at 10:1 another
  8 TB.
- **Which variant is the PI's call**, and P9's bitrate measurement is what decides it.
- **Outside the budget:** the cameras, lenses, filters, cables and the fan-out board. So is a
  separate OS drive: the OS shares drive 1 here.
- **Not sized here:** P10's tracker running on this box later (the spike's §9 item 7).

### 7.7 What this list cannot settle yet

- **The rig geometry.** Every camera distance and field in §7.3 is ASSUMED. Where the camera
  box sits decides passive against active USB, and the GPIO lengths.
- **The measurements P9 names:**
  - the real bitrate, which sizes the NVMe and decides the budget variant;
  - NVENC throughput on our mono 1440 × 1080 video at a visually lossless preset, for 4 and
    for 8 cameras;
  - 940 nm sensitivity, since no NIR quantum efficiency is published;
  - whether the passive light is bright enough, and whether a lamp disturbs P1 and P4;
  - 12 hours at 200 fps with no drops;
  - no added neural noise.
- **The ASUS proximity sensor.** It is still open whether the Neo Proximity Sensor and pixel
  cleaning can be turned off (open item 3). How the sensor senses is not published. So
  whether the tracker's 940 nm light, or mounts under the bezel, affect it is **UNVERIFIED**,
  and the below-screen mount cannot be placed until that is known.
- **The direct-view design.** It sets the viewing distance (57–65 cm), and with it the camera
  angle, the mount, and the photodiode shields. The stereoscope drawing's recompute for
  26.5" sets the secondary mount.

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
