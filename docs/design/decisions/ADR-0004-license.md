# ADR-0004: License for eventual public release

- Status: Open (decide before public release; inventory maintained meanwhile)
- Date: 2026-08-30

## Context
- PsychoPy is GPL-3: a distributed work importing it must be GPL-compatible; the
  distribution as a whole is effectively GPL-3.
- OpenIris (AGPL-3) and OpenIrisDPI (GPL-3) run as separate processes spoken to over
  a network protocol — no license constraint on our code.
- SpikeGLX SDK: Janelia BSD-3-Clause-style (permissive; redistribution permitted).
- pyzmq (BSD), msgpack (Apache-2.0), NumPy (BSD): permissive.

## Options
(a) GPL-3 for the whole repo — simplest, honest given the PsychoPy import; common in
this niche (pyControl, REC-GUI, Syntalos are GPL). (b) MIT core + isolated GPL
display package — cleaner reuse story, real maintenance cost. (c) Defer engine
coupling via the DisplayAdapter seam and decide at release.

## Current lean
(a), unless a concrete reuse scenario needs permissive licensing. Revisit at M7.

## Consequences meanwhile
Dependency additions require a license entry here (CLAUDE.md policy). No LICENSE file
in the repo until this ADR is Accepted; repo stays private.
