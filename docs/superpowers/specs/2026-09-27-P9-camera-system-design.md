# P9 — The camera system: one headless box, every camera, controlled from expcontroller

- **Status:** designed in conversation with the PI on 2026-09-27, section by section, each
  approved. It is built **after P4d-2b's b2a**: the automatic pause (§4) needs b2a's pause.
- **Date:** 2026-09-27
- **Parent:** S0 (hosts and hardware), S3 §8 (cameras free-run; the sync box records them),
  S5 (eye tracking), S6 (I/O: "We do not trigger the cameras"), and the P4d-2b spec (the
  console, `/health`, b2a's pause, b2b's sign-in)
- **Supersedes:** the single "animal camera" sketched in the P4d-2b spec §6 on 2026-09-27.
  Within the day the PI folded the lab's planned separate behavioral-camera system into
  expcontroller and made every camera dual-purpose (§1).
- **Sibling:** P10, a feasibility spike on reimplementing OpenIrisDPI as a headless
  expcontroller service on this system's framework (§8)

---

## 1. What the PI decided (2026-09-27, asked in plain terms)

- **An always-on view of the animal**, for sleepiness and general state, and **the lab's
  behavioral cameras are the same cameras**: "there is no seperate monitoring vs
  behavioral. the behavioral ones become, in effect, the monitoring ones as well. dual
  purpose."
- **One camera box per rig, headless, part of expcontroller:** "it is more like it is
  treated as a part of expcontroller that happens to run on a seperate box than a seperate
  system." Every control and setting lives in expcontroller.
- **A shared headless camera framework** (acquisition, triggering, recording, control and
  health through expcontroller). This box is its first user. A reimplemented eye tracker
  may be its second (P10).
- **Cameras:**
  - **2 to 4 running in practice, 8 as the maximum the design supports.**
  - **All are FLIR/Teledyne Blackfly S BFS-U3-16S2M-CS**, the eye tracker's own body, chosen
    for a standard body across the rig.
- **Analysis:**
  - uses: face (eyes, mouth, licking), hands and arms, body and posture, and **3D pose
    from several views**;
  - **200 fps**;
  - **the whole session, start to end**;
  - **compressed, visually lossless, on the box's GPU**;
  - **keep everything, and buy storage to fit.**
- **Timing: the primary camera triggers the rest** (§2); the sync box is not changed.
- **Viewing:** only people who can control see the cameras (the box in b2a, people signed
  in to wl-works in b2b). Not open to the LAN.
- **When cameras fail, trials pause, with an override:** "it pauses and says cameras not
  running, but you can still unpause. The warning should also monitor for the cameras
  coming back online and indicate that it is safe to unpause when they are running again."
- **The eye tracker's IR is 940 nm.**

## 2. Hardware and timing

- **The box** is a new S0 role, `rig/cam`. It runs headless Linux, with no screen and no UI
  of its own, and runs `camd`, a daemon that ships in this package beside `taskd`.
- **The camera**, per the maker's page read 2026-09-27:
  - Sony IMX273, mono, global shutter, 1440 × 1080, 226 fps maximum, 3.45 µm pixels;
  - USB 3.1 Gen 1 (Micro-B), CS-mount, no optical filter;
  - 1 opto-isolated input and 1 output, plus 2 non-isolated I/O lines;
  - hardware trigger;
  - bus-powered at 3 W maximum, 29 × 29 × 30 mm, 36 g;
  - Spinnaker SDK.

  No near-infrared quantum efficiency is published, so sensitivity at 940 nm is
  **UNVERIFIED** and is measured at bring-up (§6).
- **The box's parts, sized to 8 cameras at 200 fps:**
  - **Raw rate:** about 311 MB/s per camera, arithmetic from the sensor's size, 8-bit
    mono. About 2.5 GB/s across 8.
  - **USB:** one USB3 host controller per camera.
  - **Storage:** NVMe.
  - **Encoding:** a GPU whose encoder is **measured** compressing 8 such streams before any
    card is chosen. Consumer NVIDIA cards cap simultaneous encoder sessions; the current
    cap is **UNVERIFIED** and is checked against NVIDIA's own documentation first.
  - **Lenses:** each lens carries a 940 nm band-pass filter.
- **Synchronized exposure, for 3D.** One **primary** camera free-runs at 200 fps. Its output
  line drives every other camera's trigger input through a small **fan-out board**, since
  one output line does not drive seven inputs. All cameras expose at the same instant, so
  frame *N* of every camera is one moment.
- **Alignment with the neural data, by the lab's existing design, unchanged** (S3 §8,
  wl-sync since 2026-08-16):
  - the sync box does not trigger cameras;
  - the primary samples the sync box's barcode (`BARCODE_RAW`, on a camera-facing BNC) on an
    input line **every frame**;
  - the camera group's `ExposureActive` goes to the sync box's behavior frame-time input
    (GPIO27);
  - every camera stamps each frame's number and exposure time into the frame (chunk data),
    so a dropped or misaligned frame is detected and named, never guessed.
- **Light.** At 200 fps an exposure is at most 5 ms. The plan, in order:
  1. **Passive:** the cameras see by the eye tracker's own 940 nm light, through their
     band-pass filters.
  2. If that is too dark, the design **returns to the PI with measured options.** It does
     not add a lamp on its own. The options are:
     - a 940 nm lamp strobed only in the tracker's off-time, which needs the tracker and
       the cameras on one clock (P10);
     - 850 nm, only if the tracker's own filter rejects it and its faint glow is shown
       invisible from the animal's position.

## 3. Control, all in expcontroller

