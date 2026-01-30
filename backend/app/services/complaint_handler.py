"""
Comfort Complaint Handler
=========================
Handles comfort complaints by linking desk location to HVAC systems.
Uses CrossSystemAnalyzer for diagnosis with occupancy context.

The killer feature: "Too hot at Desk 25" -> instant BMS diagnosis.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from app.models.complaint import (
    Desk,
    HVACZone,
    ComfortComplaint,
    ComplaintDiagnosis,
)
from app.services.cross_system_analyzer import get_cross_system_analyzer

logger = logging.getLogger(__name__)


class ComfortComplaintHandler:
    """
    Handles comfort complaints by linking desk location to HVAC systems.
    Uses CrossSystemAnalyzer for diagnosis with occupancy context.
    """

    def __init__(self):
        self._desks: Dict[str, Desk] = {}
        self._zones: Dict[str, HVACZone] = {}
        self._complaints: Dict[str, ComfortComplaint] = {}
        self._desk_id_map: Dict[str, str] = {}  # Normalized ID -> full ID
        self._load_data()

    def _load_data(self):
        """Load desk and zone data from JSON files."""
        data_path = Path(__file__).parent.parent / "data"

        # Load desks
        desks_file = data_path / "desks.json"
        if desks_file.exists():
            with open(desks_file) as f:
                desks_data = json.load(f)
                for d in desks_data:
                    desk = Desk.from_dict(d)
                    self._desks[desk.desk_id] = desk
                    # Create normalized ID mappings for flexible lookup
                    self._create_desk_id_mappings(desk)
            logger.info(f"Loaded {len(self._desks)} desks")
        else:
            logger.warning(f"Desks data not found at {desks_file}")

        # Load zones
        zones_file = data_path / "hvac_zones.json"
        if zones_file.exists():
            with open(zones_file) as f:
                zones_data = json.load(f)
                for z in zones_data:
                    zone = HVACZone.from_dict(z)
                    self._zones[zone.zone_id] = zone
            logger.info(f"Loaded {len(self._zones)} zones")
        else:
            logger.warning(f"Zones data not found at {zones_file}")

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

        # Map without hyphen (e.g., "L1225" -> "L12-25")
        no_hyphen = full_id.replace("-", "").lower()
        self._desk_id_map[no_hyphen] = full_id

    def _normalize_desk_id(self, desk_id: str) -> Optional[str]:
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

        return None

    def get_desk(self, desk_id: str) -> Optional[Desk]:
        """
        Get desk by ID with flexible matching.

        Accepts various formats: "25", "L12-25", "Desk 25", etc.
        """
        normalized_id = self._normalize_desk_id(desk_id)
        if normalized_id:
            return self._desks.get(normalized_id)
        return None

    def get_zone(self, zone_id: str) -> Optional[HVACZone]:
        """Get HVAC zone by ID."""
        return self._zones.get(zone_id)

    def lookup_desk_bms(self, desk_id: str) -> Dict:
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
            "desk_context": {
                "near_window": desk.near_window,
                "near_diffuser": desk.near_diffuser,
                "near_printer": desk.near_printer,
                "department": desk.department,
            },
        }

    def handle_complaint(
        self,
        desk_id: str,
        complaint_type: str,
        user_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> ComplaintDiagnosis:
        """
        Main entry point for complaint handling.

        1. Lookup desk -> zone mapping
        2. Get zone context (HVAC status, occupancy, lighting)
        3. Use CrossSystemAnalyzer for diagnosis
        4. Enhance with desk-specific context
        5. Log complaint for pattern tracking
        6. Return structured diagnosis with suggestions
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

        # 4. Use CrossSystemAnalyzer for diagnosis
        analyzer = get_cross_system_analyzer()
        comfort_diagnosis = analyzer.analyze_comfort_complaint(
            zone_id=desk.zone_id,
            complaint_type=complaint_type,
            desk_id=desk.desk_id,
        )

        # 5. Enhance with desk-specific context
        enhanced_suggestions = list(comfort_diagnosis.suggestions)
        enhanced_root_cause = comfort_diagnosis.root_cause
        enhanced_confidence = comfort_diagnosis.confidence

        # Check time of day for solar context
        current_hour = datetime.now().hour

        # Near window + too_hot + afternoon = solar heat gain
        if desk.near_window and complaint_type == "too_hot" and 12 <= current_hour <= 18:
            if "solar" not in enhanced_root_cause.lower():
                enhanced_root_cause = (
                    f"Solar heat gain likely - desk is near west-facing window. "
                    f"{enhanced_root_cause}"
                )
                enhanced_confidence = "high"
                enhanced_suggestions.insert(0, "Close blinds or activate automated shading")
                if "Temporarily boost cooling" not in str(enhanced_suggestions):
                    enhanced_suggestions.insert(
                        1, f"Temporarily boost cooling to {zone.setpoint - 2}C for 2 hours"
                    )

        # Under diffuser + too_cold = direct airflow
        if desk.near_diffuser and complaint_type == "too_cold":
            enhanced_root_cause = (
                f"Direct airflow from diffuser {desk.near_diffuser}. "
                f"Desk is directly under supply air outlet."
            )
            enhanced_confidence = "high"
            enhanced_suggestions = [
                f"Adjust diffuser {desk.near_diffuser} direction or airflow",
                "Consider desk relocation",
                "Install local air deflector",
            ]

        # Near printer + too_hot = heat source
        if desk.near_printer and complaint_type == "too_hot":
            if "printer" not in enhanced_root_cause.lower():
                enhanced_root_cause = (
                    f"Heat source detected - desk is near printer/copier. "
                    f"{enhanced_root_cause}"
                )
                enhanced_suggestions.insert(
                    0, "Consider relocating desk away from printer heat source"
                )

        # Check if zone has fault
        needs_dispatch = zone.status == "fault"
        if needs_dispatch:
            enhanced_root_cause = f"HVAC FAULT DETECTED in zone. {enhanced_root_cause}"
            enhanced_suggestions.insert(0, "Dispatch technician - FCU fault detected")

        return ComplaintDiagnosis(
            complaint_id=complaint.complaint_id,
            desk=desk,
            zone=zone,
            diagnosis=f"{comfort_diagnosis.hvac_analysis} | {comfort_diagnosis.lighting_analysis}",
            root_cause=enhanced_root_cause,
            confidence=enhanced_confidence,
            suggestions=enhanced_suggestions,
            auto_action_taken=None,
            needs_dispatch=needs_dispatch,
        )

    def get_zone_context(self, zone_id: str) -> Dict:
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
        self, desk_id: Optional[str] = None, zone_id: Optional[str] = None
    ) -> List[ComfortComplaint]:
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

    def get_recent_complaints(self, hours: int = 24) -> List[ComfortComplaint]:
        """Get recent complaints across all zones."""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [c for c in self._complaints.values() if c.timestamp >= cutoff]
        recent.sort(key=lambda c: c.timestamp, reverse=True)
        return recent

    def get_all_desks(self) -> List[Desk]:
        """Get all desks."""
        return list(self._desks.values())

    def get_all_zones(self) -> List[HVACZone]:
        """Get all HVAC zones."""
        return list(self._zones.values())


# Singleton pattern
_handler: Optional[ComfortComplaintHandler] = None


def get_complaint_handler() -> ComfortComplaintHandler:
    """Get singleton ComfortComplaintHandler instance."""
    global _handler
    if _handler is None:
        _handler = ComfortComplaintHandler()
    return _handler
