"""The load-time checks from S1 §9.

A task that fails any of these is refused at load, not at run. The point is that a
generated task is caught before an animal sees it -- pitfalls P15.
"""

import pytest

from wl_xcon.task import (
    RDS,
    Corrugation,
    Disc,
    REMEMBERED,
    After,
    Array,
    Entered,
    Bounded,
    Custom,
    Exited,
    On,
    Outcome,
    P,
    Param,
    Mark,
    Response,
    Reward,
    Show,
    State,
    Stimulus,
    Update,
    Window,
    Trial,
)
from wl_xcon.check import check
from dataclasses import replace

# `GEOMETRY` is the rig's stereoscope at the drawing's `E` = 1.6 cm: a 63.15 cm path, and
# the ±13.15° × ±14.77° viewport stopped by the PI's ±12° mask. `DIRECT` is the rig in
# direct view. Both are `tests/_rig.py`'s, with its stand-in housings.
from _rig import DIRECT, STEREOSCOPE as GEOMETRY
from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.components import Registry
from wl_xcon.geometry import Geometry


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
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "hold_fix",
                go=[On(Exited("fix"), Outcome.FIXATION_BREAK)],
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
                enter=[Mark(4097)],
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
                enter=[Mark(4096)],
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
                enter=[Show(Stimulus("s", at=(30.0, 0.0)))],
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
        view="stereoscope",
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(11.5, 0.0), disparity=2.0))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert GEOMETRY.can_show(11.5, 0.0), "the cyclopean position is legal"

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
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "decide",
                go=[
                    On(After(1.0), Outcome.CORRECT),
                    On(Exited("fix"), Outcome.FIXATION_BREAK),
                ],
            ),
        ],
    )

    findings = check(trial, allocation)

    assert [f.code for f in findings] == ["unallocated-outcome"]
    assert "FIXATION_BREAK" in findings[0].detail


def test_actions_on_a_transition_are_checked_too():
    """Found by writing the first real task, which the checker passed while
    emitting an unallocated code.

    Actions live in two places -- on state entry and on a transition -- and every
    check that walks actions must walk both. Reward in particular can only ever be
    a transition action, because a terminal outcome has no state to enter, so a
    checker blind to transitions is blind to exactly the actions that score.
    """
    trial = Trial(
        start="decide",
        states=[
            State(
                "decide",
                go=[On(After(1.0), Outcome.CORRECT, do=[Mark(4097)])],
            ),
        ],
    )

    findings = check(trial, replace(PROVISIONAL, task_events={4096: "STIMULUS_ON"}))

    assert [f.code for f in findings] == ["unallocated-code"]
    assert "4097" in findings[0].detail


def test_a_task_referencing_an_undeclared_window_is_refused():
    """S1a §1. A task naming `"fix"` as a gaze window while nothing says where it
    is or how large has no fixation criterion at all -- and position and size are
    exactly what an experimenter tunes, so they cannot be implicit."""
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["undeclared-window"]
    assert "target" in findings[0].detail


def test_a_position_parameter_whose_range_leaves_the_field_is_refused():
    """Stronger than checking one value. At load there is no value -- there is a
    declared range, and every value in it is one an experimenter can dial in live
    (S8 §3). So the check proves the task *cannot* place a stimulus off-screen for
    any legal setting, rather than that it happens not to today."""
    trial = Trial(
        start="show",
        params=[Param("ecc", unit="deg", low=-20.0, high=20.0)],
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(P("ecc"), 0.0)))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, geometry=GEOMETRY)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "ecc" in findings[0].detail


def test_a_position_parameter_whose_range_stays_inside_the_field_is_accepted():
    trial = Trial(
        start="show",
        params=[Param("ecc", unit="deg", low=-11.5, high=11.5)],
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(P("ecc"), 0.0)))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert check(trial, geometry=GEOMETRY) == []


# ---------------------------------------------------------------------------
# Check 8 against each setup's own field (direct-view spec §2, §4)
# ---------------------------------------------------------------------------


def _showing(at, params=(), **fields) -> Trial:
    """One state showing stimulus `s` at `at`, with any other `Stimulus` fields."""
    return Trial(
        start="show",
        params=list(params),
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=at, **fields))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )


