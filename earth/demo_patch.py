"""Cut one Earth patch (default: Meteor Crater) and save a hillshade picture.

    uv run python earth/demo_patch.py [--lat 35.03 --lon -111.02]
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rasterio
from matplotlib.colors import LightSource
from rasterio.merge import merge

from config import NASADEM_DIR, NASADEM_NODATA, OUTPUT_DIR, PIXEL_SIZE_M
from download_nasadem import download_tiles
from raster_io import extract_patch

p = argparse.ArgumentParser()
p.add_argument("--lat", type=float, default=35.03)
p.add_argument("--lon", type=float, default=-111.02)
args = p.parse_args()

m = 0.2
tiles = download_tiles([args.lon - m, args.lat - m, args.lon + m, args.lat + m])

# Mosaic from local disk so patches at tile edges are not cut off.
mosaic = NASADEM_DIR / "mosaic_tmp.tif"
datasets = [rasterio.open(t) for t in tiles]
arr, transform = merge(datasets, nodata=NASADEM_NODATA)
profile = datasets[0].profile | {
    "height": arr.shape[1], "width": arr.shape[2], "transform": transform, "nodata": NASADEM_NODATA,
}
for d in datasets:
    d.close()
with rasterio.open(mosaic, "w", **profile) as dst:
    dst.write(arr)

with rasterio.open(mosaic) as src:
    patch = extract_patch(src, args.lat, args.lon, "earth", nodata=NASADEM_NODATA)
if patch is None:
    raise SystemExit("patch rejected")
print(f"shape={patch.shape} min={patch.min():.1f} max={patch.max():.1f} mean={patch.mean():.1f}")

OUTPUT_DIR.mkdir(exist_ok=True)
hs = LightSource(azdeg=315, altdeg=45).hillshade(patch, vert_exag=1, dx=PIXEL_SIZE_M, dy=PIXEL_SIZE_M)
fig, ax = plt.subplots(1, 2, figsize=(11, 5))
ax[0].imshow(hs, cmap="gray")
ax[0].set_title("hillshade (north up)")
im = ax[1].imshow(patch - patch.min(), cmap="terrain")
ax[1].set_title("height above patch min [m]")
fig.colorbar(im, ax=ax[1])
out = OUTPUT_DIR / "demo_patch.png"
fig.savefig(out, dpi=110)
print("saved", out)
