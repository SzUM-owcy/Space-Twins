"""Validate solar_visibility_fraction at the lunar south pole against NASA's LOLA average-visibility map.

    uv run --frozen python 4_validate_illumination.py

Needs (gitignored, see README): data/validation/illumination/AVGVISIB_65S_240M_201608.JP2
and data/validation/lola_polar/LDEM_80S_80MPP_ADJ.TIF. Compares the project's horizon + SPICE method on
the 80 m polar DEM and on the 118 m global DEM with the official map (ordering and spatial pattern, not
exact equality: the official map uses another DEM and an 18.6-year cycle).

Validation uses the absolute visibility (any part of the solar disc above the unfloored terrain horizon),
which is what the official product stores; the production feature divides by the flat-horizon share.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy.stats import spearmanr

from config import DATA_DIR, LOLA_GLOBAL_PATH, LOLA_NODATA, LOLA_SCALE, MOON_RADIUS_M, OUTPUT_DIR
from src.illumination import dem_window, horizon_profile
from src.moon_solar import sun_position
from src.raster_io import aeqd_crs

OFFICIAL = DATA_DIR / "validation" / "illumination" / "AVGVISIB_65S_240M_201608.JP2"
POLAR_DEM = DATA_DIR / "validation" / "lola_polar" / "LDEM_80S_80MPP_ADJ.TIF"
OFFICIAL_SCALE = 0.00004
SUN_RADIUS_DEG = 0.267  # "any part of the solar disc"
SITES = {  # centres from data/moon_index.csv
    "shackleton": (-89.69, 126.1),
    "haworth": (-87.5, -5.0),
    "de_gerlache": (-88.39, -91.4),
    "malapert": (-85.9, 0.0),
}
RADIUS_M, STEP_M = 10_000, 1_000
MOON_LONLAT = f"+proj=longlat +R={MOON_RADIUS_M} +no_defs"


def grid_offsets() -> list[tuple[float, float]]:
    t = np.arange(-RADIUS_M, RADIUS_M + 1, STEP_M, dtype=float)
    return [(float(e), float(n)) for n in t for e in t]


def visibility(elev, azim, horizon_row) -> float:
    grid = np.arange(len(horizon_row)) * 360.0 / len(horizon_row)
    h = np.interp(azim, grid, horizon_row, period=360.0)
    return float(np.mean(elev + SUN_RADIUS_DEG > h))


def computed(lat0, lon0, z, step_m, offsets):
    """Absolute visibility per offset point, with the Sun position of each point itself."""
    hz = horizon_profile(z, "moon", offsets, step_m=step_m)
    to_ll = Transformer.from_crs(aeqd_crs(lat0, lon0, "moon"), MOON_LONLAT, always_xy=True)
    lons, lats = to_ll.transform([o[0] for o in offsets], [o[1] for o in offsets])
    out = []
    for lat, lon, row in zip(lats, lons, hz):
        out.append(np.nan if not np.isfinite(row).all() else visibility(*sun_position(lat, lon), row))
    return np.array(out), np.array(lats), np.array(lons)


def official(lats, lons, src, rotate_deg=0.0) -> np.ndarray:
    tr = Transformer.from_crs(MOON_LONLAT, src.crs, always_xy=True)
    x, y = tr.transform(lons + rotate_deg, lats)
    vals = np.array([v[0] for v in src.sample(zip(x, y))], dtype=float)
    return vals * OFFICIAL_SCALE


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--horizon-km", type=float, default=20.0, help="DEM window half-size for horizons (default 20)")
    args = ap.parse_args()
    horizon_m = args.horizon_km * 1000
    offsets = grid_offsets()
    rows = []
    with rasterio.open(OFFICIAL) as off, rasterio.open(POLAR_DEM) as dem80, rasterio.open(LOLA_GLOBAL_PATH) as dem118:
        for name, (lat, lon) in SITES.items():
            z80 = dem_window(dem80, lat, lon, "moon", None, 1.0, radius_m=horizon_m, step_m=100.0)
            z118 = dem_window(dem118, lat, lon, "moon", LOLA_NODATA, LOLA_SCALE, radius_m=horizon_m)
            for label, z, step in (("dem80", z80, 100.0), ("dem118", z118, 250.0)):
                vis, lats, lons = computed(lat, lon, z, step, offsets)
                ref = official(lats, lons, off)
                for o, v, r, la, lo in zip(offsets, vis, ref, lats, lons):
                    rows.append((name, label, o[0], o[1], la, lo, v, r))
    df = pd.DataFrame(rows, columns=["site", "dem", "east_m", "north_m", "lat", "lon", "computed", "official"])
    OUTPUT_DIR.mkdir(exist_ok=True)
    df.to_csv(OUTPUT_DIR / "illumination_validation.csv", index=False)

    print(f"Horizon window +-{args.horizon_km:g} km. Spearman correlation computed vs official ({len(offsets)} points per site, 1 km spacing)")
    for dem, g in df.groupby("dem"):
        parts = []
        for site, s in g.groupby("site"):
            s = s.dropna()
            rho = spearmanr(s["computed"], s["official"]).statistic if s["official"].nunique() > 1 else np.nan
            parts.append(f"{site} {rho:.2f}")
        a = g.dropna()
        print(f"  {dem}: " + ", ".join(parts) + f" | all {spearmanr(a['computed'], a['official']).statistic:.2f}")
    print("\nPer site (dem80): median computed / median official; shadow (<0.02) share computed / official")
    g = df[df["dem"] == "dem80"].dropna()
    for site, s in g.groupby("site"):
        print(
            f"  {site}: {s['computed'].median():.3f} / {s['official'].median():.3f}; "
            f"{(s['computed'] < 0.02).mean():.2f} / {(s['official'] < 0.02).mean():.2f}"
        )
    low = g["official"] < 0.02
    print("\nExplicit points per site (dem80 window): lowest vs highest DEM point within 10 km of the site centre")
    pts = []
    with rasterio.open(OFFICIAL) as off, rasterio.open(POLAR_DEM) as dem80:
        for name, (lat, lon) in SITES.items():
            z = dem_window(dem80, lat, lon, "moon", None, 1.0, radius_m=horizon_m, step_m=100.0)
            n = z.shape[0]
            yy, xx = np.mgrid[0:n, 0:n]
            east, north = (xx - (n - 1) / 2) * 100.0, ((n - 1) / 2 - yy) * 100.0
            inside = np.hypot(east, north) <= RADIUS_M
            for label, idx in (("floor", np.nanargmin(np.where(inside, z, np.nan))), ("ridge", np.nanargmax(np.where(inside, z, np.nan)))):
                o = [(float(east.flat[idx]), float(north.flat[idx]))]
                v, la, lo = computed(lat, lon, z, 100.0, o)
                pts.append((name, label, float(z.flat[idx]), v[0], official(la, lo, off)[0]))
    p = pd.DataFrame(pts, columns=["site", "point", "elev_m", "computed", "official"])
    print(p.round(3).to_string(index=False))
    pivot = p.pivot(index="site", columns="point", values=["computed", "official"])
    print("ridge > floor: computed", int((pivot["computed"]["ridge"] > pivot["computed"]["floor"]).sum()), "of", len(pivot),
          "| official", int((pivot["official"]["ridge"] > pivot["official"]["floor"]).sum()), "of", len(pivot))
    print(
        f"\nOfficial shadow vs computed shadow agreement (dem80): {((g['computed'] < 0.02) == low).mean():.2f}; "
        f"mean computed where official shadow {g.loc[low, 'computed'].mean():.3f}, "
        f"elsewhere {g.loc[~low, 'computed'].mean():.3f}"
    )


if __name__ == "__main__":
    main()
