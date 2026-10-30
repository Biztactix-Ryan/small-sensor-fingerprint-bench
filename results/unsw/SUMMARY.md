## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| akaze | unsw2d_v3b | 1452 | 8321477 | 12 | 13 | 6.9% | 8.8% | 10 | 1 | 4.8% |
| ours | unsw2d_v3 | 1452 | 8347595 | 9 | 10 | 6.8% | 8.9% | 10 | 0 | 6.8% |
| sigfm_fix | unsw2d_v3b | 1452 | 8321477 | 133 | 134 | 6.2% | 8.2% | 24 | 236 | 3.6% |
| sigfm | unsw2d_v3b | 1452 | 8321477 | 100 | 101 | 6.2% | 8.3% | 24 | 72 | 3.9% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | akaze unsw2d_v3b | ours unsw2d_v3 | sigfm_fix unsw2d_v3b | sigfm unsw2d_v3b |
|---|---|---|---|---|---|
| unsw2d | 5585 | 6.9% | 6.8% | 6.2% | 6.2% |

### Uncertainty, fixed false-accept rate and per-set average

Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean over sets with at least 20 registered attempts.

| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) | threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA | stored bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| akaze | unsw2d_v3b | 13 (9-13) | 6.9% (3.9-7.3%) | 8 (k=83) | 3.8% | 6.9% (1 sets) | 21158 |
| ours | unsw2d_v3 | 10 (9-10) | 6.8% (5.1-7.3%) | 8 (k=83) | 5.1% | 6.8% (1 sets) | - |
| sigfm_fix | unsw2d_v3b | 134 (84-134) | 6.2% (4.6-6.6%) | 34 (k=83) | 3.9% | 6.2% (1 sets) | 141554 |
| sigfm | unsw2d_v3b | 101 (53-101) | 6.2% (4.5-6.7%) | 23 (k=83) | 3.9% | 6.2% (1 sets) | 141554 |

### FRR by overlap with the enrolled area

Registered genuine attempts at each matcher's zero-FA threshold, by the share of the probe patch covered by the enrolled patches (from the patch offsets; rotation between impressions is ignored).

| matcher | run | 0-50% | 50-75% | 75-90% | 90-100% |
|---|---|---|---|---|---|
| akaze | unsw2d_v3b | 68.8% (n=16) | 17.4% (n=288) | 10.1% (n=883) | 5.3% (n=4380) |
| ours | unsw2d_v3 | 50.0% (n=16) | 14.0% (n=286) | 9.7% (n=888) | 5.6% (n=4395) |
| sigfm_fix | unsw2d_v3b | 56.2% (n=16) | 15.6% (n=288) | 10.0% (n=883) | 4.6% (n=4380) |
| sigfm | unsw2d_v3b | 50.0% (n=16) | 15.6% (n=288) | 10.5% (n=883) | 4.6% (n=4380) |
