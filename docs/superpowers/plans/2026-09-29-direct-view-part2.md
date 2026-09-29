# Direct View, Part 2 — The Session's Setup: `wlx run --view`, the Session's Field in Every Load-Time Check, the Record and Telemetry: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Execution: subagent-driven**, the method this project uses (b1, b2a, direct view part 1): a fresh implementer per task and a fresh reviewer before the next one starts, then a whole-branch review.
>
> **Branch from `main` once `check8-fail-closed` has merged** (it closes XC-036 to XC-038, which XC-003 waited on, and this plan's check 8 is that branch's). Name the branch `direct-view-part2`.
>
> **No welfare-critical code changes.** Nothing here touches `bounds.py`, `welfare.py`, the four `cli` welfare functions or `main`'s `session.left_cage(...)` line, or the listed `taskd` functions (`_ends`, `_hold`, `_manual_reward`, `set`, `_schedule`, `_command`'s two parts) or `link._setting` (`docs/design/architecture.md`). `wlx run` gains code **before** the `Session` is built, which is before any of those run. Task 6 Step 4 checks this by diff.

**Goal:** Every session runs in the setup its operator chose, `direct` or `stereoscope`, and every load-time check — `taskd`'s and `wlx check`'s — holds the task to that setup's field, which until now only the tests ever passed; the choice is recorded and shown on both consoles for the whole session.

**Architecture:** `wlx run` gains three flags: `--rig` (the rig's display settings, a Python file defining `RIG`, required), `--view` (required, no default) and `--subject-settings` (a per-animal file defining `SETTINGS`, required with the stereoscope for the animal's half-IPD). It builds the session's `Geometry` from them and runs the load-time check against it **before anything is recorded**. `taskd.SessionSpec` requires that geometry, so `Session.run()`'s own check has one too. The setup goes into `config.json` and into telemetry (schema 9), which `wlx console` and the page show. `wlx check` takes `--rig`, and checks one setup with `--view` or, without it, every setup the task allows.

**Tech Stack:** Python 3.11–3.13; dataclasses; argparse; msgpack (telemetry, unchanged); pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-28-direct-view-design.md`, approved by the PI on 2026-09-28: §3 (which setup a session runs in) and §8's part-2 bullets. The PI's ruling of 2026-09-29 answers what §2 left open ("A subject's `E` comes from its record"): **a per-animal settings file**, named at session start like the bounds file.

## Plan decisions

The spec left these to the plan. Each is taken here, with its reason; the code is in the task named.

1. **The animal's half-IPD comes from a per-animal settings file** (PI, 2026-09-29, asked in the UI; Tasks 1, 2, 4). It is a Python file defining `SETTINGS = SubjectSettings(subject=..., half_ipd_cm=...)`, named by `--subject-settings`, and refused when its subject is not the session's, as a bounded config is. It holds only what the geometry needs today. `tasks/reference_subject.py` is the reference file, for subject `REFERENCE`, with the optics drawing's nominal `E` = 1.6 cm, labeled as not a measurement.
2. **The rig's settings file is named at session start with `--rig`, required, like `--bounds`** (Tasks 2, 4). Nothing else knows which rig a process is on, and a default path would be a field acquired by omission. The same file serves `wlx check`.
3. **The rig says which half-IPDs its stereoscope is built for** (Task 1): `Rig.half_ipd_range_cm`, 1.5–1.9 cm in `tasks/rig.py`, the optics drawing's IPD 30–38 mm table (S0 §7.1.3). `Rig.stereoscope(E)` refuses an `E` outside it: the mirrors and the field there are nobody's drawing.
4. **`wlx check` without an animal checks the stereoscope at both ends of that range** (Task 2), so a task that passes, passes for every animal the rig is built for. With `--subject-settings` it checks that animal's field alone.
5. **`Geometry` carries the half-IPD it was built for** (Task 1): `half_ipd_cm`, set by `Geometry.stereoscope`, `None` in direct view and refused there. One object then answers both "what field" and "for which animal", so the record and telemetry read it rather than a second copy in `SessionSpec`.
6. **`SessionSpec.geometry` is required, with no default** (Task 3), as `bounds` and `deployment` are. The backlog's carry asked that "a missing geometry fail loudly"; a required field fails at construction, before any session exists. `rig_config` and `subject_settings` (the paths, as named) are defaulted strings, as `bounds_config` is.
7. **`wlx run` runs the load-time check against the chosen field before the session opens** (Task 4). `Session.run()` checks too, but only after `wlx run` has opened the session and marked the departure, so a wrong pick would put an animal's departure on record for a session that cannot run. `run()`'s check stays as the backstop for callers that are not `wlx run`.
8. **`--subject-settings` is refused with `--view direct`** (Task 4). Direct view reads nothing from it, and accepting it would suggest it mattered.
9. **Telemetry schema 9 adds `view` and `half_ipd_cm`** (Task 5). The paths stay in the record only: the console needs what the session is running in, and the files it came from are provenance.
10. **The page's "display mode" row, which reads *no source yet*, shows the setup** (Task 5). S9a §3 listed display mode as configuration information; this is its source. "Stimulus calibration" keeps *no source yet*.
11. **One stand-in rig for the tests, `tests/_rig.py`** (Task 1), replacing the four copies of the stand-in housings (closes XC-056). It is also a file `--rig` can load, since it defines `RIG`.

## Global Constraints

- US English in code, docs and comments.
- **No default for the setup**: "`wlx run` takes a required `--view direct|stereoscope`" (spec §3).
- **"A mismatch refuses to start, naming both sides"** (spec §3) — the `wrong-setup` finding's words, from `check._view_faults`.
- **"A field that is not the rig's is never used to pass a task"** (spec §2). The tests' stand-in rig says it is one.
- **Direct view refuses to exist on `tasks/rig.py` until the housings are measured** (spec §9 item 1). A refusal is a sentence, never a traceback.
- No timing claim without a measurement (CLAUDE.md). This plan makes none.
- No welfare-critical code changes (see the note at the top).
- `python3 tools/mutate.py --all <module>` on every changed module before the branch merges, read line by line (CLAUDE.md, "Prove a test can fail").

## Review Focus

1. **An operator picks the setup the task was not written for.** Expected: refused before the session opens, naming both setups, with no session directory created — not after the departure is on record. Test: Task 4, `test_wlx_run_refuses_a_task_written_for_the_other_setup_before_anything_is_recorded`.
2. **The rig's own settings, whose housings are unmeasured, given with `--view direct`.** Expected: the housings sentence, exit status non-zero, no traceback, from both `wlx run` and `wlx check`. Tests: Task 2, `test_wlx_check_refuses_direct_view_on_a_rig_whose_housings_are_unmeasured`; Task 4, `test_wlx_run_refuses_direct_view_on_a_rig_whose_housings_are_unmeasured`.
3. **Another animal's settings file.** Expected: refused, naming both animals. Tests: Task 2, `test_subject_settings_for_another_animal_are_refused`; Task 4, `test_wlx_run_refuses_another_animals_settings`.
4. **A half-IPD on the wire that is not a number** (a string, `NaN`, `inf` from a malformed or future peer). Expected: `wlx console` and the page say it is unreadable and keep rendering. Test: Task 5, `test_a_setup_that_is_not_a_number_on_the_wire_is_said_not_shown`.
5. **A settings or rig file that defines nothing, or the wrong type.** Expected: "must define RIG" / "must define SETTINGS", as a bounded config without `BOUNDS` is. Test: Task 2, `test_a_rig_or_settings_file_that_defines_nothing_is_refused`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `wl_xcon/geometry.py` | modify | `SubjectSettings`; `Rig.half_ipd_range_cm` and its refusal; `Geometry.half_ipd_cm` |
| `tasks/rig.py` | modify | the rig's half-IPD range; its docstring's "no session is checked against this file yet" |
| `tasks/reference_subject.py` | create | the reference animal's settings |
| `tests/_rig.py` | create | the one stand-in rig (XC-056) |
| `wl_xcon/cli.py` | modify | `_load_rig`, `_load_subject_settings`, `_setups`, `_session_geometry`, `_setup_words`; `wlx check` and `wlx run` flags; `render`'s setup line |
| `wl_xcon/taskd.py` | modify | `SessionSpec.geometry`, `rig_config`, `subject_settings`; `run()`'s check and snapshot |
| `wl_xcon/record.py` | modify | `snapshot(..., setup=...)` |
| `wl_xcon/link.py` | modify | schema 9: `view`, `half_ipd_cm` |
| `wl_xcon/web.py` | modify | the page's display-mode row |
| `wl_xcon/check.py` | modify (docstrings only) | the "no caller supplies one yet" sentences |
| tests | modify | `test_geometry`, `test_cli`, `test_taskd`, `test_record`, `test_link`, `test_web`, `test_serve`, `test_gaze`, `test_task_checks`, `test_calibration`, `test_reference_tasks`, `_frames.py` |
| docs | modify | the direct-view spec §2/§3, `architecture.md`, CHECKPOINT, backlog |

---

### Task 1: Per-animal settings, the rig's half-IPD range, and one stand-in rig

**Files:**
- Modify: `wl_xcon/geometry.py` (`Geometry`, `Geometry.stereoscope`, `Rig`; new `SubjectSettings`)
- Modify: `tasks/rig.py`
- Create: `tasks/reference_subject.py`, `tests/_rig.py`
- Modify: `tests/test_geometry.py`, `tests/test_task_checks.py`, `tests/test_calibration.py`, `tests/test_reference_tasks.py` (the four stand-in copies)

**Interfaces:**
- Produces: `geometry.SubjectSettings(subject: str, half_ipd_cm: float)`; `Rig.half_ipd_range_cm: tuple[float, float]`; `Rig.stereoscope(half_ipd_cm)` raising `ValueError` outside the range; `Geometry.half_ipd_cm: float | None`; `tests/_rig.py`'s `RIG`, `DIRECT`, `STEREOSCOPE`, `PATH = "tests/_rig.py"`; `tasks/reference_subject.py`'s `SETTINGS`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_geometry.py`)

