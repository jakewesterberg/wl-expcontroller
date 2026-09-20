# S8 — Session and experiment management

- **Status:** proposed, for PI review
- **Corrected 2026-09-06 by the PI, and the correction is welfare-critical:** §4 and §5
  are written as though fluid had a ceiling. **It does not. Fluid has a floor** — the
  daily figure is a *minimum* the animal must reach, topped up by hand after the
  session if the work did not earn it. There is no upper limit on earned reward and a
  delivery is never refused on volume. Every "budget", "ceiling" and "refuses
  delivery" below that concerns *fluid* reads the wrong way round; the code
  (`bounds.Floor`, `Welfare.shortfall`) is correct and this text is not yet rewritten.
  Chair time and trial count are genuine ceilings and are unaffected.
- **Date:** 2026-08-31
- **Parent:** `2026-08-31-controller-architecture-design.md` §5.5, §7
- **Welfare-critical.** Most of this file requires human review before merge (CLAUDE.md).

---

## 1. Structure

A **session** is one subject's run (S3 §2 — not the sync box's day). It contains:

- **Blocks** — one run of one task, mirroring `wl-preproc`'s `core.Block`. Each declares its
  condition set, parameter overrides, a length rule, and a transition.
- **Interludes** — sub-tasks the session enters and leaves without ending. Calibration is the
  motivating case; an interlude creates no block.

**Blocks are planned in wl.works before the session** (S3 §7). `wl-preproc` authors block rows
from the planner and quarantines on absence, so an unplanned block degrades the session's timing
tier. Changing condition weights or geometry within a task creates no block and is free;
**changing task type mid-session does**, and is therefore a planning operation, not a live edit.

Length rules: fixed N, or criterion-based (*"80% correct over the last 20 completed trials"*).
Criterion transitions consume the same running statistics the console plots use, computed once.

---

## 2. The trial scheduler

Owns condition selection, block progression and the counters.

- **Counters distinguish attempted / completed / correct**, per condition. Collapsing them makes
  a balanced design unverifiable.
- The console shows **achieved against target**, because the question at a rig is never "how many
  have I run" but "how many more do I need."
- **Aborted trials are re-queued under a declared policy.** Default (PI, 2026-08-31): a
  **fixation break is re-queued at the end of the block**; a **wrong choice is not**. The
  reasoning is that a broken fixation is a failure to engage and the condition still owes you a
  datum, whereas a wrong choice *is* the datum. End of block rather than immediately, so the
  animal cannot make an easy condition repeat by breaking on the hard one. Overridable per block.
- Randomisation is seeded and the seed is recorded, so a session's condition order is
  reconstructable.

---

## 3. Parameters

### 3.1 Declaration

Each task declares its parameter space: name, type, unit, valid range, live-editable or not.
From that one declaration comes validation, the console's widgets, the saved record and the ELN
summary — which is what makes live control work for model-authored tasks with no per-task UI
code (ADR-0006).

### 3.2 Application

- **Staged, then applied atomically in the ITI.** Never mid-trial.
- If regenerating derived stimuli overruns the ITI, **the ITI extends. Frames are never
  dropped.**
- Values and structure are both live; **logic is not** — a task reload happens at a trial
  boundary and is logged as a discontinuity (parent §7.2).

### 3.3 Provenance

- **Every trial records a complete resolved parameter snapshot**, not a pointer to "the config."
- Every change emits `PARAM_CHANGE` carrying a sequence number that joins to the change record
  (S2 §5.2). The pointer is on the recording clock; the content is in the session directory.
- **One validated write path**, whatever the origin — console, external control API, or the task
  itself. Origin and actor are recorded. In-task writes are off by default.
- Concurrent writers need an **arbitration rule**: last-write-wins is wrong when a human and an
  adaptive process disagree. Proposed: the console holds a soft lock a process cannot take, and
  a process write during a held lock is refused and surfaced rather than queued.

### 3.4 Precedence

**deployment → rig → subject → task → session → live edits**, all under the bounded config's
ceiling (S13). The resolved set is snapshotted per trial; the layers are recorded too, so a
value's origin is recoverable.

---

## 4. The bounded config

Welfare-critical parameters are **live-editable by a human through the console, bounded by
ceilings the console cannot exceed and the task cannot touch.**

