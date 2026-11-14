"""Practicality scoring framework: how hard/expensive is a simulation at an Earth patch.

Independent of the scientific analog score. Group A (mitigable) inputs become 0-100 scores
(higher = easier/cheaper); Group B (intrinsic) inputs are flags and penalties. Missing is never zero:
profile scores are weight-renormalised over the available dimensions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    PRACTICALITY_BAND_SCORES,
    PRACTICALITY_BARE_FULL_FRACTION,
    PRACTICALITY_CLASS_EDGES,
    PRACTICALITY_COLUMNS,
    PRACTICALITY_FLAG_COLUMNS,
    PRACTICALITY_POPULATION_BANDS,
    PRACTICALITY_SCORE_WEIGHTS,
    PRACTICALITY_THRESHOLDS,
    PRACTICALITY_VERSION,
)

FLAG_STATUSES = ("ok", "warning", "manual_review", "excluded", "missing")
DIMENSIONS = ("access", "emergency", "buildability", "infrastructure", "population")
EXCLUDED_LABEL = "EXCLUDED / MANUAL REVIEW"


def band_score(value: float, key: str) -> float:
    """Map a cost driver to a 0-100 score using the configured ascending thresholds."""
    if value is None or not np.isfinite(value):
        return np.nan
    for threshold, score in zip(PRACTICALITY_THRESHOLDS[key], PRACTICALITY_BAND_SCORES):
        if value <= threshold:
            return score
    return PRACTICALITY_BAND_SCORES[-1]


def bare_score(fraction: float) -> float:
    """Bare/sparse ground needs less clearing; full score at the configured fraction."""
    if fraction is None or not np.isfinite(fraction):
        return np.nan
    return float(100.0 * min(1.0, fraction / PRACTICALITY_BARE_FULL_FRACTION))


def mean_available(parts: list[float]) -> float:
    vals = [v for v in parts if np.isfinite(v)]
    return float(np.mean(vals)) if vals else np.nan


def cost_class(score: float) -> str:
    if not np.isfinite(score):
        return "missing"
    low, medium, high = PRACTICALITY_CLASS_EDGES
    if score >= low:
        return "LOW"
    if score >= medium:
        return "MEDIUM"
    if score >= high:
        return "HIGH"
    return "VERY HIGH"


def population_outputs(population_25km: float) -> tuple[float, float, float]:
    """Return (isolation_logistics_penalty, population_impact_penalty, population_score); the two penalties stay separate."""
    if population_25km is None or not np.isfinite(population_25km):
        return np.nan, np.nan, np.nan
    for upper, isolation, impact in PRACTICALITY_POPULATION_BANDS:
        if population_25km < upper:
            return isolation, impact, float(np.clip(100.0 - isolation - impact, 0.0, 100.0))
    return np.nan, np.nan, np.nan


def weighted_available(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted mean over the available dimensions only."""
    avail = {k: v for k, v in scores.items() if np.isfinite(v)}
    total = sum(weights[k] for k in avail)
    if total <= 0:
        return np.nan
    return float(sum(weights[k] * v for k, v in avail.items()) / total)


def completeness_confidence(completeness: float) -> str:
    if completeness >= 0.8:
        return "high"
    if completeness >= 0.6:
        return "medium"
    if completeness > 0:
        return "low"
    return "missing"


def empty_table(patch_ids) -> pd.DataFrame:
    df = pd.DataFrame({"patch_id": list(patch_ids)})
    for col in PRACTICALITY_COLUMNS[1:]:
        df[col] = "missing" if col in PRACTICALITY_FLAG_COLUMNS or col == "grid_source" else np.nan
    df["hard_excluded"] = False
    df["exclusion_reasons"] = ""
    return df[PRACTICALITY_COLUMNS]


