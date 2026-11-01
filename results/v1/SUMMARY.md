## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| ours | - | 568 | 1440034 | 8 | 9 | 18.6% | 53.0% | 10 | 0 | 20.6% |
| ours_raw | - | 568 | 1440034 | 7 | 8 | 18.9% | 53.1% | 10 | 0 | 23.2% |
| sigfm | - | 568 | 1440034 | 20 | 21 | 15.8% | 50.8% | 24 | 0 | 16.6% |
| sigfm_fix | - | 568 | 1440034 | 55 | 56 | 18.4% | 52.7% | 24 | 3 | 15.7% |
| sigfm_pre | - | 568 | 1440034 | 90 | 91 | 17.5% | 52.1% | 24 | 145 | 13.5% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | ours | ours_raw | sigfm | sigfm_fix | sigfm_pre |
|---|---|---|---|---|---|---|
| fvc2000_DB1_B | 22 | 95.5% | 86.4% | 68.2% | 77.3% | 86.4% |
| fvc2000_DB2_B | 40 | 32.5% | 40.0% | 25.0% | 27.5% | 22.5% |
| fvc2000_DB3_B | 43 | 72.1% | 69.8% | 60.5% | 69.8% | 69.8% |
| fvc2002_DB1_B | 32 | 21.9% | 18.8% | 21.9% | 25.0% | 21.9% |
| fvc2002_DB2_B | 60 | 13.3% | 10.0% | 6.7% | 13.3% | 16.7% |
| fvc2002_DB3_B | 6 | 66.7% | 83.3% | 50.0% | 66.7% | 50.0% |
| fvc2004_DB1_B | 14 | 71.4% | 57.1% | 57.1% | 57.1% | 64.3% |
| fvc2004_DB2_B | 61 | 75.4% | 77.0% | 73.8% | 77.0% | 75.4% |
| fvc2004_DB3_B | 68 | 44.1% | 42.6% | 41.2% | 45.6% | 44.1% |
| fvc2004_DB4_B | 8 | 37.5% | 37.5% | 37.5% | 50.0% | 25.0% |
| fvs | 166 | 0.0% | 0.6% | 0.0% | 0.6% | 0.0% |
| minex | 39 | 79.5% | 79.5% | 69.2% | 76.9% | 76.9% |
| neuro_crossmatch | 378 | 7.7% | 5.0% | 4.5% | 5.0% | 7.1% |
| neuro_uareu | 474 | 6.1% | 9.9% | 6.3% | 8.9% | 5.3% |

### Uncertainty, fixed false-accept rate and per-set average

Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean over sets with at least 20 registered attempts.

| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) | threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA | stored bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| ours | - | 9 (8-9) | 18.6% (13.8-20.5%) | 7 (k=14) | 14.4% | 40.7% (11 sets) | - |
| ours_raw | - | 8 (7-8) | 18.9% (15.3-22.4%) | 7 (k=14) | 16.7% | 40.0% (11 sets) | - |
| sigfm | - | 21 (15-21) | 15.8% (12.6-18.8%) | 12 (k=14) | 14.7% | 34.3% (11 sets) | 139858 |
| sigfm_fix | - | 56 (21-56) | 18.4% (12.7-21.1%) | 16 (k=14) | 14.7% | 38.8% (11 sets) | 139858 |
| sigfm_pre | - | 91 (58-91) | 17.5% (13.5-20.1%) | 46 (k=14) | 15.1% | 38.7% (11 sets) | - |

### FRR by overlap with the enrolled area

Registered genuine attempts at each matcher's zero-FA threshold, by the share of the probe patch covered by the enrolled patches (from the patch offsets; rotation between impressions is ignored).

| matcher | run | 0-50% | 50-75% | 75-90% | 90-100% |
|---|---|---|---|---|---|
| sigfm | - | 0.0% (n=3) | 24.6% (n=61) | 22.6% (n=230) | 14.0% (n=1117) |
| sigfm_fix | - | 0.0% (n=3) | 29.5% (n=61) | 25.2% (n=230) | 16.5% (n=1117) |
