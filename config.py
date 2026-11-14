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
