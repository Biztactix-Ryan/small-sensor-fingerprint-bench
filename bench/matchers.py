# SPDX-License-Identifier: LGPL-2.1-or-later
"""Matchers for big_eval.py, selected with --matcher.

Each matcher has:
  features_img(img) -> picklable features (computed in worker processes)
  load(features)    -> object for score() (done once in the parent, before the
                       scoring workers fork, so C pointers stay valid in them)
  score(probe, gallery) -> int
  score_set(probe, galleries) -> int, optional: one score against all the
                       enrolled images of a finger (default: best score())
  default           -> the threshold the matcher is meant to be used with
  thresholds        -> thresholds to report

ours / ours_raw: a SIFT + RANSAC matcher (rigid transform, score = inliers),
    with or without its preprocessing (2x upscale + CLAHE). Descriptors are
    stored as bytes like its C implementation, which gives identical scores.
ours_det: ours with a deterministic estimator instead of OpenCV's RANSAC:
    every two-point similarity from the 50 best matches, scored against all
    matches; the one with most inliers wins. Matching is defined exactly
    (integer descriptor distances, fixed order of floating point operations)
    and reproduced bit for bit by fpi-keypoint-match.c in our libfprint
    branch.
ours_strict: ours_det, plus mutual nearest neighbours only and rotation
    limited to 45 degrees.
ours_det2: ours_det, then least squares refits of the best transform to its
    inliers while they gain inliers (what RANSAC's final refinement does).
union: ArcticLampyrid's overlap score proposed on !530: the union of the
    probe keypoints that are inliers against any enrolled image, x10000 over
    max(probe keypoints, mean keypoints of the enrolled images). Inliers from
    ours_det.
vlsift / ftsift: ours_det with SIFT from a C implementation instead of
    OpenCV's, built by csift/build.sh: VLFeat's (BSD), or the one in the
    FocalTech FT9366 driver of a libfprint fork (LGPL). Without OpenCV in
    the matcher itself; upscale + CLAHE still come from OpenCV here.
q_pca40 / q_bin128 / q_bin256 / q_tern128: ours_det with SIFT descriptors
    stored compactly (40, 16, 32 and 32 bytes instead of 128), fit by
    fit_quant.py on the stranger-only sets; matched by euclidean, Hamming and
    masked Hamming distance (ternary). Needs kpm/libkpm.so.
orb / akaze / brisk (+ _raw): the same matcher with binary keypoints and
    descriptors (Hamming distance) instead of SIFT, to see what a matcher
    without SIFT, e.g. one in plain C, would cost.
akaze_c: akaze without OpenCV: upscale + CLAHE and AKAZE (MLDB, 61 byte
    descriptors) from fpi-keypoint-prepare.c and fpi-keypoint-akaze.c of our
    libfprint branch, matched by fpi-keypoint-match.c (Hamming) with the
    strict deterministic matching of ftsift_strict. Built by akaze/build.sh
    (FPBENCH_AKAZE_LIB to override).
    Keeps the FPBENCH_AKAZE_MAX_KP (default 384) strongest keypoints.
    Upscales 3x and pads 20 px before detection, so keypoints are not
    confined to the central half of the frame (AKAZE's descriptor border).
akaze_det: akaze_c with OpenCV's AKAZE features, i.e. akaze with the C
    matching instead of RANSAC, at 2x and without padding. The C features
    equal OpenCV's bit for bit, so its scores equal akaze_c's with
    FPBENCH_AKAZE_UPSCALE=2 FPBENCH_AKAZE_PAD=0.
sigfm / sigfm_fix / sigfm_pre: the SIGFM code of libfprint MR !530, built by
    sigfm/build.sh into sigfm/build. sigfm_fix applies Sergey Subbotin's fix
    proposed on !530 (full match ordering + keep the 176 best matches),
    sigfm_pre runs unmodified SIGFM on images with the ours preprocessing.
    Features go through sigfm_serialize/deserialize like stored prints do.
nbis: what libfprint does today for image devices, NIST's mindtct minutiae
    and bozorth3 score from libfprint's nbis/ tree, built by nbis/build.sh
    into nbis/build/libnbis.so (FPBENCH_NBIS_LIB to override). The patch goes
    to mindtct as the elan press driver submits a 0c3d frame: unscaled, not
    inverted, FPI_IMAGE_PARTIAL (perimeter minutiae removed) and ppmm 0
    (FpImage's default, no driver sets it); the first 200 minutiae are kept,
    as fpi-print.c does. Scores equal libfprint's (nbis/check_libfprint.c).
    Default threshold 24, the elan driver's bz3_threshold; libfprint's
    general default is 40 (BOZORTH3_DEFAULT_THRESHOLD, fp-image-device.c).
    A probe matches a finger when any enrolled image scores at least that.

Per-pair time (big_eval.py): matchers whose score() runs in C (c_timed) call
it through timing/libpairtime.so, which measures the call with
CLOCK_MONOTONIC inside C and adds it to PAIR_NS (and 1 to PAIR_CALLS; a
pair with an empty print never reaches C); n_keypoints(loaded features)
gives the keypoints (minutiae for nbis) of an image.
"""
import ctypes
import os
import subprocess

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
_sift = cv2.SIFT_create()
_bf = cv2.BFMatcher()

