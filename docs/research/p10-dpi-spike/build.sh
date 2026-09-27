#!/bin/sh
# Build the C++ core (shared library for ctypes) and the standalone benchmark.
# -ffp-contract=off keeps floating point identical to numba's (no fused multiply-add).
set -eu
cd "$(dirname "$0")"
mkdir -p build
CXX="${CXX:-clang++}"
FLAGS="-O3 -std=c++17 -ffp-contract=off -Wall -Wextra"
case "$(uname -s)" in
  Darwin) LIB=libdpi.dylib; SHARED="-dynamiclib" ;;
  *)      LIB=libdpi.so;    SHARED="-shared -fPIC" ;;
esac
$CXX $FLAGS $SHARED dpi_core.cpp -o "build/$LIB"
$CXX $FLAGS -pthread bench_cpp.cpp dpi_core.cpp -o build/bench_cpp
"$CXX" --version | head -1
echo "built build/$LIB build/bench_cpp"