```python
from wl_xcon.geometry import SubjectSettings


def test_subject_settings_refuse_a_blank_subject_or_an_impossible_half_ipd():
    """One animal's settings, from the file named at session start (PI, 2026-09-29).
    A blank subject could match nothing it is checked against, and a half-IPD that
    is not a positive number is not a distance."""
    assert SubjectSettings(subject="A", half_ipd_cm=1.6).half_ipd_cm == 1.6
    for subject, half in (("", 1.6), ("A", 0.0), ("A", -1.6), ("A", float("nan"))):
        with pytest.raises(ValueError):
            SubjectSettings(subject=subject, half_ipd_cm=half)


def test_the_stereoscope_refuses_a_half_ipd_it_is_not_built_for():
    """The optics drawing tabulates IPD 30-38 mm (S0 §7.1.3), so the rig is built for
    half-IPDs 1.5-1.9 cm. Outside that, the mirrors and the field are nobody's drawing."""
    assert RIG.half_ipd_range_cm == (1.5, 1.9)
    RIG.stereoscope(half_ipd_cm=1.5)
    RIG.stereoscope(half_ipd_cm=1.9)
    for half in (1.49, 1.91, float("nan")):
        with pytest.raises(ValueError, match="IPD 30-38 mm"):
            RIG.stereoscope(half_ipd_cm=half)


def test_a_geometry_carries_the_half_ipd_it_was_built_for():
    """The record and telemetry read the animal's half-IPD from the field it built,
    not from a second copy. Direct view has none, and refuses one."""
    assert RIG.stereoscope(half_ipd_cm=1.6).half_ipd_cm == 1.6
    assert DIRECT.half_ipd_cm is None
    with pytest.raises(ValueError, match="direct view has no half-IPD"):
        replace(DIRECT, half_ipd_cm=1.6)


def test_the_reference_subject_is_the_reference_bounds_subject():
    """So the reference settings can never quietly become a real animal's."""
    from tasks.reference_bounds import BOUNDS
    from tasks.reference_subject import SETTINGS

    assert SETTINGS.subject == BOUNDS.subject == "REFERENCE"
```

`tests/test_geometry.py` already imports `pytest`, `replace` and `RIG` (check its header; add what is missing). Replace its local stand-in housings (`tests/test_geometry.py:146-147`) with `from _rig import DIRECT` as in Step 5, which this test uses.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_geometry.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'SubjectSettings'`.

- [ ] **Step 3: Implement**

In `wl_xcon/geometry.py`, add the field to `Geometry` after `housings`:

```python
    #: The half-IPD, `E`, a stereoscope field was built for, in cm: one animal's,
    #: from its settings file (PI, 2026-09-29). `None` in direct view, which has none.
    #: Kept on the field so the record and telemetry read it from the object that
    #: decided the field, never from a second copy.
    half_ipd_cm: float | None = None
```

and, at the end of `Geometry.__post_init__`:

```python
        if self.view == "direct" and self.half_ipd_cm is not None:
            raise ValueError(
                "direct view has no half-IPD: both eyes see the one screen at its own "
                "distance, so an animal's eye spacing changes nothing in its field"
            )
```

In `Geometry.stereoscope`, pass it through:

```python
        return cls(
            panel_width_cm=panel_width_cm,
            panel_height_cm=panel_height_cm,
            viewing_distance_cm=screen_distance_cm + panel_width_cm / 4 - half_ipd_cm,
            mask_deg=mask_deg,
            half_ipd_cm=half_ipd_cm,
        )
```

In `Rig`, add the range between `mask_deg` and `housings` (required: it is a fact about this stereoscope, not a preference), and refuse outside it:

```python
    #: The half-IPDs the stereoscope is built for, in cm: the optics drawing's
    #: eye-separation table, IPD 30-38 mm (S0 §7.1.3). An animal outside it is refused
    #: rather than given a field nobody drew.
    half_ipd_range_cm: tuple[float, float]
