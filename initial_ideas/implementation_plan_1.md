# `moon-analog-lite` — Parallel 2-Person Implementation Plan

## Goal

Build the smallest working Earth–Moon terrain comparison application.

For the first version, use only **two datasets**:

1. **Earth:** NASADEM elevation data, discovered/downloaded through NASA Earthdata Search. 【1-45986e】
2. **Moon:** LOLA elevation/topography data from Lunar Reconnaissance Orbiter (LRO). 【2-5d5843】

Do **not** start with LRO Diviner Lunar Data. Diviner measures lunar surface temperature and can become the next dataset after terrain comparison works. 【3-754d95】

The challenge explicitly allows terrain/topography comparison and similarity-ranking tools, so this is a reasonable first MVP. 【4-693eab】

---

# 1. Parallel Architecture

```text
                     SHARED SPEC
                         │
                 10 × 10 km patch
                 85 × 85 grid
                 same feature schema
                         │
            ┌────────────┴────────────┐
            │                         │
       👤 PERSON A               👤 PERSON B
          EARTH                       MOON
            │                         │
         NASADEM                     LOLA
            │                         │
        Earth DEM                   Moon DEM
            │                         │
      10 × 10 km patch         10 × 10 km patch
            │                         │
      Feature extraction       Feature extraction
            │                         │
    earth_features.csv       moon_features.csv
            │                         │
            └────────────┬────────────┘
                         │
                     INTEGRATE
                         │
                  Similarity score
                         │
                   Top matches
                         │
                   Streamlit UI
```

---

# 2. First Agree on the Shared Contract

Before working separately, spend about **30–60 minutes together** defining the interface between both pipelines.

Both pipelines must eventually call:

```python
extract_patch_features(
    patch: np.ndarray,
    pixel_size_m: float,
) -> dict
```

Both datasets should eventually produce:

```text
10 km × 10 km terrain patch
85 × 85 pixels
~117.6 m/pixel
```

And the same feature structure:

```text
patch_id
source
center_lat
center_lon

slope_p05
slope_p10
slope_p25
slope_p50
slope_p75
slope_p90
slope_p95

rms_height
tri_mean
relief_range
hypsometric_integral
elev_skew
```

This is the key contract:

```text
EARTH                            MOON

NASADEM                          LOLA
   │                               │
   ▼                               ▼
DEM                             DEM
   │                               │
   ▼                               ▼
85 × 85                         85 × 85
   │                               │
   ▼                               ▼
12 features                     12 features
   │                               │
   └─────────── COMPARE ───────────┘
```

---

# 3. 👤 Person A — Earth / NASADEM

## Responsibility

```text
NASADEM
   ↓
Earth DEM
   ↓
Common grid
   ↓
Earth patches
   ↓
Terrain features
   ↓
earth_features.csv
```

## Milestone A1 — Download One Earth Area

Use NASA Earthdata Search to find/download NASADEM elevation data. NASA Earthdata Search is NASA's portal for discovering and accessing Earth observation datasets. 【1-45986e】

Start with **one small region only**.

For example:

```text
Barringer Crater area
```

For now, treat the location only as an **algorithm-development fixture**.

Do not try to prove yet that it is scientifically the best lunar analog.

### Expected result

```text
NASADEM
   ↓
Small Earth DEM
```

---

## Milestone A2 — Standardize the Earth DEM

Convert the Earth DEM into:

```text
10,000 m × 10,000 m

85 × 85 pixels

~117.6 m/pixel
```

Expected result:

```python
earth_patch.shape == (85, 85)
```

---

## Milestone A3 — Extract Features

Run:

```python
earth_features = extract_patch_features(
    earth_patch,
    pixel_size_m=117.647,
)
```

Save:

```text
earth_features.csv
```

Initially:

```text
1 Earth patch
```

is enough.

Later expand:

```text
1 patch
  ↓
5 patches
  ↓
20 patches
  ↓
100+ patches
```

---

# 4. 👤 Person B — Moon / LOLA

## Responsibility

```text
LOLA
  ↓
Moon DEM
  ↓
Common grid
  ↓
Moon patch
  ↓
Terrain features
  ↓
moon_features.csv
```

The Lunar Reconnaissance Orbiter (LRO) archive provides access to LOLA through NASA's Planetary Data System and Lunar Orbital Data Explorer. 【2-5d5843】

---

## Milestone B1 — Download One Moon Area

Start with **one lunar benchmark only**.

For example:

```text
Marius Hills

Latitude:  14.0
Longitude: -56.0
```

Again, initially this is an **algorithm-development fixture**.

### Expected result

```text
LOLA
 ↓
Small Moon DEM
```

---

## Milestone B2 — Standardize the Moon DEM

Produce exactly the same representation Person A produces:

```text
10,000 m × 10,000 m

85 × 85 pixels

~117.6 m/pixel
```

Expected result:

```python
moon_patch.shape == (85, 85)
```

---

## Milestone B3 — Extract Features

Use exactly the same function:

```python
moon_features = extract_patch_features(
    moon_patch,
    pixel_size_m=117.647,
)
```

Save:

```text
moon_features.csv
```

---

# 5. Milestone 1 — Independent Dataset Pipelines

Both people work in parallel.

## 👤 Person A

```text
NASADEM
   ↓
One Earth location
   ↓
85 × 85 patch
   ↓
12 features
   ↓
earth_features.csv
```

