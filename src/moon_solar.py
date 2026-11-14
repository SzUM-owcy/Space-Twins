"""Moon Sun position from NASA/JPL SPICE (IAU_MOON frame, planetocentric east-positive longitude)."""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np
import requests
import spiceypy as spice

from config import (
    ILLUM_END,
    ILLUM_START,
    ILLUM_STEP_HOURS,
    MOON_RADIUS_M,
    SPICE_DIR,
    SPICE_KERNELS,
    SPICE_URL,
)

log = logging.getLogger(__name__)
_SUBDIR = {"naif0012.tls": "lsk", "pck00011.tpc": "pck", "de440s.bsp": "spk/planets"}


def ensure_kernels() -> list[str]:
    SPICE_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in SPICE_KERNELS:
        path = SPICE_DIR / name
        if not path.exists():
            url = f"{SPICE_URL}/{_SUBDIR[name]}/{name}"
            log.info("downloading %s", url)
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
        paths.append(str(path))
    return paths


@lru_cache(maxsize=1)
def sun_vectors_moon_frame() -> np.ndarray:
    """Sun position relative to the Moon centre in IAU_MOON (km), one row per hourly timestamp."""
    for k in ensure_kernels():
        spice.furnsh(k)
    start = spice.str2et(f"{ILLUM_START} 00:00:00 UTC")
    end = spice.str2et(f"{ILLUM_END} 00:00:00 UTC")
    ets = np.arange(start, end, ILLUM_STEP_HOURS * 3600.0)
    return np.array([spice.spkpos("SUN", et, "IAU_MOON", "LT+S", "MOON")[0] for et in ets])


def sun_position(lat: float, lon: float) -> tuple[np.ndarray, np.ndarray]:
    """(elevation_deg, azimuth_deg clockwise from north) of the Sun's centre at (lat, lon)."""
    phi, lam = np.radians(lat), np.radians(lon)
    east = np.array([-np.sin(lam), np.cos(lam), 0.0])
    north = np.array([-np.sin(phi) * np.cos(lam), -np.sin(phi) * np.sin(lam), np.cos(phi)])
    up = np.array([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)])
    rel = sun_vectors_moon_frame() - up * (MOON_RADIUS_M / 1000.0)  # observer on the surface (parallax)
    e, n, u = rel @ east, rel @ north, rel @ up
    elev = np.degrees(np.arctan2(u, np.hypot(e, n)))
    azim = np.degrees(np.arctan2(e, n)) % 360.0
    return elev, azim
