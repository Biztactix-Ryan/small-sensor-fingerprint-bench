# AKAZE reference for the C port

The C AKAZE (`libfprint/fpi-keypoint-akaze.c`, branch `sift-matcher`) must
reproduce the bench's `akaze` matcher: `cv2.AKAZE_create(threshold=0.0002)` on
96x96 frames upscaled 2x (INTER_CUBIC) and CLAHE'd (clip 2.0, 4x4 tiles), i.e.
192x192 8-bit input. `./fetch.sh` puts the reference sources in `ref/` (not
committed).

## Source and pin

Port from **OpenCV 4.4.0** (tag `4.4.0`, commit
`c3bb57afeaf030f10939204d48d7c2a3842f4293`), `modules/features2d/src/kaze/`
and `akaze.cpp`.

- Alcantarilla's libAKAZE (`pablofdezalc/akaze` @ `25d5897`) is not usable as
  the source: OpenCV rewrote detection, orientation and descriptor sampling in
  2016-2017 (Jiri Horner, Alexander Alekhin), so libAKAZE gives different
  keypoints (e.g. `sigma_size = fRound(esigma)` vs OpenCV's
  `cvRound(esigma * 1.5 / octave_ratio)`, different extrema filtering and
  k-contrast estimate).
- OpenCV 4.6.0 (local) and 4.10.0 (box) AKAZE are the same code:
  `git diff 4.4.0 4.10.0 -- modules/features2d/src/kaze` changes only doxygen
  `@param` names (nldiffusion_functions.cpp, utils.h). The last code change to
  AKAZEFeatures.cpp is 7e7bb30 (2020-03-16), before 4.4.0. `akaze.cpp` gained
  `max_points` (4.x, default -1 = no limit, a no-op here) and FileStorage
  read/write between 4.6 and 4.10; nothing on the compute path.
- Verified empirically: SHA-256 over keypoints (pt, size, angle, response,
  octave, class_id) and descriptors of 200 synthetic integer-generated frames
  (107,931 keypoints; throwaway script, not committed) is identical on
  4.6.0 / i7-13700KF and 4.10.0 / EPYC 7302 (`1dd14b1695a207cc`).
- The OpenCV primitives AKAZE calls (GaussianBlur, Scharr, sepFilter2D,
  resize INTER_AREA, fastAtan2, solve) were refactored between 4.4 and 4.10
  (SIMD intrinsics rewrite), with no output change on the test above. The port
  mimics their arithmetic, read from the 4.4.0 copies in `ref/`.

## Licence

libfprint is LGPL-2.1-or-later.

