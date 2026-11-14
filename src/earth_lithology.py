"""Earth: categorical lithology of a patch from Macrostrat (public API, CC-BY 4.0, no login).

This is an explanatory fallback next to the ASTER mafic-felsic proxy. It is never converted into
``mafic_felsic_percentile``: bedrock maps describe mapped units that can be hidden by soil, dunes or vegetation.
Each patch is sampled on a small point grid and every point is classified from the unit's lithology text.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

from config import PATCH_SIZE_M

log = logging.getLogger(__name__)
API_URL = "https://macrostrat.org/api/v2/geologic_units/map"
SCALE_RANK = {"large": 0, "medium": 1, "small": 2, "tiny": 3}
SAMPLES_PER_SIDE = 3
EARTH_KM_PER_DEG = 111.32

# Order matters: the first matching class wins (anorthosite before generic mafic, evaporite before sediment).
LITHOLOGY_KEYWORDS = [
    ("anorthosite", ("anorthosite",)),
    ("evaporite", ("gypsum", "evaporite", "halite", "salt", "anhydrite")),
    ("carbonate", ("limestone", "dolomite", "carbonate", "marble", "chalk", "travertine")),
    ("mafic", ("basalt", "gabbro", "diabase", "dolerite", "mafic", "andesite", "amphibolite", "peridotite",
               "ultramafic", "greenstone", "komatiite", "norite", "scoria", "basanite", "picrite", "latite")),
    ("felsic", ("rhyolite", "granite", "granodiorite", "dacite", "felsic", "syenite", "tonalite", "trachyte",
                "ignimbrite", "obsidian", "quartz", "gneiss", "monzonite", "phonolite", "tuff")),
    ("unconsolidated", ("alluvium", "alluvial", "sand", "gravel", "silt", "dune", "colluvium", "till", "loess",
                        "unconsolidated", "lake", "glacial", "regolith", "soil", "clay", "mud")),
    ("sedimentary", ("sandstone", "shale", "siltstone", "conglomerate", "mudstone", "sediment", "chert")),
]
CLASSES = [c for c, _ in LITHOLOGY_KEYWORDS] + ["unknown"]


# Whole-word matching: "salt" must not match "basalt" and "sand" must not match "sandstone".
_PATTERNS = [(name, re.compile(r"\b(?:" + "|".join(words) + r")(?:s|es|y|ic)?\b")) for name, words in LITHOLOGY_KEYWORDS]


def classify_lithology(text: str | None) -> str:
    if not text:
        return "unknown"
    low = text.lower()
    for name, pattern in _PATTERNS:
        if pattern.search(low):
            return name
    return "unknown"


def _sample_points(lat: float, lon: float) -> list[tuple[float, float]]:
    half = PATCH_SIZE_M / 2000.0 / EARTH_KM_PER_DEG
    offs = (np.arange(SAMPLES_PER_SIDE) + 0.5) / SAMPLES_PER_SIDE * 2 - 1  # centres of equal cells
    cos = max(np.cos(np.radians(lat)), 0.05)
    return [(lat + a * half, lon + b * half / cos) for a in offs for b in offs]


def classify_point(lat: float, lon: float, session: requests.Session, retries: int = 3) -> str | None:
    """Class of the most detailed mapped unit at a point; ``None`` when the service fails, ``unknown`` when unmapped."""
    for attempt in range(retries):
        try:
            resp = session.get(API_URL, params={"lat": lat, "lng": lon, "response": "long", "format": "json"}, timeout=40)
            resp.raise_for_status()
            units = resp.json()["success"]["data"]
            break
        except (requests.RequestException, ValueError, KeyError):
            time.sleep(1.5 * (attempt + 1))
    else:
        return None
    if not units:
        return "unknown"
    best = min(units, key=lambda u: SCALE_RANK.get(u.get("scale"), 4))
    return classify_lithology(" ".join(str(best.get(k) or "") for k in ("lith", "name")))


def patch_lithology(lat: float, lon: float, session: requests.Session | None = None) -> dict:
    """Class fractions, dominant class and mapped-point count for one patch."""
    session = session or requests.Session()
    classes = [classify_point(la, lo, session) for la, lo in _sample_points(lat, lon)]
    answered = [c for c in classes if c is not None]
    mapped = [c for c in answered if c != "unknown"]
    counts = Counter(mapped)
    out = {
        "lithology_samples": len(classes),
        "lithology_mapped_samples": len(mapped),
        "dominant_lithology": counts.most_common(1)[0][0] if counts else "unknown",
    }
    for name in CLASSES[:-1]:
        out[f"{name}_fraction"] = counts[name] / len(mapped) if mapped else float("nan")
    out["mixed_lithology_flag"] = bool(mapped) and counts.most_common(1)[0][1] / len(mapped) < 0.6
    return out


def lithology_table(points: list[tuple[str, float, float]], workers: int = 12) -> list[dict]:
    """``points`` are (patch_id, lat, lon); returns one row per patch."""
    def one(p):
        with requests.Session() as s:
            return {"patch_id": p[0], **patch_lithology(p[1], p[2], s)}
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, points))
