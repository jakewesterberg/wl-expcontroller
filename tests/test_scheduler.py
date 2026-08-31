"""The trial scheduler: which condition next, when a block ends, what is owed.

S8 §1-2. Between-trial code, outside the frame budget -- so it may hold state and do
arbitrary arithmetic, and an error here is observable and recoverable rather than a
dropped frame.
"""

from __future__ import annotations

from wl_expcontroller.scheduler import (
    Block,
    Condition,
    Constrained,
    Counting,
    Scheduler,
    WithReplacement,
)
from wl_expcontroller.task import Outcome


def _block(**kwargs) -> Block:
    return Block(
        name="main",
        conditions=[
            Condition("near", values={"eccentricity": 5.0}, target=10),
            Condition("far", values={"eccentricity": 15.0}, target=10),
        ],
        **kwargs,
    )


def test_counters_distinguish_attempted_completed_and_correct():
    """Collapsing them makes a balanced design unverifiable: an animal that aborts
    only the hard condition looks, on an attempted count, like it ran both."""
    # One condition, so the shuffle cannot decide which one is being counted.
    scheduler = Scheduler(
        [Block(name="main", conditions=[Condition("near", {}, target=10)])], seed=1
    )

    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)

    counts = scheduler.counts("near")
    assert (counts.attempted, counts.completed, counts.correct) == (2, 1, 1)


def test_owed_is_target_minus_completed_not_minus_attempted():
    """The question at a rig is never how many have run but how many more are
    needed, and an aborted trial produced no datum."""
    scheduler = Scheduler([_block()], seed=1)

    for _ in range(3):
        trial = scheduler.next_trial()
        scheduler.record(trial.name, Outcome.FIXATION_BREAK)

    assert scheduler.owed("near") == 10
    assert scheduler.owed("far") == 10


def test_a_fixation_break_is_requeued_at_the_end_of_the_block():
    """The default ruled 2026-08-31. A broken fixation is a failure to engage and
    the condition still owes a datum; end of block rather than immediately, so an
    animal cannot make an easy condition repeat by breaking on the hard one."""
    scheduler = Scheduler([_block()], seed=1)

    first = scheduler.next_trial()
    scheduler.record(first.name, Outcome.FIXATION_BREAK)

    assert first.name in scheduler.requeued
    assert scheduler.upcoming()[-1] == first.name


def test_a_wrong_choice_is_not_requeued():
    """A wrong choice *is* the datum."""
    scheduler = Scheduler([_block()], seed=1)

    first = scheduler.next_trial()
    scheduler.record(first.name, Outcome.WRONG_TARGET)

    assert scheduler.requeued == []


def test_a_block_with_a_fixed_length_ends_when_every_condition_is_owed_nothing():
    scheduler = Scheduler([_block()], seed=1)

    while not scheduler.finished:
        trial = scheduler.next_trial()
        scheduler.record(trial.name, Outcome.CORRECT)

    assert scheduler.counts("near").completed == 10
    assert scheduler.counts("far").completed == 10


def test_a_criterion_block_ends_on_performance_not_on_a_count():
    """"80% over the last 20 completed" -- and it consumes the same running
    statistics the console plots use, computed once."""
    scheduler = Scheduler(
        [_block(criterion=(0.8, 20))], seed=1
    )

    for _ in range(20):
        trial = scheduler.next_trial()
        scheduler.record(trial.name, Outcome.CORRECT)

    assert scheduler.finished, "20 correct in a row meets 80% over 20"


def test_aborted_trials_do_not_count_toward_a_criterion_window():
    """An abort says nothing about performance. Letting one into the window makes
    the criterion track engagement rather than what the animal can do -- the same
    reasoning that keeps aborts out of the staircase."""
    scheduler = Scheduler([_block(criterion=(0.8, 4))], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.NO_FIXATION, Outcome.NO_FIXATION):
        trial = scheduler.next_trial()
        scheduler.record(trial.name, outcome)

    assert not scheduler.finished, "one completed trial is not a window of four"


# --- what counts, declared per block -------------------------------------------

def test_a_block_can_count_only_correct_trials():
    """"Run until 10 correct" -- the animal owes the condition a correct trial and
    an error leaves the debt standing."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=3)],
        counts_toward=Counting.CORRECT_ONLY,
    )
    scheduler = Scheduler([block], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.owed("near") == 1, "the error did not pay the debt"


def test_a_block_can_count_every_presentation_regardless_of_accuracy():
    """"Show the array 100 times" -- accuracy is the measurement, not the quota, so
    a wrong answer and a no-response both count."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=3)],
        counts_toward=Counting.PRESENTED,
    )
    scheduler = Scheduler([block], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.NO_RESPONSE):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.owed("near") == 0


def test_a_trial_that_never_reached_the_stimulus_is_not_a_presentation():
    """The distinction PRESENTED exists to draw: the animal never fixated, so the
    array was never shown, so nothing was presented to count."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=3)],
        counts_toward=Counting.PRESENTED,
    )
    scheduler = Scheduler([block], seed=1)

    scheduler.record(scheduler.next_trial().name, Outcome.NO_FIXATION)

    assert scheduler.owed("near") == 3


def test_the_criterion_window_can_use_a_different_rule_from_the_counter():
    """They are different questions. A block may count every presentation toward
    its quota while judging performance only on completed choices."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=100)],
        counts_toward=Counting.PRESENTED,
        criterion=(0.8, 2),
        criterion_over=Counting.CORRECT_ONLY | {Outcome.WRONG_TARGET},
    )
    scheduler = Scheduler([block], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.NO_RESPONSE, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.finished, "two correct choices; the no-response was not judged"


# --- order, declared per block --------------------------------------------------

def test_constrained_order_refuses_a_run_longer_than_declared():
    """What most search and attention designs actually use, because an animal
    exploits runs -- three of the same target position in a row and it stops
    searching and starts predicting."""
    block = Block(
        name="main",
        conditions=[Condition("a", {}, target=40), Condition("b", {}, target=40)],
        order=Constrained(max_run=2),
    )
    scheduler = Scheduler([block], seed=3)

    drawn = [scheduler.next_trial().name for _ in range(60)]

    runs = []
    for name in drawn:
        if runs and runs[-1][0] == name:
            runs[-1][1] += 1
        else:
            runs.append([name, 1])
    assert max(length for _, length in runs) <= 2


def test_with_replacement_respects_weights():
    """For conditions you want rarely: catch trials, probes."""
    block = Block(
        name="main",
        conditions=[Condition("common", {}, target=900), Condition("rare", {}, target=100)],
        order=WithReplacement(weights={"common": 9.0, "rare": 1.0}),
    )
    scheduler = Scheduler([block], seed=5)

    drawn = [scheduler.next_trial().name for _ in range(2000)]

    assert 0.05 < drawn.count("rare") / len(drawn) < 0.15
