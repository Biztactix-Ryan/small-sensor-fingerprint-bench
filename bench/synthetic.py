#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Synthetic probes for the safety metrics of docs/FINAL_RUN.md: no matcher
may accept any of them at its frozen threshold.

Every probe is a SIZExSIZE frame at sensor dpi, normalised with
public_sets.thirds() like the elan driver does with every frame, so it is
prepared exactly like a real probe patch (big_eval.patch_at minus its
background and ridge checks, which a driver does not have): the harness
passes it to MATCH.features_img() as is. Nothing is written to disk; every
frame is generated from a fixed seed (crc32 of its name), so the set is the
same on every machine.

Probe kinds, named "synth/<kind>...":
  blank, blank_n2      constant frame (thirds() makes it all 255); constant +
                       sensor-like noise (sigma 2, which thirds() stretches)
  gauss_s<s>           Gaussian noise, sigma s grey levels around 128
  uniform              uniform noise 0-255
  sp<f>                salt-and-pepper, f% of the pixels black or white
  grating_p<p>_o<a>    sine grating, period p px, orientation a degrees
  grating_n_p<p>_o<a>  the same with Gaussian noise (sigma 30) on top
  checker<c>           checkerboard, c px cells
  inv/, mirror/, inv_mirror/<finger>/<i>
                       an enrolled impression inverted (255 - p), mirrored
                       left-right, or both (derived(): from patches the
                       harness passes in)
Gratings: the ridge period at the sensor's 542 dpi is 10.67 px (median of
the 500 dpi calibration sets, 9.85 px, x 542 / 500 = 10.68; our own 0c3d
captures measure 10.67, docs/SCALING.md); PERIODS adds about +-20% around
it, all inside big_eval's ridge band (7-16 px), so these pass its
ridge_ratio check like real ridges. 8 orientations, 22.5 degrees apart.

Fixed-pattern pairs (pairs()): the Goodix 5125 failure, where the sensor's
own fixed pattern noise, the same in every frame, makes two different
fingers match. One pattern P is added to the enrolled stages of finger A and
to the probes of finger B before the driver normalisation; P alone (on a
blank frame) is a probe too. Patterns: "gauss" (white Gaussian, sigma s)
and "cols" (a per-column offset, sigma s, plus a per-row offset, sigma s/2,
like readout stripes). Strength s in grey levels on the 0-255 thirds()
patch: 16, 32, 64 (thirds() patches have a std of about 70, so a quarter,
half and about the full ridge contrast). The control is B vs A without P:
a matcher fails if it accepts B+P against A+P, and the score gain over the
control measures how much it matches the pattern. P alone against A+P shows
how far the pattern by itself carries; at s 64 the pattern is as strong as
the ridges, so read that strength as a stress level, not a sensor.

Adversarial frames (adversarial()): the frames that maximise keypoints
(Phase 3; 2 px checkerboards and salt-and-pepper reach the akaze/ftsift caps,
see the keypoint tables of US-FPR-2-3), with n different seeds so they can
fill every enrolled stage too.

How the harness calls it:
  for name, img in synthetic.probes(): f = MATCH.load(MATCH.features_img(img))
      -> best(f, tmpl) for every template, like a C stranger
  for name, img in synthetic.derived(enrolled): the same, where enrolled is
      [(finger, patch)] of the raw template patches of run_b
  for name, kind, s, stages, probes in synthetic.pairs([(fa, stages_a, fb, probes_b)]):
      enrol stages, score every probe against them (and the controls)
  synthetic.adversarial(kind, n) for the timing worst case
