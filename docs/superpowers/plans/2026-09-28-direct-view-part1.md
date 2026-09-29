# Direct View, Part 1 — Each Setup's Field, `Trial.view`, and Calibration per Setup: Implementation Plan

> **Naming note (2026-09-29):** this document predates the rename and keeps the names it was
> written with. The repository `wl-expcontroller` is `wl-xcon` since 2026-09-28, and the Python
> package `wl_expcontroller` is `wl_xcon` since 2026-09-29 (XC-053), so a path such as
> `wl_expcontroller/taskd.py` is now `wl_xcon/taskd.py`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Execution: subagent-driven.** That method is already chosen for this project, as it was for b1 and b2a: a fresh implementer per task and a fresh reviewer before the next one starts.
>
> **Part 1 of the direct-view spec: the half that does not touch session start.** It builds each setup's field in `geometry.py` and the rig's settings that field is built from, `Trial.view` and the checks that hold a task to its setup, and the calibration constellation per setup with its two new records. **Out of scope, and direct view part 2, after P4d-2b slice b2a merges** (both change session start): `wlx run --view`; passing the session's geometry into `taskd`'s and `wlx check`'s load-time checks; the session snapshot and record; the telemetry field. **So part 1 adds checks that only the tests exercise until part 2 wires them in**: check 8 against a setup's field, and the `wrong-setup` refusal, both of which need a geometry that `taskd` and `wlx check` do not pass yet. Every place that waits says so in a comment naming *direct view part 2*, so `grep -rn "direct view part 2"` finds the gap. The `needs-stereoscope` and `unknown-view` findings need no geometry, and are live at every load from Task 4 on.
>
> **Checked not to overlap b2a** (`p4d2b-b2a-controls`, being executed now), against its plan and its branch on 2026-09-28. No step here touches `link`, `taskd`, `serve`, `web`, `cli`, `record`, `run`, `health` or `tasks/allocation.py`. It touches none of the test files b2a changes (`test_link`, `test_taskd`, `test_run`, `test_cli`, `test_health`, `test_web`, `test_serve`, `test_measure_mark_check`, `_frames`, `_zmq_release`), and not `tests/conftest.py`, `tools/mutation_gate.py` or `pyproject.toml`. In `docs/design/architecture.md` the one block replaced is the "Stereo, as viewports" section. It sits six lines below b2a's nearest anchor, the "**Control/telemetry**" bullet, and shares no line with any of b2a's five anchors. In `docs/validation.md` the V9 items are added inside V9, as their own lines, and b2a appends V12 at the file's end. `docs/pitfalls.md`, S9a, `docs/CHECKPOINT.md` and `docs/next-session.md` are untouched; the controller writes the checkpoint.
>
> **Every task's code was built and run before this plan was written.** The scratch copy was a `git archive` of this branch's tip, `dec6f85`, with the `wl-preproc` checkout (`7a060e0`) linked inside it. Each task was built there in order, its tests red first and then green, with the whole suite after each. The code in every step is that code. Each "replace" block's old text is unique in its file at the moment the step is applied, in the order given, and is whole lines, except two one-line blocks inside a table row: `docs/M0-REVIEW.md`'s row 9 (Task 2) and the controller architecture's D6 (Task 4), where only that text is replaced. An "Append to" block goes at the end of the file as it stands.
>
> **Then the whole plan was re-applied, as written**, to a fresh `git archive` of `dec6f85`, by the scratch tool `apply_plan.py`, with every RED run where the plan puts it: **1134 passed** at `dec6f85`; then 1144, 1148, 1152, 1160, 1174 and **1182 passed** after Tasks 1–6, each the count stated. Every RED showed the failure stated for it, run as written. The scratch tools `stepper.py` and `redcheck.py` ran every `Run:` line and every commit block in a git copy, and rebuilt each task's RED state on its own. Task 5's regeneration check printed `direct regenerates`, `stereoscope regenerates` and `2026-09-05 regenerates`. The suite was then green three times in a row, **1182 passed** each time, and Task 7's sweeps, run on that fully applied tree, printed the lines quoted there: 39 functions, every one `caught … N failed`, no survivor, no timeout and no error.

**Goal:** The rig answers, for either setup, whether a stimulus can be shown — direct view's whole panel less the light sensors' housings, or the stereoscope's viewport stopped by its mask — from settings in one file; a task says which setup it is written for, and is refused in the other; and the calibration constellation is placed over each setup's own region, at the reach that setup's record chose.

**Architecture:** `geometry.Geometry` gains a setup (`view`), the stereoscope's mask (`mask_deg`) and direct view's light-sensor housings (`housings`), and `Geometry.direct` joins `Geometry.stereoscope`. Direct view refuses to exist without the housings, which are not measured yet. `geometry.Rig` holds the rig's settings, and `tasks/rig.py` writes them down. `Trial.view` defaults to `"either"`; `check()` gains three findings, and check 8 names the field it used. `calibration.region` and a per-setup `calibration.REACH` place the constellation; `tools/calibration_design.py --setup` reruns the 2026-09-05 method for each region, and each result is a new dated record.

**Tech Stack:** Python 3.11–3.13; dataclasses; numpy (the design tool, as before); pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-28-direct-view-design.md`, approved by the PI on 2026-09-28, is the binding authority. §2, §4, §6 and §7, §3's `Trial.view` and its findings, and §8's part-1 half bind this plan. §3's session-start half and §8's `wlx run --view`, snapshot, record and telemetry bullets are part 2. Read the spec first; this plan argues from it.

## Plan decisions

The spec left these to the plan, or to whoever built it. Each is taken here, with its reason; the code is in the task named.

1. **The rig's settings: a new, smallest mechanism, because none existed** (Task 2). The code has no rig configuration. S0 §5.3's "Mode is a rig configuration" is prose about the 4K and FHD modes, and nothing reads it. The nearest thing, `tasks/reference_bounds.py`, is the subject's bounded config, which is welfare-critical and per subject. So: a frozen `geometry.Rig` (panel active area, `Z`, the mask's half-angle, the housings), with `direct()` and `stereoscope(half_ipd_cm)`, and one settings file, `tasks/rig.py`, defining `RIG`. It is Python for the reason the tasks and `reference_bounds.py` are (ADR-0006), and part 2 can load it by path, as `wlx run --bounds` loads a bounded config.

2. **The housings are unmeasured, so direct view refuses to exist without them, and the tests supply stand-ins** (Tasks 1 and 2). `Geometry.__post_init__` raises `ValueError` for `view="direct"` with no housings, naming spec §9 item 1. `tasks/rig.py` has `housings=()` under a `NOT YET MEASURED` comment, and `test_the_rigs_housings_are_unmeasured_so_direct_view_refuses_on_its_settings` pins that, so writing the measurement in fails a test that is then replaced by one pinning the real rectangles. Every test fixture that needs direct view builds it with two **stand-in** housings, one per bottom corner, 4 × 3 cm with a 0.5 cm margin, labelled a stand-in where it is defined. **The cost:** until the housings are measured at build, nothing runs in direct view on this rig's settings, not even its calibration block, and part 2's `wlx run --view direct` will refuse with the spec §9 sentence. A dev-machine demo in direct view needs a settings file with stand-ins, and part 2 decides how that file is labelled (`tasks/reference_bounds.py`'s guards are the precedent). The design tool cannot build the direct-view field either; it scores a disc that lies inside the field whole (decision 10). **The alternative, rejected:** a conservative PROVISIONAL placeholder. No size can be known to be conservative before the sensors exist, because whether both fit at one corner is itself a build finding (spec §9 item 1), and a placeholder is a number the next reader believes.

3. **`Geometry` grows; nothing replaces it** (Task 1). It gains three fields with defaults: `view="stereoscope"`, `mask_deg=None` and `housings=()`. So every existing `Geometry(...)` and `Geometry.stereoscope(...)` call means what it meant: the design tool's 31.5-inch geometry, and the optics drawing's viewport that `tests/test_geometry.py` pins. `half_width_cm` is W/2 in direct view and W/4 through the stereoscope. The mask narrows `half_field_h_deg` and `half_field_v_deg` (the smaller of viewport and mask) and never `pixels_per_degree`, which stays S0 §5.2's mean across the viewport, because the mask covers pixels and does not rescale them. An unknown `view` is refused.

4. **A housing is a rectangle in cm from the active area's bottom-left corner, as the animal faces the screen** (Task 1). That is what a person measures at build with a rule against the panel. `can_show` maps a position to the panel by `D · tan` per axis, the mapping its rectangular field already implied, and refuses a point under a housing or its margin. Check 8 stays a point test, as it always was at the panel's edge, so the margin recorded beside each rectangle (spec §4) is where a stimulus's extent is allowed for.

5. **The mask is a half-angle**, as the spec's §2 says the rig's settings hold it. The optics drawing cuts it as a 26.85 cm opening at `E` = 1.6 cm, and a fixed opening subtends 11.98° at IPD 30 mm and 12.06° at 38 mm. The half-angle model therefore differs from the physical cut by at most 0.02°, on the narrow-IPD side. That is stated here and not modelled.

6. **Three findings, appended last in `check()`** (Task 4). `needs-stereoscope` is a property of the task, so it runs with or without a geometry, and is therefore live at every load in `taskd` and `wlx check` from Task 4 on. `wrong-setup` runs only against a geometry, and names both sides. `unknown-view` is refused outright, as `unknown-eye` is. **One case added to the spec's list:** a stimulus shown to one eye (`Stimulus.eye` or an `Update`'s `eye` other than `"both"`) needs the stereoscope too, for the spec's own reason: an unmirrored screen shows both eyes one image. Also covered: disparity set by an `Update`; a disparity parameter whose declared range can leave zero; and a random-dot stereogram reachable only through a parameter's choices.

7. **Check 8's finding names the field it used** (Task 3): `±12.0° × ±12.0° stereoscope field`, or `±30.5° × ±18.4° direct field, less the light sensors' housings`. The refusals themselves already follow from Task 1's `can_show`; Task 3 pins them through `check()`, and its RED is the message.