def test_a_stimulus_under_a_light_sensors_housing_is_refused_in_direct_view():
    """Direct-view spec §4: "check 8 refuses a stimulus that could overlap a housing,
    exactly as it refuses one off the panel." The position is on the panel; the
    housing covers it."""
    findings = check(_showing((-29.0, -17.0)), geometry=DIRECT)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "direct field, less the light sensors' housings" in findings[0].detail


def test_a_range_that_can_reach_a_housing_is_refused():
    """Over the declared range, as check 8 always reasons: a target an experimenter
    can slide into the corner is refused before anyone does."""
    trial = _showing(
        (P("x"), -17.0), params=[Param("x", unit="deg", low=-29.0, high=0.0)]
    )

    assert [f.code for f in check(trial, geometry=DIRECT)] == ["stimulus-off-screen"]
    assert check(_showing((P("x"), 0.0), trial.params), geometry=DIRECT) == []


def test_direct_view_shows_what_the_stereoscopes_mask_stops():
    """The reference detection tasks' ±16°, which the interim narrowed to ±12° for the
    stereoscope. Direct view takes it; the mask refuses it, and says which field."""
    trial = _showing((P("ecc"), 0.0), params=[Param("ecc", unit="deg", low=-16.0, high=16.0)])

    assert check(trial, geometry=DIRECT) == []
    (finding,) = check(trial, geometry=GEOMETRY)
    assert finding.code == "stimulus-off-screen"
    assert "±12.0° × ±12.0° stereoscope field" in finding.detail


def test_the_mask_refuses_what_the_bare_viewport_would_show():
    """Held to the rig's field, not the optics': 12.5° is inside the viewport's ±13.15°
    and behind the mask, so an animal would never see it."""
    viewport = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
    )

    assert check(_showing((12.5, 0.0)), geometry=viewport) == []
    assert [f.code for f in check(_showing((12.5, 0.0)), geometry=GEOMETRY)] == [
        "stimulus-off-screen"
    ]


# ---------------------------------------------------------------------------
# Check 8 fails closed: every value a parameter offers, and every Update
# (XC-036 to XC-038, carried from direct view part 1's final review)
# ---------------------------------------------------------------------------


def _off(trial, geometry=GEOMETRY) -> list:
    return [f for f in check(trial, geometry=geometry) if f.code == "stimulus-off-screen"]


def test_a_whole_position_parameter_is_checked_at_every_point_it_offers():
    """XC-036: `Stimulus(at=P("pos"))` crashed check 8 with a `TypeError`, indexing a
    parameter as if it were a pair, and would have crashed `taskd`'s load the day it
    passed a geometry. A position chosen among points is checked at each of them."""
    near = [Param("pos", unit="deg", choices=((0.0, 0.0), (5.0, -5.0)))]
    far = [Param("pos", unit="deg", choices=((0.0, 0.0), (30.0, 0.0)))]

    assert _off(_showing(P("pos"), near)) == []
    (finding,) = _off(_showing(P("pos"), far))
    assert "pos" in finding.detail
    assert "30.0" in finding.detail


def test_a_whole_position_parameter_that_offers_no_points_is_refused():
    """A range, or choices that are not (x, y) points, names no place check 8 can
    test. It cannot be proved on screen, so it is refused rather than passed."""
    for param in (
        Param("pos", unit="deg", low=0.0, high=1.0),
        Param("pos", unit="deg", choices=(1.0, 2.0)),
    ):
        (finding,) = _off(_showing(P("pos"), [param]))
        assert "cannot be bounded" in finding.detail, param


def test_a_coordinate_declared_by_choices_is_checked_at_every_choice():
    """XC-038: a coordinate chosen among values was read as 0, the one place every
    field contains, so a choice of 30 degrees passed."""
    assert _off(_showing((P("x"), 0.0), [Param("x", unit="deg", choices=(0.0, 5.0))])) == []
    (finding,) = _off(_showing((P("x"), 0.0), [Param("x", unit="deg", choices=(0.0, 30.0))]))
    assert "30.0" in finding.detail


