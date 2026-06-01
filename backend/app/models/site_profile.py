"""
Pydantic models for Site Profile — Phase 191 Wave 1.

Building profile for onboarding gating. Used to confirm what "good" looks like
for a given building type before ML shadow mode starts.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ObjectiveWeights(BaseModel):
    """Cost vs comfort weighting for optimisation target."""

    cost: float = Field(0.5, ge=0.0, le=1.0)
    comfort: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("cost", "comfort", mode="after")
    @classmethod
    def _round_to_two_places(cls, v: float) -> float:
        return round(v, 2)


class OperatingSchedule(BaseModel):
    """Standard operating schedule for a building."""

    weekday_start: str = Field("08:00", pattern=r"^\d{2}:\d{2}$")
    weekday_end: str = Field("18:00", pattern=r"^\d{2}:\d{2}$")
    saturday_start: str | None = Field("09:00", pattern=r"^\d{2}:\d{2}$")
    saturday_end: str | None = Field("13:00", pattern=r"^\d{2}:\d{2}$")
    sunday_active: bool = False
    timezone: str = "Africa/Johannesburg"
    is_24_7: bool = False


class OnSiteGeneration(BaseModel):
    """On-site generation and storage capacity."""

    solar_kwp: float = Field(0.0, ge=0.0)
    bess_kwh: float = Field(0.0, ge=0.0)
    generator: bool = False


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


BUILDING_TYPES = ["commercial_office", "hospital", "retail", "mixed_use", "industrial", "residential"]
PRIMARY_OBJECTIVES = ["cost", "comfort", "compliance", "balanced"]
TARIFF_STRUCTURES = ["flat", "tou_megaflex", "tou_miniflex", "wheeling", "municipal"]
REGULATORY_FRAMEWORKS = ["SANS_10400_XA", "SANS_10400_T", "NRS_047", "NRS_048", "POPIA", "LEGIONELLA"]


class SiteProfileCreate(BaseModel):
    """Payload for creating or updating a site profile."""

    model_config = ConfigDict(str_strip_whitespace=True)

    building_type: str = Field(..., description="Building type")
    primary_objective: str = Field(..., description="Optimisation goal: cost | comfort | compliance | balanced")
    objective_weights: ObjectiveWeights = Field(
        default_factory=ObjectiveWeights,
        description="Relative weighting of cost vs comfort (must sum to 1.0 ± 0.01)",
    )
    operating_schedule: OperatingSchedule = Field(
        default_factory=OperatingSchedule,
        description="Standard operating hours and timezone",
    )
    tariff_structure: str = Field(
        default="flat",
        description="Electricity tariff type: flat | tou_megaflex | tou_miniflex | wheeling | municipal",
    )
    on_site_generation: OnSiteGeneration = Field(
        default_factory=OnSiteGeneration,
        description="Solar, BESS, and backup generation capacity",
    )
    temp_band_min_c: float = Field(19.0, ge=15.0, le=30.0)
    temp_band_max_c: float = Field(26.0, ge=15.0, le=30.0)
    clinical_zones_present: bool = Field(False, description="Hospital/clinical zones present")
    regulatory_frameworks: list[str] = Field(
        default=["SANS_10400_XA"],
        description="Applicable regulatory frameworks",
    )

    @field_validator("building_type")
    @classmethod
    def _validate_building_type(cls, v: str) -> str:
        if v not in BUILDING_TYPES:
            raise ValueError(f"building_type must be one of: {BUILDING_TYPES}")
        return v

    @field_validator("primary_objective")
    @classmethod
    def _validate_primary_objective(cls, v: str) -> str:
        if v not in PRIMARY_OBJECTIVES:
            raise ValueError(f"primary_objective must be one of: {PRIMARY_OBJECTIVES}")
        return v

    @field_validator("tariff_structure")
    @classmethod
    def _validate_tariff_structure(cls, v: str) -> str:
        if v not in TARIFF_STRUCTURES:
            raise ValueError(f"tariff_structure must be one of: {TARIFF_STRUCTURES}")
        return v

    @field_validator("regulatory_frameworks", mode="after")
    @classmethod
    def _validate_regulatory_frameworks(cls, v: list[str]) -> list[str]:
        for framework in v:
            if framework not in REGULATORY_FRAMEWORKS:
                raise ValueError(f"regulatory_framework '{framework}' not recognized: {REGULATORY_FRAMEWORKS}")
        return v

    @field_validator("objective_weights", mode="after")
    @classmethod
    def _validate_weights_sum(cls, v: ObjectiveWeights) -> ObjectiveWeights:
        total = round(v.cost + v.comfort, 2)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"objective_weights cost + comfort must sum to 1.0 (±0.01), got {total}")
        return v

    @field_validator("temp_band_max_c", mode="after")
    @classmethod
    def _validate_temp_band(cls, v: float, info) -> float:
        min_c = info.data.get("temp_band_min_c", 19.0)
        if v <= min_c:
            raise ValueError(f"temp_band_max_c ({v}) must be greater than temp_band_min_c ({min_c})")
        return v


class SiteProfileResponse(SiteProfileCreate):
    """Full site profile including server-generated fields."""

    id: str
    site_id: str
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    profile_version: int = 1
    created_at: datetime
    updated_at: datetime


class SiteProfileStatus(BaseModel):
    """Lightweight status response for gate checking."""

    site_id: str
    has_profile: bool
    confirmed_at: datetime | None = None
