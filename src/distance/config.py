"""Loading of the versioned distance scales and scoring profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "distance_config"
SCALES_PATH = CONFIG_DIR / "distance_scales.yaml"
PROFILES_PATH = CONFIG_DIR / "scoring_profiles.yaml"
COMPONENTS = ("terrain", "thermal", "illumination", "composition")


@dataclass(frozen=True)
class DistanceConfig:
    version: str
    terrain_scales: dict[str, float]
    thermal_scale_k: float
    illumination_gamma: float


def load_config(path: Path = SCALES_PATH) -> DistanceConfig:
    """Read the scales; refuse to score while a required scale is still ``null``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [name for name, spec in raw["terrain"].items() if spec["scale"] is None]
    if raw["thermal"]["temperature_swing"]["scale_k"] is None:
        missing.append("thermal.temperature_swing")
    if missing:
        raise ValueError(
            f"distance scales not calibrated: {missing}. Run scripts/calibrate_distance_scales.py"
        )
    gamma = float(raw["illumination"].get("gamma", 1.0))
    if gamma <= 0:
        raise ValueError("illumination.gamma must be > 0")
    return DistanceConfig(
        version=str(raw["version"]),
        terrain_scales={name: float(spec["scale"]) for name, spec in raw["terrain"].items()},
        thermal_scale_k=float(raw["thermal"]["temperature_swing"]["scale_k"]),
        illumination_gamma=gamma,
    )


def load_profile(name: str, path: Path = PROFILES_PATH) -> dict[str, float]:
    profiles = yaml.safe_load(path.read_text(encoding="utf-8"))["profiles"]
    if name not in profiles:
        raise ValueError(f"unknown profile {name!r}. Available: {', '.join(profiles)}")
    weights = {k: float(profiles[name].get(k, 0.0)) for k in COMPONENTS}
    if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError(f"profile {name!r}: weights must be >= 0 and sum to 1")
    return weights
