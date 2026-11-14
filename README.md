# 🌕 moon\-analog\-lite

A lightweight Earth–Moon terrain comparison tool for the **2026 NASA Space Apps Challenge**.

The project explores a simple question:

**Given a location on the Moon, which locations on Earth have the most similar terrain characteristics?**

moon\-analog\-lite compares elevation\-derived terrain characteristics from two datasets:

- **Earth:** NASADEM elevation data --> https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001
- **Moon:** LRO/LOLA lunar topography data --> https://astrogeology.usgs.gov/search/map/moon_lro_lola_dem_118m

The first version deliberately focuses **only on terrain morphology**. The goal is to build a small, understandable end\-to\-end prototype before introducing additional dimensions such as temperature, geology, illumination, or Mars data.

---


Event website: https://www.spaceappschallenge.org/2026/local-events/poznan

Topic and useful datasets: https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/?tab=resources

Judging criteria: https://www.spaceappschallenge.org/resources/judging-awards-guide/



---

## 🎯 Project Objective

The application will:

1. Load a selected lunar terrain area.
2. Extract a **10 km × 10 km** terrain patch.
3. Convert the patch to a common **85 × 85** analysis grid.
4. Calculate terrain characteristics.
5. Perform the same calculation for Earth terrain patches.
6. Compare lunar and Earth feature vectors.
7. Rank the most similar Earth locations.
8. Present the results in a simple Streamlit application.

The result is an **explainable terrain similarity ranking**, not a prediction of whether a location is suitable for a real lunar mission.

---

## Setup with `uv`

This project uses **Python 3.12+** and `uv`.

### Create the environment

```bash
uv venv --python 3.12
```

### Install dependencies

```bash
uv add numpy rasterio \
  --default-index https://pypi.org/simple
```

Install development dependencies:

```bash
uv add --dev pytest \
  --default-index https://pypi.org/simple
```

### Install dependencies after cloning

```bash
uv sync \
  --default-index https://pypi.org/simple
```

### Run Python

```bash
uv run \
  --default-index https://pypi.org/simple \
  python src/prepare_earth_data.py
```

### Run tests

```bash
uv run \
  --default-index https://pypi.org/simple \
  pytest
```

Dependencies are stored in `pyproject.toml` and locked in `uv.lock`.

### Run the HTTP API (backend for the new frontend)

```bash
uv run uvicorn api.main:app --reload --port 8000
```

Interactive docs at `http://localhost:8000/docs`. The backend ↔ frontend contract is described in
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) and generated into [`api/openapi.json`](api/openapi.json).
After changing `api/schemas.py` or the routes, run `uv run python -m api.export_openapi`.

---------

# 🛰️ Initial Datasets

The MVP intentionally uses only **two datasets**.

## Earth — NASADEM

NASADEM provides elevation data for Earth's land surface.

For this project:

NASADEM

   ↓

Earth DEM

   ↓

10 km × 10 km patches

   ↓

Common 85 × 85 grid

   ↓

Terrain features

   ↓

earth\_index.csv

Dataset discovery and access:

[NASA Earthdata Search](https://search.earthdata.nasa.gov/?utm_source=%27chatgpt.com%27)

---

## Moon — LRO / LOLA

The Lunar Orbiter Laser Altimeter (LOLA), part of NASA's Lunar Reconnaissance Orbiter mission, provides lunar topographic measurements.

For this project:

LOLA

 ↓

Moon DEM

 ↓

10 km × 10 km patch

 ↓

Common 85 × 85 grid

 ↓

Terrain features

 ↓

Moon feature vector

Resources:

[NASA Planetary Data System](https://pds.nasa.gov/?utm_source=%27chatgpt.com%27)

[NASA LRO Data Archive](https://pds-geosciences.wustl.edu/missions/lro/?utm_source=%27chatgpt.com%27)

---

# 🧠 Core Idea

Both Earth and Moon data are transformed into the **same representation**.

                 EARTH                      MOON

                NASADEM                    LOLA

                   │                         │

                   ▼                         ▼

                  DEM                       DEM

                   │                         │

                   ▼                         ▼

             10 km patch                10 km patch

                   │                         │

                   ▼                         ▼

              85 × 85                    85 × 85

                   │                         │

                   ▼                         ▼

            Terrain features          Terrain features

                   │                         │

                   └──────────┬──────────────┘

                              │

                              ▼

                     Similarity Engine

                              │

                              ▼

                      Ranked Earth Sites

                              │

                              ▼

                         Streamlit

This shared representation is the main contract between the Earth and Moon pipelines.

---

# 📐 Terrain Features

Each terrain patch is converted into the same **12\-feature vector**.

## Slope distribution

slope\_p05

slope\_p10

slope\_p25

slope\_p50

slope\_p75

slope\_p90

slope\_p95

These describe how steep the terrain is across the patch.

## Terrain shape

rms\_height

tri\_mean

relief\_range

hypsometric\_integral

elev\_skew

These describe properties such as terrain roughness, elevation variation, and elevation distribution.

Both pipelines use the same function:

extract\_patch\_features(

    patch: np.ndarray,

    pixel\_size\_m: float,

) \-> dict

---

# 👥 Parallel Development

The initial work is divided by **dataset**, allowing two people to develop independently.

## 👤 Person A — Earth Pipeline

Responsible for:

NASA Earthdata

      ↓

NASADEM

      ↓

Earth DEM processing

      ↓

10 × 10 km patches

      ↓

85 × 85 common grid

      ↓

12 terrain features

      ↓

earth\_index.csv

### Initial tasks

- [ ] Download one small NASADEM area.
- [ ] Load the DEM with Rasterio.
- [ ] Convert the selected area to the common metric grid.
- [ ] Extract one 10 km × 10 km patch.
- [ ] Calculate the 12 terrain features.
- [ ] Save the results to CSV.
- [ ] Expand from one patch to multiple Earth patches.
- [ ] Add tests for Earth preprocessing.

Start with **one Earth region**.

Do not attempt a global search initially.

---

## 👤 Person B — Moon Pipeline

Responsible for:

NASA PDS

    ↓

LRO / LOLA

    ↓

Moon DEM processing

    ↓

10 × 10 km patch

    ↓

85 × 85 common grid

    ↓

12 terrain features

    ↓

Moon feature vector

### Initial tasks

- [ ] Download one small LOLA DEM.
- [ ] Load the DEM with Rasterio.
- [ ] Select one lunar location.
- [ ] Extract a 10 km × 10 km area.
- [ ] Convert it to the common 85 × 85 grid.
- [ ] Calculate the same 12 terrain features.
- [ ] Save the resulting feature vector.
- [ ] Add tests for lunar preprocessing.

Start with **one Moon location**.

A possible development benchmark is:

Marius Hills

Latitude:   14.0

Longitude: \-56.0

The benchmark is initially being used to develop and verify the algorithm, not as a claim that it is the optimal location for a future lunar base.

---

# 🤝 Shared Data Contract

Both pipelines must produce compatible feature records.

Example:

patch\_id

source

center\_lat

center\_lon

slope\_p05

slope\_p10

slope\_p25

slope\_p50

slope\_p75

slope\_p90

slope\_p95

rms\_height

tri\_mean

relief\_range

hypsometric\_integral

elev\_skew

Example Earth output:

patch\_id,source,center\_lat,center\_lon,slope\_p50,rms\_height,tri\_mean,relief\_range

earth\_001,NASADEM,35.4,\-111.5,4.2,42.0,12.5,180.0

The complete implementation contains all 12 terrain features.

The two pipelines should be considered compatible when:

set(earth\_features.keys()) == set(moon\_features.keys())

for the terrain\-feature fields.

---

# 🏗️ Project Structure

Planned repository structure:

moon\-analog\-lite/

├── README.md

├── requirements.txt

├── config.py

├── app.py

│

├── 0\_download\_data.py

├── 1\_build\_index.py

├── 2\_find\_analogs.py

├── 3\_plot\_match.py

│

├── src/

│   ├── \_\_init\_\_.py

│   ├── contracts.py

│   ├── raster\_io.py

│   ├── morphometry.py

│   ├── scoring.py

│   ├── query.py

│   └── plotting.py

│

├── tests/

│   ├── test\_morphometry.py

│   ├── test\_scoring.py

│   └── test\_pipeline.py

│

├── data/

│   ├── nasadem/

│   ├── lola/

│   └── earth\_index.csv

│

└── outputs/

    ├── latest\_query.json

    └── analog\_comparison.png

---

# 🚀 Milestones

## Milestone 0 — Define the Contract

**Together**

Before implementing the individual pipelines:

- [ ] Agree on patch size: **10 km × 10 km**
- [ ] Agree on analysis grid: **85 × 85**
- [ ] Agree on feature names.
- [ ] Agree on feature units.
- [ ] Define extract\_patch\_features().
- [ ] Define CSV/output schema.

---

## Milestone 1 — Independent Data Pipelines

Work completely in parallel.

### Earth

NASADEM

   ↓

one DEM

   ↓

one 85 × 85 patch

   ↓

12 features

### Moon

LOLA

 ↓

one DEM

 ↓

one 85 × 85 patch

 ↓

12 features

### Success

Both pipelines independently produce compatible feature vectors.

---

## Milestone 2 — First Earth–Moon Comparison

Combine both outputs:

Earth features

      │

      ▼

   Compare

      ▲

      │

Moon features

Calculate:

Slope distance

      \+

Terrain shape distance

      =

Combined distance

Lower distance means the terrain profiles are more similar according to the selected metrics.

---

## Milestone 3 — Build Earth Index

Expand the Earth pipeline:

1 Earth patch

     ↓

10 patches

     ↓

100\+ patches

     ↓

earth\_index.csv

Each row represents one Earth terrain patch and its feature vector.

---

## Milestone 4 — Find Top\-K Analogs

Implement:

find\_analogs(

    moon\_features,

    earth\_index,

    top\_k=5,

)

Example:

Moon location: Marius Hills

Rank \| Earth Region \| Distance

\-\-\-\-\-\|\-\-\-\-\-\-\-\-\-\-\-\-\-\-\|\-\-\-\-\-\-\-\-\-

1    \| Region A     \| 0.31

2    \| Region B     \| 0.38

3    \| Region C     \| 0.44

4    \| Region D     \| 0.51

5    \| Region E     \| 0.57

---

## Milestone 5 — Streamlit MVP

Create a lightweight UI:

🌕 Moon Analog Finder

Moon location:

[Marius Hills ▼]

Slope / terrain weighting:

[━━━━━━━━●━━]

[ Find Analogs ]

Top Earth Matches

1\. Region A

2\. Region B

3\. Region C

Moon Terrain     Earth Terrain

Slope distance: 0.21

Shape distance: 0.42

Total distance: 0.31

Initial UI scope:

- [ ] Select predefined Moon location.
- [ ] Enter custom latitude/longitude.
- [ ] Select Top\-K.
- [ ] Adjust slope/shape weighting.
- [ ] Run comparison.
- [ ] Display ranked Earth sites.
- [ ] Show terrain comparison plot.
- [ ] Show individual similarity components.
- [ ] Show project limitations.

---

# ✅ Definition of MVP

The MVP is complete when this path works:

Real NASADEM Earth data

           ↓

     Earth features

           │

           │

           ▼

     Similarity engine

           ▲

           │

      Moon features

           ↑

 Real LOLA Moon data

           │

           ▼

    Top Earth matches

           │

           ▼

      Streamlit UI

The goal is **not** initially to search the entire Earth.

The goal is to prove that the complete pipeline works correctly for a small number of locations.

---

# 🔬 Scientific Scope

The first version measures **terrain similarity only**.

The score should be interpreted as:

Similarity between selected elevation\-derived terrain characteristics.

It should **not** be interpreted as:

- probability that two environments are equivalent;
- lunar landing\-site suitability;
- habitat suitability;
- mission safety;
- geological equivalence;
- NASA endorsement of an Earth analog.

Earth cannot reproduce many important lunar conditions, including lunar gravity, vacuum, radiation environment, dust properties, and thermal behavior.

---

# 🔭 Future Development

## Phase 2 — Temperature

After terrain works, investigate:

[LRO Diviner Lunar Data](https://pds-geosciences.wustl.edu/missions/lro/diviner.htm?utm_source=%27chatgpt.com%27)

The model could then become:

Analog similarity

      │

      ├── Terrain similarity

      │      ├── slope

      │      ├── roughness

      │      └── relief

      │

      └── Thermal similarity

             ├── temperature range

             ├── minimum temperature

             └── thermal extremes

An appropriate NASA Earth\-observation temperature dataset would need to be selected for the Earth side before implementing this phase.

---

## Phase 3 — Additional Characteristics

Possible future dimensions:

Terrain

\+

Temperature

\+

Illumination

\+

Surface/geological characteristics

\+

Ice/resource indicators

Each dimension should remain an independent, explainable component of the final similarity score.

---

## Phase 4 — Mars

Once the architecture works for:

Earth ↔ Moon

extend the target pipeline to:

Earth ↔ Moon

Earth ↔ Mars

The same high\-level architecture can remain:

Planetary dataset

       ↓

Common representation

       ↓

Feature extraction

       ↓

Similarity engine

       ↓

Earth analog ranking

---

# 🧪 Development Principle

Always implement the smallest version first.

ONE Earth patch

\+

ONE Moon patch

        ↓

Feature comparison

        ↓

Does it work?

        ↓

YES

        ↓

More Earth patches

        ↓

More Moon locations

        ↓

Streamlit

        ↓

Additional datasets

Do not add new datasets until the previous comparison works end\-to\-end.

---

# 🌌 NASA Space Apps Challenge

This project is being developed for the:

**2026 NASA Space Apps Challenge**

Challenge:

**Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars**

Challenge resources:

[Official Challenge Resources](https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/?tab=resources)

The initial MVP focuses specifically on the challenge's **terrain and topography** dimension.

---

# ⚠️ Current Status

**Early prototype / proof of concept.**

Current focus:

NASADEM

   ↕

terrain comparison

   ↕

LOLA

The initial candidate regions and lunar benchmarks are used to develop and verify the algorithm.

They should not yet be considered scientifically validated planetary analog classifications.

