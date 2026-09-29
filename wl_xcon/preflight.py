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

import math
from collections.abc import Collection
from pathlib import Path

from wl_xcon.bounds import Exceeded
from wl_xcon.check import check
from wl_xcon.cli import _load_bounds, _load_subject_settings, _load_trial, _setup_words
from wl_xcon.geometry import Rig
from wl_xcon.link import Preflight, PreflightItem
from wl_xcon.task import Trial
from wl_xcon.welfare import OUT_OF_CAGE, Absent, Simulated

PASS, UNKNOWN, FAIL = "pass", "unknown", "fail"

#: The items' names, as a person acknowledges them.
TASK_CHECKS = "task checks"
STARTING_VALUES = "starting values"
BOUNDED_CONFIG = "bounded config"
SUBJECT_SETTINGS = "subject settings"
OUT_OF_CAGE_MARK = "out of cage"
PUMP_CALIBRATION = "pump calibration"
EYE_TRACKER = "eye tracker"


def _said(refused: SystemExit, path: Path) -> str:
    """What a file's `sys.exit` said. A bare `sys.exit()` says nothing, and a fail with
    an empty sentence is one a person cannot act on."""
    code = refused.code
    if isinstance(code, str) and code.strip():
        return code
    return f"{path.name} ended its own load without saying why (exit {code!r})"


