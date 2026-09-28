# Split-screen stereoscope — buildable geometry

- **Status:** proposed, for PI review and in-house build
- **Date:** 2026-08-31; **revised 2026-09-28**
- **Derives from:** S0 §5.1–§5.2 (panel and screen distance), S3 §8 (photodiode patch placement)
- **Owner:** in-house build (PI, 2026-08-31)

> **Revised 2026-09-28.** Two PI decisions moved every number here:
>
> - **the display** is now the 26.5-inch ASUS PG27UCDM (2026-09-27, S0 §5.1), recomputed
>   from its published active area;
> - **the screen is fixed 50 cm from the eyes, physically, in both setups** (2026-09-28). The
>   optical path was ruled 57 cm on 2026-08-31 and reaffirmed that morning after comparing
>   50 cm. The same day, the PI fixed the physical distance instead, and the path followed:
>   `D = Z + HW − E`, 63.15 cm at `E` = 1.6 cm (§1, §4.4).
>
> The recompute also fixes four errors that the panel comparison
> (`docs/research/2026-09-27-panel-27-vs-32.md` §9) found in this drawing's own relations, each
> re-derived here rather than taken from it:
>
> 1. **the nasal clip** was `atan(E/a)`; a 45° roof with its ridge on the midline clips at
>    `atan(E/(a − E))`, so the symmetric position is `E(1 + 1/tan θ)`, not `E/tan θ` (§4);
> 2. **the mirror sizes** ignored the 45° footprint's trapezoid, whose temporal end is the
>    tallest, so rectangles cut to them vignette the field's temporal corners (§3.1);
> 3. **§3 put M2's center at x = ∓18.31 cm**, against its own 1.60 + 15.83 = 17.43; M2 sits at
>    `∓HW` (§3);
> 4. **§3's mirror plane, 7.0 cm from the eyes and 34.17 cm from the screen,** predated the
>    symmetric rule; the plane is at `a` (§3).
>
> It also records the ±10° field requirement (PI, 2026-09-27), shows that the ridge is not a
> stop (§4.2), and records the PI's two answers of 2026-09-28: **a midline divider** blocks the
> path past the ridge (§4.2), and **the field is set by a removable mask at the panel, starting
> at ±12°**, with the mirrors cut for the full viewport (§5).

Every number below is computed from the inputs in §1 and recomputes if any of them move.
Nothing here is measured — **it is a drawing to build to and then verify against** (protocol V9).
Direct viewing is not covered here: it shares the fixed screen at 50 cm and is being designed
separately.

---

## 1. Inputs

