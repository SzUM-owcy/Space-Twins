"""Logika API: ładowanie danych i wywołania ``src/``. Bez FastAPI - łatwo testować i podmieniać.

Backendowiec może tu dowolnie zmieniać implementację, dopóki odpowiedzi zgadzają się z ``api.schemas``.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from config import (
    DATA_DIR,
    FEATURE_NAMES,
    GRID_N,
    LOLA_GLOBAL_PATH,
    PATCH_SIZE_M,
    PIXEL_SIZE_M,
    SHAPE_FEATURES,
    SLOPE_FEATURES,
)
from src.morphometry import extract_patch_features
from src.plotting import load_earth_patch
from src.query import OUT_OF_RANGE_Z, find_analogs, moon_patch_for
from src.scoring import fit_scaler, transform

from .schemas import (
    Analog,
    AnalogsRequest,
    AnalogsResponse,
    EarthRegion,
    FeatureInfo,
    Health,
    Meta,
    MoonQuery,
    MoonSite,
    MoonSummary,
    PatchGrid,
)

EARTH_INDEX = DATA_DIR / "earth_index.csv"
MOON_INDEX = DATA_DIR / "moon_index.csv"
REGIONS_CSV = DATA_DIR / "regions.csv"
MOON_PATCH_DIR = DATA_DIR / "patches" / "moon"

DEFAULT_W_SLOPE = 0.5
DEFAULT_TOP_K = 5

_FEATURE_DOCS: dict[str, tuple[str, str]] = {
    "rms_height": ("m", "RMS of heights after removing the best-fit plane (roughness)."),
    "tri_mean": ("m", "Mean Terrain Ruggedness Index (Riley 1999)."),
    "relief_range": ("m", "Max minus min elevation in the patch."),
    "hypsometric_integral": ("", "(mean - min) / (max - min) elevation; 0..1."),
    "elev_skew": ("", "Skewness of the elevation distribution."),
}

LIMITATIONS = [
    "This is similarity of elevation-derived terrain features - not landing-site suitability, mission safety or geological equivalence.",
    "LOLA 118 m is largely interpolated between altimeter tracks, so Moon slopes/TRI are slightly smoothed versus Earth averaged from real 30 m data; results may favour flat analogs.",
    "The scaler and the |z| > 3 threshold depend on the hand-picked Earth regions; patches within one region are strongly correlated. The index is not a representative sample of Earth.",
    "NASADEM is a surface model (includes tree canopy), so the index deliberately relies on desert and volcanic terrain.",
    "Patches are 10 x 10 km (85 x 85 px). By default at most one patch per region is shown.",
]


class NotFound(LookupError):
    """Nie ma takiego site_id / patch_id."""


class RasterUnavailable(RuntimeError):
    """Brak rastra LOLA na tej maszynie (własne współrzędne niedostępne)."""


def _pretty(slug: str) -> str:
    return slug.replace("_", " ").title()


@lru_cache(maxsize=1)
def earth_index() -> pd.DataFrame:
    return pd.read_csv(EARTH_INDEX)


@lru_cache(maxsize=1)
def moon_index() -> pd.DataFrame:
    return pd.read_csv(MOON_INDEX)


@lru_cache(maxsize=1)
def _scaler():
    return fit_scaler(earth_index())


def _features(row: pd.Series) -> dict[str, float]:
    return {name: float(row[name]) for name in FEATURE_NAMES}


def _z_scores(features: dict[str, float]) -> dict[str, float]:
    return {name: float(z) for name, z in zip(FEATURE_NAMES, transform(features, _scaler())[0])}


def health() -> Health:
    return Health(
        status="ok",
        custom_coordinates_available=LOLA_GLOBAL_PATH.exists(),
        moon_sites=len(moon_index()),
        earth_patches=len(earth_index()),
    )


def meta() -> Meta:
    features = [
        FeatureInfo(
            name=name,
            group="slope" if name in SLOPE_FEATURES else "shape",
            unit=_FEATURE_DOCS[name][0] if name in SHAPE_FEATURES else "°",
            description=(
                _FEATURE_DOCS[name][1]
                if name in SHAPE_FEATURES
                else f"{int(name[-2:])}th percentile of slope."
            ),
        )
        for name in FEATURE_NAMES
    ]
    return Meta(
        patch_size_m=PATCH_SIZE_M,
        grid_n=GRID_N,
        pixel_size_m=PIXEL_SIZE_M,
        default_w_slope=DEFAULT_W_SLOPE,
        default_top_k=DEFAULT_TOP_K,
        out_of_range_z=OUT_OF_RANGE_Z,
        features=features,
        limitations=LIMITATIONS,
    )


def moon_sites() -> list[MoonSite]:
    return [
        MoonSite(
            site_id=row.patch_id,
            name=_pretty(row.region),
            lat=float(row.center_lat),
            lon=float(row.center_lon),
            features=_features(row),
        )
        for _, row in moon_index().iterrows()
    ]


def earth_regions() -> list[EarthRegion]:
    counts = earth_index().groupby("region").size()
    regions = pd.read_csv(REGIONS_CSV)
    return [
        EarthRegion(
            region=row.region,
            name=_pretty(row.region),
            dem=row.dem,
            validation=bool(row.validation),
            bbox=(float(row.west), float(row.south), float(row.east), float(row.north)),
            patches=int(counts.get(row.region, 0)),
        )
        for row in regions.itertuples()
    ]


def _grid(patch: np.ndarray, *, patch_id: str | None, body: str, region: str | None, lat: float, lon: float) -> PatchGrid:
    heights = np.round(np.asarray(patch, dtype=np.float64), 2)
    return PatchGrid(
        patch_id=patch_id,
        body=body,
        region=region,
        lat=lat,
        lon=lon,
        size_m=PATCH_SIZE_M,
        grid_n=GRID_N,
        pixel_size_m=PIXEL_SIZE_M,
        min_m=float(heights.min()),
        max_m=float(heights.max()),
        heights_m=heights.tolist(),
    )


def _moon_site_row(site_id: str) -> pd.Series:
    rows = moon_index()[moon_index()["patch_id"] == site_id]
    if rows.empty:
        raise NotFound(f"unknown moon site_id {site_id!r}")
    return rows.iloc[0]


def _moon_patch(query: MoonQuery) -> tuple[np.ndarray, str | None, str, float, float]:
    """(patch, site_id, name, lat, lon) dla miejsca z listy albo własnych współrzędnych."""
    if query.site_id is not None:
        row = _moon_site_row(query.site_id)
        patch = np.load(MOON_PATCH_DIR / f"{row.patch_id}.npy").astype(np.float64)
        return patch, row.patch_id, _pretty(row.region), float(row.center_lat), float(row.center_lon)
    if not LOLA_GLOBAL_PATH.exists():
        raise RasterUnavailable("LOLA raster is not available on this machine - pick a site from /moon/sites")
    lat, lon = float(query.lat), float(query.lon)
    return moon_patch_for(lat, lon), None, f"Custom point ({lat:.3f}, {lon:.3f})", lat, lon


def moon_patch(query: MoonQuery) -> PatchGrid:
    patch, site_id, _, lat, lon = _moon_patch(query)
    region = site_id.removeprefix("moon_") if site_id else None
    return _grid(patch, patch_id=site_id, body="moon", region=region, lat=lat, lon=lon)


def earth_patch(patch_id: str) -> PatchGrid:
    rows = earth_index()[earth_index()["patch_id"] == patch_id]
    patch = load_earth_patch(patch_id) if not rows.empty else None
    if patch is None:
        raise NotFound(f"unknown earth patch_id {patch_id!r}")
    row = rows.iloc[0]
    return _grid(
        patch, patch_id=patch_id, body="earth", region=row.region, lat=float(row.center_lat), lon=float(row.center_lon)
    )


def analogs(req: AnalogsRequest) -> AnalogsResponse:
    patch, site_id, name, lat, lon = _moon_patch(req.moon)
    features = extract_patch_features(patch, PIXEL_SIZE_M)
    earth = earth_index()
    result = find_analogs(
        features, earth, top_k=req.top_k, w_slope=req.w_slope, max_per_region=req.max_per_region
    )
    by_id = earth.set_index("patch_id")
    items = []
    for row in result.itertuples():
        earth_row = by_id.loc[row.patch_id]
        earth_features = _features(earth_row)
        items.append(
            Analog(
                rank=int(row.rank),
                patch_id=row.patch_id,
                region=row.region,
                region_name=_pretty(row.region),
                source=earth_row["source"],
                lat=float(row.center_lat),
                lon=float(row.center_lon),
                slope_distance=float(row.slope_distance),
                shape_distance=float(row.shape_distance),
                total_distance=float(row.total_distance),
                features=earth_features,
                z_scores=_z_scores(earth_features),
            )
        )
    return AnalogsResponse(
        moon=MoonSummary(
            site_id=site_id,
            name=name,
            lat=lat,
            lon=lon,
            features={k: float(v) for k, v in features.items()},
            z_scores=_z_scores(features),
        ),
        w_slope=req.w_slope,
        top_k=req.top_k,
        max_per_region=req.max_per_region,
        out_of_range=list(result.attrs["out_of_range"]),
        results=items,
    )
