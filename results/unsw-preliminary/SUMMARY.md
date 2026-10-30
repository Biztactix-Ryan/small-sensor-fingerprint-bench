## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| ours | unsw2d_v3 | 1452 | 8347595 | 9 | 10 | 6.8% | 8.9% | 10 | 0 | 6.8% |
| sigfm_fix | unsw2d_v3 | 1452 | 8347595 | 133 | 134 | 6.1% | 8.2% | 24 | 236 | 3.5% |
| sigfm | unsw2d_v3 | 1452 | 8347595 | 100 | 101 | 6.2% | 8.2% | 24 | 72 | 3.8% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | ours unsw2d_v3 | sigfm_fix unsw2d_v3 | sigfm unsw2d_v3 |
|---|---|---|---|---|
| unsw2d | 5585 | 6.8% | 6.1% | 6.2% |

### Uncertainty, fixed false-accept rate and per-set average

Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean over sets with at least 20 registered attempts.

| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) | threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA |
|---|---|---|---|---|---|---|
| ours | unsw2d_v3 | 10 (9-10) | 6.8% (5.1-7.3%) | 8 (k=83) | 5.1% | 6.8% (1 sets) |
| sigfm_fix | unsw2d_v3 | 134 (84-134) | 6.1% (4.5-6.5%) | 34 (k=83) | 3.8% | 6.1% (1 sets) |
| sigfm | unsw2d_v3 | 101 (53-101) | 6.2% (4.5-6.6%) | 23 (k=83) | 3.8% | 6.2% (1 sets) |

### FRR by overlap with the enrolled area

Registered genuine attempts at each matcher's zero-FA threshold, by the share of the probe patch covered by the enrolled patches (from the patch offsets; rotation between impressions is ignored).

| matcher | run | 0-50% | 50-75% | 75-90% | 90-100% |
|---|---|---|---|---|---|
| ours | unsw2d_v3 | 50.0% (n=16) | 14.0% (n=286) | 9.7% (n=888) | 5.6% (n=4395) |
| sigfm_fix | unsw2d_v3 | 56.2% (n=16) | 15.4% (n=286) | 9.8% (n=888) | 4.6% (n=4395) |