def test_a_coordinate_with_no_two_sided_range_is_refused_rather_than_read_as_zero():
    """XC-038: no range, half a range, or no declaration at all can each be dialled
    anywhere, and each was read as 0. Undeclared is also `undeclared-parameter`'s to
    report; check 8 refuses what it cannot bound either way."""
    for params in ([Param("x", unit="deg")], [Param("x", unit="deg", low=-5.0)], []):
        (finding,) = _off(_showing((P("x"), 0.0), params))
        assert "'x'" in finding.detail and "cannot be bounded" in finding.detail, params


def test_a_disparity_declared_by_choices_is_checked_at_every_choice():
    """XC-038's disparity half. 2 degrees at 11.5 puts one eye's image past the mask."""
    safe = [Param("d", unit="deg", choices=(0.0, 0.4))]
    wide = [Param("d", unit="deg", choices=(0.0, 2.0))]

    assert _off(_showing((11.5, 0.0), safe, disparity=P("d"))) == []
    assert len(_off(_showing((11.5, 0.0), wide, disparity=P("d")))) == 1


def test_an_array_radius_declared_by_choices_is_checked_at_every_choice():
    """An item ring whose radius is chosen among values reaches as far as the
    largest; read as 0, it was only ever its centre."""
    ring = [Param("r", unit="deg", choices=(4.0, 20.0))]

    assert len(_off(_showing((0.0, 0.0), ring, looks=Array(radius=P("r"))))) == 1


def test_an_appearance_parameter_is_checked_at_each_appearance_it_offers():
    """An appearance is a parameter too (S1a §4), and one of its choices may be an
    item ring. Check 8 looked only at a literal `Array`, so a ring offered as a choice
    was never measured."""
    looks = [Param("looks", unit="appearance", choices=(Disc(), Array(radius=20.0)))]
    small = [Param("looks", unit="appearance", choices=(Disc(), Array(radius=4.0)))]

    assert _off(_showing((0.0, 0.0), small, looks=P("looks"))) == []
    assert len(_off(_showing((0.0, 0.0), looks, looks=P("looks")))) == 1


def test_a_corrugation_is_checked_at_both_ends_of_its_amplitude():
    """The form was evaluated at each parameter's upper bound only, so an amplitude
    ranging over [-8, 0.1] was measured as 0.1. Its depth reaches 8."""
    lopsided = [Param("amp", unit="deg", low=-8.0, high=0.1)]
    patch = RDS(form=Corrugation(sf=0.5, amplitude=P("amp")))

    assert len(_off(_showing((11.5, 0.0), lopsided, looks=patch))) == 1


def test_a_corrugation_whose_amplitude_cannot_be_bounded_is_refused():
    """A form over a parameter the check cannot bound fell back to no depth at all."""
    chosen = [Param("amp", unit="deg", choices=(0.1, 8.0))]
    unranged = [Param("amp", unit="deg")]
    patch = RDS(form=Corrugation(sf=0.5, amplitude=P("amp")))

    assert len(_off(_showing((11.5, 0.0), chosen, looks=patch))) == 1
    (finding,) = _off(_showing((11.5, 0.0), unranged, looks=patch))
    assert "cannot be bounded" in finding.detail


def _updating(*updates, params=(), at=(0.0, 0.0)) -> Trial:
    """`s` shown at `at`, then each update in a state of its own, in order."""
    names = ["show"] + [f"update{i}" for i in range(len(updates))]
    nexts = names[1:] + [Outcome.CORRECT]
    return Trial(
        start="show",
        params=list(params),
        states=[
            State(
                name,
                enter=[Show(Stimulus("s", at=at))] if name == "show" else [updates[i - 1]],
                go=[On(After(1.0), after)],
            )
            for i, (name, after) in enumerate(zip(names, nexts))
        ],
    )


def test_an_update_that_moves_a_stimulus_off_screen_is_refused():
    """XC-037: `Update(at=...)` escaped check 8, so a stimulus shown legally could be
    moved off the panel one state later and nothing said so."""
    assert _off(_updating(Update("s", at=(5.0, 0.0)))) == []
    (finding,) = _off(_updating(Update("s", at=(30.0, 0.0))))
    assert "'update0'" in finding.detail


