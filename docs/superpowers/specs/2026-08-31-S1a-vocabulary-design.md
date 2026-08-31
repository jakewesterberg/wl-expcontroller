# S1a — The task vocabulary

- **Status:** proposed, for PI review — **naming especially**
- **Date:** 2026-08-31
- **Parent:** S1 §2, ADR-0006

The closed vocabulary a task is written in. Two audiences with the same need: a
scientist reading a task should recognise the words from how the field talks, and a
model writing one is grounded by a small vocabulary of familiar terms rather than an
open library. **Naming is therefore not cosmetic** — it is the main thing keeping
generation accurate and review fast.

Where MonkeyLogic has a word for something, we generally take it: people arrive from
ML-shaped labs, and `acquire`/`hold` already means something to them.

---

## 1. Windows are declared, not named in passing

**The gap this spec opened with.** A task refers to `"fix"` and `"target"` as gaze
windows, and nothing says where they are or how large. Position and size are exactly
the things an experimenter tunes, so they must be parameters, and a reference to an
undeclared window must be refused like an undeclared parameter (check 6).

```python
windows=[
    Window("fix",    at=(0, 0),               radius=P("fix_window")),
    Window("target", at=P("target_position"), radius=P("target_window")),
]
```

A window's `at` may itself be a parameter, which is what makes "move the array from
0° to 10° between trials" a value change rather than a new task.

---

## 2. Guards

| Term | Means | Why this word |
|---|---|---|
| `After(duration)` | elapsed since the state was entered | |
| `AfterFrames(n)` | an exact frame count | Stimulus durations that must be frame-exact rather than time-approximate |
| `Acquired(window)` | gaze entered and settled | ML's `acquirefix` / `acquiretarget` |
| `Held(window, duration)` | continuously inside for a duration | ML's `holdfix`; restarts if gaze leaves |
| `Broke(window)` | left after acquiring | "the animal broke fixation" |
| `SaccadeOnset()` | a detected saccade began | |
| `SaccadeTo(window)` | a saccade landed in a window | |
| `Pressed(device)` / `Released(device)` | lever, button | |
| `Touched(window)` | touchscreen contact inside a window | S13 |
| `JoystickIn(window)` | joystick deflected into a region | |
| `RateAbove(source, threshold)` | MUA feature over threshold | Tier-3 gating (S7) |
| `Onscreen(patch)` | **photodiode-confirmed** stimulus onset | S6 §3 — physical, not believed |
| `ChairStill()` / `ChairMoving()` | `wl-shook`'s motion gate | |

**`Onscreen` is the one worth arguing over.** It reads as a claim about the world
rather than about our intention, which is the distinction it exists to draw.

---

## 3. Actions

| Term | Means |
|---|---|
| `Show(stimulus)` / `Hide(stimulus)` | present and extinguish |
| `Mark(code)` | strobe an event code — ML calls these *event markers* |
| `Reward(bounded)` | deliver reward by bounded-config reference; never a magnitude |
| `Stimulate(bounded)` | assert the stim trigger, likewise bounded |
| `Play(sound)` | auditory stimulus or feedback |
| `AwardToken()` / `TakeToken()` | token economies (S1 §5.6) |
| `Custom(name)` | the typed seam (S1 §8) |

`Mark` replaces `Emit`: *event marker* is what the field and ML both call it, and
`Emit` says nothing about what is emitted or where it goes.

---

## 4. Stimuli

All carry `at` (cyclopean degrees), `disparity`, and `eye`.

| Term | Parameters |
|---|---|
| `FixPoint` | `size` |
| `Spot` | `size`, `contrast` — a plain disc |
| `Gabor` | `sf`, `orientation`, `phase`, `contrast`, `sigma` |
| `Grating` | `sf`, `orientation`, `phase`, `contrast`, `aperture` |
| `Dots` | `coherence`, `direction`, `speed`, `density`, `aperture` — an RDK |
| `Bar` | `length`, `width`, `orientation`, `contrast` — RF mapping |
| `Image` | `asset`, `size` |
| `Movie` | `asset`, `size` |
| `Noise` | `contrast`, `octaves`, `seed` |

Field names throughout: `sf` for spatial frequency, `coherence` for an RDK, `sigma`
for a Gabor's envelope. A model writing `spatial_frequency_cycles_per_degree` is a
model that has not seen a methods section.

### 4.1 `eye` is not an afterthought

`eye="left" | "right" | "both"` (default `"both"`). On a split-screen stereoscope,
**monocular and dichoptic presentation are first-class**: binocular rivalry, monocular
RF mapping, and interocular-suppression designs all need one eye's viewport to carry
something the other's does not.

