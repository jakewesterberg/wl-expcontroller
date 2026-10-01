"""The browser console's panes (P4d-2b spec §4.2, §4.4): pure, and tested the way
`cli.render` is.

The assertions that matter most are the ones a simplified pane would break: fluid
session and the supplement never dropped (the zero-reward ruling rests on their being
visible, S9a §9), nothing unmeasured ever shown as 0, and no telemetry string ever
reaching the page as markup.
"""

from __future__ import annotations

import fnmatch
import html
import re
import time
import tomllib
from dataclasses import replace
from importlib import resources
from pathlib import Path

import pytest

from _frames import frame, idle, view
from wl_xcon.cli import _clock, _local
from wl_xcon.link import Control, Counts, ParamRow, Performance, Preflight, PreflightItem, Question, Refused, ScheduledStop, Staged, Stranded
from wl_xcon.web import (
    _SCRIPT,
    _clock_time,
    CONTROLS_AT_THE_BOX,
    DEBOUNCE_MS,
    END_CONFIRM,
    FONTS,
    FRAGMENT_IDS,
    LEGEND,
    NO_MARK_ENDPOINT,
    REWARD_ONLY_PAUSED,
    RUN_TRIALS,
    font_bytes,
    fragments,
    page,
)

LIMIT = "out_of_cage: subject 'A' has been out of its cage 28801 s against a ceiling of 28800"

STATES = {
    "running": {},
    "ended by the limit": {"stop_kind": "limit", "stopped_because": LIMIT},
    "awaiting return": {
        "stop_kind": "completed",
        "stopped_because": "every block is finished",
        "phase": "awaiting_return",
    },
    "returned": {
        "stop_kind": "operator",
        "stopped_because": "stopped by jake",
        "phase": "closed",
    },
    "fault": {
        "stop_kind": "fault",
        "stopped_because": "fault, session aborted: RuntimeError: solenoid did not answer",
    },
    "cage-side": {
        "deployment": "cage_side",
        "out_of_cage_seconds": None,
        "out_of_cage_limit_s": None,
        "chair_seconds": None,
    },
}


# --- never dropped -------------------------------------------------------------


@pytest.mark.parametrize("state", sorted(STATES))
def test_fluid_session_and_the_supplement_are_never_dropped(state):
    """The zero-reward ruling (PI, 2026-09-20) rests on both being visible, and the
    strip does not carry fluid session (spec §4.0; the supplement returned to it with
    the session-levels spec §6) -- so Runtime and End of session both must, in every
    state, a zero volume included."""
    parts = fragments(
        frame(fluid_session_ml=0.0, shortfall_ml=3.21, **STATES[state]), view()
    )

    for pane in ("rt-work", "end"):
        assert "0.00 mL" in parts[pane], (state, pane)
        assert "3.21" in parts[pane], (state, pane)


def test_an_unknown_supplement_is_a_sentence_not_a_zero():
    parts = fragments(frame(shortfall_ml=None, fluid_today_ml=None), view())

    for pane in ("rt-work", "end"):
        assert "unknown: the day's prior total was not supplied" in parts[pane]


@pytest.mark.parametrize(
    "state", ["running", "ended by the limit", "awaiting return", "returned", "fault"]
)
def test_the_out_of_cage_time_is_never_dropped(state):
    parts = fragments(frame(**STATES[state]), view())

    assert "1:23:45" in parts["strip"]
    assert "1:23:45" in parts["end"]


def test_a_cage_side_session_says_it_has_no_out_of_cage_clock_rather_than_zero():
    parts = fragments(frame(**STATES["cage-side"]), view())

    assert (
        '<span class="k">back to cage</span><span class="n"><span class="nm">cage-side</span>'
        '</span><span class="n"></span><span class="x">no limit</span>' in parts["strip"]
    )
    assert "cage-side · no out-of-cage interval" in parts["end"]
    assert "0:00" not in parts["strip"] + parts["end"]


def test_the_duration_warning_is_never_dropped():
    warning = "out_of_cage: subject 'A' has 900 s left of its 28800 s out of the cage"

    parts = fragments(frame(duration_warning=warning), view())

    assert html.escape(warning, quote=True) in parts["banners"]


def test_the_refusals_that_fell_off_the_cap_are_counted_before_the_rows():
    parts = fragments(
        frame(refusals=(Refused("fx_hold", "sam", "not declared"),), refusals_dropped=417),
        view(),
    )

    changes = parts["rt-changes"]
    assert "417 earlier refusal(s) not shown" in changes
    assert changes.index("417 earlier") < changes.index("fx_hold")


# --- never a zero for what nothing measured -----------------------------------


def test_nothing_unmeasured_is_rendered_as_zero():
    parts = fragments(
        frame(fluid_today_ml=None, last_reward_at=None), view(trials_per_min=None)
    )

    for name in ("dropped frames", "tracker staleness", "RHX margin"):
        assert re.search(
            rf'<span>{name}</span><span class="nm">not measured</span>', parts["rt-wrong"]
        ), name
    strip = parts["strip"]
    assert "unknown" in strip and "none yet" in strip
    # A rate `wlx serve` has not yet derived is left out, as mockup v13 leaves it:
    # never 0.0/min.
    assert "/min" not in strip
    assert "0 s" not in strip


def test_the_time_since_the_last_reward_is_the_frames_instant_aged_by_serve():
    """Ledger Ruling 1 (2026-09-27): the frame's own instant less the reward's, both on
    the session's anchored clock, plus the seconds `wlx serve` has held the frame --
    30 s and 12 s here, so neither alone reads 42."""
    parts = fragments(
        frame(wall_at=1_700_000_030.0, last_reward_at=1_700_000_000.0),
        view(frame_age_s=12.0),
    )

    assert (
        '<span class="k">last reward</span><span class="n">42 s ago</span>' in parts["strip"]
    )


@pytest.mark.parametrize(
    "at", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"]
)
def test_a_reward_instant_that_is_not_a_number_reads_unknown_not_a_crash(at):
    """m1: `welfare.deliver` stores a non-finite `wall_now` rather than refusing it
    (its docstring: it bounds nothing), so a frame can carry one. `health.ago` raised
    on it, so every stream died and reconnected in a loop and `GET /` failed, while
    `/health` said `ok`. Every other pane still renders."""
    parts = fragments(frame(last_reward_at=at), view())

    assert (
        '<span class="k">last reward</span>'
        '<span class="n"><span class="nm">unknown</span></span>' in parts["strip"]
    )
    assert tuple(parts) == FRAGMENT_IDS


@pytest.mark.parametrize("at", [1e20, 1e18, -1e18], ids=["past-time_t", "1e18", "-1e18"])
def test_a_finite_instant_this_host_cannot_show_is_a_dash_not_a_crash(at):
    """The b2a final review: `_clock_time` refused only NaN and inf, and a finite
    instant `time.localtime` cannot convert raised out of `fragments` -- on this
    macOS host, 2026-09-28, `OverflowError` for 1e20 and `OSError` for +-1e18 --
    which ends every stream and `GET /`, as m1's non-finite reward did. A pause's
    instant and a control's are both on the wire."""
    parts = fragments(
        frame(paused_at=at, controls=(Control("pause", "jake", at, "paused before trial 3"),)),
        view(),
    )

    assert parts["state"] == (
        '<span class="pill warn" data-state="paused">paused · since —</span>'
    )
    assert "— · paused before trial 3 · jake" in parts["rt-changes"]
    assert tuple(parts) == FRAGMENT_IDS


def test_out_of_cage_time_with_no_published_limit_shows_the_clock_alone():
    """A rig session whose frame carries its out-of-cage time but no limit shows the
    clock alone, and says no limit was published: no deadline and no time left, since
    neither can be worked out without one."""
    strip = fragments(frame(out_of_cage_limit_s=None), view())["strip"]

    assert (
        '<span class="k">back to cage</span><span class="n">1:23:45</span>'
        '<span class="n"></span><span class="x">out · no limit published</span>' in strip
    )
    assert '<span class="n">by ' not in strip and " left" not in strip


# --- counts, ticks, and the strip's arithmetic ----------------------------------


def test_the_working_pane_keeps_every_count_unrolled():
    """The strip's rollup is the strip's alone: this pane counts each outcome as it
    occurred, as `/health` does."""
    work = fragments(
        frame(
            trial_index=10,
            outcomes={"correct": 3, "correct_reject": 2, "no_fixation": 5},
        ),
        view(),
    )["rt-work"]

    assert '<span>correct</span><span class="num">3</span>' in work
    assert '<span>correct_reject</span><span class="num">2</span>' in work
    assert '<span>correct</span><span class="num">5</span>' not in work


def test_the_fluid_bar_is_today_over_the_floor():
    strip = fragments(frame(fluid_today_ml=61.25, floor_ml=250.0), view())["strip"]

    assert 'style="width:24.5%"' in strip
    assert "61.25" in strip and "/ 250.00 mL" in strip


def test_counts_are_grouped_by_family_with_no_rollup():
    work = fragments(
        frame(outcomes={"correct": 3, "early_response": 1, "no_fixation": 2}), view()
    )["rt-work"]

    assert "<h3>Target</h3>" in work and "<h3>No engagement</h3>" in work
    assert '<span>correct</span><span class="num">3</span>' in work
    assert '<span>early_response</span><span class="num">1</span>' in work
    assert '<span class="num">4</span>' not in work, "a family total is back"


def test_an_outcome_this_build_does_not_know_is_shown_not_dropped():
    """Review Focus 3: a newer `taskd` may send an outcome this `Outcome` lacks."""
    parts = fragments(
        frame(
            outcomes={"from_a_newer_taskd": 5},
            recent_outcomes=("from_a_newer_taskd", "hang"),
        ),
        view(),
    )

    assert "<h3>Other</h3>" in parts["rt-work"]
    assert "from_a_newer_taskd" in parts["rt-work"]
    assert 'class="tk f-other" title="from_a_newer_taskd"' in parts["rt-trials"]
    assert 'class="tk f-hang" title="hang"' in parts["rt-trials"]


def test_the_ticks_are_sixty_oldest_first_colored_by_family_with_a_legend():
    ticks = fragments(
        frame(recent_outcomes=("correct", "fixation_break", "wrong_target")), view()
    )["rt-trials"]

    assert ticks.count('<span class="tk') == 60
    assert 'class="tk f-target" title="correct"' in ticks
    assert 'class="tk f-breaks" title="fixation_break"' in ticks
    assert 'class="tk f-distractor" title="wrong_target"' in ticks
    assert ticks.index('title="correct"') < ticks.index('title="wrong_target"')
    for key, label in LEGEND:
        assert f'<i class="tk f-{key}"></i>{label}' in ticks


# --- the strip's two cells (session-levels spec §6) -----------------------------


def _no_run(phase):
    """A frame while no run goes: the session's counts alone (`taskd.Session.performance`).
    Named apart from b3a-2's `_between` below, which keeps `frame()`'s four levels."""
    return replace(
        frame(),
        phase=phase,
        performance=Performance(
            Counts({"correct": 30, "no_fixation": 10}, 0), None, None, None, None, None, None, None, None
        ),
    )


def test_the_strip_has_two_cells():
    assert fragments(frame(), view())["strip"].count('<div class="row">') == 2


def test_correct_trials_shows_the_session_its_task_this_run_and_this_block():
    strip = fragments(frame(), view(trials_per_min=12.0))["strip"]
    assert '30<span class="u"> / 40</span>' in strip and "75%" in strip
    assert "12.0/min" in strip
    assert "fixation_detection" in strip and "2 runs" in strip
    assert "this run" in strip and "run 3" in strip
    assert "block 27 · near" in strip


def test_correct_counts_correct_and_correct_reject_at_every_level():
    """The one rollup (PI, 2026-09-26), on each line."""
    perf = Performance(
        session=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        task=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        run=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        block=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        task_name="t", runs_of_task=1, run_in_session=1, block_in_session=1, block_type="b",
    )
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert strip.count("50%") == 4


def test_hangs_count_among_the_trials():
    perf = replace(frame().performance, session=Counts({"correct": 1}, 1))
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert '1<span class="u"> / 2</span>' in strip and "50%" in strip