| Symbol | Value | Source | Confidence |
|---|---|---|---|
| Panel | ASUS ROG Swift OLED **PG27UCDM**: "26.5-inch viewable", 3840 × 2160, active area **58.997 × 33.293 cm** | ASUS [spec page](https://rog.asus.com/us/monitors/27-to-31-5-inches/rog-swift-oled-pg27ucdm/spec/) ("Display Viewing Area (HxV) : 589.97 x 332.93 mm") and [product page](https://rog.asus.com/us/monitors/27-to-31-5-inches/rog-swift-oled-pg27ucdm/) ("27-inch (26.5-inch viewable)"), both read 2026-09-28; S0 §5.1 | Published by the maker. Chosen by the PI 2026-09-27 |
| Pitch | **0.15364 mm** horizontal | derived: 589.97 mm / 3840 | ASUS lists "0.153mm". The area gives 0.15413 mm vertically (332.93 / 2160); whether the pixels are square is not published: **UNVERIFIED** |
| `Z` | **50.0 cm**, eye to screen, **physical**, the same in both setups | PI, 2026-09-28: "I want the screen to be the same physical distance from the animal in stereoscope and the direct viewing. The stereoscope is a device that is removable and everything else is fixed." | **Ruled.** The screen is fixed in place (a locked arm or stand with a stop), measured once at setup and re-checked in the regular rig checks |
| `D` | **63.15 cm** optical path at `E` = 1.6 cm; **62.85–63.25 cm** over IPD 30–38 mm | derived: `D = Z + HW − E` (§3, §4.4) | **Per animal**, and measured per eye (V9) |
| `HW`, `HH` | 14.749 cm, 16.647 cm — half-viewport on screen | active width / 4, active height / 2 | Derived |
| `E` | half-IPD, **variable per animal** | measured per animal | **A build parameter, not a constant** |
| `θ` | the full viewport, `atan(HW/D)` = **13.15°** at `E` = 1.6 cm (13.13–13.21° over IPD); the **mask** stops it, **starting at ±12°**; the **requirement** is ±10° | PI, 2026-09-27 ("for the stereoscope setup +/- 10 deg is enough, most of the experiments will not be in the stereoscope") and 2026-09-28 (the mask) | Ruled (§5) |

**The area, not the diagonal.** ASUS's "26.5-inch" is rounded: the published area's own diagonal
is 67.74 cm (26.67 in), and its aspect is 1.772:1 rather than 16:9. S0 §5.2's diagonal form fed
26.5 in would put each viewport edge 0.6–0.9% short, so every number here starts from the area.

**`E` varies by animal, so the rig is adjustable rather than fixed** (PI, 2026-08-31). That is
not a tolerance on a nominal — it is the design constraint that shapes the mechanics, and §4
replaces the fixed-distance table with the relationship the adjustment must hold. With the
screen fixed, it also makes the optical path, and so the field and deg/pixel, per animal (§4.4).

---

## 2. The arrangement: a periscope per eye

Two flat first-surface mirrors per eye at 45°, translating each eye's optical axis laterally
outward onto the center of its own screen half. Plan view, not to scale, at `E` = 1.6 cm, with
the mirrors built for the full viewport (§5):

```
                      PANEL  (59.00 cm active width, split at the midline)
                      fixed at Z = 50 cm from the eyes
    ╔═════════════════════════════╦═════════════════════════════╗
    ║      LEFT VIEWPORT          ║        RIGHT VIEWPORT       ║
    ╚═════════════════════════════╩═════════════════════════════╝
         ▲                                                   ▲
         │  axial Z − a = 41.55 cm                           │
         │                                                   │
      ┌──┴──┐                                             ┌──┴──┐
      │ M2L │◄────────────────┐               ┌──────────►│ M2R │    mirror plane,
      └─────┘   lateral       │               │           └─────┘    a = 8.45 cm from the eyes
      x=-14.75  13.15 cm      │               │           x=+14.75
                              │               │
                            ┌─┴───▼─┐   ┌───▼─┴─┐
                            │  M1L  │   │  M1R  │   roof pair, ridge on the midline,
                            └───────┘   └───────┘   a − E = 6.85 cm from the eyes
                                ▲           ▲
                                │           │        a = 8.45 cm
                             ( L eye )   ( R eye )   x = ∓1.60 cm
```

**Two reflections per eye, so parity is preserved** — no software mirror-flip, which a
single-mirror design would have required for natural images and any chiral stimulus.

**Both mirrors' centers sit in one plane**, `a` in front of the eyes: the eye's axis leaves M1
along x, at `z = a`, and must meet M2 there. The lateral run passes across the front of the
face in that plane.

---

## 3. The numbers that follow

At `E` = 1.6 cm, with the mirrors built for the full viewport (§5). `x` is measured from the
midline.

| Quantity | Relation | Value |
|---|---|---|
| **Physical** axial distance, eye to screen | `Z`, fixed (§1) | **50.00 cm** |
| Lateral shift per eye (outward) | `HW − E` | **13.15 cm** |
| **Optical path** (eye → M1 → M2 → screen) | `D = Z + (HW − E)` = `a + (HW − E) + (Z − a)` | 8.45 + 13.15 + 41.55 = **63.15 cm** |
| M1 axial distance: the mirror plane, from the eyes | `a = E(1 + D/HW)` (§4) | **8.45 cm** |
| Roof ridge, from the eyes | `a − E` | 6.85 cm |
| Mirror plane, from the screen | `Z − a` | **41.55 cm** |
| M1 centers (roof pair) | `x = ∓E` | x = ∓1.60 cm, meeting at the ridge x = 0 |
| M2 centers | `x = ∓HW` | **x = ∓14.75 cm** |
| Field per eye, temporal | `atan(HW/D)` | **±13.15°** |
| Field per eye, nasal | `atan(E/(a − E))` (§4) | **13.15°** |
| Field per eye, vertical | `atan(HH/D)`, before the mask (§5) | **±14.77°** |
| Resolution | S0 §5.2's mean, `1920 / (2 × 13.15°)` | **73.0 px/deg** (4K); 71.7 at the center and 75.7 at the viewport's side edge, from `D / (pitch · cos² e)` px per radian |
| Pixel size at the center | `pitch / D` | **0.84 arcmin** |
| FHD/480 | — | not listed for this panel (S0 §5.1) |

**The mirrors add `HW − E` of optical path, 13.15 cm here.** The screen sits physically 50 cm
from the animal in both setups, and appears at 63.15 cm through the stereoscope.

### 3.1 Mirror sizes: the 45° footprint is a trapezoid

Unfold the periscope so each eye looks straight at its viewport. A ray leaving the eye with
direction `(p, v, 1)` — `p` the horizontal slope, positive nasal, and `v` the vertical —
meets a 45° mirror whose axis point is at optical distance `c` at an unfolded depth of
`c / (1 + p)`. On the mirror face, measured from where the eye's axis meets it:

- along the face: `s = √2 · c · p / (1 + p)`;
- height: `y = c · v / (1 + p)`.

So a rectangular field — temporal `tan θT`, nasal `tan θN`, vertical `tan θV` — lands as a
**trapezoid**:

- length `L = √2 · c · (tan θN / (1 + tan θN) + tan θT / (1 − tan θT))`;
- height `2c · tan θV / (1 − tan θT)` at the temporal end, `2c · tan θV` on the axis, and
  `2c · tan θV / (1 + tan θN)` at the nasal end.

M1 has `c = a`; M2 has `c = a + (HW − E)`. **The temporal end is the tallest:** 1.30 times the
height on the axis at ±13.15°. The drawing's old relation, `√2 · c · (tan θT + tan θN)` by
`2c · tan θV`, was the linear approximation, cut to the height on the axis. It is short in both
directions and loses the temporal corners.

**The mirrors are cut for the full viewport** (PI, 2026-09-28; §5), with the vertical field
equal to the horizontal. Sizes in mm, **length along the 45° face × height at the temporal
end** (height at the nasal end in parentheses); §4.3 says why the largest IPD sizes the pair.

| `E` | M1, exact | M1, to cut | M2, exact | M2, to cut |
|---|---|---|---|---|
| 1.6 cm | 59.0 × 51.5 (32.0) | 65 × 62 | 150.9 × 131.6 (81.8) | 161 × 142 |
| **1.9 cm** | 70.2 × 61.3 (38.0) | **76 × 72** | 160.5 × 140.1 (86.8) | **171 × 151** |

With no vertical stop at all (±14.83° at `E` = 1.9 cm), the heights would be 69.2 mm (M1) and
158.1 mm (M2).

**"To cut" is the trapezoid's bounding rectangle plus a 5 mm margin on every free edge,**
rounded up: M1 gains 5 mm of length at its temporal end only, since its nasal edge is the ridge
and cannot move, and 10 mm of height; M2 gains 10 mm in both. **The 5 mm is an allowance, not a
derivation.** A pupil of radius `r` needs `√2 · r / (1 − tan θT)` more mirror along the face at
the temporal end (1.85·r at ±13.15°), so 5 mm covers a pupil up to 5.4 mm across at the nominal
eye position — or a smaller pupil plus some eye placement error or gaze-driven pupil shift.
The macaque pupil under the rig's luminance is a bring-up measurement, **UNVERIFIED** here, and
V9 tests the margin (§7).

**A margin and a stop are different edges.** An oversized mirror cannot also be the field stop,
which is why the field is stopped by a mask at the panel (§5). A straight edge on a 45° mirror
would stop at a sloped line on the screen, because the height it subtends scales with `1 + p`.

---

## 4. Adjustability: what moves, and the rule it holds

The two eyes are close together, so the M1 mirrors meet at a ridge on the midline. Put the left
eye at `x = −E`, `z = 0`, with `z` toward the screen. M1L then lies in the plane
`x + z = a − E`, which meets the midline at `z = a − E`. A ray at nasal slope `p` reaches
that plane at `x = −E + a · p / (1 + p)`, and is on M1L only while `x ≤ 0`, that is while
`p ≤ E / (a − E)`. **The nasal clip is `atan(E / (a − E))`.** The drawing used `atan(E/a)` until
2026-09-28, the angle to the midline at M1's center depth `a`; the ridge is `E` nearer the eye.

**Symmetric field is chosen** (PI, 2026-08-31), which fixes the relationship the adjustment
must hold rather than a distance. With the corrected clip, nasal equals temporal at

> **`a = E(1 + 1/tan θ)`**, which for the full viewport is `a = E(1 + D/HW)`: **5.28·E** at
> `E` = 1.6 cm

where θ is the field's half-angle. The coefficient moves slightly with `E` (5.29–5.26 over IPD
30–38 mm), because with the screen fixed `D` does (§4.4). Set `a` longer and you trade nasal
field for an unviewed center strip, 4.3 cm of strip per 1 cm of extra distance near the
full-viewport position at `E` = 1.6 cm; the rig can do either, but symmetric is the default
because it is the thing least likely to surprise an analysis. The mask at the panel stops the
field at ±12°, inside the ridge's 13.15°, so the ridge does not set the nasal edge (§5).