| Bounded | Covers |
|---|---|
| Reward | Volume per delivery, rate. **Not a daily total** — see the correction at the head of this file: the daily fluid figure is a floor, and only the per-delivery volume is a ceiling |
| Session | **Time out of the cage** — the one duration limit (§5.2), twelve hours. **Not maximum trials**: there is no session-length maximum (PI, 2026-09-19), and per-condition targets are a task's config, carried by `scheduler`. Mandatory breaks |
| Tokens | Token-to-fluid conversion, maximum accumulation |
| Stimulation | Amplitude, pulse width, frequency, train duration, duty cycle, charge per phase and charge density, refractory, deliveries per session |

Two structural properties, not conventions:

- **A task cannot express a magnitude.** `Reward(P.reward_small)` resolves through the subject's
  ceiling; `Reward(ml=5.0)` does not type-check (S1 §2.3). The guardrail is the type, not review.
- **One mechanism across rig and kiosk** (S13), so the less-supervised deployment gets no weaker
  path of its own.

---

## 5. Accounting, and what happens when we lose count

### 5.1 Fluid is reconciled, not tallied

Our commanded total is a **lower bound** (P17): the panel button bypasses us entirely and reaches
the pump through the board's OR gate. The truth is the sync box's record of the *delivered* line.

So fluid accounting **reconciles against the sync box's delivered-line record**, continuously
where available and at minimum at session end. A divergence between commanded and delivered is
information — usually manual rewards, occasionally a fault — and is reported rather than
reconciled away.

### 5.2 A restart must not reset the day

`taskd` crashing mid-session is the case that turns an accounting bug into a welfare event: a
naive restart begins the daily fluid total at zero, and the day's shortfall — the amount to
supplement afterwards — is then computed against a figure that describes half a day.

1. **The session record is streamed, not accumulated.** A crash loses the tail, not the session.
   This is the lesson `wl-sync` learned when its own recorder held a whole day in memory.
2. **On restart, the daily total is reconstructed from the sync box's delivered-line record**,
   which survives our crash independently. That is the whole reason the reconciliation in §5.1
   exists rather than being a nicety.
3. ~~**If it cannot be reconstructed, reward is refused until a human confirms a figure.**~~
   **Reversed 2026-09-06.** That rule follows from a ceiling, and there is no ceiling. Under a
   floor the argument runs the other way: an unknown day leaves the *shortfall* unreportable, and
   the one thing it must not do is stop paying an animal that is working. So the session
   delivers, reports the day as uncountable, and a human supplies the figure —
   `Welfare.shortfall()` answers `None` rather than zero, because a day nobody measured is not a
   day that went well.
