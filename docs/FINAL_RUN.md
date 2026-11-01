# Final run: protocol (pre-registration)

Status: frozen and signed off 2026-11-02 (end of file).
Scope, FAR bar and slow-machine choice agreed 2026-10-31; matcher set
(`ftsift_strict` dropped) 2026-11-01; `akaze_c` pad-20 kept 2026-11-02.
This file is committed **before** any final-run score is computed, and the
commit hash is quoted with the results. Nothing below (parameters,
thresholds, splits, decision rule) changes after that commit; anything that
does is reported as a deviation.

## Frozen sources and environment

| item | frozen value | source |
|---|---|---|
| libfprint (`akaze_c` C sources, NBIS mindtct/bozorth3, virtual_image) | `663de000143ec69303897dfe9eca87e13be442e3` (branch `sift-matcher`, on upstream `6f9479c3`; local until the matcher MR is opened) | `akaze/build.sh`, `nbis/build.sh` build from this tree (`LIBFPRINT`) |
| bench repo (harness, this file) | `f4a3efd7852518fcbd630b2dc4dc64e6d9fcf9a7` (harness); this file is frozen by the commit that adds it | `bench/big_eval.py`, `bench/matchers.py`, `bench/public_sets.py`, `bench/summarize.py` |
| SIGFM sources | !530 at `bc986621b906546836cb008355c1e8d5cd88a0db` | `sigfm/fetch.sh` (`PIN`) |
| SIGFM fix | `sigfm/patches/ssubbotin-ordering-and-cap.patch` (full match ordering + 176 best matches) | `sigfm/build.sh` |
| OpenCV (image loading, rescale, patching for every matcher; SIFT for SIGFM) | 4.10.0 on every machine that produces final-run scores: AI box (EPYC 7302, Ubuntu 26.04, Python 3.14.4, NumPy 2.3.5) and compute VM (Xeon Gold 6154, Debian 13, Python 3.13.5, NumPy 2.2.4) | `python3 -c 'import cv2, numpy; print(cv2.__version__, numpy.__version__)'` on each, 2026-11-02 |
| OpenCV on the Pi 4 (timing, aarch64 identity) | 4.10.0 (NumPy 2.2.4) | same command on `raspberrypi4` |
| not used for final-run scores | the local i7-13700KF (OpenCV 4.6.0, NumPy 1.26.4): Phase 3 single-thread timing only | |

Matchers are compared within one machine and one OpenCV version only.

## Questions this run answers

1. **Safety** (the !530 blocker): at a fixed, pre-chosen threshold, how often
   does each matcher accept a finger that isn't enrolled, with an upper
   confidence bound, on data that was never used to tune it? How does that
   compare with NBIS on the same data, and does the libfprint build give the
   same scores as the harness?
2. **Choice**: which matcher goes upstream: `akaze_c` (C port) or SIGFM
   (!530, with or without the ordering fix)? (`ftsift_strict`, C SIFT, was
   a candidate until 2026-11-01 and is not in the final run.)
3. **Cost**: worst-case extract, verify and identify time and memory, bounded
   by construction rather than observed by luck. A worst case of 5 s
   fails.

## Phase 0: prerequisites (before the frozen commit)

