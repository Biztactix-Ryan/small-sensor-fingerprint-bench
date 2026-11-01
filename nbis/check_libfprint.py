# SPDX-License-Identifier: LGPL-2.1-or-later
"""Checks the nbis matcher's scores against libfprint's own NBIS path.

Takes one big_eval patch from each of the first impressions of a few fingers
of each set, scores every ordered pair with the nbis matcher and with
build/check_libfprint (./build.sh check), and compares. Patches go to the
harness through a pipe; nothing is written. NBIS finds a handful of minutiae
in a 96x96 patch and scores nearly every pair 0, so --full checks on the
whole impressions (at sensor dpi) as well, where scores are not 0.

  FPBENCH_DATA=<datasets> python3 nbis/check_libfprint.py [--sets a,b]
      [--fingers 4] [--impressions 3] [--full]
"""
import argparse
import os
import random
import struct
import subprocess
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bench"))
import big_eval  # noqa: E402
import matchers  # noqa: E402
import public_sets as pub  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--sets", default="fvs,neuro_uareu")
ap.add_argument("--fingers", type=int, default=4, help="per set")
ap.add_argument("--impressions", type=int, default=3, help="per finger")
ap.add_argument("--full", action="store_true", help="whole impressions instead of patches")
a = ap.parse_args()

by = defaultdict(list)
for s, f, imp, p in sorted(pub.index()):
    if s in a.sets.split(","):
        by[(s, f)].append(p)
rng = random.Random(1)
patches = []
for s in a.sets.split(","):
    for (_, f) in [k for k in by if k[0] == s][:a.fingers]:
        for p in by[(s, f)][:a.impressions]:
            img = big_eval.load_scaled(p, pub.SETS[s][0])
            if img is not None:
                patches += [img] if a.full else big_eval.jittered(img, 1, 20, rng)

m = matchers.get("nbis")
feats = [m.load(m.features_img(p)) for p in patches]
inp = b"".join(struct.pack("ii", p.shape[1], p.shape[0]) + np.ascontiguousarray(p, np.uint8).tobytes()
              for p in patches)
out = subprocess.run([os.path.join(HERE, "build", "check_libfprint")], input=inp,
                     capture_output=True, check=True).stdout.decode()
same = diff = nonzero = 0
for line in out.splitlines():
    w = line.split()
    if w[0] != "score":
        continue
    i, j, ref = int(w[1]), int(w[2]), max(0, int(w[3]))
    got = m.score(feats[i], feats[j])
    same, diff = same + (got == ref), diff + (got != ref)
    nonzero += ref > 0
    if got != ref:
        print(f"differs: {i} {j} libfprint {ref} nbis {got}")
print(f"{len(patches)} {'impressions' if a.full else 'patches'}, {same + diff} pairs ({nonzero} with a nonzero score): "
      f"{same} equal, {diff} differ; max score {max(m.score(x, y) for x in feats for y in feats if x is not y)}")
