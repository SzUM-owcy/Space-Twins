"""Composition: body-relative percentile difference (ASTER MI on Earth and Diviner CF on the Moon are different quantities)."""

from __future__ import annotations

import numpy as np
import pandas as pd

METHOD = "body_relative_percentile"


def composition_distance(moon_percentile: float | None, earth_percentile: pd.Series) -> pd.Series:
    """|percentile difference| in [0, 1]; NaN when either side is missing (never zero).

    Percentiles come from frozen, versioned per-body reference distributions, so no Earth-catalogue std is used.
    """
    if moon_percentile is None or not np.isfinite(moon_percentile):
        return pd.Series(np.nan, index=earth_percentile.index)
    return (earth_percentile.astype(float) - float(moon_percentile)).abs()
