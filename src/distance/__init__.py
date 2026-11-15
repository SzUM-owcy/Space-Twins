"""Feature-specific distances (``physical_hybrid_v1``): each component uses a comparison suited to its physics."""

from src.distance.aggregate import aggregate
from src.distance.composition import composition_distance
from src.distance.config import DistanceConfig, load_config, load_profile
from src.distance.illumination import illumination_distance
from src.distance.models import ComponentDistance
from src.distance.terrain import terrain_distance
from src.distance.thermal import thermal_distance

SCORING_METHODS = ("legacy_percentile", "physical_hybrid_v1")

__all__ = [
    "ComponentDistance",
    "DistanceConfig",
    "SCORING_METHODS",
    "aggregate",
    "composition_distance",
    "illumination_distance",
    "load_config",
    "load_profile",
    "terrain_distance",
    "thermal_distance",
]
