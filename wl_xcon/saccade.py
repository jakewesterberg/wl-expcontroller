"""Online Engbert-Kliegl saccade detection, and the batch form it is checked against.

**The algorithm is not ours and the choice was made for one reason.** S5 §5: it is
already `wl-preproc`'s offline baseline, so online-versus-offline disagreement measures
*staleness and latency* rather than two different algorithms. Anything else would have
made the disagreement uninterpretable, which is the whole point of running the same
method twice. Read `wl_preproc/eye/detect/engbert_kliegl.py` and `.../velocity.py`
before changing anything here; the constants below are theirs.

**Two functions and one class, in that order of trust.** `velocity` and `median_scale`
are theirs, reimplemented (a task PC does not import a pipeline that pulls DataJoint)
and contract-tested against the originals. `detect` is the batch form, which must agree
with their detector interval for interval on the same trace. `Detector` is the online
form the trial loop uses, and it is checked against `detect` -- so the online path is
never compared against a second idea of the algorithm, only against the shared one.

**What online costs, stated rather than discovered later.** Their five-point estimator
is `(x[n+2] + x[n+1] - x[n-1] - x[n-2]) * fs / 6`, so the velocity *at* sample n is not
computable until sample n+2 has arrived. A run is then only a saccade once
`min_duration_samples` of it exist. Detection therefore trails true onset by at least
`2 + min_duration_samples` samples -- 16 ms at 500 Hz -- **before** any display can
react. That number is arithmetic, not a measurement: whether it lands inside saccadic
suppression is V3(b)'s to answer, photodiode to photodiode, and S5 says so explicitly
because a budget computed from component latencies is the thing that is always wrong.

**The stall rule is why this is not just their code in a loop.** A tracker gap produces
an apparent velocity that is an artifact of the gap: two samples 80 ms apart differenced
as though they were 2 ms apart is an enormous fake velocity, and it both fires the
detector and inflates the threshold that is supposed to catch it. So velocity is
computed only across five samples that are genuinely consecutive in time, and a
detection whose window touched a gap is **flagged rather than dropped or silently
reported** (S5 §5). Dropping it would hide a real saccade; reporting it unmarked would
launder an artifact into the record.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Engbert & Kliegl's own conventional values, and `wl-preproc`'s defaults. Mirrored
#: rather than imported, and asserted equal to theirs in the contract tests: a
#: threshold that differs between the online and offline detector would make their
#: disagreement a parameter difference, which is exactly what S5 chose this algorithm
#: to avoid.
DEFAULT_LAMBDA = 6.0
DEFAULT_MIN_DURATION_SAMPLES = 6

#: Samples each side of the sample being estimated; the window spans `[n-2, n+2]`.
HALF_WINDOW = 2

#: Denominator of the five-point weighted difference.
_WEIGHT_SUM = 6.0

#: Bumped whenever anything here changes what a session would detect. Written into
#: the trial record beside the mapping version, because S5 §5 makes a detector change
#: a discontinuity of the same class as a parameter change (P16) -- two sessions run
#: under different versions are not comparable and must not silently look it.
VERSION = 1


@dataclass(frozen=True, slots=True)
class Params:
    """Logged with every session. Not per-task, and not re-derivable in a task: S5 §5
    is explicit that parameters affecting results make two sessions incomparable if a
    task can set them privately."""

    lambda_: float = DEFAULT_LAMBDA
    min_duration_samples: int = DEFAULT_MIN_DURATION_SAMPLES
    #: The largest gap between consecutive samples that still counts as consecutive.
    #: Defaults to `eye.Tracker.staleness`, because the two answer the same question
    #: -- is this information still about the same stretch of time -- and two answers
    #: to it would drift.
    max_gap_s: float = 0.05
    #: How many usable velocity samples must exist before the threshold means
    #: anything. Below this the detector reports nothing rather than reporting
    #: against a scale estimated from noise -- the same refusal `Tracker.state` makes
    #: before its first sample, for the same reason.
    warmup_samples: int = 50


@dataclass(frozen=True, slots=True)
class Saccade:
    """One detected event, in sample indices into the trace that produced it."""

    start: int
    stop: int
    #: Degrees, start point to end point -- not path length.
    amplitude_deg: float
    #: True when the detection window touched a tracker gap. **Never dropped, never
    #: unmarked**: the velocity that triggered it may be an artifact of the gap
    #: rather than of the eye, and only the record can decide that afterwards.
    flagged: bool = False


def median(values: list[float]) -> float:
    """The middle value, on a copy, matching numpy's even-length averaging."""
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def median_scale(component: list[float]) -> float:
    """`sqrt(median(v²) - median(v)²)`, the paper's own scale estimate.

    **A median-based scale, not a standard deviation**, and the difference is the
    point: an SD is inflated by the very saccades the threshold exists to find, so the
    detector would grow less sensitive exactly as a session contained more of what it
    is looking for.

    **The `variance > 0` guard is not caution.** The quantity is bounded below by zero
    by an order-statistics argument, but that is about exact arithmetic; in float64 two
    near-tied middle order statistics can make the subtraction round to a small
    negative number, and `sqrt` of that is `nan` rather than an error -- silent, not
    loud. `wl-preproc` measured `-1.78e-15` on a literal four-sample array. The guard
    turns that back into the zero it should have been.
    """
    if not component:
        return 0.0
    variance = median([v * v for v in component]) - median(component) ** 2
    return math.sqrt(variance) if variance > 0 else 0.0


