"""Freeze the terrain distance scales into distance_config/distance_scales.yaml.

    uv run --frozen python scripts/calibrate_distance_scales.py            # fills null scales only
    uv run --frozen python scripts/calibrate_distance_scales.py --force    # recalibrate (bump the version!)

scale = max(1.4826 * MAD(Earth index), min_scale). Scales that are already set are left untouched, so
historical distances stay reproducible when Earth patches are added.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DATA_DIR  # noqa: E402

PATH = ROOT / "distance_config" / "distance_scales.yaml"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true", help="overwrite scales that are already set")
    args = p.parse_args()

    earth = pd.read_csv(DATA_DIR / "earth_index.csv")
    text = PATH.read_text(encoding="utf-8")
    terrain = yaml.safe_load(text)["terrain"]
    for name, spec in terrain.items():
        if spec["scale"] is not None and not args.force:
            continue
        x = earth[name].to_numpy(dtype=float)
        x = x[np.isfinite(x)]
        scale = max(1.4826 * float(np.median(np.abs(x - np.median(x)))), float(spec["min_scale"]))
        scale = float(f"{scale:.4g}")
        pattern = rf"(  {name}: \{{scale: )[^,]+(, min_scale: [^,]+, unit: [^,]+, source: )[^}}]+"
        text, n = re.subn(pattern, rf"\g<1>{scale}\g<2>mad_earth_index_{len(earth)}", text)
        assert n == 1, name
        print(f"{name:22s} scale={scale}")
    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
