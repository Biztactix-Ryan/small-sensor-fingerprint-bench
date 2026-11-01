/* SPDX-License-Identifier: LGPL-2.1-or-later
 *
 * Drives patches through libfprint's virtual_image driver, as fprintd would
 * use an image device: enroll a template from its patches, serialize the
 * print and load it back, then verify probes against the loaded print. The
 * score of every comparison is read from libfprint's own debug output
 * ("score %d/%d" of fpi_print_bz3_match, "sigfm score %d/%d" of
 * fpi_print_sigfm_match, "keypoint score %d/%d" of fpi_print_keypoint_match),
 * in the order of the template's prints.
 *
 * Linked statically against the objects of a configured libfprint build
 * (build.sh), so the libfprint code is unmodified; the tool only sets up the
 * driver before use:
 *  - the score threshold is G_MAXINT, so verify scores every enrolled print
 *    instead of stopping at the first match;
 *  - the number of enroll stages is the template's number of patches;
 *  - the device's simulated temperature is off (FP_VIRTUAL_IMAGE_HOT_SECONDS
 *    -1): otherwise it is too hot after about 3 minutes of continuous use
 *    and fails every action (FP_DEVICE_ERROR_TOO_HOT) until it cools down;
 *  - with --sigfm (a !530 build), the image device algorithm is SIGFM, with
 *    --keypoint (the sift-matcher branch) KEYPOINT (akaze_c);
 *  - unless --no-partial, images are flagged FPI_IMAGE_PARTIAL like the elan
 *    driver flags its frames (fpi_image_device_image_captured is wrapped by
 *    the linker, -Wl,--wrap).
 *
 * Usage: virtual_check [--sigfm|--keypoint] [--no-partial] IMAGES PLAN OUT
 * IMAGES: int32 width, int32 height, width * height bytes, per image.
 * PLAN, one per line, processed in order:
 *   T <template id> <image> <image> ...   enroll (and serialize/load) a template
 *   P <template id> <probe id> <image>    verify against the current template
 * OUT, one line per PLAN line, after "#" lines with the build's parameters
 * (--keypoint: "# keypoint NAME=VALUE ..." from the FPI_AKAZE_* macros the
 * build has, so a diff can check the harness ran the same variant):
 *   E <template id> <stored bytes> <round trip> <equal> <accepted images,> <rejected images,> <features,>
 *     round trip: 1 if the loaded print serializes to the same bytes;
 *     equal: fp_print_equal (loaded, enrolled), 0 for SIGFM prints on !530,
 *     which fp_print_equal does not compare
 *   V <template id> <probe id> <ok|retry|error|notemplate> <us> <features> <n> <scores...>
 * features: of each enrolled image / of the probe, "<count>:<sha1>": NBIS
 * minutiae and the first 16 hex digits of the SHA-1 of its struct
 * xyt_struct; SIGFM keypoints and of its sigfm_serialize_binary () blob;
 * KEYPOINT keypoints and of their points (float x, y) followed by their
 * descriptors (FPI_AKAZE_DESCRIPTOR_LEN bytes each); "-" when libfprint
 * gave no print.
 * Images of a template that libfprint rejects (an error or a retry) are left
 * out and the template enrolled again from the others, as a user would
 * present the finger again; "-" for an empty list.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <glib/gstdio.h>

#include "fpi-device.h"
#include "fpi-image.h"
#include "fpi-image-device.h"
#include "fp-context.h"
#include "fp-print-private.h"
#ifdef HAVE_SIGFM
#include "sigfm/sigfm.h"
#endif
#ifdef HAVE_KEYPOINT
#include "fpi-keypoint-akaze.h"
#endif

GType fpi_device_virtual_image_get_type (void);

typedef struct
{
  gint    width, height;
  guint8 *data;
} Image;

static GArray *images;
static GArray *scores;
static gboolean partial = TRUE;
static FpDevice *dev;
static int sock = -1;
/* features of the images of the current action, as features() gives them */
static GPtrArray *feats;

