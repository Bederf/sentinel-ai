"""
Equipment Alert Service - Orchestrates alert creation and notifications.

Central service for creating equipment alerts with:
1. Alert creation in Supabase via AlertRepository
2. Telegram notification via Sentry alert_notifier
3. Returns created alert data

Phase: Demo Flow - Equipment Warning State with Notifications
"""

import logging
import re
import uuid
from typing import Any

from app.database.repositories.alert_repository import AlertRepository
from app.database.supabase_client import get_supabase_client
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
        site_id: str,
        severity: str,
        message: str,
        alert_type: str = "health_degradation",
        notify_telegram: bool = True,
    ) -> dict[str, Any]:
        """
        Create an alert for equipment and optionally send Telegram notification.

        Args:
            equipment_id: Equipment UUID
            site_id: Building UUID
            severity: Alert severity (critical, warning, info)
            message: Alert message
            alert_type: Type of alert (default: health_degradation)
            notify_telegram: Whether to send Telegram notification

        Returns:
            Dict with created alert data and notification status
        """
        # Get equipment details (accepts UUID or equipment code)
        equipment = self._get_equipment(equipment_id)
        if not equipment:
            return {"error": f"Equipment {equipment_id} not found"}

        # Resolve building to UUID (accepts UUID or site/building code)
        building = self._get_site(site_id)
        if not building and equipment.get("site_id"):
            building = self._get_site(str(equipment.get("site_id")))

        resolved_site_id = building.get("id") if building else equipment.get("site_id", site_id)
        site_name = building.get("name", "Unknown") if building else "Unknown"

        # Use equipment code as primary identifier
        resolved_equipment_id = equipment.get("id", equipment_id)
        equipment_code = equipment.get("code", "UNKNOWN")
        equipment_type = equipment.get("type", "equipment").upper()

        # Create alert record with equipment code in title
        alert_id = str(uuid.uuid4())
        alert_data = {
            "id": alert_id,
            "site_id": resolved_site_id,
            "equipment_id": resolved_equipment_id,
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
            return {"error": f"Failed to create alert: {e!s}"}

        # Send Telegram notification
        telegram_sent = False
        if notify_telegram:
            sentry_alert = {
                "id": alert_id,
                "site_name": site_name,
                "zone_name": equipment.get("zone_name", "Unknown"),
                "equipment_name": equipment.get("display_name", equipment.get("name", "Unknown")),
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
            "site_name": site_name,
        }

    def _get_equipment(self, equipment_id: str) -> dict[str, Any] | None:
        """Get equipment by UUID or code."""
        try:
            # Try code first if it doesn't look like a UUID (avoids Postgres type error)
            is_uuid = bool(
                re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", equipment_id, re.IGNORECASE)
            )

            if is_uuid:
                response = (
                    self.supabase.table("equipment")
                    .select("id, code, name, type, health_score, site_id")
                    .eq("id", equipment_id)
                    .execute()
                )
            else:
                response = (
                    self.supabase.table("equipment")
                    .select("id, code, name, type, health_score, site_id")
                    .eq("code", equipment_id)
                    .execute()
                )

            # Fallback: try the other field
            if not response.data:
                fallback_field = "code" if is_uuid else "id"
                response = (
                    self.supabase.table("equipment")
                    .select("id, code, name, type, health_score, site_id")
                    .eq(fallback_field, equipment_id)
                    .execute()
                )

            if not response.data:
                return None
            equipment = response.data[0]

            # Look up zone name from hvac_zones (FCU/VAV codes 1:1 with zone codes)
            equipment["zone_name"] = self._lookup_zone_name(equipment.get("code", ""))

            # Clean equipment name for display (strip code in parentheses — code shown separately)
            name = equipment.get("name", "")
            equipment["display_name"] = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip() or name

            return equipment
        except Exception as e:
            logger.error(f"Failed to get equipment: {e}")
            return None

    def _lookup_zone_name(self, equipment_code: str) -> str:
        """Look up zone name from hvac_zones using equipment code.

        Equipment codes map 1:1 to zones after v34.0:
        S002-FCU-001 → Zone-001, S002-VAV-101 → Zone-101
        """
        try:
            # Try by fcu_id first, then vav_id
            response = (
                self.supabase.table("hvac_zones").select("zone_id, zone_name").eq("fcu_id", equipment_code).execute()
            )
            if not response.data:
                response = (
                    self.supabase.table("hvac_zones")
                    .select("zone_id, zone_name")
                    .eq("vav_id", equipment_code)
                    .execute()
                )
            if response.data:
                zone = response.data[0]
                return f"{zone['zone_name']} ({zone['zone_id']})"

            # For non-zone equipment (chillers, generators, etc.), derive from name
            return "Plant Room"
        except Exception as e:
            logger.warning(f"Zone lookup failed for {equipment_code}: {e}")
            return "Unknown"

    def _get_site(self, site_id: str) -> dict[str, Any] | None:
        """Get building by UUID or building/site code."""
        try:
            is_uuid = bool(
                re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", site_id, re.IGNORECASE)
            )
            field = "id" if is_uuid else "code"
            response = self.supabase.table("sites").select("id, code, name").eq(field, site_id).execute()
            if response.data:
                return response.data[0]
            # Fallback: try the other field
            fallback_field = "code" if is_uuid else "id"
            response = self.supabase.table("sites").select("id, code, name").eq(fallback_field, site_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get building: {e}")
            return None

    def resolve_alerts_for_site(self, site_id: str) -> int:
        """
        Resolve all active alerts for a building.

        Args:
            site_id: Building UUID

        Returns:
            Number of alerts resolved
        """
        try:
            # Get active alerts for building
            active_alerts = self.alert_repo.get_active_by_site(site_id)

            resolved_count = 0
            for alert in active_alerts:
                self.alert_repo.resolve(alert["id"])
                resolved_count += 1

            if resolved_count > 0:
                logger.info(f"Resolved {resolved_count} alerts for building {site_id}")

            return resolved_count

        except Exception as e:
            logger.error(f"Failed to resolve alerts: {e}")
            return 0


# Singleton instance
_service_instance: EquipmentAlertService | None = None


def get_equipment_alert_service() -> EquipmentAlertService:
    """Get singleton equipment alert service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EquipmentAlertService()
    return _service_instance
