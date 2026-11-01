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
S. Synthetic probes (--synthetic, synthetic.py): blank, noise, gratings,
   checkerboards, inverted/mirrored enrolled patches and the adversarial
   frames, scored against every template of B like C strangers (same
   features, caps and C timing); big_eval_s_<matcher>.npz keeps the matrix
   and, per probe, its kind, max score and best template. The fixed-pattern
   pairs of synthetic.pairs() need templates of their own and are not run.

Per-stage store (B and C): for the stage counts in --derive below --stages,
the score against every enrolled image of every template a direct run at that
stage count would use, for each probe x template pair whose best stage score
is >= --floor; derive_stages.py turns it into the score matrices of those
runs, exact at and above the floor (not for matchers with score_set()).

Usage: big_eval.py --data DIR [--matcher ours] [--stages 10] [--jitter 20]
                   [--probes 2] [--own-captures DIR] [--strangers socofing,family]
                   [--derive 5,10,15] [--floor N] [--synthetic]
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
import derive_stages  # noqa: E402

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


def same_place(a, b):
    """Whether @a and @b correlate (NCC > 0.5) over the area where both show
    a finger (high local contrast): the same finger placed the same way."""
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:h, :w].astype(np.float32), b[:h, :w].astype(np.float32)
    mask = np.ones((h, w), bool)
    for f in (a, b):
        m = cv2.blur(f, (15, 15))
        mask &= np.sqrt(np.maximum(cv2.blur(f * f, (15, 15)) - m * m, 0)) > 12
    return mask.sum() >= 500 and np.corrcoef(a[mask], b[mask])[0, 1] > 0.5


