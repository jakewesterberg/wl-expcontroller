# Next session — wl-expcontroller

**State at handoff:** `main` @ `b0954c6`, 70 tests passing, working tree clean, nothing
unpushed. CI runs pytest on 3.11/3.13 plus a mutation gate over every module. **Roadmap
M1 is met.** No hardware exists and none is needed for the next package.

> **Read `docs/CHECKPOINT.md` first, then this.** The checkpoint says where the build
> is; this says what to do. There are 25 design documents and **you should read three**:
> the checkpoint, `docs/M0-REVIEW.md` §3–§4, and the one S-spec named below. Reading more
> is how a session exhausts its context before producing anything, and that is the
> specific failure this file exists to prevent.

---

> **Amended 2026-08-31.** ADR-0002 is deferred to V1 — neither display stack is built
> until a rig can measure both — so P5 is hardware-blocked and P4 is *not* the last
> package needing nothing. **P4b (session management), P4c (outputs and the lab-host
> endpoint) and P4d (the console against a fake taskd) all need no hardware either.**
> P4b is the welfare-critical code and wants human review time more than anything else
> does; if you only do one thing after P4, do that.

## 1. Do P4. Then P4b, which matters more.

**Demo mode and operator documentation.** Read **S9** (`docs/superpowers/specs/
2026-08-31-S9-operations-console-design.md`) §5 and nothing else from the spec set.

P5 onward is blocked: the display needs a panel, the eye path needs `wl-preproc` to
accept a calibration reader, the I/O layer needs an NI card on a bench. **P4 is blocked
on nothing**, and it closes the argument the whole design rests on.

### Why it matters more than it sounds

ADR-0006 says a task Claude wrote is approved from a rendered diagram, a code table and
a simulation report — **without reading the source**. Two thirds of that exists:
`wlx review` renders the artifact and `wlx run` produces the report.

The missing third is a human watching the task actually behave. A diagram proves
structure and a census proves statistics; neither proves the task *does what was asked*.
Someone has to drive it for thirty seconds and see a fixation point, a target, and a
reward. Until that exists, every claim in this repository about model-authored tasks
being safe rests on two legs of a three-legged argument.

---

## 2. Steps, in order

### Step A — keyboard/mouse demo mode *(no hardware)*

A `World` implementation where the mouse is gaze and keys are responses. **It is a peer
of `Subject` and hardware, not a special mode** (S6 §6) — the loop must not be able to
tell them apart, or what a person sees in demo mode is not what an animal will get.

- Mouse position → gaze; `Entered`/`Exited`/`Hold`/`SaccadeTo` resolve against the
  declared windows, in cyclopean degrees, through `Geometry`.
- Keys → `Pressed`/`Released`/`Touched`. Mouse click stands in for touch, which is what
  makes the same mode serve the S13 kiosk.
- **It needs a window on screen.** That is the first thing in this repo that touches a
  display library, so it is where ADR-0002 stops being a decision and starts being a
  dependency. Keep it behind `DisplayAdapter` (S4 §4) even though P5 has not built one
  — a demo mode that reaches PsychoPy directly will have to be unpicked.

### Step B — the operator document *(no hardware)*

P8 was sharpened on 2026-08-31: **people arrive with or before the animals, and a tech
or student runs the rigs day to day.** So this is an M1 deliverable, not a later one.

Not a design doc. A *how to run a session* document, written for someone who has never
read a spec: what to type, what a failure means, what to do about it. If a sentence
needs the design to be understood, it is wrong.

### Step C — the acceptance test, run for real

Take a task **you did not write** — generate one, or take `adaptive_detection` cold —
and approve it from the artifact and the demo alone. Write down what you could not tell.
That list is the design's remaining debt and nothing else measures it.

---

## 3. Traps specific to P4

1. **Demo mode must not become a second runner.** If it grows its own loop, the thing a
   person validates is not the thing an animal gets, and the whole exercise proves
   nothing. It is a `World`.
2. **Mouse gaze is not eye data.** It has no staleness, never stalls, and lands exactly
   where aimed. Do not let it become the thing saccade detection is tested against — S5
   §5 says replayed OpenIrisDPI recordings, and it means it.
3. **The operator document will drift.** Everything in this repo does; that is why
   CLAUDE.md requires the checkpoint updated at session end. Put the document's own
   commands in a test if you can.

---

## 4. Do not do these, and why

- **Do not start P5, and now for a second reason.** The panel is not chosen, and
  ADR-0002 is deferred to V1: neither PsychoPy nor the thin stack is built properly
  until a photodiode on a rig can compare them. `tools/spike_display.py` is a spike and
  stays one.
- **Do not implement the wl-works or wl-preproc integrations.** Four handovers are
  outstanding and two block real work. Building against a guess costs more than waiting.
- **Do not add Parquet.** JSONL is the durable streamed record deliberately (P2); the
  columnar table is a derivation at session close and belongs with the S10 work.
- **Do not allocate event codes outside 4096–32767.** `TaskEvent` 256–4095 is still
  pending `wl-preproc`'s agreement, and allocating there means rework if they decline.

---

## 5. Waiting on people, not on code

| Who | What | Blocks |
|---|---|---|
| `wl-sync` | Session id readable by a rig host; a subject change mints `_02` | naming our own output directory |
| `wl-preproc` | A reader for our online calibration map | `CalibrationSource.ONLINE`, every session |
| `wl-preproc` | `PARAM_CHANGE` escape; ownership split; codec as an artifact | P16's guarantee |
| `wl-works` | `prepare-session`, calibration block per session, alerting | ELN autopopulation |
| PI | IPD per animal; tandem panel's two questions; the RDS decision (S1a §10) | optics, panel, stereo vocabulary |

Handovers are `HANDOVER-wl-expcontroller.md` in each repo — **committed in `wl-sync`,
written but uncommitted in the other two**, because one was on a feature branch with
work in flight and the other is owned by another worker including its remote.

---

## 6. If you have time after P4

In order: the derived Parquet table at session close (S10), then the `labhost` endpoint
(S10 §4) which can be built and contract-tested against `wl-preproc`'s published schema
without them answering anything.

**Do not skip ahead to hardware work to feel productive.** Everything on that side is
gated on measurements that cannot be taken until January, and building it now means
building it twice.
