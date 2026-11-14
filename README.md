# 🌕 moon-analog-lite

A lightweight, explainable **Earth–Moon analog discovery tool** for the **2026 NASA Space Apps Challenge**
([Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars](https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/?tab=resources)).

**Given a location on the Moon, which places on Earth are analogous to it, in which respects, and where does the analogy break down?**

The challenge accepts that an Earth analog need not match the Moon in every respect. It asks which
dimensions (terrain, temperature, illumination, ...) are analogous and where they are not. So the tool does
not produce one opaque "Moon-likeness" number. It scores each dimension separately and combines them with
user-adjustable weights. A result can read: *strong terrain analog, moderate thermal analog, poor
illumination analog*.

The terrain comparison is the core. Both bodies are reduced to the same representation:

```text
 Earth DEM (NASADEM / Copernicus)      Moon DEM (LRO LOLA 118 m)
              │                                   │
        10 km patch, 85 x 85 grid          10 km patch, 85 x 85 grid
              │                                   │
        12 terrain features                12 terrain features
              └──────────────┬────────────────────┘
                     similarity engine  ◄── optional: thermal range, solar illumination
                             │
                  ranked Earth analogs ──► CLI · HTTP API · Streamlit
```

The ranking measures similarity of selected, measurable features. It is **not** a statement about
landing-site suitability, mission safety or geological equivalence, and Earth cannot reproduce lunar vacuum,
gravity, radiation, day length or the exact thermal regime.

- Event: https://www.spaceappschallenge.org/2026/local-events/poznan
- Data resources: https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/?tab=resources
- Judging criteria: https://www.spaceappschallenge.org/resources/judging-awards-guide/

---

## Features

1. **Terrain (12 features per patch)** — computed by the same function for both bodies
(`src/morphometry.py::extract_patch_features`):

- slope percentiles: `slope_p05, p10, p25, p50, p75, p90, p95`
- shape: `rms_height`, `tri_mean`, `relief_range`, `hypsometric_integral`, `elev_skew`

`log1p` is applied to `rms_height`, `tri_mean` and `relief_range`, then all features are z-scored with the
Earth index statistics. Terrain distance = `w_slope · slope RMS + (1 - w_slope) · shape RMS` of the z-score
differences (smaller = more similar). Moon features outside the Earth range (|z| > 3) are flagged.

2. **Thermal range** (optional, experimental): `thermal_range_percentile`, how thermally variable a patch is
relative to other patches of its own body.

3. **Solar illumination** (optional, experimental):
`solar_visibility_fraction`, the share of time the Sun is above the terrain horizon. Both live in side
tables keyed by `patch_id`, so the strict 17-column index CSVs ([`docs/CONTRACT.md`](docs/CONTRACT.md)) are
unchanged and terrain-only queries keep working.

### Why these dimensions

A DEM says how a place *looks*, not what conditions it exposes equipment to. Thermal range and illumination
are two operationally relevant dimensions that can be compared consistently for both bodies with openly
available data. They are not the only ones: vacuum, regolith and dust, radiation and gravity can matter just
as much, and are **not** covered here.

- **Thermal range.** The Moon has almost no atmosphere to buffer temperature, so surface temperatures swing
  strongly over the lunar day, and permanently shadowed regions stay extremely cold. Large temperature
  variation drives thermal stress on materials and affects batteries, electronics and mechanisms. Earth
  locations with a large temperature range (hot or polar deserts, high plateaus) can be useful for testing
  *selected aspects* of equipment behaviour under thermal cycling. The feature does not claim that Earth
  reproduces lunar absolute temperatures.
