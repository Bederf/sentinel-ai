"""Repository for municipal tariff schedules with JSON fallback."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class TariffScheduleRepository:
    """CRUD operations for municipal tariff schedules."""

    def __init__(self):
        self.client = None
        try:
            self.client = get_supabase_client()
        except Exception as exc:
            logger.warning("Supabase client not available for tariffs: %s", exc)

        self._json_path = Path("backend/app/data/municipal_tariff_schedules.json")
        self._json_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_json(self) -> dict[str, Any]:
        if not self._json_path.exists():
            return {"tariffs": []}
        with open(self._json_path) as f:
            return json.load(f)

    def _save_json(self, data: dict[str, Any]) -> None:
        with open(self._json_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def list_tariffs(
        self,
        municipality: str | None = None,
        utility_type: str | None = None,
        active_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if self.client:
            try:
                query = self.client.table("municipal_tariff_schedules").select("*")
                if municipality:
                    query = query.eq("municipality", municipality)
                if utility_type:
                    query = query.eq("utility_type", utility_type)
                if active_date:
                    query = query.lte("effective_date", active_date.isoformat())
                result = query.execute()
                return result.data or []
            except Exception as exc:
                logger.error("Error listing tariff schedules: %s", exc)
                return []

        data = self._load_json()
        tariffs = data.get("tariffs", [])
        filtered = []
        for tariff in tariffs:
            if municipality and tariff.get("municipality") != municipality:
                continue
            if utility_type and tariff.get("utility_type") != utility_type:
                continue
            if active_date:
                eff = tariff.get("effective_date")
                if eff and eff > active_date.isoformat():
                    continue
            filtered.append(tariff)
        return filtered

    def get_tariff(
        self,
        municipality: str,
        tariff_name: str,
        active_date: date | None = None,
    ) -> dict[str, Any] | None:
        if self.client:
            try:
                query = (
                    self.client.table("municipal_tariff_schedules")
                    .select("*")
                    .eq("municipality", municipality)
                    .eq("tariff_name", tariff_name)
                    .order("effective_date", desc=True)
                    .limit(1)
                )
                if active_date:
                    query = query.lte("effective_date", active_date.isoformat())
                result = query.execute()
                return result.data[0] if result.data else None
            except Exception as exc:
                logger.error("Error fetching tariff schedule: %s", exc)
                return None

        data = self._load_json()
        for tariff in data.get("tariffs", []):
            if tariff.get("municipality") == municipality and tariff.get("tariff_name") == tariff_name:
                return tariff
        return None

    def upsert_tariff(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.client:
            try:
                result = self.client.table("municipal_tariff_schedules").upsert(payload).execute()
                return result.data[0] if result.data else None
            except Exception as exc:
                logger.error("Error upserting tariff schedule: %s", exc)
                return None

        data = self._load_json()
        tariffs = data.get("tariffs", [])
        updated = False
        for idx, tariff in enumerate(tariffs):
            if (
                tariff.get("municipality") == payload.get("municipality")
                and tariff.get("tariff_name") == payload.get("tariff_name")
                and tariff.get("effective_date") == payload.get("effective_date")
            ):
                tariffs[idx] = payload
                updated = True
                break
        if not updated:
            tariffs.append(payload)
        data["tariffs"] = tariffs
        self._save_json(data)
        return payload
