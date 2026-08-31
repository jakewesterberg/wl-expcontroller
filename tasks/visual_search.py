"""Colour pop-out search. The paradigm the vocabulary could not express.

Until 2026-08-31 this task was **unwritable**, twice over. There was no colour, so a
red target among green distractors could not be stated at all; and an array was N
separate `Show` actions, so set size was a change to the *shape* of the task rather
than a value -- a different file for four items and eight, invisible to live editing.
Both are the commonest manipulations in visual search, which is the lab's programme.

What makes this the pop-out paradigm rather than a collection of shapes: the target
and the distractors differ in **exactly one** feature, and which feature is a
parameter. Swapping `target_looks` from a red disc to a square turns a colour
pop-out into a shape pop-out between one trial and the next, with the same task
running and the same structure recorded.

`target_looks` and `distractors` are isoluminant by construction -- `DKL(lum=0)` --
which is a claim about photometry, so this task **will not load without a measured
display calibration**. That is deliberate. No calibration for our panels exists yet.
"""

from wl_expcontroller.photometry import DKL
from wl_expcontroller.task import (
    After,
    Array,
    Bounded,
    Disc,
    Entered,
    Exited,
    Hold,
    ItemWindows,
    Mark,
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

#: A red and a green of equal luminance, as cone contrasts from the background.
#: Equal *by construction* rather than by arithmetic somebody did once: the whole
#: reason DKL is the space this is written in.
RED = DKL(lum=0.0, l_m=0.08)
GREEN = DKL(lum=0.0, l_m=-0.08)

ARRAY = Stimulus(
    "search",
    at=(0.0, 0.0),
    looks=Array(
        n=P("set_size"),
        radius=P("eccentricity"),
        target=P("target_index"),
        looks=P("target_looks"),
        among=P("distractors"),
        phase=P("array_phase"),
    ),
)

search = Trial(
    start="await_fix",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
        # One declaration, `set_size` windows. The author cannot write them out,
        # because how many there are is not known until a trial runs.
        ItemWindows(of="search", radius=P("item_window")),
    ],
    params=[
        Param("fix_timeout", unit="s", low=0.5, high=10.0),
        Param("fix_hold", unit="s", low=0.05, high=2.0),
        Param("response_window", unit="s", low=0.1, high=3.0),
        Param("target_hold", unit="s", low=0.05, high=1.0),
        Param("fix_window", unit="deg", low=0.5, high=5.0),
        Param("item_window", unit="deg", low=0.5, high=4.0),
        Param("eccentricity", unit="deg", low=3.0, high=12.0),
        # The manipulation. A value, not a structure -- which is the entire point.
        Param("set_size", unit="items", low=2, high=12),
        # `high` is one below `set_size`'s *lowest* legal value, because the checker
        # reasons over ranges: a target index of 6 is illegal the moment set size
        # can be 2, whatever it happens to be set to right now.
        Param("target_index", unit="index", low=0, high=1),
        #: Randomised between trials so the animal cannot learn positions.
        Param("array_phase", unit="deg", low=0.0, high=360.0),
        # Feature as a value. Red-among-green and square-among-discs are the same
        # task with a different setting.
        Param(
            "target_looks",
            unit="appearance",
            choices=(
                Disc(size=1.0, color=RED),
                Disc(size=1.0, color=GREEN),
                Square(size=1.0, color=GREEN),
            ),
        ),
        Param(
            "distractors",
            unit="appearance",
            choices=(Disc(size=1.0, color=GREEN), Disc(size=1.0, color=RED)),
        ),
    ],
    states=[
        State(
            "await_fix",
            enter=[Show(FIX), Mark(4096)],
            go=[
                On(Entered("fix"), "hold_fix"),
                On(After(P("fix_timeout")), Outcome.NO_FIXATION, do=[Mark(4100)]),
            ],
        ),
        State(
            "hold_fix",
            go=[
                On(Hold("fix", P("fix_hold")), "array_on"),
                On(Exited("fix"), Outcome.FIXATION_BREAK, do=[Mark(4101)]),
                On(After(P("fix_timeout")), Outcome.NO_FIXATION),
            ],
        ),
        State(
            "array_on",
            enter=[Show(ARRAY), Mark(4103)],
            go=[
                On(SaccadeTo("search.target"), "verify", do=[Mark(4098)]),
                # One transition for every distractor there will ever be. Enumerating
                # them would be the same structure-versus-value problem one level
                # down, and would make the measurement this task exists for --
                # target versus distractor -- unavailable.
                On(
                    SaccadeTo("search.distractor"),
                    Outcome.WRONG_TARGET,
                    do=[Mark(4104), Mark(4113)],
                ),
                On(After(P("response_window")), Outcome.NO_RESPONSE, do=[Mark(4117)]),
            ],
        ),
        State(
            "verify",
            go=[
                On(
                    Hold("search.target", P("target_hold")),
                    Outcome.CORRECT,
                    do=[Mark(4099), Mark(4110), Mark(4102), Reward("reward_correct")],
                ),
                On(Exited("search.target"), Outcome.TARGET_BREAK, do=[Mark(4120)]),
                On(After(P("response_window")), Outcome.NO_RESPONSE, do=[Mark(4117)]),
            ],
        ),
    ],
)