- **Configuration:** a versioned per-rig camera file lists:
  - the serial numbers and which camera is primary;
  - names such as `face-left`;
  - region of interest, 200 fps, exposure, gain and encoder settings.

  The session references it, as it references the bounds file, and its copy is saved in
  the session's `config.json`.
- **Changes during a session:** exposure and gain can be changed from the console. Every
  change is recorded with who made it, like a task setting.
- **Recording span:** from the session's open until the return to the cage is recorded, since
  the animal is in the chair until then. Nobody touches the box.
- **Protocol:** `camd` takes commands and publishes status the way `taskd` does (a
  request/reply socket and a publish socket). `taskd` starts and stops recording and reads
  camera health. `wlx serve` reads status and the preview. **Browsers never talk to the box**;
  the console relays everything.

## 4. The console, `/health`, and failure

- **A camera pane:**
  - one tile per camera, with a preview at a few frames per second (thinned on the box,
    never taken from the recording path), its frame rate, dropped frames and recording
    state;
  - the box's free disk;
  - click a tile to enlarge it;
  - visible only to people who can control.
- **`/health`** gains a camera reading, and is `degraded` while cameras are down mid-session.
- **Failure pauses trials** (§1):
  - `taskd` checks camera health **at each trial boundary**, never inside a trial;
  - if a configured camera has stopped reporting, reports an error, or drops frames beyond a
    threshold, trials pause through b2a's pause, attributed to `cameras`, with a banner
    naming which cameras are not running;
  - the operator may resume anyway, and the override covers this outage;
  - the banner keeps watching, and when every camera is healthy it says *cameras are back
    — safe to resume*, but never resumes on its own;
  - a new outage pauses again;
  - at session open, cameras not ready, including too little disk (§5), opens the session
    paused with the same banner and override;
  - the out-of-cage limit is enforced during an automatic pause as during any pause (b2a).

## 5. Storage

- **During the session**, video goes to the box's NVMe. Its size is set from **measured**
  bitrates for 8 cameras at 200 fps over the longest possible session (the 12-hour
  out-of-cage limit), plus margin. It is checked at session open (§4).
- **Afterwards**, the video, its `bcam` sidecar and the camera log join the session's package
  (P4d-2b's b6), bound for wl-nas.
- **Until wl-nas exists** (it does not yet: `wl-stack/docs/data-access.md`, read
  2026-09-27), video stays on the box and **is never deleted before a copy elsewhere is
  verified by checksum.**

## 6. Testing and bring-up

- **Sim first.** `camd` has a simulated camera backend:
  - synthetic frames;
  - simulated primary/secondary triggering;
  - frame stamps and barcode samples;
  - dropped frames and failures on demand.

  The tests cover:
  - the control protocol;
  - the output, checked against wl-preproc's own `bcam` sidecar model, as `/health` is
    checked against `HealthResponse`;
  - the automatic pause, its override and the recovery notice;
  - the console pane;
  - end to end: a simulated session, the simulated box and the console together.
- **Bring-up checks on real hardware** (added to the verification list):
  1. All cameras' exposure stamps agree, and wl-preproc decodes the barcode from the primary.
  2. 8 cameras at 200 fps for 12 hours with no drops, and the GPU encoder keeps up.
  3. The eye tracker's P1 and P4 reflections are unaffected, and the passive 940 nm image
     is bright enough.
  4. No added noise in a real neural recording.
  5. The preview never disturbs recording.

## 7. Outside this repository (asks, not assumptions)

- **wl-preproc: amend the `bcam` sidecar contract.**
  - `REQUIRED_TRIGGER_SOURCE = "syncbox"` and `extract_bcam`'s "frame times are known by
    construction" (`wl_preproc/contracts/sidecar.py`, `timebase/extract.py`, read
    2026-09-27) predate wl-sync's 2026-08-16 change to free-running cameras.
  - Ask for a trigger source that says the primary camera triggered the group, and for the
    per-frame `digital_line` and `frame_rate_hz` fields to become required.
- **wl-stack: adopt `rig/cam`** with S0's other proposed roles. `wl-manifest` accepts free
  role strings, so no code change is needed there.
- **wl-nas: it has to exist.** That is infrastructure, and the PI's.
- **A license decision, an ADR, before P9 is planned:**
  - the camera library: FLIR's Spinnaker/PySpin (proprietary) or Aravis (LGPL);
  - the encoder library: FFmpeg with NVENC, which is LGPL or GPL depending on the build.

  The terms are checked against their primary sources and put to the PI.

## 8. P10: the eye-tracker spike — done 2026-09-27

The spike (`docs/research/2026-09-27-p10-dpi-spike.md`) recommends **building a clean-room
tracker in C++, on conditions**:

- validation against OpenIrisDPI on the same recorded frames comes first;
- blink and validity rejection are designed in (the published method reports confident,
  wrong P4 positions on partial blinks);
- P4 near the pupil edge needs handling (a pull of 7–9 px at the published 15 px region,
  on synthetic frames);
- two cameras at 500 Hz are proven on the rig's Linux.

Its numbers are from a development laptop under load, on synthetic eyes, and are not
claims about the rig.

**The PI's answers:**

- validate on raw eye video from our own rig, once the cameras arrive;
- **match or beat OpenIrisDPI on everything** before switching;
- a C++ core, with its ADR;
- invalid frames reach expcontroller as "no sample";
- OpenIrisDPI stays live, and the new tracker is validated offline only.

So P10's build follows P9's hardware: the validation video needs the cameras.

## 9. Not in this package

- Pose estimation itself (DeepLabCut, anipose): offline, downstream of wl-preproc
- The eye tracker's reimplementation (P10's spike decides whether it happens)
- b6, the end-of-session package and its transfer: P4d-2b
