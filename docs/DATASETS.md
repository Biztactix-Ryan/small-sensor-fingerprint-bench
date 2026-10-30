# Datasets

No fingerprint images are included in this repository, only instructions to
obtain them. Results computed on them are published in `results/`.

Put everything under one data directory (`--data DIR`, default `data/`) with
the layout below; `bench/public_sets.py --data DIR` prints what it finds.

The resolution column is what the images are rescaled from to the sensor's
resolution (542 dpi for the Elan 04f3:0c3d, see [SCALING.md](SCALING.md)).
"measured" means it was derived from the ridge period, because the dataset
does not state it or states it wrongly.

| | Sets | Fingers | Images |
|---|---|---|---|
| Enroll/verify (part B) | 20 | 4,813 | 19,585 |
| Strangers only (part C) | 2 | 7,500 | 7,500 |

## Enroll/verify (part B: genuine and impostor attempts)

| Set (directory) | Fingers × impressions | Resolution | Access | Source |
|---|---|---|---|---|
| `fvc2000_DB1_B` … `fvc2000_DB4_B` | 10 × 8 each | 500 dpi | public download | `http://bias.csr.unibo.it/fvc2000/Downloads/DB1_B.zip` (DB2_B, DB3_B, DB4_B likewise) |
| `fvc2002_DB1_B` … `fvc2002_DB4_B` | 10 × 8 each | 500 dpi, DB2: 569 dpi | public download | `http://bias.csr.unibo.it/fvc2002/Downloads/DB1_B.zip` … |
| `fvc2004_DB1_B` … `fvc2004_DB4_B` | 10 × 8 each | 500 dpi, DB2/DB3: 512 dpi | public download | `http://bias.csr.unibo.it/fvc2004/Downloads/DB1_B.zip` … |
| `neuro_crossmatch` | 51 × 8 | 500 dpi | public download | `https://www.neurotechnology.com/download/CrossMatch_Sample_DB.zip` |
| `neuro_uareu` | 65 × 8 | 512 dpi | public download | `https://www.neurotechnology.com/download/UareU_sample_DB.zip` |
| `fvs` | 21 × 8 | 394 dpi (measured) | public download | `http://fvs.sourceforge.net/fingerprint_bitmaps.zip` |
| `minex` | 400 × 2 | 500 dpi | public (NIST) | `https://github.com/usnistgov/minex` (`minexiii/validation`), then `bench/prepare_minex.py DIR` |
| `tsinghua` | 320 × 2 (normal + distorted) | 449 dpi (measured) | public download, terms not stated | Tsinghua Distorted Fingerprint Database (TDFD), `https://ivg.au.tsinghua.edu.cn/dataset/samples_TDFD/TDFD/Tsinghua%20Distorted%20Fingerprint%20Database.zip` |
| `unsw2d` | 1500 (150 subjects × 10) × 4 | 433 dpi (measured; the BMP headers say 500) | public download, research use only, cite | J. Hu, W. Zhou, *2D and 3D biometrics fingerprint dataset in contactless and labeled conditions*, Dryad, 2023, `https://doi.org/10.5061/dryad.612jm649q` (`2D_Database.7z` only) |
| `polyu_cross` | 336 × 6; 160 of them also × 6 in a second session 2–24 months later | 512 dpi (sensor; see SCALING.md) | research and non-commercial use only, cite | C. Lin, A. Kumar, *Matching Contactless and Contact-based Conventional Fingerprint Images for Biometrics Identification*, IEEE TIP 27, 2018: The Hong Kong Polytechnic University Contactless 2D to Contact-based 2D Fingerprint Images Database, contact-based part only |
| `nist302_plain` | 2000 (200 people × 10) × 2–4 plain impressions, each from a different device | 500 dpi | NIST, on request; terms agreed when obtaining it (no redistribution) | NIST Special Database 302, `https://nigos.nist.gov/datasets/sd302/request`: part d (auxiliary plain captures, devices K, L, M, P) and part b's segmented slaps (devices R, S), 500 ppi only |

Identities and data fixes (`public_sets.identity()` and `index()`):

- DB4 of each FVC year is synthetic (SFinGe).
- FVC2000 DB1 and DB2 share volunteers and finger numbering, and the two
  Neurotechnology sets are the same people on two sensors: treated as one
  finger, never counted as impostors of each other.