8. **Test fixtures that pass a task stand for the rig, and say so** (spec §2; Tasks 3, 4 and 6). `test_task_checks.py` and `test_disparity.py` check against `RIG.stereoscope(half_ipd_cm=1.6)`, masked, with their boundary positions moved 0.5° inside the mask (12.65 → 11.5, ±12.5 → ±11.5, 12.5 → 11.5), as the interim kept them 0.5° inside the viewport. `test_reference_tasks.py` checks against direct view with the stand-in housings. Fixtures that test the optics (`test_geometry.py`'s `STEREOSCOPE`), constellation arithmetic (`test_calibration.py`, `test_gaze.py`) or an array 40° out (`test_array.py`) keep the bare viewport, which is what they describe.

9. **The calibration region per setup** (Task 5). `calibration.region(geometry)` gives ±15° × ±15° in direct view (`DIRECT_REGION_DEG`) and the geometry's own half-fields through the stereoscope, which with the rig's mask are ±12° × ±12°. `REACH` becomes a dict keyed by setup, and `constellation(geometry)` uses the setup's value unless a `reach` is given. `MARGIN` still applies, now to the region, so reach is a fraction of margin × region, as on 2026-09-05. The spec's "75% of the field would put targets at ±22.9°" leaves the margin out; with it, 19.5°.

10. **The reruns follow the 2026-09-05 method, changing three inputs** (Task 5). `tools/calibration_design.py --setup {2026-09-05,direct,stereoscope}`. The default still regenerates the 2026-09-05 record byte for byte, which is checked. All three use the same seed, forward model, optics sweep, margin and sections. The three inputs that change:
    - the extent the constellation is scaled to: the region;
    - the tested disc. In direct view it runs to 16°, the detection tasks' restored range, unclipped, because it lies inside direct view's ±30.5° × ±18.4° and clear of the housings. Through the stereoscope it runs to 12°, the mask;
    - the reach sections 1, 2 and 4–7 lay out: the one section 3 chose, which on 2026-09-05 was 75%, so that record's output is unchanged.

    **Results: 85% in direct view, 100% in the stereoscope. Both are close calls, said plainly in the records, in `calibration.py` and in S5.** Each won under three of the four optics assumptions and lost the fourth by 0.001°. In direct view, near-axial, 100% scores 0.217° against 85%'s 0.218°. In the stereoscope, strong obliquity, 85% scores 0.174° against 100%'s 0.175°. The rule is 2026-09-05's, the reach that wins under the most assumptions, and the mean over the four agrees (direct view: 0.213° against 0.221°; stereoscope: 0.169° against 0.179°). 100% is the top of the sweep, where the margin stops. One more reading, not committed: a scratch run of section 3's sweep with the random stream started elsewhere split direct view two and two and gave the stereoscope 100% under all four assumptions. So the ranking between 85% and 100% is within this simulation's own variation, and both are close calls in the plain sense.

11. **The design tool gets tests, because it changed and no gate mode reaches `tools/`** (Task 5). `tests/test_calibration_design.py` pins each setup's inputs, the disc a run scores, section 7 against each committed record digit for digit (it is arithmetic, not simulation), and that a run prints every section at its setup's reach. **The Monte-Carlo tables are not compared in the suite**: that would hold CI's three Pythons to this machine's floating point. Task 5 instead regenerates each record and diffs it, and Task 7 sweeps the tool by hand.

12. **The reference tasks are written for direct view** (Task 6). `fixation_detection` and `adaptive_detection` return to ±16° (spec §8), and `adaptive_detection`'s eccentricity to 2–16°. `visual_search`'s eccentricity returns to 14°, its value before the interim (`git log -p`: `855ff92`..`142989c`). **The calibration task's range becomes ±15° × ±15°, direct view's calibration region, and not the pre-interim ±14.5° × ±16.1°**, which was 0.85 of the 31.5-inch panel's field and bounds nothing on this rig. It holds direct view's constellation, whose outer targets are at ±10.84°. **No stereoscope calibration task exists yet.** The constellation over the mask is `calibration.constellation`'s, and the task that presents it waits for the first stereoscope session, which part 2 makes possible. `tasks/calibration.py` says so.

13. **Docs travel with their code**: S0 §5.5 and S4 §2 in Task 1; S3 §8, S4 §7, M0-REVIEW row 9 and V9's direct-view items in Task 2; `architecture.md`'s display section and D6 in Task 4; S5 in Task 5. The roadmap and `pitfalls.md` say nothing this plan makes false.

14. **The mutation gate needs no edit**: no module is added to `wl_expcontroller/`. A push runs `--changed-only`, which selects `geometry`, `check`, `calibration` and `task` by module and their own test files; the `tasks/` paths this branch changes would escalate a full sweep, and `--changed-only` never escalates, so the nightly covers them. Task 7 sweeps every function this plan adds or changes, and the tool by hand.

## Global Constraints

- **Branch `direct-view-part1`, in its worktree; not `main`.** Do not fast-forward `main`.
- **Not welfare-critical**: nothing here touches reward delivery, session duration, fluid or stimulation. Nothing is added to `architecture.md`'s welfare-critical list.
- **Never edit b2a's files**: `wl_expcontroller/{link,taskd,serve,web,cli,record,run,health}.py`, `tasks/allocation.py`, their test files, `tests/_frames.py`, `tests/_zmq_release.py`, `docs/pitfalls.md`, S9a, V12, and the five `architecture.md` lines b2a anchors on (starting "binds a ZMQ PUB socket for `Telemetry`", "Reads are open to the LAN; writes from the box", "**In code, that is `wl_expcontroller/bounds.py`", "prompt goes. A change to either module" and "- **Control/telemetry** (console <-> taskd)").
- **Never edit `docs/CHECKPOINT.md` or `docs/next-session.md`.** The controller writes them.
- **Do not edit `tests/conftest.py`, `tools/mutation_gate.py` or `pyproject.toml`.**
- **The code on disk wins over this plan's quotations.** Every "replace" block was applied to `dec6f85` in order and matched. If one does not match on disk, anchor on the named function and keep its meaning; never restore the quoted text.
- **The 2026-09-05 record stays as written**, and `python3 tools/calibration_design.py` with no `--setup` still regenerates it byte for byte.
- **A field that is not the rig's is never used to pass a task** (spec §2). Test fixtures that pass tasks stand for the rig (`tasks/rig.py`), and the stand-in housings say they are stand-ins.
- **Degrees are the API.** No task names a pixel; `geometry.py` fixes the mapping S4's display module will implement.
- **US English** in code, comments and docs.
- **No timing claim without a measurement.** None is made. The design tool's numbers are a simulation, and the records say so in their first lines.
- **Hot path**: nothing inside a frame changes. `can_show` and the findings run at load.
- **No new dependency.**
- **Prove each new test can fail** (CLAUDE.md): Task 7 reads the harness line by line. `N failed` is a test noticing; `N errors in 0.8s` is not.
- **Never run the suite, edit a test, or `git add` while a mutation sweep is in flight.**
- Run tests with `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider` from the worktree root, with the `wl-preproc` checkout beside the repo or inside it.
- Commit messages: imperative subject; body says why when it is not obvious; end with the two attribution lines the session supplies.

## Review Focus

The five conditions the spec implies that a lab member will meet, and that no task's main tests would otherwise pin. Each has its test in the owning task:

1. **A stimulus just outside a housing's rectangle but inside its margin** → refused, and one just outside the margin shown. *Task 1 (`test_a_housings_margin_is_part_of_it`).*
2. **Stereo content that is not a literal in a `Show`**: disparity set by an `Update`, a disparity parameter whose range can leave zero, a random-dot stereogram only a parameter's choices reach → each is `needs-stereoscope`, and a parameter pinned at zero is not. *Task 4 (`test_disparity_needs_a_task_that_declares_the_stereoscope`, `test_a_disparity_parameter_counts_when_its_range_can_leave_zero`, `test_a_shown_stereogram_or_one_a_parameter_can_choose_needs_the_stereoscope`).*
3. **A typed-wrong setup, `"stereo"`, in a task or a geometry** → refused by name, never read as one setup or the other. *Task 4 (`test_a_view_that_is_no_setup_is_refused`), Task 1 (`test_a_setup_that_is_neither_is_refused`).*
4. **The rig's settings file as committed, asked for direct view** → refuses, naming spec §9 item 1, and the test pinning that fails the day the housings are written in. *Task 2 (`test_the_rigs_housings_are_unmeasured_so_direct_view_refuses_on_its_settings`).*
5. **An animal at either end of the IPD range, or a mask set wider than the viewport** → the ±12° mask is the field at IPD 30, 32 and 38 mm, and a wider mask leaves the viewport's own edge. *Task 2 (`test_the_rig_gives_the_stereoscope_its_mask_and_the_subjects_path`), Task 1 (`test_a_mask_wider_than_the_viewport_stops_nothing`).*

Also pinned, the sixth candidate: **a region, reach or mask changed without rerunning the design tool** → the committed record's section 7 no longer matches what the code presents, and a test says so. *Task 5 (`test_each_records_constellation_is_what_the_tool_lays_out_now`).*

## File Structure

| File | Responsibility |
|---|---|
| `wl_expcontroller/geometry.py` (modify) | `VIEWS`; `Housing`; `Geometry`'s `view`, `mask_deg`, `housings`, `__post_init__`, `direct`, `stereoscope(mask_deg=)`, `_viewport_deg`, `_stopped`, and `can_show` with the housings (Task 1); `Rig` (Task 2) |
| `tasks/rig.py` (create) | This rig's settings: the PG27UCDM's active area, `Z` = 50 cm, the ±12° mask, the housings (not yet measured) |
| `wl_expcontroller/check.py` (modify) | Check 8's finding names the field (Task 3); `TRIAL_VIEWS`, `_view_faults`, `_stereo_content`, called last from `check()` (Task 4) |
| `wl_expcontroller/task.py` (modify) | `Trial.view` |
| `wl_expcontroller/calibration.py` (modify) | `DIRECT_REGION_DEG`, per-setup `REACH`, `region`, and `constellation` over it |
| `tools/calibration_design.py` (modify) | `Setup`, `SETUPS`, `use`, `--setup`; the clip to a setup's field; the chosen reach laid out in sections 1, 2 and 4–7 |
| `docs/measurements/dev-machine/2026-09-28-calibration-constellation-{direct,stereoscope}.md` (create) | The two reruns |
| `tasks/{fixation_detection,adaptive_detection,visual_search,calibration}.py` (modify) | `view="direct"`, and the ranges restored |
| `tests/test_geometry.py`, `test_task_checks.py`, `test_disparity.py`, `test_calibration.py`, `test_reference_tasks.py` (modify); `tests/test_calibration_design.py` (create) | Each change's own tests |
| S0, S3, S4, S5, the controller architecture, `docs/design/architecture.md`, `docs/M0-REVIEW.md`, `docs/validation.md` (modify) | The spec's §8 docs, part 1's half, each with its code |

---

### Task 1: Direct view's field, and the stereoscope's mask

**Why:** spec §2 and §4. Each setup is a field the checks can ask `can_show(x, y)`, its half-fields and its pixels per degree. **Direct view** is the whole panel at `Z`, less the light sensors' housings, and it refuses to exist without them, because they are unmeasured (Plan decision 2). **The stereoscope** is `D = Z + HW − E`, as `main` already has it, now clipped to the mask. `Geometry` keeps its fields and its `stereoscope` constructor and grows three more (Plan decision 3). Docs: S0 gains a short direct-view section, and S4 §2 the viewport mapping per setup.

**Files:**
- Modify: `wl_expcontroller/geometry.py` (module docstring; `VIEWS`, `Housing` before `Geometry`; `Geometry`'s fields, `__post_init__`, `stereoscope`, `direct`, `half_width_cm`, `half_field_h_deg`, `half_field_v_deg`, `_viewport_deg`, `_stopped`, `pixels_per_degree`, `can_show`)
- Modify: `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md` (§5.5, new), `docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md` (§2)
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `Geometry(panel_width_cm, panel_height_cm, viewing_distance_cm)` and `Geometry.stereoscope(panel_width_cm, panel_height_cm, *, screen_distance_cm, half_ipd_cm)` as on `main` at `dec6f85`.
- Produces:
  - `geometry.VIEWS = ("direct", "stereoscope")`.
  - `geometry.Housing(left_cm, right_cm, bottom_cm, top_cm, margin_cm)`, frozen, in cm from the active area's bottom-left corner as the animal faces it; `Housing.covers(x_cm, y_cm) -> bool`, margin included.
  - `Geometry.view: str = "stereoscope"`, `Geometry.mask_deg: float | None = None`, `Geometry.housings: tuple[Housing, ...] = ()`. `__post_init__` raises `ValueError` for a `view` not in `VIEWS` (`"'stereo' is not a setup"`) and for `view="direct"` with no housings (the message names "§9 item 1").
  - `Geometry.stereoscope(..., mask_deg: float | None = None)`; `Geometry.direct(panel_width_cm, panel_height_cm, *, screen_distance_cm, housings) -> Geometry`.
  - `half_field_h_deg` and `half_field_v_deg` are the smaller of viewport and mask; `pixels_per_degree(horizontal_pixels)` is the viewport's; `can_show` also refuses a position under a housing.

- [ ] **Step 1: Write the failing tests**

In `tests/test_geometry.py`, replace:

```python
from wl_expcontroller.geometry import Geometry
```

with:

```python
from wl_expcontroller.geometry import Geometry, Housing
```

Append to `tests/test_geometry.py`:

```python


# ---------------------------------------------------------------------------
# Direct view, and the stereoscope's mask (direct-view spec §2, §4)
# ---------------------------------------------------------------------------

#: **Stand-ins for the light sensors' housings, not a measurement**: the real ones are
#: measured at build (direct-view spec §9 item 1). One per bottom corner, 4 × 3 cm with
#: a 0.5 cm margin, in cm from the active area's bottom-left corner.
HOUSINGS = (
    Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
)

#: The PG27UCDM seen directly with the screen at 50 cm (direct-view spec §2), with the
#: stand-in housings.
DIRECT = Geometry.direct(58.997, 33.293, screen_distance_cm=50.0, housings=HOUSINGS)

#: The same screen through the stereoscope at `E` = 1.6 cm, stopped by the PI's ±12° mask.
MASKED = Geometry.stereoscope(
    58.997, 33.293, screen_distance_cm=50.0, half_ipd_cm=1.6, mask_deg=12.0
)


def test_direct_view_is_the_whole_panel_at_the_screens_own_distance():
    """No periscope, so no lateral run: the path is `Z`, and the viewport is the whole
    panel, seen by both eyes."""
    assert DIRECT.view == "direct"
    assert DIRECT.viewing_distance_cm == 50.0
    assert DIRECT.half_width_cm == pytest.approx(29.4985)
    assert DIRECT.half_height_cm == pytest.approx(16.6465)


def test_direct_views_field_is_the_spec_tables():
    """The direct-view spec §2's table: ±30.5° × ±18.4° at `Z` = 50 cm."""
    assert DIRECT.half_field_h_deg == pytest.approx(30.539, abs=0.001)
    assert DIRECT.half_field_v_deg == pytest.approx(18.414, abs=0.001)


def test_pixels_per_degree_in_direct_view_are_across_the_whole_panel():
    """S0 §5.2's mean, with the viewport the whole panel: 3840 px across 2 × 30.54°.
    (The spec's 56.8 is the center's, a different statistic.)"""
    assert DIRECT.pixels_per_degree(horizontal_pixels=3840) == pytest.approx(
        62.87, abs=0.005
    )


def test_direct_view_refuses_to_exist_without_the_housings():
    """A missing measurement is not an absent housing. A direct-view field with no
    exclusions would pass a stimulus drawn under a sensor, so it is refused, by either
    road to it, naming what is missing."""
    with pytest.raises(ValueError, match="§9 item 1"):
        Geometry.direct(58.997, 33.293, screen_distance_cm=50.0, housings=())
    with pytest.raises(ValueError, match="housings"):
        Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=50.0,
                 view="direct")


def test_a_setup_that_is_neither_is_refused():
    """`view="stereo"` is not a setup. Read as one or the other it would compute a
    field for a screen nobody has."""
    with pytest.raises(ValueError, match="'stereo' is not a setup"):
        Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=50.0,
                 view="stereo")


def test_a_stimulus_under_a_housing_cannot_be_shown():
    """Direct-view spec §4: check 8 refuses a stimulus that could overlap a housing,
    exactly as it refuses one off the panel. Both bottom corners here, since which
    corner the sensors take is a build finding."""
    assert not DIRECT.can_show(-29.0, -17.0)
    assert not DIRECT.can_show(29.0, -17.0)
    assert DIRECT.can_show(-29.0, 0.0), "the side of the panel, above the housing"
    assert DIRECT.can_show(0.0, -18.0), "the bottom of the panel, between them"
    assert DIRECT.can_show(16.0, 0.0)
    assert not DIRECT.can_show(31.0, 0.0), "off the panel"
    assert not DIRECT.can_show(0.0, 18.5), "off the panel"


def test_a_housings_margin_is_part_of_it():
    """The margin is recorded beside each rectangle and widens it on every side.
    4.5 cm in from the left edge is 26.565° left of center at 50 cm; 3.5 cm up from
    the bottom is 14.731° below it."""
    housing = HOUSINGS[0]
    assert housing.covers(4.5, 1.0) and not housing.covers(4.51, 1.0)
    assert housing.covers(-0.5, 1.0) and not housing.covers(-0.51, 1.0)
    assert housing.covers(2.0, 3.5) and not housing.covers(2.0, 3.51)
    assert housing.covers(2.0, -0.5) and not housing.covers(2.0, -0.51)

    assert not DIRECT.can_show(-26.6, -16.0)
    assert DIRECT.can_show(-26.5, -16.0)
    assert not DIRECT.can_show(-29.0, -14.8)
    assert DIRECT.can_show(-29.0, -14.6)


def test_the_mask_is_the_stereoscopes_field():
    """The PI's removable mask at the panel, ±12° to start (2026-09-28): inside the
    viewport's ±13.15° × ±14.77°, so it sets both edges."""
    assert MASKED.half_field_h_deg == 12.0
    assert MASKED.half_field_v_deg == 12.0
    assert MASKED.can_show(11.99, -11.99)
    assert not MASKED.can_show(12.01, 0.0)
    assert not MASKED.can_show(0.0, -12.01)


def test_a_mask_wider_than_the_viewport_stops_nothing():
    """The mask can only narrow the field. One cut wider than the viewport leaves the
    viewport's own edge, which is where the mirrors end."""
    wide = Geometry.stereoscope(
        58.997, 33.293, screen_distance_cm=50.0, half_ipd_cm=1.6, mask_deg=20.0
    )
    assert wide.half_field_h_deg == pytest.approx(13.146, abs=0.001)
    assert wide.half_field_v_deg == pytest.approx(14.768, abs=0.001)


def test_the_mask_covers_pixels_and_does_not_rescale_them():
    """Pixels per degree are the viewport's: the mask hides the edge, it does not
    change what one pixel subtends."""
    assert MASKED.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(
        STEREOSCOPE.pixels_per_degree(horizontal_pixels=1920)
    )
    assert MASKED.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(73.02, abs=0.005)
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_geometry.py`
Expected: collection fails, `ImportError: cannot import name 'Housing' from 'wl_expcontroller.geometry'`, and no test runs.

- [ ] **Step 3: Implement**

In `wl_expcontroller/geometry.py`, replace:

```python
"""Display geometry for the split-screen stereoscope.

One panel split down the middle, each eye viewing its half through a two-mirror
periscope. The mirrors translate rather than deviate, so the *optical path* is the
physical eye-to-panel distance plus the lateral shift. The screen is fixed 50 cm from
the eyes in both setups (PI, 2026-09-28), so through the stereoscope the path is about
63 cm, and it moves with each animal's eye spacing (`Geometry.stereoscope`).

**The panel is given by its active area, not its diagonal.** S0 §5.2's diagonal form
assumes an exact 16:9, and the rig's ASUS PG27UCDM is neither: ASUS publishes its
active area as 589.97 × 332.93 mm (1.772:1) and its diagonal as a rounded "26.5-inch
viewable". Feeding the rounded diagonal through the 16:9 fractions puts each edge
0.6-0.9% short of the published area (S0 §5.2).

Every number here is derived from `2026-08-31-stereoscope-optics-drawing.md` §3 and
S0 §5.2, and the tests assert the agreement. **They are computed, not measured.**
V9 measures each eye's real path per animal, because the mirror carriage is
adjustable and the two paths are equal only if the mirrors are.
```

with:

```python
"""Display geometry, for both setups: direct view and the split-screen stereoscope.

**One screen at one place, two paths to it** (direct-view spec §2). The screen is fixed
50 cm from the eyes in both setups (PI, 2026-09-28); the stereoscope is a removable device
in front of it.

- **Direct view:** both eyes see the whole panel, at the screen's own distance. The field
  is the panel's, less the light sensors' housings in a bottom corner (spec §4).
- **The stereoscope:** one panel split down the middle, each eye viewing its half through a
  two-mirror periscope. The mirrors translate rather than deviate, so the *optical path* is
  the physical distance plus the lateral shift: about 63 cm, moving with each animal's eye
  spacing (`Geometry.stereoscope`). A removable mask at the panel stops the field, at ±12°
  to start.

**The panel is given by its active area, not its diagonal.** S0 §5.2's diagonal form
assumes an exact 16:9, and the rig's ASUS PG27UCDM is neither: ASUS publishes its
active area as 589.97 × 332.93 mm (1.772:1) and its diagonal as a rounded "26.5-inch
viewable". Feeding the rounded diagonal through the 16:9 fractions puts each edge
0.6-0.9% short (S0 §5.2).

**Degrees map to the panel by `D · tan`, per axis**, so the field is a rectangle in degrees
as it is in centimeters, and a housing's rectangle on the panel is a region in degrees the
same way.

Every number here is derived from `2026-08-31-stereoscope-optics-drawing.md` §3,
S0 §5.2 and the direct-view spec §2, and the tests assert the agreement. **They are
computed, not measured.** V9 measures each eye's real path per animal, because the
mirror carriage is adjustable and the two paths are equal only if the mirrors are.
```

In `wl_expcontroller/geometry.py`, replace:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Geometry:
    #: The panel's active area. Each eye's viewport is half its width and all of
    #: its height.
    panel_width_cm: float
    panel_height_cm: float
    #: Along the **folded** optical path, not the physical distance to the panel.
    viewing_distance_cm: float

    @classmethod
```

with:

```python
from dataclasses import dataclass

#: The two setups a session can run in (direct-view spec §3). The operator picks one at
#: session start; a task's `Trial.view` names one of these, or `"either"`.
VIEWS = ("direct", "stereoscope")


@dataclass(frozen=True, slots=True)
class Housing:
    """One screen-timing light sensor's opaque housing, as a rectangle on the panel.

    **In cm from the active area's bottom-left corner, as the animal faces the screen**:
    `left_cm` and `right_cm` from its left edge, `bottom_cm` and `top_cm` up from its
    bottom edge -- what a person measures at build with a rule against the panel.

    `margin_cm` is recorded beside the rectangle (direct-view spec §4) and widens it on
    every side, because check 8 tests a stimulus's position, not its extent.
    """

    left_cm: float
    right_cm: float
    bottom_cm: float
    top_cm: float
    margin_cm: float

    def covers(self, x_cm: float, y_cm: float) -> bool:
        """Whether a point on the panel, in the same corner-origin cm, is under this
        housing or its margin."""
        return (
            self.left_cm - self.margin_cm <= x_cm <= self.right_cm + self.margin_cm
            and self.bottom_cm - self.margin_cm <= y_cm <= self.top_cm + self.margin_cm
        )


@dataclass(frozen=True, slots=True)
class Geometry:
    #: The panel's active area. Through the stereoscope each eye's viewport is half its
    #: width and all of its height; in direct view the viewport is the whole panel.
    panel_width_cm: float
    panel_height_cm: float
    #: Along the **folded** optical path through the stereoscope; the screen's own
    #: distance in direct view.
    viewing_distance_cm: float
    #: `"stereoscope"` or `"direct"` (`VIEWS`).
    view: str = "stereoscope"
    #: The stereoscope's mask at the panel, as a half-angle in degrees (direct-view spec
    #: §2), or `None` for the viewport's own field.
    mask_deg: float | None = None
    #: The light sensors' housings, direct view's alone: through the stereoscope the
    #: mask hides them. **Direct view refuses to exist without them.**
    housings: tuple[Housing, ...] = ()

    def __post_init__(self) -> None:
        if self.view not in VIEWS:
            raise ValueError(
                f"{self.view!r} is not a setup; a geometry is one of {', '.join(VIEWS)}"
            )
        if self.view == "direct" and not self.housings:
            raise ValueError(
                "direct view's field excludes the light sensors' housings, and none were "
                "given. They are measured at build (direct-view spec §9 item 1); a field "
                "without them would pass a stimulus drawn under a housing"
            )

    @classmethod
```

In `wl_expcontroller/geometry.py`, in `Geometry.stereoscope`, replace:

```python
    ) -> Geometry:
        """The field through the periscope, with the screen `screen_distance_cm` from
```

with:

```python
        mask_deg: float | None = None,
    ) -> Geometry:
        """The field through the periscope, with the screen `screen_distance_cm` from
```

In `wl_expcontroller/geometry.py`, in `Geometry.stereoscope`, replace:

```python
        )

    @property
    def half_width_cm(self) -> float:
        return self.panel_width_cm / 4
