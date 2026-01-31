"""Zone diagnostics service for BMS alerts.

Analyzes zone equipment to determine root cause of comfort issues.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class FaultType(Enum):
    FCU_VALVE_STUCK = "fcu_valve_stuck"
    FCU_FAN_FAILURE = "fcu_fan_failure"
    VAV_DAMPER_STUCK = "vav_damper_stuck"
    AHU_SUPPLY_HIGH = "ahu_supply_high"
    SENSOR_FAULT = "sensor_fault"
    HIGH_OCCUPANCY = "high_occupancy"
    CHILLER_ISSUE = "chiller_issue"
    UNKNOWN = "unknown"


@dataclass
class DiagnosticResult:
    zone_id: str
    current_temp: float
    setpoint: float
    deviation: float
    fault_type: FaultType
    faulty_equipment: str
    fault_code: Optional[str]
    fault_description: str
    equipment_status: Dict[str, Dict]
    recommended_actions: List[str]
    parts_required: List[str]
    estimated_repair_hours: float
    severity: str  # critical, warning, info


class ZoneDiagnostics:
    """Diagnose zone comfort issues by analyzing equipment chain."""

    def __init__(self, supabase_client):
        self.client = supabase_client

    def get_zone_equipment(self, zone_id: str) -> Dict[str, str]:
        """Get equipment codes for a zone."""
        # Parse zone_id like "Zone-L10-C"
        parts = zone_id.split("-")
        floor = parts[1]  # L10
        zone = parts[2]   # C
        zone_num = ord(zone) - ord('A') + 1  # A=1, B=2, etc.

        return {
            "fcu": f"FCU-{floor}-0{zone_num}",
            "vav": f"VAV-{floor}-0{zone_num}",
            "ahu": f"AHU-{floor}-01",
            "temp_sensor": f"TS-{floor}-0{zone_num}",
            "co2_sensor": f"CO2-{floor}-0{zone_num}"
        }

    def get_equipment_status(self, equipment_codes: Dict[str, str]) -> Dict[str, Dict]:
        """Fetch status for all zone equipment."""
        status = {}
        for eq_type, code in equipment_codes.items():
            result = self.client.table("equipment").select("*").eq("code", code).execute()
            if result.data:
                status[code] = result.data[0]
        return status

    def analyze_temperature_high(
        self,
        zone_id: str,
        current_temp: float,
        setpoint: float
    ) -> DiagnosticResult:
        """Analyze high temperature condition."""
        deviation = current_temp - setpoint
        equipment_codes = self.get_zone_equipment(zone_id)
        equipment_status = self.get_equipment_status(equipment_codes)

        # Check each component for issues
        fcu_code = equipment_codes["fcu"]
        vav_code = equipment_codes["vav"]
        ahu_code = equipment_codes["ahu"]

        fcu = equipment_status.get(fcu_code, {})
        vav = equipment_status.get(vav_code, {})
        ahu = equipment_status.get(ahu_code, {})

        fcu_meta = fcu.get("metadata", {})
        ahu_meta = ahu.get("metadata", {})

        # Diagnostic logic
        fault_type = FaultType.UNKNOWN
        faulty_equipment = ""
        fault_code = None
        fault_description = "Unable to determine root cause"
        recommended_actions = []
        parts_required = []
        repair_hours = 1.0

        # Check FCU valve position
        valve_pos = fcu_meta.get("valve_position", 100)
        if valve_pos < 30 and deviation > 2:
            fault_type = FaultType.FCU_VALVE_STUCK
            faulty_equipment = fcu_code
            fault_code = "E04"
            fault_description = f"FCU valve stuck at {valve_pos}% - insufficient chilled water flow"
            recommended_actions = [
                "Check valve actuator power supply (24VAC)",
                "Verify BMS control signal (0-10V or 4-20mA)",
                "Attempt manual override to test valve",
                "Replace actuator if unresponsive"
            ]
            parts_required = [f"{fcu.get('manufacturer', 'Belimo')} {fcu.get('model', 'LMV-D3')} actuator"]
            repair_hours = 2.0

        # Check AHU supply air temp
        elif ahu_meta.get("supply_air_temp", 14) > 16:
            supply_temp = ahu_meta.get("supply_air_temp", 14)
            fault_type = FaultType.AHU_SUPPLY_HIGH
            faulty_equipment = ahu_code
            fault_code = "E12"
            fault_description = f"AHU supply air temp high ({supply_temp}°C) - chiller or coil issue"
            recommended_actions = [
                "Check chiller operation and leaving water temp",
                "Verify AHU chilled water valve position",
                "Check for air filter blockage",
                "Inspect cooling coil for fouling"
            ]
            parts_required = []
            repair_hours = 4.0

        # Check for high occupancy (if CO2 is high)
        elif deviation > 1 and deviation < 3:
            fault_type = FaultType.HIGH_OCCUPANCY
            faulty_equipment = ""
            fault_description = "Possible high occupancy heat load"
            recommended_actions = [
                "Check zone occupancy count",
                "Increase FCU fan speed temporarily",
                "Lower setpoint by 1°C during peak hours"
            ]
            repair_hours = 0

        # Determine severity
        if deviation >= 4:
            severity = "critical"
        elif deviation >= 2:
            severity = "warning"
        else:
            severity = "info"

        return DiagnosticResult(
            zone_id=zone_id,
            current_temp=current_temp,
            setpoint=setpoint,
            deviation=deviation,
            fault_type=fault_type,
            faulty_equipment=faulty_equipment,
            fault_code=fault_code,
            fault_description=fault_description,
            equipment_status=equipment_status,
            recommended_actions=recommended_actions,
            parts_required=parts_required,
            estimated_repair_hours=repair_hours,
            severity=severity
        )

    def format_clawd_message(self, diag: DiagnosticResult) -> str:
        """Format diagnostic result for Clawd Telegram."""
        severity_emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
        emoji = severity_emoji.get(diag.severity, "📢")

        # Equipment status summary
        eq_lines = []
        for code, eq in diag.equipment_status.items():
            status = eq.get("status", "unknown")
            icon = "✅" if status == "normal" else "⚠️" if status == "warning" else "❌"
            eq_lines.append(f"{icon} {code}: {status}")

        eq_summary = "\n".join(eq_lines)

        # Actions
        actions = "\n".join([f"  {i+1}. {a}" for i, a in enumerate(diag.recommended_actions[:3])])

        message = f"""{emoji} *{diag.severity.upper()} ALERT*

*Zone:* {diag.zone_id}
*Temp:* {diag.current_temp}°C (setpoint {diag.setpoint}°C)
*Deviation:* +{diag.deviation:.1f}°C

*Equipment:*
{eq_summary}

*Diagnosis:* {diag.fault_description}
{f"*Fault Code:* {diag.fault_code}" if diag.fault_code else ""}

*Actions:*
{actions}

{f"*Parts:* {', '.join(diag.parts_required)}" if diag.parts_required else ""}
{f"*Est. Repair:* {diag.estimated_repair_hours}h" if diag.estimated_repair_hours else ""}

Reply: /ack | /dispatch | /wo {diag.faulty_equipment}"""

        return message


def get_zone_diagnostics():
    """Get diagnostics service instance."""
    from app.database.supabase_client import get_supabase_client
    return ZoneDiagnostics(get_supabase_client())
