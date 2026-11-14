"""Patch extraction shared by Earth and Moon (CONTRACT §2)."""
from typing import Literal

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform as warp_transform
from rasterio.windows import Window

from config import GRID_N, MOON_RADIUS_M, PATCH_SIZE_M, PIXEL_SIZE_M

HALF = PATCH_SIZE_M / 2
MARGIN_PX = 4
MAX_ZERO_HEIGHT_FRAC = 0.05  # Earth water rule, source pixels
MAX_ZERO_SLOPE_FRAC = 0.20  # Earth water rule, interior pixels


def aeqd_crs(lat: float, lon: float, body: str) -> CRS:
    datum = "+datum=WGS84" if body == "earth" else f"+R={MOON_RADIUS_M}"
    return CRS.from_string(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 {datum} +units=m +no_defs"
    )


def _zero_slope_fraction(z: np.ndarray) -> float:
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * PIXEL_SIZE_M)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * PIXEL_SIZE_M)
    return float(np.mean(np.hypot(dzdx, dzdy) == 0))


def extract_patch(
    src: rasterio.DatasetReader,
    center_lat: float,
    center_lon: float,
    body: Literal["earth", "moon"],
    src_crs: CRS | None = None,
    nodata: float | None = None,
    scale: float = 1.0,
    offset: float = 0.0,
) -> np.ndarray | None:
    """Cut a 10x10 km, 85x85 patch (row 0 = north) centred on (lat, lon).

    Returns float64 metres, or None if rejected (outside raster, any nodata in
    the source window, water for Earth). `nodata`, `scale` and `offset` are
    supplied by the caller; src.scales is NOT read. z = value * scale + offset
    (LOLA: scale=0.5, NASADEM: scale=1.0).
    """
    src_crs = src_crs or src.crs
    dst_crs = aeqd_crs(center_lat, center_lon, body)

    # Patch outline in the source CRS -> source pixel window.
    t = np.linspace(-HALF, HALF, 21)
    xs, ys = np.meshgrid(t, t)
    edge = np.zeros_like(xs, dtype=bool)
    edge[[0, -1], :] = edge[:, [0, -1]] = True
    sx, sy = warp_transform(dst_crs, src_crs, xs[edge].tolist(), ys[edge].tolist())

    inv = ~src.transform
    cols, rows = zip(*(inv @ (x, y) for x, y in zip(sx, sy)))
    c0, c1 = int(np.floor(min(cols))), int(np.ceil(max(cols)))
    r0, r1 = int(np.floor(min(rows))), int(np.ceil(max(rows)))
    if c0 < 0 or r0 < 0 or c1 > src.width or r1 > src.height:
        return None

    mc0, mr0 = max(c0 - MARGIN_PX, 0), max(r0 - MARGIN_PX, 0)
    mc1, mr1 = min(c1 + MARGIN_PX, src.width), min(r1 + MARGIN_PX, src.height)
    window = Window(mc0, mr0, mc1 - mc0, mr1 - mr0)
    raw = src.read(1, window=window).astype(np.float64)

    inner = raw[r0 - mr0 : r1 - mr0, c0 - mc0 : c1 - mc0]
    if nodata is not None and np.any(inner == nodata):
        return None
    if body == "earth" and np.mean(inner == 0) > MAX_ZERO_HEIGHT_FRAC:
        return None

    if nodata is not None:
        raw[raw == nodata] = np.nan
    raw = raw * scale + offset

    dst = np.full((GRID_N, GRID_N), np.nan, dtype=np.float64)
    reproject(
        source=raw,
        destination=dst,
        src_transform=src.window_transform(window),
        src_crs=src_crs,
        dst_transform=from_bounds(-HALF, -HALF, HALF, HALF, GRID_N, GRID_N),
        dst_crs=dst_crs,
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.average,
    )
    if not np.all(np.isfinite(dst)):
        return None
    if body == "earth" and _zero_slope_fraction(dst) > MAX_ZERO_SLOPE_FRAC:
        return None
    return dst
