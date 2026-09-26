# Review of the expcontroller console mockup (v9)

Reviewed 2026-09-26 against `expcontroller-console.html` ("Mockup v9"). Every scenario
button was rendered in every tab at 1440×1000 (plus tall, narrow, light-theme, LAN-viewer,
design-notes-on, full-screen, simulation and 390 px phone variants). Screenshots are in
`review/shots/`, the wrapped page variants in `review/variants/`, and the script that made
them is `review/shoot.py`. Where a claim is about behavior a still cannot show, the element
id or function in the file is named.

The decisions in the brief (strip, right column, toolbar and hotkeys, tab list, ELN owns
out-of-cage, in-session clock bounds nothing, wl-works look, sim rig and test subject only,
LAN read-only, per-task plots and parameters) are taken as fixed and built on, not
re-argued.

Costs: **S** = hours to a day, **M** = days, **L** = a week or more, for a page that already
has the P4d-2b transport (server-rendered panes over SSE).

---

## 1. Top 10

One zero-cost correction comes before the list, because the lab's rules single it out:
the display panel prints **`0 dropped`** under the fps (`drawDisplays`, line 920) while the
"Wrong?" panel says dropped frames are *not measured*, and the toolbar pill **`check:
0 blocking`** is static text (line 347) that no check ever updates. Both are fabricated
zeros of exactly the kind P4d-2b §3 forbids ("render *not measured*, never 0"). Fix
before anything else.

