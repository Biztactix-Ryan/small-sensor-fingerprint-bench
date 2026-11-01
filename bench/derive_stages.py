#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Score matrices of smaller enrollments from big_eval.py's per-stage store.

A big_eval.py run at S stages with --derive K1,K2,... stores, for every
template a direct run at K stages would use, the score of each probe against
each of its enrolled images (stages), for every probe x template pair whose
best stage score is >= the floor. A template at K stages is the best of a
subset of those stages (subset() below), so its score is exact wherever the
pair is stored. Where it is not, every stage scored below the floor, and the
cell gets the best stage score of the template (the S-stage score for the
templates of the S-stage run): an upper bound, below the floor. Everything
at or above the floor is exact: false accepts and false rejects at any
threshold > floor, and any threshold found to be > floor. The output keeps
the floor as `floor`; summarize.py marks thresholds it can't vouch for.

Usage: derive_stages.py --stages 5,10,15 [--out DIR] B.npz [C.npz ...]
       derive_stages.py --compare DIRECT.npz DERIVED.npz
C matrices (big_eval_c_*) are derived with the B matrix of the same run,
which must come first.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def subset(imp, rank, att, nimp, k):
    """Indices of the patches a direct run at @k stages enrolls, out of all
    patches of a finger's @nimp enrollment impressions in order (impression
    @imp, @rank-th usable patch in it, found at attempt @att); None if that
    run has fewer than @k and drops the finger. Each impression gives its
    first ceil(k / nimp) usable patches out of 3x as many attempts
    (big_eval.jittered()), the first k of them in order form the template."""
    per = -(-k // nimp)
    sel = [c for c in range(len(imp)) if rank[c] < per and att[c] < 3 * per]
    return sel[:k] if len(sel) >= k else None


def _templates(d, k):
    """[(stored template, names index, local columns)] of the templates at @k
    stages."""
    if "ps_derive" not in d.files:
        raise SystemExit("no per-stage store (run big_eval.py with --derive)")
    if k not in set(d["ps_derive"].tolist()):
        raise SystemExit(f"{k} stages not stored, only {d['ps_derive'].tolist()}")
    ptr = d["ps_ptr"]
    out = []
    for t, (name, nimp) in enumerate(zip(d["ps_tmpl"], d["ps_nimp"])):
        a, b = ptr[t], ptr[t + 1]
        sub = subset(d["ps_imp"][a:b], d["ps_rank"][a:b], d["ps_att"][a:b], nimp, k)
        if sub is not None:
            out.append((t, int(name), sub))
    return out


def _matrix(b, s, tmpls):
    """Derived matrix of the probes of @s (a B or C npz of the run of @b)."""
    ptr, st_names = b["ps_ptr"], b["ps_tmpl"]
    kcol = {k: j for j, k in enumerate(b["keep"].tolist())}
    xcol = {t: x for x, t in enumerate(t for t, k in enumerate(st_names.tolist()) if k not in kcol)}
    M, xbest = s["M"], s["ps_xbest"]
    out = np.empty((M.shape[0], len(tmpls)), M.dtype)
    sub = {}
    for j, (t, name, cols) in enumerate(tmpls):
        out[:, j] = M[:, kcol[name]] if name in kcol else xbest[:, xcol[t]]
        sub[t] = (j, np.array(cols))
    pair, score = s["ps_pair"], s["ps_score"]
    off = np.concatenate([[0], np.cumsum(np.diff(ptr)[pair])])
    for n, (p, t) in enumerate(zip(s["ps_probe"], pair)):
        if t in sub:
            j, cols = sub[t]
            out[p, j] = score[off[n]:off[n + 1]][cols].max()
    return out


def derive(paths, k, out_dir):
    import public_sets as pub
    b = np.load(paths[0], allow_pickle=False)
    tmpls = _templates(b, k)
    keep = [name for _, name, _ in tmpls]
    names = b["names"].tolist()
    ptr = b["ps_ptr"]
    cols = [ptr[t] + np.array(c) for t, _, c in tmpls]
    stem = os.path.basename(paths[0])[:-len(".npz")]
    outs = [os.path.join(out_dir, f"{stem}_d{k}.npz")]
    np.savez_compressed(outs[0], M=_matrix(b, b, tmpls), powner=b["powner"], paligned=b["paligned"],
                        keep=keep, names=names, setname=[names[i].split("/")[0] for i in keep],
                        ident=[pub.identity(names[i]) for i in keep], split=[pub.split(names[i]) for i in keep],
                        person=[pub.person(names[i]) for i in keep],
                        tbytes=np.float64([np.mean(b["ps_bytes"][c]) for c in cols]),
                        poff=b["poff"], toff=np.float32([b["ps_off"][c] for c in cols]).reshape(len(keep), k, 2),
                        floor=b["ps_floor"], derived_from=b["ps_stages"])
    for path in paths[1:]:
        c = np.load(path, allow_pickle=False)
        if "ps_pair" not in c.files or c["M"].shape[1] != len(b["keep"]):
            raise SystemExit(f"{path}: not a part C matrix of the run of {paths[0]}")
        outs.append(os.path.join(out_dir, f"{os.path.basename(path)[:-len('.npz')]}_d{k}.npz"))
        np.savez_compressed(outs[-1], M=_matrix(b, c, tmpls), templates=[names[i] for i in keep],
                            **{f: c[f] for f in ("names", "powner", "split", "person", "kin_pairs")
                               if f in c.files},
                            floor=b["ps_floor"], derived_from=b["ps_stages"])
    return outs


def compare(direct, derived):
    """Check a derived matrix against a direct run at the same stage count:
    the same fields, cells >= floor equal, the others below the floor and not
    below the direct score. Returns whether it holds."""
    a, b = np.load(direct, allow_pickle=False), np.load(derived, allow_pickle=False)
    floor = int(b["floor"])
    ok = True
    for f in sorted(set(a.files) & set(b.files) - {"M"}):
        same = a[f].shape == b[f].shape and np.array_equal(a[f], b[f])
        ok &= same
        if not same:
            print(f"   field {f}: differs")
    A, B = a["M"], b["M"]
    if A.shape != B.shape:
        print(f"   M: shape {A.shape} vs {B.shape}")
        return False
    hi = A >= floor
    eq = int((A == B).sum())
    bad_hi = int((hi & (A != B)).sum())
    bad_lo = int((~hi & ((B >= floor) | (B < A))).sum())
    print(f"   M {A.shape}: {eq}/{A.size} cells equal; {int(hi.sum())} cells >= floor {floor}, "
          f"{bad_hi} of them differ; {int((~hi).sum())} below, {int((~hi & (A != B)).sum())} censored "
          f"(upper bound), {bad_lo} outside [direct, floor)")
    print(f"   fields compared: {sorted(set(a.files) & set(b.files))}")
    return ok and not bad_hi and not bad_lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", help="comma-separated stage counts to derive")
    ap.add_argument("--out", default=".")
    ap.add_argument("--compare", action="store_true", help="compare DIRECT.npz with DERIVED.npz")
    ap.add_argument("npz", nargs="+")
    a = ap.parse_args()
    if a.compare:
        ok = compare(*a.npz)
        print("OK" if ok else "MISMATCH")
        sys.exit(0 if ok else 1)
    os.makedirs(a.out, exist_ok=True)
    for k in (int(x) for x in a.stages.split(",")):
        for p in derive(a.npz, k, a.out):
            print(p)


if __name__ == "__main__":
    main()