static char *
features (FpPrint *print)
{
  g_autofree char *sum = NULL;

  if (!print || !print->prints || print->prints->len != 1)
    return g_strdup ("-");
  if (print->type == FPI_PRINT_NBIS)
    {
      struct xyt_struct *xyt = g_ptr_array_index (print->prints, 0);

      sum = g_compute_checksum_for_data (G_CHECKSUM_SHA1, (guint8 *) xyt, sizeof (*xyt));
      return g_strdup_printf ("%d:%.16s", xyt->nrows, sum);
    }
#ifdef HAVE_SIGFM
  if (print->type == FPI_PRINT_SIGFM)
    {
      SigfmImgInfo *info = g_ptr_array_index (print->prints, 0);
      int len = 0;
      unsigned char *blob = sigfm_serialize_binary (info, &len);

      sum = g_compute_checksum_for_data (G_CHECKSUM_SHA1, blob, len);
      free (blob);
      return g_strdup_printf ("%d:%.16s", sigfm_keypoints_count (info), sum);
    }
#endif
#ifdef HAVE_KEYPOINT
  if (print->type == FPI_PRINT_KEYPOINT)
    {
      const FpiKeypointPrint *kp = g_ptr_array_index (print->prints, 0);
      g_autoptr(GChecksum) ck = g_checksum_new (G_CHECKSUM_SHA1);

      g_checksum_update (ck, (const guchar *) kp->points, sizeof (FpiKeypoint) * kp->n);
      g_checksum_update (ck, kp->descriptors, (gsize) kp->n * FPI_AKAZE_DESCRIPTOR_LEN);
      return g_strdup_printf ("%u:%.16s", kp->n, g_checksum_get_string (ck));
    }
#endif
  return g_strdup ("?");
}

/* the elan driver marks its frames partial (perimeter minutiae dropped) */
void __real_fpi_image_device_image_captured (FpImageDevice *self,
                                             FpImage       *image);

void
__wrap_fpi_image_device_image_captured (FpImageDevice *self, FpImage *image)
{
  if (partial && image)
    image->flags |= FPI_IMAGE_PARTIAL;
  __real_fpi_image_device_image_captured (self, image);
}

static void
score_logged (const gchar   *domain,
              GLogLevelFlags level,
              const gchar   *message,
              gpointer       user_data)
{
  gint s, t;

  if (sscanf (message, "score %d/%d", &s, &t) == 2 ||
      sscanf (message, "sigfm score %d/%d", &s, &t) == 2 ||
      sscanf (message, "keypoint score %d/%d", &s, &t) == 2)
    g_array_append_val (scores, s);
}

typedef struct
{
  gboolean done;
  gint     events;
  gboolean retried;
  GError  *error;
  FpPrint *print;
} Op;

static void
iterate_until (Op *op, gboolean (*cond)(Op *op, gint arg), gint arg)
{
  while (!op->done && !cond (op, arg))
    g_main_context_iteration (NULL, TRUE);
}

static gboolean
finger_needed (Op *op, gint arg)
{
  return (fp_device_get_finger_status (dev) & FP_FINGER_STATUS_NEEDED) != 0;
}

static gboolean
event_after (Op *op, gint before)
{
  return op->events != before;
}

static gboolean
never (Op *op, gint arg)
{
  return FALSE;
}

static void
send_image (guint i)
{
  Image *img = &g_array_index (images, Image, i);
  gint32 hdr[2] = { img->width, img->height };
  gsize len = (gsize) img->width * img->height;
  const guint8 *p = img->data;

  if (write (sock, hdr, sizeof (hdr)) != sizeof (hdr))
    g_error ("socket write failed");
  while (len > 0)
    {
      ssize_t n = write (sock, p, len);
      if (n <= 0)
        g_error ("socket write failed");
      p += n;
      len -= n;
    }
}

/* sends one image once the device waits for a finger; FALSE if the action
 * ended first */
static gboolean
present (Op *op, guint i)
{
  gint before = op->events;

  iterate_until (op, finger_needed, 0);
  if (op->done)
    return FALSE;
  send_image (i);
  iterate_until (op, event_after, before);
  return TRUE;
}

static void
enroll_progress (FpDevice *device, gint completed, FpPrint *print,
                 gpointer user_data, GError *error)
{
  Op *op = user_data;

  op->events++;
  if (error)
    op->retried = TRUE;
  else
    g_ptr_array_add (feats, features (print));
}

