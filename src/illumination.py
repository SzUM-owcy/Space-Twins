"""Shared solar-visibility logic for Earth and Moon (same function for both bodies).

solar_visibility_fraction = share of the time the Sun is above the *terrain* horizon,
relative to the time it is above the flat astronomical horizon (elevation > 0).
Over a full year the astronomical share is ~0.5 almost everywhere, so only the terrain
horizon carries signal. Geometric visibility of the Sun's centre; no atmosphere,
refraction or clouds on either body.
"""

from __future__ import annotations

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform as warp_transform
from rasterio.windows import Window
from scipy.ndimage import map_coordinates

from config import (
    ILLUM_AZIMUTHS,
    ILLUM_GRID_STEP_M,
    ILLUM_HORIZON_RADIUS_M,
    ILLUM_MIN_ASTRO_FRACTION,
    ILLUM_POINTS_N,
    ILLUM_POINTS_SPAN_M,
    MOON_RADIUS_M,
)
from src.raster_io import aeqd_crs

EARTH_RADIUS_M = 6_371_000.0
BODY_RADIUS_M = {"earth": EARTH_RADIUS_M, "moon": float(MOON_RADIUS_M)}


def dem_window(
    src: rasterio.DatasetReader,
    lat: float,
    lon: float,
    body: str,
    nodata: float | None,
    scale: float = 1.0,
    src_crs: CRS | None = None,
    radius_m: float = ILLUM_HORIZON_RADIUS_M,
    step_m: float = ILLUM_GRID_STEP_M,
) -> np.ndarray | None:
    """Elevation (m) on an azimuthal-equidistant grid centred on (lat, lon), row 0 = north.

    Pixels outside the raster or nodata are NaN. None if the window does not touch the raster.
    """
    src_crs = src_crs or src.crs
    dst_crs = aeqd_crs(lat, lon, body)
    n = int(round(2 * radius_m / step_m))
    t = np.linspace(-radius_m, radius_m, 41)
    xs, ys = np.meshgrid(t, t)
    sx, sy = warp_transform(dst_crs, src_crs, xs.ravel().tolist(), ys.ravel().tolist())
    inv = ~src.transform
    cols, rows = zip(*(inv @ (x, y) for x, y in zip(sx, sy)))
    c0, c1 = max(int(np.floor(min(cols))) - 2, 0), min(int(np.ceil(max(cols))) + 2, src.width)
    r0, r1 = max(int(np.floor(min(rows))) - 2, 0), min(int(np.ceil(max(rows))) + 2, src.height)
    if c1 <= c0 or r1 <= r0:
        return None
    window = Window(c0, r0, c1 - c0, r1 - r0)
    raw = src.read(1, window=window).astype(np.float64)
    if nodata is not None:
        raw[raw == nodata] = np.nan
    raw = raw * scale
    dst = np.full((n, n), np.nan)
    reproject(
        source=raw, destination=dst,
        src_transform=src.window_transform(window), src_crs=src_crs,
        dst_transform=from_bounds(-radius_m, -radius_m, radius_m, radius_m, n, n),
        dst_crs=dst_crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.average,
    )
    return dst if np.isfinite(dst).any() else None


def observer_points(
    n: int = ILLUM_POINTS_N, span_m: float = ILLUM_POINTS_SPAN_M
) -> list[tuple[float, float]]:
    """NxN (east, north) offsets in metres around the patch centre."""
    offs = np.linspace(-span_m / 2, span_m / 2, n) if n > 1 else np.array([0.0])
    return [(float(e), float(nn)) for nn in offs for e in offs]


def observer_latlon(
    lat: float, lon: float, body: str, points: list[tuple[float, float]]
) -> tuple[np.ndarray, np.ndarray]:
    """Latitude/longitude of (east, north) metre offsets from the patch centre."""
    radius = BODY_RADIUS_M[body]
    to_ll = Transformer.from_crs(aeqd_crs(lat, lon, body), f"+proj=longlat +R={radius} +no_defs", always_xy=True)
    lons, lats = to_ll.transform([p[0] for p in points], [p[1] for p in points])
    return np.asarray(lats), np.asarray(lons)