# Cost caps (FINAL_RUN.md item 0b), as in libfprint, overridable for sweeps:
# keypoints the deterministic matcher looks at per image (the first ones,
# FPI_KEYPOINT_MAX_POINTS; fixed), candidate matches it keeps (the closest,
# FPI_KEYPOINT_MAX_MATCHES), keypoints akaze_c keeps (FPI_AKAZE_MAX_KEYPOINTS)
# and ftsift keeps (the strongest, see csift/ft9366-topn.patch).
MAX_POINTS = 1024
MAX_MATCHES = int(os.environ.get("FPBENCH_MAX_MATCHES", 64))
AKAZE_MAX_KP = int(os.environ.get("FPBENCH_AKAZE_MAX_KP", 384))
FTSIFT_MAX_KP = int(os.environ.get("FPBENCH_FTSIFT_MAX_KP", 512))
# akaze_c parameters, defaults = libfprint's (FPI_AKAZE_UPSCALE,
# FPI_AKAZE_PAD, FPI_AKAZE_THRESHOLD), overridable for sweeps: upscale
# factor and CLAHE clip of fpi_keypoint_prepare_image_full, pixels of pad
# (replicate, or reflect101 with FPBENCH_AKAZE_PAD_MODE=reflect) added
# around the prepared image before detection, and the detector threshold.
# Upscale 2, pad 0 is the OpenCV-identical port.
AKAZE_UPSCALE = int(os.environ.get("FPBENCH_AKAZE_UPSCALE", 3))
AKAZE_CLAHE_CLIP = float(os.environ.get("FPBENCH_AKAZE_CLAHE_CLIP", 2.0))
AKAZE_PAD_REPLICATE = os.environ.get("FPBENCH_AKAZE_PAD_MODE", "replicate") == "replicate"
AKAZE_THRESHOLD = float(os.environ.get("FPBENCH_AKAZE_THRESHOLD", 0.0002))
# FPBENCH_AKAZE_MASK=1: border-aware descriptors instead of the pad
# (fpi_akaze_extract_masked, fpi_keypoint_match_score_masked; evaluated in
# FINAL_RUN.md item 0c and not kept, so only in a library built from a tree
# with akaze/masked.patch applied: without it these knobs stop). No pad (a
# nonzero FPBENCH_AKAZE_PAD is an error), keypoints detected up to
# FPBENCH_AKAZE_BORDER sigma_size from the edge (FPI_AKAZE_MASKED_BORDER),
# descriptor bits sampling outside the image masked out, and pairs with
# fewer than FPBENCH_AKAZE_MIN_BITS bits valid in both no candidates
# (FPI_AKAZE_MIN_VALID_BITS).
AKAZE_MASK = os.environ.get("FPBENCH_AKAZE_MASK", "0") not in ("", "0")
AKAZE_PAD = int(os.environ.get("FPBENCH_AKAZE_PAD", 0 if AKAZE_MASK else 20))
AKAZE_BORDER = int(os.environ.get("FPBENCH_AKAZE_BORDER", 2))
AKAZE_MIN_BITS = int(os.environ.get("FPBENCH_AKAZE_MIN_BITS", 162))
# FPBENCH_AKAZE_FLOOR_FIRST=1 (masked only, sweep): drop keypoints with
# fewer than FPBENCH_AKAZE_MIN_BITS valid bits before keeping the
# FPBENCH_AKAZE_MAX_KP strongest, so they take no cap slots. Done here on
# uncapped fpi_akaze_extract_masked() output, the same selection as
# keep_strongest() (response, ties to the earlier keypoint).
AKAZE_FLOOR_FIRST = os.environ.get("FPBENCH_AKAZE_FLOOR_FIRST", "0") not in ("", "0")

# The C implementation of the deterministic matcher (fpi-keypoint-match.c of
# our libfprint branch, built as a shared library), if FPBENCH_KPM_LIB names
# it or it is at kpm/libkpm.so: same scores as the Python code below, much
# faster.
_kpm = None


class _Keypoints(ctypes.Structure):
    _fields_ = [("n", ctypes.c_uint), ("points", ctypes.c_void_p), ("descriptors", ctypes.c_void_p)]


def _kpm_lib():
    global _kpm
    path = os.environ.get("FPBENCH_KPM_LIB", os.path.join(HERE, "..", "kpm", "libkpm.so"))
    if _kpm is None and os.path.exists(path):
        _kpm = ctypes.CDLL(path)
        _kpm.fpi_keypoint_match_score.restype = ctypes.c_uint
        _kpm.fpi_keypoint_match_score.argtypes = (ctypes.POINTER(_Keypoints), ctypes.POINTER(_Keypoints),
                                                  ctypes.c_double, ctypes.c_int, ctypes.c_void_p)
        if hasattr(_kpm, "fpi_keypoint_match_score_full"):
            _kpm.fpi_keypoint_match_score_full.restype = ctypes.c_uint
            _kpm.fpi_keypoint_match_score_full.argtypes = _FULL_ARGS
    return _kpm


# fpi_keypoint_match_score_full (probe, gallery, metric, desc_len, max_error,
# max_matches, flags, inliers)
_FULL_ARGS = (ctypes.POINTER(_Keypoints), ctypes.POINTER(_Keypoints), ctypes.c_int, ctypes.c_uint,
              ctypes.c_double, ctypes.c_uint, ctypes.c_int, ctypes.c_void_p)


