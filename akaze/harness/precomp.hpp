// SPDX-License-Identifier: LGPL-2.1-or-later
// Stands in for OpenCV's internal modules/features2d/src/precomp.hpp so the
// pinned AKAZE sources in ../ref build against an installed OpenCV.
#pragma once
#include <algorithm>
#include <cmath>
#include <iostream>
#include <vector>
#include <opencv2/core.hpp>
#include <opencv2/core/utility.hpp>
#include <opencv2/core/hal/hal.hpp>
#include <opencv2/core/ocl.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/features2d.hpp>

#ifndef CV_INSTRUMENT_REGION
#define CV_INSTRUMENT_REGION()
#endif
// from core/opencl/ocl_defs.hpp without HAVE_OPENCL, and core/private.hpp
#define CV_OCL_RUN(condition, func)
namespace cv { namespace ocl { static inline bool isOpenCLActivated() { return false; } } }
#define CV_TOGGLE_FLT(x) ((x) ^ ((int)(x) < 0 ? 0x7fffffff : 0))

// evolution_ref.cpp reads the evolution AKAZEFeatures keeps private
#define private public
