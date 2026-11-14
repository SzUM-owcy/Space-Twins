"""Ranking analogów Księżyc -> Ziemia (CONTRACT §5)."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
import rasterio

from config import (
    FEATURE_NAMES,
    LOLA_GLOBAL_PATH,
    LOLA_NODATA,
    LOLA_POLAR_PATH,
    LOLA_SCALE,
    PIXEL_SIZE_M,
)
from src.morphometry import extract_patch_features
from src.raster_io import extract_patch
from src.scoring import distances, fit_scaler, transform

# Produkt globalny LOLA 118 m: |lat| <= 75°; polarny: lat <= -80°. Pas 75-80° pomijamy (CONTRACT §2).
GLOBAL_MAX_ABS_LAT = 75.0
POLAR_MAX_LAT = -80.0
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
    """Łatki nie da się wyciąć: szerokość poza produktami, nodata albo poza rastrem."""


def extract_moon_patch(src: rasterio.DatasetReader, lat: float, lon: float) -> np.ndarray:
    """Łatka 85x85 (metry, float64, północ u góry) z otwartego rastra LOLA (globalnego lub polarnego).

    ``PatchRejected`` dla odrzuconej łatki (nodata albo poza rastrem); zwykły
    ``ValueError``, gdy wysokości wychodzą poza zakres LOLA (zła skala rastra).
    """
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


def moon_patch_for(
    lat: float,
    lon: float,
    lola_path: str | Path = LOLA_GLOBAL_PATH,
    polar_path: str | Path | None = LOLA_POLAR_PATH,
) -> np.ndarray:
    """Łatka 10x10 km dla (lat, lon); produkt wybierany wg szerokości.

    |lat| <= 75° -> ``lola_path`` (globalny 118 m), lat <= -80° -> ``polar_path`` (20 m, południe).
    ``PatchRejected`` dla pasa 75-80°, północy powyżej 75° i łatek odrzuconych.
    """
    if not np.isfinite(lat) or not np.isfinite(lon) or not -90.0 <= lat <= 90.0:
        raise PatchRejected(f"niepoprawne współrzędne: lat={lat}, lon={lon}")
    lon = (lon + 180.0) % 360.0 - 180.0

    if abs(lat) <= GLOBAL_MAX_ABS_LAT:
        path = lola_path
    elif lat <= POLAR_MAX_LAT:
        if polar_path is None:
            raise PatchRejected(f"lat={lat}: brak produktu polarnego (podaj polar_path)")
        path = polar_path
    else:
        raise PatchRejected(
            f"lat={lat}: obsługujemy |lat| <= {GLOBAL_MAX_ABS_LAT:g}° (produkt globalny) "
            f"i lat <= {POLAR_MAX_LAT:g}° (produkt polarny); pas 75-80° i biegun północny pomijamy"
        )
    with rasterio.open(path) as src:
        return extract_moon_patch(src, lat, lon)


def moon_features_for(
    lat: float,
    lon: float,
    lola_path: str | Path = LOLA_GLOBAL_PATH,
    polar_path: str | Path | None = LOLA_POLAR_PATH,
) -> dict[str, float]:
    """12 cech łatki 10x10 km wyciętej na żywo z rastra LOLA (np. dla UI).

    Rzuca ``PatchRejected`` (podklasa ``ValueError``) dla pasa 75-80°, bieguna północnego
    i łatek odrzuconych.
    """
    return extract_patch_features(moon_patch_for(lat, lon, lola_path, polar_path), PIXEL_SIZE_M)


THERMAL_RESULT_COLUMNS = ["terrain_distance", "thermal_distance", "thermal_status"]
ILLUM_RESULT_COLUMNS = ["illumination_distance", "illumination_status"]
# E|d|^2 of two independent uniform percentiles is 1/6, so sqrt(6) puts |dp| on a z-score-like scale.
THERMAL_DISTANCE_SCALE = float(np.sqrt(6.0))
ILLUM_VALUE_COLUMN = "solar_visibility_fraction"


def _component_distance(
    ranked: pd.DataFrame, moon_value: float | None, earth_values: pd.Series | None, scale: float
) -> pd.Series:
    """|moon - earth| * scale per ranked patch; NaN when either side is missing."""
    out = pd.Series(np.nan, index=ranked.index)
    if earth_values is not None and moon_value is not None and np.isfinite(moon_value):
        out = (ranked["patch_id"].map(earth_values).astype(float) - moon_value).abs() * scale
    return out


def _add_components(
    ranked: pd.DataFrame,
    moon_percentile: float | None,
    earth_thermal: pd.DataFrame | None,
    w_thermal: float,
    moon_illumination: float | None = None,
    earth_illumination: pd.DataFrame | None = None,
    w_illum: float = 0.0,
) -> pd.DataFrame:
    """Dodaj składniki termiczny i oświetleniowy; połącz z terenowym i sortuj po nowej sumie.

    Brakujący składnik wypada z sumy (jego waga wraca do pozostałych), nigdy nie jest zerem.
    """
    ranked = ranked.rename(columns={"total_distance": "terrain_distance"})
    num = (1.0 - w_thermal - w_illum) * ranked["terrain_distance"]
    den = pd.Series(1.0 - w_thermal - w_illum, index=ranked.index)

    def add(name: str, weight: float, dist: pd.Series) -> None:
        nonlocal num, den
        ranked[f"{name}_distance"] = dist
        ok = dist.notna()
        ranked[f"{name}_status"] = np.where(ok, "ok", "missing")
        num = num + weight * dist.fillna(0.0)
        den = den + weight * ok

    if w_thermal > 0.0:
        lookup = earth_thermal.set_index("patch_id")["thermal_range_percentile"] if earth_thermal is not None else None
        add("thermal", w_thermal, _component_distance(ranked, moon_percentile, lookup, THERMAL_DISTANCE_SCALE))
    if w_illum > 0.0:
        lookup, scale = None, 1.0
        if earth_illumination is not None:
            lookup = earth_illumination.set_index("patch_id")[ILLUM_VALUE_COLUMN]
            std = float(lookup.std())
            scale = 1.0 / std if np.isfinite(std) and std > 0 else 1.0
        dist = _component_distance(ranked, moon_illumination, lookup, scale)
        add("illumination", w_illum, dist.clip(upper=OUT_OF_RANGE_Z))
    ranked["total_distance"] = np.where(den > 1e-12, num / den.where(den > 1e-12, 1.0), ranked["terrain_distance"])
    return ranked.sort_values("total_distance", kind="stable")


def find_analogs(
    moon_features: Mapping[str, float],
    earth_index: pd.DataFrame,
    top_k: int = 5,
    w_slope: float = 0.5,
    max_per_region: int | None = 1,
    moon_thermal_percentile: float | None = None,
    earth_thermal: pd.DataFrame | None = None,
    w_thermal: float = 0.0,
    moon_illumination: float | None = None,
    earth_illumination: pd.DataFrame | None = None,
    w_illum: float = 0.0,
) -> pd.DataFrame:
    """Najbardziej podobne łatki Ziemi do łatki Księżyca (mniejsza odległość = większe podobieństwo).

    ``max_per_region=1``: z każdego regionu tylko najlepsza łatka, potem top-K regionów.
    ``max_per_region=None``: bez limitu. Cechy Księżyca spoza zakresu Ziemi (|z| > 3)
    trafiają do ``result.attrs["out_of_range"]``.

    Opcjonalnie składnik termiczny (``w_thermal`` > 0): ``earth_thermal`` ma kolumny
    ``patch_id`` i ``thermal_range_percentile``. Gdy brakuje danych termicznych (Księżyca albo
    łatki Ziemi), ``total_distance`` = odległość terenowa, a ``thermal_status`` = "missing".
    Analogicznie oświetlenie (``w_illum`` > 0): ``earth_illumination`` ma kolumny ``patch_id`` i
    ``solar_visibility_fraction``; odległość = |różnica| / std Ziemi (obcięta do 3). Waga terenu
    to ``1 - w_thermal - w_illum``.
    """
    if not 0.0 <= w_thermal <= 1.0:
        raise ValueError(f"w_thermal musi być w [0, 1], jest {w_thermal}")
    if not 0.0 <= w_illum <= 1.0:
        raise ValueError(f"w_illum musi być w [0, 1], jest {w_illum}")
    if w_thermal + w_illum > 1.0 + 1e-9:
        raise ValueError(f"w_thermal + w_illum musi być <= 1, jest {w_thermal + w_illum}")
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

    if w_thermal > 0.0 or w_illum > 0.0:
        ranked = _add_components(
            ranked, moon_thermal_percentile, earth_thermal, w_thermal,
            moon_illumination, earth_illumination, w_illum,
        )

    if max_per_region is not None:
        ranked = ranked.groupby("region", sort=False).head(max_per_region)
    result = ranked.head(top_k).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    extra = THERMAL_RESULT_COLUMNS + ILLUM_RESULT_COLUMNS
    result = result[RESULT_COLUMNS + [c for c in extra if c in result.columns]]

    z_moon = transform(moon_features, scaler)[0]
    result.attrs["out_of_range"] = [
        name for name, z in zip(FEATURE_NAMES, z_moon) if abs(z) > OUT_OF_RANGE_Z
    ]
    return result