# Nanoseconds spent in C match calls of this process, measured in C around
# each call (timing/pairtime.c), and the number of those calls (none when
# either print is empty: score() returns 0 without calling C); big_eval.py
# takes differences per pair.
PAIR_NS = 0
PAIR_CALLS = 0
_pairtime = None
_ns = ctypes.c_uint64()


def pairtime_lib():
    global _pairtime
    if _pairtime is None:
        path = os.environ.get("FPBENCH_PAIRTIME_LIB", os.path.join(HERE, "..", "timing", "build", "libpairtime.so"))
        if not os.path.exists(path):
            subprocess.run(["sh", os.path.join(HERE, "..", "timing", "build.sh")], check=True,
                           stdout=subprocess.DEVNULL)
        lib = ctypes.CDLL(path)
        lib.pairtime_kpm.restype = ctypes.c_uint
        lib.pairtime_kpm.argtypes = (ctypes.c_void_p, ctypes.POINTER(_Keypoints), ctypes.POINTER(_Keypoints),
                                     ctypes.c_int, ctypes.c_uint, ctypes.c_double, ctypes.c_uint, ctypes.c_int,
                                     ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64))
        lib.pairtime_pp.restype = ctypes.c_int
        lib.pairtime_pp.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.POINTER(ctypes.c_uint64))
        _pairtime = lib
    return _pairtime


def _fn_ptr(fn):
    return ctypes.cast(fn, ctypes.c_void_p).value


def _timed_pp(fn, a, b):
    """fn(a, b) of a C int f (void *, void *), timed in C."""
    global PAIR_NS, PAIR_CALLS
    r = pairtime_lib().pairtime_pp(_fn_ptr(fn), a, b, ctypes.byref(_ns))
    PAIR_NS += _ns.value
    PAIR_CALLS += 1
    return r


def _c_match(lib, a, b, metric, desc_len, px, flags, max_matches):
    """Probe indices of the inliers from fpi_keypoint_match_score_full,
    timed in C."""
    global PAIR_NS, PAIR_CALLS
    if a[1] is None or b[1] is None:
        return ()
    # normally converted in load(); never pass other layouts to C
    a, b = [(np.ascontiguousarray(p, np.float32), np.ascontiguousarray(d, np.uint8)) for p, d in (a, b)]
    ka, kb = [_Keypoints(len(p), p.ctypes.data, d.ctypes.data) for p, d in (a, b)]
    out = np.zeros(len(a[0]), np.uint32)
    n = pairtime_lib().pairtime_kpm(_fn_ptr(lib.fpi_keypoint_match_score_full), ctypes.byref(ka),
                                     ctypes.byref(kb), metric, desc_len, px, max_matches, flags,
                                     out.ctypes.data, ctypes.byref(_ns))
    PAIR_NS += _ns.value
    PAIR_CALLS += 1
    return out[:n] if n else ()
_bf_hamming = cv2.BFMatcher(cv2.NORM_HAMMING)

# binary detectors, set up for 96x96 frames (192x192 with preprocessing): the
# defaults find few keypoints and drop a wide border
_DETECTORS = {
    "orb": lambda: cv2.ORB_create(nfeatures=1000, nlevels=4, edgeThreshold=16, patchSize=16,
                                  fastThreshold=5),
    "akaze": lambda: cv2.AKAZE_create(threshold=0.0002),
    "brisk": lambda: cv2.BRISK_create(thresh=15, octaves=2),
}


def _preprocess(img):
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return _clahe.apply(img)


class Ransac:
    thresholds = (6, 8, 10, 12, 14, 16, 20)
    default = 10

    def __init__(self, pre, detector=None, det=False, mutual=False, limit_angle=False, refit=False):
        self.pre = pre
        self.ransac_px = 3.0 * (2 if pre else 1)
        self.detector = detector
        self.det = det
        self.mutual = mutual
        self.limit_angle = limit_angle
        self.refit = refit
        self.max_matches = MAX_MATCHES
        self._det = None

    def features_img(self, img):
        if self.pre:
            img = _preprocess(img)
        if self.detector:
            if self._det is None:
                self._det = _DETECTORS[self.detector]()
            kp, des = self._det.detectAndCompute(img, None)
            return np.float32([k.pt for k in kp]), des
        kp, des = _sift.detectAndCompute(img, None)
        if des is not None:
            # stored as bytes, like the C version
            des = np.clip(np.rint(des), 0, 255).astype(np.uint8).astype(np.float32)
        return np.float32([k.pt for k in kp]), des

    def load(self, f):
        if self.det and f[1] is not None:
            # the C matcher's layout: float32 points, byte descriptors
            return np.ascontiguousarray(f[0], np.float32), np.ascontiguousarray(f[1], np.uint8)
        return f

    def matches(self, a, b):
        """Ratio-test matches as (probe indices, probe points, gallery points),
        best first for the deterministic estimator."""
        pa, da = a
        pb, db = b
        if da is None or db is None or len(da) < 2 or len(db) < 2:
            return None
        if self.det:
            return _exact_matches(pa, da, pb, db, self.mutual, self.max_matches)
        bf = _bf_hamming if self.detector else _bf
        good = [m[0] for m in bf.knnMatch(da, db, k=2)
                if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if self.mutual and good:
            back = {m.queryIdx: m.trainIdx for m in bf.match(db, da)}
            good = [m for m in good if back.get(m.trainIdx) == m.queryIdx]
        if len(good) < 3:
            return None
        return (np.int32([m.queryIdx for m in good]),
                pa[[m.queryIdx for m in good]], pb[[m.trainIdx for m in good]])

    def inliers(self, a, b):
        """Indices of the probe keypoints consistent with the best transform."""
        if self.det and _kpm_lib():
            return self._c_inliers(a, b)
        m = self.matches(a, b)
        if m is None:
            return ()
        qi, src, dst = m
        if self.det:
            mask = _similarity_inliers(src, dst, self.ransac_px, self.limit_angle, refit=self.refit)
            return qi[mask] if mask is not None else ()
        M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                             ransacReprojThreshold=self.ransac_px)
        if M is None:
            return ()
        s = np.hypot(M[0, 0], M[1, 0])
        if not 0.85 < s < 1.15:
            return ()
        return qi[inl.ravel() > 0]

    def _c_inliers(self, a, b):
        flags = (1 if self.mutual else 0) | (2 if self.limit_angle else 0) | (4 if self.refit else 0)
        # FPI_KEYPOINT_L2 on 128 byte descriptors
        return _c_match(_kpm, a, b, 0, 128, self.ransac_px, flags, self.max_matches)

    def score(self, a, b):
        return len(self.inliers(a, b))

    @property
    def c_timed(self):
        """Whether score() runs in C (fpi_keypoint_match_score_full)."""
        return bool(self.det and _kpm_lib())

    def n_keypoints(self, f):
        return 0 if f[1] is None else len(f[0])

    def stored_bytes(self, f):
        """Bytes of one enrolled image: float32 x, y and the descriptor (SIFT
        descriptors are stored as bytes)."""
        if f[1] is None:
            return 0
        return len(f[0]) * (8 + (128 if not self.detector else f[1].shape[1]))


