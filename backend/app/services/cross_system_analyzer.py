"""
Cross-System Analyzer
=====================
Combines HVAC (Desigo) + Lighting (Scenecom) + Occupancy data
for intelligent comfort diagnostics.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

from app.services.dali_service import get_dali_service

logger = logging.getLogger(__name__)
from app.models.dali import ZoneOccupancy, ZoneLighting


@dataclass
class ComfortDiagnosis:
    """Result of comfort analysis combining HVAC + Lighting data"""
    zone_id: str
    zone_name: str
    complaint_type: str  # 'too_hot', 'too_cold', 'too_dark', etc.

    # HVAC data
    hvac_temp: float
    hvac_setpoint: float
    hvac_status: str  # 'running', 'off', 'fault'
    hvac_analysis: str

    # Lighting/Occupancy data
    occupancy_percent: float
    occupied_sensors: int
    total_sensors: int
    daylight_lux: float
    max_lux: float
    lighting_level: float
    lighting_analysis: str

    # Combined diagnosis
    root_cause: str
    confidence: str  # 'high', 'medium', 'low'
    suggestions: List[str]

    # Desk-specific (if complaint from specific location)
    desk_id: Optional[str] = None
    desk_sensor: Optional[str] = None
    desk_occupied: Optional[bool] = None
    desk_lux: Optional[float] = None


class CrossSystemAnalyzer:
    """Analyzes comfort issues using combined HVAC + Lighting data"""

    def __init__(self):
        self.dali = get_dali_service()
        # Would also inject HVAC service in production
        self._mock_hvac_data = self._load_mock_hvac()

    def _load_mock_hvac(self) -> Dict:
        """Load mock HVAC zone data (simplified for demo)"""
        return {
            "Zone-L12-N": {"temp": 22.5, "setpoint": 22.0, "status": "running", "fcu": "FCU-L12-03"},
            "Zone-L12-S": {"temp": 23.0, "setpoint": 22.0, "status": "running", "fcu": "FCU-L12-04"},
            "Zone-L11-N": {"temp": 21.5, "setpoint": 22.0, "status": "running", "fcu": "FCU-L11-01"},
            "Zone-L11-S": {"temp": 24.0, "setpoint": 22.0, "status": "fault", "fcu": "FCU-L11-02"},
            "Zone-L10-N": {"temp": 22.0, "setpoint": 22.0, "status": "running", "fcu": "FCU-L10-01"},
        }

    def analyze_comfort_complaint(
        self,
        zone_id: str,
        complaint_type: str = "too_hot",
        desk_id: Optional[str] = None
    ) -> ComfortDiagnosis:
        """
        Analyze a comfort complaint using HVAC + Lighting + Occupancy data.

        This is the hero use case: "Too hot at Desk 25" gets intelligent diagnosis.
        """
        # Get zone data
        occupancy = self.dali.get_zone_occupancy(zone_id)
        lighting = self.dali.get_zone_lighting(zone_id)
        hvac = self._mock_hvac_data.get(zone_id, {"temp": 22.0, "setpoint": 22.0, "status": "unknown"})

        # Desk-specific data if provided
        desk_sensor = None
        desk_data = {}
        if desk_id:
            desk_sensor = self.dali.get_sensor_by_desk(desk_id)
            if desk_sensor:
                desk_data = {
                    "desk_id": desk_id,
                    "desk_sensor": desk_sensor.sensor_id,
                    "desk_occupied": desk_sensor.occupancy,
                    "desk_lux": desk_sensor.lux_level
                }

        # Analyze HVAC
        hvac_analysis = self._analyze_hvac(hvac, complaint_type)

        # Analyze Lighting/Occupancy
        lighting_analysis = self._analyze_lighting(occupancy, lighting, complaint_type, desk_data)

        # Determine root cause
        root_cause, confidence, suggestions = self._determine_root_cause(
            hvac, occupancy, lighting, complaint_type, desk_data
        )

        return ComfortDiagnosis(
            zone_id=zone_id,
            zone_name=occupancy.zone_name if occupancy else zone_id,
            complaint_type=complaint_type,
            hvac_temp=hvac["temp"],
            hvac_setpoint=hvac["setpoint"],
            hvac_status=hvac["status"],
            hvac_analysis=hvac_analysis,
            occupancy_percent=occupancy.occupancy_percent if occupancy else 0,
            occupied_sensors=occupancy.occupied_sensors if occupancy else 0,
            total_sensors=occupancy.total_sensors if occupancy else 0,
            daylight_lux=occupancy.avg_lux_level if occupancy else 0,
            max_lux=occupancy.max_lux_level if occupancy else 0,
            lighting_level=lighting.avg_dim_level if lighting else 0,
            lighting_analysis=lighting_analysis,
            root_cause=root_cause,
            confidence=confidence,
            suggestions=suggestions,
            **desk_data
        )

    def _analyze_hvac(self, hvac: Dict, complaint_type: str) -> str:
        """Analyze HVAC contribution to comfort issue"""
        temp = hvac["temp"]
        setpoint = hvac["setpoint"]
        status = hvac["status"]

        if status == "fault":
            return f"HVAC FAULT detected. FCU may not be operating correctly."
        elif status == "off":
            return f"HVAC is OFF. Zone temperature uncontrolled."

        diff = temp - setpoint
        if complaint_type == "too_hot":
            if diff > 1.5:
                return f"Zone is {diff:.1f}C above setpoint. HVAC struggling to maintain."
            elif diff > 0.5:
                return f"Zone is slightly warm ({temp}C vs {setpoint}C setpoint), but within tolerance."
            else:
                return f"HVAC is maintaining setpoint correctly ({temp}C)."
        elif complaint_type == "too_cold":
            if diff < -1.5:
                return f"Zone is {abs(diff):.1f}C below setpoint. Possible overcooling."
            else:
                return f"Zone temperature ({temp}C) is at or near setpoint ({setpoint}C)."

        return f"Zone at {temp}C (setpoint {setpoint}C), status: {status}"

    def _analyze_lighting(
        self,
        occupancy: Optional[ZoneOccupancy],
        lighting: Optional[ZoneLighting],
        complaint_type: str,
        desk_data: Dict
    ) -> str:
        """Analyze lighting/occupancy contribution"""
        parts = []

        if occupancy:
            parts.append(f"Zone occupancy: {occupancy.occupancy_percent:.0f}% ({occupancy.occupied_sensors}/{occupancy.total_sensors} sensors)")

            if occupancy.max_lux_level > 800:
                parts.append(f"HIGH DAYLIGHT detected ({occupancy.max_lux_level:.0f} lux max) - possible solar heat gain")
            elif occupancy.avg_lux_level > 500:
                parts.append(f"Moderate daylight ({occupancy.avg_lux_level:.0f} lux avg)")
            else:
                parts.append(f"Low daylight ({occupancy.avg_lux_level:.0f} lux)")

        if desk_data.get("desk_lux"):
            if desk_data["desk_lux"] > 800:
                parts.append(f"YOUR LOCATION shows {desk_data['desk_lux']:.0f} lux (very bright - direct sun exposure)")

        if lighting:
            parts.append(f"Lights at {lighting.avg_dim_level:.0f}% average dim level")
            if lighting.faulty_count > 0:
                parts.append(f"{lighting.faulty_count} faulty luminaires in zone")

        return " | ".join(parts) if parts else "No lighting data available"

    def _determine_root_cause(
        self,
        hvac: Dict,
        occupancy: Optional[ZoneOccupancy],
        lighting: Optional[ZoneLighting],
        complaint_type: str,
        desk_data: Dict
    ) -> tuple[str, str, List[str]]:
        """Determine most likely root cause and suggestions"""

        suggestions = []

        # Check for HVAC fault first
        if hvac["status"] == "fault":
            return (
                "HVAC equipment fault - FCU not operating correctly",
                "high",
                ["Create maintenance job for FCU inspection", "Check BMS alarms for fault codes"]
            )

        # Solar heat gain scenario (the hero demo case)
        desk_lux = desk_data.get("desk_lux", 0)
        max_lux = occupancy.max_lux_level if occupancy else 0

        if complaint_type == "too_hot" and (desk_lux > 800 or max_lux > 800):
            # High daylight = solar heat gain likely
            if hvac["temp"] <= hvac["setpoint"] + 0.5:
                # HVAC is fine, solar is the issue
                cause = "Solar heat gain from windows. HVAC is working correctly but direct sunlight is warming your location."
                confidence = "high"
                suggestions = [
                    "Close blinds or activate automated shading",
                    f"Temporarily boost cooling to {hvac['setpoint'] - 2}C for 2 hours",
                    "Consider relocating to a shaded desk"
                ]
                if occupancy and occupancy.occupancy_percent < 30:
                    suggestions.append("Note: Zone is only {:.0f}% occupied - less internal heat load".format(occupancy.occupancy_percent))
                return (cause, confidence, suggestions)

        # Low occupancy with high cooling demand
        if occupancy and occupancy.occupancy_percent < 20 and complaint_type == "too_hot":
            return (
                "Low zone occupancy ({:.0f}%) means less internal heat load, but may also indicate poor air circulation in unoccupied areas".format(
                    occupancy.occupancy_percent),
                "medium",
                ["Check VAV box positions in unoccupied areas", "Consider temporary setpoint adjustment"]
            )

        # Generic HVAC issue
        if complaint_type == "too_hot" and hvac["temp"] > hvac["setpoint"] + 1:
            return (
                f"Zone temperature ({hvac['temp']}C) exceeds setpoint ({hvac['setpoint']}C). HVAC may be undersized or have reduced capacity.",
                "medium",
                ["Check chilled water supply temperature", "Verify FCU fan speed and valve position", "Review zone load vs equipment capacity"]
            )

        # Default
        return (
            "No clear equipment issue detected. May be localized discomfort or perception.",
            "low",
            ["Check for localized heat sources (equipment, sun exposure)", "Consider desk fan or temporary relocation"]
        )

    def get_zone_context_for_chat(self, zone_id: str) -> str:
        """Get formatted zone context for AI chat"""
        occupancy = self.dali.get_zone_occupancy(zone_id)
        lighting = self.dali.get_zone_lighting(zone_id)
        hvac = self._mock_hvac_data.get(zone_id, {})

        lines = [f"## Zone: {zone_id}"]

        if hvac:
            lines.append(f"**HVAC:** {hvac.get('temp', 'N/A')}C (setpoint {hvac.get('setpoint', 'N/A')}C), status: {hvac.get('status', 'unknown')}")

        if occupancy:
            lines.append(f"**Occupancy:** {occupancy.occupancy_percent:.0f}% ({occupancy.occupied_sensors}/{occupancy.total_sensors} sensors)")
            lines.append(f"**Daylight:** {occupancy.avg_lux_level:.0f} lux avg, {occupancy.max_lux_level:.0f} lux max")

        if lighting:
            lines.append(f"**Lighting:** {lighting.avg_dim_level:.0f}% dim level, {lighting.total_power_w:.0f}W total")
            if lighting.faulty_count > 0:
                lines.append(f"**Faults:** {lighting.faulty_count} faulty luminaires")

        return "\n".join(lines)


# Singleton
_analyzer: Optional[CrossSystemAnalyzer] = None

def get_cross_system_analyzer() -> CrossSystemAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = CrossSystemAnalyzer()
    return _analyzer
