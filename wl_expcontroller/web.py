"""The browser console's panes and page: a `Telemetry` frame in, HTML out.

P4d-2b slice b1 (`docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md`
§1, §4.2). **Pure** -- no socket, no clock, no thread. `wlx serve` reads the clock and
the stream and hands them in as a `View`, so every pane is tested the way `cli.render`
is: "fluid session and the supplement are never dropped" is an assertion on this
module's output (spec §4.4), not a hope about a browser.

**Every telemetry string reaches the page through `_e`** (`html.escape`, quotes
included), in elements and attributes alike. A task path, a condition, a refusal's
reason and an actor's typed name are text a person or a peer chose.

**Every number is read from the frame**, as `cli.render`'s are, with the arithmetic a
display needs and no more: the strip's correct count, which adds `correct_reject` to
`correct` -- the one rollup, ruled for the strip alone (PI, 2026-09-26, spec §3) -- and
its percentage, two bar widths, and the time since the last reward -- the frame's own
instant less the reward's, both on the session's anchored clock, plus how long `wlx
serve` has held the frame on its steady clock (`View.frame_age_s`; ledger Ruling 1,
2026-09-27). No host clock is read against a session instant. Trials per minute is
derived by `wlx serve`, never here, and is labeled as derived.

**Unknown is a word, never 0**: a day nobody measured, a reward not given yet, a rate
not derived yet, a configuration nobody named, and the three *Wrong?* measurements
nothing takes yet.

**The strip carries four cells** (PI, 2026-09-26, spec §4.0): fluid today against its
floor, time out of the cage against its limit, correct over trials, and the time since
the last reward. Fluid session and the supplement moved to Runtime and End of session,
where **both are on the page in every state**: the zero-reward ruling (S9a §9) rests on
their being visible.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from wl_expcontroller import health as _health
from wl_expcontroller.cli import _clock
from wl_expcontroller.link import RECENT_OUTCOMES, Telemetry
from wl_expcontroller.task import Family, Outcome


@dataclass(frozen=True, slots=True)
class View:
    """What `wlx serve` adds to a frame: facts about the stream and the viewer, never
    about the session."""

    #: Seconds since `wlx serve` received the latest frame, on its own steady clock
    #: (`serve.Hub`); `None` before any. **Also what the time since the last reward is
    #: aged by** (ledger Ruling 1, 2026-09-27): the frame's `wall_at` less its
    #: `last_reward_at`, both on the session's anchored clock, plus this. There is no
    #: wall clock here on purpose: `wlx serve`'s host clock parts from the session's
    #: anchor by any step it has taken since the session began, and a step back once
    #: read the age short -- clamped at `0 s`, the direction that hides a working,
    #: unpaid animal.
    frame_age_s: float | None
    #: `--stale-after`: a display choice (spec §3), not a measurement.
    stale_after_s: float
    #: Derived by `wlx serve` from `trial_index` over the frames of the last five
    #: minutes (spec §4.1); `None` until two frames a moment apart exist.
    trials_per_min: float | None
    #: Whether the browser this render is for is on the box (a loopback peer).
    on_box: bool
    #: How many event streams are open from other hosts.
    lan_viewers: int
    #: Why the last frame `wlx serve` received could not be used, or `None`.
    rejected: str | None


#: Every fragment `fragments` renders, in page order. Each is the inner HTML of the
#: element with that id; the page's script swaps them by the same id.
FRAGMENT_IDS = (
    "state",
    "head-id",
    "presence",
    "strip",
    "banners",
    "rt-trials",
    "rt-work",
    "rt-need",
    "rt-wrong",
    "rt-health",
    "rt-changes",
    "params",
    "setup",
    "end",
)

#: The ticks' legend: one entry per `Family`, then the two strings that are none.
LEGEND = tuple((family.name.lower(), family.value) for family in Family) + (
    ("hang", "hang"),
    ("other", "unknown outcome"),
)

_NONE = '<span class="nm">no session</span>'
_UNKNOWN_DAY = "unknown: the day's prior total was not supplied"
#: Spec §3: "Drops, tracker staleness and RHX margin have no source and render not
#: measured, never 0."
_NOT_MEASURED = ("dropped frames", "tracker staleness", "RHX margin")
_VERDICT_TONE = {"ok": "ok", "degraded": "warn", "down": "crit"}


def _e(value: object) -> str:
    """The one way telemetry text reaches the page."""
    return html.escape(str(value), quote=True)


def _num(value: object) -> str:
    """A parameter's value: `unset` for `None`, two decimals for a number, and the
    text of a categorical choice. Formatting, not derivation."""
    if value is None:
        return "unset"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value)


def _edge(value: object) -> str:
    """One end of a declared range: `open` where the task declared none."""
    return "open" if value is None else _num(value)


def _pct(part: float, whole: float) -> float:
    """A bar's width, held to 0-100. Display arithmetic on two published numbers."""
    if whole <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * part / whole))


