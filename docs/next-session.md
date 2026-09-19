# Next session — wl-expcontroller

**State at handoff:** **383 tests passing**, working tree clean, **and the work is on
`p4b-session-management`, not on `main`.** Six commits, pushed. `main` still points
at `300d7d1`, so a check that looks only at `main` will report that nothing happened.
The branch exists rather than merging straight in because `bounds.py` and `welfare.py`
are welfare-critical and want a human before they merge (§1). No hardware exists.

> **Read `docs/CHECKPOINT.md` first, then this.** The checkpoint says where the build
> is; this says what to do. There are 19 specs and 8 ADRs (ADR-0008 is the newest and
> settles the console), and **you should read the
> four the checkpoint's "Read this much" names** — itself, `CLAUDE.md`,
> `docs/M0-REVIEW.md` §3–§4, and the one S-spec your package names. Reading more is how
> a session exhausts its context before producing anything, and that is the specific
> failure this file exists to prevent.

---

## 0. Check this before believing anything below

```
git branch --show-current && git log --oneline -3 && git status --short
git log --oneline origin/main..HEAD        # what has never been pushed
git log --oneline main..HEAD               # what is not on main yet
```

**Check the branch first, and it is not `main`.** P4b sits on
`p4b-session-management`; a session that checks out `main` and reads this file will find
a handoff describing work its tree does not contain.

**Trap 17, learned expensively on 2026-09-05 and paid off on 2026-09-13.** Nothing was
pushed for four days while this file and the checkpoint both described CI behaviour that
had never executed. The first push found seven bugs in five runs. **A green local suite
says nothing about CI.** P4b's first push proved it again: the full sweep ran for 1h46m
and failed on two functions the harness could not find, one of which had been reporting
itself covered on the strength of a `SyntaxError` for as long as it existed (trap 7's
seventh entry). Fixed 2026-09-19.

---

## 0b. The first thing to do

**Read the branch's own CI run before anything else** — `gh run list --branch
p4b-session-management`, then `gh run view <id> --log-failed` and *read it*, because the
last two things this gate reported were a skip dressed as a failure and a syntax error
dressed as coverage.

The push this section used to ask for happened on 2026-09-13 and the run failed; the fix
landed on 2026-09-19 and **the branch is green end to end** — run `35433303094`, read
rather than trusted: 21 modules, 215 caught, 0 survivors, 0 skips, `383 passed` at every
baseline.

`tools/mutate.py` changing escalates to a **full sweep** by rule, and a full sweep now
costs **about 1h40m** (1h46m on 2026-09-13, 1h39m on 2026-09-19, read off GitHub's own
durations). The 47–61 minute figure from 2026-09-05 is stale. And if a sweep ever comes
back *much* faster than the modules it names, that is a reason to read the output rather
than to celebrate.

CI itself is green and needs nothing from anyone — the `WL_PREPROC_TOKEN` ask this file
carried is closed, verified 2026-09-06 by reading the runs.

---

## 1. The thing that needs a person, not a session

**`bounds.py` and `welfare.py` want human review before they merge** (CLAUDE.md, S8
§7), and that review is what `p4b-session-management` is waiting on. They are the only
two welfare-critical files and they are deliberately small — 191 and 311 lines, most of
it argument — so that this is a job someone can actually do. `git diff main..HEAD --
wl_expcontroller/bounds.py wl_expcontroller/welfare.py` is the whole of it.

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
- **Read the harness's output, not its exit code** (trap 7, now seven occurrences).
  `caught deliver  3 errors in 0.60s` is a collection error, not a test failing — and it
  was reporting the welfare-critical reward path as covered. `caught recenter  2 errors
  in 0.82s` was the same lie in the nightly, every night, until 2026-09-19. With the
  fixes those two report `16 failed` and `5 failed`.
- **A tool that reasons about code asks the parser.** Three of the seven were one
  regex, and each fix created the next: a trailing comment defeated the match, then a
  same-line body matched and made a `SyntaxError`, then a nested paren ended the
  signature early. `_neuter_source` uses `ast` now. If you find yourself writing a
  pattern to find a `def`, that is the trap re-forming.
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

## 3b. ~~One cheap win~~ — taken on 2026-09-19

`mutate._function_names` returned one entry per `def` while `mutate` neuters every
definition of a name together, so a name six worlds implement ran six identical sweeps.
It now returns each name once — `run.py` 24 targets → 12, `dio.py` 14 → 6, 120 → 94
across eight modules — with a test that a repeated name is mutated once.

Done here, against the earlier judgement that it was a performance change to the tool the
evidence depends on, because the same commit had to replace that tool's locator anyway
and leaving a known waste beside a rewrite is how the next session inherits both.

---

## 3c. One decision left on the table

**`task.FixPoint` is used by nothing**, and the fixed harness is what said so
(`SURVIVED FixPoint  379 passed`). It has tests now, but the disagreement underneath
them is not repaired: S1 §5.1's worked example builds its fixation point with
`FixPoint(...)` and all three reference tasks spell out a `Stimulus` longhand instead.
Tasks here are model-authored, so the reference tasks *are* the examples a task author
copies — if the shortcut is right, they should use it; if it is not, S1a §6 should lose
it. One decision, in the task layer, deliberately not made by the session that found it.

---

## 3d. The next decision: what the kiosk's iPad actually is

**Not made 2026-09-19, deliberately.** ADR-0008 settled the console; it did not settle
whether the iPad runs the task or is a display and touch surface for a Linux host.

The argument points hard at the thin client, and it is a welfare argument rather than an
engineering preference. S13 §4: *"the welfare-critical module stays single, written once
and reviewed once — the less-supervised deployment gets no weaker path of its own."* An
iPad running the task means a second task engine and either an iOS twin of `bounds` and
`welfare` or a route around them. S13 §3 already assumes a host besides: reward is
`wl-juicer`, whose spec wires its dose input and witness line to the sync box, which the
kiosk has not got, *"so the host has to drive the one and read the other."*

The cost of the thin client, which should be accepted out loud rather than discovered:
kiosk display timing is not frame-accurate, and touch latency gains a network hop. Touch
already reaches the record only as event codes (S13 §3), so it is software-timed either
way — but the added hop wants measuring before it is relied on.

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