| # | item | done when |
|---|---|---|
| 0a | `akaze_c`: AKAZE (nonlinear scale space + MLDB) in C, deterministic, in `fpi-keypoint-*`, scored by the existing C matcher | keypoints/descriptors agree with OpenCV AKAZE on ≥ 1,000 patches (report the agreement); v1 zero-FA threshold and FRR @ FA 1e-5 within bootstrap range of `akaze`. Done (US-FPR-1, 2026-10-31): 1,005 images at 192² (301,515 keypoints) bit-identical in keypoints and all 61 descriptor bytes, plus 4 other sensor sizes ([akaze/README.md](../akaze/README.md), "Agreement"); on the 2×, unpadded path, which the frozen 3× + pad setting leaves unchanged |
| 0b | Hard caps in every candidate: max keypoints per image (strongest N), max candidate matches, fixed iteration bound in the geometric search | worst-case cost is a function of the caps only (Phase 3). Done: caps 384 / 512 keypoints, 64 matches, 1,225 transforms; closed form under "Cost bound by construction" |
| 0c | AKAZE vs real 0c3d gap (23 vs 14 rejects) explained, fixed or accepted | tuned **only** on dev data (below), then frozen. Done: cause is AKAZE's descriptor border; fixed by 3× upscale + 20 px replicate padding (23 → 11 rejects, v1 FRR @ FA 1e-5 10.9% → 7.6%); see "AKAZE on the real 0c3d (item 0c)". Masked descriptors as the pad's replacement (2026-11-02): lose on the selection rule (best: v1 FRR @ FA 1e-5 tied, v1 impostor max 7 vs 6, real B 31 vs 28 rejects); owner kept pad-20 (2026-11-02); masked code moved off the libfprint branch into `akaze/masked.patch` |
| 0d | NIST SD 302 registration (23% cross-device) fixed, or NIST genuine results restricted to a protocol that registers | ≥ 80% of NIST probes registered, or the protocol change is written here. Done: 85.0% of NIST probes registered after dropping device L and ordering devices; see DATASETS.md |
| 0e | Harness: `nbis` matcher (libfprint's bozorth3, `tools/bz3eval.c`), per-stage sparse scores, per-pair timing and keypoint counts, dev/test split flag | smoke run on 2 sets for every matcher. Done (US-FPR-5) |
| 0f | Fidelity: the libfprint build through `virtual_image` (enroll → serialize → verify/identify) | identical scores to the harness on ≥ 10,000 pairs per C matcher, plus NBIS. Done (US-FPR-7): `akaze_c`, `sigfm`, `sigfm_fix` 10,560 pairs (211,200 stage scores) each, NBIS 12,672 pairs, every score identical on x86-64 and on aarch64 (Pi 4); README Tables P1-6 and P2-10 |

### AKAZE on the real 0c3d (item 0c)

Dev data only: our 0c3d captures of one person (scores only) and v1.
Protocol A = the README real-sensor table (2026-10-30 sessions, 201
genuine / 2,709 impostor attempts); protocol B = all 396 captures to date
(296 / 3,564). Both enrol each finger from the 10 presses of one session
(best of 10); threshold 10 for the inlier counts, 24 for SIGFM.

**Cause.** AKAZE (OpenCV and the bit-identical C port) only places a
keypoint where its rotated MLDB descriptor window fits:
border = round(10√2 · sigma_size) + 1 = 29 px at the finest level, i.e.
14.5 native px on the 2× (192²) image. At 2× no keypoint on a real capture
is closer than 13.5 native px to the frame edge, so AKAZE uses the central
~50% of the frame. SIFT (`ftsift_strict`, `sigfm`) detects to 1–2 native
px from the edge, with 37–40% of its keypoints within 12 native px of it.
On a press placed off the enrolled presses the shared skin is a strip
along the edges, mostly in AKAZE's dead band. Evidence:

- Keypoints per capture (p1 / p50 / p99): `akaze_c` 212 / 258 / 309 (never
  reaches the 384 cap), `ftsift_strict` 253 / 410 / 512, `sigfm` 145 / 268
  / 408. Keypoint count does not separate rejects (AKAZE-only rejects:
  246–298).
- Genuine score p1 / p5 / p10 / p25 / p50, protocol A: `akaze_c` 0 / 2 / 7
  / 19 / 35, `ftsift_strict` 2 / 7 / 14 / 23 / 42, `sigfm` 0 / 0 / 123 /
  3491 / 25716. Impostor p50 / p99 / max: `akaze_c` 0 / 3 / 4,
  `ftsift_strict` 2 / 4 / 5, `sigfm` 0 / 0 / 8. AKAZE's impostor tail is
  the lowest; its genuine low tail is what differs.
- Over 1,108 genuine pairs binned by frame overlap (< 0.30 / 0.30–0.45 /
  0.45–0.60 / 0.60–0.80 / ≥ 0.80), the `akaze_c` median score is 3 / 8 /
  19 / 35 / 62 against `ftsift_strict`'s 14 / 19 / 28 / 41 / 59, and the
  share with `akaze_c` < 10 is 0.98 / 0.65 / 0.12 / 0.03 / 0.00. The 9
  AKAZE-only rejects of protocol A are mostly full-contact, good-contrast
  presses with frame overlap 0.18–0.64 (median 0.40, vs 0.69 for accepted
  pairs).
- The keypoint and match caps change no reject (capped and uncapped
  `akaze_c` both reject 23 in A, 48 in B).

**Fix, frozen.** The prepared image is upscaled 3× instead of 2× and padded
before the scale space; keypoint positions are shifted back. Detector
threshold (1e-4, 5e-5: no reject changes) and CLAHE clip (1–4: ±3 rejects,
noise) were swept and left. Frozen `akaze_c` parameters (libfprint
`sift-matcher` branch and `bench/matchers.py` defaults, which agree):

| parameter | value | source |
|---|---|---|
| upscale (bicubic) | 3× (96² → 288²) | `FPI_AKAZE_UPSCALE` 3; `FPBENCH_AKAZE_UPSCALE` default 3 |
| CLAHE | 4×4 tiles, clip 2.0 | `CLAHE_TILES`, `CLAHE_CLIP` in `fpi-keypoint-prepare.c`; `FPBENCH_AKAZE_CLAHE_CLIP` default 2.0 |
| padding | 20 px per side of the prepared image (288² → 328²), replicate (edge pixels repeated) | `FPI_AKAZE_PAD` 20; `FPBENCH_AKAZE_PAD` 20, `FPBENCH_AKAZE_PAD_MODE` replicate |
| detector threshold | 0.0002 | `FPI_AKAZE_THRESHOLD`; `FPBENCH_AKAZE_THRESHOLD` |
| scale space | 4 sublevels per octave, octaves while ≥ 80 px wide: 328² → 164² → 82², 3 octaves, 12 levels | `FPI_AKAZE_SUBLEVELS`, `fpi_akaze_scale_space_new()` |
| keypoints kept | 384 strongest | `FPI_AKAZE_MAX_KEYPOINTS`; `FPBENCH_AKAZE_MAX_KP` |
| matching | Hamming, ratio 3/4, mutual, rotation ±45°, scale 0.85–1.15, inlier distance 3 native px (9 px at 3×), 64 candidate matches, 50 seeds | `fpi-keypoint-match.c/.h`; `AkazeC.ransac_px` = 3 × upscale |

Valid paddings at 3× are those that keep exact halving per octave (14–24
px); 3× with pad 14–24 gives 11–12 / 28–31 rejects (A / B), a plateau,
not a lucky point. Finest-level keypoints now reach 3 native px from the
frame edge (measured minimum 2.2); 20% of keypoints lie in the former dead
band, and every real frame reaches the 384 cap (uncapped p50 896).
`fpi_akaze_extract()` and `fpi_keypoint_prepare_image()` (2×, no pad) are
unchanged and still bit-identical to OpenCV; `akaze_det` stays on that path.
`FPBENCH_AKAZE_UPSCALE=2 FPBENCH_AKAZE_PAD=0` reproduces the old `akaze_c`
scores exactly.

**Before / after** (threshold 10 on the real sets; v1 on the compute VM,
range = bootstrap over fingers, 5th–95th percentile):

| | real A rejects | real B rejects | real impostor max (A / B) | v1 zero-FA threshold | v1 FRR there | v1 FRR @ FA 1e-5 | v1 impostor max |
|---|---:|---:|---:|---|---:|---|---:|
| `akaze_c` 2×, no pad (old) | 23 | 48 | 4 / 4 | 9 (7–9) | 15.8% | 10.9% (9.4–14.4%) | 8 |
| `akaze_c` 3×, pad 20 (frozen) | **11** | **28** | 4 / 5 | 7 (7–7) | 8.5% | **7.6% (6.1–9.7%)** | 6 |
| `ftsift_strict` | 14 | 38 | 5 / 5 | | | | |
| `sigfm` @ 24 | 14 | 27 | 8 / 8 | | | | |
| `sigfm_fix` @ 24 | 12 | 22 | 8 / 8 | | | | |

No false accepts on the real sets for any row. Of the old 23 protocol A
rejects, 12 are now accepted and none newly rejected. The 11 left: 9
rejected by all three matchers (8 thumb presses and one with ~0 overlap to
any enrolled press: enrolment coverage) and 2 borderline left-little
presses. 3× without padding was rejected: it raises the v1 impostor max to
9 and the zero-FA threshold to 10. Padding alone (12 px replicate at 2×:
14 / 33 rejects, v1 FRR @ FA 1e-5 9.7%) is the cheaper fallback.

**Remaining gaps** (accepted, not fixed by 0c):

- Protocol B is one reject above SIGFM (28 vs 27) and above `sigfm_fix`
  (22): 0c's "at SIGFM's level or lower" holds on protocol A (11 vs 14)
  only, and B is this accepted gap. 10 of the 28 are day-2 left-thumb presses rotated
  62–81° from enrolment, rejected by the ±45° rotation limit that
  `ftsift_strict` shares (0 in protocol A); `sigfm` and OpenCV
  `akaze`+RANSAC accept them. Widening the limit is a false-accept
  question for the final run and is not changed here; without it the real
  impostor max stays 4–6.
- Cost: extract 11.4 → 34.2 ms and typical match 0.92 → 2.04 ms per pair
  (i7-13700KF, one thread, real frames, which now reach the 384 cap);
  verify 30 → 75 ms, identify 10 195 → 442 ms. Not measured on the Pi 4;
  at the usual 4–6× that is verify ~0.30–0.45 s and identify 10
  ~1.8–2.7 s on real frames, against the 2 s budget. The worst-case match
  is cap-bound and unchanged; the worst-case extract must be re-measured
  (item 0b below).
- One person's captures: a dev-data fit, re-checked on test (new sessions
  and people) after the freeze.

