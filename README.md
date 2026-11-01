# small-sensor-fingerprint-bench

Benchmark for fingerprint matchers on small area sensors (96×96 px), built to
evaluate keypoint matchers for [libfprint](https://gitlab.freedesktop.org/libfprint/libfprint),
in particular SIGFM from merge request
[!530](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/530),
for the Elan 04f3:0c3d (96×96, ~542 dpi) and similar sensors.

This README has two separate parts. They answer different questions, and
each can be read and acted on without the other.

- **[Part 1: SIGFM as proposed in !530](#part-1-sigfm-as-proposed-in-530)**
  settles !530 on its own terms: the two fixes SIGFM needs (image
  normalization; match ordering with a cap), a threshold with its
  false-accept upper bound against NBIS on held-out data, scored through
  libfprint itself, and SIGFM's worst-case cost on a Raspberry Pi 4.
  *What it asks of the !530 reviewers:* whether this is enough to merge !530
  with those two fixes and that threshold. Part 1 does not depend on Part 2.
- **[Part 2: `akaze_c`, AKAZE in pure C](#part-2-akaze_c-akaze-in-pure-c)**
  proposes a different matcher: AKAZE keypoints and binary descriptors in
  plain C (no OpenCV, no C++), scored by the number of matches that agree on
  one rotation + translation, with hard caps on cost. It is compared with
  `sigfm_fix` on the same runs (accuracy, cost, template size,
  determinism), including where it is not better. *What it asks:* whether
  it is worth a separate MR, independent of !530.

Every results table is labelled Part 1 or Part 2 (Table P1-n, P2-n);
exploration results in the appendix are Tables A-n. Numbers from the final
run ([docs/FINAL_RUN.md](docs/FINAL_RUN.md), pre-registered) don't exist
yet and are marked _pending final run_.

## How the benchmark works

Public fingerprint datasets are rescaled to the sensor's resolution and cut
into sensor-sized patches ([docs/SCALING.md](docs/SCALING.md)). On those, the
benchmark simulates enrollment (10 stages in the runs so far, 20 in the
final run; a finger placed slightly differently each time) and verification against every enrolled finger, and
reports false accepts and false rejects per matcher. All matchers see exactly
the same patches. 20 enroll/verify sets with 4,813 fingers and 2 stranger-only
sets with 7,500 more are listed in [docs/DATASETS.md](docs/DATASETS.md).

Run types (called parts B and C in [docs/FINAL_RUN.md](docs/FINAL_RUN.md);
unrelated to Parts 1 and 2 of this README):

- **B, enroll/verify**: fingers with several impressions: genuine and
  impostor attempts. Runs: v1 (16 sets, 568 fingers, 1.44 M impostor
  attempts), v2 (v1 + Tsinghua, 880 fingers, 2.58 M), UNSW 2D (1,452
  fingers, 8.32 M).
- **C, strangers**: strangers only (SOCOFing, Family) against the enrolled
  fingers of B.
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
| NIST SD 302 plain (302b, c, d; up to 6 devices per finger, device L dropped) | 200 | 2,000 | 8,631 | enroll/verify |
| **enroll/verify total** | | **4,813** | **21,075** | |
| SOCOFing | 600 | 6,000 | 6,000 | strangers only |
| Family Fingerprint Dataset | 300 (100 families) | 1,500 | 1,500 | strangers only |
| **public total** | **at least 1,309** | **12,313** | **28,575** | |
| Elan 04f3:0c3d captures (ours, not published) | 1 | 10 | 301 | real sensor check |

Details, sources and terms: [docs/DATASETS.md](docs/DATASETS.md). Not every
set has been run yet: v1 used the FVC, Neurotechnology, FVS and MINEX sets
(16 sets, 568 fingers after
quality filters), v2 added Tsinghua, UNSW 2D ran on its own, and PolyU and
NIST SD 302 have had subset smoke tests so far. Registration (CLAHE, scale,
rotation and identity guards) changed for every set before the final run, so
registered-FRR numbers from earlier runs aren't directly comparable with it.

Matchers are compared at their own **zero-false-accept threshold** (the lowest
threshold without a false accept in the run; range = bootstrap over fingers,
5th–95th percentile) and by the false-reject rate (FRR) of genuine attempts
whose probe could be registered to the enrollment, also at a fixed
false-accept rate of 1e-5. Scores are only comparable within a matcher.

### Matchers in the final run

| Name | Part | What |
|---|---|---|
| `nbis` | 1 | libfprint's current minutiae matcher (bozorth3, `tools/bz3eval.c`), the baseline the !530 maintainers asked for |
| `sigfm` | 1 | SIGFM as in !530 (commit `bc986621`), built from its sources by `sigfm/build.sh`: SIFT keypoints on the raw image, ratio-test matches, score = number of pairs of match pairs whose length and angle agree |
| `sigfm_fix` | 1, and the Part 2 reference | SIGFM with Sergey Subbotin's ordering fix + 176 best matches: what !530 would likely merge |
| `akaze_c` | 2 | AKAZE in C (`akaze/build.sh`): 3× upscale + CLAHE, nonlinear scale space and MLDB binary descriptors, then deterministic strict matching (below). 20 px replicate pad at the border (Part 2, Table P2-11) |
| `akaze` | 2 (dev only) | the same inlier count on OpenCV AKAZE keypoints and descriptors (Hamming distance) with OpenCV RANSAC; checks that `akaze_c` reproduces it |

`ftsift_strict` (C SIFT) was a candidate until 2026-11-01 and is no longer
in the final run; its results are in the [appendix](#appendix-exploration-history) (and
Table P2-8). Other matchers tried along the way are listed there too.

---

## Part 1: SIGFM as proposed in !530

Part 1 is about SIGFM only. NBIS is the baseline; nothing here depends on
`akaze_c`.

**Table P1-1 (Part 1): what !530 needs, and where it stands**

| item | status | section |
|---|---|---|
| normalize fix (flip/invert before SIGFM extraction) | done, branch ready | [1.1](#11-normalize-fix-found-here) |
| ordering fix + 176 cap (`sigfm_fix`) | fix from the !530 thread, benchmarked | [1.2](#12-ordering-fix-and-cap-reported-on-530) |
| harness argument order matches libfprint | corrected 2026-11-01, results rerun | [correction](#correction-2026-11-01-sigfm-in-libfprints-argument-order) |
| threshold | the shipped 24 is too low on 2 of 3 runs; recommended value _pending final run_ | [1.3](#13-threshold) |
| false accepts vs NBIS on held-out data, through libfprint | _pending final run_ | [1.4](#14-false-accepts-against-nbis-held-out-data) |
| libfprint gives the harness's scores | `sigfm`, `sigfm_fix`: 211,200 of 211,200 identical, NBIS 205,328 of 205,328, on x86-64 and aarch64 | [1.5](#15-libfprint-fidelity) |
| worst-case cost on the Pi 4 | _pending final run_ | [1.6](#16-worst-case-cost) |

### 1.1 Normalize fix (found here)

!530's SIGFM extraction skips the flip/invert normalization that libfprint
applies before NBIS: drivers whose images are flagged inverted or flipped
(`fpi-assembling` sets `COLORS_INVERTED` and `H`/`V_FLIPPED`) hand SIGFM the
raw orientation, so the elan and elan-cobo capture tests fail on !530 and
applications get inverted images. Fix: normalize the image before
`sigfm_extract()`, one commit on top of !530's `bc98662`: branch
`sigfm-normalize-fix` (`96e8b49`, "fp-image: Normalize images before SIGFM
extraction") on our libfprint fork. The bug is in libfprint's image path,
not in SIGFM's matching: the harness calls SIGFM on its patches directly,
and the virtual_image check (1.5) gave the harness's scores exactly.

### 1.2 Ordering fix and cap (reported on !530)

Reported on !530 by others, not found here: SIGFM's `operator<` on matches
isn't a strict weak ordering, so about 80% of matches are dropped as
duplicates. That drop is also the only thing that bounds SIGFM's cost
(1.6). Sergey Subbotin's fix compares with `std::tie` and keeps the 176
best matches by distance; `sigfm_fix` is !530 with that fix. On the runs so
far it doesn't change accuracy (FRR @ FA 1e-5 14.7% for both on v1, Table
P1-2) and its zero-FA threshold is set by single impostor pairs, so it
moves more between runs (1.3).

### Correction (2026-11-01): SIGFM in libfprint's argument order

Until 2026-11-01 the harness called SIGFM as `sigfm_match_score(probe,
enrolled)`; libfprint (`fpi_print_sigfm_match()` in !530) calls
`sigfm_match_score(enrolled, probe)`, and the score isn't symmetric. Scoring
the benchmark's patches through libfprint's virtual_image driver
(`bench/virtual_check.py`) found 10,403 of 12,000 stage scores equal in the
old order. `sigfm` and `sigfm_fix` now score in libfprint's order, and all
27,600 stage scores of both pair sets are identical to libfprint's.

The published SIGFM results were rerun with only the order changed (bench
code of commit `4e66447`). A control rerun in the old order reproduced the
published v1 score matrix up to 4 of 1.53 M scores (OpenCV 4.6 → 4.10, same
summary) and the smoke-test matrices exactly. Changes:

**Table P1-C (Part 1): SIGFM results before and after the order correction**

| result | old order | libfprint order |
|---|---|---|
| v1 `sigfm`: zero-FA threshold, FRR @ FA 1e-5, false accepts @ 24 | 28, 15.1%, 1 | 21, 14.7%, 0 |
| v1 `sigfm_fix` | 63, 15.5%, 7 | 56, 14.7%, 3 |
| v1 `sigfm_fix`, 5 / 15 / 25 enrolled images: threshold @ FA 1e-5, FRR there | 13, 17.4% / 22, 13.9% / 26, 12.0% | 12, 17.1% / 18, 14.1% / 20, 12.1% |
| v2 `sigfm` | 29, 21.9%, 5 | 28, 22.1%, 1 |
| v2 `sigfm` strangers: SOCOFing max, false accepts @ 24; Family max | 15, 0; 2 | 35, 6; 23 |
| v2 `sigfm_fix` | 63, 21.8%, 12 | 58, 22.2%, 9 |
| v2 `sigfm_fix` strangers: SOCOFing max, false accepts @ 24; Family max, false accepts @ 24 | 29, 1; 10, 0 | 57, 31; 66, 6 |
| UNSW `sigfm` | 101, 3.9%, 72 | 123, 4.0%, 88 |
| UNSW `sigfm_fix` | 134, 3.9%, 236 | 149, 4.1%, 271 |
| PolyU / NIST smoke `sigfm`: FRR @ zero-FA | 52.7% / 43.0% | 44.2% / 38.4% |
| real sensor `sigfm` @ 24: genuine rejected (of 201 / of 296) | 14 / 27 | 13 / 22 |
| real sensor `sigfm_fix` @ 24: genuine rejected (of 296) | 22 | 20 |

Still in the old order, marked † below: the retired `sigfm_pre` and the
speed numbers (not rerun). The v1 and enrollment-depth reruns ran on OpenCV 4.10 (compute VM),
the published ones on 4.6; v2, UNSW and the smoke tests on the AI box
(OpenCV 4.10).
The findings hold: SIGFM's safe threshold still depends on the data (21 on
v1, 123 on UNSW), and in libfprint's order the shipped 24 also accepts
strangers: 6 of 10.3 M SOCOFing attempts for `sigfm`, 31 SOCOFing and 6
Family for `sigfm_fix`.

### 1.3 Threshold

**SIGFM's threshold isn't a constant.** The shipped 24 accepts impostors on
every run but one: `sigfm` 1 on v2 plus 6 of 10.3 M SOCOFing strangers and
88 on UNSW (none on v1); `sigfm_fix` 3 on v1, 9 on v2 plus 31 SOCOFing and
6 Family strangers, and 271 on UNSW. The safe value depends on the sensor's
images (~21 contact, ~120 optical) and on the number of enrolled images (12
to 20 at FA 1e-5 for 5 to 25 images). With the ordering fix it is set by
single impostor pairs and moves between 21 and 56 on v1.

**Table P1-2 (Part 1): SIGFM thresholds and false accepts by run** (from
[results/v1](results/v1/SUMMARY.md), [results/v2](results/v2/SUMMARY.md)
and [results/unsw](results/unsw/SUMMARY.md), as in Table P1-C; Part 2
repeats them next to its own matchers)

| run | `sigfm` zero-FA threshold (range) | `sigfm` FRR @ FA 1e-5 | `sigfm` FA @ 24 | `sigfm_fix` zero-FA threshold (range) | `sigfm_fix` FRR @ FA 1e-5 | `sigfm_fix` FA @ 24 |
|---|---|---|---|---|---|---|
| v1 (contact) | 21 (15–21) | 14.7% | 0 | 56 (21–56) | 14.7% | 3 |
| v2 (v1 + Tsinghua) | 28 (21–28) | 22.1% | 1 | 58 (28–58) | 22.2% | 9 |
| v2 SOCOFing strangers (10.3 M): max, FA @ 24 | 35 | | 6 | 57 | | 31 |
| v2 Family strangers (656 k): max, FA @ 24 | 23 | | 0 | 66 | | 6 |
| UNSW 2D (optical) | 123 (47–123) | 4.0% | 88 | 149 (71–149) | 4.1% | 271 |

Bytes per enrolled image: 141,554 for both. On the real sensor (one
person, Table P1-C) neither has a false accept at 24; genuine rejected:
`sigfm` 13 of 201 and 22 of 296, `sigfm_fix` 20 of 296.

**Table P1-3 (Part 1): enrollment depth (v1)**,
[results/enrollment-depth](results/enrollment-depth/SUMMARY.md); `ours_det`
(an inlier count: the number of matches that agree on one rotation +
translation; see the [appendix](#appendix-exploration-history)) for
comparison.

| enrolled images | 5 | 10 | 15 | 25 |
|---|---|---|---|---|
| `ours_det` threshold @ FA 1e-5 | 7 | 8 | 8 | 8 |
| `ours_det` FRR @ FA 1e-5 | 17.3% | 16.2% | 14.2% | 12.7% |
| `sigfm_fix` threshold @ FA 1e-5 | 12 | 16 | 18 | 20 |
| `sigfm_fix` FRR @ FA 1e-5 | 17.1% | 14.7% | 14.1% | 12.1% |

More enrolled images help both equally; SIGFM's threshold has to rise by two
thirds from 5 to 25 images to stay as safe, the inlier count's doesn't move.

**Recommended threshold:** _pending final run_. Rule, fixed before the run
([docs/FINAL_RUN.md](docs/FINAL_RUN.md)): the lowest score with zero false
accepts on the dev sets + 1, one value per matcher for all sensors, at 20
enrollment stages (libfprint's default for the 0c3d).

### 1.4 False accepts against NBIS (held-out data)

Measured on test sets never used to choose the threshold (NIST SD 302,
PolyU cross-session, SOCOFing and Family strangers, new 0c3d sessions), at
the threshold from 1.3, with the 95% Clopper-Pearson upper bound. A matcher
passes if that bound is ≤ 1e-5 per template attempt and no synthetic probe
is accepted.

**Table P1-4 (Part 1): safety on test data, final run**

| matcher | threshold | false accepts / attempts | 95% upper bound per attempt | per identify over 10 fingers | FRR (registered) there | passes |
|---|---|---|---|---|---|---|
| `nbis` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |
| `sigfm` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |
| `sigfm_fix` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |

### 1.5 libfprint fidelity

Through libfprint itself (enroll, store and verify with the virtual_image
driver, `bench/virtual_check.py`), `sigfm`, `sigfm_fix` and NBIS give the
harness's stage scores exactly, in libfprint's argument order (see the
correction above and [Fidelity](#fidelity)), on x86-64 and on aarch64
(Raspberry Pi 4). The pairs are a sample of every FVC 2000/2002/2004 B set
plus FVS: 132 templates of 20 patches, each verified against its genuine
probes and random impostors (10,560 pairs, 211,200 stage scores; NBIS
12,672 pairs). The harness ran on x86-64; libfprint ran on both machines and
was compared with it, so the aarch64 column is aarch64 libfprint against
the x86-64 harness. aarch64 builds use `-ffp-contract=off`.

**Table P1-6 (Part 1): libfprint gives the harness's scores**

| matcher | pairs | stage scores | identical, x86-64 | identical, aarch64 |
|---|---|---|---|---|
| `sigfm` (!530) | 10,560 | 211,200 | all | all scores; features differ (below) |
| `sigfm_fix` | 10,560 | 211,200 | all | all scores; features differ (below) |
| NBIS | 12,672 (11,301 verified) | 205,328 | all | all |

- NBIS: libfprint asks for a retry on probes without minutiae (1,371 of
  12,672; the harness has no print there and scores 0) and leaves 245 of
  2,640 template images without minutiae out of the print; diff checks
  every one of those against the harness. The aarch64 output is the
  x86-64 output byte for byte (timings aside).
- SIGFM on aarch64: every score and every keypoint count is the same, but
  none of the 3,737 serialized feature blobs is. The Pi has OpenCV 4.10,
  the x86-64 machine 4.6, and SIFT's keypoint floats differ in the last bits
  both between those versions (x, size, up to 4e-6) and between x86-64 and
  aarch64 on 4.10 (response, up to 2e-9), on synthetic images with
  descriptors identical. SIGFM's score does not change with them here.
- A fault in the check tool itself, not libfprint: the virtual_image
  driver simulates device temperature, and after about 3 minutes of
  continuous use every action failed as too hot. That hit the Pi runs
  (4 processes, long-running); `fidelity/virtual_check.c` now turns the
  simulation off (`FP_VIRTUAL_IMAGE_HOT_SECONDS=-1`), and all runs above
  were redone with it.

### 1.6 Worst-case cost

SIGFM as shipped is bounded only by its comparator bug: at most 97 unique
matches on a 96 px frame, so at most C(97, 2) = 4,656 angle pairs; without
the bug (and without a cap) the score is O(n⁴) in the number of matches.
With the ordering fix the 176-match cap is the bound. Typical cost on a
desktop: Table P2-9 (`sigfm`†: extract 6 ms, verify 23 ms, identify over 10
fingers 198 ms on an i7-13700KF, under load).

**Table P1-5 (Part 1): worst case on the slow reference (Raspberry Pi 4),
adversarial input, single thread.** Budget: verify ≤ 0.5 s, identify of 10
prints ≤ 2 s.

| matcher | extract | verify (20 stages) | identify over 10 fingers | peak RSS | bytes per stored print |
|---|---|---|---|---|---|
| `nbis` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |
| `sigfm` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |
| `sigfm_fix` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |

---

## Part 2: `akaze_c`, AKAZE in pure C

A proposal separate from !530. `akaze_c` is AKAZE (nonlinear scale space and
MLDB binary descriptors) in plain C, in libfprint's `fpi-keypoint-*`, with
no OpenCV or C++. The image is upscaled 3× with CLAHE; matches are mutual
ratio-test matches, and the score is the number of them that agree on one
rotation (±45°) + translation, found by a deterministic search (no RANSAC).
Hard caps (384 keypoints per image, 64 candidate matches, 1,225 candidate
transforms) make the worst-case match cost a function of the caps only
([docs/FINAL_RUN.md](docs/FINAL_RUN.md), "Cost bound by construction").

**Border: a 20 px replicate pad.** AKAZE only places a keypoint where its
rotated MLDB descriptor window fits inside the image, which on a 96×96
frame leaves the central half (below, finding 3). `akaze_c` upscales the
frame 3× (288×288), then repeats its edge pixels 20 px outwards on each
side before detection, so the rotated sampling pattern has values for
keypoints near the edge; positions are shifted back afterwards. Each pad
pixel is a copy of the nearest edge pixel, so no ridge content is
invented, and the pad is not stored: a stored print holds the keypoint
positions and their descriptors only. Two pad-free alternatives were
measured on the same dev data ([docs/FINAL_RUN.md](docs/FINAL_RUN.md),
item 0c): no pad, and border-aware (masked) descriptors, which detect
nearer the edge and leave out the descriptor bits that sample outside the
image. The pad is better than both on real-sensor rejects, v1 impostor max
and v1 zero-FA threshold; masking ties it only on v1 FRR @ FA 1e-5, and
needs a 61-byte mask per keypoint (1.9× the stored print) and ~25% more
time per match. The owner kept the pad (2026-11-02). The masked code is
not in libfprint; [akaze/masked.patch](akaze/masked.patch) adds it back to
reproduce item 0c.

**Table P2-11 (Part 2): `akaze_c` border handling, dev data** (real 0c3d
protocols A / B at threshold 10, one person; v1 on the compute VM, range =
bootstrap over fingers, 5th–95th percentile; cost on real frames, i7-13700KF,
one thread)

| variant | real rejects (A / B) | real impostor max (A / B) | v1 zero-FA threshold | v1 FRR there | v1 FRR @ FA 1e-5 | v1 impostor max | stored bytes per image (p50) | match p50 |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| pad 20 (kept) | **11 / 28** | 4 / 5 | **7** | **8.5%** | **7.6% (6.1–9.7%)** | **6** | 26,496 | 2.01 ms |
| no pad | 16 / 34 | 5 / 6 | 10 | 12.7% | 9.2% (7.6–11.9%) | 9 | 26,496 | 2.02 ms |
| masked (floor first, border 2, floor 243 bits) | 12 / 31 | 4 / 5 | 8 | 10.3% | 7.6% (6.2–11.0%) | 7 | 49,920 | ~2.5 ms |

### 2.1 Why: findings

1. **An inlier count (matches agreeing on one rigid transform) has a stable
   threshold:** 8–10 on every set and for 5–25 enrolled images (Tables
   P2-1, P1-3). In 21 M stranger attempts over all runs it never reached 10.
   SIGFM's moves between 21 and 149 (Table P1-2).
2. **Accuracy is close between SIGFM and SIFT inlier counts;** AKAZE
   descriptors are better on all three public runs, most of all averaged per
   set (30% vs 40% FRR on v1, 31% vs 41% on v2) and on hard data
   (cross-session and cross-device subsets, Table P2-7).
3. **On the real Elan 0c3d, AKAZE at 2× rejected more presses** (23 of
   201, against 13 for SIGFM and 14 for `ftsift_strict`): its descriptor border
   (14.5 native px) left only the central half of the 96×96 frame for
   keypoints, and offset presses share skin mostly near the edges.
   Upscaling 3× and padding the image by 20 px before detection
   (`akaze_c`'s default, see above) brings it to 11,
   and also improves v1 (FRR @ FA 1e-5 10.9% → 7.6%). Details in
   [docs/FINAL_RUN.md](docs/FINAL_RUN.md), item 0c.
4. **Smaller templates:** 19,848 bytes per enrolled image for OpenCV
   `akaze` against 141,554 for SIGFM; `akaze_c`'s size is pending (Table
   P2-2).
5. **Deterministic and in C:** `akaze_c` gives the same scores on every run
   and needs no OpenCV; its keypoints and descriptors at 2× are
   bit-identical to OpenCV AKAZE (Fidelity).

### 2.2 Where it is not better

- **Rotation:** the ±45° limit rejects presses rotated further. On all 396
  real captures, 10 of `akaze_c`'s 28 rejects are left thumb presses rotated
  62–81° from enrolment; `sigfm` (22 rejects) and `sigfm_fix` (20) accept
  them. On that set `akaze_c` rejects more than both.
- **Extraction cost:** `akaze_c` at 3× + pad extracts in 34 ms and
  verifies in 75 ms on an i7, against 6 and 23 ms for `sigfm`† (different runs, Table P2-9).
  The Pi 4 estimate for identify over 10 fingers is 1.8–2.7 s against a
  2 s budget, not yet measured (Table P2-3).
- **UNSW 2D (optical):** the zero-FA FRR is 6.9% against 6.4% (`sigfm`) and
  6.1% (`sigfm_fix`), and one impostor reaches 12 (threshold 13, 1 false
  accept at 10; Table P2-6).
  At FA 1e-5 it is lower (3.8% vs 4.0% / 4.1%).
- One person's captures so far; the real-sensor numbers are a check of the
  sensor's images, not a false-accept estimate.

### 2.3 Summary

**Table P2-1 (Part 2): accuracy summary, all public runs.** `sigfm_fix` is
the reference; `ours` (OpenCV SIFT + RANSAC) is the SIFT inlier count that
findings 1 and 2 compare against. `ftsift_strict` is in Table A-1.

| | v1 threshold | v1 FRR @ FA 1e-5 | v2 threshold | v2 FRR @ FA 1e-5 | UNSW threshold | UNSW FRR @ FA 1e-5 | bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| `sigfm` (!530) | 21 (15–21) | 14.7% | 28 (21–28) | 22.1% | 123 (47–123) | 4.0% | 141,554 |
| `sigfm_fix` | 56 (21–56) | 14.7% | 58 (28–58) | 22.2% | 149 (71–149) | 4.1% | 141,554 |
| `ours` (SIFT + RANSAC) | 9 (8–9) | 14.4% | 9 (8–9) | 18.8% | 10 (9–10) | 5.1% | — |
| `akaze` | 9 (7–9) | **11.2%** | 9 (8–9) | **18.1%** | 13 (9–13) | **3.8%** | 19,848 |
| `akaze_c` 3× + pad (compute VM, FINAL_RUN.md item 0c) | 7 (7–7) | 7.6% | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |

**Table P2-2 (Part 2): template size and determinism**

| matcher | bytes per enrolled image | deterministic | needs |
|---|---|---|---|
| `sigfm_fix` | 141,554 | not checked separately; a rerun of `sigfm` reproduced its summary exactly | OpenCV, C++ |
| `akaze` (OpenCV) | 19,848 | no: OpenCV RANSAC is randomized | OpenCV, C++ |
| `akaze_c` | _pending final run_ | yes: deterministic search, identical scores Python vs C | C only |

**Table P2-3 (Part 2): final run, `akaze_c` against `sigfm_fix` on the same
test data and machine**

| matcher | threshold | 95% FMR upper bound per attempt | FRR (registered) there | worst-case verify, Pi 4 | worst-case identify 10, Pi 4 |
|---|---|---|---|---|---|
| `sigfm_fix` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |
| `akaze_c` | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ | _pending final run_ |

### 2.4 Results by run

Logs, score matrices and generated summaries (`bench/summarize.py`) in
[results/](results/). These tables keep the matchers Part 2 argues with;
`ours` is the SIFT inlier-count baseline. Rows for the other matchers run so
far are in the [appendix](#appendix-exploration-history), Tables A-1 to A-5.

#### v1

16 sets, 568 fingers, 1,440,034 impostor attempts. `sigfm*`, `ours` and
`ours_raw` from [results/v1](results/v1/SUMMARY.md), the rest from
[results/v1-variants](results/v1-variants/SUMMARY.md) (OpenCV 4.10; its `ours`
baseline reproduces v1: threshold 9, FRR 18.6%, 14.5% at FA 1e-5). `sigfm`
and `sigfm_fix` are the 2026-11-01 reruns in libfprint's order (OpenCV
4.10).

**Table P2-4 (Part 2): v1**

| matcher | zero-FA threshold (range) | FRR there | FRR @ FA 1e-5 | per-set average FRR | bytes per enrolled image |
|---|---|---|---|---|---|
| `sigfm` | 21 (15–21) | 15.8% | 14.7% | 34.3% | |
| `sigfm_fix` | 56 (21–56) | 18.4% | 14.7% | 38.8% | |
| `ours` | 9 (8–9) | 18.6% | 14.4% | 40.7% | |
| `akaze` | 9 (7–9) | 13.4% | 11.2% | 29.8% | |

- The pooled FRR is dominated by the clean sets (Neurotechnology, FVS); the
  per-set average weighs every set equally.

#### v2 and strangers

[results/v2](results/v2/SUMMARY.md). v2 adds Tsinghua (320 fingers, one
deliberately distorted impression) to v1.

**Table P2-5 (Part 2): v2 and strangers**

| matcher | zero-FA threshold | FRR there | FRR @ FA 1e-5 | per-set average | SOCOFing strangers (10.3 M): max, FA @ default | Family strangers (656 k): max |
|---|---|---|---|---|---|---|
| `sigfm` | 28 (21–28) | 24.7% | 22.1% | 36.8% | 35, 6 @ 24 | 23 |
| `sigfm_fix` | 58 (28–58) | 26.5% | 22.2% | 39.8% | 57, 31 @ 24 | 66 |
| `ours` | 9 (8–9) | 24.4% | 18.8% | 40.8% | 9, 0 @ 10 | 6 |
| `akaze` | 9 (8–9) | 21.1% | 18.1% | 31.0% | | |

#### UNSW 2D (optical, 1,452 fingers)

[results/unsw](results/unsw/SUMMARY.md). `ours` is from a run that still
included 25 duplicated impressions; reruns of the SIGFM variants without
them changed FRR by 0.1 point at most.

**Table P2-6 (Part 2): UNSW 2D**

| matcher | max impostor | FA @ default | zero-FA threshold | FRR there | FRR @ FA 1e-5 |
|---|---|---|---|---|---|
| `sigfm` | 122 | 88 @ 24 | 123 (47–123) | 6.4% | 4.0% |
| `sigfm_fix` | 148 | 271 @ 24 | 149 (71–149) | 6.1% | 4.1% |
| `ours` | 9 | 0 @ 10 | 10 (9–10) | 6.8% | 5.1% |
| `akaze` | 12 (next: 9) | 1 @ 10 | 13 (9–13) | 6.9% | 3.8% |

#### New sets: smoke test on subsets

[results/new-sets-smoke](results/new-sets-smoke/SUMMARY.md): 56 PolyU fingers
enrolled in one session and verified 2–24 months later, 86 NIST SD 302
fingers enrolled and verified on different devices; ~30 k impostor attempts
each, so thresholds aren't comparable with the full runs. FRR at each
matcher's zero-FA threshold:

**Table P2-7 (Part 2): PolyU and NIST smoke tests**

| matcher | PolyU, cross-session | NIST, cross-device |
|---|---|---|
| `sigfm` | 44.2% | 38.4% |
| `ours_strict` | 73.0% | 25.6% |
| `akaze` | **26.5%** | **14.0%** |

SIFT-based matching degrades most on these harder conditions. Only 23% of
NIST's cross-device impressions could be registered to their enrollment
impression, to be looked into before a full NIST run. Fixed since: with device L
dropped, devices ordered best first for enrollment and a harder
registration with guards, 85% register on the full set; see
[docs/DATASETS.md](docs/DATASETS.md).

#### Real sensor: Elan 04f3:0c3d, one person

Ten fingers, 301 presses in five sessions (normal skin, freshly washed hands,
dry skin at night). Each finger is enrolled from 10 presses of one session;
impostors are the other nine fingers of the same person (2,709 attempts),
genuine attempts the presses of the other sessions (201).
`bench/cross_finger.py`. One person, so a check of the real sensor's images
rather than a false-accept estimate.

**Table P2-8 (Part 2): real sensor, 201 genuine / 2,709 impostor attempts**

| matcher | impostor max | FA | genuine rejected |
|---|---|---|---|
| `sigfm` @ 24 | 8 | 0 | 13 |
| `ftsift_strict` @ 10 | 5 | 0 | 14 |
| `akaze` @ 10 | 4 | 0 | 23 |
| `akaze_c` @ 10, 2× (old default) | 4 | 0 | 23 |
| `akaze_c` @ 10, 3× + 20 px pad | 4 | 0 | **11** |

- No sign of fixed-pattern matches (impostor scores far above the rest, as
  reported for some Goodix sensors on !530); the elan driver subtracts a
  background frame.
- Genuine rejections are mostly thumbs, much larger than the 96×96 window: a
  press often lands on skin that wasn't enrolled.
- Six captures first looked like false accepts; all were labelling mistakes
  during collection (the first presses after a finger change made with the
  previous finger) and are excluded. The capture tool now waits for a key at
  each finger change.
- AKAZE's extra rejects at 2× were good presses placed off the enrolled
  area: its keypoints never came closer than 13.5 native px to the frame
  edge.
  With all 396 captures to date (two more sessions, 296 genuine attempts),
  rejects are `akaze_c` 28 (2×: 48), `sigfm` 22, `sigfm_fix` 20,
  `ftsift_strict` 38, still no false accept. 10 of `akaze_c`'s 28 are left
  thumb presses rotated 62–81° from enrolment, which its ±45° rotation
  limit (shared with `ftsift_strict`) rejects.
- An earlier table on the first 205 presses with all matchers is in the git
  history.

#### Speed (preliminary)

Single thread, Intel i7-13700KF, real 96×96 captures, 20 enrolled images;
measured while the benchmark ran on all cores, so upper bounds. Milliseconds:

**Table P2-9 (Part 2): speed, i7-13700KF**

| matcher | extract | verify (extract + 20 matches) | identify over 10 fingers |
|---|---|---|---|
| `sigfm`† | 6 | 23 | 198 |
| `akaze` | 7 | 28 | 232 |

Every matcher verifies in well under a second.
`akaze_c` at its current 3× + pad setting (one thread pinned, later run):
extract 34 ms, verify 75 ms, identify 442 ms (2× unpadded: 11, 30, 195);
not yet measured on the slow reference (Raspberry Pi 4), where identify
over 10 fingers is estimated at 1.8–2.7 s against a 2 s budget.

### 2.5 Matching code and caps

The deterministic matching is in our libfprint branch as plain C
(`fpi-keypoint-match.c`, with euclidean, Hamming and ternary descriptors) and
gives scores identical to the Python code here. When it is built as
`kpm/libkpm.so` (`akaze/build.sh lib` builds it; or `FPBENCH_KPM_LIB`), the
matchers using it score through it. Its cost caps (at most 1024 keypoints per
image, the 64 closest candidate matches; akaze_c keeps its 384 strongest
keypoints, ftsift its 512 strongest; chosen by a sweep on v1) can be changed
for sweeps with `FPBENCH_MAX_MATCHES`, `FPBENCH_AKAZE_MAX_KP` and
`FPBENCH_FTSIFT_MAX_KP`.

---

## Appendix: exploration history

Before settling on `akaze_c`, other descriptors (OpenCV SIFT, two C SIFTs,
ORB, BRISK), compact SIFT descriptor codes, SIGFM variants and RANSAC versus
deterministic matching were tried. These results informed the choice of
`akaze_c` as the Part 2 matcher; none of these matchers is in the final run.
Their results are kept here, and they are still runnable.

| Name | What | Why not in the final run |
|---|---|---|
| `ftsift_strict` | the inlier count, all in C: 2× upscale + CLAHE, SIFT from a libfprint fork's FocalTech FT9366 driver (LGPL, `csift/build.sh`), ratio-test matches that are each other's nearest neighbours, deterministic search for the rotation (±45°) + translation the most matches agree with; score = agreeing matches | dropped from the final run 2026-11-01; `akaze_c` is the C candidate |
| `sigfm_pre` | SIGFM on upscaled + CLAHE images | raises impostor scores as much as genuine ones |
| `ours`, `ours_raw` | inlier count, OpenCV SIFT + RANSAC | not reproducible (randomized); `ours_strict` equals it |
| `ours_det`, `ours_strict`, `ours_det2` | deterministic search; `strict` adds mutual matches + ±45°; `det2` least squares refits | superseded by `ftsift_strict`; the refit changed nothing |
| `vlsift`, `ftsift`, `vlsift_strict` | C SIFT from VLFeat (BSD) or FocalTech | `ftsift_strict` equals `vlsift_strict` and is LGPL |
| `q_pca40`, `q_bin128`, `q_bin256`, `q_tern128` | compact SIFT descriptor codes, fit on the stranger sets (`bench/fit_quant.py`) | storage experiment; `q_tern128` worth revisiting for templates |
| `union` | ArcticLampyrid's union-of-inliers score from !530 | FRR more than doubles |
| `orb`, `brisk` (+ `_raw`) | binary descriptors | clearly worse than SIFT and AKAZE |

Exploration findings:

- **SIFT without OpenCV works:** the FocalTech FT9366 C SIFT (LGPL) with
  strict matching (mutual matches, ±45°) and our C matcher beats the OpenCV
  pipeline on v1.
- **Compact descriptors:** ternary codes (32 bytes per keypoint, 3.4×
  smaller than SIFT's) match AKAZE's accuracy on v1 with their own threshold
  of 13.

### Exploration results

**Table A-1 (Appendix): accuracy summary.** Extends Table P2-1.

| | v1 threshold | v1 FRR @ FA 1e-5 | v2 threshold | v2 FRR @ FA 1e-5 | UNSW threshold | UNSW FRR @ FA 1e-5 | bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| `ftsift_strict` (all C) | 8 (7–8) | 13.3% | | | | | 67,121 |

**Table A-2 (Appendix): v1.** Extends Table P2-4 (same sources and runs).

| matcher | zero-FA threshold (range) | FRR there | FRR @ FA 1e-5 | per-set average FRR | bytes per enrolled image |
|---|---|---|---|---|---|
| `sigfm_pre`† | 91 (58–91) | 17.5% | 15.1% | 38.7% | |
| `ours_raw` | 8 (7–8) | 18.9% | 16.7% | 40.0% | |
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
| `orb` | 13 (12–13) | 25.1% | 22.5% | 45.4% | |
| `union` | 1221 (1026–1221) | 40.7% | 33.0% | 65.3% | |

- The deterministic search alone (`ours_det`) costs ~1.5 points against
  RANSAC; mutual matches + ±45° (`ours_strict`) win it back; a least squares
  refit (`ours_det2`) changes nothing.
- The FocalTech SIFT is weak with plain matching (strangers up to 13) and
  among the best with strict matching (strangers up to 7).

**Table A-3 (Appendix): PolyU and NIST smoke tests.** Extends Table P2-7.

| matcher | PolyU, cross-session | NIST, cross-device |
|---|---|---|
| `q_tern128` | 34.1% | 16.3% |

**Table A-4 (Appendix): real sensor, 201 genuine / 2,709 impostor attempts.**
Extends Table P2-8.

| matcher | impostor max | FA | genuine rejected |
|---|---|---|---|
| `ours_det` @ 10 | 7 | 0 | 17 |
| `q_tern128` @ 13 | 10 | 0 | 10 |

**Table A-5 (Appendix): speed, i7-13700KF, milliseconds.** Extends Table
P2-9 (same run). The FocalTech SIFT extracts keypoints ~6× slower than
OpenCV's (not vectorized), which still fits.

| matcher | extract | verify (extract + 20 matches) | identify over 10 fingers |
|---|---|---|---|
| `ours_strict` | 15 | 29 | 310 |
| `ftsift` | 94 | 137 | 722 |

## Next

- The final run ([docs/FINAL_RUN.md](docs/FINAL_RUN.md)): `nbis`, `sigfm`,
  `sigfm_fix` (Part 1) and `akaze_c` (Part 2) on all sets, with the
  worst-case cost on the slow reference. This fills every _pending final
  run_ above.
- More real-sensor sessions and people.
- `akaze_c` in libfprint, scored through its virtual image driver
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

Each enroll/verify run (B) takes 15–45 minutes on 22 cores (about 1.5 M
matcher comparisons); a stranger run (C) is several times that.
`bench/bench_watch.sh` can watch a queue of runs for errors and stalls.

If `import cv2` fails with a NumPy ABI error, a pip NumPy 2 in `~/.local`
is shadowing the distribution's NumPy 1 that the distribution's OpenCV was
built against; run with `PYTHONNOUSERSITE=1`.

For another sensor, measure its resolution first
([docs/SCALING.md](docs/SCALING.md)) and set `FPBENCH_SENSOR_DPI`.

## Fidelity

- `sigfm*` call the !530 C++ code through its C API (via ctypes), including a
  serialize/deserialize round trip like stored prints: 0 score differences
  in 1,260 pairs against a standalone C++ build. Through libfprint itself
  (enroll, store and verify with the virtual_image driver,
  `bench/virtual_check.py`), `sigfm`, `sigfm_fix` and NBIS give the
  harness's stage scores exactly, on x86-64 and aarch64, since the harness
  passes SIGFM's arguments in libfprint's order (enrolled, probe); see the
  correction above and Table P1-6.
- `akaze_c` through libfprint, the same pairs as Table P1-6 (Table P2-10).
  The libfprint side is the `sift-matcher` branch with its uncommitted
  work; the harness loads `libakaze_c.so` built from the same tree. Only the
  padded variant (3× + 20 px replicate pad) is in libfprint's device path:
  prints carry no descriptor masks, so the masked variant
  (`FPBENCH_AKAZE_MASK=1`, border 2, 162 valid bits; not kept, item 0c, and
  since then only with [akaze/masked.patch](akaze/masked.patch) applied)
  cannot go through virtual_image. For it, `virtual_check.py cscore` runs the same C
  library from the standard library alone (no NumPy/OpenCV) and compares
  with the harness's file; on x86-64 that reproduces the harness, and on
  the Pi it compares aarch64 with the x86-64 harness. Through virtual_image
  the masked harness scores of course differ from libfprint's padded ones
  (`diff` reports `PARAMETER DIFFERS pad`).

**Table P2-10 (Part 2): `akaze_c` scores, harness (x86-64) against
libfprint and against the C library alone, 10,560 pairs (211,200 stage
scores, 3,737 images' features)**

| variant | path | identical, x86-64 | identical, aarch64 |
|---|---|---|---|
| padded (3×, pad 20) | libfprint virtual_image | all | all |
| padded (3×, pad 20) | C library (`cscore`) | all | all |
| masked (border 2, 162 bits) | C library (`cscore`) | all | all |
| masked | libfprint virtual_image | not possible: not in libfprint's device path | — |
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
- `akaze_c`'s C AKAZE extraction on the 2×, unpadded path is bit-identical
  to OpenCV AKAZE ([docs/FINAL_RUN.md](docs/FINAL_RUN.md), item 0c).

## Disclosure

This benchmark was written with AI assistance (Claude). Every result was
produced by the code in this repository and can be reproduced with it.

## License

LGPL-2.1-or-later, like libfprint and SIGFM. The SIGFM sources are fetched
from libfprint, not included.
