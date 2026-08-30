# SpikeGLX real-time access: facts and consequences

**As of 2026-08-30.** Sources: billkarsh.github.io/SpikeGLX (docs, release notes, help
pages), the SDK repos (read directly), and the cited preprint.

## SDK facts (verified)

- Official remote API over TCP/IP with SDKs in **C++, C, C#, and Python**
  ([SpikeGLX-CPP-SDK](https://github.com/billkarsh/SpikeGLX-CPP-SDK), Python package
  `sglx_pkg` via ctypes; [MATLAB SDK](https://github.com/billkarsh/SpikeGLX-MATLAB-SDK)).
  **Linux clients supported** (added 2024-06). SpikeGLX itself remains Windows-only.
  Repos actively maintained (SDK commit 2026-07-21; app commit 2026-08-28).
- Key calls: `sglx_fetchLatest` (most recent samples, no index bookkeeping),
  `sglx_fetch` (from sample index), `sglx_mapSample` (cross-stream time mapping),
  channel-subset and integer downsample arguments on both fetches.
- **Server-side filtered AP stream** (`js = -2`, since release 20240129): SpikeGLX
  maintains a bandpassed, globally demuxed-CAR stream; set band edges on the IM tab.
  The CAR + filter cost is paid inside SpikeGLX's C++, not in our client. This is the
  intended MUA feed.
- **Latency** (vendor): "Fetch data with low latency (<4 ms on same computer)";
  the SDK's shipped closed-loop test histogram (NP 2.0, C++ client, same-machine
  loopback) concentrates at ~1.5-2.5 ms with a tail to ~4 ms.
- **Independent measurement**: OP-GLX ([bioRxiv 2026.03.04.709636](https://www.biorxiv.org/content/10.1101/2026.03.04.709636)),
  a MATLAB client on simulated recordings: minimum ~6.5 ms end-to-end round trip.
  Treat this as the realistic bound for non-C++ clients.
- **"Low latency" mode** (IM Setup tab): reduces closed-loop latency by >1 ms but
  "drives the CPU 50%+ harder and reduces the maximum number of probes you can safely
  run concurrently." Real trade-off on multi-probe rigs — budget CPU accordingly.
- Caveats stated in the docs: lowest latency is same-machine loopback (127.0.0.1);
  WSL2 does not get the loopback path; C++ clients are fastest (Python adds
  conversion/copies); connection handles time out after 10 s idle and reconnects can
  take tens of ms (keep the loop hot); multithreaded clients need one handle per
  thread.

## OneBox / PXIe hardware facts (verified)

- OneBox: 2 headstage ports, up to 12 analog inputs, up to 12 analog outputs; DAC
  settable during a run via SDK (`sglx_obx_AO_set`); **WavePlayer** on DAC-0 can be
  armed via SDK and **hardware-triggered by a TTL on AI-1** (no software in the
  trigger path). Use it for stimulus/feedback waveforms; our controller supplies only
  the trigger edge.
- **No onboard neural threshold-to-TTL exists anywhere** in OneBox or the PXIe
  basestations. Every neural-contingent decision transits host software.
- Corollary: never route the stim trigger back out through the SpikeGLX API
  (`sglx_ni_DO_set` / `sglx_obx_AO_set` are API round trips). The task/neural plane
  asserts TTLs from its own DAQ or microcontroller.

## Consequences for our architecture

1. The fetch client (`neurofeatd`) lives **on the acquisition PC, in C++, over
   loopback** — the only configuration the vendor numbers actually describe — and
   publishes compact MUA feature vectors (tens of floats) over the network. Python
   stays on the far side of the wire.
2. Expected neural-event-to-TTL budget on this path: ~3-6 ms (estimate; to be
   measured per validation protocol V4 before any scientific claim).
3. **Fallback with a published number**: Open Ephys (Neuropix-PXI supports NHP probe
   variants, Windows) + Falcon Output plugin -> Linux consumer: 9.241 ms median /
   13 ms max, end-to-end, 384 channels, TTL verified by loopback into the PXIe
   ([plugin docs](https://open-ephys.github.io/gui-docs/User-Manual/Plugins/Falcon-Output.html)).
   Falcon itself is from Kloosterman's group (NERF, Leuven) — a local collaboration
   to pursue regardless.
4. Every loop event (feature publication, decision, TTL) is mirrored into the
   SpikeGLX-recorded digital streams so true closed-loop latency is measured from
   recorded data, not asserted.
