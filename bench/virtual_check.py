#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fidelity check: the harness's scores against libfprint's own, through the
virtual_image driver (FINAL_RUN.md item 0f).

export: the template and probe patches of part B of big_eval.py for some
    fingers (same patches: same impressions, seeds, registration, jitter and
    normalization), a plan of probe x template pairs, and the harness's score
    of every probe against every image of each template, per matcher.
score:  adds the harness's scores of more matchers to an existing export
    (its images and plan as they are).
run:    feeds them through libfprint with fidelity/virtual_check (built by
    fidelity/build.sh against a libfprint build): enroll each template from
    its patches, serialize and load the print, verify each probe, and record
    the scores libfprint computes (one per enrolled print, in order).
diff:   compares the two, per stage score and per pair (best stage), and
    writes pairs.<matcher>.tsv.

libfprint rejects some images the harness scores: NBIS fails the action on an
image without minutiae (the harness: no print, score 0), SIGFM asks for a
retry below 25 keypoints (the harness scores them). Rejected template images
are left out of the enrolled print, so its scores are compared with the
harness's on the images it holds; diff checks that every rejection is one of
those cases and reports how often it changes the pair's best score.

fpi_print_sigfm_match() calls sigfm_match_score (enrolled, probe); the score
is not symmetric, and matchers.Sigfm.score() passed (probe, enrolled) until
2026-11-01. It now passes libfprint's order; exports from before then have
SIGFM harness scores in the old order.

akaze_c: the harness extracts and matches with FPBENCH_AKAZE_LIB (default
akaze/ref/build/libakaze_c.so); build it from the libfprint tree the
fidelity build is of (akaze/build.sh lib with LIBFPRINT=...), else the two
can run different code. Its FPBENCH_AKAZE_* parameters go to
harness.akaze_c.json; diff compares them with the FPI_AKAZE_* macros the
libfprint build reports, so the same tool checks any akaze_c variant.

cscore: akaze_c through FPBENCH_AKAZE_LIB alone, without libfprint's device
path or NumPy/OpenCV, written like harness.akaze_c.txt (masks in the
feature hash when masked) and compared with it. For a variant libfprint's
device path lacks (FPBENCH_AKAZE_MASK=1: prints carry no masks) and to
compare architectures, e.g. on the Pi against the x86 export's harness file.

Patches stay in --out: they are images, never commit or publish them.

Usage:
  virtual_check.py export --data DIR --sets fvc2000_DB1_B --matchers nbis,sigfm,sigfm_fix --out D
  virtual_check.py score --dir D --matchers akaze_c
  virtual_check.py run --dir D --matcher nbis [--jobs 4]
  virtual_check.py diff --dir D --matcher nbis
  FPBENCH_AKAZE_MASK=1 virtual_check.py cscore --dir D [--against FILE]