**Border-aware (masked) descriptors instead of the pad** (2026-11-02,
dev data only). The pad puts invented pixels into the scan, so masked
descriptors were tried as its replacement: no pad, keypoints detected to
`border` sigma_size from the edge, descriptor bits whose sample cells fall
outside the image masked out, Hamming over the bits valid in both
(normalised to 486), pairs under a `floor` of valid bits no candidates
(`FPBENCH_AKAZE_MASK=1`, `FPBENCH_AKAZE_BORDER`, `FPBENCH_AKAZE_MIN_BITS`).
"Floor first" (`FPBENCH_AKAZE_FLOOR_FIRST=1`, bench only, same selection
as `keep_strongest()`) drops keypoints under the floor before keeping the
384 strongest, so they take no cap slots. Selection rule, fixed before the
runs: primary v1 FRR @ FA 1e-5 (bootstrap range) with v1 impostor max and
zero-FA threshold not worse than pad 20; secondary real A/B rejects with
real impostor max ≤ 5; tie → fewer knobs. Real sets local (threshold 10),
v1 on the compute VM; the two control rows are the US-FPR-3-4 VM files,
re-checked with the current code (0 of 3,528 fvs cells differ for each).

| variant | real A rejects | real B rejects | real imp max (A / B) | v1 zero-FA thr | v1 FRR there | v1 FRR @ FA 1e-5 | v1 imp max |
|---|---:|---:|---:|---|---:|---|---:|
| pad 20 replicate (frozen) | **11** | **28** | 4 / 5 | **7 (7–7)** | **8.5%** | **7.6% (6.1–9.7%)** | **6** |
| no pad, unmasked | 16 | 34 | 5 / 6 | 10 (8–10) | 12.7% | 9.2% (7.6–11.9%) | 9 |
| masked, border 2, floor 162 | 14 | 35 | 4 / 4 | 8 (7–8) | 12.8% | 10.4% (8.5–12.7%) | 7 |
| masked, border 2, floor 120 | 12 | 32 | 4 / 4 | 9 (7–9) | 14.6% | 10.3% (8.5–12.7%) | 8 |
| masked floor first, border 2, floor 162 | 13 | 34 | 5 / 5 | 9 (7–9) | 12.2% | 8.0% (6.4–11.5%) | 8 |
| masked floor first, border 2, floor 243 (best masked) | 12 | 31 | 4 / 5 | 8 (7–8) | 10.3% | 7.6% (6.2–11.0%) | 7 |
| masked, border 1, floor 120 / 162 / 243 | 14 / 14 / 16 | 36 / 36 / 38 | 4 / 4–5 | | | | |
| masked, border 2, floor 243 | 14 | 35 | 4 / 4 | | | | |
| masked, border 3, floor 120 / 162 / 243 | 13 / 13 / 13 | 33 / 33 / 34 | 4–5 / 4–5 | | | | |
| masked floor first, border 2, floor 120 | 12 | 32 | 4 / 5 | | | | |
| masked floor first, border 2, floor 324 / 405 | 13 / 14 | 31 / 31 | 4–5 / 6–7 | | | | |

