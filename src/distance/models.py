"""Typed result of one component distance for one candidate (used for explainability output)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ComponentDistance:
    name: str
    raw_difference: float | None
    normalized_distance: float | None
    weight_requested: float
    weight_applied: float
    status: str
    method: str
    diagnostics: dict[str, float | str | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
