"""Znajdź na Ziemi analogi miejsca z Księżyca (CONTRACT §5).

    uv run python 2_find_analogs.py --site marius_hills --top-k 5 --w-slope 0.5
    uv run python 2_find_analogs.py --lat 14.07 --lon -56.75   # dowolny punkt, żywa ekstrakcja z LOLA

Drukuje tabelę wyników i zapisuje outputs/latest_query.json.
"""

import argparse
import json
import sys

import pandas as pd

from config import (
    DATA_DIR,
    COMPOSITION_EARTH_LITHOLOGY_PATH,
    COMPOSITION_EARTH_PATH,
    COMPOSITION_MOON_PATH,
    ILLUM_EARTH_PATH,
    ILLUM_MOON_PATH,
    OUTPUT_DIR,
    THERMAL_EARTH_PATH,
    THERMAL_MOON_PATH,
    THERMAL_MOON_REFERENCE_PATH,
    W_COMPOSITION_DEFAULT,
    W_ILLUM_DEFAULT,
    W_THERMAL_DEFAULT,
)
from src.morphometry import FEATURE_NAMES
from src.query import find_analogs, moon_features_for, rank_stability

EARTH_INDEX = DATA_DIR / "earth_index.csv"
MOON_INDEX = DATA_DIR / "moon_index.csv"
OUTPUT_PATH = OUTPUT_DIR / "latest_query.json"


def parse_feature_weights(parser: argparse.ArgumentParser, text: str | None) -> dict | None:
    if not text:
        return None
    try:
        return {k.strip(): float(v) for k, v in (item.split("=") for item in text.split(","))}
    except ValueError:
        parser.error("--feature-weights: oczekiwano NAME=WARTOŚĆ,NAME=WARTOŚĆ")


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
    p.add_argument(
        "--w-thermal", type=float, default=W_THERMAL_DEFAULT,
        help="waga składnika termicznego w [0, 1] (0 = tylko teren); działa, gdy są dane termiczne",
    )
    p.add_argument(
        "--w-illum", type=float, default=W_ILLUM_DEFAULT,
        help="waga składnika oświetlenia w [0, 1] (0 = wyłączony); waga terenu = 1 - w_thermal - w_illum",
    )
    p.add_argument(
        "--w-composition", type=float, default=W_COMPOSITION_DEFAULT,
        help="waga składnika składu mafic-felsic w [0, 1] (0 = wyłączony); wymaga data/composition_*.csv",
    )
    p.add_argument(
        "--feature-weights", default=None, metavar="NAME=W,...",
        help="względne ważności cech terenu, np. slope_p50=3,rms_height=2 (pominięte = 1; zastępuje --w-slope)",
    )
    p.add_argument(
        "--stability", type=int, default=0, metavar="N",
        help="N przebiegów z szumem na cechach Księżyca; dodaje kolumnę stability (ułamek przebiegów, w których łatka zostaje w top-K)",
    )
    args = p.parse_args()
    args.feature_weights = parse_feature_weights(p, args.feature_weights)
    if args.w_thermal + args.w_illum + args.w_composition > 1.0:
        p.error("--w-thermal + --w-illum + --w-composition musi być <= 1")
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


def moon_thermal(args: argparse.Namespace, moon: dict) -> dict:
    """Percentyl zakresu temperatur łatki Księżyca (z tabeli albo na żywo z Diviner GCP)."""
    info = {"surface_temperature_range_k": None, "thermal_range_percentile": None}
    if not THERMAL_MOON_REFERENCE_PATH.exists():
        return info
    if args.site is not None:
        if THERMAL_MOON_PATH.exists():
            table = pd.read_csv(THERMAL_MOON_PATH).set_index("patch_id")
            if moon["patch_id"] in table.index:
                row = table.loc[moon["patch_id"]]
                info["surface_temperature_range_k"] = float(row["surface_temperature_range_k"])
                info["thermal_range_percentile"] = float(row["thermal_range_percentile"])
        return info
    try:
        from src.moon_temperature import moon_cell_stats
        from src.thermal import empirical_cdf, load_reference

        rng = moon_cell_stats(args.lat, args.lon)["surface_temperature_range_k"]
        info["surface_temperature_range_k"] = float(rng)
        info["thermal_range_percentile"] = float(empirical_cdf(rng, load_reference(THERMAL_MOON_REFERENCE_PATH)))
    except Exception as err:  # offline or no data: fall back to terrain only
        print(f"UWAGA: brak danych termicznych Księżyca ({err})", file=sys.stderr)
    return info