Disparity and `eye` are different mechanisms and both are needed. Disparity shifts one
stimulus in both eyes; `eye` puts different content in each.

---

## 5. Motion

A pure function of parameters, seed and frame index — never a logged trajectory
(S4 §5).

| Term | Means |
|---|---|
| `Drift(speed)` | grating phase drifting, in cycles per second |
| `Move(velocity)` | the whole stimulus translating, in degrees per second |
| `Follow("gaze")` | anchored to current gaze — the gaze-contingent case |

---

## 6. Settled 2026-08-31

`Mark` · `Onscreen` · `Entered` / `Exited` / `Hold` · `Window` · one `Stimulus` with
`looks` · `Reward("name")` taking a bare name · `FixPoint` as a **shortcut**, not a
class.

**The shortcut rule**, since more are expected: a shortcut adds *defaults and a
name*, never a concept, and what it returns is an ordinary `Stimulus` the rest of
the system cannot distinguish. `FixPoint()` is a small disc at the origin because
every task would otherwise spell that out and "fix point" is the most-used phrase in
the field -- it earns a name without earning a type.

## 7. Outcomes

Thirteen, in two families plus a residual.

| Family | Outcomes |
|---|---|
| Response to the **target** | `CORRECT`, `EARLY_RESPONSE`, `LATE_RESPONSE` |
| Response to a **distractor** | `WRONG_TARGET`, `EARLY_ERROR`, `LATE_ERROR` |
| **Nothing** | `NO_FIXATION`, `NO_RESPONSE`, `ABORT` |
| **Breaks** — a hold not maintained | `FIXATION_BREAK`, `TARGET_BREAK`, `CATCH_BREAK`, `MOTION_BREAK` |

`ABORT` is deliberately not a break: the animal went somewhere that was neither
target nor distractor, which is a different statement from failing to hold something.

**Thirteen outcomes onto five markers.** The marker gives the class and the reason
travels as a `TaskEvent` strobed immediately before it — the rule S2 §4 already set
for `NO_FIXATION`. We did **not** ask `wl-preproc` for eight more `Marker` values:
their range is for *trial structure*, and which distractor an animal chose, and
whether it went early, is task meaning. Pushing it into their range would be
convenient for one analysis and wrong about who owns what.

## 8. Multiple responses in one trial — settled 2026-08-31

**Trials emit scored events; the terminal outcome summarises.** A `Score(window,
outcome)` action records a response as it happens, and the trial still ends once.

- **Several correct targets**: *which* was chosen is a scored event, which is the
  thing the experiment is about and was previously not expressible anywhere.
- **Free viewing**: a trial with many scored responses and a mundane ending. The
  census counts responses as well as outcomes, because a free-viewing task ends the
  same way every trial and an outcome-only report would say nothing about it.

**The classification reuses `Outcome`.** The same taxonomy applies at both grains --
a single choice can be early, late, to a distractor or correct exactly as a whole
trial can -- and a second vocabulary would need keeping in step with this one for no
gain.

The two cases this answers, recorded because they are what forced it:

1. **Several correct targets.** A trial where any of N choices scores. The outcome is
   still one value, but *which* target was chosen is not currently expressible
   anywhere, and it is the thing the experiment is about.
2. **Free viewing with multiple responses.** An animal moving between windows,
   producing a sequence of responses rather than one, with **intermediary outcomes
   throughout the trial**.

The second is the harder one, and it questions an assumption the whole model rests
on: that a trial has exactly one outcome, at the end. S1 already made unbounded
epochs first-class, but not multi-response scoring.

This needs its own design pass, not an extension bolted onto `Outcome`.

## 9. Appearances

Fifteen, and the set is deliberately shape-agnostic where it can be: `Polygon(sides=3)`
rather than a `Triangle` class, for the same reason `Stimulus` carries a look rather
than being subclassed per shape.

| Family | Appearances |
|---|---|
| Shapes | `Disc`, `Square`, `Polygon`, `Annulus`, `Cross`, `Bar` |
| Patterns | `Gabor`, `Grating`, `Plaid`, `Checkerboard`, `Noise` |
| Motion | `Dots` |
| Assets | `Picture`, `Movie` |
| Nothing | `Blank` |

`Gabor` and `Grating` are separate because the envelope differs — Gaussian against a
hard aperture — and that changes edge artifacts and spatial-frequency bandwidth,
which is why the field names them separately rather than parameterising one.

`Blank` is not the absence of a `Show`. A catch trial shows nothing *at the moment a
stimulus would have appeared*, and making that explicit keeps catch and non-catch
trials structurally identical, which is what makes them comparable.

## 10. Settled 2026-08-31 — disparity-defined form

**The gap that matters for a stereo lab, and it is not in the list above.**

