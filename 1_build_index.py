"""Build data/earth_index.csv: split regions into 10 km patches, extract, compute features.

    uv run python 1_build_index.py [--dem nasadem|copdem] [--regions uyuni,alps] [--workers 4]

Default: all regions of the chosen DEM. Existing rows of other regions are kept.
If Python SSL fails (WSL/proxy), set REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt.
"""
import argparse
import itertools
import logging
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.warp import transform as warp_transform

from config import (
    COPDEM_NODATA, DATA_DIR, EARTH_INDEX_PATH, EARTH_PATCH_DIR, NASADEM_NODATA, OUTPUT_DIR,
    PATCH_SIZE_M, PIXEL_SIZE_M, RECORD_COLUMNS,
)
from src.contracts import validate_records
from src.morphometry import extract_patch_features
from src.raster_io import aeqd_crs, extract_patch

download_tiles = import_module("0_download_earth").download_tiles
DEMS = import_module("0_download_earth").DEMS

MARGIN_DEG = 0.2  # tile margin around the region bbox (0.1 deg of lon at 56N is only ~6 km)
NODATA = {"nasadem": NASADEM_NODATA, "copdem": COPDEM_NODATA}


@dataclass(frozen=True)
class Region:
    slug: str
    dem: str
    bbox: tuple[float, float, float, float]  # W, S, E, N
    validation: bool = False  # known lunar analogue, used for post-MVP validation


# Phase 2 starter set. NASADEM covers ~60N..56S; higher latitudes need COPDEM.
REGIONS = [
    Region("uyuni", "nasadem", (-68.0, -20.7, -67.0, -19.7)),  # salt flat
    Region("black_rock", "nasadem", (-119.5, 40.4, -118.5, 41.4)),  # playa
    Region("meteor_crater", "nasadem", (-111.5, 34.5, -110.5, 35.5), validation=True),
    Region("etna", "nasadem", (14.5, 37.25, 15.5, 38.25)),  # volcano
    Region("alps", "nasadem", (7.0, 45.5, 8.0, 46.5)),  # steep control region
    Region("askja", "copdem", (-17.3, 64.8, -16.3, 65.8)),  # Iceland, lava fields
]


def check_regions(regions: list[Region]) -> None:
    slugs = [r.slug for r in regions]
    assert len(slugs) == len(set(slugs)), "duplicate region slug"
    for a, b in itertools.combinations(regions, 2):
        overlap = a.bbox[0] < b.bbox[2] and b.bbox[0] < a.bbox[2] and a.bbox[1] < b.bbox[3] and b.bbox[1] < a.bbox[3]
        assert not overlap, f"bboxes overlap: {a.slug} / {b.slug}"


def write_regions_csv(regions: list[Region]) -> None:
    """Region metadata incl. the `validation` flag (kept out of the 17-column index, CONTRACT §4)."""
    pd.DataFrame(
        [{"region": r.slug, "dem": r.dem, "validation": r.validation,
          "west": r.bbox[0], "south": r.bbox[1], "east": r.bbox[2], "north": r.bbox[3]} for r in regions]
    ).to_csv(DATA_DIR / "regions.csv", index=False)


def grid_centres(bbox) -> list[tuple[float, float]]:
    """Centres (lat, lon) of non-overlapping 10 km patches lying inside the bbox (row-major, N->S)."""
    w, s, e, n = bbox
    lat0, lon0 = (s + n) / 2, (w + e) / 2
    crs = aeqd_crs(lat0, lon0, "earth")
    t = np.linspace(0, 1, 11)
    def to_xy(lons, lats):
        x, y = warp_transform("EPSG:4326", crs, list(lons), list(lats))
        return np.array(x), np.array(y)
    # Largest metric rectangle inside the (slightly curved) bbox.
    xl, _ = to_xy([w] * 11, s + t * (n - s))
    xr, _ = to_xy([e] * 11, s + t * (n - s))
    _, yb = to_xy(w + t * (e - w), [s] * 11)
    _, yt = to_xy(w + t * (e - w), [n] * 11)
    x_min, x_max, y_min, y_max = xl.max(), xr.min(), yb.max(), yt.min()
    half = PATCH_SIZE_M / 2
    xs = np.arange(x_min + half, x_max - half + 1e-6, PATCH_SIZE_M)
    ys = np.arange(y_max - half, y_min + half - 1e-6, -PATCH_SIZE_M)  # north first
    px, py = np.meshgrid(xs, ys)
    lon, lat = warp_transform(crs, "EPSG:4326", px.ravel().tolist(), py.ravel().tolist())
    return list(zip(lat, lon))


