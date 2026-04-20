"""
Base class for all maintenance intake adapters.
Provides common upsert, SLA breach detection, event publishing, and sync state management.
Each adapter (MRI, ServiceNow, CSV, etc.) implements fetch_records() and normalise().
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.maintenance_event import MaintenanceEvent
from app.services.event_bus import SentinelEvent, get_event_bus

logger = logging.getLogger(__name__)


def _get_supabase():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


class MaintenanceAdapter(ABC):
    """
    Abstract base for maintenance intake adapters.

    Subclass implements:
      - source_system: str  — identifies the origin system
      - fetch_records(since) — pull raw records from the source
      - normalise(raw, site_id) — translate to MaintenanceEvent

    Base class provides:
      - _upsert(event) — deduplicated insert/update
      - _check_sla_breach(event) — milestone breach detection
      - _publish_event(event_type, event) — Event Bus publish
      - _get_last_sync(site_id) / _update_sync_state — per-adapter sync tracking
    """

    source_system: str = "maintenance"
    adapter_table: str = "maintenance_connector_sync"

    def __init__(self) -> None:
        self.db = _get_supabase()

    @abstractmethod
    async def fetch_records(self, since: datetime | None = None, site_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch raw records from the source system since last sync."""

    @abstractmethod
    def normalise(self, raw: dict[str, Any], site_id: str | None = None) -> MaintenanceEvent:
        """Translate source-specific record format to canonical MaintenanceEvent."""

    async def run_sync(self, site_id: str | None = None) -> dict:
        """Run a full sync cycle: fetch → normalise → upsert → check SLA → publish → update state."""
        last_sync = self._get_last_sync(site_id)
        raw_records = await self.fetch_records(since=last_sync, site_id=site_id)

        ingested = updated = errors = 0
        for raw in raw_records:
            try:
                event = self.normalise(raw, site_id=site_id)
                result = self._upsert(event)
                if result == "inserted":
                    ingested += 1
                    await self._publish_event("work_order.created", event)
                else:
                    updated += 1
                    await self._publish_event("work_order.updated", event)
                self._check_sla_breach(event)
            except Exception as exc:
                errors += 1
                logger.error("[%s] Failed to ingest record: %s", self.source_system, exc)

        self._update_sync_state(site_id, ingested, updated, errors)
        return {"ingested": ingested, "updated": updated, "errors": errors}

    def _upsert(self, event: MaintenanceEvent) -> str:
        """Upsert MaintenanceEvent. Returns 'inserted' or 'updated'."""
        existing = self.db.table("maintenance_events").select("id").eq("external_ref", event.external_ref).execute()

        data = event.model_dump(exclude={"metadata"})
        data["source_system"] = self.source_system
        data["metadata"] = event.metadata
        data["last_synced_at"] = datetime.now(UTC).isoformat()
        if data.get("site_id"):
            data["site_id"] = str(data["site_id"])

        if existing.data:
            self.db.table("maintenance_events").update(data).eq("external_ref", event.external_ref).execute()
            return "updated"
        else:
            self.db.table("maintenance_events").insert(data).execute()
            return "inserted"

    def _check_sla_breach(self, event: MaintenanceEvent) -> None:
        """Detect SLA breaches and write breach events to sla_breach_events."""
        now = datetime.now(UTC)
        if not event.created_at_source:
            return

        checks = [
            ("respond", event.assigned_at, event.sla_respond_hours),
            ("attend", event.attended_at, event.sla_attend_hours),
            ("temp_fix", event.temp_fixed_at, event.sla_temp_fix_hours),
        ]

        for breach_type, milestone_dt, threshold_hours in checks:
            if threshold_hours is None:
                continue
            deadline = event.created_at_source + timedelta(hours=threshold_hours)
            compare_dt = milestone_dt or now
            if compare_dt > deadline:
                actual_hours = (compare_dt - event.created_at_source).total_seconds() / 3600
                result = (
                    self.db.table("maintenance_events")
                    .select("id")
                    .eq("external_ref", event.external_ref)
                    .maybe_single()
                    .execute()
                )
                if result and result.data:
                    self.db.table("sla_breach_events").insert(
                        {
                            "maintenance_event_id": result.data["id"],
                            "breach_type": breach_type,
                            "breached_at": now.isoformat(),
                            "sla_threshold_hours": threshold_hours,
                            "actual_hours": round(actual_hours, 2),
                        }
                    ).execute()

    async def _publish_event(self, event_type: str, event: MaintenanceEvent) -> None:
        """Publish work order lifecycle events to the SENTINEL Event Bus."""
        bus = get_event_bus()
        await bus.emit(
            SentinelEvent(
                event_type=event_type,
                source=self.source_system,
                payload=event.model_dump(),
                site_id=str(event.site_id) if event.site_id else None,
                equipment_id=event.metadata.get("equipment_id"),
            )
        )

    def _get_last_sync(self, site_id: str | None) -> datetime | None:
        query = (
            self.db.table(self.adapter_table).select("last_successful_sync").eq("adapter_source", self.source_system)
        )
        if site_id:
            query = query.eq("site_id", site_id)
        result = query.execute()
        if result.data and result.data[0]["last_successful_sync"]:
            return datetime.fromisoformat(result.data[0]["last_successful_sync"])
        return None

    def _update_sync_state(self, site_id: str | None, ingested: int, updated: int, errors: int) -> None:
        now = datetime.now(UTC).isoformat()
        self.db.table(self.adapter_table).upsert(
            {
                "adapter_source": self.source_system,
                "site_id": site_id,
                "last_successful_sync": now,
                "last_sync_attempted": now,
                "records_ingested": ingested,
                "records_updated": updated,
                "errors": errors,
            },
            on_conflict="adapter_source,site_id",
        ).execute()
