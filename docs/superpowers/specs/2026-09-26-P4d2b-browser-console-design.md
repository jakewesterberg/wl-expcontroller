# P4d-2b — The browser console and `/health`

- **Status:** §1–§3 approved in conversation on 2026-09-26 (PI). §4 covers slice b1, the
  read-only console, and was approved the same day. §5 covers slice b2, split into b2a
  (controls from the box) and b2b (remote sign-in through wl-works); b2a's design was
  approved in conversation on 2026-09-27, section by section, and b2b's decisions so far
  are recorded in §5.7. Slices b3–b6 get their own sections as each is designed.
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
- **Reads are open to the LAN; writes from the box in b2a, and from people signed in to
  wl-works in b2b** (PI, 2026-09-26; amended 2026-09-27, when the PI asked that "folks that
  are logged into wl-works" be able to write too — which replaces this bullet's earlier
  "until P4d-3"; see §5.7). A write from the box — `POST /commands` without a wl-works
  token — is accepted only when all hold: loopback peer; `Host` names loopback (against
  DNS rebinding); `Origin` is the box's own page (against a cross-site post from a page
  open in the rig PC's browser); `Content-Type: application/json` (forces a preflight this
  server never approves). Until b2b, a refused write says *controls work only at the rig
  PC until remote sign-in arrives*, and the page greys its controls with the same
  sentence.
- **Every request is answered only when its `Host` names this console** (2026-09-27, §5.3):
  loopback, the box's own host name and addresses, and names given with `--allow-host`.
  Anything else is refused, which closes DNS rebinding on the LAN-open reads too; b2b needs
  each rig reached by a known, registered name anyway.
