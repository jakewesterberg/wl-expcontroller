"""Detection with contrast on a staircase, and mini-blocks of held eccentricity.

The task S1's bake-off expected to be the hard case, and it was not: **the trial is
`fixation_detection`'s trial unchanged.** A staircase was never a within-trial
concern. Everything adaptive here lives in `next_params`, which is ordinary Python
called at a trial boundary, outside the frame budget (ADR-0006).

That is the whole argument for the split, demonstrated rather than asserted: the
strongest case for imperative trials evaporates once condition generation lives
between trials, where it always belonged.
"""

from dataclasses import dataclass, field

from wl_expcontroller.task import (
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

adaptive_detection = Trial(
    start="await_fix",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
        Window(
            "target",
            at=(P("target_position"), 0.0),
            radius=P("target_window"),
            on="target",
        ),
    ],
    params=[
        Param("fix_timeout", unit="s", low=0.5, high=10.0),
        Param("fix_hold", unit="s", low=0.05, high=2.0),
        Param("response_window", unit="s", low=0.1, high=3.0),
        Param("target_hold", unit="s", low=0.05, high=1.0),
        Param("fix_window", unit="deg", low=0.5, high=5.0),
        Param("target_window", unit="deg", low=0.5, high=6.0),
        Param("target_position", unit="deg", low=-16.0, high=16.0),
        # Appearance is a parameter, so switching circles among squares for
        # penguins among elephants is a value applied in an ITI -- not a new
        # task and not a new block.
        Param(
            "target_looks",
            unit="appearance",
            choices=(Disc(size=1.0), Square(size=1.0)),
        ),
        Param("contrast", unit="fraction", low=0.02, high=1.0),
        Param("eccentricity", unit="deg", low=2.0, high=16.0),
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
                On(Hold("fix", P("fix_hold")), "stim_on"),
                On(Exited("fix"), Outcome.FIXATION_BREAK, do=[Mark(4101)]),
                On(After(P("fix_timeout")), Outcome.NO_FIXATION, do=[Mark(4100)]),
            ],
        ),
        State(
            # The target's position and contrast are parameters, so a mini-block
            # that moves the array from 0 to 10 degrees is a value change applied
            # in an ITI -- not a new task, and not a new block (S3 §7).
            "stim_on",
            enter=[
                Show(
                    Stimulus(
                        "target",
                        at=(P("target_position"), 0.0),
                        looks=P("target_looks"),
                    )
                ),
                Mark(4097),
            ],
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
                    do=[Mark(4099), Mark(4102), Reward("reward_correct")],
                ),
                On(Exited("target"), Outcome.WRONG_TARGET),
                On(After(P("response_window")), Outcome.NO_RESPONSE),
            ],
        ),
    ],
)


@dataclass
class Staircase:
    """One-up two-down on contrast, converging near 71% correct.

    Between-trial Python. It holds state across trials, does arbitrary arithmetic,
    and none of that costs anything -- it runs in the inter-trial interval where
    an error is observable and recoverable rather than inside a frame budget.
    """

    value: float
    step: float = 0.8
    floor: float = 0.02
    ceiling: float = 1.0
    _consecutive_correct: int = field(default=0, repr=False)

    def update(self, correct: bool) -> None:
        if not correct:
            self._consecutive_correct = 0
            self.value = min(self.ceiling, self.value / self.step)
            return
        self._consecutive_correct += 1
        if self._consecutive_correct >= 2:
            self._consecutive_correct = 0
            self.value = max(self.floor, self.value * self.step)


def next_params(
    staircase: Staircase, eccentricity: float, last: Outcome | None
) -> dict[str, float]:
    """The next trial's values. Called at a trial boundary, never inside one.

    Only completed trials move the staircase: an abort says nothing about
    difficulty, and letting one move the estimate makes contrast track engagement
    rather than perception.
    """
    if last in (Outcome.CORRECT, Outcome.WRONG_TARGET):
        staircase.update(last is Outcome.CORRECT)
    return {
        "fix_timeout": 4.0,
        "fix_hold": 0.3,
        "response_window": 0.6,
        "target_hold": 0.2,
        "contrast": staircase.value,
        "eccentricity": eccentricity,
    }