def velocity(
    gaze_deg: list[tuple[float, float] | None],
    at: list[float],
    params: Params,
) -> list[tuple[float, float] | None]:
    """Degrees per second per sample, or `None` where it cannot honestly be computed.

    `None` in two cases, and they are the same case: the five-sample window is not
    fully present, or it spans a gap wider than `max_gap_s`. **The edges are `None`
    rather than zero**, which is where this deliberately differs from `wl-preproc`'s
    array form -- they return zeros because an array has to have a value there, and
    their docstring says the fabricated edge is the hazard. Having the option of
    "no answer" here, we take it, and `detect` excludes those samples from the
    threshold as well as from the output.
    """
    out: list[tuple[float, float] | None] = [None] * len(gaze_deg)
    for n in range(HALF_WINDOW, len(gaze_deg) - HALF_WINDOW):
        window = range(n - HALF_WINDOW, n + HALF_WINDOW + 1)
        if any(gaze_deg[i] is None for i in window):
            continue
        if any(at[i + 1] - at[i] > params.max_gap_s for i in range(n - HALF_WINDOW, n + HALF_WINDOW)):
            continue
        span = at[n + HALF_WINDOW] - at[n - HALF_WINDOW]
        if span <= 0:
            continue
        # `fs` from the window's own span rather than a declared sampling rate: the
        # protocol is poll-based and its interval is not guaranteed (`eye.py`), so a
        # nominal rate would be an assumption where a measurement is available.
        fs = 2 * HALF_WINDOW / span
        out[n] = (
            (gaze_deg[n + 2][0] + gaze_deg[n + 1][0] - gaze_deg[n - 1][0] - gaze_deg[n - 2][0])
            * fs / _WEIGHT_SUM,
            (gaze_deg[n + 2][1] + gaze_deg[n + 1][1] - gaze_deg[n - 1][1] - gaze_deg[n - 2][1])
            * fs / _WEIGHT_SUM,
        )
    return out


def thresholds(velocities: list[tuple[float, float] | None], params: Params) -> tuple[float, float]:
    """The per-axis elliptic thresholds, from the usable velocities only.

    Unusable samples are excluded from the estimate as well as from the output, for
    the reason `wl-preproc`'s detector gives: a gap's velocity spike would otherwise
    inflate the scale and desensitise the detector for the rest of the trial.
    """
    usable = [v for v in velocities if v is not None]
    return (
        params.lambda_ * median_scale([v[0] for v in usable]),
        params.lambda_ * median_scale([v[1] for v in usable]),
    )


def _outside(v: tuple[float, float], eta_x: float, eta_y: float) -> bool:
    """The paper's elliptic test: outside the ellipse whose semi-axes are the two
    thresholds. Not a speed threshold -- the axes are scaled independently, because
    horizontal and vertical noise differ and a circular test would be set by whichever
    axis was worse."""
    return (v[0] / eta_x) ** 2 + (v[1] / eta_y) ** 2 > 1.0


def _amplitude(gaze_deg: list[tuple[float, float] | None], start: int, stop: int) -> float:
    first = next((gaze_deg[i] for i in range(start, stop) if gaze_deg[i] is not None), None)
    last = next((gaze_deg[i] for i in range(stop - 1, start - 1, -1) if gaze_deg[i] is not None), None)
    if first is None or last is None:
        return 0.0
    return math.hypot(last[0] - first[0], last[1] - first[1])


