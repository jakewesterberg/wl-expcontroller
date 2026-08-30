# OpenIrisDPI: facts and integration plan

**As of 2026-08-30.** Sources: the OpenIris and OpenIrisDPI repos/wikis (read
directly), the ETRA 2024 OpenIris paper, and the OpenIrisDPI paper.

## System facts (verified)

- **OpenIris** ([repo](https://github.com/ocular-motor-lab/OpenIris)): C#/.NET 4.8,
  **Windows-only**, AGPL-3.0. Plugin architecture (cameras, tracking pipelines,
  calibration). Paper: Sadeghi, Ressmeyer, Yates, Otero-Millan,
  [ETRA 2024](https://doi.org/10.1145/3649902.3653348). Last commit 2025-08-18.
- **OpenIrisDPI plugin** ([repo](https://github.com/ryan-ressmeyer/OpenIrisDPI)):
  GPL-3.0, last commit 2026-04-14. Paper: Ressmeyer, Otero-Millan, Horwitz, Yates,
  [J Neurosci Methods 2026](https://doi.org/10.1016/j.jneumeth.2026.110693).
  Verified numbers from the paper:
  - 500 Hz binocular on a consumer CPU (no GPU); FLIR BFS-U3-16S2M-CS cameras;
    complete system under $5,000.
  - In vivo (macaque) precision 0.39-0.44 arcmin (azimuth/elevation) vs 1.55-1.82
    arcmin for P-CR on the same rig.
  - Frame processing 1.1 +/- 0.1 ms median — **but ~2% of frames take >= 10 ms
    (max ~50 ms)** from OS preemption.
  - Validated in two rhesus macaques including Neuropixels NHP recordings (LGN).

## Output interfaces (verified in source/wiki)

1. **UDP, port 9003** (base 9000 + 3): send `WAITFORDATA`, receive a JSON string with
   pupil center, pupil diameter, CR center, and P4 center. **Poll-based** protocol.
   A worked Python client ships in the repo
   ([PythonUDP/openiris_udp_client.py](https://github.com/ryan-ressmeyer/OpenIrisDPI/blob/master/PythonUDP/openiris_udp_client.py)).
2. Raw TCP (port 9002), WCF NetTcp (9000), HTTP/SOAP (9001) — remote control API
   (`GetCurrentData`, `StartRecording`, `RecordEvent`, settings, etc.).
3. **Analog out** via companion OpenIrisDAC app + ACCES USB-AO16-8E DAC (6 channels:
   eye X/Y per eye + pupils). Adds ~3-4 ms; the paper notes this "may limit the use
   of this signal for gaze-contingent applications." This is our **MonkeyLogic bridge
   path** (drops into ML analog eye inputs or a NIDQ AI channel).
4. **Sync:** camera GPIO takes a shared digital sync line for lossless offline
   alignment. Offline reconstruction is the timing ground truth, always.
5. No LSL, no ROS, no first-party bridges to any task controller (grep of both repos:
   zero hits for LSL/ROS/MonkeyLogic/MWorks/PsychoPy).

## Design consequences for our controller

- The eye client polls at (at least) display frame rate, timestamps locally on
  receipt, and treats each sample as "latest available," not as a clocked stream.
- **Gaze-window logic must tolerate the ~2% >= 10 ms tracker stalls**: hold-last with
  a staleness ceiling, grace periods on fixation windows, never abort a trial on a
  single stale sample. Stall frequency/duration gets measured on our hardware
  (validation protocol V3) before window parameters are finalized.
- Calibration (fixation-grid mapping raw DPI signal -> degrees, per animal, with
  drift correction) is ours to build; OpenIris calibration plugins target its own
  display, not our task display.
- The tracker runs on its own Windows PC. License note: AGPL/GPL on the tracker side
  does not constrain our code — separate process, network protocol (see ADR-0004).
- Camera GPIO sync line joins the rig-wide sync fabric (architecture.md, sync
  conventions) from day one.
