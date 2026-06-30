"""Repository for POPIA consent records (Supabase-only).

Migrated from JSON file storage to Supabase exclusively.
Consent records are immutable — withdrawals create new records.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ConsentRepository:
    """CRUD for the consent_records table."""

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    def insert(self, record: dict[str, Any]) -> dict[str, Any] | None:
        result = self.client.table("consent_records").insert(record).execute()
        if result.data:
            return result.data[0]
        logger.error("Failed to insert consent record")
        return None

    def get_latest(self, data_subject_id: str, consent_type: str) -> dict[str, Any] | None:
        result = (
            self.client.table("consent_records")
            .select("*")
            .eq("data_subject_id", data_subject_id)
            .eq("consent_type", consent_type)
            .order("given_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_active_consent(self, data_subject_id: str, consent_type: str) -> bool:
        latest = self.get_latest(data_subject_id, consent_type)
        if latest is None:
            return False
        return bool(latest["consent_given"]) and latest["withdrawn_at"] is None

    def mark_withdrawn(self, record_id: str, withdrawn_at: str) -> None:
        self.client.table("consent_records").update({"withdrawn_at": withdrawn_at}).eq("record_id", record_id).eq(
            "withdrawn_at", None
        ).execute()

    def get_history(self, data_subject_id: str) -> list[dict[str, Any]]:
        result = (
            self.client.table("consent_records")
            .select("*")
            .eq("data_subject_id", data_subject_id)
            .order("given_at", desc=False)
            .execute()
        )
        return result.data if result.data else []

    def get_all_records(self) -> list[dict[str, Any]]:
        result = self.client.table("consent_records").select("*").order("given_at", desc=False).execute()
        return result.data if result.data else []

    def count(self) -> int:
        result = self.client.table("consent_records").select("record_id", count="exact").limit(0).execute()
        return result.count or 0

    def get_by_date_range(self, start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
        query = self.client.table("consent_records").select("*").order("given_at", desc=False)
        if start_date:
            query = query.gte("given_at", start_date)
        if end_date:
            query = query.lte("given_at", end_date)
        result = query.execute()
        return result.data if result.data else []