def horizon_profile(
    z: np.ndarray,
    body: str,
    points: list[tuple[float, float]] | None = None,
    step_m: float = ILLUM_GRID_STEP_M,
    n_az: int = ILLUM_AZIMUTHS,
) -> np.ndarray:
    """Terrain horizon elevation angle (deg) per observer point and azimuth bin (clockwise from N).

    Ray-marches over `z` and subtracts the curvature drop d^2 / 2R (about 260 m at 30 km on the Moon).
    Returns shape (n_points, n_az); NaN where the observer cell is unknown.
    """
    points = points or observer_points()
    radius = BODY_RADIUS_M[body]
    n = z.shape[0]
    c = (n - 1) / 2.0
    az = np.deg2rad(np.arange(n_az) * 360.0 / n_az)
    out = np.full((len(points), n_az), np.nan)
    for i, (e0, n0) in enumerate(points):
        col0, row0 = c + e0 / step_m, c - n0 / step_m
        z0 = map_coordinates(z, [[row0], [col0]], order=1, mode="nearest")[0]
        if not np.isfinite(z0):
            continue
        max_d = (n / 2.0 - 1) * step_m
        d = np.arange(step_m, max_d, step_m)
        cols = col0 + np.outer(np.sin(az), d) / step_m
        rows = row0 - np.outer(np.cos(az), d) / step_m
        zz = map_coordinates(z, [rows.ravel(), cols.ravel()], order=1, mode="constant", cval=np.nan)
        zz = zz.reshape(len(az), len(d))
        ang = np.degrees(np.arctan2(zz - z0 - d**2 / (2 * radius), d))
        with np.errstate(all="ignore"):
            hz = np.nanmax(np.where(np.isfinite(ang), ang, -90.0), axis=1)
        out[i] = hz
    return out


def extract_solar_visibility_fraction(
    sun_elevation_deg: np.ndarray,
    sun_azimuth_deg: np.ndarray,
    horizon_deg: np.ndarray,
) -> dict:
    """Shared Earth/Moon aggregation.

    sun_*: (n_samples,) for one Sun track, or (n_points, n_samples) with a Sun track per observer point
    (matters near the poles, where the local azimuth changes quickly over a few km).
    horizon_deg: (n_points, n_az) terrain horizon. Per point: terrain visibility = share of samples
    with elevation > max(horizon, 0); astronomical = share with elevation > 0. The patch fraction is
    the median over points of terrain/astronomical; NaN when the Sun is almost never up.
    """
    n_az = horizon_deg.shape[1]
    grid = np.arange(n_az) * 360.0 / n_az
    elev2d = np.atleast_2d(sun_elevation_deg)
    azim2d = np.atleast_2d(sun_azimuth_deg)
    if elev2d.shape[0] == 1:
        elev2d = np.repeat(elev2d, len(horizon_deg), axis=0)
        azim2d = np.repeat(azim2d, len(horizon_deg), axis=0)
    astro_pts = (elev2d > 0).mean(axis=1)
    astro = float(np.median(astro_pts))
    valid = np.isfinite(horizon_deg).all(axis=1)
    if not valid.any() or astro < ILLUM_MIN_ASTRO_FRACTION:
        return {"fraction": np.nan, "astro": astro, "terrain": np.nan, "points": int(valid.sum())}
    terr, ratio = [], []
    for i in np.flatnonzero(valid):
        up = elev2d[i] > 0
        h_at_sun = np.interp(azim2d[i][up], grid, horizon_deg[i], period=360.0)
        t = np.mean(elev2d[i][up] > np.maximum(h_at_sun, 0.0)) * astro_pts[i]
        terr.append(t)
        ratio.append(t / astro_pts[i] if astro_pts[i] > 0 else np.nan)
    terrain = float(np.median(terr))
    return {
        "fraction": float(np.nanmedian(ratio)),
        "astro": astro,
        "terrain": terrain,
        "points": int(valid.sum()),
    }