def test_between_runs_one_line_says_so():
    """Review Focus 5 and plan ruling 4."""
    strip = fragments(_no_run("between_runs"), view())["strip"]
    assert '<span class="k">between runs</span>' in strip
    assert "this run" not in strip and "block" not in strip


def test_after_the_runs_one_line_says_no_run_is_going():
    strip = fragments(_no_run("awaiting_return"), view())["strip"]
    # The line's own name span: the fluid cell's reward note also says "no run going".
    assert '<span class="k">no run going</span>' in strip


def test_while_a_run_goes_the_last_reward_line_notes_what_a_correct_trial_pays():
    """Session-levels spec §6 and plan ruling 6: the last-reward line's note is
    `reward_correct`'s value in its row's own unit. The final review found
    `web._per_correct` neutered to `None` with every test passing."""
    running = frame(
        phase="running",
        stop_kind=None,
        params=(ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),),
    )

    strip = fragments(running, view())["strip"]

    assert (
        '<span class="k">last reward</span><span class="n">42 s ago</span>'
        '<span class="n"></span><span class="x">0.15 mL per correct</span>'
    ) in strip


def test_with_no_run_going_the_last_reward_line_says_so_in_its_own_note():
    """The last-reward line's own `x` span, not a bare substring: after the runs the
    performance cell's one line says "no run going" too
    (`test_after_the_runs_one_line_says_no_run_is_going`)."""
    strip = fragments(_no_run("awaiting_return"), view())["strip"]

    assert (
        '<span class="k">last reward</span><span class="n">42 s ago</span>'
        '<span class="n"></span><span class="x">no run going</span>'
    ) in strip


def test_before_the_first_trial_the_session_says_so_not_zero():
    """Its percentage would be 0/0, and neither `0%` nor `NaN` may stand in for a count
    nobody has made (the claim of the four-cell strip's test of this name)."""
    perf = Performance(Counts({}, 0), None, None, None, None, None, None, None, None)
    strip = fragments(replace(frame(), performance=perf, phase="between_runs"), view())["strip"]
    assert "no trials yet" in strip
    assert '<span class="u"> / 0</span>' not in strip
    assert "0%" not in strip and "NaN" not in strip


def test_a_run_before_its_first_trial_keeps_its_notes_and_has_no_block_yet():
    """A block opens with its first trial (plan ruling 1): until then its line is
    *block* and a dash. The run's line and its task's (the task's first run here) show
    a dash, no percentage of nothing, and keep their notes, "run 3" and "1 run" (spec
    §6, mockup v13; the controller's ruling in Task 6's review)."""
    perf = replace(
        frame().performance, task=Counts({}, 0), runs_of_task=1, run=Counts({}, 0),
        block=None, block_in_session=None, block_type=None,
    )
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert (
        '<span class="k">block</span><span class="n"><span class="u">—</span></span>'
        '<span class="n"></span><span class="x"></span>' in strip
    )
    assert (
        '<span class="k">this run</span><span class="n"><span class="u">—</span></span>'
        '<span class="n"></span><span class="x">run 3</span>' in strip
    )
    assert (
        '<span class="k">fixation_detection</span><span class="n"><span class="u">—</span></span>'
        '<span class="n"></span><span class="x">1 run</span>' in strip
    )
    assert "no trials yet" not in strip, "the session has trials; only its line says that"


def test_the_supplement_owed_is_on_the_strip():
    strip = fragments(replace(frame(), shortfall_ml=12.5), view())["strip"]
    assert "supplement" in strip and "12.50" in strip and "to reach the floor" in strip


def test_a_met_floor_says_so():
    strip = fragments(replace(frame(), shortfall_ml=0.0), view())["strip"]
    assert "floor met" in strip


def test_an_unknown_day_says_the_supplement_is_unknown():
    strip = fragments(replace(frame(), shortfall_ml=None, fluid_today_ml=None), view())["strip"]
    assert "unknown" in strip and "the day's prior total was not supplied" in strip


def test_back_to_cage_gives_the_deadline_the_time_out_and_the_time_left():
    """5025 s out of an 8 h limit (ruling 5): the deadline is the frame's wall instant
    less the time out plus the limit, as this host shows it."""
    f = replace(frame(), out_of_cage_seconds=5025.0, out_of_cage_limit_s=28_800.0, duration_warning=None)
    strip = fragments(f, view())["strip"]
    deadline = time.strftime("%H:%M", time.localtime(f.wall_at - 5025.0 + 28_800.0))
    assert f"by {deadline}" in strip
    assert f"{_clock(5025.0)} out · {_clock(28_800.0 - 5025.0)} left" in strip


def test_back_to_cage_warns_with_the_sessions_warning_and_is_critical_at_the_limit():
    warned = fragments(replace(frame(), duration_warning="30 min left"), view())["strip"]
    limited = fragments(replace(frame(), stop_kind="limit"), view())["strip"]
    assert 'class="k warn"' in warned and 'class="k crit"' in limited


def test_back_to_cage_past_the_limit_is_critical_and_says_so():
    """30,000 s out against an 8 h limit, the session ended and the return awaited:
    no time is left, so the line is critical whatever `stop_kind` says, and it says
    *past the limit* rather than a negative time left."""
    f = replace(
        frame(), phase="awaiting_return", stop_kind="completed",
        out_of_cage_seconds=30_000.0, out_of_cage_limit_s=28_800.0,
    )
    strip = fragments(f, view())["strip"]
    assert 'class="k crit"' in strip and "past the limit" in strip


def test_a_recorded_return_says_when():
    f = replace(frame(), returned_at=1_700_000_000.0, phase="closed")
    strip = fragments(f, view())["strip"]
    assert "at " + time.strftime("%H:%M", time.localtime(1_700_000_000.0)) in strip and "recorded" in strip


def test_a_cage_side_session_has_no_back_to_cage_clock():
    strip = fragments(replace(frame(), out_of_cage_seconds=None, out_of_cage_limit_s=None), view())["strip"]
    assert "cage-side" in strip and "no limit" in strip


# --- the header, the banners, and no session ------------------------------------


@pytest.mark.parametrize(
    ("overrides", "label", "state"),
    [
        ({}, "running", "running"),
        ({"stop_kind": "limit", "stopped_because": LIMIT}, "ended · limit", "ended"),
        (STATES["awaiting return"], "ended · completed · awaiting return", "ended"),
        (STATES["returned"], "ended · operator · returned", "ended"),
    ],
)
def test_the_state_pill_reads_phase_and_stop_kind(overrides, label, state):
    pill = fragments(frame(**overrides), view())["state"]

    assert f'data-state="{state}">{label}</span>' in pill


def test_with_no_frame_every_pane_says_so():
    parts = fragments(None, view(frame_age_s=None))

    assert tuple(parts) == FRAGMENT_IDS
    assert 'data-state="none"' in parts["state"]
    assert "no telemetry yet" in parts["banners"]
    for pane in ("head-id", "strip", "rt-trials", "rt-work", "rt-need", "params", "setup", "end"):
        assert "no session" in parts[pane], pane


def test_with_no_frame_and_no_refusal_the_page_names_the_endpoint_it_reads():
    """m4: *Waiting* used to assert that no session was publishing on the link, which
    this console cannot know. What it knows is that nothing has arrived on the PUB
    endpoint it reads, so that is what it says -- and *wl-works sees* says the same."""
    parts = fragments(None, view(frame_age_s=None, endpoint="tcp://10.0.0.7:5571"))

    assert (
        "no telemetry yet: no frame has arrived on tcp://10.0.0.7:5571"
        in parts["banners"]
    )
    assert "no session is publishing" not in parts["banners"]
    assert (
        "none attached · no frame has arrived on tcp://10.0.0.7:5571"
        in parts["rt-health"]
    )


def test_the_endpoint_is_escaped_wherever_the_page_names_it():
    parts = fragments(None, view(frame_age_s=None, endpoint=EVIL))

    text = "".join(parts.values())
    assert "<script" not in text
    assert EVIL not in text
    assert html.escape(EVIL, quote=True) in parts["banners"]


def test_the_header_carries_the_session_and_the_trial():
    head = fragments(frame(trial_index=41), view())["head-id"]

    for text in ("2027-01-14_01", ">A<", "rig_fixed", ">session<", 'data-trial="41">41<', "1:12:01"):
        assert text in head, text


def test_presence_says_this_box_or_lan_viewer_with_the_count():
    assert (
        fragments(frame(), view(on_box=True, lan_viewers=2))["presence"]
        == "<b>this box</b> · 2 LAN viewers"
    )
    assert (
        fragments(frame(), view(on_box=False, lan_viewers=1))["presence"]
        == "<b>LAN viewer</b> · 1 LAN viewer"
    )


def test_a_refused_frame_is_said_above_everything_else():
    """Review Focus 1: a frame this console could not read is said, first."""
    banners = fragments(
        frame(), view(rejected="a telemetry frame carried schema 6")
    )["banners"]

    assert banners.startswith('<div class="banner crit"><span class="tag">Refused</span>')
    assert "schema 6" in banners


def test_a_refusal_with_no_frame_held_says_so_and_nothing_else():
    """Ruling 11 (2026-09-27): with a refusal and no frame, the *Waiting* banner's
    "no session is publishing" is false -- one is, in a schema this console cannot
    read -- so only the refusal is said."""
    banners = fragments(
        None, view(frame_age_s=None, rejected="a telemetry frame carried schema 6")
    )["banners"]

    assert banners.startswith('<div class="banner crit"><span class="tag">Refused</span>')
    assert "Waiting" not in banners
    assert "no telemetry yet" not in banners


@pytest.mark.parametrize("held", [None, *sorted(STATES)])
def test_the_health_pane_features_a_refusal_as_health_does(held):
    """Ruling 11: the pane shows `/health`'s verdict and featured reading, so a
    refusal is on it too -- `degraded`, featured, unless a held frame's warning or
    fault outranks it -- and still with exactly one ◆."""
    found = None if held is None else frame(**STATES[held])
    pane = fragments(
        found, view(frame_age_s=None if found is None else 0.5, rejected="schema 6")
    )["rt-health"]

    assert pane.count("◆") == 1
    assert '<span class="l">Refused</span><span class="v">schema 6</span>' in pane
    if held == "fault":
        assert '<span class="pill crit">down</span>' in pane
    else:
        assert '<span class="pill warn">degraded</span>' in pane
    if held in (None, "running", "awaiting return", "returned", "cage-side"):
        assert '<span class="f">◆</span><span class="l">Refused</span>' in pane


def test_the_stop_reason_is_a_banner_and_ends_the_summary():
    parts = fragments(frame(**STATES["returned"]), view())

    assert "stopped by jake" in parts["banners"]
    assert "stopped by jake" in parts["end"]


# --- the read-only panes ----------------------------------------------------------


def test_parameters_show_value_range_ceiling_and_what_is_staged():
    params = fragments(
        frame(
            params=(
                ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
                ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
                ParamRow("target_looks", "", None, None, None, False),
                ParamRow("fix_window", "deg", None, 5.0, 2.0, False),
                ParamRow("shape", "", None, None, "penguin", False),
            ),
            staged=(Staged("fix_hold", 0.3, 0.4, "jake", False),),
        ),
        view(),
    )["params"]

    assert params.count('<div class="param') == 5
    assert '<div class="param staged">' in params
    assert "staged → 0.40 by jake" in params
    assert '<span class="ceil">ceiling</span>' in params
    # Review fix round 1: the ceiling keeps its own decimals (`_significant`), unlike
    # `_num`'s two-decimal `staged →` figure just above -- 0.4, not 0.40.
    assert "welfare ceiling 0.4 mL" in params
    assert "0.10 to 1.00 s" in params
    assert "open to 5.00 deg" in params
    assert "no declared range" in params
    assert "unset" in params
    assert "penguin" in params


def test_the_page_shows_the_stereoscopes_half_ipd():
    setup = fragments(frame(view="stereoscope", half_ipd_cm=1.6), view())["setup"]

    assert "the stereoscope, half-IPD 1.60 cm" in setup


