"""What `GET /health` tells wl-works about this box (P4d-2b spec §3).

The body is `wl_preproc.contracts.protocol.HealthResponse`, schema version 1 --
`verdict`, `readings`, `actions` -- built here as plain data and contract-tested
against their model with `WLX_REQUIRE_PREPROC=1` (`tests/test_health.py`). **Pure**: a
frame and two numbers in, a dict out. `wlx serve` supplies how old the frame is.

**The rules are wl-preproc's, read from their source on 2026-09-26**
(`wl_preproc/contracts/protocol.py`, `docs/ops/lab-host-protocol.md`):

- A reading is plain text. `<`, `>` and `&` in a value are spelled `(lt)`, `(gt)` and
  `(amp)`, as their `plain_text` does; every label here is a constant with none.
- `unknown` is never emitted. It is wl-works' word for a host that went silent, and a
  host answering the request cannot be silent.
- `actions` is always empty: no welfare action goes through wl-works (ADR-0008).
- **Exactly one reading is featured, the most urgent** (PI, 2026-09-26, spec §3).
  wl-works' Plan 10 §4 says of more than one "the first wins", and wl-preproc emits
  exactly one for that reason. `_featured` holds the ruled order.

**The behavioral counts are grouped here and nowhere else** (`families`), so the
browser console's Working? pane and this body show them identically (spec §3): total
trials, then every outcome that occurred with its count, by `task.Family`, and no
rollup.
"""

from __future__ import annotations

from wl_expcontroller.cli import _clock
from wl_expcontroller.link import Telemetry
from wl_expcontroller.task import Family, Outcome

#: `wl_preproc.contracts.protocol.SCHEMA_VERSION`, read from their source 2026-09-26.
#: `tests/test_health.py` compares the two, so a bump on their side fails here first.
HEALTH_SCHEMA = 1

#: wl-preproc's substitutes, one per character and never one shared: `A&B` and `A<B`
#: must not render alike (their `_MARKUP_SUBSTITUTES`).
_MARKUP = (("<", "(lt)"), (">", "(gt)"), ("&", "(amp)"))


def plain_text(text: str) -> str:
    """`text` with `<`, `>` and `&` spelled out, as wl-preproc's `plain_text` does.

    Their `Reading` refuses markup in a value outright. A session id or a stop reason
    is producer-supplied text worth reporting, so it is spelled out rather than
    dropped. A second copy of their function, pinned to theirs by a contract test:
    this package cannot import wl-preproc at run time (`tests/conftest.py`).
    """
    for char, substitute in _MARKUP:
        text = text.replace(char, substitute)
    return text


def ago(seconds: float) -> str:
    """An age as a person reads it: seconds under a minute and a half, minutes under
    an hour and a half, then a clock. Formatting only; a negative age is `0 s`."""
    whole = max(0, int(seconds))
    if whole < 90:
        return f"{whole} s"
    if whole < 5400:
        return f"{whole // 60} min"
    return _clock(whole)


def family_key(wire: str) -> str:
    """The family an outcome's wire string belongs to, as a short key -- `hang` for a
    trial with no outcome, and `other` for a string this build's `Outcome` does not
    know, which a newer `taskd` can send. Never raises: an unknown outcome is shown,
    never dropped."""
    if wire == "hang":
        return "hang"
    try:
        return Outcome(wire).family.name.lower()
    except ValueError:
        return "other"


def families(outcomes: dict) -> list[tuple[str, str, list[tuple[str, object]]]]:
    """Every outcome that occurred, grouped by `Family`, with its count and **no
    rollup** (PI, 2026-09-26): `(key, label, [(outcome, count), ...])` in `Family`
    order, each family's outcomes in `Outcome` order, then any this build does not
    know, sorted, under `other`."""
    grouped = []
    for family in Family:
        rows = [
            (outcome.value, outcomes[outcome.value])
            for outcome in Outcome
            if outcome.family is family and outcome.value in outcomes
        ]
        if rows:
            grouped.append((family.name.lower(), family.value.capitalize(), rows))
    known = {outcome.value for outcome in Outcome}
    other = [
        (name, outcomes[name]) for name in sorted(outcomes, key=str) if name not in known
    ]
    if other:
        grouped.append(("other", "Other", other))
    return grouped


def expects_frames(frame: Telemetry | None) -> bool:
    """Whether more frames are due: the loop is running, or a rig session is still
    publishing its out-of-cage clock until the return (P4d-2a). Only then is silence
    a stale stream -- an ended session's last frame is its last. The page's stale
    timer runs on the same answer."""
    return frame is not None and (
        frame.stop_kind is None or frame.phase == "awaiting_return"
    )


def _stale(frame: Telemetry | None, frame_age_s: float | None, stale_after_s: float) -> bool:
    return (
        expects_frames(frame) and frame_age_s is not None and frame_age_s >= stale_after_s
    )


