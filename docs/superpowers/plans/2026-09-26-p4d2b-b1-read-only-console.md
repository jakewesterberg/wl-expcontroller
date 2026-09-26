# P4d-2b slice b1 — The Read-Only Browser Console: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Assumes P4d-2a merged, including its Tasks 7–9.** Every welfare duration is on the
> session's anchored wall clock (`Session.wall_now()`, Task 7 and its Ruling 8);
> `ReturnedToCage` and `--await-return-for` are gone, and a linked `wlx run` with no
> terminal records `return not recorded (no terminal)` and exits without post-loop frames
> (Task 8); `Session.open()`/`Session.end()` exist and `Telemetry.in_session_seconds` is
> on schema 6 (Task 9). Do not start this plan on a `main` that lacks them.

**Goal:** A person on the lab network opens `http://BOX:PORT/` and reads a running session — header, the four-cell strip, Runtime, Task parameters, Setup and End of session — live from the session's telemetry, with nothing on the page able to write; and wl-works reads the same session from `GET /health`.

**Architecture:** Telemetry goes from schema 6 to 7, adding the configuration a session runs under, the two limits its numbers are read against, the instant of the last reward (taken inside `welfare.deliver`) and the last 60 outcomes. A new process, `wlx serve`, holds one `ZmqConsole` on a telemetry thread, keeps the latest frame in a `Hub`, and serves a stdlib `ThreadingHTTPServer`: `GET /` (the page), `GET /events` (server-sent events carrying HTML fragments), `GET /health` (bearer token), and `GET /fonts/<file>` (the wl-works fonts, bundled so the page never reaches the internet). Every pane is rendered in Python by a pure module (`web.py`), `/health`'s body by another (`health.py`), so the page's JavaScript only opens the stream, swaps fragments by id, runs the stale timer, and offers close and reconnect.

**Tech Stack:** Python 3.11–3.13; stdlib `http.server.ThreadingHTTPServer`, `threading`, `queue`, `json`, `html`, `hmac`, `secrets`, `ipaddress`, `importlib.resources`; pyzmq and msgpack through `link.py` (the existing `console` extra, imported lazily); pytest. `wl-preproc`'s pydantic `HealthResponse` at test time only. Fonts: IBM Plex Sans, Plex Sans Condensed, Plex Mono and Newsreader (OFL-1.1), bundled as package data.

**Spec:** `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` — §1–§3 decided, §4.1–§4.4 are this slice, §4.0 holds rulings for later slices (b1 builds none of them beyond §4.2). The page follows `docs/superpowers/mockups/2026-09-26-console-mockup-v12.html`. Read the spec first; this plan argues from it.

## Global Constraints

