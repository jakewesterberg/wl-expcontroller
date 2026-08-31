"""The review artifact.

ADR-0006 rests on this: a task Claude wrote is approved from a rendered diagram, a
code table and a simulation report, **without reading the source**. If that is not
possible, the design failed rather than the reviewer -- so the artifact is a
deliverable, not a convenience.
"""

from __future__ import annotations

from wl_expcontroller.review import render
from wl_expcontroller.task import (
    After,
    Mark,
    Hold,
    Exited,
    On,
    P,
    Param,
    Outcome,
    State,
    Trial,
    Window,
)

TRIAL = Trial(
    start="hold",
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
    states=[
        State(
            "hold",
            enter=[Mark(4096)],
            go=[
                On(Exited("fix"), Outcome.FIXATION_BREAK),
                On(After(0.3), Outcome.CORRECT),
            ],
        ),
    ],
)


def test_the_diagram_shows_every_transition_with_its_guard():
    """A diagram that omits a transition is worse than none: it is a picture a
    reviewer trusts, showing a task that is not the one that will run."""
    artifact = render(TRIAL)

    assert "stateDiagram-v2" in artifact
    assert "[*] --> hold" in artifact
    assert "hold --> FIXATION_BREAK: Exited(fix)" in artifact
    assert "hold --> CORRECT: After(0.3s)" in artifact


def test_the_code_table_names_what_each_code_means():
    """A recorded code carries timing without meaning. The reviewer has to be able
    to see which state emits what, or the event stream is unreviewable."""
    artifact = render(TRIAL, allocation_names={4096: "FIX_ON"})

    assert "4096" in artifact
    assert "FIX_ON" in artifact
    assert "hold" in artifact


def test_a_parameter_reference_renders_as_its_name():
    """The artifact exists to be read. `After(fix_timeouts)` -- a unit suffix glued
    to a parameter name -- and a raw `P(name='fix_hold')` are both noise in the one
    place noise costs the most, because a reviewer who stops trusting the diagram
    goes back to reading source, which is the thing this replaces."""
    trial = Trial(
        start="hold",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        params=[Param("fix_hold", unit="s", low=0.05, high=2.0)],
        states=[
            State(
                "hold",
                go=[
                    On(Hold("fix", P("fix_hold")), Outcome.CORRECT),
                    On(After(P("fix_hold")), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )

    artifact = render(trial)

    assert "Hold(fix, fix_hold)" in artifact
    assert "After(fix_hold)" in artifact
    assert "P(name=" not in artifact
    assert "fix_holds" not in artifact
