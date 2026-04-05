"""
Core ingestion logic for MRI Evolution job cards.
Upserts MaintenanceEvents into Supabase.
Detects SLA breaches and writes to sla_breach_events.
Publishes WorkOrderCreated / WorkOrderUpdated to Event Bus (stub).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from app.models.maintenance_event import MaintenanceEvent
from app.services.event_bus import SentinelEvent, get_event_bus
from app.services.mri_evolution_client import MRIEvolutionClient

logger = logging.getLogger(__name__)


def _get_supabase():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


class MRIConnectorService:
    """Orchestrates sync between MRI Evolution and SENTINEL."""

    def __init__(self) -> None:
        self.client = MRIEvolutionClient()
        self.db = _get_supabase()

    async def run_sync(self, site_id: str | None = None) -> dict:
        """Run a full sync cycle: fetch -> normalise -> upsert -> check SLA -> update state."""
        last_sync = self._get_last_sync(site_id)
        raw_records = await self.client.fetch_delta(since=last_sync, site_filter=site_id)

        ingested = updated = errors = 0
        for raw in raw_records:
            try:
                event = self.client.normalise(raw, site_id=site_id)
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
                logger.error("Failed to ingest record %s: %s", raw.get("TaskId", "?"), exc)

        await self.client.close()
        self._update_sync_state(site_id, ingested, updated, errors)
        return {"ingested": ingested, "updated": updated, "errors": errors}

    def _upsert(self, event: MaintenanceEvent) -> str:
        """Upsert MaintenanceEvent. Returns 'inserted' or 'updated'."""
        existing = self.db.table("maintenance_events").select("id").eq("external_ref", event.external_ref).execute()

        data = event.model_dump(exclude={"metadata"})
        data["metadata"] = event.metadata
        data["last_synced_at"] = datetime.now(timezone.utc).isoformat()
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
        now = datetime.now(timezone.utc)
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
                # Look up maintenance_event_id
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
                source="mri_connector",
                payload=event.model_dump(),
                site_id=str(event.site_id) if event.site_id else None,
                equipment_id=event.metadata.get("equipment_id"),
            )
        )

    def _get_last_sync(self, site_id: str | None) -> datetime | None:
        query = self.db.table("mri_connector_sync").select("last_successful_sync")
        if site_id:
            query = query.eq("site_id", site_id)
        result = query.execute()
        if result.data and result.data[0]["last_successful_sync"]:
            return datetime.fromisoformat(result.data[0]["last_successful_sync"])
        return None

    def _update_sync_state(self, site_id: str | None, ingested: int, updated: int, errors: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.table("mri_connector_sync").upsert(
            {
                "site_id": site_id,
                "last_successful_sync": now,
                "last_sync_attempted": now,
                "records_ingested": ingested,
                "records_updated": updated,
                "errors": errors,
            },
            on_conflict="site_id",
        ).execute()
