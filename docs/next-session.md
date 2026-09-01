# Next session — wl-expcontroller

**State at handoff:** `main`, **194 tests passing**, working tree clean. CI runs pytest
on 3.11/3.12/3.13 plus a mutation gate over every module, and now checks out
`wl-preproc` so the event-codec round-trip actually runs. No hardware exists.

> **Read `docs/CHECKPOINT.md` first, then this.** The checkpoint says where the build
> is; this says what to do. There are 25 design documents and **you should read three**:
> the checkpoint, `docs/M0-REVIEW.md` §3–§4, and the one S-spec named below. Reading
> more is how a session exhausts its context before producing anything, and that is the
> specific failure this file exists to prevent.

---

## 0. The thing that changed the plan

Two reviews on 2026-08-31 found that **every load-time check inspected the same
object** — the transition graph — so the residual defect class was tasks whose graph is
right and whose *experiment* is wrong. Five vocabulary gaps and two framework bugs came
out of that, all closed on 2026-09-01. Read **trap 9** and **pitfall P18** before adding
another check; the useful question is what a gate is *looking at*, not how many gates
there are.

The same review killed a load-bearing assumption. **"January validates rather than
discovers" is false.** It justified building the task layer instead of the four things
that must work on day one: **DIO out, gaze in, a frame on screen, reward out.** Two of
those four now exist (`dio.py`, `eye.py`) and are proven without hardware. The other two
are genuinely blocked. Until a rig runs all four end to end, January discovers.

---

## 1. Do eye calibration. It needs no hardware and it is on the day-one path.

The fixation-grid map from raw DPI signal to degrees, per animal, with drift
correction. **Ours to build** — OpenIris's own calibration plugins target its display,
not our task display. Read **S5** (`docs/superpowers/specs/2026-08-31-S5-eye-tracking-design.md`)
and nothing else from the spec set.

`eye.py` already gives you samples in camera pixels with `dpi()` as the gaze signal
(P1 − P4). Calibration is the missing step between that and a `Window` test.

**Two things already established, which will cost you a day each if rediscovered:**

- **A ring of calibration targets is degenerate** on the second-order basis. Points on
  a circle make `constant`, `dx²` and `dy²` linearly dependent, so the fit is singular.
  Use a grid, or a ring plus centre, and **assert the conditioning** in a test.
- **The model is already fixed** by `wl-preproc` — read their source, not their README.
  We supply the map; the functional form is not ours to choose. See ADR-0007 and the
  cross-repo table below.

**Exit condition:** replayed OpenIrisDPI samples map to degrees, the fit refuses a
degenerate target set with a named finding rather than a singular matrix, and a
calibration map serialises in a form `wl-preproc` can read.

---

## 2. Then saccade detection, and then the World adapter

- **Saccade detection** is the versioned Engbert–Kliegl component (S5 §5), never
  re-derived per task. It is what `SaccadeTo` and `SaccadeOnset` ride on, and both
  currently reach the world as bare `happened()` calls that nothing implements.
- **The World adapter** is the join: `eye.Tracker` + calibration + `dio.Card` behind
  the `World` protocol in `run.py`, so a trial loop can run against real ingest. That
  turns four modules into one working path, and it is the last piece before the display.

---

## 3. Traps specific to this work

- **`Tracker.state` before the first sample returns `"lost"`, never `"ok"`.** A tracker
  reporting (0, 0) at startup puts gaze exactly on the fixation point and scores a hold
  against an empty chair. Keep it that way.
- **What OpenIris emits when one eye's tracking fails is UNVERIFIED.** It is recorded as
  such in `eye.py`. Do not invent a validity rule — it decides whether an animal is
  looking. It is a bench measurement (V3).
- **Do not re-derive the staleness policy per world.** It lives in `Tracker` and the
  trial loop, once, for the same reason `Entered`/`Exited`/`Hold` do.
- **Never `git add` after a mutation run that did not print `restored:`.** Trap 12: a
  run hung, an outer timeout killed the harness past its `finally`, and left a neutered
  `scheduler.py` on disk. The sentinel healed it; the tool now has its own timeout.

---

## 4. Do not do these, and why

- **Do not start the display (P5).** The panel is not chosen and ADR-0002 is deferred to
  V1: neither PsychoPy nor the thin stack is built properly until a photodiode on a rig
  can compare them. `tools/spike_display.py` is a spike and stays one.
- **Do not write a `nidaqmx` implementation you cannot run.** `dio.py`'s interface is
  the deliverable; the real card is a day's work once one exists, and guessing at
  DAQmx semantics now means rewriting it then.
- **Do not implement the wl-works or wl-preproc integrations.** Four handovers are
  outstanding and two block real work.
- **Do not add Parquet.** JSONL is the durable streamed record deliberately (P2); the
  columnar table is a derivation at session close, with the S10 work.
- **Do not allocate event codes outside 4096–32767.** `TaskEvent` 256–4095 is still
  pending `wl-preproc`'s agreement.
- **Do not add a fourteenth load-time check before reading P18.** More gates over the
  same object is what produced the problem the reviews found.

---

## 5. Waiting on people, not on code

| Who | What | Blocks |
|---|---|---|
| `wl-sync` | Session id readable by a rig host; a subject change mints `_02` | naming our own output directory |
| `wl-preproc` | A reader for our online calibration map | **§1 of this document** |
| `wl-preproc` | `PARAM_CHANGE` escape; ownership split; codec as an artifact | P16's guarantee |
| `wl-works` | `prepare-session`, calibration block per session, alerting | ELN autopopulation |
| PI | **A photometer measurement of the panel** | every chromatic task (P19) |
| PI | IPD per animal; the tandem panel's two questions | optics, panel |

Handovers are `HANDOVER-wl-expcontroller.md` in each repo — **committed in `wl-sync`,
written but uncommitted in the other two**, because one was on a feature branch with
work in flight and the other is owned by another worker including its remote.

**Settled since the last version of this file:** the RDS decision (S1a §10 — both, split
by what they describe) and binocular eye tracking (already in the architecture: 500 Hz
binocular dDPI; the gap was that the *vocabulary* could not use it, now closed by
`Window.eye`).

---

## 6. The blocking measurement

**No display calibration exists, and chromatic tasks will not load without one.** That
is intended — the alternative is a task that runs, looks convincing, and reports a
colour nobody measured, which reaches a methods section. What is needed is a
spectroradiometer or colorimeter on the actual panel: primaries and background in CIE
xyY, gamma, reachable cone contrast, and **whose luminous efficiency** the luminances
were measured against — a macaque V(λ), not a human one, or `lum=0` is isoluminant for
nobody in the room. Result goes under `docs/measurements/`.

`tasks/visual_search.py` is the task waiting on it.

---

## 7. If you have time after the eye work

In order: the derived Parquet table at session close (S10), then the `labhost` endpoint
(S10 §4), which can be built and contract-tested against `wl-preproc`'s published schema
without them answering anything. Then P4d, the console shell against a fake `taskd`.

**Do not skip ahead to hardware work to feel productive.** Everything on that side is
blocked on a card, a panel, or a photometer, and none of the three is ours to hurry.