## 👤 Person B

```text
LOLA
  ↓
One Moon location
  ↓
85 × 85 patch
  ↓
12 features
  ↓
moon_features.csv
```

## Done When

Both files exist:

```text
earth_features.csv
moon_features.csv
```

and:

```python
set(earth_features.columns) == set(moon_features.columns)
```

---

# 6. Milestone 2 — First Earth–Moon Comparison

Bring both pipelines together.

```text
earth_features.csv
          │
          │
          ▼
       COMPARE
          ▲
          │
moon_features.csv
```

Implement:

```python
compare_features(
    moon_features,
    earth_features,
)
```

Initially, do not overcomplicate the algorithm.

Calculate:

```text
Slope distance
+
Terrain shape distance
=
Combined distance
```

Lower distance:

```text
more similar terrain
```

Higher distance:

```text
less similar terrain
```

---

# 7. Milestone 3 — Expand the Earth Search

Once the first comparison works:

## 👤 Person A

Expand:

```text
1 Earth patch
     ↓
10 Earth patches
     ↓
100+ Earth patches
     ↓
earth_index.csv
```

Each row represents:

```text
one 10 × 10 km Earth terrain patch
```

Example:

```text
patch_id
region
latitude
longitude
12 terrain features
```

---

## 👤 Person B

At the same time, add several lunar locations:

```text
Marius Hills

Linné Crater

Aristarchus
```

Each produces:

```text
Moon location
     ↓
10 × 10 km patch
     ↓
12 features
```

---

# 8. Milestone 4 — Matching Engine

Implement:

```python
find_analogs(
    moon_features,
    earth_index,
    top_k=5,
)
```

Flow:

```text
Moon features
      │
      ├── slope distance
      │
      └── shape distance
              │
              ▼
       combined distance
              │
              ▼
       Sort Earth patches
              │
              ▼
          Top 5 matches
```

Example:

```text
Moon location: Marius Hills

Rank | Earth Area | Distance
-----|------------|---------
1    | Region A   | 0.31
2    | Region B   | 0.38
3    | Region C   | 0.44
4    | Region D   | 0.51
5    | Region E   | 0.57
```

---

# 9. Milestone 5 — Streamlit MVP

Only build the UI once the matching algorithm works.

Keep it simple:

```text
┌─────────────────────────────────────┐
│       🌕 Moon Analog Finder         │
│                                     │
│ Moon location                       │
│ [ Marius Hills ▼ ]                  │
│                                     │
│ Terrain weighting                   │
│ [━━━━━━━━●━━]                       │
│                                     │
│        [ Find Analogs ]             │
│                                     │
│ Top Earth Matches                   │
│                                     │
│ 1. Region A                         │
│ 2. Region B                         │
│ 3. Region C                         │
│                                     │
│ Moon Terrain | Earth Terrain        │
│                                     │
│ Slope distance: 0.21                │
│ Shape distance: 0.42                │
│ Total distance: 0.31                │
└─────────────────────────────────────┘
```

## UI scope

Implement only:

- Moon location selection
- Custom latitude/longitude
- Top-K
- slope/shape weights
- `Find Analogs`
- ranked table
- terrain comparison plot
- component scores
- short limitations warning

Do not add complicated maps yet.

---

# 10. Parallel Work Summary

## 👤 Person A

```text
EARTH PIPELINE

NASA Earthdata
      ↓
NASADEM
      ↓
Earth DEM processing
      ↓
10 × 10 km patches
      ↓
85 × 85 grids
      ↓
12 features
      ↓
earth_index.csv
```

## 👤 Person B

```text
MOON PIPELINE

NASA PDS
    ↓
LRO / LOLA
    ↓
Moon DEM processing
    ↓
10 × 10 km patches
    ↓
85 × 85 grids
    ↓
12 features
    ↓
moon_features.csv
```

## Together

```text
earth_index.csv
        │
        ▼
  SIMILARITY ENGINE
        ▲
        │
moon_features.csv
        │
        ▼
    TOP MATCHES
        │
        ▼
     STREAMLIT
```

---

# 11. Phase 2 — Add Temperature

Do this **only after terrain works**.

The next logical lunar dataset is LRO Diviner Lunar Data. Diviner maps lunar surface temperatures, including derived global and polar products. 【3-754d95】

Then the system can evolve from:

```text
Analog score
    │
    └── Terrain similarity
```

to:

```text
Analog score
    │
    ├── Terrain similarity
    │     ├── slope
    │     ├── roughness
    │     └── relief
    │
    └── Temperature similarity
          ├── temperature range
          ├── thermal extremes
          └── minimum temperature
```

This follows the challenge's suggestion that an Earth analog may be similar in some dimensions while differing strongly in others, and that terrain and temperature are both relevant dimensions to explore. 【4-693eab】

---

# Definition of First Success

The goal for the first iteration is **not**:

> Search the entire Earth and accurately discover the best lunar analog.

The goal is:

```text
Real NASADEM Earth patch
           ↓
     12 features
           │
           │
           ▼
       COMPARE
           ▲
           │
     12 features
           ↑
Real LOLA Moon patch
           ↓
     Similarity result
```

Once this works reliably:

```text
1 Earth patch
     ↓
many Earth patches

1 Moon location
     ↓
several Moon locations

terrain only
     ↓
terrain + temperature
```

That keeps the first implementation small while allowing both people to work independently from the beginning.