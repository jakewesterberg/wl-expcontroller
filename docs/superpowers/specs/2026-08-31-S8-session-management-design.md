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

   ~~**The mark is "how long ago", and the time base is checked.**~~ **The mark is a clock
   time, and the mapping lives in `welfare` — PI, 2026-09-20.** *"A clock time is what an
   operator reads."*

   The time-base problem is unchanged and so is its solution: the session clock is
   frame-derived and reads zero when the session starts, so the animal leaving its cage sits
   at a *negative* instant in that base — counting transport and chairing requires it. A
   plain timestamp parameter invited a caller to pass zero, and `wlx run` did, which made
   out-of-cage time identical to chair time: the under-count this clock exists to remove,
   reintroduced by the interface. What changed is **where the arithmetic happens**.
   `welfare.left_cage(at, wall_now, now)` takes the departure as a wall-clock instant, takes
   the wall clock the session is reading beside it, and does the subtraction itself — so
   there is exactly one place the two bases meet, and it is inside the welfare-critical file.
   A caller that computed the interval would be a second such place, which is how the first
   one came to pass zero. `wlx run --out-of-cage-at` is **required with no default**, for the
   reason `--as WHO` is.

   **What the change cost, shown to the PI and accepted.** The old ceiling refusal doubled as
   a wall-clock catch: an *interval* of 1.79e9 seconds is fifty-seven years and self-evidently
   absurd. An *instant* of 1.79e9 is simply now, so that catch is gone. Worse, a plausible
   typo now survives: `08:45` for `18:45` is nine hours of slack, comfortably inside a
   twelve-hour ceiling. Two refusals replace it and a third thing does the rest:

   - **A departure in the future is refused** — against the wall clock the session is
     reading, which is the mark nothing could have taken.
   - **A departure longer ago than the subject's `out_of_cage` ceiling is refused** — the
     same refusal that already existed, and still what catches the gross error: a date typed
     a day early, or a zone an operator's phone was in.
   - **The computed interval is printed where the operator sees it as the session starts** —
     `wlx run` prints *"the animal has been out N hours M minutes"* with the departure it
     resolved. A nine-hour error is then legible rather than silent, which is the condition
     on which the guard was given up. The finiteness and magnitude contract of §5.2c is
     unchanged, and now covers three readings rather than two plus the interval they imply.

   **And a fourth thing, asked for the same day once he had seen the trade: a person
   confirms a departure more than thirty minutes from now.**

   > *"if a number is input that is more than 30 min from the current time, a warning should
   > appear that the experimenter must click through to confirm. There should also be an
   > option to update the time if necessary, but a reason should be given and the
   > experimenter name logged."*

   **Thirty minutes is his number, not a derived one**, and it lives in
   `welfare.CONFIRM_MARK_WITHIN` rather than in `cli.py` so nothing re-derives it from the
   ceiling. It is 1,800 and so is `WARN_WITHIN_DEFAULT`; the two are separate constants that
   happen to agree, because tuning a console warning must not quietly move a welfare guard.

   **The band sits between "obviously wrong" and "obviously fine", and both edges still
   refuse.** A departure in the future and one at or past the ceiling are refused outright and
   are never offered for confirmation — a prompt that sometimes means "check this" and
   sometimes stands between an operator and a run is a prompt clicked past. A consequence
   worth knowing before reading the tests: `tasks/reference_bounds.py`'s `out_of_cage` ceiling
   is a deliberately implausible ten minutes, **shorter than the threshold**, so that config
   has an *empty* band and `wlx run` against it never prompts. Review made the point that this
   left **nothing that ships able to dry-run the one welfare interaction an operator is asked
   to perform**, so `tasks/twelve_hour_bounds.py` is a second reference config carrying the
   real institutional ceiling — same subject `REFERENCE`, same implausible fluid placeholders,
   one entry different. `--confirm-out-of-cage`'s help names it, and two tests check the pair
   rather than asserting it.

   **What each case does, and the non-interactive one is the decision.**

   - **Interactive** (`stdin` is a terminal): `wlx run` prints the warning and asks. Anything
     that is not a confirmation stops the session, **end-of-input included** — a prompt whose
     default is "proceed" is the silent path wearing a question mark.
   - **Non-interactive: it refuses.** `wlx run` may have no terminal behind it — a wrapper, a
     scheduler, the `labhost` process P4d-2 adds — and proceeding there would write a
     confirmation nobody made, which is worse than no confirmation at all.
     `--confirm-out-of-cage` is the honest way to say it out loud, and the recorded row says
     the confirmation came from a flag rather than from a person, because **a wrapper with
     that flag baked in is how this ruling would otherwise be defeated in silence.**
   - **Amended**: `--amend-out-of-cage-to TIME` with `--amend-reason WHY` and `--as WHO`, or
     the same three typed at the prompt. **Both are required with no default and no blank** —
     `welfare.amend_mark` refuses either missing, for the reason `--as WHO` is required for a
     console write. **An amendment is its own confirmation** (a named person giving a reason
     has done strictly more than click through) but **not an override**: the amended value
     goes through the mark and meets every refusal the original would have.

   **The guard is on the marks, not only in `wlx run`.** `welfare.left_cage` and
   `returned_to_cage` take a `confirmed` flag and refuse a far mark without it. That is
   CLAUDE.md's "a safety component ships with its consumer, or its absence fails" rather than
   belt and braces: both are console actions, and P4d-2's console calling `Session.left_cage`
   directly would otherwise reach around the prompt entirely. A caller can lie to `confirmed`;
   it cannot forget it.

   **The amendment is recorded durably, in `welfare_notes.jsonl` in the session directory.**
   Not `parameter_changes.jsonl`, whose rows carry a `sequence` joining them to a strobe on
   the recording clock — and these marks are deliberately *not* event-coded (open item 8), so
   such a row would look alignable and be nothing of the kind. Not `refusals.jsonl`, which is
   for writes that did **not** happen and is capped against a flooding console peer. It is
   written by `record.welfare_note` at the moment it happens, **before `Session.run` opens the
   record**, because the mark has to be settled before `preflight` and because a row written
   then survives every refusal that can follow. Confirmations are written too, with `how`
   naming which path they came from. Each instant is written twice — the POSIX float and local
   clock time with its zone — because the question this file answers is asked by a person.

   **Date and timezone are resolved, not implicit** (`cli._wall_clock_time`). A value with no
   offset is read in **this host's local timezone** — the clock on the wall the operator is
   reading — and one carrying an offset is honoured as given; an ambiguous local time, the
   repeated hour when clocks go back, takes the first occurrence.

   **The daylight-saving gap is closed, not fixed — PI, 2026-09-20.** *"the dst switches
   happen in the night, when no experiments occur."* The unsafe half of the two DST hours is
   the **spring-forward** one: a nonexistent local time is moved *forward*, so
   `2026-03-29T02:30` resolves to `03:30+02:00` and the animal is reported as out up to an
   hour **less** than it has been. That hour cannot be typed as a departure if no session runs
   through it, so the arithmetic is left alone rather than special-cased for a value nothing
   can produce. **The description of what would happen is kept, in `cli._wall_clock_time` and
   here, because the dismissal rests on a fact about when experiments run and not on anything
   about the arithmetic** — if night sessions ever start, an overnight protocol or an
   unattended cage-side kiosk (S13), the hour comes back with them, and whoever reads this
   then needs to find what it does rather than a note saying it was considered and closed.

   **The daylight-saving gap is closed, not fixed — PI, 2026-09-20.** *"the dst switches
   happen in the night, when no experiments occur."* The unsafe half of the two DST hours is
   the **spring-forward** one: a nonexistent local time is moved *forward*, so
   `2026-03-29T02:30` resolves to `03:30+02:00` and the animal is reported as out up to an
   hour **less** than it has been. That hour cannot be typed as a departure if no session
   runs through it, so the arithmetic is left alone rather than special-cased for a value
   nothing can produce. **The description of what would happen is kept, in
   `cli._wall_clock_time` and here, because the dismissal rests on a fact about when
   experiments run and not on anything about the arithmetic** — if night sessions ever start,
   an overnight protocol or an unattended cage-side kiosk (S13), the hour comes back with them
   and whoever reads this then needs to find what it does rather than a note saying it was
   considered and closed. A bare `HH:MM` is **today's
   date on this host and is never rolled back to yesterday**: rolling back would turn `23:59`
   mistyped in the morning into an animal recorded as out for most of a day, which is the
   exact class of error the refusals above exist for. An overnight departure is typed with
   its date.

   **The absence of a mark must never disable the limit.** A rig session nobody marked and a
   cage-side session with nothing to mark are indistinguishable to anything that answers zero,
   so a session **declares** which it is. The declaration is required on `SessionSpec`, with
   no default, and a cage-side config that also states an `out_of_cage` ceiling is refused —
   the two must not disagree.

   **Three kinds, not two — PI, 2026-09-20**, who was shown this shape and chose it:

   | `welfare.Deployment` | out-of-cage mark | head-fixation | duration bound | `chair_seconds` | 4128/4129 | `Telemetry.chair_seconds` |
   |---|---|---|---|---|---|---|
   | `RIG_FIXED` | required | required | yes | a number (`0.0` before fixation) | emitted at both ends | the number |
   | `RIG_CHAIRED` | required | **refused** | yes | **`None`** | **never emitted** | **`None`** |
   | `CAGE_SIDE` | **refused** | **refused** | no | **`None`** | **never emitted** | **`None`** |

   Head-fixation was a blanket rig requirement until then, which made the commonest
   intermediate — a chaired animal working at a screen, unfixed — impossible to declare and
   therefore impossible to run honestly. It is a property of the deployment, so `preflight`
   asks for it only where the deployment says the marks exist.

   **`chair_seconds` is absent, never `0.00`, for the two kinds that take no marks**, and
   this is the trap the shape was chosen against. A chaired-but-unfixed animal *is*
   restrained; what it lacks is head-fixation marks. `0.00` there would be a welfare quantity
   reported as a measured zero by something that measured nothing — `shortfall()` answering
   `0` for a day nobody measured, in another costume. `CAGE_SIDE` answers `None` for the other
   reason: the animal was never restrained at all. The two absences are **different facts**,
   so `Telemetry` carries the declaration and `cli.render` prints one of

   - `chair: n/a -- cage-side, the animal is home and unrestrained`
   - `chair: n/a -- this deployment takes no head-fixation marks, so restraint is UNMEASURED
     here, not zero; the animal is in a chair`

   rather than deriving which it is from the pattern of nulls. `welfare.head_fixed` **refuses**
   the two kinds that declare no such marks, in both directions like every other declaration
   here — without that refusal, `chair_seconds` answering `None` would be discarding a
   measurement somebody took rather than reporting one nobody could take. `taskd.Session.run`
   releases the head only for `RIG_FIXED`. **What actually makes "no stream carries a
   `HEAD_RELEASED` with no `HEAD_FIXED` before it" true is `welfare.head_released`'s own
   three refusals**, not `run()`: the sentence was credited to `run()` when it was written,
   and a console action calling `Session.head_released` directly — which is precisely what
   the console gains — bypassed `run()` entirely. It is refused now on the deployment, on
   there being a fixation to release at all, and on the release preceding it.

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

   **The return is a clock time too — PI, 2026-09-20 (ruling 4), and the symmetry is the
   point.** ~~The session clock stops when the frames do, so a return marked long after the
   loop ended carries the loop's last reading unless the caller supplies a later one.~~
   **Closed by this ruling.** That caveat was the gap, not a footnote about it: an operator who
   ends a session, unchairs the animal, walks it back and *then* marks the return was recording
   the animal as home at the instant the frames stopped, so the release, the unchairing and the
   walk back — minutes of an animal out of its cage — fell outside the twelve hours, every
   time. With both ends read from the wall, the frame clock stopping no longer matters.

   **`welfare.returned_to_cage(at, wall_now, confirmed=False)` maps against `left_cage`'s
   anchor, not against a fresh `now`/`wall_now` pair.** Those two are the same instant only
   while the loop is running; afterwards the session clock is frozen and the wall clock is not,
   and a mapping built on them would drop exactly the interval this ruling exists to count.
   `Welfare.left_cage_wall_at` is that anchor, set by `left_cage` and by nothing else, and the
   return refuses when it is absent rather than mapping against `None`.

   **Every refusal the return already had is preserved**, now read against wall instants:
   nothing to close, a second return, an animal still head-fixed, a return before the
   departure. **Two are new and both are the departure's**: a return **in the future**, which
   is a mark nothing could have taken and which would *stretch* the interval rather than
   shorten it, and one more than `CONFIRM_MARK_WITHIN` ago that no person confirmed. The
   confirmation applies identically because a return typed hours ago moves the same interval —
   in the direction that makes a session look shorter than it was — and the amendment path is
   the same `welfare.amend_mark`, with the same required reason and actor.

   **The consequence the PI weighed and accepted:** an animal returned mid-day produces **two
   session directories and two records**, not one record with a gap in it. He judged that the
   more honest account — a single record spanning a period the animal was not in the rig would
   have to leave that period unexplained, and nothing downstream could tell it from a session
   that simply ran long.

   **The session warns as the limit approaches — PI, 2026-09-20.** The console showed the
   clock and nothing drew attention as it ran out, so the limit arrived as an interruption
   rather than as a deadline an operator had been working towards; he asked for a warning so a
   block can be finished deliberately. `welfare.approaching_limit(now)` returns the sentence
   or `None`, `Telemetry.duration_warning` carries it, and `cli.render` prints it beside the
   stop reason. It is `None` once the limit is past, where `must_stop` speaks instead.

   ~~**The threshold is `welfare.WARN_WITHIN_DEFAULT` = 1,800 s … and it is a proposal
   awaiting the PI.**~~ **Accepted by the PI on 2026-09-20 as a starting value**, so it is his
   figure rather than an implementer's — which is the difference between a number an operator
   sees and a number somebody guessed. It remains `welfare.WARN_WITHIN_DEFAULT` = 1,800 s,
   configurable by `SessionSpec.warn_within` / `wlx run --warn-within`. It is **not derived
   from any measurement of this system** — no block duration has
   been measured and nothing under `docs/measurements/` states one, so nothing here claims it
   clears a block. What it is: a twenty-fourth of the twelve-hour limit, **intended to be**
   long enough to finish what is running and walk an animal back and short enough not to sit
   on screen for most of a session — an intention, not a measured property, stated as one
   because the sentence before it disclaims measuring anything. **That is why it is a
   *starting* value and not a settled one**, and every word of the disclaimer above is kept
   for exactly that reason: accepting a number is not the same as measuring one. Zero switches the warning off. **A threshold wider than the ceiling is not
   refused**: such a session is genuinely inside the threshold throughout, and refusing it
   would make `tasks/reference_bounds.py`'s deliberately implausible ten-minute placeholder
   fail to construct a `Welfare` at all. This may carry a named default where twelve hours may
   not, because it **bounds nothing** — the session ends at the same instant whatever it is.

   **Chair time is still recorded and bounds nothing.** `HEAD_FIXED` / `HEAD_RELEASED`
   (4128/4129, allocated in S2) remain, and the reasoning below stands unchanged: restraint is
   the one welfare quantity with no hardware line, so the codes *are* its durable record and an
   offline reader recovers chair time from the sync box's `W` capture of them. Head-fixation
   also stays a **preflight requirement** for a `RIG_FIXED` session — **not for every rig
   session**, since `RIG_CHAIRED` is a rig session and takes no such marks (see the table
   above, which this sentence contradicted until 2026-09-20). It stays for the kind that has
   them, because such a session with neither code in the stream has no record of a restraint
   that happened.

   **This needs an input the software did not have, and it needs one for a second reason.**
   Nothing tells `taskd` when the animal was fixed: `wl-shook`'s resting pedestal proves the
   chair device is present, not that an animal is in it. So the console gains an explicit
   **"animal fixed" / "animal released"** action — and, since 2026-09-19, an **"out of cage" /
   "back in cage"** action beside it, which is what preflight now requires.

   ~~**Open, and asked of the PI: the out-of-cage marks have no event code.**~~
   **Answered 2026-09-20 (PI): they do not get one, and this is closed** (open item 8).

   His reasoning: the out-of-cage marks are **operator-entered rather than measured**, so a
   hardware timestamp would add precision to a number that never had it — an operator typing
   `08:45` is not producing a figure a microsecond-accurate strobe makes truer. Our own log
   and the session directory already carry both marks, which is the record this quantity
   warrants. The argument that made head-fixation event-coded does not carry over, because
   that clock is about an event with a defined instant and this one is about a recollection.

   **The consequence, which follows rather than being conceded:** a restart cannot reconstruct
   this clock, so a person re-supplies the departure time — by typing the same clock time they
   typed the first time, which is exactly as good as the original. §6's restart table says so.
   It is no longer an ask on `wl-preproc` or S2 and has been removed from the outstanding-ask
   lists.

