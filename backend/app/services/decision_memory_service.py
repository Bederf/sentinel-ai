"""Decision Memory Service — learns from diagnostic and control outcomes.

Records every diagnosis-action-outcome triple and extracts patterns
when enough evidence accumulates. Over time, the system learns:
  pattern -> best fix -> expected outcome

Architecture:
    Event -> Reasoning -> Action -> Outcome -> DecisionMemory -> Pattern
    Next similar event -> Query patterns -> Faster/better recommendation

Phase 145: Decision Memory Layer.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.models.decision_memory import (
    DecisionOutcome,
    DecisionPattern,
    DecisionRecord,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "decision_memory"
RECORDS_FILE = DATA_DIR / "decision_records.json"
PATTERNS_FILE = DATA_DIR / "decision_patterns.json"

# Minimum records before extracting a pattern
PATTERN_THRESHOLD = 3


class DecisionMemoryService:
    """Service for recording decisions and learning patterns.

    Stores records to JSON (with Supabase integration when available).
    Automatically extracts patterns when evidence accumulates.
    """

    _instance: DecisionMemoryService | None = None

    def __init__(
        self,
        data_dir: Path | None = None,
        records_file: Path | None = None,
        patterns_file: Path | None = None,
    ) -> None:
        self._records: list[DecisionRecord] = []
        self._patterns: list[DecisionPattern] = []
        self._loaded = False
        self._client = None
        self._site_uuid_cache: dict[str, str | None] = {}
        self._equipment_uuid_cache: dict[str, str | None] = {}
        # Allow explicit path overrides for testing isolation
        self._data_dir_override = data_dir
        self._records_file_override = records_file
        self._patterns_file_override = patterns_file

    @property
    def _db_enabled(self) -> bool:
        return (
            self._data_dir_override is None
            and self._records_file_override is None
            and self._patterns_file_override is None
        )

    @property
    def client(self):
        if not self._db_enabled:
            return None
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    @property
    def _data_dir(self) -> Path:
        return self._data_dir_override if self._data_dir_override is not None else DATA_DIR

    @property
    def _records_file(self) -> Path:
        return self._records_file_override if self._records_file_override is not None else RECORDS_FILE

    @property
    def _patterns_file(self) -> Path:
        return self._patterns_file_override if self._patterns_file_override is not None else PATTERNS_FILE

    def _ensure_loaded(self) -> None:
        """Lazy-load records and patterns from disk."""
        if self._loaded:
            return
        self._records = self._load_records()
        self._patterns = self._load_patterns()
        self._loaded = True

    # -----------------------------------------------------------------
    # Record management
    # -----------------------------------------------------------------

    async def record_decision(
        self,
        event_type: str,
        equipment_id: str,
        equipment_type: str,
        site_id: str,
        diagnosis: str,
        diagnosis_confidence: float = 0.0,
        diagnosis_source: str = "ai_reasoning",
        action_type: str = "",
        action_details: dict[str, Any] | None = None,
        signals_snapshot: list[dict] | None = None,
        correlation_id: str | None = None,
        recommendation_id: str | None = None,
        event_id: str | None = None,
    ) -> DecisionRecord:
        """Record a new decision.

        Called when AI makes a recommendation or control action is taken.
        """
        self._ensure_loaded()

        record = DecisionRecord(
            event_type=event_type,
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            site_id=site_id,
            diagnosis=diagnosis,
            diagnosis_confidence=diagnosis_confidence,
            diagnosis_source=diagnosis_source,
            action_type=action_type,
            action_details=action_details or {},
            signals_snapshot=signals_snapshot or [],
            correlation_id=correlation_id,
            recommendation_id=recommendation_id,
            event_id=event_id,
        )

        self._records.append(record)
        self._save_records()

        logger.info(
            "Decision recorded: %s for %s (%s) -> %s",
            record.record_id,
            equipment_id,
            event_type,
            diagnosis,
        )
        return record

    async def record_outcome(
        self,
        record_id: str,
        outcome: DecisionOutcome,
        outcome_details: str | None = None,
        work_order_id: str | None = None,
    ) -> DecisionRecord | None:
        """Record the outcome of a previously recorded decision.

        After recording, checks if a pattern can be extracted or updated.
        """
        self._ensure_loaded()

        record = self._find_record(record_id)
        if not record:
            logger.warning("Decision record %s not found", record_id)
            return None

        now = datetime.now(UTC)
        record.outcome = outcome
        record.outcome_details = outcome_details
        record.outcome_evaluated_at = now
        record.updated_at = now

        if work_order_id:
            record.work_order_id = work_order_id

        # Calculate resolution time
        if record.action_executed_at:
            delta = now - record.action_executed_at
            record.resolution_time_minutes = delta.total_seconds() / 60
        elif record.created_at:
            delta = now - record.created_at
            record.resolution_time_minutes = delta.total_seconds() / 60

        self._save_records()

        # Try to extract or update patterns
        await self._extract_patterns(record.event_type, record.equipment_type)

        logger.info(
            "Outcome recorded for %s: %s (%s)",
            record_id,
            outcome.value,
            outcome_details or "",
        )
        return record

    # -----------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------

    async def find_similar_decisions(
        self,
        event_type: str,
        equipment_type: str,
        equipment_id: str | None = None,
        limit: int = 10,
    ) -> list[DecisionRecord]:
        """Find past decisions for similar events.

        Prioritizes: same equipment > same type > same event type.
        """
        self._ensure_loaded()

        # Score each record by relevance
        scored = []
        for record in self._records:
            if record.outcome == DecisionOutcome.PENDING:
                continue
            score = 0
            if record.event_type == event_type:
                score += 10
            if record.equipment_type == equipment_type:
                score += 5
            if equipment_id and record.equipment_id == equipment_id:
                score += 20
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    async def get_recommended_action(
        self,
        event_type: str,
        equipment_type: str,
    ) -> DecisionPattern | None:
        """Get the best learned pattern for an event type + equipment type.

        Returns the pattern with highest confidence if one exists.
        """
        self._ensure_loaded()

        best: DecisionPattern | None = None
        for pattern in self._patterns:
            if pattern.event_type == event_type and pattern.equipment_type == equipment_type:
                if best is None or pattern.diagnosis_confidence > best.diagnosis_confidence:
                    best = pattern

        if best:
            best.last_matched_at = datetime.now(UTC)
            self._save_patterns()

        return best

    async def get_active_events_with_history(
        self,
        event_type: str,
        equipment_type: str,
    ) -> dict[str, Any]:
        """Get pattern + recent decisions for a given event/equipment combo.

        Used by the reasoning layer for enriched context.
        """
        pattern = await self.get_recommended_action(event_type, equipment_type)
        decisions = await self.find_similar_decisions(event_type, equipment_type, limit=5)

        return {
            "pattern": pattern.to_dict() if pattern else None,
            "recent_decisions": [d.to_dict() for d in decisions],
            "has_historical_knowledge": pattern is not None,
        }

    # -----------------------------------------------------------------
    # Pattern extraction
    # -----------------------------------------------------------------

    async def _extract_patterns(self, event_type: str, equipment_type: str) -> DecisionPattern | None:
        """Extract or update a pattern from accumulated records.

        Requires >= PATTERN_THRESHOLD records with same diagnosis + RESOLVED outcome.
        """
        relevant = [
            r
            for r in self._records
            if r.event_type == event_type
            and r.equipment_type == equipment_type
            and r.outcome != DecisionOutcome.PENDING
        ]

        if len(relevant) < PATTERN_THRESHOLD:
            return None

        # Group by diagnosis
        by_diagnosis: dict[str, list[DecisionRecord]] = defaultdict(list)
        for r in relevant:
            if r.diagnosis:
                by_diagnosis[r.diagnosis].append(r)

        best_pattern: DecisionPattern | None = None

        for diagnosis, records in by_diagnosis.items():
            if len(records) < PATTERN_THRESHOLD:
                continue

            resolved = [r for r in records if r.outcome == DecisionOutcome.RESOLVED]
            total = len(records)
            success_rate = len(resolved) / total if total > 0 else 0.0

            if success_rate < 0.5:
                continue

            # Find most common action
            action_counts = Counter(r.action_type for r in resolved if r.action_type)
            if not action_counts:
                continue
            best_action = action_counts.most_common(1)[0][0]
            best_action_records = [r for r in resolved if r.action_type == best_action]

            # Average resolution time
            times = [r.resolution_time_minutes for r in resolved if r.resolution_time_minutes]
            avg_time = sum(times) / len(times) if times else 0.0

            # Sites
            sites = list({r.site_id for r in records if r.site_id})

            # Check if pattern already exists
            existing = self._find_pattern(event_type, equipment_type, diagnosis)

            if existing:
                existing.total_occurrences = total
                existing.resolved_count = len(resolved)
                existing.success_rate = success_rate
                existing.avg_resolution_time_minutes = avg_time
                existing.diagnosis_confidence = success_rate
                existing.applicable_sites = sites
                existing.updated_at = datetime.now(UTC)
                pattern = existing
            else:
                # Get action details from most recent successful record
                action_details = best_action_records[-1].action_details if best_action_records else {}

                pattern = DecisionPattern(
                    event_type=event_type,
                    equipment_type=equipment_type,
                    likely_diagnosis=diagnosis,
                    diagnosis_confidence=success_rate,
                    recommended_action=best_action,
                    action_details=action_details,
                    total_occurrences=total,
                    resolved_count=len(resolved),
                    success_rate=success_rate,
                    avg_resolution_time_minutes=avg_time,
                    applicable_sites=sites,
                )
                self._patterns.append(pattern)

            if best_pattern is None or pattern.diagnosis_confidence > best_pattern.diagnosis_confidence:
                best_pattern = pattern

        self._save_patterns()
        return best_pattern

    # -----------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------

    async def get_decision_stats(self, site_id: str | None = None) -> dict[str, Any]:
        """Get statistics about decision memory."""
        self._ensure_loaded()

        records = self._records
        if site_id:
            records = [r for r in records if r.site_id == site_id]

        outcome_dist = Counter(r.outcome.value for r in records)
        type_dist = Counter(r.event_type for r in records)

        resolved = [r for r in records if r.outcome == DecisionOutcome.RESOLVED]
        times = [r.resolution_time_minutes for r in resolved if r.resolution_time_minutes]

        return {
            "total_records": len(records),
            "total_patterns": len(self._patterns),
            "outcome_distribution": dict(outcome_dist),
            "event_type_distribution": dict(type_dist),
            "avg_resolution_time_minutes": sum(times) / len(times) if times else 0,
            "resolution_rate": len(resolved) / len(records) if records else 0,
            "top_patterns": [
                p.to_dict() for p in sorted(self._patterns, key=lambda p: p.success_rate, reverse=True)[:5]
            ],
        }

    # -----------------------------------------------------------------
    # Prompt formatting
    # -----------------------------------------------------------------

    def format_for_prompt(
        self,
        patterns: list[DecisionPattern] | None = None,
        records: list[DecisionRecord] | None = None,
    ) -> str:
        """Format decision memory as readable text for AI prompt injection."""
        sections = []

        if patterns:
            sections.append("Historical Patterns:")
            for p in patterns:
                sections.append(
                    f"  - {p.event_type} on {p.equipment_type}: "
                    f"likely {p.likely_diagnosis} "
                    f"(confidence {p.diagnosis_confidence:.0%}, "
                    f"{p.resolved_count}/{p.total_occurrences} resolved). "
                    f"Action: {p.recommended_action}. "
                    f"Avg resolution: {p.avg_resolution_time_minutes:.0f} min."
                )

        if records:
            sections.append("\nRecent Similar Decisions:")
            for r in records[:5]:
                outcome_str = r.outcome.value
                sections.append(f"  - [{outcome_str}] {r.equipment_id}: {r.diagnosis} -> {r.action_type}")
                if r.outcome_details:
                    sections.append(f"    Note: {r.outcome_details}")

        return "\n".join(sections) if sections else ""

    # -----------------------------------------------------------------
    # Persistence (Postgres primary, JSON fallback for test/local overrides)
    # -----------------------------------------------------------------

    def _find_record(self, record_id: str) -> DecisionRecord | None:
        for r in self._records:
            if r.record_id == record_id:
                return r
        return None

    def _find_pattern(self, event_type: str, equipment_type: str, diagnosis: str) -> DecisionPattern | None:
        for p in self._patterns:
            if p.event_type == event_type and p.equipment_type == equipment_type and p.likely_diagnosis == diagnosis:
                return p
        return None

    def _load_records(self) -> list[DecisionRecord]:
        records_file = self._records_file
        try:
            if self._db_enabled and self.client:
                response = self.client.table("decision_records").select("*").order("created_at").execute()
                records = []
                for row in response.data or []:
                    if row.get("decision_id") or (
                        isinstance(row.get("decision_data"), dict) and row["decision_data"].get("record_id")
                    ):
                        records.append(self._record_from_db_row(row))
                return records
            if records_file.exists():
                with open(records_file) as f:
                    data = json.load(f)
                return [DecisionRecord.from_dict(d) for d in data]
        except Exception as e:
            logger.error("Failed to load decision records: %s", e)
        return []

    def _load_patterns(self) -> list[DecisionPattern]:
        patterns_file = self._patterns_file
        try:
            if self._db_enabled and self.client:
                response = self.client.table("decision_patterns").select("*").order("created_at").execute()
                return [self._pattern_from_db_row(d) for d in (response.data or [])]
            if patterns_file.exists():
                with open(patterns_file) as f:
                    data = json.load(f)
                return [DecisionPattern.from_dict(d) for d in data]
        except Exception as e:
            logger.error("Failed to load decision patterns: %s", e)
        return []

    def _save_records(self) -> None:
        try:
            if self._db_enabled and self.client:
                for record in self._records:
                    self._save_record_db(record)
                return
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._records_file, "w") as f:
                json.dump([r.to_dict() for r in self._records], f, indent=2)
        except Exception as e:
            logger.error("Failed to save decision records: %s", e)

    def _save_patterns(self) -> None:
        try:
            if self._db_enabled and self.client:
                for pattern in self._patterns:
                    self._save_pattern_db(pattern)
                return
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._patterns_file, "w") as f:
                json.dump([p.to_dict() for p in self._patterns], f, indent=2)
        except Exception as e:
            logger.error("Failed to save decision patterns: %s", e)

    def _record_from_db_row(self, row: dict[str, Any]) -> DecisionRecord:
        data = row.get("decision_data") or {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("record_id", row.get("decision_id"))
        data.setdefault("outcome", row.get("outcome") or "pending")
        data.setdefault("diagnosis", row.get("reasoning") or "")
        data.setdefault("diagnosis_confidence", row.get("confidence") or 0.0)
        data.setdefault("created_at", row.get("created_at"))
        data.setdefault("updated_at", row.get("updated_at"))
        return DecisionRecord.from_dict(data)

    def _pattern_from_db_row(self, row: dict[str, Any]) -> DecisionPattern:
        trigger = row.get("trigger_conditions") or {}
        actions = row.get("recommended_actions") or {}
        if not isinstance(trigger, dict):
            trigger = {}
        if not isinstance(actions, dict):
            actions = {}
        return DecisionPattern.from_dict(
            {
                "pattern_id": row.get("pattern_name"),
                "event_type": trigger.get("event_type") or row.get("pattern_type") or "",
                "equipment_type": trigger.get("equipment_type") or "",
                "likely_diagnosis": trigger.get("diagnosis") or "",
                "recommended_action": actions.get("action_type") or "",
                "action_details": actions.get("action_details") or {},
                "success_rate": row.get("success_rate") or 0.0,
                "total_occurrences": row.get("usage_count") or 0,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )

    def _save_record_db(self, record: DecisionRecord) -> None:
        if not record.record_id:
            return
        payload = self._record_to_db_row(record)
        existing = (
            self.client.table("decision_records").select("id").eq("decision_id", record.record_id).limit(1).execute()
        )
        if existing.data:
            self.client.table("decision_records").update(payload).eq("id", existing.data[0]["id"]).execute()
        else:
            self.client.table("decision_records").insert(payload).execute()

    def _save_pattern_db(self, pattern: DecisionPattern) -> None:
        payload = self._pattern_to_db_row(pattern)
        existing = (
            self.client.table("decision_patterns")
            .select("id")
            .eq("pattern_name", pattern.pattern_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            self.client.table("decision_patterns").update(payload).eq("id", existing.data[0]["id"]).execute()
        else:
            self.client.table("decision_patterns").insert(payload).execute()

    def _record_to_db_row(self, record: DecisionRecord) -> dict[str, Any]:
        data = record.to_dict()
        return {
            "decision_id": record.record_id,
            "site_id": self._resolve_site_uuid(record.site_id),
            "equipment_id": self._resolve_equipment_uuid(record.equipment_id),
            "decision_type": record.event_type or record.action_type or "recommendation_outcome",
            "decision_data": data,
            "reasoning": record.diagnosis or record.outcome_details or "",
            "outcome": record.outcome.value,
            "confidence": record.diagnosis_confidence,
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def _pattern_to_db_row(self, pattern: DecisionPattern) -> dict[str, Any]:
        site_id = pattern.applicable_sites[0] if pattern.applicable_sites else ""
        return {
            "pattern_name": pattern.pattern_id,
            "site_id": self._resolve_site_uuid(site_id),
            "pattern_type": pattern.event_type or "decision_memory",
            "trigger_conditions": {
                "event_type": pattern.event_type,
                "equipment_type": pattern.equipment_type,
                "diagnosis": pattern.likely_diagnosis,
                "seasonal_pattern": pattern.seasonal_pattern,
            },
            "recommended_actions": {
                "action_type": pattern.recommended_action,
                "action_details": pattern.action_details,
                "avg_resolution_time_minutes": pattern.avg_resolution_time_minutes,
                "resolved_count": pattern.resolved_count,
            },
            "success_rate": pattern.success_rate,
            "usage_count": pattern.total_occurrences,
            "created_at": pattern.created_at.isoformat()
            if isinstance(pattern.created_at, datetime)
            else pattern.created_at,
            "updated_at": pattern.updated_at.isoformat()
            if isinstance(pattern.updated_at, datetime)
            else pattern.updated_at,
        }

    def _resolve_site_uuid(self, site_id: str | None) -> str | None:
        if not site_id:
            return None
        if site_id in self._site_uuid_cache:
            return self._site_uuid_cache[site_id]
        try:
            resp = self.client.table("sites").select("id").eq("code", site_id).limit(1).execute()
            value = resp.data[0]["id"] if resp.data else None
        except Exception as e:
            logger.debug("Failed to resolve site UUID for %s: %s", site_id, e)
            value = None
        self._site_uuid_cache[site_id] = value
        return value

    def _resolve_equipment_uuid(self, equipment_id: str | None) -> str | None:
        if not equipment_id:
            return None
        if equipment_id in self._equipment_uuid_cache:
            return self._equipment_uuid_cache[equipment_id]
        try:
            resp = self.client.table("equipment").select("id").eq("code", equipment_id).limit(1).execute()
            value = resp.data[0]["id"] if resp.data else None
        except Exception as e:
            logger.debug("Failed to resolve equipment UUID for %s: %s", equipment_id, e)
            value = None
        self._equipment_uuid_cache[equipment_id] = value
        return value


# -----------------------------------------------------------------
# Singleton
# -----------------------------------------------------------------

_service: DecisionMemoryService | None = None


def get_decision_memory_service() -> DecisionMemoryService:
    """Get or create singleton DecisionMemoryService."""
    global _service
    if _service is None:
        _service = DecisionMemoryService()
    return _service


def reset_decision_memory_service() -> None:
    """Reset singleton for testing."""
    global _service
    _service = None
