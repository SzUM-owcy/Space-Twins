"""Top level: weighted arithmetic mean of the available component distances."""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def aggregate(
    distances: Mapping[str, pd.Series], weights: Mapping[str, float]
) -> tuple[pd.Series, pd.DataFrame]:
    """Return (total distance, weight actually applied per component and patch).

    A NaN component (or a zero weight) drops out and the remaining weights renormalise; never filled with 0.
    A patch with no available weight gets NaN.
    """
    index = next(iter(distances.values())).index
    num = pd.Series(0.0, index=index)
    den = pd.Series(0.0, index=index)
    available = {}
    for name, dist in distances.items():
        w = float(weights.get(name, 0.0))
        if w < 0 or not np.isfinite(w):
            raise ValueError(f"weight for {name!r} must be finite and >= 0")
        ok = dist.notna() & (w > 0)
        available[name] = ok * w
        num = num + dist.fillna(0.0) * available[name]
        den = den + available[name]
    total = (num / den.where(den > 0)).astype(float)
    applied = pd.DataFrame({n: (a / den.where(den > 0)).fillna(0.0) for n, a in available.items()})
    return total, applied
