"""`marks` -- the departure and the return, decided once for `wlx run`'s terminal and
`wlx taskd`'s page (P4d-2b spec §6.2: "One shared piece of code decides"). Every rule
is `welfare`'s; these pin the decision made around it, which both callers now share."""

from __future__ import annotations

import argparse
import json

import pytest

from _sessions import WALL, session, typed
from wl_xcon import cli, marks
from wl_xcon.bounds import Exceeded
from wl_xcon.welfare import CONFIRM_MARK_WITHIN

FAR = CONFIRM_MARK_WITHIN + 600


def _rows(made) -> list[dict]:
    path = made.directory / "welfare_notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _kinds(made) -> list[str]:
    return [row["kind"] for row in _rows(made)]


def _departed(tmp_path):
    """A session whose departure, three hours ago, a person confirmed."""
    made = session(tmp_path)
    marks.depart(
        made,
        marks.decide_departure(
            made, WALL - 3 * 3600, marks.Confirm(by="jake", how="t"), by="jake", how="t"
        ),
    )
    return made


def test_the_terminal_and_the_page_read_a_time_with_one_parser():
    """Spec §6.2: "the service parses it with the terminal's own parser"."""
    assert cli._wall_clock_time is marks.clock_time
    assert cli._clock_or_now is marks.clock_or_now
    assert cli._TIME_FORMATS == marks.TIME_FORMATS


def test_a_near_departure_is_taken_as_given_and_writes_no_confirmation(tmp_path):
    made = session(tmp_path)

    decision = marks.decide_departure(made, WALL - 60, None, by="jake", how="--out-of-cage-at")
    marks.depart(made, decision)
    marks.record_departure(made, decision)

    assert (decision.at, decision.confirmed, decision.note) == (WALL - 60, False, None)
    assert (decision.by, decision.how) == ("jake", "--out-of-cage-at")
    assert made.welfare.left_cage_wall_at == WALL - 60
    assert _kinds(made) == ["departure"]


def test_a_far_departure_with_no_answer_is_owed_and_nothing_is_marked(tmp_path):
    made = session(tmp_path)

    with pytest.raises(marks.Owed) as owed:
        marks.decide_departure(made, WALL - FAR, None, by="jake", how="typed on the page")

    assert (owed.value.mark, owed.value.at) == ("departure", WALL - FAR)
    assert owed.value.answers == ("confirm", "amend")
    assert "Confirm it, or amend it" in owed.value.warning
    assert made.welfare.left_cage_wall_at is None
    assert not made.directory.exists(), "nothing is written for an unanswered mark"


def test_a_far_departure_a_person_confirmed_is_marked_confirmed_with_its_row(tmp_path):
    made = session(tmp_path)

    decision = marks.decide_departure(
        made,
        WALL - FAR,
        marks.Confirm(by="jake", how="confirmed on the page"),
        by="jake",
        how="typed on the page",
    )
    marks.depart(made, decision)
    marks.record_departure(made, decision)

    assert decision.confirmed
    rows = _rows(made)
    assert [row["kind"] for row in rows] == ["departure", "departure confirmed"]
    assert rows[0]["how"] == rows[1]["how"] == "confirmed on the page"


def test_an_amendment_is_its_own_confirmation_and_marks_the_corrected_time(tmp_path):
    made = session(tmp_path)
    typed_at, corrected = WALL - 9 * 3600, WALL - 600

    decision = marks.decide_departure(
        made,
        typed_at,
        marks.Amend(at=corrected, reason="typed 08:45 for 18:45", by="sam", how="amended on the page"),
        by="jake",
        how="typed on the page",
    )
    marks.depart(made, decision)
    marks.record_departure(made, decision)

    assert decision.confirmed and made.welfare.left_cage_wall_at == corrected
    departed = _rows(made)[0]
    assert (departed["kind"], departed["by"], departed["how"]) == (
        "departure", "sam", "amended on the page"
    )
    note = _rows(made)[1]
    assert (note["kind"], note["was"], note["now"]) == ("departure amended", typed_at, corrected)
    assert (note["reason"], note["by"]) == ("typed 08:45 for 18:45", "sam")


@pytest.mark.parametrize(("reason", "by", "said"), [("", "sam", "no reason"), ("typo", "", "by nobody")])
def test_an_amendment_without_a_reason_or_a_name_is_refused(tmp_path, reason, by, said):
    made = session(tmp_path)

    with pytest.raises(Exceeded, match=said):
        marks.decide_departure(
            made,
            WALL - 9 * 3600,
            marks.Amend(at=WALL - 600, reason=reason, by=by, how="amended on the page"),
            by="jake",
            how="typed on the page",
        )

    assert made.welfare.left_cage_wall_at is None