probes(), derived() (the first --synthetic-derived patches of each
template) and adversarial() as probes (--synthetic-adv seeds) are wired in:
big_eval.py --synthetic (part S); pairs() and adversarial frames as
enrolled stages are not yet.
"""
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import public_sets as pub  # noqa: E402

PERIOD = 10.67
PERIODS = (8.5, PERIOD, 13.0)
ORIENTATIONS = tuple(22.5 * i for i in range(8))
CHECKERS = (1, 2, 3, 4, 6, 8, 12, 16)
STRENGTHS = (16, 32, 64)
PATTERNS = ("gauss", "cols")
# keypoint-maximising kinds for adversarial()
ADVERSARIAL = ("checker2", "sp50", "gauss_s40", "uniform")


def _rng(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def _u8(f):
    return np.uint8(np.clip(np.rint(f), 0, 255))


def _grid():
    return np.indices((pub.SIZE, pub.SIZE), dtype=np.float64)


def _num(x):
    return f"{x:g}".replace(".", "_") if "." in f"{x:g}" else f"{x:g}"


def frame(kind):
    """The raw (not yet normalised) frame of a data-independent probe kind,
    e.g. "gauss_s40", "sp50#3" (#n: another seed of the same kind)."""
    S = pub.SIZE
    r = _rng(kind)
    base = kind.split("#")[0]
    yy, xx = _grid()
    if base == "blank":
        return np.full((S, S), 128, np.uint8)
    if base == "blank_n2":
        return _u8(128 + 2 * r.standard_normal((S, S)))
    if base.startswith("gauss_s"):
        return _u8(128 + float(base[7:]) * r.standard_normal((S, S)))
    if base == "uniform":
        return np.uint8(r.integers(0, 256, (S, S)))
    if base.startswith("sp"):
        im = np.full((S, S), 128, np.uint8)
        m = r.random((S, S)) < int(base[2:]) / 100
        im[m] = np.where(r.random(int(m.sum())) < 0.5, 0, 255)
        return im
    if base.startswith("checker"):
        c = int(base[7:])
        return np.uint8(255 * ((yy // c + xx // c) % 2))
    if base.startswith("grating"):
        noisy = base.startswith("grating_n_")
        p, o = base.split("_p")[1].split("_o")
        p, t = float(p.replace("_", ".")), np.radians(float(o.replace("_", ".")))
        g = 128 + (90 if noisy else 100) * np.sin(2 * np.pi * (xx * np.cos(t) + yy * np.sin(t)) / p)
        return _u8(g + (30 * r.standard_normal((S, S)) if noisy else 0))
    raise ValueError(f"unknown synthetic kind {kind}")


def kinds():
    out = ["blank", "blank_n2", "gauss_s10", "gauss_s40", "uniform", "sp10", "sp50"]
    out += [f"grating_p{_num(p)}_o{_num(o)}" for p in PERIODS for o in ORIENTATIONS]
    out += [f"grating_n_p{_num(PERIOD)}_o{_num(o)}" for o in ORIENTATIONS]
    out += [f"checker{c}" for c in CHECKERS]
    return out


def probes():
    """[(name, frame)] of every data-independent probe, normalised."""
    return [("synth/" + k, pub.thirds(frame(k))) for k in kinds()]


def derived(enrolled):
    """[(name, frame)]: each enrolled patch, given as [(finger, patch)] at
    sensor dpi, inverted, mirrored and both, normalised again."""
    out, seen = [], {}
    for finger, p in enrolled:
        i = seen[finger] = seen.get(finger, -1) + 1
        p = np.asarray(p, np.uint8)
        for kind, q in (("inv", 255 - p), ("mirror", p[:, ::-1]), ("inv_mirror", 255 - p[:, ::-1])):
            out.append((f"synth/{kind}/{finger}/{i}", pub.thirds(np.ascontiguousarray(q))))
    return out


def pattern(kind, strength, seed=0):
    """Zero-mean fixed pattern noise, float SIZExSIZE."""
    S = pub.SIZE
    r = _rng(f"fpn/{kind}/{strength}/{seed}")
    if kind == "gauss":
        return strength * r.standard_normal((S, S))
    if kind == "cols":
        return (strength * r.standard_normal((1, S)) + strength / 2 * r.standard_normal((S, 1))
                + np.zeros((S, S)))
    raise ValueError(f"unknown pattern {kind}")


def with_pattern(p, P):
    return pub.thirds(_u8(np.asarray(p, np.float64) + P))


def pairs(fingers, kinds=PATTERNS, strengths=STRENGTHS):
    """Fixed-pattern pair test. @fingers: [(finger_a, stages_a, finger_b,
    probes_b)] with different fingers a and b, patches at sensor dpi. Yields
    (name, kind, strength, stages, probes): finger a's stages and finger b's
    probes, both with the same pattern added, then the pattern alone as the
    last probe. The same pattern for every pair of one kind and strength,
    like one sensor."""
    for kind in kinds:
        for s in strengths:
            P = pattern(kind, s)
            for fa, sa, fb, pb in fingers:
                yield (f"synth/fpn_{kind}_s{s}/{fa}+{fb}", kind, s, [with_pattern(x, P) for x in sa],
                       [with_pattern(x, P) for x in pb] + [with_pattern(np.full(P.shape, 128.0), P)])


def adversarial(kind, n):
    """@n normalised frames of a keypoint-maximising @kind (ADVERSARIAL),
    each with its own seed (checkerboards shift by one cell instead), to use
    as the probe and as every enrolled stage."""
    if kind.startswith("checker"):
        f = frame(kind)
        c = int(kind[7:])
        return [(f"synth/adv/{kind}#{i}", pub.thirds(np.roll(f, (i % 2) * c, axis=1))) for i in range(n)]
    return [(f"synth/adv/{kind}#{i}", pub.thirds(frame(f"{kind}#{i}"))) for i in range(n)]


if __name__ == "__main__":
    ps = probes()
    print(f"{len(ps)} data-independent probes")
    for name, im in ps:
        print(f"  {name:28s} mean {im.mean():6.1f} std {im.std():5.1f}")
