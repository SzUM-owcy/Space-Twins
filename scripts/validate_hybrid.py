"""Sanity checks and legacy-vs-hybrid rank comparison for physical_hybrid_v1.

    PYTHONPATH=. uv run --frozen python scripts/validate_hybrid.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DATA_DIR, FEATURE_NAMES, ILLUM_EARTH_PATH, THERMAL_EARTH_PATH  # noqa: E402
from src.distance import aggregate, load_config, terrain_distance  # noqa: E402
from src.query import find_analogs  # noqa: E402


def check(name: str, ok: bool) -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {name}")


def main() -> None:
    earth = pd.read_csv(DATA_DIR / "earth_index.csv")
    moon = pd.read_csv(DATA_DIR / "moon_index.csv").set_index("region")
    cfg = load_config()
    row = earth.iloc[0]
    same = {k: float(row[k]) for k in FEATURE_NAMES}

    d, _ = terrain_distance(same, earth.iloc[[0]], cfg.terrain_scales)
    check("identical features -> distance 0", float(d.iloc[0]) == 0.0)

    shifted = {k: v + cfg.terrain_scales[k] for k, v in same.items()}
    shifted2 = {k: v + 2 * cfg.terrain_scales[k] for k, v in same.items()}
    d1 = float(terrain_distance(shifted, earth.iloc[[0]], cfg.terrain_scales)[0].iloc[0])
    d2 = float(terrain_distance(shifted2, earth.iloc[[0]], cfg.terrain_scales)[0].iloc[0])
    check("doubling the physical difference doubles the distance", abs(d2 - 2 * d1) < 1e-9 and abs(d1 - 1) < 1e-9)

    zero_w = {k: 0.0 for k in FEATURE_NAMES} | {"slope_p50": 1.0}
    moved = dict(same, relief_range=same["relief_range"] + 5000)
    dz = float(terrain_distance(moved, earth.iloc[[0]], cfg.terrain_scales, zero_w)[0].iloc[0])
    check("zero-weight features do not affect the result", dz == 0.0)

    moon_f = {k: float(moon.loc["apollo_11", k]) for k in FEATURE_NAMES}
    full = terrain_distance(moon_f, earth, cfg.terrain_scales)[0]
    subset = terrain_distance(moon_f, earth.iloc[:2000], cfg.terrain_scales)[0]
    check("adding Earth patches does not change existing distances", np.allclose(full.iloc[:2000], subset))

    comp, applied = aggregate(
        {"terrain": pd.Series([0.2, 0.2]), "illumination": pd.Series([0.1, np.nan])},
        {"terrain": 0.7, "illumination": 0.3},
    )
    check("missing component renormalises weights", abs(applied["terrain"].iloc[1] - 1.0) < 1e-12 and abs(comp.iloc[1] - 0.2) < 1e-12)

    print("\nTop-5 regions, legacy vs physical_hybrid_v1 (terrain + illumination only)")
    et, ei = pd.read_csv(THERMAL_EARTH_PATH), pd.read_csv(ILLUM_EARTH_PATH)
    ill = pd.read_csv(DATA_DIR / "illumination_moon.csv").set_index("patch_id")["solar_visibility_fraction"]
    for site in moon.index:
        mf = {k: float(moon.loc[site, k]) for k in FEATURE_NAMES}
        kw = dict(earth_illumination=ei, moon_illumination=ill.get(moon.loc[site, "patch_id"]), w_illum=0.1, earth_thermal=et)
        legacy = find_analogs(mf, earth, top_k=5, **kw)["region"].tolist()
        hybrid = find_analogs(mf, earth, top_k=5, scoring_method="physical_hybrid_v1", **kw)["region"].tolist()
        print(f"{site:20s} overlap {len(set(legacy) & set(hybrid))}/5  legacy={legacy}  hybrid={hybrid}")


if __name__ == "__main__":
    main()
