"""
Zone Assessment Model
====================
Full assessment result for a comfort complaint at a desk.

Used by ZoneAssessmentService to produce a complete picture:
zone equipment health + contextual factors + gated recommendations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class EquipmentAlert:
    """Active alert on an equipment unit."""
    alert_id: str
    title: str
    severity: str  # "critical", "warning"
    message: str
    created_at: str


@dataclass
class EquipmentPrediction:
    """Active prediction on an equipment unit."""
    prediction_id: str
    severity: str  # "critical", "warning"
    prediction_type: str
    probability_percent: int
    timeframe_days: int | None
    description: str


@dataclass
class EquipmentStatus:
    """
    Health snapshot for one piece of equipment in a zone.

    One row per equipment (FCU, VAV, AHU, lighting controller, sensors).
    """
    equipment_id: str      # UUID from equipment.id
    code: str              # Equipment code e.g. "S002-FCU-L2-A"
    name: str
    type: str              # "fcu", "vav", "ahu", "lighting", "sensor"
    health_score: int      # 0-100
    status: str            # "normal", "warning", "critical", "fault", "off"
    alerts: list[EquipmentAlert] = field(default_factory=list)
    predictions: list[EquipmentPrediction] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return (
            self.status in ("critical", "fault")
            or bool(self.alerts)
            or bool(self.predictions)
        )

    @property
    def has_critical_issues(self) -> bool:
        return (
            self.status == "fault"
            or any(a.severity == "critical" for a in self.alerts)
            or any(p.severity == "critical" for p in self.predictions)
        )


@dataclass
class VAVLiveReadings:
    """Live VAV box readings from BMS."""
    vav_id: str
    damper_position: float | None      # 0-100 %
    airflow_actual: float | None       # L/s
    airflow_setpoint: float | None    # L/s
    discharge_temp: float | None       # °C
    reheat_valve: float | None         # 0-100 %
    has_stuck_damper: bool = False
    has_airflow_mismatch: bool = False
    has_reheat_conflict: bool = False


@dataclass
class Recommendation:
    """
    One recommended action for a complaint.

    can_supervised_adjust: True if phase is supervised or auto (shows "Request Approval" button)
    can_auto_adjust:       True if phase is auto (shows "Auto-adjust" button)
    """
    action: str           # Human-readable action e.g. "Lower FCU setpoint"
    equipment_code: str   # e.g. "S002-FCU-L2-A"
    parameter: str        # e.g. "temperature_setpoint"
    current_value: float | None
    suggested_value: float | None
    reason: str           # Why this helps
    can_supervised_adjust: bool = False
    can_auto_adjust: bool = False


ASSESSMENT_STATUSES = (
    "no_issues",          # All equipment healthy, no contextual factors
    "equipment_fault",    # Equipment has health/alert/prediction issues
    "contextual_factor",  # No equipment faults, but contextual factors present
    "combined",           # Both equipment faults and contextual factors
)


@dataclass
class ZoneAssessment:
    """
    Complete assessment for a comfort complaint at a specific desk/zone.

    Produced by ZoneAssessmentService.assess_zone().
    """
    # Identity
    zone_id: str
    zone_name: str
    desk_id: str
    desk_floor: str
    complaint_type: str          # "too_hot", "too_cold", "stuffy", "drafty", "noise"
    site_id: str                 # e.g. "site-002"

    # Equipment in this zone
    equipment_statuses: list[EquipmentStatus]

    # VAV live readings (from BMS)
    vav: VAVLiveReadings | None

    # Zone readings
    zone_temp: float
    zone_setpoint: float
    zone_status: str             # "running", "off", "fault", "unknown"
    occupancy_pct: float          # 0-100
    co2_level: float | None      # ppm
    lighting_level: float         # 0-100 % dim
    outdoor_temp: float | None    # °C — from AHU outdoor air temp sensor (telemetry)

    # Desk context
    near_window: bool
    near_diffuser: bool
    near_printer: bool
    orientation: str | None       # "N", "NE", "E", "SE", "S", "SW", "W", "NW"

    # Contextual factors (contributing but not faults)
    solar_factor: str | None          # "morning_sun", "afternoon_sun", "north_facing", None
    outdoor_extreme: bool             # outdoor_temp > 35°C or < 10°C
    low_occupancy: bool              # occupancy_pct < 20
    high_lighting_load: bool          # lighting_level > 70
    after_hours: bool                # outside building hours

    # Assessment result
    status: str                  # ASSESSMENT_STATUSES
    root_causes: list[str]
    confidence: str             # "high", "medium", "low"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Recommendations (gated by control module + phase)
    recommendations: list[Recommendation] = field(default_factory=list)
    control_module_active: bool = False
    phase: str = "shadow"       # "shadow", "advisory", "supervised", "auto"

    # Convenience properties
    @property
    def has_equipment_issues(self) -> bool:
        return any(eq.has_issues for eq in self.equipment_statuses)

    @property
    def has_critical_equipment_issues(self) -> bool:
        return any(eq.has_critical_issues for eq in self.equipment_statuses)

    @property
    def has_contextual_factors(self) -> bool:
        return bool(self.solar_factor or self.outdoor_extreme or self.low_occupancy
                    or self.high_lighting_load or self.after_hours)

    @property
    def equipment_healthy(self) -> list[EquipmentStatus]:
        return [eq for eq in self.equipment_statuses if not eq.has_issues]

    @property
    def equipment_with_issues(self) -> list[EquipmentStatus]:
        return [eq for eq in self.equipment_statuses if eq.has_issues]

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "desk_id": self.desk_id,
            "desk_floor": self.desk_floor,
            "complaint_type": self.complaint_type,
            "site_id": self.site_id,
            "status": self.status,
            "confidence": self.confidence,
            "root_causes": self.root_causes,
            "timestamp": self.timestamp,
            "zone_temp": self.zone_temp,
            "zone_setpoint": self.zone_setpoint,
            "zone_status": self.zone_status,
            "occupancy_pct": self.occupancy_pct,
            "co2_level": self.co2_level,
            "lighting_level": self.lighting_level,
            "outdoor_temp": self.outdoor_temp,
            "near_window": self.near_window,
            "near_diffuser": self.near_diffuser,
            "near_printer": self.near_printer,
            "orientation": self.orientation,
            "solar_factor": self.solar_factor,
            "outdoor_extreme": self.outdoor_extreme,
            "low_occupancy": self.low_occupancy,
            "high_lighting_load": self.high_lighting_load,
            "after_hours": self.after_hours,
            "control_module_active": self.control_module_active,
            "phase": self.phase,
            "recommendations": [
                {
                    "action": r.action,
                    "equipment_code": r.equipment_code,
                    "parameter": r.parameter,
                    "current_value": r.current_value,
                    "suggested_value": r.suggested_value,
                    "reason": r.reason,
                    "can_supervised_adjust": r.can_supervised_adjust,
                    "can_auto_adjust": r.can_auto_adjust,
                }
                for r in self.recommendations
            ],
            "equipment_statuses": [
                {
                    "equipment_id": eq.equipment_id,
                    "code": eq.code,
                    "name": eq.name,
                    "type": eq.type,
                    "health_score": eq.health_score,
                    "status": eq.status,
                    "has_issues": eq.has_issues,
                    "has_critical_issues": eq.has_critical_issues,
                    "alerts": [
                        {
                            "alert_id": a.alert_id,
                            "title": a.title,
                            "severity": a.severity,
                            "message": a.message,
                            "created_at": a.created_at,
                        }
                        for a in eq.alerts
                    ],
                    "predictions": [
                        {
                            "prediction_id": p.prediction_id,
                            "severity": p.severity,
                            "prediction_type": p.prediction_type,
                            "probability_percent": p.probability_percent,
                            "timeframe_days": p.timeframe_days,
                            "description": p.description,
                        }
                        for p in eq.predictions
                    ],
                }
                for eq in self.equipment_statuses
            ],
            "vav": (
                {
                    "vav_id": self.vav.vav_id,
                    "damper_position": self.vav.damper_position,
                    "airflow_actual": self.vav.airflow_actual,
                    "airflow_setpoint": self.vav.airflow_setpoint,
                    "discharge_temp": self.vav.discharge_temp,
                    "reheat_valve": self.vav.reheat_valve,
                    "has_stuck_damper": self.vav.has_stuck_damper,
                    "has_airflow_mismatch": self.vav.has_airflow_mismatch,
                    "has_reheat_conflict": self.vav.has_reheat_conflict,
                }
                if self.vav
                else None
            ),
        }