class CSift(Ransac):
    def __init__(self, lib, strict=False, max_kp=2048):
        super().__init__(pre=True, det=True, mutual=strict, limit_angle=strict)
        self.libname = lib
        # libftsift keeps the strongest max_kp, libvlsift the first found
        self.max_kp = max_kp
        self._lib = None

    def features_img(self, img):
        if self._lib is None:
            self._lib = ctypes.CDLL(os.path.join(HERE, "..", "csift", "build", self.libname))
            self._lib.csift_extract.restype = ctypes.c_int
            self._lib.csift_extract.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                ctypes.c_void_p, ctypes.c_void_p)
        img = np.ascontiguousarray(_preprocess(img), dtype=np.uint8)
        xy = np.zeros((2048, 2), np.float32)
        des = np.zeros((2048, 128), np.float32)
        n = self._lib.csift_extract(img.ctypes.data, img.shape[1], img.shape[0], min(self.max_kp, len(xy)),
                                    xy.ctypes.data, des.ctypes.data)
        if n < 0:
            raise ValueError(f"{self.libname}: unsupported image size {img.shape}")
        # bytes, like stored SIFT descriptors (OpenCV's are scaled the same way)
        des = np.minimum(np.rint(des[:n] * 512), 255).astype(np.uint8)
        return xy[:n].copy(), (des if n else None)


class _AkazeFeatures(ctypes.Structure):
    # FpiAkazeFeatures
    _fields_ = [("n", ctypes.c_uint), ("keypoints", ctypes.c_void_p), ("points", ctypes.c_void_p),
                ("descriptors", ctypes.c_void_p)]


class _AkazeFeaturesMasked(_AkazeFeatures):
    # FpiAkazeFeatures with akaze/masked.patch: masks (n * 61 bytes) and
    # valid_bits (n guint16), set by fpi_akaze_extract_masked only
    _fields_ = [("masks", ctypes.c_void_p), ("valid_bits", ctypes.c_void_p)]


MASKED_SYMBOLS = ("fpi_akaze_extract_masked", "fpi_keypoint_match_score_masked")


def require_masked(lib, path):
    """Raises if the AKAZE library at path lacks the masked API."""
    missing = [s for s in MASKED_SYMBOLS if not hasattr(lib, s)]
    if missing:
        raise RuntimeError(
            f"FPBENCH_AKAZE_MASK=1 needs {', '.join(missing)}, which {path} lacks: the masked "
            "descriptors are not on the libfprint branch. Apply akaze/masked.patch to a copy of the "
            "libfprint tree and rebuild with LIBFPRINT=<copy> akaze/build.sh lib (see the patch header)")


