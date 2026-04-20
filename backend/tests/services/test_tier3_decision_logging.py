"""Regression tests for Tier 3 auto-execute decision logging.

Verifies that approval_service.auto_execute_recommendation() correctly calls
parasite_decision_repository.record_decision() (not the non-existent log_decision).

Bug: approval_service.py called parasite_repo.log_decision() which doesn't exist
on ParasiteDecisionRepository (the method is record_decision). This would cause
AttributeError at runtime for every Tier 3 auto-execute path.

Fix: Replaced all 3 log_decision() calls with record_decision({...}) using the
correct dict-based argument format.
"""

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class MockRecommendation:
    id: str = "rec-001"
    target_equipment: str = "S002-CHILLER-B1-001"
    site_id: str = "site-002"
    status: Any = None
    action: dict = None

    def __post_init__(self):
        if self.action is None:
            self.action = {"point": "cooling_setpoint", "value": 22.0}
        if self.status is None:
            from app.models.recommendation import RecommendationStatus

            self.status = RecommendationStatus.PENDING


def _mock_gate_pass():
    """Return a mock quality gate result that passes."""
    gate = MagicMock()
    gate.overall = MagicMock(value="pass")
    gate.enforcement = MagicMock(value="normal")
    gate.failed_rules = []
    gate.warn_rules = []
    gate.reason_codes = []
    return gate


class TestTierRoutingResultHasDecisionId:
    """TierRoutingResult must include a decision_id UUID."""

    def test_decision_id_auto_generated(self):
        from app.services.tier_routing_engine import TierRoutingResult

        result = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.92,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="High confidence chiller optimization",
            equipment_type="CHILLER",
            risk_level="medium",
        )
        assert result.decision_id
        assert len(result.decision_id) == 36  # UUID format

    def test_decision_id_unique_per_instance(self):
        from app.services.tier_routing_engine import TierRoutingResult

        r1 = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.9,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="test",
            equipment_type="FCU",
            risk_level="low",
        )
        r2 = TierRoutingResult(
            tier="tier2",
            action="require_approval",
            confidence_score=0.75,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="test",
            equipment_type="FCU",
            risk_level="low",
        )
        assert r1.decision_id != r2.decision_id


class TestRecordDecisionMethodExists:
    """ParasiteDecisionRepository must have record_decision, not log_decision."""

    def test_record_decision_exists(self):
        from app.database.repositories.parasite_decision_repository import (
            ParasiteDecisionRepository,
        )

        repo = ParasiteDecisionRepository()
        assert hasattr(repo, "record_decision")
        assert callable(repo.record_decision)

    def test_log_decision_does_not_exist(self):
        """Regression: log_decision was never a real method."""
        from app.database.repositories.parasite_decision_repository import (
            ParasiteDecisionRepository,
        )

        repo = ParasiteDecisionRepository()
        assert not hasattr(repo, "log_decision")


class TestTier3SafetyFailureLogging:
    """When safety validation fails, decision is recorded as failed."""

    @pytest.mark.asyncio
    async def test_safety_failure_records_decision(self):
        from app.services.approval_service import ApprovalService
        from app.services.tier_routing_engine import TierRoutingResult

        service = ApprovalService()

        routing_result = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.92,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="High confidence",
            equipment_type="CHILLER",
            risk_level="medium",
        )

        mock_rec = MockRecommendation()

        with (
            patch.object(service, "recommendations_repo", new_callable=MagicMock) as mock_repo,
            patch.object(service, "_validate_safety", new_callable=AsyncMock) as mock_safety,
            patch.object(service, "_check_quality_gate", new_callable=AsyncMock) as mock_gate,
            patch("app.services.approval_service.ParasiteDecisionRepository") as MockParasiteRepo,
        ):
            mock_repo.get_by_id = AsyncMock(return_value=mock_rec)
            mock_safety.return_value = {"is_safe": False, "reason": "Temperature out of range"}
            mock_gate.return_value = _mock_gate_pass()

            mock_parasite = MagicMock()
            mock_parasite.record_decision = AsyncMock(return_value={"id": routing_result.decision_id})
            MockParasiteRepo.return_value = mock_parasite

            result = await service.auto_execute_recommendation(
                recommendation_id="rec-001",
                routing_result=routing_result,
            )

            assert not result.success
            assert "Safety constraint" in result.error_message

            # Verify record_decision called (not log_decision)
            mock_parasite.record_decision.assert_called_once()
            call_arg = mock_parasite.record_decision.call_args[0][0]
            assert call_arg["id"] == routing_result.decision_id
            assert call_arg["tier"] == "tier3"
            assert call_arg["write_status"] == "failed"
            assert "Safety constraint" in call_arg["failure_reason"]


