"""Core (a): Python + numba. A clean-room implementation of the published OpenIrisDPI
algorithm (Ressmeyer et al., bioRxiv 2025.04.18.649589 v2, Appendix B, Algorithm 1;
J Neurosci Methods 2026, 10.1016/j.jneumeth.2026.110693, Appendix B).

Written from the paper's pseudocode and prose only. Every choice the paper leaves open is
marked UNSPECIFIED with what was chosen; ../2026-09-27-p10-dpi-spike.md lists them.
`dpi_core.cpp` is the same algorithm, statement for statement, and must agree bit for bit
on the integer stages (checked by `check_agreement.py`).

Algorithm 1, as published (line numbers are the paper's):
   6  Icrop  <- Crop(I, D)                          Stage 1: preprocess
   7  Iblur  <- GaussianBlur(Icrop, Rb)
   8  Ithr   <- Iblur < Tpup                        Stage 2: pupil boundary
   9  c0     <- Centroid(Ithr)
  10  maskp  <- CircularMask(c0, Rpup)
  11  Ilap   <- Laplacian(Ithr AND maskp)
  12  Iedge  <- Ilap > 0
  13  contour<- ConvexHull(Iedge)
  14  pupil  <- FitEllipse(contour)                 Stage 3
  15  Icr    <- (Iblur AND maskp) > Tcr             Stage 4: CR (P1)
  16  CRa    <- Centroid(Icr)
  17  roi    <- ExtractROI(Iblur, CRa, Rcr)
  18  CR     <- ThresholdedCenterOfMass(roi, Tcr)
  19  Imask  <- MaskRegion(Iblur, CR, Rcr)          Stage 5: P4
  20  maskp  <- FillContour(contour)
  21  maskp  <- Erode(maskp, Rerode)
  22  Ip4    <- Imask AND maskp
  23  P4a    <- ArgMax(Ip4)
  24  roi    <- ExtractROI(Iblur, P4a, RP4)
  25  P4     <- ThresholdedCenterOfMass(roi, Tpup)
  ThresholdedCenterOfMass(patch, t) = Centroid(max(patch - t, 0))

Hot path: `process` allocates nothing; the caller passes a preallocated workspace.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

# Parameter vector layout (int64).
P_TPUP, P_TCR, P_RPUP, P_RCR, P_RERODE, P_RP4, P_MINPUP, P_P4THR, P_BLUR, P_P4MASK = range(10)
N_PARAMS = 10

# Output vector layout (float64).
O_FLAGS, O_PUP_X, O_PUP_Y, O_PUP_A, O_PUP_B, O_PUP_ANG = 0, 1, 2, 3, 4, 5
O_CR_X, O_CR_Y, O_P4_X, O_P4_Y, O_P4_PEAK, O_NHULL = 6, 7, 8, 9, 10, 11
O_C0_X, O_C0_Y, O_NTHR = 12, 13, 14
N_OUT = 16

F_PUPIL, F_CR, F_P4, F_ELLIPSE = 1, 2, 4, 8

# UNSPECIFIED: the blur kernel for "blur radius Rb". Chosen: Rb = 2 -> 5 taps, sigma =
# 0.3*((k-1)/2 - 1) + 0.8 = 1.1 (OpenCV's documented default sigma for a kernel size).
# Integer weights round(256*g/sum(g)) = 18, 63, 94, 63, 18 (sum 256), so the two cores
# are bit-identical through every integer stage.
BW0, BW1, BW2 = 18, 63, 94


def default_params(
    t_pup: int = 30,
    t_cr: int = 245,
    r_pup: int = 170,
    r_cr: int = 29,
    r_erode: int = 8,
    r_p4: int = 15,
    min_pupil_px: int = 2000,
    p4_thr: int = -1,
    blur: int = 1,
    p4_roi_masked: int = 0,
) -> np.ndarray:
    """Operator settings. Tpup, Tcr, Rpup, Rcr and RP4 are the values shown in the paper's
    Figure 2 screenshot (left eye 28/245/172/29/15, right eye 33/245/168/30/15; the
    middle is used). Rerode and Rb are not visible there: ASSUMED 8 px and 2 (5 taps).
    min_pupil_px is ours (the paper names no failure test). p4_thr = -1 is the published
    choice, P4 threshold = Tpup (line 25). blur = 0 skips line 7 (a sensitivity variant).
    p4_roi_masked = 1 is NOT the published algorithm: line 25's centroid then counts only
    pixels inside the filled hull (a mitigation tested for P4 near the pupil edge; numba
    core only, and check_agreement.py runs with it off)."""
    p = np.zeros(N_PARAMS, np.int64)
    p[P_TPUP], p[P_TCR], p[P_RPUP], p[P_RCR] = t_pup, t_cr, r_pup, r_cr
    p[P_RERODE], p[P_RP4], p[P_MINPUP], p[P_P4THR] = r_erode, r_p4, min_pupil_px, p4_thr
    p[P_BLUR] = blur
    p[P_P4MASK] = p4_roi_masked
    return p


class Workspace:
    """Preallocated buffers for one camera stream."""

    def __init__(self, h: int, w: int):
        self.tmp = np.empty((h, w), np.uint16)
        self.blur = np.empty((h, w), np.uint8)
        self.pts = np.empty((2 * (h + 4), 2), np.float64)
        self.hull = np.empty((2 * (h + 4) + 2, 2), np.float64)
        self.rowlo = np.empty(h, np.int64)
        self.rowhi = np.empty(h, np.int64)
        self.bl = np.empty(h, np.int64)
        self.br = np.empty(h, np.int64)
        self.out = np.zeros(N_OUT, np.float64)


# --------------------------------------------------------------------------------------
# Stage 1 (+ lines 8-9 fused)
# --------------------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def blur_and_threshold(img, tmp, blur, t_pup, do_blur):
    """Line 7 fused with lines 8-9: returns (count, sum x, sum y) of blurred pixels below
    Tpup. UNSPECIFIED: border rule (replicate chosen). Loops run over sliced views so
    LLVM can vectorize them (a negative-index wraparound check otherwise blocks it)."""
    h, w = img.shape
    if do_blur != 0:
        n = w - 4
        for y in range(h):
            r = img[y]
            r0 = img[y, 0:n]
            r1 = img[y, 1 : n + 1]
            r2 = img[y, 2 : n + 2]
            r3 = img[y, 3 : n + 3]
            r4 = img[y, 4 : n + 4]
            t = tmp[y, 2 : n + 2]
            for i in range(n):
                t[i] = np.uint16(BW0) * np.uint16(r0[i]) + np.uint16(BW1) * np.uint16(r1[i]) + np.uint16(BW2) * np.uint16(r2[i]) + np.uint16(BW1) * np.uint16(r3[i]) + np.uint16(BW0) * np.uint16(r4[i])
            tt = tmp[y]
            tt[0] = np.uint16(BW0 + BW1 + BW2) * np.uint16(r[0]) + np.uint16(BW1) * np.uint16(r[1]) + np.uint16(BW0) * np.uint16(r[2])
            tt[1] = np.uint16(BW0 + BW1) * np.uint16(r[0]) + np.uint16(BW2) * np.uint16(r[1]) + np.uint16(BW1) * np.uint16(r[2]) + np.uint16(BW0) * np.uint16(r[3])
            tt[w - 2] = np.uint16(BW0) * np.uint16(r[w - 4]) + np.uint16(BW1) * np.uint16(r[w - 3]) + np.uint16(BW2) * np.uint16(r[w - 2]) + np.uint16(BW1 + BW0) * np.uint16(r[w - 1])
            tt[w - 1] = np.uint16(BW0) * np.uint16(r[w - 3]) + np.uint16(BW1) * np.uint16(r[w - 2]) + np.uint16(BW2 + BW1 + BW0) * np.uint16(r[w - 1])
        for y in range(h):
            a = tmp[max(y - 2, 0)]
            b = tmp[max(y - 1, 0)]
            c = tmp[y]
            d = tmp[min(y + 1, h - 1)]
            e = tmp[min(y + 2, h - 1)]
            o = blur[y]
            for x in range(w):
                o[x] = np.uint8((np.uint32(BW0) * np.uint32(a[x]) + np.uint32(BW1) * np.uint32(b[x]) + np.uint32(BW2) * np.uint32(c[x]) + np.uint32(BW1) * np.uint32(d[x]) + np.uint32(BW0) * np.uint32(e[x]) + np.uint32(32768)) >> np.uint32(16))
    else:
        for y in range(h):
            r = img[y]
            o = blur[y]
            for x in range(w):
                o[x] = r[x]
    tt8 = np.uint8(min(max(t_pup, 0), 255))
    cnt = 0
    sx = 0
    sy = 0
    for y in range(h):
        o = blur[y]
        rc = np.int32(0)
        rsx = np.int32(0)
        for x in range(w):
            m = np.int32(-1) if o[x] < tt8 else np.int32(0)
            rc -= m
            rsx += m & np.int32(x)
        cnt += rc
        sx += rsx
        sy += rc * y
    return cnt, sx, sy


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


@njit(cache=True, nogil=True, inline="always")
def _cross(ox, oy, ax, ay, bx, by):
    return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)


@njit(cache=True, nogil=True)
def tcom(blur, cx, cy, r, t, res):
    """ThresholdedCenterOfMass over a square ROI of half-width r around (cx, cy).
    UNSPECIFIED: ROI shape (square chosen), clipping at the image border (clipped).
    res <- (x, y, sum of weights). Returns False if every weight is zero."""
    h, w = blur.shape
    sw = 0
    sx = 0
    sy = 0
    for y in range(max(cy - r, 0), min(cy + r, h - 1) + 1):
        row = blur[y]
        for x in range(max(cx - r, 0), min(cx + r, w - 1) + 1):
            v = np.int64(row[x]) - t
            if v > 0:
                sw += v
                sx += v * x
                sy += v * y
    if sw <= 0:
        return False
    res[0] = sx / sw
    res[1] = sy / sw
    res[2] = sw
    return True


@njit(cache=True, nogil=True)
def tcom_in_hull(blur, cx, cy, r, t, hull, nh, sgn, res):
    """tcom restricted to pixel centers inside the hull polygon (variant, not published)."""
    h, w = blur.shape
    sw = 0
    sx = 0
    sy = 0
    for y in range(max(cy - r, 0), min(cy + r, h - 1) + 1):
        xlo = -1e18
        xhi = 1e18
        empty = False
        for i in range(nh):
            j = i + 1 if i + 1 < nh else 0
            ex = hull[j, 0] - hull[i, 0]
            ey = hull[j, 1] - hull[i, 1]
            ln = math.sqrt(ex * ex + ey * ey)
            if ln == 0.0:
                continue
            nx = -ey / ln * sgn
            ny = ex / ln * sgn
            rhs = -ny * (y - hull[i, 1]) + nx * hull[i, 0]
            if nx > 1e-12:
                vv = rhs / nx
                if vv > xlo:
                    xlo = vv
            elif nx < -1e-12:
                vv = rhs / nx
                if vv < xhi:
                    xhi = vv
            elif ny * (y - hull[i, 1]) < 0:
                empty = True
                break
        if empty:
            continue
        row = blur[y]
        for x in range(max(cx - r, 0, int(math.ceil(xlo))), min(cx + r, w - 1, int(math.floor(xhi))) + 1):
            v = np.int64(row[x]) - t
            if v > 0:
                sw += v
                sx += v * x
                sy += v * y
    if sw <= 0:
        return False
    res[0] = sx / sw
    res[1] = sy / sw
    res[2] = sw
    return True


@njit(cache=True, nogil=True)
def _eig_vec(m00, m01, m02, m10, m11, m12, m20, m21, m22, lam, v):
    """Eigenvector of a 3x3 for eigenvalue lam: the largest cross product of two rows of
    (M - lam I)."""
    a0, a1, a2 = m00 - lam, m01, m02
    b0, b1, b2 = m10, m11 - lam, m12
    c0, c1, c2 = m20, m21, m22 - lam
    best = -1.0
    for k in range(3):
        if k == 0:
            x0, x1, x2 = a1 * b2 - a2 * b1, a2 * b0 - a0 * b2, a0 * b1 - a1 * b0
        elif k == 1:
            x0, x1, x2 = a1 * c2 - a2 * c1, a2 * c0 - a0 * c2, a0 * c1 - a1 * c0
        else:
            x0, x1, x2 = b1 * c2 - b2 * c1, b2 * c0 - b0 * c2, b0 * c1 - b1 * c0
        n = x0 * x0 + x1 * x1 + x2 * x2
        if n > best:
            best = n
            v[0], v[1], v[2] = x0, x1, x2
    return best > 0


@njit(cache=True, nogil=True)
def fit_ellipse(hull, n, out, v):
    """Line 14. UNSPECIFIED: which ellipse fit, and on which points. Chosen: direct least
    squares (Fitzgibbon, Pilu & Fisher 1999) in Halir & Flusser's (1998) numerically
    stable form, on the hull vertices (the literal reading of lines 13-14). Scalar code,
    no allocation. Returns False if degenerate."""
    if n < 5:
        return False
    mx = 0.0
    my = 0.0
    for i in range(n):
        mx += hull[i, 0]
        my += hull[i, 1]
    mx /= n
    my /= n
    s = 0.0
    for i in range(n):
        s += (hull[i, 0] - mx) ** 2 + (hull[i, 1] - my) ** 2
    s = math.sqrt(s / (2.0 * n)) + 1e-12
    # S1 = D1'D1 (sym), S2 = D1'D2, S3 = D2'D2 (sym); D1 = [x2, xy, y2], D2 = [x, y, 1]
    s1_00 = s1_01 = s1_02 = s1_11 = s1_12 = s1_22 = 0.0
    s2_00 = s2_01 = s2_02 = s2_10 = s2_11 = s2_12 = s2_20 = s2_21 = s2_22 = 0.0
    s3_00 = s3_01 = s3_02 = s3_11 = s3_12 = s3_22 = 0.0
    for i in range(n):
        x = (hull[i, 0] - mx) / s
        y = (hull[i, 1] - my) / s
        xx, xy, yy = x * x, x * y, y * y
        s1_00 += xx * xx
        s1_01 += xx * xy
        s1_02 += xx * yy
        s1_11 += xy * xy
        s1_12 += xy * yy
        s1_22 += yy * yy
        s2_00 += xx * x
        s2_01 += xx * y
        s2_02 += xx
        s2_10 += xy * x
        s2_11 += xy * y
        s2_12 += xy
        s2_20 += yy * x
        s2_21 += yy * y
        s2_22 += yy
        s3_00 += xx
        s3_01 += xy
        s3_02 += x
        s3_11 += yy
        s3_12 += y
        s3_22 += 1.0
    # inverse of S3 (symmetric) by adjugate
    c00 = s3_11 * s3_22 - s3_12 * s3_12
    c01 = -(s3_01 * s3_22 - s3_12 * s3_02)
    c02 = s3_01 * s3_12 - s3_11 * s3_02
    det = s3_00 * c00 + s3_01 * c01 + s3_02 * c02
    if abs(det) < 1e-12:
        return False
    c11 = s3_00 * s3_22 - s3_02 * s3_02
    c12 = -(s3_00 * s3_12 - s3_01 * s3_02)
    c22 = s3_00 * s3_11 - s3_01 * s3_01
    i00, i01, i02 = c00 / det, c01 / det, c02 / det
    i11, i12, i22 = c11 / det, c12 / det, c22 / det
    # T = -inv(S3) @ S2^T  (3x3). S2^T[r][c] = S2[c][r].
    s2t_00, s2t_01, s2t_02 = s2_00, s2_10, s2_20
    s2t_10, s2t_11, s2t_12 = s2_01, s2_11, s2_21
    s2t_20, s2t_21, s2t_22 = s2_02, s2_12, s2_22
    t00 = -(i00 * s2t_00 + i01 * s2t_10 + i02 * s2t_20)
    t01 = -(i00 * s2t_01 + i01 * s2t_11 + i02 * s2t_21)
    t02 = -(i00 * s2t_02 + i01 * s2t_12 + i02 * s2t_22)
    t10 = -(i01 * s2t_00 + i11 * s2t_10 + i12 * s2t_20)
    t11 = -(i01 * s2t_01 + i11 * s2t_11 + i12 * s2t_21)
    t12 = -(i01 * s2t_02 + i11 * s2t_12 + i12 * s2t_22)
    t20 = -(i02 * s2t_00 + i12 * s2t_10 + i22 * s2t_20)
    t21 = -(i02 * s2t_01 + i12 * s2t_11 + i22 * s2t_21)
    t22 = -(i02 * s2t_02 + i12 * s2t_12 + i22 * s2t_22)
    # M = S1 + S2 @ T
    m00 = s1_00 + s2_00 * t00 + s2_01 * t10 + s2_02 * t20
    m01 = s1_01 + s2_00 * t01 + s2_01 * t11 + s2_02 * t21
    m02 = s1_02 + s2_00 * t02 + s2_01 * t12 + s2_02 * t22
    m10 = s1_01 + s2_10 * t00 + s2_11 * t10 + s2_12 * t20
    m11 = s1_11 + s2_10 * t01 + s2_11 * t11 + s2_12 * t21
    m12 = s1_12 + s2_10 * t02 + s2_11 * t12 + s2_12 * t22
    m20 = s1_02 + s2_20 * t00 + s2_21 * t10 + s2_22 * t20
    m21 = s1_12 + s2_20 * t01 + s2_21 * t11 + s2_22 * t21
    m22 = s1_22 + s2_20 * t02 + s2_21 * t12 + s2_22 * t22
    # M2 = inv(C1) @ M, inv(C1) = [[0,0,.5],[0,-1,0],[.5,0,0]]
    a00, a01, a02 = m20 / 2.0, m21 / 2.0, m22 / 2.0
    a10, a11, a12 = -m10, -m11, -m12
    a20, a21, a22 = m00 / 2.0, m01 / 2.0, m02 / 2.0
    # characteristic polynomial: l^3 + p2 l^2 + p1 l + p0 = 0
    tr = a00 + a11 + a22
    minors = a00 * a11 - a01 * a10 + a00 * a22 - a02 * a20 + a11 * a22 - a12 * a21
    dt = a00 * (a11 * a22 - a12 * a21) - a01 * (a10 * a22 - a12 * a20) + a02 * (a10 * a21 - a11 * a20)
    p2, p1, p0 = -tr, minors, -dt
    # depressed cubic via trigonometric / Cardano
    q = (3.0 * p1 - p2 * p2) / 9.0
    r = (9.0 * p2 * p1 - 27.0 * p0 - 2.0 * p2 * p2 * p2) / 54.0
    disc = q * q * q + r * r
    roots0 = roots1 = roots2 = np.nan
    if disc <= 0:
        th = math.acos(max(-1.0, min(1.0, r / math.sqrt(-q * q * q)))) if q < 0 else 0.0
        sq = 2.0 * math.sqrt(-q) if q < 0 else 0.0
        roots0 = sq * math.cos(th / 3.0) - p2 / 3.0
        roots1 = sq * math.cos((th + 2.0 * math.pi) / 3.0) - p2 / 3.0
        roots2 = sq * math.cos((th + 4.0 * math.pi) / 3.0) - p2 / 3.0
    else:
        sd = math.sqrt(disc)
        sa = r + sd
        sb = r - sd
        roots0 = math.copysign(abs(sa) ** (1.0 / 3.0), sa) + math.copysign(abs(sb) ** (1.0 / 3.0), sb) - p2 / 3.0
    found = False
    for k in range(3):
        lam = roots0 if k == 0 else (roots1 if k == 1 else roots2)
        if lam != lam:
            continue
        if not _eig_vec(a00, a01, a02, a10, a11, a12, a20, a21, a22, lam, v):
            continue
        if 4.0 * v[0] * v[2] - v[1] * v[1] > 0:
            found = True
            break
    if not found:
        return False
    A, B, C = v[0], v[1], v[2]
    D = t00 * A + t01 * B + t02 * C
    E = t10 * A + t11 * B + t12 * C
    F = t20 * A + t21 * B + t22 * C
    den = B * B - 4.0 * A * C
    if den >= 0:
        return False
    x0 = (2.0 * C * D - B * E) / den
    y0 = (2.0 * A * E - B * D) / den
    num = 2.0 * (A * E * E + C * D * D - B * D * E + den * F)
    root = math.sqrt((A - C) ** 2 + B * B)
    qa = num * (A + C + root)
    qb = num * (A + C - root)
    if qa <= 0 or qb <= 0:
        return False
    ax1 = math.sqrt(qa) / -den
    ax2 = math.sqrt(qb) / -den
    out[O_PUP_X] = x0 * s + mx
    out[O_PUP_Y] = y0 * s + my
    out[O_PUP_A] = max(ax1, ax2) * s
    out[O_PUP_B] = min(ax1, ax2) * s
    out[O_PUP_ANG] = 0.5 * math.atan2(-B, C - A)
    return True


# --------------------------------------------------------------------------------------
# The frame
# --------------------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def process(img, prm, tmp, blur, pts, hull, rowlo, rowhi, bl, br_, out, scratch):
    h, w = img.shape
    t_pup = prm[P_TPUP]
    t_cr = prm[P_TCR]
    r_pup = prm[P_RPUP]
    r_cr = prm[P_RCR]
    r_erode = prm[P_RERODE]
    r_p4 = prm[P_RP4]
    t8 = np.uint8(min(max(t_pup, 0), 255))
    c8 = np.uint8(min(max(t_cr, 0), 255))
    for i in range(N_OUT):
        out[i] = np.nan
    flags = 0

    # Lines 7-9.
    cnt, sx, sy = blur_and_threshold(img, tmp, blur, t_pup, prm[P_BLUR])
    out[O_NTHR] = cnt
    if cnt < prm[P_MINPUP]:
        out[O_FLAGS] = flags
        return
    cx = sx / cnt
    cy = sy / cnt
    out[O_C0_X] = cx
    out[O_C0_Y] = cy

    # Lines 10-13, and 15-16 fused. Row intervals of the circle (pixel centers inside).
    r2 = float(r_pup) * float(r_pup)
    y0 = max(int(math.floor(cy - r_pup)) - 1, 0)
    y1 = min(int(math.ceil(cy + r_pup)) + 1, h - 1)
    for y in range(y0, y1 + 1):
        dd = r2 - (y - cy) * (y - cy)
        if dd < 0:
            rowlo[y] = 1
            rowhi[y] = 0
        else:
            hw = math.sqrt(dd)
            rowlo[y] = max(int(math.ceil(cx - hw)), 0)
            rowhi[y] = min(int(math.floor(cx + hw)), w - 1)
    # Pass A (line 15 fused): per row, the leftmost and rightmost pixel of
    # B = (blur < Tpup) inside the circle, and the Tcr centroid sums. Branch-free.
    crn = 0
    crsx = 0
    crsy = 0
    for y in range(y0, y1 + 1):
        lo = rowlo[y]
        hi = rowhi[y]
        if lo > hi:
            bl[y] = w
            br_[y] = -1
            continue
        seg = blur[y, lo : hi + 1]
        L = np.int32(w)
        R = np.int32(-1)
        c = np.int32(0)
        csx = np.int32(0)
        for i in range(hi - lo + 1):
            v = seg[i]
            xi = np.int32(i)
            if v < t8:
                L = min(L, xi)
                R = max(R, xi)
            if v > c8:
                c += 1
                csx += xi
        bl[y] = L + lo if R >= 0 else w
        br_[y] = R + lo if R >= 0 else -1
        crn += c
        crsx += csx + c * lo
        crsy += c * y
    # Pass B (lines 11-12): an edge pixel is a non-B pixel with a 4-neighbor in B. On
    # row y the leftmost one is the smallest of: (leftmost B on row y) - 1, and the
    # leftmost B on rows y-1 and y+1 where that lies left of row y's. Symmetrically on
    # the right. The hull of all edge pixels is the hull of each row's extremes, so this
    # is exact (checked against a brute-force Laplacian in check_agreement.py).
    npts = 0
    for y in range(y0, y1 + 1):
        Ly = bl[y]
        Ry = br_[y]
        xl = w
        xr = -1
        if Ry >= 0:
            if Ly >= 1:
                xl = Ly - 1
            else:
                # B touches the left border: the first non-B pixel after that run.
                x = 0
                while x < w and x >= rowlo[y] and x <= rowhi[y] and blur[y, x] < t8:
                    x += 1
                if x < w:
                    xl = x
            if Ry <= w - 2:
                xr = Ry + 1
            else:
                x = w - 1
                while x >= 0 and x >= rowlo[y] and x <= rowhi[y] and blur[y, x] < t8:
                    x -= 1
                if x >= 0:
                    xr = x
        for yy in (y - 1, y + 1):
            if yy < y0 or yy > y1 or br_[yy] < 0:
                continue
            if bl[yy] < Ly and bl[yy] < xl:
                xl = bl[yy]
            if br_[yy] > Ry and br_[yy] > xr:
                xr = br_[yy]
        if xr < 0 and xl >= w:
            continue
        if xl >= w:
            xl = xr
        if xr < 0:
            xr = xl
        pts[npts, 0] = xl
        pts[npts, 1] = y
        npts += 1
        if xr != xl:
            pts[npts, 0] = xr
            pts[npts, 1] = y
            npts += 1

    # Line 13: Andrew's monotone chain; points are already sorted by (y, x).
    k = 0
    for i in range(npts):
        while k >= 2 and _cross(hull[k - 2, 0], hull[k - 2, 1], hull[k - 1, 0], hull[k - 1, 1], pts[i, 0], pts[i, 1]) <= 0:
            k -= 1
        hull[k, 0] = pts[i, 0]
        hull[k, 1] = pts[i, 1]
        k += 1
    lower = k + 1
    for i in range(npts - 2, -1, -1):
        while k >= lower and _cross(hull[k - 2, 0], hull[k - 2, 1], hull[k - 1, 0], hull[k - 1, 1], pts[i, 0], pts[i, 1]) <= 0:
            k -= 1
        hull[k, 0] = pts[i, 0]
        hull[k, 1] = pts[i, 1]
        k += 1
    nh = k - 1 if k > 1 else k
    out[O_NHULL] = nh
    if nh >= 3:
        flags |= F_PUPIL
    # Line 14.
    if fit_ellipse(hull, nh, out, scratch):
        flags |= F_ELLIPSE

    # Lines 16-18.
    if crn > 0:
        cax = int(round(crsx / crn))
        cay = int(round(crsy / crn))
        if tcom(blur, cax, cay, r_cr, t_cr, scratch):
            out[O_CR_X] = scratch[0]
            out[O_CR_Y] = scratch[1]
            flags |= F_CR
    if not (flags & F_PUPIL):
        out[O_FLAGS] = flags
        return

    # Lines 19-23. Fill + Erode(Rerode) of a convex polygon = points at least Rerode inside
    # every edge: one x-interval per row. UNSPECIFIED: erosion kernel; chosen: the exact
    # geometric inset. UNSPECIFIED: MaskRegion's shape; chosen: a disc of radius Rcr.
    has_cr = (flags & F_CR) != 0
    crx = out[O_CR_X]
    cry = out[O_CR_Y]
    rcr2 = float(r_cr) * float(r_cr)
    hy0 = h
    hy1 = -1
    area2 = 0.0
    for i in range(nh):
        j = i + 1 if i + 1 < nh else 0
        area2 += hull[i, 0] * hull[j, 1] - hull[j, 0] * hull[i, 1]
        yi = int(hull[i, 1])
        if yi < hy0:
            hy0 = yi
        if yi > hy1:
            hy1 = yi
    sgn = 1.0 if area2 > 0 else -1.0
    best = -1
    bx = -1
    by = -1
    for y in range(max(hy0, 0), min(hy1, h - 1) + 1):
        xlo = -1e18
        xhi = 1e18
        empty = False
        for i in range(nh):
            j = i + 1 if i + 1 < nh else 0
            ex = hull[j, 0] - hull[i, 0]
            ey = hull[j, 1] - hull[i, 1]
            ln = math.sqrt(ex * ex + ey * ey)
            if ln == 0.0:
                continue
            nx = -ey / ln * sgn  # inward (left) normal for positive signed area
            ny = ex / ln * sgn
            rhs = r_erode - ny * (y - hull[i, 1]) + nx * hull[i, 0]
            if nx > 1e-12:
                vv = rhs / nx
                if vv > xlo:
                    xlo = vv
            elif nx < -1e-12:
                vv = rhs / nx
                if vv < xhi:
                    xhi = vv
            elif ny * (y - hull[i, 1]) < r_erode:
                empty = True
                break
        if empty:
            continue
        xa = max(int(math.ceil(xlo)), 0)
        xb = min(int(math.floor(xhi)), w - 1)
        br = blur[y]
        for x in range(xa, xb + 1):
            val = np.int64(br[x])
            if val > best:  # UNSPECIFIED: ArgMax ties -> first in raster order
                if has_cr and (x - crx) * (x - crx) + (y - cry) * (y - cry) <= rcr2:
                    continue
                best = val
                bx = x
                by = y

    # Lines 24-25. The published P4 threshold is Tpup.
    t4 = t_pup if prm[P_P4THR] < 0 else prm[P_P4THR]
    if best > t4:
        if prm[P_P4MASK] != 0:
            ok4 = tcom_in_hull(blur, bx, by, r_p4, t4, hull, nh, sgn, scratch)
        else:
            ok4 = tcom(blur, bx, by, r_p4, t4, scratch)
        if ok4:
            out[O_P4_X] = scratch[0]
            out[O_P4_Y] = scratch[1]
            out[O_P4_PEAK] = best
            flags |= F_P4
    out[O_FLAGS] = flags


class Tracker:
    """One camera stream: parameters plus its preallocated workspace."""

    def __init__(self, h: int, w: int, prm: np.ndarray | None = None):
        self.ws = Workspace(h, w)
        self.prm = default_params() if prm is None else prm
        self.scratch = np.zeros(4, np.float64)

    def __call__(self, img: np.ndarray) -> np.ndarray:
        ws = self.ws
        process(img, self.prm, ws.tmp, ws.blur, ws.pts, ws.hull, ws.rowlo, ws.rowhi, ws.bl, ws.br, ws.out, self.scratch)
        return ws.out
