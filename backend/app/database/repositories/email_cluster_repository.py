"""Repository for email_clusters and email_intake_clusters tables."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
JSON_PATH = DATA_DIR / "email_clusters.json"


class EmailClusterRepository:
    """DB operations for email_clusters + email_intake_clusters."""

    def __init__(self) -> None:
        self.client = None
        try:
            self.client = get_supabase_client()
        except Exception as exc:
            logger.warning("EmailClusterRepository: Supabase unavailable: %s", exc)

    # -------------------------------------------------------------------------
    # Clusters
    # -------------------------------------------------------------------------

    def upsert_cluster(self, record: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a cluster row."""
        if "id" not in record:
            record["id"] = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        record.setdefault("created_at", now)
        record.setdefault("updated_at", now)
        record.setdefault("status", "open")
        record.setdefault("email_count", 1)
        record.setdefault("keywords", [])

        if self.client:
            try:
                result = self.client.table("email_clusters").upsert(record, on_conflict="id").execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailClusterRepository.upsert_cluster failed: %s", exc)

        return self._upsert_json(record)

    def get_by_id(self, cluster_id: str) -> dict[str, Any] | None:
        if self.client:
            try:
                r = self.client.table("email_clusters").select("*").eq("id", cluster_id).execute()
                if r.data:
                    return r.data[0]
            except Exception as exc:
                logger.error("get_by_id failed: %s", exc)
        return None

    def find_open_cluster(
        self,
        site_id: str,
        zone_id: str,
        complaint_type: str,
    ) -> dict[str, Any] | None:
        """Find an open cluster matching zone + type. Adjacency is handled by caller."""
        if self.client:
            try:
                r = (
                    self.client.table("email_clusters")
                    .select("*")
                    .eq("site_id", site_id)
                    .eq("zone_id", zone_id)
                    .eq("complaint_type", complaint_type)
                    .eq("status", "open")
                    .order("last_seen", desc=True)
                    .limit(1)
                    .execute()
                )
                if r.data:
                    return r.data[0]
            except Exception as exc:
                logger.error("find_open_cluster failed: %s", exc)
        return None

    def increment_cluster(self, cluster_id: str) -> dict[str, Any]:
        now = datetime.utcnow().isoformat()
        updates = {
            "email_count": self.client.table("email_clusters")
            .select("email_count")
            .eq("id", cluster_id)
            .execute()
            .data[0]["email_count"]
            + 1,
            "last_seen": now,
            "updated_at": now,
        }
        if self.client:
            try:
                r = self.client.table("email_clusters").update(updates).eq("id", cluster_id).execute()
                if r.data:
                    return r.data[0]
            except Exception as exc:
                logger.error("increment_cluster failed: %s", exc)
        return {}

    def update_severity(self, cluster_id: str, severity: str, summary: str) -> None:
        now = datetime.utcnow().isoformat()
        updates = {"severity": severity, "summary": summary, "updated_at": now}
        if self.client:
            try:
                self.client.table("email_clusters").update(updates).eq("id", cluster_id).execute()
            except Exception as exc:
                logger.error("update_severity failed: %s", exc)

    def get_open_by_site(self, site_id: str) -> list[dict[str, Any]]:
        if self.client:
            try:
                r = (
                    self.client.table("email_clusters")
                    .select("*")
                    .eq("site_id", site_id)
                    .eq("status", "open")
                    .execute()
                )
                return r.data or []
            except Exception as exc:
                logger.error("get_open_by_site failed: %s", exc)
        return []

    def link_intake_to_cluster(self, intake_id: str, cluster_id: str) -> None:
        if self.client:
            try:
                self.client.table("email_intake_clusters").insert(
                    {
                        "intake_id": intake_id,
                        "cluster_id": cluster_id,
                    }
                ).execute()
            except Exception as exc:
                # Ignore duplicate key — idempotent
                if "duplicate key" not in str(exc).lower():
                    logger.error("link_intake_to_cluster failed: %s", exc)

    # -------------------------------------------------------------------------
    # JSON fallback
    # -------------------------------------------------------------------------

    def _load_json(self) -> dict[str, Any]:
        if JSON_PATH.exists():
            try:
                return json.loads(JSON_PATH.read_text())
            except Exception:
                pass
        return {"clusters": []}

    def _save_json(self, data: dict[str, Any]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(data, indent=2))

    def _upsert_json(self, record: dict[str, Any]) -> dict[str, Any]:
        data = self._load_json()
        clusters = data.get("clusters", [])
        for i, c in enumerate(clusters):
            if c.get("id") == record["id"]:
                clusters[i] = record
                break
        else:
            clusters.append(record)
        self._save_json({"clusters": clusters})
        return record
