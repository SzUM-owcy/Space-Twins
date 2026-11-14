"""Practicality side table (cost / access / constraints), separate from the scientific analog score.

Usage:
  uv run --frozen python 1f_build_practicality.py init       # create data/practicality_earth.csv (all patches, nothing measured)
  uv run --frozen python 1f_build_practicality.py buildability  # best 1 km facility core per patch from the cached DEM patches
  uv run --frozen python 1f_build_practicality.py access         # city + healthcare travel time (Malaria Atlas WCS), airports, roads
  uv run --frozen python 1f_build_practicality.py population     # WorldPop people within 10/25/50 km
  uv run --frozen python 1f_build_practicality.py landcover      # ESA WorldCover bare/tree/wetland fractions
  uv run --frozen python 1f_build_practicality.py grid           # OSM high-voltage line distance (cached regions) + approximate estimates; --fetch queries Overpass
  uv run --frozen python 1f_build_practicality.py protected      # WDPA overlap per patch -> data/practicality/protected.csv (cache only)
  uv run --frozen python 1f_build_practicality.py flags          # volcano hazard + all constraint flags, merged into the table
  uv run --frozen python 1f_build_practicality.py finalize   # recompute derived scores/classes from the raw columns present

Later phases add steps that fill raw columns (buildability, population, travel time, ...) and then call finalize.
Existing raw values are kept across ``init`` reruns only through ``finalize``; ``init`` never overwrites an existing table.
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from config import (
    EARTH_INDEX_PATH,
    EARTH_NPZ_DIR,
    PRACTICALITY_CITY_COVERAGE,
    PRACTICALITY_DIR,
    PRACTICALITY_GRID_CENSORED_KM,
    PRACTICALITY_GRID_ESTIMATE_KM,
    PRACTICALITY_GRID_PAD_DEG,
    PRACTICALITY_HEALTH_COVERAGE,
    PRACTICALITY_PATH,
    PRACTICALITY_PROTECTED_CACHE,
    PRACTICALITY_URLS,
    PRACTICALITY_WORLDPOP_PATH,
)
from src import practicality_data as pdata
from src import practicality_flags as pflags
from src.buildability import best_facility_core
from src.practicality import empty_table, score_table

log = logging.getLogger("practicality")


def cmd_init(force: bool) -> None:
    if PRACTICALITY_PATH.exists() and not force:
        log.info("%s exists; use --force to recreate", PRACTICALITY_PATH)
        return
    ids = pd.read_csv(EARTH_INDEX_PATH, usecols=["patch_id"])["patch_id"]
    cmd_write(score_table(empty_table(ids)))


def cmd_write(df: pd.DataFrame) -> None:
    PRACTICALITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PRACTICALITY_PATH, index=False)
    log.info("wrote %s (%d rows)", PRACTICALITY_PATH, len(df))


def cmd_buildability() -> None:
    df = pd.read_csv(PRACTICALITY_PATH)
    rows = {}
    for path in sorted(EARTH_NPZ_DIR.glob("*.npz")):
        with np.load(path) as z:
            for pid in z.files:
                rows[pid] = best_facility_core(z[pid])
    res = pd.DataFrame.from_dict(rows, orient="index")
    for col in res.columns:
        df[col] = df["patch_id"].map(res[col])
    log.info("buildability for %d/%d patches", int(df["facility_core_slope_p90"].notna().sum()), len(df))
    cmd_write(score_table(df))


def _centres() -> pd.DataFrame:
    return pd.read_csv(EARTH_INDEX_PATH, usecols=["patch_id", "region", "center_lat", "center_lon"])


def _merge(df: pd.DataFrame, res: pd.DataFrame) -> pd.DataFrame:
    for col in res.columns:
        df[col] = df["patch_id"].map(res[col])
    return df


def cmd_access() -> None:
    df = pd.read_csv(PRACTICALITY_PATH)
    idx = _centres().set_index("patch_id")
    res = pd.DataFrame(index=idx.index, columns=["city_travel_minutes", "hospital_travel_minutes"], dtype=float)
    for region, g in idx.groupby("region"):
        w, e = g.center_lon.min() - 0.2, g.center_lon.max() + 0.2
        s_, n = g.center_lat.min() - 0.2, g.center_lat.max() + 0.2
        for col, cov in (("city_travel_minutes", PRACTICALITY_CITY_COVERAGE), ("hospital_travel_minutes", PRACTICALITY_HEALTH_COVERAGE)):
            try:
                path = pdata.wcs_raster(cov, w, s_, e, n, f"{region}_{col}")
            except Exception as exc:
                log.warning("%s %s failed: %s", region, col, exc)
                continue
            res.loc[g.index, col] = [pdata.raster_median(path, la, lo) for la, lo in zip(g.center_lat, g.center_lon)]
        log.info("travel time: %s", region)
    pts = idx[["center_lat", "center_lon"]].to_numpy()
    res["airport_travel_minutes"] = pdata.airport_travel_minutes(pdata.nearest_distance_km(pts, pdata.load_airports()))
    res["major_road_distance_km"] = pdata.nearest_distance_km(pts, pdata.load_road_points())
    cmd_write(score_table(_merge(df, res)))


def cmd_population() -> None:
    import rasterio

    idx = _centres().set_index("patch_id")
    rows = {}
    pdata._download(PRACTICALITY_URLS["worldpop"], PRACTICALITY_WORLDPOP_PATH)
    with rasterio.open(PRACTICALITY_WORLDPOP_PATH) as src:
        for pid, r in idx.iterrows():
            pop = pdata.population_within(src, r.center_lat, r.center_lon)
            rows[pid] = {f"population_{k}km": v for k, v in pop.items()}
    df = pd.read_csv(PRACTICALITY_PATH)  # re-read: other steps may have written meanwhile
    cmd_write(score_table(_merge(df, pd.DataFrame.from_dict(rows, orient="index"))))


def cmd_landcover() -> None:
    df = pd.read_csv(PRACTICALITY_PATH)
    idx = _centres().set_index("patch_id")
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda r: pdata.worldcover_fractions(r.center_lat, r.center_lon), idx.itertuples()))
    res = pd.DataFrame(results, index=idx.index)
    log.info("landcover for %d/%d patches", int(res["bare_ground_fraction"].notna().sum()), len(res))
    cmd_write(score_table(_merge(df, res)))


def cmd_grid(fetch: bool) -> None:
    """OSM high-voltage lines from the Overpass cache; ``--fetch`` queries missing regions, else approximate estimates are used."""
    idx = _centres().set_index("patch_id")
    cache = PRACTICALITY_DIR / "power"
    cache.mkdir(parents=True, exist_ok=True)
    dist = pd.Series(np.nan, index=idx.index)
    source = pd.Series("missing", index=idx.index)
    for region, g in idx.groupby("region"):
        f = cache / f"{region}.npy"
        if not f.exists() and fetch:
            pad = PRACTICALITY_GRID_PAD_DEG
            np.save(f, pdata.overpass_power_points(g.center_lon.min() - pad, g.center_lat.min() - pad, g.center_lon.max() + pad, g.center_lat.max() + pad))
        if f.exists():
            pts = np.load(f)
            # no line inside the search box: the true distance is at least the censored value
            dist[g.index] = pdata.nearest_distance_km(g[["center_lat", "center_lon"]].to_numpy(), pts) if len(pts) else PRACTICALITY_GRID_CENSORED_KM
            source[g.index] = "osm"
        elif region in PRACTICALITY_GRID_ESTIMATE_KM:
            dist[g.index] = PRACTICALITY_GRID_ESTIMATE_KM[region]
            source[g.index] = "estimated"
    df = pd.read_csv(PRACTICALITY_PATH)  # re-read: other steps may have written meanwhile
    df["grid_distance_km"] = df["patch_id"].map(dist.clip(upper=PRACTICALITY_GRID_CENSORED_KM))
    df["grid_source"] = df["patch_id"].map(source)
    log.info("grid source: %s", source.value_counts().to_dict())
    cmd_write(score_table(df))


def cmd_protected() -> None:
    idx = _centres().set_index("patch_id")
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda r: pflags.protected_overlap(r.center_lat, r.center_lon), idx.itertuples()))
    res = pd.DataFrame(results, index=idx.index)
    PRACTICALITY_PROTECTED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(PRACTICALITY_PROTECTED_CACHE)
    log.info("protected-area lookups ok for %d/%d patches", int(res["protected_overlap_fraction"].notna().sum()), len(res))


def cmd_flags() -> None:
    df = pd.read_csv(PRACTICALITY_PATH)
    idx = _centres().set_index("patch_id")
    df = _merge(df, pd.read_csv(PRACTICALITY_PROTECTED_CACHE, index_col=0))
    vol = pflags.nearest_volcano(idx[["center_lat", "center_lon"]].to_numpy(), pflags.load_volcanoes())
    vol.index = idx.index
    df = _merge(df, vol)
    df = pflags.derive_flags(df, df["patch_id"].map(idx["region"]))
    cmd_write(score_table(df))


def cmd_finalize() -> None:
    cmd_write(score_table(pd.read_csv(PRACTICALITY_PATH)))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["init", "buildability", "access", "population", "landcover", "grid", "protected", "flags", "finalize"])
    p.add_argument("--force", action="store_true")
    p.add_argument("--fetch", action="store_true", help="grid: query Overpass for regions without a cache")
    args = p.parse_args()
    {"init": lambda: cmd_init(args.force), "buildability": cmd_buildability, "access": cmd_access, "population": cmd_population, "landcover": cmd_landcover, "grid": lambda: cmd_grid(args.fetch), "protected": cmd_protected, "flags": cmd_flags, "finalize": cmd_finalize}[args.step]()


if __name__ == "__main__":
    main()
