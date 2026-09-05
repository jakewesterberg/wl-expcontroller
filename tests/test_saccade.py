"""Saccade detection: ours against theirs, and online against batch.

Three layers, and the ordering is the argument. `velocity` and `median_scale` are
`wl-preproc`'s, so they are checked against the originals. `detect` must agree with
their detector interval for interval, because S5 §5 chose this algorithm *specifically*
so that online-versus-offline disagreement measures staleness and latency rather than
two different methods -- a claim that is worth nothing unless the two really are the
same method. `Detector` is then checked against `detect`, never against a fresh
expectation, so the online path is only ever compared with the shared algorithm.
"""

from __future__ import annotations

import math
import os
import random

import pytest

from wl_expcontroller.saccade import (
    DEFAULT_LAMBDA,
    DEFAULT_MIN_DURATION_SAMPLES,
    VERSION,
    Detector,
    Params,
    detect,
    median_scale,
    thresholds,
    velocity,
)

FS = 500.0
DT = 1.0 / FS


def _trace(saccades, n=600, noise=0.02, seed=3):
    """A fixation trace with saccades stepped into it.

    `saccades` is `(onset_sample, duration_samples, dx_deg, dy_deg)`. Position moves
    linearly across the saccade, which is what makes velocity supra-threshold there
    and nowhere else.
    """
    rng = random.Random(seed)
    x, y = 0.0, 0.0
    gaze, at = [], []
    steps = {}
    for onset, duration, dx, dy in saccades:
        for k in range(duration):
            steps[onset + k] = (dx / duration, dy / duration)
    for i in range(n):
        step = steps.get(i, (0.0, 0.0))
        x += step[0]
        y += step[1]
        gaze.append((x + rng.gauss(0, noise), y + rng.gauss(0, noise)))
        at.append(i * DT)
    return gaze, at


# ---------------------------------------------------------------------------
# Ours, on its own terms
# ---------------------------------------------------------------------------


def test_a_clean_saccade_is_found_at_about_the_right_place():
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    found = detect(gaze, at)
    assert len(found) == 1
    assert abs(found[0].start - 200) <= 4
    assert found[0].amplitude_deg == pytest.approx(8.0, abs=0.5)
    assert not found[0].flagged


def test_pure_fixation_produces_nothing():
    """The threshold is estimated from the trace's own noise, so a trace that is all
    noise must not find events in it -- otherwise every fixation trial reports
    saccades and the guard is worthless."""
    gaze, at = _trace([])
    assert detect(gaze, at) == []


def test_two_saccades_are_two_events():
    gaze, at = _trace([(150, 10, 6.0, 0.0), (400, 10, -6.0, 2.0)], n=700)
    found = detect(gaze, at)
    assert len(found) == 2
    assert found[0].start < found[1].start


def test_a_run_shorter_than_the_minimum_duration_is_not_a_saccade():
    """Engbert-Kliegl's minimum duration is what separates a saccade from a noise
    excursion above threshold, and dropping it would make the detector fire on the
    tail of its own distribution."""
    brief = Params(min_duration_samples=40)
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    assert detect(gaze, at, brief) == []


def test_median_scale_is_not_a_standard_deviation():
    """The property the whole threshold rests on: adding large excursions must not
    inflate the scale much, or the detector desensitises exactly as a session
    accumulates the events it is looking for."""
    quiet = [0.1, -0.1, 0.2, -0.2] * 25
    with_saccades = quiet + [400.0, -380.0, 420.0] * 5

    quiet_scale = median_scale(quiet)
    loud_scale = median_scale(with_saccades)
    assert loud_scale < quiet_scale * 2.0

    ordinary_sd = _sd(with_saccades)
    assert ordinary_sd > quiet_scale * 20


def _sd(values):
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def test_a_near_tie_cannot_produce_nan():
    """`median(v²) - median(v)²` is non-negative in exact arithmetic and can round
    negative in float64; `sqrt` of that is `nan`, silently. wl-preproc measured
    -1.78e-15 on a four-sample array."""
    assert median_scale([1.0, 1.0, 1.0, 1.0]) == 0.0
    assert not math.isnan(median_scale([0.1, 0.1, 0.1000000000000001, 0.1]))


# ---------------------------------------------------------------------------
# The stall rule (S5 §5)
# ---------------------------------------------------------------------------


