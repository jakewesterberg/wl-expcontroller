"""Our encoder against wl-preproc's own decoder.

If these pass, we emit their protocol rather than our idea of it.
"""

from __future__ import annotations

import os

import pytest

#: CI sets this. A skip is the right behaviour on a laptop without the sibling
#: checkout and the **wrong** behaviour in CI, where these tests are the only
#: thing proving we emit wl-preproc's protocol rather than our idea of it -- and
#: where they were silently skipping into a green build, because `actions/checkout`
#: fetches this repository alone. A contract test that is allowed to not run is not
#: a contract test.
_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"

try:
    from wl_preproc.contracts import events as wl_preproc_events
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). "
            f"The event-codec round-trip is the only check that we emit their "
            f"protocol; skipping it would report a compatibility nobody verified"
        ) from exc
    wl_preproc_events = None
    pytest.skip(
        "wl-preproc checkout not beside this repo; the round-trip cannot run",
        allow_module_level=True,
    )

from wl_xcon import codes, encode  # noqa: E402
from wl_xcon.encode import words_for, words_for_code  # noqa: E402


def test_a_trial_number_round_trips_through_wl_preprocs_decoder():
    """The escape payload is where a second implementation would drift: escape
    word, payload words, then an XOR checksum over both. Their decoder rejects a
    stream whose checksum disagrees, so this fails loudly rather than subtly."""
    Escape = wl_preproc_events.Escape

    words = words_for(Escape.TRIAL_NUMBER, 4242)
    decoded = wl_preproc_events.decode_stream(
        [(i * 0.001, word) for i, word in enumerate(words)]
    )

    assert len(decoded) == 1
    event = decoded[0]
    assert event.escape is Escape.TRIAL_NUMBER
    assert (event.words[0] << 16) | event.words[1] == 4242


def test_a_simple_code_decodes_as_one_event():
    Marker = wl_preproc_events.Marker

    words = words_for_code(Marker.TRIAL_START)
    decoded = wl_preproc_events.decode_stream([(0.0, word) for word in words])

    assert [event.code for event in decoded] == [Marker.TRIAL_START]


def test_emitting_an_escape_value_as_a_simple_code_is_refused():
    """The defect that would corrupt a whole trial rather than one event.

    Their decoder treats an escape word as the start of a payload and consumes the
    next words as its body. So a bare escape emitted as though it were a plain code
    silently swallows the events that follow, and the checksum then fails against
    words that were never a payload -- losing the rest of the trial's codes, not
    just this one. Refused where it is written rather than detected where it is read.
    """
    with pytest.raises(ValueError, match="escape"):
        words_for_code(wl_preproc_events.Escape.TRIAL_NUMBER)


@pytest.mark.parametrize("escape", ["TRIAL_NUMBER", "CONDITION"])
@pytest.mark.parametrize("value", [0, 1, 4242, 65535, 65536, 4294967295])
def test_our_payload_framing_matches_theirs_exactly(escape, value):
    """Their `encode_payload` as an oracle, across the uint32 range, for both escapes
    `words_for` frames.

    Stronger than the round trip: it catches a drift that happens to survive
    decoding -- a checksum convention that is self-consistent but not theirs, or a
    word order that reads back the same because both halves were swapped.

    **`CONDITION` too, although nothing emits it yet** (XC-197, which waits on the
    conditions the day's plan brings, XC-150): `words_for` has framed it since it was
    written, and no test read that framing against theirs until XC-155.
    """
    their = wl_preproc_events.Escape[escape]
    payload = [(value >> 16) & 0xFFFF, value & 0xFFFF]

    assert words_for(their, value) == wl_preproc_events.encode_payload(their, payload)


def test_the_escapes_the_rig_names_are_theirs():
    """`encode.TRIAL_NUMBER` is the escape `taskd` strobes each trial's number behind
    (XC-155), so a wrong value there is a stream wl-preproc reads as another escape, or
    as none at all."""
    Escape = wl_preproc_events.Escape

    assert (encode.TRIAL_NUMBER, encode.CONDITION) == (Escape.TRIAL_NUMBER, Escape.CONDITION)