static void
enroll_done (GObject *src, GAsyncResult *res, gpointer user_data)
{
  Op *op = user_data;

  op->print = fp_device_enroll_finish (FP_DEVICE (src), res, &op->error);
  op->done = TRUE;
  op->events++;
}

static void
verify_match (FpDevice *device, FpPrint *match, FpPrint *print,
              gpointer user_data, GError *error)
{
  if (!error)
    g_ptr_array_add (feats, features (print));
}

static void
verify_done (GObject *src, GAsyncResult *res, gpointer user_data)
{
  Op *op = user_data;
  gboolean match;

  fp_device_verify_finish (FP_DEVICE (src), res, &match, NULL, &op->error);
  op->done = TRUE;
  op->events++;
}

static void
print_list (FILE *out, GArray *list)
{
  if (list->len == 0)
    fputs (" -", out);
  for (guint i = 0; i < list->len; i++)
    fprintf (out, "%c%u", i ? ',' : ' ', g_array_index (list, guint, i));
}

/* enrolls @imgs, leaving out (into @rejected) the images libfprint rejects;
 * NULL if it rejects them all */
static FpPrint *
enroll (GArray *imgs, GArray *rejected)
{
  while (imgs->len > 0)
    {
      g_autoptr(GCancellable) cancel = g_cancellable_new ();
      FpPrint *tmpl = fp_print_new (dev);
      Op op = { 0 };
      guint k;

      g_ptr_array_set_size (feats, 0);
      fpi_device_set_nr_enroll_stages (dev, imgs->len);
      fp_device_enroll (dev, tmpl, cancel, enroll_progress, &op, NULL,
                        enroll_done, &op);
      for (k = 0; k < imgs->len; k++)
        {
          if (!present (&op, g_array_index (imgs, guint, k)) ||
              op.retried || (op.done && op.error))
            break;
        }
      if (!op.done && op.retried)
        g_cancellable_cancel (cancel);
      iterate_until (&op, never, 0);

      if (op.print && !op.error)
        return op.print;
      if (k == imgs->len)
        g_error ("enrollment failed without a rejected image: %s",
                 op.error ? op.error->message : "?");
      g_array_append_val (rejected, g_array_index (imgs, guint, k));
      g_array_remove_index (imgs, k);
      g_clear_error (&op.error);
      g_clear_object (&op.print);
    }
  return NULL;
}

static void
verify (FpPrint *tmpl, guint img, const char *tid, const char *pid, FILE *out)
{
  Op op = { 0 };
  const char *status = "ok";
  gint64 t;

  g_array_set_size (scores, 0);
  g_ptr_array_set_size (feats, 0);
  t = g_get_monotonic_time ();
  fp_device_verify (dev, tmpl, NULL, verify_match, NULL, NULL, verify_done, &op);
  present (&op, img);
  iterate_until (&op, never, 0);
  t = g_get_monotonic_time () - t;
  if (op.error)
    status = op.error->domain == FP_DEVICE_RETRY ? "retry" : "error";
  if (op.error && op.error->domain != FP_DEVICE_RETRY)
    g_printerr ("verify %s %s: %s\n", tid, pid, op.error->message);
  fprintf (out, "V %s %s %s %" G_GINT64_FORMAT " %s %u", tid, pid, status, t,
           feats->len == 1 ? (char *) g_ptr_array_index (feats, 0) : "-", scores->len);
  for (guint i = 0; i < scores->len; i++)
    fprintf (out, " %d", g_array_index (scores, gint, i));
  fputc ('\n', out);
  g_clear_error (&op.error);
}

