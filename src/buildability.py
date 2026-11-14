"""Buildability: find the flattest ~1 x 1 km facility core inside a 10 x 10 km Earth patch."""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from config import FACILITY_CORE_PIXELS, FACILITY_CORE_STRIDE, PIXEL_SIZE_M
from src.morphometry import _horn_slope_deg


def best_facility_core(patch: np.ndarray, pixel_size_m: float = PIXEL_SIZE_M) -> dict[str, float]:
    """Slide a window over the patch; return slope P90 and relief of the most buildable core.

    Best = lowest slope P90, ties broken by lower relief. NaN values if the patch has no finite data.
    """
    z = np.asarray(patch, dtype=np.float64)
    if not np.all(np.isfinite(z)):
        return {"facility_core_slope_p90": np.nan, "facility_core_relief_m": np.nan}
    slope = _horn_slope_deg(z, pixel_size_m)  # slope[i, j] belongs to elevation pixel (i + 1, j + 1)
    w, step = FACILITY_CORE_PIXELS, FACILITY_CORE_STRIDE
    slope_win = sliding_window_view(slope, (w, w))[::step, ::step]
    elev_win = sliding_window_view(z[1:-1, 1:-1], (w, w))[::step, ::step]
    if slope_win.size == 0:
        return {"facility_core_slope_p90": np.nan, "facility_core_relief_m": np.nan}
    p90 = np.percentile(slope_win, 90, axis=(-2, -1))
    relief = np.ptp(elev_win, axis=(-2, -1))
    k = np.lexsort((relief.ravel(), p90.ravel()))[0]  # lowest slope P90, ties by relief
    best = (float(p90.ravel()[k]), float(relief.ravel()[k]))
    return {"facility_core_slope_p90": best[0], "facility_core_relief_m": best[1]}
