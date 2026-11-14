"""Moon | Earth patch comparison plot (CONTRACT §6)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.colors import LightSource
from matplotlib.figure import Figure

from config import EARTH_NPZ_DIR, EARTH_PATCH_DIR, PIXEL_SIZE_M, PATCH_SIZE_M


def load_earth_patch(patch_id: str, npz_dir=None) -> np.ndarray | None:
    """Patch from earth_npz/{region}.npz, falling back to the per-patch .npy; None if neither has it.

    patch_id is ``earth_{region}_{NNNN}``, so the region (and its npz) follows from the id.
    """
    npz_dir = Path(npz_dir) if npz_dir else EARTH_NPZ_DIR
    region = patch_id.removeprefix("earth_").rsplit("_", 1)[0]
    npz = npz_dir / f"{region}.npz"
    if npz.exists():
        with np.load(npz) as z:
            if patch_id in z.files:
                return z[patch_id]
    npy = EARTH_PATCH_DIR / f"{patch_id}.npy"
    return np.load(npy) if npy.exists() else None


def _panel(ax, patch: np.ndarray | None, label: str, vmax: float, title: str) -> None:
    ax.set_title(f"{title}\n{label}", fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])
    if patch is None:
        ax.text(0.5, 0.5, "patch not available", ha="center", va="center", transform=ax.transAxes)
        return
    rel = patch - np.nanmin(patch)
    hs = LightSource(azdeg=315, altdeg=45).hillshade(
        patch.astype(float), vert_exag=1, dx=PIXEL_SIZE_M, dy=PIXEL_SIZE_M
    )
    extent = (0, PATCH_SIZE_M / 1000, 0, PATCH_SIZE_M / 1000)
    ax.imshow(hs, cmap="gray", extent=extent, origin="upper")
    # colour = height above the patch minimum, same scale on both panels
    ax.imshow(rel, cmap="terrain", alpha=0.45, vmin=0, vmax=vmax, extent=extent, origin="upper")
    ax.set_xlabel("km")


def plot_comparison(
    moon_patch: np.ndarray | None,
    earth_patch: np.ndarray | None,
    moon_label: str,
    earth_label: str,
) -> Figure:
    """Two panels (Moon | Earth): hillshade plus colour = height above patch minimum, shared colour scale."""
    heights = [np.ptp(p) for p in (moon_patch, earth_patch) if p is not None]
    vmax = max(heights) if heights and max(heights) > 0 else 1.0
    fig = Figure(figsize=(11, 5.2), constrained_layout=True)
    axes = fig.subplots(1, 2)
    _panel(axes[0], moon_patch, moon_label, vmax, "Moon")
    _panel(axes[1], earth_patch, earth_label, vmax, "Earth")
    sm = matplotlib.cm.ScalarMappable(
        norm=matplotlib.colors.Normalize(0, vmax), cmap="terrain"
    )
    fig.colorbar(sm, ax=axes, shrink=0.8, label="height above patch minimum [m]")
    return fig
