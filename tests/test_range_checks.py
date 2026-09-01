"""Checks that reason over the values a console can dial in, not the ones set today.

Every parameter here is live-editable between trials, which means a task is not one
configuration but a *space* of them. A check against current values proves the task
happens not to be broken right now; a check against declared ranges proves an
experimenter cannot break it from the console.
"""

from wl_expcontroller.check import check
from wl_expcontroller.task import (
    After,
    Disc,
    Hold,
    On,
    Outcome,
    P,
    Param,
    Show,
    State,
    Stimulus,
    Trial,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))


def codes(trial) -> set[str]:
    return {f.code for f in check(trial)}


def two_windows(a_at, a_r, b_at, b_r, params=()) -> Trial:
    return Trial(
        start="wait",
        params=list(params),
        windows=[
            Window("a", at=a_at, radius=a_r, on="fix"),
            Window("b", at=b_at, radius=b_r, on="fix"),
        ],
        states=[
            State(
                "wait",
                enter=[Show(FIX)],
                go=[
                    On(Hold("a", 0.1), Outcome.CORRECT),
                    On(Hold("b", 0.1), Outcome.WRONG_TARGET),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )


def test_windows_that_overlap_are_refused():
    """A gaze position inside both scores whichever transition is listed first.

    Which is a coin flip decided by editing order, and it silently relabels errors
    as correct trials or the reverse -- in a task where nothing looks wrong.
    """
    assert "overlapping-windows" in codes(
        two_windows((0.0, 0.0), 3.0, (4.0, 0.0), 3.0)
    )


def test_windows_that_cannot_overlap_are_accepted():
    assert "overlapping-windows" not in codes(
        two_windows((0.0, 0.0), 2.0, (8.0, 0.0), 2.0)
    )


def test_windows_that_overlap_only_at_an_extreme_of_a_range_are_refused():
    """Separated today, overlapping at a setting the console allows."""
    trial = two_windows(
        (0.0, 0.0),
        P("fix_window"),
        (6.0, 0.0),
        2.0,
        params=[Param("fix_window", unit="deg", low=0.5, high=5.0)],
    )
    assert "overlapping-windows" in codes(trial)


def test_a_later_after_that_can_never_fire_first_is_refused():
    """Two time bounds where one always wins.

    The second is dead code that reads as a safety net, so the state it was meant
    to protect against is unprotected and nobody notices, because the line is there.
    """
    trial = Trial(
        start="wait",
        params=[],
        windows=[],
        states=[
            State(
                "wait",
                go=[
                    On(After(0.5), Outcome.NO_RESPONSE),
                    On(After(2.0), Outcome.ABORT),
                ],
            ),
        ],
    )
    assert "unreachable-timeout" in codes(trial)


def test_two_after_bounds_whose_ranges_cross_are_allowed():
    """Either can win depending on the setting, so neither is dead."""
    trial = Trial(
        start="wait",
        params=[
            Param("short", unit="s", low=0.1, high=3.0),
            Param("long", unit="s", low=0.2, high=1.0),
        ],
        windows=[],
        states=[
            State(
                "wait",
                go=[
                    On(After(P("short")), Outcome.NO_RESPONSE),
                    On(After(P("long")), Outcome.ABORT),
                ],
            ),
        ],
    )
    assert "unreachable-timeout" not in codes(trial)


def test_array_items_that_can_crowd_into_each_other_are_refused():
    """Set size and eccentricity are both live, so crowding is a console setting.

    Twelve items on a small ring with generous windows overlap, and then a saccade
    to one distractor is scored against another -- or against the target. The
    windows are generated, so no author ever looks at them.
    """
    from wl_expcontroller.task import Array, ItemWindows, SaccadeTo

    trial = Trial(
        start="search",
        params=[
            Param("set_size", unit="items", low=2, high=12),
            Param("eccentricity", unit="deg", low=3.0, high=12.0),
            Param("item_window", unit="deg", low=0.5, high=4.0),
        ],
        windows=[ItemWindows(of="search", radius=P("item_window"))],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(
                                n=P("set_size"),
                                radius=P("eccentricity"),
                                target=0,
                            ),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    assert "crowded-array" in codes(trial)


def test_an_array_that_cannot_crowd_is_accepted():
    from wl_expcontroller.task import Array, ItemWindows, SaccadeTo

    trial = Trial(
        start="search",
        params=[
            Param("set_size", unit="items", low=2, high=6),
            Param("eccentricity", unit="deg", low=8.0, high=12.0),
            Param("item_window", unit="deg", low=0.5, high=2.0),
        ],
        windows=[ItemWindows(of="search", radius=P("item_window"))],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(
                                n=P("set_size"),
                                radius=P("eccentricity"),
                                target=0,
                            ),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    assert "crowded-array" not in codes(trial)