### 5.2c Every number entering the welfare path

**Three review rounds found one class of defect on three surfaces**, because each was fixed
where it was found. The class: a guard on a *limit*, with the *measurement* compared against
it left unchecked. Written out here rather than in `welfare.py`, so that the code carries one
sentence per guard and this carries the argument.

**Two kinds of bad number, and they break guards in opposite ways.**

- **`nan` is `False` against every ordered comparison**, so nothing refuses it: not `< 0`, not
  `> ceiling`, not `max(0.0, floor - nan)`. It reached the limit (`--out-of-cage-ago nan`:
  400 rewarded trials, clean summary, no duration limit — that flag became
  `--out-of-cage-at TIME` on 2026-09-20 and can no longer produce a NaN, but the guard stays
  for every other caller), the *ceiling* (a NaN `out_of_cage`
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

**Three readings for one mark since 2026-09-20.** `left_cage` takes the departure, the wall
clock and the session clock, all three *instants*, and checks the interval it computes from
the first two — the fifth blind spot below, closed where it lives rather than by enumerating
it. `Welfare.warn_within` is the one new *magnitude*: a NaN there makes
`remaining > warn_within` `False` forever, which would leave a welfare-facing line silently
off.

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

**Confirmed 2026-09-20, with a reason nobody here had — and the reason changes what the
number means.** Asked again, he answered:

> *"zero reward is fine. some trials will have a reward period, but they may not receive a
> juice reward. they may get an on-screen token reward that eventually becomes a real
> reward."*

So a zero-volume reward is **not an edge case being tolerated; it is a designed trial
outcome** — a reward period that pays a **token** rather than fluid. Two things follow.

- **The case for the existing behaviour is stronger than the one above.** A policy refusal on
  zero would not merely remove an operational convenience; it would make a class of trial the
  protocol intends impossible to express at all.
- **`fluid session: 0.00 mL` no longer implies something is wrong.** A session that has paid
  no fluid may be running exactly as designed, so nothing may treat that figure as a fault
  signal — and `supplement:` remains the number that matters, because a token is not fluid and
  the day's floor is still owed in millilitres until the token converts.

**Nothing in the task vocabulary models that token**, which is a gap in S1/S8 rather than a
defect on the welfare path — see open item 9.

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

**"Is this refusal earned?" should be a lookup, not a reading.** §5.2c earns the
`_finite`/`_magnitude` refusals as a class — two messages every numeric entry point reaches
— but `welfare.py` has **thirty-one** `raise` sites and `bounds.py` **five**, and a
reviewer sitting at `returned_to_cage`'s five would not find them there. Every one is below,
with the failure it was written against and where the argument lives.

> **The counts in this paragraph and in the closing one are measured, and they were not.**
> This said "the **nine** `_finite`/`_magnitude` refusals ... eighteen `raise` sites and
> `bounds.py` five" — nine reproduced neither the row count nor the `raise`-site count, and
> the eighteen went stale as soon as a refusal was added. The closing sentence was corrected
> on 2026-09-20 and this one was missed in the same pass, which is the whole argument for
> `tests/test_welfare.py::test_every_refusal_has_a_row_in_the_table_and_every_row_still_greps`
> — it counts the rows against the `raise` sites and **cannot see prose**. Prose figures here
> are checked by hand, so they are kept to the two that the table's own length states.

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
| `cannot have left its cage … seconds in the future` | A mark nothing could have taken. It caught a negative "how long ago" until 2026-09-20 and catches a clock time later than the wall clock since — **and it is the guard that makes "a bare time is today, never yesterday" safe**: `23:59` mistyped in the morning is refused rather than rolled back into a departure twenty-three hours old | §5.2 item 4 |
| `is recorded as out of its cage … ago, against a ceiling of` | A session starting at or past its own limit, and the gross data-entry error — a date typed a day early, a departure in the wrong half of the day. It *also* caught a wall clock handed to a session-relative parameter until the mark became a clock time (PI, 2026-09-20); that catch is gone and its loss is accounted for in §5.2 item 4 | §5.2 item 4 |
| `It was not confirmed by anyone, so it is refused rather than taken` | **A clock time cannot be refused for being implausible, so a person has to look at it** (PI, 2026-09-20). `08:45` typed for `18:45` is nine hours and sits inside a twelve-hour ceiling; no other refusal here will ever catch it. It is on the *marks* rather than only in `wlx run`'s prompt because `Session.left_cage`/`returned_to_cage` are console actions, and a guardrail written now and wired later is how `bounds`' fluid check went a week called by nothing (CLAUDE.md). A caller can lie to `confirmed`; it cannot forget it | §5.2 item 4 |
| `is at home, so there is no interval for a return to close` | Declaration and mark disagreeing, on the closing side | S13 §4.0 |
| `is not recorded as having left its cage, so a return closes nothing` | A session marked only at the end has no interval at all | §5.2 item 4 |
| `is already recorded as back in its cage at` *(in `returned_to_cage`)* | A second return moves a closed interval, and the shorter one silently wins | §5.2 item 4 |
| `is recorded as head-fixed at … and not released, so it cannot also be in its cage` | **The freeze.** A return marked mid-session froze the clock at whatever it read, so `must_stop` answered `None` for the rest of a session that reported itself fully marked | §5.2 item 4 |
| `cannot be back in its cage … seconds in the future` | **The departure's future refusal, on the closing mark** (PI, 2026-09-20, ruling 4). Once the return is a clock time it can be typed later than the clock the session is reading, which is a mark nothing could have taken — and it would stretch the interval rather than shorten it, so nothing downstream would complain | §5.2 item 4 |
| `cannot be back in its cage at … having left it at` | A return before the departure gave a **negative** duration, which is under every ceiling there is | §5.2 item 4 |
| `cannot be back in its cage before it was released from head-fixation at` | **The restraint record as a cross-check, not only a record** (review, 2026-09-20). Both marks present, both orderings individually legal, and the whole thing inside the thirty-minute band so nothing prompts: a return typed one second after a departure 25 minutes old, on a session head-fixed at 60 s and released at 1,400 s, gave `out_of_cage_seconds` of **1.0** beside `chair_seconds` of **1,340** — an impossible pair accepted in silence, under-reporting the exact interval ruling 4 exists to count | §5.2 item 4 |
| `is not recorded as out of its cage, so the session's one duration limit has no start` | **The absence of a mark must never disable a limit.** An unmarked rig session is indistinguishable from a cage-side one to anything that answers zero | §5.2 item 4 |
| `A duration that runs backwards` | Arithmetic producing an unchecked value from checked marks — a `now` in a base the mark was not taken in | §5.2c |
| `out of the cage while the restraint record reads` | **The same impossibility by the route no mark refuses.** `head_fixed` has deliberately no ordering check against the departure — a console may take the two marks in either order — so a fixation marked *before* the animal left its cage is wrong only in the pair it forms. This is that pair, checked where the number is read rather than where a mark is taken, which is this file's standing rule for a computed value | §5.2c; §5.2 item 4 |
| `is already recorded as back in its cage at …, so this session's interval is closed` | The closed-clock hole reached *before* the loop rather than during it | §5.2 item 4 |
| `is not recorded as head-fixed, so the session would carry no record of restraint` | A rig session with no `HEAD_FIXED` in the stream has no durable record of restraint | §5.2 |
| `is already recorded as head-fixed at` | Two restraint clocks, and the shorter one would silently win | §5.2 |
| `is not recorded as head-fixed, so there is nothing to release` | **The guard added on 2026-09-20 stopped one check short.** It asked which deployment this was and not whether there was anything to release, so a `RIG_FIXED` session never fixed accepted the release: `released_at` set, a 4129 strobed into a stream with no 4128, `chair_seconds` then answering `0.00` for it, and `returned_to_cage`'s "fixed and not released" check blind to it because `fixed_at` was still `None` | §5.2 item 4 |
| `cannot have been released at … having been head-fixed at` | A release before the fixation. `returned_to_cage` refused a backwards interval from the day it was written and the restraint clock had no equivalent, so `head_fixed(500)` and `head_released(100)` were both accepted | §5.2 item 4 |
| `the restraint clock for subject … reads` | **The computed duration, not only the marks** — `out_of_cage_seconds`' rule, which `chair_seconds` did not have. It guarded `now`, which is not the quantity, so a backwards restraint interval reached the wire and rendered `chair: -1:53:20`. It is also the only thing that makes the entry-point enumeration's exemption for `fixed_at`/`released_at` true | §5.2c |
| `which takes no head-fixation marks, so the animal cannot be recorded as fixed` | **A deployment recording restraint it declared it does not mark.** Accepted silently until 2026-09-20: a cage-side session could be recorded as head-fixed and nothing disagreed. Without it, `chair_seconds` answering `None` for the two kinds that take no marks would be *discarding* a measurement somebody took rather than reporting one nobody could | §5.2 item 4 |
| `which takes no head-fixation marks, so the animal cannot be recorded as released` | **The closing half of the same record.** `taskd.Session.head_released` strobes `HEAD_RELEASED`, so guarding only the opening mark left a console action able to put a 4129 in a stream that never carried a 4128 — a restraint record for restraint nothing marked. Found by asking what the documented claim *"no stream carries a HEAD_RELEASED with no HEAD_FIXED before it"* actually depended on: `run()`, and nothing else | §5.2 item 4 |
| `was amended with no reason given, so it is refused rather than recorded blank` | **A blank reason looks like an answer.** The PI asked for a reason on 2026-09-20 precisely so that a departure time somebody changed can be explained months later; a row recording the change and not the cause answers nothing it would be read for, and is worse than the absence of a row because it appears to | §5.2 item 4 |
| `was amended by nobody, so it is refused` | **An anonymous change to the clock that bounds a session.** `--as WHO` is required for a console write because a forgeable or invented actor is worse than none, and this moves the one quantity `must_stop` reads. It is in `welfare` rather than in `cli` so that the console action P4d-2 adds cannot reach the record around it | §5.2 item 4 |
| `is at home, so there is no out-of-cage clock to read against the wall` | **P4d-2a.** `now_from_wall` is the one mapping from the wall clock onto the session clock, through the departure; a cage-side session has no departure and therefore no interval for a wall instant to fall inside | §5.2 item 4 |
| `is not recorded as having left its cage, so the wall clock has no departure to be read through` | **The same method, the rig side.** A session with no `left_cage` anchor has nothing for `wall_now` to be mapped through — the same absence `out_of_cage_seconds` refuses, read where the wall clock is the one asking | §5.2 item 4 |

**Thirty-six refusals. Two rows are the §5.2c guards** — `is not a real number` and
`cannot be negative`, which every numeric entry point reaches — **and thirty-four are
structural.** (This said "nine of them are the two guards"; that figure counted neither rows
nor `raise` sites and could not be reproduced from either, so it is replaced with two that
`tests/test_welfare.py` checks.) Every message is kept verbatim in the code — they are what an
operator reads — and this table is the index into why each exists.

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

**Finding, 2026-09-20: none of that exists, and the PI's zero-reward reason is what surfaced
it.** Recorded here as a finding rather than as work, and **not designed** — it is a task-layer
gap, for a task-layer session. Read from source the same day:

- `task.py`'s action vocabulary is `Show`, `Hide`, `Update`, `Score`, `Custom`, `Mark`,
  `Reward`. **`Reward` means fluid**: it names an entry in the bounded config and reaches
  `welfare.Rig.reward` → `Welfare.deliver` → the pump.
- S1 §2.3 lists `Token(+1 / -1)` and `SetPersistent(...)` in the vocabulary. **Neither is
  implemented**, and no cross-trial persistent state exists anywhere in `wl_expcontroller` —
  `grep -rn "Token\|SetPersistent\|persistent" wl_expcontroller/` returns nothing.
- So a trial that has a reward period and pays a **token** rather than fluid (§5.2c, the PI's
  own description) cannot be expressed. The paragraph above describes a conversion bound for a
  mechanism that has no representation to bound.

**What is missing, stated so a task-layer session can scope it without re-deriving it:**

1. **A persistent count** that survives across trials within a session, is declared the way a
   parameter is, and appears in every per-trial snapshot — otherwise a token balance is exactly
   the "pointer to the config" failure §3.3 exists to prevent, one level up.
2. **A conversion rule**: when a balance becomes fluid, who triggers it, and how it passes
   through `welfare.deliver` so the day's accounting sees it. It must be *one* route to the
   pump; a second would make `Rig` stop being the one-file answer to "can anything deliver
   reward without the accounting seeing it".
3. **What the recording sees when a token is paid rather than fluid.** A `Reward` action today
   produces a commanded volume and, on a rig, a delivered-line pulse the sync box captures. A
   token produces neither, so a trial that paid one is indistinguishable in the record from a
   trial that paid nothing — which is the question S2 and `wl-preproc` would have to answer,
   and it is an event-code question before it is a schema one.

**This is not a welfare-path defect and nothing here is blocked on it.** Zero-volume reward is
already correct, already allowed and already visible (§5.2c); what is missing is a vocabulary
for the thing the zero *means*.

---

## 6. Restart and resume

| Question | Answer |
|---|---|
| Is the log lost? | No — streamed |
| Is fluid lost? | No — reconstructed from the delivered line; the session pays on regardless (§5.2 item 3) |
| Is the duration clock lost? | **Yes, and by ruling rather than by omission** (PI, 2026-09-20, closing open item 8). The out-of-cage marks are operator-entered and get no event code, so a restart cannot reconstruct them and a person re-supplies the departure — by typing the same clock time they typed the first time, which is exactly as good as the original |
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
| 8 | ~~**The out-of-cage marks have no event code** (§5.2 item 4). The clock that now bounds a session has no hardware record, so a restart cannot reconstruct it — the gap `HEAD_FIXED` closed for chair time. Two codes in 4096–32767 would close it; allocation is S2's and `wl-preproc`'s under ADR-0007~~ **Answered 2026-09-20 (PI): no codes.** The marks are **operator-entered rather than measured**, so a hardware timestamp would add precision to a number that never had it; our own log and the session directory already carry them. The consequence he accepted: a restart re-asks a person for the departure time (§6). No longer an ask on S2 or `wl-preproc` | ✔ |
| 3 | ~~Default re-queue policy~~ **Answered: fixation break re-queued at end of block, wrong choice not, overridable per block** | — |
| 4 | ~~Session duration from first reward or first trial~~ ~~**Answered: chair time, from head-fixation.**~~ **Re-answered 2026-09-19: out of cage to back in cage, twelve hours** (§5.2 item 4). Remaining: whether a hardware head-fix signal is ever worth adding beside the console action — still open, and now about a *recorded* quantity rather than a bounding one | welfare review |
| 5 | Who plans blocks when wl.works is unreachable | S3 §7's quarantine risk |
| 9 | **A token that accumulates across trials and later converts to fluid has no representation** (new, 2026-09-20). The PI's reason for allowing zero reward — *"they may get an on-screen token reward that eventually becomes a real reward"* — describes a designed trial outcome the task vocabulary cannot express: `task.Reward` means fluid, and S1 §2.3's `Token`/`SetPersistent` are specified and unimplemented. Three things are missing — a persistent count, a conversion rule, and what the recording sees when a token rather than fluid is paid. §5.3 has the detail. **Deliberately not designed here**; it is S1's vocabulary and S2's codes before it is S8's accounting | S1 §10 item 3; a task-layer session |