- **Solar illumination.** Sunlight affects power availability, heating and the length of operating windows.
  Near the lunar poles, crater interiors can be permanently shadowed while nearby elevated terrain is lit for
  a much larger share of the time (NASA's LOLA polar products map average illumination and permanent shadow).
  Terrain that looks the same can therefore have very different light conditions. The feature measures how
  much terrain shading limits the Sun, so the ranking can prefer Earth sites with comparable shading.

Because each dimension is scored separately, the tool can show *what* is analogous and *where* the analogy
fails, and a user can weight the dimensions for a given test question (see [Adjusting weights](#adjusting-weights)).
The weights are experiment-dependent settings, not a universal definition of "Moon-like".

Both features are relative or geometric: thermal values are percentiles within each body, and illumination is
geometric Sun visibility without an atmosphere or clouds. They add explainable dimensions to the analog score
and are not proof of environmental equivalence. See the limitations below.

## Datasets

| Feature | Body | Dataset | Used for |
|---|---|---|---|
| **Terrain** | Earth | [NASADEM](https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001) (SRTM-derived, 1″ ≈ 30 m, surface model incl. canopy) for 51 regions; [Copernicus DEM GLO-30](https://planetarycomputer.microsoft.com/dataset/cop-dem-glo-30) (30 m) for 8 regions. Tiles come from the Planetary Computer and were cross-checked in `docs/dem_crosscheck.md` | Elevation → 10 km patches → 12 terrain features |
| | Moon | [LRO LOLA global DEM, 118 m/px](https://astrogeology.usgs.gov/search/map/moon_lro_lola_dem_118m) (USGS Astrogeology, simple cylindrical, mostly interpolated between altimeter tracks); optional 20 m south-polar product (`ldem_80s_20m`, [PDS Geosciences](https://pds-geosciences.wustl.edu/missions/lro/lola.htm)) | Elevation → 10 km patches → 12 terrain features |
| **Thermal range** | Earth | [MODIS MOD11A2/MYD11A2 v061](https://lpdaac.usgs.gov/products/mod11a2v061/) land surface temperature (Terra + Aqua, 1 km, 8-day composites, day and night layers + QA flags), read as COGs from the [Planetary Computer](https://planetarycomputer.microsoft.com/dataset/modis-11A2-061); year 2024 | How far the temperature swings between a hot and a cold reading, per pixel |
| | Moon | [LRO Diviner](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/) Global Cumulative Product, `tbol` bolometric temperature (0.5° cells, 96 local-time bins, 2009–2015 average) | The same hot-vs-cold swing across the 96 times of the lunar day |
| **Solar illumination** | Earth | NASADEM / Copernicus DEM (terrain horizon, as above) + [pvlib](https://pvlib-python.readthedocs.io/) solar position (NREL SPA), hourly 2024 | Share of time the Sun is above the terrain horizon |
| | Moon | LOLA 118 m DEM (terrain horizon, 40 km window) + [NASA/JPL SPICE](https://naif.jpl.nasa.gov/naif/) ephemerides (`de440s.bsp`, `pck00011.tpc`, `naif0012.tls`), same hourly grid | Share of time the Sun is above the terrain horizon |

Used for validation only (`data/validation/`, see [Illumination validation](#illumination-validation)):
[LOLA average solar visibility map `AVGVISIB_65S_240M_201608`](https://pgda.gsfc.nasa.gov/products/69) (240 m, south of 65°S) and
the [80 m south-polar LOLA DEM `LDEM_80S_80MPP_ADJ`](https://pgda.gsfc.nasa.gov/products/90). The 20 m polar DEM is not used. Raw data are not committed; see [Data in the repository](#data-in-the-repository).

## Data in the repository

| Item | Content |
|---|---|
| Earth index | `data/earth_index.csv`: **4269 patches, 59 regions** (51 NASADEM + 8 Copernicus DEM; 8 validation regions flagged in `data/regions.csv`; 12 exploratory regions use overlapping patches via `stride_km`) |
| Moon index | `data/moon_index.csv`: **18 sites** (Apollo, maria, highlands, craters, 4 polar) + `data/patches/moon/*.npy` |
| Earth patches | `data/patches/earth_npz/{region}.npz`, one small archive per region |
| Side tables | `data/thermal_*.csv`, `data/illumination_*.csv`, `data/processed/*_thermal_reference.json` |

Not committed (gitignored): raw DEM tiles (`data/nasadem`, `data/copdem`), LOLA rasters (`data/lola/` or
`moon/data/`; global 118 m is 8.5 GB; the 20 m south-polar DEM is only needed for live terrain queries below 80°S), SPICE kernels (`data/spice/`) and
the polar validation rasters (`data/validation/`, ~230 MB).

---

## Setup

Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). Use `--frozen` (plain `uv run` may fail to re-resolve on
some platforms). Behind a proxy or on WSL set `REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt`.

```bash
uv sync --frozen --default-index https://pypi.org/simple
```

### Run a query (works from the committed data)

```bash
uv run --frozen python 2_find_analogs.py --site marius_hills --top-k 5
uv run --frozen python 3_plot_match.py --site marius_hills            # -> outputs/analog_comparison.png
uv run --frozen python 2_find_analogs.py --lat 14.07 --lon -56.75     # any point; needs the LOLA raster
```

Results are printed and saved to `outputs/latest_query.json`.

### Streamlit app and HTTP API

```bash
uv run --frozen streamlit run app.py
uv run --frozen uvicorn api.main:app --reload --port 8000     # docs at http://localhost:8000/docs
```

The backend ↔ frontend contract is [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md), generated into
[`api/openapi.json`](api/openapi.json) (regenerate with `uv run --frozen python -m api.export_openapi`).

### Tests

```bash
uv run --frozen python -m pytest
```

---

## Adjusting weights

Every comparison component is adjustable (CLI flags and the API request fields of `POST /api/v1/analogs`):

| Control | Meaning |
|---|---|
| `--w-slope` / `w_slope` | slope vs shape split of the terrain distance (default 0.5) |
| `--feature-weights slope_p50=3,rms_height=2,elev_skew=0` / `feature_weights` | relative importance of each of the 12 terrain features (omitted = 1; replaces `w_slope`; terrain distance becomes the weighted RMS) |
| `--w-thermal` / `w_thermal` | share of the thermal component (CLI default 0.2, API default 0) |
| `--w-illum` / `w_illum` | share of the illumination component (CLI default 0.1, API default 0) |

Terrain share = `1 - w_thermal - w_illum`. A component with missing data for the query or a patch drops out
of the sum (`*_status = "missing"`), it is never treated as zero. With both weights 0 the result is the
pure terrain ranking. All components are shown separately (`terrain_distance`, `thermal_distance`,
`illumination_distance`) so a ranking stays explainable. The default weights are experimental, not validated
scientific constants.

---

## Rebuilding the data

Only needed to extend or regenerate the indexes.

```bash
# Earth index (tiles are downloaded and cached)
uv run --frozen python 1_build_index.py --dem nasadem --workers 3
uv run --frozen python 1_build_index.py --dem copdem
uv run --frozen python 1_build_index.py --npz                  # pack new regions into data/patches/earth_npz/

# Moon index (needs the LOLA rasters)
uv run --frozen python 1b_build_moon_index.py

# Thermal side tables
uv run --frozen python 1c_build_thermal.py earth               # resumable per region
uv run --frozen python 1c_build_thermal.py moon
uv run --frozen python 1c_build_thermal.py finalize            # versioned references + percentiles

# Illumination side tables
uv run --frozen python 1d_build_illumination.py earth          # ~1 min, resumable per region
uv run --frozen python 1d_build_illumination.py moon
```

### How the optional features are computed

| | Earth | Moon |
|---|---|---|
| **Thermal range** | MODIS 11A2 v061 (Terra + Aqua, 1 km, day + night, 2024) via Planetary Computer: per-pixel temperature swing (see below), median over the patch | LRO Diviner Global Cumulative Product `tbol` (0.5° cell, 96 local-time bins): temperature swing (see below) |
| **Illumination** | NASADEM/COPDEM terrain horizon (20 km window at 250 m) + pvlib Sun positions, hourly 2024 | LOLA horizon (40 km window) + NASA SPICE (DE440s) Sun positions, one Sun track per observer point |

**Temperature swing ("P95 − P05").** For each place we collect all valid temperature readings (day and night
over the year on Earth, the 96 times of the lunar day on the Moon), sort them, and take the value that is
higher than 95 % of the readings (the "typical hot" value) minus the value that is higher than only 5 % of
them (the "typical cold" value). Example: typical hot 45 °C, typical cold 5 °C → swing 40 K. Using the 95th
and 5th percentiles instead of the single hottest and coldest reading keeps one bad pixel or outlier from
distorting the result.

Thermal ranges are converted to a percentile within their own body (Earth: all valid indexed patches; Moon:
1654 area-uniform cells on a 5° grid); the distance is `sqrt(6) · |Δ percentile|`. Illumination distance is
`|Δ fraction| / std(Earth)`, capped at 3. Horizons are ray-marched (72 azimuths, curvature included) from a
5 × 5 grid of points in the patch centre.

---

## Repository layout

| Path | Purpose |
|---|---|
| `config.py` | Geometry, nodata/scale, feature names, data paths, thermal/illumination constants |
| `0_download_earth.py`, `1_build_index.py`, `1b_build_moon_index.py` | DEM download and Earth/Moon index builders |
| `1c_build_thermal.py`, `1d_build_illumination.py` | Side-table builders |
| `2_find_analogs.py`, `3_plot_match.py` | CLI query and comparison plot |
| `4_validate_illumination.py` | Polar illumination validation against NASA's LOLA visibility map |
| `app.py` | Streamlit app |
| `api/` | FastAPI backend (`main.py`, `service.py`, `schemas.py`, OpenAPI + examples) |
| `src/raster_io.py`, `src/morphometry.py` | Shared patch extraction and the 12 terrain features |
| `src/scoring.py`, `src/query.py` | Scaling, distances, `find_analogs`, live Moon extraction |
| `src/thermal.py`, `src/earth_temperature.py`, `src/moon_temperature.py` | Thermal feature |
| `src/illumination.py`, `src/earth_solar.py`, `src/moon_solar.py`, `src/illumination_live.py` | Illumination feature |
| `src/contracts.py`, `src/plotting.py` | CSV schema validation, plots |
| `dem_crosscheck.py` | NASADEM vs Copernicus DEM comparison (`docs/dem_crosscheck.md`) |
| `tests/` | Raster extraction, contract and synthetic end-to-end tests |
| `docs/` | `CONTRACT.md` (source of truth), `API_CONTRACT.md`, per-person plans |

---

## Illumination validation

`4_validate_illumination.py` compares the Moon illumination method with NASA's LOLA average solar-visibility
map (`AVGVISIB_65S_240M_201608`, 18.6-year cycle) at the four polar sites (441 points each, 1 km spacing,
absolute visibility with the solar disc and the Sun track of each point). Exact equality is not expected: the
official map uses another DEM and period. Download both rasters first (about 230 MB):

```bash
mkdir -p data/validation/illumination data/validation/lola_polar
B=https://imbrium.mit.edu/EXTRAS/ILLUMINATION/JP2
for f in AVGVISIB_65S_240M_201608.JP2 AVGVISIB_65S_240M_201608_JP2.LBL AVGVISIB_65S_240M_201608_AUX.XML; do
  curl -L -o data/validation/illumination/$f $B/$f; done
curl -L -o data/validation/lola_polar/LDEM_80S_80MPP_ADJ.TIF https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF
uv run --frozen python 4_validate_illumination.py --horizon-km 40
```

| Horizon window | Spearman vs official (all points) | Shadow classification agreement |
|---|---|---|
| ±20 km | 0.85 | 77 % |
| ±40 km | 0.97 | 98 % |

- A 20 km window misses crater walls (Haworth came out 37 % lit instead of fully shadowed), so the Moon
  uses **40 km**. 60 km changed little.
- Shackleton 0.98, de Gerlache 0.98 (rank correlation); crater floors are 0 in both. The 118 m global DEM gives
  the same result as the 80 m polar DEM at this scale.
- Lowest vs highest point per site: ridge > floor in both products for 3 of 4 sites (Haworth is 0 in both).
  Malapert: floor 0.36 vs 0.35, ridge 0.62 vs 0.73 (computed vs official); correlation inside Malapert is low
  (0.4-0.5) because its visibility varies little (0.35-0.7).
- Earth illumination is not validated against an independent product.

---

## Scientific scope and limitations

- Only elevation-derived morphometry is the core comparison; thermal and illumination are experimental
  add-ons. Composition, regolith, gravity, vacuum and radiation are **not** compared.
- Earth analogs come from a hand-picked set of regions, not global coverage; some regions contain mixed
  terrain (coastal or ice-adjacent patches). The scaler and the |z| > 3 flag depend on this selection, and
  patches within a region are strongly correlated.
- LOLA 118 m is largely interpolated between altimeter tracks, so Moon slopes and TRI are slightly smoothed
  compared with Earth averaged from real 30 m data; results may favour flat analogs. NASADEM is a surface
  model (includes canopy), hence the desert/volcanic selection.
- **Thermal:** a relative percentile, not absolute equivalence. Earth values mix seasonal and diurnal
  variation at fixed overpass times and include an atmosphere; Moon values cover the full diurnal cycle in
  vacuum. Polar-night or cloudy patches are `missing`; polar Moon sites match low-range Earth patches.
- **Illumination:** geometric Sun visibility only (no atmosphere, clouds or insolation). On Earth the 20 km
  window (limited by the regional DEM mosaics) truncates horizons near region edges; the Moon uses 40 km, which
  the polar validation showed is needed for large craters. Polar sites use the 118 m global LOLA product, which
  matched the 80 m polar DEM in validation. On Earth
  it is strongly rank-correlated with roughness (about −0.85 with `rms_height`), and it saturates for
  permanently shadowed Moon sites.
- Candidate regions and lunar benchmarks were used to develop the algorithm; they are not scientifically
  validated planetary analog classifications.

## Status and future work

Working end to end: Earth index (59 regions) and Moon index (18 sites) → scoring with adjustable weights →
top-K analogs → CLI and HTTP API. The Streamlit app (`app.py`) currently runs terrain-only scoring and has no
controls for the thermal, illumination or per-feature weights yet.

Next: validate thermal range against an independent source, a patch-scale (< 0.5°) Moon temperature source,
more Earth regions, additional dimensions (mineralogy, ice/resource indicators) and Mars as a
second target body.