class TestTier3WriteFailureLogging:
    """When device write fails, decision is recorded as failed."""

    @pytest.mark.asyncio
    async def test_write_failure_records_decision(self):
        from app.services.approval_service import ApprovalService
        from app.services.tier_routing_engine import TierRoutingResult

        service = ApprovalService()

        routing_result = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.92,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="High confidence",
            equipment_type="CHILLER",
            risk_level="medium",
        )

        mock_rec = MockRecommendation()

        with (
            patch.object(service, "recommendations_repo", new_callable=MagicMock) as mock_repo,
            patch.object(service, "_validate_safety", new_callable=AsyncMock) as mock_safety,
            patch.object(service, "_execute_device_write", new_callable=AsyncMock) as mock_write,
            patch.object(service, "_check_quality_gate", new_callable=AsyncMock) as mock_gate,
            patch("app.services.approval_service.ParasiteDecisionRepository") as MockParasiteRepo,
        ):
            mock_repo.get_by_id = AsyncMock(return_value=mock_rec)
            mock_safety.return_value = {"is_safe": True}
            mock_gate.return_value = _mock_gate_pass()
            # Mock device_manager.read_device_value for current value
            service.device_manager = MagicMock()
            mock_device_value = MagicMock()
            mock_device_value.value = 24.0
            service.device_manager.read_device_value = AsyncMock(return_value=mock_device_value)
            mock_write.return_value = {"success": False, "error": "Device offline"}

            mock_parasite = MagicMock()
            mock_parasite.record_decision = AsyncMock(return_value={"id": routing_result.decision_id})
            MockParasiteRepo.return_value = mock_parasite

            result = await service.auto_execute_recommendation(
                recommendation_id="rec-001",
                routing_result=routing_result,
            )

            assert not result.success
            assert "Device write failed" in result.error_message

            mock_parasite.record_decision.assert_called_once()
            call_arg = mock_parasite.record_decision.call_args[0][0]
            assert call_arg["write_status"] == "failed"
            assert "Device offline" in call_arg["failure_reason"]


