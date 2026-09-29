"""Turning events into the 16-bit strobed word stream.

The protocol is `wl-preproc`'s and is frozen (ADR-0007): escape word, payload
words, then an XOR checksum over the escape and its payload. This module produces
that stream; **it never reads one.** Decoding is theirs, and a second decoder here
would be a second definition of the framing, free to drift from the one the
recordings are actually written against.

Tests assert the agreement by round-tripping through their own `decode_stream`
(S2 §6.2), which is why this file may be written independently without becoming a
second source of truth.
"""

from __future__ import annotations

WORD_MASK = 0xFFFF


#: Payload word counts, mirroring `wl-preproc`'s `PAYLOAD_WORD_COUNTS`. Mirrored
#: rather than imported so the rig carries no pipeline dependency; the round-trip
#: tests are what keep the mirror honest, and a drift fails there rather than in a
#: recording.
_UINT32_ESCAPES = (0x8001, 0x8003)  # TRIAL_NUMBER, CONDITION

#: Their range allocation: 32768+ introduces a multi-word payload. Any word at or
#: above this is structural, never a plain code.
_ESCAPE_FLOOR = 0x8000


def words_for_code(code: int) -> list[int]:
    """One word for a simple event code.

    **Refuses an escape value.** Their decoder treats a word at or above
    `_ESCAPE_FLOOR` as the start of a payload and consumes the following words as
    its body, so a bare escape emitted as a plain code swallows the events after
    it and then fails a checksum against words that were never a payload. The
    damage is the rest of the trial's codes, not this one -- which is why it is
    refused where it is written rather than detected where it is read.
    """
    value = int(code)
    if not 0 < value <= WORD_MASK:
        raise ValueError(f"event code out of 16-bit range: {value}")
    if value >= _ESCAPE_FLOOR:
        raise ValueError(
            f"code {value:#06x} is an escape value; emitting it as a plain code "
            f"would make the decoder consume the following events as its payload"
        )
    return [value]


def _checksum(escape: int, words: list[int]) -> int:
    accumulator = escape
    for word in words:
        accumulator ^= word
    return accumulator & WORD_MASK


def words_for(escape: int, value: int) -> list[int]:
    """The full word sequence for a uint32-payload escape.

    High word first, matching their `TRIAL_NUMBER: 2  # uint32, high word first`.
    """
    if escape not in _UINT32_ESCAPES:
        raise ValueError(f"not a uint32-payload escape: {escape:#06x}")
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"value out of uint32 range: {value}")
    payload = [(value >> 16) & WORD_MASK, value & WORD_MASK]
    return [escape, *payload, _checksum(escape, payload)]