def test_setup_names_the_configuration_and_what_has_no_source():
    setup = fragments(frame(allocation="", bounds_config=""), view())["setup"]

    assert "tasks/fixation_detection.py" in setup
    assert "provisional: none given" in setup
    assert '<dt>bounds config</dt><dd><span class="nm">not given</span></dd>' in setup
    assert setup.count("no source yet") == 1
    assert "<dt>display mode</dt><dd>direct view</dd>" in setup
    assert "250.00 mL" in setup and "8:00:00" in setup


def test_still_needed_lists_each_condition_and_its_count():
    need = fragments(frame(owed={"ecc 10": 18, "catch": 2}), view())["rt-need"]

    assert '<span class="mono">ecc 10</span><span class="num">18</span>' in need
    assert '<span class="mono">catch</span><span class="num">2</span>' in need


def test_the_health_pane_shows_what_wl_works_would_be_sent():
    pane = fragments(frame(duration_warning="warning text"), view())["rt-health"]

    assert '<span class="pill warn">degraded</span>' in pane
    assert pane.count("◆") == 1
    assert "warning text" in pane


# --- escaping ------------------------------------------------------------------

EVIL = "<script>alert(1)</script>\"'&"


def test_every_telemetry_string_is_escaped():
    """Review Focus 2: every string a frame carries -- and the refusal `wlx serve`
    adds -- is text on the page, in an element or an attribute, and never markup."""
    evil = frame(
        session_id=EVIL,
        subject=EVIL,
        block=EVIL,
        deployment=EVIL,
        stop_kind=EVIL,
        phase=EVIL,
        stopped_because=EVIL,
        duration_warning=EVIL,
        task=EVIL,
        allocation=EVIL,
        bounds_config=EVIL,
        outcomes={EVIL: 1, "correct": 2},
        owed={EVIL: 3},
        recent_outcomes=(EVIL, "correct"),
        staged=(Staged(EVIL, 0.1, 0.2, EVIL, False),),
        refusals=(Refused(EVIL, EVIL, EVIL),),
        params=(ParamRow(EVIL, EVIL, None, None, EVIL, False),),
        performance=replace(frame().performance, task_name=EVIL, block_type=EVIL),
    )
    # `phase` is EVIL above, so the reward's unit, which the strip shows only while a
    # run goes (`_per_correct`), needs a running frame of its own.
    paying = frame(params=(ParamRow("reward_correct", EVIL, 0.0, 0.4, 0.15, True),))

    text = "".join(fragments(evil, view(rejected=EVIL)).values()) + "".join(
        fragments(paying, view()).values()
    )

    assert "<script" not in text
    assert EVIL not in text
    assert html.escape(EVIL, quote=True) in text


# --- the page (Task 8) --------------------------------------------------------------


def _document(**frame_overrides) -> str:
    return page(
        fragments(frame(**frame_overrides), view()), stale_after_s=30.0, nonce="n0nce"
    )


def test_the_page_holds_every_pane_in_the_element_its_stream_swaps():
    """On connect the page is already rendered (spec §4.3): each fragment sits in the
    element whose id the stream's events name, and each id is on the page once."""
    parts = fragments(frame(), view())
    document = page(parts, stale_after_s=30.0, nonce="n0nce")

    for key in FRAGMENT_IDS:
        assert document.count(f'id="{key}"') == 1, key
        assert re.search(
            rf'id="{re.escape(key)}"[^>]*>{re.escape(parts[key])}<', document
        ), key


def test_a_page_missing_a_pane_is_refused_not_rendered_blank():
    parts = fragments(frame(), view())
    del parts["strip"]

    with pytest.raises(KeyError):
        page(parts, stale_after_s=30.0, nonce="n0nce")


def test_the_one_script_carries_the_nonce_and_nothing_loads_from_elsewhere():
    """A lab host renders with no internet: the fonts are the box's own (PI,
    2026-09-26), and the page names no other host at all."""
    document = _document()

    assert document.count("<script") == 1
    assert '<script nonce="n0nce">' in document
    assert "<link" not in document
    assert "http://" not in document and "https://" not in document
    assert not re.search(r'(?:src|href|url)\s*[=(]\s*"?//', document)


def test_the_page_declares_each_bundled_font_and_no_other():
    document = _document()

    assert document.count("@font-face") == len(FONTS)
    for font in FONTS:
        assert f'url("/fonts/{font.file}") format("woff2")' in document, font.file
    for family in (
        "IBM Plex Sans",
        "IBM Plex Sans Condensed",
        "IBM Plex Mono",
        "Newsreader",
    ):
        assert any(font.family == family for font in FONTS), family


