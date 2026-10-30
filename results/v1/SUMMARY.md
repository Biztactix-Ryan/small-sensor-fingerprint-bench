## Simulated enroll/verify (part B)

| matcher | run | fingers | impostor attempts | impostor max | zero-FA threshold | FRR registered @ zero-FA | FRR all @ zero-FA | default threshold | FA @ default | FRR registered @ default |
|---|---|---|---|---|---|---|---|---|---|---|
| ours | - | 568 | 1440034 | 8 | 9 | 18.6% | 53.0% | 10 | 0 | 20.6% |
| ours_raw | - | 568 | 1440034 | 7 | 8 | 18.9% | 53.1% | 10 | 0 | 23.2% |
| sigfm | - | 568 | 1440034 | 27 | 28 | 17.2% | 51.8% | 24 | 1 | 16.9% |
| sigfm_fix | - | 568 | 1440034 | 62 | 63 | 18.4% | 52.8% | 24 | 7 | 15.8% |
| sigfm_pre | - | 568 | 1440034 | 90 | 91 | 17.5% | 52.1% | 24 | 145 | 13.5% |

### FRR of registered genuine attempts per set, at each matcher's zero-FA threshold

| set | n | ours | ours_raw | sigfm | sigfm_fix | sigfm_pre |
|---|---|---|---|---|---|---|
| fvc2000_DB1_B | 22 | 95.5% | 86.4% | 72.7% | 81.8% | 86.4% |
| fvc2000_DB2_B | 40 | 32.5% | 40.0% | 35.0% | 32.5% | 22.5% |
| fvc2000_DB3_B | 43 | 72.1% | 69.8% | 65.1% | 74.4% | 69.8% |
| fvc2002_DB1_B | 32 | 21.9% | 18.8% | 18.8% | 21.9% | 21.9% |
| fvc2002_DB2_B | 60 | 13.3% | 10.0% | 6.7% | 13.3% | 16.7% |
| fvc2002_DB3_B | 6 | 66.7% | 83.3% | 83.3% | 83.3% | 50.0% |
| fvc2004_DB1_B | 14 | 71.4% | 57.1% | 64.3% | 57.1% | 64.3% |
| fvc2004_DB2_B | 61 | 75.4% | 77.0% | 75.4% | 75.4% | 75.4% |
| fvc2004_DB3_B | 68 | 44.1% | 42.6% | 42.6% | 45.6% | 44.1% |
| fvc2004_DB4_B | 8 | 37.5% | 37.5% | 37.5% | 37.5% | 25.0% |
| fvs | 166 | 0.0% | 0.6% | 0.0% | 0.0% | 0.0% |
| minex | 39 | 79.5% | 79.5% | 71.8% | 74.4% | 76.9% |
| neuro_crossmatch | 378 | 7.7% | 5.0% | 4.5% | 5.3% | 7.1% |
| neuro_uareu | 474 | 6.1% | 9.9% | 7.8% | 8.4% | 5.3% |
