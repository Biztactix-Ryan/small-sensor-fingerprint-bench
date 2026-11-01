#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
# Fetches the AKAZE reference sources the C port follows into akaze/ref, at
# pinned commits: OpenCV 4.4.0 (the last 3-clause BSD release; its AKAZE code
# is unchanged through 4.10.0), the AKAZE files of OpenCV 4.10.0 (what the box
# runs) to diff against, and the licences of Alcantarilla's original KAZE and
# AKAZE code (BSD-3-Clause). See README.md.
set -e
cd "$(dirname "$0")"
OCV_PORT=c3bb57afeaf030f10939204d48d7c2a3842f4293   # tag 4.4.0
OCV_BOX=71d3237a093b60a27601c20e9ee6c3e52154e8b1    # tag 4.10.0
AKAZE=25d5897483cc8753e2c904aaa10c5a421c3024a8      # pablofdezalc/akaze master
KAZE=93f358f5807d1f7eb32a871918aa424babc898b5       # pablofdezalc/kaze master
RAW=https://raw.githubusercontent.com

AKAZE_FILES="
modules/features2d/src/akaze.cpp
modules/features2d/src/kaze/AKAZEConfig.h
modules/features2d/src/kaze/AKAZEFeatures.cpp
modules/features2d/src/kaze/AKAZEFeatures.h
modules/features2d/src/kaze/TEvolution.h
modules/features2d/src/kaze/fed.cpp
modules/features2d/src/kaze/fed.h
modules/features2d/src/kaze/nldiffusion_functions.cpp
modules/features2d/src/kaze/nldiffusion_functions.h
modules/features2d/src/kaze/utils.h
modules/features2d/include/opencv2/features2d.hpp
"
# OpenCV primitives AKAZE calls, whose numerics the port has to mimic
PRIM_FILES="
LICENSE
modules/imgproc/src/smooth.dispatch.cpp
modules/imgproc/src/smooth.simd.hpp
modules/imgproc/src/deriv.cpp
modules/imgproc/src/filter.dispatch.cpp
modules/imgproc/src/filter.simd.hpp
modules/imgproc/src/resize.cpp
modules/core/src/mathfuncs_core.simd.hpp
modules/core/src/lapack.cpp
modules/core/src/convert_scale.simd.hpp
modules/core/include/opencv2/core/fast_math.hpp
"

get() { # repo rev dir path...
  repo=$1 rev=$2 dir=$3; shift 3
  for f in "$@"; do
    mkdir -p "$dir/$(dirname "$f")"
    curl -fsSL "$RAW/$repo/$rev/$f" -o "$dir/$f"
  done
  echo "fetched $repo at $rev into $dir"
}

rm -rf ref
get opencv/opencv $OCV_PORT ref/opencv-4.4.0 $AKAZE_FILES $PRIM_FILES
get opencv/opencv $OCV_BOX ref/opencv-4.10.0 $AKAZE_FILES LICENSE
get pablofdezalc/akaze $AKAZE ref/libakaze LICENSE
get pablofdezalc/kaze $KAZE ref/kaze LICENSE