def test_velocity_is_not_computed_across_a_gap():
    """Two samples 80 ms apart differenced as though 2 ms apart is an enormous fake
    velocity -- it fires the detector AND inflates the threshold meant to catch it."""
    gaze, at = _trace([])
    at = [t + (0.2 if i >= 300 else 0.0) for i, t in enumerate(at)]  # an 80 ms hole
    velocities = velocity(gaze, at, Params())
    assert all(v is None for v in velocities[298:301]), "the window spanning the hole"
    assert velocities[290] is not None and velocities[310] is not None


def test_a_missing_sample_produces_no_velocity():
    gaze, at = _trace([])
    gaze[300] = None
    velocities = velocity(gaze, at, Params())
    assert all(v is None for v in velocities[298:303])


def test_a_saccade_whose_window_touched_a_gap_is_flagged_not_dropped():
    """S5 §5, exactly: flagged, not silently reported, and not dropped either.
    Dropping hides a real saccade; reporting it unmarked launders an artifact."""
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    gaze[203] = None
    found = detect(gaze, at)
    assert found, "a dropped sample must not delete the saccade"
    assert any(s.flagged for s in found)


def test_the_gap_ceiling_matches_the_trackers_staleness_by_default():
    """Two answers to 'is this still about the same stretch of time' would drift."""
    from wl_expcontroller.eye import Tracker

    assert Params().max_gap_s == Tracker.staleness


# ---------------------------------------------------------------------------
# Online against batch
# ---------------------------------------------------------------------------


def _online(gaze, at, params=Params()):
    detector = Detector(params=params)
    return [s for t, g in zip(at, gaze) if (s := detector.accept(t, g)) is not None]


def test_the_online_detector_finds_what_the_batch_form_finds():
    """Not compared against a fresh expectation: the online path is checked against
    the shared algorithm, so a change to the algorithm cannot be silently satisfied
    by adjusting a number here."""
    gaze, at = _trace([(200, 10, 8.0, 0.0), (450, 12, -7.0, 3.0)], n=700)
    batch = detect(gaze, at)
    online = _online(gaze, at)

    assert len(online) == len(batch)
    for got, want in zip(online, batch):
        assert abs(got.start - want.start) <= 2


def test_the_online_detector_reports_on_the_sample_that_confirms():
    """Confirmation is not onset. A run becomes a saccade once
    `min_duration_samples` of it exist, and `start` is where it actually began -- so
    the record keeps the onset while the trial loop learns of it later."""
    gaze, at = _trace([(200, 12, 8.0, 0.0)])
    detector = Detector()
    confirmed_at = None
    for i, (t, g) in enumerate(zip(at, gaze)):
        if detector.accept(t, g) is not None:
            confirmed_at = i
            break
    assert confirmed_at is not None
    saccade = detector.onset
    assert confirmed_at > saccade.start, "confirmation must trail onset"
    assert confirmed_at - saccade.start >= DEFAULT_MIN_DURATION_SAMPLES


def test_nothing_fires_before_the_threshold_has_enough_samples():
    """A scale estimated from a handful of samples is a scale estimated from noise.
    The same refusal `Tracker.state` makes before its first sample."""
    gaze, at = _trace([(10, 10, 8.0, 0.0)])
    detector = Detector(params=Params(warmup_samples=200))
    assert _online_with(detector, gaze[:150], at[:150]) == []
    assert not detector.ready


def _online_with(detector, gaze, at):
    return [s for t, g in zip(at, gaze) if (s := detector.accept(t, g)) is not None]


def test_reset_forgets_the_previous_trials_threshold():
    """The threshold is per trial (S5 §5). Carried across, a quiet first trial would
    decide a noisy second trial's sensitivity."""
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    detector = Detector()
    _online_with(detector, gaze, at)
    assert detector.ready

    detector.reset()
    assert not detector.ready
    assert detector.onset is None


def test_the_onset_edge_survives_exactly_one_question():
    """The trial loop asks once per frame. An edge that persisted would fire the
    guard on every subsequent frame; one that vanished before being asked would be
    missed entirely."""
    gaze, at = _trace([(200, 12, 8.0, 0.0)])
    detector = Detector()
    for t, g in zip(at, gaze):
        if detector.accept(t, g) is not None:
            break
    assert detector.onset is not None
    detector.accept(at[-1] + DT, gaze[-1])
    assert detector.onset is None


def test_the_buffer_stays_bounded_over_a_long_trial():
    """Hot-path discipline: no unbounded work or memory per frame. A trial loop that
    grew a list for its whole duration would allocate through the trial it must not
    allocate in."""
    detector = Detector(history=100)
    gaze, at = _trace([], n=3000)
    _online_with(detector, gaze, at)
    assert len(detector._gaze) <= 2 * 2 + 1 + 100 + 1


