# Scaling public datasets to a small sensor

Public fingerprint datasets come from large sensors (typically 500 dpi, whole
fingertip). A small sensor sees a 96×96 window, at its own resolution. To
benchmark a matcher for such a sensor, every public image is rescaled to the
sensor's resolution and cut into sensor-sized patches. Getting the scale
right matters:

- it decides how much of the finger one patch covers, i.e. how many ridges
  and keypoints a matcher gets to work with;
- keypoint detectors are scale-dependent, so a wrong scale changes how many
  features are found and how well they repeat between impressions.

## Measuring the sensor's resolution

Resolution is measured through the ridge period: human ridge spacing is about
the same across people, so the period in pixels is proportional to dpi.

`public_sets.ridge_period()` takes the highest-contrast square region of an
image, and returns the period at the peak of its radially averaged Fourier
spectrum. Comparing the median period of your captures with that of the
500 dpi datasets gives your sensor's resolution:

```
bench/public_sets.py --data DIR --captures MY_CAPTURES   # MY_CAPTURES/<finger>/*.png
...
ridge period of the 500dpi sets: 9.85px (n=422)
ridge period of your captures: 10.67px (n=36)
=> your sensor is about 542 dpi (set FPBENCH_SENSOR_DPI)
```

These are the numbers for the Elan 04f3:0c3d (96×96). Use at least a few
dozen captures from several fingers, then run the benchmark with
`FPBENCH_SENSOR_DPI=<value>`. For a sensor that isn't 96×96, also change
`SIZE` in `bench/public_sets.py` (patches are square).

## Turning images into sensor patches

For each image (`bench/big_eval.py`):

1. rescale by `sensor_dpi / dataset_dpi` (area interpolation);
2. find the centre of the fingerprint (the area of high local contrast);
3. cut 96×96 patches around it, jittered by a Gaussian of 20 px (`--jitter`),
   like a finger placed slightly differently on each press. For genuine
   probes, the probe impression is first registered to the enrollment
   impression so the patches cover the same part of the finger
   ("registered" attempts in the results);
4. drop patches that are mostly background (standard deviation < 10) or have
   no ridge structure: the share of spectral energy at ridge frequencies must
   be ≥ 0.5 (real captures of the 0c3d are all ≥ 0.73; ink blots, smudges and
   card print are ~0.2);
5. normalize contrast the way the libfprint elan driver does (`thirds()`: a
   3-segment percentile stretch).

## When the ridge period estimate fails

Measure every new dataset, and check the result: after rescaling, the ridge
period should match the sensor's. Two datasets here needed manual work:

- **SOCOFing**: the images are 96×103 px for a whole fingertip, about
  162 dpi, not the declared 500. With ridges only ~3 px apart, the default
  search range (4–20 px periods) has no peak and the estimate sticks to the
  edge of the range. Searching 2.5–8 px gives a stable 3.2 px (IQR 3.0–3.56)
  → 162 dpi.
- **Family** (inked scans): over-inked blotches dominate the low frequencies
  and the estimate is unstable (650 or 928 dpi depending on the search range,
  neither credible). Ridges counted by hand in native-resolution 128 px crops:
  16–18 ridges, i.e. ~7.5 px period → ~380 dpi. A stranger-only set tolerates
  a ±15% scale error; a genuine-match set would not.

In both cases look at the images: render a few at a known zoom and count
ridges over a fixed distance. Datasets with a known, consistent resolution
(FVC, Neurotechnology, MINEX) only need a sanity check.

## Limits of this approach

- A patch cut from a large-sensor image is not a capture of a small sensor:
  noise, pressure, distortion and the sensor's own image processing differ.
  The benchmark measures matchers on realistic *amounts* of finger, not on
  the target sensor's images. Captures of the real sensor (part A, and the
  matching tests in libfprint) complement it.
- Upscaled low-resolution sets (SOCOFing at 3.3×) are smoother than real
  captures, which makes them weaker impostors; they are reported separately
  (part C).
