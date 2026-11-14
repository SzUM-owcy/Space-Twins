"""NASADEM vs COPDEM on the same patch centres (CONTRACT §10 pt 13) -> docs/dem_crosscheck.md.

    uv run python dem_crosscheck.py
"""
import dataclasses
from importlib import import_module

import numpy as np
import pandas as pd
import rasterio

from config import DATA_DIR, PIXEL_SIZE_M
from src.morphometry import extract_patch_features
from src.raster_io import extract_patch

bi = import_module("1_build_index")
FEATURES = ["slope_p50", "slope_p90", "rms_height", "tri_mean", "relief_range"]
REGIONS = ["meteor_crater", "mauna_loa"]


def features(region, dem):
    r = dataclasses.replace(region, dem=dem)
    w, s, e, n = r.bbox
    box = [w - bi.MARGIN_DEG, s - bi.MARGIN_DEG, e + bi.MARGIN_DEG, n + bi.MARGIN_DEG]
    # copdem needs its own mosaic file name
    r = dataclasses.replace(r, slug=f"{region.slug}_xcheck") if dem == "copdem" else r
    mosaic = bi.make_mosaic(r, bi.download_tiles(box, dem))
    out = {}
    with rasterio.open(mosaic) as src:
        for i, (lat, lon) in enumerate(bi.grid_centres(region.bbox)):
            p = extract_patch(src, lat, lon, "earth", nodata=bi.NODATA[dem])
            if p is not None:
                out[i] = extract_patch_features(p, PIXEL_SIZE_M)
    return pd.DataFrame.from_dict(out, orient="index")


lines = ["# NASADEM vs COPDEM cross-check", "",
         "Same patch centres, same `extract_patch` and features, only the DEM differs. "
         "Median of per-patch relative difference `(COPDEM - NASADEM) / NASADEM`.", "",
         "| Region | patches | " + " | ".join(FEATURES) + " |", "|---|---|" + "---|" * len(FEATURES)]
for slug in REGIONS:
    region = next(r for r in bi.REGIONS if r.slug == slug)
    a, b = features(region, "nasadem"), features(region, "copdem")
    idx = a.index.intersection(b.index)
    rel = [f"{np.median((b.loc[idx, f] - a.loc[idx, f]) / a.loc[idx, f].replace(0, np.nan)) * 100:+.1f}%" for f in FEATURES]
    med = [f"{a.loc[idx, 'slope_p50'].median():.2f} -> {b.loc[idx, 'slope_p50'].median():.2f}"]
    lines.append(f"| {slug} | {len(idx)} | " + " | ".join(rel) + " |")
    lines.append(f"<!-- {slug} median slope_p50 NASADEM -> COPDEM: {med[0]} -->")
(DATA_DIR.parent / "docs" / "dem_crosscheck.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
