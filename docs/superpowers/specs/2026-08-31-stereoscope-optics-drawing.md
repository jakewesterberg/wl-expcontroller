# Split-screen stereoscope — buildable geometry

- **Status:** proposed, for PI review and in-house build
- **Date:** 2026-08-31; **revised 2026-09-28**
- **Derives from:** S0 §5.1–§5.2 (panel and viewing distance), S3 §8 (photodiode patch placement)
- **Owner:** in-house build (PI, 2026-08-31)

> **Revised 2026-09-28.** The PI switched the display to the 26.5-inch ASUS PG27UCDM on
> 2026-09-27 (S0 §5.1), so every panel-dependent number is recomputed for its published active
> area, at the same 57 cm. The recompute also fixes four errors that the panel comparison
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
> It also records the ±10° field requirement (PI, 2026-09-27) and the stops it allows, without
> choosing one (§5), and shows that the ridge is not a stop (§4.2).

Every number below is computed from the inputs in §1 and recomputes if any of them move.
Nothing here is measured — **it is a drawing to build to and then verify against** (protocol V9).
Direct viewing is not covered: it is designed nowhere yet, and its viewing distance is open
(S0 §5.1).

---

## 1. Inputs

| Symbol | Value | Source | Confidence |
|---|---|---|---|
| Panel | ASUS ROG Swift OLED **PG27UCDM**: "26.5-inch viewable", 3840 × 2160, active area **58.997 × 33.293 cm** | ASUS [spec page](https://rog.asus.com/us/monitors/27-to-31-5-inches/rog-swift-oled-pg27ucdm/spec/) ("Display Viewing Area (HxV) : 589.97 x 332.93 mm") and [product page](https://rog.asus.com/us/monitors/27-to-31-5-inches/rog-swift-oled-pg27ucdm/) ("27-inch (26.5-inch viewable)"), both read 2026-09-28; S0 §5.1 | Published by the maker. Chosen by the PI 2026-09-27 |
| Pitch | **0.15364 mm** horizontal | derived: 589.97 mm / 3840 | ASUS lists "0.153mm". The area gives 0.15413 mm vertically (332.93 / 2160); whether the pixels are square is not published: **UNVERIFIED** |
| `D` | **57.0 cm** optical path, eye to screen | S0 §5.2 | Ruled 2026-08-31; **reaffirmed by the PI 2026-09-28 after comparing 50 cm** |
| `HW`, `HH` | 14.749 cm, 16.647 cm — half-viewport on screen | active width / 4, active height / 2 | Derived |
| `E` | half-IPD, **variable per animal** | measured per animal | **A build parameter, not a constant** |
| `θ` | the field's half-angle: at most `atan(HW/D)` = 14.51°, at least the **±10° requirement** | PI, 2026-09-27: "for the stereoscope setup +/- 10 deg is enough, most of the experiments will not be in the stereoscope" | The requirement is ruled; **the stop is not chosen** (§5) |

**Why 57 cm and not 50** (PI, 2026-09-28): ±10° is enough, so 50 cm's wider field (±16.44° ×
±18.41°) buys nothing; 57 cm is sharper (0.93 against 1.06 arcmin per pixel at the center), so
whole-pixel disparity steps are finer; and it keeps the 1 cm ≈ 1° convention for checking the
built rig (1 cm at the center subtends 1.005° at 57 cm, 1.146° at 50).

**The area, not the diagonal.** ASUS's "26.5-inch" is rounded: the published area's own diagonal
is 67.74 cm (26.67 in), and its aspect is 1.772:1 rather than 16:9. S0 §5.2's diagonal form fed
26.5 in would put each viewport edge 0.6–0.9% short, so every number here starts from the area.

**`E` varies by animal, so the rig is adjustable rather than fixed** (PI, 2026-08-31). That is
not a tolerance on a nominal — it is the design constraint that shapes the mechanics, and §4
replaces the fixed-distance table with the relationship the adjustment must hold.

---

## 2. The arrangement: a periscope per eye

