"""`tests/_ports.py`: endpoints chosen where the operating system never chooses a port."""

import fcntl
import socket

import pytest

import _ports
from _ports import BAND, endpoints, ephemeral_floor


@pytest.fixture(autouse=True)
def _own_locks(tmp_path, monkeypatch):
    """Each test claims ports in a lock directory of its own, so the ports this process
    claimed for other tests, which it holds until it exits, do not decide these."""
    monkeypatch.setattr(_ports, "LOCKS", tmp_path / "locks")


class _Scripted:
    """A generator whose `randrange` returns `ports` in order."""

    def __init__(self, *ports: int) -> None:
        self.ports = list(ports)

    def randrange(self, start: int, stop: int) -> int:
        return self.ports.pop(0)


def _port(endpoint: str) -> int:
    assert endpoint.startswith("tcp://127.0.0.1:")
    return int(endpoint.rsplit(":", 1)[1])


def _unclaimed_free_ports(count: int) -> list[int]:
    """Ports in the band that nothing holds now, found without claiming them."""
    found: list[int] = []
    for port in range(BAND.start, BAND.stop):
        if _ports._free(port):
            found.append(port)
        if len(found) == count:
            return found
    raise AssertionError("no free ports in the band")


def test_endpoints_are_distinct_loopback_ports_in_the_band():
    chosen = endpoints(3)
    ports = [_port(endpoint) for endpoint in chosen]
    assert len(set(ports)) == 3
    assert all(port in BAND for port in ports)


def test_the_band_lies_below_this_kernels_own_choices_where_it_says():
    floor = ephemeral_floor()
    assert floor is None or floor >= BAND.stop


def test_a_port_held_now_is_passed_over(monkeypatch):
    (free,) = _unclaimed_free_ports(1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        taken = held.getsockname()[1]
        monkeypatch.setattr(_ports, "_PICK", _Scripted(taken, free))
        assert endpoints(1) == (f"tcp://127.0.0.1:{free}",)


def test_a_port_already_chosen_is_not_chosen_twice(monkeypatch):
    """Its claim, held by this process, is what passes it over the second time."""
    first, second = _unclaimed_free_ports(2)
    monkeypatch.setattr(_ports, "_PICK", _Scripted(first, first, second))
    assert endpoints(2) == (f"tcp://127.0.0.1:{first}", f"tcp://127.0.0.1:{second}")


def test_a_port_another_process_claimed_is_passed_over(monkeypatch):
    """Another open of a lock file stands for another process: `flock` refuses it the
    same way within one process."""
    claimed, free = _unclaimed_free_ports(2)
    _ports.LOCKS.mkdir()
    with (_ports.LOCKS / f"{claimed}.lock").open("a") as elsewhere:
        fcntl.flock(elsewhere, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(_ports, "_PICK", _Scripted(claimed, free))
        assert endpoints(1) == (f"tcp://127.0.0.1:{free}",)


def test_a_chosen_port_stays_claimed_after_it_is_returned():
    port = _port(endpoints(1)[0])
    with (_ports.LOCKS / f"{port}.lock").open("a") as again:
        with pytest.raises(BlockingIOError):
            fcntl.flock(again, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_a_kernel_choosing_ports_inside_the_band_is_refused():
    with pytest.raises(RuntimeError, match="from 30000 up, inside tests/_ports.py's band"):
        endpoints(1, floor=30000)


def test_a_kernel_choosing_from_the_bands_last_port_is_refused():
    with pytest.raises(RuntimeError, match=f"from {BAND.stop - 1} up"):
        endpoints(1, floor=BAND.stop - 1)


def test_the_kernels_floor_is_read_when_none_is_given(monkeypatch):
    monkeypatch.setattr(_ports, "ephemeral_floor", lambda: 30000)
    with pytest.raises(RuntimeError, match="from 30000 up"):
        endpoints(1)


def test_a_kernel_choosing_ports_above_the_band_is_accepted():
    assert len(endpoints(1, floor=BAND.stop)) == 1


def test_the_floor_is_the_first_number_of_linuxs_range_file(tmp_path):
    path = tmp_path / "ip_local_port_range"
    path.write_text("32768\t60999\n")
    assert ephemeral_floor(path) == 32768
    assert ephemeral_floor(tmp_path / "absent") is None


def test_a_band_with_no_free_port_fails_rather_than_looping(monkeypatch):
    monkeypatch.setattr(_ports, "_free", lambda port: False)
    with pytest.raises(RuntimeError, match="found 0 free ports of 2 in 1000 tries"):
        endpoints(2)
