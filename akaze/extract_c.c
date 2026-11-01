/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Runs fpi_akaze_extract on WIDTH x HEIGHT 8-bit images read back to back
 * from IMAGES.raw and writes, per image, the keypoint count, the keypoints
 * (FpiAkazeKeypoint) and the descriptors to OUT.bin. Built by build.sh
 * against the C port; link it against libfprint's libfprint-private.a
 * instead to check the two builds agree, or run it under valgrind.
 */
#include <stdio.h>
#include <stdlib.h>

#include "fpi-keypoint-akaze.h"

int
main (int argc, char **argv)
{
  FILE *in, *out;
  guint8 *buf;
  gint w, h, count = 0, total = 0, empty = 0;

  if (argc != 5)
    {
      fprintf (stderr, "usage: %s WIDTH HEIGHT IMAGES.raw OUT.bin\n", argv[0]);
      return 2;
    }
  w = atoi (argv[1]);
  h = atoi (argv[2]);
  in = fopen (argv[3], "rb");
  out = fopen (argv[4], "wb");
  if (!in || !out)
    return 2;
  buf = g_malloc ((gsize) w * h);

  while (fread (buf, 1, (gsize) w * h, in) == (gsize) w * h)
    {
      FpiAkazeFeatures *f = fpi_akaze_extract (buf, w, h, FPI_AKAZE_THRESHOLD,
                                                FPI_AKAZE_MAX_KEYPOINTS);
      guint n = f ? f->n : 0;

      if (!f)
        empty++;
      fwrite (&n, sizeof (n), 1, out);
      if (n)
        {
          fwrite (f->keypoints, sizeof (FpiAkazeKeypoint), n, out);
          fwrite (f->descriptors, FPI_AKAZE_DESCRIPTOR_LEN, n, out);
        }
      total += n;
      count++;
      fpi_akaze_features_free (f);
    }

  fprintf (stderr, "%d images, %d keypoints, %d refused\n", count, total, empty);
  g_free (buf);
  fclose (in);
  fclose (out);
  return 0;
}
