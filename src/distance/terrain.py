"""Terrain: fixed-scale normalised physical differences, aggregated with a weighted RMS."""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from config import FEATURE_NAMES

METHOD = "fixed_scale_weighted_rms"


def terrain_distance(
    moon_features: Mapping[str, float],
    earth_df: pd.DataFrame,
    scales: Mapping[str, float],
    feature_weights: Mapping[str, float] | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """Return (distance per Earth patch, normalised per-feature differences).

    normalized_i = |earth_i - moon_i| / scale_i;  distance = sqrt(sum(w_i * n_i^2) / sum(w_i)).
    A non-finite feature drops out of that patch's sum and the remaining weights renormalise.
    Features without a weight use 1.0; weights must be >= 0 and not all zero.
    """
    unknown = sorted(set(feature_weights or {}) - set(FEATURE_NAMES))
    if unknown:
        raise ValueError(f"unknown features in feature_weights: {unknown}")
    w = np.array([float((feature_weights or {}).get(n, 1.0)) for n in FEATURE_NAMES])
    if not np.all(np.isfinite(w)) or np.any(w < 0) or w.sum() <= 0:
        raise ValueError("feature weights must be finite, >= 0 and not all zero")
    moon = np.array([float(moon_features[n]) for n in FEATURE_NAMES])
    scale = np.array([scales[n] for n in FEATURE_NAMES])
    earth = earth_df[FEATURE_NAMES].to_numpy(dtype=float)
    norm = np.abs(earth - moon) / scale
    ok = np.isfinite(norm) & np.isfinite(moon)
    w_ok = ok * w
    den = w_ok.sum(axis=1)
    num = (np.where(ok, norm, 0.0) ** 2 * w_ok).sum(axis=1)
    dist = np.where(den > 0, np.sqrt(num / np.where(den > 0, den, 1.0)), np.nan)
    return (
        pd.Series(dist, index=earth_df.index),
        pd.DataFrame(norm, index=earth_df.index, columns=FEATURE_NAMES),
    )
