"""Fixation -> detection. The first task intended to run on an animal (roadmap M6).

Fixate, hold, a target appears at one of six positions, saccade to it, hold, reward.

Every number here is a parameter rather than a literal, because S8 §3 makes them
live-editable between trials and the console's widgets are generated from these
declarations. A literal would be invisible to all of that.
"""

from wl_expcontroller.task import (
    After,
    Spot,
    Bounded,
    Mark,
    FixPoint,
    Acquired,
    Held,
    Broke,
    On,
    Outcome,
    P,
    Param,
    Reward,
    SaccadeTo,
    Show,
    State,
    Trial,
    Window,
)

FIX = FixPoint(at=(0.0, 0.0), size=0.3)
TARGET = Spot(at=(10.0, 0.0), size=1.0)

detection = Trial(
    start="await_fix",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window")),
        Window("target", at=(P("target_position"), 0.0), radius=P("target_window")),
    ],
    params=[
        Param("fix_timeout", unit="s", low=0.5, high=10.0),
        Param("fix_hold", unit="s", low=0.05, high=2.0),
        Param("response_window", unit="s", low=0.1, high=3.0),
        Param("target_hold", unit="s", low=0.05, high=1.0),
        Param("fix_window", unit="deg", low=0.5, high=5.0),
        Param("target_window", unit="deg", low=0.5, high=6.0),
        Param("target_position", unit="deg", low=-16.0, high=16.0),
    ],
    states=[
        State(
            "await_fix",
            enter=[Show(FIX), Mark(4096)],
            go=[
                On(Acquired("fix"), "hold_fix"),
                On(
                    After(P("fix_timeout")),
                    Outcome.NO_FIXATION,
                    do=[Mark(4100)],
                ),
            ],
        ),
        State(
            "hold_fix",
            go=[
                On(Held("fix", P("fix_hold")), "stim_on"),
                On(
                    Broke("fix"),
                    Outcome.FIXATION_BREAK,
                    do=[Mark(4101)],
                ),
                # A bound even though the two guards above are exhaustive in
                # practice: check 4 refuses a state that could wait forever, and
                # "in practice" is exactly the reasoning that produced the S1
                # bake-off's unbounded hold.
                On(After(P("fix_timeout")), Outcome.NO_FIXATION),
            ],
        ),
        State(
            "stim_on",
            enter=[Show(TARGET), Mark(4097)],
            go=[
                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),
                On(After(P("response_window")), Outcome.NO_RESPONSE),
            ],
        ),
        State(
            "verify",
            go=[
                On(
                    Held("target", P("target_hold")),
                    Outcome.CORRECT,
                    do=[
                        Mark(4099),
                        Mark(4102),
                        Reward(Bounded("reward_correct")),
                    ],
                ),
                On(Broke("target"), Outcome.WRONG_TARGET),
                On(After(P("response_window")), Outcome.NO_RESPONSE),
            ],
        ),
    ],
)
