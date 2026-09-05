# ADR-0004: License for eventual public release

- Status: **Accepted 2026-09-05** — Apache-2.0. Superseded the 2026-08-30 lean toward GPL-3.
- Date: 2026-08-30, decided 2026-09-05

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

## Current lean (superseded)
(a), unless a concrete reuse scenario needs permissive licensing. Revisit at M7.

## Decision: Apache-2.0

**The lean's own escape clause fired.** It said GPL-3 "unless a concrete reuse
scenario needs permissive licensing", and there is one: **ADR-0007 plans to move
`tasks/` and the event allocation into `wl-mllib`.** Apache-2.0 code can be taken into
a GPL-3 work but not the reverse, so a GPL-3 core would make that move illegal and
wall this repo off from a stack that is otherwise uniformly Apache-2.0 — `wl-preproc`,
`wl-sync`, `wl-works`, `wl-orchestrator`, `wl-stack`.

**And the premise was false.** The whole case for (a) was "honest given the PsychoPy
import". *There is no PsychoPy import*, and there never has been: not in
`pyproject.toml`, not in the tree, not in 73 commits of history. ADR-0002 is deferred
to V1 and `tools/spike_display.py` exists to ask whether a thin stack can replace
PsychoPy entirely — glfw (zlib) and moderngl (MIT), both permissive. The copyleft
obligation this ADR was reasoning about is not one this project has incurred.

The other constraints in Context are unchanged and none of them forces copyleft:
OpenIris (AGPL-3) and OpenIrisDPI (GPL-3) are separate processes spoken to over UDP,
and every runtime dependency is permissive.

**Apache-2.0 over MIT** for the explicit patent grant, and because it is what the rest
of the family already uses; `wl-sync` is public under it already.

**If ADR-0002 ever chooses PsychoPy**, the adapter that imports it goes in a *separate*
package under GPL-3, behind the `DisplayAdapter` seam that already exists for this
purpose. That is option (b), taken then rather than now, and the seam is what keeps it
cheap. **The core does not become GPL because a display backend did.**

## Consequences
`LICENSE` is Apache-2.0, matching `wl-preproc` byte for byte. The repository is public
as of 2026-09-05. Dependency additions still require a license entry in the inventory
below (CLAUDE.md policy), and an added dependency under a copyleft license is now a
decision that reopens this ADR rather than a routine addition.

**Not settled here: who the copyright holder is.** No `wl-*` repository states one --
`wl-sync` is public with the stock placeholder -- and the answer depends on KU Leuven's
IP terms for software written by lab staff. It is one line in each repo whenever it is
decided, and worth deciding once across the family rather than per repo.

## Dependency inventory

Maintained per CLAUDE.md's dependency policy: a new dependency needs a one-line
justification and a license entry here.

| Dependency | License | Why |
|---|---|---|
| `pydantic` >= 2 | MIT | Bounded configuration and session-snapshot validation |
| `numpy` >= 1.24 | BSD-3-Clause | Least squares for the gaze calibration fit, and the SVD behind its conditioning gate. The gate is `wl-preproc`'s and is computed with numpy on their side; agreeing with their numerics on a refusal threshold is worth more than saving the dependency. Fitting only -- applying a map in the trial loop is plain float arithmetic (`calibration.EyeMap.degrees`) |
| `pytest` >= 8 (dev) | MIT | Test runner |
| `pyyaml` >= 6 (contract extra) | MIT | Only so `wl-preproc`'s own `eye/expcontroller.py` can be imported by the contract tests, which read YAML. Never installed on a rig, and deliberately not `pip install -e ./wl-preproc`, which would pull DataJoint, Kilosort and SpikeInterface |