| # | What | Why it changes what someone does at the rig | Cost | Where |
|---|------|---------------------------------------------|------|-------|
| 1 | **A "mark" control with hotkey `M`**: one press writes a timestamped mark to the record and the feed; a text box (which suspends the other hotkeys while focused, as inputs already do) lets the operator type "probe moved 200 µm", "monkey sneezed", "lights flickered". | The feed is titled "Changes and marks" but the page has no way to make a mark: every `log(..., "mark", ...)` call is system-generated. Annotating the record at the moment something happens is the one thing every comparable system provides (Blackrock *Add Comment*, Bpod *BpodNotebook*, pyControl "adding notes to the data log", Open Ephys message center "recording custom messages"; §3). Without it, notes go on paper and never reach `trials.jsonl`'s neighbors. | S | Toolbar, feed on Runtime |
| 2 | **Trial-phase timeline** on the Runtime tab and, compactly, under the replica: the current phase and its elapsed time while a trial runs (`acquire 0.4 s / hold 0.30`), then the finished trial's phases as a bar with durations and the outcome. | The only way today to learn *why* a trial was `fixation_break` is the outcome name. A timeline shows "broke 180 ms into a 300 ms hold" versus "broke on target onset", which is the difference between shortening `fix_hold` and fixing a flash. In simulation it is what a task author needs to verify a model-written task's state machine before an animal sees it (the sim shows only a dot and a target, `sim_full_target.png`). MonkeyLogic draws "a timeline visualization of trial events"; Bpod's *StateTiming* "shows the time course of states in the previous trial" (§3). | M | Runtime, right column, sim |
| 3 | **Keep the strip, the state pill and the toolbar visible in full-screen views**, as a one-line bar above the screen (values only, no bars). | Full-screen replica is the mode a trainer will sit in for an hour, and in it the page shows nothing but the screen and `close Esc` (`full_replica.png`, `sim_full_target.png`): no fluid, no out-of-cage time, no last-reward, no limit banner. The hotkeys work there but their feedback (toast) is the only confirmation. The always-visible strip is a PI decision; full screen currently defeats it. | S | Full-screen |
| 4 | **Expand `check: N blocking` into a real pre-flight list** on Setup, one row per item with pass / warn / fail and a test button where one exists: eye tracker reachable and streaming, NI card present, sync ack on a test word (exists: `io-test`), reward pulse (test, counted as fluid), tones, disk free versus an estimate, monitor calibration age, pump calibration present, eye map age, save directory writable. Clicking the pill jumps to the list. | The Rig panel already flags `pump calibration · not measured (V10)` in warn color (`running_setup.png`), but nothing gathers the flags or blocks Start on the ones that must block. A rig that starts a run with a dead tracker or an unwritable directory is discovered at trial 1, with the animal in the chair. MonkeyLogic's main menu has `[Test]` buttons for subject screen, eye tracker, joystick and reward and an `[I/O Test]` panel; pyControl's Experiments tab has an optional hardware test task (§3). | M | Toolbar pill, Setup |
| 5 | **Remember per-subject, per-task values**: last-used parameter values, shaping parameter and step, `error timeout`, `repeat after error`, and offer "start from last session (2027-01-13, run 2)" as the default with a diff against task defaults. | Today `task-sel` change and `confirmNew` both reset to task defaults (`withReward(taskParams(...))`, lines 1586 and 1507), and the shaping ladder restarts at step 0 every session (`S.train.step = 0`, `fresh()`). A trainer working `fix_window` down from 5° to 2° over a week re-enters it daily and can enter it wrong. MonkeyLogic "keeps a separate configuration per each subject" and reloads the last subject's; pyControl has a *Persistent* checkbox that saves variable values across sessions (§3). This is also what makes the shaping ladder usable across days. | M | Task parameters, Training tools, Setup |
| 6 | **Promote the last-N-trials outcome strip** (the `Last 60` ticks, `st-ticks`) from the Training tools tab to the top of Runtime, colored by outcome family rather than ok/err, and add **trials per minute over the last 5 min** to the strip's correct/trials cell. | The tick strip is the fastest read of "is the animal working, and how is it failing" and it is on the one tab an experimenter will not have open. Bpod's *TrialTypeOutcomePlot*/*SideOutcomePlot* and MonkeyLogic's number-coded trial results are the equivalents and they are always on screen (§3). Trials/min is the engagement number the last-reward cell only hints at. | S | Runtime, strip |
| 7 | **Neural-recording status row**: is RHX (or whatever the S7 plane is) recording, to which file, for how long; warn when a run starts and it is not. | The classic rig failure is an hour of clean behavior with the recording software idle. The "Wrong?" panel already reserves *RHX margin*; a recording yes/no is a cheaper and more consequential reading. Intan RHX exposes a "complete TCP command interface" for third-party control (intantech.com, checked 2026-09-26; §3), which is the hook. Depends on the S7 spec's integration, so cost is for the pane, not the plane. | M | Runtime (NI card panel), Setup pre-flight |
| 8 | **Scheduled stop and earlier limit warning**: "stop this run at HH:MM / after N trials / after X mL this run" (stop at the trial boundary, like `a-stop`), and a warning stage before the current 30-minute one (`WARN_WITHIN = 1800`, line 738). | The only bound today is the block quota and the 12-hour limit; a trainer who must leave the room has no way to make the rig stop on its own before the limit trips. Blackrock Central has *Record For* ("Once the time has expired, the recording will stop automatically"); MonkeyLogic sets "# of trials to run in this block" (§3). The warning level is welfare-facing, so the values are a question for the PI (§5). | S–M | Toolbar (next to stop), Runtime |
| 9 | **Stalled-animal and rig alerts**: last reward older than X min while running, tracker lost for Y s, run ended by limit or fault, disk below Z. Visual on the strip cell, an audible cue on the box if the PI wants one (§5), and carried to LAN and phone viewers. | The console is what the operator is *not* looking at while they prepare the next probe. The strip cell for last reward already goes to `9 min ago` quietly (`limit-reached_runtime.png`). Mymou emails the experimenter on a schedule; MonkeyLogic has a user-warning panel and an `[Alert]` function (§3). | M | Strip, banners, LAN/phone |
| 10 | **Eye-map quality beside the replica**: map name and age, validation residual, and the accumulated recenter offset (`S.gazeOff`), with "re-calibrate" suggested when the offset passes a threshold. | `recenter` logs each offset (`recenter()`, line 1343) but the page never shows the running total, so nobody knows the map has drifted 1.5° until windows stop making sense. The eye map line is on Setup only. EyeLink's Host PC has drift check/correct as a first-class screen and reports validation error in degrees (§3); MonkeyLogic exposes drift-correction settings in the main menu. | S | Right column, Setup |

Near misses, listed in §2: phone layout (tabs and replica placement), a run plan or
queue, an end-of-session notes field, a camera view of the animal.

---

## 2. By area

### Setup

*What works.* The three columns (Session, Monkey, Rig) answer the three questions asked
before a run, in the order they are asked (`running_setup.png`, `no-session_setup.png`).
Locking subject, rig, mode and save directory while a session is open, with a visible
`locked` label, is right. The Monkey panel's *Limits* block (reward, ceiling, floor, ←cage
12:00, config file) and the *Recent* table (day, task, trials, mL) are exactly what a
trainer wants to glance at. The Rig panel's warn-colored `not measured` rows are honest.
The save-directory browser on the box (`dlg_dir.png`) refusing session folders and the
disk root is careful. The new-session dialog (`dlg_new.png`) shows id and path before
committing. The load dialog (`dlg_load.png`) distinguishes an open, crashed session from
a closed one and refuses to reopen the closed one.

*What doesn't.*
- The `check: 0 blocking` pill has no list behind it (Top 10 #4).
- The new-session dialog takes `←cage at` in the console. The PI's decision is that the
  ELN owns departure and return and the console only reads them. Either this field is the
  fallback until the ELN exists (then say so on the dialog) or it goes (§5, §6).
- Nothing on this tab says where `earlier today 60.00 mL · kiosk 05:40–06:20` comes from
  or how old it is. If it is read from wl-works and the read fails, the strip's fluid
  number is wrong in the dangerous direction (§5).
- `eye map · map v3 · 2nd order · 06:58` is the only place calibration quality lives
  (Top 10 #10).

*Fixes.* Pre-flight list with test buttons (#4); a "start from last session" row in the
Session panel (#5); label the fluid-today source and its timestamp; move or mirror the eye
map line to the right column.

### Task parameters

*What works.* Generated parameter cards with name, unit, range, spin arrows, keyboard
stepping and a 600 ms debounce (`stepInput`) are dense without clutter
(`running_task.png`). Out-of-range and non-numeric entries are refused and the refusal is
logged with the actor (`offer()`, lines 1128–1129). While running, edits are staged and
applied at the next trial boundary (`applyStaged()`), and the card, the *Staged* panel and
the tab dot all show it. The welfare ceiling is marked on the card (`CEILING`) and the
card's range is the ceiling. `target_position` shows whether it is bound to an RF. The
task version hash (`@ 2ac9bea`) is on the tab.

*What doesn't.*
- "Staged" is not a review step: staged values apply automatically at the next trial.
  There is no *discard* and no *apply now*; if you typed the wrong value you must type
  the old one back before the trial ends. A one-line `2 staged → next trial · discard`
  under the cards is enough.
- Defaults reset on task change and on new session (Top 10 #5).
- The parameter grid does not say which parameters are shapeable or bindable to an RF; the
  Training tools tab and Overlays tab know but this tab does not. A small tag on the card
  (`shape`, `rf`) makes the task's declaration visible where it is edited.

*Fixes.* Discard and apply-now for staged; per-subject memory; declaration tags on cards.

### Overlays

*What works.* The RF table (show, label, x, y, r, use, remove) and the preview are
compact and the preview draws the fixation and target windows even between runs
(`replicaSvg(true)`), so an RF can be placed against the task's geometry before a run
(`running_overlays.png`). "target at rf" being allowed only when the task declares
`target_position` bindable, and only one RF at a time (`drawRfs` change handler), is the
right constraint.

*What doesn't.*
- `import from mapping` is a stub that restores three constants (`rf-import`, line 1641).
  What it will read (a mapping run's output on the box? wl-preproc's result?) decides
  whether this tab is useful on a recording day.
- *Recording notes* (probe, hemisphere, depth, mapping run) is static HTML (line 464). If
  it comes from the ELN it belongs with Setup's rig panel; if it has no source yet, it
  should render as *not recorded* rather than as data.
- RF edits are not logged except the use change; moving an RF that a target is bound to
  changes the task's target and should appear in the feed with the actor.

*Fixes.* Log RF geometry edits when bound; give Recording notes a source or remove it;
specify the import.

### Runtime

*What works.* This is the strongest tab (`running_runtime.png`, `notes_runtime.png` for
the whole page). *This run* shows total trials and every outcome that occurred, grouped by
family, with no invented rollup, as the PI asked. *Runs* gives the session's history in
one table with the reason each run ended (`out_of_cage: 12:00 limit`, `stopped by jake
(box, unverified)`, `interrupted at trial 187`). *Still needed* shows quota progress per
condition. *NI card* LEDs flashing on word, strobe, reward, photodiode and sync ack
(`flash()`) make the I/O path visible at a glance, and `send test word` is refused during
a run with the reason ("it would land in the recording"). The feed carries actor and
time on every entry. The recovery banner after a crash (`after-a-crash_runtime.png`)
reads back the departure and fluid and blocks Start until the departure is confirmed. The
warning and limit banners (`near-the-limit_runtime.png`, `limit-reached_runtime.png`) are
unmissable and the strip bar changes color with them.

*What doesn't.*
- No mark control (Top 10 #1) and no trial timeline (#2).
- *wl-works sees* duplicates the strip, the state pill and the session header, in a
  different order, in the middle of the tab. It is the `/health` payload and useful for
  "what does the portal think", but it competes with the panels the operator acts on
  (§4).
- The *Runs* table's `breaks` column is a rollup (`runsTable`, line 1085: fixation +
  target + blink + catch breaks) on a page where the PI decided against rollups. Either
  show the family counts or name the column by the family ("Breaks" family) so it is
  the declared grouping, not an invented one.
- `hangs 0` is a bare counter beside three *not measured* rows; if it is measured say what
  counts as a hang, if not, say *not measured*.
- The NI card's `spare 4 · low` and `stim trigger · not wired` rows are dead space on
  every rig until they are wired (§4).
- Between runs (`between-runs_runtime.png`) the top third of the tab is two empty panels
  (*This run: no run*, *Still needed: no run*). Collapse them to one line when there is no
  run, and let *Runs* rise.

*Fixes.* Mark control; timeline; collapse empty panels; demote *wl-works sees*; family
label on the breaks column; hide unwired I/O rows behind a count.

### Behavior

*What works.* Per-task plots drawn from the run's trials, with `n=` on each and the source
file named (`plots: tasks/fixation_detection.py`), selectable per run, live for the
current run (`running_behavior.png`, `between-runs_behavior.png`). Three plots per row at
1440 px is the right density.

*What doesn't.*
- Plots are static SVG: no hover values, no click to a trial. A trainer who sees the
  rolling-50 line dip wants the trials under the dip.
- All three tabs of the mockup's plots are per-run; there is no session-level view (all
  runs, time on the x axis). The one plot that is task-independent and is missing is
  **engagement over wall-clock time**: trials/min and correct/min per 5-minute bin across
  the session, with run boundaries and the limit marked. That is the plot that answers
  "is the animal done for today", and it needs no per-task declaration.
- Empty state on a fresh run is "waiting for trials" in each panel; fine.

*Fixes.* Session-level engagement-over-time plot (task-independent); hover readouts;
click-through from a point to the feed at that time.

### Training tools

*What works.* Everything a trainer touches is on one tab (`running_training.png`):
manual reward with amount, tone toggle, ceiling shown ("the same as reward_correct's"),
manual total this session; attention helpers (flash fixation, show target, go_cue,
reward_tone) that draw on the subject display (`S.attn`) and are logged; a shaping ladder
on one declared parameter with steps, advance/step-back rules and the last-50 bar; trial
helpers (repeat after error, error timeout, reward fixation); and the last-60 strip with
the streak. Amounts are validated against the ceiling on entry (`th-fixamt` handler) and
on delivery (`giveReward`), with refusals logged.

*What doesn't.*
- The shaping rules (`≥ 80% correct over 50`, `< 50% correct over 30`) are hard-coded
  (`shapingCheck`, lines 1461–1462) and shown as if they were settings. Either make them
  editable per subject or label them as the task's declaration.
- Steps are a comma-separated text field; the chips below it are display only. Clicking
  a chip to jump the ladder (with a log entry) is the natural control and costs little.
- The ladder shapes one parameter. Real shaping runs two or three (window, hold, timeout)
  in sequence; a list of ladders, each with its own parameter, is the same UI repeated.
- `reward fixation` pays on fixation acquisition *in addition to* `reward_correct`; the
  per-reward ceiling is checked on each separately, so a trial can pay up to 2× the
  ceiling (§5).
- The tick strip is on this tab only (Top 10 #6).
- The manual-reward key `R` is global; there is no hotkey lock (§5, §6).

*Fixes.* Editable or declared thresholds; clickable chips; multiple ladders; ceiling
semantics question to the PI; promote the tick strip.

### Online analysis

*What works.* Request → queue → result with states, the script path shown, results
rendered with the same plot code, and an honest design note that the transport is open
(`running_analysis.png`). Disabled for LAN viewers.

*What doesn't.*
- Value to the operator at the rig is low until the transport exists; the tab is mostly
  empty (`running_analysis.png`). It earns its place when results can include things the
  box cannot compute (psychometric fits, calibration residuals from the mapping run).
- The result panel shows `wl-preproc@87e7318 · example`; keep the version hash, it is the
  provenance the record needs.
- No way to attach the result to the session record or the ELN; the result is viewed and
  lost.

*Fixes.* Save results next to the run (`analysis/<script>@<hash>.json` plus the plot); a
"request again for this run" shortcut; otherwise leave until the transport is decided.

### End of session

*What works.* *Supplement to give* as the largest number on the tab, with the floor and
today's total beside it (`ended_end.png`); the session summary (←cage, →cage from the
ELN, in-session, out-of-cage, fluid, correct/trials) and the runs table; the *Record*
checklist of files with `pending` for the clock until ended; *Transfer to wl-nas*
disabled until ended and never for simulation (`xfer-go` in `drawEnd`). The end
confirmation says what ending means ("takes no more runs, and the in-session clock
stops"; `end_confirm.png`).

*What doesn't.*
- The supplement number is shown while a run is still going (`running_end.png`,
  `161.75 mL`). It is a projection then, not an instruction; label it "if ended now"
  until the session ends (§5).
- After ending, the tab still says `→cage from the eln · not yet` in small type. That is
  the one open welfare item after the operator's job is done, and `/health` stays
  `degraded` until it is recorded (P4d-2b §3). Make it a banner on this tab and on the
  strip after `end session`: "return to cage not yet recorded in the ELN".
- No free-text session notes (animal state, what to try tomorrow). If the ELN owns notes,
  say so here with the session id to paste; if not, a text box that writes to the record
  is a small addition.
- The runs table appears here, on Runtime and (per day) on Setup; fine, but the end
  version could add the per-run fluid rate (mL/min) which is what decides tomorrow's
  reward size.

*Fixes.* "if ended now" label; return-to-cage banner after end; session notes or an ELN
hand-off line; mL/min per run.

### The always-visible strip

*What works.* Four cells, one number each, bars only where a bound exists
(`running_runtime.png`): fluid today / floor with the bar filling toward the floor;
←cage / 12:00 with `8:47 left` and a bar that turns warn at 30 min and crit past the
limit; correct / trials with percent and run count; last reward with the per-correct
amount. In the *no session* scenario three of the four cells show `—` rather than zeros,
and the fourth shows the day's earlier fluid (`no-session_runtime.png`). It survives 1000 px (`narrow_runtime.png`) and stacks on a
phone (`phone_runtime.png`).

*What doesn't.*
- Fluid today has a floor but no ceiling, so the bar is full at the floor and the cell
  cannot show an over-delivery; if the protocol has a daily maximum it belongs here (§5).
- Last reward only tells you the animal stalled if you are watching it grow (Top 10 #9).
- The strip is hidden in full-screen views (Top 10 #3).
- `manual this session` (0.25 mL presses) is on the Training tab only; a small
  `· 1.50 manual` suffix in the fluid cell would make manual dosing visible where fluid is
  read.
- `←cage / 12:00` is the right label for the lab but `←cage` alone is cryptic to a new
  tech; the docs can explain it, the tooltip (`title`) should too.

*Fixes.* Manual suffix; alert states; tooltip; full-screen mirror; ceiling if one exists.

### Toolbar and hotkeys

*What works.* Task select, `check` pill, start/stop, pause/reward/recenter with `P`/`R`/`C`
shown as kbd caps (`running_runtime.png`). Every disabled button carries a reason in its
`title` (`setBtn`). Stop and end both confirm inline at the trial boundary
(`stop_confirm.png`, `end_confirm.png`) rather than in a modal. Hotkeys ignore modifier
combinations, key repeat, inputs, selects and contenteditable (`keydown` handler, lines
1652–1660), and each fires a toast. `pause` toasts "the out-of-cage clock keeps running",
which is the right thing to say.

*What doesn't.*
- `calibrate LATER` and `test screens LATER` are dead buttons in the primary toolbar. A
  toolbar that people learn to skip parts of is a toolbar. Remove until they exist; the
  "not yet" belongs in the docs with the slice named (§4).
- `R` delivers fluid from any focus except inputs. Bumping a key after clicking a button
  (focus on a `<button>`) pays a reward. MonkeyLogic has an `F12` hotkey lock for this
  reason (§3). Whether a lock or a minimum interval is wanted is welfare-facing (§5).
- No `M` for mark (Top 10 #1).
- The reward amount `R` uses is on the Training tab (`mr-amt`); when pressed from
  Runtime, the toast is the only place the amount appears. Show the amount on the button
  (`reward 0.25 R`), since it is the one number the key commits.
- Start goes straight to the Runtime tab (`a-start` handler); good. Task change while
  idle logs `check 0 blocking` (line 1586) without checking anything.

*Fixes.* Remove dead buttons; amount on the reward button; mark key; hotkey-lock or rate
question to the PI.

### Right column

*What works.* Replica with fixation window, target window, gaze trail, RF circles and a
caption `run 2 · trial 120 · 8 px/°`; subject display drawn stereo when the rig is
(`stereo · 2 halves`) and single otherwise, with fixation and target as the animal sees
them; sound with the tone name while it plays; fps (`running_runtime.png`). Clicking either
screen opens it full screen.

*What doesn't.*
- `0 dropped` is fabricated (top of §1).
- No numeric gaze readout (x°, y°) and no tracker state; MonkeyLogic's control screen
  shows "the real-time input state" (§3). When tracker staleness becomes measured it
  belongs here, not in "Wrong?".
- The replica has no time axis. A small gaze-versus-time trace (last 2 s of x and y)
  beside it is how blinks, tracker dropouts and slow drift are told apart; EyeLink's
  Record screen offers exactly this "Plot view" alternative to the gaze cursor (§3).
- Eye-map age and accumulated recenter offset are missing (Top 10 #10).
- The sound panel's tone name is on screen for 220–650 ms (`TONES`), which is shorter
  than a glance; `last: reward_tone · 3 s ago` is readable.
- `V11` in the replica header is a milestone tag, not information for the operator (§4).

*Fixes.* Gaze x/y and tracker state under the replica; gaze trace; map age and offset;
persistent last-tone; drop the `0 dropped` and `V11`.

### Full-screen views

*What works.* `Esc` and a visible `close Esc` button; the replica scales to the viewport
(`full_replica.png`); the subject display shows the two halves at size
(`full_subject.png`); in simulation the hint explains the mouse
(`sim_full_target.png`).

*What doesn't.*
- No strip, state, trial counter or banners (Top 10 #3). A limit warning that fires while
  the replica is full screen is not seen.
- No trial phase or timer (Top 10 #2); the caption is `run 1 · trial 0` even mid-trial.
- On a phone the full-screen replica is a 220 px band with the rest of the screen empty
  (`phone_sim.png`); a rotate hint or landscape-only layout for full screen is cheap.

### Simulation mode

*What works.* Header stripe and `SIMULATION` pill (`sim_runtime.png`), the sim rig and
test subject only (`subjectsFor`, `rigsFor`), reward "counted, not delivered", transfer
refused, every welfare check still applied to the test subject's bounds (design note). The
mouse-as-gaze trial (`mouseStep`) honors `fix_window`, `fix_hold`, `target_window`,
`target_hold` and `response_window`, so changing a parameter changes what the mouse must
do, which is the point.

*What doesn't.*
- No visibility into the state machine (Top 10 #2): you cannot tell acquire from hold,
  or see the timers, so a wrong `fix_hold` looks like a slow mouse.
- The scripted-gaze mode (`scripted` in `gaze-segs`) plays trials at a fixed cadence with
  random outcomes drawn from a table (`ERRORS`). Useful for exercising the page, not for
  testing a task; label it "page exercise" so nobody reads its plots as task behavior.
- Only the fixation task has a mouse trial; the others fall through to the scripted path
  (`trialTarget` parses `ecc N`). Fine for a mockup; in the product the mouse path must be
  the task's own state machine, or sim proves nothing.

### LAN viewer

*What works.* Read-only is enforced in the model (`canWrite()`), not just in the DOM; every
control is disabled with the same sentence; presence reads `LAN viewer · read-only`
(`lan_training.png`, `lan_task.png`). The disconnect dialog names the run and trial at the
moment of leaving and offers reconnect (`disconnected.png`).

*What doesn't.*
- The *READ-ONLY* banner and the presence label say the same thing (§4).
- A PI watching from elsewhere wants three things at a glance: state, strip, last-60
  ticks (or the engagement plot). The page gives the first two and buries the third on
  Training tools (Top 10 #6).
- "2 LAN viewers" is shown to the box but LAN viewers are not told who is at the box, or
  that nobody is (the operator's page closed). Presence should say `nobody at the box`
  when no box page is connected; that is the fact the remote viewer needs to phone
  someone.
- Nothing distinguishes "the stream stopped" from "nothing is happening": add the age of
  the last frame to the presence line (the `/health` reading already exists).

### Phone width

*What works.* Everything stacks and stays legible at 390 px (`phone_runtime.png`,
`phone_training.png`); text does not overflow; the strip becomes four rows.

*What doesn't.*
- The header wraps to six rows and the tab bar to four rows of uppercase labels before
  any content; the toolbar (which a phone viewer cannot use) takes five rows.
- The right column is pushed to the very bottom, below all tab content (`.shell` collapses
  to one column at 900 px and the aside comes last), so the replica, which is the most
  useful thing on a phone, is a long scroll away.
- Phone is the LAN viewer's device, so writes are off anyway; render the toolbar as the
  state pill only, the tabs as a `<select>`, and put the replica and the last-60 strip
  directly under the strip.

*Fixes.* A "glance" layout below 700 px: state, strip, replica, ticks, then a tab
selector. S.

### Other observations

- Light theme (`light_runtime.png`, `light_near_runtime.png`) is as legible as dark; the
  warn bar and banner read correctly in both.
- Keyboard: tabs have arrow-key navigation and roving tabindex; dialogs close on `Esc`;
  focus rings are visible. Good.
- The header shows `IN SESSION 3:04:10` next to `SESSION`, `SUBJECT`, `RIG`, `RUN`,
  `TRIAL`: dense and right. The purple design-note boxes are hidden by default and read
  well when shown (`notes_runtime.png`).
- `actor()` is hard-coded `jake (box, unverified)`; the product asks for a name once per
  box page (P4d-2b §2). Show that name in the presence line so a wrong name is noticed.

---

## 3. What comparable systems do

All checked 2026-09-26. Only what the cited page states is claimed; where a page could not
be read, the item says so. Nothing below is a screenshot description unless the page's own
text describes it.

**NIMH MonkeyLogic** — https://monkeylogic.nimh.nih.gov/docs_RunningTask.html and
https://monkeylogic.nimh.nih.gov/docs_MainMenu.html
- Control screen: a replica of the subject screen with "the real-time input state, the
  location and size of fixation windows, reward delivery, etc."; "a timeline visualization
  of trial events"; trial counts and results "number-coded as specified in the trialerror
  runtime function"; a user text/warning panel; a user plot for "online behavior
  analysis" defaulting to reaction time.
- Runtime keys: `ESC` pause after the current trial; `C`/`V` recenter eye 1/2; `R` manual
  reward ("initial 100 ms pulse"); `-`/`+` change the reward pulse by 10 ms; `F12`
  lock/unlock hotkeys. Pause menu: `V` edit timing-file variables, `B` new block, `X`
  alter behavioral-error handling. At the end "a figure that summarizes behavioral
  performance pops up" and a player replays trials.
- Main menu: "NIMH ML keeps a separate configuration per each subject" and reloads the
  last subject's; "# of trials to run in this block"; "Count correct trials only"; test
  buttons for subject screen, eye tracker, joystick and reward; an `[I/O Test]` panel and
  `[Latency test]`; eye-calibration method, drift-correction percentage, import from
  other configs; an `[Alert]` function; an "On error" menu.
- Relevant here: the same three hotkeys (`P`≈`ESC`, `R`, `C`); the hotkey lock; per-subject
  configuration; the trial timeline; test buttons before a run; reward adjustable by key.
  Weak point relative to this console: no welfare bounds in the interface as documented,
  and the runtime information is a fixed panel rather than a record.

**MWorks** — https://mworks.github.io/documentation/latest/guide/running.html; window
names from https://mworks.github.io/news/2019/05/13/0.9-released/
- Client/server split: MWServer runs the experiment (macOS or iOS, "Listening port:
  19989"); MWClient connects over TCP/IP, loads the experiment, has a start button that
  becomes stop. A *Console* window shows messages; a *Variables* window lets you examine
  "and modify variable values during execution", in expandable groups (descriptions as
  tooltips, per the 0.12 notes at https://mworks.github.io/news/2023/04/12/0.12-released/).
- The release notes name an *eye window*, a *calibrator* and a *reward window*, but their
  content is not described on the pages read: what they show is UNVERIFIED here.
- Relevant here: the client/server model is the closest analog to box + browser; live
  variable editing is the analog of the parameter cards. Weak point for this lab: it is
  a macOS client by documentation ("MWClient (red monkey icon, macOS only)").

**PsychoPy (Builder, Runner)** — https://www.psychopy.org/builder/concepts.html and
https://psychopy.org/faqs/runner_exp.html
- Builder: Routines ("the timing of stimuli, instructions and responses" in "a
  track-based view"), a single Flow with loops, a Components panel (an Eyetracking group
  since 2021.2). Runner: "displays real-time logs and error messages while your
  experiment runs", errors "highlighted in red".
- The pages read do not describe live parameter editing, animal-facing limits or a
  replica display; whether they exist elsewhere in PsychoPy is UNVERIFIED here.
- Relevant here: Builder's track view is a good model for the trial timeline (Top 10 #2).
  Otherwise PsychoPy is a human-subject tool and its runtime window is a log, not a
  console.

**PLDAPS (Psychtoolbox rigs)** — https://github.com/HukLab/PLDAPS (README)
- "PLexon DAtapixx PSychtoolbox"; experimenter "overlay" window distinct from the subject
  display ("things rendered to the Overlay pointer will only appear on the overlay
  window"); keys during trials: `d` debugger, `q` quit, `m` manual reward, `p` end trial;
  `createRigPrefs` "opens a gui" for rig preferences. No runtime GUI is described.
- Relevant here: the overlay is the replica; hotkeys without a GUI is where most
  Psychtoolbox rigs live, and this console's feed with actor and time is the thing they
  lack.

**Bpod (Sanworks)** — https://sanworks.github.io/Bpod_Wiki/user-guide/bpod-gui/ and
https://sanworks.github.io/Bpod_Wiki/function-reference/general-plugins/
- Console: *Live Info* (current and previous states, last event, trial start time, USB
  status); *Manual Override* of "behavior ports, BNC and Wire interfaces"; *Config* with
  liquid calibration, audio, networking, data paths; *Session* play/pause that "schedules
  a pause after the current trial ends", and stop. The hardware LED glows green when the
  console is connected and blue when not.
- Plugins: *BpodParameterGUI* edits protocol parameters during a session;
  *BpodNotebook* "for taking notes on individual trials, or marking them digitally";
  *TrialTypeOutcomePlot* / *SideOutcomePlot* (green correct, red error, blue no-response
  around the current trial); *TotalRewardDisplay* "the total amount of liquid reward
  delivered in the current session" with µL→mL; *StateTiming* "the time course of states
  in the previous trial".
- Liquid calibration (search result from the same wiki, page URL not resolved): a
  "Measure Pending" button delivers pulses per valve, water is weighed, weights entered,
  and the calibration curve updated; `GetValveTimes()` converts µL to seconds
  (https://sanworks.github.io/Bpod_Wiki/function-reference/liquid-calibration/).
- Relevant here: outcome plot, state timing, notebook, total reward, pause at trial
  boundary are all present or proposed here; the calibration workflow is what `pump
  calibration · not measured (V10)` will need.

**pyControl** — https://pycontrol.readthedocs.io/en/latest/user-guide/graphical-user-interface/
- *Run task* tab: controls, a log and plot panels; the interface switches from *Start* to
  *Record* only when a data directory and subject ID are set. A *Controls* dialog for
  "set/getting the value of task variables, adding notes to the data log, and manually
  triggering task events"; custom controls dialogs with checkboxes, sliders, spinboxes.
- *Experiments* tab runs several setups at once; per-subject variables; a *Persistent*
  checkbox saves variable values across sessions; a *Summary* checkbox shows subject
  values at session end; per-setup boxes show "current state, the most recent event, the
  most recent line printed, and a log".
- Relevant here: persistent per-subject variables (Top 10 #5); notes into the log (#1);
  refusing to record without subject and directory (this console does the same by
  locking them into the session).

**Bonsai** — https://bonsai-rx.org/docs/articles/editor.html
- A dataflow editor: nodes on a canvas, a toolbox, a Properties panel, `F5`/`Shift+F5`
  start/stop, and per-node visualizers ("Show Visualizer") with positions remembered; a
  watch mode shows whether an operator "is emitting values".
- Relevant here: not a rig console. The per-node visualizer is a good precedent for
  "click any reading to see its trace" (the gaze trace in §2, right column).

**Open Ephys GUI** — https://open-ephys.github.io/gui-docs/User-Manual/Exploring-the-user-interface.html
- Control panel: a CPU meter ("ideally" under 20%), a disk-space meter, play and record
  buttons, a clock that "turns red and displays the amount of time since the current
  recording began"; a message center for notifications and "recording custom messages";
  a signal chain of sources, filters, sinks.
- Relevant here: disk space and a recording clock always on screen; custom messages into
  the record (Top 10 #1); the red record clock is a cleaner "you are recording" than a
  pill.

**Intan RHX** — https://intantech.com/RHX_software.html
- Waveform display, probe map with impedance and activity, spike scope, PSTH/ISI/spectrum
  tools, one-click impedance measurement, settings in XML, and a "Complete TCP command
  interface allows third-party software (e.g., MATLAB, Python) to control all functions
  remotely and automate tasks."
- Relevant here: the TCP interface is how a recording-status row (Top 10 #7) and a
  pre-flight "RHX reachable" check would be built. The page does not list a run/record
  control; that detail is UNVERIFIED here.

**SpikeGLX** — https://billkarsh.github.io/SpikeGLX/ and
https://github.com/billkarsh/SpikeGLX/blob/master/Markdown/UserManual.md
- Console status bar "During a run … shows the current gate/trigger indices and the
  current file writing efficiency"; a *Run Metrics* window "consolidates the most vital
  health statistics from the Console log"; files named `run-name_g1/run-name_g1_t0.nidq.bin`;
  a remote API to "Set/get parameters", "Start/stop runs" and fetch data (the page claims
  "<4 ms on same computer"; not measured here).
- Relevant here: a single health window fed by the log (this console's "Wrong?" plus
  NI card is that); gate/trigger indices are the analog of session/run numbering.

**Blackrock Central** — Research Central Software Suite IFU, LB-0574 rev 5.00 (2019),
https://blackrockneurotech.com/wp-content/uploads/LB-0574_Central_Software_Suite_IFU.pdf
- *File Storage* "contains the controls to start and stop recording"; *File Description*
  "Up to 256-character comments … prior to recording"; *Record For* "Specify an amount of
  time … Once the time has expired, the recording will stop automatically"; *Remote
  Recording Control* starts, stops, pauses and resumes recording from digital inputs or
  serial; *Add Comment* "a timestamped text comment to the Neural Event file" that "can be
  visualized in the Raster Plot"; Spike Panel, Raster Plot, Activity Map, System Load.
- Relevant here: timed stop (Top 10 #8), comments in the record (#1), and recording
  start/stop by digital line, which is how the sync box could make the neural recorder
  follow the run.

**Plexon OmniPlex / PlexControl** — OmniPlex System Data Sheet,
https://plexon.com/wp-content/uploads/2017/06/OmniPlex-System-Data-Sheet.pdf
- "Powerful online software"; "flexible, customizable user interface"; online sorting
  methods (box, template, line, band, contour in PCA space); per-channel recording of
  data types; "Timed/event-triggered multiple-file recording"; MATLAB/C++ online APIs;
  "Remote online data access across any TCP/IP or UDP network using PlexNet". The user
  guide itself exceeded the fetch limit and was not read; anything beyond the datasheet is
  UNVERIFIED here.
- Relevant here: event-triggered recording is the same idea as the sync-box-driven start.

**EyeLink 1000 Plus (Host PC)** — EyeLink 1000 Plus User Manual v1.0.20 (SR Research,
2013–2022), https://www.axonlab.org/hcph-sops/assets/files/EL1000Plus_UserManual_1.0.20_GOP.pdf
- The Camera Setup screen is "the central screen for most EyeLink 1000 Plus setup
  functions": camera view, pupil/CR thresholds (with an auto-threshold button), tracking
  mode, and "Calibration, Validation, and Drift Checking/Drift Correction can be initiated
  from this screen." The Record screen shows "the participant's current gaze position as
  a cursor overlaid on a simulated display screen" or, in Plot view, "x, y data traces …
  graphed as a function of time" (`F6` switches views). A Primate mount is a documented
  configuration. The Validate screen (§2.4.5.1) "measures the difference between the
  target position and the computed fixation position" and "Spatial error is reported in
  degrees of visual angle"; a GOOD/FAIR/POOR verdict was not located in the manual text
  and is UNVERIFIED here. Data Viewer was not checked.
- Relevant here: gaze cursor *and* plot view (right column); drift correction as a
  first-class, logged action (Top 10 #10).

**NHP cage-side and kiosk training**
- XBI: Calapai, Berger, Niessing, Heisig, Brockhausen, Treue, Gail, *Behav Res Methods*
  2017, "a stand-alone cage-based training and testing system for rhesus monkeys" that is
  "mobile and easy to handle by both experts and non-experts" (abstract via Europe PMC,
  https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:26896242%20AND%20SRC:MED&format=json&resultType=core).
- AUT on the XBI: Berger et al., *J Neurophysiol* 2018, "across-task unsupervised
  training … of successively more complex cognitive tasks", "self-paced training
  schedules with individualized learning speeds based on automatic updating of task
  conditions"; the monkeys "stay engaged with the AUT over months despite access to water
  and food outside the experimental sessions" (Europe PMC,
  https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:29142094%20AND%20SRC:MED&format=json&resultType=core).
- ACTS: Griggs et al., *J Neurosci Methods* 2020, a cage-side touchscreen tablet with a
  reward feeder; the laptop lets "researchers … remotely monitor the performance of the
  subject and modify the parameters (e.g., target size) of the task presented to the
  subject throughout a session, or even change tasks entirely"; "Data is saved at the end
  of each trial to protect against data loss"
  (https://pmc.ncbi.nlm.nih.gov/articles/PMC8384435/).
- Mymou: Butler and Kennerley, *Behav Res Methods* 2018/2019: facial recognition to tell
  subjects apart, the system "can analyze task performance in real time and adapt the task
  parameters", and "there is no remote monitoring of the device, apart from text-based
  email alerts" (https://pmc.ncbi.nlm.nih.gov/articles/PMC6877703/).
- Kiosk: Ramezanpour, Giverin, Kar, *J Neurophysiol* 2024, "a portable, low-cost,
  easy-to-use kiosk system developed to conduct home-cage vision-based behavioral tasks"
  (Europe PMC,
  https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:39015072%20AND%20SRC:MED&format=json&resultType=core).
  The task software is not named in the abstract; UNVERIFIED which client it runs.
- mkturk: https://github.com/dicarlolab/mkturk — "purely a client-side piece of code" for
  browsers on tablets; parameters and data as JSON in cloud storage; `liveplot.html`, "a
  basic plotting web page that uses the google charts api". Reward hardware is not
  described in the README.
- Relevant here: the shaping ladder is the console's AUT; ACTS and Mymou show that remote
  parameter changes and alerts are what a cage-side operator actually uses, which argues
  for Top 10 #9 and, after P4d-3, for some LAN writes. This lab's kiosk (`RIGS.kiosk`,
  S13) already feeds "earlier today" fluid into the strip, which none of the cited systems
  describe doing.

---

## 4. Remove or demote

- **`calibrate LATER`, `test screens LATER`** in the toolbar: remove until they exist.
  Two dead buttons in the primary control row teach the eye to skip the row.
- **`V11` tag** on the replica header: milestone bookkeeping; not for the operator.
- **`0 dropped`** under the fps: fabricated (see §1). Show *not measured* or nothing.
- **`check: 0 blocking` pill** until a list exists behind it: either wire it or render
  *not checked*.
- **`wl-works sees` panel** on Runtime: collapse to a single line (`portal: ok · last
  frame 1 s`) that expands, or move it to the End of session tab where "what did the
  portal record" matters. Everything else in it is already on the strip and header.
- **`READ-ONLY` banner** for LAN viewers: the presence line says it; keep one.
- **`stim trigger · not wired`** and **`spare 4`** rows in the NI card: show wired lines
  only, with `2 unwired` as a footnote, until the stim trigger is a real line (then it is
  welfare-critical and gets its own treatment).
- **`Staged` as a separate panel** on Task parameters: fold into a one-line summary with
  *discard*; the cards already mark staged values.
- **`Recording notes`** on Overlays: static text with no source; remove or give it one.
- **`Blocks` table** on Task parameters duplicates *Still needed* on Runtime for a running
  task; keep it (it is the plan, the other is progress) but it need not be a panel of its
  own: one line per block under the parameter cards.
- **Scripted gaze** in simulation: keep for exercising the page, but label it so its plots
  are never read as task behavior.
- **`hangs 0`**: measured or *not measured*, not a bare 0.
- The "Wrong?" panel: three of its four rows are *not measured* by design until later
  slices. That is honest, but a panel that is 75% placeholder should be one row
  (`health: 3 readings not yet measured`) until it has readings.

---

## 5. Welfare-relevant observations (questions for the PI, not decisions)

1. **Manual reward rate.** `R` and `give reward` deliver `mr-amt` mL per press with the
   per-reward ceiling as the only check (`giveReward`, lines 1325–1335); key repeat is
   suppressed but repeated presses are not. Is a minimum interval between manual rewards,
   or a per-session manual total that warns, wanted? Should the manual total appear in the
   strip's fluid cell?
2. **Two rewards per trial.** With `reward fixation` on, a trial pays `fixAmt` on
   acquisition and `reward_correct` on success (`mouseStep` line 1435; `simTrial` line
   860), each checked against the ceiling separately, so one trial can deliver up to
   2 × ceiling. Is the ceiling per pulse or per trial?
3. **No daily maximum.** The strip has a floor and a supplement but no ceiling on fluid
   today. If the protocol sets a daily maximum, should the console show it and warn,
   and if it does not, should the fluid cell say so?
4. **Limit warning timing and channel.** The only pre-limit warning is at 30 minutes
   (`WARN_WITHIN`), visual only, and it is not shown in full-screen views. Is an earlier
   stage wanted (for example 60 min), and an audible cue on the box?
5. **Limit trips mid-run.** `afterTrial` ends the run at the trial boundary when
   `ooc() >= LIMIT` and blocks further runs. The animal is still in the chair until
   someone notices. Should that moment push a notification to LAN viewers and to
   wl-works, and should `/health` (already `degraded`) be enough?
6. **Departure entry in the console.** The new-session dialog takes `←cage at` and the
   recovery banner asks to confirm a read-back departure, while the decision is that the
   ELN owns departure and return. Is the console field a fallback until the ELN exists?
   If both exist and disagree, which is the record? And after recovery, where does a
   wrong read-back departure get corrected (there is no edit path on the banner)?
7. **Fluid from other systems.** `earlier today 60.00 mL · kiosk 05:40–06:20` feeds the
   strip. If that read is stale or fails, the fluid-today number and the supplement are
   both wrong in the direction that under-supplements. Should the console refuse to open
   a session without a fresh read, or show *unknown* and let the operator decide?
8. **Supplement shown early.** `Supplement to give` is displayed at full size while a run
   is still going (`running_end.png`). Should it be labeled "if ended now" or hidden until
   the session ends, so nobody gives it early?
9. **Return not yet recorded.** After `end session` the tab says `→cage from the eln · not
   yet` in small type. Should the console keep a visible banner until the ELN's return is
   read back, given `/health` stays `degraded` until then?
10. **Pause.** The toast says the out-of-cage clock keeps running. Should a pause longer
    than N minutes prompt the operator ("return to cage?"), and should paused minutes be
    reported in the session summary?
11. **Simulation isolation.** The design note says a simulation session can only take the
    test subject and the sim rig. Does *load session* also refuse to attach a real
    subject's saved session to a sim rig, and is `subjects/test/bounds.py` the only
    bounds file simulation may ever read?
12. **Stimulation trigger.** It is shown as a dead line today. When wired, does it get a
    distinct control with confirmation, a hotkey lock, and its own line in the feed, or is
    it purely task-driven with no console control?
13. **Shaping and error timeout.** The ladder cannot touch ceiling parameters (good), but
    `error timeout` and `repeat after error` change trial rate and so fluid rate. Should
    those be in the welfare-critical module list, or is their bound the per-reward ceiling
    alone?

---

## 6. Open questions that would change the design

1. **Who sits at the box most days**, a trainer or the experimenter? If a trainer, the
   default tab after `start run` should be a Runtime with the tick strip and the timeline
   on top; if the experimenter, Behavior. Today it is Runtime without the ticks.
2. **Does the box have an operator-facing audio channel** separate from the animal's
   speaker? Decides whether alerts (§5.4) can be audible at all.
3. **Is there a camera on the animal?** A small live view in the right column is standard
   on chair rigs; it is not in the decided right-column list and is hardware-dependent.
4. **Hotkey lock.** MonkeyLogic's `F12` exists because `R` on a rig keyboard gets bumped.
   Wanted here, or is the input-focus rule enough?
5. **Will any LAN write be allowed after P4d-3** (for example the PI stopping a run
   remotely)? If yes, the stop confirmation and the presence line need to name the remote
   actor now, so the feed's `actor()` field does not have to change shape later.
6. **Run plan per subject.** Do trainers run the same sequence daily (calibration →
   fixation → search)? If so, a per-subject run queue with "same as yesterday" is cheap
   and removes a class of wrong-task starts.
7. **Where do session notes live** — the ELN, the record on the box, or both? Decides
   whether Top 10 #1's text marks are the notes, or a link to the ELN is.
8. **Phone use.** Is the phone case "glance at state" only? If so the layout in §2
   (state, strip, replica, ticks, tab selector) is enough; if any control is ever wanted
   from a phone, the toolbar has to be redesigned for touch, which is a different page.
9. **Model-authored tasks.** Since tasks are written by the model, should the console show
   the task's declared manifest (parameters with ranges, which are shapeable and bindable,
   plots, helpers honored) as a review pane before the first run with an animal? The
   parameter cards show values; they do not show what the task *may* do.
10. **`import from mapping`**: what is the source (a mapping run's file on the box,
    wl-preproc's result via the analysis transport, or the ELN)? Decides whether Overlays
    is a recording-day tool or a manual-entry table.
11. **Multi-rig.** One page per box is the current shape. If the portal will ever show
    two rigs to one viewer, presence and the strip need a rig prefix now; pyControl's
    Experiments tab is what that looks like.
