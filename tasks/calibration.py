"""The calibration block: one target, held, per trial.

**Written in the ordinary task vocabulary on purpose.** S5 §7 calls this a planned
block, and the cheapest way to find out whether the vocabulary can express its own
calibration was to write it there rather than build a special-purpose driver beside
it. It can, and the exercise cost nothing -- which is itself the finding, since the
previous four times a real artifact was written against this vocabulary it exposed a
gap (trap 5).

**The target position is a parameter, so the constellation is the block's schedule
rather than this file's business.** `calibration.constellation` says where the
thirteen targets go; the scheduler walks them one trial each, and an animal that
refuses one simply leaves that condition short. That is why `fit_eye` accepts fewer
targets than were presented and reports what it could reach.

**Nothing here fits anything.** The trial's job is to put a target up, decide whether
the animal really held it, and reward that. Turning held fixations into a map is
`calibration.Collector`'s, and it deliberately consumes only trials this task scored
`CORRECT` -- a fixation the task would not pay for is not one to calibrate against.

**Written for direct view** (`view="direct"`, direct-view spec §8), over its ±15° region.
The stereoscope's constellation, over its ±12° mask, is `calibration.constellation`'s too, and
the task that presents it does not exist yet: it is backlog item XC-005, not yet written.
(`wlx run --view stereoscope` exists since direct view part 2.)
"""

from wl_xcon.task import (
    After,
    Disc,
    Entered,
    Exited,
    Hold,
    Mark,
    On,
    Outcome,
    P,
    Param,
    Reward,
    Show,
    State,
    Stimulus,
    Trial,
    Window,
)

TARGET = Stimulus(
    "cal_target", at=(P("target_x"), P("target_y")), looks=Disc(size=0.3)
)

calibration = Trial(
    start="await_fix",
    view="direct",
    windows=[
        Window(
            "cal",
            at=(P("target_x"), P("target_y")),
            radius=P("cal_window"),
            on="cal_target",
        )
    ],
    params=[
        # Bounded to direct view's calibration region, ±15° × ±15° (direct-view spec
        # §6), not to the constellation of the day: check 8 inspects the parameter
        # *space*, and a range wider than the field is a task that can be scheduled
        # off-screen. Direct view shows ±30.5° × ±18.4°, so the region is the tighter
        # bound. It was ±12 in the interim, at the stereoscope's mask (2026-09-28), and
        # ±14.5 × ±16.1 before that, 0.85 of the 31.5-inch panel's field.
        Param("target_x", unit="deg", low=-15.0, high=15.0),
        Param("target_y", unit="deg", low=-15.0, high=15.0),
        # Wider than an ordinary fixation window. A calibration window has to admit
        # gaze that is *wrong by the amount calibration is about to correct*; sized
        # for a good map it would reject every fixation on the uncalibrated animal
        # it exists to measure.
        Param("cal_window", unit="deg", low=1.0, high=8.0),
        Param("fix_timeout", unit="s", low=0.5, high=10.0),
        Param("cal_hold", unit="s", low=0.1, high=2.0),
    ],
    states=[
        State(
            "await_fix",
            enter=[Show(TARGET), Mark(4105)],
            go=[
                On(Entered("cal"), "hold"),
                On(After(P("fix_timeout")), Outcome.NO_FIXATION, do=[Mark(4100)]),
            ],
        ),
        State(
            "hold",
            go=[
                On(
                    Hold("cal", P("cal_hold")),
                    Outcome.CORRECT,
                    do=[Mark(4106), Mark(4110), Reward("reward_correct")],
                ),
                On(Exited("cal"), Outcome.FIXATION_BREAK, do=[Mark(4101)]),
                # Bounded even though the two guards above are exhaustive in
                # practice, for the reason `fixation_detection` gives: check 4
                # refuses a state that could wait forever, and "in practice" is the
                # reasoning that produced the S1 bake-off's unbounded hold.
                On(After(P("fix_timeout")), Outcome.NO_FIXATION),
            ],
        ),
    ],
)
