"""Validation of index records (CONTRACT §4)."""
import numpy as np
import pandas as pd

from config import FEATURE_NAMES, RECORD_COLUMNS, VALID_SOURCES

_SLUG = r"[a-z0-9_]+"


def validate_records(df: pd.DataFrame) -> None:
    """Raise ValueError if ``df`` violates the CONTRACT §4 schema."""
    if list(df.columns) != RECORD_COLUMNS:
        raise ValueError(f"columns must be exactly {RECORD_COLUMNS}, got {list(df.columns)}")
    if df.empty:
        raise ValueError("no records")
    if df["patch_id"].duplicated().any():
        raise ValueError(f"duplicate patch_id: {df['patch_id'][df['patch_id'].duplicated()].tolist()[:5]}")
    bad = ~df["source"].isin(VALID_SOURCES)
    if bad.any():
        raise ValueError(f"invalid source {df['source'][bad].unique().tolist()}, allowed {VALID_SOURCES}")
    for col in ("patch_id", "region"):
        if not df[col].astype(str).str.fullmatch(_SLUG).all():
            raise ValueError(f"{col} must match {_SLUG}")
    numeric = ["center_lat", "center_lon", *FEATURE_NAMES]
    values = df[numeric].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("NaN/inf or non-numeric values in numeric columns")
    if not df["center_lon"].between(-180, 180).all():
        raise ValueError("center_lon outside -180..180")
    if not df["center_lat"].between(-90, 90).all():
        raise ValueError("center_lat outside -90..90")
