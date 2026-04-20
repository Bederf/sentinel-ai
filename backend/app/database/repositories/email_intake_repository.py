"""Repository for SENTINEL email intake persistence (Phase 131).

Follows the 3-tier fallback pattern: Supabase → JSON fallback.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
JSON_PATH = DATA_DIR / "email_intakes.json"


class EmailIntakeRepository:
    """Database operations for ``email_intakes``."""

    def __init__(self) -> None:
        self.client = None
        try:
            self.client = get_supabase_client()
        except Exception as exc:  # pragma: no cover
            logger.warning("EmailIntakeRepository: Supabase client unavailable: %s", exc)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        """Insert a new email intake row."""
        if "id" not in record:
            record["id"] = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        record.setdefault("created_at", now)
        record.setdefault("updated_at", now)
        record.setdefault("pipeline_status", "received")

        if self.client:
            try:
                result = self.client.table("email_intakes").insert(record).execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.create failed (Supabase): %s", exc)

        # JSON fallback
        return self._create_json(record)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, intake_id: str) -> dict[str, Any] | None:
        """Return a single intake by primary key."""
        if self.client:
            try:
                result = self.client.table("email_intakes").select("*").eq("id", intake_id).execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.get_by_id failed: %s", exc)
        return self._get_by_id_json(intake_id)

    def get_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        """Return intake by RFC 822 Message-ID (exact dedup)."""
        if not message_id:
            return None
        if self.client:
            try:
                result = self.client.table("email_intakes").select("*").eq("message_id", message_id).limit(1).execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.get_by_message_id failed: %s", exc)
        return self._get_by_message_id_json(message_id)

    # ------------------------------------------------------------------
    # Upsert (for IMAP poller — Phase 189)
    # ------------------------------------------------------------------

    def upsert_email_intake(self, result: Any, msg_hash: str) -> dict[str, Any]:
        """Insert or update an email intake record (IMAP poller path).

        Args:
            result: EmailIntakeResult from process_email()
            msg_hash: SHA-256 hash of the Message-ID (deduplication key)
        """
        record: dict[str, Any] = {
            "discipline": result.discipline,
            "sub_category": result.sub_category,
            "specialty": result.specialty,
            "priority": result.priority,
            "location_desk": result.location_desk,
            "location_floor": result.location_floor,
            "location_area": result.location_area,
            "phone": result.phone,
            "issue_summary": result.issue_summary,
            "completeness": result.completeness,
            "action": result.action,
            "reply_text": result.reply_text,
            "agent_model": result.agent_model,
            "agent_latency_ms": result.agent_latency_ms,
            "msg_hash": msg_hash,
        }

        # Try upsert via message_id hash first
        if self.client:
            try:
                # Check if exists by hash
                existing = (
                    self.client.table("email_intakes").select("id, message_id").eq("msg_hash", msg_hash).execute()
                )
                if existing.data:
                    # Update existing
                    updates = {**record, "updated_at": datetime.utcnow().isoformat()}
                    upd = self.client.table("email_intakes").update(updates).eq("id", existing.data[0]["id"]).execute()
                    if upd.data:
                        return upd.data[0]

                # Insert new
                record["message_id"] = result.message_id
                record["from_email"] = result.from_email
                record["from_name"] = result.from_name
                record["subject"] = result.subject
                record["body_text"] = result.body_plain
                record["pipeline_status"] = "received"
                ins = self.client.table("email_intakes").insert(record).execute()
                if ins.data:
                    return ins.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.upsert_email_intake failed: %s", exc)

        # JSON fallback (no upsert — insert only, caller checks email_exists_hash first)
        return self._create_json(record)

    def email_exists_hash(self, msg_hash: str) -> bool:
        """Check if email already processed (deduplication by msg_hash)."""
        if self.client:
            try:
                result = self.client.table("email_intakes").select("id").eq("msg_hash", msg_hash).limit(1).execute()
                return len(result.data) > 0
            except Exception as exc:
                logger.error("EmailIntakeRepository.email_exists_hash failed: %s", exc)
        # JSON fallback
        for r in self._load_json():
            if r.get("msg_hash") == msg_hash:
                return True
        return False

    def get_latest_by_reference(self, reference: str) -> dict[str, Any] | None:
        """Return latest intake row for an existing reference code."""
        if not reference:
            return None
        if self.client:
            try:
                result = (
                    self.client.table("email_intakes")
                    .select("*")
                    .eq("existing_reference", reference)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.get_latest_by_reference failed: %s", exc)
        return self._get_latest_by_reference_json(reference)

    def find_recent(
        self,
        from_email: str,
        site_id: str | None,
        issue_category: str | None,
        hours: int = 24,
    ) -> dict[str, Any] | None:
        """Heuristic dedup: same sender + site + category within window."""
        if not from_email:
            return None
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        if self.client:
            try:
                query = (
                    self.client.table("email_intakes")
                    .select("*")
                    .eq("from_email", from_email)
                    .gte("received_at", cutoff)
                    .order("received_at", desc=True)
                    .limit(1)
                )
                if site_id:
                    query = query.eq("site_id", site_id)
                if issue_category:
                    query = query.eq("issue_category", issue_category)
                result = query.execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.find_recent failed: %s", exc)

        return self._find_recent_json(from_email, site_id, issue_category, hours)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_status(self, intake_id: str, status: str, **fields: Any) -> dict[str, Any]:
        """Update pipeline_status and optional extra fields."""
        updates: dict[str, Any] = {"pipeline_status": status, **fields}
        updates["updated_at"] = datetime.utcnow().isoformat()
        if self.client:
            try:
                result = self.client.table("email_intakes").update(updates).eq("id", intake_id).execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.update_status failed: %s", exc)
        return self._update_json(intake_id, updates)

    def update_enrichment(self, intake_id: str, enrichment: dict[str, Any]) -> dict[str, Any]:
        """Persist BMS enrichment context."""
        updates = {
            "bms_context": enrichment,
            "enrichment_ts": datetime.utcnow().isoformat(),
            "pipeline_status": "enriched",
            "updated_at": datetime.utcnow().isoformat(),
        }
        if self.client:
            try:
                result = self.client.table("email_intakes").update(updates).eq("id", intake_id).execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("EmailIntakeRepository.update_enrichment failed: %s", exc)
        return self._update_json(intake_id, updates)

    # ------------------------------------------------------------------
    # JSON fallback helpers
    # ------------------------------------------------------------------

    def _load_json(self) -> list[dict[str, Any]]:
        if JSON_PATH.exists():
            try:
                with open(JSON_PATH) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save_json(self, data: list[dict[str, Any]]) -> None:
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(JSON_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _create_json(self, record: dict[str, Any]) -> dict[str, Any]:
        records = self._load_json()
        records.append(record)
        self._save_json(records)
        return record

    def _get_by_id_json(self, intake_id: str) -> dict[str, Any] | None:
        for r in self._load_json():
            if r.get("id") == intake_id:
                return r
        return None

    def _get_by_message_id_json(self, message_id: str) -> dict[str, Any] | None:
        for r in self._load_json():
            if r.get("message_id") == message_id:
                return r
        return None

    def _get_latest_by_reference_json(self, reference: str) -> dict[str, Any] | None:
        matches = [r for r in self._load_json() if r.get("existing_reference") == reference]
        if not matches:
            return None
        matches.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return matches[0]

    def _find_recent_json(
        self,
        from_email: str,
        site_id: str | None,
        issue_category: str | None,
        hours: int,
    ) -> dict[str, Any] | None:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        candidates = []
        for r in self._load_json():
            if r.get("from_email") != from_email:
                continue
            if r.get("received_at", r.get("created_at", "")) < cutoff:
                continue
            if site_id and r.get("site_id") != site_id:
                continue
            if issue_category and r.get("issue_category") != issue_category:
                continue
            candidates.append(r)
        if not candidates:
            return None
        candidates.sort(key=lambda r: r.get("received_at", r.get("created_at", "")), reverse=True)
        return candidates[0]

    def _update_json(self, intake_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        records = self._load_json()
        for r in records:
            if r.get("id") == intake_id:
                r.update(updates)
                self._save_json(records)
                return r
        return updates


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_repository: EmailIntakeRepository | None = None


def get_email_intake_repository() -> EmailIntakeRepository:
    """Get singleton repository."""
    global _repository
    if _repository is None:
        _repository = EmailIntakeRepository()
    return _repository
