"""EskomSePush API v2.0 integration service.

Provides real-time load shedding status and area-specific schedules
from the EskomSePush API (https://eskomsepush.gumroad.com/l/api).

API Base: https://developer.sepush.co.za/business/2.0/
Auth: token header
Endpoints used:
  GET /status - National load shedding status (Eskom + Cape Town)
  GET /area_information?id={area_id} - Area-specific events & schedule
  GET /areas_search?text={query} - Search for area IDs
  GET /api_allowance - Check remaining API quota
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

ESP_BASE_URL = "https://developer.sepush.co.za/business/2.0"


@dataclass
class CachedResponse:
    """Cached API response with TTL."""
    data: Any
    fetched_at: float
    ttl_seconds: int

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.fetched_at) > self.ttl_seconds


@dataclass
class NationalStatus:
    """Parsed national load shedding status."""
    stage: int
    stage_updated: str
    name: str
    next_stages: List[Dict[str, str]]


@dataclass
class AreaEvent:
    """A scheduled load shedding event for an area."""
    start: str
    end: str
    note: str
    stage: int


@dataclass
class EskomSePushStatus:
    """Combined status from EskomSePush API."""
    eskom: NationalStatus
    capetown: Optional[NationalStatus]
    area_events: List[AreaEvent]
    area_name: str
    area_region: str
    fetched_at: str


class EskomSePushService:
    """Service for interacting with the EskomSePush API v2.0."""

    def __init__(self):
        self._cache: Dict[str, CachedResponse] = {}

    @property
    def _token(self) -> str:
        return settings.eskomsepush_api_token

    @property
    def _area_id(self) -> str:
        return settings.eskomsepush_area_id

    @property
    def _cache_ttl(self) -> int:
        return settings.eskomsepush_cache_seconds

    @property
    def is_configured(self) -> bool:
        """Check if the service has valid API credentials."""
        return bool(self._token)

    def _get_cached(self, key: str) -> Optional[Any]:
        cached = self._cache.get(key)
        if cached and not cached.is_expired:
            return cached.data
        return None

    def _set_cached(self, key: str, data: Any) -> None:
        self._cache[key] = CachedResponse(
            data=data,
            fetched_at=time.time(),
            ttl_seconds=self._cache_ttl,
        )

    async def _api_get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make authenticated GET request to EskomSePush API."""
        url = f"{ESP_BASE_URL}/{endpoint}"
        headers = {"token": self._token}

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_status(self) -> Dict:
        """Get national load shedding status.

        Returns:
            {
                "status": {
                    "eskom": {
                        "name": "National",
                        "stage": "0",
                        "stage_updated": "...",
                        "next_stages": [{"stage": "2", "stage_start_timestamp": "..."}]
                    },
                    "capetown": { ... }
                }
            }
        """
        cached = self._get_cached("status")
        if cached:
            return cached

        data = await self._api_get("status")
        self._set_cached("status", data)
        return data

    async def get_area_information(self, area_id: Optional[str] = None) -> Dict:
        """Get area-specific load shedding events and schedule.

        Args:
            area_id: EskomSePush area ID. Falls back to configured default.

        Returns:
            {
                "events": [{"start": "...", "end": "...", "note": "Stage 2"}],
                "info": {"name": "...", "region": "..."},
                "schedule": {"days": [...], "source": "..."}
            }
        """
        aid = area_id or self._area_id
        if not aid:
            return {"events": [], "info": {"name": "Unknown", "region": ""}, "schedule": {"days": [], "source": ""}}

        cache_key = f"area_{aid}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        data = await self._api_get("area_information", params={"id": aid})
        self._set_cached(cache_key, data)
        return data

    async def search_areas(self, text: str) -> List[Dict]:
        """Search for areas by name.

        Returns list of matching areas with id, name, region.
        """
        data = await self._api_get("areas_search", params={"text": text})
        return data.get("areas", [])

    async def get_allowance(self) -> Dict:
        """Check remaining API quota."""
        return await self._api_get("api_allowance")

    async def get_combined_status(self, area_id: Optional[str] = None) -> EskomSePushStatus:
        """Get combined national status + area events.

        This is the main method used by the optimization endpoints.
        Makes 1-2 API calls (cached) and returns a unified status object.
        """
        status_data = await self.get_status()

        # Parse national status
        eskom_raw = status_data.get("status", {}).get("eskom", {})
        capetown_raw = status_data.get("status", {}).get("capetown")

        eskom = NationalStatus(
            stage=int(eskom_raw.get("stage", "0")),
            stage_updated=eskom_raw.get("stage_updated", ""),
            name=eskom_raw.get("name", "National"),
            next_stages=eskom_raw.get("next_stages", []),
        )

        capetown = None
        if capetown_raw:
            capetown = NationalStatus(
                stage=int(capetown_raw.get("stage", "0")),
                stage_updated=capetown_raw.get("stage_updated", ""),
                name=capetown_raw.get("name", "Cape Town"),
                next_stages=capetown_raw.get("next_stages", []),
            )

        # Parse area events
        area_events: List[AreaEvent] = []
        area_name = ""
        area_region = ""

        aid = area_id or self._area_id
        if aid:
            area_data = await self.get_area_information(aid)
            info = area_data.get("info", {})
            area_name = info.get("name", "")
            area_region = info.get("region", "")

            for event in area_data.get("events", []):
                note = event.get("note", "")
                # Extract stage number from note (e.g., "Stage 2" -> 2)
                stage_num = 0
                if "stage" in note.lower():
                    parts = note.lower().replace("stage", "").strip().split()
                    if parts:
                        try:
                            stage_num = int(parts[0])
                        except (ValueError, IndexError):
                            pass

                area_events.append(AreaEvent(
                    start=event.get("start", ""),
                    end=event.get("end", ""),
                    note=note,
                    stage=stage_num,
                ))

        return EskomSePushStatus(
            eskom=eskom,
            capetown=capetown,
            area_events=area_events,
            area_name=area_name,
            area_region=area_region,
            fetched_at=datetime.now().isoformat(),
        )

    def clear_cache(self) -> None:
        """Clear all cached responses."""
        self._cache.clear()


# Singleton instance
eskomsepush_service = EskomSePushService()
