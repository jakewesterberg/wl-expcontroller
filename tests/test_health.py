"""`GET /health`'s body (P4d-2b spec §3): the verdict table, the readings, and the
contract against `wl-preproc`'s own `HealthResponse`.

**The contract tests are not allowed to skip in CI.** A missing `wl-preproc`
checkout skips them locally and fails them under `WLX_REQUIRE_PREPROC=1`, the same
guard `test_gaze.py` and `test_calibration.py` use: a `/health` wl-works might refuse
is not a `/health`.
"""

from __future__ import annotations

import itertools
import json
import os

import pytest

from _frames import ENDPOINT, frame
from wl_expcontroller.health import (
    HEALTH_SCHEMA,
    ago,
    expects_frames,
    families,
    family_key,
    plain_text,
    readings,
    response,
    verdict,
)

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts.protocol import SCHEMA_VERSION, HealthResponse
    from wl_preproc.contracts.protocol import plain_text as their_plain_text
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). /health "
            f"is only useful if wl-works accepts it, and wl-preproc's HealthResponse is "
            f"the model it is checked against"
        ) from exc
    HealthResponse = None

_contract = pytest.mark.skipif(
    HealthResponse is None, reason="wl-preproc checkout not beside this repo"
)

WARNING = (
    "out_of_cage: subject 'A' has 900 s left of its 43200 s out of the cage; finish "
    "the block and start bringing the animal back"
)
LIMIT = (
    "out_of_cage: subject 'A' has been out of its cage 43201 s against a ceiling of "
    "43200"
)

#: `(frame, seconds since it arrived)` for every row of spec §3's verdict table, and
#: the absences and markup a reading must survive.
CASES = {
    "no session": (None, None),
    "running": (frame(), 1.0),
    "warning": (frame(duration_warning=WARNING), 1.0),
    "stale": (frame(), 45.0),
    "ended by the limit": (frame(stop_kind="limit", stopped_because=LIMIT), 1.0),
    "completed": (
        frame(stop_kind="completed", stopped_because="every block is finished"),
        45.0,
    ),
    "awaiting return": (
        frame(
            stop_kind="completed",
            stopped_because="every block is finished",
            phase="awaiting_return",
        ),
        1.0,
    ),
    "returned after the limit": (
        frame(stop_kind="limit", stopped_because=LIMIT, phase="closed"),
        1.0,
    ),
    "fault": (
        frame(
            stop_kind="fault",
            stopped_because="fault, session aborted: RuntimeError: solenoid did not answer",
        ),
        1.0,
    ),
    "cage-side": (
        frame(
            deployment="cage_side",
            out_of_cage_seconds=None,
            out_of_cage_limit_s=None,
            chair_seconds=None,
        ),
        1.0,
    ),
    "markup": (
        frame(
            session_id="<b>&",
            subject="A<B>",
            task="t&t.py",
            stop_kind="operator",
            stopped_because="stopped by <script>",
        ),
        1.0,
    ),
}

EXPECTED = {
    "no session": "ok",
    "running": "ok",
    "warning": "degraded",
    "stale": "degraded",
    "ended by the limit": "degraded",
    "completed": "ok",
    "awaiting return": "ok",
    "returned after the limit": "ok",
    "fault": "down",
    "cage-side": "ok",
    "markup": "ok",
}


def _readings(case: str) -> dict:
    found, age = CASES[case]
    return {
        r["key"]: r
        for r in readings(
            found, frame_age_s=age, stale_after_s=30.0, rejected=None, endpoint=ENDPOINT
        )
    }


# --- the verdict: spec §3's table -------------------------------------------


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_verdict_follows_the_specs_table(case):
    found, age = CASES[case]

    assert (
        verdict(found, frame_age_s=age, stale_after_s=30.0, rejected=None)
        == EXPECTED[case]
    )


