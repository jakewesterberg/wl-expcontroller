// Core (b): C++. The same clean-room implementation of the published OpenIrisDPI
// algorithm as dpi_numba.py (Ressmeyer et al., bioRxiv 2025.04.18.649589 v2, Appendix B,
// Algorithm 1), statement for statement, so the two agree bit for bit on every integer
// stage and to floating-point identity on the rest (check_agreement.py).
//
// Written from the paper's pseudocode and prose only; no OpenIris/OpenIrisDPI source was
// read. UNSPECIFIED choices are documented in dpi_numba.py and in the report.
//
// C ABI for ctypes (dpi_cpp.py); no allocation inside dpi_process.
//
// Build: clang++ -O3 -std=c++17 -ffp-contract=off -shared -fPIC dpi_core.cpp -o libdpi.dylib
// (-ffp-contract=off: numba does not fuse multiply-adds either, so results stay identical.)

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {

enum { O_FLAGS, O_PUP_X, O_PUP_Y, O_PUP_A, O_PUP_B, O_PUP_ANG, O_CR_X, O_CR_Y, O_P4_X,
       O_P4_Y, O_P4_PEAK, O_NHULL, O_C0_X, O_C0_Y, O_NTHR, N_OUT = 16 };
enum { F_PUPIL = 1, F_CR = 2, F_P4 = 4, F_ELLIPSE = 8 };
constexpr uint32_t BW0 = 18, BW1 = 63, BW2 = 94;

struct Workspace {
  int h, w;
  std::vector<uint16_t> tmp;
  std::vector<uint8_t> blur;
  std::vector<double> pts;   // (x, y) pairs
  std::vector<double> hull;  // (x, y) pairs
  std::vector<int64_t> rowlo, rowhi, bl, br;
  Workspace(int h_, int w_)
      : h(h_), w(w_), tmp((size_t)h_ * w_), blur((size_t)h_ * w_), pts(4 * (h_ + 4)),
        hull(4 * (h_ + 4) + 4), rowlo(h_), rowhi(h_), bl(h_), br(h_) {}
};

inline double X(const std::vector<double>& v, int i) { return v[2 * i]; }
inline double Y(const std::vector<double>& v, int i) { return v[2 * i + 1]; }

inline double cross(double ox, double oy, double ax, double ay, double bx, double by) {
  return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox);
}

// Lines 7-9.
void blur_and_threshold(const uint8_t* img, int stride, Workspace& ws, int t_pup, int do_blur,
                        int64_t& cnt, int64_t& sx, int64_t& sy) {
  const int h = ws.h, w = ws.w;
  uint16_t* tmp = ws.tmp.data();
  uint8_t* blur = ws.blur.data();
  if (do_blur) {
    for (int y = 0; y < h; ++y) {
      const uint8_t* r = img + (size_t)y * stride;
      uint16_t* t = tmp + (size_t)y * w;
      for (int x = 2; x < w - 2; ++x)
        t[x] = (uint16_t)(BW0 * r[x - 2] + BW1 * r[x - 1] + BW2 * r[x] + BW1 * r[x + 1] + BW0 * r[x + 2]);
      t[0] = (uint16_t)((BW0 + BW1 + BW2) * r[0] + BW1 * r[1] + BW0 * r[2]);
      t[1] = (uint16_t)((BW0 + BW1) * r[0] + BW2 * r[1] + BW1 * r[2] + BW0 * r[3]);
      t[w - 2] = (uint16_t)(BW0 * r[w - 4] + BW1 * r[w - 3] + BW2 * r[w - 2] + (BW1 + BW0) * r[w - 1]);
      t[w - 1] = (uint16_t)(BW0 * r[w - 3] + BW1 * r[w - 2] + (BW2 + BW1 + BW0) * r[w - 1]);
    }
    for (int y = 0; y < h; ++y) {
      const uint16_t* a = tmp + (size_t)std::max(y - 2, 0) * w;
      const uint16_t* b = tmp + (size_t)std::max(y - 1, 0) * w;
      const uint16_t* c = tmp + (size_t)y * w;
      const uint16_t* d = tmp + (size_t)std::min(y + 1, h - 1) * w;
      const uint16_t* e = tmp + (size_t)std::min(y + 2, h - 1) * w;
      uint8_t* o = blur + (size_t)y * w;
      for (int x = 0; x < w; ++x)
        o[x] = (uint8_t)((BW0 * a[x] + BW1 * b[x] + BW2 * c[x] + BW1 * d[x] + BW0 * e[x] + 32768u) >> 16);
    }
  } else {
    for (int y = 0; y < h; ++y) std::memcpy(blur + (size_t)y * w, img + (size_t)y * stride, w);
  }
  const uint8_t tt8 = (uint8_t)std::min(std::max(t_pup, 0), 255);
  cnt = sx = sy = 0;
  for (int y = 0; y < h; ++y) {
    const uint8_t* o = blur + (size_t)y * w;
    int32_t rc = 0, rsx = 0;
    for (int x = 0; x < w; ++x) {
      int32_t m = o[x] < tt8 ? -1 : 0;
      rc -= m;
      rsx += m & x;
    }
    cnt += rc;
    sx += rsx;
    sy += (int64_t)rc * y;
  }
}

