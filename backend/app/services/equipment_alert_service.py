"""
Equipment Alert Service - Orchestrates alert creation and notifications.

Central service for creating equipment alerts with:
1. Alert creation in Supabase via AlertRepository
2. Telegram notification via Sentry alert_notifier
3. Returns created alert data

Phase: Demo Flow - Equipment Warning State with Notifications
"""

import uuid
import logging
from typing import Dict, Any, Optional

from app.database.supabase_client import get_supabase_client
from app.database.repositories.alert_repository import AlertRepository
from app.services.sentry_integration.alert_notifier import alert_notifier

logger = logging.getLogger(__name__)


class EquipmentAlertService:
    """Service for creating equipment alerts with notifications."""

    def __init__(self):
        """Initialize the service."""
        self.supabase = get_supabase_client()
        self.alert_repo = AlertRepository()

    def create_alert_for_equipment(
        self,
        equipment_id: str,
        building_id: str,
        severity: str,
        message: str,
        alert_type: str = "health_degradation",
        notify_telegram: bool = True,
    ) -> Dict[str, Any]:
        """
        Create an alert for equipment and optionally send Telegram notification.

        Args:
            equipment_id: Equipment UUID
            building_id: Building UUID
            severity: Alert severity (critical, warning, info)
            message: Alert message
            alert_type: Type of alert (default: health_degradation)
            notify_telegram: Whether to send Telegram notification

        Returns:
            Dict with created alert data and notification status
        """
        # Get equipment details
        equipment = self._get_equipment(equipment_id)
        if not equipment:
            return {"error": f"Equipment {equipment_id} not found"}

        # Get building details
        building = self._get_building(building_id)
        building_name = building.get("name", "Unknown") if building else "Unknown"

        # Use equipment code as primary identifier
        equipment_code = equipment.get("code", "UNKNOWN")
        equipment_type = equipment.get("type", "equipment").upper()

        # Create alert record with equipment code in title
        alert_id = str(uuid.uuid4())
        alert_data = {
            "id": alert_id,
            "building_id": building_id,
            "equipment_id": equipment_id,
            "type": alert_type,
            "severity": severity,
            "status": "active",
            "title": f"{severity.upper()}: {equipment_code} ({equipment_type}) - {equipment.get('name', 'Equipment')}",
            "message": message,
        }

        # Insert into Supabase
        try:
            created_alert = self.alert_repo.create(alert_data)
            logger.info(f"Created alert {alert_id} for equipment {equipment.get('name')}")
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            return {"error": f"Failed to create alert: {str(e)}"}

        # Send Telegram notification
        telegram_sent = False
        if notify_telegram:
            sentry_alert = {
                "id": alert_id,
                "building_name": building_name,
                "zone_name": equipment.get("zone_name", "Building"),
                "equipment_name": equipment.get("name", "Unknown"),
                "equipment_code": equipment.get("code", ""),
                "equipment_type": equipment.get("type", "equipment"),
                "type": severity.title(),  # "Warning" or "Critical"
                "severity": severity,
                "message": message,
            }
            telegram_sent = alert_notifier.send_alert_sync(sentry_alert)
            if telegram_sent:
                logger.info(f"Telegram notification sent for alert {alert_id}")
            else:
                logger.warning(f"Telegram notification failed for alert {alert_id}")

        return {
            "alert": created_alert,
            "telegram_sent": telegram_sent,
            "equipment_code": equipment_code,
            "equipment_name": equipment.get("name"),
            "equipment_type": equipment_type,
            "building_name": building_name,
        }

    def _get_equipment(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """Get equipment by UUID."""
        try:
            response = self.supabase.table("equipment").select(
                "id, code, name, type, health_score, building_id"
            ).eq("id", equipment_id).execute()
            if not response.data:
                return None
            equipment = response.data[0]
            # Parse zone from equipment name (e.g., "Zone-L12-C" → "Level 12 Zone C")
            equipment["zone_name"] = self._parse_zone_from_name(equipment.get("name", ""))
            return equipment
        except Exception as e:
            logger.error(f"Failed to get equipment: {e}")
            return None

    def _parse_zone_from_name(self, name: str) -> str:
        """Parse zone name from equipment name pattern like 'Zone-L12-C'."""
        import re
        # Match patterns like "Zone-L12-C" or "S001-Zone-L1-A"
        match = re.search(r'Zone-L(\d+)-([A-Z])', name)
        if match:
            level = match.group(1)
            zone_letter = match.group(2)
            return f"Level {level} Zone {zone_letter}"
        return "Building"

    def _get_building(self, building_id: str) -> Optional[Dict[str, Any]]:
        """Get building by UUID."""
        try:
            response = self.supabase.table("buildings").select(
                "id, code, name"
            ).eq("id", building_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get building: {e}")
            return None

    def resolve_alerts_for_building(self, building_id: str) -> int:
        """
        Resolve all active alerts for a building.

        Args:
            building_id: Building UUID

        Returns:
            Number of alerts resolved
        """
        try:
            # Get active alerts for building
            active_alerts = self.alert_repo.get_active_by_building(building_id)

            resolved_count = 0
            for alert in active_alerts:
                self.alert_repo.resolve(alert["id"])
                resolved_count += 1

            if resolved_count > 0:
                logger.info(f"Resolved {resolved_count} alerts for building {building_id}")

            return resolved_count

        except Exception as e:
            logger.error(f"Failed to resolve alerts: {e}")
            return 0


# Singleton instance
_service_instance: Optional[EquipmentAlertService] = None


def get_equipment_alert_service() -> EquipmentAlertService:
    """Get singleton equipment alert service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EquipmentAlertService()
    return _service_instance
