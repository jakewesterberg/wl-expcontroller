"""`tools/measure_mark_check.py` (P4d-2b b2a, spec §5.4): the measurement runs, times
what it says it times, and its report says what it is and what it is not.

The numbers it produces are not tested -- they are what it exists to find out, and
they are committed under `docs/measurements/` by the task that runs it. What is
tested is that the script cannot quietly measure something else.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from wl_expcontroller.run import Quiet, run_trial

_SPEC = importlib.util.spec_from_file_location(
    "wlx_measure_mark_check",
    Path(__file__).resolve().parents[1] / "tools" / "measure_mark_check.py",
)
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)


def test_the_trial_it_times_ends_on_the_frame_it_names():
    """Frames per trial is the divisor of every per-frame figure, so the trial must
    run exactly that many."""
    for frames in (1, 37, 1000):
        result = run_trial(tool._trial(frames), Quiet(), tool.PERIOD, values={})
        assert result.frames == frames


def test_the_check_it_times_is_the_sessions_and_a_mark_would_be_stamped():
    class _Link:
        def __init__(self) -> None:
            self.calls = 0

        def mark_signal(self) -> int:
            self.calls += 1
            return 9 if self.calls == 3 else 0

    link = _Link()
    each_frame = tool._session_check(link)
    for frame in range(1, 6):
        each_frame(frame)

    assert link.calls == 5, "one check per frame"
    kept = [
        cell.cell_contents
        for cell in each_frame.__closure__
        if isinstance(cell.cell_contents, list)
    ]
    assert kept == [[(9, 3)]], "a mark is taken in the frame it answered"


def test_a_small_measurement_reports_both_loops_the_check_and_its_allocation():
    found = tool.measure(frames=50, trials=5, calls=2000)

    for key in ("without_ns", "with_ns", "check_ns"):
        assert set(found[key]) == {"median", "p90", "p99", "max"}
        assert 0 < found[key]["median"] <= found[key]["max"]
    assert found["alloc_held_by_link_bytes"] == 0

    text = tool.report(found)
    assert "**This is not V1, and not a frame-timing measurement.**" in text
    assert "Median added per frame by the check:" in text
    assert "V12 (`docs/validation.md`)" in text
    assert "--frames 50 --trials 5" in text


def test_the_command_line_writes_the_report_where_it_is_told(tmp_path, capsys):
    """`main` is how Task 14 commits the number, so the file `--out` names gets the
    report the options asked for, and the terminal says where it went."""
    out = tmp_path / "measurements" / "mark-check.md"

    code = tool.main(
        ["--frames", "20", "--trials", "3", "--calls", "500", "--out", str(out)]
    )

    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "Median added per frame by the check:" in text
    assert "--frames 20 --trials 3" in text
    assert capsys.readouterr().out == f"wrote {out}\n"