def test_a_rig_session_awaiting_its_return_that_goes_quiet_is_degraded():
    """Its out-of-cage clock is published once a second until the return (P4d-2a);
    silence then means nobody can see an animal that is still out."""
    awaiting, _ = CASES["awaiting return"]

    assert (
        verdict(awaiting, frame_age_s=45.0, stale_after_s=30.0, rejected=None)
        == "degraded"
    )


def test_an_ended_sessions_last_frame_is_its_last_and_never_stale():
    completed, _ = CASES["completed"]

    assert not expects_frames(completed)
    assert expects_frames(frame())
    assert not expects_frames(None)


def test_a_fault_is_down_even_after_the_return_and_beside_a_warning():
    faulted = frame(
        stop_kind="fault",
        stopped_because="fault after the loop",
        phase="closed",
        duration_warning=WARNING,
    )

    assert (
        verdict(faulted, frame_age_s=1.0, stale_after_s=30.0, rejected=None) == "down"
    )


def test_unknown_is_never_emitted():
    """`unknown` is wl-works' word for a host that went silent; a host answering the
    request cannot be silent (wl-preproc `docs/ops/lab-host-protocol.md`)."""
    for found, age in CASES.values():
        for stale_after, rejected in itertools.product((0.5, 30.0), (None, REFUSED)):
            assert verdict(
                found, frame_age_s=age, stale_after_s=stale_after, rejected=rejected
            ) in {
                "ok",
                "degraded",
                "down",
            }


# --- the readings ------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(CASES))
def test_exactly_one_reading_is_featured(case):
    """wl-works' Plan 10 §4: of several featured readings, the first wins -- so this
    host features one, the most urgent (PI, 2026-09-26, spec §3)."""
    assert sum(r["featured"] for r in _readings(case).values()) == 1


@pytest.mark.parametrize(
    ("case", "key"),
    [
        ("no session", "state"),
        ("running", "out_of_cage"),
        ("warning", "duration_warning"),
        ("stale", "last_frame"),
        ("ended by the limit", "state"),
        ("fault", "state"),
        ("cage-side", "state"),
    ],
)
def test_the_featured_reading_is_the_one_that_drove_the_verdict(case, key):
    featured = [k for k, r in _readings(case).items() if r["featured"]]

    assert featured == [key]


def test_the_readings_come_in_the_specs_order():
    keys = [
        r["key"]
        for r in readings(
            frame(duration_warning=WARNING, outcomes={"correct": 30, "no_fixation": 8}),
            frame_age_s=2.0,
            stale_after_s=30.0,
            rejected=None,
            endpoint=ENDPOINT,
        )
    ]

    assert keys == [
        "session",
        "state",
        "out_of_cage",
        "duration_warning",
        "fluid_session",
        "supplement",
        "trials",
        "outcomes_target",
        "outcomes_no_engagement",
        "hangs",
        "last_frame",
    ]


def test_the_readings_say_what_a_person_needs_to_know():
    values = {
        r["key"]: r["value"]
        for r in readings(
            frame(),
            frame_age_s=3.0,
            stale_after_s=30.0,
            rejected=None,
            endpoint=ENDPOINT,
        )
    }

    assert values["session"] == "2027-01-14_01 · A · tasks/fixation_detection.py"
    assert values["state"] == "running · trial 40 · block session"
    assert values["out_of_cage"] == "1:23:45 of 12:00:00"
    assert values["fluid_session"] == "1.25 mL"
    assert values["supplement"] == "188.75 mL"
    assert values["trials"] == "40"
    assert values["outcomes_target"] == "correct 30"
    assert values["outcomes_breaks"] == "fixation_break 2"
    assert values["hangs"] == "0"
    assert values["last_frame"] == "3 s ago"


