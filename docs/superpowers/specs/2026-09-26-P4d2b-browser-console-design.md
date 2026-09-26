# P4d-2b — The browser console and `/health`

- **Status:** §1–§3 approved in conversation on 2026-09-26 (PI). §4 covers slice b1, the
  read-only console, and was approved the same day. Slices b2–b6 get their own sections as
  each is designed.
- **Date:** 2026-09-26
- **Parent:** S9a §6–§9; ADR-0008; `architecture.md`'s `console` and `labhost` rows
- **Depends on:** P4d-2a (`2026-09-26-P4d2a-return-to-cage-design.md`, as amended in its
  §10): `phase`, `stop_kind` and `in_session_seconds` in telemetry schema 6. The page sends
  no return to the cage: the wl-works ELN owns it (PI, 2026-09-26)

---

## 1. Transport and rendering (decided)

- **Stdlib `ThreadingHTTPServer`**, the stack `wl-preproc`'s responder already runs. No
  new dependency.
- **Server-sent events** carry telemetry to browsers; writes are JSON `POST`s.
- **Panes are rendered to HTML in Python** and pushed as fragments; the page's JavaScript
  only swaps them in. The point is testability: "`fluid session` and `supplement` are never
  dropped" (S9a §9) becomes a pytest assertion on the renderer, as `cli.render` is tested.
- **WebSockets are deferred to the replica pane**, if V11 shows a browser can carry it at
  display rate — the one place binary frames would matter. That is an added endpoint for one
  pane, not a rewrite. **Known limit, accepted:** over HTTP/1.1 a browser holds about six
  connections per host, and each event stream holds one, so a seventh console tab on the
  same box in one browser would stall (MDN's server-sent events guide; not re-verified
  2026-09-26). S9a §7 is amended from "HTTP/WS" when this slice lands.

## 2. Process and security (decided; the write rules apply from slice b2)

- `wlx serve --link PUB,REP --http HOST:PORT --health-token-file PATH`, its own process.
  One `ZmqConsole`. A telemetry thread keeps the latest frame; a command thread owns the
  REQ socket and takes commands from a queue, so each ZMQ socket has one owning thread.
  Each browser gets a bounded queue that drops its oldest frames when it falls behind.
  Restarting `wlx serve` changes nothing in `taskd`.
- **Reads are open to the LAN; writes only from the box, until P4d-3** (PI, 2026-09-26).
  `POST /commands` is accepted only when all hold: loopback peer; `Host` names loopback
  (against DNS rebinding); `Origin` is the box's own page (against a cross-site post from a
  page open in the rig PC's browser); `Content-Type: application/json` (forces a preflight
  this server never approves). A refused write says *writes are accepted only from this box
  until P4d-3*, and the page greys its controls with the same sentence.
- **Attribution until P4d-3:** the box's page asks for a name once and the console records
  `NAME (box, unverified)` — S9a §6: a forgeable name is worse than none, because it is
  believed.
- **`/health`**: `Authorization: Bearer` from a token file, never the repository;
  `hmac.compare_digest`; one identical `401` for missing or wrong credentials; `404` for
  unknown paths, `405` for wrong methods, and no stdlib default error page — the rules of
  `wl-preproc`'s `responder/handler.py`, read 2026-09-26.

## 3. Telemetry and `/health` (decided)

**Telemetry, schema 6 → 7** (P4d-2a takes 6). Each field from the object the record is
written from:

- `params` — name, unit, low, high, current value, and whether a welfare ceiling checks it;
  the parameter row is generated from it
- `task`, `allocation`, `bounds_config` — S9a §3's configuration information. Display mode
  and stimulus calibration have no source yet and render as such
- `floor_ml`, `out_of_cage_limit_s` — the day's floor, and the ceiling the clock runs
  against (`None` cage-side)

Drops, tracker staleness and RHX margin have no source and render *not measured*, never 0.

**Behavioral counts, no rollup** (PI, 2026-09-26). Total trials, then every outcome that
occurred with its count, grouped by `Outcome`'s existing documented families — target,
distractor, withhold, no engagement, breaks, rig — encoded on the enum as data rather than
left in comments. No correct/error/aborted definition is invented; one can be added when the
PI defines it (open: fixed on the enum or per task, and where `early_response`,
`late_response` and `no_response` fall). Shown identically on the Working? pane and on
`/health`.

**One rollup is ruled, for the strip only** (PI, 2026-09-26): its *correct* counts `correct`
plus `correct_reject`, since both are the right answer on their trial. Every other count
stays unrolled.

**`/health`** is `wl_preproc.contracts.protocol.HealthResponse`, schema version 1: readings
are plain text, with `<`, `>` and `&` spelled out as `wl-preproc`'s `plain_text` does.
Readings: session (id · subject · task); state; time out of cage against its limit, or
*cage-side, no limit*; the duration warning when active; fluid this session; supplement
owed; the behavioral counts above; age of the last frame. **Exactly one is featured**,
because wl-works' home page shows only the first and wl-preproc's responder features
exactly one. It is the most urgent (PI, 2026-09-26, amending the five first marked here):
- the duration warning when active;
- else the state, when the session faulted or ended on the limit and the animal is not back;
- else the last frame's age, when the stream went stale;
- else the time out of cage. `actions` is
always empty — no welfare action goes through `wl-works`.

