# ADR-0003: Messaging and transport

- Status: Proposed
- Date: 2026-08-30

## Context
Three data paths with different needs: eye samples (high rate, latest-wins), neural
features (high rate, latest-wins, cross-machine), control/telemetry (reliable,
low rate). Plus the hardware-truth rule (architecture.md, principle 2).

## Decision (proposed)
- Eye: consume OpenIris's native UDP poll protocol unmodified (port 9003,
  WAITFORDATA -> JSON); poll >= display rate; local staleness accounting.
- Neural features + control/telemetry: ZeroMQ (PUB/SUB + REQ/REP) with msgpack,
  schema-versioned messages, on a dedicated point-to-point link for features.
- Every scientifically meaningful event is mirrored as a hardware TTL/event word;
  network messages are never the timing record.

## Alternatives considered
- Redis streams (BRAND-style): proven sub-ms IPC, but adds a broker to operate on
  every rig; revisit if we later run deep decoder graphs (then interop with BRAND
  becomes an argument for it).
- LSL: sync/glue only — its own authors advise against network links inside
  closed-loop paths (Imaging Neurosci 2025).
- Raw UDP everywhere: fine for eye (it is the tracker's protocol), too lossy/ad hoc
  for control-plane semantics.

## Consequences
Two small, boring dependencies (pyzmq, msgpack). Message schemas live in one module
with golden-file tests; version field from day one.
