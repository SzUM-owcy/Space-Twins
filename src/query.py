"""Ranking analogów Księżyc -> Ziemia (CONTRACT §5)."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
import rasterio

from config import LOLA_NODATA, LOLA_SCALE, PIXEL_SIZE_M
from src.morphometry import FEATURE_NAMES, extract_patch_features
from src.raster_io import extract_patch
from src.scoring import distances, fit_scaler, transform

# Produkt globalny LOLA 118 m pokrywa |lat| <= 75°; pas 75-80° pomijamy (CONTRACT §2).
# Produkt polarny (lat <= -80°) jeszcze nie jest podłączony.
GLOBAL_MAX_ABS_LAT = 75.0
# Sanity check wysokości LOLA po zastosowaniu skali (CONTRACT §2 pkt 8).
LOLA_MIN_M, LOLA_MAX_M = -9150.0, 10800.0

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


class PatchRejected(ValueError):
    """Łatki nie da się wyciąć: szerokość poza produktem, nodata albo poza rastrem."""


def extract_moon_patch(src: rasterio.DatasetReader, lat: float, lon: float) -> np.ndarray:
    """Łatka 85x85 (metry, float64, północ u góry) z otwartego globalnego rastra LOLA.

    ``PatchRejected`` dla szerokości poza zakresem produktu albo odrzuconej łatki;
    zwykły ``ValueError``, gdy wysokości wychodzą poza zakres LOLA (zła skala rastra).
    """
    if not (-90.0 <= lat <= 90.0) or not np.isfinite(lat) or not np.isfinite(lon):
        raise PatchRejected(f"niepoprawne współrzędne: lat={lat}, lon={lon}")
    if abs(lat) > GLOBAL_MAX_ABS_LAT:
        raise PatchRejected(
            f"lat={lat}: produkt globalny 118 m pokrywa tylko |lat| <= {GLOBAL_MAX_ABS_LAT:g}° "
            "(pas 75-80° nie jest obsługiwany, a produkt polarny nie jest jeszcze podłączony)"
        )
    lon = (lon + 180.0) % 360.0 - 180.0

    patch = extract_patch(src, lat, lon, body="moon", nodata=LOLA_NODATA, scale=LOLA_SCALE)
    if patch is None:
        raise PatchRejected(f"({lat}, {lon}): łatka odrzucona (nodata albo poza rastrem)")
    lo, hi = float(patch.min()), float(patch.max())
    if lo < LOLA_MIN_M or hi > LOLA_MAX_M:
        raise ValueError(
            f"({lat}, {lon}): wysokości {lo:.0f}..{hi:.0f} m poza zakresem LOLA "
            f"({LOLA_MIN_M:.0f}..{LOLA_MAX_M:.0f}) – sprawdź skalę"
        )
    return patch


def moon_features_for(lat: float, lon: float, lola_path: str | Path) -> dict[str, float]:
    """12 cech łatki 10x10 km wyciętej na żywo z globalnego rastra LOLA (np. dla UI).

    Rzuca ``PatchRejected`` (podklasa ``ValueError``) dla pasa 75-80°, biegunów
    i łatek odrzuconych.
    """
    with rasterio.open(lola_path) as src:
        patch = extract_moon_patch(src, lat, lon)
    return extract_patch_features(patch, PIXEL_SIZE_M)


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
