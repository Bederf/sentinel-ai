from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SetbackFloor(BaseModel):
    """A floor where the building steps back or widens."""

    floor: int = Field(..., description="Floor index (0=ground)")
    ratio: float = Field(..., description="Width multiplier at this floor (0.0-1.0)")


class BuildingGeometry(BaseModel):
    """Geometry data extracted from a building photo for cockpit rendering."""

    floor_count: int = Field(..., description="Number of visible floors", ge=1, le=200)
    shape: str = Field(
        "rectangular",
        description="Building shape: rectangular, tower, L_shaped, stepped, courtyard",
    )
    setbacks: list[SetbackFloor] = Field(
        default_factory=list,
        description="Floors where the building steps back",
    )
    facade: str = Field("mixed", description="Facade material: glass, concrete, mixed")
    footprint_width_depth_ratio: float = Field(
        1.0,
        description="Width-to-depth ratio (>1.5=wide, 1.0=square, <0.7=narrow)",
        ge=0.3,
        le=5.0,
    )
    roof_equipment: bool = Field(
        False,
        description="Whether cooling towers/antennas are visible on roof",
    )
    source: str = Field("claude_vision", description="How geometry was obtained")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BuildingGeometry:
        return cls(**data)
