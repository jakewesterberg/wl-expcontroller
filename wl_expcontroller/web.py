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
import math
from dataclasses import dataclass
from importlib import resources

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
    #: The PUB endpoint this console reads, `--link`'s first half (`serve.Hub`). With
    #: no frame and no refusal, what the page and `/health` can truthfully say is
    #: that nothing has arrived *here* -- never that nothing is publishing (m4).
    endpoint: str


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
    since = frame.wall_at - frame.last_reward_at + held
    # m1: a reward instant that is not a number is stored, not refused (it bounds
    # nothing), so it can arrive here; it is a word, never a crash of every pane.
    if not math.isfinite(since):
        return _cell("Since last reward", '<span class="nm">unknown</span>')
    return _cell("Since last reward", _health.ago(since))


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
    the page script's, in its own element.

    **With no frame, *Waiting* only when nothing was refused either** (Ruling 11,
    2026-09-27): a refused frame is a session publishing in a form this console
    cannot read, so a sentence saying nothing had arrived would be false beside it."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    if frame is None:
        if view.rejected:
            return "".join(out)
        out.append(
            _banner(
                "info",
                "Waiting",
                f"no telemetry yet: no frame has arrived on {_e(view.endpoint)}",
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
    """*wl-works sees*: `/health`'s verdict and readings, as they would be sent --
    `health.response` itself, from the same `View` fields `serve`'s `/health` hands
    it, so the two cannot disagree about a refusal (Ruling 11)."""
    body = _health.response(
        frame,
        frame_age_s=view.frame_age_s,
        stale_after_s=view.stale_after_s,
        rejected=view.rejected,
        endpoint=view.endpoint,
    )
    verdict = body["verdict"]
    rows = "".join(
        f'<div class="r"><span class="f">{"◆" if reading["featured"] else ""}</span>'
        f'<span class="l">{_e(reading["label"])}</span>'
        f'<span class="v">{_e(reading["value"])}</span></div>'
        for reading in body["readings"]
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


# --- the page -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Font:
    """One face the page uses: bundled at `wl_expcontroller/fonts/<directory>/<file>`
    and served by `wlx serve` at `/fonts/<file>`."""

    family: str
    weight: int
    style: str
    directory: str
    file: str


#: **Every face the page's CSS asks for, and no other** (PI, 2026-09-26: "bundle the
#: fonts", so the page keeps the wl-works look and never reaches the internet). The
#: unmodified woff2 files their primary sources publish -- the IBM/plex GitHub releases
#: and productiontype/Newsreader -- fetched 2026-09-26, each family's OFL-1.1 license
#: beside them as `OFL.txt`; ADR-0004's inventory carries the sources and licenses.
#: The weights are the ones `_CSS` sets; italics are synthesized, as in the mockup.
#: Newsreader draws only the logo, from its 72pt optical-size cut.
FONTS = (
    Font("IBM Plex Sans", 400, "normal", "ibm-plex-sans", "IBMPlexSans-Regular.woff2"),
    Font("IBM Plex Sans", 500, "normal", "ibm-plex-sans", "IBMPlexSans-Medium.woff2"),
    Font("IBM Plex Sans", 600, "normal", "ibm-plex-sans", "IBMPlexSans-SemiBold.woff2"),
    Font(
        "IBM Plex Sans Condensed",
        400,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-Regular.woff2",
    ),
    Font(
        "IBM Plex Sans Condensed",
        600,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-SemiBold.woff2",
    ),
    Font(
        "IBM Plex Sans Condensed",
        700,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-Bold.woff2",
    ),
    Font("IBM Plex Mono", 400, "normal", "ibm-plex-mono", "IBMPlexMono-Regular.woff2"),
    Font("IBM Plex Mono", 500, "normal", "ibm-plex-mono", "IBMPlexMono-Medium.woff2"),
    Font("IBM Plex Mono", 600, "normal", "ibm-plex-mono", "IBMPlexMono-SemiBold.woff2"),
    Font("Newsreader", 700, "normal", "newsreader", "Newsreader72pt-Bold.woff2"),
    Font("Newsreader", 700, "italic", "newsreader", "Newsreader72pt-BoldItalic.woff2"),
)


def font_bytes(font: Font) -> bytes:
    """A bundled font file, read as package data -- the same bytes from a checkout and
    from an installed wheel (`pyproject.toml`'s `package-data`)."""
    return (
        resources.files("wl_expcontroller")
        .joinpath("fonts")
        .joinpath(font.directory)
        .joinpath(font.file)
        .read_bytes()
    )


#: One `@font-face` per bundled face, each fetched from this box's `/fonts/` route.
_FONT_FACES = "".join(
    f'@font-face {{ font-family: "{font.family}"; font-style: {font.style}; '
    f"font-weight: {font.weight}; font-display: swap; "
    f'src: url("/fonts/{font.file}") format("woff2"); }}\n'
    for font in FONTS
)

#: The mockup's wl-works tokens and layout (`docs/superpowers/mockups/
#: 2026-09-26-console-mockup-v12.html`), trimmed to what b1 builds. **The fonts are the
#: box's own** (`FONTS`, `_FONT_FACES`); each stack's system faces are only the fallback
#: while they load. Tabs are radio inputs styled by `:checked`, so they need no script.
_CSS = """
:root {
  --bg: #faf8f3; --surface: #fffefb; --surface-2: #f2f0e9; --ink: #050c19; --muted: #55606f;
  --rule: rgb(136 148 166 / 0.45); --edge: rgb(5 12 25 / 0.08);
  --accent: #0a6e6b; --accent-fg: #faf8f3; --accent-soft: #dfecea;
  --ok: #2e7a4f; --ok-soft: #deefe4; --warn: #9a5b00; --warn-soft: #f6e7cf;
  --crit: #b3261e; --crit-soft: #f6dcda;
  --screen: #081122; --screen-ink: #8ea0bc; --rf: #67b2ea; --mock: #452d81;
  --wl-muted: #55606f; --distract: #c9187b;
  --shadow: inset 0 1px 0 rgb(255 255 255 / 0.9), inset 0 -1px 0 rgb(5 12 25 / 0.06), 0 1px 2px rgb(5 12 25 / 0.04), 0 8px 28px -12px rgb(5 12 25 / 0.18);
  --sans: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  --cond: "IBM Plex Sans Condensed", "IBM Plex Sans", "Arial Narrow", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #050c19; --surface: #112037; --surface-2: #152743; --ink: #faf8f3; --muted: #8ea0bc;
    --rule: rgb(136 148 166 / 0.3); --edge: rgb(250 248 243 / 0.1);
    --accent: #12a5a1; --accent-fg: #050c19; --accent-soft: #0f3a44;
    --ok: #5cba80; --ok-soft: #133427; --warn: #e6a646; --warn-soft: #382a12;
    --crit: #f07166; --crit-soft: #3c1b1a;
    --screen: #02060d; --mock: #b3a2ea; --wl-muted: #8ea0bc; --distract: #d6579c;
    --shadow: inset 0 1px 0 rgb(250 248 243 / 0.06), inset 0 -1px 0 rgb(0 0 0 / 0.25), 0 1px 2px rgb(0 0 0 / 0.3), 0 8px 28px -12px rgb(0 0 0 / 0.6);
  }
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.4; padding: 12px 16px 28px; }
.wrap { max-width: 1520px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.num, .mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
h2 { font-family: var(--cond); font-weight: 700; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin: 0; }
h3 { margin: 0; font-family: var(--cond); font-weight: 600; font-size: 11.5px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); }
.sub { font-size: 12.5px; color: var(--muted); }
.nm { color: var(--muted); font-style: italic; }
.later { font-size: 11px; color: var(--mock); font-family: var(--cond); letter-spacing: 0.05em; text-transform: uppercase; font-weight: 600; }
.glass { background: var(--surface); border: 1px solid var(--edge); border-radius: 8px; box-shadow: var(--shadow); }
.head { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center; padding: 8px 14px; }
.logo { display: flex; align-items: center; gap: 10px; color: var(--ink); }
.logo svg { height: 34px; width: auto; display: block; }
.logo .app { font-family: var(--cond); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12px; color: var(--muted); border-left: 1px solid var(--rule); padding-left: 10px; }
.head .id { display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; }
.head .k { font-family: var(--cond); font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin-right: 4px; }
.head .v { font-family: var(--mono); font-weight: 500; }
.head .spacer { flex: 1; }
.presence { font-size: 12.5px; color: var(--muted); }
.presence b { color: var(--ink); font-weight: 600; }
.pill { font-family: var(--cond); font-weight: 700; letter-spacing: 0.08em; font-size: 12px; text-transform: uppercase; border-radius: 999px; padding: 3px 10px; display: inline-flex; gap: 6px; align-items: center; white-space: nowrap; }
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.pill.ok { background: var(--ok-soft); color: var(--ok); }
.pill.warn { background: var(--warn-soft); color: var(--warn); }
.pill.crit { background: var(--crit-soft); color: var(--crit); }
.pill.neutral { background: var(--surface-2); color: var(--muted); }
.strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); overflow: hidden; }
.strip > div { padding: 5px 12px; display: grid; gap: 3px; border-left: 1px solid var(--rule); }
.strip > div:first-child { border-left: 0; }
.strip .row { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 0 8px; }
.strip .lab { font-family: var(--cond); font-weight: 700; font-size: 11.5px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }
.strip .val { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 14.5px; font-weight: 600; white-space: nowrap; }
.strip .val .u { font-size: 12px; color: var(--muted); font-family: var(--sans); font-weight: 400; margin-left: 3px; }
.strip .bar { height: 4px; }
.banners { display: grid; gap: 6px; }
.banner { border-radius: 6px; padding: 6px 12px; font-size: 13.5px; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.banner.warn { background: var(--warn-soft); border-left: 4px solid var(--warn); }
.banner.crit { background: var(--crit-soft); border-left: 4px solid var(--crit); }
.banner.info { background: var(--accent-soft); border-left: 4px solid var(--accent); }
.banner .tag { font-family: var(--cond); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12px; }
.shell { display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr) minmax(260px, 330px); align-items: stretch; }
@media (max-width: 900px) { .shell { grid-template-columns: minmax(0, 1fr); } }
.main { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.main > input { position: absolute; opacity: 0; pointer-events: none; }
.tabs { display: flex; flex-wrap: wrap; gap: 2px; border-bottom: 1px solid var(--rule); }
.tab { border: 1px solid transparent; border-bottom: 0; padding: 7px 12px 6px; cursor: pointer; font-family: var(--cond); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12.5px; color: var(--muted); border-radius: 6px 6px 0 0; margin-bottom: -1px; }
#t-runtime:checked ~ .tabs [for="t-runtime"], #t-task:checked ~ .tabs [for="t-task"], #t-setup:checked ~ .tabs [for="t-setup"], #t-end:checked ~ .tabs [for="t-end"] { background: var(--surface); border-color: var(--edge); color: var(--ink); }
#t-runtime:focus-visible ~ .tabs [for="t-runtime"], #t-task:focus-visible ~ .tabs [for="t-task"], #t-setup:focus-visible ~ .tabs [for="t-setup"], #t-end:focus-visible ~ .tabs [for="t-end"] { outline: 2px solid var(--accent); outline-offset: 2px; }
.tabpanel { display: none; flex-direction: column; gap: 10px; }
#t-runtime:checked ~ .panels #tp-runtime, #t-task:checked ~ .panels #tp-task, #t-setup:checked ~ .panels #tp-setup, #t-end:checked ~ .panels #tp-end { display: flex; }
.cols { display: grid; gap: 10px; align-items: stretch; }
.cols.c3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
@media (max-width: 1100px) { .cols.c3 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .cols.c3 { grid-template-columns: minmax(0, 1fr); } }
.stack, .aside { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.panel { padding: 9px 12px; display: grid; gap: 7px; align-content: start; min-width: 0; }
.panel .top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 10px; font-size: 13px; margin: 0; }
.dl dt { color: var(--muted); }
.dl dd { margin: 0; font-family: var(--mono); font-size: 12.5px; overflow-wrap: anywhere; }
.big { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 22px; font-weight: 600; line-height: 1.1; }
.unit { font-size: 13px; color: var(--muted); font-weight: 500; margin-left: 3px; font-family: var(--sans); }
.selrow { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.bar { height: 8px; background: var(--surface-2); border-radius: 3px; position: relative; overflow: hidden; }
.bar .fill { position: absolute; inset: 0 auto 0 0; background: var(--accent); }
.bar .fill.ok { background: var(--ok); } .bar .fill.warn { background: var(--warn); } .bar .fill.crit { background: var(--crit); }
.counts { display: grid; gap: 6px 14px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.fam { display: grid; gap: 1px; align-content: start; }
.kv { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }
.kv > span { min-width: 0; overflow-wrap: anywhere; }
.owe { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; background: var(--accent-soft); border-radius: 6px; padding: 8px 10px; }
.params { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
.param { border: 1px solid var(--rule); border-radius: 5px; padding: 6px 8px; display: grid; gap: 2px; background: var(--surface-2); }
.param .pn { font-family: var(--mono); font-size: 12.5px; font-weight: 500; display: flex; justify-content: space-between; gap: 6px; overflow-wrap: anywhere; }
.param .ceil { font-family: var(--cond); font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--warn); font-weight: 700; }
.param .pv { font-family: var(--mono); font-size: 13px; }
.param .range, .param .stg { font-size: 11.5px; color: var(--muted); }
.param.staged { border-color: var(--accent); }
.param.staged .stg { color: var(--accent); }
.feed { display: grid; align-content: start; max-height: 300px; overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; }
.ev { display: grid; grid-template-columns: 5.5em minmax(0, 1fr); gap: 6px; padding: 4px 0; border-top: 1px solid var(--rule); font-size: 12.5px; }
.ev:first-child { border-top: 0; }
.ev > span { min-width: 0; overflow-wrap: anywhere; }
.ev .kind { font-family: var(--cond); font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; font-size: 11px; }
.ev.staged .kind { color: var(--accent); } .ev.refused .kind { color: var(--crit); }
.health .r { display: grid; grid-template-columns: 1em minmax(0, 7.5em) minmax(0, 1fr); gap: 6px; font-size: 12.5px; }
.health .r .f { color: var(--accent); } .health .r .l { color: var(--muted); }
.health .r .v { font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.ticks { display: grid; grid-template-columns: repeat(30, minmax(0, 1fr)); gap: 2px; }
.tk { display: block; height: 12px; border-radius: 2px; background: var(--surface-2); }
.tk.f-target { background: var(--accent); } .tk.f-distractor { background: var(--crit); } .tk.f-withhold { background: var(--rf); }
.tk.f-no_engagement { background: color-mix(in srgb, var(--muted) 60%, transparent); } .tk.f-breaks { background: var(--warn); } .tk.f-rig { background: var(--mock); }
.tk.f-hang { background: var(--ink); } .tk.f-other { background: transparent; box-shadow: inset 0 0 0 1px var(--muted); }
.legend { display: flex; flex-wrap: wrap; gap: 3px 12px; font-size: 11.5px; color: var(--muted); }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
.screen { border-radius: 5px; background: var(--screen); color: var(--screen-ink); aspect-ratio: 16 / 9; display: grid; place-items: center; font-family: var(--mono); font-size: 12px; }
.duo { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.xbtn { width: 30px; height: 30px; display: grid; place-items: center; border: 1.5px solid var(--distract); color: var(--distract); background: transparent; border-radius: 6px; cursor: pointer; padding: 0; flex: none; }
.xbtn:hover { background: var(--distract); color: var(--bg); }
.xbtn svg { width: 12px; height: 12px; }
.btn { border: 1px solid var(--rule); background: var(--surface); color: inherit; border-radius: 5px; padding: 5px 12px; cursor: pointer; font-family: var(--cond); font-weight: 600; font-size: 14px; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
.scrim { position: fixed; inset: 0; background: var(--bg); display: grid; place-items: center; padding: 16px; z-index: 30; }
.dialog { padding: 16px; width: min(520px, 100%); display: grid; gap: 12px; }
.dialog h2 { font-size: 14px; color: var(--ink); }
.dialog .actions { display: flex; justify-content: flex-end; }
body.stale .strip, body.stale .panels { filter: grayscale(1); opacity: 0.55; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""

#: The wl.works mark, as the mockup draws it. No `xmlns`: an inline SVG in an HTML
#: document needs none, and the page names no other host, not even as a namespace.
_LOGO = (
    '<svg viewBox="0 0 395.67 147.54" role="img" aria-label="wl.works">'
    '<circle cx="130.40" cy="34.98" r="11" fill="currentColor"/>'
    '<circle cx="97.40" cy="11.00" r="11" fill="currentColor"/>'
    '<circle cx="56.60" cy="11.00" r="11" fill="currentColor"/>'
    '<circle cx="23.60" cy="34.98" r="11" fill="#C9187B"/>'
    '<circle cx="11.00" cy="73.77" r="11" fill="currentColor"/>'
    '<circle cx="23.60" cy="112.56" r="11" fill="currentColor"/>'
    '<rect x="45.6" y="125.54" width="22" height="22" fill="currentColor"/>'
    '<circle cx="97.40" cy="136.54" r="11" fill="currentColor"/>'
    '<text x="71" y="112.77" font-family="Newsreader, Georgia, serif" font-size="72" '
    'font-weight="700" letter-spacing="-1.44" fill="currentColor">w'
    '<tspan font-style="italic">l</tspan>'
    '<tspan style="fill: var(--wl-muted)">.works</tspan></text></svg>'
)

#: **The page's whole script, and all it does** (spec §4.3, §4.4): open the event
#: stream, swap each fragment into the element with its id, run the stale timer while
#: more frames are due, close the stream on the ✕, and reconnect. `EventSource`
#: reconnects on its own after a dropped connection, and `wlx serve` sends a full
#: render first on every new stream, so a reconnect re-renders in full. Everything
#: worth testing is in Python; this is small enough to read.
#:
#: **The stale timer runs from the frame's age, not from an event's arrival**
#: (Ruling 12, 2026-09-27). Every event carries `age`, the seconds `wlx serve` has
#: held the latest frame; the baseline is the arrival less that, and the stream is
#: stale once `now - baseline` reaches `--stale-after` -- `>=`, so the page agrees
#: with `/health`'s own boundary -- with that interval as the banner's N. A `null`
#: age -- no frame yet -- runs no timer. It shares with `/health` *when* frames are
#: due (`live`, `health.expects_frames`), not the clock: this one is the page's own
#: `performance.now()`, monotonic so a browser clock step never skews it, carried
#: from `wlx serve`'s steady clock by `age`.
#:
#: **A lost stream is greyed as a stale one is** (m3): the timer stands down while
#: the stream is lost, so without this a red *stream lost* banner sat over
#: full-color numbers nothing was updating. The next frame's `check()` clears it.
_SCRIPT = """
(function () {
  "use strict";
  var body = document.body;
  var staleMs = Number(body.getAttribute("data-stale-after")) * 1000;
  var source = null;
  var baseline = null;
  var live = false;
  var lost = false;
  var closed = false;
  function el(id) { return document.getElementById(id); }
  function say(text, tone) {
    var banner = el("stream");
    banner.textContent = text || "";
    banner.className = "banner " + (tone || "");
    banner.hidden = !text;
  }
  function check() {
    if (closed || lost) { return; }
    if (!live || baseline === null) {
      body.classList.remove("stale");
      say("");
      return;
    }
    var held = performance.now() - baseline;
    if (held >= staleMs) {
      body.classList.add("stale");
      say("stream stale · last frame " + Math.floor(held / 1000) + " s ago", "warn");
    } else {
      body.classList.remove("stale");
      say("");
    }
  }
  function onFrame(event) {
    var payload = JSON.parse(event.data);
    Object.keys(payload.frags).forEach(function (id) {
      var node = el(id);
      if (node) { node.innerHTML = payload.frags[id]; }
    });
    live = payload.live;
    baseline = payload.age === null ? null : performance.now() - payload.age * 1000;
    lost = false;
    check();
  }
  function open() {
    closed = false;
    lost = false;
    el("gone").hidden = true;
    source = new EventSource("/events");
    source.addEventListener("frame", onFrame);
    source.onerror = function () {
      if (closed) { return; }
      lost = true;
      body.classList.add("stale");
      say("stream lost", "crit");
      if (source.readyState === EventSource.CLOSED) {
        setTimeout(function () { if (!closed && lost) { open(); } }, 3000);
      }
    };
  }
  setInterval(check, 1000);
  el("close").addEventListener("click", function () {
    closed = true;
    if (source) { source.close(); }
    say("");
    el("gone").hidden = false;
  });
  el("reconnect").addEventListener("click", function () {
    if (source) { source.close(); }
    open();
  });
  open();
})();
"""


def page(parts: dict[str, str], *, stale_after_s: float, nonce: str) -> str:
    """The whole document, every pane already rendered into it, so it reads before
    its stream has opened (spec §4.3).

    `parts` is `fragments(...)`; each fills the element whose id is its key, the id
    the stream's events swap by. A missing key raises `KeyError`: a page with a pane
    left blank is a bug to see, not a page to serve. `nonce` is the one in the
    Content-Security-Policy `wlx serve` sends with this response; the one script
    carries it. `stale_after_s` goes to the script as `data-stale-after`.

    **Nothing here writes** (spec §4.2): two buttons -- close this page's stream, and
    reconnect it -- and four radio inputs that choose a tab.
    """
    p = {key: parts[key] for key in FRAGMENT_IDS}
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>expcontroller console</title>
<style>{_FONT_FACES}{_CSS}</style>
</head>
<body data-stale-after="{stale_after_s:g}">
<div class="wrap">
  <header class="head glass">
    <span class="logo">{_LOGO}<span class="app">expcontroller</span></span>
    <span id="state">{p['state']}</span>
    <div class="id" id="head-id">{p['head-id']}</div>
    <span class="spacer"></span>
    <span class="presence" id="presence">{p['presence']}</span>
    <button class="xbtn" id="close" type="button" aria-label="close this page's stream" title="close this page's stream · the session keeps running on the box"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
  </header>
  <div class="strip glass" role="region" aria-label="animal" id="strip">{p['strip']}</div>
  <div class="banner" id="stream" role="status" hidden></div>
  <div class="banners" id="banners">{p['banners']}</div>
  <div class="shell">
    <div class="main">
      <input type="radio" name="tab" id="t-runtime" checked>
      <input type="radio" name="tab" id="t-task">
      <input type="radio" name="tab" id="t-setup">
      <input type="radio" name="tab" id="t-end">
      <div class="tabs" aria-label="console sections">
        <label class="tab" for="t-runtime">Runtime</label>
        <label class="tab" for="t-task">Task parameters</label>
        <label class="tab" for="t-setup">Setup</label>
        <label class="tab" for="t-end">End of session</label>
      </div>
      <div class="panels">
        <div class="tabpanel" id="tp-runtime">
          <section class="panel glass"><div class="top"><h2>Trials</h2></div><div id="rt-trials">{p['rt-trials']}</div></section>
          <section class="panel glass"><div class="top"><h2>This run</h2></div><div id="rt-work">{p['rt-work']}</div></section>
          <div class="cols c3">
            <div class="stack">
              <section class="panel glass"><div class="top"><h2>Still needed</h2></div><div id="rt-need">{p['rt-need']}</div></section>
              <section class="panel glass"><div class="top"><h2>Wrong?</h2></div><div id="rt-wrong">{p['rt-wrong']}</div></section>
            </div>
            <div class="stack"><section class="panel glass health"><div class="top"><h2>wl-works sees</h2></div><div id="rt-health">{p['rt-health']}</div></section></div>
            <div class="stack"><section class="panel glass"><div class="top"><h2>Changes</h2></div><div class="feed" id="rt-changes">{p['rt-changes']}</div></section></div>
          </div>
        </div>
        <div class="tabpanel" id="tp-task"><section class="panel glass"><div class="top"><h2>Task parameters</h2><span class="sub">read-only</span></div><div class="params" id="params">{p['params']}</div></section></div>
        <div class="tabpanel" id="tp-setup"><section class="panel glass"><div class="top"><h2>Setup</h2><span class="sub">read-only</span></div><div id="setup">{p['setup']}</div></section></div>
        <div class="tabpanel" id="tp-end"><section class="panel glass"><div class="top"><h2>End of session</h2><span class="sub">read-only</span></div><div id="end">{p['end']}</div></section></div>
      </div>
    </div>
    <aside class="aside" aria-label="always shown">
      <section class="panel glass"><div class="top"><h2>Replica</h2><span class="later">V11</span></div><div class="screen">replica · V11</div></section>
      <section class="panel glass"><div class="top"><h2>Subject display</h2></div><div class="screen">subject display · no source yet</div></section>
      <div class="duo">
        <section class="panel glass"><h2>Sound</h2><span class="nm">sound · not measured</span></section>
        <section class="panel glass"><h2>Display</h2><span class="nm">display · not measured</span></section>
      </div>
    </aside>
  </div>
</div>
<div class="scrim" id="gone" role="dialog" aria-modal="true" aria-labelledby="gone-h" hidden>
  <div class="dialog glass">
    <h2 id="gone-h">Disconnected</h2>
    <p>disconnected · the session keeps running on the box</p>
    <div class="actions"><button class="btn primary" id="reconnect" type="button">reconnect</button></div>
  </div>
</div>
<script nonce="{_e(nonce)}">{_SCRIPT}</script>
</body>
</html>
"""
