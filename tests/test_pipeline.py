"""End-to-end: synthetic raster -> extract_patch -> features -> records -> find_analogs."""
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from config import PIXEL_SIZE_M, RECORD_COLUMNS
from src.contracts import validate_records
from src.morphometry import extract_patch_features
from src.query import find_analogs
from src.raster_io import extract_patch

M_PER_DEG = 111_000
PX = 1 / 3600
SLOPES = {"flat": 0.002, "hilly": 0.1, "steep": 0.5}  # rise/run towards north
CENTERS = {"flat": (10.0, 20.0), "hilly": (30.0, 40.0), "steep": (-20.0, 60.0)}


def _raster(path, lat0, lon0, slope, seed):
    n = 720  # 0.2 deg, enough for a 10 km patch plus margin
    west, north = lon0 - 0.1, lat0 + 0.1
    lat = north - (np.arange(n) + 0.5) * PX
    z = 1000 + slope * (lat - lat0) * M_PER_DEG
    z = z[:, None] + np.random.default_rng(seed).normal(0, 1 + 20 * slope, (n, n))
    with rasterio.open(
        path, "w", driver="GTiff", height=n, width=n, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(west, north, PX, PX),
    ) as dst:
        dst.write(z.astype(np.float32), 1)
    return path


@pytest.fixture
def earth_index(tmp_path):
    rows = []
    for seed, (name, slope) in enumerate(SLOPES.items()):
        lat, lon = CENTERS[name]
        path = _raster(tmp_path / f"{name}.tif", lat, lon, slope, seed)
        with rasterio.open(path) as src:
            # small jitter of the centre -> several distinct patches per region
            for i, d in enumerate((0.0, 0.01, -0.01)):
                patch = extract_patch(src, lat + d, lon, "earth")
                assert patch is not None
                feats = extract_patch_features(patch, PIXEL_SIZE_M)
                rows.append(
                    {"patch_id": f"earth_{name}_{i:04d}", "source": "NASADEM",
                     "region": name, "center_lat": lat + d, "center_lon": lon, **feats}
                )
    df = pd.DataFrame(rows)[RECORD_COLUMNS]
    validate_records(df)
    return df


@pytest.mark.parametrize("name", list(SLOPES))
def test_moon_like_patch_matches_its_own_region(earth_index, name):
    # a "Moon" patch taken from the same synthetic terrain must rank that region first
    moon = earth_index[earth_index["region"] == name].iloc[0]
    result = find_analogs(moon[RECORD_COLUMNS[5:]].to_dict(), earth_index, top_k=3)
    assert result.loc[0, "region"] == name
    assert result["region"].is_unique
    assert result["total_distance"].is_monotonic_increasing
    assert list(result["rank"]) == [1, 2, 3]


def test_flat_terrain_is_closer_to_hilly_than_to_steep(earth_index):
    moon = earth_index[earth_index["region"] == "flat"].iloc[0]
    result = find_analogs(moon[RECORD_COLUMNS[5:]].to_dict(), earth_index, top_k=3)
    assert list(result["region"]) == ["flat", "hilly", "steep"]
