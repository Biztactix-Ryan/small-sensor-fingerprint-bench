# small-sensor-fingerprint-bench

Benchmark for fingerprint matchers on small area sensors (96×96 px), built to
evaluate keypoint matchers for [libfprint](https://gitlab.freedesktop.org/libfprint/libfprint),
in particular SIGFM from merge request
[!530](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/530),
for the Elan 04f3:0c3d (96×96, ~542 dpi) and similar sensors.

Public fingerprint datasets are rescaled to the sensor's resolution and cut
into sensor-sized patches ([docs/SCALING.md](docs/SCALING.md)). On those, the
benchmark simulates enrollment (10 stages, a finger placed slightly
differently each time) and verification against every enrolled finger, and
reports false accepts and false rejects per matcher. All matchers see exactly
the same patches. 20 enroll/verify sets with 4,813 fingers and 2 stranger-only
sets with 7,500 more are listed in [docs/DATASETS.md](docs/DATASETS.md).

- **Part B**: enroll/verify on fingers with several impressions: genuine and
  impostor attempts. Runs: v1 (16 sets, 568 fingers, 1.44 M impostor
  attempts), v2 (v1 + Tsinghua, 880 fingers, 2.58 M), UNSW 2D (1,452
  fingers, 8.32 M).
- **Part C**: strangers only (SOCOFing, Family) against the enrolled fingers
  of part B.
- **Real sensor** (`bench/cross_finger.py`): genuine and impostor scores on
  real captures of one person's fingers. Only scores are published.
- **Speed** (`bench/timing.py`): single-threaded extraction, match, verify and
  identify times.

### Data at a glance

| data | people | fingers | prints | used for |
|---|---|---|---|---|
| FVC2000/2002/2004 B sets (12 sets, 3 synthetic) | not stated | 120 | 960 | enroll/verify |
| Neurotechnology CrossMatch + U.are.U samples | 9 | 116 (same fingers on 2 sensors) | 928 | enroll/verify |
| FVS | not stated | 21 | 168 | enroll/verify |
| NIST MINEX III validation | 50 | 400 | 797 | enroll/verify |
| Tsinghua Distorted | not stated | 320 recordings | 640 | enroll/verify |
| UNSW 2D | 150 | 1,500 | 5,975 | enroll/verify |
| PolyU contact-based, 2 sessions | not stated (336 "clients/fingers") | 336 | 2,976 | enroll/verify |
| NIST SD 302 plain (302b, c, d; up to 7 devices per finger) | 200 | 2,000 | 10,584 | enroll/verify |
| **enroll/verify total** | | **4,813** | **23,028** | |
| SOCOFing | 600 | 6,000 | 6,000 | strangers only |
| Family Fingerprint Dataset | 300 (100 families) | 1,500 | 1,500 | strangers only |
| **public total** | **at least 1,309** | **12,313** | **30,528** | |
| Elan 04f3:0c3d captures (ours, not published) | 1 | 10 | 301 | real sensor check |

Details, sources and terms: [docs/DATASETS.md](docs/DATASETS.md). Not every
set has been run yet: v1 used the FVC, Neurotechnology, FVS and MINEX sets
(16 sets, 568 fingers after
quality filters), v2 added Tsinghua, UNSW 2D ran on its own, and PolyU and
NIST SD 302 have had subset smoke tests so far.

Matchers are compared at their own **zero-false-accept threshold** (the lowest
threshold without a false accept in the run; range = bootstrap over fingers,
5th–95th percentile) and by the false-reject rate (FRR) of genuine attempts
whose probe could be registered to the enrollment, also at a fixed
false-accept rate of 1e-5. Scores are only comparable within a matcher.

## Findings

| | v1 threshold | v1 FRR @ FA 1e-5 | v2 threshold | v2 FRR @ FA 1e-5 | UNSW threshold | UNSW FRR @ FA 1e-5 | bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| `sigfm` (!530) | 28 (19–28) | 15.1% | 29 (24–29) | 21.9% | 101 (53–101) | 3.9% | 141,554 |
| `sigfm_fix` | 63 (28–63) | 15.5% | 63 (32–63) | 21.8% | 134 (84–134) | 3.9% | 141,554 |
| `ours` (SIFT + RANSAC) | 9 (8–9) | 14.4% | 9 (8–9) | 18.8% | 10 (9–10) | 5.1% | — |
| `ftsift_strict` (all C) | 8 (7–8) | 13.3% | | | | | 67,121 |
| `akaze` | 9 (7–9) | **11.2%** | 9 (8–9) | **18.1%** | 13 (9–13) | **3.8%** | 19,848 |

1. **SIGFM's threshold isn't a constant.** The shipped 24 accepts strangers
   on every set (1 in v1, 5 in v2, 72 in UNSW); the safe value depends on the
   sensor's images (~28 contact, ~100 optical) and on the number of enrolled
   images (13 to 26 at FA 1e-5 for 5 to 25 images). With the ordering fix it
   is set by single impostor pairs and moves between 28 and 63.
2. **An inlier count (matches agreeing on one rigid transform) has a stable
   threshold:** 8–10 on every set and for 5–25 enrolled images. In 21 M
   stranger attempts over all runs it never reached 10.
3. **Accuracy is close between SIGFM and SIFT inlier counts;** AKAZE
   descriptors are better on all three public runs, most of all averaged per
   set (30% vs 40% FRR on v1, 31% vs 41% on v2) and on hard data
   (cross-session and cross-device subsets below).
4. **But on the real Elan 0c3d, AKAZE rejects more presses** (23 of 201,
   against 14 for SIGFM and `ftsift_strict`) at the same threshold: its
   scores, genuine and impostor, run lower on this sensor's images. Whether a
   per-sensor threshold or tuning fixes that is open.
5. **SIFT without OpenCV works:** the FocalTech FT9366 C SIFT (LGPL) with
   strict matching (mutual matches, ±45°) and our C matcher beats the OpenCV
   pipeline on v1.
6. **Compact descriptors:** ternary codes (32 bytes per keypoint, 3.4×
   smaller than SIFT's) match AKAZE's accuracy on v1 with their own threshold
   of 13.

## Matchers

**Going forward**, three matchers:

| Name | What |
|---|---|
| `sigfm` | SIGFM as in !530 (commit `bc986621`), built from its sources by `sigfm/build.sh`: SIFT keypoints on the raw image, ratio-test matches, score = number of pairs of match pairs whose length and angle agree. The reference |
| `ftsift_strict` | the inlier count, all in C: 2× upscale + CLAHE, SIFT from a libfprint fork's FocalTech FT9366 driver (LGPL, `csift/build.sh`), ratio-test matches that are each other's nearest neighbours, deterministic search for the rotation (±45°) + translation the most matches agree with; score = agreeing matches |
| `akaze` | the inlier count on OpenCV AKAZE keypoints and binary descriptors (Hamming distance), with OpenCV RANSAC. The candidate for a C port |

**Retired** (results kept; still runnable):

| Name | What | Why retired |
|---|---|---|
| `sigfm_fix` | SIGFM with Sergey Subbotin's ordering fix + 176 best matches | same accuracy as `sigfm`, threshold less stable |
| `sigfm_pre` | SIGFM on upscaled + CLAHE images | raises impostor scores as much as genuine ones |
| `ours`, `ours_raw` | inlier count, OpenCV SIFT + RANSAC | not reproducible (randomized); `ours_strict` equals it |
| `ours_det`, `ours_strict`, `ours_det2` | deterministic search; `strict` adds mutual matches + ±45°; `det2` least squares refits | superseded by `ftsift_strict`; the refit changed nothing |
| `vlsift`, `ftsift`, `vlsift_strict` | C SIFT from VLFeat (BSD) or FocalTech | `ftsift_strict` equals `vlsift_strict` and is LGPL |
| `q_pca40`, `q_bin128`, `q_bin256`, `q_tern128` | compact SIFT descriptor codes, fit on the stranger sets (`bench/fit_quant.py`) | storage experiment; `q_tern128` worth revisiting for templates |
| `union` | ArcticLampyrid's union-of-inliers score from !530 | FRR more than doubles |
| `orb`, `brisk` (+ `_raw`) | binary descriptors | clearly worse than SIFT and AKAZE |

The deterministic matching is in our libfprint branch as plain C
(`fpi-keypoint-match.c`, with euclidean, Hamming and ternary descriptors) and
gives scores identical to the Python code here. When it is built as
`kpm/libkpm.so` (or `FPBENCH_KPM_LIB`), the matchers using it score through it.

## Results

Logs, score matrices and generated summaries (`bench/summarize.py`) in
[results/](results/).

### v1: all matchers

16 sets, 568 fingers, 1,440,034 impostor attempts. `sigfm*`, `ours` and
`ours_raw` from [results/v1](results/v1/SUMMARY.md), the rest from
[results/v1-variants](results/v1-variants/SUMMARY.md) (OpenCV 4.10; its `ours`
baseline reproduces v1: threshold 9, FRR 18.6%, 14.5% at FA 1e-5).

| matcher | zero-FA threshold (range) | FRR there | FRR @ FA 1e-5 | per-set average FRR | bytes per enrolled image |
|---|---|---|---|---|---|
| `sigfm` | 28 (19–28) | 17.2% | 15.1% | 36.4% | |
| `sigfm_fix` | 63 (28–63) | 18.4% | 15.5% | 39.4% | |
| `sigfm_pre` | 91 (58–91) | 17.5% | 15.1% | 38.7% | |
| `ours_raw` | 8 (7–8) | 18.9% | 16.7% | 40.0% | |
| `ours` | 9 (8–9) | 18.6% | 14.4% | 40.7% | |
| `ours_det` | 10 (8–10) | 20.0% | 16.2% | 43.3% | 57,297 |
| `ours_det2` | 10 (8–10) | 20.0% | 16.1% | 43.3% | 57,297 |
| `ours_strict` | 9 (7–9) | 18.5% | 14.5% | 40.3% | 57,297 |
| `vlsift` | 11 (10–11) | 16.4% | 14.4% | 36.4% | 66,963 |
| `vlsift_strict` | 10 (8–10) | 15.7% | 13.3% | 35.6% | 66,963 |
| `ftsift` | 14 (10–14) | 23.8% | 17.2% | 48.4% | 67,121 |
| `ftsift_strict` | 8 (7–8) | 15.0% | 13.3% | 34.8% | 67,121 |
| `q_pca40` | 10 (9–10) | 19.8% | 15.4% | 42.1% | 20,222 |
| `q_bin256` | 9 (7–9) | 22.3% | 16.7% | 46.3% | 16,852 |
| `q_bin128` | 9 (8–9) | 22.6% | 17.5% | 48.2% | 10,111 |
| `q_tern128` | 13 (12–13) | 13.4% | 11.3% | 32.9% | 16,852 |
| `akaze` | 9 (7–9) | 13.4% | 11.2% | 29.8% | |
| `orb` | 13 (12–13) | 25.1% | 22.5% | 45.4% | |
| `union` | 1221 (1026–1221) | 40.7% | 33.0% | 65.3% | |

- The deterministic search alone (`ours_det`) costs ~1.5 points against
  RANSAC; mutual matches + ±45° (`ours_strict`) win it back; a least squares
  refit (`ours_det2`) changes nothing.
- The FocalTech SIFT is weak with plain matching (strangers up to 13) and
  among the best with strict matching (strangers up to 7).
- The pooled FRR is dominated by the clean sets (Neurotechnology, FVS); the
  per-set average weighs every set equally.

### Enrollment depth (v1)

[results/enrollment-depth](results/enrollment-depth/SUMMARY.md).

| enrolled images | 5 | 10 | 15 | 25 |
|---|---|---|---|---|
| `ours_det` threshold @ FA 1e-5 | 7 | 8 | 8 | 8 |
| `ours_det` FRR @ FA 1e-5 | 17.3% | 16.2% | 14.2% | 12.7% |
| `sigfm_fix` threshold @ FA 1e-5 | 13 | 21 | 22 | 26 |
| `sigfm_fix` FRR @ FA 1e-5 | 17.4% | 15.5% | 13.9% | 12.0% |

More enrolled images help both equally; SIGFM's threshold has to double from
5 to 25 images to stay as safe, the inlier count's doesn't move.

### v2 and strangers

[results/v2](results/v2/SUMMARY.md). v2 adds Tsinghua (320 fingers, one
deliberately distorted impression) to v1.

| matcher | zero-FA threshold | FRR there | FRR @ FA 1e-5 | per-set average | SOCOFing strangers (10.3 M): max, FA @ default | Family strangers (656 k): max |
|---|---|---|---|---|---|---|
| `sigfm` | 29 (24–29) | 24.6% | 21.9% | 38.3% | 15, 0 @ 24 | 2 |
| `sigfm_fix` | 63 (32–63) | 26.1% | 21.8% | 40.2% | 29, 1 @ 24 | 10 |
| `ours` | 9 (8–9) | 24.4% | 18.8% | 40.8% | 9, 0 @ 10 | 6 |
| `akaze` | 9 (8–9) | 21.1% | 18.1% | 31.0% | | |

### UNSW 2D (optical, 1,452 fingers)

[results/unsw](results/unsw/SUMMARY.md). `ours` is from a run that still
included 25 duplicated impressions; reruns of the SIGFM variants without
them changed FRR by 0.1 point at most.

| matcher | max impostor | FA @ default | zero-FA threshold | FRR there | FRR @ FA 1e-5 |
|---|---|---|---|---|---|
| `sigfm` | 100 | 72 @ 24 | 101 (53–101) | 6.2% | 3.9% |
| `sigfm_fix` | 133 | 236 @ 24 | 134 (84–134) | 6.2% | 3.9% |
| `ours` | 9 | 0 @ 10 | 10 (9–10) | 6.8% | 5.1% |
| `akaze` | 12 (next: 9) | 1 @ 10 | 13 (9–13) | 6.9% | 3.8% |

### New sets: smoke test on subsets

[results/new-sets-smoke](results/new-sets-smoke/SUMMARY.md): 56 PolyU fingers
enrolled in one session and verified 2–24 months later, 86 NIST SD 302
fingers enrolled and verified on different devices; ~30 k impostor attempts
each, so thresholds aren't comparable with the full runs. FRR at each
matcher's zero-FA threshold:

| matcher | PolyU, cross-session | NIST, cross-device |
|---|---|---|
| `sigfm` | 52.7% | 43.0% |
| `ours_strict` | 73.0% | 25.6% |
| `q_tern128` | 34.1% | 16.3% |
| `akaze` | **26.5%** | **14.0%** |

SIFT-based matching degrades most on these harder conditions. Only 23% of
NIST's cross-device impressions could be registered to their enrollment
impression, to be looked into before a full NIST run.

### Real sensor: Elan 04f3:0c3d, one person

Ten fingers, 301 presses in five sessions (normal skin, freshly washed hands,
dry skin at night). Each finger is enrolled from 10 presses of one session;
impostors are the other nine fingers of the same person (2,709 attempts),
genuine attempts the presses of the other sessions (201).
`bench/cross_finger.py`. One person, so a check of the real sensor's images
rather than a false-accept estimate.

| matcher | impostor max | FA | genuine rejected |
|---|---|---|---|
| `sigfm` @ 24 | 8 | 0 | 14 |
| `ftsift_strict` @ 10 | 5 | 0 | 14 |
| `ours_det` @ 10 | 7 | 0 | 17 |
| `q_tern128` @ 13 | 10 | 0 | 10 |
| `akaze` @ 10 | 4 | 0 | 23 |

- No sign of fixed-pattern matches (impostor scores far above the rest, as
  reported for some Goodix sensors on !530); the elan driver subtracts a
  background frame.
- Genuine rejections are mostly thumbs, much larger than the 96×96 window: a
  press often lands on skin that wasn't enrolled.
- Six captures first looked like false accepts; all were labelling mistakes
  during collection (the first presses after a finger change made with the
  previous finger) and are excluded. The capture tool now waits for a key at
  each finger change.
- An earlier table on the first 205 presses with all matchers is in the git
  history.

### Speed (preliminary)

Single thread, Intel i7-13700KF, real 96×96 captures, 20 enrolled images;
measured while the benchmark ran on all cores, so upper bounds. Milliseconds:

| matcher | extract | verify (extract + 20 matches) | identify over 10 fingers |
|---|---|---|---|
| `sigfm` | 6 | 23 | 198 |
| `akaze` | 7 | 28 | 232 |
| `ours_strict` | 15 | 29 | 310 |
| `ftsift` | 94 | 137 | 722 |

Every matcher verifies in well under a second. The FocalTech SIFT extracts
keypoints ~6× slower than OpenCV's (not vectorized), which still fits.

## Next

- AKAZE in C (nonlinear diffusion scale space, MLDB descriptors) for the
  deterministic C matcher, and why AKAZE scores lower on the Elan 0c3d.
- Full PolyU and NIST SD 302 runs of the three matchers, after looking into
  NIST's low registration rate.
- More real-sensor sessions and people.
- The chosen matcher in libfprint, scored through its virtual image driver
  (as requested on !530).

## Running it

```sh
# Python 3 with numpy and OpenCV >= 4.4; g++, pkg-config, OpenCV headers, git
sigfm/build.sh                       # fetches !530's SIGFM at the pinned commit and builds it
# get the datasets into data/, see docs/DATASETS.md
python3 bench/public_sets.py --data data              # what was found
python3 bench/big_eval.py --data data --matcher sigfm --out results/mine
python3 bench/big_eval.py --data data --matcher ours --strangers socofing,family --out results/mine
python3 bench/summarize.py results/mine
csift/build.sh                       # optional: the C SIFT matchers vlsift, ftsift
python3 bench/cross_finger.py --captures MY_CAPTURES --enroll-session SESSION --matcher ours
python3 bench/timing.py --captures MY_CAPTURES
```

Each run of part B takes 15–45 minutes on 22 cores (about 1.5 M matcher
comparisons); part C is several times that. `bench/bench_watch.sh` can watch
a queue of runs for errors and stalls.

If `import cv2` fails with a NumPy ABI error, a pip NumPy 2 in `~/.local`
is shadowing the distribution's NumPy 1 that the distribution's OpenCV was
built against; run with `PYTHONNOUSERSITE=1`.

For another sensor, measure its resolution first
([docs/SCALING.md](docs/SCALING.md)) and set `FPBENCH_SENSOR_DPI`.

## Fidelity

- `sigfm*` call the !530 C++ code through its C API (via ctypes), including a
  serialize/deserialize round trip like stored prints: 0 score differences
  in 1,260 pairs against a standalone C++ build.
- `ours` gives the same scores as the C++ (OpenCV) implementation in our
  first libfprint branch.
- `ours` and `ours_raw` are not bit-reproducible: OpenCV's RANSAC is
  randomized and multithreaded. Two runs of `ours` differed in 1,028 of
  1.53 M scores, by a few points each, with the same summary. A rerun of
  `sigfm` reproduced its summary exactly.
- `ours_det` and the matchers built on it are deterministic, and the Python
  code and our plain C implementation give identical scores: 7,080 real
  capture pairs, and identical inlier sets on 1,560. The C upscale + CLAHE is
  byte-identical to OpenCV 4.6 (412 images) and 4.10 (285 images).

## Disclosure

This benchmark was written with AI assistance (Claude). Every result was
produced by the code in this repository and can be reproduced with it.

## License

LGPL-2.1-or-later, like libfprint and SIGFM. The SIGFM sources are fetched
from libfprint, not included.
