"""Earth: ASTER Global Emissivity Dataset (AG100.003, 100 m) patch extraction.

AG100 is distributed as 1 x 1 degree HDF5 tiles (about 42 MB each) that need a free NASA Earthdata login
(``~/.netrc`` entry for urs.earthdata.nasa.gov). Tiles already placed in ``data/aster_ged/`` are used as is;
missing ones are found through the public CMR granule search and downloaded with the netrc credentials.
Only the tiles that intersect the indexed regions are needed, never the global archive.
"""

from __future__ import annotations

import logging
from pathlib import Path

import h5py
import numpy as np
import requests

from config import ASTER_GED_DIR, PATCH_SIZE_M
from src.composition import extract_earth_composition

log = logging.getLogger(__name__)
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
EARTH_KM_PER_DEG = 111.32
BAND_NAMES = [f"emissivity_band{n}" for n in (10, 11, 12, 13, 14)]


class AsterAccessError(RuntimeError):
    """ASTER GED tiles are not on disk and could not be downloaded (usually: no Earthdata login)."""


def find_tiles(bbox: tuple[float, float, float, float]) -> list[tuple[str, str]]:
    """(granule name, HTTPS URL) of AG100 tiles intersecting a (west, south, east, north) bbox, via CMR."""
    w, s, e, n = bbox
    params = {
        "short_name": "AG100", "version": "003", "page_size": 200,
        "bounding_box": f"{w:.4f},{s:.4f},{e:.4f},{n:.4f}",
    }
    resp = requests.get(CMR_URL, params=params, timeout=60)
    resp.raise_for_status()
    tiles = []
    for entry in resp.json()["feed"]["entry"]:
        urls = [link["href"] for link in entry["links"] if link["href"].startswith("https") and link["href"].endswith(".h5")]
        if urls:
            tiles.append((entry["title"], urls[0]))
    return tiles


def ensure_tile(name: str, url: str, directory: Path = ASTER_GED_DIR) -> Path:
    """Local path of a tile; downloads it with the ``~/.netrc`` Earthdata login when missing."""
    path = directory / f"{name}.h5"
    if path.exists():
        return path
    directory.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.Session() as session:  # requests follows the URS redirect and applies the netrc login
        resp = session.get(url, stream=True, timeout=300)
        if resp.status_code in (401, 403) or "urs.earthdata.nasa.gov" in resp.url:
            raise AsterAccessError(
                "ASTER GED download needs a free NASA Earthdata login: add it to ~/.netrc "
                "(machine urs.earthdata.nasa.gov login USER password PASS), or place the .h5 tiles in "
                f"{directory}"
            )
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                fh.write(chunk)
    tmp.rename(path)
    return path


def _find_dataset(h5: h5py.File, *needles: str, exclude: tuple[str, ...] = ("sdev", "std")) -> h5py.Dataset:
    """First dataset whose path contains all ``needles`` (case-insensitive); AG100 group names vary by version."""
    found: list[h5py.Dataset] = []

    def visit(name: str, obj) -> None:
        low = name.lower()
        if isinstance(obj, h5py.Dataset) and all(n in low for n in needles) and not any(x in low for x in exclude):
            found.append(obj)

    h5.visititems(visit)
    if not found:
        raise KeyError(f"no dataset with {needles} in {h5.filename}")
    return found[0]


def read_tile(path: Path) -> dict[str, np.ndarray]:
    """Raw arrays of one tile: emissivity_band10..14, ndvi, land_water_map, num_obs, lat, lon (2-D)."""
    with h5py.File(path, "r") as h5:
        emis = _find_dataset(h5, "emissivity", "mean")[...]  # (5, rows, cols), scale 0.001
        tile = {name: emis[i].astype(np.float64) for i, name in enumerate(BAND_NAMES)}
        tile["ndvi"] = _find_dataset(h5, "ndvi", "mean")[...].astype(np.float64)
        tile["land_water_map"] = _find_dataset(h5, "land")[...]
        tile["num_obs"] = _find_dataset(h5, "numobs")[...].astype(np.float64)
        tile["lat"] = _find_dataset(h5, "latitude")[...].astype(np.float64)
        tile["lon"] = _find_dataset(h5, "longitude")[...].astype(np.float64)
    return tile


def region_composition(
    patches: list[tuple[str, float, float]], bbox: tuple[float, float, float, float] | None = None
) -> list[dict]:
    """Earth composition diagnostics for the patches of one region: [(patch_id, lat, lon), ...]."""
    centres = np.array([[p[1], p[2]] for p in patches])
    half_lat = PATCH_SIZE_M / 2000.0 / EARTH_KM_PER_DEG
    if bbox is None:
        pad = 2 * half_lat
        bbox = (centres[:, 1].min() - pad, centres[:, 0].min() - pad, centres[:, 1].max() + pad, centres[:, 0].max() + pad)
    tiles = [read_tile(ensure_tile(name, url)) for name, url in find_tiles(bbox)]
    if not tiles:
        raise AsterAccessError(f"no AG100 tiles found for bbox {bbox}")
    keys = BAND_NAMES + ["ndvi", "land_water_map", "num_obs"]
    results = []
    for patch_id, lat0, lon0 in patches:
        half_lon = half_lat / np.cos(np.radians(lat0))
        parts: dict[str, list[np.ndarray]] = {k: [] for k in keys}
        for tile in tiles:
            m = (np.abs(tile["lat"] - lat0) <= half_lat) & (np.abs(tile["lon"] - lon0) <= half_lon)
            if m.any():
                for k in keys:
                    parts[k].append(tile[k][m])
        if not parts["ndvi"]:
            results.append({"patch_id": patch_id, "composition_status": "missing", "composition_valid_pixel_ratio": 0.0})
            continue
        stats = extract_earth_composition({k: np.concatenate(v) for k, v in parts.items()})
        results.append({"patch_id": patch_id, **stats})
    return results
