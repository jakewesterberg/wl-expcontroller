# P4d-2a — Close the out-of-cage interval

- **Status:** approved in conversation 2026-09-26 (PI); written spec for PI review.
  **Amended 2026-09-26 (§10)** after the PI's answers on the ELN: §4's wall-to-session
  mapping, §5's console path and `--await-return-for`, and §7 are superseded where §10 says so
- **Date:** 2026-09-26
- **Parent:** S8 §5.2 item 4 (the one welfare limit); S9a §7, §9
- **Welfare-critical:** yes — it touches session-duration tracking. `welfare.py` changes, and
  the slice does not merge before the PI has reviewed §7's numbered list (CLAUDE.md)
- **Followed by:** P4d-2b, the browser console and `/health`
  (`2026-09-26-P4d2b-browser-console-design.md`), which renders and forwards what this adds

---

## 1. Why this comes first

Found on 2026-09-26 while designing P4d-2's `/health` verdict. Each item is read from the
code, not inferred:

1. **Nothing in production records the return to the cage.** `taskd.Session.returned_to_cage`
   exists and is tested, and its only callers are tests. Its docstring expected the prompt
   to arrive with P4d-2's console. `wlx run` takes the departure and never the return, so
   every rig session's out-of-cage interval is left open.
2. **Neither end of the interval is in the session directory.** `config.json` holds the
   parameter layers and `trials.jsonl` the trials. The departure reaches `welfare_notes.jsonl`
   only when a far mark is confirmed or amended. The one number that bounds a session is
   answered from the record or not at all (S9a §9), and today it is not at all.
3. **A `RIG_FIXED` session that ends on a fault cannot be closed.** `run()` marks the
   release at the loop's end on every *normal* ending (`taskd.py`, after the loop), but a
   fault re-raises past it, and `welfare.returned_to_cage` refuses a return while the head
   is recorded as fixed. *Corrected 2026-09-26 while planning: this item first said every
   `RIG_FIXED` `wlx run` session was unclosable, which was wrong for the normal path.*
4. **The clock goes dark when the loop ends.** Since ruling 4 (2026-09-20) the interval is
   counted on the wall until the return, but nothing publishes it after the last trial. A
   console would show a frozen out-of-cage time while the real one runs, and a limit crossed
   after the loop would be seen by nobody.

## 2. Rulings this slice rests on

- **Only cage-to-cage time matters** (PI, 2026-09-19, restated 2026-09-26). Head-post
  release gates nothing and its clock is unchanged. `run()` already marks the release at a
  normal loop end; `await_return` marks it on entry if a fault skipped that, so that
  `welfare`'s release-before-return cross-check is never a dead end and is not removed.
- **The return mark is its own slice, before the browser** (PI, 2026-09-26).
- **A rig session that ended on its limit reads `degraded` on `wl-works` until the return is
  recorded** (PI, 2026-09-26). That verdict is P4d-2b's; the state it reads is this slice's.

## 3. Recording both ends

`record.welfare_note` gains two kinds, written **for every rig session**, not only when a
person confirmed or amended a far mark:

| `kind` | Written when | `how` |
|---|---|---|
| `departure` | `left_cage` accepts the mark | `terminal` |
| `returned` | `returned_to_cage` accepts the mark | `terminal` or `console` |
| `return not recorded` | the process ends with no return on a rig session | the reason |

The existing `departure confirmed` / `departure amended` rows are unchanged and still written
beside `departure` when they apply; a far return that a person confirmed gets a `return
confirmed` row the same way. **There is no `return amended`**: the return is typed at the
moment it is taken, so a corrected time is simply the time entered, and nothing was marked
that an amendment could replace. Each row carries the wall instant and its local clock time with zone, as the
existing rows do, and `by`.

`return not recorded` is written from a `finally`, so an exception or an interrupted prompt
leaves it. A process killed outright leaves no row, and then the absence of a `returned` row
is the signal. Rows are never capped: they are one or two per session.

## 4. The session stays up after the loop

`taskd.Session.await_return()`, called by the owner of a rig session after `run()` returns,
whatever the stop reason. **Cage-side sessions skip it**: there is no interval to close.

- **Publishes a frame every `heartbeat` seconds** (default 1 s — a display cadence for the
  console, not a measurement of this system and not a claim about its timing; it must sit
  well inside `ZmqConsole`'s 5 s receive timeout, or a console waiting for the next frame
  times out between them — found planning, 2026-09-26). Each frame
  reads the out-of-cage time from the **wall**, through the departure anchor.
