// Standalone C++ benchmark for the DPI core: no Python in the loop.
//
//   bench_cpp POOL OUT_PREFIX FRAMES THREADS PACE_US [STAGES]
//
// POOL: frame pool written by bench_speed.py ("DPIP", int32 h, w, n, then n*h*w bytes).
// Each thread is one camera: its own workspace, its own stretch of the pool, FRAMES
// frames. PACE_US > 0 releases a frame every PACE_US microseconds (sleep_until), as a
// camera would; 0 runs back to back. Only the processing call is timed.
// Writes OUT_PREFIX.t<k>.i64 (ns per frame) per thread; with STAGES=1 also
// OUT_PREFIX.t<k>.stages.i64 (6 stamps per frame).

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

extern "C" {
void* dpi_create(int h, int w);
void dpi_destroy(void*);
typedef uint64_t (*clock_fn)(void);
void dpi_process_timed(void* ws, const uint8_t* img, int stride, const int64_t* prm, double* out,
                       uint64_t* stamps, clock_fn clk);
}

static uint64_t now_ns() {
  return (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch()).count();
}

int main(int argc, char** argv) {
  if (argc < 6) {
    std::fprintf(stderr, "usage: %s POOL OUT_PREFIX FRAMES THREADS PACE_US [STAGES]\n", argv[0]);
    return 2;
  }
  const std::string pool_path = argv[1], prefix = argv[2];
  const long frames = std::atol(argv[3]);
  const int threads = std::atoi(argv[4]);
  const long pace_us = std::atol(argv[5]);
  const bool stages = argc > 6 && std::atoi(argv[6]) != 0;

  std::ifstream f(pool_path, std::ios::binary);
  char magic[4];
  int32_t hwn[3];
  f.read(magic, 4);
  f.read(reinterpret_cast<char*>(hwn), sizeof hwn);
  if (!f || std::memcmp(magic, "DPIP", 4) != 0) { std::fprintf(stderr, "bad pool\n"); return 2; }
  const int h = hwn[0], w = hwn[1], n = hwn[2];
  std::vector<uint8_t> pool((size_t)h * w * n);
  f.read(reinterpret_cast<char*>(pool.data()), (std::streamsize)pool.size());
  if (!f) { std::fprintf(stderr, "short pool\n"); return 2; }

  // Parameters: dpi_numba.default_params() (Tpup 30, Tcr 245, Rpup 170, Rcr 29,
  // Rerode 8, RP4 15, min pupil 2000 px, P4 threshold = Tpup, blur on).
  const int64_t prm[10] = {30, 245, 170, 29, 8, 15, 2000, -1, 1, 0};
  const long warm = 200;

  std::vector<std::vector<int64_t>> times(threads, std::vector<int64_t>(frames));
  std::vector<std::vector<uint64_t>> st(threads, std::vector<uint64_t>(stages ? frames * 6 : 0));
  std::vector<double> checksum(threads, 0.0);
  std::vector<std::thread> pool_threads;
  for (int k = 0; k < threads; ++k) {
    pool_threads.emplace_back([&, k] {
      void* ws = dpi_create(h, w);
      double out[16];
      uint64_t stamp[6];
      const long offset = (long)k * n / threads;
      for (long i = 0; i < warm; ++i) {
        const uint8_t* img = pool.data() + (size_t)((offset + i) % n) * h * w;
        dpi_process_timed(ws, img, w, prm, out, nullptr, nullptr);
      }
      const auto t0 = std::chrono::steady_clock::now();
      for (long i = 0; i < frames; ++i) {
        if (pace_us > 0) std::this_thread::sleep_until(t0 + std::chrono::microseconds(pace_us * i));
        const uint8_t* img = pool.data() + (size_t)((offset + i) % n) * h * w;
        const uint64_t a = now_ns();
        dpi_process_timed(ws, img, w, prm, out, stages ? stamp : nullptr, stages ? now_ns : nullptr);
        const uint64_t b = now_ns();
        times[k][i] = (int64_t)(b - a);
        if (stages) std::memcpy(&st[k][i * 6], stamp, sizeof stamp);
        checksum[k] += out[6] + out[8];
      }
      dpi_destroy(ws);
    });
  }
  for (auto& t : pool_threads) t.join();

  for (int k = 0; k < threads; ++k) {
    std::string p = prefix + ".t" + std::to_string(k) + ".i64";
    std::ofstream o(p, std::ios::binary);
    o.write(reinterpret_cast<const char*>(times[k].data()), (std::streamsize)(times[k].size() * 8));
    if (stages) {
      std::ofstream s(prefix + ".t" + std::to_string(k) + ".stages.i64", std::ios::binary);
      s.write(reinterpret_cast<const char*>(st[k].data()), (std::streamsize)(st[k].size() * 8));
    }
    std::printf("thread %d: %ld frames, checksum %.6f\n", k, frames, checksum[k]);
  }
  return 0;
}
