"""Repository for alert operations."""

from datetime import UTC
from typing import Any, Optional

from app.database.supabase_client import get_supabase_client
from app.services.cache_service import CacheInvalidation, CacheKeys, CacheService, cache, track_query


class AlertRepository:
    """Repository for alert database operations."""

    _COLUMNS = (
        "id, title, message, severity, status, type, "
        "site_id, equipment_id, created_at, updated_at, "
        "acknowledged_by, acknowledged_at"
    )

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self,
        site_id: str | None = None,
        equipment_id: str | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all alerts with optional filtering.

        Args:
            site_id: Filter by building UUID
            equipment_id: Filter by equipment UUID
            status: Filter by status
            severity: Filter by severity

        Returns:
            List of alerts
        """
        query = self.client.table("alerts").select(self._COLUMNS)

        if site_id:
            query = query.eq("site_id", site_id)
        if equipment_id:
            query = query.eq("equipment_id", equipment_id)
        if status:
            query = query.eq("status", status)
        if severity:
            query = query.eq("severity", severity)

        response = query.execute()
        return response.data

    def get_by_id(self, alert_id: str) -> dict[str, Any] | None:
        """Get alert by its UUID.

        Args:
            alert_id: Alert UUID

        Returns:
            Alert data or None if not found
        """
        response = self.client.table("alerts").select(self._COLUMNS).eq("id", alert_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_active_by_site(self, site_uuid: str) -> list[dict[str, Any]]:
        """Get active alerts for a building.

        Args:
            site_uuid: Building UUID

        Returns:
            List of active alerts
        """
        cached = cache.get(CacheKeys.alerts_active(site_uuid))
        if cached is not None:
            return cached

        with track_query("alert", "get_active_by_site"):
            response = (
                self.client.table("alerts")
                .select(self._COLUMNS)
                .eq("site_id", site_uuid)
                .eq("status", "active")
                .execute()
            )

        result = response.data
        cache.set(CacheKeys.alerts_active(site_uuid), result, CacheService.TTL_DYNAMIC)
        return result

    def get_active_by_equipment(self, equipment_uuid: str) -> list[dict[str, Any]]:
        """Get active alerts for equipment.

        Args:
            equipment_uuid: Equipment UUID

        Returns:
            List of active alerts
        """
        response = (
            self.client.table("alerts")
            .select(self._COLUMNS)
            .eq("equipment_id", equipment_uuid)
            .eq("status", "active")
            .execute()
        )

        return response.data

    def get_active_alerts_for_equipment(self, equipment_code: str) -> list[dict[str, Any]]:
        """Check if active alerts exist for equipment by code (for deduplication).

        Searches for active alerts whose title contains the equipment code.
        Used by the health monitoring pipeline to avoid creating duplicate alerts.

        Args:
            equipment_code: Equipment code (e.g., S002-CHILLER-B1-001)

        Returns:
            List of active alerts for this equipment code
        """
        try:
            from app.utils import escape_like

            response = (
                self.client.table("alerts")
                .select("id, title, severity, status")
                .eq("status", "active")
                .ilike("title", f"%{escape_like(equipment_code)}%")
                .execute()
            )
            return response.data or []
        except Exception:
            return []

    def get_critical_alerts(self) -> list[dict[str, Any]]:
        """Get all critical active alerts.

        Returns:
            List of critical alerts
        """
        response = (
            self.client.table("alerts")
            .select(self._COLUMNS)
            .eq("severity", "critical")
            .eq("status", "active")
            .execute()
        )

        return response.data

    def create(self, alert_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new alert.

        Args:
            alert_data: Alert data

        Returns:
            Created alert
        """
        response = self.client.table("alerts").insert(alert_data).execute()
        result = response.data[0]
        CacheInvalidation.on_alert_change(site_id=alert_data.get("site_id"))
        return result

    def update(self, alert_id: str, alert_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an alert.

        Args:
            alert_id: Alert UUID
            alert_data: Data to update

        Returns:
            Updated alert or None if not found
        """
        response = self.client.table("alerts").update(alert_data).eq("id", alert_id).execute()

        if response.data:
            CacheInvalidation.on_alert_change(site_id=response.data[0].get("site_id"))
            return response.data[0]
        return None

    def acknowledge(self, alert_id: str, acknowledged_by: str) -> dict[str, Any] | None:
        """Acknowledge an alert.

        Args:
            alert_id: Alert UUID
            acknowledged_by: User who acknowledged the alert

        Returns:
            Updated alert or None if not found
        """
        from datetime import datetime

        return self.update(
            alert_id,
            {
                "status": "acknowledged",
                "acknowledged_by": acknowledged_by,
                "acknowledged_at": datetime.now(UTC).isoformat(),
            },
        )

    def resolve(self, alert_id: str) -> dict[str, Any] | None:
        """Resolve an alert.

        Args:
            alert_id: Alert UUID

        Returns:
            Updated alert or None if not found
        """
        return self.update(alert_id, {"status": "resolved"})

    def delete(self, alert_id: str) -> bool:
        """Delete an alert.

        Args:
            alert_id: Alert UUID

        Returns:
            True if deleted, False if not found
        """
        response = self.client.table("alerts").delete().eq("id", alert_id).execute()

        if len(response.data) > 0:
            CacheInvalidation.on_alert_change()
            return True
        return False

    def resolve_by_equipment(self, equipment_id: str) -> int:
        """Resolve all active alerts for a specific equipment.

        Called when a service record is completed to mark all related
        alerts as resolved.

        Args:
            equipment_id: Equipment UUID

        Returns:
            Number of alerts resolved
        """
        # Get all active alerts for this equipment
        active_alerts = self.get_active_by_equipment(equipment_id)

        if not active_alerts:
            return 0

        # Resolve each alert
        resolved_count = 0
        for alert in active_alerts:
            result = self.resolve(alert["id"])
            if result:
                resolved_count += 1

        return resolved_count

    def resolve_by_site(self, site_id: str) -> int:
        """Resolve all active alerts for a specific building.

        Args:
            site_id: Building UUID

        Returns:
            Number of alerts resolved
        """
        # Get all active alerts for this building
        active_alerts = self.get_active_by_site(site_id)

        if not active_alerts:
            return 0

        # Resolve each alert
        resolved_count = 0
        for alert in active_alerts:
            result = self.resolve(alert["id"])
            if result:
                resolved_count += 1

        return resolved_count


# Singleton instance
_alert_repository_instance: Optional["AlertRepository"] = None


def get_alert_repository() -> "AlertRepository":
    """Get or create the singleton AlertRepository instance."""
    global _alert_repository_instance
    if _alert_repository_instance is None:
        _alert_repository_instance = AlertRepository()
    return _alert_repository_instance
