# Next session — wl-expcontroller

**State at handoff:** **375 tests passing**, working tree clean. No hardware
exists.

> **Read `docs/CHECKPOINT.md` first, then this.** The checkpoint says where the build
> is; this says what to do. There are 19 specs and 8 ADRs, and **you should read three
> documents**:
> the checkpoint, `docs/M0-REVIEW.md` §3–§4, and the S-spec your package names.
> Reading more is how a session exhausts its context before producing anything, and
> that is the specific failure this file exists to prevent.

---

## 0. Check this before believing anything below

```
git log --oneline -1 && git status --short && git log --oneline origin/main..main
```

**Trap 17, learned expensively on 2026-09-05.** Nothing was pushed for four days while
this file and the checkpoint both described CI behaviour that had never executed. The
first push found seven bugs in five runs. **A green local suite says nothing about
CI**, and unpushed commits are how every one of those hid.

---

## 1. The thing that needs a person, not a session

**`bounds.py` and `welfare.py` want human review before they merge** (CLAUDE.md, S8
§7). They are the only two welfare-critical files and they are deliberately small —
191 and 311 lines, most of it argument — so that this is a job someone can actually do.

What a reviewer has to check, stated so the ask is concrete:

**Read the fluid model first.** It was inverted on 2026-09-06 by the PI: *"there is
never a ceiling for fluid reward. only a floor (which can be supplemented after the
training/rec session to reach)."* Everything below follows from that, and the version
before it was thoroughly tested and thoroughly wrong. See trap 22.

- **Nothing refuses a delivery on volume.** `Welfare.deliver` has no fluid check at
  all, by design. If you find one, it is a regression.
- **`bounds.Floor` and `bounds.Ceiling` are different types on purpose**, and the daily
  fluid figure lives in `Bounds.minima`. Same type for both is how a minimum came to be
  compared with `>`.
- **`welfare.Welfare.deliver` is the only path from a task to fluid.** Grep for
  `pump.deliver` and for `Rig.reward`; if a second route exists, the day's accounting
  is optional.
- **The charge happens before the valve opens**, so a pump that raises after opening
  does not leave fluid unaccounted — the day's total is what a person supplements
  against.
- **`already_today=None` still pays the animal** and makes `shortfall()` answer `None`.
  It is a refusal to *claim* the day went well, not a refusal to deliver.
- **A pump fault is not absorbed.** A solenoid that will not answer is a broken rig.
- **`chair_time` runs from head-fixation**, and a session refuses to start without it.
  That and `max_trials` are the two real ceilings.
- **The numbers in `tasks/reference_bounds.py` are placeholders and its subject is
  `REFERENCE`.** No protocol figure exists in this repository for reward volume, daily
  fluid floor, restraint time or trial count — the PI has said to keep it that way
  until there are animals. A session refuses a bounded config belonging to another
  subject, which is what stops that file quietly becoming a real one.

---

## 2. P4c — the derived Parquet table, then `labhost`

**Exit condition:** the columnar table is written at session close and contract-tested
against `wl-preproc`'s published schema. Read **S10**.

JSONL is the durable streamed record deliberately — a Parquet file is only valid once
closed, so it cannot be the crash-safe one. The table is a *derivation* at close, where
a crash costs a conversion rather than a session. `trials.jsonl` now carries the block
and condition per row as well as the resolved parameters, so the derivation has what it
needs.

Then the `labhost` endpoint (S10 §4), which can be contract-tested against their
published schema **without them answering anything** — which is what makes it the right
next thing while four cross-repo asks are outstanding.

---

## 3. Traps specific to what P4b just left behind

- **A "not yet" comment is a claim nothing can check** (trap 20, pitfall P21). Two
  guardrails sat unwired behind one for a week. If you write one, name what it is
  waiting for so the next reader can grep it.
- **The session clock is derived from frames, not the wall.** That is what keeps "stops
  at its chair-time ceiling" deterministic. `Session(clock=...)` takes a real one for a
  rig. Do not quietly swap the default.
- **A block test that can run past its criterion runs to `max_trials`.** Under mutation
  that is a 300-second timeout per function. `tests/test_taskd.py` caps it at 400 for
  exactly this reason, and the M1 gate raises its own to 1,000 because its claim needs
  them.
- **A limit whose direction is load-bearing must say so in its name** (trap 22).
  `minima` beside `ceilings`; `shortfall` rather than `check_delivery`.
