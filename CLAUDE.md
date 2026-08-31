# Working conventions — wl-expcontroller

These conventions bind every session (human- or AI-driven) working in this repo.

## Read order before touching code
1. `docs/M0-REVIEW.md` — where the project actually is, and what is still open
2. `docs/design/architecture.md` — topology, contracts, latency budgets
3. `docs/pitfalls.md` — the failure modes we are designing against
4. Relevant ADRs in `docs/design/decisions/`, then the S-spec you are working in
   (`docs/superpowers/specs/2026-08-31-spec-map.md` says which)

## Rules
- **US English** everywhere (code, docs, comments).
- **No timing claim without a measurement.** Never state or document a latency,
  jitter, or throughput number for this system unless it comes from a script in
  `tools/` (once code exists) with results committed under `docs/measurements/`.
  Literature numbers are cited with source and date.
- **Sim first.** New functionality ships with a simulator-backed test. Nothing merges
  with a red test suite. Hardware-specific code lives behind the interfaces defined
  in `docs/design/architecture.md`.
- **Hot-path discipline.** Inside trial loops: no allocation, no logging I/O, no
  unbounded work per frame. GC is explicitly managed around trials, never during.
- **Welfare-critical code requires human review.** Anything touching reward delivery
  amounts/limits, session duration or fluid tracking, or stimulation triggering must
  be reviewed by a human lab member before merge. Keep these modules small and listed
  in `docs/design/architecture.md`.
- **ADRs for irreversible choices.** Engine, transport, file-format, and license
  decisions go through `docs/design/decisions/` using the template.
- **Dependency policy.** New dependencies need a one-line justification and a license
  entry in ADR-0004's inventory. Prefer boring, maintained libraries.
- **Docs stay in sync.** A change that invalidates architecture.md, pitfalls.md, or
  the roadmap updates them in the same commit.
- **No fabrication.** If a fact about external software matters (API behavior,
  license, latency), verify against the primary source and cite it with an as-of
  date, or mark it UNVERIFIED.
- **Read the neighbouring repository's source before specifying against it.** Not its
  README, not its manifest. This session found the event codec already frozen in
  `wl-preproc` after `wl-mllib`'s manifest said nothing was allocated, found
  `expcontroller/` already reserved for us by name, and found the eye-calibration
  model already fixed — each time while about to design a second one. `wlo validate`
  cannot catch this class of error: it checks that a published name resolves to one
  publisher, never that the description is true.
- **Registry over README for lifecycle.** A package's stage is what
  `wl-orchestrator/registry/` says. `wl-elab`'s own README still reads as the live ELN
  and the registry has said `deprecated` for some time.
- **Ask, do not file.** A decision that is science-facing, animal-facing, or expensive
  to get wrong goes to the PI as a question at the moment it arises. Recording it in an
  open-items table is a record, not an ask — and three of the first four decisions
  revisited that way were changed.

## Commit style
Imperative subject line; body explains why when non-obvious. The repo history is part
of the lab record.
