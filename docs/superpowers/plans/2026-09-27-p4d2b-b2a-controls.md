# P4d-2b slice b2a — Controls From the Box: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Built on b1** (`p4d2b-b1-read-only-console`, approved by the PI on 2026-09-27 to fast-forward onto `main` once its gate and CI are clean) **plus the spec commit** (`e426de2`, "Design slice b2: controls from the box (b2a), and remote sign-in's decisions (b2b)"). b1 landed on `main` the same day, and branch `p4d2b-b2a-controls` was rebased onto `main` at `a7493e4` (the CI split, the `test_cli.py` minute-boundary fix, and the P9/P10 docs); the plan was then re-applied there (below).
>
> **Every task's code was built and run before this plan was written**, in a scratch copy of `e426de2` (`git archive HEAD`, with the `wl-preproc` checkout linked beside it), task by task, each task's tests red first and then green, the whole suite after each task. The code in every step below is that code, and the steps are exact replacements: each "replace" block's old text is unique in its file at the moment the step is applied, in the order given, and is whole lines — except a one-line block in Task 15 that sits inside a longer line of a document (a table row), where only that text is replaced. An "Append to" block goes at the end of the file as it stands. A script then re-applied every step of this plan, as written, to a fresh copy of `e426de2`, ran the suite after each task and checked the counts stated here. **1092 passed** at `e426de2`; **1330 passed** after the measurement task (Task 13 then, Task 14 since the amendment below). **Re-applied after the rebase** (2026-09-27), step by step to a copy of `37c2f1e` — `main` at `a7493e4` plus this branch's spec and plan — with every RED and GREEN run where the plan puts it, each commit block executed, and the documents task's anchors (Task 14 then, Task 15 now) moved to `main`'s newer `CHECKPOINT.md` and `next-session.md`: **1124 passed** there, **1362 passed** after the measurement task. Every count is 32 above the first run's: `main`'s new `tests/test_mutation_gate.py` tests. **Rebased again** (2026-09-28) onto `334f6db`, `main`'s fix to `--changed-only` selection, which adds three tests: **1127 passed** there, and every count below through Task 12 is 3 above the `37c2f1e` run's. Nothing else this plan touches moved — no step edits `tools/mutation_gate.py`, and each of the documents task's replace blocks still matches its file exactly once, applied in order (checked by script, 2026-09-28).
>
> **Amended 2026-09-28, at the PI's review of this plan** (Plan decision 16): he approved it with one change, "I want to be able to give manual rewards during pause", and chose "Same as a correct trial" for how much one press gives. **Task 13, a manual reward during a pause, is new; the old Tasks 13, 14 and 15 are now 14, 15 and 16**, and every reference in this plan says the new number, except where a history note says which it was. Task 13 was built first, test-first, in a scratch copy of this branch's tip with Tasks 1–12 applied — its tests red, then green — and each function it adds or changes was mutation-checked there (Task 13 Step 5). The whole amended plan was then re-applied, as written, to a fresh `git archive` of the branch tip: **1361 passed** after Task 12 as before, 1388 after Task 13 and 1392 after Task 14, every stated count matched, and every one of Task 15's replace blocks still matches its file exactly once, applied in order.
>
> **Also looked at in a real browser, in the scratch copy** (Playwright, 2026-09-27): a simulated `wlx run --link PUB,REP,MARK` and `wlx serve`, the page on `127.0.0.1`. A refused and a cleared name prompt sent nothing and said why; a name was kept in `localStorage`; **P** paused (pill *paused · since HH:MM:SS*, button *resume (P)*); **M** signalled a mark while paused, the note box opened with focus, an **M** typed into it stayed text, and Enter attached the note (feed: *mark 1 stamped while paused, before trial 3511* and *mark 1: "reward line bubble" · jake (box, unverified)*); three clicks on an arrow sent one change, 0.30 → 0.45, staged and then applied on resume; a scheduled stop after N trials showed on the strip and its cancel removed it; `25:00` was refused with its sentence; the stop's confirm step opened and closed; stop ended the session. `controls.jsonl` held every row, the note's with its three instants and two gaps. That look came before four small amendments the suite covers and the browser has not seen — the note box no longer shows the mark's random number, a schedule that fired is spent, a console's stop is a record row, and one test was made deterministic — and before Task 13's manual reward, which no browser has seen either; so Task 16 Step 4 repeats it on the branch, in full, with the reward button added.
>
> **Swept in the scratch copy** (`tools/mutate.py --all --returns None`, 2026-09-27), every module this plan changes — `link`, `taskd`, `serve`, `web`, `cli`, `record`, `run`, `health` and `tools/measure_mark_check.py`: 241 functions, each read by its line. 235 were `N failed` naming tests; `run`'s `display` is inert, as it was before this slice; one `SURVIVED` and five `timed out`. Four defects in this plan's tests were found by that sweep and the round before it, each fixed in its owning task and re-run to `N failed`: `measure_mark_check.main` `SURVIVED` (Task 14 now tests it), and three missing bounds that printed `caught … timed out` — `taskd.Session._command` (Task 12's `CONTROL_TRIAL_BUDGET`; now 68 failed), `serve.Outbox._answer` (Task 11's `_submitted`; 20 failed) and `taskd.Session._hold` (Task 5's `PASS_BUDGET`; 12 failed). The other four `timed out` lines — `link.mark_signal`, `taskd.Session.controls`, `serve.parse_command` and `web._wrong` — all ran in the same five minutes, while the machine's load average stood above 300 from other work; each, re-run alone, was `N failed` in about a minute (15, 165, 45 and 7). Task 13's functions, added on 2026-09-28, were swept on their own (Task 13 Step 5). Task 16 Step 2 sweeps again on the executed branch: the gate for `wl_expcontroller/`, and `tools/measure_mark_check.py` by hand, since no gate mode reaches `tools/`.

**Goal:** A person at the rig PC works a running session from the browser console: sets parameters with arrows and inputs, pauses and resumes, marks a moment that is stamped in the frame it reaches the rig, schedules a stop by clock time, trials or fluid, gives a manual reward while paused (the PI's 2026-09-28 amendment), and stops — every control recorded with who did it and when, every write refused anywhere but the box, and the page told the truth about whether the rig got it.

**Architecture:** Commands on the link grow from `SetParameter | Stop` to eight kinds, each carrying `by` and each checked where it is decoded — M8 first, so a malformed setting is a refusal and never the end of a session. `taskd` holds a pause at the trial boundary (a housekeeping loop that still drains, publishes, and asks `welfare.must_stop`), gives a person's manual reward only while it holds one, holds a scheduled stop, and records every control in a new `controls.jsonl`. A mark is two things: an eight-byte signal on a third loopback socket that the trial loop checks once per frame — `getsockopt(EVENTS)` and, only when one waits, `recv_into` a preallocated buffer — strobing `OPERATOR_MARK` in that frame; and a note, an ordinary `Mark` command, joined to its stamp by the signal's number. Telemetry goes to schema 8 (`paused_at`, `scheduled_stop`, `controls`, `controls_dropped`). `wlx serve` takes `POST /commands` under spec §2's four checks, answers every request only when its `Host` names the console, and owns each ZMQ socket on one thread: a read-only telemetry thread, a command thread whose REQ socket waits for the rig's acknowledgment and resets on a timeout, and a mark thread that sends the signal ahead of every command. The page renders the controls in Python, as every pane is, and its script grows to send them.

**Tech Stack:** Python 3.11–3.13; pyzmq (floor raised to 26.4 for `Socket.recv_into`) and msgpack through `link.py`, imported lazily; stdlib `http.server`, `threading`, `queue`, `socket`, `json`, `tracemalloc` (the measurement); pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` — §2 and all of §5 (§5.0–§5.7) bind this slice; §3, §4 and §6 are context. Read the spec first; this plan argues from it.

## Plan decisions

Spec §5 left these to the plan. Each is taken here, with its reason; the code is in the task named.

1. **The mark signal: a third loopback socket, checked once per frame through `EVENTS`, read with `recv_into`** (spec §5.1's proposal, kept; Tasks 3 and 6). `taskd` binds a PULL socket, `wlx serve` connects a PUSH. `ZmqLink.mark_signal()` is `getsockopt(EVENTS) & POLLIN` on plain `int` constants read once in `__init__`, and only when a message waits, `recv_into(self._mark_buffer, flags=DONTWAIT)` into an eight-byte `bytearray` the link allocated once. **Verified against the installed source**, pyzmq 27.2.0 in this repository's venv, read 2026-09-27: `zmq/sugar/socket.py:376` makes `getsockopt` `SocketBase.get`; `zmq/backend/cython/_zmq.py:853` is `Socket.get`, which for an `int` option calls `zmq_getsockopt` into a C `int` and returns it; `_zmq.py:1264` is `Socket.recv_into`, "storing the data into a buffer rather than allocating a new Frame", `.. versionadded:: 26.4`, returning "the size of the received frame" even past the buffer's size, which is how an oversize signal is told from a mark. **Allocation, checked** (scratchpad `tracemalloc` probes, 2026-09-27): with nothing waiting, the check's peak over 100,000 calls was indistinguishable from an empty function's, and nothing was left held; the `zmq.EVENTS & zmq.POLLIN` form of the same check left 656 bytes held, because `&` on a `PollEvent` builds a flag through the enum machinery — hence the plain `int`s. `test_the_per_frame_check_keeps_nothing_it_allocates` pins "nothing held"; transient allocation is not pinned by a test, because `tracemalloc`'s peak moved by ±32 bytes run to run in the probe. **Cost: it is not free, and this plan does not say how much it costs** (CLAUDE.md). In a scratchpad probe on a heavily loaded development machine (2026-09-27; not committed, and not a claim about this system), `getsockopt(EVENTS)` took tens of times as long as `getsockopt(LINGER)`, consistent with work inside libzmq on each call — libzmq's own source was not read, so which work is UNVERIFIED. The committed measurement is Task 14's. `tools/measure_mark_check.py` measures it (Task 14), its first result is committed, and its effect on real frames is V12 on a rig. The spec's rule stands: if it disturbs frames, it goes back to the PI (Task 16 Step 6 asks). The alternative, if it must change: a listener thread in `taskd` that blocks on the PULL socket and appends to a `deque` the frame reads — a length test per frame, at the cost of a thread in the trial process and a mark's wake-up waiting on the GIL. Not built. **Where it runs**: `run_trial` gains one per-frame hook, `each_frame(frame)`, called first thing on every frame, the gaze-lost frames included; `taskd` passes the check. Between trials it runs once per boundary (`Session._check_marks`); while paused, the housekeeping wait is `Link.idle`, a `zmq.Poller` over the REP and PULL sockets that returns the moment a mark or a command arrives, so a mark is stamped then. **One signal per frame**: a second waiting is read on the next frame, and its stamp names that frame. A signal that is not eight bytes naming a mark is counted in the frame (one integer, no list grows mid-trial) and refused once at the next `drain`.

2. **`--link PUB,REP[,MARK]`, for `wlx run` and `wlx serve` alike** (Task 3, Task 11). The operator gives both processes the same string, as b1 already asks for two endpoints. Two endpoints still work as they did in b1: `taskd` binds no mark socket, and `wlx serve` greys the mark control with a sentence naming the flag (`web.NO_MARK_ENDPOINT`) and answers a mark *not delivered*. The mark endpoint gets the other two's rule: loopback unless `--link-allow-remote`.

3. **A mark's number is random, not counted** (Task 11). `wlx serve` draws each mark's number with `secrets.randbelow(2**53 - 1) + 1`. A counter restarts with `wlx serve` — which spec §2 says changes nothing in `taskd` — and two marks in one session would then share a number. The bound is `2**53 - 1`, JavaScript's `Number.MAX_SAFE_INTEGER`, because the page sends the number back with the note and a number its JSON had rounded would join nothing. The signal carries it as eight bytes, big-endian (`link.MARK_BYTES`). The session numbers its marks 1, 2, 3 in the order it stamps them (`controls.jsonl`'s `number`), and that is what the feed shows.

4. **A mark is recorded in two rows, and the first never waits for the second** (Task 6). The stamp — `kind: mark`, the signal's number, the session's number, the trial and frame (`null` between trials and while paused), whether it was strobed, and `at`, the stamp's instant on the session's anchored clock — is written at the boundary after its frame, whether or not a note ever comes: a page closed before Enter must not lose the mark. The note arrives as a `Mark` command (Enter attaches the typed text; Esc sends it empty) and is written as `kind: note`, joined by number, with all three instants — `pressed_at` (the browser's clock), `received_at` (`wlx serve`'s host clock), `stamped_at` (the session's anchored clock) — and both gaps, `received_after_pressed_s` and `stamped_after_received_s`. The gaps are across two clocks each and are recorded as the clocks read, never corrected (spec §5.1: "recorded, never hidden"); they are session data, not a claim about this system's latency. A note for a mark the session never stamped says so; a note after `wlx serve` restarted carries its instants as `null`, never guessed. A mark is never refused, since it has already been pressed: with no `OPERATOR_MARK` code in the allocation it is stamped unstrobed and the feed says so.

5. **Pause holds at the boundary, in `Session._hold`** (Task 5). Once per housekeeping pass (`taskd.PAUSE_HOUSEKEEPING_S = 0.5`, a responsiveness choice and not a measurement; the wait ends early on any command or mark) it drains commands, publishes a frame, and asks `Session._ends` — the one place the loop asks `welfare.must_stop`, between trials and while paused alike, so the limit ends a paused session "exactly as between trials". `welfare` is called unchanged. **The task rewards nothing because it cannot**: its reward is a trial's action, and no trial runs. A person may give one correct-trial reward per press, and only while the session is held (Plan decision 16, Task 13). **The display shows the task's background because nothing is drawn**: a stimulus is shown only by a trial. No display process exists yet to be told so (S4's is not built; `docs/CHECKPOINT.md`: "a frame on screen" is blocked on a panel), so this is structural today, and V12 item 3 is how a rig proves it. A pause is **refused, with a sentence**, when a `Stop` was drained ahead of it (Review Focus 3), when the session is already paused (a double click), or when the allocation lacks `PAUSE` or `RESUME` — a gap in the recording needs both ends. Settings staged while paused apply at the top of the loop's next pass, before the next trial. Telemetry: `paused_at`, the instant on the session's anchored clock, `None` while running; a session stopped while paused keeps it, and the page shows how it ended, not *paused*.

6. **A scheduled stop is fixed when it is accepted** (Task 7). `ScheduleStop(kind, value, by)`, kinds `clock` (`"HH:MM"`), `trials` (a whole number, at least one) and `fluid` (mL above zero); `link.check_schedule` is the one rule, asked where the wire decodes it and again by `taskd`. **Clock**: `taskd._next_occurrence(hhmm, wall)` — the first instant strictly after `wall = Session.wall_now()`, the session's anchored clock, at which the host's local clock reads `hhmm`; `time.mktime` with `tm_isdst=-1` decides daylight saving and rolls the day. **Exactly now is past**, so both name tomorrow's (Review Focus 4), and the schedule's words then carry the date — *at 22:13 on 2023-11-15* — on the feed and the strip, so a slip of the hour is read rather than waited for. **Trials**: the target is the trial count at acceptance plus N, shown as *after trial 48*. **Fluid**: the target is mL compared with `welfare.session_total()`, read and never asked to decide. One at a time: a new one replaces the old and says what it replaced; cancel with nothing scheduled is refused. `_ends` checks it after `must_stop`, so a session that reached its limit ends as `limit`; when due it ends the session like the stop button, `stop_kind` `operator`, *scheduled stop (after trial 48) set by NAME*, writes a `scheduled_stop` row, and the schedule is spent.

7. **The record: `controls.jsonl`, one row per control** (Tasks 5–7). `SessionRecord.control(kind, by, at, trial_index, **detail)`, beside `refusal` and `parameter_change` and in their shape: `at` is the session's anchored clock, written also as local clock time with its zone (`record._local`); `trial_index` is the trial it happened in or, between trials, the one about to run. Kinds: `stop` (a console's stop, which until now was on the record nowhere but in the stop reason's telemetry and at the terminal), `pause`, `resume` (with `paused_s`), `mark`, `note`, `schedule`, `cancel`, `scheduled_stop`, and — since the 2026-09-28 amendment — `reward` (Task 13). **Its own file**, for `welfare_notes.jsonl`'s reason, and **uncapped**, unlike `refusals.jsonl`: each row is something that happened, made by the box's own console, and marks are bounded besides at one per frame. An applied setting is already a row in `parameter_changes.jsonl` and is not repeated here; it goes on the feed only.

8. **Three framework event names, allocated as the others are** (Task 5). `tasks/allocation.py` gains `4131: "PAUSE"`, `4132: "RESUME"`, `4133: "OPERATOR_MARK"`, after `4130: "PARAM_CHANGED"`: the spec's `pause`, `resume` and `operator_mark`, spelled as every framework name there is. `codes.py`'s docstring confines this package to 4096–32767 while ADR-0007's `TaskEvent` range is being moved, and wl-exptasks owns the final numbering (spec §5.6). `taskd` looks them up through `Session._code`, which answers `None` for a name the allocation lacks rather than raising out of the loop, and each control says what it does then (decisions 4 and 5). **A fourth, `4134: "MANUAL_REWARD"`, joined on 2026-09-28** (Plan decision 16, Task 13), allocated the same way.

9. **Telemetry schema 8** (Task 8). After `recent_outcomes`: `paused_at: float | None`; `scheduled_stop: ScheduledStop | None`, where `ScheduledStop(kind, target, by, said)` carries the rig's own words so every console shows the same sentence the stop reason uses; `controls: tuple` of `Control(kind, by, at, said)`, the last `link.CONTROL_HISTORY` (50) control events, oldest first; and `controls_dropped: int`, so a cap never reads as a quiet session. `Control` kinds include `set`, a staged setting applied, because the feed lists every setting change (spec §5.2) and a staged row leaves `Telemetry.staged` when it applies. A schema-7 reader refuses schema 8 by name (`SchemaMismatch`), and schema 8 refuses 7.

10. **`wlx serve`'s writes** (Task 4, Task 11). Three threads, each owning its socket (spec §2): the telemetry thread builds a **read-only** `ZmqConsole` (its REQ endpoint `None`); the **command thread** (an `Outbox`) builds `ZmqCommands`, a REQ socket with `IMMEDIATE`, and `deliver` returns only when `taskd` acknowledged receipt — *sent* — or raises `NotDelivered`: at once when no rig is connected (`IMMEDIATE` queues only to a completed connection; `CONNECT_TIMEOUT_S = 1.0` covers a socket still connecting), or after `REPLY_TIMEOUT_S = 15.0` with no reply, **after which the socket is reset** — closed, and a new one connected — because a REQ socket cannot send again unanswered. The timeout outlasts a trial, since `taskd` reads commands only at boundaries; a command that timed out was handed over and not acknowledged, and may still apply at the rig's next boundary, so its sentence says so rather than calling it lost. The **mark thread** builds `ZmqMarks`, a PUSH socket with `IMMEDIATE`, so a mark never waits behind a command awaiting its acknowledgment. Each `Outbox` has a bounded queue (`COMMAND_QUEUE_DEPTH = 4`, `MARK_QUEUE_DEPTH = 8`); a full one answers *busy* at once, and every queued job is answered, by its work or by *not delivered: wlx serve is closing*. All of these numbers are housekeeping, not measurements. **`POST /commands`** takes one JSON object: `{"kind": "set", "name", "value"}`, `{"kind": "stop" | "pause" | "resume" | "cancel" | "reward"}` (`reward` since Task 13), `{"kind": "schedule"}` with exactly one of `"at": "HH:MM"`, `"trials": N`, `"ml": X`, `{"kind": "mark", "pressed_at"}` and `{"kind": "note", "mark", "note"}`, each with `"by"`, the person's name (1–64 printable characters), recorded as `NAME (box, unverified)`. A field a kind does not take is refused, not ignored. `serve.parse_command` validates before anything is queued, with the wire's own rules (`link._setting`, `link.check_schedule`). Answers: `200` *sent* or *signaled* (a mark, with its number); `503` *busy*; `504` *not delivered*, or, for a manual reward handed over and not acknowledged, *unknown* (Task 13); `400` *refused* with the sentence (a body that is not a command, or longer than `BODY_LIMIT = 4096` bytes — `413`); `403` with spec §2's sentence when any of the four checks fails.

11. **Every request's `Host`** (Task 11). `do_GET`, `do_POST` and every refused method answer `421` with a JSON body, and no page, unless `host_name(Host)` is in the console's names: `serve.LOOPBACK_NAMES` (`localhost`, `127.0.0.1`, `::1`), `socket.gethostname()` and `socket.getfqdn()`, every address `socket.getaddrinfo` gives for those, and each `--allow-host NAME` (repeatable) — lowercased, computed once when `wlx serve` starts (`serve.box_names`). A lookup that fails adds nothing: loopback and `--allow-host` still work, and a LAN viewer's refusal names the flag. A request so malformed that the stdlib answers it before `do_*` (`send_error`) is answered as in b1: a fixed JSON body that echoes nothing. **A write** also needs `Host` to name loopback, not merely the box: spec §2's second check. `View.can_write` is §2's first two checks, per request, and greys the page's controls.

12. **The page** (Task 10). The controls are rendered in Python like every pane: a `controls` fragment (pause *or* resume by the session's state — never a toggle, so a double click sends the same command twice and the rig refuses the second — mark, stop, and since Task 13 *give reward*, live only while paused), each parameter card's input and ▲▼ arrows (step by unit, the mockup's rule: mL 0.01, s 0.05, deg 0.1, else 0.01; a categorical card takes a word and has no arrows), the last refusal of that parameter on its card as *last refused: …* (a refusal carries no time, so *last* is the honest word), and a fifth strip cell while a schedule is held (*stop at 14:30 · set by jake*, with *cancel*). What no frame changes — the name, the last command's answer, the stop confirm, the mark's note box, the scheduled-stop form — is static in `page()`, so a frame never replaces what a person is typing. The script grows as spec §5.2 says and still renders nothing: it posts JSON with `fetch`, debounces the arrows (`web.DEBOUNCE_MS = 600`, the mockup's, housekeeping), holds a new parameters fragment while an input has focus or a change is pending, handles **P** and **M** outside text boxes and never on a held key, and asks the name once, kept in `localStorage` inside `try`. A prompt refused or cleared sends nothing and says why (Review Focus's sixth case, below). **The Content-Security-Policy is unchanged**: `connect-src 'self'` already covers the `fetch`, and `form-action 'none'` refuses any form. `View.can_write` and `View.can_mark` default to `False`: a view that did not say may not write.

13. **Three `taskd` functions join the welfare-critical list** (Task 15). `Session._ends` is now the one place the loop asks `welfare.must_stop`, and where a scheduled stop — "after X mL" included — ends a session; `Session._hold` is where a paused session runs no trial and is still ended on the limit, and — since the PI's 2026-09-28 amendment — the only place a person's manual reward is given from; and `Session._manual_reward` (Task 13) delivers that reward. Spec §5.5's items 1 and 2 are about exactly these, so `architecture.md` lists them beside `bounds.py`, `welfare.py` and the `cli` functions. **Nothing already on the list changes**: `welfare.py`, `bounds.py`, and `cli.py`'s `_wall_clock_time`, `_clock_or_now`, `_settle_return`, `_settle_departure` and `main`'s `confirmed=` line are untouched, and `welfare.must_stop` is called as it was.

14. **M8 closes first, where the command is decoded** (Task 1). `link._setting`: a setting's value is a finite real number that is not a `bool` (returned as a `float`; `True` was accepted as `1.0`), or a word of at most `TEXT_LIMIT` characters for a categorical parameter; anything else is a `CommandRefused` naming the parameter and the sender, which `drain` turns into a `Refused` row the feed shows. `by` must be a non-empty string, for every kind. `Session.set` refuses a non-number for a ceiling and for a numeric parameter before `bounds._finite` could raise, and `Session._command` catches `TypeError` too, as the spec's backstop. **`bounds.py` is not touched.** One more hole on the same line was found and closed: a categorical parameter's word reached `_finite` too, and raised; `Session.set` now checks a categorical value against its choices alone.

15. **A test-only speedup** (Task 11). `tests/test_serve.py`'s `_served` runs `serve_forever(poll_interval=0.05)`: `shutdown()` otherwise waits up to half a second, and b2a adds dozens of handler tests that each serve once — run once more per function by the mutation sweep. In the scratch copy `test_serve.py` took 49 s before this and 19 s after, on one loaded machine: a wall-clock reading of the test suite, not a claim about this system.

16. **A manual reward during a pause** (PI, 2026-09-28; Task 13). He approved this plan with one change: "I want to be able to give manual rewards during pause." Asked how much one press gives, he chose **"Same as a correct trial"**: the task's current reward size, and nothing new set. The engineering calls below were stated to him the same day; the spec records them in §5.0–§5.7.
    - **Only while held** at the trial boundary (`Session._hold`, Task 5). `_hold` passes `held=True` to `Session._command` for the commands it drains, and `Session._manual_reward` gives a reward for no other. Pressed while trials run, in the same drain as a pause that has not held yet, after a `Stop` or a `Resume` ahead of it in the drain, or after the session has ended (`_command`'s post-loop refusal), a reward is refused with a plain sentence, nothing is given, and the session goes on. Any-time manual reward stays in slice b5 (spec §4.0).
    - **One press, one delivery of the bounded config's `reward_correct`** (`taskd.MANUAL_REWARD_ENTRY`), at the value it holds then — a size staged while paused applies at resume, so it is the next trial's, not this reward's — **through the path a task's reward takes**, `welfare.Rig.reward` → `Welfare.deliver`: charged before the valve opens and counted in `commanded`, `deliveries` and `last_delivery_wall_at`. A config with no `reward_correct` refuses the press, naming the entry; **no other entry ever stands in**. `welfare.py` and `bounds.py` are called, not edited. A pump fault is not caught, as `welfare.Rig` catches none for a task's reward: the session ends as a fault.
    - **Recorded like every control**: a `controls.jsonl` row (`SessionRecord.control`), kind `reward`, with `by`, `at` — the instant the reward was commanded, which is also the frame's `last_reward_at` — the trial index, `ml` and `entry`; and a framework code, **`4134: "MANUAL_REWARD"`**, allocated after 4131–4133 as Task 5 allocated them: in 4096–32767, the task-specific range `wl-preproc`'s `wl_preproc/contracts/events.py` gives to wl-exptasks and whose values its `decode_stream` reads as simple events (read 2026-09-28; wl-exptasks allocates nothing in code yet). It is strobed before the delivery, as `REWARD_COMMANDED` precedes a task's reward, so a recording tells a manual reward from a task's and from a panel press (S6 §4). An allocation without it refuses the press, as one without `PAUSE` or `RESUME` refuses a pause.
    - **It counts toward "stop after X mL", and `Session._ends` checks it** — unchanged, and asked by `_hold` after its drain, in the same pass that gave the reward and that asks the out-of-cage limit. So the session ends there as a scheduled stop, without waiting for a resume. Why `_ends` and not `_manual_reward`: `_ends` is the one place the loop asks the limit and then the schedule (Tasks 5 and 7), so the limit still wins a tie, and a second copy of the schedule's rule inside the reward would be the thing decision 13 put `_ends` on the welfare-critical list to prevent.
    - **No accidental doubles.** Nothing on the command path re-sends a command: `ZmqCommands.deliver` sends once and, on a reply timeout, closes the socket and raises (Task 4), and an `Outbox` runs each job's work once (Task 11). So no exemption is needed; a test on real sockets pins one reward command on the wire whatever the answer, so a retry added later cannot silently double a reward. A reward handed over and not acknowledged may have been given, so `ZmqCommands.deliver` raises it as `link.Unacknowledged`, a `NotDelivered`, and `wlx serve` answers `serve.REWARD_UNKNOWN` — *unknown*, check the fluid total before pressing again — never *not delivered*. Each accepted command is exactly one reward; `taskd` does not deduplicate. The page holds its button from the click until the answer or the failure, and a lost answer is *unknown* there too.
    - **The page**: *give reward* in the controls fragment, live only on a frame with `paused_at`, greyed with `web.REWARD_ONLY_PAUSED` while trials run and with the §2 sentence off the box; no key. While paused it is followed by the session's fluid total, the last reward given and the last press refused. Frames are still published while paused (`_hold`'s `publish()`), so the total moves on the next one. Pause stays *pause or resume*. `wlx console` stays render-only; it lists a `reward` control row like any other.
    - **Welfare-critical**: `Session._manual_reward` joins `_ends` and `_hold` on the list (decision 13; Global Constraints; Task 15 writes it into `architecture.md`).
    - **Remote (b2b)**: spec §5.7 records that it follows the PI's 2026-09-27 ruling for people signed in to wl-works — every b2 control, reward size included. b2b is not designed here.

## Global Constraints

- **Branch, not `main`.** Work on `p4d2b-b2a-controls` in its worktree. **This slice is welfare-critical** (CLAUDE.md; spec §5.5): the pause's limit check, a scheduled stop that can end a session ("after X mL" included), reward size set from the page, a manual reward during a pause (Plan decision 16), and M8. **It must not merge to `main` until the PI has approved Task 16 Step 6's items.** Push the branch; do not fast-forward `main`.
- **The code on disk wins over this plan's quotations.** Every "replace" block below was applied to `e426de2` in order and matched, and again, after the rebase onto `main`, to `37c2f1e`. If one does not match on disk, anchor on the named function and keep its meaning; never restore the quoted text.
- **Welfare-critical code is not edited**: `welfare.py`, `bounds.py`, and `cli.py`'s `_wall_clock_time`, `_clock_or_now`, `_settle_return`, `_settle_departure`, and `main`'s `session.left_cage(at=departure, confirmed=note is not None, ...)` line. `welfare.must_stop` and `welfare.session_total` are called, never changed. If a step seems to need any of them changed, stop and ask.
- **Three functions join the welfare-critical list, and their code requires human review before merge** (CLAUDE.md; Plan decisions 13 and 16): `taskd.Session._ends` (Tasks 5 and 7), `taskd.Session._hold` (Tasks 5 and 13) and `taskd.Session._manual_reward` (Task 13), which delivers fluid. Keep them small; Task 15 lists them in `architecture.md`, and Task 16 Step 6 puts what they do to the PI.
- **Every session instant is read through `Session.wall_now()`**, the session's anchored `welfare.SessionClock`: a pause and a resume, a mark's stamp, a schedule's target and its check, every control row. `wlx serve` reads its own host clock once, for a mark's `received_at`, which the record labels as that clock's.
- **US English** in code, comments and docs.
- **No timing claim without a measurement.** `PAUSE_HOUSEKEEPING_S`, `DEBOUNCE_MS`, `REPLY_TIMEOUT_S`, `CONNECT_TIMEOUT_S`, `COMMAND_QUEUE_DEPTH`, `MARK_QUEUE_DEPTH`, `OUTBOX_POLL_S`, `BODY_LIMIT` and `MARKS_REMEMBERED` are housekeeping, and every docstring that names one says so. The mark check's cost is stated only by `tools/measure_mark_check.py`'s committed output, labeled as a development machine's; its effect on frames is V12's, on a rig.
- **Hot path.** The only new work inside a frame is `run_trial`'s `each_frame(frame)`, which is `link.mark_signal()` — one `getsockopt(EVENTS)`, one `&` — and, only on a frame a mark arrived in, one strobe, one `Session.wall_now()` and one list append. Nothing in a frame writes a file: stamps are written at the boundary after. Everything else happens at a trial boundary, while paused, or in `wlx serve`'s process — a manual reward only while paused, in `_hold`, never in a frame.
- **No new dependency.** The console extra's pyzmq floor rises from 26 to 26.4 (`Socket.recv_into`), recorded in `pyproject.toml` and ADR-0004's inventory row (Task 3). `serve.py`, `web.py` and `health.py` still import with no transport installed (`tests/test_no_transport_leak.py`).
- **Writes come from the box alone** (spec §2): a loopback peer, a `Host` naming loopback, the page's own `Origin`, and `Content-Type: application/json`. **Every request is answered only when its `Host` names this console** (spec §5.3). The actor is `NAME (box, unverified)`.
- **Every telemetry string reaches the page through `web._e`**, in elements and attributes alike; the page's script writes only rendered fragments (`innerHTML`) and its own words (`textContent`).
- **Tests that open a socket set a client timeout and bind loopback only**, register every `ZmqLink`/`ZmqConsole`/`ZmqCommands`/`ZmqMarks` they build with `zmq_cleanup`, and rely on `tests/_zmq_release.py`'s autouse fixture (extended in Tasks 3 and 4) for those built inside `main()` or a server thread.
- **Tests that start a `wlx run` follow P4d-2a's two rules**: a trial budget (Ruling 10) — `_trial_budget` in `test_serve.py`, sized to the session it bounds (`CONTROL_TRIAL_BUDGET` for Task 12's, which have a mark socket and so run fewer trials a second than b1's), and for a paused session `_Scripted`'s wait and drain budgets in `test_taskd.py` — and `_main_uninterrupted` for every `main(...)` call on a thread (M3). **A mutation that prints `caught … timed out` is a missing bound, not a catch** (`docs/next-session.md`: *the fix is a bound, not a shrug*): fix the bound in the owning task.
- **Do not edit `tests/conftest.py`.** Shared frames live in `tests/_frames.py`.
- **Prove each new test can fail** (CLAUDE.md): Task 16 runs the mutation gate and reads it line by line — `N failed` is a test noticing; `N errors in 0.8s` is not.
- **Never run the suite, edit a test, or `git add` while a mutation sweep is in flight.**
- Run tests with `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider` from the worktree root, with the `wl-preproc` checkout beside the repo or inside it.
- Commit messages: imperative subject; body says why when it is not obvious; end with the two attribution lines the session supplies.

## Review Focus

The five conditions the spec implies that a lab member will meet and no task's main tests would otherwise pin — each has its test in the owning task:

1. **A double-click, or a held arrow, floods commands** → the arrows send one change once they stop being clicked; a second identical pause or a stray resume is refused by the rig with a sentence, never stacked; and whatever does not fit `wlx serve`'s queue is answered *busy* at once, never queued without bound, while everything queued is answered. *Task 5 (`test_a_second_pause_and_a_resume_with_nothing_paused_are_refused`), Task 10 (`test_the_script_debounces_the_arrows_and_keeps_p_and_m_out_of_text_boxes`), Task 11 (`test_a_full_outbox_answers_busy_at_once_and_every_queued_job_is_answered`).*
2. **M pressed twice fast** → two signals, two numbers, two `OPERATOR_MARK` codes in order, neither lost; the second is read in the next frame and its stamp names that frame; a second mark while a note box is open leaves the first bare. *Task 6 (`test_two_marks_pressed_fast_are_two_stamps_in_order`); the page's half in Task 16 Step 4.*
3. **Pause pressed while a stop is already on its way** → both land in one drain; the stop ends the session at that boundary, and the pause is refused with *the session is stopping (…)*, never holding a session that is ending. *Task 5 (`test_a_pause_pressed_after_a_stop_is_refused_and_the_session_ends`).*
4. **A scheduled clock time that is already past, or exactly now** → the next occurrence, tomorrow's, as the spec rules, with the date in the schedule's words on the feed and the strip. *Task 7 (`test_a_clock_time_already_past_or_exactly_now_is_tomorrows`).*
5. **`wlx serve` restarted while the session is paused** → the pause is `taskd`'s, so the new console shows it paused and offers *resume*, and its resume continues the session; a mark's note sent across the restart is recorded with its instants unknown, never guessed. *Task 12 (`test_e2e_wlx_serve_restarted_while_paused_shows_it_paused_and_can_resume`), Task 11 (`test_a_note_for_a_mark_this_console_does_not_know_carries_no_instants`).*

Also pinned, the sixth candidate: **the name prompt refused or cleared** sends nothing and says *give your name first*, and a command with no name is refused at `POST /commands` whatever sent it. *Task 10 (`test_the_script_asks_for_the_name_once_and_keeps_it_where_it_may`), Task 11 (`test_a_body_that_is_not_a_command_is_refused_before_anything_is_queued`).*

Added with the PI's manual reward during a pause (2026-09-28, Plan decision 16), three more, each with its tests in Task 13:

- **A reward pressed while trials run, or while a pause is on its way** → refused with a sentence and nothing given: while running, *the session is not paused*; in the same drain as the pause, before the boundary holds it, *the session's pause has not begun holding yet*; after a stop or a resume ahead of it, or after the session ended, likewise. The page offers the button only on a frame that says paused. *Task 13 (`test_a_manual_reward_at_any_other_time_is_refused_and_nothing_is_given`, `test_after_the_loop_a_manual_reward_is_refused_and_nothing_is_given`, `test_the_reward_button_is_live_only_while_paused_and_greyed_otherwise`, and the refusal in `test_e2e_a_reward_pressed_while_paused_is_one_correct_trial_reward_on_the_record`).*
- **A reward whose answer is lost** → *unknown*, with the fluid total to check before pressing again, and **never sent again**: one press is one command on the wire whatever the answer, a lost answer never reads *not delivered*, and the page's button is held from the click until the answer. *Task 13 (`test_a_reward_the_rig_takes_and_never_acknowledges_is_unknown_and_sent_once`, `test_a_rewards_answer_is_sent_unknown_or_not_given_and_it_is_delivered_once`, `test_a_command_the_rig_took_and_never_acknowledged_is_told_from_one_never_sent`, `test_the_script_sends_one_reward_per_click_and_holds_the_button_until_its_answer`).*
- **A manual reward that reaches a scheduled "stop after X mL"** → the session ends in that housekeeping pass, as a scheduled stop, without a resume, and the limit is still asked first. *Task 13 (`test_a_manual_reward_that_reaches_a_fluid_stop_ends_the_paused_session_in_that_pass`).*

## File Structure

| File | Responsibility |
|---|---|
| `wl_expcontroller/link.py` (modify) | M8's `_setting`, `_actor`, `CommandRefused`; `Pause`, `Resume`, `Mark`, `ScheduleStop`, `CancelScheduledStop`, `check_schedule`, `ManualReward`; the mark socket (`mark_signal`, `idle`, `MARK_BYTES`); `ZmqMarks`, `ZmqCommands`, `NotDelivered`, `Unacknowledged`; a read-only `ZmqConsole`; schema 8 (`ScheduledStop`, `Control`, `CONTROL_HISTORY`) |
| `wl_expcontroller/taskd.py` (modify) | M8's backstop; `_pause`, `_resume`, `_hold`, `_ends`; `_stamp`, `_settle_stamps`, `_check_marks`, `_mark_note`; `_schedule`, `_cancel`, `_next_occurrence`; `_control`, `_feed`, `controls`; `PAUSE_HOUSEKEEPING_S`; `_manual_reward`, `MANUAL_REWARD_ENTRY`, `_command`'s `held` |
| `wl_expcontroller/run.py` (modify) | `run_trial`'s `each_frame` hook |
| `wl_expcontroller/record.py` (modify) | `CONTROLS`, `SessionRecord.control` |
| `tasks/allocation.py` (modify) | `PAUSE`, `RESUME`, `OPERATOR_MARK`, `MANUAL_REWARD` |
| `wl_expcontroller/cli.py` (modify) | `--link PUB,REP[,MARK]` for `run` and `serve`; `serve --allow-host`; `render` for schema 8 |
| `wl_expcontroller/health.py` (modify) | *paused* in the state reading |
| `wl_expcontroller/web.py` (modify) | `View.can_write`, `View.can_mark`; the `controls` fragment, card inputs and arrows, the strip's schedule cell, the feed's control rows; *give reward* (`_reward_button`, `_reward_answer`, `REWARD_ONLY_PAUSED`); the page's static controls; the script |
| `wl_expcontroller/serve.py` (modify) | `host_name`, `box_names`, `names_loopback`; `parse_command`, `MarkSignal`, `MarkNote`; `Outbox`; `POST /commands`; `Server.dispatch`; `_rewarded`, `REWARD_SENT`, `REWARD_UNKNOWN`; `parse_link`'s third endpoint |
| `tools/measure_mark_check.py` (create) | The measurement spec §5.4 requires |
| `pyproject.toml`, `docs/design/decisions/ADR-0004-license.md` (modify) | pyzmq ≥ 26.4 |
| `docs/validation.md` (modify) | V12 |
| `tests/test_link.py`, `test_taskd.py`, `test_run.py`, `test_cli.py`, `test_health.py`, `test_web.py`, `test_serve.py` (modify) | Each module's own changes; the end to end in `test_serve.py` |
| `tests/test_measure_mark_check.py` (create) | The measurement script measures what it says |
| `tests/_frames.py`, `tests/_zmq_release.py` (modify) | Schema 8's fields and `View`'s two; the two new socket owners registered |
| `docs/measurements/dev-machine/<date>-mark-check.md` (create, by running the script) | The measurement's first result |
| `docs/design/architecture.md`, `docs/pitfalls.md`, S9a, `docs/CHECKPOINT.md`, `docs/next-session.md` (modify) | Task 15 |

**The mutation gate needs no edit**: no module is added to `wl_expcontroller/`. `tasks/allocation.py`, `pyproject.toml`, `tests/_zmq_release.py` and `tests/_frames.py` change — each a `tasks/` or `GLOBAL` path in `tools/mutation_gate.py` — and eight modules do, so this branch needs the **full sweep before it merges**. A push does not give it: since the CI split (`c215a10`), a push runs `--changed-only`, which never escalates, and with a `GLOBAL` path in the diff selects no module at all. Task 16 Step 2 plans for that.

---

### Task 1: M8 — a malformed setting is refused, and never ends the session

**Why:** spec §5.1, "M8 closes first". `SetParameter.value` is a type hint nothing enforces: a string reaching `bounds._finite` raises `TypeError`, `Session._command` does not catch it, and `run()`'s fault handler ends the whole session with an animal in the chair. The value is checked where the command is decoded — a finite real number that is not a `bool`, or a word for a categorical parameter — and a bad one becomes a refusal with a sentence naming the parameter and the sender. `Session.set` refuses what is not a number before `bounds` is asked, and `Session._command` also refuses on a `TypeError`, as the spec's backstop (Plan decision 14). **`bounds.py` is not touched.**

**Files:**
- Modify: `wl_expcontroller/link.py` (`import math`; `SetParameter`'s docstring and `value` type; `CommandRefused`, `TEXT_LIMIT`, `_actor`, `_setting` before `_decode_command`; `_decode_command`; `ZmqLink.drain`)
- Modify: `wl_expcontroller/taskd.py` (`Session.set`, `Session._command`)
- Test: `tests/test_link.py`, `tests/test_taskd.py`

**Interfaces:**
- Consumes: `link._decode_command`, `ZmqLink.drain`, `Session.set`, `Session._command` as they are at `e426de2`.
- Produces:
  - `link.CommandRefused(name: str, by: str, why: str)`, a `ValueError` whose `.name`, `.by`, `.why` a refusal is filed under. Task 2 raises it for every kind; Task 11 turns it into a `400`.
  - `link.TEXT_LIMIT = 200`; `link._actor(by: object, name: str) -> str`; `link._setting(value: object, name: str, by: str) -> float | str`. Task 11's `serve.parse_command` calls `_setting`.
  - `SetParameter.value: float | str`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_link.py`, replace:

```python
    Absent,
    FrameError,
```

with:

```python
    Absent,
    CommandRefused,
    FrameError,
```

In `tests/test_link.py`, replace:

```python
    ZmqLink,
    decode,
```

with:

```python
    ZmqLink,
    _decode_command,
    _encode_command,
    decode,
```

Append to `tests/test_link.py`:

```python


# ---------------------------------------------------------------------------
# M8 (P4d-2a's review, closed in P4d-2b b2a): a setting's value is checked where
# the command is decoded
# ---------------------------------------------------------------------------


def _packed(**fields) -> bytes:
    import msgpack

    return msgpack.packb(fields, use_bin_type=True)


@pytest.mark.parametrize(
    "value",
    [True, False, None, [0.4], {"v": 0.4}, float("nan"), float("inf"), float("-inf")],
)
def test_a_setting_that_is_not_a_real_number_or_a_word_is_refused_where_it_is_decoded(
    value,
):
    """M8: `SetParameter.value` was a type hint nothing enforced, so a string reached
    `bounds._finite`, raised `TypeError`, and `run()`'s fault handler ended the whole
    session. A value is a finite real number that is not a `bool`, or a word for a
    categorical parameter; anything else is refused here, naming the parameter and
    the sender, so the refusal a console shows says whose write it was."""
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name="fix_hold", value=value, by="jake"))

    assert refused.value.name == "fix_hold"
    assert refused.value.by == "jake"
    assert "'fix_hold' was sent" in refused.value.why
    assert "the session runs on" in refused.value.why


def test_a_whole_number_decodes_as_a_float_and_a_word_as_itself():
    """A browser's JSON gives `1` for one and `0.5` for a half; both are numbers. A
    categorical choice travels as its word, and `Session.set` checks it against the
    task's `choices`."""
    whole = _decode_command(_packed(kind="set", name="fix_window", value=2, by="jake"))
    word = _decode_command(_packed(kind="set", name="shape", value="penguin", by="jake"))

    assert whole == SetParameter(name="fix_window", value=2.0, by="jake")
    assert type(whole.value) is float
    assert word == SetParameter(name="shape", value="penguin", by="jake")


@pytest.mark.parametrize("by", [None, "", "   ", 7])
def test_a_command_that_does_not_say_who_sent_it_is_refused(by):
    """S9a §6: every write records its actor. A packet with no usable `by` is refused
    by name rather than recorded as written by nobody."""
    fields = {"kind": "set", "name": "fix_hold", "value": 0.4}
    if by is not None:
        fields["by"] = by

    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(**fields))

    assert refused.value.name == "fix_hold"
    assert refused.value.by == "<unknown>"
    assert "who sent it" in refused.value.why


def test_a_setting_with_no_parameter_name_is_refused():
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(kind="set", name="", value=0.4, by="jake"))

    assert refused.value.name == "<transport>"
    assert "no parameter name" in refused.value.why


def test_a_malformed_setting_over_the_wire_is_a_refusal_naming_it_and_the_link_goes_on(
    zmq_cleanup,
):
    """The path, not the piece: a real packet on a real socket, a refusal that names
    the parameter and the sender (so the feed says whose write it was), and a channel
    that still carries the next command."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    # `True`, not a word: a word is a categorical choice on the wire, and whether it
    # is one of this parameter's choices is `Session.set`'s to say.
    console._req.send(_packed(kind="set", name="fix_hold", value=True, by="jake"))
    console._awaiting_reply = True
    commands = _drain_until(link)

    assert commands == []
    assert [(r.name, r.by) for r in link.refused] == [("fix_hold", "jake")]

    console.send(SetParameter(name="fix_hold", value=0.4, by="jake"))
    assert _drain_until(link) == [SetParameter(name="fix_hold", value=0.4, by="jake")]
```

Append to `tests/test_taskd.py`:

```python


# ---------------------------------------------------------------------------
# M8 (P4d-2b b2a): a malformed setting is refused and never ends the session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value", "said"),
    [
        ("fix_hold", "abc", "'fix_hold' takes a number (s)"),
        ("fix_hold", True, "'fix_hold' takes a number (s)"),
        ("reward_correct", "lots", "'reward_correct' is a welfare ceiling and takes a number"),
        ("reward_correct", False, "'reward_correct' is a welfare ceiling and takes a number"),
    ],
)
def test_a_malformed_setting_is_refused_and_the_session_runs_on(tmp_path, name, value, said):
    """M8, the backstop behind the decoder: a value that is not a number reaches
    `Session.set` only from inside this process (the wire refuses it first), and it is
    refused with a sentence rather than raising `TypeError` out of `bounds._finite`,
    which `run()`'s fault handler turned into the end of the session."""
    link = Simulated()
    link.queue(SetParameter(name=name, value=value, by="jake"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert [(n, b) for n, b, _ in session.refusals] == [(name, "jake")]
    assert said in session.refusals[0][2]


def test_a_type_error_in_a_setting_is_a_refusal_not_a_fault(tmp_path, monkeypatch):
    """The spec's second half of M8: `Session._command` refuses on a `TypeError` too,
    so no check `set` does not yet make can end a session with an animal in the
    chair."""

    def raises(self, name, value, by):
        raise TypeError("must be real number, not list")

    monkeypatch.setattr(Session, "set", raises)
    link = Simulated()
    link.queue(SetParameter(name="fix_hold", value=[0.4], by="jake"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    assert session.stop_kind == "completed"
    (refusal,) = session.refusals
    assert refusal[:2] == ("fix_hold", "jake")
    assert "could not be checked" in refusal[2]
    assert "must be real number, not list" in refusal[2]


def test_a_malformed_ceiling_write_is_recorded_as_asked(tmp_path):
    """A refused write to a welfare ceiling goes to the session record (PI,
    2026-09-19), a malformed one included, with what was asked written as it came."""
    link = Simulated()
    link.queue(SetParameter(name="reward_correct", value="lots", by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    (row,) = _refusal_rows(session)
    assert row["name"] == "reward_correct"
    assert row["asked"] == "lots"
    assert row["by"] == "jake"
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider --continue-on-collection-errors tests/test_link.py tests/test_taskd.py`
Expected: `tests/test_link.py` fails to collect — `ImportError: cannot import name 'CommandRefused'` (without `--continue-on-collection-errors` pytest stops there and runs nothing else); in `tests/test_taskd.py` the six new tests fail, the string cases with `TypeError: must be real number, not str` out of `bounds._finite` (M8 itself) and the `bool` cases because `True` was staged as `1.0` rather than refused.

- [ ] **Step 3: Implement**

In `wl_expcontroller/link.py`, replace:

```python
import ipaddress
import time
```

with:

```python
import ipaddress
import math
import time
```

In `wl_expcontroller/link.py`, in `SetParameter`, replace:

```python
    """A parameter change offered by a console. Validated by `Session.set`, which is
    the one write path -- this carries the request, never a second validator."""
```

with:

```python
    """A parameter change offered by a console. Validated by `Session.set`, which is
    the one write path -- this carries the request, never a second validator.

    **`value` is a `float` or, for a categorical parameter, a `str`** -- and since
    M8 (P4d-2b b2a) the wire enforces the type before this object exists
    (`_setting`). Whether the value is in range, or one of the choices, stays
    `Session.set`'s question."""
```

In `wl_expcontroller/link.py`, in `SetParameter`, replace:

```python
    name: str
    value: float
```

with:

```python
    name: str
    value: float | str
```

In `wl_expcontroller/link.py`, replace:

```python

def _decode_command(payload: bytes) -> Command:
```

with:

```python

class CommandRefused(ValueError):
    """A command that decoded and cannot be built as sent (M8, closed in P4d-2b b2a).

    Carries what the packet said of the parameter and of the sender, where it said
    them, so the `Refused` row `ZmqLink.drain` makes from it names both: a console's
    feed then says whose write was refused and which setting it was for, not
    `<transport>` by `<unknown>`. `why` is a complete sentence."""

    def __init__(self, name: str, by: str, why: str) -> None:
        super().__init__(why)
        self.name = name
        self.by = by
        self.why = why


#: The longest parameter name, actor, or categorical value a command may carry. A
#: bound on what one packet can put into a refusal row, the record and every frame,
#: not a rule about names: nothing a person types is this long.
TEXT_LIMIT = 200


def _actor(by: object, name: str) -> str:
    """`by`, when it is a name: a non-empty string no longer than `TEXT_LIMIT`.

    S9a §6: every welfare-affecting write records its actor, and a write from nobody
    is refused rather than recorded as written by nobody. `name` is what the refusal
    is filed under -- the parameter for a setting, the command's kind otherwise."""
    if not isinstance(by, str) or not by.strip() or len(by) > TEXT_LIMIT:
        raise CommandRefused(
            name,
            "<unknown>",
            f"a {name!r} command must say who sent it (`by`, a name of at most "
            f"{TEXT_LIMIT} characters; S9a §6), and this one did not, so it is refused",
        )
    return by


def _setting(value: object, name: str, by: str) -> float | str:
    """**M8.** A setting's value: a finite real number that is not a `bool`, returned
    as a `float`, or a word for a categorical parameter, returned as itself.

    `SetParameter.value` was a type hint nothing enforced. A string reached
    `bounds._finite`, raised `TypeError`, and `Session._command` did not catch it, so
    `run()`'s fault handler ended the session over a malformed setting. Checked here,
    where the bytes become a command, the bad value is a refusal with a sentence and
    the session runs on. `bool` is refused although Python counts it as an `int`:
    `True` was accepted as `1.0`. Whether a word is one of the parameter's choices is
    `Session.set`'s to decide, since only the task knows them."""
    if isinstance(value, str):
        if len(value) > TEXT_LIMIT:
            raise CommandRefused(
                name,
                by,
                f"{name!r} was sent a word of {len(value)} characters; a categorical "
                f"choice is at most {TEXT_LIMIT}, so it is refused and the session "
                f"runs on",
            )
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CommandRefused(
            name,
            by,
            f"{name!r} was sent {value!r}: a setting is a finite number, or a word "
            f"for a categorical parameter, and this is neither, so it is refused and "
            f"the session runs on",
        )
    if not math.isfinite(value):
        raise CommandRefused(
            name,
            by,
            f"{name!r} was sent {value!r}, which is not a real number: it would "
            f"defeat every range check, so it is refused and the session runs on",
        )
    return float(value)


def _decode_command(payload: bytes) -> Command:
```

In `wl_expcontroller/link.py`, in `_decode_command`, replace:

```python
    special case.
    """
```

with:

```python
    special case.

    **Every field is checked here, before a command exists** (M8, P4d-2b b2a): a
    command that decoded and is malformed raises `CommandRefused`, naming what it
    could of the parameter and the sender; bytes that are not a command at all raise
    whatever `msgpack` or the dict raised, and `drain` refuses those as before.
    """
```

In `wl_expcontroller/link.py`, in `_decode_command`, replace:

```python
    if kind == "set":
        return SetParameter(name=data["name"], value=data["value"], by=data["by"])
```

with:

```python
    if kind == "set":
        name = data.get("name")
        if not isinstance(name, str) or not name or len(name) > TEXT_LIMIT:
            raise CommandRefused(
                "<transport>",
                data["by"] if isinstance(data.get("by"), str) else "<unknown>",
                f"a setting arrived with no parameter name it could be for "
                f"({name!r}), so it is refused",
            )
        by = _actor(data.get("by"), name)
        return SetParameter(name=name, value=_setting(data.get("value"), name, by), by=by)
```

In `wl_expcontroller/link.py`, in `_decode_command`, replace:

```python
    if kind == "stop":
        return Stop(by=data["by"])
```

with:

```python
    if kind == "stop":
        return Stop(by=_actor(data.get("by"), "stop"))
```

In `wl_expcontroller/link.py`, in `ZmqLink.drain`, replace:

```python
                commands.append(_decode_command(raw))
            except Exception as exc:  # noqa: BLE001 -- deliberately broad, see above
```

with:

```python
                commands.append(_decode_command(raw))
            except CommandRefused as refused:
                # M8: a command that decoded and is malformed, named by what it
                # said of itself -- which setting, and who sent it.
                self.refused.append(
                    Refused(name=refused.name, by=refused.by, why=refused.why)
                )
            except Exception as exc:  # noqa: BLE001 -- deliberately broad, see above
```

In `wl_expcontroller/taskd.py`, in `Session.set`, replace:

```python
        if name in self.spec.bounds.ceilings:
            # Checked here, assigned by `_apply_staged()` -- `bounds.validate` moves
```

with:

```python
        if name in self.spec.bounds.ceilings:
            # M8 (P4d-2b b2a): a ceiling takes a number. A word reached
            # `bounds._finite` and raised `TypeError` out of this method, which
            # `run()`'s fault handler turned into the end of the session; `True`
            # was accepted as 1.0. Refused here, before `bounds` is asked, with the
            # sentence a console shows.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Exceeded(
                    f"{name!r} is a welfare ceiling and takes a number; {value!r} is "
                    f"not one, so it is refused and the previous value stands"
                )
            # Checked here, assigned by `_apply_staged()` -- `bounds.validate` moves
```

In `wl_expcontroller/taskd.py`, in `Session.set`, replace:

```python
        if declared.choices and value not in declared.choices:
            raise Exceeded(f"{name!r} may only be one of {declared.choices}")
        # **The same hole as the welfare path, on the task's own declaration.** The
        # range check below is two ordered comparisons, and `nan` is `False` against
        # both -- so a declared range accepts a value no range contains. This is not
        # a welfare-critical file and a `nan` fixation window is a broken trial
        # rather than a hurt animal, but it is the identical defect and it enters
        # from the identical place: a console over the wire, or `--set` on a
        # command line. `bounds._finite` is the same guard the ceilings use.
        _finite(f"{name!r}", value)
        low, high = declared.low, declared.high
        if (low is not None and value < low) or (high is not None and value > high):
            raise Exceeded(
                f"{name!r} is declared over [{low}, {high}] {declared.unit} and "
                f"{value} is outside it"
            )
```

with:

```python
        if declared.choices:
            if value not in declared.choices:
                raise Exceeded(f"{name!r} may only be one of {declared.choices}")
        else:
            # M8 (P4d-2b b2a): a numeric parameter takes a number, and a word used
            # to reach `_finite` below and raise `TypeError` instead of this
            # sentence. `bool` is refused although Python counts it as an `int`.
            # A categorical parameter skips the numeric checks: its value is one of
            # its choices, which may be words, and `_finite` raised on those too.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Exceeded(
                    f"{name!r} takes a number ({declared.unit}); {value!r} is not "
                    f"one, so it is refused and the previous value stands"
                )
            # **The same hole as the welfare path, on the task's own declaration.**
            # The range check below is two ordered comparisons, and `nan` is
            # `False` against both -- so a declared range accepts a value no range
            # contains. This is not a welfare-critical file and a `nan` fixation
            # window is a broken trial rather than a hurt animal, but it is the
            # identical defect and it enters from the identical place: a console
            # over the wire, or `--set` on a command line. `bounds._finite` is the
            # same guard the ceilings use.
            _finite(f"{name!r}", value)
            low, high = declared.low, declared.high
            if (low is not None and value < low) or (high is not None and value > high):
                raise Exceeded(
                    f"{name!r} is declared over [{low}, {high}] {declared.unit} and "
                    f"{value} is outside it"
                )
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
            self.set(command.name, command.value, by=command.by)
        except Exceeded as refused:
```

with:

```python
            self.set(command.name, command.value, by=command.by)
        except (Exceeded, TypeError) as refused:
            # **M8's backstop** (P4d-2b b2a): `TypeError` too. The wire refuses a
            # malformed value before it becomes a command (`link._setting`) and
            # `set` refuses what it knows is not a number, so this catches only a
            # check neither of them makes yet -- and a session never ends with an
            # animal in the chair because a setting was malformed.
            why = (
                str(refused)
                if isinstance(refused, Exceeded)
                else f"{command.name!r} could not be checked ({type(refused).__name__}: "
                f"{refused}), so it is refused and the session runs on"
            )
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
                    name=command.name,
                    asked=command.value,
```

with:

```python
                    name=command.name,
                    # As asked, when it can be written as asked; `repr` otherwise,
                    # so the row is written whatever the value was.
                    asked=(
                        command.value
                        if isinstance(command.value, (int, float, str))
                        else repr(command.value)
                    ),
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
                    by=command.by,
                    why=str(refused),
```

with:

```python
                    by=command.by,
                    why=why,
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
                )
            self._refuse(command.name, command.by, str(refused))
```

with:

```python
                )
            self._refuse(command.name, command.by, why)
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_taskd.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1148 passed**.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/taskd.py tests/test_link.py tests/test_taskd.py
git commit -m "Refuse a malformed setting where it is decoded, and never end a session over one (M8)"
```

---

### Task 2: The five controls on the wire

**Why:** spec §5.1: today's closed union, `SetParameter | Stop`, gains `Pause`, `Resume`, `Mark`, `ScheduleStop` and `CancelScheduledStop`, each carrying `by`. Each is checked where it is decoded — M8's rule for every field — so a malformed control is a refusal filed under its kind, never a command that faults the session later. `check_schedule` is the one rule for what a scheduled stop may be (Plan decision 6). Every command class names its kind (`KIND`), which is what a refusal is filed under and what `taskd`'s fallback names: a command `_command` has no branch for — the next four tasks add the branches — is refused by kind and the session runs on, as `drain` already refuses an unknown kind on the wire.

**Files:**
- Modify: `wl_expcontroller/link.py` (`import re`, `ClassVar`; `KIND` on `SetParameter` and `Stop`; the five new commands, `Command`, `SCHEDULE_KINDS`, `MARK_LIMIT`, `NOTE_LIMIT`, `check_schedule`; `_encode_command`; `_decode_command`, `_instant`, `_mark`)
- Modify: `wl_expcontroller/taskd.py` (`Session._command`)
- Test: `tests/test_link.py`, `tests/test_taskd.py`

**Interfaces:**
- Consumes: Task 1's `CommandRefused`, `_actor`, `_setting`, `_packed` (the test helper).
- Produces:
  - `link.Pause(by: str)`, `link.Resume(by: str)`, `link.CancelScheduledStop(by: str)`.
  - `link.Mark(mark: int, note: str, by: str, pressed_at: float | None, received_at: float | None)` — the note half of a mark (Plan decision 4).
  - `link.ScheduleStop(kind: str, value: str | int | float, by: str)`, `kind` one of `link.SCHEDULE_KINDS = ("clock", "trials", "fluid")`.
  - `KIND: ClassVar[str]` on every command: `"set"`, `"stop"`, `"pause"`, `"resume"`, `"mark"`, `"schedule"`, `"cancel"`.
  - `link.Command = SetParameter | Stop | Pause | Resume | Mark | ScheduleStop | CancelScheduledStop`.
  - `link.MARK_LIMIT = 2**64 - 1`, `link.NOTE_LIMIT = 500`, `link.check_schedule(kind: object, value: object) -> str | None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_link.py`, replace:

```python
    Absent,
    CommandRefused,
```

with:

```python
    Absent,
    CancelScheduledStop,
    CommandRefused,
```

In `tests/test_link.py`, replace:

```python
    CommandRefused,
    FrameError,
```

with:

```python
    CommandRefused,
    Mark,
    Pause,
    Resume,
    ScheduleStop,
    FrameError,
```

Append to `tests/test_link.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a: the five controls on the wire (spec §5.1)
# ---------------------------------------------------------------------------

_CONTROLS = [
    Pause(by="jake (box, unverified)"),
    Resume(by="jake (box, unverified)"),
    Mark(mark=7, note="reward line bubble", by="jake (box, unverified)",
         pressed_at=1_700_000_000.25, received_at=1_700_000_000.5),
    Mark(mark=2**64 - 1, note="", by="jake", pressed_at=None, received_at=None),
    ScheduleStop(kind="clock", value="14:30", by="jake"),
    ScheduleStop(kind="trials", value=40, by="jake"),
    ScheduleStop(kind="fluid", value=12.5, by="jake"),
    CancelScheduledStop(by="jake"),
]


@pytest.mark.parametrize("command", _CONTROLS, ids=lambda c: type(c).__name__)
def test_each_control_survives_the_wire_with_who_sent_it(command):
    """Spec §5.1: `SetParameter | Stop` gains `Pause`, `Resume`, `Mark`,
    `ScheduleStop` and `CancelScheduledStop`, each carrying `by`."""
    restored = _decode_command(_encode_command(command))

    assert restored == command
    assert type(restored) is type(command)


def test_the_controls_cross_a_real_socket_in_order(zmq_cleanup):
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    seen = []
    for command in _CONTROLS:
        console.send(command)
        seen += _drain_until(link)

    assert seen == _CONTROLS


def test_each_command_names_its_kind():
    """What a refusal is filed under, and what `taskd` names in its feed."""
    assert [type(c).KIND for c in _CONTROLS] == [
        "pause", "resume", "mark", "mark", "schedule", "schedule", "schedule", "cancel",
    ]
    assert Stop.KIND == "stop" and SetParameter.KIND == "set"


@pytest.mark.parametrize(
    ("fields", "name", "said"),
    [
        ({"kind": "pause"}, "pause", "who sent it"),
        ({"kind": "resume", "by": ""}, "resume", "who sent it"),
        ({"kind": "cancel", "by": 3}, "cancel", "who sent it"),
        ({"kind": "mark", "mark": 0, "note": "", "by": "jake"}, "mark", "mark number"),
        ({"kind": "mark", "mark": -1, "note": "", "by": "jake"}, "mark", "mark number"),
        ({"kind": "mark", "mark": True, "note": "", "by": "jake"}, "mark", "mark number"),
        ({"kind": "mark", "mark": "3", "note": "", "by": "jake"}, "mark", "mark number"),
        ({"kind": "mark", "mark": 3, "note": None, "by": "jake"}, "mark", "note"),
        ({"kind": "mark", "mark": 3, "note": "x" * 501, "by": "jake"}, "mark", "note"),
        ({"kind": "mark", "mark": 3, "note": "", "by": "jake", "pressed_at": "now"}, "mark", "pressed_at"),
        ({"kind": "mark", "mark": 3, "note": "", "by": "jake", "received_at": float("nan")}, "mark", "received_at"),
        ({"kind": "schedule", "stop": "blocks", "value": 3, "by": "jake"}, "schedule", "clock, trials or fluid"),
        ({"kind": "schedule", "stop": "clock", "value": "25:00", "by": "jake"}, "schedule", "HH:MM"),
        ({"kind": "schedule", "stop": "clock", "value": "9:05", "by": "jake"}, "schedule", "HH:MM"),
        ({"kind": "schedule", "stop": "clock", "value": 1430, "by": "jake"}, "schedule", "HH:MM"),
        ({"kind": "schedule", "stop": "trials", "value": 0, "by": "jake"}, "schedule", "whole number of trials"),
        ({"kind": "schedule", "stop": "trials", "value": 2.5, "by": "jake"}, "schedule", "whole number of trials"),
        ({"kind": "schedule", "stop": "trials", "value": True, "by": "jake"}, "schedule", "whole number of trials"),
        ({"kind": "schedule", "stop": "fluid", "value": 0, "by": "jake"}, "schedule", "mL"),
        ({"kind": "schedule", "stop": "fluid", "value": float("inf"), "by": "jake"}, "schedule", "mL"),
        ({"kind": "schedule", "stop": "fluid", "value": "5", "by": "jake"}, "schedule", "mL"),
    ],
)
def test_a_malformed_control_is_refused_by_name_where_it_is_decoded(fields, name, said):
    """The M8 rule for every control: a field that is the wrong type or out of its
    domain is a refusal with a sentence, filed under the command's kind, never a
    command that faults the session later."""
    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(**fields))

    assert refused.value.name == name
    assert said in refused.value.why


def test_check_schedule_is_the_one_rule_for_what_a_schedule_may_be():
    """`taskd` asks the same question of a schedule that reached it without the
    wire (`link.Simulated`), so there is one rule for it."""
    from wl_expcontroller.link import check_schedule

    assert check_schedule("clock", "00:00") is None
    assert check_schedule("clock", "23:59") is None
    assert check_schedule("trials", 1) is None
    assert check_schedule("fluid", 0.01) is None
    assert "HH:MM" in check_schedule("clock", "24:00")
    assert "whole number" in check_schedule("trials", 1.0)
    assert "mL" in check_schedule("fluid", -2.0)
    assert "clock, trials or fluid" in check_schedule("never", 1)
```

Append to `tests/test_taskd.py`:

```python


def test_a_command_the_session_does_not_act_on_is_refused_not_a_fault(tmp_path):
    """A command type `_command` has no branch for -- a newer console's, say -- is
    refused under its kind and the session runs on, the rule `drain` already applies
    to an unknown kind on the wire."""

    class Recenter:
        KIND = "recenter"

        def __init__(self, by: str) -> None:
            self.by = by

    link = Simulated()
    link.queue(Recenter(by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.refusals == [
        ("recenter", "jake", "a 'recenter' command is not one this session acts on, so it is refused")
    ]
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider --continue-on-collection-errors tests/test_link.py tests/test_taskd.py`
Expected: `tests/test_link.py` fails to collect — `ImportError: cannot import name 'CancelScheduledStop'`; `test_a_command_the_session_does_not_act_on_is_refused_not_a_fault` fails with `AttributeError: 'Recenter' object has no attribute 'name'`, the fault this task's fallback closes.

- [ ] **Step 3: Implement**

In `wl_expcontroller/link.py`, replace:

```python
import weakref
from dataclasses import dataclass, field
```

with:

```python
import weakref
import re
from dataclasses import dataclass, field
```

In `wl_expcontroller/link.py`, replace:

```python
from dataclasses import dataclass, field
from typing import Protocol
```

with:

```python
from dataclasses import dataclass, field
from typing import ClassVar, Protocol
```

In `wl_expcontroller/link.py`, in `SetParameter`, replace:

```python
    `Session.set`'s question."""

    name: str
```

with:

```python
    `Session.set`'s question."""

    #: The command's kind on the wire, and what a refusal of it is filed under
    #: when it names no parameter (P4d-2b b2a). A class attribute, not a field.
    KIND: ClassVar[str] = "set"

    name: str
```

In `wl_expcontroller/link.py`, in `Stop`, replace:

```python
    pump faults."""

    by: str
```

with:

```python
    pump faults."""

    KIND: ClassVar[str] = "stop"

    by: str
```

In `wl_expcontroller/link.py`, replace:

```python

Command = SetParameter | Stop
```

with:

```python

@dataclass(frozen=True, slots=True)
class Pause:
    """Hold the session at the next trial boundary (P4d-2b spec §5.1): no trial runs
    and nothing is rewarded until `Resume`, while the out-of-cage clock keeps running
    and still ends the session. `taskd.Session._hold` is what it does."""

    KIND: ClassVar[str] = "pause"

    by: str


@dataclass(frozen=True, slots=True)
class Resume:
    """End a pause: trials run again from the next pass of the loop, with any setting
    staged while paused applied first (P4d-2b spec §5.1)."""

    KIND: ClassVar[str] = "resume"

    by: str


@dataclass(frozen=True, slots=True)
class Mark:
    """The **note** half of an operator's mark (P4d-2b spec §5.1).

    The mark itself is a signal on its own socket -- `mark`, eight bytes, sent the
    moment M is pressed and stamped by `taskd` in the frame it arrives, with the
    `OPERATOR_MARK` event code strobed in that frame. This command follows it on the
    ordinary command path, is drained at the next boundary like every command, and is
    joined to its stamp by `mark`.

    - `mark`: the signal's number, `1` to `2**64 - 1`; `0` is never a mark (it is
      what `Link.mark_signal` answers when none is waiting).
    - `note`: what the person typed after pressing M; empty when they pressed Esc.
    - `pressed_at`: when M was pressed, **on the browser's clock**, POSIX seconds;
      `None` when the console that sent this never knew.
    - `received_at`: when `wlx serve` received the signal, **on its host's clock**;
      `None` when this `wlx serve` was restarted between the signal and the note.

    The two instants are on two clocks and the stamp is on a third (the session's
    anchored one); the record keeps all three and their gaps, and hides neither.
    """

    KIND: ClassVar[str] = "mark"

    mark: int
    note: str
    by: str
    pressed_at: float | None
    received_at: float | None


@dataclass(frozen=True, slots=True)
class ScheduleStop:
    """Stop the session later, held by `taskd` so a closed page cannot lose it (P4d-2b
    spec §5.1). One of three `kind`s, each with its `value`:

    - `"clock"`: `"HH:MM"`, 24-hour; `taskd` stops at the next occurrence of that
      time on the session's anchored clock, within 24 hours.
    - `"trials"`: a whole number of further trials, counted from when `taskd`
      accepts the schedule.
    - `"fluid"`: mL this session, as `welfare.session_total()` reports it.

    `check_schedule` is the rule for what `value` may be. A new schedule replaces the
    one before it."""

    KIND: ClassVar[str] = "schedule"

    kind: str
    value: str | int | float
    by: str


@dataclass(frozen=True, slots=True)
class CancelScheduledStop:
    """Remove the scheduled stop, if there is one."""

    KIND: ClassVar[str] = "cancel"

    by: str


Command = SetParameter | Stop | Pause | Resume | Mark | ScheduleStop | CancelScheduledStop

#: The kinds of scheduled stop, in the order a person is offered them.
SCHEDULE_KINDS = ("clock", "trials", "fluid")
#: The largest mark number: the signal is eight bytes, unsigned.
MARK_LIMIT = 2**64 - 1
#: The longest note a mark may carry. A bound on one packet's reach into the record
#: and every frame, not a rule about what a person may say.
NOTE_LIMIT = 500
_HHMM = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


def check_schedule(kind: object, value: object) -> str | None:
    """Why a scheduled stop of `kind` at `value` is refused, or `None` when it is
    one: `"clock"` takes `"HH:MM"`, `"trials"` a whole number of at least one, and
    `"fluid"` a finite number of mL above zero. **The one rule**, asked where the
    wire decodes a `ScheduleStop` and again by `taskd.Session` of one that reached it
    without the wire."""
    if kind == "clock":
        if isinstance(value, str) and _HHMM.fullmatch(value):
            return None
        return (
            f"a scheduled stop at a clock time takes HH:MM on a 24-hour clock, such "
            f"as 14:30, and {value!r} is not one"
        )
    if kind == "trials":
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
            return None
        return (
            f"a scheduled stop after trials takes a whole number of trials, at least "
            f"one, and {value!r} is not one"
        )
    if kind == "fluid":
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
        ):
            return None
        return (
            f"a scheduled stop after fluid takes a number of mL above zero, and "
            f"{value!r} is not one"
        )
    return f"a scheduled stop is by clock, trials or fluid, and {kind!r} is none of them"
```

In `wl_expcontroller/link.py`, in `_encode_command`, replace:

```python
    elif isinstance(command, Stop):
        payload = {"kind": "stop", "by": command.by}
```

with:

```python
    elif isinstance(command, (Stop, Pause, Resume, CancelScheduledStop)):
        payload = {"kind": command.KIND, "by": command.by}
    elif isinstance(command, Mark):
        payload = {
            "kind": "mark",
            "mark": command.mark,
            "note": command.note,
            "by": command.by,
            "pressed_at": command.pressed_at,
            "received_at": command.received_at,
        }
    elif isinstance(command, ScheduleStop):
        payload = {
            "kind": "schedule",
            "stop": command.kind,
            "value": command.value,
            "by": command.by,
        }
```

In `wl_expcontroller/link.py`, in `_decode_command`, replace:

```python
    if kind == "stop":
        return Stop(by=_actor(data.get("by"), "stop"))
```

with:

```python
    simple = {command.KIND: command for command in (Stop, Pause, Resume, CancelScheduledStop)}
    if kind in simple:
        return simple[kind](by=_actor(data.get("by"), kind))
    if kind == "mark":
        return _mark(data)
    if kind == "schedule":
        by = _actor(data.get("by"), "schedule")
        why = check_schedule(data.get("stop"), data.get("value"))
        if why is not None:
            raise CommandRefused("schedule", by, f"{why}, so it is refused")
        return ScheduleStop(kind=data["stop"], value=data["value"], by=by)
```

In `wl_expcontroller/link.py`, in `_decode_command`, replace:

```python
    raise ValueError(f"unknown command kind on the wire: {kind!r}")

```

with:

```python
    raise ValueError(f"unknown command kind on the wire: {kind!r}")


def _instant(data: dict, key: str, by: str) -> float | None:
    """`pressed_at` or `received_at`: absent or `None` is `None`; otherwise a finite
    number of POSIX seconds, or the mark is refused."""
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CommandRefused(
            "mark",
            by,
            f"a mark's {key} is POSIX seconds or nothing, and {value!r} is neither, "
            f"so it is refused",
        )
    return float(value)


def _mark(data: dict) -> Mark:
    """A `Mark` from the wire, every field checked (the M8 rule, for the note)."""
    by = _actor(data.get("by"), "mark")
    number = data.get("mark")
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not 1 <= number <= MARK_LIMIT
    ):
        raise CommandRefused(
            "mark",
            by,
            f"a mark's note must name its mark number, 1 to {MARK_LIMIT}, and "
            f"{number!r} is not one, so it is refused",
        )
    note = data.get("note")
    if not isinstance(note, str) or len(note) > NOTE_LIMIT:
        raise CommandRefused(
            "mark",
            by,
            f"a mark's note is text of at most {NOTE_LIMIT} characters, and this one "
            f"is not, so it is refused",
        )
    return Mark(
        mark=number,
        note=note,
        by=by,
        pressed_at=_instant(data, "pressed_at", by),
        received_at=_instant(data, "received_at", by),
    )

```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
            self._refuse(
                "stop" if isinstance(command, _link.Stop) else command.name,
```

with:

```python
            self._refuse(
                command.name if isinstance(command, _link.SetParameter) else command.KIND,
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
            self.stop_kind = "operator"
            return
```

with:

```python
            self.stop_kind = "operator"
            return
        if not isinstance(command, _link.SetParameter):
            # A command this session has no branch for -- a newer console's -- is
            # refused under its kind, as `drain` refuses an unknown kind on the
            # wire, and the session runs on.
            self._refuse(
                command.KIND,
                command.by,
                f"a {command.KIND!r} command is not one this session acts on, so it "
                f"is refused",
            )
            return
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_taskd.py`
Expected: all pass. `test_an_undecodable_command_is_refused_not_raised` (b1) still passes: its `{"kind": "pause"}` packet is now a known kind with no `by`, refused with a sentence that names *pause*.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1181 passed**.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/taskd.py tests/test_link.py tests/test_taskd.py
git commit -m "Carry pause, resume, mark, schedule and cancel on the link, each checked where it is decoded"
```

---

### Task 3: The mark signal on the link

**Why:** spec §5.0 and §5.1: a mark is stamped in the frame it reaches the rig, not at the next trial boundary, and draining every command per frame would break the trial loop's rules. So the mark's signal is a fixed-size number on a third loopback socket that the loop checks once per frame with no allocation and bounded work (Plan decision 1). This task builds both ends of that socket and the `Link` protocol the loop will call; Task 6 calls it. `wlx run --link` learns the third endpoint (Plan decision 2). The console extra's pyzmq floor rises to 26.4, for `Socket.recv_into`.

**Files:**
- Modify: `wl_expcontroller/link.py` (`MARK_BYTES`; `Link.mark_signal`, `Link.idle`; `Absent` and `Simulated`'s; `ZmqLink.__init__`'s third socket; `ZmqLink.drain`, `_refuse`, `mark_signal`, `_take_mark`, `idle`; `NotDelivered`, `CONNECT_TIMEOUT_S`, `ZmqMarks`)
- Modify: `wl_expcontroller/cli.py` (`run`'s `--link` help and parsing)
- Modify: `pyproject.toml`, `docs/design/decisions/ADR-0004-license.md` (pyzmq ≥ 26.4)
- Test: `tests/test_link.py`, `tests/test_cli.py`, `tests/_zmq_release.py`

**Interfaces:**
- Consumes: Task 2's `MARK_LIMIT`.
- Produces:
  - `ZmqLink(pub_endpoint: str, rep_endpoint: str, mark_endpoint: str | None = None, *, allow_remote: bool = False)`; `.mark_endpoint: str | None`; `.mark_signal() -> int` (a mark's number, or `0`); `.idle(timeout: float) -> int`; `.mark_malformed: int`.
  - The `Link` protocol's `mark_signal() -> int` and `idle(timeout: float) -> int`, implemented by `Absent` (`0`; `idle` sleeps) and `Simulated` (`marks: list`, handed over once each; `idle` never waits).
  - `link.MARK_BYTES = 8`; `link.NotDelivered(Exception)`; `link.CONNECT_TIMEOUT_S = 1.0`.
  - `link.ZmqMarks(mark_endpoint: str, connect_timeout_s: float = CONNECT_TIMEOUT_S)`, `.signal(mark: int) -> None` (raises `NotDelivered`, or `ValueError` for a number that is not a mark), `.endpoint`, `.close()`; used by Task 11's mark thread.
  - `wlx run --link PUB,REP[,MARK]`.

- [ ] **Step 1: Write the failing tests**

In `tests/_zmq_release.py`, replace:

```python
"""Every `ZmqLink` and `ZmqConsole` a test builds is held until its teardown, and its
`Context` is destroyed there directly. That includes the ones built where the test has
```

with:

```python
"""Every `ZmqLink`, `ZmqConsole` and `ZmqMarks` a test builds is held until its
teardown, and its `Context` is destroyed there directly. That includes the ones built where the test has
```

In `tests/_zmq_release.py`, replace:

```python

from wl_expcontroller.link import ZmqConsole, ZmqLink
```

with:

```python

from wl_expcontroller.link import ZmqConsole, ZmqLink, ZmqMarks
```

In `tests/_zmq_release.py`, in `_every_zmq_context_released`, replace:

```python
    """Wrap `ZmqLink.__init__` and `ZmqConsole.__init__` to record each object and the
    thread that built it. At teardown, destroy each context directly with `linger=0`."""
```

with:

```python
    """Wrap `ZmqLink.__init__`, `ZmqConsole.__init__` and `ZmqMarks.__init__` (P4d-2b
    b2a: `wlx serve`'s mark thread builds one) to record each object and the thread
    that built it. At teardown, destroy each context directly with `linger=0`."""
```

In `tests/_zmq_release.py`, in `_every_zmq_context_released`, replace:

```python

    for cls in (ZmqLink, ZmqConsole):
```

with:

```python

    for cls in (ZmqLink, ZmqConsole, ZmqMarks):
```

In `tests/test_cli.py`, in `test_wlx_run_refuses_a_malformed_link_value`, replace:

```python
    remainder -- as the REP endpoint rather than refusing it. Exactly two
    comma-separated endpoints or refusal; nothing in between. Raised before any
    socket is touched, so this needs no real endpoint and no cleanup."""
    with pytest.raises(SystemExit, match="PUB,REP"):
```

with:

```python
    remainder -- as the REP endpoint rather than refusing it. Two or three
    comma-separated endpoints (P4d-2b b2a added the third, the mark endpoint) or
    refusal; nothing in between. Raised before any socket is touched, so this needs
    no real endpoint and no cleanup."""
    with pytest.raises(SystemExit, match="PUB,REP or PUB,REP,MARK"):
```

In `tests/test_cli.py`, in `test_wlx_run_refuses_a_malformed_link_value`, replace:

```python
                *_TASK_SETS,
                "--link", "tcp://127.0.0.1:1,tcp://127.0.0.1:2,tcp://127.0.0.1:3",
```

with:

```python
                *_TASK_SETS,
                "--link",
                "tcp://127.0.0.1:1,tcp://127.0.0.1:2,tcp://127.0.0.1:3,tcp://127.0.0.1:4",
```

In `tests/test_cli.py`, in `test_wlx_run_refuses_a_malformed_link_value`, replace:

```python
                "tcp://127.0.0.1:1,tcp://127.0.0.1:2,tcp://127.0.0.1:3,tcp://127.0.0.1:4",
            ]
        )


```

with:

```python
                "tcp://127.0.0.1:1,tcp://127.0.0.1:2,tcp://127.0.0.1:3,tcp://127.0.0.1:4",
            ]
        )


def test_wlx_run_binds_the_mark_endpoint_when_link_names_three(tmp_path, monkeypatch):
    """P4d-2b b2a: `--link PUB,REP,MARK` gives the session its mark socket, on the
    third endpoint; two endpoints still give it none, as in b1."""
    built = []

    class _SpyLink(ZmqLink):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            built.append(self)

    monkeypatch.setattr("wl_expcontroller.link.ZmqLink", _SpyLink)

    for session_id, link in (
        ("2027-01-14_31", "tcp://127.0.0.1:0,tcp://127.0.0.1:0,tcp://127.0.0.1:0"),
        ("2027-01-14_32", "tcp://127.0.0.1:0,tcp://127.0.0.1:0"),
    ):
        exit_code = main(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", BOUNDS,
                "--root", str(tmp_path),
                "--session-id", session_id,
                "--subject", "REFERENCE",
                "--out-of-cage-at", _hhmm(),
                "--delivered-today", "0",
                "--trials", "3",
                *_TASK_SETS,
                "--link", link,
            ]
        )
        assert exit_code == 0

    with_mark, without = built
    assert with_mark.mark_endpoint is not None
    assert with_mark.mark_endpoint.startswith("tcp://127.0.0.1:")
    assert without.mark_endpoint is None


```

In `tests/test_link.py`, replace:

```python
from wl_expcontroller.link import (
    REFUSAL_HISTORY,
```

with:

```python
from wl_expcontroller.link import (
    MARK_BYTES,
    REFUSAL_HISTORY,
```

In `tests/test_link.py`, replace:

```python
    CommandRefused,
    Mark,
```

with:

```python
    CommandRefused,
    FrameError,
    Mark,
```

In `tests/test_link.py`, replace:

```python
    Mark,
    Pause,
```

with:

```python
    Mark,
    NotDelivered,
    ParamRow,
    Pause,
```

In `tests/test_link.py`, replace:

```python
    Pause,
    Resume,
    ScheduleStop,
    FrameError,
    ParamRow,
```

with:

```python
    Pause,
```

In `tests/test_link.py`, replace:

```python
    RemoteBindRefused,
    SCHEMA,
```

with:

```python
    RemoteBindRefused,
    Resume,
    SCHEMA,
```

In `tests/test_link.py`, replace:

```python
    SCHEMA,
    Simulated,
```

with:

```python
    SCHEMA,
    ScheduleStop,
    Simulated,
```

In `tests/test_link.py`, replace:

```python
    ZmqLink,
    _decode_command,
```

with:

```python
    ZmqLink,
    ZmqMarks,
    _decode_command,
```

Append to `tests/test_link.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a: the mark signal (spec §5.1) -- a third loopback socket, checked once
# per frame, and read into a buffer the link already holds
# ---------------------------------------------------------------------------


def _marked_link(zmq_cleanup) -> ZmqLink:
    return zmq_cleanup(
        ZmqLink(
            pub_endpoint="tcp://127.0.0.1:0",
            rep_endpoint="tcp://127.0.0.1:0",
            mark_endpoint="tcp://127.0.0.1:0",
        )
    )


def _signalled(link, *, tries=200, pause=0.005) -> int:
    """`link.mark_signal()` until it answers a number, bounded as `_drain_until` is and
    for its reason: a signal just sent is not visible to the very next statement."""
    for _ in range(tries):
        mark = link.mark_signal()
        if mark:
            return mark
        time.sleep(pause)
    return 0


def test_a_mark_signal_reaches_the_rig_as_its_number(zmq_cleanup):
    """Spec §5.1: the signal is a fixed-size sequence number. `wlx serve` sends it the
    moment M is pressed, and `taskd` reads it in the frame it arrives."""
    link = _marked_link(zmq_cleanup)
    marks = zmq_cleanup(ZmqMarks(link.mark_endpoint))

    marks.signal(7)
    marks.signal(2**64 - 1)

    assert _signalled(link) == 7
    assert _signalled(link) == 2**64 - 1
    assert link.mark_signal() == 0, "each signal is read once"


def test_with_nothing_waiting_the_check_answers_zero_every_time(zmq_cleanup):
    link = _marked_link(zmq_cleanup)

    assert [link.mark_signal() for _ in range(1000)] == [0] * 1000


def test_the_per_frame_check_keeps_nothing_it_allocates(zmq_cleanup):
    """Hot-path discipline (CLAUDE.md): the check runs every frame, so it must not
    leave memory behind. Measured with `tracemalloc` over ten thousand checks with
    nothing waiting: what is allocated and still held afterwards is nothing. What it
    costs per frame in time is `tools/measure_mark_check.py`'s to say, not this
    test's."""
    import tracemalloc

    link = _marked_link(zmq_cleanup)
    check = link.mark_signal
    for _ in range(100):
        check()
    tracemalloc.start()
    try:
        before = tracemalloc.take_snapshot()
        for _ in range(10_000):
            check()
        after = tracemalloc.take_snapshot()
    finally:
        tracemalloc.stop()

    import wl_expcontroller.link as link_module

    held = [
        stat
        for stat in after.compare_to(before, "filename")
        if stat.size_diff > 0 and stat.traceback[0].filename == link_module.__file__
    ]
    assert held == []


def test_a_link_given_no_mark_endpoint_has_no_mark_socket_and_answers_zero(zmq_cleanup):
    """`wlx run --link PUB,REP` still works as it did (P4d-2b b1): no third socket,
    and a check that answers zero and never blocks."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))

    assert link.mark_endpoint is None
    assert link.mark_signal() == 0


def test_a_signal_that_is_not_eight_bytes_naming_a_mark_is_refused_at_the_next_drain(
    zmq_cleanup,
):
    """A malformed signal is not a mark, and it is not dropped silently either: the
    frame only counts it (one integer, no list to grow mid-trial) and `drain`, at the
    boundary, turns the count into one refusal a console shows."""
    link = _marked_link(zmq_cleanup)
    raw = zmq_cleanup(ZmqMarks(link.mark_endpoint))
    raw._push.send(b"abc")
    raw._push.send(bytes(MARK_BYTES))  # eight bytes, but zero is never a mark
    raw._push.send(b"x" * 20)
    raw.signal(9)

    assert _signalled(link) == 9
    assert link.mark_signal() == 0
    assert link.drain() == []
    (refusal,) = link.refused
    assert refusal.name == "mark"
    assert refusal.why.startswith("3 mark signal(s) were not eight bytes naming a mark")
    assert link.mark_malformed == 0, "the count is spent once it is refused"


def test_idle_hands_back_a_mark_as_soon_as_it_arrives(zmq_cleanup):
    """While paused, the loop waits in `idle`, and a mark is stamped the moment it
    arrives rather than at the end of the wait. Bounded by the wait itself."""
    link = _marked_link(zmq_cleanup)
    marks = zmq_cleanup(ZmqMarks(link.mark_endpoint))

    marks.signal(11)
    started = time.monotonic()
    mark = link.idle(5.0)

    assert mark == 11
    assert time.monotonic() - started < 4.0, "idle waited out its timeout with a mark waiting"


def test_idle_wakes_for_a_command_and_leaves_it_for_drain(zmq_cleanup):
    link = _marked_link(zmq_cleanup)
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0))

    console.send(Resume(by="jake"))
    started = time.monotonic()
    mark = link.idle(5.0)

    assert mark == 0
    assert time.monotonic() - started < 4.0, "idle waited out its timeout with a command waiting"
    assert _drain_until(link) == [Resume(by="jake")]


def test_idle_with_nothing_arriving_waits_its_timeout_and_answers_zero(zmq_cleanup):
    link = _marked_link(zmq_cleanup)

    started = time.monotonic()
    assert link.idle(0.05) == 0
    assert time.monotonic() - started >= 0.04


def test_the_mark_endpoint_is_refused_where_other_hosts_can_reach_it():
    """The mark socket is a third door into the session, and gets the first two's
    rule: loopback unless `allow_remote` says otherwise."""
    with pytest.raises(RemoteBindRefused, match="PULL"):
        ZmqLink(
            pub_endpoint="tcp://127.0.0.1:0",
            rep_endpoint="tcp://127.0.0.1:0",
            mark_endpoint="tcp://0.0.0.0:0",
        )


def test_close_releases_the_mark_socket_too(zmq_cleanup):
    link = _marked_link(zmq_cleanup)
    marks = zmq_cleanup(ZmqMarks(link.mark_endpoint))

    link.close()
    marks.close()

    assert link._mark.closed and link._ctx.closed
    assert marks._push.closed and marks._ctx.closed


def test_an_unclosed_link_with_a_mark_socket_is_released_by_the_collector():
    """Ruling 18, for the third socket: it is appended to the list the finalizer
    holds the moment it exists, or collecting an unclosed link hangs on it."""
    with _collector_paused():
        link = ZmqLink(
            pub_endpoint="tcp://127.0.0.1:0",
            rep_endpoint="tcp://127.0.0.1:0",
            mark_endpoint="tcp://127.0.0.1:0",
        )
        link._cycle = link
        ctx = link._ctx
        sockets = [weakref.ref(link._pub), weakref.ref(link._rep), weakref.ref(link._mark)]
        del link

        returned = _collected_within(10.0)

    assert returned, "collecting an unclosed ZmqLink with a mark socket hung for 10 s"
    assert ctx.closed
    assert all(ref() is None for ref in sockets)


def test_an_unclosed_mark_sender_is_released_by_the_collector(zmq_cleanup):
    link = _marked_link(zmq_cleanup)
    with _collector_paused():
        marks = ZmqMarks(link.mark_endpoint)
        marks._cycle = marks
        ctx = marks._ctx
        push = weakref.ref(marks._push)
        del marks

        returned = _collected_within(10.0)

    assert returned, "collecting an unclosed ZmqMarks in a reference cycle hung for 10 s"
    assert ctx.closed
    assert push() is None


def test_a_mark_with_no_rig_to_reach_is_not_delivered_and_says_so(zmq_cleanup):
    """`wlx serve` tells the page the truth (spec §5.3): with no rig on the mark
    endpoint the signal is refused at once, not queued for a session that is gone.
    `IMMEDIATE` makes the socket queue only to a completed connection."""
    probe = _marked_link(zmq_cleanup)
    endpoint = probe.mark_endpoint
    probe.close()
    marks = zmq_cleanup(ZmqMarks(endpoint, connect_timeout_s=0.1))

    with pytest.raises(NotDelivered, match="no rig is listening"):
        marks.signal(3)


@pytest.mark.parametrize("mark", [0, -1, 2**64, True])
def test_a_mark_number_that_is_not_one_is_refused_before_it_is_sent(zmq_cleanup, mark):
    link = _marked_link(zmq_cleanup)
    marks = zmq_cleanup(ZmqMarks(link.mark_endpoint))

    with pytest.raises(ValueError, match="mark number"):
        marks.signal(mark)


def test_absent_has_no_marks_and_idle_waits_it_out():
    link = Absent()

    assert link.mark_signal() == 0
    started = time.monotonic()
    assert link.idle(0.02) == 0
    assert time.monotonic() - started >= 0.015


def test_simulated_hands_over_each_queued_mark_once():
    link = Simulated()
    link.marks.extend([4, 5])

    assert link.mark_signal() == 4
    assert link.idle(10.0) == 5, "a simulated idle never waits"
    assert link.mark_signal() == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_cli.py tests/test_serve.py`
Expected: all three fail to collect — `ImportError: cannot import name 'MARK_BYTES'` in `test_link.py`, and `cannot import name 'ZmqMarks'` through `tests/_zmq_release.py` in `test_cli.py` and `test_serve.py`.

- [ ] **Step 3: Implement**

In `docs/design/decisions/ADR-0004-license.md`, replace:

```markdown
| `pyyaml` >= 6 (contract extra) | MIT | Only so `wl-preproc`'s own `eye/expcontroller.py` can be imported by the contract tests, which read YAML. Never installed on a rig, and deliberately not `pip install -e ./wl-preproc`, which would pull DataJoint, Kilosort and SpikeInterface |
| `pyzmq` >= 26 (console extra) | BSD-3-Clause (pypi.org/pypi/pyzmq/json `.info.license_expression`, verified 2026-09-19) | ADR-0003's control/telemetry transport (ZeroMQ PUB/SUB + REQ/REP), accepted 2026-08-31. Extra, not core: a terminal-only rig needs neither this nor msgpack |
```

with:

```markdown
| `pyyaml` >= 6 (contract extra) | MIT | Only so `wl-preproc`'s own `eye/expcontroller.py` can be imported by the contract tests, which read YAML. Never installed on a rig, and deliberately not `pip install -e ./wl-preproc`, which would pull DataJoint, Kilosort and SpikeInterface |
| `pyzmq` >= 26.4 (console extra) | BSD-3-Clause (pypi.org/pypi/pyzmq/json `.info.license_expression`, verified 2026-09-19) | ADR-0003's control/telemetry transport (ZeroMQ PUB/SUB + REQ/REP), accepted 2026-08-31. Extra, not core: a terminal-only rig needs neither this nor msgpack. **Floor raised from 26 to 26.4 on 2026-09-27** (P4d-2b b2a): the mark signal is read with `Socket.recv_into`, added in 26.4 (pyzmq 27.2.0's `zmq/backend/cython/_zmq.py`, `.. versionadded:: 26.4`, read 2026-09-27). Same package, same license; no new dependency |
```

In `pyproject.toml`, replace:

```toml
# stronger of the two.
console = ["pyzmq>=26", "msgpack>=1"]
```

with:

```toml
# stronger of the two.
#
# `pyzmq>=26.4`, not 26 (P4d-2b b2a): `link.ZmqLink.mark_signal` reads a mark into a
# buffer it already holds with `Socket.recv_into`, which pyzmq added in 26.4
# (`zmq/backend/cython/_zmq.py`'s `recv_into`, `.. versionadded:: 26.4`, read in
# pyzmq 27.2.0 on 2026-09-27).
console = ["pyzmq>=26.4", "msgpack>=1"]
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
        metavar="PUB,REP",
        help="open a console link on two endpoints THIS SESSION binds: first the "
```

with:

```python
        metavar="PUB,REP[,MARK]",
        help="open a console link on endpoints THIS SESSION binds: first the "
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
        "receives commands on, e.g. "
        "tcp://127.0.0.1:5571,tcp://127.0.0.1:5572. A console attaches to the "
        "same pair from the other side, passing the first to `wlx console "
        "--sub` and the second to `--req`. Loopback only unless "
        "--link-allow-remote is also given. Omitted, the session runs with no "
        "console attached -- exactly as it did before this option existed, and "
        "with no transport dependency acquired",
```

with:

```python
        "receives commands on, and optionally a third, the MARK endpoint an "
        "operator's mark signal arrives on, e.g. "
        "tcp://127.0.0.1:5571,tcp://127.0.0.1:5572,tcp://127.0.0.1:5573. A "
        "console attaches from the other side: `wlx console --sub` takes the "
        "first and `--req` the second, and `wlx serve --link` takes the same "
        "value as given here. Without MARK the session takes no marks. Loopback "
        "only unless --link-allow-remote is also given. Omitted, the session runs "
        "with no console attached -- exactly as it did before this option "
        "existed, and with no transport dependency acquired",
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
            # two comma-separated parts.
            link_parts = args.link.split(",")
```

with:

```python
            # two comma-separated parts.
            #
            # P4d-2b b2a: a third endpoint, the mark socket, is optional, so a
            # `--link PUB,REP` written for b1 runs as it did.
            link_parts = args.link.split(",")
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
            link_parts = args.link.split(",")
            if len(link_parts) != 2:
```

with:

```python
            link_parts = args.link.split(",")
            if len(link_parts) not in (2, 3):
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
                    f"--link expects PUB,REP (exactly two comma-separated "
                    f"endpoints), got {args.link!r}"
```

with:

```python
                    f"--link expects PUB,REP or PUB,REP,MARK (two or three "
                    f"comma-separated endpoints), got {args.link!r}"
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
                )
            pub_endpoint, rep_endpoint = link_parts
```

with:

```python
                )
            pub_endpoint, rep_endpoint, *mark = link_parts
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
                link_cm = _link.ZmqLink(
                    pub_endpoint, rep_endpoint, allow_remote=args.link_allow_remote
```

with:

```python
                link_cm = _link.ZmqLink(
                    pub_endpoint,
                    rep_endpoint,
                    mark[0] if mark else None,
                    allow_remote=args.link_allow_remote,
```

In `wl_expcontroller/link.py`, replace:

```python
SCHEDULE_KINDS = ("clock", "trials", "fluid")
#: The largest mark number: the signal is eight bytes, unsigned.
```

with:

```python
SCHEDULE_KINDS = ("clock", "trials", "fluid")
#: The mark signal's size: one unsigned number, big-endian (spec §5.1: "a
#: fixed-size sequence number").
MARK_BYTES = 8
#: The largest mark number: the signal is eight bytes, unsigned.
```

In `wl_expcontroller/link.py`, in `Link.drain`, replace:

```python
        command is returned once."""


```

with:

```python
        command is returned once."""

    def mark_signal(self) -> int:
        """The number of one mark signal waiting, or `0` when none is (P4d-2b spec
        §5.1). **Called once per frame** by the trial loop, and at every trial
        boundary: it never blocks, does bounded work, and on a live link allocates
        nothing when no signal is waiting (`ZmqLink.mark_signal`). Each signal is
        returned once."""

    def idle(self, timeout: float) -> int:
        """**While paused**: wait up to `timeout` seconds for a console to say
        anything -- a mark signal or a command -- and return the mark's number if one
        arrived, else `0`. A command is left for `drain`. The paused loop's one wait,
        so a mark is stamped and a resume is read as soon as either arrives."""


```

In `wl_expcontroller/link.py`, in `Absent.drain`, replace:

```python
        return []


```

with:

```python
        return []

    def mark_signal(self) -> int:
        return 0

    def idle(self, timeout: float) -> int:
        """Nothing can arrive, so the wait is the whole of it. A session with no
        console is never paused -- nothing can send `Pause` -- so this is not
        reached; it waits rather than returning at once so that, if it ever were,
        a paused loop would not spin."""
        time.sleep(timeout)
        return 0


```

In `wl_expcontroller/link.py`, in `Simulated`, replace:

```python
    refused: list = field(default_factory=list)
    refused_dropped: int = 0

```

with:

```python
    refused: list = field(default_factory=list)
    refused_dropped: int = 0
    #: Mark signals a test has sent, oldest first: `mark_signal` and `idle` hand
    #: each over once (P4d-2b b2a).
    marks: list = field(default_factory=list)

```

In `wl_expcontroller/link.py`, in `Simulated.drain`, replace:

```python
        return taken

```

with:

```python
        return taken

    def mark_signal(self) -> int:
        return self.marks.pop(0) if self.marks else 0

    def idle(self, timeout: float) -> int:
        """Never waits: a simulated session's clocks are the test's, not this
        host's. A test that scripts what arrives while paused overrides this."""
        return self.mark_signal()

```

In `wl_expcontroller/link.py`, in `ZmqLink.__init__`, replace:

```python
    def __init__(
        self, pub_endpoint: str, rep_endpoint: str, *, allow_remote: bool = False
```

with:

```python
    def __init__(
        self,
        pub_endpoint: str,
        rep_endpoint: str,
        mark_endpoint: str | None = None,
        *,
        allow_remote: bool = False,
```

In `wl_expcontroller/link.py`, in `ZmqLink.__init__`, replace:

```python
    ):
        """Bind both sockets. **Loopback unless `allow_remote` says otherwise.**
```

with:

```python
    ):
        """Bind the sockets. **Loopback unless `allow_remote` says otherwise.**

        **A third, the mark socket, when `mark_endpoint` is given** (P4d-2b b2a): a
        PULL socket `mark_signal` checks once per frame, so an operator's mark is
        stamped in the frame it reaches the rig rather than at the next trial
        boundary (spec §5.0). Without it, this link has no marks, as in b1.
```

In `wl_expcontroller/link.py`, in `ZmqLink.__init__`, replace:

```python
            for role, endpoint in (("PUB", pub_endpoint), ("REP", rep_endpoint)):
                if _binds_beyond_this_machine(endpoint):
```

with:

```python
            for role, endpoint in (
                ("PUB", pub_endpoint),
                ("REP", rep_endpoint),
                ("PULL (mark)", mark_endpoint),
            ):
                if endpoint is not None and _binds_beyond_this_machine(endpoint):
```

In `wl_expcontroller/link.py`, in `ZmqLink.__init__`, replace:

```python
            self.rep_endpoint = self._rep.getsockopt_string(zmq.LAST_ENDPOINT)
        except BaseException:
```

with:

```python
            self.rep_endpoint = self._rep.getsockopt_string(zmq.LAST_ENDPOINT)

            #: The mark socket, or `None` for a link given no mark endpoint.
            self._mark = None
            #: What ZeroMQ bound it to, for `wlx serve`; `None` without one.
            self.mark_endpoint: str | None = None
            if mark_endpoint is not None:
                self._mark = self._ctx.socket(zmq.PULL)
                self._sockets.append(self._mark)
                self._mark.setsockopt(zmq.LINGER, 0)
                self._mark.bind(mark_endpoint)
                self.mark_endpoint = self._mark.getsockopt_string(zmq.LAST_ENDPOINT)
        except BaseException:
```

In `wl_expcontroller/link.py`, in `ZmqLink.__init__`, replace:

```python
        self.refused_dropped: int = 0

```

with:

```python
        self.refused_dropped: int = 0

        # **Plain `int`s, read once** (P4d-2b b2a), for `mark_signal`, which runs
        # every frame: `zmq.EVENTS` and `zmq.POLLIN` are enum members, and `&`
        # between an `int` and a `zmq.PollEvent` builds a new flag object through
        # the enum machinery on every call (a scratchpad `tracemalloc` probe,
        # 2026-09-27: 656 bytes left held over 100,000 checks in that form, none in
        # this one). Not a measurement of this system's timing.
        self._events = int(zmq.EVENTS)
        self._pollin = int(zmq.POLLIN)
        self._dontwait = int(zmq.DONTWAIT)
        #: Where a mark signal is read into: allocated once, here, so reading one
        #: allocates no bytes object (`Socket.recv_into`).
        self._mark_buffer = bytearray(MARK_BYTES)
        #: Signals `mark_signal` read and could not use -- the wrong size, or zero.
        #: Counted in the frame, where nothing may grow a list, and refused once at
        #: the next `drain()`.
        self.mark_malformed: int = 0

```

In `wl_expcontroller/link.py`, in `ZmqLink.drain`, replace:

```python
        commands: list[Command] = []
        while self._rep.poll(timeout=0, flags=zmq.POLLIN):
```

with:

```python
        commands: list[Command] = []
        if self.mark_malformed:
            # P4d-2b b2a: what `mark_signal` counted in the frame, said here once.
            self._refuse(
                Refused(
                    name="mark",
                    by="<unknown>",
                    why=(
                        f"{self.mark_malformed} mark signal(s) were not eight bytes "
                        f"naming a mark, and were ignored"
                    ),
                )
            )
            self.mark_malformed = 0
        while self._rep.poll(timeout=0, flags=zmq.POLLIN):
```

In `wl_expcontroller/link.py`, in `ZmqLink.drain`, replace:

```python
                self.refused.append(
                    Refused(name=refused.name, by=refused.by, why=refused.why)
                )
```

with:

```python
                self._refuse(Refused(name=refused.name, by=refused.by, why=refused.why))
```

In `wl_expcontroller/link.py`, in `ZmqLink.drain`, replace:

```python
            except Exception as exc:  # noqa: BLE001 -- deliberately broad, see above
                self.refused.append(
```

with:

```python
            except Exception as exc:  # noqa: BLE001 -- deliberately broad, see above
                self._refuse(
```

In `wl_expcontroller/link.py`, in `ZmqLink.drain`, replace:

```python
                )
                if len(self.refused) > REFUSAL_HISTORY:
                    self.refused_dropped += len(self.refused) - REFUSAL_HISTORY
                    del self.refused[:-REFUSAL_HISTORY]
```

with:

```python
                )
```

In `wl_expcontroller/link.py`, in `ZmqLink.drain`, replace:

```python
        return commands

```

with:

```python
        return commands

    def _refuse(self, refused: Refused) -> None:
        """One refusal onto `refused`, trimmed to `REFUSAL_HISTORY` -- see `drain`."""
        self.refused.append(refused)
        if len(self.refused) > REFUSAL_HISTORY:
            self.refused_dropped += len(self.refused) - REFUSAL_HISTORY
            del self.refused[:-REFUSAL_HISTORY]

    def mark_signal(self) -> int:
        """The number of one mark signal waiting, or `0` (the `Link` protocol).

        **The per-frame check, and the only one** (P4d-2b spec §5.1): with nothing
        waiting it is one `getsockopt(EVENTS)` -- a C call answering a small integer
        -- and one `&`. `EVENTS` reads the socket's state without blocking;
        `POLLIN` in it means a whole message is waiting. Only then is anything
        received, and into `_mark_buffer`, which this link allocated once.

        Source, read 2026-09-27, pyzmq 27.2.0 as installed in this repository's
        venv: `zmq/sugar/socket.py:376` makes `getsockopt` `SocketBase.get`;
        `zmq/backend/cython/_zmq.py:853` is `Socket.get`, which for an `int` option
        calls `zmq_getsockopt` into a C `int` and returns it; `_zmq.py:1264` is
        `Socket.recv_into`, "storing the data into a buffer rather than allocating
        a new Frame", `.. versionadded:: 26.4`, returning "the size of the received
        frame" even when that is larger than the buffer, which is how an oversize
        signal is told from a mark. The console extra's floor is `pyzmq>=26.4` for
        it (`pyproject.toml`).

        **One signal per frame**: a second waiting is read on the next frame, and
        its stamp names that frame. Bounded work, whatever arrives."""
        mark = self._mark
        if mark is None or not mark.getsockopt(self._events) & self._pollin:
            return 0
        return self._take_mark()

    def _take_mark(self) -> int:
        """Read one waiting signal into `_mark_buffer`: its number, or `0` -- counted
        in `mark_malformed` -- when it is not eight bytes naming a mark. Called only
        with a signal waiting, from a frame or from `idle`."""
        size = self._mark.recv_into(self._mark_buffer, flags=self._dontwait)
        if size != MARK_BYTES:
            self.mark_malformed += 1
            return 0
        number = int.from_bytes(self._mark_buffer, "big")
        if number == 0:
            self.mark_malformed += 1
        return number

    def idle(self, timeout: float) -> int:
        """Wait up to `timeout` seconds for a mark signal or a command, whichever
        comes first (the `Link` protocol). A `zmq.Poller` over the REP socket and,
        when there is one, the mark socket: built per call, which is allowed here --
        this runs while paused, never inside a frame."""
        import zmq

        poller = zmq.Poller()
        poller.register(self._rep, zmq.POLLIN)
        if self._mark is not None:
            poller.register(self._mark, zmq.POLLIN)
        ready = dict(poller.poll(int(timeout * 1000)))
        if self._mark is not None and ready.get(self._mark):
            return self._take_mark()
        return 0

```

Append to `wl_expcontroller/link.py`:

```python


class NotDelivered(Exception):
    """A command or a mark signal that did not reach the rig (P4d-2b spec §5.3: the
    page is told the truth about delivery). The message is a sentence a console
    shows as it is."""


#: How long a console's sender waits for its connection to the rig before it says a
#: command or a mark was not delivered. ZeroMQ connects in the background, so a
#: sender built a moment ago, or rebuilt after a timeout, may not be connected yet.
#: Housekeeping, not a measurement of this system.
CONNECT_TIMEOUT_S = 1.0


class ZmqMarks:
    """The console side of the mark signal (P4d-2b b2a): a PUSH socket connected to
    the session's mark endpoint, which `wlx serve`'s mark thread owns.

    **Ahead of every command** (spec §5.3): the signal goes on its own socket, so a
    mark never waits behind a command whose acknowledgment has not come back.

    **`IMMEDIATE`**, so a signal is queued only to a completed connection: with no
    rig listening, `signal` says so instead of queuing a mark for a session that is
    not there (checked in a scratchpad probe 2026-09-27, and pinned by
    `test_a_mark_with_no_rig_to_reach_is_not_delivered_and_says_so`). A PUSH socket
    has no reply, so *delivered* here means handed to a connected rig's socket, and
    the stamp -- in the session record and on the feed -- is what says it landed.

    Released the way `ZmqLink` and `ZmqConsole` are: `_release`, from `close()` or
    from its finalizer, with its one socket in the list the finalizer holds.
    """

    def __init__(self, mark_endpoint: str, connect_timeout_s: float = CONNECT_TIMEOUT_S):
        import zmq

        self._ctx = zmq.Context()
        self._sockets: list = []
        self._finalizer = weakref.finalize(self, _release, self._ctx, self._sockets)
        self._push = self._ctx.socket(zmq.PUSH)
        self._sockets.append(self._push)
        self._push.setsockopt(zmq.LINGER, 0)
        self._push.setsockopt(zmq.IMMEDIATE, 1)
        self._push.connect(mark_endpoint)
        #: Where this sends, named in the sentence a failed signal raises.
        self.endpoint = mark_endpoint
        self._connect_ms = int(connect_timeout_s * 1000)

    def signal(self, mark: int) -> None:
        """Send `mark`, eight bytes big-endian. Raises `NotDelivered` when no rig is
        connected within the connect timeout, and `ValueError` for a number that is
        not a mark, before anything is sent."""
        import zmq

        if isinstance(mark, bool) or not isinstance(mark, int) or not 1 <= mark <= MARK_LIMIT:
            raise ValueError(f"a mark number is 1 to {MARK_LIMIT}, and {mark!r} is not one")
        if not self._push.poll(self._connect_ms, zmq.POLLOUT):
            raise NotDelivered(f"no rig is listening for marks on {self.endpoint}")
        try:
            self._push.send(mark.to_bytes(MARK_BYTES, "big"), flags=zmq.DONTWAIT)
        except zmq.Again as exc:
            raise NotDelivered(
                f"no rig is listening for marks on {self.endpoint}"
            ) from exc

    def close(self) -> None:
        """See `ZmqLink.close` -- same reasoning, same shape."""
        _release(self._ctx, self._sockets)
        self._finalizer.detach()

    def __enter__(self) -> "ZmqMarks":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_cli.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1201 passed**, and `tests/test_no_transport_leak.py` still passes (`link` imports `zmq` only inside functions).

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/cli.py pyproject.toml docs/design/decisions/ADR-0004-license.md tests/test_link.py tests/test_cli.py tests/_zmq_release.py
git commit -m "Give the link a mark socket the trial loop can check once per frame without allocating"
```

---

### Task 4: Commands that know whether they arrived

**Why:** spec §5.3: the page is told *sent* only when `taskd` has acknowledged receipt, *not delivered* when the REQ exchange times out — after which the socket is reset, since a REQ socket cannot send twice without a reply — and spec §2: each ZMQ socket has one owning thread. `ZmqConsole.send` reads each reply one send behind, which suits `wlx console` and cannot say whether a command arrived. `ZmqCommands` is the sender for `wlx serve`'s command thread (Task 11), and `ZmqConsole` learns to be built read-only, for its telemetry thread (Plan decision 10).

**Files:**
- Modify: `wl_expcontroller/link.py` (`ZmqConsole.__init__`, `ZmqConsole.send`; `REPLY_TIMEOUT_S`, `ZmqCommands`)
- Test: `tests/test_link.py`, `tests/_zmq_release.py`

**Interfaces:**
- Consumes: Task 2's commands, Task 3's `NotDelivered` and `CONNECT_TIMEOUT_S`.
- Produces:
  - `link.REPLY_TIMEOUT_S = 15.0`.
  - `link.ZmqCommands(req_endpoint: str, reply_timeout_s: float = REPLY_TIMEOUT_S, connect_timeout_s: float = CONNECT_TIMEOUT_S)`, `.deliver(command) -> None` (returns once acknowledged; raises `NotDelivered` otherwise), `.endpoint`, `.close()`.
  - `ZmqConsole(pub_endpoint: str, req_endpoint: str | None, ...)`: with `None`, no REQ socket, and `send` raises `RuntimeError`.

- [ ] **Step 1: Write the failing tests**

In `tests/_zmq_release.py`, replace:

```python
"""Every `ZmqLink`, `ZmqConsole` and `ZmqMarks` a test builds is held until its
teardown, and its `Context` is destroyed there directly. That includes the ones built where the test has
```

with:

```python
"""Every `ZmqLink`, `ZmqConsole`, `ZmqCommands` and `ZmqMarks` a test builds is held
until its teardown, and its `Context` is destroyed there directly. That includes the ones built where the test has
```

In `tests/_zmq_release.py`, replace:

```python

from wl_expcontroller.link import ZmqConsole, ZmqLink, ZmqMarks
```

with:

```python

from wl_expcontroller.link import ZmqCommands, ZmqConsole, ZmqLink, ZmqMarks
```

In `tests/_zmq_release.py`, in `_every_zmq_context_released`, replace:

```python
    """Wrap `ZmqLink.__init__`, `ZmqConsole.__init__` and `ZmqMarks.__init__` (P4d-2b
    b2a: `wlx serve`'s mark thread builds one) to record each object and the thread
    that built it. At teardown, destroy each context directly with `linger=0`."""
```

with:

```python
    """Wrap the `__init__` of `ZmqLink`, `ZmqConsole`, `ZmqCommands` and `ZmqMarks`
    (P4d-2b b2a: `wlx serve`'s command and mark threads build the last two) to record
    each object and the thread that built it. At teardown, destroy each context
    directly with `linger=0`."""
```

In `tests/_zmq_release.py`, in `_every_zmq_context_released`, replace:

```python

    for cls in (ZmqLink, ZmqConsole, ZmqMarks):
```

with:

```python

    for cls in (ZmqLink, ZmqConsole, ZmqCommands, ZmqMarks):
```

In `tests/test_link.py`, replace:

```python
    Telemetry,
    ZmqConsole,
```

with:

```python
    Telemetry,
    ZmqCommands,
    ZmqConsole,
```

Append to `tests/test_link.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a: a command that knows whether it arrived (spec §5.3)
# ---------------------------------------------------------------------------


def _draining(link, until=None, seconds: float = 5.0) -> tuple[threading.Thread, list]:
    """Drain `link` on a thread, as `taskd` would at its boundaries, until `until` has
    arrived -- or any command, when `until` is `None` -- or `seconds` pass. Bounded,
    so a broken sender fails a test rather than hanging it."""
    got: list = []

    def arrived() -> bool:
        return until in got if until is not None else bool(got)

    def run() -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not arrived():
            got.extend(link.drain())
            time.sleep(0.005)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, got


def test_a_command_is_delivered_once_the_rig_acknowledges_it(zmq_cleanup):
    """*Sent* means `taskd` acknowledged receipt (spec §5.3): `deliver` returns only
    after the rig's `drain` has replied."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    commands = zmq_cleanup(ZmqCommands(link.rep_endpoint, reply_timeout_s=5.0))
    thread, got = _draining(link)

    commands.deliver(Pause(by="jake (box, unverified)"))
    thread.join(timeout=10)

    assert got == [Pause(by="jake (box, unverified)")]


def test_with_no_rig_connected_a_command_is_not_delivered(zmq_cleanup):
    """With `taskd` gone the page is told *not delivered* (spec §5.4), and it is told
    once the connect timeout passes, not after a reply timeout: `IMMEDIATE` queues a
    message only to a completed connection, so there is nothing to wait a reply for."""
    probe = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    endpoint = probe.rep_endpoint
    probe.close()
    commands = zmq_cleanup(ZmqCommands(endpoint, reply_timeout_s=30.0, connect_timeout_s=0.1))

    started = time.monotonic()
    with pytest.raises(NotDelivered, match="no rig is connected"):
        commands.deliver(Stop(by="jake"))
    assert time.monotonic() - started < 10.0, "it waited out the reply timeout"


def test_a_rig_that_never_acknowledges_is_not_delivered_and_the_socket_is_reset(zmq_cleanup):
    """*Not delivered* when the exchange times out, **after which the socket is reset**
    (spec §5.3): a REQ socket cannot send again until it reads a reply, so without the
    reset every later command would raise instead of being sent. The rig here is a
    live link nobody drains until the second command."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    commands = zmq_cleanup(ZmqCommands(link.rep_endpoint, reply_timeout_s=0.2))
    first = commands._req

    with pytest.raises(NotDelivered, match="did not acknowledge it within 0.2 s"):
        commands.deliver(Pause(by="jake"))

    assert first.closed, "the timed-out socket was not closed"
    assert commands._req is not first
    assert commands._sockets == [commands._req], "a reset must not grow the release list"

    thread, got = _draining(link, until=Resume(by="jake"))
    commands.deliver(Resume(by="jake"))
    thread.join(timeout=10)
    # The first command was already on the rig's side of the wire, so it may still be
    # drained: a timed-out command is *not acknowledged*, not unsent, which is why
    # the page is told to watch the feed (serve.NOT_DELIVERED).
    assert Resume(by="jake") in got


def test_an_unclosed_command_sender_is_released_by_the_collector(zmq_cleanup):
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    with _collector_paused():
        commands = ZmqCommands(link.rep_endpoint)
        commands._cycle = commands
        ctx = commands._ctx
        req = weakref.ref(commands._req)
        del commands

        returned = _collected_within(10.0)

    assert returned, "collecting an unclosed ZmqCommands in a reference cycle hung for 10 s"
    assert ctx.closed
    assert req() is None


def test_close_releases_the_command_socket(zmq_cleanup):
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    commands = zmq_cleanup(ZmqCommands(link.rep_endpoint))

    commands.close()

    assert commands._req.closed and commands._ctx.closed


def test_a_console_built_to_read_only_has_no_command_socket(zmq_cleanup):
    """`wlx serve`'s telemetry thread reads and never sends (P4d-2b b2a): the REQ
    socket belongs to its command thread, so each socket has one owning thread
    (spec §2). A console given no REQ endpoint opens none, and refuses to send."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, None, settle_s=0))

    assert console._req is None
    assert len(console._sockets) == 1
    with pytest.raises(RuntimeError, match="no command endpoint"):
        console.send(Stop(by="jake"))
    link.publish(_telemetry())
    console.close()
    assert console._sub.closed and console._ctx.closed
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py`
Expected: fails to collect — `ImportError: cannot import name 'ZmqCommands'`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/link.py`, in `ZmqConsole.__init__`, replace:

```python
        pub_endpoint: str,
        req_endpoint: str,
```

with:

```python
        pub_endpoint: str,
        req_endpoint: str | None,
```

In `wl_expcontroller/link.py`, in `ZmqConsole.__init__`, replace:

```python
    ):
        import zmq
```

with:

```python
    ):
        """Connect SUB to `pub_endpoint` and REQ to `req_endpoint`.

        **`req_endpoint` may be `None`** (P4d-2b b2a): a console that only reads --
        `wlx serve`'s telemetry thread, whose commands go through `ZmqCommands` on a
        thread of their own, so that each socket has one owning thread (spec §2) --
        opens no REQ socket, and `send` refuses."""
        import zmq
```

In `wl_expcontroller/link.py`, in `ZmqConsole.__init__`, replace:

```python
        self._req = self._ctx.socket(zmq.REQ)
        self._sockets.append(self._req)
        self._req.setsockopt(zmq.LINGER, 0)
        # Same ceiling as the SUB socket above, same reasoning -- see send()'s
        # docstring for why a bounded read happens there at all.
        self._req.setsockopt(zmq.RCVTIMEO, 5000)
        self._req.connect(req_endpoint)
```

with:

```python
        self._req = None
        if req_endpoint is not None:
            self._req = self._ctx.socket(zmq.REQ)
            self._sockets.append(self._req)
            self._req.setsockopt(zmq.LINGER, 0)
            # Same ceiling as the SUB socket above, same reasoning -- see send()'s
            # docstring for why a bounded read happens there at all.
            self._req.setsockopt(zmq.RCVTIMEO, 5000)
            self._req.connect(req_endpoint)
```

In `wl_expcontroller/link.py`, in `ZmqConsole.send`, replace:

```python

        if self._awaiting_reply:
```

with:

```python

        if self._req is None:
            raise RuntimeError(
                "this console was built to read only, with no command endpoint, so it "
                "cannot send"
            )
        if self._awaiting_reply:
```

Append to `wl_expcontroller/link.py`:

```python


#: How long `wlx serve` waits for the rig to acknowledge a command before it tells
#: the page the command was not delivered. `taskd` reads commands only at a trial
#: boundary (P4d-2b spec §5.1) -- and once per housekeeping interval while paused --
#: so this has to outlast a trial, and a reply can take that long on a working rig.
#: A responsiveness choice, not a measurement of this system.
REPLY_TIMEOUT_S = 15.0


class ZmqCommands:
    """The console side of the command path, for a sender that must know whether each
    command arrived (P4d-2b b2a): `wlx serve`'s command thread owns one.

    `ZmqConsole.send` reads the previous reply lazily, one send behind, because `wlx
    console` sends and then watches on one thread. This reads each reply before
    `deliver` returns: the page is told *sent* only when `taskd` has acknowledged
    receipt, and *not delivered* when it has not (spec §5.3).

    **Two ways not to be delivered, told apart.** With `IMMEDIATE` set, the REQ socket
    queues only to a completed connection, so with no rig connected `deliver` says so
    once the connect timeout passes rather than waiting for a reply that cannot come
    (a scratchpad probe, 2026-09-27; pinned by
    `test_with_no_rig_connected_a_command_is_not_delivered`). With a rig connected and
    no reply within the reply timeout, the command **was handed over and was not
    acknowledged**: it may still be drained and applied at the rig's next boundary,
    which is why that sentence says so rather than calling it lost.

    **After a timeout the socket is reset** (spec §5.3): a REQ socket may not send
    again before it reads a reply, so the old one is closed and a new one opened and
    connected in its place, and removed from and added to the list the finalizer
    holds, so that list never grows.
    """

    def __init__(
        self,
        req_endpoint: str,
        reply_timeout_s: float = REPLY_TIMEOUT_S,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
    ):
        import zmq

        self._ctx = zmq.Context()
        self._sockets: list = []
        self._finalizer = weakref.finalize(self, _release, self._ctx, self._sockets)
        #: Where this sends, named in every sentence `deliver` raises.
        self.endpoint = req_endpoint
        self._reply_s = reply_timeout_s
        self._connect_ms = int(connect_timeout_s * 1000)
        self._req = self._open()

    def _open(self):
        """A REQ socket, appended to the release list the moment it exists."""
        import zmq

        req = self._ctx.socket(zmq.REQ)
        self._sockets.append(req)
        req.setsockopt(zmq.LINGER, 0)
        req.setsockopt(zmq.IMMEDIATE, 1)
        req.setsockopt(zmq.RCVTIMEO, int(self._reply_s * 1000))
        req.connect(self.endpoint)
        return req

    def deliver(self, command: Command) -> None:
        """Send `command` and wait for the rig's acknowledgment. Returns once it
        arrives; raises `NotDelivered` otherwise, with the sentence the page shows."""
        import zmq

        payload = _encode_command(command)
        if not self._req.poll(self._connect_ms, zmq.POLLOUT):
            raise NotDelivered(f"not delivered: no rig is connected on {self.endpoint}")
        try:
            self._req.send(payload, flags=zmq.DONTWAIT)
        except zmq.Again as exc:
            raise NotDelivered(
                f"not delivered: no rig is connected on {self.endpoint}"
            ) from exc
        try:
            self._req.recv()
        except zmq.Again as exc:
            self._reset()
            raise NotDelivered(
                f"not delivered: the rig did not acknowledge it within "
                f"{self._reply_s:g} s. It may still be applied at the rig's next trial "
                f"boundary; the changes feed will show it if it is"
            ) from exc

    def _reset(self) -> None:
        """Close the REQ socket that is owed a reply and open a fresh one."""
        old = self._req
        old.close(linger=0)
        self._sockets.remove(old)
        self._req = self._open()

    def close(self) -> None:
        """See `ZmqLink.close` -- same reasoning, same shape."""
        _release(self._ctx, self._sockets)
        self._finalizer.detach()

    def __enter__(self) -> "ZmqCommands":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py`
Expected: all pass — three times in a row, since the reset test drains on a thread.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1207 passed**.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py tests/test_link.py tests/_zmq_release.py
git commit -m "Add a command sender that waits for the rig's acknowledgment and resets after a timeout"
```

---

### Task 5: Pause and resume, and the record of every control

**Why:** spec §5.1: at the next trial boundary the loop holds — no trial runs, nothing is rewarded (since the PI's 2026-09-28 amendment: the task rewards nothing, and a person may give a manual reward, which Task 13 adds), the display shows the task's background — while once per housekeeping interval it still drains commands, publishes telemetry, and ends the session on the out-of-cage limit with `welfare.must_stop`, exactly as between trials; pause and resume are recorded and strobed so the recording shows the gap (Plan decision 5). This task also opens `controls.jsonl` (Plan decision 7) — with a row for a console's stop as well, since "every one is written to the session record with who sent it and when" and a stop was on disk nowhere — the feed a console shows (`Session.controls`, capped like the refusal feed), and the three framework event names (Plan decision 8).

**Files:**
- Modify: `tasks/allocation.py` (4131–4133)
- Modify: `wl_expcontroller/record.py` (`CONTROLS`, `SessionRecord.control`)
- Modify: `wl_expcontroller/link.py` (`CONTROL_HISTORY`)
- Modify: `wl_expcontroller/taskd.py` (import `_clock`; `PAUSE_HOUSEKEEPING_S`; `Session.paused_at`, `_controls`, `controls_dropped`; `controls`; `_control`, `_code`, `_pause`, `_resume`, `_ends`, `_hold`; `_command`; `run`'s loop)
- Test: `tests/test_taskd.py`

**Interfaces:**
- Consumes: Task 2's `Pause`, `Resume`; Task 3's `Link.idle`; `welfare.must_stop` unchanged.
- Produces:
  - `taskd.PAUSE_HOUSEKEEPING_S = 0.5`.
  - `Session.paused_at: float | None`; `Session.controls -> tuple` of `(kind, by, at, said)`; `Session.controls_dropped: int` — Task 8 publishes all three. Control kinds `stop`, `pause`, `resume`.
  - `Session._control(kind, by, said, index, **detail) -> float` (Task 6 adds `at=`; Task 7 renames `said` to `feed`); `Session._code(name) -> int | None`; `Session._pause(by, index)`, `_resume(by, index)`, `_ends() -> bool` (Task 7 gives it `index`), `_hold(index, publish)`.
  - `link.CONTROL_HISTORY = 50`; `record.CONTROLS = "controls.jsonl"`; `SessionRecord.control(kind, by, at, trial_index, **detail)`.
  - The allocation's `PAUSE` (4131), `RESUME` (4132), `OPERATOR_MARK` (4133).
  - Test helpers Tasks 6 and 7 use: `_Scripted` (a `Simulated` whose `idle` runs a script and fails after a budget of waits, and whose `drain` fails after `PASS_BUDGET` passes — Ruling 10 for a paused loop, and for one that stops waiting), `PASS_BUDGET`, `_walled`, `_controls_rows`, and `PAUSE_CODE`, `RESUME_CODE`, `MARK_CODE`.

**Why `_Scripted` counts drains as well as waits:** in the plan's pre-flight, `Session._hold` neutered sent the paused loop round the boundary with no trial and no `idle` — draining and publishing as fast as it could — so the wait budget never moved, and the suite hung until the mutation harness printed `caught … timed out`. Every pass drains, so a drain budget bounds it: the same mutant is `9 failed` in `tests/test_taskd.py`, in seconds.

- [ ] **Step 1: Write the failing tests**

In `tests/test_taskd.py`, replace:

```python
from wl_expcontroller.link import (
    RECENT_OUTCOMES,
```

with:

```python
from wl_expcontroller.link import (
    CONTROL_HISTORY,
    RECENT_OUTCOMES,
```

In `tests/test_taskd.py`, replace:

```python
    REFUSAL_HISTORY,
    SetParameter,
```

with:

```python
    REFUSAL_HISTORY,
    Pause,
    Resume,
    SetParameter,
```

In `tests/test_taskd.py`, replace:

```python
from wl_expcontroller.task import Outcome
from wl_expcontroller.taskd import Session, SessionSpec
```

with:

```python
from wl_expcontroller.task import Outcome
from wl_expcontroller.taskd import PAUSE_HOUSEKEEPING_S, Session, SessionSpec
```

Append to `tests/test_taskd.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a: pause and resume (spec §5.1)
# ---------------------------------------------------------------------------

#: The three framework codes b2a allocates (`tasks/allocation.py`).
PAUSE_CODE, RESUME_CODE, MARK_CODE = 4131, 4132, 4133

#: How many times a `_Scripted` session may drain its commands. The loop drains once
#: at each trial boundary and once in each paused wait, so these sessions -- a few
#: trials, at most a few hundred waits -- stay far below it.
PASS_BUDGET = 2_000


class _Scripted(Simulated):
    """A link whose `idle` -- the paused loop's one wait -- runs a script: on its Nth
    call it queues `script[N]`, moves `wall` on by `step` seconds, and calls `each`.

    **Ruling 10, for a paused loop**: a session still paused after `budget` waits
    fails -- `idle` raises, the session faults -- rather than holding the suite until
    the mutation harness kills it, which is what a neutered `Resume` would otherwise
    do here. **And for a paused loop that never waits**: with `Session._hold`
    neutered, the loop goes round the boundary draining and publishing with no trial
    and no `idle`, so neither budget moves and the suite hung until the harness's
    300 s; a session that drains more than `PASS_BUDGET` times fails the same way."""

    def __init__(self, script=None, wall=None, step=0.0, budget=200, each=None):
        super().__init__()
        self.script = dict(script or {})
        self.wall = wall
        self.step = step
        self.budget = budget
        self.each = each
        self.waits: list = []
        self.drains = 0

    def drain(self) -> list:
        self.drains += 1
        if self.drains > PASS_BUDGET:
            raise RuntimeError(
                f"drained {PASS_BUDGET} times: the loop is going round with no trial "
                f"and no wait (tests/test_taskd.py, Ruling 10)"
            )
        return super().drain()

    def idle(self, timeout: float) -> int:
        self.waits.append(timeout)
        if len(self.waits) > self.budget:
            raise RuntimeError(
                f"still paused after {self.budget} waits: nothing ended the pause "
                f"(tests/test_taskd.py, Ruling 10)"
            )
        if self.wall is not None:
            self.wall.at += self.step
        for command in self.script.get(len(self.waits), ()):
            self.queue(command)
        if self.each is not None:
            self.each()
        return super().idle(timeout)


def _walled(tmp_path, link, *, trials: int = 5, **spec) -> tuple[Session, "_Wall"]:
    """A head-fixed session whose wall follows its frames while trials run and moves
    only when a test moves it while paused (`_Scripted.step`)."""
    wall = _Wall(WALL_NOW)
    session = Session(
        _spec(tmp_path, trials=trials, **spec),
        card=Card(),
        pump=Pump(),
        link=link,
        wall_clock=wall,
    )
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=wall())
    # The frames' seconds, on top of wherever `at` stands: a paused wait moves `at`.
    wall.follow = session.now
    return session, wall


def _controls_rows(session: Session) -> list[dict]:
    path = session.directory / "controls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_pause_holds_the_session_at_a_boundary_and_resume_continues(tmp_path):
    """Spec §5.1: at the next trial boundary the loop holds -- no trial runs -- and
    resume continues. Both are strobed so the recording shows the gap, and nothing
    else is strobed inside it."""
    link = _Scripted(script={3: [Resume(by="sam")]}, step=30.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "completed"
    assert len(link.waits) == 3
    codes = session.card.codes
    assert codes.count(PAUSE_CODE) == 1 and codes.count(RESUME_CODE) == 1
    assert codes.index(RESUME_CODE) == codes.index(PAUSE_CODE) + 1, (
        "something was strobed while paused: a trial ran"
    )
    trials = (session.directory / "trials.jsonl").read_text().splitlines()
    assert len(trials) == 5
    held = [frame.trial_index for frame in link.published if frame.trial_index == 0]
    assert len(held) >= 4, "the paused loop published once per wait at trial 0"


def test_pause_and_resume_are_recorded_with_who_and_when(tmp_path):
    """Spec §5.1: every control is written to the session record with who sent it and
    when -- the instant on the session's anchored clock, as a number and as a clock
    time."""
    link = _Scripted(script={3: [Resume(by="sam")]}, step=30.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    pause, resume = _controls_rows(session)
    assert (pause["kind"], pause["by"], pause["trial_index"]) == ("pause", "jake", 0)
    assert (resume["kind"], resume["by"], resume["trial_index"]) == ("resume", "sam", 0)
    assert resume["paused_s"] == pytest.approx(90.0)
    assert resume["at"] - pause["at"] == pytest.approx(90.0)
    assert pause["at_local"].endswith("local")


def test_a_stop_is_recorded_with_who_and_when(tmp_path):
    """Spec §5.1: every control is written to the session record with who sent it and
    when. A console's stop was in telemetry and at the terminal and nowhere on disk."""
    link = Simulated()
    link.queue(Stop(by="sam"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    (row,) = _controls_rows(session)
    assert (row["kind"], row["by"], row["trial_index"]) == ("stop", "sam", 0)
    assert row["at"] == WALL_NOW
    assert session.controls[0][3] == "stopped by sam"


def test_nothing_is_rewarded_while_paused(tmp_path):
    """Human review item 1 (spec §5.5): while paused, nothing is rewarded. No trial
    runs, so no `Reward` action reaches the pump, and the session's fluid stands
    still. Paused after six trials, so what stands still is not zero."""
    seen: list = []
    link = _Scripted(script={4: [Resume(by="jake")]}, step=10.0)
    session, wall = _walled(tmp_path, link, trials=9)
    link.wall = wall
    link.each = lambda: seen.append(
        (
            session.welfare.session_total(),
            session.welfare.deliveries,
            len(session.pump.delivered),
        )
    )
    ran = [0]

    def pause_after_six(condition, values, result) -> None:
        ran[0] += 1
        if ran[0] == 6:
            link.queue(Pause(by="jake"))

    session.observe = pause_after_six

    session.run()

    assert len(seen) == 4
    assert seen[0][0] > 0.0, "choose a pause point after a reward"
    assert len(set(seen)) == 1, f"fluid moved while paused: {seen}"


def test_the_out_of_cage_limit_still_ends_a_paused_session(tmp_path):
    """Human review item 1 (spec §5.5): the out-of-cage clock keeps running while
    paused, and `welfare.must_stop` still ends the session on it, exactly as between
    trials. The wall moves five minutes per wait; `_bounds()`' limit is 800 s."""
    link = _Scripted(step=300.0)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "limit"
    assert session.stopped_because.startswith("out_of_cage")
    assert len(link.waits) == 3, "800 s is past after the third five-minute wait"
    assert not (session.directory / "trials.jsonl").read_text().strip(), "no trial ran"
    clocks = [frame.out_of_cage_seconds for frame in link.published]
    assert clocks == sorted(clocks) and clocks[-1] > 800.0, "the clock kept running"
    assert link.published[-1].stop_kind == "limit"


def test_a_setting_staged_while_paused_applies_when_trials_resume(tmp_path):
    """Spec §5.1: settings staged while paused apply when trials resume -- at the top
    of the pass that runs the next trial, recorded and strobed there."""
    link = _Scripted(
        script={1: [SetParameter(name="fix_hold", value=0.4, by="sam")], 3: [Resume(by="jake")]}
    )
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=3)
    link.wall = wall

    session.run()

    assert _parameter_changes(session)[0]["now"] == 0.4
    rows = [json.loads(line) for line in (session.directory / "trials.jsonl").read_text().splitlines()]
    assert [row["params"]["fix_hold"] for row in rows] == [0.4, 0.4, 0.4]


def test_stop_while_paused_ends_the_session(tmp_path):
    link = _Scripted(script={2: [Stop(by="sam")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "operator"
    assert session.stopped_because == "stopped by sam"
    assert len(link.waits) == 2


def test_a_second_pause_and_a_resume_with_nothing_paused_are_refused(tmp_path):
    """A double click sends two pauses; the second is said, not stacked, and a stray
    resume is said too. Neither strobes."""
    link = _Scripted(script={2: [Resume(by="jake"), Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=2)
    link.wall = wall

    session.run()

    assert [(n, why.split(";")[0]) for n, _, why in session.refusals] == [
        ("pause", "the session is already paused"),
        ("resume", "the session is not paused"),
    ]
    assert session.card.codes.count(PAUSE_CODE) == 1
    assert session.card.codes.count(RESUME_CODE) == 1


def test_a_pause_pressed_after_a_stop_is_refused_and_the_session_ends(tmp_path):
    """Review Focus 3: pause pressed while a stop is already on its way. Both land in
    one drain; the stop ends the session at that boundary, and the pause is refused
    with a sentence rather than holding a session that is ending."""
    link = _Scripted()
    link.queue(Stop(by="sam"))
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stopped_because == "stopped by sam"
    assert link.waits == [], "a stopping session never held"
    ((name, by, why),) = session.refusals
    assert (name, by) == ("pause", "jake")
    assert "the session is stopping (stopped by sam)" in why
    assert PAUSE_CODE not in session.card.codes


def test_a_pause_is_refused_when_the_allocation_cannot_mark_it(tmp_path):
    """A pause the recording cannot show is refused rather than taken silently: the
    allocation must carry both `PAUSE` and `RESUME`, so the gap has two ends."""
    from dataclasses import replace

    link = _Scripted()
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=2)
    link.wall = wall
    session.allocation = replace(
        session.allocation,
        task_events={
            code: name
            for code, name in session.allocation.task_events.items()
            if name != "RESUME"
        },
    )

    session.run()

    assert session.stop_kind == "completed"
    ((name, _, why),) = session.refusals
    assert name == "pause"
    assert "no RESUME event code" in why
    assert link.waits == []


def test_the_paused_loop_waits_one_housekeeping_interval_at_a_time(tmp_path):
    link = _Scripted(script={2: [Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=1)
    link.wall = wall

    session.run()

    assert link.waits == [PAUSE_HOUSEKEEPING_S, PAUSE_HOUSEKEEPING_S]


def test_after_the_loop_a_pause_or_a_resume_is_refused_not_applied(tmp_path):
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    link.queue(Pause(by="jake"))
    link.queue(Resume(by="sam"))

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: len(session.refusals) == 2)
    finally:
        give_up.set()
        thread.join(timeout=2)

    assert [(n, b) for n, b, _ in session.refusals] == [("pause", "jake"), ("resume", "sam")]
    assert session.paused_at is None


def test_the_control_feed_keeps_the_newest_and_counts_what_fell_off(tmp_path):
    """The feed a console shows is bounded like the refusal feed, and a cap never
    reads as a quiet session. The record keeps every row."""
    pairs = CONTROL_HISTORY // 2 + 10
    # Resumed and paused again in one drain, so the loop stays held, and resumed for
    # good on the last wait: `pairs` pauses and `pairs` resumes.
    script = {n: [Resume(by="jake"), Pause(by="jake")] for n in range(1, pairs)}
    script[pairs] = [Resume(by="jake")]
    link = _Scripted(script=script, budget=2 * pairs)
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=1)
    link.wall = wall

    session.run()

    assert len(session.controls) == CONTROL_HISTORY
    assert session.controls_dropped == 2 * pairs - CONTROL_HISTORY
    assert len(_controls_rows(session)) == 2 * pairs
    kinds = [row[0] for row in session.controls]
    assert kinds[-1] == "resume"
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py`
Expected: fails to collect — `ImportError: cannot import name 'CONTROL_HISTORY'`.

- [ ] **Step 3: Implement**

In `tasks/allocation.py`, replace:

```python
        4130: "PARAM_CHANGED",
    },
```

with:

```python
        4130: "PARAM_CHANGED",
        # Console controls the framework strobes (P4d-2b spec §5.1, 2026-09-27):
        # a pause and its resume, so the recording shows the gap, and an operator's
        # mark, strobed in the frame it reaches the rig. The spec calls them
        # `pause`, `resume` and `operator_mark`; spelled here as every other
        # framework name is. In this range while ADR-0007's `TaskEvent` range is
        # being moved; wl-exptasks owns the final numbering (spec §5.6).
        4131: "PAUSE",
        4132: "RESUME",
        4133: "OPERATOR_MARK",
    },
```

In `wl_expcontroller/link.py`, replace:

```python
RECENT_OUTCOMES = 60

```

with:

```python
RECENT_OUTCOMES = 60

#: How many recent control events -- a pause, a resume, a mark and its note, a
#: schedule, a cancellation, an applied setting -- a session keeps for its consoles'
#: changes feed, newest kept (P4d-2b spec §5.1). A display bound, capped for
#: `REFUSAL_HISTORY`'s reason; what falls off is counted in `Session.controls_dropped`
#: and the session record keeps every one (`record.CONTROLS`).
CONTROL_HISTORY = 50

```

In `wl_expcontroller/record.py`, replace:

```python
WELFARE_NOTES = "welfare_notes.jsonl"

```

with:

```python
WELFARE_NOTES = "welfare_notes.jsonl"

#: A console's controls, one row each (P4d-2b spec §5.1: "every one is written to
#: the session record with who sent it and when"): a stop, a pause, a resume, a
#: mark's stamp and its note, a schedule, a cancellation, and a scheduled stop firing.
#:
#: **Its own file**, for `WELFARE_NOTES`' reason: a row in `parameter_changes.jsonl`
#: carries a `sequence` for joining to a `PARAM_CHANGED` code, and these join to their
#: own codes (`PAUSE`, `RESUME`, `OPERATOR_MARK`) by order and instant, or to nothing.
#: **Uncapped**, unlike `refusals.jsonl`: each row is something that happened, and
#: the party making them is the box's own console, one person at a keyboard, with
#: marks bounded besides at one per frame (`link.ZmqLink.mark_signal`).
CONTROLS = "controls.jsonl"

```

In `wl_expcontroller/record.py`, in `SessionRecord`, replace:

```python

    def refusal(
```

with:

```python

    def control(
        self, kind: str, by: str, at: float, trial_index: int, **detail: object
    ) -> None:
        """One console control, as it happened (P4d-2b spec §5.1).

        `at` is the instant `taskd` acted on it, **on the session's anchored clock**
        (`Session.wall_now`), written as the number and as local clock time with its
        zone, as `welfare_note` writes its instants. `trial_index` is the trial it
        happened in or, between trials, the trial about to run. `detail` is the row's
        own fields -- a mark's frame and its three instants, a schedule's target --
        written as given and never interpreted here."""
        with (self.directory / CONTROLS).open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "kind": kind,
                        "by": by,
                        "at": at,
                        "at_local": _local(at),
                        "trial_index": trial_index,
                        **detail,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    def refusal(
```

In `wl_expcontroller/taskd.py`, replace:

```python
from wl_expcontroller.check import check
from wl_expcontroller.cli import _load_allocation, _load_trial
```

with:

```python
from wl_expcontroller.check import check
from wl_expcontroller.cli import _clock, _load_allocation, _load_trial
```

In `wl_expcontroller/taskd.py`, replace:

```python
    Welfare,
)

```

with:

```python
    Welfare,
)

#: How long the paused loop waits for a console between its housekeeping passes --
#: draining commands, publishing a frame, and asking `welfare.must_stop` -- in
#: seconds (P4d-2b spec §5.1). The wait ends early when a mark or a command arrives
#: (`link.Link.idle`), so a resume or a stop is read as soon as it lands; this bounds
#: only how long a paused session goes between frames, and between limit checks,
#: when nothing arrives. A responsiveness choice, not a measurement of this system.
PAUSE_HOUSEKEEPING_S = 0.5

```

In `wl_expcontroller/taskd.py`, in `Session`, replace:

```python
    ended_wall_at: float | None = field(init=False, default=None)

```

with:

```python
    ended_wall_at: float | None = field(init=False, default=None)
    #: When a console paused the session, on the session's anchored clock, or `None`
    #: while trials run (P4d-2b spec §5.1). Set at the boundary the `Pause` was
    #: drained at, cleared by `Resume`; a session stopped while paused keeps it, as
    #: the truth of how it ended. Published as `Telemetry.paused_at`.
    paused_at: float | None = field(init=False, default=None)
    #: The consoles' changes feed: the last `link.CONTROL_HISTORY` control events as
    #: `(kind, by, at, said)`, oldest first -- see `controls`.
    _controls: deque = field(
        init=False,
        default_factory=lambda: deque(maxlen=_link.CONTROL_HISTORY),
        repr=False,
    )
    #: How many control events fell off the far end of `_controls`. Rolled into
    #: `Telemetry.controls_dropped`, so a cap can never read as a quiet session.
    controls_dropped: int = field(init=False, default=0)

```

In `wl_expcontroller/taskd.py`, in `Session.parameters`, replace:

```python
    @property
    def parameters(self) -> tuple:
```

with:

```python
    @property
    def controls(self) -> tuple:
        """The recent control events a console's changes feed lists, as `(kind, by,
        at, said)`, oldest first (P4d-2b spec §5.1): `stop`, `pause`, `resume`, and
        -- from the tasks that add them -- `mark`, `note`, `schedule`, `cancel`,
        `scheduled_stop` and `set` (a staged setting applied). `at` is the session's anchored clock; `said` is the
        sentence a console shows after the kind. The public face of `_controls`,
        for the reason `staged` is public; the session record keeps every one."""
        return tuple(self._controls)

    @property
    def parameters(self) -> tuple:
```

In `wl_expcontroller/taskd.py`, in `Session.parameters`, replace:

```python
        return declared + ceilings

```

with:

```python
        return declared + ceilings

    def _control(self, kind: str, by: str, said: str, index: int, **detail: object) -> float:
        """One control event: onto the changes feed and into the session record,
        stamped with the session's anchored clock, which it returns (P4d-2b spec
        §5.1). `index` is the trial it happened in or, between trials, the trial
        about to run; `detail` is the record row's own fields."""
        at = self.wall_now()
        if len(self._controls) == self._controls.maxlen:
            self.controls_dropped += 1
        self._controls.append((kind, by, at, said))
        if self._record is not None:
            self._record.control(kind, by, at, index, **detail)
        return at

    def _code(self, name: str) -> int | None:
        """The code this session's allocation gives a framework event, or `None` when
        it gives none. `Allocation.code_for` refuses rather than inventing a number;
        a control that needs a code it does not have refuses in its turn (`_pause`),
        rather than raising out of the loop."""
        try:
            return self.allocation.code_for(name)
        except KeyError:
            return None

    def _pause(self, by: str, index: int) -> None:
        """Hold the session at this boundary (P4d-2b spec §5.1): `run()` enters
        `_hold` before the next trial. Strobed now, so the recording shows where the
        gap begins.

        **Refused, with the sentence, when it would not hold a session that can
        resume and be seen to**: a session already stopping -- a `Stop` drained
        ahead of this in the same pass (Review Focus 3) -- one already paused (a
        double click), or an allocation without both `PAUSE` and `RESUME`, which
        would leave a gap in the recording with an end nobody could find."""
        if self.stopped_because:
            self._refuse(
                "pause",
                by,
                f"the session is stopping ({self.stopped_because}); a pause is not "
                f"applied",
            )
            return
        if self.paused_at is not None:
            self._refuse(
                "pause",
                by,
                "the session is already paused; this pause changes nothing",
            )
            return
        codes = {name: self._code(name) for name in ("PAUSE", "RESUME")}
        missing = [name for name, code in codes.items() if code is None]
        if missing:
            self._refuse(
                "pause",
                by,
                f"this session's allocation has no {' or '.join(missing)} event code, "
                f"so the recording could not show the pause; it is refused",
            )
            return
        self.card.emit(codes["PAUSE"])
        self.paused_at = self._control("pause", by, f"paused at trial {index}", index)

    def _resume(self, by: str, index: int) -> None:
        """End the pause: `_hold` returns and `run()` goes back to the top of its
        loop, which applies whatever was staged while paused before the next trial
        runs (spec §5.1). Strobed, so the recording shows where the gap ends."""
        if self.paused_at is None:
            self._refuse("resume", by, "the session is not paused; this resume changes nothing")
            return
        self.card.emit(self.allocation.code_for("RESUME"))
        held = self.wall_now() - self.paused_at
        self.paused_at = None
        self._control(
            "resume", by, f"resumed after {_clock(held)} paused", index, paused_s=held
        )

    def _ends(self) -> bool:
        """Whether the session must end at this boundary, with its reason and kind
        set: the out-of-cage limit, `welfare.must_stop`, read on the wall as ever
        (P4d-2a spec §10). **One place for it**, asked between trials and on every
        pass of the paused loop alike (P4d-2b spec §5.1: "ending the session on it
        exactly as between trials"), so the limit cannot be enforced in one of the
        two and not the other."""
        stop = self.welfare.must_stop(self.wall_now())
        if stop:
            self.stopped_because = stop
            self.stop_kind = "limit"
            return True
        return False

    def _hold(self, index: int, publish) -> None:
        """**Paused** (P4d-2b spec §5.1): no trial runs and nothing is rewarded, while
        once per housekeeping pass the loop drains commands -- resume, stop, marks,
        schedules, settings -- publishes a frame, and asks `_ends` whether the
        out-of-cage limit has arrived, ending the session on it as between trials.
        The out-of-cage clock runs on the wall throughout, since nothing here stops
        it.

        **Nothing is rewarded because nothing can be**: a reward is a trial's action
        (`run.Effects.reward`), and no trial runs here. **Nothing is drawn** for the
        same reason: a stimulus is shown only by a trial, so the display the task's
        trials draw on shows its background with nothing on it (spec §5.0). There is
        no display process yet to be told so -- S4's is not built (docs/CHECKPOINT.md:
        "a frame on screen" is blocked on a panel) -- and when there is, this is the
        pause it must show; the hardware verification list says so.

        Returns when the session resumes, or with `stopped_because` set when it must
        end; `run()` reads which."""
        while self.paused_at is not None:
            self.link.idle(PAUSE_HOUSEKEEPING_S)
            for command in self.link.drain():
                self._command(command, index)
            publish()
            if self.stopped_because:
                return
            if self._ends():
                publish()
                return

```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
            self.stop_kind = "operator"
            return
```

with:

```python
            self.stop_kind = "operator"
            # P4d-2b b2a: the record says who stopped the session and when, as it
            # says who paused it; the reason alone was in telemetry and at the
            # terminal, and neither is the record.
            self._control("stop", command.by, self.stopped_because, index)
            return
        if isinstance(command, _link.Pause):
            self._pause(command.by, index)
            return
        if isinstance(command, _link.Resume):
            self._resume(command.by, index)
            return
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
                # another at the same trial boundary, never per frame.
                stop = self.welfare.must_stop(self.wall_now())
                if stop:
                    self.stopped_because = stop
                    self.stop_kind = "limit"
```

with:

```python
                # another at the same trial boundary, never per frame. `_ends` is
                # the same question the paused loop asks.
                if self._ends():
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
                    break
                if scheduler.finished:
```

with:

```python
                    break
                if self.paused_at is not None:
                    # Held here, at the boundary, until a resume or an ending
                    # (P4d-2b spec §5.1). A resume goes back to the top, where
                    # anything staged while paused is applied before the next trial.
                    self._hold(index, publish)
                    if self.stopped_because:
                        break
                    continue
                if scheduler.finished:
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py tests/test_reference_tasks.py tests/test_task_checks.py`
Expected: all pass — the allocation's three new names break none of the reference tasks' checks.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1220 passed**.

- [ ] **Step 5: Commit**

```bash
git add tasks/allocation.py wl_expcontroller/record.py wl_expcontroller/link.py wl_expcontroller/taskd.py tests/test_taskd.py
git commit -m "Hold a paused session at the boundary, still ending it on the out-of-cage limit, and record every control"
```

---

### Task 6: Marks, stamped in the frame they arrive

**Why:** spec §5.0 (the PI: marks must be instant) and §5.1: the loop checks the mark signal once per frame and strobes `OPERATOR_MARK` in that frame; the check runs between trials and while paused too; the note arrives later as a `Mark` command and is joined to its stamp by number; the record keeps three instants and the gaps between them (Plan decisions 1 and 4). `run_trial` gains its one per-frame hook, called first on every frame, the gaze-lost ones included.

**Files:**
- Modify: `wl_expcontroller/run.py` (`Callable`; `run_trial`'s `each_frame`)
- Modify: `wl_expcontroller/taskd.py` (`_gap`; `Session._mark_code`, `_stamps`, `_stamped`; `_control`'s `at`; `_stamp`, `_settle_stamps`, `_check_marks`, `_mark_note`; `_hold`; `_command`; `run`)
- Test: `tests/test_run.py`, `tests/test_taskd.py`

**Interfaces:**
- Consumes: Task 3's `Link.mark_signal`, `Link.idle`, `Simulated.marks`; Task 2's `Mark`; Task 5's `_control`, `_code`, `_Scripted`, `_walled`, `_controls_rows`, `MARK_CODE`.
- Produces:
  - `run.run_trial(..., each_frame: Callable[[int], None] | None = None) -> Result`.
  - `Session._stamp(mark: int, frame: int | None)`, `_settle_stamps(index: int)`, `_check_marks(index: int)`, `_mark_note(command, index: int)`; `taskd._gap(later, earlier) -> float | None`.
  - `Session._control(kind, by, said, index, at: float | None = None, **detail) -> float`.
  - Control kinds `mark` (by `""` — the sender arrives with the note) and `note`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_run.py`, replace:

```python
    State,
    Trial,
```

with:

```python
    State,
    Tolerances,
    Trial,
```

Append to `tests/test_run.py`:

```python


# --- P4d-2b b2a: the one per-frame hook ------------------------------------------


class _Watched(Quiet):
    """`Quiet`, with every display call logged beside the hook's."""

    def __init__(self, log: list) -> None:
        object.__setattr__(self, "log", log)

    def display(self, visible, frame: int) -> None:
        self.log.append(("display", frame))


def test_each_frame_is_called_once_per_frame_before_anything_else_on_it():
    """P4d-2b spec §5.1: a mark is stamped in the frame it reaches the rig, so the
    session's check runs once per frame, first, before the frame is drawn or any
    guard is read -- the frame it names is the frame it happened in."""
    trial = Trial(
        start="wait",
        states=[State("wait", go=[On(After(0.1), Outcome.CORRECT)])],
    )
    log: list = []

    result = run_trial(
        trial,
        world=_Watched(log),
        frame_period=0.01,
        each_frame=lambda frame: log.append(("each", frame)),
    )

    assert result.frames == 10
    assert log == [
        entry for frame in range(1, 11) for entry in (("each", frame), ("display", frame))
    ]


class _Blinking(Quiet):
    def signal(self, frame: int) -> str:
        return "blink"


def test_each_frame_runs_on_a_frame_the_gaze_signal_was_lost_too():
    """An interrupted frame skips the guards (`continue`), and must not skip the mark
    check: an operator's mark during a blink is still a mark."""
    trial = Trial(
        start="wait",
        states=[State("wait", go=[On(After(10.0), Outcome.CORRECT)])],
        tolerances=Tolerances(blink=None, tracker_lost=None),
    )
    frames: list = []

    run_trial(
        trial, world=_Blinking(), frame_period=0.01, max_frames=20,
        each_frame=frames.append,
    )

    assert frames == list(range(1, 21))
```

In `tests/test_taskd.py`, replace:

```python
    REFUSAL_HISTORY,
    Pause,
```

with:

```python
    REFUSAL_HISTORY,
    Mark,
    Pause,
```

Append to `tests/test_taskd.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a: marks, stamped in the frame they arrive (spec §5.0, §5.1)
# ---------------------------------------------------------------------------

#: `fixation_detection`'s first code on entering a trial, and the markers a trial ends
#: on (`codes._standing_outcomes`).
FIX_ON = 4096
MARKERS = {34, 35, 36, 37, 38}


class _MarkAfter(Simulated):
    """A link whose mark check answers `mark` on the `calls`-th check after it is
    armed, and zero otherwise -- so a test chooses the frame a mark arrives in."""

    def __init__(self, mark: int, calls: int) -> None:
        super().__init__()
        self.mark = mark
        self.calls = calls
        self.armed = False
        self.seen = 0

    def mark_signal(self) -> int:
        if not self.armed:
            return 0
        self.seen += 1
        if self.seen == self.calls:
            return self.mark
        return 0


def _trial_codes(codes: list, trial: int) -> list:
    """The codes strobed during trial `trial` (0-based): from its `FIX_ON` to its
    ending marker."""
    starts = [i for i, code in enumerate(codes) if code == FIX_ON]
    start = starts[trial]
    end = next(i for i in range(start, len(codes)) if codes[i] in MARKERS)
    return codes[start : end + 1]


def test_a_mark_is_strobed_and_stamped_in_the_frame_it_arrives(tmp_path):
    """Spec §5.0, the PI's ruling: marks must be instant -- stamped in the frame they
    reach the rig, not at the next trial boundary. Armed after the second trial, the
    link answers on its eleventh check: the first is the boundary's, so the mark
    arrives in the third trial's tenth frame, and that is where the code is strobed
    and what the record names."""
    link = _MarkAfter(mark=77, calls=11)
    session = _session(_spec(tmp_path, trials=4), link=link)
    ran = [0]

    def arm_after_two(condition, values, result) -> None:
        ran[0] += 1
        if ran[0] == 2:
            link.armed = True

    session.observe = arm_after_two

    session.run()

    assert MARK_CODE in _trial_codes(session.card.codes, 2)
    assert session.card.codes.count(MARK_CODE) == 1
    (stamp,) = _controls_rows(session)
    assert (stamp["kind"], stamp["mark"], stamp["number"]) == ("mark", 77, 1)
    assert (stamp["trial_index"], stamp["frame"]) == (2, 10)
    assert stamp["strobed"] is True
    assert session.controls[0][3] == "mark 1 stamped in trial 2, frame 10"


def test_a_mark_between_trials_is_stamped_at_the_boundary_with_no_frame(tmp_path):
    link = Simulated()
    link.marks.append(5)
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    (stamp,) = _controls_rows(session)
    assert (stamp["trial_index"], stamp["frame"]) == (0, None)
    assert session.controls[0][3] == "mark 1 stamped between trials, before trial 0"
    assert session.card.codes.index(MARK_CODE) < session.card.codes.index(FIX_ON)


def test_a_mark_while_paused_is_stamped_when_it_arrives(tmp_path):
    class _MarkWhilePaused(_Scripted):
        def idle(self, timeout: float) -> int:
            super().idle(timeout)
            return 9 if len(self.waits) == 2 else 0

    link = _MarkWhilePaused(script={3: [Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=1)
    link.wall = wall

    session.run()

    pause, stamp, resume = _controls_rows(session)
    assert (pause["kind"], stamp["kind"], resume["kind"]) == ("pause", "mark", "resume")
    assert (stamp["mark"], stamp["frame"]) == (9, None)
    assert session.controls[1][3] == "mark 1 stamped while paused, before trial 0"
    codes = session.card.codes
    assert codes.index(PAUSE_CODE) < codes.index(MARK_CODE) < codes.index(RESUME_CODE)


def test_a_note_joins_its_stamp_with_the_three_instants_and_their_gaps(tmp_path):
    """Spec §5.1: the record keeps when M was pressed (the browser's clock), when
    `wlx serve` received it (its clock), and when the rig stamped it (the session's
    anchored clock and frame), and the gaps between them are recorded, never hidden.
    The note arrives as a `Mark` command and is joined to its stamp by number."""
    link = Simulated()
    link.marks.append(5)
    link.queue(
        Mark(
            mark=5,
            note="reward line bubble",
            by="jake (box, unverified)",
            pressed_at=WALL_NOW - 2.0,
            received_at=WALL_NOW - 1.5,
        )
    )
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    stamp, note = _controls_rows(session)
    assert note["kind"] == "note" and note["by"] == "jake (box, unverified)"
    assert (note["mark"], note["number"], note["note"]) == (5, 1, "reward line bubble")
    assert note["pressed_at"] == WALL_NOW - 2.0
    assert note["received_at"] == WALL_NOW - 1.5
    assert note["stamped_at"] == stamp["at"] == WALL_NOW
    assert note["received_after_pressed_s"] == pytest.approx(0.5)
    assert note["stamped_after_received_s"] == pytest.approx(1.5)
    assert (note["stamped_in_trial"], note["frame"]) == (0, None)
    assert session.controls[1][1:] == (
        "jake (box, unverified)", session.controls[1][2], 'mark 1: "reward line bubble"'
    )


def test_a_note_left_bare_and_a_note_whose_instants_are_unknown_still_record(tmp_path):
    """Esc leaves the mark bare; a `wlx serve` restarted between the signal and the
    note knows no instants. Both are recorded as they are, never filled in."""
    link = Simulated()
    link.marks.append(5)
    link.queue(Mark(mark=5, note="", by="jake", pressed_at=None, received_at=None))
    session = _session(_spec(tmp_path, trials=1), link=link)

    session.run()

    _, note = _controls_rows(session)
    assert note["note"] == ""
    assert note["received_after_pressed_s"] is None
    assert note["stamped_after_received_s"] is None
    assert session.controls[1][3] == "mark 1: no note"


def test_a_note_for_a_mark_this_session_never_stamped_says_so(tmp_path):
    link = Simulated()
    link.queue(Mark(mark=99, note="lost?", by="jake", pressed_at=None, received_at=None))
    session = _session(_spec(tmp_path, trials=1), link=link)

    session.run()

    (note,) = _controls_rows(session)
    assert note["number"] is None and note["stamped_at"] is None
    assert session.controls[0][3] == 'a note for mark 99, which this session never stamped: "lost?"'


def test_two_marks_pressed_fast_are_two_stamps_in_order(tmp_path):
    """Review Focus 2: M pressed twice fast. Two signals, two numbers, two codes, in
    order, neither lost -- the check reads one per frame, so the second is stamped in
    the next frame and its row names that frame."""
    link = Simulated()
    link.marks.extend([5, 6])
    session = _session(_spec(tmp_path, trials=1), link=link)

    session.run()

    first, second = _controls_rows(session)
    assert (first["mark"], first["number"], first["frame"]) == (5, 1, None)
    assert (second["mark"], second["number"], second["trial_index"], second["frame"]) == (6, 2, 0, 1)
    assert session.card.codes.count(MARK_CODE) == 2


def test_a_mark_the_allocation_cannot_strobe_is_stamped_and_says_so(tmp_path):
    """A mark cannot be refused -- it has already been pressed -- so without an
    `OPERATOR_MARK` code it is recorded unstrobed, and the feed says so rather than
    implying the recording has it."""
    from dataclasses import replace

    link = Simulated()
    link.marks.append(5)
    session = _session(_spec(tmp_path, trials=1), link=link)
    session.allocation = replace(
        session.allocation,
        task_events={
            code: name
            for code, name in session.allocation.task_events.items()
            if name != "OPERATOR_MARK"
        },
    )

    session.run()

    (stamp,) = _controls_rows(session)
    assert stamp["strobed"] is False
    assert session.controls[0][3].endswith(
        "; not strobed: this session's allocation has no OPERATOR_MARK event code"
    )
    assert MARK_CODE not in session.card.codes


def test_a_mark_in_a_trial_that_faults_is_still_recorded(tmp_path, monkeypatch):
    """The strobe is on the recording the instant it happens; the record row is
    written at the boundary after, and a trial that faults has no boundary after, so
    the stamps it holds are written as the session closes."""
    from wl_expcontroller import taskd

    def faults(trial, world, frame_period, values=None, effects=None, each_frame=None):
        each_frame(1)
        raise RuntimeError("the display went away")

    monkeypatch.setattr(taskd, "run_trial", faults)
    link = Simulated()
    link.marks.extend([0, 8])  # nothing at the boundary; mark 8 in frame 1
    session = _session(_spec(tmp_path, trials=3), link=link)

    with pytest.raises(RuntimeError, match="the display went away"):
        session.run()

    (stamp,) = _controls_rows(session)
    assert (stamp["mark"], stamp["trial_index"], stamp["frame"]) == (8, 0, 1)
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_run.py tests/test_taskd.py`
Expected: the two `test_run.py` tests fail with `TypeError: run_trial() got an unexpected keyword argument 'each_frame'`; the nine mark tests in `test_taskd.py` fail — nothing is stamped (Task 2's fallback refuses the note, and the faulting stand-in calls an `each_frame` nobody passed), so `controls.jsonl` has no row to unpack.

- [ ] **Step 3: Implement**

In `wl_expcontroller/run.py`, replace:

```python
from dataclasses import dataclass, field, replace
from typing import Mapping, NamedTuple, Protocol
```

with:

```python
from dataclasses import dataclass, field, replace
from typing import Callable, Mapping, NamedTuple, Protocol
```

In `wl_expcontroller/run.py`, in `run_trial`, replace:

```python
    effects: "Effects | None" = None,
) -> Result:
```

with:

```python
    effects: "Effects | None" = None,
    each_frame: "Callable[[int], None] | None" = None,
) -> Result:
```

In `wl_expcontroller/run.py`, in `run_trial`, replace:

```python
    command quietly dropped.
    """
```

with:

```python
    command quietly dropped.

    **`each_frame`, the loop's one per-frame hook** (P4d-2b spec §5.1): called with
    the frame's number first thing on every frame -- before the display, before any
    guard, and on a frame the gaze signal was lost -- so what it does happens in the
    frame it names. `taskd.Session` passes its mark check, which strobes an
    operator's mark in the frame it arrives. **Hot path**: whatever is passed must
    not block, log or allocate when there is nothing to do; this loop does not check.
    """
```

In `wl_expcontroller/run.py`, in `run_trial`, replace:

```python
    for frame in range(1, max_frames + 1):
        world.display(visible, frame)
```

with:

```python
    for frame in range(1, max_frames + 1):
        if each_frame is not None:
            each_frame(frame)
        world.display(visible, frame)
```

In `wl_expcontroller/taskd.py`, replace:

```python
PAUSE_HOUSEKEEPING_S = 0.5

```

with:

```python
PAUSE_HOUSEKEEPING_S = 0.5


def _gap(later: float | None, earlier: float | None) -> float | None:
    """`later - earlier`, or `None` when either instant is unknown: a mark's gaps are
    recorded as the clocks read, and one nobody read is not a gap of zero."""
    if later is None or earlier is None:
        return None
    return later - earlier

```

In `wl_expcontroller/taskd.py`, in `Session`, replace:

```python
    controls_dropped: int = field(init=False, default=0)

```

with:

```python
    controls_dropped: int = field(init=False, default=0)
    #: `OPERATOR_MARK`'s code, looked up once when `run()` starts so the frame never
    #: searches the allocation; `None` when the allocation has none (P4d-2b b2a).
    _mark_code: int | None = field(init=False, default=None, repr=False)
    #: Marks stamped in a frame and not yet written: `(mark, frame, at, paused)`. The
    #: frame only appends; `_settle_stamps` writes them at the boundary after.
    _stamps: list = field(init=False, default_factory=list, repr=False)
    #: Every mark this session stamped, by its signal's number: `(number, trial,
    #: frame, at)`, what a note arriving later is joined to.
    _stamped: dict = field(init=False, default_factory=dict, repr=False)

```

In `wl_expcontroller/taskd.py`, in `Session._control`, replace:

```python
    def _control(self, kind: str, by: str, said: str, index: int, **detail: object) -> float:
        """One control event: onto the changes feed and into the session record,
        stamped with the session's anchored clock, which it returns (P4d-2b spec
        §5.1). `index` is the trial it happened in or, between trials, the trial
        about to run; `detail` is the record row's own fields."""
        at = self.wall_now()
```

with:

```python
    def _control(
        self,
        kind: str,
        by: str,
        said: str,
        index: int,
        at: float | None = None,
        **detail: object,
    ) -> float:
        """One control event: onto the changes feed and into the session record, at
        `at` on the session's anchored clock -- now, unless the event was stamped
        earlier (a mark, in its frame) -- which it returns (P4d-2b spec §5.1).
        `index` is the trial it happened in or, between trials, the trial about to
        run; `detail` is the record row's own fields."""
        if at is None:
            at = self.wall_now()
```

In `wl_expcontroller/taskd.py`, in `Session`, replace:

```python

    def _ends(self) -> bool:
```

with:

```python

    def _stamp(self, mark: int, frame: int | None) -> None:
        """**An operator's mark, in the frame it reached the rig** (P4d-2b spec
        §5.0, §5.1): `OPERATOR_MARK` strobed now, and the stamp -- the mark's
        number, the frame (`None` between trials and while paused), the session's
        anchored clock -- kept for `_settle_stamps` to write at the boundary after.

        **Called from inside a frame**, but only when a signal arrived: the per-frame
        check that finds none is `link.mark_signal` alone. What this does on a mark
        is bounded -- one strobe, one clock read, one append -- and is the whole of
        the mark's work in the frame; nothing here writes a file. A mark is never
        refused, since it has already been pressed: without an `OPERATOR_MARK` code
        it is stamped unstrobed, and `_settle_stamps` says so."""
        if self._mark_code is not None:
            self.card.emit(self._mark_code)
        self._stamps.append((mark, frame, self.wall_now(), self.paused_at is not None))

    def _settle_stamps(self, index: int) -> None:
        """Write the stamps a frame or a boundary kept (`_stamp`): one `mark` row
        each, numbered in the order this session stamped them, onto the changes feed
        and into the record, and remembered for the note that follows (`_mark_note`).
        `index` is the trial they were stamped in, or the one about to run."""
        for mark, frame, at, paused in self._stamps:
            number = len(self._stamped) + 1
            if frame is not None:
                said = f"mark {number} stamped in trial {index}, frame {frame}"
            elif paused:
                said = f"mark {number} stamped while paused, before trial {index}"
            else:
                said = f"mark {number} stamped between trials, before trial {index}"
            strobed = self._mark_code is not None
            if not strobed:
                said += (
                    "; not strobed: this session's allocation has no OPERATOR_MARK "
                    "event code"
                )
            self._control(
                "mark", "", said, index, at=at,
                mark=mark, number=number, frame=frame, strobed=strobed,
            )
            self._stamped[mark] = (number, index, frame, at)
        self._stamps.clear()

    def _check_marks(self, index: int) -> None:
        """The mark check at a trial boundary (spec §5.1: it "runs between trials and
        while paused too"): a mark waiting here is stamped with no frame and written
        at once, since nothing here is inside a frame."""
        mark = self.link.mark_signal()
        if mark:
            self._stamp(mark, None)
            self._settle_stamps(index)

    def _mark_note(self, command, index: int) -> None:
        """A `Mark` command: the note half of a mark, joined to its stamp by the
        signal's number (spec §5.1). One `note` row carrying the three instants --
        pressed (the browser's clock), received (`wlx serve`'s), stamped (the
        session's anchored clock, with its frame) -- **and the gaps between them**,
        each across two clocks and recorded as they read, never hidden and never
        corrected. A note for a mark this session never stamped -- a signal that
        did not arrive, or one from before this session -- is recorded as such."""
        joined = self._stamped.get(command.mark)
        number, trial, frame, stamped_at = joined if joined else (None, None, None, None)
        quoted = f'"{command.note}"' if command.note else "no note"
        said = (
            f"a note for mark {command.mark}, which this session never stamped: {quoted}"
            if number is None
            else f"mark {number}: {quoted}"
        )
        self._control(
            "note",
            command.by,
            said,
            index,
            mark=command.mark,
            number=number,
            note=command.note,
            pressed_at=command.pressed_at,
            received_at=command.received_at,
            stamped_at=stamped_at,
            stamped_in_trial=trial,
            frame=frame,
            received_after_pressed_s=_gap(command.received_at, command.pressed_at),
            stamped_after_received_s=_gap(stamped_at, command.received_at),
        )

    def _ends(self) -> bool:
```

In `wl_expcontroller/taskd.py`, in `Session._hold`, replace:

```python
        while self.paused_at is not None:
            self.link.idle(PAUSE_HOUSEKEEPING_S)
```

with:

```python
        while self.paused_at is not None:
            # The wait is also the paused loop's mark check: `idle` returns the
            # moment a mark arrives, and it is stamped then.
            mark = self.link.idle(PAUSE_HOUSEKEEPING_S)
            if mark:
                self._stamp(mark, None)
                self._settle_stamps(index)
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
            self._resume(command.by, index)
            return
```

with:

```python
            self._resume(command.by, index)
            return
        if isinstance(command, _link.Mark):
            self._mark_note(command, index)
            return
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
        self.phase = "running"
        try:
```

with:

```python
        self.phase = "running"
        self._mark_code = self._code("OPERATOR_MARK")
        # **The per-frame mark check** (P4d-2b spec §5.1), handed to `run_trial` as
        # its one per-frame hook. Bound once, here, so each frame is two calls and a
        # test on a small integer; `_stamp` runs only when a signal arrived.
        signal, stamp = self.link.mark_signal, self._stamp

        def each_frame(frame: int) -> None:
            mark = signal()
            if mark:
                stamp(mark, frame)

        try:
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
                self._apply_staged()
                # Drain *after* `_apply_staged()`, not before: staging and applying
```

with:

```python
                self._apply_staged()
                # Between trials the frame's mark check runs once here, before the
                # drain, so a mark's stamp is written ahead of a note that arrived
                # with it (P4d-2b spec §5.1).
                self._check_marks(index)
                # Drain *after* `_apply_staged()`, not before: staging and applying
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
                    effects=self.rig,
                )
```

with:

```python
                    effects=self.rig,
                    each_frame=each_frame,
                )
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
                )
                self._elapsed += result.frames * self.spec.frame_period + self.spec.iti
```

with:

```python
                )
                # The marks this trial's frames stamped, written now that it is over.
                self._settle_stamps(index)
                self._elapsed += result.frames * self.spec.frame_period + self.spec.iti
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
        finally:
            record.close()
```

with:

```python
        finally:
            # A trial that faulted or was interrupted has no boundary after it, so
            # the marks its frames stamped -- already strobed -- are written here,
            # while the record is still open (P4d-2b b2a).
            if self._stamps:
                self._settle_stamps(self._index)
            record.close()
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_run.py tests/test_taskd.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1231 passed**. `tests/test_cli.py` and `tests/test_serve.py` wrap `taskd.run_trial` for their trial budgets with `*args, **kwargs`, so `each_frame` passes through them.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/run.py wl_expcontroller/taskd.py tests/test_run.py tests/test_taskd.py
git commit -m "Stamp an operator's mark in the frame it reaches the rig, and join its note to the stamp"
```

---

### Task 7: The scheduled stop, held by the rig

**Why:** spec §5.1: a scheduled stop is held by `taskd`, so a closed page cannot lose it — at a clock time on the session's clock (the next occurrence, within 24 hours), after N more trials (shown as the target trial number), or after X mL this session (read from `welfare`'s session fluid); checked at each boundary and while paused; ending the session like the stop button; one at a time (Plan decision 6). A schedule that fired is spent.

**Files:**
- Modify: `wl_expcontroller/taskd.py` (`import time`; `_next_occurrence`; `Session.scheduled_stop`; `_control`'s `feed`; `_schedule`, `_cancel`; `_ends(index)`; `_hold`; `_command`; `run`)
- Test: `tests/test_taskd.py`

**Interfaces:**
- Consumes: Task 2's `ScheduleStop`, `CancelScheduledStop`, `check_schedule`; Task 5's `_ends`, `_hold`, `_Scripted`, `_walled`; `welfare.session_total()`, read only.
- Produces:
  - `taskd._next_occurrence(hhmm: str, wall: float) -> float`.
  - `Session.scheduled_stop: tuple | None` — `(kind, target, by, said)`; Task 8 publishes it as `ScheduledStop`.
  - `Session._schedule(command, index)`, `_cancel(by, index)`, `_ends(index) -> bool`.
  - `Session._control(kind, by, feed, index, at=None, **detail)` — its third parameter renamed, because a schedule's record row has a `said` of its own.
  - Control kinds `schedule`, `cancel`, `scheduled_stop`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_taskd.py`, replace:

```python
    REFUSAL_HISTORY,
    Mark,
```

with:

```python
    REFUSAL_HISTORY,
    CancelScheduledStop,
    Mark,
```

In `tests/test_taskd.py`, replace:

```python
    Resume,
    SetParameter,
```

with:

```python
    Resume,
    ScheduleStop,
    SetParameter,
```

Append to `tests/test_taskd.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a: the scheduled stop (spec §5.1), held by `taskd`
# ---------------------------------------------------------------------------


@pytest.fixture
def utc(monkeypatch):
    """The host's zone as UTC, so a clock time names one instant whatever zone the
    suite runs in. `WALL_NOW` is 2023-11-14 22:13:20 UTC."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _scheduled_at_trial(link, session, after: int, *commands) -> None:
    """Queue `commands` once `after` trials have run, through `observe`."""
    ran = [0]

    def queue(condition, values, result) -> None:
        ran[0] += 1
        if ran[0] == after:
            for command in commands:
                link.queue(command)

    session.observe = queue


def _trials_run(session: Session) -> int:
    return len((session.directory / "trials.jsonl").read_text().splitlines())


def test_a_stop_after_n_trials_ends_the_session_there_with_its_reason(tmp_path):
    """Spec §5.1: after N more trials, counted from when the schedule is accepted,
    shown as the target trial number. It stops the session like the stop button --
    `stop_kind` `operator` -- with the reason *scheduled stop (...) set by NAME*."""
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=3, by="jake"))
    session = _session(_spec(tmp_path, trials=50), link=link)

    session.run()

    assert _trials_run(session) == 3
    assert session.stop_kind == "operator"
    assert session.stopped_because == "scheduled stop (after trial 3) set by jake"
    assert session.scheduled_stop is None, "a stop that has happened is spent"
    rows = _controls_rows(session)
    assert [row["kind"] for row in rows] == ["schedule", "scheduled_stop"]
    assert (rows[0]["stop"], rows[0]["target"], rows[0]["said"]) == ("trials", 3.0, "after trial 3")
    assert rows[1]["by"] == "jake"


def test_after_n_trials_counts_from_when_the_schedule_is_accepted(tmp_path):
    link = Simulated()
    session = _session(_spec(tmp_path, trials=50), link=link)
    _scheduled_at_trial(link, session, 2, ScheduleStop(kind="trials", value=3, by="jake"))

    session.run()

    assert _trials_run(session) == 5
    assert session.stopped_because == "scheduled stop (after trial 5) set by jake"


def test_a_stop_at_a_clock_time_is_read_on_the_sessions_clock(tmp_path, utc):
    """At a clock time on the rig's session clock (spec §5.1): the next occurrence of
    that time, on the session's anchored clock -- `wall_now`, which here follows the
    frames from `WALL_NOW` (22:13:20) -- so 22:14 is forty seconds in."""
    link = Simulated()
    link.queue(ScheduleStop(kind="clock", value="22:14", by="jake"))
    session = _session(_spec(tmp_path, trials=500), link=link)

    session.run()

    assert session.stopped_because == "scheduled stop (at 22:14) set by jake"
    (schedule, fired) = _controls_rows(session)
    assert schedule["target"] == WALL_NOW + 40.0
    assert fired["at"] >= WALL_NOW + 40.0
    frames = [frame.wall_at for frame in link.published]
    assert frames[-3] < WALL_NOW + 40.0 <= frames[-1], "it stopped at the first boundary past 22:14"


def test_a_clock_time_already_past_or_exactly_now_is_tomorrows(tmp_path, utc):
    """Review Focus 4: a scheduled time that is past, or exactly now, is the next
    occurrence of it -- tomorrow's -- as the spec rules, and the feed and the strip
    say which day, so a slip of the hour is read rather than waited for."""
    from wl_expcontroller.taskd import _next_occurrence

    assert _next_occurrence("22:14", WALL_NOW) == WALL_NOW + 40.0
    assert _next_occurrence("22:13", WALL_NOW) == WALL_NOW - 20.0 + 86_400.0
    assert _next_occurrence("22:13", WALL_NOW - 20.0) == WALL_NOW - 20.0 + 86_400.0
    assert _next_occurrence("00:00", WALL_NOW) == WALL_NOW + 6_400.0

    link = Simulated()
    link.queue(ScheduleStop(kind="clock", value="22:13", by="jake"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.scheduled_stop[3] == "at 22:13 on 2023-11-15"
    assert session.controls[0][3] == "scheduled stop at 22:13 on 2023-11-15"


def test_a_stop_after_fluid_reads_welfares_session_fluid(tmp_path):
    """After X mL this session, read from `welfare`'s session fluid (spec §5.1) --
    `session_total()`, the figure the console shows -- and nothing else."""
    link = Simulated()
    link.queue(ScheduleStop(kind="fluid", value=0.3, by="jake"))
    session = _session(_spec(tmp_path, trials=200), link=link)

    session.run()

    assert session.stopped_because == "scheduled stop (after 0.3 mL this session) set by jake"
    assert session.welfare.session_total() >= 0.3
    before_last = [frame.fluid_session_ml for frame in link.published][-3]
    assert before_last < 0.3, "it stopped at the first boundary at or past 0.3 mL"


def test_a_new_schedule_replaces_the_old_and_says_so(tmp_path):
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=2, by="jake"))
    link.queue(ScheduleStop(kind="trials", value=4, by="sam"))
    session = _session(_spec(tmp_path, trials=50), link=link)

    session.run()

    assert _trials_run(session) == 4
    assert session.stopped_because == "scheduled stop (after trial 4) set by sam"
    assert session.controls[1][3] == "scheduled stop after trial 4, replacing after trial 2"


def test_cancel_removes_the_scheduled_stop(tmp_path):
    link = Simulated()
    link.queue(ScheduleStop(kind="trials", value=2, by="jake"))
    link.queue(CancelScheduledStop(by="sam"))
    session = _session(_spec(tmp_path, trials=5), link=link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.scheduled_stop is None
    cancel = _controls_rows(session)[1]
    assert (cancel["kind"], cancel["by"], cancel["cancelled"]) == ("cancel", "sam", "after trial 2")


def test_cancel_with_nothing_scheduled_is_refused(tmp_path):
    link = Simulated()
    link.queue(CancelScheduledStop(by="sam"))
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    assert session.refusals == [
        ("cancel", "sam", "there is no scheduled stop to cancel; nothing changed")
    ]


def test_a_malformed_schedule_that_never_crossed_the_wire_is_refused(tmp_path):
    """`link.check_schedule` is asked again of a schedule that reached the session
    without the wire, so one rule holds on both paths."""
    link = Simulated()
    link.queue(ScheduleStop(kind="clock", value="25:00", by="jake"))
    session = _session(_spec(tmp_path, trials=2), link=link)

    session.run()

    ((name, by, why),) = session.refusals
    assert (name, by) == ("schedule", "jake")
    assert "HH:MM" in why and why.endswith("so it is refused")
    assert session.scheduled_stop is None


def test_a_scheduled_stop_ends_a_paused_session(tmp_path, utc):
    """Checked at each trial boundary *and while paused* (spec §5.1)."""
    link = _Scripted(step=30.0)
    link.queue(Pause(by="jake"))
    link.queue(ScheduleStop(kind="clock", value="22:14", by="sam"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stopped_because == "scheduled stop (at 22:14) set by sam"
    assert len(link.waits) == 2, "22:14 passed on the second thirty-second wait"


def test_the_limit_wins_when_it_and_a_schedule_fall_due_together(tmp_path, utc):
    """Both at one check: the out-of-cage limit is asked first, and a session that
    reached it ends as `limit`, never as an operator's stop."""
    link = _Scripted(step=900.0)
    link.queue(Pause(by="jake"))
    link.queue(ScheduleStop(kind="clock", value="22:14", by="sam"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "limit"
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py`
Expected: ten of the eleven new tests fail — Task 2's fallback refuses *a 'schedule' command is not one this session acts on*, and `_next_occurrence` cannot be imported. `test_the_limit_wins_when_it_and_a_schedule_fall_due_together` passes already, since nothing is scheduled yet: it stays as the guard on the order `_ends` asks in.

- [ ] **Step 3: Implement**

In `wl_expcontroller/taskd.py`, replace:

```python
import threading
from collections import deque
```

with:

```python
import threading
import time
from collections import deque
```

In `wl_expcontroller/taskd.py`, in `_gap`, replace:

```python
    return later - earlier

```

with:

```python
    return later - earlier


def _next_occurrence(hhmm: str, wall: float) -> float:
    """The first instant after `wall` at which this host's local clock reads `hhmm`
    (P4d-2b spec §5.1: "the next occurrence of that time, within 24 hours").

    **`wall` is the session's anchored clock** (`Session.wall_now`), so a scheduled
    stop is read on the clock every welfare instant is on, and a host clock stepped
    mid-session moves it no more than it moves the out-of-cage limit. Local time is
    the host's zone, as the departure mark's clock time is (`cli._wall_clock_time`),
    and `time.mktime` with `tm_isdst=-1` lets the platform say whether daylight
    saving applies on the day, and rolls day 32 into the next month.

    **Exactly now counts as past**: `hhmm` read at 14:30:00 names tomorrow's 14:30,
    because the spec's occurrence is the next one. The schedule's own words then
    carry the date (`Session._schedule`), so the slip is read, not waited for."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    today = time.localtime(wall)
    for days in (0, 1):
        target = time.mktime(
            (today.tm_year, today.tm_mon, today.tm_mday + days, hour, minute, 0, 0, 0, -1)
        )
        if target > wall:
            return target
    # Unreachable: tomorrow's `hhmm` is after `wall` on every calendar day. Said
    # rather than looped past, so a platform where it is not fails here, by name.
    raise ValueError(f"no occurrence of {hhmm} after {wall} within a day")

```

In `wl_expcontroller/taskd.py`, in `Session`, replace:

```python
    controls_dropped: int = field(init=False, default=0)
    #: `OPERATOR_MARK`'s code, looked up once when `run()` starts so the frame never
```

with:

```python
    controls_dropped: int = field(init=False, default=0)
    #: The scheduled stop, held here so a closed page cannot lose it (P4d-2b spec
    #: §5.1): `(kind, target, by, said)`, or `None`. `target` is an instant on the
    #: session's anchored clock (`clock`), a trial count (`trials`) or mL this
    #: session (`fluid`); `said` is its words, used by the feed, the strip and the
    #: stop reason alike. One at a time: a new schedule replaces it.
    scheduled_stop: tuple | None = field(init=False, default=None)
    #: `OPERATOR_MARK`'s code, looked up once when `run()` starts so the frame never
```

In `wl_expcontroller/taskd.py`, in `Session._control`, replace:

```python
        by: str,
        said: str,
```

with:

```python
        by: str,
        feed: str,
```

In `wl_expcontroller/taskd.py`, in `Session._control`, replace:

```python
        """One control event: onto the changes feed and into the session record, at
        `at` on the session's anchored clock -- now, unless the event was stamped
        earlier (a mark, in its frame) -- which it returns (P4d-2b spec §5.1).
        `index` is the trial it happened in or, between trials, the trial about to
        run; `detail` is the record row's own fields."""
```

with:

```python
        """One control event: onto the changes feed, saying `feed`, and into the
        session record, at `at` on the session's anchored clock -- now, unless the
        event was stamped earlier (a mark, in its frame) -- which it returns (P4d-2b
        spec §5.1). `index` is the trial it happened in or, between trials, the trial
        about to run; `detail` is the record row's own fields."""
```

In `wl_expcontroller/taskd.py`, in `Session._control`, replace:

```python
            self.controls_dropped += 1
        self._controls.append((kind, by, at, said))
```

with:

```python
            self.controls_dropped += 1
        self._controls.append((kind, by, at, feed))
```

In `wl_expcontroller/taskd.py`, in `Session`, replace:

```python

    def _ends(self) -> bool:
```

with:

```python

    def _schedule(self, command, index: int) -> None:
        """Hold a scheduled stop (P4d-2b spec §5.1), replacing any before it.

        `link.check_schedule` is asked again here -- the wire asked it of a command
        that crossed it -- so a schedule that reached the session another way meets
        the same rule. The target is fixed now: a clock time's next occurrence on
        the session's anchored clock, a trial count from the trials run so far, or
        mL this session."""
        why = _link.check_schedule(command.kind, command.value)
        if why is not None:
            self._refuse("schedule", command.by, f"{why}, so it is refused")
            return
        if self.stopped_because:
            self._refuse(
                "schedule",
                command.by,
                f"the session is stopping ({self.stopped_because}); a schedule is not "
                f"applied",
            )
            return
        if command.kind == "clock":
            wall = self.wall_now()
            target = _next_occurrence(command.value, wall)
            said = f"at {command.value}"
            if time.localtime(target)[:3] != time.localtime(wall)[:3]:
                said += f" on {time.strftime('%Y-%m-%d', time.localtime(target))}"
        elif command.kind == "trials":
            target = float(index + command.value)
            said = f"after trial {index + command.value}"
        else:
            target = float(command.value)
            said = f"after {command.value:g} mL this session"
        replaced = self.scheduled_stop
        self.scheduled_stop = (command.kind, target, command.by, said)
        self._control(
            "schedule",
            command.by,
            f"scheduled stop {said}" + (f", replacing {replaced[3]}" if replaced else ""),
            index,
            stop=command.kind,
            target=target,
            said=said,
            replaced=replaced[3] if replaced else None,
        )

    def _cancel(self, by: str, index: int) -> None:
        """Remove the scheduled stop (spec §5.1), or say there is none."""
        if self.scheduled_stop is None:
            self._refuse("cancel", by, "there is no scheduled stop to cancel; nothing changed")
            return
        said = self.scheduled_stop[3]
        self.scheduled_stop = None
        self._control(
            "cancel", by, f"cancelled the scheduled stop {said}", index, cancelled=said
        )

    def _ends(self, index: int) -> bool:
```

In `wl_expcontroller/taskd.py`, in `Session._ends`, replace:

```python
        set: the out-of-cage limit, `welfare.must_stop`, read on the wall as ever
        (P4d-2a spec §10). **One place for it**, asked between trials and on every
        pass of the paused loop alike (P4d-2b spec §5.1: "ending the session on it
        exactly as between trials"), so the limit cannot be enforced in one of the
        two and not the other."""
        stop = self.welfare.must_stop(self.wall_now())
```

with:

```python
        set. **One place for it**, asked between trials and on every pass of the
        paused loop alike (P4d-2b spec §5.1: "ending the session on it exactly as
        between trials"), so neither can be enforced on one path and not the other.

        **The out-of-cage limit first**, `welfare.must_stop`, read on the wall as
        ever (P4d-2a spec §10): a session at its limit ends as `limit` even when a
        schedule fell due at the same check. **Then the scheduled stop**, which ends
        the session like the stop button -- `stop_kind` `operator`, the reason
        *scheduled stop (...) set by NAME* -- when its clock time has come on the
        session's anchored clock, `index` trials have run, or `welfare`'s session
        fluid has reached it. `welfare` is read, never asked to decide."""
        wall = self.wall_now()
        stop = self.welfare.must_stop(wall)
```

In `wl_expcontroller/taskd.py`, in `Session._ends`, replace:

```python
            return True
        return False
```

with:

```python
            return True
        if self.scheduled_stop is None:
            return False
        kind, target, by, said = self.scheduled_stop
        due = (
            wall >= target
            if kind == "clock"
            else index >= target
            if kind == "trials"
            else self.welfare.session_total() >= target
        )
        if not due:
            return False
        self.stopped_because = f"scheduled stop ({said}) set by {by}"
        self.stop_kind = "operator"
        # Spent: the stop reason says it now, and a console no longer offers to
        # cancel a stop that has happened.
        self.scheduled_stop = None
        self._control(
            "scheduled_stop", by, self.stopped_because, index, stop=kind, target=target
        )
        return True
```

In `wl_expcontroller/taskd.py`, in `Session._hold`, replace:

```python
                return
            if self._ends():
```

with:

```python
                return
            if self._ends(index):
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
            self._mark_note(command, index)
            return
```

with:

```python
            self._mark_note(command, index)
            return
        if isinstance(command, _link.ScheduleStop):
            self._schedule(command, index)
            return
        if isinstance(command, _link.CancelScheduledStop):
            self._cancel(command.by, index)
            return
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
                # the same question the paused loop asks.
                if self._ends():
```

with:

```python
                # the same question the paused loop asks.
                if self._ends(index):
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1242 passed**.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/taskd.py tests/test_taskd.py
git commit -m "Hold a scheduled stop by clock time, trials or fluid, and end the session on it"
```

---

### Task 8: Telemetry schema 8, and every setting change on the feed

**Why:** spec §5.1: schema 8 adds what the page needs — whether the session is paused and since when, the scheduled stop (kind, target, who), and a bounded list of recent control events for the changes feed — and a schema-7 reader refuses schema 8 (Plan decision 9). Spec §5.2: the feed lists *every* setting change with who made it; a staged row leaves `Telemetry.staged` when it applies, so `_apply_staged` puts each applied change on the feed as `set` — not in `controls.jsonl`, since `parameter_changes.jsonl` already records it.

**Files:**
- Modify: `wl_expcontroller/link.py` (`SCHEMA` and its history; `ScheduledStop`, `Control`; four `Telemetry` fields; `Telemetry.of`, `encode`, `_telemetry_from`)
- Modify: `wl_expcontroller/taskd.py` (import `_shown`; `_feed`; `_apply_staged(index)`)
- Test: `tests/test_link.py` (the `_session_with` stand-in; new tests), `tests/test_cli.py` (the `_telemetry` fixture; one schema string), `tests/test_serve.py` (schema strings), `tests/_frames.py`, `tests/test_taskd.py`

**Interfaces:**
- Consumes: Task 5's `Session.paused_at`, `controls`, `controls_dropped`, `_control`; Task 7's `Session.scheduled_stop`.
- Produces:
  - `link.SCHEMA == 8`.
  - `link.ScheduledStop(kind: str, target: float, by: str, said: str)` and `link.Control(kind: str, by: str, at: float, said: str)`, frozen and slotted.
  - `Telemetry` gains, after `recent_outcomes`: `paused_at: float | None`, `scheduled_stop: ScheduledStop | None`, `controls: tuple` (of `Control`), `controls_dropped: int`. Tasks 9–13 read them by name.
  - `Session._feed(kind, by, at, said)`; `Session._apply_staged(index: int)`; the feed kind `set`, saying *fix_hold 0.30 → 0.40, from trial 1*.

- [ ] **Step 1: Write the failing tests, and move the fixtures to schema 8**

In `tests/_frames.py`, replace:

```python
"""A complete schema-7 `Telemetry` frame for the browser console's tests (P4d-2b b1).

```

with:

```python
"""A complete `Telemetry` frame, at this build's `SCHEMA`, for the browser console's
tests (P4d-2b b1; schema 8's fields since b2a).

```

In `tests/_frames.py`, replace:

```python
field that may be `None` holds a number here, so a test that wants an absence asks
for it by name.
```

with:

```python
field that may be `None` holds a number here, so a test that wants an absence asks
for it by name -- **except schema 8's `paused_at` and `scheduled_stop`**, whose
`None` is the ordinary running session (not paused, nothing scheduled), and whose
number would make every frame here a paused one.
```

In `tests/_frames.py`, in `frame`, replace:

```python
        recent_outcomes=("correct", "no_fixation", "correct"),
    )
```

with:

```python
        recent_outcomes=("correct", "no_fixation", "correct"),
        paused_at=None,
        scheduled_stop=None,
        controls=(),
        controls_dropped=0,
    )
```

In `tests/test_cli.py`, in `_telemetry`, replace:

```python

    `schema=SCHEMA`, not a stale literal (fix round 1, I3): `decode` now refuses any
```

with:

```python

    Schema 8's (P4d-2b b2a) default to a running session that is not paused, has
    nothing scheduled and no control yet -- the quiet case, as above.

    `schema=SCHEMA`, not a stale literal (fix round 1, I3): `decode` now refuses any
```

In `tests/test_cli.py`, in `_telemetry`, replace:

```python
        recent_outcomes=(),
    )
```

with:

```python
        recent_outcomes=(),
        paused_at=None,
        scheduled_stop=None,
        controls=(),
        controls_dropped=0,
    )
```

In `tests/test_cli.py`, in `test_console_shows_a_schema_mismatch_as_a_sentence_not_a_traceback`, replace:

```python
    assert "console: a telemetry frame carried schema 6" in captured.err
    assert "this console reads schema 7" in captured.err
```

with:

```python
    assert "console: a telemetry frame carried schema 6" in captured.err
    assert f"this console reads schema {SCHEMA}" in captured.err
```

In `tests/test_link.py`, replace:

```python
    CommandRefused,
    FrameError,
```

with:

```python
    CommandRefused,
    Control,
    FrameError,
```

In `tests/test_link.py`, replace:

```python
    ScheduleStop,
    Simulated,
```

with:

```python
    ScheduleStop,
    ScheduledStop,
    SchemaMismatch,
    Simulated,
```

In `tests/test_link.py`, in `_session_with`, replace:

```python
        ended_wall_at=None,
    )
```

with:

```python
        ended_wall_at=None,
        # Stand-ins for what schema 8 reads (P4d-2b b2a): a running session, not
        # paused, nothing scheduled, no control yet -- `Session.paused_at`,
        # `.scheduled_stop`, `.controls` and `.controls_dropped`.
        paused_at=None,
        scheduled_stop=None,
        controls=(),
        controls_dropped=0,
    )
```

In `tests/test_link.py`, in `test_schema_7_reads_the_configuration_from_the_session`, replace:

```python

    assert telemetry.schema == SCHEMA == 7
```

with:

```python

    assert telemetry.schema == SCHEMA
```

Append to `tests/test_link.py`:

```python


# ---------------------------------------------------------------------------
# Schema 8 (P4d-2b b2a): what the controls need on the page (spec §5.1)
# ---------------------------------------------------------------------------


def test_schema_8_reads_the_pause_the_schedule_and_the_feed_from_the_session():
    """Whether the session is paused and since when, the scheduled stop (kind,
    target, who, and its words), and the bounded list of recent control events --
    each read from the `Session` the record is written from."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.paused_at = 1_700_000_100.0
    session.scheduled_stop = ("trials", 48.0, "jake (box, unverified)", "after trial 48")
    session.controls = (
        ("pause", "jake (box, unverified)", 1_700_000_100.0, "paused at trial 40"),
        ("mark", "", 1_700_000_101.5, "mark 1 stamped while paused, before trial 40"),
    )
    session.controls_dropped = 3

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=40)

    assert telemetry.schema == SCHEMA == 8
    assert telemetry.paused_at == 1_700_000_100.0
    assert telemetry.scheduled_stop == ScheduledStop(
        kind="trials", target=48.0, by="jake (box, unverified)", said="after trial 48"
    )
    assert telemetry.controls == (
        Control("pause", "jake (box, unverified)", 1_700_000_100.0, "paused at trial 40"),
        Control("mark", "", 1_700_000_101.5, "mark 1 stamped while paused, before trial 40"),
    )
    assert telemetry.controls_dropped == 3


def test_a_running_session_with_nothing_scheduled_says_so_with_none():
    telemetry = _telemetry()

    assert telemetry.paused_at is None
    assert telemetry.scheduled_stop is None
    assert telemetry.controls == () and telemetry.controls_dropped == 0


def test_schema_8_survives_the_wire_with_its_absences_intact():
    """The golden round trip, both ways round: everything populated, and every new
    field at its absence."""
    populated = _telemetry(
        paused_at=1_700_000_100.0,
        scheduled_stop=ScheduledStop("clock", 1_700_003_600.0, "jake", "at 14:30"),
        controls=(
            Control("note", "jake", 1_700_000_102.0, 'mark 1: "<b>bubble</b>"'),
            Control("resume", "sam", 1_700_000_200.0, "resumed after 1:40 paused"),
        ),
        controls_dropped=7,
    )
    bare = _telemetry()

    for original in (populated, bare):
        restored = decode(encode(original))
        assert restored == original
        assert all(type(c) is Control for c in restored.controls)
    assert type(decode(encode(populated)).scheduled_stop) is ScheduledStop
    assert decode(encode(bare)).scheduled_stop is None
    assert decode(encode(bare)).paused_at is None


def test_a_schema_7_frame_is_refused_by_a_schema_8_reader():
    """§3's schema rule: a reader built for 8 refuses 7 by name, before touching a
    field (`SchemaMismatch`), and says which it reads."""
    old = encode(replace(_telemetry(), schema=7))

    with pytest.raises(SchemaMismatch, match="carried schema 7 and this console reads schema 8"):
        decode(old)
```

In `tests/test_serve.py`, replace:

```python
from wl_expcontroller.cli import main
from wl_expcontroller.link import Stop, ZmqConsole, ZmqLink
```

with:

```python
from wl_expcontroller.cli import main
from wl_expcontroller.link import SCHEMA, Stop, ZmqConsole, ZmqLink
```

In `tests/test_serve.py`, replace:

```python
    "a telemetry frame carried schema 6, and this console reads schema 7, so it is "
    "not shown"
```

with:

```python
    f"a telemetry frame carried schema 6, and this console reads schema {SCHEMA}, so "
    f"it is not shown"
```

In `tests/test_serve.py`, in `test_a_frame_this_console_cannot_read_is_shown_as_refused_not_guessed`, replace:

```python
        )
        assert "this console reads schema 7" in why
        assert server.hub.snapshot(on_box=True, stale_after_s=30.0)[0] is None
```

with:

```python
        )
        assert f"this console reads schema {SCHEMA}" in why
        assert server.hub.snapshot(on_box=True, stale_after_s=30.0)[0] is None
```

In `tests/test_serve.py`, in `test_a_frame_this_console_cannot_read_is_shown_as_refused_not_guessed`, replace:

```python
            server,
            lambda: link._pub.send(msgpack.packb({"schema": 7}, use_bin_type=True)),
```

with:

```python
            server,
            lambda: link._pub.send(msgpack.packb({"schema": SCHEMA}, use_bin_type=True)),
```

In `tests/test_serve.py`, in `test_a_real_schema_6_frame_is_refused_by_name_not_a_keyerror`, replace:

```python
        )
        assert "this console reads schema 7" in why
```

with:

```python
        )
        assert f"this console reads schema {SCHEMA}" in why
```

In `tests/test_taskd.py`, in `test_a_stop_after_n_trials_ends_the_session_there_with_its_reason`, replace:

```python
    assert session.scheduled_stop is None, "a stop that has happened is spent"
    rows = _controls_rows(session)
```

with:

```python
    assert session.scheduled_stop is None, "a stop that has happened is spent"
    assert link.published[-1].scheduled_stop is None
    rows = _controls_rows(session)
```

Append to `tests/test_taskd.py`:

```python


def test_an_applied_setting_is_on_the_changes_feed_with_who_and_when(tmp_path):
    """Spec §5.2: the changes feed lists every setting change with who made it. A
    staged row leaves `Telemetry.staged` when it is applied; the feed keeps it, as
    `set`, with the trial it applies from. The record already has it, in
    `parameter_changes.jsonl`, so no control row repeats it there."""
    link = Simulated()
    link.queue(SetParameter(name="fix_hold", value=0.4, by="jake (box, unverified)"))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    ((kind, by, at, said),) = session.controls
    assert (kind, by) == ("set", "jake (box, unverified)")
    assert said == "fix_hold 0.30 → 0.40, from trial 1"
    assert at >= WALL_NOW
    assert _controls_rows(session) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider --continue-on-collection-errors tests/test_link.py tests/test_cli.py tests/test_taskd.py tests/test_web.py`
Expected: `tests/test_link.py` fails to collect — `ImportError: cannot import name 'Control'`; the fixtures in `test_cli.py` and `_frames.py` raise `TypeError: Telemetry.__init__() got an unexpected keyword argument 'paused_at'`; `test_an_applied_setting_is_on_the_changes_feed_with_who_and_when` fails on an empty feed, and `test_a_stop_after_n_trials_ends_the_session_there_with_its_reason` on its new line, `AttributeError: 'Telemetry' object has no attribute 'scheduled_stop'`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/link.py`, replace:

```python
#: showing a guess (`serve.Server._listen`).
SCHEMA = 7
```

with:

```python
#: showing a guess (`serve.Server._listen`).
#:
#: 8 (2026-09-27, P4d-2b b2a): the controls from the box -- `paused_at` (whether the
#: session is paused, and since when), `scheduled_stop` (kind, target, who, and its
#: words), and `controls` with `controls_dropped` (the recent control events a
#: changes feed lists). Nothing changed meaning. A schema-7 reader refuses a schema-8
#: frame, and a schema-8 reader a schema-7 one, by name (`SchemaMismatch`), as §3's
#: schema rule says.
SCHEMA = 8
```

In `wl_expcontroller/link.py`, in `ParamRow`, replace:

```python
    value: float | str | None
    bounded: bool

```

with:

```python
    value: float | str | None
    bounded: bool


@dataclass(frozen=True, slots=True)
class ScheduledStop:
    """The scheduled stop a session holds (P4d-2b spec §5.1), as a console shows it:
    from `taskd.Session.scheduled_stop`.

    `kind` is `clock`, `trials` or `fluid`. `target` is when it falls due: an instant
    on the session's anchored clock, the trial count it stops at, or mL this session.
    `said` is its words -- *at 14:30*, *after trial 48*, *after 5 mL this session*
    -- the same the feed and the stop reason use, so a console shows the rig's
    sentence rather than composing its own."""

    kind: str
    target: float
    by: str
    said: str


@dataclass(frozen=True, slots=True)
class Control:
    """One recent control event for a console's changes feed (P4d-2b spec §5.1):
    from `taskd.Session.controls`. `kind` is `stop`, `pause`, `resume`, `mark`,
    `note`, `schedule`, `cancel`, `scheduled_stop` or `set` (a staged setting applied);
    `by` is who sent it, empty for a mark's stamp, whose sender arrives with its note;
    `at` is on the session's anchored clock; `said` is the sentence after the kind.
    The session record keeps every one (`record.CONTROLS`); this feed keeps the last
    `CONTROL_HISTORY`."""

    kind: str
    by: str
    at: float
    said: str

```

In `wl_expcontroller/link.py`, in `Telemetry`, replace:

```python
    recent_outcomes: tuple

```

with:

```python
    recent_outcomes: tuple
    #: `session.paused_at`: when a console paused the session, on the session's
    #: anchored clock, or `None` while trials run (P4d-2b spec §5.1). A session that
    #: ended while paused keeps it; `stop_kind` says it ended.
    paused_at: float | None
    #: `session.scheduled_stop` as a `ScheduledStop`, or `None` when nothing is
    #: scheduled.
    scheduled_stop: ScheduledStop | None
    #: `session.controls` as `Control` rows, oldest first: the last
    #: `CONTROL_HISTORY` control events, for the changes feed.
    controls: tuple
    #: How many control events are **not** in `controls`, having fallen off the far
    #: end -- zero for a session nobody controlled much, and never a quiet cap.
    controls_dropped: int

```

In `wl_expcontroller/link.py`, in `Telemetry.of`, replace:

```python
            recent_outcomes=session.recent_outcomes,
        )
```

with:

```python
            recent_outcomes=session.recent_outcomes,
            # P4d-2b b2a (spec §5.1): the session's own, through its public surface.
            paused_at=session.paused_at,
            scheduled_stop=(
                None
                if session.scheduled_stop is None
                else ScheduledStop(*session.scheduled_stop)
            ),
            controls=tuple(Control(*row) for row in session.controls),
            controls_dropped=session.controls_dropped,
        )
```

In `wl_expcontroller/link.py`, in `encode`, replace:

```python
        "recent_outcomes": list(telemetry.recent_outcomes),
    }
```

with:

```python
        "recent_outcomes": list(telemetry.recent_outcomes),
        "paused_at": telemetry.paused_at,
        "scheduled_stop": (
            None
            if telemetry.scheduled_stop is None
            else {
                "kind": telemetry.scheduled_stop.kind,
                "target": telemetry.scheduled_stop.target,
                "by": telemetry.scheduled_stop.by,
                "said": telemetry.scheduled_stop.said,
            }
        ),
        "controls": [
            {"kind": c.kind, "by": c.by, "at": c.at, "said": c.said}
            for c in telemetry.controls
        ],
        "controls_dropped": telemetry.controls_dropped,
    }
```

In `wl_expcontroller/link.py`, in `_telemetry_from`, replace:

```python
        recent_outcomes=tuple(data["recent_outcomes"]),
    )
```

with:

```python
        recent_outcomes=tuple(data["recent_outcomes"]),
        paused_at=data["paused_at"],
        scheduled_stop=(
            None
            if data["scheduled_stop"] is None
            else ScheduledStop(**data["scheduled_stop"])
        ),
        controls=tuple(Control(**c) for c in data["controls"]),
        controls_dropped=data["controls_dropped"],
    )
```

In `wl_expcontroller/taskd.py`, replace:

```python
from wl_expcontroller.check import check
from wl_expcontroller.cli import _clock, _load_allocation, _load_trial
```

with:

```python
from wl_expcontroller.check import check
from wl_expcontroller.cli import _clock, _load_allocation, _load_trial, _shown
```

In `wl_expcontroller/taskd.py`, in `Session._control`, replace:

```python
        if len(self._controls) == self._controls.maxlen:
            self.controls_dropped += 1
        self._controls.append((kind, by, at, feed))
```

with:

```python
        self._feed(kind, by, at, feed)
```

In `wl_expcontroller/taskd.py`, in `Session._control`, replace:

```python
        return at

```

with:

```python
        return at

    def _feed(self, kind: str, by: str, at: float, said: str) -> None:
        """One row onto the changes feed, counting what the cap pushes off -- see
        `controls_dropped`. `_control` adds the record row; an applied setting,
        which `parameter_changes.jsonl` already records, comes here alone."""
        if len(self._controls) == self._controls.maxlen:
            self.controls_dropped += 1
        self._controls.append((kind, by, at, said))

```

In `wl_expcontroller/taskd.py`, in `Session`, replace:

```python

    def _apply_staged(self) -> None:
```

with:

```python

    def _apply_staged(self, index: int) -> None:
```

In `wl_expcontroller/taskd.py`, in `Session._apply_staged`, replace:

```python
        change ships. Named so the next reader can grep it rather than believe it.
        """
```

with:

```python
        change ships. Named so the next reader can grep it rather than believe it.

        **Each applied row goes onto the changes feed** (P4d-2b spec §5.2: the feed
        lists every setting change, with who made it), as `set`, naming `index`,
        the first trial it applies to: its staged row leaves `Telemetry.staged`
        here, and the feed is where a console still sees it.
        """
```

In `wl_expcontroller/taskd.py`, in `Session._apply_staged`, replace:

```python
            self.card.emit(self.allocation.code_for("PARAM_CHANGED"))
        self._staged.clear()
```

with:

```python
            self.card.emit(self.allocation.code_for("PARAM_CHANGED"))
            self._feed(
                "set",
                by,
                self.wall_now(),
                f"{name} {_shown(was)} → {_shown(now)}, from trial {index}",
            )
        self._staged.clear()
```

In `wl_expcontroller/taskd.py`, in `Session.run`, replace:

```python
            while True:
                self._apply_staged()
```

with:

```python
            while True:
                self._apply_staged(index)
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_cli.py tests/test_taskd.py tests/test_web.py tests/test_health.py tests/test_serve.py`
Expected: all pass. `test_serve.py`'s refused-frame tests now name schema 8, from `SCHEMA`.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1247 passed**.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/taskd.py tests/test_link.py tests/test_cli.py tests/test_serve.py tests/_frames.py tests/test_taskd.py
git commit -m "Publish the pause, the scheduled stop and the control feed: telemetry schema 8"
```

---

### Task 9: `wlx console` renders schema 8

**Why:** the terminal client is a console too, and `render`'s promise is that every line names a field. Schema 8's four fields each get a line — *paused*, *scheduled stop*, and a *control* line per event with the dropped count above them, as the refusal lines have — and every absence is a word.

**Files:**
- Modify: `wl_expcontroller/cli.py` (`render` and its docstring)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 8's `ScheduledStop`, `Control` and the four fields.
- Produces: `render`'s lines `  paused: no` / `  paused: since HH:MM:SS` / `  paused: since an unknown time`; `  scheduled stop: none` / `  scheduled stop: <said>, set by <by>`; `  controls: none` / `  control: <kind>[ by <by>]: <said>`, after the staged lines.

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py`, replace:

```python
    SCHEMA,
    ParamRow,
```

with:

```python
    SCHEMA,
    Control,
    ParamRow,
```

In `tests/test_cli.py`, replace:

```python
    Refused,
    SetParameter,
```

with:

```python
    Refused,
    ScheduledStop,
    SetParameter,
```

Append to `tests/test_cli.py`:

```python


# ---------------------------------------------------------------------------
# `render` and schema 8 (P4d-2b b2a): every new field has a line
# ---------------------------------------------------------------------------


def test_console_says_when_nothing_is_paused_scheduled_or_controlled():
    rendered = render(_telemetry()).splitlines()

    assert "  paused: no" in rendered
    assert "  scheduled stop: none" in rendered
    assert "  controls: none" in rendered


def test_console_names_a_pause_by_its_clock_time():
    at = 1_700_000_000.0
    expected = time.strftime("%H:%M:%S", time.localtime(at))

    assert f"  paused: since {expected}" in render(_telemetry(paused_at=at)).splitlines()


@pytest.mark.parametrize("at", [float("nan"), float("inf")])
def test_console_says_a_pause_instant_that_is_not_a_number_is_unknown(at):
    assert "  paused: since an unknown time" in render(
        _telemetry(paused_at=at)
    ).splitlines()


def test_console_names_the_scheduled_stop_and_who_set_it():
    rendered = render(
        _telemetry(
            scheduled_stop=ScheduledStop("trials", 48.0, "jake (box, unverified)", "after trial 48")
        )
    ).splitlines()

    assert "  scheduled stop: after trial 48, set by jake (box, unverified)" in rendered


def test_console_lists_control_events_and_counts_what_fell_off_before_them():
    rendered = render(
        _telemetry(
            controls=(
                Control("mark", "", 1_700_000_001.0, "mark 1 stamped in trial 3, frame 10"),
                Control("note", "jake", 1_700_000_002.0, 'mark 1: "bubble"'),
            ),
            controls_dropped=4,
        )
    ).splitlines()

    dropped = rendered.index(
        "  control: 4 earlier control event(s) NOT SHOWN -- only the most recent 2 are "
        "kept (link.CONTROL_HISTORY)"
    )
    stamp = rendered.index("  control: mark: mark 1 stamped in trial 3, frame 10")
    note = rendered.index('  control: note by jake: mark 1: "bubble"')
    assert dropped < stamp < note
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_cli.py -k "nothing_is_paused or pause or scheduled_stop or control_events"`
Expected: the six new tests fail — `render` has no such lines.

- [ ] **Step 3: Implement**

In `wl_expcontroller/cli.py`, in `render`, replace:

```python
    *PROVISIONAL*, *not given*, *none yet*, *unset*, *open* -- never a zero.
    """
```

with:

```python
    *PROVISIONAL*, *not given*, *none yet*, *unset*, *open* -- never a zero.

    **Schema 8 adds the controls** (P4d-2b b2a): whether the session is paused and
    since when, the scheduled stop and who set it -- in the rig's own words -- and
    the recent control events, each with who sent it, below the staged rows. A capped
    feed says so above its rows, as the refusal feed does. Absences are words again:
    *no*, *none*.
    """
```

In `wl_expcontroller/cli.py`, in `render`, replace:

```python
    lines.append(f"  phase: {frame.phase.replace('_', ' ')}")
    if frame.stopped_because:
```

with:

```python
    lines.append(f"  phase: {frame.phase.replace('_', ' ')}")
    # Schema 8 (P4d-2b b2a). The pause's instant as a clock time on this host, like
    # the last reward's; one that is not a number is `unknown`, never a crash.
    if frame.paused_at is None:
        lines.append("  paused: no")
    elif not math.isfinite(frame.paused_at):
        lines.append("  paused: since an unknown time")
    else:
        lines.append(
            f"  paused: since "
            f"{time.strftime('%H:%M:%S', time.localtime(frame.paused_at))}"
        )
    # The rig's own words for it, never recomposed here from `kind` and `target`.
    lines.append(
        "  scheduled stop: none"
        if frame.scheduled_stop is None
        else f"  scheduled stop: {frame.scheduled_stop.said}, set by "
        f"{frame.scheduled_stop.by}"
    )
    if frame.stopped_because:
```

In `wl_expcontroller/cli.py`, in `render`, replace:

```python
        lines.append("  staged: none")

```

with:

```python
        lines.append("  staged: none")

    # The changes feed's control events (schema 8), oldest first like the refusals
    # below, the count of what fell off the cap before them for the same reason. A
    # mark's stamp has no sender -- it arrives with the note -- and says so by
    # naming none.
    if frame.controls:
        if frame.controls_dropped:
            lines.append(
                f"  control: {frame.controls_dropped} earlier control event(s) NOT "
                f"SHOWN -- only the most recent {len(frame.controls)} are kept "
                f"(link.CONTROL_HISTORY)"
            )
        for control in frame.controls:
            who = f" by {control.by}" if control.by else ""
            lines.append(f"  control: {control.kind}{who}: {control.said}")
    else:
        lines.append("  controls: none")

```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_cli.py`
Expected: all pass — `test_console_says_a_session_that_has_not_opened_has_no_in_session_clock` still finds no `0:00` on the screen, since the fixture's frame is not paused.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1253 passed**.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/cli.py tests/test_cli.py
git commit -m "Show the pause, the scheduled stop and the control feed in wlx console"
```

---

### Task 10: The page's controls

**Why:** spec §5.2. Each parameter card gets arrows and an input, sent about 600 ms after the last click and shown *staged* until the next trial; stop has a confirm step; pause and resume are one button and the **P** key; **M** or a button sends the mark's signal and opens a note box (Enter attaches, Esc leaves it bare); a small form schedules a stop, and the strip shows it with a cancel button; keys do nothing in a text box; the feed lists every setting change, refusal, pause, resume, mark with its note, and schedule, with who did it; the box's browser asks for a name once and remembers it; everywhere but the box the controls are greyed with §2's sentence; the script grows to send, debounce, handle P and M and ask the name, and still renders nothing itself (Plan decision 12). `/health`'s state reading says *paused*.

**Files:**
- Modify: `wl_expcontroller/web.py` (`import time`; `View.can_write`, `View.can_mark`; `FRAGMENT_IDS`; `CONTROLS_AT_THE_BOX`, `NO_MARK_ENDPOINT`, `DEBOUNCE_MS`; `_clock_time`, `_state`; `_off`, `_scheduled`, `_strip`; `_controls`; `_changes`; `_STEPS`, `_step`, `_field`, `_params`; `fragments`; `_CSS`; `_SCRIPT`; `page`)
- Modify: `wl_expcontroller/health.py` (`_state_text`)
- Test: `tests/test_web.py`, `tests/test_health.py`, `tests/_frames.py`

**Interfaces:**
- Consumes: Task 8's schema-8 fields.
- Produces:
  - `web.View.can_write: bool = False`, `web.View.can_mark: bool = False` — Task 11's `Hub.snapshot` fills them.
  - `web.CONTROLS_AT_THE_BOX`, `web.NO_MARK_ENDPOINT` (Task 11's refusals say them), `web.DEBOUNCE_MS = 600`.
  - `web.FRAGMENT_IDS` gains `"controls"`, after `"banners"`.
  - `web.page(parts, *, stale_after_s: float, nonce: str, can_write: bool = False) -> str`.
  - The page's element ids the script uses: `controls`, `who`, `rename`, `sent`, `stop-confirm`, `stop-yes`, `stop-no`, `mark-form`, `mark-note`, `sched-kind`, `sched-value`, `sched-set`; and the attributes `data-cmd`, `data-param`, `data-step`, `data-min`, `data-max`, `data-kind="word"`, `data-dir`.
  - The body the script posts to `/commands` (Task 11 parses it): `{"kind": ..., "by": NAME, ...}` as Plan decision 10 lists.

- [ ] **Step 1: Write the failing tests**

In `tests/_frames.py`, in `view`, replace:

```python
    after `frame()`'s last reward -- with a derived rate of twelve trials a minute, on
    a console reading `ENDPOINT`."""
```

with:

```python
    after `frame()`'s last reward -- with a derived rate of twelve trials a minute, on
    a console reading `ENDPOINT`. Since P4d-2b b2a it may write, as the box's own page
    may, and its console has the session's mark endpoint."""
```

In `tests/_frames.py`, in `view`, replace:

```python
        endpoint=ENDPOINT,
    )
```

with:

```python
        endpoint=ENDPOINT,
        can_write=True,
        can_mark=True,
    )
```

Append to `tests/test_health.py`:

```python


def test_a_paused_session_is_said_to_be_paused_and_is_ok():
    """P4d-2b b2a: a pause is a person's choice, not a fault, so the verdict stands;
    the state reading says it, so wl-works does not read a held trial count as a
    stalled rig."""
    found = frame(paused_at=1_700_000_030.0)
    values = {
        r["key"]: r["value"]
        for r in readings(
            found, frame_age_s=1.0, stale_after_s=30.0, rejected=None, endpoint=ENDPOINT
        )
    }

    assert values["state"] == "paused · trial 40 · block session"
    assert verdict(found, frame_age_s=1.0, stale_after_s=30.0, rejected=None) == "ok"
```

In `tests/test_web.py`, replace:

```python
import re
import tomllib
```

with:

```python
import re
import time
import tomllib
```

In `tests/test_web.py`, replace:

```python
from _frames import frame, view
from wl_expcontroller.link import ParamRow, Refused, Staged
```

with:

```python
from _frames import frame, view
from wl_expcontroller.link import Control, ParamRow, Refused, ScheduledStop, Staged
```

In `tests/test_web.py`, replace:

```python
    _SCRIPT,
    FONTS,
```

with:

```python
    _SCRIPT,
    CONTROLS_AT_THE_BOX,
    DEBOUNCE_MS,
    FONTS,
```

In `tests/test_web.py`, replace:

```python
    LEGEND,
    font_bytes,
```

with:

```python
    LEGEND,
    NO_MARK_ENDPOINT,
    font_bytes,
```

In `tests/test_web.py`, in `test_the_page_tells_its_script_when_a_stream_is_stale`, replace:

```python

    assert '<body data-stale-after="45">' in document
```

with:

```python

    assert '<body data-stale-after="45" data-can-write="0" data-debounce-ms="600">' in document
```

In `tests/test_web.py`, in `test_nothing_on_the_page_writes`, replace:

```python
def test_nothing_on_the_page_writes():
    """Spec §4.2: every write control is absent until its slice. The page's buttons
    close and reopen its own stream; its inputs only choose a tab."""
```

with:

```python
def test_the_page_writes_only_by_posting_json_to_commands():
    """Spec §4.2, as amended by §5.2: the page's writes are the controls, and every
    one goes through the script's one `fetch` -- a JSON `POST` to `/commands` -- and
    never a form (the Content-Security-Policy's `form-action 'none'` refuses one
    anyway). Its radio inputs still only choose a tab."""
```

In `tests/test_web.py`, in `test_the_page_writes_only_by_posting_json_to_commands`, replace:

```python
    assert document.count("<button") == 2
    assert 'id="close"' in document and 'id="reconnect"' in document
    for absent in ("<form", "<textarea", "<select", "POST", "fetch("):
        assert absent not in document, absent
    inputs = re.findall(r"<input[^>]*>", document)
    assert len(inputs) == 4
    assert all('type="radio"' in field for field in inputs)
```

with:

```python
    assert "<form" not in document and "<textarea" not in document
    assert _SCRIPT.count("fetch(") == 1
    assert 'fetch("/commands", {' in _SCRIPT
    assert 'method: "POST"' in _SCRIPT
    assert 'headers: { "Content-Type": "application/json" }' in _SCRIPT
    radios = re.findall(r'<input type="radio"[^>]*>', document)
    assert len(radios) == 4
```

In `tests/test_web.py`, replace:

```python

def test_the_script_does_only_what_spec_4_3_asks():
```

with:

```python

def test_the_script_does_only_what_spec_4_3_and_5_2_ask():
    """§4.3's stream, and §5.2's growth: it sends commands, debounces the arrows,
    handles P and M, and asks for the name. It still renders nothing itself: every
    `innerHTML` it writes is a fragment `wlx serve` rendered."""
```

In `tests/test_web.py`, in `test_the_script_does_only_what_spec_4_3_and_5_2_ask`, replace:

```python
        'addEventListener("frame"',
        "innerHTML",
```

with:

```python
        'addEventListener("frame"',
```

In `tests/test_web.py`, in `test_the_script_does_only_what_spec_4_3_and_5_2_ask`, replace:

```python
        "source.close()",
    ):
```

with:

```python
        "source.close()",
        'fetch("/commands", {',
        "window.prompt(",
        'k === "p"',
        'k === "m"',
    ):
```

In `tests/test_web.py`, in `test_the_script_does_only_what_spec_4_3_and_5_2_ask`, replace:

```python
    assert "disconnected · the session keeps running on the box" in document

```

with:

```python
    assert "disconnected · the session keeps running on the box" in document
    assert re.findall(r"\.innerHTML = (\w+)", _SCRIPT) == ["html", "heldParams"]

```

In `tests/test_web.py`, in `test_the_stale_timer_runs_from_the_frames_age_not_from_arrival`, replace:

```python
    assert "last = Date.now()" not in _SCRIPT
    assert "Date.now()" not in _SCRIPT
```

with:

```python
    assert "last = Date.now()" not in _SCRIPT
    timer = re.search(r"function check\(\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)
    assert "Date.now()" not in timer
    # The one `Date.now()` is the mark's `pressed_at`, the browser's clock, sent as
    # such (spec §5.1) and never read against the stream.
    assert _SCRIPT.count("Date.now()") == 1
    assert "pressed_at: Date.now() / 1000" in _SCRIPT
```

Append to `tests/test_web.py`:

```python


# --- P4d-2b b2a: the controls (spec §5.2) -------------------------------------------


def _controls(**frame_overrides) -> str:
    return fragments(frame(**frame_overrides), view())["controls"]


def test_the_controls_offer_pause_mark_and_stop_while_running():
    controls = _controls()

    assert '<button type="button" class="btn" data-cmd="pause">pause (P)</button>' in controls
    assert '<button type="button" class="btn" data-cmd="mark">mark (M)</button>' in controls
    assert '<button type="button" class="btn danger" data-cmd="stop">stop…</button>' in controls
    assert "disabled" not in controls


def test_a_paused_session_offers_resume_and_says_since_when_in_its_pill():
    at = 1_700_000_030.0
    since = time.strftime("%H:%M:%S", time.localtime(at))
    parts = fragments(frame(paused_at=at), view())

    assert 'data-cmd="resume">resume (P)</button>' in parts["controls"]
    assert 'data-cmd="pause"' not in parts["controls"]
    assert parts["state"] == (
        f'<span class="pill warn" data-state="paused">paused · since {since}</span>'
    )


def test_an_ended_session_is_not_shown_paused_and_offers_no_controls():
    parts = fragments(frame(**STATES["returned"], paused_at=1_700_000_030.0), view())

    assert 'data-state="ended"' in parts["state"]
    assert "data-cmd" not in parts["controls"]
    assert "the session has ended" in parts["controls"]


def test_everywhere_but_the_box_the_controls_are_greyed_with_the_sentence():
    """Spec §5.2 and §2: every control is disabled and says why, in the §2 sentence,
    on the page a LAN viewer -- or the box's browser under another name -- is
    served. Refused at `POST /commands` too; this is so nobody is offered a button
    that cannot work."""
    parts = fragments(
        frame(scheduled_stop=ScheduledStop("trials", 48.0, "jake", "after trial 48")),
        view(on_box=False, can_write=False),
    )
    written = parts["controls"] + parts["params"] + parts["strip"]

    buttons = re.findall(r"<button[^>]*data-(?:cmd|dir)[^>]*>", written)
    inputs = re.findall(r"<input[^>]*data-param[^>]*>", written)
    assert buttons and inputs
    assert all(" disabled" in tag for tag in buttons + inputs)
    assert CONTROLS_AT_THE_BOX in parts["controls"]
    assert CONTROLS_AT_THE_BOX == (
        "controls work only at the rig PC until remote sign-in arrives"
    )


def test_a_console_without_the_mark_endpoint_greys_mark_alone():
    controls = fragments(frame(), view(can_mark=False))["controls"]

    assert re.search(r'data-cmd="mark" disabled title="[^"]+"', controls)
    assert NO_MARK_ENDPOINT in html.unescape(controls)
    assert re.search(r'data-cmd="pause">', controls)


def test_each_parameter_card_has_arrows_and_an_input_with_its_step_and_range():
    """Spec §5.2: up/down arrows and an input on each card. The step is the mockup's
    rule by unit (mL 0.01, s 0.05, deg 0.1, else 0.01), and the input shows the value
    at the step's decimals; a categorical card takes a word and has no arrows."""
    params = fragments(
        frame(
            params=(
                ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
                ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
                ParamRow("fix_window", "deg", None, 5.0, 2.0, False),
                ParamRow("target_looks", "", None, None, None, False),
                ParamRow("shape", "", None, None, "penguin", False),
            )
        ),
        view(),
    )["params"]

    assert (
        '<input class="field mono" data-param="fix_hold" data-step="0.05" '
        'data-min="0.1" data-max="1.0" inputmode="decimal" value="0.30" '
        'aria-label="fix_hold">'
    ) in params
    assert 'data-param="reward_correct" data-step="0.01" data-min="0.0" data-max="0.4"' in params
    assert 'data-param="fix_window" data-step="0.1" data-max="5.0" inputmode="decimal" value="2.0"' in params
    assert 'data-param="target_looks" data-step="0.01" inputmode="decimal" value=""' in params
    assert (
        '<input class="field mono" data-param="shape" data-kind="word" value="penguin" '
        'aria-label="shape">'
    ) in params
    assert params.count('data-dir="1"') == 4 and params.count('data-dir="-1"') == 4


def test_a_refusal_shows_on_its_parameters_card_with_its_sentence():
    params = fragments(
        frame(
            refusals=(
                Refused("fix_hold", "jake", "first"),
                Refused("fix_hold", "jake", "'fix_hold' is declared over [0.05, 2.0] s and 9 is outside it"),
            )
        ),
        view(),
    )["params"]

    assert (
        '<span class="rfs">last refused: &#x27;fix_hold&#x27; is declared over '
        "[0.05, 2.0] s and 9 is outside it</span>"
    ) in params
    assert "first" not in params


def test_the_strip_shows_a_scheduled_stop_with_who_set_it_and_a_cancel():
    """Spec §5.2: while a schedule is active the strip shows it -- *stop at 14:30 ·
    set by jake* -- with a cancel button."""
    strip = fragments(
        frame(scheduled_stop=ScheduledStop("clock", 1_700_003_600.0, "jake (box, unverified)", "at 14:30")),
        view(),
    )["strip"]

    assert '<span class="lab">Scheduled</span><span class="val">stop at 14:30</span>' in strip
    assert "set by jake (box, unverified)" in strip
    assert '<button type="button" class="btn small" data-cmd="cancel">cancel</button>' in strip


def test_with_nothing_scheduled_the_strip_keeps_its_four_cells():
    strip = fragments(frame(), view())["strip"]

    assert "Scheduled" not in strip
    assert strip.count('<div class="row">') == 4


def test_a_session_that_ended_another_way_shows_no_schedule_to_cancel():
    strip = fragments(
        frame(
            **STATES["returned"],
            scheduled_stop=ScheduledStop("trials", 48.0, "jake", "after trial 48"),
        ),
        view(),
    )["strip"]

    assert "Scheduled" not in strip and "data-cmd" not in strip


def test_the_feed_lists_control_events_newest_first_with_who_and_counts_the_rest():
    """Spec §5.2: the changes feed lists every setting change, refusal, pause, resume,
    mark (with its note) and schedule, with who did it. Newest first, since it is
    read to see what just happened; what fell off the cap is counted below them."""
    at = 1_700_000_001.0
    clock = time.strftime("%H:%M:%S", time.localtime(at))
    changes = fragments(
        frame(
            controls=(
                Control("mark", "", at, "mark 1 stamped in trial 3, frame 10"),
                Control("note", "jake", at, 'mark 1: "bubble"'),
                Control("set", "sam", at, "fix_hold 0.30 → 0.40, from trial 4"),
            ),
            controls_dropped=5,
        ),
        view(),
    )["rt-changes"]

    set_row = changes.index(f"{clock} · fix_hold 0.30 → 0.40, from trial 4 · sam")
    note_row = changes.index(f"{clock} · mark 1: &quot;bubble&quot; · jake")
    mark_row = changes.index(f"{clock} · mark 1 stamped in trial 3, frame 10</span>")
    dropped = changes.index("5 earlier control event(s) not shown")
    assert set_row < note_row < mark_row < dropped
    assert '<span class="kind">note</span>' in changes


def test_every_control_string_is_escaped():
    """Review Focus 2 for b2a's strings: an actor's typed name, a note, a schedule's
    words, and a parameter's name in the attributes its input carries."""
    evil = frame(
        controls=(Control(EVIL, EVIL, 1_700_000_001.0, EVIL),),
        scheduled_stop=ScheduledStop(EVIL, 1.0, EVIL, EVIL),
        params=(ParamRow(EVIL, EVIL, 0.0, 1.0, 0.5, False), ParamRow("w", "", None, None, EVIL, False)),
        refusals=(Refused(EVIL, EVIL, EVIL),),
    )

    text = "".join(fragments(evil, view()).values())

    assert "<script" not in text
    assert EVIL not in text


def test_the_page_tells_its_script_whether_it_may_write_and_the_debounce():
    """The page is rendered per request, so the box's own page says it may write and
    a LAN viewer's says it may not; the script reads both from `<body>`. The 600 ms
    debounce is the mockup's, housekeeping and not a measurement."""
    box = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)
    lan = page(
        fragments(frame(), view(can_write=False)), stale_after_s=30.0, nonce="n0nce"
    )

    assert DEBOUNCE_MS == 600
    assert '<body data-stale-after="30" data-can-write="1" data-debounce-ms="600">' in box
    assert '<body data-stale-after="30" data-can-write="0" data-debounce-ms="600">' in lan
    for control in ('id="sched-kind"', 'id="sched-value"', 'id="sched-set"', 'id="rename"'):
        assert re.search(control + r"[^>]* disabled", lan), control
        assert not re.search(control + r"[^>]* disabled", box), control


def test_the_page_holds_the_stop_confirm_and_the_mark_note_hidden():
    document = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert re.search(r'<div class="inline crit" id="stop-confirm"[^>]*hidden>', document)
    assert "stop at the next trial boundary?" in document
    assert re.search(r'<div class="inline info" id="mark-form"[^>]*hidden>', document)
    assert 'id="mark-note" maxlength="500"' in document


def test_the_script_debounces_the_arrows_and_keeps_p_and_m_out_of_text_boxes():
    """Spec §5.2: a change is sent once the arrows stop being clicked, and the keys do
    nothing while a text box has focus, or when held (a held key does not repeat)."""
    assert "setTimeout(function () { delete timers[key]; send(input); }, debounceMs)" in _SCRIPT
    assert "clearTimeout(timers[key]);" in _SCRIPT
    assert "if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) { return; }" in _SCRIPT
    assert '/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable' in _SCRIPT


def test_the_script_asks_for_the_name_once_and_keeps_it_where_it_may():
    """Spec §5.2: the box's browser asks once and remembers it locally. Storage can
    be refused -- a private window -- so every read and write is in `try`; a prompt
    refused or cleared sends nothing (Review Focus 6)."""
    assert "try { return window.localStorage.getItem(NAME_KEY) || \"\"; } catch (e) { return \"\"; }" in _SCRIPT
    assert "try { window.localStorage.setItem(NAME_KEY, given); } catch (e) { /* kept for this page only */ }" in _SCRIPT
    assert "if (given === null) { return \"\"; }" in _SCRIPT
    assert '"not sent: give your name first -- every command records who sent it"' in _SCRIPT


def test_the_script_holds_a_parameter_card_it_is_being_typed_into():
    """A frame that re-renders the parameter cards while a person types into one, or
    while an arrow's debounce is pending, would replace the input under them; the
    script holds the newest cards and swaps them in once the person is done."""
    assert 'if (id === "params" && busy()) { heldParams = html; return; }' in _SCRIPT
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider --continue-on-collection-errors tests/test_web.py tests/test_health.py`
Expected: `tests/test_web.py` fails to collect — `ImportError: cannot import name 'CONTROLS_AT_THE_BOX'`; `test_a_paused_session_is_said_to_be_paused_and_is_ok` fails on `running · trial 40 · block session`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/health.py`, in `_state_text`, replace:

```python
    if frame.stop_kind is None:
        return f"running · trial {frame.trial_index} · block {frame.block}"
```

with:

```python
    if frame.stop_kind is None:
        # P4d-2b b2a: a paused session is running and holding -- said, so a trial
        # count standing still does not read as a stalled rig. Not a verdict.
        doing = "running" if frame.paused_at is None else "paused"
        return f"{doing} · trial {frame.trial_index} · block {frame.block}"
```

In `wl_expcontroller/web.py`, replace:

```python
import math
from dataclasses import dataclass
```

with:

```python
import math
import time
from dataclasses import dataclass
```

In `wl_expcontroller/web.py`, in `View`, replace:

```python
    endpoint: str

```

with:

```python
    endpoint: str
    #: Whether this page may write (P4d-2b spec §2, §5.2): the box's own page, a
    #: loopback peer that named loopback in `Host`. Everywhere else every control is
    #: greyed with `CONTROLS_AT_THE_BOX`. `False` unless `wlx serve` says otherwise:
    #: a view that did not say may not write.
    can_write: bool = False
    #: Whether this console has the session's mark endpoint (`wlx serve --link
    #: PUB,REP,MARK`); without it the mark control is greyed with `NO_MARK_ENDPOINT`.
    can_mark: bool = False

```

In `wl_expcontroller/web.py`, replace:

```python
    "banners",
    "rt-trials",
```

with:

```python
    "banners",
    "controls",
    "rt-trials",
```

In `wl_expcontroller/web.py`, replace:

```python
    ("other", "unknown outcome"),
)

```

with:

```python
    ("other", "unknown outcome"),
)

#: What a refused write says, and what every greyed control says (P4d-2b spec §2):
#: until remote sign-in arrives (b2b), writes come from the box alone.
CONTROLS_AT_THE_BOX = "controls work only at the rig PC until remote sign-in arrives"
#: Why the mark control is greyed on a console started without the mark endpoint.
NO_MARK_ENDPOINT = (
    "this console was started without the session's mark endpoint: give wlx serve "
    "--link PUB,REP,MARK, as wlx run was given it"
)
#: How long after the last click on a parameter's arrows the change is sent, in
#: milliseconds: the mockup's debounce (spec §5.2), housekeeping and not a
#: measurement. The page's script reads it from `<body>`.
DEBOUNCE_MS = 600

```

In `wl_expcontroller/web.py`, replace:

```python

def _state(frame: Telemetry | None) -> str:
```

with:

```python

def _clock_time(at: float | None) -> str:
    """A session instant as this host's local clock time, `HH:MM:SS`, as `cli.render`
    prints the last reward: formatting an instant the frame carries, never reading a
    clock. One that is not a number is `—`, never a crash of every pane."""
    if at is None or not math.isfinite(at):
        return "—"
    return time.strftime("%H:%M:%S", time.localtime(at))


def _state(frame: Telemetry | None) -> str:
```

In `wl_expcontroller/web.py`, in `_state`, replace:

```python
def _state(frame: Telemetry | None) -> str:
    """The header's pill, from `phase` and `stop_kind` (spec §4.2)."""
```

with:

```python
def _state(frame: Telemetry | None) -> str:
    """The header's pill, from `phase`, `stop_kind` and -- P4d-2b b2a -- `paused_at`:
    a session that ended while paused shows how it ended, never *paused*."""
```

In `wl_expcontroller/web.py`, in `_state`, replace:

```python
        return '<span class="pill neutral" data-state="none">no session</span>'
    if frame.stop_kind is None:
```

with:

```python
        return '<span class="pill neutral" data-state="none">no session</span>'
    if frame.stop_kind is None and frame.paused_at is not None:
        return (
            f'<span class="pill warn" data-state="paused">paused · since '
            f"{_clock_time(frame.paused_at)}</span>"
        )
    if frame.stop_kind is None:
```

In `wl_expcontroller/web.py`, replace:

```python

def _strip(frame: Telemetry | None, view: View) -> str:
```

with:

```python

def _off(view: View, why: str = CONTROLS_AT_THE_BOX) -> str:
    """The attributes that grey a control this page may not use, saying why; nothing
    for the box's own page."""
    return "" if view.can_write else f' disabled title="{_e(why)}"'


def _scheduled(frame: Telemetry, view: View) -> str:
    """The strip's fifth cell, while a scheduled stop is held (spec §5.2): *stop at
    14:30 · set by jake*, in the rig's own words, with a cancel button."""
    stop = frame.scheduled_stop
    cancel = (
        f'<button type="button" class="btn small" data-cmd="cancel"{_off(view)}>'
        f"cancel</button>"
    )
    return _cell("Scheduled", f"stop {_e(stop.said)}", sub=f"set by {_e(stop.by)} {cancel}")


def _strip(frame: Telemetry | None, view: View) -> str:
```

In `wl_expcontroller/web.py`, in `_strip`, replace:

```python
        + _last_reward(frame, view)
    )
```

with:

```python
        + _last_reward(frame, view)
        # Only while the session runs: one that ended another way keeps its
        # schedule on the frame, and a cancel button for it would offer nothing.
        + (
            _scheduled(frame, view)
            if frame.scheduled_stop is not None and frame.stop_kind is None
            else ""
        )
    )
```

In `wl_expcontroller/web.py`, in `_banners`, replace:

```python
    return "".join(out)

```

with:

```python
    return "".join(out)


# --- the controls (P4d-2b b2a) ------------------------------------------------------


def _controls(frame: Telemetry | None, view: View) -> str:
    """Pause or resume, mark, and stop (spec §5.2), while a session runs.

    **Pause or resume by the session's state**, never a toggle: the page sends what
    the button says, so a double click sends the same command twice, and the rig
    refuses the second with a sentence (`taskd.Session._pause`). **Stop** opens the
    page's confirm step. **Mark** is greyed on its own when this console has no mark
    endpoint. **Everywhere but the box**, every control is greyed with the §2
    sentence, which is also said beside them."""
    if frame is None:
        return '<span class="nm">controls · no session</span>'
    if frame.stop_kind is not None:
        return '<span class="nm">controls · the session has ended</span>'
    off = _off(view)
    mark_off = off or ("" if view.can_mark else f' disabled title="{_e(NO_MARK_ENDPOINT)}"')
    cmd, label = ("resume", "resume (P)") if frame.paused_at is not None else ("pause", "pause (P)")
    note = "" if view.can_write else f'<span class="nm">{CONTROLS_AT_THE_BOX}</span>'
    return (
        f'<button type="button" class="btn" data-cmd="{cmd}"{off}>{label}</button>'
        f'<button type="button" class="btn" data-cmd="mark"{mark_off}>mark (M)</button>'
        f'<button type="button" class="btn danger" data-cmd="stop"{off}>stop…</button>'
        f"{note}"
    )

```

In `wl_expcontroller/web.py`, in `_changes`, replace:

```python
    """Staged and refused changes, the dropped-refusal count before the rows, as
    `cli.render` does."""
```

with:

```python
    """The changes feed (spec §5.2): staged changes first, then the control events --
    applied settings, pauses, resumes, marks and their notes, schedules -- newest
    first with when and who, then the refusals with the dropped-refusal count before
    them, as `cli.render` does."""
```

In `wl_expcontroller/web.py`, in `_changes`, replace:

```python
            f"by {_e(change.by)} ({kind}, applies at the next trial)</span></div>"
        )
```

with:

```python
            f"by {_e(change.by)} ({kind}, applies at the next trial)</span></div>"
        )
    for control in reversed(frame.controls):
        who = f" · {_e(control.by)}" if control.by else ""
        rows.append(
            f'<div class="ev ctl"><span class="kind">{_e(control.kind)}</span><span>'
            f"{_clock_time(control.at)} · {_e(control.said)}{who}</span></div>"
        )
    if frame.controls_dropped:
        rows.append(
            f'<div class="ev ctl"><span class="kind">earlier</span><span>'
            f"{_e(frame.controls_dropped)} earlier control event(s) not shown: only "
            f"the most recent {len(frame.controls)} are kept</span></div>"
        )
```

In `wl_expcontroller/web.py`, in `_changes`, replace:

```python
        )
    return "".join(rows) or '<span class="nm">nothing staged or refused</span>'
```

with:

```python
        )
    return "".join(rows) or '<span class="nm">nothing staged, controlled or refused</span>'
```

In `wl_expcontroller/web.py`, in `_params`, replace:

```python
def _params(frame: Telemetry | None) -> str:
    """One card per `ParamRow`: value, unit, range, the ceiling flag, and a staged
    marker. Read-only: b2 adds the inputs."""
```

with:

```python
#: The arrows' step by unit: the mockup's `stepOf` (`docs/superpowers/mockups/
#: 2026-09-26-console-mockup-v12.html`), in this repository's unit names -- the tasks
#: say `deg` where the mockup said `°`. A display choice, not a rule about values:
#: `Session.set` checks the range whatever step reached it.
_STEPS = {"mL": 0.01, "s": 0.05, "deg": 0.1}


def _step(row) -> float:
    return _STEPS.get(row.unit, 0.01)


def _field(row, view: View) -> str:
    """A card's input and arrows (spec §5.2). A number is shown at its step's
    decimals and carries the step and the declared range for the script's arrows,
    which clamp to it; a categorical value is a word, with no arrows. Greyed away
    from the box."""
    off = _off(view)
    name = _e(row.name)
    if isinstance(row.value, str):
        return (
            f'<span class="spin"><input class="field mono" data-param="{name}" '
            f'data-kind="word" value="{_e(row.value)}" aria-label="{name}"{off}></span>'
        )
    step = _step(row)
    places = len(f"{step:g}".partition(".")[2])
    value = "" if row.value is None else f"{row.value:.{places}f}"
    edges = "".join(
        f' data-{end}="{_e(edge)}"'
        for end, edge in (("min", row.low), ("max", row.high))
        if edge is not None
    )
    return (
        f'<span class="spin"><input class="field mono" data-param="{name}" '
        f'data-step="{step:g}"{edges} inputmode="decimal" value="{value}" '
        f'aria-label="{name}"{off}>'
        f'<span class="arrows"><button type="button" data-dir="1" tabindex="-1" '
        f'aria-label="increase {name}"{off}>▲</button>'
        f'<button type="button" data-dir="-1" tabindex="-1" '
        f'aria-label="decrease {name}"{off}>▼</button></span></span>'
    )


def _params(frame: Telemetry | None, view: View) -> str:
    """One card per `ParamRow`: value, unit, range, the ceiling flag, a staged
    marker, and -- P4d-2b b2a -- the input and arrows that set it and the last
    refusal of it with its sentence (spec §5.2: "A refusal shows on the card and in
    the feed"). *Last* is the word because a refusal carries no time: it stays on
    the card beside whatever the value has since become, and says it is the last."""
```

In `wl_expcontroller/web.py`, in `_params`, replace:

```python
    staged = {change.name: change for change in frame.staged}
    cards = []
```

with:

```python
    staged = {change.name: change for change in frame.staged}
    refused = {refusal.name: refusal for refusal in frame.refusals}
    cards = []
```

In `wl_expcontroller/web.py`, in `_params`, replace:

```python
        )
        cls = "param staged" if change is not None else "param"
```

with:

```python
        )
        refusal = refused.get(row.name)
        said = (
            ""
            if refusal is None
            else f'<span class="rfs">last refused: {_e(refusal.why)}</span>'
        )
        cls = "param staged" if change is not None else "param"
```

In `wl_expcontroller/web.py`, in `_params`, replace:

```python
            f'<span class="unit">{_e(row.unit)}</span></span>'
            f'<span class="range">{_range(row)}</span>{mark}</div>'
```

with:

```python
            f'<span class="unit">{_e(row.unit)}</span></span>'
            f"{_field(row, view)}"
            f'<span class="range">{_range(row)}</span>{mark}{said}</div>'
```

In `wl_expcontroller/web.py`, in `fragments`, replace:

```python
        "banners": _banners(frame, view),
        "rt-trials": _trials(frame),
```

with:

```python
        "banners": _banners(frame, view),
        "controls": _controls(frame, view),
        "rt-trials": _trials(frame),
```

In `wl_expcontroller/web.py`, in `fragments`, replace:

```python
        "rt-changes": _changes(frame),
        "params": _params(frame),
```

with:

```python
        "rt-changes": _changes(frame),
        "params": _params(frame, view),
```

In `wl_expcontroller/web.py`, replace:

```python
.dialog .actions { display: flex; justify-content: flex-end; }
body.stale .strip, body.stale .panels { filter: grayscale(1); opacity: 0.55; }
```

with:

```python
.dialog .actions { display: flex; justify-content: flex-end; }
.controlbar { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; padding: 6px 12px; }
.ctlrow { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
.controlbar .spacer { flex: 1; }
.btn.small { padding: 2px 8px; font-size: 12.5px; }
.btn.danger { border-color: var(--crit); color: var(--crit); }
.btn:disabled, .field:disabled, .arrows button:disabled, select:disabled { opacity: 0.45; cursor: not-allowed; }
.who { font-size: 12.5px; color: var(--muted); }
.who b { color: var(--ink); font-weight: 600; }
.sent { font-size: 12.5px; }
.sent.ok { color: var(--ok); } .sent.crit { color: var(--crit); }
.inline { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; padding: 6px 12px; border-radius: 6px; font-size: 13px; background: var(--surface-2); }
.inline.crit { background: var(--crit-soft); } .inline.info { background: var(--accent-soft); }
.inline input, .inline select { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--rule); border-radius: 3px; padding: 1px 4px; }
#mark-note { width: min(34em, 60vw); }
#sched-value { width: 7em; }
.spin { display: inline-flex; align-items: stretch; }
.field { width: 6em; border: 1px solid var(--rule); border-radius: 3px 0 0 3px; padding: 1px 4px; background: var(--surface); color: inherit; font-size: 12.5px; }
.field[data-kind="word"] { border-radius: 3px; }
.field.pending { border-color: var(--accent); }
.arrows { display: flex; flex-direction: column; border: 1px solid var(--rule); border-left: 0; border-radius: 0 3px 3px 0; overflow: hidden; }
.arrows button { flex: 1; width: 18px; border: 0; padding: 0; background: var(--surface-2); color: var(--muted); cursor: pointer; font-size: 8px; line-height: 1; }
.arrows button + button { border-top: 1px solid var(--rule); }
.param .rfs { font-size: 11.5px; color: var(--crit); }
.ev.ctl .kind { color: var(--accent); }
body.stale .strip, body.stale .panels { filter: grayscale(1); opacity: 0.55; }
```

In `wl_expcontroller/web.py`, replace:

```python
#: **The page's whole script, and all it does** (spec §4.3, §4.4): open the event
#: stream, swap each fragment into the element with its id, run the stale timer while
#: more frames are due, close the stream on the ✕, and reconnect. `EventSource`
#: reconnects on its own after a dropped connection, and `wlx serve` sends a full
#: render first on every new stream, so a reconnect re-renders in full. Everything
#: worth testing is in Python; this is small enough to read.
```

with:

```python
#: **The page's whole script, and all it does** (spec §4.3, §4.4, and since P4d-2b
#: b2a §5.2): open the event stream, swap each fragment into the element with its id,
#: run the stale timer while more frames are due, close the stream on the ✕, and
#: reconnect -- and, from b2a, send the controls as JSON `POST`s to `/commands`,
#: debounce the parameter arrows, handle the **P** and **M** keys, and ask for the
#: operator's name. `EventSource` reconnects on its own after a dropped connection,
#: and `wlx serve` sends a full render first on every new stream, so a reconnect
#: re-renders in full. **It still renders nothing itself**: every `innerHTML` it
#: writes is a fragment `wlx serve` rendered, and what it writes of its own -- the
#: name and the last command's answer -- goes in as `textContent`.
```

In `wl_expcontroller/web.py`, replace:

```python
#: full-color numbers nothing was updating. The next frame's `check()` clears it.
_SCRIPT = """
```

with:

```python
#: full-color numbers nothing was updating. The next frame's `check()` clears it.
#:
#: **The controls (P4d-2b b2a).** Only the box's own page may write (`data-can-write`
#: on `<body>`, from `View.can_write`); elsewhere every control is disabled in the
#: HTML and `post` sends nothing. The name is asked once, kept in `localStorage` --
#: inside `try`, since a private window may refuse it -- and a prompt refused or
#: cleared sends nothing. An arrow steps its input and the change is sent
#: `debounceMs` after the last click; while an input has focus or a change is
#: pending, a new parameters fragment is held and swapped in afterwards, so a frame
#: never replaces an input under a person's hands. P and M do nothing in a text box
#: or when held. A mark sends its signal at once with `pressed_at` -- the browser's
#: clock, and the only `Date.now()` here -- then opens the note box: Enter attaches
#: the note, Esc leaves the mark bare, and a second mark leaves the first bare.
_SCRIPT = """
```

In `wl_expcontroller/web.py`, replace:

```python
  var staleMs = Number(body.getAttribute("data-stale-after")) * 1000;
  var source = null;
```

with:

```python
  var staleMs = Number(body.getAttribute("data-stale-after")) * 1000;
  var canWrite = body.getAttribute("data-can-write") === "1";
  var debounceMs = Number(body.getAttribute("data-debounce-ms"));
  var NAME_KEY = "wlx-console-name";
  var source = null;
```

In `wl_expcontroller/web.py`, replace:

```python
  var closed = false;
  function el(id) { return document.getElementById(id); }
```

with:

```python
  var closed = false;
  var timers = {};
  var heldParams = null;
  var markNo = null;
  function el(id) { return document.getElementById(id); }
```

In `wl_expcontroller/web.py`, replace:

```python
  }
  function onFrame(event) {
```

with:

```python
  }
  function busy() {
    var focused = document.activeElement;
    return Boolean(focused && focused.closest && focused.closest("#params")) ||
      Object.keys(timers).length > 0;
  }
  function swap(id, html) {
    if (id === "params" && busy()) { heldParams = html; return; }
    var node = el(id);
    if (node) { node.innerHTML = html; }
  }
  function release() {
    if (heldParams !== null && !busy()) {
      el("params").innerHTML = heldParams;
      heldParams = null;
    }
  }
  function onFrame(event) {
```

In `wl_expcontroller/web.py`, replace:

```python
    Object.keys(payload.frags).forEach(function (id) {
      var node = el(id);
      if (node) { node.innerHTML = payload.frags[id]; }
    });
```

with:

```python
    Object.keys(payload.frags).forEach(function (id) { swap(id, payload.frags[id]); });
```

In `wl_expcontroller/web.py`, replace:

```python
  }
  setInterval(check, 1000);
```

with:

```python
  }
  function storedName() {
    try { return window.localStorage.getItem(NAME_KEY) || ""; } catch (e) { return ""; }
  }
  var name = storedName();
  function showName() {
    el("who").textContent = name ? name + " (box, unverified)" : "not given yet";
  }
  function askName() {
    var given = window.prompt("Your name, for the session record:", name);
    if (given === null) { return ""; }
    given = given.trim();
    if (!given) { return ""; }
    name = given;
    try { window.localStorage.setItem(NAME_KEY, given); } catch (e) { /* kept for this page only */ }
    showName();
    return given;
  }
  function tell(text, tone) {
    var line = el("sent");
    line.textContent = text;
    line.className = "sent " + (tone || "");
  }
  function post(command, then) {
    if (!canWrite) { return; }
    var by = name || askName();
    if (!by) {
      tell("not sent: give your name first -- every command records who sent it", "crit");
      return;
    }
    command.by = by;
    tell("sending…", "");
    fetch("/commands", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command),
      cache: "no-store"
    }).then(function (response) {
      return response.json();
    }).then(function (answer) {
      tell(answer.said, answer.status === "sent" || answer.status === "signaled" ? "ok" : "crit");
      if (then) { then(answer); }
    }).catch(function () {
      tell("not delivered: this page could not reach wlx serve", "crit");
    });
  }
  function decimals(step) { return (String(step).split(".")[1] || "").length; }
  function send(input) {
    input.classList.remove("pending");
    var key = input.getAttribute("data-param");
    var raw = input.value.trim();
    var word = input.getAttribute("data-kind") === "word";
    var value = word ? raw : Number(raw);
    if (!word && (raw === "" || !isFinite(value))) {
      tell("not sent: " + key + " needs a number", "crit");
    } else {
      post({ kind: "set", name: key, value: value });
    }
    release();
  }
  function schedule(input) {
    var key = input.getAttribute("data-param");
    clearTimeout(timers[key]);
    input.classList.add("pending");
    timers[key] = setTimeout(function () { delete timers[key]; send(input); }, debounceMs);
  }
  function stepInput(input, dir) {
    var step = Number(input.getAttribute("data-step")) || 0.01;
    var lo = input.hasAttribute("data-min") ? Number(input.getAttribute("data-min")) : -Infinity;
    var hi = input.hasAttribute("data-max") ? Number(input.getAttribute("data-max")) : Infinity;
    var v = Number(input.value);
    if (input.value.trim() === "" || !isFinite(v)) { v = isFinite(lo) ? lo : 0; }
    v = Math.min(hi, Math.max(lo, Math.round((v + dir * step) / step) * step));
    input.value = v.toFixed(decimals(step));
    schedule(input);
  }
  function closeNote(note) {
    if (markNo === null) { return; }
    var number = markNo;
    markNo = null;
    el("mark-form").hidden = true;
    post({ kind: "note", mark: number, note: note });
  }
  function mark() {
    var button = el("controls").querySelector('[data-cmd="mark"]');
    if (!button || button.disabled) { return; }
    closeNote("");
    post({ kind: "mark", pressed_at: Date.now() / 1000 }, function (answer) {
      if (answer.status !== "signaled") { return; }
      markNo = answer.mark;
      el("mark-note").value = "";
      el("mark-form").hidden = false;
      el("mark-note").focus();
    });
  }
  function command(cmd) {
    if (cmd === "stop") { el("stop-confirm").hidden = false; }
    else if (cmd === "mark") { mark(); }
    else { post({ kind: cmd }); }
  }
  function pauseOrResume() {
    var button = el("controls").querySelector('[data-cmd="pause"], [data-cmd="resume"]');
    if (button && !button.disabled) { command(button.getAttribute("data-cmd")); }
  }
  document.addEventListener("click", function (e) {
    if (!e.target.closest) { return; }
    var button = e.target.closest("[data-cmd]");
    if (button && !button.disabled) { command(button.getAttribute("data-cmd")); return; }
    var arrow = e.target.closest("[data-dir]");
    if (arrow && !arrow.disabled) {
      var input = arrow.closest(".spin").querySelector("input[data-param]");
      if (input && !input.disabled) { stepInput(input, Number(arrow.getAttribute("data-dir"))); }
    }
  });
  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches("input[data-param]")) { schedule(e.target); }
  });
  document.addEventListener("focusout", function () { setTimeout(release, 0); });
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) { return; }
    var t = e.target;
    if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) { return; }
    var k = e.key.toLowerCase();
    if (k === "p") { e.preventDefault(); pauseOrResume(); }
    else if (k === "m") { e.preventDefault(); mark(); }
  });
  el("mark-note").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); closeNote(el("mark-note").value.trim()); }
    else if (e.key === "Escape") { e.preventDefault(); closeNote(""); }
  });
  el("stop-yes").addEventListener("click", function () {
    el("stop-confirm").hidden = true;
    post({ kind: "stop" });
  });
  el("stop-no").addEventListener("click", function () { el("stop-confirm").hidden = true; });
  el("rename").addEventListener("click", function () { askName(); });
  el("sched-set").addEventListener("click", function () {
    var kind = el("sched-kind").value;
    var raw = el("sched-value").value.trim();
    var request = { kind: "schedule" };
    if (kind === "clock") { request.at = raw; }
    else if (kind === "trials") { request.trials = Number(raw); }
    else { request.ml = Number(raw); }
    post(request);
  });
  setInterval(check, 1000);
```

In `wl_expcontroller/web.py`, replace:

```python
  });
  open();
```

with:

```python
  });
  showName();
  open();
```

In `wl_expcontroller/web.py`, replace:

```python

def page(parts: dict[str, str], *, stale_after_s: float, nonce: str) -> str:
```

with:

```python

def page(
    parts: dict[str, str], *, stale_after_s: float, nonce: str, can_write: bool = False
) -> str:
```

In `wl_expcontroller/web.py`, in `page`, replace:

```python
    **Nothing here writes** (spec §4.2): two buttons -- close this page's stream, and
    reconnect it -- and four radio inputs that choose a tab.
```

with:

```python
    **The controls (P4d-2b b2a, spec §5.2)**: the control bar's buttons are the
    `controls` fragment, and around it are the parts no frame changes -- the name,
    the last command's answer, the stop confirm, the mark's note box and the
    scheduled-stop form -- static, so a frame never replaces what a person is typing.
    `can_write` is `View.can_write` for the browser this page is for: `False`
    disables those static controls here and tells the script (`data-can-write`); the
    fragments grey their own. Close and reconnect, and the tab radios, are b1's.
```

In `wl_expcontroller/web.py`, in `page`, replace:

```python
    p = {key: parts[key] for key in FRAGMENT_IDS}
    return f"""<!doctype html>
```

with:

```python
    p = {key: parts[key] for key in FRAGMENT_IDS}
    off = "" if can_write else f' disabled title="{_e(CONTROLS_AT_THE_BOX)}"'
    return f"""<!doctype html>
```

In `wl_expcontroller/web.py`, in `page`, replace:

```python
</head>
<body data-stale-after="{stale_after_s:g}">
```

with:

```python
</head>
<body data-stale-after="{stale_after_s:g}" data-can-write="{int(can_write)}" data-debounce-ms="{DEBOUNCE_MS}">
```

In `wl_expcontroller/web.py`, in `page`, replace:

```python
  <div class="banners" id="banners">{p['banners']}</div>
  <div class="shell">
```

with:

```python
  <div class="banners" id="banners">{p['banners']}</div>
  <section class="controlbar glass" aria-label="controls">
    <div class="ctlrow" id="controls">{p['controls']}</div>
    <span class="spacer"></span>
    <span class="who">name <b id="who">not given yet</b> <button class="btn small" id="rename" type="button"{off}>change</button></span>
    <span class="sent" id="sent" role="status"></span>
  </section>
  <div class="inline crit" id="stop-confirm" role="alertdialog" aria-label="confirm stop" hidden><span>stop at the next trial boundary?</span><button class="btn danger" id="stop-yes" type="button">stop</button><button class="btn" id="stop-no" type="button">cancel</button></div>
  <div class="inline info" id="mark-form" role="dialog" aria-label="mark note" hidden><span>mark sent · note</span><input id="mark-note" maxlength="500" autocomplete="off" placeholder="Enter attaches it · Esc leaves the mark bare" aria-label="mark note"></div>
  <div class="inline" id="sched-form"><span>scheduled stop</span><select id="sched-kind" aria-label="stop when"{off}><option value="clock">at HH:MM</option><option value="trials">after N more trials</option><option value="fluid">after mL this session</option></select><input id="sched-value" autocomplete="off" aria-label="stop at"{off}><button class="btn small" id="sched-set" type="button"{off}>set</button></div>
  <div class="shell">
```

In `wl_expcontroller/web.py`, in `page`, replace:

```python
        </div>
        <div class="tabpanel" id="tp-task"><section class="panel glass"><div class="top"><h2>Task parameters</h2><span class="sub">read-only</span></div><div class="params" id="params">{p['params']}</div></section></div>
```

with:

```python
        </div>
        <div class="tabpanel" id="tp-task"><section class="panel glass"><div class="top"><h2>Task parameters</h2><span class="sub">staged until the next trial</span></div><div class="params" id="params">{p['params']}</div></section></div>
```

- [ ] **Step 4: Run the tests, then the suite, then check the script parses**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_web.py tests/test_health.py tests/test_serve.py`
Expected: all pass. `wlx serve` builds its `View`s without the two new fields until Task 11, so every page it serves is greyed for now — the safe default.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1271 passed**.
Python cannot run the script, so check at least that it parses, if Node is on the machine:
Run: `python -c "from wl_expcontroller.web import _SCRIPT; open('/tmp/b2a-page.js', 'w').write(_SCRIPT)" && node --check /tmp/b2a-page.js`
Expected: no output, exit 0. (Task 16 Step 4 runs it in a browser.)

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/web.py wl_expcontroller/health.py tests/test_web.py tests/test_health.py tests/_frames.py
git commit -m "Put the controls on the page: settings, pause, mark, stop and a scheduled stop, greyed away from the box"
```

---

### Task 11: `wlx serve` takes writes from the box

**Why:** spec §2 and §5.3. `POST /commands` takes one JSON command, accepted only under §2's four checks and validated before anything is queued; a command thread alone owns the REQ socket and takes commands from a bounded queue; the page is told *sent* only when `taskd` acknowledged it, *not delivered* when the exchange times out (and the socket resets), *busy* when the queue is full; the mark's signal goes on its own path ahead of the queue; and every request's `Host` must name this console, `--allow-host` adding names (Plan decisions 3, 10, 11). `--link` takes the mark endpoint (Plan decision 2).

**The `Outbox` tests call `submit` through `_submitted`**, on a thread of their own with a 10 s join. `submit` waits for as long as the outbox's thread lives, so a job that thread never answers — the defect those tests exist to catch — would otherwise hang the test instead of failing it: in the plan's pre-flight, `Outbox._answer` neutered ran the mutation harness out to its 300 s and printed `caught … timed out`, which no test noticed. With `_submitted`, the same mutant is `20 failed`.

**Files:**
- Modify: `wl_expcontroller/serve.py` (the module docstring; imports; `Hub`'s `marks` and `snapshot`'s `can_write`; `_ROUTES`, `_MISDIRECTED`; `LOOPBACK_NAMES`, `host_name`, `names_loopback`, `box_names`; `BODY_LIMIT`, `NAME_LIMIT`, `MARK_ID_LIMIT`, `MARKS_REMEMBERED`, `COMMAND_QUEUE_DEPTH`, `MARK_QUEUE_DEPTH`, `OUTBOX_POLL_S`, `SENT`, `BUSY`; `BadCommand`, `MarkSignal`, `MarkNote`, `_SHAPES`, `_person`, `parse_command`, `not_delivered`, `_Job`, `Outbox`, `_delivered`; `make_handler`; `Server`; `parse_link`; `run`)
- Modify: `wl_expcontroller/cli.py` (`serve`'s `--link` and `--allow-host`)
- Test: `tests/test_serve.py`

**Interfaces:**
- Consumes: Task 2's commands and `check_schedule`; Task 1's `_setting`, `CommandRefused`; Task 3's `ZmqMarks`, `NotDelivered`; Task 4's `ZmqCommands`, `REPLY_TIMEOUT_S`, `CONNECT_TIMEOUT_S`, read-only `ZmqConsole`; Task 10's `View.can_write`, `View.can_mark`, `CONTROLS_AT_THE_BOX`, `NO_MARK_ENDPOINT`, `page(..., can_write=...)`.
- Produces:
  - `serve.host_name(header: str | None) -> str | None`, `serve.names_loopback(name) -> bool`, `serve.box_names(allowed: tuple[str, ...] = ()) -> frozenset[str]`, `serve.LOOPBACK_NAMES`.
  - `serve.parse_command(data) -> Command | MarkSignal | MarkNote` (raises `BadCommand`); `MarkSignal(by, pressed_at)`, `MarkNote(mark, note, by)`.
  - `serve.Outbox(name, build, depth, stop)`, `.start()`, `.submit(work) -> tuple[int, dict]`, `.thread`; `serve.not_delivered(why) -> tuple[int, dict]`; `serve.BUSY`.
  - `serve.make_handler(hub, *, token, stale_after_s, keepalive_s=KEEPALIVE_S, hosts=LOOPBACK_NAMES, dispatch=None)`.
  - `serve.Server(..., mark: str | None = None, allow_hosts: tuple[str, ...] = (), reply_timeout_s=..., connect_timeout_s=...)`, `.dispatch(request) -> tuple[int, dict]`, `._commands`, `._marks`.
  - `serve.parse_link(text) -> tuple[str, str, str | None]`; `wlx serve --link PUB,REP[,MARK] --allow-host NAME`.
  - Test helpers: `_outbox` and `_submitted`, for this task's `Outbox` tests; and for Task 12, `_post`, `_rig`, `_drained_any`, `_Dispatch`, `LOOPBACK_NAMES` from `serve`.

- [ ] **Step 1: Write the failing tests, and move b1's to the new surfaces**

b1's tests change where b2a changes what they pin: `POST /commands` is a route now (`test_a_known_path_with_the_wrong_method_is_405`), a raw request carries a `Host` (`test_a_non_ascii_authorization_header_gets_the_same_401`), `--link` takes two or three endpoints, `_served` passes the handler's two new parameters, and `_teardown_without_close` joins the two new threads.

In `tests/test_serve.py`, replace:

```python
from wl_expcontroller.link import SCHEMA, Stop, ZmqConsole, ZmqLink
from wl_expcontroller.serve import CLOSED, QUEUE_DEPTH, Hub, Server, make_handler, on_box
```

with:

```python
from wl_expcontroller.link import (
    SCHEMA,
    CancelScheduledStop,
    Mark,
    Pause,
    Resume,
    ScheduleStop,
    SetParameter,
    Stop,
    ZmqConsole,
    ZmqLink,
)
from wl_expcontroller.serve import (
    BUSY,
    CLOSED,
    COMMAND_QUEUE_DEPTH,
    LOOPBACK_NAMES,
    MARK_ID_LIMIT,
    MARKS_REMEMBERED,
    QUEUE_DEPTH,
    BadCommand,
    Hub,
    MarkNote,
    MarkSignal,
    Outbox,
    Server,
    box_names,
    host_name,
    make_handler,
    names_loopback,
    on_box,
    parse_command,
)
from wl_expcontroller.web import CONTROLS_AT_THE_BOX, NO_MARK_ENDPOINT
```

In `tests/test_serve.py`, in `_teardown_without_close`, replace:

```python
        server._telemetry.join(timeout=5)

```

with:

```python
        server._telemetry.join(timeout=5)
    # P4d-2b b2a: the command and mark threads stop on `_stop` as well; joined here so
    # their sockets are closed on their own threads before `_every_zmq_context_released`
    # destroys the contexts.
    for outbox in (server._commands, server._marks):
        if outbox is not None and outbox.thread.ident is not None:
            outbox.thread.join(timeout=5)

```

In `tests/test_serve.py`, in `_served`, replace:

```python
@contextmanager
def _served(hub: Hub, *, keepalive_s: float = 15.0, stale_after_s: float = 30.0):
```

with:

```python
@contextmanager
def _served(
    hub: Hub,
    *,
    keepalive_s: float = 15.0,
    stale_after_s: float = 30.0,
    hosts: frozenset = LOOPBACK_NAMES,
    dispatch=None,
):
```

In `tests/test_serve.py`, in `_served`, replace:

```python
        make_handler(
            hub, token=TOKEN, stale_after_s=stale_after_s, keepalive_s=keepalive_s
```

with:

```python
        make_handler(
            hub,
            token=TOKEN,
            stale_after_s=stale_after_s,
            keepalive_s=keepalive_s,
            hosts=hosts,
            dispatch=dispatch,
```

In `tests/test_serve.py`, in `_served`, replace:

```python
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
```

with:

```python
    )
    # A short poll, so `shutdown()` returns in a twentieth of a second rather than
    # the stdlib's default half: dozens of tests here each serve and shut down once,
    # and the mutation sweep runs them once per function. Housekeeping.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
```

In `tests/test_serve.py`, replace:

```python

def test_a_known_path_with_the_wrong_method_is_405_and_b1_takes_no_post():
```

with:

```python

def test_a_known_path_with_the_wrong_method_is_405():
    """`/commands` is a path since b2a and takes `POST` alone; every other path takes
    no `POST` at all."""
```

In `tests/test_serve.py`, in `test_a_known_path_with_the_wrong_method_is_405`, replace:

```python
        assert _request(port, "DELETE", "/")[0] == 405
        assert _request(port, "POST", "/commands")[0] == 404
```

with:

```python
        assert _request(port, "DELETE", "/")[0] == 405
        assert _request(port, "GET", "/commands")[0] == 405
        assert _request(port, "OPTIONS", "/commands")[0] == 405
        assert _request(port, "POST", "/nope")[0] == 404
```

In `tests/test_serve.py`, in `test_a_non_ascii_authorization_header_gets_the_same_401`, replace:

```python
        answer = _raw(
            port, b"GET /health HTTP/1.0\r\nAuthorization: Bearer t\xe9ken\r\n\r\n"
```

with:

```python
        answer = _raw(
            port,
            b"GET /health HTTP/1.0\r\nHost: 127.0.0.1\r\n"
            b"Authorization: Bearer t\xe9ken\r\n\r\n",
```

In `tests/test_serve.py`, in `test_wlx_serve_refuses_a_link_that_is_not_two_endpoints`, replace:

```python
    "link",
    ["tcp://127.0.0.1:5571", "a,b,c", ",tcp://127.0.0.1:5572"],
```

with:

```python
    "link",
    [
        "tcp://127.0.0.1:5571",
        "tcp://127.0.0.1:1,tcp://127.0.0.1:2,tcp://127.0.0.1:3,tcp://127.0.0.1:4",
        ",tcp://127.0.0.1:5572",
    ],
```

In `tests/test_serve.py`, in `test_wlx_serve_refuses_a_link_that_is_not_two_endpoints`, replace:

```python
def test_wlx_serve_refuses_a_link_that_is_not_two_endpoints(tmp_path, link):
    with pytest.raises(SystemExit, match="exactly two"):
```

with:

```python
def test_wlx_serve_refuses_a_link_that_is_not_two_or_three_endpoints(tmp_path, link):
    with pytest.raises(SystemExit, match="two or three"):
```

In `tests/test_serve.py`, in `test_parse_link_strips_whitespace_around_each_endpoint`, replace:

```python
    second endpoint, still `"://"`-shaped, so it passed straight through and only
    ZeroMQ noticed, inside the telemetry thread, with no `try` around it (I1(b))."""
```

with:

```python
    second endpoint, still `"://"`-shaped, so it passed straight through and only
    ZeroMQ noticed, inside the telemetry thread, with no `try` around it (I1(b)).
    Two endpoints give no mark endpoint (P4d-2b b2a); a third is it."""
```

In `tests/test_serve.py`, in `test_parse_link_strips_whitespace_around_each_endpoint`, replace:

```python
        "tcp://127.0.0.1:5572",
    )
```

with:

```python
        "tcp://127.0.0.1:5572",
        None,
    )
    assert serve.parse_link("tcp://127.0.0.1:1, tcp://127.0.0.1:2 ,tcp://127.0.0.1:3") == (
        "tcp://127.0.0.1:1",
        "tcp://127.0.0.1:2",
        "tcp://127.0.0.1:3",
    )
```

In `tests/test_serve.py`, in `test_wlx_serve_refuses_a_link_endpoint_zmq_would_choke_on`, replace:

```python
        ("5571,5572", "tcp://HOST:PORT"),
    ],
```

with:

```python
        ("5571,5572", "tcp://HOST:PORT"),
        # Three parts, which is a count `--link` takes since P4d-2b b2a, none of
        # them an endpoint (this was "not two endpoints" in b1).
        ("a,b,c", "tcp://HOST:PORT"),
    ],
```

Append to `tests/test_serve.py`:

```python


# --- P4d-2b b2a: every request's Host (spec §2, §5.3) --------------------------------


@pytest.mark.parametrize(
    ("header", "name"),
    [
        ("127.0.0.1:8080", "127.0.0.1"),
        ("LocalHost:8080", "localhost"),
        ("localhost", "localhost"),
        ("[::1]:8080", "::1"),
        ("[::1]", "::1"),
        ("Rig3.Lab.example:80", "rig3.lab.example"),
        (None, None),
        ("", None),
        ("::1", None),
        ("127.0.0.1:80x", None),
        ("[::1:8080", None),
        ("[]:80", None),
        ("h\xe9te:80", None),
    ],
)
def test_host_name_is_the_name_a_host_header_gives(header, name):
    assert host_name(header) == name


def test_names_loopback_is_localhost_and_the_loopback_addresses_alone():
    assert all(names_loopback(n) for n in ("localhost", "127.0.0.1", "127.8.9.10", "::1"))
    assert not any(names_loopback(n) for n in (None, "mac.lab", "192.168.1.92", "localhost.evil"))


def test_box_names_are_loopback_this_boxs_own_names_and_addresses_and_the_allowed(
    monkeypatch,
):
    """The defaults (spec §5.3): loopback and the box's own host names and addresses;
    `--allow-host` adds names. Read from the host's resolver, which a test pins."""
    monkeypatch.setattr(serve.socket, "gethostname", lambda: "Rig3")
    monkeypatch.setattr(serve.socket, "getfqdn", lambda: "rig3.lab.example")
    found = {
        "rig3": [(2, 1, 6, "", ("192.168.1.92", 0))],
        "rig3.lab.example": [(30, 1, 6, "", ("fe80::1%en0", 0, 0, 1))],
    }

    def getaddrinfo(name, port):
        if name not in found:
            raise OSError("no such name")
        return found[name]

    monkeypatch.setattr(serve.socket, "getaddrinfo", getaddrinfo)

    assert box_names(("Other.Name ", "")) == frozenset(
        {
            "localhost", "127.0.0.1", "::1",
            "rig3", "rig3.lab.example", "192.168.1.92", "fe80::1",
            "other.name",
        }
    )


def test_a_lookup_that_fails_leaves_loopback_and_the_allowed(monkeypatch):
    monkeypatch.setattr(serve.socket, "gethostname", lambda: "")
    monkeypatch.setattr(serve.socket, "getfqdn", lambda: "")

    assert box_names(("rig3",)) == LOOPBACK_NAMES | {"rig3"}


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/"), ("GET", "/events"), ("GET", "/health"), ("GET", "/nope"),
     ("POST", "/commands"), ("PUT", "/")],
)
def test_a_request_whose_host_names_another_console_gets_a_json_421(method, path):
    """Spec §2 and §5.3: every request is answered only when its `Host` names this
    console. A DNS-rebinding page's request carries its own name, and gets a JSON
    421 and no page -- not even the token check."""
    hub = _hub()
    with _served(hub) as port:
        status, headers, body = _request(
            port, method, path, {"Host": "evil.example", "Authorization": f"Bearer {TOKEN}"}
        )

    assert status == 421
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body)["error"] == "misdirected request"
    assert b"<" not in body and b"evil" not in body


def test_a_request_with_no_host_at_all_is_misdirected():
    hub = _hub()
    with _served(hub) as port:
        answer = _raw(port, b"GET / HTTP/1.0\r\n\r\n")

    assert answer.startswith(b"HTTP/1.0 421")


def test_a_name_given_with_allow_host_is_answered():
    hub = _hub()
    with _served(hub, hosts=LOOPBACK_NAMES | {"rig3.lab"}) as port:
        status = _request(port, "GET", "/", {"Host": f"rig3.lab:{port}"})[0]

    assert status == 200


# --- P4d-2b b2a: POST /commands, from the box (spec §2, §5.3) --------------------------


class _Dispatch:
    """What `Server.dispatch` would be, recording each request it is handed."""

    def __init__(self, answer=(200, {"status": "sent", "said": "sent: test"})):
        self.seen: list = []
        self.answer = answer

    def __call__(self, request):
        self.seen.append(request)
        return self.answer


def _post(port: int, body, headers: dict | None = None):
    """`POST /commands` the way the box's own page sends it, unless `headers` says
    otherwise: loopback `Host`, this page's `Origin`, and JSON."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    sent = {
        "Host": f"127.0.0.1:{port}",
        "Origin": f"http://127.0.0.1:{port}",
        "Content-Type": "application/json",
    }
    sent.update(headers or {})
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.putrequest("POST", "/commands", skip_host=True)
        for name, value in sent.items():
            if value is not None:
                connection.putheader(name, value)
        connection.putheader("Content-Length", str(len(raw)))
        connection.endheaders(raw)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_a_command_from_the_boxs_own_page_is_dispatched_as_the_person_named():
    """Spec §2's four checks all hold, the body is a command, and it is dispatched
    with the actor recorded as `NAME (box, unverified)` -- S9a §6: a forgeable name
    says it is unverified. The dispatch's answer is the page's."""
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(port, {"kind": "pause", "by": " jake "})

    assert (status, answer) == (200, {"status": "sent", "said": "sent: test"})
    assert dispatch.seen == [Pause(by="jake (box, unverified)")]


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": None},
        {"Origin": "http://evil.example"},
        {"Origin": "http://127.0.0.1:1"},
        {"Content-Type": "text/plain"},
        {"Content-Type": None},
        {"Host": "rig3.lab"},
    ],
    ids=["no-origin", "cross-site", "other-port", "text-plain", "no-type", "lan-name"],
)
def test_a_write_that_fails_one_of_the_four_checks_is_refused_with_the_sentence(headers):
    """Spec §2: a write from the box is accepted only when all four hold. A LAN name
    in `Host` -- one this console answers reads on -- is still not loopback, so the
    box's browser under that name cannot write. Each is refused with the §2
    sentence, and nothing is dispatched."""
    dispatch = _Dispatch()
    with _served(_hub(), hosts=LOOPBACK_NAMES | {"rig3.lab"}, dispatch=dispatch) as port:
        status, answer = _post(port, {"kind": "stop", "by": "jake"}, headers)

    assert status == 403
    assert answer == {"status": "refused", "said": CONTROLS_AT_THE_BOX}
    assert dispatch.seen == []


def test_a_write_from_a_peer_that_is_not_the_box_is_refused(monkeypatch):
    """The first check: a loopback peer. Every test socket is loopback, so the peer
    the handler reads is made a LAN one."""
    monkeypatch.setattr(serve, "on_box", lambda host: False)
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(port, {"kind": "stop", "by": "jake"})

    assert (status, answer["said"]) == (403, CONTROLS_AT_THE_BOX)
    assert dispatch.seen == []


@pytest.mark.parametrize(
    ("body", "said"),
    [
        (b"not json", "a command is one JSON object"),
        (b"[1]", "a command is one JSON object"),
        (b"\xff", "a command is one JSON object"),
        ({"kind": "reboot", "by": "jake"}, "'reboot' is not a command"),
        ({"kind": "pause"}, "every command records who sent it"),
        ({"kind": "pause", "by": "   "}, "every command records who sent it"),
        ({"kind": "pause", "by": "j" * 65}, "every command records who sent it"),
        ({"kind": "pause", "by": "ja\nke"}, "every command records who sent it"),
        ({"kind": "pause", "by": "jake", "why": "x"}, "a pause command takes no why"),
        ({"kind": "set", "by": "jake", "name": "fix_hold", "value": True}, "neither"),
        ({"kind": "set", "by": "jake", "value": 0.4}, "names its parameter"),
        ({"kind": "schedule", "by": "jake", "at": "25:00"}, "HH:MM"),
        ({"kind": "schedule", "by": "jake", "at": "14:30", "trials": 3}, "exactly one"),
        ({"kind": "schedule", "by": "jake"}, "exactly one"),
        ({"kind": "mark", "by": "jake", "pressed_at": "now"}, "pressed_at"),
        ({"kind": "note", "by": "jake", "mark": MARK_ID_LIMIT + 1, "note": ""}, "names the mark"),
        ({"kind": "note", "by": "jake", "mark": 3, "note": "x" * 501}, "at most 500"),
    ],
)
def test_a_body_that_is_not_a_command_is_refused_before_anything_is_queued(body, said):
    """Spec §5.3: the body is validated before anything is queued, with a sentence
    the page shows; a person with no name is told to give one (Review Focus 6)."""
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        status, answer = _post(port, body)

    assert status == 400
    assert answer["status"] == "refused"
    assert answer["said"].startswith("not sent: ")
    assert said in answer["said"]
    assert dispatch.seen == []


def test_a_body_longer_than_the_limit_or_without_a_length_is_refused_unread():
    dispatch = _Dispatch()
    with _served(_hub(), dispatch=dispatch) as port:
        too_long = _post(port, {"kind": "pause", "by": "j" * 5000})
        answer = _raw(
            port,
            (
                f"POST /commands HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n"
                f"Origin: http://127.0.0.1:{port}\r\n"
                f"Content-Type: application/json\r\n\r\n"
            ).encode("ascii"),
        )

    assert too_long == (413, {"status": "refused", "said": "a command is at most 4096 bytes"})
    assert answer.startswith(b"HTTP/1.0 400")
    assert b"Content-Length" in answer
    assert dispatch.seen == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"kind": "set", "by": "jake", "name": "fix_hold", "value": 1},
         SetParameter(name="fix_hold", value=1.0, by="jake (box, unverified)")),
        ({"kind": "set", "by": "jake", "name": "shape", "value": "penguin"},
         SetParameter(name="shape", value="penguin", by="jake (box, unverified)")),
        ({"kind": "stop", "by": "jake"}, Stop(by="jake (box, unverified)")),
        ({"kind": "resume", "by": "jake"}, Resume(by="jake (box, unverified)")),
        ({"kind": "cancel", "by": "jake"}, CancelScheduledStop(by="jake (box, unverified)")),
        ({"kind": "schedule", "by": "jake", "at": "14:30"},
         ScheduleStop(kind="clock", value="14:30", by="jake (box, unverified)")),
        ({"kind": "schedule", "by": "jake", "trials": 12},
         ScheduleStop(kind="trials", value=12, by="jake (box, unverified)")),
        ({"kind": "schedule", "by": "jake", "ml": 5},
         ScheduleStop(kind="fluid", value=5, by="jake (box, unverified)")),
        ({"kind": "mark", "by": "jake", "pressed_at": 1_700_000_000},
         MarkSignal(by="jake (box, unverified)", pressed_at=1_700_000_000.0)),
        ({"kind": "mark", "by": "jake"}, MarkSignal(by="jake (box, unverified)", pressed_at=None)),
        ({"kind": "note", "by": "jake", "mark": 7, "note": "bubble"},
         MarkNote(mark=7, note="bubble", by="jake (box, unverified)")),
    ],
)
def test_each_command_the_page_sends_parses_to_what_the_rig_is_sent(body, expected):
    assert parse_command(body) == expected


def test_a_parse_refusal_is_a_bad_command():
    with pytest.raises(BadCommand):
        parse_command({"kind": "pause", "by": ""})


def test_the_boxs_page_may_write_and_the_same_box_under_a_lan_name_may_not():
    """`View.can_write` is spec §2's first two checks, per request: the page greys
    its controls where a write would be refused anyway."""
    hub = _hub()
    with _served(hub, hosts=LOOPBACK_NAMES | {"rig3.lab"}) as port:
        box = _request(port, "GET", "/")[2].decode("utf-8")
        lan = _request(port, "GET", "/", {"Host": f"rig3.lab:{port}"})[2].decode("utf-8")

    assert 'data-can-write="1"' in box
    assert 'data-can-write="0"' in lan


def test_a_stream_on_the_boxs_page_renders_controls_that_work():
    hub = Hub(steady=_Clock(0.0), endpoint=ENDPOINT, marks=True)
    hub.offer(frame())
    with _served(hub) as port, _stream(port) as response:
        first = next(_events(response))

    assert 'data-cmd="pause"' in first["frags"]["controls"]
    assert "disabled" not in first["frags"]["controls"]


# --- P4d-2b b2a: the outboxes, where each ZMQ socket has its one thread ---------------


class _Sender:
    """A sender that answers its work, and a way to hold it mid-work."""

    def __init__(self) -> None:
        self.thread = None
        self.release = threading.Event()
        self.release.set()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _outbox(build, depth: int = 2) -> tuple[Outbox, threading.Event]:
    stop = threading.Event()
    outbox = Outbox("test-outbox", build, depth, stop)
    outbox.start()
    return outbox, stop


def _submitted(outbox: Outbox, work, seconds: float = 10.0) -> tuple[int, dict]:
    """`outbox.submit(work)` on a thread of its own, and its answer within `seconds`;
    fails the test otherwise. `submit` waits for as long as the outbox's thread
    lives, so a job that thread never answers -- the defect these tests exist to
    catch -- would hang the test on its own thread rather than fail it: with
    `Outbox._answer` neutered, the mutation harness ran out its 300 s and printed
    `timed out`, which no test noticed (`docs/next-session.md`: the fix is a bound)."""
    answers: list = []
    thread = threading.Thread(
        target=lambda: answers.append(outbox.submit(work)), daemon=True
    )
    thread.start()
    thread.join(timeout=seconds)
    assert answers, f"the outbox did not answer within {seconds} s"
    return answers[0]


def test_an_outbox_builds_its_sender_on_its_own_thread_and_answers_each_job():
    sender = _Sender()

    def build():
        sender.thread = threading.current_thread().name
        return sender

    outbox, stop = _outbox(build)
    try:
        answer = _submitted(
            outbox, lambda built: (200, {"status": "sent", "said": built.thread})
        )
    finally:
        stop.set()
        outbox.thread.join(timeout=5)

    assert answer == (200, {"status": "sent", "said": "test-outbox"})
    assert sender.closed, "the sender is closed on its thread when the outbox stops"


def test_a_full_outbox_answers_busy_at_once_and_every_queued_job_is_answered():
    """Review Focus 1: a flood -- a double click, a held key, a stuck page -- fills
    the queue, and what does not fit is answered *busy* at once, never queued without
    bound and never left hanging."""
    sender = _Sender()
    sender.release.clear()
    outbox, stop = _outbox(lambda: sender, depth=2)
    in_hand = threading.Event()

    def held(built):
        in_hand.set()
        built.release.wait(10)
        return 200, {"status": "sent", "said": "held"}

    answers: list = []

    def submit() -> None:
        answers.append(outbox.submit(held))

    threads = [threading.Thread(target=submit, daemon=True) for _ in range(3)]
    try:
        # One job in the thread's hands first, then two to fill the queue behind it.
        # Started together, the third could find the queue full before the thread had
        # taken the first, and be the one told *busy* (seen once, on a loaded machine).
        threads[0].start()
        assert in_hand.wait(5.0), "the outbox thread never took the first job"
        threads[1].start()
        threads[2].start()
        assert _until(lambda: outbox._queue.full(), 5.0), "one in hand and two waiting"
        started = time.monotonic()
        busy = outbox.submit(held)
        assert time.monotonic() - started < 1.0, "busy is said at once"
        sender.release.set()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        sender.release.set()
        stop.set()
        outbox.thread.join(timeout=5)

    assert busy == BUSY
    assert answers == [(200, {"status": "sent", "said": "held"})] * 3


def test_an_outbox_whose_sender_cannot_be_built_says_so_to_every_job():
    def build():
        raise RuntimeError("no such endpoint")

    outbox, stop = _outbox(build)
    try:
        answer = _submitted(outbox, lambda built: (200, {}))
    finally:
        stop.set()
        outbox.thread.join(timeout=5)

    assert answer == (
        504,
        {
            "status": "not_delivered",
            "said": "not delivered: wlx serve could not reach the rig (RuntimeError: no such endpoint)",
        },
    )


def test_work_that_raises_is_answered_not_delivered():
    outbox, stop = _outbox(_Sender)
    try:

        def raises(built):
            raise ValueError("socket gone")

        answer = _submitted(outbox, raises)
    finally:
        stop.set()
        outbox.thread.join(timeout=5)

    assert answer == (504, {"status": "not_delivered", "said": "not delivered: ValueError: socket gone"})


def test_a_job_submitted_to_a_stopped_outbox_is_answered_not_delivered():
    outbox, stop = _outbox(_Sender)
    stop.set()
    outbox.thread.join(timeout=5)

    assert _submitted(outbox, lambda built: (200, {}))[1]["said"] == (
        "not delivered: wlx serve is closing"
    )


def _until(predicate, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


# --- P4d-2b b2a: the Server's command and mark threads, on real sockets ---------------


def _rig(zmq_cleanup) -> ZmqLink:
    return zmq_cleanup(
        ZmqLink(
            pub_endpoint="tcp://127.0.0.1:0",
            rep_endpoint="tcp://127.0.0.1:0",
            mark_endpoint="tcp://127.0.0.1:0",
        )
    )


def _drained(link, until, seconds: float = 10.0) -> tuple[threading.Thread, list]:
    got: list = []

    def run() -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and until not in got:
            got.extend(link.drain())
            time.sleep(0.005)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, got


def test_a_command_is_sent_when_the_rig_acknowledges_it(zmq_cleanup, server_cleanup):
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(sub=rig.pub_endpoint, req=rig.rep_endpoint, http=("127.0.0.1", 0), token=TOKEN)
    )
    server.start()
    try:
        thread, got = _drained(rig, Pause(by="jake (box, unverified)"))
        status, answer = _post(server.address[1], {"kind": "pause", "by": "jake"})
        thread.join(timeout=15)
    finally:
        server.close()

    assert (status, answer["status"]) == (200, "sent")
    assert got == [Pause(by="jake (box, unverified)")]


def test_with_taskd_gone_the_page_is_told_not_delivered(zmq_cleanup, server_cleanup):
    """Spec §5.4: with `taskd` gone, the page is told *not delivered* -- once the
    connect timeout passes, since there is no rig to wait a reply from."""
    probe = _rig(zmq_cleanup)
    pub, rep = probe.pub_endpoint, probe.rep_endpoint
    probe.close()
    server = server_cleanup(
        Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN, connect_timeout_s=0.2)
    )
    server.start()
    try:
        status, answer = _post(server.address[1], {"kind": "stop", "by": "jake"})
    finally:
        server.close()

    assert status == 504
    assert answer == {
        "status": "not_delivered",
        "said": f"not delivered: no rig is connected on {rep}",
    }


def _drained_any(link, kind, seconds: float = 10.0) -> tuple[threading.Thread, list]:
    """Drain `link` on a thread until a command of type `kind` arrives."""
    got: list = []

    def run() -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not any(isinstance(c, kind) for c in got):
            got.extend(link.drain())
            time.sleep(0.005)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, got


def test_a_mark_goes_ahead_of_a_command_waiting_on_the_rig(zmq_cleanup, server_cleanup):
    """Spec §5.3: the mark's signal goes on its own path, as soon as it arrives,
    ahead of the queue -- here, ahead of a pause the rig has not acknowledged,
    because nothing drains it -- and the note that follows it carries the instants
    `wlx serve` kept for that mark: the browser's `pressed_at`, and when this process
    received the signal, on its own clock."""
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(
            sub=rig.pub_endpoint,
            req=rig.rep_endpoint,
            mark=rig.mark_endpoint,
            http=("127.0.0.1", 0),
            token=TOKEN,
            reply_timeout_s=2.0,
        )
    )
    server.start()
    port = server.address[1]
    waiting: list = []
    pause = threading.Thread(
        target=lambda: waiting.append(_post(port, {"kind": "pause", "by": "sam"})),
        daemon=True,
    )
    try:
        pause.start()
        time.sleep(0.2)
        before = time.time()
        started = time.monotonic()
        status, answer = _post(port, {"kind": "mark", "by": "jake", "pressed_at": 1_700_000_000.5})
        took = time.monotonic() - started
        after = time.time()
        signalled = 0
        for _ in range(400):
            signalled = rig.mark_signal()
            if signalled:
                break
            time.sleep(0.005)
        pause.join(timeout=10)

        thread, got = _drained_any(rig, Mark)
        noted = _post(port, {"kind": "note", "by": "jake", "mark": answer["mark"], "note": "bubble"})
        thread.join(timeout=15)
    finally:
        server.close()

    assert (status, answer["status"]) == (200, "signaled")
    assert took < 1.5, "the mark waited behind the pause"
    assert 1 <= answer["mark"] <= MARK_ID_LIMIT
    assert signalled == answer["mark"]
    assert waiting and waiting[0][0] == 504, "the pause was never acknowledged"
    assert noted[0] == 200
    (note,) = [command for command in got if isinstance(command, Mark)]
    assert (note.mark, note.note, note.by) == (answer["mark"], "bubble", "jake (box, unverified)")
    assert note.pressed_at == 1_700_000_000.5
    assert before <= note.received_at <= after


def test_a_console_without_the_mark_endpoint_says_a_mark_is_not_delivered(
    zmq_cleanup, server_cleanup
):
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(sub=rig.pub_endpoint, req=rig.rep_endpoint, http=("127.0.0.1", 0), token=TOKEN)
    )
    server.start()
    try:
        status, answer = _post(server.address[1], {"kind": "mark", "by": "jake"})
    finally:
        server.close()

    assert status == 504
    assert answer["said"] == f"not delivered: {NO_MARK_ENDPOINT}"
    assert server._marks is None


def test_a_note_for_a_mark_this_console_does_not_know_carries_no_instants(
    zmq_cleanup, server_cleanup
):
    """Review Focus 5's neighbor: a `wlx serve` restarted between a mark and its note
    knows neither instant, and says so with `None` rather than inventing one."""
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(sub=rig.pub_endpoint, req=rig.rep_endpoint, http=("127.0.0.1", 0), token=TOKEN)
    )
    server.start()
    try:
        thread, got = _drained_any(rig, Mark)
        status, _ = _post(server.address[1], {"kind": "note", "by": "jake", "mark": 42, "note": ""})
        thread.join(timeout=15)
    finally:
        server.close()

    assert status == 200
    assert got == [Mark(mark=42, note="", by="jake (box, unverified)", pressed_at=None, received_at=None)]


def test_the_marks_kept_for_their_notes_are_the_newest_and_each_is_given_once():
    server = Server(sub=ENDPOINT, req="tcp://127.0.0.1:1", http=("127.0.0.1", 0), token=TOKEN)
    try:
        for number in range(1, MARKS_REMEMBERED + 2):
            server._remember(number, None, float(number))

        assert server._recall(1) == (None, None), "the oldest was let go"
        assert server._recall(MARKS_REMEMBERED + 1) == (None, float(MARKS_REMEMBERED + 1))
        assert server._recall(MARKS_REMEMBERED + 1) == (None, None), "given once"
    finally:
        server.close()


def test_closing_the_server_stops_its_command_and_mark_threads(zmq_cleanup, server_cleanup):
    rig = _rig(zmq_cleanup)
    server = server_cleanup(
        Server(
            sub=rig.pub_endpoint,
            req=rig.rep_endpoint,
            mark=rig.mark_endpoint,
            http=("127.0.0.1", 0),
            token=TOKEN,
        )
    )
    server.start()
    assert server._commands.thread.is_alive() and server._marks.thread.is_alive()

    started = time.monotonic()
    server.close()

    assert time.monotonic() - started < 2.0
    assert not server._commands.thread.is_alive()
    assert not server._marks.thread.is_alive()


def test_wlx_serve_takes_the_mark_endpoint_and_the_allowed_hosts(tmp_path, monkeypatch):
    seen: dict = {}

    def stop_at_construction(self, **kwargs) -> None:
        seen.update(kwargs)
        raise OSError("stopped here by the test")

    monkeypatch.setattr(Server, "__init__", stop_at_construction)

    with pytest.raises(SystemExit, match="stopped here by the test"):
        main(
            _serve_args(
                tmp_path,
                link="tcp://127.0.0.1:5571,tcp://127.0.0.1:5572,tcp://127.0.0.1:5573",
                extra=("--allow-host", "rig3.lab", "--allow-host", "rig3"),
            )
        )

    assert seen["mark"] == "tcp://127.0.0.1:5573"
    assert seen["allow_hosts"] == ("rig3.lab", "rig3")
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py`
Expected: fails to collect — `ImportError: cannot import name 'BUSY' from 'wl_expcontroller.serve'`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
        "serve",
        help="serve a running session's read-only browser console, and /health",
```

with:

```python
        "serve",
        help="serve a running session's browser console, and /health",
```

In `wl_expcontroller/cli.py`, in `main`, replace:

```python
        metavar="PUB,REP",
        help="the session's two endpoints, exactly as given to `wlx run --link "
        "PUB,REP`. Telemetry is read from the first; the second is connected and, in "
        "this slice (P4d-2b b1), never sent to -- nothing on the page writes",
```

with:

```python
        metavar="PUB,REP[,MARK]",
        help="the session's endpoints, exactly as given to `wlx run --link`. "
        "Telemetry is read from the first, commands are sent to the second, and an "
        "operator's mark signal to the third; without the third the page's mark "
        "control is greyed",
    )
    server_parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="NAME",
        help="a name this box is reached by, to answer to (P4d-2b spec §5.3); may be "
        "given more than once. Every request's Host must name this console -- "
        "loopback, this box's own host names and addresses, or a name given here -- "
        "or it is refused with a 421, against DNS rebinding",
```

In `wl_expcontroller/serve.py`, replace:

```python
"""`wlx serve` -- the browser console's process (P4d-2b slice b1).

```

with:

```python
"""`wlx serve` -- the browser console's process (P4d-2b slices b1 and b2a).

```

In `wl_expcontroller/serve.py`, replace:

```python

Spec: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §1-§4.
```

with:

```python

Spec: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §1-§5.
```

In `wl_expcontroller/serve.py`, replace:

```python
Everything else is 404 or 405, as JSON, never the stdlib's HTML page. **b1 has no
`POST`**: nothing on the page writes; writes from the box are slice b2's.
```

with:

```python
- `POST /commands` (P4d-2b b2a, spec §5.3) -- one JSON command from the box's own
  page, accepted only under spec §2's four checks and validated before anything is
  queued (`parse_command`); answered *sent*, *not delivered* or *busy*, the truth
  about delivery.
```

In `wl_expcontroller/serve.py`, replace:

```python
**Restarting it changes nothing in `taskd`** (spec §2): it only ever reads the PUB
socket, and telemetry is lossy by design (S9a §9).
```

with:

```python
Everything else is 404 or 405, as JSON, never the stdlib's HTML page. **Every request
is answered only when its `Host` names this console** (spec §2, §5.3): loopback, the
box's own names and addresses, and `--allow-host` names (`box_names`); anything else
gets a JSON 421 and no page, which closes DNS rebinding on the LAN-open reads too.
```

In `wl_expcontroller/serve.py`, replace:

```python
**Threads, and what each owns.** The telemetry thread (`Server._listen`) owns the
`ZmqConsole` -- both of its sockets, created, read and closed there -- so each ZMQ
socket has one owning thread. b1 sends no command, so the REQ socket is connected and
never used; slice b2 moves it to a command thread of its own. Each browser's
`/events` runs on the HTTP server's thread for that connection, reading its own
bounded queue from the `Hub`.
```

with:

```python
**Restarting it changes nothing in `taskd`** (spec §2): it reads the PUB socket, and
what it sends is acknowledged or said not to be; a pause, a schedule and every
setting are held by `taskd`, not here.

**Threads, and what each owns** (spec §2: each ZMQ socket has one owning thread).
The telemetry thread (`Server._listen`) owns a read-only `ZmqConsole`, its SUB
socket. The command thread (an `Outbox`) owns a `ZmqCommands`, the REQ socket, and
takes commands from a bounded queue. The mark thread (another `Outbox`) owns a
`ZmqMarks`, the PUSH socket to the session's mark endpoint, so a mark's signal goes
ahead of any command waiting on the rig's acknowledgment (spec §5.3). Each browser's
`/events` and each `POST` runs on the HTTP server's thread for that connection.
```

In `wl_expcontroller/serve.py`, replace:

```python
§3); `QUEUE_DEPTH`, `RATE_SAMPLE_S`, `KEEPALIVE_S`, `REQUEST_TIMEOUT_S` and
`RETRY_MS` are housekeeping, not a measurement of this system.
```

with:

```python
§3); `QUEUE_DEPTH`, `RATE_SAMPLE_S`, `KEEPALIVE_S`, `REQUEST_TIMEOUT_S`, `RETRY_MS`,
`COMMAND_QUEUE_DEPTH`, `MARK_QUEUE_DEPTH` and the link's `REPLY_TIMEOUT_S` and
`CONNECT_TIMEOUT_S` are housekeeping, not a measurement of this system.
```

In `wl_expcontroller/serve.py`, replace:

```python
import secrets
import sys
```

with:

```python
import secrets
import socket
import sys
```

In `wl_expcontroller/serve.py`, replace:

```python
import threading
import traceback
```

with:

```python
import threading
import time
import traceback
```

In `wl_expcontroller/serve.py`, replace:

```python
import traceback
from collections import deque
```

with:

```python
import traceback
from collections import OrderedDict, deque
```

In `wl_expcontroller/serve.py`, replace:

```python
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
```

with:

```python
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
```

In `wl_expcontroller/serve.py`, in `Hub.__init__`, replace:

```python
        steady: Callable[[], float] = _welfare.steady_seconds,
    ) -> None:
```

with:

```python
        steady: Callable[[], float] = _welfare.steady_seconds,
        marks: bool = False,
    ) -> None:
```

In `wl_expcontroller/serve.py`, in `Hub.__init__`, replace:

```python
        self._endpoint = endpoint
        self._steady = steady
```

with:

```python
        self._endpoint = endpoint
        #: Whether this console has the session's mark endpoint (P4d-2b b2a), for
        #: every `View`: without it the page greys its mark control.
        self._marks = marks
        self._steady = steady
```

In `wl_expcontroller/serve.py`, in `Hub.snapshot`, replace:

```python
    def snapshot(
        self, *, on_box: bool, stale_after_s: float
```

with:

```python
    def snapshot(
        self, *, on_box: bool, stale_after_s: float, can_write: bool = False
```

In `wl_expcontroller/serve.py`, in `Hub.snapshot`, replace:

```python
        """The latest frame and the `View` a render of it needs, read together. The
        frame's age is on `steady` alone (ledger Ruling 1)."""
```

with:

```python
        """The latest frame and the `View` a render of it needs, read together. The
        frame's age is on `steady` alone (ledger Ruling 1). `can_write` is the
        handler's to say (P4d-2b b2a, `may_write`); a caller that does not say gets a
        view that may not write."""
```

In `wl_expcontroller/serve.py`, in `Hub.snapshot`, replace:

```python
            endpoint=self._endpoint,
        )
```

with:

```python
            endpoint=self._endpoint,
            can_write=can_write,
            can_mark=self._marks,
        )
```

In `wl_expcontroller/serve.py`, replace:

```python
_FONTS = {f"/fonts/{font.file}": font for font in _web.FONTS}
_ROUTES = frozenset({"/", "/events", "/health", *_FONTS})
```

with:

```python
_FONTS = {f"/fonts/{font.file}": font for font in _web.FONTS}
_ROUTES = frozenset({"/", "/events", "/health", "/commands", *_FONTS})
```

In `wl_expcontroller/serve.py`, replace:

```python
_UNAUTHORIZED = {"error": "unauthorized"}
#: Fixed bodies, keyed on the status alone and echoing nothing a caller sent
```

with:

```python
_UNAUTHORIZED = {"error": "unauthorized"}
#: What a request whose `Host` does not name this console is answered (P4d-2b spec
#: §5.3): a JSON 421 and no page. It names no host, echoing nothing it was sent.
_MISDIRECTED = {
    "error": "misdirected request",
    "said": (
        "this console answers only to its own names: loopback, this box's host names "
        "and addresses, and names given with --allow-host"
    ),
}
#: Fixed bodies, keyed on the status alone and echoing nothing a caller sent
```

In `wl_expcontroller/serve.py`, replace:

```python

def event(payload: dict) -> bytes:
```

with:

```python

#: The names loopback goes by in a `Host` header (P4d-2b spec §2, §5.3).
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def host_name(header: str | None) -> str | None:
    """The name a `Host` header gives, lowercased and without its port, or `None`
    when there is none or it does not parse: `127.0.0.1:8080` is `127.0.0.1`,
    `[::1]:8080` is `::1`, `Box.local` is `box.local`. An unbracketed IPv6
    address is not a `Host` (RFC 9110 §7.2 brackets it) and names nothing here."""
    if not header or not header.isascii():
        return None
    value = header.strip().lower()
    if value.startswith("["):
        name, bracket, rest = value[1:].partition("]")
        if not bracket or not name:
            return None
        if rest and not (rest.startswith(":") and rest[1:].isdecimal()):
            return None
        return name
    name, colon, port = value.rpartition(":")
    if not colon:
        return value or None
    if not port.isdecimal() or not name or ":" in name:
        return None
    return name


def names_loopback(name: str | None) -> bool:
    """Whether a `Host` name is this machine by loopback (spec §2's second check):
    `localhost`, or an address in 127.0.0.0/8 or `::1`."""
    if name is None:
        return False
    return name == "localhost" or on_box(name)


def box_names(allowed: tuple[str, ...] = ()) -> frozenset[str]:
    """Every name a request's `Host` may give for this console (P4d-2b spec §5.3):
    loopback, this box's host name and fully qualified name, the addresses those
    resolve to, and `allowed` -- `--allow-host`, for a name the box is reached by
    that it does not know itself by. Lowercased.

    Read once, when `wlx serve` starts. A lookup that fails adds nothing and is not
    an error: loopback and `--allow-host` still work, and the refusal a LAN viewer
    then gets names the flag that fixes it."""
    names = set(LOOPBACK_NAMES)
    for name in (socket.gethostname(), socket.getfqdn()):
        if name:
            names.add(name.lower())
    for name in sorted(names - LOOPBACK_NAMES):
        try:
            found = socket.getaddrinfo(name, None)
        except OSError:
            continue
        names.update(info[4][0].split("%", 1)[0].lower() for info in found)
    names.update(name.strip().lower() for name in allowed if name.strip())
    return frozenset(names)


def event(payload: dict) -> bytes:
```

In `wl_expcontroller/serve.py`, replace:

```python

def make_handler(
```

with:

```python

# --- writes from the box (P4d-2b b2a, spec §5.3) ---------------------------------------

#: The largest body `POST /commands` reads, in bytes. One command is a few hundred;
#: a longer body is refused before it is read. Housekeeping, not a measurement.
BODY_LIMIT = 4096
#: The longest name a person may give at the box's prompt (spec §5.2).
NAME_LIMIT = 64
#: The largest mark number `wlx serve` hands a browser: 2**53 - 1, JavaScript's
#: `Number.MAX_SAFE_INTEGER`, the largest whole number a browser's JSON carries
#: exactly -- the page sends the number back with the note, and a number it had
#: rounded would join nothing. Within the signal's eight bytes (`link.MARK_LIMIT`).
MARK_ID_LIMIT = 2**53 - 1
#: How many marks' instants `wlx serve` keeps for the notes that follow them. A mark
#: whose note comes after 256 later marks, or after a restart, is recorded with its
#: pressed and received instants unknown, never guessed.
MARKS_REMEMBERED = 256
#: How many commands may wait for the command thread, and marks for the mark thread,
#: before `POST /commands` answers *busy* (spec §5.3). Housekeeping, not a
#: measurement: a person's clicks, debounced, do not fill them; a flood does.
COMMAND_QUEUE_DEPTH = 4
MARK_QUEUE_DEPTH = 8
#: How long an outbox thread waits for work before it looks again at whether to
#: stop, so `Server.close` returns promptly. A responsiveness choice.
OUTBOX_POLL_S = 0.25

#: What the page is told when the rig has a command (spec §5.3): *sent* means `taskd`
#: acknowledged receipt. Whether it was applied or refused is the feed's to show.
SENT = (
    "sent: the rig has it and acts on it at its next trial boundary; the changes feed "
    "shows what it did"
)
#: What the page is told when the queue is full (spec §5.3).
BUSY = (
    503,
    {
        "status": "busy",
        "said": (
            "busy: wlx serve is still sending earlier commands, so this one was not "
            "sent; try again"
        ),
    },
)


class BadCommand(ValueError):
    """A `POST /commands` body that is not a command this console sends. The message
    is the sentence the page shows; nothing was queued."""


@dataclass(frozen=True, slots=True)
class MarkSignal:
    """M pressed at the box: send the mark's signal now, ahead of every command (spec
    §5.3). `pressed_at` is the browser's clock, `None` if it did not say."""

    by: str
    pressed_at: float | None


@dataclass(frozen=True, slots=True)
class MarkNote:
    """The note typed after M -- empty after Esc -- for mark `mark`: sent to the rig as
    a `link.Mark` command, with the instants `wlx serve` kept for that mark."""

    mark: int
    note: str
    by: str


#: The fields each kind of command takes besides `kind` and `by`. A schedule takes
#: exactly one of `at`, `trials` or `ml`, checked in `parse_command`.
_SHAPES = {
    "set": frozenset({"name", "value"}),
    "stop": frozenset(),
    "pause": frozenset(),
    "resume": frozenset(),
    "cancel": frozenset(),
    "schedule": frozenset({"at", "trials", "ml"}),
    "mark": frozenset({"pressed_at"}),
    "note": frozenset({"mark", "note"}),
}
_SCHEDULES = {"at": "clock", "trials": "trials", "ml": "fluid"}


def _person(by: object) -> str:
    """The actor a box command is recorded under: the name the page asked for, as
    `NAME (box, unverified)` (spec §2, S9a §6: a forgeable name is worse than none,
    because it is believed, so it says it is unverified)."""
    if (
        not isinstance(by, str)
        or not by.strip()
        or len(by.strip()) > NAME_LIMIT
        or not by.strip().isprintable()
    ):
        raise BadCommand(
            f"every command records who sent it (S9a §6): give a name of 1 to "
            f"{NAME_LIMIT} printable characters"
        )
    return f"{by.strip()} (box, unverified)"


def parse_command(data: object):
    """One `POST /commands` body -- a JSON object with a `kind` and the person's
    name, `by` -- as what `Server.dispatch` sends: a `link` command, a `MarkSignal`
    or a `MarkNote`. **Validated before anything is queued** (spec §5.3), with the
    wire's own rules where the wire has one (`link._setting` for a value, M8;
    `link.check_schedule` for a schedule), so the page hears the sentence at once
    and the rig never sees what it would refuse on type. Raises `BadCommand`.

    A field a kind does not take is refused, not ignored: a page that sent one has a
    bug a person should see."""
    if not isinstance(data, dict):
        raise BadCommand("a command is one JSON object")
    kind = data.get("kind")
    if kind not in _SHAPES:
        raise BadCommand(f"{kind!r} is not a command this console sends")
    by = _person(data.get("by"))
    extra = set(data) - {"kind", "by"} - _SHAPES[kind]
    if extra:
        raise BadCommand(f"a {kind} command takes no {', '.join(sorted(extra))}")
    if kind == "set":
        name = data.get("name")
        if not isinstance(name, str) or not name or len(name) > _link.TEXT_LIMIT:
            raise BadCommand("a setting names its parameter")
        try:
            value = _link._setting(data.get("value"), name, by)
        except _link.CommandRefused as refused:
            raise BadCommand(refused.why) from refused
        return _link.SetParameter(name=name, value=value, by=by)
    if kind == "schedule":
        given = [key for key in _SCHEDULES if key in data]
        if len(given) != 1:
            raise BadCommand("a scheduled stop takes exactly one of at, trials or ml")
        stop, value = _SCHEDULES[given[0]], data[given[0]]
        why = _link.check_schedule(stop, value)
        if why is not None:
            raise BadCommand(why)
        return _link.ScheduleStop(kind=stop, value=value, by=by)
    if kind == "mark":
        pressed = data.get("pressed_at")
        if pressed is not None and (
            isinstance(pressed, bool)
            or not isinstance(pressed, (int, float))
            or not math.isfinite(pressed)
        ):
            raise BadCommand("a mark's pressed_at is the browser's clock, in seconds")
        return MarkSignal(by=by, pressed_at=None if pressed is None else float(pressed))
    if kind == "note":
        number, note = data.get("mark"), data.get("note")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= MARK_ID_LIMIT
        ):
            raise BadCommand("a note names the mark it is for")
        if not isinstance(note, str) or len(note) > _link.NOTE_LIMIT:
            raise BadCommand(f"a note is text of at most {_link.NOTE_LIMIT} characters")
        return MarkNote(mark=number, note=note, by=by)
    return {
        "stop": _link.Stop,
        "pause": _link.Pause,
        "resume": _link.Resume,
        "cancel": _link.CancelScheduledStop,
    }[kind](by=by)


def not_delivered(why: str) -> tuple[int, dict]:
    """The answer for a command or a mark that did not reach the rig (spec §5.3)."""
    said = why if why.startswith("not delivered") else f"not delivered: {why}"
    return 504, {"status": "not_delivered", "said": said}


@dataclass
class _Job:
    """One piece of work for an `Outbox`'s thread, and the answer it leaves."""

    work: Callable[[object], tuple[int, dict]]
    answer: tuple[int, dict] | None = None
    done: threading.Event = field(default_factory=threading.Event)


class Outbox:
    """A bounded queue and the one thread that owns a sender (spec §2: each ZMQ socket
    has one owning thread). `wlx serve` has two: the command thread, whose sender is a
    `link.ZmqCommands`, and the mark thread, whose sender is a `link.ZmqMarks`.

    **The sender is built on the thread**, by `build`, and closed there, so no other
    thread ever touches its socket. `submit` puts one job on the queue -- or answers
    *busy* at once when the queue is full (spec §5.3) -- and waits for its answer.
    **Every job is answered**: by its work; by `not_delivered` when the work raised,
    or the sender could not be built; or, when the thread stops, by *not delivered:
    wlx serve is closing* -- so no HTTP handler waits forever. `stop` is the
    `Server`'s own stop event, so whatever stops the server stops this thread.
    """

    def __init__(
        self,
        name: str,
        build: Callable[[], object],
        depth: int,
        stop: threading.Event,
    ) -> None:
        self._build = build
        self._queue: queue.Queue = queue.Queue(maxsize=depth)
        self._stop = stop
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def submit(self, work: Callable[[object], tuple[int, dict]]) -> tuple[int, dict]:
        if self._stop.is_set():
            return not_delivered("wlx serve is closing")
        job = _Job(work)
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            return BUSY
        while not job.done.wait(OUTBOX_POLL_S):
            if not self.thread.is_alive():
                # Queued after the thread answered its last job and left: nobody
                # will answer this one, so it is answered here.
                return not_delivered("wlx serve is closing")
        return job.answer

    def _run(self) -> None:
        sender, broken = None, None
        try:
            sender = self._build()
        except Exception as exc:  # noqa: BLE001 -- said to every job, never hidden
            broken = _link._describe(exc)
        try:
            while not self._stop.is_set():
                try:
                    job = self._queue.get(timeout=OUTBOX_POLL_S)
                except queue.Empty:
                    continue
                self._answer(job, sender, broken)
        finally:
            if sender is not None:
                sender.close()
            while True:
                try:
                    job = self._queue.get_nowait()
                except queue.Empty:
                    break
                job.answer = not_delivered("wlx serve is closing")
                job.done.set()

    def _answer(self, job: _Job, sender: object, broken: str | None) -> None:
        try:
            job.answer = (
                not_delivered(f"wlx serve could not reach the rig ({broken})")
                if broken is not None
                else job.work(sender)
            )
        except Exception as exc:  # noqa: BLE001 -- answered, never hidden
            job.answer = not_delivered(_link._describe(exc))
        finally:
            job.done.set()


def _delivered(command) -> Callable[[object], tuple[int, dict]]:
    """The command thread's work for one command: deliver it and say so, or say why
    not (spec §5.3)."""

    def work(commands) -> tuple[int, dict]:
        try:
            commands.deliver(command)
        except _link.NotDelivered as exc:
            return not_delivered(str(exc))
        return 200, {"status": "sent", "said": SENT}

    return work


def make_handler(
```

In `wl_expcontroller/serve.py`, in `make_handler`, replace:

```python
    keepalive_s: float = KEEPALIVE_S,
) -> type[BaseHTTPRequestHandler]:
```

with:

```python
    keepalive_s: float = KEEPALIVE_S,
    hosts: frozenset[str] = LOOPBACK_NAMES,
    dispatch: Callable[[object], tuple[int, dict]] | None = None,
) -> type[BaseHTTPRequestHandler]:
```

In `wl_expcontroller/serve.py`, in `make_handler`, replace:

```python
    request, the correct one included (wl-preproc, review round 2's Minor 7).
    """
```

with:

```python
    request, the correct one included (wl-preproc, review round 2's Minor 7).

    **P4d-2b b2a.** `hosts` is every name a request's `Host` may give (`box_names`);
    anything else is a JSON 421. `dispatch` sends a parsed command and says what
    became of it (`Server.dispatch`); a handler given none answers every command
    *not delivered*.
    """
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler`, replace:

```python
        _keepalive_s = keepalive_s
        # No interpreter version in any `Server` header (wl-preproc's Important 5).
```

with:

```python
        _keepalive_s = keepalive_s
        _hosts = hosts
        # A function stored on a class becomes a method; `staticmethod` keeps it the
        # plain callable it was given.
        _dispatch = None if dispatch is None else staticmethod(dispatch)
        # No interpreter version in any `Server` header (wl-preproc's Important 5).
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler`, replace:

```python

        def send_error(self, code, message=None, explain=None) -> None:
```

with:

```python

        def _host_ok(self) -> bool:
            """Whether this request's `Host` names this console (spec §2, §5.3)."""
            return host_name(self.headers.get("Host")) in self._hosts

        def may_write(self) -> bool:
            """Spec §2's first two checks -- a loopback peer, and a `Host` naming
            loopback -- which are what a page's controls are greyed by. `POST
            /commands` adds the other two, `Origin` and `Content-Type`."""
            return on_box(self.client_address[0]) and names_loopback(
                host_name(self.headers.get("Host"))
            )

        def _from_the_box(self) -> bool:
            """All four of spec §2's checks on a write: a loopback peer; `Host` naming
            loopback (against DNS rebinding); `Origin` being the page this console
            serves on that host (against a cross-site post from another page open
            in the box's browser); and `Content-Type: application/json`, which makes
            a browser ask a preflight this server never approves."""
            host = self.headers.get("Host") or ""
            origin = self.headers.get("Origin") or ""
            content = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            return (
                self.may_write()
                and origin.lower() == f"http://{host}".lower()
                and content.lower() == "application/json"
            )

        def send_error(self, code, message=None, explain=None) -> None:
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._refuse_method`, replace:

```python
        def _refuse_method(self) -> None:
            code = 405 if self.path in _ROUTES else 404
```

with:

```python
        def _refuse_method(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            code = 405 if self.path in _ROUTES else 404
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler`, replace:

```python
        # Every verb a client commonly sends besides GET. b1 takes no POST at all:
        # nothing on the page writes (spec §4.2).
        do_POST = _refuse_method
```

with:

```python
        # Every verb a client commonly sends besides GET and POST. An `OPTIONS`
        # preflight is one of them: refused, so a cross-site page is never let to
        # post JSON (spec §2's fourth check).
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler`, replace:

```python

        def do_GET(self) -> None:
```

with:

```python

        def do_POST(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            if self.path != "/commands":
                self._refuse_method()
                return
            self._command()

        def _command(self) -> None:
            """`POST /commands` (spec §5.3): one JSON command, from the box, checked
            and validated before anything is queued, then sent and answered *sent*,
            *not delivered* or *busy*."""
            if not self._from_the_box():
                self._send_json(
                    403, {"status": "refused", "said": _web.CONTROLS_AT_THE_BOX}
                )
                return
            length = self.headers.get("Content-Length") or ""
            if not length.isascii() or not length.isdecimal():
                self._send_json(
                    400, {"status": "refused", "said": "a command needs a Content-Length"}
                )
                return
            if int(length) > BODY_LIMIT:
                self._send_json(
                    413,
                    {"status": "refused", "said": f"a command is at most {BODY_LIMIT} bytes"},
                )
                return
            try:
                data = json.loads(self.rfile.read(int(length)).decode("utf-8"))
                request = parse_command(data)
            except (UnicodeDecodeError, ValueError) as exc:
                # `BadCommand` is a `ValueError`, and so is `json`'s own error.
                said = str(exc) if isinstance(exc, BadCommand) else "a command is one JSON object"
                self._send_json(400, {"status": "refused", "said": f"not sent: {said}"})
                return
            if self._dispatch is None:
                code, answer = not_delivered("this console has no command path")
            else:
                code, answer = self._dispatch(request)
            self._send_json(code, answer)

        def do_GET(self) -> None:
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler.do_GET`, replace:

```python
        def do_GET(self) -> None:
            if self.path == "/":
```

with:

```python
        def do_GET(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            if self.path == "/":
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler.do_GET`, replace:

```python
            else:
                self._send_json(404, _ERRORS[404])
```

with:

```python
            else:
                # 405 for a known path that takes another method -- `/commands`,
                # since b2a -- and 404 for anything else.
                self._refuse_method()
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._page`, replace:

```python
        def _page(self) -> None:
            latest, view = self._hub.snapshot(
```

with:

```python
        def _page(self) -> None:
            can_write = self.may_write()
            latest, view = self._hub.snapshot(
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._page`, replace:

```python
                stale_after_s=self._stale_after_s,
            )
```

with:

```python
                stale_after_s=self._stale_after_s,
                can_write=can_write,
            )
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._page`, replace:

```python
                nonce=nonce,
            )
```

with:

```python
                nonce=nonce,
                can_write=can_write,
            )
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._events`, replace:

```python
            box = on_box(self.client_address[0])
            subscriber = self._hub.subscribe(on_box=box)
```

with:

```python
            box = on_box(self.client_address[0])
            can_write = self.may_write()
            subscriber = self._hub.subscribe(on_box=box)
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._events`, replace:

```python
                sent: dict[str, str] = {}
                self._send_frame(box, sent)
```

with:

```python
                sent: dict[str, str] = {}
                self._send_frame(box, can_write, sent)
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._events`, replace:

```python
                    except queue.Empty:
                        self._send_frame(box, sent)
```

with:

```python
                    except queue.Empty:
                        self._send_frame(box, can_write, sent)
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._events`, replace:

```python
                        return
                    self._send_frame(box, sent)
```

with:

```python
                        return
                    self._send_frame(box, can_write, sent)
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler`, replace:

```python

        def _send_frame(self, box: bool, sent: dict) -> None:
```

with:

```python

        def _send_frame(self, box: bool, can_write: bool, sent: dict) -> None:
```

In `wl_expcontroller/serve.py`, in `make_handler.ConsoleHandler._send_frame`, replace:

```python
            latest, view = self._hub.snapshot(
                on_box=box, stale_after_s=self._stale_after_s
```

with:

```python
            latest, view = self._hub.snapshot(
                on_box=box, stale_after_s=self._stale_after_s, can_write=can_write
```

In `wl_expcontroller/serve.py`, in `Server`, replace:

```python
    is refused before anything else happens -- and starts two threads in `start`: the
    telemetry thread (`_listen`) and the HTTP server's loop.
```

with:

```python
    is refused before anything else happens -- and starts its threads in `start`: the
    telemetry thread (`_listen`), the command thread and, given a mark endpoint, the
    mark thread (each an `Outbox`, P4d-2b b2a), and the HTTP server's loop.

    `mark` is the session's mark endpoint, `--link`'s third; `None` without one, and
    then a mark is answered *not delivered* and the page greys its control.
    `allow_hosts` is `--allow-host`. `reply_timeout_s` and `connect_timeout_s` are
    the command sender's (`link.ZmqCommands`), passed so a test need not wait them.
```

In `wl_expcontroller/serve.py`, in `Server.__init__`, replace:

```python
        receive_timeout_s: float = RECEIVE_TIMEOUT_S,
    ) -> None:
```

with:

```python
        receive_timeout_s: float = RECEIVE_TIMEOUT_S,
        mark: str | None = None,
        allow_hosts: tuple[str, ...] = (),
        reply_timeout_s: float = _link.REPLY_TIMEOUT_S,
        connect_timeout_s: float = _link.CONNECT_TIMEOUT_S,
    ) -> None:
```

In `wl_expcontroller/serve.py`, in `Server.__init__`, replace:

```python
    ) -> None:
        self.hub = Hub(endpoint=sub)
```

with:

```python
    ) -> None:
        self.hub = Hub(endpoint=sub, marks=mark is not None)
```

In `wl_expcontroller/serve.py`, in `Server.__init__`, replace:

```python
        self._stop = threading.Event()
        #: Set by `_listen` when the telemetry thread cannot go on -- a transport
```

with:

```python
        self._stop = threading.Event()
        #: The command thread (spec §5.3): it alone owns the REQ socket.
        self._commands = Outbox(
            "wlx-serve-commands",
            lambda: _link.ZmqCommands(req, reply_timeout_s, connect_timeout_s),
            COMMAND_QUEUE_DEPTH,
            self._stop,
        )
        #: The mark thread: it alone owns the PUSH socket to the mark endpoint, so a
        #: mark's signal never waits behind a command (spec §5.3). `None` without a
        #: mark endpoint.
        self._marks = (
            None
            if mark is None
            else Outbox(
                "wlx-serve-marks",
                lambda: _link.ZmqMarks(mark, connect_timeout_s),
                MARK_QUEUE_DEPTH,
                self._stop,
            )
        )
        #: Each signalled mark's `(pressed_at, received_at)`, by number, for the note
        #: that follows it; the newest `MARKS_REMEMBERED`. HTTP threads share it.
        self._marked: OrderedDict = OrderedDict()
        self._marked_lock = threading.Lock()
        #: Set by `_listen` when the telemetry thread cannot go on -- a transport
```

In `wl_expcontroller/serve.py`, in `Server.__init__`, replace:

```python
                keepalive_s=keepalive_s,
            ),
```

with:

```python
                keepalive_s=keepalive_s,
                hosts=box_names(allow_hosts),
                dispatch=self.dispatch,
            ),
```

In `wl_expcontroller/serve.py`, in `Server.start`, replace:

```python
        self._telemetry.start()
        self._web.start()
```

with:

```python
        self._telemetry.start()
        self._commands.start()
        if self._marks is not None:
            self._marks.start()
        self._web.start()
```

In `wl_expcontroller/serve.py`, in `Server.start`, replace:

```python
        self._web.start()

```

with:

```python
        self._web.start()

    def dispatch(self, request) -> tuple[int, dict]:
        """Send one parsed command (`parse_command`) and say what became of it.

        A `MarkSignal` goes to the mark thread, ahead of every command; the rest go
        to the command thread's queue, a `MarkNote` as the `link.Mark` it is, with
        the instants this process kept for that mark."""
        if isinstance(request, MarkSignal):
            return self._signal(request)
        if isinstance(request, MarkNote):
            pressed_at, received_at = self._recall(request.mark)
            request = _link.Mark(
                mark=request.mark,
                note=request.note,
                by=request.by,
                pressed_at=pressed_at,
                received_at=received_at,
            )
        return self._commands.submit(_delivered(request))

    def _signal(self, request: MarkSignal) -> tuple[int, dict]:
        """A mark's signal (spec §5.1, §5.3): a fresh number, the instant this
        process received it -- its own host clock, one of the record's three -- and
        the signal sent on the mark thread. Answered *signaled* with the number the
        page sends back with the note."""
        if self._marks is None:
            return not_delivered(_web.NO_MARK_ENDPOINT)
        number = secrets.randbelow(MARK_ID_LIMIT) + 1
        received_at = time.time()

        def work(marks) -> tuple[int, dict]:
            try:
                marks.signal(number)
            except _link.NotDelivered as exc:
                return not_delivered(str(exc))
            self._remember(number, request.pressed_at, received_at)
            return 200, {
                "status": "signaled",
                "mark": number,
                "said": "mark sent to the rig: type a note and press Enter, or Esc",
            }

        return self._marks.submit(work)

    def _remember(self, number: int, pressed_at: float | None, received_at: float) -> None:
        with self._marked_lock:
            self._marked[number] = (pressed_at, received_at)
            while len(self._marked) > MARKS_REMEMBERED:
                self._marked.popitem(last=False)

    def _recall(self, number: int) -> tuple[float | None, float | None]:
        with self._marked_lock:
            return self._marked.pop(number, (None, None))

```

In `wl_expcontroller/serve.py`, in `Server._listen`, replace:

```python
        try:
            with _link.ZmqConsole(
```

with:

```python
        try:
            # Read-only (P4d-2b b2a): no REQ socket here. Commands are the command
            # thread's, so each socket has one owning thread (spec §2).
            with _link.ZmqConsole(
```

In `wl_expcontroller/serve.py`, in `Server._listen`, replace:

```python
            with _link.ZmqConsole(
                self._sub, self._req, receive_timeout_s=self._receive_timeout_s
```

with:

```python
            with _link.ZmqConsole(
                self._sub, None, receive_timeout_s=self._receive_timeout_s
```

In `wl_expcontroller/serve.py`, in `Server.close`, replace:

```python
            self._telemetry.join(timeout=5)

```

with:

```python
            self._telemetry.join(timeout=5)
        # The outboxes stop on `_stop` too, answering anything still queued, and
        # close their sockets on their own threads (P4d-2b b2a).
        for outbox in (self._commands, self._marks):
            if outbox is not None and outbox.thread.ident is not None:
                outbox.thread.join(timeout=5)

```

In `wl_expcontroller/serve.py`, in `parse_link`, replace:

```python
def parse_link(text: str) -> tuple[str, str]:
    """`PUB,REP`, exactly as `wlx run --link` takes it. This process reads the first
    and, in b1, never sends to the second.
```

with:

```python
def parse_link(text: str) -> tuple[str, str, str | None]:
    """`PUB,REP` or `PUB,REP,MARK`, exactly as `wlx run --link` takes it (P4d-2b b2a
    added the third): telemetry is read from the first, commands are sent to the
    second, and mark signals to the third, which is `None` when not given.
```

In `wl_expcontroller/serve.py`, in `parse_link`, replace:

```python
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2 or not all(parts):
```

with:

```python
    parts = [part.strip() for part in text.split(",")]
    if len(parts) not in (2, 3) or not all(parts):
```

In `wl_expcontroller/serve.py`, in `parse_link`, replace:

```python
            f"refused: --link expects PUB,REP -- exactly two comma-separated endpoints "
            f"such as tcp://127.0.0.1:5571, as given to `wlx run --link` -- got {text!r}"
```

with:

```python
            f"refused: --link expects PUB,REP or PUB,REP,MARK -- two or three "
            f"comma-separated endpoints such as tcp://127.0.0.1:5571, as given to "
            f"`wlx run --link` -- got {text!r}"
```

In `wl_expcontroller/serve.py`, in `parse_link`, replace:

```python
        _refuse_unless_tcp_endpoint(endpoint, text)
    return parts[0], parts[1]
```

with:

```python
        _refuse_unless_tcp_endpoint(endpoint, text)
    return parts[0], parts[1], parts[2] if len(parts) == 3 else None
```

In `wl_expcontroller/serve.py`, in `run`, replace:

```python
    token = read_token(args.health_token_file)
    sub, req = parse_link(args.link)
```

with:

```python
    token = read_token(args.health_token_file)
    sub, req, mark = parse_link(args.link)
```

In `wl_expcontroller/serve.py`, in `run`, replace:

```python
        server = Server(
            sub=sub, req=req, http=(host, port), token=token, stale_after_s=stale_after
```

with:

```python
        server = Server(
            sub=sub,
            req=req,
            http=(host, port),
            token=token,
            stale_after_s=stale_after,
            mark=mark,
            allow_hosts=tuple(args.allow_host),
```

In `wl_expcontroller/serve.py`, in `run`, replace:

```python
            f"wlx serve: the console is at http://{bound_host}:{bound_port}/, reading "
            f"{sub}; GET /health needs the bearer token",
```

with:

```python
            f"wlx serve: the console is at http://{bound_host}:{bound_port}/, reading "
            f"{sub}, sending commands to {req} and marks to "
            f"{mark or 'nowhere (no MARK endpoint given)'}; controls work only from "
            f"this box's own browser at http://127.0.0.1:{bound_port}/; GET /health "
            f"needs the bearer token",
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1349 passed**, and `tests/test_no_transport_leak.py` still passes (`serve` imports `socket` and `time`, and no transport).

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/serve.py wl_expcontroller/cli.py tests/test_serve.py
git commit -m "Take commands from the box's own page, answer every request only to this console's names, and tell the truth about delivery"
```

---

### Task 12: End to end, the way the page drives it

**Why:** spec §5.4, sim first: a real `wlx run --link` in the simulator and a real `wlx serve`, on loopback, driven through `POST /commands` the way the page drives it — a setting staged then applied; a malformed setting (M8) refused on the feed while the session runs on; pause holding `trial_index` while the out-of-cage clock runs, resume continuing, and the limit ending a session mid-pause; a mark in the recorded event stream where its stamp says, with its three instants and its note; each kind of scheduled stop ending the session with its reason, and cancel removing one; a write from elsewhere refused before the rig sees it; *not delivered* with `taskd` gone; and `wlx serve` restarted while paused (Review Focus 5). **Test the path, not the piece** (CLAUDE.md): every link of this chain has its own test by now, and this is what shows the chain holds.

The clock kind's next occurrence is made a quarter second away inside the test (`taskd._next_occurrence`, in this process, where `wlx run` runs), because a real minute is too long for the suite; what that function computes is pinned by Task 7.

**These sessions have their own trial budget, and a frame wait that ends with the session** (Ruling 10; `docs/next-session.md`: *if a sweep prints `timed out`, the fix is a bound, not a shrug*). b1's `E2E_TRIAL_BUDGET` of 20,000 is sized for b1's session, which has no mark socket; a session with one runs fewer trials a second in the simulator, since every frame pays for the mark check Task 14 measures — b1's 20,000 took about 20 s without one, and 1,000 took a few seconds with one (scratch readings on one loaded machine). In the plan's pre-flight, `tools/mutate.py --returns None wl_expcontroller/taskd.py _command` under b1's budget ran each of these tests past 50 s — its 20 s frame wait, then its 30 s join with the session still short of the budget — and the suite past the harness's 300 s, which the harness prints as `caught … timed out` and no test noticed. `CONTROL_TRIAL_BUDGET` is 1,000, against 27 to 84 trials per test over three pre-flight runs (a scratch count), and `_Session.frame` gives up `LAST_FRAME_S` after `wlx run` ends, so the same mutant fails all twelve in about 100 s.

**Files:**
- Test: `tests/test_serve.py`

**Interfaces:**
- Consumes: everything above; b1's `_trial_budget`, `_main_uninterrupted`, `_stream`, `_events`, `GOOD`, `ALLOCATION`, `TWELVE_HOURS`, `_TASK_SETS`; Task 11's `_post`, `_rig`.
- Produces: `CONTROL_TRIAL_BUDGET`, `LAST_FRAME_S`, `_three_endpoints`, `_Session` (a real session and console, the card `wlx run` strobed onto, and the record) — for this file only.

- [ ] **Step 1: Write the tests**

In `tests/test_serve.py`, in `_trial_budget`, replace:

```python
    `run_trial` raises past that, so the session faults, publishes that it did, and
    `wlx run` ends -- `tests/test_cli.py`'s budget, for the one test here that runs a
```

with:

```python
    `run_trial` raises past that, so the session faults, publishes that it did, and
    `wlx run` ends -- `tests/test_cli.py`'s budget, for the tests here that run a
```

Append to `tests/test_serve.py`:

```python


# --- P4d-2b b2a end to end: a real `wlx run --link`, a real `wlx serve`, and POST
# /commands the way the page sends them (spec §5.4) ----------------------------------

#: The three framework codes b2a allocates (`tasks/allocation.py`), and the first code
#: `fixation_detection` strobes in a trial.
PAUSE_CODE, RESUME_CODE, MARK_CODE, FIX_ON = 4131, 4132, 4133, 4096
#: `fixation_detection`'s trial-ending markers (`codes._standing_outcomes`).
MARKERS = {34, 35, 36, 37, 38}

#: **Ruling 10, sized for these sessions.** Each one below is ended by the page's
#: `stop`, its schedule or its limit within about a hundred trials: 27 to 84 over three
#: runs of these twelve tests in the plan's pre-flight, 2026-09-27. b1's
#: `E2E_TRIAL_BUDGET` is sized for b1's session, which has no mark socket; a session
#: with one runs fewer trials a second in the simulator, every frame paying for the
#: mark check Task 14 measures. There, b1's 20,000 trials took about 20 s without one,
#: and 1,000 took a few seconds with one (scratch readings on one loaded machine, not
#: claims about this system). Under b1's budget, a mutant that breaks the command path
#: -- `taskd.Session._command` neutered -- held each of these tests past 50 s, its 20 s
#: frame wait and then its 30 s join, and the suite past the mutation harness's 300 s:
#: a timeout, which no test noticed.
CONTROL_TRIAL_BUDGET = 1_000

#: How long `_Session.frame` still waits once `wlx run` has ended, for the last frame
#: it published to reach the console.
LAST_FRAME_S = 2.0


def _three_endpoints(zmq_cleanup) -> tuple[str, str, str]:
    """A free PUB/REP/mark triple on loopback, bound by a throwaway link and released."""
    probe = _rig(zmq_cleanup)
    endpoints = probe.pub_endpoint, probe.rep_endpoint, probe.mark_endpoint
    probe.close()
    return endpoints


class _Session:
    """A real simulated `wlx run --link PUB,REP,MARK` on a thread, the `Server` beside
    it, and what a test reads them through: the latest frame the console holds, the
    card the session strobed onto (captured as `wlx run` builds it), and the record."""

    def __init__(self, tmp_path, monkeypatch, zmq_cleanup, *, bounds=TWELVE_HOURS,
                 session_id="2027-01-14_21", cleanup=None):
        from wl_expcontroller import dio

        _trial_budget(monkeypatch, CONTROL_TRIAL_BUDGET)
        self.cards: list = []
        cards = self.cards

        class _KeptCard(dio.Simulated):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                cards.append(self)

        monkeypatch.setattr(dio, "Simulated", _KeptCard)
        self.pub, self.rep, self.mark = _three_endpoints(zmq_cleanup)
        self.root = tmp_path
        self.session_id = session_id
        self.bounds = bounds
        self.zmq_cleanup = zmq_cleanup
        self.cleanup = cleanup
        self.result: dict = {}
        self.server = self.serve()
        self.runner = threading.Thread(target=self._run, daemon=True)

    def serve(self) -> Server:
        server = Server(
            sub=self.pub, req=self.rep, mark=self.mark, http=("127.0.0.1", 0), token=TOKEN
        )
        if self.cleanup is not None:
            self.cleanup(server)
        server.start()
        return server

    def _run(self) -> None:
        self.result["exit_code"] = _main_uninterrupted(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", str(self.bounds),
                "--root", str(self.root),
                "--session-id", self.session_id,
                "--subject", "REFERENCE",
                "--out-of-cage-at", time.strftime("%H:%M"),
                "--delivered-today", "0",
                "--trials", "100000",
                *_TASK_SETS,
                "--link", f"{self.pub},{self.rep},{self.mark}",
            ]
        )

    def __enter__(self) -> "_Session":
        self.runner.start()
        return self

    def __exit__(self, *exc_info) -> None:
        # Fix round 1, M6's rescue, as in the b1 end to end: a session still running
        # when a test ends is stopped at its next boundary, not left to its budget.
        if self.runner.is_alive():
            try:
                with self.zmq_cleanup(ZmqConsole(self.pub, self.rep)) as rescue:
                    rescue.send(Stop(by="e2e-cleanup"))
            except Exception:  # noqa: BLE001 -- best-effort cleanup
                pass
        self.runner.join(timeout=30)
        self.server.close()

    def post(self, body: dict):
        return _post(self.server.address[1], body)

    def frame(self, predicate, seconds: float = 20.0):
        """The first frame this console holds for which `predicate` is true, within
        `seconds`; fails the test otherwise -- and within `LAST_FRAME_S` once `wlx
        run` has ended, since no frame comes after that: a session a mutant ended
        early fails its test then, rather than after the full wait."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            latest = self.server.hub.snapshot(on_box=True, stale_after_s=30.0)[0]
            if latest is not None and predicate(latest):
                return latest
            if not self.runner.is_alive():
                deadline = min(deadline, time.monotonic() + LAST_FRAME_S)
            time.sleep(0.01)
        ended = "" if self.runner.is_alive() else "; wlx run had ended"
        raise AssertionError(f"no frame within {seconds} s satisfied {predicate}{ended}")

    def ended(self):
        return self.frame(lambda f: f.stop_kind is not None)

    def controls(self) -> list[dict]:
        path = Path(self.root) / self.session_id / "expcontroller" / "controls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def finished(self) -> None:
        self.runner.join(timeout=30)
        assert not self.runner.is_alive(), "wlx run did not finish"
        assert "exit_code" in self.result, "wlx run's thread raised before main() returned"


def test_e2e_a_setting_is_staged_then_applied_at_the_next_trial(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "set", "by": "jake", "name": "fix_hold", "value": 0.4})[0] == 200
        staged = run.frame(lambda f: any(s.name == "fix_hold" for s in f.staged))
        applied = run.frame(
            lambda f: not f.staged
            and any(p.name == "fix_hold" and p.value == 0.4 for p in f.params)
        )
        assert applied.trial_index > staged.trial_index - 1
        assert any(
            c.kind == "set" and c.by == "jake (box, unverified)" and c.said.startswith("fix_hold 0.30 → 0.40")
            for c in applied.controls
        )
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()


def test_e2e_a_malformed_setting_is_refused_on_the_feed_and_the_session_runs_on(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """M8, end to end: a word sent for a numeric parameter is a categorical choice on
    the wire, so it reaches the rig, where it once raised `TypeError` out of
    `bounds._finite` and ended the session. Now it is a refusal with a sentence on the
    feed, and trials go on."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        before = run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "set", "by": "jake", "name": "fix_hold", "value": "abc"})[0] == 200
        refused = run.frame(lambda f: any(r.name == "fix_hold" for r in f.refusals))
        (refusal,) = [r for r in refused.refusals if r.name == "fix_hold"]
        assert refusal.by == "jake (box, unverified)"
        assert "'fix_hold' takes a number (s)" in refusal.why
        run.frame(lambda f: f.trial_index > refused.trial_index + 2)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        assert run.ended().stop_kind == "operator"
        assert before.stop_kind is None
    run.finished()


def test_e2e_pause_holds_the_trial_count_keeps_the_clock_and_resume_continues(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 2)
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        first = run.frame(lambda f: f.paused_at is not None)
        later = run.frame(
            lambda f: f.paused_at is not None
            and f.out_of_cage_seconds >= first.out_of_cage_seconds + 1.0
        )
        assert later.trial_index == first.trial_index, "a trial ran while paused"
        assert run.post({"kind": "resume", "by": "sam"})[0] == 200
        run.frame(lambda f: f.paused_at is None and f.trial_index > first.trial_index)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()
    codes = run.cards[0].codes
    assert codes.count(PAUSE_CODE) == 1 and codes.count(RESUME_CODE) == 1
    assert codes.index(RESUME_CODE) == codes.index(PAUSE_CODE) + 1
    kinds = [row["kind"] for row in run.controls()]
    assert kinds == ["pause", "resume", "stop"]


def test_e2e_the_limit_ends_a_session_paused_in_front_of_it(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §5.4 and human review item 1: pause, and the out-of-cage limit still
    arrives and ends the session, mid-pause. A bounded config here sets the limit a
    few seconds past the departure `wlx run` is given (the current minute)."""
    now = time.localtime()
    departure = time.mktime((*now[:5], 0, 0, 0, -1))
    limit = time.time() - departure + 6.0
    bounds = tmp_path / "short_bounds.py"
    bounds.write_text(
        "from wl_expcontroller.bounds import Bounds, Ceiling, Floor\n"
        "BOUNDS = Bounds(subject='REFERENCE', ceilings={"
        "'reward_correct': Ceiling(value=0.05, maximum=10.0, unit='mL'), "
        f"'out_of_cage': Ceiling(value={limit!r}, maximum=43200.0, unit='s')}}, "
        "minima={'daily_fluid': Floor(value=20.0, unit='mL')})\n",
        encoding="utf-8",
    )
    with _Session(tmp_path, monkeypatch, zmq_cleanup, bounds=bounds, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        paused = run.frame(lambda f: f.paused_at is not None)
        ended = run.ended()
    run.finished()

    assert ended.stop_kind == "limit"
    assert ended.trial_index == paused.trial_index, "the limit ended it while paused"
    assert ended.out_of_cage_seconds >= limit


def test_e2e_a_mark_is_strobed_in_its_trial_and_recorded_with_three_instants_and_a_note(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §5.4: a mark puts `OPERATOR_MARK` into the recorded event stream -- the
    card `wlx run` strobed onto -- where its stamp says it arrived, and the record
    holds its three instants, their gaps, and its note."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 2)
        pressed = time.time()
        status, signal = run.post({"kind": "mark", "by": "jake", "pressed_at": pressed})
        assert (status, signal["status"]) == (200, "signaled")
        run.frame(lambda f: any(c.kind == "mark" for c in f.controls))
        assert run.post({"kind": "note", "by": "jake", "mark": signal["mark"], "note": "sneeze"})[0] == 200
        run.frame(lambda f: any(c.kind == "note" for c in f.controls))
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()

    stamp, note, stop = run.controls()
    assert (stamp["kind"], stamp["mark"], stamp["number"]) == ("mark", signal["mark"], 1)
    assert (stop["kind"], stop["by"]) == ("stop", "jake (box, unverified)")
    codes = run.cards[0].codes
    assert codes.count(MARK_CODE) == 1
    starts = [i for i, code in enumerate(codes) if code == FIX_ON]
    at = codes.index(MARK_CODE)
    trial_start = starts[stamp["trial_index"]]
    if stamp["frame"] is None:
        assert at < trial_start, "stamped between trials, strobed before the trial"
        assert stamp["trial_index"] == 0 or at > starts[stamp["trial_index"] - 1]
    else:
        trial_end = next(i for i in range(trial_start, len(codes)) if codes[i] in MARKERS)
        assert trial_start < at < trial_end, "strobed inside the trial its stamp names"
    assert note["note"] == "sneeze" and note["by"] == "jake (box, unverified)"
    assert note["pressed_at"] == pressed
    assert pressed <= note["received_at"] <= note["stamped_at"] + 60.0
    assert note["received_after_pressed_s"] == pytest.approx(note["received_at"] - pressed)
    assert note["stamped_after_received_s"] == pytest.approx(
        note["stamped_at"] - note["received_at"]
    )


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"trials": 3}, "scheduled stop (after trial {target}) set by jake (box, unverified)"),
        ({"ml": 0.1}, "scheduled stop (after 0.1 mL this session) set by jake (box, unverified)"),
        ({"at": "00:00"}, "scheduled stop (at 00:00{day}) set by jake (box, unverified)"),
    ],
    ids=["trials", "fluid", "clock"],
)
def test_e2e_each_kind_of_scheduled_stop_ends_the_session_with_its_reason(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup, body, reason
):
    """Spec §5.4. The clock kind's next occurrence is made a quarter second away
    (`taskd._next_occurrence`, in this process, where `wlx run` runs): a real minute
    is too long for the suite, and what that function computes is pinned on its own
    in `tests/test_taskd.py`. Everything else is real -- the page's POST, `wlx
    serve`'s command thread, the wire, and the session's anchored clock."""
    from wl_expcontroller import taskd

    monkeypatch.setattr(taskd, "_next_occurrence", lambda hhmm, wall: wall + 0.25)
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        running = run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "schedule", "by": "jake", **body})[0] == 200
        ended = run.ended()
    run.finished()

    # A schedule that fired is spent, so the frames may never have shown it held;
    # the record has what it was.
    schedule, fired = run.controls()
    assert (schedule["kind"], fired["kind"]) == ("schedule", "scheduled_stop")
    day = schedule["said"][len("at 00:00"):] if "at" in body else ""
    target = int(schedule["target"]) if "trials" in body else None
    assert ended.stop_kind == "operator"
    assert ended.stopped_because == reason.format(target=target, day=day)
    assert fired["by"] == "jake (box, unverified)"
    assert ended.scheduled_stop is None
    assert running.stop_kind is None


def test_e2e_cancel_removes_the_scheduled_stop(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        running = run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "schedule", "by": "jake", "trials": 30})[0] == 200
        held = run.frame(lambda f: f.scheduled_stop is not None)
        assert run.post({"kind": "cancel", "by": "sam"})[0] == 200
        run.frame(lambda f: f.scheduled_stop is None and f.trial_index > held.trial_index)
        past = run.frame(lambda f: f.trial_index > held.scheduled_stop.target + 5)
        assert past.stop_kind is None, "a cancelled schedule still stopped the session"
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()
    assert running.scheduled_stop is None


def test_e2e_a_write_from_elsewhere_is_refused_and_the_session_never_sees_it(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Spec §5.4: a write from a non-loopback peer, or to an unknown `Host`, is
    refused -- and never reaches the rig: no control, no refusal, no strobe."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        port = run.server.address[1]
        wrong_host = _post(port, {"kind": "pause", "by": "mallory"}, {"Host": "evil.example"})
        with monkeypatch.context() as patch:
            patch.setattr(serve, "on_box", lambda host: False)
            not_the_box = _post(port, {"kind": "pause", "by": "mallory"})
        after = run.frame(lambda f: f.trial_index >= 3)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()

    assert wrong_host[0] == 421
    assert not_the_box == (403, {"status": "refused", "said": CONTROLS_AT_THE_BOX})
    assert after.paused_at is None and after.refusals == () and after.controls == ()
    assert PAUSE_CODE not in run.cards[0].codes


def test_e2e_with_taskd_gone_the_page_is_told_not_delivered(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
        run.finished()
        status, answer = run.post({"kind": "pause", "by": "jake"})
        mark_status, mark = run.post({"kind": "mark", "by": "jake"})

    assert status == 504
    assert answer["said"] == f"not delivered: no rig is connected on {run.rep}"
    assert mark_status == 504
    assert mark["said"] == f"not delivered: no rig is listening for marks on {run.mark}"


def test_e2e_wlx_serve_restarted_while_paused_shows_it_paused_and_can_resume(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """Review Focus 5: the pause is held by `taskd`, so a `wlx serve` restarted while
    the session is paused picks it up paused -- its page offers *resume* -- and the
    resume it sends continues the session."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        run.frame(lambda f: f.trial_index >= 1)
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        paused = run.frame(lambda f: f.paused_at is not None)
        run.server.close()

        run.server = run.serve()
        again = run.frame(lambda f: f.paused_at is not None)
        with _stream(run.server.address[1]) as response:
            first = next(_events(response))
        assert 'data-cmd="resume"' in first["frags"]["controls"]
        assert 'data-state="paused"' in first["frags"]["state"]
        assert again.trial_index == paused.trial_index
        assert run.post({"kind": "resume", "by": "jake"})[0] == 200
        run.frame(lambda f: f.paused_at is None and f.trial_index > paused.trial_index)
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        run.ended()
    run.finished()
```

- [ ] **Step 2: Run them — they pass on arrival — and show they can fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py -k e2e`
Expected: **12 passed** — this task's tests; b1's end to end has another name. They pass on arrival because Tasks 1–11 built the path, so that they *can* fail is shown now rather than trusted. Break `Server.dispatch` by hand, run them, and put it back:

```bash
python - <<'EOF'
from pathlib import Path
p = Path("wl_expcontroller/serve.py")
s = p.read_text()
assert s.count("        return self._commands.submit(_delivered(request))") == 1
p.write_text(s.replace(
    "        return self._commands.submit(_delivered(request))",
    '        return not_delivered("a deliberately broken dispatch")',
))
EOF
WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py -k e2e
git checkout -- wl_expcontroller/serve.py
git status --short
```

Expected: **12 failed**, every one of this task's tests by name; then `git status` shows only `tests/test_serve.py` modified — `serve.py` is back as it was.

- [ ] **Step 3: Run them three times, then the suite**

Run: `for i in 1 2 3; do WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py -k e2e; done`
Expected: 12 passed each time.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1361 passed**.

Then the mutation that once ran these tests past the harness's limit, read by its line. Do nothing else in the worktree while it runs:

Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/taskd.py _command`
Expected: `baseline: 1361 passed`; then `caught    _command    68 failed, 1293 passed … <- tests/…`, naming tests — **not** `caught … timed out after 300s (mutation hangs)`, which the harness also prints as caught and which is no test noticing; then `restored: 1361 passed`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_serve.py
git commit -m "Drive a simulated session through the page's own commands, end to end"
```

---

### Task 13: A manual reward during a pause

**Why:** the PI approved this plan on 2026-09-28 with one change: "I want to be able to give manual rewards during pause." Asked how much one press gives, he chose "Same as a correct trial" (Plan decision 16). So while the session is held paused at a trial boundary, one press of the page's *give reward* is one delivery of the bounded config's `reward_correct` — at the value it holds, nothing new set — through the path a task's reward takes, `welfare.Rig.reward` → `Welfare.deliver`: charged before the valve opens, and counted in `commanded`, `deliveries` and `last_delivery_wall_at`, so it is on the fluid total, the time since the last reward, and a "stop after X mL". `MANUAL_REWARD` (4134) is strobed before it, as `REWARD_COMMANDED` precedes a task's reward, and `controls.jsonl` records it. At any other time it is refused with a sentence and the session goes on; any-time manual reward stays in slice b5 (spec §4.0). S9 and S6 §4 already asked for this shape: a console reward "commands through the normal path", so it "appears as commanded *and* delivered", told apart from a panel press.

**Which function checks "stop after X mL", and why:** `Session._ends`, unchanged. `_hold`'s pass is wait → drain → publish → `_ends`; the reward is given inside the drain, and `_ends` — the one place the loop asks `welfare.must_stop` and then the scheduled stop, `welfare.session_total() >= target` (Tasks 5 and 7) — is asked before the pass ends. So a manual reward that reaches the target ends the session in that pass, as a scheduled stop, without waiting for a resume, and the out-of-cage limit is still asked first. A check inside `_manual_reward` would be a second copy of the schedule's rule, the thing Plan decision 13 put `_ends` on the welfare-critical list to prevent. `test_a_manual_reward_that_reaches_a_fluid_stop_ends_the_paused_session_in_that_pass` pins it.

**"Only while paused" means held, and only `_hold` can say so.** A pause is taken in the loop's boundary drain and held from the next `_hold` pass, so `_command` gains `held`, true only for the commands `_hold` drains. A reward in the same drain as its pause — pressed after the pause and before the boundary held it — is refused; so is one while trials run, one after a `Stop` or a `Resume` ahead of it in the drain, and one after the session has ended (`_command`'s post-loop refusal). The page's button is live only on a frame with `paused_at`, and that frame is published after the pause is taken, so a press from the page is drained by `_hold`.

**Nothing re-sends a command, and a test makes sure nothing starts to.** `ZmqCommands.deliver` sends once and, on a reply timeout, closes its socket, opens another, and raises (Task 4); an `Outbox` runs each job's work once (Task 11); the page's `fetch` is never retried. So there is nothing to exempt a reward from. What changes is the answer: a reward handed over and not acknowledged may have been given, so `deliver` raises that case as `link.Unacknowledged`, a `NotDelivered`, and `wlx serve` answers `serve.REWARD_UNKNOWN` — *unknown*, check the fluid total before pressing again — never *not delivered*, which would invite the second press. `test_a_reward_the_rig_takes_and_never_acknowledges_is_unknown_and_sent_once` puts a ROUTER socket where the rig is, which reads every message and answers none, and counts one reward command on the wire. The page holds its button from the click until the answer or the failure.

**Frames are still published while paused**: `_hold` publishes once a pass, after its drain, so the frame after a reward carries the new fluid total, still paused. Both the session's test and the end to end read it from that frame.

**Files:**
- Modify: `tasks/allocation.py` (4134)
- Modify: `wl_expcontroller/link.py` (`Pause`'s docstring; `ManualReward`; `Command`; `_encode_command`, `_decode_command`; `Unacknowledged`; `ZmqCommands`' docstring and `deliver`)
- Modify: `wl_expcontroller/taskd.py` (`MANUAL_REWARD_ENTRY`; `controls`' docstring; `_hold`; `_manual_reward`; `_command`'s `held`)
- Modify: `wl_expcontroller/record.py` (`CONTROLS`' docstring)
- Modify: `wl_expcontroller/serve.py` (`_SHAPES`, `parse_command`; `REWARD_SENT`, `REWARD_UNKNOWN`, `_rewarded`; `Server.dispatch`)
- Modify: `wl_expcontroller/web.py` (`REWARD_ONLY_PAUSED`, `_reward_button`, `_reward_answer`, `_controls`; the script's `post`, `swap`, `holdReward`, `reward`, `command`)
- Test: `tests/test_link.py`, `tests/test_taskd.py`, `tests/test_web.py`, `tests/test_serve.py`

**Interfaces:**
- Consumes: Task 4's `ZmqCommands`, `NotDelivered`; Task 5's `_hold`, `_command`, `_control`, `_code`, `_refuse`, `_Scripted`, `_walled`, `_controls_rows`, `PAUSE_CODE`, `RESUME_CODE`; Task 6's `_control(..., at=)`; Task 7's `_ends(index)`, `_scheduled_at_trial`; Task 10's `_controls`, `_off`, `_clock_time` and the script's `post`, `swap`, `command`; Task 11's `parse_command`, `Outbox`, `Server.dispatch`, `_post`, `_rig`; Task 12's `_Session`, `FIX_ON`; `welfare.Rig.reward` and `Welfare.deliver`, unchanged.
- Produces:
  - The allocation's `MANUAL_REWARD` (4134).
  - `link.ManualReward(by)`, `KIND` `"reward"`; `link.Unacknowledged(NotDelivered)`, raised by `ZmqCommands.deliver` on a reply timeout.
  - `taskd.MANUAL_REWARD_ENTRY = "reward_correct"`; `Session._command(command, index, held=False)`; `Session._manual_reward(by, index, held)`. Control kind `reward`; its record row adds `ml` and `entry`.
  - `serve.REWARD_SENT`, `serve.REWARD_UNKNOWN`, `serve._rewarded(command)`; `POST /commands` takes `{"kind": "reward", "by"}` and nothing else for it.
  - `web.REWARD_ONLY_PAUSED`; `web._reward_button`, `web._reward_answer`; the controls fragment's `<button … data-cmd="reward">give reward</button>`.

- [ ] **Step 1: Write the failing tests**

The wire, in `tests/test_link.py`:

In `tests/test_link.py`, replace:

```python
    FrameError,
    Mark,
    NotDelivered,
```

with:

```python
    FrameError,
    ManualReward,
    Mark,
    NotDelivered,
```

In `tests/test_link.py`, replace:

```python
    Telemetry,
    ZmqCommands,
```

with:

```python
    Telemetry,
    Unacknowledged,
    ZmqCommands,
```

Append to `tests/test_link.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a, amended 2026-09-28 (PI): a manual reward during a pause
# ---------------------------------------------------------------------------


def test_a_manual_reward_crosses_the_wire_as_one_press_with_who_pressed_it(zmq_cleanup):
    """PI, 2026-09-28: one press gives one correct-trial reward. The command carries who
    pressed it and nothing else -- the size is the bounded config's `reward_correct`,
    read by the rig, so nothing a console sends can set it -- and it crosses a real
    socket like every other control."""
    command = ManualReward(by="jake (box, unverified)")
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint))

    console.send(command)

    assert ManualReward.KIND == "reward"
    assert _decode_command(_encode_command(command)) == command
    assert _drain_until(link) == [command]


@pytest.mark.parametrize("by", [None, "", 3])
def test_a_manual_reward_that_does_not_say_who_pressed_it_is_refused(by):
    """S9a §6, as for every command: a reward nobody pressed is refused by its kind."""
    fields = {"kind": "reward"}
    if by is not None:
        fields["by"] = by

    with pytest.raises(CommandRefused) as refused:
        _decode_command(_packed(**fields))

    assert refused.value.name == "reward"
    assert "who sent it" in refused.value.why


def test_a_command_the_rig_took_and_never_acknowledged_is_told_from_one_never_sent(
    zmq_cleanup,
):
    """No accidental doubles (PI, 2026-09-28). A command handed to a connected rig that
    does not acknowledge it may still be applied, so it raises `Unacknowledged` -- a
    `NotDelivered`, so every caller that catches that still does -- and `wlx serve`
    answers a reward in that state *unknown*. A command that never left, with no rig
    connected, is a plain `NotDelivered`: nothing was given."""
    link = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    took = zmq_cleanup(ZmqCommands(link.rep_endpoint, reply_timeout_s=0.2))
    probe = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    gone = probe.rep_endpoint
    probe.close()
    never = zmq_cleanup(ZmqCommands(gone, reply_timeout_s=30.0, connect_timeout_s=0.1))

    with pytest.raises(Unacknowledged, match="did not acknowledge it within 0.2 s"):
        took.deliver(ManualReward(by="jake"))
    with pytest.raises(NotDelivered, match="no rig is connected") as not_sent:
        never.deliver(ManualReward(by="jake"))

    assert issubclass(Unacknowledged, NotDelivered)
    assert not isinstance(not_sent.value, Unacknowledged)
```

The session, in `tests/test_taskd.py`:

In `tests/test_taskd.py`, replace:

```python
    CancelScheduledStop,
    Mark,
```

with:

```python
    CancelScheduledStop,
    ManualReward,
    Mark,
```

Task 5's test of spec §5.5 item 1 says what the amended item says:

In `tests/test_taskd.py`, replace:

```python
    """Human review item 1 (spec §5.5): while paused, nothing is rewarded. No trial
    runs, so no `Reward` action reaches the pump, and the session's fluid stands
    still. Paused after six trials, so what stands still is not zero."""
```

with:

```python
    """Human review item 1 (spec §5.5, amended 2026-09-28): while paused, the task
    rewards nothing. No trial runs, so no `Reward` action reaches the pump, and with
    no manual reward pressed the session's fluid stands still. Paused after six
    trials, so what stands still is not zero."""
```

Append to `tests/test_taskd.py`:

```python


# ---------------------------------------------------------------------------
# P4d-2b b2a, amended 2026-09-28 (PI): a manual reward during a pause
# ---------------------------------------------------------------------------

#: `MANUAL_REWARD`'s code (`tasks/allocation.py`), after b2a's other three; and
#: `REWARD_COMMANDED`'s, which `fixation_detection` strobes with each reward it pays.
REWARD_CODE, TASK_REWARD_CODE = 4134, 4102


class _Watched(Pump):
    """A simulated pump that notes, as each delivery arrives, the last code the card
    had strobed: how a test tells that the strobe came before the valve."""

    def __init__(self, card) -> None:
        super().__init__()
        self.card = card
        self.strobed_before: list = []

    def deliver(self, ml: float) -> None:
        self.strobed_before.append(self.card.codes[-1] if self.card.codes else None)
        super().deliver(ml)


def _manual_rows(session: Session) -> list[dict]:
    return [row for row in _controls_rows(session) if row["kind"] == "reward"]


def test_a_manual_reward_while_paused_is_one_correct_trial_reward_through_the_tasks_path(
    tmp_path,
):
    """PI, 2026-09-28: "I want to be able to give manual rewards during pause", and one
    press is "Same as a correct trial". A `ManualReward` drained while the session is
    held is one delivery of the bounded config's `reward_correct` -- 0.15 mL here, the
    value it holds -- through `Rig.reward` and `Welfare.deliver`, the path a task's
    reward takes: `commanded`, `deliveries` and `last_delivery_wall_at` count it,
    `MANUAL_REWARD` is strobed before the valve opens, `controls.jsonl` has one row, and
    the frame published in that pass, still paused, carries the new fluid total."""
    link = _Scripted(script={1: [ManualReward(by="jake")], 2: [Resume(by="sam")]}, step=10.0)
    session, wall = _walled(tmp_path, link, trials=6)
    link.wall = wall
    pump = _Watched(session.card)
    session.welfare.pump = pump
    seen: list = []
    link.each = lambda: seen.append(
        (
            session.welfare.commanded,
            session.welfare.deliveries,
            len(pump.delivered),
            session.welfare.last_delivery_wall_at,
        )
    )
    _scheduled_at_trial(link, session, 3, Pause(by="jake"))

    session.run()

    (commanded, deliveries, delivered, _), (after, then, now, last) = seen
    assert after == pytest.approx(commanded + 0.15)
    assert (then, now) == (deliveries + 1, delivered + 1), "exactly one delivery"
    assert pump.delivered[delivered] == 0.15
    assert pump.strobed_before[delivered] == REWARD_CODE, "strobed before the valve"
    codes = session.card.codes
    assert codes.count(REWARD_CODE) == 1
    assert codes.index(PAUSE_CODE) + 1 == codes.index(REWARD_CODE) == codes.index(RESUME_CODE) - 1
    (row,) = _manual_rows(session)
    assert (row["by"], row["trial_index"]) == ("jake", 3)
    assert (row["ml"], row["entry"]) == (0.15, "reward_correct")
    assert row["at"] == last
    held = [frame for frame in link.published if frame.paused_at is not None]
    assert held[-1].fluid_session_ml == pytest.approx(after)
    assert held[-1].last_reward_at == last
    assert [c.kind for c in held[-1].controls][-1] == "reward"
    assert len((session.directory / "trials.jsonl").read_text().splitlines()) == 6


@pytest.mark.parametrize(
    ("first", "script", "said"),
    [
        ([ManualReward(by="jake")], {}, "the session is not paused"),
        (
            [Pause(by="jake"), ManualReward(by="jake")],
            {1: [Resume(by="sam")]},
            "the session's pause has not begun holding yet",
        ),
        (
            [Pause(by="jake")],
            {1: [Stop(by="sam"), ManualReward(by="jake")]},
            "the session is stopping (stopped by sam)",
        ),
        (
            [Pause(by="jake")],
            {1: [Resume(by="sam"), ManualReward(by="jake")]},
            "the session is not paused",
        ),
    ],
    ids=["while-running", "pause-not-yet-held", "after-a-stop", "after-a-resume"],
)
def test_a_manual_reward_at_any_other_time_is_refused_and_nothing_is_given(
    tmp_path, first, script, said
):
    """Only while paused, meaning held at the boundary (Plan decision 16). Pressed while
    trials run; in the same drain as the pause, before the boundary holds it; or after
    a stop or a resume ahead of it in the paused loop's drain -- refused with a
    sentence, nothing strobed, nothing given, and the session goes on. Every delivery
    left is a trial's, each with its `REWARD_COMMANDED`."""
    link = _Scripted(script=script)
    for command in first:
        link.queue(command)
    session, wall = _walled(tmp_path, link, trials=2)
    link.wall = wall

    session.run()

    ((name, by, why),) = [r for r in session.refusals if r[0] == "reward"]
    assert (name, by) == ("reward", "jake")
    assert said in why and "no reward was given" in why
    assert REWARD_CODE not in session.card.codes
    assert _manual_rows(session) == []
    assert session.welfare.deliveries == session.card.codes.count(TASK_REWARD_CODE)


def test_after_the_loop_a_manual_reward_is_refused_and_nothing_is_given(tmp_path):
    """After the session has ended, a reward is refused with the post-loop sentence,
    as every command is then, and the fluid total does not move."""
    link, wall = Simulated(), _Wall(WALL_NOW)
    session = _fixed_and_run(tmp_path, link, wall)
    given = (session.welfare.commanded, session.welfare.deliveries)
    link.queue(ManualReward(by="jake"))

    thread, give_up = _awaiting(session)
    try:
        assert _until(lambda: len(session.refusals) == 1)
    finally:
        give_up.set()
        thread.join(timeout=2)

    ((name, by, why),) = session.refusals
    assert (name, by) == ("reward", "jake")
    assert "the session has ended" in why
    assert (session.welfare.commanded, session.welfare.deliveries) == given
    assert REWARD_CODE not in session.card.codes


def test_a_manual_reward_with_no_reward_correct_in_the_bounded_config_is_refused(
    tmp_path,
):
    """One press is "Same as a correct trial": the bounded config's `reward_correct`. A
    config without that entry gives a press no size, so it is refused naming the entry
    -- and **never** paid from another entry, even one that is there."""
    bounds = Bounds(
        subject="A",
        ceilings={
            "reward_large": Ceiling(value=0.3, maximum=0.4, unit="mL"),
            "out_of_cage": Ceiling(value=800.0, maximum=100_000.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )
    link = _Scripted(script={1: [ManualReward(by="jake")], 2: [Stop(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, bounds=bounds)
    link.wall = wall

    session.run()

    ((name, by, why),) = session.refusals
    assert (name, by) == ("reward", "jake")
    assert "has no 'reward_correct' entry" in why
    assert "never taken from another entry" in why
    assert session.welfare.deliveries == 0 and session.pump.delivered == []
    assert REWARD_CODE not in session.card.codes


def test_a_manual_reward_is_refused_when_the_allocation_cannot_mark_it(tmp_path):
    """A reward the recording could not show is refused, as a pause is: without
    `MANUAL_REWARD` a delivery in the event stream would look like nothing, or like a
    panel press."""
    from dataclasses import replace

    link = _Scripted(script={1: [ManualReward(by="jake")], 2: [Resume(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=2)
    link.wall = wall
    session.allocation = replace(
        session.allocation,
        task_events={
            code: name
            for code, name in session.allocation.task_events.items()
            if name != "MANUAL_REWARD"
        },
    )

    session.run()

    ((name, _, why),) = session.refusals
    assert name == "reward"
    assert "no MANUAL_REWARD event code" in why
    assert session.welfare.deliveries == session.card.codes.count(TASK_REWARD_CODE)


def test_a_manual_reward_that_reaches_a_fluid_stop_ends_the_paused_session_in_that_pass(
    tmp_path,
):
    """Items 1 and 2 of spec §5.5 together (amended 2026-09-28): a manual reward counts
    toward "stop after X mL". `_hold` gives it in its drain and asks `_ends` before the
    pass is over -- the pass that asks the out-of-cage limit -- so the session ends
    there, as a scheduled stop, without waiting for a resume."""
    link = _Scripted(script={1: [ManualReward(by="jake")]})
    link.queue(ScheduleStop(kind="fluid", value=0.15, by="sam"))
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall

    session.run()

    assert session.stop_kind == "operator"
    assert session.stopped_because == "scheduled stop (after 0.15 mL this session) set by sam"
    assert len(link.waits) == 1, "it ended in the pass that gave the reward"
    assert session.welfare.session_total() == pytest.approx(0.15)
    assert [row["kind"] for row in _controls_rows(session)] == [
        "schedule", "pause", "reward", "scheduled_stop",
    ]
    assert not (session.directory / "trials.jsonl").read_text().strip(), "no trial ran"
    assert link.published[-1].stop_kind == "operator"


def test_a_reward_size_staged_while_paused_is_not_a_manual_rewards_until_trials_resume(
    tmp_path,
):
    """A setting staged while paused applies when trials resume (spec §5.1), so a
    manual reward given before then is the size a correct trial pays now -- the applied
    `reward_correct` -- and the staged size is the next trial's."""
    link = _Scripted(
        script={
            1: [SetParameter(name="reward_correct", value=0.3, by="sam")],
            2: [ManualReward(by="jake")],
            3: [Resume(by="jake")],
        }
    )
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link, trials=1)
    link.wall = wall

    session.run()

    assert session.pump.delivered[0] == 0.15
    (row,) = _manual_rows(session)
    assert row["ml"] == 0.15
    assert _parameter_changes(session)[0]["now"] == 0.3


def test_a_pump_that_fails_a_manual_reward_faults_the_session_as_a_tasks_would(tmp_path):
    """`welfare.Rig` swallows nothing for a task's reward, and a manual reward takes
    the same path: a pump that will not answer ends the session as a fault, published,
    with the reward charged, since it was charged before the valve opened."""

    class _Broken(Pump):
        def deliver(self, ml: float) -> None:
            raise RuntimeError("the pump did not answer")

    link = _Scripted(script={1: [ManualReward(by="jake")]})
    link.queue(Pause(by="jake"))
    session, wall = _walled(tmp_path, link)
    link.wall = wall
    session.welfare.pump = _Broken()

    with pytest.raises(RuntimeError, match="the pump did not answer"):
        session.run()

    assert session.stop_kind == "fault"
    assert link.published[-1].stop_kind == "fault"
    assert (session.welfare.commanded, session.welfare.deliveries) == (0.15, 1)
    assert session.card.codes[-1] == REWARD_CODE
```

The page, in `tests/test_web.py`:

In `tests/test_web.py`, replace:

```python
    NO_MARK_ENDPOINT,
    font_bytes,
```

with:

```python
    NO_MARK_ENDPOINT,
    REWARD_ONLY_PAUSED,
    font_bytes,
```

Task 10's running-session test keeps its three buttons, and now sees the fourth greyed:

In `tests/test_web.py`, replace:

```python
    assert '<button type="button" class="btn danger" data-cmd="stop">stop…</button>' in controls
    assert "disabled" not in controls
```

with:

```python
    assert '<button type="button" class="btn danger" data-cmd="stop">stop…</button>' in controls
    # Every control but the manual reward, which waits for a pause (Task 13).
    assert controls.count(" disabled") == 1
    assert 'data-cmd="reward" disabled' in controls
```

Append to `tests/test_web.py`:

```python


# --- P4d-2b b2a, amended 2026-09-28 (PI): a manual reward during a pause -------------


def test_the_reward_button_is_live_only_while_paused_and_greyed_otherwise():
    """PI, 2026-09-28: a manual reward during a pause. The button works only while the
    session is paused (`paused_at`), and otherwise says why: greyed with its reason
    while trials run, with the §2 sentence away from the box, and gone once the
    session has ended. One button and no key: a click is one command."""
    at = 1_700_000_030.0
    paused = _controls(paused_at=at)
    running = _controls()
    lan = fragments(frame(paused_at=at), view(on_box=False, can_write=False))["controls"]
    ended = fragments(frame(**STATES["returned"], paused_at=at), view())["controls"]

    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in paused
    assert (
        f'<button type="button" class="btn" data-cmd="reward" disabled '
        f'title="{REWARD_ONLY_PAUSED}">give reward</button>'
    ) in running
    assert REWARD_ONLY_PAUSED == (
        "a manual reward is given only while the session is paused: pause first"
    )
    assert re.search(r'data-cmd="reward" disabled title="[^"]+">give reward', lan)
    assert CONTROLS_AT_THE_BOX in lan
    assert "give reward" not in ended
    assert 'k === "r"' not in _SCRIPT, "no key gives a reward"


def test_while_paused_the_controls_show_the_fluid_total_and_what_the_last_press_did():
    """The answer to a press, from the frames the rig publishes while paused: the
    session's fluid total, the newest reward given with its size, and the newest
    refused with the rig's sentence -- *last*, since a refusal carries no time, as on
    a parameter card. Escaped like every string from telemetry."""
    at = 1_700_000_035.0
    controls = _controls(
        paused_at=1_700_000_030.0,
        fluid_session_ml=1.4,
        controls=(
            Control(
                "reward",
                "jake (box, unverified)",
                at,
                "0.15 mL of reward_correct, given while paused before trial 40",
            ),
        ),
        refusals=(Refused(name="reward", by="sam", why="the session is <not> paused"),),
    )
    clock = time.strftime("%H:%M:%S", time.localtime(at))

    assert "fluid session 1.40 mL" in controls
    assert (
        f"last given {clock}: 0.15 mL of reward_correct, given while paused before trial 40"
        in controls
    )
    assert "last refused: the session is &lt;not&gt; paused" in controls
    assert "fluid session" not in _controls(), "said beside the live button alone"


def test_the_script_sends_one_reward_per_click_and_holds_the_button_until_its_answer():
    """No accidental doubles (PI, 2026-09-28). Python cannot run the script, so its text
    is pinned where it is load-bearing: a click while a reward is on its way does
    nothing; the button is held from the click until the answer or the failure -- and
    held again whenever a frame re-renders the controls meanwhile -- and only a button
    the script held is released; the one `fetch` is never retried; and an answer the
    page lost is *unknown*, never *not delivered*, with the fluid total to check first."""
    assert "if (!button || button.disabled || rewarding) { return; }" in _SCRIPT
    assert "rewarding = true;" in _SCRIPT
    assert 'post({ kind: "reward" }, null, function () {' in _SCRIPT
    assert 'if (id === "controls") { holdReward(); }' in _SCRIPT
    assert "if (rewarding && button && !button.disabled) {" in _SCRIPT
    assert """el("controls").querySelector('[data-cmd="reward"][data-held]')""" in _SCRIPT
    assert "}).then(done);" in _SCRIPT
    assert _SCRIPT.count("fetch(") == 1
    assert (
        "unknown: this page lost wlx serve's answer, so whether the reward was given is "
        "not known, and it was not sent again; check the session's fluid total before "
        "pressing again"
    ) in _SCRIPT
```

`wlx serve`, in `tests/test_serve.py`:

In `tests/test_serve.py`, replace:

```python
    CancelScheduledStop,
    Mark,
    Pause,
```

with:

```python
    CancelScheduledStop,
    ManualReward,
    Mark,
    NotDelivered,
    Pause,
```

In `tests/test_serve.py`, replace:

```python
    Stop,
    ZmqConsole,
```

with:

```python
    Stop,
    Unacknowledged,
    ZmqConsole,
```

In `tests/test_serve.py`, replace:

```python
    QUEUE_DEPTH,
    BadCommand,
```

with:

```python
    QUEUE_DEPTH,
    REWARD_SENT,
    REWARD_UNKNOWN,
    BadCommand,
```

A reward body parses to the command, and one that tries to say how much is refused:

In `tests/test_serve.py`, replace:

```python
        ({"kind": "note", "by": "jake", "mark": 7, "note": "bubble"},
         MarkNote(mark=7, note="bubble", by="jake (box, unverified)")),
    ],
```

with:

```python
        ({"kind": "note", "by": "jake", "mark": 7, "note": "bubble"},
         MarkNote(mark=7, note="bubble", by="jake (box, unverified)")),
        ({"kind": "reward", "by": "jake"}, ManualReward(by="jake (box, unverified)")),
    ],
```

In `tests/test_serve.py`, replace:

```python
        ({"kind": "note", "by": "jake", "mark": 3, "note": "x" * 501}, "at most 500"),
    ],
```

with:

```python
        ({"kind": "note", "by": "jake", "mark": 3, "note": "x" * 501}, "at most 500"),
        ({"kind": "reward", "by": "jake", "ml": 0.5}, "a reward command takes no ml"),
    ],
```

Task 11's box stream renders a running session, whose reward button waits for a pause:

In `tests/test_serve.py`, replace:

```python
    assert 'data-cmd="pause"' in first["frags"]["controls"]
    assert "disabled" not in first["frags"]["controls"]
```

with:

```python
    controls = first["frags"]["controls"]
    assert 'data-cmd="pause"' in controls
    # Every control but the manual reward, which waits for a pause (Task 13).
    assert controls.count(" disabled") == 1
    assert 'data-cmd="reward" disabled' in controls
```

Append to `tests/test_serve.py`:

```python


# --- P4d-2b b2a, amended 2026-09-28 (PI): a manual reward during a pause ---------------

#: `MANUAL_REWARD`'s code (`tasks/allocation.py`), after b2a's other three.
MANUAL_REWARD_CODE = 4134
#: `tasks/twelve_hour_bounds.py`'s `reward_correct`: what one press gives these sessions.
REWARD_ML = 0.05


class _Answers:
    """A command sender whose `deliver` records what it was handed and raises `raised`,
    or returns when that is `None`."""

    def __init__(self, raised: Exception | None) -> None:
        self.raised = raised
        self.sent: list = []

    def deliver(self, command) -> None:
        self.sent.append(command)
        if self.raised is not None:
            raise self.raised


@pytest.mark.parametrize(
    ("raised", "answer"),
    [
        (None, (200, {"status": "sent", "said": REWARD_SENT})),
        (
            Unacknowledged("not delivered: the rig did not acknowledge it within 15 s"),
            REWARD_UNKNOWN,
        ),
        (RuntimeError("socket gone"), REWARD_UNKNOWN),
        (
            NotDelivered("not delivered: no rig is connected on tcp://127.0.0.1:5572"),
            (
                504,
                {
                    "status": "not_delivered",
                    "said": (
                        "not delivered: no rig is connected on tcp://127.0.0.1:5572; "
                        "no reward was given"
                    ),
                },
            ),
        ),
    ],
    ids=["acknowledged", "unacknowledged", "failed-after-handing-over", "never-sent"],
)
def test_a_rewards_answer_is_sent_unknown_or_not_given_and_it_is_delivered_once(
    raised, answer
):
    """No accidental doubles (PI, 2026-09-28). A reward the rig acknowledged is *sent*;
    one it took and did not acknowledge -- or one whose send failed in a way that
    cannot say whether it went -- is *unknown*, never *not delivered*, which would
    invite the press that doubles it; only one that never left `wlx serve` is *not
    delivered*, and says no reward was given. Each is handed to the sender once."""
    sender = _Answers(raised)

    assert serve._rewarded(ManualReward(by="jake"))(sender) == answer
    assert sender.sent == [ManualReward(by="jake")]


def test_a_reward_the_rig_takes_and_never_acknowledges_is_unknown_and_sent_once(
    zmq_cleanup, server_cleanup
):
    """No accidental doubles, on real sockets (PI, 2026-09-28). The rig here is a ROUTER
    socket, which reads every message and answers none, so it sees each one `wlx
    serve` sends: one press is one POST and one reward command on the wire, and after
    the reply timeout the page is told *unknown* and nothing sends it again. If a
    retry is ever added to the command path, this is where it doubles a reward."""
    import zmq

    from wl_expcontroller.link import _decode_command

    telemetry = _rig(zmq_cleanup)
    ctx = zmq.Context()
    rig = ctx.socket(zmq.ROUTER)
    try:
        rig.setsockopt(zmq.LINGER, 0)
        port = rig.bind_to_random_port("tcp://127.0.0.1")
        server = server_cleanup(
            Server(
                sub=telemetry.pub_endpoint,
                req=f"tcp://127.0.0.1:{port}",
                http=("127.0.0.1", 0),
                token=TOKEN,
                reply_timeout_s=0.3,
            )
        )
        server.start()
        try:
            answer = _post(server.address[1], {"kind": "reward", "by": "jake"})
            seen: list = []
            # Several reply timeouts, and the command thread's reset, after the answer.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if rig.poll(50, zmq.POLLIN):
                    seen.append(rig.recv_multipart())
        finally:
            server.close()
    finally:
        rig.close(linger=0)
        ctx.term()

    assert answer == REWARD_UNKNOWN
    assert [_decode_command(frames[-1]) for frames in seen] == [
        ManualReward(by="jake (box, unverified)")
    ]


def test_e2e_a_reward_pressed_while_paused_is_one_correct_trial_reward_on_the_record(
    tmp_path, monkeypatch, zmq_cleanup, server_cleanup
):
    """PI, 2026-09-28, end to end. While trials run, the page's *give reward* is greyed,
    and a press that reaches the rig anyway is refused on the feed. Paused, the button
    is live; the POST it sends crosses `wlx serve`'s command thread to the held
    session, which gives exactly one `reward_correct` -- and the next frame's fluid
    total, the page, `controls.jsonl` and the recorded event stream all show it, while
    the trial count stands still."""
    with _Session(tmp_path, monkeypatch, zmq_cleanup, cleanup=server_cleanup) as run:
        port = run.server.address[1]
        running = run.frame(lambda f: f.trial_index >= 2)
        with _stream(port) as response:
            greyed = next(_events(response))["frags"]["controls"]
        assert run.post({"kind": "reward", "by": "jake"}) == (
            200, {"status": "sent", "said": REWARD_SENT}
        )
        refused = run.frame(lambda f: any(r.name == "reward" for r in f.refusals))
        assert run.post({"kind": "pause", "by": "jake"})[0] == 200
        paused = run.frame(lambda f: f.paused_at is not None)
        with _stream(port) as response:
            live = next(_events(response))["frags"]["controls"]
        assert run.post({"kind": "reward", "by": "jake"})[0] == 200
        given = run.frame(lambda f: any(c.kind == "reward" for c in f.controls))
        with _stream(port) as response:
            shown = next(_events(response))["frags"]["controls"]
        assert run.post({"kind": "stop", "by": "jake"})[0] == 200
        ended = run.ended()
    run.finished()

    assert running.stop_kind is None
    assert 'data-cmd="reward" disabled' in greyed
    (refusal,) = [r for r in refused.refusals if r.name == "reward"]
    assert refusal.by == "jake (box, unverified)"
    assert "the session is not paused" in refusal.why
    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in live
    assert given.paused_at is not None and given.trial_index == paused.trial_index
    assert given.fluid_session_ml == pytest.approx(paused.fluid_session_ml + REWARD_ML)
    assert f"fluid session {given.fluid_session_ml:.2f} mL" in shown
    assert ended.fluid_session_ml == pytest.approx(given.fluid_session_ml)
    assert ended.trial_index == paused.trial_index
    pause, reward, stop = run.controls()
    assert (pause["kind"], reward["kind"], stop["kind"]) == ("pause", "reward", "stop")
    assert reward["by"] == "jake (box, unverified)"
    assert (reward["ml"], reward["entry"]) == (REWARD_ML, "reward_correct")
    assert reward["trial_index"] == paused.trial_index
    assert reward["at"] == given.last_reward_at
    codes = run.cards[0].codes
    assert codes.count(MANUAL_REWARD_CODE) == 1
    at = codes.index(MANUAL_REWARD_CODE)
    assert codes.index(PAUSE_CODE) < at
    assert FIX_ON not in codes[at:], "no trial ran after the pause"
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider --continue-on-collection-errors tests/test_link.py tests/test_taskd.py tests/test_web.py tests/test_serve.py`
Expected: four files fail to collect, `4 errors` — `ImportError: cannot import name 'ManualReward'` from `wl_expcontroller.link` in `test_link.py`, `test_taskd.py` and `test_serve.py`, and `cannot import name 'REWARD_ONLY_PAUSED'` from `wl_expcontroller.web` in `test_web.py`.

- [ ] **Step 3: Implement**

The event code, allocated as Task 5 allocated 4131–4133 (Plan decision 16):

In `tasks/allocation.py`, replace:

```python
        4133: "OPERATOR_MARK",
    },
```

with:

```python
        4133: "OPERATOR_MARK",
        # A person's manual reward, given while paused (PI, 2026-09-28), strobed
        # before its delivery as `REWARD_COMMANDED` precedes a task's reward, so the
        # recording tells it from a task's reward and from a panel press (S6 §4). In
        # this range for the reason the three above are; wl-exptasks owns the final
        # numbering (P4d-2b spec §5.6).
        4134: "MANUAL_REWARD",
    },
```

The command, on the wire as every simple control is:

In `wl_expcontroller/link.py`, in `Pause`, replace:

```python
    and nothing is rewarded until `Resume`, while the out-of-cage clock keeps running
    and still ends the session. `taskd.Session._hold` is what it does."""
```

with:

```python
    and the task rewards nothing until `Resume` -- a person may give a `ManualReward`
    meanwhile (PI, 2026-09-28) -- while the out-of-cage clock keeps running and still
    ends the session. `taskd.Session._hold` is what it does."""
```

In `wl_expcontroller/link.py`, replace:

```python
    KIND: ClassVar[str] = "cancel"

    by: str


Command = SetParameter | Stop | Pause | Resume | Mark | ScheduleStop | CancelScheduledStop
```

with:

```python
    KIND: ClassVar[str] = "cancel"

    by: str


@dataclass(frozen=True, slots=True)
class ManualReward:
    """One press of the page's *give reward* (P4d-2b b2a, amended 2026-09-28; the PI: "I
    want to be able to give manual rewards during pause").

    **One press, one reward, the size a correct trial pays** -- the PI's answer to how
    much, "Same as a correct trial" -- so it carries who pressed it and nothing else:
    the size is the bounded config's `reward_correct`, read by `taskd` when it gives
    the reward, and nothing a console sends can set it. `taskd.Session._manual_reward`
    gives it only while the session is held paused, and refuses it with a sentence at
    any other time. **Never sent twice**: `wlx serve` answers one it cannot confirm
    *unknown*, and nothing on the command path re-sends a command."""

    KIND: ClassVar[str] = "reward"

    by: str


Command = (
    SetParameter
    | Stop
    | Pause
    | Resume
    | Mark
    | ScheduleStop
    | CancelScheduledStop
    | ManualReward
)
```

In `wl_expcontroller/link.py`, in `_encode_command`, replace:

```python
    elif isinstance(command, (Stop, Pause, Resume, CancelScheduledStop)):
```

with:

```python
    elif isinstance(command, (Stop, Pause, Resume, CancelScheduledStop, ManualReward)):
```

In `wl_expcontroller/link.py`, in `_decode_command`, replace:

```python
    simple = {command.KIND: command for command in (Stop, Pause, Resume, CancelScheduledStop)}
```

with:

```python
    simple = {
        command.KIND: command
        for command in (Stop, Pause, Resume, CancelScheduledStop, ManualReward)
    }
```

A command handed over and not acknowledged, told apart from one never sent:

In `wl_expcontroller/link.py`, replace:

```python
REPLY_TIMEOUT_S = 15.0


class ZmqCommands:
```

with:

```python
REPLY_TIMEOUT_S = 15.0


class Unacknowledged(NotDelivered):
    """A command handed to a connected rig that did not acknowledge it within the reply
    timeout (P4d-2b b2a, amended 2026-09-28). Unlike a `NotDelivered` raised before the
    send, it **may still be applied** at the rig's next boundary. A `NotDelivered`, so
    every caller that catches that still does; `wlx serve` tells the two apart for a
    manual reward (`serve._rewarded`), which it answers *unknown*, because a reward
    that may have been given must not invite a second press."""


class ZmqCommands:
```

In `wl_expcontroller/link.py`, in `ZmqCommands`, replace:

```python
    which is why that sentence says so rather than calling it lost.
```

with:

```python
    which is why that sentence says so rather than calling it lost, and why it is
    raised as `Unacknowledged`, which a caller can tell from a command never sent.

    **Nothing here sends a command twice**, and nothing may (PI, 2026-09-28): a manual
    reward is a command, and a re-send after a timeout would double a reward the rig
    had already given. A test in `tests/test_serve.py` puts a socket that answers
    nothing where the rig is, and counts what reaches the wire.
```

In `wl_expcontroller/link.py`, in `ZmqCommands.deliver`, replace:

```python
            self._reset()
            raise NotDelivered(
```

with:

```python
            self._reset()
            raise Unacknowledged(
```

The session. The entry one press delivers:

In `wl_expcontroller/taskd.py`, replace:

```python
PAUSE_HOUSEKEEPING_S = 0.5

```

with:

```python
PAUSE_HOUSEKEEPING_S = 0.5

#: The bounded config's entry one manual reward delivers (PI, 2026-09-28): asked how
#: much one press gives, he chose "Same as a correct trial" -- `reward_correct`, the
#: entry the reference tasks pay a correct trial from, at the value it holds when the
#: press is given. **The only one**: a config without it refuses the press by name,
#: and no other entry stands in (`Session._manual_reward`).
MANUAL_REWARD_ENTRY = "reward_correct"

```

In `wl_expcontroller/taskd.py`, in `Session.controls`, replace:

```python
        -- from the tasks that add them -- `mark`, `note`, `schedule`, `cancel`,
        `scheduled_stop` and `set` (a staged setting applied). `at` is the session's anchored clock; `said` is the
```

with:

```python
        -- from the tasks that add them -- `mark`, `note`, `schedule`, `cancel`,
        `scheduled_stop`, `set` (a staged setting applied) and `reward` (a manual
        reward given while paused). `at` is the session's anchored clock; `said` is the
```

`_hold` drains the only commands a held session hears, so it alone says `held`:

In `wl_expcontroller/taskd.py`, in `Session._hold`, replace:

```python
        """**Paused** (P4d-2b spec §5.1): no trial runs and nothing is rewarded, while
        once per housekeeping pass the loop drains commands -- resume, stop, marks,
        schedules, settings -- publishes a frame, and asks `_ends` whether the
        out-of-cage limit has arrived, ending the session on it as between trials.
        The out-of-cage clock runs on the wall throughout, since nothing here stops
        it.

        **Nothing is rewarded because nothing can be**: a reward is a trial's action
        (`run.Effects.reward`), and no trial runs here. **Nothing is drawn** for the
        same reason: a stimulus is shown only by a trial, so the display the task's
        trials draw on shows its background with nothing on it (spec §5.0). There is
        no display process yet to be told so -- S4's is not built (docs/CHECKPOINT.md:
        "a frame on screen" is blocked on a panel) -- and when there is, this is the
        pause it must show; the hardware verification list says so.
```

with:

```python
        """**Paused** (P4d-2b spec §5.1): no trial runs and the task rewards nothing,
        while once per housekeeping pass the loop drains commands -- resume, stop,
        marks, schedules, settings, and a person's manual reward -- publishes a frame,
        and asks `_ends` whether the out-of-cage limit has arrived, ending the session
        on it as between trials. The out-of-cage clock runs on the wall throughout,
        since nothing here stops it.

        **The task rewards nothing because it cannot**: its reward is a trial's action
        (`run.Effects.reward`), and no trial runs here. **A person may**, one
        correct-trial reward per press (PI, 2026-09-28): the commands drained here are
        the only ones a held session hears, so only they reach `_command` with
        `held=True`, which is what `_manual_reward` gives a reward for. `_ends`, asked
        later in this same pass, then ends the session if that reward reached a
        scheduled "stop after X mL" -- without waiting for a resume, and with the
        out-of-cage limit asked first, as always.

        **Nothing is drawn**, because a stimulus is shown only by a trial: the display
        the task's trials draw on shows its background with nothing on it (spec §5.0).
        There is no display process yet to be told so -- S4's is not built
        (docs/CHECKPOINT.md: "a frame on screen" is blocked on a panel) -- and when
        there is, this is the pause it must show; the hardware verification list says
        so.
```

In `wl_expcontroller/taskd.py`, in `Session._hold`, replace:

```python
            for command in self.link.drain():
                self._command(command, index)
            publish()
```

with:

```python
            for command in self.link.drain():
                self._command(command, index, held=True)
            publish()
```

The reward itself, beside the other controls, on the path a task's reward takes:

In `wl_expcontroller/taskd.py`, replace:

```python

    def _refuse(self, name: str, by: str, why: str) -> None:
```

with:

```python

    def _manual_reward(self, by: str, index: int, held: bool) -> None:
        """**A manual reward, given while paused** (PI, 2026-09-28: "I want to be able to
        give manual rewards during pause"). Asked how much one press gives: "Same as a
        correct trial" -- one delivery of the bounded config's `MANUAL_REWARD_ENTRY`,
        at the value it holds now, **through the path a task's reward takes**:
        `welfare.Rig.reward`, then `Welfare.deliver`, which charges it before the valve
        opens and counts it in `commanded`, `deliveries` and `last_delivery_wall_at`.
        So it is on the fluid total, the time since the last reward, and a scheduled
        stop after X mL, which `_hold` asks `_ends` about in this same pass.
        `MANUAL_REWARD` is strobed first, as a task strobes `REWARD_COMMANDED` before
        its `Reward`, and one `reward` row goes to the record, with the mL given, at
        the instant the reward was commanded.

        **Only while held** (`held`: drained by `_hold`). Refused, with a sentence and
        nothing given, when the session is stopping -- a `Stop` ahead of it in the
        drain -- or not paused -- trials running, or a `Resume` ahead of it -- or
        paused in this same drain and not yet held; when the bounded config has no
        `MANUAL_REWARD_ENTRY`, which **no other entry replaces**; and when the
        allocation has no `MANUAL_REWARD` code, since the recording could not show it.
        A session that has ended refuses it in `_command`, as every command.

        **A pump fault is not caught**, as `welfare.Rig` catches none for a task's
        reward: the session ends on it as a fault, with the reward charged.

        Welfare-critical (`docs/design/architecture.md`): it delivers fluid."""
        if self.stopped_because:
            self._refuse(
                "reward",
                by,
                f"the session is stopping ({self.stopped_because}); no reward was given",
            )
            return
        if self.paused_at is None:
            self._refuse(
                "reward",
                by,
                "the session is not paused, and a manual reward is given only while it "
                "is; no reward was given",
            )
            return
        if not held:
            self._refuse(
                "reward",
                by,
                "the session's pause has not begun holding yet, and a manual reward is "
                "given only while it is; no reward was given -- press again once the "
                "page shows the session paused",
            )
            return
        if MANUAL_REWARD_ENTRY not in self.spec.bounds.ceilings:
            self._refuse(
                "reward",
                by,
                f"this subject's bounded config has no {MANUAL_REWARD_ENTRY!r} entry, so "
                f"a manual reward has no size, and it is never taken from another "
                f"entry; no reward was given",
            )
            return
        code = self._code("MANUAL_REWARD")
        if code is None:
            self._refuse(
                "reward",
                by,
                "this session's allocation has no MANUAL_REWARD event code, so the "
                "recording could not show the reward; no reward was given",
            )
            return
        ml = self.spec.bounds.value(MANUAL_REWARD_ENTRY)
        self.card.emit(code)
        self.rig.reward(MANUAL_REWARD_ENTRY)
        self._control(
            "reward",
            by,
            f"{ml:g} mL of {MANUAL_REWARD_ENTRY}, given while paused before trial {index}",
            index,
            at=self.welfare.last_delivery_wall_at,
            ml=ml,
            entry=MANUAL_REWARD_ENTRY,
        )

    def _refuse(self, name: str, by: str, why: str) -> None:
```

In `wl_expcontroller/taskd.py`, replace:

```python
    def _command(self, command, index: int) -> None:
```

with:

```python
    def _command(self, command, index: int, held: bool = False) -> None:
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
        the post-loop phase but a refusal.
        """
```

with:

```python
        the post-loop phase but a refusal.

        **`held` is true only for a command `_hold` drained** (P4d-2b b2a, amended
        2026-09-28): the session held paused at this boundary. Only a manual reward
        reads it (`_manual_reward`): the PI's manual reward is given while paused, and
        never while a pause drained in this same pass has yet to hold.
        """
```

In `wl_expcontroller/taskd.py`, in `Session._command`, replace:

```python
        if isinstance(command, _link.CancelScheduledStop):
            self._cancel(command.by, index)
            return
```

with:

```python
        if isinstance(command, _link.CancelScheduledStop):
            self._cancel(command.by, index)
            return
        if isinstance(command, _link.ManualReward):
            self._manual_reward(command.by, index, held)
            return
```

The record:

In `wl_expcontroller/record.py`, replace:

```python
#: mark's stamp and its note, a schedule, a cancellation, and a scheduled stop firing.
```

with:

```python
#: mark's stamp and its note, a schedule, a cancellation, a scheduled stop firing, and
#: a manual reward given while paused, with its mL (PI, 2026-09-28).
```

In `wl_expcontroller/record.py`, replace:

```python
#: own codes (`PAUSE`, `RESUME`, `OPERATOR_MARK`) by order and instant, or to nothing.
```

with:

```python
#: own codes (`PAUSE`, `RESUME`, `OPERATOR_MARK`, `MANUAL_REWARD`) by order and
#: instant, or to nothing.
```

`wlx serve`: the body, and the answers that never invite a second press:

In `wl_expcontroller/serve.py`, replace:

```python
    "cancel": frozenset(),
```

with:

```python
    "cancel": frozenset(),
    "reward": frozenset(),
```

In `wl_expcontroller/serve.py`, in `parse_command`, replace:

```python
        "cancel": _link.CancelScheduledStop,
    }[kind](by=by)
```

with:

```python
        "cancel": _link.CancelScheduledStop,
        "reward": _link.ManualReward,
    }[kind](by=by)
```

In `wl_expcontroller/serve.py`, replace:

```python
            "sent; try again"
        ),
    },
)
```

with:

```python
            "sent; try again"
        ),
    },
)
#: What the page is told when the rig has a manual reward (PI, 2026-09-28). Whether
#: it was given, and how much, is the changes feed's and the fluid total's to show.
REWARD_SENT = (
    "sent: the rig has the reward command; the changes feed and the fluid total show "
    "whether it was given"
)
#: What the page is told when the rig took a manual reward and did not acknowledge it
#: (PI, 2026-09-28: no accidental doubles). It may have been given, so it is neither
#: *not delivered*, which would invite a second press, nor sent again.
REWARD_UNKNOWN = (
    504,
    {
        "status": "unknown",
        "said": (
            "unknown: the rig took the reward command and did not acknowledge it, so "
            "whether the reward was given is not known, and it was not sent again; "
            "check the session's fluid total before pressing again"
        ),
    },
)
```

In `wl_expcontroller/serve.py`, in `_delivered`, replace:

```python
        return 200, {"status": "sent", "said": SENT}

    return work
```

with:

```python
        return 200, {"status": "sent", "said": SENT}

    return work


def _rewarded(command: _link.ManualReward) -> Callable[[object], tuple[int, dict]]:
    """The command thread's work for a manual reward (PI, 2026-09-28): delivered
    **once**, like every command -- nothing on this path re-sends one, and a reward
    must never be the first thing that does -- and answered without guessing. *Sent*
    when the rig acknowledged it; *unknown* when it was handed over and not
    acknowledged (`link.Unacknowledged`), or failed in a way that cannot say whether
    it went, since it may already have been given; *not delivered* only when it never
    left, saying no reward was given."""

    def work(commands) -> tuple[int, dict]:
        try:
            commands.deliver(command)
        except _link.Unacknowledged:
            return REWARD_UNKNOWN
        except _link.NotDelivered as exc:
            return not_delivered(f"{exc}; no reward was given")
        except Exception:  # noqa: BLE001 -- a reward that may have gone is unknown
            return REWARD_UNKNOWN
        return 200, {"status": "sent", "said": REWARD_SENT}

    return work
```

In `wl_expcontroller/serve.py`, in `Server.dispatch`, replace:

```python
        if isinstance(request, MarkSignal):
            return self._signal(request)
```

with:

```python
        if isinstance(request, MarkSignal):
            return self._signal(request)
        if isinstance(request, _link.ManualReward):
            # Its own answers, never a re-send (PI, 2026-09-28): see `_rewarded`.
            return self._commands.submit(_rewarded(request))
```

The page: the button, what became of the last press, and a script that sends one reward per click:

In `wl_expcontroller/web.py`, replace:

```python
NO_MARK_ENDPOINT = (
    "this console was started without the session's mark endpoint: give wlx serve "
    "--link PUB,REP,MARK, as wlx run was given it"
)
```

with:

```python
NO_MARK_ENDPOINT = (
    "this console was started without the session's mark endpoint: give wlx serve "
    "--link PUB,REP,MARK, as wlx run was given it"
)
#: Why *give reward* is greyed while trials run: the rig gives a manual reward only
#: while the session is paused (PI, 2026-09-28; `taskd.Session._manual_reward`).
REWARD_ONLY_PAUSED = "a manual reward is given only while the session is paused: pause first"
```

In `wl_expcontroller/web.py`, replace:

```python
def _controls(frame: Telemetry | None, view: View) -> str:
    """Pause or resume, mark, and stop (spec §5.2), while a session runs.

    **Pause or resume by the session's state**, never a toggle: the page sends what
    the button says, so a double click sends the same command twice, and the rig
    refuses the second with a sentence (`taskd.Session._pause`). **Stop** opens the
    page's confirm step. **Mark** is greyed on its own when this console has no mark
    endpoint. **Everywhere but the box**, every control is greyed with the §2
    sentence, which is also said beside them."""
    if frame is None:
        return '<span class="nm">controls · no session</span>'
    if frame.stop_kind is not None:
        return '<span class="nm">controls · the session has ended</span>'
    off = _off(view)
    mark_off = off or ("" if view.can_mark else f' disabled title="{_e(NO_MARK_ENDPOINT)}"')
    cmd, label = ("resume", "resume (P)") if frame.paused_at is not None else ("pause", "pause (P)")
    note = "" if view.can_write else f'<span class="nm">{CONTROLS_AT_THE_BOX}</span>'
    return (
        f'<button type="button" class="btn" data-cmd="{cmd}"{off}>{label}</button>'
        f'<button type="button" class="btn" data-cmd="mark"{mark_off}>mark (M)</button>'
        f'<button type="button" class="btn danger" data-cmd="stop"{off}>stop…</button>'
        f"{note}"
    )
```

with:

```python
def _reward_button(frame: Telemetry, view: View) -> str:
    """The manual reward's button (PI, 2026-09-28): live only while the session is
    paused, since the rig gives a manual reward only then
    (`taskd.Session._manual_reward`); greyed with `REWARD_ONLY_PAUSED` while trials
    run, and with the §2 sentence away from the box. **One button and no key**: a
    click is one command, and the script holds the button until that command's
    answer."""
    paused = frame.paused_at is not None
    off = _off(view) or ("" if paused else f' disabled title="{_e(REWARD_ONLY_PAUSED)}"')
    return f'<button type="button" class="btn" data-cmd="reward"{off}>give reward</button>'


def _reward_answer(frame: Telemetry) -> str:
    """While paused, what became of the last press (PI, 2026-09-28), from the frames
    the paused loop publishes: the session's fluid total, the newest reward given
    with its size, and the newest press refused with the rig's sentence -- *last*,
    since a refusal carries no time, as on a parameter card. Nothing while trials
    run, when the button is greyed."""
    if frame.paused_at is None:
        return ""
    said = [f"fluid session {frame.fluid_session_ml:.2f} mL"]
    given = [control for control in frame.controls if control.kind == "reward"]
    if given:
        said.append(f"last given {_clock_time(given[-1].at)}: {_e(given[-1].said)}")
    refused = [refusal for refusal in frame.refusals if refusal.name == "reward"]
    if refused:
        said.append(f"last refused: {_e(refused[-1].why)}")
    return f'<span class="nm">{" · ".join(said)}</span>'


def _controls(frame: Telemetry | None, view: View) -> str:
    """Pause or resume, mark, give reward, and stop (spec §5.2), while a session runs.

    **Pause or resume by the session's state**, never a toggle: the page sends what
    the button says, so a double click sends the same command twice, and the rig
    refuses the second with a sentence (`taskd.Session._pause`). **Stop** opens the
    page's confirm step. **Mark** is greyed on its own when this console has no mark
    endpoint, and **give reward** while trials run (`_reward_button`). **Everywhere
    but the box**, every control is greyed with the §2 sentence, which is also said
    beside them."""
    if frame is None:
        return '<span class="nm">controls · no session</span>'
    if frame.stop_kind is not None:
        return '<span class="nm">controls · the session has ended</span>'
    off = _off(view)
    mark_off = off or ("" if view.can_mark else f' disabled title="{_e(NO_MARK_ENDPOINT)}"')
    cmd, label = ("resume", "resume (P)") if frame.paused_at is not None else ("pause", "pause (P)")
    note = "" if view.can_write else f'<span class="nm">{CONTROLS_AT_THE_BOX}</span>'
    return (
        f'<button type="button" class="btn" data-cmd="{cmd}"{off}>{label}</button>'
        f'<button type="button" class="btn" data-cmd="mark"{mark_off}>mark (M)</button>'
        f"{_reward_button(frame, view)}"
        f'<button type="button" class="btn danger" data-cmd="stop"{off}>stop…</button>'
        f"{_reward_answer(frame)}{note}"
    )
```

In `wl_expcontroller/web.py`, in `_SCRIPT`, replace:

```python
  var markNo = null;
```

with:

```python
  var markNo = null;
  var rewarding = false;
  var REWARD_LOST = "unknown: this page lost wlx serve's answer, so whether the reward was given is not known, and it was not sent again; check the session's fluid total before pressing again";
```

In `wl_expcontroller/web.py`, in `_SCRIPT`, replace:

```python
    if (node) { node.innerHTML = html; }
  }
```

with:

```python
    if (node) { node.innerHTML = html; }
    if (id === "controls") { holdReward(); }
  }
```

In `wl_expcontroller/web.py`, in `_SCRIPT`, replace:

```python
  function post(command, then) {
    if (!canWrite) { return; }
    var by = name || askName();
    if (!by) {
      tell("not sent: give your name first -- every command records who sent it", "crit");
      return;
    }
```

with:

```python
  function post(command, then, after) {
    var done = after || function () {};
    if (!canWrite) { done(); return; }
    var by = name || askName();
    if (!by) {
      tell("not sent: give your name first -- every command records who sent it", "crit");
      done();
      return;
    }
```

In `wl_expcontroller/web.py`, in `_SCRIPT`, replace:

```python
    }).catch(function () {
      tell("not delivered: this page could not reach wlx serve", "crit");
    });
  }
```

with:

```python
    }).catch(function () {
      tell(command.kind === "reward" ? REWARD_LOST : "not delivered: this page could not reach wlx serve", "crit");
    }).then(done);
  }
```

In `wl_expcontroller/web.py`, in `_SCRIPT`, replace:

```python
  function command(cmd) {
    if (cmd === "stop") { el("stop-confirm").hidden = false; }
    else if (cmd === "mark") { mark(); }
    else { post({ kind: cmd }); }
  }
```

with:

```python
  function holdReward() {
    var button = el("controls").querySelector('[data-cmd="reward"]');
    if (rewarding && button && !button.disabled) {
      button.disabled = true;
      button.setAttribute("data-held", "1");
    }
  }
  function reward() {
    var button = el("controls").querySelector('[data-cmd="reward"]');
    if (!button || button.disabled || rewarding) { return; }
    rewarding = true;
    holdReward();
    post({ kind: "reward" }, null, function () {
      rewarding = false;
      var held = el("controls").querySelector('[data-cmd="reward"][data-held]');
      if (held) { held.removeAttribute("data-held"); held.disabled = false; }
    });
  }
  function command(cmd) {
    if (cmd === "stop") { el("stop-confirm").hidden = false; }
    else if (cmd === "mark") { mark(); }
    else if (cmd === "reward") { reward(); }
    else { post({ kind: cmd }); }
  }
```

- [ ] **Step 4: Run the tests, then the suite, then check the script parses**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_taskd.py tests/test_web.py tests/test_serve.py`
Expected: all pass.
Run: `for i in 1 2 3; do WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py -k "reward_pressed_while_paused or never_acknowledges"; done`
Expected: 2 passed each time — the end to end and the wire count, which run threads and sockets.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1388 passed**.
Python cannot run the script, so check at least that it parses, if Node is on the machine:
Run: `python -c "from wl_expcontroller.web import _SCRIPT; open('/tmp/b2a-page.js', 'w').write(_SCRIPT)" && node --check /tmp/b2a-page.js`
Expected: no output, exit 0. (Task 16 Step 4 clicks the button in a browser.)

- [ ] **Step 5: Show the new tests can fail**

Every function this task adds or changes, neutered by the harness one at a time and read by its line (CLAUDE.md: `N failed` is a test noticing; `N errors` or `timed out` is not). Do nothing else in the worktree while each runs:

Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/taskd.py _manual_reward`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/taskd.py _command`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/taskd.py _hold`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/link.py _encode_command`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/link.py _decode_command`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/link.py deliver`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/serve.py parse_command`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/serve.py _rewarded`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/serve.py dispatch`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/web.py _reward_button`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/web.py _reward_answer`
Run: `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns None wl_expcontroller/web.py _controls`
Expected, each: `baseline: 1388 passed`; then `caught    <function>    N failed, … <- tests/…`, never `N errors` and never `timed out`; then `restored: 1388 passed`. For the four functions this task adds, the `<-` names this task's tests. A changed function breaks older tests too, and the harness names only the first three failures, so the scratch run also ran each mutant against the four test files with `-rf` and read which of this task's tests were among them. What the scratch run read (2026-09-28, a copy of the branch tip with Tasks 1–13 applied, four lanes in parallel copies on one development machine):

| Function | Harness line | This task's tests among the failures |
|---|---|---|
| `taskd._manual_reward` (new) | `11 failed, 1377 passed` | all 11: every `test_a_manual_reward_*`, the staged-size and pump-fault tests, the end to end |
| `taskd._command` | `80 failed, 1308 passed` | 12: the ten `taskd` reward tests, the post-loop refusal, the end to end |
| `taskd._hold` | `22 failed, 1366 passed` | 10: every paused-reward `taskd` test (not *while-running*, which never holds), the end to end |
| `link._encode_command` | `39 failed, 1349 passed` | 4: the wire test, the unacknowledged test, the ROUTER count, the end to end |
| `link._decode_command` | `77 failed, 1311 passed` | 6: the wire test, the three no-name refusals, the ROUTER count, the end to end |
| `link.deliver` | `22 failed, 1366 passed` | 3: the unacknowledged test, the ROUTER count, the end to end |
| `serve.parse_command` | `49 failed, 1339 passed` | 4: the reward parse, the refused `ml`, the ROUTER count, the end to end |
| `serve._rewarded` (new) | `6 failed, 1382 passed` | all 6: the four answers, the ROUTER count, the end to end |
| `serve.dispatch` | `19 failed, 1369 passed` | 2: the ROUTER count, the end to end |
| `web._reward_button` (new) | `4 failed, 1384 passed` | all 4: both amended running-session tests, the button test, the end to end |
| `web._reward_answer` (new) | `2 failed, 1386 passed` | both: the answer test, the end to end |
| `web._controls` | `16 failed, 1372 passed` | 5: the three `test_web` controls tests, the stream test, the end to end |

The script's reward logic has no Python function to neuter; `test_the_script_sends_one_reward_per_click_and_holds_the_button_until_its_answer` pins its text, and Task 16 Step 4 clicks it.

- [ ] **Step 6: Commit**

```bash
git add tasks/allocation.py wl_expcontroller/link.py wl_expcontroller/taskd.py wl_expcontroller/record.py wl_expcontroller/serve.py wl_expcontroller/web.py tests/test_link.py tests/test_taskd.py tests/test_web.py tests/test_serve.py
git commit -m "Give a manual reward during a pause: one correct-trial reward per press, counted, strobed, recorded, and never sent twice"
```

---

### Task 14: The measurement

**Why:** spec §5.4 and CLAUDE.md: no timing claim without a measurement. A script in `tools/` measures the per-frame mark check's cost in the frame loop, with and without it, and commits its result under `docs/measurements/`; the effect on real frame timing goes onto the hardware verification list, as V12 in `docs/validation.md`. **This plan states no number**: the number is the script's output, produced when this task runs (Plan decision 1).

**Files:**
- Create: `tools/measure_mark_check.py`, `tests/test_measure_mark_check.py`
- Modify: `docs/validation.md` (V12)
- Create, by running the script: `docs/measurements/dev-machine/<today>-mark-check.md`

**Interfaces:**
- Consumes: Task 3's `ZmqLink(..., mark_endpoint=...)` and `mark_signal`; Task 6's `run_trial(..., each_frame=...)` and the session's check shape.
- Produces: `tools/measure_mark_check.py` with `measure(frames, trials, calls) -> dict`, `report(found) -> str` and `main(argv) -> int`; V12.

**`main` has its own test** because it is how Step 5 commits the number: in the plan's pre-flight sweep, `main` neutered was the one `SURVIVED` line, every test having called `measure` and `report` directly.

- [ ] **Step 1: Write the failing test**

Create `tests/test_measure_mark_check.py`:

```python
"""`tools/measure_mark_check.py` (P4d-2b b2a, spec §5.4): the measurement runs, times
what it says it times, and its report says what it is and what it is not.

The numbers it produces are not tested -- they are what it exists to find out, and
they are committed under `docs/measurements/` by the task that runs it. What is
tested is that the script cannot quietly measure something else.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from wl_expcontroller.run import Quiet, run_trial

_SPEC = importlib.util.spec_from_file_location(
    "wlx_measure_mark_check",
    Path(__file__).resolve().parents[1] / "tools" / "measure_mark_check.py",
)
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)


def test_the_trial_it_times_ends_on_the_frame_it_names():
    """Frames per trial is the divisor of every per-frame figure, so the trial must
    run exactly that many."""
    for frames in (1, 37, 1000):
        result = run_trial(tool._trial(frames), Quiet(), tool.PERIOD, values={})
        assert result.frames == frames


def test_the_check_it_times_is_the_sessions_and_a_mark_would_be_stamped():
    class _Link:
        def __init__(self) -> None:
            self.calls = 0

        def mark_signal(self) -> int:
            self.calls += 1
            return 9 if self.calls == 3 else 0

    link = _Link()
    each_frame = tool._session_check(link)
    for frame in range(1, 6):
        each_frame(frame)

    assert link.calls == 5, "one check per frame"
    kept = [
        cell.cell_contents
        for cell in each_frame.__closure__
        if isinstance(cell.cell_contents, list)
    ]
    assert kept == [[(9, 3)]], "a mark is taken in the frame it answered"


def test_a_small_measurement_reports_both_loops_the_check_and_its_allocation():
    found = tool.measure(frames=50, trials=5, calls=2000)

    for key in ("without_ns", "with_ns", "check_ns"):
        assert set(found[key]) == {"median", "p90", "p99", "max"}
        assert 0 < found[key]["median"] <= found[key]["max"]
    assert found["alloc_held_by_link_bytes"] == 0

    text = tool.report(found)
    assert "**This is not V1, and not a frame-timing measurement.**" in text
    assert "Median added per frame by the check:" in text
    assert "V12 (`docs/validation.md`)" in text
    assert "--frames 50 --trials 5" in text


def test_the_command_line_writes_the_report_where_it_is_told(tmp_path, capsys):
    """`main` is how Task 14 commits the number, so the file `--out` names gets the
    report the options asked for, and the terminal says where it went."""
    out = tmp_path / "measurements" / "mark-check.md"

    code = tool.main(
        ["--frames", "20", "--trials", "3", "--calls", "500", "--out", str(out)]
    )

    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "Median added per frame by the check:" in text
    assert "--frames 20 --trials 3" in text
    assert capsys.readouterr().out == f"wrote {out}\n"
```

- [ ] **Step 2: Run it to see it fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_measure_mark_check.py`
Expected: fails to collect — `FileNotFoundError` for `tools/measure_mark_check.py`.

- [ ] **Step 3: Write the script and V12**

Append to `docs/validation.md`:

```markdown

## V12 — Console controls in the frame loop (P4d-2b b2a)
New (2026-09-27). Slice b2a puts one call inside every frame: `link.ZmqLink.mark_signal`,
the check for an operator's mark, handed to `run.run_trial` as its `each_frame` hook, so a
mark is stamped and its `OPERATOR_MARK` code strobed in the frame it reaches the rig (P4d-2b
spec §5.0: marks must be instant). `tools/measure_mark_check.py` measures what the check
costs the CPU per frame on the machine it runs on, and its first result is committed under
`docs/measurements/dev-machine/`. That is **not a frame-timing measurement**: those frames
are not paced. The spec's rule stands: **if the check measurably disturbs frames, it goes
back to the PI before b2a ships** — and only a rig can say whether it does.

Procedure, on the rig, with V1's photodiode and NIDQ capture:

1. **Frame timing with the check.** Run V1's flip sequence as a session three ways — no
   mark endpoint (`wlx run --link PUB,REP`), the mark endpoint bound and idle
   (`--link PUB,REP,MARK`, `wlx serve` attached), and marks arriving about once a second
   from the console — for ≥ 10 minutes each. Report the frame-interval distribution and
   the dropped frames of each, side by side.
2. **The mark lands in its frame.** For each mark in (1), the `OPERATOR_MARK` edge on the
   NIDQ lies inside the frame the session record's stamp names (`controls.jsonl`: its
   `trial_index` and `frame`), against the photodiode's frame boundaries.
3. **A pause shows the background.** Pause from the console mid-block: the photodiode
   patch and the panel show the task's background with nothing drawn on it until the
   resume, and the `PAUSE` and `RESUME` edges bracket that stretch on the NIDQ.

Re-run after any change to the frame loop, the link, or the display stack (P4).
```

Create `tools/measure_mark_check.py`:

```python
#!/usr/bin/env python3
"""What the per-frame mark check costs in the trial loop (P4d-2b spec §5.4).

CLAUDE.md: no timing claim without a measurement. Slice b2a puts one call inside every
frame -- `link.ZmqLink.mark_signal`, handed to `run.run_trial` as `each_frame` by
`taskd.Session.run` -- so that an operator's mark is stamped in the frame it reaches
the rig (spec §5.0). The spec says: "If the check measurably disturbs frames, it goes
back to the PI before b2a ships." This script is how that is decided on a given
machine, and the number it writes is the only number anyone may quote.

It measures, on the machine it runs on:

1. **The check alone**: `mark_signal()` on a live link whose mark socket is bound and
   idle -- the state it is in on nearly every frame -- in nanoseconds per call.
2. **The trial loop with and without it**: `run_trial` over a trial that ends on its
   own after a fixed number of frames, against a world that does nothing, first with
   no `each_frame` and then with the session's own check shape (the link's bound
   `mark_signal`, then a test on what it answered). Interleaved, trial by trial, so
   drift in the machine lands on both. Reported per frame.
3. **What the check leaves allocated**: `tracemalloc`, the net change and the peak
   over the calls in (1), with the link's own module's share named.

**What this is not.** Frames here are not paced: the loop runs as fast as the CPU
lets it, so this is the check's *CPU cost per frame* -- the only way it could disturb
a paced frame -- and not a frame-timing measurement. It is not V1. On a rig, the
effect on real frame timing is V12 in `docs/validation.md`, measured with the
photodiode. The garbage collector is off inside each timed trial and collected
between them, the discipline CLAUDE.md sets for trial loops, so a collection is not
billed to whichever variant it happened to land in.

    python tools/measure_mark_check.py
    python tools/measure_mark_check.py --frames 2000 --trials 400 \\
        --out docs/measurements/dev-machine/2026-09-27-mark-check.md
"""

from __future__ import annotations

import argparse
import gc
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import zmq  # noqa: E402 -- after the path, so the checkout's package is the one measured

from wl_expcontroller import link as _link  # noqa: E402
from wl_expcontroller.run import Quiet, run_trial  # noqa: E402
from wl_expcontroller.task import After, On, Outcome, State, Trial  # noqa: E402

#: The trial loop's frame period here: a number `After` compares against, nothing
#: more, since frames are not paced.
PERIOD = 0.001


def _trial(frames: int) -> Trial:
    """A trial that ends on its own on frame `frames`: `After` fires on the first
    frame whose elapsed time reaches it, and half a period short of `frames * PERIOD`
    is reached on frame `frames` and not before, whatever the float rounding."""
    return Trial(
        start="wait",
        states=[State("wait", go=[On(After((frames - 0.5) * PERIOD), Outcome.CORRECT)])],
    )


def _session_check(link: _link.ZmqLink):
    """The check exactly as `taskd.Session.run` builds it: the link's `mark_signal`,
    bound once, then a test on the answer. A mark never arrives here, so `stamp` is
    never reached; it is present so the closure is the session's shape."""
    signal = link.mark_signal
    stamped: list = []

    def each_frame(frame: int) -> None:
        mark = signal()
        if mark:
            stamped.append((mark, frame))

    return each_frame


def _timed_trial(trial: Trial, frames: int, each_frame) -> float:
    """Nanoseconds per frame for one trial, with the collector off inside it."""
    gc.collect()
    gc.disable()
    try:
        started = time.perf_counter_ns()
        result = run_trial(trial, Quiet(), PERIOD, values={}, each_frame=each_frame)
        took = time.perf_counter_ns() - started
    finally:
        gc.enable()
    if result.frames != frames:
        raise RuntimeError(f"the trial ran {result.frames} frames, not {frames}")
    return took / frames


def _spread(values: list[float]) -> dict:
    ordered = sorted(values)

    def at(q: float) -> float:
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    return {
        "median": statistics.median(ordered),
        "p90": at(0.90),
        "p99": at(0.99),
        "max": ordered[-1],
    }


def measure(frames: int = 1000, trials: int = 300, calls: int = 200_000) -> dict:
    """Run the three measurements and return what they found, as numbers."""
    link = _link.ZmqLink(
        "tcp://127.0.0.1:0", "tcp://127.0.0.1:0", mark_endpoint="tcp://127.0.0.1:0"
    )
    try:
        check = link.mark_signal
        for _ in range(1000):
            check()

        per_call = []
        for _ in range(20):
            started = time.perf_counter_ns()
            for _ in range(calls // 20):
                check()
            per_call.append((time.perf_counter_ns() - started) / (calls // 20))

        tracemalloc.start()
        try:
            before = tracemalloc.take_snapshot()
            tracemalloc.reset_peak()
            base, _ = tracemalloc.get_traced_memory()
            for _ in range(calls):
                check()
            now, peak = tracemalloc.get_traced_memory()
            after = tracemalloc.take_snapshot()
        finally:
            tracemalloc.stop()
        held_by_link = sum(
            stat.size_diff
            for stat in after.compare_to(before, "filename")
            if stat.traceback[0].filename == _link.__file__
        )

        trial = _trial(frames)
        each_frame = _session_check(link)
        for _ in range(10):
            _timed_trial(trial, frames, None)
            _timed_trial(trial, frames, each_frame)
        without, with_check = [], []
        for _ in range(trials):
            without.append(_timed_trial(trial, frames, None))
            with_check.append(_timed_trial(trial, frames, each_frame))
    finally:
        link.close()

    return {
        "frames": frames,
        "trials": trials,
        "calls": calls,
        "check_ns": _spread(per_call),
        "without_ns": _spread(without),
        "with_ns": _spread(with_check),
        "alloc_net_bytes": now - base,
        "alloc_peak_bytes": peak - base,
        "alloc_held_by_link_bytes": held_by_link,
    }


def report(found: dict) -> str:
    """The measurement as a Markdown file for `docs/measurements/`, with its
    conditions, in the shape the display spike's is."""
    rows = "\n".join(
        f"| {label} | {found[key]['median']:.1f} | {found[key]['p90']:.1f} | "
        f"{found[key]['p99']:.1f} | {found[key]['max']:.1f} |"
        for label, key in (
            ("trial loop, no check (ns per frame)", "without_ns"),
            ("trial loop, with the check (ns per frame)", "with_ns"),
            ("the check alone (ns per call)", "check_ns"),
        )
    )
    added = found["with_ns"]["median"] - found["without_ns"]["median"]
    return f"""# The per-frame mark check -- its cost in the trial loop, on a development machine

> **This is not V1, and not a frame-timing measurement.** Frames here are not paced; the
> loop runs as fast as the CPU lets it. It measures what the check costs the CPU per
> frame, which is the only way it could disturb a paced frame. The effect on real frame
> timing is V12 (`docs/validation.md`), on a rig, with the photodiode.

**Date:** {time.strftime('%Y-%m-%d')}. **Script:** `tools/measure_mark_check.py`
(P4d-2b b2a, spec §5.4), run as
`python tools/measure_mark_check.py --frames {found['frames']} --trials {found['trials']}`.
**Machine:** {platform.platform()}, {platform.machine()}, {platform.processor() or 'processor not reported'}.
**Python:** {platform.python_version()}. **pyzmq:** {zmq.__version__} (libzmq {zmq.zmq_version()}).

## What was measured

`run.run_trial` over a trial that ends on frame {found['frames']}, against `run.Quiet`
(a world where nothing happens), {found['trials']} times with no `each_frame` and
{found['trials']} times with the session's check -- `link.ZmqLink.mark_signal` on a live
loopback link whose mark socket is bound and idle -- interleaved trial by trial. The
collector is off inside each timed trial. The check alone is {found['calls']} calls in
twenty batches.

| | median | p90 | p99 | max |
|---|---|---|---|---|
{rows}

**Median added per frame by the check: {added:.1f} ns.**

## What the check allocates

Over {found['calls']} calls with nothing waiting (`tracemalloc`): net
{found['alloc_net_bytes']} bytes, peak {found['alloc_peak_bytes']} bytes above the
starting point, and {found['alloc_held_by_link_bytes']} bytes still held that were
allocated in `wl_expcontroller/link.py`. The peak includes `tracemalloc`'s own
bookkeeping between readings; the held figure is the one about the check.

## What it decides, and what it does not

It says what the check costs a frame's CPU on this machine. Whether that disturbs a
frame on a rig -- at the rig's refresh rate, with the rig's display and card -- is V12's
to say, and the spec's rule stands: if it does, it goes back to the PI before b2a ships.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--calls", type=int, default=200_000)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    text = report(measure(args.frames, args.trials, args.calls))
    if args.out is None:
        print(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_measure_mark_check.py`
Expected: 4 passed.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: **1392 passed**.

- [ ] **Step 5: Measure, read it, and commit it with the script**

On a quiet machine — no mutation sweep, no suite, no build running beside it, since whatever else the CPU is doing lands in the numbers:

Run: `python tools/measure_mark_check.py --out "docs/measurements/dev-machine/$(date +%Y-%m-%d)-mark-check.md"`
Expected: `wrote docs/measurements/dev-machine/<today>-mark-check.md`. Read it: the table's three rows, the median added per frame, and the allocation paragraph, whose "still held" figure is `0`. **Quote its numbers nowhere else** except as that file's, with its conditions; Task 16 Step 6 hands them to the PI.

```bash
git add tools/measure_mark_check.py tests/test_measure_mark_check.py docs/validation.md docs/measurements/dev-machine/
git commit -m "Measure what the per-frame mark check costs in the trial loop, and put its frame effect on the rig's list (V12)"
```

---

### Task 15: Write it down

**Why:** CLAUDE.md — a change that invalidates `architecture.md`, `pitfalls.md` or a spec updates them in the same branch, and a session ends by leaving the repo resumable. `architecture.md`'s console row still says writes are "slice b2", its commands are `SetParameter`/`Stop`, and its welfare-critical list must name what joins it (Plan decision 13). S9a §7 gains the mark socket and the command thread, §8 the controls, §9 schema 8's panes and its history bullet. `pitfalls.md` gains the one risk b2a opened — a browser page that can write — and P3's note the one per-frame call b2a added. **No ADR is written**: the transport is ADR-0003's, untouched (a third socket on the same link), and the pyzmq floor is an inventory row (Task 3), not a new dependency.

Where a line below says *the date the branch is finished*, write that date; the text here says 2026-09-27, the day this plan was written.

**Files:**
- Modify: `docs/design/architecture.md`, `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, `docs/pitfalls.md`, `docs/CHECKPOINT.md`, `docs/next-session.md`

**Interfaces:** none (documents only).

- [ ] **Step 1: `docs/design/architecture.md`**

The console row, the commands and what reaches them:

In `docs/design/architecture.md`, replace:

```markdown
binds a ZMQ PUB socket for `Telemetry` and a REP socket for `SetParameter`/`Stop` commands (ADR-0003's transport, untouched).
```

with:

```markdown
binds a ZMQ PUB socket for `Telemetry`, a REP socket for its commands — `SetParameter` and `Stop`, and since P4d-2b b2a `Pause`, `Resume`, `Mark` (a mark's note), `ScheduleStop`, `CancelScheduledStop` and `ManualReward` (a manual reward, given only while paused), each checked where it is decoded — and, given a third endpoint, a PULL socket for an operator's mark signal, which the trial loop checks once per frame (ADR-0003's transport, untouched: a third socket on the same link).
```

In `docs/design/architecture.md`, replace:

```markdown
Reads are open to the LAN; writes from the box are slice b2, and OAuth is P4d-3 |
```

with:

```markdown
Reads are open to the LAN. **Writes come from the box** (P4d-2b slice b2a, 2026-09-27): `POST /commands` is accepted only from a loopback peer, with a `Host` naming loopback, the page's own `Origin` and `Content-Type: application/json` (spec §2), and recorded as `NAME (box, unverified)`; every request is answered only when its `Host` names this console (`--allow-host` adds names). `wlx serve` owns each socket on one thread — a read-only telemetry thread, a command thread whose REQ socket waits for `taskd`'s acknowledgment (*sent*, *not delivered*, *busy*), and a mark thread that sends the signal ahead of every command. Writes from people signed in to wl-works are slice b2b |
```

The welfare-critical list:

In `docs/design/architecture.md`, replace:

```markdown
**In code, that is `wl_expcontroller/bounds.py` and `wl_expcontroller/welfare.py`, and
four functions in `wl_expcontroller/cli.py`, plus one line inside a fifth.** Both modules
```

with:

```markdown
**In code, that is `wl_expcontroller/bounds.py` and `wl_expcontroller/welfare.py`, and
four functions in `wl_expcontroller/cli.py`, plus one line inside a fifth — and, since
P4d-2b b2a, three functions in `wl_expcontroller/taskd.py`.** Both modules
```

In `docs/design/architecture.md`, replace:

```markdown
prompt goes. A change to either module, to those four functions, or to that one line, is
a change requiring review; a change elsewhere is not.
```

with:

```markdown
prompt goes. A change to either module, to those four functions, to that one line, or to
the three `taskd` functions below, is a change requiring review; a change elsewhere is not.

**The three `taskd` functions are `Session._ends`, `Session._hold` and
`Session._manual_reward`** (P4d-2b b2a, 2026-09-27; the third since the PI's 2026-09-28
amendment). `_ends` is the one place the trial loop asks `welfare.must_stop`, between
trials and on every pass of a paused session alike, and where a scheduled stop — "after X
mL this session" among them, read from `welfare.session_total()` — ends a session; it asks
the limit first, so a session at its limit ends as `limit`. `_hold` is the paused loop:
no trial runs, so the task rewards nothing; each pass still drains, publishes and asks
`_ends`; and the commands it drains are the only ones a manual reward is given for.
`_manual_reward` gives one: a person's press of *give reward* while paused, one delivery
of the bounded config's `reward_correct` through `welfare.Rig.reward`, strobed
`MANUAL_REWARD` first and refused at any other time. All three call `welfare` unchanged,
and none holds a clock or a limit of its own; they are on this list because a plausible
mistake in any — the limit asked on one path and not the other, a paused session that
forgot to ask, a reward given while trials run or paid from another entry — ends a session
late or rewards an animal when nobody meant it to, and passes every refusal `welfare` has.
```

The protocols list:

In `docs/design/architecture.md`, replace:

```markdown
- **Control/telemetry** (console <-> taskd): ZMQ REQ/REP for commands, PUB for telemetry.
  Bearer token, rate limit, and a write-arbitration rule for concurrent writers.
```

with:

```markdown
- **Control/telemetry** (console <-> taskd): ZMQ REQ/REP for commands, PUB for telemetry,
  and PUSH/PULL for an operator's mark signal — eight bytes, read by the trial loop once
  per frame and stamped in the frame it arrives (P4d-2b b2a). Bearer token, rate limit,
  and a write-arbitration rule for concurrent writers.
```

- [ ] **Step 2: S9a (`docs/superpowers/specs/2026-08-31-S9a-console-design.md`)**

§7's diagram and the paragraph under it:

In `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, replace:

```markdown
browser ──HTTP + SSE──►  console  ──ZMQ REQ/REP (commands)──►  taskd ──► world, devices
                      ├ OAuth client + local credential  ◄──ZMQ PUB (telemetry)──┘
```

with:

```markdown
browser ──HTTP + SSE──►  console  ──ZMQ REQ/REP (commands)──►  taskd ──► world, devices
                      ├ OAuth client + local credential  ◄──ZMQ PUB (telemetry)──┘
                      │                 ──ZMQ PUSH/PULL (mark signal)──►
```

In `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, replace:

```markdown
**Two processes, and the split was already mandatory.**
```

with:

```markdown
**Writes from the box, and one socket per thread** (P4d-2b spec §2, §5.3; built in slice
b2a, 2026-09-27). `POST /commands` is accepted only from the box's own page — a loopback
peer, a `Host` naming loopback, the page's `Origin`, JSON — and every request is answered
only when its `Host` names this console. The console's telemetry thread reads, its command
thread alone owns the REQ socket and tells the page *sent* only when `taskd` has
acknowledged, and its mark thread sends an operator's mark on a third socket, ahead of
every command, for `taskd` to stamp in the frame it arrives.

**Two processes, and the split was already mandatory.**
```

§8's feed:

In `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, replace:

```markdown
Last-write-wins within an ITI, both writes recorded with their actors, and the resolution
shown.
```

with:

```markdown
Last-write-wins within an ITI, both writes recorded with their actors, and the resolution
shown.

**Since P4d-2b b2a (2026-09-27) the feed is on the page**, rendered in Python like every
pane: staged changes, then the control events — each setting applied, each pause and
resume, each mark and its note, each schedule and cancellation, and each manual reward
given while paused — newest first with when
and who, then the refusals. The session keeps the last `link.CONTROL_HISTORY` of those
events for the feed and counts what fell off (`controls_dropped`); `controls.jsonl` in the
session record keeps every one.
```

§9's table — three rows after the "Trials per minute" row:

In `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, replace:

```markdown
| Trials per minute | **Derived by `wlx serve`**, from `trial_index` over the last five minutes of frames, labeled derived on the page, bounding nothing — the one console number not in the record, and it says so |
```

with:

```markdown
| Trials per minute | **Derived by `wlx serve`**, from `trial_index` over the last five minutes of frames, labeled derived on the page, bounding nothing — the one console number not in the record, and it says so |
| Paused, and since when | `Session.paused_at` → `Telemetry.paused_at` (schema 8), the instant on the session's anchored clock, `None` while trials run. Set at the boundary a `Pause` was drained at; the pill says *paused · since HH:MM:SS* only while the session runs |
| Scheduled stop | `Session.scheduled_stop` → `Telemetry.scheduled_stop` (kind, target, who, and `said`, the rig's own words, which the stop reason reuses). Shown on the strip while it is held, with a cancel button; spent when it fires |
| Changes feed: control events | `Session.controls` → `Telemetry.controls` and `controls_dropped` (schema 8): the last 50 stops, pauses, resumes, marks, notes, schedules, cancellations, manual rewards and applied settings, with who and when. The record (`controls.jsonl`, and `parameter_changes.jsonl` for settings) keeps all of them |
```

§9's schema history:

In `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, replace:

```markdown
Schema-versioned with golden-file tests, which ADR-0003 already requires. **`SCHEMA` is
7 as of 2026-09-26** (P4d-2b b1; `wall_at` arrived in it on 2026-09-27, ledger Ruling
1), and every bump since 2 is the same case: a field that still decodes and no longer
```

with:

```markdown
Schema-versioned with golden-file tests, which ADR-0003 already requires. **`SCHEMA` is
8 as of 2026-09-27** (P4d-2b b2a), and every bump since 2 is the same case: a field
that still decodes and no longer
```

In `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, replace:

```markdown
  and `recent_outcomes` arrived. Nothing changed meaning; a schema-7 reader cannot decode a
  schema-6 frame, which lacks them, so `wlx serve` refuses it and says so on its page rather
  than guessing.
```

with:

```markdown
  and `recent_outcomes` arrived. Nothing changed meaning; a schema-7 reader cannot decode a
  schema-6 frame, which lacks them, so `wlx serve` refuses it and says so on its page rather
  than guessing.
- **8 (2026-09-27, P4d-2b b2a):** `paused_at`, `scheduled_stop` (`ScheduledStop`: kind,
  target, who, and its words), `controls` (`Control`: kind, who, when, and its words) and
  `controls_dropped` arrived — the controls from the box. Nothing changed meaning; each
  reader refuses the other's schema by name.
```

- [ ] **Step 3: `docs/pitfalls.md`**

In `docs/pitfalls.md`, replace:

```markdown
| **P21** | **A guardrail nothing calls, behind a comment that went stale** | **High** | A safety component needs a *consumer* in the same commit, and a test that the consumer is on the only path — see expanded note |
```

with:

```markdown
| **P21** | **A guardrail nothing calls, behind a comment that went stale** | **High** | A safety component needs a *consumer* in the same commit, and a test that the consumer is on the only path — see expanded note |
| **P22** | **A browser page that can write is a page any site can try to make write** | **High** | Spec §2's four checks on every write, the `Host` check on every request, the rig's own validation behind them — see expanded note |
```

In `docs/pitfalls.md`, replace:

```markdown
`gc.freeze()` after startup; SCHED_FIFO + CPU isolation for `taskd`; profile with py-spy
under load. The console is a separate process precisely so no UI or plotting work can
share the hot loop's runtime.
```

with:

```markdown
`gc.freeze()` after startup; SCHED_FIFO + CPU isolation for `taskd`; profile with py-spy
under load. The console is a separate process precisely so no UI or plotting work can
share the hot loop's runtime.

**Since P4d-2b b2a the frame does one thing for the console** (2026-09-27): it asks the
link's mark socket whether an operator's mark is waiting (`link.ZmqLink.mark_signal`, one
`getsockopt(EVENTS)`), so a mark is stamped in the frame it arrives. It allocates nothing
it keeps; what it costs a frame's CPU is `tools/measure_mark_check.py`'s to say, on the
machine it runs on, and what it does to real frames is V12's, on a rig.
```

Append to `docs/pitfalls.md`:

```markdown

**P22 — A browser page that can write.** P4d-2b b2a put controls on a page served to the
lab network, and a page that can post a command is a page another site can try to make
post one: a cross-site form or `fetch` from a tab open in the rig PC's browser, or a
hostile name rebound to the box's address (DNS rebinding), whose requests then look
same-origin to the browser. Mitigation, all of it tested (`tests/test_serve.py`): a write
is accepted only from a loopback peer, with a `Host` naming loopback, the page's own
`Origin`, and `Content-Type: application/json` — which a cross-site request cannot send
without a preflight this server never approves (spec §2); **every** request, reads
included, is answered only when its `Host` names this console, so a rebound name gets a
421 and no page (spec §5.3); and behind both, `taskd` validates every command as it
decodes it (M8) and `bounds` holds every ceiling whoever asks. The actor recorded from the
box is `NAME (box, unverified)`, because a forgeable name that looks verified is worse
than none (S9a §6). Signed-in writes from other machines are b2b's, and bring their own
token checks.
```

- [ ] **Step 4: `docs/CHECKPOINT.md`**

The note at the top:

In `docs/CHECKPOINT.md`, replace:

```markdown
> **This file describes `main`.** P4d-2b slice b1 fast-forwarded onto `main` on
> 2026-09-27 (`207b170..7b01992`). Work in flight lives on branch `p4d2b-b2a-controls`
> (the b2 design, approved, and its plan); see "What moved on 2026-09-27, afternoon".
> Run `git branch --show-current` before believing a line about a branch.
```

with:

```markdown
> **This file describes `main`, plus one branch that is not on it yet.** The newest entry,
> "What moved on 2026-09-27, P4d-2b slice b2a", describes `p4d2b-b2a-controls`, which waits
> for the PI's approval of its welfare items (`docs/next-session.md` §1) and has not merged;
> `main`'s copy of this file does not have that entry. The entries below it are on `main`:
> P4d-2b slice b1 fast-forwarded onto `main` on 2026-09-27 (`207b170..7b01992`). Run
> `git branch --show-current` before believing a line about a branch.
```

A new entry above the afternoon one (the newest on `main`), with the resume line moved into it:

In `docs/CHECKPOINT.md`, replace:

```markdown
## What moved on 2026-09-27, afternoon: b1 merged, b2 designed, the camera, CI

**Resume here:** the b2a implementation plan, on branch `p4d2b-b2a-controls` (worktree
```

with:

```markdown
## What moved on 2026-09-27, P4d-2b slice b2a: controls from the box

**Resume here:** b2a is built on branch `p4d2b-b2a-controls` and waits for the PI's
approval of its four welfare items (`docs/next-session.md` §1) and his answer on the mark
check's measured cost. In order: his answers; the fast-forward to `main`; then b2b, remote
sign-in through wl-works, designed in full from the P4d-2b spec §5.7 once b2a has shipped.

- **What was built** (plan `docs/superpowers/plans/2026-09-27-p4d2b-b2a-controls.md`):
  M8 closed where commands are decoded; six new commands on the link, each with `by`;
  pause and resume, held at a trial boundary; a manual reward while paused, one
  correct-trial reward per press (the PI's one change at his review of the plan,
  2026-09-28); a mark stamped in the frame it reaches the rig, on a third loopback socket,
  with its note joined by number; a scheduled stop by clock time, trials or fluid, held by
  `taskd`; `controls.jsonl`; telemetry schema 8;
  `wlx console` and the page rendering all of it; `POST /commands` under spec §2's four
  checks, the `Host` check on every request, and `wlx serve`'s command and mark threads;
  the end to end; and `tools/measure_mark_check.py` with its first result and V12.
- **Welfare-critical, and waiting on the PI:** while paused the task rewards nothing, a
  person may give one correct-trial reward per press (`reward_correct`, counted in the
  fluid total and toward "stop after X mL"), and the out-of-cage limit still ends the
  session; a scheduled stop, "after X mL" included, can end a session; reward size can be
  set from the page, still capped by its ceiling; and the M8 fix. `taskd.Session._ends`,
  `_hold` and `_manual_reward` joined the welfare-critical list (`architecture.md`).
  `welfare.py`, `bounds.py` and the `cli` welfare functions did not change.
- **The plan's sixteen decisions** are in its header: the mark socket and its `EVENTS`
  check, verified in pyzmq 27.2.0's source; `--link PUB,REP[,MARK]`; random mark numbers
  below 2**53; the mark's two rows; the pause's housekeeping loop; the schedule's rules
  (exactly now is tomorrow's, with the date said); `controls.jsonl`; `PAUSE`, `RESUME`,
  `OPERATOR_MARK` at 4131–4133; schema 8; `wlx serve`'s threads and answers; the `Host`
  check's names; the page; the welfare list; M8; a test-only speedup; and the manual
  reward during a pause (`MANUAL_REWARD` at 4134; only while held; never re-sent).
- **The display during a pause is structural**: no trial runs, so nothing is drawn. No
  display process exists to show the task's background yet; V12 item 3 proves it on a rig.
- **Carried forward from b2a:** the mark check's frame effect is V12, unmeasured until a
  rig exists; a note typed after the session ended is refused with the post-loop sentence,
  so it is lost from the record (the stamp is kept); the page's script is checked by
  `node --check` and by eye (Task 16 Step 4), never by pytest.
- **Three bounds a test here needs, found by the plan's pre-flight sweep printing `timed
  out`:** a simulated session with a mark socket runs fewer trials a second than one
  without (every frame pays for the check), so a trial budget sized for b1's session held
  each of b2a's end to end tests past 50 s under a broken command path —
  `tests/test_serve.py`'s `CONTROL_TRIAL_BUDGET` is theirs, and `_Session.frame` stops
  waiting once `wlx run` has ended; `Outbox.submit` waits as long as its thread lives,
  so a test calling it on its own thread hangs rather than fails when a job goes
  unanswered — call it through `_submitted`; and a paused loop that stops waiting runs no
  trial and calls no `idle`, so neither the trial budget nor `_Scripted`'s wait budget
  moves — `_Scripted` also counts drains (`PASS_BUDGET`).

The gate's result and the test count are added here in the plan's Task 16 Step 3.

## What moved on 2026-09-27, afternoon: b1 merged, b2 designed, the camera, CI

**Where b2a stood when this entry was made:** the b2a implementation plan, on branch `p4d2b-b2a-controls` (worktree
```

The Work packages row:

In `docs/CHECKPOINT.md`, replace:

```markdown
**b2 designed, 2026-09-27**: the spec's §5, on branch `p4d2b-b2a-controls` — b2a (controls from the box) is planned there next, b2b (remote sign-in through wl-works) after it. Spec `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md`: §1–§4 approved, with the mockup rulings held in §4.0; §4 is b1, on telemetry schema 7; §5 is b2. b3–b6 each get a section as they are designed | that spec | **b2a's plan, then its execution** (close M8 first) |
```

with:

```markdown
**b2 designed, 2026-09-27**, and **split** (PI): **b2a, controls from the box, is built on branch `p4d2b-b2a-controls`** and waits for the PI's approval of its four welfare items (spec §5.5); b2b, remote sign-in through wl-works, is designed from §5.7 after b2a ships. Spec `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md`: §1–§4 approved, with the mockup rulings held in §4.0; §4 is b1, on telemetry schema 7; §5 is b2. b3–b6 each get a section as they are designed | that spec | **b2a: the PI's review, then the fast-forward to `main`** |
```

- [ ] **Step 5: `docs/next-session.md`**

A new §1 above b1's, which becomes §1a's neighbor as the record of what he approved:

In `docs/next-session.md`, replace:

```markdown
## 1. The thing that needed a person — P4d-2b b1, approved and merged 2026-09-27
```

with:

```markdown
## 1. The thing that needs a person, not a session — P4d-2b b2a, awaiting the PI

**Branch `p4d2b-b2a-controls` is welfare-critical** (CLAUDE.md; P4d-2b spec §5.5) and does
not merge until the PI approves the four items the plan's Task 16 Step 6 gives him, in
plain terms: (1) while paused, the task rewards nothing, a person may give one
correct-trial reward per press (his one change at his review of the plan, 2026-09-28), and
the out-of-cage limit still ends the session; (2) a scheduled stop, "after X mL" included,
can end a session; (3) reward size can be changed from the console page, still capped by
its approved ceiling; (4) the M8 fix — a malformed setting is refused and never ends the
session. He is also asked about the per-frame mark check's measured cost (the spec's rule:
a check that measurably disturbs frames goes back to him before b2a ships). Record his
answers here, and move this section below as the record once he has.

## 1b. The thing that needed a person — P4d-2b b1, approved and merged 2026-09-27
```

§6's title and first paragraph:

In `docs/next-session.md`, replace:

```markdown
## 6. P4d-2a is on `main`; P4d-2b b1 is built; b2 is next

**2026-09-27.** b1 is built on branch `p4d2b-b1-read-only-console`, and the PI approved
its welfare item that day (§1 above): it fast-forwards onto `main` once the mutation gate
and CI are clean. **b2 is next** after that — writes from the box (spec §2's
four conditions on `POST /commands`, the `NAME (box, unverified)` attribution, and the
greyed controls' sentence), per spec §4.0's slice list, and it first closes P4d-2a's M8
(`SetParameter.value`'s type) before any write ships. The command thread that owns the REQ
socket arrives with b2 (`serve.py`'s module docstring names it). **Ask the PI while
designing b2:** should the `Host` check spec §2 requires for writes also apply to reads?
DNS rebinding could let a page open in a lab browser read the LAN-open `/` and `/events`.
The rest of what b1 carries forward is listed in `docs/CHECKPOINT.md`'s 2026-09-27 entry,
under "Carried forward from b1". What follows is the
```

with:

```markdown
## 6. P4d-2b b1 is on `main`; b2a is built; b2b is next

**2026-09-27.** b2a — controls from the box — is built on branch `p4d2b-b2a-controls` and
waits for the PI (§1 above). What it built and what it carries forward are in
`docs/CHECKPOINT.md`'s b2a entry. **b2b is next** after it merges: remote sign-in through
wl-works, designed in full as its own section of the P4d-2b spec from what §5.7 already
decided — the browser holds the wl-works access token, the rig verifies it — and it needs
a registered client per rig and a network route from each rig to wl-works, neither of
which is this repository's. The question this section used to carry, whether the `Host`
check applies to reads, was answered in spec §2 (2026-09-27): every request, and b2a
builds it. What follows is the
```

- [ ] **Step 6: Commit**

```bash
git add docs/
git commit -m "Record the controls from the box, and what the PI is asked to approve"
```

---

### Task 16: Prove it, look at it, and hand it to the PI

**Files:** `docs/CHECKPOINT.md` (Step 3). Nothing else, unless a step finds a survivor or a defect; then the owning task's files, with a test that fails without the fix.

**Interfaces:** none.

- [ ] **Step 1: The whole suite, three times**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider -rs` three times in a row.
Expected: all pass each time, and the `-rs` summary lists no skip from `test_health.py` or `test_serve.py`. **1392 passed** if nothing was added after Task 14 (Task 15 adds no test).

- [ ] **Step 2: The full mutation sweep, before the merge, read line by line**

**This branch touches `GLOBAL` files and many modules, so it gets the full sweep before it merges** (`docs/CHECKPOINT.md`'s CI row): `pyproject.toml`, `tests/_zmq_release.py` and `tests/_frames.py` are `GLOBAL`, `tasks/allocation.py` is under `tasks/`, and eight modules change. **A push runs only part of it**: CI's `mutation` job runs `tools/mutation_gate.py --changed-only`, which never escalates — it sweeps the eight modules this plan changes and stops there (`select()` on this plan's files, 2026-09-28, on `main` at `334f6db`: `8 module(s) -- pyproject.toml changed; --changed-only does not escalate on it -- the nightly full sweep covers it; swept: changed modules and their own test files`, selecting `cli`, `health`, `link`, `record`, `run`, `serve`, `taskd`, `web`). Every other module is unswept against this branch's `GLOBAL` changes until the full sweep runs. (Before `334f6db` a `GLOBAL` path made `--changed-only` select nothing at all; the pre-flight found that, and it was fixed on `main`.) The full sweep is every module in the gate's `RETURNS`, split six ways by `--all --shard K/6`, as CI's `mutation-full` job runs it. Do it one of two ways:

- **On GitHub:** push first (Step 5's `git push`), then trigger the sharded sweep on the branch, `gh workflow run ci.yml --ref p4d2b-b2a-controls`; find the run with `gh run list --branch p4d2b-b2a-controls --workflow ci.yml --event workflow_dispatch`, list its jobs with `gh run view <run-id> --json jobs --jq '.jobs[] | "\(.databaseId) \(.name) \(.conclusion)"'`, save each of the six `mutation-full` shards' logs with `gh run view --job <job-id> --log > shard-K.txt`, and read all six, line by line.
- **Locally, as six parallel lanes, each in its own `git archive` copy of the branch tip** — never two lanes in one tree, since the harness neuters a module's file in place. Set `PREPROC` to the `wl-preproc` checkout, and use the venv's `python`:

```bash
PREPROC=/path/to/wl-preproc
tip=$(git rev-parse HEAD)
for k in 1 2 3 4 5 6; do
  lane="${TMPDIR:-/tmp}/p4d2b-b2a-lane-$k"
  rm -rf "$lane" && mkdir -p "$lane"
  git archive "$tip" | tar -x -C "$lane"
  ln -s "$PREPROC" "$lane/wl-preproc"
  (cd "$lane" && WLX_REQUIRE_PREPROC=1 python tools/mutation_gate.py --all --shard "$k/6" \
     > "${TMPDIR:-/tmp}/p4d2b-b2a-gate-$k.txt" 2>&1) &
done
wait
```

Either way it takes hours. Do not commit to the branch while it runs (the sweep is of `$tip`), and never run a suite, edit a test or `git add` inside a lane. **A lane's line that says `timed out` is not a catch** (trap 7): six lanes compete for one machine and each mutant's suite has a 300 s limit, so re-run that function alone, in one lane with nothing else running — `WLX_REQUIRE_PREPROC=1 python tools/mutate.py --returns <R> wl_expcontroller/<module>.py <function>`, `<R>` being the module's value in the gate's `RETURNS` (`None` for every module this plan changes) — and read its line. If it still times out, it is a missing bound: fix the bound in the owning task (Global Constraints). Three of `serve`'s run close to the limit even alone — in the pre-flight's scratch sweep (2026-09-27, a development machine), `start` took 241 s, `offer` 200 s and `_send_frame` 196 s — so expect those three to time out in lanes and re-run them alone first.

**`tools/measure_mark_check.py` is outside every gate mode** — the gate sweeps only `wl_expcontroller/` — so sweep it by hand, in one lane with nothing else running, after the six lanes finish (or while the GitHub run goes):

```bash
WLX_REQUIRE_PREPROC=1 python tools/mutate.py --all --returns None tools/measure_mark_check.py
```

Read its lines the same way as the shards': `_trial`, `_session_check`, `_timed_trial`, `_spread`, `measure`, `report` and `main` each `caught … N failed` with a `<-` naming a test in `tests/test_measure_mark_check.py` (the pre-flight's first sweep found `main` `SURVIVED`; Task 14 now tests it).

Then read every line of every shard's log, not its exit code:
- Zero `SURVIVED` and zero `SKIPPED`.
- Every `caught` shows `N failed` and a `<-` naming tests. `N errors`, a timeout, or a single unrelated test does not count as caught.
- For each function this plan added or changed, find its line and check that the `<-` names a test this plan wrote for it: in `link.py`, `_actor`, `_setting`, `check_schedule`, `_instant`, `_mark`, `_encode_command`, `_decode_command`, `drain`, `_refuse`, `mark_signal`, `_take_mark`, `idle`, `signal`, `deliver`, `_open`, `_reset`, `of`, `encode`, `_telemetry_from`, and `ZmqConsole`'s and `ZmqCommands`' `__init__`; in `taskd.py`, `_next_occurrence`, `_gap`, `set`, `_command`, `_control`, `_feed`, `_code`, `_pause`, `_resume`, `_stamp`, `_settle_stamps`, `_check_marks`, `_mark_note`, `_schedule`, `_cancel`, `_ends`, `_hold`, `_manual_reward`, `_apply_staged`, `controls`, `run`; `run.run_trial`; `record.control`; `cli.render` and `cli.main`; `health._state_text`; in `web.py`, `_clock_time`, `_state`, `_off`, `_scheduled`, `_strip`, `_reward_button`, `_reward_answer`, `_controls`, `_changes`, `_step`, `_field`, `_params`, `fragments`, `page`; in `serve.py`, `host_name`, `names_loopback`, `box_names`, `_person`, `parse_command`, `not_delivered`, `Outbox`'s methods, `_delivered`, `_rewarded`, `make_handler`, `_host_ok`, `may_write`, `_from_the_box`, `_refuse_method`, `do_POST`, `_command`, `do_GET`, `dispatch`, `_signal`, `_remember`, `_recall`, `start`, `close`, `parse_link`, `run`.
- A survivor gets a test that fails without it, in the owning task's test file. A function nothing can test is deleted, not exempted.

- [ ] **Step 3: Record what the gate said**

In `docs/CHECKPOINT.md`'s b2a entry from Task 15, add the gate's result as read in Step 2 — modules swept, `SURVIVED`/`SKIPPED` counts, and any survivor found and how it was closed — the by-hand sweep of `tools/measure_mark_check.py` the same way, and the passed count from Step 1; update the Status table's test count to the same number.

```bash
git add docs/CHECKPOINT.md
git commit -m "Record the b2a mutation sweep and test count"
```

- [ ] **Step 4: Look at it in a browser (manual)**

The suite cannot run the page's script. With a token file outside the repository, start a simulated session with a mark endpoint and the console, in two terminals from the worktree root:

```bash
python -m wl_expcontroller.cli run tasks/fixation_detection.py \
  --allocation tasks/allocation.py --bounds tasks/twelve_hour_bounds.py \
  --root "${TMPDIR:-/tmp}/wlx-b2a" --session-id 2027-01-14_01 --subject REFERENCE \
  --out-of-cage-at "$(date +%H:%M)" --delivered-today 0 --trials 10000000 \
  --set fix_timeout=4.0 --set fix_hold=0.3 --set response_window=0.6 \
  --set target_hold=0.2 --set fix_window=2.0 --set target_window=3.0 \
  --set target_position=10.0 \
  --link tcp://127.0.0.1:5571,tcp://127.0.0.1:5572,tcp://127.0.0.1:5573
```

```bash
python -m wl_expcontroller.cli serve \
  --link tcp://127.0.0.1:5571,tcp://127.0.0.1:5572,tcp://127.0.0.1:5573 \
  --http 127.0.0.1:8080 --health-token-file ~/.config/wlx/health.token --stale-after 5
```

Open `http://127.0.0.1:8080/` and confirm, writing down what was seen:
1. **The name.** Press **P** with no name kept: the prompt asks once. Cancel it: nothing is sent and the line says *not sent: give your name first*. Press **P** again and give a name: the session pauses, the pill reads *paused · since HH:MM:SS*, the button reads *resume (P)*, and reloading the page keeps the name.
2. **Pause holds.** While paused the header's trial number stands still and the out-of-cage clock keeps moving. **P** resumes; the trial number moves again. The feed lists both, with the name.
3. **Mark.** Press **M**: a note box opens with the cursor in it. Type a note containing the letter *m* — it is text, not a second mark — and press Enter: the feed shows *mark N stamped in trial T, frame F* (or *between trials*), then the note with the name. Press **M** and then Esc: the feed says *no note*. Click the mark button twice quickly: two marks, two numbers, in order.
4. **Settings.** On *Task parameters*, click `fix_hold`'s ▲ three times quickly: one change is sent, not three — the card reads *staged → 0.45* and then, a trial later, 0.45; the feed lists *fix_hold 0.30 → 0.45, from trial T*. Type `abc` into `fix_hold` and press Enter: *not sent: fix_hold needs a number*. Type a value above its range: the rig refuses it, and the card and the feed show the sentence.
5. **Scheduled stop.** Schedule *after N more trials* with 50000: the strip shows *stop after trial …* and *set by NAME*, with *cancel*; cancel removes it. Schedule `25:00`: refused with its sentence. Schedule the current minute (`date +%H:%M`): the strip says *at HH:MM on <tomorrow's date>*; cancel it.
6. **Stop.** The stop button asks *stop at the next trial boundary?*; *cancel* closes it; *stop* ends the session: *ended · operator*, the banner *stopped by NAME (box, unverified)*, and the controls say *the session has ended*.
7. **Away from the box.** Start another session and `wlx serve` with `--http 0.0.0.0:8080`, and open the page from another machine on the LAN by the box's name: every control is greyed and says *controls work only at the rig PC until remote sign-in arrives*. From the box, open `http://<the box's name>:8080/`: greyed too (a write needs a `Host` naming loopback). `curl -s -H 'Host: evil.example' http://127.0.0.1:8080/` answers 421 with JSON.
8. **Not delivered.** Start a third session, and kill its `wlx run` outright (`kill -9`, so it publishes nothing more): the page still shows it running until it greys. Press **P**: *not delivered: no rig is connected on …*, after about a second.
9. **Give reward** (Task 13). While trials run, *give reward* is greyed and its title says why. Pause, and it is live, followed by *fluid session N mL*. Click it once: it greys at once and stays grey until the answer, the line says *sent: the rig has the reward command…*, and within a second the fluid total beside it and on *Runtime* rises by `reward_correct` (0.05 mL under `tasks/twelve_hour_bounds.py`), *last given HH:MM:SS: 0.05 mL of reward_correct, given while paused before trial T* appears, the feed lists it with the name, and the trial number stands still. Double-click it: one reward, not two. Stop `wlx serve` with Ctrl-C and click it: the line says *unknown: this page lost wlx serve's answer…* or *not delivered…*, never *sent*, and the fluid total has not moved; start `wlx serve` again. Resume: the button greys again.
10. `controls.jsonl` in the session directory holds every pause, resume, mark, note, reward and schedule above, each note with `pressed_at`, `received_at`, `stamped_at` and both gaps, and each reward with its `ml`.

If any of these fails, fix it in the owning task with a test where Python can reach it, and repeat this step.

- [ ] **Step 5: Push and read CI**

```bash
git push -u origin p4d2b-b2a-controls
```

Then read the branch's push run (`gh run list --branch p4d2b-b2a-controls --event push`): its log, not its verdict — pytest on all three Pythons, and the `mutation` job's `--changed-only` gate, which should select the modules this branch changes and say it did not escalate on the shared files (Step 2). That job is not this branch's mutation check; Step 2's full sweep is, and it must be read before Step 6. **Do not merge to `main`.**

- [ ] **Step 6: Hand the PI the review**

Give the PI numbered items to approve, in plain terms, through the question UI (memory: he wants items, not files, and his decisions asked in the UI):

1. **While paused, the task rewards nothing, a person at the box may give one correct-trial reward per press, and the out-of-cage limit still ends the session** (item 1 as amended at his 2026-09-28 review). A pause holds the session at the end of a trial. No trial runs, so the task gives no reward. A press of *give reward* then gives exactly what a correct trial pays now — the bounded config's `reward_correct` as applied at the press (a size changed during the pause applies from the next trial, not to this reward), through the same path a task's reward takes — counted in the fluid total and toward a "stop after X mL", which ends the session there if it is reached; strobed as its own event code and recorded with who pressed it. At any other time — while trials run, while a pause is still on its way, after the session has ended — a press is refused with a sentence and nothing is given; a config with no `reward_correct` gives nothing; and a press whose answer was lost is reported as unknown, never sent again, with the fluid total to check before pressing again. Every half second the rig still checks the out-of-cage limit exactly as it does between trials, and ends the session on it; the clock keeps running while paused. Pinned by `test_nothing_is_rewarded_while_paused`, `test_the_out_of_cage_limit_still_ends_a_paused_session`, `test_e2e_the_limit_ends_a_session_paused_in_front_of_it`, Task 13's `test_a_manual_reward_*` tests, `test_a_reward_the_rig_takes_and_never_acknowledges_is_unknown_and_sent_once` and `test_e2e_a_reward_pressed_while_paused_is_one_correct_trial_reward_on_the_record`.
2. **A scheduled stop can end a session**, at a clock time, after a number of trials, or after a number of mL this session (read from the same session fluid the console shows). It ends the session like the stop button, naming who set it; the limit is checked first. Pinned by the `test_*scheduled*`/`test_a_stop_*` tests in `test_taskd.py` and `test_e2e_each_kind_of_scheduled_stop_ends_the_session_with_its_reason`.
3. **Reward size can be changed from the console page, still capped by its approved ceiling**: the same path `wlx console --set` uses, checked when offered and applied at the next trial, and only from the box. Pinned by `test_a_console_command_moving_reward_volume_goes_through_its_ceiling` (b1's) and b2a's write tests.
4. **The M8 fix: a malformed setting is refused and never ends the session.** A value that is not a number was able to end a session; now it is refused with a sentence, at the link and again at the session. Pinned by the Task 1 tests and `test_e2e_a_malformed_setting_is_refused_on_the_feed_and_the_session_runs_on`.

And ask, as its own question: **the per-frame mark check's cost** — give him the numbers from Task 14's `docs/measurements/dev-machine/<date>-mark-check.md` as they stand, say that they are CPU time on a development machine and not frame timing, and that V12 measures frames on a rig, which does not exist yet. The spec's rule is that a check that measurably disturbs frames goes back to him before b2a ships; ask whether b2a may ship with V12 on the hardware list, or should wait for it — naming the alternative Plan decision 1 describes (a listener thread) if he would rather not have a socket call in the frame at all.

It merges to `main` by fast-forward only after he approves items 1–4 and answers the question.