"""
import argparse
import ctypes
import hashlib
import json
import os
import random
import subprocess
import sys
import zlib
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# export needs the harness (OpenCV, NumPy); run and diff only the standard
# library, so they also work on a machine without the harness (e.g. the Pi)
be = matchers = np = pub = None


def _harness():
    global be, matchers, np, pub
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    import numpy as np
    import big_eval as be
    import matchers
    import public_sets as pub

HERE = os.path.dirname(os.path.abspath(__file__))
FIDELITY = os.path.join(HERE, "..", "fidelity")
# matcher -> virtual_check options; the build is fidelity/build/<matcher>
LIBFPRINT = {"nbis": [], "sigfm": ["--sigfm"], "sigfm_fix": ["--sigfm"], "akaze_c": ["--keypoint"]}
# below this many keypoints fp-image.c of !530 rejects a SIGFM image
SIGFM_MIN_KEYPOINTS = 25


def patch_job(job):
    """The patches feat_worker() of big_eval.py computes features of."""
    path, dpi, n, jitter, seed, ref = job
    rng = random.Random(seed)
    img = be.load_scaled(path, dpi)
    if img is None or min(img.shape) < pub.SIZE:
        return []
    at = None
    if ref:
        at = be.aligned_centre(img, be.load_scaled(*ref))
    return be.jittered(img, n, jitter, rng, at)


def finger_patches(f, imps, stages, jitter, nprobes):
    """(template patches, [probe patches]) of finger @f as run_b() forms them."""
    imps = sorted(imps)
    half = max(1, len(imps) // 2)
    enroll, probe = imps[:half], imps[half:]
    per = -(-stages // len(enroll))
    ref = (enroll[0][1], enroll[0][2])
    tmpl = []
    for i, (_, p, dpi) in enumerate(enroll):
        tmpl += patch_job((p, dpi, per, jitter, zlib.crc32(f"{f}/{i}".encode()), ref if i else None))
    probes = []
    for i, (_, p, dpi) in enumerate(probe):
        probes += patch_job((p, dpi, nprobes, jitter, zlib.crc32(f"{f}/p{i}".encode()), ref))
    return tmpl[:stages], probes


def _patches_worker(job):
    return finger_patches(*job)


G = {}


def _score_worker(t):
    """Harness scores of every planned probe against every image of template t."""
    m, feats = G["match"], G["feats"]
    gal = [feats[i] for i in G["timgs"][t]]
    return [(t, p, [int(m.score(feats[G["pimg"][p]], g)) for g in gal]) for p in G["plan"][t]]


def export(a):
    _harness()
    pub.ROOT = a.data
    idx = [x for x in pub.index() if x[0] in a.sets.split(",")]
    by_finger = defaultdict(list)
    for s, f, imp, p in idx:
        by_finger[f].append((imp, p, pub.SETS[s][0]))
    names = sorted(by_finger)
    with be.pool() as p:
        res = p.map(_patches_worker, [(f, by_finger[f], a.stages, a.jitter, a.probes) for f in names])

    images, timgs, tname, pimg, powner = [], [], [], [], []
    keep = [k for k, (t, _) in enumerate(res) if len(t) == a.stages]
    for k in keep:
        timgs.append(list(range(len(images), len(images) + a.stages)))
        tname.append(names[k])
        images += res[k][0]
    for k, (_, probes) in enumerate(res):
        for x in probes:
            pimg.append(len(images))
            powner.append(names[k])
            images.append(x)
    rng = random.Random(a.seed)
    tsel = list(range(len(keep)))
    if a.templates and a.templates < len(tsel):
        tsel = sorted(rng.sample(tsel, a.templates))
    plan = {}
    for t in tsel:
        ps = list(range(len(pimg)))
        if a.pairs_per_template and a.pairs_per_template < len(ps):
            # every genuine probe, then random impostors
            gen = [p for p in ps if powner[p] == tname[t]]
            imp = [p for p in ps if powner[p] != tname[t]]
            ps = sorted(gen + rng.sample(imp, max(0, a.pairs_per_template - len(gen))))
        plan[t] = ps
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "images.bin"), "wb") as f:
        for x in images:
            x = np.ascontiguousarray(x, np.uint8)
            f.write(np.int32([x.shape[1], x.shape[0]]).tobytes() + x.tobytes())
    with open(os.path.join(a.out, "plan.txt"), "w") as f:
        for t in tsel:
            f.write(f"T {t} {' '.join(map(str, timgs[t]))}\n")
            f.writelines(f"P {t} {p} {pimg[p]}\n" for p in plan[t])
    meta = dict(sets=a.sets, stages=a.stages, jitter=a.jitter, probes=a.probes, names=names, keep=keep,
                templates=tname, probe_owner=powner, probe_image=pimg, template_images=timgs,
                pairs=sum(len(v) for v in plan.values()))
    with open(os.path.join(a.out, "meta.json"), "w") as f:
        json.dump(meta, f)
    print(f"{len(names)} fingers, {len(keep)} templates of {a.stages} patches, {len(pimg)} probe patches, "
          f"{meta['pairs']} pairs from {len(tsel)} templates, {len(images)} images")
    score_matchers(a.out, a.matchers, images, timgs, pimg, plan)


def harness_params(name):
    """The harness's parameters of matcher @name that libfprint has at build
    time, as virtual_check reports them ("# keypoint ...")."""
    if name != "akaze_c":
        return {}
    return dict(upscale=matchers.AKAZE_UPSCALE, clahe_clip=matchers.AKAZE_CLAHE_CLIP, pad=matchers.AKAZE_PAD,
                pad_mode="replicate" if matchers.AKAZE_PAD_REPLICATE else "reflect",
                threshold=matchers.AKAZE_THRESHOLD, max_keypoints=matchers.AKAZE_MAX_KP,
                max_matches=matchers.MAX_MATCHES,
                **(dict(mask=1, border=matchers.AKAZE_BORDER, min_bits=matchers.AKAZE_MIN_BITS)
                   if matchers.AKAZE_MASK else {}),
                lib=os.path.realpath(os.environ.get("FPBENCH_AKAZE_LIB", os.path.join(
                    HERE, "..", "akaze", "ref", "build", "libakaze_c.so"))))


def score_matchers(out, names, images, timgs, pimg, plan):
    tsel = list(plan)
    for name in names.split(","):
        m = matchers.get(name)
        raw = [m.features_img(x) for x in images]
        G.update(match=m, feats=[m.load(x) for x in raw], timgs=timgs, pimg=pimg, plan=plan)
        with be.pool() as p:
            rows = [r for rs in p.map(_score_worker, tsel) for r in rs]
        params = harness_params(name)
        if params:
            with open(os.path.join(out, f"harness.{name}.json"), "w") as f:
                json.dump(params, f)
        with open(os.path.join(out, f"harness.{name}.txt"), "w") as f:
            # image, keypoints (-1: no print), features as virtual_check reports them
            f.writelines(f"I {i} {m.n_keypoints(x) if x is not None else -1} {features_id(m, r, x)}\n"
                         for i, (r, x) in enumerate(zip(raw, G["feats"])))
            f.writelines(f"H {t} {p} {len(s)} {' '.join(map(str, s))}\n" for t, p, s in rows)
        print(f"   {name}: {len(rows)} pairs scored")


def load_export(d):
    """images, template images, probe images and plan of export @d."""
    _harness()
    images = []
    with open(os.path.join(d, "images.bin"), "rb") as f:
        while True:
            wh = f.read(8)
            if not wh:
                break
            w, h = np.frombuffer(wh, np.int32)
            images.append(np.frombuffer(f.read(int(w) * int(h)), np.uint8).reshape(int(h), int(w)))
    meta = json.load(open(os.path.join(d, "meta.json")))
    plan = {}
    with open(os.path.join(d, "plan.txt")) as f:
        for line in f:
            x = line.split()
            if x[0] == "T":
                plan[int(x[1])] = []
            elif x[0] == "P":
                plan[int(x[1])].append(int(x[2]))
    return images, meta["template_images"], meta["probe_image"], plan


def score(a):
    images, timgs, pimg, plan = load_export(a.dir)
    print(f"{a.dir}: {len(images)} images, {sum(map(len, plan.values()))} pairs from {len(plan)} templates")
    score_matchers(a.dir, a.matchers, images, timgs, pimg, plan)


def features_id(m, raw, loaded):
    """"<count>:<sha1 prefix>" of an image's features as fidelity/virtual_check.c
    reports them from libfprint's print: NBIS's struct xyt_struct, SIGFM's
    serialized info, keypoint matchers' float32 points then descriptors; "-"
    without a print."""
    if raw is None:
        return "-"
    if isinstance(raw, tuple):
        pts, des = loaded[:2]
        if des is None or len(pts) == 0:
            return "-"
        raw = np.ascontiguousarray(pts, np.float32).tobytes() + np.ascontiguousarray(des, np.uint8).tobytes()
        if len(loaded) > 2:
            # akaze_c with FPBENCH_AKAZE_MASK=1: then the masks (as cscore)
            raw += np.ascontiguousarray(loaded[2], np.uint8).tobytes()
    return f"{m.n_keypoints(loaded)}:{hashlib.sha1(raw).hexdigest()[:16]}"


def run(a):
    exe = a.helper or os.path.join(FIDELITY, "build", a.matcher, "virtual_check")
    opts = LIBFPRINT[a.matcher] + (["--no-partial"] if a.no_partial else [])
    out = os.path.join(a.dir, f"libfprint.{a.matcher}.txt")
    # split the plan by template into --jobs parts, one process each
    blocks, cur = [], None
    with open(os.path.join(a.dir, "plan.txt")) as f:
        for line in f:
            if line.startswith("T "):
                cur = []
                blocks.append(cur)
            cur.append(line)
    jobs = max(1, min(a.jobs, len(blocks)))
    parts = [os.path.join(a.dir, f"plan.{a.matcher}.{j}.txt") for j in range(jobs)]
    for j, path in enumerate(parts):
        with open(path, "w") as f:
            for b in blocks[j::jobs]:
                f.writelines(b)
    procs = [subprocess.Popen([exe, *opts, os.path.join(a.dir, "images.bin"), path, path + ".out"])
             for path in parts]
    if any(p.wait() for p in procs):
        sys.exit("virtual_check failed")
    with open(out, "w") as f:
        for path in parts:
            with open(path + ".out") as g:
                f.write(g.read())
            os.remove(path + ".out")
            os.remove(path)
    print(f"wrote {out}")


def rejected_ok(matcher, kp):
    """Whether libfprint may reject an image the harness found @kp keypoints in."""
    if matcher in ("nbis", "akaze_c"):
        return kp <= 0
    return kp < SIGFM_MIN_KEYPOINTS


def diff(a):
    kp, fid, harness = {}, {}, {}
    with open(os.path.join(a.dir, f"harness.{a.matcher}.txt")) as f:
        for line in f:
            x = line.split()
            if x[0] == "I":
                kp[int(x[1])] = int(x[2])
                fid[int(x[1])] = x[3]
            else:
                harness[(int(x[1]), int(x[2]))] = [int(s) for s in x[4:]]
    meta = json.load(open(os.path.join(a.dir, "meta.json")))
    timgs, pimg = meta["template_images"], meta["probe_image"]
    enrolled, lib, feat_lib, lib_params = {}, {}, {}, {}
    with open(os.path.join(a.dir, f"libfprint.{a.matcher}.txt")) as f:
        for line in f:
            x = line.split()
            if x[0] == "#":
                lib_params.update(kv.split("=", 1) for kv in x[2:])
            elif x[0] == "E":
                acc = [] if x[5] == "-" else [int(i) for i in x[5].split(",")]
                rej = [] if x[6] == "-" else [int(i) for i in x[6].split(",")]
                # bytes, round trip (the loaded print serializes to the same bytes)
                enrolled[int(x[1])] = (acc, rej, int(x[2]), x[3] == "1")
                for i, ft in zip(acc, x[7].split(",") if acc else []):
                    feat_lib[i] = ft
            else:
                lib[(int(x[1]), int(x[2]))] = (x[3], [int(s) for s in x[7:]])
                feat_lib.setdefault(pimg[int(x[2])], x[5])

    n_stage = same_stage = 0
    max_abs = 0
    pair_same = pair_full_same = 0
    status = defaultdict(int)
    unexplained = []
    rows = []
    for t, (acc, rej, size, round_trip) in enrolled.items():
        if acc and not round_trip:
            unexplained.append(f"template {t}: the loaded print serializes differently")
        unexplained += [f"template {t}: image {i} rejected, harness keypoints {kp[i]}"
                        for i in rej if not rejected_ok(a.matcher, kp[i])]
    for (t, p), hs in harness.items():
        if (t, p) not in lib:
            unexplained.append(f"pair {t} {p}: not run through libfprint")
            continue
        st, ls = lib[(t, p)]
        status[st] += 1
        acc = enrolled[t][0]
        pos = [timgs[t].index(i) for i in acc]
        hacc = [hs[k] for k in pos]
        hmax_all = max(hs)
        if st != "ok":
            if not rejected_ok(a.matcher, kp[pimg[p]]):
                unexplained.append(f"pair {t} {p}: probe {st}, harness keypoints {kp[pimg[p]]}")
            rows.append((t, p, st, "", max(hacc) if hacc else 0, hmax_all, ""))
            continue
        if len(ls) != len(hacc):
            unexplained.append(f"pair {t} {p}: {len(ls)} libfprint scores for {len(hacc)} enrolled images")
            continue
        d = [abs(x - y) for x, y in zip(ls, hacc)]
        n_stage += len(d)
        same_stage += d.count(0)
        max_abs = max([max_abs] + d)
        lmax, hmax = max(ls), max(hacc)
        pair_same += lmax == hmax
        pair_full_same += lmax == hmax_all
        rows.append((t, p, st, lmax, hmax, hmax_all, int(not any(d))))

    same_feat = sum(fid[i] == ft for i, ft in feat_lib.items() if ft != "-")
    n_feat = sum(ft != "-" for ft in feat_lib.values())
    unexplained += [f"image {i}: features {ft} in libfprint, {fid[i]} in the harness"
                    for i, ft in feat_lib.items() if ft != "-" and fid[i] != ft]
    hpath = os.path.join(a.dir, f"harness.{a.matcher}.json")
    hparams = json.load(open(hpath)) if os.path.exists(hpath) else {}
    # the harness's and libfprint's build parameters, those both report
    params_differ = [f"{k}: harness {hparams[k]}, libfprint {v}" for k, v in sorted(lib_params.items())
                     if k in hparams and float(v) != float(hparams[k])]
    n_ok = status["ok"]
    nrej = sum(len(e[1]) for e in enrolled.values())
    nimg = sum(len(timgs[t]) for t in enrolled)
    print(f"{a.matcher}: {len(harness)} pairs, {len(enrolled)} templates "
          f"({nrej}/{nimg} template images rejected by libfprint)")
    if lib_params or hparams:
        print(f"   parameters: libfprint {lib_params}, harness "
              f"{ {k: v for k, v in hparams.items() if k != 'lib'} }, harness lib {hparams.get('lib')}")
    for p in params_differ:
        print(f"   PARAMETER DIFFERS {p} (a different variant: scores are not expected to agree)")
    print(f"   verify status: {dict(status)}")
    print(f"   image features (count + SHA-1), images libfprint made a print of: {same_feat}/{n_feat} identical")
    print(f"   stage scores (pairs verified, enrolled images): {same_stage}/{n_stage} identical, "
          f"max abs diff {max_abs}")
    print(f"   pair score (best stage), same enrolled images: {pair_same}/{n_ok} identical")
    print(f"   pair score vs the harness's full template: {pair_full_same}/{n_ok} identical "
          f"(differs only through rejected template images)")
    print(f"   unexplained: {len(unexplained)}")
    for u in unexplained[:20]:
        print("     ", u)
    with open(os.path.join(a.dir, f"pairs.{a.matcher}.tsv"), "w") as f:
        f.write("template\tprobe\tstatus\tlibfprint\tharness_enrolled\tharness_all\tstages_identical\n")
        f.writelines("\t".join(map(str, r)) + "\n" for r in rows)
    ok = not unexplained and same_stage == n_stage and n_stage > 0
    print("   IDENTICAL" if ok else "   MISMATCH")
    return 0 if ok else 1


class _CFeatures(ctypes.Structure):
    # FpiAkazeFeatures
    _fields_ = [("n", ctypes.c_uint), ("keypoints", ctypes.c_void_p), ("points", ctypes.c_void_p),
                ("descriptors", ctypes.c_void_p)]


class _CFeaturesMasked(_CFeatures):
    # FpiAkazeFeatures with akaze/masked.patch
    _fields_ = [("masks", ctypes.c_void_p), ("valid_bits", ctypes.c_void_p)]


class _CKeypoints(ctypes.Structure):
    # FpiKeypoints
    _fields_ = [("n", ctypes.c_uint), ("points", ctypes.c_void_p), ("descriptors", ctypes.c_void_p)]


C = {}


def _c_env():
    """akaze_c's FPBENCH_AKAZE_* settings, read as bench/matchers.py reads
    them (that module needs NumPy and OpenCV)."""
    e = os.environ.get
    mask = e("FPBENCH_AKAZE_MASK", "0") not in ("", "0")
    if e("FPBENCH_AKAZE_FLOOR_FIRST", "0") not in ("", "0"):
        sys.exit("cscore: FPBENCH_AKAZE_FLOOR_FIRST is not supported")
    return dict(mask=mask, max_kp=int(e("FPBENCH_AKAZE_MAX_KP", 384)), upscale=int(e("FPBENCH_AKAZE_UPSCALE", 3)),
                clahe=float(e("FPBENCH_AKAZE_CLAHE_CLIP", 2.0)),
                replicate=e("FPBENCH_AKAZE_PAD_MODE", "replicate") == "replicate",
                threshold=float(e("FPBENCH_AKAZE_THRESHOLD", 0.0002)),
                pad=int(e("FPBENCH_AKAZE_PAD", 0 if mask else 20)), border=int(e("FPBENCH_AKAZE_BORDER", 2)),
                min_bits=int(e("FPBENCH_AKAZE_MIN_BITS", 162)), max_matches=int(e("FPBENCH_MAX_MATCHES", 64)),
                lib=e("FPBENCH_AKAZE_LIB", os.path.join(HERE, "..", "akaze", "ref", "build", "libakaze_c.so")))


def _c_lib(path, mask):
    lib = ctypes.CDLL(path)
    # the masked library's FpiAkazeFeatures has two more fields
    feat = _CFeaturesMasked if mask else _CFeatures
    lib.fpi_keypoint_prepare_image_full.restype = None
    lib.fpi_keypoint_prepare_image_full.argtypes = (ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                    ctypes.c_double, ctypes.c_void_p)
    lib.fpi_akaze_extract_full.restype = ctypes.POINTER(feat)
    lib.fpi_akaze_extract_full.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_float, ctypes.c_uint)
    lib.fpi_akaze_features_free.argtypes = (ctypes.POINTER(feat),)
    lib.fpi_keypoint_match_score_full.restype = ctypes.c_uint
    lib.fpi_keypoint_match_score_full.argtypes = (ctypes.POINTER(_CKeypoints), ctypes.POINTER(_CKeypoints),
                                                  ctypes.c_int, ctypes.c_uint, ctypes.c_double, ctypes.c_uint,
                                                  ctypes.c_int, ctypes.c_void_p)
    if not mask:
        return lib
    missing = [s for s in ("fpi_akaze_extract_masked", "fpi_keypoint_match_score_masked") if not hasattr(lib, s)]
    if missing:
        sys.exit(f"cscore: FPBENCH_AKAZE_MASK=1 needs {', '.join(missing)}, which {path} lacks: apply "
                 "akaze/masked.patch to a copy of the libfprint tree and rebuild with LIBFPRINT=<copy> "
                 "akaze/build.sh lib (see the patch header)")
    lib.fpi_akaze_extract_masked.restype = ctypes.POINTER(feat)
    lib.fpi_akaze_extract_masked.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_float, ctypes.c_uint)
    lib.fpi_keypoint_match_score_masked.restype = ctypes.c_uint
    lib.fpi_keypoint_match_score_masked.argtypes = (ctypes.POINTER(_CKeypoints), ctypes.c_void_p,
                                                    ctypes.POINTER(_CKeypoints), ctypes.c_void_p, ctypes.c_uint,
                                                    ctypes.c_uint, ctypes.c_double, ctypes.c_uint, ctypes.c_int,
                                                    ctypes.c_void_p)
    return lib


def _c_features(img):
    """(n, points, descriptors, masks) of an export image (w, h, bytes), as
    matchers.AkazeC.features_img() computes them."""
    lib, p = C["lib"], C["env"]
    w, h, data = img
    k = p["upscale"]
    if (k * w) % 4 or (k * h) % 4:
        raise ValueError(f"akaze_c: unsupported image size {w}x{h} at upscale {k}")
    pre = ctypes.create_string_buffer(k * w * k * h)
    lib.fpi_keypoint_prepare_image_full(data, w, h, k, p["clahe"], pre)
    if p["mask"]:
        f = lib.fpi_akaze_extract_masked(pre, k * w, k * h, p["border"], p["threshold"], p["max_kp"])
    else:
        f = lib.fpi_akaze_extract_full(pre, k * w, k * h, p["pad"], p["replicate"], p["threshold"], p["max_kp"])
    if not f:
        raise ValueError(f"akaze_c: unsupported image size {w}x{h}")
    n = f.contents.n
    dl = 61  # FPI_AKAZE_DESCRIPTOR_LEN
    pts = ctypes.string_at(f.contents.points, 8 * n) if n else b""
    des = ctypes.string_at(f.contents.descriptors, n * dl) if n else b""
    masks = ctypes.string_at(f.contents.masks, n * dl) if p["mask"] and n else b""
    lib.fpi_akaze_features_free(f)
    return n, pts, des, masks


def _c_score_worker(t):
    lib, p, feats = C["lib"], C["env"], C["feats"]
    # inlier indices, up to the probe's keypoints
    out = (ctypes.c_uint * max(1, max(x[0] for x in feats)))()

    def kp(i):
        n, pts, des, _ = feats[i]
        return _CKeypoints(n, ctypes.cast(ctypes.c_char_p(pts), ctypes.c_void_p),
                           ctypes.cast(ctypes.c_char_p(des), ctypes.c_void_p))

    rows = []
    for pr in C["plan"][t]:
        pi = C["pimg"][pr]
        a = kp(pi)
        s = []
        for g in C["timgs"][t]:
            if not feats[pi][0] or not feats[g][0]:
                s.append(0)  # the harness: no descriptors, no match
                continue
            b = kp(g)
            if p["mask"]:
                s.append(lib.fpi_keypoint_match_score_masked(
                    ctypes.byref(a), feats[pi][3], ctypes.byref(b), feats[g][3], p["min_bits"], 61,
                    3.0 * p["upscale"], p["max_matches"], 1 | 2, out))
            else:
                s.append(lib.fpi_keypoint_match_score_full(ctypes.byref(a), ctypes.byref(b), 1, 61,
                                                           3.0 * p["upscale"], p["max_matches"], 1 | 2, out))
        rows.append((t, pr, s))
    return rows


def cscore(a):
    """akaze_c through its C library alone (FPBENCH_AKAZE_LIB, ctypes,
    standard library only), in the harness's format, compared with
    harness.akaze_c.txt of the export (or --against). For variants
    libfprint's device path does not have (FPBENCH_AKAZE_MASK=1: prints
    carry no masks), and to compare architectures: on another machine
    against the export's harness file from the first."""
    import multiprocessing
    env = _c_env()
    images = []
    with open(os.path.join(a.dir, "images.bin"), "rb") as f:
        while True:
            wh = f.read(8)
            if not wh:
                break
            w, h = int.from_bytes(wh[:4], "little", signed=True), int.from_bytes(wh[4:], "little", signed=True)
            images.append((w, h, f.read(w * h)))
    meta = json.load(open(os.path.join(a.dir, "meta.json")))
    plan = {}
    with open(os.path.join(a.dir, "plan.txt")) as f:
        for line in f:
            x = line.split()
            if x[0] == "T":
                plan[int(x[1])] = []
            elif x[0] == "P":
                plan[int(x[1])].append(int(x[2]))
    C.update(lib=_c_lib(env["lib"], env["mask"]), env=env)
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(a.jobs) as pool:
        feats = pool.map(_c_features, images, chunksize=16)
    C.update(feats=feats, plan=plan, timgs=meta["template_images"], pimg=meta["probe_image"])
    with ctx.Pool(a.jobs) as pool:
        rows = [r for rs in pool.map(_c_score_worker, list(plan)) for r in rs]
    out = a.out or os.path.join(a.dir, "cscore.akaze_c.txt")
    with open(out, "w") as f:
        for i, (n, pts, des, masks) in enumerate(feats):
            fid = f"{n}:{hashlib.sha1(pts + des + masks).hexdigest()[:16]}" if n else "-"
            f.write(f"I {i} {n} {fid}\n")
        f.writelines(f"H {t} {p} {len(s)} {' '.join(map(str, s))}\n" for t, p, s in rows)
    print(f"wrote {out}: {len(images)} images, {len(rows)} pairs, "
          f"{ {k: v for k, v in env.items() if k != 'lib'} }, lib {os.path.realpath(env['lib'])}")
    against = a.against or os.path.join(a.dir, "harness.akaze_c.txt")
    hp = os.path.splitext(against)[0] + ".json"
    if os.path.exists(hp):
        h = json.load(open(hp))
        want = dict(pad=env["pad"], max_keypoints=env["max_kp"], upscale=env["upscale"], mask=int(env["mask"]))
        differ = {k: (h.get(k, 0), v) for k, v in want.items() if float(h.get(k, 0)) != float(v)}
        if differ:
            print(f"   PARAMETERS DIFFER from {hp} (theirs, ours): {differ}")
    with open(out) as f:
        mine = f.read().splitlines()
    with open(against) as f:
        theirs = f.read().splitlines()
    mi = {tuple(x.split()[:3]): x for x in mine}
    ti = {tuple(x.split()[:3]): x for x in theirs}
    img_same = sum(x[0] == "I" and mi[x] == ti.get(x) for x in mi)
    n_img = sum(x[0] == "I" for x in mi)
    n_stage = same_stage = pair_same = n_pair = 0
    for k, x in mi.items():
        if k[0] != "H":
            continue
        n_pair += 1
        y = ti.get(k)
        ys = y.split()[4:] if y else []
        xs = x.split()[4:]
        n_stage += len(xs)
        same_stage += sum(u == v for u, v in zip(xs, ys))
        pair_same += bool(y) and max(map(int, xs)) == max(map(int, ys))
    print(f"   against {against}: image features {img_same}/{n_img} identical, stage scores "
          f"{same_stage}/{n_stage} identical, pair score (best stage) {pair_same}/{n_pair} identical")
    ok = mine == theirs
    print("   IDENTICAL" if ok else "   MISMATCH")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--data", required=True)
    e.add_argument("--sets", required=True, help="comma-separated public sets")
    e.add_argument("--matchers", default="nbis,sigfm,sigfm_fix")
    e.add_argument("--stages", type=int, default=20)
    e.add_argument("--jitter", type=float, default=20)
    e.add_argument("--probes", type=int, default=2)
    e.add_argument("--templates", type=int, help="random sample of this many templates")
    e.add_argument("--pairs-per-template", type=int, help="genuine probes + random impostors up to this")
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--out", required=True)
    s = sub.add_parser("score")
    s.add_argument("--dir", required=True)
    s.add_argument("--matchers", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dir", required=True)
    r.add_argument("--matcher", required=True, choices=sorted(LIBFPRINT))
    r.add_argument("--helper", help="virtual_check binary (default fidelity/build/<matcher>/virtual_check)")
    r.add_argument("--no-partial", action="store_true", help="don't flag images partial like elan does")
    r.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    c = sub.add_parser("cscore")
    c.add_argument("--dir", required=True)
    c.add_argument("--out", help="default DIR/cscore.akaze_c.txt")
    c.add_argument("--against", help="default DIR/harness.akaze_c.txt")
    c.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    d = sub.add_parser("diff")
    d.add_argument("--dir", required=True)
    d.add_argument("--matcher", required=True)
    a = ap.parse_args()
    if a.cmd == "export":
        export(a)
    elif a.cmd == "score":
        score(a)
    elif a.cmd == "run":
        run(a)
    elif a.cmd == "cscore":
        sys.exit(cscore(a))
    else:
        sys.exit(diff(a))


if __name__ == "__main__":
    main()
