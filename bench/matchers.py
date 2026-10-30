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
union: ArcticLampyrid's overlap score proposed on !530: the union of the
    probe keypoints that are inliers against any enrolled image, x10000 over
    max(probe keypoints, mean keypoints of the enrolled images). Inliers from
    ours_det.
vlsift / ftsift: ours_det with SIFT from a C implementation instead of
    OpenCV's, built by csift/build.sh: VLFeat's (BSD), or the one in the
    FocalTech FT9366 driver of a libfprint fork (LGPL). Without OpenCV in
    the matcher itself; upscale + CLAHE still come from OpenCV here.
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

    def __init__(self, pre, detector=None, det=False, mutual=False, limit_angle=False):
        self.pre = pre
        self.ransac_px = 3.0 * (2 if pre else 1)
        self.detector = detector
        self.det = det
        self.mutual = mutual
        self.limit_angle = limit_angle
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
        if self.det:
            return _exact_matches(pa, da, pb, db, self.mutual)
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
        m = self.matches(a, b)
        if m is None:
            return ()
        qi, src, dst = m
        if self.det:
            mask = _similarity_inliers(src, dst, self.ransac_px, self.limit_angle)
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


class CSift(Ransac):
    def __init__(self, lib):
        super().__init__(pre=True, det=True)
        self.libname = lib
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
        n = self._lib.csift_extract(img.ctypes.data, img.shape[1], img.shape[0], len(xy),
                                    xy.ctypes.data, des.ctypes.data)
        if n < 0:
            raise ValueError(f"{self.libname}: unsupported image size {img.shape}")
        # bytes, like stored SIFT descriptors (OpenCV's are scaled the same way)
        des = np.minimum(np.rint(des[:n] * 512), 255).astype(np.uint8)
        return xy[:n].copy(), (des if n else None)


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


def _exact_matches(pa, da, pb, db, mutual):
    """Ratio-test matches on exact integer squared descriptor distances, as
    (probe indices, probe points, gallery points) sorted by distance, then
    probe index. Ties between equally near descriptors go to the lower
    index."""
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
    order = np.lexsort((q, d1))
    q, g = q[order], g[order]
    return np.int32(q), pa[q], pb[g]


def _similarity_inliers(src, dst, px, limit_angle, n_best=50):
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
    "ours_strict": lambda: Ransac(pre=True, det=True, mutual=True, limit_angle=True),
    "union": Union,
    "vlsift": lambda: CSift("libvlsift.so"),
    "ftsift": lambda: CSift("libftsift.so"),
    **{f"{d}{suffix}": (lambda d=d, pre=pre: Ransac(pre, d))
       for d in _DETECTORS for suffix, pre in (("", True), ("_raw", False))},
    "sigfm": lambda: Sigfm("libsigfm.so", pre=False),
    "sigfm_fix": lambda: Sigfm("libsigfm_fixed.so", pre=False),
    "sigfm_pre": lambda: Sigfm("libsigfm.so", pre=True),
}


def get(name):
    return MATCHERS[name]()