- **Branch, not `main`.** Work in a worktree on branch `p4d2b-b1-read-only-console`, cut from `main` after P4d-2a's fast-forward. **Task 2 changes `welfare.py`** (reward delivery), so this slice is welfare-critical (CLAUDE.md) and **must not merge to `main` until the PI has approved Task 13's welfare item** (the fonts' license is already settled by ADR-0004's 2026-09-26 amendment). Push the branch; do not fast-forward `main`.
- **The merged code wins over this plan's quotations of P4d-2a.** P4d-2a was still moving when this was written. Where a step quotes an existing line to anchor an edit and the merged line differs, anchor on the named function or field and keep its meaning; never restore the quoted text.
- **US English** in code, comments and docs.
- **No timing claim without a measurement.** `DEFAULT_STALE_AFTER_S` (30 s) is a display choice (spec §3); `KEEPALIVE_S`, `RECEIVE_TIMEOUT_S`, `RETRY_MS`, `QUEUE_DEPTH` and the rate window's sampling are housekeeping. Every docstring that names one says so. No latency, jitter or throughput number enters the repo.
- **Hot path.** The only new work inside `run_trial` is `Rig.reward`'s one call to the session's wall clock and one float store per reward (Task 2). Everything else happens at a trial boundary, as `Telemetry.of` already does, or in `wlx serve`'s own process.
- **No new code dependency.** Everything above is stdlib or already declared. The bundled fonts are the one new third-party asset: licensed OFL-1.1, verified at their primary sources, entered in ADR-0004's inventory with a justification each, under the ADR's 2026-09-26 amendment allowing unmodified OFL-1.1 fonts as assets (PI; Task 8). `link.py` keeps importing `zmq`/`msgpack` inside functions; `serve.py`, `web.py` and `health.py` import cleanly without them (Task 11 extends `tests/_transport_import_blocker.py` to prove it).
- **Nothing leaves the box from the page, and the fonts are bundled** (PI, 2026-09-26, spec §4.2). The mockup's Google Fonts `<link>` is replaced by the same four families shipped in the package — IBM Plex Sans, Plex Sans Condensed, Plex Mono and Newsreader, unmodified woff2 files with each family's `OFL.txt` beside them (Task 8) — and served by `wlx serve` at `/fonts/<file>` (Task 10). The page contains no `http://` or `https://` URL, and its Content-Security-Policy is `default-src 'none'` plus its own script by nonce, inline styles, `font-src 'self'` and `connect-src 'self'`.
- **Every telemetry string reaches the page through `web._e`** (`html.escape(..., quote=True)`), and every `/health` value through `health.plain_text`.
- **Every welfare number comes from `welfare`** (S9a §9). The renderer does display arithmetic only: the strip's correct count — `correct` plus `correct_reject`, the one rollup the PI ruled, for the strip alone (2026-09-26, spec §3) — and its percentage, two bar widths, and the time since the last reward (server clock minus `last_reward_at`). Every other count is shown as it occurred. Trials per minute is derived by `wlx serve` and labeled as derived.
- **Tests that open a socket set a client timeout** (5 s for HTTP requests, 10 s for event streams), register every `ZmqLink`/`ZmqConsole` they build with `zmq_cleanup`, and call `gc.collect()` after closing a `Server` or joining a background `wlx run` — both build a `ZmqConsole`/`ZmqLink` no test can register (`ZmqLink.close`'s docstring has the 300 s hang this prevents).
- **Do not edit `tests/conftest.py`.** Shared test data lives in `tests/_frames.py` (not collected: no `test_` prefix), imported as `from _frames import frame, view`.
- **Prove each new test can fail** (CLAUDE.md): Task 13 runs the mutation gate and reads its output line by line — `N failed` is a test noticing; `N errors in 0.8s` is not.
- **Never run the suite, edit a test, or `git add` while a mutation sweep is in flight.**
- Run tests with `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider` from the worktree root; the `wl-preproc` checkout must be beside the repo or inside it, as CI has it.
- Commit messages: imperative subject; body says why when it is not obvious; end with the two attribution lines the session supplies.

## Review Focus

The five conditions the spec implies that a person will meet and no task's main tests pin — each has its test added to the owning task:

1. **A frame this console cannot read** — a schema-6 `wlx run` beside a schema-7 `wlx serve` (this slice's own upgrade makes it likely), or a garbage packet → the page shows a *Refused* banner naming why, shows no guessed frame, and `wlx serve` keeps running. *Task 7 (banner), Task 9 (`Hub.reject`), Task 11 (`test_a_frame_this_console_cannot_read_is_shown_as_refused_not_guessed`).*
2. **Markup in any string a frame carries** — a task path, a condition name, an actor's typed name, a refusal's reason → text on the page in elements and attributes alike, spelled out on `/health`, never executed. *Task 6 (`test_markup_in_a_value_is_spelled_out_as_wl_preproc_does`), Task 7 (`test_every_telemetry_string_is_escaped`).*
3. **An outcome string this build does not know** — a newer `taskd` → counted under *Other* and ticked as *unknown outcome*, never dropped and never a crash. *Task 6 (`test_counts_are_grouped_by_family_and_never_summed`), Task 7 (`test_an_outcome_this_build_does_not_know_is_shown_not_dropped`).*
4. **A browser tab that stops reading** (asleep, backgrounded) while a simulator publishes at full speed → its queue stays at `QUEUE_DEPTH`, the telemetry thread never waits on it, it catches up in one render, and when it is closed the server forgets it. *Task 9 (`test_a_stream_that_falls_behind_keeps_only_the_newest_frames`), Task 10 (`test_a_browser_that_goes_away_is_forgotten`).*
5. **`wlx serve` restarted mid-session** → the session never notices, and the new console picks the running session up where it is. *Task 11 (`test_the_console_follows_a_simulated_session_through_a_restart_to_its_end`).*

## File Structure

| File | Responsibility |
|---|---|
| `wl_expcontroller/task.py` (modify) | `Family` and `Outcome.family`: the enum's documented groups, as data |
| `wl_expcontroller/welfare.py` (modify, **welfare-critical**) | `Welfare.last_delivery_wall_at`; `deliver(ref, wall_now)`; `Rig.wall_clock` |
| `wl_expcontroller/taskd.py` (modify) | `SessionSpec.bounds_config`; `Session.recent_outcomes`; `Session.parameters`; the Rig wired to the session's wall; the bounds path in the config snapshot |
| `wl_expcontroller/link.py` (modify) | `RECENT_OUTCOMES`; `ParamRow`; schema 7 fields, codec and `Telemetry.of`; `ZmqConsole(receive_timeout_s=...)` |
| `wl_expcontroller/cli.py` (modify) | `wlx run` passes the bounds path; `render` for schema 7; the `serve` subcommand's arguments |
| `wl_expcontroller/health.py` (create) | `/health`'s body: verdict, readings, plain text, outcome grouping — pure |
| `wl_expcontroller/web.py` (create) | `View`; `fragments()` — every pane as HTML; `page()` — the document, CSS and script; `FONTS` and `font_bytes` — pure |
| `wl_expcontroller/serve.py` (create) | `Hub`; the HTTP handler; `Server`; `wlx serve`'s `run()` |
| `wl_expcontroller/fonts/<family>/` (create) | The page's fonts, unmodified woff2, each family's `OFL.txt` beside them |
| `pyproject.toml` (modify) | `[tool.setuptools.package-data]`: the fonts and their licenses ship with the package |
| `docs/design/decisions/ADR-0004-license.md` (modify) | The fonts' inventory rows, under the OFL-fonts amendment the PI made 2026-09-26 |
| `tools/mutation_gate.py` (modify) | `health`, `web`, `serve` in `RETURNS` |
| `tests/_frames.py` (create) | A complete schema-7 frame and a `View`, for the three new test files |
| `tests/test_task.py`, `test_welfare.py`, `test_taskd.py`, `test_link.py`, `test_cli.py` (modify) | Each module's own changes |
| `tests/test_health.py`, `test_web.py`, `test_serve.py` (create) | The new modules; the `/health` contract; the end-to-end run |
| `tests/_transport_import_blocker.py`, `tests/test_no_transport_leak.py` (modify) | The three new modules import with no transport installed |
| `docs/design/architecture.md`, S9a spec, `docs/CHECKPOINT.md`, `docs/next-session.md` (modify) | Task 12 |

---

### Task 1: Outcome families, held on the enum as data

**Why:** spec §3 groups the behavioral counts by `Outcome`'s documented families — target, distractor, withhold, no engagement, breaks, rig — "encoded on the enum as data rather than left in comments". No correct/error/aborted definition is invented.

**Files:**
- Modify: `wl_expcontroller/task.py` (a `Family` enum before `Outcome`; a `family` property on `Outcome`; `_FAMILY` after it; the `Outcome` docstring's first paragraph)
- Test: `tests/test_task.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `task.Family` (members `TARGET`, `DISTRACTOR`, `WITHHOLD`, `NO_ENGAGEMENT`, `BREAKS`, `RIG`; values `"target"`, `"distractor"`, `"withhold"`, `"no engagement"`, `"breaks"`, `"rig"`, in that order); `Outcome.family -> Family` (a property; `Outcome.value` is unchanged). Tasks 6 and 7 group by it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_task.py`, change the import line to:

```python
from wl_expcontroller.task import Disc, Family, FixPoint, Outcome, P, Stimulus
```

and append:

```python
# ---------------------------------------------------------------------------
# Outcome families (P4d-2b spec §3): the groups the enum's comments draw, as data
# ---------------------------------------------------------------------------


def test_every_outcome_has_a_family():
    """Total, so a console can never meet an outcome it cannot group: a member added
    without one fails here rather than on a rig's screen."""
    for outcome in Outcome:
        assert isinstance(outcome.family, Family), outcome


def test_the_families_are_the_groups_the_enums_comments_draw():
    grouped = {
        family: [o.value for o in Outcome if o.family is family] for family in Family
    }

    assert grouped == {
        Family.TARGET: ["correct", "early_response", "late_response"],
        Family.DISTRACTOR: ["wrong_target", "early_error", "late_error"],
        Family.WITHHOLD: ["correct_reject", "false_alarm"],
        Family.NO_ENGAGEMENT: ["no_fixation", "no_response", "abort"],
        Family.BREAKS: [
            "fixation_break",
            "target_break",
            "catch_break",
            "motion_break",
            "blink_break",
        ],
        Family.RIG: ["tracker_lost", "fault"],
    }


def test_the_family_words_are_the_specs_in_its_order():
    assert [family.value for family in Family] == [
        "target",
        "distractor",
        "withhold",
        "no engagement",
        "breaks",
        "rig",
    ]


def test_a_family_leaves_the_wire_value_alone():
    """`family` is a property, not part of the value, so every record and every frame
    that carries `Outcome.value` reads exactly what it did before."""
    assert Outcome.CORRECT.value == "correct"
    assert Outcome("abort") is Outcome.ABORT
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_task.py`
Expected: collection error — `ImportError: cannot import name 'Family' from 'wl_expcontroller.task'`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/task.py`, immediately above `class Outcome(Enum):`, add:

```python
class Family(Enum):
    """Which kind of ending an `Outcome` is: the groups `Outcome`'s own comments have
    always drawn, held as data so a console can group by them (P4d-2b spec §3).

    **Grouping, never a rollup.** A console shows each outcome that occurred with its
    count, under its family, and never sums a family into one number. Nothing here
    defines correct, error or aborted: that is the PI's to define -- fixed on this
    enum or per task, and where `early_response`, `late_response` and `no_response`
    fall is open (spec §3, 2026-09-26).

    The values are the words a console prints.
    """

    TARGET = "target"
    DISTRACTOR = "distractor"
    WITHHOLD = "withhold"
    NO_ENGAGEMENT = "no engagement"
    BREAKS = "breaks"
    RIG = "rig"
```

Replace the first paragraph of `Outcome`'s docstring (the one that begins "Two families.") with:

```python
    """How a trial ended.

    **Six families, held as data** (`Family`, `Outcome.family`, P4d-2b spec §3):
    responses to the target, responses to a distractor, withholding, no engagement,
    breaks -- the trial ending because a hold was not maintained -- and the rig. The
    comments below mark the same groups.
```

keeping the existing second paragraph (about `ABORT`) as it is. At the end of the `Outcome` class body, after `FAULT = "fault"`, add:

```python

    @property
    def family(self) -> "Family":
        """This outcome's `Family`, from `_FAMILY` below the class. A property rather
        than part of the value, so `Outcome.value` stays the wire string every record
        and every telemetry frame already carries."""
        return _FAMILY[self]


#: Every `Outcome`'s family: the comment groups above, as data. **Total** --
#: `tests/test_task.py` fails if an outcome is added without one.
_FAMILY: dict[Outcome, Family] = {
    Outcome.CORRECT: Family.TARGET,
    Outcome.EARLY_RESPONSE: Family.TARGET,
    Outcome.LATE_RESPONSE: Family.TARGET,
    Outcome.WRONG_TARGET: Family.DISTRACTOR,
    Outcome.EARLY_ERROR: Family.DISTRACTOR,
    Outcome.LATE_ERROR: Family.DISTRACTOR,
    Outcome.CORRECT_REJECT: Family.WITHHOLD,
    Outcome.FALSE_ALARM: Family.WITHHOLD,
    Outcome.NO_FIXATION: Family.NO_ENGAGEMENT,
    Outcome.NO_RESPONSE: Family.NO_ENGAGEMENT,
    Outcome.ABORT: Family.NO_ENGAGEMENT,
    Outcome.FIXATION_BREAK: Family.BREAKS,
    Outcome.TARGET_BREAK: Family.BREAKS,
    Outcome.CATCH_BREAK: Family.BREAKS,
    Outcome.MOTION_BREAK: Family.BREAKS,
    Outcome.BLINK_BREAK: Family.BREAKS,
    Outcome.TRACKER_LOST: Family.RIG,
    Outcome.FAULT: Family.RIG,
}
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_task.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass (`Outcome`'s members and values are unchanged, so nothing else moves).

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/task.py tests/test_task.py
git commit -m "Hold the outcome families on the enum as data"
```

---

### Task 2: Welfare records when it last paid (welfare-critical)

**Why:** spec §4.1 — `last_reward_at` is "the wall instant of the last reward delivered, taken where `welfare` records a delivery". The strip's fourth cell (spec §4.0) is what keeps an unpaid working animal visible now that fluid session left the strip: fluid today standing still while the time since the last reward grows. **This changes `welfare.py`, so it is the item the PI approves in Task 13.**

**Files:**
- Modify: `wl_expcontroller/welfare.py` (`Welfare.last_delivery_wall_at`; `Welfare.deliver`; `Rig`)
- Modify: `wl_expcontroller/taskd.py` (the one `Rig(...)` construction, in `Session.__post_init__`)
- Test: `tests/test_welfare.py`, `tests/test_taskd.py`

**Interfaces:**
- Consumes: `Session.wall_now()` (P4d-2a Task 7 and Ruling 8: the session's anchored wall).
- Produces: `Welfare.last_delivery_wall_at: float | None` (default `None`); `Welfare.deliver(self, ref: str, wall_now: float) -> float`; `Rig.wall_clock: Callable[[], float]` (required field, after `welfare`). Task 4's `Telemetry.of` reads `session.welfare.last_delivery_wall_at`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_welfare.py`, in the `# --- the delivery path ---` part of the file (anywhere after `_welfare` is defined):

```python
def test_a_delivery_records_the_wall_instant_it_was_charged_at():
    """P4d-2b spec §4.1: the console's time since the last reward. **`None` before the
    first**, never `0.0`, which would read as a reward paid at the epoch."""
    welfare = _welfare()
    assert welfare.last_delivery_wall_at is None

    welfare.deliver("reward_correct", wall_now=WALL_NOW + 5.0)
    welfare.deliver("reward_correct", wall_now=WALL_NOW + 9.0)

    assert welfare.last_delivery_wall_at == WALL_NOW + 9.0


def test_a_rewards_instant_is_read_from_the_rigs_wall_clock():
    """`Rig` is what a task's `Reward` reaches, so it is what reads the clock: the
    session's own wall, handed to it as `wall_clock`."""
    welfare = _welfare()
    rig = Rig(card=Card(), wall_clock=lambda: WALL_NOW + 12.5, welfare=welfare)

    rig.reward("reward_correct")

    assert welfare.last_delivery_wall_at == WALL_NOW + 12.5


def test_a_delivery_the_pump_refused_is_still_charged_and_timed():
    """Charged before the valve opens, like `commanded` and `deliveries`, so the three
    always describe the same deliveries. A pump that raises ends the session anyway
    (`test_a_pump_fault_reaches_the_session_rather_than_being_absorbed`)."""

    class Failing:
        def deliver(self, ml: float) -> None:
            raise RuntimeError("solenoid did not answer")

    welfare = Welfare(
        bounds=_bounds(),
        pump=Failing(),
        already_today=0.0,
        deployment=Deployment.RIG_FIXED,
    )

    with pytest.raises(RuntimeError, match="solenoid"):
        welfare.deliver("reward_correct", wall_now=WALL_NOW)

    assert welfare.deliveries == 1
    assert welfare.last_delivery_wall_at == WALL_NOW
```

Append to `tests/test_taskd.py`, after `test_a_session_delivers_reward_and_the_day_counts_every_one`:

```python
def test_a_session_records_when_it_last_paid_on_its_own_wall_clock(tmp_path):
    """The path, not the piece: a task's `Reward`, through `Rig`, into `welfare`, on
    the session's wall. `_session` gives the wall `WALL_NOW` plus the frame clock, so
    a `Rig` that read `time.time()` instead would land decades outside this range."""
    session = _session(_spec(tmp_path, trials=50))

    census = session.run()

    assert census.outcomes[Outcome.CORRECT] > 0
    assert WALL_NOW <= session.welfare.last_delivery_wall_at <= session.wall_now()
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_welfare.py tests/test_taskd.py -k "charged_at or rigs_wall_clock or still_charged or last_paid"`
Expected: FAIL — `TypeError: Welfare.deliver() got an unexpected keyword argument 'wall_now'`, `TypeError: Rig.__init__() got an unexpected keyword argument 'wall_clock'`, and `AttributeError: 'Welfare' object has no attribute 'last_delivery_wall_at'`.

- [ ] **Step 3: Implement in `welfare.py`**

Add `from collections.abc import Callable` to the imports (beside `from dataclasses import dataclass, field`).

In `Welfare`, directly after `deliveries: int = 0`, add:

```python
    #: The wall instant, POSIX seconds, at which the last delivery was charged, or
    #: `None` before the first -- never `0.0`, which would read as a reward paid at
    #: the epoch. **Recorded for the console's time since the last reward, and
    #: compared against nothing** (P4d-2b spec §4.1, 2026-09-26): fluid today standing
    #: still while this ages is what keeps a working, unpaid animal visible now that
    #: the console's strip no longer carries fluid session (spec §4.0). Set where
    #: `commanded` and `deliveries` are, for their reason: charged before the valve.
    last_delivery_wall_at: float | None = None
```

Replace `deliver` with:

```python
    def deliver(self, ref: str, wall_now: float) -> float:
        """The only path from a `Reward` action to fluid.

        **No volume check, deliberately** (PI, 2026-09-06): there is no fluid
        ceiling. What bounds a delivery is `Ceiling.maximum` on `ref`, enforced when
        a console *sets* the volume -- the magnitude is a configuration decision and
        a task can only name it. **Charged before the valve opens**, so a pump that
        raises after opening leaves no fluid unaccounted.

        **`wall_now` says when, and it bounds nothing** (P4d-2b spec §4.1). It is kept
        as `last_delivery_wall_at` beside the charge and compared with no limit, so it
        is not refused when it is not a number: a refusal here would end a trial the
        animal completed over a display field. `Rig.reward` passes the session's
        wall, which is the only caller.
        """
        ml = self.bounds.value(ref)
        self.commanded += ml
        self.deliveries += 1
        self.last_delivery_wall_at = wall_now
        self.pump.deliver(ml)
        return ml
```

In `Rig`, append this paragraph to the class docstring (before its closing `"""`):

```python

    **`wall_clock` is the session's wall** (`taskd.Session.wall_now`), read once per
    reward so `Welfare.deliver` can record when it paid (P4d-2b spec §4.1) -- one
    clock read and one float store on the trial's path, per reward and never per
    frame. Required, with no default: a default of `time.time` would quietly disagree
    with a session whose wall a test injects, or that P4d-2a anchored.
```

and replace its fields and `reward` with:

```python
    card: Card
    welfare: Welfare
    wall_clock: Callable[[], float]

    def mark(self, code: int) -> None:
        self.card.emit(code)

    def reward(self, ref: str) -> None:
        self.welfare.deliver(ref, wall_now=self.wall_clock())
```

- [ ] **Step 4: Wire it in `taskd.py`**

In `Session.__post_init__`, replace `self.rig = Rig(card=self.card, welfare=self.welfare)` with:

```python
        # The session's own wall, so a reward's instant is on the base every welfare
        # mark is (P4d-2a spec §10) -- a bound method, so a wall a test injects after
        # construction is the one read.
        self.rig = Rig(card=self.card, welfare=self.welfare, wall_clock=self.wall_now)
```

- [ ] **Step 5: Update the existing welfare tests to the new signatures**

Every `welfare.deliver("reward_correct")` call in `tests/test_welfare.py` gains the wall instant, and every `Rig(...)` gains a clock. Run from the worktree root:

```bash
python - <<'EOF'
from pathlib import Path

path = Path("tests/test_welfare.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    '.deliver("reward_correct")', '.deliver("reward_correct", wall_now=WALL_NOW)'
)
text = text.replace(
    "Rig(card=Card(), welfare=", "Rig(card=Card(), wall_clock=lambda: WALL_NOW, welfare="
)
text = text.replace(
    "rig = Rig(\n        card=Card(),\n",
    "rig = Rig(\n        card=Card(),\n        wall_clock=lambda: WALL_NOW,\n",
)
path.write_text(text, encoding="utf-8")
EOF
grep -n "Rig(" tests/test_welfare.py
grep -c 'deliver("reward_correct")' tests/test_welfare.py
```

Expected: every `Rig(` line printed carries or is followed by `wall_clock=` exactly once, and the count of bare `deliver("reward_correct")` is `0`. The tests Step 1 added are unchanged by the script: they already pass `wall_now=`, and the one new `Rig(...)` names `wall_clock` before `welfare`, so the pattern does not match it.

Then add three entries to `NOT_ENTRY_POINTS` in `tests/test_welfare.py`, after the `"Rig.mark.code"` entry:

```python
    # P4d-2b b1 (spec §4.1): when the last reward was charged, for the console's time
    # since the last reward. Compared against nothing, so refusing a non-finite one
    # would end a trial the animal completed over a display field -- the reason
    # `Welfare.deliveries` is exempt, on an instant.
    "Welfare.deliver.wall_now": (
        "a display instant stored as last_delivery_wall_at and compared against no "
        "limit; refusing it would abort a completed trial over a display field"
    ),
    "Welfare.last_delivery_wall_at": (
        "as Welfare.deliver.wall_now; read by telemetry and compared against nothing"
    ),
    "Rig.wall_clock": (
        "a callable, not a number; the instant it returns is Welfare.deliver.wall_now"
    ),
```

- [ ] **Step 6: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_welfare.py tests/test_taskd.py`
Expected: all pass, including `test_the_enumeration_of_numeric_entry_points_is_complete` (it would name the three new doors if the exemptions were missing).
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add wl_expcontroller/welfare.py wl_expcontroller/taskd.py tests/test_welfare.py tests/test_taskd.py
git commit -m "Record when welfare last charged a reward, on the session's wall"
```

Body: this is welfare-critical and awaits the PI's approval (Task 13); the instant bounds nothing and is not refused when non-finite, for the reason `deliver`'s docstring gives.

---

### Task 3: The session surfaces what schema 7 reads

**Why:** spec §3 and §4.1 add fields that must each come from "the object the record is written from". Three have no public source yet: the last 60 outcomes, the parameter rows, and which bounded config the session runs under — `SessionSpec` holds the `Bounds` object and never the file it came from.

**Files:**
- Modify: `wl_expcontroller/link.py` (one constant, `RECENT_OUTCOMES`, beside `REFUSAL_HISTORY`)
- Modify: `wl_expcontroller/taskd.py` (`SessionSpec.bounds_config`; `Session._recent`, `recent_outcomes`, `parameters`; the snapshot's `versions`; the trial record)
- Modify: `wl_expcontroller/cli.py` (`wlx run` passes the bounds path)
- Test: `tests/test_taskd.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `Session._params()` (existing: name → `task.Param`), `welfare.OUT_OF_CAGE`.
- Produces:
  - `link.RECENT_OUTCOMES = 60`.
  - `SessionSpec.bounds_config: str = ""`.
  - `Session.recent_outcomes -> tuple[str, ...]` (property; the strings `trials.jsonl` records, `"hang"` included, oldest first, at most `RECENT_OUTCOMES`).
  - `Session.parameters -> tuple[tuple[str, str, float | None, float | None, float | str | None, bool], ...]` (property; `(name, unit, low, high, value, bounded)`; task `Param`s in declaration order, then every ceiling except `out_of_cage` as `(name, unit, 0.0, maximum, value, True)`).
  - `config.json`'s `versions["bounds"]` = `spec.bounds_config`.
  Task 4's `Telemetry.of` reads all three.

- [ ] **Step 1: Write the failing tests**

In `tests/test_taskd.py`, add `from pathlib import Path` to the imports, add `from wl_expcontroller.cli import _load_trial`, and add `RECENT_OUTCOMES` to the existing `from wl_expcontroller.link import (...)` block. Append:

```python
# --- what the browser console reads (P4d-2b b1) ------------------------------


def test_a_session_keeps_the_last_sixty_outcomes_as_the_record_wrote_them(tmp_path):
    """Spec §4.1: the Runtime pane's ticks. **The record's own strings**, `hang`
    included: one string is computed and handed to both, so a tick can never say what
    `trials.jsonl` does not."""
    session = _session(_spec(tmp_path, trials=100))
    assert session.recent_outcomes == ()

    session.run()

    recorded = [
        json.loads(line)["outcome"]
        for line in (session.directory / "trials.jsonl").read_text().splitlines()
    ]
    assert len(recorded) == 100
    assert session.recent_outcomes == tuple(recorded[-RECENT_OUTCOMES:])
    assert len(session.recent_outcomes) == RECENT_OUTCOMES == 60


def test_the_parameters_a_console_shows_are_the_declarations_then_the_ceilings(
    tmp_path,
):
    """Spec §3: the parameter pane is generated from `params`. The task's own
    declarations with their current values, then each ceiling a console could stage
    -- and not the out-of-cage ceiling, which is the limit a clock runs against and
    not a task setting."""
    session = _session(_spec(tmp_path))
    declared = _load_trial(Path("tasks/fixation_detection.py")).params

    rows = session.parameters
    by_name = {row[0]: row for row in rows}

    assert [row[0] for row in rows[: len(declared)]] == [p.name for p in declared]
    fix_hold = next(p for p in declared if p.name == "fix_hold")
    assert by_name["fix_hold"] == (
        "fix_hold",
        fix_hold.unit,
        fix_hold.low,
        fix_hold.high,
        0.3,
        False,
    )
    assert by_name["reward_correct"] == ("reward_correct", "mL", 0.0, 0.40, 0.15, True)
    assert "out_of_cage" not in by_name


def test_a_parameter_nobody_set_is_unset_not_zero(tmp_path):
    spec = _spec(tmp_path)
    del spec.values["fix_hold"]
    session = _session(spec)

    values = {row[0]: row[4] for row in session.parameters}

    assert values["fix_hold"] is None


def test_the_config_snapshot_names_the_bounded_config_it_ran_under(tmp_path):
    """S9a §3's "which bounded config" had no source: `SessionSpec` holds `Bounds`,
    never the file it came from. It is recorded where the task and allocation are."""
    session = _session(_spec(tmp_path, trials=2, bounds_config="subjects/A/bounds.py"))

    session.run()

    config = json.loads((session.directory / "config.json").read_text())
    assert config["versions"]["bounds"] == "subjects/A/bounds.py"
```

Append to `tests/test_cli.py`:

```python
def test_wlx_run_records_which_bounded_config_it_ran_under(tmp_path):
    """P4d-2b spec §3: the console's Setup pane names the bounded config, read from
    the same place the record keeps it."""
    exit_code = main(
        [
            "run", GOOD,
            "--allocation", ALLOCATION,
            "--bounds", BOUNDS,
            "--root", str(tmp_path),
            "--session-id", "2027-01-14_09",
            "--subject", "REFERENCE",
            "--out-of-cage-at", _hhmm(),
            "--delivered-today", "0",
            "--trials", "2",
            *_TASK_SETS,
        ]
    )

    assert exit_code == 0
    config = json.loads(
        (tmp_path / "2027-01-14_09" / "expcontroller" / "config.json").read_text()
    )
    assert config["versions"]["bounds"] == BOUNDS
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py tests/test_cli.py -k "sixty_outcomes or declarations_then or unset_not_zero or bounded_config"`
Expected: collection error `ImportError: cannot import name 'RECENT_OUTCOMES'`; after Step 3's first edit, `AttributeError` on `recent_outcomes`/`parameters` and `KeyError: 'bounds'`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/link.py`, directly after `REFUSAL_HISTORY = 50`, add:

```python

#: How many recent outcomes a `Telemetry` frame carries, oldest first: the browser
#: console's Runtime ticks (P4d-2b spec §4.1, "the last 60"). Capped for
#: `REFUSAL_HISTORY`'s reason -- a frame is re-encoded at every trial boundary -- and a
#: display bound, not a measurement.
RECENT_OUTCOMES = 60
```

In `wl_expcontroller/taskd.py`:

1. Add `from collections import deque` to the imports, and `OUT_OF_CAGE` to the `from wl_expcontroller.welfare import (...)` block.
2. In `SessionSpec`, directly after `warn_within: float = WARN_WITHIN_DEFAULT` and its comment, add:

```python
    #: Where `bounds` was loaded from, as the operator named it: S9a §3's "which
    #: bounded config" (P4d-2b spec §3). Written into the config snapshot beside the
    #: task and the allocation, and published from there. Empty when a caller built
    #: `Bounds` in code, as the tests do; a console then says *not given* rather than
    #: inventing a name.
    bounds_config: str = ""
```

3. In `Session`, directly after the `stop_kind` field, add:

```python
    #: The last `link.RECENT_OUTCOMES` outcomes as the strings `trials.jsonl` records
    #: (`hang` for a trial with no outcome), oldest first (P4d-2b spec §4.1). Appended
    #: beside `record.trial`, from the one string both are given.
    _recent: deque = field(
        init=False,
        default_factory=lambda: deque(maxlen=_link.RECENT_OUTCOMES),
        repr=False,
    )
```

4. Directly after the `staged` property, add:

```python
    @property
    def recent_outcomes(self) -> tuple:
        """The last `link.RECENT_OUTCOMES` outcome strings, oldest first -- the public
        face of `_recent`, for the reason `staged` is public."""
        return tuple(self._recent)

    @property
    def parameters(self) -> tuple:
        """Every settable value a console shows, as `(name, unit, low, high, value,
        bounded)` -- the shape `link.Telemetry.of` builds its `ParamRow`s from (P4d-2b
        spec §3: "the parameter row is generated from it").

        The task's own `Param` declarations first, in declaration order, each with
        its value in `spec.values` (`None` when nobody set it); then every welfare
        ceiling a console could stage through `set`, bounded, over `[0, maximum]` --
        a ceiling's value is a magnitude (`bounds._magnitude`), so zero is its floor.

        **Not the out-of-cage ceiling.** It is the limit the session's clock runs
        against, published as that (`Telemetry.out_of_cage_limit_s`); a parameter
        card for it would set the duration limit beside a fixation hold as though it
        were a task setting.
        """
        declared = tuple(
            (p.name, p.unit, p.low, p.high, self.spec.values.get(p.name), False)
            for p in self._params().values()
        )
        ceilings = tuple(
            (name, ceiling.unit, 0.0, ceiling.maximum, ceiling.value, True)
            for name, ceiling in self.spec.bounds.ceilings.items()
            if name != OUT_OF_CAGE
        )
        return declared + ceilings
```

5. In `run()`, replace the snapshot's `versions=` argument with:

```python
            versions={
                "task": self.spec.task,
                "allocation": self.spec.allocation,
                "bounds": self.spec.bounds_config,
            },
```

6. In `run()`'s loop, replace the `record.trial(...)` call with:

```python
                # One string for the record and for a console's recent outcomes, so
                # the two cannot disagree (P4d-2b spec §4.1).
                recorded = result.outcome.value if result.outcome else "hang"
                self._recent.append(recorded)
                record.trial(
                    index=index,
                    outcome=recorded,
                    params=values,
                    block=scheduler.block.name,
                    condition=condition.name,
                )
```

In `wl_expcontroller/cli.py`, in `wlx run`'s `SessionSpec(...)` call, directly after the `warn_within=(...)` argument, add:

```python
                        # Which bounded config, as the operator named it: recorded in
                        # the config snapshot and published to consoles (P4d-2b §3).
                        bounds_config=str(args.bounds),
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_taskd.py tests/test_cli.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/taskd.py wl_expcontroller/cli.py tests/test_taskd.py tests/test_cli.py
git commit -m "Keep the recent outcomes, the parameter rows and the bounds path on the session"
```

---
### Task 4: Telemetry schema 7 on the wire

**Why:** spec §3 and §4.1. Schema 7 carries the configuration a session runs under (`task`, `allocation`, `bounds_config`, `params`), the two limits its numbers are read against (`floor_ml`, `out_of_cage_limit_s`), `last_reward_at` and `recent_outcomes`. `in_session_seconds` is already on the frame (P4d-2a Task 9).

**Files:**
- Modify: `wl_expcontroller/link.py` (import two welfare constants; `ParamRow`; `SCHEMA`; eight `Telemetry` fields; `Telemetry.of`; `encode`; `decode`)
- Test: `tests/test_link.py` (the `_session_with` stand-in; new tests; one assertion in `test_the_phase_and_the_kind_of_stop_survive_the_wire`)
- Modify tests: `tests/test_cli.py` (the `_telemetry` fixture constructs a `Telemetry` field by field)

**Interfaces:**
- Consumes: Task 2's `Welfare.last_delivery_wall_at`; Task 3's `Session.parameters`, `Session.recent_outcomes`, `SessionSpec.bounds_config`; `welfare.DAILY_FLUID`, `welfare.OUT_OF_CAGE`.
- Produces:
  - `link.ParamRow(name: str, unit: str, low: float | None, high: float | None, value: float | str | None, bounded: bool)` — frozen, slotted.
  - `link.SCHEMA == 7`.
  - `Telemetry` gains, after its last existing field: `task: str`, `allocation: str`, `bounds_config: str`, `params: tuple` (of `ParamRow`), `floor_ml: float`, `out_of_cage_limit_s: float | None`, `last_reward_at: float | None`, `recent_outcomes: tuple` (of `str`).
  Tasks 5–11 read these by name.

- [ ] **Step 1: Write the failing tests**

In `tests/test_link.py`, add `ParamRow` and `SCHEMA` to the `from wl_expcontroller.link import (...)` block.

In `_session_with`, add three keyword arguments to the inner `spec=SimpleNamespace(...)`:

```python
            task="tasks/fixation_detection.py",
            allocation="tasks/allocation.py",
            bounds_config="subjects/A/bounds.py",
```

and two to the outer `SimpleNamespace(...)`, beside `staged=()`:

```python
        # Stand-ins for `Session.parameters` and `Session.recent_outcomes` (P4d-2b
        # b1): the shapes `Telemetry.of` reads, as `staged` and `refusals` are.
        parameters=(
            ("fix_hold", "s", 0.1, 1.0, 0.3, False),
            ("reward_correct", "mL", 0.0, 0.4, 0.15, True),
        ),
        recent_outcomes=("correct", "hang"),
```

In `test_the_phase_and_the_kind_of_stop_survive_the_wire`, change `assert restored.schema == 6` to `assert restored.schema == SCHEMA`.

Append:

```python
# ---------------------------------------------------------------------------
# Schema 7 (P4d-2b b1): what the browser console reads
# ---------------------------------------------------------------------------


def test_schema_7_reads_the_configuration_from_the_session():
    """Spec §3: which task, which allocation, which bounded config, and the parameter
    rows -- each from the object the record is written from."""
    session = _session_with(delivered_ml=1.0, already_today=None)

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.schema == SCHEMA == 7
    assert telemetry.task == "tasks/fixation_detection.py"
    assert telemetry.allocation == "tasks/allocation.py"
    assert telemetry.bounds_config == "subjects/A/bounds.py"
    assert telemetry.params == (
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
        ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
    )
    assert telemetry.recent_outcomes == ("correct", "hang")


def test_the_limits_are_the_ones_welfare_reads_them_against():
    """`floor_ml` is the day's floor and `out_of_cage_limit_s` the ceiling's *value*
    -- the number `welfare.must_stop` compares with -- never its maximum."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.welfare.bounds.ceilings["out_of_cage"] = Ceiling(
        value=3_600.0, maximum=43_200.0, unit="s"
    )

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.floor_ml == 250.0
    assert telemetry.out_of_cage_limit_s == 3_600.0


def test_a_cage_side_session_has_no_limit_to_publish():
    """`None`, never `0.0`: a cage-side session has no out-of-cage ceiling at all, and
    a zero would read as a limit already reached."""
    session = _session_with(delivered_ml=1.0, already_today=None)
    session.welfare = Welfare(
        bounds=Bounds(
            subject="A",
            ceilings={},
            minima={"daily_fluid": Floor(value=250.0, unit="mL")},
        ),
        pump=Pump(),
        already_today=None,
        deployment=Deployment.CAGE_SIDE,
    )
    session.spec.deployment = Deployment.CAGE_SIDE
    session.duration_warning = lambda wall_now: None

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)

    assert telemetry.out_of_cage_limit_s is None
    assert telemetry.out_of_cage_seconds is None


def test_the_last_reward_is_welfares_instant_and_none_before_the_first():
    session = _session_with(delivered_ml=1.0, already_today=None)
    assert Telemetry.of(session, Tally(), _scheduler(), index=0).last_reward_at is None

    session.welfare.last_delivery_wall_at = 1_700_000_123.0

    telemetry = Telemetry.of(session, Tally(), _scheduler(), index=0)
    assert telemetry.last_reward_at == 1_700_000_123.0


def test_schema_7_survives_the_wire_with_its_absences_intact():
    """The golden round trip, with every new field populated and every new `None`
    present: a missing reward time, a cage-side limit, an unset parameter, and a
    categorical one whose value is a string."""
    original = _telemetry(
        params=(
            ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
            ParamRow("target_looks", "", None, None, None, False),
            ParamRow("shape", "", None, None, "penguin", False),
        ),
        recent_outcomes=("correct", "hang", "no_fixation"),
        last_reward_at=None,
        out_of_cage_limit_s=None,
    )

    restored = decode(encode(original))

    assert restored == original
    assert [type(p) for p in restored.params] == [ParamRow, ParamRow, ParamRow]
    assert restored.params[1].value is None
    assert restored.params[2].value == "penguin"
    assert restored.recent_outcomes == ("correct", "hang", "no_fixation")
    assert restored.last_reward_at is None
    assert restored.out_of_cage_limit_s is None
```

In `tests/test_cli.py`, in the `_telemetry` fixture's `Telemetry(...)` call, add after the last existing keyword argument:

```python
        task="tasks/fixation_detection.py",
        allocation="tasks/allocation.py",
        bounds_config="tasks/reference_bounds.py",
        params=(),
        floor_ml=250.0,
        out_of_cage_limit_s=600.0,
        last_reward_at=None,
        recent_outcomes=(),
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_cli.py`
Expected: collection error — `ImportError: cannot import name 'ParamRow'`; and in `test_cli.py`, `TypeError: Telemetry.__init__() got an unexpected keyword argument 'task'`.

- [ ] **Step 3: Implement in `link.py`**

After `from typing import Protocol`, add:

```python

from wl_expcontroller.welfare import DAILY_FLUID, OUT_OF_CAGE
```

Replace `SCHEMA = 6` with:

```python
#:
#: 7 (2026-09-26, P4d-2b b1): the configuration a session runs under (`task`,
#: `allocation`, `bounds_config`, `params`), the two limits its numbers are read
#: against (`floor_ml`, `out_of_cage_limit_s`), `last_reward_at` and
#: `recent_outcomes`. Nothing changed meaning. A reader built against 6 decodes a
#: schema-7 frame and ignores the additions; a schema-7 reader cannot decode a
#: schema-6 frame, which lacks them, and `wlx serve` says so on its page rather than
#: showing a guess (`serve.Server._listen`).
SCHEMA = 7
```

Directly after the `Refused` class, add:

```python
@dataclass(frozen=True, slots=True)
class ParamRow:
    """One settable value, as the browser console's parameter pane shows it (P4d-2b
    spec §3: "the parameter row is generated from it").

    From `taskd.Session.parameters`: a task `Param` with its current value, or a
    welfare ceiling (`bounded=True`) over `[0, maximum]`. `value` is `None` when the
    task declares a parameter nobody set -- a console prints *unset*, never `0` --
    and may be a string for a categorical one.
    """

    name: str
    unit: str
    low: float | None
    high: float | None
    value: float | str | None
    bounded: bool
```

In `Telemetry`, after its last existing field, add:

```python
    #: `session.spec.task` -- the task file this session loaded: S9a §3's
    #: configuration information (P4d-2b spec §3). Also in the config snapshot.
    task: str
    #: `session.spec.allocation`. Empty is the provisional allocation (`cli`).
    allocation: str
    #: `session.spec.bounds_config`: the bounded config's file. Empty when nobody
    #: named one, which a console says rather than filling in.
    bounds_config: str
    #: `session.parameters`, as `ParamRow`s: the task's declarations, then the welfare
    #: ceilings a console may stage (P4d-2b spec §3).
    params: tuple
    #: The day's fluid floor, `welfare.bounds.minima[DAILY_FLUID].value` -- what
    #: `fluid_today_ml` is read against. `Welfare` refuses a config without one, so it
    #: is never `None`.
    floor_ml: float
    #: The ceiling the out-of-cage clock runs against, `ceilings[OUT_OF_CAGE].value`
    #: -- the number `welfare.must_stop` compares with, not the maximum. `None`
    #: cage-side, where `Welfare` refuses a config that declares one.
    out_of_cage_limit_s: float | None
    #: `welfare.last_delivery_wall_at`: when the last reward was charged, POSIX
    #: seconds on the session's wall, or `None` before the first -- never `0.0`
    #: (P4d-2b spec §4.1). A console subtracts it from its own clock.
    last_reward_at: float | None
    #: `session.recent_outcomes`: the last `RECENT_OUTCOMES` outcome strings, oldest
    #: first, exactly as `trials.jsonl` records them, `hang` included.
    recent_outcomes: tuple
```

In `Telemetry.of`, directly before `return cls(`, add:

```python
        # Read, never decided: `Welfare` guarantees a rig session has this ceiling
        # and a cage-side one does not, so its absence is the cage-side case.
        limit = session.welfare.bounds.ceilings.get(OUT_OF_CAGE)
```

and add these keyword arguments after the last existing one in the `cls(...)` call:

```python
            # P4d-2b b1 (spec §3, §4.1). The configuration is the spec's -- what the
            # config snapshot records -- and the rest is `welfare`'s and the
            # session's own, read through their public surface.
            task=session.spec.task,
            allocation=session.spec.allocation,
            bounds_config=session.spec.bounds_config,
            params=tuple(ParamRow(*row) for row in session.parameters),
            floor_ml=session.welfare.bounds.minima[DAILY_FLUID].value,
            out_of_cage_limit_s=None if limit is None else limit.value,
            last_reward_at=session.welfare.last_delivery_wall_at,
            recent_outcomes=session.recent_outcomes,
```

In `encode`'s `payload` dict, add after the last existing entry:

```python
        "task": telemetry.task,
        "allocation": telemetry.allocation,
        "bounds_config": telemetry.bounds_config,
        "params": [
            {
                "name": p.name,
                "unit": p.unit,
                "low": p.low,
                "high": p.high,
                "value": p.value,
                "bounded": p.bounded,
            }
            for p in telemetry.params
        ],
        "floor_ml": telemetry.floor_ml,
        "out_of_cage_limit_s": telemetry.out_of_cage_limit_s,
        "last_reward_at": telemetry.last_reward_at,
        "recent_outcomes": list(telemetry.recent_outcomes),
```

In `decode`'s `Telemetry(...)` call, add after the last existing argument:

```python
        task=data["task"],
        allocation=data["allocation"],
        bounds_config=data["bounds_config"],
        params=tuple(ParamRow(**p) for p in data["params"]),
        floor_ml=data["floor_ml"],
        out_of_cage_limit_s=data["out_of_cage_limit_s"],
        last_reward_at=data["last_reward_at"],
        recent_outcomes=tuple(data["recent_outcomes"]),
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_link.py tests/test_cli.py tests/test_taskd.py`
Expected: all pass. `test_wlx_run_with_link_lets_a_real_console_attach` decodes real schema-7 frames from a real `wlx run`, so it is the path check for Tasks 2–4 together.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass, and `tests/test_no_transport_leak.py` still passes (`welfare` imports no transport).

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py tests/test_link.py tests/test_cli.py
git commit -m "Carry the session's configuration, limits, last reward and recent outcomes: schema 7"
```

---

### Task 5: `wlx console` renders schema 7

**Why:** the terminal client is a console too, and `render`'s promise is that every line names a field. Schema 7's fields each get a line, and every absence is a word.

**Files:**
- Modify: `wl_expcontroller/cli.py` (`render`; two small formatting helpers beside `_value`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 4's fields and `link.ParamRow`.
- Produces: `render` prints, in this order among its lines: `  task: T  allocation: A  bounds: B` after the deployment line; `  fluid today: X mL of a F mL floor` (or the `UNKNOWN` sentence with `(floor F mL)`); `  out of cage: C of L` when a limit is published; `  last reward: none yet` or `  last reward: at HH:MM:SS`; one `  param: ...` line per `ParamRow`; `  recent (oldest first): ...` or `  recent: none yet`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py`, add `ParamRow` to the `from wl_expcontroller.link import (...)` block, and append:

```python
# ---------------------------------------------------------------------------
# `render` and schema 7 (P4d-2b b1)
# ---------------------------------------------------------------------------


def test_console_names_the_task_allocation_and_bounded_config():
    rendered = render(_telemetry())

    assert (
        "  task: tasks/fixation_detection.py  allocation: tasks/allocation.py"
        "  bounds: tasks/reference_bounds.py"
    ) in rendered.splitlines()


def test_console_names_an_absent_allocation_and_bounded_config():
    """An empty allocation is the provisional one and an empty bounds path means
    nobody named the file: both said, never printed as nothing."""
    rendered = render(_telemetry(allocation="", bounds_config=""))

    assert "allocation: PROVISIONAL (none given)" in rendered
    assert "bounds: not given" in rendered


def test_console_reads_fluid_today_against_the_days_floor():
    known = render(_telemetry(fluid_today_ml=61.25)).splitlines()
    unknown = render(_telemetry(fluid_today_ml=None))

    assert "  fluid today: 61.25 mL of a 250.00 mL floor" in known
    assert "fluid today: UNKNOWN" in unknown
    assert "(floor 250.00 mL)" in unknown


def test_console_reads_the_out_of_cage_clock_against_its_limit():
    rendered = render(_telemetry(out_of_cage_seconds=96.0, out_of_cage_limit_s=600.0))

    assert "  out of cage: 1:36 of 10:00" in rendered.splitlines()


def test_console_says_no_reward_yet_rather_than_a_time():
    assert "  last reward: none yet" in render(
        _telemetry(last_reward_at=None)
    ).splitlines()


def test_console_prints_the_last_rewards_clock_time():
    at = 1_700_000_000.0
    expected = time.strftime("%H:%M:%S", time.localtime(at))

    assert f"  last reward: at {expected}" in render(
        _telemetry(last_reward_at=at)
    ).splitlines()


def test_console_lists_every_parameter_with_its_range_or_its_ceiling():
    rendered = render(
        _telemetry(
            params=(
                ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
                ParamRow("reward_correct", "mL", 0.0, 10.0, 0.05, True),
                ParamRow("target_looks", "", None, None, None, False),
                ParamRow("fix_window", "deg", None, 5.0, 2.0, False),
            )
        )
    ).splitlines()

    assert "  param: fix_hold 0.30 s (range 0.1 to 1 s)" in rendered
    assert "  param: reward_correct 0.05 mL (welfare ceiling 10.00 mL)" in rendered
    assert "  param: target_looks unset (no declared range)" in rendered
    assert "  param: fix_window 2.00 deg (range open to 5 deg)" in rendered


def test_console_lists_the_recent_outcomes_oldest_first():
    assert "  recent (oldest first): correct hang no_fixation" in render(
        _telemetry(recent_outcomes=("correct", "hang", "no_fixation"))
    ).splitlines()
    assert "  recent: none yet" in render(_telemetry()).splitlines()
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_cli.py -k "names_the_task or absent_allocation or days_floor or against_its_limit or reward or every_parameter or recent_outcomes"`
Expected: FAIL — the lines are absent.

- [ ] **Step 3: Implement**

In `wl_expcontroller/cli.py`, directly after `_value`, add:

```python
def _shown(value: object) -> str:
    """A parameter's value on the terminal: `unset` for `None`, two decimals for a
    number, like every other figure on this screen, and the text of a categorical
    choice. Formatting, not derivation -- see `_value`."""
    if value is None:
        return "unset"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value)


def _edge(value: float | None) -> str:
    """One end of a declared range: `open` where the task declared none."""
    return "open" if value is None else f"{value:g}"


def _with_unit(text: str, unit: str) -> str:
    return f"{text} {unit}" if unit else text
```

In `render`, directly after `lines.append(f"  deployment: {frame.deployment}")`, add:

```python
    # P4d-2b spec §3: S9a §3's configuration information. Named, never guessed: an
    # empty allocation is the provisional one (`_load_allocation`), and an empty
    # bounds path means the caller built `Bounds` in code.
    lines.append(
        f"  task: {frame.task}"
        f"  allocation: {frame.allocation or 'PROVISIONAL (none given)'}"
        f"  bounds: {frame.bounds_config or 'not given'}"
    )
```

Replace the `fluid today` append with:

```python
    lines.append(
        f"  fluid today: UNKNOWN -- the day's prior total was not supplied "
        f"(floor {frame.floor_ml:.2f} mL)"
        if frame.fluid_today_ml is None
        else f"  fluid today: {frame.fluid_today_ml:.2f} mL of a "
        f"{frame.floor_ml:.2f} mL floor"
    )
```

Replace the `out of cage` append with:

```python
    if frame.out_of_cage_seconds is None:
        lines.append("  out of cage: n/a -- cage-side, the animal is home")
    elif frame.out_of_cage_limit_s is None:
        lines.append(f"  out of cage: {_clock(frame.out_of_cage_seconds)}")
    else:
        # Against the ceiling's value, the number the session is stopped on (schema 7).
        lines.append(
            f"  out of cage: {_clock(frame.out_of_cage_seconds)} of "
            f"{_clock(frame.out_of_cage_limit_s)}"
        )
```

Directly before the `still_owed` lines, add:

```python
    # When the last reward was charged, as a clock time on this host (P4d-2b spec
    # §4.1). None yet is said, never printed as a time.
    lines.append(
        "  last reward: none yet"
        if frame.last_reward_at is None
        else f"  last reward: at "
        f"{time.strftime('%H:%M:%S', time.localtime(frame.last_reward_at))}"
    )
    for row in frame.params:
        if row.bounded:
            limit = f"(welfare ceiling {_with_unit(_shown(row.high), row.unit)})"
        elif row.low is None and row.high is None:
            limit = "(no declared range)"
        else:
            limit = (
                f"(range {_edge(row.low)} to "
                f"{_with_unit(_edge(row.high), row.unit)})"
            )
        lines.append(
            f"  param: {row.name} {_with_unit(_shown(row.value), row.unit)} {limit}"
        )
    lines.append(
        f"  recent (oldest first): {' '.join(frame.recent_outcomes)}"
        if frame.recent_outcomes
        else "  recent: none yet"
    )
```

Add one paragraph to `render`'s docstring, before its closing `"""`:

```python

    **Schema 7 adds the configuration and the limits** (P4d-2b b1): which task,
    allocation and bounded config; fluid today against the day's floor; the
    out-of-cage clock against the ceiling it is stopped on; when the last reward was
    charged; the parameter rows; and the last outcomes. Each absence is a word --
    *PROVISIONAL*, *not given*, *none yet*, *unset*, *open* -- never a zero.
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_cli.py`
Expected: all pass, the earlier render tests included (`out of cage: 1:06:47` is still a substring of its line, and no new line prints `0:00`, `107.0` or `task parameter`).
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/cli.py tests/test_cli.py
git commit -m "Show schema 7 in wlx console: configuration, limits, last reward, parameters"
```

---
### Task 6: `/health`'s body — verdict, readings, and the contract

**Why:** spec §3. `/health` is `wl_preproc.contracts.protocol.HealthResponse`, schema version 1; readings are plain text with `<`, `>` and `&` spelled out as their `plain_text` does; the verdict follows spec §3's table and never says `unknown`; `actions` is always empty. The behavioral counts are grouped by family with no rollup, shown identically here and on the Working? pane — so the grouping function lives here and Task 7 renders it.

**Exactly one reading is featured, the most urgent** (PI, 2026-09-26, recorded in spec §3). wl-works' Plan 10 §4 (`wl-works/docs/superpowers/specs/2026-08-03-plan-10-infrastructure-dashboard-design.md`, read 2026-09-26) says of more than one featured reading "the first wins", and wl-preproc's responder emits exactly one for that reason (`docs/ops/lab-host-protocol.md`, "`featured`: exactly one, always"). `_featured` holds the ruled order: the duration warning when active; else the state when the session faulted or ended on the limit and the animal is not back; else the last frame's age when the stream went stale; else the time out of the cage; and, where there is no out-of-cage clock (cage-side, or no session yet), the state.

**Files:**
- Create: `wl_expcontroller/health.py`
- Create: `tests/_frames.py`
- Create: `tests/test_health.py`
- Modify: `tools/mutation_gate.py` (`"health": "None"` in `RETURNS`)

**Interfaces:**
- Consumes: Task 1's `Family`, `Outcome.family`; Task 4's `Telemetry` fields; `cli._clock`.
- Produces (all pure):
  - `health.HEALTH_SCHEMA = 1`
  - `health.plain_text(text: str) -> str`
  - `health.ago(seconds: float) -> str` — `"42 s"`, `"10 min"`, `"2:00:00"`
  - `health.family_key(wire: str) -> str` — `"target"`, …, `"no_engagement"`, …, `"hang"`, `"other"`
  - `health.families(outcomes: dict) -> list[tuple[str, str, list[tuple[str, object]]]]` — `(key, label, [(outcome, count), ...])`
  - `health.expects_frames(frame: Telemetry | None) -> bool`
  - `health.verdict(frame: Telemetry | None, *, frame_age_s: float | None, stale_after_s: float) -> str`
  - `health.readings(frame, *, frame_age_s, stale_after_s) -> list[dict]` — each `{"key", "label", "value", "featured"}`
  - `health.response(frame, *, frame_age_s, stale_after_s) -> dict` — `{"verdict", "readings", "actions": []}`
  - `tests/_frames.frame(**overrides) -> Telemetry`

- [ ] **Step 1: Write the test data and the failing tests**

Create `tests/_frames.py`:

```python
"""A complete schema-7 `Telemetry` frame for the browser console's tests (P4d-2b b1).

Imported by `test_health.py`, `test_web.py` and `test_serve.py` as
`from _frames import frame`; never collected, because its name does not start with
`test_`. Every field holds a value a test can find in rendered output, and every
field that may be `None` holds a number here, so a test that wants an absence asks
for it by name.
"""

from __future__ import annotations

from dataclasses import replace

from wl_expcontroller.link import SCHEMA, ParamRow, Telemetry


def frame(**overrides) -> Telemetry:
    """A running rig session, forty trials in. Distinctive numbers: 5025 s out of the
    cage is `1:23:45`, 4321 s in session is `1:12:01`, and the last reward was
    charged at `1_700_000_000.0`."""
    base = Telemetry(
        schema=SCHEMA,
        session_id="2027-01-14_01",
        subject="A",
        trial_index=40,
        block="session",
        stopped_because="",
        stop_kind=None,
        phase="running",
        fluid_session_ml=1.25,
        fluid_today_ml=61.25,
        shortfall_ml=188.75,
        out_of_cage_seconds=5025.0,
        chair_seconds=4000.0,
        deployment="rig_fixed",
        duration_warning=None,
        outcomes={"correct": 30, "no_fixation": 8, "fixation_break": 2},
        hangs=0,
        owed={"ecc 10": 18},
        staged=(),
        refusals=(),
        refusals_dropped=0,
        in_session_seconds=4321.0,
        task="tasks/fixation_detection.py",
        allocation="tasks/allocation.py",
        bounds_config="subjects/A/bounds.py",
        params=(
            ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
            ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
        ),
        floor_ml=250.0,
        out_of_cage_limit_s=43_200.0,
        last_reward_at=1_700_000_000.0,
        recent_outcomes=("correct", "no_fixation", "correct"),
    )
    return replace(base, **overrides) if overrides else base
```

Create `tests/test_health.py`:

```python
"""`GET /health`'s body (P4d-2b spec §3): the verdict table, the readings, and the
contract against `wl-preproc`'s own `HealthResponse`.

**The contract tests are not allowed to skip in CI.** A missing `wl-preproc`
checkout skips them locally and fails them under `WLX_REQUIRE_PREPROC=1`, the same
guard `test_gaze.py` and `test_calibration.py` use: a `/health` wl-works might refuse
is not a `/health`.
"""

from __future__ import annotations

import json
import os

import pytest

from _frames import frame
from wl_expcontroller.health import (
    HEALTH_SCHEMA,
    ago,
    expects_frames,
    families,
    family_key,
    plain_text,
    readings,
    response,
    verdict,
)

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts.protocol import SCHEMA_VERSION, HealthResponse
    from wl_preproc.contracts.protocol import plain_text as their_plain_text
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). /health "
            f"is only useful if wl-works accepts it, and wl-preproc's HealthResponse is "
            f"the model it is checked against"
        ) from exc
    HealthResponse = None

_contract = pytest.mark.skipif(
    HealthResponse is None, reason="wl-preproc checkout not beside this repo"
)

WARNING = (
    "out_of_cage: subject 'A' has 900 s left of its 43200 s out of the cage; finish "
    "the block and start bringing the animal back"
)
LIMIT = (
    "out_of_cage: subject 'A' has been out of its cage 43201 s against a ceiling of "
    "43200"
)

#: `(frame, seconds since it arrived)` for every row of spec §3's verdict table, and
#: the absences and markup a reading must survive.
CASES = {
    "no session": (None, None),
    "running": (frame(), 1.0),
    "warning": (frame(duration_warning=WARNING), 1.0),
    "stale": (frame(), 45.0),
    "ended by the limit": (frame(stop_kind="limit", stopped_because=LIMIT), 1.0),
    "completed": (
        frame(stop_kind="completed", stopped_because="every block is finished"),
        45.0,
    ),
    "awaiting return": (
        frame(
            stop_kind="completed",
            stopped_because="every block is finished",
            phase="awaiting_return",
        ),
        1.0,
    ),
    "returned after the limit": (
        frame(stop_kind="limit", stopped_because=LIMIT, phase="closed"),
        1.0,
    ),
    "fault": (
        frame(
            stop_kind="fault",
            stopped_because="fault, session aborted: RuntimeError: solenoid did not answer",
        ),
        1.0,
    ),
    "cage-side": (
        frame(
            deployment="cage_side",
            out_of_cage_seconds=None,
            out_of_cage_limit_s=None,
            chair_seconds=None,
        ),
        1.0,
    ),
    "markup": (
        frame(
            session_id="<b>&",
            subject="A<B>",
            task="t&t.py",
            stop_kind="operator",
            stopped_because="stopped by <script>",
        ),
        1.0,
    ),
}

EXPECTED = {
    "no session": "ok",
    "running": "ok",
    "warning": "degraded",
    "stale": "degraded",
    "ended by the limit": "degraded",
    "completed": "ok",
    "awaiting return": "ok",
    "returned after the limit": "ok",
    "fault": "down",
    "cage-side": "ok",
    "markup": "ok",
}


def _readings(case: str) -> dict:
    found, age = CASES[case]
    return {
        r["key"]: r for r in readings(found, frame_age_s=age, stale_after_s=30.0)
    }


# --- the verdict: spec §3's table -------------------------------------------


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_verdict_follows_the_specs_table(case):
    found, age = CASES[case]

    assert verdict(found, frame_age_s=age, stale_after_s=30.0) == EXPECTED[case]


def test_a_rig_session_awaiting_its_return_that_goes_quiet_is_degraded():
    """Its out-of-cage clock is published once a second until the return (P4d-2a);
    silence then means nobody can see an animal that is still out."""
    awaiting, _ = CASES["awaiting return"]

    assert verdict(awaiting, frame_age_s=45.0, stale_after_s=30.0) == "degraded"


def test_an_ended_sessions_last_frame_is_its_last_and_never_stale():
    completed, _ = CASES["completed"]

    assert not expects_frames(completed)
    assert expects_frames(frame())
    assert not expects_frames(None)


def test_a_fault_is_down_even_after_the_return_and_beside_a_warning():
    faulted = frame(
        stop_kind="fault",
        stopped_because="fault after the loop",
        phase="closed",
        duration_warning=WARNING,
    )

    assert verdict(faulted, frame_age_s=1.0, stale_after_s=30.0) == "down"


def test_unknown_is_never_emitted():
    """`unknown` is wl-works' word for a host that went silent; a host answering the
    request cannot be silent (wl-preproc `docs/ops/lab-host-protocol.md`)."""
    for found, age in CASES.values():
        for stale_after in (0.5, 30.0):
            assert verdict(found, frame_age_s=age, stale_after_s=stale_after) in {
                "ok",
                "degraded",
                "down",
            }


# --- the readings ------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(CASES))
def test_exactly_one_reading_is_featured(case):
    """wl-works' Plan 10 §4: of several featured readings, the first wins -- so this
    host features one, the most urgent (PI, 2026-09-26, spec §3)."""
    assert sum(r["featured"] for r in _readings(case).values()) == 1


@pytest.mark.parametrize(
    ("case", "key"),
    [
        ("no session", "state"),
        ("running", "out_of_cage"),
        ("warning", "duration_warning"),
        ("stale", "last_frame"),
        ("ended by the limit", "state"),
        ("fault", "state"),
        ("cage-side", "state"),
    ],
)
def test_the_featured_reading_is_the_one_that_drove_the_verdict(case, key):
    featured = [k for k, r in _readings(case).items() if r["featured"]]

    assert featured == [key]


def test_the_readings_come_in_the_specs_order():
    keys = [
        r["key"]
        for r in readings(
            frame(duration_warning=WARNING, outcomes={"correct": 30, "no_fixation": 8}),
            frame_age_s=2.0,
            stale_after_s=30.0,
        )
    ]

    assert keys == [
        "session",
        "state",
        "out_of_cage",
        "duration_warning",
        "fluid_session",
        "supplement",
        "trials",
        "outcomes_target",
        "outcomes_no_engagement",
        "hangs",
        "last_frame",
    ]


def test_the_readings_say_what_a_person_needs_to_know():
    values = {
        r["key"]: r["value"]
        for r in readings(frame(), frame_age_s=3.0, stale_after_s=30.0)
    }

    assert values["session"] == "2027-01-14_01 · A · tasks/fixation_detection.py"
    assert values["state"] == "running · trial 40 · block session"
    assert values["out_of_cage"] == "1:23:45 of 12:00:00"
    assert values["fluid_session"] == "1.25 mL"
    assert values["supplement"] == "188.75 mL"
    assert values["trials"] == "40"
    assert values["outcomes_target"] == "correct 30"
    assert values["outcomes_breaks"] == "fixation_break 2"
    assert values["hangs"] == "0"
    assert values["last_frame"] == "3 s ago"


def test_an_ended_session_gives_its_reason_and_where_the_animal_is():
    def state(**overrides):
        found = frame(stop_kind="completed", stopped_because="every block is finished", **overrides)
        return {
            r["key"]: r["value"]
            for r in readings(found, frame_age_s=1.0, stale_after_s=30.0)
        }["state"]

    assert state() == "ended (completed): every block is finished"
    assert state(phase="awaiting_return") == (
        "ended (completed): every block is finished · awaiting the return to the cage"
    )
    assert state(phase="closed") == (
        "ended (completed): every block is finished · returned to the cage"
    )


def test_absences_are_sentences_never_zeros():
    found = frame(
        deployment="cage_side",
        out_of_cage_seconds=None,
        out_of_cage_limit_s=None,
        shortfall_ml=None,
    )
    values = {
        r["key"]: r["value"]
        for r in readings(found, frame_age_s=None, stale_after_s=30.0)
    }

    assert values["out_of_cage"] == "cage-side, no limit"
    assert values["supplement"] == "unknown: the day's prior total was not supplied"
    assert values["last_frame"] == "none received"


def test_with_no_session_it_says_so():
    values = {
        r["key"]: r["value"] for r in readings(None, frame_age_s=None, stale_after_s=30.0)
    }

    assert values == {
        "session": "none attached",
        "state": "waiting for the session's telemetry",
        "last_frame": "none received",
    }


def test_markup_in_a_value_is_spelled_out_as_wl_preproc_does():
    """Review Focus 2. A session id is text an operator chose, and wl-preproc's
    `Reading` refuses markup in a value outright -- so it is spelled out, never
    dropped and never sent."""
    values = {key: r["value"] for key, r in _readings("markup").items()}

    assert values["session"] == "(lt)b(gt)(amp) · A(lt)B(gt) · t(amp)t.py"
    assert values["state"] == "ended (operator): stopped by (lt)script(gt)"
    assert not any(c in "".join(values.values()) for c in "<>&")


def test_counts_are_grouped_by_family_and_never_summed():
    """No rollup (PI, 2026-09-26), and Review Focus 3: an outcome this build does not
    know is shown under Other, never dropped."""
    grouped = families(
        {"correct": 30, "early_response": 2, "no_fixation": 8, "from_a_newer_taskd": 1}
    )

    assert grouped == [
        ("target", "Target", [("correct", 30), ("early_response", 2)]),
        ("no_engagement", "No engagement", [("no_fixation", 8)]),
        ("other", "Other", [("from_a_newer_taskd", 1)]),
    ]


def test_the_strips_rollup_never_reaches_health():
    """The PI's one rollup -- `correct` plus `correct_reject` -- is the strip's alone
    (2026-09-26, spec §3). `/health` counts every outcome as it occurred."""
    values = {
        r["key"]: r["value"]
        for r in readings(
            frame(
                trial_index=10,
                outcomes={"correct": 3, "correct_reject": 2, "no_fixation": 5},
            ),
            frame_age_s=1.0,
            stale_after_s=30.0,
        )
    }

    assert values["trials"] == "10"
    assert values["outcomes_target"] == "correct 3"
    assert values["outcomes_withhold"] == "correct_reject 2"
    assert not any("correct 5" in value for value in values.values())


def test_a_wire_string_names_its_family():
    assert family_key("fixation_break") == "breaks"
    assert family_key("tracker_lost") == "rig"
    assert family_key("no_response") == "no_engagement"
    assert family_key("hang") == "hang"
    assert family_key("from_a_newer_taskd") == "other"


def test_ages_read_as_a_person_reads_them():
    assert ago(42.9) == "42 s"
    assert ago(600.0) == "10 min"
    assert ago(7200.0) == "2:00:00"
    assert ago(-3.0) == "0 s"


def test_plain_text_spells_out_the_three_characters():
    assert plain_text("A&B<C>") == "A(amp)B(lt)C(gt)"


@pytest.mark.parametrize("case", sorted(CASES))
def test_no_action_is_ever_offered(case):
    """ADR-0008: no welfare action goes through wl-works."""
    found, age = CASES[case]

    assert response(found, frame_age_s=age, stale_after_s=30.0)["actions"] == []


# --- the contract: wl-preproc's own model -------------------------------------


@_contract
@pytest.mark.parametrize("case", sorted(CASES))
def test_the_body_is_wl_preprocs_health_response(case):
    found, age = CASES[case]
    body = json.dumps(response(found, frame_age_s=age, stale_after_s=30.0))

    parsed = HealthResponse.model_validate_json(body)

    assert parsed.verdict == EXPECTED[case]
    assert parsed.actions == []


@_contract
def test_our_plain_text_is_theirs():
    for text in ("A&B", "<script>alert(1)</script>", "a>b<c&d", "plain", "", "(lt)"):
        assert plain_text(text) == their_plain_text(text), text


@_contract
def test_our_schema_version_is_theirs():
    assert HEALTH_SCHEMA == SCHEMA_VERSION
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_health.py`
Expected: collection error — `ModuleNotFoundError: No module named 'wl_expcontroller.health'`.

- [ ] **Step 3: Implement**

Create `wl_expcontroller/health.py`:

```python
"""What `GET /health` tells wl-works about this box (P4d-2b spec §3).

The body is `wl_preproc.contracts.protocol.HealthResponse`, schema version 1 --
`verdict`, `readings`, `actions` -- built here as plain data and contract-tested
against their model with `WLX_REQUIRE_PREPROC=1` (`tests/test_health.py`). **Pure**: a
frame and two numbers in, a dict out. `wlx serve` supplies how old the frame is.

**The rules are wl-preproc's, read from their source on 2026-09-26**
(`wl_preproc/contracts/protocol.py`, `docs/ops/lab-host-protocol.md`):

- A reading is plain text. `<`, `>` and `&` in a value are spelled `(lt)`, `(gt)` and
  `(amp)`, as their `plain_text` does; every label here is a constant with none.
- `unknown` is never emitted. It is wl-works' word for a host that went silent, and a
  host answering the request cannot be silent.
- `actions` is always empty: no welfare action goes through wl-works (ADR-0008).
- **Exactly one reading is featured, the most urgent** (PI, 2026-09-26, spec §3).
  wl-works' Plan 10 §4 says of more than one "the first wins", and wl-preproc emits
  exactly one for that reason. `_featured` holds the ruled order.

**The behavioral counts are grouped here and nowhere else** (`families`), so the
browser console's Working? pane and this body show them identically (spec §3): total
trials, then every outcome that occurred with its count, by `task.Family`, and no
rollup.
"""

from __future__ import annotations

from wl_expcontroller.cli import _clock
from wl_expcontroller.link import Telemetry
from wl_expcontroller.task import Family, Outcome

#: `wl_preproc.contracts.protocol.SCHEMA_VERSION`, read from their source 2026-09-26.
#: `tests/test_health.py` compares the two, so a bump on their side fails here first.
HEALTH_SCHEMA = 1

#: wl-preproc's substitutes, one per character and never one shared: `A&B` and `A<B`
#: must not render alike (their `_MARKUP_SUBSTITUTES`).
_MARKUP = (("<", "(lt)"), (">", "(gt)"), ("&", "(amp)"))


def plain_text(text: str) -> str:
    """`text` with `<`, `>` and `&` spelled out, as wl-preproc's `plain_text` does.

    Their `Reading` refuses markup in a value outright. A session id or a stop reason
    is producer-supplied text worth reporting, so it is spelled out rather than
    dropped. A second copy of their function, pinned to theirs by a contract test:
    this package cannot import wl-preproc at run time (`tests/conftest.py`).
    """
    for char, substitute in _MARKUP:
        text = text.replace(char, substitute)
    return text


def ago(seconds: float) -> str:
    """An age as a person reads it: seconds under a minute and a half, minutes under
    an hour and a half, then a clock. Formatting only; a negative age is `0 s`."""
    whole = max(0, int(seconds))
    if whole < 90:
        return f"{whole} s"
    if whole < 5400:
        return f"{whole // 60} min"
    return _clock(whole)


def family_key(wire: str) -> str:
    """The family an outcome's wire string belongs to, as a short key -- `hang` for a
    trial with no outcome, and `other` for a string this build's `Outcome` does not
    know, which a newer `taskd` can send. Never raises: an unknown outcome is shown,
    never dropped."""
    if wire == "hang":
        return "hang"
    try:
        return Outcome(wire).family.name.lower()
    except ValueError:
        return "other"


def families(outcomes: dict) -> list[tuple[str, str, list[tuple[str, object]]]]:
    """Every outcome that occurred, grouped by `Family`, with its count and **no
    rollup** (PI, 2026-09-26): `(key, label, [(outcome, count), ...])` in `Family`
    order, each family's outcomes in `Outcome` order, then any this build does not
    know, sorted, under `other`."""
    grouped = []
    for family in Family:
        rows = [
            (outcome.value, outcomes[outcome.value])
            for outcome in Outcome
            if outcome.family is family and outcome.value in outcomes
        ]
        if rows:
            grouped.append((family.name.lower(), family.value.capitalize(), rows))
    known = {outcome.value for outcome in Outcome}
    other = [
        (name, outcomes[name]) for name in sorted(outcomes, key=str) if name not in known
    ]
    if other:
        grouped.append(("other", "Other", other))
    return grouped


def expects_frames(frame: Telemetry | None) -> bool:
    """Whether more frames are due: the loop is running, or a rig session is still
    publishing its out-of-cage clock until the return (P4d-2a). Only then is silence
    a stale stream -- an ended session's last frame is its last. The page's stale
    timer runs on the same answer."""
    return frame is not None and (
        frame.stop_kind is None or frame.phase == "awaiting_return"
    )


def _stale(frame: Telemetry | None, frame_age_s: float | None, stale_after_s: float) -> bool:
    return (
        expects_frames(frame) and frame_age_s is not None and frame_age_s >= stale_after_s
    )


def verdict(
    frame: Telemetry | None, *, frame_age_s: float | None, stale_after_s: float
) -> str:
    """Spec §3's table, first match wins:

    - no session attached yet: `ok`
    - ended by a fault: `down`, whatever else holds
    - returned to the cage (`phase == "closed"`): `ok`, however it ended
    - the duration warning active, or no frame for `stale_after_s` while more were
      due: `degraded`
    - ended by the out-of-cage limit and not yet back: `degraded`
    - otherwise -- running normally, or ended any other way: `ok`
    """
    if frame is None:
        return "ok"
    if frame.stop_kind == "fault":
        return "down"
    if frame.phase == "closed":
        return "ok"
    if frame.duration_warning or _stale(frame, frame_age_s, stale_after_s):
        return "degraded"
    if frame.stop_kind == "limit":
        return "degraded"
    return "ok"


def _state_text(frame: Telemetry) -> str:
    if frame.stop_kind is None:
        return f"running · trial {frame.trial_index} · block {frame.block}"
    text = f"ended ({frame.stop_kind}): {frame.stopped_because}"
    if frame.phase == "awaiting_return":
        return f"{text} · awaiting the return to the cage"
    if frame.phase == "closed":
        return f"{text} · returned to the cage"
    return text


def _cage_text(frame: Telemetry) -> str:
    if frame.out_of_cage_seconds is None:
        return "cage-side, no limit"
    if frame.out_of_cage_limit_s is None:
        return _clock(frame.out_of_cage_seconds)
    return f"{_clock(frame.out_of_cage_seconds)} of {_clock(frame.out_of_cage_limit_s)}"


def _supplement_text(frame: Telemetry) -> str:
    if frame.shortfall_ml is None:
        return "unknown: the day's prior total was not supplied"
    return f"{frame.shortfall_ml:.2f} mL"


def _age_text(frame_age_s: float | None) -> str:
    return "none received" if frame_age_s is None else f"{ago(frame_age_s)} ago"


def _featured(frame: Telemetry | None, verdict_: str, stale: bool) -> str:
    """The one reading wl-works' home page shows: the most urgent (PI, 2026-09-26,
    spec §3) -- the warning, else the state of a session that faulted or ended on the
    limit with the animal not back, else a stale stream's age, else the out-of-cage
    time a rig session is bounded by, else the state."""
    if frame is None:
        return "state"
    if frame.duration_warning:
        return "duration_warning"
    if verdict_ == "down" or (frame.stop_kind == "limit" and frame.phase != "closed"):
        return "state"
    if stale:
        return "last_frame"
    if frame.out_of_cage_seconds is not None:
        return "out_of_cage"
    return "state"


def readings(
    frame: Telemetry | None, *, frame_age_s: float | None, stale_after_s: float
) -> list[dict]:
    """The readings, in spec §3's order: session, state, time out of cage, the
    duration warning when active, fluid this session, supplement owed, the
    behavioral counts, and the last frame's age. Every value through `plain_text`."""
    if frame is None:
        rows = [
            ("session", "Session", "none attached"),
            ("state", "State", "waiting for the session's telemetry"),
            ("last_frame", "Last frame", _age_text(frame_age_s)),
        ]
    else:
        rows = [
            ("session", "Session", f"{frame.session_id} · {frame.subject} · {frame.task}"),
            ("state", "State", _state_text(frame)),
            ("out_of_cage", "Time out of cage", _cage_text(frame)),
        ]
        if frame.duration_warning:
            rows.append(("duration_warning", "Warning", frame.duration_warning))
        rows += [
            ("fluid_session", "Fluid this session", f"{frame.fluid_session_ml:.2f} mL"),
            ("supplement", "Supplement owed", _supplement_text(frame)),
            ("trials", "Trials", str(frame.trial_index)),
        ]
        for key, label, counted in families(frame.outcomes):
            rows.append(
                (
                    f"outcomes_{key}",
                    label,
                    " · ".join(f"{name} {count}" for name, count in counted),
                )
            )
        rows += [
            ("hangs", "Hangs", str(frame.hangs)),
            ("last_frame", "Last frame", _age_text(frame_age_s)),
        ]
    featured = _featured(
        frame,
        verdict(frame, frame_age_s=frame_age_s, stale_after_s=stale_after_s),
        _stale(frame, frame_age_s, stale_after_s),
    )
    return [
        {"key": key, "label": label, "value": plain_text(str(value)), "featured": key == featured}
        for key, label, value in rows
    ]


def response(
    frame: Telemetry | None, *, frame_age_s: float | None, stale_after_s: float
) -> dict:
    """The whole `/health` body: `HealthResponse`'s three fields, `actions` always
    empty."""
    return {
        "verdict": verdict(frame, frame_age_s=frame_age_s, stale_after_s=stale_after_s),
        "readings": readings(frame, frame_age_s=frame_age_s, stale_after_s=stale_after_s),
        "actions": [],
    }
```

In `tools/mutation_gate.py`, add `"health": "None",` to `RETURNS` (after `"link": "None",`).

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_health.py tests/test_mutation_gate.py`
Expected: all pass, the `_contract` tests included (none skipped: check the summary line says `0 skipped`, or run with `-rs` and see no skip reasons).
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/health.py tests/_frames.py tests/test_health.py tools/mutation_gate.py
git commit -m "Build /health's body: the verdict table, one featured reading, plain text"
```

Body: cites the PI's ruling on the featured reading (2026-09-26, spec §3): exactly one, the most urgent.

---
### Task 7: The panes — `web.fragments`

**Why:** spec §1 and §4.2. Every pane is rendered to HTML in Python so that "fluid session and supplement are never dropped", "not measured is never 0" and "every string is escaped" are pytest assertions (spec §4.4). This task renders the fragments; Task 8 puts them in a page.

**Two readings of the mockup, and how they are settled:**
- **The strip's correct is `correct` plus `correct_reject`** (PI, 2026-09-26, recorded in spec §3: "count both", since both are the right answer on their trial), over `trial_index` (total trials, hangs included). **It is the one rollup, and it is the strip's alone**: the Working? pane and `/health` count every outcome as it occurred.
- **Tick colors are by `Family`** (spec §4.2, "colored by family"), where the mockup colored `correct_reject` with `correct` and `false_alarm` with early and late responses. A hang and an outcome this build does not know get their own ticks and legend entries.

**Files:**
- Create: `wl_expcontroller/web.py` (this task: `View`, `FRAGMENT_IDS`, `LEGEND`, `fragments` and its helpers)
- Modify: `tests/_frames.py` (add `view`)
- Create: `tests/test_web.py`
- Modify: `tools/mutation_gate.py` (`"web": "None"` in `RETURNS`)

**Interfaces:**
- Consumes: Task 4's `Telemetry`, `ParamRow`, `RECENT_OUTCOMES`; Task 6's `health.families`, `family_key`, `ago`, `verdict`, `readings`; `cli._clock`; `task.Family`, `Outcome`.
- Produces:
  - `web.View(now: float, frame_age_s: float | None, stale_after_s: float, trials_per_min: float | None, on_box: bool, lan_viewers: int, rejected: str | None)` — frozen, slotted.
  - `web.FRAGMENT_IDS: tuple[str, ...]` = `("state", "head-id", "presence", "strip", "banners", "rt-trials", "rt-work", "rt-need", "rt-wrong", "rt-health", "rt-changes", "params", "setup", "end")`.
  - `web.LEGEND: tuple[tuple[str, str], ...]` — `(css key, label)` per tick kind.
  - `web.fragments(frame: Telemetry | None, view: View) -> dict[str, str]` — one entry per `FRAGMENT_IDS`, each the inner HTML of the element with that id.
  - The header's trial value carries `data-trial="N"`; the state pill carries `data-state="none" | "running" | "ended"`. Tasks 10 and 11 read both.
  - `tests/_frames.view(**overrides) -> View`.

- [ ] **Step 1: Write the failing tests**

In `tests/_frames.py`, add `from wl_expcontroller.web import View` to the imports, and append:

```python
def view(**overrides) -> View:
    """A box viewer, alone, forty-two seconds after the last reward, with a derived
    rate of twelve trials a minute."""
    base = View(
        now=1_700_000_042.0,
        frame_age_s=0.5,
        stale_after_s=30.0,
        trials_per_min=12.0,
        on_box=True,
        lan_viewers=0,
        rejected=None,
    )
    return replace(base, **overrides) if overrides else base
```

Create `tests/test_web.py`:

```python
"""The browser console's panes (P4d-2b spec §4.2, §4.4): pure, and tested the way
`cli.render` is.

The assertions that matter most are the ones a simplified pane would break: fluid
session and the supplement never dropped (the zero-reward ruling rests on their being
visible, S9a §9), nothing unmeasured ever shown as 0, and no telemetry string ever
reaching the page as markup.
"""

from __future__ import annotations

import html
import re

import pytest

from _frames import frame, view
from wl_expcontroller.link import ParamRow, Refused, Staged
from wl_expcontroller.web import FRAGMENT_IDS, LEGEND, fragments

LIMIT = "out_of_cage: subject 'A' has been out of its cage 43201 s against a ceiling of 43200"

STATES = {
    "running": {},
    "ended by the limit": {"stop_kind": "limit", "stopped_because": LIMIT},
    "awaiting return": {
        "stop_kind": "completed",
        "stopped_because": "every block is finished",
        "phase": "awaiting_return",
    },
    "returned": {
        "stop_kind": "operator",
        "stopped_because": "stopped by jake",
        "phase": "closed",
    },
    "fault": {
        "stop_kind": "fault",
        "stopped_because": "fault, session aborted: RuntimeError: solenoid did not answer",
    },
    "cage-side": {
        "deployment": "cage_side",
        "out_of_cage_seconds": None,
        "out_of_cage_limit_s": None,
        "chair_seconds": None,
    },
}


# --- never dropped -------------------------------------------------------------


@pytest.mark.parametrize("state", sorted(STATES))
def test_fluid_session_and_the_supplement_are_never_dropped(state):
    """The zero-reward ruling (PI, 2026-09-20) rests on both being visible, and the
    strip no longer carries them (spec §4.0) -- so Runtime and End of session both
    must, in every state, a zero volume included."""
    parts = fragments(
        frame(fluid_session_ml=0.0, shortfall_ml=3.21, **STATES[state]), view()
    )

    for pane in ("rt-work", "end"):
        assert "0.00 mL" in parts[pane], (state, pane)
        assert "3.21" in parts[pane], (state, pane)


def test_an_unknown_supplement_is_a_sentence_not_a_zero():
    parts = fragments(frame(shortfall_ml=None, fluid_today_ml=None), view())

    for pane in ("rt-work", "end"):
        assert "unknown: the day's prior total was not supplied" in parts[pane]


@pytest.mark.parametrize(
    "state", ["running", "ended by the limit", "awaiting return", "returned", "fault"]
)
def test_the_out_of_cage_time_is_never_dropped(state):
    parts = fragments(frame(**STATES[state]), view())

    assert "1:23:45" in parts["strip"]
    assert "1:23:45" in parts["end"]


def test_a_cage_side_session_says_it_has_no_out_of_cage_clock_rather_than_zero():
    parts = fragments(frame(**STATES["cage-side"]), view())

    assert "cage-side · no limit" in parts["strip"]
    assert "cage-side · no out-of-cage interval" in parts["end"]
    assert "0:00" not in parts["strip"] + parts["end"]


def test_the_duration_warning_is_never_dropped():
    warning = "out_of_cage: subject 'A' has 900 s left of its 43200 s out of the cage"

    parts = fragments(frame(duration_warning=warning), view())

    assert html.escape(warning, quote=True) in parts["banners"]


def test_the_refusals_that_fell_off_the_cap_are_counted_before_the_rows():
    parts = fragments(
        frame(refusals=(Refused("fx_hold", "sam", "not declared"),), refusals_dropped=417),
        view(),
    )

    changes = parts["rt-changes"]
    assert "417 earlier refusal(s) not shown" in changes
    assert changes.index("417 earlier") < changes.index("fx_hold")


# --- never a zero for what nothing measured -----------------------------------


def test_nothing_unmeasured_is_rendered_as_zero():
    parts = fragments(
        frame(fluid_today_ml=None, last_reward_at=None), view(trials_per_min=None)
    )

    for name in ("dropped frames", "tracker staleness", "RHX margin"):
        assert re.search(
            rf'<span>{name}</span><span class="nm">not measured</span>', parts["rt-wrong"]
        ), name
    strip = parts["strip"]
    assert "unknown" in strip and "none yet" in strip
    assert "trials/min not yet derived" in strip
    assert "0.0 trials/min" not in strip
    assert "0 s" not in strip


def test_the_time_since_the_last_reward_is_read_against_the_servers_clock():
    parts = fragments(
        frame(last_reward_at=1_700_000_000.0), view(now=1_700_000_042.0)
    )

    assert "42 s" in parts["strip"]


# --- counts, ticks, and the strip's arithmetic ----------------------------------


def test_the_strips_correct_counts_correct_and_correct_reject():
    """The one rollup (PI, 2026-09-26, spec §3): on the strip, `correct` plus
    `correct_reject` -- 3 and 2 of 10 trials read 5 / 10, 50%."""
    parts = fragments(
        frame(
            trial_index=10,
            outcomes={"correct": 3, "correct_reject": 2, "no_fixation": 5},
        ),
        view(trials_per_min=12.0),
    )

    strip = parts["strip"]
    assert '5<span class="u">/ 10</span>' in strip
    assert "50% correct" in strip
    assert "12.0 trials/min, derived by wlx serve" in strip


def test_the_working_pane_keeps_every_count_unrolled():
    """The strip's rollup is the strip's alone: this pane counts each outcome as it
    occurred, as `/health` does."""
    work = fragments(
        frame(
            trial_index=10,
            outcomes={"correct": 3, "correct_reject": 2, "no_fixation": 5},
        ),
        view(),
    )["rt-work"]

    assert '<span>correct</span><span class="num">3</span>' in work
    assert '<span>correct_reject</span><span class="num">2</span>' in work
    assert '<span>correct</span><span class="num">5</span>' not in work


def test_the_fluid_bar_is_today_over_the_floor():
    strip = fragments(frame(fluid_today_ml=61.25, floor_ml=250.0), view())["strip"]

    assert 'style="width:24.5%"' in strip
    assert "61.25" in strip and "/ 250.00 mL" in strip


def test_counts_are_grouped_by_family_with_no_rollup():
    work = fragments(
        frame(outcomes={"correct": 3, "early_response": 1, "no_fixation": 2}), view()
    )["rt-work"]

    assert "<h3>Target</h3>" in work and "<h3>No engagement</h3>" in work
    assert '<span>correct</span><span class="num">3</span>' in work
    assert '<span>early_response</span><span class="num">1</span>' in work
    assert '<span class="num">4</span>' not in work, "a family total is back"


def test_an_outcome_this_build_does_not_know_is_shown_not_dropped():
    """Review Focus 3: a newer `taskd` may send an outcome this `Outcome` lacks."""
    parts = fragments(
        frame(
            outcomes={"from_a_newer_taskd": 5},
            recent_outcomes=("from_a_newer_taskd", "hang"),
        ),
        view(),
    )

    assert "<h3>Other</h3>" in parts["rt-work"]
    assert "from_a_newer_taskd" in parts["rt-work"]
    assert 'class="tk f-other" title="from_a_newer_taskd"' in parts["rt-trials"]
    assert 'class="tk f-hang" title="hang"' in parts["rt-trials"]


def test_the_ticks_are_sixty_oldest_first_colored_by_family_with_a_legend():
    ticks = fragments(
        frame(recent_outcomes=("correct", "fixation_break", "wrong_target")), view()
    )["rt-trials"]

    assert ticks.count('<span class="tk') == 60
    assert 'class="tk f-target" title="correct"' in ticks
    assert 'class="tk f-breaks" title="fixation_break"' in ticks
    assert 'class="tk f-distractor" title="wrong_target"' in ticks
    assert ticks.index('title="correct"') < ticks.index('title="wrong_target"')
    for key, label in LEGEND:
        assert f'<i class="tk f-{key}"></i>{label}' in ticks


# --- the header, the banners, and no session ------------------------------------


@pytest.mark.parametrize(
    ("overrides", "label", "state"),
    [
        ({}, "running", "running"),
        ({"stop_kind": "limit", "stopped_because": LIMIT}, "ended · limit", "ended"),
        (STATES["awaiting return"], "ended · completed · awaiting return", "ended"),
        (STATES["returned"], "ended · operator · returned", "ended"),
    ],
)
def test_the_state_pill_reads_phase_and_stop_kind(overrides, label, state):
    pill = fragments(frame(**overrides), view())["state"]

    assert f'data-state="{state}">{label}</span>' in pill


def test_with_no_frame_every_pane_says_so():
    parts = fragments(None, view(frame_age_s=None))

    assert tuple(parts) == FRAGMENT_IDS
    assert 'data-state="none"' in parts["state"]
    assert "no telemetry yet" in parts["banners"]
    for pane in ("head-id", "strip", "rt-trials", "rt-work", "rt-need", "params", "setup", "end"):
        assert "no session" in parts[pane], pane


def test_the_header_carries_the_session_and_the_trial():
    head = fragments(frame(trial_index=41), view())["head-id"]

    for text in ("2027-01-14_01", ">A<", "rig_fixed", ">session<", 'data-trial="41">41<', "1:12:01"):
        assert text in head, text


def test_presence_says_this_box_or_lan_viewer_with_the_count():
    assert (
        fragments(frame(), view(on_box=True, lan_viewers=2))["presence"]
        == "<b>this box</b> · 2 LAN viewers"
    )
    assert (
        fragments(frame(), view(on_box=False, lan_viewers=1))["presence"]
        == "<b>LAN viewer</b> · 1 LAN viewer"
    )


def test_a_refused_frame_is_said_above_everything_else():
    """Review Focus 1: a frame this console could not read is said, first."""
    banners = fragments(
        frame(), view(rejected="a telemetry frame carried schema 6")
    )["banners"]

    assert banners.startswith('<div class="banner crit"><span class="tag">Refused</span>')
    assert "schema 6" in banners


def test_the_stop_reason_is_a_banner_and_ends_the_summary():
    parts = fragments(frame(**STATES["returned"]), view())

    assert "stopped by jake" in parts["banners"]
    assert "stopped by jake" in parts["end"]


# --- the read-only panes ----------------------------------------------------------


def test_parameters_show_value_range_ceiling_and_what_is_staged():
    params = fragments(
        frame(
            params=(
                ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
                ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
                ParamRow("target_looks", "", None, None, None, False),
                ParamRow("fix_window", "deg", None, 5.0, 2.0, False),
                ParamRow("shape", "", None, None, "penguin", False),
            ),
            staged=(Staged("fix_hold", 0.3, 0.4, "jake", False),),
        ),
        view(),
    )["params"]

    assert params.count('<div class="param') == 5
    assert '<div class="param staged">' in params
    assert "staged → 0.40 by jake" in params
    assert '<span class="ceil">ceiling</span>' in params
    assert "welfare ceiling 0.40 mL" in params
    assert "0.10 to 1.00 s" in params
    assert "open to 5.00 deg" in params
    assert "no declared range" in params
    assert "unset" in params
    assert "penguin" in params


def test_setup_names_the_configuration_and_what_has_no_source():
    setup = fragments(frame(allocation="", bounds_config=""), view())["setup"]

    assert "tasks/fixation_detection.py" in setup
    assert "provisional: none given" in setup
    assert '<dt>bounds config</dt><dd><span class="nm">not given</span></dd>' in setup
    assert setup.count("no source yet") == 2
    assert "250.00 mL" in setup and "12:00:00" in setup


def test_still_needed_lists_each_condition_and_its_count():
    need = fragments(frame(owed={"ecc 10": 18, "catch": 2}), view())["rt-need"]

    assert '<span class="mono">ecc 10</span><span class="num">18</span>' in need
    assert '<span class="mono">catch</span><span class="num">2</span>' in need


def test_the_health_pane_shows_what_wl_works_would_be_sent():
    pane = fragments(frame(duration_warning="warning text"), view())["rt-health"]

    assert '<span class="pill warn">degraded</span>' in pane
    assert pane.count("◆") == 1
    assert "warning text" in pane


# --- escaping ------------------------------------------------------------------

EVIL = "<script>alert(1)</script>\"'&"


def test_every_telemetry_string_is_escaped():
    """Review Focus 2: every string a frame carries -- and the refusal `wlx serve`
    adds -- is text on the page, in an element or an attribute, and never markup."""
    evil = frame(
        session_id=EVIL,
        subject=EVIL,
        block=EVIL,
        deployment=EVIL,
        stop_kind=EVIL,
        phase=EVIL,
        stopped_because=EVIL,
        duration_warning=EVIL,
        task=EVIL,
        allocation=EVIL,
        bounds_config=EVIL,
        outcomes={EVIL: 1, "correct": 2},
        owed={EVIL: 3},
        recent_outcomes=(EVIL, "correct"),
        staged=(Staged(EVIL, 0.1, 0.2, EVIL, False),),
        refusals=(Refused(EVIL, EVIL, EVIL),),
        params=(ParamRow(EVIL, EVIL, None, None, EVIL, False),),
    )

    text = "".join(fragments(evil, view(rejected=EVIL)).values())

    assert "<script" not in text
    assert EVIL not in text
    assert html.escape(EVIL, quote=True) in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_web.py`
Expected: collection error — `ModuleNotFoundError: No module named 'wl_expcontroller.web'`.

- [ ] **Step 3: Implement**

Create `wl_expcontroller/web.py`:

```python
"""The browser console's panes and page: a `Telemetry` frame in, HTML out.

P4d-2b slice b1 (`docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md`
§1, §4.2). **Pure** -- no socket, no clock, no thread. `wlx serve` reads the clock and
the stream and hands them in as a `View`, so every pane is tested the way `cli.render`
is: "fluid session and the supplement are never dropped" is an assertion on this
module's output (spec §4.4), not a hope about a browser.

**Every telemetry string reaches the page through `_e`** (`html.escape`, quotes
included), in elements and attributes alike. A task path, a condition, a refusal's
reason and an actor's typed name are text a person or a peer chose.

**Every number is read from the frame**, as `cli.render`'s are, with the arithmetic a
display needs and no more: the strip's correct count, which adds `correct_reject` to
`correct` -- the one rollup, ruled for the strip alone (PI, 2026-09-26, spec §3) -- and
its percentage, two bar widths, and the time since the last reward -- `View.now` less
`Telemetry.last_reward_at`. Trials per minute is derived by `wlx serve`, never here,
and is labeled as derived.

**Unknown is a word, never 0**: a day nobody measured, a reward not given yet, a rate
not derived yet, a configuration nobody named, and the three *Wrong?* measurements
nothing takes yet.

**The strip carries four cells** (PI, 2026-09-26, spec §4.0): fluid today against its
floor, time out of the cage against its limit, correct over trials, and the time since
the last reward. Fluid session and the supplement moved to Runtime and End of session,
where **both are on the page in every state**: the zero-reward ruling (S9a §9) rests on
their being visible.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from wl_expcontroller import health as _health
from wl_expcontroller.cli import _clock
from wl_expcontroller.link import RECENT_OUTCOMES, Telemetry
from wl_expcontroller.task import Family, Outcome


@dataclass(frozen=True, slots=True)
class View:
    """What `wlx serve` adds to a frame: facts about the stream and the viewer, never
    about the session."""

    #: The wall instant of this render, POSIX seconds, from `wlx serve`'s host clock.
    #: Read only to say how long ago the last reward was. The session's wall is
    #: anchored when the session is created (P4d-2a, Ruling 8), so the two differ by
    #: however far the host clock has been adjusted since; the cell is an age for a
    #: person to read, and bounds nothing.
    now: float
    #: Seconds since `wlx serve` received the latest frame; `None` before any.
    frame_age_s: float | None
    #: `--stale-after`: a display choice (spec §3), not a measurement.
    stale_after_s: float
    #: Derived by `wlx serve` from `trial_index` over the frames of the last five
    #: minutes (spec §4.1); `None` until two frames a moment apart exist.
    trials_per_min: float | None
    #: Whether the browser this render is for is on the box (a loopback peer).
    on_box: bool
    #: How many event streams are open from other hosts.
    lan_viewers: int
    #: Why the last frame `wlx serve` received could not be used, or `None`.
    rejected: str | None


#: Every fragment `fragments` renders, in page order. Each is the inner HTML of the
#: element with that id; the page's script swaps them by the same id.
FRAGMENT_IDS = (
    "state",
    "head-id",
    "presence",
    "strip",
    "banners",
    "rt-trials",
    "rt-work",
    "rt-need",
    "rt-wrong",
    "rt-health",
    "rt-changes",
    "params",
    "setup",
    "end",
)

#: The ticks' legend: one entry per `Family`, then the two strings that are none.
LEGEND = tuple((family.name.lower(), family.value) for family in Family) + (
    ("hang", "hang"),
    ("other", "unknown outcome"),
)

_NONE = '<span class="nm">no session</span>'
_UNKNOWN_DAY = "unknown: the day's prior total was not supplied"
#: Spec §3: "Drops, tracker staleness and RHX margin have no source and render not
#: measured, never 0."
_NOT_MEASURED = ("dropped frames", "tracker staleness", "RHX margin")
_VERDICT_TONE = {"ok": "ok", "degraded": "warn", "down": "crit"}


def _e(value: object) -> str:
    """The one way telemetry text reaches the page."""
    return html.escape(str(value), quote=True)


def _num(value: object) -> str:
    """A parameter's value: `unset` for `None`, two decimals for a number, and the
    text of a categorical choice. Formatting, not derivation."""
    if value is None:
        return "unset"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value)


def _edge(value: object) -> str:
    """One end of a declared range: `open` where the task declared none."""
    return "open" if value is None else _num(value)


def _pct(part: float, whole: float) -> float:
    """A bar's width, held to 0-100. Display arithmetic on two published numbers."""
    if whole <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * part / whole))


