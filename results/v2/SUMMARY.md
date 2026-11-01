## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| akaze | v2 | 880 | 2576466 | 8 | 9 | 21.1% | 50.5% | 10 | 0 | 22.5% |
| ours | v2 | 880 | 2576466 | 8 | 9 | 24.4% | 53.2% | 10 | 0 | 26.8% |
| sigfm_fix | v2 | 880 | 2576466 | 57 | 58 | 26.5% | 54.4% | 24 | 9 | 22.9% |
| sigfm | v2 | 880 | 2576466 | 27 | 28 | 24.7% | 53.0% | 24 | 1 | 24.2% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | akaze v2 | ours v2 | sigfm_fix v2 | sigfm v2 |
|---|---|---|---|---|---|
| fvc2000_DB1_B | 22 | 45.5% | 95.5% | 77.3% | 68.2% |
| fvc2000_DB2_B | 40 | 17.5% | 32.5% | 27.5% | 27.5% |
| fvc2000_DB3_B | 43 | 53.5% | 72.1% | 69.8% | 62.8% |
| fvc2002_DB1_B | 32 | 18.8% | 21.9% | 25.0% | 21.9% |
| fvc2002_DB2_B | 60 | 8.3% | 13.3% | 13.3% | 10.0% |
| fvc2002_DB3_B | 6 | 50.0% | 66.7% | 66.7% | 50.0% |
| fvc2004_DB1_B | 14 | 71.4% | 71.4% | 57.1% | 57.1% |
| fvc2004_DB2_B | 61 | 75.4% | 75.4% | 77.0% | 75.4% |
| fvc2004_DB3_B | 68 | 27.9% | 44.1% | 45.6% | 44.1% |
| fvc2004_DB4_B | 8 | 25.0% | 37.5% | 50.0% | 50.0% |
| fvs | 166 | 0.0% | 0.0% | 0.6% | 0.0% |
| minex | 39 | 74.4% | 79.5% | 76.9% | 71.8% |
| neuro_crossmatch | 378 | 3.2% | 7.7% | 5.0% | 4.8% |
| neuro_uareu | 474 | 3.6% | 6.1% | 8.9% | 7.8% |
| tsinghua | 467 | 44.5% | 42.0% | 50.7% | 47.8% |

### Uncertainty, fixed false-accept rate and per-set average

Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean over sets with at least 20 registered attempts.

| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) | threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA | stored bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| akaze | v2 | 9 (8-9) | 21.1% (17.7-23.4%) | 7 (k=25) | 18.1% | 31.0% (12 sets) | 19848 |
| ours | v2 | 9 (8-9) | 24.4% (20.4-27.3%) | 7 (k=25) | 18.8% | 40.8% (12 sets) | - |
| sigfm_fix | v2 | 58 (28-58) | 26.5% (21.8-29.1%) | 21 (k=25) | 22.2% | 39.8% (12 sets) | 140089 |
| sigfm | v2 | 28 (21-28) | 24.7% (21.3-27.2%) | 15 (k=25) | 22.1% | 36.8% (12 sets) | 140089 |

### FRR by overlap with the enrolled area

Registered genuine attempts at each matcher's zero-FA threshold, by the share of the probe patch covered by the enrolled patches (from the patch offsets; rotation between impressions is ignored).

| matcher | run | 0-50% | 50-75% | 75-90% | 90-100% |
|---|---|---|---|---|---|
| akaze | v2 | 40.0% (n=5) | 31.7% (n=82) | 27.4% (n=310) | 19.2% (n=1481) |
| ours | v2 | 40.0% (n=5) | 35.4% (n=82) | 31.0% (n=310) | 22.3% (n=1481) |
| sigfm_fix | v2 | 40.0% (n=5) | 40.2% (n=82) | 33.5% (n=310) | 24.2% (n=1481) |
| sigfm | v2 | 60.0% (n=5) | 36.6% (n=82) | 31.6% (n=310) | 22.4% (n=1481) |

## Strangers only (part C)

| set | matcher | run | attempts | max score | FA @ default | default threshold |
|---|---|---|---|---|---|---|
| family | ours | v2 | 655600 | 6 | 0 | 10 |
| family | sigfm_fix | v2 | 655600 | 66 | 6 | 24 |
| family | sigfm | v2 | 655600 | 23 | 0 | 24 |
| socofing | ours | v2 | 10333840 | 9 | 0 | 10 |
| socofing | sigfm_fix | v2 | 10333840 | 57 | 31 | 24 |
| socofing | sigfm | v2 | 10333840 | 35 | 6 | 24 |
