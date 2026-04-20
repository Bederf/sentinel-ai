"""Indoor Air Quality models."""


from pydantic import BaseModel, Field


class IAQReading(BaseModel):
    """Raw IAQ sensor readings for a zone."""

    co2_ppm: float | None = None
    humidity_percent: float | None = None
    temperature_c: float | None = None
    setpoint_c: float | None = None
    voc_ppb: float | None = None
    pm25_ugm3: float | None = None


class IAQComponentScore(BaseModel):
    """Score for a single IAQ component (0-100)."""

    component: str
    value: float | None = None
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
    components: list[IAQComponentScore]
    alerts: list[str] = []
    occupancy: int | None = None
    area_sqm: float | None = None


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
    zones: list[IAQZoneScore]
    alerts: list[IAQAlert]


class IAQComplianceReport(BaseModel):
    """IAQ compliance report for WELL/ESG."""

    site_id: str
    report_type: str  # well, esg
    generated_at: str
    overall_score: float
    zones_compliant: int
    zones_non_compliant: int
    metrics: dict
    recommendations: list[str]
