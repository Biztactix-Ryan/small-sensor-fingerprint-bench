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

<!-- RESULTS -->

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

## Disclosure

This benchmark was written with AI assistance (Claude). Every result was
produced by the code in this repository and can be reproduced with it.

## License

LGPL-2.1-or-later, like libfprint and SIGFM. The SIGFM sources are fetched
from libfprint, not included.
