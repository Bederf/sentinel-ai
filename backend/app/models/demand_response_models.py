"""Demand Response Pydantic models for curtailable load API.

These models define the request/response schema for the demand response endpoint
used by BESS controllers and demand response aggregators.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ZoneCurtailableLoad(BaseModel):
    """Per-zone curtailable load breakdown."""

    zone_id: str = Field(..., description="Zone identifier")
    zone_name: str = Field(..., description="Human-readable zone name")
    priority: int = Field(..., ge=1, le=5, description="Zone priority (1=critical, 5=lowest)")
    curtailable_kw: float = Field(..., ge=0, description="Estimated curtailable load in kW")
    current_temp_c: float | None = Field(None, description="Current zone temperature in Celsius")
    setpoint_c: float | None = Field(None, description="Zone temperature setpoint in Celsius")
    headroom_c: float | None = Field(None, description="Temperature headroom before comfort boundary")
    equipment_count: int = Field(..., ge=0, description="Number of HVAC equipment in zone")


class CurtailableLoadResponse(BaseModel):
    """Response model for curtailable load endpoint.

    Provides real-time signal for how much HVAC load can be safely curtailed,
    for how long, and with what confidence. Compatible with Eskom DDMP requirements.
    """

    site_id: str = Field(..., description="Sentinel site ID")
    timestamp: datetime = Field(..., description="UTC timestamp of calculation")
    curtailable_load_kw: float = Field(..., ge=0, description="Total curtailable HVAC load in kW")
    safe_duration_minutes: int = Field(..., ge=0, description="Minutes until comfort breach")
    confidence: float = Field(..., ge=0.0, le=0.95, description="Confidence score (0.0-0.95)")
    limiting_factor: str = Field(
        ...,
        description="Primary constraint on curtailment (chiller_thermal_mass, comfort_boundary, bess_low_soc, zone_temperature_limit, thermal_runway_short, none)",
    )
    eskom_stage: int | None = Field(None, description="Current Eskom load shedding stage (0-8)")
    is_load_shedding_active: bool = Field(..., description="Whether load shedding is currently active")
    ddmp_eligible: bool = Field(..., description="Whether site meets DDMP minimum requirements")
    bess_soc_pct: float | None = Field(None, ge=0, le=100, description="BESS state of charge percentage")
    zone_breakdown: list[ZoneCurtailableLoad] = Field(
        default_factory=list, description="Per-zone curtailable load details"
    )
    data_freshness_seconds: int = Field(..., ge=0, description="Seconds since last sensor reading")
    calculation_method: str = Field(
        default="thermal_runway_zone_priority", description="Algorithm used for calculation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "site-002",
                "timestamp": "2026-05-18T17:45:00Z",
                "curtailable_load_kw": 142.0,
                "safe_duration_minutes": 95,
                "confidence": 0.82,
                "limiting_factor": "chiller_thermal_mass",
                "eskom_stage": 2,
                "is_load_shedding_active": False,
                "ddmp_eligible": True,
                "bess_soc_pct": 78.4,
                "zone_breakdown": [
                    {
                        "zone_id": "L0-A",
                        "zone_name": "Ground Floor Zone A",
                        "priority": 3,
                        "curtailable_kw": 28.4,
                        "current_temp_c": 21.8,
                        "setpoint_c": 22.0,
                        "headroom_c": 2.2,
                        "equipment_count": 4,
                    }
                ],
                "data_freshness_seconds": 45,
                "calculation_method": "thermal_runway_zone_priority",
            }
        }
