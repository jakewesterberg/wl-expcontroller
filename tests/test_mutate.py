"""The mutation harness's own tests -- specifically, that its new escape hatch is narrow.

`tools/mutate.py` is the gate every other gate is checked by, and it has been wrong
four times, always the same way: quietly examining nothing and reporting success
(trap 7). `_already_inert` is a fifth change of exactly the dangerous shape -- a
category of result that does *not* fail the build -- so the point of this file is not
that it works on the case it was written for, but that it **refuses everything else**.

The detector is unit-tested rather than driven end to end because `mutate` runs the
whole pytest suite, and a test that invoked it from inside pytest would be running
this suite inside itself.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "wlx_mutate", Path(__file__).resolve().parents[1] / "tools" / "mutate.py"
)
mutate_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mutate_tool)
_already_inert = mutate_tool._already_inert


# ---------------------------------------------------------------------------
# What it must accept: bodies no mutation can reach
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "        return None",
        '        """A docstring and nothing else."""',
        "        ...",
        "        pass",
        '        """Docstring, then the same return."""\n        return None',
    ],
    ids=["return-none", "docstring-only", "ellipsis", "pass", "docstring-and-return"],
)
def test_a_body_that_already_returns_immediately_is_inert(body):
    source = f"class W:\n    def display(self, visible, frame) -> None:\n{body}\n"
    assert _already_inert(source, "display", "None")


def test_the_returned_value_has_to_match_not_merely_be_a_return():
    """`return []` under `--returns []` is inert; the same body under `--returns None`
    is a real mutation, because the function stops returning a list."""
    source = "def check(trial):\n        return []\n"
    assert _already_inert(source, "check", "[]")
    assert not _already_inert(source, "check", "None")


# ---------------------------------------------------------------------------
# What it must refuse -- the half that keeps the gate a gate
# ---------------------------------------------------------------------------


def test_a_real_body_is_never_inert():
    source = "def signal(self, frame):\n        return self.tracker.state(frame)\n"
    assert not _already_inert(source, "signal", "None")


def test_a_body_that_returns_late_is_not_inert():
    """Only the FIRST statement matters: a function that does work and then returns
    None is fully neutered by an early return, and that is a real mutation."""
    source = (
        "def display(self, visible, frame) -> None:\n"
        "        self.tracker.accept(self.source.poll(frame))\n"
        "        return None\n"
    )
    assert not _already_inert(source, "display", "None")


def test_one_real_definition_among_inert_ones_makes_the_whole_name_mutable():
    """All definitions of a name are neutered together, so the answer has to be about
    all of them. This is the case that would hide a genuine survivor: two worlds with
    no-op displays and a third that actually does something."""
    source = (
        "class Quiet:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        return None\n"
        "class Scripted:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        return None\n"
        "class Tracked:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        self.tracker.accept(self.source.poll(frame))\n"
    )
    assert not _already_inert(source, "display", "None")


def test_a_name_that_is_not_there_is_not_inert():
    """`found` guards the vacuous case. Without it an empty match would report inert,
    which is the harness's recurring failure exactly: examining nothing, reporting
    that all is well."""
    assert not _already_inert("def other():\n        return None\n", "display", "None")
    assert not _already_inert("", "display", "None")


def test_unparseable_source_is_not_inert():
    assert not _already_inert("def broken(:\n", "broken", "None")


# ---------------------------------------------------------------------------
# The functions this was actually written for
# ---------------------------------------------------------------------------


def test_the_real_no_op_displays_are_inert_and_the_real_one_is_not():
    """Against the shipped source rather than a fixture, so this fails if `run.py`'s
    worlds grow a body -- at which point the exemption must stop applying to them."""
    run_py = (Path(__file__).resolve().parents[1] / "wl_expcontroller" / "run.py").read_text()
    gaze_py = (Path(__file__).resolve().parents[1] / "wl_expcontroller" / "gaze.py").read_text()

    assert _already_inert(run_py, "display", "None"), "Quiet/Scripted display are no-ops"
    assert not _already_inert(gaze_py, "display", "None"), "Tracked.display polls gaze"
