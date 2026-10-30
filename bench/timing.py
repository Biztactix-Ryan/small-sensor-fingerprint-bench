#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Single-threaded speed of each matcher, as it would run in libfprint.

For each matcher: feature extraction per image, one probe-vs-image match
(genuine and impostor pairs separately, since RANSAC-style matching costs
more when many keypoints match), and from those the time of a verify
(extract the probe + match it against every enrolled image) and of an
identify over 10 enrolled fingers. Also the size of the stored features.

Times are the minimum over --repeat runs (closest to an idle machine) and
the median. Python overhead is included, so they are upper bounds for a C
implementation; matchers whose work is in C (OpenCV, SIGFM, the C SIFTs,
kpm/libkpm.so) are close to what libfprint would see.

Usage: timing.py --captures DIR [--matchers a,b] [--stages 20]
  DIR/<finger>/*.png, e.g. real captures (only timings are printed)
"""
import argparse
import glob
import os
import pickle
import sys
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import cv2  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matchers  # noqa: E402

cv2.setNumThreads(1)


def timed(fn, repeat):
    ts = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t)
    return min(ts), float(np.median(ts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", required=True)
    ap.add_argument("--matchers", default="ours,ours_det,ours_strict,vlsift,ftsift,akaze,orb,sigfm,sigfm_fix,union")
    ap.add_argument("--stages", type=int, default=20)
    ap.add_argument("--repeat", type=int, default=5)
    a = ap.parse_args()

    fingers = sorted(f for f in os.listdir(a.captures)
                     if not f.startswith("_") and os.path.isdir(os.path.join(a.captures, f)) and f != "sessions")
    imgs = {f: [cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                for p in sorted(glob.glob(os.path.join(a.captures, f, "*.png")))]
            for f in fingers}
    fingers = [f for f in fingers if len(imgs[f]) >= 2][:2]
    if len(fingers) < 2:
        sys.exit("need two fingers with at least 2 captures each")
    f1, f2 = fingers
    # probe = last capture; enrollment = the others, repeated if too few
    for f in fingers:
        rest = imgs[f][:-1]
        imgs[f] = (rest * (a.stages // len(rest) + 1))[:a.stages] + imgs[f][-1:]

    print(f"single thread, {a.stages} enrolled images per finger, min / median of {a.repeat} runs, ms\n")
    print("| matcher | extract | match genuine | match impostor | verify (extract + "
          f"{a.stages} matches) | identify, 10 fingers | stored bytes per image |")
    print("|---|---|---|---|---|---|---|")
    for name in a.matchers.split(","):
        m = matchers.get(name)
        probe_img = imgs[f1][-1]
        ext = timed(lambda: m.features_img(probe_img), a.repeat * 4)
        enrolled = [m.load(m.features_img(i)) for i in imgs[f1][:a.stages]]
        other = [m.load(m.features_img(i)) for i in imgs[f2][:a.stages]]
        probe = m.load(m.features_img(probe_img))
        size = np.mean([len(pickle.dumps(m.features_img(i))) for i in imgs[f1][:5]])

        if hasattr(m, "score_set"):
            gen = timed(lambda: m.score_set(probe, enrolled), a.repeat)
            imp = timed(lambda: m.score_set(probe, other), a.repeat)
            per_match = None  # score_set covers the whole enrollment at once
        else:
            gen = timed(lambda: [m.score(probe, g) for g in enrolled], a.repeat)
            imp = timed(lambda: [m.score(probe, g) for g in other], a.repeat)
            per_match = [(x[0] / a.stages, x[1] / a.stages) for x in (gen, imp)]
        # verify against the right finger, identify against 1 right + 9 wrong
        verify = (ext[0] + gen[0], ext[1] + gen[1])
        ident = (ext[0] + gen[0] + 9 * imp[0], ext[1] + gen[1] + 9 * imp[1])

        def f(x):
            return f"{1000 * x[0]:.1f} / {1000 * x[1]:.1f}"
        g1, i1 = [f(x) for x in per_match] if per_match else ("-", "-")
        print(f"| {name} | {f(ext)} | {g1} | {i1} | {f(verify)} | {f(ident)} | {size:.0f} |", flush=True)


if __name__ == "__main__":
    main()
