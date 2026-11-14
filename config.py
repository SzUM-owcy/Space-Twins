"""Shared constants (CONTRACT §1, §2, §6)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
NASADEM_DIR = DATA_DIR / "nasadem"
OUTPUT_DIR = ROOT / "outputs"

PATCH_SIZE_M = 10_000
GRID_N = 85
PIXEL_SIZE_M = PATCH_SIZE_M / GRID_N
MOON_RADIUS_M = 1_737_400

# Verified empirically on Planetary Computer COGs: nodata tag is -32768,
# ocean is stored as 0 (not nodata).
NASADEM_NODATA = -32768
LOLA_NODATA = -32768
_LOLA_NAME = "Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"
LOLA_GLOBAL_PATH = DATA_DIR / "lola" / _LOLA_NAME
if not LOLA_GLOBAL_PATH.exists() and (ROOT / "moon" / "data" / _LOLA_NAME).exists():
    LOLA_GLOBAL_PATH = ROOT / "moon" / "data" / _LOLA_NAME  # alternative location of the same file
LOLA_POLAR_PATH = DATA_DIR / "lola" / "ldem_80s_20m.lbl"
LOLA_SCALE = 0.5

# CONTRACT §2 pt 1: fallback if PROJ does not recognise the CRS stored in the LOLA file.
LOLA_CRS_FALLBACK = (
    "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"
)
# COPDEM (cop-dem-glo-30, asset "data"): EPSG:4326, float32, no nodata tag.
COPDEM_NODATA = None  # verified: COG has no nodata tag, float32, scale 1
COPDEM_DIR = DATA_DIR / "copdem"

EARTH_PATCH_DIR = DATA_DIR / "patches" / "earth"
EARTH_NPZ_DIR = DATA_DIR / "patches" / "earth_npz"  # one small {region}.npz per region
EARTH_INDEX_PATH = DATA_DIR / "earth_index.csv"

# CONTRACT §3/§4
SLOPE_FEATURES = [f"slope_p{q:02d}" for q in (5, 10, 25, 50, 75, 90, 95)]
SHAPE_FEATURES = ["rms_height", "tri_mean", "relief_range", "hypsometric_integral", "elev_skew"]
FEATURE_NAMES = SLOPE_FEATURES + SHAPE_FEATURES
ID_COLUMNS = ["patch_id", "source", "region", "center_lat", "center_lon"]
RECORD_COLUMNS = ID_COLUMNS + FEATURE_NAMES
VALID_SOURCES = ("NASADEM", "COPDEM", "LOLA")

# Thermal feature (side tables keyed by patch_id; the CONTRACT index columns are untouched).
THERMAL_EARTH_PATH = DATA_DIR / "thermal_earth.csv"
THERMAL_MOON_PATH = DATA_DIR / "thermal_moon.csv"
THERMAL_REFERENCE_DIR = DATA_DIR / "processed"
THERMAL_EARTH_REFERENCE_PATH = THERMAL_REFERENCE_DIR / "earth_thermal_reference.json"
THERMAL_MOON_REFERENCE_PATH = THERMAL_REFERENCE_DIR / "moon_thermal_reference.json"
THERMAL_COLUMNS = [
    "patch_id", "surface_temperature_range_k", "thermal_seasonal_range_k", "thermal_valid_fraction",
    "thermal_valid_observations", "thermal_dataset", "thermal_period",
    "thermal_range_percentile",
]
THERMAL_REFERENCE_START = "2024-01-01"
THERMAL_REFERENCE_END = "2024-12-31"
THERMAL_EARTH_COLLECTION = "modis-11A2-061"  # Terra (MOD) + Aqua (MYD), 1 km, 8-day
THERMAL_MIN_OBS = 100  # valid Earth observations per pixel (of ~184 per year); fewer = seasonal bias (polar night, cloud)
THERMAL_MOON_MIN_BINS = 40  # of 96 local-time bins; GCP cells have scattered sampling gaps
THERMAL_MIN_VALID_FRACTION = 0.70
THERMAL_MIN_PERIODS = 20  # 8-day periods per pixel (of ~46 per year) with a usable day-night swing
THERMAL_MIN_SAMPLES_PER_PERIOD = 3  # of 4 overpass samples (Terra/Aqua day/night) needed for a period swing
THERMAL_MOON_GCP_URL = (
    "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gcp"
)
THERMAL_MOON_GRID_STEP_DEG = 5.0  # reference grid of lunar cells for the percentile
W_THERMAL_DEFAULT = 0.1  # experimental: thermal range is only weakly tied to terrain similarity

# Solar-illumination feature (side tables keyed by patch_id).
ILLUM_EARTH_PATH = DATA_DIR / "illumination_earth.csv"
ILLUM_MOON_PATH = DATA_DIR / "illumination_moon.csv"
ILLUM_COLUMNS = [
    "patch_id", "solar_visibility_fraction", "solar_visibility_astro",
    "solar_visibility_terrain", "illumination_points", "illumination_horizon_km",
    "illumination_dataset", "illumination_period",
]
ILLUM_START = "2024-01-01"
ILLUM_END = "2025-01-01"  # exclusive; hourly samples (a 12 h grid would alias with the Earth day)
ILLUM_STEP_HOURS = 1
ILLUM_HORIZON_RADIUS_M = 20_000  # Earth DEM window half-size for terrain horizons (mosaics have a ~22 km margin)
ILLUM_HORIZON_RADIUS_MOON_M = 40_000  # Moon: a 20 km window misses crater walls (polar validation, README)
ILLUM_GRID_STEP_M = 250.0
ILLUM_AZIMUTHS = 72
ILLUM_POINTS_N = 5  # NxN observer points over the central part of the patch
ILLUM_POINTS_SPAN_M = 8_000
ILLUM_MIN_ASTRO_FRACTION = 0.02  # below this (polar night) the ratio is not meaningful -> missing
SPICE_DIR = DATA_DIR / "spice"
SPICE_KERNELS = ("naif0012.tls", "pck00011.tpc", "de440s.bsp")
SPICE_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels"
W_ILLUM_DEFAULT = 0.1

# Mafic-felsic composition proxy (side tables keyed by patch_id).
COMPOSITION_EARTH_PATH = DATA_DIR / "composition_earth.csv"
COMPOSITION_MOON_PATH = DATA_DIR / "composition_moon.csv"
COMPOSITION_EARTH_REFERENCE_PATH = DATA_DIR / "processed" / "earth_composition_reference.json"
COMPOSITION_MOON_REFERENCE_PATH = DATA_DIR / "processed" / "moon_composition_reference.json"
COMPOSITION_EARTH_COLUMNS = [
    "patch_id", "mafic_index_raw", "quartz_index_raw", "mafic_felsic_percentile",
    "composition_valid_pixel_ratio", "composition_observation_count_median",
    "composition_confidence", "composition_status", "composition_dataset", "composition_reference_version",
]
COMPOSITION_MOON_COLUMNS = [
    "patch_id", "diviner_cf_microns", "mafic_felsic_percentile", "composition_valid_pixel_ratio",
    "composition_confidence", "composition_status", "composition_dataset", "composition_reference_version",
]
COMPOSITION_DIR = DATA_DIR / "composition"
COMPOSITION_CF_PATH = COMPOSITION_DIR / "diviner_CF_space_weathering_corrected.tiff"
COMPOSITION_CF_URL = "https://zenodo.org/api/records/4558194/files/diviner_CF_space_weathering_corrected.tiff/content"
COMPOSITION_CF_RAW_PATH = COMPOSITION_DIR / "DIVGLOB1701_CX3.tiff"  # previous viewing-geometry-only map, kept for comparison
COMPOSITION_CF_RAW_URL = "https://zenodo.org/records/4558235/files/DIVGLOB1701_CX3.tiff?download=1"
COMPOSITION_MINERAL_MAPS = {  # Diviner mineral-abundance rasters, same grid as the CF map (Zenodo record 4558194)
    "plagioclase": "diviner_MI_plagioclase.tiff",
    "pyroxene": "diviner_MI_pyroxene.tiff",
    "olivine": "diviner_MI_olivine.tiff",
}
COMPOSITION_MINERAL_URL = "https://zenodo.org/api/records/4558194/files/{name}/content"
COMPOSITION_EARTH_LITHOLOGY_PATH = DATA_DIR / "composition_earth_lithology.csv"
COMPOSITION_EARTH_MINERALS_PATH = DATA_DIR / "composition_earth_minerals.csv"
COMPOSITION_MOON_MINERALS_PATH = DATA_DIR / "composition_moon_minerals.csv"
COMPOSITION_MOON_RAW_COMPARISON_PATH = DATA_DIR / "composition_moon_cf_comparison.csv"
COMPOSITION_CF_PPD = 32  # pixels per degree; the file has no georeferencing: lat +70 (top) .. -70, lon -180 .. 180
COMPOSITION_CF_MAX_ABS_LAT = 70.0
ASTER_GED_DIR = DATA_DIR / "aster_ged"
ASTER_EMISSIVITY_SCALE = 0.001
ASTER_NDVI_SCALE = 0.01
ASTER_LAND_CLASS = 1  # AG100 land/water map value for land (verify on the first real tile)
COMPOSITION_MAX_NDVI = 0.20
COMPOSITION_MIN_VALID_RATIO = 0.30
COMPOSITION_MIN_ASTER_OBS = 3
COMPOSITION_TRIM_PERCENT = 1.0
COMPOSITION_QI_FLAG_PERCENTILE = 95.0
COMPOSITION_GRID_STEP_DEG = 5.0
W_COMPOSITION_DEFAULT = 0.0  # opt-in: experimental, needs the Earth ASTER GED build

# --- Practicality (separate from the scientific analog score) ---
PRACTICALITY_VERSION = "v0"
PRACTICALITY_PATH = DATA_DIR / "practicality_earth.csv"
PRACTICALITY_DIR = DATA_DIR / "practicality"  # gitignored download cache
# Ascending thresholds: value <= t[i] maps to band i (LOW, MEDIUM, HIGH cost), above the last is VERY HIGH.
PRACTICALITY_THRESHOLDS = {
    "city_travel_minutes": (60, 120, 240),
    "major_road_distance_km": (10, 30, 75),
    "airport_travel_minutes": (120, 240, 480),
    "hospital_travel_minutes": (60, 120, 240),
    "grid_distance_km": (5, 25, 100),
    "facility_core_slope_p90": (5, 10, 20),
    "facility_core_relief_m": (10, 30, 100),
}
FACILITY_CORE_PIXELS = 9  # ~1 km at 117.6 m/px
FACILITY_CORE_STRIDE = 2
PRACTICALITY_BARE_FULL_FRACTION = 0.5  # bare/sparse share giving the full bare-ground score
PRACTICALITY_GRID_CENSORED_KM = 150.0  # no OSM line within the search box: distance is at least this
PRACTICALITY_GRID_PAD_DEG = 1.5
PRACTICALITY_BAND_SCORES = (100.0, 62.5, 37.5, 12.5)  # centre of each 25-point class
PRACTICALITY_CLASS_EDGES = (75.0, 50.0, 25.0)  # LOW >= 75, MEDIUM >= 50, HIGH >= 25, else VERY HIGH
PRACTICALITY_SCORE_WEIGHTS = {
    "field": {"access": 0.30, "emergency": 0.25, "buildability": 0.20, "infrastructure": 0.10, "population": 0.15},
    "facility": {"access": 0.15, "emergency": 0.15, "buildability": 0.25, "infrastructure": 0.35, "population": 0.10},
}
# Population within 25 km: (upper bound, isolation penalty, impact penalty), both 0-100 (higher = worse).
PRACTICALITY_POPULATION_BANDS = (
    (100, 100.0, 0.0),
    (50_000, 0.0, 10.0),
    (250_000, 0.0, 50.0),
    (float("inf"), 0.0, 100.0),
)
PRACTICALITY_FLAG_COLUMNS = [
    "protected_area_status", "world_heritage_status", "community_rights_status", "biodiversity_status",
    "water_stress_status", "hazard_status", "security_status",
]
PRACTICALITY_COLUMNS = [
    "patch_id",
    "city_travel_minutes", "airport_travel_minutes", "major_road_distance_km", "access_score",
    "facility_core_slope_p90", "facility_core_relief_m", "bare_ground_fraction", "tree_fraction", "wetland_fraction", "buildability_score",
    "hospital_travel_minutes", "emergency_support_score",
    "grid_distance_km", "grid_source", "infrastructure_score",
    "population_10km", "population_25km", "population_50km",
    "isolation_logistics_penalty", "population_impact_penalty", "population_score",
    "protected_overlap_fraction", "protected_category", "world_heritage_overlap", "protected_communal_land", "nearest_volcano_km", "nearest_volcano_last_eruption",
    *PRACTICALITY_FLAG_COLUMNS,
    "field_campaign_score", "facility_score", "field_cost_class", "facility_cost_class",
    "hard_excluded", "exclusion_reasons",
    "practicality_completeness", "practicality_confidence", "practicality_version",
]

# Phase 2 open-data sources (no login)
PRACTICALITY_URLS = {
    "worldpop": "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/0_Mosaicked/ppp_2020_1km_Aggregated.tif",
    "airports": "https://davidmegginson.github.io/ourairports-data/airports.csv",
    "roads": "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_roads.zip",
}
PRACTICALITY_WORLDPOP_PATH = PRACTICALITY_DIR / "ppp_2020_1km.tif"
PRACTICALITY_CITY_COVERAGE = "Accessibility__201501_Global_Travel_Time_to_Cities"
PRACTICALITY_HEALTH_COVERAGE = "Accessibility__202001_Global_Motorized_Travel_Time_to_Healthcare"
PRACTICALITY_AIRPORT_DETOUR = 1.4  # road length / straight line
PRACTICALITY_AIRPORT_SPEED_KMH = 50.0

# Phase 4 constraint flags (policy, configurable)
PRACTICALITY_WDPA_URL = "https://services5.arcgis.com/Mj0hjvkNtV7NRhA7/arcgis/rest/services/WDPA_v0/FeatureServer/1/query"
PRACTICALITY_GVP_URL = (
    "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=application/json"
)
PRACTICALITY_PROTECTED_CACHE = PRACTICALITY_DIR / "protected.csv"
PRACTICALITY_VOLCANO_CACHE = PRACTICALITY_DIR / "volcanoes.csv"
PRACTICALITY_STRICT_IUCN = ("Ia", "Ib")  # strict categories: excluded when overlap >= the fraction below
PRACTICALITY_STRICT_OVERLAP = 0.5
PRACTICALITY_VOLCANO_WARN_KM = 20.0
PRACTICALITY_VOLCANO_WARN_SINCE = 1900
PRACTICALITY_VOLCANO_EXCLUDE_KM = 10.0
PRACTICALITY_VOLCANO_EXCLUDE_SINCE = 2020  # recent eruption very close: acute hazard
PRACTICALITY_TREE_WARN = 0.30
PRACTICALITY_WETLAND_WARN = 0.10
PRACTICALITY_ARID_BARE_FRACTION = 0.5  # arid proxy for the water-stress flag
PRACTICALITY_WATER_STRESS_POP_25KM = 1000
# Curated advisory per region (dynamic: recheck before any real deployment). Unlisted regions default to "ok".
PRACTICALITY_SECURITY_BY_REGION = {
    "meidob": "excluded", "bayuda": "excluded",
    "tibesti": "warning", "aorounga": "warning", "gweni_fada": "warning", "richat": "warning", "hoggar": "warning",
    "danakil": "manual_review", "nabro": "manual_review", "makhtesh_ramon": "manual_review",
}

# Approximate distance (km) from each region to the nearest high-voltage line, from general knowledge.
# Used only where no OSM Overpass result is cached; marked grid_source="estimated". 150 = remote/none (cap).
PRACTICALITY_GRID_ESTIMATE_KM = {
    "death_valley": 15, "dry_valleys": 150, "elgygytgyn": 150, "erg_chebbi": 20, "etna": 3, "gosses_bluff": 100,
    "gran_desierto": 30, "gweni_fada": 150, "haughton": 150, "harrat_lunayyir": 40, "hekla": 15, "high_atlas": 15,
    "hoggar": 100, "jebel_shams": 20, "jingpo_lake": 15, "khaybar": 25, "kamestastin": 150, "klyuchevskoy": 40,
    "ladakh": 40, "lanzarote": 5, "lava_beds": 15, "lonar": 10, "lut": 60, "mauna_kea": 10, "mauna_loa": 15,
    "makhtesh_ramon": 15, "meidob": 150, "meteor_crater": 20, "nabro": 150, "namib": 40, "odadahraun": 60,
    "ol_doinyo_lengai": 100, "pico_do_fogo": 10, "patagonia": 80, "paricutin": 20, "pinacate": 40, "pingualuit": 150,
    "puna": 100, "reunion": 5, "richat": 120, "ries": 5, "rio_grande_gorge": 20, "saririaky": 40,
    "schirmacher_oasis": 150, "sittampundi": 10, "sverrefjell": 150, "teide": 5, "tibesti": 150, "tien_shan": 30,
    "tin_bider": 100, "uyuni": 60, "vredefort": 15, "wadi_rum": 30, "waqf_as_suwwan": 40, "white_sands": 20,
    "wolfe_creek": 120, "zagros": 20, "zuni_bandera": 25,
}