def moon_illumination(args: argparse.Namespace, moon: dict) -> dict:
    """Ułamek widoczności Słońca łatki Księżyca (z tabeli albo na żywo: LOLA + SPICE)."""
    info = {"solar_visibility_fraction": None, "solar_visibility_astro": None}
    try:
        if args.site is not None:
            if ILLUM_MOON_PATH.exists():
                table = pd.read_csv(ILLUM_MOON_PATH).set_index("patch_id")
                if moon["patch_id"] in table.index:
                    row = table.loc[moon["patch_id"]]
                    info = {k: None if pd.isna(row[k]) else float(row[k]) for k in info}
            return info
        from src.illumination_live import moon_illumination_for

        res = moon_illumination_for(args.lat, args.lon)
        info["solar_visibility_fraction"] = None if res["fraction"] != res["fraction"] else float(res["fraction"])
        info["solar_visibility_astro"] = float(res["astro"])
    except Exception as err:  # no data: fall back to the other components
        print(f"UWAGA: brak danych oświetlenia Księżyca ({err})", file=sys.stderr)
    return info


def moon_composition_info_empty() -> dict:
    return {"diviner_cf_microns": None, "mafic_felsic_percentile": None, "composition_status": "not_requested"}


def moon_composition_info(args: argparse.Namespace, moon: dict) -> dict:
    """Percentyl mafic-felsic łatki Księżyca (z tabeli albo na żywo z mapy Diviner CF)."""
    info = {"diviner_cf_microns": None, "mafic_felsic_percentile": None, "composition_status": "missing"}
    try:
        if args.site is not None:
            if COMPOSITION_MOON_PATH.exists():
                table = pd.read_csv(COMPOSITION_MOON_PATH).set_index("patch_id")
                if moon["patch_id"] in table.index:
                    row = table.loc[moon["patch_id"]]
                    info = {k: (None if pd.isna(row[k]) else row[k]) for k in info}
            return info
        from src.moon_composition import moon_composition_live

        res = moon_composition_live(args.lat, args.lon)
        info = {k: (None if res[k] is None or res[k] != res[k] else res[k]) for k in info}
    except Exception as err:  # no data: the component drops out of the score
        print(f"UWAGA: brak danych składu Księżyca ({err})", file=sys.stderr)
    return info


def main() -> None:
    args = parse_args()
    try:
        moon = moon_patch_record(args)
        thermal = moon_thermal(args, moon)
        earth_thermal = pd.read_csv(THERMAL_EARTH_PATH) if THERMAL_EARTH_PATH.exists() else None
        illum = moon_illumination(args, moon)
        earth_illum = pd.read_csv(ILLUM_EARTH_PATH) if ILLUM_EARTH_PATH.exists() else None
        comp = moon_composition_info(args, moon) if args.w_composition > 0 else moon_composition_info_empty()
        earth_comp = pd.read_csv(COMPOSITION_EARTH_PATH) if COMPOSITION_EARTH_PATH.exists() else None
        earth_index = pd.read_csv(EARTH_INDEX)
        find_kwargs = dict(
            w_slope=args.w_slope,
            max_per_region=args.max_per_region or None,
            moon_thermal_percentile=thermal["thermal_range_percentile"],
            earth_thermal=earth_thermal,
            w_thermal=args.w_thermal,
            moon_illumination=illum["solar_visibility_fraction"],
            earth_illumination=earth_illum,
            w_illum=args.w_illum,
            moon_composition=comp["mafic_felsic_percentile"],
            earth_composition=earth_comp,
            w_composition=args.w_composition,
            earth_lithology=pd.read_csv(COMPOSITION_EARTH_LITHOLOGY_PATH) if COMPOSITION_EARTH_LITHOLOGY_PATH.exists() else None,
            feature_weights=args.feature_weights,
        )
        result = find_analogs(moon["features"], earth_index, top_k=args.top_k, **find_kwargs)
        if args.stability:
            stability = rank_stability(moon["features"], earth_index, result, args.stability, **find_kwargs)
            result["stability"] = result["patch_id"].map(stability)
    except ValueError as err:
        sys.exit(f"Błąd: {err}")

    payload = {
        "moon": moon,
        "w_slope": args.w_slope,
        "w_thermal": args.w_thermal,
        "moon_thermal": thermal,
        "w_illum": args.w_illum,
        "feature_weights": args.feature_weights,
        "moon_illumination": illum,
        "w_composition": args.w_composition,
        "moon_composition": comp,
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
