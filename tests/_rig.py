"""This rig with **stand-in** light-sensor housings, for the tests (backlog XC-056).

The real housings are unmeasured (direct-view spec §9 item 1), so `tasks/rig.py`'s
direct view refuses to exist, deliberately. The tests need one that does: these are
one per bottom corner, 4 × 3 cm with a 0.5 cm margin, and **nobody measured them**.
Everything else is `tasks/rig.py`'s own.

Also a rig settings file: it defines `RIG`, so `wlx run --rig` and `wlx check --rig`
can load it by `PATH`. Never collected, since its name does not start with `test_`. It loads `tasks/rig.py`
by path because `tasks/` is not part of the installed package, so `import tasks` works
under pytest's `pythonpath` and fails under the real `wlx`.
"""

import importlib.util
from dataclasses import replace
from pathlib import Path

from wl_xcon.geometry import Housing


def _load_this_rig():
    path = Path(__file__).resolve().parents[1] / "tasks" / "rig.py"
    spec = importlib.util.spec_from_file_location("_tasks_rig_by_path", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RIG


_THIS_RIG = _load_this_rig()

RIG = replace(
    _THIS_RIG,
    housings=(
        Housing(left_cm=0.0, right_cm=4.0, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
        Housing(left_cm=54.997, right_cm=58.997, bottom_cm=0.0, top_cm=3.0, margin_cm=0.5),
    ),
)
DIRECT = RIG.direct()
STEREOSCOPE = RIG.stereoscope(half_ipd_cm=1.6)
#: What `--rig` is given in the tests that run `wlx`.
PATH = "tests/_rig.py"
