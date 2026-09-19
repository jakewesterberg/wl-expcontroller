"""A reference bounded config, for `wlx run` and for reading.

**Every number in this file is a placeholder and none of them is a protocol.**
There is no approved protocol figure in this repository for reward volume, daily
fluid or time out of the cage, and there will not be one until a person with the
protocol in front of them writes it down. What this file is for is the *shape*:
which entries a session needs, that each carries a current value and a maximum, and
that the units are stated.

Two guards, so a copy of this file cannot quietly become a real one:

- **The subject is `REFERENCE`.** A session refuses a bounded config whose subject is
  not its own, so running this against a real animal is impossible without editing
  the name -- and the name then appears on every trial row in the record.
- **The numbers are deliberately implausible**, each in whichever direction makes it
  unmistakable. Most are far too small to be a protocol figure. `reward_correct`'s
  *maximum* is the exception and runs the other way: 10 mL is far too large to be a
  dose, because it is not one -- see the entry itself.

**Each ceiling states which kind of limit its maximum is** -- a protocol figure or a
fault bound (`bounds.Ceiling`). Both are enforced identically, so the comment is the
only place the difference is written down, and a reviewer signing this off is entitled
to know which refusal they are approving.

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
        # What one correct trial pays, and a **fault bound** on it -- specifically a
        # runaway-fluid one (PI, 2026-09-19). Not a ration and not a protocol dose:
        # 10 mL in one delivery is the size of thing that happens only when software
        # is broken -- a loop, a unit slip, a console sending litres -- so refusing
        # it catches a fault rather than enforcing a limit on an animal. The value
        # beside it is still an ordinary placeholder, and the daily figure below is
        # still a floor; nothing here caps what an animal may earn.
        "reward_correct": Ceiling(value=0.05, maximum=10.0, unit="mL"),
        # **The session's one duration limit** (PI, 2026-09-19): out of the home
        # cage to back in it, which is what the twelve-hour institutional figure is
        # about -- not chair time, which starts at head-fixation and so misses the
        # transport and chairing before it. **A protocol figure**: an institution
        # states it, and the number changes when the protocol does.
        #
        # Ten minutes, and therefore a placeholder like everything else here. The
        # real figure is twelve hours; nobody could mistake this one for it, which
        # is this file's second guard doing its job.
        "out_of_cage": Ceiling(value=600.0, maximum=600.0, unit="s"),
        # There is no `chair_time` ceiling and no `max_trials` ceiling. Both were
        # here until 2026-09-19, when the PI ruled that **there is no session-length
        # maximum** -- per-condition targets are a task's config and the scheduler's
        # job -- and that the one welfare duration limit runs out of cage to back in
        # cage. Chair time is still recorded, by `HEAD_FIXED`/`HEAD_RELEASED`; it is
        # simply not a limit, so there is nothing here for it.
    },
    minima={
        # The day's minimum, including what another deployment already delivered
        # (S8 sec 5.2b). A session reports what is still owed; it never refuses a
        # delivery for passing it.
        "daily_fluid": Floor(value=20.0, unit="mL"),
    },
)