Two flat first-surface mirrors per eye at 45°, translating each eye's optical axis laterally
outward onto the center of its own screen half. Plan view, not to scale, at `E` = 1.6 cm and
the full-viewport field (§5, option A):

```
                      PANEL  (59.00 cm active width, split at the midline)
    ╔═════════════════════════════╦═════════════════════════════╗
    ║      LEFT VIEWPORT          ║        RIGHT VIEWPORT       ║
    ╚═════════════════════════════╩═════════════════════════════╝
         ▲                                                   ▲
         │  axial Z − a = 36.07 cm                           │
         │                                                   │
      ┌──┴──┐                                             ┌──┴──┐
      │ M2L │◄────────────────┐               ┌──────────►│ M2R │    mirror plane,
      └─────┘   lateral       │               │           └─────┘    a = 7.78 cm from the eyes
      x=-14.75  13.15 cm      │               │           x=+14.75
                              │               │
                            ┌─┴───▼─┐   ┌───▼─┴─┐
                            │  M1L  │   │  M1R  │   roof pair, ridge on the midline,
                            └───────┘   └───────┘   a − E = 6.18 cm from the eyes
                                ▲           ▲
                                │           │        a = 7.78 cm
                             ( L eye )   ( R eye )   x = ∓1.60 cm
```

**Two reflections per eye, so parity is preserved** — no software mirror-flip, which a
single-mirror design would have required for natural images and any chiral stimulus.

**Both mirrors' centers sit in one plane**, `a` in front of the eyes: the eye's axis leaves M1
along x, at `z = a`, and must meet M2 there. The lateral run passes across the front of the
face in that plane.

---

## 3. The numbers that follow

At `E` = 1.6 cm and the full-viewport field (§5, option A). `Z` is the physical eye-to-screen
distance; `x` is measured from the midline.

| Quantity | Relation | Value |
|---|---|---|
| Lateral shift per eye (outward) | `HW − E` | **13.15 cm** |
| M1 axial distance: the mirror plane, from the eyes | `a = E(1 + D/HW)` (§4) | **7.78 cm** |
| Roof ridge, from the eyes | `a − E` | 6.18 cm |
| Optical path (eye → M1 → M2 → screen) | `a + (HW − E) + (Z − a)` | 7.78 + 13.15 + 36.07 = **57.00 cm** |
| **Physical** axial distance, eye to screen | `Z = D − (HW − E)` | **43.85 cm** |
| Mirror plane, from the screen | `Z − a` | **36.07 cm** |
| M1 centers (roof pair) | `x = ∓E` | x = ∓1.60 cm, meeting at the ridge x = 0 |
| M2 centers | `x = ∓HW` | **x = ∓14.75 cm** |
| Field per eye, temporal | `atan(HW/D)` | **±14.51°** |
| Field per eye, nasal | `atan(E/(a − E))` (§4) | **14.51°** |
| Field per eye, vertical | `atan(HH/D)`, before any stop (§5) | **±16.28°** |
| Resolution | S0 §5.2's mean, `1920 / (2 × 14.51°)` | **66.2 px/deg** (4K); 64.8 at the center and 69.1 at the viewport's side edge, from `D / (pitch · cos² e)` px per radian |
| Pixel size at the center | `pitch / D` | **0.93 arcmin** |
| FHD/480 | — | not listed for this panel (S0 §5.1) |

**The mirrors buy `HW − E` of optical path, 13.15 cm here** — not a fixed amount: a narrower
panel puts each viewport's center closer to the eye's own axis. The screen sits physically
43.85 cm from the animal while appearing at 57 cm, which is what makes a 57 cm viewing distance
fit inside a chair-sized enclosure.

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

