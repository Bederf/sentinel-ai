"""Site 002 IPMVP data fetcher — reads from the Site 002 bridge API.

The bridge runs at BRIDGE_BASE and exposes:
    GET /api/sites/site-002/ipmvp
    GET /api/sites/site-002/ipmvp/energy
    GET /api/sites/site-002/ipmvp/oat
    GET /api/sites/site-002/ipmvp/events
    GET /api/sites/site-002/ipmvp/load-shedding
    GET /api/sites/site-002/ipmvp/tariff
    GET /api/sites/site-002/ipmvp/occupancy

Authentication: Bearer token from BRIDGE_API_TOKEN_SITE_002 env var.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, date, timedelta
from typing import Any

from app.services.ipmvp.ipmvp_engine import (
    EnergyRecord,
    EquipmentEvent,
    IPMVPDataFetcher,
)

logger = logging.getLogger(__name__)

BRIDGE_BASE = os.getenv("BRIDGE_BASE_SITE002") or os.getenv("BRIDGE_BASE_URL", "http://localhost:8080")
TOKEN = os.getenv("BRIDGE_API_TOKEN_SITE_002") or os.getenv("BRIDGE_API_TOKEN_SITE002") or os.getenv("BRIDGE_API_TOKEN", "")


class Site002DataFetcher(IPMVPDataFetcher):
    """Concrete fetcher for Site 002 — calls bridge REST API."""

    def __init__(self, site_id: str = "site-002"):
        super().__init__(site_id)
        self._client: Any = None  # httpx.AsyncClient, lazy init

    # ── Lazy HTTP client ──────────────────────────────────────────────────────

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=BRIDGE_BASE,
                headers={"Authorization": f"Bearer {TOKEN}"},
                timeout=30.0,
            )
        return self._client

    # ── Energy + OAT ─────────────────────────────────────────────────────────

    async def fetch_energy_and_oat(
        self,
        start: datetime,
        end: datetime,
    ) -> list[EnergyRecord]:
        """Fetch 15-min energy + OAT from /ipmvp/energy and /ipmvp/oat."""
        client = await self._get_client()

        # Fetch energy
        energy_resp = await client.get(
            "/api/sites/site-002/ipmvp/energy",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 50000,
            },
        )
        energy_resp.raise_for_status()
        energy_data = energy_resp.json()

        # Fetch OAT (separate endpoint)
        try:
            oat_resp = await client.get(
                "/api/sites/site-002/ipmvp/oat",
                params={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": 50000,
                },
            )
            oat_resp.raise_for_status()
            oat_data = oat_resp.json()
        except Exception:
            oat_data = []

        # Fetch load shedding days for flagging
        ls_days = await self.fetch_load_shedding_days(start, end)

        # Fetch occupancy schedule
        occupancy = await self._fetch_occupancy()
        holiday_dates = set(occupancy.get("holidays", []))

        # Index OAT by timestamp for quick lookup
        # OAT records look like: {"timestamp": "2026-01-01T00:00:00", "oat_celsius": 22.4}
        oat_index: dict[str, float] = {}
        for rec in oat_data.get("records", []):
            ts = rec.get("timestamp")
            if ts:
                oat_index[ts] = rec.get("oat_celsius", rec.get("outdoor_air_temp"))

        records: list[EnergyRecord] = []
        for rec in energy_data.get("records", []):
            ts_str = rec.get("timestamp")
            if not ts_str:
                continue

            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            ts_date = ts.date()
            ls_day = ts_date in ls_days
            holiday = ts_date in holiday_dates
            occupied = self._is_occupied(ts, occupancy)

            records.append(EnergyRecord(
                timestamp=ts,
                kwh=float(rec.get("kwh", rec.get("active_energy_kwh", 0))),
                oat_celsius=oat_index.get(ts_str),
                occupied=occupied,
                load_shedding=ls_day,
                holiday=holiday,
            ))

        return records

    # ── Equipment events ─────────────────────────────────────────────────────

    async def fetch_equipment_events(
        self,
        start: datetime,
        end: datetime,
        system_types: list[str] | None = None,
    ) -> list[EquipmentEvent]:
        client = await self._get_client()
        params: dict[str, Any] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": 5000,
        }
        if system_types:
            params["system_types"] = ",".join(system_types)

        resp = await client.get("/api/sites/site-002/ipmvp/events", params=params)
        resp.raise_for_status()
        data = resp.json()

        events: list[EquipmentEvent] = []
        for rec in data.get("events", []):
            try:
                ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue

            events.append(EquipmentEvent(
                event_id=rec.get("event_id", rec.get("id", "")),
                timestamp=ts,
                system_type=rec.get("system_type", "unknown"),
                device_id=rec.get("device_id", ""),
                point_name=rec.get("point_name", ""),
                old_value=rec.get("old_value"),
                new_value=rec.get("new_value"),
                recommendation_id=rec.get("recommendation_id"),
            ))

        return events

    # ── Load shedding ─────────────────────────────────────────────────────────

    async def fetch_load_shedding_days(
        self,
        start: datetime,
        end: datetime,
    ) -> set[date]:
        client = await self._get_client()
        resp = await client.get(
            "/api/sites/site-002/ipmvp/load-shedding",
            params={"start": start.isoformat(), "end": end.isoformat(), "limit": 500},
        )
        resp.raise_for_status()
        data = resp.json()

        dates: set[date] = set()
        for rec in data.get("events", data.get("records", [])):
            ts = rec.get("timestamp", rec.get("event_timestamp"))
            if ts:
                try:
                    dates.add(datetime.fromisoformat(ts.replace("Z", "+00:00")).date())
                except (ValueError, KeyError):
                    pass
        return dates

    # ── Tariff ────────────────────────────────────────────────────────────────

    async def fetch_tariff(self) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.get("/api/sites/site-002/ipmvp/tariff")
        resp.raise_for_status()
        tariff = resp.json()

        # Normalise to common shape
        return {
            "peak_zar_per_kwh": tariff.get("peak_rate", tariff.get("peak_zar_per_kwh", 4.52)),
            "standard_zar_per_kwh": tariff.get("standard_rate", tariff.get("standard_zar_per_kwh", 1.87)),
            "offpeak_zar_per_kwh": tariff.get("offpeak_rate", tariff.get("offpeak_zar_per_kwh", 0.63)),
            "peak_hours": tariff.get("peak_hours", [6, 7, 8, 17, 18, 19, 20]),
            "weekday_only": True,
        }

    # ── Occupancy ─────────────────────────────────────────────────────────────

    async def _fetch_occupancy(self) -> dict[str, Any]:
        """Fetch and cache occupancy schedule."""
        if not hasattr(self, "_occupancy"):
            client = await self._get_client()
            resp = await client.get("/api/sites/site-002/ipmvp/occupancy")
            resp.raise_for_status()
            self._occupancy = resp.json()
        return self._occupancy

    # ── Persistence to Supabase ───────────────────────────────────────────

    def _supabase(self):
        from app.database.supabase_client import get_supabase_client
        return get_supabase_client()

    async def persist_energy(self, records: list[EnergyRecord]) -> int:
        """Upsert energy records into ipmvp_energy."""
        if not records:
            return 0
        rows = [
            {
                "site_id": self.site_id,
                "timestamp": r.timestamp.isoformat(),
                "import_kwh": r.kwh if r.kwh >= 0 else None,
                "export_kwh": abs(r.kwh) if r.kwh < 0 else None,
                "hvac_kwh": None,
                "lighting_kwh": None,
                "solar_generation_kwh": None,
                "source": "bridge_ipmvp",
            }
            for r in records
        ]
        sb = self._supabase()
        result = sb.table("ipmvp_energy").upsert(
            rows,
            on_conflict="site_id,timestamp",
            ignore_duplicates=False,
        ).execute()
        count = len(result.data) if result.data else 0
        logger.info("[IPMVP] Persisted %d energy records", count)
        return count

    async def persist_oat(self, oat_data: dict) -> int:
        """Upsert OAT records into ipmvp_oat."""
        records = oat_data.get("records", [])
        if not records:
            return 0
        rows = [
            {
                "site_id": self.site_id,
                "timestamp": r["timestamp"],
                "oat_celsius": r.get("oat_celsius", r.get("outdoor_air_temp")),
                "source": "bridge_ipmvp",
            }
            for r in records if r.get("timestamp")
        ]
        if not rows:
            return 0
        sb = self._supabase()
        result = sb.table("ipmvp_oat").upsert(
            rows,
            on_conflict="site_id,timestamp",
            ignore_duplicates=False,
        ).execute()
        count = len(result.data) if result.data else 0
        logger.info("[IPMVP] Persisted %d OAT records", count)
        return count

    async def persist_events(self, events_data: dict) -> int:
        """Insert events into ipmvp_events."""
        events = events_data.get("events", [])
        if not events:
            return 0
        rows = [
            {
                "site_id": self.site_id,
                "event_id": e.get("event_id", f"evt-{i}"),
                "timestamp": e.get("timestamp"),
                "event_type": e.get("event_type", "unknown"),
                "target_id": e.get("target_id"),
                "value": e.get("value"),
                "unit": e.get("unit"),
                "reason": e.get("reason"),
                "source": "bridge_ipmvp",
            }
            for i, e in enumerate(events) if e.get("timestamp")
        ]
        if not rows:
            return 0
        sb = self._supabase()
        result = sb.table("ipmvp_events").upsert(
            rows,
            on_conflict="site_id,event_id",
            ignore_duplicates=True,
        ).execute()
        count = len(result.data) if result.data else 0
        logger.info("[IPMVP] Persisted %d events", count)
        return count

    async def persist_occupancy(self, occupancy_data: dict) -> bool:
        """Upsert occupancy schedule into ipmvp_occupancy."""
        if not occupancy_data:
            return False
        sb = self._supabase()
        result = sb.table("ipmvp_occupancy").upsert(
            {
                "site_id": self.site_id,
                "schedule_data": occupancy_data,
                "source": "bridge_ipmvp",
                "updated_at": datetime.now(UTC).isoformat(),
            },
            on_conflict="site_id",
        ).execute()
        ok = bool(result.data)
        if ok:
            logger.info("[IPMVP] Occupancy schedule persisted")
        return ok

    async def persist_tariff(self, tariff_data: dict) -> bool:
        """Upsert tariff into ipmvp_tariff."""
        if not tariff_data:
            return False
        sb = self._supabase()
        result = sb.table("ipmvp_tariff").upsert(
            {
                "site_id": self.site_id,
                "tariff_data": tariff_data,
                "source": "bridge_ipmvp",
                "updated_at": datetime.now(UTC).isoformat(),
            },
            on_conflict="site_id",
        ).execute()
        ok = bool(result.data)
        if ok:
            logger.info("[IPMVP] Tariff data persisted")
        return ok

    async def _purge_older_than(self, days: int = 7) -> None:
        """Delete IPMVP rows older than `days` to enforce rolling window."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        sb = self._supabase()
        for table in ("ipmvp_energy", "ipmvp_oat", "ipmvp_events"):
            try:
                sb.table(table).delete().lt("timestamp", cutoff).eq("site_id", self.site_id).execute()
            except Exception:
                pass

    async def run_full_sync(self, days_back: int = 7) -> dict[str, Any]:
        """Fetch all IPMVP data and persist to Supabase."""
        now = datetime.now(UTC)
        start = now - timedelta(days=days_back)
        summary: dict[str, Any] = {"status": "ok", "counts": {}}

        try:
            energy = await self.fetch_energy_and_oat(start, now)
            summary["counts"]["energy"] = await self.persist_energy(energy)
        except Exception as e:
            logger.warning("[IPMVP] Energy sync failed: %s", e)
            summary.setdefault("errors", []).append(f"energy:{e}")

        try:
            client = await self._get_client()
            resp = await client.get(
                "/api/sites/site-002/ipmvp/oat",
                params={"start": start.isoformat(), "end": now.isoformat(), "limit": 50000},
            )
            oat_data = resp.json()
            summary["counts"]["oat"] = await self.persist_oat(oat_data)
        except Exception as e:
            logger.warning("[IPMVP] OAT sync failed: %s", e)
            summary.setdefault("errors", []).append(f"oat:{e}")

        try:
            resp = await client.get(
                "/api/sites/site-002/ipmvp/events",
                params={"start": start.isoformat(), "end": now.isoformat(), "limit": 5000},
            )
            events_data = resp.json()
            summary["counts"]["events"] = await self.persist_events(events_data)
        except Exception as e:
            logger.warning("[IPMVP] Events sync failed: %s", e)
            summary.setdefault("errors", []).append(f"events:{e}")

        try:
            occupancy = await self._fetch_occupancy()
            summary["counts"]["occupancy"] = await self.persist_occupancy(occupancy)
        except Exception as e:
            logger.warning("[IPMVP] Occupancy sync failed: %s", e)
            summary.setdefault("errors", []).append(f"occupancy:{e}")

        try:
            tariff = await self.fetch_tariff()
            summary["counts"]["tariff"] = await self.persist_tariff(tariff)
        except Exception as e:
            logger.warning("[IPMVP] Tariff sync failed: %s", e)
            summary.setdefault("errors", []).append(f"tariff:{e}")

        # Rolling 7-day window
        self._purge_older_than(days_back)

        if summary.get("errors"):
            summary["status"] = "partial"
        logger.info("[IPMVP] Full sync complete: %s", summary)
        return summary

    def _is_occupied(self, dt: datetime, occupancy: dict[str, Any]) -> bool:
        """Check if dt falls within occupied hours per schedule."""
        if dt.weekday() >= 5:  # Saturday/Sunday
            return False

        schedule = occupancy.get("schedule", {})
        weekday = ["monday", "tuesday", "wednesday", "thursday", "friday"][dt.weekday()]
        entry = schedule.get(weekday, {})
        start = entry.get("start", "08:00")
        end = entry.get("end", "18:00")

        try:
            hour_start = int(start.split(":")[0])
            hour_end = int(end.split(":")[0])
            return hour_start <= dt.hour < hour_end
        except (ValueError, IndexError):
            return 8 <= dt.hour < 18
