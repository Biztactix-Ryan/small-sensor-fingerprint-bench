#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compares the C port's AKAZE scale space (libfprint fpi-keypoint-akaze.c)
with OpenCV's, level by level (Lt, Lsmooth, Lx, Ly, Ldet), on prepared patches of the public datasets.

    ./build.sh
    PYTHONNOUSERSITE=1 python3 compare_evolution.py --data DIR [--n 50]

Patches are cut as bench/big_eval.py does (jittered() around the fingerprint
centre) and prepared as the matchers do (_preprocess: 2x bicubic + CLAHE),
so they are what the akaze matcher sees. evolution_ref dumps OpenCV's levels;
it is first checked against the installed cv2.AKAZE (same keypoints and
descriptors), then the C levels are compared with it. Images stay in a
temporary directory.
"""
import argparse
import ctypes
import os
import random
import struct
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "ref", "build")
MAX_LEVELS = 16


class Level(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int),
                ("octave", ctypes.c_int), ("sublevel", ctypes.c_int),
                ("sigma_size", ctypes.c_int), ("border", ctypes.c_int),
                ("esigma", ctypes.c_float), ("etime", ctypes.c_float), ("octave_ratio", ctypes.c_float),
                ("lt", ctypes.POINTER(ctypes.c_float)), ("lsmooth", ctypes.POINTER(ctypes.c_float)),
                ("lx", ctypes.POINTER(ctypes.c_float)), ("ly", ctypes.POINTER(ctypes.c_float)),
                ("ldet", ctypes.POINTER(ctypes.c_float))]


class ScaleSpace(ctypes.Structure):
    _fields_ = [("n_levels", ctypes.c_int), ("kcontrast", ctypes.c_float), ("levels", Level * MAX_LEVELS)]


def patches(n, seed):
    import big_eval
    import matchers
    import public_sets as pub
    idx = pub.index()
    if not idx:
        sys.exit(f"no public datasets under {pub.ROOT}")
    rng = random.Random(seed)
    rng.shuffle(idx)
    out = []
    for s, finger, imp, path in idx:
        img = big_eval.load_scaled(path, pub.SETS[s][0])
        if img is None or min(img.shape) < pub.SIZE:
            continue
        for p in big_eval.jittered(img, 1, 30, rng):
            out.append((f"{s}/{os.path.basename(path)}", matchers._preprocess(p)))
        if len(out) == n:
            break
    return out


def read_ref(path):
    """[(kcontrast, levels, keypoints, descriptors)] from evolution_ref."""
    data = open(path, "rb").read()
    pos, out = 0, []

    def take(fmt):
        nonlocal pos
        v = struct.unpack_from("<" + fmt, data, pos)
        pos += struct.calcsize("<" + fmt)
        return v

    def floats(n):
        nonlocal pos
        a = np.frombuffer(data, "<f4", n, pos)
        pos += 4 * n
        return a

    while pos < len(data):
        assert data[pos:pos + 4] == b"AKZE"
        pos += 4
        nl, kc = take("if")
        levels = []
        for _ in range(nl):
            w, h, octave, sub, ssize, border, esigma, etime, ntau = take("iiiiiiffi")
            tau = floats(ntau)
            lt = floats(w * h).reshape(h, w)
            ls = floats(w * h).reshape(h, w)
            lx, ly, ldet = (floats(w * h).reshape(h, w) for _ in range(3))
            levels.append(dict(w=w, h=h, octave=octave, sublevel=sub, sigma_size=ssize, border=border,
                               esigma=np.float32(esigma), etime=np.float32(etime), tau=tau, lt=lt, lsmooth=ls,
                               lx=lx, ly=ly, ldet=ldet))
        nk, dcols = take("ii")
        kps, desc = [], []
        for _ in range(nk):
            kps.append(take("fffffii"))
            desc.append(np.frombuffer(data, np.uint8, dcols, pos))
            pos += dcols
        out.append((np.float32(kc), levels, kps, np.array(desc, np.uint8).reshape(nk, dcols)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="directory with the public datasets")
    ap.add_argument("--n", type=int, default=50, help="number of patches")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--synthetic", action="store_true",
                    help="add flat, noise and saturated images (edge cases: zero gradient, extreme values)")
    args = ap.parse_args()
    os.environ["FPBENCH_DATA"] = os.path.abspath(args.data)
    sys.path.insert(0, os.path.join(HERE, "..", "bench"))
    import cv2

    pats = patches(args.n, args.seed)
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
        subprocess.run([os.path.join(BUILD, "evolution_ref"), str(w), str(h), raw, dump], check=True)
        ref = read_ref(dump)
    assert len(ref) == len(pats)

    lib = ctypes.CDLL(os.path.join(BUILD, "libakaze_c.so"))
    lib.fpi_akaze_scale_space_new.restype = ctypes.POINTER(ScaleSpace)
    lib.fpi_akaze_scale_space_new.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int)
    lib.fpi_akaze_scale_space_free.argtypes = (ctypes.POINTER(ScaleSpace),)

    akaze = cv2.AKAZE_create(threshold=0.0002)
    harness_bad = param_bad = 0
    nlev = len(ref[0][1])
    fields = ("lt", "lsmooth", "lx", "ly", "ldet")
    worst = {k: np.zeros(nlev) for k in fields}
    ndiff = {k: np.zeros(nlev, np.int64) for k in fields}
    kc_bad = 0
    for (name, p), (kc, levels, kps, desc) in zip(pats, ref):
        # the harness must be what cv2.AKAZE runs
        ck, cd = akaze.detectAndCompute(p, None)
        cvk = [(k.pt[0], k.pt[1], k.size, k.angle, k.response, k.octave, k.class_id) for k in ck]
        cvk = [tuple(np.float32(v) if i < 5 else v for i, v in enumerate(t)) for t in cvk]
        refk = [tuple(np.float32(v) if i < 5 else v for i, v in enumerate(t)) for t in kps]
        if cvk != refk or (cd if cd is not None else np.zeros((0, desc.shape[1]), np.uint8)).tobytes() != desc.tobytes():
            harness_bad += 1
            print(f"{name}: harness keypoints differ from cv2.AKAZE ({len(refk)} vs {len(cvk)})")

        buf = np.ascontiguousarray(p, np.uint8)
        ss = lib.fpi_akaze_scale_space_new(buf.ctypes.data, w, h)
        s = ss.contents
        if s.n_levels != len(levels):
            sys.exit(f"{name}: {s.n_levels} levels, OpenCV has {len(levels)}")
        if np.float32(s.kcontrast) != kc:
            kc_bad += 1
        for i, lv in enumerate(levels):
            c = s.levels[i]
            if (c.width, c.height, c.octave, c.sublevel, c.sigma_size, c.border) != \
               (lv["w"], lv["h"], lv["octave"], lv["sublevel"], lv["sigma_size"], lv["border"]) or \
               np.float32(c.esigma) != lv["esigma"] or np.float32(c.etime) != lv["etime"]:
                param_bad += 1
                print(f"{name} level {i}: parameters differ")
            for k in fields:
                a = np.ctypeslib.as_array(getattr(c, k), (c.height, c.width))
                d = np.abs(a.astype(np.float64) - lv[k])
                worst[k][i] = max(worst[k][i], d.max())
                ndiff[k][i] += int((a.view(np.uint32) != lv[k].view(np.uint32)).sum())
        lib.fpi_akaze_scale_space_free(ss)

    print(f"{len(pats)} patches {w}x{h}, OpenCV {cv2.__version__}")
    print(f"harness vs cv2.AKAZE: {len(pats) - harness_bad}/{len(pats)} identical (keypoints + descriptors)")
    print(f"level parameters (size, sigma, time, border) differing: {param_bad}; kcontrast differing: {kc_bad}")
    print("FED steps per level:", [len(lv["tau"]) for lv in ref[0][1]])
    print("level  size     " + "".join(f"{k + ' max|d| / bits':<24}" for k in fields))
    for i, lv in enumerate(ref[0][1]):
        print(f"{i:5d}  {lv['w']:3d}x{lv['h']:<3d}  " +
              "".join(f"{worst[k][i]:<10.3g} {ndiff[k][i]:<13d}" for k in fields))
    exact = harness_bad == 0 and param_bad == 0 and kc_bad == 0 and \
        all(ndiff[k].sum() == 0 for k in ndiff)
    print("bit-identical" if exact else "NOT bit-identical")
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(main())
