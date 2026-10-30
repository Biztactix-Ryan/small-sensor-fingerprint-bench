#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fit the compact SIFT descriptor codes of the q_* matchers.

The codes are fit on the stranger-only sets (SOCOFing, Family), which part B
never scores, so the benchmark isn't tuned on its own test data. Patches are
cut exactly as for part C; descriptors are those of `ours` (2x upscale +
CLAHE, OpenCV SIFT).

From the descriptors' PCA (centered on their mean):
  pca40    first 40 components, each quantized to a byte (0.5-99.5 percentile)
  bin128   sign of every component relative to its median: 128 bits
  bin256   2 bits per component, its tercile: 256 bits whose Hamming distance
           is the sum of tercile differences
  tern128  ternary: sign bits as bin128, plus "trusted" bits for components
           farther than their 30th percentile from the median: 2 x 128 bits

Usage: fit_quant.py --data DIR [--out quant/sift_quant.npz] [--images 3000]
"""
import argparse
import os
import random
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import big_eval  # noqa: E402
import matchers  # noqa: E402
import public_sets as pub  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def descriptors(job):
    path, dpi, seed = job
    img = big_eval.load_scaled(path, dpi)
    if img is None or min(img.shape) < pub.SIZE:
        return []
    m = matchers.get("ours")
    out = []
    for p in big_eval.jittered(img, 2, 20, random.Random(seed)):
        des = m.features_img(p)[1]
        if des is not None:
            out.append(des)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "quant", "sift_quant.npz"))
    ap.add_argument("--images", type=int, default=3000, help="images per stranger set")
    ap.add_argument("--max-descriptors", type=int, default=400000)
    a = ap.parse_args()
    pub.ROOT = a.data

    jobs = []
    for name in ("socofing", "family"):
        items = pub.strangers(name)
        random.Random(name).shuffle(items)
        jobs += [(p, pub.STRANGER_SETS[name][0], i) for i, (_, p) in enumerate(items[:a.images])]
    with big_eval.pool() as p:
        X = np.concatenate([d for ds in p.map(descriptors, jobs, chunksize=8) for d in ds])
    rng = np.random.default_rng(0)
    if len(X) > a.max_descriptors:
        X = X[rng.choice(len(X), a.max_descriptors, replace=False)]
    X = X.astype(np.float64)
    print(f"{len(jobs)} stranger images, {len(X)} descriptors")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    mu = X.mean(0)
    w, V = np.linalg.eigh(np.cov(X - mu, rowvar=False))
    W = V[:, np.argsort(w)[::-1]]
    Z = (X - mu) @ W
    med = np.median(Z, 0)
    dz = np.abs(Z - med)
    np.savez(a.out if a.out.endswith(".npz") else a.out + ".npz",
             mu=mu, W=W,
             lo40=np.percentile(Z[:, :40], 0.5, 0), hi40=np.percentile(Z[:, :40], 99.5, 0),
             med=med, q33=np.percentile(Z, 100 / 3, 0), q67=np.percentile(Z, 200 / 3, 0),
             dead=np.percentile(dz, 30, 0))
    var = np.sort(w)[::-1]
    print(f"variance in the first 40 components: {100 * var[:40].sum() / var.sum():.1f}%")
    print(f"written {a.out}")


if __name__ == "__main__":
    main()