# --- the header -------------------------------------------------------------------


def _state(frame: Telemetry | None) -> str:
    """The header's pill, from `phase` and `stop_kind` (spec §4.2)."""
    if frame is None:
        return '<span class="pill neutral" data-state="none">no session</span>'
    if frame.stop_kind is None:
        return '<span class="pill ok" data-state="running">running</span>'
    tone = "crit" if frame.stop_kind in ("fault", "limit") else "neutral"
    label = f"ended · {frame.stop_kind}"
    if frame.phase == "awaiting_return":
        label += " · awaiting return"
    elif frame.phase == "closed":
        label += " · returned"
    return f'<span class="pill {tone}" data-state="ended">{_e(label)}</span>'


def _head(frame: Telemetry | None) -> str:
    """Session, subject, deployment, block, trial, and the in-session clock."""
    if frame is None:
        return _NONE
    in_session = (
        "—" if frame.in_session_seconds is None else _clock(frame.in_session_seconds)
    )
    cells = (
        ("Session", _e(frame.session_id), ""),
        ("Subject", _e(frame.subject), ""),
        ("Deployment", _e(frame.deployment), ""),
        ("Block", _e(frame.block), ""),
        ("Trial", _e(frame.trial_index), f' data-trial="{_e(frame.trial_index)}"'),
        ("In session", in_session, ""),
    )
    return "".join(
        f'<span><span class="k">{name}</span><span class="v"{attr}>{value}</span></span>'
        for name, value, attr in cells
    )


