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
then connect to its web server, as the connections seen suggest. (CI's own logs carry only
"1 warning", not its text, so for CI this is the reproduction's reading, not CI's.) macOS
never showed it because it hands out port-0 ports in sequence (52094, 52095, ... on the
lab's development Mac, 2026-10-01), so it does not hand back the port just released.

**Below the ephemeral range.** The operating system picks a port for a bind to port 0, and
for the source of every outgoing connection, from its ephemeral range, and from nowhere
else. Read 2026-10-01: Linux `32768 60999` (`/proc/sys/net/ipv4/ip_local_port_range`, in
the container above), macOS `49152 65535` (`sysctl net.inet.ip.portrange.first` and
`.last`, on the lab's development Mac). `BAND` sits below both, so a port chosen here is
taken in the gap only by a bind that names it. Where the range can be read (Linux), a range
reaching into `BAND` is refused rather than trusted, so the protection cannot lapse quietly.

**One host, several suites.** The binds that name a port are this suite's own, and a local
sweep runs it as parallel lanes on one host (CHECKPOINT's CI row). Two lanes could choose
the same port within the moments between choosing and binding, and a test failed that way
reads as `caught` under the mutation harness. So each chosen port is also claimed with an
`flock` on a lock file of its own, held until the process exits: another process on this
host passes it over, and so does this one, which never chooses a port twice.

Never collected, since its name does not start with `test_`.
"""

import fcntl
import random
import socket
import tempfile
from pathlib import Path

#: Ports below both kernels' ephemeral ranges. Registered services may sit here too;
#: the check that each chosen port is free covers those.
BAND = range(20000, 32768)

#: Its own generator: a test that seeds `random` must not make two tests choose alike.
_PICK = random.Random()

#: How many ports to try before giving up, so a band that is somehow full fails the test.
_ATTEMPTS = 1000

#: Where Linux keeps its ephemeral range; there is no such file on macOS.
_LINUX_RANGE = Path("/proc/sys/net/ipv4/ip_local_port_range")

#: Where each chosen port's lock file lives, shared by every process of this user.
LOCKS = Path(tempfile.gettempdir()) / "wl-xcon-test-ports"

#: The lock files this process holds, open until it exits.
_HELD: list = []


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


def _claim(port: int, locks: Path) -> bool:
    """Whether this process now holds `port`'s lock file, which no other open of it can
    take until this process exits; `False` if anything, this process included, holds it."""
    locks.mkdir(exist_ok=True)
    handle = (locks / f"{port}.lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _HELD.append(handle)
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
        # No `port not in chosen`: this process holds each port it chose, and `_claim`
        # refuses a port held by anything, this process included.
        if _free(port) and _claim(port, LOCKS):
            chosen.append(port)
    if len(chosen) < count:
        raise RuntimeError(f"found {len(chosen)} free ports of {count} in {_ATTEMPTS} tries")
    return tuple(f"tcp://127.0.0.1:{port}" for port in chosen)
