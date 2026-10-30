#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Markdown summary of big_eval.py score matrices.

For every part B matrix (big_eval_b_<matcher>*.npz): impostor maximum, the
lowest threshold without false accepts and the genuine false-reject rate there,
the false accepts at the matcher's default threshold, and the false-reject
rate per set. For part C matrices (big_eval_c_<set>_<matcher>*.npz): stranger
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
    d = np.load(path, allow_pickle=True)
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
    cs = sorted(glob.glob(os.path.join(out, "big_eval_c_*.npz")))
    if cs:
        print("\n## Strangers only (part C)\n")
        print("| set | matcher | run | attempts | max score | FA @ default | default threshold |")
        print("|---|---|---|---|---|---|---|")
        for p in cs:
            setname = os.path.basename(p)[len("big_eval_c_"):].split("_")[0]
            name, run = matcher_of(p, f"big_eval_c_{setname}_")
            m = matchers.get(name)
            M = np.load(p, allow_pickle=True)["M"]
            print(f"| {setname} | {name} | {run or '-'} | {M.size} | {int(M.max())} "
                  f"| {int((M >= m.default).sum())} | {m.default} |")


if __name__ == "__main__":
    main()
