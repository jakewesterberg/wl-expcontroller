"""Colour as a physical claim, checked against a measured display.

**RGB is not a colour.** It is a triple of instructions to one particular panel,
so the same task file is a different stimulus on every monitor, and a methods
section quoting it describes nothing reproducible. Everything here is specified in
a device-independent space and converted, at load, against a calibration somebody
measured with a photometer.

The word that forces this is *isoluminant*. It is the control condition of most
chromatic experiments, it is a claim about photometry, and an unmeasured claim of
isoluminance is usually false -- so this module makes stating it require a
calibration that names whose luminous efficiency it was measured against. A
macaque's is not a human's.

**As of 2026-08-31 no calibration for our panels exists.** The `Calibration` in the
tests is illustrative. A real one is measured and committed under
`docs/measurements/`, per CLAUDE.md's rule on timing and physical claims.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Color:
    """Base for the colour vocabulary. Two spaces, for two different questions."""


@dataclass(frozen=True, slots=True)
class xyY(Color):
    """CIE 1931 chromaticity plus luminance in cd/m^2.

    An **absolute** specification: this names a light. Use it to reproduce a
    published stimulus, or when the quantity that matters is the light itself
    rather than its distance from the background.
    """

    x: float
    y: float
    Y: float


@dataclass(frozen=True, slots=True)
class DKL(Color):
    """Derrington-Krauskopf-Lennie cone-opponent contrast, relative to the background.

    A **modulation**: each component is a contrast away from the background along one
    cardinal axis, so the background itself is `DKL()`. This is the space nearly every
    chromatic experiment wants, because the three axes are the ones early visual
    cortex is organised around and because **`lum=0` is isoluminant by construction**
    rather than by arithmetic somebody did once in a spreadsheet.

    `l_m` is the L-minus-M axis (red/green), `s_lm` the S-cone axis (violet/lime).
    """

    lum: float = 0.0
    l_m: float = 0.0
    s_lm: float = 0.0

    def magnitude(self) -> float:
        return max(abs(self.lum), abs(self.l_m), abs(self.s_lm))


@dataclass(frozen=True, slots=True)
class Calibration:
    """A display, as measured. Every field is an observation, not a setting.

    `observer` names whose luminous efficiency the luminances were measured against,
    because that is what makes `lum=0` mean anything: photometric luminance is
    defined by a V(lambda), and using a human one for a macaque produces a stimulus
    that is isoluminant for nobody in the room.
    """

    red: xyY
    green: xyY
    blue: xyY
    background: xyY
    gamma: float
    observer: str
    measured_on: str
    #: The largest cone contrast this panel reaches on its weakest axis, measured.
    #: A three-primary display cannot produce arbitrary cone contrast, and the
    #: achievable maximum is a property of the primaries and the background -- so it
    #: is measured rather than assumed, like everything else here.
    max_cone_contrast: float = 0.85

    def weights(self, color: xyY) -> tuple[float, float, float]:
        """Linear primary weights for a colour, by solving the 3x3 mixture.

        Inside the gamut exactly when all three weights lie in [0, 1]: that is what
        "this panel can make this light" means, and it covers chromaticity and
        luminance in one test rather than two approximations.
        """
        columns = [_XYZ(p) for p in (self.red, self.green, self.blue)]
        return _solve3(columns, _XYZ(color))


def _XYZ(c: xyY) -> tuple[float, float, float]:
    """xyY to CIE XYZ. `y == 0` is not a colour; it is a typo."""
    if c.y <= 0.0:
        raise ValueError(f"chromaticity y must be positive, got {c.y}")
    return (c.Y * c.x / c.y, c.Y, c.Y * (1.0 - c.x - c.y) / c.y)


def _solve3(columns, target) -> tuple[float, float, float]:
    """Solve `columns @ w = target` by Cramer's rule.

    Three unknowns, done by hand rather than by pulling in a linear-algebra
    dependency for nine multiplications (CLAUDE.md's dependency policy).
    """
    a = [[columns[j][i] for j in range(3)] for i in range(3)]
    det = _det3(a)
    if abs(det) < 1e-12:
        raise ValueError("display primaries are degenerate: they do not span a gamut")
    out = []
    for j in range(3):
        m = [row[:] for row in a]
        for i in range(3):
            m[i][j] = target[i]
        out.append(_det3(m) / det)
    return (out[0], out[1], out[2])


def _det3(m) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


#: A hair of slack on the gamut test. Measured primaries carry measurement error,
#: and refusing a colour that sits 10^-9 outside a boundary would reject stimuli
#: that are physically fine for a reason no experimenter could act on.
TOLERANCE = 1e-6


def unrealizable(color: Color, panel: Calibration) -> str | None:
    """Why `panel` cannot produce `color`, or `None` if it can."""
    if isinstance(color, xyY):
        try:
            weights = panel.weights(color)
        except ValueError as exc:
            return str(exc)
        if any(w < -TOLERANCE or w > 1.0 + TOLERANCE for w in weights):
            return (
                f"needs primary weights {tuple(round(w, 3) for w in weights)}, "
                f"which are outside [0, 1]; the panel would clip, and a clipped "
                f"colour is neither the requested chromaticity nor the requested "
                f"luminance"
            )
        return None
    if isinstance(color, DKL):
        if color.magnitude() > panel.max_cone_contrast + TOLERANCE:
            return (
                f"asks for cone contrast {color.magnitude():.3f}; this panel was "
                f"measured to reach {panel.max_cone_contrast:.3f}"
            )
        return None
    return None
