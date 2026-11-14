"""Generate synthetic index CSVs (CONTRACT §4) for development: python data/fake/make_fake_csv.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import RECORD_COLUMNS  # noqa: E402
from src.contracts import validate_records  # noqa: E402

HERE = Path(__file__).parent


def _features(rng: np.random.Generator, n: int) -> pd.DataFrame:
    slopes = np.sort(rng.uniform(0, 40, size=(n, 7)), axis=1)
    rms = rng.uniform(1, 500, n)
    return pd.DataFrame({
        **{f"slope_p{q:02d}": slopes[:, i] for i, q in enumerate((5, 10, 25, 50, 75, 90, 95))},
        "rms_height": rms,
        "tri_mean": rng.uniform(0.5, 60, n),
        "relief_range": rms * rng.uniform(3, 8, n),
        "hypsometric_integral": rng.uniform(0.1, 0.9, n),
        "elev_skew": rng.normal(0, 1, n),
    })


def make_earth(n_regions: int = 15, per_region: int = 8, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for r in range(n_regions):
        lat, lon = rng.uniform(-50, 55), rng.uniform(-170, 170)
        for i in range(per_region):
            rows.append((f"earth_region{r:02d}_{i:04d}", "NASADEM", f"region{r:02d}",
                         lat + rng.uniform(-0.4, 0.4), lon + rng.uniform(-0.4, 0.4)))
    ids = pd.DataFrame(rows, columns=RECORD_COLUMNS[:5])
    return pd.concat([ids, _features(rng, len(ids))], axis=1)


def make_moon(seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sites = [("moon_marius_hills", 14.0, -56.0), ("moon_apollo_12", -3.0, -23.4),
             ("moon_tycho", -43.3, -11.4)]
    ids = pd.DataFrame([(pid, "LOLA", pid.removeprefix("moon_"), la, lo) for pid, la, lo in sites],
                       columns=RECORD_COLUMNS[:5])
    return pd.concat([ids, _features(rng, len(ids))], axis=1)


if __name__ == "__main__":
    for name, df in (("earth_index_fake.csv", make_earth()), ("moon_index_fake.csv", make_moon())):
        validate_records(df)
        df.to_csv(HERE / name, index=False)
        print(name, len(df))