```

with:

```python
            mask_deg=mask_deg,
        )

    @classmethod
    def direct(
        cls,
        panel_width_cm: float,
        panel_height_cm: float,
        *,
        screen_distance_cm: float,
        housings: tuple[Housing, ...],
    ) -> Geometry:
        """The whole panel, seen by both eyes at the screen's own distance, less the
        light sensors' housings (direct-view spec §2, §4)."""
        return cls(
            panel_width_cm=panel_width_cm,
            panel_height_cm=panel_height_cm,
            viewing_distance_cm=screen_distance_cm,
            view="direct",
            housings=tuple(housings),
        )

    @property
    def half_width_cm(self) -> float:
        """The viewport's half-width: the whole panel's in direct view, one eye's half
        through the stereoscope."""
        return self.panel_width_cm / (2 if self.view == "direct" else 4)
```

In `wl_expcontroller/geometry.py`, in `Geometry.half_field_h_deg`, replace:

```python
        return math.degrees(math.atan(self.half_width_cm / self.viewing_distance_cm))

    @property
    def half_field_v_deg(self) -> float:
        return math.degrees(math.atan(self.half_height_cm / self.viewing_distance_cm))

    def pixels_per_degree(self, horizontal_pixels: int) -> float:
        """Across one eye's viewport, so `horizontal_pixels` is half the panel."""
        return horizontal_pixels / (2 * self.half_field_h_deg)

    def can_show(self, x_deg: float, y_deg: float) -> bool:
        """Whether a cyclopean position lands inside the field both eyes see.

        A position outside it is not a rendering problem to clamp -- the stimulus would
        be drawn off the panel, the animal would never see it, and the trial would
        score as a miss indistinguishable from behaviour. Refused at load instead.
        """
        return (
            abs(x_deg) <= self.half_field_h_deg
            and abs(y_deg) <= self.half_field_v_deg
        )
```

with:

```python
        """The horizontal half-field a stimulus may use: the viewport's, or the mask's
        where the mask is narrower."""
        return self._stopped(self._viewport_deg(self.half_width_cm))

    @property
    def half_field_v_deg(self) -> float:
        return self._stopped(self._viewport_deg(self.half_height_cm))

    def _viewport_deg(self, half_cm: float) -> float:
        return math.degrees(math.atan(half_cm / self.viewing_distance_cm))

    def _stopped(self, degrees: float) -> float:
        return degrees if self.mask_deg is None else min(degrees, self.mask_deg)

    def pixels_per_degree(self, horizontal_pixels: int) -> float:
        """S0 §5.2's mean across one viewport, so `horizontal_pixels` is the viewport's:
        half the panel through the stereoscope, all of it in direct view. Across the
        viewport's own extent, not the mask's: the mask covers pixels, it does not
        rescale them."""
        return horizontal_pixels / (2 * self._viewport_deg(self.half_width_cm))

    def can_show(self, x_deg: float, y_deg: float) -> bool:
        """Whether a cyclopean position lands inside the field the setup shows.

        A position outside it is not a rendering problem to clamp -- the stimulus would
        be drawn off the panel, behind the mask or under a light sensor's housing, the
        animal would never see it, and the trial would score as a miss
        indistinguishable from behavior. Refused at load instead.
        """
        if abs(x_deg) > self.half_field_h_deg or abs(y_deg) > self.half_field_v_deg:
            return False
        x_cm = self.panel_width_cm / 2 + self.viewing_distance_cm * math.tan(
            math.radians(x_deg)
        )
        y_cm = self.panel_height_cm / 2 + self.viewing_distance_cm * math.tan(
            math.radians(y_deg)
        )
        return not any(housing.covers(x_cm, y_cm) for housing in self.housings)
```

- [ ] **Step 4: The docs**

In `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md`, replace:

```markdown
100% APL — the number that decides how low we can sit, and therefore how long a panel lasts.

---
```

with:

```markdown
100% APL — the number that decides how low we can sit, and therefore how long a panel lasts.

### 5.5 Direct view

**Most experiments view the screen directly, and the first animal task does** (PI, 2026-09-27
and 2026-09-28). The stereoscope is a removable device in front of the same screen, and the
operator picks the setup at session start (`2026-09-28-direct-view-design.md` §1, §3).

- **One screen at one place.** `Z` = 50 cm, eye to screen, in both setups (§5.2), on a locked
  arm or stand with a stop. It is measured once at setup and re-checked in the regular rig
  checks (V9).
- **The field is the whole panel at `Z`**, the same image to both eyes: ±30.5° × ±18.4°, and
  62.9 px/deg by §5.2's formula with the whole panel as the viewport (56.8 px/deg at the
  center). **Less the light sensors' housings**, in a bottom corner around (±30°, −18°)
  (direct-view spec §4; S3 §8).
- **In code**, `geometry.Geometry.direct`: its `can_show` refuses a position under a housing's
  rectangle or its margin, as it refuses one off the panel. **It refuses to exist without the
  housings**, which are measured at build (direct-view spec §9 item 1). Through the
  stereoscope, `Geometry.stereoscope` takes the mask as `mask_deg`.

---
```

In `docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md`, replace:

```markdown
to per-eye viewport pixels using measured optics. That is what makes the same task run at a
different viewing distance, on a different panel, in either display mode, and on the S13 kiosk.
```

with:

```markdown
to viewport pixels using measured optics. That is what makes the same task run at a different
viewing distance, on a different panel, in either display mode, and on the S13 kiosk.
```

In `docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md`, replace:

````markdown
```

The mapping inputs are per-rig and per-animal, and all of them are **measured, not derived**:
````

with:

````markdown
```

**The mapping is per setup** (`2026-09-28-direct-view-design.md` §2). The diagram is the
stereoscope's: two per-eye viewports at the folded path `D`, stopped by the mask. **In direct
view there is one viewport, the whole panel, at the screen's own distance `Z`**, and both eyes
see it. Either way a position maps by `D · tan` per axis, so each field is a rectangle in degrees.
This module does not exist yet; `wl_expcontroller/geometry.py` fixes the mapping it must
implement, and the field check 8 uses is the one it will draw into.

The mapping inputs are per-rig and per-animal, and all of them are **measured, not derived**:
````

- [ ] **Step 5: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_geometry.py`
Expected: **20 passed**.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1144 passed**.

- [ ] **Step 6: Commit**

```bash
git add wl_expcontroller/geometry.py tests/test_geometry.py docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md
git commit -m "Give each setup its field: direct view less the sensor housings, the stereoscope stopped by its mask"
```

---

### Task 2: The rig's settings

**Why:** spec §2: "The rig's settings hold everything the geometry needs: `Z`; the mask's half-angle; the sensor housings' rectangles (§4)." None existed (Plan decision 1). `geometry.Rig` holds them and builds each setup's field, and `tasks/rig.py` is this rig's. Its housings are empty until measured, and a test pins that (Plan decision 2). Docs: the sensors in both setups (S3 §8, S4 §7), M0-REVIEW row 9, and V9's direct-view items (spec §7), as their own lines.

**Files:**
- Modify: `wl_expcontroller/geometry.py` (`Rig`, appended)
- Create: `tasks/rig.py`
- Modify: `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md` (§5.5), `docs/superpowers/specs/2026-08-31-S3-sync-integration-design.md` (§8), `docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md` (§7), `docs/M0-REVIEW.md` (row 9), `docs/validation.md` (V9)
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: Task 1's `Housing`, `Geometry.direct` and `Geometry.stereoscope(..., mask_deg=)`.
- Produces:
  - `geometry.Rig(panel_width_cm, panel_height_cm, screen_distance_cm, mask_deg, housings=())`, frozen; `Rig.direct() -> Geometry` (raises while `housings` is empty); `Rig.stereoscope(half_ipd_cm) -> Geometry` (masked).
  - `tasks/rig.py`: `RIG = Rig(58.997, 33.293, screen_distance_cm=50.0, mask_deg=12.0, housings=())`. Tasks 3–6 and the design tool import it; each builds direct view with `dataclasses.replace(RIG, housings=...)` and its stand-ins.

- [ ] **Step 1: Write the failing tests**

In `tests/test_geometry.py`, replace:

```python
from __future__ import annotations

import pytest

from wl_expcontroller.geometry import Geometry, Housing
```

with:

```python
from __future__ import annotations

from dataclasses import replace

import pytest

from tasks.rig import RIG
from wl_expcontroller.geometry import Geometry, Housing
```

Append to `tests/test_geometry.py`:

```python


# ---------------------------------------------------------------------------
# The rig's settings (direct-view spec §2), `tasks/rig.py`
# ---------------------------------------------------------------------------


def test_the_rigs_settings_are_its_screen_its_distance_and_its_mask():
    """"The rig's settings hold everything the geometry needs": the PG27UCDM's
    published active area, `Z` = 50 cm in both setups, and the mask at ±12° (PI,
    2026-09-28)."""
    assert (RIG.panel_width_cm, RIG.panel_height_cm) == (58.997, 33.293)
    assert RIG.screen_distance_cm == 50.0
    assert RIG.mask_deg == 12.0


def test_the_rigs_housings_are_unmeasured_so_direct_view_refuses_on_its_settings():
    """NOT YET MEASURED (direct-view spec §9 item 1), and this pins it: when the
    housings are written into `tasks/rig.py`, this fails, and is replaced by a test of
    the measured rectangles. Until then no task passes direct view on this rig."""
    assert RIG.housings == ()
    with pytest.raises(ValueError, match="§9 item 1"):
        RIG.direct()


def test_the_rig_gives_direct_view_the_panel_at_z_and_its_housings():
    assert replace(RIG, housings=HOUSINGS).direct() == DIRECT


def test_the_rig_gives_the_stereoscope_its_mask_and_the_subjects_path():
    """`E` comes from the subject's record (spec §2), so the stereoscope's field is
    built per subject; the mask is the rig's and stops it at every IPD the drawing
    tabulates."""
    assert RIG.stereoscope(half_ipd_cm=1.6) == MASKED
    assert RIG.stereoscope(half_ipd_cm=1.9).viewing_distance_cm == pytest.approx(
        62.849, abs=0.001
    )
    for half_ipd_cm in (1.5, 1.6, 1.9):
        field = RIG.stereoscope(half_ipd_cm=half_ipd_cm)
        assert (field.half_field_h_deg, field.half_field_v_deg) == (12.0, 12.0)
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_geometry.py`
Expected: collection fails, `ModuleNotFoundError: No module named 'tasks.rig'`, and no test runs.

- [ ] **Step 3: Implement**

Create `tasks/rig.py`:

```python
"""This rig's display settings: what both setups' fields are built from.

The direct-view spec §2: "The rig's settings hold everything the geometry needs: `Z`; the
mask's half-angle; the sensor housings' rectangles." One screen at one place serves both
setups, so one file does too: `Rig.direct()` is the field in direct view, and
`Rig.stereoscope(E)` the field through the stereoscope for a subject whose half-IPD, `E`,
comes from its record.

Python rather than YAML, for the reason the tasks and `reference_bounds.py` are (ADR-0006):
plain text, diffable, and read in an ordinary editor.

**The light sensors' housings are not measured yet** (direct-view spec §9 item 1: "measured
at build from the real sensors"). Until they are, `housings` is empty and `RIG.direct()`
refuses, so no task passes a direct-view check on this rig's settings. That is deliberate: a
field without them would pass a stimulus drawn under a housing, and a guessed rectangle is a
number nobody measured. The tests stand for this rig with stand-in housings they label as
such.

**No session is checked against this file yet**: `wlx run --view` and `wlx check --view` load
it in direct view part 2, after P4d-2b slice b2a merges (both change session start).
"""

from wl_expcontroller.geometry import Rig

RIG = Rig(
    # The ASUS PG27UCDM's published active area, 589.97 × 332.93 mm (spec page, read
    # 2026-09-28; S0 §5.1).
    panel_width_cm=58.997,
    panel_height_cm=33.293,
    # `Z`, eye to screen, physical, in both setups (PI, 2026-09-28; direct-view spec §1).
    # Measured once at setup and re-checked in the regular rig checks (V9).
    screen_distance_cm=50.0,
    # The stereoscope's removable mask at the panel, starting at ±12° (PI, 2026-09-28;
    # optics drawing §5).
    mask_deg=12.0,
    # NOT YET MEASURED: the light sensors' housings, each a rectangle with its margin,
    # measured at build from the real sensors (direct-view spec §4, §9 item 1). Until
    # then direct view refuses to exist on these settings.
    housings=(),
)
```

Append to `wl_expcontroller/geometry.py`:

```python


@dataclass(frozen=True, slots=True)
class Rig:
    """The rig's display settings: everything both setups' fields are built from
    (direct-view spec §2), written in the rig's settings file, `tasks/rig.py`.

    **The housings may be empty** while they are unmeasured (spec §9 item 1): then
    `direct` refuses, because `Geometry` does, and the stereoscope still works -- its
    mask hides the sensors.

    **Nothing outside the tests builds a session's field from this yet.** `wlx run
    --view`, which passes the chosen setup's field to `taskd`'s load-time check, is
    direct view part 2, after P4d-2b slice b2a merges (both change session start).
    """

    panel_width_cm: float
    panel_height_cm: float
    #: `Z`: eye to screen, physical, the same in both setups (PI, 2026-09-28).
    screen_distance_cm: float
    #: The stereoscope's mask, as a half-angle (±12° to start, PI 2026-09-28).
    mask_deg: float
    housings: tuple[Housing, ...] = ()

    def direct(self) -> Geometry:
        return Geometry.direct(
            self.panel_width_cm,
            self.panel_height_cm,
            screen_distance_cm=self.screen_distance_cm,
            housings=self.housings,
        )

    def stereoscope(self, half_ipd_cm: float) -> Geometry:
        """Through the stereoscope, for one subject's half-IPD, `E`, which comes from
        its record (spec §2)."""
        return Geometry.stereoscope(
            self.panel_width_cm,
            self.panel_height_cm,
            screen_distance_cm=self.screen_distance_cm,
            half_ipd_cm=half_ipd_cm,
            mask_deg=self.mask_deg,
        )
```

- [ ] **Step 4: The docs**

In `docs/M0-REVIEW.md`, replace:

```markdown
1.90 cm with the mask at the full viewport's ±13.15°, 5.51 cm at the ±10° requirement |
```

with:

```markdown
1.90 cm with the mask at the full viewport's ±13.15°, 5.51 cm at the ±10° requirement. **In direct view** (2026-09-28), the same bottom corner, each patch under its sensor's opaque housing; the housings' rectangles are measured at build, and until then direct view refuses to exist (`tasks/rig.py`; direct-view spec §4, §9 item 1) |
```

In `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md`, replace:

```markdown
  stereoscope, `Geometry.stereoscope` takes the mask as `mask_deg`.

---
```

with:

```markdown
  stereoscope, `Geometry.stereoscope` takes the mask as `mask_deg`.
- **The rig's settings are `tasks/rig.py`**, a `geometry.Rig`: the panel's active area, `Z`,
  the mask's half-angle and the housings' rectangles, each with its margin. No rig
  configuration existed before it. The housings are empty until measured, so direct view
  refuses on this rig's settings. No session is checked against the file until
  direct view part 2 (`wlx run --view`).

---
```

In `docs/superpowers/specs/2026-08-31-S3-sync-integration-design.md`, replace:

```markdown
**Cameras** take the barcode as a timebase to record, not a trigger — they free-run, and the
```

with:

```markdown
**In both setups the patches sit at one place: a bottom corner** (`2026-09-28-direct-view-design.md`
§4). The screen is fixed, so the sensors are mounted once and never moved. Through the stereoscope
that corner is inside the masked bottom strip. **In direct view each sensor's opaque housing
covers its patch**: the animal sees a small dark shape around (±30°, −18°), well outside the ±15°
where stimuli go, and never the flicker. The housings are rectangles, each with a margin, in the
rig's settings (`tasks/rig.py`), measured at build from the real sensors; direct view's field
excludes them, so check 8 refuses a stimulus that could overlap one, and until they are measured
direct view refuses to exist. The flicker is checked invisible from the animal's position in both
setups at bring-up (V9).

**Cameras** take the barcode as a timebase to record, not a trigger — they free-run, and the
```

In `docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md`, replace:

```markdown
  Outside both viewports, so neither is visible to either eye.
- **Verified dark to each eye at bring-up**, not assumed from geometry — a stray reflection off a
  mirror edge would put the flip patch back into the field, and that is a V9 item.
```

with:

```markdown
  Outside both viewports, so neither is visible to either eye. They sit at one bottom corner of
  it, the place they keep in direct view.
- **In direct view there is no strip**: each patch is covered by its sensor's opaque housing, a
  rectangle with a margin in the rig's settings that direct view's field excludes
  (`geometry.Housing`, `tasks/rig.py`; `2026-09-28-direct-view-design.md` §4).
- **Verified dark to each eye at bring-up, in both setups**, not assumed from geometry — a stray
  reflection off a mirror edge would put the flip patch back into the field, and a housing that
  leaks would show it in direct view. Both are V9 items.
```