def make_mosaic(region: Region, tiles: list[Path]) -> Path:
    path = tiles[0].parent / f"mosaic_{region.slug}.tif"
    if path.exists():
        return path
    w, s, e, n = region.bbox
    bounds = (w - MARGIN_DEG, s - MARGIN_DEG, e + MARGIN_DEG, n + MARGIN_DEG)
    srcs = [rasterio.open(t) for t in tiles]
    try:
        data, transform = merge(srcs, bounds=bounds, nodata=NODATA[region.dem])
        profile = srcs[0].profile | {
            "driver": "GTiff", "height": data.shape[1], "width": data.shape[2],
            "transform": transform, "compress": "deflate", "tiled": True, "blockxsize": 256,
            "blockysize": 256, "nodata": NODATA[region.dem],
        }
    finally:
        for src in srcs:
            src.close()
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
    return path


class _ReasonCounter(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.counts: Counter = Counter()

    def emit(self, record):
        self.counts[record.getMessage().removeprefix("reject: ")] += 1


def process_region(region: Region, mosaic: Path) -> tuple[list[dict], Counter]:
    """Runs in a worker process: opens its own file handle (rasterio objects are not picklable)."""
    counter = _ReasonCounter()
    raster_log = logging.getLogger("src.raster_io")
    raster_log.setLevel(logging.DEBUG)
    raster_log.propagate = False
    raster_log.addHandler(counter)
    source = DEMS[region.dem][3]
    EARTH_PATCH_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    with rasterio.open(mosaic) as src:
        for i, (lat, lon) in enumerate(grid_centres(region.bbox)):
            patch = extract_patch(src, lat, lon, "earth", nodata=NODATA[region.dem])
            if patch is None:
                continue
            patch_id = f"earth_{region.slug}_{i:04d}"
            np.save(EARTH_PATCH_DIR / f"{patch_id}.npy", patch.astype(np.float32))
            feats = extract_patch_features(patch, PIXEL_SIZE_M)
            rows.append({"patch_id": patch_id, "source": source, "region": region.slug,
                         "center_lat": lat, "center_lon": lon, **feats})
    return rows, counter.counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dem", choices=list(DEMS), default="nasadem")
    p.add_argument("--regions", help="comma-separated slugs (default: all of the chosen DEM)")
    p.add_argument("--workers", type=int, default=1)
    args = p.parse_args()

    check_regions(REGIONS)
    write_regions_csv(REGIONS)
    wanted = args.regions.split(",") if args.regions else None
    todo = [r for r in REGIONS if r.dem == args.dem and (wanted is None or r.slug in wanted)]
    if wanted and {r.slug for r in todo} != set(wanted):
        raise SystemExit(f"unknown region(s) for --dem {args.dem}: {set(wanted) - {r.slug for r in todo}}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(OUTPUT_DIR / "build_index.log", "w")])
    mosaics = {}
    for r in todo:  # download serially: neighbouring regions can share tiles
        w, s, e, n = r.bbox
        tiles = download_tiles([w - MARGIN_DEG, s - MARGIN_DEG, e + MARGIN_DEG, n + MARGIN_DEG], r.dem)
        mosaics[r.slug] = make_mosaic(r, tiles)

    with ProcessPoolExecutor(args.workers) as pool:
        results = list(pool.map(process_region, todo, [mosaics[r.slug] for r in todo]))

    new_rows = []
    for r, (rows, reasons) in zip(todo, results):
        total = len(grid_centres(r.bbox))
        logging.info("%s: %d/%d patches kept; rejected: %s", r.slug, len(rows), total, dict(reasons) or "none")
        new_rows += rows
    new = pd.DataFrame(new_rows, columns=RECORD_COLUMNS)
    if EARTH_INDEX_PATH.exists():
        old = pd.read_csv(EARTH_INDEX_PATH)
        new = pd.concat([old[~old["region"].isin([r.slug for r in todo])], new], ignore_index=True)
    validate_records(new)
    new.to_csv(EARTH_INDEX_PATH, index=False)
    logging.info("wrote %s (%d rows)", EARTH_INDEX_PATH, len(new))


if __name__ == "__main__":
    main()
