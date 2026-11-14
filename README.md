# `moon-analog-lite` — Simple 2-Person Implementation Plan

## Goal

Build the **smallest working version first**:

> Select a Moon location → extract terrain features → compare them with Earth terrain → rank similar Earth locations → show results in Streamlit.

For the beginning, use only **2 datasets**:

1. **Moon:** LOLA DEM
2. **Earth:** NASADEM

Do **not** add AI/ML, vegetation, temperature, geology, or Mars yet.

---

# 1. MVP Flow

```text
Moon LOLA DEM
    ↓
10 × 10 km Moon patch
    ↓
12 terrain features
    ↓
Similarity comparison
    ↑
12 terrain features
    ↑
10 × 10 km Earth patches
    ↑
NASADEM
```

Result:

```text
Moon location
    ↓
Terrain features
    ↓
Similarity score
    ↓
Top 5 Earth matches
    ↓
Streamlit UI
```

---

# 2. Split the Work Between Two People

## 👤 Person A — Data & Feature Pipeline

**Responsibility:**

```text
DEM → patches → features → earth_index.csv
```

### Main tasks

- [ ] Generate simple mock DEM data
- [ ] Implement common 10 × 10 km / 85 × 85 grid
- [ ] Implement `extract_patch_features()`
- [ ] Read NASADEM
- [ ] Extract Earth patches
- [ ] Generate `earth_index.csv`
- [ ] Read LOLA
- [ ] Extract Moon patch
- [ ] Add feature extraction tests

### Main interface

```python
extract_patch_features(
    patch: np.ndarray,
    pixel_size_m: float,
) -> dict
```

### Output features

```text
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

---

## 👤 Person B — Matching & Streamlit

**Responsibility:**

```text
features → similarity → ranking → UI
```

### Main tasks

- [ ] Create temporary/mock `earth_index.csv`
- [ ] Implement slope distance
- [ ] Implement shape distance
- [ ] Implement combined similarity score
- [ ] Implement `find_analogs()`
- [ ] Build CLI query
- [ ] Build basic Streamlit UI
- [ ] Build comparison plot
- [ ] Add scoring tests

### Main interface

```python
find_analogs(
    moon_features,
    earth_index,
    top_k=5,
    slope_weight=0.6,
)
```

Example result:

```text
Rank | Earth Region | Distance
1    | Region A     | 0.42
2    | Region B     | 0.57
3    | Region C     | 0.71
```

---

# 3. Shared Contract

Before starting separate work, agree on the structure of:

```text
earth_index.csv
```

Example:

```csv
patch_id,region_name,center_lat,center_lon,slope_p05,slope_p10,slope_p25,slope_p50,slope_p75,slope_p90,slope_p95,rms_height,tri_mean,relief_range,hypsometric_integral,elev_skew
earth_001,region_a,35.4,-111.5,1.2,2.0,3.1,4.2,5.7,8.1,10.2,42.0,12.5,180.0,0.43,0.31
```

This becomes the boundary between both people:

```text
Person A

DEM
 ↓
Feature extraction
 ↓
earth_index.csv

--------------------
SHARED CONTRACT
--------------------

Person B

earth_index.csv
 ↓
Similarity
 ↓
Ranking
 ↓
Streamlit
```

Person B does **not** need to wait for Person A.

Person B can create a mock CSV and start implementing the application immediately.

---

# 4. Milestone 1 — Mock End-to-End Prototype

## Goal

Prove that the architecture works **without NASA data**.

### 👤 Person A

Generate three simple synthetic terrains:

```text
Crater
Cone
Flat terrain
```

Then:

```text
Mock DEM
   ↓
Feature extraction
   ↓
mock_earth_index.csv
```

### 👤 Person B

Create a temporary `mock_earth_index.csv` and implement:

```text
Features
   ↓
Similarity scoring
   ↓
Ranking
   ↓
Streamlit
```

### Milestone complete when

```bash
pytest -v
streamlit run app.py
```

works and the application shows something like:

```text
Moon mock crater

Top Earth matches:

1. Earth crater
2. Earth cone
3. Flat terrain
```

---

# 5. Milestone 2 — Add Real Earth Data

## Goal

Replace mock Earth terrain with NASADEM.

### 👤 Person A

Implement:

```text
NASADEM
   ↓
Terrain preprocessing
   ↓
10 × 10 km patches
   ↓
12 features
   ↓
