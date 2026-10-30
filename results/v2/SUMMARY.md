## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| ours | v2 | 880 | 2576466 | 8 | 9 | 24.4% | 53.2% | 10 | 0 | 26.8% |
| sigfm_fix | v2 | 880 | 2576466 | 62 | 63 | 26.1% | 54.2% | 24 | 12 | 22.2% |
| sigfm | v2 | 880 | 2576466 | 28 | 29 | 24.6% | 53.1% | 24 | 5 | 23.7% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | ours v2 | sigfm_fix v2 | sigfm v2 |
|---|---|---|---|---|
| fvc2000_DB1_B | 22 | 95.5% | 81.8% | 77.3% |
| fvc2000_DB2_B | 40 | 32.5% | 32.5% | 35.0% |
| fvc2000_DB3_B | 43 | 72.1% | 74.4% | 69.8% |
| fvc2002_DB1_B | 32 | 21.9% | 21.9% | 21.9% |
| fvc2002_DB2_B | 60 | 13.3% | 13.3% | 6.7% |
| fvc2002_DB3_B | 6 | 66.7% | 83.3% | 83.3% |
| fvc2004_DB1_B | 14 | 71.4% | 57.1% | 64.3% |
| fvc2004_DB2_B | 61 | 75.4% | 75.4% | 75.4% |
| fvc2004_DB3_B | 68 | 44.1% | 45.6% | 42.6% |
| fvc2004_DB4_B | 8 | 37.5% | 37.5% | 37.5% |
| fvs | 166 | 0.0% | 0.0% | 0.0% |
| minex | 39 | 79.5% | 74.4% | 71.8% |
| neuro_crossmatch | 378 | 7.7% | 5.3% | 5.0% |
| neuro_uareu | 474 | 6.1% | 8.4% | 7.8% |
| tsinghua | 467 | 42.0% | 49.3% | 45.8% |

### Uncertainty, fixed false-accept rate and per-set average

Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean over sets with at least 20 registered attempts.

| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) | threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA |
|---|---|---|---|---|---|---|
| ours | v2 | 9 (8-9) | 24.4% (20.4-27.3%) | 7 (k=25) | 18.8% | 40.8% (12 sets) |
| sigfm_fix | v2 | 63 (32-63) | 26.1% (21.5-28.5%) | 21 (k=25) | 21.8% | 40.2% (12 sets) |
| sigfm | v2 | 29 (24-29) | 24.6% (21.2-27.1%) | 16 (k=25) | 21.9% | 38.3% (12 sets) |

### FRR by overlap with the enrolled area

Registered genuine attempts at each matcher's zero-FA threshold, by the share of the probe patch covered by the enrolled patches (from the patch offsets; rotation between impressions is ignored).

| matcher | run | 0-50% | 50-75% | 75-90% | 90-100% |
|---|---|---|---|---|---|
| ours | v2 | 40.0% (n=5) | 35.4% (n=82) | 31.0% (n=310) | 22.3% (n=1481) |
| sigfm_fix | v2 | 60.0% (n=5) | 37.8% (n=82) | 33.2% (n=310) | 23.8% (n=1481) |

## Strangers only (part C)

| set | matcher | run | attempts | max score | FA @ default | default threshold |
|---|---|---|---|---|---|---|
| family | sigfm_fix | v2 | 655600 | 10 | 0 | 24 |
| family | sigfm | v2 | 655600 | 2 | 0 | 24 |
| socofing | sigfm_fix | v2 | 10333840 | 29 | 1 | 24 |
| socofing | sigfm | v2 | 10333840 | 15 | 0 | 24 |