| Situation | Verdict |
|---|---|
| Running normally, or no session attached yet | `ok` |
| Duration warning active | `degraded` |
| No frame for `--stale-after` (default 30 s, a display choice) while the last said running | `degraded` |
| Ended by the out-of-cage limit, **until the return is recorded** (PI, 2026-09-26) | `degraded` |
| Ended otherwise (completed, operator stop), or ended on the limit and since returned | `ok`, with the reason as a reading |
| Ended by a fault | `down` |

`unknown` is never emitted: it is `wl-works`' word for a silent host. Contract-tested
against `HealthResponse` itself, imported at test time with `WLX_REQUIRE_PREPROC=1`.

## 4. Slice b1: the read-only console (approved 2026-09-26)

The mockup (`docs/superpowers/mockups/2026-09-26-console-mockup-v12.html`) is the page's
design, and the rulings held below say what each part of it is for. Each slice builds the
parts whose data exists. b1 builds the page a person reads: nothing on it writes.

### 4.0 Rulings held from the mockup rounds

Every ruling the PI made while the mockup was iterated (2026-09-26). Each binds the slice that
builds its part; S9a is amended to match when that slice lands.

- **The always-visible strip carries four cells**: fluid today / floor, out-of-cage time /
  12:00, correct / trials for the session, and time since the last reward. Fluid session
  moves to the runtime tab and the end-of-session summary; the supplement moves to the
  end-of-session summary. Asked against the 09-20 ruling that allowed zero-reward sessions
  *because* fluid session and supplement were always visible (S9a §9): "fine as is". What
  keeps an unpaid working animal visible is fluid today standing still while the time since
  the last reward grows. S9a §9 is amended to say so when this section is written.
- **The return to the cage is the ELN's, not this page's.** Asked whether the wl-works ELN
  (not yet built) records the return as well as the departure: "Yes, the ELN handles return
  to cage. you can take it out of this interface." The page reads out-of-cage, on the wall
  clock alone, and offers no →cage control; a session ends with an explicit "end session".
- **An in-session clock, kept separately**: from opening the session to ending it,
  expcontroller's own, never mixed with out-of-cage. Asked whether it bounds anything:
  "only shown and recorded."
- **Ending a session packages the code it used**: "an end session function that packages
  all of the interface (wl-expcontroller) and task code that was used in the session ...
  saved and packaged for a seperate backup that can be uploaded to github (maybe?) for
  tracking what was used session to session." Mocked as a package in the session directory
  (so it travels to wl-nas) plus one commit per session to a separate code-record repo.
  Open: which host pushes it to GitHub.
- **Nothing runs until the task library is pulled**: "a button next to the task, that must be
  pressed before anything can run in a new session that pulls the task library from github."
  The pulled commit is recorded with every run. The library is wl-mllib, which is not
  built out yet and will be renamed. When GitHub cannot be reached, the last version pulled
  runs after a warning and a person's confirmation. The code package goes to wl-nas with
  the session, and pushing it to GitHub is proposed as wl-preproc's job (all PI, 2026-09-26).
- **Load parameters from an earlier session**: "a feature that can pull task parameters for
  an animal from a log that is perhaps stored in the eln ... preload parameters from a
  previous session." The box cannot ask wl-works for the log, so its source is open: pushed
  when a session opens, or read from earlier session records on the box and wl-nas.
- **The GUI review's top ten are accepted** ("I like all of the suggestions at the top"),
  from `docs/superpowers/mockups/2026-09-26-console-review.md` §1 (mockup: `docs/superpowers/mockups/2026-09-26-console-mockup-v12.html`):
  1. a mark control (M);
  2. a trial-phase timeline;
  3. the strip and actions kept in full screen;
  4. a pre-flight checklist that gates start;
  5. start values and the shaping step remembered from the last session;
  6. outcome ticks on Runtime, and trials/min;
  7. recording status;
  8. a scheduled stop and a 60-minute notice;
  9. stalled-animal and tracker alerts;
  10. eye-map quality and recenter drift.
  
  The review's welfare questions were set aside: "the welfare ones are irrelevant, we can
  ignore."
- **Runs follow the plan, and an unplanned run is explicit.** Asked how S8 §1 (blocks are
  planned in wl.works before the session, and wl-preproc quarantines unplanned blocks,
  lowering the timing tier) meets the mockup's free task choice, the PI chose plan first,
  unplanned allowed. The page runs the day's plan in order, pushed from wl.works. A run
  outside the plan is an explicit "unplanned run", with a warning that it lowers the
  session's timing tier.
