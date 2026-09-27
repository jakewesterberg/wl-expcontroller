"""Synthetic DPI camera frames with known ground truth (P10 spike; research artifact).

Every number here is either cited (see ../2026-09-27-p10-dpi-spike.md, "Sources") or
marked ASSUMED. Nothing here was taken from OpenIris or OpenIrisDPI source code.

Coordinate convention: pixel (row r, col c) covers [c-0.5, c+0.5] x [r-0.5, r+0.5], so
a pixel's center is at integer (x=c, y=r). Ground-truth positions and every estimate use
this convention.

Units: image intensities are 8-bit sensor counts (DN). Positions are pixels on the sensor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
from scipy.special import ndtr  # standard normal CDF

# --------------------------------------------------------------------------------------
# Optical model: object space (the eye) -> sensor pixels
# --------------------------------------------------------------------------------------

# Sensor pixel pitch, BFS-U3-16S2M-CS (Sony IMX273): 3.45 um (maker's page, read
# 2026-09-27 for the P9 spec).
PIXEL_UM = 3.45

# ASSUMED magnification. Paper: 100 mm macro lens, eye 57 cm from the camera. Thin lens,
# 570 mm taken as the object distance: m = f / (u - f) = 100 / 470 = 0.2128.
# (If 570 mm were the whole object-to-sensor track instead, m = 0.294.)
MAGNIFICATION = 100.0 / (570.0 - 100.0)
UM_PER_PX = PIXEL_UM / MAGNIFICATION  # 16.2 um of eye per sensor pixel

# Relative P1-P4 motion per arcmin of eye rotation, object space. Wu et al. 2023 (J Vis
# 23(5):4), ray tracing a human schematic eye: 2.4 um/arcmin. Paraxial check from the same
# paper: d*sin(rotation) with d = 7.7 mm (Gullstrand) -> 2.24 um/arcmin.
DPI_UM_PER_ARCMIN_HUMAN = 2.4
# ASSUMED: a macaque eye is smaller; d scaled by 0.85. UNVERIFIED, a sensitivity row only.
MACAQUE_D_RATIO = 0.85

# Wu et al. 2023: P4 travels about +/-4.7 mm for +/-20 deg (human model) -> 0.235 mm/deg.
P4_UM_PER_DEG = 4700.0 / 20.0
DIFF_UM_PER_DEG = DPI_UM_PER_ARCMIN_HUMAN * 60.0  # 144 um/deg
P1_UM_PER_DEG = P4_UM_PER_DEG - DIFF_UM_PER_DEG  # P4 moves faster than P1 (Wu et al.)
# ASSUMED: pupil plane about 10.3 mm in front of the rotation center (rotation center
# 13.8 mm behind the cornea, cited by Wu et al. from Fry & Hill 1962; pupil ASSUMED 3.5 mm
# behind the cornea). Pupil center then moves 10.3 mm/rad.
PUPIL_UM_PER_DEG = 10300.0 * math.pi / 180.0

# Paper: cameras 35 deg below the line of sight. ASSUMED consequence: vertical
# displacements in the eye's frontal plane are foreshortened by cos(35 deg).
CAMERA_ELEVATION_DEG = 35.0
VERTICAL_FORESHORTENING = math.cos(math.radians(CAMERA_ELEVATION_DEG))


def arcmin_per_px(axis: str, species: str = "human") -> float:
    """Arcmin of eye rotation per pixel of P1-P4 displacement, under the stated model."""
    gain = DPI_UM_PER_ARCMIN_HUMAN * (MACAQUE_D_RATIO if species == "macaque" else 1.0)
    if axis == "y":
        gain *= VERTICAL_FORESHORTENING
    return UM_PER_PX / gain


# --------------------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------------------


@dataclass
class Scene:
    """One camera's view of one eye. All intensities are DN before noise.

    "FIG2" marks a value measured from the paper's published Figure 2 (the OpenIris GUI
    screenshot, bioRxiv v2 p. 9): the 720 x 450 frame is displayed at 0.605 scale, derived
    from the 172 px and 168 px pupil-search circles drawn on it. "FIG1B" marks a ratio
    measured from Figure 1b. Display mapping of both figures is unknown, so intensities
    taken from them are ASSUMED to be linear.
    """

    width: int = 720  # the paper's 500 Hz ROI: 720 x 450
    height: int = 450
    pupil_level: float = 8.0  # ASSUMED: FIG1B pupil/iris ~0.03-0.04, plus a black level
    iris_level: float = 75.0  # FIG2: iris 73-80 in the displayed frame
    iris_texture_sd: float = 8.0  # ASSUMED
    skin_level: float = 105.0  # FIG2: lid/skin 88-121
    pupil_a_px: float = 105.0  # FIG2: right-eye pupil 210 x 193 camera px
    pupil_b_px: float = 97.0
    pupil_edge_sd: float = 1.5  # ASSUMED edge blur, px
    iris_radius_px: float = 330.0  # ASSUMED; the iris fills the frame in FIG2
    # Reflections. Wu et al. 2023: P1 largely saturated; P4 "smaller and weaker", peak
    # irradiance "almost two orders of magnitude" below P1 -> ASSUMED ratio 80.
    # FIG2: P4 peak ~1.2-1.7x the iris level; FIG1B: ~1.5x -> base amplitude 90 DN.
    # FIG1B: P4 FWHM ~3.0 % of the pupil diameter (-> sigma ~2.5 px at a 200 px pupil);
    # FIG2 left eye: FWHM ~3.8 camera px (sigma ~1.6). Base sigma 2.0 px, swept.
    p4_amp: float = 90.0
    p1_over_p4: float = 80.0
    p1_sigma: float = 2.5  # ASSUMED; gives a ~13 px saturated disc, as in FIG2
    p4_sigma: float = 2.0
    # P2 (posterior cornea) abuts P1 (paper, Fig. 2 caption). ASSUMED 1/100 of P1, 6 px up.
    p2_rel: float = 0.0
    p2_offset: tuple[float, float] = (1.0, -6.0)
    # Noise: variance = read^2 + I/e_per_dn, times noise_scale^2. ASSUMED read noise
    # 1.0 DN and 20 e-/DN; the paper reports QE < 10 % at 940 nm, which is why the scale
    # is swept rather than fixed.
    read_noise_dn: float = 1.0
    e_per_dn: float = 20.0
    noise_scale: float = 1.0
    saturation: float = 255.0


@dataclass
class Truth:
    pupil_x: float
    pupil_y: float
    pupil_a: float
    pupil_b: float
    p1_x: float
    p1_y: float
    p4_x: float
    p4_y: float
    visible: bool = True  # False for a blink

    @property
    def dpi(self) -> tuple[float, float]:
        return (self.p1_x - self.p4_x, self.p1_y - self.p4_y)


def geometry(
    scene: Scene,
    az_deg: float = 0.0,
    el_deg: float = 0.0,
    head_dx_px: float = 0.0,
    head_dy_px: float = 0.0,
    p4_rel_pupil: tuple[float, float] = (35.0, -25.0),
    p1_rel_pupil: tuple[float, float] = (-10.0, 51.0),
) -> Truth:
    """Feature positions for an eye rotation plus a head translation.

    Primary-position layout from FIG2 (right eye): P4 35 px right of and 25 px above the
    pupil center, P1 10 px left of and 51 px below it (P1-P4 separation 88 px). ASSUMED
    that the screenshot's gaze is near primary. Rotation moves pupil, P1 and P4 with the
    different gains above; head translation moves all three together.
    """
    cx0, cy0 = scene.width / 2.0, scene.height / 2.0
    fx = 1.0 / UM_PER_PX
    fy = VERTICAL_FORESHORTENING / UM_PER_PX

    def move(gain_um_per_deg: float) -> tuple[float, float]:
        # Image y grows downward; upward gaze moves features up (ASSUMED sign).
        return (gain_um_per_deg * az_deg * fx, -gain_um_per_deg * el_deg * fy)

    pdx, pdy = move(PUPIL_UM_PER_DEG)
    p4dx, p4dy = move(P4_UM_PER_DEG)
    p1dx, p1dy = move(P1_UM_PER_DEG)
    return Truth(
        pupil_x=cx0 + pdx + head_dx_px,
        pupil_y=cy0 + pdy + head_dy_px,
        pupil_a=scene.pupil_a_px * math.cos(math.radians(az_deg)),
        pupil_b=scene.pupil_b_px * math.cos(math.radians(el_deg)),
        p1_x=cx0 + p1_rel_pupil[0] + p1dx + head_dx_px,
        p1_y=cy0 + p1_rel_pupil[1] + p1dy + head_dy_px,
        p4_x=cx0 + p4_rel_pupil[0] + p4dx + head_dx_px,
        p4_y=cy0 + p4_rel_pupil[1] + p4dy + head_dy_px,
    )


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def smooth_field(h: int, w: int, sd: float, corr_px: float, rng: np.random.Generator) -> np.ndarray:
    """Zero-mean spatially correlated texture (Gaussian-filtered white noise)."""
    from scipy.ndimage import gaussian_filter

    f = gaussian_filter(rng.standard_normal((h, w)), corr_px)
    f *= sd / (f.std() + 1e-12)
    return f


def _pixel_gaussian(img: np.ndarray, x0: float, y0: float, sigma: float, amp: float) -> None:
    """Add amp*exp(-r^2/2s^2), averaged over each pixel's area (exact, via the CDF)."""
    h, w = img.shape
    r = int(math.ceil(6 * sigma)) + 1
    xs = np.arange(max(int(x0) - r, 0), min(int(x0) + r + 2, w))
    ys = np.arange(max(int(y0) - r, 0), min(int(y0) + r + 2, h))
    if xs.size == 0 or ys.size == 0:
        return
    gx = ndtr((xs + 0.5 - x0) / sigma) - ndtr((xs - 0.5 - x0) / sigma)
    gy = ndtr((ys + 0.5 - y0) / sigma) - ndtr((ys - 0.5 - y0) / sigma)
    img[ys[0] : ys[-1] + 1, xs[0] : xs[-1] + 1] += amp * 2 * math.pi * sigma**2 * np.outer(gy, gx)