class AkazeC(Ransac):
    """Features are (points, descriptors), and with FPBENCH_AKAZE_MASK=1
    (points, descriptors, masks): masks like the descriptors, a set bit per
    valid descriptor bit."""
    DESC_LEN = 61  # FPI_AKAZE_DESCRIPTOR_LEN
    _lib = None
    _time = None

    def __init__(self, c_features=True, max_kp=None):
        super().__init__(pre=True, detector="akaze", det=True, mutual=True, limit_angle=True)
        self.c_features = c_features
        self.masked = AKAZE_MASK
        if self.masked and not c_features:
            raise ValueError("FPBENCH_AKAZE_MASK=1 needs the C features (akaze_c, not akaze_det)")
        if self.masked and AKAZE_PAD:
            raise ValueError("FPBENCH_AKAZE_MASK=1 does not pad: FPBENCH_AKAZE_PAD must be 0 or unset")
        if AKAZE_FLOOR_FIRST and not self.masked:
            raise ValueError("FPBENCH_AKAZE_FLOOR_FIRST=1 needs FPBENCH_AKAZE_MASK=1")
        if self.masked:
            self.lib()  # fails now, not in the first worker, without the masked API
        self.max_kp = AKAZE_MAX_KP if max_kp is None else max_kp
        self.upscale = AKAZE_UPSCALE if c_features else 2
        # the same 3 native pixels at any upscale factor
        self.ransac_px = 3.0 * self.upscale

    @classmethod
    def lib(cls):
        if cls._lib is None:
            path = os.environ.get("FPBENCH_AKAZE_LIB", os.path.join(
                HERE, "..", "akaze", "ref", "build", "libakaze_c.so"))
            lib = ctypes.CDLL(path)
            # the masked library's FpiAkazeFeatures has two more fields
            feat = _AkazeFeaturesMasked if AKAZE_MASK else _AkazeFeatures
            lib.fpi_keypoint_prepare_image_full.restype = None
            lib.fpi_keypoint_prepare_image_full.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                                            ctypes.c_int, ctypes.c_double, ctypes.c_void_p)
            lib.fpi_akaze_extract_full.restype = ctypes.POINTER(feat)
            lib.fpi_akaze_extract_full.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                   ctypes.c_int, ctypes.c_float, ctypes.c_uint)
            lib.fpi_akaze_features_free.argtypes = (ctypes.POINTER(feat),)
            lib.fpi_keypoint_match_score_full.restype = ctypes.c_uint
            lib.fpi_keypoint_match_score_full.argtypes = _FULL_ARGS
            if AKAZE_MASK:
                require_masked(lib, path)
                lib.fpi_akaze_extract_masked.restype = ctypes.POINTER(feat)
                lib.fpi_akaze_extract_masked.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                                         ctypes.c_int, ctypes.c_float, ctypes.c_uint)
            cls._lib = lib
        return cls._lib

    @classmethod
    def time_lib(cls):
        """pairtime_masked of akaze/masked_time.c, timing
        fpi_keypoint_match_score_masked as pairtime_kpm does the others."""
        if cls._time is None:
            lib = ctypes.CDLL(os.environ.get("FPBENCH_AKAZE_TIME_LIB", os.path.join(
                HERE, "..", "akaze", "ref", "build", "libakaze_time.so")))
            lib.pairtime_masked.restype = ctypes.c_uint
            lib.pairtime_masked.argtypes = (ctypes.c_void_p, ctypes.POINTER(_Keypoints), ctypes.c_void_p,
                                            ctypes.POINTER(_Keypoints), ctypes.c_void_p, ctypes.c_uint,
                                            ctypes.c_uint, ctypes.c_double, ctypes.c_uint, ctypes.c_int,
                                            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64))
            cls._time = lib
        return cls._time

    def features_img(self, img):
        if not self.c_features:
            return super().features_img(img)
        lib = self.lib()
        img = np.ascontiguousarray(img, np.uint8)
        h, w = img.shape
        k = self.upscale
        if (k * w) % 4 or (k * h) % 4:  # CLAHE tiles, checked in C only by g_return_if_fail
            raise ValueError(f"akaze_c: unsupported image size {img.shape} at upscale {k}")
        pre = np.zeros((k * h, k * w), np.uint8)
        lib.fpi_keypoint_prepare_image_full(img.ctypes.data, w, h, k, AKAZE_CLAHE_CLIP, pre.ctypes.data)
        if self.masked:
            f = lib.fpi_akaze_extract_masked(pre.ctypes.data, k * w, k * h, AKAZE_BORDER, AKAZE_THRESHOLD,
                                             (1 << 30) if AKAZE_FLOOR_FIRST else self.max_kp)
        else:
            f = lib.fpi_akaze_extract_full(pre.ctypes.data, k * w, k * h, AKAZE_PAD, AKAZE_PAD_REPLICATE,
                                           AKAZE_THRESHOLD, self.max_kp)
        if not f:
            raise ValueError(f"akaze_c: unsupported image size {img.shape}")
        n = f.contents.n
        pts = np.ctypeslib.as_array(ctypes.cast(f.contents.points, ctypes.POINTER(ctypes.c_float)),
                                    (n, 2)).copy() if n else np.zeros((0, 2), np.float32)
        des = np.frombuffer(ctypes.string_at(f.contents.descriptors, n * self.DESC_LEN), np.uint8)
        masks = None
        if self.masked and n:
            if not f.contents.masks:
                lib.fpi_akaze_features_free(f)
                raise RuntimeError("akaze_c: fpi_akaze_extract_masked returned no masks")
            masks = np.frombuffer(ctypes.string_at(f.contents.masks, n * self.DESC_LEN),
                                  np.uint8).reshape(n, self.DESC_LEN).copy()
            if AKAZE_FLOOR_FIRST:
                valid = np.frombuffer(ctypes.string_at(f.contents.valid_bits, 2 * n), np.uint16)
                # FpiAkazeKeypoint: x, y, size, angle, response, octave, level
                resp = np.frombuffer(ctypes.string_at(f.contents.keypoints, 28 * n), np.float32).reshape(n, 7)[:, 4]
                keep = np.flatnonzero(valid >= AKAZE_MIN_BITS)
                if len(keep) > self.max_kp:
                    keep = np.sort(keep[np.lexsort((keep, -resp[keep]))][:self.max_kp])
                pts, masks = pts[keep], masks[keep]
                des = des.reshape(n, self.DESC_LEN)[keep].ravel()
                n = len(keep)
                if not n:
                    pts, masks = np.zeros((0, 2), np.float32), None
        lib.fpi_akaze_features_free(f)
        des = des.reshape(n, self.DESC_LEN).copy() if n else None
        return (pts, des, masks) if self.masked else (pts, des)

    def load(self, f):
        if not self.masked:
            return super().load(f)
        if f[1] is None:
            return f
        return (np.ascontiguousarray(f[0], np.float32), np.ascontiguousarray(f[1], np.uint8),
                np.ascontiguousarray(f[2], np.uint8))

    def stored_bytes(self, f):
        """Ransac.stored_bytes, plus the masks: a descriptor's worth of bytes
        per keypoint."""
        b = super().stored_bytes(f)
        return b + (len(f[0]) * self.DESC_LEN if self.masked and f[1] is not None else 0)

    c_timed = True

    def inliers(self, a, b):
        if self.masked:
            return self._masked_inliers(a, b)
        # FPI_KEYPOINT_HAMMING, mutual matches + rotation within 45 degrees
        return _c_match(self.lib(), a, b, 1, self.DESC_LEN, self.ransac_px, 1 | 2, self.max_matches)

    def _masked_inliers(self, a, b):
        """_c_match with fpi_keypoint_match_score_masked: masked normalised
        Hamming distance, mutual matches + rotation within 45 degrees."""
        global PAIR_NS, PAIR_CALLS
        if a[1] is None or b[1] is None:
            return ()
        a, b = [self.load(f) for f in (a, b)]
        ka, kb = [_Keypoints(len(p), p.ctypes.data, d.ctypes.data) for p, d, _ in (a, b)]
        out = np.zeros(len(a[0]), np.uint32)
        n = self.time_lib().pairtime_masked(_fn_ptr(self.lib().fpi_keypoint_match_score_masked),
                                            ctypes.byref(ka), a[2].ctypes.data, ctypes.byref(kb),
                                            b[2].ctypes.data, AKAZE_MIN_BITS, self.DESC_LEN, self.ransac_px,
                                            self.max_matches, 1 | 2, out.ctypes.data, ctypes.byref(_ns))
        PAIR_NS += _ns.value
        PAIR_CALLS += 1
        return out[:n] if n else ()


