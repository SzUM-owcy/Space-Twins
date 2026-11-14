"""Mafic-felsic composition side tables: Earth ASTER GED emissivity ratio, Moon Diviner Christiansen Feature.

Usage:
  uv run --frozen python 1e_build_composition.py moon                 # CF for Moon sites + 5 deg reference grid
  uv run --frozen python 1e_build_composition.py minerals             # Moon mineral fractions, raw-vs-corrected CF
  uv run --frozen python 1e_build_composition.py lithology            # Earth Macrostrat lithology (no login)
  uv run --frozen python 1e_build_composition.py earth [--regions a,b]  # raw ASTER MI/QI (needs Earthdata login or tiles)
  uv run --frozen python 1e_build_composition.py validate             # class ordering, outputs/composition_validation.*
  uv run --frozen python 1e_build_composition.py finalize [--earth-direction higher_is_mafic|lower_is_mafic]

Writes data/composition_{moon,earth}.csv and data/processed/{moon,earth}_composition_reference.json.
The CONTRACT index CSVs are untouched. ``earth`` is resumable by region.
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
import rasterio

from config import (
    COMPOSITION_CF_MAX_ABS_LAT,
    COMPOSITION_CF_RAW_PATH,
    COMPOSITION_CF_RAW_URL,
    COMPOSITION_DIR,
    COMPOSITION_EARTH_LITHOLOGY_PATH,
    COMPOSITION_MINERAL_MAPS,
    COMPOSITION_MINERAL_URL,
    COMPOSITION_MOON_MINERALS_PATH,
    COMPOSITION_MOON_RAW_COMPARISON_PATH,
    COMPOSITION_EARTH_COLUMNS,
    COMPOSITION_EARTH_PATH,
    COMPOSITION_EARTH_REFERENCE_PATH,
    COMPOSITION_GRID_STEP_DEG,
    COMPOSITION_MIN_VALID_RATIO,
    COMPOSITION_MOON_COLUMNS,
    COMPOSITION_MOON_PATH,
    COMPOSITION_MOON_REFERENCE_PATH,
    COMPOSITION_QI_FLAG_PERCENTILE,
    DATA_DIR,
    EARTH_INDEX_PATH,
    OUTPUT_DIR,
)
from src.composition import (
    STATUS_OK,
    build_composition_reference,
    composition_confidence,
    load_composition_reference,
    mafic_felsic_percentile,
    save_composition_reference,
)
from src.moon_composition import ensure_cf_map, moon_composition, moon_raster_median

log = logging.getLogger("composition")
MOON_INDEX_PATH = DATA_DIR / "moon_index.csv"
MOON_GRID_PATH = DATA_DIR / "composition_moon_grid.csv"
EARTH_DATASET = "ASTER GED AG100.003 (100 m): median Mafic Index e12/e13, NDVI<=0.2, land, >=3 observations"
MOON_DATASET = "LRO Diviner Christiansen Feature map, space-weathering corrected (Zenodo 4558194, 32 ppd)"
# Reference classes for validation; Earth classes are region slugs, Moon classes are site ids.
EARTH_CLASSES = {
    "mafic": ["craters_of_the_moon", "mauna_loa", "carrizozo", "zuni_bandera", "lava_beds", "paricutin"],
    "felsic_anorthosite": ["sittampundi", "saririaky", "kamestastin"],
    "confounder": ["white_sands", "erg_chebbi", "uyuni", "dalangtan", "namib", "lonar"],
}
MOON_CLASSES = {
    "mafic_mare": ["moon_apollo_11", "moon_apollo_12", "moon_apollo_17", "moon_mare_serenitatis", "moon_mare_imbrium", "moon_marius_hills"],
    "felsic_highlands": ["moon_apollo_16", "moon_highlands_maurolycus", "moon_highlands_hipparchus"],
}


def _read(path, columns) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=columns)


def _grid_points() -> list[tuple[float, float]]:
    """Area-uniform grid of cell centres within +-70 deg (longitude spacing widens towards the poles)."""
    step = COMPOSITION_GRID_STEP_DEG
    pts = []
    for lat in np.arange(-COMPOSITION_CF_MAX_ABS_LAT + step / 2, COMPOSITION_CF_MAX_ABS_LAT, step):
        n_lon = max(1, int(round(360.0 / step * np.cos(np.radians(lat)))))
        for lon in (np.arange(n_lon) + 0.5) * 360.0 / n_lon - 180.0:
            pts.append((float(lat), float(lon)))
    return pts


def build_moon() -> None:
    sites = pd.read_csv(MOON_INDEX_PATH)
    with rasterio.open(ensure_cf_map()) as src:
        rows = [{"patch_id": s.patch_id, **moon_composition(s.center_lat, s.center_lon, src)} for s in sites.itertuples()]
        grid = [{"lat": la, "lon": lo, **moon_composition(la, lo, src)} for la, lo in _grid_points()]
    table = pd.DataFrame(rows)
    table["composition_dataset"] = MOON_DATASET
    table.reindex(columns=COMPOSITION_MOON_COLUMNS).to_csv(COMPOSITION_MOON_PATH, index=False)
    pd.DataFrame(grid).to_csv(MOON_GRID_PATH, index=False)
    log.info("moon: %d/%d sites ok, %d reference cells", (table["composition_status"] == STATUS_OK).sum(), len(table), len(grid))


def build_moon_diagnostics() -> None:
    """Side tables: raw-vs-corrected CF comparison and Diviner mineral fractions (diagnostics only, never scored)."""
    sites = pd.read_csv(MOON_INDEX_PATH)
    cmp_ = pd.DataFrame({"patch_id": sites["patch_id"]})
    with rasterio.open(ensure_cf_map(COMPOSITION_CF_RAW_PATH, COMPOSITION_CF_RAW_URL)) as raw:
        cmp_["cf_viewing_corrected_microns"] = [moon_raster_median(s.center_lat, s.center_lon, raw) for s in sites.itertuples()]
    with rasterio.open(ensure_cf_map()) as cor:
        cmp_["cf_space_weathering_corrected_microns"] = [moon_raster_median(s.center_lat, s.center_lon, cor) for s in sites.itertuples()]
    cmp_.to_csv(COMPOSITION_MOON_RAW_COMPARISON_PATH, index=False)
    minerals = pd.DataFrame({"patch_id": sites["patch_id"]})
    for name, fname in COMPOSITION_MINERAL_MAPS.items():
        with rasterio.open(ensure_cf_map(COMPOSITION_DIR / fname, COMPOSITION_MINERAL_URL.format(name=fname))) as ds:
            minerals[f"{name}_fraction"] = [moon_raster_median(s.center_lat, s.center_lon, ds) for s in sites.itertuples()]
    minerals.to_csv(COMPOSITION_MOON_MINERALS_PATH, index=False)
    log.info("moon diagnostics written:\n%s", minerals.round(3).to_string(index=False))


def build_earth_lithology() -> None:
    """Macrostrat bedrock class per Earth patch (categorical, explanatory; no login). Resumable by patch."""
    from src.earth_lithology import lithology_table

    index = pd.read_csv(EARTH_INDEX_PATH)
    done = pd.read_csv(COMPOSITION_EARTH_LITHOLOGY_PATH) if COMPOSITION_EARTH_LITHOLOGY_PATH.exists() else pd.DataFrame()
    todo = index[~index["patch_id"].isin(done["patch_id"])] if len(done) else index
    log.info("lithology: %d patches to do, %d already done", len(todo), len(done))
    for start in range(0, len(todo), 500):
        chunk = todo.iloc[start : start + 500]
        rows = pd.DataFrame(lithology_table([(r.patch_id, r.center_lat, r.center_lon) for r in chunk.itertuples()]))
        failed = rows["lithology_mapped_samples"].eq(0) & rows["dominant_lithology"].eq("unknown")
        done = pd.concat([done, rows], ignore_index=True)
        done.to_csv(COMPOSITION_EARTH_LITHOLOGY_PATH, index=False)
        log.info("lithology: %d/%d (unmapped in chunk: %d)", min(start + 500, len(todo)), len(todo), failed.sum())


def build_earth(regions: list[str] | None) -> None:
    from src.earth_composition import AsterAccessError, region_composition

    index = pd.read_csv(EARTH_INDEX_PATH)
    table = _read(COMPOSITION_EARTH_PATH, COMPOSITION_EARTH_COLUMNS)
    done = set(index.loc[index["patch_id"].isin(table["patch_id"]), "region"])
    for region in regions or sorted(index["region"].unique()):
        if region in done and not regions:
            continue
        sub = index[index["region"] == region]
        try:
            rows = region_composition(list(zip(sub["patch_id"], sub["center_lat"], sub["center_lon"])))
        except AsterAccessError as exc:
            raise SystemExit(f"{exc}\n(done so far: {len(done)} regions; the step is resumable)")
        except Exception as exc:  # keep going; the region can be retried
            log.error("%s: failed (%s)", region, exc)
            continue
        new = pd.DataFrame(rows)
        new["composition_dataset"] = EARTH_DATASET
        table = pd.concat([table[~table["patch_id"].isin(new["patch_id"])], new], ignore_index=True)
        table.reindex(columns=COMPOSITION_EARTH_COLUMNS).to_csv(COMPOSITION_EARTH_PATH, index=False)
        ok = (new["composition_status"] == STATUS_OK).sum()
        log.info("%s: %d/%d patches ok, MI median %.4f", region, ok, len(new), new["mafic_index_raw"].median())


def moon_direction(table: pd.DataFrame) -> tuple[str, float, float]:
    """Direction of the Moon CF (mare vs highlands class medians); the expected one is higher_is_mafic."""
    by_id = table.set_index("patch_id")["diviner_cf_microns"]
    mafic = by_id.reindex(MOON_CLASSES["mafic_mare"]).median()
    felsic = by_id.reindex(MOON_CLASSES["felsic_highlands"]).median()
    return ("higher_is_mafic" if mafic > felsic else "lower_is_mafic"), float(mafic), float(felsic)


def earth_direction(table: pd.DataFrame, index: pd.DataFrame) -> tuple[str, float, float] | None:
    """Direction of the Earth MI from mafic vs felsic region medians; None if either class has no data."""
    merged = table.merge(index[["patch_id", "region"]], on="patch_id")
    ok = merged[merged["composition_status"] == STATUS_OK]
    mafic = ok.loc[ok["region"].isin(EARTH_CLASSES["mafic"]), "mafic_index_raw"].median()
    felsic = ok.loc[ok["region"].isin(EARTH_CLASSES["felsic_anorthosite"]), "mafic_index_raw"].median()
    if not (np.isfinite(mafic) and np.isfinite(felsic)):
        return None
    return ("higher_is_mafic" if mafic > felsic else "lower_is_mafic"), float(mafic), float(felsic)


def validate() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    moon = _read(COMPOSITION_MOON_PATH, COMPOSITION_MOON_COLUMNS)
    if moon.empty:
        build_moon()
        moon = pd.read_csv(COMPOSITION_MOON_PATH)
    direction, mafic, felsic = moon_direction(moon)
    rows = []
    for cls, ids in MOON_CLASSES.items():
        for pid in ids:
            v = moon.set_index("patch_id")["diviner_cf_microns"].get(pid, np.nan)
            rows.append({"body": "moon", "class": cls, "id": pid, "raw": v, "qi": np.nan, "valid_ratio": np.nan})
    log.info("moon: mare median CF %.3f vs highlands %.3f -> %s", mafic, felsic, direction)

    earth = _read(COMPOSITION_EARTH_PATH, COMPOSITION_EARTH_COLUMNS)
    index = pd.read_csv(EARTH_INDEX_PATH)
    e_dir = earth_direction(earth, index) if not earth.empty else None
    if not earth.empty:
        merged = earth.merge(index[["patch_id", "region"]], on="patch_id")
        for cls, regions in EARTH_CLASSES.items():
            for reg, g in merged[merged["region"].isin(regions)].groupby("region"):
                ok = g[g["composition_status"] == STATUS_OK]
                rows.append({
                    "body": "earth", "class": cls, "id": reg,
                    "raw": ok["mafic_index_raw"].median(), "qi": ok["quartz_index_raw"].median(),
                    "valid_ratio": g["composition_valid_pixel_ratio"].mean(),
                })
        log.info("earth direction: %s", e_dir)
    else:
        log.warning("no Earth composition table: Earth validation skipped (needs ASTER GED, see README)")

    out = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(exist_ok=True)
    out.to_csv(OUTPUT_DIR / "composition_validation.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, body, label in ((axes[0], "moon", "Diviner CF wavelength [micron]"), (axes[1], "earth", "ASTER mafic index e12/e13")):
        sub = out[out["body"] == body]
        classes = [c for c in sub["class"].unique()]
        if sub["raw"].notna().any():
            ax.boxplot([sub.loc[sub["class"] == c, "raw"].dropna() for c in classes], tick_labels=classes)
            for i, c in enumerate(classes, 1):
                vals = sub.loc[sub["class"] == c, "raw"].dropna()
                ax.scatter(np.full(len(vals), i), vals, s=14, color="k", zorder=3)
        else:
            ax.text(0.5, 0.5, "no data", ha="center", transform=ax.transAxes)
        ax.set_title(body.capitalize())
        ax.set_ylabel(label)
        ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "composition_validation.png", dpi=130)
    print(out.round(4).to_string(index=False))


def finalize(earth_dir: str | None) -> None:
    moon = pd.read_csv(COMPOSITION_MOON_PATH)
    direction, mafic, felsic = moon_direction(moon)
    if direction != "higher_is_mafic":
        raise SystemExit(f"Moon CF direction is {direction} (mare {mafic:.3f}, highlands {felsic:.3f}); check the data before finalizing")
    grid = pd.read_csv(MOON_GRID_PATH)
    ref_values = grid.loc[grid["composition_status"] == STATUS_OK, "diviner_cf_microns"]
    mref = build_composition_reference(
        ref_values, MOON_DATASET, direction, {"grid_step_deg": COMPOSITION_GRID_STEP_DEG, "lat_range": [-70, 70]}
    )
    save_composition_reference(mref, COMPOSITION_MOON_REFERENCE_PATH)
    moon["mafic_felsic_percentile"] = mafic_felsic_percentile(moon["diviner_cf_microns"], mref)
    moon["composition_confidence"] = [
        "missing" if st != STATUS_OK else composition_confidence(r) for st, r in zip(moon["composition_status"], moon["composition_valid_pixel_ratio"])
    ]
    moon["composition_reference_version"] = mref["version"]
    moon.reindex(columns=COMPOSITION_MOON_COLUMNS).to_csv(COMPOSITION_MOON_PATH, index=False)
    log.info("moon reference: n=%d version=%s", mref["n"], mref["version"])

    earth = _read(COMPOSITION_EARTH_PATH, COMPOSITION_EARTH_COLUMNS)
    if earth.empty:
        log.warning("no Earth composition table: Earth percentiles not built")
        return
    index = pd.read_csv(EARTH_INDEX_PATH)
    ok = earth["composition_status"] == STATUS_OK
    chosen = earth_dir
    if chosen is None:
        found = earth_direction(earth, index)
        if found is None:
            raise SystemExit("cannot determine the Earth direction (no mafic/felsic reference regions built); pass --earth-direction")
        chosen = found[0]
        log.info("earth direction from validation regions: %s (mafic MI %.4f vs felsic %.4f)", *found)
    eref = build_composition_reference(earth.loc[ok, "mafic_index_raw"], EARTH_DATASET, chosen)
    save_composition_reference(eref, COMPOSITION_EARTH_REFERENCE_PATH)
    earth["mafic_felsic_percentile"] = mafic_felsic_percentile(earth["mafic_index_raw"], eref)
    qi_cut = float(np.nanpercentile(earth.loc[ok, "quartz_index_raw"], COMPOSITION_QI_FLAG_PERCENTILE))
    earth["composition_confidence"] = [
        composition_confidence(r, bool(np.isfinite(q) and q >= qi_cut)) if st == STATUS_OK else "missing"
        for st, r, q in zip(earth["composition_status"], earth["composition_valid_pixel_ratio"], earth["quartz_index_raw"])
    ]
    earth["composition_reference_version"] = eref["version"]
    earth.reindex(columns=COMPOSITION_EARTH_COLUMNS).to_csv(COMPOSITION_EARTH_PATH, index=False)
    log.info("earth reference: n=%d version=%s QI p%.0f=%.4f", eref["n"], eref["version"], COMPOSITION_QI_FLAG_PERCENTILE, qi_cut)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["moon", "minerals", "lithology", "earth", "validate", "finalize"])
    parser.add_argument("--regions", default=None, help="comma-separated Earth regions (re-does them)")
    parser.add_argument("--earth-direction", choices=["higher_is_mafic", "lower_is_mafic"], default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.step == "lithology":
        build_earth_lithology()
    elif args.step == "minerals":
        build_moon_diagnostics()
    elif args.step == "moon":
        build_moon()
    elif args.step == "earth":
        build_earth(args.regions.split(",") if args.regions else None)
    elif args.step == "validate":
        validate()
    else:
        finalize(args.earth_direction)


if __name__ == "__main__":
    main()
