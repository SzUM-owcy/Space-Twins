"""Znajdź na Ziemi analogi miejsca z Księżyca (CONTRACT §5).

    uv run python 2_find_analogs.py --site marius_hills --top-k 5 --w-slope 0.5
    uv run python 2_find_analogs.py --lat 14.07 --lon -56.75   # dowolny punkt, żywa ekstrakcja z LOLA

Drukuje tabelę wyników i zapisuje outputs/latest_query.json.
"""

import argparse
import json
import sys

import pandas as pd

from config import DATA_DIR, OUTPUT_DIR
from src.morphometry import FEATURE_NAMES
from src.query import find_analogs, moon_features_for

EARTH_INDEX = DATA_DIR / "earth_index.csv"
MOON_INDEX = DATA_DIR / "moon_index.csv"
OUTPUT_PATH = OUTPUT_DIR / "latest_query.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--site", help="slug z data/moon_index.csv, np. marius_hills")
    src.add_argument("--lat", type=float, help="szerokość dowolnego punktu (wymaga --lon)")
    p.add_argument("--lon", type=float, help="długość dowolnego punktu, wschodnia dodatnia")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--w-slope", type=float, default=0.5, help="waga nachyleń w [0, 1] (reszta: kształt)")
    p.add_argument(
        "--max-per-region", type=int, default=1,
        help="ile łatek z jednego regionu (domyślnie 1; 0 = bez limitu)",
    )
    args = p.parse_args()
    if (args.lat is None) != (args.lon is None):
        p.error("--lat i --lon podaje się razem")
    return args


def moon_patch_record(args: argparse.Namespace) -> dict:
    """Łatka Księżyca: z indeksu (--site) albo wycięta na żywo (--lat/--lon)."""
    if args.site is not None:
        moon = pd.read_csv(MOON_INDEX).set_index("region")
        if args.site not in moon.index:
            sys.exit(f"Nieznane miejsce {args.site!r}. Dostępne: {', '.join(moon.index)}")
        row = moon.loc[args.site]
        return {
            "patch_id": row["patch_id"],
            "center_lat": float(row["center_lat"]),
            "center_lon": float(row["center_lon"]),
            "features": {name: float(row[name]) for name in FEATURE_NAMES},
        }
    return {
        "patch_id": f"moon_custom_{args.lat:.4f}_{args.lon:.4f}",
        "center_lat": args.lat,
        "center_lon": args.lon,
        "features": moon_features_for(args.lat, args.lon),
    }


def main() -> None:
    args = parse_args()
    try:
        moon = moon_patch_record(args)
        result = find_analogs(
            moon["features"],
            pd.read_csv(EARTH_INDEX),
            top_k=args.top_k,
            w_slope=args.w_slope,
            max_per_region=args.max_per_region or None,
        )
    except ValueError as err:
        sys.exit(f"Błąd: {err}")

    payload = {
        "moon": moon,
        "w_slope": args.w_slope,
        "top_k": args.top_k,
        "max_per_region": args.max_per_region or None,
        "out_of_range": result.attrs["out_of_range"],
        "results": json.loads(result.to_json(orient="records")),
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Księżyc: {moon['patch_id']} ({moon['center_lat']:.3f}, {moon['center_lon']:.3f})")
    print(result.round(3).to_string(index=False))
    if payload["out_of_range"]:
        print(f"UWAGA: cechy poza zakresem Ziemi (|z| > 3): {', '.join(payload['out_of_range'])}")
    print(f"zapisano {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
