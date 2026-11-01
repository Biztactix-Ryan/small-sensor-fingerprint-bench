#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compares the C port's AKAZE keypoints (fpi_akaze_detect in libfprint
fpi-keypoint-akaze.c) with OpenCV's, on the same prepared patches as
compare_evolution.py (plus its synthetic images with --synthetic).

    ./build.sh
    PYTHONNOUSERSITE=1 python3 compare_keypoints.py --data DIR [--n 1000] [--synthetic]

The reference is evolution_ref's detectAndCompute through the pinned 4.4.0
sources; its keypoints are checked against the installed cv2.AKAZE first.
Per image the C keypoints must come in the same number and order with
bit-identical x, y, size, angle, response, octave and class_id (level). The
C detector runs twice per image to check it is repeatable.
"""
import argparse
import ctypes
import os
import subprocess
import sys
import tempfile

import numpy as np

import compare_evolution as ce

FIELDS = ("x", "y", "size", "angle", "response", "octave", "class_id")


class Keypoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("size", ctypes.c_float),
                ("angle", ctypes.c_float), ("response", ctypes.c_float),
                ("octave", ctypes.c_int), ("class_id", ctypes.c_int)]


class GArray(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(Keypoint)), ("len", ctypes.c_uint)]


def as_bits(kps):
    """keypoint tuples -> int64 array (n, 7): float bit patterns, then ints"""
    a = np.zeros((len(kps), 7), np.int64)
    for i, k in enumerate(kps):
        a[i, :5] = np.array(k[:5], np.float32).view(np.uint32)
        a[i, 5:] = k[5:]
    return a


def as_values(bits):
    v = bits[:, :5].astype(np.uint32).view(np.float32).astype(np.float64)
    return np.concatenate([v, bits[:, 5:].astype(np.float64)], axis=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="directory with the public datasets")
    ap.add_argument("--n", type=int, default=1000, help="number of patches")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--synthetic", action="store_true", help="add compare_evolution.py's synthetic images")
    args = ap.parse_args()
    os.environ["FPBENCH_DATA"] = os.path.abspath(args.data)
    sys.path.insert(0, os.path.join(ce.HERE, "..", "bench"))
    import cv2

    pats = ce.patches(args.n, args.seed)
    h, w = pats[0][1].shape
    if args.synthetic:
        r = np.random.default_rng(args.seed)
        pats += [("flat0", np.zeros((h, w), np.uint8)), ("flat128", np.full((h, w), 128, np.uint8)),
                 ("noise", r.integers(0, 256, (h, w), dtype=np.uint8)),
                 ("binary", (r.integers(0, 2, (h, w)) * 255).astype(np.uint8)),
                 ("step", np.repeat(np.where(np.arange(w) < w // 2, 0, 255)[None], h, 0).astype(np.uint8))]
    with tempfile.TemporaryDirectory() as tmp:
        raw, dump = os.path.join(tmp, "in.raw"), os.path.join(tmp, "ref.bin")
        with open(raw, "wb") as f:
            for _, p in pats:
                f.write(np.ascontiguousarray(p, np.uint8).tobytes())
        subprocess.run([os.path.join(ce.BUILD, "evolution_ref"), str(w), str(h), raw, dump], check=True)
        ref = ce.read_ref(dump)
    assert len(ref) == len(pats)

    lib = ctypes.CDLL(os.path.join(ce.BUILD, "libakaze_c.so"))
    glib = ctypes.CDLL("libglib-2.0.so.0")
    lib.fpi_akaze_scale_space_new.restype = ctypes.POINTER(ce.ScaleSpace)
    lib.fpi_akaze_scale_space_new.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int)
    lib.fpi_akaze_scale_space_free.argtypes = (ctypes.POINTER(ce.ScaleSpace),)
    lib.fpi_akaze_detect.restype = ctypes.POINTER(GArray)
    lib.fpi_akaze_detect.argtypes = (ctypes.POINTER(ce.ScaleSpace), ctypes.c_float)
    glib.g_array_free.argtypes = (ctypes.POINTER(GArray), ctypes.c_int)
    glib.g_array_free.restype = ctypes.c_void_p

    def detect(buf):
        ss = lib.fpi_akaze_scale_space_new(buf.ctypes.data, w, h)
        arr = lib.fpi_akaze_detect(ss, ctypes.c_float(0.0002))
        a = arr.contents
        out = [tuple(getattr(a.data[i], f) for f in FIELDS) for i in range(a.len)]
        glib.g_array_free(arr, 1)
        lib.fpi_akaze_scale_space_free(ss)
        return out

    akaze = cv2.AKAZE_create(threshold=0.0002)
    harness_bad = repeat_bad = count_bad = order_bad = 0
    total_ref = total_c = 0
    nbits = np.zeros(7, np.int64)
    maxdiff = np.zeros(7)
    worst = []
    per_level = {}
    for (name, p), (_, levels, kps, _) in zip(pats, ref):
        ck = akaze.detect(p, None)
        cvk = as_bits([(k.pt[0], k.pt[1], k.size, k.angle, k.response, k.octave, k.class_id) for k in ck])
        rb = as_bits(kps)
        if not np.array_equal(cvk, rb):
            harness_bad += 1
            print(f"{name}: harness keypoints differ from cv2.AKAZE ({len(rb)} vs {len(cvk)})")

        buf = np.ascontiguousarray(p, np.uint8)
        c1 = detect(buf)
        if detect(buf) != c1:
            repeat_bad += 1
            print(f"{name}: C keypoints differ between two runs")
        cb = as_bits(c1)
        total_ref += len(rb)
        total_c += len(cb)
        for k in rb[:, 6]:
            per_level.setdefault(int(k), [0, 0])[0] += 1
        for k in cb[:, 6]:
            per_level.setdefault(int(k), [0, 0])[1] += 1
        if len(cb) != len(rb):
            count_bad += 1
            worst.append(f"{name}: {len(cb)} C keypoints, OpenCV {len(rb)}")
            continue
        if len(cb) == 0:
            continue
        # same set and order: positions and levels must line up before the floats are compared
        if not np.array_equal(cb[:, 6], rb[:, 6]):
            order_bad += 1
        nbits += (cb != rb).sum(axis=0)
        maxdiff = np.maximum(maxdiff, np.abs(as_values(cb) - as_values(rb)).max(axis=0))

    print(f"{len(pats)} images {w}x{h}, OpenCV {cv2.__version__}")
    print(f"harness vs cv2.AKAZE keypoints: {len(pats) - harness_bad}/{len(pats)} identical")
    print(f"C repeatability: {len(pats) - repeat_bad}/{len(pats)} identical across two runs")
    print(f"keypoints: OpenCV {total_ref}, C {total_c}; images with a different count: {count_bad}; "
          f"with a different level sequence: {order_bad}")
    print("per level (OpenCV / C):", {k: tuple(v) for k, v in sorted(per_level.items())})
    print("field      keypoints differing  max|diff|")
    for i, f in enumerate(FIELDS):
        print(f"{f:<10} {nbits[i]:<20d} {maxdiff[i]:.3g}")
    for line in worst[:20]:
        print(line)
    exact = harness_bad == 0 and repeat_bad == 0 and count_bad == 0 and order_bad == 0 and nbits.sum() == 0
    print("bit-identical" if exact else "NOT bit-identical")
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(main())
