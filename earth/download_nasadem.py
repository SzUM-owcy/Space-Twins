"""Download NASADEM 1x1 deg tiles covering a bbox from Planetary Computer and inspect them.

    uv run python earth/download_nasadem.py [--bbox W S E N]

If Python SSL fails (WSL/proxy), set REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt.
"""
import argparse
from pathlib import Path

import numpy as np
import planetary_computer
import pystac_client
import rasterio
import requests

from config import NASADEM_DIR

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def download_tiles(bbox, out_dir: Path = NASADEM_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = catalog.search(collections=["nasadem"], bbox=bbox).item_collection()
    paths = []
    for item in items:
        path = out_dir / f"{item.id}.tif"
        if not path.exists():
            print(f"downloading {item.id} ...")
            with requests.get(item.assets["elevation"].href, stream=True, timeout=60) as r:
                r.raise_for_status()
                tmp = path.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.rename(path)
        paths.append(path)
    return paths


def inspect(path: Path) -> None:
    with rasterio.open(path) as src:
        a = src.read(1)
        print(f"\n== {path.name}")
        print(f"crs={src.crs} size={src.width}x{src.height} dtype={src.dtypes[0]}")
        print(f"nodata={src.nodata} scale={src.scales[0]} offset={src.offsets[0]}")
        print(f"min={a.min()} max={a.max()} nodata_px={(a == -32768).sum()}")
        print(f"pixels exactly 0: {(a == 0).mean():.1%}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--bbox", type=float, nargs=4, default=[-111.1, 35.0, -111.0, 35.1])
    for path in download_tiles(p.parse_args().bbox):
        inspect(path)
