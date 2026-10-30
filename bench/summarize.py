#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Markdown summary of big_eval.py score matrices.

For every part B matrix (big_eval_b_<matcher>*.npz): impostor maximum, the
lowest threshold without false accepts and the genuine false-reject rate there,
the false accepts at the matcher's default threshold, and the false-reject
rate per set. A second table gives the false-reject rate at a fixed
false-accept rate (1e-5) and per set averaged, and how much the zero-FA
threshold and its false-reject rate move when the fingers are resampled
(bootstrap over fingers, 5th-95th percentile). For part C matrices (big_eval_c_<set>_<matcher>*.npz): stranger
score maximum and false accepts at the default threshold.

"registered" genuine attempts are those whose probe impression could be
registered to the enrollment impression, i.e. the probe patches cover the
enrolled area; the others are dominated by probes that don't overlap it.

Usage: summarize.py RESULTS_DIR
"""
import glob
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matchers  # noqa: E402
import public_sets as pub  # noqa: E402


def matcher_of(path, prefix):
    stem = os.path.basename(path)[len(prefix):-len(".npz")]
    for name in sorted(matchers.MATCHERS, key=len, reverse=True):
        if stem == name or stem.startswith(name + "_"):
            return name, stem[len(name):].lstrip("_")
    return stem, ""


def part_b(path):
    d = np.load(path, allow_pickle=False)
    M, powner, paligned = d["M"], d["powner"], d["paligned"]
    keep, names = list(d["keep"]), list(d["names"])
    ident = [pub.identity(names[i]) for i in keep]
    col = {k: j for j, k in enumerate(keep)}
    gen, reg, imp, gset = [], [], [], []
    for pi, k in enumerate(powner):
        if k not in col:
            continue
        own = col[k]
        for j in range(M.shape[1]):
            if j == own:
                gen.append(M[pi, j])
                reg.append(bool(paligned[pi]))
                gset.append(names[k].split("/")[0])
            elif ident[j] != ident[own]:
                imp.append(M[pi, j])
    return np.array(gen), np.array(reg), np.array(imp), np.array(gset), len(keep)


def threshold_at(hist, k):
    """Lowest threshold with at most k (weighted) impostor scores at or above."""
    above = np.cumsum(hist[::-1])[::-1]  # above[t] = weight of scores >= t
    return int(np.argmax(above <= k))


def stats(path, rate=1e-5, rounds=200, min_set=20):
    """Zero-FA threshold and FRR (registered) with bootstrap ranges over
    fingers, FRR at a false-accept rate, and FRR averaged over sets."""
    d = np.load(path, allow_pickle=False)
    M, powner, paligned = d["M"], d["powner"], d["paligned"]
    keep, names = list(d["keep"]), list(d["names"])
    col = {k: j for j, k in enumerate(keep)}
    ident = np.array([pub.identity(names[i]) for i in keep])
    rows = np.array([pi for pi, k in enumerate(powner) if k in col])
    own = np.array([col[powner[pi]] for pi in rows])
    S = M[rows]
    imp_mask = ident[None, :] != ident[own][:, None]
    gen = S[np.arange(len(rows)), own]
    reg = paligned[rows]
    gset = np.array([names[keep[o]].split("/")[0] for o in own])
    top = int(S[imp_mask].max()) + 2
    imp_scores = np.minimum(S, top - 1)

    def evaluate(w):
        wi = (w[own][:, None] * w[None, :]) * imp_mask
        hist = np.bincount(imp_scores.ravel(), weights=wi.ravel(), minlength=top)
        zt = threshold_at(hist, 0)
        wg = w[own] * reg
        frr = (wg * (gen < zt)).sum() / max(wg.sum(), 1)
        return zt, frr, hist, wi.sum()

    zt, frr, hist, n_imp = evaluate(np.ones(len(keep)))
    k = int(rate * n_imp)
    kt = threshold_at(hist, k)
    frr_k = (gen[reg] < kt).mean()
    sets = [x for x in np.unique(gset) if (reg & (gset == x)).sum() >= min_set]
    set_mean = np.mean([(gen[reg & (gset == x)] < zt).mean() for x in sets])
    rng = np.random.default_rng(0)
    boot = [evaluate(np.bincount(rng.integers(0, len(keep), len(keep)), minlength=len(keep)).astype(float))[:2]
            for _ in range(rounds)]
    bt, bf = np.array(boot).T
    return dict(zt=zt, frr=frr, zt_lo=int(np.percentile(bt, 5)), zt_hi=int(np.percentile(bt, 95)),
                frr_lo=np.percentile(bf, 5), frr_hi=np.percentile(bf, 95), k=k, kt=kt, frr_k=frr_k,
                set_mean=set_mean, nsets=len(sets),
                tbytes=float(d["tbytes"].mean()) if "tbytes" in d.files else None)


OVERLAP_BINS = (0, 0.5, 0.75, 0.9, 1.01)


def overlap(probe, templates, size=pub.SIZE):
    """Share of the probe patch covered by the union of the enrolled patches,
    from patch centre offsets in a common frame."""
    u = np.arange(size) - size / 2 + 0.5
    cover = np.zeros((size, size), bool)
    for t in templates:
        my = np.abs(probe[0] + u - t[0]) < size / 2
        mx = np.abs(probe[1] + u - t[1]) < size / 2
        cover |= my[:, None] & mx[None, :]
    return cover.mean()


def overlap_frr(path):
    """Registered FRR at the zero-FA threshold, by overlap of the probe with the
    enrolled area: [(n, frr)] per OVERLAP_BINS bin; None without offsets."""
    d = np.load(path, allow_pickle=False)
    if "poff" not in d.files:
        return None
    M, powner, paligned, poff, toff = d["M"], d["powner"], d["paligned"], d["poff"], d["toff"]
    keep = list(d["keep"])
    col = {k: j for j, k in enumerate(keep)}
    _, _, imp, _, _ = part_b(path)
    zt = int(imp.max()) + 1
    ov, ok = [], []
    for pi, k in enumerate(powner):
        if k in col and paligned[pi]:
            ov.append(overlap(poff[pi], toff[col[k]]))
            ok.append(M[pi, col[k]] >= zt)
    ov, ok = np.array(ov), np.array(ok)
    out = []
    for lo, hi in zip(OVERLAP_BINS, OVERLAP_BINS[1:]):
        b = (ov >= lo) & (ov < hi)
        out.append((int(b.sum()), (~ok[b]).mean() if b.any() else float("nan")))
    return out


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    bs = sorted(glob.glob(os.path.join(out, "big_eval_b_*.npz")))
    per_set = {}
    print("## Simulated enroll/verify (part B)\n")
    print("| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold "
          "| FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default "
          "| FRR registered @ default |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for p in bs:
        name, run = matcher_of(p, "big_eval_b_")
        m = matchers.get(name)
        gen, reg, imp, gset, nfing = part_b(p)
        zt = int(imp.max()) + 1
        print(f"| {name} | {run or '-'} | {nfing} | {imp.size} | {int(imp.max())} | {zt} "
              f"| {100 * (gen[reg] < zt).mean():.1f}% | {100 * (gen < zt).mean():.1f}% "
              f"| {m.default} | {int((imp >= m.default).sum())} | {100 * (gen[reg] < m.default).mean():.1f}% |")
        r = defaultdict(lambda: [0, 0])
        for g, ok, s in zip(gen, reg, gset):
            if ok:
                r[s][0] += g < zt
                r[s][1] += 1
        per_set[(name, run)] = r
    if per_set:
        cols = list(per_set)
        sets = sorted({s for r in per_set.values() for s in r})
        print("\n### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold\n")
        print("| set | n | " + " | ".join(f"{n} {r}".strip() for n, r in cols) + " |")
        print("|---|---|" + "---|" * len(cols))
        for s in sets:
            n = max(per_set[c][s][1] for c in cols)
            cells = [f"{100 * per_set[c][s][0] / per_set[c][s][1]:.1f}%" if per_set[c][s][1] else "-"
                     for c in cols]
            print(f"| {s} | {n} | " + " | ".join(cells) + " |")
    if bs:
        print("\n### Uncertainty, fixed false-accept rate and per-set average\n")
        print("Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x "
              "impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean "
              "over sets with at least 20 registered attempts.\n")
        print("| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) "
              "| threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA "
              "| stored bytes per enrolled image |")
        print("|---|---|---|---|---|---|---|---|")
        for p in bs:
            name, run = matcher_of(p, "big_eval_b_")
            r = stats(p)
            print(f"| {name} | {run or '-'} | {r['zt']} ({r['zt_lo']}-{r['zt_hi']}) "
                  f"| {100 * r['frr']:.1f}% ({100 * r['frr_lo']:.1f}-{100 * r['frr_hi']:.1f}%) "
                  f"| {r['kt']} (k={r['k']}) | {100 * r['frr_k']:.1f}% "
                  f"| {100 * r['set_mean']:.1f}% ({r['nsets']} sets) "
                  f"| {'-' if r['tbytes'] is None else round(r['tbytes'])} |")
    ov = [(matcher_of(p, "big_eval_b_"), overlap_frr(p)) for p in bs]
    ov = [(m, r) for m, r in ov if r]
    if ov:
        print("\n### FRR by overlap with the enrolled area\n")
        print("Registered genuine attempts at each matcher's zero-FA threshold, by the share of "
              "the probe patch covered by the enrolled patches (from the patch offsets; rotation "
              "between impressions is ignored).\n")
        bins = [f"{int(100 * lo)}-{int(100 * min(hi, 1))}%" for lo, hi in zip(OVERLAP_BINS, OVERLAP_BINS[1:])]
        print("| matcher | run | " + " | ".join(bins) + " |")
        print("|---|---|" + "---|" * len(bins))
        for (name, run), r in ov:
            print(f"| {name} | {run or '-'} | " + " | ".join(f"{100 * f:.1f}% (n={n})" for n, f in r) + " |")
    cs = sorted(glob.glob(os.path.join(out, "big_eval_c_*.npz")))
    if cs:
        print("\n## Strangers only (part C)\n")
        print("| set | matcher | run | attempts | max score | FA @ default | default threshold |")
        print("|---|---|---|---|---|---|---|")
        for p in cs:
            setname = os.path.basename(p)[len("big_eval_c_"):].split("_")[0]
            name, run = matcher_of(p, f"big_eval_c_{setname}_")
            m = matchers.get(name)
            M = np.load(p, allow_pickle=False)["M"]
            print(f"| {setname} | {name} | {run or '-'} | {M.size} | {int(M.max())} "
                  f"| {int((M >= m.default).sum())} | {m.default} |")


if __name__ == "__main__":
    main()
