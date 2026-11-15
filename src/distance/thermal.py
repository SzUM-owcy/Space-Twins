"""Thermal: temperature-swing difference in Kelvin on one common fixed scale."""

from __future__ import annotations

import numpy as np
import pandas as pd

METHOD = "fixed_scale_kelvin_difference"


def thermal_distance(
    moon_swing_k: float | None, earth_swing_k: pd.Series, scale_k: float
) -> tuple[pd.Series, pd.Series]:
    """Return (normalised distance, raw |difference| in K); NaN when either side is missing.

    It compares the magnitude of the variation only; atmosphere, day length and thermal inertia still differ.
    """
    if moon_swing_k is None or not np.isfinite(moon_swing_k):
        nan = pd.Series(np.nan, index=earth_swing_k.index)
        return nan, nan.copy()
    diff = (earth_swing_k.astype(float) - float(moon_swing_k)).abs()
    return diff / scale_k, diff
