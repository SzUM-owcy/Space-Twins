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
from src.scoring import LOG1P_FEATURES, distances, fit_scaler, transform

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
COMPOSITION_RESULT_COLUMNS = ["composition_distance", "composition_status", "composition_confidence", "earth_mafic_felsic_percentile"]
QUALITY_COLUMNS = ["terrain_quality", "thermal_quality", "illumination_quality", "composition_quality"]
# Etykieta składnika wg odległości (skala z-score): < 0.5 dobre, < 1.0 umiarkowane, dalej słabe.
QUALITY_GOOD_MAX, QUALITY_MODERATE_MAX = 0.5, 1.0
STABILITY_SIGMA = 0.3  # odch. std szumu dodawanego do z-score cech Księżyca


def quality_label(distance: float | None) -> str | None:
    """"good" / "moderate" / "poor" dla odległości składnika; None, gdy brak danych."""
    if distance is None or not np.isfinite(distance):
        return None
    if distance < QUALITY_GOOD_MAX:
        return "good"
    return "moderate" if distance < QUALITY_MODERATE_MAX else "poor"
# E|d|^2 of two independent uniform percentiles is 1/6, so sqrt(6) puts |dp| on a z-score-like scale.
THERMAL_DISTANCE_SCALE = float(np.sqrt(6.0))
ILLUM_VALUE_COLUMN = "solar_visibility_fraction"
COMPOSITION_VALUE_COLUMN = "mafic_felsic_percentile"


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
    moon_composition: float | None = None,
    earth_composition: pd.DataFrame | None = None,
    w_composition: float = 0.0,
) -> pd.DataFrame:
    """Dodaj składniki termiczny i oświetleniowy; połącz z terenowym i sortuj po nowej sumie.

    Brakujący składnik wypada z sumy (jego waga wraca do pozostałych), nigdy nie jest zerem.
    """
    ranked = ranked.rename(columns={"total_distance": "terrain_distance"})
    terrain_weight = 1.0 - w_thermal - w_illum - w_composition
    num = terrain_weight * ranked["terrain_distance"]
    den = pd.Series(terrain_weight, index=ranked.index)

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
    if w_composition > 0.0:
        lookup, scale = None, 1.0
        if earth_composition is not None:
            valid = earth_composition[earth_composition["composition_status"] == "ok"]
            lookup = earth_composition.set_index("patch_id")[COMPOSITION_VALUE_COLUMN].where(
                earth_composition.set_index("patch_id")["composition_status"] == "ok"
            )
            std = float(valid[COMPOSITION_VALUE_COLUMN].std())
            scale = 1.0 / std if np.isfinite(std) and std > 0 else 1.0
        dist = _component_distance(ranked, moon_composition, lookup, scale).clip(upper=OUT_OF_RANGE_Z)
        add("composition", w_composition, dist)
        if earth_composition is not None:
            by_id = earth_composition.set_index("patch_id")
            ranked["earth_mafic_felsic_percentile"] = ranked["patch_id"].map(lookup)
            ranked["composition_confidence"] = ranked["patch_id"].map(by_id["composition_confidence"]).where(dist.notna())
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
    feature_weights: Mapping[str, float] | None = None,
    moon_composition: float | None = None,
    earth_composition: pd.DataFrame | None = None,
    w_composition: float = 0.0,
    earth_lithology: pd.DataFrame | None = None,
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
    to ``1 - w_thermal - w_illum``. ``feature_weights``: względne ważności 12 cech terenu
    (patrz ``scoring.distances``); zastępuje podział ``w_slope``. Skład (``w_composition`` > 0):
    ``earth_composition`` ma kolumny ``patch_id``, ``mafic_felsic_percentile``, ``composition_status``,
    ``composition_confidence``; odległość = |różnica percentyli| / std Ziemi (obcięta do 3); brak danych
    (np. bieguny Księżyca) = składnik wypada z sumy. ``earth_lithology`` (opcjonalnie: ``patch_id``,
    ``dominant_lithology``, ``mixed_lithology_flag``) dodaje kolumny objaśniające; nie wpływa na wynik.
    """
    if not 0.0 <= w_thermal <= 1.0:
        raise ValueError(f"w_thermal musi być w [0, 1], jest {w_thermal}")
    if not 0.0 <= w_illum <= 1.0:
        raise ValueError(f"w_illum musi być w [0, 1], jest {w_illum}")
    if not 0.0 <= w_composition <= 1.0:
        raise ValueError(f"w_composition musi być w [0, 1], jest {w_composition}")
    if w_thermal + w_illum + w_composition > 1.0 + 1e-9:
        raise ValueError(f"w_thermal + w_illum + w_composition musi być <= 1, jest {w_thermal + w_illum + w_composition}")
    if top_k < 1:
        raise ValueError(f"top_k musi być >= 1, jest {top_k}")
    if max_per_region is not None and max_per_region < 1:
        raise ValueError(f"max_per_region musi być >= 1 albo None, jest {max_per_region}")
    for col in ("patch_id", "region", "center_lat", "center_lon"):
        if col not in earth_index.columns:
            raise ValueError(f"earth_index nie ma kolumny {col!r}")

    scaler = fit_scaler(earth_index)
    dist = distances(moon_features, earth_index, scaler, w_slope, feature_weights)
    ranked = pd.concat(
        [earth_index[["patch_id", "region", "center_lat", "center_lon"]], dist], axis=1
    ).sort_values("total_distance", kind="stable")

    if w_thermal > 0.0 or w_illum > 0.0 or w_composition > 0.0:
        ranked = _add_components(
            ranked, moon_thermal_percentile, earth_thermal, w_thermal,
            moon_illumination, earth_illumination, w_illum,
            moon_composition, earth_composition, w_composition,
        )

    if max_per_region is not None:
        ranked = ranked.groupby("region", sort=False).head(max_per_region)
    result = ranked.head(top_k).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    for name in ("terrain", "thermal", "illumination", "composition"):
        if f"{name}_distance" in result.columns:
            result[f"{name}_quality"] = result[f"{name}_distance"].map(quality_label)
    extra = THERMAL_RESULT_COLUMNS + ILLUM_RESULT_COLUMNS + COMPOSITION_RESULT_COLUMNS + QUALITY_COLUMNS
    result = result[RESULT_COLUMNS + [c for c in extra if c in result.columns]]
    if earth_lithology is not None:
        by_id = earth_lithology.set_index("patch_id")
        result["dominant_lithology"] = result["patch_id"].map(by_id["dominant_lithology"])
        result["mixed_lithology_flag"] = result["patch_id"].map(by_id["mixed_lithology_flag"]).map(
            lambda v: None if pd.isna(v) else bool(v)
        )

    z_moon = transform(moon_features, scaler)[0]
    result.attrs["out_of_range"] = [
        name for name, z in zip(FEATURE_NAMES, z_moon) if abs(z) > OUT_OF_RANGE_Z
    ]
    return result


def rank_stability(
    moon_features: Mapping[str, float],
    earth_index: pd.DataFrame,
    result: pd.DataFrame,
    runs: int = 20,
    sigma: float = STABILITY_SIGMA,
    seed: int = 0,
    **find_kwargs,
) -> pd.Series:
    """Ułamek przebiegów z szumem na z-score cech Księżyca, w których region łatki zostaje w top-K
    (inna łatka tego samego regionu też się liczy, bo ranking bierze jedną łatkę na region).

    ``find_kwargs`` te same co dla ``find_analogs`` (wagi, termika, oświetlenie); wynik
    indeksowany ``patch_id``. Blisko 1 = stabilna pozycja, blisko 0 = prawie remis.
    """
    if runs < 1:
        raise ValueError(f"runs musi być >= 1, jest {runs}")
    scaler = fit_scaler(earth_index)
    z_moon = transform(moon_features, scaler)[0]
    rng = np.random.default_rng(seed)
    hits = pd.Series(0, index=result["patch_id"], dtype=float)
    top_k = len(result)
    for _ in range(runs):
        logged = (z_moon + rng.normal(0.0, sigma, z_moon.shape)) * scaler.std + scaler.mean
        raw = np.array(logged)
        for name in LOG1P_FEATURES:
            i = FEATURE_NAMES.index(name)
            raw[i] = np.expm1(raw[i])
        noisy = dict(zip(FEATURE_NAMES, raw))
        top = find_analogs(noisy, earth_index, top_k=top_k, **find_kwargs)
        hits[result["region"].isin(top["region"]).to_numpy()] += 1
    return hits / runs
