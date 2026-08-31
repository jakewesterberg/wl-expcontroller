"""The trial loop: the framework executing a task's declarative data.

This is the loop S1 §5.1 keeps out of task files. A task declares states and
guarded transitions; this runs them, frame by frame, and asks a `World` whether
each non-temporal guard is satisfied. On a rig the world is hardware; in a
simulated session it is a behaviour agent; in demo mode it is a mouse and keyboard.
**They are peers** (S6 §6) -- the loop cannot tell them apart, which is what makes
a simulated session evidence about the real one.

`After` is the one guard the loop evaluates itself, from elapsed frames, because
time is the loop's own property rather than something the world reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, NamedTuple, Protocol

from wl_expcontroller.task import (
    Action,
    After,
    Entered,
    Exited,
    Guard,
    Hide,
    Hold,
    Outcome,
    P,
    Score,
    Show,
    Stimulus,
    Trial,
    Update,
    expand_windows,
)


class World(Protocol):
    """Whatever supplies the signals a guard asks about.

    **Two primitives, and the split is what makes worlds interchangeable.** A world
    reports where gaze is (`in_window`) and whether a discrete event occurred
    (`happened`). It does *not* decide what entering, leaving or holding mean --
    the loop derives those from membership, so those semantics, including the
    staleness policy S5 §4.1 requires, exist exactly once.

    If each world implemented them, the simulator and a mouse would disagree about
    what a hold is, and a person validating a task in demo mode would be validating
    different behaviour from the one the animal gets.
    """

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        """Is gaze inside `window`, for the eye the window declares?

        `eye` is `"both"` for an ordinary conjugate criterion, or `"left"`/`"right"`
        when a window scores one eye. The tracker is binocular, so this is a real
        primitive; and on a stereoscope it is the *correct* one, because under
        dichoptic presentation the non-viewing eye drifts and a conjugate estimate
        averages one eye doing the task with one eye doing nothing.
        """

    def happened(self, guard: Guard, state: str, frame: int) -> bool: ...

    def display(self, visible: Mapping[str, Stimulus], frame: int) -> None:
        """What is on the screen this frame.

        Called every frame, before the frame's guards are evaluated, with the
        stimuli a real display would be showing at that moment. On a rig this is
        what draws; in a simulated session it is what the subject can respond to.

        **Without it the display was not modelled anywhere**, so every check
        inspected the transition graph and none could see that a task was holding
        fixation on a point it had taken down.
        """


@dataclass(frozen=True, slots=True)
class Quiet:
    """A world where nothing ever happens.

    Useful on its own: it proves a trial terminates on its time bounds alone,
    which is the property S1 §9 check 4 exists to make true.
    """

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        return False

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        return False

    def display(self, visible: Mapping[str, Stimulus], frame: int) -> None:
        return None


@dataclass(frozen=True, slots=True)
class Scripted:
    """A world where named guards fire on given frames.

    Deterministic, so a test can assert a frame count rather than a distribution.
    Frames are counted from the start of the trial, not of the state, because a
    script describes what the animal did and the animal does not know about states.
    """

    at_frame: dict[Guard, int]
    #: Which window gaze occupies on each frame. Membership rather than events,
    #: because entering, leaving and holding are the loop's to derive.
    inside: dict[int, str] = field(default_factory=dict)

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        return self.inside.get(frame) == window

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        return self.at_frame.get(guard) == frame

    def display(self, visible: Mapping[str, Stimulus], frame: int) -> None:
        return None


class Shown(NamedTuple):
    """One stimulus's time on the display.

    `on` is the first frame it was visible and `off` the first frame it was not,
    so a duration is a subtraction and a presentation still up when the trial ended
    has `off is None`. Half-open because the alternative -- last-visible-frame --
    makes every duration an off-by-one waiting to be reported as a result.
    """

    name: str
    on: int
    off: int | None


class Changed(NamedTuple):
    """An `Update` taking effect: which stimulus, and the first frame it differed."""

    name: str
    frame: int


@dataclass(frozen=True, slots=True)
class Scored:
    """One scored response inside a trial: what, where, and when."""

    window: str
    scored_as: Outcome
    frame: int


@dataclass(frozen=True, slots=True)
class Result:
    outcome: Outcome | None
    frames: int
    #: Every state this trial entered, in order. A census over many trials turns
    #: this into starvation detection: a state no trial ever entered is either
    #: unreachable in practice or gated on behaviour the animal never produces,
    #: and the static checks cannot tell the difference.
    visited: tuple[str, ...] = ()
    #: Scored responses in the order they happened. Empty for a task that scores
    #: only at the end, which is most of them.
    scored: tuple[Scored, ...] = ()
    #: What was on the display and when. This is the realized timeline, not the
    #: declared one: comparing the two is how a task whose stimulus was up for a
    #: different duration than its author wrote gets caught.
    shown: tuple[Shown, ...] = ()
    #: Every `Update` that took effect, in order.
    changed: tuple[Changed, ...] = ()


def _resolve(value: float | P, values: dict[str, float]) -> float:
    """A parameter reference against this trial's bound values.

    **Missing is an error, never a default.** A timeout that silently became 0.0
    would abort every trial immediately -- and that reads as an animal who will not
    work, not as a bug, which is the most expensive way for this to fail.
    """
    if isinstance(value, P):
        if value.name not in values:
            raise KeyError(
                f"no value bound for parameter {value.name!r}; a trial runs against "
                f"a resolved parameter set, not a partially resolved one"
            )
        return values[value.name]
    return value


def _apply(
    actions: "list[Action]",
    visible: "dict[str, Stimulus]",
    shown: "list[Shown]",
    open_at: "dict[str, int]",
    changed: "list[Changed]",
    frame: int,
) -> None:
    """Execute the display actions among `actions`, effective from `frame`.

    **A display action decided while processing frame N takes effect on frame N+1.**
    The loop chooses during a frame what the *next* flip will carry; recording it as
    though it were already visible would build the one-frame lie into every realized
    duration this system reports, and reporting durations honestly is most of why it
    exists.

    Non-display actions are not this function's business: `Score` is the loop's, and
    `Mark` and `Reward` belong to the I/O layer, which has no simulator yet.
    """
    for action in actions:
        if isinstance(action, Show):
            name = action.stimulus.name
            if name in visible:
                raise ValueError(
                    f"stimulus {name!r} is already on the display; two live "
                    f"stimuli under one name would make Hide and Update ambiguous"
                )
            visible[name] = action.stimulus
            open_at[name] = len(shown)
            shown.append(Shown(name, frame, None))
        elif isinstance(action, Hide):
            if action.stimulus not in visible:
                raise ValueError(
                    f"stimulus {action.stimulus!r} is not on the display, so it "
                    f"cannot be hidden"
                )
            del visible[action.stimulus]
            index = open_at.pop(action.stimulus)
            shown[index] = shown[index]._replace(off=frame)
        elif isinstance(action, Update):
            if action.stimulus not in visible:
                raise ValueError(
                    f"stimulus {action.stimulus!r} is not on the display, so it "
                    f"cannot be updated"
                )
            visible[action.stimulus] = replace(
                visible[action.stimulus], **action.changes()
            )
            changed.append(Changed(action.stimulus, frame))


def run_trial(
    trial: Trial,
    world: World,
    frame_period: float,
    max_frames: int = 100_000,
    values: dict[str, float] | None = None,
) -> Result:
    """Run one trial to its outcome.

    `max_frames` is a backstop, not a policy: a well-formed task cannot hang,
    because check 3 proves every state reaches an outcome and check 4 proves every
    wait is bounded. It exists so a task that skipped the checker fails a test
    rather than a session.
    """
    by_name = {state.name: state for state in trial.states}
    current = by_name[trial.start]
    entered_at = 0
    visited = [current.name]
    scored: list[Scored] = []
    #: Window membership on the previous frame, so entering and leaving are edges
    #: rather than states, and the frame a hold began, so leaving restarts it.
    tracked = {
        guard.window
        for state in trial.states
        for edge in state.go
        if isinstance(edge.guard, (Entered, Exited, Hold))
        for guard in (edge.guard,)
    }
    # An array's windows do not exist until `n` is bound, so aliases -- `<of>.target`
    # and `<of>.distractor` -- are resolved here against this trial's values. A
    # saccade guard reaches the world directly and worked by accident; membership is
    # derived by the loop, so an unresolved alias is simply never satisfied and the
    # animal fixates the target while the task waits forever.
    declared, aliases = expand_windows(trial, values or {})
    # Which eye each window scores. A window that declares one and is asked about
    # the conjugate estimate is a criterion nobody applied.
    eyes = {window.name: window.eye for window in declared}
    asked = {
        name: aliases.get(name, (name,))
        for name in tracked
    }
    tracked = {concrete for names in asked.values() for concrete in names}
    was_inside: dict[str, bool] = dict.fromkeys(asked, False)
    holding_since: dict[str, int] = {}

    # The display. The start state's entry actions run before the loop, so what
    # they put up is visible on frame 1 -- the same one-frame rule every other
    # entry action follows, counted from a notional frame 0.
    visible: dict[str, Stimulus] = {}
    shown: list[Shown] = []
    open_at: dict[str, int] = {}
    changed: list[Changed] = []
    _apply(current.enter, visible, shown, open_at, changed, 1)

    for frame in range(1, max_frames + 1):
        world.display(visible, frame)
        elapsed = (frame - entered_at) * frame_period
        bound = values or {}

        # Membership first, once per frame: entering and leaving are edges against
        # the previous frame, and a hold that lapses restarts rather than pausing.
        membership = {
            name: world.in_window(name, frame, eyes.get(name, "both"))
            for name in tracked
        }
        inside_now = {
            name: any(membership[concrete] for concrete in concretes)
            for name, concretes in asked.items()
        }
        for name, inside in inside_now.items():
            if inside:
                holding_since.setdefault(name, frame)
            else:
                holding_since.pop(name, None)

        for edge in current.go:
            guard = edge.guard
            if isinstance(guard, After):
                fired = elapsed >= _resolve(guard.seconds, bound)
            elif isinstance(guard, Entered):
                fired = inside_now[guard.window] and not was_inside[guard.window]
            elif isinstance(guard, Exited):
                fired = was_inside[guard.window] and not inside_now[guard.window]
            elif isinstance(guard, Hold):
                # The entry frame counts: gaze inside on frames 2, 3 and 4 is
                # 30 ms of hold at a 10 ms frame, completing on frame 4. Counting
                # from the frame *after* entry would make every hold one frame
                # longer than declared, which at 240 Hz is invisible and at 60 Hz
                # is 17 ms of unasked-for fixation.
                since = holding_since.get(guard.window)
                fired = since is not None and (
                    (frame - since + 1) * frame_period >= _resolve(guard.seconds, bound)
                )
            else:
                fired = world.happened(guard, current.name, frame)
            if not fired:
                continue
            scored.extend(
                Scored(action.window, action.scored_as, frame)
                for action in edge.do
                if isinstance(action, Score)
            )
            if isinstance(edge.to, Outcome):
                _apply(edge.do, visible, shown, open_at, changed, frame + 1)
                return Result(
                    edge.to,
                    frame,
                    tuple(visited),
                    tuple(scored),
                    tuple(shown),
                    tuple(changed),
                )
            current, entered_at = by_name[edge.to], frame
            _apply(edge.do, visible, shown, open_at, changed, frame + 1)
            _apply(current.enter, visible, shown, open_at, changed, frame + 1)
            # **Entering a state clears every hold.** A hold declared in a state
            # means held continuously *since that state began*. Carrying the window's
            # own entry frame across a transition let a later state's hold be
            # satisfied by presence that began before it -- a memory-guided structure
            # with a declared 0.3 s delay ran that delay for **one frame** and scored
            # CORRECT, with the task written correctly and every load-time check
            # passing. Found by review 2026-08-31; every working-memory delay in the
            # v1 inventory is written this way.
            holding_since.clear()
            visited.append(current.name)
            break
        was_inside = inside_now
    return Result(
        None, max_frames, tuple(visited), tuple(scored), tuple(shown), tuple(changed)
    )
