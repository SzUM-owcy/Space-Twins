"""Live illumination of an arbitrary lunar point (LOLA horizon + SPICE Sun), for --lat/--lon queries."""

from __future__ import annotations

import rasterio

import numpy as np

from config import ILLUM_HORIZON_RADIUS_MOON_M, LOLA_GLOBAL_PATH, LOLA_NODATA, LOLA_SCALE
from src.illumination import (
    dem_window,
    extract_solar_visibility_fraction,
    horizon_profile,
    observer_latlon,
    observer_points,
)
from src.moon_solar import sun_position


def moon_illumination_for(lat: float, lon: float, lola_path=LOLA_GLOBAL_PATH) -> dict:
    with rasterio.open(lola_path) as src:
        z = dem_window(src, lat, lon, "moon", LOLA_NODATA, LOLA_SCALE, radius_m=ILLUM_HORIZON_RADIUS_MOON_M)
    if z is None:
        raise ValueError(f"({lat}, {lon}): poza rastrem LOLA")
    points = observer_points()
    tracks = [sun_position(la, lo) for la, lo in zip(*observer_latlon(lat, lon, "moon", points))]
    elev, azim = np.array([t[0] for t in tracks]), np.array([t[1] for t in tracks])
    return extract_solar_visibility_fraction(elev, azim, horizon_profile(z, "moon", points))
