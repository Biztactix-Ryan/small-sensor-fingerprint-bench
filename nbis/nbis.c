/* SPDX-License-Identifier: LGPL-2.1-or-later
 *
 * libfprint's NBIS path (mindtct minutiae + bozorth3), for matchers.py:
 *   int nbis_xyt_size (void)
 *   int nbis_extract (const uint8_t *img, int w, int h, int partial,
 *                     double ppmm, struct xyt_struct *out)
 *   int nbis_score (struct xyt_struct *probe, struct xyt_struct *gallery)
 * nbis_extract does what fp_image_detect_minutiae (fp-image.c) and
 * fpi_print_add_from_image (fpi-print.c) do for an image device frame:
 * get_minutiae with g_lfsparms_V2, perimeter points removed for partial
 * images, then the first MAX_BOZORTH_MINUTIAE converted to NIST x, y, theta
 * and sorted. Returns the number of minutiae found (0 when there are none,
 * which libfprint reports as an error), -1 if mindtct fails. nbis_score is
 * fpi_print_bz3_match's score for one enrolled image.
 *
 * mindtct and bozorth3 are NIST's NBIS (public domain, see the notices in
 * libfprint/nbis), compiled from the libfprint tree, see build.sh.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "nbis.h"

int
nbis_xyt_size (void)
{
  return sizeof (struct xyt_struct);
}

int
nbis_extract (const uint8_t *img, int w, int h, int partial, double ppmm, struct xyt_struct *out)
{
  struct minutiae_struct c[MAX_FILE_MINUTIAE];
  LFSPARMS lfsparms = g_lfsparms_V2;
  MINUTIAE *minutiae = NULL;
  int *quality_map = NULL, *direction_map = NULL, *low_contrast_map = NULL;
  int *low_flow_map = NULL, *high_curve_map = NULL;
  unsigned char *image = g_memdup2 (img, w * h);
  unsigned char *binarized = NULL;
  int map_w, map_h, bw, bh, bd, r, nmin;

  memset (out, 0, sizeof (*out));
  lfsparms.remove_perimeter_pts = partial ? TRUE : FALSE;
  r = get_minutiae (&minutiae, &quality_map, &direction_map,
                    &low_contrast_map, &low_flow_map, &high_curve_map,
                    &map_w, &map_h, &binarized, &bw, &bh, &bd,
                    image, w, h, 8, ppmm, &lfsparms);
  g_free (image);
  g_free (quality_map);
  g_free (direction_map);
  g_free (low_contrast_map);
  g_free (low_flow_map);
  g_free (high_curve_map);
  g_free (binarized);
  if (r)
    {
      if (minutiae)
        free_minutiae (minutiae);
      return -1;
    }
  if (!minutiae)
    return 0;

  /* minutiae_to_xyt of fpi-print.c */
  nmin = MIN (minutiae->num, MAX_BOZORTH_MINUTIAE);
  for (int i = 0; i < nmin; i++)
    {
      struct fp_minutia *m = minutiae->list[i];

      lfs2nist_minutia_XYT (&c[i].col[0], &c[i].col[1], &c[i].col[2], m, w, h);
      c[i].col[3] = sround (m->reliability * 100.0);
      if (c[i].col[2] > 180)
        c[i].col[2] -= 360;
    }
  qsort (&c, nmin, sizeof (struct minutiae_struct), sort_x_y);
  for (int i = 0; i < nmin; i++)
    {
      out->xcol[i] = c[i].col[0];
      out->ycol[i] = c[i].col[1];
      out->thetacol[i] = c[i].col[2];
    }
  out->nrows = nmin;
  r = minutiae->num;
  free_minutiae (minutiae);
  return r;
}

int
nbis_score (struct xyt_struct *probe, struct xyt_struct *gallery)
{
  return bozorth_to_gallery (bozorth_probe_init (probe), probe, gallery);
}