def score_table(df: pd.DataFrame) -> pd.DataFrame:
    """Derive dimension scores, field/facility profile scores, classes, exclusions and completeness from raw columns."""
    df = df.copy()
    for col in PRACTICALITY_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    for col in PRACTICALITY_FLAG_COLUMNS + ["grid_source"]:
        df[col] = df[col].where(df[col].notna(), "missing")

    def apply(row_fn, *cols):
        return [row_fn(*vals) for vals in zip(*(df[c] for c in cols))]

    df["access_score"] = apply(
        lambda c, a, r: mean_available([band_score(c, "city_travel_minutes"), band_score(a, "airport_travel_minutes"), band_score(r, "major_road_distance_km")]),
        "city_travel_minutes", "airport_travel_minutes", "major_road_distance_km",
    )
    df["buildability_score"] = apply(
        lambda s, r, b: mean_available([band_score(s, "facility_core_slope_p90"), band_score(r, "facility_core_relief_m"), bare_score(b)]),
        "facility_core_slope_p90", "facility_core_relief_m", "bare_ground_fraction",
    )
    df["emergency_support_score"] = apply(lambda h: band_score(h, "hospital_travel_minutes"), "hospital_travel_minutes")
    df["infrastructure_score"] = apply(lambda g: band_score(g, "grid_distance_km"), "grid_distance_km")

    pop = np.array(apply(population_outputs, "population_25km"), dtype=float).reshape(len(df), 3)
    df["isolation_logistics_penalty"], df["population_impact_penalty"], df["population_score"] = pop.T

    dim_cols = {
        "access": "access_score", "emergency": "emergency_support_score", "buildability": "buildability_score",
        "infrastructure": "infrastructure_score", "population": "population_score",
    }
    for profile, out in (("field", "field_campaign_score"), ("facility", "facility_score")):
        weights = PRACTICALITY_SCORE_WEIGHTS[profile]
        df[out] = [
            weighted_available({d: row[c] for d, c in dim_cols.items()}, weights)
            for _, row in df.iterrows()
        ]

    df["practicality_completeness"] = df[list(dim_cols.values())].notna().sum(axis=1) / len(dim_cols)
    df["practicality_confidence"] = df["practicality_completeness"].map(completeness_confidence)

    excluded = df[PRACTICALITY_FLAG_COLUMNS].eq("excluded")
    df["hard_excluded"] = excluded.any(axis=1)
    df["exclusion_reasons"] = excluded.apply(lambda r: ";".join(c for c in PRACTICALITY_FLAG_COLUMNS if r[c]), axis=1)

    for score_col, class_col in (("field_campaign_score", "field_cost_class"), ("facility_score", "facility_cost_class")):
        classes = df[score_col].map(cost_class)
        df[class_col] = classes.where(~df["hard_excluded"], EXCLUDED_LABEL)
    df["practicality_version"] = PRACTICALITY_VERSION
    return df[PRACTICALITY_COLUMNS]


PRACTICALITY_FIELDS = (
    "access_score", "buildability_score", "emergency_support_score", "infrastructure_score", "population_score",
    "isolation_logistics_penalty", "population_impact_penalty", "population_25km", "grid_source",
    "field_campaign_score", "field_cost_class", "facility_score", "facility_cost_class",
    "practicality_completeness", "practicality_confidence",
)


def pareto_optimal(distance: np.ndarray, score: np.ndarray) -> np.ndarray:
    """True where no other candidate has a lower-or-equal analog distance AND a higher-or-equal score (one strictly)."""
    distance, score = np.asarray(distance, float), np.asarray(score, float)
    out = np.zeros(len(distance), dtype=bool)
    for i in range(len(distance)):
        if not (np.isfinite(distance[i]) and np.isfinite(score[i])):
            continue
        better = (distance <= distance[i]) & (score >= score[i]) & ((distance < distance[i]) | (score > score[i]))
        out[i] = not better.any()
    return out


def _clean(value):
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def practicality_blocks(table: pd.DataFrame, patch_ids, analog_distance) -> dict[str, dict]:
    """Per patch: separate ``practicality`` and ``constraints`` blocks plus Pareto flags among the given candidates.

    The scientific distance is only used for the Pareto flags; it is never altered.
    """
    rows = table.set_index("patch_id").reindex(list(patch_ids))
    p_field = pareto_optimal(analog_distance, rows["field_campaign_score"].to_numpy())
    p_fac = pareto_optimal(analog_distance, rows["facility_score"].to_numpy())
    blocks = {}
    for i, (pid, row) in enumerate(rows.iterrows()):
        if row.isna().all():
            continue
        practicality = {k: _clean(row[k]) for k in PRACTICALITY_FIELDS}
        practicality["pareto_field"] = bool(p_field[i])
        practicality["pareto_facility"] = bool(p_fac[i])
        constraints = {k: row[k] if isinstance(row[k], str) else "missing" for k in PRACTICALITY_FLAG_COLUMNS}
        constraints["hard_excluded"] = bool(row["hard_excluded"]) if pd.notna(row["hard_excluded"]) else False
        constraints["exclusion_reasons"] = [r for r in str(row["exclusion_reasons"]).split(";") if r and r != "nan"]
        blocks[pid] = {"practicality": practicality, "constraints": constraints}
    return blocks
