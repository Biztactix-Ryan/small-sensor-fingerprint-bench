#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Genuine and impostor scores on real captures of one person's fingers.

Each finger is enrolled from its captures of one session; every capture of
the other sessions is verified against it (genuine), and every capture of
the other fingers against it (impostor: one person's different fingers are
strangers to each other). A probe's score is its best against the
enrollment (or score_set() for matchers scoring a whole enrollment).

Layout: DIR/<finger>/<session>-<n>.png, as written by the capture tool.
Directories starting with "_" are ignored (e.g. quarantined mislabelled
captures). Only scores are printed; nothing of the images.

Usage: cross_finger.py --captures DIR --enroll-session SESSION --matcher NAME
"""
import argparse
import glob
import os
import sys
from multiprocessing import get_context

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matchers  # noqa: E402

cv2.setNumThreads(1)
MATCH = None


def features(path):
    return MATCH.features_img(cv2.imread(path, cv2.IMREAD_GRAYSCALE))


def main():
    global MATCH
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", required=True)
    ap.add_argument("--enroll-session", required=True)
    ap.add_argument("--matcher", required=True, choices=sorted(matchers.MATCHERS))
    a = ap.parse_args()
    MATCH = matchers.get(a.matcher)

    fingers = sorted(f for f in os.listdir(a.captures)
                     if not f.startswith("_") and f != "sessions"
                     and os.path.isdir(os.path.join(a.captures, f)))
    caps = [(f, p) for f in fingers for p in sorted(glob.glob(os.path.join(a.captures, f, "*.png")))]
    with get_context("fork").Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        feats = [MATCH.load(x) for x in pool.map(features, [p for _, p in caps])]
    enrolled = {f: [i for i, (g, p) in enumerate(caps)
                    if g == f and os.path.basename(p).startswith(a.enroll_session)] for f in fingers}

    def score(j, f):
        gallery = [feats[t] for t in enrolled[f]]
        if hasattr(MATCH, "score_set"):
            return MATCH.score_set(feats[j], gallery)
        return max(MATCH.score(feats[j], g) for g in gallery)

    gen, imp = [], []
    for j, (g, p) in enumerate(caps):
        for f in fingers:
            if not enrolled[f] or (f == g and j in enrolled[f]):
                continue
            (gen if f == g else imp).append(score(j, f))
    gen, imp = np.array(gen), np.array(imp)
    t = MATCH.default
    print(f"{a.matcher}: {len(fingers)} fingers, enrolled from session {a.enroll_session} "
          f"({sum(map(len, enrolled.values()))} captures)")
    print(f"  impostor attempts {imp.size}, max {imp.max()}, false accepts at {t}: {(imp >= t).sum()}")
    print(f"  genuine attempts {gen.size}, rejected at {t}: {(gen < t).sum()}")


if __name__ == "__main__":
    main()
