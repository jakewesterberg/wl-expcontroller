# ADR-0001: Scope and process for wl-expcontroller

- Status: Accepted; decision 3 superseded by ADR-0005 (2026-08-31)
- Date: 2026-08-30
- Deciders: Jake (PI)

## Context
No maintained Linux-native Python-first NHP controller exists (docs/research/
landscape.md, as of 2026-08-30). The lab needs three closed-loop regimes on 3-4
Neuropixels rigs with OpenIrisDPI eye tracking. Building is justified; building badly
is the main risk (docs/pitfalls.md).

## Decision
1. Build a lab-scoped controller (not a community framework) on maintained engines.
2. Process commitments: spec-first (contracts before code), sim-first (headless CI),
   measure-everything (docs/validation.md; numbers committed per rig), ADRs for
   irreversible choices, AI-assisted development under CLAUDE.md conventions.
3. ~~Bridge strategy: rigs may run MonkeyLogic + OpenIrisDPI analog out during
   development; tasks migrate on demonstrated parity (roadmap M5).~~ **Superseded by
   ADR-0005.** The bridge assumed a MonkeyLogic task library that does not exist
   (`wl-mllib` holds no code and its own manifest states the behavioural stack is
   unchosen), so switching to it would have meant writing that library from scratch
   under pressure. wl-expcontroller is the day-one stack; see ADR-0005 for the
   replacement commitment and pitfalls P12 for the replacement mitigation.

## Alternatives considered
- Adopt MWorks: healthiest open-source NHP suite, but macOS-only and MWEL-first —
  fails the Linux/Python requirements.
- Stay on MonkeyLogic: viable (active, custom-UDP eye interface) but keeps MATLAB +
  Windows and offers no native neural-contingent path; retained as bridge instead.
- Resurrect REC-GUI: right architecture, dormant Python-2 codebase; we adopt the
  pattern, not the code.

## Consequences
Engineering effort lands on us (estimate: person-quarter scale to animal-ready v1,
compressed in calendar time by AI-assisted authorship; validation time is
irreducible). We accept early-adopter status for PsychoPy-on-macaque-ephys with the
mitigations in docs/pitfalls.md (P1, P11, P12).