def verdict(
    frame: Telemetry | None, *, frame_age_s: float | None, stale_after_s: float
) -> str:
    """Spec §3's table, first match wins:

    - no session attached yet: `ok`
    - ended by a fault: `down`, whatever else holds
    - returned to the cage (`phase == "closed"`): `ok`, however it ended
    - the duration warning active, or no frame for `stale_after_s` while more were
      due: `degraded`
    - ended by the out-of-cage limit and not yet back: `degraded`
    - otherwise -- running normally, or ended any other way: `ok`
    """
    if frame is None:
        return "ok"
    if frame.stop_kind == "fault":
        return "down"
    if frame.phase == "closed":
        return "ok"
    if frame.duration_warning or _stale(frame, frame_age_s, stale_after_s):
        return "degraded"
    if frame.stop_kind == "limit":
        return "degraded"
    return "ok"


def _state_text(frame: Telemetry) -> str:
    if frame.stop_kind is None:
        return f"running · trial {frame.trial_index} · block {frame.block}"
    text = f"ended ({frame.stop_kind}): {frame.stopped_because}"
    if frame.phase == "awaiting_return":
        return f"{text} · awaiting the return to the cage"
    if frame.phase == "closed":
        return f"{text} · returned to the cage"
    return text


def _cage_text(frame: Telemetry) -> str:
    if frame.out_of_cage_seconds is None:
        return "cage-side, no limit"
    if frame.out_of_cage_limit_s is None:
        return _clock(frame.out_of_cage_seconds)
    return f"{_clock(frame.out_of_cage_seconds)} of {_clock(frame.out_of_cage_limit_s)}"


def _supplement_text(frame: Telemetry) -> str:
    if frame.shortfall_ml is None:
        return "unknown: the day's prior total was not supplied"
    return f"{frame.shortfall_ml:.2f} mL"


def _age_text(frame_age_s: float | None) -> str:
    return "none received" if frame_age_s is None else f"{ago(frame_age_s)} ago"


def _featured(frame: Telemetry | None, verdict_: str, stale: bool) -> str:
    """The one reading wl-works' home page shows: the most urgent (PI, 2026-09-26,
    spec §3) -- the warning, else the state of a session that faulted or ended on the
    limit with the animal not back, else a stale stream's age, else the out-of-cage
    time a rig session is bounded by, else the state."""
    if frame is None:
        return "state"
    if frame.duration_warning:
        return "duration_warning"
    if verdict_ == "down" or (frame.stop_kind == "limit" and frame.phase != "closed"):
        return "state"
    if stale:
        return "last_frame"
    if frame.out_of_cage_seconds is not None:
        return "out_of_cage"
    return "state"


def readings(
    frame: Telemetry | None, *, frame_age_s: float | None, stale_after_s: float
) -> list[dict]:
    """The readings, in spec §3's order: session, state, time out of cage, the
    duration warning when active, fluid this session, supplement owed, the
    behavioral counts, and the last frame's age. Every value through `plain_text`."""
    if frame is None:
        rows = [
            ("session", "Session", "none attached"),
            ("state", "State", "waiting for the session's telemetry"),
            ("last_frame", "Last frame", _age_text(frame_age_s)),
        ]
    else:
        rows = [
            ("session", "Session", f"{frame.session_id} · {frame.subject} · {frame.task}"),
            ("state", "State", _state_text(frame)),
            ("out_of_cage", "Time out of cage", _cage_text(frame)),
        ]
        if frame.duration_warning:
            rows.append(("duration_warning", "Warning", frame.duration_warning))
        rows += [
            ("fluid_session", "Fluid this session", f"{frame.fluid_session_ml:.2f} mL"),
            ("supplement", "Supplement owed", _supplement_text(frame)),
            ("trials", "Trials", str(frame.trial_index)),
        ]
        for key, label, counted in families(frame.outcomes):
            rows.append(
                (
                    f"outcomes_{key}",
                    label,
                    " · ".join(f"{name} {count}" for name, count in counted),
                )
            )
        rows += [
            ("hangs", "Hangs", str(frame.hangs)),
            ("last_frame", "Last frame", _age_text(frame_age_s)),
        ]
    featured = _featured(
        frame,
        verdict(frame, frame_age_s=frame_age_s, stale_after_s=stale_after_s),
        _stale(frame, frame_age_s, stale_after_s),
    )
    return [
        {"key": key, "label": label, "value": plain_text(str(value)), "featured": key == featured}
        for key, label, value in rows
    ]


def response(
    frame: Telemetry | None, *, frame_age_s: float | None, stale_after_s: float
) -> dict:
    """The whole `/health` body: `HealthResponse`'s three fields, `actions` always
    empty."""
    return {
        "verdict": verdict(frame, frame_age_s=frame_age_s, stale_after_s=stale_after_s),
        "readings": readings(frame, frame_age_s=frame_age_s, stale_after_s=stale_after_s),
        "actions": [],
    }
