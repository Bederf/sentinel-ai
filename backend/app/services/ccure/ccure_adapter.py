"""C•CURE 9000 Access Control Integration Adapter.

This adapter provides integration with Johnson Controls / Software House
C•CURE 9000 access control platform via the victor Web Service API.

SENTINEL Integration Philosophy:
- Read-only observer (no direct door control commands)
- Intelligence overlay (anomaly detection, cross-system correlation)
- Rapid client onboarding when they have C•CURE licenses

Integration Options:
1. Demo Mode (default) - Uses ccure_demo_data.json
2. Live Mode - victor Web Service API (requires Partner Program license)

Usage:
    adapter = CCureAdapter(demo_mode=True)
    await adapter.connect()
    events = await adapter.get_badge_events(since=datetime.now() - timedelta(hours=24))
"""

from typing import Dict, List, Optional
from datetime import datetime
import json
import logging
from pathlib import Path

from app.models.security import CCureController, CCurePersonnel

logger = logging.getLogger(__name__)


class CCureAdapter:
    """C•CURE 9000 integration adapter.

    Phase 58.2: Demo mode with mock data
    Phase 58.3: Live mode with victor Web Service API
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        license_guid: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        demo_mode: bool = True,
    ):
        self.api_url = api_url
        self.license_guid = license_guid
        self.username = username
        self.password = password
        self.demo_mode = demo_mode
        self._demo_data = None
        self._token = None
        self._connected = False

    async def connect(self) -> bool:
        """Establish connection to C•CURE system."""
        if self.demo_mode:
            logger.info("CCureAdapter: Using DEMO MODE (Partner license required for live API)")
            self._demo_data = self._load_demo_data()
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

    def _load_demo_data(self) -> Dict:
        """Load demo data from ccure_demo_data.json."""
        demo_file = Path(__file__).parent.parent.parent / "data" / "ccure_demo_data.json"
        with open(demo_file, "r") as f:
            return json.load(f)

    async def get_badge_events(
        self,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Fetch badge events from C•CURE.

        Args:
            since: Only return events after this timestamp (default: last 24 hours)
            limit: Maximum number of events to return

        Returns:
            List of badge events with SENTINEL-normalized format
        """
        if self.demo_mode:
            events = self._demo_data.get("badge_events", [])

            # Filter by timestamp if provided
            if since:
                events = [
                    e
                    for e in events
                    if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) > since
                ]

            return events[:limit]
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/access-events?since={since}&limit={limit}
            # Headers: {"Authorization": f"Bearer {self._token}"}
            pass

    async def get_door_status(self, door_id: str) -> Dict:
        """Get door/reader status from C•CURE.

        Args:
            door_id: C•CURE door identifier

        Returns:
            Door status dict with keys: door_id, name, status, reader_status, last_event
        """
        if self.demo_mode:
            doors = {d["door_id"]: d for d in self._demo_data.get("doors", [])}
            return doors.get(door_id, {})
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/doors/{door_id}/status
            pass

    async def get_controllers(self) -> List[CCureController]:
        """Get all iSTAR controllers and their health status.

        Returns:
            List of CCureController objects with tamper status, online/offline
        """
        if self.demo_mode:
            controllers_data = self._demo_data.get("controllers", [])
            return [
                CCureController(
                    controller_id=c["controller_id"],
                    name=c["name"],
                    model=c["model"],
                    firmware=c["firmware"],
                    encryption_mode=c["encryption_mode"],
                    tamper_status=c.get("tamper_status", "normal"),
                    last_seen=datetime.fromisoformat(
                        c["last_seen"].replace("Z", "+00:00")
                    ),
                    ip_address=c["ip_address"],
                    reader_count=c["reader_count"],
                    status=c.get("status", "online"),
                )
                for c in controllers_data
            ]
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/controllers
            pass

    async def get_occupancy(self, zone_id: str) -> Dict:
        """Get real-time occupancy from C•CURE anti-passback zones.

        Args:
            zone_id: C•CURE zone identifier

        Returns:
            Dict with keys: zone_id, current_count, max_occupancy, anti_passback_enabled
        """
        if self.demo_mode:
            zones = {z["zone_id"]: z for z in self._demo_data.get("zones", [])}
            return zones.get(zone_id, {})
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/zones/{zone_id}/occupancy
            pass

    async def get_personnel(self, badge_id: str) -> Optional[CCurePersonnel]:
        """Lookup personnel details by badge ID.

        Args:
            badge_id: Badge/credential number

        Returns:
            CCurePersonnel object or None if not found
        """
        if self.demo_mode:
            personnel_list = self._demo_data.get("personnel", [])
            for p in personnel_list:
                if p["badge_id"] == badge_id:
                    return CCurePersonnel(**p)
            return None
        else:
            # TODO Phase 58.3: Implement victor API call
            # GET {api_url}/api/personnel?badge_id={badge_id}
            pass
