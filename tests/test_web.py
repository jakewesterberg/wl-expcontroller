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
from importlib import resources
from pathlib import Path

import pytest

from _frames import frame, view
from wl_xcon.link import Control, ParamRow, Refused, ScheduledStop, Staged
from wl_xcon.web import (
    _SCRIPT,
    CONTROLS_AT_THE_BOX,
    DEBOUNCE_MS,
    FONTS,
    FRAGMENT_IDS,
    LEGEND,
    NO_MARK_ENDPOINT,
    REWARD_ONLY_PAUSED,
    font_bytes,
    fragments,
    page,
)

LIMIT = "out_of_cage: subject 'A' has been out of its cage 43201 s against a ceiling of 43200"

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
    strip no longer carries them (spec §4.0) -- so Runtime and End of session both
    must, in every state, a zero volume included."""
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

    assert "cage-side · no limit" in parts["strip"]
    assert "cage-side · no out-of-cage interval" in parts["end"]
    assert "0:00" not in parts["strip"] + parts["end"]


def test_the_duration_warning_is_never_dropped():
    warning = "out_of_cage: subject 'A' has 900 s left of its 43200 s out of the cage"

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
    assert "trials/min not yet derived" in strip
    assert "0.0 trials/min" not in strip
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
        '<span class="lab">Since last reward</span><span class="val">42 s</span>'
        in parts["strip"]
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
        '<span class="lab">Since last reward</span>'
        '<span class="val"><span class="nm">unknown</span></span>' in parts["strip"]
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


def test_before_the_first_trial_the_strip_says_so_not_zero():
    """Before the first trial the strip's correct cell says *no trials yet*: its
    percentage would be 0/0, and neither `0%` nor `NaN` may stand in for a count
    nobody has made."""
    strip = fragments(frame(trial_index=0, outcomes={}), view())["strip"]

    assert (
        '<span class="lab">Correct / trials</span>'
        '<span class="val"><span class="nm">no trials yet</span></span>' in strip
    )
    assert "0/0" not in strip
    assert "0%" not in strip
    assert "NaN" not in strip


def test_out_of_cage_time_with_no_published_limit_shows_the_clock_alone():
    """A rig session whose frame carries its out-of-cage time but no limit shows the
    clock alone: no bar, and no limit in the label, since a bar needs something to
    be a fraction of."""
    strip = fragments(frame(out_of_cage_limit_s=None), view())["strip"]

    assert (
        '<div><div class="row"><span class="lab">Out of cage</span>'
        '<span class="val">1:23:45</span></div></div>' in strip
    )
    assert "Out of cage /" not in strip


# --- counts, ticks, and the strip's arithmetic ----------------------------------


def test_the_strips_correct_counts_correct_and_correct_reject():
    """The one rollup (PI, 2026-09-26, spec §3): on the strip, `correct` plus
    `correct_reject` -- 3 and 2 of 10 trials read 5 / 10, 50%."""
    parts = fragments(
        frame(
            trial_index=10,
            outcomes={"correct": 3, "correct_reject": 2, "no_fixation": 5},
        ),
        view(trials_per_min=12.0),
    )

    strip = parts["strip"]
    assert '5<span class="u">/ 10</span>' in strip
    assert "50% correct" in strip
    assert "12.0 trials/min, derived by wlx serve" in strip


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
    assert "250.00 mL" in setup and "12:00:00" in setup


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
    )

    text = "".join(fragments(evil, view(rejected=EVIL)).values())

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
    assert '<button type="button" class="btn danger" data-cmd="stop">stop…</button>' in controls
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


def test_with_nothing_scheduled_the_strip_keeps_its_four_cells():
    strip = fragments(frame(), view())["strip"]

    assert "Scheduled" not in strip
    assert strip.count('<div class="row">') == 4


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


def test_the_reward_button_is_live_only_while_paused_and_greyed_otherwise():
    """PI, 2026-09-28: a manual reward during a pause. The button works only while the
    session is paused (`paused_at`), and otherwise says why: greyed with its reason
    while trials run, with the §2 sentence away from the box, and gone once the
    session has ended. One button and no key: a click is one command."""
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
