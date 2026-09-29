"""Pre-flight: what is checked before a run starts (P4d-2b spec §6.2), under S9a §10's
one rule.

**The rule** (PI, 2026-09-19): **fail** blocks; **unknown** proceeds only on an
acknowledgement, by name, written into the record (`runs.jsonl`); **pass** proceeds. The
failure it is shaped against is a gate that cries wolf and gets clicked through, so it
refuses only on evidence of a problem and records acceptance where evidence is merely
absent. `gate` is the rule; the items are what it is asked about: the task's load-time
checks in the session's setup, its starting values, the animal's bounded config and, in
the stereoscope, its settings, the out-of-cage mark and limit, and the two things
nothing measures yet.

**Welfare-critical: `out_of_cage` and `gate`** (`docs/design/architecture.md`). The first
is what refuses a new run once the out-of-cage limit is reached between runs (spec §6.1);
the second is what lets an unknown through. The other items are ordinary: each is an
item a person reads, and a wrong one fails or passes a run that `taskd` still checks
itself -- `Session.run` refuses a blocking finding and a missing mark on its own.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from wl_xcon.bounds import Exceeded
from wl_xcon.check import check
from wl_xcon.cli import _load_bounds, _load_subject_settings, _load_trial, _setup_words
from wl_xcon.geometry import Rig
from wl_xcon.link import Preflight, PreflightItem
from wl_xcon.task import Trial

PASS, UNKNOWN, FAIL = "pass", "unknown", "fail"

#: The items' names, as a person acknowledges them.
TASK_CHECKS = "task checks"
STARTING_VALUES = "starting values"
BOUNDED_CONFIG = "bounded config"
SUBJECT_SETTINGS = "subject settings"
OUT_OF_CAGE_MARK = "out of cage"
PUMP_CALIBRATION = "pump calibration"
EYE_TRACKER = "eye tracker"


def task(path: Path, allocation, geometry) -> tuple[PreflightItem, Trial | None]:
    """The task's load-time checks in the session's setup: **fail** if it will not load
    or any finding blocks. Returns the loaded `Trial` too, for `values`."""
    try:
        trial = _load_trial(path)
    except SystemExit as refused:
        return PreflightItem(TASK_CHECKS, FAIL, str(refused)), None
    except Exception as broken:  # noqa: BLE001 -- a task file is code; its fault is this item's
        return (
            PreflightItem(
                TASK_CHECKS, FAIL, f"{path.name} did not load: {type(broken).__name__}: {broken}"
            ),
            None,
        )
    blocking = [f for f in check(trial, allocation, geometry=geometry) if f.blocking]
    if blocking:
        return (
            PreflightItem(
                TASK_CHECKS, FAIL, "; ".join(f"{f.code}: {f.detail}" for f in blocking)
            ),
            trial,
        )
    return (
        PreflightItem(
            TASK_CHECKS,
            PASS,
            f"{path.name} passes its load-time checks in "
            f"{_setup_words(geometry.view, geometry.half_ipd_cm)}",
        ),
        trial,
    )


def values(trial: Trial | None, given: dict) -> PreflightItem:
    """A run's starting values against the task's own declarations: **fail** for a name
    it does not declare, a word where it takes a number, a number outside its range, or
    a choice it does not offer. Starting values are the task's own (spec §6.2); they
    arrive from a console, so they are checked where `Session.set` checks a live one."""
    if trial is None:
        return PreflightItem(
            STARTING_VALUES, FAIL, "the task did not load, so its values cannot be checked"
        )
    declared = {param.name: param for param in trial.params}
    wrong = []
    for name, value in given.items():
        param = declared.get(name)
        if param is None:
            wrong.append(f"{name!r} is not a parameter this task declares")
        elif param.choices:
            if value not in param.choices:
                wrong.append(f"{name!r} may only be one of {param.choices}")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            wrong.append(f"{name!r} takes a number ({param.unit}), and {value!r} is not one")
        elif (param.low is not None and value < param.low) or (
            param.high is not None and value > param.high
        ):
            wrong.append(
                f"{name!r} is declared over [{param.low}, {param.high}] {param.unit} and "
                f"{value} is outside it"
            )
    if wrong:
        return PreflightItem(STARTING_VALUES, FAIL, "; ".join(wrong))
    return PreflightItem(
        STARTING_VALUES, PASS, f"{len(given)} starting value(s), each declared and in range"
    )


def files(
    bounds_path: Path, subject: str, settings_path: Path | None, rig: Rig
) -> list[PreflightItem]:
    """The animal's files, read again (spec §6.2: "fail if refused"): the bounded config
    loads and names this animal, and in the stereoscope its settings load, name it, and
    give a half-IPD this rig is built for. **The session runs under what it loaded when
    it opened**; a file that no longer loads or names another animal is a sign
    something about this animal's files has gone wrong since, and blocks a new run."""
    items = []
    try:
        found = _load_bounds(bounds_path)
        if found.subject != subject:
            raise SystemExit(
                f"{bounds_path} now holds {found.subject!r}'s bounded config, and this "
                f"session is {subject!r}'s"
            )
        items.append(
            PreflightItem(
                BOUNDED_CONFIG,
                PASS,
                f"{bounds_path} loads and names {subject!r}; the session runs under the "
                f"config it loaded when it opened",
            )
        )
    except SystemExit as refused:
        items.append(PreflightItem(BOUNDED_CONFIG, FAIL, str(refused)))
    except Exception as broken:  # noqa: BLE001 -- a bounds file is code
        items.append(
            PreflightItem(BOUNDED_CONFIG, FAIL, f"{bounds_path} did not load: {type(broken).__name__}: {broken}")
        )
    if settings_path is not None:
        try:
            half = _load_subject_settings(settings_path, subject).half_ipd_cm
            rig.stereoscope(half)
            items.append(
                PreflightItem(
                    SUBJECT_SETTINGS,
                    PASS,
                    f"{settings_path} loads, names {subject!r}, and gives a half-IPD of "
                    f"{half:g} cm this stereoscope is built for",
                )
            )
        except (SystemExit, ValueError) as refused:
            items.append(PreflightItem(SUBJECT_SETTINGS, FAIL, str(refused)))
        except Exception as broken:  # noqa: BLE001 -- a settings file is code
            items.append(
                PreflightItem(SUBJECT_SETTINGS, FAIL, f"{settings_path} did not load: {type(broken).__name__}: {broken}")
            )
    return items


