"""Shared site holiday calendar service for lifecycle and API consumers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"

# South African public holidays (recurring annually)
SA_PUBLIC_HOLIDAYS = [
    {"date": "01-01", "name": "New Year's Day", "type": "public", "recurring": True},
    {"date": "03-21", "name": "Human Rights Day", "type": "public", "recurring": True},
    {"date": "04-18", "name": "Good Friday", "type": "public", "recurring": True},
    {"date": "04-21", "name": "Family Day", "type": "public", "recurring": True},
    {"date": "04-27", "name": "Freedom Day", "type": "public", "recurring": True},
    {"date": "05-01", "name": "Workers' Day", "type": "public", "recurring": True},
    {"date": "06-16", "name": "Youth Day", "type": "public", "recurring": True},
    {"date": "08-09", "name": "National Women's Day", "type": "public", "recurring": True},
    {"date": "09-24", "name": "Heritage Day", "type": "public", "recurring": True},
    {"date": "12-16", "name": "Day of Reconciliation", "type": "public", "recurring": True},
    {"date": "12-25", "name": "Christmas Day", "type": "public", "recurring": True},
    {"date": "12-26", "name": "Day of Goodwill", "type": "public", "recurring": True},
]


class SiteHolidayService:
    """Reads the effective holiday calendar for a site."""

    def __init__(self, data_path: Path | None = None):
        self._data_path = data_path or DATA_PATH

    def _load_building_data(self, site_id: str) -> dict[str, Any]:
        path = self._data_path / site_id / "building.json"
        if not path.exists():
            return {}
        with open(path) as handle:
            return json.load(handle)

    def list_holidays(self, site_id: str) -> list[dict[str, Any]]:
        building = self._load_building_data(site_id)
        custom_holidays = building.get("holidays", [])
        return [*SA_PUBLIC_HOLIDAYS, *custom_holidays]

    def is_holiday(self, site_id: str, target_date: date) -> bool:
        exact_date = target_date.isoformat()
        recurring_date = target_date.strftime("%m-%d")

        for holiday in self.list_holidays(site_id):
            holiday_date = str(holiday.get("date", "")).strip()
            if not holiday_date:
                continue
            if holiday.get("recurring", False):
                if holiday_date[-5:] == recurring_date:
                    return True
            elif holiday_date == exact_date:
                return True

        return False


_holiday_service: SiteHolidayService | None = None


def get_site_holiday_service() -> SiteHolidayService:
    global _holiday_service
    if _holiday_service is None:
        _holiday_service = SiteHolidayService()
    return _holiday_service