def test_an_update_over_a_parameter_is_checked_across_its_range():
    ranged = [Param("x", unit="deg", low=-30.0, high=0.0)]

    assert len(_off(_updating(Update("s", at=(P("x"), 0.0)), params=ranged))) == 1


def test_an_update_that_adds_disparity_is_refused_when_it_takes_one_eye_off_screen():
    """XC-037's disparity half: the same 2 degrees at 11.5 that a `Show` is refused
    for, arriving by `Update`."""
    assert len(_off(_updating(Update("s", disparity=2.0), at=(11.5, 0.0)))) == 1


def test_an_update_that_turns_a_stimulus_into_a_wide_ring_is_refused():
    assert len(_off(_updating(Update("s", looks=Array(radius=20.0))))) == 1


def test_two_updates_that_are_each_safe_are_checked_together():
    """Moving to 11.5 is legal and so is adding 2 degrees of disparity at the centre;
    after both, one eye is past the mask. An update leaves every property it does not
    set as an earlier `Show` or `Update` left it, so each is checked against those."""
    move = Update("s", at=(11.5, 0.0))
    deepen = Update("s", disparity=2.0)

    assert _off(_updating(move)) == []
    assert _off(_updating(deepen)) == []
    assert len(_off(_updating(move, deepen))) >= 1


# ---------------------------------------------------------------------------
# Which setup a task is written for (direct-view spec §3)
# ---------------------------------------------------------------------------


def _task(*enter, view="either", params=()) -> Trial:
    """One state that shows a plain disc, then does `enter`, then ends."""
    return Trial(
        start="show",
        view=view,
        params=list(params),
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(0.0, 0.0))), *enter],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )


def test_a_task_is_either_until_it_says_otherwise():
    """The default is safe because check 8 runs against whichever setup the session
    chose -- once direct view part 2 passes the session's geometry; until then only
    the tests run it -- so an undeclared task in the stereoscope is held to the
    mask."""
    assert _task().view == "either"
    assert check(_task(), geometry=DIRECT) == []
    assert check(_task(), geometry=GEOMETRY) == []


def test_disparity_needs_a_task_that_declares_the_stereoscope():
    """"Two side-by-side images on an unmirrored screen are not a stimulus." Refused
    with or without a geometry: it is the task's content, not the session's."""
    shifted = Update("s", disparity=0.4)

    (finding,) = check(_task(shifted))
    assert finding.code == "needs-stereoscope"
    assert "gives 's' disparity" in finding.detail
    assert "view='either'" in finding.detail
    assert [f.code for f in check(_task(shifted, view="direct"))] == ["needs-stereoscope"]
    assert check(_task(shifted, view="stereoscope")) == []


def test_a_disparity_parameter_counts_when_its_range_can_leave_zero():
    """Over the declared range, as every range check here: a disparity an
    experimenter can dial in is disparity."""
    ranged = [Param("d", unit="deg", low=-0.5, high=0.5)]
    pinned = [Param("d", unit="deg", low=0.0, high=0.0)]

    assert [f.code for f in check(_task(Update("s", disparity=P("d")), params=ranged))] == [
        "needs-stereoscope"
    ]
    assert check(_task(Update("s", disparity=P("d")), params=pinned)) == []


def test_a_disparity_parameter_declared_by_choices_counts():
    """Review I1(a): a disparity parameter with no `low`/`high` -- declared by
    `choices` instead -- is not the `(0, 0)` `_widest` falls back to for an
    undeclared range. `taskd` would accept any listed choice, so the checker must
    count the non-zero ones as stereo content too."""
    choices = [Param("d", unit="deg", choices=(-0.4, 0.0, 0.4))]
    pinned = [Param("d", unit="deg", choices=(0.0,))]

    assert [f.code for f in check(_task(Update("s", disparity=P("d")), params=choices))] == [
        "needs-stereoscope"
    ]
    assert check(_task(Update("s", disparity=P("d")), params=pinned)) == []


