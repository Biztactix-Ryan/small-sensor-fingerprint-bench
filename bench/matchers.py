# SPDX-License-Identifier: LGPL-2.1-or-later
"""Matchers for big_eval.py, selected with --matcher.

Each matcher has:
  features_img(img) -> picklable features (computed in worker processes)
  load(features)    -> object for score() (done once in the parent, before the
                       scoring workers fork, so C pointers stay valid in them)
  score(probe, gallery) -> int
  default           -> the threshold the matcher is meant to be used with
  thresholds        -> thresholds to report

ours / ours_raw: a SIFT + RANSAC matcher (rigid transform, score = inliers),
    with or without its preprocessing (2x upscale + CLAHE). Descriptors are
    stored as bytes like its C implementation, which gives identical scores.
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


def _preprocess(img):
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return _clahe.apply(img)


class Ransac:
    thresholds = (6, 8, 10, 12, 14, 16, 20)
    default = 10

    def __init__(self, pre):
        self.pre = pre
        self.ransac_px = 3.0 * (2 if pre else 1)

    def features_img(self, img):
        if self.pre:
            img = _preprocess(img)
        kp, des = _sift.detectAndCompute(img, None)
        if des is not None:
            # stored as bytes, like the C version
            des = np.clip(np.rint(des), 0, 255).astype(np.uint8).astype(np.float32)
        return np.float32([k.pt for k in kp]), des

    def load(self, f):
        return f

    def score(self, a, b):
        pa, da = a
        pb, db = b
        if da is None or db is None or len(da) < 2 or len(db) < 2:
            return 0
        good = [m[0] for m in _bf.knnMatch(da, db, k=2)
                if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if len(good) < 3:
            return 0
        src = pa[[m.queryIdx for m in good]]
        dst = pb[[m.trainIdx for m in good]]
        M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                             ransacReprojThreshold=self.ransac_px)
        if M is None:
            return 0
        s = np.hypot(M[0, 0], M[1, 0])
        if not 0.85 < s < 1.15:
            return 0
        return int(inl.sum())


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
    "sigfm": lambda: Sigfm("libsigfm.so", pre=False),
    "sigfm_fix": lambda: Sigfm("libsigfm_fixed.so", pre=False),
    "sigfm_pre": lambda: Sigfm("libsigfm.so", pre=True),
}


def get(name):
    return MATCHERS[name]()
