# ADR-0006: Task representation and authoring model

- Status: Proposed; item 6 settled by S1 (2026-08-31)
- Date: 2026-08-31
- Deciders: Jake (PI)

## Context

Tasks in this lab will be **primarily written by a model under experimenter direction**,
not hand-written by lab members. That inverts what a task API should optimise for.
Terseness, learnability and authoring ergonomics stop mattering; the human's role moves
from writing to reviewing, and so does the failure mode — generated task code is
syntactically clean, plausibly structured, and confidently wrong in ways that read well.
That is pitfalls P1 and P8 pointed at task code, and it is now P15.

Tasks must also be readable and editable in an ordinary IDE or text editor, support
gaze-contingent and neural-contingent behaviour within a trial, express unbounded
free-viewing epochs as well as discrete trials, carry cross-trial state (token economies),
and expose live-editable parameters.

## Decision

1. **Within a trial, task logic is declarative data.** States, guarded transitions,
   entry/exit actions, outcome codes. `taskd` executes it; the task never owns the frame
   loop. This makes it statically checkable, exhaustively simulatable, renderable as a
   diagram for review, and hot-path-safe by construction.
2. **Between trials, task logic is ordinary Python.** Condition selection, block
   progression, staircases, adaptive updates. Outside the frame budget, errors are
   observable and recoverable, and the freedom costs nothing.
3. **The representation is Python declarations** (dataclass/pydantic) in plain-text,
   diffable files — not a bespoke text DSL, not YAML/JSON, not a GUI builder, not
   database-stored tasks.
4. **Event codes are allocated in `wl-mllib`, never invented in a task.** Validation
   refuses an unregistered code at load time.
5. **Welfare-critical parameters are unreachable from a task file.** They live in a
   rig/subject bounded config that a task references and cannot set, and that a human can
   move within but not exceed.
6. **Escape-hatch strictness — settled by S1's bake-off, as the working assumption
   predicted.** The within-trial layer stays pure data; behaviour the vocabulary lacks is
   declared by name and resolves to a typed, reviewed component in the framework's own
   source, and a task using one is flagged for human review. The bake-off's decisive finding
   was not an argument but an accident: writing the permissive version of a fixation task, I
   produced an unbounded hold loop and silently dropped the photodiode confirmation, and
   neither was visible on reading. See
   `docs/superpowers/specs/2026-08-31-S1-task-model-design.md` §7.

## Alternatives considered

- **A bespoke declarative DSL (new text language).** Rejected: models write mainstream
  Python far better than a language with no training data, and it would forfeit IDE
  autocomplete, type checking and jump-to-definition — which the "readable in a local
  editor" requirement demands.
- **YAML/JSON task files.** Rejected for the same tooling reason: no type checking, no
  autocomplete, worse error messages, and no cheaper to generate.
- **Async/await linear trial scripts.** Rejected: most pleasant to read, but hidden control
  flow makes "what runs on which frame" non-obvious, defeats static verification, and makes
  hot-path discipline unenforceable in review — the exact properties needed when a machine
  wrote the code.
- **Thin library, each task a plain Python program with its own frame loop** (the Pype and
  REC-GUI model). Rejected: it was the YAGNI option under human authorship and becomes the
  risk option under D4. Nothing is checkable, the reviewer must read a frame loop, and every
  task re-invents trial structure differently.
- **Pure state machine with no imperative layer at all.** Rejected: between-trial concerns
  (staircases, block logic, condition balancing) express badly as graphs and gain nothing
  from being one, since they are outside the frame budget.

## Consequences

- One declaration drives four consumers: validation, the generated console UI, the saved
  session record, and the downstream contracts (`wl-mllib` decoding, the wl-works summary).
  A generated task gets a working parameter panel and working live plots with no UI code.
- The framework must carry a vocabulary rich enough that escape hatches stay rare;
  gaze-contingent rendering and neural-threshold gating are core vocabulary, not extensions,
  because they already meet P2's second-consumer test.
- Review becomes an artifact rather than an activity: a rendered state diagram, a timeline,
  a condition/code table, and a simulation report. **A task nobody could review from those
  alone has failed the design, not the reviewer.**
- Keyboard/mouse demo mode and simulated sessions become v1 deliverables with the same
  status as the display module, because they are the verification loop this decision
  depends on.