4. ~~**Session duration is chair time, from head-fixation**~~ **Superseded 2026-09-19 (PI):
   the one duration limit is out-of-cage to back-in-cage, and it is twelve hours.**

   > *"The only limit we have welfare wise is that a session from out of cage to back into
   > cage cannot be longer than 12 hours."*

   Chair time was the wrong clock for that limit, not a wrong idea: it starts at
   head-fixation, so it misses the transport and chairing that sit before it and
   under-counts exactly the interval the institution bounds. `welfare.out_of_cage_seconds`
   measures from the mark, and it is the only quantity `welfare.must_stop` reads.

   **Twelve hours is documented, not configured.** No constant in `welfare.py` carries it —
   a number with a name is a number something will default to — and the figure arrives with
   a real subject's bounded config. `tasks/reference_bounds.py`'s `out_of_cage` value stays
   implausible until there are animals, per that file's own two guards.

   **The mark is "how long ago", and the time base is checked.** The session clock is
   frame-derived and reads zero when the session starts, so the animal leaving its cage sits
   at a *negative* instant in that base — counting transport and chairing requires it. A
   timestamp parameter invited a caller to pass zero, and `wlx run` did, which made
   out-of-cage time identical to chair time: the under-count this clock exists to remove,
   reintroduced by the interface. So `welfare.left_cage(seconds_ago, now)` takes the number an
   operator actually holds, refuses a value in the future, and refuses one longer ago than the
   ceiling — which is also what catches a wall-clock timestamp handed to a session-relative
   parameter, and is the same refusal a session already past twelve hours gets.
   `wlx run --out-of-cage-ago` is **required with no default**, for the reason `--as WHO` is.

   **The absence of a mark must never disable the limit.** A rig session nobody marked and a
   cage-side session with nothing to mark are indistinguishable to anything that answers zero,
   so a session **declares** which it is: `welfare.Deployment.OUT_OF_CAGE` carries the clock
   and the ceiling and refuses without either, and `ANIMAL_AT_HOME` states that the animal
   never left home and the deployment therefore has no duration bound (S13 §4). The
   declaration is required on `SessionSpec`, with no default, and a cage-side config that also
   states an `out_of_cage` ceiling is refused — the two must not disagree.

   **And the *presence* of both marks must not disable it either.** The mirror case, found by
   review: two marks in the wrong order are a session that reports itself fully marked and is
   bounded by nothing. A return before the departure gave a **negative** duration, which is
   under every ceiling there is; a return marked mid-session **froze** the clock, so
   `must_stop` answered `None` for the rest of it; and the opening guard allowed a *re-arm*
   after a return, so one `Welfare` could report a fresh clock for an animal out twenty-two
   hours. The interval is therefore **opened once, closed once, and never runs backwards**: a
   return is refused unless it closes an open interval, is refused while the animal is
   recorded as head-fixed (it cannot be in the chair and in its cage at once, which is what
   puts the whole trial loop inside the refusal), and is refused before the departure. A
   closed interval refuses a `preflight` and **stops** a running session rather than freezing
   its clock.

   **Out and back is one session** — PI, asked and answered 2026-09-20, after the code was
   written the way the rest of this item describes. It is recorded as a ruling rather than as
   an inference from the wording above because this repository has learned the difference:
   three of the first four decisions revisited as inferences were changed once somebody
   actually asked (CLAUDE.md, "ask, do not file"). The question was whether an animal returned
   to its cage briefly and brought out again resumes its session or starts a new one. It
   starts a new one, so `left_cage` refuses to re-arm a closed interval.

   **The consequence the PI weighed and accepted:** an animal returned mid-day produces **two
   session directories and two records**, not one record with a gap in it. He judged that the
   more honest account — a single record spanning a period the animal was not in the rig would
   have to leave that period unexplained, and nothing downstream could tell it from a session
   that simply ran long.

   **Chair time is still recorded and bounds nothing.** `HEAD_FIXED` / `HEAD_RELEASED`
   (4128/4129, allocated in S2) remain, and the reasoning below stands unchanged: restraint is
   the one welfare quantity with no hardware line, so the codes *are* its durable record and an
   offline reader recovers chair time from the sync box's `W` capture of them. Head-fixation
   also stays a **preflight requirement** for a rig session, because a session with neither
   code in the stream has no record of restraint at all.

   **This needs an input the software did not have, and it needs one for a second reason.**
   Nothing tells `taskd` when the animal was fixed: `wl-shook`'s resting pedestal proves the
   chair device is present, not that an animal is in it. So the console gains an explicit
   **"animal fixed" / "animal released"** action — and, since 2026-09-19, an **"out of cage" /
   "back in cage"** action beside it, which is what preflight now requires.

   **Open, and asked of the PI: the out-of-cage marks have no event code.** The argument that
   made head-fixation event-coded — a clock with no hardware record cannot survive a restart —
   now applies with more force to the clock that actually bounds the session. Allocating two
   codes is S2's and `wl-preproc`'s to agree (ADR-0007), so it is asked rather than taken.
   Until it is answered a restart loses this clock's start and a person supplies it again;
   nothing reconstructs chair time from the sync box today either.

### 5.2c Every number entering the welfare path

**Three review rounds found one class of defect on three surfaces**, because each was fixed
where it was found. The class: a guard on a *limit*, with the *measurement* compared against
it left unchecked. Written out here rather than in `welfare.py`, so that the code carries one
sentence per guard and this carries the argument.

**Two kinds of bad number, and they break guards in opposite ways.**

- **`nan` is `False` against every ordered comparison**, so nothing refuses it: not `< 0`, not
  `> ceiling`, not `max(0.0, floor - nan)`. It reached the limit (`--out-of-cage-ago nan`:
  400 rewarded trials, clean summary, no duration limit), the *ceiling* (a NaN `out_of_cage`
  in a bounded config, honest mark), and the *measurement* (`--delivered-today nan`: an animal
  on 10.90 mL against a 20 mL floor reported as `supplement: 0.00 mL` — "nobody measured"
  turned into "nothing is owed", in the one figure the 2026-09-06 floor ruling exists to
  produce).
- **`inf` is ordered but unreachable**: `seconds > inf` is `False` for every real duration, so
  an `inf` ceiling is never exceeded. An earlier version of this account said `inf` "was
  already refused correctly"; **that was measured false** — only the *mark* route refused it.
  Recorded rather than deleted, because it was repeated twice before anyone checked it.
