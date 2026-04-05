"""
MRI Evolution REST API client.
Auth: Basic Auth (username:password base64) or Bearer API key.
Base URL: https://{tenant}.mrisoftware.com/Evolution/api/v1/

FIELD_MAP is PROVISIONAL — field names are assumed from CSV export column names.
Must be updated when vendor confirms actual API field names.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

import httpx

from app.models.maintenance_event import MaintenanceEvent
from app.services.mri_priority_map import normalise_priority

# PROVISIONAL — update when vendor confirms API field names
FIELD_MAP: dict[str, str] = {
    "task_id":      "TaskId",
    "problem":      "Problem",
    "task_created": "TaskCreated",
    "building":     "Building",
    "location":     "Location",
    "discipline":   "Discipline",
    "status":       "Status",
    "completion":   "LevelOfCompletion",
    "assigned_at":  "AssignedDate",
    "attended_at":  "AttendedDate",
    "temp_fixed_at":"TempFixDate",
    "resolved_at":  "ResolvedDate",
    "priority":     "Priority",
    "sla_pct":      "SLAPercentage",
    "days_open":    "DaysOpen",
}


def _get_settings():
    """Lazy import to avoid circular dependencies."""
    from app.core.config import settings
    return settings


class MRIEvolutionClient:
    """Async HTTP client for MRI Evolution REST API."""

    def __init__(self) -> None:
        s = _get_settings()
        self.base_url = s.MRI_EVOLUTION_BASE_URL
        self.api_key = s.MRI_EVOLUTION_API_KEY
        self.username = s.MRI_EVOLUTION_USERNAME
        self.password = s.MRI_EVOLUTION_PASSWORD
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        creds = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(headers=self._headers(), timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_delta(
        self, since: datetime | None = None, site_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Pull job cards updated since last sync. Falls back to full pull."""
        params: dict[str, Any] = {}
        if since:
            params["updated_since"] = since.isoformat()
        if site_filter:
            params["site"] = site_filter

        client = await self._get_client()
        response = await client.get(f"{self.base_url}/tasks", params=params)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else data.get("results", [])

    async def fetch_single(self, task_id: str) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.get(f"{self.base_url}/tasks/{task_id}")
        response.raise_for_status()
        return response.json()

    def normalise(self, raw: dict[str, Any], site_id: str | None = None) -> MaintenanceEvent:
        """Translate MRI Evolution API response to canonical MaintenanceEvent."""
        priority_raw = raw.get(FIELD_MAP["priority"])
        priority_data = normalise_priority(priority_raw)
        problem = raw.get(FIELD_MAP["problem"], "") or ""
        is_ppm = "PPM" in problem.upper() or "PLANNED" in (priority_raw or "").upper()

        return MaintenanceEvent(
            external_ref=raw.get(FIELD_MAP["task_id"], ""),
            site_id=site_id,
            building=raw.get(FIELD_MAP["building"]),
            location=raw.get(FIELD_MAP["location"]),
            discipline=raw.get(FIELD_MAP["discipline"]),
            problem=problem,
            priority_raw=priority_raw,
            priority_normalised=priority_data["tier"],
            sla_respond_hours=priority_data["respond_hours"],
            sla_attend_hours=priority_data["attend_hours"],
            sla_temp_fix_hours=priority_data["temp_fix_hours"],
            sla_resolve_work_days=priority_data["resolve_work_days"],
            is_ppm=is_ppm,
            status=raw.get(FIELD_MAP["status"]),
            created_at_source=self._parse_dt(raw.get(FIELD_MAP["task_created"])),
            assigned_at=self._parse_dt(raw.get(FIELD_MAP["assigned_at"])),
            attended_at=self._parse_dt(raw.get(FIELD_MAP["attended_at"])),
            temp_fixed_at=self._parse_dt(raw.get(FIELD_MAP["temp_fixed_at"])),
            resolved_at=self._parse_dt(raw.get(FIELD_MAP["resolved_at"])),
            level_of_completion=raw.get(FIELD_MAP["completion"]),
            sla_pct=self._parse_float(raw.get(FIELD_MAP["sla_pct"])),
            days_open=self._parse_int(raw.get(FIELD_MAP["days_open"])),
            metadata=raw,
        )

    def _parse_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    def _parse_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