def test_every_font_the_page_uses_is_bundled_with_its_license():
    """OFL-1.1 condition 2: each copy carries the copyright notice and the license --
    here, beside the files, as `OFL.txt`. And each file is the woff2 it claims to be."""
    fonts = resources.files("wl_xcon").joinpath("fonts")

    for font in FONTS:
        assert font_bytes(font)[:4] == b"wOF2", font.file
    for directory in {font.directory for font in FONTS}:
        text = fonts.joinpath(directory).joinpath("OFL.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in text, directory


def test_the_fonts_ship_with_the_package():
    """`pyproject.toml`'s package data carries every font and its license, so an
    installed `wlx serve` serves what a checkout does."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["setuptools"]
    globs = table["package-data"]["wl_xcon"]

    for font in FONTS:
        for rel in (f"fonts/{font.directory}/{font.file}", f"fonts/{font.directory}/OFL.txt"):
            assert any(fnmatch.fnmatch(rel, pattern) for pattern in globs), rel


def test_the_nonce_is_escaped_into_its_attribute():
    document = page(fragments(frame(), view()), stale_after_s=30.0, nonce='x"><b>')

    assert '<script nonce="x&quot;&gt;&lt;b&gt;">' in document


def test_the_page_tells_its_script_when_a_stream_is_stale():
    document = page(fragments(frame(), view()), stale_after_s=45.0, nonce="n0nce")

    assert '<body data-stale-after="45" data-can-write="0" data-debounce-ms="600">' in document


def test_the_right_column_is_honest_placeholders():
    """So the layout never shifts and nothing pretends to be live (PI, 2026-09-26)."""
    document = _document()

    for text in (
        "replica · V11",
        "subject display · no source yet",
        "sound · not measured",
        "display · not measured",
    ):
        assert text in document, text


def test_the_page_writes_only_by_posting_json_to_commands():
    """Spec §4.2, as amended by §5.2: the page's writes are the controls, and every
    one goes through the script's one `fetch` -- a JSON `POST` to `/commands` -- and
    never a form (the Content-Security-Policy's `form-action 'none'` refuses one
    anyway). Its radio inputs still only choose a tab."""
    document = _document()

    assert "<form" not in document and "<textarea" not in document
    assert _SCRIPT.count("fetch(") == 1
    assert 'fetch("/commands", {' in _SCRIPT
    assert 'method: "POST"' in _SCRIPT
    assert 'headers: { "Content-Type": "application/json" }' in _SCRIPT
    radios = re.findall(r'<input type="radio"[^>]*>', document)
    assert len(radios) == 4


def test_the_script_does_only_what_spec_4_3_and_5_2_ask():
    """§4.3's stream, and §5.2's growth: it sends commands, debounces the arrows,
    handles P and M, and asks for the name. It still renders nothing itself: every
    `innerHTML` it writes is a fragment `wlx serve` rendered."""
    document = _document()

    for needle in (
        'new EventSource("/events")',
        'addEventListener("frame"',
        "stream stale · last frame ",
        "stream lost",
        'el("close")',
        'el("reconnect")',
        "source.close()",
        'fetch("/commands", {',
        "window.prompt(",
        'k === "p"',
        'k === "m"',
    ):
        assert needle in document, needle
    assert "disconnected · the session keeps running on the box" in document
    # R3 (Task 13 rulings, carried from Task 10's review): capture the whole
    # right-hand side, not just the identifier -- `node.innerHTML = "<b>" + name`
    # would have slipped past a pin that only read the trailing word -- and allow
    # only the fragment renderer's own two forms. No other way to write markup.
    assert re.findall(r"\.innerHTML\s*\+?=\s*([^;]+);", _SCRIPT) == ["html", "heldParams"]
    assert "outerHTML" not in _SCRIPT
    assert "insertAdjacentHTML" not in _SCRIPT
    assert "document.write" not in _SCRIPT


def test_the_stale_timer_runs_from_the_frames_age_not_from_arrival():
    """Ruling 12 (2026-09-27). Python cannot run the script, so its text is pinned
    where it is load-bearing: the baseline is the event's arrival less the `age`
    `wlx serve` sends, stale is `now - baseline` at or beyond `--stale-after` --
    `>=`, so the page agrees with `/health`'s own boundary -- the banner's N is that
    same interval, and a `null` age -- no frame yet -- runs no timer. `now` and the
    baseline are both `performance.now()`, monotonic, so a browser clock step never
    skews the timer. The old `last = Date.now()` reset is what let a reconnect onto
    an old frame, or a refusal's wake-up, restart the clock."""
    assert "last = Date.now()" not in _SCRIPT
    timer = re.search(r"function check\(\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)
    assert "Date.now()" not in timer
    # The one `Date.now()` is the mark's `pressed_at`, the browser's clock, sent as
    # such (spec §5.1) and never read against the stream.
    assert _SCRIPT.count("Date.now()") == 1
    assert "pressed_at: Date.now() / 1000" in _SCRIPT
    assert (
        "baseline = payload.age === null ? null : performance.now() - payload.age * 1000;"
        in _SCRIPT
    )
    assert "var held = performance.now() - baseline;" in _SCRIPT
    assert "if (held >= staleMs) {" in _SCRIPT
    assert '"stream stale · last frame " + Math.floor(held / 1000) + " s ago"' in _SCRIPT
    assert "if (!live || baseline === null) {" in _SCRIPT


def test_a_lost_stream_greys_the_page_as_a_stale_one_does():
    """m3: the stale timer stands down while the stream is lost, so a red *stream
    lost* banner used to sit over full-color numbers nobody was updating. The error
    handler greys the page itself; the next frame's `check()` clears it."""
    handler = re.search(r"source\.onerror = function \(\) \{(.*?)\n    \};", _SCRIPT, re.S)

    assert handler, "the script's error handler moved; re-pin this test on it"
    body = handler.group(1)
    assert 'body.classList.add("stale");' in body
    assert body.index("lost = true;") < body.index('body.classList.add("stale");')
    assert 'say("stream lost", "crit");' in body


def test_the_stream_banner_and_the_disconnect_dialog_start_hidden():
    document = _document()

    assert '<div class="banner" id="stream" role="status" hidden></div>' in document
    assert re.search(r'<div class="scrim" id="gone"[^>]*hidden>', document)


# --- P4d-2b b2a: the controls (spec §5.2) -------------------------------------------


def _controls(**frame_overrides) -> str:
    return fragments(frame(**frame_overrides), view())["controls"]


def test_the_controls_offer_pause_mark_and_stop_while_running():
    controls = _controls()

    assert '<button type="button" class="btn" data-cmd="pause">pause (P)</button>' in controls
    assert '<button type="button" class="btn" data-cmd="mark">mark (M)</button>' in controls
    assert '<button type="button" class="btn danger" data-cmd="stop">stop run</button>' in controls
    # Every control but the manual reward, which waits for a pause (Task 13).
    assert controls.count(" disabled") == 1
    assert 'data-cmd="reward" disabled' in controls


def test_a_paused_session_offers_resume_and_says_since_when_in_its_pill():
    at = 1_700_000_030.0
    since = time.strftime("%H:%M:%S", time.localtime(at))
    parts = fragments(frame(paused_at=at), view())

    assert 'data-cmd="resume">resume (P)</button>' in parts["controls"]
    assert 'data-cmd="pause"' not in parts["controls"]
    assert parts["state"] == (
        f'<span class="pill warn" data-state="paused">paused · since {since}</span>'
    )


def test_an_ended_session_is_not_shown_paused_and_offers_no_controls():
    parts = fragments(frame(**STATES["returned"], paused_at=1_700_000_030.0), view())

    assert 'data-state="ended"' in parts["state"]
    assert "data-cmd" not in parts["controls"]
    assert "the session has ended" in parts["controls"]


def test_everywhere_but_the_box_the_controls_are_greyed_with_the_sentence():
    """Spec §5.2 and §2: every control is disabled and says why, in the §2 sentence,
    on the page a LAN viewer -- or the box's browser under another name -- is
    served. Refused at `POST /commands` too; this is so nobody is offered a button
    that cannot work."""
    parts = fragments(
        frame(scheduled_stop=ScheduledStop("trials", 48.0, "jake", "after trial 48")),
        view(on_box=False, can_write=False),
    )
    written = parts["controls"] + parts["params"] + parts["strip"]

    buttons = re.findall(r"<button[^>]*data-(?:cmd|dir)[^>]*>", written)
    inputs = re.findall(r"<input[^>]*data-param[^>]*>", written)
    assert buttons and inputs
    assert all(" disabled" in tag for tag in buttons + inputs)
    assert CONTROLS_AT_THE_BOX in parts["controls"]
    assert CONTROLS_AT_THE_BOX == (
        "controls work only at the rig PC until remote sign-in arrives"
    )


def test_a_console_without_the_mark_endpoint_greys_mark_alone():
    controls = fragments(frame(), view(can_mark=False))["controls"]

    assert re.search(r'data-cmd="mark" disabled title="[^"]+"', controls)
    assert NO_MARK_ENDPOINT in html.unescape(controls)
    assert re.search(r'data-cmd="pause">', controls)


def test_each_parameter_card_has_arrows_and_an_input_with_its_step_and_range():
    """Spec §5.2: up/down arrows and an input on each card. The step is the mockup's
    rule by unit (mL 0.01, s 0.05, deg 0.1, else 0.01), and the input shows the value
    at the step's decimals; a categorical card takes a word and has no arrows."""
    params = fragments(
        frame(
            params=(
                ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
                ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
                ParamRow("fix_window", "deg", None, 5.0, 2.0, False),
                ParamRow("target_looks", "", None, None, None, False),
                ParamRow("shape", "", None, None, "penguin", False),
            )
        ),
        view(),
    )["params"]

    assert (
        '<input class="field mono" data-param="fix_hold" data-step="0.05" '
        'data-min="0.1" data-max="1.0" inputmode="decimal" value="0.30" '
        'aria-label="fix_hold">'
    ) in params
    assert 'data-param="reward_correct" data-step="0.01" data-min="0.0" data-max="0.4"' in params
    assert 'data-param="fix_window" data-step="0.1" data-max="5.0" inputmode="decimal" value="2.0"' in params
    assert 'data-param="target_looks" data-step="0.01" inputmode="decimal" value=""' in params
    assert (
        '<input class="field mono" data-param="shape" data-kind="word" value="penguin" '
        'aria-label="shape">'
    ) in params
    assert params.count('data-dir="1"') == 4 and params.count('data-dir="-1"') == 4


def test_a_refusal_shows_on_its_parameters_card_with_its_sentence():
    params = fragments(
        frame(
            refusals=(
                Refused("fix_hold", "jake", "first"),
                Refused("fix_hold", "jake", "'fix_hold' is declared over [0.05, 2.0] s and 9 is outside it"),
            )
        ),
        view(),
    )["params"]

    assert (
        '<span class="rfs">last refused: &#x27;fix_hold&#x27; is declared over '
        "[0.05, 2.0] s and 9 is outside it</span>"
    ) in params
    assert "first" not in params


def test_the_strip_shows_a_scheduled_stop_with_who_set_it_and_a_cancel():
    """Spec §5.2: while a schedule is active the strip shows it -- *stop at 14:30 ·
    set by jake* -- with a cancel button."""
    strip = fragments(
        frame(scheduled_stop=ScheduledStop("clock", 1_700_003_600.0, "jake (box, unverified)", "at 14:30")),
        view(),
    )["strip"]

    assert '<span class="lab">Scheduled</span><span class="val">stop at 14:30</span>' in strip
    assert "set by jake (box, unverified)" in strip
    assert '<button type="button" class="btn small" data-cmd="cancel">cancel</button>' in strip


def test_with_nothing_scheduled_the_strip_keeps_its_two_cells():
    strip = fragments(frame(), view())["strip"]

    assert "Scheduled" not in strip
    assert strip.count('<div class="row">') == 2


def test_the_strip_guards_against_an_ended_frame_still_carrying_a_schedule():
    """Review fix round 1: since Task 8's fix, `Telemetry.of` sends
    `scheduled_stop=None` once `stopped_because` is set, so a frame like this should
    never arrive on the wire. This pins the guard's defensive behavior anyway -- a
    frame that combined an ended `stop_kind` with a `scheduled_stop` would still show
    no schedule and no cancel button for it."""
    strip = fragments(
        frame(
            **STATES["returned"],
            scheduled_stop=ScheduledStop("trials", 48.0, "jake", "after trial 48"),
        ),
        view(),
    )["strip"]

    assert "Scheduled" not in strip and "data-cmd" not in strip


def test_the_feed_lists_control_events_newest_first_with_who_and_counts_the_rest():
    """Spec §5.2: the changes feed lists every setting change, refusal, pause, resume,
    mark (with its note) and schedule, with who did it. Newest first, since it is
    read to see what just happened; what fell off the cap is counted below them."""
    at = 1_700_000_001.0
    clock = time.strftime("%H:%M:%S", time.localtime(at))
    changes = fragments(
        frame(
            controls=(
                Control("mark", "", at, "mark 1 stamped in trial 3, frame 10"),
                Control("note", "jake", at, 'mark 1: "bubble"'),
                Control("set", "sam", at, "fix_hold 0.30 → 0.40, from trial 4"),
            ),
            controls_dropped=5,
        ),
        view(),
    )["rt-changes"]

    set_row = changes.index(f"{clock} · fix_hold 0.30 → 0.40, from trial 4 · sam")
    note_row = changes.index(f"{clock} · mark 1: &quot;bubble&quot; · jake")
    mark_row = changes.index(f"{clock} · mark 1 stamped in trial 3, frame 10</span>")
    dropped = changes.index("5 earlier control event(s) not shown")
    assert set_row < note_row < mark_row < dropped
    assert '<span class="kind">note</span>' in changes


def test_every_control_string_is_escaped():
    """Review Focus 2 for b2a's strings: an actor's typed name, a note, a schedule's
    words, and a parameter's name in the attributes its input carries."""
    evil = frame(
        controls=(Control(EVIL, EVIL, 1_700_000_001.0, EVIL),),
        scheduled_stop=ScheduledStop(EVIL, 1.0, EVIL, EVIL),
        params=(ParamRow(EVIL, EVIL, 0.0, 1.0, 0.5, False), ParamRow("w", "", None, None, EVIL, False)),
        refusals=(Refused(EVIL, EVIL, EVIL),),
    )

    text = "".join(fragments(evil, view()).values())

    assert "<script" not in text
    assert EVIL not in text


def test_the_page_tells_its_script_whether_it_may_write_and_the_debounce():
    """The page is rendered per request, so the box's own page says it may write and
    a LAN viewer's says it may not; the script reads both from `<body>`. The 600 ms
    debounce is the mockup's, housekeeping and not a measurement."""
    box = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)
    lan = page(
        fragments(frame(), view(can_write=False)), stale_after_s=30.0, nonce="n0nce"
    )

    assert DEBOUNCE_MS == 600
    assert '<body data-stale-after="30" data-can-write="1" data-debounce-ms="600">' in box
    assert '<body data-stale-after="30" data-can-write="0" data-debounce-ms="600">' in lan
    for control in ('id="sched-kind"', 'id="sched-value"', 'id="sched-set"', 'id="rename"'):
        assert re.search(control + r"[^>]* disabled", lan), control
        assert not re.search(control + r"[^>]* disabled", box), control


def test_the_page_holds_the_stop_confirm_and_the_mark_note_hidden():
    document = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert re.search(r'<div class="inline crit" id="stop-confirm"[^>]*hidden>', document)
    assert "stop at a trial boundary, after any commands already sent?" in document
    assert re.search(r'<div class="inline info" id="mark-form"[^>]*hidden>', document)
    assert 'id="mark-note" maxlength="500"' in document


def test_the_script_debounces_the_arrows_and_keeps_p_and_m_out_of_text_boxes():
    """Spec §5.2: a change is sent once the arrows stop being clicked, and the keys do
    nothing while a text box has focus, or when held (a held key does not repeat)."""
    assert "setTimeout(function () { delete timers[key]; send(input); }, debounceMs)" in _SCRIPT
    assert "clearTimeout(timers[key]);" in _SCRIPT
    assert "if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) { return; }" in _SCRIPT
    assert '/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable' in _SCRIPT


def test_the_script_asks_for_the_name_once_and_keeps_it_where_it_may():
    """Spec §5.2: the box's browser asks once and remembers it locally. Storage can
    be refused -- a private window -- so every read and write is in `try`; a prompt
    refused or cleared sends nothing (Review Focus 6)."""
    assert "try { return window.localStorage.getItem(NAME_KEY) || \"\"; } catch (e) { return \"\"; }" in _SCRIPT
    assert "try { window.localStorage.setItem(NAME_KEY, given); } catch (e) { /* kept for this page only */ }" in _SCRIPT
    assert "if (given === null) { return \"\"; }" in _SCRIPT
    assert '"not sent: give your name first -- every command records who sent it"' in _SCRIPT


def test_the_script_holds_a_parameter_card_it_is_being_typed_into():
    """A frame that re-renders the parameter cards while a person types into one, or
    while an arrow's debounce is pending, would replace the input under them; the
    script holds the newest cards and swaps them in once the person is done."""
    assert 'if (id === "params" && busy()) { heldParams = html; return; }' in _SCRIPT


# --- Task 10 review, fix round 1 ----------------------------------------------------


def test_a_double_click_or_one_within_the_hold_cannot_toggle_pause_or_resume():
    """The review, round 2: the **P** key (`pauseOrResume`, wired from `keydown`)
    called `command` directly and was not covered by round 1's click-only guard -- a
    rapid double **P** is not an `e.repeat` (that only filters OS key-autorepeat, not
    two independent keydowns) and could reproduce the same toggle. One
    `toggleAllowed` helper now guards both routes: it refuses a click's own double
    (`detail > 1`) or anything within `TOGGLE_HOLD_MS` of the last pause/resume this
    page sent, and stamps that instant only on success. `command` itself is called
    only after the helper allows it, from both the click handler and
    `pauseOrResume`."""
    assert "var TOGGLE_HOLD_MS = 1000;" in _SCRIPT
    helper = re.search(
        r"function toggleAllowed\(detail\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    assert "detail > 1" in helper
    assert "now - lastToggleAt < TOGGLE_HOLD_MS" in helper
    assert "return false;" in helper
    assert "lastToggleAt = now;" in helper
    assert "return true;" in helper
    assert helper.index("return false;") < helper.index("lastToggleAt = now;")
    assert helper.index("lastToggleAt = now;") < helper.index("return true;")

    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);',
        _SCRIPT,
        re.S,
    ).group(1)
    assert 'cmd === "pause" || cmd === "resume"' in handler
    assert "toggleAllowed(e.detail)" in handler
    # Only pause/resume are guarded -- mark, stop and cancel are unaffected.
    assert handler.index('cmd === "pause"') > handler.index("var cmd =")
    assert handler.index("toggleAllowed(e.detail)") < handler.index("command(cmd);")

    pause_or_resume = re.search(
        r"function pauseOrResume\(\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    assert "toggleAllowed(" in pause_or_resume
    assert pause_or_resume.index("toggleAllowed(") < pause_or_resume.index("command(")


def test_the_arrows_round_before_clamping_and_write_the_edge_exactly():
    """The review: the old order clamped to `[lo, hi]` first and let `toFixed` round
    the display afterwards, so a clamped value could be rounded back out past its own
    ceiling (0.125 mL clamped, then `toFixed(2)` sent "0.13"). Rounding to the step
    now comes first; the clamp that follows writes the edge's own `data-min`/
    `data-max` attribute string exactly, never re-rounding it. Verified against the
    review's own examples in Node (pasted into the fix report): 0.125, 0.337 and 5.25
    ceilings all now stay at their own figure instead of overshooting to "0.13",
    "0.34" and "5.3"."""
    body = re.search(
        r"function stepInput\(input, dir\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)

    assert body.index("Math.round(") < body.index("if (v <= lo)")
    assert 'input.value = input.getAttribute("data-min");' in body
    assert 'input.value = input.getAttribute("data-max");' in body
    assert body.index("if (v <= lo)") < body.index("else if (v >= hi)")


def test_a_welfare_ceiling_displays_its_own_decimals_not_rounded_to_two():
    """The review: `_num`'s two-decimal display rounded a 0.125 mL ceiling to "0.12"
    -- short of "0.13", which the unfixed arrows could still send. The ceiling now
    keeps its own figure."""
    params = fragments(
        frame(params=(ParamRow("reward_correct", "mL", 0.0, 0.125, 0.1, True),)),
        view(),
    )["params"]

    assert "welfare ceiling 0.125 mL" in params
    assert "welfare ceiling 0.12 mL" not in params


def test_the_script_pins_the_box_only_write_guard():
    """The review found neither half of this pinned: the script reads `can-write`
    from `<body>`, and `post` -- the one function every command goes through --
    refuses to send anything when it says this page may not write, before it does
    anything else. Welfare-critical review round 1 (2026-09-28): a plain `in`
    passed with the guard moved below `tell("sending...")`, so this pins its
    position again -- the guard is the first thing `post` does, right after `done`
    is resolved."""
    assert 'var canWrite = body.getAttribute("data-can-write") === "1";' in _SCRIPT
    post_body = re.search(
        r"function post\(command, then, after\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    assert post_body.strip().startswith(
        "var done = after || function () {};\n    if (!canWrite) { done(); return; }"
    )


# --- P4d-2b b2a, amended 2026-09-28 (PI): a manual reward during a pause -------------


def test_during_a_run_the_reward_button_is_live_only_while_paused_and_greyed_otherwise():
    """PI, 2026-09-28: a manual reward during a pause. During a run the button works only
    while the session is paused (`paused_at`), and otherwise says why: greyed with its
    reason while trials run, with the §2 sentence away from the box, and gone once a
    `wlx run` session has ended. One button and no key: a click is one command. Outside a
    run, in a `wlx taskd` session, it is live too (PI, 2026-09-29): see
    `test_outside_a_run_the_hand_reward_and_mark_are_live_with_what_the_last_press_did`."""
    at = 1_700_000_030.0
    paused = _controls(paused_at=at)
    running = _controls()
    lan = fragments(frame(paused_at=at), view(on_box=False, can_write=False))["controls"]
    ended = fragments(frame(**STATES["returned"], paused_at=at), view())["controls"]

    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in paused
    assert (
        f'<button type="button" class="btn" data-cmd="reward" disabled '
        f'title="{REWARD_ONLY_PAUSED}">give reward</button>'
    ) in running
    assert REWARD_ONLY_PAUSED == (
        "a manual reward is given only while the session is paused: pause first"
    )
    assert re.search(r'data-cmd="reward" disabled title="[^"]+">give reward', lan)
    assert CONTROLS_AT_THE_BOX in lan
    assert "give reward" not in ended
    assert 'k === "r"' not in _SCRIPT, "no key gives a reward"


def test_while_paused_the_controls_show_the_fluid_total_and_what_the_last_press_did():
    """The answer to a press, from the frames the rig publishes while paused: the
    session's fluid total, the newest reward given with its size, and the newest
    refused with the rig's sentence -- *last*, since a refusal carries no time, as on
    a parameter card. Escaped like every string from telemetry."""
    at = 1_700_000_035.0
    controls = _controls(
        paused_at=1_700_000_030.0,
        fluid_session_ml=1.4,
        controls=(
            Control(
                "reward",
                "jake (box, unverified)",
                at,
                "0.15 mL of reward_correct, given while paused before trial 40",
            ),
        ),
        refusals=(Refused(name="reward", by="sam", why="the session is <not> paused"),),
    )
    clock = time.strftime("%H:%M:%S", time.localtime(at))

    assert "fluid session 1.40 mL" in controls
    assert (
        f"last given {clock}: 0.15 mL of reward_correct, given while paused before trial 40"
        in controls
    )
    assert "last refused: the session is &lt;not&gt; paused" in controls
    assert "fluid session" not in _controls(), "said beside the live button alone"


def test_the_script_sends_one_reward_per_click_and_holds_the_button_until_its_answer():
    """No accidental doubles (PI, 2026-09-28). Python cannot run the script, so its text
    is pinned where it is load-bearing: a click while a reward is on its way does
    nothing; the button is held from the click until the answer or the failure -- and
    held again whenever a frame re-renders the controls meanwhile -- and only a button
    the script held is released; the one `fetch` is never retried; and an answer the
    page lost is *unknown*, never *not delivered*, with the fluid total to check first."""
    assert "if (!button || button.disabled || rewarding) { return; }" in _SCRIPT
    assert "rewarding = true;" in _SCRIPT
    assert 'post({ kind: "reward" }, null, function () {' in _SCRIPT
    assert 'if (id === "controls") { holdReward(); }' in _SCRIPT
    assert "if (rewarding && button && !button.disabled) {" in _SCRIPT
    assert """el("controls").querySelector('[data-cmd="reward"][data-held]')""" in _SCRIPT
    assert "}).then(done);" in _SCRIPT
    assert _SCRIPT.count("fetch(") == 1
    assert (
        "unknown: this page lost wlx serve's answer, so whether the reward was given is "
        "not known, and it was not sent again; check the session's fluid total before "
        "pressing again"
    ) in _SCRIPT


def test_a_double_click_on_give_reward_gives_only_one_reward():
    """R2 (Task 13 rulings, an animal-facing defect in the plan): the disabled-until-
    answered rule alone can miss a double click on loopback, where the answer can
    return well inside a double click's span, leaving the button live again before
    the second click lands. `rewardAllowed` gives *give reward* the same debounce
    Task 10 gave pause and resume -- refused on a native double click (`detail > 1`)
    or within `REWARD_HOLD_MS` of the last reward this page sent -- in the click
    handler's own branch, never inside `command` or `post`, so a deliberate second
    press a second later still gives another reward."""
    assert "var REWARD_HOLD_MS = 1000;" in _SCRIPT
    assert (
        "// Housekeeping, not a measurement (R2, 2026-09-28): the same double click's span as\n"
        "  // TOGGLE_HOLD_MS, since a reward's answer can return well inside it on loopback,\n"
        "  // leaving the button live again before a double click's second click lands.\n"
        "  var REWARD_HOLD_MS = 1000;"
    ) in _SCRIPT
    assert "var lastRewardAt = -Infinity;" in _SCRIPT
    assert "function rewardAllowed(detail) {" in _SCRIPT
    assert (
        "if (detail > 1 || now - lastRewardAt < REWARD_HOLD_MS) { return false; }"
        in _SCRIPT
    )
    assert "lastRewardAt = now;" in _SCRIPT
    assert 'if (cmd === "reward" && !rewardAllowed(e.detail)) { return; }' in _SCRIPT
    command_body = re.search(
        r"function command\(cmd\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    post_body = re.search(
        r"function post\(command, then, after\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    assert "rewardAllowed" not in command_body
    assert "rewardAllowed" not in post_body


def test_the_page_with_no_session_open_says_so_and_puts_a_stranded_animal_first():
    panes = fragments(
        idle(
            stranded=(Stranded("2027-01-13_01", "<b>B</b>", 1_700_000_000.0),),
            question=Question("departure", "2027-01-14_01", 1.0, "far <i>", ("confirm", "amend")),
            refusals=(Refused("open", "jake", "refused <script>"),),
        ),
        view(),
    )

    assert set(panes) == set(FRAGMENT_IDS)
    assert 'data-state="idle"' in panes["state"]
    assert panes["banners"].index("Stranded") < panes["banners"].index("Confirm")
    assert "&lt;b&gt;B&lt;/b&gt;" in panes["banners"] and "<b>B" not in panes["banners"]
    assert "far &lt;i&gt; · answer confirm or amend" in panes["banners"]
    assert "Waiting" not in panes["banners"]
    assert "refused &lt;script&gt;" in panes["rt-changes"]
    assert "controls · no session open" in panes["controls"]
    assert "none open · wlx taskd is idle" in panes["rt-health"]
    assert '<span class="pill warn">degraded</span>' in panes["rt-health"], "an animal is stranded"


@pytest.mark.parametrize("unshowable", [1e20, float("nan")])
def test_the_pages_stranded_banner_shows_the_departures_date_or_says_it_is_unknown(unshowable):
    """The b3a-1 final review, Minor 1: the banner gave the departure as a clock time
    alone, so an animal stranded three days ago read "left its cage at 22:55:14". It is
    this host's local date, minute and zone, as the terminal gives it (`cli._moment`),
    or "an unknown time" for an instant this host cannot show."""
    left_at = 1_700_000_000.0
    banners = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", left_at), Stranded("2027-01-13_02", "C", unshowable))),
        view(),
    )["banners"]

    assert f"B left its cage at {html.escape(_local(left_at))} in session 2027-01-13_01" in banners
    assert "C left its cage at an unknown time in session 2027-01-13_02" in banners


def test_the_page_escapes_control_characters_and_markup_in_an_idle_frames_text():
    panes = fragments(
        idle(
            stranded=(Stranded("<s>", "B\x1b[2J<", None),),
            question=Question("return", "<q>", 1.0, "far\x1b", ("<a>",)),
            refusals=(Refused("<n>", "<by>", "<why>\x1b"),),
        ),
        view(),
    )

    joined = "".join(panes.values())
    for raw in ("<s>", "<q>", "<a>", "<n>", "<by>", "<why>"):
        assert raw not in joined


def test_the_page_between_runs_says_which_run_ended_and_offers_start_run_not_pause_or_stop():
    """`run_index` 1 is the session's second run: a person reads runs from 1
    (session-levels spec §3)."""
    panes = fragments(
        frame(phase="between_runs", service=True, run_index=1, stop_kind="operator", stopped_because="stopped by jake"),
        view(),
    )

    assert 'data-state="between-runs"' in panes["state"] and "run 2 ended" in panes["state"]
    assert "Run 2 ended" in panes["banners"]
    assert 'data-cmd="start"' in panes["controls"]
    assert 'data-cmd="pause"' not in panes["controls"] and 'data-cmd="stop"' not in panes["controls"]
    assert '<span class="k">Run</span><span class="v">2</span>' in panes["head-id"]


def test_the_header_pill_banner_and_strip_name_one_run():
    """The review of session levels' Task 6: the header, pill and banner printed the
    wire's 0-based `run_index` while the strip printed `run_in_session`, so one page
    named a session's third run as both 2 and 3."""
    perf = frame().performance
    assert perf.run_in_session == 3
    running = fragments(frame(run_index=2), view())
    ended = fragments(
        frame(
            phase="between_runs", service=True, run_index=2, stop_kind="operator",
            stopped_because="stopped by jake",
            performance=replace(perf, task=None, run=None, block=None, task_name=None,
                                runs_of_task=None, run_in_session=None,
                                block_in_session=None, block_type=None),
        ),
        view(),
    )

    assert '<span class="k">Run</span><span class="v">3</span>' in running["head-id"]
    assert "run 3" in running["strip"]
    assert '<span class="k">Run</span><span class="v">3</span>' in ended["head-id"]
    assert "run 3 ended" in ended["state"] and "Run 3 ended" in ended["banners"]


def test_the_page_before_a_sessions_first_run_shows_no_block_and_no_task():
    panes = fragments(
        frame(phase="between_runs", service=True, run_index=None, block=None, task=None, trial_index=0, outcomes={}),
        view(),
    )

    assert "between runs" in panes["state"] and "None" not in panes["head-id"]
    assert "no run yet" in panes["setup"] and "no run yet" in panes["end"]


def test_the_page_shows_the_question_a_return_owes():
    panes = fragments(
        frame(phase="awaiting_return", service=True, stop_kind="operator", stopped_because="session ended by jake",
              question=Question("return", "2027-01-14_01", 1.0, "the return is far", ("confirm", "re-type"))),
        view(),
    )

    assert "the return is far · answer confirm or re-type" in panes["banners"]


# --- P4d-2b b3a-2: sessions from the page ---------------------------------------------


def _between(**over):
    """A `wlx taskd` session between runs, its first run ended, one task offered."""
    fields = dict(
        phase="between_runs", service=True, run_index=0, stop_kind="completed",
        stopped_because="every block is finished", offered_tasks=("fixation_detection.py",),
    )
    fields.update(over)
    return frame(**fields)


#: A pre-flight as `wlx taskd` takes one (`preflight.py`'s item names), two items passing
#: and the two nothing measures yet unknown.
PREFLIGHT = Preflight(
    "fixation_detection.py",
    (
        PreflightItem("task checks", "pass", "fixation_detection.py passes its load-time checks"),
        PreflightItem("out of cage", "pass", "the departure is marked and the limit is not reached"),
        PreflightItem("pump calibration", "unknown", "no pump calibration has been measured (V10)"),
        PreflightItem("eye tracker", "unknown", "nothing reports the eye tracker's health yet"),
    ),
)
FAILING = replace(
    PREFLIGHT,
    items=(PREFLIGHT.items[0], PreflightItem("out of cage", "fail", "past <the> limit"))
    + PREFLIGHT.items[2:],
)


def test_the_task_chooser_offers_what_wlx_taskd_offers_and_says_when_there_is_nothing():
    only = '<option value="fixation_detection.py">fixation_detection.py</option>'

    assert fragments(_between(), view())["task-sel"] == only
    assert fragments(idle(), view())["task-sel"] == only
    assert fragments(frame(), view())["task-sel"] == '<option value="">no task offered</option>'
    assert fragments(None, view())["task-sel"] == '<option value="">no task offered</option>'


@pytest.mark.parametrize(
    ("preflight", "tone", "said"),
    [
        (None, "neutral", "pre-flight · not taken"),
        (PREFLIGHT, "warn", "pre-flight · 2 to acknowledge"),
        (FAILING, "crit", "pre-flight · 1 fail"),
        (replace(PREFLIGHT, items=PREFLIGHT.items[:2]), "ok", "pre-flight ✓"),
    ],
    ids=["not-taken", "unknowns", "a-fail", "all-pass"],
)
def test_between_runs_the_preflight_pill_is_a_button_that_says_what_the_rig_found(
    preflight, tone, said
):
    """The mockup's `pf-pill` and `pf-sum` (the b3a-2 plan, decisions 6 and 7): its words
    from the frame's pre-flight, and, between runs, a button that takes the pre-flight."""
    parts = fragments(_between(preflight=preflight), view())

    assert parts["pf-pill"] == (
        f'<button type="button" class="pill {tone}" data-cmd="check" '
        f'title="take the pre-flight for the task chosen">{said}</button>'
    )
    assert parts["pf-sum"] == f'<span class="pill {tone}">{said}</span>'


@pytest.mark.parametrize(
    ("shown", "said"),
    [
        (None, "no session"),
        (idle(), "no session"),
        (frame(), "pre-flight · wlx run takes none"),
        (frame(service=True), "pre-flight · taken as the run started"),
        (_between(phase="awaiting_return"), "pre-flight · the session has ended"),
    ],
    ids=["no-frame", "idle", "wlx-run", "a-run-going", "ended"],
)
def test_outside_between_runs_the_preflight_pill_only_says_why_there_is_none(shown, said):
    assert fragments(shown, view())["pf-pill"] == f'<span class="pill neutral">{said}</span>'


def test_the_preflight_panel_shows_each_item_its_result_and_no_unplanned_warning():
    """Under a line naming the task and S9a §10's rule, and nothing after it: the PI
    retired the unplanned-run warning on 2026-10-01, through wl-works (P4d-2b spec
    §4.0)."""
    shown = fragments(_between(preflight=FAILING), view())["preflight"]

    assert '<span class="st fail" title="fail"></span><span>out of cage</span>' in shown
    assert '<span class="st pass" title="pass"></span><span>task checks</span>' in shown
    assert '<span class="st untested" title="unknown"></span><span>eye tracker</span>' in shown
    assert "past &lt;the&gt; limit" in shown
    assert (
        '<div class="sub">for fixation_detection.py · a fail blocks the run; each unknown '
        "starts it only on your acknowledgement, by name, written into runs.jsonl</div>"
    ) in shown
    assert "unplanned" not in shown and "timing tier" not in shown
    assert 'data-task="fixation_detection.py"' in shown
    assert "not taken" in fragments(_between(), view())["preflight"]


def test_each_unknown_item_has_an_unticked_acknowledgement_carrying_its_exact_name():
    """Review Focus 4 (the b3a-2 plan, decision 9): one box per unknown item, its exact
    name on it for the start to send, never rendered ticked -- a tick is the person's,
    for the run about to start -- and greyed away from the box."""
    shown = fragments(_between(preflight=PREFLIGHT), view())["preflight"]
    lan = fragments(_between(preflight=PREFLIGHT), view(can_write=False))["preflight"]

    for name in ("pump calibration", "eye tracker"):
        assert (
            f'<label class="chk"><input type="checkbox" data-ack="{name}" '
            f'aria-label="acknowledge {name}"> acknowledge</label>'
        ) in shown
    assert shown.count("data-ack=") == 2, "only an unknown is acknowledged"
    assert "checked" not in shown
    boxes = re.findall(r"<input[^>]*data-ack[^>]*>", lan)
    assert boxes and all(" disabled" in box for box in boxes)


def test_between_runs_start_run_carries_the_shown_preflights_task_and_waits_for_one_with_no_fail():
    """The b3a-2 plan, decision 8, and spec §6.2: "the start refused while any item
    fails" -- greyed with its reason in the page, and refused by the rig anyway."""
    none = fragments(_between(), view())["controls"]
    ready = fragments(_between(preflight=PREFLIGHT), view())["controls"]
    failing = fragments(_between(preflight=FAILING), view())["controls"]

    assert (
        '<button type="button" class="btn go" data-cmd="start" data-task="" disabled '
        'title="take the pre-flight first: choose a task, or press the pre-flight pill">'
        "start run</button>"
    ) in none
    assert (
        '<button type="button" class="btn go" data-cmd="start" '
        'data-task="fixation_detection.py">start run</button>'
    ) in ready
    assert 'disabled title="pre-flight: out of cage failing">start run</button>' in failing
    # No unplanned-run warning beside it (the PI, 2026-10-01, through wl-works).
    assert "unplanned" not in ready and "timing tier" not in ready
    assert 'data-cmd="pause"' not in ready and 'data-cmd="stop"' not in ready


@pytest.mark.parametrize("phase", ["between_runs", "awaiting_return"])
def test_outside_a_run_the_hand_reward_and_mark_are_live_with_what_the_last_press_did(phase):
    """PI, 2026-09-29 (spec §6.0): *give reward* works between runs and while the return
    is awaited in a `wlx taskd` session, and says beside itself what the rig did."""
    controls = fragments(
        _between(
            phase=phase,
            fluid_session_ml=0.4,
            controls=(
                Control("reward", "jake (box, unverified)", 1_700_000_035.0,
                        "0.15 mL of reward_correct, given between runs"),
            ),
        ),
        view(),
    )["controls"]

    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in controls
    assert '<button type="button" class="btn" data-cmd="mark">mark (M)</button>' in controls
    assert "fluid session 0.40 mL" in controls
    assert "0.15 mL of reward_correct, given between runs" in controls


@pytest.mark.parametrize(
    "name, phase",
    [("start", "between_runs"), ("check", "between_runs"), ("end", "awaiting_return"), ("end", "between_runs")],
)
def test_a_refused_session_command_shows_in_the_control_bar_escaped(name, phase):
    """The b3a-2 final review, I3: a start refused on the Setup tab, or a return refused
    on the End tab, showed only in the Runtime tab's feed. `serve.SERVICE_SENT` promises
    the page shows a refusal with its reason; the newest of the session's own commands'
    refusals shows in the always-visible control bar, as a reward's does."""
    refusals = (
        Refused("start", "jake", "older"),
        Refused("reward", "jake", "a reward's own"),
        Refused(name, "jake", "why <b>&"),
        Refused("set", "jake", "not a session command"),
    )

    controls = fragments(_between(phase=phase, refusals=refusals), view())["controls"]

    assert f'<span class="nm">last refused · {name}: why &lt;b&gt;&amp;</span>' in controls
    assert "older" not in controls and "not a session command" not in controls


def test_the_idle_control_bar_shows_a_refused_open_or_stranded_return():
    refusals = (Refused("open", "jake", "no session opens while <b>"),)

    controls = fragments(idle(refusals=refusals), view())["controls"]

    assert '<span class="nm">last refused · open: no session opens while &lt;b&gt;</span>' in controls
    assert "last refused" not in fragments(idle(), view())["controls"]
    assert "last refused ·" not in fragments(_between(), view())["controls"]


def test_the_phases_the_page_lights_the_reward_in_are_the_ones_the_rig_gives_it_in():
    """The b3a-2 final review, m3: `taskd.OUTSIDE_A_RUN` decides in which phases outside a
    run the rig gives a hand reward, and `web._hand_reward_now` repeats it. The page must
    light the button in exactly those phases -- and during a run only while paused."""
    from wl_xcon.taskd import OUTSIDE_A_RUN
    from wl_xcon.web import _hand_reward_now

    phases = ("", "running", "between_runs", "awaiting_return", "closed")
    lit = {phase for phase in phases if _hand_reward_now(frame(service=True, phase=phase))}

    assert lit == set(OUTSIDE_A_RUN)
    assert not any(_hand_reward_now(frame(service=False, phase=phase)) for phase in phases)
    assert _hand_reward_now(frame(service=True, phase="running", paused_at=1_700_000_030.0))


def test_while_the_return_is_awaited_there_is_no_run_to_start():
    controls = fragments(_between(phase="awaiting_return"), view())["controls"]

    assert "session ended · waiting for the animal&#x27;s return" in controls
    assert 'data-cmd="start"' not in controls


def test_a_wlx_run_session_after_its_run_offers_no_hand_reward():
    """XC-184: its return is taken at its terminal, and the rig refuses a press then."""
    assert "give reward" not in fragments(frame(**STATES["awaiting return"]), view())["controls"]


def test_away_from_the_box_the_run_controls_are_greyed_with_the_sentence():
    parts = fragments(_between(preflight=PREFLIGHT), view(on_box=False, can_write=False))
    written = parts["controls"] + parts["pf-pill"] + parts["preflight"]

    buttons = re.findall(r"<button[^>]*data-cmd[^>]*>", written)
    assert buttons and all(" disabled" in tag for tag in buttons)
    assert CONTROLS_AT_THE_BOX in parts["controls"]


def test_the_control_bar_offers_the_task_the_trials_and_the_preflight_as_the_mockup_draws_them():
    """The mockup's toolbar (`task-sel`, `pf-pill`), with the run's trial count beside the
    task (the b3a-2 plan, decision 6): the select's options are a fragment, the count is
    static, and it starts at `wlx run --trials`'s default."""
    document = page(fragments(_between(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert '<label class="tsel" for="task-sel"><span class="k">Task</span><select id="task-sel" aria-label="task">' in document
    assert (
        f'<input class="field mono" id="run-trials" value="{RUN_TRIALS}" inputmode="numeric" '
        f'autocomplete="off" aria-label="trials">'
    ) in document
    assert RUN_TRIALS == 1000
    assert document.index('id="task-sel"') < document.index('id="pf-pill"') < document.index('id="controls"')
    assert "<h2>Pre-flight</h2>" in document and "<h2>Session</h2>" in document
    assert document.index('id="pf-panel"') < document.index('id="setup"')


def test_a_run_going_in_a_wlx_taskd_session_gives_no_hand_reward_until_xc_157():
    """XC-157: during a trial the rig refuses a manual reward, so the page greys the
    button with the reason -- a `wlx taskd` session's being a service is not enough."""
    controls = fragments(frame(service=True, phase="running", paused_at=None), view())["controls"]

    assert re.search(r'data-cmd="reward" disabled title="[^"]+"', controls)
    assert html.escape(REWARD_ONLY_PAUSED) in controls


HOSTILE = 'x"><b>'


def test_a_hostile_name_reaches_no_attribute_unescaped():
    """Every place a rig-supplied name becomes an attribute value or a label: the
    acknowledgement's `data-ack`, `data-task` on the panel and on *start run*, the
    option's value and label, and *start run*'s `title`."""
    preflight = Preflight(
        HOSTILE,
        (
            PreflightItem(HOSTILE, "unknown", "s"),
            PreflightItem(HOSTILE + "2", "fail", "s"),
        ),
    )
    shown = fragments(_between(preflight=preflight, offered_tasks=(HOSTILE,)), view())
    escaped = html.escape(HOSTILE)
    for name in ("preflight", "controls", "task-sel"):
        assert '"><b>' not in shown[name], name
    assert f'data-ack="{escaped}"' in shown["preflight"]
    assert f'<div class="pf" data-task="{escaped}">' in shown["preflight"]
    assert f'data-task="{escaped}"' in shown["controls"]
    assert f'title="pre-flight: {html.escape(HOSTILE + "2")} failing"' in shown["controls"]
    assert f'<option value="{escaped}">{escaped}</option>' == shown["task-sel"]
    assert fragments(idle(offered_tasks=(HOSTILE,)), view())["task-sel"] == shown["task-sel"]


def test_the_summary_ends_a_wlx_taskd_session_in_two_steps():
    """The b3a-2 plan, decision 12 (b3a-1 decision 6): *end session* while the session is
    open -- during a run too, which it stops first -- then *record return…*, the second
    step, while the return is awaited. A `wlx run` session's return is its terminal's."""
    open_ = (
        '<span class="pill neutral">open</span><button type="button" class="btn small '
        'danger" data-cmd="end" data-session="2027-01-14_01">end session</button>'
    )
    for phase in ("between_runs", "running"):
        assert fragments(_between(phase=phase), view())["end-actions"] == open_
    assert fragments(_between(phase="awaiting_return"), view())["end-actions"] == (
        '<span class="pill warn">ended · awaiting the return</span><button type="button" '
        'class="btn small danger" data-return="2027-01-14_01">record return…</button>'
    )
    assert fragments(_between(phase="closed"), view())["end-actions"] == (
        '<span class="pill ok">ended</span>'
    )
    assert "<button" not in fragments(frame(**STATES["awaiting return"]), view())["end-actions"]
    assert fragments(idle(), view())["end-actions"] == '<span class="pill neutral">none</span>'


def test_the_warning_is_answered_with_its_own_answers_naming_its_mark_and_session():
    """Spec §6.2: a far departure is confirmed or amended, a far return confirmed or
    typed again -- buttons for the frame's own answers, which the page's script sends
    only as the answer to this question (the b3a-2 plan, decision 10)."""
    departure = fragments(
        idle(question=Question("departure", "2027-01-14_01", 1.0, "far", ("confirm", "amend"))),
        view(),
    )["banners"]
    returning = fragments(
        _between(
            phase="awaiting_return",
            question=Question("return", "2027-01-14_01", 1.0, "far", ("confirm", "re-type")),
        ),
        view(),
    )["banners"]
    lan = fragments(
        idle(question=Question("departure", "2027-01-14_01", 1.0, "far", ("confirm", "amend"))),
        view(can_write=False),
    )["banners"]

    assert (
        '<button type="button" class="btn small" data-answer="confirm" data-mark="departure" '
        'data-session="2027-01-14_01">confirm</button>'
    ) in departure
    assert (
        '<button type="button" class="btn small" data-answer="amend" data-mark="departure" '
        'data-session="2027-01-14_01">amend…</button>'
    ) in departure
    assert (
        'data-answer="re-type" data-mark="return" data-session="2027-01-14_01">re-type</button>'
    ) in returning
    answers = re.findall(r"<button[^>]*data-answer[^>]*>", lan)
    assert answers and all(" disabled" in tag for tag in answers)


def test_the_end_tab_shows_the_closed_sessions_summary_from_an_idle_frame():
    """The b3a-2 final review, I2 (spec §6.2; the v12 mockup's `closed` state; §4.0 puts
    the supplement owed there): once the return is recorded the page is idle, and the End
    tab shows the closed session's summary, rendered as any closed frame's is, naming its
    session, until the next opens -- then *no session* again."""
    closed = frame(
        phase="closed", stop_kind="operator", stopped_because="stopped by jake",
        service=True, shortfall_ml=112.5, fluid_session_ml=0.3,
    )

    panes = fragments(idle(closed=closed), view())

    assert panes["end"] == fragments(closed, view())["end"], "one renderer for a closed frame"
    assert "Supplement owed" in panes["end"] and "112.50" in panes["end"]
    assert "2027-01-14_01" in panes["end-actions"] and "closed" in panes["end-actions"]
    assert "<script" not in fragments(
        idle(closed=replace(closed, session_id="<script>x", subject="<b>")), view()
    )["end-actions"]
    assert fragments(idle(), view())["end"] == fragments(None, view())["end"]
    assert fragments(idle(), view())["end-actions"] == '<span class="pill neutral">none</span>'


def test_the_closed_summary_keeps_an_unknown_day_unknown():
    closed = frame(phase="closed", stop_kind="operator", service=True, shortfall_ml=None, fluid_today_ml=None)

    end = fragments(idle(closed=closed), view())["end"]

    assert "0.00</span><span class=\"unit\">mL" not in end
    assert end == fragments(closed, view())["end"]


def test_a_stranded_animals_return_is_recorded_from_its_banner_naming_its_session():
    """XC-176: `Service._open`'s refusal says "Resume it, or record its return with End
    session, naming its session", and this is where its return is recorded. A record
    that cannot be read is repaired by hand first, so it has no button."""
    banners = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0), Stranded("2027-01-13_02", "", None))),
        view(),
    )["banners"]

    assert (
        '<button type="button" class="btn small danger" data-return="2027-01-13_01">'
        "end session…</button>"
    ) in banners
    assert 'data-return="2027-01-13_02"' not in banners
    assert "Idle" not in banners, "nothing opens while an animal is stranded"


def test_the_idle_page_offers_a_new_session_and_says_which_animals_and_tasks_there_are():
    """Spec §6.1: "the page shows *no session open* beside the form that opens one"; the
    mockup's Session panel has *new session* too. Greyed while an animal is stranded."""
    parts = fragments(idle(), view())
    stranded = fragments(idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0),)), view())
    button = '<button type="button" class="btn small primary" data-cmd="new">new session</button>'

    assert button in parts["banners"] and "no session open" in parts["banners"]
    assert button in parts["setup"]
    assert "<dt>animals</dt><dd>A, B</dd>" in parts["setup"]
    assert "<dt>tasks offered</dt><dd>fixation_detection.py</dd>" in parts["setup"]
    assert parts["dn-subject"] == (
        '<option value="">choose the animal</option>'
        '<option value="A">A</option><option value="B">B</option>'
    ), "the b3a-2 final review, I1: no animal is chosen until a person chooses one"
    assert re.search(r'data-cmd="new" disabled title="[^"]+">new session</button>', stranded["setup"])
    assert fragments(frame(), view())["dn-subject"] == '<option value="">no animal offered</option>'