def test_an_amendment_meets_every_refusal_the_original_would(tmp_path):
    """An amendment is not an override: into the future is refused at the mark, and
    nothing about the departure is written."""
    made = session(tmp_path)
    decision = marks.decide_departure(
        made,
        WALL - 9 * 3600,
        marks.Amend(at=WALL + 3600, reason="typo", by="sam", how="amended on the page"),
        by="jake",
        how="typed on the page",
    )

    with pytest.raises(Exceeded, match="in the future"):
        marks.depart(made, decision)

    assert not made.directory.exists()


def test_a_departure_past_the_ceiling_is_refused_and_never_asked_about(tmp_path):
    """The band has two edges and only one of them asks (`welfare`'s rule)."""
    made = session(tmp_path, out_of_cage=3600.0)

    decision = marks.decide_departure(made, WALL - 7200, None, by="jake", how="t")

    assert decision.note is None
    with pytest.raises(Exceeded, match="at or outside the limit"):
        marks.depart(made, decision)


def test_a_near_return_is_taken_and_written(tmp_path):
    made = _departed(tmp_path)

    marks.take_return(made, WALL - 60, confirmed=False, by="jake", how="the page")

    assert made.welfare.returned_wall_at == WALL - 60
    assert _kinds(made)[-1] == "returned"


def test_a_far_return_nobody_confirmed_is_owed_confirm_or_retype(tmp_path):
    """No amendment for a return (spec §6.2): the page offers *confirm* or *re-type*."""
    made = _departed(tmp_path)

    with pytest.raises(marks.Owed) as owed:
        marks.take_return(made, WALL - 2 * 3600, confirmed=False, by="jake", how="the page")

    assert (owed.value.mark, owed.value.answers) == ("return", ("confirm", "re-type"))
    assert made.welfare.returned_wall_at is None


def test_a_far_return_a_person_confirmed_is_taken_with_its_row(tmp_path):
    made = _departed(tmp_path)

    marks.take_return(made, WALL - 2 * 3600, confirmed=True, by="jake", how="the page")

    assert _kinds(made)[-2:] == ["returned", "return confirmed"]


@pytest.mark.parametrize(
    ("before_wall", "said"), [(-600, "in the future"), (4 * 3600, "having left it at")]
)
def test_a_return_meets_every_welfare_refusal(tmp_path, before_wall, said):
    made = _departed(tmp_path)

    with pytest.raises(Exceeded, match=said):
        marks.take_return(made, WALL - before_wall, confirmed=True, by="jake", how="the page")


def test_the_pages_departure_is_read_by_the_terminals_parser(tmp_path):
    decision = marks.page_departure(
        session(tmp_path),
        departure=typed(60),
        answer=None,
        amend_to=None,
        amend_reason="",
        by="jake (box, unverified)",
    )

    assert decision.at == pytest.approx(WALL - 60, abs=1.0)
    assert (decision.by, decision.how) == ("jake (box, unverified)", "typed on the page")


def test_the_pages_answers_are_the_terminals(tmp_path):
    confirmed = marks.page_departure(
        session(tmp_path / "a"), departure=typed(3 * 3600), answer="confirm",
        amend_to=None, amend_reason="", by="jake",
    )
    amended = marks.page_departure(
        session(tmp_path / "b"), departure=typed(9 * 3600), answer="amend",
        amend_to=typed(600), amend_reason="typo", by="jake",
    )

    assert (confirmed.confirmed, confirmed.how) == (True, "confirmed on the page")
    assert (amended.how, amended.by, amended.confirmed) == ("amended on the page", "jake", True)
    assert amended.at == pytest.approx(WALL - 600, abs=1.0)


#: A date `datetime` parses and no host's calendar can place: the parser's
#: `astimezone()` raises `ValueError` for it, which is not an `ArgumentTypeError`.
#: Seen on macOS and on CI's Linux at UTC.
UNPLACEABLE = ["0001-01-01T00:00"]

#: The calendar's last minute. Whether a host can place it depends on the host:
#: macOS cannot (the parser's `ValueError`), while CI's Linux at UTC -- the rig's
#: platform -- can, and there it is a time in the future. Either way it is refused
#: and nothing is marked; which refusal comes is the host's.
LAST_MINUTE = "9999-12-31T23:59"
REFUSED = (argparse.ArgumentTypeError, Exceeded)
REFUSED_AS = "is not a clock time|in the future"


@pytest.mark.parametrize("text", ["half past nine", "25:00", "", *UNPLACEABLE])
def test_a_page_time_that_is_not_one_is_refused_in_the_terminals_words(tmp_path, text):
    made = session(tmp_path)

    with pytest.raises(argparse.ArgumentTypeError, match="is not a clock time") as refused:
        marks.page_departure(
            made, departure=text, answer=None, amend_to=None, amend_reason="", by="jake",
        )

    assert repr(text) in str(refused.value) and marks.TIME_FORMATS in str(refused.value)
    assert made.welfare.left_cage_wall_at is None


