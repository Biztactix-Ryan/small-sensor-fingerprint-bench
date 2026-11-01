/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Per-pair match time for bench/big_eval.py: calls a matcher's C match
 * function through a pointer and returns the CLOCK_MONOTONIC time spent in
 * that call alone, so neither Python nor ctypes is counted. The matcher
 * libraries themselves are not rebuilt or changed, so scores stay the same.
 */
#include <stdint.h>
#include <time.h>

static inline uint64_t
now_ns (void)
{
  struct timespec t;

  clock_gettime (CLOCK_MONOTONIC, &t);
  return (uint64_t) t.tv_sec * 1000000000u + (uint64_t) t.tv_nsec;
}

/* fpi_keypoint_match_score_full () of fpi-keypoint-match.c (libkpm.so,
 * libakaze_c.so); the enums are ints */
typedef unsigned (*kpm_fn) (const void *probe, const void *gallery, int metric,
                            unsigned desc_len, double max_error,
                            unsigned max_matches, int flags, void *inliers);

unsigned
pairtime_kpm (kpm_fn fn, const void *probe, const void *gallery, int metric,
              unsigned desc_len, double max_error, unsigned max_matches,
              int flags, void *inliers, uint64_t *ns)
{
  uint64_t t = now_ns ();
  unsigned r = fn (probe, gallery, metric, desc_len, max_error, max_matches,
                   flags, inliers);

  *ns = now_ns () - t;
  return r;
}

/* int f (probe, gallery): sigfm_match_score () and nbis_score () */
typedef int (*pp_fn) (void *probe, void *gallery);

int
pairtime_pp (pp_fn fn, void *probe, void *gallery, uint64_t *ns)
{
  uint64_t t = now_ns ();
  int r = fn (probe, gallery);

  *ns = now_ns () - t;
  return r;
}
