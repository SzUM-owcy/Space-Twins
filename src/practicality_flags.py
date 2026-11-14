"""Phase 4 constraint flags (Group B): protected areas, World Heritage, land rights, habitat, water, hazard, security.

Flags never feed the numeric scores; ``excluded`` only follows the configured policy. Unknown stays
``manual_review``/``missing``, never ``ok``.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import requests
from matplotlib.path import Path as MplPath

from config import (
    PRACTICALITY_ARID_BARE_FRACTION,
    PRACTICALITY_GVP_URL,
    PRACTICALITY_SECURITY_BY_REGION,
    PRACTICALITY_STRICT_IUCN,
    PRACTICALITY_STRICT_OVERLAP,
    PRACTICALITY_TREE_WARN,
    PRACTICALITY_VOLCANO_EXCLUDE_KM,
    PRACTICALITY_VOLCANO_EXCLUDE_SINCE,
    PRACTICALITY_VOLCANO_WARN_KM,
    PRACTICALITY_VOLCANO_WARN_SINCE,
    PRACTICALITY_WATER_STRESS_POP_25KM,
    PRACTICALITY_WDPA_URL,
    PRACTICALITY_WETLAND_WARN,
)
from src.practicality_data import haversine_km, nearest_distance_km

log = logging.getLogger("practicality")
IUCN_STRICTNESS = ["Ia", "Ib", "II", "III", "IV", "V", "VI"]
COMMUNAL_WORDS = ("communal", "indigenous", "community")


def protected_overlap(lat: float, lon: float, half_deg: float = 0.045) -> dict:
    """Query WDPA polygons intersecting the patch; returns overlap fraction, strictest IUCN, World Heritage and communal flags."""
    dlon = half_deg / max(np.cos(np.radians(lat)), 0.05)
    params = {
        "geometry": f"{lon - dlon},{lat - half_deg},{lon + dlon},{lat + half_deg}", "geometryType": "esriGeometryEnvelope",
        "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "true",
        "maxAllowableOffset": 0.002, "outFields": "iucn_cat,desig_eng,own_type,status", "f": "json",
    }
    for attempt in range(3):
        try:
            r = requests.get(PRACTICALITY_WDPA_URL, params=params, timeout=90)
            data = r.json()
            if "features" in data:
                break
        except (requests.RequestException, ValueError):
            pass
    else:
        return {"protected_overlap_fraction": np.nan, "protected_category": "", "world_heritage_overlap": np.nan, "protected_communal_land": np.nan}
    inside = np.zeros(400, dtype=bool)
    cats, heritage, communal = [], False, False
    n = 20
    xs, ys = np.meshgrid(np.linspace(lon - dlon, lon + dlon, n), np.linspace(lat - half_deg, lat + half_deg, n))
    pts = np.column_stack([xs.ravel(), ys.ravel()])
    for f in data["features"]:
        a = f["attributes"]
        if str(a.get("status", "")).lower() not in ("designated", "inscribed", "established", ""):
            continue
        rings = f.get("geometry", {}).get("rings", [])
        if not rings:
            continue
        parity = np.zeros(len(pts), dtype=int)
        for ring in rings:
            parity += MplPath(np.asarray(ring)).contains_points(pts).astype(int)
        mask = parity % 2 == 1
        if not mask.any():
            continue
        inside |= mask
        cat = str(a.get("iucn_cat") or "")
        if cat in IUCN_STRICTNESS:
            cats.append(cat)
        heritage |= "world heritage" in str(a.get("desig_eng") or "").lower()
        communal |= any(w in str(a.get("own_type") or "").lower() for w in COMMUNAL_WORDS)
    strictest = min(cats, key=IUCN_STRICTNESS.index) if cats else ""
    return {
        "protected_overlap_fraction": float(inside.mean()),
        "protected_category": strictest,
        "world_heritage_overlap": float(heritage),
        "protected_communal_land": float(communal),
    }


def load_volcanoes() -> pd.DataFrame:
    """Smithsonian GVP Holocene volcanoes: lat, lon, last eruption year (NaN if unknown)."""
    feats = requests.get(PRACTICALITY_GVP_URL, timeout=120).json()["features"]
    rows = [
        {"lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0], "last_eruption": f["properties"].get("Last_Eruption_Year")}
        for f in feats
    ]
    return pd.DataFrame(rows)


def nearest_volcano(centres: np.ndarray, volcanoes: pd.DataFrame) -> pd.DataFrame:
    """Distance to the nearest Holocene volcano and the most recent eruption among volcanoes within the warning radius."""
    pts = volcanoes[["lat", "lon"]].to_numpy()
    dist = nearest_distance_km(centres, pts)
    recent = np.full(len(centres), np.nan)
    lat, lon, year = volcanoes.lat.to_numpy(), volcanoes.lon.to_numpy(), volcanoes.last_eruption.to_numpy(dtype=float)
    for i, (la, lo) in enumerate(centres):
        within = haversine_km(la, lo, lat, lon) <= PRACTICALITY_VOLCANO_WARN_KM
        if within.any() and np.isfinite(year[within]).any():
            recent[i] = np.nanmax(year[within])
    return pd.DataFrame({"nearest_volcano_km": dist, "nearest_volcano_last_eruption": recent})


def _status(series_fn, df: pd.DataFrame) -> pd.Series:
    return pd.Series([series_fn(r) for r in df.itertuples()], index=df.index)


def derive_flags(df: pd.DataFrame, region: pd.Series) -> pd.DataFrame:
    """Fill the flag columns from the raw Phase 4 columns and earlier land cover / population."""
    df = df.copy()

    def protected(r):
        f = r.protected_overlap_fraction
        if not np.isfinite(f):
            return "missing"
        if f <= 0:
            return "ok"
        if isinstance(r.protected_category, str) and r.protected_category in PRACTICALITY_STRICT_IUCN and f >= PRACTICALITY_STRICT_OVERLAP:
            return "excluded"
        return "manual_review"

    def heritage(r):
        if not np.isfinite(r.world_heritage_overlap):
            return "missing"
        return "manual_review" if r.world_heritage_overlap > 0 else "ok"

    def community(r):
        if np.isfinite(r.protected_communal_land) and r.protected_communal_land > 0:
            return "warning"
        return "manual_review"  # no public land-rights dataset checked: unknown is never "clear"

    def biodiversity(r):
        if not (np.isfinite(r.tree_fraction) and np.isfinite(r.wetland_fraction)):
            return "missing"
        return "warning" if r.tree_fraction >= PRACTICALITY_TREE_WARN or r.wetland_fraction >= PRACTICALITY_WETLAND_WARN else "ok"

    def water(r):
        if not (np.isfinite(r.bare_ground_fraction) and np.isfinite(r.population_25km)):
            return "missing"
        arid = r.bare_ground_fraction >= PRACTICALITY_ARID_BARE_FRACTION
        return "warning" if arid and r.population_25km >= PRACTICALITY_WATER_STRESS_POP_25KM else "ok"

    def hazard(r):
        d, y = r.nearest_volcano_km, r.nearest_volcano_last_eruption
        if not np.isfinite(d):
            return "missing"
        if np.isfinite(y) and d <= PRACTICALITY_VOLCANO_EXCLUDE_KM and y >= PRACTICALITY_VOLCANO_EXCLUDE_SINCE:
            return "excluded"
        if np.isfinite(y) and d <= PRACTICALITY_VOLCANO_WARN_KM and y >= PRACTICALITY_VOLCANO_WARN_SINCE:
            return "warning"
        return "ok"

    df["protected_area_status"] = _status(protected, df)
    df["world_heritage_status"] = _status(heritage, df)
    df["community_rights_status"] = _status(community, df)
    df["biodiversity_status"] = _status(biodiversity, df)
    df["water_stress_status"] = _status(water, df)
    df["hazard_status"] = _status(hazard, df)
    df["security_status"] = region.map(lambda x: PRACTICALITY_SECURITY_BY_REGION.get(x, "ok")).values
    return df
