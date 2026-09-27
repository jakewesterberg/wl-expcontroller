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
import tomllib
from importlib import resources
from pathlib import Path

import pytest

from _frames import frame, view
from wl_expcontroller.link import ParamRow, Refused, Staged
from wl_expcontroller.web import FONTS, FRAGMENT_IDS, LEGEND, font_bytes, fragments, page

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


def test_before_the_first_trial_the_strip_says_so_not_zero():
    """I1 (fix round 1): `_correct`'s early return for `trial_index == 0` is the
    strip's own guard against a 0/0 percentage -- no test exercised it until this
    round."""
    strip = fragments(frame(trial_index=0, outcomes={}), view())["strip"]

    assert (
        '<span class="lab">Correct / trials</span>'
        '<span class="val"><span class="nm">no trials yet</span></span>' in strip
    )
    assert "0/0" not in strip
    assert "0%" not in strip
    assert "NaN" not in strip


def test_out_of_cage_time_with_no_published_limit_shows_the_clock_alone():
    """M2 (fix round 1): `_out_of_cage`'s other guarded branch -- elapsed time
    published, but no limit -- a rig session whose ceiling was not sent. Shown as
    the clock alone: no bar, and no limit in the label."""
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
    assert "welfare ceiling 0.40 mL" in params
    assert "0.10 to 1.00 s" in params
    assert "open to 5.00 deg" in params
    assert "no declared range" in params
    assert "unset" in params
    assert "penguin" in params


def test_setup_names_the_configuration_and_what_has_no_source():
    setup = fragments(frame(allocation="", bounds_config=""), view())["setup"]

    assert "tasks/fixation_detection.py" in setup
    assert "provisional: none given" in setup
    assert '<dt>bounds config</dt><dd><span class="nm">not given</span></dd>' in setup
    assert setup.count("no source yet") == 2
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
    fonts = resources.files("wl_expcontroller").joinpath("fonts")

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
    globs = table["package-data"]["wl_expcontroller"]

    for font in FONTS:
        for rel in (f"fonts/{font.directory}/{font.file}", f"fonts/{font.directory}/OFL.txt"):
            assert any(fnmatch.fnmatch(rel, pattern) for pattern in globs), rel


def test_the_nonce_is_escaped_into_its_attribute():
    document = page(fragments(frame(), view()), stale_after_s=30.0, nonce='x"><b>')

    assert '<script nonce="x&quot;&gt;&lt;b&gt;">' in document


def test_the_page_tells_its_script_when_a_stream_is_stale():
    document = page(fragments(frame(), view()), stale_after_s=45.0, nonce="n0nce")

    assert '<body data-stale-after="45">' in document


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


def test_nothing_on_the_page_writes():
    """Spec §4.2: every write control is absent until its slice. The page's buttons
    close and reopen its own stream; its inputs only choose a tab."""
    document = _document()

    assert document.count("<button") == 2
    assert 'id="close"' in document and 'id="reconnect"' in document
    for absent in ("<form", "<textarea", "<select", "POST", "fetch("):
        assert absent not in document, absent
    inputs = re.findall(r"<input[^>]*>", document)
    assert len(inputs) == 4
    assert all('type="radio"' in field for field in inputs)


def test_the_script_does_only_what_spec_4_3_asks():
    document = _document()

    for needle in (
        'new EventSource("/events")',
        'addEventListener("frame"',
        "innerHTML",
        "stream stale · last frame ",
        "stream lost",
        'el("close")',
        'el("reconnect")',
        "source.close()",
    ):
        assert needle in document, needle
    assert "disconnected · the session keeps running on the box" in document


def test_the_stream_banner_and_the_disconnect_dialog_start_hidden():
    document = _document()

    assert '<div class="banner" id="stream" role="status" hidden></div>' in document
    assert re.search(r'<div class="scrim" id="gone"[^>]*hidden>', document)
