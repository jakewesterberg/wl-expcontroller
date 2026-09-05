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

## Dependency inventory

Maintained per CLAUDE.md's dependency policy: a new dependency needs a one-line
justification and a license entry here.

| Dependency | License | Why |
|---|---|---|
| `pydantic` >= 2 | MIT | Bounded configuration and session-snapshot validation |
| `numpy` >= 1.24 | BSD-3-Clause | Least squares for the gaze calibration fit, and the SVD behind its conditioning gate. The gate is `wl-preproc`'s and is computed with numpy on their side; agreeing with their numerics on a refusal threshold is worth more than saving the dependency. Fitting only -- applying a map in the trial loop is plain float arithmetic (`calibration.EyeMap.degrees`) |
| `pytest` >= 8 (dev) | MIT | Test runner |
