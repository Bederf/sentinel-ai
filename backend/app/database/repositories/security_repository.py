"""Repository for security data operations.

Implements dual-write pattern: Supabase (primary) + JSON file (backup).
Gracefully falls back to JSON-only when Supabase is unavailable.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.database.supabase_client import get_supabase_client
from app.models.security import AccessEvent, AlertStatus, SecurityAlert, VisitorStatus

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

    def _load_json_backup(self, data_type: str) -> dict[str, Any]:
        """Load data from JSON backup."""
        json_path = self._get_json_backup_path(data_type)
        if not json_path.exists():
            return {}
        try:
            with open(json_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load JSON backup for {data_type}: {e}")
            return {}

    def _save_json_backup(self, data_type: str, data: dict[str, Any]) -> None:
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

    def get_zones(self, site: str | None = None) -> list[dict[str, Any]]:
        """List access zones for a site."""
        try:
            query = self.client.table("security_access_zones").select("*")
            if site:
                query = query.eq("building_id", site)
            response = query.order("zone_id").execute()
            zones = response.data or []

            backup = self._load_json_backup("security_access_zones")
            backup[site or "_all"] = list(zones)
            self._save_json_backup("security_access_zones", backup)

            return zones
        except Exception as e:
            logger.warning(f"Failed to fetch security zones for {site or 'all'}: {e}")
            backup = self._load_json_backup("security_access_zones")
            return backup.get(site or "_all", [])

    def get_zone(self, zone_id: str) -> dict[str, Any] | None:
        """Get a single access zone by zone_id."""
        try:
            response = self.client.table("security_access_zones").select("*").eq("zone_id", zone_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to fetch security zone {zone_id}: {e}")
            backup = self._load_json_backup("security_access_zones")
            for zones in backup.values():
                for zone in zones:
                    if zone.get("zone_id") == zone_id:
                        return zone
            return None

    def get_badge_events(
        self,
        zone_id: str | None = None,
        limit: int = 100,
        after_hours: bool = False,
        site: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent badge events.

        Queries the canonical security_badge_events table and optionally scopes
        to a zone or building site.
        """
        try:
            query = self.client.table("security_badge_events").select("*")
            if zone_id:
                query = query.eq("zone_id", zone_id)
            elif site:
                zone_ids = [z.get("zone_id") for z in self.get_zones(site) if z.get("zone_id")]
                if not zone_ids:
                    return []
                query = query.in_("zone_id", zone_ids)

            response = query.order("timestamp", desc=True).limit(limit).execute()
            events = response.data or []

            if after_hours:
                events = [e for e in events if self._is_after_hours(e.get("timestamp")) or e.get("after_hours") is True]

            backup_key = site or zone_id or "_all"
            backup = self._load_json_backup("security_badge_events")
            backup[backup_key] = list(events)
            self._save_json_backup("security_badge_events", backup)

            return events
        except Exception as e:
            logger.warning(f"Failed to fetch badge events for {zone_id or site or 'all'}: {e}")
            backup = self._load_json_backup("security_badge_events")
            events = backup.get(zone_id or site or "_all", [])
            if after_hours:
                events = [e for e in events if self._is_after_hours(e.get("timestamp")) or e.get("after_hours") is True]
            return events[:limit]

    def log_badge_event(self, event_data: dict[str, Any]) -> dict[str, Any] | None:
        """Persist a badge event into the canonical security_badge_events table."""
        payload = dict(event_data)
        payload.setdefault("event_id", payload.get("event_id") or f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        payload.setdefault("timestamp", datetime.now().isoformat())

        door_id = payload.get("door_id") or payload.get("access_point_id") or payload.get("equipment_id") or ""
        badge_id = payload.get("badge_id") or payload.get("card_id") or payload.get("person_id") or ""
        person_name = payload.get("person_name") or payload.get("name") or ""
        direction = payload.get("direction") or "entry"
        granted = payload.get("granted")
        if granted is None:
            status = str(payload.get("status", "granted")).lower()
            granted = status not in {"denied", "error", "timeout"}

        record = {
            "event_id": payload["event_id"],
            "door_id": door_id,
            "zone_id": payload.get("zone_id", ""),
            "badge_id": badge_id,
            "person_name": person_name,
            "direction": direction,
            "timestamp": payload["timestamp"],
            "granted": granted,
            "reason": payload.get("reason", ""),
            "event_type": payload.get("event_type") or ("access_granted" if granted else "access_denied"),
        }
        for key in ("clearance_level", "department", "after_hours"):
            if key in payload:
                record[key] = payload[key]
        if "after_hours" not in record:
            record["after_hours"] = self._is_after_hours(record["timestamp"])

        try:
            response = self.client.table("security_badge_events").insert(record).execute()
            saved = response.data[0] if response.data else record

            backup = self._load_json_backup("security_badge_events")
            backup_key = record["zone_id"] or "_all"
            backup.setdefault(backup_key, [])
            backup[backup_key].append(saved)
            self._save_json_backup("security_badge_events", backup)

            return saved
        except Exception as e:
            logger.warning(f"Failed to log badge event in Supabase: {e}")
            backup = self._load_json_backup("security_badge_events")
            backup_key = record["zone_id"] or "_all"
            backup.setdefault(backup_key, [])
            backup[backup_key].append(record)
            self._save_json_backup("security_badge_events", backup)
            return record

    def list_events(
        self,
        site: str,
        limit: int = 100,
        offset: int = 0,
        after_hours: bool = False,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        """List access events for a site."""
        try:
            query = self.client.table("access_events").select("*").eq("site_id", site)

            if location:
                query = query.eq("location", location)

            query = query.order("timestamp", desc=True).limit(limit).offset(offset)
            response = query.execute()
            events = response.data

            if after_hours:
                events = [e for e in events if self._is_after_hours(e.get("timestamp"))]

            # Backup to JSON
            backup = self._load_json_backup("access_events")
            backup[site] = list(events)
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

    def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
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

    def create_event(self, event: AccessEvent) -> dict[str, Any] | None:
        """Create access event."""
        event_data = event.to_dict()

        try:
            response = self.client.table("access_events").insert(event_data).execute()
            record = response.data[0]

            # Backup
            backup = self._load_json_backup("access_events")
            site_id = event.location.split("-")[0]
            if site_id not in backup:
                backup[site_id] = []
            backup[site_id].append(record)
            self._save_json_backup("access_events", backup)

            return record
        except Exception as e:
            logger.warning(f"Failed to create event in Supabase: {e}")
            # Fallback to JSON only
            backup = self._load_json_backup("access_events")
            site_id = event.location.split("-")[0]
            if site_id not in backup:
                backup[site_id] = []
            backup[site_id].append(event_data)
            self._save_json_backup("access_events", backup)
            return event_data

    # ========================================================================
    # Access Points
    # ========================================================================

    def get_access_points(self, site: str) -> list[dict[str, Any]]:
        """List all access points for a site."""
        try:
            zones = {z.get("zone_id"): z for z in self.get_zones(site)}
            response = self.client.table("security_doors").select("*").execute()
            points = []
            for door in response.data or []:
                zone = zones.get(door.get("zone_id"))
                if site and not zone:
                    continue
                points.append(
                    {
                        "access_point_id": door.get("door_id"),
                        "id": door.get("door_id"),
                        "site_id": site,
                        "zone_id": door.get("zone_id"),
                        "location": door.get("name"),
                        "name": door.get("name"),
                        "reader_type": door.get("reader_type"),
                        "status": door.get("status"),
                        "last_event_timestamp": door.get("last_event_time"),
                    }
                )

            # Backup
            backup = self._load_json_backup("access_points")
            backup[site] = points
            self._save_json_backup("access_points", backup)

            return points
        except Exception as e:
            logger.warning(f"Failed to fetch access points for {site}: {e}")
            backup = self._load_json_backup("access_points")
            return backup.get(site, [])

    def get_access_point_by_id(self, point_id: str) -> dict[str, Any] | None:
        """Get single access point by ID."""
        try:
            response = self.client.table("security_doors").select("*").eq("door_id", point_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to fetch access point {point_id}: {e}")
            backup = self._load_json_backup("access_points")
            for points in backup.values():
                for point in points:
                    if point.get("point_id") == point_id:
                        return point
            return None

    def get_doors(self, site: str | None = None) -> list[dict[str, Any]]:
        """List all doors for a site."""
        try:
            zones = {z.get("zone_id"): z for z in self.get_zones(site)}
            response = self.client.table("security_doors").select("*").execute()
            doors = []
            for door in response.data or []:
                if site and door.get("zone_id") not in zones:
                    continue
                doors.append(door)

            backup = self._load_json_backup("security_doors")
            backup[site or "_all"] = list(doors)
            self._save_json_backup("security_doors", backup)

            return doors
        except Exception as e:
            logger.warning(f"Failed to fetch doors for {site or 'all'}: {e}")
            backup = self._load_json_backup("security_doors")
            return backup.get(site or "_all", [])

    def get_door_status(self, door_id: str) -> dict[str, Any] | None:
        """Get a single door by door_id."""
        try:
            response = self.client.table("security_doors").select("*").eq("door_id", door_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to fetch door {door_id}: {e}")
            backup = self._load_json_backup("security_doors")
            for doors in backup.values():
                for door in doors:
                    if door.get("door_id") == door_id:
                        return door
            return None

    def get_cameras(self, site: str | None = None) -> list[dict[str, Any]]:
        """List cameras for a site."""
        try:
            zones = {z.get("zone_id") for z in self.get_zones(site)}
            response = self.client.table("security_cameras").select("*").execute()
            cameras = []
            for camera in response.data or []:
                if site and camera.get("zone_id") not in zones:
                    continue
                cameras.append(camera)

            backup = self._load_json_backup("security_cameras")
            backup[site or "_all"] = list(cameras)
            self._save_json_backup("security_cameras", backup)

            return cameras
        except Exception as e:
            logger.warning(f"Failed to fetch cameras for {site or 'all'}: {e}")
            backup = self._load_json_backup("security_cameras")
            return backup.get(site or "_all", [])

    def get_camera_status(self, camera_id: str) -> dict[str, Any] | None:
        """Get a single camera by camera_id."""
        try:
            response = self.client.table("security_cameras").select("*").eq("camera_id", camera_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to fetch camera {camera_id}: {e}")
            backup = self._load_json_backup("security_cameras")
            for cameras in backup.values():
                for camera in cameras:
                    if camera.get("camera_id") == camera_id:
                        return camera
            return None

    def get_alarm_zones(self, site: str | None = None) -> list[dict[str, Any]]:
        """List alarm zones."""
        try:
            query = self.client.table("security_alarm_zones").select("*")
            response = query.execute()
            zones = response.data or []

            backup = self._load_json_backup("security_alarm_zones")
            backup[site or "_all"] = list(zones)
            self._save_json_backup("security_alarm_zones", backup)

            return zones
        except Exception as e:
            logger.warning(f"Failed to fetch alarm zones for {site or 'all'}: {e}")
            backup = self._load_json_backup("security_alarm_zones")
            return backup.get(site or "_all", [])

    # ========================================================================
    # Visitors
    # ========================================================================

    def list_visitors(self, site: str, limit: int = 50) -> list[dict[str, Any]]:
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

    def record_visit_checkin(self, visitor_id: str) -> dict[str, Any] | None:
        """Record visitor check-in."""
        now = datetime.now()
        try:
            response = (
                self.client.table("visitors")
                .update({"status": VisitorStatus.CHECKED_IN, "checkin_time": now.isoformat()})
                .eq("visitor_id", visitor_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to record check-in for {visitor_id}: {e}")
            return None

    def record_visit_checkout(self, visitor_id: str) -> dict[str, Any] | None:
        """Record visitor check-out."""
        now = datetime.now()
        try:
            response = (
                self.client.table("visitors")
                .update({"status": VisitorStatus.CHECKED_OUT, "checkout_time": now.isoformat()})
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
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get security alerts."""
        try:
            query = self.client.table("security_alerts").select("*").eq("site_id", site)

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

    def create_alert(self, alert: SecurityAlert) -> dict[str, Any] | None:
        """Create security alert."""
        alert_data = alert.to_dict()

        try:
            response = self.client.table("security_alerts").insert(alert_data).execute()
            record = response.data[0]

            # Backup
            backup = self._load_json_backup("security_alerts")
            site_id = alert.site_id
            if site_id not in backup:
                backup[site_id] = []
            backup[site_id].append(record)
            self._save_json_backup("security_alerts", backup)

            return record
        except Exception as e:
            logger.warning(f"Failed to create alert in Supabase: {e}")
            # Fallback to JSON
            backup = self._load_json_backup("security_alerts")
            site_id = alert.site_id
            if site_id not in backup:
                backup[site_id] = []
            backup[site_id].append(alert_data)
            self._save_json_backup("security_alerts", backup)
            return alert_data

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> dict[str, Any] | None:
        """Acknowledge an alert."""
        now = datetime.now()
        try:
            response = (
                self.client.table("security_alerts")
                .update(
                    {
                        "status": AlertStatus.ACKNOWLEDGED,
                        "acknowledged_by": acknowledged_by,
                        "acknowledged_at": now.isoformat(),
                    }
                )
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

    def get_occupancy(self, site: str) -> dict[str, Any]:
        """Get current building occupancy from security badge events."""
        try:
            thirty_min_ago = (datetime.now() - timedelta(minutes=30)).isoformat()
            zones = [z.get("zone_id") for z in self.get_zones(site) if z.get("zone_id")]
            if not zones:
                return {"total_occupancy": 0, "last_updated": datetime.now().isoformat()}

            response = (
                self.client.table("security_badge_events")
                .select("zone_id,direction,granted,timestamp")
                .in_("zone_id", zones)
                .gte("timestamp", thirty_min_ago)
                .order("timestamp", desc=True)
                .execute()
            )

            total = 0
            for event in response.data or []:
                if not event.get("granted", True):
                    continue
                if event.get("direction") == "entry":
                    total += 1
                elif event.get("direction") == "exit":
                    total = max(0, total - 1)

            return {
                "total_occupancy": total,
                "last_updated": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"total_occupancy": 0, "error": str(e)}

    # ========================================================================
    # Helper Methods
    # ========================================================================

    @staticmethod
    def _is_after_hours(timestamp_str: str | None) -> bool:
        """Check if timestamp is during after-hours (18:00-06:00)."""
        if not timestamp_str:
            return False
        try:
            dt = datetime.fromisoformat(timestamp_str)
            hour = dt.hour
            return hour >= 18 or hour < 6
        except Exception:
            return False


# Singleton accessor
_security_repository_instance: Optional["SecurityRepository"] = None


def get_security_repository() -> SecurityRepository:
    """Get or create the SecurityRepository singleton."""
    global _security_repository_instance
    if _security_repository_instance is None:
        _security_repository_instance = SecurityRepository()
    return _security_repository_instance
