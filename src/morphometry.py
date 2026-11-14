"""Cechy terenu łatki 85x85 (CONTRACT §3).

Jedna funkcja publiczna: ``extract_patch_features``. Używana tak samo dla Księżyca
i dla Ziemi, więc definicje cech muszą być zgodne z kontraktem co do joty.
"""

from __future__ import annotations

import numpy as np

from config import FEATURE_NAMES, GRID_N

SLOPE_PERCENTILES = (5, 10, 25, 50, 75, 90, 95)  # kolejność jak SLOPE_FEATURES w config.py

# Poniżej tego rozstępu wysokości łatkę uznajemy za idealnie płaską (CONTRACT §3).
_FLAT_PTP = 1e-6


def _validate(patch: np.ndarray, pixel_size_m: float) -> np.ndarray:
    z = np.asarray(patch, dtype=np.float64)
    if z.shape != (GRID_N, GRID_N):
        raise ValueError(f"patch musi mieć kształt ({GRID_N}, {GRID_N}), jest {z.shape}")
    if not np.all(np.isfinite(z)):
        raise ValueError("patch zawiera NaN lub inf")
    if not np.isfinite(pixel_size_m) or pixel_size_m <= 0:
        raise ValueError(f"pixel_size_m musi być dodatnie, jest {pixel_size_m}")
    return z


def _horn_slope_deg(z: np.ndarray, pixel_size_m: float) -> np.ndarray:
    """Nachylenie metodą Horna [°] dla pikseli wewnętrznych (83x83, bez paddingu).

    Okno 3x3:  a b c / d e f / g h i
    """
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * pixel_size_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * pixel_size_m)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def _plane_fit_rms(z: np.ndarray, pixel_size_m: float) -> float:
    """RMS reszt po odjęciu płaszczyzny z = ax + by + c (MNK, x,y w metrach)."""
    n = z.shape[0]
    coords = (np.arange(n) - (n - 1) / 2) * pixel_size_m  # wyśrodkowane, lepsze uwarunkowanie
    xx, yy = np.meshgrid(coords, coords)
    design = np.column_stack([xx.ravel(), yy.ravel(), np.ones(z.size)])
    coef, *_ = np.linalg.lstsq(design, z.ravel(), rcond=None)
    residual = z.ravel() - design @ coef
    return float(np.sqrt(np.mean(residual**2)))


def _riley_tri_mean(z: np.ndarray) -> float:
    """TRI Rileya (1999): sqrt(suma kwadratów różnic do 8 sąsiadów), średnia po 83x83."""
    center = z[1:-1, 1:-1]
    n = z.shape[0]
    sq = np.zeros_like(center)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            neighbor = z[1 + dr : n - 1 + dr, 1 + dc : n - 1 + dc]
            sq += (neighbor - center) ** 2
    return float(np.mean(np.sqrt(sq)))


def _skewness(z: np.ndarray) -> float:
    """Skośność Fishera-Pearsona (bias=True), jak ``scipy.stats.skew`` domyślnie."""
    dev = z - z.mean()
    m2 = np.mean(dev**2)
    if m2 == 0:
        return 0.0
    return float(np.mean(dev**3) / m2**1.5)


def extract_patch_features(patch: np.ndarray, pixel_size_m: float) -> dict[str, float]:
    """Policz 12 cech terenu łatki 85x85 [m] (CONTRACT §3).

    Raises:
        ValueError: zły kształt, NaN/inf w łatce albo niedodatni ``pixel_size_m``.
    """
    z = _validate(patch, pixel_size_m)

    slope = _horn_slope_deg(z, pixel_size_m)
    slope_pcts = np.percentile(slope, SLOPE_PERCENTILES)

    z_min, z_max = float(z.min()), float(z.max())
    ptp = z_max - z_min
    flat = ptp < _FLAT_PTP

    features: dict[str, float] = {
        name: float(value)
        for name, value in zip(FEATURE_NAMES[: len(SLOPE_PERCENTILES)], slope_pcts)
    }
    features["rms_height"] = _plane_fit_rms(z, pixel_size_m)
    features["tri_mean"] = _riley_tri_mean(z)
    features["relief_range"] = float(ptp)
    features["hypsometric_integral"] = 0.5 if flat else float((z.mean() - z_min) / ptp)
    features["elev_skew"] = 0.0 if flat else _skewness(z)

    # Kolejność i zestaw kluczy dokładnie jak w FEATURE_NAMES.
    return {name: features[name] for name in FEATURE_NAMES}
