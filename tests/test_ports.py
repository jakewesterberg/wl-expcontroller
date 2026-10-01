"""`tests/_ports.py`: endpoints chosen where the operating system never chooses a port."""

import socket

import pytest

import _ports
from _ports import BAND, endpoints, ephemeral_floor


class _Scripted:
    """A generator whose `randrange` returns `ports` in order."""

    def __init__(self, *ports: int) -> None:
        self.ports = list(ports)

    def randrange(self, start: int, stop: int) -> int:
        return self.ports.pop(0)


def _port(endpoint: str) -> int:
    assert endpoint.startswith("tcp://127.0.0.1:")
    return int(endpoint.rsplit(":", 1)[1])


def test_endpoints_are_distinct_loopback_ports_in_the_band():
    chosen = endpoints(3)
    ports = [_port(endpoint) for endpoint in chosen]
    assert len(set(ports)) == 3
    assert all(port in BAND for port in ports)


def test_the_band_lies_below_this_kernels_own_choices_where_it_says():
    floor = ephemeral_floor()
    assert floor is None or floor >= BAND.stop


def test_a_port_held_now_is_passed_over(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        taken = held.getsockname()[1]
        free = endpoints(1)[0]
        monkeypatch.setattr(_ports, "_PICK", _Scripted(taken, _port(free)))
        assert endpoints(1) == (free,)


def test_a_port_already_chosen_is_not_chosen_twice(monkeypatch):
    first, second = (_port(endpoint) for endpoint in endpoints(2))
    monkeypatch.setattr(_ports, "_PICK", _Scripted(first, first, second))
    assert endpoints(2) == (f"tcp://127.0.0.1:{first}", f"tcp://127.0.0.1:{second}")


def test_a_kernel_choosing_ports_inside_the_band_is_refused():
    with pytest.raises(RuntimeError, match="from 30000 up, inside tests/_ports.py's band"):
        endpoints(1, floor=30000)


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