#ifdef HAVE_KEYPOINT
/* the parameters libfprint was built with, those that this build has */
static void
keypoint_params (FILE *out)
{
  fputs ("# keypoint", out);
#ifdef FPI_AKAZE_UPSCALE
  fprintf (out, " upscale=%d", FPI_AKAZE_UPSCALE);
#endif
#ifdef FPI_AKAZE_CLAHE_CLIP
  fprintf (out, " clahe_clip=%g", (double) FPI_AKAZE_CLAHE_CLIP);
#endif
#ifdef FPI_AKAZE_PAD
  fprintf (out, " pad=%d", FPI_AKAZE_PAD);
#endif
#ifdef FPI_AKAZE_THRESHOLD
  fprintf (out, " threshold=%g", (double) FPI_AKAZE_THRESHOLD);
#endif
#ifdef FPI_AKAZE_MAX_KEYPOINTS
  fprintf (out, " max_keypoints=%d", FPI_AKAZE_MAX_KEYPOINTS);
#endif
#ifdef FPI_KEYPOINT_MAX_MATCHES
  fprintf (out, " max_matches=%d", FPI_KEYPOINT_MAX_MATCHES);
#endif
  fputc ('\n', out);
}
#endif

static void
load_images (const char *path)
{
  FILE *f = fopen (path, "rb");
  gint32 wh[2];

  if (!f)
    g_error ("cannot open %s", path);
  images = g_array_new (FALSE, FALSE, sizeof (Image));
  while (fread (wh, sizeof (wh), 1, f) == 1)
    {
      Image img = { wh[0], wh[1], g_malloc ((gsize) wh[0] * wh[1]) };

      if (fread (img.data, 1, (gsize) wh[0] * wh[1], f) != (gsize) wh[0] * wh[1])
        g_error ("short image in %s", path);
      g_array_append_val (images, img);
    }
  fclose (f);
}

