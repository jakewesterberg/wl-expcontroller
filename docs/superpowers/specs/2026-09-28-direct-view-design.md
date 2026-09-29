# Direct view: the animal looks at the screen, with the stereoscope out

- **Status:** design approved by the PI 2026-09-28, spec for his review
- **Date:** 2026-09-28
- **Derives from:** S0 §5 (display), the stereoscope optics drawing, S3 §8 (photodiode patches),
  S4 §2 and §7, S5 (calibration), `docs/research/2026-09-27-panel-27-vs-32.md` §2–§4
- **Builds after:** P4d-2b slice b2a merges (both touch session start), and after branch
  `stereo-geometry-27` (the stereoscope redrawn for the 26.5-inch panel at a 50 cm screen)

Until now every document routed every task through the split-screen stereoscope (panel
comparison §2). Most experiments will not use it (PI, 2026-09-27: "most of the experiments
will not be in the stereoscope"), and **the first animal task runs in direct view** (PI,
2026-09-28). This spec is the missing half.

---

## 1. Decisions (PI, 2026-09-28, asked in plain terms)

1. **One physical screen distance for both setups, and the screen never moves.** "I want the
   screen to be the same physical distance from the animal in stereoscope and the direct
   viewing. The stereoscope is a device that is removable and everything else is fixed."
2. **That distance is `Z` = 50 cm**, eye to screen. He was shown three options: 44 cm, which
   keeps the stereoscope's optical path at 57 cm; 50 cm; and 57 cm.
3. **The screen is fixed in place**, on a locked arm or stand with a stop. It is measured once at
   setup and re-checked in the regular rig checks.
4. **The operator picks the setup at session start.** Nothing detects the stereoscope
   physically; a switch on its mount was offered and declined.
5. **The design below was approved as five parts** (setup and geometry, the light sensor, the
   eye camera, calibration and checks, order of work) before this spec was written.

Earlier the same day the PI had also decided the following. This spec uses them as given:
- the stereoscope's field is set by a removable mask at the panel, starting at ±12°;
- a midline divider blocks the path past the mirror ridge;
- beyond the tracker's P4 reach, eye tracking falls back to pupil plus corneal reflection
  (PI, 2026-09-27).

---

## 2. Geometry, per setup

**The two setups share one screen at one place.** Both use the ASUS PG27UCDM's published
active area, 589.97 × 332.93 mm (ASUS spec page, read 2026-09-28, S0 §5.1). Each setup
differs only in the path from the eye to that screen.

| | Direct view | Stereoscope |
|---|---|---|
| Distance used for degrees | `Z` = 50 cm | the optical path `D = Z + HW − E`: 63.15 cm at `E` = 1.6 cm; 62.85–63.25 cm over IPD 30–38 mm |
| What each eye sees | the whole panel, the same image to both eyes | its own half, through the mirrors |
| Field a stimulus may use | ±30.5° × ±18.4°, **minus the light sensors' housings** (§4) | **the mask**, ±12° to start. That is inside the half-panel's ±13.15° × ±14.77°, which sets the upper limit |
| Pixels per degree, center | 56.8 | 71.7 |

`HW` is a quarter of the panel's width and `E` is the animal's half-IPD. The stereoscope column
is the optics drawing's, reworked for `Z` = 50 cm; if the drawing and this table ever
disagree, the drawing wins.

**In code:** `geometry.py` models each setup as a field the checks can ask
`can_show(x, y)`:
- **Direct view:** the full panel at `Z`, with exclusion rectangles.
- **Stereoscope:** `D` for the subject's `E`, clipped to the mask.

The rig's settings hold everything the geometry needs:
- `Z`;
- the mask's half-angle;
- the sensor housings' rectangles (§4).

A subject's `E` comes from its record. **From a per-animal settings file** (PI, 2026-09-29), named at session start with `--subject-settings` as the bounded config is with `--bounds`, and refused for another animal; `Rig.half_ipd_range_cm` refuses an `E` the stereoscope is not built for. **A field that is not the rig's is never used to pass a
task.** The tests' fixtures stand for this rig, and say so.

