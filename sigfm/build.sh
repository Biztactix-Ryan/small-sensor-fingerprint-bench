#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds the SIGFM variants used by bench/matchers.py:
#   build/libsigfm.so        !530 as is
#   build/libsigfm_fixed.so  with patches/ssubbotin-ordering-and-cap.patch
set -e
cd "$(dirname "$0")"
[ -f src/sigfm.cpp ] || ./fetch.sh
mkdir -p build
CV="$(pkg-config --cflags --libs opencv4)"
g++ -O2 -std=c++17 -shared -fPIC -Isrc src/sigfm.cpp -o build/libsigfm.so $CV
cp src/sigfm.cpp build/sigfm_fixed.cpp
patch -s build/sigfm_fixed.cpp patches/ssubbotin-ordering-and-cap.patch
g++ -O2 -std=c++17 -shared -fPIC -Isrc build/sigfm_fixed.cpp -o build/libsigfm_fixed.so $CV
echo "built: $(ls build/*.so | tr '\n' ' ')"
