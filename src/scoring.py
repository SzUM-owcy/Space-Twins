"""Podobieństwo Księżyc <-> Ziemia (CONTRACT §5).

Skaler jest dopasowany do indeksu Ziemi (log1p dla cech z ciężkim ogonem, potem
z-score ze statystykami Ziemi). Wektor Księżyca transformujemy tym samym skalerem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from config import FEATURE_NAMES, SHAPE_FEATURES, SLOPE_FEATURES

LOG1P_FEATURES = ("rms_height", "tri_mean", "relief_range")


@dataclass(frozen=True)
class Scaler:
    """Średnia i odchylenie cech Ziemi (po log1p), w kolejności FEATURE_NAMES."""

    mean: np.ndarray
    std: np.ndarray


def _log_transformed(values: np.ndarray) -> np.ndarray:
    """log1p na wybranych cechach; ``values`` ma kształt (n, 12) w kolejności FEATURE_NAMES."""
    out = np.array(values, dtype=np.float64, copy=True)
    for name in LOG1P_FEATURES:
        out[:, FEATURE_NAMES.index(name)] = np.log1p(out[:, FEATURE_NAMES.index(name)])
    return out


def _as_matrix(features: Mapping[str, float] | pd.DataFrame) -> np.ndarray:
    """Dict (jeden wiersz) albo DataFrame -> macierz (n, 12) w kolejności FEATURE_NAMES."""
    if isinstance(features, pd.DataFrame):
        missing = [c for c in FEATURE_NAMES if c not in features.columns]
        if missing:
            raise ValueError(f"brak kolumn cech: {missing}")
        matrix = features[FEATURE_NAMES].to_numpy(dtype=np.float64)
    else:
        missing = [c for c in FEATURE_NAMES if c not in features]
        if missing:
            raise ValueError(f"brak cech: {missing}")
        matrix = np.array([[features[c] for c in FEATURE_NAMES]], dtype=np.float64)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("cechy zawierają NaN lub inf")
    return matrix


def fit_scaler(earth_df: pd.DataFrame) -> Scaler:
    """Dopasuj skaler do indeksu Ziemi: log1p dla 3 cech, potem średnia i std (ddof=0).

    Jeśli std == 0 dla cechy, używamy 1.0 (CONTRACT §5).
    """
    if len(earth_df) == 0:
        raise ValueError("indeks Ziemi jest pusty")
    logged = _log_transformed(_as_matrix(earth_df))
    std = logged.std(axis=0)
    std[std == 0] = 1.0
    return Scaler(mean=logged.mean(axis=0), std=std)


def transform(features: Mapping[str, float] | pd.DataFrame, scaler: Scaler) -> np.ndarray:
    """Cechy -> z-score ze statystykami Ziemi. Zwraca macierz (n, 12)."""
    return (_log_transformed(_as_matrix(features)) - scaler.mean) / scaler.std


def _rms(diff: np.ndarray, columns: list[str]) -> np.ndarray:
    idx = [FEATURE_NAMES.index(c) for c in columns]
    return np.sqrt(np.mean(diff[:, idx] ** 2, axis=1))


def distances(
    moon_features: Mapping[str, float],
    earth_df: pd.DataFrame,
    scaler: Scaler,
    w_slope: float = 0.5,
) -> pd.DataFrame:
    """Odległości jednej łatki Księżyca od każdej łatki Ziemi (indeks jak w ``earth_df``).

    slope_distance = sqrt(mean_slope((z_moon - z_earth)^2)),
    shape_distance = sqrt(mean_shape((z_moon - z_earth)^2)),
    total_distance = w_slope * slope_distance + (1 - w_slope) * shape_distance.
    """
    if not 0.0 <= w_slope <= 1.0:
        raise ValueError(f"w_slope musi być w [0, 1], jest {w_slope}")
    z_moon = transform(moon_features, scaler)  # (1, 12)
    z_earth = transform(earth_df, scaler)  # (n, 12)
    diff = z_earth - z_moon

    slope_distance = _rms(diff, SLOPE_FEATURES)
    shape_distance = _rms(diff, SHAPE_FEATURES)
    return pd.DataFrame(
        {
            "slope_distance": slope_distance,
            "shape_distance": shape_distance,
            "total_distance": w_slope * slope_distance + (1.0 - w_slope) * shape_distance,
        },
        index=earth_df.index,
    )
