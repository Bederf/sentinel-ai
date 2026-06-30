"""Zone-level occupancy transition trigger.

Records zone occupancy changes as inert events. This deliberately does not call
AI optimization or control paths; the future ReflexReconciliationService should
consume these events and decide what, if anything, to reconcile.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger("sentinel.zone_occupancy_trigger")

DEFAULT_COOLDOWN_MINUTES = 10


@dataclass
class ZoneOccupancyState:
    zone_id: str
    occupied: bool
    occupancy_value: float | None = None
    zone_group: str | None = None
    source_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ZoneOccupancyTriggerEvent:
    id: str
    site_id: str
    zone_id: str
    previous_occupied: bool
    current_occupied: bool
    observed_at: datetime
    zone_group: str | None = None
    previous_occupancy: float | None = None
    current_occupancy: float | None = None
    source: str | None = None
    event_type: str = "zone_occupancy_change"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["observed_at"] = self.observed_at.isoformat()
        return record


class ZoneOccupancyTriggerRepository:
    """Persistence for zone occupancy trigger events."""

    async def create_event(self, event: ZoneOccupancyTriggerEvent) -> None:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        await client.table("zone_occupancy_trigger_events").insert(event.to_record()).execute()

    async def list_recent_events(
        self,
        site_id: str,
        *,
        zone_id: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Query pattern required by the future reconciliation service."""
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        query = (
            client.table("zone_occupancy_trigger_events")
            .select("*")
            .eq("site_id", site_id)
            .order("observed_at", desc=True)
            .limit(limit)
        )
        if zone_id:
            query = query.eq("zone_id", zone_id)
        if since:
            query = query.gte("observed_at", since.isoformat())
        result = await query.execute()
        return result.data or []