class TestTier3SuccessLogging:
    """When auto-execute succeeds, decision is recorded with full context."""

    @pytest.mark.asyncio
    async def test_success_records_decision_with_context(self):
        from app.services.approval_service import ApprovalService
        from app.services.tier_routing_engine import TierRoutingResult

        service = ApprovalService()

        routing_result = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.92,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="High confidence",
            equipment_type="CHILLER",
            risk_level="medium",
        )

        mock_rec = MockRecommendation()

        mock_cov = MagicMock()
        mock_cov.verified = True

        with (
            patch.object(service, "recommendations_repo", new_callable=MagicMock) as mock_repo,
            patch.object(service, "_validate_safety", new_callable=AsyncMock) as mock_safety,
            patch.object(service, "_execute_device_write", new_callable=AsyncMock) as mock_write,
            patch.object(service, "_check_quality_gate", new_callable=AsyncMock) as mock_gate,
            patch("app.services.approval_service.get_cov_monitor_service") as mock_get_cov,
            patch.object(service, "_create_audit_log", new_callable=AsyncMock) as mock_audit,
            patch.object(service, "_record_module_feedback") as mock_feedback,
            patch("app.services.approval_service.ParasiteDecisionRepository") as MockParasiteRepo,
        ):
            mock_repo.get_by_id = AsyncMock(return_value=mock_rec)
            mock_repo.upsert = AsyncMock(return_value=True)
            mock_safety.return_value = {"is_safe": True}
            mock_gate.return_value = _mock_gate_pass()
            # Mock device_manager.read_device_value for current value
            service.device_manager = MagicMock()
            mock_device_value = MagicMock()
            mock_device_value.value = 24.0
            service.device_manager.read_device_value = AsyncMock(return_value=mock_device_value)
            mock_write.return_value = {"success": True}

            mock_cov_service = AsyncMock()
            mock_cov_service.verify_write = AsyncMock(return_value=mock_cov)
            mock_cov_service.schedule_outcome_measurement = AsyncMock()
            mock_get_cov.return_value = mock_cov_service

            mock_parasite = MagicMock()
            mock_parasite.record_decision = AsyncMock(return_value={"id": routing_result.decision_id})
            MockParasiteRepo.return_value = mock_parasite

            result = await service.auto_execute_recommendation(
                recommendation_id="rec-001",
                routing_result=routing_result,
            )

            assert result.success

            mock_parasite.record_decision.assert_called_once()
            call_arg = mock_parasite.record_decision.call_args[0][0]
            assert call_arg["id"] == routing_result.decision_id
            assert call_arg["tier"] == "tier3"
            assert call_arg["write_status"] == "success"
            assert call_arg["cov_verified"] is True
            assert call_arg["equipment_code"] == "S002-CHILLER-B1-001"
            assert call_arg["control_point"] == "cooling_setpoint"
            assert call_arg["target_value"] == 22.0
            assert call_arg["original_value"] == 24.0
            assert "correlation_id" in call_arg


class TestCorrelationIdThreading:
    """Correlation ID flows from TierRoutingResult through all decision records."""

    def test_correlation_id_on_routing_result(self):
        from app.services.tier_routing_engine import TierRoutingResult

        result = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.92,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="test",
            equipment_type="CHILLER",
            risk_level="medium",
            correlation_id="corr-abc-123",
        )
        assert result.correlation_id == "corr-abc-123"

    def test_correlation_id_defaults_empty(self):
        from app.services.tier_routing_engine import TierRoutingResult

        result = TierRoutingResult(
            tier="tier1",
            action="advisory",
            confidence_score=0.5,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="test",
            equipment_type="FCU",
            risk_level="low",
        )
        assert result.correlation_id == ""

    @pytest.mark.asyncio
    async def test_correlation_id_in_safety_failure_record(self):
        from app.services.approval_service import ApprovalService
        from app.services.tier_routing_engine import TierRoutingResult

        service = ApprovalService()

        routing_result = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.92,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="High confidence",
            equipment_type="CHILLER",
            risk_level="medium",
            correlation_id="corr-test-safety",
        )

        mock_rec = MockRecommendation()

        with (
            patch.object(service, "recommendations_repo", new_callable=MagicMock) as mock_repo,
            patch.object(service, "_validate_safety", new_callable=AsyncMock) as mock_safety,
            patch.object(service, "_check_quality_gate", new_callable=AsyncMock) as mock_gate,
            patch("app.services.approval_service.ParasiteDecisionRepository") as MockParasiteRepo,
        ):
            mock_repo.get_by_id = AsyncMock(return_value=mock_rec)
            mock_safety.return_value = {"is_safe": False, "reason": "Out of range"}
            mock_gate.return_value = _mock_gate_pass()

            mock_parasite = MagicMock()
            mock_parasite.record_decision = AsyncMock(return_value={"id": routing_result.decision_id})
            MockParasiteRepo.return_value = mock_parasite

            await service.auto_execute_recommendation(
                recommendation_id="rec-001",
                routing_result=routing_result,
            )

            call_arg = mock_parasite.record_decision.call_args[0][0]
            assert call_arg["correlation_id"] == "corr-test-safety"


