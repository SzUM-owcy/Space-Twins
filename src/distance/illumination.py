"""Illumination: direct difference of the solar-visibility fraction (both bodies use the same definition)."""

from __future__ import annotations

import numpy as np
import pandas as pd

METHOD = "absolute_fraction_difference"


def illumination_distance(
    moon_fraction: float | None, earth_fraction: pd.Series, gamma: float = 1.0
) -> tuple[pd.Series, pd.Series]:
    """Return (distance = |diff| ** gamma, raw |difference|); NaN when either side is missing.

    No division by the Earth spread, so the value does not depend on the current Earth catalogue.
    """
    if moon_fraction is None or not np.isfinite(moon_fraction):
        nan = pd.Series(np.nan, index=earth_fraction.index)
        return nan, nan.copy()
    diff = (earth_fraction.astype(float) - float(moon_fraction)).abs()
    return diff**gamma, diff