def _presence(view: View) -> str:
    """This box, or a LAN viewer, and how many LAN viewers there are (spec §4.2)."""
    count = view.lan_viewers
    lan = f"{count} LAN viewer{'' if count == 1 else 's'}"
    who = "this box" if view.on_box else "LAN viewer"
    return f"<b>{who}</b> · {lan}"


# --- the strip --------------------------------------------------------------------


def _cell(
    label: str, value: str, *, sub: str = "", bar: tuple[float, str] | None = None
) -> str:
    """One strip cell. `label` and `sub` are this module's own text; `value` is HTML
    built from escaped parts."""
    parts = [
        f'<div class="row"><span class="lab">{label}</span>'
        f'<span class="val">{value}</span></div>'
    ]
    if bar is not None:
        width, tone = bar
        parts.append(
            f'<div class="bar" aria-hidden="true">'
            f'<div class="fill {tone}" style="width:{width:.1f}%"></div></div>'
        )
    if sub:
        parts.append(f'<span class="sub">{sub}</span>')
    return "<div>" + "".join(parts) + "</div>"


def _fluid_today(frame: Telemetry) -> str:
    floor = f'<span class="u">/ {frame.floor_ml:.2f} mL</span>'
    if frame.fluid_today_ml is None:
        return _cell(
            "Fluid today / floor",
            f'<span class="nm">unknown</span>{floor}',
            sub="the day's prior total was not supplied",
        )
    tone = "ok" if frame.fluid_today_ml >= frame.floor_ml else ""
    return _cell(
        "Fluid today / floor",
        f"{frame.fluid_today_ml:.2f}{floor}",
        bar=(_pct(frame.fluid_today_ml, frame.floor_ml), tone),
    )


def _out_of_cage(frame: Telemetry) -> str:
    if frame.out_of_cage_seconds is None:
        return _cell("Out of cage", '<span class="nm">cage-side · no limit</span>')
    clock = _clock(frame.out_of_cage_seconds)
    limit = frame.out_of_cage_limit_s
    if limit is None:
        return _cell("Out of cage", clock)
    tone = "crit" if frame.stop_kind == "limit" else "warn" if frame.duration_warning else ""
    return _cell(
        f"Out of cage / {_clock(limit)}",
        clock,
        bar=(_pct(frame.out_of_cage_seconds, limit), tone),
    )


def _correct(frame: Telemetry, view: View) -> str:
    rate = (
        "trials/min not yet derived"
        if view.trials_per_min is None
        else f"{view.trials_per_min:.1f} trials/min, derived by wlx serve"
    )
    if frame.trial_index == 0:
        return _cell("Correct / trials", '<span class="nm">no trials yet</span>', sub=rate)
    # The one rollup, and the strip's alone (PI, 2026-09-26, spec §3): `correct` plus
    # `correct_reject`, both the right answer on their trial. The Working? pane and
    # `/health` stay unrolled.
    correct = frame.outcomes.get(Outcome.CORRECT.value, 0) + frame.outcomes.get(
        Outcome.CORRECT_REJECT.value, 0
    )
    percent = 100.0 * correct / frame.trial_index
    return _cell(
        "Correct / trials",
        f'{_e(correct)}<span class="u">/ {_e(frame.trial_index)}</span>',
        sub=f"{percent:.0f}% correct · {rate}",
    )


def _last_reward(frame: Telemetry, view: View) -> str:
    if frame.last_reward_at is None:
        return _cell("Since last reward", '<span class="nm">none yet</span>')
    return _cell("Since last reward", _health.ago(view.now - frame.last_reward_at))


def _strip(frame: Telemetry | None, view: View) -> str:
    if frame is None:
        return "".join(
            _cell(label, _NONE)
            for label in (
                "Fluid today / floor",
                "Out of cage",
                "Correct / trials",
                "Since last reward",
            )
        )
    return (
        _fluid_today(frame)
        + _out_of_cage(frame)
        + _correct(frame, view)
        + _last_reward(frame, view)
    )


# --- banners ----------------------------------------------------------------------


def _banner(tone: str, tag: str, text: str) -> str:
    return (
        f'<div class="banner {tone}"><span class="tag">{tag}</span>'
        f"<span>{text}</span></div>"
    )


def _banners(frame: Telemetry | None, view: View) -> str:
    """A refused frame first, then the duration warning and the stop reason -- where
    a person looks when something is wrong. The stream's own banner (stale, lost) is
    the page script's, in its own element."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    if frame is None:
        out.append(
            _banner(
                "info",
                "Waiting",
                "no telemetry yet: no session is publishing on the link this console reads",
            )
        )
        return "".join(out)
    if frame.duration_warning:
        tone = "crit" if frame.stop_kind == "limit" else "warn"
        out.append(_banner(tone, "Warning", _e(frame.duration_warning)))
    if frame.stopped_because:
        tone = "crit" if frame.stop_kind in ("fault", "limit") else "info"
        out.append(_banner(tone, "Ended", _e(frame.stopped_because)))
    return "".join(out)


# --- runtime ------------------------------------------------------------------------


def _trials(frame: Telemetry | None) -> str:
    """The last outcomes as ticks, oldest first, colored by family, with a legend."""
    if frame is None:
        return _NONE
    recent = frame.recent_outcomes
    blanks = '<span class="tk"></span>' * max(0, RECENT_OUTCOMES - len(recent))
    ticks = "".join(
        f'<span class="tk f-{_health.family_key(outcome)}" title="{_e(outcome)}"></span>'
        for outcome in recent
    )
    legend = "".join(
        f'<span><i class="tk f-{key}"></i>{label}</span>' for key, label in LEGEND
    )
    return (
        f'<div class="sub">the last {len(recent)} of {_e(frame.trial_index)} trials, '
        f"oldest first</div>"
        f'<div class="ticks">{blanks}{ticks}</div><div class="legend">{legend}</div>'
    )


def _fluid(frame: Telemetry) -> str:
    """Fluid session and the supplement: welfare-load-bearing, never dropped."""
    supplement = (
        f'<span class="nm">{_UNKNOWN_DAY}</span>'
        if frame.shortfall_ml is None
        else f'<span class="num">{frame.shortfall_ml:.2f} mL</span>'
    )
    return (
        f'<div class="kv"><span>fluid session</span>'
        f'<span class="num">{frame.fluid_session_ml:.2f} mL</span></div>'
        f'<div class="kv"><span>supplement owed</span>{supplement}</div>'
    )


def _work(frame: Telemetry | None) -> str:
    """Total trials, then every outcome that occurred with its count, by family, and
    no rollup -- `health.families`, so this and `/health` agree (spec §3)."""
    if frame is None:
        return _NONE
    groups = "".join(
        f'<div class="fam"><h3>{_e(label)}</h3>'
        + "".join(
            f'<div class="kv"><span>{_e(name)}</span>'
            f'<span class="num">{_e(count)}</span></div>'
            for name, count in rows
        )
        + "</div>"
        for _, label, rows in _health.families(frame.outcomes)
    )
    hangs = (
        f'<div class="fam"><h3>Hangs</h3><div class="kv"><span>hangs</span>'
        f'<span class="num">{_e(frame.hangs)}</span></div></div>'
    )
    return (
        f'<div class="selrow"><span class="big">{_e(frame.trial_index)}</span>'
        f'<span class="unit">trials</span></div>'
        f'<div class="counts">{groups}{hangs}</div>{_fluid(frame)}'
    )


def _need(frame: Telemetry | None) -> str:
    """Still needed, by condition: `scheduler.owed` as published."""
    if frame is None:
        return _NONE
    if not frame.owed:
        return '<span class="nm">nothing still needed</span>'
    return "".join(
        f'<div class="kv"><span class="mono">{_e(condition)}</span>'
        f'<span class="num">{_e(count)}</span></div>'
        for condition, count in frame.owed.items()
    )


def _wrong(frame: Telemetry | None) -> str:
    """Hangs, which are counted, and the three measurements nothing takes yet."""
    hangs = _NONE if frame is None else f'<span class="num">{_e(frame.hangs)}</span>'
    rows = [f'<div class="kv"><span>hangs</span>{hangs}</div>']
    rows += [
        f'<div class="kv"><span>{name}</span><span class="nm">not measured</span></div>'
        for name in _NOT_MEASURED
    ]
    return "".join(rows)


def _health_pane(frame: Telemetry | None, view: View) -> str:
    """*wl-works sees*: `/health`'s verdict and readings, as they would be sent."""
    verdict = _health.verdict(
        frame, frame_age_s=view.frame_age_s, stale_after_s=view.stale_after_s
    )
    rows = "".join(
        f'<div class="r"><span class="f">{"◆" if reading["featured"] else ""}</span>'
        f'<span class="l">{_e(reading["label"])}</span>'
        f'<span class="v">{_e(reading["value"])}</span></div>'
        for reading in _health.readings(
            frame, frame_age_s=view.frame_age_s, stale_after_s=view.stale_after_s
        )
    )
    return f'<div><span class="pill {_VERDICT_TONE[verdict]}">{verdict}</span></div>{rows}'


def _changes(frame: Telemetry | None) -> str:
    """Staged and refused changes, the dropped-refusal count before the rows, as
    `cli.render` does."""
    if frame is None:
        return _NONE
    rows = []
    for change in frame.staged:
        kind = "welfare-bounded ceiling" if change.bounded else "task parameter"
        rows.append(
            f'<div class="ev staged"><span class="kind">staged</span><span>'
            f"{_e(change.name)} {_e(_num(change.was))} → {_e(_num(change.now))} "
            f"by {_e(change.by)} ({kind}, applies at the next trial)</span></div>"
        )
    if frame.refusals_dropped:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(frame.refusals_dropped)} earlier refusal(s) not shown: only the most "
            f"recent {len(frame.refusals)} are kept</span></div>"
        )
    for refusal in frame.refusals:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(refusal.name)} by {_e(refusal.by)}: {_e(refusal.why)}</span></div>"
        )
    return "".join(rows) or '<span class="nm">nothing staged or refused</span>'


# --- task parameters, setup, end of session ----------------------------------------


def _range(row) -> str:
    if row.bounded:
        return f"welfare ceiling {_e(_num(row.high))} {_e(row.unit)}"
    if row.low is None and row.high is None:
        return "no declared range"
    return f"{_e(_edge(row.low))} to {_e(_edge(row.high))} {_e(row.unit)}"


def _params(frame: Telemetry | None) -> str:
    """One card per `ParamRow`: value, unit, range, the ceiling flag, and a staged
    marker. Read-only: b2 adds the inputs."""
    if frame is None:
        return _NONE
    if not frame.params:
        return '<span class="nm">this task declares no parameters</span>'
    staged = {change.name: change for change in frame.staged}
    cards = []
    for row in frame.params:
        change = staged.get(row.name)
        flag = '<span class="ceil">ceiling</span>' if row.bounded else ""
        mark = (
            ""
            if change is None
            else f'<span class="stg">staged → {_e(_num(change.now))} by {_e(change.by)}</span>'
        )
        cls = "param staged" if change is not None else "param"
        cards.append(
            f'<div class="{cls}"><div class="pn"><span>{_e(row.name)}</span>{flag}</div>'
            f'<span class="pv">{_e(_num(row.value))} '
            f'<span class="unit">{_e(row.unit)}</span></span>'
            f'<span class="range">{_range(row)}</span>{mark}</div>'
        )
    return "".join(cards)


def _setup(frame: Telemetry | None) -> str:
    """S9a §3's configuration information. Display mode and stimulus calibration have
    no source yet and say so (spec §3)."""
    if frame is None:
        return _NONE
    limit = (
        '<span class="nm">none: cage-side</span>'
        if frame.out_of_cage_limit_s is None
        else _clock(frame.out_of_cage_limit_s)
    )
    rows = (
        ("session", _e(frame.session_id)),
        ("subject", _e(frame.subject)),
        ("deployment", _e(frame.deployment)),
        ("task", _e(frame.task)),
        (
            "allocation",
            _e(frame.allocation)
            if frame.allocation
            else '<span class="nm">provisional: none given</span>',
        ),
        (
            "bounds config",
            _e(frame.bounds_config)
            if frame.bounds_config
            else '<span class="nm">not given</span>',
        ),
        ("daily fluid floor", f"{frame.floor_ml:.2f} mL"),
        ("out-of-cage limit", limit),
        ("display mode", '<span class="nm">no source yet</span>'),
        ("stimulus calibration", '<span class="nm">no source yet</span>'),
    )
    return (
        '<dl class="dl">'
        + "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in rows)
        + "</dl>"
    )


def _end(frame: Telemetry | None) -> str:
    """The supplement owed, fluid session, out-of-cage and in-session time, and the
    stop reason (spec §4.2)."""
    if frame is None:
        return _NONE
    owed = (
        f'<span class="nm">{_UNKNOWN_DAY}</span>'
        if frame.shortfall_ml is None
        else f'<span class="big">{frame.shortfall_ml:.2f}</span><span class="unit">mL</span>'
    )
    cage = (
        '<span class="nm">cage-side · no out-of-cage interval</span>'
        if frame.out_of_cage_seconds is None
        else _clock(frame.out_of_cage_seconds)
    )
    in_session = (
        '<span class="nm">not recorded</span>'
        if frame.in_session_seconds is None
        else _clock(frame.in_session_seconds)
    )
    reason = (
        _e(frame.stopped_because)
        if frame.stopped_because
        else '<span class="nm">still running</span>'
    )
    return (
        f'<div class="owe"><h2>Supplement owed</h2>{owed}</div>'
        f'<dl class="dl"><dt>fluid session</dt><dd>{frame.fluid_session_ml:.2f} mL</dd>'
        f"<dt>out of cage</dt><dd>{cage}</dd>"
        f"<dt>in session</dt><dd>{in_session}</dd>"
        f"<dt>stop reason</dt><dd>{reason}</dd></dl>"
    )


def fragments(frame: Telemetry | None, view: View) -> dict[str, str]:
    """Every pane of the page for one frame, keyed by the id of the element each one
    fills (`FRAGMENT_IDS`, in that order). `frame` is `None` before any has arrived,
    and every pane then says so."""
    return {
        "state": _state(frame),
        "head-id": _head(frame),
        "presence": _presence(view),
        "strip": _strip(frame, view),
        "banners": _banners(frame, view),
        "rt-trials": _trials(frame),
        "rt-work": _work(frame),
        "rt-need": _need(frame),
        "rt-wrong": _wrong(frame),
        "rt-health": _health_pane(frame, view),
        "rt-changes": _changes(frame),
        "params": _params(frame),
        "setup": _setup(frame),
        "end": _end(frame),
    }
```

In `tools/mutation_gate.py`, add `"web": "None",` to `RETURNS` (after `"health": "None",`).

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_web.py tests/test_health.py tests/test_mutation_gate.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/web.py tests/_frames.py tests/test_web.py tools/mutation_gate.py
git commit -m "Render the console's panes in Python, escaped, with nothing unmeasured shown as 0"
```

---
### Task 8: The page — `web.page`, its CSS, its script and its bundled fonts

**Why:** spec §4.2–§4.4 and the mockup. One HTML document with every pane already rendered into it, the mockup's wl-works tokens and layout for the parts b1 builds, tabs that need no script, the right column's honest placeholders, and a script that does only what spec §4.3 lists: open the stream, swap fragments by id, run the stale timer, close the stream on ✕, and reconnect.

**The fonts are bundled** (PI, 2026-09-26, recorded in spec §4.2: "bundle the fonts"). IBM Plex Sans, Plex Sans Condensed, Plex Mono and Newsreader ship inside the package and are served by `wlx serve` (Task 10 adds the route), so the page keeps the wl-works look and never reaches the internet. Only the weights `_CSS` sets are shipped, as the unmodified woff2 files their primary sources publish; italics are synthesized, as they were in the mockup. Newsreader draws only the logo, at 700 upright and italic, from its 72pt optical-size cut — the size the logo's text is set at, which is what the mockup's variable font resolved to.

**Sources and licenses, read 2026-09-26:**

