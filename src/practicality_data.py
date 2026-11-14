"""Open-data layers for the practicality table (no login): WorldPop, Malaria Atlas travel times, OurAirports, Natural Earth roads."""

from __future__ import annotations

import io
import logging
import struct
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.windows import from_bounds
from scipy.spatial import cKDTree

from config import (
    PRACTICALITY_AIRPORT_DETOUR,
    PRACTICALITY_AIRPORT_SPEED_KMH,
    PRACTICALITY_DIR,
    PRACTICALITY_URLS,
)

log = logging.getLogger("practicality")
EARTH_R_KM = 6371.0088
WCS_BASE = "https://data.malariaatlas.org/geoserver/ows"


def _download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s", url)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.rename(dest)
    return dest


def _xyz(lat, lon) -> np.ndarray:
    lat, lon = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.column_stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


def _chord_to_km(chord: np.ndarray) -> np.ndarray:
    return 2 * EARTH_R_KM * np.arcsin(np.clip(chord / 2, 0, 1))


def haversine_km(lat0: float, lon0: float, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    p0, p = np.radians(lat0), np.radians(lat)
    a = np.sin((p - p0) / 2) ** 2 + np.cos(p0) * np.cos(p) * np.sin(np.radians(lon - lon0) / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def population_within(src: rasterio.DatasetReader, lat: float, lon: float, radii_km=(10, 25, 50)) -> dict[int, float]:
    """Sum WorldPop people per pixel inside each radius; pixels farther than the radius centre are excluded."""
    rmax = max(radii_km)
    dlat = rmax / 111.0 + 0.02
    dlon = rmax / (111.0 * max(np.cos(np.radians(lat)), 0.05)) + 0.02
    win = from_bounds(lon - dlon, lat - dlat, lon + dlon, lat + dlat, src.transform)
    a = src.read(1, window=win, boundless=True, fill_value=0).astype(float)
    a[~np.isfinite(a) | (a < 0)] = 0.0
    rows, cols = np.meshgrid(np.arange(a.shape[0]), np.arange(a.shape[1]), indexing="ij")
    xs, ys = rasterio.transform.xy(src.window_transform(win), rows.ravel(), cols.ravel(), offset="center")
    d = haversine_km(lat, lon, np.asarray(ys), np.asarray(xs)).reshape(a.shape)
    return {r: float(a[d <= r].sum()) for r in radii_km}


def wcs_raster(coverage: str, west: float, south: float, east: float, north: float, name: str) -> Path:
    """Download (and cache) a Malaria Atlas WCS subset as GeoTIFF."""
    dest = PRACTICALITY_DIR / "wcs" / f"{name}.tif"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    params = {
        "service": "WCS", "version": "2.0.1", "request": "GetCoverage", "coverageId": coverage,
        "format": "image/tiff", "subset": [f"Lat({south:.4f},{north:.4f})", f"Long({west:.4f},{east:.4f})"],
    }
    r = requests.get(WCS_BASE, params=params, timeout=180)
    r.raise_for_status()
    if r.content[:2] not in (b"II", b"MM"):
        raise RuntimeError(f"WCS {coverage} returned non-TIFF: {r.content[:200]!r}")
    dest.write_bytes(r.content)
    return dest


def raster_median(path: Path, lat: float, lon: float, half_deg: float = 0.05) -> float:
    """Median of valid pixels in a small box (about a 10 km patch) around a point."""
    with rasterio.open(path) as src:
        win = from_bounds(lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg, src.transform)
        a = src.read(1, window=win, boundless=True, fill_value=src.nodata if src.nodata is not None else -9999).astype(float)
        nodata = src.nodata
    valid = np.isfinite(a) & (a >= 0)
    if nodata is not None:
        valid &= a != nodata
    return float(np.median(a[valid])) if valid.any() else np.nan


def load_airports() -> np.ndarray:
    """Lat/lon of scheduled-service medium and large airports (OurAirports)."""
    path = _download(PRACTICALITY_URLS["airports"], PRACTICALITY_DIR / "airports.csv")
    df = pd.read_csv(path, usecols=["type", "latitude_deg", "longitude_deg", "scheduled_service"])
    df = df[df["type"].isin(["large_airport", "medium_airport"]) & (df["scheduled_service"] == "yes")]
    return df[["latitude_deg", "longitude_deg"]].to_numpy()


def nearest_distance_km(points_latlon: np.ndarray, targets_latlon: np.ndarray) -> np.ndarray:
    tree = cKDTree(_xyz(targets_latlon[:, 0], targets_latlon[:, 1]))
    chord, _ = tree.query(_xyz(points_latlon[:, 0], points_latlon[:, 1]))
    return _chord_to_km(chord)


def airport_travel_minutes(distance_km: np.ndarray) -> np.ndarray:
    """Straight-line distance with a detour factor and an average road speed; an estimate, not routing."""
    return distance_km * PRACTICALITY_AIRPORT_DETOUR / PRACTICALITY_AIRPORT_SPEED_KMH * 60.0


def _read_polylines(shp_bytes: bytes) -> list[np.ndarray]:
    """Minimal ESRI shapefile reader for PolyLine (type 3) geometries; returns (lat, lon) vertex arrays."""
    lines, pos, end = [], 100, len(shp_bytes)
    while pos + 8 <= end:
        (length_words,) = struct.unpack(">i", shp_bytes[pos + 4 : pos + 8])
        body = shp_bytes[pos + 8 : pos + 8 + length_words * 2]
        pos += 8 + length_words * 2
        if len(body) < 44 or struct.unpack("<i", body[:4])[0] != 3:
            continue
        n_parts, n_points = struct.unpack("<ii", body[36:44])
        pts = np.frombuffer(body, dtype="<f8", count=n_points * 2, offset=44 + 4 * n_parts).reshape(-1, 2)
        lines.append(np.column_stack([pts[:, 1], pts[:, 0]]))
    return lines


def load_road_points(spacing_km: float = 2.0) -> np.ndarray:
    """Natural Earth major roads densified to roughly ``spacing_km`` vertices; returns (lat, lon)."""
    path = _download(PRACTICALITY_URLS["roads"], PRACTICALITY_DIR / "ne_10m_roads.zip")
    with zipfile.ZipFile(path) as z:
        shp = next(n for n in z.namelist() if n.endswith(".shp"))
        lines = _read_polylines(z.read(shp))
    out = []
    for ln in lines:
        for a, b in zip(ln[:-1], ln[1:]):
            n = max(1, int(haversine_km(a[0], a[1], np.array([b[0]]), np.array([b[1]]))[0] // spacing_km))
            t = np.linspace(0, 1, n + 1, endpoint=False)[:, None]
            out.append(a + t * (b - a))
        out.append(ln[-1:])
    return np.vstack(out)


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{ns}{lat:02d}{ew}{lon:03d}_Map.tif"


def overpass_power_points(west: float, south: float, east: float, north: float, spacing_km: float = 2.0, retries: int = 3) -> np.ndarray:
    """OSM high-voltage power lines (power=line) in a bbox as densified (lat, lon) vertices; empty array if none."""
    query = f'[out:json][timeout:120];way["power"="line"]({south},{west},{north},{east});out geom;'
    for attempt in range(retries):
        r = requests.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": "moon-analog-lite/0.1"}, timeout=180)
        if r.status_code == 200:
            break
        import time

        time.sleep(15 * (attempt + 1))
    else:
        r.raise_for_status()
    out = []
    for el in r.json().get("elements", []):
        ln = np.array([[p["lat"], p["lon"]] for p in el.get("geometry", [])])
        for a, b in zip(ln[:-1], ln[1:]):
            n = max(1, int(haversine_km(a[0], a[1], np.array([b[0]]), np.array([b[1]]))[0] // spacing_km))
            out.append(a + np.linspace(0, 1, n, endpoint=False)[:, None] * (b - a))
        if len(ln):
            out.append(ln[-1:])
    return np.vstack(out) if out else np.empty((0, 2))


def worldcover_fractions(lat: float, lon: float, half_deg: float = 0.045, size: int = 100) -> dict[str, float]:
    """Bare/sparse, tree and wetland fractions of the 10 m ESA WorldCover map around a patch centre (decimated read)."""
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    tile_lat, tile_lon = int(np.floor(lat / 3) * 3), int(np.floor(lon / 3) * 3)
    url = WORLDCOVER_URL.format(ns=ns, lat=abs(tile_lat), ew=ew, lon=abs(tile_lon))
    nan = {"bare_ground_fraction": np.nan, "tree_fraction": np.nan, "wetland_fraction": np.nan}
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
            with rasterio.open(url) as src:
                win = from_bounds(lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg, src.transform)
                a = src.read(1, window=win, out_shape=(size, size), boundless=True, fill_value=0)
    except rasterio.errors.RasterioIOError:
        return nan
    valid = a > 0
    if not valid.any():
        return nan
    n = valid.sum()
    return {
        "bare_ground_fraction": float((a == 60).sum() / n),
        "tree_fraction": float((a == 10).sum() / n),
        "wetland_fraction": float(np.isin(a, (90, 95)).sum() / n),
    }
