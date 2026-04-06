"""Fuel tank 3-tier persistence store (Phase 148).

Follows the standard SENTINEL pattern: Supabase -> Redis -> JSON fallback.
Uses CacheService for Redis and graceful degradation on all tiers.

Usage:
    from app.services.fuel_store import get_fuel_store

    store = get_fuel_store()
    config = store.get_tank_config("S002-TANK-EXT-001")
    await store.store_telemetry(telemetry)
    latest = await store.get_latest_telemetry("S002-TANK-EXT-001")
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.models.fuel import FuelTankConfig, FuelTelemetry

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data" / "fuel"
_TANKS_FILE = _DATA_DIR / "tanks.json"
_TELEMETRY_FILE = _DATA_DIR / "telemetry.json"

_REDIS_TTL = 120  # seconds


class FuelStore:
    """3-tier persistence for fuel tank telemetry and configuration."""

    def __init__(self) -> None:
        self._tanks: dict[str, FuelTankConfig] = {}
        self._load_tank_configs()

    # ------------------------------------------------------------------
    # Tank configuration (loaded from JSON seed)
    # ------------------------------------------------------------------

    def _load_tank_configs(self) -> None:
        """Load tank configurations from seed JSON."""
        if not _TANKS_FILE.exists():
            logger.warning("Fuel tanks config not found at %s", _TANKS_FILE)
            return
        try:
            with open(_TANKS_FILE) as fh:
                raw_list = json.load(fh)
            for item in raw_list:
                cfg = FuelTankConfig(**item)
                self._tanks[cfg.tank_id] = cfg
            logger.info("Loaded %d fuel tank config(s)", len(self._tanks))
        except Exception as exc:
            logger.error("Failed to load fuel tank configs: %s", exc)

    def get_tank_config(self, tank_id: str) -> FuelTankConfig | None:
        """Return config for a single tank, or None if unknown."""
        return self._tanks.get(tank_id)

    def get_all_tanks(self, site_id: str | None = None) -> list[FuelTankConfig]:
        """Return all tank configs, optionally filtered by site_id."""
        tanks = list(self._tanks.values())
        if site_id:
            tanks = [t for t in tanks if t.site_id == site_id]
        return tanks

    # ------------------------------------------------------------------
    # Telemetry write (3-tier)
    # ------------------------------------------------------------------

    async def store_telemetry(self, telemetry: FuelTelemetry) -> None:
        """Persist a telemetry reading across all available tiers."""
        record = asdict(telemetry)
        # Ensure received_at is ISO string for JSON serialisation
        if isinstance(record.get("received_at"), datetime):
            record["received_at"] = record["received_at"].isoformat()

        # Tier 1: Supabase (best-effort)
        self._write_supabase(telemetry.tank_id, record)

        # Tier 2: Redis cache
        self._write_redis(telemetry.tank_id, record)

        # Tier 3: JSON fallback / audit
        self._write_json(record)

    def _write_supabase(self, tank_id: str, record: dict) -> None:
        try:
            from app.database.supabase_client import get_client

            client = get_client()
            if client:
                client.table("fuel_telemetry").insert(record).execute()
                logger.debug("Fuel telemetry written to Supabase for %s", tank_id)
        except Exception as exc:
            logger.warning("Supabase fuel write failed (non-fatal): %s", exc)

    def _write_redis(self, tank_id: str, record: dict) -> None:
        try:
            from app.services.cache_service import cache

            cache.set(f"fuel:{tank_id}:latest", record, ttl=_REDIS_TTL)
        except Exception as exc:
            logger.debug("Redis fuel write failed (non-fatal): %s", exc)

    def _write_json(self, record: dict) -> None:
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_TELEMETRY_FILE, "a") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except Exception as exc:
            logger.warning("JSON fuel write failed: %s", exc)

    # ------------------------------------------------------------------
    # Telemetry read (3-tier fallback)
    # ------------------------------------------------------------------

    async def get_latest_telemetry(self, tank_id: str) -> FuelTelemetry | None:
        """Read latest telemetry for a tank using the 3-tier fallback chain."""
        # Tier 1: Redis cache
        record = self._read_redis(tank_id)
        if record:
            return self._record_to_telemetry(record)

        # Tier 2: Supabase
        record = self._read_supabase(tank_id)
        if record:
            return self._record_to_telemetry(record)

        # Tier 3: JSON file (last matching line)
        record = self._read_json(tank_id)
        if record:
            return self._record_to_telemetry(record)

        return None

    def _read_redis(self, tank_id: str) -> dict | None:
        try:
            from app.services.cache_service import cache

            return cache.get(f"fuel:{tank_id}:latest")
        except Exception:
            return None

    def _read_supabase(self, tank_id: str) -> dict | None:
        try:
            from app.database.supabase_client import get_client

            client = get_client()
            if not client:
                return None
            resp = (
                client.table("fuel_telemetry")
                .select("*")
                .eq("tank_id", tank_id)
                .order("ts", desc=True)
                .limit(1)
                .execute()
            )
            if resp.data:
                return resp.data[0]
        except Exception as exc:
            logger.debug("Supabase fuel read failed: %s", exc)
        return None

    def _read_json(self, tank_id: str) -> dict | None:
        if not _TELEMETRY_FILE.exists():
            return None
        try:
            last_match: dict | None = None
            with open(_TELEMETRY_FILE) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line == "[]":
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("tank_id") == tank_id:
                            last_match = rec
                    except json.JSONDecodeError:
                        continue
            return last_match
        except Exception as exc:
            logger.debug("JSON fuel read failed: %s", exc)
            return None

    @staticmethod
    def _record_to_telemetry(record: dict) -> FuelTelemetry:
        """Convert a dict back into a FuelTelemetry dataclass."""
        received = record.get("received_at")
        if isinstance(received, str):
            try:
                received = datetime.fromisoformat(received)
            except ValueError:
                received = datetime.now(tz=UTC)
        elif not isinstance(received, datetime):
            received = datetime.now(tz=UTC)

        return FuelTelemetry(
            node_id=record.get("node_id", ""),
            site_id=record.get("site_id", ""),
            tank_id=record.get("tank_id", ""),
            generator_id=record.get("generator_id", ""),
            fuel_level_pct=float(record.get("fuel_level_pct", 0)),
            fuel_level_litres=float(record.get("fuel_level_litres", 0)),
            fuel_level_mm=float(record.get("fuel_level_mm", 0)),
            fuel_temp_c=float(record.get("fuel_temp_c", 0)),
            consumption_rate_lph=record.get("consumption_rate_lph"),
            consumption_anomaly=bool(record.get("consumption_anomaly", False)),
            runtime_remaining_hrs=record.get("runtime_remaining_hrs"),
            days_to_empty=record.get("days_to_empty"),
            generator_running=bool(record.get("generator_running", False)),
            leak_detected=bool(record.get("leak_detected", False)),
            overfill_alert=bool(record.get("overfill_alert", False)),
            theft_suspected=bool(record.get("theft_suspected", False)),
            sensor_fault=bool(record.get("sensor_fault", False)),
            sensor_ma=float(record.get("sensor_ma", 0)),
            rssi=int(record.get("rssi", 0)),
            uptime_s=int(record.get("uptime_s", 0)),
            ts=int(record.get("ts", 0)),
            received_at=received,
        )


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: FuelStore | None = None


def get_fuel_store() -> FuelStore:
    """Return the singleton FuelStore instance."""
    global _instance
    if _instance is None:
        _instance = FuelStore()
    return _instance