`Stimulus.disparity` shifts a whole stimulus in depth. That is not what a random-dot
stereogram does: an RDS defines a **shape by disparity within the dot pattern**, so
the figure is invisible monocularly and exists only in the correspondence between the
two eyes' images. Cyclopean form, in the Julesz sense.

The two are different mechanisms and the vocabulary currently has only the first.
Adding it means either an `RDS` appearance carrying its own figure and disparity, or
a general way for an appearance to be *defined* by disparity rather than merely
displaced by it — which would also cover disparity-defined edges and surfaces.

**Settled: both, split by what they describe.** `RDS` is an appearance carrying
`correlation` — +1 correlated, 0 uncorrelated, **-1 anticorrelated** — because
anticorrelation is not a shape at all and cannot be expressed as a displacement, and
it is the control every disparity paper is asked for. Separately, `Form` is a
disparity *field* across a patch (`Corrugation`, `Slant`), because a patch carrying
one has no single disparity to be displaced by. A `Slant`'s extreme depends on how
wide the patch is, so its range is answered against the aperture rather than quoted
alone.

Check 8 adds a form's extremes to the stimulus's own disparity: a patch centred
safely can still push one eye's image off the panel at the extreme of its
corrugation, and only that eye's. A stereogram declared for one eye is refused —
monocular presentation of one half is a field of random dots with no disparity, and
it would still run, still record, and still appear in a figure as a disparity
condition.

## 11. Still open — the naming, which is the point

Everything above is a proposal and the words are the deliverable. Places I am least
confident:

1. **`Mark` vs `Emit` vs `Strobe`** for an event code.
2. **`Broke(window)`** — reads oddly out of context, but "broke fixation" is what
   people say.
3. **`Onscreen(patch)`** for photodiode confirmation. Alternatives: `Displayed`,
   `Confirmed`, `PhotodiodeOn`.
4. **`Spot` vs `Blob` vs `Disc`** for a plain circular target.
5. **`Held` vs `Holding`** — the guard fires at the *end* of the hold, so past tense
   is right, but `Held("fix", 300ms)` can read as a duration already elapsed.
6. Whether windows should be `Window` or `Region` — the latter also covers touch
   targets, which are not gaze windows at all.


## 12. Added 2026-08-31 after review — what the graph could not see

Two independent reviews found the same shape of problem: **every gate inspected the
transition graph**, so the residual defect class was "correct graph, wrong
experiment". Five additions, each closing a paradigm that was unwritable or a defect
that was uncatchable.

**The display is state.** `Show` persists until `Hide` or the end of the trial rather
than being scoped to its state — the original wording removed a fixation point at the
exact frame the animal was asked to hold it, in a task that read correctly and passed
all ten checks. Stimuli carry **names**; `Hide` and `Update` address them. `Update`
changes a live stimulus without the offset transient `Hide`+`Show` inserts, which is
the confound change detection exists to avoid. A `Window` names the stimulus it
scores, or `REMEMBERED` when the location is deliberately blank; unset is refused,
because otherwise the check is opt-in and the tasks likeliest to skip it are the ones
written fastest.

**Colour, device-independently.** `xyY` names a light absolutely; `DKL` is a
modulation from the background along the cardinal cone-opponent axes, where `lum=0`
is isoluminant by construction. Colour sits on the **appearance**, not the stimulus,
so "red among green" and "circles among squares" are the same kind of switch and both
are values a parameter can carry. Colour without a measured `Calibration` is refused,
and a calibration that does not name whose luminous efficiency it used cannot carry an
isoluminance claim — a macaque V(lambda) is not a human one.

**Set size as a value.** `Array` is an appearance, so an N-item search array is one
named stimulus and the rest of the system needs to know nothing about arrays.
`ItemWindows` is one declaration that becomes n windows plus the aliases
`<of>.target` and `<of>.distractor`. The distractor alias is the point: enumerating
error saccades per item is the same structure-versus-value problem one level down,
and it would make the measurement search tasks exist to produce unavailable.
`target-outside-array` reasons over declared **ranges**, because set size and target
index are both live.

**Per-eye criteria.** `Window.eye` is honoured by the loop, which previously parsed
and dropped it. The tracker is binocular, and on a stereoscope a per-eye criterion is
the correct primitive: under dichoptic presentation the non-viewing eye drifts, so a
conjugate estimate averages one eye doing the task with one eye doing nothing. A
window scoring the eye its stimulus is not shown to is refused.

**The simulated animal sees the screen.** `World.display` is called every frame with
what a real display would carry, and a subject will not acquire a window whose
coupled stimulus is absent. Without it the subject responded to the transition graph
alone, so every defect in this section simulated perfectly.