- Tsinghua's folders are recordings rather than fingers: many fingers were
  recorded more than once (folder pairs whose normal impressions match with
  hundreds of inliers, mostly nearby folder numbers), so Tsinghua is never
  used against itself as an impostor, only against the other sets.
- UNSW 2D: 25 impressions are byte-identical copies of another impression of
  the same finger (all of subject 6) and are dropped; fingers 8 and 9 of
  subject 138 are the same finger (SIGFM scores in the millions).
- PolyU: impressions sort session 1 first, so fingers with two sessions are
  enrolled from one and verified with the other.
- NIST SD 302: thumbs swapped per its errata (00002302 device L, 00002534
  and 00002561 device S, 00002420 device R).

Expected layout:

```
DIR/fvc2000_DB1_B/101_1.tif         (likewise every FVC set: <finger>_<impression>.tif/.bmp)
DIR/neuro_crossmatch/012_3_4.tif    (<subject>_<finger>_<impression>.tif)
DIR/neuro_uareu/012_3_4.tif
DIR/fvs/19_1.bmp
DIR/minex/minexiii/...              (git checkout), DIR/minex/png/a001_02.png (prepare_minex.py)
DIR/tsinghua/Tsinghua Distorted Fingerprint Database/<finger>/<image>.png
DIR/unsw2d/2D Database/<subject>_<finger>_<impression>.bmp
DIR/polyu_cross/contact-based_fingerprints/{first,second}_session/<finger>_<impression>.jpg
DIR/nist302_plain/images/auxiliary/flat/<device>/500/plain/png/<subject>_<device>_500_plain_<finger>.png
DIR/nist302_plain/images/baseline/<device>/500/slap-segmented/png/<subject>_<device>_500_slap_<finger>.png
```

## Strangers only (part C: one impression per finger)

| Set | Fingers | Resolution | Access | Source |
|---|---|---|---|---|
| `socofing` | 6000 (600 subjects × 10), `Real` folder only | 162 dpi (measured; the declared 500 is wrong) | free, Kaggle account | `https://www.kaggle.com/datasets/ruizgara/socofing` |
| `family` | 1500 (100 families × father/mother/child × 5 fingers), inked scans | ~380 dpi (counted by hand, see SCALING.md) | CC BY 4.0 | D. Maiti, D. Das, *Family Fingerprint Dataset*, Mendeley Data, 2023, `https://doi.org/10.17632/m4kz5ygxrn.1` |

Only SOCOFing's `Real` images are used: the `Altered` ones are synthetic
modifications of the same prints, not other fingers. About 30% of the Family
patches pass the quality filters (over-inked or faint scans are dropped).
SOCOFing and Family also serve to fit the compact descriptor codes
(`bench/fit_quant.py`), since part B never scores them.

```
DIR/SOCOFing/SOCOFing/Real/<subject>__<sex>_<hand>_<finger>_finger.BMP
DIR/family/FAMILY FINGERPRINT DATASET/FAMILY-<n>/<FATHER|MOTHER|CHILD>/FM<nnn>_<role><k>.png
```

## Obtained but not used

| What | Why not |
|---|---|
| UNSW 3D / contactless parts (`DS1-3.7z`) | contactless captures, not a contact sensor |
| PolyU contactless 2D images | contactless camera images |
| NIST SD 302a, 302b rolled prints (`U`, `V`) and 1000 ppi images | rolled nail to nail, unlike a press; 302a's resolution varies by device |
| NIST SD 302g (EBTS transactions), 302h (latents) | not plain impressions |
| FVC2002 DB1 synthetic blend, SFinGe demo (Windows installer) | synthetic; v1 couldn't register any synthetic impression |
| `latentOverlap` | overlapping latent prints |

## Not (yet) obtained

Free on request, licensed (no redistribution; results may be published):
NIST SD301, CASIA-FingerprintV5, FVC2006 (its DB1 is a 96×96 small-area
sensor). Paid: the FVC2000/2002/2004 "A" sets, used in the benchmarks posted
on libfprint MR !530.

Dataset index: [IAPR TC4 fingerprint datasets](https://iapr-tc4.org/fingerprint-datasets/).