In `docs/validation.md`, replace:

```markdown
## V10 — Pump calibration (millilitres per second of open time)
```

with:

```markdown
**Direct view** (added 2026-09-28, `2026-09-28-direct-view-design.md` §7):
1. Measure `Z` at setup. Re-check it in the regular rig checks against the stop.
2. Confirm from the animal's eye position that neither patch is visible: the housings cover
   the flicker.
3. Confirm the camera and light see the eye past the screen housing's bottom edge, with the
   paper's 35°/25° layout, and past the muzzle, the juice spout and the chair front.
4. Insert the stereoscope, and confirm that both lines are still clear and that the patches
   are dark to both eyes through the mask.

V1 already runs in every mode the rig uses (S0 §5.3). In direct view it covers luminance
uniformity and ABL across the whole panel, as a within-image nonlinearity rather than
interocular coupling.

## V10 — Pump calibration (millilitres per second of open time)
```

- [ ] **Step 5: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_geometry.py`
Expected: **24 passed**.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1148 passed**.

- [ ] **Step 6: Commit**

```bash
git add wl_expcontroller/geometry.py tasks/rig.py tests/test_geometry.py docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md docs/superpowers/specs/2026-08-31-S3-sync-integration-design.md docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md docs/M0-REVIEW.md docs/validation.md
git commit -m "Write the rig's display settings down, with the sensor housings refused until measured"
```

---

### Task 3: Check 8 against each setup's own field

**Why:** spec §2 and §4: check 8 runs against the setup's field, "including the housings and the mask", and "refuses a stimulus that could overlap a housing, exactly as it refuses one off the panel". Task 1's `can_show` already carries both, so this task pins them through `check()` (test the path, not the piece), makes the finding name the field it used (Plan decision 7), and moves the fixtures that pass tasks onto the rig's own fields (Plan decision 8). `check()` keeps `geometry=None` meaning unchecked, and `_offscreen_stimuli`'s docstring names direct view part 2 as what passes a geometry outside the tests.

**Files:**
- Modify: `wl_expcontroller/check.py` (`_offscreen_stimuli`: docstring, finding)
- Test: `tests/test_task_checks.py` (fixtures `GEOMETRY` and `DIRECT`; two boundary positions; four new tests), `tests/test_disparity.py` (`test_form_disparity_counts_toward_the_off_screen_check` on the rig's stereoscope)

**Interfaces:**
- Consumes: `tasks.rig.RIG`, `RIG.stereoscope(half_ipd_cm=1.6)`, `dataclasses.replace(RIG, housings=...).direct()`, `Housing`, `Geometry.view`, `Geometry.housings`.
- Produces: the `stimulus-off-screen` detail reads `outside the ±H° × ±V° <view> field`, followed by `, less the light sensors' housings` when the geometry has any. `tests/test_task_checks.py`'s `GEOMETRY` (the rig's masked stereoscope) and `DIRECT` (the rig in direct view with stand-ins), which Task 4 reuses.

- [ ] **Step 1: Write the failing tests**

In `tests/test_disparity.py`, in `test_form_disparity_counts_toward_the_off_screen_check`, replace:

```python
    from wl_expcontroller.geometry import Geometry

    geometry = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
    )
    safe = a_task(RDS(form=Corrugation(sf=0.5, amplitude=0.2)), at=(12.5, 0.0))
    extreme = a_task(RDS(form=Corrugation(sf=0.5, amplitude=8.0)), at=(12.5, 0.0))
```

with:

```python
    from tasks.rig import RIG

    # The rig's stereoscope at `E` = 1.6 cm, stopped by its ±12° mask.
    geometry = RIG.stereoscope(half_ipd_cm=1.6)
    safe = a_task(RDS(form=Corrugation(sf=0.5, amplitude=0.2)), at=(11.5, 0.0))
    extreme = a_task(RDS(form=Corrugation(sf=0.5, amplitude=8.0)), at=(11.5, 0.0))
```

In `tests/test_task_checks.py`, replace:

```python
from wl_expcontroller.codes import PROVISIONAL, Allocation
from wl_expcontroller.components import Registry
from wl_expcontroller.geometry import Geometry
```

with:

```python
from tasks.rig import RIG
from wl_expcontroller.codes import PROVISIONAL, Allocation
from wl_expcontroller.components import Registry
from wl_expcontroller.geometry import Geometry, Housing
```

In `tests/test_task_checks.py`, replace:

```python
#: The PG27UCDM through the stereoscope, the screen at 50 cm and E = 1.6 cm: a 63.15 cm
#: path and a ±13.15° × ±14.77° field per eye.
GEOMETRY = Geometry.stereoscope(
    panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
)
```

with:

```python
#: The rig's stereoscope (`tasks/rig.py`) at the drawing's `E` = 1.6 cm: a 63.15 cm path,
#: and the ±13.15° × ±14.77° viewport stopped by the PI's ±12° mask.
GEOMETRY = RIG.stereoscope(half_ipd_cm=1.6)

#: The rig in direct view, with **stand-in housings**: the real ones are unmeasured
#: (direct-view spec §9 item 1). One per bottom corner, 4 × 3 cm with a 0.5 cm margin.
DIRECT = replace(
    RIG,
    housings=(
        Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
        Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    ),
).direct()
```

In `tests/test_task_checks.py`, in `test_disparity_can_push_one_eye_off_screen_from_a_legal_cyclopean_position`, replace:

```python
                enter=[Show(Stimulus("s", at=(12.65, 0.0), disparity=2.0))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert GEOMETRY.can_show(12.65, 0.0), "the cyclopean position is legal"
```

with:

```python
                enter=[Show(Stimulus("s", at=(11.5, 0.0), disparity=2.0))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert GEOMETRY.can_show(11.5, 0.0), "the cyclopean position is legal"
```

In `tests/test_task_checks.py`, in `test_a_position_parameter_whose_range_stays_inside_the_field_is_accepted`, replace:

```python
        params=[Param("ecc", unit="deg", low=-12.5, high=12.5)],
```

with:

```python
        params=[Param("ecc", unit="deg", low=-11.5, high=11.5)],
```

Append to `tests/test_task_checks.py`:

```python


# ---------------------------------------------------------------------------
# Check 8 against each setup's own field (direct-view spec §2, §4)
# ---------------------------------------------------------------------------


def _showing(at, params=()) -> Trial:
    return Trial(
        start="show",
        params=list(params),
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=at))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )


def test_a_stimulus_under_a_light_sensors_housing_is_refused_in_direct_view():
    """Direct-view spec §4: "check 8 refuses a stimulus that could overlap a housing,
    exactly as it refuses one off the panel." The position is on the panel; the
    housing covers it."""
    findings = check(_showing((-29.0, -17.0)), geometry=DIRECT)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "direct field, less the light sensors' housings" in findings[0].detail


def test_a_range_that_can_reach_a_housing_is_refused():
    """Over the declared range, as check 8 always reasons: a target an experimenter
    can slide into the corner is refused before anyone does."""
    trial = _showing(
        (P("x"), -17.0), params=[Param("x", unit="deg", low=-29.0, high=0.0)]
    )

    assert [f.code for f in check(trial, geometry=DIRECT)] == ["stimulus-off-screen"]
    assert check(_showing((P("x"), 0.0), trial.params), geometry=DIRECT) == []


def test_direct_view_shows_what_the_stereoscopes_mask_stops():
    """The reference detection tasks' ±16°, which the interim narrowed to ±12° for the
    stereoscope. Direct view takes it; the mask refuses it, and says which field."""
    trial = _showing((P("ecc"), 0.0), params=[Param("ecc", unit="deg", low=-16.0, high=16.0)])

    assert check(trial, geometry=DIRECT) == []
    (finding,) = check(trial, geometry=GEOMETRY)
    assert finding.code == "stimulus-off-screen"
    assert "\u00b112.0\u00b0 \u00d7 \u00b112.0\u00b0 stereoscope field" in finding.detail


def test_the_mask_refuses_what_the_bare_viewport_would_show():
    """Held to the rig's field, not the optics': 12.5° is inside the viewport's ±13.15°
    and behind the mask, so an animal would never see it."""
    viewport = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
    )

    assert check(_showing((12.5, 0.0)), geometry=viewport) == []
    assert [f.code for f in check(_showing((12.5, 0.0)), geometry=GEOMETRY)] == [
        "stimulus-off-screen"
    ]
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_task_checks.py tests/test_disparity.py`
Expected: **2 failed, 30 passed**. `test_a_stimulus_under_a_light_sensors_housing_is_refused_in_direct_view` and `test_direct_view_shows_what_the_stereoscopes_mask_stops` fail on the finding's words: the refusal happens, but the detail says only `field`. The other two new tests and the moved fixtures already pass, because the refusals come from Task 1's `can_show`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/check.py`, in `_offscreen_stimuli`, replace:

```python
    Skipped when no geometry is supplied: a task is not wrong for being checked
    without a rig, it is unchecked, and the caller knows which it wanted.
```

with:

```python
    **Against the setup's own field** (direct-view spec §2, §4): the whole panel less
    the light sensors' housings in direct view, the mask through the stereoscope. A
    stimulus under a housing is refused exactly as one off the panel is.

    Skipped when no geometry is supplied: a task is not wrong for being checked
    without a rig, it is unchecked, and the caller knows which it wanted. **No caller
    outside the tests supplies one yet**: `taskd` and `wlx check` call `check()`
    without a geometry until direct view part 2 passes the session's in.
```

In `wl_expcontroller/check.py`, in `_offscreen_stimuli`, replace:

```python
                f"\u00b1{geometry.half_field_v_deg:.1f}\u00b0 field"
```

with:

```python
                f"\u00b1{geometry.half_field_v_deg:.1f}\u00b0 {geometry.view} field"
                + (", less the light sensors' housings" if geometry.housings else "")
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_task_checks.py tests/test_disparity.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1152 passed**.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/check.py tests/test_task_checks.py tests/test_disparity.py
git commit -m "Hold check 8 to the rig's own fields, housings and mask included, and name the field"
```

---

### Task 4: `Trial.view`, and a task held to its setup

**Why:** spec §3: "A task says which setup it is written for: `Trial.view`, one of `"direct"`, `"stereoscope"` or `"either"`, default `"either"`." Disparity and random-dot stereograms need `"stereoscope"`, and so does a stimulus shown to one eye (Plan decision 6). A task written for one setup is refused in the other, naming both, so part 2 has only to pass the session's geometry in. Existing stereogram tests now declare the stereoscope, as a stereogram task must. Docs: `architecture.md`'s display section, which until now routed every task through the stereoscope, and the controller architecture's D6.

**Files:**
- Modify: `wl_expcontroller/task.py` (`Trial.view`)
- Modify: `wl_expcontroller/check.py` (imports; `check()`; `TRIAL_VIEWS`, `_view_faults`, `_stereo_content`, appended)
- Modify: `docs/design/architecture.md` ("Stereo, as viewports", retitled), `docs/superpowers/specs/2026-08-31-controller-architecture-design.md` (D6)
- Test: `tests/test_task_checks.py`, `tests/test_disparity.py` (`a_task` declares the stereoscope; one rebuilt trial keeps it)

**Interfaces:**
- Consumes: `geometry.VIEWS`, `Geometry.view`; `check.py`'s `_ranges`, `_widest`, `_appearances`; `task.actions_of`, `task.Unchanged`; Task 3's `GEOMETRY` and `DIRECT` in `tests/test_task_checks.py`.
- Produces:
  - `Trial.view: str = "either"`, the last field.
  - `check.TRIAL_VIEWS = ("direct", "stereoscope", "either")`.
  - Three findings, appended last by `check()`: `unknown-view` (alone, when `view` is not in `TRIAL_VIEWS`); `needs-stereoscope`, one per piece of stereo content, when `view != "stereoscope"`, with or without a geometry; `wrong-setup`, when a geometry is given and `view` is neither `"either"` nor the geometry's `view`. Each detail names what it found; `wrong-setup` names `written for '<view>'` and `checked against '<geometry.view>'`.
  - `check._view_faults(trial, geometry) -> list[Finding]`; `check._stereo_content(trial) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_disparity.py`, in `a_task`, replace:

```python
    stimulus_kwargs.setdefault("at", (0.0, 0.0))
    return Trial(
        start="on",
```

with:

```python
    """A stereogram task, so it declares the stereoscope (direct-view spec §3)."""
    stimulus_kwargs.setdefault("at", (0.0, 0.0))
    return Trial(
        start="on",
        view="stereoscope",
```

In `tests/test_disparity.py`, in `test_correlation_is_a_parameter_so_the_control_is_a_value_not_a_task`, replace:

```python
    )
    assert codes(trial) == set()
```

with:

```python
        view=trial.view,
    )
    assert codes(trial) == set()
```

In `tests/test_task_checks.py`, replace:

```python
    REMEMBERED,
    After,
```

with:

```python
    RDS,
    REMEMBERED,
    After,
```

In `tests/test_task_checks.py`, replace:

```python
    Window,
    Trial,
```

with:

```python
    Update,
    Window,
    Trial,
```

In `tests/test_task_checks.py`, in `test_disparity_can_push_one_eye_off_screen_from_a_legal_cyclopean_position`, replace:

```python
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(11.5, 0.0), disparity=2.0))],
```

with:

```python
    trial = Trial(
        start="show",
        view="stereoscope",
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(11.5, 0.0), disparity=2.0))],
```

Append to `tests/test_task_checks.py`:

```python


# ---------------------------------------------------------------------------
# Which setup a task is written for (direct-view spec §3)
# ---------------------------------------------------------------------------


def _task(*enter, view="either", params=()) -> Trial:
    """One state that shows a plain disc, then does `enter`, then ends."""
    return Trial(
        start="show",
        view=view,
        params=list(params),
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(0.0, 0.0))), *enter],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )


def test_a_task_is_either_until_it_says_otherwise():
    """The default is safe because check 8 runs against whichever setup the session
    chose: an undeclared task in the stereoscope is held to the mask."""
    assert _task().view == "either"
    assert check(_task(), geometry=DIRECT) == []
    assert check(_task(), geometry=GEOMETRY) == []


def test_disparity_needs_a_task_that_declares_the_stereoscope():
    """"Two side-by-side images on an unmirrored screen are not a stimulus." Refused
    with or without a geometry: it is the task's content, not the session's."""
    shifted = Update("s", disparity=0.4)

    (finding,) = check(_task(shifted))
    assert finding.code == "needs-stereoscope"
    assert "gives 's' disparity" in finding.detail
    assert "view='either'" in finding.detail
    assert [f.code for f in check(_task(shifted, view="direct"))] == ["needs-stereoscope"]
    assert check(_task(shifted, view="stereoscope")) == []


def test_a_disparity_parameter_counts_when_its_range_can_leave_zero():
    """Over the declared range, as every range check here: a disparity an
    experimenter can dial in is disparity."""
    ranged = [Param("d", unit="deg", low=-0.5, high=0.5)]
    pinned = [Param("d", unit="deg", low=0.0, high=0.0)]

    assert [f.code for f in check(_task(Update("s", disparity=P("d")), params=ranged))] == [
        "needs-stereoscope"
    ]
    assert check(_task(Update("s", disparity=P("d")), params=pinned)) == []


def test_a_shown_stereogram_or_one_a_parameter_can_choose_needs_the_stereoscope():
    """A random-dot stereogram has no content but its disparity. One reachable only
    through a parameter's choices is as real as one written into a `Show`."""
    shown = _task(Show(Stimulus("rds", at=(0.0, 0.0), looks=RDS())))
    chosen = _task(params=[Param("looks", unit="appearance", choices=(RDS(),))])
    updated = _task(Update("s", looks=RDS()))

    for trial in (shown, chosen, updated):
        (finding,) = check(trial)
        assert finding.code == "needs-stereoscope"
        assert "random-dot stereogram" in finding.detail


def test_a_stimulus_shown_to_one_eye_needs_the_stereoscope():
    """Plan decision: an unmirrored screen shows both eyes one image, so a stimulus
    for one eye is the same impossibility as disparity -- by `Show` or by `Update`."""
    left = _task(Show(Stimulus("left", at=(2.0, 0.0), eye="left")))
    right = _task(Update("s", eye="right"))

    assert [f.detail.split(",")[0] for f in check(left)] == [
        "state 'show' shows 'left' to the left eye only"
    ]
    assert [f.code for f in check(right)] == ["needs-stereoscope"]
    assert check(_task(Update("s", eye="both"))) == []


def test_a_task_written_for_one_setup_is_refused_in_the_other_naming_both():
    """Spec §3: "a stereoscope task in direct view, or a direct task in the
    stereoscope" -- the refusal part 2's session start will show, naming both
    sides."""
    (in_direct,) = check(_task(view="stereoscope"), geometry=DIRECT)
    (in_stereoscope,) = check(_task(view="direct"), geometry=GEOMETRY)

    assert in_direct.code == in_stereoscope.code == "wrong-setup"
    assert "written for 'stereoscope'" in in_direct.detail
    assert "checked against 'direct'" in in_direct.detail
    assert "written for 'direct'" in in_stereoscope.detail
    assert "checked against 'stereoscope'" in in_stereoscope.detail
    assert check(_task(view="direct"), geometry=DIRECT) == []
    assert check(_task(view="stereoscope"), geometry=GEOMETRY) == []


