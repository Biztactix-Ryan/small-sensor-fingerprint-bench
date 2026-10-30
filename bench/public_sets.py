#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Index of the public fingerprint datasets and helpers to turn them into
patches that look like captures from a 96x96 sensor.

Run directly to print the index summary and calibrate a sensor's resolution
against the 500dpi sets (ridge period from the FFT spectrum):
    public_sets.py --data DIR [--captures DIR]   (captures as DIR/<finger>/*.png)
See docs/SCALING.md.
"""
import glob
import os
import re
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# set by big_eval.py --data, or FPBENCH_DATA
ROOT = os.environ.get("FPBENCH_DATA", os.path.join(HERE, "..", "data"))
SIZE = 96

# set name -> (dpi, synthetic)
SETS = {
    "fvc2000_DB1_B": (500, False), "fvc2000_DB2_B": (500, False),
    "fvc2000_DB3_B": (500, False), "fvc2000_DB4_B": (500, True),
    "fvc2002_DB1_B": (500, False), "fvc2002_DB2_B": (569, False),
    "fvc2002_DB3_B": (500, False), "fvc2002_DB4_B": (500, True),
    "fvc2004_DB1_B": (500, False), "fvc2004_DB2_B": (512, False),
    "fvc2004_DB3_B": (512, False), "fvc2004_DB4_B": (500, True),
    "neuro_crossmatch": (500, False), "neuro_uareu": (512, False),
    # fvs: undocumented, measured from its ridge period
    "fvs": (394, False), "minex": (500, False),
    # Tsinghua Distorted: normal + deliberately distorted impression per
    # finger; measured from its ridge period (8.84px)
    "tsinghua": (449, False),
}

# one impression per finger, so only usable as strangers (big_eval part C);
# measured from its ridge period (3.2px), the declared 500dpi is wrong
# family: inked scans of 5 fingers of father, mother and child of 100
# families. Its blotchy ink defeats ridge_period(); ~7.5px ridges counted by
# hand in native crops. Faint scans are dropped by the patch filters.
STRANGER_SETS = {"socofing": (162, False), "family": (380, False)}


def strangers(name):
    """[(finger_id, path)] of a stranger-only set."""
    if name == "socofing":
        d = os.path.join(ROOT, "SOCOFing", "SOCOFing", "Real")
        return sorted((f"socofing/{os.path.splitext(os.path.basename(p))[0]}", p)
                      for p in glob.glob(os.path.join(d, "*.BMP")))
    if name == "family":
        return sorted((f"family/{os.path.splitext(os.path.basename(p))[0]}", p)
                      for p in glob.glob(os.path.join(ROOT, "family", "**", "*.png"), recursive=True))
    raise KeyError(name)


def index():
    """Returns [(set, finger_id, impression, path)]; finger_id is unique across sets."""
    out = []
    for name in SETS:
        d = os.path.join(ROOT, name)
        if not os.path.isdir(d):
            continue
        if name == "tsinghua":
            for p in glob.glob(os.path.join(d, "*", "*", "*.png")):
                finger = os.path.basename(os.path.dirname(p))
                out.append((name, f"{name}/{finger}", os.path.splitext(os.path.basename(p))[0], p))
            continue
        if name == "minex":
            for p in glob.glob(os.path.join(d, "png", "*.png")):
                m = re.fullmatch(r"([ab])(\d+)_(\d+)\.png", os.path.basename(p))
                if m:
                    out.append((name, f"{name}/{m[2]}_{m[3]}", m[1], p))
            continue
        for p in glob.glob(os.path.join(d, "**", "*.*"), recursive=True):
            b = os.path.basename(p)
            m = re.fullmatch(r"(\d+)_(\d+)_(\d+)\.tif", b) or re.fullmatch(r"(\d+)_(\d+)\.(?:tif|bmp)", b)
            if not m:
                continue
            if m.lastindex == 3:
                out.append((name, f"{name}/{m[1]}_{m[2]}", m[3], p))
            else:
                out.append((name, f"{name}/{m[1]}", m[2], p))
    return sorted(out)


# Resolution the public images are rescaled to: that of the target sensor.
# Elan 04f3:0c3d (96x96): ridge period 10.67px in its captures vs 9.85px in
# the 500dpi sets => 542 dpi. Measure yours with --captures, then set
# FPBENCH_SENSOR_DPI.
SENSOR_DPI = int(os.environ.get("FPBENCH_SENSOR_DPI", "542"))


def identity(finger_id):
    """Fingers that are (or may be) the same physical finger across sets. The
    two Neurotechnology samples share subject_finger names (same people, two
    sensors), so treat them as one identity."""
    finger_id = re.sub(r"^neuro_(?:crossmatch|uareu)/", "neuro/", finger_id)
    # FVC2000 DB1 and DB2 share volunteers and finger numbering: e.g. 107 is
    # visibly the same finger on both sensors, and same-numbered pairs score up
    # to 14 where strangers never exceed 8. Other FVC DB pairs score like
    # strangers (max 5), so they stay separate identities.
    return re.sub(r"^fvc2000_DB[12]_B/", "fvc2000_DB12/", finger_id)


def ridge_period(img):
    """Dominant ridge period in pixels, from the radial peak of the spectrum
    of the highest-contrast central region."""
    f = img.astype(np.float32)
    h, w = f.shape
    s = min(h, w, 256)
    best = None
    for y in range(0, h - s + 1, max(1, (h - s) // 4 or 1)):
        for x in range(0, w - s + 1, max(1, (w - s) // 4 or 1)):
            c = f[y:y + s, x:x + s]
            if best is None or c.std() > best.std():
                best = c
    c = best - best.mean()
    c *= np.outer(np.hanning(s), np.hanning(s))
    spec = np.abs(np.fft.fftshift(np.fft.fft2(c))) ** 2
    yy, xx = np.indices(spec.shape)
    r = np.hypot(yy - s // 2, xx - s // 2).astype(int)
    radial = np.bincount(r.ravel(), spec.ravel()) / np.maximum(np.bincount(r.ravel()), 1)
    lo, hi = int(s / 20), int(s / 4)  # periods between 4 and 20 px
    k = lo + int(np.argmax(radial[lo:hi]))
    return s / k


def thirds(p):
    """The elan driver's 3-segment percentile normalization."""
    lv = np.percentile(p, [0, 30, 65, 100])
    return np.interp(p, lv, [0, 99, 155, 255]).astype(np.uint8)


def patches(path, scale, n, rng):
    """Up to @n foreground patches of SIZExSIZE after rescaling by @scale."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
    if abs(scale - 1) > 0.01:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = img.shape
    if h < SIZE or w < SIZE:
        return []
    f = img.astype(np.float32)
    mean = cv2.blur(f, (SIZE, SIZE))
    std = np.sqrt(np.maximum(cv2.blur(f * f, (SIZE, SIZE)) - mean * mean, 0))
    half = SIZE // 2
    ys, xs = np.where(std[half:h - half, half:w - half] > 0.8 * std.max())
    out = []
    for k in rng.sample(range(len(ys)), min(n, len(ys))):
        y, x = ys[k], xs[k]
        out.append(thirds(img[y:y + SIZE, x:x + SIZE]))
    return out


def main():
    import argparse
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=ROOT, help="directory with the public datasets")
    ap.add_argument("--captures", help="DIR/<finger>/*.png captures of your sensor to calibrate")
    a = ap.parse_args()
    ROOT = a.data
    idx = index()
    by_set = {}
    for s, f, i, p in idx:
        by_set.setdefault(s, set()).add(f)
    total = 0
    for s in SETS:
        if s in by_set:
            n = sum(1 for x in idx if x[0] == s)
            print(f"{s:18s} {len(by_set[s]):4d} fingers {n:5d} images  dpi {SETS[s][0]}"
                  f"{'  synthetic' if SETS[s][1] else ''}")
            total += len(by_set[s])
    print(f"total {total} fingers")

    ref = [ridge_period(cv2.imread(p, cv2.IMREAD_GRAYSCALE))
           for s, f, i, p in idx if SETS[s][0] == 500 and not SETS[s][1]][::4]
    pr = float(np.median(ref))
    print(f"ridge period of the 500dpi sets: {pr:.2f}px (n={len(ref)})")
    if a.captures:
        ours = [ridge_period(cv2.imread(p, cv2.IMREAD_GRAYSCALE))
                for p in glob.glob(os.path.join(a.captures, "*", "*.png"))]
        po = float(np.median(ours))
        print(f"ridge period of your captures: {po:.2f}px (n={len(ours)})")
        print(f"=> your sensor is about {500 * po / pr:.0f} dpi (set FPBENCH_SENSOR_DPI)")
    fvs = [ridge_period(cv2.imread(p, cv2.IMREAD_GRAYSCALE)) for s, f, i, p in idx if s == "fvs"]
    if fvs:
        print(f"fvs ridge period {np.median(fvs):.2f}px => about {500 * np.median(fvs) / pr:.0f} dpi")


if __name__ == "__main__":
    main()
