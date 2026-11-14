"""Moon: diurnal bolometric temperature range from the Diviner Global Cumulative Product.

GCP (LRO-L-DLRE-5-GCP-V1.0) stores tbol per 0.5° cell and 96 local-time bins (0.25 h) in
fixed-width ASCII, so one cell is read with a single HTTP range request.
"""

from __future__ import annotations

import numpy as np
import requests

from config import THERMAL_MOON_GCP_URL, THERMAL_MOON_MIN_BINS
from src.thermal import extract_temperature_range

CELL_DEG = 0.5
BINS = 96
LAT_CELLS_PER_BAND = 20
ROW_BYTES = 113
NODATA = -9999.0
TBOL_MIN_K = 10.0  # below this a "temperature" is a sensor artefact (negative radiance)
SESSION = requests.Session()


def band_file(lat: float) -> tuple[str, float]:
    """File name and southern edge of the 10° latitude band that contains ``lat``."""
    lo = min(max(int(np.floor(lat / 10.0)) * 10, -90), 80)
    hi = lo + 10

    def tag(v: int, south: bool) -> str:
        return f"{abs(v):02d}{'s' if south else 'n'}"

    south = lo < 0  # the equator is "00s" in southern bands and "00n" in northern ones
    return f"global_cumul_avg_cyl_{tag(lo, south)}{tag(hi, south)}_002.tab", float(lo)


def fetch_cell_tbol(lat: float, lon: float) -> np.ndarray:
    """Return the 96 tbol values [K] of the cell containing (lat, lon); invalid -> NaN."""
    lon = (lon + 180.0) % 360.0 - 180.0
    name, lo = band_file(lat)
    lon_i = min(int((lon + 180.0) // CELL_DEG), 719)
    lat_i = min(max(int((lat - lo) // CELL_DEG), 0), LAT_CELLS_PER_BAND - 1)
    first = 1 + (lon_i * LAT_CELLS_PER_BAND + lat_i) * BINS
    start, end = first * ROW_BYTES, (first + BINS) * ROW_BYTES - 1
    resp = SESSION.get(
        f"{THERMAL_MOON_GCP_URL}/{name}", headers={"Range": f"bytes={start}-{end}"}, timeout=60
    )
    if resp.status_code != 206:
        raise RuntimeError(f"range request failed ({resp.status_code}) for {name}")
    rows = resp.text.strip().splitlines()
    if len(rows) != BINS:
        raise RuntimeError(f"expected {BINS} rows, got {len(rows)} for ({lat}, {lon})")
    tbol = np.array([float(r.split(",")[-1]) for r in rows])
    tbol[(tbol == NODATA) | (tbol < TBOL_MIN_K)] = np.nan
    return tbol


def moon_cell_stats(lat: float, lon: float) -> dict:
    """Diurnal tbol range of the cell containing (lat, lon), plus validity diagnostics."""
    tbol = fetch_cell_tbol(lat, lon)
    n_valid = int(np.isfinite(tbol).sum())
    rng = extract_temperature_range(tbol, min_obs=THERMAL_MOON_MIN_BINS)
    return {
        "surface_temperature_range_k": rng,
        "thermal_valid_fraction": n_valid / BINS,
        "thermal_valid_observations": n_valid,
    }
