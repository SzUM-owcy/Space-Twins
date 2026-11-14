"""Moon: Diviner Christiansen Feature (CF) wavelength for a 10 x 10 km patch.

The global CF map (Zenodo record 4558235, viewing-geometry corrected, 32 pixels/degree, +-70 deg latitude)
is an un-georeferenced GeoTIFF: row 0 is +70 deg, column 0 is -180 deg, longitude east positive.
Higher CF wavelength means a relatively more mafic surface, lower means more felsic / anorthositic.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.windows import Window

from config import (
    COMPOSITION_MOON_REFERENCE_PATH,
    COMPOSITION_CF_MAX_ABS_LAT,
    COMPOSITION_CF_PATH,
    COMPOSITION_CF_PPD,
    COMPOSITION_CF_URL,
    MOON_RADIUS_M,
    PATCH_SIZE_M,
)
from src.composition import (
    STATUS_OK,
    STATUS_OUTSIDE_CF,
    extract_moon_composition,
    load_composition_reference,
    mafic_felsic_percentile,
)

log = logging.getLogger(__name__)
KM_PER_DEG = np.pi * MOON_RADIUS_M / 180.0 / 1000.0


def ensure_cf_map(path: Path = COMPOSITION_CF_PATH) -> Path:
    """Download the CF GeoTIFF (206 MB, no login) when it is not on disk."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(COMPOSITION_CF_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                fh.write(chunk)
    tmp.rename(path)
    return path


def cf_patch_window(src: rasterio.DatasetReader, lat: float, lon: float) -> np.ndarray:
    """CF pixels whose centres fall inside the 10 x 10 km footprint around (lat, lon); longitude wraps."""
    half_lat = PATCH_SIZE_M / 2000.0 / KM_PER_DEG
    half_lon = half_lat / np.cos(np.radians(lat))
    ppd = COMPOSITION_CF_PPD
    row0 = int(np.floor((COMPOSITION_CF_MAX_ABS_LAT - (lat + half_lat)) * ppd))
    row1 = int(np.ceil((COMPOSITION_CF_MAX_ABS_LAT - (lat - half_lat)) * ppd))
    row0, row1 = max(row0, 0), min(row1, src.height)
    col0 = int(np.floor((lon - half_lon + 180.0) * ppd))
    col1 = int(np.ceil((lon + half_lon + 180.0) * ppd))
    cols = np.arange(col0, col1) % src.width  # wrap across the antimeridian
    rows = np.arange(row0, row1)
    lat_c = COMPOSITION_CF_MAX_ABS_LAT - (rows + 0.5) / ppd
    lon_c = (np.arange(col0, col1) + 0.5) / ppd - 180.0
    r_ok = np.abs(lat_c - lat) <= half_lat
    c_ok = np.abs(lon_c - lon) <= half_lon
    if not r_ok.any() or not c_ok.any():
        return np.empty((0,), dtype=np.float32)
    block = src.read(1, window=Window(0, row0, src.width, row1 - row0))  # full rows: wrap-safe, still only ~1 MB
    return block[np.ix_(r_ok, cols[c_ok])]


def moon_composition(lat: float, lon: float, src: rasterio.DatasetReader | None = None) -> dict:
    """Raw CF stats of the patch at (lat, lon); ``outside_diviner_cf_coverage`` beyond +-70 deg latitude."""
    if abs(lat) > COMPOSITION_CF_MAX_ABS_LAT:
        return {
            "diviner_cf_microns": float("nan"),
            "composition_valid_pixel_ratio": float("nan"),
            "composition_status": STATUS_OUTSIDE_CF,
        }
    lon = (lon + 180.0) % 360.0 - 180.0
    if src is not None:
        return extract_moon_composition(cf_patch_window(src, lat, lon), src.nodata)
    with rasterio.open(ensure_cf_map()) as ds:
        return extract_moon_composition(cf_patch_window(ds, lat, lon), ds.nodata)


def moon_composition_live(lat: float, lon: float) -> dict:
    """CF stats plus body-relative ``mafic_felsic_percentile`` for any point (None when outside coverage or no reference)."""
    stats = moon_composition(lat, lon)
    pct = None
    if stats["composition_status"] == STATUS_OK and COMPOSITION_MOON_REFERENCE_PATH.exists():
        pct = float(mafic_felsic_percentile(stats["diviner_cf_microns"], load_composition_reference(COMPOSITION_MOON_REFERENCE_PATH)))
    return {**stats, "mafic_felsic_percentile": pct}