- **The duration warning keeps running.** Before the limit it is `approaching_limit`'s
  sentence, as during the loop. Past the limit it is `must_stop`'s sentence, because there
  is no loop left to stop and the warning is what tells someone to act.
- **Drains the link** for `ReturnedToCage` and applies it through `returned_to_cage`, under
  one lock shared with the terminal path.
- **Ends when the return is recorded**: one final frame with `phase = closed`, then it
  returns. It never ends on its own otherwise. It takes a `threading.Event` its owner sets
  to give up — `wlx run` sets it when the operator interrupts the prompt — and then it
  publishes nothing further and the owner writes `return not recorded` (§3).

`wlx run` runs `await_return` on a background thread while its main thread holds the
terminal prompt (§5). The two meet only at the lock around the mark.

> **Superseded by §10 (built, then removed in Task 7).** The method below no longer exists:
> every welfare duration is read on the wall, so there is nothing to map. What follows is
> kept as the design that was built and why it failed.

The wall-to-session mapping is one new method on `welfare.Welfare`, the mapping
`returned_to_cage` already performs inline, lifted so both use it:

```python
def now_from_wall(self, wall_now: float) -> float:
    """The session-base instant `wall_now` corresponds to, through the departure."""
```

It refuses (raises `Exceeded`) where there is no anchor — cage-side, or no departure — for
the reason `out_of_cage_seconds` raises on an unmarked rig session. The post-loop frame then
calls the existing `out_of_cage_seconds`, `approaching_limit` and `must_stop` with it, so no
welfare number is computed anywhere new.

## 5. Taking the mark from the box

- **Terminal.** After the loop, `wlx run` prompts `returned to cage at (HH:MM, or now):` and
  applies `welfare.return_needs_confirmation`'s confirm-or-amend flow for a time more than
  thirty minutes off, exactly as `_settle_departure` does for the departure.
- **Console.** A new link command, `ReturnedToCage(at: float, by: str, confirmed: bool)`,
  `at` a POSIX wall instant. `wlx console --returned HH:MM --as WHO [--confirm-return]` sends
  it. A far return sent without `--confirm-return` is refused by `welfare` with the sentence
  a person needs, published as a `Refused`; re-sending with the flag is the confirmation.
  P4d-2b's browser sends the same command, from the box only.
- **Whichever is accepted first wins.** One lock covers the mark. A second return is refused
  by `welfare`'s existing sentence, and a waiting terminal prompt is told the console
  recorded it.
- **The terminal prompt ends.** An empty answer, or three answers that are not an accepted
  mark, end it with `return not recorded` and the reason — a prompt that re-asked forever
  would hang any script, and any test, that answers with a fixed string.
- **`--await-return-for SECONDS`** bounds the wait when only a console can deliver the mark,
  and records `return not recorded (nobody marked it within N s)` when it lapses. Without it,
  a linked run with no terminal waits until a console marks the return or it is interrupted.
- **No terminal and no link.** `wlx run` does not wait for a mark nothing can deliver: it
  writes `return not recorded (no terminal and no console attached)` and exits. This keeps
  headless runs and every existing test working, and the record says why the interval is
  open rather than leaving it open silently.

## 6. Telemetry, schema 5 → 6

| Field | Values | Set by |
|---|---|---|
| `phase` | `running`, `awaiting_return`, `closed` | the loop; `await_return` |
| `stop_kind` | `completed`, `operator`, `limit`, `fault`, or `None` while running | each of `taskd`'s four stop sites |

`stopped_because` keeps its text. `stop_kind` exists because telling a pump fault from a
clean finish by parsing that text would be fragile, and P4d-2b's verdict needs the
distinction. Golden files updated; `SCHEMA` bumps because a console built against 5 would
render an `awaiting_return` frame's advancing clock as a running session.

## 7. For PI review (welfare-critical)

*As amended by §10.* The list first written here is kept in the history; this is the one
to review.

1. **Out-of-cage is counted on the wall clock alone**, from the departure to the return.
   The frame clock never enters a welfare duration, and head-fixation marks are taken on
   the wall too, so every cross-check compares like with like. This replaces
   `welfare.now_from_wall`'s mapping.
2. After the loop, the duration warning continues, and past the limit it reads as
   `must_stop`'s sentence.
3. **The return is taken only at `wlx run`'s terminal**, as a stand-in until the wl-works
   ELN records it, with the same refusals and the same thirty-minute confirmation. There is
   no console or browser path.
4. `departure` and `returned` rows are written for every rig session, not only on
   confirmation.
