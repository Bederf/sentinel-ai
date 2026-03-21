"""Repository for review queue persistence.

Phase 162: Semantic Control Foundation — Plan 05.
Persists review queue entries and decisions with Supabase primary storage
and JSON file fallback.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.models.review_queue import ReviewDecision, ReviewQueueEntry, ReviewQueueStats

logger = logging.getLogger(__name__)

# JSON fallback directory
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "simbiot" / "review_queue"


class ReviewQueueRepository:
    """Repository for review queue CRUD operations."""

    def __init__(self) -> None:
        self._client = None
        self._use_json = False

    # ------------------------------------------------------------------
    # Supabase client (lazy, falls back to JSON on failure)
    # ------------------------------------------------------------------

    @property
    def client(self):
        """Lazy-load Supabase client; fall back to JSON if unavailable."""
        if self._client is None and not self._use_json:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as exc:
                logger.warning("Failed to get Supabase client, using JSON fallback: %s", exc)
                self._use_json = True
        return self._client

    # ------------------------------------------------------------------
    # JSON fallback helpers
    # ------------------------------------------------------------------

    def _queue_json_path(self, entry_id: str) -> Path:
        return DATA_DIR / "entries" / f"{entry_id}.json"

    def _decision_json_path(self, decision_id: str) -> Path:
        return DATA_DIR / "decisions" / f"{decision_id}.json"

    def _store_entry_json(self, entry: ReviewQueueEntry) -> None:
        DATA_DIR.joinpath("entries").mkdir(parents=True, exist_ok=True)
        path = self._queue_json_path(entry.id)
        with path.open("w") as fh:
            json.dump(entry.model_dump(mode="json"), fh, indent=2, default=str)

    def _store_decision_json(self, decision: ReviewDecision) -> None:
        DATA_DIR.joinpath("decisions").mkdir(parents=True, exist_ok=True)
        path = self._decision_json_path(decision.id)
        with path.open("w") as fh:
            json.dump(decision.model_dump(mode="json"), fh, indent=2, default=str)

    def _load_all_entries_json(self, site_id: str, status: str | None = None) -> list[ReviewQueueEntry]:
        entries_dir = DATA_DIR / "entries"
        if not entries_dir.exists():
            return []
        entries = []
        for path in entries_dir.glob("*.json"):
            try:
                with path.open() as fh:
                    data = json.load(fh)
                entry = ReviewQueueEntry(**data)
                if entry.site_id == site_id and (status is None or entry.status == status):
                    entries.append(entry)
            except Exception as exc:
                logger.warning("Failed to load entry %s: %s", path, exc)
        return entries

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def add_to_queue(self, entry: ReviewQueueEntry) -> str:
        """Add a classification to the review queue. Returns the entry ID."""
        if entry.id is None:
            entry.id = str(uuid4())
        entry.updated_at = datetime.now(UTC)

        if not self._use_json and self.client is not None:
            try:
                payload = {
                    "id": entry.id,
                    "site_id": entry.site_id,
                    "equipment_id": entry.equipment_id,
                    "point_id": entry.point_id,
                    "classification_id": entry.classification_id,
                    "semantic_tags": entry.semantic_tags,
                    "confidence_score": entry.confidence_score,
                    "confidence_level": entry.confidence_level,
                    "safety_class": entry.safety_class,
                    "automation_tier": entry.automation_tier,
                    "validation_passed": entry.validation_passed,
                    "validation_errors": entry.validation_errors,
                    "completeness_score": entry.completeness_score,
                    "status": entry.status,
                    "priority": entry.priority,
                    "classified_by": entry.classified_by,
                    "classified_at": (
                        entry.classified_at.isoformat()
                        if isinstance(entry.classified_at, datetime)
                        else entry.classified_at
                    ),
                }
                self.client.table("review_queue").insert(payload).execute()
                return entry.id
            except Exception as exc:
                logger.warning("Supabase insert failed, falling back to JSON: %s", exc)

        self._store_entry_json(entry)
        return entry.id

    async def get_pending_reviews(
        self,
        site_id: str,
        safety_class: str | None = None,
        equipment_id: str | None = None,
        confidence_threshold: float | None = None,
        limit: int = 100,
    ) -> list[ReviewQueueEntry]:
        """Get pending reviews with optional filtering, sorted by priority ascending."""
        if not self._use_json and self.client is not None:
            try:
                query = (
                    self.client.table("review_queue")
                    .select("*")
                    .eq("site_id", site_id)
                    .eq("status", "pending")
                    .order("priority")
                    .limit(limit)
                )
                if safety_class:
                    query = query.eq("safety_class", safety_class)
                if equipment_id:
                    query = query.eq("equipment_id", equipment_id)
                if confidence_threshold is not None:
                    query = query.lte("confidence_score", confidence_threshold)
                result = query.execute()
                return [ReviewQueueEntry(**row) for row in (result.data or [])]
            except Exception as exc:
                logger.warning("Supabase query failed, falling back to JSON: %s", exc)

        entries = self._load_all_entries_json(site_id, status="pending")

        # Apply filters
        if safety_class:
            entries = [e for e in entries if e.safety_class == safety_class]
        if equipment_id:
            entries = [e for e in entries if e.equipment_id == equipment_id]
        if confidence_threshold is not None:
            entries = [e for e in entries if e.confidence_score <= confidence_threshold]

        entries.sort(key=lambda e: e.priority)
        return entries[:limit]

    async def get_review_stats(self, site_id: str) -> ReviewQueueStats:
        """Get queue statistics: total pending, by priority, by safety class, avg age."""
        pending = await self.get_pending_reviews(site_id, limit=10000)
        by_safety: dict[str, int] = {}
        by_confidence: dict[str, int] = {}
        high_priority = 0
        total_age_hours = 0.0
        now = datetime.now(UTC)

        for entry in pending:
            by_safety[entry.safety_class] = by_safety.get(entry.safety_class, 0) + 1
            by_confidence[entry.confidence_level] = by_confidence.get(entry.confidence_level, 0) + 1
            if entry.priority <= 50:
                high_priority += 1
            classified_at = entry.classified_at
            if isinstance(classified_at, str):
                classified_at = datetime.fromisoformat(classified_at)
            if classified_at.tzinfo is None:
                classified_at = classified_at.replace(tzinfo=UTC)
            total_age_hours += (now - classified_at).total_seconds() / 3600.0

        avg_age = total_age_hours / len(pending) if pending else 0.0

        return ReviewQueueStats(
            total_pending=len(pending),
            by_safety_class=by_safety,
            by_confidence_level=by_confidence,
            avg_age_hours=avg_age,
            high_priority_count=high_priority,
        )

    async def make_decision(
        self,
        entry_id: str,
        decision_type: str,
        reviewed_by: str,
        review_notes: str,
        decision_reason: str | None = None,
    ) -> bool:
        """Record approval/rejection decision and update queue status."""
        reviewed_at = datetime.now(UTC)
        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "override": "overridden",
        }
        new_status = status_map.get(decision_type, "reviewed")

        # Persist audit decision record
        decision = ReviewDecision(
            id=str(uuid4()),
            review_queue_id=entry_id,
            decision_type=decision_type,
            decision_reason=decision_reason,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            review_notes=review_notes,
        )

        if not self._use_json and self.client is not None:
            try:
                # Update queue entry
                self.client.table("review_queue").update(
                    {
                        "status": new_status,
                        "reviewed_by": reviewed_by,
                        "reviewed_at": reviewed_at.isoformat(),
                        "review_notes": review_notes,
                        "decision_reason": decision_reason,
                        "updated_at": reviewed_at.isoformat(),
                    }
                ).eq("id", entry_id).execute()

                # Insert decision record
                self.client.table("review_decisions").insert(
                    {
                        "id": decision.id,
                        "review_queue_id": entry_id,
                        "decision_type": decision_type,
                        "decision_reason": decision_reason,
                        "reviewed_by": reviewed_by,
                        "reviewed_at": reviewed_at.isoformat(),
                        "review_notes": review_notes,
                    }
                ).execute()
                return True
            except Exception as exc:
                logger.warning("Supabase decision failed, falling back to JSON: %s", exc)

        # JSON fallback — update entry file
        entry_path = self._queue_json_path(entry_id)
        if entry_path.exists():
            with entry_path.open() as fh:
                data = json.load(fh)
            data["status"] = new_status
            data["reviewed_by"] = reviewed_by
            data["reviewed_at"] = reviewed_at.isoformat()
            data["review_notes"] = review_notes
            data["decision_reason"] = decision_reason
            data["updated_at"] = reviewed_at.isoformat()
            with entry_path.open("w") as fh:
                json.dump(data, fh, indent=2, default=str)

        self._store_decision_json(decision)
        return True

    async def make_override(
        self,
        entry_id: str,
        reviewed_by: str,
        correct_tags: list[str],
        justification: str,
    ) -> bool:
        """Override classification with corrected tags."""
        reviewed_at = datetime.now(UTC)

        if not self._use_json and self.client is not None:
            try:
                self.client.table("review_queue").update(
                    {
                        "status": "overridden",
                        "reviewed_by": reviewed_by,
                        "reviewed_at": reviewed_at.isoformat(),
                        "override_tags": correct_tags,
                        "override_justification": justification,
                        "updated_at": reviewed_at.isoformat(),
                    }
                ).eq("id", entry_id).execute()

                decision_id = str(uuid4())
                self.client.table("review_decisions").insert(
                    {
                        "id": decision_id,
                        "review_queue_id": entry_id,
                        "decision_type": "override",
                        "reviewed_by": reviewed_by,
                        "reviewed_at": reviewed_at.isoformat(),
                        "review_notes": justification,
                        "metadata": {"override_tags": correct_tags},
                    }
                ).execute()
                return True
            except Exception as exc:
                logger.warning("Supabase override failed, falling back to JSON: %s", exc)

        entry_path = self._queue_json_path(entry_id)
        if entry_path.exists():
            with entry_path.open() as fh:
                data = json.load(fh)
            data["status"] = "overridden"
            data["reviewed_by"] = reviewed_by
            data["reviewed_at"] = reviewed_at.isoformat()
            data["override_tags"] = correct_tags
            data["override_justification"] = justification
            data["updated_at"] = reviewed_at.isoformat()
            with entry_path.open("w") as fh:
                json.dump(data, fh, indent=2, default=str)

        decision = ReviewDecision(
            id=str(uuid4()),
            review_queue_id=entry_id,
            decision_type="override",
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            review_notes=justification,
            metadata={"override_tags": correct_tags},
        )
        self._store_decision_json(decision)
        return True

    async def bulk_decision(
        self,
        entry_ids: list[str],
        decision_type: str,
        reviewed_by: str,
        review_notes: str = "",
    ) -> int:
        """Apply same decision to multiple queue entries. Returns count of entries updated."""
        count = 0
        for entry_id in entry_ids:
            success = await self.make_decision(entry_id, decision_type, reviewed_by, review_notes)
            if success:
                count += 1
        return count

    async def get_review_history(self, entry_id: str) -> list[ReviewDecision]:
        """Get the full review decision history for a queue entry."""
        if not self._use_json and self.client is not None:
            try:
                result = (
                    self.client.table("review_decisions")
                    .select("*")
                    .eq("review_queue_id", entry_id)
                    .order("reviewed_at")
                    .execute()
                )
                return [ReviewDecision(**row) for row in (result.data or [])]
            except Exception as exc:
                logger.warning("Supabase history query failed, falling back to JSON: %s", exc)

        decisions_dir = DATA_DIR / "decisions"
        if not decisions_dir.exists():
            return []
        decisions = []
        for path in decisions_dir.glob("*.json"):
            try:
                with path.open() as fh:
                    data = json.load(fh)
                d = ReviewDecision(**data)
                if d.review_queue_id == entry_id:
                    decisions.append(d)
            except Exception:
                pass
        decisions.sort(key=lambda d: d.reviewed_at)
        return decisions


_repository: ReviewQueueRepository | None = None


def get_review_queue_repository() -> ReviewQueueRepository:
    """Get singleton review queue repository."""
    global _repository
    if _repository is None:
        _repository = ReviewQueueRepository()
    return _repository