| Family | Primary source | License, verified 2026-09-26 |
|---|---|---|
| IBM Plex Sans | GitHub release `@ibm/plex-sans@1.1.0` of github.com/IBM/plex, asset `ibm-plex-sans.zip` | OFL-1.1, Reserved Font Name "Plex": `LICENSE.txt` at the root of github.com/IBM/plex (branch `master`, head `763c36e`) and in each release zip, byte-identical (sha256 `7e6b2818…`) |
| IBM Plex Sans Condensed | release `@ibm/plex-sans-condensed@2.0.0`, asset `ibm-plex-sans-condensed.zip` | as above |
| IBM Plex Mono | release `@ibm/plex-mono@2.5.0`, asset `ibm-plex-mono.zip` | as above |
| Newsreader | github.com/productiontype/Newsreader at `cfcb4f7af0e52c25e8df2a2431814c8e5fe2e155` (branch `master`'s head, 2021-03-01), `fonts/static/woff2/` | OFL-1.1, no Reserved Font Name: `OFL.txt` at that commit, byte-identical to google/fonts `ofl/newsreader/OFL.txt` (sha256 `fdfad381…`) |

google/fonts' `ofl/newsreader` carries only variable TTF files, so the woff2 files come from Production Type's own repository, which google/fonts names as the upstream (`ofl/newsreader/upstream_info.md`).

**The OFL-1.1 conditions that bind this task** (from the license text verified above): condition 2 permits bundling "with any software, provided that each copy contains the above copyright notice and this license" — so each family's license ships beside its files; condition 3 keeps a Reserved Font Name off any Modified Version — so the files are never subset or converted, and Plex stays Plex; condition 5 keeps the fonts under the OFL but "does not apply to any document created using the Font Software".

**Files:**
- Create: `wl_expcontroller/fonts/ibm-plex-sans/` (`IBMPlexSans-Regular.woff2`, `IBMPlexSans-Medium.woff2`, `IBMPlexSans-SemiBold.woff2`, `OFL.txt`); `wl_expcontroller/fonts/ibm-plex-sans-condensed/` (`IBMPlexSansCondensed-Regular.woff2`, `IBMPlexSansCondensed-SemiBold.woff2`, `IBMPlexSansCondensed-Bold.woff2`, `OFL.txt`); `wl_expcontroller/fonts/ibm-plex-mono/` (`IBMPlexMono-Regular.woff2`, `IBMPlexMono-Medium.woff2`, `IBMPlexMono-SemiBold.woff2`, `OFL.txt`); `wl_expcontroller/fonts/newsreader/` (`Newsreader72pt-Bold.woff2`, `Newsreader72pt-BoldItalic.woff2`, `OFL.txt`)
- Modify: `pyproject.toml` (a `[tool.setuptools.package-data]` table — the package has no data files yet, so this is the first)
- Modify: `docs/design/decisions/ADR-0004-license.md` (two inventory rows, under its 2026-09-26 amendment allowing unmodified OFL-1.1 fonts as assets)
- Modify: `wl_expcontroller/web.py` (add `Font`, `FONTS`, `font_bytes`, `_FONT_FACES`, `_CSS`, `_LOGO`, `_SCRIPT`, `page`)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 7's `FRAGMENT_IDS`, `fragments`, `_e`.
- Produces:
  - `web.page(parts: dict[str, str], *, stale_after_s: float, nonce: str) -> str` — raises `KeyError` if `parts` lacks any of `FRAGMENT_IDS`. The page's script expects `GET /events` to send events named `frame` whose data is `{"frags": {id: html, ...}, "live": bool}` (Task 10 sends them). Element ids the script uses: `stream`, `gone`, `close`, `reconnect`. `<body data-stale-after="N">`. The page contains no `http://` or `https://` URL.
  - `web.Font(family: str, weight: int, style: str, directory: str, file: str)` — frozen, slotted.
  - `web.FONTS: tuple[Font, ...]` — the eleven faces above; each file is `wl_expcontroller/fonts/<directory>/<file>`, and the page asks for it at `/fonts/<file>`.
  - `web.font_bytes(font: Font) -> bytes` — the file, read as package data. Task 10 serves it.

- [ ] **Step 1: Fetch the fonts from their primary sources**

From the worktree root:

```bash
W="${TMPDIR:-/tmp}/wlx-fonts"; R="$PWD/wl_expcontroller/fonts"
mkdir -p "$W" "$R/ibm-plex-sans" "$R/ibm-plex-sans-condensed" "$R/ibm-plex-mono" "$R/newsreader"
curl -fsSL -o "$W/plex-sans.zip" "https://github.com/IBM/plex/releases/download/%40ibm/plex-sans%401.1.0/ibm-plex-sans.zip"
curl -fsSL -o "$W/plex-sans-condensed.zip" "https://github.com/IBM/plex/releases/download/%40ibm/plex-sans-condensed%402.0.0/ibm-plex-sans-condensed.zip"
curl -fsSL -o "$W/plex-mono.zip" "https://github.com/IBM/plex/releases/download/%40ibm/plex-mono%402.5.0/ibm-plex-mono.zip"
unzip -j -o "$W/plex-sans.zip" ibm-plex-sans/fonts/complete/woff2/IBMPlexSans-Regular.woff2 ibm-plex-sans/fonts/complete/woff2/IBMPlexSans-Medium.woff2 ibm-plex-sans/fonts/complete/woff2/IBMPlexSans-SemiBold.woff2 -d "$R/ibm-plex-sans"
unzip -j -o "$W/plex-sans-condensed.zip" ibm-plex-sans-condensed/fonts/complete/woff2/IBMPlexSansCondensed-Regular.woff2 ibm-plex-sans-condensed/fonts/complete/woff2/IBMPlexSansCondensed-SemiBold.woff2 ibm-plex-sans-condensed/fonts/complete/woff2/IBMPlexSansCondensed-Bold.woff2 -d "$R/ibm-plex-sans-condensed"
unzip -j -o "$W/plex-mono.zip" ibm-plex-mono/fonts/complete/woff2/IBMPlexMono-Regular.woff2 ibm-plex-mono/fonts/complete/woff2/IBMPlexMono-Medium.woff2 ibm-plex-mono/fonts/complete/woff2/IBMPlexMono-SemiBold.woff2 -d "$R/ibm-plex-mono"
unzip -p "$W/plex-sans.zip" ibm-plex-sans/LICENSE.txt > "$R/ibm-plex-sans/OFL.txt"
unzip -p "$W/plex-sans-condensed.zip" ibm-plex-sans-condensed/LICENSE.txt > "$R/ibm-plex-sans-condensed/OFL.txt"
unzip -p "$W/plex-mono.zip" ibm-plex-mono/LICENSE.txt > "$R/ibm-plex-mono/OFL.txt"
N="https://raw.githubusercontent.com/productiontype/Newsreader/cfcb4f7af0e52c25e8df2a2431814c8e5fe2e155"
curl -fsSL -o "$R/newsreader/Newsreader72pt-Bold.woff2" "$N/fonts/static/woff2/Newsreader72pt-Bold.woff2"
curl -fsSL -o "$R/newsreader/Newsreader72pt-BoldItalic.woff2" "$N/fonts/static/woff2/Newsreader72pt-BoldItalic.woff2"
curl -fsSL -o "$R/newsreader/OFL.txt" "$N/OFL.txt"
```

Plex's license file is `LICENSE.txt` upstream; it is kept byte for byte, under the name `OFL.txt` so every family's license sits under one name. Then check every file against what was fetched when this plan was written, by running this script from the worktree root (save it as `${TMPDIR:-/tmp}/check_fonts.py` and run `python "${TMPDIR:-/tmp}/check_fonts.py"`):

```python
import hashlib
from pathlib import Path

EXPECTED = {
    "ibm-plex-sans/IBMPlexSans-Regular.woff2": "ba711a3085ff9f27440b6b9c4550cfc47c97bf36591d5da958b975bb3add8c1a",
    "ibm-plex-sans/IBMPlexSans-Medium.woff2": "5660f8a658f8bb50dbc005232f885eadffd2bc1c235c4f6fbb63469d1f9cde6d",
    "ibm-plex-sans/IBMPlexSans-SemiBold.woff2": "f78048030eab62e860efa39a0df79e2e5581bf122eb95b9bc42c0b8a4988d205",
    "ibm-plex-sans-condensed/IBMPlexSansCondensed-Regular.woff2": "a71a56e516751883cb7877112d39f9c13b92c2dc15caaf00277b7f9d941d673a",
    "ibm-plex-sans-condensed/IBMPlexSansCondensed-SemiBold.woff2": "385a082a1eac88343eab01fb6746be04b7175dacaf4550b17dee76ea0f78126d",
    "ibm-plex-sans-condensed/IBMPlexSansCondensed-Bold.woff2": "e1481c7a925b4bfb31bcbff09182b43d5f1c1eab7834a2b6ac51ac75b8c3f9a1",
    "ibm-plex-mono/IBMPlexMono-Regular.woff2": "ba204497f16b6d334cee9d1e963a831b73e3a56e1d6300a8489d18df7214b350",
    "ibm-plex-mono/IBMPlexMono-Medium.woff2": "33faf307fa6031fb4062276d7320a6d632de890cbb347576fd80cfa01077bc25",
    "ibm-plex-mono/IBMPlexMono-SemiBold.woff2": "6a825b4824c01cbb401e829e5a066a1818411bcb3538b5a5792c5ca9b82343c3",
    "newsreader/Newsreader72pt-Bold.woff2": "4785c0388ea38c0b8932c275cc2b0a72067bbeb040a46d9e58068b6ad36520da",
    "newsreader/Newsreader72pt-BoldItalic.woff2": "9a29791366e5afbbeeaf0623abaa64cfcdb2a363e92bf82719693a2b921c3687",
    "ibm-plex-sans/OFL.txt": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
    "ibm-plex-sans-condensed/OFL.txt": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
    "ibm-plex-mono/OFL.txt": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
    "newsreader/OFL.txt": "fdfad38143ec470553cae82a1e45320bdd1b9ec70415d37bd0171051d8a4ded8",
}
root = Path("wl_expcontroller/fonts")
for rel, digest in EXPECTED.items():
    got = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    print("ok      " if got == digest else "MISMATCH", rel)
present = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
print("nothing else present:", present == sorted(EXPECTED))
```

Expected: fifteen `ok` lines and `nothing else present: True`. A `MISMATCH` means a source changed since 2026-09-26: stop, and say so in the task report — a changed font or license is a new dependency decision, not a checksum to update.

- [ ] **Step 2: Verify each license at its primary source, and record it**

Read each license where it is published, not only the copy that came with the files:

```bash
curl -fsSL https://raw.githubusercontent.com/IBM/plex/master/LICENSE.txt | shasum -a 256
curl -fsSL https://raw.githubusercontent.com/IBM/plex/master/LICENSE.txt | head -3
curl -fsSL https://raw.githubusercontent.com/google/fonts/main/ofl/newsreader/OFL.txt | shasum -a 256
curl -fsSL https://raw.githubusercontent.com/google/fonts/main/ofl/newsreader/OFL.txt | head -3
```

Expected: `7e6b2818…`, then `Copyright © 2017 IBM Corp. with Reserved Font Name "Plex"` and `This Font Software is licensed under the SIL Open Font License, Version 1.1.`; then `fdfad381…`, `Copyright 2020 The Newsreader Project Authors (http://github.com/productiontype/Newsreader)` and the same license line. **If a primary source cannot be read, or its text differs, write UNVERIFIED and the date in that inventory row instead of "verified", and say so in the task report.**

In `docs/design/decisions/ADR-0004-license.md`, add two rows to the Dependency inventory table:

```markdown
| IBM Plex Sans, Plex Sans Condensed, Plex Mono (fonts, bundled unmodified as woff2 in `wl_expcontroller/fonts/`) | OFL-1.1, Reserved Font Name "Plex" (`LICENSE.txt` at the root of github.com/IBM/plex and in each release zip, byte-identical, verified 2026-09-26) | The console page's wl-works typography, served by `wlx serve` so the page never reaches the internet (P4d-2b spec §4.2, PI 2026-09-26). From the `@ibm/plex-sans@1.1.0`, `@ibm/plex-sans-condensed@2.0.0` and `@ibm/plex-mono@2.5.0` releases; never subset or converted, which would make a Modified Version that could not be called Plex |
| Newsreader (font, bundled unmodified as woff2 in `wl_expcontroller/fonts/newsreader/`) | OFL-1.1 (`OFL.txt` at productiontype/Newsreader `cfcb4f7`, byte-identical to google/fonts `ofl/newsreader/OFL.txt`, verified 2026-09-26) | The wl.works logo's face on the console page: 700 upright and italic, from the 72pt optical-size cut, the size the logo's text is set at |
```

and, at the end of its Consequences section, add:

```markdown
**Reopened for the console's fonts (2026-09-26, P4d-2b b1)**, as the paragraph above requires
of a copyleft addition. OFL-1.1's condition 5 keeps the font files under the OFL. Its
condition 2 permits bundling them "with any software, provided that each copy contains the
above copyright notice and this license", and condition 5 does "not apply to any document
created using the Font Software" -- so the Apache-2.0 code, and the pages it serves, stay
Apache-2.0. The files ship unmodified, each family's license beside them as `OFL.txt`, read
from its primary source on 2026-09-26 (see the inventory). Put to the PI with the branch's
welfare item.
```

In `pyproject.toml`, add directly after the `[tool.setuptools.packages.find]` table:

```toml
[tool.setuptools.package-data]
# The console page's fonts (P4d-2b b1), served by `wlx serve` so the page never reaches
# the internet. Each family's license ships beside its files as OFL.txt, which OFL-1.1's
# condition 2 requires (ADR-0004's inventory).
wl_expcontroller = ["fonts/*/*.woff2", "fonts/*/OFL.txt"]
```

- [ ] **Step 3: Write the failing tests**

In `tests/test_web.py`, add `import fnmatch`, `import tomllib`, `from importlib import resources` and `from pathlib import Path` to the imports, change the `wl_expcontroller.web` import to `from wl_expcontroller.web import FONTS, FRAGMENT_IDS, LEGEND, font_bytes, fragments, page`, and append:

```python
# --- the page (Task 8) --------------------------------------------------------------


def _document(**frame_overrides) -> str:
    return page(
        fragments(frame(**frame_overrides), view()), stale_after_s=30.0, nonce="n0nce"
    )


def test_the_page_holds_every_pane_in_the_element_its_stream_swaps():
    """On connect the page is already rendered (spec §4.3): each fragment sits in the
    element whose id the stream's events name, and each id is on the page once."""
    parts = fragments(frame(), view())
    document = page(parts, stale_after_s=30.0, nonce="n0nce")

    for key in FRAGMENT_IDS:
        assert document.count(f'id="{key}"') == 1, key
        assert re.search(
            rf'id="{re.escape(key)}"[^>]*>{re.escape(parts[key])}<', document
        ), key


def test_a_page_missing_a_pane_is_refused_not_rendered_blank():
    parts = fragments(frame(), view())
    del parts["strip"]

    with pytest.raises(KeyError):
        page(parts, stale_after_s=30.0, nonce="n0nce")


def test_the_one_script_carries_the_nonce_and_nothing_loads_from_elsewhere():
    """A lab host renders with no internet: the fonts are the box's own (PI,
    2026-09-26), and the page names no other host at all."""
    document = _document()

    assert document.count("<script") == 1
    assert '<script nonce="n0nce">' in document
    assert "<link" not in document
    assert "http://" not in document and "https://" not in document
    assert not re.search(r'(?:src|href|url)\s*[=(]\s*"?//', document)


def test_the_page_declares_each_bundled_font_and_no_other():
    document = _document()

    assert document.count("@font-face") == len(FONTS)
    for font in FONTS:
        assert f'url("/fonts/{font.file}") format("woff2")' in document, font.file
    for family in (
        "IBM Plex Sans",
        "IBM Plex Sans Condensed",
        "IBM Plex Mono",
        "Newsreader",
    ):
        assert any(font.family == family for font in FONTS), family


def test_every_font_the_page_uses_is_bundled_with_its_license():
    """OFL-1.1 condition 2: each copy carries the copyright notice and the license --
    here, beside the files, as `OFL.txt`. And each file is the woff2 it claims to be."""
    fonts = resources.files("wl_expcontroller").joinpath("fonts")

    for font in FONTS:
        assert font_bytes(font)[:4] == b"wOF2", font.file
    for directory in {font.directory for font in FONTS}:
        text = fonts.joinpath(directory).joinpath("OFL.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in text, directory


def test_the_fonts_ship_with_the_package():
    """`pyproject.toml`'s package data carries every font and its license, so an
    installed `wlx serve` serves what a checkout does."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["setuptools"]
    globs = table["package-data"]["wl_expcontroller"]

    for font in FONTS:
        for rel in (f"fonts/{font.directory}/{font.file}", f"fonts/{font.directory}/OFL.txt"):
            assert any(fnmatch.fnmatch(rel, pattern) for pattern in globs), rel


def test_the_nonce_is_escaped_into_its_attribute():
    document = page(fragments(frame(), view()), stale_after_s=30.0, nonce='x"><b>')

    assert '<script nonce="x&quot;&gt;&lt;b&gt;">' in document


def test_the_page_tells_its_script_when_a_stream_is_stale():
    document = page(fragments(frame(), view()), stale_after_s=45.0, nonce="n0nce")

    assert '<body data-stale-after="45">' in document


def test_the_right_column_is_honest_placeholders():
    """So the layout never shifts and nothing pretends to be live (PI, 2026-09-26)."""
    document = _document()

    for text in (
        "replica · V11",
        "subject display · no source yet",
        "sound · not measured",
        "display · not measured",
    ):
        assert text in document, text


def test_nothing_on_the_page_writes():
    """Spec §4.2: every write control is absent until its slice. The page's buttons
    close and reopen its own stream; its inputs only choose a tab."""
    document = _document()

    assert document.count("<button") == 2
    assert 'id="close"' in document and 'id="reconnect"' in document
    for absent in ("<form", "<textarea", "<select", "POST", "fetch("):
        assert absent not in document, absent
    inputs = re.findall(r"<input[^>]*>", document)
    assert len(inputs) == 4
    assert all('type="radio"' in field for field in inputs)


def test_the_script_does_only_what_spec_4_3_asks():
    document = _document()

    for needle in (
        'new EventSource("/events")',
        'addEventListener("frame"',
        "innerHTML",
        "stream stale · last frame ",
        "stream lost",
        'el("close")',
        'el("reconnect")',
        "source.close()",
    ):
        assert needle in document, needle
    assert "disconnected · the session keeps running on the box" in document


def test_the_stream_banner_and_the_disconnect_dialog_start_hidden():
    document = _document()

    assert '<div class="banner" id="stream" role="status" hidden></div>' in document
    assert re.search(r'<div class="scrim" id="gone"[^>]*hidden>', document)
```

- [ ] **Step 4: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_web.py`
Expected: collection error — `ImportError: cannot import name 'FONTS' from 'wl_expcontroller.web'`.

- [ ] **Step 5: Implement**

Add `from importlib import resources` to `wl_expcontroller/web.py`'s imports, and append:

```python
# --- the page -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Font:
    """One face the page uses: bundled at `wl_expcontroller/fonts/<directory>/<file>`
    and served by `wlx serve` at `/fonts/<file>`."""

    family: str
    weight: int
    style: str
    directory: str
    file: str


#: **Every face the page's CSS asks for, and no other** (PI, 2026-09-26: "bundle the
#: fonts", so the page keeps the wl-works look and never reaches the internet). The
#: unmodified woff2 files their primary sources publish -- the IBM/plex GitHub releases
#: and productiontype/Newsreader -- fetched 2026-09-26, each family's OFL-1.1 license
#: beside them as `OFL.txt`; ADR-0004's inventory carries the sources and licenses.
#: The weights are the ones `_CSS` sets; italics are synthesized, as in the mockup.
#: Newsreader draws only the logo, from its 72pt optical-size cut.
FONTS = (
    Font("IBM Plex Sans", 400, "normal", "ibm-plex-sans", "IBMPlexSans-Regular.woff2"),
    Font("IBM Plex Sans", 500, "normal", "ibm-plex-sans", "IBMPlexSans-Medium.woff2"),
    Font("IBM Plex Sans", 600, "normal", "ibm-plex-sans", "IBMPlexSans-SemiBold.woff2"),
    Font(
        "IBM Plex Sans Condensed",
        400,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-Regular.woff2",
    ),
    Font(
        "IBM Plex Sans Condensed",
        600,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-SemiBold.woff2",
    ),
    Font(
        "IBM Plex Sans Condensed",
        700,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-Bold.woff2",
    ),
    Font("IBM Plex Mono", 400, "normal", "ibm-plex-mono", "IBMPlexMono-Regular.woff2"),
    Font("IBM Plex Mono", 500, "normal", "ibm-plex-mono", "IBMPlexMono-Medium.woff2"),
    Font("IBM Plex Mono", 600, "normal", "ibm-plex-mono", "IBMPlexMono-SemiBold.woff2"),
    Font("Newsreader", 700, "normal", "newsreader", "Newsreader72pt-Bold.woff2"),
    Font("Newsreader", 700, "italic", "newsreader", "Newsreader72pt-BoldItalic.woff2"),
)


def font_bytes(font: Font) -> bytes:
    """A bundled font file, read as package data -- the same bytes from a checkout and
    from an installed wheel (`pyproject.toml`'s `package-data`)."""
    return (
        resources.files("wl_expcontroller")
        .joinpath("fonts")
        .joinpath(font.directory)
        .joinpath(font.file)
        .read_bytes()
    )


#: One `@font-face` per bundled face, each fetched from this box's `/fonts/` route.
_FONT_FACES = "".join(
    f'@font-face {{ font-family: "{font.family}"; font-style: {font.style}; '
    f"font-weight: {font.weight}; font-display: swap; "
    f'src: url("/fonts/{font.file}") format("woff2"); }}\n'
    for font in FONTS
)

#: The mockup's wl-works tokens and layout (`docs/superpowers/mockups/
#: 2026-09-26-console-mockup-v12.html`), trimmed to what b1 builds. **The fonts are the
#: box's own** (`FONTS`, `_FONT_FACES`); each stack's system faces are only the fallback
#: while they load. Tabs are radio inputs styled by `:checked`, so they need no script.
_CSS = """
:root {
  --bg: #faf8f3; --surface: #fffefb; --surface-2: #f2f0e9; --ink: #050c19; --muted: #55606f;
  --rule: rgb(136 148 166 / 0.45); --edge: rgb(5 12 25 / 0.08);
  --accent: #0a6e6b; --accent-fg: #faf8f3; --accent-soft: #dfecea;
  --ok: #2e7a4f; --ok-soft: #deefe4; --warn: #9a5b00; --warn-soft: #f6e7cf;
  --crit: #b3261e; --crit-soft: #f6dcda;
  --screen: #081122; --screen-ink: #8ea0bc; --rf: #67b2ea; --mock: #452d81;
  --wl-muted: #55606f; --distract: #c9187b;
  --shadow: inset 0 1px 0 rgb(255 255 255 / 0.9), inset 0 -1px 0 rgb(5 12 25 / 0.06), 0 1px 2px rgb(5 12 25 / 0.04), 0 8px 28px -12px rgb(5 12 25 / 0.18);
  --sans: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  --cond: "IBM Plex Sans Condensed", "IBM Plex Sans", "Arial Narrow", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #050c19; --surface: #112037; --surface-2: #152743; --ink: #faf8f3; --muted: #8ea0bc;
    --rule: rgb(136 148 166 / 0.3); --edge: rgb(250 248 243 / 0.1);
    --accent: #12a5a1; --accent-fg: #050c19; --accent-soft: #0f3a44;
    --ok: #5cba80; --ok-soft: #133427; --warn: #e6a646; --warn-soft: #382a12;
    --crit: #f07166; --crit-soft: #3c1b1a;
    --screen: #02060d; --mock: #b3a2ea; --wl-muted: #8ea0bc; --distract: #d6579c;
    --shadow: inset 0 1px 0 rgb(250 248 243 / 0.06), inset 0 -1px 0 rgb(0 0 0 / 0.25), 0 1px 2px rgb(0 0 0 / 0.3), 0 8px 28px -12px rgb(0 0 0 / 0.6);
  }
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.4; padding: 12px 16px 28px; }
.wrap { max-width: 1520px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.num, .mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
h2 { font-family: var(--cond); font-weight: 700; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin: 0; }
h3 { margin: 0; font-family: var(--cond); font-weight: 600; font-size: 11.5px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); }
.sub { font-size: 12.5px; color: var(--muted); }
.nm { color: var(--muted); font-style: italic; }
.later { font-size: 11px; color: var(--mock); font-family: var(--cond); letter-spacing: 0.05em; text-transform: uppercase; font-weight: 600; }
.glass { background: var(--surface); border: 1px solid var(--edge); border-radius: 8px; box-shadow: var(--shadow); }
.head { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center; padding: 8px 14px; }
.logo { display: flex; align-items: center; gap: 10px; color: var(--ink); }
.logo svg { height: 34px; width: auto; display: block; }
.logo .app { font-family: var(--cond); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12px; color: var(--muted); border-left: 1px solid var(--rule); padding-left: 10px; }
.head .id { display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; }
.head .k { font-family: var(--cond); font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin-right: 4px; }
.head .v { font-family: var(--mono); font-weight: 500; }
.head .spacer { flex: 1; }
.presence { font-size: 12.5px; color: var(--muted); }
.presence b { color: var(--ink); font-weight: 600; }
.pill { font-family: var(--cond); font-weight: 700; letter-spacing: 0.08em; font-size: 12px; text-transform: uppercase; border-radius: 999px; padding: 3px 10px; display: inline-flex; gap: 6px; align-items: center; white-space: nowrap; }
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.pill.ok { background: var(--ok-soft); color: var(--ok); }
.pill.warn { background: var(--warn-soft); color: var(--warn); }
.pill.crit { background: var(--crit-soft); color: var(--crit); }
.pill.neutral { background: var(--surface-2); color: var(--muted); }
.strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); overflow: hidden; }
.strip > div { padding: 5px 12px; display: grid; gap: 3px; border-left: 1px solid var(--rule); }
.strip > div:first-child { border-left: 0; }
.strip .row { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 0 8px; }
.strip .lab { font-family: var(--cond); font-weight: 700; font-size: 11.5px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }
.strip .val { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 14.5px; font-weight: 600; white-space: nowrap; }
.strip .val .u { font-size: 12px; color: var(--muted); font-family: var(--sans); font-weight: 400; margin-left: 3px; }
.strip .bar { height: 4px; }
.banners { display: grid; gap: 6px; }
.banner { border-radius: 6px; padding: 6px 12px; font-size: 13.5px; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.banner.warn { background: var(--warn-soft); border-left: 4px solid var(--warn); }
.banner.crit { background: var(--crit-soft); border-left: 4px solid var(--crit); }
.banner.info { background: var(--accent-soft); border-left: 4px solid var(--accent); }
.banner .tag { font-family: var(--cond); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12px; }
.shell { display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr) minmax(260px, 330px); align-items: stretch; }
@media (max-width: 900px) { .shell { grid-template-columns: minmax(0, 1fr); } }
.main { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.main > input { position: absolute; opacity: 0; pointer-events: none; }
.tabs { display: flex; flex-wrap: wrap; gap: 2px; border-bottom: 1px solid var(--rule); }
.tab { border: 1px solid transparent; border-bottom: 0; padding: 7px 12px 6px; cursor: pointer; font-family: var(--cond); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12.5px; color: var(--muted); border-radius: 6px 6px 0 0; margin-bottom: -1px; }
#t-runtime:checked ~ .tabs [for="t-runtime"], #t-task:checked ~ .tabs [for="t-task"], #t-setup:checked ~ .tabs [for="t-setup"], #t-end:checked ~ .tabs [for="t-end"] { background: var(--surface); border-color: var(--edge); color: var(--ink); }
#t-runtime:focus-visible ~ .tabs [for="t-runtime"], #t-task:focus-visible ~ .tabs [for="t-task"], #t-setup:focus-visible ~ .tabs [for="t-setup"], #t-end:focus-visible ~ .tabs [for="t-end"] { outline: 2px solid var(--accent); outline-offset: 2px; }
.tabpanel { display: none; flex-direction: column; gap: 10px; }
#t-runtime:checked ~ .panels #tp-runtime, #t-task:checked ~ .panels #tp-task, #t-setup:checked ~ .panels #tp-setup, #t-end:checked ~ .panels #tp-end { display: flex; }
.cols { display: grid; gap: 10px; align-items: stretch; }
.cols.c3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
@media (max-width: 1100px) { .cols.c3 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .cols.c3 { grid-template-columns: minmax(0, 1fr); } }
.stack, .aside { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.panel { padding: 9px 12px; display: grid; gap: 7px; align-content: start; min-width: 0; }
.panel .top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 10px; font-size: 13px; margin: 0; }
.dl dt { color: var(--muted); }
.dl dd { margin: 0; font-family: var(--mono); font-size: 12.5px; overflow-wrap: anywhere; }
.big { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 22px; font-weight: 600; line-height: 1.1; }
.unit { font-size: 13px; color: var(--muted); font-weight: 500; margin-left: 3px; font-family: var(--sans); }
.selrow { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.bar { height: 8px; background: var(--surface-2); border-radius: 3px; position: relative; overflow: hidden; }
.bar .fill { position: absolute; inset: 0 auto 0 0; background: var(--accent); }
.bar .fill.ok { background: var(--ok); } .bar .fill.warn { background: var(--warn); } .bar .fill.crit { background: var(--crit); }
.counts { display: grid; gap: 6px 14px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.fam { display: grid; gap: 1px; align-content: start; }
.kv { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }
.kv > span { min-width: 0; overflow-wrap: anywhere; }
.owe { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; background: var(--accent-soft); border-radius: 6px; padding: 8px 10px; }
.params { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
.param { border: 1px solid var(--rule); border-radius: 5px; padding: 6px 8px; display: grid; gap: 2px; background: var(--surface-2); }
.param .pn { font-family: var(--mono); font-size: 12.5px; font-weight: 500; display: flex; justify-content: space-between; gap: 6px; overflow-wrap: anywhere; }
.param .ceil { font-family: var(--cond); font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--warn); font-weight: 700; }
.param .pv { font-family: var(--mono); font-size: 13px; }
.param .range, .param .stg { font-size: 11.5px; color: var(--muted); }
.param.staged { border-color: var(--accent); }
.param.staged .stg { color: var(--accent); }
.feed { display: grid; align-content: start; max-height: 300px; overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; }
.ev { display: grid; grid-template-columns: 5.5em minmax(0, 1fr); gap: 6px; padding: 4px 0; border-top: 1px solid var(--rule); font-size: 12.5px; }
.ev:first-child { border-top: 0; }
.ev > span { min-width: 0; overflow-wrap: anywhere; }
.ev .kind { font-family: var(--cond); font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; font-size: 11px; }
.ev.staged .kind { color: var(--accent); } .ev.refused .kind { color: var(--crit); }
.health .r { display: grid; grid-template-columns: 1em minmax(0, 7.5em) minmax(0, 1fr); gap: 6px; font-size: 12.5px; }
.health .r .f { color: var(--accent); } .health .r .l { color: var(--muted); }
.health .r .v { font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.ticks { display: grid; grid-template-columns: repeat(30, minmax(0, 1fr)); gap: 2px; }
.tk { display: block; height: 12px; border-radius: 2px; background: var(--surface-2); }
.tk.f-target { background: var(--accent); } .tk.f-distractor { background: var(--crit); } .tk.f-withhold { background: var(--rf); }
.tk.f-no_engagement { background: color-mix(in srgb, var(--muted) 60%, transparent); } .tk.f-breaks { background: var(--warn); } .tk.f-rig { background: var(--mock); }
.tk.f-hang { background: var(--ink); } .tk.f-other { background: transparent; box-shadow: inset 0 0 0 1px var(--muted); }
.legend { display: flex; flex-wrap: wrap; gap: 3px 12px; font-size: 11.5px; color: var(--muted); }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
.screen { border-radius: 5px; background: var(--screen); color: var(--screen-ink); aspect-ratio: 16 / 9; display: grid; place-items: center; font-family: var(--mono); font-size: 12px; }
.duo { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.xbtn { width: 30px; height: 30px; display: grid; place-items: center; border: 1.5px solid var(--distract); color: var(--distract); background: transparent; border-radius: 6px; cursor: pointer; padding: 0; flex: none; }
.xbtn:hover { background: var(--distract); color: var(--bg); }
.xbtn svg { width: 12px; height: 12px; }
.btn { border: 1px solid var(--rule); background: var(--surface); color: inherit; border-radius: 5px; padding: 5px 12px; cursor: pointer; font-family: var(--cond); font-weight: 600; font-size: 14px; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
.scrim { position: fixed; inset: 0; background: var(--bg); display: grid; place-items: center; padding: 16px; z-index: 30; }
.dialog { padding: 16px; width: min(520px, 100%); display: grid; gap: 12px; }
.dialog h2 { font-size: 14px; color: var(--ink); }
.dialog .actions { display: flex; justify-content: flex-end; }
body.stale .strip, body.stale .panels { filter: grayscale(1); opacity: 0.55; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""

#: The wl.works mark, as the mockup draws it. No `xmlns`: an inline SVG in an HTML
#: document needs none, and the page names no other host, not even as a namespace.
_LOGO = (
    '<svg viewBox="0 0 395.67 147.54" role="img" aria-label="wl.works">'
    '<circle cx="130.40" cy="34.98" r="11" fill="currentColor"/>'
    '<circle cx="97.40" cy="11.00" r="11" fill="currentColor"/>'
    '<circle cx="56.60" cy="11.00" r="11" fill="currentColor"/>'
    '<circle cx="23.60" cy="34.98" r="11" fill="#C9187B"/>'
    '<circle cx="11.00" cy="73.77" r="11" fill="currentColor"/>'
    '<circle cx="23.60" cy="112.56" r="11" fill="currentColor"/>'
    '<rect x="45.6" y="125.54" width="22" height="22" fill="currentColor"/>'
    '<circle cx="97.40" cy="136.54" r="11" fill="currentColor"/>'
    '<text x="71" y="112.77" font-family="Newsreader, Georgia, serif" font-size="72" '
    'font-weight="700" letter-spacing="-1.44" fill="currentColor">w'
    '<tspan font-style="italic">l</tspan>'
    '<tspan style="fill: var(--wl-muted)">.works</tspan></text></svg>'
)

#: **The page's whole script, and all it does** (spec §4.3, §4.4): open the event
#: stream, swap each fragment into the element with its id, run the stale timer while
#: more frames are due, close the stream on the ✕, and reconnect. `EventSource`
#: reconnects on its own after a dropped connection, and `wlx serve` sends a full
#: render first on every new stream, so a reconnect re-renders in full. Everything
#: worth testing is in Python; this is small enough to read.
_SCRIPT = """
(function () {
  "use strict";
  var body = document.body;
  var staleMs = Number(body.getAttribute("data-stale-after")) * 1000;
  var source = null;
  var last = Date.now();
  var live = false;
  var lost = false;
  var closed = false;
  function el(id) { return document.getElementById(id); }
  function say(text, tone) {
    var banner = el("stream");
    banner.textContent = text || "";
    banner.className = "banner " + (tone || "");
    banner.hidden = !text;
  }
  function onFrame(event) {
    var payload = JSON.parse(event.data);
    Object.keys(payload.frags).forEach(function (id) {
      var node = el(id);
      if (node) { node.innerHTML = payload.frags[id]; }
    });
    live = payload.live;
    last = Date.now();
    lost = false;
    body.classList.remove("stale");
    say("");
  }
  function open() {
    closed = false;
    lost = false;
    el("gone").hidden = true;
    source = new EventSource("/events");
    source.addEventListener("frame", onFrame);
    source.onerror = function () {
      if (closed) { return; }
      lost = true;
      say("stream lost", "crit");
      if (source.readyState === EventSource.CLOSED) {
        setTimeout(function () { if (!closed && lost) { open(); } }, 3000);
      }
    };
  }
  setInterval(function () {
    if (closed || lost || !live) { return; }
    var age = Math.floor((Date.now() - last) / 1000);
    if (age * 1000 >= staleMs) {
      body.classList.add("stale");
      say("stream stale · last frame " + age + " s ago", "warn");
    }
  }, 1000);
  el("close").addEventListener("click", function () {
    closed = true;
    if (source) { source.close(); }
    say("");
    el("gone").hidden = false;
  });
  el("reconnect").addEventListener("click", function () {
    if (source) { source.close(); }
    open();
  });
  open();
})();
"""


def page(parts: dict[str, str], *, stale_after_s: float, nonce: str) -> str:
    """The whole document, every pane already rendered into it, so it reads before
    its stream has opened (spec §4.3).

    `parts` is `fragments(...)`; each fills the element whose id is its key, the id
    the stream's events swap by. A missing key raises `KeyError`: a page with a pane
    left blank is a bug to see, not a page to serve. `nonce` is the one in the
    Content-Security-Policy `wlx serve` sends with this response; the one script
    carries it. `stale_after_s` goes to the script as `data-stale-after`.

    **Nothing here writes** (spec §4.2): two buttons -- close this page's stream, and
    reconnect it -- and four radio inputs that choose a tab.
    """
    p = {key: parts[key] for key in FRAGMENT_IDS}
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>expcontroller console</title>
<style>{_FONT_FACES}{_CSS}</style>
</head>
<body data-stale-after="{stale_after_s:g}">
<div class="wrap">
  <header class="head glass">
    <span class="logo">{_LOGO}<span class="app">expcontroller</span></span>
    <span id="state">{p['state']}</span>
    <div class="id" id="head-id">{p['head-id']}</div>
    <span class="spacer"></span>
    <span class="presence" id="presence">{p['presence']}</span>
    <button class="xbtn" id="close" type="button" aria-label="close this page's stream" title="close this page's stream · the session keeps running on the box"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
  </header>
  <div class="strip glass" role="region" aria-label="animal" id="strip">{p['strip']}</div>
  <div class="banner" id="stream" role="status" hidden></div>
  <div class="banners" id="banners">{p['banners']}</div>
  <div class="shell">
    <div class="main">
      <input type="radio" name="tab" id="t-runtime" checked>
      <input type="radio" name="tab" id="t-task">
      <input type="radio" name="tab" id="t-setup">
      <input type="radio" name="tab" id="t-end">
      <div class="tabs" aria-label="console sections">
        <label class="tab" for="t-runtime">Runtime</label>
        <label class="tab" for="t-task">Task parameters</label>
        <label class="tab" for="t-setup">Setup</label>
        <label class="tab" for="t-end">End of session</label>
      </div>
      <div class="panels">
        <div class="tabpanel" id="tp-runtime">
          <section class="panel glass"><div class="top"><h2>Trials</h2></div><div id="rt-trials">{p['rt-trials']}</div></section>
          <section class="panel glass"><div class="top"><h2>This run</h2></div><div id="rt-work">{p['rt-work']}</div></section>
          <div class="cols c3">
            <div class="stack">
              <section class="panel glass"><div class="top"><h2>Still needed</h2></div><div id="rt-need">{p['rt-need']}</div></section>
              <section class="panel glass"><div class="top"><h2>Wrong?</h2></div><div id="rt-wrong">{p['rt-wrong']}</div></section>
            </div>
            <div class="stack"><section class="panel glass health"><div class="top"><h2>wl-works sees</h2></div><div id="rt-health">{p['rt-health']}</div></section></div>
            <div class="stack"><section class="panel glass"><div class="top"><h2>Changes</h2></div><div class="feed" id="rt-changes">{p['rt-changes']}</div></section></div>
          </div>
        </div>
        <div class="tabpanel" id="tp-task"><section class="panel glass"><div class="top"><h2>Task parameters</h2><span class="sub">read-only</span></div><div class="params" id="params">{p['params']}</div></section></div>
        <div class="tabpanel" id="tp-setup"><section class="panel glass"><div class="top"><h2>Setup</h2><span class="sub">read-only</span></div><div id="setup">{p['setup']}</div></section></div>
        <div class="tabpanel" id="tp-end"><section class="panel glass"><div class="top"><h2>End of session</h2><span class="sub">read-only</span></div><div id="end">{p['end']}</div></section></div>
      </div>
    </div>
    <aside class="aside" aria-label="always shown">
      <section class="panel glass"><div class="top"><h2>Replica</h2><span class="later">V11</span></div><div class="screen">replica · V11</div></section>
      <section class="panel glass"><div class="top"><h2>Subject display</h2></div><div class="screen">subject display · no source yet</div></section>
      <div class="duo">
        <section class="panel glass"><h2>Sound</h2><span class="nm">sound · not measured</span></section>
        <section class="panel glass"><h2>Display</h2><span class="nm">display · not measured</span></section>
      </div>
    </aside>
  </div>
</div>
<div class="scrim" id="gone" role="dialog" aria-modal="true" aria-labelledby="gone-h" hidden>
  <div class="dialog glass">
    <h2 id="gone-h">Disconnected</h2>
    <p>disconnected · the session keeps running on the box</p>
    <div class="actions"><button class="btn primary" id="reconnect" type="button">reconnect</button></div>
  </div>
</div>
<script nonce="{_e(nonce)}">{_SCRIPT}</script>
</body>
</html>
"""
```

- [ ] **Step 6: Run the tests, then check the script parses**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_web.py`
Expected: all pass.

If `node` is on `PATH`, check the script is valid JavaScript (the suite cannot):

```bash
python -c "from wl_expcontroller.web import _SCRIPT; print(_SCRIPT)" > "${TMPDIR:-/tmp}/wlx-console.js"
node --check "${TMPDIR:-/tmp}/wlx-console.js" && echo "script parses"
```

Expected: `script parses`. With no `node`, Task 13's browser check is where the script is first run; say so in the task report.

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add wl_expcontroller/web.py wl_expcontroller/fonts tests/test_web.py pyproject.toml docs/design/decisions/ADR-0004-license.md
git commit -m "Assemble the read-only console page, with the wl-works fonts bundled and licensed"
```

Body: the fonts' sources and license verification (URLs, date), and that they ship under ADR-0004's 2026-09-26 amendment (PI): unmodified OFL-1.1 fonts, each family's `OFL.txt` beside them.

---
### Task 9: The hub — the latest frame, bounded queues, trials per minute, presence

**Why:** spec §2 and §4.1. A telemetry thread keeps the latest frame; each browser gets a bounded queue that drops its oldest frames when it falls behind; trials per minute is derived by `wlx serve` from `trial_index` over the frames of the last five minutes; presence counts who is watching. The hub is that state, with no socket in it, so all of it is tested without a network.

**Files:**
- Create: `wl_expcontroller/serve.py` (this task: the module docstring, the constants, `Hub`, `_put_dropping_oldest`, `CLOSED`)
- Create: `tests/test_serve.py`
- Modify: `tools/mutation_gate.py` (`"serve": "None"` in `RETURNS`)

**Interfaces:**
- Consumes: Task 4's `Telemetry`; Task 7's `web.View`.
- Produces:
  - `serve.DEFAULT_STALE_AFTER_S = 30.0`, `serve.QUEUE_DEPTH = 8`, `serve.RATE_WINDOW_S = 300.0`, `serve.RATE_SAMPLE_S = 1.0`, `serve.CLOSED` (a sentinel object).
  - `serve.Hub(*, wall: Callable[[], float] = time.time, mono: Callable[[], float] = time.monotonic)` with:
    - `offer(frame: Telemetry) -> None`
    - `reject(why: str) -> None`
    - `trials_per_min() -> float | None`
    - `snapshot(*, on_box: bool, stale_after_s: float) -> tuple[Telemetry | None, web.View]`
    - `subscribe(*, on_box: bool) -> queue.Queue`
    - `unsubscribe(subscriber: queue.Queue) -> None`
    - `viewers() -> tuple[int, int]` — `(on the box, from the LAN)`
    - `take(subscriber: queue.Queue, timeout: float) -> Telemetry | None | object` — the newest item waiting (a frame, `None` when a refusal woke the stream before any frame, or `CLOSED`); raises `queue.Empty` after `timeout`
    - `close() -> None`
  Tasks 10 and 11 use every one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_serve.py`:

```python
"""`wlx serve` (P4d-2b slice b1): the hub, the HTTP surface, and the whole process.

Sim first: the end-to-end test runs a real `wlx run --link` in the simulator and a
real `wlx serve` on loopback, and reads the page's event stream the way a browser
would. Every socket here has a client timeout, so a broken server fails a test in
seconds rather than hanging the suite (and the mutation sweep) for 300.
"""

from __future__ import annotations

import queue

import pytest

from _frames import frame
from wl_expcontroller.serve import CLOSED, QUEUE_DEPTH, Hub


class _Clock:
    """A clock a test sets by hand."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _hub(mono: _Clock | None = None) -> Hub:
    return Hub(wall=_Clock(1_700_000_042.0), mono=mono or _Clock(0.0))


# --- the hub (Task 9) ------------------------------------------------------------


def test_a_hub_with_no_frame_has_nothing_to_show():
    found, seen = _hub().snapshot(on_box=True, stale_after_s=30.0)

    assert found is None
    assert seen.frame_age_s is None
    assert seen.trials_per_min is None
    assert seen.now == 1_700_000_042.0


def test_the_latest_frame_is_kept_with_its_age():
    mono = _Clock(10.0)
    hub = _hub(mono)

    hub.offer(frame(trial_index=3))
    mono.t = 25.0
    found, seen = hub.snapshot(on_box=True, stale_after_s=30.0)

    assert found.trial_index == 3
    assert seen.frame_age_s == 15.0
    assert seen.stale_after_s == 30.0


def test_trials_per_minute_is_trials_over_the_time_between_frames():
    """Spec §4.1: derived here, from `trial_index` and when frames arrived."""
    mono = _Clock(0.0)
    hub = _hub(mono)

    hub.offer(frame(trial_index=0))
    mono.t = 30.0
    hub.offer(frame(trial_index=30))

    assert hub.trials_per_min() == 60.0


def test_one_frame_derives_no_rate():
    hub = _hub()
    hub.offer(frame(trial_index=5))

    assert hub.trials_per_min() is None


def test_the_rate_forgets_frames_older_than_five_minutes():
    """Across all three frames the rate would be 160 trials in 460 s; over the last
    five minutes it is 60 trials in 60 s."""
    mono = _Clock(0.0)
    hub = _hub(mono)

    hub.offer(frame(trial_index=0))
    mono.t = 400.0
    hub.offer(frame(trial_index=100))
    mono.t = 460.0
    hub.offer(frame(trial_index=160))

    assert hub.trials_per_min() == 60.0


def test_a_new_session_restarts_the_rate():
    """A second `wlx run` on the same link is a new session, and a rate across two
    would describe neither."""
    mono = _Clock(0.0)
    hub = _hub(mono)
    hub.offer(frame(session_id="2027-01-14_01", trial_index=0))
    mono.t = 60.0
    hub.offer(frame(session_id="2027-01-14_01", trial_index=60))

    mono.t = 61.0
    hub.offer(frame(session_id="2027-01-14_02", trial_index=0))
    assert hub.trials_per_min() is None

    mono.t = 91.0
    hub.offer(frame(session_id="2027-01-14_02", trial_index=15))
    assert hub.trials_per_min() == 30.0


def test_a_trial_count_that_goes_back_restarts_the_rate():
    mono = _Clock(0.0)
    hub = _hub(mono)
    hub.offer(frame(trial_index=50))
    mono.t = 10.0
    hub.offer(frame(trial_index=3))

    assert hub.trials_per_min() is None


def test_a_fast_publisher_cannot_grow_the_rate_window():
    """A simulator publishes far faster than a rig; the window keeps at most one point
    a second however many frames arrive."""
    mono = _Clock(0.0)
    hub = _hub(mono)

    for n in range(10_000):
        mono.t = n * 0.001
        hub.offer(frame(trial_index=n))

    assert len(hub._points) <= 11
    assert round(hub.trials_per_min()) == 60_000


def test_a_stream_that_falls_behind_keeps_only_the_newest_frames():
    """Review Focus 4: a tab that stops reading never holds up the telemetry thread
    and never grows -- its oldest frames go."""
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)

    for n in range(20):
        hub.offer(frame(trial_index=n))

    kept = [subscriber.get_nowait().trial_index for _ in range(subscriber.qsize())]
    assert kept == list(range(20 - QUEUE_DEPTH, 20))


def test_take_renders_only_the_newest_frame_waiting():
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)
    for n in range(3):
        hub.offer(frame(trial_index=n))

    assert hub.take(subscriber, timeout=1.0).trial_index == 2
    with pytest.raises(queue.Empty):
        hub.take(subscriber, timeout=0.01)


def test_closing_the_hub_ends_every_stream_including_later_ones():
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)
    hub.offer(frame())

    hub.close()
    hub.offer(frame(trial_index=99))

    assert hub.take(subscriber, timeout=1.0) is CLOSED
    assert hub.take(hub.subscribe(on_box=False), timeout=1.0) is CLOSED
    assert hub.viewers() == (0, 0)


def test_viewers_are_counted_by_where_they_are():
    hub = _hub()
    hub.subscribe(on_box=True)
    lan = hub.subscribe(on_box=False)
    hub.subscribe(on_box=False)

    assert hub.viewers() == (1, 2)
    assert hub.snapshot(on_box=True, stale_after_s=30.0)[1].lan_viewers == 2

    hub.unsubscribe(lan)
    assert hub.viewers() == (1, 1)


def test_a_refused_frame_wakes_every_stream_and_a_good_one_clears_it():
    """Review Focus 1, in the hub: a frame that could not be used is said on every
    open page at once, and the last good frame -- here none -- is what is shown."""
    hub = _hub()
    subscriber = hub.subscribe(on_box=True)

    hub.reject("a telemetry frame carried schema 6")

    assert hub.take(subscriber, timeout=1.0) is None
    found, seen = hub.snapshot(on_box=True, stale_after_s=30.0)
    assert found is None
    assert seen.rejected == "a telemetry frame carried schema 6"

    hub.offer(frame())
    assert hub.snapshot(on_box=True, stale_after_s=30.0)[1].rejected is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py`
Expected: collection error — `ModuleNotFoundError: No module named 'wl_expcontroller.serve'`.

- [ ] **Step 3: Implement**

Create `wl_expcontroller/serve.py`:

```python
"""`wlx serve` -- the browser console's process (P4d-2b slice b1).

Spec: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §1-§4.

**Its own process, beside `taskd` and never inside it** (S9a §7: the hot loop never
serves a request). It holds one `link.ZmqConsole`, keeps the latest frame, and serves
three things over the stdlib `ThreadingHTTPServer` -- the stack wl-preproc's responder
already runs, so no new dependency:

- `GET /` -- the page, every pane rendered in Python (`web.py`).
- `GET /events` -- server-sent events: one full render on connect, then the fragments
  that changed, once per frame this browser keeps up with.
- `GET /health` -- `health.py`'s body for wl-works, behind a bearer token.

Everything else is 404 or 405, as JSON, never the stdlib's HTML page. **b1 has no
`POST`**: nothing on the page writes; writes from the box are slice b2's.

**Restarting it changes nothing in `taskd`** (spec §2): it only ever reads the PUB
socket, and telemetry is lossy by design (S9a §9).

**Threads, and what each owns.** The telemetry thread (`Server._listen`) owns the
`ZmqConsole` -- both of its sockets, created, read and closed there -- so each ZMQ
socket has one owning thread. b1 sends no command, so the REQ socket is connected and
never used; slice b2 moves it to a command thread of its own. Each browser's
`/events` runs on the HTTP server's thread for that connection, reading its own
bounded queue from the `Hub`.

**No timing claim is made here.** `DEFAULT_STALE_AFTER_S` is a display choice (spec
§3); the queue depth, the rate window's sampling, the keepalive and the receive
timeout are housekeeping. None is a measurement of this system.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Callable

from wl_expcontroller import link as _link
from wl_expcontroller import web as _web

#: Seconds without a frame, while more are due, before the page greys and `/health`
#: says `degraded`. A display choice (spec §3), not a measurement.
DEFAULT_STALE_AFTER_S = 30.0
#: How many frames one browser's queue holds before its oldest is dropped (spec §2).
#: Small on purpose: telemetry is latest-wins, and a stream renders only the newest
#: frame it finds waiting (`Hub.take`).
QUEUE_DEPTH = 8
#: Trials per minute is read over the frames of the last five minutes (spec §4.1)...
RATE_WINDOW_S = 300.0
#: ...sampled at most once a second, so the window holds a few hundred points however
#: fast a simulator publishes.
RATE_SAMPLE_S = 1.0

#: What `Hub.take` returns once the hub is closed: the stream ends.
CLOSED = object()


def _put_dropping_oldest(subscriber: queue.Queue, item: object) -> None:
    """Queue `item`, dropping the oldest item waiting if the queue is full (spec §2): a
    browser that falls behind loses its oldest frames, never the newest, and never
    holds up the thread that offers them."""
    while True:
        try:
            subscriber.put_nowait(item)
            return
        except queue.Full:
            try:
                subscriber.get_nowait()
            except queue.Empty:
                pass


class Hub:
    """The latest frame, the rate window, and every open stream's queue (spec §2).

    `offer` and `reject` are called by the telemetry thread; everything else by HTTP
    handler threads. One lock guards the frame, the window and the table of
    subscribers; each queue is thread-safe on its own. `wall` and `mono` are
    injectable so that no test reads a real clock.
    """

    def __init__(
        self,
        *,
        wall: Callable[[], float] = time.time,
        mono: Callable[[], float] = time.monotonic,
    ) -> None:
        self._wall = wall
        self._mono = mono
        self._lock = threading.Lock()
        self._frame: _link.Telemetry | None = None
        #: When `_frame` arrived, on `mono`.
        self._received: float | None = None
        #: `(mono, trial_index)` sampled at most every `RATE_SAMPLE_S`, within
        #: `RATE_WINDOW_S` of the newest frame.
        self._points: deque = deque()
        #: The newest frame's `(mono, trial_index)`, sampled or not.
        self._newest: tuple[float, int] | None = None
        self._rejected: str | None = None
        #: Each open stream's queue, and whether it is on the box.
        self._subscribers: dict[queue.Queue, bool] = {}
        self._closed = False

    def offer(self, frame: _link.Telemetry) -> None:
        """Keep `frame` as the latest and hand it to every open stream.

        The rate window restarts when the session changes or its trial count goes
        back: a new `wlx run` on the same link is a new session, and a rate across two
        would describe neither. A good frame clears a refusal (`reject`).
        """
        now = self._mono()
        with self._lock:
            previous = self._frame
            if (
                previous is None
                or previous.session_id != frame.session_id
                or frame.trial_index < previous.trial_index
            ):
                self._points.clear()
            if not self._points or now - self._points[-1][0] >= RATE_SAMPLE_S:
                self._points.append((now, frame.trial_index))
            while now - self._points[0][0] > RATE_WINDOW_S:
                self._points.popleft()
            self._newest = (now, frame.trial_index)
            self._frame, self._received, self._rejected = frame, now, None
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, frame)

    def reject(self, why: str) -> None:
        """Say that a frame arrived and could not be used, and wake every stream to
        show it (`Server._listen`). The last good frame stays: a console that cannot
        read one frame shows what it last could, beside the reason -- never a guess."""
        with self._lock:
            self._rejected = why
            latest = self._frame
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, latest)

    def _rate(self) -> float | None:
        """Trials per minute over the window. The caller holds the lock."""
        if not self._points or self._newest is None:
            return None
        (t0, n0), (t1, n1) = self._points[0], self._newest
        if t1 <= t0:
            return None
        return 60.0 * (n1 - n0) / (t1 - t0)

    def trials_per_min(self) -> float | None:
        """Derived here, from `trial_index` and when frames arrived (spec §4.1); `None`
        until two frames a moment apart exist. **Bounds nothing**, and the page says
        it is derived."""
        with self._lock:
            return self._rate()

    def snapshot(
        self, *, on_box: bool, stale_after_s: float
    ) -> tuple[_link.Telemetry | None, _web.View]:
        """The latest frame and the `View` a render of it needs, read together."""
        now_mono, now_wall = self._mono(), self._wall()
        with self._lock:
            latest = self._frame
            age = None if self._received is None else now_mono - self._received
            rate = self._rate()
            lan = sum(1 for box in self._subscribers.values() if not box)
            rejected = self._rejected
        return latest, _web.View(
            now=now_wall,
            frame_age_s=age,
            stale_after_s=stale_after_s,
            trials_per_min=rate,
            on_box=on_box,
            lan_viewers=lan,
            rejected=rejected,
        )

    def subscribe(self, *, on_box: bool) -> queue.Queue:
        """A new stream's bounded queue. After `close`, one that is already closed."""
        subscriber: queue.Queue = queue.Queue(maxsize=QUEUE_DEPTH)
        with self._lock:
            if self._closed:
                subscriber.put_nowait(CLOSED)
                return subscriber
            self._subscribers[subscriber] = on_box
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self._subscribers.pop(subscriber, None)

    def viewers(self) -> tuple[int, int]:
        """How many streams are open: `(on the box, from the LAN)`."""
        with self._lock:
            box = sum(1 for on in self._subscribers.values() if on)
            return box, len(self._subscribers) - box

    def take(self, subscriber: queue.Queue, timeout: float) -> object:
        """The newest item waiting on `subscriber` -- a frame, `None` when a refusal
        woke it before any frame arrived, or `CLOSED` -- waiting up to `timeout`
        seconds and raising `queue.Empty` after that.

        **Older frames are skipped, not rendered**: telemetry is latest-wins, so a
        browser that fell behind catches up in one render rather than replaying what
        it missed.
        """
        item = subscriber.get(timeout=timeout)
        while item is not CLOSED:
            try:
                item = subscriber.get_nowait()
            except queue.Empty:
                break
        return item

    def close(self) -> None:
        """End every open stream, and any opened after this. The table is emptied so
        no later frame can push a stream's `CLOSED` out of its queue."""
        with self._lock:
            self._closed = True
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, CLOSED)
```

In `tools/mutation_gate.py`, add `"serve": "None",` to `RETURNS` (after `"web": "None",`).

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py tests/test_mutation_gate.py`
Expected: all pass.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/serve.py tests/test_serve.py tools/mutation_gate.py
git commit -m "Keep the latest frame for wlx serve, with bounded per-browser queues and a derived rate"
```

---
### Task 10: The HTTP surface — routes, the bearer token, and the event stream

**Why:** spec §2 and §4.2–§4.4. `GET /`, `GET /events`, `GET /health` and — the fonts being bundled (PI, 2026-09-26, spec §4.2) — `GET /fonts/<file>` for each of `web.FONTS` are served; everything else is 404 or 405, as JSON, with no stdlib error page; b1 has no `POST`. A font is found by its exact published path in a fixed table, never by joining a request's path onto a directory, so there is no path to traverse. `/health` follows wl-preproc's `responder/handler.py` (read 2026-09-26): `Authorization: Bearer`, the scheme matched case-insensitively, `hmac.compare_digest` on UTF-8 bytes, one identical `401` for a missing, malformed or wrong credential, no interpreter version on any response, and a socket timeout on every request.

**One place where this server answers differently from wl-preproc's, and why.** wl-preproc turns the stdlib's `501` for an unknown method into `401`, because every one of its paths needs the token and a method name must not leak before authentication. Here `/` and `/events` are open to the LAN (spec §2), so an unknown method is a routing fact: `405` on a known path, `404` on any other. Only `GET /health` is behind the token.

**Files:**
- Modify: `wl_expcontroller/serve.py` (add the constants, `on_box`, `event`, `_csp`, `make_handler`)
- Test: `tests/test_serve.py`

**Interfaces:**
- Consumes: Task 9's `Hub`, `CLOSED`; Task 7/8's `web.fragments`, `web.page`, `web.FRAGMENT_IDS`, `web.FONTS`, `web.font_bytes`; Task 6's `health.response`, `health.expects_frames`.
- Produces:
  - `serve.KEEPALIVE_S = 15.0`, `serve.RETRY_MS = 3000`, `serve.REQUEST_TIMEOUT_S = 30.0`.
  - `serve.on_box(host: str) -> bool`.
  - `serve.event(payload: dict) -> bytes` — one `event: frame` with a one-line JSON `data:`.
  - `serve.make_handler(hub: Hub, *, token: str, stale_after_s: float, keepalive_s: float = KEEPALIVE_S) -> type[BaseHTTPRequestHandler]` — raises `ValueError` for an empty or non-ASCII token.
  - `GET /fonts/<file>` for each `web.FONTS` entry: `200`, `Content-Type: font/woff2`, `Cache-Control: max-age=86400`, the bytes `web.font_bytes` reads; any other `/fonts/...` path is `404`. The page's Content-Security-Policy includes `font-src 'self'`.
  - The stream's contract with the page: after a `retry:` line, one `frame` event whose `frags` holds every `FRAGMENT_IDS` entry, then one per frame taken, holding only the fragments that changed, each with `"live": health.expects_frames(frame)`; a `: keepalive` comment every `keepalive_s` seconds without a frame.
  Task 11's `Server` builds the handler with `make_handler`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_serve.py`, extend the imports to:

```python
import http.client
import json
import os
import queue
import socket
import threading
import time
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

from _frames import frame
from wl_expcontroller.serve import CLOSED, QUEUE_DEPTH, Hub, make_handler, on_box
from wl_expcontroller.web import FONTS, FRAGMENT_IDS, font_bytes

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts.protocol import HealthResponse
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}); the "
            f"/health served over HTTP is checked against their HealthResponse"
        ) from exc
    HealthResponse = None

_contract = pytest.mark.skipif(
    HealthResponse is None, reason="wl-preproc checkout not beside this repo"
)

TOKEN = "t0ken-for-tests"
```

and append:

```python
# --- the HTTP surface (Task 10) ---------------------------------------------------


@contextmanager
def _served(hub: Hub, *, keepalive_s: float = 15.0, stale_after_s: float = 30.0):
    """The handler on a real loopback socket, with no ZMQ anywhere."""
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(
            hub, token=TOKEN, stale_after_s=stale_after_s, keepalive_s=keepalive_s
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        hub.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(port: int, method: str, path: str, headers: dict | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def _raw(port: int, data: bytes) -> bytes:
    """Bytes a browser would never send, and everything the server says back."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(data)
        chunks = []
        while chunk := sock.recv(4096):
            chunks.append(chunk)
    return b"".join(chunks)


def _events(response):
    """Each `frame` event's payload, as a browser's `EventSource` would dispatch it:
    comments and the `retry:` line are skipped."""
    name, data = None, None
    while True:
        line = response.readline()
        if not line:
            return
        line = line.decode("utf-8").rstrip("\n")
        if line == "":
            if name == "frame" and data is not None:
                yield json.loads(data)
            name, data = None, None
        elif line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            data = line[len("data: ") :]


@contextmanager
def _stream(port: int):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", "/events")
    response = connection.getresponse()
    try:
        yield response
    finally:
        response.close()
        connection.close()


def test_the_page_is_served_with_every_pane_and_its_own_nonce():
    hub = _hub()
    hub.offer(frame())
    with _served(hub) as port:
        status, headers, body = _request(port, "GET", "/")

    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    policy = headers["Content-Security-Policy"]
    nonce = policy.split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'<script nonce="{nonce}">'.encode() in body
    assert "default-src 'none'" in policy and "connect-src 'self'" in policy
    assert "font-src 'self'" in policy
    assert b'id="strip"' in body and b"2027-01-14_01" in body
    assert b"http://" not in body and b"https://" not in body


def test_every_bundled_font_is_served_with_its_type():
    """The page's fonts come from this box (PI, 2026-09-26): each face `web.FONTS`
    declares, as `font/woff2`, byte for byte the file the package carries."""
    hub = _hub()
    with _served(hub) as port:
        for font in FONTS:
            status, headers, body = _request(port, "GET", f"/fonts/{font.file}")
            assert status == 200, font.file
            assert headers["Content-Type"] == "font/woff2", font.file
            assert body == font_bytes(font), font.file


def test_a_font_path_that_is_not_a_bundled_name_is_404():
    """Exact names from a fixed table: nothing is joined onto a directory, so a `..`
    has nowhere to go, and a license file or a module beside the fonts is not served."""
    hub = _hub()
    with _served(hub) as port:
        for path in (
            "/fonts/../web.py",
            "/fonts/../../pyproject.toml",
            "/fonts/%2e%2e/web.py",
            "/fonts/ibm-plex-sans/OFL.txt",
            f"/fonts/ibm-plex-sans/{FONTS[0].file}",
            "/fonts/Unknown.woff2",
            f"/fonts/{FONTS[0].file}?v=1",
            "/fonts/",
            "/fonts",
        ):
            assert _request(port, "GET", path)[::2] == (
                404,
                b'{"error": "not found"}',
            ), path
        assert _request(port, "POST", f"/fonts/{FONTS[0].file}")[0] == 405


def test_health_needs_the_token_and_every_failure_looks_the_same():
    """wl-preproc's rule: missing, malformed and wrong are one path to one `401`, so
    which part was wrong cannot be read off the response."""
    hub = _hub()
    with _served(hub) as port:
        answers = {
            _request(port, "GET", "/health", headers)[::2]
            for headers in (
                {},
                {"Authorization": "Bearer wrong"},
                {"Authorization": f"Basic {TOKEN}"},
                {"Authorization": "Bearer"},
                {"Authorization": "Bearer "},
            )
        }

    assert answers == {(401, b'{"error": "unauthorized"}')}


def test_health_answers_the_token_whatever_the_schemes_case():
    hub = _hub()
    hub.offer(frame())
    with _served(hub) as port:
        for scheme in ("Bearer", "bearer"):
            status, headers, body = _request(
                port, "GET", "/health", {"Authorization": f"{scheme} {TOKEN}"}
            )
            assert status == 200, scheme
            assert headers["Content-Type"] == "application/json"
            assert set(json.loads(body)) == {"verdict", "readings", "actions"}


def test_an_unknown_path_is_404_as_json():
    hub = _hub()
    with _served(hub) as port:
        for path in ("/nope", "/favicon.ico", "/health/", "/events/x"):
            assert _request(port, "GET", path)[::2] == (
                404,
                b'{"error": "not found"}',
            ), path


def test_a_known_path_with_the_wrong_method_is_405_and_b1_takes_no_post():
    hub = _hub()
    with _served(hub) as port:
        assert _request(port, "POST", "/")[0] == 405
        assert _request(port, "POST", "/events")[0] == 405
        assert _request(port, "PUT", "/health")[0] == 405
        assert _request(port, "DELETE", "/")[0] == 405
        assert _request(port, "POST", "/commands")[0] == 404


def test_a_method_the_stdlib_does_not_know_gets_json_not_its_html_page():
    hub = _hub()
    with _served(hub) as port:
        known = _raw(port, b"BREW / HTTP/1.0\r\n\r\n")
        unknown = _raw(port, b"BREW /nope HTTP/1.0\r\n\r\n")

    assert known.startswith(b"HTTP/1.0 405")
    assert known.endswith(b'{"error": "method not allowed"}')
    assert unknown.startswith(b"HTTP/1.0 404")
    assert b"<" not in known + unknown


def test_a_malformed_request_gets_no_html_and_no_echo():
    hub = _hub()
    with _served(hub) as port:
        answer = _raw(port, b"GARBAGE\r\n\r\n")

    assert b'"bad request"' in answer
    assert b"<" not in answer
    assert b"GARBAGE" not in answer


def test_no_response_names_the_interpreter():
    hub = _hub()
    with _served(hub) as port:
        for path in ("/", "/nope", "/health"):
            server = _request(port, "GET", path)[1].get("Server", "")
            assert "Python" not in server and "BaseHTTP" not in server, path


def test_a_stream_opens_with_a_full_render_then_sends_what_changed():
    """Spec §4.3: one full render on connect, then a fragment per frame -- here, only
    the fragments that differ from what this browser already holds."""
    hub = _hub()
    with _served(hub) as port, _stream(port) as response:
        assert response.getheader("Content-Type") == "text/event-stream"
        events = _events(response)

        first = next(events)
        assert tuple(first["frags"]) == FRAGMENT_IDS
        assert first["live"] is False
        assert 'data-state="none"' in first["frags"]["state"]

        hub.offer(frame(trial_index=5))
        second = next(events)
        assert second["live"] is True
        assert 'data-trial="5"' in second["frags"]["head-id"]

        hub.offer(frame(trial_index=6))
        third = next(events)
        assert 'data-trial="6"' in third["frags"]["head-id"]
        assert "setup" not in third["frags"], "an unchanged pane was sent again"


def test_a_stream_on_the_box_says_so():
    hub = _hub()
    with _served(hub) as port, _stream(port) as response:
        first = next(_events(response))

    assert first["frags"]["presence"].startswith("<b>this box</b>")


def test_a_quiet_stream_sends_keepalives():
    hub = _hub()
    with _served(hub, keepalive_s=0.05) as port, _stream(port) as response:
        lines = [response.readline() for _ in range(40)]

    assert b": keepalive\n" in lines


def test_closing_the_hub_ends_an_open_stream():
    hub = _hub()
    with _served(hub, keepalive_s=60.0) as port, _stream(port) as response:
        next(_events(response))
        hub.close()
        tail = [response.readline() for _ in range(5)]

    assert tail[-1] == b"", "the stream stayed open after the hub closed"


def test_a_browser_that_goes_away_is_forgotten():
    """Review Focus 4: a closed tab is noticed at the next write, and its queue goes."""
    hub = _hub()
    with _served(hub) as port:
        with _stream(port) as response:
            next(_events(response))
            assert hub.viewers() == (1, 0)
        for n in range(250):
            hub.offer(frame(trial_index=n))
            if hub.viewers() == (0, 0):
                break
            time.sleep(0.02)

        assert hub.viewers() == (0, 0)


def test_the_box_is_a_loopback_peer_and_nothing_else():
    for host in ("127.0.0.1", "127.8.9.10", "::1", "::ffff:127.0.0.1"):
        assert on_box(host), host
    for host in ("192.168.1.50", "10.0.0.7", "::ffff:10.0.0.7", "not an address", ""):
        assert not on_box(host), host


def test_a_handler_refuses_a_token_it_could_not_compare():
    """wl-preproc's `make_handler` refuses a non-ASCII token for its reason:
    `hmac.compare_digest` cannot compare one, so every request would fail, the
    correct one included."""
    for token in ("", "tök"):
        with pytest.raises(ValueError):
            make_handler(_hub(), token=token, stale_after_s=30.0)


@_contract
def test_health_over_http_is_wl_preprocs_health_response():
    """The body as it crosses the wire -- JSON encoding included -- against their
    model, with markup in the frame."""
    hub = _hub()
    hub.offer(frame(session_id="<b>&", stop_kind="operator", stopped_because="<script>"))
    with _served(hub) as port:
        status, _, body = _request(
            port, "GET", "/health", {"Authorization": f"Bearer {TOKEN}"}
        )

    assert status == 200
    assert HealthResponse.model_validate_json(body).verdict == "ok"
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py`
Expected: collection error — `ImportError: cannot import name 'make_handler' from 'wl_expcontroller.serve'`.

- [ ] **Step 3: Implement**

In `wl_expcontroller/serve.py`, extend the imports to:

```python
import hmac
import ipaddress
import json
import queue
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler

from wl_expcontroller import health as _health
from wl_expcontroller import link as _link
from wl_expcontroller import web as _web
```

and append:

```python
#: Seconds between comment lines on a stream with no frame to send. Housekeeping: a
#: browser that went away is found at the next write rather than never.
KEEPALIVE_S = 15.0
#: The reconnection delay the page's `EventSource` is told, in milliseconds.
RETRY_MS = 3000
#: Socket timeout for every request -- wl-preproc's `_REQUEST_TIMEOUT_S`, for its
#: reason: a request that never finishes must not park a thread for good.
REQUEST_TIMEOUT_S = 30.0

#: Each bundled font by the exact path the page asks for it at (`web.FONTS`). A request
#: is looked up here, never joined onto a directory, so there is no path to traverse.
_FONTS = {f"/fonts/{font.file}": font for font in _web.FONTS}
_ROUTES = frozenset({"/", "/events", "/health", *_FONTS})
_UNAUTHORIZED = {"error": "unauthorized"}
#: Fixed bodies, keyed on the status alone and echoing nothing a caller sent
#: (wl-preproc's `_SEND_ERROR_BODIES`).
_ERRORS = {
    400: {"error": "bad request"},
    404: {"error": "not found"},
    405: {"error": "method not allowed"},
    414: {"error": "request line too long"},
    431: {"error": "request header fields too large"},
    505: {"error": "http version not supported"},
}
_FALLBACK = {"error": "request rejected"}


def on_box(host: str) -> bool:
    """Whether a peer is this machine: loopback in either family, or an IPv4 loopback
    mapped into IPv6. Anything that does not parse is the LAN."""
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def event(payload: dict) -> bytes:
    """One server-sent event named `frame`. `json.dumps` escapes every newline and
    control character, so the payload is one `data:` line whatever telemetry held."""
    return b"event: frame\ndata: " + json.dumps(payload).encode("utf-8") + b"\n\n"


def _csp(nonce: str) -> str:
    """The page's Content-Security-Policy: its one script by nonce, inline styles (the
    bar widths), its bundled fonts and the event stream from this origin, and nothing
    else -- no request leaves the box from this page. Defense beneath `web._e`, not
    instead of it."""
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
        f"font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
        f"frame-ancestors 'none'"
    )


def make_handler(
    hub: Hub,
    *,
    token: str,
    stale_after_s: float,
    keepalive_s: float = KEEPALIVE_S,
) -> type[BaseHTTPRequestHandler]:
    """A handler class closing over `hub` and the token, built the way wl-preproc's
    `make_handler` is and for its reason: `BaseHTTPRequestHandler` handles the whole
    request inside `__init__`, so all it needs must already be class attributes.

    Refuses an empty or non-ASCII token before building anything: `hmac.compare_digest`
    cannot compare a non-ASCII `str`, and a handler built from one would refuse every
    request, the correct one included (wl-preproc, review round 2's Minor 7).
    """
    if not token or not token.isascii():
        raise ValueError(
            "the /health bearer token must be non-empty ASCII: hmac.compare_digest "
            "cannot compare anything else, and a handler built from one would refuse "
            "every request, the correct one included"
        )

    class ConsoleHandler(BaseHTTPRequestHandler):
        _hub = hub
        _token = token
        _stale_after_s = stale_after_s
        _keepalive_s = keepalive_s
        # No interpreter version in any `Server` header (wl-preproc's Important 5).
        server_version = ""
        sys_version = ""
        timeout = REQUEST_TIMEOUT_S

        def _authorized(self) -> bool:
            """`Authorization: Bearer <token>`, the scheme matched case-insensitively
            (RFC 7235 §2.1), the token by `hmac.compare_digest` on UTF-8 bytes --
            wl-preproc's `_authorized`. Missing, malformed and wrong take one path."""
            value = self.headers.get("Authorization")
            if value is None:
                return False
            scheme, _, candidate = value.partition(" ")
            if scheme.lower() != "bearer" or not candidate:
                return False
            return hmac.compare_digest(
                candidate.encode("utf-8"), self._token.encode("utf-8")
            )

        def _write(
            self,
            status: int,
            body: bytes,
            content_type: str,
            headers: tuple = (),
            cache: str = "no-store",
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            self._write(status, json.dumps(payload).encode("utf-8"), "application/json")

        def send_error(self, code, message=None, explain=None) -> None:
            """Every error the stdlib raises on its own, as JSON and never its HTML
            page (wl-preproc's `send_error`, read 2026-09-26). `message` and `explain`
            are discarded: the stdlib formats the caller's own bytes into them.

            **An unknown method is 405 on a known path and 404 elsewhere**, where
            wl-preproc answers 401: every one of its paths needs the token, and here
            only `GET /health` does -- the pages are open to the LAN (spec §2).
            """
            if code == 501:
                code = 405 if getattr(self, "path", None) in _ROUTES else 404
            self._send_json(code, _ERRORS.get(code, _FALLBACK))

        def _refuse_method(self) -> None:
            code = 405 if self.path in _ROUTES else 404
            self._send_json(code, _ERRORS[code])

        # Every verb a client commonly sends besides GET. b1 takes no POST at all:
        # nothing on the page writes (spec §4.2).
        do_POST = _refuse_method
        do_PUT = _refuse_method
        do_DELETE = _refuse_method
        do_PATCH = _refuse_method
        do_OPTIONS = _refuse_method
        do_HEAD = _refuse_method
        do_TRACE = _refuse_method

        def do_GET(self) -> None:
            if self.path == "/":
                self._page()
            elif self.path == "/events":
                self._events()
            elif self.path == "/health":
                if not self._authorized():
                    self._send_json(401, _UNAUTHORIZED)
                    return
                self._health()
            elif self.path in _FONTS:
                self._font(_FONTS[self.path])
            else:
                self._send_json(404, _ERRORS[404])

        def _font(self, font) -> None:
            """A bundled font (PI, 2026-09-26: "bundle the fonts"). Cached a day: the
            files change only with the package."""
            self._write(
                200, _web.font_bytes(font), "font/woff2", cache="max-age=86400"
            )

        def _page(self) -> None:
            latest, view = self._hub.snapshot(
                on_box=on_box(self.client_address[0]),
                stale_after_s=self._stale_after_s,
            )
            nonce = secrets.token_urlsafe(16)
            body = _web.page(
                _web.fragments(latest, view),
                stale_after_s=self._stale_after_s,
                nonce=nonce,
            )
            self._write(
                200,
                body.encode("utf-8"),
                "text/html; charset=utf-8",
                (("Content-Security-Policy", _csp(nonce)),),
            )

        def _health(self) -> None:
            latest, view = self._hub.snapshot(
                on_box=False, stale_after_s=self._stale_after_s
            )
            self._send_json(
                200,
                _health.response(
                    latest,
                    frame_age_s=view.frame_age_s,
                    stale_after_s=self._stale_after_s,
                ),
            )

        def _events(self) -> None:
            """One browser's stream (spec §4.3): a full render on connect, then an
            event per frame it keeps up with, until the hub closes or the browser
            goes away."""
            box = on_box(self.client_address[0])
            subscriber = self._hub.subscribe(on_box=box)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(f"retry: {RETRY_MS}\n\n".encode("ascii"))
                sent: dict[str, str] = {}
                latest, _ = self._hub.snapshot(
                    on_box=box, stale_after_s=self._stale_after_s
                )
                self._send_frame(latest, box, sent)
                while True:
                    try:
                        item = self._hub.take(subscriber, timeout=self._keepalive_s)
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        continue
                    if item is CLOSED:
                        return
                    self._send_frame(item, box, sent)
            except OSError:
                # A broken pipe, a reset, or a write that timed out: the browser went
                # away. There is nobody to tell; `finally` forgets it.
                return
            finally:
                self._hub.unsubscribe(subscriber)

        def _send_frame(self, latest, box: bool, sent: dict) -> None:
            """One event: the fragments that differ from what this browser holds --
            all of them on connect -- and whether more frames are due, which is when
            the page's stale timer runs."""
            _, view = self._hub.snapshot(on_box=box, stale_after_s=self._stale_after_s)
            parts = _web.fragments(latest, view)
            changed = {key: html for key, html in parts.items() if sent.get(key) != html}
            sent.update(changed)
            self.wfile.write(
                event({"frags": changed, "live": _health.expects_frames(latest)})
            )

    return ConsoleHandler
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py`
Expected: all pass, the `_contract` test included. Run it three times; the stream tests use threads and must not flake.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/serve.py tests/test_serve.py
git commit -m "Serve the page, its event stream and /health, with wl-preproc's auth rules"
```

Body: names the one deliberate difference from wl-preproc's responder (an unknown method is 404/405 here, not 401) and why.

---
### Task 11: `wlx serve` — the telemetry thread, the server, the command, end to end

**Why:** spec §2 and §4.4. `wlx serve --link PUB,REP --http HOST:PORT --health-token-file PATH [--stale-after SECONDS]` is its own process with one `ZmqConsole` on a telemetry thread. The end-to-end test runs `wlx run --link` in the simulator and `wlx serve` on loopback, reads the event stream, and sees the trial count advance, then the ended state — across a restart of `wlx serve` in between (Review Focus 5).

**Files:**
- Modify: `wl_expcontroller/link.py` (`ZmqConsole(..., receive_timeout_s=5.0)`)
- Modify: `wl_expcontroller/serve.py` (add `RECEIVE_TIMEOUT_S`, `Server`, `read_token`, `parse_link`, `parse_http`, `run`, `_wait`)
- Modify: `wl_expcontroller/cli.py` (the `serve` subparser and its dispatch)
- Test: `tests/test_serve.py`, `tests/test_link.py`
- Modify: `tests/_transport_import_blocker.py`, `tests/test_no_transport_leak.py`

**Interfaces:**
- Consumes: Task 9's `Hub`; Task 10's `make_handler`, `KEEPALIVE_S`; `link.ZmqConsole`, `link.SCHEMA`.
- Produces:
  - `link.ZmqConsole(pub_endpoint: str, req_endpoint: str, settle_s: float = 0.05, receive_timeout_s: float = 5.0)` — `receive_timeout_s` sets the SUB socket's `RCVTIMEO`; the REQ socket keeps 5 s.
  - `serve.RECEIVE_TIMEOUT_S = 0.5`.
  - `serve.Server(*, sub: str, req: str, http: tuple[str, int], token: str, stale_after_s: float = DEFAULT_STALE_AFTER_S, keepalive_s: float = KEEPALIVE_S, receive_timeout_s: float = RECEIVE_TIMEOUT_S)` — binds the HTTP port on construction; `.hub: Hub`; `.address -> tuple[str, int]`; `.start() -> None`; `.close() -> None` (idempotent).
  - `serve.read_token(path: Path) -> str`, `serve.parse_link(text: str) -> tuple[str, str]`, `serve.parse_http(text: str) -> tuple[str, int]` — each raises `SystemExit` with a sentence.
  - `serve.run(args: argparse.Namespace) -> int` — `130` when interrupted; `serve._wait(server: Server) -> None` blocks until interrupted.
  - `wlx serve` on the command line.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_link.py`:

```python
def test_a_console_can_be_given_a_shorter_receive_timeout(zmq_cleanup):
    """P4d-2b b1: `wlx serve`'s telemetry thread looks between receives at whether it
    should stop, so its wait is short. `wlx console` keeps the 5 s it always had."""
    import zmq

    link = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    short = zmq_cleanup(
        ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0, receive_timeout_s=0.05)
    )
    default = zmq_cleanup(ZmqConsole(link.pub_endpoint, link.rep_endpoint, settle_s=0))

    assert short._sub.getsockopt(zmq.RCVTIMEO) == 50
    assert default._sub.getsockopt(zmq.RCVTIMEO) == 5000
    try:
        short.receive()
    except TimeoutError:
        pass
    else:
        raise AssertionError("a console received a frame nobody published")
```

In `tests/test_serve.py`, extend the imports with:

```python
import gc
import re
from dataclasses import replace
from pathlib import Path

from wl_expcontroller import serve
from wl_expcontroller.cli import main
from wl_expcontroller.link import Stop, ZmqConsole, ZmqLink
from wl_expcontroller.serve import Server
```

and append:

```python
# --- the process (Task 11) --------------------------------------------------------

GOOD = "tasks/fixation_detection.py"
ALLOCATION = "tasks/allocation.py"
#: The twelve-hour reference config: a session under it runs until it is stopped.
TWELVE_HOURS = "tasks/twelve_hour_bounds.py"
#: What the fixation task needs set to run headless (as in `test_cli.py`).
_TASK_SETS = [
    "--set", "fix_timeout=4.0",
    "--set", "fix_hold=0.3",
    "--set", "response_window=0.6",
    "--set", "target_hold=0.2",
    "--set", "fix_window=2.0",
    "--set", "target_window=3.0",
    "--set", "target_position=10.0",
]


@pytest.fixture
def server_cleanup():
    """Registers each `Server` a test builds, and stops it at teardown **without
    calling `Server.close`** -- `zmq_cleanup`'s reasoning, for this module's object.

    The mutation harness blanks every function named `close` in `serve.py` at once,
    `Hub.close` and `Server.close` alike. A `Server` left running then holds its
    telemetry thread in a ZMQ receive into interpreter shutdown, and the suite hung for
    the harness's full 300 s (found while this plan was checked, 2026-09-26) -- the
    harness noticing, not a test. With this teardown, the test that checks `close`
    fails in seconds instead.
    """
    started: list = []

    def _register(server):
        started.append(server)
        return server

    yield _register
    for server in started:
        server._stop.set()
        if server._started:
            server._telemetry.join(timeout=5)
            server._http.shutdown()
        server._http.server_close()


def _endpoints(zmq_cleanup) -> tuple[str, str]:
    """A free PUB/REP pair on loopback, bound by a throwaway link and released."""
    probe = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    pub, rep = probe.pub_endpoint, probe.rep_endpoint
    probe.close()
    return pub, rep


def _advancing(server: Server, count: int = 2) -> list[int]:
    """Trial numbers from `server`'s event stream until `count` increasing ones are
    seen: the trial count advancing, as a person watching would see it. Bounded by
    the stream's 10 s read timeout and by a count of events, never by hope."""
    seen: list[int] = []
    with _stream(server.address[1]) as response:
        for _, payload in zip(range(20_000), _events(response)):
            found = re.search(
                r'data-trial="(\d+)"', payload["frags"].get("head-id", "")
            )
            if found and (not seen or int(found.group(1)) > seen[-1]):
                seen.append(int(found.group(1)))
            if len(seen) >= count:
                return seen
    raise AssertionError(f"the trial count never advanced: {seen}")


def test_the_console_follows_a_simulated_session_through_a_restart_to_its_end(
    tmp_path, zmq_cleanup, server_cleanup
):
    """Spec §4.4's end to end, and spec §2's "restarting `wlx serve` changes nothing
    in `taskd`" (Review Focus 5): a real `wlx run --link` in the simulator, a real
    `wlx serve` on loopback, and the event stream read as a browser reads it.

    The session is ended by a console's `Stop` -- what slice b2's page will send --
    because under the twelve-hour reference config nothing else would end it soon.
    With no terminal attached, `wlx run` records that nobody took the return and exits
    (P4d-2a Task 8), so the stop frame is the last one the console sees.
    """
    pub, rep = _endpoints(zmq_cleanup)
    first = server_cleanup(Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN))
    first.start()
    second = None
    result: dict = {}

    def _run() -> None:
        result["exit_code"] = main(
            [
                "run", GOOD,
                "--allocation", ALLOCATION,
                "--bounds", TWELVE_HOURS,
                "--root", str(tmp_path),
                "--session-id", "2027-01-14_08",
                "--subject", "REFERENCE",
                "--out-of-cage-at", time.strftime("%H:%M"),
                "--delivered-today", "0",
                "--trials", "100000",
                *_TASK_SETS,
                "--link", f"{pub},{rep}",
            ]
        )

    # A daemon, so a run that a broken `Stop` never ends cannot hold the suite open.
    runner = threading.Thread(target=_run, daemon=True)
    runner.start()
    try:
        before = _advancing(first)
        first.close()

        second = server_cleanup(
            Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN)
        )
        second.start()
        after = _advancing(second)
        assert after[0] > before[-1], "the session did not run on without a console"

        with zmq_cleanup(ZmqConsole(pub, rep)) as console, _stream(
            second.address[1]
        ) as response:
            events = _events(response)
            next(events)
            console.send(Stop(by="e2e"))
            ended = None
            for _, payload in zip(range(20_000), events):
                if 'data-state="ended"' in payload["frags"].get("state", ""):
                    ended = payload
                    break

        assert ended is not None, "the console never showed the session ending"
        assert "stopped by e2e" in ended["frags"]["banners"]
        assert ended["live"] is False
    finally:
        runner.join(timeout=30)
        first.close()
        if second is not None:
            second.close()
    assert not runner.is_alive(), "wlx run did not finish once it was stopped"
    # Both servers' `ZmqConsole`s and `main()`'s own `ZmqLink` were built inside
    # threads this test cannot register with `zmq_cleanup`; collected here, under the
    # test's control (`ZmqLink.close`'s docstring).
    gc.collect()
    assert result["exit_code"] == 0


def _until_refused(server: Server, publish, expect: str) -> str:
    """Publish until the hub says it refused a frame for `expect`'s reason: a PUB
    socket drops what it sends before a subscription lands, so one send proves
    nothing."""
    for _ in range(250):
        publish()
        rejected = server.hub.snapshot(on_box=True, stale_after_s=30.0)[1].rejected
        if rejected and expect in rejected:
            return rejected
        time.sleep(0.02)
    raise AssertionError(f"the server never said it refused a frame ({expect!r})")


def test_a_frame_this_console_cannot_read_is_shown_as_refused_not_guessed(
    zmq_cleanup, server_cleanup
):
    """Review Focus 1: a frame of another schema -- a schema-6 `wlx run` beside this
    `wlx serve`, which this slice's own upgrade makes likely -- and a packet that is
    no frame at all. Each is said, neither is shown, and serving goes on."""
    import msgpack

    link = zmq_cleanup(
        ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0")
    )
    server = server_cleanup(
        Server(
            sub=link.pub_endpoint,
            req=link.rep_endpoint,
            http=("127.0.0.1", 0),
            token=TOKEN,
        )
    )
    server.start()
    try:
        why = _until_refused(
            server, lambda: link.publish(replace(frame(), schema=6)), "schema 6"
        )
        assert "this console reads schema 7" in why
        assert server.hub.snapshot(on_box=True, stale_after_s=30.0)[0] is None

        why = _until_refused(
            server,
            lambda: link._pub.send(msgpack.packb({"schema": 7}, use_bin_type=True)),
            "could not be decoded",
        )
        assert "KeyError" in why

        for _ in range(250):
            link.publish(frame())
            shown, seen = server.hub.snapshot(on_box=True, stale_after_s=30.0)
            if shown is not None:
                break
            time.sleep(0.02)
        assert shown is not None and seen.rejected is None
        assert _request(server.address[1], "GET", "/")[0] == 200
    finally:
        server.close()
        gc.collect()


def test_closing_the_server_stops_serving(zmq_cleanup, server_cleanup):
    pub, rep = _endpoints(zmq_cleanup)
    server = server_cleanup(Server(sub=pub, req=rep, http=("127.0.0.1", 0), token=TOKEN))
    server.start()
    port = server.address[1]
    assert _request(port, "GET", "/")[0] == 200

    server.close()
    server.close()

    with pytest.raises(OSError):
        _request(port, "GET", "/")
    gc.collect()


def _token_file(tmp_path, text: str = f"{TOKEN}\n") -> Path:
    path = tmp_path / "health.token"
    path.write_text(text, encoding="utf-8")
    return path


def _serve_args(
    tmp_path,
    *,
    token: Path | None = None,
    link: str = "tcp://127.0.0.1:5571,tcp://127.0.0.1:5572",
    http: str = "127.0.0.1:0",
    extra: tuple = (),
) -> list:
    return [
        "serve",
        "--link", link,
        "--http", http,
        "--health-token-file", str(token if token is not None else _token_file(tmp_path)),
        *extra,
    ]


def test_wlx_serve_serves_until_interrupted_then_closes(
    tmp_path, monkeypatch, capsys, zmq_cleanup, server_cleanup
):
    pub, rep = _endpoints(zmq_cleanup)
    seen: dict = {}

    def interrupted(server: Server) -> None:
        server_cleanup(server)
        seen["port"] = server.address[1]
        seen["page"] = _request(seen["port"], "GET", "/")[0]
        seen["health"] = _request(
            seen["port"], "GET", "/health", {"Authorization": f"Bearer {TOKEN}"}
        )[0]
        raise KeyboardInterrupt

    monkeypatch.setattr(serve, "_wait", interrupted)

    assert main(_serve_args(tmp_path, link=f"{pub},{rep}")) == 130
    assert seen["page"] == 200 and seen["health"] == 200
    captured = capsys.readouterr()
    assert f"http://127.0.0.1:{seen['port']}/" in captured.out
    assert "the session keeps running on the box" in captured.err
    with pytest.raises(OSError):
        _request(seen["port"], "GET", "/")
    gc.collect()


def test_serving_waits_for_the_operator():
    """A `_wait` that returned would end the console the moment it started."""
    waiter = threading.Thread(target=serve._wait, args=(None,), daemon=True)
    waiter.start()
    waiter.join(timeout=0.2)

    assert waiter.is_alive()


@pytest.mark.parametrize(
    ("text", "why"),
    [("", "is empty"), ("   \n", "is empty"), ("tök\n", "non-ASCII")],
)
def test_wlx_serve_refuses_a_token_it_cannot_use(tmp_path, text, why):
    with pytest.raises(SystemExit, match=why):
        main(_serve_args(tmp_path, token=_token_file(tmp_path, text)))


def test_wlx_serve_refuses_a_token_file_inside_the_repository(tmp_path):
    """Spec §2: a token file, never the repository. `pyproject.toml` stands in for a
    token someone saved into the checkout."""
    inside = Path(serve.__file__).resolve().parents[1] / "pyproject.toml"

    with pytest.raises(SystemExit, match="inside this repository"):
        main(_serve_args(tmp_path, token=inside))


def test_wlx_serve_refuses_a_token_file_it_cannot_read(tmp_path):
    with pytest.raises(SystemExit, match="cannot read"):
        main(_serve_args(tmp_path, token=tmp_path / "missing.token"))


@pytest.mark.parametrize(
    "link",
    ["tcp://127.0.0.1:5571", "a,b,c", ",tcp://127.0.0.1:5572", "5571,5572"],
)
def test_wlx_serve_refuses_a_link_that_is_not_two_endpoints(tmp_path, link):
    with pytest.raises(SystemExit, match="exactly two"):
        main(_serve_args(tmp_path, link=link))


@pytest.mark.parametrize(
    "http", ["8080", "localhost:", "127.0.0.1:99999", "[::1]:8080", "::1:8080"]
)
def test_wlx_serve_refuses_an_address_it_cannot_serve_on(tmp_path, http):
    with pytest.raises(SystemExit, match="HOST:PORT"):
        main(_serve_args(tmp_path, http=http))


@pytest.mark.parametrize("stale", ["0", "-5", "nan", "inf"])
def test_wlx_serve_refuses_a_stale_after_that_is_not_a_positive_time(tmp_path, stale):
    with pytest.raises(SystemExit, match="--stale-after"):
        main(_serve_args(tmp_path, extra=("--stale-after", stale)))
```

In `tests/_transport_import_blocker.py`, after `import wl_expcontroller.cli as _cli  # noqa: E402`, add:

```python
# P4d-2b b1: the browser console's three modules. `serve` reaches `zmq` only through
# `link.ZmqConsole`, inside its telemetry thread, so importing it -- or `web` and
# `health`, which it renders with -- must acquire no transport.
import wl_expcontroller.health as _health  # noqa: E402
import wl_expcontroller.serve as _serve  # noqa: E402
import wl_expcontroller.web as _web  # noqa: E402
```

extend the `for _name, _mod in (...)` tuple with `("health", _health), ("serve", _serve), ("web", _web)`, and append:

```python
print(f"PASS: wl_expcontroller.health imported ({_health.__file__})")
print(f"PASS: wl_expcontroller.serve imported ({_serve.__file__})")
print(f"PASS: wl_expcontroller.web imported ({_web.__file__})")
```

In `tests/test_no_transport_leak.py`, after the `cli` assertion, add:

```python
    # P4d-2b b1: the browser console imports no transport either.
    assert "PASS: wl_expcontroller.health imported" in result.stdout, result.stdout
    assert "PASS: wl_expcontroller.serve imported" in result.stdout, result.stdout
    assert "PASS: wl_expcontroller.web imported" in result.stdout, result.stdout
```

- [ ] **Step 2: Run them to see them fail**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py tests/test_link.py tests/test_no_transport_leak.py`
Expected: `tests/test_serve.py` fails to collect — `ImportError: cannot import name 'Server' from 'wl_expcontroller.serve'`; `test_a_console_can_be_given_a_shorter_receive_timeout` fails with `TypeError: ... unexpected keyword argument 'receive_timeout_s'`. `tests/test_no_transport_leak.py` already passes: the three modules exist and import no transport, so its new lines are a regression guard rather than a new behavior — say so in the task report rather than claiming it failed first.

- [ ] **Step 3: Implement**

In `wl_expcontroller/link.py`, change `ZmqConsole.__init__`'s signature to:

```python
    def __init__(
        self,
        pub_endpoint: str,
        req_endpoint: str,
        settle_s: float = 0.05,
        receive_timeout_s: float = 5.0,
    ):
```

replace the SUB socket's `self._sub.setsockopt(zmq.RCVTIMEO, 5000)` line (keep the comment above it) with:

```python
        # `receive_timeout_s` is 5 s by default, the ceiling `wlx console` has always
        # had. `wlx serve`'s telemetry thread passes a short one so it can look between
        # receives at whether to stop, and `Server.close` returns promptly (P4d-2b b1).
        # A responsiveness choice either way, not a measurement.
        self._sub.setsockopt(zmq.RCVTIMEO, int(receive_timeout_s * 1000))
```

and leave the REQ socket's `RCVTIMEO` at 5000.

In `wl_expcontroller/serve.py`, extend the imports to add `import math`, `import sys`, `from pathlib import Path`, and change the `http.server` import to `from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer`. Then append:

```python
#: How long the telemetry thread's receive waits before it looks again at whether to
#: stop, so `Server.close` returns promptly. A responsiveness choice, not a
#: measurement; `wlx console` keeps `ZmqConsole`'s 5 s.
RECEIVE_TIMEOUT_S = 0.5

#: The checkout this module runs from. A token file inside it is refused (spec §2).
_REPO_ROOT = Path(__file__).resolve().parents[1]


class Server:
    """`wlx serve`'s whole process, as an object a test can start and stop.

    Binds the HTTP port on construction -- so `address` is known, and a port in use
    is refused before anything else happens -- and starts two threads in `start`: the
    telemetry thread (`_listen`) and the HTTP server's loop.
    """

    def __init__(
        self,
        *,
        sub: str,
        req: str,
        http: tuple[str, int],
        token: str,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        keepalive_s: float = KEEPALIVE_S,
        receive_timeout_s: float = RECEIVE_TIMEOUT_S,
    ) -> None:
        self.hub = Hub()
        self._sub = sub
        self._req = req
        self._receive_timeout_s = receive_timeout_s
        self._stop = threading.Event()
        self._http = ThreadingHTTPServer(
            http,
            make_handler(
                self.hub,
                token=token,
                stale_after_s=stale_after_s,
                keepalive_s=keepalive_s,
            ),
        )
        self._web = threading.Thread(
            target=self._http.serve_forever, name="wlx-serve-http", daemon=True
        )
        self._telemetry = threading.Thread(
            target=self._listen, name="wlx-serve-telemetry", daemon=True
        )
        self._started = False
        self._closed = False

    @property
    def address(self) -> tuple[str, int]:
        """`(host, port)` as bound: the port the OS chose when `http` asked for 0."""
        host, port = self._http.server_address[:2]
        return host, port

    def start(self) -> None:
        self._started = True
        self._telemetry.start()
        self._web.start()

    def _listen(self) -> None:
        """The telemetry thread: the one `ZmqConsole`, created, read and closed here,
        so its sockets have one owning thread (spec §2).

        **A frame this console cannot use is said, never shown and never fatal**
        (Review Focus 1): one that does not decode, and one of another schema -- which
        may decode perfectly well and mean something else (`link.SCHEMA`'s own rule).
        Either goes to `Hub.reject`, the page says why, and the last good frame stays.
        """
        with _link.ZmqConsole(
            self._sub, self._req, receive_timeout_s=self._receive_timeout_s
        ) as console:
            while not self._stop.is_set():
                try:
                    frame = console.receive()
                except TimeoutError:
                    continue
                except Exception as exc:  # noqa: BLE001 -- said on the page, never fatal
                    self.hub.reject(
                        f"a telemetry frame could not be decoded, so it is not shown: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue
                if frame.schema != _link.SCHEMA:
                    self.hub.reject(
                        f"a telemetry frame carried schema {frame.schema!r} and this "
                        f"console reads schema {_link.SCHEMA}, so it is not shown "
                        f"rather than guessed at"
                    )
                    continue
                self.hub.offer(frame)

    def close(self) -> None:
        """Stop serving, end every open stream, and close the `ZmqConsole`. Safe to
        call twice, and before `start`."""
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self.hub.close()
        if self._started:
            self._http.shutdown()
        self._http.server_close()
        if self._started:
            self._web.join(timeout=5)
            self._telemetry.join(timeout=5)


def read_token(path: Path) -> str:
    """The `/health` bearer token: from a file, never from the repository (spec §2).

    Refused, each with a sentence and before anything binds: a file inside this
    checkout -- one `git add` from public -- a file that cannot be read, an empty one
    (there is no default token), and one holding a non-ASCII character, which
    `hmac.compare_digest` cannot compare, so every request would fail, the correct
    one included (wl-preproc refuses the same). The whitespace around it -- the
    newline an editor leaves -- is not part of the token.
    """
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(_REPO_ROOT):
        raise SystemExit(
            f"refused: the /health token file {str(path)!r} is inside this repository, "
            f"one `git add` from being published; keep it outside the checkout "
            f"(P4d-2b spec §2: a token file, never the repository)"
        )
    try:
        token = resolved.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(
            f"refused: cannot read the /health token file {str(path)!r}: {exc}"
        ) from exc
    if not token:
        raise SystemExit(
            f"refused: the /health token file {str(path)!r} is empty; there is no "
            f"default token, so wl-works could never authenticate -- write one token "
            f"on one line"
        )
    if not token.isascii():
        raise SystemExit(
            "refused: the /health token contains a non-ASCII character; "
            "hmac.compare_digest cannot compare it, which would make every request "
            "fail authentication, the correct one included"
        )
    return token


def parse_link(text: str) -> tuple[str, str]:
    """`PUB,REP`, exactly as `wlx run --link` takes it. This process reads the first
    and, in b1, never sends to the second.

    Each must at least name a transport (`tcp://...`): ZeroMQ refuses one that does
    not only when the telemetry thread connects, where the refusal would be a
    traceback on a thread rather than a sentence before anything binds."""
    parts = text.split(",")
    if len(parts) != 2 or not all("://" in part for part in parts):
        raise SystemExit(
            f"refused: --link expects PUB,REP -- exactly two comma-separated endpoints "
            f"such as tcp://127.0.0.1:5571, as given to `wlx run --link` -- got {text!r}"
        )
    return parts[0], parts[1]


def parse_http(text: str) -> tuple[str, int]:
    """`HOST:PORT`, IPv4 or a name: the stdlib server here binds IPv4 only."""
    host, sep, port = text.rpartition(":")
    if (
        not sep
        or not host
        or ":" in host
        or host.startswith("[")
        or not port.isdigit()
        or int(port) > 65535
    ):
        raise SystemExit(
            f"refused: --http expects HOST:PORT with an IPv4 address or a name -- "
            f"127.0.0.1:8080 for this box only, 0.0.0.0:8080 to let the lab network "
            f"read the page -- got {text!r}"
        )
    return host, int(port)


def _wait(server: Server) -> None:
    """Block until the operator interrupts. Its own function so a test can stand in
    for the person pressing Ctrl-C; `time.sleep` is interrupted by it everywhere."""
    while True:
        time.sleep(3600)


def run(args) -> int:
    """`wlx serve`: check everything, bind, serve until interrupted (spec §2).

    Every refusal is a sentence, and all of them happen before anything binds.
    Ctrl-C ends it with 130, as `wlx console` does, and says what it did not stop.
    """
    token = read_token(args.health_token_file)
    sub, req = parse_link(args.link)
    host, port = parse_http(args.http)
    stale_after = (
        DEFAULT_STALE_AFTER_S if args.stale_after is None else args.stale_after
    )
    if not math.isfinite(stale_after) or stale_after <= 0:
        raise SystemExit(
            f"refused: --stale-after must be a positive number of seconds, got "
            f"{args.stale_after!r}"
        )
    try:
        server = Server(
            sub=sub, req=req, http=(host, port), token=token, stale_after_s=stale_after
        )
    except OSError as exc:
        raise SystemExit(f"refused: cannot serve on {host}:{port}: {exc}") from exc
    server.start()
    bound_host, bound_port = server.address
    print(
        f"wlx serve: the console is at http://{bound_host}:{bound_port}/, reading "
        f"{sub}; GET /health needs the bearer token",
        flush=True,
    )
    try:
        _wait(server)
    except KeyboardInterrupt:
        print(
            "serve: interrupted -- the session keeps running on the box; nothing here "
            "stops it",
            file=sys.stderr,
        )
        return 130
    finally:
        server.close()
    return 0
```

In `wl_expcontroller/cli.py`, directly after the `console_parser` arguments (before `args = parser.parse_args(argv)`), add:

```python
    server_parser = sub.add_parser(
        "serve",
        help="serve a running session's read-only browser console, and /health",
    )
    server_parser.add_argument(
        "--link",
        required=True,
        metavar="PUB,REP",
        help="the session's two endpoints, exactly as given to `wlx run --link "
        "PUB,REP`. Telemetry is read from the first; the second is connected and, in "
        "this slice (P4d-2b b1), never sent to -- nothing on the page writes",
    )
    server_parser.add_argument(
        "--http",
        required=True,
        metavar="HOST:PORT",
        help="where to serve the page and /health: 127.0.0.1:8080 for this box only, "
        "or 0.0.0.0:8080 to let the lab network read it (P4d-2b spec §2: reads are "
        "open to the LAN). An IPv4 address or a name",
    )
    server_parser.add_argument(
        "--health-token-file",
        required=True,
        type=Path,
        metavar="PATH",
        help="a file holding the bearer token wl-works sends to GET /health, on one "
        "line. Refused if it is inside this repository: a token there is one `git "
        "add` from public",
    )
    server_parser.add_argument(
        "--stale-after",
        type=float,
        default=None,
        metavar="SECONDS",
        help="how long without a frame, while one is due, before the page greys and "
        "/health says degraded. Omitted uses 30, a display choice (P4d-2b spec §3), "
        "not a measurement",
    )
```

and directly after `args = parser.parse_args(argv)`, add:

```python
    if args.command == "serve":
        # Imported here, the way `--link` builds its `ZmqLink` inside `run`: no other
        # subcommand loads a web server.
        from wl_expcontroller import serve as _serve

        return _serve.run(args)
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider tests/test_serve.py tests/test_link.py tests/test_no_transport_leak.py`
Expected: all pass. Run `tests/test_serve.py` three times in a row; the end-to-end test must not flake.
Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wl_expcontroller/link.py wl_expcontroller/serve.py wl_expcontroller/cli.py tests/test_serve.py tests/test_link.py tests/_transport_import_blocker.py tests/test_no_transport_leak.py
git commit -m "Add wlx serve: one ZmqConsole, a telemetry thread, the page and /health"
```

---
### Task 12: Write it down

**Why:** CLAUDE.md — a change that invalidates `architecture.md` or a spec updates them in the same branch, and a session ends by leaving the repo resumable. Spec §1 says S9a §7 is amended from "HTTP/WS" when this slice lands; spec §4.0 says S9a §9 is amended for the strip. **No ADR is written**: ADR-0008 chose the browser and names no browser transport, and spec §1 keeps server-sent events reversible (WebSockets are an added endpoint for one pane, not a rewrite).

**Files:**
- Modify: `docs/design/architecture.md`, `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, `docs/CHECKPOINT.md`, `docs/next-session.md`

**Interfaces:** none (documents only).

- [ ] **Step 1: `docs/design/architecture.md`**

1. In the `console` row of the Components table, replace the clause that says the browser client and the HTTP/WS server "are P4d-2" with:

   > **The browser console exists, read-only** (P4d-2b slice b1, 2026-09-26): `wlx serve --link PUB,REP --http HOST:PORT --health-token-file PATH` is its own process — a stdlib `ThreadingHTTPServer`, one `ZmqConsole` on a telemetry thread, server-sent events to each browser from a bounded queue, and every pane rendered in Python (`web.py`) so the page's script only swaps fragments. The wl-works fonts are bundled and served by the box, so the page never reaches the internet (PI, 2026-09-26). Reads are open to the LAN; writes from the box are slice b2, and OAuth is P4d-3.

2. In the `labhost` row, append:

   > Served as `GET /health` by `wlx serve` (`health.py`, P4d-2b b1): `HealthResponse` schema 1, contract-tested against wl-preproc's own model; a bearer token read from a file outside the repository, compared with `hmac.compare_digest`, one `401` for every credential failure — the rules of wl-preproc's `responder/handler.py`. Exactly one reading is featured, the most urgent (PI, 2026-09-26), because wl-works shows only the first.

3. In the protocols list, after the **Control/telemetry** bullet, add:

   > - **Browser** (browser <-> console): HTTP, with server-sent events carrying rendered HTML fragments to the page (P4d-2b spec §1). WebSockets are deferred to the replica pane, if V11 shows a browser can carry it at display rate.

4. After the paragraph that begins "`welfare.py` has all three", add:

   > **`deliver` also records when it charged** (`Welfare.last_delivery_wall_at`, P4d-2b b1, 2026-09-26): the wall instant, read from the session's own clock by `Rig`, for the console's time since the last reward. Nothing compares it with a limit, and it is not refused when it is not a number, so a display field can never end a trial.

- [ ] **Step 2: S9a (`docs/superpowers/specs/2026-08-31-S9a-console-design.md`)**

1. §7's diagram: `browser ──HTTP/WS──►` becomes `browser ──HTTP + SSE──►`, and `├ static assets, WS fan-out` becomes `├ the page, SSE fan-out`. Directly below the diagram, add:

   > **HTTP and server-sent events, not WebSockets** (P4d-2b spec §1, PI 2026-09-26). Panes are rendered to HTML in Python and pushed as fragments, so what a pane may never drop is a pytest assertion on the renderer. WebSockets are deferred to the replica pane, if V11 shows a browser can carry it at display rate — an added endpoint for one pane, not a rewrite. Known limit, accepted: over HTTP/1.1 a browser holds about six connections per host and each event stream holds one, so a seventh console tab on one box in one browser stalls (MDN's server-sent events guide; not re-verified 2026-09-26).

2. §9's table: add these rows after "Still needed, by condition", and change the "Parameter row" row's Source to the one below:

   | Pane | Source |
   |---|---|
   | Configuration: task, allocation, bounded config | `SessionSpec.task`, `.allocation`, `.bounds_config` — what the config snapshot's `versions` records. Display mode and stimulus calibration have no source yet and say so |
   | The day's floor; the out-of-cage limit | `welfare.bounds.minima[DAILY_FLUID]` and `ceilings[OUT_OF_CAGE].value` — the numbers `shortfall` and `must_stop` read. The limit is `None` cage-side |
   | Time since the last reward | `welfare.last_delivery_wall_at` (`Telemetry.last_reward_at`) less the console's clock. **What keeps a working, unpaid animal visible on the strip** since 2026-09-26: fluid today standing still while this grows |
   | Recent outcomes | `Session.recent_outcomes` — the last 60 strings `trials.jsonl` records, from the one string both are handed |
   | Correct / trials, on the strip | `Telemetry.outcomes["correct"]` plus `["correct_reject"]`, over `trial_index`: **the one rollup, ruled for the strip only** (PI, 2026-09-26: both are the right answer on their trial). The Working? pane and `/health` count every outcome as it occurred |
   | Parameter row | `Session.parameters` → `Telemetry.params`: the task's own `Param` declarations with their values, then the welfare ceilings a console may stage; writes return through `Session.set` |
   | Trials per minute | **Derived by `wlx serve`**, from `trial_index` over the last five minutes of frames, labeled derived on the page, bounding nothing — the one console number not in the record, and it says so |

3. At the end of the paragraph "**And two of those numbers may not be removed**", add:

   > **Since 2026-09-26 neither is on the always-visible strip** (P4d-2b spec §4.0; asked against this paragraph, the PI answered "fine as is"): both are on Runtime and End of session in every state, and `tests/test_web.py::test_fluid_session_and_the_supplement_are_never_dropped` holds that. What keeps a working, unpaid animal visible at a glance is fluid today standing still on the strip while the time since the last reward grows.

4. In the schema history sentence (P4d-2a's Task 10 carried it through 6), append:

   > At 7 (2026-09-26, P4d-2b b1) the configuration, the floor and the out-of-cage limit, the last reward's instant and the recent outcomes were added. Nothing changed meaning; a schema-7 reader refuses a schema-6 frame rather than guessing, and `wlx serve` says so on its page.

- [ ] **Step 3: `docs/CHECKPOINT.md`**

1. Add a "What moved" entry, dated the day the branch is finished, headed "P4d-2b slice b1: the read-only browser console". It says, in this order:
   - what was built: schema 7, `wlx serve`, the page, `/health`, and the files (`serve.py`, `web.py`, `health.py`);
   - **the one welfare-critical change** (`Welfare.deliver`'s `wall_now` and `last_delivery_wall_at`, and `Rig.wall_clock`), the fonts shipped under ADR-0004's 2026-09-26 amendment, and that the branch awaits the PI's approval of the welfare item;
   - the PI's three rulings on the plan (2026-09-26, recorded in spec §3 and §4.2): exactly one featured reading, the most urgent; the strip's correct counts `correct` plus `correct_reject`, the one rollup, while every other count stays unrolled; and the fonts bundled and served by the box, with ADR-0004 reopened for their OFL-1.1 licenses. Also: tick colors are by family, where the mockup's were not;
   - the page's stale banner runs only while frames are due (running, or awaiting the return), which is also `/health`'s staleness rule;
   - one line on how a refused frame shows: a schema-6 `wlx run` beside a schema-7 `wlx serve` shows a *Refused* banner, by design.
2. In the Work packages table, the P4d-2b row (P4d-2a's Task 10 created it) becomes: b1 built on branch `p4d2b-b1-read-only-console`, awaiting the PI's approval of the welfare item; next is b2 (writes from the box), read the P4d-2b spec §2 and §4.0.

The gate's result and the test count are added to this entry in Task 13 Step 3, once they exist.

- [ ] **Step 4: `docs/next-session.md`**

1. §1: add Task 13 Step 6's numbered item (the welfare item). The fonts' license question is settled by ADR-0004's 2026-09-26 amendment.
2. §6: P4d-2b b1 is built; b2 is next — writes from the box (spec §2's four conditions on `POST /commands`, the `NAME (box, unverified)` attribution, and the greyed controls' sentence), per spec §4.0's slice list. The command thread that owns the REQ socket arrives with b2 (`serve.py`'s module docstring names it).

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "Record the read-only browser console, and what the PI is asked to approve"
```

---

### Task 13: Prove it, look at it, and hand it to the PI

**Files:** `docs/CHECKPOINT.md` (Step 3). Nothing else, unless a step finds a survivor or a defect; then the owning task's files, with a test that fails without the fix.

**Interfaces:** none.

- [ ] **Step 1: The whole suite, three times**

Run: `WLX_REQUIRE_PREPROC=1 python -m pytest -q -p no:cacheprovider -rs` three times in a row.
Expected: all pass each time, and the `-rs` summary lists no skip from `test_health.py` or `test_serve.py` (their contract tests must run). Note the passed count; Step 3 records it.

- [ ] **Step 2: The mutation gate, read line by line**

Run: `python tools/mutation_gate.py --base main 2>&1 | tee "${TMPDIR:-/tmp}/p4d2b-b1-gate.txt"`

**`tools/mutation_gate.py` changed in this branch, so this is a full sweep** — it selects every module (`GLOBAL` escalates), and it takes a long time. Run it in the background and do nothing else in the worktree until it ends: **never run the suite, edit a test, or `git add` while it is in flight.**

Then read every line of the output file:
- Zero `SURVIVED` and zero `SKIPPED`.
- Every `caught` shows `N failed` and a `<-` naming tests. `N errors`, a timeout, or a single unrelated test does not count as caught.
- For each function this plan added or changed, find its line and check that the `<-` names a test this plan wrote for it: `Outcome.family`; `Welfare.deliver`, `Rig.reward`; `Session.recent_outcomes`, `Session.parameters`; `Telemetry.of`, `encode`, `decode`, `ZmqConsole.__init__`; `render`, `_shown`, `_edge`, `_with_unit`; every function in `health.py`, `web.py` and `serve.py` (including `font_bytes`, `_wait`, `_put_dropping_oldest`, `on_box`, `event`, `_csp`, `send_error`, `_refuse_method`, `_font`, `_send_frame`, `read_token`, `parse_link`, `parse_http`).
- A survivor gets a test that fails without it, in the owning task's test file. A function nothing can test is deleted, not exempted.

- [ ] **Step 3: Record what the gate said**

In `docs/CHECKPOINT.md`'s entry from Task 12, add the gate's result as read in Step 2 — modules swept, `SURVIVED`/`SKIPPED` counts, and any survivor found and how it was closed — and the passed count from Step 1; update the Status table's test count to the same number.

```bash
git add docs/CHECKPOINT.md
git commit -m "Record the b1 mutation sweep and test count"
```

- [ ] **Step 4: Look at it in a browser (manual)**

The suite cannot run the page's script. With a token file outside the repository (for example `~/.config/wlx/health.token` holding one line), start a simulated session and the console in two terminals from the worktree root:

```bash
python -m wl_expcontroller.cli run tasks/fixation_detection.py \
  --allocation tasks/allocation.py --bounds tasks/twelve_hour_bounds.py \
  --root "${TMPDIR:-/tmp}/wlx-b1" --session-id 2027-01-14_01 --subject REFERENCE \
  --out-of-cage-at "$(date +%H:%M)" --delivered-today 0 --trials 100000 \
  --set fix_timeout=4.0 --set fix_hold=0.3 --set response_window=0.6 \
  --set target_hold=0.2 --set fix_window=2.0 --set target_window=3.0 \
  --set target_position=10.0 \
  --link tcp://127.0.0.1:5571,tcp://127.0.0.1:5572
```

```bash
python -m wl_expcontroller.cli serve --link tcp://127.0.0.1:5571,tcp://127.0.0.1:5572 \
  --http 127.0.0.1:8080 --health-token-file ~/.config/wlx/health.token --stale-after 5
```

Open `http://127.0.0.1:8080/` and confirm, writing down what was seen:
1. The header, the four strip cells and the ticks advance; the four tabs switch with no script involved; the right column shows its four placeholders.
2. `curl -s -H "Authorization: Bearer $(cat ~/.config/wlx/health.token)" http://127.0.0.1:8080/health` returns `ok` with one featured reading, and the page's *wl-works sees* pane matches it.
3. Stop `wlx serve` with Ctrl-C: the page says *stream lost*. Start it again: the page re-renders in full on its own, and the session never paused.
4. The ✕ closes the stream and shows *disconnected · the session keeps running on the box*; *reconnect* brings the page back.
5. Send `python -m wl_expcontroller.cli console --sub tcp://127.0.0.1:5571 --req tcp://127.0.0.1:5572 --as jake --stop`: the pill reads *ended · operator*, and after `--stale-after` seconds nothing greys (no frames are due).
6. Start a second session and stop its `wlx run` with Ctrl-Z (suspend, so no stop frame is sent): after `--stale-after` seconds the page greys and says *stream stale · last frame N s ago*, and `/health` says `degraded`. Resume it with `fg` and the page recovers.
7. Open the page in a browser's private window with network access disabled: it renders fully, in IBM Plex with the Newsreader logo, and the developer tools' network panel shows requests to the box only — `/`, `/events` and the `/fonts/...` files.

If any of these fails, fix it in the owning task with a test where Python can reach it, and repeat this step.

- [ ] **Step 5: Push and read CI**

```bash
git push -u origin p4d2b-b1-read-only-console
```

Then read the branch's CI run (`gh run list --branch p4d2b-b1-read-only-console`): its log, not its verdict. **Do not merge to `main`.**

- [ ] **Step 6: Hand the PI the review**

Give the PI (memory: he wants numbered items to approve, not the files):

1. **`welfare.deliver` now records when it charged each reward.** It takes the session's wall instant and keeps the last one as `last_delivery_wall_at`, set beside `commanded` and `deliveries`, before the valve opens. Nothing compares it with a limit, and it is not refused when it is not a number, so a display field can never end a trial the animal completed. `Rig` reads the session's own clock for it, once per reward. Pinned by `test_a_delivery_records_the_wall_instant_it_was_charged_at`, `test_a_rewards_instant_is_read_from_the_rigs_wall_clock`, `test_a_delivery_the_pump_refused_is_still_charged_and_timed` and `test_a_session_records_when_it_last_paid_on_its_own_wall_clock`.

2. **The fonts ship under ADR-0004's amendment of 2026-09-26** (PI: "Allow OFL fonts"), for information, not for approval. The PI settled it when asked: the fonts ship unmodified with each family's `OFL.txt`; condition 2 permits bundling them with any software; and condition 5 exempts "any document created using the Font Software", so the Apache-2.0 code and the pages it serves are unaffected. Pinned by `test_every_font_the_page_uses_is_bundled_with_its_license` and `test_the_fonts_ship_with_the_package`.

The featured reading (exactly one, the most urgent) and the strip's correct count (`correct` plus `correct_reject`) were ruled on 2026-09-26 and are in spec §3; they are not asked again.

It merges to `main` by fast-forward only after he approves item 1; item 2 is for information.
