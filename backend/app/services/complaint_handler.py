"""
Comfort Complaint Handler
=========================
Handles comfort complaints by linking desk location to HVAC systems.
Uses CrossSystemAnalyzer for diagnosis with occupancy context.

Data sources:
- Building config (desks, zones): JSON files via BuildingDataLoader
- Complaint history: Supabase (with JSON fallback)

The killer feature: "Too hot at Desk 25" -> instant BMS diagnosis.
"""

import logging
import os
import re
from datetime import datetime, timedelta

from app.models.complaint import (
    ComfortComplaint,
    ComplaintDiagnosis,
    Desk,
    HVACZone,
)
from app.services.zone_assessment_service import get_zone_assessment_service
from app.services.cross_system_analyzer import get_cross_system_analyzer

logger = logging.getLogger(__name__)

# Check if Supabase is configured
USE_SUPABASE = os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY")


class ComfortComplaintHandler:
    """
    Handles comfort complaints by linking desk location to HVAC systems.
    Uses CrossSystemAnalyzer for diagnosis with occupancy context.
    """

    def __init__(self):
        self._desks: dict[str, Desk] = {}
        self._zones: dict[str, HVACZone] = {}
        self._complaints: dict[str, ComfortComplaint] = {}
        self._desk_id_map: dict[str, str] = {}  # Normalized ID -> full ID
        self._load_data()

    def _load_data(self):
        """Load desk and zone data directly from Supabase."""
        try:
            from app.database.repositories.desk_repository import DeskRepository
            from app.database.repositories.zone_repository import ZoneRepository

            # Build building UUID -> code lookup
            site_code_map = {}
            try:
                from app.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                bld_resp = client.table("sites").select("id, code").execute()
                if bld_resp.data:
                    site_code_map = {b["id"]: b["code"] for b in bld_resp.data}
            except Exception:
                pass

            # Load desks from Supabase
            desk_repo = DeskRepository()
            all_desks = desk_repo.get_all()
            if all_desks:
                for d in all_desks:
                    # Populate building field from UUID lookup
                    if not d.get("building") and d.get("site_id"):
                        d["building"] = site_code_map.get(d["site_id"], "")
                    desk = Desk.from_dict(d)
                    self._desks[desk.desk_id] = desk
                    # Create normalized ID mappings for flexible lookup
                    self._create_desk_id_mappings(desk)
                logger.info(f"Loaded {len(self._desks)} desks from Supabase")
            else:
                logger.warning("No desks found in Supabase")

            # Load zones from Supabase (zones table has equipment refs)
            zone_repo = ZoneRepository()
            all_zones = zone_repo.get_all()

            # Also fetch live readings from hvac_zones table
            live_readings = {}
            try:
                hvac_resp = (
                    client.table("hvac_zones")
                    .select("zone_id, current_temp, setpoint, status, current_humidity, current_co2")
                    .execute()
                )
                if hvac_resp.data:
                    live_readings = {r["zone_id"]: r for r in hvac_resp.data}
            except Exception:
                pass

            if all_zones:
                for z in all_zones:
                    # Merge live readings from hvac_zones into zone data
                    live = live_readings.get(z.get("zone_id", ""), {})
                    if live.get("current_temp") is not None:
                        z["current_temp"] = live["current_temp"]
                    if live.get("setpoint") is not None:
                        z["setpoint"] = live["setpoint"]
                    if live.get("status"):
                        z["status"] = live["status"]
                    zone = HVACZone.from_dict(z)
                    self._zones[zone.zone_id] = zone
                logger.info(f"Loaded {len(self._zones)} zones from Supabase ({len(live_readings)} with live readings)")
            else:
                logger.warning("No zones found in Supabase")

        except Exception as e:
            logger.error(f"Error loading data from Supabase: {e}")
            logger.warning("Complaint handler will have no desk/zone data available")

    def _create_desk_id_mappings(self, desk: Desk):
        """Create multiple ID mappings for flexible desk lookup."""
        full_id = desk.desk_id

        # Map by full ID
        self._desk_id_map[full_id.lower()] = full_id

        # Map by number only (e.g., "25" -> "L12-25")
        match = re.search(r"(\d+)$", full_id)
        if match:
            number_only = match.group(1)
            # Only map if not already mapped (first match wins)
            if number_only not in self._desk_id_map:
                self._desk_id_map[number_only] = full_id
            # Also map without leading zeros (e.g., "25" -> "025")
            stripped = number_only.lstrip("0") or "0"
            if stripped not in self._desk_id_map:
                self._desk_id_map[stripped] = full_id

        # Map without hyphen (e.g., "L1225" -> "L12-25")
        no_hyphen = full_id.replace("-", "").lower()
        self._desk_id_map[no_hyphen] = full_id

    def _normalize_desk_id(self, desk_id: str) -> str | None:
        """
        Normalize desk ID to handle various input formats.

        Accepts: "25", "L12-25", "l12-25", "L1225", "Desk 25"
        Returns: "L12-25" (the full canonical ID)
        """
        if not desk_id:
            return None

        # Clean up input
        cleaned = desk_id.strip().lower()
        cleaned = re.sub(r"^desk\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        # Try direct lookup
        if cleaned in self._desk_id_map:
            return self._desk_id_map[cleaned]

        # Try with hyphen variations
        if cleaned in self._desk_id_map:
            return self._desk_id_map[cleaned]

        # Try just the number
        match = re.search(r"(\d+)$", cleaned)
        if match:
            number = match.group(1)
            if number in self._desk_id_map:
                return self._desk_id_map[number]
            # Try zero-padded to 3 digits (user says "25", DB has "025")
            padded = number.zfill(3)
            if padded in self._desk_id_map:
                return self._desk_id_map[padded]

        return None

    def get_desk(self, desk_id: str) -> Desk | None:
        """
        Get desk by ID with flexible matching.

        Accepts various formats: "25", "L12-25", "Desk 25", etc.
        """
        normalized_id = self._normalize_desk_id(desk_id)
        if normalized_id:
            return self._desks.get(normalized_id)
        return None

    def get_zone(self, zone_id: str) -> HVACZone | None:
        """Get HVAC zone by ID."""
        return self._zones.get(zone_id)

    def lookup_desk_bms(self, desk_id: str) -> dict:
        """
        The killer feature: desk_id -> zone -> FCU -> sensors -> current readings.

        Returns complete BMS context for a desk location.
        """
        desk = self.get_desk(desk_id)
        if not desk:
            return {
                "success": False,
                "error": f"Desk '{desk_id}' not found",
                "suggestions": list(self._desks.keys())[:5],
            }

        zone = self.get_zone(desk.zone_id)
        if not zone:
            return {
                "success": False,
                "error": f"Zone '{desk.zone_id}' not found for desk '{desk_id}'",
            }

        return {
            "success": True,
            "desk": desk.to_dict(),
            "zone": zone.to_dict(),
            "bms_context": {
                "fcu_id": zone.fcu_id,
                "vav_id": zone.vav_id,
                "ahu_id": zone.ahu_id,
                "temp_sensor": zone.temp_sensor,
                "co2_sensor": zone.co2_sensor,
                "current_temp": zone.current_temp,
                "setpoint": zone.setpoint,
                "status": zone.status,
            },
            "dali_context": {
                "dali_zone": desk.dali_zone,
                "sensor_id": desk.sensor_id,
                "luminaire_ids": desk.luminaire_ids,
                "dali_controller": desk.dali_controller,
            },
            "desk_context": {
                "near_window": desk.near_window,
                "orientation": desk.orientation,
                "near_diffuser": desk.near_diffuser,
                "near_printer": desk.near_printer,
                "department": desk.department,
                "occupant": desk.occupant,
            },
        }

    def handle_complaint(
        self,
        desk_id: str,
        complaint_type: str,
        user_name: str | None = None,
        description: str | None = None,
    ) -> ComplaintDiagnosis:
        """
        Main entry point for complaint handling.

        1. Lookup desk -> zone mapping
        2. ZoneAssessmentService produces full zone assessment:
           - All equipment in zone (health, alerts, predictions)
           - VAV live readings (BMS telemetry)
           - Contextual factors (solar, occupancy, outdoor temp, etc.)
           - Recommendations gated by control module + phase
        3. Log complaint for pattern tracking
        4. Return structured diagnosis with suggestions
        """
        # 1. Parse and lookup desk
        desk = self.get_desk(desk_id)
        if not desk:
            # Return diagnosis with error state
            return ComplaintDiagnosis(
                complaint_id="error",
                desk=Desk(
                    desk_id=desk_id,
                    floor="Unknown",
                    building="Unknown",
                    zone_id="unknown",
                ),
                zone=HVACZone(
                    zone_id="unknown",
                    zone_name="Unknown",
                    floor="Unknown",
                    fcu_id="unknown",
                    temp_sensor="unknown",
                    typical_occupancy=0,
                ),
                diagnosis=f"Desk '{desk_id}' not found in system",
                root_cause="Unknown desk location",
                confidence="low",
                suggestions=[
                    "Please verify desk ID",
                    f"Available desks include: {', '.join(list(self._desks.keys())[:5])}",
                ],
                needs_dispatch=False,
            )

        # 2. Get zone
        zone = self.get_zone(desk.zone_id)
        if not zone:
            zone = HVACZone(
                zone_id=desk.zone_id,
                zone_name=desk.zone_id,
                floor=desk.floor,
                fcu_id="unknown",
                temp_sensor="unknown",
                typical_occupancy=0,
            )

        # 3. Create complaint record
        complaint = ComfortComplaint(
            desk_id=desk.desk_id,
            user_name=user_name,
            complaint_type=complaint_type,
            description=description,
            status="diagnosed",
        )
        self._complaints[complaint.complaint_id] = complaint

        # 4. ZoneAssessmentService: full zone assessment
        assessor = get_zone_assessment_service()
        assessment = assessor.assess_zone(
            zone_id=desk.zone_id,
            complaint_type=complaint_type,
            desk_id=desk.desk_id,
            site_id=zone.site_id if hasattr(zone, "site_id") else None,
        )

        # 5. Convert ZoneAssessment -> ComplaintDiagnosis for backward compatibility
        diagnosis_parts = []

        # Zone temperature summary
        delta = assessment.zone_temp - assessment.zone_setpoint
        delta_str = f"+{delta:.1f}C above" if delta > 0 else f"{delta:.1f}C below" if delta < 0 else "at setpoint"
        diagnosis_parts.append(
            f"Zone {assessment.zone_id}: {assessment.zone_temp}°C "
            f"(setpoint {assessment.zone_setpoint}°C, {delta_str}). "
            f"Status: {assessment.zone_status}."
        )

        # Equipment summary
        if assessment.equipment_statuses:
            eq_lines = []
            for eq in assessment.equipment_statuses:
                health = f"{eq.health_score}%"
                issues = []
                if eq.alerts:
                    issues.append(f"{len(eq.alerts)} alert(s)")
                if eq.predictions:
                    issues.append(f"{len(eq.predictions)} prediction(s)")
                issue_str = f" — {', '.join(issues)}" if issues else ""
                eq_lines.append(f"{eq.name}: {eq.status} ({health}){issue_str}")
            diagnosis_parts.append("Equipment: " + "; ".join(eq_lines))

        # VAV summary
        if assessment.vav:
            vav_parts = []
            if assessment.vav.damper_position is not None:
                vav_parts.append(f"damper {assessment.vav.damper_position:.0f}%")
            if assessment.vav.airflow_actual is not None:
                vav_parts.append(f"airflow {assessment.vav.airflow_actual:.0f} L/s")
            if assessment.vav.discharge_temp is not None:
                vav_parts.append(f"discharge {assessment.vav.discharge_temp:.1f}°C")
            if assessment.vav.reheat_valve is not None:
                vav_parts.append(f"reheat {assessment.vav.reheat_valve:.0f}%")
            if vav_parts:
                diagnosis_parts.append(f"VAV {assessment.vav.vav_id}: {', '.join(vav_parts)}")

        # Outdoor temp
        if assessment.outdoor_temp is not None:
            extreme = " (extreme heat)" if assessment.outdoor_extreme else ""
            diagnosis_parts.append(f"Outdoor temp: {assessment.outdoor_temp:.0f}°C{extreme}.")

        # Contextual factors
        if assessment.solar_factor:
            sf_map = {
                "morning_sun": "Morning sun (east-facing windows) heating area",
                "afternoon_sun": "Afternoon sun (west-facing windows) heating area",
                "north_facing": "Direct sunlight (north-facing) — HVAC unable to fully offset",
            }
            diagnosis_parts.append(sf_map.get(assessment.solar_factor, assessment.solar_factor))

        if assessment.low_occupancy:
            diagnosis_parts.append(f"Low zone occupancy ({assessment.occupancy_pct:.0f}%)")

        if assessment.high_lighting_load:
            diagnosis_parts.append(f"High lighting heat load ({assessment.lighting_level:.0f}%)")

        # Build final diagnosis text
        diagnosis = " | ".join(diagnosis_parts) if diagnosis_parts else "No issues detected."

        # Build suggestions from ZoneAssessment recommendations
        suggestions: list[str] = []
        needs_dispatch = assessment.status == "equipment_fault" or assessment.has_critical_equipment_issues

        for rec in assessment.recommendations:
            action_text = rec.action
            if rec.can_auto_adjust:
                action_text += " [auto]"
            elif rec.can_supervised_adjust:
                action_text += " [approval required]"
            suggestions.append(action_text)

        # Add root cause context if no recommendations
        if not suggestions and assessment.root_causes:
            for cause in assessment.root_causes:
                suggestions.append(cause)

        # Status message based on assessment result
        if assessment.status == "no_issues":
            suggestions.append("All systems operating within parameters. No action required.")

        return ComplaintDiagnosis(
            complaint_id=complaint.complaint_id,
            desk=desk,
            zone=zone,
            diagnosis=diagnosis,
            root_cause="; ".join(assessment.root_causes) if assessment.root_causes else assessment.status,
            confidence=assessment.confidence,
            suggestions=suggestions,
            auto_action_taken=None,
            needs_dispatch=needs_dispatch,
        )

    def get_zone_context(self, zone_id: str) -> dict:
        """Get combined HVAC + DALI context for a zone."""
        zone = self.get_zone(zone_id)
        if not zone:
            return {"error": f"Zone '{zone_id}' not found"}

        analyzer = get_cross_system_analyzer()
        context_text = analyzer.get_zone_context_for_chat(zone_id)

        # Get desks in this zone
        desks_in_zone = [d for d in self._desks.values() if d.zone_id == zone_id]

        return {
            "zone": zone.to_dict(),
            "context_text": context_text,
            "desks_count": len(desks_in_zone),
            "desks": [d.to_dict() for d in desks_in_zone],
        }

    def get_complaint_history(
        self, desk_id: str | None = None, zone_id: str | None = None
    ) -> list[ComfortComplaint]:
        """Get complaint history for pattern analysis."""
        complaints = list(self._complaints.values())

        if desk_id:
            normalized_id = self._normalize_desk_id(desk_id)
            if normalized_id:
                complaints = [c for c in complaints if c.desk_id == normalized_id]

        if zone_id:
            # Filter to desks in this zone
            zone_desks = {d.desk_id for d in self._desks.values() if d.zone_id == zone_id}
            complaints = [c for c in complaints if c.desk_id in zone_desks]

        # Sort by timestamp descending
        complaints.sort(key=lambda c: c.timestamp, reverse=True)
        return complaints

    def get_complaint_history_summary(
        self,
        desk_id: str,
        days: int = 7,
        complaint_types: list[str] | None = None,
    ) -> dict:
        """
        Summarize recent complaints for a desk - used by agent for escalation logic.

        Returns dict with count, same-type match count, last complaint timestamp,
        and whether escalation is recommended (3+ in 7 days).
        """
        history = self.get_complaint_history(desk_id=desk_id)
        cutoff = datetime.now() - timedelta(days=days)
        recent = [c for c in history if c.timestamp >= cutoff]

        same_type_count = 0
        if complaint_types and recent:
            same_type_count = sum(1 for c in recent if c.complaint_type in complaint_types)

        return {
            "count": len(recent),
            "same_type_count": same_type_count,
            "last_complaint": recent[0].timestamp.isoformat() if recent else None,
            "escalation_recommended": len(recent) >= 3,
        }

    def get_recent_complaints(self, hours: int = 24) -> list[ComfortComplaint]:
        """Get recent complaints across all zones."""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [c for c in self._complaints.values() if c.timestamp >= cutoff]
        recent.sort(key=lambda c: c.timestamp, reverse=True)
        return recent

    def get_all_desks(self) -> list[Desk]:
        """Get all desks."""
        return list(self._desks.values())

    def get_all_zones(self) -> list[HVACZone]:
        """Get all HVAC zones."""
        return list(self._zones.values())


# Singleton pattern
_handler: ComfortComplaintHandler | None = None


def get_complaint_handler() -> ComfortComplaintHandler:
    """Get singleton ComfortComplaintHandler instance."""
    global _handler
    if _handler is None:
        _handler = ComfortComplaintHandler()
    return _handler


def reload_complaint_handler() -> ComfortComplaintHandler:
    """Force reload of complaint handler with fresh data from Supabase."""
    global _handler
    # Recreate handler to reload from Supabase
    _handler = ComfortComplaintHandler()
    logger.info("Complaint handler reloaded with fresh data from Supabase")
    return _handler
