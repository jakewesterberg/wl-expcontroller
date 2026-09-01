"""Digital I/O behind its interfaces, against a simulated card.

The pin map is **fixed in copper** by wl-sync's breakout board, so it is not a
preference: 16 event-code bits on P0.8-P0.23, not zero-based. Getting the shift wrong
would relabel every event in every recording -- consistently, plausibly, and
invisibly, since a recording full of codes that are all 256 too small still decodes.

This is the second of the four day-one items that can be built without hardware. What
January adds is a card, not an integration.
"""

import pytest

from wl_expcontroller.dio import EVENT_BITS, FIRST_EVENT_LINE, Absent, Simulated


def test_an_event_code_lands_on_the_lines_the_breakout_wired():
    """P0.8 upward, so a code is shifted by eight before it reaches the port."""
    card = Simulated()
    card.emit(1)

    assert card.port_writes[0] == 1 << FIRST_EVENT_LINE


def test_the_word_settles_before_the_strobe_and_clears_after():
    """Order is the contract. A strobe rising before the word is stable latches
    whatever the lines happened to hold, which is a valid-looking wrong code."""
    card = Simulated()
    card.emit(4096)

    assert card.log == [
        ("word", 4096 << FIRST_EVENT_LINE),
        ("strobe", True),
        ("strobe", False),
    ]


def test_a_code_too_wide_for_sixteen_bits_is_refused():
    """32768 does not fit sixteen lines, and truncation would emit 0 -- a code that
    decodes as a different event rather than as an error."""
    card = Simulated()

    with pytest.raises(ValueError, match="16 bits"):
        card.emit(1 << EVENT_BITS)
    with pytest.raises(ValueError, match="negative"):
        card.emit(-1)


def test_reward_and_stimulation_are_their_own_lines_not_event_codes():
    """A strobed code says a thing happened; these lines make it happen.

    Conflating them would let an event code deliver fluid, which is the sort of
    coupling that turns a logging bug into a welfare incident.
    """
    card = Simulated()
    card.reward(True)
    card.stim_trigger()

    assert ("reward", True) in card.log
    assert ("stim", True) in card.log


def test_the_inputs_the_breakout_returns_are_all_readable():
    card = Simulated(inputs={"task_patch": True, "flip_patch": False,
                             "chair_motion": False, "rhs_stim": True})

    assert card.read("task_patch") is True
    assert card.read("rhs_stim") is True
    with pytest.raises(KeyError):
        card.read("not_a_line")


def test_an_absent_card_refuses_rather_than_pretending():
    """The dangerous alternative is a no-op card.

    A session that runs a full protocol, rewards the animal, and writes a record
    containing no event codes at all is worse than one that will not start -- the
    animal has worked and the data is unusable, and nothing said so.
    """
    card = Absent()

    with pytest.raises(RuntimeError, match="no DIO card"):
        card.emit(4096)
    with pytest.raises(RuntimeError, match="no DIO card"):
        card.reward(True)


def test_a_simulated_card_reports_what_a_recording_would_contain():
    """So a simulated session's event stream can be asserted against the task."""
    card = Simulated()
    for code in (4096, 4097, 4110):
        card.emit(code)

    assert card.codes == [4096, 4097, 4110]


def test_a_card_counts_what_it_sent():
    """The console shows it, and a session that strobed nothing is a session whose
    recording cannot be aligned -- worth seeing before the animal has worked an hour."""
    card = Simulated()
    card.emit(4096)
    card.emit(4097)

    assert card.sent == 2