No false accepts on the real sets for any row. v1 was run for the masked
cells that were best or default on the real sets (~100 min each on the VM);
the rest stopped at the real sets: border 1 is worse than 2 everywhere,
border 3 no better, and with floor first the border hardly matters
(keypoints within 2 sigma_size of the edge are nearly all under a floor of
162: border 1 and 2 give identical real score matrices at floors 162 and
243, border 3 differs in 175 and 2 of 156,816 cells).
Floors above 243 raise the real impostor max to 6–7.

**Result: masking loses; the owner kept pad-20 (2026-11-02).** No
masked variant meets the rule. The best, floor first at 243, ties pad 20
on v1 FRR @ FA 1e-5 (7.6%, range 6.2–11.0% vs 6.1–9.7%) but has a higher v1
impostor max (7 vs 6) and zero-FA threshold (8 vs 7, FRR there 10.3% vs
8.5%), and 3 more real B rejects (31 vs 28, A 12 vs 11). On the real B set
no masked variant accepts any press that pad 20 rejects. Masking does beat
no pad on every column (best masked v1 imp max 7 vs 9, FRR @ FA 1e-5 7.6%
vs 9.2%), so if the pad is ruled out on principle it is the better of the
two pad-free options, at the cost above.

Why it loses, as far as measured: masked keypoints are partial (at border
2 only 43% have all 486 bits, 20% are under 162; floor first at 243: 63%
complete), and partial descriptors are weaker evidence in the ratio test
and the inlier count than the replicated-edge descriptors, which still
describe real edge-row pixels. The 384 cap is part of it: uncapped (1,024)
masked border 2 / floor 162 gives real A / B 8 / 25 against pad 20's 9 / 25,
but with real impostor max 7 vs 6 and ~1.6× the match time, so raising the
cap is no fix within the cost bound.

Cost (real p01 frames, i7-13700KF, one thread; not a formal measurement):

| variant | keypoints | stored bytes per image (p50) | extract | match p50 |
|---|---:|---:|---:|---:|
| pad 20 | 384 | 26,496 | 36.5 ms | 2.01 ms |
| no pad | 384 | 26,496 | 27.5 ms | 2.02 ms |
| masked (any floor, border 1–3) | 384 | 49,920 (+61 B mask per keypoint) | 29.0–29.5 ms | 2.44–2.60 ms |
| masked floor first | 384 | 49,920 | 34.3–36.1 ms | 2.48–2.60 ms |