def test_an_ended_session_gives_its_reason_and_where_the_animal_is():
    def state(**overrides):
        found = frame(stop_kind="completed", stopped_because="every block is finished", **overrides)
        return {
            r["key"]: r["value"]
            for r in readings(
                found,
                frame_age_s=1.0,
                stale_after_s=30.0,
                rejected=None,
                endpoint=ENDPOINT,
            )
        }["state"]

    assert state() == "ended (completed): every block is finished"
    assert state(phase="awaiting_return") == (
        "ended (completed): every block is finished · awaiting the return to the cage"
    )
    assert state(phase="closed") == (
        "ended (completed): every block is finished · returned to the cage"
    )


def test_absences_are_sentences_never_zeros():
    found = frame(
        deployment="cage_side",
        out_of_cage_seconds=None,
        out_of_cage_limit_s=None,
        shortfall_ml=None,
    )
    values = {
        r["key"]: r["value"]
        for r in readings(
            found,
            frame_age_s=None,
            stale_after_s=30.0,
            rejected=None,
            endpoint=ENDPOINT,
        )
    }

    assert values["out_of_cage"] == "cage-side, no limit"
    assert values["supplement"] == "unknown: the day's prior total was not supplied"
    assert values["last_frame"] == "none received"


def test_with_no_session_it_says_so():
    values = {
        r["key"]: r["value"]
        for r in readings(
            None, frame_age_s=None, stale_after_s=30.0, rejected=None, endpoint=ENDPOINT
        )
    }

    assert values == {
        "session": "none attached · no frame has arrived on tcp://127.0.0.1:5571",
        "state": "waiting for the session's telemetry",
        "last_frame": "none received",
    }


# --- a refused frame (Ruling 11, 2026-09-27) --------------------------------------

#: `Hub.reject`'s reason for a schema-6 `wlx run`, with markup to be spelled out.
REFUSED = "a telemetry frame carried schema 6 <b>&"


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_refusal_degrades_the_verdict_at_once_unless_the_held_frame_faulted(case):
    """Ruling 11: a frame this console could not read means it cannot see the
    session, whatever the frame it still holds says -- `degraded` at once, not after
    `--stale-after`. A held fault stays `down`: a refusal never lowers a verdict."""
    found, age = CASES[case]

    assert verdict(found, frame_age_s=age, stale_after_s=30.0, rejected=REFUSED) == (
        "down" if EXPECTED[case] == "down" else "degraded"
    )


@pytest.mark.parametrize("case", sorted(CASES))
def test_with_a_refusal_exactly_one_reading_is_still_featured(case):
    found, age = CASES[case]
    rows = readings(
        found, frame_age_s=age, stale_after_s=30.0, rejected=REFUSED, endpoint=ENDPOINT
    )

    assert sum(r["featured"] for r in rows) == 1


@pytest.mark.parametrize(
    ("case", "key"),
    [
        ("no session", "refused"),
        ("running", "refused"),
        ("warning", "duration_warning"),
        ("stale", "refused"),
        ("ended by the limit", "state"),
        ("completed", "refused"),
        ("awaiting return", "refused"),
        ("returned after the limit", "refused"),
        ("fault", "state"),
        ("cage-side", "refused"),
        ("markup", "refused"),
    ],
)
def test_a_refusal_is_featured_after_the_warning_and_the_unreturned_state(case, key):
    """Ruling 11's place in `_featured`'s ruled order: after the duration warning
    and the state of a session that faulted or ended on the limit with the animal
    not back, and before the last frame's age -- so a stale held frame features the
    refusal, which says why no new frame is shown."""
    found, age = CASES[case]
    featured = [
        r["key"]
        for r in readings(
            found,
            frame_age_s=age,
            stale_after_s=30.0,
            rejected=REFUSED,
            endpoint=ENDPOINT,
        )
        if r["featured"]
    ]

    assert featured == [key]