earth_index.csv
```

For the first version, use only **2–3 Earth regions**.

Do not start with all 15 candidate regions.

### 👤 Person B

No major changes should be required.

Replace:

```text
mock_earth_index.csv
```

with:

```text
earth_index.csv
```

### Milestone complete when

```text
Real NASADEM
     ↓
Earth feature index
     ↓
Existing similarity algorithm
     ↓
Ranking works
```

---

# 6. Milestone 3 — Add Real Moon Data

## Goal

Replace the mock Moon patch with LOLA data.

### 👤 Person A

Start with **one Moon location only**.

For example:

```text
Marius Hills
```

Implement:

```text
LOLA DEM
   ↓
10 × 10 km Moon patch
   ↓
85 × 85 common grid
   ↓
12 terrain features
```

### 👤 Person B

Connect the Moon features to the existing matching function:

```text
Moon features
      ↓
find_analogs()
      ↓
Top 5 Earth matches
```

### Milestone complete when

```bash
python 2_find_analogs.py \
    --lat 14.0 \
    --lon -56.0 \
    --top-k 5
```

returns results using real Moon and Earth terrain data.

---

# 7. Milestone 4 — Streamlit MVP

Keep the first UI very simple.

```text
Moon Analog Finder

Moon location:
[Marius Hills ▼]

Slope importance:
[------●----]

Top results:

1. Earth Region A
2. Earth Region B
3. Earth Region C

[Comparison Plot]
```

## UI Features

Only implement:

- [ ] Moon benchmark selection
- [ ] Custom latitude/longitude
- [ ] Top-K selection
- [ ] Slope/shape weight
- [ ] `Find Analogs` button
- [ ] Ranked results table
- [ ] Comparison plot
- [ ] Short limitations warning

Do not add complicated interactive maps yet.

---

# 8. Milestone 5 — Demo Ready

Only start this milestone once the complete MVP works.

Possible improvements:

- [ ] Add 2–3 Moon locations
- [ ] Add more Earth regions
- [ ] Improve comparison plots
- [ ] Show data provenance
- [ ] Show slope vs. shape score
- [ ] Explain why each match ranked highly
- [ ] Improve Streamlit styling
- [ ] Add download results button
- [ ] Prepare README
- [ ] Prepare hackathon demo/presentation

---

# 9. Parallel Development Flow

```text
                    START
                      │
             Agree on contracts
                      │
          ┌───────────┴───────────┐
          │                       │
     👤 Person A             👤 Person B
          │                       │
     Mock DEMs              Mock feature CSV
          │                       │
 Feature extraction             Scoring
          │                       │
  NASADEM pipeline               CLI
          │                       │
    LOLA pipeline             Streamlit
          │                       │
          └───────────┬───────────┘
                      │
                 INTEGRATION
                      │
               Real Earth DEM
                      │
               Real Moon DEM
                      │
                Full ranking
                      │
               Streamlit MVP
                      │
                    DEMO
```

---

# 10. Recommended First Sprint

Keep the first sprint **very small**.

## 👤 Person A

### Task A1

Generate:

```text
crater.tif
cone.tif
flat.tif
```

### Task A2

Implement:

```python
extract_patch_features()
```

### Task A3

Generate:

```text
mock_earth_index.csv
```

### Task A4

Write feature tests.

---

## 👤 Person B

### Task B1

Create a temporary:

```text
mock_earth_index.csv
```

### Task B2

Implement:

```python
find_analogs()
```

### Task B3

Write ranking tests.

### Task B4

Create:

```text
app.py
```

with a basic Streamlit interface.

---

# 11. Definition of First Success

Do **not** define the first success as:

> We downloaded and processed all NASA data.

Instead, the first success should be:

```text
Mock Moon terrain
       ↓
12 features
       ↓
Similarity algorithm
       ↓
Mock Earth terrains
       ↓
Correct ranking
       ↓
Streamlit displays results
```

Once this works, replace the mock inputs **one at a time**:

```text
STEP 1

Mock Earth
    ↓
Real NASADEM
```

Then:

```text
STEP 2

Mock Moon
    ↓
Real LOLA
```

Final MVP:

```text
Real LOLA Moon terrain
          ↓
     12 features
          ↓
 Similarity engine
          ↑
     12 features
          ↑
Real NASADEM Earth terrain
          ↓
    Top 5 matches
          ↓
     Streamlit UI
```

---

# Key Principle

**Make the algorithm work with fake/simple data first.**

Then gradually introduce real NASA data.

This allows both people to work in parallel and prevents geospatial/data-access problems from blocking development of the scoring algorithm and UI.