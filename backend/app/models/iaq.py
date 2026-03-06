"""Indoor Air Quality models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class IAQReading(BaseModel):
    """Raw IAQ sensor readings for a zone."""

    co2_ppm: Optional[float] = None
    humidity_percent: Optional[float] = None
    temperature_c: Optional[float] = None
    setpoint_c: Optional[float] = None
    voc_ppb: Optional[float] = None
    pm25_ugm3: Optional[float] = None


class IAQComponentScore(BaseModel):
    """Score for a single IAQ component (0-100)."""

    component: str
    value: Optional[float] = None
    score: float
    weight: float
    status: str  # excellent, good, poor, unhealthy
    unit: str = ""
    threshold_info: str = ""


class IAQZoneScore(BaseModel):
    """IAQ score for a single zone."""

    zone_id: str
    zone_name: str
    floor: str
    site_id: str
    iaq_score: float = Field(..., ge=0, le=100)
    status: str  # excellent, good, poor, unhealthy
    components: List[IAQComponentScore]
    alerts: List[str] = []
    occupancy: Optional[int] = None
    area_sqm: Optional[float] = None


class IAQAlert(BaseModel):
    """An IAQ threshold alert."""

    zone_id: str
    zone_name: str
    floor: str
    site_id: str
    alert_type: str  # co2_high, humidity_high, temp_deviation, voc_high, pm25_high
    severity: str  # warning, critical
    message: str
    current_value: float
    threshold: float
    unit: str


class IAQSiteOverview(BaseModel):
    """IAQ overview for an entire site."""

    site_id: str
    total_zones: int
    avg_iaq_score: float
    zones_excellent: int
    zones_good: int
    zones_poor: int
    zones_unhealthy: int
    zones: List[IAQZoneScore]
    alerts: List[IAQAlert]


class IAQComplianceReport(BaseModel):
    """IAQ compliance report for WELL/ESG."""

    site_id: str
    report_type: str  # well, esg
    generated_at: str
    overall_score: float
    zones_compliant: int
    zones_non_compliant: int
    metrics: dict
    recommendations: List[str]