def test_without_a_geometry_the_setup_is_unchecked():
    """`geometry=None` still means unchecked (S1 §9 check 8): a task is not wrong for
    being checked without a rig."""
    assert check(_task(view="stereoscope")) == []
    assert check(_task(view="direct")) == []


def test_a_view_that_is_no_setup_is_refused():
    """`view="stereo"` is not a declaration. Read as either setup it would be checked
    against the wrong one; read as neither it would pass everything."""
    (finding,) = check(_task(Update("s", disparity=0.4), view="stereo"), geometry=DIRECT)

    assert finding.code == "unknown-view"
    assert "'stereo'" in finding.detail
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_task_checks.py tests/test_disparity.py`
Expected: **14 failed, 26 passed**, every failure `TypeError: Trial.__init__() got an unexpected keyword argument 'view'`: the eight new tests, the stereoscope-declaring disparity test in `test_task_checks.py`, and five tests in `test_disparity.py` that build `a_task`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/check.py`, replace:

```python
from wl_expcontroller.geometry import Geometry
```

with:

```python
from wl_expcontroller.geometry import VIEWS, Geometry
```

In `wl_expcontroller/check.py`, replace:

```python
    Update,
    Window,
```

with:

```python
    Unchanged,
    Update,
    Window,
```

In `wl_expcontroller/check.py`, in `check`, replace:

```python
        + _unreachable_timeouts(trial)
        + _crowded_arrays(trial)
    )


def _unreachable_states(trial: Trial) -> list[Finding]:
```

with:

```python
        + _unreachable_timeouts(trial)
        + _crowded_arrays(trial)
        + _view_faults(trial, geometry)
    )


def _unreachable_states(trial: Trial) -> list[Finding]:
```

Append to `wl_expcontroller/check.py`:

```python


# --- Which setup -------------------------------------------------------------

#: What `Trial.view` may say (direct-view spec §3): one setup, or either.
TRIAL_VIEWS = (*VIEWS, "either")


def _view_faults(trial: Trial, geometry: Geometry | None) -> list[Finding]:
    """A task says which setup it is written for, and is held to it (direct-view
    spec §3).

    **Stereo content needs the stereoscope, with or without a geometry**: it is a
    property of the task, not of the session, so it is refused at every load. **Against
    a geometry, a task written for the other setup is refused, naming both**, so a
    caller that passes the session's geometry has nothing else to do. That caller is
    direct view part 2: until then `taskd` and `wlx check` pass none, and only the
    tests reach the mismatch. An unrecognized `view` is refused outright, as an
    unrecognized eye is: it would be checked as neither.
    """
    if trial.view not in TRIAL_VIEWS:
        return [
            Finding(
                "unknown-view",
                f"the task's view is {trial.view!r}; it must be one of "
                f"{', '.join(TRIAL_VIEWS)}. An unrecognized setup is not a "
                f"declaration, and nothing could be checked against it",
            )
        ]
    findings: list[Finding] = []
    if trial.view != "stereoscope":
        findings += [
            Finding(
                "needs-stereoscope",
                f"{what}, and the task declares view={trial.view!r}; only the "
                f"stereoscope shows each eye its own image, so declare "
                f"view='stereoscope'. On an unmirrored screen both eyes see both "
                f"images, which is not the stimulus the task describes",
            )
            for what in _stereo_content(trial)
        ]
    if geometry is not None and trial.view not in ("either", geometry.view):
        findings.append(
            Finding(
                "wrong-setup",
                f"the task is written for {trial.view!r} and is checked against "
                f"{geometry.view!r}; a task written for one setup is refused in the "
                f"other (direct-view spec §3)",
            )
        )
    return findings


def _stereo_content(trial: Trial) -> list[str]:
    """Everything a task shows that only the stereoscope can: disparity, a
    random-dot stereogram (direct-view spec §3), and a stimulus shown to one eye.

    **Parameter choices count**, for `_appearances`' reason: an appearance only a
    parameter selects is as real as one written into a `Show`.
    """
    ranges = _ranges(trial)
    found = [
        "it can show a random-dot stereogram"
        for looks in _appearances(trial)
        if isinstance(looks, RDS)
    ]
    for state, action in actions_of(trial):
        if isinstance(action, Show):
            name, carrier = action.stimulus.name, action.stimulus
        elif isinstance(action, Update):
            name, carrier = action.stimulus, action
        else:
            continue
        if not isinstance(carrier.disparity, Unchanged) and any(
            value != 0.0 for value in _widest(carrier.disparity, ranges)
        ):
            found.append(f"state {state!r} gives {name!r} disparity")
        if not isinstance(carrier.eye, Unchanged) and carrier.eye != "both":
            found.append(f"state {state!r} shows {name!r} to the {carrier.eye} eye only")
    return found
```

In `wl_expcontroller/task.py`, in `Trial`, replace:

```python
    tolerances: "Tolerances" = field(default_factory=lambda: Tolerances())


@dataclass(frozen=True, slots=True)
```

with:

```python
    tolerances: "Tolerances" = field(default_factory=lambda: Tolerances())
    #: Which setup the task is written for: `"direct"`, `"stereoscope"` or `"either"`
    #: (direct-view spec §3). **`"either"` is safe as the default** because the field
    #: check runs against the setup the session chose, so an undeclared task in the
    #: stereoscope is held to its mask. Disparity, a random-dot stereogram or a
    #: stimulus shown to one eye needs `"stereoscope"`, and the checker says so.
    view: str = "either"


@dataclass(frozen=True, slots=True)
```

- [ ] **Step 4: The docs**

In `docs/design/architecture.md`, replace:

```markdown
## Stereo, as viewports

Split-screen mirror stereoscope on **one panel**: each eye views one half through
redirection mirrors. Therefore one window, one flip, one refresh clock, no genlock —
**two viewports on one framebuffer**, in cyclopean coordinates with disparity as a
stimulus property. The monocular v1 task is the zero-disparity case of the same path.

Per-eye viewport geometry (center, folded optical path length, deg/pixel) is measured, not
derived. Mirror angles set vergence, so alignment is a calibrated parameter with a real
alignment procedure. Photodiode patches sit outside both viewports. Panel left/right
nonuniformity is by construction an interocular mismatch and is photometered in V1.
```

with:

```markdown
## The display: direct view, and stereo as viewports

**Two setups share one screen, fixed 50 cm from the eyes** (`2026-09-28-direct-view-design.md`).
**Direct view** — both eyes see the whole panel — is where most experiments run, the first
animal task included. The split-screen mirror stereoscope is a removable device in front of the
same screen. The operator picks the setup at session start. Each setup has its own field in
`geometry.py`, built from the rig's settings (`tasks/rig.py`): the whole panel less the light
sensors' housings, or the stereoscope's viewport stopped by its mask.

**A task says which setup it is written for**: `Trial.view`, `"direct"`, `"stereoscope"` or
`"either"` (the default). Disparity, a random-dot stereogram or a stimulus shown to one eye needs
`"stereoscope"`, a load-time finding at every load. Check 8 against the session's field, and the
refusal of a task written for the other setup, need the session's geometry, which `taskd` and
`wlx check` do not pass until direct view part 2 (`wlx run --view`, after P4d-2b b2a merges);
until then only the tests reach them.

Through the stereoscope each eye views one half of the panel through redirection mirrors.
Therefore one window, one flip, one refresh clock, no genlock — **two viewports on one
framebuffer**, in cyclopean coordinates with disparity as a stimulus property. A monocular task
is the zero-disparity case of the same path, and runs in either setup.

Per-eye viewport geometry (center, folded optical path length, deg/pixel) is measured, not
derived. Mirror angles set vergence, so alignment is a calibrated parameter with a real
alignment procedure. Photodiode patches sit outside both viewports, at a bottom corner, and
under the sensors' housings in direct view. Panel left/right nonuniformity is by construction
an interocular mismatch and is photometered in V1.
```

In `docs/superpowers/specs/2026-08-31-controller-architecture-design.md`, replace:

```markdown
the monocular v1 task is the zero-disparity case of the stereo path. | architecture.md's display section |
```

with:

```markdown
the monocular v1 task is the zero-disparity case of the stereo path. **Amended 2026-09-28: direct view is the other setup, and the first.** One screen fixed at 50 cm serves both, the stereoscope is removable, the operator picks the setup at session start, and a task declares `Trial.view` (`2026-09-28-direct-view-design.md`). | architecture.md's display section |
```

- [ ] **Step 5: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_task_checks.py tests/test_disparity.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1160 passed**.

- [ ] **Step 6: Commit**

```bash
git add wl_expcontroller/task.py wl_expcontroller/check.py tests/test_task_checks.py tests/test_disparity.py docs/design/architecture.md docs/superpowers/specs/2026-08-31-controller-architecture-design.md
git commit -m "Let a task say which setup it is written for, and refuse stereo content anywhere else"
```

---

### Task 5: Calibration per setup

**Why:** spec §6. The constellation was placed as a fraction of the per-eye field, and in direct view that would put targets far beyond the stimuli and P4's reach. So it is placed over a **calibration region** per setup: ±15° × ±15° in direct view, and the mask's ±12° in the stereoscope (Plan decision 9). `tools/calibration_design.py` is rerun for each region by the 2026-09-05 method (Plan decision 10), and each result is a new dated record; the 2026-09-05 record stays as written. Each setup gets the reach its record chose: **85% in direct view and 100% in the stereoscope, both close calls.** The tool changed and is outside the gate, so it gets tests (Plan decision 11). Docs: S5, the constellation per setup.

**Files:**
- Modify: `wl_expcontroller/calibration.py` (`DIRECT_REGION_DEG`, `REACH`, `region` before `constellation`; `constellation`)
- Modify: `tools/calibration_design.py` (docstring; imports; `FIELD`, `EXTENT`, `SHOWN_REACH`; `Setup`, `SETUPS`, `use`, `_pct`; `augmented`, `tested_region`; sections 1, 2 and 4–7; `main`)
- Create: `docs/measurements/dev-machine/2026-09-28-calibration-constellation-direct.md`, `docs/measurements/dev-machine/2026-09-28-calibration-constellation-stereoscope.md`
- Modify: `docs/superpowers/specs/2026-08-31-S5-eye-tracking-design.md` (§1, §2)
- Test: `tests/test_calibration.py`; create `tests/test_calibration_design.py`

**Interfaces:**
- Consumes: `Geometry.view` and its mask-clipped half-fields; `tasks.rig.RIG`, `RIG.stereoscope(half_ipd_cm=1.6)`, `RIG.mask_deg`.
- Produces:
  - `calibration.DIRECT_REGION_DEG = 15.0`.
  - `calibration.REACH: dict[str, float] = {"direct": 0.85, "stereoscope": 1.0}`. It was a float, 0.75; nothing outside `calibration.py` read it.
  - `calibration.region(geometry) -> tuple[float, float]`.
  - `calibration.constellation(geometry, reach: float | None = None, intermediate=INTERMEDIATE, margin=MARGIN)`, which uses `REACH[geometry.view]` when `reach` is `None`. `conditions(geometry, ...)` is unchanged and so follows it.
  - `tools/calibration_design.py`: `Setup(record, extent, half, field, max_tested_deg, reach)`, `SETUPS` keyed `2026-09-05`, `direct` and `stereoscope`, `use(name) -> Setup`, and `main(argv=None)` taking `--setup`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_calibration.py`, replace:

```python
import os

import pytest

from wl_expcontroller.calibration import (
    MIN_CONDITIONING,
    RAW_DEFINITION,
```

with:

```python
import os
from dataclasses import replace

import pytest

from tasks.rig import RIG
from wl_expcontroller.calibration import (
    DIRECT_REGION_DEG,
    MIN_CONDITIONING,
    RAW_DEFINITION,
    REACH,
```

In `tests/test_calibration.py`, replace:

```python
)
from wl_expcontroller.geometry import Geometry
```

with:

```python
    region,
)
from wl_expcontroller.geometry import Geometry, Housing
```

In `tests/test_calibration.py`, in `test_a_ring_cannot_carry_a_second_order_map`, replace:

```python
    assert conditioning(ring, Model.AFFINE) > MIN_CONDITIONING[Model.AFFINE]


def test_the_constellation_survives_losing_four_targets():
```

with:

```python
    assert conditioning(ring, Model.AFFINE) > MIN_CONDITIONING[Model.AFFINE]


# ---------------------------------------------------------------------------
# The constellation per setup (direct-view spec §6)
# ---------------------------------------------------------------------------

#: The rig in direct view, with **stand-in housings**: the real ones are unmeasured
#: (direct-view spec §9 item 1). One per bottom corner, 4 × 3 cm with a 0.5 cm margin.
DIRECT = replace(
    RIG,
    housings=(
        Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
        Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    ),
).direct()

#: The rig's stereoscope at `E` = 1.6 cm, stopped by its ±12° mask.
MASKED = RIG.stereoscope(half_ipd_cm=1.6)


def test_each_setup_places_its_constellation_over_its_own_region():
    """±15° × ±15° in direct view, where the stimuli go, and the mask's ±12° in the
    stereoscope -- never direct view's whole field, which would put targets far
    beyond both the stimuli and P4's reach. The bare optics keep their own field."""
    assert DIRECT_REGION_DEG == 15.0
    assert region(DIRECT) == (15.0, 15.0)
    assert region(MASKED) == (12.0, 12.0)
    assert region(GEOMETRY) == (GEOMETRY.half_field_h_deg, GEOMETRY.half_field_v_deg)


def test_each_setup_gets_the_reach_its_record_chose():
    """85% in direct view and 100% in the stereoscope, each a close call its 2026-09-28
    record says so about. The outer targets sit at reach × margin × region."""
    assert REACH == {"direct": 0.85, "stereoscope": 1.0}

    direct, masked = constellation(DIRECT), constellation(MASKED)

    assert max(abs(x) for x, _ in direct) == pytest.approx(0.85 * 0.85 * 15.0)
    assert max(abs(y) for _, y in direct) == pytest.approx(0.85 * 0.85 * 15.0)
    assert max(abs(x) for x, _ in masked) == pytest.approx(0.85 * 12.0)
    assert max(abs(y) for _, y in masked) == pytest.approx(0.85 * 12.0)


def test_a_reach_given_still_overrides_the_setups():
    widest = max(abs(x) for x, _ in constellation(MASKED, reach=0.5))
    assert widest == pytest.approx(0.5 * 0.85 * 12.0)


def test_every_target_of_both_setups_can_be_shown():
    for geometry in (DIRECT, MASKED):
        for x, y in constellation(geometry):
            assert geometry.can_show(x, y), f"({x:.2f}, {y:.2f}) in {geometry.view}"


def test_both_setups_carry_the_second_order_map_and_survive_losing_four():
    """Scaling moves where the targets are, never whether they constrain the model:
    each setup's thirteen condition the quadratic basis, and so do its first nine."""
    for geometry in (DIRECT, MASKED):
        targets = constellation(geometry)
        assert len(targets) == 13
        assert conditioning(targets, Model.SECOND_ORDER) >= MIN_CONDITIONING[Model.SECOND_ORDER]
        assert conditioning(targets[:9], Model.SECOND_ORDER) >= MIN_CONDITIONING[
            Model.SECOND_ORDER
        ]


def test_the_constellation_survives_losing_four_targets():
```

Create `tests/test_calibration_design.py`:

```python
"""The design tool that chose each setup's reach, held to the records it wrote.

`tools/calibration_design.py` is outside the mutation gate -- no gate mode reaches
`tools/` -- so these tests are what a hand sweep of it reads. They pin what is
deterministic: each setup's inputs, the region a run scores, the constellation section
7 lays out (against the committed record, digit for digit), and that a run prints every
section for its setup. **The Monte-Carlo tables are not compared here**: they are
reproduced by rerunning the script, which the records say how to do, and a byte-for-byte
test of them would hold CI to another machine's floating point.

The tool imports `wl-preproc`'s own conditioning metric, so without that checkout these
skip, and under `WLX_REQUIRE_PREPROC=1` they fail, as `test_calibration.py`'s do.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path

import pytest

from wl_expcontroller.calibration import DIRECT_REGION_DEG, REACH

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "docs" / "measurements" / "dev-machine"

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    import wl_preproc.eye.calibration  # noqa: F401 -- the tool measures with theirs
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). The "
            f"design tool measures with their conditioning metric, so without it these "
            f"tests would report a tool nobody ran"
        ) from exc
    _AVAILABLE = False
else:
    _AVAILABLE = True

pytestmark = pytest.mark.skipif(
    not _AVAILABLE, reason="wl-preproc checkout not beside this repo; the tool cannot run"
)


def _tool():
    """A fresh copy of the tool for each test: `use` rebinds its module globals, and
    no test may inherit another's setup."""
    spec = importlib.util.spec_from_file_location(
        "calibration_design", ROOT / "tools" / "calibration_design.py"
    )
    module = importlib.util.module_from_spec(spec)
    # `dataclass` looks its module up here to read the tool's annotations.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def _section_7(text: str) -> str:
    return text[text.index("## 7."):].strip()


def test_the_default_setup_is_the_one_the_2026_09_05_record_was_measured_on():
    tool = _tool()
    setup = tool.use("2026-09-05")

    assert setup.record == "2026-09-05-calibration-constellation.md"
    assert (tool.HALF_H, tool.HALF_V) == (
        tool.GEOMETRY.half_field_h_deg,
        tool.GEOMETRY.half_field_v_deg,
    )
    assert tool.FIELD == (tool.HALF_H, tool.HALF_V)
    assert (tool.MAX_TESTED_DEG, tool.SHOWN_REACH) == (16.0, 0.75)