| IPD | `E` | Path `D` | M1 at `a` | Ridge at `a − E` | Screen at `Z` | Lateral shift |
|---|---|---|---|---|---|---|
| 30 mm | 1.50 cm | 63.25 cm | 7.93 cm | 6.43 cm | 50.00 cm | 13.25 cm |
| 32 mm | 1.60 cm | 63.15 cm | 8.45 cm | 6.85 cm | 50.00 cm | 13.15 cm |
| 34 mm | 1.70 cm | 63.05 cm | 8.97 cm | 7.27 cm | 50.00 cm | 13.05 cm |
| 36 mm | 1.80 cm | 62.95 cm | 9.48 cm | 7.68 cm | 50.00 cm | 12.95 cm |
| 38 mm | 1.90 cm | 62.85 cm | 10.00 cm | 8.10 cm | 50.00 cm | 12.85 cm |

### 4.1 Three things move, and one does not

1. **M1 axial distance**, 7.93 → 10.00 cm. The adjustment that matters.
2. **M1 lateral position**, ±1.5 → ±1.9 cm, so each near mirror stays centered on its eye. The
   **ridge stays on the midline at x = 0** for every IPD — the two sides mirror each other
   about it — and that is what lets the roof be a fixed reference. It moves only axially, to
   `a − E`: 6.43 → 8.10 cm.