class Union(Ransac):
    thresholds = (500, 750, 900, 1000, 1200, 1500, 2000)
    default = 1000

    def __init__(self):
        super().__init__(pre=True, det=True)

    def score_set(self, probe, galleries):
        if not galleries:
            return 0
        union = set()
        for g in galleries:
            union.update(int(i) for i in self.inliers(probe, g))
        mean = sum(len(g[0]) for g in galleries) // len(galleries)
        return len(union) * 10000 // max(len(probe[0]), mean, 1)


class Quant(Ransac):
    """ours_det on compact codes of its SIFT descriptors, see fit_quant.py."""
    # metric (fpi-keypoint-match.h) and bytes per descriptor
    KINDS = {"pca40": (0, 40), "bin128": (1, 16), "bin256": (1, 32), "tern128": (2, 32)}
    _params = None

    def __init__(self, kind):
        super().__init__(pre=True, det=True)
        self.kind = kind
        self.metric, self.desc_len = self.KINDS[kind]

    @classmethod
    def params(cls):
        if cls._params is None:
            path = os.environ.get("FPBENCH_QUANT", os.path.join(HERE, "..", "quant", "sift_quant.npz"))
            cls._params = dict(np.load(path))
        return cls._params

    def encode(self, des):
        q = self.params()
        Z = (des.astype(np.float64) - q["mu"]) @ q["W"]
        if self.kind == "pca40":
            z = (Z[:, :40] - q["lo40"]) / (q["hi40"] - q["lo40"]) * 255
            return np.uint8(np.clip(np.rint(z), 0, 255))
        if self.kind == "bin128":
            bits = Z > q["med"]
        elif self.kind == "bin256":
            bits = np.concatenate([Z > q["q33"], Z > q["q67"]], 1)
        else:
            bits = np.concatenate([Z > q["med"], np.abs(Z - q["med"]) > q["dead"]], 1)
        return np.packbits(bits, axis=1)

    def features_img(self, img):
        pts, des = super().features_img(img)
        return pts, (self.encode(des) if des is not None else None)

    c_timed = True

    def inliers(self, a, b):
        if not _kpm_lib() or not hasattr(_kpm, "fpi_keypoint_match_score_full"):
            raise RuntimeError("q_* matchers need kpm/libkpm.so with fpi_keypoint_match_score_full")
        return _c_match(_kpm, a, b, self.metric, self.desc_len, self.ransac_px, 0, self.max_matches)

    def stored_bytes(self, f):
        return 0 if f[1] is None else len(f[0]) * (8 + self.desc_len)