def test_a_shown_stereogram_or_one_a_parameter_can_choose_needs_the_stereoscope():
    """A random-dot stereogram has no content but its disparity. One reachable only
    through a parameter's choices is as real as one written into a `Show`."""
    shown = _task(Show(Stimulus("rds", at=(0.0, 0.0), looks=RDS())))
    chosen = _task(params=[Param("looks", unit="appearance", choices=(RDS(),))])
    updated = _task(Update("s", looks=RDS()))

    for trial in (shown, chosen, updated):
        (finding,) = check(trial)
        assert finding.code == "needs-stereoscope"
        assert "random-dot stereogram" in finding.detail


def test_a_stereogram_inside_an_arrays_looks_or_among_needs_the_stereoscope():
    """Review I1(b): `_appearances` reports the `Array` itself, not the `RDS`
    nested in its `looks`/`among` -- so an array of stereograms in an "either" task
    must still be found, whichever slot carries the `RDS`."""
    as_looks = _task(Show(Stimulus("arr", at=(0.0, 0.0), looks=Array(looks=RDS()))))
    as_among = _task(Show(Stimulus("arr", at=(0.0, 0.0), looks=Array(among=RDS()))))

    for trial in (as_looks, as_among):
        (finding,) = check(trial)
        assert finding.code == "needs-stereoscope"
        assert "random-dot stereogram" in finding.detail


def test_a_stimulus_shown_to_one_eye_needs_the_stereoscope():
    """Plan decision: an unmirrored screen shows both eyes one image, so a stimulus
    for one eye is the same impossibility as disparity -- by `Show` or by `Update`."""
    left = _task(Show(Stimulus("left", at=(2.0, 0.0), eye="left")))
    right = _task(Update("s", eye="right"))

    assert [f.detail.split(",")[0] for f in check(left)] == [
        "state 'show' shows 'left' to the left eye only"
    ]
    assert [f.code for f in check(right)] == ["needs-stereoscope"]
    assert check(_task(Update("s", eye="both"))) == []


def test_a_task_written_for_one_setup_is_refused_in_the_other_naming_both():
    """Spec §3: "a stereoscope task in direct view, or a direct task in the
    stereoscope" -- the refusal part 2's session start will show, naming both
    sides."""
    (in_direct,) = check(_task(view="stereoscope"), geometry=DIRECT)
    (in_stereoscope,) = check(_task(view="direct"), geometry=GEOMETRY)

    assert in_direct.code == in_stereoscope.code == "wrong-setup"
    assert "written for 'stereoscope'" in in_direct.detail
    assert "checked against 'direct'" in in_direct.detail
    assert "written for 'direct'" in in_stereoscope.detail
    assert "checked against 'stereoscope'" in in_stereoscope.detail
    assert check(_task(view="direct"), geometry=DIRECT) == []
    assert check(_task(view="stereoscope"), geometry=GEOMETRY) == []


def test_without_a_geometry_the_setup_is_unchecked():
    """`geometry=None` still means unchecked (S1 §9 check 8): a task is not wrong for
    being checked without a rig."""
    assert check(_task(view="stereoscope")) == []
    assert check(_task(view="direct")) == []


def test_a_view_that_is_no_setup_is_refused():
    """`view="stereo"` is not a declaration. Read as either setup it would be checked
    against the wrong one; read as neither it would pass everything."""
    (finding,) = check(_task(Update("s", disparity=0.4), view="stereo"), geometry=DIRECT)

    assert finding.code == "unknown-view"
    assert "'stereo'" in finding.detail


# ---------------------------------------------------------------------------
# Check 8 on extent, not just centre, reaching a housing (Task 3 review)
# ---------------------------------------------------------------------------


def test_an_arrays_ring_reaching_a_housing_is_refused_even_though_its_centre_is_legal():
    """Task 3 review: check 8 already refuses a stimulus whose *extent* reaches a
    housing in direct view -- not only one whose centre sits under it. An `Array`'s
    item ring makes the point without disparity, which would also trip the new
    needs-stereoscope finding in direct view."""
    centre = (-25.0, -16.0)
    assert DIRECT.can_show(*centre), "the centre alone is legal"
    assert check(_showing(centre), geometry=DIRECT) == []

    (finding,) = check(_showing(centre, looks=Array(radius=2.0)), geometry=DIRECT)

    assert finding.code == "stimulus-off-screen"
    assert "direct field, less the light sensors' housings" in finding.detail
