# Where this build actually is

**Last updated 2026-08-31**, at the commit this file was committed in. Check
`git log --oneline -1`; if it has moved far, distrust the numbers here before you
distrust the reasoning. Numbers go stale, arguments do not.

**The lab opens January 2027.** Everything is being built before any rig exists, so
January validates rather than discovers. Nothing here has touched hardware.

---

## Read this much, and no more

24 design documents exist. **Do not read them all.** In order:

1. **This file** — where things are.
2. **`CLAUDE.md`** — the conventions, including three that were learned the hard way.
3. **`docs/M0-REVIEW.md`** §3 and §4 — what is still open, and the 24 engineering
   calls made without asking.
4. **The one S-spec your package names**, from the table below. Not the others.

`docs/superpowers/specs/2026-08-31-spec-map.md` maps S0–S13 if you need to find one.

---

## Status

**M0 signed off 2026-08-31.** Contracts frozen; code started.

| | |
|---|---|
| Tests | 27, green |
| CI | pytest on 3.11 and 3.13, plus a **mutation gate** |
| Load-time checks | **8 of 10** (S1 §9) |
| Cross-repo asks outstanding | **4 documents, 3 repos** — see below |
| Hardware verified | **none** |

### What exists

- `task.py` — the declarative trial: states, guarded transitions, actions, parameters.
- `check.py` — 8 of the 10 load-time checks. Missing: **5** (terminal states map to
  allocated outcome codes) needs `wl-mllib`'s allocation; **8** (stimuli expressible
  in cyclopean degrees) needs S4's stimulus vocabulary.
- `encode.py` — the 16-bit strobed word stream. Round-trips through `wl-preproc`'s
  own `decode_stream` and matches their `encode_payload` exactly across the uint32
  range. **We deliberately write no decoder.**
- `run.py` — the trial loop. Hardware, behaviour agents and demo mode are peers the
  loop cannot distinguish.
- `simulate.py` — sessions and the census: outcomes, states visited, hangs, and
  outcomes nothing reached.
- `cli.py` — `wlx check <task.py>`, exit 1 on a blocking finding.
- `tools/mutate.py` — proves a test can fail. Read its docstring before trusting a
  mutation result by hand.

### What does not exist, and matters

- **No task has been written.** The artifact this whole design exists to produce.
  S1's bake-off tasks are snippets in a spec, not files. This is P1.
- **No session record.** Nothing is written to disk. This is P2.
- **The round-trip tests skip in CI**, because they need a `wl-preproc` checkout
  beside this repo and CI has none. So **CI cannot currently catch an encoder
  drift** — the strongest test in the suite is the one CI does not run. Fixing it
  needs `wl-preproc` pinned as a git dependency, which needs a token for a private
  repo. Recorded rather than hidden.

---

## Work packages

One session each. Each names what to read; **reading more than that is how a session
runs out of context before it produces anything.**

| | Package | Exit condition | Read | Blocked on |
|---|---|---|---|---|
| ~~P0~~ | ~~Make the repo resumable~~ | **done 2026-08-31** | — | — |
| **P1** | Finish the task layer: checks 5 and 8, the first two real task files, the review artifact | A generated task is approved from a diagram and a report, without reading source | S1, S2 | nothing |
| P2 | Session record: JSONL events, parquet behaviour, config snapshot, directory layout | A simulated session writes a real session directory | S10, S3, S8 | nothing |
| P3 | `taskd` skeleton → **roadmap M1** | 1,000 deterministic trials with full outputs | S8, S9 | P2 |
| P4 | Demo mode + operator documentation | The D4 acceptance test; a stranger runs a session | S9 | P3 |
| P5 | Display adapter, stereo viewports, photodiode patches | Photodiode-ready display | S4, optics drawing | ADR-0002 ✔ |
| P6 | Eye ingest, calibration, saccade detection | Replay-driven gaze, and a calibration map `wl-preproc` can read | S5 | their reader |
| P7 | I/O behind interfaces: NI DIO, reward, comparator inputs | Absent, simulated and hardware as peers | S6 | hardware to verify |
| P8 | Neural plane, both feature sources | post-v1 | S7 | hardware |

**P1 through P4 need no hardware and no other repository.** That is four sessions to
M1, and M1 is what makes everything after it testable.

---

## Outstanding asks on other repositories

One consolidated handover sits in each repo as `HANDOVER-wl-expcontroller.md`.
**Committed in `wl-sync`; written but uncommitted in `wl-preproc` and `wl-works`**,
because the first was on a feature branch with work in flight and the second is owned
by another worker including its remote.

| Repo | Blocking? | Ask |
|---|---|---|
| `wl-sync` | **yes** | The session id is unreadable by a rig host, so `taskd` cannot name its own output directory. And two animals a day means a subject change must mint `_02` |
| `wl-preproc` | **yes** | `read_online_map` reads a `.bhv2` that will not exist, so `CalibrationSource.ONLINE` is unavailable for every session |
| `wl-preproc` | no | `PARAM_CHANGE` escape; ownership split recorded; codec declared as an artifact; per-trial gaze staleness |
| `wl-works` | no | `prepare-session`, a planned calibration block per session, alerting on bad readings |

Neither blocking item stops P1–P4. Both are built around: codes are allocated in
**4096–32767** (undisputed) and the session id sits behind a provider interface.

---

## Traps

Things that cost something to learn here. Each is a convention in `CLAUDE.md` now.

1. **Read the neighbouring repository's source, not its manifest.** `wl-mllib`'s
   manifest said the event vocabulary was unallocated; `wl-preproc` had a frozen
   codec. This project came within one spec of building a second one. Twice more
   since: `expcontroller/` was already reserved for us by name, and the eye
   calibration model was already fixed.
2. **`wlo validate` cannot catch a false description.** It checks that a published
   name resolves to one publisher, never that what it says is true.
3. **A ring of calibration targets is degenerate** on the second-order basis, because
   points on a circle make the constant, dx² and dy² columns linearly dependent. The
   intuitive pattern silently forecloses second-order calibration.
4. **Clear `__pycache__` when mutating.** Doing it by hand left stale bytecode and
   reported failures against already-correct code. The same staleness the other way
   reports a false *pass*. Use `tools/mutate.py`.
5. **A pure hazard model cannot produce non-engagement.** It fires eventually given
   enough frames, so `NO_FIXATION` — the commonest real abort — was unreachable in
   every simulated session until engagement became per-trial.