def _exact_matches(pa, da, pb, db, mutual, max_matches=MAX_MATCHES):
    """Ratio-test matches on exact integer squared descriptor distances, as
    (probe indices, probe points, gallery points) sorted by distance, then
    probe index, the first max_matches of them; only the first MAX_POINTS
    keypoints of each image count. Ties between equally near descriptors go
    to the lower index."""
    pa, da, pb, db = pa[:MAX_POINTS], da[:MAX_POINTS], pb[:MAX_POINTS], db[:MAX_POINTS]
    # float64 is exact here (sums of 128 products of bytes are < 2^24) and
    # its matrix product is much faster than numpy's integer one
    A, B = np.float64(da), np.float64(db)
    D = np.int64((A * A).sum(1)[:, None] + (B * B).sum(1)[None, :] - 2 * (A @ B.T))
    q = np.arange(len(A))
    g = D.argmin(1)
    d1 = D[q, g]
    D2 = D.copy()
    D2[q, g] = np.iinfo(np.int64).max
    d2 = D2.min(1)
    ok = 16 * d1 < 9 * d2
    if mutual:
        ok &= D.argmin(0)[g] == q
    q, g, d1 = q[ok], g[ok], d1[ok]
    if len(q) < 3:
        return None
    order = np.lexsort((q, d1))[:max_matches]
    if len(order) < 3:
        return None
    q, g = q[order], g[order]
    return np.int32(q), pa[q], pb[g]


def _similarity_inliers(src, dst, px, limit_angle, n_best=50, refit=False):
    """Inlier mask of the transform (rotation, translation, scale 0.85-1.15,
    optionally rotation within 45 degrees) with most inliers, among those
    through every pair of the n_best first matches; the first maximum wins.
    Same operations in the same order as fpi_keypoint_match_score()."""
    sx, sy = np.float64(src[:, 0]), np.float64(src[:, 1])
    dx, dy = np.float64(dst[:, 0]), np.float64(dst[:, 1])
    k = min(len(sx), n_best)
    i, j = np.triu_indices(k, 1)
    dsx, dsy = sx[j] - sx[i], sy[j] - sy[i]
    ddx, ddy = dx[j] - dx[i], dy[j] - dy[i]
    n2 = dsx * dsx + dsy * dsy
    ok = n2 > 1e-12
    n2 = np.where(ok, n2, 1.0)
    ar = (ddx * dsx + ddy * dsy) / n2
    ai = (ddy * dsx - ddx * dsy) / n2
    s2 = ar * ar + ai * ai
    ok &= (s2 > 0.85 * 0.85) & (s2 < 1.15 * 1.15)
    if limit_angle:
        ok &= (ar > 0) & (ai * ai <= ar * ar)
    if not ok.any():
        return None
    ar, ai, i = ar[ok], ai[ok], i[ok]
    tx = dx[i] - (ar * sx[i] - ai * sy[i])
    ty = dy[i] - (ai * sx[i] + ar * sy[i])
    ex = ar[:, None] * sx[None, :] - ai[:, None] * sy[None, :] + tx[:, None] - dx[None, :]
    ey = ai[:, None] * sx[None, :] + ar[:, None] * sy[None, :] + ty[:, None] - dy[None, :]
    within = ex * ex + ey * ey < px * px
    mask = within[int(np.argmax(within.sum(1)))]
    if refit:
        mask = _refit(sx, sy, dx, dy, mask, px, limit_angle)
    return mask


def _refit(sx, sy, dx, dy, mask, px, limit_angle, rounds=3):
    """Least squares fits of the transform to its inliers while they gain
    inliers; sums in match order, as fpi_keypoint_match_score() does."""
    best = int(mask.sum())
    for _ in range(rounds):
        if best < 3:
            break
        idx = [int(m) for m in np.nonzero(mask)[0]]
        msx = msy = mdx = mdy = 0.0
        for m in idx:
            msx += float(sx[m])
            msy += float(sy[m])
            mdx += float(dx[m])
            mdy += float(dy[m])
        msx /= best
        msy /= best
        mdx /= best
        mdy /= best
        nr = ni = den = 0.0
        for m in idx:
            csx, csy = float(sx[m]) - msx, float(sy[m]) - msy
            cdx, cdy = float(dx[m]) - mdx, float(dy[m]) - mdy
            nr += cdx * csx + cdy * csy
            ni += cdy * csx - cdx * csy
            den += csx * csx + csy * csy
        if den <= 1e-12:
            break
        ar, ai = nr / den, ni / den
        s2 = ar * ar + ai * ai
        if s2 <= 0.85 * 0.85 or s2 >= 1.15 * 1.15:
            break
        if limit_angle and not (ar > 0 and ai * ai <= ar * ar):
            break
        tx = mdx - (ar * msx - ai * msy)
        ty = mdy - (ai * msx + ar * msy)
        ex = ar * sx - ai * sy + tx - dx
        ey = ai * sx + ar * sy + ty - dy
        new = ex * ex + ey * ey < px * px
        if int(new.sum()) <= best:
            break
        mask, best = new, int(new.sum())
    return mask