# --- the header -------------------------------------------------------------------


def _state(frame: Telemetry | None) -> str:
    """The header's pill, from `phase` and `stop_kind` (spec §4.2)."""
    if frame is None:
        return '<span class="pill neutral" data-state="none">no session</span>'
    if frame.stop_kind is None:
        return '<span class="pill ok" data-state="running">running</span>'
    tone = "crit" if frame.stop_kind in ("fault", "limit") else "neutral"
    label = f"ended · {frame.stop_kind}"
    if frame.phase == "awaiting_return":
        label += " · awaiting return"
    elif frame.phase == "closed":
        label += " · returned"
    return f'<span class="pill {tone}" data-state="ended">{_e(label)}</span>'


def _head(frame: Telemetry | None) -> str:
    """Session, subject, deployment, block, trial, and the in-session clock."""
    if frame is None:
        return _NONE
    in_session = (
        "—" if frame.in_session_seconds is None else _clock(frame.in_session_seconds)
    )
    cells = (
        ("Session", _e(frame.session_id), ""),
        ("Subject", _e(frame.subject), ""),
        ("Deployment", _e(frame.deployment), ""),
        ("Block", _e(frame.block), ""),
        ("Trial", _e(frame.trial_index), f' data-trial="{_e(frame.trial_index)}"'),
        ("In session", in_session, ""),
    )
    return "".join(
        f'<span><span class="k">{name}</span><span class="v"{attr}>{value}</span></span>'
        for name, value, attr in cells
    )


def _presence(view: View) -> str:
    """This box, or a LAN viewer, and how many LAN viewers there are (spec §4.2)."""
    count = view.lan_viewers
    lan = f"{count} LAN viewer{'' if count == 1 else 's'}"
    who = "this box" if view.on_box else "LAN viewer"
    return f"<b>{who}</b> · {lan}"


# --- the strip --------------------------------------------------------------------


def _cell(
    label: str, value: str, *, sub: str = "", bar: tuple[float, str] | None = None
) -> str:
    """One strip cell. `label` and `sub` are this module's own text; `value` is HTML
    built from escaped parts."""
    parts = [
        f'<div class="row"><span class="lab">{label}</span>'
        f'<span class="val">{value}</span></div>'
    ]
    if bar is not None:
        width, tone = bar
        parts.append(
            f'<div class="bar" aria-hidden="true">'
            f'<div class="fill {tone}" style="width:{width:.1f}%"></div></div>'
        )
    if sub:
        parts.append(f'<span class="sub">{sub}</span>')
    return "<div>" + "".join(parts) + "</div>"


def _fluid_today(frame: Telemetry) -> str:
    floor = f'<span class="u">/ {frame.floor_ml:.2f} mL</span>'
    if frame.fluid_today_ml is None:
        return _cell(
            "Fluid today / floor",
            f'<span class="nm">unknown</span>{floor}',
            sub="the day's prior total was not supplied",
        )
    tone = "ok" if frame.fluid_today_ml >= frame.floor_ml else ""
    return _cell(
        "Fluid today / floor",
        f"{frame.fluid_today_ml:.2f}{floor}",
        bar=(_pct(frame.fluid_today_ml, frame.floor_ml), tone),
    )


def _out_of_cage(frame: Telemetry) -> str:
    if frame.out_of_cage_seconds is None:
        return _cell("Out of cage", '<span class="nm">cage-side · no limit</span>')
    clock = _clock(frame.out_of_cage_seconds)
    limit = frame.out_of_cage_limit_s
    if limit is None:
        return _cell("Out of cage", clock)
    tone = "crit" if frame.stop_kind == "limit" else "warn" if frame.duration_warning else ""
    return _cell(
        f"Out of cage / {_clock(limit)}",
        clock,
        bar=(_pct(frame.out_of_cage_seconds, limit), tone),
    )