bool tcom(const Workspace& ws, int64_t cx, int64_t cy, int64_t r, int64_t t, double* res) {
  const int h = ws.h, w = ws.w;
  const uint8_t* blur = ws.blur.data();
  int64_t sw = 0, sx = 0, sy = 0;
  for (int64_t y = std::max<int64_t>(cy - r, 0); y <= std::min<int64_t>(cy + r, h - 1); ++y) {
    const uint8_t* row = blur + (size_t)y * w;
    for (int64_t x = std::max<int64_t>(cx - r, 0); x <= std::min<int64_t>(cx + r, w - 1); ++x) {
      int64_t v = (int64_t)row[x] - t;
      if (v > 0) {
        sw += v;
        sx += v * x;
        sy += v * y;
      }
    }
  }
  if (sw <= 0) return false;
  res[0] = (double)sx / (double)sw;
  res[1] = (double)sy / (double)sw;
  res[2] = (double)sw;
  return true;
}

bool eig_vec(double m00, double m01, double m02, double m10, double m11, double m12, double m20,
             double m21, double m22, double lam, double* v) {
  double a0 = m00 - lam, a1 = m01, a2 = m02;
  double b0 = m10, b1 = m11 - lam, b2 = m12;
  double c0 = m20, c1 = m21, c2 = m22 - lam;
  double best = -1.0;
  for (int k = 0; k < 3; ++k) {
    double x0, x1, x2;
    if (k == 0) { x0 = a1 * b2 - a2 * b1; x1 = a2 * b0 - a0 * b2; x2 = a0 * b1 - a1 * b0; }
    else if (k == 1) { x0 = a1 * c2 - a2 * c1; x1 = a2 * c0 - a0 * c2; x2 = a0 * c1 - a1 * c0; }
    else { x0 = b1 * c2 - b2 * c1; x1 = b2 * c0 - b0 * c2; x2 = b0 * c1 - b1 * c0; }
    double n = x0 * x0 + x1 * x1 + x2 * x2;
    if (n > best) { best = n; v[0] = x0; v[1] = x1; v[2] = x2; }
  }
  return best > 0;
}

