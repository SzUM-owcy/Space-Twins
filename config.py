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
LOLA_SCALE = 0.5

# CONTRACT §2 pt 1: fallback if PROJ does not recognise the CRS stored in the LOLA file.
LOLA_CRS_FALLBACK = (
    "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"
)
# COPDEM (cop-dem-glo-30, asset "data"): EPSG:4326, float32, no nodata tag.
COPDEM_NODATA = None  # verified: COG has no nodata tag, float32, scale 1
COPDEM_DIR = DATA_DIR / "copdem"

EARTH_PATCH_DIR = DATA_DIR / "patches" / "earth"
EARTH_INDEX_PATH = DATA_DIR / "earth_index.csv"

# CONTRACT §3/§4
SLOPE_FEATURES = [f"slope_p{q:02d}" for q in (5, 10, 25, 50, 75, 90, 95)]
SHAPE_FEATURES = ["rms_height", "tri_mean", "relief_range", "hypsometric_integral", "elev_skew"]
FEATURE_NAMES = SLOPE_FEATURES + SHAPE_FEATURES
ID_COLUMNS = ["patch_id", "source", "region", "center_lat", "center_lon"]
RECORD_COLUMNS = ID_COLUMNS + FEATURE_NAMES
VALID_SOURCES = ("NASADEM", "COPDEM", "LOLA")
