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
import time
from dataclasses import dataclass
from importlib import resources

from wl_xcon import health as _health
from wl_xcon.cli import _clock, _moment, _setup_words
from wl_xcon.link import RECENT_OUTCOMES, Idle, Question, Telemetry
from wl_xcon.task import Family, Outcome


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
    #: Whether this page may write (P4d-2b spec §2, §5.2): the box's own page, a
    #: loopback peer that named loopback in `Host`. Everywhere else every control is
    #: greyed with `CONTROLS_AT_THE_BOX`. `False` unless `wlx serve` says otherwise:
    #: a view that did not say may not write.
    can_write: bool = False
    #: Whether this console has the session's mark endpoint (`wlx serve --link
    #: PUB,REP,MARK`); without it the mark control is greyed with `NO_MARK_ENDPOINT`.
    can_mark: bool = False


#: Every fragment `fragments` renders, in page order. Each is the inner HTML of the
#: element with that id; the page's script swaps them by the same id.
FRAGMENT_IDS = (
    "state",
    "head-id",
    "presence",
    "strip",
    "banners",
    "task-sel",
    "pf-pill",
    "controls",
    "rt-trials",
    "rt-work",
    "rt-need",
    "rt-wrong",
    "rt-health",
    "rt-changes",
    "params",
    "pf-sum",
    "preflight",
    "setup",
    "end-actions",
    "end",
    "dn-subject",
)

#: The ticks' legend: one entry per `Family`, then the two strings that are none.
LEGEND = tuple((family.name.lower(), family.value) for family in Family) + (
    ("hang", "hang"),
    ("other", "unknown outcome"),
)

