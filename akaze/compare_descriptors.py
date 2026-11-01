#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compares the C port's AKAZE features (fpi_akaze_extract in libfprint
fpi-keypoint-akaze.c: keypoints + MLDB descriptors) with OpenCV's.

    ./build.sh
    PYTHONNOUSERSITE=1 python3 compare_descriptors.py --data DIR [--n 1000] [--synthetic]
    PYTHONNOUSERSITE=1 python3 compare_descriptors.py --data DIR --sensor 150x52

Patches are those of compare_evolution.py (96x96, prepared to 192x192).
With --sensor WxH they are cut at that size around the fingerprint centre
instead (no ridge filter), then prepared the same way (2x bicubic + CLAHE),
to try other sensor sizes. The reference is evolution_ref (pinned 4.4.0
sources); its keypoints and descriptors are checked against the installed
cv2.AKAZE detectAndCompute first.

When the C keypoints equal OpenCV's (count, order, every field) the
descriptors are compared byte for byte. Otherwise keypoints are paired by
level and nearest position (within 1 px of the level) and the report gives
the count difference, the largest field differences and the Hamming
distance of the paired descriptors. The C extractor runs twice per image to
check it is repeatable.
"""
import argparse
import ctypes
import os
import random
import subprocess
import sys
import tempfile

import numpy as np

import compare_evolution as ce
from compare_keypoints import FIELDS, Keypoint, as_bits, as_values

DLEN = 61
CHUNK = 100


class Features(ctypes.Structure):
    _fields_ = [("n", ctypes.c_uint), ("keypoints", ctypes.POINTER(Keypoint)),
                ("points", ctypes.c_void_p), ("descriptors", ctypes.POINTER(ctypes.c_uint8))]


def sensor_patches(n, seed, sw, sh):
    import big_eval
    import matchers
    import public_sets as pub
    idx = pub.index()
    rng = random.Random(seed)
    rng.shuffle(idx)
    out = []
    for s, finger, imp, path in idx:
        img = big_eval.load_scaled(path, pub.SETS[s][0])
        if img is None or img.shape[0] < sh or img.shape[1] < sw:
            continue
        cy, cx = big_eval.centre(img)
        y = int(min(max(cy + rng.gauss(0, 30) - sh / 2, 0), img.shape[0] - sh))
        x = int(min(max(cx + rng.gauss(0, 30) - sw / 2, 0), img.shape[1] - sw))
        p = img[y:y + sh, x:x + sw]
        if p.std() < 10:
            continue
        out.append((f"{s}/{os.path.basename(path)}", matchers._preprocess(np.ascontiguousarray(p))))
        if len(out) == n:
            break
    return out


def popcount(a):
    return np.unpackbits(a, axis=-1).sum(axis=-1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="directory with the public datasets")
    ap.add_argument("--n", type=int, default=1000, help="number of patches")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sensor", help="sensor size WxH (default: 96x96 bench patches)")
    ap.add_argument("--synthetic", action="store_true", help="add compare_keypoints.py's synthetic images")
    args = ap.parse_args()
    os.environ["FPBENCH_DATA"] = os.path.abspath(args.data)
    sys.path.insert(0, os.path.join(ce.HERE, "..", "bench"))
    import cv2

    if args.sensor:
        sw, sh = map(int, args.sensor.split("x"))
        pats = sensor_patches(args.n, args.seed, sw, sh)
    else:
        pats = ce.patches(args.n, args.seed)
    h, w = pats[0][1].shape
    if args.synthetic:
        r = np.random.default_rng(args.seed)
        pats += [("flat0", np.zeros((h, w), np.uint8)), ("flat128", np.full((h, w), 128, np.uint8)),
                 ("noise", r.integers(0, 256, (h, w), dtype=np.uint8)),
                 ("binary", (r.integers(0, 2, (h, w)) * 255).astype(np.uint8)),
                 ("step", np.repeat(np.where(np.arange(w) < w // 2, 0, 255)[None], h, 0).astype(np.uint8))]

    lib = ctypes.CDLL(os.path.join(ce.BUILD, "libakaze_c.so"))
    lib.fpi_akaze_extract.restype = ctypes.POINTER(Features)
    lib.fpi_akaze_extract.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_float,
                                      ctypes.c_uint)
    lib.fpi_akaze_features_free.argtypes = (ctypes.POINTER(Features),)

    def extract(buf):
        # no keypoint cap: OpenCV has none
        f = lib.fpi_akaze_extract(buf.ctypes.data, w, h, ctypes.c_float(0.0002), 0xffffffff)
        if not f:
            return [], np.zeros((0, DLEN), np.uint8)
        a = f.contents
        kps = [tuple(getattr(a.keypoints[i], fl) for fl in FIELDS) for i in range(a.n)]
        d = np.ctypeslib.as_array(a.descriptors, (a.n * DLEN,)).copy().reshape(a.n, DLEN) if a.n else \
            np.zeros((0, DLEN), np.uint8)
        lib.fpi_akaze_features_free(f)
        return kps, d

    akaze = cv2.AKAZE_create(threshold=0.0002)
    st = dict(harness_bad=0, repeat_bad=0, tail_bad=0, kp_bad=0, ref=0, c=0, paired=0,
              unpaired_ref=0, unpaired_c=0, desc_kp=0, desc_bytes=0, desc_bits=0, images_desc_bad=0,
              paired_desc_kp=0, paired_desc_bits=0)
    maxdiff = np.zeros(7)
    max_ham = 0
    worst = []
    for c0 in range(0, len(pats), CHUNK):
        chunk = pats[c0:c0 + CHUNK]
        with tempfile.TemporaryDirectory() as tmp:
            raw, dump = os.path.join(tmp, "in.raw"), os.path.join(tmp, "ref.bin")
            with open(raw, "wb") as f:
                for _, p in chunk:
                    f.write(np.ascontiguousarray(p, np.uint8).tobytes())
            subprocess.run([os.path.join(ce.BUILD, "evolution_ref"), str(w), str(h), raw, dump],
                           check=True, stderr=subprocess.DEVNULL)
            ref = ce.read_ref(dump)
        assert len(ref) == len(chunk)
        for (name, p), (_, _, kps, desc) in zip(chunk, ref):
            ck, cd = akaze.detectAndCompute(p, None)
            cd = cd if cd is not None else np.zeros((0, DLEN), np.uint8)
            cvk = as_bits([(k.pt[0], k.pt[1], k.size, k.angle, k.response, k.octave, k.class_id) for k in ck])
            rb = as_bits(kps)
            if not np.array_equal(cvk, rb) or cd.tobytes() != desc.tobytes():
                st["harness_bad"] += 1
                print(f"{name}: harness differs from cv2.AKAZE detectAndCompute")

            buf = np.ascontiguousarray(p, np.uint8)
            k1, d1 = extract(buf)
            k2, d2 = extract(buf)
            if k1 != k2 or d1.tobytes() != d2.tobytes():
                st["repeat_bad"] += 1
                print(f"{name}: C features differ between two runs")
            if len(d1) and (d1[:, 60] & 0xc0).any():
                st["tail_bad"] += 1
            cb = as_bits(k1)
            st["ref"] += len(rb)
            st["c"] += len(cb)

            if len(cb) == len(rb) and np.array_equal(cb, rb):
                diff = d1 != desc
                if diff.any():
                    st["images_desc_bad"] += 1
                    st["desc_kp"] += int(diff.any(axis=1).sum())
                    st["desc_bytes"] += int(diff.sum())
                    st["desc_bits"] += int(popcount(d1 ^ desc).sum())
                    bad = np.flatnonzero(diff.any(axis=1))
                    worst.append(f"{name}: descriptors of keypoints {bad[:10].tolist()} differ")
                continue

            st["kp_bad"] += 1
            worst.append(f"{name}: {len(cb)} C keypoints, OpenCV {len(rb)}")
            rv, cv_ = as_values(rb), as_values(cb)
            used = np.zeros(len(rb), bool)
            for i in range(len(cb)):
                cand = np.flatnonzero((rb[:, 6] == cb[i, 6]) & ~used)
                if not len(cand):
                    continue
                ratio = 2.0 ** cb[i, 5]
                dist = np.hypot(rv[cand, 0] - cv_[i, 0], rv[cand, 1] - cv_[i, 1])
                j = cand[np.argmin(dist)]
                if dist.min() > ratio:
                    continue
                used[j] = True
                st["paired"] += 1
                d = np.abs(rv[j] - cv_[i])
                d[3] = min(d[3], 360 - d[3])
                maxdiff = np.maximum(maxdiff, d)
                ham = int(popcount(d1[i] ^ desc[j]))
                if ham:
                    st["paired_desc_kp"] += 1
                    st["paired_desc_bits"] += ham
                    max_ham = max(max_ham, ham)
            st["unpaired_ref"] += int((~used).sum())
            st["unpaired_c"] += len(cb) - int(used.sum())

    n = len(pats)
    print(f"{n} images {w}x{h}, OpenCV {cv2.__version__}")
    print(f"harness vs cv2.AKAZE (keypoints + descriptors): {n - st['harness_bad']}/{n} identical")
    print(f"C repeatability: {n - st['repeat_bad']}/{n} identical across two runs")
    print(f"descriptors with nonzero top 2 bits of byte 60: {st['tail_bad']} images")
    print(f"keypoints: OpenCV {st['ref']}, C {st['c']}; images with identical keypoints: {n - st['kp_bad']}/{n}")
    print(f"on identical keypoints: {st['images_desc_bad']} images, {st['desc_kp']} descriptors, "
          f"{st['desc_bytes']} bytes, {st['desc_bits']} bits differ")
    if st["kp_bad"]:
        print(f"other images: {st['paired']} keypoints paired, {st['unpaired_ref']} OpenCV and "
              f"{st['unpaired_c']} C unpaired; paired descriptors differing: {st['paired_desc_kp']} "
              f"({st['paired_desc_bits']} bits, max Hamming {max_ham} of 486)")
        print("paired max|diff|: " + ", ".join(f"{f} {maxdiff[i]:.3g}" for i, f in enumerate(FIELDS)))
    for line in worst[:20]:
        print(line)
    exact = (st["harness_bad"] == 0 and st["repeat_bad"] == 0 and st["tail_bad"] == 0
             and st["kp_bad"] == 0 and st["desc_bytes"] == 0)
    print("bit-identical" if exact else "NOT bit-identical")
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(main())
