# Software landscape: closed-loop NHP task control

**As of 2026-08-30.** Every dated claim below was read from the cited primary source
(repo pages or clones, official docs, or the papers) on that date. Claims that could
not be verified are marked UNVERIFIED. Survey performed with Claude research agents;
spot-checked against primary sources.

## Summary

There is no actively maintained, Linux-native, Python-first NHP task-control suite.
The two healthy full suites are NIMH MonkeyLogic (Windows + MATLAB; v2.4.0 released
2026-03-27) and MWorks (macOS-only; commits within days of the survey date). Every
Linux-capable suite is dormant. No Python port of MonkeyLogic exists. Recent macaque
Neuropixels papers show no convergence on any one controller (see methods survey
below). Conclusion: for a Linux/Python/open-source requirement, the realistic path is
a lab-built controller on maintained engines, not adoption of an existing suite.

## Task-control suites

| System | Stack | Status (2026-08) | Closed-loop / gaze story | Custom eye-stream ingest | Verdict for us |
|---|---|---|---|---|---|
| [NIMH MonkeyLogic](https://monkeylogic.nimh.nih.gov/) | MATLAB, Windows 10/11 | Active: v2.4.0 (2026-03-27), forum active into 2026 | Frame-level gaze contingency; 1 kHz analog sampling; measured 0.18 ms median event-marker latency (Hwang et al. 2019) | Yes, first-class: ["My EyeTracker"](https://monkeylogic.nimh.nih.gov/docs_TCPIPEyeTracker.html) custom UDP/TCP interface; analog inputs | Bridge/fallback, not the target (MATLAB + Windows) |
| [MWorks](https://mworks.github.io/) | C++ core + MWEL, macOS only, MIT | Very active: release 0.13 (2024-05); commits 2026-08-25; DiCarlo lab backbone | Real-time state system; gaze windows; embedded Python; LSL input device added 2025; Open Ephys hooks. No published end-to-end latency benchmark (UNVERIFIED) | Via embedded-Python socket reads, external Python conduit, LSL bridge, or C++ plugin | Best maintained open-source NHP suite; fails our Linux constraint |
| [REC-GUI](https://elifesciences.org/articles/40231) (Rosenberg lab) | Python GUI + UDP fabric, Linux, GPL-3 | Dormant: last commit 2020-09-07; Python 2-era | Measured (eLife 2019): 6.79 ms (SD 2.9) full round-trip; 4.71 ms command-to-display; macaque gaze-contingent 240 Hz stereo demonstrated | UDP-native by design (you write the client) | Adopt the architecture pattern, not the code |
| [PLDAPS](https://github.com/HukLab/PLDAPS) (Huk lab) | MATLAB + Psychtoolbox + Datapixx | Dormant: last commit 2022-03-01; no license file | Frame-locked via PTB/Datapixx; no published loop benchmark | DIY MATLAB | Pass (MATLAB, Datapixx-bound, unlicensed, dormant) |
| [Maestro](https://sites.google.com/a/srscicomp.com/maestro/) (Lisberger lab) | C++, Windows + RTX64 (commercial RTOS), MIT | Development formally ended; final release 5.0.2 (2024-12-28) | Hard real-time 1 kHz servo loop (by design; oculomotor-specialized) | No generic network eye interface documented | Pass (EOL, Windows + paid RTOS) |
| [Lablib](https://github.com/MaunsellLab/Lablib-Public-05-February-2026) (Maunsell lab) | Objective-C, macOS | Public snapshots only (latest 2026-02-05, explicitly not updated); active development private | Real-time gaze-contingent state systems; no published benchmarks (UNVERIFIED) | No; Objective-C plugin work | Pass |
| [M-USE](https://github.com/Multitask-Unified-Suite-for-Expts/M-USE) (Womelsdorf lab) | Unity/C#, Windows/macOS, MIT | Active: commits 2026-04-21 | Frame-level (60 Hz); sub-ms alignment post hoc via Arduino SyncBox; no neural hooks | Tobii Spectrum only; custom C# work otherwise | Pass for head-fixed precision rigs; interesting for game-like batteries |
| [ARCADE](https://github.com/esi-neuroscience/ARCADE) (ESI Frankfurt) | MATLAB + C++ services, Windows | Low activity since 2022-2023 | Event-driven state machine; no published benchmarks (UNVERIFIED) | EyeLink-only (dedicated EyeLinkServer) | Pass |
| [Neurostim](https://github.com/klabhub/neurostim) (Krekelberg) | MATLAB + PTB, cross-platform | Last commit 2024-10-16 | PTB frame-locked | DIY MATLAB | Noted; still MATLAB |

## Python-native building blocks (not suites)

- **[PsychoPy](https://github.com/psychopy/psychopy)** (GPL-3; release 2026.2.3,
  2026-08): display/timing engine, not a rig framework. Photodiode-measured on Ubuntu:
  0.34 ms visual onset variability, 4.71 ms constant onset lag
  ([Bridges et al. 2020](https://peerj.com/articles/9414/)). Flip-locked callbacks
  (`callOnFlip`), PTB-derived keyboard timing. Linux TTL out via parallel port,
  LabJack, serial. **No published macaque ephys rig runs PsychoPy as controller**
  (negative search result, 2026-08-30); published NHP use: head-fixed marmoset
  gaze-contingent saccade tasks ([Front Syst Neurosci 2024](https://doi.org/10.3389/fnsys.2024.1478019)),
  rhesus behavioral tasks, marmoset home-cage (CalliCog,
  [Cell Rep Methods 2025](https://doi.org/10.1016/j.crmeth.2025.101034)).
- **Pype2/3** (Mazer): the historical Linux+Python macaque precedent; still in use in
  at least one lab — Pasupathy lab macaque V4 **Neuropixels** paper
  ([J Neurosci 2025](https://doi.org/10.1523/JNEUROSCI.1893-23.2024)) ran on Pype2 —
  but the codebase is dead (last push 2021-03, no license). Existence proof, not a
  foundation.
- **[Heron](https://github.com/Heron-Repositories/Heron)** (MIT;
  [eLife 2025](https://doi.org/10.7554/eLife.91915)): Python + ZeroMQ node graphs;
  explicitly not hard real-time; single-maintainer, quiet ~18 months. Optional glue,
  not a foundation.
- **[pyControl](https://github.com/pyControl/code)** (GPL-3; v2.1.1, 2025-12):
  MicroPython state machines; measured 556 +/- 17 us event-to-output. No display. Role
  here: deterministic I/O sidecar if host-side output jitter proves unacceptable.
- **[Syntalos](https://github.com/syntalos/syntalos)** (GPL-3; v3.1.1, 2026-06;
  [Nat Commun 2025](https://doi.org/10.1038/s41467-025-56081-9)): Linux multi-modal
  acquisition orchestrator; no psychophysics display; duplicates SpikeGLX's role here.
- **Autopilot**: officially maintenance-only since 2024-01. Pass.
- **mkturk** (DiCarlo): browser/tablet home-cage training; different niche.

## Real-time neural layer

| Platform | Measured latency | Neuropixels path | Notes |
|---|---|---|---|
| [SpikeGLX remote SDK](https://billkarsh.github.io/SpikeGLX/) | Vendor: "<4 ms on same computer"; vendor C++ loopback histogram mode ~2 ms; independent MATLAB measurement ~6.5 ms min ([OP-GLX, bioRxiv 2026](https://www.biorxiv.org/content/10.1101/2026.03.04.709636)) | Native | Official C++/C/C#/Python SDKs, Linux clients supported. Details: `spikeglx-realtime.md` |
| [Open Ephys](https://github.com/open-ephys/plugin-GUI) + [Falcon Output](https://open-ephys.github.io/gui-docs/User-Manual/Plugins/Falcon-Output.html) -> [Falcon](https://doi.org/10.1088/1741-2552/aa7526) | **9.241 ms median, SD 1.302, max 13 ms, end-to-end, all 384 ch -> Arduino TTL** (plugin docs; the only independently published Neuropixels-to-TTL number found) | Neuropix-PXI plugin supports NHP probe variants (Windows) | Falcon is C++/Linux from Kloosterman's group (NERF, Leuven) — local collaboration option; repo activity UNVERIFIED (Bitbucket unreachable from survey environment) |
| [BRAND](https://github.com/brandbci/brand) ([J Neural Eng 2024](https://doi.org/10.1088/1741-2552/ad3b3a)) | <600 us inter-node (Redis) at 1,024 ch / 30 kHz; <8 ms end-to-end iBCI | None today (Blackrock ingest only; would need a SpikeGLX node) | MIT, Python/Redis, Linux PREEMPT_RT; active development on non-default branches |
| [LiCoRICE](https://github.com/bil/licorice) | 1 ms ticks, ~18 us jitter (claimed, LCTES'18 WIP paper) | None built in | GPL-2; thin validation record |
| ONIX (Open Ephys) | ~300 us (rodent configurations) | **No NHP-probe headstages** | Effectively rodent-only in 2026 |
| RTXI | ~50 us I/O at 20 kHz | None | Dynamic-clamp class; wrong shape for 384-ch arrays |
| LabStreamingLayer | sub-ms jitter after correction; authors advise against network links inside closed-loop paths ([Imaging Neurosci 2025](https://doi.org/10.1162/IMAG.a.136)) | n/a | Use for sync/glue, never inside the control loop |

## What recent macaque Neuropixels papers actually used (methods survey)

| Paper | Task control | Eye tracking |
|---|---|---|
| Steinemann et al., eLife 2024 (LIP) | REX + Psychtoolbox | EyeLink 1000, 1 kHz |
| Li et al. (Bao lab), Nat Neurosci 2026 ("Triple-N") | NIMH MonkeyLogic | JSMZ / ISCAN |
| Namima et al. (Pasupathy lab), J Neurosci 2025 (V4) | Pype2 (custom Python) | EyeLink 1000, 1 kHz |
| Zhu et al. (Angelucci lab), eLife 2026 (V1, anesthetized) | Psychtoolbox | none |
| Ressmeyer et al., J Neurosci Methods 2026 (LGN) | unnamed; OpenIrisDPI analog out to control PC | OpenIrisDPI |

Takeaway: no convergence; the field runs on legacy, MATLAB, or bespoke Python.

## Watch list

- **[Neurokraken](https://www.biorxiv.org/content/10.64898/2026.06.30.735592v1)**
  (bioRxiv 2026-07-06, Innsbruck): Python-native platform, NHP psychophysics
  demonstrated; v1 preprint, public repo not located at survey time. Re-check quarterly.
- **NERV** (bioRxiv 2025-09, Vanderbilt): Unity/C# framework used for NHP high-density
  ephys; wrong language for us, useful yardstick.
- **BRAND** `neurostream` repo (claims 2048 ch @ 30 kHz, 1 kHz output): re-check if we
  build the neural plane.
- No Python port/fork of MonkeyLogic exists (searched 2026-08-30; only .bhv readers
  and old MATLAB forks).

## Verdicts driving this project

1. Task/display plane: build thin on PsychoPy-as-library, following the REC-GUI
   multi-process/UDP pattern (its measured 6.8 ms loop shows the pattern suffices).
2. Neural plane: SpikeGLX SDK client on the acquisition PC as primary; Open Ephys +
   Falcon as the measured ~9 ms fallback and NERF collaboration path.
3. MonkeyLogic stays as bridge (it is alive, and its custom-UDP eye interface +
   OpenIrisDPI analog out keep rigs productive during development).
