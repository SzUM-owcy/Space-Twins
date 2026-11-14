"""Mafic-felsic composition proxy shared by Earth and Moon.

Earth: ASTER GED thermal-infrared emissivity ratios (Mafic Index MI = e12 / e13; Quartz Index
QI = e11^2 / (e10 * e12), used only as a confounder diagnostic). Moon: wavelength of the Diviner
Christiansen Feature (CF). The two raw values are never compared: each is converted to a
percentile within its own body, and ``mafic_felsic_percentile`` (0 = more felsic, 1 = more mafic)
is compared instead. This is a coarse proxy, not mineral or chemical equality.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from config import (
    ASTER_EMISSIVITY_SCALE,
    ASTER_LAND_CLASS,
    ASTER_NDVI_SCALE,
    COMPOSITION_MAX_NDVI,
    COMPOSITION_MIN_ASTER_OBS,
    COMPOSITION_MIN_VALID_RATIO,
    COMPOSITION_TRIM_PERCENT,
)

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_exposed_surface"
STATUS_OUTSIDE_CF = "outside_diviner_cf_coverage"
STATUS_MISSING = "missing"
HIGH_RATIO, MEDIUM_RATIO = 0.70, 0.50
MIN_PIXELS_FOR_TRIM = 20
INDEX_FORMULAS = {"mafic_index": "e12 / e13", "quartz_index": "e11**2 / (e10 * e12)"}


def calculate_aster_indices(
    e10: np.ndarray, e11: np.ndarray, e12: np.ndarray, e13: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel (Mafic Index, Quartz Index) from scaled emissivities; NaN where a division is undefined."""
    e10, e11, e12, e13 = (np.asarray(a, dtype=np.float64) for a in (e10, e11, e12, e13))
    with np.errstate(divide="ignore", invalid="ignore"):
        mi = np.where(e13 > 0, e12 / e13, np.nan)
        qi = np.where((e10 > 0) & (e12 > 0), e11**2 / (e10 * e12), np.nan)
    return np.where(np.isfinite(mi), mi, np.nan), np.where(np.isfinite(qi), qi, np.nan)


def composition_confidence(valid_ratio: float, quartz_flag: bool = False) -> str:
    """high / medium / low / low_quartz_confounder / missing from the valid-pixel ratio and the QI flag."""
    if not np.isfinite(valid_ratio) or valid_ratio < COMPOSITION_MIN_VALID_RATIO:
        return "missing"
    if quartz_flag:
        return "low_quartz_confounder"
    if valid_ratio >= HIGH_RATIO:
        return "high"
    return "medium" if valid_ratio >= MEDIUM_RATIO else "low"


def _trim(values: np.ndarray, percent: float) -> np.ndarray:
    """Drop the lowest and highest ``percent`` % as corrupted outliers (skipped for tiny samples)."""
    if values.size < MIN_PIXELS_FOR_TRIM or percent <= 0:
        return values
    lo, hi = np.percentile(values, [percent, 100.0 - percent])
    return values[(values >= lo) & (values <= hi)]


