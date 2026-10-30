/* SPDX-License-Identifier: LGPL-2.1-or-later
 *
 * One entry point over a C SIFT implementation, for matchers.py:
 *   int csift_extract (const uint8_t *img, int w, int h, int max,
 *                      float *xy, float *desc)
 * returns the number of keypoints (<= max), their positions in xy (x, y
 * pairs) and 128-float descriptors in desc.
 */
#include <stdint.h>
#include <string.h>

#ifdef CSIFT_VLFEAT
#include <vl/sift.h>

int
csift_extract (const uint8_t *img, int w, int h, int max, float *xy, float *desc)
{
  /* like OpenCV: image in [0, 1], first octave upscaled 2x, 3 levels per
   * octave, contrast threshold 0.04 / 3, edge threshold 10 */
  VlSiftFilt *f = vl_sift_new (w, h, -1, 3, -1);
  float *im = vl_malloc (sizeof (float) * w * h);
  int n = 0;

  for (int i = 0; i < w * h; i++)
    im[i] = img[i] / 255.0f;
  vl_sift_set_peak_thresh (f, 0.04 / 3);
  vl_sift_set_edge_thresh (f, 10);
  for (int err = vl_sift_process_first_octave (f, im); !err && n < max;
       err = vl_sift_process_next_octave (f))
    {
      vl_sift_detect (f);
      const VlSiftKeypoint *k = vl_sift_get_keypoints (f);
      for (int i = 0; i < vl_sift_get_nkeypoints (f) && n < max; i++)
        {
          double a[4];
          int na = vl_sift_calc_keypoint_orientations (f, a, k + i);
          for (int j = 0; j < na && n < max; j++, n++)
            {
              xy[2 * n] = k[i].x;
              xy[2 * n + 1] = k[i].y;
              vl_sift_calc_keypoint_descriptor (f, desc + 128 * n, k + i, a[j]);
            }
        }
    }
  vl_free (im);
  vl_sift_delete (f);
  return n;
}
#endif

#ifdef CSIFT_FT9366
#include "ft9366-match.c"

int
csift_extract (const uint8_t *img, int w, int h, int max, float *xy, float *desc)
{
  guint8 im[FT9366_FRAME_PIXELS];
  int n = 0;

  if (w != FT9366_FRAME_WIDTH || h != FT9366_FRAME_HEIGHT)
    return -1;
  /* 255 marks pixels the finger doesn't touch */
  for (int i = 0; i < w * h; i++)
    im[i] = img[i] == FT9366_PX_NONE ? FT9366_PX_NONE - 1 : img[i];
  g_autoptr(Ft9366Features) f = ft9366_features_new (im);
  for (guint i = 0; i < f->n && n < max; i++, n++)
    {
      xy[2 * n] = f->kp[i].x;
      xy[2 * n + 1] = f->kp[i].y;
      memcpy (desc + 128 * n, f->kp[i].d, sizeof (float) * 128);
    }
  return n;
}
#endif
