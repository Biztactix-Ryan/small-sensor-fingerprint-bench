## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| akaze | nist302_plain | 86 | 28220 | 5 | 6 | 14.0% | 75.3% | 10 | 0 | 22.1% |
| akaze | polyu_cross | 56 | 35695 | 5 | 6 | 26.5% | 55.9% | 10 | 0 | 50.4% |
| ours_strict | nist302_plain | 86 | 28220 | 5 | 6 | 25.6% | 78.9% | 10 | 0 | 41.9% |
| ours_strict | polyu_cross | 56 | 35695 | 9 | 10 | 73.0% | 86.3% | 10 | 0 | 73.0% |
| q_tern128 | nist302_plain | 86 | 28220 | 10 | 11 | 16.3% | 76.2% | 10 | 3 | 14.0% |
| q_tern128 | polyu_cross | 56 | 35695 | 11 | 12 | 34.1% | 61.6% | 10 | 28 | 20.4% |
| sigfm | nist302_plain | 86 | 28220 | 35 | 36 | 43.0% | 84.9% | 24 | 1 | 41.9% |
| sigfm | polyu_cross | 56 | 35695 | 18 | 19 | 52.7% | 76.3% | 24 | 0 | 55.3% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | akaze nist302_plain | akaze polyu_cross | ours_strict nist302_plain | ours_strict polyu_cross | q_tern128 nist302_plain | q_tern128 polyu_cross | sigfm nist302_plain | sigfm polyu_cross |
|---|---|---|---|---|---|---|---|---|---|
| nist302_plain | 86 | 14.0% | - | 25.6% | - | 16.3% | - | 43.0% | - |
| polyu_cross | 226 | - | 26.5% | - | 73.0% | - | 34.1% | - | 52.7% |

### Uncertainty, fixed false-accept rate and per-set average

Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean over sets with at least 20 registered attempts.

| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) | threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA | stored bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| akaze | nist302_plain | 6 (6-6) | 14.0% (6.2-22.5%) | 6 (k=0) | 14.0% | 14.0% (1 sets) | 21475 |
| akaze | polyu_cross | 6 (6-6) | 26.5% (19.9-33.4%) | 6 (k=0) | 26.5% | 26.5% (1 sets) | 22079 |
| ours_strict | nist302_plain | 6 (6-6) | 25.6% (15.5-36.8%) | 6 (k=0) | 25.6% | 25.6% (1 sets) | 75461 |
| ours_strict | polyu_cross | 10 (7-10) | 73.0% (44.2-79.1%) | 10 (k=0) | 73.0% | 73.0% (1 sets) | 79908 |
| q_tern128 | nist302_plain | 11 (10-11) | 16.3% (8.1-25.0%) | 11 (k=0) | 16.3% | 16.3% (1 sets) | 22194 |
| q_tern128 | polyu_cross | 12 (11-12) | 34.1% (22.3-43.0%) | 12 (k=0) | 34.1% | 34.1% (1 sets) | 23502 |
| sigfm | nist302_plain | 36 (7-36) | 43.0% (28.0-51.0%) | 36 (k=0) | 43.0% | 43.0% (1 sets) | 153320 |
| sigfm | polyu_cross | 19 (8-19) | 52.7% (36.9-59.6%) | 19 (k=0) | 52.7% | 52.7% (1 sets) | 176435 |

### FRR by overlap with the enrolled area

Registered genuine attempts at each matcher's zero-FA threshold, by the share of the probe patch covered by the enrolled patches (from the patch offsets; rotation between impressions is ignored).

| matcher | run | 0-50% | 50-75% | 75-90% | 90-100% |
|---|---|---|---|---|---|
| akaze | nist302_plain | nan% (n=0) | 33.3% (n=6) | 12.5% (n=16) | 12.5% (n=64) |
| akaze | polyu_cross | 100.0% (n=2) | 77.8% (n=9) | 30.6% (n=36) | 22.3% (n=179) |
| ours_strict | nist302_plain | nan% (n=0) | 33.3% (n=6) | 25.0% (n=16) | 25.0% (n=64) |
| ours_strict | polyu_cross | 100.0% (n=2) | 100.0% (n=9) | 94.4% (n=36) | 67.0% (n=179) |
| q_tern128 | nist302_plain | nan% (n=0) | 16.7% (n=6) | 18.8% (n=16) | 15.6% (n=64) |
| q_tern128 | polyu_cross | 100.0% (n=2) | 77.8% (n=9) | 44.4% (n=36) | 29.1% (n=179) |
| sigfm | nist302_plain | nan% (n=0) | 66.7% (n=6) | 50.0% (n=16) | 39.1% (n=64) |
| sigfm | polyu_cross | 100.0% (n=2) | 88.9% (n=9) | 80.6% (n=36) | 44.7% (n=179) |
