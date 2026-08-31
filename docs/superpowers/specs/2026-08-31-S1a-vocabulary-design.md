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

## 6. Open — the naming, which is the point

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
