"""Security module service.

Provides access control monitoring, CCTV camera status, alarm zone management,
badge event tracking, and system status overview.
Uses SecurityRepository for all data operations (Supabase + JSON fallback).
"""

import logging
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from app.database.repositories.security_repository import get_security_repository
from app.models.security import (
    AccessLevel,
    AccessZone,
    AlarmStatus,
    AlarmZone,
    ArmType,
    BadgeEvent,
    Camera,
    CameraStatus,
    Door,
    DoorStatus,
    EventDirection,
    ReaderType,
    SecuritySystemStatus,
)

logger = logging.getLogger(__name__)

_instance: Optional["SecurityService"] = None


class SecurityService:
    """Service for security module operations."""

    def __init__(self):
        self._repo = get_security_repository()

    def get_system_status(self) -> SecuritySystemStatus:
        """Get aggregate security system status."""
        doors = self.get_doors()
        cameras = self.get_cameras()
        alarm_zones = self.get_alarm_zones()

        doors_secure = sum(1 for d in doors if d.status in (DoorStatus.LOCKED, DoorStatus.CLOSED))
        cameras_online = sum(1 for c in cameras if c.status == CameraStatus.ONLINE)
        alarm_zones_armed = sum(1 for az in alarm_zones if az.status == AlarmStatus.ARMED)

        # Count active alerts (denied events in last 24h + triggered alarms + camera faults)
        active_alerts = 0
        active_alerts += sum(1 for az in alarm_zones if az.status == AlarmStatus.TRIGGERED)
        active_alerts += sum(1 for c in cameras if c.status == CameraStatus.FAULT)
        active_alerts += sum(1 for d in doors if d.status == DoorStatus.FAULT)

        # Calculate building occupancy from badge events
        from app.services.security_occupancy_service import get_security_occupancy_service

        occ_service = get_security_occupancy_service()
        building_occ = occ_service.get_building_occupancy()
        occupancy_total = building_occ.get("total_occupancy", 0)

        return SecuritySystemStatus(
            total_doors=len(doors),
            doors_secure=doors_secure,
            cameras_online=cameras_online,
            cameras_total=len(cameras),
            alarm_zones_armed=alarm_zones_armed,
            alarm_zones_total=len(alarm_zones),
            active_alerts=active_alerts,
            occupancy_total=occupancy_total,
        )

    def get_access_zones(self) -> list[AccessZone]:
        """Get all access zones with current door status."""
        raw_zones = self._repo.get_zones()
        zones = []
        for z in raw_zones:
            try:
                zones.append(
                    AccessZone(
                        zone_id=z.get("zone_id", ""),
                        name=z.get("name", ""),
                        floor=z.get("floor", ""),
                        access_level=AccessLevel(z.get("access_level", "restricted")),
                        doors=z.get("doors", []),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing access zone: {e}")
        return zones

    def get_doors(self) -> list[Door]:
        """Get all doors with status."""
        raw_doors = self._repo.get_doors()
        doors = []
        for d in raw_doors:
            try:
                doors.append(
                    Door(
                        door_id=d.get("door_id", ""),
                        name=d.get("name", ""),
                        zone_id=d.get("zone_id", ""),
                        status=DoorStatus(d.get("status", "locked")),
                        reader_type=ReaderType(d.get("reader_type", "card")),
                        last_event_time=d.get("last_event_time"),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing door: {e}")
        return doors

    def get_door_status(self, door_id: str) -> Door | None:
        """Get a single door's status."""
        raw_door = self._repo.get_door_status(door_id)
        if not raw_door:
            return None
        try:
            return Door(
                door_id=raw_door.get("door_id", ""),
                name=raw_door.get("name", ""),
                zone_id=raw_door.get("zone_id", ""),
                status=DoorStatus(raw_door.get("status", "locked")),
                reader_type=ReaderType(raw_door.get("reader_type", "card")),
                last_event_time=raw_door.get("last_event_time"),
            )
        except Exception as e:
            logger.warning(f"Error parsing door {door_id}: {e}")
            return None

    def get_recent_badge_events(self, zone_id: str = None, limit: int = 50) -> list[BadgeEvent]:
        """Get recent badge events with optional zone filter."""
        raw_events = self._repo.get_badge_events(zone_id=zone_id, limit=limit)
        events = []
        for e in raw_events:
            try:
                events.append(
                    BadgeEvent(
                        event_id=e.get("event_id", ""),
                        door_id=e.get("door_id", ""),
                        zone_id=e.get("zone_id", ""),
                        badge_id=e.get("badge_id", ""),
                        person_name=e.get("person_name", ""),
                        direction=EventDirection(e.get("direction", "entry")),
                        timestamp=e.get("timestamp", datetime.utcnow()),
                        granted=e.get("granted", True),
                        reason=e.get("reason", ""),
                    )
                )
            except Exception as e_err:
                logger.warning(f"Error parsing badge event: {e_err}")
        return events

    def process_badge_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Validate and log a badge event."""
        # Generate event ID if not provided
        if "event_id" not in event_data:
            event_data["event_id"] = f"EVT-{uuid4().hex[:8].upper()}"
        if "timestamp" not in event_data:
            event_data["timestamp"] = datetime.now(UTC).isoformat()
        if "granted" not in event_data:
            event_data["granted"] = True
        if "reason" not in event_data:
            event_data["reason"] = "Valid badge"

        # Check access level restrictions
        zone_id = event_data.get("zone_id", "")
        zone = self._repo.get_zone(zone_id)
        if zone:
            access_level = zone.get("access_level", "public")
            if access_level == "critical":
                # Critical zones could have additional checks
                event_data.setdefault("reason", "Critical zone access")

        # Check time restrictions (after hours = 20:00-06:00)
        try:
            ts = event_data.get("timestamp", "")
            if isinstance(ts, str) and "T" in ts:
                hour = int(ts.split("T")[1][:2])
                if hour >= 20 or hour < 6:
                    event_data["reason"] = event_data.get("reason", "") + " (after-hours)"
        except (ValueError, IndexError):
            pass

        # Log the event
        result = self._repo.log_badge_event(event_data)
        return result or event_data

    def get_cameras(self) -> list[Camera]:
        """Get all cameras with status."""
        raw_cameras = self._repo.get_cameras()
        cameras = []
        for c in raw_cameras:
            try:
                cameras.append(
                    Camera(
                        camera_id=c.get("camera_id", ""),
                        name=c.get("name", ""),
                        zone_id=c.get("zone_id", ""),
                        floor=c.get("floor", ""),
                        status=CameraStatus(c.get("status", "online")),
                        type=c.get("type", "fixed"),
                        resolution=c.get("resolution", "1080p"),
                        has_analytics=c.get("has_analytics", False),
                        motion_detected=c.get("motion_detected", False),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing camera: {e}")
        return cameras

    def get_camera_status(self, camera_id: str) -> Camera | None:
        """Get a single camera's status."""
        raw_camera = self._repo.get_camera_status(camera_id)
        if not raw_camera:
            return None
        try:
            return Camera(
                camera_id=raw_camera.get("camera_id", ""),
                name=raw_camera.get("name", ""),
                zone_id=raw_camera.get("zone_id", ""),
                floor=raw_camera.get("floor", ""),
                status=CameraStatus(raw_camera.get("status", "online")),
                type=raw_camera.get("type", "fixed"),
                resolution=raw_camera.get("resolution", "1080p"),
                has_analytics=raw_camera.get("has_analytics", False),
                motion_detected=raw_camera.get("motion_detected", False),
            )
        except Exception as e:
            logger.warning(f"Error parsing camera {camera_id}: {e}")
            return None

    def get_alarm_zones(self) -> list[AlarmZone]:
        """Get all alarm zones."""
        raw_zones = self._repo.get_alarm_zones()
        zones = []
        for az in raw_zones:
            try:
                zones.append(
                    AlarmZone(
                        zone_id=az.get("zone_id", ""),
                        name=az.get("name", ""),
                        status=AlarmStatus(az.get("status", "disarmed")),
                        arm_type=ArmType(az.get("arm_type", "full")),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing alarm zone: {e}")
        return zones

    def arm_alarm_zone(self, zone_id: str, arm_type: str = "full") -> dict[str, Any]:
        """Arm an alarm zone."""
        self._repo.update_alarm_zone_status(
            zone_id,
            {
                "status": "armed",
                "arm_type": arm_type,
            },
        )
        return {"zone_id": zone_id, "status": "armed", "arm_type": arm_type}

    def disarm_alarm_zone(self, zone_id: str) -> dict[str, Any]:
        """Disarm an alarm zone."""
        self._repo.update_alarm_zone_status(
            zone_id,
            {
                "status": "disarmed",
            },
        )
        return {"zone_id": zone_id, "status": "disarmed"}

    def trigger_alarm(self, zone_id: str) -> dict[str, Any]:
        """Trigger an alarm zone."""
        self._repo.update_alarm_zone_status(
            zone_id,
            {
                "status": "triggered",
            },
        )
        return {
            "zone_id": zone_id,
            "status": "triggered",
            "message": f"Alarm triggered in zone {zone_id}",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_after_hours_events(self, since: str = None) -> list[BadgeEvent]:
        """Get events outside business hours (06:00-20:00)."""
        events = self.get_recent_badge_events(limit=200)
        after_hours = []
        for evt in events:
            try:
                ts = evt.timestamp
                if isinstance(ts, str):
                    hour = int(ts.split("T")[1][:2]) if "T" in ts else 12
                elif isinstance(ts, datetime):
                    hour = ts.hour
                else:
                    continue
                if hour >= 20 or hour < 6:
                    after_hours.append(evt)
            except (ValueError, IndexError, AttributeError):
                continue
        return after_hours

    def get_denied_access_events(self, since: str = None) -> list[BadgeEvent]:
        """Get denied entry events."""
        events = self.get_recent_badge_events(limit=200)
        return [e for e in events if not e.granted]


def get_security_service() -> SecurityService:
    """Get or create singleton SecurityService."""
    global _instance
    if _instance is None:
        _instance = SecurityService()
    return _instance