**Degrees are the API**, as S4 already has it. The display module will map degrees to pixels
per setup:
- direct view uses one full-panel viewport at `Z`;
- the stereoscope uses two per-eye viewports at `D`.

That module does not exist yet (S4). This spec fixes the mapping it must implement, and the
field the checks use is the same one it will draw into.

---

## 3. Which setup a session runs in

**The operator chooses at session start, and there is no default.** `wlx run` takes a required
`--view direct|stereoscope`. The page gets the same choice when sessions start from it (P4d-2b
slice b3). `--rig` names the rig's settings, and a task that does not pass the load-time checks in the chosen setup is refused before the session opens (plan `2026-09-29-direct-view-part2.md`, decision 7). The choice is:
- written into the session snapshot and the session record;
- published in telemetry, and shown by `wlx console` and the page for the whole session (a
  telemetry schema bump, taken after b2a's schema 8).

**A task says which setup it is written for:** `Trial.view`, one of `"direct"`,
`"stereoscope"` or `"either"`, default `"either"`.
- **The default is safe because the field check runs against the chosen setup.** A task that
  runs in the stereoscope without saying so is checked against the ±12° mask, and a target
  beyond it is refused.
- **A monocular task in the stereoscope** is the zero-disparity case (S4 §2), so `"either"` is
  honest for it.
- **Disparity requires the stereoscope.** A task whose stimuli carry disparity, or that shows
  a random-dot stereogram, is a load-time finding unless it declares `"stereoscope"`. Two
  side-by-side images on an unmirrored screen are not a stimulus.
- **A mismatch refuses to start**, naming both sides: a `"stereoscope"` task in direct view,
  or a `"direct"` task in the stereoscope.

**The residual risk is the operator's pick**, since nothing senses the device (§1 item 4).
What limits it:
- no default;
- the setup is on screen all session;
- the refusal above;
- the geometry check on every task.

A wrong pick for an `"either"` task still runs, with degrees computed on the wrong distance.
That is the cost the PI accepted when he declined the switch.

---

## 4. The screen-timing light sensors

S3 §8 fixes the two patches in copper: `A_PD1`, the task patch, and `A_PD2`, the flip patch,
which alternates every refresh.

**They sit at one place on the screen, in both setups: a bottom corner.** Because the screen is
fixed, the sensors are mounted once and never moved.
- **In the stereoscope**, that corner is inside the masked bottom strip. The strip is 3.22 cm
  tall at the ±12° mask (optics drawing, reworked), so no eye sees it through the mirrors.
- **In direct view**, each sensor's own opaque housing covers its patch. The animal sees a
  small dark shape at the panel's far lower corner, around (±30°, −18°), well outside the ±15°
  where stimuli go, and never the flicker.

**The housings are rectangles in the rig's settings**, in cm on the panel, each with a margin
recorded beside it. They are measured at build from the real sensors. Whether both sensors fit
side by side at one corner, or take one corner each, is a build finding. **Direct view's field
excludes them**, so check 8 refuses a stimulus that could overlap a housing, exactly as it
refuses one off the panel.

**At bring-up, the flicker is checked invisible from the animal's position, in both setups**
(§7). It is not assumed from geometry.

---

## 5. The eye camera and its light

**One position, serving both setups**: directly below the screen, in the eye's own vertical
plane, at the OpenIrisDPI paper's layout of camera at 35° and light at 25°. The paper's rule is
that the illuminator sits about 10° shallower than the camera, to center P4 (Ressmeyer et al.
2026, §3.1; panel comparison §4.1).

At `Z` = 50 cm on the 27-inch (panel comparison §4.2, even border split ASSUMED):
- the housing's bottom edge is 20.3° below the line of sight;
- the lowest camera that still centers P4 is 32.3°, so the paper's 35° has about 2.7° to spare;
- the light at 25° is 4.7° below the housing edge, or 2.7° past the report's 2° margin.

With all of the housing border at the bottom, which is the bound, these tighten by about 2°
(panel comparison §4.2). The real clearance is a bring-up check (§7).

**The stereoscope, when inserted, must leave both lines clear**: a window or cutout in its
underside along the 35° and 25° lines. The mirrors themselves clear them (the drawing's
clearance rows); the enclosure and the divider are what could block them. This is a build
requirement on the stereoscope device.

Beyond P4's reach, which is about 10° in the paper's macaques (panel comparison §6), tracking
falls back to pupil plus corneal reflection (PI, 2026-09-27; S5).

---

## 6. Calibration, per setup

S5's constellation is placed as a fraction (`calibration.REACH`) of the per-eye field. In
direct view, 75% of the field would put targets at ±22.9° horizontally: beyond the stimuli,
and far beyond P4. So **the constellation is placed per setup, over a calibration region**:
- **Direct view:** ±15° × ±15°. That is the PI's stimulus range ("out to about 15°",
  2026-09-27), inside the ±18.4° vertical field.
