"""Earth: per-patch surface temperature range from MODIS 8-day LST (Terra + Aqua, day + night).

For every pixel the P95-P05 of all valid observations of the reference period is computed
(seasonal + diurnal spread at the overpass times); a patch gets the median of its pixels.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.errors import WindowError
from rasterio.windows import Window, from_bounds

from config import (
    PATCH_SIZE_M,
    THERMAL_EARTH_COLLECTION,
    THERMAL_MIN_OBS,
    THERMAL_MIN_VALID_FRACTION,
    THERMAL_REFERENCE_END,
    THERMAL_REFERENCE_START,
)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
LST_SCALE = 0.02
SPHERE_R = 6371007.181  # MODIS sinusoidal sphere
KM_PER_DEG = np.pi * SPHERE_R / 180.0 / 1000.0
HALF_PATCH_KM = PATCH_SIZE_M / 2000.0
_TO_SINU = Transformer.from_crs("EPSG:4326", f"+proj=sinu +R={SPHERE_R} +units=m +no_defs", always_xy=True)


def _region_bbox(centres: np.ndarray, margin_km: float = HALF_PATCH_KM + 2.0) -> tuple:
    """(west, south, east, north) around patch centres [lat, lon], with a margin in km."""
    lat, lon = centres[:, 0], centres[:, 1]
    dlat = margin_km / KM_PER_DEG
    dlon = margin_km / (KM_PER_DEG * np.cos(np.radians(np.abs(lat).max())))
    return lon.min() - dlon, lat.min() - dlat, lon.max() + dlon, lat.max() + dlat


def _window(ds, bbox) -> Window:
    """Pixel window of ``ds`` (sinusoidal) covering a lon/lat bbox, clipped to the tile."""
    w, s, e, n = bbox
    xs, ys = [], []
    for lon in np.linspace(w, e, 9):
        for lat in (s, n):
            x, y = _TO_SINU.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    for lat in np.linspace(s, n, 9):
        for lon in (w, e):
            x, y = _TO_SINU.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    win = from_bounds(min(xs), min(ys), max(xs), max(ys), ds.transform)
    win = win.round_offsets(op="floor").round_lengths(op="ceil")
    try:
        return win.intersection(Window(0, 0, ds.width, ds.height))
    except WindowError:  # the tile only touches the bbox corner in lon/lat, not in the grid
        return Window(0, 0, 0, 0)


def _read(href: str, win: Window) -> np.ndarray:
    with rasterio.open(href) as ds:
        return ds.read(1, window=win)


def _search(bbox) -> list:
    client = pystac_client.Client.open(STAC_URL)
    search = client.search(
        collections=[THERMAL_EARTH_COLLECTION],
        bbox=list(bbox),
        datetime=f"{THERMAL_REFERENCE_START}/{THERMAL_REFERENCE_END}",
    )
    return [pc.sign(item) for item in search.items()]  # serial: parallel signing hits HTTP 429


def _load_item(item, bbox):
    """Read day/night LST (K, NaN where invalid) of one composite for the bbox window."""
    with rasterio.open(item.assets["LST_Day_1km"].href) as ds:
        win = _window(ds, bbox)
        transform = ds.window_transform(win)
    if win.width <= 0 or win.height <= 0:
        return None
    out = []
    for lst_key, qc_key in (("LST_Day_1km", "QC_Day"), ("LST_Night_1km", "QC_Night")):
        lst = _read(item.assets[lst_key].href, win).astype(np.float64)
        qc = _read(item.assets[qc_key].href, win)
        ok = (lst > 0) & ((qc & 3) < 2)  # QA bits 0-1: 0 good, 1 other quality; 2-3 not produced
        out.append(np.where(ok, lst * LST_SCALE, np.nan))
    tile = item.id.split(".")[2]
    return tile, transform, win, out


def _pixel_latlon(transform, shape) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = np.indices(shape)
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    lat = y / SPHERE_R
    lon = x / (SPHERE_R * np.cos(lat))
    return np.degrees(lat), np.degrees(lon)


def region_thermal(patches: list[tuple[str, float, float]], workers: int = 16) -> list[dict]:
    """Thermal stats for the patches of one region: [(patch_id, lat, lon), ...]."""
    centres = np.array([[p[1], p[2]] for p in patches])
    bbox = _region_bbox(centres)
    items = _search(bbox)
    if not items:
        raise RuntimeError("no MODIS items found for the region")

    with ThreadPoolExecutor(workers) as pool:
        loaded = [r for r in pool.map(lambda it: _load_item(it, bbox), items) if r is not None]

    tiles: dict[str, dict] = {}
    for tile, transform, win, obs in loaded:
        entry = tiles.setdefault(tile, {"transform": transform, "shape": obs[0].shape, "obs": []})
        if obs[0].shape == entry["shape"]:
            entry["obs"].extend(obs)

    for entry in tiles.values():
        stack = np.stack(entry["obs"])  # (n_obs, h, w)
        n_valid = np.isfinite(stack).sum(axis=0)
        with np.errstate(all="ignore"):
            p05, p95 = np.nanpercentile(stack, [5, 95], axis=0)
        rng = p95 - p05
        rng[n_valid < THERMAL_MIN_OBS] = np.nan
        entry["range"], entry["n_valid"] = rng, n_valid
        entry["lat"], entry["lon"] = _pixel_latlon(entry["transform"], entry["shape"])

    results = []
    for patch_id, lat0, lon0 in patches:
        half_lat = HALF_PATCH_KM / KM_PER_DEG
        half_lon = half_lat / np.cos(np.radians(lat0))
        ranges, counts, total = [], [], 0
        for entry in tiles.values():
            m = (np.abs(entry["lat"] - lat0) <= half_lat) & (
                np.abs(((entry["lon"] - lon0 + 180) % 360) - 180) <= half_lon
            )
            total += int(m.sum())
            good = m & np.isfinite(entry["range"])
            ranges.append(entry["range"][good])
            counts.append(entry["n_valid"][good])
        ranges, counts = np.concatenate(ranges), np.concatenate(counts)
        frac = ranges.size / total if total else 0.0
        ok = frac >= THERMAL_MIN_VALID_FRACTION
        results.append(
            {
                "patch_id": patch_id,
                "surface_temperature_range_k": float(np.median(ranges)) if ok else float("nan"),
                "thermal_valid_fraction": frac,
                "thermal_valid_observations": int(np.median(counts)) if ranges.size else 0,
            }
        )
    return results