- **Never `git add` after a mutation run that did not print `restored:`** (trap 12).
  Running the suite while one is in flight reports failures against a neutered module —
  which happened twice this session and read exactly like a real regression both times.
  Editing a *test* file mid-run is the same hazard from the other side: the suite the
  harness is measuring changes underneath it.
- **Read the harness's output, not its exit code** (trap 7, sixth occurrence). `caught
  deliver  3 errors in 0.60s` is a collection error, not a test failing — and it was
  reporting the welfare-critical reward path as covered. With the fix the same function
  reports `16 failed`.
- **A contract test that may skip is not a contract test.** The new calibration-file
  test uses `test_calibration.py`'s guard, not `pytest.importorskip`: a missing
  `wl-preproc` skips locally and **fails** under `WLX_REQUIRE_PREPROC=1`, which is what
  CI sets. `importorskip` would have skipped silently in CI — the exact hole
  `tests/conftest.py` exists to close.
- **A new module must be declared in `tools/mutation_gate.py`**, in `RETURNS` or in
  `EXEMPT` with a reason. The gate fails otherwise, on purpose (trap 18).
- **`PARAM_CHANGED` (4130) is not the `PARAM_CHANGE` escape.** It carries no sequence
  number, so two changes in one interval are told apart by order alone. The escape is
  still the ask on `wl-preproc`.

---

## 3b. One cheap win, if you want a warm-up

`mutate._function_names` returns **one entry per `def`**, and `mutate` neuters *every*
definition of a name together — so a name implemented by six worlds is mutated six times
with identical inputs and identical results. `run.py`'s sweep prints `in_window`,
`happened`, `signal`, `mark` and `reward` three or four times each, and every repeat is a
full suite run. De-duplicating the target list changes no result and roughly halves the
sweep for the modules with protocol implementations, against a full sweep that already
costs 47–61 minutes and grows with every module.

Not done here because it is a performance change to the tool the evidence depends on, and
this session had already changed that tool once for a correctness reason (trap 7's sixth
entry). Worth a test that a repeated name is mutated once.

---

## 4. Do not do these, and why

- **Do not write the pump driver.** `welfare.Pump` takes millilitres; the conversion to
  solenoid open time is a per-rig calibration nobody has measured (protocol **V10**), and
  `wl-sync`'s board passes our commanded line through untouched so the pulse width is
  genuinely ours to choose. Guessing at it is inventing a dose. Same rule as `nidaqmx`.
- **Do not start the display (P5).** ADR-0002 is deferred to V1; neither stack is built
  properly until a photodiode on a rig can compare them.
- **Do not allocate event codes outside 4096–32767.** `TaskEvent` 256–4095 still needs
  `wl-preproc`'s agreement on ADR-0007.
- **Do not add a load-time check before reading P18 and trap 9.** More gates over the
  same object is what produced the defect class the reviews found.

---

## 5. Waiting on people, not on code

| Who | What | Blocks |
|---|---|---|
| `wl-sync` | Session id readable by a rig host; a subject change mints `_02` | naming our own output directory |
| `wl-preproc` | `PARAM_CHANGE` escape; ownership split; codec as an artifact | P16's guarantee |
| `wl-works` | `prepare-session`, **including the day's already-delivered fluid total** | the day's shortfall is computed from it; without it a session pays the animal but can report no supplement |
| PI | **A photometer measurement of the panel** | every chromatic task (P19); `tasks/visual_search.py` is what waits |
| PI | **A pump calibration: millilitres per second of open time** — protocol **V10**, `docs/validation.md` | real reward delivery (new 2026-09-06) |
| PI | **The real bounded-config numbers** — reward volume per delivery, the daily fluid **floor**, chair time, trial cap. Asked 2026-09-06; answer was *keep the placeholder until there are animals* | every session that is not a simulation |
| PI | **Is a runaway-fluid *fault* limit wanted?** Not a ration — a sanity bound catching a software fault delivering litres, reported as a fault. Nothing enforces one today, which is correct under the protocol and leaves a bug unbounded | welfare review; S8 open item 6 |
| PI | IPD per animal; the tandem panel's two questions | optics, panel |

---

## 6. After P4c

P4d, the console shell against a fake `taskd`. `Session.set` is already the validated
write path it will hold — staged, applied atomically in the ITI, recorded with its
origin — and `Session(world=...)` is already the seam a rig plugs into. What is missing
is the link between a console process and a session, and the preflight S9 describes.

**Do not skip ahead to hardware work to feel productive.** Everything on that side is
blocked on a card, a panel, a photometer or a pump measurement, and none of the four is
ours to hurry.
