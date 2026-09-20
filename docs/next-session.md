# Next session — wl-expcontroller

**State at handoff:** **610 tests passing** (with `.[dev,contract,console]` installed —
nine of them need the transport, and until 2026-09-19 CI did not install it), working
tree clean, **and the work has
moved past `p4b-session-management` to `p4d1-console-link`, not on `main`.** The
console link this file used to list as missing (§6, old text) now exists, built on
`p4b-session-management`'s tip (`8693299`) — run `git log --oneline
p4b-session-management..p4d1-console-link` for the branch's own commits rather than
trusting a count written here. **That is not a hedge, it is the whole rule**: a
commit count of a branch, stated in a file tracked on that branch, is wrong the
instant it is committed, every time, because writing it is itself one more commit
than it counted — this exact number was wrong three different ways across three
fix rounds before it was removed rather than corrected a fourth time.
`p4d1-console-link` is **committed locally only — not pushed, and not merged**
(`git ls-remote origin p4d1-console-link` finds nothing). `p4b-session-management`
itself is 11 commits ahead of `main` (ten of them pushed; the eleventh, `8693299`,
is local only) — that count is safe to state here, unlike `p4d1-console-link`'s
own, because nothing committed to *this* branch can change *another* branch's
history. `main` still points at `300d7d1` and knows about neither branch, so a
check that looks only at `main` will report that nothing happened. Both branches
exist rather than merging straight in because `bounds.py` and `welfare.py` are
welfare-critical and want a human before they merge (§1) — `p4d1-console-link`
adds a second, narrower ask to the same review rather than a new one (§1, bottom).
The push and the merge decision are the PI's. No hardware exists.

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
two welfare-critical files and they are deliberately small — **285 and 528 lines, of
which 99 and 249 are executable**; the rest is argument. `git diff main..HEAD --
wl_expcontroller/bounds.py wl_expcontroller/welfare.py` is the whole of it.

> **`welfare.py` grew across the welfare-clock rulings and three review rounds**, from
> 311 lines to a peak of 630, and was then cut back to **528 lines / 249 executable**.
> The cut moved the dated PI-ruling narratives into S8 §5.2 and §5.2c — which already
> carry the rulings — leaving one sentence per guard and a pointer. **Every refusal
> message is verbatim**; those are what an operator reads, and they are most of why the
> executable count is what it is (a `raise` wraps over four or five lines).
>
> It did not reach the ~350 lines the review asked for, and the gap is reported rather
> than closed by gutting: at ~180 docstring lines there is roughly one sentence per
> guard left, and cutting further removes the "why" from a welfare-critical file.
> `bounds.py` got the same treatment in the last round — 327 → 285 lines, 99
> executable — which nobody had been tracking.
>
> **The useful question is whether each *refusal* is earned, and S8 §5.2d makes that a
> lookup**: all twenty-three across both files, the message's first clause verbatim
> and greppable, each against the failure it was written for. A test keeps the table
> and the code in step in both directions, so it cannot rot into decoration.

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
  Since 2026-09-19 `taskd`'s loop boundary publishes one telemetry frame naming the
  fault before the exception propagates; it does not catch it.
- **One ceiling ends a session: `out_of_cage`**, from the animal leaving its home cage
  to going back in, bounded at twelve hours (PI, 2026-09-19). A rig session refuses to
  start without the mark, and **`welfare.out_of_cage_seconds` raises rather than
  answering zero** on an unmarked one — forgetting a mark must not be what disables the
  limit. A cage-side session declares `Deployment.CAGE_SIDE` and has no duration
  bound; that declaration is required on `SessionSpec` with no default.
- **Three deployment kinds, and "absent" is not "zero"** (PI, 2026-09-20). `RIG_FIXED`
  takes both marks; `RIG_CHAIRED` takes the out-of-cage mark only and is bounded by the
  same clock; `CAGE_SIDE` takes neither. **A chaired-but-unfixed animal is restrained**,
  so `chair_seconds` answers `None` rather than `0.00` for the two kinds with no
  head-fixation marks, `welfare.head_fixed` refuses them, `taskd` strobes 4128/4129 only
  for `RIG_FIXED`, and the console says which absence it is looking at. A restrained
  session reporting zero restraint is `shortfall()` answering `0` for an unmeasured day,
  in another costume — if you add a welfare quantity, ask what it reports where nothing
  measured it.
- **The interval is opened once, closed once, and never runs backwards.** The rule above
  is only half of it: two marks in the *wrong order* disable the limit while the session
  reports itself fully marked. A return before the departure gave a negative duration
  (under every ceiling), a return marked mid-session froze the clock, and a return
  re-armed `left_cage`. All refused now — including a return while the animal is recorded
  head-fixed, which is what puts the whole trial loop inside the refusal. **If you add a
  mark, ask what its mis-ordering does**, not only what its absence does.
- **Out and back is one session — the PI's ruling of 2026-09-20, not our reading.** An
  animal returned to its cage briefly and brought out again starts a **new** session;
  `left_cage` refuses to re-arm a closed interval. He accepted the consequence: an animal
  returned mid-day gives **two session directories and two records**, not one with an
  unexplained gap. Do not "fix" this into a resume without asking him — it was asked once
  precisely because it looked like an inference, and the answer is on the record in S8
  §5.2 item 4.
- **A reward volume of zero is allowed, and the console showing it is the condition
  of that** (PI, 2026-09-20). Zeroing reward pauses payment without ending a session;
  he allowed it because `fluid session: 0.00 mL` and the unchanged `supplement` figure
  make it visible, accepting that an animal working correctly is paid nothing while it
  holds. **So `Telemetry.fluid_session_ml` and `shortfall_ml` are welfare-load-bearing:
  dropping either from a pane is a welfare regression, not a display change.** It is
  also the one place a magnitude of zero is deliberately allowed.
- **The rule, in two words: an instant is finite; a magnitude is finite and not
  negative.** Three Criticals in three review rounds were one class — a guard on a
  *limit* with the *measurement* compared against it unchecked — found one surface at a
  time. `--delivered-today nan` reported an animal on 10.90 mL against a 20 mL floor as
  `supplement: 0.00 mL`; `--set reward_correct=-0.5` commanded twenty negative doses to
  the pump. **`tests/test_welfare.py` now enumerates every numeric door and fails if one
  is in neither its guarded list nor an exempt list with a reason** — add a float-taking
  method to either welfare-critical file and the suite refuses until you do one or the
  other. Do not fix the next one of these where you find it; check the enumeration.
- **NaN is `False` against every ordered comparison, so it switches a limit off rather
  than exceeding it.** This got further than anything else on the branch: `wlx run
  --out-of-cage-ago nan` ran 400 rewarded trials with a clean summary and no duration
  limit, and a NaN ceiling in a bounded config did the same. (That flag is
  `--out-of-cage-at TIME` since 2026-09-20 and can no longer carry a NaN; the guards
  stand for every other caller, and the enumeration is what proves it.) `bounds._finite` guards
  `Ceiling`, `Floor`, `validate`, the mark, the measurements and the computed
  duration. **`inf` is just as bad and was *not* already refused** — an earlier note
  here said it was, and that was measured false: `seconds > inf` is `False` for every
  real duration, so an `inf` ceiling is never exceeded either. Only the mark route
  refused it. **If you write a guard as `<` or `>`, ask what `nan`, `inf` and a
  negative value each do to it.**
- **`left_cage` takes a clock time and maps it itself** (PI, 2026-09-20: *"a clock time
  is what an operator reads"*). It takes the departure and the wall clock as wall-clock
  instants and the session clock beside them, and does the subtraction inside
  `welfare.py` — **one place where the two bases meet**, because the caller that had that
  job passed a plain `0.0` and made out-of-cage time equal chair time. `wlx
  run --out-of-cage-at` is required with no default for the same reason `--as WHO` is.
  The cost, which the PI weighed: a 1.7e9 *instant* is just now, so the ceiling no longer
  doubles as a wall-clock catch, and `08:45` for `18:45` is nine hours inside a
  twelve-hour limit. What replaces it: a refusal for a departure in the future, the
  ceiling refusal unchanged, and **the computed interval printed at session start** —
  *"the animal has been out N hours M minutes"*. A bare time is **today** on this host,
  in **this host's local zone**, and is never rolled back to yesterday.
- **The session warns before the limit, and the threshold is not settled** (PI,
  2026-09-20 asked for the warning). `welfare.approaching_limit` at
  `WARN_WITHIN_DEFAULT` = 1,800 s, configurable by `--warn-within`. **That number is this
  session's proposal and is waiting on the PI** — it is not derived from any measurement
  of this system, because no block duration has been measured. If he names a figure, it
  goes in that constant and nowhere else.
- **`chair_time` and `max_trials` are gone as ceilings.** Chair time is still recorded
  (`head_fixed`/`head_released`, codes 4128/4129, required by a `RIG_FIXED` preflight and
  refused by the other two kinds since 2026-09-20) and bounds nothing; there is no
  session-length maximum at all. If you find either name
  used as a limit, it is a regression.
- **The numbers in `tasks/reference_bounds.py` are placeholders and its subject is
  `REFERENCE`.** No protocol figure exists in this repository for reward volume, the
  daily fluid floor or time out of the cage — the PI has said to keep it that way
  until there are animals. A session refuses a bounded config belonging to another
  subject, which is what stops that file quietly becoming a real one. **One number in
  it is no longer a placeholder-for-a-protocol-figure**: `reward_correct`'s maximum,
  10 mL, is a runaway-fluid fault bound (PI, 2026-09-19) — it is not waiting on a
  protocol, because no protocol states it. The value beside it still is.

**This review gained a second, smaller item on 2026-09-19.** `p4d1-console-link` (built
on top of this branch) gives `wlx console --set reward_correct=...` as the first
*person-invocable* path that moves a reward limit — `Session.set` validating against
the ceiling and staging, with `_apply_staged` assigning at the next trial boundary. `cli.py` and `link.py` do not become
welfare-critical by `architecture.md`'s definition — the limit is still enforced in
`bounds.py` alone, and the welfare-critical surface stays exactly two files — but the
*capability* is new and welfare-facing, and CLAUDE.md is explicit that anything
touching reward delivery amounts or limits is reviewed by a human lab member before
merge. It merges into the same lineage this section already asks a person to read, so
it goes to the same reviewer rather than opening a second thread. `git diff
p4b-session-management..p4d1-console-link -- wl_expcontroller/cli.py
wl_expcontroller/link.py wl_expcontroller/taskd.py` was the whole of it at the review
(ruling R23, `.superpowers/sdd/2026-09-19-p4d1-console-link/progress.md`). **The PI's
four decisions since then added `wl_expcontroller/bounds.py`,
`wl_expcontroller/record.py` and `tasks/reference_bounds.py` to that diff**, and **the
four welfare-clock rulings later the same day added `wl_expcontroller/welfare.py`** —
which had been at zero diff for the whole branch until then. **So this is now a review of
both welfare-critical files.** `welfare.py`'s diff is the one to read closest: it removes
a concept (`max_trials`), changes which clock bounds a session, and adds the declaration
that decides whether a duration limit applies at all. `docs/CHECKPOINT.md`'s "The welfare
clock, and the four rulings that reshaped it" is the account to read beside it.

**And that reviewer has four PI decisions to check, not only code to read** — taken on
2026-09-19 after the whole-branch review, and implemented on this branch:

> 1. **A welfare-bounded change now defers, like an ordinary parameter.** `Session.set`
>    used to call `bounds.set` synchronously as the command was drained, so a new reward
>    volume was live for the trial that ran later in that same pass while every console
>    displayed it as `staged`, and its `PARAM_CHANGED` strobe and `parameter_changes.jsonl`
>    row landed a pass later still — **fluid attribution off by one trial**. Validation and
>    application are now separate calls in `bounds.py` (`validate`, then `set`);
>    `Session.set` validates at offer time and stages, `_apply_staged` assigns. The cost
>    the PI weighed: an operator who has just lowered a volume watches one more trial go
>    out at the old one. S9a §8.1 has the full account.
> 2. **A pump fault publishes a final frame before it propagates.** `welfare.Rig` still
>    does not swallow it — that refusal is the behaviour that matters and `welfare.py` did
>    not change — but the loop boundary now names the fault in `stopped_because` and
>    publishes once, so a console watching a rig break cage-side sees a reason rather than
>    silence.
> 3. **A refused welfare-bounded set reaches the session record**, in `refusals.jsonl`.
>    Telemetry is lossy by design, so a refusal that reached only telemetry left no durable
>    trace of an attempt to set a dose above its limit. Ordinary parameter typos stay
>    telemetry-only.
> 4. **`reward_correct`'s maximum is 10 mL and is a runaway-fluid fault bound**, not a
>    dose cap — see §5, where the ask that raised it is now answered.

**`SCHEMA` is 3.** `Staged.bounded` stopped meaning "already live" and became "checked
against a welfare ceiling": a field that still decodes and no longer means what it did, so
a console built against schema 2 would render a lowered reward volume as already in
effect.

---

## 2. P4c — the derived Parquet table

**Exit condition:** the columnar table is written at session close and contract-tested
against `wl-preproc`'s published schema. Read **S10**.

JSONL is the durable streamed record deliberately — a Parquet file is only valid once
closed, so it cannot be the crash-safe one. The table is a *derivation* at close, where
a crash costs a conversion rather than a session. `trials.jsonl` now carries the block
and condition per row as well as the resolved parameters, so the derivation has what it
needs.

~~Then the `labhost` endpoint (S10 §4)~~ — **superseded 2026-09-19, ADR-0008.**
`labhost` stopped being its own component: S9a §7 folds P4c's pull-only `/health`
endpoint into the console process as a second surface, same server, separate path,
separate auth. It is built alongside the console's HTTP/WS server now, in P4d-2 (§6),
not here. What is still this package's own is the Parquet derivation above.

---

## 3. Traps specific to what P4b just left behind

- **A "not yet" comment is a claim nothing can check** (trap 20, pitfall P21). Two
  guardrails sat unwired behind one for a week. If you write one, name what it is
  waiting for so the next reader can grep it.
- **The session clock is derived from frames, not the wall.** That is what keeps "stops
  at its out-of-cage ceiling" deterministic. `Session(clock=...)` takes a real one for a
  rig. Do not quietly swap the default.
- **A block test that can run past its criterion now runs to the `out_of_cage` ceiling.**
  Under mutation an unbounded one is a 300-second timeout per function.
  `tests/test_taskd.py` sets that ceiling to 800 s — a little over four hundred trials of
  that task, so the same size of backstop `max_trials=400` was, expressed in the unit a
  real session ends on. The M1 gate raises its own to the twelve-hour figure because its
  claim needs a thousand trials. **Do not reintroduce a trial cap to bound a test**: the
  two stop conditions a real session has are a block quota and this ceiling, and a test
  bounded by anything else is a test of something that cannot happen.
- **A limit whose direction is load-bearing must say so in its name** (trap 22).
  `minima` beside `ceilings`; `shortfall` rather than `check_delivery`.
- **Never `git add` after a mutation run that did not print `restored:`** (trap 12).
  Running the suite while one is in flight reports failures against a neutered module —
  which happened twice this session and read exactly like a real regression both times.
  Editing a *test* file mid-run is the same hazard from the other side: the suite the
  harness is measuring changes underneath it.
- **`caught … timed out after 300s` is the harness noticing a hang, not a test noticing
  a defect** (trap 7's shape again, found 2026-09-19 sweeping `scheduler`). Two
  functions reported it and both were real gaps, not harness bugs. `Scheduler.record`
  hung because `test_scheduler.py` drove a block with `while not scheduler.finished:` —
  a loop that trusts the code under test; it counts to a finite bound and asserts now.
  `Scheduler.advance` hung because `taskd.run()`'s block-advance `continue` runs no
  trial and moves no clock, so a scheduler that reported `finished` and then stayed put
  would spin with an animal in the chair and nothing on any console changing; `run()`
  refuses that now. **If a sweep prints `timed out`, the fix is a bound, not a shrug.**
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

## 3d. ~~The next decision: what the kiosk's iPad actually is~~ — answered 2026-09-19

**The iPad is the experimenter's window, not the animal's screen.** A touch arriving over
WiFi cannot be strobed promptly, and RT is recovered offline by joining sync ticks, so the
animal-facing screen is an attached panel with a wired touch sensor on the edge box. The
cage-side deployment also gains a **reduced sync module**, reversing S13 §2 — which is
what gives `wl-juicer`'s dose input and witness line the home its own spec designed them
for, and gives the kiosk a hardware timebase to recover RT against.

The full control-system design is **S9a §6–§10**. Read that before writing any console
code; it is the one spec this package names.

## 3e. What the console needs that does not exist yet

Three things S9a §6–§10 depends on that nobody has built:

- **`wl-works` must register the box as an OAuth2 client.** Drafted in
  `pending-wl-works-amendments.md`; it is configuration on their side, not development,
  because the `/oauth2/*` surface exists and Zulip consumes it. **Not blocking** — the box
  ships with its own credential and records `unattributed` until identity arrives.
- **Protocol V11** decides whether a browser can carry the replica pane. Measurable now,
  over the LAN, with no rig. Until it is run, S9a §2's replica is the one pane the design
  makes no claim about.
- **`wl-touchtrain` holds no design at all yet**, and now owes one: what the reduced sync
  module carries. S13 §2, §3 and §5 are corrected, and so are S6, S8 and the spec map,
  which all asserted the kiosk had no sync box. What is *not* settled is whether the
  reduced module mints a session id or emits a barcode — S13 §5's three candidates for the
  kiosk's session directory turn on it, and the first is no longer ruled out by hardware.

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
| `wl-works` | **An NTP server, reachable from the lab network on UDP 123** (ADR-0009, 2026-09-20; ask drafted in `docs/pending-wl-works-amendments.md`) | lab hosts agreeing what "today" and a clock time are, for wall-clock welfare marks and the fluid figure that spans rig and kiosk; **not session-blocking** — an outage just stops correction |
| PI | **A photometer measurement of the panel** | every chromatic task (P19); `tasks/visual_search.py` is what waits |
| PI | **A pump calibration: millilitres per second of open time** — protocol **V10**, `docs/validation.md` | real reward delivery (new 2026-09-06) |
| PI | **The real bounded-config numbers** — reward volume per delivery, the daily fluid **floor**, time out of the cage. Asked 2026-09-06; answer was *keep the placeholder until there are animals*. (Chair time and a trial cap were on this list until 2026-09-19; neither is a limit any more, so neither needs a number.) The twelve-hour figure is documented in S8 §5.2 item 4 and in `welfare.py`, deliberately not carried by any constant | every session that is not a simulation |
| ~~PI~~ | ~~**Is a runaway-fluid *fault* limit wanted?**~~ **Answered 2026-09-19: yes.** `reward_correct`'s maximum is 10 mL — far above any dose, so refusing it catches software delivering litres rather than enforcing a ration. It is a **fault bound**, and `tasks/reference_bounds.py`, `bounds.Ceiling` and S8 open item 6 all say so at the entry. The *value* beside it stays a placeholder | ✔ (S8 open item 6) |
| ~~PI~~ | ~~**Which clock is the twelve-hour out-of-cage limit measured on?**~~ **Answered 2026-09-19 and implemented the same day:** the clock runs out of cage to back in cage. `welfare.out_of_cage_seconds` measures it, `must_stop` reads it against `out_of_cage`, and `chair_seconds` is recorded beside it and bounds nothing. `max_trials` went with it | ✔ (S8 open item 7) |
| ~~PI~~ | ~~**Do the out-of-cage marks get event codes?**~~ **Answered 2026-09-20: no.** They are **operator-entered rather than measured**, so a hardware timestamp would add precision to a number that never had it, and our own log and the session directory already carry them. A restart re-asks a person for the departure time — the same clock time they typed the first time. Withdrawn from S2's and `wl-preproc`'s plate | ✔ (S8 open item 8) |
| PI | **Is 30 minutes the right warning before the twelve-hour limit?** `welfare.WARN_WITHIN_DEFAULT` = 1,800 s since 2026-09-20, chosen so a block can be finished deliberately — but **not derived from any measurement**, because no block duration has been measured here. Configurable by `--warn-within`; his number replaces the constant | welfare-facing default, in use now |
| PI | IPD per animal; the tandem panel's two questions | optics, panel |

---

## 6. P4d-1 shipped; P4d-2 is the console's HTTP surface

**What moved, 2026-09-19 (`p4d1-console-link`, on top of `p4b-session-management`).**
This section used to describe P4d as "the link between a console process and a
session" being missing. It is not anymore: `Session` gained a `Link` port, drained and
published once per trial boundary and never per frame — `link.py`'s `Telemetry` (built
only from `welfare`/`tally`/`scheduler`, S9a §9's one rule, unknown always `None`),
`Staged`/`Refused` for S9a §8's visibility, `SetParameter`/`Stop` as the commands a
console sends, and `ZmqLink`/`ZmqConsole` as the one live transport (ZMQ PUB/SUB +
REQ/REP, msgpack, ADR-0003). `wlx run --link PUB,REP` opens it; `wlx console --sub PUB
--req REP --as WHO [--set NAME=VALUE ...] [--stop]` is a terminal client for it — not
the browser ADR-0008 chose, which is exactly what P4d-2 builds. Full account,
including every ruling made building it, in `docs/CHECKPOINT.md`'s "What moved on
2026-09-19" entry and `.superpowers/sdd/2026-09-19-p4d1-console-link/progress.md`.

> **Before you touch a console pane, read S9a §9's "two of those numbers may not be
> removed".** The PI allowed a reward volume of zero *because the console shows it*
> (2026-09-20), so `fluid session` and `supplement` are welfare-load-bearing: a
> simplified pane or a folded summary that stopped showing either would turn a
> permitted operation into a silent one, and an animal working correctly for nothing
> would appear nowhere. This is the one welfare regression P4d-2 could reach without
> touching a welfare-critical file.

**Next is P4d-2: the console's HTTP/WS surface (S9a §7), which is also where
`labhost` lives now.** `wlx console` today talks ZMQ directly; P4d-2 puts an HTTP
server in the same console process — `browser ──HTTP/WS──► console ──ZMQ──► taskd`
(S9a §7's diagram) — for the web client ADR-0008 chose, and adds `GET /health` as a
second path on that same server for `wl-works` to poll, exactly as
`architecture.md`'s `labhost` row already says (S9a §7: *"same process, separate
path, separate auth"*). Read S9a §7 before starting.
`Session.set` is already the validated write path both surfaces go through, and
nothing in P4d-1 assumed a terminal client, so `ZmqConsole` (or a thin wrapper around
it) should be reusable from the server rather than needing a second console-side
implementation.

**The PI ruling this section carried forward is now done.**

> ### There is no session-length maximum, and `max_trials` is gone
>
> **PI, 2026-09-19:** *"There is no session length max. Sessions will be comprised of
> multiple tasks with perhaps multiple blocks of the same tasks. Each task, depending on
> its config, will have a target number of trials (likely per condition within the
> task). But the max trials idea makes no sense to me. The only limit we have welfare
> wise is that a session from out of cage to back into cage cannot be longer than 12
> hours."*
>
> Most of what replaces it already existed: per-condition targets are `scheduler`'s
> `owed()`, `Counts` and `upcoming()`, and the console already renders them as *still
> needed by condition*. It was the session-level cap that made no sense.
>
> **Implemented 2026-09-19**, once the PI settled the clock question that blocked it.
> `welfare.must_stop` reads `out_of_cage` against a twelve-hour ceiling; `chair_seconds`
> is recorded and bounds nothing; `head_fixed`/`head_released` and codes 4128/4129 stay;
> a cage-side session declares `Deployment.CAGE_SIDE` and has no duration bound,
> while an unmarked rig session **raises** rather than running unbounded. `docs/CHECKPOINT.md`'s
> "The welfare clock, and the four rulings that reshaped it" is the full account, and
> S8 §5.2 item 4 is the spec.

**Three things this slice found and deliberately left open, for whoever picks up
P4d-2 or later:**

1. ~~**A pump fault publishes nothing.**~~ **Closed 2026-09-19 by the PI's second
   decision** (§1). `welfare.deliver` still raises and `Rig` still deliberately does
   not swallow it (P21's shape — never absorb a broken rig), but `Session.run`'s loop
   boundary now names the fault in `stopped_because`, publishes one final `Telemetry`
   frame, and re-raises unchanged. What a console should *do* with that frame — beyond
   printing the reason, which `cli.render` already does — is still a design question
   for P4d-2.
2. **A change staged on a session's literal last pass is never applied.**
   `_apply_staged()` gets no further pass once the loop decides to stop (a welfare
   ceiling, every block finished, or a console `Stop`), so a `SetParameter` drained
   on that same last pass is staged and then abandoned — `parameter_changes.jsonl`
   never gets the row, though the final frame still shows it queued beside
   `STOPPED:` (an implicit signal, not silence). **The obvious way to hit this on
   purpose does not, which narrows the risk rather than removing it**: `wlx console
   --set X --stop` sends `SetParameter` then `Stop` as two separate `send()` calls,
   and `ZmqConsole.send`'s lazy reply-read means `Stop` is not even transmitted
   until `SetParameter`'s reply is read — Task 6's reviewer reproduced this 20/20
   times, landing in different `drain()` batches, not the same one (not committed
   under `docs/measurements/`, and not a claim about this system's timing; the
   number says the ordering held every time it was tried, nothing about speed), so
   the ordinary case actually gives `_apply_staged()` a pass in between. The
   residual risk is a `SetParameter` that happens to land on whichever pass a
   *different* stop condition (a welfare ceiling, or every block finishing)
   resolves on — a matter of timing, not of anything an operator does.

   > **Widened on 2026-09-19, and it is now on the reward path.** Before the PI's
   > first decision this could not touch a welfare-bounded name, because `Session.set`
   > moved the ceiling at drain time and only the *record* row was lost. Now the value
   > is staged too, so a `SetParameter(reward_correct, …)` landing on the stopping pass
   > is shown as `staged` on the final frame and then dropped entirely: **no ceiling
   > move, no `parameter_changes.jsonl` row**. Animal risk is low — the session is
   > ending, so no further trial runs at either value, and the ceiling that was in
   > force is the one every trial actually ran under. It is a *record* gap on the fluid
   > path, and it is the price of the deferral. A *refused* command is unaffected:
   > refusals are recorded at drain time
   > (`test_a_recorded_refusal_says_where_in_the_session_it_happened` pins a row landing
   > on that very pass). Whoever closes this item should close it for both kinds at
   > once.
3. **`wlx console --set reward_correct=...` is now a person-invocable path to a
   reward limit** — recorded in §1 above, beside the `bounds.py`/`welfare.py` review
   already waiting.

**Do not skip ahead to hardware work to feel productive.** Everything on that side is
blocked on a card, a panel, a photometer or a pump measurement, and none of the four is
ours to hurry.