- **A negative magnitude passes every `>`.** Through the real console path,
  `--set reward_correct=-0.5` commanded twenty rewards of −0.5 mL to the pump and then asked
  for 30 mL of supplement against a 20 mL floor; `--delivered-today=-1000` asked for 1019.75.

**The rule, in two words.** *An instant is finite. A magnitude is finite and not negative.*
Instants are the clock readings and the marks; magnitudes are volumes, durations, and every
limit on them. `bounds._finite` and `bounds._magnitude` are the two guards, spelled with
`math.isfinite` because `calibration._yaml_float` already spells it that way.

**The enumeration is checked, not asserted.** `tests/test_welfare.py` lists every numeric
entry point on the two welfare-critical modules with a driver for each, recomputes that set
from the live modules, and **fails if anything is in neither the guarded list nor an exempt
list with a reason** — the shape `tools/mutation_gate.py` uses for modules. A new float-taking
method on either file fails the suite until it is guarded and listed. Its own blind spots — an unannotated
parameter, one annotated `object`, and a `@property`/`@staticmethod`/`@classmethod`
descriptor — have their own test and their own walk.

**What would still have to be true for a door to be missing.** An earlier version of this
said "exactly two routes", and a review disproved it by planting six doors the tripwire
could not see. There are **at least six**: a parameter the introspection cannot classify
(closed); a numeric type the classifier does not name, such as `Decimal` (narrowed — it is a
list of spellings); a number inside a container, which is safe here only because
`Bounds.ceilings` holds `Ceiling`s rather than bare floats; `*args`/`**kwargs`; arithmetic
producing an unchecked third value; and assignment after construction. The last two are not
closable by enumerating doors, which is why `out_of_cage_seconds` checks the *computed*
duration, `reconcile_report` checks both inputs, and every field feeding a comparison is
guarded where it is read as well as where it is set.

**A reward volume of exactly zero is allowed, because it is visible** — PI, asked and answered
2026-09-20.

Zero is a quantity, not a non-quantity, so neither guard refuses it; the question put to him
was whether a *policy* refusal belonged on top. A console setting the volume to zero
mid-session leaves every subsequent correct trial unpaid, which is `welfare.Absent`'s failure
reached another way. **He allowed it, on the reasoning that it is not silent** — and because
it is a legitimate operational move: pausing reward without ending a session.

**The consequence he weighed and accepted:** while it holds, an animal working correctly is
paid nothing.

**So the visibility is the condition of the ruling, not an incidental property.** Two numbers
carry it, and both must keep reporting: `welfare.session_total()` — which
`link.Telemetry.fluid_session_ml` reads and `cli.render` prints as `fluid session: 0.00 mL` —
and `welfare.shortfall()`, which keeps the supplement figure correct by reporting the whole
floor as still owed. **A change that stopped reporting either would turn a permitted operation
into a silent one**, and would be a welfare regression even though it touched only a console
pane. `cli.render`, `link.Telemetry` and S9a §9 each carry that sentence, because a session
simplifying the renderer or the reconciliation is where it would otherwise be lost.

**This is the one place a magnitude of zero is deliberately allowed on the welfare path.** The
rule above — *an instant is finite; a magnitude is finite and not negative* — is unchanged and
has no exception. What sits on top of it is a policy choice about zero, for this one quantity,
made by the PI and conditional on the reporting above.

### 5.2d Every refusal in the two welfare-critical files

**"Is this refusal earned?" should be a lookup, not a reading.** §5.2c earns the nine
`_finite`/`_magnitude` refusals as a class, but `welfare.py` has eighteen `raise` sites and
`bounds.py` five, and a reviewer sitting at `returned_to_cage`'s five would not find them
there. Every one is below, with the failure it was written against and where the argument
lives.

The first column is **the literal head of the message, greppable** — `grep -rn "<phrase>"
wl_expcontroller/` lands on the `raise`. Interpolated values are elided.