def out_of_cage(session) -> PreflightItem:
    """**Welfare-critical.** The out-of-cage mark and limit, on the session's own clock:
    **fail** when `welfare.preflight` refuses (no departure, the animal recorded home, a
    head-fixed session not fixed) or `welfare.must_stop` says the limit is reached --
    spec §6.1: "reached between runs, it refuses a new run, and the page asks for the
    return". `welfare` decides both; this reads them."""
    wall = session.wall_now()
    try:
        session.welfare.preflight(wall)
    except Exceeded as refused:
        return PreflightItem(OUT_OF_CAGE_MARK, FAIL, str(refused))
    stop = session.welfare.must_stop(wall)
    if stop is not None:
        return PreflightItem(
            OUT_OF_CAGE_MARK,
            FAIL,
            f"{stop}; no run starts past the limit -- end the session (End session) and "
            f"record the animal's return",
        )
    warning = session.welfare.approaching_limit(wall)
    return PreflightItem(
        OUT_OF_CAGE_MARK,
        PASS,
        warning or "the departure is marked and the out-of-cage limit is not reached",
    )


def unmeasured() -> list[PreflightItem]:
    """The two items spec §6.2 names as **unknown until measured**. Each says what it
    waits for, so the next reader can find it rather than believe it (CLAUDE.md)."""
    return [
        PreflightItem(
            PUMP_CALIBRATION,
            UNKNOWN,
            "no pump calibration has been measured (V10), so no millilitre is known to "
            "be what the valve gives; this rig's pump is the simulator. Acknowledgeable "
            "only because no real pump driver exists yet -- when one is written, S9a §10 "
            "says this rule must be revisited before it ships",
        ),
        PreflightItem(
            EYE_TRACKER,
            UNKNOWN,
            "nothing reports the eye tracker's health yet (V3, the eye loop's stall "
            "census, is the measurement it waits on); this rig's gaze is the simulated "
            "animal's",
        ),
    ]


def gate(preflight: Preflight, acknowledged: Collection[str]) -> str | None:
    """**Welfare-critical: S9a §10's one rule.** Why the run may not start, or `None`.

    **Any fail blocks**, acknowledged or not. **Each unknown needs its name in
    `acknowledged`**, which is what a person sent; one not named blocks, and the
    sentence names it. **A result that is neither pass nor unknown counts as a fail**,
    so an item this rule does not know closes the gate rather than opening it."""
    failed = [item for item in preflight.items if item.result not in (PASS, UNKNOWN)]
    if failed:
        return "pre-flight failed, so the run does not start: " + "; ".join(
            f"{item.name}: {item.said}" for item in failed
        )
    owed = [
        item.name
        for item in preflight.items
        if item.result == UNKNOWN and item.name not in acknowledged
    ]
    if owed:
        return (
            f"pre-flight has {len(owed)} unknown item(s) nobody has acknowledged: "
            f"{', '.join(owed)}. Each proceeds only on a named acknowledgement written "
            f"into the record (S9a §10); acknowledge them by name to start"
        )
    return None


def rows(preflight: Preflight, by: str) -> list[dict]:
    """The pre-flight as `runs.jsonl` records it: every item, and **who acknowledged
    each unknown one** -- the person who started the run, since the gate let nothing
    through that they did not name."""
    return [
        {
            "name": item.name,
            "result": item.result,
            "said": item.said,
            "acknowledged_by": by if item.result == UNKNOWN else None,
        }
        for item in preflight.items
    ]
