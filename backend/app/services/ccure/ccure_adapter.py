"""C•CURE 9000 Access Control Integration Adapter.

This adapter provides integration with Johnson Controls / Software House
C•CURE 9000 access control platform via the victor Web Service API.

SENTINEL Integration Philosophy:
- Read-only observer (no direct door control commands)
- Intelligence overlay (anomaly detection, cross-system correlation)
- Rapid client onboarding when they have C•CURE licenses

Integration Options:
1. Local seeded mode - Uses ccure_seed_data.json when explicitly enabled
2. Live Mode - victor Web Service API (requires Partner Program license)

Usage:
    adapter = CCureAdapter(seeded_mode=False)
    await adapter.connect()
    events = await adapter.get_badge_events(since=datetime.now() - timedelta(hours=24))
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.models.visit import Visit


@dataclass
class CCureController:
    """Represents an iSTAR controller in C•CURE."""

    controller_id: str
    name: str
    model: str
    firmware: str
    encryption_mode: str
    tamper_status: str
    last_seen: datetime
    ip_address: str
    reader_count: int
    status: str


@dataclass
class CCurePersonnel:
    """Represents a personnel record in C•CURE."""

    badge_id: str
    first_name: str
    last_name: str
    email: str
    title: str
    department: str
    access_level: str


logger = logging.getLogger(__name__)


class CCureAdapter:
    """C•CURE 9000 integration adapter.

    Phase 58.2: Local seeded mode with sample data
    Phase 58.3: Live mode with victor Web Service API
    """

    def __init__(
        self,
        api_url: str | None = None,
        license_guid: str | None = None,
        username: str | None = None,
        password: str | None = None,
        seeded_mode: bool = False,
    ):
        self.api_url = api_url
        self.license_guid = license_guid
        self.username = username
        self.password = password
        self.seeded_mode = seeded_mode
        self._seed_data = None
        self._token = None
        self._connected = False

    async def connect(self) -> bool:
        """Establish connection to C•CURE system."""
        if self.seeded_mode:
            logger.info("CCureAdapter: Using local seeded mode (Partner license required for live API)")
            self._seed_data = self._load_seed_data()
            self._connected = True
            return True
        else:
            # TODO Phase 58.3: Implement victor Web Service API authentication
            # POST {api_url}/auth/token with license_guid, username, password
            # Store JWT token in self._token
            logger.warning("CCureAdapter: Live mode not implemented yet - requires Partner Program license")
            return False

    async def disconnect(self) -> None:
        """Disconnect from C•CURE system."""
        # No persistent connection needed for C•CURE integration
        # API calls are stateless
        self._connected = False

    def _load_seed_data(self) -> dict:
        """Load seeded data from ccure_seed_data.json. Returns empty dict if absent."""
        seed_file = Path(__file__).parent.parent.parent / "data" / "ccure_seed_data.json"
        if not seed_file.exists():
            logger.warning("CCureAdapter: seed data file not found at %s", seed_file)
            return {}
        with open(seed_file) as f:
            return json.load(f)

    async def get_badge_events(
        self,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch badge events from C•CURE.

        Args:
            since: Only return events after this timestamp (default: last 24 hours)
            limit: Maximum number of events to return

        Returns:
            List of badge events with SENTINEL-normalized format
        """
        if self.seeded_mode:
            events = self._seed_data.get("badge_events", [])

            # Filter by timestamp if provided
            if since:
                events = [e for e in events if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) > since]

            return events[:limit]
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/access-events?since={since}&limit={limit}
            # Headers: {"Authorization": f"Bearer {self._token}"}
            pass

    async def get_door_status(self, door_id: str) -> dict:
        """Get door/reader status from C•CURE.

        Args:
            door_id: C•CURE door identifier

        Returns:
            Door status dict with keys: door_id, name, status, reader_status, last_event
        """
        if self.seeded_mode:
            doors = {d["door_id"]: d for d in self._seed_data.get("doors", [])}
            return doors.get(door_id, {})
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/doors/{door_id}/status
            pass

    async def get_controllers(self) -> list[CCureController]:
        """Get all iSTAR controllers and their health status.

        Returns:
            List of CCureController objects with tamper status, online/offline
        """
        if self.seeded_mode and self._seed_data:
            controllers_data = self._seed_data.get("controllers", [])
            return [
                CCureController(
                    controller_id=c["controller_id"],
                    name=c["name"],
                    model=c["model"],
                    firmware=c["firmware"],
                    encryption_mode=c["encryption_mode"],
                    tamper_status=c.get("tamper_status", "normal"),
                    last_seen=datetime.fromisoformat(c["last_seen"].replace("Z", "+00:00")),
                    ip_address=c["ip_address"],
                    reader_count=c["reader_count"],
                    status=c.get("status", "online"),
                )
                for c in controllers_data
            ]
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/controllers
            return []

    async def get_occupancy(self, zone_id: str) -> dict:
        """Get real-time occupancy from C•CURE anti-passback zones.

        Args:
            zone_id: C•CURE zone identifier

        Returns:
            Dict with keys: zone_id, current_count, max_occupancy, anti_passback_enabled
        """
        if self.seeded_mode:
            zones = {z["zone_id"]: z for z in self._seed_data.get("zones", [])}
            return zones.get(zone_id, {})
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/zones/{zone_id}/occupancy
            pass

    async def get_personnel(self, badge_id: str) -> CCurePersonnel | None:
        """Lookup personnel details by badge ID.

        Args:
            badge_id: Badge/credential number

        Returns:
            CCurePersonnel object or None if not found
        """
        if self.seeded_mode:
            personnel_list = self._seed_data.get("personnel", [])
            for p in personnel_list:
                if p["badge_id"] == badge_id:
                    return CCurePersonnel(**p)
            return None
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/personnel?badge_id={badge_id}
            pass

    # -------------------------------------------------------------------------
    # Visit access management — Phase 176-03
    # -------------------------------------------------------------------------

    def issue_visitor_access(self, visit: "Visit") -> dict:
        """Issue visitor access to C-CURE.

        Args:
            visit: Visit model with visitor details and meeting window.

        Returns:
            dict with keys: success (bool), card_id (str|None), message (str)
        """
        # Access group mapping: building_id -> C-CURE access group
        access_groups = {
            "site-001": "VISITOR_FAIRLANDS",
            "site-002": "VISITOR_SANDTON",
            "site-003": "VISITOR_CENTURION",
            "site-004": "VISITOR_UMHLANGA",
        }
        group = access_groups.get(visit.building_id, "VISITOR_DEFAULT")

        # Build access payload (used in live mode; logged in demo mode)
        _payload = {
            "person_name": visit.visitor_name or visit.visitor_email,
            "email": visit.visitor_email,
            "access_group": group,
            "valid_until": visit.meeting_end.isoformat(),
            "building": visit.building_id,
        }
        logger.debug(f"[CCureAdapter] Visit access payload: {_payload}")

        if self.seeded_mode:
            # Demo mode: return simulated badge
            card_id = f"VIS-{visit.id.hex[:8].upper()}"
            logger.info(f"[CCureAdapter] Demo access issued: card_id={card_id}, group={group}")
            return {"success": True, "card_id": card_id, "message": "Demo access issued"}

        # Live mode: call C-CURE victor Web Service API
        # POST {api_url}/Access/GrantAccess
        # TODO Phase 58.3: Implement live API call with self._token auth
        logger.warning("[CCureAdapter] Live visit access not implemented — requires Partner license")
        return {"success": False, "card_id": None, "message": "Live C-CURE API not implemented"}

    def revoke_visitor_access(self, visit_id: "UUID") -> dict:
        """Revoke visitor access from C-CURE.

        Args:
            visit_id: UUID of the visit whose access should be revoked.

        Returns:
            dict with keys: success (bool), message (str)
        """
        if self.seeded_mode:
            logger.info(f"[CCureAdapter] Demo access revoked for visit_id={visit_id}")
            return {"success": True, "message": "Demo access revoked"}

        # Live mode: call C-CURE victor Web Service API
        # POST {api_url}/Access/RevokeAccess
        # TODO Phase 58.3: Implement live API call with self._token auth
        logger.warning("[CCureAdapter] Live visit revoke not implemented — requires Partner license")
        return {"success": False, "message": "Live C-CURE API not implemented"}