```

```python
    def stereoscope(self, half_ipd_cm: float) -> Geometry:
        """Through the stereoscope, for one animal's half-IPD, `E`, from its settings
        file (spec §2; PI, 2026-09-29)."""
        low, high = self.half_ipd_range_cm
        if not low <= half_ipd_cm <= high:
            raise ValueError(
                f"a half-IPD of {half_ipd_cm:g} cm is outside the {low:g}-{high:g} cm "
                f"this stereoscope is built for (IPD {20 * low:g}-{20 * high:g} mm, the "
                f"optics drawing's table); its mirrors and its field are unknown there"
            )
        return Geometry.stereoscope(
            self.panel_width_cm,
            self.panel_height_cm,
            screen_distance_cm=self.screen_distance_cm,
            half_ipd_cm=half_ipd_cm,
            mask_deg=self.mask_deg,
        )
```

After `Rig`, add:

```python
@dataclass(frozen=True, slots=True)
class SubjectSettings:
    """One animal's settings, from the file named at session start with
    `--subject-settings` (PI, 2026-09-29), as its bounded config is named with
    `--bounds`.

    Today it holds what the stereoscope's field needs and nothing more: the animal's
    half-IPD, `E`, "measured per animal" (optics drawing §2; backlog XC-082). Direct
    view reads nothing from it. `subject` is checked against the session's own, so one
    animal's eye spacing cannot quietly become another's.
    """

    subject: str
    half_ipd_cm: float

    def __post_init__(self) -> None:
        if not self.subject:
            raise ValueError("subject settings name no subject")
        if not (math.isfinite(self.half_ipd_cm) and self.half_ipd_cm > 0):
            raise ValueError(
                f"half_ipd_cm={self.half_ipd_cm!r} is not a half-IPD: half the distance "
                f"between the eyes' centers, in cm, a positive number"
            )
```

In `tasks/rig.py`, add after `mask_deg=12.0,`:

```python
    # The half-IPDs the stereoscope is built for: IPD 30-38 mm, the optics drawing's
    # eye-separation table (S0 §7.1.3). An animal outside it is refused.
    half_ipd_range_cm=(1.5, 1.9),
```

and replace its docstring's last paragraph ("**No session is checked against this file yet** ...") with:

```
**Sessions are checked against this file** since direct view part 2: `wlx run --rig` and
`wlx check --rig` load it and build the chosen setup's field from it.
```

Create `tasks/reference_subject.py`:

```python
"""The reference animal's settings: a file for `wlx run --subject-settings`, and for
reading.

One per animal, named at session start like its bounded config (PI, 2026-09-29). It
holds the animal's half-IPD, `E`, which the stereoscope's field is built from; direct
view reads nothing from it.

**The number is not a measurement.** 1.6 cm is the optics drawing's nominal `E`, and
the subject is `REFERENCE`, the one `reference_bounds.py` is written for, so a session
refuses this file for any real animal.
"""

from wl_xcon.geometry import SubjectSettings

SETTINGS = SubjectSettings(subject="REFERENCE", half_ipd_cm=1.6)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_geometry.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: One stand-in rig for the tests (closes XC-056)**

Create `tests/_rig.py`:

```python
"""This rig with **stand-in** light-sensor housings, for the tests (backlog XC-056).

The real housings are unmeasured (direct-view spec §9 item 1), so `tasks/rig.py`'s
direct view refuses to exist, deliberately. The tests need one that does: these are
one per bottom corner, 4 × 3 cm with a 0.5 cm margin, and **nobody measured them**.
Everything else is `tasks/rig.py`'s own.

Also a rig settings file: it defines `RIG`, so `wlx run --rig` and `wlx check --rig`
can load it by `PATH`. Never collected, since its name does not start with `test_`.
"""

from dataclasses import replace

from tasks.rig import RIG as _THIS_RIG
from wl_xcon.geometry import Housing

RIG = replace(
    _THIS_RIG,
    housings=(
        Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
        Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    ),
)
DIRECT = RIG.direct()
STEREOSCOPE = RIG.stereoscope(half_ipd_cm=1.6)
#: What `--rig` is given in the tests that run `wlx`.
PATH = "tests/_rig.py"
```

Then replace each of the four copies with an import from it, keeping each file's own names:
- `tests/test_task_checks.py:273-279` (`DIRECT = replace(RIG, housings=(...)).direct()`) becomes `from _rig import DIRECT`; its `GEOMETRY = RIG.stereoscope(half_ipd_cm=1.6)` becomes `from _rig import STEREOSCOPE as GEOMETRY`.
- `tests/test_geometry.py:146-147`, `tests/test_calibration.py:156-157`, `tests/test_reference_tasks.py:40-41`: read the lines around each, and import `RIG` or `DIRECT` from `_rig` in place of the local `replace(...)`.

Remove imports this leaves unused (`Housing`, `replace`) in each file.

Run: `grep -rn 'Housing(' tests/` — Expected: only `tests/_rig.py`.

- [ ] **Step 6: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass (the count before this task plus 4).

- [ ] **Step 7: Commit**

```bash
git add wl_xcon/geometry.py tasks/rig.py tasks/reference_subject.py tests/_rig.py tests/test_geometry.py tests/test_task_checks.py tests/test_calibration.py tests/test_reference_tasks.py
git commit -m "Give each animal a settings file, and the stereoscope the half-IPDs it is built for"
```

The commit body names the PI's ruling of 2026-09-29 and closes XC-056 (remove its backlog line in this commit).

---

### Task 2: `wlx check` against the rig's own fields

