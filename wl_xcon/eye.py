"""Gaze ingest: OpenIrisDPI's UDP protocol, parsed and made stale-aware.

**Protocol verified 2026-09-01** against the client that ships in the OpenIrisDPI
repository (`PythonUDP/openiris_udp_client.py`): send the literal string
`WAITFORDATA` to UDP port 9003 and receive a JSON object with `Left` and `Right`,
each carrying `FrameNumber`, `Pupil.Center.{X,Y}`, `Pupil.Size.{Width,Height}` and a
`CRs` list whose index 0 is the first Purkinje image and index 3 the fourth.

Three things this module exists to get right, none of which is parsing:

**The gaze signal is P1 minus P4.** Both Purkinje images move with the eye and with
the camera relative to the head, so either alone confounds rotation with translation.
Their difference cancels translation to first order, which is the whole of what buys
DPI its arcminute precision. Using the pupil centre would throw that away while still
producing entirely plausible numbers.

**Timestamps are local.** The protocol is poll-based and carries no clock we can
trust, so a sample is stamped when it arrives here. Offline reconstruction against
the camera's shared sync line stays the timing ground truth (S3); this is for the
trial loop, which needs to know how old its information is, not what time it is.

**Staleness has a ceiling and a floor.** P6: ~2% of OpenIrisDPI frames take >= 10 ms,
worst measured ~50 ms. A tracker reporting loss on the first late frame reports loss
constantly; one that never reports it hands the loop a position the eye left long ago.

**UNVERIFIED:** what OpenIris emits when tracking fails on one eye -- zeros, a null,
or an absent key -- is not documented in the material read, and guessing would put a
fabricated validity rule in the one place that decides whether an animal is looking.
`parse` therefore treats a structurally incomplete eye as no sample at all, and the
real failure representation is a bench measurement (V3) before this runs on an animal.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field

#: Verified from the shipped client: base port 9000 plus 3.
PORT = 9003
REQUEST = b"WAITFORDATA"

#: Indices into `CRs`. Named, because `CRs[3]` at a call site is a magic number in
#: the one calculation that must not be wrong.
_P1 = 0
_P4 = 3


@dataclass(frozen=True, slots=True)
class EyeReading:
    """One eye, in camera pixels. Nothing here is in degrees yet."""

    frame: int
    pupil: tuple[float, float]
    pupil_area: float
    p1: tuple[float, float]
    p4: tuple[float, float]

    def dpi(self) -> tuple[float, float]:
        """The dual-Purkinje difference: the translation-cancelled gaze signal."""
        return (self.p1[0] - self.p4[0], self.p1[1] - self.p4[1])


@dataclass(frozen=True, slots=True)
class Sample:
    """A binocular reading, stamped when it arrived here."""

    at: float
    left: EyeReading
    right: EyeReading


def _eye(struct: object) -> EyeReading | None:
    """One eye, or `None` if the structure is not what the protocol promises.

    Strict rather than forgiving: a partially parsed eye would flow into a gaze
    window as a confident position derived from missing data.
    """
    if not isinstance(struct, dict):
        return None
    try:
        pupil = struct["Pupil"]
        centre = pupil["Center"]
        size = pupil["Size"]
        crs = struct["CRs"]
        if len(crs) <= _P4:
            return None
        return EyeReading(
            frame=int(struct["FrameNumber"]),
            pupil=(float(centre["X"]), float(centre["Y"])),
            pupil_area=float(size["Width"]) * float(size["Height"]),
            p1=(float(crs[_P1]["X"]), float(crs[_P1]["Y"])),
            p4=(float(crs[_P4]["X"]), float(crs[_P4]["Y"])),
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def parse(payload: str | bytes, at: float) -> Sample | None:
    """A datagram into a sample, or `None` if it was not one.

    **Never raises.** UDP truncates and loses packets by design, and a parse error
    reaching the frame loop would end a session for something the protocol does
    routinely. A bad datagram is a dropped frame, which the staleness policy already
    knows how to survive.
    """
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        struct = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(struct, dict):
        return None
    left, right = _eye(struct.get("Left")), _eye(struct.get("Right"))
    if left is None or right is None:
        return None
    return Sample(at=at, left=left, right=right)


@dataclass
class Tracker:
    """The latest gaze, and how old it is.

    Hold-last with a ceiling. The loop asks `state` rather than reading `latest`
    directly, so "is this information still worth acting on" is decided in one place
    -- the same reasoning that keeps `Entered`, `Exited` and `Hold` in the trial loop
    rather than in each world.
    """

    #: How long a sample stays actionable. Default 50 ms: P6's **measured** worst
    #: OpenIrisDPI frame time, so an ordinary stall is survived and a real dropout
    #: is not.
    staleness: float = 0.05
    latest: Sample | None = None
    received: int = 0
    dropped: int = 0

    def accept(self, sample: Sample | None) -> None:
        if sample is None:
            self.dropped += 1
            return
        self.received += 1
        self.latest = sample

    def state(self, at: float) -> str:
        """`"ok"` or `"lost"`, which is what `World.signal` reports.

        Lost before the first sample, never centred: a tracker reporting (0, 0) at
        startup puts gaze exactly on a fixation point nobody is looking at, and the
        trial would score a hold against an empty chair.
        """
        if self.latest is None:
            return "lost"
        return "ok" if (at - self.latest.at) < self.staleness else "lost"


@dataclass
class Replay:
    """Recorded payloads, played back as a peer of the real socket.

    S11 §2 asks for replayed recordings rather than synthetic traces, and the reason
    is this module: a synthetic trace exercises the parser against exactly the
    assumptions that wrote it, so it can only confirm them.
    """

    payloads: list[tuple[float, str]]
    _index: int = field(default=0, repr=False)

    def poll(self, at: float) -> Sample | None:
        if self._index >= len(self.payloads):
            return None
        _offset, payload = self.payloads[self._index]
        self._index += 1
        return parse(payload, at)


@dataclass
class UdpSource:
    """The real tracker. Poll-based, so this asks and waits rather than listening.

    A timeout rather than a blocking read: the frame loop must return whether or not
    the tracker answered, because a display that stops flipping because the eye
    tracker went quiet is a worse failure than a stale gaze sample.
    """

    host: str = "127.0.0.1"
    port: int = PORT
    timeout: float = 0.002
    _socket: socket.socket | None = field(default=None, repr=False)

    def open(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.settimeout(self.timeout)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def poll(self, at: float) -> Sample | None:
        if self._socket is None:
            raise RuntimeError("UdpSource.poll before open()")
        try:
            self._socket.sendto(REQUEST, (self.host, self.port))
            payload, _ = self._socket.recvfrom(65535)
        except (OSError, socket.timeout):
            return None
        return parse(payload, at)
