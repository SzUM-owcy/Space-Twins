# NASADEM vs COPDEM cross-check

Same patch centres, same `extract_patch` and features, only the DEM differs. Median of per-patch relative difference `(COPDEM - NASADEM) / NASADEM`.

| Region | patches | slope_p50 | slope_p90 | rms_height | tri_mean | relief_range |
|---|---|---|---|---|---|---|
| meteor_crater | 99 | -3.3% | +0.6% | +0.3% | -3.8% | +0.3% |
<!-- meteor_crater median slope_p50 NASADEM -> COPDEM: 1.23 -> 1.18 -->
| mauna_loa | 51 | +0.0% | +0.4% | +0.1% | +0.4% | +0.0% |
<!-- mauna_loa median slope_p50 NASADEM -> COPDEM: 4.77 -> 4.78 -->

Conclusion: differences are a few percent at most (well below the tens of percent that would warrant a README limitation), so NASADEM and COPDEM patches are treated as comparable.
