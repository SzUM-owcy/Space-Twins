# Earth analog practicality

Answers a different question than the scientific engine: *if a site is scientifically useful, how hard, expensive,
disruptive and risky is it to run the simulation there?* The two are **never combined** and practicality never changes
`total_distance` or the ranking. `include_practicality` / `--practicality` only attaches extra blocks.

Side table: `data/practicality_earth.csv` (one row per Earth patch, built by `1f_build_practicality.py`).

## Groups

**Group A - mitigable with resources** (money, logistics): turned into 0-100 scores, higher = easier/cheaper.

| Score | Inputs | Source |
|---|---|---|
| `access_score` | `city_travel_minutes`, `airport_travel_minutes`, `major_road_distance_km` | Malaria Atlas travel time to cities (2015); OurAirports (straight line x1.4 at 50 km/h, an estimate); Natural Earth major roads |
| `buildability_score` | `facility_core_slope_p90`, `facility_core_relief_m`, `bare_ground_fraction` | best 1 x 1 km window in the existing DEM patch; ESA WorldCover 2021 |
| `emergency_support_score` | `hospital_travel_minutes` | Malaria Atlas motorised travel time to the nearest healthcare facility (2020) - a proxy for hospital |
| `infrastructure_score` | `grid_distance_km` | OSM high-voltage lines (Overpass) for `grid_source = osm`; **approximate values from general knowledge** for `estimated` regions |

**Group B - intrinsic constraints**: flags, never a number that money can fix. Each is
`ok | warning | manual_review | excluded | missing`.

| Flag | Rule |
|---|---|
| `protected_area_status` | WDPA overlap; any overlap = `manual_review`; strict IUCN (Ia, Ib) covering >= 50% = `excluded` |
| `world_heritage_status` | overlap with a World Heritage designation = `manual_review` |
| `community_rights_status` | communal/indigenous WDPA ownership = `warning`, otherwise always `manual_review` (no land-rights dataset was checked; unknown is never "clear") |
| `biodiversity_status` | tree fraction >= 0.30 or wetland fraction >= 0.10 = `warning` |
| `water_stress_status` | **proxy**: arid (bare fraction >= 0.5) and population within 25 km >= 1000 = `warning` |
| `hazard_status` | Smithsonian GVP Holocene volcano: <= 20 km and erupted since 1900 = `warning`; <= 10 km and erupted since 2020 = `excluded` |
| `security_status` | curated per-region list in `config.py` (`PRACTICALITY_SECURITY_BY_REGION`); dynamic, recheck before any deployment |

Population is deliberately non-monotonic and keeps two separate outputs: `isolation_logistics_penalty` (few people
within 25 km) and `population_impact_penalty` (many people). Moving residents is never a way to improve a score.

## Profiles

| Dimension | `field_campaign_score` | `facility_score` |
|---|---|---|
| access | 30% | 15% |
| emergency | 25% | 15% |
| buildability | 20% | 25% |
| infrastructure | 10% | 35% |
| population | 15% | 10% |

Classes: >= 75 LOW, >= 50 MEDIUM, >= 25 HIGH, below VERY HIGH relative cost. Any `excluded` flag gives
`hard_excluded = true` and the class `EXCLUDED / MANUAL REVIEW` instead of a cost class.

Missing is never zero: a score is the weight-renormalised mean over available dimensions;
`practicality_completeness` (share of the five dimensions available) sets `practicality_confidence`.

## Query output

With `include_practicality = true` each result gets `practicality` (scores, classes, `pareto_field`,
`pareto_facility`) and `constraints` (the seven flags, `hard_excluded`, `exclusion_reasons`).
`pareto_*` marks candidates not dominated on (scientific `total_distance`, practical score) among the returned
results; use a larger `top_k` and `max_per_region = null` for a fuller front.
`3b_plot_pareto.py --profile field|facility` draws the trade-off from `outputs/latest_query.json`.

## Rebuild

```bash
uv run --frozen python 1f_build_practicality.py init           # empty table for all patches
uv run --frozen python 1f_build_practicality.py buildability   # from cached DEM patches
uv run --frozen python 1f_build_practicality.py access         # travel time, airports, roads
uv run --frozen python 1f_build_practicality.py population     # WorldPop 2020 1 km (870 MB download)
uv run --frozen python 1f_build_practicality.py landcover      # ESA WorldCover
uv run --frozen python 1f_build_practicality.py grid           # cached OSM + estimates; --fetch queries Overpass (slow)
uv run --frozen python 1f_build_practicality.py protected      # WDPA lookups (cache)
uv run --frozen python 1f_build_practicality.py flags          # volcano hazard + all flags
```

Downloads are cached in the gitignored `data/practicality/`.

## Limitations

- Practicality is region/patch-level and coarse (1 km rasters); it is a screening aid, not a cost estimate.
- Grid distance: only 15 regions come from OSM; the rest are rough estimates (`grid_source = estimated`).
- Airport travel time is a straight-line estimate; healthcare time is to the nearest health facility, not a hospital.
- Natural Earth roads are major roads only; OSM coverage is uneven in remote areas.
- Antarctic regions lie outside the travel-time rasters (19 patches have no city/hospital time).
- Water stress and community rights are proxies/unknowns, not assessments; no real permitting or cost (EUR) model.
- Bare/sparse land cover and WDPA categories change over time; dynamic hazards and security need a pre-deployment recheck.