def test_indices_stay_absolute_once_the_buffer_has_been_trimmed():
    """The buffer is trimmed, so a stored buffer index goes stale the moment it is.
    A saccade late in a long trial must still report where it actually began."""
    detector = Detector(history=60)
    gaze, at = _trace([(900, 12, 9.0, 0.0)], n=1100)
    found = _online_with(detector, gaze, at)
    assert found, "a saccade after many trims is still a saccade"
    assert abs(found[0].start - 900) <= 6, f"start drifted to {found[0].start}"


# ---------------------------------------------------------------------------
# Contract: wl-preproc's own detector
# ---------------------------------------------------------------------------

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"

try:
    import numpy as np

    from wl_preproc.eye.detect import engbert_kliegl as theirs
    from wl_preproc.eye.detect import velocity as their_velocity
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). S5 §5 "
            f"chose this algorithm because it is theirs; if our reimplementation "
            f"drifts from it, online-versus-offline disagreement stops measuring "
            f"latency and starts measuring the drift"
        ) from exc
    theirs = None

_contract = pytest.mark.skipif(theirs is None, reason="wl-preproc checkout not beside this repo")


@_contract
def test_our_defaults_are_their_defaults():
    assert DEFAULT_LAMBDA == theirs.DEFAULT_LAMBDA
    assert DEFAULT_MIN_DURATION_SAMPLES == theirs.DEFAULT_MIN_DURATION_SAMPLES


@_contract
def test_our_median_scale_is_theirs():
    rng = np.random.default_rng(11)
    for values in (
        np.array([1.0, 1.0, 1.0, 1.0]),
        np.array([0.1, -0.1, 0.2, -0.2]),
        rng.normal(0, 3, 200),
        rng.normal(0, 0.01, 51),
        np.array([]),
    ):
        assert median_scale(list(values)) == pytest.approx(
            theirs._median_scale(values), abs=1e-12
        )


@_contract
def test_our_velocity_is_their_velocity_on_an_evenly_sampled_trace():
    """Ours derives `fs` from the window's own timestamps because the protocol is
    poll-based; on an evenly sampled trace that must reduce to their fixed-rate
    estimator exactly, or the two detectors are differentiating differently and
    every comparison between them is partly about smoothing."""
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    mine = velocity(gaze, at, Params())
    theirs_v = their_velocity.velocity(np.array(gaze), FS)
    for n in range(2, len(gaze) - 2):
        assert mine[n][0] == pytest.approx(theirs_v[n][0], rel=1e-9)
        assert mine[n][1] == pytest.approx(theirs_v[n][1], rel=1e-9)


@_contract
def test_our_detector_finds_the_intervals_theirs_finds():
    """The claim S5 §5 rests on. Their detector labels by amplitude and ours does not
    -- labelling is offline analysis, not something a task guard needs -- so the
    contract is over the intervals, which is the detection itself."""
    gaze, at = _trace([(150, 10, 6.0, 0.0), (400, 12, -7.0, 3.0)], n=700)
    mine = detect(gaze, at)

    array = np.array(gaze)
    their_v = their_velocity.velocity(array, FS)
    available = [None] * len(gaze)
    their_runs = theirs.detect_engbert_kliegl(
        array, their_v, available, theirs.DEFAULT_EK_PARAMS
    )

    assert [(s.start, s.stop) for s in mine] == [(r.start, r.stop) for r in their_runs]


def test_in_flight_tracks_the_open_run_not_the_confirmation():
    """`gaze.Tracked` uses this to decide when the eye has landed, so it has to mean
    'a supra-threshold run is open', not 'a saccade was recently confirmed'. A
    saccade is confirmed part-way through its own flight, and asking the wrong
    question would let `SaccadeTo` report a landing while the eye was still moving."""
    gaze, at = _trace([(200, 20, 9.0, 0.0)], n=500)
    detector = Detector()

    during, after = [], []
    for i, (t, g) in enumerate(zip(at, gaze)):
        detector.accept(t, g)
        if 210 <= i <= 218:
            during.append(detector.in_flight)
        if 260 <= i <= 280:
            after.append(detector.in_flight)

    assert any(during), "in_flight must be true while the eye is moving"
    assert not any(after), "in_flight must be false once the eye has landed"


def test_in_flight_is_false_on_a_still_eye():
    gaze, at = _trace([], n=400)
    detector = Detector()
    for t, g in zip(at, gaze):
        detector.accept(t, g)
    assert not detector.in_flight