class Renderer:
    """Renders frames for one Scene. The iris texture is fixed per renderer (seeded)."""

    def __init__(self, scene: Scene, seed: int = 0):
        self.scene = scene
        rng = np.random.default_rng(seed)
        h, w = scene.height, scene.width
        # Texture larger than the frame so it can move with the eye.
        pad = 200
        self._iris_tex = smooth_field(h + 2 * pad, w + 2 * pad, scene.iris_texture_sd, 3.0, rng)
        self._skin_tex = smooth_field(h + 2 * pad, w + 2 * pad, 6.0, 6.0, rng)
        self._pad = pad
        yy, xx = np.mgrid[0:h, 0:w]
        self._xx = xx.astype(np.float64)
        self._yy = yy.astype(np.float64)

    def background(self, t: Truth) -> np.ndarray:
        """Pupil + iris + skin, no reflections, no noise."""
        s = self.scene
        h, w = s.height, s.width
        p = self._pad
        ox = int(round(t.pupil_x - w / 2.0))
        oy = int(round(t.pupil_y - h / 2.0))
        ox = max(-p, min(p, ox))
        oy = max(-p, min(p, oy))
        iris_tex = self._iris_tex[p - oy : p - oy + h, p - ox : p - ox + w]
        dx = self._xx - t.pupil_x
        dy = self._yy - t.pupil_y
        # Normalized elliptical radius; distance to the edge approximated along the
        # minor-axis scale (adequate for a smooth, anti-aliased edge).
        rho = np.sqrt((dx / t.pupil_a) ** 2 + (dy / t.pupil_b) ** 2)
        edge_d = (rho - 1.0) * min(t.pupil_a, t.pupil_b)
        inside = ndtr(-edge_d / s.pupil_edge_sd)  # 1 inside the pupil, 0 outside
        rho_i = np.sqrt((dx / s.iris_radius_px) ** 2 + (dy / (s.iris_radius_px * s.pupil_b_px / s.pupil_a_px)) ** 2)
        in_iris = ndtr(-(rho_i - 1.0) * s.iris_radius_px / 3.0)
        outside = s.iris_level + iris_tex
        outside = in_iris * outside + (1 - in_iris) * (s.skin_level + self._skin_tex[p : p + h, p : p + w])
        return inside * s.pupil_level + (1 - inside) * outside

    def reflections(self, img: np.ndarray, t: Truth) -> None:
        s = self.scene
        a1 = s.p4_amp * s.p1_over_p4
        _pixel_gaussian(img, t.p1_x, t.p1_y, s.p1_sigma, a1)
        if s.p2_rel > 0:
            _pixel_gaussian(img, t.p1_x + s.p2_offset[0], t.p1_y + s.p2_offset[1], s.p1_sigma, a1 * s.p2_rel)
        _pixel_gaussian(img, t.p4_x, t.p4_y, s.p4_sigma, s.p4_amp)

    def noise_sd(self, level: np.ndarray | float) -> np.ndarray | float:
        s = self.scene
        return s.noise_scale * np.sqrt(s.read_noise_dn**2 + np.maximum(level, 0.0) / s.e_per_dn)

    def finish(self, img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Add sensor noise, clip at saturation, quantize to uint8."""
        sd = self.noise_sd(np.minimum(img, self.scene.saturation))
        img = img + sd * rng.standard_normal(img.shape)
        return np.clip(np.rint(img), 0, 255).astype(np.uint8)

    def frame(self, t: Truth, rng: np.random.Generator, bg: np.ndarray | None = None) -> np.ndarray:
        img = (self.background(t) if bg is None else bg).copy()
        self.reflections(img, t)
        return self.finish(img, rng)

    def blink(
        self,
        rng: np.random.Generator,
        t: Truth | None = None,
        closure: float = 1.0,
        lashes: bool = True,
        glints: int = 2,
    ) -> np.ndarray:
        """Upper lid lowered over the eye. closure = fraction of the pupil's height covered
        from the top (1.0 = fully closed). ASSUMED appearance: lid skin at skin_level with
        texture; dark lashes (20 DN, 2-4 px thick) hanging from the lid margin; `glints`
        bright specular spots on the margin (tear film), as the paper's Figure 2 shows
        bright spots on lashes and lids."""
        s = self.scene
        h, w = s.height, s.width
        t = t or geometry(s)
        img = self.background(t)
        self.reflections(img, t)
        top = t.pupil_y - t.pupil_b
        y_lid = top + closure * (2.0 * t.pupil_b) + (40.0 if closure >= 1.0 else 0.0)
        # The lid margin is a gentle arc, lowest in the middle.
        margin = y_lid - 0.0006 * (self._xx - t.pupil_x) ** 2
        lid = ndtr((margin - self._yy) / 2.0)  # 1 above the margin
        p = self._pad
        skin = s.skin_level + self._skin_tex[p : p + h, p : p + w]
        img = lid * skin + (1.0 - lid) * img
        if lashes:
            for _ in range(70):
                x = rng.uniform(0.05 * w, 0.95 * w)
                y = y_lid - 0.0006 * (x - t.pupil_x) ** 2
                ang = rng.uniform(-0.5, 0.5)
                length = rng.uniform(15, 45)
                thick = int(rng.integers(2, 5))
                for k in range(int(length)):
                    xi = int(x + k * math.sin(ang))
                    yi = int(y + k * math.cos(ang))
                    if 0 <= xi < w - thick and 0 <= yi < h:
                        img[yi, xi : xi + thick] = 20.0
        for _ in range(glints):
            gx = rng.uniform(0.25 * w, 0.75 * w)
            gy = y_lid - 0.0006 * (gx - t.pupil_x) ** 2 + rng.uniform(-3, 3)
            if 0 <= gy < h:
                _pixel_gaussian(img, gx, gy, 1.8, 3000.0)
        return self.finish(img, rng)


def full_frame_scene(base: Scene | None = None) -> Scene:
    """1440 x 1080 (the sensor's full frame) with the same eye in the middle."""
    return replace(base or Scene(), width=1440, height=1080)
