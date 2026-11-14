"""Live illumination of an arbitrary lunar point (LOLA horizon + SPICE Sun), for --lat/--lon queries."""

from __future__ import annotations

import rasterio

from config import LOLA_GLOBAL_PATH, LOLA_NODATA, LOLA_SCALE
from src.illumination import dem_window, extract_solar_visibility_fraction, horizon_profile
from src.moon_solar import sun_position


def moon_illumination_for(lat: float, lon: float, lola_path=LOLA_GLOBAL_PATH) -> dict:
    with rasterio.open(lola_path) as src:
        z = dem_window(src, lat, lon, "moon", LOLA_NODATA, LOLA_SCALE)
    if z is None:
        raise ValueError(f"({lat}, {lon}): poza rastrem LOLA")
    elev, azim = sun_position(lat, lon)
    return extract_solar_visibility_fraction(elev, azim, horizon_profile(z, "moon"))
