# Split-screen stereoscope — buildable geometry

- **Status:** proposed, for PI review and in-house build
- **Date:** 2026-08-31
- **Derives from:** S0 §5.2 (panel and viewing distance), S3 §8 (photodiode patch placement)
- **Owner:** in-house build (PI, 2026-08-31)

Every number below is computed from four inputs and recomputes if any of them move. Nothing
here is measured — **it is a drawing to build to and then verify against** (protocol V9).

---

## 1. Inputs

| Symbol | Value | Source | Confidence |
|---|---|---|---|
| Panel | 31.5" 16:9, 69.73 × 39.23 cm, 0.1816 mm pitch | S0 §5.1 | Panel class fixed; tandem model pending |
| `D` | **57.0 cm** optical path, eye to screen | S0 §5.2 | Ruled 2026-08-31 |
| `HW`, `HH` | 17.43 cm, 19.61 cm — half-viewport on screen | panel / 4, panel / 2 | Derived |
| `E` | half-IPD, **variable per animal** | measured per animal | **A build parameter, not a constant** |

**`E` varies by animal, so the rig is adjustable rather than fixed** (PI, 2026-08-31). That is
not a tolerance on a nominal — it is the design constraint that shapes the mechanics, and §4
replaces the fixed-distance table with the relationship the adjustment must hold.

---

## 2. The arrangement: a periscope per eye

Two flat first-surface mirrors per eye at 45°, translating each eye's optical axis laterally
outward onto the centre of its own screen half. Plan view, not to scale:

```
                          PANEL  (69.73 cm wide, split at the midline)
    ╔═════════════════════════════╦═════════════════════════════╗
    ║      LEFT VIEWPORT          ║        RIGHT VIEWPORT       ║
    ╚═════════════════════════════╩═════════════════════════════╝
         ▲                        :  dead   :                ▲
         │  axial 34.17 cm        : strip   :                │
         │                        :         :                │
      ┌──┴──┐                     :         :             ┌──┴──┐
      │ M2L │◄────────────────┐   :         :   ┌────────►│ M2R │     mirror plane,
      └─────┘   lateral       │   :         :   │         └─────┘     7.0 cm from eyes
       x=-18.3  15.83 cm      │   :         :   │          x=+18.3
                              │   :         :   │
                            ┌─┴───▼─┐   ┌───▼─┴─┐
                            │  M1L  │   │  M1R  │   roof pair, ridge on the midline
                            └───────┘   └───────┘
                                ▲           ▲
                                │           │        7.0 cm
                             ( L eye )   ( R eye )   x = ∓1.60 cm
```

**Two reflections per eye, so parity is preserved** — no software mirror-flip, which a
single-mirror design would have required for natural images and any chiral stimulus.

**Both mirrors sit in one plane**, 7.0 cm in front of the eyes. The lateral run passes across
the front of the face in that plane.

---

## 3. The numbers that follow

| Quantity | Value |
|---|---|
| Lateral shift per eye (outward) | `HW − E` = **15.83 cm** |
| Optical path (eye → M1 → M2 → screen) | 7.00 + 15.83 + 34.17 = **57.00 cm** |
| **Physical** axial distance, eye to screen | `D − shift` = **41.17 cm** |
| Mirror plane, from eyes | **7.0 cm** |
| Mirror plane, from screen | **34.17 cm** |
| M1 centres (roof pair) | x = ∓1.60 cm, meeting at the ridge x = 0 |
| M2 centres | x = ∓18.31 cm |
| M1 mirror size (45°, incl. √2) | **53 × 48 mm** each |
| M2 mirror size (45°, incl. √2) | **173 × 157 mm** each |
| Field per eye, temporal | **±17.0°** |
| Field per eye, nasal | **12.9°** |
| Field per eye, vertical | **±19.0°** |
| Resolution | **56 px/deg** (4K), 28 px/deg (FHD/480) |