def test_every_string_the_session_panes_show_is_escaped():
    parts = fragments(
        _between(
            session_id=EVIL,
            offered_tasks=(EVIL,),
            preflight=Preflight(EVIL, (PreflightItem(EVIL, "unknown", EVIL),)),
            question=Question(EVIL, EVIL, 1.0, EVIL, (EVIL,)),
        ),
        view(),
    )
    idle_parts = fragments(
        idle(animals=(EVIL,), offered_tasks=(EVIL,), stranded=(Stranded(EVIL, EVIL, 1.0),)),
        view(),
    )

    text = "".join(parts.values()) + "".join(idle_parts.values())
    assert "<script" not in text
    assert EVIL not in text


#: What a person types or chooses on the page's forms. Each is static, outside every
#: fragment, so no frame -- one a second while idle and between runs -- replaces it.
_TYPED = (
    "run-trials", "amend-to", "amend-why", "end-return", "ret-at",
    "dn-deployment", "dn-view", "dn-left", "dn-id", "dn-given",
)


def test_nothing_a_person_types_into_is_inside_a_fragment():
    """Review Focus 1 (the b3a-2 plan, decision 11)."""
    for parts in (fragments(_between(preflight=PREFLIGHT), view()), fragments(idle(), view())):
        document = page(parts, stale_after_s=30.0, nonce="n0nce", can_write=True)
        for name in _TYPED:
            assert document.count(f'id="{name}"') == 1, name
            assert not any(f'id="{name}"' in pane for pane in parts.values()), name


