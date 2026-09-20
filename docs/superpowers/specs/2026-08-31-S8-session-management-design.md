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

   **And a value that is not a number must not disable it either.** The same failure reached
   a third way, found by review after the two below were closed: every guard on this path is
   an *ordered* comparison, and **NaN is `False` against all of them** — not in the future,
   not past the ceiling, not backwards. One NaN made the mark NaN, the duration NaN, and
   `must_stop` answer `None` for a whole session; `wlx run --out-of-cage-ago nan` (argparse's
   `float` accepts it) ran four hundred rewarded trials with a clean summary and no limit.
   A NaN `out_of_cage` **ceiling** in a bounded config did the same with an honest mark.
   `inf` was always refused, because `inf` is ordered — which is what made NaN the one that
   got through. `bounds._finite` now refuses a non-finite value at `Ceiling`, at `Floor`, at
   `Bounds.validate` and at both ends of the out-of-cage mark, spelled with `math.isfinite`
   because `calibration._yaml_float` already spells it that way.

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
