"""Earth-Moon mineral comparison (diagnostic, never part of the weighted score).

Moon: Diviner plagioclase / pyroxene / olivine fractions (Lucey et al. 2021), measured per patch.
Earth: *estimated* from the Macrostrat lithology of the patch with typical modal compositions per rock class.
This is a first-order, class-level estimate, not a measurement: real outcrops vary widely, and 52 % of the Earth
patches have no mapped unit (status ``no_lithology``). Minerals with no lunar counterpart (quartz, K-feldspar,
carbonates, evaporites, clays) are reported as ``other`` and count as a mismatch in the distance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MINERALS = ("plagioclase", "pyroxene", "olivine")
# Typical modal fractions per lithology class: (plagioclase, pyroxene, olivine); the remainder is "other".
MODAL_COMPOSITION = {
    "anorthosite": (0.90, 0.08, 0.02),
    "mafic": (0.45, 0.40, 0.10),  # basalt, gabbro, andesite, peridotite (broad average)
    "felsic": (0.30, 0.05, 0.00),  # the rest is quartz, K-feldspar, mica
    "sedimentary": (0.05, 0.02, 0.00),
    "unconsolidated": (0.15, 0.05, 0.00),  # sand, alluvium: mixed sources, mostly quartz
    "carbonate": (0.0, 0.0, 0.0),
    "evaporite": (0.0, 0.0, 0.0),
}

EARTH_MINERAL_COLUMNS = [
    "patch_id", "earth_plagioclase_fraction", "earth_pyroxene_fraction", "earth_olivine_fraction",
    "earth_other_fraction", "earth_mineral_status", "earth_mineral_source",
]


def earth_mineral_estimate(lithology: pd.DataFrame) -> pd.DataFrame:
    """Expected mineral fractions per patch: class fractions (``*_fraction`` columns) times modal compositions."""
    out = pd.DataFrame({"patch_id": lithology["patch_id"]})
    totals = np.zeros((len(lithology), 3))
    weight = np.zeros(len(lithology))
    for name, modal in MODAL_COMPOSITION.items():
        frac = lithology.get(f"{name}_fraction")
        if frac is None:
            continue
        f = frac.fillna(0.0).to_numpy()
        totals += f[:, None] * np.array(modal)[None, :]
        weight += f
    ok = weight > 0
    est = np.where(ok[:, None], totals / np.where(ok, weight, 1.0)[:, None], np.nan)
    for i, m in enumerate(MINERALS):
        out[f"earth_{m}_fraction"] = est[:, i]
    out["earth_other_fraction"] = 1.0 - est.sum(axis=1)
    out["earth_mineral_status"] = np.where(ok, "estimated", "no_lithology")
    out["earth_mineral_source"] = "Macrostrat lithology x typical modal composition"
    return out[EARTH_MINERAL_COLUMNS]


def normalize_moon_minerals(fractions: dict[str, float]) -> dict[str, float] | None:
    """Clip the raw Diviner fractions at 0 and rescale them to sum to 1 (they are only approximately normalised)."""
    values = np.array([fractions.get(f"{m}_fraction", np.nan) for m in MINERALS], dtype=float)
    if not np.isfinite(values).all():
        return None
    values = np.clip(values, 0.0, None)
    return None if values.sum() <= 0 else dict(zip(MINERALS, values / values.sum()))


def mineral_distance(moon: dict[str, float] | None, earth_row: pd.Series) -> float:
    """Half the L1 distance between the Moon mix and the Earth mix over four classes: plagioclase, pyroxene, olivine
    and "other" (minerals with no lunar counterpart, 0 on the Moon). 0 = identical, 1 = disjoint. Counting "other"
    stops quartz- or carbonate-rich surfaces from looking lunar after renormalisation. NaN when either side is
    unavailable."""
    if moon is None:
        return float("nan")
    earth = np.array([earth_row.get(f"earth_{m}_fraction", np.nan) for m in MINERALS], dtype=float)
    if not np.isfinite(earth).all():
        return float("nan")
    other = max(0.0, 1.0 - earth.sum())
    moon_mix = np.array([moon[m] for m in MINERALS])
    return float(0.5 * (np.abs(earth - moon_mix).sum() + other))
