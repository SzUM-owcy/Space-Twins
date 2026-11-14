"""Earth Sun position (pvlib), geometric elevation of the Sun's centre (no refraction)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pvlib import solarposition

from config import ILLUM_END, ILLUM_START, ILLUM_STEP_HOURS


def times() -> pd.DatetimeIndex:
    return pd.date_range(
        ILLUM_START, ILLUM_END, freq=f"{ILLUM_STEP_HOURS}h", tz="UTC", inclusive="left"
    )


def sun_position(lat: float, lon: float, t: pd.DatetimeIndex | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(elevation_deg, azimuth_deg clockwise from north) for every timestamp."""
    t = times() if t is None else t
    pos = solarposition.get_solarposition(t, lat, lon, method="nrel_numpy")
    return pos["elevation"].to_numpy(), pos["azimuth"].to_numpy()
