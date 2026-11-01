## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| ours_det | s10 | 568 | 1440034 | 9 | 10 | 20.0% | 53.9% | 10 | 0 | 20.0% |
| ours_det | s15 | 562 | 1401829 | 9 | 10 | 17.4% | 52.5% | 10 | 0 | 17.4% |
| ours_det | s25 | 563 | 1414977 | 9 | 10 | 15.7% | 51.0% | 10 | 0 | 15.7% |
| ours_det | s5 | 573 | 1468151 | 8 | 9 | 21.9% | 55.5% | 10 | 0 | 23.8% |
| sigfm_fix | s15 | 562 | 1401829 | 55 | 56 | 16.6% | 51.7% | 24 | 6 | 14.8% |
| sigfm_fix | s25 | 563 | 1414977 | 55 | 56 | 14.3% | 49.7% | 24 | 7 | 12.7% |
| sigfm_fix | s5 | 573 | 1468151 | 55 | 56 | 22.0% | 55.6% | 24 | 2 | 18.9% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | ours_det s10 | ours_det s15 | ours_det s25 | ours_det s5 | sigfm_fix s15 | sigfm_fix s25 | sigfm_fix s5 |
|---|---|---|---|---|---|---|---|---|
| fvc2000_DB1_B | 22 | 95.5% | 77.3% | 63.6% | 100.0% | 63.6% | 54.5% | 77.3% |
| fvc2000_DB2_B | 40 | 35.0% | 27.5% | 25.0% | 32.5% | 25.0% | 20.0% | 37.5% |
| fvc2000_DB3_B | 43 | 72.1% | 67.4% | 65.1% | 72.1% | 65.1% | 60.5% | 72.1% |
| fvc2002_DB1_B | 32 | 28.1% | 28.1% | 21.9% | 34.4% | 18.8% | 18.8% | 34.4% |
| fvc2002_DB2_B | 60 | 23.3% | 13.3% | 8.3% | 23.3% | 8.3% | 6.7% | 21.7% |
| fvc2002_DB3_B | 6 | 66.7% | 66.7% | 50.0% | 66.7% | 50.0% | 33.3% | 83.3% |
| fvc2004_DB1_B | 18 | 71.4% | 71.4% | 71.4% | 55.6% | 57.1% | 57.1% | 55.6% |
| fvc2004_DB2_B | 61 | 77.0% | 71.2% | 71.2% | 82.0% | 72.9% | 69.5% | 80.3% |
| fvc2004_DB3_B | 68 | 45.6% | 41.2% | 39.7% | 58.8% | 42.6% | 42.6% | 63.2% |
| fvc2004_DB4_B | 9 | 37.5% | 25.0% | 25.0% | 44.4% | 50.0% | 37.5% | 44.4% |
| fvs | 166 | 0.0% | 0.0% | 0.0% | 0.0% | 0.6% | 0.6% | 1.2% |
| minex | 39 | 84.6% | 79.5% | 76.9% | 82.1% | 74.4% | 71.8% | 76.9% |
| neuro_crossmatch | 386 | 8.2% | 6.0% | 5.1% | 11.1% | 3.5% | 2.9% | 8.3% |
| neuro_uareu | 476 | 7.2% | 6.0% | 4.9% | 8.2% | 7.8% | 4.5% | 10.9% |

### Uncertainty, fixed false-accept rate and per-set average

Bootstrap over fingers (200 resamples, 5th-95th percentile). FA <= k: k = 1e-5 x impostor attempts. Per-set average: registered FRR at the zero-FA threshold, mean over sets with at least 20 registered attempts.

| matcher | run | zero-FA threshold (range) | FRR registered @ zero-FA (range) | threshold @ FA <= k | FRR registered @ FA <= k | per-set average FRR @ zero-FA | stored bytes per enrolled image |
|---|---|---|---|---|---|---|---|
| ours_det | s10 | 10 (8-10) | 20.0% (14.7-22.0%) | 8 (k=14) | 16.2% | 43.3% (11 sets) | 57296 |
| ours_det | s15 | 10 (8-10) | 17.4% (12.3-19.6%) | 8 (k=14) | 14.2% | 38.0% (11 sets) | 57195 |
| ours_det | s25 | 10 (8-10) | 15.7% (11.1-18.3%) | 8 (k=14) | 12.7% | 34.7% (11 sets) | 57249 |
| ours_det | s5 | 9 (8-9) | 21.9% (16.8-24.7%) | 7 (k=14) | 17.3% | 45.9% (11 sets) | 57304 |
| sigfm_fix | s15 | 56 (23-56) | 16.6% (13.0-19.6%) | 18 (k=14) | 14.1% | 34.8% (11 sets) | 139650 |
| sigfm_fix | s25 | 56 (26-56) | 14.3% (10.8-17.1%) | 20 (k=14) | 12.1% | 32.0% (11 sets) | 139772 |
| sigfm_fix | s5 | 56 (16-56) | 22.0% (15.9-24.9%) | 12 (k=14) | 17.1% | 44.0% (11 sets) | 139818 |

### FRR by overlap with the enrolled area

Registered genuine attempts at each matcher's zero-FA threshold, by the share of the probe patch covered by the enrolled patches (from the patch offsets; rotation between impressions is ignored).

| matcher | run | 0-50% | 50-75% | 75-90% | 90-100% |
|---|---|---|---|---|---|
| ours_det | s10 | 0.0% (n=3) | 32.8% (n=61) | 27.4% (n=230) | 17.8% (n=1117) |
| ours_det | s15 | 0.0% (n=1) | 26.3% (n=38) | 24.3% (n=140) | 16.4% (n=1197) |
| ours_det | s25 | nan% (n=0) | 20.8% (n=24) | 16.7% (n=78) | 15.6% (n=1295) |
| ours_det | s5 | 68.2% (n=22) | 38.8% (n=165) | 21.9% (n=383) | 17.5% (n=856) |
| sigfm_fix | s15 | 0.0% (n=1) | 26.3% (n=38) | 25.0% (n=140) | 15.3% (n=1197) |
| sigfm_fix | s25 | nan% (n=0) | 16.7% (n=24) | 14.1% (n=78) | 14.3% (n=1295) |
| sigfm_fix | s5 | 68.2% (n=22) | 37.6% (n=165) | 20.4% (n=383) | 18.6% (n=856) |