- **Attribution from the box:** the box's page asks for a name once and the console records
  `NAME (box, unverified)` — S9a §6: a forgeable name is worse than none, because it is
  believed. b2b adds the verified actor for signed-in people (§5.7).
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
Readings: session (id · subject · task; while nothing readable has arrived but frames
are being refused, "a session is sending on ENDPOINT, but in a format this console cannot
read", the PI's wording, 2026-09-27); state; the reason a frame was refused, when one
was (Ruling 11; approved by the PI, 2026-09-27); time out of cage against its limit,
or *cage-side, no limit*; the duration warning when active; fluid this session; supplement
owed; the behavioral counts above; age of the last frame. **Exactly one is featured**,
because wl-works' home page shows only the first and wl-preproc's responder features
exactly one. It is the most urgent (PI, 2026-09-26, amending the five first marked here):
- the duration warning when active;
- else the state, when the session faulted or ended on the limit and the animal is not back;
- else the refused frame's reason, when a frame was refused since the last one this console
  could read (Ruling 11; approved by the PI, 2026-09-27);
- else the last frame's age, when the stream went stale;
- else the time out of cage. `actions` is
always empty — no welfare action goes through `wl-works`.

| Situation | Verdict |
|---|---|
| Running normally, or no session attached yet | `ok` |
| Duration warning active | `degraded` |
| No frame for `--stale-after` (default 30 s, a display choice) while the last said running | `degraded` |
| A frame arrived that this console cannot read (another schema, or no frame at all), until the next one it can — at once, not after `--stale-after`; a held fault stays `down` (Ruling 11; approved by the PI, 2026-09-27) | `degraded` |
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
  The pulled commit is recorded with every run. The library is wl-exptasks (wl-mllib until 2026-09-26),
  which is not built out yet. When GitHub cannot be reached, the last version pulled
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

Schema 7 carries §3's fields, plus four more for the strip and the ticks:

- `last_reward_at`: the wall instant of the last reward delivered, taken where `welfare`
  records a delivery; `None` before the first.
- `recent_outcomes`: the last 60 outcomes' wire strings, oldest first, capped like
  `refusals`.
- `in_session_seconds`: P4d-2a's.
- `wall_at`: the frame's own instant on the session's anchored clock, the one wall reading
  `Telemetry.of` already takes, so that `wlx serve` gives the time since the last reward as
  `wall_at − last_reward_at` plus its own steady-clock time since the frame arrived and never
  subtracts its host clock from a session instant, which a host-clock step would throw off
  (ledger Ruling 1, 2026-09-27).

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

- **On connect:** one full render, then the fragments that changed, once per frame and once
  per keepalive interval between frames, each re-rendered from a fresh snapshot, so what
  ages between frames — the time since the last reward, *wl-works sees* — moves on the page.
  Every event carries `age`, the seconds `wlx serve` has held the latest frame on its steady
  clock (`null` before any) (Ruling 12, 2026-09-27).
- **Stale** (no frame for `--stale-after`): a banner reading *stream stale · last frame N s
  ago*, and the values are greyed. The page's timer runs only while frames are due, from a
  baseline of the event's arrival less its `age`, both on `performance.now()` (monotonic,
  so a browser clock step cannot skew it): stale once *now − baseline* reaches
  `--stale-after` (`>=`, matching `/health`'s own boundary), and N is *now − baseline*. So
  a page that connects onto an already-old frame, or is woken by a refused one, does not
  restart the clock, and a `null` age runs no timer (Ruling 12, 2026-09-27).
- **Lost:** a banner reading *stream lost*, and the values are greyed as when stale
  (2026-09-27: the stale timer stands down while the stream is lost, so without this the
  banner sat over full-color numbers). The browser reconnects on its own and re-renders in
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

## 5. Slice b2: controls (b2a approved 2026-09-27)

b2 is split in two (PI, 2026-09-27): **b2a**, the controls, sent from the box; then **b2b**,
the same controls for people signed in to wl-works. b2a ships and is used while wl-works
registers the rigs and the rigs gain their route to it (§5.7), which b2b cannot do without.

### 5.0 Rulings (PI, 2026-09-27, asked in plain terms)

- **Pause shows a plain background:** the task's background color, nothing drawn on it.
- **A mark goes to the session record and into the neural recording's event stream**, and
  **it is stamped in the frame it reaches the rig, not at the next trial boundary.** Asked
  whether boundary stamping was acceptable, the PI answered that marks must be instant.
- **A setting is sent when the arrows stop being clicked** (the mockup's debounce), and shows
  *staged* until the next trial.
- **No earlier limit warning:** the 30-minute warning stays the only one. The GUI review's
  item 8 proposed an earlier stage; it is dropped.
- **People signed in to wl-works may write** (§2), and **they get every b2 control, reward
  size included**, still capped by its approved ceiling. The rig PC keeps every control.
  This supersedes the line in wl-expcontroller's 2026-08-31 handover to wl-works
  (`wl-works/HANDOVER-wl-expcontroller.md`) that reward, stimulation and parameter changes
  need a person at the console — for signed-in, attributed writes. wl-works is told so
  with b2b.
- **Rig machines may connect to wl-works** ("i think its fine if the rig machines can
  connect to wl-works"). A permission, not a route: see §5.7.

### 5.1 What the rig does

Commands are still read by `taskd` only at a trial boundary (`taskd.py`, the loop's
`link.drain()`), except the mark's own signal (below).

- **Commands on the wire.** Today's closed union, `SetParameter | Stop`, gains `Pause`,
  `Resume`, `Mark`, `ScheduleStop` and `CancelScheduledStop`, each carrying `by`. Every one
  is written to the session record with who sent it and when.
- **M8 closes first.** `SetParameter.value` is a type hint that nothing enforces: a string
  reaching `bounds._finite` raises `TypeError`, which `Session._command` does not catch, so
  `run()`'s fault handler ends the whole session. The value is checked where the command is
  decoded (a finite real number, not a `bool`, or a string for a categorical parameter)
  and a bad one becomes a refusal with a sentence. `Session._command` also refuses on a
  type error, as a backstop. The session never ends because a setting was malformed.
- **Pause.** At the next trial boundary the loop holds: no trial runs, the display shows the
  task's background color, and nothing is rewarded. While paused the rig still, once per
  housekeeping interval, drains commands (resume, stop, marks, schedules, settings),
  publishes telemetry, and **checks the out-of-cage limit with `welfare.must_stop`, ending
  the session on it exactly as between trials**. The out-of-cage clock keeps running.
  Settings staged while paused apply when trials resume. Stop while paused ends the
  session. Pause and resume are recorded, and are strobed as framework events (`pause`,
  `resume`) so the recording shows the gap.
- **Mark, stamped instantly.** Draining every command per frame would break the trial loop's
  rules, so a mark has two parts:
  - a **signal**: a fixed-size sequence number the loop checks once per frame with no
    allocation and bounded work, and on seeing it strobes `operator_mark` in that frame.
    Proposed mechanism, settled by the plan and the measurement: a third loopback socket on
    the link, read per frame through its `EVENTS` option and `recv_into` a preallocated
    buffer. The check runs between trials and while paused too;
  - the **note**, with who sent it, as an ordinary `Mark` command, drained at the next
    boundary and joined to its stamp by the sequence number.

  The record keeps three instants: when M was pressed (the browser's clock, labeled as
  such), when `wlx serve` received it, and when the rig stamped it (its session clock and
  frame). The gap between them is recorded, never hidden.
- **Scheduled stop**, held by `taskd`, so a closed page cannot lose it. Three kinds:
  - at a clock time on the rig's session clock — the next occurrence of that time,
    within 24 hours;
  - after N more trials, counted from when the schedule is accepted, and shown as the
    target trial number;
  - after X mL this session, read from `welfare`'s session fluid.

  Checked at each trial boundary (and while paused), it stops the session like the stop
  button: `stop_kind` `operator`, the reason *scheduled stop (…) set by NAME*. One at a
  time: a new schedule replaces the old, and `CancelScheduledStop` removes it.
- **Settings** keep today's behavior: validated when offered, staged, applied at the next
  trial boundary, every change recorded.
- **Telemetry schema 8** adds what the page needs: whether the session is paused and since
  when, the scheduled stop (kind, target, who), and a bounded list of recent control events
  (pause, resume, mark with its note, schedule, cancel) for the changes feed. A schema-7
  reader refuses schema 8, as §3's schema rule already says.
- **Event codes.** `operator_mark`, `pause` and `resume` are new framework event names in
  the allocation (`codes.Allocation.code_for`), in the task-specific range while ADR-0007's
  `TaskEvent` range is being moved; wl-exptasks owns the final numbering.

### 5.2 The page

- **Settings:** each parameter card gets up/down arrows and an input. A change is sent about
  600 ms after the last click (a debounce, housekeeping and not a measurement). The card
  shows *staged* until the next trial, then the new value. A refusal shows on the card and
  in the feed, with its sentence.
- **Stop:** a button with a confirm step (*stop at the next trial boundary?*).
- **Pause / resume:** one button, and the **P** key.
- **Mark:** the **M** key, or a button, sends the signal at once. A note box then opens:
  Enter attaches the note to that mark and Esc leaves it bare.
- **Scheduled stop:** a small form (clock time, N trials, or mL this session). While a
  schedule is active the strip shows it, for example *stop at 14:30 · set by jake*, with a
  cancel button.
- **Keys** do nothing while a text box has focus.
- **The changes feed** lists every setting change, refusal, pause, resume, mark (with its
  note) and schedule, with who did it, rendered in Python like every other pane.
- **Name:** the box's browser asks once and remembers it locally; commands carry it and are
  recorded as `NAME (box, unverified)`.
- **Everywhere but the box**, the controls are greyed with the §2 sentence.
- **The script's scope grows** past §4.3's list: it also sends commands, debounces the arrows,
  handles P and M, and asks for the name. It still renders nothing itself.

### 5.3 Sending

- **`POST /commands`** takes one JSON command. It is accepted only under §2's four checks,
  and its body is validated before anything is queued. `wlx serve` gets the **command
  thread** §2 always named: it alone owns the REQ socket and takes commands from a bounded
  queue.
- **The page is told the truth about delivery.** *Sent* only when `taskd` has acknowledged
  receipt. *Not delivered* when the REQ exchange times out, after which the socket is reset
  (a REQ socket cannot send twice without a reply). *Busy* when the queue is full. Whether
  the rig accepted or refused a command shows in the feed, from telemetry, as today.
- **The mark's signal** goes on its own path to the rig's mark socket as soon as it
  arrives, ahead of the queue.
- **`Host` is checked on every request** (§2). `--allow-host NAME`, repeatable, adds names;
  the defaults are loopback and the box's own host names and addresses. A refused request
  gets a JSON 421 and no page.

### 5.4 Testing, and the measurement

- **Sim first, end to end:** a real `wlx run --link` in the simulator and a real `wlx serve`,
  on loopback, driven through `POST /commands` the way the page drives it:
  - a setting goes from staged to applied at the next trial;
  - a malformed setting (M8) is refused, shown in the feed, and the session runs on;
  - pause holds `trial_index`, keeps the out-of-cage clock running, and still ends the
    session when the limit arrives mid-pause; resume continues;
  - a mark puts `operator_mark` into the recorded event stream in the frame it arrives,
    and the record holds its three instants and its note;
  - each kind of scheduled stop ends the session with its reason, and cancel removes it;
  - a write from a non-loopback peer, or to an unknown `Host`, is refused;
  - with `taskd` gone, the page is told *not delivered*.
- **The renderer** stays pure and is tested as in §4.4, with the new controls, feed rows and
  strip item.
- **The measurement** (CLAUDE.md: no timing claim without one). A script in `tools/`
  measures the per-frame mark check's cost in the frame loop, with and without it, and
  commits its results under `docs/measurements/`. The effect on real frame timing is added
  to the hardware verification list. **If the check measurably disturbs frames, it goes back
  to the PI before b2a ships.**
- **The mutation gate** sweeps every changed module, read line by line (trap 7).

### 5.5 Human review before b2a merges

Welfare-critical by CLAUDE.md, given to the PI as numbered items in plain terms:

1. While paused, nothing is rewarded, and the out-of-cage limit still ends the session.
2. A scheduled stop, including "after X mL", can end a session.
3. Reward size can be changed from the console page, still capped by its approved ceiling.
4. The M8 fix: a malformed setting is refused and never ends the session.

### 5.6 Outside this repository

- The three new event names go into the allocation; wl-exptasks owns the final numbering.
- With b2b, not before: tell wl-works that its handover's "a person at the console" line
  is superseded for signed-in writes (§5.0), and ask it to register each rig's client.

### 5.7 b2b, remote sign-in: decided so far (PI, 2026-09-27)

Designed in full as its own section when b2a has shipped. Decided now:

- **Who:** people signed in to wl-works, with every b2 control (§5.0).
- **How:** **the browser holds the wl-works access token and presents it with each command**,
  and the rig verifies it. The PI chose this over the rig holding its own sign-in session,
  knowing that **a deactivated account keeps working until its token expires**.
- **What wl-works offers** (its source, read 2026-09-27):
  - a full OAuth2/OIDC provider (better-auth 1.7.1's `mcp()` plugin, with `jwt()`);
  - an access token that is an RS256 JWT, verifiable offline against `GET /api/auth/jwks`,
    **only when the client asks for a `resource`** — otherwise it is opaque;
  - `/oauth2/introspect` for a live check;
  - a ban or deactivation does not invalidate a JWT already issued.
- **Needs outside this repo:**
  - a registered client, with a redirect URI, per rig name (a wl-works ask);
  - **a network route from each rig to wl-works.** Today wl-works sits behind a rented VPS
    front door, and the lab LAN has no route to its WireGuard side. The permission is the
    PI's (§5.0); the route is infrastructure, and his.
- **Carried from S9a §6:**
  - the actor is `Verified(person, issuer, token id)` for a signed-in person and stays
    `NAME (box, unverified)` at the box;
  - the box path is a permanent peer, never an emergency hatch;
  - a token expiring mid-session interrupts nothing.

## 6. Not in this slice

- Plots (accuracy over time, RT distribution, accuracy by position) — their own slice, with
  the per-trial RT and bounded history they need (PI, 2026-09-26)
- The replica pane — gated on V11
- **Cameras** — their own package, **P9**, designed 2026-09-27
  (`docs/superpowers/specs/2026-09-27-P9-camera-system-design.md`). It supersedes the single
  "animal camera" first sketched here the same day. P9 is one headless camera box per rig,
  part of expcontroller, running 2–4 dual-purpose Blackfly S cameras (8 at most) that
  record behavior and serve as the always-on view of the animal. They are
  primary-triggered at 200 fps, and a camera failure pauses trials through b2a's pause. P9
  is built after b2a.
