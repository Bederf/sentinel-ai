"""
MRI Evolution maintenance intake adapter.
Polls MRI Evolution REST API and translates job cards to the canonical MaintenanceEvent schema.
Extend MaintenanceAdapter — only fetch_records() and normalise() are MRI-specific.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.models.maintenance_event import MaintenanceEvent
from app.services.mri_evolution_client import MRIEvolutionClient
from app.services.maintenance_adapter_base import MaintenanceAdapter

logger = logging.getLogger(__name__)


class MRIEvolutionAdapter(MaintenanceAdapter):
    """MRI Evolution -> SENTINEL maintenance intake adapter."""

    source_system: str = "mri_evolution"
    adapter_table: str = "maintenance_connector_sync"

    def __init__(self) -> None:
        super().__init__()
        self.client = MRIEvolutionClient()

    async def fetch_records(self, since: datetime | None = None, site_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch job cards updated since last sync from MRI Evolution."""
        return await self.client.fetch_delta(since=since, site_filter=site_id)

    def normalise(self, raw: dict[str, Any], site_id: str | None = None) -> MaintenanceEvent:
        """Translate MRI Evolution API response to canonical MaintenanceEvent."""
        return self.client.normalise(raw, site_id=site_id)
