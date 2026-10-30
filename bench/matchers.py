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
    matches; the one with most inliers wins (bit-reproducible, easy in C).
ours_strict: ours_det, plus mutual nearest neighbours only and rotation
    limited to 45 degrees.
union: ArcticLampyrid's overlap score proposed on !530: the union of the
    probe keypoints that are inliers against any enrolled image, x10000 over
    max(probe keypoints, mean keypoints of the enrolled images). Inliers from
    ours_det.
orb / akaze / brisk (+ _raw): the same matcher with binary keypoints and
    descriptors (Hamming distance) instead of SIFT, to see what a matcher
    without SIFT, e.g. one in plain C, would cost.
sigfm / sigfm_fix / sigfm_pre: the SIGFM code of libfprint MR !530, built by
    sigfm/build.sh into sigfm/build. sigfm_fix applies Sergey Subbotin's fix
    proposed on !530 (full match ordering + keep the 176 best matches),
    sigfm_pre runs unmodified SIGFM on images with the ours preprocessing.
    Features go through sigfm_serialize/deserialize like stored prints do.
"""
import ctypes
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
_sift = cv2.SIFT_create()
_bf = cv2.BFMatcher()
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

    def __init__(self, pre, detector=None, det=False, mutual=False, max_rot=None):
        self.pre = pre
        self.ransac_px = 3.0 * (2 if pre else 1)
        self.detector = detector
        self.det = det
        self.mutual = mutual
        self.max_rot = max_rot
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
        return f

    def matches(self, a, b):
        """Ratio-test matches as (probe indices, probe points, gallery points),
        best first for the deterministic estimator."""
        pa, da = a
        pb, db = b
        if da is None or db is None or len(da) < 2 or len(db) < 2:
            return None
        bf = _bf_hamming if self.detector else _bf
        good = [m[0] for m in bf.knnMatch(da, db, k=2)
                if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if self.mutual and good:
            back = {m.queryIdx: m.trainIdx for m in bf.match(db, da)}
            good = [m for m in good if back.get(m.trainIdx) == m.queryIdx]
        if len(good) < 3:
            return None
        if self.det:
            good.sort(key=lambda m: m.distance)
        return (np.int32([m.queryIdx for m in good]),
                pa[[m.queryIdx for m in good]], pb[[m.trainIdx for m in good]])

    def inliers(self, a, b):
        """Indices of the probe keypoints consistent with the best transform."""
        m = self.matches(a, b)
        if m is None:
            return ()
        qi, src, dst = m
        if self.det:
            mask = _similarity_inliers(src, dst, self.ransac_px, self.max_rot)
            return qi[mask] if mask is not None else ()
        M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                             ransacReprojThreshold=self.ransac_px)
        if M is None:
            return ()
        s = np.hypot(M[0, 0], M[1, 0])
        if not 0.85 < s < 1.15:
            return ()
        return qi[inl.ravel() > 0]

    def score(self, a, b):
        return len(self.inliers(a, b))


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


def _similarity_inliers(src, dst, px, max_rot, n_best=50):
    """Inlier mask of the similarity transform (scale 0.85-1.15, rotation within
    max_rot degrees) with most inliers, among those through every pair of the
    n_best first matches. Ties go to the first pair, so the result is
    deterministic."""
    k = min(len(src), n_best)
    i, j = np.triu_indices(k, 1)
    S = src[:, 0] + 1j * src[:, 1]
    D = dst[:, 0] + 1j * dst[:, 1]
    ds, dd = S[j] - S[i], D[j] - D[i]
    ok = np.abs(ds) > 1e-6
    i, j, ds, dd = i[ok], j[ok], ds[ok], dd[ok]
    a = dd / ds
    ok = (np.abs(a) > 0.85) & (np.abs(a) < 1.15)
    if max_rot is not None:
        ok &= np.abs(np.angle(a, deg=True)) <= max_rot
    if not ok.any():
        return None
    a, i = a[ok], i[ok]
    t = D[i] - a * S[i]
    err = np.abs(a[:, None] * S[None, :] + t[:, None] - D[None, :])
    within = err < px
    return within[int(np.argmax(within.sum(1)))]


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

    def score(self, a, b):
        if not a or not b:
            return 0
        return max(0, self.lib.sigfm_match_score(a, b))


MATCHERS = {
    "ours": lambda: Ransac(pre=True),
    "ours_raw": lambda: Ransac(pre=False),
    "ours_det": lambda: Ransac(pre=True, det=True),
    "ours_strict": lambda: Ransac(pre=True, det=True, mutual=True, max_rot=45),
    "union": Union,
    **{f"{d}{suffix}": (lambda d=d, pre=pre: Ransac(pre, d))
       for d in _DETECTORS for suffix, pre in (("", True), ("_raw", False))},
    "sigfm": lambda: Sigfm("libsigfm.so", pre=False),
    "sigfm_fix": lambda: Sigfm("libsigfm_fixed.so", pre=False),
    "sigfm_pre": lambda: Sigfm("libsigfm.so", pre=True),
}


def get(name):
    return MATCHERS[name]()