def aligned_centre(img, ref):
    """Where the centre of @ref's fingerprint lies in @img, an impression of the
    same finger, so patches cover the same area like a user placing the finger
    the same way; None if the impressions can't be registered.
    CLAHE evens out contrast between devices (NIST SD 302: 74.6% -> 85.0% of
    impressions registered). Both impressions are at sensor dpi, so a fit
    with a scale far from 1 or a large rotation is a false registration, and
    so is the identity: keypoints on the sensor's fixed pattern rather than
    on the finger (35 of 60 fits on FVC2004 DB2 before this check), unless
    the finger really is in the same place (most such fits on UNSW 2D)."""
    sift = cv2.SIFT_create()
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    ka, da = sift.detectAndCompute(clahe.apply(ref), None)
    kb, db = sift.detectAndCompute(clahe.apply(img), None)
    if da is None or db is None or len(da) < 2 or len(db) < 2:
        return None
    good = [m[0] for m in cv2.BFMatcher().knnMatch(da, db, k=2)
            if len(m) == 2 and m[0].distance < 0.8 * m[1].distance]
    if len(good) < 8:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in good])
    dst = np.float32([kb[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=8)
    if M is None or inl.sum() < 12:
        return None
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    angle = abs(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    if not 0.85 <= scale <= 1.15 or angle > 45:
        return None
    if np.hypot(M[0, 2], M[1, 2]) < 2 and angle < 0.5 and not same_place(img, ref):
        return None
    cy, cx = centre(ref)
    x, y = M @ np.array([cx, cy, 1.0])
    if not (0 <= x < img.shape[1] and 0 <= y < img.shape[0]):
        return None
    return float(y), float(x)


def jittered(img, n, jitter, rng, at=None, offsets=None, attempts=None):
    """Up to @n usable patches around @at (default: the fingerprint centre).
    With a list as @offsets, appends the (y, x) offset of each patch centre
    from @at to it; with a list as @attempts, the attempt each patch came
    from. The patches for a smaller @n are the first ones of a larger @n that
    came from attempts < 3 @n (see derive_stages.subset())."""
    cy, cx = at if at else centre(img)
    out = []
    for t in range(n * 3):
        py, px = cy + rng.gauss(0, jitter), cx + rng.gauss(0, jitter)
        p = patch_at(img, py, px)
        if p is not None:
            out.append(p)
            if offsets is not None:
                y, x = patch_origin(img, py, px)
                offsets.append((y + pub.SIZE / 2 - cy, x + pub.SIZE / 2 - cx))
            if attempts is not None:
                attempts.append(t)
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
    Returns (features, alignment: None | True | False, offsets, attempts)."""
    patches, aligned, off, att = job_patches(job)
    return [MATCH.features_img(p) for p in patches], aligned, off, att


def job_patches(job):
    """The patches feat_worker() takes the features of, with (alignment,
    offsets, attempts)."""
    path, dpi, n, jitter, seed, ref = job
    rng = random.Random(seed)
    img = load_scaled(path, dpi)
    if img is None or min(img.shape) < pub.SIZE:
        return [], None, [], []
    at = aligned = None
    if ref:
        at = aligned_centre(img, load_scaled(*ref))
        aligned = at is not None
    off, att = [], []
    return jittered(img, n, jitter, rng, at, off, att), aligned, off, att


def best(f, gallery):
    """Score of one probe against one finger's enrolled images."""
    if hasattr(MATCH, "score_set"):
        return MATCH.score_set(f, gallery)
    return max(MATCH.score(f, g) for g in gallery)


# Per-pair time (matchers with c_timed, see matchers.py): every probe x
# enrolled image match that M covers (the templates of this run, their first
# --stages images), timed in C. Kept per run: pt_hist, the count of matches
# by [own template (0) or another (1), keypoints, time], keypoints in bins of
# KP_BIN of the larger count of the two images, time in HIST_PER_OCTAVE log2
# bins of nanoseconds (bin b: [2^(b/8), 2^((b+1)/8)) ns); the time of each
# probe's whole row of M and against its own template; and the SLOWEST
# slowest image pairs. With score_set() (union) the unit is a probe x
# template instead of an image, and only the probe's keypoints count. Pairs
# that never reach C (an empty print: score() returns 0 without matching,
# as libfprint has no print to match) are not timed, only counted per probe
# (pt_untimed).
HIST_PER_OCTAVE = 8
HIST_BINS = 40 * HIST_PER_OCTAVE
KP_BIN = 16
KP_BINS = 256
TOP_PER_PROBE = 5
SLOWEST = 100


class PairTimes:
    """Times of one probe's matches, from the C time in matchers.PAIR_NS."""

    def __init__(self, own):
        self.own = own
        self.ns, self.who = [], []
        self.untimed = 0

    def score(self, f, g, col, k, c, gkp):
        t, calls = matchers.PAIR_NS, matchers.PAIR_CALLS
        s = MATCH.score(f, g) if c >= 0 else MATCH.score_set(f, g)
        if col >= 0 and MATCH.c_timed:
            if matchers.PAIR_CALLS == calls:
                self.untimed += 1
            else:
                self.ns.append(matchers.PAIR_NS - t)
                self.who.append((col, k, c, gkp, s))
        return s

    def summary(self, kp):
        """(probe keypoints, None or (pt_hist flat indices and counts, row
        ns, own template ns, slowest (ns, template, image, its keypoints,
        score), untimed pairs))"""
        if not MATCH.c_timed:
            return kp, None
        ns = np.int64(self.ns)
        own = np.int64([w[0] == self.own for w in self.who]) if self.who else np.zeros(0, np.int64)
        b = np.clip(np.floor(HIST_PER_OCTAVE * np.log2(np.maximum(ns, 1))), 0, HIST_BINS - 1).astype(np.int64)
        kb = np.minimum(np.maximum(kp, np.int64([w[3] for w in self.who])) // KP_BIN, KP_BINS - 1) \
            if self.who else np.zeros(0, np.int64)
        # sparse: a few distinct bins per probe
        hist = np.unique(((1 - own) * KP_BINS + kb) * HIST_BINS + b, return_counts=True)
        top = np.argsort(-ns, kind="stable")[:TOP_PER_PROBE]
        slow = np.int64([(ns[i], *self.who[i][1:]) for i in top]).reshape(-1, 5)
        return kp, (hist, int(ns.sum()), int(ns[own > 0].sum()) if own.any() else -1, slow, self.untimed)


def stage_scores(f, own=-1):
    """Scores of one probe against every template, and its PairTimes
    summary (@own: its template's column). Without the per-stage store: the
    best score per template of part B. With it, (best per template of part
    B; best over the stages of every other stored template; the stored
    template indices with any stage score >= the floor; their stage scores,
    concatenated)."""
    pt = PairTimes(own)
    st = G_FEATS.get("stage")
    if st is None:
        if hasattr(MATCH, "score_set"):
            row = [pt.score(f, tmpl, j, k, -1, -1) for j, (tmpl, k) in enumerate(zip(G_FEATS["templates"],
                                                                                   G_FEATS["tid"]))]
        else:
            row = [max(pt.score(f, g, j, k, c, gkp) for c, (g, gkp) in enumerate(zip(tmpl, kps)))
                   for j, (tmpl, k, kps) in enumerate(zip(G_FEATS["templates"], G_FEATS["tid"],
                                                          G_FEATS["tkp"]))]
        return row, pt.summary(MATCH.n_keypoints(f))
    floor, n = st["floor"], st["stages"]
    row, xbest, pairs, scores = [0] * len(G_FEATS["templates"]), [], [], []
    for t, (gal, col, k, cs, kps) in enumerate(zip(st["galleries"], st["col"], st["tid"], st["cand"], st["kp"])):
        # timed: the images M covers
        s = [pt.score(f, g, col if i < n else -1, k, c, gkp) for i, (g, c, gkp) in enumerate(zip(gal, cs, kps))]
        top = max(s)
        if col >= 0:
            row[col] = max(s[:n])
        else:
            xbest.append(top)
        if top >= floor:
            pairs.append(t)
            scores += s
    # arrays: a list of ints per probe takes several times the memory on the full run
    return (np.int64(row), np.int64(xbest), np.int32(pairs), np.int64(scores)), pt.summary(MATCH.n_keypoints(f))


def b_worker(probe):
    return stage_scores(G_FEATS["probes"][probe], G_FEATS["pcol"][probe])


def stage_matrix(res, nprobes):
    """M, the per-stage store and the per-pair times (npz fields) from
    stage_scores() rows."""
    times = pair_times([t for _, t in res])
    res = [r for r, _ in res]
    if G_FEATS.get("stage") is None:
        return np.array(res), times
    nt, nx = len(G_FEATS["templates"]), sum(c < 0 for c in G_FEATS["stage"]["col"])
    cat = (lambda i, dt: np.concatenate([r[i] for r in res]) if res else np.zeros(0, dt))
    return (cat(0, np.int64).reshape(nprobes, nt),
            dict(ps_floor=G_FEATS["stage"]["floor"], ps_xbest=cat(1, np.int64).reshape(nprobes, nx),
                 ps_probe=np.int32(np.repeat(np.arange(nprobes), [r[2].size for r in res])),
                 ps_pair=cat(2, np.int32), ps_score=cat(3, np.int64), **times))


def pair_times(rows):
    """npz fields from the PairTimes summaries of every probe: pkp (probe
    keypoints) and, for C matchers, the pt_* timing fields."""
    out = dict(pkp=np.int32([kp for kp, _ in rows]))
    timed = [t for _, t in rows if t is not None]
    if not timed or len(timed) != len(rows):
        return out
    hist = np.zeros(2 * KP_BINS * HIST_BINS, np.int64)
    for t in timed:
        hist[t[0][0]] += t[0][1]
    slow = np.int64([(p, *x) for p, t in enumerate(timed) for x in t[3]]).reshape(-1, 6)
    slow = slow[np.lexsort((slow[:, 0], -slow[:, 1]))][:SLOWEST]
    names = G_FEATS["names"]
    out.update(pt_unit="template" if hasattr(MATCH, "score_set") else "image",
               pt_hist=hist.reshape(2, KP_BINS, HIST_BINS), pt_hist_per_octave=HIST_PER_OCTAVE,
               pt_kp_bin=KP_BIN,
               pt_row_ns=np.int64([t[1] for t in timed]), pt_own_ns=np.int64([t[2] for t in timed]),
               pt_untimed=np.int32([t[4] for t in timed]),
               # probe, template (index into B's names), image of it (index
               # into its candidates, ps_cand; -1 for a whole template),
               # ns, image keypoints, score; probe keypoints are in pkp
               pt_slow=np.int64(slow[:, [0, 2, 3, 1, 4, 5]]),
               pt_slow_tname=np.array([names[k] for k in slow[:, 2]], dtype=str))
    return out


def pt_report(d):
    """Lines summarizing the pair_times() fields @d."""
    if "pt_hist" not in d:
        return [f"   keypoints per probe image: median {np.median(d['pkp']):.0f}, "
                f"min {d['pkp'].min()}, max {d['pkp'].max()}; no C timing for {MATCHER_NAME}"]
    out = [f"   keypoints per probe image: median {np.median(d['pkp']):.0f}, "
           f"min {d['pkp'].min()}, max {d['pkp'].max()}"]
    for label, h in (("own template", d["pt_hist"][0].sum(0)), ("other templates", d["pt_hist"][1].sum(0))):
        if h.sum():
            out.append(f"   C match time per probe x {d['pt_unit']}, {label}: {int(h.sum())} matches, " +
                       ", ".join(f"p{p:g} {hist_quantile(h, p / 100) / 1e3:.1f}" for p in (50, 90, 99, 99.9)) +
                       " us (+-5%)")
    if "pt_untimed" in d and d["pt_untimed"].sum():
        out.append(f"   not timed (empty print, no C match): {int(d['pt_untimed'].sum())} pairs of "
                   f"{int((d['pt_untimed'] > 0).sum())} probes")
    for (p, _, c, ns, gkp, sc), tname in list(zip(d["pt_slow"], d["pt_slow_tname"]))[:3]:
        out.append(f"      slowest: {ns / 1e3:.0f} us, probe {p} ({d['pkp'][p]} kp) vs {tname} "
                   f"image {c} ({gkp} kp), score {sc}")
    return out


def hist_quantile(h, q):
    """The @q quantile of pt_hist summed over keypoints, in ns, at its log
    bin's centre."""
    i = int(np.searchsorted(np.cumsum(h), q * h.sum()))
    return 2 ** ((i + 0.5) / HIST_PER_OCTAVE)


def run_b(idx, stages, jitter, nprobes, derive=(), floor=None):
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
    # every patch of the enrollment impressions, in order: (impression, rank
    # in it, attempt, features, offset); the template is the first STAGES
    cands, pos = [], 0
    for js in tjobs:
        cands.append([(i, j, a, x, o) for i, (r, _, off, att) in enumerate(flat[pos:pos + len(js)])
                      for j, (x, o, a) in enumerate(zip(r, off, att))])
        pos += len(js)
    templates = [[c[3] for c in cs[:stages]] for cs in cands]
    toff = [[c[4] for c in cs[:stages]] for cs in cands]
    probes, powner, paligned, poff = [], [], [], []
    for k, (r, aligned, off, _) in zip(owners, probes_nested):
        for x, o in zip(r, off):
            probes.append(x)
            powner.append(k)
            paligned.append(bool(aligned))
            poff.append(o)
    al = [a for _, a, _, _ in flat + probes_nested if a is not None]
    print(f"   impressions registered to the enrollment impression: {sum(al)}/{len(al)}")
    keep = [i for i, tm in enumerate(templates) if len(tm) == stages]
    print(f"\n=== B. simulated enroll/verify: {len(keep)} public fingers, {stages} stages, "
          f"jitter {jitter}px, {len(probes)} probes (features {time.time() - t:.0f}s)")

    G_FEATS = {"templates": [[MATCH.load(x) for x in templates[i]] for i in keep],
               "probes": [MATCH.load(x) for x in probes], "names": names, "tid": keep}
    G_FEATS["tkp"] = [[MATCH.n_keypoints(g) for g in tm] for tm in G_FEATS["templates"]]
    col = {k: j for j, k in enumerate(keep)}
    G_FEATS["pcol"] = [col.get(k, -1) for k in powner]
    # the first enrollment impression's job per template, for run_s()
    G_FEATS["tjob0"] = [tjobs[i][0] for i in keep]
    store = {}
    if derive:
        # per-stage store: the stages of every template a direct run at a
        # stage count in DERIVE would use (derive_stages.py), the template of
        # this run first
        st_t, st_cols = [], []
        for k, cs in enumerate(cands):
            imp_, rank, att = ([c[n] for c in cs] for n in range(3))
            use = set(range(stages)) if k in col else set()
            for n in derive:
                use.update(derive_stages.subset(imp_, rank, att, len(tjobs[k]), n) or ())
            if use:
                st_t.append(k)
                st_cols.append(sorted(use))
        G_FEATS["stage"] = {"floor": floor, "stages": stages, "col": [col.get(k, -1) for k in st_t],
                            "galleries": [[MATCH.load(cands[k][c][3]) for c in cs]
                                          for k, cs in zip(st_t, st_cols)],
                            "tid": st_t, "cand": st_cols}
        G_FEATS["stage"]["kp"] = [[MATCH.n_keypoints(g) for g in gal] for gal in G_FEATS["stage"]["galleries"]]
        sc = [cands[k][c] for k, cs in zip(st_t, st_cols) for c in cs]
        store = dict(ps_stages=stages, ps_derive=np.int32(derive), ps_tmpl=np.int32(st_t),
                     ps_nimp=np.int32([len(tjobs[k]) for k in st_t]),
                     ps_ptr=np.int64(np.cumsum([0] + [len(cs) for cs in st_cols])),
                     ps_cand=np.int32([c for cs in st_cols for c in cs]),
                     ps_imp=np.int32([c[0] for c in sc]), ps_rank=np.int32([c[1] for c in sc]),
                     ps_att=np.int32([c[2] for c in sc]),
                     ps_bytes=np.float64([MATCH.stored_bytes(c[3]) for c in sc]),
                     ps_off=np.float32([c[4] for c in sc]).reshape(-1, 2),
                     ps_kp=np.int32([x for kps in G_FEATS["stage"]["kp"] for x in kps]))
        print(f"   per-stage store: {len(st_t)} templates ({len(st_t) - len(keep)} only for derived stage "
              f"counts {list(derive)}), {len(sc)} stages, floor {floor}")
    ident = [pub.identity(names[i]) for i in keep]
    setname = [names[i].split("/")[0] for i in keep]
    tperson = [pub.person(names[i]) for i in keep]
    t = time.time()
    with pool() as p:
        M, sparse = stage_matrix(progress_map(p, b_worker, range(len(probes)), "cross-match", 4), len(probes))
    print(f"   {M.size} probe x template comparisons in {time.time() - t:.0f}s")
    if "ps_pair" in sparse:
        print(f"   per-stage scores stored for {sparse['ps_pair'].size} probe x template pairs "
              f"({sparse['ps_score'].size} scores)")
    print("\n".join(pt_report(sparse)))

    np.savez_compressed(os.path.join(OUT_DIR, f"big_eval_b_{MATCHER_NAME}{RUN_SUFFIX}.npz"), M=M, powner=powner,
                        paligned=paligned, keep=keep, names=names, setname=setname, ident=ident,
                        split=[pub.split(names[i]) for i in keep], person=tperson,
                        tbytes=np.float64([np.mean([MATCH.stored_bytes(x) for x in templates[i]]) for i in keep]),
                        poff=np.float32(poff).reshape(-1, 2),
                        toff=np.float32([toff[i] for i in keep]).reshape(len(keep), stages, 2),
                        tkp=np.int32(G_FEATS["tkp"]).reshape(len(keep), stages), **store, **sparse)

    gen, gen_al, imp, worst, same, sp = [], [], [], [], [], []
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
                if tperson[own] and tperson[j] == tperson[own]:
                    sp.append(int(M[pi, j]))
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
    if sp:
        sp = np.array(sp)
        print(f"   same person, other finger (kept in impostors): {sp.size} attempts, "
              f"{int((sp >= MATCH.default).sum())} score >= {MATCH.default}, max {sp.max()}")
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
    """stage_scores() of each probe patch of one stranger image."""
    path, dpi, n, seed = job
    img = load_scaled(path, dpi)
    if img is None or min(img.shape) < pub.SIZE:
        return []
    rng = random.Random(seed)
    return [stage_scores(f) for f in (MATCH.load(MATCH.features_img(p)) for p in jittered(img, n, 20, rng))]


def run_c(setname, nprobes, tnames):
    dpi = pub.STRANGER_SETS[setname][0]
    items = pub.strangers(setname)
    jobs = [(p, dpi, nprobes, zlib.crc32(f.encode())) for f, p in items]
    fnames = [f for f, _ in items]
    t = time.time()
    with pool() as p:
        res = progress_map(p, c_worker, jobs, f"C {setname}", 8)
    rows = [r for rs in res for r in rs]
    M, sparse = stage_matrix(rows, len(rows))
    print(f"\n=== C. {len(items)} {setname} strangers ({dpi} dpi, {len(rows)} probe patches) vs the "
          f"{M.shape[1]} templates of B: {M.size} attempts in {time.time() - t:.0f}s")
    print("score histogram:", {int(k): int(v) for k, v in zip(*np.unique(M, return_counts=True))})
    for th in MATCH.thresholds:
        print(f"   threshold {th:4d}: false accepts {int((M >= th).sum())}/{M.size}")
    print("\n".join(pt_report(sparse)))
    np.savez_compressed(os.path.join(OUT_DIR, f"big_eval_c_{setname}_{MATCHER_NAME}{RUN_SUFFIX}.npz"),
                        M=M, templates=tnames,
                        # row -> stranger finger, and its labels (kin: Family only)
                        names=fnames, powner=[i for i, rs in enumerate(res) for _ in rs],
                        split=[pub.split(f) for f in fnames], person=[pub.person(f) for f in fnames],
                        kin_pairs=np.int64(pub.kin_pairs(fnames)).reshape(-1, 2), **sparse)


# ---- S ----------------------------------------------------------------------

# probe kinds of synthetic.py, longest prefix first
S_KINDS = ("blank_n2", "blank", "grating_n", "grating", "checker", "gauss", "uniform", "sp")


def s_kind(name):
    """Kind of a synthetic probe name, e.g. synth/grating_p8_5_o45 -> grating,
    synth/inv/<finger>/0 -> inv, synth/adv/sp50#1 -> adv."""
    seg = name.split("/")[1]
    if seg in ("inv", "mirror", "inv_mirror", "adv"):
        return seg
    return next(k for k in S_KINDS if seg.startswith(k))


def s_worker(img):
    """stage_scores() of one synthetic frame, prepared like a probe patch."""
    return stage_scores(MATCH.load(MATCH.features_img(img)))


def run_s(tnames, nderived, nadv):
    """Synthetic probes (synthetic.py) against every template of B, like C
    strangers: the data-independent probes, the first @nderived enrolled
    patches of every template inverted, mirrored and both, and @nadv seeds of
    each adversarial kind."""
    import synthetic
    probes = synthetic.probes()
    if nderived:
        with pool() as p:
            got = p.map(job_patches, G_FEATS["tjob0"], chunksize=4)
        probes += synthetic.derived([(tnames[j], x) for j, (ps, _, _, _) in enumerate(got) for x in ps[:nderived]])
    for k in synthetic.ADVERSARIAL:
        probes += synthetic.adversarial(k, nadv)
    pnames = [n for n, _ in probes]
    kinds = [s_kind(n) for n in pnames]
    t = time.time()
    with pool() as p:
        res = progress_map(p, s_worker, [im for _, im in probes], "S synthetic", 4)
    M, sparse = stage_matrix(res, len(res))
    smax, sbest = M.max(1), M.argmax(1)
    print(f"\n=== S. {len(probes)} synthetic probes vs the {M.shape[1]} templates of B: {M.size} attempts "
          f"in {time.time() - t:.0f}s")
    print("score histogram:", {int(k): int(v) for k, v in zip(*np.unique(M, return_counts=True))})
    for th in MATCH.thresholds:
        print(f"   threshold {th:4d}: synthetic probes accepted {int((smax >= th).sum())}/{len(probes)}")
    print("   max score per kind (probe, best template):")
    for k in dict.fromkeys(kinds):
        i = max((i for i in range(len(kinds)) if kinds[i] == k), key=lambda i: (smax[i], -i))
        print(f"      {k:10s} {int(smax[i]):4d}  ({kinds.count(k)} probes; {pnames[i]} vs {tnames[sbest[i]]})")
    if "ps_xbest" in sparse and sparse["ps_xbest"].size:
        print(f"   max over the stages stored only for derived stage counts: {int(sparse['ps_xbest'].max())}")
    print("\n".join(pt_report(sparse)))
    np.savez_compressed(os.path.join(OUT_DIR, f"big_eval_s_{MATCHER_NAME}{RUN_SUFFIX}.npz"),
                        M=M, templates=tnames, names=pnames, kind=kinds, smax=smax, sbest=sbest,
                        sbest_name=np.array([tnames[j] for j in sbest], dtype=str),
                        nderived=nderived, nadv=nadv, **sparse)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matcher", default="ours", choices=sorted(matchers.MATCHERS))
    ap.add_argument("--stages", type=int, default=10)
    ap.add_argument("--derive", default="5,10,15",
                    help="smaller stage counts to store per-stage scores for (derive_stages.py); '' for none")
    ap.add_argument("--floor", type=int,
                    help="per-stage scores are stored where a template's best stage score is >= this "
                         "(default: the matcher's lowest reported threshold - 1)")
    ap.add_argument("--jitter", type=float, default=20, help="patch position spread, px at sensor dpi")
    ap.add_argument("--probes", type=int, default=2, help="probe patches per probe impression")
    ap.add_argument("--skip-a", action="store_true")
    ap.add_argument("--skip-b", action="store_true")
    ap.add_argument("--sets", help="comma-separated subset of public sets")
    ap.add_argument("--tag", help="suffix for the result files, e.g. a dataset version")
    ap.add_argument("--strangers", help="comma-separated stranger-only sets for part C, "
                    f"from {sorted(pub.STRANGER_SETS)}")
    ap.add_argument("--synthetic", action="store_true",
                    help="also score the synthetic probes of synthetic.py against every template of B (part S)")
    ap.add_argument("--synthetic-derived", type=int, default=1,
                    help="enrolled patches per template to invert and mirror for part S")
    ap.add_argument("--synthetic-adv", type=int, default=2, help="seeds per adversarial kind for part S")
    ap.add_argument("--data", required=True, help="directory with the public datasets, see docs/DATASETS.md")
    ap.add_argument("--own-captures", help="DIR/<finger>/*.png captures of your own sensor for part A")
    ap.add_argument("--out", default=".", help="directory for the score matrices")
    a = ap.parse_args()
    global MATCH, MATCHER_NAME, RUN_SUFFIX, OUT_DIR
    pub.ROOT = a.data
    OUT_DIR = a.out
    os.makedirs(OUT_DIR, exist_ok=True)
    MATCH, MATCHER_NAME = matchers.get(a.matcher), a.matcher
    if MATCH.c_timed:
        matchers.pairtime_lib()  # built if missing, here rather than in every worker
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
        derive = sorted({int(x) for x in a.derive.split(",") if x and 0 < int(x) < a.stages})
        if derive and hasattr(MATCH, "score_set"):
            # one score against the whole gallery: not the best of its stages
            print(f"   {a.matcher} scores a gallery as a set: no per-stage store")
            derive = []
        floor = a.floor if a.floor is not None else min(MATCH.thresholds) - 1
        tnames = run_b(idx, a.stages, a.jitter, a.probes, derive, floor)
        if a.synthetic:
            run_s(tnames, a.synthetic_derived, a.synthetic_adv)
        for s in (a.strangers.split(",") if a.strangers else []):
            run_c(s, a.probes, tnames)


if __name__ == "__main__":
    main()
