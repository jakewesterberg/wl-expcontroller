"""Our encoder against wl-preproc's own decoder.

If these pass, we emit their protocol rather than our idea of it.
"""

from __future__ import annotations

import os

import pytest

#: CI sets this. A skip is the right behaviour on a laptop without the sibling
#: checkout and the **wrong** behaviour in CI, where these nine tests are the only
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

from wl_expcontroller.encode import words_for, words_for_code  # noqa: E402


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


@pytest.mark.parametrize("value", [0, 1, 4242, 65535, 65536, 4294967295])
def test_our_payload_framing_matches_theirs_exactly(value):
    """Their `encode_payload` as an oracle, across the uint32 range.

    Stronger than the round trip: it catches a drift that happens to survive
    decoding -- a checksum convention that is self-consistent but not theirs, or a
    word order that reads back the same because both halves were swapped.
    """
    Escape = wl_preproc_events.Escape
    payload = [(value >> 16) & 0xFFFF, value & 0xFFFF]

    assert words_for(Escape.TRIAL_NUMBER, value) == wl_preproc_events.encode_payload(
        Escape.TRIAL_NUMBER, payload
    )
