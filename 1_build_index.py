"""Build data/earth_index.csv: split regions into 10 km patches, extract, compute features.

    uv run python 1_build_index.py [--dem nasadem|copdem] [--regions uyuni,alps] [--workers 4]
    uv run python 1_build_index.py --npz   # pack patches into data/patches/earth_npz/{region}.npz

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
    COPDEM_NODATA, DATA_DIR, EARTH_INDEX_PATH, EARTH_NPZ_DIR, EARTH_PATCH_DIR, NASADEM_NODATA, OUTPUT_DIR,
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
    stride_km: float = PATCH_SIZE_M / 1000  # grid step; < patch size gives overlapping patches (small bboxes)


# Phase 2 starter set. NASADEM covers ~60N..56S; higher latitudes need COPDEM.
REGIONS = [
    Region("uyuni", "nasadem", (-67.9, -20.5, -67.1, -19.9)),  # salt flat only (no Andean volcano slopes)
    Region("black_rock", "nasadem", (-119.5, 40.4, -118.5, 41.4)),  # playa
    Region("meteor_crater", "nasadem", (-111.5, 34.5, -110.5, 35.5), validation=True),
    Region("etna", "nasadem", (14.5, 37.25, 15.5, 38.25)),  # volcano
    Region("alps", "nasadem", (7.0, 45.5, 8.0, 46.5)),  # steep control region
    Region("askja", "copdem", (-17.3, 64.8, -16.3, 65.8)),  # Iceland, lava fields (also covers Krafla, Holuhraun)
    # flat
    Region("bonneville", "nasadem", (-114.3, 40.3, -113.3, 41.3)),
    # volcanic / lava
    Region("mauna_loa", "nasadem", (-155.95, 19.1, -155.05, 19.75)),
    Region("mauna_kea", "nasadem", (-155.9, 19.75, -155.1, 20.2), validation=True),
    Region("craters_of_the_moon", "nasadem", (-114.0, 43.0, -113.0, 44.0), validation=True),
    Region("pinacate", "nasadem", (-114.0, 31.4, -113.0, 32.4), validation=True),
    Region("lanzarote", "nasadem", (-14.0, 28.7, -13.2, 29.3)),
    Region("teide", "nasadem", (-17.2, 27.9, -16.2, 28.6)),
    Region("reunion", "nasadem", (55.2, -21.4, 55.9, -20.85)),
    Region("paricutin", "nasadem", (-102.75, 19.0, -101.75, 20.0)),
    Region("klyuchevskoy", "nasadem", (160.1, 55.6, 161.1, 56.6)),
    # craters
    Region("aorounga", "nasadem", (18.75, 18.6, 19.75, 19.6)),
    Region("ries", "nasadem", (10.0, 48.4, 11.0, 49.4), validation=True),
    Region("cinder_lake", "nasadem", (-112.5, 35.0, -111.5, 36.0), validation=True),
    # desert / dunes
    Region("erg_chebbi", "nasadem", (-4.5, 30.7, -3.5, 31.7)),
    Region("namib", "nasadem", (14.8, -25.0, 15.8, -24.0)),
    Region("lut", "nasadem", (58.5, 30.0, 59.5, 31.0)),
    Region("wadi_rum", "nasadem", (35.0, 29.1, 36.0, 30.1)),
    Region("gran_desierto", "nasadem", (-115.0, 31.6, -114.0, 32.6)),
    # mountains / steep
    Region("tibesti", "nasadem", (17.0, 20.5, 18.0, 21.5)),
    Region("atacama", "nasadem", (-69.0, -24.5, -68.0, -23.5)),
    Region("tien_shan", "nasadem", (79.5, 41.5, 80.5, 42.5)),
    # plateaus / basins
    Region("colorado_plateau", "nasadem", (-111.0, 36.5, -110.0, 37.5)),
    Region("basin_and_range", "nasadem", (-117.0, 38.5, -116.0, 39.5)),
    Region("patagonia", "nasadem", (-72.0, -47.0, -71.0, -46.0)),
    Region("death_valley", "nasadem", (-117.5, 36.0, -116.5, 37.0)),
    Region("rio_grande_gorge", "nasadem", (-106.2, 35.8, -105.2, 36.8), validation=True),
    # high latitude (COPDEM); bboxes widened in longitude because 1 deg of lon is ~49 km at 64N, ~28 km at 75N
    Region("hekla", "copdem", (-20.7, 63.6, -18.7, 64.6)),
    Region("odadahraun", "copdem", (-16.3, 65.0, -14.3, 66.0)),
    Region("haughton", "copdem", (-92.0, 75.0, -88.0, 75.8), validation=True),
    # phase 4: rough / steep terrain, impact structures, polar, basalt
    Region("hoggar", "nasadem", (5.0, 22.8, 6.0, 23.8)),
    Region("danakil", "nasadem", (40.2, 13.1, 41.2, 14.1)),
    Region("zagros", "nasadem", (50.3, 31.5, 51.3, 32.5)),
    Region("ladakh", "nasadem", (77.5, 33.8, 78.5, 34.8)),
    Region("puna", "nasadem", (-68.0, -27.0, -67.0, -26.0)),
    Region("high_atlas", "nasadem", (-6.0, 31.2, -5.0, 32.2)),
    Region("khaybar", "nasadem", (39.4, 25.2, 40.4, 26.2)),  # harrat basalt field
    Region("gosses_bluff", "nasadem", (131.8, -24.4, 132.8, -23.4)),
    Region("wolfe_creek", "nasadem", (127.3, -19.7, 128.3, -18.7)),
    Region("vredefort", "nasadem", (27.0, -27.5, 28.0, -26.5)),
    Region("richat", "nasadem", (-11.9, 20.6, -10.9, 21.6)),
    Region("dry_valleys", "copdem", (160.5, -77.7, 162.5, -77.3)),  # Antarctica, ice-free valleys
    # Exploratory candidates (axel_heiberg dropped: its bbox is all sea level -> water_zero_height); small bboxes are sampled with overlapping patches (stride_km < 10).
    Region("jingpo_lake", "nasadem", (128.5, 43.87, 129.0, 44.33), stride_km=5),  # lava tubes / lake risk
    Region("kamestastin", "nasadem", (-63.6, 55.7, -63.0, 56.05), stride_km=5),  # impact + anorthosite
    Region("sittampundi", "nasadem", (77.75, 11.1, 78.05, 11.35), stride_km=5),  # anorthosite
    Region("dalangtan", "nasadem", (91.17, 38.0, 92.17, 38.67)),  # hyperarid playa
    Region("schirmacher_oasis", "copdem", (11.45, -70.8, 11.9, -70.7), stride_km=2.5),  # Antarctica
    Region("meidob", "nasadem", (25.95, 14.95, 27.0, 15.65)),  # volcanic field
    Region("lava_beds", "nasadem", (-121.75, 41.65, -121.25, 42.05), stride_km=5),
    Region("elgygytgyn", "copdem", (171.65, 67.35, 172.45, 67.65), stride_km=5),  # arctic impact crater
    Region("lonar", "nasadem", (76.44, 19.92, 76.58, 20.04), stride_km=2.5),  # basalt impact crater
    Region("saririaky", "nasadem", (46.0, -23.7, 46.25, -23.42), stride_km=5),  # anorthosite massif
    Region("white_sands", "nasadem", (-106.45, 32.7, -105.95, 33.0), stride_km=5),  # gypsum dunes
    Region("sverrefjell", "copdem", (13.05, 79.35, 13.6, 79.5), stride_km=2.5),  # Arctic volcano
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


def grid_centres(bbox, stride_km: float = PATCH_SIZE_M / 1000) -> list[tuple[float, float]]:
    """Centres (lat, lon) of 10 km patches (non-overlapping at the default stride) lying inside the bbox (row-major, N->S)."""
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
    step = stride_km * 1000
    xs = np.arange(x_min + half, x_max - half + 1e-6, step)
    ys = np.arange(y_max - half, y_min + half - 1e-6, -step)  # north first
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
        for i, (lat, lon) in enumerate(grid_centres(region.bbox, region.stride_km)):
            patch = extract_patch(src, lat, lon, "earth", nodata=NODATA[region.dem])
            if patch is None:
                continue
            patch_id = f"earth_{region.slug}_{i:04d}"
            np.save(EARTH_PATCH_DIR / f"{patch_id}.npy", patch.astype(np.float32))
            feats = extract_patch_features(patch, PIXEL_SIZE_M)
            rows.append({"patch_id": patch_id, "source": source, "region": region.slug,
                         "center_lat": lat, "center_lon": lon, **feats})
    return rows, counter.counts


def build_npz(regions: list[str] | None = None) -> None:
    """Pack patches into data/patches/earth_npz/{region}.npz (keys = patch_id, float32).

    Existing region files are left untouched (rewriting changes the bytes and bloats git history)
    unless the region is named in ``regions``.
    """
    index = pd.read_csv(EARTH_INDEX_PATH)
    EARTH_NPZ_DIR.mkdir(parents=True, exist_ok=True)
    for region, ids in index.groupby("region")["patch_id"]:
        out = EARTH_NPZ_DIR / f"{region}.npz"
        if out.exists() and not (regions and region in regions):
            continue
        np.savez_compressed(out, **{i: np.load(EARTH_PATCH_DIR / f"{i}.npy").astype(np.float32) for i in ids})
        print(f"wrote {out.name} ({len(ids)} patches, {out.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dem", choices=list(DEMS), default="nasadem")
    p.add_argument("--regions", help="comma-separated slugs (default: all of the chosen DEM)")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--npz", action="store_true", help="only pack patches into data/patches/earth_npz/{region}.npz (existing files kept unless named in --regions)")
    args = p.parse_args()
    if args.npz:
        return build_npz(args.regions.split(",") if args.regions else None)

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
        total = len(grid_centres(r.bbox, r.stride_km))
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