**The mirrors buy 15.8 cm of optical path.** The screen sits physically 41 cm from the animal
while appearing at 57 cm — which is what makes a 57 cm viewing distance fit inside a chair-sized
enclosure at all.

---

## 4. Adjustability: what moves, and the rule it holds

The two eyes are close together, so the M1 mirrors meet at a ridge on the midline and each
eye's nasal field is clipped where its beam would cross it. The clip angle is `atan(E / a)`.

**Symmetric field is chosen** (PI, 2026-08-31), which fixes the relationship the adjustment
must hold rather than a distance:

> **`a = E / tan(17°) = 3.27 · E`**

Set it and nasal equals temporal at ±17°. Set `a` longer and you trade nasal field for an
unviewed centre strip (§5 fallback); the rig can do either, but symmetric is the default
because it is the thing least likely to surprise an analysis.

| IPD | `E` | M1 at `a` | Screen at `Z` | Lateral shift |
|---|---|---|---|---|
| 30 mm | 1.50 cm | 4.91 cm | 41.07 cm | 15.93 cm |
| 32 mm | 1.60 cm | 5.23 cm | 41.17 cm | 15.83 cm |
| 34 mm | 1.70 cm | 5.56 cm | 41.27 cm | 15.73 cm |
| 36 mm | 1.80 cm | 5.89 cm | 41.37 cm | 15.63 cm |
| 38 mm | 1.90 cm | 6.21 cm | 41.47 cm | 15.53 cm |

### 4.1 Three things move, and one does not

1. **M1 axial distance**, 4.9 → 6.2 cm. The adjustment that matters.
2. **M1 lateral position**, ±1.5 → ±1.9 cm, so each near mirror stays centred on its eye. The
   **ridge stays on the midline at x = 0** for every IPD — that is a property of the symmetric
   condition, not a coincidence, and it is what lets the roof be a fixed reference.
3. **M2 axial position**, which must track M1 because the two mirrors have to stay **coplanar**
   for the translation to be pure. Mechanically: **one axial carriage per eye carrying both
   mirrors**, with a small lateral slide for M1 alone.
4. **M2 lateral position does not move.** It sits at x = ∓17.43 cm — the centre of its screen
   half — for every IPD, because the eye's axis after translation always lands there by
   construction. It is the fixed datum the whole build can be squared to.

### 4.2 One mirror pair covers the range

**M1: 54 × 38 mm. M2: 188 × 133 mm.** Sized for the largest IPD; smaller animals simply use
less of the surface. There is no need for per-animal optics, only per-animal positions.

### 4.3 Screen distance is measured, not adjusted

`Z` varies over just 4 mm across the whole IPD range — 0.7% of the optical path. Rather than
add a fourth adjustment for it, **fix the panel and measure each eye's path per animal**, which
V9 requires anyway. deg/pixel is then derived from the measurement instead of asserted from a
nominal.

### 4.4 The consequence for operations

**The optics are now per-animal state, so they are per-session state.** Changing animals means
re-setting `a` and the M1 slides, which invalidates the previous geometry. Therefore:

- the mirror geometry and both measured optical paths go in **every session's config snapshot**,
  beside the gaze mapping version;
- **re-verification moves into the preflight check** (parent §11.1) rather than being a
  build-time activity — at minimum the Nonius/vernier residual, which is the cheap test that
  catches a carriage that moved;
- a geometry change is a **discontinuity of the same class as a parameter change** (P16), and is
  event-coded and recorded as one.

---

## 5. Photodiode patches — the problem the geometry solves

S3 §8 requires both patches outside **both** viewports, or the flip patch (alternating every
refresh) becomes a flickering distractor in one eye's field. Naively that is impossible: two
viewports tile the panel exactly, so every pixel is seen by one eye.

**Symmetric field means there is no centre strip** — that space is exactly what the symmetric
condition gives back to the nasal field. So the patches go to a **horizontal strip, created by
stopping the M2 aperture vertically.**

Vertical field is the surplus dimension: ±19.0° against a ±17.0° horizontal requirement. Stopping
M2 to ±17.0° vertical costs nothing that matters and yields:

