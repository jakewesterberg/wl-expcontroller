# Next session — wl-expcontroller

**State at handoff:** **438 tests passing** (with `.[dev,contract,console]` installed —
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

**This review gained a second, smaller item on 2026-09-19.** `p4d1-console-link` (built
on top of this branch) gives `wlx console --set reward_correct=...` as the first
*person-invocable* path that moves a reward limit — `Session.set` staging straight
into `bounds.set` and its ceiling. `cli.py` and `link.py` do not become
welfare-critical by `architecture.md`'s definition — the limit is still enforced in
`bounds.py` alone, and the welfare-critical surface stays exactly two files — but the
*capability* is new and welfare-facing, and CLAUDE.md is explicit that anything
touching reward delivery amounts or limits is reviewed by a human lab member before
merge. It merges into the same lineage this section already asks a person to read, so
it goes to the same reviewer rather than opening a second thread. `git diff
p4b-session-management..p4d1-console-link -- wl_expcontroller/cli.py
wl_expcontroller/link.py wl_expcontroller/taskd.py` is the whole of it (ruling R23,
`.superpowers/sdd/2026-09-19-p4d1-console-link/progress.md`).

**And that reviewer now has one question to answer, not only code to read** — found by
the whole-branch review on 2026-09-19 and deliberately not decided by a session:

> **When a console lowers or raises a reward volume, should it take effect on the trial
> that is about to run, or on the one after?**
>
> It currently takes effect **immediately**. `Session.set` calls `bounds.set`
> synchronously as the command is drained, and `welfare.Rig.deliver` reads
> `bounds.value(ref)` when it opens the valve, so the trial that runs later in that same
> pass is already at the new volume — measured: a queued
> `SetParameter(reward_correct, 0.30)` against a starting 0.15 has trial 0 commanding
> 0.30 mL. An *ordinary* task parameter does the opposite and waits for the next pass.
>
> The ceiling is enforced either way and nothing lands mid-trial, so no animal gets more
> than its limit. What is wrong is the *record*: the `PARAM_CHANGED` strobe and the
> `parameter_changes.jsonl` row are written on the next pass, so **for a welfare-bounded
> name the record is off by one trial**, and anyone reconciling commanded fluid offline
> will assign one trial's delivery to the wrong value.
>
> Deferring means an operator who has just lowered a volume watches one more trial go
> out at the old one. Keeping it means the record needs a second strobe point, or S9a
> §8.1 becomes the contract and offline tooling has to know it. Both are expensive in
> the way CLAUDE.md says to ask about rather than file — one edits the call path into a
> welfare-critical module, the other changes the spec — so this is a question for the
> PI, marked in the source at `taskd.Session.set` and in S9a §8.1. **Every document now
> describes the behavior truthfully; only the decision is open.**

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
| PI | **A photometer measurement of the panel** | every chromatic task (P19); `tasks/visual_search.py` is what waits |
| PI | **A pump calibration: millilitres per second of open time** — protocol **V10**, `docs/validation.md` | real reward delivery (new 2026-09-06) |
| PI | **The real bounded-config numbers** — reward volume per delivery, the daily fluid **floor**, chair time, trial cap. Asked 2026-09-06; answer was *keep the placeholder until there are animals* | every session that is not a simulation |
| PI | **Is a runaway-fluid *fault* limit wanted?** Not a ration — a sanity bound catching a software fault delivering litres, reported as a fault. Nothing enforces one today, which is correct under the protocol and leaves a bug unbounded | welfare review; S8 open item 6 |
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

**Three things this slice found and deliberately left open, for whoever picks up
P4d-2 or later:**

1. **A pump fault publishes nothing.** `welfare.deliver` raises, `Rig` deliberately
   does not swallow it (P21's shape — never absorb a broken rig), and the exception
   propagates past `Session.run`'s `finally` with no final `Telemetry` frame and no
   `stopped_because`. A console watching a rig break, unattended, cage-side, sees only
   silence. What a console should show when the rig itself is faulty is a design
   question for this package, not a bolt-on inside P4d-1.
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
3. **`wlx console --set reward_correct=...` is now a person-invocable path to a
   reward limit** — recorded in §1 above, beside the `bounds.py`/`welfare.py` review
   already waiting.

**Do not skip ahead to hardware work to feel productive.** Everything on that side is
blocked on a card, a panel, a photometer or a pump measurement, and none of the four is
ours to hurry.