def test_direct_view_is_scored_over_its_whole_disc_and_scaled_to_its_region():
    """The detection tasks' ±16° is wider than the ±15° region, so the disc must not
    be clipped to the region: it lies inside the field, and a window can land there."""
    tool = _tool()
    setup = tool.use("direct")

    assert setup.record == "2026-09-28-calibration-constellation-direct.md"
    assert (tool.HALF_H, tool.HALF_V) == (DIRECT_REGION_DEG, DIRECT_REGION_DEG)
    assert tool.FIELD is None
    assert tool.SHOWN_REACH == REACH["direct"]
    points = tool.tested_region()
    assert max(math.hypot(x, y) for x, y in points) == pytest.approx(16.0)
    assert max(abs(x) for x, _ in points) > DIRECT_REGION_DEG


def test_the_stereoscope_is_scaled_to_its_mask_and_scored_inside_it():
    tool = _tool()
    setup = tool.use("stereoscope")

    assert setup.record == "2026-09-28-calibration-constellation-stereoscope.md"
    assert (tool.HALF_H, tool.HALF_V) == (12.0, 12.0)
    assert tool.FIELD == (12.0, 12.0)
    assert tool.SHOWN_REACH == REACH["stereoscope"]
    points = tool.tested_region()
    assert max(math.hypot(x, y) for x, y in points) == pytest.approx(12.0)
    assert all(abs(x) <= 12.0 and abs(y) <= 12.0 for x, y in points)


@pytest.mark.parametrize("name", ["2026-09-05", "direct", "stereoscope"])
def test_each_records_constellation_is_what_the_tool_lays_out_now(name, capsys):
    """Section 7 is arithmetic, not simulation, so it is compared with the committed
    record digit for digit: a change to a region, a reach or the mask that leaves a
    record describing a constellation the code no longer presents fails here."""
    tool = _tool()
    setup = tool.use(name)
    tool.section_recommended()

    record = (RECORDS / setup.record).read_text()
    assert capsys.readouterr().out.strip() == _section_7(record)


@pytest.mark.parametrize(
    ("argv", "extent", "reach"),
    [
        ([], "Per-eye field: +/-17.01 deg horizontal, +/-18.99 deg vertical.", "75%"),
        (
            ["--setup", "direct"],
            "Calibration region, direct view: +/-15.00 deg horizontal, +/-15.00 deg vertical.",
            "85%",
        ),
        (
            ["--setup", "stereoscope"],
            "Calibration region, stereoscope (the mask): +/-12.00 deg horizontal, "
            "+/-12.00 deg vertical.",
            "100%",
        ),
    ],
)
def test_a_run_prints_every_section_for_its_setup(argv, extent, reach, capsys):
    tool = _tool()
    tool.main(argv)
    out = capsys.readouterr().out

    for section in range(1, 8):
        assert f"\n## {section}. " in out, f"section {section} is missing"
    assert extent in out
    assert out.count(f"| 3x3 @{reach} + 4 intermediates |") == 2
    assert out.count(f"| 3x3 @{reach} (9) |") == 2
    assert f"| 5x5 @{reach} (25) |" in out
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider --continue-on-collection-errors tests/test_calibration.py tests/test_calibration_design.py`
Expected: both files fail to collect, `ImportError: cannot import name 'DIRECT_REGION_DEG' from 'wl_expcontroller.calibration'`, and no test runs. (Without `--continue-on-collection-errors` pytest stops at the first.)

- [ ] **Step 3: Implement the region and the reach per setup**

In `wl_expcontroller/calibration.py`, replace:

```python
#: Fractions of the per-eye half-field. Measured, not chosen: see
#: `docs/measurements/dev-machine/2026-09-05-calibration-constellation.md`.
#: `REACH` at 0.75 beat 0.6, 0.7, 0.85 and 1.0 under every optics assumption swept --
#: pushing targets to the panel edge is worse than pulling them in, because the
#: corners sit outside the disc any task uses and their leverage drags the quadratic
#: away from where stimuli actually go. `INTERMEDIATE` at 0.5 beat 0.35, 0.7 and 1.0
#: on dropout survival and conditioning, at identical accuracy.
MARGIN = 0.85
REACH = 0.75
INTERMEDIATE = 0.50


def constellation(
    geometry: Geometry,
    reach: float = REACH,
    intermediate: float = INTERMEDIATE,
    margin: float = MARGIN,
) -> tuple[tuple[float, float], ...]:
    """The thirteen targets the calibration block presents, in degrees.

    A 3x3 grid plus four intermediates on the diagonals, scaled to each axis of the
    per-eye field separately -- which is **taller than it is wide**, because
    splitting the panel halves each eye's width and keeps its full height. A grid
    square in degrees would be the wrong shape for it.
```

with:

```python
#: Direct view's calibration region, ±15° × ±15° (direct-view spec §6): the PI's
#: stimulus range, "out to about 15°" (2026-09-27), inside the ±18.4° vertical field.
#: The whole field would put targets far beyond both the stimuli and P4's reach.
DIRECT_REGION_DEG = 15.0

#: Fractions of each setup's calibration region (`region`), inside `MARGIN`. Measured
#: per setup, not chosen (direct-view spec §6): see the two 2026-09-28 records under
#: `docs/measurements/dev-machine/`. **Both are close calls**: each reach won under
#: three of four optics assumptions and lost the fourth by 0.001°. A single `REACH` of
#: 0.75 was measured on the 31.5-inch stereoscope (the 2026-09-05 record, which stands
#: as written). `INTERMEDIATE` at 0.5 beat 0.35, 0.7 and 1.0 on dropout survival and
#: conditioning there, and still does in both setups, at accuracy within 0.01° of the
#: best.
MARGIN = 0.85
REACH: dict[str, float] = {"direct": 0.85, "stereoscope": 1.0}
INTERMEDIATE = 0.50


def region(geometry: Geometry) -> tuple[float, float]:
    """The half-extents, in degrees, that `geometry`'s constellation is placed over.

    **Per setup** (direct-view spec §6): ±15° × ±15° in direct view, where the stimuli
    go, and the mask in the stereoscope -- which is the field `geometry` already reports.
    """
    if geometry.view == "direct":
        return (DIRECT_REGION_DEG, DIRECT_REGION_DEG)
    return (geometry.half_field_h_deg, geometry.half_field_v_deg)


def constellation(
    geometry: Geometry,
    reach: float | None = None,
    intermediate: float = INTERMEDIATE,
    margin: float = MARGIN,
) -> tuple[tuple[float, float], ...]:
    """The thirteen targets the calibration block presents, in degrees.

    A 3x3 grid plus four intermediates on the diagonals, scaled to each axis of the
    setup's calibration region separately (`region`), at that setup's `REACH` unless
    `reach` is given. The rig's two regions are square; the bare optics' field is
    **taller than it is wide**, because splitting the panel halves each eye's width
    and keeps its full height, which is why the axes stay separate.
```

In `wl_expcontroller/calibration.py`, in `constellation`, replace:

```python
    half_h = geometry.half_field_h_deg * margin
    half_v = geometry.half_field_v_deg * margin
```

with:

```python
    extent_h, extent_v = region(geometry)
    half_h = extent_h * margin
    half_v = extent_v * margin
    reach = REACH[geometry.view] if reach is None else reach
```

- [ ] **Step 4: The design tool, per setup**

In `tools/calibration_design.py`, replace:

```python
Run: `python3 tools/calibration_design.py` from the repository root, with a
`wl-preproc` checkout beside this one. Results are committed under
`docs/measurements/2026-09-05-calibration-constellation.md`; regenerate that file
from this script rather than editing its numbers by hand.
```

with:

```python
Run: `python3 tools/calibration_design.py [--setup NAME]` from the repository root,
with a `wl-preproc` checkout beside this one. Each setup is the source of one record
under `docs/measurements/dev-machine/` (`SETUPS` names it); regenerate a record from
this script rather than editing its numbers by hand. The default, `2026-09-05`, is the
31.5-inch stereoscope that record was measured on, and still regenerates it byte for
byte.
```

In `tools/calibration_design.py`, replace:

```python
import math
import sys
```

with:

```python
import argparse
import math
import sys
from dataclasses import dataclass
```

In `tools/calibration_design.py`, replace:

```python
from wl_expcontroller.geometry import Geometry  # noqa: E402
```

with:

```python
from tasks.rig import RIG  # noqa: E402
from wl_expcontroller.calibration import DIRECT_REGION_DEG, REACH  # noqa: E402
from wl_expcontroller.geometry import Geometry  # noqa: E402
```

In `tools/calibration_design.py`, replace:

```python
#: Per-fixation scatter: where the animal's gaze actually sits relative to the
#: target centre, not sample noise within a fixation. An assumption, swept in
#: `fixations_per_target` rather than asserted.
FIXATION_NOISE_DEG = 0.35
```

with:

```python
#: Where a window can land, which the tested disc is clipped to; `None` when the disc
#: lies inside the field whole. On 2026-09-05 the field was the extent itself.
FIELD: tuple[float, float] | None = (HALF_H, HALF_V)

#: What section 7 calls the extent the constellation is scaled to.
EXTENT = "Per-eye field"

#: The reach sections 1, 2 and 4-7 lay their designs out at: section 3's choice.
SHOWN_REACH = 0.75

#: Per-fixation scatter: where the animal's gaze actually sits relative to the
#: target centre, not sample noise within a fixation. An assumption, swept in
#: `fixations_per_target` rather than asserted.
FIXATION_NOISE_DEG = 0.35



@dataclass(frozen=True)
class Setup:
    """What one record measures: the extent the constellation is scaled to (the
    per-eye field on 2026-09-05; a calibration region since the direct-view spec's
    §6), where a window can land, and the reach the record chose."""

    record: str
    extent: str
    half: tuple[float, float]
    field: tuple[float, float] | None
    max_tested_deg: float
    reach: float


#: The stereoscope's record is measured at the drawing's `E` = 1.6 cm. Its ±12° mask
#: is inside the viewport at every IPD the drawing tabulates, so `E` moves nothing here.
_STEREOSCOPE = RIG.stereoscope(half_ipd_cm=1.6)

SETUPS: dict[str, Setup] = {
    "2026-09-05": Setup(
        record="2026-09-05-calibration-constellation.md",
        extent="Per-eye field",
        half=(HALF_H, HALF_V),
        field=(HALF_H, HALF_V),
        max_tested_deg=16.0,
        reach=0.75,
    ),
    # Direct view's region, ±15°, where the stimuli go (direct-view spec §6). Windows
    # land out to ±16°, the detection tasks' range in direct view; that disc lies inside
    # the ±30.5° × ±18.4° field, clear of the housings near (±30°, −18°), so nothing is
    # clipped -- and the field itself is not built here, because direct view refuses to
    # exist without the housings, which are unmeasured (`tasks/rig.py`).
    "direct": Setup(
        record="2026-09-28-calibration-constellation-direct.md",
        extent="Calibration region, direct view",
        half=(DIRECT_REGION_DEG, DIRECT_REGION_DEG),
        field=None,
        max_tested_deg=16.0,
        reach=REACH["direct"],
    ),
    # The mask, which is the stereoscope's field and its calibration region at once.
    # Windows land anywhere inside it, so the tested disc runs to its half-angle.
    "stereoscope": Setup(
        record="2026-09-28-calibration-constellation-stereoscope.md",
        extent="Calibration region, stereoscope (the mask)",
        half=(_STEREOSCOPE.half_field_h_deg, _STEREOSCOPE.half_field_v_deg),
        field=(_STEREOSCOPE.half_field_h_deg, _STEREOSCOPE.half_field_v_deg),
        max_tested_deg=RIG.mask_deg,
        reach=REACH["stereoscope"],
    ),
}


def use(name: str) -> Setup:
    """Point every section at one setup. The sections read module globals, as they
    did when there was one setup, so the 2026-09-05 run is unchanged line for line."""
    global HALF_H, HALF_V, FIELD, MAX_TESTED_DEG, EXTENT, SHOWN_REACH
    setup = SETUPS[name]
    HALF_H, HALF_V = setup.half
    FIELD = setup.field
    MAX_TESTED_DEG = setup.max_tested_deg
    EXTENT = setup.extent
    SHOWN_REACH = setup.reach
    return setup


def _pct(reach: float) -> str:
    return "%d%%" % round(100 * reach)
```

In `tools/calibration_design.py`, in `augmented`, replace:

```python
def augmented(reach: float = 0.75, fraction: float = 0.50) -> np.ndarray:
    """The recommended constellation: a 3x3 plus four intermediates."""
```

with:

```python
def augmented(reach: float | None = None, fraction: float = 0.50) -> np.ndarray:
    """The recommended constellation: a 3x3 plus four intermediates, at the setup's
    reach unless told otherwise."""
    reach = SHOWN_REACH if reach is None else reach
```

In `tools/calibration_design.py`, in `tested_region`, replace:

```python
    to the panel. Not the panel's corners, which no task reaches."""
    angles = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    rings = []
    for eccentricity in np.linspace(0.5, MAX_TESTED_DEG, step):
        points = np.column_stack(
            [eccentricity * np.cos(angles), eccentricity * np.sin(angles)]
        )
        inside = (np.abs(points[:, 0]) <= HALF_H) & (np.abs(points[:, 1]) <= HALF_V)
        rings.append(points[inside])
```

with:

```python
    to the field. Not the panel's corners, which no task reaches."""
    angles = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    rings = []
    for eccentricity in np.linspace(0.5, MAX_TESTED_DEG, step):
        points = np.column_stack(
            [eccentricity * np.cos(angles), eccentricity * np.sin(angles)]
        )
        if FIELD is not None:
            inside = (np.abs(points[:, 0]) <= FIELD[0]) & (np.abs(points[:, 1]) <= FIELD[1])
            points = points[inside]
        rings.append(points)
```

In `tools/calibration_design.py`, in `section_conditioning`, replace:

```python
        "3x3, 60% of the field": grid(3, reach=0.6),
        "3x3 @75% + 4 intermediates": augmented(),
```

with:

```python
        "3x3, 60% of the field": grid(3, reach=0.6),
        "3x3 @%s + 4 intermediates" % _pct(SHOWN_REACH): augmented(),
```

In `tools/calibration_design.py`, in `section_honesty`, replace:

```python
        "3x3 @75% + 4 intermediates": augmented(),
```

with:

```python
        "3x3 @%s + 4 intermediates" % _pct(SHOWN_REACH): augmented(),
```

In `tools/calibration_design.py`, in `section_count`, replace:

```python
        "3x3 @75% (9)": grid(3, reach=0.75),
        "3x3 + intermediates @0.35 (13)": augmented(fraction=0.35),
        "3x3 + intermediates @0.50 (13)": augmented(fraction=0.50),
        "3x3 + intermediates @0.70 (13)": augmented(fraction=0.70),
        "3x3 + intermediates at corners (13)": augmented(fraction=1.00),
        "5x5 @75% (25)": grid(5, reach=0.75),
```

with:

```python
        "3x3 @%s (9)" % _pct(SHOWN_REACH): grid(3, reach=SHOWN_REACH),
        "3x3 + intermediates @0.35 (13)": augmented(fraction=0.35),
        "3x3 + intermediates @0.50 (13)": augmented(fraction=0.50),
        "3x3 + intermediates @0.70 (13)": augmented(fraction=0.70),
        "3x3 + intermediates at corners (13)": augmented(fraction=1.00),
        "5x5 @%s (25)" % _pct(SHOWN_REACH): grid(5, reach=SHOWN_REACH),
```

In `tools/calibration_design.py`, in `section_dropout`, replace:

```python
        "3x3 @75% (9)": grid(3, reach=0.75),
```

with:

```python
        "3x3 @%s (9)" % _pct(SHOWN_REACH): grid(3, reach=SHOWN_REACH),
```

In `tools/calibration_design.py`, in `section_held_out`, replace:

```python
    fit_targets = grid(3, reach=0.75)
    test_targets = diagonals(0.75, 0.50)
```

with:

```python
    fit_targets = grid(3, reach=SHOWN_REACH)
    test_targets = diagonals(SHOWN_REACH, 0.50)
```

In `tools/calibration_design.py`, in `section_recommended`, replace:

```python
    print("Per-eye field: +/-%.2f deg horizontal, +/-%.2f deg vertical.\n" % (HALF_H, HALF_V))
```

with:

```python
    print("%s: +/-%.2f deg horizontal, +/-%.2f deg vertical.\n" % (EXTENT, HALF_H, HALF_V))
```

In `tools/calibration_design.py`, in `section_recommended`, replace:

```python
        print("| %s | %.2f | %.2f | %.2f |" % (label, x, y, np.hypot(x, y)))


def main() -> None:
    rng = np.random.default_rng(20260905)
    print("# Calibration constellation: measurements\n")
```

with:

```python
        print("| %s | %.2f | %.2f | %.2f |" % (label, x, y, np.hypot(x, y)))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--setup", choices=sorted(SETUPS), default="2026-09-05")
    use(parser.parse_args(argv).setup)
    rng = np.random.default_rng(20260905)
    print("# Calibration constellation: measurements\n")
```

- [ ] **Step 5: The two records**

These are the tool's output on the development machine (`dev-machine`), under a hand-written account of what each settled, in the 2026-09-05 record's form.

Create `docs/measurements/dev-machine/2026-09-28-calibration-constellation-direct.md`:

```markdown
# Calibration constellation in direct view — how far out the targets go

