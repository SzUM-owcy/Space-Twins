"""Shared thermal-range logic for Earth and Moon (same aggregation on both bodies)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from config import THERMAL_MIN_OBS


def extract_temperature_range(
    temperatures_k: np.ndarray,
    valid_mask: np.ndarray | None = None,
    min_obs: int = THERMAL_MIN_OBS,
) -> float:
    """P95 - P05 of the valid temperatures [K]; NaN if fewer than ``min_obs`` valid values."""
    values = np.asarray(temperatures_k, dtype=np.float64)
    ok = np.isfinite(values)
    if valid_mask is not None:
        ok &= np.asarray(valid_mask, dtype=bool)
    values = values[ok]
    if values.size < min_obs:
        return float("nan")
    p05, p95 = np.percentile(values, [5, 95])
    return float(p95 - p05)


def build_reference(raw_ranges_k, dataset: str, period: str) -> dict:
    """Versioned reference distribution: sorted finite raw ranges + a deterministic hash."""
    values = np.sort(np.asarray(raw_ranges_k, dtype=np.float64))
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("pusta referencja termiczna")
    rounded = [round(float(v), 3) for v in values]
    digest = hashlib.sha256(json.dumps(rounded).encode()).hexdigest()[:12]
    return {
        "dataset": dataset,
        "period": period,
        "n": len(rounded),
        "version": digest,
        "sorted_range_k": rounded,
    }


def save_reference(reference: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reference))


def load_reference(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def empirical_cdf(value_k, reference: dict) -> np.ndarray:
    """Percentile in [0, 1] of ``value_k`` within the reference (mid-rank for ties; NaN stays NaN)."""
    ref = np.asarray(reference["sorted_range_k"], dtype=np.float64)
    v = np.asarray(value_k, dtype=np.float64)
    left = np.searchsorted(ref, v, side="left")
    right = np.searchsorted(ref, v, side="right")
    pct = (left + right) / (2.0 * ref.size)
    return np.where(np.isfinite(v), pct, np.nan)
