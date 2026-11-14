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
    "patch_id", "surface_temperature_range_k", "thermal_valid_fraction",
    "thermal_valid_observations", "thermal_dataset", "thermal_period",
    "thermal_range_percentile",
]
THERMAL_REFERENCE_START = "2024-01-01"
THERMAL_REFERENCE_END = "2024-12-31"
THERMAL_EARTH_COLLECTION = "modis-11A2-061"  # Terra (MOD) + Aqua (MYD), 1 km, 8-day
THERMAL_MIN_OBS = 100  # valid Earth observations per pixel (of ~184 per year); fewer = seasonal bias (polar night, cloud)
THERMAL_MOON_MIN_BINS = 40  # of 96 local-time bins; GCP cells have scattered sampling gaps
THERMAL_MIN_VALID_FRACTION = 0.70
THERMAL_MOON_GCP_URL = (
    "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gcp"
)
THERMAL_MOON_GRID_STEP_DEG = 5.0  # reference grid of lunar cells for the percentile
W_THERMAL_DEFAULT = 0.2

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