| Vertical stop | Strip, top and bottom | Full panel width |
|---|---|---|
| ±18.0° | 1.09 cm | 69.73 cm |
| ±17.5° | 1.64 cm | 69.73 cm |
| **±17.0°** | **2.18 cm** | **69.73 cm** |
| ±16.5° | 2.73 cm | 69.73 cm |

**Recommended: stop to ±17.0°, put both patches in the bottom strip.** 2.18 cm × 69.73 cm is
ample for two patches, keeps vertical field equal to horizontal, and puts the flip patch as far
from any stimulus as the panel allows.

The centre strip remains available as a **fallback**: lengthening `a` beyond `3.27·E` trades
nasal field for it, at 4.4 cm of strip per 1 cm of extra distance. Use it only if the M2 vertical
stop turns out to be mechanically awkward.

**Whichever is chosen, the patches must be verified dark to each eye during bring-up**, not
assumed from geometry — a stray reflection off a mirror edge would put the flip patch back in
the field, and that is a V9 item.

---

## 6. Vergence is a software constant, not a mechanical one

The periscope translates without deviating, so both eyes' axes leave parallel and normal to the
panel. A stimulus drawn at identical viewport coordinates therefore has **zero retinal
disparity and is perceived at optical infinity**, while accommodation sits at 57 cm — the
ordinary stereoscope conflict.

To place zero-disparity at the screen distance instead, the axes must converge by
`2·atan(E/D)` = **3.2°**. Do this **in software**, as a constant horizontal offset between the
two viewports, not by angling the mirrors:

- it is adjustable per animal without touching hardware,
- it is recorded in the session snapshot like any other parameter,
- it survives an IPD that turns out different from the placeholder, and
- it does not demand angular precision from a mechanical build.

**Angling the mirrors to converge is the mistake to avoid.** It bakes one animal's IPD into
metal, and it makes the two optical paths unequal — which S0's V9 already forbids assuming.

---

## 7. Build and verification checklist

**Build**
1. First-surface mirrors only. A second-surface mirror gives a ghost image displaced by twice
   the glass thickness, which on a stereoscope reads as a faint uncorrelated second image to one
   eye — a genuine confound for binocular work.
2. M1 ridge on the midline, both faces at 45° ± 0.25°, meeting with no gap and no overlap.
3. M2 faces parallel to their M1 counterpart, so the translation is pure.
4. Independent fine adjustment on each M2, in the horizontal axis at minimum.
5. Everything matte black except the mirror faces; baffle the lateral run so no direct screen
   light reaches an eye.

**Verify before an animal (V9)**
1. **Measure each eye's optical path independently.** They are equal only if the mirrors are;
   S0 §5.2 already forbids deriving them from the panel distance.
2. Nonius / vernier alignment target, run at every session start, residual recorded.
3. Confirm each eye sees only its own viewport — occlude one half, check the other eye is
   unaffected.
4. Confirm both photodiode patches are dark to both eyes.
5. Per-half photometry (V9), which on a split panel is an interocular check, not a uniformity
   check.

---

## 8. What is still open

| # | Item | Owner |
|---|---|---|
| 1 | Measure `E` (IPD) per animal | PI — sets `a` via §4's rule |
| 2 | ~~M1 distance~~ **Answered: symmetric field, `a = 3.27·E`, adjustable per animal** | — |
| 3 | Patch location — **bottom strip via a ±17° M2 vertical stop** — confirm with `wl-sync` | PI + `wl-sync` |
| 4 | ~~Chair and head-post clearance~~ **Build to it and find out** (PI, 2026-08-31). If the muzzle fouls the carriage, symmetric field is unreachable and §4's table is re-derived from the achievable clearance instead of from IPD — moving the near mirrors out trades nasal field for a central strip, which is then where the photodiode patches go instead of the bottom strip | commissioning |
| 5 | Enclosure and baffling against ambient light | build |