def _correct(frame: Telemetry, view: View) -> str:
    rate = (
        "trials/min not yet derived"
        if view.trials_per_min is None
        else f"{view.trials_per_min:.1f} trials/min, derived by wlx serve"
    )
    if frame.trial_index == 0:
        return _cell("Correct / trials", '<span class="nm">no trials yet</span>', sub=rate)
    # The one rollup, and the strip's alone (PI, 2026-09-26, spec §3): `correct` plus
    # `correct_reject`, both the right answer on their trial. The Working? pane and
    # `/health` stay unrolled.
    correct = frame.outcomes.get(Outcome.CORRECT.value, 0) + frame.outcomes.get(
        Outcome.CORRECT_REJECT.value, 0
    )
    percent = 100.0 * correct / frame.trial_index
    return _cell(
        "Correct / trials",
        f'{_e(correct)}<span class="u">/ {_e(frame.trial_index)}</span>',
        sub=f"{percent:.0f}% correct · {rate}",
    )


def _last_reward(frame: Telemetry, view: View) -> str:
    if frame.last_reward_at is None:
        return _cell("Since last reward", '<span class="nm">none yet</span>')
    # Ledger Ruling 1 (2026-09-27): the frame's own instant less the reward's, one
    # interval on the session's anchored clock, plus how long `wlx serve` has held the
    # frame, on its steady clock. `frame_age_s` is `None` only before any frame, and
    # a render with a frame and no age is the age as of the frame.
    held = view.frame_age_s or 0.0
    return _cell(
        "Since last reward",
        _health.ago(frame.wall_at - frame.last_reward_at + held),
    )


def _strip(frame: Telemetry | None, view: View) -> str:
    if frame is None:
        return "".join(
            _cell(label, _NONE)
            for label in (
                "Fluid today / floor",
                "Out of cage",
                "Correct / trials",
                "Since last reward",
            )
        )
    return (
        _fluid_today(frame)
        + _out_of_cage(frame)
        + _correct(frame, view)
        + _last_reward(frame, view)
    )


# --- banners ----------------------------------------------------------------------


def _banner(tone: str, tag: str, text: str) -> str:
    return (
        f'<div class="banner {tone}"><span class="tag">{tag}</span>'
        f"<span>{text}</span></div>"
    )


