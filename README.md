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

**Terrain (12 features per patch)** — computed by the same function for both bodies
(`src/morphometry.py::extract_patch_features`):

- slope percentiles: `slope_p05, p10, p25, p50, p75, p90, p95`
- shape: `rms_height`, `tri_mean`, `relief_range`, `hypsometric_integral`, `elev_skew`

`log1p` is applied to `rms_height`, `tri_mean` and `relief_range`, then all features are z-scored with the
Earth index statistics. Terrain distance = `w_slope · slope RMS + (1 - w_slope) · shape RMS` of the z-score
differences (smaller = more similar). Moon features outside the Earth range (|z| > 3) are flagged.

**Thermal range** (optional, experimental): `thermal_range_percentile`, how thermally variable a patch is
relative to other patches of its own body. **Solar illumination** (optional, experimental):
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

## Data in the repository

| Item | Content |
|---|---|
| Earth index | `data/earth_index.csv`: **4269 patches, 59 regions** (51 NASADEM + 8 Copernicus DEM; 8 validation regions flagged in `data/regions.csv`; 12 exploratory regions use overlapping patches via `stride_km`) |
| Moon index | `data/moon_index.csv`: **18 sites** (Apollo, maria, highlands, craters, 4 polar) + `data/patches/moon/*.npy` |
| Earth patches | `data/patches/earth_npz/{region}.npz`, one small archive per region |
| Side tables | `data/thermal_*.csv`, `data/illumination_*.csv`, `data/processed/*_thermal_reference.json` |

Not committed (gitignored): raw DEM tiles (`data/nasadem`, `data/copdem`), LOLA rasters (`data/lola/` or
`moon/data/`; global 118 m is 8.5 GB, the polar 20 m product 1.85 GB) and SPICE kernels (`data/spice/`).

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
| **Thermal range** | MODIS 11A2 v061 (Terra + Aqua, 1 km, day + night, 2024) via Planetary Computer: per-pixel P95 − P05, median over the patch | LRO Diviner Global Cumulative Product `tbol` (0.5° cell, 96 local-time bins): P95 − P05 |
| **Illumination** | NASADEM/COPDEM terrain horizon (20 km window at 250 m) + pvlib Sun positions, hourly 2024 | LOLA horizon, same window + NASA SPICE (DE440s) Sun positions |

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
- **Illumination:** geometric Sun visibility only (no atmosphere, clouds or insolation). The 20 km window
  truncates horizons near region edges and for polar craters; polar sites use the global LOLA product. On
  Earth it is strongly rank-correlated with roughness (about −0.85 with `rms_height`), and it saturates for
  permanently shadowed Moon sites.
- Candidate regions and lunar benchmarks were used to develop the algorithm; they are not scientifically
  validated planetary analog classifications.

## Status and future work

Working end to end: Earth index (59 regions) and Moon index (18 sites) → scoring with adjustable weights →
top-K analogs → CLI, HTTP API and Streamlit.

Next: the 20 m polar LOLA product for polar illumination, validation against NASA polar illumination
products, more Earth regions, additional dimensions (mineralogy, ice/resource indicators) and Mars as a
second target body.
