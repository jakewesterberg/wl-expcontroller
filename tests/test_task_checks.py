"""The load-time checks from S1 §9.

A task that fails any of these is refused at load, not at run. The point is that a
generated task is caught before an animal sees it -- pitfalls P15.
"""

import pytest

from wl_expcontroller.task import (
    After,
    Blob,
    Bounded,
    Custom,
    GazeLeaves,
    On,
    Outcome,
    P,
    Param,
    Emit,
    Response,
    Reward,
    Show,
    State,
    Trial,
)
from wl_expcontroller.check import check
from dataclasses import replace

from wl_expcontroller.codes import PROVISIONAL, Allocation
from wl_expcontroller.components import Registry
from wl_expcontroller.geometry import Geometry


def test_a_state_no_transition_can_reach_is_reported():
    """S1 §9 check 2. A state nothing reaches is dead code in a task, and in a
    generated task it is the shape a hallucinated state name takes."""
    trial = Trial(
        start="await_fix",
        states=[
            State("await_fix", go=[On(After(4.0), Outcome.NO_FIXATION)]),
            State("orphan", go=[On(After(1.0), Outcome.CORRECT)]),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["unreachable-state"]
    assert "orphan" in findings[0].detail


def test_a_state_with_no_time_bound_is_reported_as_an_unbounded_wait():
    """S1 §9 check 4, and the defect the S1 bake-off actually produced: a
    fixation hold that can wait forever. Every wait needs a bound or an
    explicit declaration that it has none."""
    trial = Trial(
        start="hold_fix",
        states=[
            State(
                "hold_fix",
                go=[On(GazeLeaves("fix"), Outcome.FIXATION_BREAK)],
            ),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["unbounded-wait"]
    assert "hold_fix" in findings[0].detail


def test_a_state_declaring_itself_unbounded_is_accepted():
    """Free viewing of natural images is a first-class unbounded epoch (S1 §5.4).
    The check exists to make it deliberate and visible, not to forbid it."""
    trial = Trial(
        start="free_view",
        states=[
            State(
                "free_view",
                go=[On(Response("lever"), Outcome.CORRECT)],
                unbounded=True,
            ),
        ],
    )

    assert check(trial) == []


def test_a_reward_action_refuses_a_magnitude():
    """S1 §2.3 and S8 §4. A task may name a bounded-config entry; it may not say
    how much. The ceiling is enforced by what the task can express, not by review
    noticing -- which matters because the task was probably written by a model.

    A type checker catches this too. The runtime refusal is the one that catches
    a generated task at load, on a machine with no type checker running.
    """
    with pytest.raises(TypeError, match="bounded-config"):
        Reward(0.15)


def test_a_reward_action_names_a_bounded_config_entry():
    assert Reward(Bounded("reward_small")).ref.name == "reward_small"


def test_states_that_cannot_reach_an_outcome_are_reported():
    """S1 §9 check 3. A trial that can enter a loop with no exit to an outcome
    never scores, never ends, and never tells anyone why -- it just stops
    producing trials while looking like it is running."""
    trial = Trial(
        start="ping",
        states=[
            State("ping", go=[On(After(1.0), "pong")]),
            State("pong", go=[On(After(1.0), "ping")]),
        ],
    )

    findings = check(trial)

    assert {f.code for f in findings} == {"no-outcome-path"}
    assert {"ping", "pong"} == {f.detail.split("'")[1] for f in findings}


def test_a_transition_shadowed_by_an_earlier_identical_guard_is_reported():
    """S1 §9 check 10, in the form it takes once transitions fire in declared
    order (M0 §4): with order defined there is no ambiguity to detect, but a
    repeated guard means the later transition can never fire. That is dead code,
    and duplicating a guard is a shape a generated task produces readily."""
    trial = Trial(
        start="decide",
        states=[
            State(
                "decide",
                go=[
                    On(After(1.0), Outcome.NO_RESPONSE),
                    On(After(1.0), Outcome.CORRECT),
                ],
            ),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["shadowed-transition"]
    assert "decide" in findings[0].detail


def test_a_task_emitting_an_unallocated_code_is_refused():
    """S1 §9 check 1, and the cheapest guardrail in the design against a
    model-authored task (P15). A model will emit a plausible-looking number; the
    allocation is the only thing that knows 4097 means nothing."""
    allocation = replace(PROVISIONAL, task_events={4096: "STIMULUS_ON"})
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Emit(4097)],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, allocation)

    assert [f.code for f in findings] == ["unallocated-code"]
    assert "4097" in findings[0].detail


def test_a_task_emitting_an_allocated_code_is_accepted():
    allocation = replace(PROVISIONAL, task_events={4096: "STIMULUS_ON"})
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Emit(4096)],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert check(trial, allocation) == []


def test_a_task_referencing_an_undeclared_parameter_is_refused():
    """S1 §9 check 6. Parameters are declared with type, unit and range (S8 §3.1),
    and that one declaration drives validation, the console's widgets and the saved
    record. A reference to something undeclared has no widget, no range and no
    snapshot -- so it would be live-editable to any value, or not editable at all,
    and nobody would know which."""
    trial = Trial(
        start="hold",
        params=[Param("fix_hold", unit="s", low=0.1, high=2.0)],
        states=[
            State("hold", go=[On(After(P("response_window")), Outcome.NO_RESPONSE)]),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["undeclared-parameter"]
    assert "response_window" in findings[0].detail


def test_a_task_referencing_a_declared_parameter_is_accepted():
    trial = Trial(
        start="hold",
        params=[Param("fix_hold", unit="s", low=0.1, high=2.0)],
        states=[
            State("hold", go=[On(After(P("fix_hold")), Outcome.NO_RESPONSE)]),
        ],
    )

    assert check(trial) == []


def test_a_custom_component_that_does_not_resolve_is_refused():
    """S1 §9 check 9, and what makes S1 §8's typed seam real. A task may name
    behaviour the vocabulary lacks, but that behaviour lives in the framework's
    own reviewed source -- not in the task file. A name that resolves to nothing
    is the seam being used as a hole."""
    trial = Trial(
        start="stabilise",
        states=[
            State(
                "stabilise",
                enter=[Custom("retinal_stabilisation")],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, components=Registry({}))

    assert [f.code for f in findings] == ["unresolved-custom-component"]
    assert "retinal_stabilisation" in findings[0].detail


def test_a_resolving_custom_component_is_accepted_but_flagged_for_review():
    """S1 §8: a task using a Custom component goes on the human-review list beside
    the welfare-critical modules. Accepted is not the same as unremarkable."""
    registry = Registry({"retinal_stabilisation": "reviewed 2026-08-31"})
    trial = Trial(
        start="stabilise",
        states=[
            State(
                "stabilise",
                enter=[Custom("retinal_stabilisation")],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, components=registry)

    assert [f.code for f in findings] == ["custom-component-needs-review"]
    assert findings[0].blocking is False


GEOMETRY = Geometry(panel_diagonal_cm=80.01, viewing_distance_cm=57.0)


def test_a_stimulus_outside_the_field_is_refused():
    """S1 §9 check 8. Asked for a peripheral target, a model will write 30 degrees
    as readily as 10. The stimulus would be drawn off the panel, the animal would
    never see it, and the trial would score as a miss indistinguishable from
    behaviour -- which is the worst kind of defect, because the data looks fine."""
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Show(Blob(at=(30.0, 0.0)))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, geometry=GEOMETRY)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "30" in findings[0].detail


def test_disparity_can_push_one_eye_off_screen_from_a_legal_cyclopean_position():
    """The stereo defect a monocular check cannot see. Disparity is applied as
    equal and opposite horizontal offsets about the cyclopean position, so a
    stimulus comfortably inside the field can still put one eye's image outside
    it -- and only that eye's. On a split-screen stereoscope that is a stimulus
    the animal fuses on one side and loses on the other."""
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Show(Blob(at=(16.5, 0.0), disparity=2.0))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert GEOMETRY.can_show(16.5, 0.0), "the cyclopean position is legal"

    findings = check(trial, geometry=GEOMETRY)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "disparity" in findings[0].detail


def test_a_terminal_outcome_with_no_allocated_marker_is_refused():
    """S1 §9 check 5. An outcome that maps to no marker is a trial that ends
    without saying how it ended -- the recording carries the timing of a decision
    whose result is only in our files."""
    allocation = Allocation(outcomes={Outcome.CORRECT: 34})
    trial = Trial(
        start="decide",
        states=[
            State(
                "decide",
                go=[
                    On(After(1.0), Outcome.CORRECT),
                    On(GazeLeaves("fix"), Outcome.FIXATION_BREAK),
                ],
            ),
        ],
    )

    findings = check(trial, allocation)

    assert [f.code for f in findings] == ["unallocated-outcome"]
    assert "FIXATION_BREAK" in findings[0].detail
