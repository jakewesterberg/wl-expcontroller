"""A reference bounded config, for `wlx run` and for reading.

**Every number in this file is a placeholder and none of them is a protocol.**
There is no approved protocol figure in this repository for reward volume, daily
fluid, restraint time or trial count, and there will not be one until a person with
the protocol in front of them writes it down. What this file is for is the *shape*:
which entries a session needs, that each carries a current value and a maximum, and
that the units are stated.

Two guards, so a copy of this file cannot quietly become a real one:

- **The subject is `REFERENCE`.** A session refuses a bounded config whose subject is
  not its own, so running this against a real animal is impossible without editing
  the name -- and the name then appears on every trial row in the record.
- **The numbers are deliberately implausible**, small enough that nobody would mistake
  them for a protocol figure.

**The daily fluid figure is a floor, not a ceiling** (PI, 2026-09-06): a minimum the
animal must reach, topped up by hand after the session if the work did not earn it.
Nothing here caps earned reward, and `Floor` is a different type from `Ceiling` so
that the two cannot be confused at a call site.

Python rather than YAML for the reason the tasks are (ADR-0006): plain text,
diffable, and reviewable in an ordinary editor. A welfare-critical config is one a
human has to read before signing it off, and a diff is how they see what changed.
"""

from wl_expcontroller.bounds import Bounds, Ceiling, Floor

BOUNDS = Bounds(
    subject="REFERENCE",
    ceilings={
        # What one correct trial pays, and the most a console may ever set it to.
        # A real ceiling: the magnitude of a single delivery is where a slip is a dose.
        "reward_correct": Ceiling(value=0.05, maximum=0.20, unit="mL"),
        # Restraint time, from head-fixation. Not from the first trial.
        "chair_time": Ceiling(value=3_600.0, maximum=3_600.0, unit="s"),
        # Optional in a way the two above are not.
        "max_trials": Ceiling(value=2_000.0, maximum=5_000.0, unit="trials"),
    },
    minima={
        # The day's minimum, including what another deployment already delivered
        # (S8 sec 5.2b). A session reports what is still owed; it never refuses a
        # delivery for passing it.
        "daily_fluid": Floor(value=20.0, unit="mL"),
    },
)
