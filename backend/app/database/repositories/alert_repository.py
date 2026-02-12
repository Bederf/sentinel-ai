"""Repository for alert operations."""

from typing import List, Optional, Dict, Any
from app.database.supabase_client import get_supabase_client


class AlertRepository:
    """Repository for alert database operations."""

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        self.client = get_supabase_client()

    def get_all(
        self,
        building_id: Optional[str] = None,
        equipment_id: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all alerts with optional filtering.

        Args:
            building_id: Filter by building UUID
            equipment_id: Filter by equipment UUID
            status: Filter by status
            severity: Filter by severity

        Returns:
            List of alerts
        """
        query = self.client.table('alerts').select("*")

        if building_id:
            query = query.eq('building_id', building_id)
        if equipment_id:
            query = query.eq('equipment_id', equipment_id)
        if status:
            query = query.eq('status', status)
        if severity:
            query = query.eq('severity', severity)

        response = query.execute()
        return response.data

    def get_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get alert by its UUID.

        Args:
            alert_id: Alert UUID

        Returns:
            Alert data or None if not found
        """
        response = self.client.table('alerts').select("*").eq('id', alert_id).execute()

        if response.data:
            return response.data[0]
        return None

    def get_active_by_building(self, building_uuid: str) -> List[Dict[str, Any]]:
        """Get active alerts for a building.

        Args:
            building_uuid: Building UUID

        Returns:
            List of active alerts
        """
        response = self.client.table('alerts').select("*").eq(
            'building_id', building_uuid
        ).eq('status', 'active').execute()

        return response.data

    def get_active_by_equipment(self, equipment_uuid: str) -> List[Dict[str, Any]]:
        """Get active alerts for equipment.

        Args:
            equipment_uuid: Equipment UUID

        Returns:
            List of active alerts
        """
        response = self.client.table('alerts').select("*").eq(
            'equipment_id', equipment_uuid
        ).eq('status', 'active').execute()

        return response.data

    def get_critical_alerts(self) -> List[Dict[str, Any]]:
        """Get all critical active alerts.

        Returns:
            List of critical alerts
        """
        response = self.client.table('alerts').select("*").eq(
            'severity', 'critical'
        ).eq('status', 'active').execute()

        return response.data

    def create(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new alert.

        Args:
            alert_data: Alert data

        Returns:
            Created alert
        """
        response = self.client.table('alerts').insert(alert_data).execute()
        return response.data[0]

    def update(self, alert_id: str, alert_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an alert.

        Args:
            alert_id: Alert UUID
            alert_data: Data to update

        Returns:
            Updated alert or None if not found
        """
        response = self.client.table('alerts').update(
            alert_data
        ).eq('id', alert_id).execute()

        if response.data:
            return response.data[0]
        return None

    def acknowledge(self, alert_id: str, acknowledged_by: str) -> Optional[Dict[str, Any]]:
        """Acknowledge an alert.

        Args:
            alert_id: Alert UUID
            acknowledged_by: User who acknowledged the alert

        Returns:
            Updated alert or None if not found
        """
        from datetime import datetime, timezone

        return self.update(alert_id, {
            'status': 'acknowledged',
            'acknowledged_by': acknowledged_by,
            'acknowledged_at': datetime.now(timezone.utc).isoformat()
        })

    def resolve(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Resolve an alert.

        Args:
            alert_id: Alert UUID

        Returns:
            Updated alert or None if not found
        """
        return self.update(alert_id, {'status': 'resolved'})

    def delete(self, alert_id: str) -> bool:
        """Delete an alert.

        Args:
            alert_id: Alert UUID

        Returns:
            True if deleted, False if not found
        """
        response = self.client.table('alerts').delete().eq('id', alert_id).execute()

        return len(response.data) > 0

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
            result = self.resolve(alert['id'])
            if result:
                resolved_count += 1

        return resolved_count

    def resolve_by_building(self, building_id: str) -> int:
        """Resolve all active alerts for a specific building.

        Args:
            building_id: Building UUID

        Returns:
            Number of alerts resolved
        """
        # Get all active alerts for this building
        active_alerts = self.get_active_by_building(building_id)

        if not active_alerts:
            return 0

        # Resolve each alert
        resolved_count = 0
        for alert in active_alerts:
            result = self.resolve(alert['id'])
            if result:
                resolved_count += 1

        return resolved_count


# Singleton instance
_alert_repository_instance: Optional['AlertRepository'] = None


def get_alert_repository() -> 'AlertRepository':
    """Get or create the singleton AlertRepository instance."""
    global _alert_repository_instance
    if _alert_repository_instance is None:
        _alert_repository_instance = AlertRepository()
    return _alert_repository_instance