def extract_earth_composition(bands: dict[str, np.ndarray]) -> dict[str, float | str]:
    """Patch-level Earth diagnostics from raw (unscaled) ASTER GED arrays of one patch footprint.

    ``bands``: emissivity_band10..14 (scale 0.001, applied here exactly once), ndvi (scale 0.01),
    land_water_map, num_obs. Pixels count as valid only if emissivities are finite and > 0, NDVI <=
    COMPOSITION_MAX_NDVI, the pixel is land and has enough ASTER observations.
    """
    e = [np.asarray(bands[f"emissivity_band{n}"], dtype=np.float64) * ASTER_EMISSIVITY_SCALE for n in (10, 11, 12, 13)]
    ndvi = np.asarray(bands["ndvi"], dtype=np.float64) * ASTER_NDVI_SCALE
    land = np.asarray(bands["land_water_map"]) == ASTER_LAND_CLASS
    num_obs = np.asarray(bands["num_obs"], dtype=np.float64)

    valid = (
        np.all([np.isfinite(a) & (a > 0) for a in e], axis=0)
        & np.isfinite(ndvi)
        & (ndvi <= COMPOSITION_MAX_NDVI)
        & land
        & (num_obs >= COMPOSITION_MIN_ASTER_OBS)
    )
    ratio = float(valid.mean()) if valid.size else 0.0
    out: dict[str, float | str] = {
        "mafic_index_raw": float("nan"),
        "quartz_index_raw": float("nan"),
        "composition_valid_pixel_ratio": ratio,
        "composition_observation_count_median": float(np.median(num_obs[valid])) if valid.any() else float("nan"),
        "composition_status": STATUS_INSUFFICIENT,
    }
    if ratio < COMPOSITION_MIN_VALID_RATIO:
        return out
    mi, qi = calculate_aster_indices(*(a[valid] for a in e))
    ok = np.isfinite(mi) & np.isfinite(qi)
    mi, qi = mi[ok], qi[ok]
    if mi.size == 0:
        return out
    kept = _trim(mi, COMPOSITION_TRIM_PERCENT)
    keep = (mi >= kept.min()) & (mi <= kept.max())
    out["mafic_index_raw"] = float(np.median(mi[keep]))
    out["quartz_index_raw"] = float(np.median(qi[keep]))
    out["composition_status"] = STATUS_OK
    return out


def extract_moon_composition(cf_patch: np.ndarray, nodata: float | None) -> dict[str, float | str]:
    """Median valid Diviner CF wavelength [micron] of one lunar patch window."""
    values = np.asarray(cf_patch, dtype=np.float64).ravel()
    ok = np.isfinite(values) & (values > 0)
    if nodata is not None and np.isfinite(nodata):
        ok &= values != nodata
    ratio = float(ok.mean()) if values.size else 0.0
    status = STATUS_OK if ratio >= COMPOSITION_MIN_VALID_RATIO else STATUS_MISSING
    return {
        "diviner_cf_microns": float(np.median(values[ok])) if status == STATUS_OK else float("nan"),
        "composition_valid_pixel_ratio": ratio,
        "composition_status": status,
    }


def build_composition_reference(values, dataset: str, direction: str, extra: dict | None = None) -> dict:
    """Versioned reference distribution of raw values (finite only) with the metadata needed to reproduce it."""
    arr = np.sort(np.asarray(values, dtype=np.float64))
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        raise ValueError("pusta referencja składu")
    rounded = [round(float(v), 5) for v in arr]
    return {
        "dataset": dataset,
        "n": len(rounded),
        "version": hashlib.sha256(json.dumps(rounded).encode()).hexdigest()[:12],
        "direction": direction,  # "higher_is_mafic" or "lower_is_mafic" for the raw value
        "index_formulas": INDEX_FORMULAS,
        "max_ndvi": COMPOSITION_MAX_NDVI,
        "land_class": ASTER_LAND_CLASS,
        "min_aster_observations": COMPOSITION_MIN_ASTER_OBS,
        "min_valid_pixel_ratio": COMPOSITION_MIN_VALID_RATIO,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(extra or {}),
        "sorted_values": rounded,
    }


def save_composition_reference(reference: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reference))


def load_composition_reference(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def mafic_felsic_percentile(raw_value, reference: dict) -> np.ndarray:
    """Body-relative percentile in [0, 1] (0 = more felsic, 1 = more mafic); NaN stays NaN."""
    ref = np.asarray(reference["sorted_values"], dtype=np.float64)
    v = np.asarray(raw_value, dtype=np.float64)
    pct = (np.searchsorted(ref, v, side="left") + np.searchsorted(ref, v, side="right")) / (2.0 * ref.size)
    if reference["direction"] == "lower_is_mafic":
        pct = 1.0 - pct
    return np.where(np.isfinite(v), pct, np.nan)


def composition_distance(earth_percentile: float, moon_percentile: float) -> float:
    """Absolute body-relative composition distance; NaN if either side is missing."""
    if not (np.isfinite(earth_percentile) and np.isfinite(moon_percentile)):
        return float("nan")
    return float(abs(earth_percentile - moon_percentile))
