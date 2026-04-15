"""Shared site holiday calendar service for lifecycle and API consumers."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"


def _easter_sunday(year: int) -> date:
    """Computus: compute Easter Sunday for a given year (Anonymous Gregorian algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    loc = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * loc) // 451
    month = (h + loc - 7 * m + 114) // 31
    day = ((h + loc - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _get_sa_public_holidays(year: int) -> list[dict[str, Any]]:
    """Build SA public holidays for a given year, computing Easter-based dates dynamically."""
    easter = _easter_sunday(year)
    good_friday = easter - timedelta(days=2)
    easter_monday = easter + timedelta(days=1)

    return [
        # Fixed-date holidays
        {"date": f"{year:4d}-01-01", "name": "New Year's Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-03-21", "name": "Human Rights Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-04-27", "name": "Freedom Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-05-01", "name": "Workers' Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-06-16", "name": "Youth Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-08-09", "name": "National Women's Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-09-24", "name": "Heritage Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-12-16", "name": "Day of Reconciliation", "type": "public", "recurring": False},
        {"date": f"{year:4d}-12-25", "name": "Christmas Day", "type": "public", "recurring": False},
        {"date": f"{year:4d}-12-26", "name": "Day of Goodwill", "type": "public", "recurring": False},
        # Easter-based holidays (computed dynamically)
        {"date": good_friday.strftime("%Y-%m-%d"), "name": "Good Friday", "type": "public", "recurring": False},
        {"date": easter_monday.strftime("%Y-%m-%d"), "name": "Family Day", "type": "public", "recurring": False},
    ]


# Cache: {year: holidays_list}
_holidays_cache: dict[int, list[dict[str, Any]]] = {}


def _get_sa_public_holidays_cached(year: int) -> list[dict[str, Any]]:
    if year not in _holidays_cache:
        _holidays_cache[year] = _get_sa_public_holidays(year)
    return _holidays_cache[year]


# Module-level constant for current year
SA_PUBLIC_HOLIDAYS: list[dict[str, Any]] = _get_sa_public_holidays_cached(date.today().year)


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

    def list_holidays(self, site_id: str, year: int | None = None) -> list[dict[str, Any]]:
        if year is None:
            year = date.today().year
        building = self._load_building_data(site_id)
        custom_holidays = building.get("holidays", [])
        return [*_get_sa_public_holidays_cached(year), *custom_holidays]

    def is_holiday(self, site_id: str, target_date: date) -> bool:
        exact_date = target_date.isoformat()
        recurring_date = target_date.strftime("%m-%d")

        for holiday in self.list_holidays(site_id, target_date.year):
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
