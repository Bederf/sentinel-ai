"""Repository for security data operations.

Implements dual-write pattern: Supabase (primary) + JSON file (backup).
Gracefully falls back to JSON-only when Supabase is unavailable.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path

from app.database.supabase_client import get_supabase_client
from app.models.security import (
    AccessEvent, SecurityAlert,
    AccessStatus, VisitorStatus, AlertStatus
)

logger = logging.getLogger(__name__)


class SecurityRepository:
    """Repository for security data with dual-write support."""

    def __init__(self):
        """Initialize repository with Supabase client."""
        self.client = get_supabase_client()
        self.json_backup_dir = Path("backend/app/data/security")

    def _get_json_backup_path(self, data_type: str) -> Path:
        """Get path to JSON backup file for a data type."""
        self.json_backup_dir.mkdir(parents=True, exist_ok=True)
        return self.json_backup_dir / f"{data_type}.json"

    def _load_json_backup(self, data_type: str) -> Dict[str, Any]:
        """Load data from JSON backup."""
        json_path = self._get_json_backup_path(data_type)
        if not json_path.exists():
            return {}
        try:
            with open(json_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load JSON backup for {data_type}: {e}")
            return {}

    def _save_json_backup(self, data_type: str, data: Dict[str, Any]) -> None:
        """Save data to JSON backup."""
        json_path = self._get_json_backup_path(data_type)
        try:
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save JSON backup for {data_type}: {e}")

    # ========================================================================
    # Access Events
    # ========================================================================

    def list_events(
        self,
        site: str,
        limit: int = 100,
        offset: int = 0,
        after_hours: bool = False,
        location: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List access events for a site."""
        try:
            query = self.client.table("access_events").select("*").eq("building_id", site)

            if location:
                query = query.eq("location", location)

            query = query.order("timestamp", desc=True).limit(limit).offset(offset)
            response = query.execute()
            events = response.data

            if after_hours:
                events = [e for e in events if self._is_after_hours(e.get("timestamp"))]

            # Backup to JSON
            backup = self._load_json_backup("access_events")
            backup[site] = [e for e in events]
            self._save_json_backup("access_events", backup)

            return events
        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON backup: {e}")
            backup = self._load_json_backup("access_events")
            events = backup.get(site, [])

            if location:
                events = [e for e in events if e.get("location") == location]

            if after_hours:
                events = [e for e in events if self._is_after_hours(e.get("timestamp"))]

            return events[:limit]

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get single access event by ID."""
        try:
            response = self.client.table("access_events").select("*").eq("event_id", event_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to fetch event {event_id}: {e}")
            backup = self._load_json_backup("access_events")
            for events in backup.values():
                for event in events:
                    if event.get("event_id") == event_id:
                        return event
            return None

    def create_event(self, event: AccessEvent) -> Optional[Dict[str, Any]]:
        """Create access event."""
        event_data = event.to_dict()

        try:
            response = self.client.table("access_events").insert(event_data).execute()
            record = response.data[0]

            # Backup
            backup = self._load_json_backup("access_events")
            building_id = event.location.split("-")[0]
            if building_id not in backup:
                backup[building_id] = []
            backup[building_id].append(record)
            self._save_json_backup("access_events", backup)

            return record
        except Exception as e:
            logger.warning(f"Failed to create event in Supabase: {e}")
            # Fallback to JSON only
            backup = self._load_json_backup("access_events")
            building_id = event.location.split("-")[0]
            if building_id not in backup:
                backup[building_id] = []
            backup[building_id].append(event_data)
            self._save_json_backup("access_events", backup)
            return event_data

    # ========================================================================
    # Access Points
    # ========================================================================

    def get_access_points(self, site: str) -> List[Dict[str, Any]]:
        """List all access points for a site."""
        try:
            response = self.client.table("access_points").select("*").eq("building_id", site).execute()
            points = response.data

            # Backup
            backup = self._load_json_backup("access_points")
            backup[site] = points
            self._save_json_backup("access_points", backup)

            return points
        except Exception as e:
            logger.warning(f"Failed to fetch access points for {site}: {e}")
            backup = self._load_json_backup("access_points")
            return backup.get(site, [])

    def get_access_point_by_id(self, point_id: str) -> Optional[Dict[str, Any]]:
        """Get single access point by ID."""
        try:
            response = self.client.table("access_points").select("*").eq("point_id", point_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to fetch access point {point_id}: {e}")
            backup = self._load_json_backup("access_points")
            for points in backup.values():
                for point in points:
                    if point.get("point_id") == point_id:
                        return point
            return None

    # ========================================================================
    # Visitors
    # ========================================================================

    def list_visitors(self, site: str, limit: int = 50) -> List[Dict[str, Any]]:
        """List active visitors for a site."""
        try:
            response = (
                self.client.table("visitors")
                .select("*")
                .eq("site", site)
                .in_("status", ["pending", "checked_in"])
                .order("visit_date", desc=True)
                .limit(limit)
                .execute()
            )
            visitors = response.data

            # Backup
            backup = self._load_json_backup("visitors")
            backup[site] = visitors
            self._save_json_backup("visitors", backup)

            return visitors
        except Exception as e:
            logger.warning(f"Failed to fetch visitors for {site}: {e}")
            backup = self._load_json_backup("visitors")
            return backup.get(site, [])

    def record_visit_checkin(self, visitor_id: str) -> Optional[Dict[str, Any]]:
        """Record visitor check-in."""
        now = datetime.now()
        try:
            response = (
                self.client.table("visitors")
                .update({
                    "status": VisitorStatus.CHECKED_IN,
                    "checkin_time": now.isoformat()
                })
                .eq("visitor_id", visitor_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to record check-in for {visitor_id}: {e}")
            return None

    def record_visit_checkout(self, visitor_id: str) -> Optional[Dict[str, Any]]:
        """Record visitor check-out."""
        now = datetime.now()
        try:
            response = (
                self.client.table("visitors")
                .update({
                    "status": VisitorStatus.CHECKED_OUT,
                    "checkout_time": now.isoformat()
                })
                .eq("visitor_id", visitor_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to record check-out for {visitor_id}: {e}")
            return None

    # ========================================================================
    # Alerts
    # ========================================================================

    def get_alerts(
        self,
        site: str,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get security alerts."""
        try:
            query = self.client.table("security_alerts").select("*").eq("building_id", site)

            if severity:
                query = query.eq("severity", severity)

            query = query.order("timestamp", desc=True).limit(limit)
            response = query.execute()
            alerts = response.data

            # Backup
            backup = self._load_json_backup("security_alerts")
            backup[site] = alerts
            self._save_json_backup("security_alerts", backup)

            return alerts
        except Exception as e:
            logger.warning(f"Failed to fetch alerts for {site}: {e}")
            backup = self._load_json_backup("security_alerts")
            alerts = backup.get(site, [])

            if severity:
                alerts = [a for a in alerts if a.get("severity") == severity]

            return alerts[:limit]

    def create_alert(self, alert: SecurityAlert) -> Optional[Dict[str, Any]]:
        """Create security alert."""
        alert_data = alert.to_dict()

        try:
            response = self.client.table("security_alerts").insert(alert_data).execute()
            record = response.data[0]

            # Backup
            backup = self._load_json_backup("security_alerts")
            building_id = alert.building_id
            if building_id not in backup:
                backup[building_id] = []
            backup[building_id].append(record)
            self._save_json_backup("security_alerts", backup)

            return record
        except Exception as e:
            logger.warning(f"Failed to create alert in Supabase: {e}")
            # Fallback to JSON
            backup = self._load_json_backup("security_alerts")
            building_id = alert.building_id
            if building_id not in backup:
                backup[building_id] = []
            backup[building_id].append(alert_data)
            self._save_json_backup("security_alerts", backup)
            return alert_data

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> Optional[Dict[str, Any]]:
        """Acknowledge an alert."""
        now = datetime.now()
        try:
            response = (
                self.client.table("security_alerts")
                .update({
                    "status": AlertStatus.ACKNOWLEDGED,
                    "acknowledged_by": acknowledged_by,
                    "acknowledged_at": now.isoformat()
                })
                .eq("alert_id", alert_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to acknowledge alert {alert_id}: {e}")
            return None

    # ========================================================================
    # Occupancy (for cross-module integration)
    # ========================================================================

    def get_occupancy(self, site: str) -> Dict[str, Any]:
        """Get current building occupancy from badge events and visitors."""
        try:
            # Get recent badge access (last 30 min)
            thirty_min_ago = (datetime.now() - timedelta(minutes=30)).isoformat()

            response = (
                self.client.table("access_events")
                .select("*")
                .eq("building_id", site)
                .gte("timestamp", thirty_min_ago)
                .eq("status", AccessStatus.GRANTED)
                .execute()
            )

            recent_events = response.data

            # Count unique people (granted access in last 30 min)
            people_in = set()
            for event in recent_events:
                if event.get("status") == AccessStatus.GRANTED:
                    people_in.add(event.get("person_name"))

            # Add checked-in visitors
            visitors_resp = (
                self.client.table("visitors")
                .select("*")
                .eq("site", site)
                .eq("status", VisitorStatus.CHECKED_IN)
                .execute()
            )

            for visitor in visitors_resp.data:
                people_in.add(visitor.get("name"))

            return {
                "total_occupancy": len(people_in),
                "by_floor": {"L0": len([p for p in people_in if True])},  # Simplified
                "by_zone": {},
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"Failed to calculate occupancy for {site}: {e}")
            return {
                "total_occupancy": 0,
                "by_floor": {},
                "by_zone": {},
                "last_updated": datetime.now().isoformat()
            }

    # ========================================================================
    # Helper Methods
    # ========================================================================

    @staticmethod
    def _is_after_hours(timestamp_str: Optional[str]) -> bool:
        """Check if timestamp is during after-hours (18:00-06:00)."""
        if not timestamp_str:
            return False
        try:
            dt = datetime.fromisoformat(timestamp_str)
            hour = dt.hour
            return hour >= 18 or hour < 6
        except Exception:
            return False