def task(path: Path, allocation, geometry) -> tuple[PreflightItem, Trial | None]:
    """The task's load-time checks in the session's setup: **fail** if it will not load,
    if its checks do not finish, or if any finding blocks. Returns the loaded `Trial`
    too, for `values`. **Nothing a task file does raises out of here**, nor out of
    `values`; and the service contains whatever any item's check raises
    (`Service._preflight`), since it takes a pre-flight on every check and start and a
    raise there would end it."""
    try:
        trial = _load_trial(path)
    except SystemExit as refused:
        return PreflightItem(TASK_CHECKS, FAIL, _said(refused, path)), None
    except Exception as broken:  # noqa: BLE001 -- a task file is code; its fault is this item's
        return (
            PreflightItem(
                TASK_CHECKS, FAIL, f"{path.name} did not load: {type(broken).__name__}: {broken}"
            ),
            None,
        )
    try:
        blocking = [f for f in check(trial, allocation, geometry=geometry) if f.blocking]
    except Exception as broken:  # noqa: BLE001 -- the checks run on code; their fault is this item's
        # Fix round 1 of Task 8: `check` can raise on a task shape it does not expect
        # (XC-156), and a pre-flight that raised took `wlx taskd` down with the animal
        # out. A check that did not finish has not passed, so it fails.
        return (
            PreflightItem(
                TASK_CHECKS,
                FAIL,
                f"{path.name}'s load-time checks did not finish: "
                f"{type(broken).__name__}: {broken}",
            ),
            trial,
        )
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
    it does not declare, a word where it takes a number, a number outside its range, a
    choice it does not offer, or a declaration it cannot be compared with. Starting
    values are the task's own (spec §6.2); they arrive from a console, so they are
    checked as `Session.set` checks a live one, non-finite numbers included. **Nothing a
    task's declarations hold raises out of here.**"""
    if trial is None:
        return PreflightItem(
            STARTING_VALUES, FAIL, "the task did not load, so its values cannot be checked"
        )
    try:
        declared = {param.name: param for param in trial.params}
    except Exception as broken:  # noqa: BLE001 -- a task's declarations are code's output
        return PreflightItem(
            STARTING_VALUES,
            FAIL,
            f"the task's parameter declarations could not be read: "
            f"{type(broken).__name__}: {broken}",
        )
    wrong = []
    for name, value in given.items():
        param = declared.get(name)
        # **Fails closed per value** (the b3a-1 final review, Important 1): `Param` checks
        # none of its fields, so a bound typed as text or `choices` that are not a
        # collection pass `check()` and raise here -- and a raise out of a pre-flight
        # ended `wlx taskd` with the animal out. It fails this value and names it.
        try:
            if param is None:
                wrong.append(f"{name!r} is not a parameter this task declares")
            elif param.choices:
                if value not in param.choices:
                    wrong.append(f"{name!r} may only be one of {param.choices}")
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                wrong.append(f"{name!r} takes a number ({param.unit}), and {value!r} is not one")
            elif not math.isfinite(value):
                wrong.append(f"{name!r} is {value!r}, which is not a real number")
            elif (param.low is not None and value < param.low) or (
                param.high is not None and value > param.high
            ):
                wrong.append(
                    f"{name!r} is declared over [{param.low}, {param.high}] {param.unit} and "
                    f"{value} is outside it"
                )
        except Exception as broken:  # noqa: BLE001 -- see above
            wrong.append(
                f"{name!r} could not be checked against its declaration: "
                f"{type(broken).__name__}: {broken}"
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
        items.append(PreflightItem(BOUNDED_CONFIG, FAIL, _said(refused, bounds_path)))
    except Exception as broken:  # noqa: BLE001 -- a bounds file is code
        items.append(
            PreflightItem(
                BOUNDED_CONFIG,
                FAIL,
                f"{bounds_path} did not load: {type(broken).__name__}: {broken}",
            )
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
        except SystemExit as refused:
            items.append(PreflightItem(SUBJECT_SETTINGS, FAIL, _said(refused, settings_path)))
        except ValueError as refused:
            items.append(PreflightItem(SUBJECT_SETTINGS, FAIL, str(refused)))
        except Exception as broken:  # noqa: BLE001 -- a settings file is code
            items.append(
                PreflightItem(
                    SUBJECT_SETTINGS,
                    FAIL,
                    f"{settings_path} did not load: {type(broken).__name__}: {broken}",
                )
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
    seconds = session.welfare.out_of_cage_seconds(wall)
    if seconds is None:
        return PreflightItem(
            OUT_OF_CAGE_MARK,
            PASS,
            "no out-of-cage interval bounds this deployment (the session is cage-side), "
            "so there is no departure to mark and no limit to reach",
        )
    warning = session.welfare.approaching_limit(wall)
    if warning is not None:
        return PreflightItem(OUT_OF_CAGE_MARK, PASS, warning)
    limit = session.welfare.bounds.ceilings[OUT_OF_CAGE].value
    if seconds >= limit:
        return PreflightItem(
            OUT_OF_CAGE_MARK,
            PASS,
            f"the animal is at its {limit:.0f} s out-of-cage limit ({seconds:.0f} s), "
            f"not past it; a session stops once it is past the limit, which is "
            f"moments away -- bring the animal back",
        )
    return PreflightItem(
        OUT_OF_CAGE_MARK,
        PASS,
        "the departure is marked and the out-of-cage limit is not reached",
    )


def unmeasured(pump: object) -> list[PreflightItem]:
    """The two items spec §6.2 names as **unknown until measured**. Each says what it
    waits for, so the next reader can find it rather than believe it (CLAUDE.md).

    **The pump calibration is acknowledgeable only while the pump is one no valve is
    behind** (S9a §10's dated dependency, V10): `welfare.Simulated` or `welfare.Absent`.
    Any other pump is a driver someone wrote, and a driver with no measured calibration
    is a **fail** here -- the rule this item is an exception to must be revisited when
    a real driver exists, and until it is, the code refuses rather than trusting that
    someone remembers."""
    if isinstance(pump, (Simulated, Absent)):
        pump_item = PreflightItem(
            PUMP_CALIBRATION,
            UNKNOWN,
            "no pump calibration has been measured (V10), so no millilitre is known to "
            "be what the valve gives; this rig's pump is the simulator. Acknowledgeable "
            "only because no real pump driver exists yet -- when one is written, S9a §10 "
            "says this rule must be revisited before it ships",
        )
    else:
        pump_item = PreflightItem(
            PUMP_CALIBRATION,
            FAIL,
            f"this rig's pump is a {type(pump).__name__}, a real pump driver, and no pump "
            f"calibration has been measured (V10): S9a §10 lets the calibration be an "
            f"acknowledged unknown only while no real driver exists, so it blocks until "
            f"a calibration is measured and this rule is revisited",
        )
    return [
        pump_item,
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
    so an item this rule does not know closes the gate rather than opening it.

    **It fails closed on what it is handed**: a bare string as `acknowledged` (whose
    `in` is a substring test, so a sentence containing an item's name would open the
    gate), and a pre-flight with no out-of-cage item (a caller that left the one item
    that bounds the animal out of its list)."""
    if isinstance(acknowledged, (str, bytes)):
        return (
            "pre-flight refused: the acknowledgement must be a collection of item names, "
            "not one string, which would match any item whose name it merely contains"
        )
    named = frozenset(acknowledged)
    if not any(item.name == OUT_OF_CAGE_MARK for item in preflight.items):
        return (
            f"pre-flight failed, so the run does not start: it has no {OUT_OF_CAGE_MARK!r} "
            f"item, and nothing else says the animal's interval is open and inside its limit"
        )
    failed = [item for item in preflight.items if item.result not in (PASS, UNKNOWN)]
    if failed:
        return "pre-flight failed, so the run does not start: " + "; ".join(
            f"{item.name}: {item.said}" for item in failed
        )
    owed = [
        item.name
        for item in preflight.items
        if item.result == UNKNOWN and item.name not in named
    ]
    if owed:
        return (
            f"pre-flight has {len(owed)} unknown item(s) nobody has acknowledged: "
            f"{', '.join(owed)}. Each proceeds only on a named acknowledgement written "
            f"into the record (S9a §10); acknowledge them by name to start"
        )
    return None


def rows(preflight: Preflight, by: str, acknowledged: Collection[str]) -> list[dict]:
    """The pre-flight as `runs.jsonl` records it: every item, and **who acknowledged
    each unknown one** -- `by`, for exactly the unknowns named in `acknowledged` (what
    was sent, not what the result implies). Acknowledging with no one to name is
    refused: a record that says an unknown was accepted by nobody is not a record."""
    if isinstance(acknowledged, (str, bytes)):
        raise ValueError("the acknowledgement must be a collection of item names, not a string")
    named = frozenset(acknowledged)
    signed = [i for i in preflight.items if i.result == UNKNOWN and i.name in named]
    if signed and not (isinstance(by, str) and by.strip()):
        raise ValueError(
            f"{len(signed)} unknown item(s) are acknowledged but the record has no name "
            f"for who acknowledged them"
        )
    return [
        {
            "name": item.name,
            "result": item.result,
            "said": item.said,
            "acknowledged_by": by if item in signed else None,
        }
        for item in preflight.items
    ]