@pytest.mark.parametrize("text", UNPLACEABLE)
def test_an_amended_time_the_host_cannot_place_is_refused_in_the_terminals_words(
    tmp_path, text
):
    made = session(tmp_path)

    with pytest.raises(argparse.ArgumentTypeError, match="is not a clock time"):
        marks.page_departure(
            made, departure=typed(9 * 3600), answer="amend", amend_to=text,
            amend_reason="typo", by="jake",
        )

    assert made.welfare.left_cage_wall_at is None


@pytest.mark.parametrize("text", UNPLACEABLE)
def test_a_return_time_the_host_cannot_place_is_refused_in_the_terminals_words(
    tmp_path, text
):
    made = _departed(tmp_path)

    with pytest.raises(argparse.ArgumentTypeError, match="is not a clock time"):
        marks.page_return(made, returned=text, confirm=True, by="jake")

    assert made.welfare.returned_wall_at is None


@pytest.mark.parametrize(
    ("departure", "answer", "amend_to", "amend_reason"),
    [(LAST_MINUTE, None, None, ""), (typed(9 * 3600), "amend", LAST_MINUTE, "typo")],
    ids=["typed", "amended"],
)
def test_a_departure_in_the_calendars_last_minute_is_refused_on_any_host(
    tmp_path, departure, answer, amend_to, amend_reason
):
    made = session(tmp_path)

    with pytest.raises(REFUSED, match=REFUSED_AS):
        decision = marks.page_departure(
            made, departure=departure, answer=answer, amend_to=amend_to,
            amend_reason=amend_reason, by="jake",
        )
        marks.depart(made, decision)

    assert made.welfare.left_cage_wall_at is None


def test_a_return_in_the_calendars_last_minute_is_refused_on_any_host(tmp_path):
    made = _departed(tmp_path)

    with pytest.raises(REFUSED, match=REFUSED_AS):
        marks.page_return(made, returned=LAST_MINUTE, confirm=True, by="jake")

    assert made.welfare.returned_wall_at is None


@pytest.mark.parametrize("answer", ["Amend", "amended", "CONFIRM", "yes", ""])
def test_an_answer_the_page_does_not_know_is_refused_not_read_as_none(tmp_path, answer):
    """The terminal's rule: anything that is not a known answer stops. Read as no
    answer, an in-band departure would be marked at the typed time and the person's
    amendment dropped without a word."""
    made = session(tmp_path)

    with pytest.raises(argparse.ArgumentTypeError, match="is none of them") as refused:
        marks.page_departure(
            made, departure=typed(60), answer=answer, amend_to=typed(600),
            amend_reason="typo", by="jake",
        )

    assert repr(answer) in str(refused.value)
    assert made.welfare.left_cage_wall_at is None
    assert not made.directory.exists()


@pytest.mark.parametrize("answer", [None, "confirm"])
@pytest.mark.parametrize(
    ("amend_to", "amend_reason", "named"),
    [("in", "", "corrected departure time"), (None, "typo", "reason")],
)
def test_an_amendment_sent_without_amend_is_refused_not_dropped(
    tmp_path, answer, amend_to, amend_reason, named
):
    """In the band, `None` or `confirm` marks the typed time; a corrected time or a
    reason sent beside it is an amendment the person meant, and dropping it would
    mark the time they were correcting."""
    made = session(tmp_path)
    corrected = typed(600) if amend_to == "in" else None

    with pytest.raises(argparse.ArgumentTypeError, match="without the answer amend") as refused:
        marks.page_departure(
            made, departure=typed(60), answer=answer, amend_to=corrected,
            amend_reason=amend_reason, by="jake",
        )

    assert named in str(refused.value)
    assert made.welfare.left_cage_wall_at is None
    assert not made.directory.exists()


@pytest.mark.parametrize("confirm", ["false", "", 1, 0, None])
def test_the_pages_return_confirmation_is_strictly_a_bool(tmp_path, confirm):
    """`take_return` and `welfare` read `confirmed` for its truth, so a `"false"` would
    confirm a far return nobody confirmed."""
    made = _departed(tmp_path)

    with pytest.raises(argparse.ArgumentTypeError, match="true or false"):
        marks.page_return(made, returned=typed(2 * 3600), confirm=confirm, by="jake")

    assert made.welfare.returned_wall_at is None


def test_an_amendment_from_the_page_needs_its_corrected_time(tmp_path):
    with pytest.raises(argparse.ArgumentTypeError, match="corrected departure time"):
        marks.page_departure(
            session(tmp_path), departure=typed(9 * 3600), answer="amend",
            amend_to=None, amend_reason="typo", by="jake",
        )


def test_the_pages_return_takes_now_on_the_sessions_clock(tmp_path):
    made = _departed(tmp_path)

    marks.page_return(made, returned="now", confirm=False, by="jake")

    assert made.welfare.returned_wall_at == WALL
    assert _rows(made)[-1]["how"] == "the page"