// Line 14: Halir & Flusser (1998) direct least squares, on the hull vertices.
bool fit_ellipse(const std::vector<double>& hull, int n, double* out) {
  if (n < 5) return false;
  double mx = 0, my = 0;
  for (int i = 0; i < n; ++i) { mx += X(hull, i); my += Y(hull, i); }
  mx /= n; my /= n;
  double s = 0;
  for (int i = 0; i < n; ++i) {
    double dx = X(hull, i) - mx, dy = Y(hull, i) - my;
    s += dx * dx + dy * dy;
  }
  s = std::sqrt(s / (2.0 * n)) + 1e-12;
  double s1_00 = 0, s1_01 = 0, s1_02 = 0, s1_11 = 0, s1_12 = 0, s1_22 = 0;
  double s2_00 = 0, s2_01 = 0, s2_02 = 0, s2_10 = 0, s2_11 = 0, s2_12 = 0, s2_20 = 0, s2_21 = 0, s2_22 = 0;
  double s3_00 = 0, s3_01 = 0, s3_02 = 0, s3_11 = 0, s3_12 = 0, s3_22 = 0;
  for (int i = 0; i < n; ++i) {
    double x = (X(hull, i) - mx) / s, y = (Y(hull, i) - my) / s;
    double xx = x * x, xy = x * y, yy = y * y;
    s1_00 += xx * xx; s1_01 += xx * xy; s1_02 += xx * yy; s1_11 += xy * xy; s1_12 += xy * yy; s1_22 += yy * yy;
    s2_00 += xx * x; s2_01 += xx * y; s2_02 += xx;
    s2_10 += xy * x; s2_11 += xy * y; s2_12 += xy;
    s2_20 += yy * x; s2_21 += yy * y; s2_22 += yy;
    s3_00 += xx; s3_01 += xy; s3_02 += x; s3_11 += yy; s3_12 += y; s3_22 += 1.0;
  }
  double c00 = s3_11 * s3_22 - s3_12 * s3_12;
  double c01 = -(s3_01 * s3_22 - s3_12 * s3_02);
  double c02 = s3_01 * s3_12 - s3_11 * s3_02;
  double det = s3_00 * c00 + s3_01 * c01 + s3_02 * c02;
  if (std::fabs(det) < 1e-12) return false;
  double c11 = s3_00 * s3_22 - s3_02 * s3_02;
  double c12 = -(s3_00 * s3_12 - s3_01 * s3_02);
  double c22 = s3_00 * s3_11 - s3_01 * s3_01;
  double i00 = c00 / det, i01 = c01 / det, i02 = c02 / det, i11 = c11 / det, i12 = c12 / det, i22 = c22 / det;
  double s2t_00 = s2_00, s2t_01 = s2_10, s2t_02 = s2_20;
  double s2t_10 = s2_01, s2t_11 = s2_11, s2t_12 = s2_21;
  double s2t_20 = s2_02, s2t_21 = s2_12, s2t_22 = s2_22;
  double t00 = -(i00 * s2t_00 + i01 * s2t_10 + i02 * s2t_20);
  double t01 = -(i00 * s2t_01 + i01 * s2t_11 + i02 * s2t_21);
  double t02 = -(i00 * s2t_02 + i01 * s2t_12 + i02 * s2t_22);
  double t10 = -(i01 * s2t_00 + i11 * s2t_10 + i12 * s2t_20);
  double t11 = -(i01 * s2t_01 + i11 * s2t_11 + i12 * s2t_21);
  double t12 = -(i01 * s2t_02 + i11 * s2t_12 + i12 * s2t_22);
  double t20 = -(i02 * s2t_00 + i12 * s2t_10 + i22 * s2t_20);
  double t21 = -(i02 * s2t_01 + i12 * s2t_11 + i22 * s2t_21);
  double t22 = -(i02 * s2t_02 + i12 * s2t_12 + i22 * s2t_22);
  double m00 = s1_00 + s2_00 * t00 + s2_01 * t10 + s2_02 * t20;
  double m01 = s1_01 + s2_00 * t01 + s2_01 * t11 + s2_02 * t21;
  double m02 = s1_02 + s2_00 * t02 + s2_01 * t12 + s2_02 * t22;
  double m10 = s1_01 + s2_10 * t00 + s2_11 * t10 + s2_12 * t20;
  double m11 = s1_11 + s2_10 * t01 + s2_11 * t11 + s2_12 * t21;
  double m12 = s1_12 + s2_10 * t02 + s2_11 * t12 + s2_12 * t22;
  double m20 = s1_02 + s2_20 * t00 + s2_21 * t10 + s2_22 * t20;
  double m21 = s1_12 + s2_20 * t01 + s2_21 * t11 + s2_22 * t21;
  double m22 = s1_22 + s2_20 * t02 + s2_21 * t12 + s2_22 * t22;
  double a00 = m20 / 2.0, a01 = m21 / 2.0, a02 = m22 / 2.0;
  double a10 = -m10, a11 = -m11, a12 = -m12;
  double a20 = m00 / 2.0, a21 = m01 / 2.0, a22 = m02 / 2.0;
  double tr = a00 + a11 + a22;
  double minors = a00 * a11 - a01 * a10 + a00 * a22 - a02 * a20 + a11 * a22 - a12 * a21;
  double dt = a00 * (a11 * a22 - a12 * a21) - a01 * (a10 * a22 - a12 * a20) + a02 * (a10 * a21 - a11 * a20);
  double p2 = -tr, p1 = minors, p0 = -dt;
  double q = (3.0 * p1 - p2 * p2) / 9.0;
  double r = (9.0 * p2 * p1 - 27.0 * p0 - 2.0 * p2 * p2 * p2) / 54.0;
  double disc = q * q * q + r * r;
  double roots[3] = {NAN, NAN, NAN};
  if (disc <= 0) {
    double th = q < 0 ? std::acos(std::max(-1.0, std::min(1.0, r / std::sqrt(-q * q * q)))) : 0.0;
    double sq = q < 0 ? 2.0 * std::sqrt(-q) : 0.0;
    roots[0] = sq * std::cos(th / 3.0) - p2 / 3.0;
    roots[1] = sq * std::cos((th + 2.0 * M_PI) / 3.0) - p2 / 3.0;
    roots[2] = sq * std::cos((th + 4.0 * M_PI) / 3.0) - p2 / 3.0;
  } else {
    double sd = std::sqrt(disc), sa = r + sd, sb = r - sd;
    roots[0] = std::copysign(std::pow(std::fabs(sa), 1.0 / 3.0), sa) +
               std::copysign(std::pow(std::fabs(sb), 1.0 / 3.0), sb) - p2 / 3.0;
  }
  double v[3] = {0, 0, 0};
  bool found = false;
  for (int k = 0; k < 3; ++k) {
    double lam = roots[k];
    if (lam != lam) continue;
    if (!eig_vec(a00, a01, a02, a10, a11, a12, a20, a21, a22, lam, v)) continue;
    if (4.0 * v[0] * v[2] - v[1] * v[1] > 0) { found = true; break; }
  }
  if (!found) return false;
  double A = v[0], B = v[1], C = v[2];
  double D = t00 * A + t01 * B + t02 * C;
  double E = t10 * A + t11 * B + t12 * C;
  double F = t20 * A + t21 * B + t22 * C;
  double den = B * B - 4.0 * A * C;
  if (den >= 0) return false;
  double x0 = (2.0 * C * D - B * E) / den;
  double y0 = (2.0 * A * E - B * D) / den;
  double num = 2.0 * (A * E * E + C * D * D - B * D * E + den * F);
  double root = std::sqrt((A - C) * (A - C) + B * B);
  double qa = num * (A + C + root), qb = num * (A + C - root);
  if (qa <= 0 || qb <= 0) return false;
  double ax1 = std::sqrt(qa) / -den, ax2 = std::sqrt(qb) / -den;
  out[O_PUP_X] = x0 * s + mx;
  out[O_PUP_Y] = y0 * s + my;
  out[O_PUP_A] = std::max(ax1, ax2) * s;
  out[O_PUP_B] = std::min(ax1, ax2) * s;
  out[O_PUP_ANG] = 0.5 * std::atan2(-B, C - A);
  return true;
}

}  // namespace

