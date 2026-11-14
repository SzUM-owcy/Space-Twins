import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform as warp_transform

from config import GRID_N, MOON_RADIUS_M, PIXEL_SIZE_M
from raster_io import aeqd_crs, extract_patch

NODATA = -32768
M_PER_DEG = 111_000
EARTH_CENTER = (35.03, -111.02)  # lat, lon
EARTH_SLOPE = 0.1  # rise/run towards north
MOON_CENTER = (14.0, -56.0)
MOON_SLOPE = 0.05
MOON_CRS = f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R={MOON_RADIUS_M} +units=m +no_defs"


def _write(path, arr, transform, crs):
    with rasterio.open(
        path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
        count=1, dtype=arr.dtype, crs=crs, transform=transform,
    ) as dst:
        dst.write(arr, 1)
    return path


@pytest.fixture
def earth_tif(tmp_path):
    """EPSG:4326, 1 arcsec, plane rising north with slope EARTH_SLOPE."""
    px = 1 / 3600
    west, north, n = EARTH_CENTER[1] - 0.15, EARTH_CENTER[0] + 0.15, 1080
    lat = north - (np.arange(n) + 0.5) * px
    z = 1000 + EARTH_SLOPE * (lat - EARTH_CENTER[0]) * M_PER_DEG
    arr = np.repeat(z[:, None], n, axis=1).astype(np.float32)
    path = _write(tmp_path / "earth.tif", arr, from_origin(west, north, px, px), "EPSG:4326")
    return path, arr, px, west, north


@pytest.fixture
def moon_tif(tmp_path):
    """Equirectangular metres, LOLA-like pixel, plane rising north, zero at centre."""
    px = 118.45
    cx = MOON_RADIUS_M * np.radians(MOON_CENTER[1])
    cy = MOON_RADIUS_M * np.radians(MOON_CENTER[0])
    n = 300
    west, north = cx - n * px / 2, cy + n * px / 2
    y = north - (np.arange(n) + 0.5) * px
    z_true = MOON_SLOPE * (y - cy)
    arr = np.repeat((z_true / 0.5)[:, None], n, axis=1).astype(np.float32)  # LOLA scale 0.5
    return _write(tmp_path / "moon.tif", arr, from_origin(west, north, px, px), MOON_CRS)


def _earth_patch(path):
    with rasterio.open(path) as src:
        return extract_patch(src, *EARTH_CENTER, "earth", nodata=NODATA)


def test_earth_shape_and_finite(earth_tif):
    patch = _earth_patch(earth_tif[0])
    assert patch.shape == (GRID_N, GRID_N)
    assert patch.dtype == np.float64
    assert np.all(np.isfinite(patch))


def test_earth_slope_and_orientation(earth_tif):
    patch = _earth_patch(earth_tif[0])
    dz_drow = np.gradient(patch, PIXEL_SIZE_M, axis=0)[10:-10, 10:-10].mean()
    dz_dcol = np.gradient(patch, PIXEL_SIZE_M, axis=1)[10:-10, 10:-10].mean()
    assert dz_drow == pytest.approx(-EARTH_SLOPE, rel=0.03)  # row 0 = north = high
    assert abs(dz_dcol) < 1e-3


def test_outside_raster_returns_none(earth_tif):
    with rasterio.open(earth_tif[0]) as src:
        assert extract_patch(src, EARTH_CENTER[0] + 0.14, EARTH_CENTER[1], "earth", nodata=NODATA) is None


@pytest.mark.parametrize("dlon,dlat", [(0, 0), (-0.04, 0.04)])  # centre and near a corner
def test_nodata_hole_in_patch_rejects(earth_tif, dlon, dlat):
    path, arr, px, west, north = earth_tif
    arr = arr.copy()
    r = int((north - (EARTH_CENTER[0] + dlat)) / px)
    c = int((EARTH_CENTER[1] + dlon - west) / px)
    arr[r, c] = NODATA
    hole = path.with_name("hole.tif")
    _write(hole, arr, from_origin(west, north, px, px), "EPSG:4326")
    assert _earth_patch(hole) is None


def test_nodata_outside_patch_is_ignored(earth_tif):
    path, arr, px, west, north = earth_tif
    arr = arr.copy()
    arr[int((north - EARTH_CENTER[0]) / px), int((EARTH_CENTER[1] + 0.08 - west) / px)] = NODATA
    far = path.with_name("far.tif")
    _write(far, arr, from_origin(west, north, px, px), "EPSG:4326")
    assert _earth_patch(far) is not None


@pytest.mark.parametrize("height", [0.0, 1000.0])  # sea level and a flat lake
def test_earth_water_rejected(earth_tif, height):
    path, arr, px, west, north = earth_tif
    flat = path.with_name("flat.tif")
    _write(flat, np.full_like(arr, height), from_origin(west, north, px, px), "EPSG:4326")
    assert _earth_patch(flat) is None


def test_roundtrip_centre_is_origin_earth():
    (x,), (y,) = warp_transform("EPSG:4326", aeqd_crs(*EARTH_CENTER, "earth"), [EARTH_CENTER[1]], [EARTH_CENTER[0]])
    assert abs(x) < 1 and abs(y) < 1


def test_roundtrip_centre_is_origin_moon():
    (x,), (y,) = warp_transform(MOON_CRS, aeqd_crs(*MOON_CENTER, "moon"),
                                [MOON_RADIUS_M * np.radians(MOON_CENTER[1])],
                                [MOON_RADIUS_M * np.radians(MOON_CENTER[0])])
    assert abs(x) < 1 and abs(y) < 1


def test_moon_patch_scale_and_slope(moon_tif):
    with rasterio.open(moon_tif) as src:
        patch = extract_patch(src, *MOON_CENTER, "moon", nodata=NODATA, scale=0.5)
    assert patch.shape == (GRID_N, GRID_N)
    assert abs(patch[GRID_N // 2, GRID_N // 2]) < 5  # plane is 0 m at the centre
    dz_drow = np.gradient(patch, PIXEL_SIZE_M, axis=0)[10:-10, 10:-10].mean()
    assert dz_drow == pytest.approx(-MOON_SLOPE, rel=0.03)
