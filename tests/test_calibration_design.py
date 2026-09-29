"""The design tool that chose each setup's reach, held to the records it wrote.

`tools/calibration_design.py` is outside the mutation gate -- no gate mode reaches
`tools/` -- so these tests are what a hand sweep of it reads. They pin what is
deterministic: each setup's inputs, the region a run scores, the constellation section
7 lays out (against the committed record, digit for digit), and that a run prints every
section for its setup. **The Monte-Carlo tables are not compared here**: they are
reproduced by rerunning the script, which the records say how to do, and a byte-for-byte
test of them would hold CI to another machine's floating point.

The tool imports `wl-preproc`'s own conditioning metric, so without that checkout these
skip, and under `WLX_REQUIRE_PREPROC=1` they fail, as `test_calibration.py`'s do.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path

import pytest

from wl_xcon.calibration import DIRECT_REGION_DEG, REACH

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "docs" / "measurements" / "dev-machine"

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    import wl_preproc.eye.calibration  # noqa: F401 -- the tool measures with theirs
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). The "
            f"design tool measures with their conditioning metric, so without it these "
            f"tests would report a tool nobody ran"
        ) from exc
    _AVAILABLE = False
else:
    _AVAILABLE = True

pytestmark = pytest.mark.skipif(
    not _AVAILABLE, reason="wl-preproc checkout not beside this repo; the tool cannot run"
)


def _tool():
    """A fresh copy of the tool for each test: `use` rebinds its module globals, and
    no test may inherit another's setup."""
    spec = importlib.util.spec_from_file_location(
        "calibration_design", ROOT / "tools" / "calibration_design.py"
    )
    module = importlib.util.module_from_spec(spec)
    # `dataclass` looks its module up here to read the tool's annotations.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def _section_7(text: str) -> str:
    return text[text.index("## 7."):].strip()


def test_the_default_setup_is_the_one_the_2026_09_05_record_was_measured_on():
    tool = _tool()
    setup = tool.use("2026-09-05")

    assert setup.record == "2026-09-05-calibration-constellation.md"
    assert (tool.HALF_H, tool.HALF_V) == (
        tool.GEOMETRY.half_field_h_deg,
        tool.GEOMETRY.half_field_v_deg,
    )
    assert tool.FIELD == (tool.HALF_H, tool.HALF_V)
    assert (tool.MAX_TESTED_DEG, tool.SHOWN_REACH) == (16.0, 0.75)


def test_direct_view_is_scored_over_its_whole_disc_and_scaled_to_its_region():
    """The detection tasks' ±16° is wider than the ±15° region, so the disc must not
    be clipped to the region: it lies inside the field, and a window can land there."""
    tool = _tool()
    setup = tool.use("direct")

    assert setup.record == "2026-09-28-calibration-constellation-direct.md"
    assert (tool.HALF_H, tool.HALF_V) == (DIRECT_REGION_DEG, DIRECT_REGION_DEG)
    assert tool.FIELD is None
    assert tool.SHOWN_REACH == REACH["direct"]
    points = tool.tested_region()
    assert max(math.hypot(x, y) for x, y in points) == pytest.approx(16.0)
    assert max(abs(x) for x, _ in points) > DIRECT_REGION_DEG


def test_the_stereoscope_is_scaled_to_its_mask_and_scored_inside_it():
    tool = _tool()
    setup = tool.use("stereoscope")

    assert setup.record == "2026-09-28-calibration-constellation-stereoscope.md"
    assert (tool.HALF_H, tool.HALF_V) == (12.0, 12.0)
    assert tool.FIELD == (12.0, 12.0)
    assert tool.SHOWN_REACH == REACH["stereoscope"]
    points = tool.tested_region()
    assert max(math.hypot(x, y) for x, y in points) == pytest.approx(12.0)
    assert all(abs(x) <= 12.0 and abs(y) <= 12.0 for x, y in points)


@pytest.mark.parametrize("name", ["2026-09-05", "direct", "stereoscope"])
def test_each_records_constellation_is_what_the_tool_lays_out_now(name, capsys):
    """Section 7 is arithmetic, not simulation, so it is compared with the committed
    record digit for digit: a change to a region, a reach or the mask that leaves a
    record describing a constellation the code no longer presents fails here."""
    tool = _tool()
    setup = tool.use(name)
    tool.section_recommended()

    record = (RECORDS / setup.record).read_text()
    assert capsys.readouterr().out.strip() == _section_7(record)


@pytest.mark.parametrize(
    ("argv", "extent", "reach"),
    [
        ([], "Per-eye field: +/-17.01 deg horizontal, +/-18.99 deg vertical.", "75%"),
        (
            ["--setup", "direct"],
            "Calibration region, direct view: +/-15.00 deg horizontal, +/-15.00 deg vertical.",
            "85%",
        ),
        (
            ["--setup", "stereoscope"],
            "Calibration region, stereoscope (the mask): +/-12.00 deg horizontal, "
            "+/-12.00 deg vertical.",
            "100%",
        ),
    ],
)
def test_a_run_prints_every_section_for_its_setup(argv, extent, reach, capsys):
    tool = _tool()
    tool.main(argv)
    out = capsys.readouterr().out

    for section in range(1, 8):
        assert f"\n## {section}. " in out, f"section {section} is missing"
    assert extent in out
    assert out.count(f"| 3x3 @{reach} + 4 intermediates |") == 2
    assert out.count(f"| 3x3 @{reach} (9) |") == 2
    assert f"| 5x5 @{reach} (25) |" in out