extern "C" {

// Parameter layout matches dpi_numba.default_params (int64 x 10). P_P4MASK (a variant,
// not the published algorithm) exists only in the numba core and is ignored here.
enum { P_TPUP, P_TCR, P_RPUP, P_RCR, P_RERODE, P_RP4, P_MINPUP, P_P4THR, P_BLUR, P_P4MASK };

void* dpi_create(int h, int w) { return new Workspace(h, w); }
void dpi_destroy(void* p) { delete static_cast<Workspace*>(p); }

// Stage timing (optional): if stamps != nullptr, 6 timestamps are written by `clock`.
typedef uint64_t (*clock_fn)(void);

void dpi_process_timed(void* wsp, const uint8_t* img, int stride, const int64_t* prm, double* out,
                       uint64_t* stamps, clock_fn clk) {
  Workspace& ws = *static_cast<Workspace*>(wsp);
  const int h = ws.h, w = ws.w;
  const int64_t t_pup = prm[P_TPUP], t_cr = prm[P_TCR], r_pup = prm[P_RPUP], r_cr = prm[P_RCR];
  const int64_t r_erode = prm[P_RERODE], r_p4 = prm[P_RP4];
  const uint8_t t8 = (uint8_t)std::min<int64_t>(std::max<int64_t>(t_pup, 0), 255);
  const uint8_t c8 = (uint8_t)std::min<int64_t>(std::max<int64_t>(t_cr, 0), 255);
  const uint8_t* blur = ws.blur.data();
  int64_t* rowlo = ws.rowlo.data();
  int64_t* rowhi = ws.rowhi.data();
  int64_t* bl = ws.bl.data();
  int64_t* br = ws.br.data();
  for (int i = 0; i < N_OUT; ++i) out[i] = NAN;
  int flags = 0;
  if (stamps) stamps[0] = clk();

  int64_t cnt, sx, sy;
  blur_and_threshold(img, stride, ws, (int)t_pup, (int)prm[P_BLUR], cnt, sx, sy);
  if (stamps) stamps[1] = clk();
  out[O_NTHR] = (double)cnt;
  if (cnt < prm[P_MINPUP]) { out[O_FLAGS] = flags; return; }
  const double cx = (double)sx / (double)cnt, cy = (double)sy / (double)cnt;
  out[O_C0_X] = cx;
  out[O_C0_Y] = cy;

  const double r2 = (double)r_pup * (double)r_pup;
  const int64_t y0 = std::max<int64_t>((int64_t)std::floor(cy - (double)r_pup) - 1, 0);
  const int64_t y1 = std::min<int64_t>((int64_t)std::ceil(cy + (double)r_pup) + 1, h - 1);
  for (int64_t y = y0; y <= y1; ++y) {
    double dd = r2 - ((double)y - cy) * ((double)y - cy);
    if (dd < 0) { rowlo[y] = 1; rowhi[y] = 0; }
    else {
      double hw = std::sqrt(dd);
      rowlo[y] = std::max<int64_t>((int64_t)std::ceil(cx - hw), 0);
      rowhi[y] = std::min<int64_t>((int64_t)std::floor(cx + hw), w - 1);
    }
  }
  // Pass A.
  int64_t crn = 0, crsx = 0, crsy = 0;
  for (int64_t y = y0; y <= y1; ++y) {
    const int64_t lo = rowlo[y], hi = rowhi[y];
    if (lo > hi) { bl[y] = w; br[y] = -1; continue; }
    const uint8_t* seg = blur + (size_t)y * w + lo;
    const int32_t n = (int32_t)(hi - lo + 1);
    int32_t L = w, R = -1, c = 0, csx = 0;
    for (int32_t i = 0; i < n; ++i) {
      uint8_t v = seg[i];
      if (v < t8) { L = std::min(L, i); R = std::max(R, i); }
      if (v > c8) { c += 1; csx += i; }
    }
    bl[y] = R >= 0 ? L + lo : w;
    br[y] = R >= 0 ? R + lo : -1;
    crn += c;
    crsx += csx + (int64_t)c * lo;
    crsy += (int64_t)c * y;
  }
  // Pass B.
  int npts = 0;
  for (int64_t y = y0; y <= y1; ++y) {
    const int64_t Ly = bl[y], Ry = br[y];
    int64_t xl = w, xr = -1;
    if (Ry >= 0) {
      if (Ly >= 1) xl = Ly - 1;
      else {
        int64_t x = 0;
        while (x < w && x >= rowlo[y] && x <= rowhi[y] && blur[(size_t)y * w + x] < t8) ++x;
        if (x < w) xl = x;
      }
      if (Ry <= w - 2) xr = Ry + 1;
      else {
        int64_t x = w - 1;
        while (x >= 0 && x >= rowlo[y] && x <= rowhi[y] && blur[(size_t)y * w + x] < t8) --x;
        if (x >= 0) xr = x;
      }
    }
    for (int64_t yy : {y - 1, y + 1}) {
      if (yy < y0 || yy > y1 || br[yy] < 0) continue;
      if (bl[yy] < Ly && bl[yy] < xl) xl = bl[yy];
      if (br[yy] > Ry && br[yy] > xr) xr = br[yy];
    }
    if (xr < 0 && xl >= w) continue;
    if (xl >= w) xl = xr;
    if (xr < 0) xr = xl;
    ws.pts[2 * npts] = (double)xl; ws.pts[2 * npts + 1] = (double)y; ++npts;
    if (xr != xl) { ws.pts[2 * npts] = (double)xr; ws.pts[2 * npts + 1] = (double)y; ++npts; }
  }
  if (stamps) stamps[2] = clk();
  // Line 13: monotone chain.
  std::vector<double>& H = ws.hull;
  const std::vector<double>& P = ws.pts;
  int k = 0;
  for (int i = 0; i < npts; ++i) {
    while (k >= 2 && cross(X(H, k - 2), Y(H, k - 2), X(H, k - 1), Y(H, k - 1), X(P, i), Y(P, i)) <= 0) --k;
    H[2 * k] = X(P, i); H[2 * k + 1] = Y(P, i); ++k;
  }
  const int lower = k + 1;
  for (int i = npts - 2; i >= 0; --i) {
    while (k >= lower && cross(X(H, k - 2), Y(H, k - 2), X(H, k - 1), Y(H, k - 1), X(P, i), Y(P, i)) <= 0) --k;
    H[2 * k] = X(P, i); H[2 * k + 1] = Y(P, i); ++k;
  }
  const int nh = k > 1 ? k - 1 : k;
  out[O_NHULL] = nh;
  if (nh >= 3) flags |= F_PUPIL;
  if (fit_ellipse(H, nh, out)) flags |= F_ELLIPSE;
  if (stamps) stamps[3] = clk();
  // Lines 16-18.
  double res[3];
  if (crn > 0) {
    int64_t cax = (int64_t)std::nearbyint((double)crsx / (double)crn);
    int64_t cay = (int64_t)std::nearbyint((double)crsy / (double)crn);
    if (tcom(ws, cax, cay, r_cr, t_cr, res)) { out[O_CR_X] = res[0]; out[O_CR_Y] = res[1]; flags |= F_CR; }
  }
  if (!(flags & F_PUPIL)) { out[O_FLAGS] = flags; if (stamps) stamps[4] = stamps[5] = clk(); return; }
  if (stamps) stamps[4] = clk();
  // Lines 19-23.
  const bool has_cr = (flags & F_CR) != 0;
  const double crx = out[O_CR_X], cry = out[O_CR_Y];
  const double rcr2 = (double)r_cr * (double)r_cr;
  int64_t hy0 = h, hy1 = -1;
  double area2 = 0.0;
  for (int i = 0; i < nh; ++i) {
    int j = i + 1 < nh ? i + 1 : 0;
    area2 += X(H, i) * Y(H, j) - X(H, j) * Y(H, i);
    int64_t yi = (int64_t)Y(H, i);
    if (yi < hy0) hy0 = yi;
    if (yi > hy1) hy1 = yi;
  }
  const double sgn = area2 > 0 ? 1.0 : -1.0;
  int64_t best = -1, bx = -1, by = -1;
  for (int64_t y = std::max<int64_t>(hy0, 0); y <= std::min<int64_t>(hy1, h - 1); ++y) {
    double xlo = -1e18, xhi = 1e18;
    bool empty = false;
    for (int i = 0; i < nh; ++i) {
      int j = i + 1 < nh ? i + 1 : 0;
      double ex = X(H, j) - X(H, i), ey = Y(H, j) - Y(H, i);
      double ln = std::sqrt(ex * ex + ey * ey);
      if (ln == 0.0) continue;
      double nx = -ey / ln * sgn, ny = ex / ln * sgn;
      double rhs = (double)r_erode - ny * ((double)y - Y(H, i)) + nx * X(H, i);
      if (nx > 1e-12) { double vv = rhs / nx; if (vv > xlo) xlo = vv; }
      else if (nx < -1e-12) { double vv = rhs / nx; if (vv < xhi) xhi = vv; }
      else if (ny * ((double)y - Y(H, i)) < (double)r_erode) { empty = true; break; }
    }
    if (empty) continue;
    int64_t xa = std::max<int64_t>((int64_t)std::ceil(xlo), 0);
    int64_t xb = std::min<int64_t>((int64_t)std::floor(xhi), w - 1);
    const uint8_t* row = blur + (size_t)y * w;
    for (int64_t x = xa; x <= xb; ++x) {
      int64_t val = row[x];
      if (val > best) {
        if (has_cr && ((double)x - crx) * ((double)x - crx) + ((double)y - cry) * ((double)y - cry) <= rcr2) continue;
        best = val; bx = x; by = y;
      }
    }
  }
  // Lines 24-25.
  const int64_t t4 = prm[P_P4THR] < 0 ? t_pup : prm[P_P4THR];
  if (best > t4 && tcom(ws, bx, by, r_p4, t4, res)) {
    out[O_P4_X] = res[0]; out[O_P4_Y] = res[1]; out[O_P4_PEAK] = (double)best; flags |= F_P4;
  }
  out[O_FLAGS] = flags;
  if (stamps) stamps[5] = clk();
}

void dpi_process(void* wsp, const uint8_t* img, int stride, const int64_t* prm, double* out) {
  dpi_process_timed(wsp, img, stride, prm, out, nullptr, nullptr);
}

}  // extern "C"