int
main (int argc, char **argv)
{
  g_autofree char *dir = g_dir_make_tmp ("virtual-check-XXXXXX", NULL);
  g_autofree char *path = g_build_filename (dir, "virtual-image.socket", NULL);
  g_autoptr(FpContext) ctx = NULL;
  g_autoptr(GError) error = NULL;
  g_autoptr(FpPrint) tmpl = NULL;
  g_autofree char *tmpl_id = NULL;
  gboolean sigfm = FALSE, keypoint = FALSE;
  struct sockaddr_un addr = { .sun_family = AF_UNIX };
  GPtrArray *devices;
  char line[65536];
  FILE *plan, *out;
  int a = 1;

  for (; a < argc && g_str_has_prefix (argv[a], "--"); a++)
    {
      if (g_str_equal (argv[a], "--sigfm"))
        sigfm = TRUE;
      else if (g_str_equal (argv[a], "--keypoint"))
        keypoint = TRUE;
      else if (g_str_equal (argv[a], "--no-partial"))
        partial = FALSE;
      else
        g_error ("unknown option %s", argv[a]);
    }
  if (argc - a != 3)
    {
      g_printerr ("usage: %s [--sigfm|--keypoint] [--no-partial] IMAGES PLAN OUT\n", argv[0]);
      return 2;
    }
  load_images (argv[a]);
  plan = fopen (argv[a + 1], "r");
  out = fopen (argv[a + 2], "w");
  if (!plan || !out)
    g_error ("cannot open the plan or the output");

  g_setenv ("FP_DRIVERS_ALLOWLIST", "virtual_image", TRUE);
  g_setenv ("FP_VIRTUAL_IMAGE", path, TRUE);
  g_setenv ("FP_VIRTUAL_IMAGE_HOT_SECONDS", "-1", TRUE);
  scores = g_array_new (FALSE, FALSE, sizeof (gint));
  feats = g_ptr_array_new_with_free_func (g_free);
  g_log_set_handler ("libfprint-print", G_LOG_LEVEL_DEBUG, score_logged, NULL);

  if (sigfm)
    {
#ifdef HAVE_SIGFM
      FpImageDeviceClass *cls = g_type_class_ref (fpi_device_virtual_image_get_type ());
      cls->algorithm = FPI_DEVICE_ALGO_SIGFM;
#else
      g_error ("--sigfm needs a libfprint build with SIGFM (!530)");
#endif
    }
  if (keypoint)
    {
#ifdef HAVE_KEYPOINT
      FpImageDeviceClass *cls = g_type_class_ref (fpi_device_virtual_image_get_type ());
      cls->algorithm = FPI_DEVICE_ALGO_KEYPOINT;
      keypoint_params (out);
#else
      g_error ("--keypoint needs a libfprint build with KEYPOINT prints (sift-matcher)");
#endif
    }

  ctx = fp_context_new ();
  devices = fp_context_get_devices (ctx);
  for (guint i = 0; i < devices->len && !dev; i++)
    if (g_str_equal (fp_device_get_driver (g_ptr_array_index (devices, i)), "virtual_image"))
      dev = g_ptr_array_index (devices, i);
  if (!dev)
    g_error ("no virtual_image device");
  if (!fp_device_open_sync (dev, NULL, &error))
    g_error ("open: %s", error->message);
#ifdef HAVE_SCORE_THRESHOLD
  fpi_image_device_set_score_threshold (FP_IMAGE_DEVICE (dev), G_MAXINT);
#else
  fpi_image_device_set_bz3_threshold (FP_IMAGE_DEVICE (dev), G_MAXINT);
#endif

  sock = socket (AF_UNIX, SOCK_STREAM, 0);
  g_strlcpy (addr.sun_path, path, sizeof (addr.sun_path));
  if (connect (sock, (struct sockaddr *) &addr, sizeof (addr)) < 0)
    g_error ("cannot connect to %s", path);

  while (fgets (line, sizeof (line), plan))
    {
      g_auto(GStrv) f = g_strsplit_set (g_strstrip (line), " ", -1);

      if (f[0] == NULL || f[0][0] == '\0' || f[0][0] == '#')
        continue;
      if (g_str_equal (f[0], "T"))
        {
          g_autoptr(GArray) imgs = g_array_new (FALSE, FALSE, sizeof (guint));
          g_autoptr(GArray) rejected = g_array_new (FALSE, FALSE, sizeof (guint));
          g_autoptr(FpPrint) enrolled = NULL;
          g_autofree guchar *data = NULL;
          g_autofree guchar *again = NULL;
          gsize len = 0, len_again = 0;

          for (guint i = 2; f[i]; i++)
            {
              guint idx = atoi (f[i]);
              if (idx >= images->len)
                g_error ("image %u out of range", idx);
              g_array_append_val (imgs, idx);
            }
          g_clear_object (&tmpl);
          g_free (tmpl_id);
          tmpl_id = g_strdup (f[1]);
          enrolled = enroll (imgs, rejected);
          fprintf (out, "E %s", tmpl_id);
          if (enrolled)
            {
              if (!fp_print_serialize (enrolled, &data, &len, &error))
                g_error ("serialize: %s", error->message);
              tmpl = fp_print_deserialize (data, len, &error);
              if (!tmpl)
                g_error ("deserialize: %s", error->message);
              /* the loaded print serializes to the same bytes */
              if (!fp_print_serialize (tmpl, &again, &len_again, &error))
                g_error ("serialize: %s", error->message);
              fprintf (out, " %" G_GSIZE_FORMAT " %d %d", len,
                       len == len_again && memcmp (data, again, len) == 0,
                       fp_print_equal (tmpl, enrolled));
            }
          else
            {
              fputs (" 0 0 0", out);
            }
          print_list (out, imgs);
          print_list (out, rejected);
          if (!enrolled || feats->len == 0)
            fputs (" -", out);
          for (guint i = 0; enrolled && i < feats->len; i++)
            fprintf (out, "%c%s", i ? ',' : ' ', (char *) g_ptr_array_index (feats, i));
          fputc ('\n', out);
        }
      else if (g_str_equal (f[0], "P") && f[1] && f[2] && f[3])
        {
          if (!tmpl_id || !g_str_equal (f[1], tmpl_id))
            g_error ("probe for template %s outside its T block", f[1]);
          if (tmpl)
            verify (tmpl, atoi (f[3]), f[1], f[2], out);
          else
            fprintf (out, "V %s %s notemplate 0 - 0\n", f[1], f[2]);
        }
      else
        {
          g_error ("bad plan line: %s", line);
        }
      fflush (out);
    }

  close (sock);
  fp_device_close_sync (dev, NULL, NULL);
  fclose (out);
  fclose (plan);
  g_unlink (path);
  g_rmdir (dir);
  return 0;
}
