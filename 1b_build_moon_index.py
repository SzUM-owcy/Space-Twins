"""Zbuduj indeks Księżyca: łatki z LOLA -> cechy -> data/moon_index.csv (CONTRACT §4).

    uv run python 1b_build_moon_index.py

Dla każdego miejsca z SITES: wycina łatkę 85x85 (extract_patch), liczy 12 cech,
zapisuje data/patches/moon/moon_<slug>.npy (float32), wiersz do data/moon_index.csv
i podgląd PNG w outputs/ (nie idzie do gita).
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import LightSource

from config import DATA_DIR, OUTPUT_DIR, PIXEL_SIZE_M
from src.morphometry import FEATURE_NAMES, extract_patch_features
from src.query import PatchRejected, extract_moon_patch

LOLA_PATH = DATA_DIR / "lola" / "Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"
PATCH_DIR = DATA_DIR / "patches" / "moon"
INDEX_PATH = DATA_DIR / "moon_index.csv"

# slug -> (lat, lon). Współrzędne wschodnie dodatnie, lon -180..180.
# Produkt globalny 118 m: |lat| <= 75. Miejsca polarne (lat <= -80) wymagają produktu polarnego.
SITES: dict[str, tuple[float, float]] = {
    # Rów lawowy w Marius Hills wg Wikipedii (Lunar lava tube: 14°4'20.83"N 56°44'57.49"W).
    # Wcześniejsze (14.0, -56.0) leżało ok. 22 km na wschód, na płaskim zboczu płaskowyżu.
    "marius_hills": (14.0725, -56.7493),
    # Miejsca lądowań Apollo
    "apollo_11": (0.67, 23.47),  # Morze Spokoju
    "apollo_12": (-3.01, -23.42),  # Ocean Burz
    "apollo_14": (-3.65, -17.47),  # Fra Mauro
    "apollo_15": (26.13, 3.63),  # Hadley Rille
    "apollo_16": (-8.97, 15.50),  # wyżyny Descartes
    "apollo_17": (20.19, 30.77),  # Taurus-Littrow
    # Kratery (centralne szczyty)
    "tycho": (-43.3, -11.4),
    "copernicus": (9.6, -20.1),
    "aristarchus_crater": (23.7, -47.4),  # sam krater; płaskowyż leży ok. 25-27N, 49-52W
    # Maria (gładkie)
    "mare_serenitatis": (28.0, 17.5),
    "mare_imbrium": (32.8, -15.6),
    # Wyżyny (szorstkie)
    "highlands_maurolycus": (-42.0, 14.0),
    "highlands_hipparchus": (-5.5, 4.8),
}

RECORD_COLUMNS = ["patch_id", "source", "region", "center_lat", "center_lon", *FEATURE_NAMES]


def save_preview(patch: np.ndarray, title: str, path) -> None:
    hs = LightSource(azdeg=315, altdeg=45).hillshade(
        patch, vert_exag=1, dx=PIXEL_SIZE_M, dy=PIXEL_SIZE_M
    )
    fig, ax = plt.subplots(1, 2, figsize=(11, 5))
    ax[0].imshow(hs, cmap="gray")
    ax[0].set_title(f"{title}: hillshade (północ u góry)")
    im = ax[1].imshow(patch - patch.min(), cmap="terrain")
    ax[1].set_title("wysokość nad minimum łatki [m]")
    fig.colorbar(im, ax=ax[1])
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main() -> None:
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    rows = []
    with rasterio.open(LOLA_PATH) as src:
        for slug, (lat, lon) in SITES.items():
            patch_id = f"moon_{slug}"
            try:
                patch = extract_moon_patch(src, lat, lon)
            except PatchRejected as err:
                print(f"[POMINIĘTO] {patch_id}: {err}")
                continue
            print(
                f"{patch_id}: shape={patch.shape} min={patch.min():.1f} "
                f"max={patch.max():.1f} mean={patch.mean():.1f} m"
            )

            features = extract_patch_features(patch, PIXEL_SIZE_M)
            np.save(PATCH_DIR / f"{patch_id}.npy", patch.astype(np.float32))
            save_preview(patch, slug, OUTPUT_DIR / f"{patch_id}.png")
            rows.append(
                {
                    "patch_id": patch_id,
                    "source": "LOLA",
                    "region": slug,
                    "center_lat": lat,
                    "center_lon": lon,
                    **features,
                }
            )

    df = pd.DataFrame(rows, columns=RECORD_COLUMNS)
    df.to_csv(INDEX_PATH, index=False)
    print(f"zapisano {INDEX_PATH} ({len(df)} wierszy)")
    if len(df):
        print(df.iloc[0].to_string())


if __name__ == "__main__":
    main()