def test_a_refusal_is_a_reading_after_the_state_in_plain_text():
    rows = readings(
        frame(),
        frame_age_s=1.0,
        stale_after_s=30.0,
        rejected=REFUSED,
        endpoint=ENDPOINT,
    )

    assert [r["key"] for r in rows][:4] == [
        "session",
        "state",
        "refused",
        "out_of_cage",
    ]
    refused = next(r for r in rows if r["key"] == "refused")
    assert refused["label"] == "Refused"
    assert refused["value"] == "a telemetry frame carried schema 6 (lt)b(gt)(amp)"


def test_without_a_refusal_there_is_no_refused_reading():
    for found, age in CASES.values():
        keys = {
            r["key"]
            for r in readings(
                found,
                frame_age_s=age,
                stale_after_s=30.0,
                rejected=None,
                endpoint=ENDPOINT,
            )
        }
        assert "refused" not in keys


@_contract
@pytest.mark.parametrize("case", sorted(CASES))
def test_a_body_with_a_refusal_is_wl_preprocs_health_response(case):
    found, age = CASES[case]
    body = json.dumps(
        response(
            found,
            frame_age_s=age,
            stale_after_s=30.0,
            rejected=REFUSED,
            endpoint=ENDPOINT,
        )
    )

    parsed = HealthResponse.model_validate_json(body)

    assert parsed.verdict == ("down" if EXPECTED[case] == "down" else "degraded")


def test_with_no_frame_the_session_reading_names_the_endpoint_it_reads():
    """m4: "none attached" alone could be read as "nothing is publishing", which this
    console cannot know; it names the PUB endpoint nothing has arrived on, in plain
    text like every other value."""
    values = {
        r["key"]: r["value"]
        for r in readings(
            None,
            frame_age_s=None,
            stale_after_s=30.0,
            rejected=None,
            endpoint="tcp://<box>&:5571",
        )
    }

    assert values["session"] == (
        "none attached · no frame has arrived on tcp://(lt)box(gt)(amp):5571"
    )


def test_with_a_refusal_and_no_frame_it_never_says_nothing_arrived():
    """Something did arrive: a frame this console could not read (Ruling 11)."""
    values = {
        r["key"]: r["value"]
        for r in readings(
            None,
            frame_age_s=None,
            stale_after_s=30.0,
            rejected=REFUSED,
            endpoint="tcp://127.0.0.1:5571",
        )
    }

    # The PI's wording (2026-09-27): something is sending, so "none attached" was
    # wrong; what the console cannot do is read it.
    assert values["session"] == (
        "a session is sending on tcp://127.0.0.1:5571, but in a format this console "
        "cannot read"
    )
    assert values["state"] == "waiting for a frame this console can read"


def test_markup_in_a_value_is_spelled_out_as_wl_preproc_does():
    """Review Focus 2. A session id is text an operator chose, and wl-preproc's
    `Reading` refuses markup in a value outright -- so it is spelled out, never
    dropped and never sent."""
    values = {key: r["value"] for key, r in _readings("markup").items()}

    assert values["session"] == "(lt)b(gt)(amp) · A(lt)B(gt) · t(amp)t.py"
    assert values["state"] == "ended (operator): stopped by (lt)script(gt)"
    assert not any(c in "".join(values.values()) for c in "<>&")


def test_counts_are_grouped_by_family_and_never_summed():
    """No rollup (PI, 2026-09-26), and Review Focus 3: an outcome this build does not
    know is shown under Other, never dropped."""
    grouped = families(
        {"correct": 30, "early_response": 2, "no_fixation": 8, "from_a_newer_taskd": 1}
    )

    assert grouped == [
        ("target", "Target", [("correct", 30), ("early_response", 2)]),
        ("no_engagement", "No engagement", [("no_fixation", 8)]),
        ("other", "Other", [("from_a_newer_taskd", 1)]),
    ]