3. **M2 axial position**, which must track M1 because the two mirrors have to stay **coplanar**
   for the translation to be pure. Mechanically: **one axial carriage per eye carrying both
   mirrors**, with a small lateral slide for M1 alone.
4. **M2 lateral position does not move.** It sits at x = ∓14.75 cm — the center of its screen
   half — for every IPD, because the eye's axis after translation always lands there by
   construction. It is the fixed datum the whole build can be squared to.

### 4.2 The ridge is not a stop

**Past the clip, a ray is not blocked.** It crosses the midline between the eyes and the ridge,
meets the other eye's M1 face, and the other periscope carries it to the **other eye's
viewport**. It lands `HW − 2E + D · p` from the midline on the far half, so the left eye,
looking more than 13.15° nasally, sees the right viewport's outer 2E = 3.2 cm. The ±12° mask
covers only the outer 1.33 cm of it; the rest is inside the right eye's field.

**A midline divider blocks it** (PI, 2026-09-28): a thin matte-black plate on the midline, from
the ridge back toward the face, stopping short of the nose, its face end trimmed to the animal
at fitting. The animal's own nose was the alternative; whether it reaches far enough forward is
**UNVERIFIED** (the muzzle clearance is found at build, §8 item 4), so it is not relied on.

**The clip is also soft.** A pupil of diameter `d` sees the ridge from a spread of positions, so
the nasal edge fades over `d / (a − E)` radians: 0.84° per mm of pupil at `E` = 1.6 cm (0.71–0.89°
over IPD). The fade reaches inside a nasal stop at θ once the pupil is wider than
`2(E − (a − E) · tan θ)`:

- **at the ±12° mask, 2.9 mm** at `E` = 1.6 cm (2.7–3.6 mm over IPD 30–38 mm). A wider pupil
  sees the mask's nasal edge dimmed by the ridge, not cut by the mask;
- **at the ±10° requirement, 7.8 mm** (7.3–9.4 mm).

The macaque pupil under the rig's luminance is a bring-up measurement, **UNVERIFIED** here (§8
item 8).

### 4.3 One mirror pair covers the range

