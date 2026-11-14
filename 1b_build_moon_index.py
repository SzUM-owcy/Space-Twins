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

from config import DATA_DIR, LOLA_NODATA, LOLA_SCALE, OUTPUT_DIR, PIXEL_SIZE_M
from src.morphometry import FEATURE_NAMES, extract_patch_features
from src.raster_io import extract_patch

LOLA_PATH = DATA_DIR / "lola" / "Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"
PATCH_DIR = DATA_DIR / "patches" / "moon"
INDEX_PATH = DATA_DIR / "moon_index.csv"

# slug -> (lat, lon). Współrzędne wschodnie dodatnie, lon -180..180.
# Faza 3 rozbuduje to do 10-20 miejsc (docs/PERSON_B_MOON.md).
SITES: dict[str, tuple[float, float]] = {
    # Rów lawowy w Marius Hills wg Wikipedii (Lunar lava tube: 14°4'20.83"N 56°44'57.49"W).
    # Wcześniejsze (14.0, -56.0) leżało ok. 22 km na wschód, na płaskim zboczu płaskowyżu.
    "marius_hills": (14.0725, -56.7493),
}

RECORD_COLUMNS = ["patch_id", "source", "region", "center_lat", "center_lon", *FEATURE_NAMES]

# Sanity check wysokości LOLA po zastosowaniu skali (CONTRACT §2 pkt 8).
LOLA_MIN_M, LOLA_MAX_M = -9150.0, 10800.0


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
            patch = extract_patch(
                src, lat, lon, body="moon", nodata=LOLA_NODATA, scale=LOLA_SCALE
            )
            if patch is None:
                print(f"[POMINIĘTO] {patch_id}: łatka odrzucona (nodata / poza rastrem)")
                continue

            lo, hi = float(patch.min()), float(patch.max())
            if lo < LOLA_MIN_M or hi > LOLA_MAX_M:
                raise ValueError(
                    f"{patch_id}: wysokości {lo:.0f}..{hi:.0f} m poza zakresem LOLA "
                    f"({LOLA_MIN_M:.0f}..{LOLA_MAX_M:.0f}) – sprawdź skalę"
                )
            print(f"{patch_id}: shape={patch.shape} min={lo:.1f} max={hi:.1f} mean={patch.mean():.1f} m")

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