def _banners(frame: Telemetry | None, view: View) -> str:
    """A refused frame first, then the duration warning and the stop reason -- where
    a person looks when something is wrong. The stream's own banner (stale, lost) is
    the page script's, in its own element."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    if frame is None:
        out.append(
            _banner(
                "info",
                "Waiting",
                "no telemetry yet: no session is publishing on the link this console reads",
            )
        )
        return "".join(out)
    if frame.duration_warning:
        tone = "crit" if frame.stop_kind == "limit" else "warn"
        out.append(_banner(tone, "Warning", _e(frame.duration_warning)))
    if frame.stopped_because:
        tone = "crit" if frame.stop_kind in ("fault", "limit") else "info"
        out.append(_banner(tone, "Ended", _e(frame.stopped_because)))
    return "".join(out)


# --- runtime ------------------------------------------------------------------------


def _trials(frame: Telemetry | None) -> str:
    """The last outcomes as ticks, oldest first, colored by family, with a legend."""
    if frame is None:
        return _NONE
    recent = frame.recent_outcomes
    blanks = '<span class="tk"></span>' * max(0, RECENT_OUTCOMES - len(recent))
    ticks = "".join(
        f'<span class="tk f-{_health.family_key(outcome)}" title="{_e(outcome)}"></span>'
        for outcome in recent
    )
    legend = "".join(
        f'<span><i class="tk f-{key}"></i>{label}</span>' for key, label in LEGEND
    )
    return (
        f'<div class="sub">the last {len(recent)} of {_e(frame.trial_index)} trials, '
        f"oldest first</div>"
        f'<div class="ticks">{blanks}{ticks}</div><div class="legend">{legend}</div>'
    )


def _fluid(frame: Telemetry) -> str:
    """Fluid session and the supplement: welfare-load-bearing, never dropped."""
    supplement = (
        f'<span class="nm">{_UNKNOWN_DAY}</span>'
        if frame.shortfall_ml is None
        else f'<span class="num">{frame.shortfall_ml:.2f} mL</span>'
    )
    return (
        f'<div class="kv"><span>fluid session</span>'
        f'<span class="num">{frame.fluid_session_ml:.2f} mL</span></div>'
        f'<div class="kv"><span>supplement owed</span>{supplement}</div>'
    )


def _work(frame: Telemetry | None) -> str:
    """Total trials, then every outcome that occurred with its count, by family, and
    no rollup -- `health.families`, so this and `/health` agree (spec §3)."""
    if frame is None:
        return _NONE
    groups = "".join(
        f'<div class="fam"><h3>{_e(label)}</h3>'
        + "".join(
            f'<div class="kv"><span>{_e(name)}</span>'
            f'<span class="num">{_e(count)}</span></div>'
            for name, count in rows
        )
        + "</div>"
        for _, label, rows in _health.families(frame.outcomes)
    )
    hangs = (
        f'<div class="fam"><h3>Hangs</h3><div class="kv"><span>hangs</span>'
        f'<span class="num">{_e(frame.hangs)}</span></div></div>'
    )
    return (
        f'<div class="selrow"><span class="big">{_e(frame.trial_index)}</span>'
        f'<span class="unit">trials</span></div>'
        f'<div class="counts">{groups}{hangs}</div>{_fluid(frame)}'
    )


def _need(frame: Telemetry | None) -> str:
    """Still needed, by condition: `scheduler.owed` as published."""
    if frame is None:
        return _NONE
    if not frame.owed:
        return '<span class="nm">nothing still needed</span>'
    return "".join(
        f'<div class="kv"><span class="mono">{_e(condition)}</span>'
        f'<span class="num">{_e(count)}</span></div>'
        for condition, count in frame.owed.items()
    )


def _wrong(frame: Telemetry | None) -> str:
    """Hangs, which are counted, and the three measurements nothing takes yet."""
    hangs = _NONE if frame is None else f'<span class="num">{_e(frame.hangs)}</span>'
    rows = [f'<div class="kv"><span>hangs</span>{hangs}</div>']
    rows += [
        f'<div class="kv"><span>{name}</span><span class="nm">not measured</span></div>'
        for name in _NOT_MEASURED
    ]
    return "".join(rows)


def _health_pane(frame: Telemetry | None, view: View) -> str:
    """*wl-works sees*: `/health`'s verdict and readings, as they would be sent."""
    verdict = _health.verdict(
        frame, frame_age_s=view.frame_age_s, stale_after_s=view.stale_after_s
    )
    rows = "".join(
        f'<div class="r"><span class="f">{"◆" if reading["featured"] else ""}</span>'
        f'<span class="l">{_e(reading["label"])}</span>'
        f'<span class="v">{_e(reading["value"])}</span></div>'
        for reading in _health.readings(
            frame, frame_age_s=view.frame_age_s, stale_after_s=view.stale_after_s
        )
    )
    return f'<div><span class="pill {_VERDICT_TONE[verdict]}">{verdict}</span></div>{rows}'


def _changes(frame: Telemetry | None) -> str:
    """Staged and refused changes, the dropped-refusal count before the rows, as
    `cli.render` does."""
    if frame is None:
        return _NONE
    rows = []
    for change in frame.staged:
        kind = "welfare-bounded ceiling" if change.bounded else "task parameter"
        rows.append(
            f'<div class="ev staged"><span class="kind">staged</span><span>'
            f"{_e(change.name)} {_e(_num(change.was))} → {_e(_num(change.now))} "
            f"by {_e(change.by)} ({kind}, applies at the next trial)</span></div>"
        )
    if frame.refusals_dropped:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(frame.refusals_dropped)} earlier refusal(s) not shown: only the most "
            f"recent {len(frame.refusals)} are kept</span></div>"
        )
    for refusal in frame.refusals:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(refusal.name)} by {_e(refusal.by)}: {_e(refusal.why)}</span></div>"
        )
    return "".join(rows) or '<span class="nm">nothing staged or refused</span>'


# --- task parameters, setup, end of session ----------------------------------------


def _range(row) -> str:
    if row.bounded:
        return f"welfare ceiling {_e(_num(row.high))} {_e(row.unit)}"
    if row.low is None and row.high is None:
        return "no declared range"
    return f"{_e(_edge(row.low))} to {_e(_edge(row.high))} {_e(row.unit)}"