Size for the largest IPD, and smaller animals use less of the surface: both trapezoids scale
with their distance, so with M1 registered at the ridge and M2 at x = ∓HW, the `E` = 1.5 cm
footprint lies inside the `E` = 1.9 cm one. **Cut M1 to 76 × 72 mm and M2 to 171 × 151 mm**
(§3.1). There is no need for per-animal optics, only per-animal positions.

### 4.4 The screen is fixed; the path follows

**The screen does not move** (PI, 2026-09-28): a locked arm or stand with a stop holds it at
`Z` = 50 cm from the eyes in both setups, measured once at setup and re-checked in the regular
rig checks. The stereoscope is the removable part. So the optical path is **per animal**:
`D = Z + HW − E`, 63.25 → 62.85 cm over IPD 30–38 mm, a 4 mm span, 0.6% of the path.

It is still not adjusted. **Measure each eye's path per animal**, which V9 requires anyway, and
derive deg/pixel from the measurement instead of asserting it from a nominal. The field moves
with it, ±13.13° to ±13.21°, and 71.9 to 71.4 px/deg at the center.

### 4.5 The consequence for operations

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

## 5. The field stop and the photodiode strip

**The requirement is ±10°** (PI, 2026-09-27). Through the stereoscope the panel gives ±13.15° ×
±14.77° at `E` = 1.6 cm. **The PI chose an adjustable stop** (2026-09-28): the mirrors and the
ridge are built for the full viewport (§3.1's sizes, §4's `a`), and the field is set by **a
removable matte-black mask at the panel, starting at ±12°**. A mask's edge is sharp where a
mirror's is soft, and moving it toward ±10° or out to the full viewport needs no new mirrors.
Because the mirrors stay at the full viewport, the room around the eye is theirs: the mask frees
none of it.

**The ±12° mask still fits, with less to spare.** The full field is now 1.15° outside it
horizontally (1.13–1.21° over IPD) and 2.77° vertically, against 2.51° horizontally with the
screen at 43.85 cm. §4.2 gives what that costs at the nasal edge for a wide pupil.

S3 §8 requires both photodiode patches outside **both** viewports, or the flip patch
(alternating every refresh) becomes a flickering distractor in one eye's field. Two viewports
tile the panel exactly, so every pixel is seen by one eye unless the field is stopped. **The
mask is what makes room for the patches.**

| Mask at | **±12°, the start** | ±10°, the requirement | ±13.15°, the full viewport |
|---|---|---|---|
| Field per eye | ±12° × ±12° | ±10° × ±10° | ±13.15° × ±13.15° |
| Mask opening per viewport, at the panel | 26.85 × 26.85 cm | 22.27 × 22.27 cm | 29.50 × 29.50 cm |
| **Dark strip, top and bottom**, full width | **3.22 cm** (209 px) | 5.51 cm (358 px) | 1.90 cm (123 px) |
| Dark strip, center, full height | 2.65 cm | 7.23 cm | none |
| Dark strips, outer edges | 1.33 cm each | 3.61 cm each | none |
| Largest pupil clear of the ridge's fade at the nasal edge (§4.2) | 2.9 mm (2.7–3.6) | 7.8 mm (7.3–9.4) | none: the fade straddles the edge |

Relations, at `E` = 1.6 cm: the opening `2D · tan θ`; strips `HH − D · tan θ`,
`2(HW − D · tan θ)` and `HW − D · tan θ`; px at the 0.15413 mm vertical pitch. **The mask is cut
once, in centimeters**, so its angle moves with `D`: an opening cut for ±12° at `E` = 1.6 cm
stops at ±11.98° to ±12.06° over IPD 30–38 mm.