def test_the_strips_rollup_never_reaches_health():
    """The PI's one rollup -- `correct` plus `correct_reject` -- is the strip's alone
    (2026-09-26, spec §3). `/health` counts every outcome as it occurred."""
    values = {
        r["key"]: r["value"]
        for r in readings(
            frame(
                trial_index=10,
                outcomes={"correct": 3, "correct_reject": 2, "no_fixation": 5},
            ),
            frame_age_s=1.0,
            stale_after_s=30.0,
            rejected=None,
            endpoint=ENDPOINT,
        )
    }

    assert values["trials"] == "10"
    assert values["outcomes_target"] == "correct 3"
    assert values["outcomes_withhold"] == "correct_reject 2"
    assert not any("correct 5" in value for value in values.values())


def test_a_wire_string_names_its_family():
    assert family_key("fixation_break") == "breaks"
    assert family_key("tracker_lost") == "rig"
    assert family_key("no_response") == "no_engagement"
    assert family_key("hang") == "hang"
    assert family_key("from_a_newer_taskd") == "other"


def test_ages_read_as_a_person_reads_them():
    assert ago(42.9) == "42 s"
    assert ago(600.0) == "10 min"
    assert ago(7200.0) == "2:00:00"
    assert ago(-3.0) == "0 s"


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"]
)
def test_an_age_that_is_not_a_number_reads_unknown(value):
    """m1: `ago` raised `ValueError` on NaN and `OverflowError` on an infinity."""
    assert ago(value) == "unknown"


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf")], ids=["nan", "inf"]
)
def test_readings_survive_a_non_finite_reward_instant_and_frame_age(value):
    """m1 through `readings`: a frame whose `last_reward_at` is not a number, aged by
    a number that is not one either, still gives every reading, the age as a word."""
    values = {
        r["key"]: r["value"]
        for r in readings(
            frame(last_reward_at=value),
            frame_age_s=value,
            stale_after_s=30.0,
            rejected=None,
            endpoint=ENDPOINT,
        )
    }

    assert values["last_frame"] == "unknown"
    assert values["session"] == "2027-01-14_01 · A · tasks/fixation_detection.py"


def test_plain_text_spells_out_the_three_characters():
    assert plain_text("A&B<C>") == "A(amp)B(lt)C(gt)"


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("rejected", [None, "a telemetry frame carried schema 6"])
def test_no_action_is_ever_offered(case, rejected):
    """ADR-0008: no welfare action goes through wl-works."""
    found, age = CASES[case]

    assert (
        response(
            found,
            frame_age_s=age,
            stale_after_s=30.0,
            rejected=rejected,
            endpoint=ENDPOINT,
        )[
            "actions"
        ]
        == []
    )


# --- the contract: wl-preproc's own model -------------------------------------


@_contract
@pytest.mark.parametrize("case", sorted(CASES))
def test_the_body_is_wl_preprocs_health_response(case):
    found, age = CASES[case]
    body = json.dumps(
        response(
            found, frame_age_s=age, stale_after_s=30.0, rejected=None, endpoint=ENDPOINT
        )
    )

    parsed = HealthResponse.model_validate_json(body)

    assert parsed.verdict == EXPECTED[case]
    assert parsed.actions == []


@_contract
def test_our_plain_text_is_theirs():
    for text in ("A&B", "<script>alert(1)</script>", "a>b<c&d", "plain", "", "(lt)"):
        assert plain_text(text) == their_plain_text(text), text


@_contract
def test_our_schema_version_is_theirs():
    assert HEALTH_SCHEMA == SCHEMA_VERSION


def test_a_paused_session_is_said_to_be_paused_and_is_ok():
    """P4d-2b b2a: a pause is a person's choice, not a fault, so the verdict stands;
    the state reading says it, so wl-works does not read a held trial count as a
    stalled rig."""
    found = frame(paused_at=1_700_000_030.0)
    values = {
        r["key"]: r["value"]
        for r in readings(
            found, frame_age_s=1.0, stale_after_s=30.0, rejected=None, endpoint=ENDPOINT
        )
    }

    assert values["state"] == "paused · trial 40 · block session"
    assert verdict(found, frame_age_s=1.0, stale_after_s=30.0, rejected=None) == "ok"
