#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds build/libvlsift.so and build/libftsift.so, see csift.c.
set -e
cd "$(dirname "$0")"
[ -d src/vlfeat ] && [ -d src/ft9366 ] || ./fetch.sh
mkdir -p build
V=src/vlfeat/vl
gcc -O2 -fPIC -shared -DVL_DISABLE_SSE2 -DVL_DISABLE_AVX -DVL_DISABLE_THREADS -DVL_DISABLE_OPENMP \
  -Isrc/vlfeat -DCSIFT_VLFEAT -o build/libvlsift.so csift.c \
  $V/sift.c $V/generic.c $V/host.c $V/imopv.c $V/mathop.c $V/random.c -lm
# the FT9366 code is built for 192x192 frames (96x96 upscaled 2x) and up to
# 1024 keypoints; it is otherwise unchanged
sed -e 's/^#define FT9366_FRAME_WIDTH .*/#define FT9366_FRAME_WIDTH  192/' \
    -e 's/^#define FT9366_FRAME_HEIGHT .*/#define FT9366_FRAME_HEIGHT 192/' \
    src/ft9366/libfprint/drivers/ft9366-match.h > build/ft9366-match.h
sed -e 's/^#define FT9366_MAX_KP .*/#define FT9366_MAX_KP      1024/' \
    src/ft9366/libfprint/drivers/ft9366-match.c > build/ft9366-match.c
gcc -O2 -fPIC -shared -Ibuild -DCSIFT_FT9366 -o build/libftsift.so csift.c \
  $(pkg-config --cflags --libs glib-2.0) -lm
echo "built: build/libvlsift.so build/libftsift.so"