> **This is a simulation, not a rig measurement, and must never be cited as one.**
> There is no eye tracker, no animal and no camera. The forward model from gaze angle
> to raw Purkinje vector is an *assumption* — stated in the script, swept across four
> optics settings, and replaced by bench data at V3. **No degree value below is a claim
> about our hardware.** What the numbers do support is a *ranking* between
> constellations, and every ranking here is reported across the whole sweep so it is
> visible whether it survives the assumption changing.
>
> The conditioning column is different in kind: it is `wl-preproc`'s own
> `_conditioning`, imported from their source rather than reimplemented, so that
> column is exactly what will gate a real session.

**Date:** 2026-09-28. **Script:** `tools/calibration_design.py --setup direct`, seeded as the
2026-09-05 run was, deterministic. **Setup:** direct view. The constellation is placed over
its calibration region, **±15° × ±15°**, the PI's stimulus range, rather than over the field
(`2026-09-28-direct-view-design.md` §6). **Tested region:** a disc out to 16°, the detection
tasks' range in direct view. It lies inside direct view's ±30.5° × ±18.4°, clear of the light
sensors' housings near (±30°, −18°), so nothing is clipped. **Against:** `wl-preproc` at
`7a060e0`.

**The method is 2026-09-05's**: the same forward model and optics sweep, the same margin
(0.85), the same seed and the same sections. Three inputs changed: the extent the constellation
is scaled to (this region, where 2026-09-05 used the per-eye field), the tested disc, and the
reach sections 1, 2 and 4–7 lay their designs out at, which is the one section 3 chose. "The
field" in the generated tables below means this region.

## What it settled

**85% of the region, inside the margin: a 3×3 at ±10.84°, corners at 15.33°, plus four
intermediates at half that** — `calibration.REACH["direct"]`. Coordinates in section 7.

1. **A close call, said plainly.** 85% wins under three of the four optics assumptions
   (moderate, strong obliquity, radial-dominated). Under near-axial, 100% wins by 0.001°
   (0.217 against 0.218): a difference in the third decimal of a mean over 60 simulated
   calibrations, so a tie. Averaged over the four assumptions, 85% is 0.213° and 100% is
   0.221°. Pulling in further loses clearly: 75% is 0.235–0.258°.
2. **Thirteen points still buy survival, and 0.50 is still the intermediates' place**: 95% of
   five-target dropouts still pass the gate, against 88% at 0.70 (section 5), at accuracy
   within 0.01° of the best intermediate fraction (section 4).
3. **Conditioning still cannot see extent**: a 3×3 shrunk to 60% of the region understates its
   own error by 4.4× (section 2).

**What this does not model: P4's reach**, about 10° in macaques (S5 §1). The edges at 10.8° sit
at it and the corners at 15.3° beyond it, where gaze comes from the pupil and corneal-reflection
fallback (PI, 2026-09-27; its design is pending). That is the region's cost, and the region is
the spec's.

---

# Calibration constellation: measurements

Generated by `tools/calibration_design.py`. Do not edit the numbers by hand.

## 1. Conditioning, and what it cannot see

Gate: 0.05 affine, 0.10 second-order.

| constellation | affine | second-order | verdict |
|---|---|---|---|
| ring of 8 | 1.0000 | 0.0000 | **REFUSED** |
| ring of 8 + centre | 1.0000 | 0.1697 | pass |
| 3x3, spanning the field | 1.0000 | 0.2277 | pass |
| 3x3, 60% of the field | 1.0000 | 0.2277 | pass |
| 3x3 @85% + 4 intermediates | 1.0000 | 0.2765 | pass |

## 2. What the reported residual hides

`rms_residual_deg` is the number an operator judges a calibration by, and
the number that goes in the file `wl-preproc` reads. It is trustworthy
only when the targets span the region the task will test.

| constellation | residual at targets | true P95 over tested region | understated by |
|---|---|---|---|
| ring of 8 + centre | 0.090 | 0.217 | 2.4x |
| 3x3, 60% of the field | 0.094 | 0.413 | 4.4x |
| 3x3, spanning the field | 0.125 | 0.212 | 1.7x |
| 3x3 @85% + 4 intermediates | 0.119 | 0.200 | 1.7x |

## 3. How far out the targets should reach

P95 error (deg) over the tested region, 3x3 grid, 11 fixations/target.

| optics | 60% | 70% | 75% | 85% | 100% | best |
|---|---|---|---|---|---|---|
| near-axial | 0.378 | 0.288 | 0.250 | 0.218 | 0.217 | **100%** |
| moderate | 0.371 | 0.275 | 0.235 | 0.205 | 0.208 | **85%** |
| strong obliquity | 0.394 | 0.288 | 0.256 | 0.206 | 0.235 | **85%** |
| radial-dominated | 0.429 | 0.302 | 0.258 | 0.222 | 0.225 | **85%** |

## 4. Target count, at equal animal cost

P95 error (deg) over the tested region; total fixations held at 130.

| design | n | fix/target | near-axial | moderate | strong obliquity | radial-dominated |
|---|---|---|---|---|---|---|
| 3x3 @85% (9) | 9 | 14 | 0.203 | 0.195 | 0.194 | 0.196 |
| 3x3 + intermediates @0.35 (13) | 13 | 10 | 0.207 | 0.211 | 0.213 | 0.221 |
| 3x3 + intermediates @0.50 (13) | 13 | 10 | 0.209 | 0.205 | 0.213 | 0.215 |
| 3x3 + intermediates @0.70 (13) | 13 | 10 | 0.209 | 0.197 | 0.206 | 0.215 |
| 3x3 + intermediates at corners (13) | 13 | 10 | 0.219 | 0.210 | 0.213 | 0.218 |
| 5x5 @85% (25) | 25 | 5 | 0.215 | 0.210 | 0.209 | 0.218 |

## 5. Surviving targets the animal will not work

Percentage of random dropouts that still fit (>= 6 points) and still pass
the 0.10 gate. **This is the whole case for thirteen points.**

| design | lose 0 | lose 1 | lose 2 | lose 3 | lose 4 | lose 5 |
|---|---|---|---|---|---|---|
| 3x3 @85% (9) | 100% | 100% | 100% | 70% | 0% | 0% |
| 3x3 + intermediates @0.50 (13) | 100% | 100% | 100% | 100% | 99% | 95% |
| 3x3 + intermediates @0.70 (13) | 100% | 100% | 100% | 99% | 96% | 88% |

## 6. Why the intermediates are fit points, not held-out points

Holding four of the thirteen out to estimate error was proposed and then
measured down. Four points at ten fixations each carry a noise floor of
about 0.11 deg, which is the same size as the error being estimated, so the
estimate cannot resolve it. `spread` is the standard deviation of the
held-out estimate across repeats of the SAME calibration: a gate whose
reading moves that much between identical sessions cannot be acted on.

| optics | held-out estimate | spread | true RMS | error |
|---|---|---|---|---|
| near-axial | 0.187 | +/-0.047 | 0.129 | +44% |
| moderate | 0.182 | +/-0.050 | 0.137 | +33% |
| strong obliquity | 0.188 | +/-0.054 | 0.128 | +46% |
| radial-dominated | 0.197 | +/-0.058 | 0.135 | +46% |

The estimate is wrong by a similar margin whether the model fits the
optics or not, so the gap between residual and held-out does not
discriminate misfit either -- which was the reason to hold them out.
They do more good inside the fit, where section 5 shows what they buy.


## 7. The constellation this recommends

Calibration region, direct view: +/-15.00 deg horizontal, +/-15.00 deg vertical.

| role | x (deg) | y (deg) | eccentricity |
|---|---|---|---|
| centre | 0.00 | 0.00 | 0.00 |
| edge, horizontal (x2) | 10.84 | 0.00 | 10.84 |
| edge, vertical (x2) | 0.00 | 10.84 | 10.84 |
| corner (x4) | 10.84 | 10.84 | 15.33 |
| intermediate (x4) | 5.42 | 5.42 | 7.66 |
```

Create `docs/measurements/dev-machine/2026-09-28-calibration-constellation-stereoscope.md`:

```markdown
# Calibration constellation through the stereoscope — how far out the targets go

> **This is a simulation, not a rig measurement, and must never be cited as one.**
> There is no eye tracker, no animal and no camera. The forward model from gaze angle
> to raw Purkinje vector is an *assumption* — stated in the script, swept across four
> optics settings, and replaced by bench data at V3. **No degree value below is a claim
> about our hardware.** What the numbers do support is a *ranking* between
> constellations, and every ranking here is reported across the whole sweep so it is
> visible whether it survives the assumption changing.
>
> The conditioning column is different in kind: it is `wl-preproc`'s own
> `_conditioning`, imported from their source rather than reimplemented, so that
> column is exactly what will gate a real session.

**Date:** 2026-09-28. **Script:** `tools/calibration_design.py --setup stereoscope`, seeded as
the 2026-09-05 run was, deterministic. **Setup:** the stereoscope, whose calibration region is
its field (`2026-09-28-direct-view-design.md` §6): the viewport at `E` = 1.6 cm (`D` = 63.15 cm,
±13.15° × ±14.77°) stopped by the **±12° mask** (`tasks/rig.py`). The mask is inside the
viewport at every IPD the optics drawing tabulates, so `E` moves nothing here. **Tested
region:** a disc out to 12°, since a stereoscope task may place a window anywhere the mask allows
along an axis; not the corners, which no task reaches, as on 2026-09-05. **Against:**
`wl-preproc` at `7a060e0`.

**The method is 2026-09-05's**: the same forward model and optics sweep, the same margin
(0.85), the same seed and the same sections. Three inputs changed: the extent the constellation
is scaled to (the mask, where 2026-09-05 used the unmasked per-eye field of the 31.5-inch
panel), the tested disc, and the reach sections 1, 2 and 4–7 lay their designs out at, which is
the one section 3 chose. "The field" in the generated tables below means the mask.

## What it settled

**100% of the mask, inside the margin: a 3×3 at ±10.20°, corners at 14.42°, plus four
intermediates at half that** — `calibration.REACH["stereoscope"]`. Coordinates in section 7.

1. **A close call, said plainly.** 100% wins under three of the four optics assumptions
   (near-axial, moderate, radial-dominated). Under strong obliquity, 85% wins by 0.001° (0.174
   against 0.175), a tie. Averaged over the four assumptions, 100% is 0.169° and 85% is 0.179°.
2. **100% is the top of the sweep.** Beyond it the targets would leave the margin, which keeps
   them 1.8° inside the mask's edge (0.15 × 12°): the method stops there, because a target at
   the very edge is one the animal saccades to and half-misses. With the mask as both the
   region and the edge of the tested disc, pushing out wins.
3. **It settles the closer call** the stereo-geometry rework's rerun found on this panel, where
   85% won under two of four assumptions (direct-view spec §6). That run was over the unmasked
   viewport.
4. **Thirteen points and 0.50 as before**: 95% of five-target dropouts pass, against 88% at 0.70
   (section 5), at accuracy within 0.01° of the best intermediate fraction (section 4).
   Conditioning still cannot see extent: 60% of the mask understates its own error by 3.9×
   (section 2).

**What this does not model: P4's reach**, about 10° in macaques (S5 §1). The edges at 10.2° sit
at it and the corners at 14.4° beyond it, where the pupil and corneal-reflection fallback takes
over (PI, 2026-09-27; its design is pending).

---

# Calibration constellation: measurements

Generated by `tools/calibration_design.py`. Do not edit the numbers by hand.

## 1. Conditioning, and what it cannot see

Gate: 0.05 affine, 0.10 second-order.

| constellation | affine | second-order | verdict |
|---|---|---|---|
| ring of 8 | 1.0000 | 0.0000 | **REFUSED** |
| ring of 8 + centre | 1.0000 | 0.1697 | pass |
| 3x3, spanning the field | 1.0000 | 0.2277 | pass |
| 3x3, 60% of the field | 1.0000 | 0.2277 | pass |
| 3x3 @100% + 4 intermediates | 1.0000 | 0.2765 | pass |

## 2. What the reported residual hides

`rms_residual_deg` is the number an operator judges a calibration by, and
the number that goes in the file `wl-preproc` reads. It is trustworthy
only when the targets span the region the task will test.

| constellation | residual at targets | true P95 over tested region | understated by |
|---|---|---|---|
| ring of 8 + centre | 0.085 | 0.191 | 2.2x |
| 3x3, 60% of the field | 0.091 | 0.353 | 3.9x |
| 3x3, spanning the field | 0.094 | 0.164 | 1.7x |
| 3x3 @100% + 4 intermediates | 0.115 | 0.146 | 1.3x |

## 3. How far out the targets should reach

P95 error (deg) over the tested region, 3x3 grid, 11 fixations/target.

| optics | 60% | 70% | 75% | 85% | 100% | best |
|---|---|---|---|---|---|---|
| near-axial | 0.323 | 0.246 | 0.212 | 0.183 | 0.161 | **100%** |
| moderate | 0.316 | 0.237 | 0.202 | 0.174 | 0.161 | **100%** |
| strong obliquity | 0.338 | 0.243 | 0.217 | 0.174 | 0.175 | **85%** |
| radial-dominated | 0.358 | 0.246 | 0.216 | 0.185 | 0.178 | **100%** |

## 4. Target count, at equal animal cost

P95 error (deg) over the tested region; total fixations held at 130.

| design | n | fix/target | near-axial | moderate | strong obliquity | radial-dominated |
|---|---|---|---|---|---|---|
| 3x3 @100% (9) | 9 | 14 | 0.164 | 0.156 | 0.153 | 0.150 |
| 3x3 + intermediates @0.35 (13) | 13 | 10 | 0.147 | 0.149 | 0.162 | 0.160 |
| 3x3 + intermediates @0.50 (13) | 13 | 10 | 0.152 | 0.150 | 0.157 | 0.154 |
| 3x3 + intermediates @0.70 (13) | 13 | 10 | 0.155 | 0.148 | 0.156 | 0.161 |
| 3x3 + intermediates at corners (13) | 13 | 10 | 0.171 | 0.166 | 0.177 | 0.174 |
| 5x5 @100% (25) | 25 | 5 | 0.154 | 0.144 | 0.146 | 0.151 |

## 5. Surviving targets the animal will not work

Percentage of random dropouts that still fit (>= 6 points) and still pass
the 0.10 gate. **This is the whole case for thirteen points.**

| design | lose 0 | lose 1 | lose 2 | lose 3 | lose 4 | lose 5 |
|---|---|---|---|---|---|---|
| 3x3 @100% (9) | 100% | 100% | 100% | 70% | 0% | 0% |
| 3x3 + intermediates @0.50 (13) | 100% | 100% | 100% | 100% | 99% | 95% |
| 3x3 + intermediates @0.70 (13) | 100% | 100% | 100% | 99% | 96% | 88% |

## 6. Why the intermediates are fit points, not held-out points

Holding four of the thirteen out to estimate error was proposed and then
measured down. Four points at ten fixations each carry a noise floor of
about 0.11 deg, which is the same size as the error being estimated, so the
estimate cannot resolve it. `spread` is the standard deviation of the
held-out estimate across repeats of the SAME calibration: a gate whose
reading moves that much between identical sessions cannot be acted on.

| optics | held-out estimate | spread | true RMS | error |
|---|---|---|---|---|
| near-axial | 0.185 | +/-0.046 | 0.110 | +68% |
| moderate | 0.181 | +/-0.050 | 0.121 | +49% |
| strong obliquity | 0.184 | +/-0.054 | 0.114 | +62% |
| radial-dominated | 0.195 | +/-0.057 | 0.112 | +73% |

The estimate is wrong by a similar margin whether the model fits the
optics or not, so the gap between residual and held-out does not
discriminate misfit either -- which was the reason to hold them out.
They do more good inside the fit, where section 5 shows what they buy.


## 7. The constellation this recommends

Calibration region, stereoscope (the mask): +/-12.00 deg horizontal, +/-12.00 deg vertical.