def test_every_marker_codes_mirrors_is_theirs():
    """`codes.py` mirrors `Marker` values and says the round-trip tests keep the mirror
    honest. `TRIAL_START` and `TRIAL_END` frame every trial since XC-155; the five
    outcome markers were mirrored before any test read them against theirs."""
    mirrored = {
        "TRIAL_START": codes.TRIAL_START,
        "TRIAL_END": codes.TRIAL_END,
        "TRIAL_CORRECT": codes._TRIAL_CORRECT,
        "TRIAL_ERROR": codes._TRIAL_ERROR,
        "TRIAL_ABORT": codes._TRIAL_ABORT,
        "TRIAL_FIXATION_BREAK": codes._TRIAL_FIXATION_BREAK,
        "TRIAL_NO_RESPONSE": codes._TRIAL_NO_RESPONSE,
    }

    assert mirrored == {name: int(wl_preproc_events.Marker[name]) for name in mirrored}


def test_the_block_markers_are_wl_preprocs():
    assert codes.BLOCK_END == wl_preproc_events.Marker.BLOCK_END
    assert encode.BLOCK_START == wl_preproc_events.Escape.BLOCK_START
    assert wl_preproc_events.PAYLOAD_WORD_COUNTS[wl_preproc_events.Escape.BLOCK_START] == 2


@pytest.mark.parametrize(("block", "task"), [(1, 0), (27, 0), (65_535, 255)])
def test_a_block_start_is_framed_exactly_as_wl_preproc_frames_it(block, task):
    theirs = wl_preproc_events.encode_payload(wl_preproc_events.Escape.BLOCK_START, [block, task])
    assert encode.words_for_block(block, task) == list(theirs)


def test_a_block_start_round_trips_through_wl_preprocs_decoder():
    words = encode.words_for_block(7, encode.UNALLOCATED_TASK_CODE)
    events = wl_preproc_events.decode_stream([(i * 0.001, w) for i, w in enumerate(words)])
    assert [(e.escape, e.words) for e in events] == [(wl_preproc_events.Escape.BLOCK_START, (7, 0))]


@pytest.mark.parametrize(("block", "task", "said"), [
    (0, 0, "counts from 1"),
    (65_536, 0, "block number out of 16-bit range"),
    (1, -1, "task code out of 16-bit range"),
    (1, 65_536, "task code out of 16-bit range"),
])
def test_a_block_start_that_cannot_be_framed_is_refused(block, task, said):
    with pytest.raises(ValueError, match=said):
        encode.words_for_block(block, task)


def test_the_run_markers_are_wl_preprocs():
    """XC-205: `encode.RUN_ESCAPE` is wl-preproc's `Escape.RUN_START`, two payload words
    as `BLOCK_START`'s are, and `codes.RUN_END_MARKER` is its `Marker.RUN_END`. Named apart
    from the allocation's `RUN_START` and `RUN_END` codes (4135 and 4136), which `taskd`
    still strobes beside them."""
    Escape, Marker = wl_preproc_events.Escape, wl_preproc_events.Marker

    assert encode.RUN_ESCAPE == Escape.RUN_START
    assert codes.RUN_END_MARKER == Marker.RUN_END
    assert wl_preproc_events.PAYLOAD_WORD_COUNTS[Escape.RUN_START] == 2


@pytest.mark.parametrize(("run", "task"), [(1, 0), (2, 0), (27, 0), (65_535, 255)])
def test_a_run_start_is_framed_exactly_as_wl_preproc_frames_it(run, task):
    """Their `encode_payload` as the oracle, as for `BLOCK_START`: the escape, the run's
    number, the task code, and their checksum."""
    theirs = wl_preproc_events.encode_payload(wl_preproc_events.Escape.RUN_START, [run, task])
    assert encode.words_for_run(run, task) == list(theirs)


def test_a_run_round_trips_through_wl_preprocs_decoder():
    """A run's opening and its closing marker, decoded by theirs: one `RUN_START` payload
    carrying the run's number and task code, then one `RUN_END`."""
    words = [
        *encode.words_for_run(2, encode.UNALLOCATED_TASK_CODE),
        *words_for_code(codes.RUN_END_MARKER),
    ]
    start, end = wl_preproc_events.decode_stream([(i * 0.001, w) for i, w in enumerate(words)])

    assert (start.escape, start.words) == (wl_preproc_events.Escape.RUN_START, (2, 0))
    assert end.code == wl_preproc_events.Marker.RUN_END


@pytest.mark.parametrize(("run", "task", "said"), [
    (0, 0, "a run number counts from 1"),
    (-1, 0, "run number out of 16-bit range"),
    (65_536, 0, "run number out of 16-bit range"),
    (1, -1, "task code out of 16-bit range"),
    (1, 65_536, "task code out of 16-bit range"),
])
def test_a_run_start_that_cannot_be_framed_is_refused(run, task, said):
    with pytest.raises(ValueError, match=said):
        encode.words_for_run(run, task)
