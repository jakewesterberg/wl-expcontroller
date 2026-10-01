"""Loopback endpoints for a test to bind later, or to find nothing listening on, chosen
where the operating system never chooses a port of its own.

**Why not bind port 0, read the port, and release it.** Every test that did so left a gap
between the release and the moment `wlx run`, `wlx taskd` or the test bound the port
again, and on Linux the operating system handed the port to something else in that gap.
CI failed twice on it, on 2026-09-30 and 2026-10-01 (runs `36789375559` and
`36797081773`), each time as an end-to-end test finding `wlx run` ended before its first
trial. Reproduced in a Linux container limited to two CPUs, 2026-10-01: `wlx run`'s
thread died on `zmq.error.ZMQError: Address already in use`, in 3 of 80 runs, and in the
two runs that looked, the port was held by a **listening** socket with connections into
it. The one socket bound in that gap is `wlx serve`'s own web server, which binds port 0
itself and so could be handed the port just released; the console's ZeroMQ sockets would
then connect to its web server, as the connections seen suggest. macOS never showed it
(XC-061: it lets overlapping binds succeed that Linux refuses).

**Below the ephemeral range.** The operating system picks a port for a bind to port 0, and
for the source of every outgoing connection, from its ephemeral range, and from nowhere
else. Read 2026-10-01: Linux `32768 60999` (`/proc/sys/net/ipv4/ip_local_port_range`, in
the container above), macOS `49152 65535` (`sysctl net.inet.ip.portrange.first` and
`.last`, on the lab's development Mac). `BAND` sits below both, so a port chosen here is
taken in the gap only by a bind that names it, and nothing in this suite names one but
the test it was chosen for. Where the range can be read (Linux), a range reaching into
`BAND` is refused rather than trusted, so the protection cannot lapse quietly.

Never collected, since its name does not start with `test_`.
"""

import random
import socket
from pathlib import Path

#: Ports below both kernels' ephemeral ranges, and above the ports services are given.
BAND = range(20000, 32768)

#: Its own generator: a test that seeds `random` must not make two tests choose alike.
_PICK = random.Random()

#: How many ports to try before giving up, so a band that is somehow full fails the test.
_ATTEMPTS = 1000

#: Where Linux keeps its ephemeral range; there is no such file on macOS.
_LINUX_RANGE = Path("/proc/sys/net/ipv4/ip_local_port_range")


def ephemeral_floor(path: Path = _LINUX_RANGE) -> int | None:
    """The lowest port this kernel chooses on its own, where it says (Linux), else `None`."""
    try:
        return int(path.read_text().split()[0])
    except OSError:
        return None


def _free(port: int) -> bool:
    """Whether nothing holds `port` on loopback now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def endpoints(count: int, *, floor: int | None = None) -> tuple[str, ...]:
    """`count` distinct `tcp://127.0.0.1:PORT` endpoints, each free when chosen, from `BAND`.

    `floor` is the kernel's lowest ephemeral port, read from the kernel when not given;
    it is a parameter only so a test can show a range reaching into the band is refused."""
    floor = ephemeral_floor() if floor is None else floor
    if floor is not None and floor < BAND.stop:
        raise RuntimeError(
            f"this kernel chooses ports from {floor} up, inside tests/_ports.py's band "
            f"{BAND.start}-{BAND.stop - 1}, so a port chosen there can be taken before "
            "the test binds it; move BAND below it"
        )
    chosen: list[int] = []
    for _ in range(_ATTEMPTS):
        if len(chosen) == count:
            break
        port = _PICK.randrange(BAND.start, BAND.stop)
        if port not in chosen and _free(port):
            chosen.append(port)
    if len(chosen) < count:
        raise RuntimeError(f"found {len(chosen)} free ports of {count} in {_ATTEMPTS} tries")
    return tuple(f"tcp://127.0.0.1:{port}" for port in chosen)
