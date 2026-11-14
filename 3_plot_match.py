"""Best Earth analogue of a Moon site, as a Moon | Earth plot.

    uv run python 3_plot_match.py --site marius_hills [--rank 1] [--top-k 5]

Needs data/moon_index.csv, data/earth_index.csv and the patches (earth_npz/{region}.npz or
data/patches/earth/*.npy; data/patches/moon/*.npy).
"""
import argparse

import numpy as np
import pandas as pd

from config import DATA_DIR, FEATURE_NAMES, OUTPUT_DIR
from src.plotting import load_earth_patch, plot_comparison
from src.query import find_analogs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="marius_hills")
    p.add_argument("--rank", type=int, default=1, help="which analogue to plot")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--out", default=str(OUTPUT_DIR / "analog_comparison.png"))
    args = p.parse_args()

    moon = pd.read_csv(DATA_DIR / "moon_index.csv")
    row = moon[moon["region"] == args.site]
    if row.empty:
        raise SystemExit(f"unknown site {args.site!r}; available: {sorted(moon['region'])}")
    row = row.iloc[0]
    earth = pd.read_csv(DATA_DIR / "earth_index.csv")
    res = find_analogs(row[FEATURE_NAMES].to_dict(), earth, top_k=max(args.top_k, args.rank))
    print(res.to_string(index=False))
    best = res.iloc[args.rank - 1]

    moon_file = DATA_DIR / "patches" / "moon" / f"{row['patch_id']}.npy"
    fig = plot_comparison(
        np.load(moon_file) if moon_file.exists() else None,
        load_earth_patch(best["patch_id"]),
        f"{args.site} ({row['center_lat']:.2f}, {row['center_lon']:.2f})",
        f"{best['region']} ({best['center_lat']:.2f}, {best['center_lon']:.2f}) d={best['total_distance']:.2f}",
    )
    OUTPUT_DIR.mkdir(exist_ok=True)
    fig.savefig(args.out, dpi=130)
    print("saved", args.out)


if __name__ == "__main__":
    main()
