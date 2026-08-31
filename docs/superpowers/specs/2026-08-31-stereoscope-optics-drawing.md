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
| `E` | **1.60 cm** half-IPD (32 mm) | **PLACEHOLDER — must be measured per animal** | **Unverified** |

**`E` is the only soft number and it drives the whole layout.** Measure it on the actual
animals before cutting anything; §5 gives the sensitivity.

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

## 4. The one real trade, and it is science-facing

The two eyes are only 3.2 cm apart, so the two M1 mirrors must meet at a ridge on the midline
and **each eye's nasal field is clipped where its beam would cross that ridge.** The clip angle
is `atan(E / a)`, where `a` is the eye-to-M1 distance. Moving M1 closer recovers nasal field and
shrinks the mirrors; moving it away loses nasal field.

| M1 at | Nasal field | Temporal | Central dead strip | M1 size | M2 size |
|---|---|---|---|---|---|
| 5.2 cm | ±17.0° (symmetric) | ±17.0° | **0 cm** | 45 × 36 mm | 182 × 145 mm |
| 6.0 cm | 14.9° | 17.0° | 4.5 cm | 49 × 41 mm | 177 × 150 mm |
| **7.0 cm** | **12.9°** | **17.0°** | **8.8 cm** | **53 × 48 mm** | **173 × 157 mm** |
| 8.0 cm | 11.3° | 17.0° | 12.1 cm | 57 × 55 mm | 170 × 164 mm |
| 10.0 cm | 9.1° | 17.0° | 16.6 cm | 66 × 69 mm | 170 × 178 mm |

**The clipped field is not lost screen — it becomes a strip down the centre of the panel that
neither eye can see.** Which is exactly what §5 needs.

At 5.2 cm the field is symmetric and there is no dead strip; at 7 cm the nasal field still
clears a 10° array by 2.9° and the strip is 8.8 cm wide. **7.0 cm is the recommendation**, but
this is a trade between nasal field and patch placement, and it is yours.

**Sensitivity to `E`.** Because the clip angle is `atan(E/a)`, a 10% error in IPD moves the
nasal field by about 1.3°. Measure it; do not inherit it from the literature.

---

## 5. Photodiode patches — the problem the geometry solves

S3 §8 requires both patches outside **both** viewports, or the flip patch (alternating every
refresh) becomes a flickering distractor in one eye's field. Naively that is impossible: two
viewports tile the panel exactly, so every pixel is seen by one eye.

The nasal clip creates the space. At M1 = 7.0 cm the viewports occupy screen x ∈ [−34.86, −4.41]
and [+4.41, +34.86], leaving **a central strip 8.8 cm wide that neither eye sees**.

Three candidate locations, in preference order:

1. **Central strip (recommended).** Free — it is the nasal clip, not a sacrifice. 8.8 cm × full
   height at M1 = 7 cm. Both patches fit with room to spare, and it is the region furthest from
   any stimulus.
2. **Bottom or top strip.** Costs vertical field, which is the field in surplus (±19° against a
   ±17° horizontal requirement). Created by sizing the M2 aperture to exclude the strip. Use if
   the central strip is wanted for a septum instead.
3. **Outer strips.** Costs temporal field, which is the binding dimension. Avoid.

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
| 1 | Measure `E` (IPD) on the actual animals | PI — everything in §3 shifts with it |
| 2 | M1 distance: 5.2 cm (symmetric field, no strip) vs 7.0 cm (12.9° nasal, 8.8 cm strip) | PI — §4 |
| 3 | Patch location, once §2 is chosen | PI + `wl-sync` |
| 4 | Whether the chair and head-post allow a mirror 7 cm from the eyes | build |
| 5 | Enclosure and baffling against ambient light | build |
