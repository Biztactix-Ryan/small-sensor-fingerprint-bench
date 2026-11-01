#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds, in ref/build (not committed):
#   evolution_ref    OpenCV's AKAZE scale space from the pinned 4.4.0 sources,
#                    against the installed OpenCV (pkg-config opencv4)
#   libakaze_c.so    the C port, libfprint/fpi-keypoint-akaze.c of LIBFPRINT,
#                    with fpi-keypoint-prepare.c and fpi-keypoint-match.c: the
#                    whole akaze_c / akaze_det pipeline of bench/matchers.py
#   ../kpm/libkpm.so fpi-keypoint-match.c alone, for the other det matchers
#   libakaze_time.so masked_time.c: the per-pair timer of masked akaze_c;
#                    builds without libfprint, used only with a LIBFPRINT
#                    that has akaze/masked.patch applied
#   extract_c        fpi_akaze_extract on raw images (valgrind, build checks)
# compare_evolution.py, compare_keypoints.py and compare_descriptors.py
# compare the two. ./build.sh lib builds only the libraries (no OpenCV
# sources needed).
set -e
cd "$(dirname "$0")"
LIBFPRINT=${LIBFPRINT:-$HOME/Repo/FingerPrintReader/libfprint-upstream}
L=$LIBFPRINT/libfprint
B=ref/build
mkdir -p $B
# as libfprint builds them: no fused multiply-add, no fast-math
gcc -O2 -std=gnu99 -fPIC -shared -ffp-contract=off -o $B/libakaze_c.so \
  "$L/fpi-keypoint-akaze.c" "$L/fpi-keypoint-prepare.c" "$L/fpi-keypoint-match.c" \
  $(pkg-config --cflags --libs glib-2.0) -lm
mkdir -p ../kpm
gcc -O2 -std=gnu99 -fPIC -shared -ffp-contract=off -o ../kpm/libkpm.so \
  "$L/fpi-keypoint-prepare.c" "$L/fpi-keypoint-match.c" $(pkg-config --cflags --libs glib-2.0) -lm
gcc -O2 -std=gnu99 -fPIC -shared -o $B/libakaze_time.so masked_time.c
[ "$1" = lib ] && { echo "built: $B/libakaze_c.so ../kpm/libkpm.so $B/libakaze_time.so"; exit 0; }
[ -d ref/opencv-4.4.0 ] || ./fetch.sh
mkdir -p $B/src/kaze
cp ref/opencv-4.4.0/modules/features2d/src/kaze/* $B/src/kaze/
cp harness/precomp.hpp $B/src/
# features2d is built for the SSE2 baseline: no FMA, so no contraction
g++ -O2 -std=c++11 -ffp-contract=off -I$B/src/kaze -Iharness -o $B/evolution_ref evolution_ref.cpp \
  $(pkg-config --cflags --libs opencv4)
gcc -O2 -g -std=gnu99 -ffp-contract=off -I"$L" -o $B/extract_c extract_c.c \
  "$L/fpi-keypoint-akaze.c" "$L/fpi-keypoint-prepare.c" "$L/fpi-keypoint-match.c" $(pkg-config --cflags --libs glib-2.0) -lm
echo "built: $B/evolution_ref $B/libakaze_c.so ../kpm/libkpm.so $B/libakaze_time.so $B/extract_c"