def detect(
    gaze_deg: list[tuple[float, float] | None],
    at: list[float],
    params: Params = Params(),
) -> list[Saccade]:
    """Every saccade in a trace. The batch form, and the reference `Detector` is
    checked against -- so the online path is compared with the shared algorithm rather
    than with a second idea of it."""
    velocities = velocity(gaze_deg, at, params)
    eta_x, eta_y = thresholds(velocities, params)
    if eta_x <= 0 or eta_y <= 0:
        return []

    found: list[Saccade] = []
    run_start: int | None = None
    for n, v in enumerate(velocities):
        continuous = n == 0 or (at[n] - at[n - 1]) <= params.max_gap_s
        if v is None:
            # **An unknown velocity does not end a run, as long as time is
            # continuous.** One dropped camera frame in the middle of a saccade used
            # to split the run into two pieces, each below the minimum duration, and
            # delete the event entirely -- so a single missing sample made the task
            # miss a response the animal really made. Unknown means unknown: the run
            # carries on and is flagged. A break in *time*, though, is different, and
            # ends the run: we no longer know what the eye did in between.
            if not continuous:
                if run_start is not None and n - run_start >= params.min_duration_samples:
                    found.append(_saccade(gaze_deg, velocities, run_start, n))
                run_start = None
            continue
        if _outside(v, eta_x, eta_y):
            if run_start is None:
                run_start = n
        elif run_start is not None:
            if n - run_start >= params.min_duration_samples:
                found.append(_saccade(gaze_deg, velocities, run_start, n))
            run_start = None
    if run_start is not None and len(velocities) - run_start >= params.min_duration_samples:
        found.append(_saccade(gaze_deg, velocities, run_start, len(velocities)))
    return found


def _saccade(gaze_deg, velocities, start: int, stop: int) -> Saccade:
    """Flagged when the window that produced it touched a sample with no velocity --
    the trace of a gap, by the time the run is being closed."""
    touched_gap = any(
        velocities[i] is None
        for i in range(max(0, start - HALF_WINDOW), min(len(velocities), stop + HALF_WINDOW))
    )
    return Saccade(start, stop, _amplitude(gaze_deg, start, stop), flagged=touched_gap)