def test_the_new_session_dialog_asks_what_an_open_needs_and_offers_no_now_for_the_departure():
    """Spec §6.2's fields, in the mockup's `dlg-new` (the b3a-2 plan, decision 6): no rig
    and no "saved to" (`wlx taskd`'s are fixed), the id typed, and the departure empty --
    the terminal's parser has no `now` for it."""
    document = page(fragments(idle(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert re.search(r'<div class="scrim" id="dlg-new"[^>]*hidden>', document)
    for field, label in (
        ("dn-subject", "subject"), ("dn-deployment", "deployment"), ("dn-view", "setup"),
        ("dn-left", "←cage at"), ("dn-id", "id"), ("dn-given", "given today, mL"),
    ):
        assert f'<label class="sub" for="{field}">{label}</label>' in document, field
    assert '<option value="rig_fixed">head-fixed</option><option value="rig_chaired">chaired</option>' in document
    assert '<option value="direct">direct view</option><option value="stereoscope">stereoscope</option>' in document
    left = re.search(r'<input[^>]*id="dn-left"[^>]*>', document).group(0)
    assert " value=" not in left and "now" not in left
    assert '<button class="btn primary" id="dn-ok" type="button">open session</button>' in document
    assert "<title>xcon console</title>" in document and "expcontroller" not in document


def test_end_session_asks_first_and_takes_the_return_now_or_later():
    document = page(fragments(_between(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert "<h2>Summary</h2>" in document
    assert re.search(r'<div class="inline crit" id="end-confirm"[^>]*hidden>', document)
    assert html.escape(END_CONFIRM) in document
    assert END_CONFIRM.startswith("end the session?")
    assert "the head's release is recorded then" in END_CONFIRM
    assert "leave it blank" in END_CONFIRM
    assert re.search(r'<div class="inline info" id="return-form"[^>]*hidden>', document)
    assert re.search(r'<div class="inline info" id="amend-form"[^>]*hidden>', document)


def test_away_from_the_box_every_session_form_is_greyed():
    lan = page(fragments(_between(preflight=PREFLIGHT), view(can_write=False)), stale_after_s=30.0, nonce="n0nce")

    for control in (
        "task-sel", "run-trials", "dn-subject", "dn-deployment", "dn-view", "dn-left",
        "dn-id", "dn-given", "dn-ok", "end-return", "end-yes", "ret-at", "ret-yes",
        "amend-to", "amend-why", "amend-yes",
    ):
        assert re.search(r'id="' + control + r'"[^>]* disabled', lan), control


def test_away_from_the_box_every_session_button_in_a_fragment_is_greyed():
    """The fragments' own write buttons, as the static forms' are above: *end session*
    and *record return…* in the Summary, a stranded animal's *end session…*, *new
    session* in the banner and the Session panel, and the warning's answers -- each
    disabled on a page that may not write (fix round 1 of Task 5's review)."""
    lan = view(on_box=False, can_write=False)
    frames = (
        _between(),
        _between(
            phase="awaiting_return",
            question=Question("return", "2027-01-14_01", 1.0, "far", ("confirm", "re-type")),
        ),
        idle(),
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0),)),
    )
    written = "".join(
        parts["end-actions"] + parts["banners"] + parts["setup"]
        for parts in (fragments(shown, lan) for shown in frames)
    )

    buttons = re.findall(r"<button[^>]*data-(?:cmd|return|answer)[^>]*>", written)
    for needle in (
        'data-cmd="end"', 'data-return="2027-01-14_01"', 'data-return="2027-01-13_01"',
        'data-cmd="new"', 'data-answer="re-type"',
    ):
        assert any(needle in tag for tag in buttons), needle
    assert all(" disabled" in tag for tag in buttons)


def _function(name: str) -> str:
    """The body of the page script's function `name`, from its opening line to its own
    closing brace at two spaces' indent."""
    return re.search(rf"function {name}\((.*?)\) \{{(.*?)\n  \}}", _SCRIPT, re.S).group(2)


def _listener(element: str) -> str:
    """The body of the page script's click listener on `element`."""
    return re.search(
        rf'el\("{element}"\)\.addEventListener\("click", function \(\) \{{(.*?)\n  \}}\);',
        _SCRIPT,
        re.S,
    ).group(1)


def test_a_frame_keeps_the_option_chosen_in_a_select():
    """Review Focus 1: a frame re-renders the task and subject selects' options; the
    option a person chose stays chosen while it is still offered."""
    swap = _function("swap")

    assert 'var chosen = node && node.tagName === "SELECT" ? node.value : null;' in swap
    assert swap.index("var chosen") < swap.index("node.innerHTML = html;") < swap.index(
        "choose(node, chosen);"
    )
    assert 'if (id === "preflight") { restoreAcks(); }' in swap
    assert "if (option.value === value) { select.value = value; }" in _function("choose")


def test_no_acknowledgement_outlives_the_run_or_the_task_it_was_ticked_for():
    """Review Focus 4 (the b3a-2 plan, decision 9): the ticks are the person's, kept
    across a re-render, sent with the start, and cleared by a start or a new pre-flight."""
    take, start = _function("takePreflight"), _function("startRun")

    assert "acked = {};" in take and "acked = {};" in start
    assert start.index("acked = {};") < start.index("post(")
    assert 'if (box.checked) { acknowledged.push(box.getAttribute("data-ack")); }' in start
    assert (
        'else if (e.target.matches("input[data-ack]")) '
        '{ acked[e.target.getAttribute("data-ack")] = e.target.checked; }'
    ) in _SCRIPT
    assert "box.checked = acked[box.getAttribute(\"data-ack\")] === true;" in _function("restoreAcks")


def test_start_sends_the_task_whose_preflight_is_shown_and_only_while_it_is_chosen():
    """The b3a-2 plan, decision 8; the page's values are none, the task's own (decision 1)."""
    start = _function("startRun")

    assert "var button = el(\"controls\").querySelector('[data-cmd=\"start\"]');" in start
    assert 'var task = button ? button.getAttribute("data-task") : "";' in start
    assert "if (!task || task !== chosenTask()) {" in start
    assert "if (!Number.isInteger(trials) || trials < 1) {" in start
    assert (
        'post({ kind: "start", task: task, values: {}, trials: trials, acknowledged: acknowledged });'
    ) in start
    assert 'post({ kind: "check", task: task, values: {} });' in _function("takePreflight")
    assert 'else if (e.target.id === "task-sel") { if (betweenRuns()) { takePreflight(false); } }' in _SCRIPT


def test_a_new_session_is_sent_with_every_field_the_dialog_asks_as_typed():
    body = _function("openSession")

    for field in (
        'session_id: el("dn-id").value.trim(),',
        'animal: el("dn-subject").value,',
        'deployment: el("dn-deployment").value,',
        'view: el("dn-view").value,',
        'departure: el("dn-left").value.trim(),',
        "delivered_today: today,",
        "answer: null,",
        "amend_to: null,",
        'amend_reason: ""',
    ):
        assert field in body, field
    assert 'var today = given === "" ? null : Number(given);' in body
    assert "lastOpen = Object.assign({}, request);" in body
    assert body.index("lastOpen = Object.assign({}, request);") < body.index("post(")


def test_the_new_session_dialog_forgets_what_was_typed_once_the_session_it_sent_opens():
    """The b3a-2 final review, I1: the dialog reopened with the last session's departure,
    id and fluid given today -- a departure within thirty minutes of now is taken on trust,
    and the fluid figure feeds the day's floor. They are cleared, and the subject set back
    to its placeholder, **only once the page shows the session it sent open** (the
    Summary's *end session* names it), so a refused or unanswered open keeps what was
    typed for a retry, and no other frame clears it."""
    settle, swap, send = _function("settleOpen"), _function("swap"), _function("openSession")

    assert 'if (id === "end-actions") { settleOpen(); }' in swap
    assert "pendingOpen = request.session_id;" in send
    assert 'if (!request.animal) { el("dn-msg").textContent = "not sent: choose the animal"; return; }' in send
    assert "if (pendingOpen === null) { return; }" in settle
    assert (
        "var shown = el(\"end-actions\").querySelector('[data-cmd=\"end\"][data-session]');"
    ) in settle
    assert 'if (!shown || shown.getAttribute("data-session") !== pendingOpen) { return; }' in settle
    guard = settle.index('!== pendingOpen) { return; }')
    for cleared in ('el("dn-left").value = "";', 'el("dn-id").value = "";', 'el("dn-given").value = "";',
                    'el("dn-subject").value = "";', "pendingOpen = null;"):
        assert cleared in settle and settle.index(cleared) > guard, cleared
    assert "pendingOpen" not in _function("onFrame"), "not on every frame"


def test_a_preflight_items_sentence_takes_the_rows_width():
    """The b3a-2 final review, m4: the pre-flight's items were laid out in columns of at
    least 320 px, which left each sentence a sliver -- the pump calibration's wrapped
    about twenty lines. One item per row, across the panel; and the end confirmation's
    return field is wide enough for its placeholder."""
    from wl_xcon.web import _CSS

    pf = re.search(r"\n\.pf \{([^}]*)\}", _CSS).group(1)
    assert "auto-fill" not in pf and "grid-template-columns: minmax(0, 1fr);" in pf
    width = re.search(r"#end-return \{ width: (\d+)ch; \}", _CSS)
    assert width and int(width.group(1)) >= len("now, HH:MM, or blank for later")


def test_a_message_for_the_dialog_is_shown_in_it_not_behind_its_scrim():
    """Task 6's deferred point, with I3: while *New session* is open, `post`'s own "not
    sent: give your name" went to the control bar's line behind the dialog's scrim."""
    tell = _function("tell")

    assert 'if (!el("dlg-new").hidden) { el("dn-msg").textContent = text; }' in tell


def test_choosing_a_task_takes_the_preflight_only_between_runs():
    """The b3a-2 final review, m1: choosing a task sent a check in every phase, and each
    put a refusal on the feed while idle, running or awaiting the return. The pre-flight
    pill is a button only between runs (`_pf_pill`), and the script reads that."""
    assert "return Boolean(el(\"pf-pill\").querySelector('[data-cmd=\"check\"]'));" in _function("betweenRuns")
    assert 'data-cmd="check"' in fragments(_between(), view())["pf-pill"]
    for outside in (frame(service=True), _between(phase="awaiting_return"), idle(), None):
        assert 'data-cmd="check"' not in fragments(outside, view())["pf-pill"]


def test_an_answer_re_sends_the_time_as_typed_and_only_for_a_warning_this_page_raised():
    """The b3a-2 plan, decision 10: *confirm* re-sends the open or the return this page
    sent, with its answer; *amend…* the open with the corrected time and the reason; a
    warning whose session this page did not send is not answered."""
    body = _function("answerWarning")

    assert 'if (given === "re-type") { openReturn(session); return; }' in body
    assert 'var sent = which === "departure" ? lastOpen : lastEnd;' in body
    assert "if (!sent || sent.session_id !== session) {" in body
    assert body.index("if (!sent || sent.session_id !== session) {") < body.index("post(")
    assert 'Object.assign({}, sent, { answer: "confirm" })' in body
    assert "Object.assign({}, sent, { confirm: true })" in body
    assert (
        'post(Object.assign({}, lastOpen, { answer: "amend", amend_to: '
        'el("amend-to").value.trim(), amend_reason: el("amend-why").value.trim() }));'
    ) in _listener("amend-yes")


def test_end_session_sends_the_return_as_typed_or_later_and_a_return_needs_a_time():
    """The b3a-2 plan, decision 12: step one's return may be left blank for later; the
    return form's may not."""
    end, ret = _listener("end-yes"), _listener("ret-yes")

    assert 'returned: returned === "" ? null : returned, confirm: false' in end
    assert 'if (returned !== "") { lastEnd = Object.assign({}, request); }' in end
    assert (
        'if (!returned) { tell("not sent: give the time the animal went back into its home '
        'cage, or now", "crit"); return; }'
    ) in ret
    assert "lastEnd = Object.assign({}, request);" in ret


def test_the_session_forms_are_opened_from_the_buttons_the_panes_render():
    command = re.search(r"function command\(cmd\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)

    for line in (
        'else if (cmd === "new") { openNew(); }',
        'else if (cmd === "check") { takePreflight(true); }',
        'else if (cmd === "start") { startRun(); }',
        'else if (cmd === "end") { askEnd(); }',
    ):
        assert line in command, line
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)
    assert 'var answering = e.target.closest("[data-answer]");' in handler
    assert 'openReturn(returning.getAttribute("data-return"))' in handler
    assert handler.index("[data-answer]") < handler.index("[data-cmd]")


def test_end_session_opens_its_confirmation_and_posts_nothing_until_end_yes():
    """One click on *end session* once posted `{kind: "end"}` and ended the session with
    no confirmation. Now only the confirmation's *end-yes* (or the return form's *ret-yes*)
    posts an end; every function a button opens a form with posts nothing."""
    command = re.search(r"function command\(cmd\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)

    assert 'else if (cmd === "end") { askEnd(); }' in command
    assert 'else { post({ kind: cmd }); }' in command
    assert command.index('cmd === "end"') < command.index("post({ kind: cmd })")
    for opener in ("askEnd", "openNew", "openReturn"):
        assert "post(" not in _function(opener), opener
    assert 'el("end-confirm").hidden = false;' in _function("askEnd")
    assert 'el("dlg-new").hidden = false;' in _function("openNew")
    assert 'el("return-form").hidden = false;' in _function("openReturn")
    assert "returnFor = session;" in _function("openReturn")
    assert 'kind: "end"' not in re.sub(
        r'el\("(end-yes|ret-yes)"\)\.addEventListener\("click".*?\n  \}\);', "", _SCRIPT, flags=re.S
    )



def test_a_resumable_stranded_session_offers_resume_beside_end_and_a_refused_one_says_why():
    """XC-026 Task 5: *resume session* is offered only when the record can carry one; a
    session that cannot be resumed says why, escaped, and keeps *end session...*."""
    can = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0, resumable=True),)), view()
    )["banners"]
    cannot = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0, False, "no <i>fluid</i> record"),)),
        view(),
    )["banners"]

    assert 'data-resume="2027-01-13_01"' in can and 'data-return="2027-01-13_01"' in can
    assert "It cannot be resumed" not in can
    assert 'data-resume=' not in cannot and 'data-return="2027-01-13_01"' in cannot
    assert "It cannot be resumed: no &lt;i&gt;fluid&lt;/i&gt; record." in cannot
    assert "<i>fluid" not in cannot
    assert "no session opens until it is resumed or its return recorded" in can
    assert "no session opens until it is resumed or its return recorded" in cannot


def test_a_resumed_session_says_so_in_its_banner_and_its_closed_summary():
    resumed = frame(resumed_at=1_700_000_000.0)
    clock = _clock_time(1_700_000_000.0)[:5]
    sentence = f"this session was resumed after its process stopped, at {clock}"

    banners = fragments(resumed, view())["banners"]
    closed = replace(resumed, phase="closed", stop_kind="operator", service=True)

    assert "Resumed" in banners and sentence in banners
    assert "Resumed" not in fragments(frame(), view())["banners"]
    assert sentence in fragments(closed, view())["end"]
    assert sentence in fragments(idle(closed=closed), view())["end"]
    assert "resumed" not in fragments(replace(closed, resumed_at=None), view())["end"]


def test_the_pages_script_posts_resume_session_for_a_click_on_resume():
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)

    assert 'var resuming = e.target.closest("[data-resume]");' in handler
    assert (
        'post({ kind: "resume_session", session_id: resuming.getAttribute("data-resume") })'
    ) in handler
    assert handler.index("[data-resume]") < handler.index("[data-return]")