| Refusal (greppable) | Written against | Argument |
|---|---|---|
| **`bounds.py`** | | |
| `is not a real number` | `nan` and `inf` defeat every ordered comparison, in opposite ways: one is `False` against all of them, the other unreachable. `--out-of-cage-ago nan` ran 400 rewarded trials with no duration limit; a NaN ceiling in a config did the same | §5.2c |
| `cannot be negative` | `--set reward_correct=-0.5` through the console path commanded twenty rewards of −0.5 mL to the pump, then asked for 30 mL of supplement | §5.2c |
| `has no ceiling in the bounded config` | A typo becoming an unbounded parameter: `rewrd_correct` set to 5.0 would otherwise be accepted, bounded by nothing | §4 |
| `may not exceed` | The console ceiling. Reward volume is the parameter most often adjusted mid-session and the one where a slip is a dose | §4 |
| `declares no … minimum, so nothing can say what the day still owes` | A missing floor reads exactly like a floor of zero, so nobody would ever be told to supplement | §5.2b |
| **`welfare.py`** | | |
| `no pump is configured` | A no-op pump lets a session score every trial correct and dispense nothing; the first sign is a weight check days later | module docstring; `dio.Absent` |
| `declares no … minimum, so a session could never say what the day still owes` | The same missing floor, refused at session start rather than at close | §5.2b |
| `has no … ceiling, so a session out of the cage would be unbounded` | A missing limit is not an absent one | §5.2 item 4 |
| `states an … ceiling while this session declares the animal is at home` | The declaration and the config disagreeing is a limit switched off by a flag | S13 §4.0 |
| `is at home, so it cannot also be recorded as leaving its cage` | The same disagreement, reached from the mark instead of the config | S13 §4.0 |
| `is already recorded as out of its cage at` | Two clocks, shorter wins — **and the re-arm**: out at 0, home at 43,000, out again at 43,100 reported a fresh clock for an animal out twenty-two hours | §5.2 item 4 |
| `cannot have left its cage … seconds in the future` | A negative "how long ago" is a mark nothing could have taken | §5.2 item 4 |
| `is recorded as out of its cage … ago, against a ceiling of` | A wall clock handed to a session-relative parameter (1.79e9 s is fifty-seven years), and a session starting at or past its own limit | §5.2 item 4 |
| `is at home, so there is no interval for a return to close` | Declaration and mark disagreeing, on the closing side | S13 §4.0 |
| `is not recorded as having left its cage, so a return closes nothing` | A session marked only at the end has no interval at all | §5.2 item 4 |
| `is already recorded as back in its cage at` *(in `returned_to_cage`)* | A second return moves a closed interval, and the shorter one silently wins | §5.2 item 4 |
| `is recorded as head-fixed at … and not released, so it cannot also be in its cage` | **The freeze.** A return marked mid-session froze the clock at whatever it read, so `must_stop` answered `None` for the rest of a session that reported itself fully marked | §5.2 item 4 |
| `cannot be back in its cage at … having left it at` | A return before the departure gave a **negative** duration, which is under every ceiling there is | §5.2 item 4 |
| `is not recorded as out of its cage, so the session's one duration limit has no start` | **The absence of a mark must never disable a limit.** An unmarked rig session is indistinguishable from a cage-side one to anything that answers zero | §5.2 item 4 |
| `A duration that runs backwards` | Arithmetic producing an unchecked value from checked marks — a `now` in a base the mark was not taken in | §5.2c |
| `is already recorded as back in its cage at …, so this session's interval is closed` | The closed-clock hole reached *before* the loop rather than during it | §5.2 item 4 |
| `is not recorded as head-fixed, so the session would carry no record of restraint` | A rig session with no `HEAD_FIXED` in the stream has no durable record of restraint | §5.2 |
| `is already recorded as head-fixed at` | Two restraint clocks, and the shorter one would silently win | §5.2 |

**Twenty-three refusals; nine of them are the two guards of §5.2c and fourteen are
structural.** Every message is kept verbatim in the code — they are what an operator reads —
and this table is the index into why each exists.

### 5.2b One fluid budget across rig and kiosk

**Kiosk fluid counts toward the same daily figure as rig work** (PI, 2026-08-31). Neither
deployment can see the other's record, so a shared total has to live somewhere neither owns.

> **Corrected 2026-09-19.** The reason given here was "the kiosk has no sync box at all",
> and the kiosk now gets a reduced one (S13 §2). **The conclusion is unaffected** — a sync
> module gives the kiosk a local timebase, not sight of the rig's records — but the reason
> was load-bearing for a reader, so it is replaced rather than left to be believed.

**wl-works holds the ledger and pushes the day's already-delivered total in `prepare-session`.**
It is the ELN, it already keys on subject and session, and the network topology permits a push in
but no pull out. Each deployment then reports `floor − already_delivered_today − earned_here` as
the amount still to supplement, and its own finished total reaches wl-works by the normal path.
(Written as `ceiling − already_delivered_today` before the 2026-09-06 correction.)

- **A start-time figure is sufficient**, because an animal cannot be in the chair and at the cage
  kiosk simultaneously — the deployments are sequential, so the one that starts second gets a
  current number.