#: What a refused write says, and what every greyed control says (P4d-2b spec §2):
#: until remote sign-in arrives (b2b), writes come from the box alone.
CONTROLS_AT_THE_BOX = "controls work only at the rig PC until remote sign-in arrives"
#: Why the mark control is greyed on a console started without the mark endpoint.
NO_MARK_ENDPOINT = (
    "this console was started without the session's mark endpoint: give wlx serve "
    "--link PUB,REP,MARK, as wlx run was given it"
)
#: Why *give reward* is greyed while a run's trials run: during a run the rig gives a
#: manual reward only while it is paused (PI, 2026-09-28); outside a run, in a `wlx
#: taskd` session, it gives one between runs and while the return is awaited (PI,
#: 2026-09-29, spec §6.0; `taskd.Session._manual_reward`).
REWARD_ONLY_PAUSED = "a manual reward is given only while the session is paused: pause first"
#: How long after the last click on a parameter's arrows the change is sent, in
#: milliseconds: the mockup's debounce (spec §5.2), housekeeping and not a
#: measurement. The page's script reads it from `<body>`.
DEBOUNCE_MS = 600
#: What the page says beside *start run* and atop every pre-flight (P4d-2b spec §6.2:
#: "Every run is unplanned until b3b brings the day's plan, and the page says so each
#: time, with the warning that an unplanned run lowers the session's timing tier").
UNPLANNED = (
    "unplanned run: no day's plan reaches this rig yet (b3b), and an unplanned run lowers "
    "the session's timing tier"
)
#: The trials a run is offered with: `wlx run --trials`'s default (`cli`), since until the
#: day's plan (b3b) a run from the page is `wlx run`'s flat run of N trials (the b3a-2
#: plan, decision 6). A starting figure the person changes, not a rule or a measurement.
RUN_TRIALS = 1000
#: What *end session* asks before it is sent (the mockup's `end-confirm`, P4d-2b spec
#: §6.2): what ending does here, the head's release now and the return now or later (the
#: b3a-1 plan, decision 6) -- not the mockup's "the in-session clock stops, and the code
#: it used is packaged", which predates it and slice b6.
END_CONFIRM = (
    "end the session? no further run starts in it; a run in progress stops at its next "
    "trial boundary, and the head's release is recorded then. give the time the animal "
    "went back into its home cage now, or leave it blank and record it once the animal "
    "is home"
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


def _clock_time(at: float | None) -> str:
    """A session instant as this host's local clock time, `HH:MM:SS`, as `cli.render`
    prints the last reward: formatting an instant the frame carries, never reading a
    clock. One that is not a number is `—`, never a crash of every pane -- and so is a
    finite one too far out for `time.localtime`, which raises `OverflowError`,
    `OSError` or `ValueError` for it, by platform and by how far (the b2a final
    review)."""
    if at is None or not math.isfinite(at):
        return "—"
    try:
        return time.strftime("%H:%M:%S", time.localtime(at))
    except (OverflowError, OSError, ValueError):
        return "—"


def _state(frame: Telemetry | None) -> str:
    """The header's pill, from `phase`, `stop_kind` and -- P4d-2b b2a -- `paused_at`:
    a session that ended while paused shows how it ended, never *paused*."""
    if frame is None:
        return '<span class="pill neutral" data-state="none">no session</span>'
    if frame.phase == "between_runs":
        label = (
            "between runs"
            if frame.run_index is None
            else f"between runs · run {frame.run_index} ended · {frame.stop_kind}"
        )
        tone = "crit" if frame.stop_kind in ("fault", "limit") else "neutral"
        return f'<span class="pill {tone}" data-state="between-runs">{_e(label)}</span>'
    if frame.stop_kind is None and frame.paused_at is not None:
        return (
            f'<span class="pill warn" data-state="paused">paused · since '
            f"{_clock_time(frame.paused_at)}</span>"
        )
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
        ("Run", "—" if frame.run_index is None else _e(frame.run_index), ""),
        ("Block", "—" if frame.block is None else _e(frame.block), ""),
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


def _off(view: View, why: str = CONTROLS_AT_THE_BOX) -> str:
    """The attributes that grey a control this page may not use, saying why; nothing
    for the box's own page."""
    return "" if view.can_write else f' disabled title="{_e(why)}"'


def _scheduled(frame: Telemetry, view: View) -> str:
    """The strip's fifth cell, while a scheduled stop is held (spec §5.2): *stop at
    14:30 · set by jake*, in the rig's own words, with a cancel button."""
    stop = frame.scheduled_stop
    cancel = (
        f'<button type="button" class="btn small" data-cmd="cancel"{_off(view)}>'
        f"cancel</button>"
    )
    return _cell("Scheduled", f"stop {_e(stop.said)}", sub=f"set by {_e(stop.by)} {cancel}")


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
        # Only while the session runs: since Task 8's fix, `Telemetry.of` sends
        # `scheduled_stop=None` once `stopped_because` is set, so an ended session's
        # frame should never carry one. This guard defends against a frame the rig
        # no longer sends, not a schedule it still carries.
        + (
            _scheduled(frame, view)
            if frame.scheduled_stop is not None and frame.stop_kind is None
            else ""
        )
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
    if frame.question is not None:
        out.append(_question_banner(frame.question, view))
    if frame.stopped_because:
        tone = "crit" if frame.stop_kind in ("fault", "limit") else "info"
        tag = (
            f"Run {frame.run_index} ended"
            if frame.phase == "between_runs" and frame.run_index is not None
            else "Ended"
        )
        out.append(_banner(tone, tag, _e(frame.stopped_because)))
    return "".join(out)


# --- the run's task and its pre-flight (P4d-2b b3a-2) ------------------------------


def _options(names, none: str) -> str:
    """A select's options, one per name, or one empty option saying why there is none.
    A frame re-renders them; the page's script keeps the option a person chose (the
    b3a-2 plan, decision 11)."""
    if not names:
        return f'<option value="">{_e(none)}</option>'
    return "".join(f'<option value="{_e(name)}">{_e(name)}</option>' for name in names)


def _pf_state(frame: Telemetry | Idle | None) -> tuple[str, str]:
    """The pre-flight pill's tone and words (the mockup's `drawPreflight`), from the
    frame's pre-flight: a fail counts first, then the unknowns a person acknowledges --
    an item that is neither pass nor unknown counts as a fail, as `preflight.gate`
    counts it -- and outside a `wlx taskd` session between runs, why there is none."""
    if frame is None or isinstance(frame, Idle):
        return "neutral", "no session"
    if not frame.service:
        return "neutral", "pre-flight · wlx run takes none"
    if frame.phase == "running":
        return "neutral", "pre-flight · taken as the run started"
    if frame.phase != "between_runs":
        return "neutral", "pre-flight · the session has ended"
    if frame.preflight is None:
        return "neutral", "pre-flight · not taken"
    items = frame.preflight.items
    fails = sum(1 for item in items if item.result not in ("pass", "unknown"))
    unknown = sum(1 for item in items if item.result == "unknown")
    if fails:
        return "crit", f"pre-flight · {fails} fail"
    if unknown:
        return "warn", f"pre-flight · {unknown} to acknowledge"
    return "ok", "pre-flight ✓"


def _pf_sum(frame: Telemetry | Idle | None) -> str:
    """The Setup tab's pre-flight pill (the mockup's `pf-sum`)."""
    tone, said = _pf_state(frame)
    return f'<span class="pill {tone}">{_e(said)}</span>'


def _pf_pill(frame: Telemetry | Idle | None, view: View) -> str:
    """The control bar's pre-flight pill (the mockup's `pf-pill`): between runs, a button
    that takes the pre-flight for the task chosen and opens the Setup tab at its panel
    (the b3a-2 plan, decision 7); otherwise the words alone."""
    if isinstance(frame, Telemetry) and frame.service and frame.phase == "between_runs":
        tone, said = _pf_state(frame)
        off = _off(view) or ' title="take the pre-flight for the task chosen"'
        return (
            f'<button type="button" class="pill {tone}" data-cmd="check"{off}>'
            f"{_e(said)}</button>"
        )
    return _pf_sum(frame)


#: A result's dot (the mockup's `.st`): an unknown is what nothing measured, which the
#: mockup draws as the hollow *untested* ring; anything but pass or unknown is a fail.
_DOTS = {"pass": "pass", "unknown": "untested"}


def _pf_row(item, view: View) -> str:
    """One pre-flight item: its dot, name and sentence, and -- for an unknown -- the box
    that acknowledges it, carrying its exact name and never ticked here (decision 9)."""
    acknowledge = (
        f'<label class="chk"><input type="checkbox" data-ack="{_e(item.name)}" '
        f'aria-label="acknowledge {_e(item.name)}"{_off(view)}> acknowledge</label>'
        if item.result == "unknown"
        else "<span></span>"
    )
    return (
        f'<div class="row"><span class="st {_DOTS.get(item.result, "fail")}" '
        f'title="{_e(item.result)}"></span><span>{_e(item.name)}</span>'
        f'<span class="val">{_e(item.said)}</span>{acknowledge}</div>'
    )


def _preflight_pane(frame: Telemetry | Idle | None, view: View) -> str:
    """The Setup tab's pre-flight (the mockup's `pf-panel`, drawn from `wlx taskd`'s items
    rather than the mockup's list: spec §6.2): one row per item, under a line naming the
    task, S9a §10's rule and the unplanned warning. The mockup's *must* tag is left out,
    since every fail blocks (the b3a-2 plan, decision 6)."""
    if frame is None or isinstance(frame, Idle):
        return _NONE
    if not frame.service:
        return '<span class="nm">wlx run takes no pre-flight (XC-159)</span>'
    if frame.phase == "running":
        return (
            '<span class="nm">a run is in progress: its pre-flight was taken as it '
            "started, and its start row in runs.jsonl holds it</span>"
        )
    if frame.phase != "between_runs":
        return '<span class="nm">the session has ended: no run starts in it</span>'
    if frame.preflight is None:
        return (
            '<span class="nm">not taken: choose a task, or press the pre-flight '
            "pill</span>"
        )
    task = _e(frame.preflight.task)
    rows = "".join(_pf_row(item, view) for item in frame.preflight.items)
    return (
        f'<div class="sub">for {task} · a fail blocks the run; each unknown starts it only '
        f"on your acknowledgement, by name, written into runs.jsonl · {_e(UNPLANNED)}</div>"
        f'<div class="pf" data-task="{task}">{rows}</div>'
    )


# --- the controls (P4d-2b b2a) ------------------------------------------------------


def _hand_reward_now(frame: Telemetry) -> bool:
    """Whether the rig gives a manual reward now (`taskd.Session._manual_reward`): a run
    held paused (PI, 2026-09-28), or a `wlx taskd` session between runs or awaiting its
    animal's return (PI, 2026-09-29, spec §6.0). During a trial it waits on XC-157, and
    after a `wlx run` session's run on XC-184."""
    return frame.paused_at is not None or (
        frame.service and frame.phase in ("between_runs", "awaiting_return")
    )


def _reward_button(frame: Telemetry, view: View) -> str:
    """The manual reward's button (PI, 2026-09-28 and 2026-09-29): live whenever the rig
    gives one (`_hand_reward_now`), and greyed with `REWARD_ONLY_PAUSED` while a run's
    trials run, and with the §2 sentence away from the box. **One button and no key**:
    a click is one command, and the script holds the button until that command's
    answer."""
    live = _hand_reward_now(frame)
    off = _off(view) or ("" if live else f' disabled title="{_e(REWARD_ONLY_PAUSED)}"')
    return f'<button type="button" class="btn" data-cmd="reward"{off}>give reward</button>'


def _reward_answer(frame: Telemetry) -> str:
    """Beside a live *give reward*, what became of the last press (PI, 2026-09-28), from
    the frames the rig publishes: the session's fluid total, the newest reward given with
    its size and where, and the newest press refused with the rig's sentence -- *last*,
    since a refusal carries no time, as on a parameter card. Nothing while the button is
    greyed."""
    if not _hand_reward_now(frame):
        return ""
    said = [f"fluid session {frame.fluid_session_ml:.2f} mL"]
    given = [control for control in frame.controls if control.kind == "reward"]
    if given:
        said.append(f"last given {_clock_time(given[-1].at)}: {_e(given[-1].said)}")
    refused = [refusal for refusal in frame.refusals if refusal.name == "reward"]
    if refused:
        said.append(f"last refused: {_e(refused[-1].why)}")
    return f'<span class="nm">{" · ".join(said)}</span>'


def _mark_button(view: View) -> str:
    """*mark (M)*: greyed on its own when this console has no mark endpoint."""
    off = _off(view) or ("" if view.can_mark else f' disabled title="{_e(NO_MARK_ENDPOINT)}"')
    return f'<button type="button" class="btn" data-cmd="mark"{off}>mark (M)</button>'


def _start_button(frame: Telemetry, view: View) -> str:
    """*start run* (the mockup's `a-start`), carrying the task of the pre-flight the frame
    shows: the page's script sends that task, and only while it is the one chosen (the
    b3a-2 plan, decision 8). Greyed, with the reason, until a pre-flight is shown with no
    item failing (spec §6.2); `Service._start` takes the pre-flight again and refuses a
    start it would block anyway."""
    preflight = frame.preflight
    if preflight is None:
        why = "take the pre-flight first: choose a task, or press the pre-flight pill"
    else:
        failing = [i.name for i in preflight.items if i.result not in ("pass", "unknown")]
        why = f"pre-flight: {', '.join(failing)} failing" if failing else None
    task = "" if preflight is None else preflight.task
    off = _off(view) or ("" if why is None else f' disabled title="{_e(why)}"')
    return (
        f'<button type="button" class="btn go" data-cmd="start" data-task="{_e(task)}"'
        f"{off}>start run</button>"
    )


def _outside_a_run(frame: Telemetry, view: View) -> str:
    """A `wlx taskd` session between runs or awaiting its animal's return (spec §6.0,
    §6.2): *start run* between runs, with the unplanned warning beside it, and *give
    reward* and *mark* in both, since the rig gives a hand reward and stamps a mark
    outside a run (the b3a-2 plan, decision 13). Pause and stop have no run to act on."""
    # Concatenated, not an f-string: an apostrophe inside a replacement field of a
    # single-quoted f-string is a syntax error before Python 3.12, and 3.11 is supported.
    lead = (
        _start_button(frame, view) + '<span class="nm">' + _e(UNPLANNED) + "</span>"
        if frame.phase == "between_runs"
        else '<span class="nm">'
        + _e("session ended · waiting for the animal's return")
        + "</span>"
    )
    note = "" if view.can_write else f'<span class="nm">{CONTROLS_AT_THE_BOX}</span>'
    return lead + _reward_button(frame, view) + _mark_button(view) + _reward_answer(frame) + note


def _controls(frame: Telemetry | None, view: View) -> str:
    """Pause or resume, mark, give reward, and stop (spec §5.2), while a run runs; and,
    since P4d-2b b3a-2, *start run*, *give reward* and *mark* outside a run in a `wlx
    taskd` session (`_outside_a_run`).

    **Pause or resume by the session's state**, never a toggle: the page sends what
    the button says, and the click handler's `toggleAllowed` stops a double click
    from sending it twice, as `rewardAllowed` does for a reward (R2, 2026-09-28).
    **Stop run** (the mockup's `a-stop`; b2a's *stop…*) opens the page's confirm step.
    **Mark** is greyed on its own when this console has no mark endpoint, and **give
    reward** while trials run (`_reward_button`). **Everywhere but the box**, every
    control is greyed with the §2 sentence, which is also said beside them."""
    if frame is None:
        return '<span class="nm">controls · no session</span>'
    if frame.service and frame.phase in ("between_runs", "awaiting_return"):
        return _outside_a_run(frame, view)
    if frame.stop_kind is not None:
        return '<span class="nm">controls · the session has ended</span>'
    off = _off(view)
    cmd, label = ("resume", "resume (P)") if frame.paused_at is not None else ("pause", "pause (P)")
    note = "" if view.can_write else f'<span class="nm">{CONTROLS_AT_THE_BOX}</span>'
    return (
        f'<button type="button" class="btn" data-cmd="{cmd}"{off}>{label}</button>'
        f"{_mark_button(view)}"
        f"{_reward_button(frame, view)}"
        f'<button type="button" class="btn danger" data-cmd="stop"{off}>stop run</button>'
        f"{_reward_answer(frame)}{note}"
    )


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


def _health_pane(frame: Telemetry | Idle | None, view: View) -> str:
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
    """The changes feed (spec §5.2): staged changes first, then the control events --
    applied settings, pauses, resumes, marks and their notes, schedules -- newest
    first with when and who, then the refusals with the dropped-refusal count before
    them, as `cli.render` does."""
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
    for control in reversed(frame.controls):
        who = f" · {_e(control.by)}" if control.by else ""
        rows.append(
            f'<div class="ev ctl"><span class="kind">{_e(control.kind)}</span><span>'
            f"{_clock_time(control.at)} · {_e(control.said)}{who}</span></div>"
        )
    if frame.controls_dropped:
        rows.append(
            f'<div class="ev ctl"><span class="kind">earlier</span><span>'
            f"{_e(frame.controls_dropped)} earlier control event(s) not shown: only "
            f"the most recent {len(frame.controls)} are kept</span></div>"
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
    return "".join(rows) or '<span class="nm">nothing staged, controlled or refused</span>'


# --- task parameters, setup, end of session ----------------------------------------


def _significant(value: float) -> str:
    """A number's own significant decimals, never rounded away.

    `_num`'s two-decimal display would round a welfare ceiling's own figure short of
    what the arrows can still reach: a review of Task 10 (fix round 1) found a 0.125
    mL ceiling showed "0.12" while the arrows -- clamping to `[lo, hi]` before
    `toFixed` rounded the display -- could still send "0.13", over it. `f"{value:g}"`
    keeps every digit the value carries, trailing zeros stripped, for the magnitudes
    a bound uses here. Only the ceiling's own display changes; `_num` is unchanged
    everywhere else."""
    return f"{value:g}"


def _range(row) -> str:
    if row.bounded:
        return f"welfare ceiling {_e(_significant(row.high))} {_e(row.unit)}"
    if row.low is None and row.high is None:
        return "no declared range"
    return f"{_e(_edge(row.low))} to {_e(_edge(row.high))} {_e(row.unit)}"


#: The arrows' step by unit: the mockup's `stepOf` (`docs/superpowers/mockups/
#: 2026-09-26-console-mockup-v12.html`), in this repository's unit names -- the tasks
#: say `deg` where the mockup said `°`. A display choice, not a rule about values:
#: `Session.set` checks the range whatever step reached it.
_STEPS = {"mL": 0.01, "s": 0.05, "deg": 0.1}


def _step(row) -> float:
    return _STEPS.get(row.unit, 0.01)


def _field(row, view: View) -> str:
    """A card's input and arrows (spec §5.2). A number is shown at its step's
    decimals and carries the step and the declared range for the script's arrows,
    which clamp to it; a categorical value is a word, with no arrows. Greyed away
    from the box."""
    off = _off(view)
    name = _e(row.name)
    if isinstance(row.value, str):
        return (
            f'<span class="spin"><input class="field mono" data-param="{name}" '
            f'data-kind="word" value="{_e(row.value)}" aria-label="{name}"{off}></span>'
        )
    step = _step(row)
    places = len(f"{step:g}".partition(".")[2])
    value = "" if row.value is None else f"{row.value:.{places}f}"
    edges = "".join(
        f' data-{end}="{_e(edge)}"'
        for end, edge in (("min", row.low), ("max", row.high))
        if edge is not None
    )
    return (
        f'<span class="spin"><input class="field mono" data-param="{name}" '
        f'data-step="{step:g}"{edges} inputmode="decimal" value="{value}" '
        f'aria-label="{name}"{off}>'
        f'<span class="arrows"><button type="button" data-dir="1" tabindex="-1" '
        f'aria-label="increase {name}"{off}>▲</button>'
        f'<button type="button" data-dir="-1" tabindex="-1" '
        f'aria-label="decrease {name}"{off}>▼</button></span></span>'
    )


def _params(frame: Telemetry | None, view: View) -> str:
    """One card per `ParamRow`: value, unit, range, the ceiling flag, a staged
    marker, and -- P4d-2b b2a -- the input and arrows that set it and the last
    refusal of it with its sentence (spec §5.2: "A refusal shows on the card and in
    the feed"). *Last* is the word because a refusal carries no time: it stays on
    the card beside whatever the value has since become, and says it is the last."""
    if frame is None:
        return _NONE
    if not frame.params:
        return '<span class="nm">this task declares no parameters</span>'
    staged = {change.name: change for change in frame.staged}
    refused = {refusal.name: refusal for refusal in frame.refusals}
    cards = []
    for row in frame.params:
        change = staged.get(row.name)
        flag = '<span class="ceil">ceiling</span>' if row.bounded else ""
        mark = (
            ""
            if change is None
            else f'<span class="stg">staged → {_e(_num(change.now))} by {_e(change.by)}</span>'
        )
        refusal = refused.get(row.name)
        said = (
            ""
            if refusal is None
            else f'<span class="rfs">last refused: {_e(refusal.why)}</span>'
        )
        cls = "param staged" if change is not None else "param"
        cards.append(
            f'<div class="{cls}"><div class="pn"><span>{_e(row.name)}</span>{flag}</div>'
            f'<span class="pv">{_e(_num(row.value))} '
            f'<span class="unit">{_e(row.unit)}</span></span>'
            f"{_field(row, view)}"
            f'<span class="range">{_range(row)}</span>{mark}{said}</div>'
        )
    return "".join(cards)


def _setup(frame: Telemetry | None) -> str:
    """S9a §3's configuration information. Display mode is the setup the session runs
    in (direct-view spec §3); stimulus calibration has no source yet and says so."""
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
        ("task", '<span class="nm">no run yet</span>' if frame.task is None else _e(frame.task)),
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
        ("display mode", _e(_setup_words(frame.view, frame.half_ipd_cm))),
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
        else '<span class="nm">no run yet</span>'
        if frame.phase == "between_runs"
        else '<span class="nm">still running</span>'
    )
    return (
        f'<div class="owe"><h2>Supplement owed</h2>{owed}</div>'
        f'<dl class="dl"><dt>fluid session</dt><dd>{frame.fluid_session_ml:.2f} mL</dd>'
        f"<dt>out of cage</dt><dd>{cage}</dd>"
        f"<dt>in session</dt><dd>{in_session}</dd>"
        f"<dt>stop reason</dt><dd>{reason}</dd></dl>"
    )


def _question_banner(question: Question, view: View) -> str:
    """The answer a console owes on a far mark (P4d-2b spec §6.2), with a button for each
    of the frame's own answers, naming its mark and session: the page's script re-sends
    the time as typed with the one pressed, and only for a question this page raised
    (the b3a-2 plan, decision 10). Greyed away from the box."""
    buttons = "".join(
        f'<button type="button" class="btn small" data-answer="{_e(answer)}" '
        f'data-mark="{_e(question.mark)}" data-session="{_e(question.session_id)}"'
        f'{_off(view)}>{_e(answer)}{"…" if answer == "amend" else ""}</button>'
        for answer in question.answers
    )
    return _banner(
        "warn",
        "Confirm",
        f"{_e(question.said)} · answer "
        f"{' or '.join(_e(answer) for answer in question.answers)} "
        f"(session {_e(question.session_id)}) {buttons}",
    )


def _new_session_button(view: View, why: str | None = None) -> str:
    """*new session* (the mockup's `a-new`): opens the page's *New session* dialog."""
    off = _off(view) or ("" if why is None else f' disabled title="{_e(why)}"')
    return f'<button type="button" class="btn small primary" data-cmd="new"{off}>new session</button>'


def _idle_banners(frame: Idle, view: View) -> str:
    """A refused frame, then every stranded animal -- each with *end session…*, which
    takes its return naming its session (XC-176) -- then a question owed, then, with no
    animal stranded, *no session open* beside *new session* (spec §6.1). A stranded
    departure is given as this host's local date, minute and zone, as the terminal gives
    it (`cli._moment`): an animal out since days ago must not read as since this morning
    (the b3a-1 final review, Minor 1). A record that cannot be read has no button: it is
    repaired by hand first."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    for found in frame.stranded:
        if found.left_at is None:
            text = (
                f"session {_e(found.session_id)}: its welfare record cannot be read, so its "
                f"animal's return cannot be checked; no session opens until the file is "
                f"repaired and the return recorded"
            )
        else:
            text = (
                f"{_e(found.subject)} left its cage at {_e(_moment(found.left_at))} in "
                f"session {_e(found.session_id)}, and its return is not recorded; no "
                f"session opens until it is "
                f'<button type="button" class="btn small danger" '
                f'data-return="{_e(found.session_id)}"{_off(view)}>end session…</button>'
            )
        out.append(_banner("crit", "Stranded", text))
    if frame.question is not None:
        out.append(_question_banner(frame.question, view))
    if not frame.stranded:
        out.append(_banner("info", "Idle", f"no session open {_new_session_button(view)}"))
    return "".join(out)


def _idle_setup(frame: Idle, view: View) -> str:
    """The Session panel with no session open (the mockup's Setup tab): *new session*,
    greyed while an animal is stranded, and what `wlx taskd` offers a session."""
    why = (
        "an animal's return is not recorded: end its session from its Stranded banner first"
        if frame.stranded
        else None
    )
    rows = (
        ("animals", ", ".join(frame.animals) or "none: no folder under --subjects holds a bounds.py"),
        ("tasks offered", ", ".join(frame.offered_tasks) or "none: no task file under --tasks"),
    )
    return (
        f'<div class="selrow">{_new_session_button(view, why)}</div><dl class="dl">'
        + "".join(f"<dt>{name}</dt><dd>{_e(value)}</dd>" for name, value in rows)
        + "</dl>"
    )


def _end_actions(frame: Telemetry | Idle | None, view: View) -> str:
    """The Summary's pill and *end session* (the mockup's `end-pill`, `a-end`) while a
    `wlx taskd` session is open -- during a run too, which it stops first -- and, once it
    has ended, *record return…*, the second step (the b3a-2 plan, decision 12). A `wlx
    run` session's return is taken at its terminal, so its pill stands alone."""
    if frame is None or isinstance(frame, Idle):
        return '<span class="pill neutral">none</span>'
    session = _e(frame.session_id)
    if not frame.service:
        return f'<span class="pill neutral">{"open" if frame.stop_kind is None else "ended"}</span>'
    if frame.phase in ("between_runs", "running"):
        return (
            '<span class="pill neutral">open</span><button type="button" class="btn small '
            f'danger" data-cmd="end" data-session="{session}"{_off(view)}>end session</button>'
        )
    if frame.phase == "awaiting_return":
        return (
            '<span class="pill warn">ended · awaiting the return</span><button type="button" '
            f'class="btn small danger" data-return="{session}"{_off(view)}>record return…</button>'
        )
    return '<span class="pill ok">ended</span>'


def _idle_refusals(frame: Idle) -> str:
    rows = []
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
    return "".join(rows) or '<span class="nm">nothing refused</span>'


def _idle(frame: Idle, view: View) -> dict[str, str]:
    """The page while `wlx taskd` has no session open (P4d-2b spec §6.1: "the page shows
    *no session open* beside the form that opens one"): every pane as before any frame,
    except the pill, the header, the banners, the controls, *wl-works sees* (`/health`
    as it would be sent for this frame, stranded animals included), the refusals, the
    tasks offered, the Session panel and the dialog's animals."""
    panes = fragments(None, view)
    panes["state"] = '<span class="pill neutral" data-state="idle">no session open</span>'
    panes["head-id"] = '<span class="nm">no session open</span>'
    panes["banners"] = _idle_banners(frame, view)
    panes["controls"] = '<span class="nm">controls · no session open</span>'
    panes["rt-health"] = _health_pane(frame, view)
    panes["rt-changes"] = _idle_refusals(frame)
    panes["task-sel"] = _options(frame.offered_tasks, "no task offered")
    panes["setup"] = _idle_setup(frame, view)
    panes["dn-subject"] = _options(frame.animals, "no animal offered")
    return panes


def fragments(frame: Telemetry | Idle | None, view: View) -> dict[str, str]:
    """Every pane of the page for one frame, keyed by the id of the element each one
    fills (`FRAGMENT_IDS`, in that order). `frame` is `None` before any has arrived,
    and every pane then says so; an `Idle` is `wlx taskd` with no session open."""
    if isinstance(frame, Idle):
        return _idle(frame, view)
    return {
        "state": _state(frame),
        "head-id": _head(frame),
        "presence": _presence(view),
        "strip": _strip(frame, view),
        "banners": _banners(frame, view),
        "task-sel": _options(() if frame is None else frame.offered_tasks, "no task offered"),
        "pf-pill": _pf_pill(frame, view),
        "controls": _controls(frame, view),
        "rt-trials": _trials(frame),
        "rt-work": _work(frame),
        "rt-need": _need(frame),
        "rt-wrong": _wrong(frame),
        "rt-health": _health_pane(frame, view),
        "rt-changes": _changes(frame),
        "params": _params(frame, view),
        "pf-sum": _pf_sum(frame),
        "preflight": _preflight_pane(frame, view),
        "setup": _setup(frame),
        "end-actions": _end_actions(frame, view),
        "end": _end(frame),
        "dn-subject": _options((), "no animal offered"),
    }


# --- the page -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Font:
    """One face the page uses: bundled at `wl_xcon/fonts/<directory>/<file>`
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
        resources.files("wl_xcon")
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
.controlbar { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; padding: 6px 12px; }
.ctlrow { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
.controlbar .spacer { flex: 1; }
.btn.small { padding: 2px 8px; font-size: 12.5px; }
.btn.danger { border-color: var(--crit); color: var(--crit); }
.btn:disabled, .field:disabled, .arrows button:disabled, select:disabled { opacity: 0.45; cursor: not-allowed; }
.who { font-size: 12.5px; color: var(--muted); }
.who b { color: var(--ink); font-weight: 600; }
.sent { font-size: 12.5px; }
.sent.ok { color: var(--ok); } .sent.crit { color: var(--crit); }
.inline { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; padding: 6px 12px; border-radius: 6px; font-size: 13px; background: var(--surface-2); }
.inline.crit { background: var(--crit-soft); } .inline.info { background: var(--accent-soft); }
.inline input, .inline select { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--rule); border-radius: 3px; padding: 1px 4px; }
#mark-note { width: min(34em, 60vw); }
#sched-value { width: 7em; }
.spin { display: inline-flex; align-items: stretch; }
.field { width: 6em; border: 1px solid var(--rule); border-radius: 3px 0 0 3px; padding: 1px 4px; background: var(--surface); color: inherit; font-size: 12.5px; }
.field[data-kind="word"] { border-radius: 3px; }
.field.pending { border-color: var(--accent); }
.arrows { display: flex; flex-direction: column; border: 1px solid var(--rule); border-left: 0; border-radius: 0 3px 3px 0; overflow: hidden; }
.arrows button { flex: 1; width: 18px; border: 0; padding: 0; background: var(--surface-2); color: var(--muted); cursor: pointer; font-size: 8px; line-height: 1; }
.arrows button + button { border-top: 1px solid var(--rule); }
.param .rfs { font-size: 11.5px; color: var(--crit); }
.ev.ctl .kind { color: var(--accent); }
.controlbar .sep { width: 1px; align-self: stretch; background: var(--rule); margin: 0 4px; }
.tsel { display: inline-flex; align-items: center; gap: 6px; }
.tsel .k { font-family: var(--cond); font-weight: 600; font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.tsel select { font-family: var(--mono); font-size: 13.5px; padding: 4px 6px; }
.tsel .field { width: 5em; border-radius: 3px; }
button.pill { border: 0; cursor: pointer; }
.btn.go { background: var(--ok); border-color: var(--ok); color: var(--bg); }
.pf { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 0 20px; }
.pf .row { display: grid; grid-template-columns: 12px minmax(0, 10em) minmax(0, 1fr) auto; gap: 8px; align-items: center; font-size: 13px; padding: 3px 0; border-bottom: 1px solid var(--rule); min-height: 30px; }
.pf .val { font-family: var(--mono); font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
.st { width: 10px; height: 10px; border-radius: 50%; }
.st.pass { background: var(--ok); } .st.warn { background: var(--warn); } .st.fail { background: var(--crit); } .st.untested { box-shadow: inset 0 0 0 1.5px var(--muted); }
.chk { display: flex; gap: 8px; align-items: center; font-size: 13px; }
.dialog .grid { display: grid; grid-template-columns: auto 1fr; gap: 8px 12px; align-items: center; }
.dialog .end { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.dialog .field, .dialog select { width: 100%; border-radius: 3px; font: inherit; }
#amend-to, #end-return, #ret-at { width: 13em; }
#amend-why { width: min(28em, 50vw); }
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

#: **The page's whole script, and all it does** (spec §4.3, §4.4, and since P4d-2b
#: b2a §5.2): open the event stream, swap each fragment into the element with its id,
#: run the stale timer while more frames are due, close the stream on the ✕, and
#: reconnect -- and, from b2a, send the controls as JSON `POST`s to `/commands`,
#: debounce the parameter arrows, handle the **P** and **M** keys, and ask for the
#: operator's name. `EventSource` reconnects on its own after a dropped connection,
#: and `wlx serve` sends a full render first on every new stream, so a reconnect
#: re-renders in full. **It still renders nothing itself**: every `innerHTML` it
#: writes is a fragment `wlx serve` rendered, and what it writes of its own -- the
#: name and the last command's answer -- goes in as `textContent`.
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
#:
#: **The controls (P4d-2b b2a).** Only the box's own page may write (`data-can-write`
#: on `<body>`, from `View.can_write`); elsewhere every control is disabled in the
#: HTML and `post` sends nothing. The name is asked once, kept in `localStorage` --
#: inside `try`, since a private window may refuse it -- and a prompt refused or
#: cleared sends nothing. An arrow steps its input and the change is sent
#: `debounceMs` after the last click; while an input has focus or a change is
#: pending, a new parameters fragment is held and swapped in afterwards, so a frame
#: never replaces an input under a person's hands. P and M do nothing in a text box
#: or when held. A mark sends its signal at once with `pressed_at` -- the browser's
#: clock, and the only `Date.now()` here -- then opens the note box: Enter attaches
#: the note, Esc leaves the mark bare, and a second mark leaves the first bare.
#:
#: **Sessions from the page (P4d-2b b3a-2).** Choosing a task, or pressing the pre-flight
#: pill, takes the pre-flight (`check`); *start run* sends the task of the pre-flight
#: shown, the trial count and the unknown items ticked, then clears the ticks; *new
#: session* sends the dialog's fields as typed; *end session* sends the return typed, or
#: none for later; a warning's *confirm* or *amend* re-sends the open or the return this
#: page sent, with its answer, and a warning this page did not raise is not answered.
#: A swap keeps a select's chosen option and the ticks. It still renders nothing itself.
_SCRIPT = """
(function () {
  "use strict";
  var body = document.body;
  var staleMs = Number(body.getAttribute("data-stale-after")) * 1000;
  var canWrite = body.getAttribute("data-can-write") === "1";
  var debounceMs = Number(body.getAttribute("data-debounce-ms"));
  var NAME_KEY = "wlx-console-name";
  // Housekeeping -- a double click's span with margin -- not a measurement: keeps a
  // double click, or a re-render's fresh button under the second click of one, from
  // toggling a pause or resume the first click already sent (spec §5.2: "never a
  // toggle").
  var TOGGLE_HOLD_MS = 1000;
  var lastToggleAt = -Infinity;
  var source = null;
  var baseline = null;
  var live = false;
  var lost = false;
  var closed = false;
  var timers = {};
  var heldParams = null;
  var markNo = null;
  var rewarding = false;
  var REWARD_LOST = "unknown: this page lost wlx serve's answer, so whether the reward was given is not known, and it was not sent again; check the session's fluid total before pressing again";
  // Housekeeping, not a measurement (R2, 2026-09-28): the same double click's span as
  // TOGGLE_HOLD_MS, since a reward's answer can return well inside it on loopback,
  // leaving the button live again before a double click's second click lands.
  var REWARD_HOLD_MS = 1000;
  var lastRewardAt = -Infinity;
  // P4d-2b b3a-2 (spec §6.2). The last open and the last return this page sent, kept so
  // an answer to the warning they raise re-sends the same typed time with it -- the rig
  // takes an answer only for the time it asked about (`service._unasked`); the unknown
  // pre-flight items ticked, by name, for the run about to start, cleared whenever a
  // pre-flight is asked for or a run started, so no tick outlives the run it was for;
  // and the session the return form is for.
  var lastOpen = null;
  var lastEnd = null;
  var acked = {};
  var returnFor = null;
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
  function busy() {
    var focused = document.activeElement;
    return Boolean(focused && focused.closest && focused.closest("#params")) ||
      Object.keys(timers).length > 0;
  }
  function swap(id, html) {
    if (id === "params" && busy()) { heldParams = html; return; }
    var node = el(id);
    var chosen = node && node.tagName === "SELECT" ? node.value : null;
    if (node) { node.innerHTML = html; }
    if (chosen !== null) { choose(node, chosen); }
    if (id === "controls") { holdReward(); }
    if (id === "preflight") { restoreAcks(); }
  }
  function release() {
    if (heldParams !== null && !busy()) {
      el("params").innerHTML = heldParams;
      heldParams = null;
    }
  }
  function choose(select, value) {
    // A frame re-renders a select's options; the option a person chose stays chosen
    // while it is still offered (the b3a-2 plan, decision 11).
    Array.prototype.forEach.call(select.options, function (option) {
      if (option.value === value) { select.value = value; }
    });
  }
  function restoreAcks() {
    Array.prototype.forEach.call(document.querySelectorAll("input[data-ack]"), function (box) {
      box.checked = acked[box.getAttribute("data-ack")] === true;
    });
  }
  function onFrame(event) {
    var payload = JSON.parse(event.data);
    Object.keys(payload.frags).forEach(function (id) { swap(id, payload.frags[id]); });
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
  function storedName() {
    try { return window.localStorage.getItem(NAME_KEY) || ""; } catch (e) { return ""; }
  }
  var name = storedName();
  function showName() {
    el("who").textContent = name ? name + " (box, unverified)" : "not given yet";
  }
  function askName() {
    var given = window.prompt("Your name, for the session record:", name);
    if (given === null) { return ""; }
    given = given.trim();
    if (!given) { return ""; }
    name = given;
    try { window.localStorage.setItem(NAME_KEY, given); } catch (e) { /* kept for this page only */ }
    showName();
    return given;
  }
  function tell(text, tone) {
    var line = el("sent");
    line.textContent = text;
    line.className = "sent " + (tone || "");
  }
  function post(command, then, after) {
    var done = after || function () {};
    if (!canWrite) { done(); return; }
    var by = name || askName();
    if (!by) {
      tell("not sent: give your name first -- every command records who sent it", "crit");
      done();
      return;
    }
    command.by = by;
    tell("sending…", "");
    fetch("/commands", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command),
      cache: "no-store"
    }).then(function (response) {
      return response.json();
    }).then(function (answer) {
      tell(answer.said, answer.status === "sent" || answer.status === "signaled" ? "ok" : "crit");
      if (then) { then(answer); }
    }).catch(function () {
      tell(command.kind === "reward" ? REWARD_LOST : "not delivered: this page could not reach wlx serve", "crit");
    }).then(done);
  }
  function decimals(step) { return (String(step).split(".")[1] || "").length; }
  function send(input) {
    input.classList.remove("pending");
    var key = input.getAttribute("data-param");
    var raw = input.value.trim();
    var word = input.getAttribute("data-kind") === "word";
    var value = word ? raw : Number(raw);
    if (!word && (raw === "" || !isFinite(value))) {
      tell("not sent: " + key + " needs a number", "crit");
    } else {
      post({ kind: "set", name: key, value: value });
    }
    release();
  }
  function schedule(input) {
    var key = input.getAttribute("data-param");
    clearTimeout(timers[key]);
    input.classList.add("pending");
    timers[key] = setTimeout(function () { delete timers[key]; send(input); }, debounceMs);
  }
  function stepInput(input, dir) {
    var step = Number(input.getAttribute("data-step")) || 0.01;
    var lo = input.hasAttribute("data-min") ? Number(input.getAttribute("data-min")) : -Infinity;
    var hi = input.hasAttribute("data-max") ? Number(input.getAttribute("data-max")) : Infinity;
    var v = Number(input.value);
    if (input.value.trim() === "" || !isFinite(v)) { v = isFinite(lo) ? lo : 0; }
    // Round to the step first, then clamp -- and on a clamp, write the edge's own
    // attribute string exactly, never `toFixed` it again: `toFixed` rounding a
    // clamped value at the step's decimals could still overshoot a ceiling with
    // more of its own (0.125 mL rounded to "0.13" at a 0.01 step).
    v = Math.round((v + dir * step) / step) * step;
    if (v <= lo) { input.value = input.getAttribute("data-min"); }
    else if (v >= hi) { input.value = input.getAttribute("data-max"); }
    else { input.value = v.toFixed(decimals(step)); }
    schedule(input);
  }
  function closeNote(note) {
    if (markNo === null) { return; }
    var number = markNo;
    markNo = null;
    el("mark-form").hidden = true;
    post({ kind: "note", mark: number, note: note });
  }
  function mark() {
    var button = el("controls").querySelector('[data-cmd="mark"]');
    if (!button || button.disabled) { return; }
    closeNote("");
    post({ kind: "mark", pressed_at: Date.now() / 1000 }, function (answer) {
      if (answer.status !== "signaled") { return; }
      markNo = answer.mark;
      el("mark-note").value = "";
      el("mark-form").hidden = false;
      el("mark-note").focus();
    });
  }
  function toggleAllowed(detail) {
    // The same hold, whichever route a pause or resume comes from (round 2: the
    // click handler alone missed the P key, which calls this before `command` too).
    var now = performance.now();
    if (detail > 1 || now - lastToggleAt < TOGGLE_HOLD_MS) { return false; }
    lastToggleAt = now;
    return true;
  }
  function holdReward() {
    var button = el("controls").querySelector('[data-cmd="reward"]');
    if (rewarding && button && !button.disabled) {
      button.disabled = true;
      button.setAttribute("data-held", "1");
    }
  }
  function reward() {
    var button = el("controls").querySelector('[data-cmd="reward"]');
    if (!button || button.disabled || rewarding) { return; }
    rewarding = true;
    holdReward();
    post({ kind: "reward" }, null, function () {
      rewarding = false;
      var held = el("controls").querySelector('[data-cmd="reward"][data-held]');
      if (held) { held.removeAttribute("data-held"); held.disabled = false; }
    });
  }
  // P4d-2b b3a-2 (spec §6.2): a run, a session and the two marks, from the page. Every
  // field is a static element no frame replaces; each form sends one command through
  // `post`, the one `fetch`, which adds who sent it.
  function chosenTask() { return el("task-sel").value; }
  function takePreflight(showPanel) {
    var task = chosenTask();
    acked = {};
    if (!task) { tell("not sent: no task is offered to check", "crit"); return; }
    post({ kind: "check", task: task, values: {} });
    if (showPanel) { el("t-setup").checked = true; }
  }
  function startRun() {
    var button = el("controls").querySelector('[data-cmd="start"]');
    var task = button ? button.getAttribute("data-task") : "";
    var trials = Number(el("run-trials").value.trim());
    if (!task || task !== chosenTask()) {
      tell("not sent: the pre-flight shown is not for the task chosen; take its pre-flight first (the pre-flight pill)", "crit");
      return;
    }
    if (!Number.isInteger(trials) || trials < 1) {
      tell("not sent: a run's trials are a whole number from 1", "crit");
      return;
    }
    var acknowledged = [];
    Array.prototype.forEach.call(document.querySelectorAll("input[data-ack]"), function (box) {
      if (box.checked) { acknowledged.push(box.getAttribute("data-ack")); }
    });
    acked = {};
    restoreAcks();
    post({ kind: "start", task: task, values: {}, trials: trials, acknowledged: acknowledged });
  }
  function openNew() {
    el("dn-msg").textContent = "";
    el("dlg-new").hidden = false;
    el("dn-subject").focus();
  }
  function openSession() {
    var given = el("dn-given").value.trim();
    var today = given === "" ? null : Number(given);
    if (today !== null && !isFinite(today)) {
      el("dn-msg").textContent = "not sent: the fluid given today is mL, or blank when it is not known";
      return;
    }
    var request = {
      kind: "open",
      session_id: el("dn-id").value.trim(),
      animal: el("dn-subject").value,
      deployment: el("dn-deployment").value,
      view: el("dn-view").value,
      departure: el("dn-left").value.trim(),
      delivered_today: today,
      answer: null,
      amend_to: null,
      amend_reason: ""
    };
    lastOpen = Object.assign({}, request);
    post(request, function (answer) {
      el("dn-msg").textContent = answer.said;
      if (answer.status === "sent") { el("dlg-new").hidden = true; }
    });
  }
  function askEnd() {
    el("end-return").value = "";
    el("end-confirm").hidden = false;
    el("end-return").focus();
  }
  function openReturn(session) {
    returnFor = session;
    el("ret-session").textContent = session;
    el("ret-at").value = "";
    el("return-form").hidden = false;
    el("t-end").checked = true;
    el("ret-at").focus();
  }
  function answerWarning(button) {
    var given = button.getAttribute("data-answer");
    var which = button.getAttribute("data-mark");
    var session = button.getAttribute("data-session");
    if (given === "re-type") { openReturn(session); return; }
    var sent = which === "departure" ? lastOpen : lastEnd;
    if (!sent || sent.session_id !== session) {
      tell("not sent: this page did not send the " + which + " this warning is about, so it cannot answer it; send the time again, then answer the warning it raises", "crit");
      return;
    }
    if (given === "amend") {
      el("amend-to").value = "";
      el("amend-why").value = "";
      el("amend-form").hidden = false;
      el("amend-to").focus();
    } else if (given === "confirm") {
      post(which === "departure" ? Object.assign({}, sent, { answer: "confirm" }) : Object.assign({}, sent, { confirm: true }));
    }
  }
  function command(cmd) {
    if (cmd === "stop") { el("stop-confirm").hidden = false; }
    else if (cmd === "mark") { mark(); }
    else if (cmd === "reward") { reward(); }
    else if (cmd === "new") { openNew(); }
    else if (cmd === "check") { takePreflight(true); }
    else if (cmd === "start") { startRun(); }
    else if (cmd === "end") { askEnd(); }
    else { post({ kind: cmd }); }
  }
  function rewardAllowed(detail) {
    // Same reasoning as `toggleAllowed` (R2, 2026-09-28): loopback's round trip can
    // return well inside a double click's span, so the disabled-until-answered rule
    // in `reward` alone can miss the second click.
    var now = performance.now();
    if (detail > 1 || now - lastRewardAt < REWARD_HOLD_MS) { return false; }
    lastRewardAt = now;
    return true;
  }
  function pauseOrResume() {
    var button = el("controls").querySelector('[data-cmd="pause"], [data-cmd="resume"]');
    // No click to read a detail from a key press, so 1 -- never a double on its own,
    // still held to the same `TOGGLE_HOLD_MS` as a click.
    if (button && !button.disabled && toggleAllowed(1)) {
      command(button.getAttribute("data-cmd"));
    }
  }
  document.addEventListener("click", function (e) {
    if (!e.target.closest) { return; }
    var answering = e.target.closest("[data-answer]");
    if (answering && !answering.disabled) { answerWarning(answering); return; }
    var returning = e.target.closest("[data-return]");
    if (returning && !returning.disabled) { openReturn(returning.getAttribute("data-return")); return; }
    var button = e.target.closest("[data-cmd]");
    if (button && !button.disabled) {
      var cmd = button.getAttribute("data-cmd");
      if ((cmd === "pause" || cmd === "resume") && !toggleAllowed(e.detail)) { return; }
      if (cmd === "reward" && !rewardAllowed(e.detail)) { return; }
      command(cmd);
      return;
    }
    var arrow = e.target.closest("[data-dir]");
    if (arrow && !arrow.disabled) {
      var input = arrow.closest(".spin").querySelector("input[data-param]");
      if (input && !input.disabled) { stepInput(input, Number(arrow.getAttribute("data-dir"))); }
    }
  });
  document.addEventListener("change", function (e) {
    if (!e.target.matches) { return; }
    if (e.target.matches("input[data-param]")) { schedule(e.target); }
    else if (e.target.matches("input[data-ack]")) { acked[e.target.getAttribute("data-ack")] = e.target.checked; }
    else if (e.target.id === "task-sel") { takePreflight(false); }
  });
  document.addEventListener("focusout", function () { setTimeout(release, 0); });
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) { return; }
    var t = e.target;
    if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) { return; }
    var k = e.key.toLowerCase();
    if (k === "p") { e.preventDefault(); pauseOrResume(); }
    else if (k === "m") { e.preventDefault(); mark(); }
  });
  el("mark-note").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); closeNote(el("mark-note").value.trim()); }
    else if (e.key === "Escape") { e.preventDefault(); closeNote(""); }
  });
  el("stop-yes").addEventListener("click", function () {
    el("stop-confirm").hidden = true;
    post({ kind: "stop" });
  });
  el("stop-no").addEventListener("click", function () { el("stop-confirm").hidden = true; });
  el("rename").addEventListener("click", function () { askName(); });
  el("sched-set").addEventListener("click", function () {
    var kind = el("sched-kind").value;
    var raw = el("sched-value").value.trim();
    var request = { kind: "schedule" };
    if (kind === "clock") { request.at = raw; }
    else if (kind === "trials") { request.trials = Number(raw); }
    else { request.ml = Number(raw); }
    post(request);
  });
  el("dn-ok").addEventListener("click", openSession);
  el("dn-cancel").addEventListener("click", function () { el("dlg-new").hidden = true; });
  el("dlg-new").addEventListener("keydown", function (e) {
    if (e.key === "Escape") { el("dlg-new").hidden = true; }
  });
  el("end-yes").addEventListener("click", function () {
    var button = el("end-actions").querySelector('[data-cmd="end"]');
    var returned = el("end-return").value.trim();
    el("end-confirm").hidden = true;
    if (!button) { tell("not sent: no session is open to end", "crit"); return; }
    var request = { kind: "end", session_id: button.getAttribute("data-session"), returned: returned === "" ? null : returned, confirm: false };
    if (returned !== "") { lastEnd = Object.assign({}, request); }
    post(request);
  });
  el("end-no").addEventListener("click", function () { el("end-confirm").hidden = true; });
  el("ret-yes").addEventListener("click", function () {
    var returned = el("ret-at").value.trim();
    if (!returned) { tell("not sent: give the time the animal went back into its home cage, or now", "crit"); return; }
    var request = { kind: "end", session_id: returnFor, returned: returned, confirm: false };
    el("return-form").hidden = true;
    lastEnd = Object.assign({}, request);
    post(request);
  });
  el("ret-no").addEventListener("click", function () { el("return-form").hidden = true; });
  el("amend-yes").addEventListener("click", function () {
    el("amend-form").hidden = true;
    if (!lastOpen) { tell("not sent: this page sent no departure to amend", "crit"); return; }
    post(Object.assign({}, lastOpen, { answer: "amend", amend_to: el("amend-to").value.trim(), amend_reason: el("amend-why").value.trim() }));
  });
  el("amend-no").addEventListener("click", function () { el("amend-form").hidden = true; });
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
  showName();
  open();
})();
"""


def page(
    parts: dict[str, str], *, stale_after_s: float, nonce: str, can_write: bool = False
) -> str:
    """The whole document, every pane already rendered into it, so it reads before
    its stream has opened (spec §4.3).

    `parts` is `fragments(...)`; each fills the element whose id is its key, the id
    the stream's events swap by. A missing key raises `KeyError`: a page with a pane
    left blank is a bug to see, not a page to serve. `nonce` is the one in the
    Content-Security-Policy `wlx serve` sends with this response; the one script
    carries it. `stale_after_s` goes to the script as `data-stale-after`.

    **The controls (P4d-2b b2a, spec §5.2)**: the control bar's buttons are the
    `controls` fragment, and around it are the parts no frame changes -- the name,
    the last command's answer, the stop confirm, the mark's note box and the
    scheduled-stop form -- static, so a frame never replaces what a person is typing.
    `can_write` is `View.can_write` for the browser this page is for: `False`
    disables those static controls here and tells the script (`data-can-write`); the
    fragments grey their own. Close and reconnect, and the tab radios, are b1's.
    **The session forms (P4d-2b b3a-2)**: the *New session* dialog, the end
    confirmation, the return and the amendment are static too, and so is the run's
    trial count; only the task and subject selects' options are fragments (the b3a-2
    plan, decision 11).
    """
    p = {key: parts[key] for key in FRAGMENT_IDS}
    off = "" if can_write else f' disabled title="{_e(CONTROLS_AT_THE_BOX)}"'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>xcon console</title>
<style>{_FONT_FACES}{_CSS}</style>
</head>
<body data-stale-after="{stale_after_s:g}" data-can-write="{int(can_write)}" data-debounce-ms="{DEBOUNCE_MS}">
<div class="wrap">
  <header class="head glass">
    <span class="logo">{_LOGO}<span class="app">xcon</span></span>
    <span id="state">{p['state']}</span>
    <div class="id" id="head-id">{p['head-id']}</div>
    <span class="spacer"></span>
    <span class="presence" id="presence">{p['presence']}</span>
    <button class="xbtn" id="close" type="button" aria-label="close this page's stream" title="close this page's stream · the session keeps running on the box"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
  </header>
  <div class="strip glass" role="region" aria-label="animal" id="strip">{p['strip']}</div>
  <div class="banner" id="stream" role="status" hidden></div>
  <div class="banners" id="banners">{p['banners']}</div>
  <div class="inline info" id="amend-form" role="dialog" aria-label="amend the departure" hidden><span>amend the departure · the corrected time</span><input id="amend-to" autocomplete="off" placeholder="HH:MM, or 2027-01-13T22:40" aria-label="the corrected departure"{off}><span>why</span><input id="amend-why" maxlength="500" autocomplete="off" aria-label="why it is amended"{off}><span class="nm">your name is recorded with it</span><button class="btn small primary" id="amend-yes" type="button"{off}>send amendment</button><button class="btn small" id="amend-no" type="button">cancel</button></div>
  <section class="controlbar glass" aria-label="controls">
    <label class="tsel" for="task-sel"><span class="k">Task</span><select id="task-sel" aria-label="task"{off}>{p['task-sel']}</select></label>
    <label class="tsel" for="run-trials"><span class="k">Trials</span><input class="field mono" id="run-trials" value="{RUN_TRIALS}" inputmode="numeric" autocomplete="off" aria-label="trials"{off}></label>
    <span id="pf-pill">{p['pf-pill']}</span>
    <span class="sep" aria-hidden="true"></span>
    <div class="ctlrow" id="controls">{p['controls']}</div>
    <span class="spacer"></span>
    <span class="who">name <b id="who">not given yet</b> <button class="btn small" id="rename" type="button"{off}>change</button></span>
    <span class="sent" id="sent" role="status"></span>
  </section>
  <div class="inline crit" id="stop-confirm" role="alertdialog" aria-label="confirm stop" hidden><span>stop at a trial boundary, after any commands already sent?</span><button class="btn danger" id="stop-yes" type="button">stop</button><button class="btn" id="stop-no" type="button">cancel</button></div>
  <div class="inline info" id="mark-form" role="dialog" aria-label="mark note" hidden><span>mark sent · note</span><input id="mark-note" maxlength="500" autocomplete="off" placeholder="Enter attaches it · Esc leaves the mark bare" aria-label="mark note"></div>
  <div class="inline" id="sched-form"><span>scheduled stop</span><select id="sched-kind" aria-label="stop when"{off}><option value="clock">at HH:MM</option><option value="trials">after N more trials</option><option value="fluid">after mL this session</option></select><input id="sched-value" autocomplete="off" aria-label="stop at"{off}><button class="btn small" id="sched-set" type="button"{off}>set</button></div>
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
        <div class="tabpanel" id="tp-task"><section class="panel glass"><div class="top"><h2>Task parameters</h2><span class="sub">staged until the next trial</span></div><div class="params" id="params">{p['params']}</div></section></div>
        <div class="tabpanel" id="tp-setup">
          <section class="panel glass" id="pf-panel"><div class="top"><h2>Pre-flight</h2><span id="pf-sum">{p['pf-sum']}</span></div><div id="preflight">{p['preflight']}</div></section>
          <section class="panel glass"><div class="top"><h2>Session</h2></div><div id="setup">{p['setup']}</div></section>
        </div>
        <div class="tabpanel" id="tp-end"><section class="panel glass"><div class="top"><h2>Summary</h2><div class="selrow" id="end-actions">{p['end-actions']}</div></div>
          <div class="inline crit" id="end-confirm" role="alertdialog" aria-label="confirm end session" hidden><span>{_e(END_CONFIRM)}</span><span>→cage at</span><input id="end-return" autocomplete="off" placeholder="now, HH:MM, or blank for later" aria-label="the return to the home cage"{off}><button class="btn small danger" id="end-yes" type="button"{off}>end session</button><button class="btn small" id="end-no" type="button">cancel</button></div>
          <div class="inline info" id="return-form" role="dialog" aria-label="the return to the home cage" hidden><span>the return to the home cage · session <b class="mono" id="ret-session"></b> · →cage at</span><input id="ret-at" autocomplete="off" placeholder="now, HH:MM, or 2027-01-13T22:40" aria-label="the return to the home cage"{off}><button class="btn small primary" id="ret-yes" type="button"{off}>record return</button><button class="btn small" id="ret-no" type="button">cancel</button></div>
          <div id="end">{p['end']}</div></section></div>
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
<div class="scrim" id="dlg-new" hidden>
  <div class="dialog glass" role="dialog" aria-modal="true" aria-labelledby="dn-h">
    <h2 id="dn-h">New session</h2>
    <div class="grid">
      <label class="sub" for="dn-subject">subject</label><select id="dn-subject"{off}>{p['dn-subject']}</select>
      <label class="sub" for="dn-deployment">deployment</label><select id="dn-deployment"{off}><option value="rig_fixed">head-fixed</option><option value="rig_chaired">chaired</option></select>
      <label class="sub" for="dn-view">setup</label><select id="dn-view"{off}><option value="direct">direct view</option><option value="stereoscope">stereoscope</option></select>
      <label class="sub" for="dn-left">←cage at</label><input class="field mono" id="dn-left" autocomplete="off" placeholder="HH:MM, or 2027-01-13T22:40"{off}>
      <label class="sub" for="dn-id">id</label><input class="field mono" id="dn-id" autocomplete="off" placeholder="as wlx run --session-id takes it"{off}>
      <label class="sub" for="dn-given">given today, mL</label><input class="field mono" id="dn-given" inputmode="decimal" autocomplete="off" placeholder="blank when not known"{off}>
    </div>
    <div id="dn-msg" class="sub" role="status"></div>
    <div class="end"><button class="btn" id="dn-cancel" type="button">cancel</button><button class="btn primary" id="dn-ok" type="button"{off}>open session</button></div>
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
