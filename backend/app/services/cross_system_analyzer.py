"""
Cross-System Analyzer
=====================
Combines HVAC (Desigo) + Lighting (Scenecom) + Occupancy data
for intelligent comfort diagnostics.

Data Sources:
- HVAC: zones.json via BuildingDataLoader (zone temps, setpoints, FCU/VAV/AHU)
- Lighting: dali_mock_data.json via DALIService (lux, occupancy, luminaires)
- Desks: desks.json via BuildingDataLoader (desk context: near_window, etc.)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import asyncio

from app.services.dali_service import get_dali_service
from app.services.building_loader import get_building_loader

logger = logging.getLogger(__name__)
from app.models.dali import ZoneOccupancy, ZoneLighting


def _get_device_manager():
    """Lazy import to avoid circular dependency."""
    from app.services.device_abstraction import device_manager
    return device_manager


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

    # VAV device data (from Desigo via mock_devices)
    vav_id: Optional[str] = None
    vav_damper_position: Optional[float] = None
    vav_airflow_actual: Optional[float] = None
    vav_airflow_setpoint: Optional[float] = None
    vav_discharge_temp: Optional[float] = None
    vav_reheat_valve: Optional[float] = None
    vav_analysis: Optional[str] = None

    # Lighting/Occupancy data
    occupancy_percent: float = 0.0
    occupied_sensors: int = 0
    total_sensors: int = 0
    daylight_lux: float = 0.0
    max_lux: float = 0.0
    lighting_level: float = 0.0
    lighting_analysis: str = ""

    # Combined diagnosis
    root_cause: str = ""
    confidence: str = "low"  # 'high', 'medium', 'low'
    suggestions: List[str] = None

    # Desk-specific (if complaint from specific location)
    desk_id: Optional[str] = None
    desk_sensor: Optional[str] = None
    desk_occupied: Optional[bool] = None
    desk_lux: Optional[float] = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class CrossSystemAnalyzer:
    """Analyzes comfort issues using combined HVAC + Lighting data"""

    def __init__(self):
        self.dali = get_dali_service()
        self._building_loader = get_building_loader()
        self._hvac_data: Dict[str, Dict] = {}
        self._load_hvac_from_zones()

    def _load_hvac_from_zones(self) -> None:
        """Load HVAC zone data from building loader (zones.json files)."""
        all_zones = self._building_loader.get_all_zones()

        for zone in all_zones:
            zone_id = zone.get("zone_id")
            if zone_id:
                self._hvac_data[zone_id] = {
                    "temp": zone.get("current_temp", 22.0),
                    "setpoint": zone.get("setpoint", 22.0),
                    "status": zone.get("status", "running"),
                    "fcu": zone.get("fcu_id", ""),
                    "vav": zone.get("vav_id"),
                    "ahu": zone.get("ahu_id"),
                    "zone_name": zone.get("zone_name", zone_id),
                    "floor": zone.get("floor", ""),
                    "building_id": zone.get("building_id", ""),
                }

        logger.info(f"Loaded HVAC data for {len(self._hvac_data)} zones from building loader")

    def refresh_hvac_data(self) -> None:
        """Refresh HVAC data from building loader (call after zone updates)."""
        self._building_loader.load(force=True)
        self._load_hvac_from_zones()

    def _get_vav_data(self, vav_id: str) -> Dict[str, Any]:
        """
        Fetch VAV device data from DeviceManager (Desigo simulation).

        Returns dict with damper_position, airflow_actual, airflow_setpoint,
        discharge_air_temp, heating_valve.
        """
        if not vav_id:
            return {}

        try:
            dm = _get_device_manager()
            if dm is None:
                logger.warning("DeviceManager not available")
                return {}

            # Get device (sync wrapper around async)
            loop = asyncio.new_event_loop()
            try:
                device = loop.run_until_complete(dm.get_device(vav_id))
            finally:
                loop.close()

            if not device:
                logger.warning(f"VAV device {vav_id} not found")
                return {}

            # Extract point values
            points = device.points or {}
            vav_data = {
                "vav_id": vav_id,
                "damper_position": self._get_point_value(points, "damper_position"),
                "airflow_actual": self._get_point_value(points, "airflow_actual"),
                "airflow_setpoint": self._get_point_value(points, "airflow_setpoint"),
                "discharge_temp": self._get_point_value(points, "discharge_air_temp"),
                "reheat_valve": self._get_point_value(points, "heating_valve"),
            }

            logger.debug(f"VAV data for {vav_id}: {vav_data}")
            return vav_data

        except Exception as e:
            logger.error(f"Error fetching VAV data for {vav_id}: {e}")
            return {}

    def _get_point_value(self, points: Dict, point_name: str) -> Optional[float]:
        """Extract point value from device points dict."""
        point = points.get(point_name)
        if point is None:
            return None
        # Handle both DevicePoint objects and dicts
        if hasattr(point, 'value'):
            return point.value
        elif hasattr(point, 'default_value'):
            return point.default_value
        elif isinstance(point, dict):
            return point.get('value') or point.get('default_value')
        return None

    def _analyze_vav(self, vav_data: Dict, complaint_type: str) -> str:
        """Analyze VAV contribution to comfort issue."""
        if not vav_data:
            return "VAV data not available"

        damper = vav_data.get("damper_position")
        airflow = vav_data.get("airflow_actual")
        setpoint = vav_data.get("airflow_setpoint")
        discharge = vav_data.get("discharge_temp")
        reheat = vav_data.get("reheat_valve")

        issues = []

        if damper is not None:
            if damper > 80:
                issues.append(f"Damper WIDE OPEN at {damper:.0f}% - possible stuck damper")
            elif damper < 20:
                issues.append(f"Damper nearly CLOSED at {damper:.0f}% - insufficient airflow")

        if airflow is not None and setpoint is not None:
            diff = airflow - setpoint
            if abs(diff) > 50:
                issues.append(f"Airflow mismatch: {airflow:.0f} L/s vs {setpoint:.0f} L/s setpoint")

        if discharge is not None:
            if complaint_type == "too_cold" and discharge < 16:
                issues.append(f"Discharge air COLD at {discharge:.1f}°C")
            elif complaint_type == "too_hot" and discharge > 20:
                issues.append(f"Discharge air WARM at {discharge:.1f}°C")

        if reheat is not None:
            if complaint_type == "too_cold" and reheat == 0:
                issues.append("Reheat valve CLOSED - no reheat active")
            elif complaint_type == "too_hot" and reheat > 50:
                issues.append(f"Reheat valve at {reheat:.0f}% - adding heat")

        if issues:
            return " | ".join(issues)

        return f"VAV operating normally: damper {damper:.0f}%, airflow {airflow:.0f} L/s, discharge {discharge:.1f}°C"

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
        hvac = self._hvac_data.get(zone_id, {"temp": 22.0, "setpoint": 22.0, "status": "unknown"})

        # Get VAV device data (Desigo simulation)
        vav_id = hvac.get("vav")
        vav_data = self._get_vav_data(vav_id) if vav_id else {}

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

        # Analyze VAV (Desigo device data)
        vav_analysis = self._analyze_vav(vav_data, complaint_type) if vav_data else None

        # Analyze Lighting/Occupancy
        lighting_analysis = self._analyze_lighting(occupancy, lighting, complaint_type, desk_data)

        # Determine root cause (now including VAV data)
        root_cause, confidence, suggestions = self._determine_root_cause(
            hvac, occupancy, lighting, complaint_type, desk_data, vav_data
        )

        return ComfortDiagnosis(
            zone_id=zone_id,
            zone_name=occupancy.zone_name if occupancy else zone_id,
            complaint_type=complaint_type,
            hvac_temp=hvac["temp"],
            hvac_setpoint=hvac["setpoint"],
            hvac_status=hvac["status"],
            hvac_analysis=hvac_analysis,
            vav_id=vav_id,
            vav_damper_position=vav_data.get("damper_position"),
            vav_airflow_actual=vav_data.get("airflow_actual"),
            vav_airflow_setpoint=vav_data.get("airflow_setpoint"),
            vav_discharge_temp=vav_data.get("discharge_temp"),
            vav_reheat_valve=vav_data.get("reheat_valve"),
            vav_analysis=vav_analysis,
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
        desk_data: Dict,
        vav_data: Dict = None
    ) -> tuple[str, str, List[str]]:
        """Determine most likely root cause and suggestions (includes VAV analysis)"""

        suggestions = []
        vav_data = vav_data or {}

        # Check for HVAC fault first
        if hvac["status"] == "fault":
            return (
                "HVAC equipment fault - FCU not operating correctly",
                "high",
                ["Create maintenance job for FCU inspection", "Check BMS alarms for fault codes"]
            )

        # ==========================================
        # VAV-specific fault detection (Desigo)
        # ==========================================
        damper = vav_data.get("damper_position")
        airflow = vav_data.get("airflow_actual")
        setpoint = vav_data.get("airflow_setpoint")
        discharge = vav_data.get("discharge_temp")
        reheat = vav_data.get("reheat_valve")

        # Stuck damper detection (damper wide open but still too hot/cold)
        if damper is not None and damper > 90:
            if complaint_type == "too_hot":
                return (
                    f"VAV damper STUCK OPEN at {damper:.0f}% - unable to reduce cooling airflow. "
                    f"Discharge air at {discharge:.1f}°C is overcooling the space.",
                    "high",
                    [
                        f"Dispatch technician to inspect VAV {vav_data.get('vav_id')} actuator",
                        "Check BMS alarms for damper position feedback",
                        "Temporarily override damper to 50% if safe"
                    ]
                )
            elif complaint_type == "too_cold" and discharge and discharge < 16:
                return (
                    f"VAV damper WIDE OPEN at {damper:.0f}% delivering COLD air at {discharge:.1f}°C. "
                    f"Likely stuck actuator or control loop issue.",
                    "high",
                    [
                        f"Dispatch technician to inspect VAV {vav_data.get('vav_id')} actuator",
                        "Override damper to reduce airflow",
                        "Check reheat valve operation"
                    ]
                )

        # Reheat valve not responding (too cold with reheat at 0%)
        if complaint_type == "too_cold" and reheat is not None and reheat == 0:
            if discharge and discharge < 18:
                return (
                    f"Zone too cold: Discharge air at {discharge:.1f}°C with reheat valve CLOSED (0%). "
                    f"Reheat system not activating despite demand.",
                    "high",
                    [
                        f"Check reheat coil valve actuator on VAV {vav_data.get('vav_id')}",
                        "Verify hot water supply to reheat coil",
                        "Check BMS heating demand signal"
                    ]
                )

        # Reheat fighting cooling (too hot with reheat active)
        if complaint_type == "too_hot" and reheat is not None and reheat > 30:
            return (
                f"Reheat valve at {reheat:.0f}% while zone is too hot! "
                f"Control conflict - heating and cooling fighting each other.",
                "high",
                [
                    f"Close reheat valve on VAV {vav_data.get('vav_id')}",
                    "Review BMS control sequence for deadband settings",
                    "Check zone temperature sensor calibration"
                ]
            )

        # Airflow mismatch (VAV not delivering requested airflow)
        if airflow is not None and setpoint is not None:
            airflow_diff = airflow - setpoint
            if abs(airflow_diff) > 100:  # >100 L/s difference
                direction = "excess" if airflow_diff > 0 else "insufficient"
                return (
                    f"VAV airflow mismatch: delivering {airflow:.0f} L/s vs {setpoint:.0f} L/s setpoint "
                    f"({direction} airflow). Damper at {damper:.0f}%.",
                    "medium",
                    [
                        "Check VAV pressure sensor calibration",
                        "Verify damper actuator operation",
                        "Review AHU static pressure"
                    ]
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
                suggestions = []

                # Suggest dimming lights to reduce heat load (actual DALI control)
                if lighting and lighting.avg_dim_level > 50:
                    suggestions.append(f"Dim zone lighting from {lighting.avg_dim_level:.0f}% to 30% to reduce heat load")

                # Suggest FCU setpoint adjustment (actual HVAC control)
                suggestions.append(f"Boost FCU cooling: lower setpoint from {hvac['setpoint']}°C to {hvac['setpoint'] - 2}°C for 2 hours")

                # Suggest VAV adjustment with specific data if available
                if damper is not None:
                    if damper < 80:
                        suggestions.append(f"Increase VAV damper from {damper:.0f}% to 100% to boost airflow")
                    else:
                        suggestions.append(f"VAV damper already at {damper:.0f}% - maximum airflow")
                else:
                    suggestions.append("Increase VAV airflow to desk area")

                if occupancy and occupancy.occupancy_percent < 30:
                    suggestions.append("Note: Zone is only {:.0f}% occupied - less internal heat load".format(occupancy.occupancy_percent))
                return (cause, confidence, suggestions)

        # Low occupancy with high cooling demand
        if occupancy and occupancy.occupancy_percent < 20 and complaint_type == "too_hot":
            low_occ_suggestions = ["Consider temporary setpoint adjustment"]
            if damper is not None:
                low_occ_suggestions.insert(0, f"VAV damper at {damper:.0f}% - check if appropriate for low occupancy")
            else:
                low_occ_suggestions.insert(0, "Check VAV box positions in unoccupied areas")
            return (
                "Low zone occupancy ({:.0f}%) means less internal heat load, but may also indicate poor air circulation in unoccupied areas".format(
                    occupancy.occupancy_percent),
                "medium",
                low_occ_suggestions
            )

        # Generic HVAC issue
        if complaint_type == "too_hot" and hvac["temp"] > hvac["setpoint"] + 1:
            hvac_suggestions = [
                "Check chilled water supply temperature",
                "Verify FCU fan speed and valve position",
                "Review zone load vs equipment capacity"
            ]
            # Add VAV-specific context if available
            if damper is not None and airflow is not None:
                hvac_suggestions.insert(0, f"VAV status: damper {damper:.0f}%, airflow {airflow:.0f} L/s, discharge {discharge:.1f}°C")
            return (
                f"Zone temperature ({hvac['temp']}C) exceeds setpoint ({hvac['setpoint']}C). HVAC may be undersized or have reduced capacity.",
                "medium",
                hvac_suggestions
            )

        # Default - suggest actions on actual BMS assets
        default_suggestions = []

        # Include VAV status summary if available
        if damper is not None:
            default_suggestions.append(
                f"VAV status: damper {damper:.0f}%, "
                f"airflow {airflow:.0f} L/s" + (f", discharge {discharge:.1f}°C" if discharge else "")
            )

        if lighting and lighting.avg_dim_level > 60:
            default_suggestions.append(f"Reduce zone lighting from {lighting.avg_dim_level:.0f}% to 50%")
        default_suggestions.append(f"Lower FCU setpoint by 1°C (current: {hvac['setpoint']}°C)")
        default_suggestions.append("Dispatch technician to check for localized heat sources")

        return (
            "No clear equipment issue detected. May be localized discomfort or perception.",
            "low",
            default_suggestions
        )

    def get_zone_context_for_chat(self, zone_id: str) -> str:
        """Get formatted zone context for AI chat (includes VAV data from Desigo)"""
        occupancy = self.dali.get_zone_occupancy(zone_id)
        lighting = self.dali.get_zone_lighting(zone_id)
        hvac = self._hvac_data.get(zone_id, {})

        lines = [f"## Zone: {zone_id}"]

        if hvac:
            lines.append(f"**HVAC:** {hvac.get('temp', 'N/A')}C (setpoint {hvac.get('setpoint', 'N/A')}C), status: {hvac.get('status', 'unknown')}")

            # Include VAV data from Desigo simulation
            vav_id = hvac.get("vav")
            if vav_id:
                vav_data = self._get_vav_data(vav_id)
                if vav_data:
                    damper = vav_data.get("damper_position")
                    airflow = vav_data.get("airflow_actual")
                    discharge = vav_data.get("discharge_temp")
                    reheat = vav_data.get("reheat_valve")
                    vav_parts = [f"VAV {vav_id}:"]
                    if damper is not None:
                        vav_parts.append(f"damper {damper:.0f}%")
                    if airflow is not None:
                        vav_parts.append(f"airflow {airflow:.0f} L/s")
                    if discharge is not None:
                        vav_parts.append(f"discharge {discharge:.1f}°C")
                    if reheat is not None:
                        vav_parts.append(f"reheat {reheat:.0f}%")
                    lines.append(f"**VAV:** {' | '.join(vav_parts)}")

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