- ~~**The fail-closed rule of §5.2 now bites more often.**~~ **Reversed 2026-09-06 with §5.2
  item 3.** A deployment that cannot learn the day's prior total cannot report what to
  supplement; it still pays the animal. Cage-side, where the ELN link is the only source, that
  is the difference between an unreportable day and an unrewarded one.
- Added to the wl-works handover as a field on `prepare-session`.

### 5.3 Tokens

Token state is session-scoped cross-trial state (S1 §5.6), recorded in every per-trial snapshot
and in the event stream. Conversion to fluid is bounded config, so a token economy cannot exceed
a *per-delivery* reward ceiling by accumulating past it. (There is no daily fluid ceiling to
exceed — see the correction at the head of this file.)

---

## 6. Restart and resume

| Question | Answer |
|---|---|
| Is the log lost? | No — streamed |
| Is fluid lost? | No — reconstructed from the delivered line; the session pays on regardless (§5.2 item 3) |
| Is the duration clock lost? | **Yes, today.** The out-of-cage marks are not event-coded yet (§5.2 item 4), so a restart cannot reconstruct them and a person re-supplies the start |
| Does the session resume? | The session **continues**; block and trial indices carry forward from the record |
| Does calibration survive? | The gaze mapping is reloaded by version; if the optics moved, it does not (S5 §6) |
| Is it recorded? | A restart is a discontinuity, event-coded like any other |

**A restart is never silent.** The console shows it, the record carries it, and the session
summary reports it.

---

## 7. Welfare-critical modules

Listed here so review has a target (CLAUDE.md). Kept small deliberately:

1. The bounded-config loader and its ceiling enforcement.
2. Reward scheduling and delivery.
3. Fluid, session-duration and token accounting, including §5.2's reconstruction and refusal —
   and §5.2 item 4's `Deployment` declaration, which decides whether a duration limit applies
   at all.
4. Stimulation gating, bounds and delivery counting.

Everything else may change without a welfare review. These four may not.

---

## 8. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Arbitration rule between console and control-API writers (§3.3) | S9 |
| 2 | Whether the sync box's delivered-line record is readable by us live, or only at session end | §5.1's "continuously" — **less urgent since 2026-09-06**: with a floor rather than a ceiling nothing in-session depends on it, and session-end is enough to compute a supplement |
| 6 | ~~**Is a runaway-fluid fault limit wanted?**~~ **Answered 2026-09-19 (PI): yes, and it is `reward_correct`'s maximum.** Set to **10 mL** — far above any dose, so what it refuses is software delivering litres, not an animal earning a ration. `Ceiling` therefore no longer means "a protocol figure" at every entry: `bounds.Ceiling` names the two kinds, and a bounded config states at each entry which it is — `tasks/reference_bounds.py` labels `reward_correct` a fault bound and `out_of_cage` a protocol figure. The *value* beside it stays a placeholder until there are animals | ✔ |
| 7 | ~~**There is no session-length maximum**~~ **Done 2026-09-19.** `max_trials` is gone — from `welfare`, from `must_stop`, from `tasks/reference_bounds.py` and from every document that said two ceilings end a session. Per-condition targets were always `scheduler`'s (`Counts`, `owed()`, `upcoming()`), which the console renders as *still needed by condition*. The clock question that blocked it is answered in the same change: `welfare.must_stop` reads **out-of-cage time** against a twelve-hour ceiling, and chair time is recorded and bounds nothing. See §5.2 item 4 | ✔ |
| 8 | **The out-of-cage marks have no event code** (§5.2 item 4). The clock that now bounds a session has no hardware record, so a restart cannot reconstruct it — the gap `HEAD_FIXED` closed for chair time. Two codes in 4096–32767 would close it; allocation is S2's and `wl-preproc`'s under ADR-0007 | PI, asked 2026-09-19 |
| 3 | ~~Default re-queue policy~~ **Answered: fixation break re-queued at end of block, wrong choice not, overridable per block** | — |
| 4 | ~~Session duration from first reward or first trial~~ ~~**Answered: chair time, from head-fixation.**~~ **Re-answered 2026-09-19: out of cage to back in cage, twelve hours** (§5.2 item 4). Remaining: whether a hardware head-fix signal is ever worth adding beside the console action — still open, and now about a *recorded* quantity rather than a bounding one | welfare review |
| 5 | Who plans blocks when wl.works is unreachable | S3 §7's quarantine risk |
