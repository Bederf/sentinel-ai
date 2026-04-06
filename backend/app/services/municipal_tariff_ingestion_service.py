"""Municipal tariff ingestion service.

Downloads official tariff PDFs and registers them in municipal_tariff_schedules.
Parsing into structured tariff_data can be added iteratively.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import requests

from app.database.repositories.tariff_schedule_repository import TariffScheduleRepository

logger = logging.getLogger(__name__)


class MunicipalTariffIngestionService:
    """Fetch and register tariff schedules from official sources."""

    def __init__(self):
        self.repo = TariffScheduleRepository()
        self.sources_path = Path("backend/app/data/municipal_tariff_sources.json")
        self.storage_dir = Path("backend/app/data/municipal_tariffs_raw")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._structured_tariff_map: dict[str, Path] = {
            "city_power_johannesburg_2025_26": Path("backend/app/data/solar/tariffs/city_power_2025_26.json"),
            "coj_consolidated_tariffs_2025_26": Path("backend/app/data/solar/tariffs/city_power_2025_26.json"),
        }

    def ingest_all(self) -> list[dict[str, Any]]:
        sources = self._load_sources()
        results = []
        for source in sources:
            results.append(self.ingest_source(source))
        return results

    def ingest_source(self, source: dict[str, Any]) -> dict[str, Any]:
        key = source.get("key", "unknown")
        url = source.get("source_url")
        if not url:
            return {"key": key, "status": "error", "message": "Missing source_url"}

        filename = f"{key}.pdf"
        pdf_path = self.storage_dir / filename

        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                return {"key": key, "status": "error", "message": f"HTTP {resp.status_code}"}
            with open(pdf_path, "wb") as f:
                f.write(resp.content)
        except Exception as exc:
            logger.info("Tariff download failed for %s: %s", key, exc)
            return {"key": key, "status": "error", "message": str(exc)}

        structured_tariff_data = self._load_structured_tariff_data(key)
        payload = {
            "municipality": source.get("municipality"),
            "tariff_name": source.get("tariff_name"),
            "utility_type": source.get("utility_type", "electricity"),
            "effective_date": source.get("effective_date") or date.today().isoformat(),
            "tariff_data": structured_tariff_data or {},
            "energy_charge_c_kwh": (structured_tariff_data or {}).get("energy_charge_c_kwh"),
            "demand_charge_r_kva": (structured_tariff_data or {}).get("demand_charge_r_kva"),
            "service_charge_r_month": (structured_tariff_data or {}).get("service_charge_r_month"),
            "network_charge_c_kwh": (structured_tariff_data or {}).get("network_charge_c_kwh"),
            "time_bands": (structured_tariff_data or {}).get("time_bands"),
            "nersa_approved": False,
            "source_url": url,
            "notes": source.get("notes"),
            "source_file_path": str(pdf_path),
        }

        record = self.repo.upsert_tariff(payload)
        return {"key": key, "status": "ok", "record": record}

    def _load_structured_tariff_data(self, key: str) -> dict[str, Any]:
        structured_path = self._structured_tariff_map.get(key)
        if not structured_path or not structured_path.exists():
            return {}
        try:
            with open(structured_path) as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed loading structured tariff for %s: %s", key, exc)
            return {}

    def _load_sources(self) -> list[dict[str, Any]]:
        if not self.sources_path.exists():
            return []
        with open(self.sources_path) as f:
            data = json.load(f)
        return data.get("sources", [])