5. With no terminal, linked or not, `wlx run` records `return not recorded` and exits
   instead of waiting.
6. If a fault skipped the release, `await_return` marks a `RIG_FIXED` session's head
   release on entry, so the return is never refused for a head nobody can release.
7. **The in-session clock** (the session opened to the session ended, on the wall) is
   published and recorded, and bounds nothing.

## 8. Testing (sim first)

Red before green, each against the code as it stands:

- A rig session's directory has no departure row and no return (§1 items 1–2).
- A `RIG_FIXED` session whose loop ended on a fault cannot record a return (§1 item 3).

Then:

- Post-loop frames advance against an injected wall clock, carry `awaiting_return`, and turn
  the warning into `must_stop`'s sentence once the limit passes.
- A `ReturnedToCage` sent by `wlx console` over a real loopback link closes the interval,
  writes the `returned` row with `how = console`, and produces a final `closed` frame.
- The terminal path, through `_ask`, including a far return confirmed and one amended.
- A second return is refused, from either side, and the first stands.
- Headless with no link writes `return not recorded` and exits 0.
- A cage-side session publishes no post-loop frame.
- `stop_kind` at each of the four stop sites.
- `tools/mutate.py` over `welfare`, `taskd`, `link`, `cli` and `record`, read line by line.

## 9. Not in this slice

- The browser, `/health`, and the verdict table — P4d-2b.
- A session summary file for `wl-preproc` to ingest — P4c's, and it will read these rows.
- Any change to how restraint is recorded beyond marking the release at the loop's end.

## 10. Amendment, 2026-09-26: the ELN owns the interval

**What the PI ruled**, asked while the P4d-2b console was being mocked up:

- "out-of-cage should be grabbed from the wl-works eln (not built yet), but there should
  also be a in-session clock that is tracked seperately."
- "Yes, the ELN handles return to cage. you can take it out of this interface."
- The in-session clock: "only shown and recorded."
- Until the ELN exists, `wlx run` keeps taking the return at the terminal: "stand-in."

**What was found that made the first design wrong**, by Task 6's implementer (2026-09-26):
`Session.now()` is accumulated frame time, and in the simulator frames run as fast as the
host allows, so the frame clock outruns the wall. §4 counted out-of-cage in the frame base
and mapped the wall into it through the departure. In the simulator that mapping put a
return typed "now" long before the loop-end head release, so `welfare` refused it, and the
first post-loop frame was itself refused by the restraint cross-check (chair time longer
than out-of-cage). `wlx run` defaults to `rig-fixed`, so the slice's main path failed in the
simulator with default flags. Task 6's tests passed only by running `rig-chaired`.

**The amendment:**

1. **Every welfare duration is on the wall clock.** `welfare` keeps the departure and the
   return as wall instants only. `out_of_cage_seconds`, `approaching_limit`, `must_stop`
   and `preflight` read the wall, so no conversion happens and there is nothing to map.
   `now_from_wall` (Task 1) goes. `head_fixed` and `head_released` take wall instants, so
   the restraint cross-check compares two wall intervals. The trial loop's limit check reads
   the wall clock once per trial boundary where it read the frame clock. The frame clock
   times trials and nothing else. When the ELN exists, its departure and return are wall
   instants already, so this is also the shape it needs. The wall is read through one
   anchor per session (Ruling 8, Task 7 fix round 1): `Session.wall_now()` is `time.time()`
   as it read when the session was created, carried forward on `time.monotonic()`, so a
   host-clock step mid-session cannot move the interval.
2. **The return is terminal-only, as the ELN's stand-in.**
   - `link.ReturnedToCage` is removed (Task 4 reverted). The browser will not send it, and
     the ELN's return will reach the box through the lab-host protocol, not this link.
   - `wlx console --returned` is not built (the first plan's Task 7).
   - `--await-return-for` is removed. A linked run with no terminal has nothing that can
     deliver the mark, so it records `return not recorded (no terminal)` and exits, as a
     headless run does.
   - The post-loop phase stays: it publishes the out-of-cage clock and the warning while
     the terminal waits.
3. **The in-session clock** is the session's own interval, the session opened to the
   session ended, on the wall. It is published as `in_session_seconds` (added to telemetry
   schema 6, which has not left this branch). It is recorded as `session opened` and
   `session ended` rows in `welfare_notes.jsonl`, beside `departure` and `returned`,
   because that file already holds the session's clock marks. It bounds nothing. For
   `wlx run`, it opens when `run()` opens the record, and ends when the process settles the
   return, or records why it could not.

