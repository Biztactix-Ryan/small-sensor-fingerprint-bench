/* SPDX-License-Identifier: LGPL-2.1-or-later
 *
 * Scores images the way a libfprint image device does, to check
 * libnbis.so against it: fp_image_detect_minutiae on a partial image
 * (as elan's press mode submits it), fpi_print_add_from_image, and the
 * bozorth3 score fpi_print_bz3_match compares to the threshold.
 *
 * stdin: images as int32 width, int32 height, width * height bytes.
 * stdout: "min <i> <count>", then "score <probe> <gallery> <score>" for
 * every ordered pair (-1 when either image has no print).
 */
#include <stdio.h>
#include <stdint.h>

#include "fp-print-private.h"
#include "fpi-image.h"

static void
detect_done (GObject *src, GAsyncResult *res, gpointer loop)
{
  g_autoptr(GError) error = NULL;

  if (!fp_image_detect_minutiae_finish (FP_IMAGE (src), res, &error))
    g_printerr ("detect: %s\n", error->message);
  g_main_loop_quit (loop);
}

static void
print_free (gpointer print)
{
  g_clear_object (&print);
}

int
main (void)
{
  g_autoptr(GMainLoop) loop = g_main_loop_new (NULL, FALSE);
  g_autoptr(GPtrArray) prints = g_ptr_array_new_with_free_func (print_free);
  int32_t wh[2];

  while (fread (wh, sizeof (wh), 1, stdin) == 1)
    {
      g_autoptr(FpImage) img = fp_image_new (wh[0], wh[1]);
      g_autoptr(GError) error = NULL;
      FpPrint *print = g_object_new (FP_TYPE_PRINT, "driver", "elan", "device-id", "check", NULL);

      if (fread (img->data, 1, wh[0] * wh[1], stdin) != (size_t) (wh[0] * wh[1]))
        g_error ("short image");
      img->flags |= FPI_IMAGE_PARTIAL;
      fp_image_detect_minutiae (img, NULL, detect_done, loop);
      g_main_loop_run (loop);
      fpi_print_set_type (print, FPI_PRINT_NBIS);
      if (!fpi_print_add_from_image (print, img, &error))
        g_clear_object (&print);
      printf ("min %u %u\n", prints->len,
              fp_image_get_minutiae (img) ? fp_image_get_minutiae (img)->len : 0);
      g_ptr_array_add (prints, print);
    }

  for (guint p = 0; p < prints->len; p++)
    for (guint g = 0; g < prints->len; g++)
      {
        FpPrint *a = g_ptr_array_index (prints, p), *b = g_ptr_array_index (prints, g);
        int score = -1;

        if (p == g)
          continue;
        if (a && b)
          {
            struct xyt_struct *ps = g_ptr_array_index (a->prints, 0);

            score = bozorth_to_gallery (bozorth_probe_init (ps), ps,
                                        g_ptr_array_index (b->prints, 0));
          }
        printf ("score %u %u %d\n", p, g, score);
      }
  return 0;
}