class ZoneOccupancyTriggerService:
    """Detects zone occupancy transitions and records inert trigger events."""

    def __init__(
        self,
        *,
        repository: ZoneOccupancyTriggerRepository | None = None,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    ):
        self.repository = repository or ZoneOccupancyTriggerRepository()
        self.cooldown = timedelta(minutes=max(1, int(cooldown_minutes)))
        self._last_states: dict[tuple[str, str], ZoneOccupancyState] = {}
        self._last_event_at: dict[tuple[str, str], datetime] = {}

    async def evaluate_snapshot(
        self,
        site_id: str,
        zone_states: dict[str, ZoneOccupancyState],
        *,
        observed_at: datetime | None = None,
        source: str = "unknown",
    ) -> list[ZoneOccupancyTriggerEvent]:
        observed_at = observed_at or datetime.now(tz=UTC)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)

        events: list[ZoneOccupancyTriggerEvent] = []
        for zone_id, state in sorted(zone_states.items()):
            key = (site_id, zone_id)
            previous = self._last_states.get(key)
            self._last_states[key] = state

            if previous is None or previous.occupied == state.occupied:
                continue

            last_event_at = self._last_event_at.get(key)
            if last_event_at and observed_at - last_event_at < self.cooldown:
                logger.info(
                    "Zone occupancy trigger suppressed by cooldown: site=%s zone=%s previous=%s current=%s",
                    site_id,
                    zone_id,
                    previous.occupied,
                    state.occupied,
                )
                continue

            event = ZoneOccupancyTriggerEvent(
                id=str(uuid4()),
                site_id=site_id,
                zone_id=zone_id,
                zone_group=state.zone_group,
                previous_occupied=previous.occupied,
                current_occupied=state.occupied,
                previous_occupancy=previous.occupancy_value,
                current_occupancy=state.occupancy_value,
                observed_at=observed_at,
                source=source,
                metadata={
                    "future_consumer": "ReflexReconciliationService",
                    "execution_status": "event_only",
                    "previous_payload": previous.source_payload,
                    "current_payload": state.source_payload,
                },
            )
            await self.repository.create_event(event)
            self._last_event_at[key] = observed_at
            events.append(event)

        return events

    async def process_payload(
        self,
        site_id: str,
        payload: dict[str, Any],
        *,
        observed_at: datetime | None = None,
        source: str = "bridge",
    ) -> list[ZoneOccupancyTriggerEvent]:
        states = self.extract_zone_states(payload)
        if not states:
            return []
        return await self.evaluate_snapshot(site_id, states, observed_at=observed_at, source=source)

    async def process_site(self, site_id: str) -> list[ZoneOccupancyTriggerEvent]:
        payload = await self._fetch_site_zone_payload(site_id)
        if not payload:
            return []
        return await self.process_payload(site_id, payload, source=payload.get("_source", "bridge"))

    async def _fetch_site_zone_payload(self, site_id: str) -> dict[str, Any]:
        from app.services.shadow_mode_polling import resolve_site_bridge_token

        token = resolve_site_bridge_token(site_id)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        base_url = os.getenv("BRIDGE_BASE_URL", "http://10.99.0.1:8080").rstrip("/")

        async with httpx.AsyncClient(timeout=10) as client:
            merged: dict[str, Any] = {"_source": "bridge"}
            for path in (f"/api/sites/{site_id}/zones", f"/api/sites/{site_id}/telemetry"):
                try:
                    resp = await client.get(f"{base_url}{path}", headers=headers)
                    if resp.is_success:
                        data = resp.json()
                        if isinstance(data, dict):
                            merged.update(data)
                except Exception as exc:
                    logger.debug("Zone occupancy trigger fetch failed for %s %s: %s", site_id, path, exc)
            return merged

    @staticmethod
    def extract_zone_states(payload: dict[str, Any]) -> dict[str, ZoneOccupancyState]:
        states: dict[str, ZoneOccupancyState] = {}

        def add_zone(zone_id: Any, raw: Any, *, source_key: str, zone_group: Any = None) -> None:
            zone = str(zone_id or "").strip()
            if not zone:
                return
            occupied, value = ZoneOccupancyTriggerService._normalise_occupancy(raw)
            if occupied is None:
                return
            source_payload = raw if isinstance(raw, dict) else {"value": raw}
            states[zone] = ZoneOccupancyState(
                zone_id=zone,
                occupied=occupied,
                occupancy_value=value,
                zone_group=str(zone_group) if zone_group else None,
                source_payload={"source_key": source_key, **source_payload},
            )

        zone_occupancy = payload.get("zone_occupancy")
        if isinstance(zone_occupancy, dict):
            for zone_id, raw in zone_occupancy.items():
                add_zone(zone_id, raw, source_key="zone_occupancy")

        occupancy = payload.get("occupancy")
        if isinstance(occupancy, dict):
            nested = occupancy.get("zone_occupancy") or occupancy.get("zones")
            if isinstance(nested, dict):
                for zone_id, raw in nested.items():
                    add_zone(zone_id, raw, source_key="occupancy")
            elif isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict):
                        add_zone(
                            item.get("zone_id") or item.get("id") or item.get("zone"),
                            item,
                            source_key="occupancy.zones",
                            zone_group=item.get("floor") or item.get("zone_group"),
                        )

        zones = payload.get("zones")
        if isinstance(zones, list):
            for item in zones:
                if isinstance(item, dict):
                    add_zone(
                        item.get("zone_id") or item.get("id") or item.get("zone"),
                        item,
                        source_key="zones",
                        zone_group=item.get("floor") or item.get("zone_group"),
                    )

        return states

    @staticmethod
    def _normalise_occupancy(raw: Any) -> tuple[bool | None, float | None]:
        if isinstance(raw, bool):
            return raw, 1.0 if raw else 0.0
        if isinstance(raw, (int, float)):
            value = float(raw)
            return value > 0, value
        if not isinstance(raw, dict):
            return None, None

        for key in ("is_occupied", "occupied"):
            if isinstance(raw.get(key), bool):
                value = raw.get("occupancy_percent") or raw.get("occupancy_pct") or raw.get("occupancy_count")
                return bool(raw[key]), float(value) if isinstance(value, (int, float)) else None

        for key in ("occupancy_count", "people_count", "occupants", "count"):
            value = raw.get(key)
            if isinstance(value, (int, float)):
                return float(value) > 0, float(value)

        for key in ("occupancy_percent", "occupancy_pct", "occupancy"):
            value = raw.get(key)
            if isinstance(value, (int, float)):
                return float(value) > 10.0, float(value)

        return None, None


_zone_occupancy_trigger_service: ZoneOccupancyTriggerService | None = None


def get_zone_occupancy_trigger_service() -> ZoneOccupancyTriggerService:
    global _zone_occupancy_trigger_service
    if _zone_occupancy_trigger_service is None:
        _zone_occupancy_trigger_service = ZoneOccupancyTriggerService()
    return _zone_occupancy_trigger_service


def reset_zone_occupancy_trigger_service() -> None:
    global _zone_occupancy_trigger_service
    _zone_occupancy_trigger_service = None
