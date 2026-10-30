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
the same patches.

- **Part B**: enroll/verify on fingers with several impressions: genuine and
  impostor attempts. v1: 568 fingers, 1.44 M impostor attempts.
- **Part C**: strangers only, from sets with one impression per finger
  (SOCOFing, Family), against the enrolled fingers of part B.
- **Part A** (optional): public patches against real enrollments of your own
  sensor. Our results are published; our captures are not.

## Matchers

| Name | What |
|---|---|
| `ours_det`, `ours_strict` | `ours` with a deterministic transform search; `strict` adds mutual nearest neighbours and a 45° rotation limit |
| `union` | ArcticLampyrid's overlap score from !530: union of inliers over all enrolled images, normalized by keypoint count |
| `orb`, `akaze`, `brisk` (+ `_raw`) | `ours` with binary descriptors instead of SIFT |
| `sigfm` | SIGFM as in libfprint !530 (commit `bc986621`), built from its sources by `sigfm/build.sh` |
| `sigfm_fix` | the same with the fix proposed on !530 by Sergey Subbotin: full ordering of matches (the original `operator<` only compares `y`) and keeping the 176 best matches |
| `sigfm_pre` | unmodified SIGFM on images upscaled 2× and CLAHE-equalized |
| `ours_raw` | SIFT + RANSAC: matches must agree on one rigid transform (scale 0.85–1.15); score = number of agreeing matches |
| `ours` | the same with 2× upscale + CLAHE |

Scores are only comparable within a matcher, so matchers are compared at
their own **zero-false-accept threshold**: the lowest threshold without any
false accept in the run, and the false-reject rate there.

## Results

See [results/](results/) for the logs, the score matrices and the generated
summaries (`bench/summarize.py`).

### v1: 16 sets, 568 fingers, 1,440,034 impostor attempts

Full summary: [results/v1/SUMMARY.md](results/v1/SUMMARY.md).

| matcher | impostor max | FA @ 24 (SIGFM default) | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA |
|---|---|---|---|---|---|
| `sigfm` | 27 | 1 | 28 | 17.2% | 51.8% |
| `sigfm_fix` | 62 | 7 | 63 | 18.4% | 52.8% |
| `sigfm_pre` | 90 | 145 | 91 | 17.5% | 52.1% |
| `ours_raw` | 7 | — | 8 | 18.9% | 53.1% |
| `ours` | 8 | — | 9 | 18.6% | 53.0% |

How stable these are (bootstrap over fingers, 5th–95th percentile), the FRR at
a fixed false-accept rate of 1e-5 (≤ 14 false accepts), and the registered FRR
averaged per set (11 sets with ≥ 20 registered attempts):

| matcher | zero-FA threshold (range) | FRR registered (range) | FRR @ FA 1e-5 | per-set average FRR |
|---|---|---|---|---|
| `sigfm` | 28 (19–28) | 17.2% (13.8–20.2%) | 15.1% | 36.4% |
| `sigfm_fix` | 63 (28–63) | 18.4% (14.1–20.9%) | 15.5% | 39.4% |
| `sigfm_pre` | 91 (58–91) | 17.5% (13.5–20.1%) | 15.1% | 38.7% |
| `ours_raw` | 8 (7–8) | 18.9% (15.3–22.4%) | 16.7% | 40.0% |
| `ours` | 9 (8–9) | 18.6% (13.8–20.5%) | 14.4% | 40.7% |

- **Accuracy is a tie.** The FRR ranges overlap completely.
- **The threshold is where they differ.** SIGFM's default of 24 lets through
  one stranger as is, and seven with the ordering fix. `sigfm_fix`'s
  zero-FA threshold of 63 is set by a single impostor pair and moves between
  28 and 63 when fingers are resampled. The inlier-count score of `ours`
  stays at 8–9, which is what a per-driver constant needs.
- **Preprocessing doesn't help SIGFM:** upscale + CLAHE raises impostor
  scores as much as genuine ones.
- **The pooled FRR is dominated by the clean sets.** Neurotechnology and FVS
  are 72% of the registered genuine attempts; averaged per set, FRR is
  36–41%. Per-set figures are in [results/v1/SUMMARY.md](results/v1/SUMMARY.md).
- "all" includes genuine probes that don't overlap the enrolled area, so it is
  dominated by placement, not the matcher.

### v2 and UNSW 2D (preliminary, runs in progress)

**v2** adds Tsinghua (320 fingers; the second impression is deliberately
distorted) to the v1 sets: 880 fingers, 2,576,466 impostor attempts.
**UNSW 2D** is a separate run on 1,452 fingers of a 150-person optical
dataset, 8,347,595 impostor attempts. Summaries:
[results/v2](results/v2/SUMMARY.md), [results/unsw-preliminary](results/unsw-preliminary/SUMMARY.md).

