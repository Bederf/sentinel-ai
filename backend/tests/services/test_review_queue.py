"""Tests for review queue service and repository.

Phase 162: Semantic Control Foundation — Plan 05.
Covers auto-approval logic, priority calculation, bulk operations,
override workflow, decision persistence, audit trail, and queue statistics.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.point_classification import PointClassification
from app.models.review_queue import ReviewDecision, ReviewQueueEntry
from app.models.semantic_tag import SafetyClass
from app.services.review_queue_service import ReviewQueueService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_classification(
    point_id: str = "S001-AHU-B1-001.SAT",
    confidence_score: float = 0.85,
    highest_safety_class: SafetyClass | None = SafetyClass.LOW,
    validation_passed: bool = True,
    validation_errors: list[str] | None = None,
) -> PointClassification:
    from app.models.point_classification import EvidenceRecord
    from app.models.semantic_tag import EvidenceSource

    evidence = [
        EvidenceRecord(
            source=EvidenceSource.HAYSTACK_ID,
            value_found="SAT",
            rule_matched="SAT",
            weight=0.8,
            contributed_confidence=0.3,
            evidence_description="Haystack ID match",
        )
    ]
    return PointClassification(
        point_id=point_id,
        device_id="S001-AHU-B1-001",
        site_id="S001",
        equipment_type="ahu",
        semantic_tags=["supply_air_temperature_sensor"],
        confidence_score=confidence_score,
        data_quality_score=0.9,
        classification_date=datetime.utcnow(),
        highest_safety_class=highest_safety_class,
        validation_passed=validation_passed,
        validation_errors=validation_errors or [],
        evidence_records=evidence,
    )


def _make_queue_entry(
    entry_id: str = "entry-001",
    site_id: str = "S001",
    equipment_id: str = "S001-AHU-B1-001",
    confidence_score: float = 0.5,
    confidence_level: str = "MEDIUM",
    safety_class: str = "LOW",
    priority: int = 80,
    status: str = "pending",
) -> ReviewQueueEntry:
    return ReviewQueueEntry(
        id=entry_id,
        site_id=site_id,
        equipment_id=equipment_id,
        point_id=f"{equipment_id}.SAT",
        classification_id="class-001",
        semantic_tags=["supply_air_temperature_sensor"],
        confidence_score=confidence_score,
        confidence_level=confidence_level,
        safety_class=safety_class,
        automation_tier="supervised",
        validation_passed=True,
        classified_by="rule_based_v1",
        classified_at=datetime.utcnow(),
        status=status,
        priority=priority,
    )


# ---------------------------------------------------------------------------
# 1. Auto-approval logic
# ---------------------------------------------------------------------------


class TestAutoApproval:
    """High confidence + low safety + passing validations => auto-approve."""

    @pytest.mark.asyncio
    async def test_high_confidence_low_safety_auto_approved(self):
        """Classification meeting all auto-approve criteria is NOT added to queue."""
        classification = _make_classification(
            confidence_score=0.85,
            highest_safety_class=SafetyClass.LOW,
            validation_passed=True,
        )
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.add_to_queue = AsyncMock()
        service._auto_approve = AsyncMock()

        result = await service.add_classification_to_queue(classification)

        assert result == "auto_approved"
        service._auto_approve.assert_called_once()
        service.repo.add_to_queue.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_confidence_added_to_queue(self):
        """Low-confidence classification must go through review."""
        classification = _make_classification(
            confidence_score=0.3,
            highest_safety_class=SafetyClass.LOW,
            validation_passed=True,
        )
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.add_to_queue = AsyncMock(return_value="entry-abc")
        service._notify_high_priority = AsyncMock()

        result = await service.add_classification_to_queue(classification)

        assert result == "entry-abc"
        service.repo.add_to_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_safety_force_to_queue(self):
        """HIGH safety class forces classification into queue regardless of confidence."""
        classification = _make_classification(
            confidence_score=0.95,  # very high confidence
            highest_safety_class=SafetyClass.HIGH,
            validation_passed=True,
        )
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.add_to_queue = AsyncMock(return_value="entry-high-safety")
        service._notify_high_priority = AsyncMock()

        result = await service.add_classification_to_queue(classification)

        # Must go to queue despite high confidence
        assert result == "entry-high-safety"
        service.repo.add_to_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_medium_confidence_added_to_queue(self):
        """Medium-confidence classification is queued even for LOW safety."""
        classification = _make_classification(
            confidence_score=0.55,  # MEDIUM confidence
            highest_safety_class=SafetyClass.LOW,
            validation_passed=True,
        )
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.add_to_queue = AsyncMock(return_value="entry-med")
        service._notify_high_priority = AsyncMock()

        result = await service.add_classification_to_queue(classification)

        assert result == "entry-med"


# ---------------------------------------------------------------------------
# 2. Priority calculation
# ---------------------------------------------------------------------------


class TestPriorityCalculation:
    """Verify priority formula produces expected scores."""

    def setup_method(self):
        self.service = ReviewQueueService.__new__(ReviewQueueService)
        self.service.repo = MagicMock()

    def test_calculate_priority_formula_base(self):
        """High confidence, low safety, no errors → base priority near 100."""
        priority = self.service._calculate_priority(0.8, "LOW", True)
        assert priority == 100

    def test_calculate_priority_low_confidence_penalty(self):
        """Low confidence (<0.4) reduces priority by 40."""
        priority = self.service._calculate_priority(0.3, "LOW", True)
        assert priority == 60

    def test_calculate_priority_medium_confidence_penalty(self):
        """Medium confidence (0.4-0.7) reduces priority by 20."""
        priority = self.service._calculate_priority(0.55, "LOW", True)
        assert priority == 80

    def test_calculate_priority_high_safety_penalty(self):
        """HIGH safety class reduces priority by 25."""
        priority = self.service._calculate_priority(0.8, "HIGH", True)
        assert priority == 75

    def test_calculate_priority_medium_safety_penalty(self):
        """MEDIUM safety class reduces priority by 10."""
        priority = self.service._calculate_priority(0.8, "MEDIUM", True)
        assert priority == 90

    def test_calculate_priority_validation_errors_penalty(self):
        """Validation errors reduce priority by 15."""
        priority = self.service._calculate_priority(0.8, "LOW", False)
        assert priority == 85

    def test_calculate_priority_combined_worst_case(self):
        """Worst case: all penalties stacked — should not go below 1."""
        priority = self.service._calculate_priority(0.2, "HIGH", False)
        # 100 - 40 - 25 - 15 = 20
        assert priority == 20

    def test_calculate_priority_never_below_one(self):
        """Priority is always >= 1 regardless of penalty accumulation."""
        # Artificially extreme: zero confidence, HIGH safety, invalid
        priority = self.service._calculate_priority(0.0, "HIGH", False)
        assert priority >= 1

    def test_validation_errors_trigger_high_priority_notification(self):
        """Priority <= 50 means high-priority notification is sent."""
        # LOW confidence + HIGH safety = 100 - 40 - 25 = 35 → should trigger
        priority = self.service._calculate_priority(0.3, "HIGH", True)
        assert priority <= ReviewQueueService.HIGH_PRIORITY_THRESHOLD


# ---------------------------------------------------------------------------
# 3. Bulk operations
# ---------------------------------------------------------------------------


class TestBulkOperations:
    """Bulk decisions apply the same decision to multiple entries."""

    @pytest.mark.asyncio
    async def test_bulk_approve_multiple_entries(self):
        """Bulk approve applies approval to all listed entries."""
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        repo = ReviewQueueRepository()
        repo._use_json = True  # Force JSON mode (no Supabase in tests)

        # Mock make_decision to succeed
        repo.make_decision = AsyncMock(return_value=True)

        entry_ids = ["e1", "e2", "e3"]
        count = await repo.bulk_decision(entry_ids, "approve", "reviewer@test.com", "Bulk approved")

        assert count == 3
        assert repo.make_decision.call_count == 3

    @pytest.mark.asyncio
    async def test_bulk_approve_partial_success(self):
        """Bulk approve counts only successfully updated entries."""
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        repo = ReviewQueueRepository()
        repo._use_json = True

        # First succeeds, second fails
        repo.make_decision = AsyncMock(side_effect=[True, False, True])

        count = await repo.bulk_decision(["e1", "e2", "e3"], "approve", "tester")
        assert count == 2


# ---------------------------------------------------------------------------
# 4. Override workflow
# ---------------------------------------------------------------------------


class TestOverrideWorkflow:
    """Override replaces tags and triggers re-validation."""

    @pytest.mark.asyncio
    async def test_override_reclassification(self):
        """Override calls repo.make_override and triggers revalidation."""
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.make_override = AsyncMock(return_value=True)
        service._revalidate_overridden = AsyncMock()

        success = await service.override_classification(
            entry_id="entry-001",
            reviewed_by="manager@site.com",
            correct_tags=["return_air_temperature_sensor"],
            justification="Misidentified — actually a RAT sensor",
        )

        assert success is True
        service.repo.make_override.assert_called_once_with(
            entry_id="entry-001",
            reviewed_by="manager@site.com",
            correct_tags=["return_air_temperature_sensor"],
            justification="Misidentified — actually a RAT sensor",
        )
        service._revalidate_overridden.assert_called_once_with("entry-001")

    @pytest.mark.asyncio
    async def test_override_failed_does_not_revalidate(self):
        """If override fails, revalidation is NOT triggered."""
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.make_override = AsyncMock(return_value=False)
        service._revalidate_overridden = AsyncMock()

        success = await service.override_classification(
            entry_id="entry-missing",
            reviewed_by="manager@site.com",
            correct_tags=["some_tag"],
            justification="Override for missing entry",
        )

        assert success is False
        service._revalidate_overridden.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Decision persistence
# ---------------------------------------------------------------------------


class TestDecisionPersistence:
    """Decisions are stored correctly via repository."""

    @pytest.mark.asyncio
    async def test_review_decision_persistence(self):
        """Approval decision updates status and creates audit record."""
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        repo = ReviewQueueRepository()
        repo._use_json = True

        # Seed a fake entry JSON
        import json
        from pathlib import Path

        entry = _make_queue_entry("persist-test-001")
        data_dir = Path(repo._queue_json_path("persist-test-001")).parent
        data_dir.mkdir(parents=True, exist_ok=True)
        with repo._queue_json_path("persist-test-001").open("w") as f:
            json.dump(entry.model_dump(mode="json"), f, default=str)

        success = await repo.make_decision(
            entry_id="persist-test-001",
            decision_type="approve",
            reviewed_by="manager@site.com",
            review_notes="Looks correct",
        )

        assert success is True

        # Verify entry was updated
        with repo._queue_json_path("persist-test-001").open() as f:
            updated = json.load(f)
        assert updated["status"] == "approved"
        assert updated["reviewed_by"] == "manager@site.com"

        # Cleanup
        repo._queue_json_path("persist-test-001").unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_approve_calls_enable_control(self):
        """Successful approval triggers _enable_control."""
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.make_decision = AsyncMock(return_value=True)
        service._enable_control = AsyncMock()

        await service.approve_classification("entry-001", "user@site.com", "Approved")

        service._enable_control.assert_called_once_with("entry-001")

    @pytest.mark.asyncio
    async def test_reject_does_not_call_enable_control(self):
        """Rejection does NOT trigger enable_control."""
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()
        service.repo.make_decision = AsyncMock(return_value=True)
        service._enable_control = AsyncMock()

        await service.reject_classification("entry-001", "user@site.com", "tag mismatch", "Notes")

        service._enable_control.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Audit trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """All review decisions are logged for the audit trail."""

    @pytest.mark.asyncio
    async def test_review_audit_trail(self):
        """Approval creates a ReviewDecision record in decisions store."""
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        repo = ReviewQueueRepository()
        repo._use_json = True

        import json
        from pathlib import Path

        entry = _make_queue_entry("audit-trail-001")
        data_dir = Path(repo._queue_json_path("audit-trail-001")).parent
        data_dir.mkdir(parents=True, exist_ok=True)
        with repo._queue_json_path("audit-trail-001").open("w") as f:
            json.dump(entry.model_dump(mode="json"), f, default=str)

        await repo.make_decision(
            entry_id="audit-trail-001",
            decision_type="approve",
            reviewed_by="auditor@site.com",
            review_notes="Audit test approval",
        )

        # Check decision files exist
        decisions_dir = Path(repo._decision_json_path("dummy")).parent
        decision_files = list(decisions_dir.glob("*.json"))
        assert len(decision_files) >= 1

        # Find the decision for our entry
        matching = []
        for df in decision_files:
            with df.open() as f:
                d = json.load(f)
            if d.get("review_queue_id") == "audit-trail-001":
                matching.append(d)

        assert len(matching) == 1
        assert matching[0]["decision_type"] == "approve"
        assert matching[0]["reviewed_by"] == "auditor@site.com"

        # Cleanup
        repo._queue_json_path("audit-trail-001").unlink(missing_ok=True)
        for df in decisions_dir.glob("*.json"):
            with df.open() as f:
                d = json.load(f)
            if d.get("review_queue_id") == "audit-trail-001":
                df.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_review_history_returns_decisions(self):
        """get_review_history returns all decisions for an entry."""
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        repo = ReviewQueueRepository()
        repo._use_json = True

        # Store two decisions for the same entry
        decision1 = ReviewDecision(
            id="dec-h1",
            review_queue_id="hist-entry-001",
            decision_type="reject",
            reviewed_by="user1@site.com",
        )
        decision2 = ReviewDecision(
            id="dec-h2",
            review_queue_id="hist-entry-001",
            decision_type="approve",
            reviewed_by="user2@site.com",
        )
        repo._store_decision_json(decision1)
        repo._store_decision_json(decision2)

        history = await repo.get_review_history("hist-entry-001")
        assert len(history) >= 2

        review_types = {d.decision_type for d in history}
        assert "reject" in review_types
        assert "approve" in review_types

        # Cleanup
        import json
        from pathlib import Path

        decisions_dir = Path(repo._decision_json_path("dummy")).parent
        for df in decisions_dir.glob("*.json"):
            with df.open() as f:
                d = json.load(f)
            if d.get("review_queue_id") == "hist-entry-001":
                df.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 7. Queue statistics
# ---------------------------------------------------------------------------


class TestQueueStatistics:
    """Stats accurately reflect current queue state."""

    @pytest.mark.asyncio
    async def test_queue_statistics_accuracy(self):
        """Stats total_pending matches number of pending entries."""
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        repo = ReviewQueueRepository()
        repo._use_json = True

        # Mock get_pending_reviews to return controlled data
        mock_entries = [
            _make_queue_entry(f"stats-{i}", safety_class="LOW", confidence_score=0.8, confidence_level="HIGH")
            for i in range(3)
        ] + [
            _make_queue_entry(
                f"stats-h-{i}", safety_class="HIGH", confidence_score=0.3, confidence_level="LOW", priority=35
            )
            for i in range(2)
        ]
        repo.get_pending_reviews = AsyncMock(return_value=mock_entries)

        stats = await repo.get_review_stats("S001")

        assert stats.total_pending == 5
        assert stats.by_safety_class.get("LOW", 0) == 3
        assert stats.by_safety_class.get("HIGH", 0) == 2
        assert stats.high_priority_count == 2  # priority <= 50

    @pytest.mark.asyncio
    async def test_empty_queue_statistics(self):
        """Empty queue returns zero counts."""
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        repo = ReviewQueueRepository()
        repo._use_json = True
        repo.get_pending_reviews = AsyncMock(return_value=[])

        stats = await repo.get_review_stats("S001")

        assert stats.total_pending == 0
        assert stats.avg_age_hours == 0.0
        assert stats.high_priority_count == 0

    def test_get_confidence_level_mapping(self):
        """_get_confidence_level maps scores to correct labels."""
        service = ReviewQueueService.__new__(ReviewQueueService)
        service.repo = MagicMock()

        assert service._get_confidence_level(0.75) == "HIGH"
        assert service._get_confidence_level(0.70) == "HIGH"
        assert service._get_confidence_level(0.55) == "MEDIUM"
        assert service._get_confidence_level(0.40) == "MEDIUM"
        assert service._get_confidence_level(0.30) == "LOW"
        assert service._get_confidence_level(0.0) == "LOW"