- **Stereoscope:** the mask's ±12°.

`tools/calibration_design.py`, which chose `REACH = 0.75` on 2026-09-05 for the 31.5-inch
stereoscope, is re-run for each setup's region. Each result is committed as a new dated record
under `docs/measurements/`, and each setup gets its own reach. The 2026-09-05 record stays as
written.

The stereo-geometry branch's rerun found a closer call on the new panel, where 85% won under
two of four optics assumptions. The per-setup records settle it.

---

## 7. Verification additions

**V9, direct view:**
1. Measure `Z` at setup. Re-check it in the regular rig checks against the stop.
2. Confirm from the animal's eye position that neither patch is visible: the housings cover
   the flicker.
3. Confirm the camera and light see the eye past the screen housing's bottom edge, with the
   paper's 35°/25° layout, and past the muzzle, the juice spout and the chair front.
4. Insert the stereoscope, and confirm that both lines are still clear and that the patches
   are dark to both eyes through the mask.

**V1** (display timing) already runs in every mode the rig uses (S0 §5.3); nothing about it
changes in direct view. Luminance uniformity and ABL are the panel acceptance test (S0 §5.4
criteria 2-3), folded into V9 above -- in direct view they are characterised across the whole
panel, as a within-image nonlinearity rather than interocular coupling (corrected 2026-09-28:
this section originally attributed them to V1).

---

## 8. What changes, and in what order

**Code, after b2a merges and after `stereo-geometry-27`:**
- `geometry.py`: the two setups' fields, the mask, and the housing exclusions.
- `task.py`: `Trial.view`.
- `check.py`:
  - check 8 against the session's field;
  - the disparity-requires-stereoscope finding.
- **The load-time checks get the geometry they have never had:** they used to call `check()`
  without one, so check 8 never ran outside the tests. Now `wlx run --rig --view` passes the
  chosen setup's geometry to `taskd`'s load-time check, and `wlx check --rig` builds the
  geometry of every setup the task allows.
- `wlx check --view` checks against one setup. Without `--view`, it checks against every setup
  the task allows.
- `wlx run --view`, the session snapshot and record, and a telemetry field shown by
  `wlx console` and the page.
- `calibration.constellation` over a per-setup region, and the two new calibration records.
- **The reference tasks declare `view="direct"`**, and `fixation_detection` and
  `adaptive_detection` go back to ±16° (checked against direct view), undoing the interim
  narrowing.

**Docs, in the same change:**
- S0 §5 (a direct-view section; `Z`, the fixed screen);
- S3 §8 and S4 §7 (the sensors in both setups);
- S4 §2 (the viewport mapping per setup);
- S5 (the constellation per setup);
- `docs/design/architecture.md` ("Stereo, as viewports", which today routes every task through
  the stereoscope);
- the controller architecture's D6;
- M0-REVIEW row 9;
- V9 in `docs/validation.md`.

**Not in this spec:**
- the stereoscope device's mechanical design, beyond §5's window;
- a stereoscope-presence switch (declined);
- touch (controller architecture §8.4);
- the page's session-start picker (b3).

---

## 9. Open, and whose

| # | Item | Owner |
|---|---|---|
| 1 | The sensor housings' size, and whether both fit at one corner | build |
| 2 | `Z` against the real chair and head-post (S0 open item 6), now one distance for both setups | commissioning |
| 3 | The camera and light clearance under the real housing edge, muzzle and spout (§5) | bring-up |
| 4 | P4's real reach, and the animals' pupils under the rig's background luminance (panel comparison §11) | bring-up (P10) |