| role | x (deg) | y (deg) | eccentricity |
|---|---|---|---|
| centre | 0.00 | 0.00 | 0.00 |
| edge, horizontal (x2) | 10.20 | 0.00 | 10.20 |
| edge, vertical (x2) | 0.00 | 10.20 | 10.20 |
| corner (x4) | 10.20 | 10.20 | 14.42 |
| intermediate (x4) | 5.10 | 5.10 | 7.21 |
```

Then check that each record, and the 2026-09-05 one, is what the tool prints:

Run: `for s in direct stereoscope; do diff <(python tools/calibration_design.py --setup $s) <(sed -n '/^# Calibration constellation: measurements/,$p' docs/measurements/dev-machine/2026-09-28-calibration-constellation-$s.md) && echo "$s regenerates"; done; diff <(python tools/calibration_design.py) <(sed -n '/^# Calibration constellation: measurements/,$p' docs/measurements/dev-machine/2026-09-05-calibration-constellation.md) && echo "2026-09-05 regenerates"`
Expected: `direct regenerates`, `stereoscope regenerates` and `2026-09-05 regenerates`, with no diff lines. The Monte-Carlo tables are seeded and deterministic on one machine; if another prints a different last digit, that is floating point, and section 7, which the suite compares, is arithmetic.

- [ ] **Step 6: The docs**

In `docs/superpowers/specs/2026-08-31-S5-eye-tracking-design.md`, replace:

```markdown
reach 8.4–12.6° in the stereoscope on the PG27UCDM with the screen at 50 cm
(`calibration.constellation`; 10.8–16.3° on the 31.5" panel,
`docs/research/2026-09-27-panel-27-vs-32.md`). Where P4 cannot be vouched
for, gaze comes from `pupil − CR1` instead:
```

with:

```markdown
reach 10.8–15.3° in direct view and 10.2–14.4° through the stereoscope's ±12° mask on the
PG27UCDM with the screen at 50 cm (`calibration.constellation`, per setup since 2026-09-28,
§2; 10.8–16.3° on the 31.5" panel, `docs/research/2026-09-27-panel-27-vs-32.md`). Where P4
cannot be vouched for, gaze comes from `pupil − CR1` instead:
```

In `docs/superpowers/specs/2026-08-31-S5-eye-tracking-design.md`, replace:

```markdown
uses, and their leverage drags the quadratic away from where stimuli actually go.

---
```

with:

```markdown
uses, and their leverage drags the quadratic away from where stimuli actually go.

**Amended 2026-09-28: the constellation is placed per setup** (`2026-09-28-direct-view-design.md`
§6). The same 3×3 plus four intermediates, scaled to a **calibration region** rather than the
field: **±15° × ±15° in direct view**, the stimulus range, since 75% of direct view's ±30.5°
field would put targets beyond both the stimuli and P4; and **the mask's ±12° in the
stereoscope**. `tools/calibration_design.py` was rerun for each, by 2026-09-05's method, and each
setup has its own reach (`calibration.REACH`): **85% in direct view, 100% in the stereoscope**,
inside the same 0.85 margin. **Both are close calls**: each won under three of the four optics
assumptions and lost the fourth by 0.001°. The records are
`docs/measurements/dev-machine/2026-09-28-calibration-constellation-direct.md` and
`…-stereoscope.md`; the 75% above is the 2026-09-05 record's, on the 31.5-inch stereoscope, and
stands as written.

---
```

- [ ] **Step 7: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_calibration.py tests/test_calibration_design.py tests/test_gaze.py`
Expected: all pass. `test_gaze.py` is in the run because its calibration sessions walk `conditions()`, whose targets moved.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1174 passed**.

- [ ] **Step 8: Commit**

```bash
git add wl_expcontroller/calibration.py tools/calibration_design.py tests/test_calibration.py tests/test_calibration_design.py docs/measurements/dev-machine/2026-09-28-calibration-constellation-direct.md docs/measurements/dev-machine/2026-09-28-calibration-constellation-stereoscope.md docs/superpowers/specs/2026-08-31-S5-eye-tracking-design.md
git commit -m "Place the calibration constellation over each setup's own region, at the reach its record chose"
```

---

### Task 6: The reference tasks, in direct view

**Why:** spec §8: "The reference tasks declare `view="direct"`, and `fixation_detection` and `adaptive_detection` go back to ±16° (checked against direct view), undoing the interim narrowing." `visual_search`'s eccentricity returns to 14°, and the calibration task's range becomes direct view's ±15° region (Plan decision 12). Their load-time tests check them against direct view's field, the rig's with stand-in housings, and one shows what part 2's session start will say when a direct-view task meets the stereoscope.

**Files:**
- Modify: `tasks/fixation_detection.py`, `tasks/adaptive_detection.py`, `tasks/visual_search.py`, `tasks/calibration.py`
- Test: `tests/test_reference_tasks.py` (`GEOMETRY` becomes the rig in direct view; five new tests)

**Interfaces:**
- Consumes: `Trial.view`; `tasks.rig.RIG`; `Housing`; `calibration.constellation`; the `wrong-setup` and `stimulus-off-screen` findings.
- Produces: all four reference tasks with `view="direct"`; `target_position` at −16..16 in both detection tasks; `adaptive_detection`'s `eccentricity` at 2..16; `visual_search`'s `eccentricity` at 5..14; the calibration task's `target_x` and `target_y` at −15..15.

- [ ] **Step 1: Write the failing tests**

In `tests/test_reference_tasks.py`, replace:

```python
from pathlib import Path

import pytest

from wl_expcontroller.check import check
from wl_expcontroller.geometry import Geometry
```

with:

```python
from dataclasses import replace
from pathlib import Path

import pytest

from tasks.rig import RIG
from wl_expcontroller.calibration import constellation
from wl_expcontroller.check import check
from wl_expcontroller.geometry import Housing
```

In `tests/test_reference_tasks.py`, replace:

```python
GEOMETRY = Geometry.stereoscope(
    panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
)
```

with:

```python

#: The rig in direct view (`tasks/rig.py`), where every reference task runs, with
#: **stand-in housings**: the real ones are unmeasured (direct-view spec §9 item 1). One
#: per bottom corner, 4 × 3 cm with a 0.5 cm margin.
GEOMETRY = replace(
    RIG,
    housings=(
        Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
        Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    ),
).direct()
```

Append to `tests/test_reference_tasks.py`:

```python


# --- In direct view (direct-view spec §8) -----------------------------------------

REFERENCE = {
    "fixation_detection": "detection",
    "adaptive_detection": "adaptive_detection",
    "visual_search": "search",
    "calibration": "calibration",
}


def _range(trial: Trial, name: str) -> tuple[float, float]:
    (param,) = [p for p in trial.params if p.name == name]
    return (param.low, param.high)


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_every_reference_task_is_written_for_direct_view(name):
    """The first animal task runs in direct view (PI, 2026-09-28), and these are the
    tasks that stand for it."""
    assert _load(name, REFERENCE[name]).view == "direct"


def test_the_interim_narrowing_is_undone(detection, adaptive, search):
    """The ranges the stereoscope's ±12° mask forced on 2026-09-28, back to what they
    were, now that direct view's field is what they are checked against."""
    assert _range(detection, "target_position") == (-16.0, 16.0)
    assert _range(adaptive, "target_position") == (-16.0, 16.0)
    assert _range(adaptive, "eccentricity") == (2.0, 16.0)
    assert _range(search, "eccentricity") == (5.0, 14.0)


def test_the_calibration_task_passes_every_load_time_check_in_direct_view():
    allocation = _load("allocation", "ALLOCATION")

    assert check(_load("calibration", "calibration"), allocation, geometry=GEOMETRY) == []


def test_the_calibration_task_can_present_direct_views_whole_constellation():
    """Its ranges are the ±15° region the constellation is placed over, so every
    target the block schedules is one the task declares."""
    task = _load("calibration", "calibration")
    (x_low, x_high), (y_low, y_high) = _range(task, "target_x"), _range(task, "target_y")

    assert (x_low, x_high, y_low, y_high) == (-15.0, 15.0, -15.0, 15.0)
    for x, y in constellation(GEOMETRY):
        assert x_low <= x <= x_high and y_low <= y <= y_high


def test_a_direct_view_task_is_refused_in_the_stereoscope_naming_both(detection):
    """What direct view part 2's session start will say if the operator picks the
    stereoscope for this task: the mismatch, and the ±16° its mask cannot show."""
    allocation = _load("allocation", "ALLOCATION")
    codes = {f.code for f in check(detection, allocation, geometry=RIG.stereoscope(1.6))}

    assert codes == {"wrong-setup", "stimulus-off-screen"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_reference_tasks.py`
Expected: **7 failed, 11 passed**. The four `test_every_reference_task_is_written_for_direct_view` cases fail with `assert 'either' == 'direct'`. `test_the_interim_narrowing_is_undone` and `test_the_calibration_task_can_present_direct_views_whole_constellation` fail on the ±12 ranges. `test_a_direct_view_task_is_refused_in_the_stereoscope_naming_both` fails with `assert set() == {...}`, because at ±12 an undeclared task passes the mask. The existing checks already pass against direct view.

- [ ] **Step 3: Implement**

In `tasks/adaptive_detection.py`, replace:

```python
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
```

with:

```python
    # Direct view, as `fixation_detection`: its ±16° is wider than the stereoscope's mask.
    view="direct",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
```

In `tasks/adaptive_detection.py`, replace:

```python
        # An interim bound, about 1° inside the stereoscope's ±13.15° (the PG27UCDM
        # with the screen at 50 cm, S0 §5.2), and at the PI's ±12° mask: check 8
        # refuses a range the rig cannot show. The PI says this task runs in direct
        # view (2026-09-28), which is wider and has no `Geometry` yet; that `Geometry`
        # is what puts ±16 back.
        Param("target_position", unit="deg", low=-12.0, high=12.0),
```

with:

```python
        # ±16° again (direct-view spec §8), checked against direct view's ±30.5° field.
        # ±12 was the interim, at the stereoscope's mask, before direct view had a
        # `Geometry` (2026-09-28).
        Param("target_position", unit="deg", low=-16.0, high=16.0),
```

In `tasks/adaptive_detection.py`, replace:

```python
        Param("eccentricity", unit="deg", low=2.0, high=12.0),
```

with:

```python
        Param("eccentricity", unit="deg", low=2.0, high=16.0),
```

In `tasks/calibration.py`, replace:

```python
`CORRECT` -- a fixation the task would not pay for is not one to calibrate against.
"""

from wl_expcontroller.task import (
```

with:

```python
`CORRECT` -- a fixation the task would not pay for is not one to calibrate against.

**Written for direct view** (`view="direct"`, direct-view spec §8), over its ±15° region.
The stereoscope's constellation, over its ±12° mask, is `calibration.constellation`'s too, and
the task that presents it does not exist yet: it waits for the first stereoscope session,
which direct view part 2's `wlx run --view` is what makes possible.
"""

from wl_expcontroller.task import (
```

In `tasks/calibration.py`, replace:

```python
    windows=[
        Window(
```

with:

```python
    view="direct",
    windows=[
        Window(
```

In `tasks/calibration.py`, replace:

```python
        # Bounded to the field the stereoscope actually shows, not to the
        # constellation of the day: check 8 inspects the parameter *space*, and a
        # range wider than the panel is a task that can be scheduled off-screen.
        # That field is ±13.15° × ±14.77° with the screen at 50 cm (S0 §5.2), stopped
        # at the panel by the PI's ±12° mask (optics drawing §5), so ±12 both ways.
        # It was ±14.5 × ±16.1, 0.85 of the 31.5-inch panel's field (2026-09-28).
        Param("target_x", unit="deg", low=-12.0, high=12.0),
        Param("target_y", unit="deg", low=-12.0, high=12.0),
```

with:

```python
        # Bounded to direct view's calibration region, ±15° × ±15° (direct-view spec
        # §6), not to the constellation of the day: check 8 inspects the parameter
        # *space*, and a range wider than the field is a task that can be scheduled
        # off-screen. Direct view shows ±30.5° × ±18.4°, so the region is the tighter
        # bound. It was ±12 in the interim, at the stereoscope's mask (2026-09-28), and
        # ±14.5 × ±16.1 before that, 0.85 of the 31.5-inch panel's field.
        Param("target_x", unit="deg", low=-15.0, high=15.0),
        Param("target_y", unit="deg", low=-15.0, high=15.0),
```

In `tasks/fixation_detection.py`, replace:

```python
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
```

with:

```python
    # The first animal task runs in direct view (PI, 2026-09-28), and its ±16° is wider
    # than the stereoscope's mask.
    view="direct",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
```

In `tasks/fixation_detection.py`, replace:

```python
        # An interim bound, about 1° inside the stereoscope's ±13.15° (the PG27UCDM
        # with the screen at 50 cm, S0 §5.2), and at the PI's ±12° mask: check 8
        # refuses a range the rig cannot show. The PI says this task runs in direct
        # view (2026-09-28), which is wider and has no `Geometry` yet; that `Geometry`
        # is what puts ±16 back.
        Param("target_position", unit="deg", low=-12.0, high=12.0),
```

with:

```python
        # ±16° again (direct-view spec §8), checked against direct view's ±30.5° field.
        # ±12 was the interim, at the stereoscope's mask, before direct view had a
        # `Geometry` (2026-09-28).
        Param("target_position", unit="deg", low=-16.0, high=16.0),
```

In `tasks/visual_search.py`, replace:

```python
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
```

with:

```python
    # Direct view, with the detection tasks: the lab's programme runs there.
    view="direct",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
```

In `tasks/visual_search.py`, replace:

```python
        # The high end is the same interim bound as the detection tasks': about 1°
        # inside the stereoscope's ±13.15° (screen at 50 cm, S0 §5.2), at the PI's
        # ±12° mask. It was 14 inside the 31.5-inch panel's ±17°. Direct view's
        # `Geometry`, when it exists, is what widens it (2026-09-28).
        Param("eccentricity", unit="deg", low=5.0, high=12.0),
```

with:

```python
        # Back to 14, what it was before the interim bound of 12 at the stereoscope's
        # mask (2026-09-28), and checked against direct view: the ring reaches ±14°
        # vertically as well, inside direct view's ±18.4°.
        Param("eccentricity", unit="deg", low=5.0, high=14.0),
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_reference_tasks.py tests/test_gaze.py`
Expected: all pass: **18 passed** in `test_reference_tasks.py`, and `test_gaze.py`'s calibration sessions still run the calibration task, now declared for direct view.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1182 passed**.

- [ ] **Step 5: Commit**

```bash
git add tasks/fixation_detection.py tasks/adaptive_detection.py tasks/visual_search.py tasks/calibration.py tests/test_reference_tasks.py
git commit -m "Write the reference tasks for direct view, and undo the interim narrowing"
```

---

### Task 7: Prove every new check can fail

**Why:** CLAUDE.md: a test that cannot fail reports safety it does not provide. Every function this plan adds or changes is neutered, one at a time, and the suite must notice. **Read each line, not the exit code**: `caught … N failed <- tests` is a test noticing; a `timed out` or an `N errors in 0.8s` is not, and is a defect in the owning task's tests, to be fixed there and re-run. Nothing is committed in this task.

**Files:** none changed.

- [ ] **Step 1: The gap part 2 closes is grep-able**

Run: `grep -rn "direct view part 2" wl_expcontroller tasks docs/design docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md`
Expected: seven lines, one each in `wl_expcontroller/geometry.py` (`Rig`), `tasks/rig.py`, `tasks/calibration.py`, `docs/design/architecture.md` and S0 §5.5, and two in `wl_expcontroller/check.py` (`_offscreen_stimuli` and `_view_faults`). Each is a place that waits for part 2, saying so.

- [ ] **Step 2: Sweep the package's changed functions**

Each `mutate.py` call runs the suite once per function it neuters, plus a baseline and a restore. `RETURNS` is the module's value in `tools/mutation_gate.py`: `None` for `geometry`, `[]` for `check` and `calibration`. `task.py` gains a field and no function.

Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --all --returns None wl_expcontroller/geometry.py`
Expected: `baseline: 1182 passed`, then one line per function (`stereoscope` and `direct` neuter `Geometry`'s and `Rig`'s together, as the harness neuters every definition of a name), every function `caught`, each with its own count of failed tests and a `<- tests/...` list naming them. These are the counts the fully applied tree printed; a test added since may raise one, and any line that is not `N failed` is a defect in the owning task's tests:

```text
caught    covers                 4 failed
caught    __post_init__          3 failed
caught    stereoscope            83 failed
caught    direct                 15 failed
caught    half_width_cm          97 failed
caught    half_height_cm         92 failed
caught    half_field_h_deg       87 failed
caught    half_field_v_deg       86 failed
caught    _viewport_deg          94 failed
caught    _stopped               87 failed
caught    pixels_per_degree      3 failed
caught    can_show               22 failed
```

and `restored: 1182 passed`.

Run: `for f in check _offscreen_stimuli _view_faults _stereo_content; do WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns '[]' wl_expcontroller/check.py $f; done`
Expected: for each function, `baseline: 1182 passed`, its line, and `restored: 1182 passed`; every function `caught`, each with its own count of failed tests and a `<- tests/...` list naming them. These are the counts the fully applied tree printed; a test added since may raise one, and any line that is not `N failed` is a defect in the owning task's tests:

```text
caught    check                  53 failed
caught    _offscreen_stimuli     10 failed
caught    _view_faults           7 failed
caught    _stereo_content        4 failed
```

Run: `for f in region constellation; do WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns '[]' wl_expcontroller/calibration.py $f; done`
Expected: as for `check`:

```text
caught    region                 52 failed
caught    constellation          41 failed
```

- [ ] **Step 3: Sweep the design tool by hand**

No gate mode reaches `tools/`, so the whole tool is swept; the functions this plan did not change are swept too, and are caught the same way.

Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --all --returns None tools/calibration_design.py`
Expected: `baseline: 1182 passed`, then one line per function, every function `caught`, each with its own count of failed tests and a `<- tests/...` list naming them. These are the counts the fully applied tree printed; a test added since may raise one, and any line that is not `N failed` is a defect in the owning task's tests:

```text
caught    use                    8 failed
caught    _pct                   3 failed
caught    forward                3 failed
caught    scaled                 6 failed
caught    grid                   6 failed
caught    ring                   3 failed
caught    diagonals              6 failed
caught    augmented              6 failed
caught    fit                    3 failed
caught    predict                3 failed
caught    tested_region          5 failed
caught    observe                3 failed
caught    field_error            3 failed
caught    section_conditioning   3 failed
caught    section_honesty        3 failed
caught    section_reach          3 failed
caught    section_count          3 failed
caught    section_dropout        3 failed
caught    section_held_out       3 failed
caught    section_recommended    6 failed
caught    main                   3 failed
```

and `restored: 1182 passed`.

- [ ] **Step 4: The suite, three times**

Run: `for i in 1 2 3; do WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider | tail -1; done`
Expected: **1182 passed**, three times.
