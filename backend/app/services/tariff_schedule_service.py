"""Tariff schedule service for municipal billing."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.database.repositories.tariff_schedule_repository import TariffScheduleRepository

logger = logging.getLogger(__name__)


@dataclass
class TariffSchedule:
    municipality: str
    tariff_name: str
    effective_date: date
    tariff_data: dict[str, Any]

    def calculate_total_charge(
        self,
        consumption_kwh: dict[str, float],
        demand_kva: float,
        month: int,
    ) -> dict[str, float]:
        """Calculate total bill from TOU consumption and demand.

        Expects tariff_data with keys:
          - energy_charge_c_kwh
          - network_charge_c_kwh
          - demand_charge_r_kva
          - service_charge_r_month
          - time_bands
        """
        season = "winter" if month in [6, 7, 8] else "summer"

        energy_charges = self.tariff_data.get("energy_charge_c_kwh", {}).get(season, {})
        network_charges = self.tariff_data.get("network_charge_c_kwh", {}).get(season, {})
        demand_rates = self.tariff_data.get("demand_charge_r_kva", {})
        service_charge = self.tariff_data.get("service_charge_r_month") or 0.0

        energy_total = 0.0
        for band, kwh in consumption_kwh.items():
            rate_c = energy_charges.get(band, 0)
            energy_total += (kwh * rate_c) / 100.0

        network_total = 0.0
        for band, kwh in consumption_kwh.items():
            rate_c = network_charges.get(band, 0)
            network_total += (kwh * rate_c) / 100.0

        demand_total = 0.0
        if demand_rates and demand_kva:
            rate_r = demand_rates.get(season, 0)
            demand_total = demand_kva * rate_r

        subtotal = energy_total + network_total + demand_total + service_charge
        vat = subtotal * 0.15
        total = subtotal + vat

        return {
            "energy_charge_zar": round(energy_total, 2),
            "network_charge_zar": round(network_total, 2),
            "demand_charge_zar": round(demand_total, 2),
            "service_charge_zar": round(service_charge, 2),
            "subtotal_zar": round(subtotal, 2),
            "vat_zar": round(vat, 2),
            "total_zar": round(total, 2),
        }


class TariffScheduleService:
    """Service wrapper for tariff schedules."""

    def __init__(self):
        self.repo = TariffScheduleRepository()

    def list_tariffs(
        self,
        municipality: str | None = None,
        utility_type: str | None = None,
        active_date: date | None = None,
    ) -> list[dict[str, Any]]:
        return self.repo.list_tariffs(municipality, utility_type, active_date)

    def get_tariff(
        self,
        municipality: str,
        tariff_name: str,
        effective_date: date,
    ) -> TariffSchedule | None:
        record = self.repo.get_tariff(municipality, tariff_name, effective_date)
        if record:
            eff_date = record.get("effective_date")
            if isinstance(eff_date, str):
                try:
                    eff_date = date.fromisoformat(eff_date)
                except Exception:
                    eff_date = effective_date
            return TariffSchedule(
                municipality=record["municipality"],
                tariff_name=record["tariff_name"],
                effective_date=eff_date or effective_date,
                tariff_data=record["tariff_data"],
            )

        fallback = self._load_default_tariff(municipality, tariff_name)
        if fallback:
            return TariffSchedule(
                municipality=municipality,
                tariff_name=tariff_name,
                effective_date=effective_date,
                tariff_data=fallback,
            )
        return None

    def upsert_tariff(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self.repo.upsert_tariff(payload)

    def _load_default_tariff(self, municipality: str, tariff_name: str) -> dict[str, Any] | None:
        """Load a default tariff from bundled JSON files."""
        tariff_path = Path("backend/app/data/solar/tariffs/city_power_2026.json")
        if not tariff_path.exists():
            return None

        if "city power" in municipality.lower() or "city power" in tariff_name.lower():
            try:
                with open(tariff_path) as f:
                    return json.load(f)
            except Exception as exc:
                logger.error("Failed to load default tariff: %s", exc)
                return None

        return None