The harness on the VM (14 workers, coarse histogram) gives a masked v1 C
match p50 of 5.2 ms per pair against 3.7 ms for pad 20 on fvs alone (no
per-pair timing in the older v1 control files). The mask depends only on
the keypoint's position, scale and angle, so it could be recomputed at
match time instead of stored; not tried.

Frozen parameter rows: unchanged (pad 20 replicate, no mask); the owner
kept pad-20 on 2026-11-02. The masked API (`fpi_akaze_extract_masked()`,
`fpi_akaze_match_score_masked()`, `fpi_keypoint_match_score_masked()` and
their tests) was then taken off the libfprint `sift-matcher` branch and kept
as [`akaze/masked.patch`](../akaze/masked.patch); its header says how to
apply it and rebuild `libakaze_c.so` to reproduce the masked rows above.
Without it `FPBENCH_AKAZE_MASK=1` stops with an error naming the patch;
default `akaze_c` scores are unchanged.

## Data and splits

All public sets are pooled: every probe is tried against every template of
every set (cross-set impostors included), as before.

- **Dev** (seen while tuning; used to choose thresholds): FVC 2000/2002/2004
  B, Neurotechnology, FVS, MINEX, Tsinghua, UNSW 2D, our own 0c3d captures
  (the 396 captures to date, protocol B of item 0c).
- **Test** (never used to tune; safety numbers are reported here): NIST
  SD 302 (b, c, d), PolyU cross-session, SOCOFing and Family as strangers,
  new 0c3d sessions / people collected after the freeze.
