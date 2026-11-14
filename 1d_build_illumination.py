"""Solar-illumination side tables: terrain-shaded Sun visibility per Earth/Moon patch.

Usage:
  uv run --frozen python 1d_build_illumination.py earth [--regions a,b] [--workers 8]
  uv run --frozen python 1d_build_illumination.py moon

Writes data/illumination_earth.csv and data/illumination_moon.csv (keyed by patch_id).
The CONTRACT index CSVs are untouched. Earth is resumable by region.
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import rasterio

from config import (
    COPDEM_DIR,
    COPDEM_NODATA,
    DATA_DIR,
    EARTH_INDEX_PATH,
    ILLUM_COLUMNS,
    ILLUM_EARTH_PATH,
    ILLUM_END,
    ILLUM_HORIZON_RADIUS_M,
    ILLUM_MOON_PATH,
    ILLUM_START,
    LOLA_GLOBAL_PATH,
    LOLA_NODATA,
    LOLA_SCALE,
    NASADEM_DIR,
    NASADEM_NODATA,
)
from src.illumination import dem_window, extract_solar_visibility_fraction, horizon_profile

log = logging.getLogger("illumination")
PERIOD = f"{ILLUM_START}/{ILLUM_END} hourly"
EARTH_DATASET = "NASADEM/COPDEM horizon (20 km window, 250 m) + pvlib NREL SPA"
MOON_DATASET = "LOLA 118 m horizon (20 km window, 250 m) + SPICE DE440s/IAU_MOON"
MOON_INDEX_PATH = DATA_DIR / "moon_index.csv"
DEM_INFO = {
    "nasadem": (NASADEM_DIR, NASADEM_NODATA),
    "copdem": (COPDEM_DIR, COPDEM_NODATA),
}
_open: dict = {}


def _src(path):
    if path not in _open:
        _open[path] = rasterio.open(path)
    return _open[path]


def _row(patch_id: str, lat: float, lon: float, body: str, path, nodata, scale, sun_position) -> dict:
    row = {
        "patch_id": patch_id, "solar_visibility_fraction": np.nan, "solar_visibility_astro": np.nan,
        "solar_visibility_terrain": np.nan, "illumination_points": 0,
        "illumination_horizon_km": ILLUM_HORIZON_RADIUS_M / 1000,
    }
    z = dem_window(_src(path), lat, lon, body, nodata, scale)
    if z is None:
        return row
    elev, azim = sun_position(lat, lon)
    res = extract_solar_visibility_fraction(elev, azim, horizon_profile(z, body))
    row.update(
        solar_visibility_fraction=res["fraction"], solar_visibility_astro=res["astro"],
        solar_visibility_terrain=res["terrain"], illumination_points=res["points"],
    )
    return row


def _earth_task(args) -> dict:
    from src.earth_solar import sun_position

    patch_id, lat, lon, dem, slug = args
    folder, nodata = DEM_INFO[dem]
    return _row(patch_id, lat, lon, "earth", folder / f"mosaic_{slug}.tif", nodata, 1.0, sun_position)


def _read_table(path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=ILLUM_COLUMNS)


def _write_table(df: pd.DataFrame, path) -> None:
    df.reindex(columns=ILLUM_COLUMNS).to_csv(path, index=False)


def build_earth(regions: list[str] | None, workers: int) -> None:
    index = pd.read_csv(EARTH_INDEX_PATH)
    dems = pd.read_csv(DATA_DIR / "regions.csv").set_index("region")["dem"]
    table = _read_table(ILLUM_EARTH_PATH)
    done = set(index.loc[index["patch_id"].isin(table["patch_id"]), "region"])
    with ProcessPoolExecutor(workers) as pool:
        for region in regions or sorted(index["region"].unique()):
            if region in done and not regions:
                continue
            sub = index[index["region"] == region]
            tasks = [
                (p, lat, lon, dems[region], region)
                for p, lat, lon in zip(sub["patch_id"], sub["center_lat"], sub["center_lon"])
            ]
            new = pd.DataFrame(list(pool.map(_earth_task, tasks, chunksize=8)))
            new["illumination_dataset"] = EARTH_DATASET
            new["illumination_period"] = PERIOD
            table = pd.concat([table[~table["patch_id"].isin(new["patch_id"])], new], ignore_index=True)
            _write_table(table, ILLUM_EARTH_PATH)
            f = new["solar_visibility_fraction"]
            log.info("%s: %d/%d valid, median %.3f", region, f.notna().sum(), len(f), f.median())


def build_moon() -> None:
    from src.moon_solar import sun_position

    idx = pd.read_csv(MOON_INDEX_PATH)
    rows = []
    for pid, lat, lon in zip(idx["patch_id"], idx["center_lat"], idx["center_lon"]):
        rows.append(_row(pid, lat, lon, "moon", LOLA_GLOBAL_PATH, LOLA_NODATA, LOLA_SCALE, sun_position))
        log.info("%s: %.3f", pid, rows[-1]["solar_visibility_fraction"])
    df = pd.DataFrame(rows)
    df["illumination_dataset"] = MOON_DATASET
    df["illumination_period"] = PERIOD
    _write_table(df, ILLUM_MOON_PATH)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("body", choices=["earth", "moon"])
    ap.add_argument("--regions", help="comma-separated Earth regions to (re)compute")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.body == "earth":
        build_earth(args.regions.split(",") if args.regions else None, args.workers)
    else:
        build_moon()


if __name__ == "__main__":
    main()
