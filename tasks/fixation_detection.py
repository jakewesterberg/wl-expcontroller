"""Fixation -> detection. The first task intended to run on an animal (roadmap M6).

Fixate, hold, a target appears at one of six positions, saccade to it, hold, reward.

Every number here is a parameter rather than a literal, because S8 §3 makes them
live-editable between trials and the console's widgets are generated from these
declarations. A literal would be invisible to all of that.
"""

from wl_xcon.task import (
    After,
    Bounded,
    Mark,
    Disc,
    Entered,
    Hold,
    Exited,
    On,
    Outcome,
    P,
    Param,
    Reward,
    SaccadeTo,
    Show,
    Square,
    State,
    Stimulus,
    Trial,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))
TARGET = Stimulus("target", at=(P("target_position"), 0.0), looks=P("target_looks"))

detection = Trial(
    start="await_fix",
    # The first animal task runs in direct view (PI, 2026-09-28), and its ±16° is wider
    # than the stereoscope's mask.
    view="direct",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
        Window(
            "target",
            at=(P("target_position"), 0.0),
            radius=P("target_window"),
            on="target",
        ),
    ],
    # Each number starts where the console mockup the PI reviewed shows it (P4d-2b spec
    # §6.2, "Starting values are the task's own"); the appearance is left to the run.
    params=[
        Param("fix_timeout", unit="s", low=0.5, high=10.0, start=4.0),
        Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),
        Param("response_window", unit="s", low=0.1, high=3.0, start=0.6),
        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),
        Param("fix_window", unit="deg", low=0.5, high=5.0, start=2.0),
        Param("target_window", unit="deg", low=0.5, high=6.0, start=3.0),
        # ±16° again (direct-view spec §8), checked against direct view's ±30.5° field.
        # ±12 was the interim, at the stereoscope's mask, before direct view had a
        # `Geometry` (2026-09-28).
        Param("target_position", unit="deg", low=-16.0, high=16.0, start=10.0),
        # Appearance is a parameter, so switching circles among squares for
        # penguins among elephants is a value applied in an ITI -- not a new
        # task and not a new block.
        Param(
            "target_looks",
            unit="appearance",
            choices=(Disc(size=1.0), Square(size=1.0)),
        ),
    ],
    states=[
        State(
            "await_fix",
            enter=[Show(FIX), Mark(4096)],
            go=[
                On(Entered("fix"), "hold_fix"),
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
                On(Hold("fix", P("fix_hold")), "stim_on"),
                On(
                    Exited("fix"),
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
                    Hold("target", P("target_hold")),
                    Outcome.CORRECT,
                    do=[
                        Mark(4099),
                        Mark(4102),
                        Reward("reward_correct"),
                    ],
                ),
                On(Exited("target"), Outcome.WRONG_TARGET),
                On(After(P("response_window")), Outcome.NO_RESPONSE),
            ],
        ),
    ],
)
