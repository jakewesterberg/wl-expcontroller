# P4d-2a — Close the out-of-cage interval

- **Status:** approved in conversation 2026-09-26 (PI); written spec for PI review
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
3. **A `RIG_FIXED` session in `wlx run` cannot be closed.** It marks head-fixation at 0 and
   never the release, and `welfare.returned_to_cage` refuses a return while the head is
   recorded as fixed.
4. **The clock goes dark when the loop ends.** Since ruling 4 (2026-09-20) the interval is
   counted on the wall until the return, but nothing publishes it after the last trial. A
   console would show a frozen out-of-cage time while the real one runs, and a limit crossed
   after the loop would be seen by nobody.

## 2. Rulings this slice rests on

- **Only cage-to-cage time matters** (PI, 2026-09-19, restated 2026-09-26). Head-post
  release gates nothing and its clock is unchanged. `wlx run` marks the release at the loop's
  end, the mirror of the fixation it already marks at 0, so that `welfare`'s
  release-before-return cross-check stops being a dead end rather than being removed.
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
beside `departure` when they apply; the return gets `return confirmed` / `return amended` the
same way. Each row carries the wall instant and its local clock time with zone, as the
existing rows do, and `by`.

`return not recorded` is written from a `finally`, so an exception or an interrupted prompt
leaves it. A process killed outright leaves no row, and then the absence of a `returned` row
is the signal. Rows are never capped: they are one or two per session.

## 4. The session stays up after the loop

`taskd.Session.await_return()`, called by the owner of a rig session after `run()` returns,
whatever the stop reason. **Cage-side sessions skip it**: there is no interval to close.

- **Publishes a frame every `heartbeat` seconds** (default 5 s — a display cadence for the
  console, not a measurement of this system and not a claim about its timing). Each frame
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

1. `welfare.now_from_wall` — the post-loop clock is the departure's wall anchor, the same
   mapping `returned_to_cage` has used since ruling 4, now shared.
2. After the loop, the duration warning continues, and past the limit it reads as
   `must_stop`'s sentence.
3. The return can arrive from a console (`ReturnedToCage`), with the same refusals and the
   same thirty-minute confirmation as the terminal.
4. `departure` and `returned` rows are written for every rig session, not only on
   confirmation.
5. With no terminal and no console, `wlx run` records `return not recorded` and exits
   instead of waiting.
6. In `wlx run`, a `RIG_FIXED` session's head release is marked at the loop's end.

## 8. Testing (sim first)

Red before green, each against the code as it stands:

- A rig session's directory has no departure row and no return (§1 items 1–2).
- A `RIG_FIXED` `wlx run` session cannot record a return (§1 item 3).

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