- The split is `public_sets.TEST_SETS` = {`nist302_plain`, `polyu_cross`,
  `socofing`, `family`}; every other set is dev (`public_sets.split()`,
  stored per template in B and per stranger in C; a B probe's split is its
  owner finger's). Pooling means a test probe is also tried against dev
  templates and vice versa, so: thresholds are chosen on attempts whose
  probe and template are both dev; safety is reported on attempts whose
  **probe** is test data (B test probes and all C strangers, against every
  template), as C strangers always were.
- Same-identity pairs (sister datasets, same finger on two devices) are
  excluded from impostors, as now. Same-person-other-finger and kin pairs are
  kept and reported separately as well as pooled.

Final dataset counts (`public_sets.index()` and `public_sets.strangers()`
on `public-datasets/`, 2026-11-02; impressions split per finger: the first
half, at least one, enrol and the rest are probe impressions,
`big_eval.run_b`):

| set | split | fingers | impressions | probe impressions |
|---|---|---:|---:|---:|
| FVC 2000/2002/2004 DB1–4 B (12 sets) | dev | 120 | 960 | 480 |
| `neuro_crossmatch` | dev | 51 | 408 | 204 |
| `neuro_uareu` | dev | 65 | 520 | 260 |
| `fvs` | dev | 21 | 168 | 84 |
| `minex` | dev | 400 | 797 | 397 |
| `tsinghua` | dev | 320 | 640 | 320 |
| `unsw2d` | dev | 1,500 | 5,975 | 2,990 |
| **dev, B** | | **2,477** | **9,468** | **4,735** |
| `polyu_cross` | test | 336 | 2,976 | 1,488 |
| `nist302_plain` | test | 2,000 | 8,631 | 4,693 |
| **test, B** | | **2,336** | **11,607** | **6,181** |
| **B total** | | **4,813** | **21,075** | **10,916** |
| `socofing` (C, strangers) | test | 6,000 (600 people) | 6,000 | 6,000 |
| `family` (C, strangers) | test | 1,500 (300 people) | 1,500 | 1,500 |

Scale: B has ≤ 21,832 probe patches (2 per probe impression) against the
fingers whose enrolment yields all 20 stage patches (≈ 4.5 k templates;
the exact count is a run output, printed and stored as `templates`):
≈ 1.0 × 10⁸ template attempts. C: 7,500 stranger images, ≤ 2 patches each
(SOCOFing gave 11,743 and Family 745 patches in v2) ≈ 5.6 × 10⁷.

## Frozen run settings

Every final-run B/C/S job is

```
PYTHONNOUSERSITE=1 python3 bench/big_eval.py --data <public-datasets> \
  --matcher <nbis|sigfm|sigfm_fix|akaze_c> --stages 20 --derive 5,10,15 \
  --jitter 20 --probes 2 --floor <floor below> \
  --strangers socofing,family --synthetic --synthetic-derived 1 \
  --synthetic-adv 2 --out <dir>
```

with no `FPBENCH_*` variable set (all defaults).

| setting | value | source |
|---|---|---|
| sensor model | 96 × 96 patches (`SIZE`), public images rescaled to 542 dpi (`FPBENCH_SENSOR_DPI` default), `cv2.INTER_AREA`; elan 3-segment percentile normalisation | `public_sets.py` `SIZE`, `SENSOR_DPI`, `thirds()`; `big_eval.load_scaled()` |
| stage count | 20 enrolled patches per template; 5 / 10 / 15 derived from the per-stage store | `--stages 20`, `--derive 5,10,15` (default) |
| jitter | patch centre ~ N(0, 20 px) per axis at sensor dpi, around the finger centre (probes: registered to the first enrolment impression where possible); ≤ 3n draws for n usable patches | `--jitter 20` (default); `big_eval.jittered()`; C strangers fixed at 20 in `c_worker()` |
| probes per impression | 2 patches per probe impression and per stranger image | `--probes 2` (default) |
| templates per finger | enrolment patches spread over the enrolment impressions, ⌈20 / impressions⌉ per impression, first 20 kept; fingers with fewer than 20 usable are dropped | `big_eval.run_b()` |
| seeds | no global seed; each impression's patch RNG is `random.Random(crc32(id))`, id = `<finger>/<i>` (enrolment impression i), `<finger>/p<i>` (probe impression i), `<finger>` (stranger image); synthetic frames `default_rng(crc32(name))`. So every matcher sees the same patches on every machine | `big_eval.run_b()`, `run_c()`; `synthetic._rng()` |
| synthetic probes (part S) | data-independent set of `synthetic.probes()`, the first enrolled patch of every template inverted, mirrored and both, and 2 seeds of each adversarial kind (`checker2`, `sp50`, `gauss_s40`, `uniform`) | `--synthetic --synthetic-derived 1 --synthetic-adv 2` (defaults) |
| score floor of the per-stage store | `akaze_c` 5; `sigfm`, `sigfm_fix` 9; `nbis` 9 (each the matcher's lowest reported threshold − 1). Derived 5/10/15-stage results are exact at and above it; the 20-stage matrix is complete regardless. A frozen threshold − 2 (wolves) below the floor is reported as a deviation | `big_eval.main()` default `min(MATCH.thresholds) - 1`; `matchers.py` `thresholds` |
| bootstrap | over fingers, 200 resamples, `default_rng(0)`, 5th–95th percentile | `summarize.stats()` |

Not in the final-run scoring: part A (`--own-captures`), and the real 0c3d
sets, which are scored with `bench/cross_finger.py` at the same frozen
thresholds.

## Matchers (frozen parameters)

The final run scores exactly four matchers:

| matcher | role |
|---|---|
| `nbis` | baseline the maintainers asked for |
| `sigfm` | !530 as shipped (`bc986621`), reference |
| `sigfm_fix` | !530 + ordering fix + 176 cap, what !530 would likely merge |
| `akaze_c` | C AKAZE candidate: 3× upscale, 20 px replicate pad (item 0c) |

Not in the final run: `ftsift_strict` (C SIFT; dropped 2026-11-01, its
earlier results stay in the README appendix), masked `akaze_c` (item 0c),
and OpenCV `akaze`, which is run only on dev data as a check that
`akaze_c` reproduces it and takes no part in the decision.

Frozen parameters (sources at the commits in "Frozen sources and
environment"; the harness defaults equal the libfprint constants):

| matcher | parameters | source |
|---|---|---|
| `nbis` | frame unscaled, not inverted; mindtct `g_lfsparms_V2`, perimeter minutiae removed (`FPI_IMAGE_PARTIAL`), ppmm 0; first 200 minutiae kept (`MAX_BOZORTH_MINUTIAE`); bozorth3 score per enrolled image, best over the stages | `nbis/nbis.c`, libfprint `nbis/include/bozorth.h`; `matchers.Nbis` |
| `sigfm` | !530 `sigfm.cpp` unmodified: OpenCV `SIFT::create()` defaults on the raw frame, BFMatcher kNN 2, ratio `distance_match` 0.75, `length_match` 0.05, `angle_match` 0.05, `min_match` 5; features through `sigfm_serialize/deserialize_binary` like stored prints | `sigfm/src/sigfm.cpp:51-54`; `matchers.Sigfm` |
| `sigfm_fix` | `sigfm` + full `match` ordering + the 176 best matches by descriptor distance (`max_matches`) | `sigfm/patches/ssubbotin-ordering-and-cap.patch` |
| `akaze_c` | the frozen table under item 0c (3× bicubic upscale, CLAHE 4×4 / 2.0, 20 px replicate pad, threshold 0.0002, 4 sublevels, 384 keypoints, 61 B MLDB; Hamming, ratio 3/4, mutual, ±45°, scale 0.85–1.15, 9 px (3 native px) inliers, 64 candidate matches, 50 seeds, no refit) | `fpi-keypoint-akaze.h`, `fpi-keypoint-prepare.c`, `fpi-keypoint-match.c/.h`; `matchers.AkazeC` |

**SIGFM argument order.** Since 2026-11-01 (US-FPR-7-7) the harness calls
`sigfm_match_score(enrolled, probe)`, the order libfprint's
`fpi_print_sigfm_match()` (!530) uses; the score is not symmetric, and
every `sigfm` / `sigfm_fix` number in the final run is in this order
(`matchers.Sigfm.score()`).

Enrollment: 20 stages (the 0c3d default); 5/10/15 derived from the stored
per-stage scores. Per-stage scores are stored for every attempt whose best
stage score is ≥ a floor below every threshold of interest (values under
"Frozen run settings"); below the floor no subset of stages can reach a
threshold, so derived results stay exact.

## Threshold rule (fixed before the run)

Per matcher and stage count: **threshold = lowest score with zero false
accepts on dev + 1.** One threshold per matcher for all sensors; per-set
zero-FA thresholds are reported to show how stable it is.

## Safety metrics (on test, at the frozen threshold)

- False accepts / attempts, with the 95% Clopper-Pearson upper bound, per
  template attempt; also bootstrapped over fingers (attempts are not
  independent, fingers are the real sample size).
- Scaled to how libfprint is used: per verify (one print), per identify over
  10 enrolled fingers, per attacker session of k tries.
- Margin: max impostor score per set vs the threshold; impostor-tail fit
  (log survival) to estimate FMR at and above the threshold.
- Wolves / master prints: per probe, the number of templates it exceeds at
  threshold and at threshold − 2 (partial-print matchers are known to be
  vulnerable: Roy et al., MasterPrint, 2017). Lambs: per template.
- Correlated impostors: same person, other finger (NIST, UNSW: 10 fingers
  each); kin (Family: child vs parent, same finger).
- Synthetic probes against all templates: blank, noise (Gaussian,
  salt-and-pepper), gratings at ridge frequency in 8 orientations,
  checkerboards, inverted and mirrored versions of enrolled impressions, and
  a fixed-pattern test (one noise pattern added to two different fingers,
  the Goodix 5125 failure).
- Enrollment depth: FA and FRR at 5/10/15/20 stages, same threshold.
- Real 0c3d: inter-person impostors once a second person's captures exist
  (collected after the freeze, so they are test data; reported as an
  addendum, same frozen thresholds).

Accuracy (secondary): FRR of registered genuine attempts at the frozen
threshold and at FA 1e-5, pooled and per set; per-set average.

## Decision rule (fixed before the run)

1. A matcher **passes safety** if, on test at its frozen threshold, the
   95% upper bound on FMR per template attempt is ≤ 1e-5 (≤ 1 in 100,000,
   about the bar Windows Hello sets) and no synthetic probe is accepted.
2. Among those that pass, and that meet the cost budget below, the lowest
   pooled registered FRR on test wins. Differences inside the bootstrap
   range count as a tie, and a tie goes to the simpler or smaller code.
3. If none pass, the threshold that would pass is reported, and so is the FRR there.

## Phase 3: cost at scale

- **In the main run**: time and keypoint count of every pair match (C
  timer), so the distribution comes from ~10⁹ real pairs: p50/p99/p99.99/max
  against keypoint count. `big_eval.py` stores it in each result file:
  `pt_hist` (matches by own/other template × larger keypoint count of the
  pair in bins of `pt_kp_bin` × time in 1/8-octave ns bins), `pt_row_ns` and
  `pt_own_ns` per probe (-1: no timed match against its own template), the
  100 slowest pairs (`pt_slow`, `pt_slow_tname`), and keypoints per image
  (`pkp`, `tkp`, `ps_kp`). Pairs with an empty print (no keypoints or
  minutiae: no C match, score 0) are not timed, only counted per probe in
  `pt_untimed`. The time is measured with
  `CLOCK_MONOTONIC` in C around the match call (`timing/pairtime.c`), for
  the matchers whose match runs in C, while every worker is busy: compare
  matchers within one run's machine, and read single slow pairs as possible
  preemption.
- **Complexity curves**: extract and match time against keypoint count and
  image size (96², 2× upscaled, and the largest sensors on !530: 150×52,
  132×112, 112×112 ×2), up to the caps and past them with caps off, to show
  what the caps prevent (SIGFM uncapped is O(n⁴)).
- **Adversarial worst case**: the synthetic images that maximise keypoints,
  as probe and as every enrolled stage.
- **Scenarios**: verify (1 print × 20 stages); identify 10 prints (200
  matches); stress 5 users × 10 prints (1,000 matches); extract +
  serialize at enroll.
- **Machines**: i7-13700KF, EPYC 7302, both single-threaded on an idle machine;
  plus a Raspberry Pi 4 Model B (aarch64) as the slow reference, which also checks that scores are identical across architectures.
- **Memory**: bytes per stored print, peak RSS during identify.

Budget (pass/fail): worst-case verify ≤ 0.5 s and worst-case identify of 10
prints ≤ 2 s on the slow reference, with all-adversarial input; nothing over
5 s even in the stress scenario.

### Cost bound by construction (item 0b)

Caps (libfprint constants; bench defaults, `FPBENCH_*` overrides for sweeps;
the `ftsift_strict` columns are kept as the item 0b record, it is not in the
final run; SIGFM's bound is below the tables):

| cap | `akaze_c` | `ftsift_strict` |
|---|---|---|
| P, keypoints kept per image (strongest) | 384 (`FPI_AKAZE_MAX_KEYPOINTS`) | 512 (csift `max_kp`) |
| matcher point clamp | 1024 (`FPI_KEYPOINT_MAX_POINTS`), above P | same |
| M, candidate matches (closest) | 64 (`FPI_KEYPOINT_MAX_MATCHES`) | 64 |
| B, matches that seed transforms | 50 (`N_BEST`) | 50 |
| R, refits | 0 (no `REFIT` flag; ≤ `N_REFIT` = 3 if set) | 0 |
| D, descriptor | 61 B, Hamming (8 popcounts) | 128 B, L2 on bytes |

One match (`fpi_keypoint_match_score_full`), every loop bounded by a cap:

- nearest neighbours: P² distances, plus ≤ P² for the mutual check
  (one back search per ratio-passing keypoint): ≤ 2P² distances, 2P²·D bytes
- sort: ≤ P matches, O(P log P), then truncated to M
- transforms: pairs of the best min(M, B): ≤ B(B−1)/2 = 1,225, each tested
  against ≤ M matches; one more pass marks inliers; each refit ≤ 4 passes:
  ≤ (B(B−1)/2 + 1 + 4R)·M residuals
- no data-dependent iteration count: no RANSAC, no convergence loop.

| per | `akaze_c` distances (bytes) | `ftsift_strict` distances (bytes) | residuals (both) |
|---|---|---|---|
| match | 294,912 (18.0 M) | 524,288 (67.1 M) | 78,464 |
| verify, 20 stages | 5.90 M (360 M) | 10.5 M (1.34 G) | 1.57 M |
| identify 10, 200 matches | 59.0 M (3.60 G) | 105 M (13.4 G) | 15.7 M |

Extraction is fixed by image size, and by pixel count where it is not by P.
`akaze_c`: 96² upscaled to 288² and padded to 328² gives 3 octaves × 4 = 12
levels (328², 164², 82²: 564,816 level pixels, 3.1× the 184,320 of the
earlier 2×, unpadded setting; FED steps fixed by the level times); filters
and FED cost the same for every image. Detection candidates are strict 3×3 maxima, < 1/4 of
the pixels per level; refinement and orientation run on all of them (before
the top-P cut), descriptors on ≤ P. `ftsift_strict`: 192² doubled to 384²,
3 octaves × 3 intervals; candidates ≤ DoG pixels × 18 orientations, ≤ 5
interpolation steps each, sorted, descriptors on ≤ P.

SIGFM as shipped is bounded only by its comparator bug: ≤ 97 unique
matches on a 96 px frame, so ≤ C(97, 2) = 4,656 angle pairs. `sigfm_fix`
is bounded by its 176-match cap: ≤ C(176, 2) = 15,400 angle pairs.

Measured worst case (cap sweep, i7-13700KF, single thread, synthetic noise
and checkerboard frames): match 4.07 ms (`akaze_c`), 3.17 ms
(`ftsift_strict`); extract 12.8 ms, 68.4 ms. So verify ≈ 0.09 s / 0.13 s
and identify 10 ≈ 0.83 s / 0.70 s with the probe extracted once; Phase 3
replaces these with the adversarial runs and the slow reference. The
`akaze_c` extract figure is for the earlier 2×, unpadded setting; the
match bound holds at 3× + pad (same caps), the extract worst case is to be
re-measured (typical real frames: 11.4 → 34.2 ms, item 0c).

## Compute plan

At the rates measured on UNSW (≈ 2,100 template attempts/s on the box, 10
stages), part B is ~15 h per matcher at 10 stages, ~30 h at 20; part C
~+50%. NBIS is cheap. Runs go on the AI box and the compute VM (queues
`run_*.sh`), both OpenCV 4.10.0; the local machine (OpenCV 4.6.0) produces
no final-run scores. (The earlier ~4 days of wall time for five matchers
counted the local machine in the queue; four matchers on the box and VM
are re-estimated from the first matcher's run.)
Order: `akaze_c`, `sigfm_fix`, `sigfm`, `nbis`, so a decision is possible
after the first three. Per-pair times are compared only between matchers
run on the same machine.

---

Signed off by: Ryan Tregea date: 2026-11-02