def _params(frame: Telemetry | None) -> str:
    """One card per `ParamRow`: value, unit, range, the ceiling flag, and a staged
    marker. Read-only: b2 adds the inputs."""
    if frame is None:
        return _NONE
    if not frame.params:
        return '<span class="nm">this task declares no parameters</span>'
    staged = {change.name: change for change in frame.staged}
    cards = []
    for row in frame.params:
        change = staged.get(row.name)
        flag = '<span class="ceil">ceiling</span>' if row.bounded else ""
        mark = (
            ""
            if change is None
            else f'<span class="stg">staged → {_e(_num(change.now))} by {_e(change.by)}</span>'
        )
        cls = "param staged" if change is not None else "param"
        cards.append(
            f'<div class="{cls}"><div class="pn"><span>{_e(row.name)}</span>{flag}</div>'
            f'<span class="pv">{_e(_num(row.value))} '
            f'<span class="unit">{_e(row.unit)}</span></span>'
            f'<span class="range">{_range(row)}</span>{mark}</div>'
        )
    return "".join(cards)


def _setup(frame: Telemetry | None) -> str:
    """S9a §3's configuration information. Display mode and stimulus calibration have
    no source yet and say so (spec §3)."""
    if frame is None:
        return _NONE
    limit = (
        '<span class="nm">none: cage-side</span>'
        if frame.out_of_cage_limit_s is None
        else _clock(frame.out_of_cage_limit_s)
    )
    rows = (
        ("session", _e(frame.session_id)),
        ("subject", _e(frame.subject)),
        ("deployment", _e(frame.deployment)),
        ("task", _e(frame.task)),
        (
            "allocation",
            _e(frame.allocation)
            if frame.allocation
            else '<span class="nm">provisional: none given</span>',
        ),
        (
            "bounds config",
            _e(frame.bounds_config)
            if frame.bounds_config
            else '<span class="nm">not given</span>',
        ),
        ("daily fluid floor", f"{frame.floor_ml:.2f} mL"),
        ("out-of-cage limit", limit),
        ("display mode", '<span class="nm">no source yet</span>'),
        ("stimulus calibration", '<span class="nm">no source yet</span>'),
    )
    return (
        '<dl class="dl">'
        + "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in rows)
        + "</dl>"
    )


def _end(frame: Telemetry | None) -> str:
    """The supplement owed, fluid session, out-of-cage and in-session time, and the
    stop reason (spec §4.2)."""
    if frame is None:
        return _NONE
    owed = (
        f'<span class="nm">{_UNKNOWN_DAY}</span>'
        if frame.shortfall_ml is None
        else f'<span class="big">{frame.shortfall_ml:.2f}</span><span class="unit">mL</span>'
    )
    cage = (
        '<span class="nm">cage-side · no out-of-cage interval</span>'
        if frame.out_of_cage_seconds is None
        else _clock(frame.out_of_cage_seconds)
    )
    in_session = (
        '<span class="nm">not recorded</span>'
        if frame.in_session_seconds is None
        else _clock(frame.in_session_seconds)
    )
    reason = (
        _e(frame.stopped_because)
        if frame.stopped_because
        else '<span class="nm">still running</span>'
    )
    return (
        f'<div class="owe"><h2>Supplement owed</h2>{owed}</div>'
        f'<dl class="dl"><dt>fluid session</dt><dd>{frame.fluid_session_ml:.2f} mL</dd>'
        f"<dt>out of cage</dt><dd>{cage}</dd>"
        f"<dt>in session</dt><dd>{in_session}</dd>"
        f"<dt>stop reason</dt><dd>{reason}</dd></dl>"
    )


def fragments(frame: Telemetry | None, view: View) -> dict[str, str]:
    """Every pane of the page for one frame, keyed by the id of the element each one
    fills (`FRAGMENT_IDS`, in that order). `frame` is `None` before any has arrived,
    and every pane then says so."""
    return {
        "state": _state(frame),
        "head-id": _head(frame),
        "presence": _presence(view),
        "strip": _strip(frame, view),
        "banners": _banners(frame, view),
        "rt-trials": _trials(frame),
        "rt-work": _work(frame),
        "rt-need": _need(frame),
        "rt-wrong": _wrong(frame),
        "rt-health": _health_pane(frame, view),
        "rt-changes": _changes(frame),
        "params": _params(frame),
        "setup": _setup(frame),
        "end": _end(frame),
    }