- **OpenCV >= 4.5.0 is Apache-2.0** (`ref/opencv-4.10.0/LICENSE`: "Apache
  License Version 2.0, January 2004"). The FSF considers Apache-2.0
  incompatible with GPLv2/LGPLv2.1 (patent-termination and indemnity terms)
  but compatible with (L)GPLv3. Code derived from it could only enter libfprint
  if the combined work is distributed under LGPL-3.0 (allowed by "or later"),
  which drops the LGPL-2.1 option for libfprint as a whole and adds Apache §4
  NOTICE obligations: a decision for libfprint upstream, not us. Avoid.
- **OpenCV 4.4.0 is 3-clause BSD** (`ref/opencv-4.4.0/LICENSE`: "License
  Agreement For Open Source Computer Vision Library (3-clause BSD License)",
  Copyright 2000-2020 Intel, 2009-2011 Willow Garage, 2009-2016 NVIDIA,
  2010-2013 AMD, 2015-2016 OpenCV Foundation, 2015-2016 Itseez, 2019-2020
  Xperience AI). That grant for the 4.4.0 text is not revoked by the later
  relicensing. Since the AKAZE code is identical through 4.10.0, porting the
  4.4.0 text gives the same algorithm under BSD-3.
- Per-file headers at 4.4.0:
  - `akaze.cpp`: the old OpenCV BSD header ("Copyright (C) 2008, Willow
    Garage Inc. ... Redistribution and use in source and binary forms, with or
    without modification, are permitted provided that ...").
  - `fed.cpp`: "AKAZE Features Copyright 2013, Pablo F. Alcantarilla, Jesus
    Nuevo / All Rights Reserved / See LICENSE for the license information".
  - `nldiffusion_functions.cpp`: "KAZE Features Copyright 2012, Pablo F.
    Alcantarilla / All Rights Reserved / See LICENSE for the license
    information".
  - `AKAZEFeatures.cpp/.h`, `AKAZEConfig.h`, `TEvolution.h`, `utils.h`: only
    `@author Pablo F. Alcantarilla, Jesus Nuevo`, no licence text (covered by
    the OpenCV LICENSE).
  - The "LICENSE" those headers point to is not shipped by OpenCV; it is
    upstream's: `ref/libakaze/LICENSE` ("Copyright (c) 2014, Pablo Fernandez
    Alcantarilla, Jesus Nuevo", BSD-3-Clause) and `ref/kaze/LICENSE`
    ("Copyright (c) 2012, Pablo Fernández Alcantarilla", BSD-3-Clause).
- BSD-3-Clause is LGPL-2.1-compatible: the port keeps the copyright notices,
  the three conditions and the disclaimer. Conservative plan: the C file is
  LGPL-2.1-or-later for our code and carries, verbatim, the OpenCV 4.4.0
  BSD-3 notice and the Alcantarilla/Nuevo BSD-3 notice (2012 KAZE, 2013-2014
  AKAZE) as the origin of the ported parts.
- Commit-message wording for the libfprint port: "Ported from OpenCV 4.4.0
  (the last 3-clause BSD release; the AKAZE code is unchanged through 4.10),
  itself based on P. F. Alcantarilla and J. Nuevo's AKAZE (BSD-3-Clause).
  BSD-3-Clause is compatible with LGPL-2.1-or-later; the notices are kept in
  the file."

Owner decisions (not settled here): whether libfprint maintainers accept a
BSD-3 notice block inside an LGPL source file (no file in libfprint carries
one today; NBIS is public domain), and whether reproducing the numerics of
OpenCV's imgproc/core primitives counts as derivation (assumed yes, covered by
the same OpenCV 4.4.0 notice).

## Parameters to reproduce

Checked against `AKAZE::create` defaults in features2d.hpp (4.4.0, 4.6.0,
4.10.0, identical apart from `max_points` in 4.10) and the live objects
(`getDescriptorType()` ... on cv2 4.6.0 local and 4.10.0 box: identical).

| parameter | value |
|---|---|
| descriptor_type | `DESCRIPTOR_MLDB` (5): full, rotation-invariant |
| descriptor_size | 0: full 486 bits = (6+36+120)x3, 61 bytes, top 2 bits of byte 60 zero |
| descriptor_channels | 3 (Lt, rotated Lx, rotated Ly) |
| threshold (dthreshold) | `0.0002f` (float: 0.00019999999494757503) |
| nOctaves (omax) | 4, but clamped: an octave is dropped when width < 80 or height < 40, so 192x192 gives **2 octaves** (192, 96) |
| nOctaveLayers (nsublevels) | 4, so 8 evolution levels |
| diffusivity | `DIFF_PM_G2` (1): g = 1 / (1 + \|grad\|^2 / k^2), no exp |
| max_points | -1 (4.10 only; no limit) |

Fixed internals (AKAZEConfig.h / AKAZEFeatures.cpp): soffset 1.6,
derivative_factor 1.5, kcontrast_percentile 0.7, kcontrast_nbins 300,
kcontrast x0.75 per new octave, descriptor_pattern_size 10, FED tau_max 0.25,
reordering true, input `convertTo(CV_32F, 1/255.)`.

Per level (i octave, j sublevel): esigma = 1.6 * 2^(j/4 + i); etime =
esigma^2 / 2; sigma_size = cvRound(esigma * 1.5 / 2^i) = 2, 3, 3, 4 in both
octaves; border = cvRound(10*sqrt(2) * sigma_size) + 1 = 29, 43, 43, 58.
Level 7 (96x96, border 58) can never hold a keypoint. KeyPoint.size =
2 * esigma * 1.5 (4.8, 5.708, 6.788, 8.073, ...), angle in degrees from
fastAtan2.

## Determinism

- OpenCV's result does not depend on the thread count: same hash with
  `setNumThreads(1)`, default (24 / 64) and repeated runs, on both machines.
  Every `parallel_for_` body writes disjoint outputs (rows of the diffusion
  step, whole pyramid levels for the Hessian and the per-level extrema mask,
  single keypoints for orientation and descriptor). Cross-level extrema
  pruning and subpixel refinement are serial, in level then raster order;
  that order fixes keypoint order and must be kept.
- No float reductions in parallel. Order-sensitive serial float sums the port
  must keep exactly: orientation window sums over the counting-sorted samples
  (`quantized_counting_sort` is unstable; its index order is part of the
  result), MLDB cell sums (k then l loops), k-contrast histogram on
  `modgs *= (nbins - 1) / hmax`.
- Approximations to reproduce, not replace: `fastAtan2` (polynomial,
  degrees; scalar and `hal::fastAtan2` vector versions), `cvRound`
  (round-half-even via lrint), 2x2 `solve(DECOMP_LU)` on floats (the 2x2
  special case of `cv::solve` computes determinant and inverse in double),
  Gaussian
  kernels from `getGaussianKernel` (soft-float `getGaussianKernelBitExact`,
  cast to float; only two are used, 9-tap sigma 1.6 and 5-tap sigma 1.0, so
  hard-code them as tables dumped from cv2),
  INTER_AREA 2x downsample (2x2 mean).
- libm dependence: `cosf` in FED tau (constant for these parameters: can be a
  table), `cos`/`sin` of the keypoint angle in MLDB: the float overloads
  (`using namespace std` in AKAZEFeatures.cpp, angle a float; the 4.6
  `libopencv_features2d.so` imports `sincosf`), so the port calls
  `cosf`/`sinf`. Use the same libm in the bench .so and libfprint; glibc's
  cosf/sinf are deterministic per build.
- OpenCV's SIMD filters may contract to FMA (AVX2 dispatch on both machines).
  For bench-vs-libfprint bit identity build the port with
  `-ffp-contract=off` and no `-ffast-math`; exact agreement with OpenCV is
  then expected up to last-bit filter differences, hence the story's
  agreement criterion rather than bit identity with OpenCV. In practice the
  port uses `fmaf()` exactly where the AVX2 filters fuse and is
  bit-identical (see Agreement below).
- OpenCL path (`akaze.cl`) runs only for UMat input; the bench passes numpy
  (Mat), so it is out of scope.

## File map for the port tasks

Paths under `ref/opencv-4.4.0/modules/features2d/src/`.

| task | port from |
|---|---|
| FED / nonlinear scale space | `kaze/fed.cpp` (`fed_tau_by_process_time`, `fed_tau_internal`, `fed_is_prime_internal`); `kaze/AKAZEFeatures.cpp`: `Allocate_Memory_Evolution`, `getGaussianKernelSize`, `nld_step_scalar_one_lane` / `NonLinearScalarDiffusionStep`, `compute_kcontrast`, `compute_diffusivity` (PM_G2 only), `prepareInputImage`, `create_nonlinear_scale_space`; `kaze/nldiffusion_functions.cpp`: `pm_g2`; `kaze/TEvolution.h`. Primitives: `imgproc/src/smooth.*` (GaussianBlur BORDER_REPLICATE), `imgproc/src/deriv.cpp` (Scharr, `getDerivKernels`), `imgproc/src/filter.*` (sepFilter2D, BORDER_DEFAULT = REFLECT_101), `imgproc/src/resize.cpp` (INTER_AREA), `core/src/convert_scale.simd.hpp` |
| Hessian detector + subpixel + orientation | `kaze/AKAZEFeatures.cpp`: `compute_determinant`, `DeterminantHessianResponse` (uses `compute_derivative_kernels` in `kaze/nldiffusion_functions.cpp`), `find_neighbor_point`, `FindKeypointsSameScale`, `Find_Scale_Space_Extrema`, `Do_Subpixel_Refinement`, `Sample_Derivative_Response_Radius6` (gauss25 table), `quantized_counting_sort`, `Compute_Main_Orientation`. Orientation (and MLDB) read the Lx, Ly that `DeterminantHessianResponse` computes with `compute_derivative_kernels` at sigma_size, not `cv::Scharr` (Scharr is only used inside the scale space). Primitives: `core/src/mathfuncs_core.simd.hpp` (fastAtan2), `core/src/lapack.cpp` (2x2 LU solve), `core/include/opencv2/core/fast_math.hpp` (cvRound, cvFloor) |
| MLDB descriptor | `kaze/AKAZEFeatures.cpp`: `Compute_Descriptors` (MLDB, size 0 branch), `MLDB_Full_Descriptor_Invoker::Get_MLDB_Full_Descriptor`, `MLDB_Fill_Values` (chan 3), `MLDB_Binary_Comparisons` (`CV_TOGGLE_FLT` integer compare) |

`ref/opencv-4.10.0/` holds the same AKAZE files at 4.10.0 for diffing;
`ref/libakaze/` and `ref/kaze/` hold only the upstream licences.

## Agreement (C port vs OpenCV 4.6, i7-13700KF)

`./build.sh`, then `compare_evolution.py` (levels), `compare_keypoints.py`
(keypoints) and `compare_descriptors.py` (`fpi_akaze_extract`: keypoints +
MLDB descriptors, byte for byte; `--sensor WxH` for other sensor sizes).
The harness (pinned 4.4.0 sources) equals `cv2.AKAZE.detectAndCompute` on
every image below; the C output repeats exactly across runs.

| input | images | keypoints | C vs OpenCV |
|---|---|---|---|
| 192x192 (96x96 bench patches, seed 1) + 5 synthetic | 1005 | 301,515 | bit-identical (keypoints, all 61 descriptor bytes) |
| 300x104 (150x52 sensor) + 5 synthetic | 205 | 34,576 | bit-identical |
| 224x224 (112x112) + 5 synthetic | 205 | 96,911 | bit-identical |
| 160x176 (80x88) + 5 synthetic | 205 | 40,138 | bit-identical |
| 300x106 (150x53) + 5 synthetic | 205 | 36,077 | bit-identical |
| 322x162 (161x81) | 20 | 9,272 | refused (NULL): octave 2 would be 80x40 from 161x81, not an exact halving |

The filters are exact for widths that are not multiples of 16 too. The scale
space refuses (critical + NULL) any size where a kept octave is not exactly
half the previous one; with 2x-upscaled input that needs a sensor of at least
160x80 with an odd half (e.g. 161x81). `detectAndCompute` neither drops nor
reorders keypoints between detection and description (no mask is passed;
`Compute_Descriptors` describes every keypoint, out-of-level samples are
skipped per sample).

`extract_c` (built by build.sh) runs the extractor on raw images: clean under
valgrind memcheck (no errors, nothing definitely lost) at 192x192, 300x104,
224x224, 160x176, 300x106 and the refused 322x162; linked against
libfprint's `libfprint-private.a` it writes byte-identical output to the bench
build.
