# P4d-2b — The browser console and `/health`

- **Status: brainstorm in progress.** §1–§3 below were approved in conversation on
  2026-09-26 (PI). **§4, the page and its testing, has not been presented yet**; resume
  there. Not ready for a plan until §4 is approved and this file is reviewed whole.
- **Date:** 2026-09-26
- **Parent:** S9a §6–§9; ADR-0008; `architecture.md`'s `console` and `labhost` rows
- **Depends on:** P4d-2a (`2026-09-26-P4d2a-return-to-cage-design.md`) — `phase` and
  `stop_kind` in telemetry schema 6, and the `ReturnedToCage` command this page sends

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

## 2. Process and security (decided)

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

**`/health`** is `wl_preproc.contracts.protocol.HealthResponse`, schema version 1: readings
are plain text, with `<`, `>` and `&` spelled out as `wl-preproc`'s `plain_text` does.
Readings, featured marked \*: \*session (id · subject · task); \*state; \*time out of cage
against its limit, or *cage-side, no limit*; \*the duration warning when active; fluid this
session; \*supplement owed; the behavioral counts above; age of the last frame. `actions` is
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

## 4. The page, and testing — NOT YET PRESENTED

To cover: the four S9a §3 groups as dense panes; the generated parameter row and its staged
and refused feed; presence (box vs LAN viewers); Stop; the return-to-cage control from
P4d-2a; how the page behaves when the stream drops; and the test plan (renderer, handler
authorization as a pure function, an end-to-end run against `wlx run --link` on loopback,
the `/health` contract, the mutation gate's module lists).

## 5. Not in this slice

- Plots (accuracy over time, RT distribution, accuracy by position) — their own slice, with
  the per-trial RT and bounded history they need (PI, 2026-09-26)
- OAuth and the `Verified`/`Local` actor — P4d-3
- The replica pane — gated on V11
