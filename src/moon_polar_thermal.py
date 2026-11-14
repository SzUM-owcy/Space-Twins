"""Moon, south polar sites: diurnal temperature range from the Diviner Polar Cumulative Product (PCP, 240 m).

PCP tables (Williams et al. 2019) hold bolometric temperature binned at 240 m and 0.25 h of local time, one
table per local-time bin and season (summer / winter), in polar stereographic coordinates (x, y in units of
the lunar radius) sorted by x with fixed 59-byte records. Only the x-band of a site is fetched with HTTP range
requests (a few MB per file instead of ~210 MB), then cropped to the 10 x 10 km footprint.

Per season: patch-median temperature in each sampled local-time bin -> P95 - P05 of that curve.
Site value: mean of the summer and winter values (the two seasons have different polar illumination).
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from config import MOON_RADIUS_M, PATCH_SIZE_M

PCP_BASE = (
    "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/"
    "data_derived_pcp/diurnal/ltim/pols"
)
RECORD_BYTES = 59  # fixed-length ASCII records; the first record is the column header
LTIM_BINS = tuple(range(1, 97, 2))  # every second 0.25 h bin (0.5 h spacing) is enough for P95 - P05
MIN_PIXELS = 30  # valid 240 m pixels in the footprint needed for a bin (about 1700 fit in the footprint)
MIN_BINS = 24  # of len(LTIM_BINS) bins needed for a season
BRACKET_ROWS = 4000
SEASONS = ("sum", "win")
DATASET = "LRO Diviner PCP tbol (240 m, 0.5 h local-time bins; mean of summer and winter P95-P05)"


def polar_xy(lat: float, lon: float) -> tuple[float, float]:
    """South polar stereographic (x, y) in lunar radii, as used by the PCP tables (lon east positive)."""
    r = 2.0 * np.tan(np.radians(90.0 + lat) / 2.0)
    return float(r * np.sin(np.radians(lon))), float(r * np.cos(np.radians(lon)))


class _Table:
    """One PCP .tab file read through HTTP range requests."""

    def __init__(self, url: str, session: requests.Session) -> None:
        self.url, self.session = url, session
        head = session.head(url, timeout=60)
        head.raise_for_status()
        self.n_rows = int(head.headers["Content-Length"]) // RECORD_BYTES - 1

    def _fetch(self, first: int, last: int) -> np.ndarray:
        """Rows ``first..last`` (inclusive) as an (n, 5) array: x, y, lon, lat, tbol."""
        start = (first + 1) * RECORD_BYTES
        end = (last + 2) * RECORD_BYTES - 1
        resp = self.session.get(self.url, headers={"Range": f"bytes={start}-{end}"}, timeout=120)
        resp.raise_for_status()
        return pd.read_csv(io.StringIO(resp.text), header=None).to_numpy(dtype=np.float64)

    def _x_at(self, i: int) -> float:
        return float(self._fetch(i, i)[0, 0])

    def _bracket(self, x: float) -> tuple[int, int]:
        """Interval [lo, hi] of at most BRACKET_ROWS rows that contains the first row with x >= ``x``."""
        lo, hi = 0, self.n_rows - 1
        x_lo, x_hi = self._x_at(lo), self._x_at(hi)
        step = 0
        while hi - lo > BRACKET_ROWS:
            step += 1
            if step % 3 == 0 or x_hi <= x_lo:
                mid = (lo + hi) // 2  # bisection guards against non-uniform density
            else:
                mid = lo + int((x - x_lo) / (x_hi - x_lo) * (hi - lo))
            mid = min(max(mid, lo + 1), hi - 1)
            x_mid = self._x_at(mid)
            if x_mid < x:
                lo, x_lo = mid, x_mid
            else:
                hi, x_hi = mid, x_mid
        return lo, hi

    def window(self, x0: float, y0: float, half: float) -> np.ndarray:
        """Rows with |x - x0| <= half and |y - y0| <= half."""
        first = self._bracket(x0 - half)[0]
        last = self._bracket(x0 + half)[1]
        rows = self._fetch(first, last)
        keep = (np.abs(rows[:, 0] - x0) <= half) & (np.abs(rows[:, 1] - y0) <= half)
        return rows[keep]


def _bin_value(args: tuple[str, int, float, float, float]) -> tuple[str, int, float, int]:
    season, ltim, x0, y0, half = args
    session = requests.Session()
    url = f"{PCP_BASE}/pcp_avg_tbol_pols_{season}_ltim{ltim:02d}_240.tab"
    rows = _Table(url, session).window(x0, y0, half)
    t = rows[:, 4]
    t = t[np.isfinite(t) & (t > 0)]
    return season, ltim, float(np.median(t)) if t.size >= MIN_PIXELS else float("nan"), int(t.size)


def polar_site_thermal(lat: float, lon: float, workers: int = 12) -> dict:
    """Thermal stats of one south-polar site (lat <= -80): summer/winter P95-P05 and their mean."""
    if lat > -80.0:
        raise ValueError(f"PCP south polar product covers lat <= -80, got {lat}")
    x0, y0 = polar_xy(lat, lon)
    half = PATCH_SIZE_M / 2.0 / MOON_RADIUS_M
    jobs = [(s, b, x0, y0, half) for s in SEASONS for b in LTIM_BINS]
    with ThreadPoolExecutor(workers) as pool:
        out = list(pool.map(_bin_value, jobs))
    ranges, n_bins = {}, {}
    for season in SEASONS:
        curve = np.array([v for s, _, v, _ in out if s == season])
        valid = curve[np.isfinite(curve)]
        n_bins[season] = int(valid.size)
        ranges[season] = float(np.percentile(valid, 95) - np.percentile(valid, 5)) if valid.size >= MIN_BINS else float("nan")
    values = [v for v in ranges.values() if np.isfinite(v)]
    return {
        "surface_temperature_range_k": float(np.mean(values)) if len(values) == len(SEASONS) else float("nan"),
        "thermal_summer_range_k": ranges["sum"],
        "thermal_winter_range_k": ranges["win"],
        "thermal_valid_observations": min(n_bins.values()),
        "thermal_valid_fraction": min(n_bins.values()) / len(LTIM_BINS),
    }