class TestScheduleOutcomeMeasurementFix:
    """Regression: schedule_outcome_measurement must use correct parameters."""

    @pytest.mark.asyncio
    async def test_outcome_measurement_uses_decision_id(self):
        """Bug: was passing recommendation_id instead of decision_id."""
        from app.services.approval_service import ApprovalService
        from app.services.tier_routing_engine import TierRoutingResult

        service = ApprovalService()

        routing_result = TierRoutingResult(
            tier="tier3",
            action="auto_execute",
            confidence_score=0.92,
            threshold_source="settings",
            tier2_threshold=0.7,
            tier3_threshold=0.85,
            reason="High confidence",
            equipment_type="CHILLER",
            risk_level="medium",
        )

        mock_rec = MockRecommendation()
        mock_cov = MagicMock()
        mock_cov.verified = True

        with (
            patch.object(service, "recommendations_repo", new_callable=MagicMock) as mock_repo,
            patch.object(service, "_validate_safety", new_callable=AsyncMock) as mock_safety,
            patch.object(service, "_execute_device_write", new_callable=AsyncMock) as mock_write,
            patch.object(service, "_check_quality_gate", new_callable=AsyncMock) as mock_gate,
            patch("app.services.approval_service.get_cov_monitor_service") as mock_get_cov,
            patch.object(service, "_create_audit_log", new_callable=AsyncMock),
            patch.object(service, "_record_module_feedback"),
            patch("app.services.approval_service.ParasiteDecisionRepository") as MockParasiteRepo,
        ):
            mock_repo.get_by_id = AsyncMock(return_value=mock_rec)
            mock_repo.upsert = AsyncMock(return_value=True)
            mock_safety.return_value = {"is_safe": True}
            mock_gate.return_value = _mock_gate_pass()
            service.device_manager = MagicMock()
            service.device_manager.read_value = AsyncMock(return_value={"success": True, "value": 24.0})
            mock_write.return_value = {"success": True}

            mock_cov_service = AsyncMock()
            mock_cov_service.verify_write = AsyncMock(return_value=mock_cov)
            mock_cov_service.schedule_outcome_measurement = AsyncMock()
            mock_get_cov.return_value = mock_cov_service

            mock_parasite = MagicMock()
            mock_parasite.record_decision = AsyncMock(return_value={"id": routing_result.decision_id})
            MockParasiteRepo.return_value = mock_parasite

            result = await service.auto_execute_recommendation(
                recommendation_id="rec-001",
                routing_result=routing_result,
            )

            assert result.success
            # Verify schedule_outcome_measurement called with decision_id
            mock_cov_service.schedule_outcome_measurement.assert_called_once()
            call_kwargs = mock_cov_service.schedule_outcome_measurement.call_args[1]
            assert call_kwargs["decision_id"] == routing_result.decision_id
            assert call_kwargs["equipment_id"] == "S002-CHILLER-B1-001"
            assert "expected_outcome" in call_kwargs


class TestRollbackMethodNameFix:
    """Regression: _auto_rollback must call mark_rolled_back, not update_decision_rollback."""

    def test_mark_rolled_back_exists(self):
        from app.database.repositories.parasite_decision_repository import (
            ParasiteDecisionRepository,
        )

        repo = ParasiteDecisionRepository()
        assert hasattr(repo, "mark_rolled_back")
        assert callable(repo.mark_rolled_back)

    def test_update_decision_rollback_does_not_exist(self):
        """Regression: update_decision_rollback was never a real method."""
        from app.database.repositories.parasite_decision_repository import (
            ParasiteDecisionRepository,
        )

        repo = ParasiteDecisionRepository()
        assert not hasattr(repo, "update_decision_rollback")
