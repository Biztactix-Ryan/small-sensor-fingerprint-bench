/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Per-pair match time of akaze_c with FPBENCH_AKAZE_MASK=1, as
 * timing/pairtime.c pairtime_kpm () for the unmasked matchers: calls
 * fpi_keypoint_match_score_masked () through a pointer and returns the
 * CLOCK_MONOTONIC time spent in that call alone.
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

/* fpi_keypoint_match_score_masked () of fpi-keypoint-match.c; the enum
 * flags are an int */
typedef unsigned (*masked_fn) (const void *probe, const void *probe_masks,
                               const void *gallery, const void *gallery_masks,
                               unsigned min_valid_bits, unsigned desc_len,
                               double max_error, unsigned max_matches,
                               int flags, void *inliers);

unsigned
pairtime_masked (masked_fn fn, const void *probe, const void *probe_masks,
                 const void *gallery, const void *gallery_masks,
                 unsigned min_valid_bits, unsigned desc_len, double max_error,
                 unsigned max_matches, int flags, void *inliers, uint64_t *ns)
{
  uint64_t t = now_ns ();
  unsigned r = fn (probe, probe_masks, gallery, gallery_masks, min_valid_bits,
                   desc_len, max_error, max_matches, flags, inliers);

  *ns = now_ns () - t;
  return r;
}