**Files:**
- Modify: `wl_xcon/cli.py` (new `_load_named`, `_load_rig`, `_load_subject_settings`, `_setups`, `_setup_words`; `wlx check`'s flags and body)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1's `Rig`, `SubjectSettings`, `Geometry.half_ipd_cm`, `tests/_rig.PATH`.
- Produces: `cli._load_rig(path: Path) -> Rig`; `cli._load_subject_settings(path: Path, subject: str | None) -> SubjectSettings`; `cli._setup_words(view: object, half_ipd_cm: object) -> str` (Task 5 uses it for wire values, hence `object`).

- [ ] **Step 1: Write the failing tests** (in `tests/test_cli.py`, beside the existing `wlx check` tests)

```python
from _rig import PATH as RIG_FILE


def _either_task(tmp_path, reach: float) -> str:
    """`fixation_detection` declared for either setup, its target reaching `reach`°."""
    text = Path("tasks/fixation_detection.py").read_text(encoding="utf-8")
    written_for = 'view="direct"'
    target = 'Param("target_position", unit="deg", low=-16.0, high=16.0)'
    assert text.count(written_for) == 1 and text.count(target) == 1
    text = text.replace(written_for, 'view="either"').replace(
        target, f'Param("target_position", unit="deg", low={-reach}, high={reach})'
    )
    path = tmp_path / "either_detection.py"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_wlx_check_needs_the_rigs_settings(capsys):
    """Check 8 holds a task to the field the rig shows. A check with no field is one
    that did not run, so `--rig` is required rather than defaulted."""
    with pytest.raises(SystemExit) as exited:
        main(["check", GOOD])
    assert exited.value.code == 2
    assert "--rig" in capsys.readouterr().err


def test_wlx_check_holds_an_either_task_to_every_setup(tmp_path, capsys):
    """Without `--view`, every setup the task allows (direct-view spec §8). ±16° fits
    direct view and not the stereoscope's ±12° mask, so an either-task reaching it is
    refused, and one reaching 10° passes both."""
    assert main(["check", _either_task(tmp_path, 16.0), "--rig", RIG_FILE]) == 1
    out = capsys.readouterr().out
    assert "checked against: direct view" in out
    assert "stimulus-off-screen" in out and "stereoscope field" in out

    assert main(["check", _either_task(tmp_path, 10.0), "--rig", RIG_FILE]) == 0


def test_wlx_check_view_checks_one_setup(tmp_path, capsys):
    wide = _either_task(tmp_path, 16.0)

    assert main(["check", wide, "--rig", RIG_FILE, "--view", "direct"]) == 0
    assert main(["check", GOOD, "--rig", RIG_FILE, "--view", "stereoscope"]) == 1
    assert "wrong-setup" in capsys.readouterr().out


def test_wlx_check_on_the_stereoscope_checks_both_ends_of_the_rigs_range(tmp_path, capsys):
    """With no animal named, both ends of the half-IPDs the rig is built for, so a task
    that passes, passes for every animal it could run on."""
    main(["check", _either_task(tmp_path, 10.0), "--rig", RIG_FILE, "--view", "stereoscope"])
    out = capsys.readouterr().out
    assert "checked against: the stereoscope, half-IPD 1.50 cm" in out
    assert "checked against: the stereoscope, half-IPD 1.90 cm" in out

    main(
        [
            "check", _either_task(tmp_path, 10.0), "--rig", RIG_FILE,
            "--view", "stereoscope", "--subject-settings", "tasks/reference_subject.py",
        ]
    )
    out = capsys.readouterr().out
    assert "half-IPD 1.60 cm" in out and "1.50" not in out


def test_wlx_check_refuses_direct_view_on_a_rig_whose_housings_are_unmeasured():
    """Review Focus 2: `tasks/rig.py`'s direct view refuses to exist until the housings
    are measured, and says so as a sentence."""
    with pytest.raises(SystemExit) as exited:
        main(["check", GOOD, "--rig", "tasks/rig.py"])
    assert str(exited.value).startswith("refused: direct view's field excludes")


def test_a_rig_or_settings_file_that_defines_nothing_is_refused(tmp_path):
    """Review Focus 5."""
    empty = tmp_path / "empty.py"
    empty.write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="must define RIG"):
        main(["check", GOOD, "--rig", str(empty)])
    with pytest.raises(SystemExit, match="must define SETTINGS"):
        main(["check", GOOD, "--rig", RIG_FILE, "--subject-settings", str(empty)])


def test_subject_settings_for_another_animal_are_refused(tmp_path):
    """Review Focus 3."""
    from wl_xcon.cli import _load_subject_settings

    with pytest.raises(SystemExit) as exited:
        _load_subject_settings(Path("tasks/reference_subject.py"), "B")
    assert "'REFERENCE'" in str(exited.value) and "'B'" in str(exited.value)
```

Then add `"--rig", RIG_FILE` to every existing `main(["check", ...])` call in `tests/test_cli.py` (five, at the lines `grep -n 'main(\["check"' tests/test_cli.py` prints). Where an existing test asserts exit 0 on `GOOD`, it still does: `fixation_detection` fits direct view on the stand-in rig.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_cli.py -q -p no:cacheprovider -k "check or settings or rig"`
Expected: FAIL — `unrecognized arguments: --rig`, and `ImportError` for `_load_subject_settings`.

- [ ] **Step 3: Implement**

In `wl_xcon/cli.py`, import beside the other `wl_xcon` imports:

```python
from wl_xcon.geometry import VIEWS, Geometry, Rig, SubjectSettings
```

After `_load_bounds`, add:

```python
def _load_named(path: Path, name: str) -> object:
    """Import a settings file and return what it defines as `name`, or `None`."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return vars(module).get(name)


def _load_rig(path: Path) -> Rig:
    """Load a rig's display settings (direct-view spec §2): a Python file defining
    `RIG`, as `tasks/rig.py` does. Refused when it defines none, as a bounded config
    without `BOUNDS` is: a check against no field is a check that did not run."""
    found = _load_named(path, "RIG")
    if not isinstance(found, Rig):
        raise SystemExit(f"{path} must define RIG, a geometry.Rig")
    return found


def _load_subject_settings(path: Path, subject: str | None) -> SubjectSettings:
    """Load one animal's settings (PI, 2026-09-29): a Python file defining `SETTINGS`.
    **Refused for another animal**, as a bounded config is, when `subject` is given:
    one animal's eye spacing is not another's."""
    found = _load_named(path, "SETTINGS")
    if not isinstance(found, SubjectSettings):
        raise SystemExit(f"{path} must define SETTINGS, a geometry.SubjectSettings")
    if subject is not None and found.subject != subject:
        raise SystemExit(
            f"refused: {path} holds {found.subject!r}'s settings and this session is "
            f"for {subject!r}; one animal's eye spacing is not another's"
        )
    return found


def _setup_words(view: object, half_ipd_cm: object) -> str:
    """A setup in words, for `wlx check`, the terminal console and the page. Takes
    wire values, so anything that is not a finite number is said, not formatted
    (Review Focus 4)."""
    if view == "direct":
        return "direct view"
    if view != "stereoscope":
        return f"an unknown setup ({_printable(str(view))})"
    if half_ipd_cm is None:
        return "the stereoscope, half-IPD not given"
    if not isinstance(half_ipd_cm, (int, float)) or not math.isfinite(half_ipd_cm):
        return "the stereoscope, half-IPD unreadable"
    return f"the stereoscope, half-IPD {half_ipd_cm:.2f} cm"


def _setups(
    trial: Trial, rig: Rig, view: str | None, settings: SubjectSettings | None
) -> list[Geometry]:
    """The fields `wlx check` holds a task to (direct-view spec §8): the setup named, or
    every setup the task allows. Through the stereoscope, one animal's field when its
    settings are given, and otherwise the fields at **both ends** of the half-IPDs the
    rig is built for, so a task that passes, passes for every animal it could run on.
    A task whose `view` is unrecognized gets none, and `check` refuses it by name."""
    views = (
        [view]
        if view is not None
        else {
            "direct": ["direct"],
            "stereoscope": ["stereoscope"],
            "either": ["direct", "stereoscope"],
        }.get(trial.view, [])
    )
    halves = [settings.half_ipd_cm] if settings else list(rig.half_ipd_range_cm)
    try:
        return [
            geometry
            for name in views
            for geometry in (
                [rig.direct()]
                if name == "direct"
                else [rig.stereoscope(half) for half in halves]
            )
        ]
    except ValueError as refused:
        raise SystemExit(f"refused: {refused}") from refused
```

Check that `cli.py` already imports `math` (`grep -n '^import math' wl_xcon/cli.py`); add it if not.

Add the flags to the `check` parser:

```python
    checker.add_argument(
        "--rig",
        type=Path,
        required=True,
        metavar="PATH",
        help="the rig's display settings: a Python file defining RIG, as tasks/rig.py "
        "does. Required: check 8 holds a task to the field the rig shows, and a check "
        "with no field is one that did not run",
    )
    checker.add_argument(
        "--view",
        choices=VIEWS,
        default=None,
        help="check against this setup only; omitted, against every setup the task "
        "allows (direct-view spec §8)",
    )
    checker.add_argument(
        "--subject-settings",
        type=Path,
        default=None,
        metavar="PATH",
        help="one animal's settings, a Python file defining SETTINGS: the stereoscope "
        "is then checked at that animal's half-IPD, rather than at both ends of the "
        "rig's range",
    )
```

Replace the body at the end of `main` (from `findings = check(_load_trial(args.task), ...)` to the line before `blocking = ...`) with:

```python
    trial = _load_trial(args.task)
    allocation = _load_allocation(args.allocation)
    rig = _load_rig(args.rig)
    settings = (
        _load_subject_settings(args.subject_settings, None)
        if args.subject_settings is not None
        else None
    )
    geometries = _setups(trial, rig, args.view, settings)
    for geometry in geometries:
        print(f"checked against: {_setup_words(geometry.view, geometry.half_ipd_cm)}")
    # One list across the setups, each finding once: most findings are the task's own
    # and read the same in every setup, while check 8's name the field they failed in.
    findings: list = []
    for geometry in geometries or [None]:
        for finding in check(trial, allocation, geometry=geometry):
            if finding not in findings:
                findings.append(finding)
    for finding in findings:
        marker = "refused " if finding.blocking else "review  "
        print(f"{marker} {finding.code:28} {finding.detail}")
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_cli.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/cli.py tests/test_cli.py
git commit -m "Hold wlx check to the rig's own fields, every setup a task allows"
```

---

### Task 3: The session's field, in `taskd`'s check and in the record

**Files:**
- Modify: `wl_xcon/taskd.py` (`SessionSpec`; `Session.run`'s check and snapshot)
- Modify: `wl_xcon/record.py` (`SessionRecord.snapshot`)
- Test: `tests/test_taskd.py`, `tests/test_record.py`; update `SessionSpec(...)` in `tests/test_gaze.py` (two) and `tests/test_serve.py` (one)

**Interfaces:**
- Consumes: `tests/_rig.DIRECT`, `STEREOSCOPE`; `Geometry.half_ipd_cm`.
- Produces: `SessionSpec.geometry: Geometry` (required, after `deployment`); `SessionSpec.rig_config: str = ""`; `SessionSpec.subject_settings: str = ""`; `SessionRecord.snapshot(layers, resolved, versions, setup: dict)`; `config.json`'s `"setup"` and `versions["rig"]`, `versions["subject_settings"]`.

- [ ] **Step 1: Write the failing tests** (`tests/test_taskd.py`, near `test_the_config_snapshot_names_the_bounded_config_it_ran_under`)

```python
from _rig import DIRECT, STEREOSCOPE


def test_a_session_holds_its_task_to_the_setup_it_runs_in(tmp_path):
    """Check 8 and the setup check ran only in the tests until direct view part 2:
    `run()` called `check()` without a geometry. `fixation_detection` is written for
    direct view, so in the stereoscope it is refused, naming both."""
    session = _session(_spec(tmp_path, geometry=STEREOSCOPE))

    with pytest.raises(SystemExit) as refused:
        session.run()

    assert "wrong-setup" in str(refused.value)
    assert "'direct'" in str(refused.value) and "'stereoscope'" in str(refused.value)


def test_the_config_snapshot_records_the_setup_it_ran_in(tmp_path):
    """Direct-view spec §3: the choice is "written into the session snapshot and the
    session record" -- the field, and which files it was built from."""
    session = _session(
        _spec(
            tmp_path,
            trials=1,
            geometry=DIRECT,
            rig_config="tests/_rig.py",
            subject_settings="",
        )
    )
    session.run()

    config = json.loads((session.directory / "config.json").read_text())
    assert config["setup"]["view"] == "direct"
    assert config["setup"]["half_ipd_cm"] is None
    assert config["setup"]["viewing_distance_cm"] == DIRECT.viewing_distance_cm
    assert len(config["setup"]["housings"]) == 2
    assert config["versions"]["rig"] == "tests/_rig.py"
    assert config["versions"]["subject_settings"] == ""


def test_a_session_cannot_be_specified_without_a_field():
    """The carry from direct view part 1: a missing geometry fails loudly. Required,
    as `bounds` is, so it fails before a session exists."""
    fields = {f.name for f in dataclasses.fields(SessionSpec)}
    required = {
        f.name
        for f in dataclasses.fields(SessionSpec)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    assert "geometry" in fields and "geometry" in required
```

(`tests/test_taskd.py` imports `json` and `pytest` already; add `import dataclasses`. `session.directory / "config.json"` is how the existing snapshot test, `test_the_config_snapshot_names_the_bounded_config_it_ran_under`, reads it.)

In `tests/test_record.py:133`, add `setup={"view": "direct"}` to the existing `record.snapshot(...)` call, and assert `json.loads(...)["setup"] == {"view": "direct"}` beside its other assertions.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_taskd.py tests/test_record.py -q -p no:cacheprovider -k "setup or field or snapshot"`
Expected: FAIL — `SessionSpec` has no attribute `geometry` / `snapshot()` got an unexpected keyword `setup`.

- [ ] **Step 3: Implement**

In `wl_xcon/taskd.py`, import `from wl_xcon.geometry import Geometry`, and add to `SessionSpec` after `deployment: Deployment`:

```python
    #: The field this session's stimuli are held to: the setup the operator chose at
    #: session start, built from the rig's settings (direct-view spec §3). **Required,
    #: with no default**, as `bounds` is: a session with no field is one whose check 8
    #: never ran, which is how every session ran until direct view part 2.
    geometry: Geometry
```

and after `bounds_config: str = ""`:

```python
    #: Where the rig's settings and the animal's were loaded from, as the operator
    #: named them (`--rig`, `--subject-settings`): recorded in the config snapshot beside
    #: the bounded config's. Empty when a caller built the field in code, as the tests do,
    #: and for `subject_settings` in direct view, which reads none.
    rig_config: str = ""
    subject_settings: str = ""
```

In `Session.run`, change `findings = check(trial, self.allocation)` to:

```python
        findings = check(trial, self.allocation, geometry=self.spec.geometry)
```

and extend the snapshot:

```python
        geometry = self.spec.geometry
        record.snapshot(
            layers={"session": dict(self.spec.values)},
            resolved=dict(self.spec.values),
            versions={
                "task": self.spec.task,
                "allocation": self.spec.allocation,
                "bounds": self.spec.bounds_config,
                "rig": self.spec.rig_config,
                "subject_settings": self.spec.subject_settings,
            },
            # Direct-view spec §3: the setup, and the field it gave, as numbers -- the
            # distance degrees were computed on is what a question months later needs.
            setup={
                "view": geometry.view,
                "half_ipd_cm": geometry.half_ipd_cm,
                "viewing_distance_cm": geometry.viewing_distance_cm,
                "half_field_deg": [geometry.half_field_h_deg, geometry.half_field_v_deg],
                "mask_deg": geometry.mask_deg,
                "housings": [dataclasses.asdict(h) for h in geometry.housings],
            },
        )
```

(`taskd.py` imports `dataclasses`' `dataclass` and `field`; add `import dataclasses` if `dataclasses.asdict` is not reachable.)

In `wl_xcon/record.py`, `snapshot` takes and writes it:

```python
    def snapshot(
        self, layers: dict[str, dict], resolved: dict, versions: dict, setup: dict
    ) -> None:
```

```python
        (self.directory / "config.json").write_text(
            json.dumps(
                {"layers": layers, "resolved": resolved, "versions": versions, "setup": setup},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
```

Add to its docstring: "**And the setup it ran in** (direct-view spec §3): required, so a snapshot cannot be written without it."

Give every `SessionSpec(...)` a field: in `tests/test_taskd.py`'s `_spec`, `geometry=DIRECT,` after `deployment=`; in `tests/test_gaze.py` (two) and `tests/test_serve.py:417` (one), `geometry=DIRECT,` with `from _rig import DIRECT`. All three run direct-view reference tasks.

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_taskd.py tests/test_record.py tests/test_gaze.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: every failure is a `wlx run` test, failing because `wlx run` does not pass a `geometry` yet (`TypeError: ... missing 1 required positional argument: 'geometry'`). Task 4 fixes them; do not commit a red suite.

- [ ] **Step 6: Continue straight into Task 4**, and commit the two together at Task 4's Step 8. (A reviewer sees Tasks 3 and 4 as one gate for this reason: `SessionSpec.geometry` has no production caller until `wlx run` passes one.)

---

### Task 4: `wlx run --rig --view --subject-settings`, refused before anything is recorded

**Files:**
- Modify: `wl_xcon/cli.py` (the `run` parser; new `_session_geometry`; the `run` branch before `Session(...)`)
- Test: `tests/test_cli.py`, `tests/test_serve.py` (every `wlx run` argv)

**Interfaces:**
- Consumes: Task 2's `_load_rig`, `_load_subject_settings`; Task 3's `SessionSpec.geometry`, `rig_config`, `subject_settings`.
- Produces: `cli._session_geometry(args) -> Geometry`.

- [ ] **Step 1: Give every existing `wlx run` argv the setup**

In `tests/test_cli.py`, beside `_run_args`:

```python
#: What every `wlx run` here runs in: the stand-in rig's direct view, which the
#: reference tasks are written for.
_SETUP = ("--rig", RIG_FILE, "--view", "direct")
```

Add `*_SETUP,` after the task path in `_run_args` and in every literal `wlx run` argv in `tests/test_cli.py` and `tests/test_serve.py`. Find them with `grep -n '"run",' tests/test_cli.py tests/test_serve.py`; in `tests/test_serve.py`, import `RIG_FILE` from `_rig` as `PATH` and define the same `_SETUP` there. Check none was missed:

Run: `grep -c '"run",' tests/test_cli.py tests/test_serve.py; grep -c '_SETUP,' tests/test_cli.py tests/test_serve.py`
Expected: in each file, the second count equals the first, less any `"run",` that is not a `wlx run` argv (read those lines).

- [ ] **Step 2: Write the failing tests** (`tests/test_cli.py`)

```python
def test_wlx_run_requires_the_setup(tmp_path, capsys):
    """Direct-view spec §3: the operator chooses at session start, and there is no
    default."""
    argv = [a for a in _run_args(tmp_path, "--out-of-cage-at", _hhmm()) if a not in ("--view", "direct")]
    with pytest.raises(SystemExit) as exited:
        main(argv)
    assert exited.value.code == 2
    assert "--view" in capsys.readouterr().err


def test_wlx_run_refuses_a_task_written_for_the_other_setup_before_anything_is_recorded(tmp_path):
    """Review Focus 1. A wrong pick is refused naming both setups, before the session
    opens -- so no departure is marked for a session that cannot run, and no session
    directory exists."""
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
    argv[argv.index("direct")] = "stereoscope"
    argv += ["--subject-settings", "tasks/reference_subject.py"]

    with pytest.raises(SystemExit) as refused:
        main(argv)

    assert "wrong-setup" in str(refused.value)
    assert "'direct'" in str(refused.value) and "'stereoscope'" in str(refused.value)
    assert not (tmp_path / "2027-01-14_01").exists()


def test_wlx_run_in_the_stereoscope_needs_the_animals_settings(tmp_path):
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
    argv[argv.index("direct")] = "stereoscope"

    with pytest.raises(SystemExit, match="needs --subject-settings"):
        main(argv)


def test_wlx_run_refuses_subject_settings_in_direct_view(tmp_path):
    """Direct view reads nothing from them, and accepting them would say it did."""
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm(), "--subject-settings", "tasks/reference_subject.py")

    with pytest.raises(SystemExit, match="direct view reads nothing from it"):
        main(argv)


def test_wlx_run_refuses_another_animals_settings(tmp_path):
    """Review Focus 3, through `wlx run`."""
    other = tmp_path / "b.py"
    other.write_text(
        "from wl_xcon.geometry import SubjectSettings\n"
        "SETTINGS = SubjectSettings(subject='B', half_ipd_cm=1.6)\n",
        encoding="utf-8",
    )
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm(), "--subject-settings", str(other))
    argv[argv.index("direct")] = "stereoscope"

    with pytest.raises(SystemExit, match="holds 'B'"):
        main(argv)


def test_wlx_run_refuses_direct_view_on_a_rig_whose_housings_are_unmeasured(tmp_path):
    """Review Focus 2, through `wlx run`."""
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
    argv[argv.index(RIG_FILE)] = "tasks/rig.py"

    with pytest.raises(SystemExit) as refused:
        main(argv)
    assert str(refused.value).startswith("refused: direct view's field excludes")
    assert not (tmp_path / "2027-01-14_01").exists()


def test_wlx_run_runs_an_either_task_in_the_stereoscope_and_records_it(tmp_path):
    """The whole path in the other setup: an either-task that fits the mask, the
    reference animal's half-IPD, and the record saying so."""
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm(), "--subject-settings", "tasks/reference_subject.py")
    argv[argv.index("tasks/fixation_detection.py")] = _either_task(tmp_path, 10.0)
    argv[argv.index("direct")] = "stereoscope"

    assert _main_uninterrupted(argv) == 0

    config = json.loads((tmp_path / "2027-01-14_01" / "xcon" / "config.json").read_text())
    assert config["setup"]["view"] == "stereoscope"
    assert config["setup"]["half_ipd_cm"] == 1.6
    assert config["versions"]["rig"] == RIG_FILE
    assert config["versions"]["subject_settings"] == "tasks/reference_subject.py"
```

(`_TASK_SETS` sets `target_position=10.0`, which the ±10° either-task allows. The path is the one `tests/test_cli.py` already reads `config.json` at, `<root>/<session>/xcon/config.json`.)

- [ ] **Step 3: Run them to verify they fail**

Run: `python3 -m pytest tests/test_cli.py -q -p no:cacheprovider -k "wlx_run"`
Expected: FAIL — `unrecognized arguments: --rig`.

- [ ] **Step 4: Implement**

Add to the `run` parser, after `--bounds`:

```python
    runner.add_argument(
        "--rig",
        type=Path,
        required=True,
        metavar="PATH",
        help="the rig's display settings: a Python file defining RIG, as tasks/rig.py "
        "does. Required, as --bounds is: the session's field is built from it",
    )
    runner.add_argument(
        "--view",
        choices=VIEWS,
        required=True,
        help="which setup this session runs in. **Required, with no default** "
        "(direct-view spec §3): nothing senses which is in place, so the operator "
        "says, the choice is shown all session, and a task written for the other "
        "setup is refused before anything is recorded",
    )
    runner.add_argument(
        "--subject-settings",
        type=Path,
        default=None,
        metavar="PATH",
        help="this animal's settings: a Python file defining SETTINGS, for --subject "
        "(PI, 2026-09-29). Required with --view stereoscope, for the animal's "
        "half-IPD; refused with --view direct, which reads nothing from it",
    )
```

After `_setups`, add:

```python
def _session_geometry(args) -> Geometry:
    """The field a `wlx run` session is held to, from `--rig`, `--view` and
    `--subject-settings` (direct-view spec §3; PI, 2026-09-29). Every refusal is a
    sentence: an unmeasured rig, an animal the stereoscope is not built for, another
    animal's file, or a file where none belongs."""
    rig = _load_rig(args.rig)
    if args.view == "direct":
        if args.subject_settings is not None:
            raise SystemExit(
                "refused: --subject-settings holds the stereoscope's half-IPD, and "
                "direct view reads nothing from it; leave it off, or pass --view "
                "stereoscope"
            )
        build = rig.direct
    else:
        if args.subject_settings is None:
            raise SystemExit(
                "refused: --view stereoscope needs --subject-settings, the file "
                "holding this animal's half-IPD (PI, 2026-09-29)"
            )
        half = _load_subject_settings(args.subject_settings, args.subject).half_ipd_cm

        def build() -> Geometry:
            return rig.stereoscope(half)

    try:
        return build()
    except ValueError as refused:
        raise SystemExit(f"refused: {refused}") from refused
```

In `main`'s `run` branch, right after `deployment = Deployment(...)`:

```python
        geometry = _session_geometry(args)
        # **Refused before anything is recorded** (direct-view spec §3, plan decision
        # 7): a task written for the other setup, or one the chosen field cannot show,
        # stops here -- before the session opens and before the departure is asked
        # about. `Session.run()` checks again, as the backstop for a caller that is
        # not this command.
        refusals = [
            finding
            for finding in check(
                _load_trial(args.task),
                _load_allocation(args.allocation),
                geometry=geometry,
            )
            if finding.blocking
        ]
        if refusals:
            raise SystemExit(
                "task refused, session not started, nothing recorded:\n"
                + "\n".join(f"  {f.code}: {f.detail}" for f in refusals)
            )
```

and in `SessionSpec(...)`, after `deployment=deployment,`:

```python
                        geometry=geometry,
                        rig_config=str(args.rig),
                        subject_settings=(
                            "" if args.subject_settings is None else str(args.subject_settings)
                        ),
```

- [ ] **Step 5: Run them to verify they pass**

Run: `python3 -m pytest tests/test_cli.py tests/test_serve.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 7: Check the welfare-critical lines did not move**

Run: `git diff main -- wl_xcon/cli.py | grep -n 'left_cage\|_settle_departure\|_settle_return\|_wall_clock_time\|_clock_or_now'`
Expected: no `+` or `-` line among them.

- [ ] **Step 8: Commit (Tasks 3 and 4)**

```bash
git add wl_xcon/taskd.py wl_xcon/record.py wl_xcon/cli.py tests/test_taskd.py tests/test_record.py tests/test_gaze.py tests/test_serve.py tests/test_cli.py
git commit -m "Run each session in the setup its operator chose, and check its task there first"
```

---

### Task 5: The setup on both consoles, schema 9

**Files:**
- Modify: `wl_xcon/link.py` (`SCHEMA`, its history, `Telemetry`, `of`, `encode`, `_telemetry_from`)
- Modify: `wl_xcon/cli.py` (`render`), `wl_xcon/web.py` (`_setup`)
- Test: `tests/test_link.py`, `tests/test_cli.py`, `tests/test_web.py`, `tests/_frames.py`, and `tests/test_cli.py`'s `_telemetry`

**Interfaces:**
- Consumes: `session.spec.geometry` (Task 3); `cli._setup_words` (Task 2).
- Produces: `Telemetry.view: str`, `Telemetry.half_ipd_cm: float | None`; `SCHEMA = 9`.

- [ ] **Step 1: Write the failing tests**

`tests/test_link.py`, beside the existing round-trip tests:

```python
def test_a_frame_carries_the_setup_the_session_runs_in():
    """Direct-view spec §3: the choice is published for the whole session (schema 9)."""
    stereo = replace(frame(), view="stereoscope", half_ipd_cm=1.6)

    assert decode(encode(stereo)).view == "stereoscope"
    assert decode(encode(stereo)).half_ipd_cm == 1.6
    assert decode(encode(frame())).half_ipd_cm is None
    assert SCHEMA == 9
```

(Use this file's existing way of building a whole frame; if it has none, import `frame` from `_frames`.) In `test_link.py`'s `SimpleNamespace` session stand-in used by `Telemetry.of`, add `geometry=DIRECT` to its `spec` (from `_rig`), and assert the built frame's `view == "direct"` there.

`tests/test_cli.py`, beside the `render` tests:

```python
def test_the_terminal_console_shows_the_setup_all_session():
    assert "setup: direct view" in render(_telemetry(view="direct", half_ipd_cm=None))
    assert "setup: the stereoscope, half-IPD 1.60 cm" in render(
        _telemetry(view="stereoscope", half_ipd_cm=1.6)
    )


def test_a_setup_that_is_not_a_number_on_the_wire_is_said_not_shown():
    """Review Focus 4: a half-IPD a peer sent as a string, NaN or infinity is said to
    be unreadable, and the frame still renders."""
    for bad in ("1.6", float("nan"), float("inf")):
        shown = render(_telemetry(view="stereoscope", half_ipd_cm=bad))
        assert "half-IPD unreadable" in shown
```

`tests/test_web.py`, replacing `test_setup_names_the_configuration_and_what_has_no_source`'s count:

```python
    assert setup.count("no source yet") == 1
    assert "<dt>display mode</dt><dd>direct view</dd>" in setup
```

and add:

```python
def test_the_page_shows_the_stereoscopes_half_ipd():
    setup = fragments(frame(view="stereoscope", half_ipd_cm=1.6), view())["setup"]

    assert "the stereoscope, half-IPD 1.60 cm" in setup
```

In `tests/_frames.py`'s `frame()`, add `view="direct", half_ipd_cm=None,` after `controls_dropped=0,`, and say in its docstring that `half_ipd_cm`'s `None` is direct view's, like `paused_at`'s. Do the same in `tests/test_cli.py`'s `_telemetry`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_link.py tests/test_cli.py tests/test_web.py -q -p no:cacheprovider`
Expected: FAIL — `Telemetry.__init__() got an unexpected keyword argument 'view'`.

- [ ] **Step 3: Implement**

In `wl_xcon/link.py`, append to the schema history and bump it:

```python
#: 9 (2026-09-29, direct view part 2): `view`, the setup the session runs in, and
#: `half_ipd_cm`, the animal's half-IPD its stereoscope field was built for (`None` in
#: direct view). Nothing changed meaning. A schema-8 reader refuses a schema-9 frame,
#: and a schema-9 reader a schema-8 one, by name (`SchemaMismatch`).
SCHEMA = 9
```

Add to `Telemetry`, after `controls_dropped`:

```python
    #: `session.spec.geometry.view`: "direct" or "stereoscope" (direct-view spec §3).
    #: Shown all session, because nothing senses which is in place and the operator's
    #: pick is the residual risk.
    view: str
    #: `session.spec.geometry.half_ipd_cm`: the animal's half-IPD, in cm, that the
    #: stereoscope's field was built for, from its settings file (PI, 2026-09-29).
    #: `None` in direct view, which has none.
    half_ipd_cm: float | None
```

In `Telemetry.of`, after `controls_dropped=session.controls_dropped,`:

```python
            view=session.spec.geometry.view,
            half_ipd_cm=session.spec.geometry.half_ipd_cm,
```

In `encode`'s dict, after `"controls_dropped"`:

```python
        "view": telemetry.view,
        "half_ipd_cm": telemetry.half_ipd_cm,
```

In `_telemetry_from`, after `controls_dropped=data["controls_dropped"],`:

```python
        view=data["view"],
        half_ipd_cm=data["half_ipd_cm"],
```

In `wl_xcon/cli.py`'s `render`, after the `deployment:` line:

```python
    # Direct-view spec §3: the setup, shown for the whole session. Words from the
    # frame's own fields, never inferred.
    lines.append(f"  setup: {_setup_words(frame.view, frame.half_ipd_cm)}")
```

In `wl_xcon/web.py`, import `_setup_words` beside `_clock` (`from wl_xcon.cli import _clock, _setup_words`), and in `_setup` replace the display-mode row:

```python
        ("display mode", _e(_setup_words(frame.view, frame.half_ipd_cm))),
```

and its docstring's first sentence with: "S9a §3's configuration information. Display mode is the setup the session runs in (direct-view spec §3); stimulus calibration has no source yet and says so."

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_link.py tests/test_cli.py tests/test_web.py tests/test_serve.py tests/test_health.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/link.py wl_xcon/cli.py wl_xcon/web.py tests/test_link.py tests/test_cli.py tests/test_web.py tests/_frames.py
git commit -m "Show the session's setup on both consoles, in telemetry schema 9"
```

---

### Task 6: Say so where it was not true, prove the tests can fail, and close the items

**Files:**
- Modify: `wl_xcon/check.py` (docstrings of `_offscreen_stimuli`, `_view_faults`), `wl_xcon/geometry.py` (`Rig`'s docstring)
- Modify: `docs/superpowers/specs/2026-09-28-direct-view-design.md` (§2, §3), `docs/design/architecture.md`, `docs/CHECKPOINT.md`, `docs/backlog.md`

- [ ] **Step 1: The "not yet" sentences** (CLAUDE.md: a "not yet" comment is a dated claim)

Run: `grep -rn "No caller\|no caller\|until direct view part 2\|direct view part 2 passes\|That caller is\|Nothing outside the tests builds" wl_xcon tasks`
Rewrite each hit to say what is true now: `taskd` and `wlx check` pass the session's field (`wlx run --rig --view`), and `check()` without a geometry is only for callers with no rig (`wlx review`, tests).

- [ ] **Step 2: The spec and the architecture**

In the direct-view spec §2, after "A subject's `E` comes from its record.", add: "**From a per-animal settings file** (PI, 2026-09-29), named at session start with `--subject-settings` as the bounded config is with `--bounds`, and refused for another animal; `Rig.half_ipd_range_cm` refuses an `E` the stereoscope is not built for." In §3, after the `--view` sentence, add: "`--rig` names the rig's settings, and a task that does not pass the load-time checks in the chosen setup is refused before the session opens (plan `2026-09-29-direct-view-part2.md`, decision 7)."

In `docs/design/architecture.md`, find where the load-time checks or the stereo viewports are described (`grep -n "load-time\|check 8\|Stereo, as viewports\|direct view" docs/design/architecture.md`) and add one sentence: the checks now run against the session's own field, from `--rig` and `--view`.

- [ ] **Step 3: Prove the tests can fail**

For each changed module run the harness in a `git archive` copy of the branch tip, with `wl-preproc` linked inside it and `PYTHONPATH` set to the copy (the working tree must not move while a sweep runs):

```bash
python3 tools/mutate.py --all wl_xcon/cli.py
python3 tools/mutate.py --all wl_xcon/geometry.py
python3 tools/mutate.py --all wl_xcon/taskd.py
python3 tools/mutation_gate.py --dry-run   # confirm each module's --returns flag first
python3 tools/mutate.py --all --returns None wl_xcon/record.py
python3 tools/mutate.py --all wl_xcon/link.py
python3 tools/mutate.py --all wl_xcon/web.py
```

Use each module's `--returns` from `tools/mutation_gate.py`'s `RETURNS`, not the ones above, where they differ. Read every line: each new or changed function is `caught` with `N failed`, never only `N errors`, and every baseline and restore is the suite's own count. A survivor is a missing test: write it, then re-run that function.

- [ ] **Step 4: The welfare-critical surface is unchanged**

Run: `git diff main -- wl_xcon/welfare.py wl_xcon/bounds.py | wc -l` — Expected: `0`.
Run: `git diff main -- wl_xcon/taskd.py | grep -n '_ends\|_hold\|_manual_reward\|def set\|_schedule\|_command'` — Expected: no hunk inside those functions.

- [ ] **Step 5: CHECKPOINT and the backlog**

CHECKPOINT: a new "What moved" entry, and the Status row of load-time checks gains `needs-stereoscope`, `wrong-setup`, `unknown-view` (closes XC-051). Backlog: remove XC-003 and XC-051 (XC-056 went in Task 1). If the stereoscope's calibration task (XC-005) was waiting on XC-003, change its `waits on:` to `nothing`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Say where the session's field now comes from, and close direct view part 2"
```

The body names the mutation results read in Step 3 and closes XC-003 and XC-051.