M1 has `c = a`; M2 has `c = a + (HW − E)`. **The temporal end is the tallest:** 1.35 times the
height on the axis at ±14.51°, 1.21 at ±10°. The drawing's old relation, `√2 · c · (tan θT +
tan θN)` by `2c · tan θV`, was the linear approximation, cut to the height on the axis. It is
short in both directions and loses the temporal corners.

Sizes in mm, **length along the 45° face × height at the temporal end** (height at the nasal
end in parentheses), with the vertical field stopped equal to the horizontal. §5 gives each
option; §4.3 says why the largest IPD sizes the pair.

| Field per eye | `E` | M1, exact | M1, to cut | M2, exact | M2, to cut |
|---|---|---|---|---|---|
| A: ±14.51° | 1.6 cm | 61.1 × 54.3 (32.0) | 67 × 65 | 164.2 × 146.1 (86.1) | 175 × 157 |
| A: ±14.51° | **1.9 cm** | 72.5 × 64.5 (38.0) | **78 × 75** | 173.3 × 154.2 (90.8) | **184 × 165** |
| B: ±12° | **1.9 cm** | 68.2 × 58.5 (38.0) | **74 × 69** | 149.2 × 127.9 (83.0) | **160 × 138** |
| C: ±10° | **1.9 cm** | 65.2 × 54.3 (38.0) | **71 × 65** | 131.4 × 109.3 (76.5) | **142 × 120** |

With no vertical stop at all (±16.28°), option A's heights at `E` = 1.9 cm would be 72.8 mm
(M1) and 174.1 mm (M2), and there would be no dark strip for the photodiodes (§5).

**"To cut" is the trapezoid's bounding rectangle plus a 5 mm margin on every free edge,**
rounded up: M1 gains 5 mm of length at its temporal end only, since its nasal edge is the ridge
and cannot move, and 10 mm of height; M2 gains 10 mm in both. **The 5 mm is an allowance, not a
derivation.** A pupil of radius `r` needs `√2 · r / (1 − tan θT)` more mirror along the face at
the temporal end (1.91·r at ±14.51°), so 5 mm covers a pupil up to 5.2 mm across at the nominal
eye position — or a smaller pupil plus some eye placement error or gaze-driven pupil shift.
The macaque pupil under the rig's luminance is a bring-up measurement, **UNVERIFIED** here, and
V9 tests the margin (§7).

**A margin and a stop are different edges.** An oversized mirror cannot also be the field stop.
If a mirror's own edge is to stop the field (§5), that edge is cut to the exact trapezoid, not
to a straight line: a straight edge on a 45° mirror stops at a sloped line on the screen,
because the height it subtends scales with `1 + p`.

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

> **`a = E(1 + 1/tan θ)`**: **4.86·E** for the full viewport (θ = 14.51°), 5.70·E at ±12°,
> 6.67·E at ±10°

where θ is the field's half-angle (§5). Set `a` longer and you trade nasal field for an
unviewed center strip (§5), 4.8 cm of strip per 1 cm of extra distance near the full-viewport
position at `E` = 1.6 cm; the rig can do either, but symmetric is the default because it is the
thing least likely to surprise an analysis. If the field is stopped at the panel instead
(§5), `a` need only stay at or nearer the eyes than `E(1 + 1/tan θ)`, so that the ridge clips at
or beyond the stop.

For the full viewport:

| IPD | `E` | M1 at `a` | Ridge at `a − E` | Screen at `Z` | Lateral shift |
|---|---|---|---|---|---|
| 30 mm | 1.50 cm | 7.30 cm | 5.80 cm | 43.75 cm | 13.25 cm |
| 32 mm | 1.60 cm | 7.78 cm | 6.18 cm | 43.85 cm | 13.15 cm |
| 34 mm | 1.70 cm | 8.27 cm | 6.57 cm | 43.95 cm | 13.05 cm |
| 36 mm | 1.80 cm | 8.76 cm | 6.96 cm | 44.05 cm | 12.95 cm |
| 38 mm | 1.90 cm | 9.24 cm | 7.34 cm | 44.15 cm | 12.85 cm |

`Z` and the lateral shift depend on `E` alone, so they hold for every option; `a` and the ridge
scale with the option's coefficient (§5).

### 4.1 Three things move, and one does not

1. **M1 axial distance**, 7.30 → 9.24 cm for the full viewport. The adjustment that matters.
2. **M1 lateral position**, ±1.5 → ±1.9 cm, so each near mirror stays centered on its eye. The
   **ridge stays on the midline at x = 0** for every IPD — the two sides mirror each other
   about it — and that is what lets the roof be a fixed reference. It moves only axially, to
   `a − E`: 5.80 → 7.34 cm.
3. **M2 axial position**, which must track M1 because the two mirrors have to stay **coplanar**
   for the translation to be pure. Mechanically: **one axial carriage per eye carrying both
   mirrors**, with a small lateral slide for M1 alone.
4. **M2 lateral position does not move.** It sits at x = ∓14.75 cm — the center of its screen
   half — for every IPD, because the eye's axis after translation always lands there by
   construction. It is the fixed datum the whole build can be squared to.

### 4.2 The ridge is not a stop

**Past the clip, a ray is not blocked.** It crosses the midline between the eyes and the ridge, meets
the other eye's M1 face, and the other periscope carries it to the **other eye's viewport**. It
lands `HW − 2E + D · p` from the midline on the far half, so at the full viewport the left eye,
looking more than 14.51° nasally, sees the right viewport's outer 2E = 3.2 cm — inside the
right eye's field. At ±10° it lands from 21.6 cm out, 3.2 cm inside the right eye's ±10° field.

Something must block it. The options, not chosen here (§8):

- a septum on the midline, from the ridge back toward the face;
- the animal's own nose, if it reaches far enough forward: **UNVERIFIED**, since the muzzle
  clearance is found at build (§8 item 4).

**The clip is also soft.** A pupil of diameter `d` sees the ridge from a spread of positions, so
the nasal edge fades over `d / (a − E)` radians: 0.93° per mm of pupil at `E` = 1.6 cm and the
full viewport.

### 4.3 One mirror pair covers the range

Size for the largest IPD, and smaller animals use less of the surface: both trapezoids scale
with their distance, so with M1 registered at the ridge and M2 at x = ∓HW, the `E` = 1.5 cm
footprint lies inside the `E` = 1.9 cm one. **For the full viewport, cut M1 to 78 × 75 mm and M2
to 184 × 165 mm** (§3.1; §5 for the other options). There is no need for per-animal optics, only
per-animal positions.

### 4.4 Screen distance is measured, not adjusted

`Z` varies over just 4 mm across the whole IPD range — 0.7% of the optical path. Rather than
add a fourth adjustment for it, **fix the panel and measure each eye's path per animal**, which
V9 requires anyway. deg/pixel is then derived from the measurement instead of asserted from a
nominal.

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

**The requirement is ±10°** (PI, 2026-09-27). The panel at 57 cm gives ±14.51° × ±16.28°, so
the field can be stopped anywhere from the viewport's own edge down to ±10°. **This drawing does
not choose the stop** (§8). A smaller field frees room: the mirrors shrink and M1 moves away
from the face, and a larger part of the panel goes dark to both eyes.

S3 §8 requires both photodiode patches outside **both** viewports, or the flip patch
(alternating every refresh) becomes a flickering distractor in one eye's field. Two viewports
tile the panel exactly, so every pixel is seen by one eye unless the field is stopped. **The
stop is what makes room for the patches.**

Three options, each with the vertical stop equal to the horizontal and the ridge at the
symmetric position for its field:

| | **A: full viewport** | **B: ±12°** | **C: ±10°, the requirement** |
|---|---|---|---|
| Field per eye | ±14.51° × ±14.51° | ±12° × ±12° | ±10° × ±10° |
| `a` (IPD 30–38 mm) | 4.86·E: 7.30–9.24 cm | 5.70·E: 8.56–10.84 cm | 6.67·E: 10.01–12.68 cm |
| Ridge, from the eyes | 5.80–7.34 cm | 7.06–8.94 cm | 8.51–10.78 cm |
| M1 / M2 to cut (`E` = 1.9 cm) | 78 × 75 / 184 × 165 mm | 74 × 69 / 160 × 138 mm | 71 × 65 / 142 × 120 mm |
| **Dark strip, top and bottom**, full width | **1.90 cm** (123 px) | 4.53 cm (294 px) | 6.60 cm (428 px) |
| Dark strip, center, full height | none | 5.27 cm | 9.40 cm |
| Dark strips, outer edges | none | 2.63 cm each | 4.70 cm each |
| M1's lower edge, + 5 mm margin + 5 mm mount (ASSUMED), below the line of sight | 20.2–21.6° | 17.0–18.2° | 14.3–15.4° |
| Clearance under it: the paper's 35° camera line | 13.4–14.8° | 16.8–18.0° | 19.6–20.7° |
| Clearance under it: the paper's 25° light line | 3.4–4.8° | 6.8–8.0° | 9.6–10.7° |
| Nasal-edge fade, per mm of pupil (§4.2) | 0.78–0.99° | 0.64–0.81° | 0.53–0.67° |

Relations: strips `HH − D · tan θ`, `2(HW − D · tan θ)` and `HW − D · tan θ`; px at the
0.15413 mm vertical pitch. Every point of M1's lower edge subtends θ below the line of sight
(the trapezoid fills the field cone), and the camera and light lie in the eye's own vertical
plane, where M1 sits at `a`. The camera and light rows are the OpenIrisDPI paper's 35° camera
and 25° light (panel comparison §4 and §9; S0 §7.1 row 9 puts the stereoscope's camera below
M1), at their centerlines: the light's own beam width is **not** included. Ranges run over
IPD 30–38 mm.

**Option A's strip is 1.90 cm**, against the 2.18 cm the drawing gave on the 31.5-inch panel.
The vertical stop table for option A's horizontal field:

| Vertical stop | Strip, top and bottom | Full panel width |
|---|---|---|
| ±16.0° | 0.30 cm | 59.00 cm |
| ±15.0° | 1.37 cm | 59.00 cm |
| **±14.51°** (equal to horizontal) | **1.90 cm** | 59.00 cm |
| ±14.0° | 2.43 cm | 59.00 cm |

**Where the stop sits is part of the choice.** Two places:

- **the mirrors' own edges**, cut to the exact trapezoid (§3.1). The edge is soft on the
  screen, by `(D − c)/c` times the pupil diameter: 1.72 × for M2 at `E` = 1.6 cm in option A,
  and 6.3 × for M1;
- **a mask at the panel**, with the mirrors keeping their margin. Its edge is sharp.

**Both patches go in the bottom strip** in every option, as S3 §8 and S4 §7 place them, clear of
the soft edge. The center strip of B and C is also dark to both eyes' own periscopes, but the
outer strips are not safe from §4.2's path past the ridge until it is blocked.

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
6. Mirrors at least the §3.1 "to cut" sizes: rectangles as tall as the trapezoid's temporal
   end, not its middle.
7. Block the path past the ridge (§4.2).

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

---

## 8. What is still open

| # | Item | Owner |
|---|---|---|
| 1 | Measure `E` (IPD) per animal | PI — sets `a` via §4's rule |
| 2 | ~~M1 distance~~ **Answered: symmetric field, adjustable per animal.** The rule is `a = E(1 + 1/tan θ)`, corrected 2026-09-28 from `E/tan θ` (`3.27·E` on the 31.5-inch panel), which used the wrong nasal clip | — |
| 3 | Patch location — **the bottom strip**, whose height depends on the stop (§5) — confirm with `wl-sync` | PI + `wl-sync` |
| 4 | ~~Chair and head-post clearance~~ **Build to it and find out** (PI, 2026-08-31). If the muzzle fouls the carriage, symmetric field is unreachable and §4's table is re-derived from the achievable clearance instead of from IPD — moving the near mirrors out trades nasal field for a central strip, which is then where the photodiode patches go instead of the bottom strip. The corrected rule already puts M1, and the ridge, exactly `E` further from the face than the old one did: 7.78 cm against 6.18 cm at `E` = 1.6 cm | commissioning |
| 5 | Enclosure and baffling against ambient light | build |
| 6 | **The field stop**: how far inside the panel's ±14.51° × ±16.28° toward the ±10° requirement, and whether at the mirrors or a mask at the panel (§5) | PI |
| 7 | **What blocks the path past the ridge** (§4.2): a septum, or the nose if it reaches | PI + build |