**The mirrors fix the room around the eye.** Every point of M1's lower edge subtends the
mirrors' 13.15° below the line of sight (the trapezoid fills the field cone), and the camera and
light lie in the eye's own vertical plane, where M1 sits at `a`. With the 5 mm margin and an
ASSUMED 5 mm mount, M1's lower edge sits 18.5–19.8° below the line of sight over IPD 30–38 mm.
That clears the OpenIrisDPI paper's 35° camera line by 15.2–16.5° and its 25° light line by
5.2–6.5° (panel comparison §4 and §9; S0 §7.1 row 9 puts the stereoscope's camera below M1).
These are centerlines: the light's own beam width is **not** included.

**Why a mask and not the mirrors' edges.** A mirror edge used as the stop is soft on the
screen, by `(D − c)/c` times the pupil diameter: 1.92 × for M2 and 6.5 × for M1 at `E` = 1.6 cm.
A mask at the panel has a sharp edge, and lets the mirrors keep their margin.

**Both patches go in the bottom strip**, as S3 §8 and S4 §7 place them. The center strip is
also dark to both eyes' own periscopes, and the outer strips are safe from §4.2's path once the
divider is in.

**The patches must be verified dark to each eye during bring-up**, not assumed from geometry — a
stray reflection off a mirror edge would put the flip patch back in the field, and that is a V9
item.

---

## 6. Vergence is a software constant, not a mechanical one

The periscope translates without deviating, so both eyes' axes leave parallel and normal to the
panel. A stimulus drawn at identical viewport coordinates therefore has **zero retinal
disparity and is perceived at optical infinity**, while accommodation sits at the optical path,
63.15 cm — the ordinary stereoscope conflict.

To place zero-disparity at the screen's optical distance instead, the axes must converge by
`2·atan(E/D)` = **2.9°** at `E` = 1.6 cm (2.7–3.5° over IPD 30–38 mm). Do this **in software**,
as a constant horizontal offset between the two viewports, not by angling the mirrors:

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
6. Mirrors at least the §3.1 "to cut" sizes: rectangles as tall as the trapezoid's temporal
   end, not its middle.
7. A matte-black midline divider from the ridge toward the face, stopping short of the nose,
   trimmed to the animal at fitting (§4.2).
8. A removable matte-black mask at the panel, cut for ±12° to start: an opening of 26.85 ×
   26.85 cm centered on each viewport (§5). The mirrors are cut for the full viewport, so a
   different mask changes the field without new mirrors.
9. The screen on a locked arm or stand with a stop, at `Z` = 50 cm from the eyes (§4.4).

**Verify before an animal (V9)**
1. **Measure each eye's optical path independently.** They are equal only if the mirrors are;
   S0 §5.2 already forbids deriving them from the panel distance.
2. Nonius / vernier alignment target, run at every session start, residual recorded.
3. Confirm each eye sees only its own viewport — occlude one half, check the other eye is
   unaffected — including at nasal angles past the ridge (§4.2).
4. Confirm both photodiode patches are dark to both eyes.
5. Per-half photometry (V9), which on a split panel is an interocular check, not a uniformity
   check.
6. Confirm the chosen field's corners are not vignetted from the eye position (§3.1's margin).
7. Measure `Z` at setup, and re-check it in the regular rig checks (§4.4).

---

## 8. What is still open

| # | Item | Owner |
|---|---|---|
| 1 | Measure `E` (IPD) per animal | PI — sets `a` via §4's rule |
| 2 | ~~M1 distance~~ **Answered: symmetric field, adjustable per animal.** The rule is `a = E(1 + 1/tan θ)`, corrected 2026-09-28 from `E/tan θ` (`3.27·E` on the 31.5-inch panel), which used the wrong nasal clip | — |
| 3 | Patch location — **the bottom strip**, 3.22 cm at the ±12° mask (§5) — confirm with `wl-sync` | PI + `wl-sync` |
| 4 | ~~Chair and head-post clearance~~ **Build to it and find out** (PI, 2026-08-31). If the muzzle fouls the carriage, symmetric field is unreachable and §4's table is re-derived from the achievable clearance instead of from IPD — moving the near mirrors out trades nasal field for a central strip, which is then where the photodiode patches go instead of the bottom strip. The corrected rule already puts M1, and the ridge, exactly `E` further from the face than the old one did: 8.45 cm against 6.85 cm at `E` = 1.6 cm | commissioning |
| 5 | Enclosure and baffling against ambient light | build |
| 6 | ~~The field stop~~ **Answered (PI, 2026-09-28): adjustable.** Mirrors and ridge built for the full viewport; a removable mask at the panel sets the field, starting at ±12°, which gives 3.22 cm strips top and bottom with the screen at 50 cm (§5) | — |
| 7 | ~~What blocks the path past the ridge~~ **Answered (PI, 2026-09-28): a midline divider**, trimmed to the animal at fitting (§4.2) | build |
| 8 | **The ridge's fade at the mask's nasal edge.** With the screen at 50 cm, a pupil wider than about 3 mm sees the ±12° mask's nasal edge dimmed by the ridge (§4.2). The pupil under the rig's luminance is measured at bring-up | PI + bring-up |
