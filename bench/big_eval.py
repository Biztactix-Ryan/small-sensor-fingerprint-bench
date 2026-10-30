#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fingerprint matcher benchmark for small (96x96) area sensors.

Public fingerprint images are rescaled to the resolution of the target sensor
and cut into sensor-sized patches, normalized like the libfprint elan driver
does (see public_sets.py and docs/SCALING.md).

A. Strangers vs real enrollments (optional, --own-captures): patches from
   every public image (both polarities) are scored against all captures of
   each of your own fingers; the best score is an upper bound on any template
   enrolled from them.
B. Simulated enroll/verify on the public fingers: per finger, STAGES patches
   around the finger centre (with jitter, like moving the finger between
   presses) from its first impressions form the template; patches from its
   other impressions are genuine probes; every probe is also tried against
   every other finger's template (impostor).
C. Strangers only (--strangers): sets with a single impression per finger are
   scored against every template of B.

Usage: big_eval.py --data DIR [--matcher ours] [--stages 10] [--jitter 20]
                   [--probes 2] [--own-captures DIR] [--strangers socofing,family]
Matchers are defined in matchers.py.
"""
import argparse
import os
import random
import sys
import time
import zlib
from collections import defaultdict
import multiprocessing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# one BLAS thread per worker process, like OpenCV below
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import public_sets as pub  # noqa: E402
import matchers  # noqa: E402

# one OpenCV thread per worker process: otherwise every worker spawns a thread
# per core and the machine thrashes
cv2.setNumThreads(1)
WORKERS = max(1, (os.cpu_count() or 2) - 2)


def pool():
    # workers use the matcher and templates set up in main(): they must be
    # forked (Python 3.14 defaults to forkserver on Linux)
    ctx = multiprocessing.get_context("fork")
    return ctx.Pool(WORKERS, initializer=os.nice, initargs=(10,))


def progress_map(p, fn, jobs, label, chunksize):
    out, t, step = [], time.time(), max(1, len(jobs) // 20)
    for i, r in enumerate(p.imap(fn, jobs, chunksize=chunksize), 1):
        out.append(r)
        if i % step == 0 or i == len(jobs):
            el = time.time() - t
            print(f"   {label}: {i}/{len(jobs)}  {el:.0f}s elapsed, ~{el / i * (len(jobs) - i):.0f}s left",
                  flush=True)
    return out


# worker globals, inherited through fork
G_FEATS = None
G_OURS = None
MATCH = None


def load_scaled(path, dpi):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    scale = pub.SENSOR_DPI / dpi
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def centre(img):
    """Centre of the fingerprint area (high local contrast)."""
    f = img.astype(np.float32)
    k = 31
    m = cv2.blur(f, (k, k))
    sd = np.sqrt(np.maximum(cv2.blur(f * f, (k, k)) - m * m, 0))
    ys, xs = np.where(sd > 0.5 * sd.max())
    return (float(ys.mean()), float(xs.mean())) if len(ys) else (img.shape[0] / 2, img.shape[1] / 2)


# Share of spectral energy at ridge frequencies (periods 7-16px). Our own
# captures are all >= 0.73; patches of non-ridge content (e.g. the ink discs
# stamped on MINEX cards) are ~0.2. Our sensor only ever images ridges.
RIDGE_MIN = 0.5


def ridge_ratio(p):
    c = p.astype(np.float32)
    c -= c.mean()
    s = c.shape[0]
    c *= np.outer(np.hanning(s), np.hanning(s))
    spec = np.abs(np.fft.fftshift(np.fft.fft2(c))) ** 2
    yy, xx = np.indices(spec.shape)
    r = np.hypot(yy - s // 2, xx - s // 2)
    return spec[(r >= s / 16) & (r <= s / 7)].sum() / spec[(r >= 2) & (r <= s / 2)].sum()


def patch_origin(img, cy, cx):
    h, w = img.shape
    return (int(round(min(max(cy - pub.SIZE / 2, 0), h - pub.SIZE))),
            int(round(min(max(cx - pub.SIZE / 2, 0), w - pub.SIZE))))


def patch_at(img, cy, cx):
    y, x = patch_origin(img, cy, cx)
    p = img[y:y + pub.SIZE, x:x + pub.SIZE]
    if p.std() < 10:  # mostly background
        return None
    p = pub.thirds(p)
    return p if ridge_ratio(p) >= RIDGE_MIN else None


def aligned_centre(img, ref):
    """Where the centre of @ref's fingerprint lies in @img, an impression of the
    same finger, so patches cover the same area like a user placing the finger
    the same way; None if the impressions can't be registered."""
    sift = cv2.SIFT_create()
    ka, da = sift.detectAndCompute(ref, None)
    kb, db = sift.detectAndCompute(img, None)
    if da is None or db is None or len(da) < 2 or len(db) < 2:
        return None
    good = [m[0] for m in cv2.BFMatcher().knnMatch(da, db, k=2)
            if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
    if len(good) < 8:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in good])
    dst = np.float32([kb[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=8)
    if M is None or inl.sum() < 12:
        return None
    cy, cx = centre(ref)
    x, y = M @ np.array([cx, cy, 1.0])
    if not (0 <= x < img.shape[1] and 0 <= y < img.shape[0]):
        return None
    return float(y), float(x)


def jittered(img, n, jitter, rng, at=None, offsets=None):
    """Up to @n usable patches around @at (default: the fingerprint centre).
    With a list as @offsets, appends the (y, x) offset of each patch centre
    from @at to it."""
    cy, cx = at if at else centre(img)
    out = []
    for _ in range(n * 3):
        py, px = cy + rng.gauss(0, jitter), cx + rng.gauss(0, jitter)
        p = patch_at(img, py, px)
        if p is not None:
            out.append(p)
            if offsets is not None:
                y, x = patch_origin(img, py, px)
                offsets.append((y + pub.SIZE / 2 - cy, x + pub.SIZE / 2 - cx))
        if len(out) == n:
            break
    return out


# ---- A ----------------------------------------------------------------------

def a_worker(job):
    path, dpi, seed = job
    rng = random.Random(seed)
    img = load_scaled(path, dpi)
    if img is None or min(img.shape) < pub.SIZE:
        return []
    res = []
    for p in jittered(img, 2, 30, rng):
        for pol in (p, 255 - p):
            f = MATCH.load(MATCH.features_img(pol))
            res.append([best(f, gal) for gal in G_OURS.values()])
    return res


def load_captures(directory):
    """[(finger, path)] of own captures laid out as DIR/<finger>/*.png"""
    items = []
    for finger in sorted(os.listdir(directory)):
        d = os.path.join(directory, finger)
        if os.path.isdir(d):
            items += [(finger, os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith(".png")]
    return items


def run_a(idx, dataset):
    global G_OURS
    ours = load_captures(dataset)
    G_OURS = defaultdict(list)
    for finger, path in ours:
        G_OURS[finger].append(MATCH.load(MATCH.features_img(cv2.imread(path, cv2.IMREAD_GRAYSCALE))))
    jobs = [(p, pub.SETS[s][0], i) for i, (s, f, imp, p) in enumerate(idx)]
    t = time.time()
    with pool() as p:
        rows = [r for rs in progress_map(p, a_worker, jobs, "A", 4) for r in rs]
    best = np.array(rows).ravel()
    print(f"\n=== A. strangers vs our {len(G_OURS)} enrolled fingers "
          f"({len(rows)} probe patches, {best.size} attempts, {time.time() - t:.0f}s)")
    print("score histogram:", {int(k): int(v) for k, v in zip(*np.unique(best, return_counts=True))})
    for th in MATCH.thresholds:
        n = int((best >= th).sum())
        print(f"   threshold {th:3d}: false accepts {n}/{best.size}")


# ---- B ----------------------------------------------------------------------

def feat_worker(job):
    """Features of patches from one impression; with a reference impression of
    the same finger, patches are placed where that impression's centre is.
    Patch offsets are from the centre of the first enrollment impression, in
    that impression's coordinates when registered (rotation is ignored).
    Returns (features, alignment: None | True | False, offsets)."""
    path, dpi, n, jitter, seed, ref = job
    rng = random.Random(seed)
    img = load_scaled(path, dpi)
    if img is None or min(img.shape) < pub.SIZE:
        return [], None, []
    at = aligned = None
    if ref:
        at = aligned_centre(img, load_scaled(*ref))
        aligned = at is not None
    off = []
    return [MATCH.features_img(p) for p in jittered(img, n, jitter, rng, at, off)], aligned, off


def best(f, gallery):
    """Score of one probe against one finger's enrolled images."""
    if hasattr(MATCH, "score_set"):
        return MATCH.score_set(f, gallery)
    return max(MATCH.score(f, g) for g in gallery)


def b_worker(probe):
    """Best score of one probe against every template."""
    f = G_FEATS["probes"][probe]
    return [best(f, tmpl) for tmpl in G_FEATS["templates"]]


def run_b(idx, stages, jitter, nprobes):
    global G_FEATS
    by_finger = defaultdict(list)
    for s, f, imp, p in idx:
        by_finger[f].append((imp, p, pub.SETS[s][0]))

    # template from the first half of the impressions, probes from the rest
    tjobs, pjobs, owners = [], [], []
    names = sorted(by_finger)
    for k, f in enumerate(names):
        imps = sorted(by_finger[f])
        half = max(1, len(imps) // 2)
        enroll, probe = imps[:half], imps[half:]
        per = -(-stages // len(enroll))
        ref = (enroll[0][1], enroll[0][2])
        tjobs.append([(p, dpi, per, jitter, zlib.crc32(f"{f}/{i}".encode()), ref if i else None)
                      for i, (_, p, dpi) in enumerate(enroll)])
        for i, (_, p, dpi) in enumerate(probe):
            pjobs.append((p, dpi, nprobes, jitter, zlib.crc32(f"{f}/p{i}".encode()), ref))
            owners.append(k)

    t = time.time()
    with pool() as p:
        flat = progress_map(p, feat_worker, [j for js in tjobs for j in js], "template features", 8)
        probes_nested = progress_map(p, feat_worker, pjobs, "probe features", 8)
    templates, toff, pos = [], [], 0
    for js in tjobs:
        feats = [x for r, _, _ in flat[pos:pos + len(js)] for x in r][:stages]
        toff.append([o for _, _, off in flat[pos:pos + len(js)] for o in off][:stages])
        pos += len(js)
        templates.append(feats)
    probes, powner, paligned, poff = [], [], [], []
    for k, (r, aligned, off) in zip(owners, probes_nested):
        for x, o in zip(r, off):
            probes.append(x)
            powner.append(k)
            paligned.append(bool(aligned))
            poff.append(o)
    al = [a for _, a, _ in flat + probes_nested if a is not None]
    print(f"   impressions registered to the enrollment impression: {sum(al)}/{len(al)}")
    keep = [i for i, tm in enumerate(templates) if len(tm) == stages]
    print(f"\n=== B. simulated enroll/verify: {len(keep)} public fingers, {stages} stages, "
          f"jitter {jitter}px, {len(probes)} probes (features {time.time() - t:.0f}s)")

    G_FEATS = {"templates": [[MATCH.load(x) for x in templates[i]] for i in keep],
               "probes": [MATCH.load(x) for x in probes]}
    ident = [pub.identity(names[i]) for i in keep]
    setname = [names[i].split("/")[0] for i in keep]
    col = {k: j for j, k in enumerate(keep)}
    t = time.time()
    with pool() as p:
        M = np.array(progress_map(p, b_worker, range(len(probes)), "cross-match", 4))
    print(f"   {M.size} probe x template comparisons in {time.time() - t:.0f}s")

    np.savez_compressed(os.path.join(OUT_DIR, f"big_eval_b_{MATCHER_NAME}{RUN_SUFFIX}.npz"), M=M, powner=powner,
                        paligned=paligned, keep=keep, names=names, setname=setname, ident=ident,
                        poff=np.float32(poff).reshape(-1, 2),
                        toff=np.float32([toff[i] for i in keep]).reshape(len(keep), stages, 2))

    gen, gen_al, imp, worst, same = [], [], [], [], []
    for pi, k in enumerate(powner):
        if k not in col:
            continue
        own = col[k]
        for j in range(M.shape[1]):
            if j == own:
                gen.append(M[pi, j])
                gen_al.append(paligned[pi])
            elif ident[j] == ident[own]:
                # same physical finger in a sister dataset (e.g. FVC DB1 vs DB2)
                same.append(int(M[pi, j]))
            else:
                imp.append(M[pi, j])
                if M[pi, j] >= MATCH.thresholds[1]:
                    worst.append((int(M[pi, j]), setname[own], names[k], names[keep[j]]))
    gen, gen_al, imp = np.array(gen), np.array(gen_al), np.array(imp)
    print(f"   genuine attempts {gen.size} ({gen_al.sum()} registered), impostor attempts {imp.size}")
    print("   threshold  false-reject% (registered / all)  false-accepts")
    for th in MATCH.thresholds:
        print(f"   {th:9d}  {100 * (gen[gen_al] < th).mean():8.1f} / {100 * (gen < th).mean():5.1f}"
              f"             {int((imp >= th).sum())}/{imp.size}")
    if same:
        same = np.array(same)
        print(f"   same finger number in sister datasets (excluded from impostors): {same.size} attempts, "
              f"{int((same >= MATCH.default).sum())} score >= {MATCH.default}, max {same.max()}")
    print("   impostor score histogram:",
          {int(k): int(v) for k, v in zip(*np.unique(imp, return_counts=True))})
    print(f"   genuine false-reject% by set at threshold {MATCH.default}:")
    for s in sorted(set(setname)):
        sel = [(M[pi, col[k]], paligned[pi]) for pi, k in enumerate(powner)
               if k in col and setname[col[k]] == s]
        if sel:
            sc = np.array([x for x, _ in sel])
            ra = np.array([a for _, a in sel])
            reg = f"{100 * (sc[ra] < MATCH.default).mean():5.1f}%" if ra.any() else "   n/a"
            print(f"      {s:18s} registered {reg} (n={ra.sum()})  all {100 * (sc < MATCH.default).mean():5.1f}% "
                  f"(n={sc.size}){'  synthetic' if pub.SETS[s][1] else ''}")
    if worst:
        print("   highest impostor scores:")
        for w in sorted(worst, reverse=True)[:10]:
            print("     ", w)
    return [names[i] for i in keep]


# ---- C ----------------------------------------------------------------------

def c_worker(job):
    """Best score of each probe patch of one stranger image against every
    template of part B."""
    path, dpi, n, seed = job
    img = load_scaled(path, dpi)
    if img is None or min(img.shape) < pub.SIZE:
        return []
    rng = random.Random(seed)
    return [[best(f, tmpl) for tmpl in G_FEATS["templates"]]
            for f in (MATCH.load(MATCH.features_img(p)) for p in jittered(img, n, 20, rng))]


def run_c(setname, nprobes, tnames):
    dpi = pub.STRANGER_SETS[setname][0]
    items = pub.strangers(setname)
    jobs = [(p, dpi, nprobes, zlib.crc32(f.encode())) for f, p in items]
    t = time.time()
    with pool() as p:
        rows = [r for rs in progress_map(p, c_worker, jobs, f"C {setname}", 8) for r in rs]
    M = np.array(rows)
    print(f"\n=== C. {len(items)} {setname} strangers ({dpi} dpi, {len(rows)} probe patches) vs the "
          f"{M.shape[1]} templates of B: {M.size} attempts in {time.time() - t:.0f}s")
    print("score histogram:", {int(k): int(v) for k, v in zip(*np.unique(M, return_counts=True))})
    for th in MATCH.thresholds:
        print(f"   threshold {th:4d}: false accepts {int((M >= th).sum())}/{M.size}")
    np.savez_compressed(os.path.join(OUT_DIR, f"big_eval_c_{setname}_{MATCHER_NAME}{RUN_SUFFIX}.npz"),
                        M=M, templates=tnames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matcher", default="ours", choices=sorted(matchers.MATCHERS))
    ap.add_argument("--stages", type=int, default=10)
    ap.add_argument("--jitter", type=float, default=20, help="patch position spread, px at sensor dpi")
    ap.add_argument("--probes", type=int, default=2, help="probe patches per probe impression")
    ap.add_argument("--skip-a", action="store_true")
    ap.add_argument("--skip-b", action="store_true")
    ap.add_argument("--sets", help="comma-separated subset of public sets")
    ap.add_argument("--tag", help="suffix for the result files, e.g. a dataset version")
    ap.add_argument("--strangers", help="comma-separated stranger-only sets for part C, "
                    f"from {sorted(pub.STRANGER_SETS)}")
    ap.add_argument("--data", required=True, help="directory with the public datasets, see docs/DATASETS.md")
    ap.add_argument("--own-captures", help="DIR/<finger>/*.png captures of your own sensor for part A")
    ap.add_argument("--out", default=".", help="directory for the score matrices")
    a = ap.parse_args()
    global MATCH, MATCHER_NAME, RUN_SUFFIX, OUT_DIR
    pub.ROOT = a.data
    OUT_DIR = a.out
    os.makedirs(OUT_DIR, exist_ok=True)
    MATCH, MATCHER_NAME = matchers.get(a.matcher), a.matcher
    # runs on a subset of the sets must not overwrite the results of full runs
    RUN_SUFFIX = ("_" + a.sets.replace(",", "+") if a.sets else "") + (f"_{a.tag}" if a.tag else "")
    print(f"matcher: {a.matcher}")
    idx = pub.index()
    if a.sets:
        idx = [x for x in idx if x[0] in a.sets.split(",")]
    print(f"{len(idx)} public images, {len({f for _, f, _, _ in idx})} fingers, "
          f"sensor {pub.SENSOR_DPI} dpi")
    if not a.skip_a and a.own_captures:
        run_a(idx, a.own_captures)
    if not a.skip_b:
        tnames = run_b(idx, a.stages, a.jitter, a.probes)
        for s in (a.strangers.split(",") if a.strangers else []):
            run_c(s, a.probes, tnames)


if __name__ == "__main__":
    main()