| run | matcher | impostor max | FA @ default | zero-FA threshold (range) | FRR registered there | FRR @ FA 1e-5 |
|---|---|---|---|---|---|---|
| v2 | `sigfm` | 28 | 5 @ 24 | 29 (24–29) | 24.6% | 21.9% |
| v2 | `sigfm_fix` | 62 | 12 @ 24 | 63 (32–63) | 26.1% | 21.8% |
| v2 | `ours` | 8 | 0 @ 10 | 9 (8–9) | 24.4% | 18.8% |
| UNSW | `sigfm` | 100 | 72 @ 24 | 101 (53–101) | 6.2% | 3.8% |
| UNSW | `sigfm_fix` | 133 | 236 @ 24 | 134 (84–134) | 6.1% | 3.8% |
| UNSW | `ours` | 9 | 0 @ 10 | 10 (9–10) | 6.8% | 5.1% |

Strangers only, against the 880 v2 enrollments: SOCOFing (10,333,840
attempts) max 15 for `sigfm`, 29 for `sigfm_fix` (1 FA @ 24); Family
(655,600) max 2 and 10. `ours` on these is running.

- **One constant threshold works for the inlier count:** its zero-FA
  threshold is 8–9 on v1 and v2 and 9–10 on UNSW, and the default of 10 has
  no false accept in any of them (2.58 M impostor attempts in v2, 8.35 M
  in UNSW).
  SIGFM's follows the data: ~28 on the contact sensor sets, ~100 on UNSW's
  optical images.
- UNSW's genuine side is much easier (clean optical impressions): 6–7% FRR.
  There SIGFM is a little better at a fixed false-accept rate (3.8% vs
  5.1%).
- Pending: `ours` on the stranger sets; v1 runs of `ours_det`,
  `ours_strict`, `union`, `orb`, `akaze` and the C SIFTs; the enrollment
  depth sweep (5–25 stages); a UNSW rerun without duplicate impressions
  (the current UNSW results include subject 6's duplicated impressions,
  about 40 of 5,875 genuine probes, so FRR may be understated by up to
  0.7 points).
- The v2 logs predate excluding Tsinghua-vs-Tsinghua impostors (see
  [docs/DATASETS.md](docs/DATASETS.md)): their impostor lines include those
  same-finger pairs. The summaries recompute impostors and are what counts.

### Real sensor: Elan 04f3:0c3d, one person

Ten fingers, 205 presses in four sessions (normal skin, freshly washed
hands). Each finger is enrolled from 10 presses of one session; impostors are
the other nine fingers of the same person (1,845 attempts), genuine attempts
the presses of the other sessions (105). `bench/cross_finger.py`, at each
matcher's default threshold. One person, so a sanity check of the real
sensor's images rather than a false-accept estimate.

| matcher | impostor max | FA @ default | genuine rejected @ default |
|---|---|---|---|
| `sigfm` | 8 | 0 @ 24 | 9 |
| `sigfm_fix` | 8 | 0 @ 24 | 8 |
| `ours` | 5 | 0 @ 10 | 11 |
| `ours_raw` | 4 | 0 @ 10 | 11 |
| `ours_det` | 7 | 0 @ 10 | 11 |
| `ours_strict` | 5 | 0 @ 10 | 11 |
| `vlsift` | 6 | 0 @ 10 | 8 |
| `ftsift` | 7 | 0 @ 10 | 9 |
| `akaze` | 4 | 0 @ 10 | 12 |
| `orb` | 9 | 0 @ 10 | 16 |
| `orb_raw` | 8 | 0 @ 10 | 31 |
| `brisk` | 8 | 0 @ 10 | 30 |
| `union` | 860 | 0 @ 1000 | 16 |

- No sign of fixed-pattern matches (impostor scores far above the rest, as
  reported for some Goodix sensors on !530); the elan driver subtracts a
  background frame.
- Genuine rejections are mostly thumbs (all of `sigfm`'s and `sigfm_fix`'s,
  9 of 11 for `ours`), much larger than the 96x96 window: a press often
  lands on skin that wasn't enrolled.
- Two captures first looked like false accepts; both were labelling
  mistakes during collection (wrong finger pressed) and are excluded.
- The C SIFT implementations (`vlsift`, `ftsift`) do at least as well as
  OpenCV's here.


## Running it

```sh
# Python 3 with numpy and OpenCV >= 4.4; g++, pkg-config, OpenCV headers, git
sigfm/build.sh                       # fetches !530's SIGFM at the pinned commit and builds it
# get the datasets into data/, see docs/DATASETS.md
python3 bench/public_sets.py --data data              # what was found
python3 bench/big_eval.py --data data --matcher sigfm --out results/mine
python3 bench/big_eval.py --data data --matcher ours --strangers socofing,family --out results/mine
python3 bench/summarize.py results/mine
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
- `ours` gives the same scores as the C implementation in our libfprint
  branch.
- `ours*` are not bit-reproducible: OpenCV's RANSAC is randomized and
  multithreaded. Two runs of `ours` differed in 1,028 of 1.53 M scores, by a
  few points each, with the same summary. A rerun of `sigfm` reproduced its
  summary exactly.

## Disclosure

This benchmark was written with AI assistance (Claude). Every result was
produced by the code in this repository and can be reproduced with it.

## License

LGPL-2.1-or-later, like libfprint and SIGFM. The SIGFM sources are fetched
from libfprint, not included.
