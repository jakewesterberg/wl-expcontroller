# ADR-0005: Day-one stack, and interchangeability with MonkeyLogic

- Status: Accepted
- Date: 2026-08-31
- Deciders: Jake (PI)
- Supersedes: ADR-0001 decision 3

## Context

ADR-0001 kept MonkeyLogic as a bridge so that "science is never blocked on this project."
Reading the rest of the lab stack showed the bridge was not real: `wl-mllib` holds no code,
its own manifest states the behavioural stack is unchosen, and no event code is allocated
anywhere. Falling back to MonkeyLogic would have meant writing a task library from scratch
under exactly the pressure a fallback exists to relieve.

Meanwhile the rig's electrical interface is already designed in copper by `wl-sync`, and it
is controller-agnostic by construction: 16 event bits plus strobe, a reward command that
transits an OR gate, analog eye and joystick inputs, two photodiode comparators. Nothing in
it names a controller. The lab opens January 2027 (`wl-preproc/docs/CHECKPOINT.md`).

## Decision

1. **wl-expcontroller is the day-one stack.** MonkeyLogic is not deployed as the working
   controller. v1 must reach the training ladder plus a first recording task, 2D and
   monocular.
2. **Interchangeability with MonkeyLogic is maintained at the rig-contract and data layer
   only.** The event lines, reward path, analog inputs, photodiode patches, polarity
   conventions and event-code vocabulary are controller-agnostic and owned by `wl-sync` and
   `wl-mllib`, so either controller can drive the same rig and downstream consumers cannot
   tell which ran.
3. **The task PC dual-boots** — a supported Linux for wl-expcontroller, Windows for
   MonkeyLogic and MATLAB — sharing one NI PCIe-6343 and one set of MDR68 cables.
4. **No shared task language, and no maintained MonkeyLogic task twins.** The swap is
   insurance, verified once (spec map S12), not a parallel development effort.

## Alternatives considered

- **Keep the bridge as written.** Rejected: it depended on an artifact that does not exist,
  so it offered the reassurance of a fallback without the substance of one.
- **Full task portability — one source compiled to both engines.** Rejected: it is the
  framework creep P2 exists to forbid, and it would cap both systems at the intersection of
  their capabilities, forfeiting frame-level neural closed loop to keep MATLAB expressible.
- **Shared declarative task definition, native execution in each.** Rejected for v1: it
  guarantees stimulus and condition identity, but costs a spec format, two executors and
  drift tests, for a swap we hope never to exercise.
- **Swap kept possible but never verified.** Rejected: an untested fallback is a belief, not
  a mitigation. S12 runs it once.

## Consequences

- **Pitfalls P12 loses its mitigation and needs a new one.** Replaced by staged exposure:
  overnight synthetic soak before any animal session, the training ladder as the lowest-stakes
  proving ground, per-capability measurement gates, and the dual-boot swap as recoverable
  insurance. Recorded in `docs/pitfalls.md`.
- The roadmap's parity gate loses its comparator; M5/M6 gate on operations completeness and
  measured capability instead of on parity with a system that will not be running.
- The event-code vocabulary becomes a v1 blocker with a cross-repo dependency on `wl-mllib`,
  since nothing downstream can decode a recording without it.
- Schedule risk concentrates rather than spreading: there is no second system to fall back
  on, so the measurement gates are the only thing standing between immature software and
  animal time. They are not negotiable under schedule pressure.