@dataclass
class Detector:
    """The online form: one trial's worth of samples, fed as they arrive.

    **The threshold is per trial and adaptive** (S5 §5), which online means estimated
    from what the trial has produced so far. Before `warmup_samples` usable
    velocities exist it reports nothing at all, because a scale estimated from a
    handful of samples is a scale estimated from noise, and a detector that fires on
    it is worse than one that stays quiet.

    **Bounded work per sample.** Velocity is five plain multiplications on a
    five-element ring. The threshold is *not* recomputed per sample -- that would be a
    median over a growing list inside a trial loop, which is the unbounded per-frame
    work CLAUDE.md forbids -- but every `refresh_every` samples, over a bounded
    history. What that costs is unmeasured and stays unmeasured here: it is a number
    for a tools/ script and `docs/measurements/`, not for a docstring.
    """

    params: Params = field(default_factory=Params)
    #: How many usable velocities the threshold is estimated over, and how often it is
    #: re-estimated. Bounded so the trial loop's cost does not grow with trial length.
    history: int = 1000
    refresh_every: int = 50

    _gaze: list[tuple[float, float] | None] = field(default_factory=list, repr=False)
    _at: list[float] = field(default_factory=list, repr=False)
    _velocities: list[tuple[float, float]] = field(default_factory=list, repr=False)
    _eta: tuple[float, float] = field(default=(0.0, 0.0), repr=False)
    _since_refresh: int = field(default=0, repr=False)
    #: Absolute sample index of the open run, not an index into the buffer. The
    #: buffer is trimmed, so a stored buffer index goes stale the moment it is; that
    #: was a real bug here before the buffer was bounded, and absolute indices are
    #: what make `Saccade.start` mean the same thing as it does in `detect`.
    _run_start: int | None = field(default=None, repr=False)
    _run_had_gap: bool = field(default=False, repr=False)
    #: How many samples have been dropped off the front. Local index + this = absolute.
    _offset: int = field(default=0, repr=False)
    #: Set for the sample on which a saccade was confirmed, and cleared by the next
    #: `accept`. The trial loop asks once per frame, so an edge has to survive exactly
    #: one question, not until someone happens to ask.
    onset: Saccade | None = field(default=None, repr=False)

    def reset(self) -> None:
        """A new trial. The threshold is per trial, so carrying one across trials
        would make the first trial's noise decide the second trial's sensitivity."""
        self._gaze.clear()
        self._at.clear()
        self._velocities.clear()
        self._eta = (0.0, 0.0)
        self._since_refresh = 0
        self._run_start = None
        self._run_had_gap = False
        self._offset = 0
        self.onset = None

    @property
    def in_flight(self) -> bool:
        """Whether a supra-threshold run is currently open -- the eye is still moving
        and has not landed anywhere yet."""
        return self._run_start is not None

    @property
    def ready(self) -> bool:
        """Whether the threshold rests on enough samples to mean anything."""
        return len(self._velocities) >= self.params.warmup_samples and min(self._eta) > 0

    def accept(self, at: float, gaze_deg: tuple[float, float] | None) -> Saccade | None:
        """One sample. Returns a saccade on the sample that confirms it, else `None`.

        Confirmation, not onset: the run is reported once `min_duration_samples` of it
        exist, and `Saccade.start` is where it actually began. The lag between the two
        is the detector's, and it is arithmetic rather than measurement -- see the
        module docstring.
        """
        self.onset = None
        self._gaze.append(gaze_deg)
        self._at.append(at)

        centre = len(self._gaze) - 1 - HALF_WINDOW
        if centre < HALF_WINDOW:
            return None

        window = self._gaze[centre - HALF_WINDOW : centre + HALF_WINDOW + 1]
        times = self._at[centre - HALF_WINDOW : centre + HALF_WINDOW + 1]
        current = None
        if all(point is not None for point in window) and all(
            times[i + 1] - times[i] <= self.params.max_gap_s for i in range(len(times) - 1)
        ):
            span = times[-1] - times[0]
            if span > 0:
                fs = 2 * HALF_WINDOW / span
                current = (
                    (window[4][0] + window[3][0] - window[1][0] - window[0][0]) * fs / _WEIGHT_SUM,
                    (window[4][1] + window[3][1] - window[1][1] - window[0][1]) * fs / _WEIGHT_SUM,
                )

        if current is not None:
            self._velocities.append(current)
            if len(self._velocities) > self.history:
                del self._velocities[0]
            self._since_refresh += 1
            if self._since_refresh >= self.refresh_every or self._eta == (0.0, 0.0):
                self._eta = thresholds(list(self._velocities), self.params)
                self._since_refresh = 0

        # Trim, but never past an open run: its start is still needed to measure the
        # amplitude, and never past what the next five-sample window needs.
        keep_from = len(self._gaze) - (2 * HALF_WINDOW + 1 + self.history)
        if self._run_start is not None:
            keep_from = min(keep_from, self._run_start - self._offset)
        if keep_from > 0:
            del self._gaze[:keep_from]
            del self._at[:keep_from]
            self._offset += keep_from
            centre -= keep_from

        if not self.ready:
            self._run_start = None
            self._run_had_gap = False
            return None

        absolute = centre + self._offset
        continuous = (
            len(self._at) < 2
            or (self._at[centre] - self._at[centre - 1]) <= self.params.max_gap_s
        )
        if current is None:
            # Same rule as `detect`: unknown velocity flags an open run rather than
            # ending it; a break in time ends it. Two answers here would make the
            # online and offline detectors disagree about gaps specifically, which is
            # the one thing S5 §5 wants their disagreement to be measurable against.
            if self._run_start is not None:
                self._run_had_gap = True
                if not continuous:
                    self._run_start = None
                    self._run_had_gap = False
            return None

        if _outside(current, *self._eta):
            if self._run_start is None:
                self._run_start = absolute
            elif absolute - self._run_start + 1 == self.params.min_duration_samples:
                found = Saccade(
                    start=self._run_start,
                    stop=absolute + 1,
                    amplitude_deg=_amplitude(
                        self._gaze, self._run_start - self._offset, centre + 1
                    ),
                    flagged=self._run_had_gap,
                )
                self.onset = found
                return found
        elif self._run_start is not None:
            self._run_start = None
            self._run_had_gap = False
        return None
