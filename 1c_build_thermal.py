"""Thermal side tables: surface temperature range per Earth/Moon patch + percentile references.

Usage:
  uv run --frozen python 1c_build_thermal.py earth [--regions a,b] [--workers 16]
  uv run --frozen python 1c_build_thermal.py moon  [--workers 16]
  uv run --frozen python 1c_build_thermal.py finalize

``finalize`` builds the versioned reference distributions and writes
``thermal_range_percentile`` into both side tables. The CONTRACT index CSVs are untouched.
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from config import (
    EARTH_INDEX_PATH,
    THERMAL_COLUMNS,
    THERMAL_EARTH_PATH,
    THERMAL_EARTH_REFERENCE_PATH,
    THERMAL_MOON_GRID_STEP_DEG,
    THERMAL_MOON_PATH,
    THERMAL_MOON_REFERENCE_PATH,
    THERMAL_REFERENCE_END,
    THERMAL_REFERENCE_START,
)
from src.thermal import build_reference, empirical_cdf, save_reference

log = logging.getLogger("thermal")
EARTH_DATASET = "MODIS MOD11A2/MYD11A2.061 LST day+night"
MOON_DATASET = "LRO Diviner GCP tbol (0.5 deg, 96 local-time bins)"
MOON_INDEX_PATH = EARTH_INDEX_PATH.with_name("moon_index.csv")
MOON_REFERENCE_GRID_PATH = THERMAL_MOON_PATH.with_name("thermal_moon_grid.csv")
PERIOD = f"{THERMAL_REFERENCE_START}/{THERMAL_REFERENCE_END}"


def _read_table(path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=THERMAL_COLUMNS)


def _write_table(df: pd.DataFrame, path) -> None:
    df = df.reindex(columns=THERMAL_COLUMNS)
    df.to_csv(path, index=False)


def build_earth(regions: list[str] | None, workers: int) -> None:
    from src.earth_temperature import region_thermal

    index = pd.read_csv(EARTH_INDEX_PATH)
    table = _read_table(THERMAL_EARTH_PATH)
    todo = regions or sorted(index["region"].unique())
    done_regions = set(index.loc[index["patch_id"].isin(table["patch_id"]), "region"])
    for region in todo:
        if region in done_regions and not regions:
            continue
        sub = index[index["region"] == region]
        patches = list(zip(sub["patch_id"], sub["center_lat"], sub["center_lon"]))
        try:
            rows = region_thermal(patches, workers=workers)
        except Exception as exc:  # keep going; the region can be retried
            log.error("%s: failed (%s)", region, exc)
            continue
        new = pd.DataFrame(rows)
        new["thermal_dataset"] = EARTH_DATASET
        new["thermal_period"] = PERIOD
        table = pd.concat([table[~table["patch_id"].isin(new["patch_id"])], new], ignore_index=True)
        _write_table(table, THERMAL_EARTH_PATH)
        ok = new["surface_temperature_range_k"].notna().sum()
        log.info(
            "%s: %d/%d patches valid, range median %.1f K",
            region, ok, len(new), new["surface_temperature_range_k"].median(),
        )


def _grid_points() -> list[tuple[float, float]]:
    """Area-uniform grid of lunar cell centres (lon spacing widens towards the poles)."""
    step = THERMAL_MOON_GRID_STEP_DEG
    points = []
    for lat in np.arange(-90 + step / 2, 90, step):
        n_lon = max(1, int(round(360.0 / step * np.cos(np.radians(lat)))))
        for lon in (np.arange(n_lon) + 0.5) * 360.0 / n_lon - 180.0:
            points.append((float(lat), float(lon)))
    return points


def build_moon(workers: int) -> None:
    from src.moon_temperature import moon_cell_stats

    sites = pd.read_csv(MOON_INDEX_PATH)
    site_pts = list(zip(sites["patch_id"], sites["center_lat"], sites["center_lon"]))

    def one(p):
        try:
            return {"patch_id": p[0], **moon_cell_stats(p[1], p[2])}
        except Exception as exc:
            log.error("%s: failed (%s)", p[0], exc)
            return None

    with ThreadPoolExecutor(workers) as pool:
        rows = [r for r in pool.map(one, site_pts) if r]
    table = pd.DataFrame(rows)
    table["thermal_dataset"] = MOON_DATASET
    table["thermal_period"] = "2009-07-05/2015-04-01"
    _write_table(table, THERMAL_MOON_PATH)
    log.info("moon sites: %d/%d valid", table["surface_temperature_range_k"].notna().sum(), len(table))

    if MOON_REFERENCE_GRID_PATH.exists():
        return
    pts = _grid_points()
    log.info("fetching %d reference cells", len(pts))
    with ThreadPoolExecutor(workers) as pool:
        stats = list(pool.map(lambda p: moon_cell_stats(*p), pts))
    grid = pd.DataFrame(stats)
    grid.insert(0, "lat", [p[0] for p in pts])
    grid.insert(1, "lon", [p[1] for p in pts])
    grid.to_csv(MOON_REFERENCE_GRID_PATH, index=False)


def finalize() -> None:
    earth = _read_table(THERMAL_EARTH_PATH)
    ref = build_reference(earth["surface_temperature_range_k"].to_numpy(float), EARTH_DATASET, PERIOD)
    save_reference(ref, THERMAL_EARTH_REFERENCE_PATH)
    earth["thermal_range_percentile"] = empirical_cdf(earth["surface_temperature_range_k"], ref)
    _write_table(earth, THERMAL_EARTH_PATH)
    log.info("earth reference: n=%d version=%s", ref["n"], ref["version"])

    grid = pd.read_csv(MOON_REFERENCE_GRID_PATH)
    mref = build_reference(
        grid["surface_temperature_range_k"].to_numpy(float), MOON_DATASET, "2009-07-05/2015-04-01"
    )
    save_reference(mref, THERMAL_MOON_REFERENCE_PATH)
    moon = _read_table(THERMAL_MOON_PATH)
    moon["thermal_range_percentile"] = empirical_cdf(moon["surface_temperature_range_k"], mref)
    _write_table(moon, THERMAL_MOON_PATH)
    log.info("moon reference: n=%d version=%s", mref["n"], mref["version"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("step", choices=["earth", "moon", "finalize"])
    parser.add_argument("--regions", default=None, help="comma-separated Earth regions (re-does them)")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.step == "earth":
        build_earth(args.regions.split(",") if args.regions else None, args.workers)
    elif args.step == "moon":
        build_moon(args.workers)
    else:
        finalize()


if __name__ == "__main__":
    main()
