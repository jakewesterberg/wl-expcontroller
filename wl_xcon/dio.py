"""Digital I/O, behind the interface the rest of the system sees.

**The pin map is fixed in copper** by `wl-sync`'s breakout board (that repo's
breakout spec 3 and 9.2), so nothing here is a preference: 16 event-code bits on
**P0.8-P0.23, not zero-based**, plus an event strobe, a reward-commanded line and a
stimulation trigger; four digital inputs coming back.

The eight-line offset is the reason this module is worth its own file and its own
tests. A code written to P0.0 upward instead would be shifted by 256 in every
recording -- consistently, plausibly, and invisibly, because a stream of codes that
are all wrong by the same amount still decodes into perfectly sensible-looking
events. It would be found at analysis time, on data already collected.

Three implementations that the trial loop cannot tell apart (S6 6, the same rule
that makes a simulated session evidence about a real one): the real card, a
simulated one that records what a recording would contain, and `Absent`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

#: P0.8: the first event-code line. Not zero-based, and not ours to change.
FIRST_EVENT_LINE = 8
#: P0.8 through P0.23.
EVENT_BITS = 16
#: The four lines the breakout returns to us. Two photodiode comparators turn an
#: offline check into an online guarantee: state progression can be gated on physical
#: stimulus onset, and dropped frames are seen at the display surface.
INPUTS = ("task_patch", "flip_patch", "chair_motion", "rhs_stim")


def word_for(code: int) -> int:
    """An event code as the port word that carries it.

    Refuses rather than truncates. A code of 32768 masked into sixteen bits is 0,
    which decodes as a *different event* rather than as an error -- and an error is
    the only one of those two a person can act on.
    """
    if code < 0:
        raise ValueError(f"event code {code} is negative; codes are unsigned")
    if code >= 1 << EVENT_BITS:
        raise ValueError(
            f"event code {code} does not fit in {EVENT_BITS} bits; truncating it "
            f"would emit a different valid code rather than an error"
        )
    return code << FIRST_EVENT_LINE


class Card(Protocol):
    """What `taskd` needs from digital I/O, and nothing more."""

    def emit(self, code: int) -> None:
        """Put an event code on the lines and strobe it."""

    def reward(self, on: bool) -> None:
        """Drive the reward-commanded line."""

    def stim_trigger(self) -> None:
        """Pulse the stimulation trigger."""

    def read(self, line: str) -> bool:
        """One of `INPUTS`."""


@dataclass
class Simulated:
    """A card that records what a recording would contain.

    `log` keeps the *order* of operations, because order is the contract: a strobe
    rising before the word is stable latches whatever the lines happened to hold,
    which produces a valid-looking wrong code. A test that only checked the final
    word could not see that.
    """

    inputs: dict = field(default_factory=dict)
    log: list = field(default_factory=list)
    port_writes: list = field(default_factory=list)
    codes: list = field(default_factory=list)
    sent: int = 0

    def emit(self, code: int) -> None:
        word = word_for(code)
        self.port_writes.append(word)
        self.codes.append(code)
        self.sent += 1
        self.log.append(("word", word))
        self.log.append(("strobe", True))
        self.log.append(("strobe", False))

    def reward(self, on: bool) -> None:
        # Its own line, never an event code. A strobed code *says* a thing happened;
        # this line makes it happen, and conflating them would let a logging bug
        # deliver fluid.
        self.log.append(("reward", on))

    def stim_trigger(self) -> None:
        self.log.append(("stim", True))

    def read(self, line: str) -> bool:
        if line not in INPUTS:
            raise KeyError(f"{line!r} is not one of {INPUTS}")
        return bool(self.inputs.get(line, False))


@dataclass
class Absent:
    """No card. **Refuses, rather than quietly doing nothing.**

    A no-op card is the dangerous version: a session runs a full protocol, rewards
    the animal, and writes a record containing no event codes at all -- which cannot
    be aligned to any recording. The animal has worked, the data is unusable, and
    nothing said so. Failing at the first strobe costs a minute.
    """

    def _refuse(self) -> None:
        raise RuntimeError(
            "no DIO card is configured; a session cannot emit event codes, deliver "
            "reward or trigger stimulation. Use Simulated for a dry run"
        )

    def emit(self, code: int) -> None:
        self._refuse()

    def reward(self, on: bool) -> None:
        self._refuse()

    def stim_trigger(self) -> None:
        self._refuse()

    def read(self, line: str) -> bool:
        self._refuse()
        return False
