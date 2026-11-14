"""Ranking analogów Księżyc -> Ziemia (CONTRACT §5)."""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from src.morphometry import FEATURE_NAMES
from src.scoring import distances, fit_scaler, transform

RESULT_COLUMNS = [
    "rank",
    "patch_id",
    "region",
    "center_lat",
    "center_lon",
    "slope_distance",
    "shape_distance",
    "total_distance",
]
OUT_OF_RANGE_Z = 3.0


def find_analogs(
    moon_features: Mapping[str, float],
    earth_index: pd.DataFrame,
    top_k: int = 5,
    w_slope: float = 0.5,
    max_per_region: int | None = 1,
) -> pd.DataFrame:
    """Najbardziej podobne łatki Ziemi do łatki Księżyca (mniejsza odległość = większe podobieństwo).

    ``max_per_region=1``: z każdego regionu tylko najlepsza łatka, potem top-K regionów.
    ``max_per_region=None``: bez limitu. Cechy Księżyca spoza zakresu Ziemi (|z| > 3)
    trafiają do ``result.attrs["out_of_range"]``.
    """
    if top_k < 1:
        raise ValueError(f"top_k musi być >= 1, jest {top_k}")
    if max_per_region is not None and max_per_region < 1:
        raise ValueError(f"max_per_region musi być >= 1 albo None, jest {max_per_region}")
    for col in ("patch_id", "region", "center_lat", "center_lon"):
        if col not in earth_index.columns:
            raise ValueError(f"earth_index nie ma kolumny {col!r}")

    scaler = fit_scaler(earth_index)
    dist = distances(moon_features, earth_index, scaler, w_slope)
    ranked = pd.concat(
        [earth_index[["patch_id", "region", "center_lat", "center_lon"]], dist], axis=1
    ).sort_values("total_distance", kind="stable")

    if max_per_region is not None:
        ranked = ranked.groupby("region", sort=False).head(max_per_region)
    result = ranked.head(top_k).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    result = result[RESULT_COLUMNS]

    z_moon = transform(moon_features, scaler)[0]
    result.attrs["out_of_range"] = [
        name for name, z in zip(FEATURE_NAMES, z_moon) if abs(z) > OUT_OF_RANGE_Z
    ]
    return result