- **P4d-2b is built in six slices, in this order** (PI, 2026-09-26):
  - **b1 — read-only:** the server, the stream, and the read-only page from today's
    telemetry, plus `/health`.
  - **b2 — writes from the box:** parameters, stop, pause, mark, scheduled stop.
  - **b3 — sessions from the page:** new / load / end session, the task-library pull and
    pre-flight. This needs a service on the box that holds a session across runs.
  - **b4 — simulation** with mouse gaze.
  - **b5 — training tools and manual reward** (welfare-critical).
  - **b6 — end of session:** the code package and the wl-nas transfer.
  
  Overlays, behavior plots, online analysis, the parameter log and RHX status come later,
  behind the parts they depend on.

### 4.1 Telemetry, schema 6 → 7

Schema 7 carries §3's fields, plus three more for the strip and the ticks:

- `last_reward_at`: the wall instant of the last reward delivered, taken where `welfare`
  records a delivery; `None` before the first.
- `recent_outcomes`: the last 60 outcomes' wire strings, oldest first, capped like
  `refusals`.
- `in_session_seconds`: P4d-2a's.

Trials per minute is derived by `wlx serve` from `trial_index` over the wall time of the
frames it has seen in the last five minutes, and the page labels it as derived. It is not a
welfare number and bounds nothing.

### 4.2 What the page shows

- **Header:**
  - the wl.works logo, and a state pill (from `phase` and `stop_kind`);
  - session · subject · deployment · block · trial · in session;
  - presence: this box, or N LAN viewers;
  - a magenta ✕ that closes this page's stream.
- **Strip:** four cells:
  - fluid today / floor;
  - out-of-cage time / limit;
  - correct / trials, with % and trials per minute;
  - time since the last reward.
  
  Fluid session and the supplement are shown on Runtime and End of session instead, as ruled
  in the rulings held above.
- **Runtime:**
  - trials: the last 60 outcomes as ticks colored by family, with a legend;
  - this run: counts by family, with no rollup;
  - still needed (`owed`);
  - *Wrong?*: hangs, with drops, tracker staleness and RHX margin shown as *not measured*;
  - *wl-works sees*: the `/health` readings, as they would be sent;
  - changes: staged and refused, with `refusals_dropped` when it is not zero.
- **Task parameters, read-only:** one card per entry in `params`: value, unit, range, the
  ceiling flag, and a staged marker.
- **Setup, read-only:** session, subject, deployment, bounds config, allocation.
- **End of session, read-only:** supplement owed (`shortfall_ml`), fluid session,
  out-of-cage time, in-session time, and the stop reason.
- **Fonts are served by the box** (PI, 2026-09-26): IBM Plex Sans, Plex Sans Condensed,
  Plex Mono and Newsreader are bundled and served from `wlx serve`, so the page keeps the
  wl-works look and never reaches the internet. Each font's license is verified against its
  primary source and entered in ADR-0004's inventory when it is added.
- **Right column:** honest placeholders, so the layout never shifts and nothing pretends to be
  live (PI, 2026-09-26): *replica · V11*, *subject display · no source yet*,
  *sound · not measured*, *display · not measured*.
- **Absent until their slices:** every write control, and overlays, behavior, training tools,
  online analysis, full screen, pre-flight and simulation.

### 4.3 When the stream falters

- **On connect:** one full render, then a fragment per frame.
- **Stale** (no frame for `--stale-after`): a banner reading *stream stale · last frame N s
  ago*, and the values are greyed.
- **Lost:** a banner reading *stream lost*. The browser reconnects on its own and re-renders in
  full when it does.
- **The ✕** closes the page's stream and says *disconnected · the session keeps running on the
  box*, with a reconnect button.

### 4.4 Testing (sim first)

- **The renderer is pure** (telemetry in, HTML fragments out) and is tested like `cli.render`:
  - fluid session, supplement, out-of-cage time, the duration warning, and
    `refusals_dropped` when it is above zero are never dropped;
  - *not measured* is never rendered as 0;
  - every telemetry string is HTML-escaped. A refusal carrying `<script>` is the test.
- **The handler:** `GET /`, `GET /events` and `GET /health` (bearer) are served. Everything
  else gets 404 or 405, with no stdlib error page. b1 has no `POST`.
- **End to end:** `wlx run --link` in the simulator and `wlx serve`, on loopback. An HTTP
  client reads the event stream and sees the trial count advance, then the ended state.
- **`/health`** is contract-tested against `HealthResponse` with `WLX_REQUIRE_PREPROC=1`.
- **The mutation gate's module lists** gain the server and the web renderer.
- **The page's JavaScript** only opens the stream, swaps fragments by id, and runs the stale
  timer, so everything worth testing is in Python.

## 5. Not in this slice

- Plots (accuracy over time, RT distribution, accuracy by position) — their own slice, with
  the per-trial RT and bounded history they need (PI, 2026-09-26)
- OAuth and the `Verified`/`Local` actor — P4d-3
- The replica pane — gated on V11
