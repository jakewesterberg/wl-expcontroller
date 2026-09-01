"""Set size as a value, not a structure.

An N-item search array written as N separate `Show` actions makes set size a change
to the *shape* of the task -- a different task file for 4 items and 8 items, which
defeats the entire reason the model is declarative and makes the commonest
manipulation in visual search unavailable to live editing. Visual search is the
lab's programme, so this was not a small gap.
"""

import math

import pytest

from wl_expcontroller.check import check
from wl_expcontroller.task import (
    Array,
    Disc,
    ItemWindows,
    On,
    After,
    Outcome,
    P,
    Param,
    SaccadeTo,
    Show,
    Square,
    State,
    Stimulus,
    Trial,
)


def test_set_size_is_a_parameter_the_array_expands_at_run_time():
    array = Array(n=P("set_size"), radius=8.0, target=P("target_index"))
    positions = array.positions({"set_size": 6, "target_index": 2})

    assert len(positions) == 6
    # Evenly spaced on a ring of the declared radius.
    for x, y in positions:
        assert math.isclose(math.hypot(x, y), 8.0, abs_tol=1e-9)
    angles = sorted(math.atan2(y, x) % (2 * math.pi) for x, y in positions)
    gaps = [b - a for a, b in zip(angles, angles[1:])]
    assert all(math.isclose(g, 2 * math.pi / 6, abs_tol=1e-9) for g in gaps)


def test_the_target_wears_the_target_appearance_and_the_rest_do_not():
    array = Array(n=4, target=1, looks=Square(size=1.0), among=Disc(size=1.0))
    worn = [array.item_looks(i, {}) for i in range(4)]

    assert worn[1] == Square(size=1.0)
    assert worn[0] == worn[2] == worn[3] == Disc(size=1.0)


def test_a_target_index_outside_the_set_is_refused_over_the_whole_range():
    """Legal at the value someone tested, illegal at one the console can set.

    Set size and target index are both live parameters, so an experimenter can put
    the target at position 6 of a 4-item array between one trial and the next. The
    check reasons over declared *ranges*, which is the only way to catch it before
    it happens.
    """
    trial = Trial(
        start="on",
        windows=[ItemWindows(of="search", radius=2.0)],
        params=[
            Param("set_size", unit="items", low=2, high=8),
            Param("target_index", unit="index", low=0, high=11),
        ],
        states=[
            State(
                "on",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=P("set_size"), target=P("target_index")),
                        )
                    )
                ],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )
    assert "target-outside-array" in {f.code for f in check(trial)}


def test_the_array_generates_its_own_windows():
    """One declaration, n windows, because n is not known until a trial runs."""
    windows = ItemWindows(of="search", radius=2.0).expand(
        Array(n=4, radius=8.0, target=1), {}
    )
    names = {w.name for w in windows}

    assert names == {
        "search.0",
        "search.1",
        "search.2",
        "search.3",
        "search.target",
        "search.distractor",
    }
    # The target alias sits where item 1 sits, not somewhere of its own.
    by_name = {w.name: w for w in windows}
    assert by_name["search.target"].at == by_name["search.1"].at
    # Every generated window scores the array, so the display check applies to
    # them exactly as it does to a hand-written window.
    assert all(w.on == "search" for w in windows)


def test_a_saccade_to_a_distractor_is_distinguishable_from_one_to_the_target():
    """The measurement search tasks exist to make.

    Without a distractor alias every error saccade would have to be enumerated as
    a separate transition per item -- which is n transitions, so it is the same
    structure-versus-value problem one level down.
    """
    from wl_expcontroller.run import Scripted, run_trial

    trial = Trial(
        start="search",
        windows=[ItemWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=8.0, target=1),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    to_distractor = Scripted(at_frame={SaccadeTo("search.distractor"): 3})
    assert run_trial(trial, to_distractor, 0.01).outcome is Outcome.WRONG_TARGET

    to_target = Scripted(at_frame={SaccadeTo("search.target"): 3})
    assert run_trial(trial, to_target, 0.01).outcome is Outcome.CORRECT


def test_an_array_that_would_not_fit_on_the_display_is_refused():
    """Check 8, over an array's items rather than one stimulus."""
    from wl_expcontroller.geometry import Geometry

    trial = Trial(
        start="on",
        windows=[ItemWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "on",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=40.0, target=0),
                        )
                    )
                ],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )
    geometry = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)
    codes = {f.code for f in check(trial, geometry=geometry)}
    assert "stimulus-off-screen" in codes


def test_a_hold_on_an_alias_resolves_to_the_item_it_names():
    """`search.target` is where item 1 is, and the loop must know that.

    A saccade guard reaches the world directly, so aliases worked there by accident.
    Membership guards -- entering, leaving, holding -- are derived by the loop from
    concrete windows, and an unresolved alias would simply never be satisfied: the
    animal fixates the target and the task waits forever.
    """
    from wl_expcontroller.run import run_trial
    from wl_expcontroller.task import Hold

    trial = Trial(
        start="search",
        windows=[ItemWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=8.0, target=1),
                        )
                    )
                ],
                go=[
                    On(Hold("search.target", 0.02), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )

    class OnItem:
        """A world that knows only concrete item windows, as a rig would."""

        def __init__(self, item: str) -> None:
            self.item = item

        def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
            return window == self.item

        def happened(self, guard, state: str, frame: int) -> bool:
            return False

        def display(self, visible, frame: int) -> None:
            pass

        def signal(self, frame: int) -> str:
            return "ok"

    assert run_trial(trial, OnItem("search.1"), 0.01).outcome is Outcome.CORRECT
    assert run_trial(trial, OnItem("search.2"), 0.01).outcome is Outcome.NO_RESPONSE


def test_a_search_task_simulates():
    """The simulator must cope with windows it did not get from `trial.windows`."""
    from wl_expcontroller.simulate import Subject, simulate

    trial = Trial(
        start="search",
        windows=[ItemWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=8.0, target=1),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    census = simulate(
        trial,
        # Not fully engaged, so some trials time out: with every trial engaged and
        # a 4/s saccade hazard over a 1 s window, NO_RESPONSE is unreachable.
        Subject(seed=3, engagement=0.85, hazards={SaccadeTo: 4.0}),
        trials=200,
        frame_period=1 / 240,
    )
    assert census.outcomes[Outcome.CORRECT] > 0
    assert census.uncovered(trial) == set()
