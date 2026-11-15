"""Logika API: ładowanie danych i wywołania ``src/``. Bez FastAPI - łatwo testować i podmieniać.

Backendowiec może tu dowolnie zmieniać implementację, dopóki odpowiedzi zgadzają się z ``api.schemas``.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from config import (
    DATA_DIR,
    ILLUM_EARTH_PATH,
    COMPOSITION_EARTH_LITHOLOGY_PATH,
    PRACTICALITY_PATH,
    COMPOSITION_EARTH_MINERALS_PATH,
    COMPOSITION_EARTH_PATH,
    COMPOSITION_MOON_PATH,
    ILLUM_MOON_PATH,
    THERMAL_EARTH_PATH,
    THERMAL_MOON_PATH,
    THERMAL_MOON_REFERENCE_PATH,
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
from src.practicality import practicality_blocks
from src.query import OUT_OF_RANGE_Z, find_analogs, moon_patch_for, rank_stability
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
    from src.moon_composition import moon_minerals_for

    thermal = _table(THERMAL_MOON_PATH)
    illum = _table(ILLUM_MOON_PATH)
    thermal_k = thermal.set_index("patch_id")["surface_temperature_range_k"] if thermal is not None else None
    illum_fraction = illum.set_index("patch_id")["solar_visibility_fraction"] if illum is not None else None

    def _lookup(series, patch_id: str) -> float | None:
        if series is None or patch_id not in series.index or pd.isna(series[patch_id]):
            return None
        return float(series[patch_id])

    sites = []
    for _, row in moon_index().iterrows():
        minerals = moon_minerals_for(row.patch_id, float(row.center_lat), float(row.center_lon))
        sites.append(
            MoonSite(
                site_id=row.patch_id,
                name=_pretty(row.region),
                lat=float(row.center_lat),
                lon=float(row.center_lon),
                features=_features(row),
                thermal_range_k=_lookup(thermal_k, row.patch_id),
                solar_visibility_fraction=_lookup(illum_fraction, row.patch_id),
                minerals=None if minerals is None else {k.replace("_fraction", ""): float(v) for k, v in minerals.items()},
            )
        )
    return sites


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


def _table(path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def _site_value(path, patch_id: str, column: str) -> float | None:
    table = _table(path)
    if table is None or patch_id not in set(table["patch_id"]):
        return None
    value = table.set_index("patch_id").loc[patch_id, column]
    return None if pd.isna(value) else float(value)


def _moon_thermal(site_id: str | None, lat: float, lon: float) -> float | None:
    """Percentyl zakresu temperatur Księżyca (tabela albo na żywo z Diviner); None = brak danych."""
    if site_id is not None:
        return _site_value(THERMAL_MOON_PATH, site_id, "thermal_range_percentile")
    if not THERMAL_MOON_REFERENCE_PATH.exists():
        return None
    try:
        from src.moon_temperature import moon_cell_stats
        from src.thermal import empirical_cdf, load_reference

        rng = moon_cell_stats(lat, lon)["surface_temperature_range_k"]
        return float(empirical_cdf(rng, load_reference(THERMAL_MOON_REFERENCE_PATH)))
    except Exception:  # offline / brak danych: tylko teren
        return None


def _moon_composition(site_id: str | None, lat: float, lon: float) -> tuple[float | None, str]:
    """(mafic_felsic_percentile, status) Księżyca: tabela albo na żywo z mapy Diviner CF."""
    if site_id is not None:
        table = _table(COMPOSITION_MOON_PATH)
        if table is None or site_id not in set(table["patch_id"]):
            return None, "missing"
        row = table.set_index("patch_id").loc[site_id]
        return (None if pd.isna(row["mafic_felsic_percentile"]) else float(row["mafic_felsic_percentile"])), str(row["composition_status"])
    try:
        from src.moon_composition import moon_composition_live

        res = moon_composition_live(lat, lon)
        return res["mafic_felsic_percentile"], res["composition_status"]
    except Exception:
        return None, "missing"


def _moon_illumination(site_id: str | None, lat: float, lon: float) -> float | None:
    if site_id is not None:
        return _site_value(ILLUM_MOON_PATH, site_id, "solar_visibility_fraction")
    try:
        from src.illumination_live import moon_illumination_for

        value = moon_illumination_for(lat, lon)["fraction"]
        return None if value != value else float(value)
    except Exception:
        return None


def _opt(row, name: str):
    value = getattr(row, name, None)
    return None if value is None or value != value else value


def analogs(req: AnalogsRequest) -> AnalogsResponse:
    patch, site_id, name, lat, lon = _moon_patch(req.moon)
    features = extract_patch_features(patch, PIXEL_SIZE_M)
    earth = earth_index()
    moon_thermal = _moon_thermal(site_id, lat, lon) if req.w_thermal > 0 else None
    moon_illum = _moon_illumination(site_id, lat, lon) if req.w_illum > 0 else None
    from src.moon_composition import moon_minerals_for

    moon_minerals = moon_minerals_for(site_id, lat, lon)
    moon_comp, moon_comp_status = _moon_composition(site_id, lat, lon) if req.w_composition > 0 else (None, None)
    find_kwargs = dict(
        w_slope=req.w_slope, max_per_region=req.max_per_region,
        moon_thermal_percentile=moon_thermal, earth_thermal=_table(THERMAL_EARTH_PATH), w_thermal=req.w_thermal,
        moon_illumination=moon_illum, earth_illumination=_table(ILLUM_EARTH_PATH), w_illum=req.w_illum,
        moon_composition=moon_comp, earth_composition=_table(COMPOSITION_EARTH_PATH), w_composition=req.w_composition,
        earth_lithology=_table(COMPOSITION_EARTH_LITHOLOGY_PATH),
        earth_minerals=_table(COMPOSITION_EARTH_MINERALS_PATH), moon_minerals=moon_minerals,
        feature_weights=req.feature_weights,
    )
    result = find_analogs(features, earth, top_k=req.top_k, **find_kwargs)
    stability = rank_stability(features, earth, result, req.stability_runs, **find_kwargs) if req.stability_runs else None
    by_id = earth.set_index("patch_id")
    earth_thermal = _table(THERMAL_EARTH_PATH)
    earth_illum = _table(ILLUM_EARTH_PATH)
    thermal_k = earth_thermal.set_index("patch_id")["surface_temperature_range_k"] if earth_thermal is not None else None
    illum_fraction = earth_illum.set_index("patch_id")["solar_visibility_fraction"] if earth_illum is not None else None

    def _lookup(series, patch_id: str) -> float | None:
        if series is None or patch_id not in series.index or pd.isna(series[patch_id]):
            return None
        return float(series[patch_id])

    blocks = {}
    if req.include_practicality:
        table = _table(PRACTICALITY_PATH)
        if table is not None:
            blocks = practicality_blocks(table, result["patch_id"], result["total_distance"])
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
                terrain_distance=_opt(row, "terrain_distance"),
                thermal_distance=_opt(row, "thermal_distance"),
                thermal_status=_opt(row, "thermal_status"),
                illumination_distance=_opt(row, "illumination_distance"),
                illumination_status=_opt(row, "illumination_status"),
                composition_distance=_opt(row, "composition_distance"),
                composition_status=_opt(row, "composition_status"),
                composition_quality=_opt(row, "composition_quality"),
                composition_confidence=_opt(row, "composition_confidence"),
                composition_source=_opt(row, "composition_source"),
                earth_mafic_felsic_percentile=_opt(row, "earth_mafic_felsic_percentile"),
                earth_plagioclase_fraction=_opt(row, "earth_plagioclase_fraction"),
                earth_pyroxene_fraction=_opt(row, "earth_pyroxene_fraction"),
                earth_olivine_fraction=_opt(row, "earth_olivine_fraction"),
                earth_other_fraction=_opt(row, "earth_other_fraction"),
                earth_mineral_status=_opt(row, "earth_mineral_status"),
                mineral_distance=_opt(row, "mineral_distance"),
                dominant_lithology=_opt(row, "dominant_lithology"),
                mixed_lithology_flag=_opt(row, "mixed_lithology_flag"),
                terrain_quality=_opt(row, "terrain_quality"),
                thermal_quality=_opt(row, "thermal_quality"),
                illumination_quality=_opt(row, "illumination_quality"),
                stability=None if stability is None else float(stability[row.patch_id]),
                thermal_range_k=_lookup(thermal_k, row.patch_id),
                solar_visibility_fraction=_lookup(illum_fraction, row.patch_id),
                practicality=blocks.get(row.patch_id, {}).get("practicality"),
                constraints=blocks.get(row.patch_id, {}).get("constraints"),
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
            thermal_range_percentile=moon_thermal,
            thermal_range_k=_site_value(THERMAL_MOON_PATH, site_id, "surface_temperature_range_k") if site_id is not None else None,
            solar_visibility_fraction=moon_illum,
            mafic_felsic_percentile=moon_comp,
            composition_status=moon_comp_status,
            minerals=None if moon_minerals is None else {k.replace("_fraction", ""): float(v) for k, v in moon_minerals.items()},
        ),
        w_slope=req.w_slope,
        w_thermal=req.w_thermal,
        w_illum=req.w_illum,
        w_composition=req.w_composition,
        feature_weights=req.feature_weights,
        top_k=req.top_k,
        max_per_region=req.max_per_region,
        out_of_range=list(result.attrs["out_of_range"]),
        results=items,
    )
