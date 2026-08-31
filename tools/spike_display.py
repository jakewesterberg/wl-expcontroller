#!/usr/bin/env python3
"""SPIKE — throwaway. Is a thin display stack good enough to replace PsychoPy?

ADR-0002 was accepted and reopened the same day. This answers the question it was
reopened on: can a window, a vsync-locked flip and fragment shaders do what the rig
needs, without 81 dependencies and a Python ceiling?

**Not production code.** It exists to produce a number and an opinion. What survives
into `DisplayAdapter` gets written again, test-first.

    python tools/spike_display.py --seconds 5
    python tools/spike_display.py --seconds 5 --fullscreen

Reports the frame-interval distribution, which is a proxy for V1 until a photodiode
exists -- it measures what the GPU handed the compositor, not what reached the panel.
Only V1 measures the latter, and that distinction is the whole reason V1 exists.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time

import glfw
import moderngl
import numpy as np

# One quad; everything is a fragment shader over it. The vocabulary in S1a is
# shader-shaped -- Gabor, grating, plaid, checkerboard, noise, disc -- which is the
# thing that makes a thin stack plausible rather than merely lighter.
VERTEX = """
#version 330
in vec2 in_pos;
out vec2 uv;
void main() {
    uv = in_pos;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

FRAGMENT = """
#version 330
in vec2 uv;
out vec4 colour;

uniform vec2  viewport_centre;   // in normalised device coords
uniform vec2  deg_per_ndc;       // degrees subtended per NDC unit
uniform vec2  gabor_at;          // degrees, cyclopean
uniform float sf;                // cycles per degree
uniform float orientation;       // radians
uniform float sigma;             // degrees
uniform float contrast;
uniform float phase;
uniform float flip_patch;        // alternates every frame: the frame clock
uniform float task_patch;        // stimulus onset

void main() {
    vec2 deg = (uv - viewport_centre) * deg_per_ndc;

    // Photodiode patches live in a bottom strip outside both viewports
    // (optics drawing §5). Drawn every frame, unconditionally: a frame clock that
    // stops during an abort is not a frame clock.
    if (uv.y < -0.93) {
        if (uv.x > -0.98 && uv.x < -0.88) { colour = vec4(vec3(flip_patch), 1.0); return; }
        if (uv.x > -0.85 && uv.x < -0.75) { colour = vec4(vec3(task_patch), 1.0); return; }
        colour = vec4(0.0, 0.0, 0.0, 1.0); return;
    }

    vec2 d = deg - gabor_at;
    float envelope = exp(-dot(d, d) / (2.0 * sigma * sigma));
    float carrier = cos(6.2831853 * sf * (d.x * cos(orientation) + d.y * sin(orientation)) + phase);
    float lum = 0.5 + 0.5 * contrast * envelope * carrier;
    colour = vec4(vec3(lum), 1.0);
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()

    if not glfw.init():
        print("glfw failed to initialise", file=sys.stderr)
        return 1
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)

    monitor = glfw.get_primary_monitor() if args.fullscreen else None
    mode = glfw.get_video_mode(glfw.get_primary_monitor())
    width, height = (mode.size.width, mode.size.height) if args.fullscreen else (960, 600)
    window = glfw.create_window(width, height, "wl-expcontroller display spike", monitor, None)
    if not window:
        glfw.terminate()
        print("could not create a window", file=sys.stderr)
        return 1

    glfw.make_context_current(window)
    glfw.swap_interval(1)  # vsync. Without this the numbers below mean nothing.

    ctx = moderngl.create_context()
    program = ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
    quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4"))
    vao = ctx.vertex_array(program, [(quad, "2f", "in_pos")])

    program["viewport_centre"].value = (0.0, 0.0)
    program["deg_per_ndc"].value = (17.0, 19.0)   # S0 §5.2 at 57 cm
    program["gabor_at"].value = (0.0, 0.0)
    program["sf"].value = 2.0
    program["orientation"].value = math.radians(45.0)
    program["sigma"].value = 2.0
    program["contrast"].value = 0.8

    intervals: list[float] = []
    previous = time.perf_counter()
    started = previous
    frame = 0

    while not glfw.window_should_close(window) and time.perf_counter() - started < args.seconds:
        frame += 1
        program["phase"].value = frame * 0.2
        program["flip_patch"].value = float(frame % 2)      # the frame clock
        program["task_patch"].value = 1.0 if (frame // 60) % 2 else 0.0
        ctx.clear(0.5, 0.5, 0.5)
        vao.render(moderngl.TRIANGLE_STRIP)
        glfw.swap_buffers(window)
        # **`swap_interval(1)` is not enough.** Without forcing the pipeline to
        # drain, swaps return before the GPU has finished and the loop free-runs --
        # the first version of this spike showed 36% long frames and a 0.43 ms
        # minimum against PsychoPy's 1.8% and 1.77 ms on the same machine, which
        # looked like evidence against the thin stack and was evidence against this
        # loop. PsychoPy does this deliberately; knowing to is a large part of what
        # its timing pedigree actually buys.
        ctx.finish()
        glfw.poll_events()
        now = time.perf_counter()
        intervals.append((now - previous) * 1000.0)
        previous = now

    glfw.terminate()

    warm = intervals[10:]  # the first frames include window mapping
    if len(warm) < 30:
        print("too few frames to say anything")
        return 1
    median = statistics.median(warm)
    print(f"\n  frames        {len(warm)}")
    print(f"  median        {median:.3f} ms  ({1000 / median:.1f} Hz)")
    print(f"  mean          {statistics.mean(warm):.3f} ms")
    print(f"  sd            {statistics.pstdev(warm):.3f} ms")
    print(f"  min / max     {min(warm):.3f} / {max(warm):.3f} ms")
    dropped = sum(1 for i in warm if i > median * 1.5)
    print(f"  long frames   {dropped}  ({100 * dropped / len(warm):.2f}%)")
    print(
        "\n  This is the swap interval, not the photodiode. It says the loop is "
        "vsync-locked;\n  it does not say when light reached the panel. Only V1 says that."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