class Sigfm:
    thresholds = (10, 15, 24, 45, 100, 200, 500, 1000)
    default = 24  # score_threshold of the elan driver in !530

    def __init__(self, lib, pre):
        self.libname = lib
        self.pre = pre
        self._lib = None

    @property
    def lib(self):
        # loaded lazily, so every process gets its own handle after fork
        if self._lib is None:
            lib = ctypes.CDLL(os.path.join(HERE, "..", "sigfm", "build", self.libname))
            lib.sigfm_extract.restype = ctypes.c_void_p
            lib.sigfm_extract.argtypes = (ctypes.c_char_p, ctypes.c_int, ctypes.c_int)
            lib.sigfm_serialize_binary.restype = ctypes.c_void_p
            lib.sigfm_serialize_binary.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
            lib.sigfm_deserialize_binary.restype = ctypes.c_void_p
            lib.sigfm_deserialize_binary.argtypes = (ctypes.c_char_p, ctypes.c_int)
            lib.sigfm_match_score.restype = ctypes.c_int
            lib.sigfm_match_score.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
            lib.sigfm_free_info.argtypes = (ctypes.c_void_p,)
            lib.sigfm_keypoints_count.restype = ctypes.c_int
            lib.sigfm_keypoints_count.argtypes = (ctypes.c_void_p,)
            self._libc = ctypes.CDLL(None)
            self._libc.free.argtypes = (ctypes.c_void_p,)
            self._lib = lib
        return self._lib

    def features_img(self, img):
        if self.pre:
            img = _preprocess(img)
        img = np.ascontiguousarray(img, dtype=np.uint8)
        info = self.lib.sigfm_extract(img.tobytes(), img.shape[1], img.shape[0])
        if not info:
            return None
        n = ctypes.c_int()
        buf = self.lib.sigfm_serialize_binary(info, ctypes.byref(n))
        data = ctypes.string_at(buf, n.value)
        self._libc.free(buf)
        self.lib.sigfm_free_info(info)
        return data

    def load(self, f):
        return self.lib.sigfm_deserialize_binary(f, len(f)) if f else None

    c_timed = True

    def score(self, a, b):
        if not a or not b:
            return 0
        # a is the probe, b the enrolled image; the score isn't symmetric, so
        # pass them in libfprint's order: fpi_print_sigfm_match() (!530) calls
        # sigfm_match_score (enrolled, probe)
        return max(0, _timed_pp(self.lib.sigfm_match_score, b, a))

    def n_keypoints(self, f):
        return self.lib.sigfm_keypoints_count(f) if f else 0

    def stored_bytes(self, f):
        """The serialized info, as stored in a print"""
        return len(f) if f else 0


class Nbis:
    thresholds = (10, 15, 20, 24, 30, 40, 60, 100)
    default = 24  # bz3_threshold of the elan driver; libfprint's default is 40

    def __init__(self):
        self._lib = None

    @property
    def lib(self):
        # loaded lazily, so every process gets its own handle after fork
        if self._lib is None:
            lib = ctypes.CDLL(os.environ.get("FPBENCH_NBIS_LIB", os.path.join(
                HERE, "..", "nbis", "build", "libnbis.so")))
            lib.nbis_extract.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_double, ctypes.c_void_p)
            lib.nbis_score.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
            self._lib = lib
        return self._lib

    def features_img(self, img):
        """struct xyt_struct as bytes, None without minutiae (libfprint then
        has no print)"""
        img = np.ascontiguousarray(img, dtype=np.uint8)
        out = ctypes.create_string_buffer(self.lib.nbis_xyt_size())
        n = self.lib.nbis_extract(img.ctypes.data, img.shape[1], img.shape[0], 1, 0.0, out)
        return out.raw if n > 0 else None

    def load(self, f):
        # bozorth3 takes non-const pointers
        return ctypes.create_string_buffer(f, len(f)) if f else None

    c_timed = True

    def score(self, a, b):
        if a is None or b is None:
            return 0
        return _timed_pp(self.lib.nbis_score, a, b)

    def n_keypoints(self, f):
        """minutiae (struct xyt_struct starts with their int count)"""
        return 0 if f is None else int(np.frombuffer(f, np.int32, 1)[0])

    def stored_bytes(self, f):
        """x, y and theta as int32 per minutia, as fp-print.c serializes them"""
        return 12 * int(np.frombuffer(f, np.int32, 1)[0]) if f else 0


MATCHERS = {
    "ours": lambda: Ransac(pre=True),
    "ours_raw": lambda: Ransac(pre=False),
    "ours_det": lambda: Ransac(pre=True, det=True),
    "ours_strict": lambda: Ransac(pre=True, det=True, mutual=True, limit_angle=True),
    "ours_det2": lambda: Ransac(pre=True, det=True, refit=True),
    "union": Union,
    **{f"q_{k}": (lambda k=k: Quant(k)) for k in Quant.KINDS},
    "vlsift": lambda: CSift("libvlsift.so"),
    "ftsift": lambda: CSift("libftsift.so", max_kp=FTSIFT_MAX_KP),
    "vlsift_strict": lambda: CSift("libvlsift.so", strict=True),
    "ftsift_strict": lambda: CSift("libftsift.so", strict=True, max_kp=FTSIFT_MAX_KP),
    **{f"{d}{suffix}": (lambda d=d, pre=pre: Ransac(pre, d))
       for d in _DETECTORS for suffix, pre in (("", True), ("_raw", False))},
    "akaze_c": AkazeC,
    "akaze_det": lambda: AkazeC(c_features=False),
    "sigfm": lambda: Sigfm("libsigfm.so", pre=False),
    "sigfm_fix": lambda: Sigfm("libsigfm_fixed.so", pre=False),
    "sigfm_pre": lambda: Sigfm("libsigfm.so", pre=True),
    "nbis": Nbis,
}


def get(name):
    return MATCHERS[name]()
